"""Project service: create, open, save, close project files.

Projects are stored as JSON files in the data/projects/ directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from loguru import logger

from core import migrations
from core.correction_service import CorrectionService
from core.models import (
    AnalysisResult,
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    SubtitleTrack,
    Timeline,
    TrackBinding,
)
from core.paths import get_projects_dir
from core.persistence import atomic_save_with_backup, load_json_with_recovery
from core.timeline_utils import split_words
from core.track_constraints import OVERLAP_EPSILON


def compute_media_fingerprint(path: str) -> str:
    """Lightweight fingerprint: size + mtime hash. O(1) regardless of file size."""
    try:
        stat = os.stat(path)
        raw = f"{stat.st_size}:{stat.st_mtime_ns}"
        return hashlib.sha256(raw.encode()).hexdigest()
    except OSError:
        return ""


def compute_media_hash_deep(path: str) -> str:
    """Full SHA-256. Only use on relink confirmation, NOT on project open."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class ProjectService:
    """Manages project lifecycle and persistence."""

    def __init__(self) -> None:
        self._current: Project | None = None
        self._current_path: Path | None = None
        # v2.3.2 stage 2: monotonic counter for ProjectPatch envelopes.
        # Frontend rejects patches with revision <= its last_seen_revision
        # to defend against out-of-order bridge responses.
        self._revision: int = 0
        # v3.0.0 M10: correction domain service (single-direction dependency)
        self.correction = CorrectionService(self)

    @property
    def current(self) -> Project | None:
        return self._current

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def active_timeline(self) -> Timeline:
        """The currently active Timeline of the open project.

        All transcript/edits/analysis operations go through this property.
        """
        if self._current is None:
            raise RuntimeError("No project loaded")
        return self._current.active_timeline

    def _update_active_timeline(self, **updates) -> Project:
        """Update the active timeline and write it back to Project.timelines.

        Returns the updated Project (also stored as self._current).
        """
        if self._current is None:
            raise RuntimeError("No project loaded")
        tl = self.active_timeline
        new_tl = tl.model_copy(update=updates)
        new_timelines = [
            new_tl if t.id == tl.id else t for t in self._current.timelines
        ]
        self._current = self._current.model_copy(update={"timelines": new_timelines})
        return self._current

    def _next_revision(self) -> int:
        """Increment and return the next revision counter.

        Always called AFTER a successful mutation, BEFORE building the
        response envelope. Per Oracle consultation, revision must be
        bumped post-mutation so concurrent in-flight requests cannot
        observe the same revision.
        """
        self._revision += 1
        return self._revision

    def _enforce_segment_sort_invariant(self) -> None:
        """Sort the active timeline's segments by start time in-place.

        v2.3.2 stage 3: the frontend ``mergedSegments`` computed property
        used to re-sort on every render because the service layer did not
        guarantee ordering. This invariant moves the cost to the write
        path so reads stay cheap. Methods that may disturb ordering
        (``update_transcript`` / ``update_segment`` with start changes /
        ``import_srt``) call this after mutation.

        v3.0.0 M11-2: MAIN TRACK ONLY by contract. Extension tracks
        (``transcript.tracks``) maintain their own ordering; the main-track
        invariant must never rewrite them.
        """
        if self._current is None:
            return
        tl = self.active_timeline
        segs = list(tl.transcript.segments)
        # Stable sort preserves insertion order for equal start times.
        sorted_segs = sorted(segs, key=lambda s: s.start)
        if [s.id for s in sorted_segs] != [s.id for s in segs]:
            new_transcript = tl.transcript.model_copy(update={"segments": sorted_segs})
            self._update_active_timeline(transcript=new_transcript)

    def _success_patch(self, meta: dict | None = None, **layers) -> dict:
        """Build a ProjectPatch response envelope for the active timeline.

        ``layers`` are passed straight to :class:`ProjectPatch`; only the
        layers the caller actually mutated should be populated. The
        ``revision`` is set via :meth:`_next_revision` and ``timeline_id``
        defaults to the active timeline. ``meta`` carries side-channel
        payloads (v3.0.1 linkage counters) -- optional, old frontends
        ignore it.
        """
        from core.models import ProjectPatch

        patch = ProjectPatch(
            revision=self._next_revision(),
            timeline_id=self._current.active_timeline_id if self._current else None,
            meta=meta,
            **layers,
        )
        return {"success": True, "data": patch.model_dump(mode="json")}

    def _success_full_fallback(self) -> dict:
        """Build a full-Project patch envelope for unsafe-to-patch writes.

        Used by methods that touch multiple timelines, switch timelines,
        or otherwise cannot be expressed as a single-layer patch.
        """
        from core.models import ProjectPatch

        if self._current is None:
            return {"success": False, "error": "No project is open"}
        patch = ProjectPatch(
            revision=self._next_revision(),
            full_project=self._current.model_dump(mode="json"),
        )
        return {"success": True, "data": patch.model_dump(mode="json")}

    # v3.0.0 M5: layered undo. Undoable layers are the timeline-scoped ones
    # the frontend actually snapshots before an operation. ``media`` /
    # ``active_timeline_id`` are not undoable (no caller snapshots them).
    # v3.0.1 M5-1: tracks/bindings join for the stacked-timeline linkage
    # operations (atomic three-layer snapshots).
    _UNDO_LAYERS = ("segments", "edits", "analysis", "tracks", "bindings")

    def apply_undo(self, layers_payload: dict, base_revision: int) -> dict:
        """Replace timeline layers from an undo/redo snapshot (M5-2).

        The single backend entry point for the layered undo path. Semantics
        (risk review 4.3 red lines):

        1. Validate the snapshot structure for *every* requested layer
           BEFORE mutating anything (all-or-nothing atomic apply).
        2. Reject stale/future ``base_revision`` (defends against
           out-of-order frontend state, same contract as the patch
           protocol's ``is_stale_patch``).
        3. Replace the layers, bump revision strictly forward, and return
           the resulting ProjectPatch via :meth:`_success_patch` so the
           frontend applies it through the existing patch channel.

        Args:
            layers_payload: mapping layer name -> layer payload
                (``segments``: list of Segment dicts, ``edits``: list of
                EditDecision dicts, ``analysis``: AnalysisData dict).
            base_revision: the frontend's last seen revision; must equal
                the current revision.

        Returns:
            ``_success_patch`` envelope on success; ``{"success": False,
            "error": ...}`` otherwise. Revision is never rewound.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        if not isinstance(layers_payload, dict) or not layers_payload:
            return {"success": False, "error": "apply_undo: empty layers payload"}

        unknown = set(layers_payload) - set(self._UNDO_LAYERS)
        if unknown:
            return {
                "success": False,
                "error": f"apply_undo: unknown layer(s): {sorted(unknown)}",
            }
        if base_revision != self._revision:
            return {
                "success": False,
                "error": (
                    f"apply_undo: stale revision {base_revision} "
                    f"(current {self._revision})"
                ),
                "data": {"current_revision": self._revision},
            }

        # Validate all layers first - no mutation on any failure.
        from core.models import AnalysisData, EditDecision, Segment, SubtitleTrack, TrackBinding

        validated: dict = {}
        try:
            if "segments" in layers_payload:
                if not isinstance(layers_payload["segments"], list):
                    raise ValueError("segments must be a list")
                validated["segments"] = [
                    Segment.model_validate(s) for s in layers_payload["segments"]
                ]
            if "edits" in layers_payload:
                if not isinstance(layers_payload["edits"], list):
                    raise ValueError("edits must be a list")
                validated["edits"] = [
                    EditDecision.model_validate(e) for e in layers_payload["edits"]
                ]
            if "analysis" in layers_payload:
                validated["analysis"] = AnalysisData.model_validate(
                    layers_payload["analysis"]
                )
            if "tracks" in layers_payload:
                if not isinstance(layers_payload["tracks"], list):
                    raise ValueError("tracks must be a list")
                validated["tracks"] = [
                    SubtitleTrack.model_validate(t) for t in layers_payload["tracks"]
                ]
            if "bindings" in layers_payload:
                if not isinstance(layers_payload["bindings"], list):
                    raise ValueError("bindings must be a list")
                validated["bindings"] = [
                    TrackBinding.model_validate(b) for b in layers_payload["bindings"]
                ]
        except Exception as exc:  # pydantic ValidationError or shape error
            return {"success": False, "error": f"apply_undo: invalid snapshot: {exc}"}

        # v3.0.1 M5-1: transcript-scoped layers merge into ONE transcript
        # model_copy so a combined segments+tracks+bindings snapshot applies
        # atomically (single replacement, no intermediate states).
        updates: dict = {}
        transcript_updates: dict = {}
        if "segments" in validated:
            transcript_updates["segments"] = validated["segments"]
        if "tracks" in validated:
            transcript_updates["tracks"] = validated["tracks"]
        if "bindings" in validated:
            transcript_updates["bindings"] = validated["bindings"]
        if transcript_updates:
            updates["transcript"] = self.active_timeline.transcript.model_copy(
                update=transcript_updates
            )
        if "edits" in validated:
            updates["edits"] = validated["edits"]
        if "analysis" in validated:
            updates["analysis"] = validated["analysis"]
        self._update_active_timeline(**updates)

        if "segments" in validated:
            # Restore the start-ascending invariant the rest of the code
            # base relies on (snapshots may be legitimately unordered).
            self._enforce_segment_sort_invariant()

        def _dump(layer: str):
            val = validated[layer]
            if isinstance(val, list):
                return [item.model_dump(mode="json") for item in val]
            return val.model_dump(mode="json")

        return self._success_patch(**{layer: _dump(layer) for layer in validated})

    def create_project(self, name: str, media_path: str, media_info: dict) -> dict:
        """Create a new project with media info."""
        media_fields = {k: v for k, v in media_info.items() if k in MediaInfo.model_fields and k != "path"}
        media_fields["media_hash"] = compute_media_fingerprint(media_path)
        project = Project(
            project=ProjectMeta(
                name=name,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
            media=MediaInfo(
                path=media_path,
                **media_fields,
            ),
        )

        project_dir = get_projects_dir() / name
        project_dir.mkdir(parents=True, exist_ok=True)
        project_path = project_dir / "project.json"
        project_path.write_text(
            project.model_dump_json(indent=2), encoding="utf-8"
        )

        self._current = project
        self._current_path = project_path
        logger.info("Created project: {} at {}", name, project_path)
        return {"success": True, "data": project.model_dump()}

    def open_project(self, path: str) -> dict:
        """Open an existing project from a JSON file."""
        try:
            project_path = Path(path)
            if not project_path.exists():
                return {"success": False, "error": f"Project file not found: {path}"}

            # v3.0.0 M2: corrupted main file falls back to .bak.1 then .bak.2.
            def _validate(raw: dict) -> Project:
                return Project.model_validate(migrations.migrate_v1_to_v2(raw))

            payload, recovered_from, tried = load_json_with_recovery(
                project_path, validate=_validate
            )
            if payload is None:
                return {
                    "success": False,
                    "error": "项目文件损坏且无可用备份",
                    "data": {"tried": tried},
                }
            project = payload

            self._current = project
            self._current_path = project_path
            logger.info("Opened project: {}", path)

            # v3.0.0 fix (macOS smoke round 2): self-heal the main file.
            # Recovery only lived in memory before, so project.json stayed
            # corrupt on disk until some later save happened. Repair now.
            if recovered_from:
                try:
                    self.save_project()
                    logger.info("Repaired corrupted project.json from {}", recovered_from)
                except Exception as e:  # noqa: BLE001 -- self-heal must not block open
                    logger.warning("Self-heal save after recovery failed: {}", e)

            # v3.0.0 M10: post-load migration chain moved to core/migrations.py
            migrations.run_post_load_migrations(self)

            # Check media path reachability
            if self._current.media and self._current.media.path:
                media_path = Path(self._current.media.path)
                if not media_path.exists():
                    result_nf = {
                        "success": False,
                        "error": "MEDIA_NOT_FOUND",
                        "data": {"path": self._current.media.path},
                    }
                    if recovered_from:
                        result_nf["recovered_from"] = recovered_from
                    return result_nf

                # Fingerprint mismatch warning (file may have been overwritten)
                warnings = []
                if self._current.media.media_hash:
                    current_fp = compute_media_fingerprint(self._current.media.path)
                    if current_fp != self._current.media.media_hash:
                        warnings.append("MEDIA_HASH_MISMATCH")

                result = {"success": True, "data": self._current.model_dump()}
                if warnings:
                    result["warnings"] = warnings
                if recovered_from:
                    result["recovered_from"] = recovered_from
                return result

            result = {"success": True, "data": self._current.model_dump()}
            if recovered_from:
                result["recovered_from"] = recovered_from
            return result

        except Exception as e:
            logger.exception("Failed to open project: {}", path)
            return {"success": False, "error": str(e)}

    def save_project(self) -> dict:
        """Save the current project to disk."""
        if self._current is None or self._current_path is None:
            return {"success": False, "error": "No project is open"}

        try:
            updated = self._current.model_copy(update={
                "project": self._current.project.model_copy(update={
                    "updated_at": datetime.now().isoformat(),
                }),
            })
            self._current = updated

            # v3.0.0 M2: fsync + backup rotation; failures inside only warn.
            atomic_save_with_backup(
                self._current_path, updated.model_dump_json(indent=2)
            )

            logger.info("Saved project to {}", self._current_path)
            return {"success": True}

        except Exception as e:
            logger.exception("Failed to save project")
            return {"success": False, "error": str(e)}

    def close_project(self) -> dict:
        """Close the current project without saving."""
        self._current = None
        self._current_path = None
        return {"success": True}

    # ------------------------------------------------------------------
    # Timeline CRUD (multi-timeline infrastructure, v2.0.0)
    # ------------------------------------------------------------------

    def create_timeline(
        self, label: str, source: str = "manual", fork_from: str | None = None
    ) -> dict:
        """Create a new timeline, optionally forking from an existing one."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl_id = f"tl_{int(datetime.now().timestamp() * 1000)}"

        if fork_from:
            parent = self._current.get_timeline(fork_from)
            if parent is None:
                return {"success": False, "error": f"Timeline not found: {fork_from}"}
            new_tl = Timeline(
                id=tl_id,
                label=label,
                source=source,
                parent_id=fork_from,
                transcript=parent.transcript.model_copy(deep=True),
                edits=[e.model_copy() for e in parent.edits],
                analysis=parent.analysis.model_copy(deep=True),
            )
        else:
            new_tl = Timeline(id=tl_id, label=label, source=source)

        new_timelines = list(self._current.timelines) + [new_tl]
        self._current = self._current.model_copy(
            update={"timelines": new_timelines, "active_timeline_id": tl_id}
        )
        logger.info("Created timeline '{}' ({})", label, tl_id)
        return {"success": True, "data": self._current.model_dump()}

    def switch_timeline(self, timeline_id: str) -> dict:
        """Switch the active timeline."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        if self._current.get_timeline(timeline_id) is None:
            return {"success": False, "error": f"Timeline not found: {timeline_id}"}
        self._current = self._current.model_copy(update={"active_timeline_id": timeline_id})
        logger.info("Switched to timeline {}", timeline_id)
        return {"success": True, "data": self._current.model_dump()}

    def delete_timeline(self, timeline_id: str) -> dict:
        """Delete a timeline (cannot delete if it's the only one)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        if len(self._current.timelines) <= 1:
            return {"success": False, "error": "Cannot delete the last timeline"}
        if self._current.get_timeline(timeline_id) is None:
            return {"success": False, "error": f"Timeline not found: {timeline_id}"}

        new_timelines = [tl for tl in self._current.timelines if tl.id != timeline_id]
        new_active = self._current.active_timeline_id
        if new_active == timeline_id:
            new_active = new_timelines[0].id
        self._current = self._current.model_copy(
            update={"timelines": new_timelines, "active_timeline_id": new_active}
        )
        logger.info("Deleted timeline {}", timeline_id)
        return {"success": True, "data": self._current.model_dump()}

    def rename_timeline(self, timeline_id: str, new_label: str) -> dict:
        """Rename a timeline."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline not found: {timeline_id}"}
        new_timelines = [
            t.model_copy(update={"label": new_label}) if t.id == timeline_id else t
            for t in self._current.timelines
        ]
        self._current = self._current.model_copy(update={"timelines": new_timelines})
        return {"success": True, "data": self._current.model_dump()}

    def duplicate_timeline(self, timeline_id: str, new_label: str) -> dict:
        """Duplicate a timeline (creates a fork)."""
        return self.create_timeline(new_label, source="duplicate", fork_from=timeline_id)

    def relink_media(self, new_path: str) -> dict:
        """Relink media to a new path. Updates path + fingerprint."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        if not Path(new_path).is_file():
            return {"success": False, "error": "File not found"}
        media = self._current.media.model_copy(update={
            "path": new_path,
            "media_hash": compute_media_fingerprint(new_path),
        })
        self._current = self._current.model_copy(update={"media": media})
        self.save_project()
        return {"success": True, "data": self._current.model_dump()}

    def update_media_waveform(self, waveform_path: str) -> dict:
        """Update the waveform_path in the current project's media info."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}
        if self._current.media is None:
            return {"success": False, "error": "No media in project"}

        updated_media = self._current.media.model_copy(update={"waveform_path": waveform_path})
        updated = self._current.model_copy(update={"media": updated_media})
        self._current = updated
        return {"success": True, "data": self._current.model_dump()}

    def update_transcript(self, segments: list[dict]) -> dict:
        """Replace subtitle segments while preserving silence segments.

        If the project already has silence segments (from silence detection),
        those are kept. Only subtitle-type segments are replaced.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        new_subtitles = [Segment.model_validate(s) for s in segments]
        existing = self.active_timeline.transcript.segments
        existing_silence = [s for s in existing if s.type == SegmentType.SILENCE]

        all_segments = new_subtitles + existing_silence
        # Sort to enforce the start-ascending invariant (G4/G13): callers
        # (e.g. SRT import) may pass segments in any order.
        all_segments.sort(key=lambda s: s.start)
        new_seg_ids = {s.id for s in all_segments}

        # Remove orphaned EditDecisions whose target_id no longer exists
        cleaned_edits = [
            e for e in self.active_timeline.edits
            if e.target_id is None or e.target_id in new_seg_ids
        ]

        self._update_active_timeline(
            # v3.0.0 M11-2 construction guard: model_copy preserves
            # engine/language/tracks/bindings (a fresh TranscriptData would
            # silently drop them).
            transcript=self.active_timeline.transcript.model_copy(
                update={"segments": all_segments}
            ),
            edits=cleaned_edits,
        )
        return {"success": True, "data": self._current.model_dump()}

    def update_transcript_meta(
        self,
        engine: str | None = None,
        language: str | None = None,
    ) -> dict:
        """Update transcript-level metadata without touching segments.

        v3.0.0 M1-1: transcription results are the single source of truth;
        this records which ASR engine/language produced the current transcript.
        Only provided fields are updated; segments/edits are left untouched.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        updates: dict = {}
        if engine is not None:
            updates["engine"] = engine
        if language is not None:
            updates["language"] = language
        if not updates:
            return {"success": True, "data": self._current.model_dump()}

        transcript = self.active_timeline.transcript.model_copy(update=updates)
        self._update_active_timeline(transcript=transcript)
        return {"success": True, "data": self._current.model_dump()}

    def import_srt_as_track(
        self,
        file_path: str,
        language: str = "",
        role: str = "extension",
    ) -> dict:
        """Import an SRT file as a read-only extension track (v3.0.0 M11-2).

        Segment ids are re-namespaced into ``track_{track_id}_seg_{start:.3f}``
        so merge / edit-decision systems can never match them against
        main-track segments. Track segments are auto-bound to main-track
        subtitle segments within a 300 ms start-time tolerance (greedy,
        time-ordered, one-to-one); bindings are written but not consumed
        this version.

        Returns:
            ``tracks`` / ``bindings`` layer patch envelope (ProjectPatch).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.subtitle_service import parse_srt

        parsed = parse_srt(file_path)
        if not parsed.get("success"):
            return {"success": False, "error": parsed.get("error", "SRT parse failed")}
        raw_segments = parsed["data"]
        if not raw_segments:
            return {"success": False, "error": "SRT file contains no subtitles"}

        from uuid import uuid4

        track_id = f"trk_{uuid4().hex[:8]}"
        track_segments = sorted(
            (
                Segment.model_validate({**s, "id": f"track_{track_id}_seg_{s['start']:.3f}"})
                for s in raw_segments
            ),
            key=lambda s: s.start,
        )
        track = SubtitleTrack(
            id=track_id,
            role=role,
            name=Path(file_path).stem,
            language=language,
            segments=track_segments,
        )

        # 300 ms tolerance auto-binding against main-track subtitle segments.
        main_subs = [
            s for s in self.active_timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE
        ]
        consumed: set[str] = set()
        bindings: list[TrackBinding] = []
        for ext in track_segments:
            main = next(
                (
                    m for m in main_subs
                    if m.id not in consumed and abs(ext.start - m.start) <= 0.3
                ),
                None,
            )
            if main is None:
                continue
            consumed.add(main.id)
            bindings.append(
                TrackBinding(
                    id=f"bind_{uuid4().hex[:8]}",
                    track_id=track_id,
                    main_segment_id=main.id,
                    extension_segment_id=ext.id,
                    start_offset=round(ext.start - main.start, 3),
                    end_offset=round(ext.end - main.end, 3),
                )
            )

        transcript = self.active_timeline.transcript.model_copy(
            update={
                "tracks": [*self.active_timeline.transcript.tracks, track],
                "bindings": [*self.active_timeline.transcript.bindings, *bindings],
            }
        )
        self._update_active_timeline(transcript=transcript)
        logger.info(
            "Imported SRT as track {} ({} segments, {} bindings, language={})",
            track_id, len(track_segments), len(bindings), language or "-",
        )
        return self._success_patch(
            tracks=transcript.tracks,
            bindings=transcript.bindings,
        )

    def create_translation_track(
        self,
        timeline_id: str,
        name: str,
        language: str,
        items: list[dict],
        bind: bool = True,
    ) -> dict:
        """Batch-write a bound translation track in ONE patch (v3.0.4 M1-4).

        Called by the LLM translation handler with the pipeline output:
        ``items = [{"segment_id", "start", "end", "text"}, ...]`` where
        ``segment_id`` references a main-track subtitle segment and
        ``text`` is its translation. This method does NO LLM work -- it
        only reconciles the items against the CURRENT main track and
        persists what still exists.

        Contract (SPEC M1-4, R1.3):

        1. Timeline pinning (entry check): ``timeline_id`` must equal
           the active timeline -- both ``_update_active_timeline`` and
           the patch envelope's ``timeline_id`` target the active
           timeline, so a mismatch is rejected with zero writes.
        2. Duplicate-language rejection: the write-side twin of the
           start_translation guard (the user may have created a same
           language track while the 1-3 minute task was running).
        3. Idempotent reconciliation: every item is checked against the
           current main-track subtitle segments. Survivors become track
           segments whose start/end are copied VERBATIM from the main
           segment (ids live in the ``track_{track_id}_seg_{start:.3f}``
           namespace so merge / edit-decision systems can never match
           them); vanished ids are reported in ``uncovered_ids`` (never
           silently dropped). Nothing surviving (or empty items) ->
           reject with zero writes.
        4. ``bind=True`` builds exact 1:1 bindings with zero offsets
           (times are copied, so extension - main == 0); ``bind=False``
           writes track segments only.
        5. Single-patch persistence via the ``import_srt_as_track``
           whole-replace pattern -- ONE ``_success_patch(tracks=...,
           bindings=...)`` envelope (revision +1, one undo step reverts
           the whole track). NEVER loop ``add_track_segment``: a
           per-segment patch means 1000 bridge round-trips, revision
           +1000, and a thousand-entry undo history for a thousand
           segment project (3.0.2 smoke already proved that trap).

        The write report (``track_id`` / ``written_count`` /
        ``target_count`` / ``uncovered_ids``) rides the patch ``meta``
        side-channel -- the sanctioned extra-data slot of a ProjectPatch
        envelope (old frontends ignore it).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from uuid import uuid4

        # Contract 6: timeline pinning, entry check, zero writes.
        if timeline_id != self._current.active_timeline_id:
            return {
                "success": False,
                "error": "Timeline no longer active: 翻译期间已切换时间轴",
            }

        tl = self.active_timeline
        # Contract 1: duplicate-language rejection, write-side twin of the
        # start_translation guard (M1-1 step 5).
        if any(
            t.role == "translation" and t.language == language
            for t in tl.transcript.tracks
        ):
            return {
                "success": False,
                "error": f"同语言翻译轨已存在（{language}），可清空或删除该轨后重试",
            }

        # Contract 2: reconcile against the CURRENT main-track subtitle
        # segments -- the task ran for minutes and segments may be gone.
        main_subs = {
            s.id: s for s in tl.transcript.segments if s.type == SegmentType.SUBTITLE
        }
        track_id = f"trk_{uuid4().hex[:8]}"
        track_segments: list[Segment] = []
        main_ids: list[str] = []
        uncovered_ids: list[str] = []
        for item in items:
            seg_id = item["segment_id"]
            main = main_subs.get(seg_id)
            if main is None:
                uncovered_ids.append(seg_id)
                continue
            track_segments.append(
                Segment(
                    id=f"track_{track_id}_seg_{main.start:.3f}",
                    type=SegmentType.SUBTITLE,
                    start=main.start,
                    end=main.end,
                    text=item["text"],
                )
            )
            main_ids.append(seg_id)

        if not track_segments:
            return {"success": False, "error": "所有目标段已被删除"}

        track = SubtitleTrack(
            id=track_id,
            role="translation",
            name=name,
            language=language,
            segments=track_segments,
        )
        # Contract 3: exact 1:1 bindings, offsets are zero because the
        # track segment times are verbatim copies of the main segment's.
        bindings: list[TrackBinding] = []
        if bind:
            bindings = [
                TrackBinding(
                    id=f"bind_{uuid4().hex[:8]}",
                    track_id=track_id,
                    main_segment_id=main_id,
                    extension_segment_id=seg.id,
                    start_offset=0.0,
                    end_offset=0.0,
                )
                for main_id, seg in zip(main_ids, track_segments, strict=True)
            ]

        # Contract 4: single whole-replace write (import_srt_as_track
        # pattern) -- one revision bump, one undo step for the track.
        transcript = tl.transcript.model_copy(
            update={
                "tracks": [*tl.transcript.tracks, track],
                "bindings": [*tl.transcript.bindings, *bindings],
            }
        )
        self._update_active_timeline(transcript=transcript)
        logger.info(
            "Created translation track {} ({} segments, {} bindings, "
            "language={}, uncovered={})",
            track_id, len(track_segments), len(bindings), language or "-",
            len(uncovered_ids),
        )
        # Contract 5: report rides the meta side-channel.
        return self._success_patch(
            tracks=transcript.tracks,
            bindings=transcript.bindings,
            meta={
                "translation": {
                    "track_id": track_id,
                    "written_count": len(track_segments),
                    "target_count": len(items),
                    "uncovered_ids": uncovered_ids,
                }
            },
        )

    def update_media_info(self, media_info: dict) -> dict:
        """Update media info in the current project."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        info = MediaInfo(
            **{k: v for k, v in media_info.items() if k in MediaInfo.model_fields},
        )
        updated = self._current.model_copy(update={"media": info})
        self._current = updated
        return {"success": True, "data": self._current.model_dump()}

    def _resolve_subtitle_overlap(
        self,
        subtitle_segments: list[Segment],
        silence_ranges: list[tuple[float, float]],
    ) -> list[Segment]:
        """Trim subtitle segments that overlap with silence ranges.

        Never deletes a subtitle entirely - only shrinks or splits it.
        """
        if not silence_ranges:
            return subtitle_segments

        result: list[Segment] = []
        for seg in subtitle_segments:
            if seg.type != SegmentType.SUBTITLE:
                result.append(seg)
                continue

            # Find all silence ranges that overlap with this subtitle
            overlapping = []
            for sil_start, sil_end in silence_ranges:
                if sil_start < seg.end and sil_end > seg.start:
                    overlapping.append((sil_start, sil_end))

            if not overlapping:
                result.append(seg)
                continue

            # Sort overlapping ranges
            overlapping.sort(key=lambda x: x[0])

            # Compute remaining parts of the subtitle after trimming
            remaining_parts: list[tuple[float, float]] = []
            current_start = seg.start

            for sil_start, sil_end in overlapping:
                if current_start < sil_start:
                    remaining_parts.append((current_start, sil_start))
                current_start = max(current_start, sil_end)

            if current_start < seg.end:
                remaining_parts.append((current_start, seg.end))

            # If no parts remain, keep the original subtitle (never delete)
            if not remaining_parts:
                result.append(seg)
                continue

            # Create segments for each remaining part
            for i, (part_start, part_end) in enumerate(remaining_parts):
                if part_end - part_start < 0.01:
                    continue
                part_id = seg.id if i == 0 else f"{seg.id}_part{i}"
                result.append(Segment(
                    id=part_id,
                    type=SegmentType.SUBTITLE,
                    start=part_start,
                    end=part_end,
                    text=seg.text,
                ))

        return result

    def _trim_silences_around_subtitles(
        self,
        silences: list[dict[str, float]],
        padding: float = 0.0,
    ) -> list[dict[str, float]]:
        """Trim silence ranges to avoid subtitle extended regions.

        For each subtitle segment, computes an extended region
        [subtitle.start - padding, subtitle.end + padding].
        Silence ranges are split/cropped to avoid these regions.
        """
        if not silences or padding <= 0:
            return silences

        # Exclude subtitles that have been confirmed for deletion
        confirmed_deleted_ids: set[str] = {
            e.target_id for e in (self.active_timeline.edits if self._current else [])
            if e.status == EditStatus.CONFIRMED and e.action == "delete" and e.target_id
        }

        subtitle_segs = sorted(
            [s for s in (self.active_timeline.transcript.segments if self._current else [])
             if s.type == SegmentType.SUBTITLE and s.id not in confirmed_deleted_ids],
            key=lambda s: s.start,
        )
        if not subtitle_segs:
            return silences

        # Build subtitle extended regions (merge overlapping)
        extended: list[tuple[float, float]] = []
        for seg in subtitle_segs:
            ext_start = max(0.0, seg.start - padding)
            ext_end = seg.end + padding
            if extended and ext_start <= extended[-1][1]:
                extended[-1] = (extended[-1][0], max(extended[-1][1], ext_end))
            else:
                extended.append((ext_start, ext_end))

        # Trim each silence range against extended regions
        result: list[dict[str, float]] = []
        for sil in silences:
            parts: list[tuple[float, float]] = [(sil["start"], sil["end"])]

            for ext_start, ext_end in extended:
                new_parts: list[tuple[float, float]] = []
                for p_start, p_end in parts:
                    if ext_end <= p_start or ext_start >= p_end:
                        new_parts.append((p_start, p_end))
                    else:
                        if p_start < ext_start:
                            new_parts.append((p_start, ext_start))
                        if ext_end < p_end:
                            new_parts.append((ext_end, p_end))
                parts = new_parts
                if not parts:
                    break

            for p_start, p_end in parts:
                if p_end - p_start > 0.01:
                    result.append({
                        "start": round(p_start, 3),
                        "end": round(p_end, 3),
                        "duration": round(p_end - p_start, 3),
                    })

        return result

    # Threshold for "ranges overlap significantly". Mirrors the frontend
    # isOverlapping(minOverlapSeconds=0.3) in segmentHelpers.ts so backend and
    # frontend agree on what counts as a competing decision.
    _SILENCE_OVERLAP_SECONDS: float = 0.3

    def _ranges_overlap(
        self,
        a_start: float, a_end: float,
        b_start: float, b_end: float,
        min_overlap: float = _SILENCE_OVERLAP_SECONDS,
    ) -> bool:
        """True if ranges [a_start,a_end] and [b_start,b_end] share more than
        ``min_overlap`` seconds. Pure function, no instance state."""
        overlap = min(a_end, b_end) - max(a_start, b_start)
        return overlap > min_overlap

    def _has_prior_decision_for_range(
        self,
        edits: list[EditDecision],
        start: float,
        end: float,
    ) -> bool:
        """True if any existing edit already represents a user decision for
        the given time range (overlap > _SILENCE_OVERLAP_SECONDS).

        Blocks silence_detection from creating a competing delete edit that
        would overwrite the prior decision in the UI (resolveSegmentState).

        Rules (any one triggers blocking):
          1. Existing ``silence_detection`` edit in the range -> dedupe.
          2. Existing ``user``-source edit of any status -> user has explicitly
             marked this range; respect it (covers user-confirmed AND user-rejected).
          3. Any other source (llm_smart_delete, llm_subtitle_correction, manual_*)
             with status CONFIRMED or REJECTED -> user has reviewed and decided.
             Pending suggestions from these sources do NOT block (they need
             silence detection's input to inform the pending review).
        """
        for e in edits:
            if not self._ranges_overlap(e.start, e.end, start, end):
                continue
            if e.source == "silence_detection":
                return True
            if e.source == "user":
                return True
            if e.status in (EditStatus.CONFIRMED, EditStatus.REJECTED):
                return True
        return False

    def add_silence_results(
        self,
        silences: list[dict],
        margin: float = 0.0,
        subtitle_padding: float = 0.0,
    ) -> dict:
        """Convert raw silence intervals to Segments + EditDecisions.

        Pipeline: raw silences -> margin shrink -> subtitle padding trim -> create segments/edits.
        Skips creating EditDecisions for silence ranges that already have
        a confirmed edit (e.g. from subtitle deletion).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        # --- D-1: Margin shrink ---
        if margin > 0:
            shrunk: list[dict] = []
            for sil in silences:
                new_start = sil["start"] + margin
                new_end = sil["end"] - margin
                if new_end - new_start > 0.01:
                    shrunk.append({
                        "start": round(new_start, 3),
                        "end": round(new_end, 3),
                        "duration": round(new_end - new_start, 3),
                    })
            silences = shrunk

        # --- D-2: Subtitle padding trim ---
        if subtitle_padding > 0:
            silences = self._trim_silences_around_subtitles(silences, padding=subtitle_padding)

        if not silences:
            return {"success": True, "data": {"message": "No silence ranges after processing"}}

        existing = self.active_timeline.transcript.segments
        existing_edits = list(self.active_timeline.edits)

        new_segments: list[Segment] = []
        new_edits: list[EditDecision] = []
        sil_idx = len([s for s in existing if s.type == SegmentType.SILENCE])

        for sil in silences:
            sil_idx += 1
            seg_id = f"sil-{sil_idx:04d}"
            edit_id = f"edit-{sil_idx:04d}"

            # Always create the silence segment (informational; shows on waveform/timeline)
            new_segments.append(Segment(
                id=seg_id,
                type=SegmentType.SILENCE,
                start=sil["start"],
                end=sil["end"],
                text="",
            ))

            # Skip creating a silence edit if the range already has a prior
            # decision that silence detection would otherwise overwrite.
            # See _has_prior_decision_for_range() for the blocking rules.
            if not self._has_prior_decision_for_range(
                existing_edits, sil["start"], sil["end"]
            ):
                new_edits.append(EditDecision(
                    id=edit_id,
                    start=sil["start"],
                    end=sil["end"],
                    action="delete",
                    source="silence_detection",
                    status=EditStatus.PENDING,
                    target_type="segment",
                    target_id=seg_id,
                ))

        all_segments = list(existing) + new_segments
        all_edits = existing_edits + new_edits

        # Note: _resolve_subtitle_overlap is deprecated. D-2 handles subtitle
        # protection via _trim_silences_around_subtitles before segment creation.

        # IMPORTANT: do NOT touch analysis data here. Earlier versions did
        # `analysis=AnalysisData(last_run=...)` which created a fresh AnalysisData
        # with results=[] and wiped all LLM analysis results (smart_delete,
        # subtitle_correction, highlight). On next project open, _migrate_highlights
        # then removed the now-orphaned edits, destroying AI suggestions.
        self._update_active_timeline(
            # v3.0.0 M11-2 construction guard (see update_transcript).
            transcript=self.active_timeline.transcript.model_copy(
                update={"segments": all_segments}
            ),
            edits=all_edits,
        )
        logger.info("Added {} silence segments to project", len(new_segments))
        return {"success": True, "data": self._current.model_dump()}

    def update_edit_decision(self, edit_id: str, status: str) -> dict:
        """Update the status of an edit decision."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        try:
            new_status = EditStatus(status)
        except ValueError:
            return {"success": False, "error": f"Invalid status: {status}"}

        updated_edits = []
        found = False
        for edit in self.active_timeline.edits:
            if edit.id == edit_id:
                updated_edits.append(edit.model_copy(update={"status": new_status}))
                found = True
            else:
                updated_edits.append(edit)

        if not found:
            return {"success": False, "error": f"Edit decision not found: {edit_id}"}

        self._update_active_timeline(edits=updated_edits)
        return self._success_patch(edits=updated_edits)

    def update_edit_decisions_batch(self, edit_ids: list[str], status: str) -> dict:
        """Batch update the status of multiple edit decisions.

        v2.1.1: Used by SuggestionPanel group-level actions (confirm-all-in-group,
        reject-all-in-group, reset-all-in-group) to avoid N sequential RPCs.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        try:
            new_status = EditStatus(status)
        except ValueError:
            return {"success": False, "error": f"Invalid status: {status}"}

        ids_set = set(edit_ids)
        updated_edits = []
        matched = 0
        for edit in self.active_timeline.edits:
            if edit.id in ids_set:
                updated_edits.append(edit.model_copy(update={"status": new_status}))
                matched += 1
            else:
                updated_edits.append(edit)

        if matched == 0:
            return {"success": False, "error": "No matching edit decisions found"}

        self._update_active_timeline(edits=updated_edits)
        logger.info("Batch-updated {} edits to {}", matched, new_status.value)
        return self._success_patch(edits=updated_edits)

    def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
        """Permanently remove edit decisions and associated data by id.

        Cascading cleanup:
        1. Remove EditDecision entries from timeline.edits
        2. Remove associated AnalysisResult entries from timeline.analysis.results
        3. Clear dirty_flags on affected segments (only correction-related flags)
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        ids_set = set(edit_ids)
        tl = self.active_timeline

        # 1. Find edits to remove + collect their analysis_ids and target segment_ids
        removed_analysis_ids: set[str] = set()
        affected_seg_ids: set[str] = set()
        for e in tl.edits:
            if e.id in ids_set:
                if e.analysis_id:
                    removed_analysis_ids.add(e.analysis_id)
                if e.target_id:
                    affected_seg_ids.add(e.target_id)

        updated_edits = [e for e in tl.edits if e.id not in ids_set]
        removed = len(tl.edits) - len(updated_edits)
        if removed == 0:
            return {"success": False, "error": "No matching edit decisions found"}

        # 2. Remove associated AnalysisResults
        updated_results = [
            r for r in tl.analysis.results
            if r.id not in removed_analysis_ids
        ]

        # 3. Clear dirty_flags on affected segments
        #    Only clear correction-related flags that are tied to AnalysisResult
        #    lifecycle. Leave user-edit flags (text_edited, merged, split,
        #    search_replaced) untouched -- those are independent of edit decisions.
        CORRECTION_FLAGS = ("llm_corrected", "llm_uncovered")
        updated_segments = list(tl.transcript.segments)
        cleaned_count = 0
        for i, seg in enumerate(updated_segments):
            if seg.id in affected_seg_ids:
                flags_to_remove = [k for k in CORRECTION_FLAGS if k in seg.dirty_flags]
                if flags_to_remove:
                    new_flags = {k: v for k, v in seg.dirty_flags.items()
                                 if k not in CORRECTION_FLAGS}
                    updated_segments[i] = seg.model_copy(update={"dirty_flags": new_flags})
                    cleaned_count += 1

        self._update_active_timeline(
            edits=updated_edits,
            analysis=tl.analysis.model_copy(update={"results": updated_results}),
            transcript=tl.transcript.model_copy(update={"segments": updated_segments}),
        )

        logger.info(
            "Permanently deleted %d edits + %d analysis results + cleaned %d segments",
            removed,
            len(tl.analysis.results) - len(updated_results),
            cleaned_count,
        )
        return {"success": True, "data": self._current.model_dump()}

    def add_range_decision(
        self, start: float, end: float, action: str = "delete", source: str = "manual"
    ) -> dict:
        """Add a manual range EditDecision (v3.0.4 M4-1, R4.1).

        Creates a ``target_type="range"`` edit covering ``[start, end]``.
        Unlike subtitle_trim (deterministic, regenerable, CONFIRMED at
        creation), manual ranges are PENDING at creation -- they need
        human review before export/preview consumers pick them up.

        Contract (SPEC M4-1, validation order per PLAN P3-5):

        1. clamp: ``start = max(0, start)``; ``end = min(upper, end)``
           where upper = media.duration, or -- media missing -- the max
           end of main-track subtitle segments (same bound caliber as
           generate_subtitle_keep_ranges). No media AND no subtitle
           segments -> reject first (empty-max() guard, mirrors the
           "No subtitle segments found" early rejection). ``end <= start``
           after clamp -> reject.
        2. action must be "delete" or "keep" (entry-level check ahead of
           the model Literal).
        3. dedup (same threshold/criteria as the subtitle_trim generation
           side): an existing edit (any status) with the same action and
           ``|e.start - start| < 0.05 and |e.end - end| < 0.05`` ->
           idempotent return of that edit's id (no patch, zero writes).
           Cross-action overlap passes (keep exists to punch through
           delete, M4-4); arbitrarily-overlapping non-near-equal ranges
           pass (range overlap is a legal state).
        4. new edit: id ``edit-manual-{uuid4().hex[:8]}`` (uuid guards
           against id collision after historical deletions; the
           sequential subtitle_trim ids rely on wholesale regeneration
           and do not fit incremental manual adds).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        # 1. clamp to a defensible upper bound
        if self._current.media is not None:
            upper_bound = self._current.media.duration
        else:
            subtitle_ends = [
                s.end for s in self.active_timeline.transcript.segments
                if s.type == SegmentType.SUBTITLE
            ]
            if not subtitle_ends:
                return {
                    "success": False,
                    "error": "无媒体时长且无字幕段，无法确定范围上界",
                }
            upper_bound = max(subtitle_ends)

        clamped_start = max(0.0, start)
        clamped_end = min(upper_bound, end)
        if clamped_end <= clamped_start:
            return {
                "success": False,
                "error": (
                    f"Invalid range: end ({clamped_end}) must be greater "
                    f"than start ({clamped_start})"
                ),
            }

        # 2. action validation
        if action not in ("delete", "keep"):
            return {
                "success": False,
                "error": f"Invalid action: {action} (must be 'delete' or 'keep')",
            }

        # 3. idempotent dedup: same action + near-equal bounds (any status)
        for edit in self.active_timeline.edits:
            if (
                edit.action == action
                and abs(edit.start - clamped_start) < 0.05
                and abs(edit.end - clamped_end) < 0.05
            ):
                return {
                    "success": True,
                    "data": {"edit_id": edit.id, "duplicate": True},
                }

        # 4. create the pending manual range edit
        new_edit = EditDecision(
            id=f"edit-manual-{uuid4().hex[:8]}",
            start=clamped_start,
            end=clamped_end,
            action=action,
            source=source,
            status=EditStatus.PENDING,
            priority=100,
            target_type="range",
            target_id=None,
        )
        updated_edits = [*self.active_timeline.edits, new_edit]
        self._update_active_timeline(edits=updated_edits)
        logger.info(
            "Added manual range decision [{:.3f}s, {:.3f}s] action={} ({})",
            clamped_start, clamped_end, action, new_edit.id,
        )
        return self._success_patch(edits=updated_edits)

    def _apply_main_linkage(
        self,
        segment_id: str,
        old_range: tuple[float, float],
        new_range: tuple[float, float],
    ) -> tuple[list, list, dict] | None:
        """v3.0.1 M2-1 step 4: linkage resolution after a main-track
        move/trim, per affected extension track:

        Phase A (unbound segments): segments crossed by the new main range
        keep their longest uncovered side; below-minimum ones are deleted
        (the passive reconcile rule, SPEC M1-3).

        Phase B (bound segments): FOLLOW WINS -- the synced geometry is the
        segment's expected state, so it is never "resolved away" for being
        inside the main range. It is clamped to [0, duration]; only when
        the clamped geometry still overlaps a placed sibling is it deleted
        and unbound (no room on the lane; MVP ruling, no fine squeezing --
        recorded in SPEC errata).

        Red lines (SPEC M0-3): reconcile NEVER rewrites the main track;
        offsets are rebuilt wholesale from the final geometry; returned
        layers are FULL layer arrays (frontend merges in place).

        Returns ``(all_tracks, all_bindings, counters)`` or ``None`` when
        the segment has no bindings (or there are no tracks at all).
        """
        from core.track_constraints import (
            MIN_SEGMENT_DURATION,
            clamp_extension_range,
            overlaps_neighbors,
            rebuild_binding_offsets,
            reconcile_extension_track,
            sync_bound_extension_for_main,
        )

        tl = self.active_timeline
        tracks = list(tl.transcript.tracks)
        if not tracks:
            return None
        all_bindings = list(tl.transcript.bindings)
        bindings = [b for b in all_bindings if b.main_segment_id == segment_id]
        if not bindings:
            return None

        duration = self._current.media.duration if self._current.media else 0.0
        counters: dict = {"squeezed": 0, "removed": 0, "unbound": 0}
        dropped_binding_ids: set[str] = set()

        by_track: dict[str, list] = {}
        for b in bindings:
            by_track.setdefault(b.track_id, []).append(b)

        for track_id, tbindings in by_track.items():
            track = next((t for t in tracks if t.id == track_id), None)
            if track is None:
                # Dangling binding -> dissolve.
                counters["unbound"] += len(tbindings)
                dropped_binding_ids.update(b.id for b in tbindings)
                continue

            ext_by_id = {s.id: s for s in track.segments}
            candidates = []  # (binding, ext_seg, synced_range)
            for b in tbindings:
                ext = ext_by_id.get(b.extension_segment_id)
                if ext is None:
                    counters["unbound"] += 1
                    dropped_binding_ids.add(b.id)
                    continue
                synced = sync_bound_extension_for_main(
                    old_range, new_range, (ext.start, ext.end)
                )
                candidates.append((b, ext, synced))
            if not candidates:
                continue

            moved_ids = {ext.id for _, ext, _ in candidates}
            # Phase A targets UNBOUND segments only -- segments bound to
            # OTHER main segments belong to their own linkage and are never
            # passively resolved here (they move with their own main).
            bound_ext_ids = {b.extension_segment_id for b in all_bindings}
            unbound_segs = [
                s for s in track.segments
                if s.id not in moved_ids and s.id not in bound_ext_ids
            ]
            result = reconcile_extension_track(unbound_segs, [new_range])
            counters["squeezed"] += result.counters.squeezed
            counters["removed"] += len(result.removed_ids)
            removed_unbound = set(result.removed_ids)
            reconciled_by_id = {item["id"]: item for item in result.segments}

            placed: list = []
            for s in track.segments:
                if s.id in moved_ids or s.id in removed_unbound:
                    continue
                geom = reconciled_by_id.get(s.id)
                if geom is not None and (
                    abs(geom["start"] - s.start) > 1e-9 or abs(geom["end"] - s.end) > 1e-9
                ):
                    placed.append(
                        s.model_copy(update={"start": geom["start"], "end": geom["end"]})
                    )
                else:
                    placed.append(s)

            # -- Phase B: bound segments follow (follow wins) -------------
            for b, ext, synced in candidates:
                g = clamp_extension_range(synced[0], synced[1], duration)
                if g[1] - g[0] < MIN_SEGMENT_DURATION - 1e-6:
                    # Degenerate media -- no room at all.
                    counters["removed"] += 1
                    counters["unbound"] += 1
                    dropped_binding_ids.add(b.id)
                    continue
                if overlaps_neighbors(g[0], g[1], placed, ext.id):
                    # No free space on the lane -> delete + unbind (MVP
                    # ruling: honest removal + undo, no fine squeezing).
                    counters["removed"] += 1
                    counters["unbound"] += 1
                    dropped_binding_ids.add(b.id)
                    continue
                placed.append(ext.model_copy(update={"start": g[0], "end": g[1]}))
                new_offsets = rebuild_binding_offsets(new_range, (g[0], g[1]))
                idx = next(i for i, x in enumerate(all_bindings) if x.id == b.id)
                all_bindings[idx] = all_bindings[idx].model_copy(update=new_offsets)

            # Extension tracks maintain their own start ordering (M11-2).
            placed.sort(key=lambda s: s.start)
            tidx = next(i for i, t in enumerate(tracks) if t.id == track_id)
            tracks[tidx] = track.model_copy(update={"segments": placed})

        if dropped_binding_ids:
            all_bindings = [b for b in all_bindings if b.id not in dropped_binding_ids]

        return tracks, all_bindings, counters

    def update_segment(self, segment_id: str, updates: dict) -> dict:
        """Update a segment's fields (start, end, text)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        # v3.0.1 M2-1: extension-track segments live in the track_ id
        # namespace and go through their own channel (update_track_segment).
        if segment_id.startswith("track_"):
            return {
                "success": False,
                "error": (
                    "update_segment: use update_track_segment for "
                    "extension-track segments (track_ namespace)"
                ),
            }

        allowed_fields = {"start", "end", "text"}
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return {"success": False, "error": "No valid fields to update"}

        old_seg = next(
            (s for s in self.active_timeline.transcript.segments if s.id == segment_id),
            None,
        )
        if old_seg is None:
            return {"success": False, "error": f"Segment not found: {segment_id}"}

        # v3.0.1 M2-1 step 4: linkage follow for bound extension segments
        # (computed BEFORE the main-track mutation so the whole change —
        # main geometry + extension tracks + bindings — lands as one patch).
        linkage = None
        cand_start = old_seg.start
        cand_end = old_seg.end
        if "start" in filtered or "end" in filtered:
            cand_start = float(filtered.get("start", old_seg.start))
            cand_end = float(filtered.get("end", old_seg.end))
            for other in self.active_timeline.transcript.segments:
                if other.id == segment_id:
                    continue
                if (
                    cand_start < other.end - OVERLAP_EPSILON
                    and cand_end > other.start + OVERLAP_EPSILON
                ):
                    return {
                        "success": False,
                        "error": (
                            f"update_segment: segment {segment_id} "
                            f"[{cand_start:.3f}, {cand_end:.3f}] overlaps "
                            f"{other.id} [{other.start:.3f}, {other.end:.3f}]"
                        ),
                    }
            linkage = self._apply_main_linkage(
                segment_id,
                (old_seg.start, old_seg.end),
                (cand_start, cand_end),
            )

        updated_segments = []
        updated_seg = None
        for seg in self.active_timeline.transcript.segments:
            if seg.id == segment_id:
                updated_seg = seg.model_copy(update=filtered)
                updated_segments.append(updated_seg)
            else:
                updated_segments.append(seg)

        updated_transcript_updates: dict = {"segments": updated_segments}
        if linkage is not None:
            new_tracks, new_bindings, _counters = linkage
            updated_transcript_updates["tracks"] = new_tracks
            updated_transcript_updates["bindings"] = new_bindings
        updated_transcript = self.active_timeline.transcript.model_copy(
            update=updated_transcript_updates
        )

        update_kwargs: dict = {"transcript": updated_transcript}

        # Silence-segment time changes also cascade to silence_detection edits
        # that mirror the segment's start/end. When this happens we emit a
        # combined segments + edits patch in a single response so the
        # frontend re-renders both layers atomically.
        updated_edits = None
        start_changed = "start" in filtered
        if updated_seg and ("start" in filtered or "end" in filtered) and old_seg.type == SegmentType.SILENCE:
            updated_edits = []
            for edit in self.active_timeline.edits:
                if (abs(edit.start - old_seg.start) < 0.01
                        and abs(edit.end - old_seg.end) < 0.01
                        and edit.source == "silence_detection"):
                    updated_edits.append(edit.model_copy(update={
                        "start": updated_seg.start,
                        "end": updated_seg.end,
                    }))
                else:
                    updated_edits.append(edit)
            update_kwargs["edits"] = updated_edits

        self._update_active_timeline(**update_kwargs)
        # If the segment's start time moved, the start-ascending invariant
        # (G4/G13) may now be violated -- re-sort before building the patch.
        if start_changed:
            self._enforce_segment_sort_invariant()
            # Reflect any re-sorting in the patch payload.
            updated_segments = list(self.active_timeline.transcript.segments)
        patch_kwargs: dict = {"segments": updated_segments}
        if updated_edits is not None:
            patch_kwargs["edits"] = updated_edits
        if linkage is not None:
            # v3.0.2 M1-2 (S2): the linkage path must carry the resolved
            # tracks + bindings layers in the patch (v3.0.1 SPEC M2-1 step
            # 5) -- dropping them left the frontend's track state stale
            # until an unrelated write happened to refresh the layers.
            tracks_arr, bindings_arr, linkage_counters = linkage
            patch_kwargs["tracks"] = tracks_arr
            patch_kwargs["bindings"] = bindings_arr
            patch_kwargs["meta"] = {"linkage": linkage_counters}
        return self._success_patch(**patch_kwargs)

    def update_track_segment(
        self, track_id: str, segment_id: str, updates: dict
    ) -> dict:
        """Update an extension-track segment (v3.0.1 M2-2).

        Validation chain (fixed order): track exists -> segment exists in
        the track -> ``id`` is never writable -> clamp to [0, duration]
        (min duration + round3) -> same-track overlap rejection. After a
        time change, the offsets of every binding on this segment are
        rebuilt wholesale (derivative rule); the main track is NEVER
        touched (red line M0-3).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.track_constraints import (
            MIN_SEGMENT_DURATION,
            clamp_extension_range,
            rebuild_binding_offsets,
        )

        tl = self.active_timeline
        track = next((t for t in tl.transcript.tracks if t.id == track_id), None)
        if track is None:
            return {"success": False, "error": f"Track not found: {track_id}"}

        allowed_fields = {"start", "end", "text"}
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return {"success": False, "error": "No valid fields to update"}

        ext = next((s for s in track.segments if s.id == segment_id), None)
        if ext is None:
            return {
                "success": False,
                "error": f"Segment not found in track {track_id}: {segment_id}",
            }

        updates_geom = "start" in filtered or "end" in filtered
        new_start = ext.start
        new_end = ext.end
        if updates_geom:
            new_start = float(filtered.get("start", ext.start))
            new_end = float(filtered.get("end", ext.end))
            # Minimum duration is an explicit rejection (NOT silently
            # widened): the frontend never submits below-min drags, so this
            # guards direct API calls with the same semantics the user sees.
            if new_end - new_start < MIN_SEGMENT_DURATION - 1e-6:
                return {
                    "success": False,
                    "error": (
                        f"update_track_segment: segment {segment_id} width "
                        f"{new_end - new_start:.3f} below minimum "
                        f"{MIN_SEGMENT_DURATION}"
                    ),
                }
            # Upper bound: media duration; without media, allow growing up
            # to the requested extent (nothing to clamp against).
            upper = (
                self._current.media.duration
                if self._current.media and self._current.media.duration > 0
                else max(new_start, new_end, ext.end, MIN_SEGMENT_DURATION)
            )
            new_start, new_end = clamp_extension_range(new_start, new_end, upper)
            for other in track.segments:
                if other.id == segment_id:
                    continue
                if (
                    new_start < other.end - OVERLAP_EPSILON
                    and new_end > other.start + OVERLAP_EPSILON
                ):
                    return {
                        "success": False,
                        "error": (
                            f"update_track_segment: segment {segment_id} "
                            f"[{new_start:.3f}, {new_end:.3f}] overlaps "
                            f"{other.id} [{other.start:.3f}, {other.end:.3f}]"
                        ),
                    }

        geom_updates: dict = {}
        if updates_geom:
            geom_updates = {"start": new_start, "end": new_end}
        # geom_updates wins over raw filtered values (clamped geometry).
        new_ext = ext.model_copy(update={**filtered, **geom_updates})
        if new_ext.end - new_ext.start < MIN_SEGMENT_DURATION - 1e-6:
            return {
                "success": False,
                "error": (
                    f"update_track_segment: segment {segment_id} width "
                    f"{new_ext.end - new_ext.start:.3f} below minimum"
                ),
            }

        new_segments = []
        for s in track.segments:
            if s.id == segment_id:
                new_segments.append(new_ext)
            else:
                new_segments.append(s)
        new_segments.sort(key=lambda s: s.start)

        new_tracks = [
            t.model_copy(update={"segments": new_segments})
            if t.id == track_id
            else t
            for t in tl.transcript.tracks
        ]

        # Offsets rebuild (derivative): every binding on this segment.
        rebuilt = 0
        new_bindings = list(tl.transcript.bindings)
        main_by_id = {s.id: s for s in tl.transcript.segments}
        for i, b in enumerate(new_bindings):
            if b.extension_segment_id != segment_id:
                continue
            main = main_by_id.get(b.main_segment_id)
            if main is None:
                continue
            offsets = rebuild_binding_offsets(
                (main.start, main.end), (new_ext.start, new_ext.end)
            )
            new_bindings[i] = b.model_copy(update=offsets)
            rebuilt += 1

        new_transcript = tl.transcript.model_copy(
            update={"tracks": new_tracks, "bindings": new_bindings}
        )
        self._update_active_timeline(transcript=new_transcript)

        meta = {"linkage": {"rebuilt": rebuilt}} if rebuilt else None
        return self._success_patch(
            tracks=new_tracks,
            bindings=new_bindings,
            meta=meta,
        )

    def delete_track_segment(self, track_id: str, segment_id: str) -> dict:
        """Delete an extension-track segment (v3.0.2 smoke fix).

        Bindings anchored to the deleted extension segment are dropped
        wholesale (offsets are undefined without the anchor text -- the
        derivative rule); the main track is NEVER touched (red line M0-3).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self.active_timeline
        track = next((t for t in tl.transcript.tracks if t.id == track_id), None)
        if track is None:
            return {"success": False, "error": f"Track not found: {track_id}"}

        ext = next((s for s in track.segments if s.id == segment_id), None)
        if ext is None:
            return {
                "success": False,
                "error": f"Segment not found in track {track_id}: {segment_id}",
            }

        new_segments = sorted(
            (s for s in track.segments if s.id != segment_id), key=lambda s: s.start
        )
        new_tracks = [
            t.model_copy(update={"segments": new_segments})
            if t.id == track_id
            else t
            for t in tl.transcript.tracks
        ]

        dropped = sum(
            1 for b in tl.transcript.bindings if b.extension_segment_id == segment_id
        )
        new_bindings = [
            b for b in tl.transcript.bindings if b.extension_segment_id != segment_id
        ]

        new_transcript = tl.transcript.model_copy(
            update={"tracks": new_tracks, "bindings": new_bindings}
        )
        self._update_active_timeline(transcript=new_transcript)

        meta = {"linkage": {"unbound": dropped}} if dropped else None
        return self._success_patch(
            tracks=new_tracks,
            bindings=new_bindings,
            meta=meta,
        )

    def add_track_segment(
        self, track_id: str, start: float, end: float, text: str = ""
    ) -> dict:
        """Add a segment to an extension track (v3.0.2 smoke feedback).

        Mirrors update_track_segment's validation: clamp to [0, duration],
        min duration, same-track overlap rejection. New segments are
        unbound; ids follow the import namespacing convention.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.track_constraints import (
            MIN_SEGMENT_DURATION,
            clamp_extension_range,
        )

        tl = self.active_timeline
        track = next((t for t in tl.transcript.tracks if t.id == track_id), None)
        if track is None:
            return {"success": False, "error": f"Track not found: {track_id}"}

        if end - start < MIN_SEGMENT_DURATION - 1e-6:
            return {
                "success": False,
                "error": f"add_track_segment: width {end - start:.3f} below minimum {MIN_SEGMENT_DURATION}",
            }
        upper = (
            self._current.media.duration
            if self._current.media and self._current.media.duration > 0
            else max(start, end, MIN_SEGMENT_DURATION)
        )
        start, end = clamp_extension_range(start, end, upper)
        for other in track.segments:
            if start < other.end - OVERLAP_EPSILON and end > other.start + OVERLAP_EPSILON:
                return {
                    "success": False,
                    "error": (
                        f"add_track_segment: [{start:.3f}, {end:.3f}] overlaps "
                        f"{other.id} [{other.start:.3f}, {other.end:.3f}]"
                    ),
                }

        new_seg = Segment(
            id=f"track_{track_id}_seg_{start:.3f}",
            version=1,
            type=SegmentType.SUBTITLE,
            start=start,
            end=end,
            text=text,
            speaker="",
        )
        new_segments = sorted([*track.segments, new_seg], key=lambda s: s.start)
        new_tracks = [
            t.model_copy(update={"segments": new_segments})
            if t.id == track_id
            else t
            for t in tl.transcript.tracks
        ]
        new_transcript = tl.transcript.model_copy(update={"tracks": new_tracks})
        self._update_active_timeline(transcript=new_transcript)
        return self._success_patch(tracks=new_tracks)

    def clear_track_segments(self, track_id: str) -> dict:
        """Remove every segment of a track in ONE operation (v3.0.2 smoke
        feedback: the per-segment loop churned N patches). Bindings
        anchored to the track are dropped wholesale (derivative rule)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self.active_timeline
        track = next((t for t in tl.transcript.tracks if t.id == track_id), None)
        if track is None:
            return {"success": False, "error": f"Track not found: {track_id}"}

        dropped = sum(1 for b in tl.transcript.bindings if b.track_id == track_id)
        new_bindings = [b for b in tl.transcript.bindings if b.track_id != track_id]
        new_tracks = [
            t.model_copy(update={"segments": []}) if t.id == track_id else t
            for t in tl.transcript.tracks
        ]
        new_transcript = tl.transcript.model_copy(
            update={"tracks": new_tracks, "bindings": new_bindings}
        )
        self._update_active_timeline(transcript=new_transcript)

        meta = {"linkage": {"unbound": dropped}} if dropped else None
        return self._success_patch(
            tracks=new_tracks,
            bindings=new_bindings,
            meta=meta,
        )

    def add_track(self, name: str, language: str = "", role: str = "extension") -> dict:
        """Create an empty extension track (v3.0.2 smoke feedback: tracks
        could only come from SRT import -- no way to start fresh)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        import uuid

        from core.models import SubtitleTrack

        tl = self.active_timeline
        track = SubtitleTrack(
            id=f"trk_{uuid.uuid4().hex[:8]}",
            role=role,
            name=name,
            language=language,
            segments=[],
        )
        new_tracks = [*tl.transcript.tracks, track]
        new_transcript = tl.transcript.model_copy(update={"tracks": new_tracks})
        self._update_active_timeline(transcript=new_transcript)
        return self._success_patch(tracks=new_tracks)

    def delete_track(self, track_id: str) -> dict:
        """Delete a whole extension track and every binding anchored to it
        (v3.0.2 smoke feedback: tracks could only be cleared, not removed).
        Main track untouched (red line M0-3).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self.active_timeline
        if not any(t.id == track_id for t in tl.transcript.tracks):
            return {"success": False, "error": f"Track not found: {track_id}"}

        new_tracks = [t for t in tl.transcript.tracks if t.id != track_id]
        dropped = sum(1 for b in tl.transcript.bindings if b.track_id == track_id)
        new_bindings = [b for b in tl.transcript.bindings if b.track_id != track_id]

        new_transcript = tl.transcript.model_copy(
            update={"tracks": new_tracks, "bindings": new_bindings}
        )
        self._update_active_timeline(transcript=new_transcript)

        meta = {"linkage": {"unbound": dropped}} if dropped else None
        return self._success_patch(
            tracks=new_tracks,
            bindings=new_bindings,
            meta=meta,
        )

    def update_segment_text(self, segment_id: str, text: str) -> dict:
        """Update a subtitle segment's text and set dirty_flags."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        old_seg = next(
            (s for s in self.active_timeline.transcript.segments if s.id == segment_id),
            None,
        )
        if old_seg is None:
            return {"success": False, "error": f"Segment not found: {segment_id}"}

        updated_segments = []
        for seg in self.active_timeline.transcript.segments:
            if seg.id == segment_id:
                updated_segments.append(seg.model_copy(update={
                    "text": text,
                    "dirty_flags": {**seg.dirty_flags, "text_edited": True},
                }))
            else:
                updated_segments.append(seg)

        updated_transcript = self.active_timeline.transcript.model_copy(
            update={"segments": updated_segments}
        )
        self._update_active_timeline(transcript=updated_transcript)
        return self._success_patch(segments=updated_segments)

    def add_segment(self, start: float, end: float, text: str = "", seg_type: str = "subtitle") -> dict:
        """Add a new segment to the transcript."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segment_type = SegmentType(seg_type)
        existing = self.active_timeline.transcript.segments
        # Generate unique ID
        type_prefix = "sub" if segment_type == SegmentType.SUBTITLE else "sil"
        existing_ids = {s.id for s in existing}
        idx = 1
        while f"{type_prefix}-user-{idx:04d}" in existing_ids:
            idx += 1
        seg_id = f"{type_prefix}-user-{idx:04d}"

        new_seg = Segment(
            id=seg_id,
            type=segment_type,
            start=start,
            end=end,
            text=text,
        )

        all_segments = list(existing) + [new_seg]
        all_segments.sort(key=lambda s: s.start)

        self._update_active_timeline(
            # v3.0.0 M11-2 construction guard (see update_transcript).
            transcript=self.active_timeline.transcript.model_copy(
                update={"segments": all_segments}
            ),
        )
        logger.info("Added segment {} ({:.3f}s - {:.3f}s)", seg_id, start, end)
        return {"success": True, "data": self._current.model_dump()}

    def delete_segment(self, segment_id: str) -> dict:
        """Remove a segment, its edit decisions, and (v3.0.1 M2-3) any bound
        extension segments with their bindings (paired deletion)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        # Extension-track segments are managed by their own channel.
        if segment_id.startswith("track_"):
            return {
                "success": False,
                "error": (
                    "delete_segment: use update_track_segment for "
                    "extension-track segments (track_ namespace)"
                ),
            }

        segments = self.active_timeline.transcript.segments
        target = [s for s in segments if s.id == segment_id]
        if not target:
            return {"success": False, "error": f"Segment not found: {segment_id}"}

        remaining_segs = [s for s in segments if s.id != segment_id]
        remaining_edits = [e for e in self.active_timeline.edits if e.target_id != segment_id]

        # v3.0.1 M2-3: paired deletion -- bound extension segments go with
        # the main segment, bindings dissolve.
        tl = self.active_timeline
        hit_bindings = [b for b in tl.transcript.bindings if b.main_segment_id == segment_id]
        removed_ext_ids: set[str] = set()
        for t in tl.transcript.tracks:
            removed_ext_ids |= {s.id for s in t.segments} & {
                b.extension_segment_id for b in hit_bindings
            }
        dropped_binding_ids = {b.id for b in hit_bindings}

        transcript_updates: dict = {"segments": remaining_segs}
        patch_kwargs: dict = {"segments": remaining_segs, "edits": remaining_edits}
        if hit_bindings:
            new_tracks = [
                t.model_copy(
                    update={"segments": [s for s in t.segments if s.id not in removed_ext_ids]}
                )
                for t in tl.transcript.tracks
            ]
            new_bindings = [
                b for b in tl.transcript.bindings if b.id not in dropped_binding_ids
            ]
            transcript_updates["tracks"] = new_tracks
            transcript_updates["bindings"] = new_bindings
            patch_kwargs["tracks"] = new_tracks
            patch_kwargs["bindings"] = new_bindings
            patch_kwargs["meta"] = {
                "linkage": {"removed": len(removed_ext_ids), "unbound": 0}
            }

        self._update_active_timeline(
            transcript=tl.transcript.model_copy(update=transcript_updates),
            edits=remaining_edits,
        )
        logger.info("Deleted segment {} (paired ext removals: {})", segment_id, len(removed_ext_ids))
        return self._success_patch(meta=patch_kwargs.get("meta"), **{
            k: v for k, v in patch_kwargs.items() if k != "meta"
        })

    def clear_subtitles(self) -> dict:
        """Remove all subtitle-type segments and their associated edit decisions."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = self.active_timeline.transcript.segments
        subtitle_ids = {s.id for s in segments if s.type == SegmentType.SUBTITLE}

        if not subtitle_ids:
            return {"success": True, "data": self._current.model_dump()}

        remaining_segs = [s for s in segments if s.type != SegmentType.SUBTITLE]
        remaining_edits = [
            e for e in self.active_timeline.edits
            if e.target_id not in subtitle_ids and e.source != "subtitle"
        ]

        self._update_active_timeline(
            transcript=self.active_timeline.transcript.model_copy(update={"segments": remaining_segs}),
            edits=remaining_edits,
        )
        logger.info("Cleared {} subtitle segments", len(subtitle_ids))
        return {"success": True, "data": self._current.model_dump()}

    def delete_silence_segments(self) -> dict:
        """Remove all silence-type segments and their associated edit decisions."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = self.active_timeline.transcript.segments
        silence_ids = {s.id for s in segments if s.type == SegmentType.SILENCE}

        if not silence_ids:
            return {"success": True, "data": self._current.model_dump()}

        remaining_segs = [s for s in segments if s.type != SegmentType.SILENCE]
        remaining_edits = [
            e for e in self.active_timeline.edits
            if e.target_id not in silence_ids and e.source != "silence_detection"
        ]

        self._update_active_timeline(
            transcript=self.active_timeline.transcript.model_copy(update={"segments": remaining_segs}),
            edits=remaining_edits,
        )
        logger.info("Deleted {} silence segments", len(silence_ids))
        return {"success": True, "data": self._current.model_dump()}

    def delete_subtitle_trim_edits(self) -> dict:
        """Remove all subtitle_trim source edit decisions."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        remaining_edits = [e for e in self.active_timeline.edits if e.source != "subtitle_trim"]
        removed_count = len(self.active_timeline.edits) - len(remaining_edits)

        if removed_count == 0:
            return {"success": True, "data": self._current.model_dump()}

        self._update_active_timeline(edits=remaining_edits)
        logger.info("Deleted {} subtitle trim edits", removed_count)
        return {"success": True, "data": self._current.model_dump()}

    def merge_segments(self, segment_ids: list[str]) -> dict:
        """Merge contiguous subtitle segments into one.

        Sorts by start time, validates contiguity, merges text, removes orphaned EditDecisions.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = list(self.active_timeline.transcript.segments)
        targets = [s for s in segments if s.id in segment_ids and s.type == SegmentType.SUBTITLE]
        if len(targets) < 2:
            return {"success": False, "error": "Need at least 2 subtitle segments to merge"}

        targets.sort(key=lambda s: s.start)
        merged_text = "".join(s.text for s in targets)
        # v3.0.0 M1-2: keep word-level data across merges (ordered by start,
        # which holds naturally when each source segment's words are ordered).
        merged_words = sorted(
            (w for s in targets for w in s.words), key=lambda w: w.start
        )
        merged_seg = targets[0].model_copy(update={
            "end": targets[-1].end,
            "text": merged_text,
            "words": merged_words,
            "dirty_flags": {**targets[0].dirty_flags, "merged": True},
        })

        remove_ids = {s.id for s in targets[1:]}
        new_segments = [merged_seg if s.id == targets[0].id else s
                        for s in segments if s.id not in remove_ids]

        # Remove orphaned EditDecisions that referenced removed segments
        new_edits = [e for e in self.active_timeline.edits
                     if not any(sid in remove_ids for sid in getattr(e, '_segment_ids', []))]

        self._update_active_timeline(
            transcript=self.active_timeline.transcript.model_copy(update={"segments": new_segments}),
            edits=new_edits,
        )
        logger.info("Merged {} segments into {}", len(targets), merged_seg.id)
        return {"success": True, "data": self._current.model_dump()}

    def split_segment(
        self, segment_id: str, position: float, snap_to_word: bool = False
    ) -> dict:
        """Split a subtitle segment at the given time position.

        Creates two segments: {id}-a and {id}-b. Text is split proportionally.
        v3.0.0 M1-4: with ``snap_to_word`` and word-level data present, the cut
        time snaps to the nearest word start before splitting.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = list(self.active_timeline.transcript.segments)
        target = next((s for s in segments if s.id == segment_id), None)
        if target is None:
            return {"success": False, "error": f"Segment not found: {segment_id}"}
        if target.type != SegmentType.SUBTITLE:
            return {"success": False, "error": "Can only split subtitle segments"}
        # Allow split at exact boundaries (e.g. playhead at 0.0 for a segment starting at 0.0)
        if position < target.start or position > target.end:
            return {"success": False, "error": "Split position must be within segment bounds"}

        # v3.0.0 M1-4: snap the cut to the nearest word boundary when requested
        # and word-level data is available. Report the applied offset so the UI
        # can toast "snapped +-Nms".
        snap_offset_ms = 0.0
        if snap_to_word and target.words:
            word_starts = [w.start for w in target.words if target.start <= w.start <= target.end]
            if word_starts:
                nearest = min(word_starts, key=lambda ws: abs(ws - position))
                if abs(nearest - position) <= 1.0:  # only snap within 1s, never teleport
                    snap_offset_ms = round((nearest - position) * 1000)
                    position = nearest

        # Split text proportionally by duration ratio
        total_dur = target.end - target.start
        ratio = (position - target.start) / total_dur
        split_idx = max(1, min(len(target.text) - 1, int(len(target.text) * ratio)))

        a_text = target.text[:split_idx].strip()
        b_text = target.text[split_idx:].strip()

        # v3.0.0 M1-2: split words at the text boundary. When the cut point
        # does not align with a word boundary (tolerance 2 chars), split_words
        # returns ([], []) -- prefer missing words over misaligned ones.
        if snap_to_word and target.words:
            # Snapped to a word start: assignment by word start is exact.
            a_words = [w for w in target.words if w.start < position]
            b_words = [w for w in target.words if w.start >= position]
        else:
            a_words, b_words = split_words(
                target.words, target.text, split_idx, a_text, b_text
            )

        seg_a = target.model_copy(update={
            "id": f"{segment_id}-a",
            "end": position,
            "text": a_text,
            "words": a_words,
            "dirty_flags": {**target.dirty_flags, "split": True},
        })
        seg_b = target.model_copy(update={
            "id": f"{segment_id}-b",
            "start": position,
            "text": b_text,
            "words": b_words,
            "dirty_flags": {**target.dirty_flags, "split": True},
        })

        new_segments = []
        for s in segments:
            if s.id == segment_id:
                new_segments.extend([seg_a, seg_b])
            else:
                new_segments.append(s)

        # Rebind EditDecisions that referenced the split segment.
        # v2.1.1 A-2.4 fix: previous logic used hasattr(e, '_segment_ids') which
        # never matched -- EditDecision has no such field, binding is via
        # target_type/target_id or implicit time-range overlap. The old code kept
        # every ED, so a range-type ED [start, end] still covered both a and b
        # sub-ranges, making their states appear 'synced'.
        #
        # Correct behavior:
        # - segment-targeted ED pointing at the split segment: copy to both a and b
        #   with updated target_id, so each sub-segment has an independent decision.
        # - range-targeted ED crossing the split position: cut into two at position
        #   so each sub-range binds to the correct sub-segment.
        # - all other EDs: keep as-is (time range already correct for whichever side
        #   they fall on; unrelated to this split).
        # v2.1.1 A-2.4 fix (revised): the previous attempt only updated
        # target_id on copied segment-type EDs but left start/end covering
        # the original (pre-split) time range. Because resolveSegmentState
        # treats any ED overlapping a segment by >0.3s as related, both a
        # and b sub-segments kept matching every copied ED -- so toggling
        # one still flipped the other.
        #
        # Correct behavior: when rebinding a segment-type ED to a/b, also
        # clip its time range to the corresponding sub-segment so each ED
        # only overlaps its own sub-segment.
        new_edits: list[EditDecision] = []
        target = next((s for s in self.active_timeline.transcript.segments
                       if s.id == segment_id), None)
        if target is None:
            new_edits = list(self.active_timeline.edits)
        else:
            for e in self.active_timeline.edits:
                if e.target_type == "segment" and e.target_id == segment_id:
                    new_edits.append(e.model_copy(update={
                        "id": f"{e.id}__{segment_id}-a",
                        "target_id": f"{segment_id}-a",
                        "end": position,
                    }))
                    new_edits.append(e.model_copy(update={
                        "id": f"{e.id}__{segment_id}-b",
                        "target_id": f"{segment_id}-b",
                        "start": position,
                    }))
                    continue
                if e.target_type == "range" and e.start < position and e.end > position:
                    new_edits.append(e.model_copy(update={
                        "id": f"{e.id}_a",
                        "end": position,
                    }))
                    new_edits.append(e.model_copy(update={
                        "id": f"{e.id}_b",
                        "start": position,
                    }))
                    continue
                new_edits.append(e)

        self._update_active_timeline(
            transcript=self.active_timeline.transcript.model_copy(update={"segments": new_segments}),
            edits=new_edits,
        )

        # v3.0.1 M2-3: linked split -- bound extension segments share the
        # same absolute cut instant (mapped through their offset). Per
        # binding: cut inside the ext segment -> both halves rebind to a/b
        # (offsets rebuilt); cut outside -> the binding rebinds to the side
        # overlapping the ext segment more; neither side overlaps enough ->
        # unbind (countered, never silent).
        from core.track_constraints import MIN_SEGMENT_DURATION, rebuild_binding_offsets

        tl = self.active_timeline
        hit_bindings = [b for b in tl.transcript.bindings if b.main_segment_id == segment_id]
        new_tracks = tl.transcript.tracks
        new_bindings = list(tl.transcript.bindings)
        linkage_meta = None
        if hit_bindings:
            counters = {"split": 0, "rebound": 0, "unbound": 0}
            old_binding_ids = {b.id for b in hit_bindings}
            dropped: set[str] = set()
            tracks = list(new_tracks)
            additions: list[TrackBinding] = []
            by_track: dict[str, list] = {}
            for b in hit_bindings:
                by_track.setdefault(b.track_id, []).append(b)

            for track_id, tb in by_track.items():
                tidx = next((i for i, t in enumerate(tracks) if t.id == track_id), None)
                if tidx is None:
                    counters["unbound"] += len(tb)
                    dropped.update(b.id for b in tb)
                    continue
                track = tracks[tidx]
                segs = list(track.segments)
                for b in tb:
                    ext = next((s for s in segs if s.id == b.extension_segment_id), None)
                    if ext is None:
                        counters["unbound"] += 1
                        dropped.add(b.id)
                        continue
                    cut_ext = round(position + b.start_offset, 3)
                    if ext.start + MIN_SEGMENT_DURATION <= cut_ext <= ext.end - MIN_SEGMENT_DURATION:
                        dur = ext.end - ext.start
                        ratio = (cut_ext - ext.start) / dur
                        cut_idx = max(1, min(len(ext.text) - 1, int(len(ext.text) * ratio)))
                        ext_a = ext.model_copy(update={
                            "id": f"{ext.id}__a",
                            "end": cut_ext,
                            "text": ext.text[:cut_idx].strip(),
                        })
                        ext_b = ext.model_copy(update={
                            "id": f"{ext.id}__b",
                            "start": cut_ext,
                            "text": ext.text[cut_idx:].strip(),
                        })
                        segs = [s for s in segs if s.id != ext.id]
                        segs.extend([ext_a, ext_b])
                        segs.sort(key=lambda s: s.start)
                        additions.append(b.model_copy(update={
                            "id": f"{b.id}__a",
                            "main_segment_id": seg_a.id,
                            "extension_segment_id": ext_a.id,
                            **rebuild_binding_offsets((seg_a.start, seg_a.end), (ext_a.start, ext_a.end)),
                        }))
                        additions.append(b.model_copy(update={
                            "id": f"{b.id}__b",
                            "main_segment_id": seg_b.id,
                            "extension_segment_id": ext_b.id,
                            **rebuild_binding_offsets((seg_b.start, seg_b.end), (ext_b.start, ext_b.end)),
                        }))
                        counters["split"] += 1
                    else:
                        ov_a = max(0.0, min(ext.end, position) - ext.start)
                        ov_b = max(0.0, ext.end - max(ext.start, position))
                        if max(ov_a, ov_b) >= MIN_SEGMENT_DURATION:
                            target_seg = seg_a if ov_a >= ov_b else seg_b
                            additions.append(b.model_copy(update={
                                "main_segment_id": target_seg.id,
                                **rebuild_binding_offsets(
                                    (target_seg.start, target_seg.end), (ext.start, ext.end)
                                ),
                            }))
                            counters["rebound"] += 1
                        else:
                            dropped.add(b.id)
                            counters["unbound"] += 1
                tracks[tidx] = track.model_copy(update={"segments": segs})

            new_tracks = tracks
            new_bindings = [
                b for b in new_bindings if b.id not in old_binding_ids
            ]
            new_bindings.extend(additions)
            if dropped:
                new_bindings = [b for b in new_bindings if b.id not in dropped]
            linkage_meta = {"linkage": counters}

        self._update_active_timeline(
            transcript=tl.transcript.model_copy(
                update={"segments": new_segments, "tracks": new_tracks, "bindings": new_bindings}
            ),
            edits=new_edits,
        )
        logger.info("Split segment {} at {:.3f}s (snap_offset={}ms)", segment_id, position, snap_offset_ms)
        patch_kwargs: dict = {"segments": new_segments, "edits": new_edits}
        if hit_bindings:
            patch_kwargs["tracks"] = new_tracks
            patch_kwargs["bindings"] = new_bindings
            patch_kwargs["meta"] = linkage_meta
        result = self._success_patch(**patch_kwargs)
        if snap_to_word:
            result["snap_offset_ms"] = snap_offset_ms
        return result

    def search_replace(
        self,
        query: str,
        replacement: str,
        scope: str = "all",
    ) -> dict:
        """Search and replace text in subtitle segments.

        Args:
            query: Text to search for.
            replacement: Replacement text.
            scope: "all" for all segments, or a segment ID.

        Returns dict with count of modified segments and their IDs.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = list(self.active_timeline.transcript.segments)
        modified_ids: list[str] = []
        new_segments: list[Segment] = []

        for seg in segments:
            if seg.type != SegmentType.SUBTITLE:
                new_segments.append(seg)
                continue
            if scope != "all" and seg.id != scope:
                new_segments.append(seg)
                continue
            if query in seg.text:
                new_text = seg.text.replace(query, replacement)
                new_segments.append(seg.model_copy(update={
                    "text": new_text,
                    "dirty_flags": {**seg.dirty_flags, "search_replaced": True},
                }))
                modified_ids.append(seg.id)
            else:
                new_segments.append(seg)

        if modified_ids:
            self._update_active_timeline(
                transcript=self.active_timeline.transcript.model_copy(update={"segments": new_segments}),
            )
        logger.info("Search-replace: {} segments modified", len(modified_ids))
        return {
            "success": True,
            "data": {"count": len(modified_ids), "modified_ids": modified_ids},
        }

    def mark_segments(self, segment_ids: list[str], action: str, status: str = "pending") -> dict:
        """Create or update EditDecisions for the given segments.

        Args:
            segment_ids: List of segment IDs to mark.
            action: "delete" or "keep".
            status: "pending" (default) or "confirmed" or "rejected".
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = self.active_timeline.transcript.segments
        target_segs = [s for s in segments if s.id in segment_ids]
        if not target_segs:
            return {"success": False, "error": "No matching segments found"}

        try:
            edit_status = EditStatus(status)
        except ValueError:
            edit_status = EditStatus.PENDING

        existing_edits = list(self.active_timeline.edits)
        target_seg_ids = {seg.id for seg in target_segs}
        new_edits: list[EditDecision] = []

        for seg in target_segs:
            edit_id = f"edit-user-{seg.id}"
            new_edits.append(EditDecision(
                id=edit_id,
                start=seg.start,
                end=seg.end,
                action=action,
                source="user",
                status=edit_status,
                priority=200,
                target_type="segment",
                target_id=seg.id,
            ))

        # Remove all old user edits targeting the same segments, then add new ones
        merged_edits = [
            e for e in existing_edits
            if not (e.source == "user" and e.target_id in target_seg_ids)
        ] + new_edits

        self._update_active_timeline(edits=merged_edits)
        logger.info("Marked {} segments as {} ({})", len(target_segs), action, status)
        return self._success_patch(edits=merged_edits)

    def confirm_all_suggestions(self) -> dict:
        """Set all pending edit decisions to confirmed."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        count = 0
        updated_edits = []
        for edit in self.active_timeline.edits:
            if edit.status == EditStatus.PENDING:
                updated_edits.append(edit.model_copy(update={"status": EditStatus.CONFIRMED}))
                count += 1
            else:
                updated_edits.append(edit)

        self._update_active_timeline(edits=updated_edits)
        logger.info("Confirmed {} pending edits", count)
        return {"success": True, "data": {"confirmed_count": count}}

    def reject_all_suggestions(self) -> dict:
        """Set all pending edit decisions to rejected."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        count = 0
        updated_edits = []
        for edit in self.active_timeline.edits:
            if edit.status == EditStatus.PENDING:
                updated_edits.append(edit.model_copy(update={"status": EditStatus.REJECTED}))
                count += 1
            else:
                updated_edits.append(edit)

        self._update_active_timeline(edits=updated_edits)
        logger.info("Rejected {} pending edits", count)
        return {"success": True, "data": {"rejected_count": count}}

    def get_edit_summary(self) -> dict:
        """Compute delete statistics and protection warnings.

        Protection warnings:
        - >40% of total duration marked for deletion
        - Any single segment >60s marked for deletion
        - 3+ consecutive segments marked for deletion
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = self.active_timeline.transcript.segments
        edits = self.active_timeline.edits
        warnings: list[str] = []

        # Compute total duration
        total_duration = 0.0
        for seg in segments:
            total_duration = max(total_duration, seg.end)

        # Compute delete duration
        # IMPORTANT: only count CONFIRMED edits here. Earlier versions also included
        # PENDING, which made the export summary modal show inflated edit_count /
        # delete_duration / delete_percent compared to the top-right status badge
        # (which uses frontend useExport.confirmedEdits == status=="confirmed").
        # The two must stay in sync; otherwise users see contradictory numbers.
        delete_duration = 0.0
        confirmed_edits = [
            e for e in edits
            if e.action == "delete" and e.status == EditStatus.CONFIRMED
        ]
        for edit in confirmed_edits:
            delete_duration += edit.end - edit.start

        # Warning: >40% total duration
        if total_duration > 0 and delete_duration / total_duration > 0.40:
            warnings.append(
                f"Warning: {delete_duration:.1f}s marked for deletion ({delete_duration / total_duration:.0%} of total duration)"
            )

        # Warning: single segment >60s
        for edit in confirmed_edits:
            seg_dur = edit.end - edit.start
            if seg_dur > 60:
                warnings.append(
                    f"Warning: edit {edit.id} spans {seg_dur:.1f}s (>60s threshold)"
                )

        # Warning: 3+ consecutive subtitle segments
        subtitle_segs = sorted(
            [s for s in segments if s.type == SegmentType.SUBTITLE],
            key=lambda s: s.start,
        )
        edit_seg_ids = set()
        for edit in confirmed_edits:
            for seg in subtitle_segs:
                if abs(seg.start - edit.start) < 0.01 and abs(seg.end - edit.end) < 0.01:
                    edit_seg_ids.add(seg.id)

        consecutive = 0
        for seg in subtitle_segs:
            if seg.id in edit_seg_ids:
                consecutive += 1
                if consecutive >= 3:
                    warnings.append("Warning: 3+ consecutive subtitle segments marked for deletion")
                    break
            else:
                consecutive = 0

        return {
            "success": True,
            "data": {
                "total_duration": round(total_duration, 2),
                "delete_duration": round(delete_duration, 2),
                "delete_percent": round(delete_duration / total_duration * 100, 1) if total_duration > 0 else 0,
                "edit_count": len(confirmed_edits),
                "warnings": warnings,
            },
        }

    def add_analysis_results(self, results: list[dict], source: str, clear_existing: bool = False) -> dict:
        """Store AnalysisResult entries and create EditDecisions from time ranges.

        Args:
            results: List of AnalysisResult dicts to add.
            source: Source label for generated EditDecisions.
            clear_existing: If True, clear existing results of the same type
                (and their associated EditDecisions) before adding new ones.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        analysis_results = [AnalysisResult.model_validate(r) for r in results]

        if clear_existing:
            # Clear existing results of the SAME type and their edits
            target_type = analysis_results[0].type if analysis_results else None
            removed_ar_ids: set[str] = set()
            existing_results = []
            for r in self.active_timeline.analysis.results:
                if target_type is not None and r.type == target_type:
                    removed_ar_ids.add(r.id)
                else:
                    existing_results.append(r)
            existing_edits = [
                e for e in self.active_timeline.edits
                if e.analysis_id not in removed_ar_ids
            ]
        else:
            existing_results = list(self.active_timeline.analysis.results)
            existing_edits = list(self.active_timeline.edits)

        all_results = existing_results + analysis_results

        # Create EditDecisions from analysis time ranges
        segments = self.active_timeline.transcript.segments
        seg_map = {s.id: s for s in segments}
        existing_edit_ids = {e.id for e in existing_edits}
        new_edits: list[EditDecision] = []

        # v2.1.2: Collect segments that already have explicit user decisions.
        # LLM/manual analysis must NOT create competing suggestions on segments
        # the user has already operated on -- this is the add_analysis_results
        # counterpart to add_silence_results._has_prior_decision_for_range.
        # Without this, re-running LLM smart-delete would flip user-rejected
        # ("keep") segments back to "pending delete" in resolveSegmentState.
        user_decided_target_ids: set[str] = {
            e.target_id for e in existing_edits
            if e.source == "user" and e.target_id
        }

        skipped_due_to_user_edit = 0
        for ar in analysis_results:
            # Find time range from segment_ids
            matching_segs = [seg_map[sid] for sid in ar.segment_ids if sid in seg_map]
            if not matching_segs:
                continue

            # If ANY referenced segment already has a user decision, skip creating
            # a competing edit. The AnalysisResult itself is still stored above
            # (in all_results) for record-keeping, but no EditDecision is created.
            if any(sid in user_decided_target_ids for sid in ar.segment_ids):
                skipped_due_to_user_edit += 1
                continue

            start = min(s.start for s in matching_segs)
            end = max(s.end for s in matching_segs)

            # Defensive: if edit-{ar.id} already exists (ar.id duplicate or other source
            # conflict), append _dup{N} suffix to ensure uniqueness.
            edit_id = f"edit-{ar.id}"
            if edit_id in existing_edit_ids:
                n = 2
                while f"{edit_id}_dup{n}" in existing_edit_ids:
                    n += 1
                edit_id = f"{edit_id}_dup{n}"
            existing_edit_ids.add(edit_id)

            # Highlight sources keep segments (not delete them).
            action = "keep" if source in ("llm_highlight", "manual_highlight") else "delete"
            # partial_delete: manual-handling items default to keep (rejected),
            # so they are surfaced but never auto-deleted.
            is_partial = source == "llm_smart" and getattr(ar, "category", "") == "partial_delete"
            status = EditStatus.REJECTED if is_partial else EditStatus.PENDING

            new_edits.append(EditDecision(
                id=edit_id,
                start=start,
                end=end,
                action=action,
                source=source,
                analysis_id=ar.id,
                status=status,
                priority=100,
                target_type="segment",
                target_id=ar.segment_ids[0],
            ))

        self._update_active_timeline(
            analysis=self.active_timeline.analysis.model_copy(update={
                "results": all_results,
                "last_run": datetime.now().isoformat(),
            }),
            edits=existing_edits + new_edits,
        )
        logger.info(
            "Added {} analysis results from {} ({} edits created, {} skipped due to user decisions)",
            len(analysis_results), source, len(new_edits), skipped_due_to_user_edit,
        )
        return {"success": True, "data": self._current.model_dump()}

    # ------------------------------------------------------------------
    # v2.1.0 Phase 2: P1 subtitle correction review (store / accept / reject)
    # ------------------------------------------------------------------

    def _update_timeline_by_id(self, timeline_id: str, **updates) -> Project:
        """Update an arbitrary timeline (not necessarily active) by id.

        Mirrors _update_active_timeline but targets a specific timeline.
        """
        if self._current is None:
            raise RuntimeError("No project loaded")
        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            raise ValueError(f"Timeline {timeline_id} not found")
        new_tl = tl.model_copy(update=updates)
        new_timelines = [
            new_tl if t.id == timeline_id else t for t in self._current.timelines
        ]
        self._current = self._current.model_copy(update={"timelines": new_timelines})
        return self._current

    def confirm_all_from_source(self, source: str, min_confidence: float = 0.0) -> dict:
        """Batch-confirm all edit decisions from a given source.

        Implements the 'trust this source' feature: one-click accept all
        suggestions from a specific source (e.g. 'llm_smart') that meet
        the minimum confidence threshold.

        Args:
            source: The source string to filter by (e.g. "llm_smart").
            min_confidence: Minimum confidence to auto-confirm. Lower-
                confidence items still require manual review.

        Returns:
            {"success": True, "data": {"confirmed_count": int}}
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        timeline = self.active_timeline
        confirmed_count = 0
        new_edits: list[EditDecision] = []

        for edit in timeline.edits:
            if edit.source == source and edit.status == EditStatus.PENDING:
                # Check confidence from analysis results if available
                should_confirm = True
                if min_confidence > 0:
                    # Look up confidence from analysis results
                    for result in timeline.analysis.results:
                        if edit.target_id in result.segment_ids:
                            should_confirm = result.confidence >= min_confidence
                            break

                if should_confirm:
                    new_edits.append(edit.model_copy(update={"status": EditStatus.CONFIRMED}))
                    confirmed_count += 1
                else:
                    new_edits.append(edit)
            else:
                new_edits.append(edit)

        if confirmed_count > 0:
            self._update_active_timeline(edits=new_edits)
            logger.info(f"Batch-confirmed {confirmed_count} edits from source '{source}'")

        return {"success": True, "data": {"confirmed_count": confirmed_count}}

    def generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict:
        """Generate EditDecisions to delete ranges outside subtitle segments + padding.

        For each subtitle segment, expands by `padding` seconds on both sides.
        The gaps between these expanded ranges become delete EditDecisions.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        # Collect IDs of segments with confirmed delete edits
        confirmed_deleted_ids: set[str] = {
            e.target_id for e in self.active_timeline.edits
            if e.status == EditStatus.CONFIRMED and e.action == "delete" and e.target_id
        }

        # Exclude confirmed-deleted subtitles from keep ranges
        subtitle_segs = sorted(
            [s for s in self.active_timeline.transcript.segments
             if s.type == SegmentType.SUBTITLE and s.id not in confirmed_deleted_ids],
            key=lambda s: s.start,
        )
        if not subtitle_segs:
            return {"success": False, "error": "No subtitle segments found"}

        # Compute total duration
        total_duration = max(s.end for s in self.active_timeline.transcript.segments)

        # Build expanded keep ranges (subtitle + padding)
        keep_ranges: list[tuple[float, float]] = []
        for seg in subtitle_segs:
            start = max(0.0, seg.start - padding)
            end = min(total_duration, seg.end + padding)
            if keep_ranges and start <= keep_ranges[-1][1]:
                # Merge overlapping ranges
                keep_ranges[-1] = (keep_ranges[-1][0], max(keep_ranges[-1][1], end))
            else:
                keep_ranges.append((start, end))

        # Compute delete ranges (gaps between keep ranges)
        delete_ranges: list[tuple[float, float]] = []
        current = 0.0
        for keep_start, keep_end in keep_ranges:
            if current < keep_start:
                delete_ranges.append((current, keep_start))
            current = keep_end
        if current < total_duration:
            delete_ranges.append((current, total_duration))

        # Create EditDecisions for delete ranges
        existing_edits = list(self.active_timeline.edits)
        new_edits: list[EditDecision] = []
        for i, (start, end) in enumerate(delete_ranges):
            edit_id = f"edit-subtitle-trim-{i:04d}"
            # Skip if already covered by existing edit
            already_covered = any(
                e.action == "delete"
                and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
                and abs(e.start - start) < 0.05
                and abs(e.end - end) < 0.05
                for e in existing_edits
            )
            if not already_covered:
                new_edits.append(EditDecision(
                    id=edit_id,
                    start=start,
                    end=end,
                    action="delete",
                    source="subtitle_trim",
                    # v2.3.1: subtitle_trim is a fast, user-triggered utility
                    # (regenerable on demand via delete_subtitle_trim_edits +
                    # generate_subtitle_keep_ranges). Unlike LLM suggestions
                    # that need user review, subtitle_trim edits represent
                    # deterministic inter-subtitle gaps the user has chosen to
                    # cut. Mark CONFIRMED at creation so that:
                    #   1. export_video/audio/srt/vtt apply them immediately
                    #      (via _get_confirmed_deletions: action=delete & status=confirmed)
                    #   2. export_timeline EDL/xmeml/OTIO apply them too
                    #      (via _build_keep_ranges: same filter)
                    #   3. frontend useExport.confirmedEdits counts them, so
                    #      the top-right badge and export summary modal agree
                    #      with the WorkspacePage/PreviewPlayer deleteRanges
                    #      which already treated source=subtitle_trim as
                    #      implicitly confirmed (since v2.1.1).
                    # Before this change, frontend showed them as "skipped" in
                    # preview but export kept them, producing the "export does
                    # not match my markings" user complaint.
                    status=EditStatus.CONFIRMED,
                    priority=100,
                    target_type="range",
                ))

        self._update_active_timeline(edits=existing_edits + new_edits)
        logger.info("Generated {} delete ranges from subtitle trim (padding={:.1f}s)", len(new_edits), padding)
        return {
            "success": True,
            "data": {
                "keep_ranges": len(keep_ranges),
                "delete_ranges": len(delete_ranges),
                "new_edits": len(new_edits),
                "project": self._current.model_dump(),
            },
        }

    def get_recent_projects(self, limit: int = 10) -> dict:
        """Scan data/projects/*/project.json and return sorted by updated_at."""
        projects_dir = get_projects_dir()
        if not projects_dir.exists():
            return {"success": True, "data": []}

        recent: list[dict] = []
        for project_file in projects_dir.glob("*/project.json"):
            try:
                data = json.loads(project_file.read_text(encoding="utf-8"))
                meta = data.get("project", {})
                recent.append({
                    "name": meta.get("name", project_file.parent.name),
                    "path": str(project_file),
                    "updated_at": meta.get("updated_at", ""),
                    "created_at": meta.get("created_at", ""),
                    "corrupted": False,
                })
            except (json.JSONDecodeError, OSError):
                # v3.0.0 fix (macOS smoke): a corrupted main file must still
                # show up in the recent list -- fall back to backup metadata
                # so the user can open it (open_project recovers from .bak).
                meta = None
                for i in (1, 2):
                    bak = project_file.with_suffix(f".json.bak.{i}")
                    try:
                        data = json.loads(bak.read_text(encoding="utf-8"))
                        meta = data.get("project", {})
                        break
                    except (json.JSONDecodeError, OSError):
                        continue
                if meta is not None:
                    recent.append({
                        "name": meta.get("name", project_file.parent.name),
                        "path": str(project_file),
                        "updated_at": meta.get("updated_at", ""),
                        "created_at": meta.get("created_at", ""),
                        "corrupted": True,
                    })
                continue

        recent.sort(key=lambda p: p["updated_at"], reverse=True)
        return {"success": True, "data": recent[:limit]}

    def get_settings(self) -> dict:
        """Return current application settings."""
        from core.config import load_settings
        return {"success": True, "data": load_settings()}

    def update_settings(self, updates: dict) -> dict:
        """Update application settings with the given key-value pairs."""
        from core.config import load_settings, save_settings
        settings = load_settings()
        settings.update(updates)
        save_settings(settings)
        return {"success": True, "data": settings}

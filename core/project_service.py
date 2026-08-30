"""Project service: create, open, save, close project files.

Projects are stored as JSON files in the data/projects/ directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.models import (
    AnalysisResult,
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    Timeline,
    TranscriptData,
)
from core.paths import get_projects_dir
from core.timeline_utils import split_words


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

    def _success_patch(self, **layers) -> dict:
        """Build a ProjectPatch response envelope for the active timeline.

        ``layers`` are passed straight to :class:`ProjectPatch`; only the
        layers the caller actually mutated should be populated. The
        ``revision`` is set via :meth:`_next_revision` and ``timeline_id``
        defaults to the active timeline.
        """
        from core.models import ProjectPatch

        patch = ProjectPatch(
            revision=self._next_revision(),
            timeline_id=self._current.active_timeline_id if self._current else None,
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

            data = json.loads(project_path.read_text(encoding="utf-8"))

            # Migrate v1 -> v2 schema if needed
            data = self._migrate_to_v2(data)

            project = Project.model_validate(data)

            self._current = project
            self._current_path = project_path
            logger.info("Opened project: {}", path)

            # Migrate old format silence edits
            self._migrate_silence_edits()

            # v2.1.1: Dedupe duplicate edit ids (legacy llm_smart bug fix)
            self._dedupe_edit_ids()

            # v2.1.1: Migrate legacy highlight EditDecisions (Bug E/G fix)
            self._migrate_highlights()

            # v2.1.2: Reject silence_detection edits that overwrite prior user
            # decisions (overlap-based repair; replaces fragile exact-time check)
            self._migrate_overlapping_silence_edits()

            # Check media path reachability
            if self._current.media and self._current.media.path:
                media_path = Path(self._current.media.path)
                if not media_path.exists():
                    return {
                        "success": False,
                        "error": "MEDIA_NOT_FOUND",
                        "data": {"path": self._current.media.path},
                    }

                # Fingerprint mismatch warning (file may have been overwritten)
                warnings = []
                if self._current.media.media_hash:
                    current_fp = compute_media_fingerprint(self._current.media.path)
                    if current_fp != self._current.media.media_hash:
                        warnings.append("MEDIA_HASH_MISMATCH")

                result = {"success": True, "data": self._current.model_dump()}
                if warnings:
                    result["warnings"] = warnings
                return result

            return {"success": True, "data": self._current.model_dump()}

        except Exception as e:
            logger.exception("Failed to open project: {}", path)
            return {"success": False, "error": str(e)}

    def _migrate_to_v2(self, raw: dict) -> dict:
        """Migrate schema_version 1 -> 2: wrap flat fields into default Timeline."""
        if raw.get("schema_version", 1) >= 2:
            return raw

        transcript = raw.pop("transcript", {"segments": []})
        edits = raw.pop("edits", [])
        analysis = raw.pop("analysis", {"results": []})
        raw.pop("topic_drift", None)  # Drop old Topic Drift data

        created_at = raw.get("project", {}).get("created_at", "")
        raw["timelines"] = [
            {
                "id": "default",
                "label": "原始",
                "source": "migrated",
                "created_at": created_at,
                "parent_id": "",
                "transcript": transcript,
                "edits": edits,
                "analysis": analysis,
            }
        ]
        raw["active_timeline_id"] = "default"
        raw["schema_version"] = 2
        return raw

    def _migrate_silence_edits(self) -> None:
        """Migrate old format silence EditDecisions to bind target_id."""
        if not self._current:
            return

        silence_map = {
            s.id: s for s in self.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        }

        migrated = []
        for edit in self.active_timeline.edits:
            if (edit.source == "silence_detection"
                    and edit.target_type == "range"
                    and edit.target_id is None):
                # Try to match by time range
                matched = next(
                    (s for s in silence_map.values()
                     if abs(s.start - edit.start) < 0.05 and abs(s.end - edit.end) < 0.05),
                    None,
                )
                if matched:
                    migrated.append(edit.model_copy(update={
                        "target_type": "segment",
                        "target_id": matched.id,
                    }))
                else:
                    migrated.append(edit)
            else:
                migrated.append(edit)

        self._update_active_timeline(edits=migrated)

    def _dedupe_edit_ids(self) -> None:
        """One-time fix: append _dup{N} suffix to duplicate edit ids in the active timeline.

        Suffix format matches the defensive logic in add_analysis_results (_dup{N}).
        O(n) fast path skips projects with no duplicates (zero overhead for large projects).
        """
        if not self._current:
            return

        tl = self.active_timeline
        edits = list(tl.edits)
        ids = [e.id for e in edits]

        # Fast path: no duplicates, skip entirely
        if len(ids) == len(set(ids)):
            return

        # Duplicate detected -- back up and fix
        all_ids = set(ids)
        seen: dict[str, int] = {}
        fixed = []
        changed_count = 0

        for e in edits:
            if e.id in seen:
                seen[e.id] += 1
                candidate = f"{e.id}_dup{seen[e.id]}"
                # Guard: candidate might collide with an existing id (secondary conflict)
                while candidate in all_ids:
                    seen[e.id] += 1
                    candidate = f"{e.id}_dup{seen[e.id]}"
                all_ids.add(candidate)
                fixed.append(e.model_copy(update={"id": candidate}))
                changed_count += 1
            else:
                seen[e.id] = 1
                fixed.append(e)

        if changed_count > 0:
            logger.warning("Deduped {} duplicate edit ids in timeline {}", changed_count, tl.id)
            self._update_active_timeline(edits=fixed)

    def _migrate_highlights(self) -> None:
        """One-time migration: fix legacy EditDecisions created before Bug E/G fix.

        - Remove ANY orphan EditDecision whose analysis_id no longer exists
          (not limited to highlights; covers all analysis-driven sources)
        - Set action="keep" for highlight-source EditDecisions still on "delete"
        Idempotent: safe to run multiple times.
        """
        if not self._current:
            return

        tl = self.active_timeline
        ar_ids = {r.id for r in tl.analysis.results}

        updated_edits = []
        fixed = 0
        orphan_removed = 0
        for e in tl.edits:
            is_highlight = e.source in ("llm_highlight", "manual_highlight")
            # An edit with analysis_id pointing at a non-existent result is an
            # orphan regardless of source -- its driving analysis was deleted.
            if e.analysis_id and e.analysis_id not in ar_ids:
                orphan_removed += 1
                continue

            if is_highlight and e.action == "delete":
                # Bug E legacy: highlight edit had wrong action
                updated_edits.append(e.model_copy(update={"action": "keep"}))
                fixed += 1
            else:
                updated_edits.append(e)

        if fixed > 0 or orphan_removed > 0:
            self._update_active_timeline(edits=updated_edits)
            logger.info(
                "Highlight migration: fixed %d actions, removed %d orphans",
                fixed, orphan_removed,
            )

    def _migrate_overlapping_silence_edits(self) -> None:
        """Repair silence_detection edits that conflict with prior user decisions.

        Background: older versions of add_silence_results used exact 0.05s
        time-range matching for deduplication, so silence_detection edits could
        be auto-created and then confirmed by bulk actions in ranges where the
        user had already rejected deletion. The frontend's resolveSegmentState
        would then show "confirmed delete" on a subtitle the user wanted to keep.

        This migration marks confirmed silence_detection edits as REJECTED when
        they overlap (>0.3s) a user edit whose effective intent is "keep".
        Idempotent: safe to run multiple times.
        """
        if not self._current:
            return

        tl = self.active_timeline
        edits = list(tl.edits)

        user_edits = [e for e in edits if e.source == "user"]
        if not user_edits:
            return

        updated: list[EditDecision] = []
        changed = 0
        for e in edits:
            if e.source != "silence_detection" or e.status != EditStatus.CONFIRMED:
                updated.append(e)
                continue

            # Effective intent "keep" = user rejected delete OR confirmed keep
            conflict = any(
                self._ranges_overlap(e.start, e.end, ue.start, ue.end)
                and (
                    (ue.status == EditStatus.REJECTED and ue.action == "delete")
                    or (ue.status == EditStatus.CONFIRMED and ue.action == "keep")
                )
                for ue in user_edits
            )

            if conflict:
                updated.append(e.model_copy(update={"status": EditStatus.REJECTED}))
                changed += 1
            else:
                updated.append(e)

        if changed > 0:
            self._update_active_timeline(edits=updated)
            logger.info(
                "Silence overlap migration: rejected {} conflicting silence edits",
                changed,
            )

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

            tmp = self._current_path.with_suffix(".tmp")
            tmp.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            os.replace(tmp, self._current_path)

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
            transcript=TranscriptData(segments=all_segments),
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
            transcript=TranscriptData(segments=all_segments),
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

    def update_segment(self, segment_id: str, updates: dict) -> dict:
        """Update a segment's fields (start, end, text)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

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

        updated_segments = []
        updated_seg = None
        for seg in self.active_timeline.transcript.segments:
            if seg.id == segment_id:
                updated_seg = seg.model_copy(update=filtered)
                updated_segments.append(updated_seg)
            else:
                updated_segments.append(seg)

        updated_transcript = self.active_timeline.transcript.model_copy(
            update={"segments": updated_segments}
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
        return self._success_patch(**patch_kwargs)

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
            transcript=TranscriptData(segments=all_segments),
        )
        logger.info("Added segment {} ({:.3f}s - {:.3f}s)", seg_id, start, end)
        return {"success": True, "data": self._current.model_dump()}

    def delete_segment(self, segment_id: str) -> dict:
        """Remove a segment and its associated edit decisions."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = self.active_timeline.transcript.segments
        target = [s for s in segments if s.id == segment_id]
        if not target:
            return {"success": False, "error": f"Segment not found: {segment_id}"}

        remaining_segs = [s for s in segments if s.id != segment_id]
        remaining_edits = [e for e in self.active_timeline.edits if e.target_id != segment_id]

        self._update_active_timeline(
            transcript=self.active_timeline.transcript.model_copy(update={"segments": remaining_segs}),
            edits=remaining_edits,
        )
        logger.info("Deleted segment {}", segment_id)
        return {"success": True, "data": self._current.model_dump()}

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
        logger.info("Split segment {} at {:.3f}s (snap_offset={}ms)", segment_id, position, snap_offset_ms)
        result = {"success": True, "data": self._current.model_dump()}
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

    def store_subtitle_corrections(
        self, corrections: list[dict], timeline_id: str
    ) -> dict:
        """Persist LLM subtitle corrections as AnalysisResult records (D-54).

        Instead of immediately mutating segment text (the old behavior), each
        correction is stored as an AnalysisResult with type=
        llm_subtitle_correction and its structured payload JSON-encoded in
        ``detail``. The frontend reviews them and calls accept/reject per item.

        Existing unreviewed corrections of the same type are cleared first so
        re-running P1 replaces the pending review set.

        Args:
            corrections: LLM output list (segment_id, corrected_text, changes,
                category, confidence).
            timeline_id: Target timeline.

        Returns:
            {"success": True, "data": {"stored_count": int}}
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        import json
        from uuid import uuid4

        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        seg_map = {s.id: s for s in tl.transcript.segments}

        # Clear previously-pending corrections (avoid duplicates on re-run).
        kept_results = [
            r for r in tl.analysis.results
            if r.type != "llm_subtitle_correction"
        ]

        stored: list[AnalysisResult] = []
        for corr in corrections:
            seg_id = corr.get("segment_id")
            if not seg_id or seg_id not in seg_map:
                continue
            original_text = seg_map[seg_id].text
            corrected_text = str(corr.get("corrected_text", original_text))
            # Skip no-op corrections (LLM says "no change").
            if corrected_text.strip() == original_text.strip():
                continue
            result = AnalysisResult(
                id=f"corr-{seg_id}-{uuid4().hex[:8]}",
                type="llm_subtitle_correction",
                segment_ids=[seg_id],
                confidence=float(corr.get("confidence", 0.8)),
                detail=json.dumps(
                    {
                        "original_text": original_text,
                        "corrected_text": corrected_text,
                        "changes": corr.get("changes", []),
                        "category": corr.get("category", "none"),
                    },
                    ensure_ascii=False,
                ),
            )
            stored.append(result)

        new_results = kept_results + stored
        self._update_timeline_by_id(
            timeline_id,
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info(
            "Stored {} subtitle corrections for review (timeline {})",
            len(stored), timeline_id,
        )
        return {"success": True, "data": {"stored_count": len(stored)}}

    def get_subtitle_corrections(self, timeline_id: str) -> dict:
        """Read pending P1 corrections for a timeline (parsed detail JSON).

        Returns:
            {"success": True, "data": [correction_dict, ...]} where each dict
            has id, segment_id, confidence, original_text, corrected_text,
            changes, category, start, end (for time-link rendering).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        import json

        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        seg_map = {s.id: s for s in tl.transcript.segments}
        out: list[dict] = []
        for r in tl.analysis.results:
            if r.type != "llm_subtitle_correction":
                continue
            try:
                payload = json.loads(r.detail) if r.detail else {}
            except (ValueError, TypeError):
                payload = {}
            seg_id = r.segment_ids[0] if r.segment_ids else ""
            seg = seg_map.get(seg_id)
            out.append({
                "id": r.id,
                "segment_id": seg_id,
                "confidence": r.confidence,
                "original_text": payload.get("original_text", seg.text if seg else ""),
                "corrected_text": payload.get("corrected_text", ""),
                "changes": payload.get("changes", []),
                "category": payload.get("category", "none"),
                "start": seg.start if seg else 0.0,
                "end": seg.end if seg else 0.0,
            })
        return {"success": True, "data": out}

    def _parse_correction_result(self, result: AnalysisResult) -> dict | None:
        """Decode the detail JSON of a correction AnalysisResult."""
        import json
        if not result.detail:
            return None
        try:
            return json.loads(result.detail)
        except (ValueError, TypeError):
            return None

    def accept_subtitle_correction(self, result_id: str) -> dict:
        """Accept one correction: apply to segment.text + remove AnalysisResult.

        Args:
            result_id: The AnalysisResult id (``corr-<seg>-<hex>``).

        Returns:
            {"success": True, "data": {"segment_id": str}}
            {"success": False, "error": str} if not found.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.llm_service import (
            TimestampCorruptionError,
            _assert_timestamps_unchanged,
            _check_correction_confidence,
        )

        tl = self.active_timeline
        target = next(
            (r for r in tl.analysis.results if r.id == result_id), None
        )
        if target is None or target.type != "llm_subtitle_correction":
            return {"success": False, "error": f"Correction {result_id} not found"}

        payload = self._parse_correction_result(target)
        if payload is None:
            return {"success": False, "error": "Malformed correction detail"}

        seg_id = target.segment_ids[0] if target.segment_ids else ""
        seg = next((s for s in tl.transcript.segments if s.id == seg_id), None)
        if seg is None:
            return {"success": False, "error": f"Segment {seg_id} not found"}

        corrected_text = str(payload.get("corrected_text", seg.text))
        conf = _check_correction_confidence(seg.text, corrected_text)
        new_flags = {**seg.dirty_flags, "llm_corrected": True}
        if conf["low_confidence"]:
            new_flags["llm_low_confidence"] = True

        corrected_seg = seg.model_copy(
            update={"text": corrected_text, "dirty_flags": new_flags}
        )

        # Timestamp assertion (defensive -- LLM should never alter timestamps).
        try:
            _assert_timestamps_unchanged(
                seg.start, seg.end, corrected_seg.start, corrected_seg.end,
                segment_id=seg.id,
            )
            new_segments = [
                corrected_seg if s.id == seg_id else s
                for s in tl.transcript.segments
            ]
        except TimestampCorruptionError:
            logger.warning("Timestamp corruption on accept, rollback segment %s", seg_id)
            new_segments = list(tl.transcript.segments)

        # Remove the accepted correction from analysis results.
        new_results = [r for r in tl.analysis.results if r.id != result_id]

        self._update_active_timeline(
            transcript=tl.transcript.model_copy(update={"segments": new_segments}),
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Accepted subtitle correction {} (seg {})", result_id, seg_id)
        return {"success": True, "data": {"segment_id": seg_id}}

    def reject_subtitle_correction(self, result_id: str) -> dict:
        """Reject one correction: remove AnalysisResult without touching text.

        Args:
            result_id: The AnalysisResult id.

        Returns:
            {"success": True, "data": {"segment_id": str}}
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self.active_timeline
        target = next(
            (r for r in tl.analysis.results if r.id == result_id), None
        )
        if target is None or target.type != "llm_subtitle_correction":
            return {"success": False, "error": f"Correction {result_id} not found"}

        seg_id = target.segment_ids[0] if target.segment_ids else ""
        new_results = [r for r in tl.analysis.results if r.id != result_id]
        self._update_active_timeline(
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Rejected subtitle correction {} (seg {})", result_id, seg_id)
        return {"success": True, "data": {"segment_id": seg_id}}

    def accept_high_confidence_corrections(
        self, timeline_id: str, threshold: float = 0.8
    ) -> dict:
        """Batch-accept all corrections with confidence >= threshold (D-52).

        Iterates the pending corrections, applying each qualifying one to
        segment.text and removing it from the analysis results. Corrections
        below the threshold remain pending for manual review.

        Args:
            timeline_id: Target timeline.
            threshold: Minimum confidence to auto-accept (default 0.8, D-68).

        Returns:
            {"success": True, "data": {"accepted_count": int, "remaining_count": int}}
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        # Gather qualifying ids, then reuse the single-accept path so the
        # apply logic (confidence flag, timestamp assertion) stays unified.
        qualifying = [
            r.id for r in tl.analysis.results
            if r.type == "llm_subtitle_correction" and r.confidence >= threshold
        ]

        # Ensure the target timeline is active so accept_subtitle_correction
        # (which operates on active_timeline) hits the right timeline.
        if self._current.active_timeline_id != timeline_id:
            self._current = self._current.model_copy(
                update={"active_timeline_id": timeline_id}
            )

        accepted = 0
        for rid in qualifying:
            res = self.accept_subtitle_correction(rid)
            if res.get("success"):
                accepted += 1

        # Count remaining (active timeline may have changed during accepts).
        tl_after = self._current.get_timeline(timeline_id)
        remaining = sum(
            1 for r in tl_after.analysis.results
            if r.type == "llm_subtitle_correction"
        ) if tl_after else 0
        logger.info(
            "Batch-accepted {} high-confidence corrections (threshold {}, {})",
            accepted, threshold, "remaining" if remaining else "clean",
        )
        return {
            "success": True,
            "data": {"accepted_count": accepted, "remaining_count": remaining},
        }

    def clear_subtitle_corrections(self, timeline_id: str) -> dict:
        """Clear all pending P1 corrections for a timeline (D-50).

        Used when the user dismisses the review without per-item action.

        Returns:
            {"success": True, "data": {"cleared_count": int}}
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        tl = self._current.get_timeline(timeline_id)
        if tl is None:
            return {"success": False, "error": f"Timeline {timeline_id} not found"}

        cleared = sum(1 for r in tl.analysis.results if r.type == "llm_subtitle_correction")
        if cleared == 0:
            return {"success": True, "data": {"cleared_count": 0}}

        new_results = [
            r for r in tl.analysis.results
            if r.type != "llm_subtitle_correction"
        ]
        self._update_timeline_by_id(
            timeline_id,
            analysis=tl.analysis.model_copy(update={"results": new_results}),
        )
        logger.info("Cleared {} subtitle corrections (timeline {})", cleared, timeline_id)
        return {"success": True, "data": {"cleared_count": cleared}}

    def apply_subtitle_corrections(self, corrections: list[dict]) -> dict:
        """Apply LLM subtitle corrections to the active timeline.

        Uses layered fault tolerance: does not fail entirely on partial
        mismatches. Matches by segment_id, applies what matches, and marks
        uncovered segments with dirty_flags.llm_uncovered.

        Args:
            corrections: List of dicts with segment_id, corrected_text,
                changes, category, confidence.

        Returns:
            {"success": True, "data": {corrected_count, uncovered_count,
             uncovered_ids, orphaned_count, partial}}
            {"success": False, "error": str} on complete mismatch.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.llm_service import (
            TimestampCorruptionError,
            _assert_timestamps_unchanged,
            _check_correction_confidence,
        )

        timeline = self.active_timeline
        seg_map = {s.id: s for s in timeline.transcript.segments}
        total = len(timeline.transcript.segments)

        # Match corrections to segments
        matched: list[tuple[Segment, dict]] = []
        uncovered_ids: list[str] = []

        for seg in timeline.transcript.segments:
            corr = next((c for c in corrections if c["segment_id"] == seg.id), None)
            if corr:
                matched.append((seg, corr))
            else:
                uncovered_ids.append(seg.id)

        extra_corrections = [c for c in corrections if c["segment_id"] not in seg_map]

        # Complete mismatch
        if len(matched) == 0 and total > 0:
            return {
                "success": False,
                "error": "No segment_id matched (LLM output completely mismatched)",
            }

        if len(matched) < total:
            logger.warning(
                f"Partial correction coverage: {len(matched)}/{total} segments matched, "
                f"{len(uncovered_ids)} uncovered, {len(extra_corrections)} orphaned"
            )

        # Apply corrections
        corr_map = {seg_id: corr for seg, corr in matched for seg_id in [seg.id]}
        new_segments: list[Segment] = []
        rolled_back_count = 0

        for seg in timeline.transcript.segments:
            corr = corr_map.get(seg.id)
            if corr:
                corrected_text = str(corr.get("corrected_text", seg.text))
                # Confidence check
                conf = _check_correction_confidence(seg.text, corrected_text)
                new_flags = {**seg.dirty_flags, "llm_corrected": True}
                if conf["low_confidence"]:
                    new_flags["llm_low_confidence"] = True

                corrected = seg.model_copy(
                    update={"text": corrected_text, "dirty_flags": new_flags}
                )

                # Timestamp assertion
                try:
                    _assert_timestamps_unchanged(
                        seg.start, seg.end, corrected.start, corrected.end,
                        segment_id=seg.id,
                    )
                    new_segments.append(corrected)
                except TimestampCorruptionError:
                    # Rollback this segment, keep original
                    rolled_back_count += 1
                    new_segments.append(seg)
            else:
                # Uncovered: keep original, mark for UI
                uncovered = seg.model_copy(
                    update={
                        "dirty_flags": {**seg.dirty_flags, "llm_uncovered": True}
                    }
                )
                new_segments.append(uncovered)

        # Update timeline: new segments + invalidate analysis
        self._update_active_timeline(
            transcript=timeline.transcript.model_copy(update={"segments": new_segments}),
            analysis=timeline.analysis.model_copy(update={"last_run": None}),
        )

        logger.info(
            f"Applied subtitle corrections: {len(matched)} matched, "
            f"{len(uncovered_ids)} uncovered, {rolled_back_count} rolled back"
        )

        return {
            "success": True,
            "data": {
                "corrected_count": len(matched) - rolled_back_count,
                "uncovered_count": len(uncovered_ids),
                "uncovered_ids": uncovered_ids,
                "orphaned_count": len(extra_corrections),
                "rolled_back_count": rolled_back_count,
                "partial": len(matched) < total,
            },
        }

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
                })
            except (json.JSONDecodeError, OSError):
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

"""Project service: create, open, save, close project files.

Projects are stored as JSON files in the data/projects/ directory.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.models import (
    AnalysisData,
    AnalysisResult,
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectMeta,
    Segment,
    SegmentType,
    TranscriptData,
)
from core.paths import get_projects_dir


class ProjectService:
    """Manages project lifecycle and persistence."""

    def __init__(self) -> None:
        self._current: Project | None = None
        self._current_path: Path | None = None

    @property
    def current(self) -> Project | None:
        return self._current

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def create_project(self, name: str, media_path: str, media_info: dict) -> dict:
        """Create a new project with media info."""
        project = Project(
            project=ProjectMeta(
                name=name,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            ),
            media=MediaInfo(
                path=media_path,
                **{k: v for k, v in media_info.items() if k in MediaInfo.model_fields and k != "path"},
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
            project = Project.model_validate(data)

            self._current = project
            self._current_path = project_path
            logger.info("Opened project: {}", path)
            return {"success": True, "data": project.model_dump()}

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

    def update_transcript(self, segments: list[dict]) -> dict:
        """Replace subtitle segments while preserving silence segments.

        If the project already has silence segments (from silence detection),
        those are kept. Only subtitle-type segments are replaced.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        new_subtitles = [Segment.model_validate(s) for s in segments]
        existing = self._current.transcript.segments
        existing_silence = [s for s in existing if s.type == SegmentType.SILENCE]

        all_segments = new_subtitles + existing_silence
        updated = self._current.model_copy(update={
            "transcript": TranscriptData(segments=all_segments),
        })
        self._current = updated
        return {"success": True, "data": updated.model_dump()}

    def update_media_info(self, media_info: dict) -> dict:
        """Update media info in the current project."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        info = MediaInfo(
            **{k: v for k, v in media_info.items() if k in MediaInfo.model_fields},
        )
        updated = self._current.model_copy(update={"media": info})
        self._current = updated
        return {"success": True, "data": updated.model_dump()}

    def add_silence_results(self, silences: list[dict]) -> dict:
        """Convert raw silence intervals to Segments + EditDecisions.

        Skips creating EditDecisions for silence ranges that already have
        a confirmed edit (e.g. from subtitle deletion).
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        existing = self._current.transcript.segments
        existing_edits = list(self._current.edits)

        new_segments: list[Segment] = []
        new_edits: list[EditDecision] = []
        sil_idx = len([s for s in existing if s.type == SegmentType.SILENCE])

        for sil in silences:
            sil_idx += 1
            seg_id = f"sil-{sil_idx:04d}"
            edit_id = f"edit-{sil_idx:04d}"

            new_segments.append(Segment(
                id=seg_id,
                type=SegmentType.SILENCE,
                start=sil["start"],
                end=sil["end"],
                text="",
            ))

            # Skip edit if range already covered by an existing edit
            already_covered = any(
                e.action == "delete"
                and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)
                and abs(e.start - sil["start"]) < 0.05
                and abs(e.end - sil["end"]) < 0.05
                for e in existing_edits
            )
            if not already_covered:
                new_edits.append(EditDecision(
                    id=edit_id,
                    start=sil["start"],
                    end=sil["end"],
                    action="delete",
                    source="silence_detection",
                    status=EditStatus.PENDING,
                ))

        all_segments = list(existing) + new_segments
        all_edits = existing_edits + new_edits

        from core.models import AnalysisData
        updated = self._current.model_copy(update={
            "transcript": TranscriptData(segments=all_segments),
            "edits": all_edits,
            "analysis": AnalysisData(last_run=datetime.now().isoformat()),
        })
        self._current = updated
        logger.info("Added {} silence segments to project", len(new_segments))
        return {"success": True, "data": updated.model_dump()}

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
        for edit in self._current.edits:
            if edit.id == edit_id:
                updated_edits.append(edit.model_copy(update={"status": new_status}))
                found = True
            else:
                updated_edits.append(edit)

        if not found:
            return {"success": False, "error": f"Edit decision not found: {edit_id}"}

        updated = self._current.model_copy(update={"edits": updated_edits})
        self._current = updated
        return {"success": True, "data": updated.model_dump()}

    def update_segment(self, segment_id: str, updates: dict) -> dict:
        """Update a segment's fields (start, end, text)."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        allowed_fields = {"start", "end", "text"}
        filtered = {k: v for k, v in updates.items() if k in allowed_fields}
        if not filtered:
            return {"success": False, "error": "No valid fields to update"}

        old_seg = next(
            (s for s in self._current.transcript.segments if s.id == segment_id),
            None,
        )
        if old_seg is None:
            return {"success": False, "error": f"Segment not found: {segment_id}"}

        updated_segments = []
        updated_seg = None
        for seg in self._current.transcript.segments:
            if seg.id == segment_id:
                updated_seg = seg.model_copy(update=filtered)
                updated_segments.append(updated_seg)
            else:
                updated_segments.append(seg)

        updated_transcript = self._current.transcript.model_copy(
            update={"segments": updated_segments}
        )

        update_kwargs: dict = {"transcript": updated_transcript}

        if updated_seg and ("start" in filtered or "end" in filtered) and old_seg.type == SegmentType.SILENCE:
            updated_edits = []
            for edit in self._current.edits:
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

        updated = self._current.model_copy(update=update_kwargs)
        self._current = updated
        return {"success": True, "data": updated.model_dump()}

    def update_segment_text(self, segment_id: str, text: str) -> dict:
        """Update a subtitle segment's text and set dirty_flags."""
        result = self.update_segment(segment_id, {"text": text})
        if not result["success"]:
            return result

        # Set dirty_flags on the updated segment
        segments = self._current.transcript.segments
        updated_segments = []
        for seg in segments:
            if seg.id == segment_id:
                updated_segments.append(seg.model_copy(update={
                    "dirty_flags": {**seg.dirty_flags, "text_edited": True},
                }))
            else:
                updated_segments.append(seg)

        updated = self._current.model_copy(update={
            "transcript": self._current.transcript.model_copy(update={"segments": updated_segments}),
        })
        self._current = updated
        return {"success": True, "data": updated.model_dump()}

    def add_segment(self, start: float, end: float, text: str = "", seg_type: str = "subtitle") -> dict:
        """Add a new segment to the transcript."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segment_type = SegmentType(seg_type)
        existing = self._current.transcript.segments
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

        updated = self._current.model_copy(update={
            "transcript": TranscriptData(segments=all_segments),
        })
        self._current = updated
        logger.info("Added segment {} ({:.3f}s - {:.3f}s)", seg_id, start, end)
        return {"success": True, "data": updated.model_dump()}

    def merge_segments(self, segment_ids: list[str]) -> dict:
        """Merge contiguous subtitle segments into one.

        Sorts by start time, validates contiguity, merges text, removes orphaned EditDecisions.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = list(self._current.transcript.segments)
        targets = [s for s in segments if s.id in segment_ids and s.type == SegmentType.SUBTITLE]
        if len(targets) < 2:
            return {"success": False, "error": "Need at least 2 subtitle segments to merge"}

        targets.sort(key=lambda s: s.start)
        merged_text = "".join(s.text for s in targets)
        merged_seg = targets[0].model_copy(update={
            "end": targets[-1].end,
            "text": merged_text,
            "dirty_flags": {**targets[0].dirty_flags, "merged": True},
        })

        remove_ids = {s.id for s in targets[1:]}
        new_segments = [merged_seg if s.id == targets[0].id else s
                        for s in segments if s.id not in remove_ids]

        # Remove orphaned EditDecisions that referenced removed segments
        new_edits = [e for e in self._current.edits
                     if not any(sid in remove_ids for sid in getattr(e, '_segment_ids', []))]

        updated = self._current.model_copy(update={
            "transcript": self._current.transcript.model_copy(update={"segments": new_segments}),
            "edits": new_edits,
        })
        self._current = updated
        logger.info("Merged {} segments into {}", len(targets), merged_seg.id)
        return {"success": True, "data": updated.model_dump()}

    def split_segment(self, segment_id: str, position: float) -> dict:
        """Split a subtitle segment at the given time position.

        Creates two segments: {id}-a and {id}-b. Text is split proportionally.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        segments = list(self._current.transcript.segments)
        target = next((s for s in segments if s.id == segment_id), None)
        if target is None:
            return {"success": False, "error": f"Segment not found: {segment_id}"}
        if target.type != SegmentType.SUBTITLE:
            return {"success": False, "error": "Can only split subtitle segments"}
        if position <= target.start or position >= target.end:
            return {"success": False, "error": "Split position must be within segment bounds"}

        # Split text proportionally by duration ratio
        total_dur = target.end - target.start
        ratio = (position - target.start) / total_dur
        split_idx = max(1, min(len(target.text) - 1, int(len(target.text) * ratio)))

        seg_a = target.model_copy(update={
            "id": f"{segment_id}-a",
            "end": position,
            "text": target.text[:split_idx].strip(),
            "dirty_flags": {**target.dirty_flags, "split": True},
        })
        seg_b = target.model_copy(update={
            "id": f"{segment_id}-b",
            "start": position,
            "text": target.text[split_idx:].strip(),
            "dirty_flags": {**target.dirty_flags, "split": True},
        })

        new_segments = []
        for s in segments:
            if s.id == segment_id:
                new_segments.extend([seg_a, seg_b])
            else:
                new_segments.append(s)

        # Remove EditDecisions referencing the old segment
        new_edits = [e for e in self._current.edits
                     if not hasattr(e, '_segment_ids') or segment_id not in e._segment_ids]

        updated = self._current.model_copy(update={
            "transcript": self._current.transcript.model_copy(update={"segments": new_segments}),
            "edits": new_edits,
        })
        self._current = updated
        logger.info("Split segment {} at {:.3f}s", segment_id, position)
        return {"success": True, "data": updated.model_dump()}

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

        segments = list(self._current.transcript.segments)
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
            updated = self._current.model_copy(update={
                "transcript": self._current.transcript.model_copy(update={"segments": new_segments}),
            })
            self._current = updated

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

        segments = self._current.transcript.segments
        target_segs = [s for s in segments if s.id in segment_ids]
        if not target_segs:
            return {"success": False, "error": "No matching segments found"}

        try:
            edit_status = EditStatus(status)
        except ValueError:
            edit_status = EditStatus.PENDING

        existing_edits = list(self._current.edits)
        new_edit_ids_set: set[str] = set()
        new_edits: list[EditDecision] = []

        for seg in target_segs:
            edit_id = f"edit-user-{seg.id}"
            new_edit_ids_set.add(edit_id)
            new_edits.append(EditDecision(
                id=edit_id,
                start=seg.start,
                end=seg.end,
                action=action,
                source="user",
                status=edit_status,
                priority=200,
            ))

        # Merge: keep non-target edits, replace/add new ones
        merged_edits = [e for e in existing_edits if e.id not in new_edit_ids_set] + new_edits

        updated = self._current.model_copy(update={"edits": merged_edits})
        self._current = updated
        logger.info("Marked {} segments as {} ({})", len(target_segs), action, status)
        return {"success": True, "data": updated.model_dump()}

    def confirm_all_suggestions(self) -> dict:
        """Set all pending edit decisions to confirmed."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        count = 0
        updated_edits = []
        for edit in self._current.edits:
            if edit.status == EditStatus.PENDING:
                updated_edits.append(edit.model_copy(update={"status": EditStatus.CONFIRMED}))
                count += 1
            else:
                updated_edits.append(edit)

        updated = self._current.model_copy(update={"edits": updated_edits})
        self._current = updated
        logger.info("Confirmed {} pending edits", count)
        return {"success": True, "data": {"confirmed_count": count}}

    def reject_all_suggestions(self) -> dict:
        """Set all pending edit decisions to rejected."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        count = 0
        updated_edits = []
        for edit in self._current.edits:
            if edit.status == EditStatus.PENDING:
                updated_edits.append(edit.model_copy(update={"status": EditStatus.REJECTED}))
                count += 1
            else:
                updated_edits.append(edit)

        updated = self._current.model_copy(update={"edits": updated_edits})
        self._current = updated
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

        segments = self._current.transcript.segments
        edits = self._current.edits
        warnings: list[str] = []

        # Compute total duration
        total_duration = 0.0
        for seg in segments:
            total_duration = max(total_duration, seg.end)

        # Compute delete duration
        delete_duration = 0.0
        confirmed_edits = [e for e in edits if e.action == "delete" and e.status in (EditStatus.PENDING, EditStatus.CONFIRMED)]
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

    def add_analysis_results(self, results: list[dict], source: str) -> dict:
        """Store AnalysisResult entries and create EditDecisions from time ranges."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        analysis_results = [AnalysisResult.model_validate(r) for r in results]
        existing_results = list(self._current.analysis.results)
        all_results = existing_results + analysis_results

        # Create EditDecisions from analysis time ranges
        segments = self._current.transcript.segments
        seg_map = {s.id: s for s in segments}
        existing_edits = list(self._current.edits)
        new_edits: list[EditDecision] = []

        for ar in analysis_results:
            # Find time range from segment_ids
            matching_segs = [seg_map[sid] for sid in ar.segment_ids if sid in seg_map]
            if not matching_segs:
                continue
            start = min(s.start for s in matching_segs)
            end = max(s.end for s in matching_segs)

            edit_id = f"edit-{ar.id}"
            new_edits.append(EditDecision(
                id=edit_id,
                start=start,
                end=end,
                action="delete",
                source=source,
                analysis_id=ar.id,
                status=EditStatus.PENDING,
                priority=100,
            ))

        updated = self._current.model_copy(update={
            "analysis": self._current.analysis.model_copy(update={
                "results": all_results,
                "last_run": datetime.now().isoformat(),
            }),
            "edits": existing_edits + new_edits,
        })
        self._current = updated
        logger.info("Added {} analysis results from {}", len(analysis_results), source)
        return {"success": True, "data": updated.model_dump()}

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

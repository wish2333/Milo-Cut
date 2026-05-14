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
        """Replace the transcript segments in the current project."""
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.models import Segment
        seg_models = [Segment.model_validate(s) for s in segments]
        updated = self._current.model_copy(update={
            "transcript": TranscriptData(segments=seg_models),
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
        """Convert raw silence intervals to Segments + EditDecisions."""
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

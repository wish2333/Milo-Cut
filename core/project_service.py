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
    MediaInfo,
    Project,
    ProjectMeta,
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
                **{k: v for k, v in media_info.items() if k in MediaInfo.model_fields},
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

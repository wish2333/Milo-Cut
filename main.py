"""Milo-Cut application entry point.

AI-powered video preprocessing tool for oral presentation videos.
"""

from __future__ import annotations

import sys
import os

from pywebvue import App, Bridge, expose

from core.config import load_settings
from core.events import LOG_LINE
from core.ffmpeg_service import detect_silence, probe_media
from core.logging import get_logger, setup_frontend_sink, setup_logging
from core.models import TaskType
from core.paths import migrate_if_needed
from core.project_service import ProjectService
from core.subtitle_service import parse_srt
from core.task_manager import TaskManager
from core.export_service import export_srt, export_video


class MiloCutApi(Bridge):
    """Bridge API exposed to the Vue frontend."""

    def __init__(self) -> None:
        super().__init__(debug=True)
        self._project = ProjectService()
        self._task_manager = TaskManager(self._emit)
        self._register_task_handlers()

    def _register_task_handlers(self) -> None:
        """Register handlers for each task type."""
        self._task_manager.register_handler(
            TaskType.SILENCE_DETECTION, self._handle_silence_detection
        )
        self._task_manager.register_handler(
            TaskType.EXPORT_VIDEO, self._handle_export_video
        )
        self._task_manager.register_handler(
            TaskType.EXPORT_SUBTITLE, self._handle_export_subtitle
        )

    def _handle_silence_detection(self, task, cancel_event):
        """Run silence detection on the project media and store results."""
        if self._project.current is None or self._project.current.media is None:
            raise ValueError("No media loaded")
        media_path = self._project.current.media.path
        settings = load_settings()
        result = detect_silence(
            media_path,
            threshold_db=settings.get("silence_threshold_db", -30.0),
            min_duration=settings.get("silence_min_duration", 0.5),
        )
        if not result["success"]:
            raise RuntimeError(result["error"])
        store_result = self._project.add_silence_results(result["data"])
        if not store_result["success"]:
            raise RuntimeError(store_result.get("error", "Failed to store silence results"))
        return {"project": store_result["data"]}

    def _handle_export_video(self, task, cancel_event):
        """Export cut video as a background task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")
        project = self._project.current
        segments_data = [s.model_dump() for s in project.transcript.segments]
        edits_data = [e.model_dump() for e in project.edits]
        media_path = project.media.path
        output_path = task.payload.get("output_path", "")
        if not output_path:
            base, ext = os.path.splitext(media_path)
            output_path = f"{base}_cut{ext}"

        def progress_cb(percent: float, message: str = "") -> None:
            self._task_manager._update_progress(task.id, percent, message)

        return export_video(
            media_path=media_path,
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )

    def _handle_export_subtitle(self, task, cancel_event):
        """Export synchronized SRT as a background task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")
        project = self._project.current
        segments_data = [s.model_dump() for s in project.transcript.segments]
        edits_data = [e.model_dump() for e in project.edits]
        output_path = task.payload.get("output_path", "")
        if not output_path:
            output_path = os.path.splitext(project.media.path)[0] + "_cut.srt"

        return export_srt(
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
        )

    # ================================================================
    # System
    # ================================================================

    @expose
    def get_app_info(self) -> dict:
        return {
            "success": True,
            "data": {
                "name": "Milo-Cut",
                "version": "0.1.0",
                "python": sys.version,
                "platform": sys.platform,
            },
        }

    @expose
    def select_files(self) -> dict:
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("Video files (*.mp4;*.mkv;*.avi;*.mov;*.webm)", "All files (*.*)"),
        )
        if result:
            return {"success": True, "data": [str(p) for p in result]}
        return {"success": True, "data": []}

    @expose
    def select_file(self) -> dict:
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("SRT files (*.srt)", "All files (*.*)"),
        )
        if result:
            return {"success": True, "data": str(result[0])}
        return {"success": True, "data": None}

    @expose
    def open_folder(self, path: str) -> dict:
        import webview
        webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG, directory=path)
        return {"success": True}

    # ================================================================
    # Project
    # ================================================================

    @expose
    def create_project(self, name: str, media_path: str) -> dict:
        probe = probe_media(media_path)
        if not probe["success"]:
            return probe
        return self._project.create_project(name, media_path, probe["data"])

    @expose
    def open_project(self, path: str) -> dict:
        return self._project.open_project(path)

    @expose
    def save_project(self) -> dict:
        return self._project.save_project()

    @expose
    def close_project(self) -> dict:
        return self._project.close_project()

    # ================================================================
    # Subtitle
    # ================================================================

    @expose
    def import_srt(self, file_path: str) -> dict:
        result = parse_srt(file_path)
        if not result["success"]:
            return result
        return self._project.update_transcript(result["data"])

    # ================================================================
    # FFmpeg
    # ================================================================

    @expose
    def probe_media(self, file_path: str) -> dict:
        return probe_media(file_path)

    @expose
    def detect_silence(self) -> dict:
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        media = self._project.current.media
        if media is None:
            return {"success": False, "error": "No media in project"}
        settings = load_settings()
        return detect_silence(
            media.path,
            threshold_db=settings.get("silence_threshold_db", -30.0),
            min_duration=settings.get("silence_min_duration", 0.5),
        )

    # ================================================================
    # Tasks
    # ================================================================

    @expose
    def create_task(self, task_type: str, payload: dict | None = None) -> dict:
        return self._task_manager.create_task(task_type, payload)

    @expose
    def start_task(self, task_id: str) -> dict:
        return self._task_manager.start_task(task_id)

    @expose
    def cancel_task(self, task_id: str) -> dict:
        return self._task_manager.cancel_task(task_id)

    @expose
    def get_task(self, task_id: str) -> dict:
        return self._task_manager.get_task(task_id)

    @expose
    def list_tasks(self) -> dict:
        return self._task_manager.list_tasks()

    # ================================================================
    # Project State
    # ================================================================

    @expose
    def get_project(self) -> dict:
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        return {"success": True, "data": self._project.current.model_dump()}

    @expose
    def update_edit_decision(self, edit_id: str, status: str) -> dict:
        return self._project.update_edit_decision(edit_id, status)

    @expose
    def update_segment(self, segment_id: str, updates: dict) -> dict:
        return self._project.update_segment(segment_id, updates)

    @expose
    def select_export_path(self, default_name: str) -> dict:
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=("Video files (*.mp4)", "All files (*.*)"),
        )
        if result:
            return {"success": True, "data": str(result)}
        return {"success": True, "data": None}


if __name__ == "__main__":
    migrate_if_needed()
    setup_logging()

    api = MiloCutApi()
    setup_frontend_sink(api._emit)

    logger = get_logger()
    logger.info("Milo-Cut starting...")

    app = App(
        api,
        title="Milo-Cut",
        width=1280,
        height=800,
        min_size=(1024, 700),
        frontend_dir="frontend_dist",
    )
    app.run(debug=True)

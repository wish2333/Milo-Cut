"""Milo-Cut application entry point.

AI-powered video preprocessing tool for oral presentation videos.
"""

from __future__ import annotations

import sys
import os
import pathlib
from pathlib import Path
import subprocess

from pywebvue import App, Bridge, expose

from core.analysis_service import detect_errors, detect_fillers, run_full_analysis
from core.config import load_settings
from core.events import EDIT_SUMMARY_UPDATED, LOG_LINE
from core.ffmpeg_service import detect_silence, generate_waveform, probe_media
from core.logging import get_logger, setup_frontend_sink, setup_logging
from core.media_server import MediaServer
from core.models import TaskType
from core.paths import migrate_if_needed
from core.project_service import ProjectService
from core.subtitle_service import parse_srt
from core.task_manager import TaskManager
from core.export_service import export_audio, export_srt, export_video


class MiloCutApi(Bridge):
    """Bridge API exposed to the Vue frontend."""

    def __init__(self) -> None:
        super().__init__(debug=True)
        self._project = ProjectService()
        self._task_manager = TaskManager(self._emit)
        self._media_server = MediaServer()
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
        self._task_manager.register_handler(
            TaskType.EXPORT_AUDIO, self._handle_export_audio
        )
        self._task_manager.register_handler(
            TaskType.FILLER_DETECTION, self._handle_filler_detection
        )
        self._task_manager.register_handler(
            TaskType.ERROR_DETECTION, self._handle_error_detection
        )
        self._task_manager.register_handler(
            TaskType.FULL_ANALYSIS, self._handle_full_analysis
        )
        self._task_manager.register_handler(
            TaskType.WAVEFORM_GENERATION, self._handle_waveform_generation
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
        margin = settings.get("silence_margin", 0.0)
        subtitle_padding = settings.get("silence_subtitle_padding", 0.0)
        store_result = self._project.add_silence_results(
            result["data"], margin=margin, subtitle_padding=subtitle_padding,
        )
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

        # Read encoding settings from project settings
        settings = load_settings()
        video_codec = settings.get("export_video_codec", "libx264")
        audio_codec = settings.get("export_audio_codec", "aac")
        audio_bitrate = settings.get("export_audio_bitrate", "192k")
        preset = settings.get("export_preset", "fast")
        crf = int(settings.get("export_crf", 23))
        resolution = settings.get("export_resolution", "original")

        def progress_cb(percent: float, message: str = "") -> None:
            self._task_manager._update_progress(task.id, percent, message)

        return export_video(
            media_path=media_path,
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
            media_info=project.media.model_dump() if project.media else None,
            video_codec=video_codec,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            preset=preset,
            crf=crf,
            resolution=resolution,
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

        media_duration = project.media.duration if project.media else 0.0
        return export_srt(
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
            media_duration=media_duration,
        )

    def _handle_export_audio(self, task, cancel_event):
        """Export cut audio as a background task."""
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
            base, _ = os.path.splitext(media_path)
            output_path = f"{base}_cut.m4a"

        def progress_cb(percent: float, message: str = "") -> None:
            self._task_manager._update_progress(task.id, percent, message)

        return export_audio(
            media_path=media_path,
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
            media_info=project.media.model_dump() if project.media else None,
            progress_callback=progress_cb,
            cancel_event=cancel_event,
        )

    def _handle_filler_detection(self, task, cancel_event):
        """Run filler word detection and store results."""
        if self._project.current is None:
            raise ValueError("No project open")
        settings = load_settings()
        segments = list(self._project.current.transcript.segments)
        results = detect_fillers(segments, settings.get("filler_words", []))
        results_dicts = [r.model_dump() for r in results]
        store = self._project.add_analysis_results(results_dicts, source="filler_detection")
        if not store["success"]:
            raise RuntimeError(store.get("error", "Failed to store analysis results"))
        return {"project": store["data"], "results": results_dicts}

    def _handle_error_detection(self, task, cancel_event):
        """Run error trigger detection and store results."""
        if self._project.current is None:
            raise ValueError("No project open")
        settings = load_settings()
        segments = list(self._project.current.transcript.segments)
        results = detect_errors(segments, settings.get("error_trigger_words", []))
        results_dicts = [r.model_dump() for r in results]
        store = self._project.add_analysis_results(results_dicts, source="error_detection")
        if not store["success"]:
            raise RuntimeError(store.get("error", "Failed to store analysis results"))
        return {"project": store["data"], "results": results_dicts}

    def _handle_full_analysis(self, task, cancel_event):
        """Run full analysis (filler + error) and store results."""
        if self._project.current is None:
            raise ValueError("No project open")
        settings = load_settings()
        segments = list(self._project.current.transcript.segments)
        results = run_full_analysis(segments, settings)
        results_dicts = [r.model_dump() for r in results]
        store = self._project.add_analysis_results(results_dicts, source="full_analysis")
        if not store["success"]:
            raise RuntimeError(store.get("error", "Failed to store analysis results"))
        return {"project": store["data"], "results": results_dicts}

    def _handle_waveform_generation(self, task, cancel_event):
        """Generate waveform peak data for the project media."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")

        media = self._project.current.media
        media_path = media.path
        duration = media.duration

        # Output path: next to project file
        from core.paths import get_projects_dir
        waveform_path = str(get_projects_dir() / f"{media.media_hash}.waveform.json")

        def progress_cb(percent: float, message: str = "") -> None:
            self._task_manager._update_progress(task.id, percent, message)

        progress_cb(10.0, "Extracting audio peaks...")
        result = generate_waveform(media_path, duration, waveform_path)
        if not result["success"]:
            raise RuntimeError(result["error"])

        progress_cb(90.0, "Updating project...")
        # Update media info with waveform path
        self._project.update_media_waveform(waveform_path)
        # Make waveform available via HTTP
        self._media_server.set_waveform(waveform_path)

        progress_cb(100.0, "Waveform generated")
        return {"project": self._project.current.model_dump() if self._project.current else None}

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
            webview.FileDialog.OPEN,
            file_types=(
                "Media files (*.mp4;*.mkv;*.avi;*.mov;*.webm;*.mp3;*.wav;*.aac;*.flac;*.ogg;*.m4a)",
                "Video files (*.mp4;*.mkv;*.avi;*.mov;*.webm)",
                "Audio files (*.mp3;*.wav;*.aac;*.flac;*.ogg;*.m4a)",
                "All files (*.*)",
            ),
        )
        if result:
            return {"success": True, "data": [str(p) for p in result]}
        return {"success": True, "data": []}

    @expose
    def select_file(self) -> dict:
        import webview
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("SRT files (*.srt)", "All files (*.*)"),
        )
        if result:
            return {"success": True, "data": str(result[0])}
        return {"success": True, "data": None}

    @expose
    def open_folder(self, path: str) -> dict:
        import webview
        webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER, directory=path)
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
        self._media_server.stop()
        return self._project.close_project()

    # ================================================================
    # Subtitle
    # ================================================================

    @expose
    def import_srt(self, file_path: str) -> dict:
        from core.subtitle_service import validate_srt

        # Validate SRT before importing
        media = self._project.current.media if self._project.current else None
        duration = media.duration if media else 0.0
        validation = validate_srt(file_path, video_duration=duration)

        result = parse_srt(file_path)
        if not result["success"]:
            return result

        update_result = self._project.update_transcript(result["data"])

        # Include validation warnings in the response
        if update_result["success"] and validation.get("success"):
            vdata = validation.get("data", {})
            if vdata.get("error_count", 0) > 0 or vdata.get("warning_count", 0) > 0:
                update_result["warnings"] = vdata.get("issues", [])

        return update_result

    # ================================================================
    # FFmpeg
    # ================================================================

    @expose
    def probe_media(self, file_path: str) -> dict:
        return probe_media(file_path)

    @expose
    def get_video_url(self, file_path: str) -> dict:
        """Start a local HTTP server and return the streaming URL."""
        result = self._media_server.start(file_path)
        # If project already has a waveform, make it available via HTTP
        if result.get("success") and self._project.current and self._project.current.media:
            waveform_path = self._project.current.media.waveform_path
            if waveform_path and Path(waveform_path).exists():
                self._media_server.set_waveform(waveform_path)
        return result

    @expose
    def get_waveform_url(self) -> dict:
        """Return the HTTP URL for the waveform JSON, or error if not available."""
        if not self._media_server.is_running:
            return {"success": False, "error": "Media server not running"}
        if not self._media_server._waveform_path:
            return {"success": False, "error": "Waveform not available"}
        return {"success": True, "data": {"url": f"http://127.0.0.1:{self._media_server.port}/waveform"}}

    @expose
    def stop_media_server(self) -> dict:
        """Stop the local media server."""
        self._media_server.stop()
        return {"success": True}

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
    def update_segment_text(self, segment_id: str, text: str) -> dict:
        return self._project.update_segment_text(segment_id, text)

    @expose
    def merge_segments(self, segment_ids: list[str]) -> dict:
        return self._project.merge_segments(segment_ids)

    @expose
    def split_segment(self, segment_id: str, position: float) -> dict:
        return self._project.split_segment(segment_id, position)

    @expose
    def add_segment(self, start: float, end: float, text: str = "", seg_type: str = "subtitle") -> dict:
        return self._project.add_segment(start, end, text, seg_type)

    @expose
    def delete_segment(self, segment_id: str) -> dict:
        return self._project.delete_segment(segment_id)

    @expose
    def delete_silence_segments(self) -> dict:
        return self._project.delete_silence_segments()

    @expose
    def delete_subtitle_trim_edits(self) -> dict:
        return self._project.delete_subtitle_trim_edits()

    @expose
    def search_replace(self, query: str, replacement: str, scope: str = "all") -> dict:
        return self._project.search_replace(query, replacement, scope)

    @expose
    def mark_segments(self, segment_ids: list[str], action: str, status: str = "pending") -> dict:
        return self._project.mark_segments(segment_ids, action, status)

    @expose
    def confirm_all_suggestions(self) -> dict:
        result = self._project.confirm_all_suggestions()
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
        return result

    @expose
    def reject_all_suggestions(self) -> dict:
        result = self._project.reject_all_suggestions()
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
        return result

    @expose
    def generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict:
        result = self._project.generate_subtitle_keep_ranges(padding)
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
        return result

    @expose
    def get_edit_summary(self) -> dict:
        return self._project.get_edit_summary()

    @expose
    def validate_srt(self, file_path: str) -> dict:
        from core.subtitle_service import validate_srt
        media = self._project.current.media if self._project.current else None
        duration = media.duration if media else 0.0
        return validate_srt(file_path, video_duration=duration)

    @expose
    def get_recent_projects(self) -> dict:
        return self._project.get_recent_projects()

    @expose
    def get_settings(self) -> dict:
        return self._project.get_settings()

    @expose
    def update_settings(self, updates: dict) -> dict:
        return self._project.update_settings(updates)

    @expose
    def select_export_path(self, default_name: str, file_types: list[str] | None = None) -> dict:
        import webview
        if file_types is None:
            file_types = ["All files (*.*)"]
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=default_name,
            file_types=tuple(file_types),
        )
        if result:
            # pywebview SAVE dialog returns a string on macOS/Linux
            # but a tuple/list on Windows
            if isinstance(result, (tuple, list)):
                path = str(result[0]) if result else None
            else:
                path = str(result)
            if path:
                return {"success": True, "data": path}
        return {"success": True, "data": None}

    @expose
    def detect_gpu(self) -> dict:
        """Detect GPU availability and return supported hardware encoders."""
        encoders: list[str] = []
        gpu_name = ""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0]
                encoders.extend(["h264_nvenc", "hevc_nvenc", "av1_nvenc"])
        except FileNotFoundError:
            pass

        # libsvtav1 is available on all platforms except some macOS builds
        if sys.platform != "darwin":
            encoders.append("libsvtav1")

        return {
            "success": True,
            "data": {
                "nvidia": bool(gpu_name),
                "gpu_name": gpu_name,
                "encoders": encoders,
            },
        }

    @expose
    def export_edl(self, output_path: str) -> dict:
        """Export EDL (CMX3600) file."""
        from core.export_timeline import export_edl as _export_edl
        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.transcript.segments]
        edits = [e.model_dump() for e in project.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_edl(segments, edits, media_info, output_path)

    @expose
    def export_xmeml_premiere(self, output_path: str) -> dict:
        """Export xmeml for Premiere Pro."""
        from core.export_timeline import export_xmeml_premiere as _export_xmeml_premiere
        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.transcript.segments]
        edits = [e.model_dump() for e in project.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_xmeml_premiere(segments, edits, media_info, output_path)


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

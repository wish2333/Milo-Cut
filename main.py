"""Milo-Cut application entry point.

AI-powered video preprocessing tool for oral presentation videos.
"""

from __future__ import annotations

import sys
import os
import pathlib
from pathlib import Path
import subprocess
import shutil

from pywebvue import App, Bridge, expose

_SUBPROCESS_KWARGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

from core.analysis_service import detect_errors, detect_fillers, run_full_analysis
from core.config import load_settings
from core.events import EDIT_SUMMARY_UPDATED, ENCODER_FALLBACK, LOG_LINE
from core.ffmpeg_service import detect_silence, generate_waveform, probe_media
from core.logging import get_logger, setup_frontend_sink, setup_logging
from core.media_server import MediaServer
from core.models import TaskType
from core.paths import migrate_if_needed
from core.plugin_manager import PluginManager, PLUGIN_REGISTRY
from core.project_service import ProjectService
from core.subtitle_service import parse_srt
from core.task_manager import TaskManager
from core.export_service import export_audio, export_srt, export_video, export_vtt
from core.ffmpeg_presets import ENCODER_METADATA, get_fallback_codec
from core.ffmpeg_service import _find_ffmpeg

logger = get_logger()


def _get_version() -> str:
    """Get app version with packaging fallback."""
    # Method 1: importlib.metadata (dev env / pip install)
    try:
        from importlib.metadata import version
        return version("milo-cut")
    except Exception:
        pass
    # Method 2: read pyproject.toml (PyInstaller/Nuitka packaging fallback)
    try:
        import tomllib
        with open(Path(__file__).parent / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        pass
    # Method 3: final fallback
    return "unknown"


class MiloCutApi(Bridge):
    """Bridge API exposed to the Vue frontend."""

    def __init__(self) -> None:
        super().__init__(debug=True)
        self._project = ProjectService()
        self._task_manager = TaskManager(self._emit)
        self._media_server = MediaServer()
        self._plugin_manager = PluginManager()
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
            TaskType.EXPORT_VTT, self._handle_export_vtt
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
        self._task_manager.register_handler(
            TaskType.PLUGIN_INSTALL, self._handle_plugin_install
        )
        self._task_manager.register_handler(
            TaskType.MODEL_DOWNLOAD, self._handle_model_download
        )
        self._task_manager.register_handler(
            TaskType.TRANSCRIPTION, self._handle_transcription
        )

    def _handle_silence_detection(self, task, cancel_event, progress_cb):
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

    def _handle_export_video(self, task, cancel_event, progress_cb):
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
        preset = settings.get("export_preset", "medium")
        crf = int(settings.get("export_crf", 23))
        resolution = settings.get("export_resolution", "original")
        fade_dur = float(settings.get("export_ffmpeg_fade_duration", 0.0))
        fade_mode = str(settings.get("export_ffmpeg_fade_mode", "crossfade"))

        # Check encoder availability and fallback if needed
        ffmpeg = _find_ffmpeg()
        original_codec = video_codec
        video_codec, fallback_msg = get_fallback_codec(ffmpeg, video_codec)
        if fallback_msg:
            logger.warning(fallback_msg)
            self._emit(ENCODER_FALLBACK, {
                "requested": original_codec,
                "fallback": video_codec,
                "message": fallback_msg,
            })

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
            fade_duration=fade_dur,
            fade_mode=fade_mode,
        )

    def _handle_export_subtitle(self, task, cancel_event, progress_cb):
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

    def _handle_export_vtt(self, task, cancel_event, progress_cb):
        """Export WebVTT as a background task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")
        project = self._project.current
        segments_data = [s.model_dump() for s in project.transcript.segments]
        edits_data = [e.model_dump() for e in project.edits]
        output_path = task.payload.get("output_path", "")
        if not output_path:
            output_path = os.path.splitext(project.media.path)[0] + "_cut.vtt"

        media_duration = project.media.duration if project.media else 0.0
        return export_vtt(
            segments=segments_data,
            edits=edits_data,
            output_path=output_path,
            media_duration=media_duration,
        )

    def _handle_export_audio(self, task, cancel_event, progress_cb):
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

        settings = load_settings()
        fade_dur = float(settings.get("export_ffmpeg_fade_duration", 0.0))
        fade_mode = str(settings.get("export_ffmpeg_fade_mode", "crossfade"))

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
            fade_duration=fade_dur,
            fade_mode=fade_mode,
        )

    def _handle_filler_detection(self, task, cancel_event, progress_cb):
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

    def _handle_error_detection(self, task, cancel_event, progress_cb):
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

    def _handle_full_analysis(self, task, cancel_event, progress_cb):
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

    def _handle_waveform_generation(self, task, cancel_event, progress_cb):
        """Generate waveform peak data for the project media."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")

        media = self._project.current.media
        media_path = media.path
        duration = media.duration

        # Output path: per-project waveform file
        if self._project._current_path:
            waveform_path = str(self._project._current_path.parent / "waveform.json")
        else:
            from core.paths import get_data_dir, get_projects_dir
            name = self._project.current.project.name
            waveform_path = str(get_projects_dir() / name / "waveform.json")

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
        # Persist waveform_path to disk so it survives restart
        try:
            self._project.save_project()
        except Exception:
            logger.exception("Failed to auto-save project after waveform generation")

        progress_cb(100.0, "Waveform generated")
        return {"project": self._project.current.model_dump() if self._project.current else None}

    def _handle_plugin_install(self, task, cancel_event, progress_cb):
        """Install an ASR plugin and optionally download its model."""
        plugin_id = task.payload.get("plugin_id", "")
        model_id = task.payload.get("model_id", "")
        mirror = task.payload.get("mirror", "official")
        no_cache = task.payload.get("no_cache", False)

        if not plugin_id:
            raise ValueError("plugin_id is required")

        # Install plugin
        self._plugin_manager.install_plugin(plugin_id, progress_cb=progress_cb, mirror=mirror, no_cache=no_cache)

        # Optionally download model
        if model_id:
            progress_cb(50.0, f"Downloading model {model_id}...")
            self._plugin_manager.ensure_model(model_id, progress_cb=progress_cb, mirror=None)

        return {
            "plugin_id": plugin_id,
            "model_id": model_id,
            "status": "installed",
        }

    def _handle_model_download(self, task, cancel_event, progress_cb):
        """Download a model via the task system."""
        model_id = task.payload.get("model_id", "")
        mirror = task.payload.get("mirror", None)

        if not model_id:
            raise ValueError("model_id is required")

        self._plugin_manager.ensure_model(model_id, progress_cb=progress_cb, mirror=mirror)

        return {
            "model_id": model_id,
            "status": "downloaded",
        }

    def _handle_transcription(self, task, cancel_event, progress_cb):
        """Run ASR transcription as a background task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")

        media_path = self._project.current.media.path
        settings = load_settings()

        engine = task.payload.get("engine", settings.get("asr_engine", "faster-whisper"))
        language = task.payload.get("language", settings.get("asr_language", "zh"))
        device = task.payload.get("device", settings.get("asr_device", "cpu"))

        if engine == "faster-whisper":
            from core.asr_service import transcribe_with_whisper
            from core.ffmpeg_service import _find_ffmpeg

            model_size = task.payload.get("model_size", settings.get("asr_model_size", "large-v3-turbo"))
            compute_type = task.payload.get("compute_type", settings.get("whisper_compute_type", "int8_float16"))
            vad_filter = task.payload.get("vad_filter", settings.get("asr_vad_filter", True))
            vad_threshold = settings.get("whisper_vad_threshold", 0.5)
            vad_min_silence_ms = settings.get("whisper_vad_min_silence_ms", 500)
            ffmpeg = _find_ffmpeg()

            result = transcribe_with_whisper(
                plugin_manager=self._plugin_manager,
                media_path=media_path,
                ffmpeg_path=ffmpeg,
                model_size=model_size,
                language=language,
                device=device,
                compute_type=compute_type,
                vad_filter=vad_filter,
                vad_threshold=vad_threshold,
                vad_min_silence_ms=vad_min_silence_ms,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
            )
        elif engine == "qwen3-asr":
            from core.asr_service import transcribe_with_qwen

            asr_model_size = task.payload.get("asr_model_size", settings.get("asr_model_size", "0.6B"))
            aligner_model_size = task.payload.get("aligner_model_size", settings.get("asr_aligner_model_size", "0.6B"))
            compute_type = settings.get("qwen_compute_type", "bfloat16")

            result = transcribe_with_qwen(
                plugin_manager=self._plugin_manager,
                media_path=media_path,
                asr_model_size=asr_model_size,
                aligner_model_size=aligner_model_size,
                language=language,
                device=device,
                compute_type=compute_type,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
            )
        else:
            raise ValueError(f"Unsupported ASR engine: {engine}")

        if not result["success"]:
            raise RuntimeError(result["error"])

        # Update project transcript with ASR results
        transcript_data = {
            "engine": engine,
            "language": result["data"].get("language", language),
            "segments": result["data"].get("segments", []),
        }
        update_result = self._project.update_transcript(transcript_data["segments"])
        if not update_result["success"]:
            raise RuntimeError(update_result.get("error", "Failed to update transcript"))

        # Auto-save SRT to project directory
        srt_path = None
        try:
            from core.export_service import export_srt
            from core.paths import get_data_dir
            from datetime import datetime
            project_name = self._project.current.project.name if self._project.current.project else "transcript"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            srt_filename = f"{project_name}_{timestamp}.srt"
            srt_dir = Path(get_data_dir()) / "transcripts"
            srt_dir.mkdir(parents=True, exist_ok=True)
            srt_path = str(srt_dir / srt_filename)

            segments_for_export = []
            for seg in result["data"].get("segments", []):
                segments_for_export.append({
                    "id": seg.get("id", ""),
                    "start": seg.get("start", 0),
                    "end": seg.get("end", 0),
                    "text": seg.get("text", ""),
                    "type": "subtitle",
                })

            srt_result = export_srt(
                segments=segments_for_export,
                edits=[],
                output_path=srt_path,
                media_duration=self._project.current.media.duration if self._project.current.media else 0,
            )
            if srt_result.get("success"):
                logger.info("Auto-saved transcription SRT to {}", srt_path)
            else:
                logger.warning("Failed to auto-save SRT: {}", srt_result.get("error"))
                srt_path = None
        except Exception as e:
            logger.warning("Failed to auto-save SRT: {}", e)
            srt_path = None

        # Import the auto-saved SRT back into the project
        if srt_path:
            try:
                self.import_srt(srt_path)
            except Exception as e:
                logger.warning("Failed to import auto-saved SRT: {}", e)

        return {
            "project": update_result["data"],
            "segment_count": len(result["data"].get("segments", [])),
            "word_count": result["data"].get("word_count", 0),
            "srt_path": srt_path,
        }

    # ================================================================
    # System
    # ================================================================

    @expose
    def get_app_info(self) -> dict:
        return {
            "success": True,
            "data": {
                "name": "Milo-Cut",
                "version": _get_version(),
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
                "Media files (*.mp4;*.mkv;*.avi;*.mov;*.webm;*.mp3;*.wav;*.aac;*.flac;*.ogg;*.m4a;*.json)",
                "Video files (*.mp4;*.mkv;*.avi;*.mov;*.webm)",
                "Audio files (*.mp3;*.wav;*.aac;*.flac;*.ogg;*.m4a)",
                "Project files (*.json)",
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

    @expose
    def relink_media(self, new_path: str) -> dict:
        return self._project.relink_media(new_path)

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
    def regenerate_waveform(self) -> dict:
        """Clear cached waveform and trigger regeneration."""
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        if self._project.current.media is None:
            return {"success": False, "error": "No media in project"}

        # Clear existing waveform state so task can re-generate
        self._project.update_media_waveform("")
        self._media_server._waveform_path = ""

        task = self._task_manager.create_task("waveform_generation")
        self._task_manager.start_task(task["data"]["id"])
        return {"success": True, "data": {"task_id": task["data"]["id"]}}

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
    def clear_subtitles(self) -> dict:
        return self._project.clear_subtitles()

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

    # ================================================================
    # Plugin Management
    # ================================================================

    @expose
    def list_plugins(self) -> dict:
        """Return all registered plugins with their installation status."""
        return {"success": True, "data": self._plugin_manager.list_plugins()}

    @expose
    def install_plugin(self, plugin_id: str, model_id: str = "", mirror: str = "official", no_cache: bool = False) -> dict:
        """Start a background task to install a plugin and optionally download its model."""
        if plugin_id not in PLUGIN_REGISTRY:
            return {"success": False, "error": f"Unknown plugin: {plugin_id}"}
        task = self._task_manager.create_task(
            "plugin_install",
            {"plugin_id": plugin_id, "model_id": model_id, "mirror": mirror, "no_cache": no_cache},
        )
        if not task["success"]:
            return task
        self._task_manager.start_task(task["data"]["id"])
        return {"success": True, "data": {"task_id": task["data"]["id"]}}

    @expose
    def uninstall_plugin(self, plugin_id: str) -> dict:
        """Uninstall a plugin by removing its venv and registry entry."""
        try:
            self._plugin_manager.uninstall_plugin(plugin_id)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def list_models(self) -> dict:
        """Return all registered models with their download status."""
        return {"success": True, "data": self._plugin_manager.list_models()}

    @expose
    def download_model(self, model_id: str, mirror: str | None = None) -> dict:
        """Download a model. Returns immediately; use task progress for updates."""
        try:
            task = self._task_manager.create_task(
                "model_download", {"model_id": model_id, "mirror": mirror}
            )
            if not task["success"]:
                return task
            self._task_manager.start_task(task["data"]["id"])
            return {"success": True, "data": {"task_id": task["data"]["id"]}}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def list_model_mirrors(self) -> dict:
        """Return available model download mirrors."""
        try:
            from core.plugin_manager import MODEL_MIRRORS
            mirrors = [
                {"id": k, "display_name": v["display_name"]}
                for k, v in MODEL_MIRRORS.items()
            ]
            return {"success": True, "data": mirrors}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def delete_model(self, model_id: str) -> dict:
        """Delete a downloaded model."""
        try:
            self._plugin_manager.delete_model(model_id)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    @expose
    def check_plugin_status(self, engine: str) -> dict:
        """Check if an ASR engine is ready (plugin installed + model downloaded)."""
        # Find the plugin for this engine
        plugin_id = None
        for pid, meta in PLUGIN_REGISTRY.items():
            if meta["engine"] == engine:
                plugin_id = pid
                break

        if plugin_id is None:
            return {"success": False, "error": f"Unknown engine: {engine}"}

        installed = self._plugin_manager.is_installed(plugin_id)
        models = PLUGIN_REGISTRY[plugin_id]["models"]
        downloaded_models = {
            mid: self._plugin_manager.is_model_downloaded(mid)
            for mid in models
        }

        return {
            "success": True,
            "data": {
                "engine": engine,
                "plugin_id": plugin_id,
                "installed": installed,
                "models": downloaded_models,
                "ready": installed and any(downloaded_models.values()),
            },
        }

    @expose
    def get_asr_log(self, task_id: str) -> dict:
        """Return the log content for an ASR task."""
        return {"success": True, "data": self._plugin_manager.get_asr_log(task_id)}

    @expose
    def list_asr_logs(self) -> dict:
        """Return ASR log file list sorted by modification time (newest first)."""
        return {"success": True, "data": self._plugin_manager.list_asr_logs()}

    @expose
    def get_asr_task_state(self, task_id: str) -> dict:
        """Return the current state of a subprocess ASR task."""
        return {"success": True, "data": self._plugin_manager.get_subprocess_state(task_id)}

    @expose
    def get_settings(self) -> dict:
        return self._project.get_settings()

    @expose
    def get_plugin_data_dir(self) -> dict:
        """Return the plugin data directory path."""
        from core.paths import get_plugin_data_dir
        path = get_plugin_data_dir()
        return {"success": True, "data": {"path": str(path)}}

    @expose
    def open_data_directory(self) -> dict:
        """Open the plugin data directory in the system file manager."""
        import os
        from core.paths import get_plugin_data_dir
        path = get_plugin_data_dir()
        try:
            os.startfile(str(path))
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def cleanup_tasks_folder(self) -> dict:
        """Clean up old transcription task files (logs and results)."""
        try:
            tasks_dir = Path(get_data_dir()) / "plugins" / "tasks"
            if not tasks_dir.exists():
                return {"success": True, "data": {"deleted": 0, "message": "No tasks folder found"}}

            deleted = 0
            for f in tasks_dir.iterdir():
                if f.is_file() and (f.suffix in (".log", ".json")):
                    f.unlink()
                    deleted += 1

            return {"success": True, "data": {"deleted": deleted, "message": f"Cleaned up {deleted} task files"}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def cleanup_transcripts_folder(self) -> dict:
        """Delete all auto-saved transcription SRT files."""
        try:
            transcripts_dir = get_data_dir() / "transcripts"
            if not transcripts_dir.exists():
                return {"success": True, "data": {"deleted": 0, "size_freed": 0}}

            deleted = 0
            size_freed = 0
            for f in transcripts_dir.iterdir():
                if f.is_file() and f.suffix == ".srt":
                    size_freed += f.stat().st_size
                    f.unlink()
                    deleted += 1

            logger.info("Cleaned up transcripts folder: {} files, {} bytes freed", deleted, size_freed)
            return {"success": True, "data": {"deleted": deleted, "size_freed": size_freed}}
        except Exception as e:
            logger.exception("cleanup_transcripts_folder failed")
            return {"success": False, "error": str(e)}

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
    def detect_gpu_encoders(self) -> dict:
        """Detect available FFmpeg encoders."""
        from core.ffmpeg_presets import ENCODER_METADATA
        encoders: list[str] = []
        try:
            from core.ffmpeg_service import _find_ffmpeg
            ffmpeg = _find_ffmpeg()
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-encoders"],
                capture_output=True, text=True, timeout=5,
                **_SUBPROCESS_KWARGS,
            )
            if result.returncode == 0:
                registered = result.stdout
                for codec_name in ENCODER_METADATA:
                    if f" {codec_name} " in registered:
                        encoders.append(codec_name)
        except Exception:
            pass

        return {
            "success": True,
            "data": {
                "encoders": sorted(set(encoders)),
            },
        }

    @expose
    def detect_gpu(self) -> dict:
        """Detect GPU status for plugin installation recommendations."""
        from core.plugin_manager import detect_gpu
        try:
            result = detect_gpu()
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def list_mirrors(self) -> dict:
        """List available PyTorch mirrors."""
        from core.plugin_manager import PYTORCH_MIRRORS
        return {"success": True, "data": PYTORCH_MIRRORS}

    @expose
    def get_ffmpeg_info(self) -> dict:
        """Return FFmpeg status for settings page."""
        from core.ffmpeg_service import _find_ffmpeg, _find_ffprobe
        info: dict = {"ffmpeg_path": "", "ffprobe_path": "", "version": ""}
        try:
            info["ffmpeg_path"] = _find_ffmpeg()
            result = subprocess.run(
                [info["ffmpeg_path"], "-version"],
                capture_output=True, text=True, timeout=5,
                **_SUBPROCESS_KWARGS,
            )
            if result.returncode == 0:
                info["version"] = result.stdout.split("\n")[0]
        except Exception:
            pass
        try:
            info["ffprobe_path"] = _find_ffprobe()
        except Exception:
            pass
        return {"success": True, "data": info}

    @expose
    def check_uv_available(self) -> dict:
        """Check if uv package manager is available in PATH."""
        if os.environ.get("MILO_FAKE_NO_UV"):
            import time; time.sleep(0.1)  # avoid pywebview callback race
            return {
                "success": True,
                "data": {
                    "available": False,
                    "path": None,
                },
            }
        uv_path = shutil.which("uv")
        return {
            "success": True,
            "data": {
                "available": uv_path is not None,
                "path": uv_path,
            },
        }

    @expose
    def get_encoder_metadata(self) -> dict:
        """Return encoder metadata for frontend UI configuration."""
        return {
            "success": True,
            "data": ENCODER_METADATA,
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
    def export_xmeml_premiere(self, output_path: str, mode: str = "clean") -> dict:
        """Export xmeml for Premiere Pro."""
        from core.export_timeline import export_xmeml_premiere as _export_xmeml_premiere
        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.transcript.segments]
        edits = [e.model_dump() for e in project.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_xmeml_premiere(segments, edits, media_info, output_path, mode=mode)

    @expose
    def export_otio(self, output_path: str, fade_duration: float = 0.0, mode: str = "clean", fade_mode: str = "crossfade", audio_fade_duration: float | None = None) -> dict:
        """Export OpenTimelineIO (.otio) file."""
        from core.export_timeline import export_otio as _export_otio
        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.transcript.segments]
        edits = [e.model_dump() for e in project.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_otio(segments, edits, media_info, output_path, fade_duration=fade_duration, mode=mode, fade_mode=fade_mode, audio_fade_duration=audio_fade_duration)


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

"""Milo-Cut application entry point.

AI-powered video preprocessing tool for oral presentation videos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from pywebvue import App, Bridge, expose

_BRIDGE_DEFAULT_PORT = 18230

_SUBPROCESS_KWARGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32"
    else {"start_new_session": True}
)


def _fix_macos_path() -> None:
    """Inject shell PATH into the macOS .app bundle environment.

    When launched as a .app, macOS does not load ~/.zshrc or ~/.bash_profile,
    so tools like ffmpeg and uv are not on PATH. This reads the user's shell
    profile and injects the resulting PATH into os.environ.
    """
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return

    import subprocess as _sp

    shell = os.environ.get("SHELL", "/bin/zsh")
    try:
        result = _sp.run(
            [shell, "-l", "-c", "echo $PATH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
    except Exception:
        pass


_fix_macos_path()

from core.bridge_service import BridgeService
from core.config import load_settings
from core.events import EDIT_SUMMARY_UPDATED, ENCODER_FALLBACK, PROJECT_DIRTY, PROJECT_SAVED
from core.export_service import export_audio, export_srt, export_video, export_vtt
from core.ffmpeg_presets import ENCODER_METADATA, get_fallback_codec
from core.ffmpeg_service import (
    _find_ffmpeg,
    detect_silence,
    generate_waveform,
    load_waveform_cache,
    probe_media,
    read_peaks_file,
    write_waveform_cache,
)
from core.logging import get_logger, setup_frontend_sink, setup_logging
from core.media_server import MediaServer
from core.models import SegmentType, TaskStatus, TaskType
from core.paths import migrate_if_needed
from core.plugin_manager import PLUGIN_REGISTRY, PluginManager
from core.project_service import ProjectService
from core.proxy_manager import ProxyManager
from core.subtitle_service import parse_srt
from core.task_manager import TaskManager

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
        settings = load_settings()
        model_dir = settings.get("model_dir", "")
        self._plugin_manager = PluginManager(model_dir=Path(model_dir) if model_dir else None)
        self._register_task_handlers()
        self._proxy_manager = ProxyManager(self._task_manager)
        self._batches: dict[str, dict] = {}  # batch_id -> batch state
        from core.file_protocol import FileProtocolManager

        self._file_protocol = FileProtocolManager()
        self._bridge_service = BridgeService(
            get_projects_fn=self._bridge_get_projects,
            get_project_fn=self._bridge_get_project,
        )
        # v2.1.0 Phase 3: workflow engine
        from core.workflow_engine import WorkflowEngine
        self._workflow_engine = WorkflowEngine(
            self._task_manager, self._project, self._emit,
        )

    def _mark_dirty(self, result: dict) -> dict:
        """Emit PROJECT_DIRTY if the wrapped mutation succeeded.

        Centralizes auto-save signaling: every @expose method that mutates the
        project state should ``return self._mark_dirty(self._project.xxx())``.
        The frontend listens for ``project:dirty`` and debounce-saves (2s).
        """
        if result.get("success"):
            self._emit(PROJECT_DIRTY)
        return result

    def _register_task_handlers(self) -> None:
        """Register handlers for each task type."""
        self._task_manager.register_handler(TaskType.SILENCE_DETECTION, self._handle_silence_detection)
        self._task_manager.register_handler(TaskType.EXPORT_VIDEO, self._handle_export_video)
        self._task_manager.register_handler(TaskType.EXPORT_SUBTITLE, self._handle_export_subtitle)
        self._task_manager.register_handler(TaskType.EXPORT_AUDIO, self._handle_export_audio)
        self._task_manager.register_handler(TaskType.EXPORT_VTT, self._handle_export_vtt)
        self._task_manager.register_handler(
            TaskType.WAVEFORM_GENERATION, self._handle_waveform_generation
        )
        self._task_manager.register_handler(TaskType.PLUGIN_INSTALL, self._handle_plugin_install)
        self._task_manager.register_handler(TaskType.MODEL_DOWNLOAD, self._handle_model_download)
        self._task_manager.register_handler(TaskType.TRANSCRIPTION, self._handle_transcription)
        self._task_manager.register_handler(
            TaskType.PROXY_GENERATION, self._handle_proxy_generation
        )
        self._task_manager.register_handler(
            TaskType.LLM_SMART_DELETE, self._handle_smart_delete
        )
        self._task_manager.register_handler(
            TaskType.LLM_SUBTITLE_CORRECTION, self._handle_subtitle_correction
        )
        self._task_manager.register_handler(
            TaskType.LLM_HIGHLIGHT, self._handle_highlight
        )
        self._task_manager.register_handler(
            TaskType.LLM_SEMANTIC_SEARCH, self._handle_semantic_search
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
            result["data"],
            margin=margin,
            subtitle_padding=subtitle_padding,
        )
        if not store_result["success"]:
            raise RuntimeError(store_result.get("error", "Failed to store silence results"))
        return {"project": store_result["data"]}

    def _handle_export_video(self, task, cancel_event, progress_cb):
        """Export cut video as a background task.

        Supports batch mode: if task.payload contains ``project_path``, that
        project is opened temporarily for the export, then the original project
        state is restored.
        """
        project_path = task.payload.get("project_path", "")

        saved_project = None
        saved_path = None

        if project_path:
            # Batch mode: temporarily open the target project
            saved_project = self._project.current
            saved_path = self._project._current_path
            result = self._project.open_project(project_path)
            if not result["success"]:
                self._project._current = saved_project
                self._project._current_path = saved_path
                raise RuntimeError(
                    f"Failed to open project for batch export: "
                    f"{result.get('error', 'unknown error')}"
                )

        try:
            if self._project.current is None:
                raise ValueError("No project open")
            if self._project.current.media is None:
                raise ValueError("No media in project")
            project = self._project.current
            timeline = project.active_timeline
            segments_data, edits_data = self._get_export_segments_and_edits(task, timeline)
            media_path = project.media.path
            output_path = task.payload.get("output_path", "")
            if not output_path:
                base, ext = os.path.splitext(media_path)
                suffix = "_highlight" if task.payload.get("highlight_mode") else "_cut"
                output_path = f"{base}{suffix}{ext}"

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
                self._emit(
                    ENCODER_FALLBACK,
                    {
                        "requested": original_codec,
                        "fallback": video_codec,
                        "message": fallback_msg,
                    },
                )

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
        finally:
            if project_path:
                # Restore original project state
                self._project._current = saved_project
                self._project._current_path = saved_path

    def _handle_export_subtitle(self, task, cancel_event, progress_cb):
        """Export synchronized SRT as a background task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")
        project = self._project.current
        timeline = project.active_timeline

        # v3.0.1 M6-1: track exports ride the confirmed-deletion mapping
        # (same functions as the main track); payload adds format and the
        # bilingual merged mode.
        track_id = task.payload.get("track_id")
        if track_id:
            from core.export_service import (
                export_bilingual_subtitle,
                export_track_subtitle,
            )

            fmt = task.payload.get("format", "srt")
            if fmt not in ("srt", "vtt"):
                fmt = "srt"
            merge_bilingual = bool(task.payload.get("merge_bilingual"))
            media_duration = project.media.duration if project.media else 0.0
            base = os.path.splitext(project.media.path)[0]
            track = next(
                (t for t in timeline.transcript.tracks if t.id == track_id), None
            )
            if track is None:
                return {"success": False, "error": f"Track {track_id} not found"}
            suffix = f"_{track.name}" if track.name else f"_{track_id}"
            if merge_bilingual:
                segments_data, edits_data = self._get_export_segments_and_edits(
                    task, timeline
                )
                output_path = task.payload.get(
                    "output_path", f"{base}_bilingual.{fmt}"
                )
                return export_bilingual_subtitle(
                    segments_data,
                    track.model_dump(mode="json"),
                    [b.model_dump(mode="json") for b in timeline.transcript.bindings],
                    edits_data,
                    output_path,
                    media_duration=media_duration,
                    fmt=fmt,
                )
            output_path = task.payload.get("output_path", f"{base}{suffix}.{fmt}")
            _segments_data, edits_data = self._get_export_segments_and_edits(
                task, timeline
            )
            return export_track_subtitle(
                track.model_dump(mode="json"),
                edits_data,
                output_path,
                media_duration=media_duration,
                fmt=fmt,
            )

        segments_data, edits_data = self._get_export_segments_and_edits(task, timeline)
        output_path = task.payload.get("output_path", "")
        if not output_path:
            suffix = "_highlight.srt" if task.payload.get("highlight_mode") else "_cut.srt"
            output_path = os.path.splitext(project.media.path)[0] + suffix

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
        timeline = project.active_timeline
        segments_data, edits_data = self._get_export_segments_and_edits(task, timeline)
        output_path = task.payload.get("output_path", "")
        if not output_path:
            suffix = "_highlight.vtt" if task.payload.get("highlight_mode") else "_cut.vtt"
            output_path = os.path.splitext(project.media.path)[0] + suffix

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
        timeline = project.active_timeline
        segments_data, edits_data = self._get_export_segments_and_edits(task, timeline)
        media_path = project.media.path
        output_path = task.payload.get("output_path", "")
        if not output_path:
            base, _ = os.path.splitext(media_path)
            suffix = "_highlight" if task.payload.get("highlight_mode") else "_cut"
            output_path = f"{base}{suffix}.m4a"

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

    def _get_target_timeline(self, task):
        """Resolve target timeline from task payload or active timeline.

        All rule analysis and LLM handlers use this helper to get segments,
        eliminating the repeated timeline-lookup boilerplate (v2.1.1 AR-1).

        payload carries ``timeline_id`` -> use it; otherwise fall back to
        ``project.active_timeline_id``.
        """
        if self._project.current is None:
            raise ValueError("No project open")
        project = self._project.current
        timeline_id = task.payload.get("timeline_id", "") or project.active_timeline_id
        timeline = project.get_timeline(timeline_id)
        if timeline is None:
            raise ValueError(f"Timeline {timeline_id} not found")
        return timeline

    def _get_export_segments_and_edits(self, task, timeline):
        """Get segments and edits for export, applying highlight mode if requested.

        v2.2.0: When ``task.payload["highlight_mode"]`` is true, replaces the
        normal edit list with virtual edits that delete all non-highlight ranges,
        so the existing export pipeline produces a highlight reel.

        Returns ``(segments_data, edits_data)``.
        """
        segments_data = [s.model_dump() for s in timeline.transcript.segments]
        if task.payload.get("highlight_mode"):
            from core.export_service import build_highlight_export_edits

            # Use actual media duration (not just last segment end) so trailing
            # content after the last subtitle is correctly excluded from the
            # highlight reel.
            media_duration = 0.0
            if self._project.current and self._project.current.media:
                media_duration = self._project.current.media.duration
            if not media_duration and segments_data:
                media_duration = max(s["end"] for s in segments_data)
            edits_data = build_highlight_export_edits(
                segments_data,
                timeline.analysis.results,
                media_duration=media_duration,
                existing_edits=[e.model_dump() for e in timeline.edits],
            )
            if not edits_data:
                raise ValueError("No highlight segments to export")
            logger.info(
                "highlight export: {} segments, {} virtual edits, "
                "analysis_results={}, media_duration={}",
                len(segments_data),
                len(edits_data),
                len(timeline.analysis.results),
                media_duration,
            )
        else:
            edits_data = [e.model_dump() for e in timeline.edits]
        return segments_data, edits_data

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
            from core.paths import get_projects_dir

            name = self._project.current.project.name
            waveform_path = str(get_projects_dir() / name / "waveform.json")

        def progress_cb(percent: float, message: str = "") -> None:
            self._task_manager._update_progress(task.id, percent, message)

        def _finalize_and_save(final_waveform_path: str) -> None:
            progress_cb(90.0, "Updating project...")
            # Update media info with waveform path
            self._project.update_media_waveform(final_waveform_path)
            # Make waveform available via HTTP
            self._media_server.set_waveform(final_waveform_path)
            # Persist waveform_path to disk so it survives restart
            try:
                self._project.save_project()
            except Exception:
                logger.exception("Failed to auto-save project after waveform generation")

        # v3.0.0 M11-3: sidecar cache probe -- a {size, mtime_ms} signature
        # hit serves the peaks instantly and skips the ffmpeg extraction.
        cached = load_waveform_cache(media_path)
        if cached:
            progress_cb(100.0, "Waveform cache hit")
            _finalize_and_save(cached)
            return {
                "cached": True,
                "project": self._project.current.model_dump() if self._project.current else None,
            }

        progress_cb(10.0, "Extracting audio peaks...")
        result = generate_waveform(media_path, duration, waveform_path)
        if not result["success"]:
            raise RuntimeError(result["error"])

        # Write the sidecar cache next to the media (best effort: a read-only
        # media dir keeps the legacy project-dir waveform as the source).
        peaks = read_peaks_file(waveform_path)
        final_waveform_path = write_waveform_cache(media_path, peaks) if peaks else None
        _finalize_and_save(final_waveform_path or waveform_path)

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
        self._plugin_manager.install_plugin(
            plugin_id, progress_cb=progress_cb, mirror=mirror, no_cache=no_cache
        )

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
        plugin_id = task.payload.get("plugin_id", settings.get("asr_plugin_id", ""))

        # MLX transcription (Apple Silicon)
        if plugin_id == "plugin-qwen-mlx":
            from core.asr_service import transcribe_with_mlx

            asr_model_size = task.payload.get(
                "asr_model_size", settings.get("asr_model_size", "0.6B")
            )
            aligner_model_size = task.payload.get(
                "aligner_model_size", settings.get("asr_aligner_model_size", "0.6B")
            )

            result = transcribe_with_mlx(
                plugin_manager=self._plugin_manager,
                media_path=media_path,
                asr_model_size=asr_model_size,
                aligner_model_size=aligner_model_size,
                language=language,
                progress_cb=progress_cb,
                cancel_event=cancel_event,
            )
        elif engine == "faster-whisper":
            from core.asr_service import transcribe_with_whisper
            from core.ffmpeg_service import _find_ffmpeg

            model_size = task.payload.get(
                "model_size", settings.get("asr_model_size", "large-v3-turbo")
            )
            compute_type = task.payload.get(
                "compute_type", settings.get("whisper_compute_type", "int8_float16")
            )
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

            asr_model_size = task.payload.get(
                "asr_model_size", settings.get("asr_model_size", "0.6B")
            )
            aligner_model_size = task.payload.get(
                "aligner_model_size", settings.get("asr_aligner_model_size", "0.6B")
            )
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

        # v3.0.0 M1-1: transcript metadata (engine/language) is persisted here;
        # the structured update_transcript data is the single source of truth.
        meta_result = self._project.update_transcript_meta(
            engine=engine, language=transcript_data["language"]
        )
        project_data = (
            meta_result["data"] if meta_result.get("success") else update_result["data"]
        )
        # v3.0.0 fix (macOS smoke): transcription must trigger auto-save.
        # Before M1-1 the SRT round-trip's import_srt/_mark_dirty incidentally
        # emitted PROJECT_DIRTY; now we emit it explicitly.
        self._emit(PROJECT_DIRTY)

        # Auto-save SRT to project directory
        srt_path = None
        try:
            from datetime import datetime

            from core.export_service import export_srt
            from core.paths import get_data_dir

            project_name = (
                self._project.current.project.name
                if self._project.current.project
                else "transcript"
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            srt_filename = f"{project_name}_{timestamp}.srt"
            srt_dir = Path(get_data_dir()) / "transcripts"
            srt_dir.mkdir(parents=True, exist_ok=True)
            srt_path = str(srt_dir / srt_filename)

            segments_for_export = []
            for seg in result["data"].get("segments", []):
                segments_for_export.append(
                    {
                        "id": seg.get("id", ""),
                        "start": seg.get("start", 0),
                        "end": seg.get("end", 0),
                        "text": seg.get("text", ""),
                        "type": "subtitle",
                    }
                )

            srt_result = export_srt(
                segments=segments_for_export,
                edits=[],
                output_path=srt_path,
                media_duration=self._project.current.media.duration
                if self._project.current.media
                else 0,
            )
            if srt_result.get("success"):
                logger.info("Auto-saved transcription SRT to {}", srt_path)
            else:
                logger.warning("Failed to auto-save SRT: {}", srt_result.get("error"))
                srt_path = None
        except Exception as e:
            logger.warning("Failed to auto-save SRT: {}", e)
            srt_path = None

        # v3.0.0 M1-1: the auto-saved SRT is an archive deliverable only.
        # It is no longer imported back into the project, so ASR-produced
        # words/speaker data and seg_{start} ids survive intact.

        return {
            "project": project_data,
            "segment_count": len(result["data"].get("segments", [])),
            "word_count": result["data"].get("word_count", 0),
            "srt_path": srt_path,
        }

    def _handle_proxy_generation(self, task, cancel_event, progress_cb):
        """Handle proxy generation task."""
        if self._project.current is None:
            raise ValueError("No project open")
        if self._project.current.media is None:
            raise ValueError("No media in project")

        media_path = self._project.current.media.path
        resolution = task.payload.get("resolution", "720p")

        # Generate output path alongside original
        base, ext = os.path.splitext(media_path)
        output_path = f"{base}_proxy{ext}"

        try:
            from core.ffmpeg_service import generate_proxy

            result = generate_proxy(media_path, output_path, resolution, progress_cb, cancel_event)
            return result
        finally:
            self._proxy_manager.on_proxy_complete(media_path)

    def _handle_smart_delete(self, task, cancel_event, progress_cb):
        """Run LLM smart-delete analysis: catch what rule engine misses."""
        if self._project.current is None:
            raise ValueError("No project open")

        from core.llm_service import analyze_smart_delete
        from core.timeline_utils import collect_confirmed_deleted_seg_ids

        timeline = self._get_target_timeline(task)

        # Audit #8: filter out confirmed-deleted segments before LLM analysis
        deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
        segments = [
            s.model_dump()
            for s in timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
        ]
        if not segments:
            raise ValueError("No subtitle segments to analyze")

        # Collect segment IDs already flagged by rule engine (incremental)
        existing_ids: set[str] = set()
        for result in timeline.analysis.results:
            existing_ids.update(result.segment_ids)

        def _chunk_callback(chunk_results: list[dict]) -> None:
            """Emit per-window results for frontend live update."""
            self._emit(
                "llm:smart_delete_progress",
                {"results": chunk_results},
            )

        # Phase 3: resolve effective prompt (project > global > default)
        from core.llm_prompts import get_effective_prompt

        project_prompts = (
            timeline.llm_prompts if hasattr(timeline, "llm_prompts") else None
        )
        effective_prompt = get_effective_prompt("smart_delete", project_prompts)

        result = analyze_smart_delete(
            segments,
            existing_flagged_ids=existing_ids,
            cancel_event=cancel_event,
            progress_cb=progress_cb,
            chunk_callback=_chunk_callback,
            system_prompt=effective_prompt,
        )

        if not result.get("success"):
            error = result.get("error", "Smart-delete analysis failed")
            self._emit("llm:analysis_failed", {"error": error})
            raise RuntimeError(error)

        all_results = result["data"]["results"]
        token_usage = result["data"]["token_usage"]
        ledger = result["data"].get("ledger")  # M3-1 batch ledger

        # Convert results to EditDecisions with source="llm_smart"
        from datetime import datetime as _dt

        _ts = int(_dt.now().timestamp() * 1000)
        # Build category lookup from all_results for partial_delete detection
        category_by_seg = {r["segment_id"]: r.get("category", "") for r in all_results}
        edits = []
        seg_map = {s.id: s for s in timeline.transcript.segments}
        for i, r in enumerate(all_results):
            seg = seg_map.get(r["segment_id"])
            if seg is None:
                continue
            is_partial = category_by_seg.get(seg.id) == "partial_delete"
            edits.append(
                {
                    "id": f"llm_smart_{_ts}_{i}",
                    "start": seg.start,
                    "end": seg.end,
                    "action": "keep" if is_partial else "delete",
                    "source": "llm_smart",
                    "target_type": "segment",
                    "target_id": seg.id,
                    "priority": 10 if is_partial else 50,
                }
            )

        # Store as analysis results + edits
        if edits:
            analysis_results = [
                {
                    "id": f"llm_smart_{_ts}_{i}",
                    "type": "llm_smart_delete",
                    "segment_ids": [r["segment_id"]],
                    "confidence": r.get("confidence", 0.8),
                    "detail": r.get("reason", ""),
                    "category": r.get("category", ""),
                }
                for i, r in enumerate(all_results)
                if r["segment_id"] in seg_map
            ]
            # v2.1.0 Phase 3: workflow accumulation mode -- skip project write
            if not task.payload.get("_workflow_accumulate"):
                store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_smart"))
                if not store["success"]:
                    raise RuntimeError(store.get("error", "Failed to store smart-delete results"))

        self._emit(
            "llm:smart_delete_completed",
            {"results": all_results, "edits": edits, "ledger": ledger},
        )
        self._emit("llm:token_usage", token_usage)

        return {
            "results": all_results,
            "edits": edits,
            "token_usage": token_usage,
            "ledger": ledger,
            "project": self._project.current.model_dump() if self._project.current else None,
        }

    def _handle_subtitle_correction(self, task, cancel_event, progress_cb):
        """Run LLM subtitle correction on the active timeline."""
        if self._project.current is None:
            raise ValueError("No project open")

        from core.llm_service import analyze_subtitle_correction
        from core.timeline_utils import (
            collect_confirmed_deleted_seg_ids,
            collect_partial_delete_hints,
        )

        timeline = self._get_target_timeline(task)
        timeline_id = task.payload.get("timeline_id", "") or self._project.current.active_timeline_id

        reference_text = task.payload.get("reference_text", "")
        # v2.1.1 M2: context_window defaults from settings; payload may override.
        context_window = task.payload.get("context_window", 3)

        # Audit #8: filter out confirmed-deleted segments before LLM correction
        deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
        # v2.2.0: collect partial_delete hints from prior smart-delete analysis
        # so the subtitle correction LLM can leverage them (e.g. intra-sentence
        # errors that cannot be wholesale deleted but should be textually fixed).
        partial_hints = collect_partial_delete_hints(timeline)
        segments = []
        for s in timeline.transcript.segments:
            if s.type != SegmentType.SUBTITLE or s.id in deleted_seg_ids:
                continue
            seg_dict = s.model_dump()
            hint = partial_hints.get(s.id)
            if hint:
                seg_dict["edit_hint"] = hint
            segments.append(seg_dict)
        if not segments:
            raise ValueError("No subtitle segments to correct")

        # Phase 3: resolve effective prompts for both modes
        from core.llm_prompts import get_effective_prompt

        project_prompts = (
            timeline.llm_prompts if hasattr(timeline, "llm_prompts") else None
        )
        effective_prompt_a = get_effective_prompt(
            "subtitle_correction_a", project_prompts
        )
        effective_prompt_b = get_effective_prompt(
            "subtitle_correction_b", project_prompts
        )

        result = analyze_subtitle_correction(
            segments,
            reference_text=reference_text if reference_text else None,
            context_window=context_window,
            cancel_event=cancel_event,
            progress_cb=progress_cb,
            system_prompt_a=effective_prompt_a,
            system_prompt_b=effective_prompt_b,
        )

        if not result.get("success"):
            error = result.get("error", "Subtitle correction failed")
            self._emit("llm:analysis_failed", {"error": error})
            raise RuntimeError(error)

        corrections = result["data"]["corrections"]
        token_usage = result["data"]["token_usage"]
        ledger = result["data"].get("ledger")  # M3-1 batch ledger

        # v2.1.0 Phase 3: workflow accumulation mode -- skip project write,
        # return raw corrections for the engine to accumulate.
        if task.payload.get("_workflow_accumulate"):
            self._emit("llm:token_usage", token_usage)
            return {
                "corrections": corrections,
                "stored_count": len(corrections),
                "token_usage": token_usage,
                "ledger": ledger,
            }

        # v2.1.0 Phase 2: store corrections for review instead of auto-applying.
        store_result = self._mark_dirty(
            self._project.correction.store_subtitle_corrections(corrections, timeline_id)
        )

        if not store_result["success"]:
            raise RuntimeError(
                store_result.get("error", "Failed to store subtitle corrections")
            )

        store_data = store_result["data"]
        if isinstance(store_data, dict) and ledger:
            store_data = {**store_data, "ledger": ledger}
        self._emit("llm:subtitle_correction_completed", store_data)
        self._emit("llm:token_usage", token_usage)

        return {
            "corrections": corrections,
            "stored_count": store_result["data"].get("stored_count", 0),
            "token_usage": token_usage,
            "ledger": ledger,
            "project": self._project.current.model_dump() if self._project.current else None,
        }

    def _handle_highlight(self, task, cancel_event, progress_cb):
        """Run LLM highlight extraction: identify high-density segments."""
        if self._project.current is None:
            raise ValueError("No project open")

        from core.llm_service import analyze_highlights
        from core.timeline_utils import collect_confirmed_deleted_seg_ids

        timeline = self._get_target_timeline(task)

        target_minutes = task.payload.get("target_duration_minutes", 10)

        # P0-5: filter out confirmed-deleted segments before LLM highlight analysis
        deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
        segments = [
            s.model_dump()
            for s in timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
        ]
        if not segments:
            raise ValueError("No subtitle segments to analyze")

        def _chunk_callback(chunk_results: list[dict]) -> None:
            self._emit(
                "llm:highlight_progress",
                {"results": chunk_results},
            )

        # Phase 3: resolve effective prompt
        from core.llm_prompts import get_effective_prompt

        project_prompts = (
            timeline.llm_prompts if hasattr(timeline, "llm_prompts") else None
        )
        effective_prompt = get_effective_prompt("highlight", project_prompts)

        result = analyze_highlights(
            segments,
            target_duration_minutes=target_minutes,
            cancel_event=cancel_event,
            progress_cb=progress_cb,
            chunk_callback=_chunk_callback,
            system_prompt=effective_prompt,
        )

        if not result.get("success"):
            error = result.get("error", "Highlight analysis failed")
            self._emit("llm:analysis_failed", {"error": error})
            raise RuntimeError(error)

        all_results = result["data"]["results"]
        token_usage = result["data"]["token_usage"]
        total_duration = result["data"]["total_highlight_duration"]

        seg_map = {s.id: s for s in timeline.transcript.segments}

        # Store as analysis results
        if all_results:
            from datetime import datetime as _dt

            analysis_results = [
                {
                    "id": f"llm_hl_{int(_dt.now().timestamp() * 1000)}",
                    "type": "llm_highlight",
                    "segment_ids": [r["segment_id"]],
                    "confidence": 1.0 if r["density"] == "high" else 0.7,
                    "detail": r.get("highlight_reason", ""),
                }
                for r in all_results
                if r["segment_id"] in seg_map
            ]
            # v2.1.0 Phase 3: workflow accumulation mode -- skip project write
            if not task.payload.get("_workflow_accumulate"):
                store = self._mark_dirty(self._project.add_analysis_results(
                    analysis_results, source="llm_highlight", clear_existing=True,
                ))
                if not store["success"]:
                    raise RuntimeError(store.get("error", "Failed to store highlight results"))

        self._emit(
            "llm:highlight_completed",
            {
                "results": all_results,
                "total_duration": total_duration,
                "target_duration": result["data"]["target_duration"],
            },
        )
        self._emit("llm:token_usage", token_usage)

        return {
            "results": all_results,
            "total_duration": total_duration,
            "token_usage": token_usage,
            "project": self._project.current.model_dump() if self._project.current else None,
        }

    def _handle_semantic_search(self, task, cancel_event, progress_cb):
        """Run LLM semantic search over transcript."""
        if self._project.current is None:
            raise ValueError("No project open")

        from core.llm_service import semantic_search

        timeline = self._get_target_timeline(task)

        query = task.payload.get("query", "")
        top_k = task.payload.get("top_k", 5)

        segments = [
            s.model_dump()
            for s in timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE
        ]
        if not segments:
            raise ValueError("No subtitle segments to search")

        result = semantic_search(
            query,
            segments,
            top_k=top_k,
            cancel_event=cancel_event,
        )

        if not result.get("success"):
            error = result.get("error", "Semantic search failed")
            self._emit("llm:analysis_failed", {"error": error})
            raise RuntimeError(error)

        search_results = result["data"]["results"]
        self._emit(
            "llm:semantic_search_completed",
            {"results": search_results, "query": query},
        )

        return {"results": search_results, "query": query}

    # ================================================================
    # region System
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

    @expose
    def select_directory(self) -> dict:
        """Open a folder picker dialog and return the selected path."""
        import webview

        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        if result:
            # pywebview FOLDER dialog returns a tuple/list on Windows,
            # but a string on macOS/Linux
            if isinstance(result, (tuple, list)):
                path = str(result[0]) if result else None
            else:
                path = str(result)
            if path:
                return {"success": True, "data": path}
        return {"success": True, "data": None}

    # ================================================================
    # endregion System
    # region Project
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
        result = self._project.save_project()
        # Publish edit timeline to file protocol on save
        if result.get("success"):
            if self._project.current is not None:
                project = self._project.current
                segments = [s.model_dump() for s in project.active_timeline.transcript.segments]
                edits = [e.model_dump() for e in project.active_timeline.edits]
                self._file_protocol.publish_edit_timeline(segments, edits)
            self._emit(PROJECT_SAVED)  # tell frontend the project is clean
        return result

    @expose
    def close_project(self) -> dict:
        self._media_server.stop()
        return self._project.close_project()

    @expose
    def relink_media(self, new_path: str) -> dict:
        return self._project.relink_media(new_path)

    # ================================================================
    # endregion Project
    # region Timeline (multi-timeline infrastructure, v2.0.0)
    # ================================================================

    @expose
    def create_timeline(
        self, label: str, source: str = "manual", fork_from: str | None = None
    ) -> dict:
        return self._mark_dirty(self._project.create_timeline(label, source, fork_from))

    @expose
    def switch_timeline(self, timeline_id: str) -> dict:
        return self._project.switch_timeline(timeline_id)

    @expose
    def delete_timeline(self, timeline_id: str) -> dict:
        return self._mark_dirty(self._project.delete_timeline(timeline_id))

    @expose
    def rename_timeline(self, timeline_id: str, new_label: str) -> dict:
        return self._mark_dirty(self._project.rename_timeline(timeline_id, new_label))

    @expose
    def duplicate_timeline(self, timeline_id: str, new_label: str) -> dict:
        return self._mark_dirty(self._project.duplicate_timeline(timeline_id, new_label))

    # ================================================================
    # endregion Timeline
    # region Subtitle
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

        # SRT import mutates transcript -- signal auto-save
        self._mark_dirty(update_result)
        return update_result

    @expose
    def import_srt_as_track(
        self, file_path: str, language: str = "", role: str = "extension"
    ) -> dict:
        """Import an SRT file as a read-only extension track (v3.0.0 M11-2)."""
        result = self._project.import_srt_as_track(file_path, language, role)
        # Track import mutates the transcript -- signal auto-save
        return self._mark_dirty(result)

    # ================================================================
    # endregion Subtitle
    # region FFmpeg
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
        return {
            "success": True,
            "data": {"url": f"http://127.0.0.1:{self._media_server.port}/waveform"},
        }

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
    # endregion FFmpeg
    # region Tasks
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
    def cancel_llm_tasks(self) -> dict:
        """Cancel all currently running/queued LLM tasks (single-function mode)."""
        llm_types = {
            "llm_smart_delete", "llm_subtitle_correction",
            "llm_highlight", "llm_semantic_search",
        }
        tasks = self._task_manager.list_tasks()
        cancelled = 0
        for t in tasks.get("data", []):
            if t.get("type") in llm_types and t.get("status") in ("queued", "running"):
                self._task_manager.cancel_task(t["id"])
                cancelled += 1
        return {"success": True, "data": {"cancelled": cancelled}}

    @expose
    def get_task(self, task_id: str) -> dict:
        return self._task_manager.get_task(task_id)

    @expose
    def list_tasks(self) -> dict:
        return self._task_manager.list_tasks()

    @expose
    def request_proxy(self, media_path: str, priority: str = "normal") -> dict:
        """Request proxy generation for a media file.

        Lazy generation: only creates a task on first request.
        Deduplicates requests for the same media path.
        """
        return self._proxy_manager.request_proxy(media_path, priority)

    @expose
    def create_batch_export(self, project_paths: list[str]) -> dict:
        """Create a batch of export video tasks for multiple projects.

        Each project gets an EXPORT_VIDEO task with ``"normal"`` priority.
        Tasks execute sequentially via the TaskManager's heavy semaphore
        (concurrency=1 for EXPORT_VIDEO).

        Args:
            project_paths: List of project.json file paths to export.

        Returns:
            ``{"success": True, "data": {"batch_id": ..., "task_ids": [...],
            "total_count": N}}``
        """
        if not project_paths:
            return {"success": False, "error": "No project paths provided"}

        batch_id = uuid.uuid4().hex[:8]
        task_ids: list[str] = []

        for path in project_paths:
            task = self._task_manager.create_task(
                "export_video",
                {"project_path": path, "batch_id": batch_id},
                priority="normal",
            )
            if not task["success"]:
                return task
            task_ids.append(task["data"]["id"])

        self._batches[batch_id] = {
            "batch_id": batch_id,
            "task_ids": task_ids,
            "project_paths": list(project_paths),
            "total_count": len(task_ids),
        }

        logger.info(
            "Batch export created: batch_id={}, {} projects queued",
            batch_id,
            len(task_ids),
        )

        return {
            "success": True,
            "data": {
                "batch_id": batch_id,
                "task_ids": task_ids,
                "total_count": len(task_ids),
            },
        }

    @expose
    def get_batch_status(self, batch_id: str) -> dict:
        """Get the aggregate status of a batch export.

        Queries each task in the batch from TaskManager and tallies counts
        by status (completed, failed, running, queued, cancelled).

        Returns:
            ``{"success": True, "data": {"batch_id", "total_count",
            "completed_count", "failed_count", "running_count",
            "queued_count", "cancelled_count", "status"}}``
        """
        batch = self._batches.get(batch_id)
        if not batch:
            return {"success": False, "error": f"Batch not found: {batch_id}"}

        completed = 0
        failed = 0
        running = 0
        queued = 0
        cancelled = 0

        for task_id in batch["task_ids"]:
            task_result = self._task_manager.get_task(task_id)
            if not task_result["success"]:
                failed += 1
                continue
            status = task_result["data"]["status"]
            if status == TaskStatus.COMPLETED:
                completed += 1
            elif status == TaskStatus.FAILED:
                failed += 1
            elif status == TaskStatus.RUNNING:
                running += 1
            elif status == TaskStatus.QUEUED:
                queued += 1
            elif status == TaskStatus.CANCELLED:
                cancelled += 1

        total = batch["total_count"]
        is_done = (completed + failed + cancelled) >= total

        return {
            "success": True,
            "data": {
                "batch_id": batch_id,
                "total_count": total,
                "completed_count": completed,
                "failed_count": failed,
                "running_count": running,
                "queued_count": queued,
                "cancelled_count": cancelled,
                "status": "completed" if is_done else "running",
            },
        }

    # ================================================================
    # endregion Tasks
    # region Project State (editing, analysis, segments)
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
    def update_edit_decisions_batch(self, edit_ids: list[str], status: str) -> dict:
        return self._project.update_edit_decisions_batch(edit_ids, status)

    @expose
    def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
        return self._mark_dirty(self._project.delete_edit_decisions_batch(edit_ids))

    @expose
    def add_analysis_results(self, results: list, source: str = "manual") -> dict:
        """Add analysis results and generate EditDecisions from them.

        Args:
            results: List of AnalysisResult dicts.
            source: Source label for the generated edits.
        """
        return self._mark_dirty(self._project.add_analysis_results(results, source=source))

    @expose
    def add_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
        """Add a single segment to highlights via AnalysisResult.

        Args:
            segment_id: The segment ID to add to highlights.
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True, "data": {"result": dict}}
        """
        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        project = self._project.current
        tl_id = timeline_id or project.active_timeline_id
        timeline = project.get_timeline(tl_id)
        if timeline is None:
            return {"success": False, "error": f"Timeline {tl_id} not found"}

        # Verify segment exists
        seg = next((s for s in timeline.transcript.segments if s.id == segment_id), None)
        if seg is None or seg.type != "subtitle":
            return {"success": False, "error": f"Segment {segment_id} not found or not a subtitle"}

        import uuid
        result = {
            "id": f"manual_hl_{uuid.uuid4().hex[:12]}",
            "type": "llm_highlight",
            "segment_ids": [segment_id],
            "confidence": 1.0,
            "detail": "手动添加",
        }

        store = self._mark_dirty(
            self._project.add_analysis_results([result], source="manual_highlight")
        )

        if not store["success"]:
            return {"success": False, "error": store.get("error", "Failed to store highlight")}

        # Return full project so the frontend can hydrate highlight state
        # in real time (Issue 5) without a separate reload.
        return {"success": True, "data": {"result": result, "project": self._project.current.model_dump()}}

    @expose
    def remove_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
        """Remove analysis results matching a segment from highlights.

        Args:
            segment_id: The segment ID whose highlight should be removed.
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True} or {"success": False, "error": str}
        """
        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        project = self._project.current
        tl_id = timeline_id or project.active_timeline_id
        timeline = project.get_timeline(tl_id)
        if timeline is None:
            return {"success": False, "error": f"Timeline {tl_id} not found"}

        results = timeline.analysis.results
        # AnalysisResult is a Pydantic model — use attribute access, not .get()
        removed = [r for r in results if segment_id in r.segment_ids]
        if not removed:
            return {"success": False, "error": f"No highlight found for segment {segment_id}"}

        remaining = [r for r in results if segment_id not in r.segment_ids]
        removed_ar_ids = {r.id for r in removed}

        # 同步清理关联 EditDecision（Bug G 修复）
        remaining_edits = [
            e for e in timeline.edits
            if e.analysis_id not in removed_ar_ids
        ]
        removed_edit_count = len(timeline.edits) - len(remaining_edits)

        self._project._update_timeline_by_id(
            tl_id,
            analysis=timeline.analysis.model_copy(update={"results": remaining}),
            edits=remaining_edits,
        )
        self._mark_dirty({"success": True})

        logger.info(
            "Removed highlight for segment %s: %d results + %d edits",
            segment_id, len(removed), removed_edit_count,
        )
        # Return full project so the frontend can hydrate highlight state
        # in real time (Issue 5) without a separate reload.
        return {"success": True, "data": {
            "removed_count": len(removed),
            "project": self._project.current.model_dump(),
        }}

    @expose
    def update_segment(self, segment_id: str, updates: dict) -> dict:
        return self._mark_dirty(self._project.update_segment(segment_id, updates))

    @expose
    def update_track_segment(self, track_id: str, segment_id: str, updates: dict) -> dict:
        """v3.0.1 M2-2: edit an extension-track segment (offsets rebuild)."""
        return self._mark_dirty(
            self._project.update_track_segment(track_id, segment_id, updates)
        )

    @expose
    def update_segment_text(self, segment_id: str, text: str) -> dict:
        return self._mark_dirty(self._project.update_segment_text(segment_id, text))

    @expose
    def delete_track_segment(self, track_id: str, segment_id: str) -> dict:
        """v3.0.2: delete an extension-track segment (bindings dropped)."""
        return self._mark_dirty(
            self._project.delete_track_segment(track_id, segment_id)
        )

    @expose
    def merge_segments(self, segment_ids: list[str]) -> dict:
        return self._mark_dirty(self._project.merge_segments(segment_ids))

    @expose
    def split_segment(
        self, segment_id: str, position: float, snap_to_word: bool = False
    ) -> dict:
        return self._mark_dirty(
            self._project.split_segment(segment_id, position, snap_to_word)
        )

    @expose
    def apply_undo(self, layers_payload: dict, base_revision: int) -> dict:
        """Layered undo/redo entry point (v3.0.0 M5)."""
        return self._mark_dirty(
            self._project.apply_undo(layers_payload, base_revision)
        )

    @expose
    def add_segment(
        self, start: float, end: float, text: str = "", seg_type: str = "subtitle"
    ) -> dict:
        return self._mark_dirty(self._project.add_segment(start, end, text, seg_type))

    @expose
    def delete_segment(self, segment_id: str) -> dict:
        return self._mark_dirty(self._project.delete_segment(segment_id))

    @expose
    def delete_silence_segments(self) -> dict:
        return self._mark_dirty(self._project.delete_silence_segments())

    @expose
    def clear_subtitles(self) -> dict:
        return self._mark_dirty(self._project.clear_subtitles())

    @expose
    def delete_subtitle_trim_edits(self) -> dict:
        return self._mark_dirty(self._project.delete_subtitle_trim_edits())

    @expose
    def search_replace(self, query: str, replacement: str, scope: str = "all") -> dict:
        return self._mark_dirty(self._project.search_replace(query, replacement, scope))

    @expose
    def mark_segments(self, segment_ids: list[str], action: str, status: str = "pending") -> dict:
        return self._mark_dirty(self._project.mark_segments(segment_ids, action, status))

    @expose
    def confirm_all_suggestions(self) -> dict:
        result = self._project.confirm_all_suggestions()
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
            self._emit(PROJECT_DIRTY)
        return result

    @expose
    def reject_all_suggestions(self) -> dict:
        result = self._project.reject_all_suggestions()
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
            self._emit(PROJECT_DIRTY)
        return result

    @expose
    def generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict:
        result = self._project.generate_subtitle_keep_ranges(padding)
        if result["success"]:
            self._emit(EDIT_SUMMARY_UPDATED, self._project.get_edit_summary().get("data", {}))
            self._emit(PROJECT_DIRTY)
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
    # endregion Project State
    # region Plugin Management
    # ================================================================

    @expose
    def list_plugins(self) -> dict:
        """Return all registered plugins with their installation status."""
        return {"success": True, "data": self._plugin_manager.list_plugins()}

    @expose
    def install_plugin(
        self, plugin_id: str, model_id: str = "", mirror: str = "official", no_cache: bool = False
    ) -> dict:
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
                {"id": k, "display_name": v["display_name"]} for k, v in MODEL_MIRRORS.items()
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
        downloaded_models = {mid: self._plugin_manager.is_model_downloaded(mid) for mid in models}

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

    # ================================================================
    # endregion Plugin Management
    # region Settings & Data Management
    # ================================================================

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
        import subprocess as _sp

        from core.paths import get_plugin_data_dir

        path = get_plugin_data_dir()
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                _sp.run(["open", str(path)])
            else:
                _sp.run(["xdg-open", str(path)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def cleanup_tasks_folder(self) -> dict:
        """Clean up old transcription task files (logs and results)."""
        from core.paths import get_plugin_data_dir

        try:
            tasks_dir = Path(get_plugin_data_dir()) / "tasks"
            if not tasks_dir.exists():
                return {"success": True, "data": {"deleted": 0, "message": "No tasks folder found"}}

            deleted = 0
            for f in tasks_dir.iterdir():
                if f.is_file() and (f.suffix in (".log", ".json")):
                    f.unlink()
                    deleted += 1

            return {
                "success": True,
                "data": {"deleted": deleted, "message": f"Cleaned up {deleted} task files"},
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @expose
    def cleanup_transcripts_folder(self) -> dict:
        """Delete all auto-saved transcription SRT files."""
        from core.paths import get_data_dir

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

            logger.info(
                "Cleaned up transcripts folder: {} files, {} bytes freed", deleted, size_freed
            )
            return {"success": True, "data": {"deleted": deleted, "size_freed": size_freed}}
        except Exception as e:
            logger.exception("cleanup_transcripts_folder failed")
            return {"success": False, "error": str(e)}

    @expose
    def update_settings(self, updates: dict) -> dict:
        return self._project.update_settings(updates)

    # ================================================================
    # endregion Settings & Data Management
    # region Export & Encoding
    # ================================================================

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
                capture_output=True,
                text=True,
                timeout=5,
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
                capture_output=True,
                text=True,
                timeout=5,
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
    def check_uv_available(self, force: bool = False) -> dict:
        """Check if uv package manager is available in PATH."""
        if not force and os.environ.get("MILO_FAKE_NO_UV"):
            import time

            time.sleep(0.1)  # avoid pywebview callback race
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
        segments = [s.model_dump() for s in project.active_timeline.transcript.segments]
        edits = [e.model_dump() for e in project.active_timeline.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_edl(segments, edits, media_info, output_path)

    @expose
    def export_xmeml_premiere(self, output_path: str, mode: str = "clean") -> dict:
        """Export xmeml for Premiere Pro."""
        from core.export_timeline import export_xmeml_premiere as _export_xmeml_premiere

        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.active_timeline.transcript.segments]
        edits = [e.model_dump() for e in project.active_timeline.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_xmeml_premiere(segments, edits, media_info, output_path, mode=mode)

    @expose
    def export_otio(
        self,
        output_path: str,
        fade_duration: float = 0.0,
        mode: str = "clean",
        fade_mode: str = "crossfade",
        audio_fade_duration: float | None = None,
    ) -> dict:
        """Export OpenTimelineIO (.otio) file."""
        from core.export_timeline import export_otio as _export_otio

        project = self._project._current
        if not project:
            return {"success": False, "error": "No project open"}
        segments = [s.model_dump() for s in project.active_timeline.transcript.segments]
        edits = [e.model_dump() for e in project.active_timeline.edits]
        media_info = project.media.model_dump() if project.media else {}
        return _export_otio(
            segments,
            edits,
            media_info,
            output_path,
            fade_duration=fade_duration,
            mode=mode,
            fade_mode=fade_mode,
            audio_fade_duration=audio_fade_duration,
        )

    # ================================================================
    # endregion Export & Encoding
    # region Bridge Service callbacks
    # ================================================================

    def _bridge_get_projects(self) -> list[dict]:
        """Callback for BridgeService: return project list."""
        result = self._project.get_recent_projects(limit=100)
        if result.get("success") and result.get("data"):
            return result["data"]
        return []

    def _bridge_get_project(self, name: str) -> dict | None:
        """Callback for BridgeService: get project by name."""
        projects = self._bridge_get_projects()
        for p in projects:
            if p.get("name") == name:
                return self._project.open_project(p["path"])
        return None

    @expose
    def get_bridge_status(self) -> dict:
        """Get bridge HTTP API server status."""
        return {
            "success": True,
            "data": {
                "running": self._bridge_service.is_running,
                "port": self._bridge_service.port,
            },
        }

    # ================================================================
    # endregion Bridge Service
    # region LLM (P0 smart-delete, P1 subtitle correction, P2 highlight, P3 search)
    # ================================================================

    @expose
    def test_llm_connection(self) -> dict:
        """Test LLM connectivity with current settings."""
        from core.llm_service import test_connection

        return test_connection()

    @expose
    def get_llm_config(self) -> dict:
        """Read LLM configuration (API key masked)."""
        from core.llm_service import get_llm_config as _get_cfg

        config = _get_cfg()
        data = config.model_dump()
        if data.get("api_key"):
            key = data["api_key"]
            data["api_key_masked"] = (
                key[:4] + "*" * (len(key) - 8) + key[-4:] if len(key) > 8 else "****"
            )
            data["api_key"] = ""
        return {"success": True, "data": data}

    @expose
    def update_llm_config(self, updates: dict) -> dict:
        """Update LLM settings (only llm_* keys accepted)."""
        allowed = {
            "llm_provider",
            "llm_base_url",
            "llm_api_key",
            "llm_model",
            "llm_temperature",
            "llm_timeout",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed}
        if not filtered:
            return {"success": False, "error": "No valid LLM settings provided"}
        return self.update_settings(filtered)

    @expose
    def get_llm_prompts(self) -> dict:
        """Read all LLM prompt configurations (defaults + user overrides).

        Returns:
            {"success": True, "data": {"defaults": {...}, "overrides": {...}}}
            - defaults: hardcoded default prompts (read-only reference)
            - overrides: user customizations from settings.json
        """
        from core.llm_prompts import DEFAULT_PROMPTS, get_default_params

        defaults = {}
        for key in DEFAULT_PROMPTS:
            defaults[key] = {
                "system": DEFAULT_PROMPTS[key]["system"],
                "params": get_default_params(key),
            }

        settings = self._load_settings_raw()
        overrides = settings.get("llm_prompts", {})

        return {"success": True, "data": {"defaults": defaults, "overrides": overrides}}

    @expose
    def update_llm_prompt(self, func_key: str, updates: dict) -> dict:
        """Update a single LLM prompt configuration.

        Args:
            func_key: One of DEFAULT_PROMPTS keys.
            updates: {"system_override": str|None, "params": {...}}

        Returns:
            {"success": True, "data": {"func_key": str}}
        """
        from core.llm_prompts import DEFAULT_PROMPTS

        if func_key not in DEFAULT_PROMPTS:
            return {"success": False, "error": f"Unknown prompt key: {func_key}"}

        settings = self._load_settings_raw()
        prompts = settings.get("llm_prompts", {})

        # Merge updates into existing override
        existing = prompts.get(func_key, {})
        if "system_override" in updates:
            val = updates["system_override"]
            existing["system_override"] = val if val and val.strip() else None
        if "params" in updates:
            existing["params"] = updates["params"]

        prompts[func_key] = existing
        settings["llm_prompts"] = prompts

        return self.update_settings({"llm_prompts": prompts})

    @expose
    def reset_llm_prompt(self, func_key: str) -> dict:
        """Reset a single LLM prompt to its hardcoded default.

        Args:
            func_key: One of DEFAULT_PROMPTS keys.

        Returns:
            {"success": True, "data": {"func_key": str}}
        """
        from core.llm_prompts import DEFAULT_PROMPTS

        if func_key not in DEFAULT_PROMPTS:
            return {"success": False, "error": f"Unknown prompt key: {func_key}"}

        settings = self._load_settings_raw()
        prompts = settings.get("llm_prompts", {})
        prompts.pop(func_key, None)
        settings["llm_prompts"] = prompts

        return self.update_settings({"llm_prompts": prompts})

    def _load_settings_raw(self) -> dict:
        """Load raw settings dict (internal helper for prompt management)."""
        from core.config import load_settings

        return load_settings()

    def _resolve_timeline_id(self, timeline_id: str) -> str:
        """Resolve a timeline id, falling back to the active timeline.

        Raises ValueError if no project is open.
        """
        if self._project.current is None:
            raise ValueError("No project is open")
        return timeline_id or self._project.current.active_timeline_id

    # ------------------------------------------------------------------
    # LLM prompt presets (v2.1.0 Phase 1: per-feature parameter snapshots)
    # ------------------------------------------------------------------

    @expose
    def get_prompt_presets(self, func_key: str) -> dict:
        """Get the saved preset list for a feature (always includes default).

        Args:
            func_key: One of PRESET_SUPPORTED_KEYS (smart_delete, etc.).

        Returns:
            {"success": True, "data": [preset, ...]}
        """
        from core.llm_presets import PRESET_SUPPORTED_KEYS, get_presets

        if func_key not in PRESET_SUPPORTED_KEYS:
            return {"success": False, "error": f"Unsupported preset key: {func_key}"}

        return {"success": True, "data": get_presets(func_key)}

    @expose
    def save_prompt_preset(
        self,
        func_key: str,
        name: str,
        params: dict | None = None,
        system_override: str = "",
        model: str = "",
    ) -> dict:
        """Save a new preset from the supplied parameters.

        Args:
            func_key: Feature key.
            name: Human-readable preset name.
            params: Simple-mode params snapshot (defaults to empty).
            system_override: Advanced-mode full prompt (empty = simple mode).
            model: Reserved model field (D-73, stored without UI).

        Returns:
            {"success": True, "data": preset}
        """
        from core.llm_presets import PRESET_SUPPORTED_KEYS, save_preset

        if func_key not in PRESET_SUPPORTED_KEYS:
            return {"success": False, "error": f"Unsupported preset key: {func_key}"}
        if not name or not name.strip():
            return {"success": False, "error": "Preset name is required"}

        try:
            preset = save_preset(
                func_key,
                name,
                params or {},
                system_override or "",
                model or "",
            )
        except ValueError as e:
            return {"success": False, "error": str(e)}
        return {"success": True, "data": preset}

    @expose
    def apply_prompt_preset(self, func_key: str, preset_id: str) -> dict:
        """Apply a preset -- writes its params + system_override to llm_prompts.

        Args:
            func_key: Feature key.
            preset_id: Target preset id.

        Returns:
            {"success": True, "data": {"func_key": str, "preset_id": str}}
        """
        from core.llm_presets import PRESET_SUPPORTED_KEYS, apply_preset

        if func_key not in PRESET_SUPPORTED_KEYS:
            return {"success": False, "error": f"Unsupported preset key: {func_key}"}

        try:
            apply_preset(func_key, preset_id)
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}
        return {
            "success": True,
            "data": {"func_key": func_key, "preset_id": preset_id},
        }

    @expose
    def delete_prompt_preset(self, func_key: str, preset_id: str) -> dict:
        """Delete a preset (the built-in default is protected).

        Args:
            func_key: Feature key.
            preset_id: Target preset id.

        Returns:
            {"success": True, "data": {"func_key": str, "preset_id": str}}
        """
        from core.llm_presets import PRESET_SUPPORTED_KEYS, delete_preset

        if func_key not in PRESET_SUPPORTED_KEYS:
            return {"success": False, "error": f"Unsupported preset key: {func_key}"}

        try:
            delete_preset(func_key, preset_id)
        except (KeyError, ValueError) as e:
            return {"success": False, "error": str(e)}
        return {
            "success": True,
            "data": {"func_key": func_key, "preset_id": preset_id},
        }

    # ------------------------------------------------------------------
    # v2.1.0 Phase 2: P1 subtitle correction review @expose methods
    # ------------------------------------------------------------------

    @expose
    def get_subtitle_corrections(self, timeline_id: str = "") -> dict:
        """Get pending P1 corrections for a timeline (parsed detail JSON).

        Args:
            timeline_id: Target timeline (defaults to active).

        Returns:
            {"success": True, "data": [correction, ...]}
        """
        tid = self._resolve_timeline_id(timeline_id)
        return self._project.correction.get_subtitle_corrections(tid)

    @expose
    def compute_diff(self, original: str, corrected: str) -> dict:
        """Compute an inline diff between original and corrected text.

        Returns:
            {"success": True, "data": {"tokens": [{"text", "type"}, ...]}}
        """
        from core.diff_service import compute_inline_diff

        return {"success": True, "data": compute_inline_diff(original, corrected)}

    @expose
    def accept_correction(self, result_id: str) -> dict:
        """Accept one subtitle correction (apply to segment + remove result).

        Returns:
            {"success": True, "data": {"segment_id": str}}
        """
        return self._mark_dirty(self._project.correction.accept_subtitle_correction(result_id))

    @expose
    def reject_correction(self, result_id: str) -> dict:
        """Reject one subtitle correction (remove result, text untouched).

        Returns:
            {"success": True, "data": {"segment_id": str}}
        """
        return self._mark_dirty(self._project.correction.reject_subtitle_correction(result_id))

    @expose
    def accept_high_confidence_corrections(
        self, timeline_id: str = "", threshold: float = 0.8
    ) -> dict:
        """Batch-accept corrections with confidence >= threshold (D-52).

        Args:
            timeline_id: Target timeline (defaults to active).
            threshold: Minimum confidence (default 0.8 per D-68).

        Returns:
            {"success": True, "data": {"accepted_count", "remaining_count"}}
        """
        tid = self._resolve_timeline_id(timeline_id)
        return self._mark_dirty(self._project.correction.accept_high_confidence_corrections(tid, threshold))

    @expose
    def clear_subtitle_corrections(self, timeline_id: str = "") -> dict:
        """Clear all pending P1 corrections for a timeline (D-50).

        Returns:
            {"success": True, "data": {"cleared_count": int}}
        """
        tid = self._resolve_timeline_id(timeline_id)
        return self._mark_dirty(self._project.correction.clear_subtitle_corrections(tid))

    @expose
    def start_smart_delete(self, timeline_id: str = "") -> dict:
        """Start LLM smart-delete analysis as a background task.

        Args:
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True, "data": {"task_id": str}}
        """
        from core.llm_service import get_llm_config as _get_cfg

        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}

        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task(
            "llm_smart_delete",
            {"timeline_id": tl_id},
        )
        return task

    @expose
    def start_subtitle_correction(
        self,
        reference_text: str = "",
        timeline_id: str = "",
        context_window: int = 3,
    ) -> dict:
        """Start LLM subtitle correction as a background task.

        Args:
            reference_text: Optional reference transcript for mode B alignment.
                Empty string = mode A (LLM self-correction).
            timeline_id: Target timeline (defaults to active_timeline_id).
            context_window: Number of adjacent segments for context.

        Returns:
            {"success": True, "data": {"task_id": str}}
        """
        from core.llm_service import get_llm_config as _get_cfg

        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}

        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task(
            "llm_subtitle_correction",
            {
                "timeline_id": tl_id,
                "reference_text": reference_text,
                "context_window": context_window,
            },
        )
        return task

    @expose
    def confirm_all_from_source(self, source: str, min_confidence: float = 0.0) -> dict:
        """Batch-confirm all pending edit decisions from a given source.

        Implements the 'trust this source' feature for reducing user review
        burden when a model's suggestions are trusted.

        Args:
            source: Source filter (e.g. "llm_smart").
            min_confidence: Minimum confidence threshold for auto-confirm.

        Returns:
            {"success": True, "data": {"confirmed_count": int, "project": dict}}
        """
        result = self._project.confirm_all_from_source(source, min_confidence)
        if result["success"]:
            self._emit(PROJECT_DIRTY)
            if self._project.current:
                result["data"]["project"] = self._project.current.model_dump()
        return result

    @expose
    def start_highlight(self, target_duration_minutes: int = 10, timeline_id: str = "") -> dict:
        """Start LLM highlight extraction as a background task.

        Args:
            target_duration_minutes: Target highlight reel duration.
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True, "data": {"task_id": str}}
        """
        from core.llm_service import get_llm_config as _get_cfg

        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}

        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task(
            "llm_highlight",
            {"timeline_id": tl_id, "target_duration_minutes": target_duration_minutes},
        )
        return task

    @expose
    def semantic_search(self, query: str, top_k: int = 5, timeline_id: str = "") -> dict:
        """Run LLM semantic search over transcript segments.

        Args:
            query: Natural language search query.
            top_k: Maximum results to return.
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True, "data": {"results": [...], "query": str}}
        """
        from core.llm_service import get_llm_config as _get_cfg
        from core.llm_service import semantic_search as _search

        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}

        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        project = self._project.current
        tl_id = timeline_id or project.active_timeline_id
        timeline = project.get_timeline(tl_id)
        if timeline is None:
            return {"success": False, "error": f"Timeline {tl_id} not found"}

        segments = [
            s.model_dump()
            for s in timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE
        ]

        # Phase 3: resolve effective prompt
        from core.llm_prompts import get_effective_prompt

        project_prompts = (
            timeline.llm_prompts if hasattr(timeline, "llm_prompts") else None
        )
        effective_prompt = get_effective_prompt("search", project_prompts)

        result = _search(
            query,
            segments,
            top_k=top_k,
            config=config,
            system_prompt=effective_prompt,
        )
        return result

    @expose
    def detect_highlight_jump_cuts(self, timeline_id: str = "") -> dict:
        """Detect jump cuts between highlight segments for export preview.

        Args:
            timeline_id: Target timeline (defaults to active_timeline_id).

        Returns:
            {"success": True, "data": {"jump_cuts": [...]}}
        """
        from core.export_service import detect_jump_cuts

        if self._project.current is None:
            return {"success": False, "error": "No project open"}

        project = self._project.current
        tl_id = timeline_id or project.active_timeline_id
        timeline = project.get_timeline(tl_id)
        if timeline is None:
            return {"success": False, "error": f"Timeline {tl_id} not found"}

        # P0-4: derive highlight ranges from AnalysisResult instead of timeline.edits
        analysis_results = [r for r in timeline.analysis.results if r.type == "llm_highlight"]
        seg_ids: set[str] = set()
        for r in analysis_results:
            seg_ids.update(r.segment_ids)
        seg_map = {s.id: s for s in timeline.transcript.segments if s.type == SegmentType.SUBTITLE}
        ranges = [(seg_map[sid].start, seg_map[sid].end) for sid in seg_ids if sid in seg_map]
        ranges.sort()
        if not ranges:
            return {"success": True, "data": {"jump_cuts": [], "highlight_count": 0}}

        seg_dicts = [{"start": s, "end": e} for s, e in ranges]
        jumps = detect_jump_cuts(seg_dicts)

        return {
            "success": True,
            "data": {
                "jump_cuts": jumps,
                "highlight_count": len(ranges),
                "total_highlight_duration": sum(e - s for s, e in ranges),
            },
        }

    @expose
    def get_file_protocol_status(self) -> dict:
        """Get file protocol bridge status."""
        return {
            "success": True,
            "data": {
                "outgoing_dir": str(self._file_protocol.outgoing_dir),
                "incoming_dir": str(self._file_protocol.incoming_dir),
                "archive_dir": str(self._file_protocol.archive_dir),
                "polling": self._file_protocol._poll_thread is not None
                and self._file_protocol._poll_thread.is_alive(),
            },
        }

    # ================================================================
    # region Workflow (v2.1.0 Phase 3)
    # ================================================================

    @expose
    def get_workflows(self) -> dict:
        """Get all saved workflow definitions."""
        return self._workflow_engine.get_workflows()

    @expose
    def save_workflow(self, name: str, steps: list[dict], workflow_id: str = "") -> dict:
        """Create or update a workflow definition."""
        return self._workflow_engine.save_workflow(name, steps, workflow_id)

    @expose
    def delete_workflow(self, workflow_id: str) -> dict:
        """Delete a workflow definition."""
        return self._workflow_engine.delete_workflow(workflow_id)

    @expose
    def start_workflow(self, workflow_id: str, timeline_id: str = "") -> dict:
        """Start a workflow execution."""
        return self._workflow_engine.start_workflow(workflow_id, timeline_id)

    @expose
    def cancel_workflow(self, mode: str = "immediate") -> dict:
        """Cancel the active workflow (immediate | after_current)."""
        return self._workflow_engine.cancel_workflow(mode)

    @expose
    def handle_step_failure(self, action: str) -> dict:
        """Respond to a workflow step failure (retry | skip | abort)."""
        return self._workflow_engine.handle_step_failure(action)

    @expose
    def get_workflow_status(self) -> dict:
        """Get current workflow execution status."""
        return self._workflow_engine.get_workflow_status()

    @expose
    def detect_workflow_conflicts(self) -> dict:
        """Run conflict detection on the active workflow snapshot."""
        return self._workflow_engine.detect_conflicts()

    @expose
    def resolve_workflow_conflict(self, segment_id: str, resolution: str) -> dict:
        """Resolve a single conflict (keep_first | keep_last | keep_all)."""
        return self._workflow_engine.resolve_conflict(segment_id, resolution)

    @expose
    def apply_workflow(self) -> dict:
        """Apply accumulated workflow edits to the real project."""
        return self._workflow_engine.apply_workflow()

    @expose
    def discard_workflow(self) -> dict:
        """Discard the active workflow without applying."""
        return self._workflow_engine.discard_workflow()

    @expose
    def find_resumable_workflows(self) -> dict:
        """Find workflow snapshots that can be resumed (cross-session recovery)."""
        return {"success": True, "data": self._workflow_engine.find_resumable_snapshots()}

    # ================================================================
    # endregion Workflow


if __name__ == "__main__":
    migrate_if_needed()
    setup_logging()

    api = MiloCutApi()
    setup_frontend_sink(api._emit)

    logger = get_logger()
    logger.info("Milo-Cut starting...")

    # Start bridge HTTP API (localhost only)
    bridge_result = api._bridge_service.start(port=_BRIDGE_DEFAULT_PORT)
    if bridge_result.get("success"):
        logger.info(f"Bridge API on http://127.0.0.1:{bridge_result['data']['port']}")
    else:
        logger.warning(f"Bridge API failed to start: {bridge_result.get('error')}")

    import atexit

    atexit.register(api._bridge_service.stop)
    atexit.register(api._file_protocol.stop_polling)

    # Start file protocol polling for incoming messages from external tools
    api._file_protocol.start_polling()
    logger.info("File protocol polling started")

    app = App(
        api,
        title="Milo-Cut",
        width=1280,
        height=800,
        min_size=(1024, 700),
        frontend_dir="frontend_dist",
    )
    app.run(debug=not getattr(sys, "frozen", False))

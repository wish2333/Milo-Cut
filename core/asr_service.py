"""ASR transcription coordination service.

Main-process side coordination for ASR workflows:
1. Check plugin installation status
2. Ensure model is downloaded
3. Launch subprocess inference via PluginManager.run_in_plugin()
4. Parse results and return to caller
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from core.plugin_manager import PluginManager, PLUGIN_REGISTRY


def transcribe_with_whisper(
    plugin_manager: PluginManager,
    media_path: str,
    ffmpeg_path: str = "",
    model_size: str = "large-v3-turbo",
    language: str = "zh",
    device: str = "cpu",
    compute_type: str = "int8",
    word_timestamps: bool = True,
    vad_filter: bool = True,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run faster-whisper transcription in an isolated subprocess.

    Args:
        plugin_manager: The PluginManager instance.
        media_path: Path to the media file to transcribe.
        ffmpeg_path: Path to ffmpeg (not used by faster-whisper directly, but
            useful for pre-processing if needed in the future).
        model_size: Model size key (e.g., "large-v3-turbo", "base").
        language: Language code (e.g., "zh", "en").
        device: Inference device ("cpu", "cuda", "auto").
        compute_type: Compute precision ("int8", "float16", "float32").
        word_timestamps: Enable word-level timestamps.
        vad_filter: Enable Silero VAD filtering.
        progress_cb: Callback for progress updates.
        cancel_event: Event to signal cancellation.

    Returns:
        dict with transcription results (segments, words, metadata).

    Raises:
        ValueError: If plugin is not installed or model not found.
        RuntimeError: If transcription fails.
    """
    plugin_id = "plugin-whisper"
    plugin_meta = PLUGIN_REGISTRY.get(plugin_id, {})

    # Resolve model ID from size key
    model_id = _resolve_whisper_model(model_size)
    if model_id is None:
        raise ValueError(f"Unknown faster-whisper model size: {model_size}")

    # Check plugin installation
    if not plugin_manager.is_installed(plugin_id):
        raise ValueError(
            f"faster-whisper plugin is not installed. "
            f"Please install it from Settings > AI Engine."
        )

    # Ensure model is downloaded
    if progress_cb:
        progress_cb(2.0, "Checking model availability...")

    model_path = plugin_manager.ensure_model(model_id, progress_cb=progress_cb)

    if progress_cb:
        progress_cb(10.0, "Preparing transcription...")

    # Locate the subprocess script
    script_path = Path(__file__).parent / "asr_scripts" / "whisper_transcribe.py"
    if not script_path.exists():
        raise RuntimeError(f"Transcription script not found: {script_path}")

    # Build subprocess arguments
    args = [
        "--media-path", str(media_path),
        "--model-path", str(model_path),
        "--language", language,
        "--device", device,
        "--compute-type", compute_type,
        "--word-timestamps", str(word_timestamps).lower(),
        "--vad-filter", str(vad_filter).lower(),
    ]

    # Run in isolated subprocess
    if progress_cb:
        progress_cb(15.0, "Starting transcription subprocess...")

    task = plugin_manager.run_in_plugin(
        plugin_id=plugin_id,
        script_path=script_path,
        args=args,
        progress_cb=progress_cb,
        cancel_event=cancel_event,
    )

    # Wait for completion
    while task.state.value in ("pending", "running"):
        if cancel_event and cancel_event.is_set():
            break
        threading.Event().wait(0.5)

    # Check result
    if task.state.value == "cancelled":
        return {"success": False, "error": "Transcription cancelled"}

    if task.state.value == "failed":
        return {"success": False, "error": task.error or "Transcription failed"}

    if task.state.value != "completed":
        return {"success": False, "error": f"Unexpected state: {task.state.value}"}

    # Read result file
    result_path = Path(task.result_path)
    if not result_path.exists():
        return {"success": False, "error": f"Result file not found: {result_path}"}

    try:
        result_data = json.loads(result_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "error": f"Failed to read result: {exc}"}

    return {"success": True, "data": result_data}


def _resolve_whisper_model(model_size: str) -> str | None:
    """Resolve a model size key to a HuggingFace model ID.

    Supports both full model IDs and shorthand size keys:
    - "large-v3-turbo" -> "Systran/faster-whisper-large-v3-turbo"
    - "base" -> "Systran/faster-whisper-base"
    - "Systran/faster-whisper-large-v3-turbo" -> "Systran/faster-whisper-large-v3-turbo"
    """
    # If it's already a full model ID, return as-is
    if "/" in model_size:
        return model_size

    # Look up in plugin registry
    whisper_models = PLUGIN_REGISTRY.get("plugin-whisper", {}).get("models", {})
    for model_id, meta in whisper_models.items():
        # Match by suffix (e.g., "large-v3-turbo" matches "Systran/faster-whisper-large-v3-turbo")
        if model_id.endswith(f"faster-whisper-{model_size}"):
            return model_id

    return None

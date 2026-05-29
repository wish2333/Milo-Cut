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
    vad_threshold: float = 0.5,
    vad_min_silence_ms: int = 500,
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
        vad_threshold: VAD probability threshold (lower = more sensitive).
        vad_min_silence_ms: Minimum silence duration in ms for VAD segmentation.
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
        "--vad-threshold", str(vad_threshold),
        "--vad-min-silence-ms", str(vad_min_silence_ms),
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


def transcribe_with_qwen(
    plugin_manager: PluginManager,
    media_path: str,
    ffmpeg_path: str = "",
    asr_model_size: str = "0.6B",
    aligner_model_size: str = "0.6B",
    language: str = "zh",
    device: str = "cpu",
    compute_type: str = "bfloat16",
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Run Qwen3-ASR transcription in an isolated subprocess.

    Args:
        plugin_manager: The PluginManager instance.
        media_path: Path to the media file to transcribe.
        ffmpeg_path: Path to ffmpeg (used for audio slicing).
        asr_model_size: ASR model size key (e.g., "0.6B", "1.7B").
        aligner_model_size: Aligner model size key (e.g., "0.6B").
        language: Language code (e.g., "zh", "en").
        device: Inference device ("cpu", "cuda").
        compute_type: Compute type for inference (e.g., "bfloat16", "float16", "int8").
        progress_cb: Callback for progress updates.
        cancel_event: Event to signal cancellation.

    Returns:
        dict with transcription results (segments, words, metadata).

    Raises:
        ValueError: If plugin is not installed or model not found.
        RuntimeError: If transcription fails.
    """
    # Determine plugin ID based on device
    plugin_id = "plugin-qwen-gpu" if device == "cuda" else "plugin-qwen-cpu"
    plugin_meta = PLUGIN_REGISTRY.get(plugin_id, {})

    # Resolve model IDs
    asr_model_id = _resolve_qwen_model("asr", asr_model_size)
    aligner_model_id = _resolve_qwen_model("aligner", aligner_model_size)

    if asr_model_id is None:
        raise ValueError(f"Unknown Qwen3-ASR model size: {asr_model_size}")
    if aligner_model_id is None:
        raise ValueError(f"Unknown Qwen3-ForcedAligner model size: {aligner_model_size}")

    # Check plugin installation
    if not plugin_manager.is_installed(plugin_id):
        raise ValueError(
            f"Qwen3-ASR plugin is not installed. "
            f"Please install it from Settings > AI Engine."
        )

    # Ensure models are downloaded
    if progress_cb:
        progress_cb(2.0, "Checking ASR model availability...")

    asr_model_path = plugin_manager.ensure_model(asr_model_id, progress_cb=progress_cb)

    if progress_cb:
        progress_cb(5.0, "Checking aligner model availability...")

    aligner_model_path = plugin_manager.ensure_model(aligner_model_id, progress_cb=progress_cb)

    if progress_cb:
        progress_cb(10.0, "Preparing transcription...")

    # Locate the subprocess script
    script_path = Path(__file__).parent / "asr_scripts" / "qwen_transcribe.py"
    if not script_path.exists():
        raise RuntimeError(f"Transcription script not found: {script_path}")

    # Build subprocess arguments
    args = [
        "--media-path", str(media_path),
        "--asr-model-path", str(asr_model_path),
        "--aligner-model-path", str(aligner_model_path),
        "--language", language,
        "--device", device,
        "--compute-type", compute_type,
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
    - "large-v3-turbo" -> "Purfview/faster-whisper-large-v3-turbo"
    - "base" -> "Systran/faster-whisper-base"
    - "Purfview/faster-whisper-large-v3-turbo" -> "Purfview/faster-whisper-large-v3-turbo"
    """
    # If it's already a full model ID, return as-is
    if "/" in model_size:
        return model_size

    # Look up in plugin registry
    whisper_models = PLUGIN_REGISTRY.get("plugin-whisper", {}).get("models", {})
    for model_id, meta in whisper_models.items():
        # Match by suffix (e.g., "large-v3-turbo" matches "Purfview/faster-whisper-large-v3-turbo")
        if model_id.endswith(f"faster-whisper-{model_size}"):
            return model_id

    return None


def _resolve_qwen_model(model_type: str, model_size: str) -> str | None:
    """Resolve a Qwen model size key to a HuggingFace model ID.

    Args:
        model_type: Either "asr" or "aligner".
        model_size: Size key like "0.6B" or "1.7B".

    Returns:
        Full model ID like "Qwen/Qwen3-ASR-0.6B" or None if not found.
    """
    # If it's already a full model ID, return as-is
    if "/" in model_size:
        return model_size

    # Build the model ID prefix based on type
    if model_type == "asr":
        prefix = "Qwen/Qwen3-ASR-"
    elif model_type == "aligner":
        prefix = "Qwen/Qwen3-ForcedAligner-"
    else:
        return None

    # Look up in plugin registry (check CPU plugin, same models for both)
    qwen_models = PLUGIN_REGISTRY.get("plugin-qwen-cpu", {}).get("models", {})
    for model_id in qwen_models:
        if model_id.startswith(prefix) and model_id.endswith(model_size):
            return model_id

    return None

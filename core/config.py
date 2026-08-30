"""Settings load/save with atomic writes.

Migrated from ff-intelligent-neo core/config.py, adapted for Milo-Cut.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any

from core.logging import get_logger
from core.paths import get_settings_path

logger = get_logger()

_DEFAULT_SETTINGS: dict[str, Any] = {
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "theme": "light",
    "language": "zh-CN",
    "silence_threshold_db": -30,
    "silence_min_duration": 0.5,
    "silence_margin": 0.0,
    "silence_subtitle_padding": 0.0,
    "trim_subtitles_on_silence_overlap": True,
    "export_fade_duration": 0.0,
    "export_transition_mode": "none",
    "export_video_codec": "libx264",
    "export_audio_codec": "aac",
    "export_audio_bitrate": "192k",
    "export_preset": "medium",
    "export_crf": 23,
    "export_resolution": "original",
    "export_ffmpeg_transitions": True,
    "export_ffmpeg_fade_duration": 0,
    "export_ffmpeg_fade_mode": "crossfade",
    # ASR / AI
    "asr_engine": "faster-whisper",
    "asr_model_size": "large-v3-turbo",
    "asr_language": "zh",
    "asr_device": "cpu",
    "asr_vad_filter": True,
    "whisper_compute_type": "int8_float16",
    "whisper_vad_threshold": 0.5,
    "whisper_vad_min_silence_ms": 500,
    "qwen_compute_type": "bfloat16",
    "qwen_language": "auto",
    "duplicate_threshold": 0.85,
    "duplicate_min_length": 5,
    "model_dir": "",
    # Proxy
    "proxy_resolution": "720p",
    "proxy_auto_generate": False,
    # LLM
    "llm_provider": "deepseek",
    "llm_base_url": "",
    "llm_api_key": "",
    "llm_model": "",
    "llm_temperature": 0.1,
    "llm_timeout": 120,
    "llm_thinking_enabled": False,
    # v2.1.1 M2: tunable LLM chunking / batching / concurrency parameters.
    # Batch/overlap control smart-delete + highlight chunking; batch/context
    # control subtitle-correction batching; concurrency enables parallel LLM
    # calls (M3). All have safe defaults so existing behavior is preserved.
    "llm_smart_batch_size": 20,
    "llm_smart_overlap_size": 4,
    "llm_correction_batch_size": 30,
    "llm_correction_context_window": 5,
    "llm_highlight_chunk_duration": 1800.0,
    "llm_highlight_overlap_duration": 60.0,
    "llm_concurrency": 5,
    # v3.0.0 M3-2/M3-4: per-batch char budget (0 = unlimited) and SSRF
    # allowance for local inference endpoints (Ollama etc.)
    "llm_max_batch_chars": 4000,
    "llm_allow_local_urls": False,
    # v3.0.0 M5: layered undo via backend apply_undo (undo.v2). When False
    # the frontend falls back to the legacy full-snapshot undo path.
    "undo_v2": True,
    # Per-provider config cache (v2.1.0): preserves base_url/api_key/model
    # across provider switches so the user never loses what they typed.
    # Structure: {provider_id: {base_url, api_key, model}}
    "llm_provider_configs": {},
    # LLM prompts (Phase 3: parameterized prompt customization)
    "llm_prompts": {},
    # LLM prompt presets (v2.1.0 Phase 1: per-feature saved parameter snapshots)
    "llm_prompt_presets": {},
    # Workflows (v2.1.0 Phase 3: saved workflow definitions, shared across projects)
    "workflows": [],
}


def load_settings() -> dict[str, Any]:
    """Load settings from disk, returning defaults for missing keys.

    Returns a deep copy of the merged settings so callers can freely mutate
    nested values (e.g. ``llm_prompt_presets``) without polluting the module
    level ``_DEFAULT_SETTINGS`` singleton across invocations.
    """
    path = get_settings_path()
    if not path.exists():
        return copy.deepcopy(_DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(_DEFAULT_SETTINGS)
    merged = copy.deepcopy(_DEFAULT_SETTINGS)
    merged.update(data)

    # Audit #10: one-time cleanup of deprecated settings keys
    _DEPRECATED_KEYS = {"llm_smart_window_duration", "llm_smart_overlap_duration"}
    removed = [k for k in _DEPRECATED_KEYS if k in merged]
    if removed:
        for k in removed:
            merged.pop(k, None)
        save_settings(merged)
        logger.info(f"Cleaned deprecated settings keys: {removed}")

    return merged


def save_settings(settings: dict[str, Any]) -> None:
    """Save settings to disk with atomic write."""
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

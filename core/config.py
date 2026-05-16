"""Settings load/save with atomic writes.

Migrated from ff-intelligent-neo core/config.py, adapted for Milo-Cut.
"""

from __future__ import annotations

import json
import os
from typing import Any

from core.paths import get_data_dir, get_settings_path

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
    "filler_words": [
        "嗯", "啊", "呃", "然后", "就是", "那个",
        "怎么说呢", "你知道", "对吧", "其实",
    ],
    "error_trigger_words": [
        "不对", "重来", "重新说", "说错了", "刚才说错了",
        "这段不要", "再来一遍", "算了", "不是这样的",
    ],
}


def load_settings() -> dict[str, Any]:
    """Load settings from disk, returning defaults for missing keys."""
    path = get_settings_path()
    if not path.exists():
        return {**_DEFAULT_SETTINGS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**_DEFAULT_SETTINGS}
    merged = {**_DEFAULT_SETTINGS, **data}
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    """Save settings to disk with atomic write."""
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)

"""Subtitle service: SRT file parsing and manipulation.

Phase 0 implements SRT import. Other formats (VTT, ASS) are P1+.
"""

from __future__ import annotations

import re
from pathlib import Path

from loguru import logger

from core.models import Segment, SegmentType


def parse_srt(file_path: str) -> dict:
    """Parse an SRT subtitle file into a list of segments.

    Returns {"success": True, "data": [Segment, ...]} or {"success": False, "error": ...}.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        if path.suffix.lower() not in (".srt",):
            return {"success": False, "error": f"Unsupported format: {path.suffix}"}

        content = path.read_text(encoding="utf-8-sig")
        blocks = re.split(r"\n\s*\n", content.strip())
        segments: list[dict] = []

        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue

            # Parse timestamp line: "00:01:23,456 --> 00:01:25,789"
            ts_match = re.match(
                r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
                lines[1].strip(),
            )
            if not ts_match:
                continue

            g = ts_match.groups()
            start = _timestamp_to_seconds(g[0], g[1], g[2], g[3])
            end = _timestamp_to_seconds(g[4], g[5], g[6], g[7])
            text = "\n".join(lines[2:]).strip()

            segments.append({
                "id": f"seg-{len(segments) + 1:04d}",
                "type": SegmentType.SUBTITLE,
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
            })

        logger.info("Parsed {} segments from {}", len(segments), file_path)
        return {"success": True, "data": segments}

    except Exception as e:
        logger.exception("parse_srt failed for {}", file_path)
        return {"success": False, "error": str(e)}


def _timestamp_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    """Convert SRT timestamp components to seconds."""
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

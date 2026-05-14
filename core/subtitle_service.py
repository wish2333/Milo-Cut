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


def validate_srt(file_path: str, video_duration: float = 0.0) -> dict:
    """Validate an SRT file for structural correctness.

    Checks: file readable (utf-8-sig/gb18030/latin-1), index continuity,
    start < end, no overlapping timestamps, duration mismatch >10% vs video.

    Returns {"success": True, "data": {"issues": [...], "warning_count": N, "error_count": M}}.
    """
    issues: list[dict] = []
    path = Path(file_path)

    if not path.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    # Try multiple encodings
    content: str | None = None
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            content = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, OSError):
            continue
    if content is None:
        return {"success": False, "error": "Unable to read file with any supported encoding"}

    blocks = re.split(r"\n\s*\n", content.strip())
    entries: list[tuple[int, float, float]] = []

    for block_idx, block in enumerate(blocks):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            issues.append({"level": "error", "message": f"Block {block_idx + 1}: insufficient lines"})
            continue

        # Parse index
        try:
            index = int(lines[0].strip())
        except ValueError:
            issues.append({"level": "error", "message": f"Block {block_idx + 1}: invalid index '{lines[0].strip()}'"})
            continue

        # Parse timestamp
        ts_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip(),
        )
        if not ts_match:
            issues.append({"level": "error", "message": f"Block {block_idx + 1}: invalid timestamp format"})
            continue

        g = ts_match.groups()
        start = _timestamp_to_seconds(g[0], g[1], g[2], g[3])
        end = _timestamp_to_seconds(g[4], g[5], g[6], g[7])

        if start >= end:
            issues.append({"level": "error", "message": f"Block {block_idx + 1} (idx {index}): start >= end"})

        entries.append((index, start, end))

    # Check index continuity
    for i, (idx, _, _) in enumerate(entries):
        expected = i + 1
        if idx != expected:
            issues.append({"level": "warning", "message": f"Index gap: expected {expected}, got {idx}"})

    # Check overlapping timestamps
    for i in range(1, len(entries)):
        prev_end = entries[i - 1][2]
        curr_start = entries[i][1]
        if curr_start < prev_end - 0.001:
            issues.append({
                "level": "warning",
                "message": f"Overlap between entry {entries[i - 1][0]} and {entries[i][0]}",
            })

    # Check duration mismatch
    if video_duration > 0 and entries:
        last_end = entries[-1][2]
        mismatch = abs(last_end - video_duration) / video_duration
        if mismatch > 0.10:
            issues.append({
                "level": "warning",
                "message": f"Duration mismatch: SRT ends at {last_end:.1f}s, video is {video_duration:.1f}s ({mismatch:.0%})",
            })

    warning_count = sum(1 for i in issues if i["level"] == "warning")
    error_count = sum(1 for i in issues if i["level"] == "error")

    return {
        "success": True,
        "data": {
            "issues": issues,
            "warning_count": warning_count,
            "error_count": error_count,
        },
    }

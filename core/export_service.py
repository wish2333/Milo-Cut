"""Export service: FFmpeg-based video and SRT export.

Exports cut video by extracting keep-ranges (non-deleted segments) and
concatenating them via FFmpeg. Also exports SRT with adjusted timestamps.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from loguru import logger

from core.ffmpeg_service import _find_ffmpeg
from core.paths import get_temp_dir


def _validate_output_path(output_path: str) -> str:
    """Validate and normalize an output file path."""
    p = Path(output_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Export cut video by keeping non-deleted ranges.

    Steps:
    1. Collect confirmed deletions from edits
    2. Compute keep-ranges (inverse of deletions)
    3. Extract each keep-range as .ts segment via FFmpeg
    4. Concat all segments via FFmpeg concat demuxer
    """
    try:
        output_path = _validate_output_path(output_path)
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits)

        # Detect if input has video stream
        has_video = True
        if media_info:
            has_video = media_info.get("width", 0) > 0

        if not deletions:
            logger.info("No confirmed deletions, copying original file")
            import shutil
            shutil.copy2(media_path, output_path)
            if progress_callback:
                progress_callback(100.0, "Done (no cuts)")
            return {"success": True, "data": {"path": output_path}}

        keep_ranges = _compute_keep_ranges(total_duration, deletions)
        if not keep_ranges:
            return {"success": False, "error": "Nothing to export after applying all cuts"}

        temp_dir = get_temp_dir()
        seg_paths: list[str] = []
        total_segments = len(keep_ranges)

        for i, (start, end) in enumerate(keep_ranges):
            if cancel_event and cancel_event.is_set():
                _cleanup_files(seg_paths)
                return {"success": False, "error": "Cancelled"}

            seg_path = str(temp_dir / f"seg_{i:04d}.ts")
            if progress_callback:
                pct = (i / total_segments) * 80.0
                progress_callback(pct, f"Extracting segment {i + 1}/{total_segments}")

            _extract_segment(ffmpeg, media_path, start, end, seg_path, has_video=has_video)
            seg_paths.append(seg_path)

        concat_list = str(temp_dir / "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in seg_paths:
                escaped = p.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        if progress_callback:
            progress_callback(85.0, "Concatenating segments...")
        _concat_segments(ffmpeg, concat_list, output_path)

        _cleanup_files(seg_paths + [concat_list])

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        if progress_callback:
            progress_callback(100.0, "Export complete")

        logger.info("Exported video to {} ({} bytes)", output_path, file_size)
        return {"success": True, "data": {"path": output_path, "size": file_size}}

    except Exception as e:
        logger.exception("export_video failed")
        return {"success": False, "error": str(e)}


def export_audio(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Export cut audio by keeping non-deleted ranges.

    Steps:
    1. Collect confirmed deletions from edits
    2. Compute keep-ranges (inverse of deletions)
    3. Extract each keep-range as audio segment via FFmpeg
    4. Concat all segments via FFmpeg concat demuxer
    """
    try:
        output_path = _validate_output_path(output_path)
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits)

        if not deletions:
            logger.info("No confirmed deletions, copying original audio")
            import shutil
            shutil.copy2(media_path, output_path)
            if progress_callback:
                progress_callback(100.0, "Done (no cuts)")
            return {"success": True, "data": {"path": output_path}}

        keep_ranges = _compute_keep_ranges(total_duration, deletions)
        if not keep_ranges:
            return {"success": False, "error": "Nothing to export after applying all cuts"}

        temp_dir = get_temp_dir()
        seg_paths: list[str] = []
        total_segments = len(keep_ranges)

        for i, (start, end) in enumerate(keep_ranges):
            if cancel_event and cancel_event.is_set():
                _cleanup_files(seg_paths)
                return {"success": False, "error": "Cancelled"}

            seg_path = str(temp_dir / f"audio_seg_{i:04d}.ts")
            if progress_callback:
                pct = (i / total_segments) * 80.0
                progress_callback(pct, f"Extracting segment {i + 1}/{total_segments}")

            _extract_segment(ffmpeg, media_path, start, end, seg_path, has_video=False)
            seg_paths.append(seg_path)

        concat_list = str(temp_dir / "audio_concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in seg_paths:
                escaped = p.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        if progress_callback:
            progress_callback(85.0, "Concatenating segments...")
        _concat_segments(ffmpeg, concat_list, output_path)

        _cleanup_files(seg_paths + [concat_list])

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        if progress_callback:
            progress_callback(100.0, "Export complete")

        logger.info("Exported audio to {} ({} bytes)", output_path, file_size)
        return {"success": True, "data": {"path": output_path, "size": file_size}}

    except Exception as e:
        logger.exception("export_audio failed")
        return {"success": False, "error": str(e)}


def export_srt(
    segments: list[dict],
    edits: list[dict],
    output_path: str,
) -> dict:
    """Export SRT with only kept subtitle segments and adjusted timestamps."""
    try:
        output_path = _validate_output_path(output_path)
        deletions = _get_confirmed_deletions(edits)
        subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

        kept: list[dict] = []
        for seg in subtitle_segs:
            if not _overlaps_deletions(seg["start"], seg["end"], deletions):
                kept.append(seg)

        kept.sort(key=lambda s: s["start"])

        cumulative_offset = 0.0
        del_idx = 0
        adjusted: list[tuple[float, float, str]] = []

        for seg in kept:
            seg_start = seg["start"]
            seg_end = seg["end"]

            while del_idx < len(deletions) and deletions[del_idx][1] <= seg_start:
                cumulative_offset += deletions[del_idx][1] - deletions[del_idx][0]
                del_idx += 1

            new_start = max(0.0, seg_start - cumulative_offset)
            new_end = max(0.0, seg_end - cumulative_offset)
            adjusted.append((new_start, new_end, seg.get("text", "")))

        with open(output_path, "w", encoding="utf-8") as f:
            for idx, (start, end, text) in enumerate(adjusted, 1):
                f.write(f"{idx}\n")
                f.write(f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n")
                f.write(f"{text}\n\n")

        logger.info("Exported {} subtitle segments to {}", len(adjusted), output_path)
        return {"success": True, "data": {"path": output_path, "segment_count": len(adjusted)}}

    except Exception as e:
        logger.exception("export_srt failed")
        return {"success": False, "error": str(e)}


# ================================================================
# Helpers
# ================================================================

def _get_confirmed_deletions(edits: list[dict]) -> list[tuple[float, float]]:
    """Extract confirmed deletion ranges from edit decisions."""
    result = []
    for edit in edits:
        if (edit.get("action") == "delete"
                and edit.get("status") == "confirmed"):
            result.append((edit["start"], edit["end"]))
    result.sort(key=lambda x: x[0])
    return result


def _get_media_duration(segments: list[dict], edits: list[dict]) -> float:
    """Compute total media duration from segments and edits."""
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    return max(all_times) if all_times else 0.0


def _compute_keep_ranges(
    total_duration: float,
    deletions: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Subtract deletion ranges from full timeline to get keep ranges."""
    if not deletions:
        return [(0.0, total_duration)]

    merged = _merge_ranges(deletions)
    keep: list[tuple[float, float]] = []
    current = 0.0

    for del_start, del_end in merged:
        if current < del_start:
            keep.append((current, del_start))
        current = max(current, del_end)

    if current < total_duration:
        keep.append((current, total_duration))

    return keep


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping ranges."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlaps_deletions(
    start: float,
    end: float,
    deletions: list[tuple[float, float]],
) -> bool:
    """Check if a range overlaps significantly with any deletion range."""
    for del_start, del_end in deletions:
        overlap_start = max(start, del_start)
        overlap_end = min(end, del_end)
        if overlap_end - overlap_start > 0.01:
            return True
    return False


def _extract_segment(
    ffmpeg: str,
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    has_video: bool = True,
) -> None:
    """Extract a single segment as MPEG-TS via FFmpeg re-encode."""
    duration = end - start
    base = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-avoid_negative_ts", "make_zero",
    ]
    if has_video:
        codec_args = ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
    else:
        codec_args = ["-c:a", "aac", "-vn"]
    cmd = base + codec_args + [output_path]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment extraction failed: {result.stderr[-500:]}")


def _concat_segments(
    ffmpeg: str,
    concat_list: str,
    output_path: str,
) -> None:
    """Concatenate .ts segments via FFmpeg concat demuxer."""
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-500:]}")


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000)) % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _cleanup_files(paths: list[str]) -> None:
    """Remove temporary files."""
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass

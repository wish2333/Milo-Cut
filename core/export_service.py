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
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    preset: str = "fast",
    crf: int = 23,
    resolution: str = "original",
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
        media_duration = media_info.get("duration", 0.0) if media_info else 0.0
        if media_duration <= 0.0:
            logger.warning("media_duration unavailable ({}), export may be truncated", media_duration)
        total_duration = _get_media_duration(segments, edits, media_duration)

        has_video = False
        if media_info:
            has_video = media_info.get("width", 0) > 0

        # Safety: detect audio-only files by extension regardless of media_info
        _audio_exts = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a", ".wma", ".opus"}
        if has_video and Path(media_path).suffix.lower() in _audio_exts:
            logger.warning("export_video: media_info reports width={} but file is audio-only ({}), forcing has_video=False",
                           media_info.get("width", 0) if media_info else 0, Path(media_path).suffix)
            has_video = False

        logger.info("export_video: has_video={}, media_path={}, width={}",
                     has_video, media_path,
                     media_info.get("width", 0) if media_info else "N/A")

        if not deletions:
            logger.info("No confirmed deletions, copying original file")
            import shutil
            shutil.copy2(media_path, output_path)
            if progress_callback:
                progress_callback(100.0, "Done (no cuts)")
            return {"success": True, "data": {"path": output_path}}

        keep_ranges = _compute_keep_ranges(total_duration, deletions)
        logger.info("export_video: media_duration={}, total_duration={}, deletions={}, keep_ranges={}", media_duration, total_duration, len(deletions), keep_ranges)
        if not keep_ranges:
            return {"success": False, "error": "Nothing to export after applying all cuts"}

        temp_dir = get_temp_dir()

        if not has_video:
            # No video stream: delegate to export_audio (proven to work)
            # Use .m4a extension for proper AAC container (WAV+AAC is broken)
            out = Path(output_path)
            if out.suffix.lower() == ".wav":
                output_path = str(out.with_suffix(".m4a"))
            return export_audio(
                media_path, segments, edits, output_path,
                media_info=media_info,
                progress_callback=progress_callback,
                cancel_event=cancel_event,
            )

        # Video+audio: single-pass filter_complex
        # Video: select keeps frames in desired time ranges, setpts resets timestamps
        # Audio: asplit+atrim+concat (proven approach)
        filter_complex = _build_video_trim_filter(keep_ranges)
        filter_path = str(temp_dir / "video_filter.txt")
        with open(filter_path, "w", encoding="utf-8") as f:
            f.write(filter_complex)

        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}

        if progress_callback:
            progress_callback(20.0, "Exporting video...")

        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-i", media_path,
            "-filter_complex_script", filter_path,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", video_codec,
            "-preset", preset,
            "-crf", str(crf),
            "-c:a", audio_codec,
            "-b:a", audio_bitrate,
        ]
        # Add scale filter if resolution is not original
        if resolution and resolution != "original":
            cmd.extend(["-vf", f"scale={resolution.replace('x', ':')}"])
        cmd.append(output_path)
        logger.info("export_video: filter_complex length={}, written to {}", len(filter_complex), filter_path)
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg video export failed: {result.stderr[-500:]}")

        _cleanup_files([filter_path])

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
    media_info: dict | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Export cut audio by keeping non-deleted ranges.

    Uses FFmpeg filter_complex (atrim + concat) for sample-accurate cutting
    in a single pass, avoiding timing drift from per-segment AAC encoding.
    """
    try:
        output_path = _validate_output_path(output_path)
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        media_duration = media_info.get("duration", 0.0) if media_info else 0.0
        if media_duration <= 0.0:
            logger.warning("media_duration unavailable ({}), export may be truncated", media_duration)
        total_duration = _get_media_duration(segments, edits, media_duration)

        if not deletions:
            logger.info("No confirmed deletions, copying original audio")
            import shutil
            shutil.copy2(media_path, output_path)
            if progress_callback:
                progress_callback(100.0, "Done (no cuts)")
            return {"success": True, "data": {"path": output_path}}

        keep_ranges = _compute_keep_ranges(total_duration, deletions)
        logger.info("export_audio: media_duration={}, total_duration={}, deletions={}, keep_ranges={}", media_duration, total_duration, len(deletions), keep_ranges)
        if not keep_ranges:
            return {"success": False, "error": "Nothing to export after applying all cuts"}

        if progress_callback:
            progress_callback(10.0, "Exporting audio...")

        filter_complex = _build_audio_trim_filter(keep_ranges)

        temp_dir = get_temp_dir()
        filter_path = str(temp_dir / "audio_filter.txt")
        with open(filter_path, "w", encoding="utf-8") as f:
            f.write(filter_complex)

        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-i", media_path,
            "-filter_complex_script", filter_path,
            "-map", "[out]",
            "-c:a", "aac",
            output_path,
        ]
        logger.info("export_audio: filter_complex length={}, written to {}", len(filter_complex), filter_path)
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio export failed: {result.stderr[-500:]}")

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        _cleanup_files([filter_path])
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
    *,
    media_duration: float = 0.0,
) -> dict:
    """Export SRT with only kept subtitle segments and adjusted timestamps."""
    try:
        output_path = _validate_output_path(output_path)
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits, media_duration)
        keep_ranges = _compute_keep_ranges(total_duration, deletions)

        subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]
        logger.info("export_srt: media_duration={}, total_duration={}, deletions={}, keep_ranges={}, total_subtitle_segs={}", media_duration, total_duration, len(deletions), keep_ranges, len(subtitle_segs))

        kept: list[dict] = []
        lost: list[dict] = []
        for seg in subtitle_segs:
            if _subtitle_survives_in_keep_ranges(seg["start"], seg["end"], keep_ranges):
                kept.append(seg)
            else:
                lost.append(seg)
        if lost:
            logger.warning("export_srt: {} subtitles lost (not in keep_ranges): {}", len(lost), [(s["start"], s["end"], s.get("text", "")[:30]) for s in lost])

        kept.sort(key=lambda s: s["start"])

        adjusted: list[tuple[float, float, str]] = []
        for seg in kept:
            new_start, new_end = _map_to_exported_timeline(
                seg["start"], seg["end"], keep_ranges,
            )
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


def _get_media_duration(
    segments: list[dict],
    edits: list[dict],
    media_duration: float = 0.0,
) -> float:
    """Compute total media duration from segments, edits, and optionally the actual media file duration.

    Uses the larger of the computed duration (from segments/edits) and the actual
    media file duration from ffprobe, so the export is never truncated by a gap
    after the last subtitle segment.
    """
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    computed = max(all_times) if all_times else 0.0
    return max(computed, media_duration)


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

    # Clamp to prevent segment/edit endpoints exceeding actual media duration
    return [(min(s, total_duration), min(e, total_duration)) for s, e in keep]


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


def _build_audio_trim_filter(
    keep_ranges: list[tuple[float, float]],
) -> str:
    """Build FFmpeg filter_complex string for sample-accurate audio trimming.

    Uses asplit to explicitly duplicate the input stream, then atrim+asetpts
    per keep range, and finally concatenates them.
    """
    n = len(keep_ranges)
    parts: list[str] = []
    if n == 1:
        start, end = keep_ranges[0]
        parts.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[out]"
        )
    else:
        split_outputs = "".join(f"[s{i}]" for i in range(n))
        parts.append(f"[0:a]asplit={n}{split_outputs}")
        for i, (start, end) in enumerate(keep_ranges):
            parts.append(
                f"[s{i}]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{i}]"
            )
        concat_inputs = "".join(f"[a{i}]" for i in range(n))
        parts.append(
            f"{concat_inputs}concat=n={n}:v=0:a=1[out]"
        )
    return ";".join(parts)


def _build_video_trim_filter(
    keep_ranges: list[tuple[float, float]],
    *,
    has_video: bool = True,
) -> str:
    """Build FFmpeg filter_complex for single-pass video+audio trimming.

    Uses split/asplit to duplicate streams, then trim/atrim per keep range,
    and finally concat.  Each filter is simple (no complex expressions),
    avoiding memory issues with large keep_range counts.
    """
    n = len(keep_ranges)
    parts: list[str] = []

    if has_video:
        if n == 1:
            s, e = keep_ranges[0]
            parts.append(f"[0:v]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v0]")
            parts.append(f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a0]")
            parts.append("[v0][a0]concat=n=1:v=1:a=1[outv][outa]")
        else:
            v_splits = "".join(f"[sv{i}]" for i in range(n))
            a_splits = "".join(f"[sa{i}]" for i in range(n))
            parts.append(f"[0:v]split={n}{v_splits}")
            parts.append(f"[0:a]asplit={n}{a_splits}")
            for i, (s, e) in enumerate(keep_ranges):
                parts.append(f"[sv{i}]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]")
                parts.append(f"[sa{i}]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]")
            # concat expects interleaved: [v0][a0][v1][a1]...
            interleaved = "".join(f"[v{i}][a{i}]" for i in range(n))
            parts.append(f"{interleaved}concat=n={n}:v=1:a=1[outv][outa]")
    else:
        if n == 1:
            s, e = keep_ranges[0]
            parts.append(f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[out]")
        else:
            a_splits = "".join(f"[s{i}]" for i in range(n))
            parts.append(f"[0:a]asplit={n}{a_splits}")
            for i, (s, e) in enumerate(keep_ranges):
                parts.append(f"[s{i}]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]")
            a_inputs = "".join(f"[a{i}]" for i in range(n))
            parts.append(f"{a_inputs}concat=n={n}:v=0:a=1[out]")

    return ";".join(parts)


def _map_to_exported_timeline(
    seg_start: float,
    seg_end: float,
    keep_ranges: list[tuple[float, float]],
) -> tuple[float, float]:
    """Map original timeline position to exported timeline via keep_ranges.

    The exported audio is a concatenation of keep_ranges.  Each keep range
    [ks, ke] occupies (ke - ks) seconds in the exported file.  This function
    finds where a subtitle's overlap with the keep_ranges falls in the
    exported timeline, clipping to the keep range boundaries.
    """
    exported_start: float | None = None
    exported_end: float | None = None
    cumulative = 0.0

    for ks, ke in keep_ranges:
        overlap_start = max(seg_start, ks)
        overlap_end = min(seg_end, ke)
        if overlap_start < overlap_end:
            if exported_start is None:
                exported_start = cumulative + (overlap_start - ks)
            exported_end = cumulative + (overlap_end - ks)
        cumulative += ke - ks

    if exported_start is None:
        return (seg_start, seg_end)
    return (exported_start, exported_end)


def _subtitle_survives_in_keep_ranges(
    seg_start: float,
    seg_end: float,
    keep_ranges: list[tuple[float, float]],
    min_keep: float = 0.3,
) -> bool:
    """Return True if the subtitle segment has enough content preserved.

    For subtitles longer than `min_keep`, at least `min_keep` seconds must
    survive in the keep_ranges.  For shorter subtitles the threshold is
    lowered to 50% of the segment duration, so that brief but completely
    intact subtitles are not silently dropped.
    """
    seg_duration = seg_end - seg_start
    effective_min = min(min_keep, seg_duration * 0.5)
    for ks, ke in keep_ranges:
        overlap = max(0.0, min(seg_end, ke) - max(seg_start, ks))
        if overlap >= effective_min:
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
    *,
    reencode_audio: bool = False,
) -> None:
    """Concatenate .ts segments via FFmpeg concat demuxer."""
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
    ]
    if reencode_audio:
        cmd += ["-af", "aresample=async=1000", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]
    cmd.append(output_path)
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

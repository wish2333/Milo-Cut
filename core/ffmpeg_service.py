"""FFmpeg service: media probing and silence detection.

Simplified for Phase 0 -- only probe and silence detection via FFmpeg filters.
Full command builder from ff-intelligent-neo will be migrated in later phases.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from loguru import logger


def _find_ffprobe() -> str:
    """Find ffprobe binary on PATH."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FileNotFoundError("ffprobe not found on PATH")
    return ffprobe


def _find_ffmpeg() -> str:
    """Find ffmpeg binary on PATH."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg not found on PATH")
    return ffmpeg


def probe_media(file_path: str) -> dict:
    """Probe a media file and return structured metadata.

    Returns {"success": True, "data": {...}} or {"success": False, "error": ...}.
    """
    try:
        ffprobe = _find_ffprobe()
        cmd = [
            ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {"success": False, "error": f"ffprobe exited with code {result.returncode}"}

        info = json.loads(result.stdout)
        format_info = info.get("format", {})
        streams = info.get("streams", [])

        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        duration = float(format_info.get("duration", 0))
        width = int(video_stream.get("width", 0)) if video_stream else 0
        height = int(video_stream.get("height", 0)) if video_stream else 0
        fps = 0.0
        if video_stream:
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = r_frame_rate.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 0.0
            except (ValueError, ZeroDivisionError):
                fps = 0.0

        data = {
            "path": file_path,
            "duration": round(duration, 3),
            "format": format_info.get("format_name", ""),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "audio_channels": int(audio_stream.get("channels", 0)) if audio_stream else 0,
            "sample_rate": int(audio_stream.get("sample_rate", 0)) if audio_stream else 0,
            "bit_rate": int(format_info.get("bit_rate", 0)),
        }
        return {"success": True, "data": data}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("probe_media failed")
        return {"success": False, "error": str(e)}


def detect_silence(
    file_path: str,
    threshold_db: float = -30.0,
    min_duration: float = 0.5,
) -> dict:
    """Detect silent segments using FFmpeg silencedetect filter.

    Returns {"success": True, "data": [{"start": float, "end": float, "duration": float}, ...]}
    or {"success": False, "error": ...}.
    """
    try:
        ffmpeg = _find_ffmpeg()
        cmd = [
            ffmpeg,
            "-i", file_path,
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null",
            "-",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=300,
            encoding="utf-8", errors="replace",
        )
        output = result.stderr

        silences: list[dict[str, float]] = []
        starts: list[float] = []

        for line in output.splitlines():
            line = line.strip()
            if "silence_start:" in line:
                try:
                    val = line.split("silence_start:")[1].strip().split()[0]
                    starts.append(float(val))
                except (ValueError, IndexError):
                    continue
            elif "silence_end:" in line:
                try:
                    parts = line.split("silence_end:")[1].strip()
                    end_val = float(parts.split()[0])
                    if starts:
                        start = starts.pop(0)
                        silences.append({
                            "start": round(start, 3),
                            "end": round(end_val, 3),
                            "duration": round(end_val - start, 3),
                        })
                except (ValueError, IndexError):
                    continue

        return {"success": True, "data": silences}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("detect_silence failed")
        return {"success": False, "error": str(e)}

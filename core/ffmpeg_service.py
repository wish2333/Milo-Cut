"""FFmpeg service: media probing and silence detection.

Simplified for Phase 0 -- only probe and silence detection via FFmpeg filters.
Full command builder from ff-intelligent-neo will be migrated in later phases.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

_SUBPROCESS_KWARGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32"
    else {"start_new_session": True}
)

from loguru import logger


def _get_settings_ffmpeg_path() -> str | None:
    """Read user-configured ffmpeg path from settings."""
    try:
        from core.config import load_settings
        settings = load_settings()
        path = settings.get("ffmpeg_path", "")
        if path and Path(path).is_file():
            return path
    except Exception as e:
        logger.debug("Failed to read ffmpeg_path from settings: {}", e)
    return None


def _get_settings_ffprobe_path() -> str | None:
    """Read user-configured ffprobe path from settings."""
    try:
        from core.config import load_settings
        settings = load_settings()
        path = settings.get("ffprobe_path", "")
        if path and Path(path).is_file():
            return path
    except Exception as e:
        logger.debug("Failed to read ffprobe_path from settings: {}", e)
    return None


def _find_ffprobe() -> str:
    """Find ffprobe binary with priority chain.

    Priority: user settings > PATH > static_ffmpeg
    """
    # 1. User-configured path
    custom = _get_settings_ffprobe_path()
    if custom:
        return custom
    # 2. PATH lookup
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    # 3. static_ffmpeg package
    try:
        import static_ffmpeg
        paths = static_ffmpeg.utils.get_or_fetch_platform_executables_else_raise()
        return paths[1]  # ffprobe is second
    except Exception as e:
        logger.debug("static_ffmpeg fallback for ffprobe failed: {}", e)
    raise FileNotFoundError("ffprobe not found. Configure path in Settings or install FFmpeg.")


def _find_ffmpeg() -> str:
    """Find ffmpeg binary with priority chain.

    Priority: user settings > PATH > static_ffmpeg
    """
    # 1. User-configured path
    custom = _get_settings_ffmpeg_path()
    if custom:
        return custom
    # 2. PATH lookup
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # 3. static_ffmpeg package
    try:
        import static_ffmpeg
        paths = static_ffmpeg.utils.get_or_fetch_platform_executables_else_raise()
        return paths[0]  # ffmpeg is first
    except Exception as e:
        logger.debug("static_ffmpeg fallback for ffmpeg failed: {}", e)
    raise FileNotFoundError("ffmpeg not found. Configure path in Settings or install FFmpeg.")


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
            **_SUBPROCESS_KWARGS,
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

        pix_fmt = video_stream.get("pix_fmt", "") if video_stream else ""

        data = {
            "path": file_path,
            "duration": round(duration, 3),
            "format": format_info.get("format_name", ""),
            "width": width,
            "height": height,
            "fps": round(fps, 3),
            "pix_fmt": pix_fmt,
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
            **_SUBPROCESS_KWARGS,
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


def generate_waveform(
    file_path: str,
    duration: float,
    output_path: str,
    buckets_per_second: int = 100,
) -> dict:
    """Generate waveform peak data from a media file.

    Extracts raw PCM audio via ffmpeg, computes min/max peaks per bucket,
    and writes the result as JSON.

    Returns {"success": True, "data": {"path": output_path, "buckets": N}}
    or {"success": False, "error": ...}.
    """
    try:
        ffmpeg = _find_ffmpeg()
        total_buckets = max(1, int(duration * buckets_per_second))

        # Extract mono f32le audio at 8kHz to reduce data volume
        cmd = [
            ffmpeg, "-hide_banner", "-y",
            "-i", file_path,
            "-f", "f32le",
            "-ac", "1",
            "-ar", "8000",
            "-vn",
            "pipe:1",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=300,
            **_SUBPROCESS_KWARGS,
        )
        if result.returncode != 0:
            return {"success": False, "error": f"ffmpeg exited with code {result.returncode}"}

        import struct
        raw = result.stdout
        sample_count = len(raw) // 4  # 4 bytes per f32
        if sample_count == 0:
            return {"success": False, "error": "No audio samples extracted"}

        samples = struct.unpack(f"<{sample_count}f", raw)

        # Compute samples per bucket
        samples_per_bucket = max(1, sample_count // total_buckets)

        peaks: list[dict[str, float]] = []
        for i in range(total_buckets):
            start_idx = i * samples_per_bucket
            end_idx = min(start_idx + samples_per_bucket, sample_count)
            if start_idx >= sample_count:
                peaks.append({"min": 0.0, "max": 0.0})
                continue

            chunk = samples[start_idx:end_idx]
            bucket_min = min(chunk)
            bucket_max = max(chunk)
            # Clamp to [-1, 1]
            peaks.append({
                "min": max(-1.0, min(1.0, bucket_min)),
                "max": max(-1.0, min(1.0, bucket_max)),
            })

        # Write JSON
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(peaks, f)

        logger.info("Generated waveform: {} buckets -> {}", len(peaks), output_path)
        return {"success": True, "data": {"path": output_path, "buckets": len(peaks)}}

    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.exception("generate_waveform failed")
        return {"success": False, "error": str(e)}


def generate_proxy(
    media_path: str,
    output_path: str,
    resolution: str = "720p",
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Generate proxy file at specified resolution.

    Args:
        media_path: Path to source video
        output_path: Path for proxy output
        resolution: Target resolution (e.g., "720p", "480p")
        progress_cb: Optional progress callback(percent, message)
        cancel_event: Optional cancellation event

    Returns:
        Path to generated proxy file
    """
    ffmpeg = _find_ffmpeg()

    # Parse resolution
    height = int(resolution.replace("p", ""))

    cmd = [
        ffmpeg, "-y",
        "-i", media_path,
        "-vf", f"scale=-2:{height}",
        "-c:v", "libx264", "-crf", "28",
        "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info("Generating proxy: {} -> {} ({})", media_path, output_path, resolution)
    subprocess.run(cmd, check=True, **_SUBPROCESS_KWARGS)
    logger.info("Proxy generated: {}", output_path)

    return output_path

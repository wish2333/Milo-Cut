"""FFmpeg encoder presets and quality configuration.

Single source of truth for encoder-specific parameters, quality modes,
fallback chains, and pixel format selection. Referenced by export_service.py
and main.py to generate correct FFmpeg arguments for each codec.
"""

from __future__ import annotations

import subprocess
import sys

from loguru import logger

_SUBPROCESS_KWARGS: dict = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# ---------------------------------------------------------------------------
# Quality mode mapping: encoder -> FFmpeg quality flag type
# ---------------------------------------------------------------------------

ENCODER_QUALITY_MODE: dict[str, str] = {
    # CPU encoders use CRF
    "libx264": "crf",
    "libx265": "crf",
    "libsvtav1": "crf",
    "libvpx-vp9": "crf",
    # NVIDIA NVENC uses CQ
    "h264_nvenc": "cq",
    "hevc_nvenc": "cq",
    "av1_nvenc": "cq",
    # Intel QSV uses QP
    "h264_qsv": "qp",
    "hevc_qsv": "qp",
    "av1_qsv": "qp",
    # AMD AMF uses QP
    "h264_amf": "qp",
    "hevc_amf": "qp",
    # Apple VideoToolbox uses q
    "h264_videotoolbox": "q",
    "hevc_videotoolbox": "q",
}

QUALITY_FLAG_MAP: dict[str, str] = {
    "crf": "-crf",
    "cq": "-cq",
    "qp": "-qp",
    "q": "-q:v",
}

# ---------------------------------------------------------------------------
# Recommended quality values per encoder
# ---------------------------------------------------------------------------

ENCODER_RECOMMENDED_QUALITY: dict[str, int] = {
    "libx264": 23,
    "libx265": 24,
    "libsvtav1": 32,
    "libvpx-vp9": 31,
    "h264_nvenc": 28,
    "hevc_nvenc": 28,
    "av1_nvenc": 36,
    "h264_qsv": 28,
    "hevc_qsv": 30,
    "av1_qsv": 32,
    "h264_amf": 34,
    "hevc_amf": 32,
    "h264_videotoolbox": 65,
    "hevc_videotoolbox": 65,
}

# ---------------------------------------------------------------------------
# Quality value ranges per encoder (min, max)
# ---------------------------------------------------------------------------

ENCODER_QUALITY_RANGE: dict[str, tuple[int, int]] = {
    "libx264": (18, 28),
    "libx265": (18, 28),
    "libsvtav1": (20, 40),
    "libvpx-vp9": (20, 40),
    "h264_nvenc": (20, 36),
    "hevc_nvenc": (20, 36),
    "av1_nvenc": (24, 44),
    "h264_qsv": (20, 36),
    "hevc_qsv": (20, 36),
    "av1_qsv": (20, 40),
    "h264_amf": (20, 40),
    "hevc_amf": (20, 40),
    "h264_videotoolbox": (40, 80),
    "hevc_videotoolbox": (40, 80),
}

# ---------------------------------------------------------------------------
# Fallback chain: hardware -> CPU -> libx264
# ---------------------------------------------------------------------------

ENCODER_FALLBACK_CHAIN: dict[str, str] = {
    "av1_nvenc": "libsvtav1",
    "hevc_nvenc": "libx265",
    "h264_nvenc": "libx264",
    "av1_qsv": "libsvtav1",
    "hevc_qsv": "libx265",
    "h264_qsv": "libx264",
    "h264_amf": "libx264",
    "hevc_amf": "libx265",
    "h264_videotoolbox": "libx264",
    "hevc_videotoolbox": "libx265",
    "libsvtav1": "libx264",
    "libx265": "libx264",
    "libvpx-vp9": "libx264",
}

# ---------------------------------------------------------------------------
# Encoder display metadata (for frontend)
# ---------------------------------------------------------------------------

ENCODER_METADATA: dict[str, dict] = {
    "libx264":     {"label": "H.264 (CPU)",     "qualityMode": "crf", "recommendedQuality": 23, "qualityRange": [18, 28]},
    "libx265":     {"label": "H.265 (CPU)",     "qualityMode": "crf", "recommendedQuality": 24, "qualityRange": [18, 28]},
    "libsvtav1":   {"label": "AV1 (CPU)",       "qualityMode": "crf", "recommendedQuality": 32, "qualityRange": [20, 40]},
    "h264_nvenc":  {"label": "H.264 (NVIDIA)",  "qualityMode": "cq",  "recommendedQuality": 28, "qualityRange": [20, 36]},
    "hevc_nvenc":  {"label": "H.265 (NVIDIA)",  "qualityMode": "cq",  "recommendedQuality": 28, "qualityRange": [20, 36]},
    "av1_nvenc":   {"label": "AV1 (NVIDIA)",    "qualityMode": "cq",  "recommendedQuality": 36, "qualityRange": [24, 44]},
    "h264_qsv":    {"label": "H.264 (Intel)",   "qualityMode": "qp",  "recommendedQuality": 28, "qualityRange": [20, 36]},
    "hevc_qsv":    {"label": "H.265 (Intel)",   "qualityMode": "qp",  "recommendedQuality": 30, "qualityRange": [20, 36]},
    "av1_qsv":     {"label": "AV1 (Intel)",     "qualityMode": "qp",  "recommendedQuality": 32, "qualityRange": [20, 40]},
    "h264_amf":    {"label": "H.264 (AMD)",     "qualityMode": "qp",  "recommendedQuality": 34, "qualityRange": [20, 40]},
    "hevc_amf":    {"label": "H.265 (AMD)",     "qualityMode": "qp",  "recommendedQuality": 32, "qualityRange": [20, 40]},
    "h264_videotoolbox": {"label": "H.264 (Apple)", "qualityMode": "q", "recommendedQuality": 65, "qualityRange": [40, 80]},
    "hevc_videotoolbox": {"label": "H.265 (Apple)", "qualityMode": "q", "recommendedQuality": 65, "qualityRange": [40, 80]},
}


def get_quality_args(codec: str, quality_value: int) -> list[str]:
    """Generate FFmpeg quality arguments for the given encoder.

    Returns the correct flag (-crf/-cq/-qp/-q:v) and value for the codec.
    Falls back to -crf if the codec is unknown.
    """
    mode = ENCODER_QUALITY_MODE.get(codec, "crf")
    flag = QUALITY_FLAG_MAP[mode]
    return [flag, str(quality_value)]


def select_pixel_format(media_info: dict | None, user_override: str = "") -> str:
    """Select pixel format: user override > input probe > safe default.

    Preserves 10-bit input to avoid banding; forces yuv420p for 8-bit content.
    """
    if user_override:
        return user_override
    if media_info:
        pix_fmt = media_info.get("pix_fmt", "")
        if "10le" in pix_fmt or "10be" in pix_fmt:
            return pix_fmt
    return "yuv420p"


def check_encoder_availability(ffmpeg: str, codec: str) -> bool:
    """Check if FFmpeg supports the given encoder."""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
            **_SUBPROCESS_KWARGS,
        )
        return codec in result.stdout
    except Exception as e:
        logger.debug("Failed to check encoder availability for {}: {}", codec, e)
        return False


def get_fallback_codec(ffmpeg: str, requested: str) -> tuple[str, str | None]:
    """Get an available fallback codec.

    Returns (codec, warning_message). If no fallback needed, warning is None.
    """
    if check_encoder_availability(ffmpeg, requested):
        return requested, None

    current = requested
    while current in ENCODER_FALLBACK_CHAIN:
        fallback = ENCODER_FALLBACK_CHAIN[current]
        if check_encoder_availability(ffmpeg, fallback):
            return fallback, (
                f"Encoder '{requested}' not available, "
                f"falling back to '{fallback}'"
            )
        current = fallback

    return "libx264", (
        f"Encoder '{requested}' not available, "
        f"falling back to 'libx264'"
    )

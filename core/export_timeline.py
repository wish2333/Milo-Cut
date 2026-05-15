"""Export timeline formats: EDL (CMX3600) and FCPXML."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime

from loguru import logger


def export_edl(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export CMX3600 EDL file."""
    try:
        fps = media_info.get("fps", 25.0)
        media_name = Path(media_info.get("path", "")).stem[:8].upper()

        # Build keep ranges from edits
        keep_ranges = _build_keep_ranges(segments, edits, media_info.get("duration", 0))

        lines = [
            "TITLE: Milo-Cut Export",
            f"FCM: NON-DROP FRAME",
            "",
        ]

        for idx, (start, end) in enumerate(keep_ranges, 1):
            start_tc = _seconds_to_timecode(start, fps)
            end_tc = _seconds_to_timecode(end, fps)
            record_start = "00:00:00:00"
            record_end = _seconds_to_timecode(end - start, fps)

            lines.append(
                f"{idx:03d}  001  {media_name}  V  C  "
                f"{start_tc} {end_tc} {record_start} {record_end}"
            )
            lines.append(f"* FROM CLIP NAME: {media_name}")
            lines.append("")

        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported EDL to {}", output_path)
        return {"success": True, "data": output_path}

    except Exception as e:
        logger.exception("Failed to export EDL")
        return {"success": False, "error": str(e)}


def export_fcpxml(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export FCPXML file."""
    try:
        fps = media_info.get("fps", 25.0)
        media_path = media_info.get("path", "")
        media_name = Path(media_path).stem
        duration = media_info.get("duration", 0)

        # Build keep ranges from edits
        keep_ranges = _build_keep_ranges(segments, edits, duration)

        # Build FCPXML
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE fcpxml>',
            '<fcpxml version="1.9">',
            "  <resources>",
            f'    <format id="r1" name="FFVideoFormat{media_info.get("height", 1080)}p{fps:.2f}" '
            f'frameDuration="1/{int(fps)}s" width="{media_info.get("width", 1920)}" '
            f'height="{media_info.get("height", 1080)}"/>',
            f'    <asset id="r2" name="{media_name}" src="{media_path}" '
            f'start="0s" duration="{duration}s" hasVideo="1" hasAudio="1"/>',
            "  </resources>",
            "  <library>",
            "    <event name=\"Milo-Cut Export\">",
            f'      <project name="{media_name}_edited">',
            '        <sequence format="r1" tcStart="0s" duration="0s">',
            "          <spine>",
        ]

        for idx, (start, end) in enumerate(keep_ranges):
            clip_duration = end - start
            lines.append(
                f'            <asset-clip ref="r2" offset="{start}s" '
                f'duration="{clip_duration}s" name="Clip {idx + 1}"/>'
            )

        lines.extend([
            "          </spine>",
            "        </sequence>",
            "      </project>",
            "    </event>",
            "  </library>",
            "</fcpxml>",
        ])

        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported FCPXML to {}", output_path)
        return {"success": True, "data": output_path}

    except Exception as e:
        logger.exception("Failed to export FCPXML")
        return {"success": False, "error": str(e)}


def _build_keep_ranges(
    segments: list[dict],
    edits: list[dict],
    total_duration: float,
) -> list[tuple[float, float]]:
    """Build list of (start, end) keep ranges."""
    # Get confirmed delete ranges
    delete_ranges = [
        (e["start"], e["end"])
        for e in edits
        if e.get("status") == "confirmed" and e.get("action") == "delete"
    ]
    delete_ranges.sort()

    # Build keep ranges by inverting delete ranges
    keep_ranges = []
    current = 0.0

    for del_start, del_end in delete_ranges:
        if del_start > current:
            keep_ranges.append((current, del_start))
        current = del_end

    if current < total_duration:
        keep_ranges.append((current, total_duration))

    return keep_ranges


def _seconds_to_timecode(seconds: float, fps: float) -> str:
    """Convert seconds to HH:MM:SS:FF timecode."""
    total_frames = int(seconds * fps)
    frames = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    s = total_seconds % 60
    m = (total_seconds // 60) % 60
    h = total_seconds // 3600
    return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"

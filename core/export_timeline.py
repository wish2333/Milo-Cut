"""Export timeline formats: EDL (CMX3600) and xmeml (FCP 7 XML)."""

from __future__ import annotations

from pathlib import Path

from loguru import logger


def export_edl(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export CMX3600 EDL file compatible with DaVinci Resolve / Premiere Pro."""
    try:
        fps = media_info.get("fps", 25.0)
        media_path = media_info.get("path", "")
        media_filename = Path(media_path).name
        media_stem = Path(media_path).stem

        reel = media_filename

        keep_ranges = _build_keep_ranges(segments, edits, media_info.get("duration", 0), fps)

        lines = [
            "TITLE: Milo-Cut Export",
            "FCM: NON-DROP FRAME",
            "",
        ]

        record_cursor = 0.0

        for idx, (start, end) in enumerate(keep_ranges, 1):
            src_start_tc = _seconds_to_timecode(start, fps)
            src_end_tc = _seconds_to_timecode(end, fps)
            rec_start_tc = _seconds_to_timecode(record_cursor, fps)
            record_cursor += end - start
            rec_end_tc = _seconds_to_timecode(record_cursor, fps)

            lines.append(
                f"{idx:03d}  {reel:<8}  V  C  "
                f"{src_start_tc} {src_end_tc} {rec_start_tc} {rec_end_tc}"
            )
            lines.append(f"* FROM CLIP NAME: {media_path}")

        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported EDL to {}", output_path)
        return {"success": True, "data": output_path}

    except Exception as e:
        logger.exception("Failed to export EDL")
        return {"success": False, "error": str(e)}


def export_xmeml_premiere(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export xmeml for Premiere Pro."""
    try:
        lines = _build_xmeml_core(segments, edits, media_info, wrap_in_project=True)
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported xmeml (Premiere) to {}", output_path)
        return {"success": True, "data": output_path}
    except Exception as e:
        logger.exception("Failed to export xmeml for Premiere")
        return {"success": False, "error": str(e)}


def _build_xmeml_core(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    wrap_in_project: bool,
) -> list[str]:
    """Build xmeml XML lines per FCP 7 XML version 5 spec.

    Timing rules (Premiere Pro / DaVinci Resolve):
    - <in>/<out>: source media frame range (absolute frames in source)
    - <start>/<end>: position in timeline (0-based, continuous)
    - <duration>: clip duration = end - start = out - in
    - Constraint: end - start == out - in (must match)
    - All timing values are non-negative integers (frame counts)
    - <pathurl>: file:///D:/path/file.mp4 format (Windows)
    """
    fps = media_info.get("fps", 25.0)
    media_path = media_info.get("path", "")
    media_name = Path(media_path).stem
    media_filename = Path(media_path).name
    width = media_info.get("width", 1920)
    height = media_info.get("height", 1080)
    source_duration = media_info.get("duration", 0)
    is_ntsc = fps not in (24.0, 25.0, 30.0)
    ntsc_str = "TRUE" if is_ntsc else "FALSE"
    timebase = int(fps)
    source_total_frames = _sec_to_frames(source_duration, fps)

    keep_ranges = _build_keep_ranges(segments, edits, source_duration, fps)
    total_frames = sum(_sec_to_frames(end - start, fps) for start, end in keep_ranges)

    # Premiere prefers relative paths when the XML sits next to source media.
    # Resolve can use a normalized file URI on Windows.
    file_url = (
        Path(media_path).name
        if wrap_in_project
        else Path(media_path).resolve().as_uri()
    )

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="5">',
    ]

    if wrap_in_project:
        lines.extend([
            "  <project>",
            f"    <name>{media_name}_edited</name>",
            "    <children>",
            "      <sequence>",
        ])
    else:
        lines.append("  <sequence>")

    seq_indent = "      " if wrap_in_project else "    "

    lines.extend([
        f"{seq_indent}<name>{media_name}_edited</name>",
        f"{seq_indent}<duration>{total_frames}</duration>",
        f"{seq_indent}<rate>",
        f"{seq_indent}  <ntsc>{ntsc_str}</ntsc>",
        f"{seq_indent}  <timebase>{timebase}</timebase>",
        f"{seq_indent}</rate>",
        f"{seq_indent}<media>",
        f"{seq_indent}  <video>",
        f"{seq_indent}    <format>",
        f"{seq_indent}      <samplecharacteristics>",
        f"{seq_indent}        <width>{width}</width>",
        f"{seq_indent}        <height>{height}</height>",
        f"{seq_indent}      </samplecharacteristics>",
        f"{seq_indent}    </format>",
        f"{seq_indent}    <track>",
    ])

    clip_indent = seq_indent + "      "

    # Pre-compute clip IDs for linking
    clip_ids = []
    for idx, (start, end) in enumerate(keep_ranges, 1):
        clip_dur = _sec_to_frames(end - start, fps)
        if clip_dur > 0:
            clip_ids.append(idx)

    # Video clipitems
    rec_cursor = 0
    for idx, (start, end) in enumerate(keep_ranges, 1):
        src_in = _sec_to_frames(start, fps)
        src_out = _sec_to_frames(end, fps)
        clip_dur = src_out - src_in
        if clip_dur <= 0:
            continue
        rec_start = rec_cursor
        rec_end = rec_cursor + clip_dur
        rec_cursor = rec_end
        v_id = f"clipitem-video-{idx}"
        a1_id = f"clipitem-audio1-{idx}"
        a2_id = f"clipitem-audio2-{idx}"

        lines.extend([
            f"{clip_indent}<clipitem id=\"{v_id}\">",
            f"{clip_indent}  <name>{media_filename}</name>",
            f"{clip_indent}  <duration>{clip_dur}</duration>",
            f"{clip_indent}  <rate>",
            f"{clip_indent}    <ntsc>{ntsc_str}</ntsc>",
            f"{clip_indent}    <timebase>{timebase}</timebase>",
            f"{clip_indent}  </rate>",
            f"{clip_indent}  <start>{rec_start}</start>",
            f"{clip_indent}  <end>{rec_end}</end>",
            f"{clip_indent}  <in>{src_in}</in>",
            f"{clip_indent}  <out>{src_out}</out>",
            f"{clip_indent}  <file id=\"file-{idx}\">",
            f"{clip_indent}    <name>{media_filename}</name>",
            f"{clip_indent}    <pathurl>{file_url}</pathurl>",
            f"{clip_indent}    <rate>",
            f"{clip_indent}      <ntsc>{ntsc_str}</ntsc>",
            f"{clip_indent}      <timebase>{timebase}</timebase>",
            f"{clip_indent}    </rate>",
            f"{clip_indent}    <duration>{source_total_frames}</duration>",
            f"{clip_indent}    <timecode>",
            f"{clip_indent}      <rate>",
            f"{clip_indent}        <ntsc>{ntsc_str}</ntsc>",
            f"{clip_indent}        <timebase>{timebase}</timebase>",
            f"{clip_indent}      </rate>",
            f"{clip_indent}      <string>00:00:00:00</string>",
            f"{clip_indent}      <frame>0</frame>",
            f"{clip_indent}      <source>source</source>",
            f"{clip_indent}    </timecode>",
            f"{clip_indent}    <media>",
            f"{clip_indent}      <video>",
            f"{clip_indent}        <samplecharacteristics>",
            f"{clip_indent}          <width>{width}</width>",
            f"{clip_indent}          <height>{height}</height>",
            f"{clip_indent}        </samplecharacteristics>",
            f"{clip_indent}      </video>",
            f"{clip_indent}      <audio>",
            f"{clip_indent}        <samplecharacteristics>",
            f"{clip_indent}          <depth>16</depth>",
            f"{clip_indent}          <samplerate>48000</samplerate>",
            f"{clip_indent}        </samplecharacteristics>",
            f"{clip_indent}        <channelcount>2</channelcount>",
            f"{clip_indent}      </audio>",
            f"{clip_indent}    </media>",
            f"{clip_indent}  </file>",
            f"{clip_indent}  <sourcetrack>",
            f"{clip_indent}    <mediatype>video</mediatype>",
            f"{clip_indent}  </sourcetrack>",
            f"{clip_indent}  <link>",
            f"{clip_indent}    <linkclipref>{a1_id}</linkclipref>",
            f"{clip_indent}    <mediatype>audio</mediatype>",
            f"{clip_indent}    <trackindex>1</trackindex>",
            f"{clip_indent}    <clipindex>{idx}</clipindex>",
            f"{clip_indent}  </link>",
            f"{clip_indent}  <link>",
            f"{clip_indent}    <linkclipref>{a2_id}</linkclipref>",
            f"{clip_indent}    <mediatype>audio</mediatype>",
            f"{clip_indent}    <trackindex>2</trackindex>",
            f"{clip_indent}    <clipindex>{idx}</clipindex>",
            f"{clip_indent}  </link>",
            f"{clip_indent}</clipitem>",
        ])

    # Close video track and video section, open audio section
    lines.extend([
        f"{seq_indent}    </track>",
        f"{seq_indent}  </video>",
        f"{seq_indent}  <audio>",
    ])

    # Audio tracks (two tracks: L and R)
    for track_idx, track_suffix in ((1, "audio1"), (2, "audio2")):
        if track_idx > 1:
            lines.append(f"{seq_indent}    </track>")
        lines.append(f"{seq_indent}    <track>")

        rec_cursor = 0
        for idx, (start, end) in enumerate(keep_ranges, 1):
            src_in = _sec_to_frames(start, fps)
            src_out = _sec_to_frames(end, fps)
            clip_dur = src_out - src_in
            if clip_dur <= 0:
                continue
            rec_start = rec_cursor
            rec_end = rec_cursor + clip_dur
            rec_cursor = rec_end

            a_id = f"clipitem-{track_suffix}-{idx}"
            other_a_id = f"clipitem-{'audio2' if track_idx == 1 else 'audio1'}-{idx}"
            v_id = f"clipitem-video-{idx}"

            lines.extend([
                f"{clip_indent}<clipitem id=\"{a_id}\">",
                f"{clip_indent}  <name>{media_filename}</name>",
                f"{clip_indent}  <duration>{clip_dur}</duration>",
                f"{clip_indent}  <rate>",
                f"{clip_indent}    <ntsc>{ntsc_str}</ntsc>",
                f"{clip_indent}    <timebase>{timebase}</timebase>",
                f"{clip_indent}  </rate>",
                f"{clip_indent}  <start>{rec_start}</start>",
                f"{clip_indent}  <end>{rec_end}</end>",
                f"{clip_indent}  <in>{src_in}</in>",
                f"{clip_indent}  <out>{src_out}</out>",
                f"{clip_indent}  <file id=\"file-{idx}\"/>",
                f"{clip_indent}  <sourcetrack>",
                f"{clip_indent}    <mediatype>audio</mediatype>",
                f"{clip_indent}    <trackindex>{track_idx}</trackindex>",
                f"{clip_indent}  </sourcetrack>",
                f"{clip_indent}  <link>",
                f"{clip_indent}    <linkclipref>{v_id}</linkclipref>",
                f"{clip_indent}    <mediatype>video</mediatype>",
                f"{clip_indent}    <trackindex>1</trackindex>",
                f"{clip_indent}    <clipindex>{idx}</clipindex>",
                f"{clip_indent}  </link>",
                f"{clip_indent}  <link>",
                f"{clip_indent}    <linkclipref>{other_a_id}</linkclipref>",
                f"{clip_indent}    <mediatype>audio</mediatype>",
                f"{clip_indent}    <trackindex>{2 if track_idx == 1 else 1}</trackindex>",
                f"{clip_indent}    <clipindex>{idx}</clipindex>",
                f"{clip_indent}  </link>",
                f"{clip_indent}</clipitem>",
            ])

    lines.extend([
        f"{seq_indent}    </track>",
        f"{seq_indent}  </audio>",
        f"{seq_indent}</media>",
    ])

    if wrap_in_project:
        lines.extend([
            "      </sequence>",
            "    </children>",
            "  </project>",
        ])
    else:
        lines.append("  </sequence>")

    lines.append("</xmeml>")
    return lines


def _build_keep_ranges(
    segments: list[dict],
    edits: list[dict],
    total_duration: float,
    fps: float,
) -> list[tuple[float, float]]:
    """Build list of (start, end) keep ranges, filtering out degenerate ranges."""
    delete_ranges = [
        (e["start"], e["end"])
        for e in edits
        if e.get("status") == "confirmed" and e.get("action") == "delete"
    ]
    delete_ranges.sort()

    keep_ranges = []
    current = 0.0

    for del_start, del_end in delete_ranges:
        if del_start > current:
            keep_ranges.append((current, min(del_start, total_duration)))
        current = max(del_end, current)

    if current < total_duration:
        keep_ranges.append((current, total_duration))

    # Filter out ranges that produce 0 frames (floating-point rounding edge cases)
    return [(s, e) for s, e in keep_ranges if _sec_to_frames(e - s, fps) > 0]


def _sec_to_frames(seconds: float, fps: float) -> int:
    """Convert seconds to frame count."""
    return int(seconds * fps)


def _seconds_to_timecode(seconds: float, fps: float) -> str:
    """Convert seconds to HH:MM:SS:FF timecode."""
    total_frames = _sec_to_frames(seconds, fps)
    frames = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    s = total_seconds % 60
    m = (total_seconds // 60) % 60
    h = total_seconds // 3600
    return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"

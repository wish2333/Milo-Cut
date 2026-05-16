"""Export timeline formats: EDL (CMX3600), xmeml (FCP 7 XML), and OTIO."""

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
    *,
    mode: str = "clean",
) -> dict:
    """Export xmeml for Premiere Pro."""
    try:
        lines = _build_xmeml_core(segments, edits, media_info, wrap_in_project=True, mode=mode)
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Exported xmeml (Premiere) to {}", output_path)
        return {"success": True, "data": output_path}
    except Exception as e:
        logger.exception("Failed to export xmeml for Premiere")
        return {"success": False, "error": str(e)}


def _build_xmeml_full_timeline(
    keep_ranges: list[tuple[float, float]],
    edits: list[dict],
    media_info: dict,
    wrap_in_project: bool,
    fps: float,
    media_path: str,
    media_name: str,
    media_filename: str,
    width: int,
    height: int,
    source_duration: float,
    is_ntsc: bool,
    ntsc_str: str,
    timebase: int,
    source_total_frames: int,
) -> list[str]:
    """Build xmeml XML with interleaved clipitem and gap elements."""
    deleted_ranges = sorted(
        (e["start"], e["end"])
        for e in edits
        if e.get("status") == "confirmed" and e.get("action") == "delete"
    )

    all_ranges: list[tuple[float, float, str]] = []
    for s, e in keep_ranges:
        all_ranges.append((s, e, "keep"))
    for s, e in deleted_ranges:
        all_ranges.append((s, e, "deleted"))
    all_ranges.sort(key=lambda r: r[0])

    total_frames = 0
    for start, end, kind in all_ranges:
        start_frame = _sec_to_frames(start, fps)
        end_frame = _sec_to_frames(end, fps)
        dur = end_frame - start_frame
        if dur > 0:
            total_frames += dur

    file_url = Path(media_path).name if wrap_in_project else Path(media_path).resolve().as_uri()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE xmeml>',
        '<xmeml version="5">',
    ]
    if wrap_in_project:
        lines.extend(["  <project>", f"    <name>{media_name}_edited</name>", "    <children>", "      <sequence>"])
    else:
        lines.append("  <sequence>")

    si = "      " if wrap_in_project else "    "
    lines.extend([
        f"{si}<name>{media_name}_edited</name>",
        f"{si}<duration>{total_frames}</duration>",
        f"{si}<rate>", f"{si}  <ntsc>{ntsc_str}</ntsc>", f"{si}  <timebase>{timebase}</timebase>", f"{si}</rate>",
        f"{si}<media>", f"{si}  <video>",
        f"{si}    <format>", f"{si}      <samplecharacteristics>",
        f"{si}        <width>{width}</width>", f"{si}        <height>{height}</height>",
        f"{si}      </samplecharacteristics>", f"{si}    </format>",
        f"{si}    <track>",
    ])

    ci = si + "      "
    current_timeline_frame = 0
    clip_idx = 0

    for start, end, kind in all_ranges:
        start_frame = _sec_to_frames(start, fps)
        end_frame = _sec_to_frames(end, fps)
        dur_frames = end_frame - start_frame
        if dur_frames <= 0:
            continue

        seq_start = current_timeline_frame
        seq_end = current_timeline_frame + dur_frames
        current_timeline_frame = seq_end

        if kind == "keep":
            clip_idx += 1
            v_id = f"clipitem-video-{clip_idx}"
            a1_id = f"clipitem-audio1-{clip_idx}"
            a2_id = f"clipitem-audio2-{clip_idx}"
            lines.extend([
                f"{ci}<clipitem id=\"{v_id}\">",
                f"{ci}  <name>{media_filename}</name>",
                f"{ci}  <duration>{dur_frames}</duration>",
                f"{ci}  <rate>", f"{ci}    <ntsc>{ntsc_str}</ntsc>", f"{ci}    <timebase>{timebase}</timebase>", f"{ci}  </rate>",
                f"{ci}  <start>{seq_start}</start>",
                f"{ci}  <end>{seq_end}</end>",
                f"{ci}  <in>{start_frame}</in>",
                f"{ci}  <out>{end_frame}</out>",
                f"{ci}  <file id=\"file-{clip_idx}\">",
                f"{ci}    <name>{media_filename}</name>",
                f"{ci}    <pathurl>{file_url}</pathurl>",
                f"{ci}    <rate>", f"{ci}      <ntsc>{ntsc_str}</ntsc>", f"{ci}      <timebase>{timebase}</timebase>", f"{ci}    </rate>",
                f"{ci}    <duration>{source_total_frames}</duration>",
                f"{ci}    <timecode>", f"{ci}      <rate>", f"{ci}        <ntsc>{ntsc_str}</ntsc>", f"{ci}        <timebase>{timebase}</timebase>", f"{ci}      </rate>",
                f"{ci}      <string>00:00:00:00</string>", f"{ci}      <frame>0</frame>", f"{ci}      <source>source</source>", f"{ci}    </timecode>",
                f"{ci}    <media>", f"{ci}      <video>", f"{ci}        <samplecharacteristics>",
                f"{ci}          <width>{width}</width>", f"{ci}          <height>{height}</height>",
                f"{ci}        </samplecharacteristics>", f"{ci}      </video>",
                f"{ci}      <audio>", f"{ci}        <samplecharacteristics>",
                f"{ci}          <depth>16</depth>", f"{ci}          <samplerate>48000</samplerate>",
                f"{ci}        </samplecharacteristics>", f"{ci}        <channelcount>2</channelcount>",
                f"{ci}      </audio>", f"{ci}    </media>",
                f"{ci}  </file>",
                f"{ci}  <sourcetrack>", f"{ci}    <mediatype>video</mediatype>", f"{ci}  </sourcetrack>",
                f"{ci}  <link>", f"{ci}    <linkclipref>{a1_id}</linkclipref>", f"{ci}    <mediatype>audio</mediatype>",
                f"{ci}    <trackindex>1</trackindex>", f"{ci}    <clipindex>{clip_idx}</clipindex>", f"{ci}  </link>",
                f"{ci}  <link>", f"{ci}    <linkclipref>{a2_id}</linkclipref>", f"{ci}    <mediatype>audio</mediatype>",
                f"{ci}    <trackindex>2</trackindex>", f"{ci}    <clipindex>{clip_idx}</clipindex>", f"{ci}  </link>",
                f"{ci}</clipitem>",
            ])
        else:
            lines.extend([
                f"{ci}<clipitem id=\"gap-{seq_start}\">",
                f"{ci}  <name>Milo-Cut Deleted ({start:.3f}-{end:.3f})</name>",
                f"{ci}  <duration>{dur_frames}</duration>",
                f"{ci}  <rate>", f"{ci}    <ntsc>{ntsc_str}</ntsc>", f"{ci}    <timebase>{timebase}</timebase>", f"{ci}  </rate>",
                f"{ci}  <start>{seq_start}</start>",
                f"{ci}  <end>{seq_end}</end>",
                f"{ci}  <in>0</in>",
                f"{ci}  <out>{dur_frames}</out>",
                f"{ci}  <syncoffset>0</syncoffset>",
                f"{ci}</clipitem>",
            ])

    lines.extend([f"{si}    </track>", f"{si}  </video>", f"{si}  <audio>"])

    # Audio tracks
    for track_idx, track_suffix in ((1, "audio1"), (2, "audio2")):
        if track_idx > 1:
            lines.append(f"{si}    </track>")
        lines.append(f"{si}    <track>")

        current_timeline_frame = 0
        clip_idx = 0
        for start, end, kind in all_ranges:
            start_frame = _sec_to_frames(start, fps)
            end_frame = _sec_to_frames(end, fps)
            dur_frames = end_frame - start_frame
            if dur_frames <= 0:
                continue
            seq_start = current_timeline_frame
            seq_end = current_timeline_frame + dur_frames
            current_timeline_frame = seq_end

            if kind == "keep":
                clip_idx += 1
                a_id = f"clipitem-{track_suffix}-{clip_idx}"
                other_a_id = f"clipitem-{'audio2' if track_idx == 1 else 'audio1'}-{clip_idx}"
                v_id = f"clipitem-video-{clip_idx}"
                lines.extend([
                    f"{ci}<clipitem id=\"{a_id}\">",
                    f"{ci}  <name>{media_filename}</name>",
                    f"{ci}  <duration>{dur_frames}</duration>",
                    f"{ci}  <rate>", f"{ci}    <ntsc>{ntsc_str}</ntsc>", f"{ci}    <timebase>{timebase}</timebase>", f"{ci}  </rate>",
                    f"{ci}  <start>{seq_start}</start>", f"{ci}  <end>{seq_end}</end>",
                    f"{ci}  <in>{start_frame}</in>", f"{ci}  <out>{end_frame}</out>",
                    f"{ci}  <file id=\"file-{clip_idx}\"/>",
                    f"{ci}  <sourcetrack>", f"{ci}    <mediatype>audio</mediatype>", f"{ci}    <trackindex>{track_idx}</trackindex>", f"{ci}  </sourcetrack>",
                    f"{ci}  <link>", f"{ci}    <linkclipref>{v_id}</linkclipref>", f"{ci}    <mediatype>video</mediatype>",
                    f"{ci}    <trackindex>1</trackindex>", f"{ci}    <clipindex>{clip_idx}</clipindex>", f"{ci}  </link>",
                    f"{ci}  <link>", f"{ci}    <linkclipref>{other_a_id}</linkclipref>", f"{ci}    <mediatype>audio</mediatype>",
                    f"{ci}    <trackindex>{2 if track_idx == 1 else 1}</trackindex>", f"{ci}    <clipindex>{clip_idx}</clipindex>", f"{ci}  </link>",
                    f"{ci}</clipitem>",
                ])
            else:
                lines.extend([
                    f"{ci}<clipitem id=\"gap-{track_suffix}-{seq_start}\">",
                    f"{ci}  <name>Milo-Cut Deleted ({start:.3f}-{end:.3f})</name>",
                    f"{ci}  <duration>{dur_frames}</duration>",
                    f"{ci}  <rate>", f"{ci}    <ntsc>{ntsc_str}</ntsc>", f"{ci}    <timebase>{timebase}</timebase>", f"{ci}  </rate>",
                    f"{ci}  <start>{seq_start}</start>", f"{ci}  <end>{seq_end}</end>",
                    f"{ci}  <in>0</in>", f"{ci}  <out>{dur_frames}</out>",
                    f"{ci}  <syncoffset>0</syncoffset>",
                    f"{ci}</clipitem>",
                ])

    lines.extend([f"{si}    </track>", f"{si}  </audio>", f"{si}</media>"])
    if wrap_in_project:
        lines.extend(["      </sequence>", "    </children>", "  </project>"])
    else:
        lines.append("  </sequence>")
    lines.append("</xmeml>")
    return lines


def _build_xmeml_core(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    wrap_in_project: bool,
    *,
    mode: str = "clean",
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

    if mode == "full_timeline":
        return _build_xmeml_full_timeline(
            keep_ranges, edits, media_info, wrap_in_project, fps, media_path,
            media_name, media_filename, width, height, source_duration,
            is_ntsc, ntsc_str, timebase, source_total_frames,
        )

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
    """Convert seconds to frame count (strict integer for NLE compatibility)."""
    return int(round(seconds * fps))


def _seconds_to_timecode(seconds: float, fps: float) -> str:
    """Convert seconds to HH:MM:SS:FF timecode."""
    total_frames = _sec_to_frames(seconds, fps)
    frames = total_frames % int(fps)
    total_seconds = total_frames // int(fps)
    s = total_seconds % 60
    m = (total_seconds // 60) % 60
    h = total_seconds // 3600
    return f"{h:02d}:{m:02d}:{s:02d}:{frames:02d}"


def _build_full_timeline_items(
    keep_ranges: list[tuple[float, float]],
    edits: list[dict],
    fps: float,
    media_filename: str,
    available_dur_frames: int,
) -> list:
    """Build OTIO track items including Gap+Marker for deleted regions."""
    import opentimelineio as otio

    deleted_ranges = sorted(
        (e["start"], e["end"])
        for e in edits
        if e.get("status") == "confirmed" and e.get("action") == "delete"
    )

    # Merge keep and deleted into a single sorted list
    all_ranges: list[tuple[float, float, str]] = []
    for s, e in keep_ranges:
        all_ranges.append((s, e, "keep"))
    for s, e in deleted_ranges:
        all_ranges.append((s, e, "deleted"))
    all_ranges.sort(key=lambda r: r[0])

    items: list = []
    for start, end, kind in all_ranges:
        start_frame = _sec_to_frames(start, fps)
        end_frame = _sec_to_frames(end, fps)
        dur_frames = end_frame - start_frame
        if dur_frames <= 0:
            continue

        if kind == "keep":
            clip = otio.schema.Clip(
                name=f"Clip {len([i for i in items if isinstance(i, otio.schema.Clip)]) + 1}",
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(start_frame, fps),
                    duration=otio.opentime.RationalTime(dur_frames, fps),
                ),
                media_reference=otio.schema.ExternalReference(
                    target_url=media_filename,
                    available_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0, fps),
                        duration=otio.opentime.RationalTime(available_dur_frames, fps),
                    ),
                ),
            )
            items.append(clip)
        else:
            gap = otio.schema.Gap(
                name="Milo-Cut Deleted",
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, fps),
                    duration=otio.opentime.RationalTime(dur_frames, fps),
                ),
            )
            marker = otio.schema.Marker(
                name="Milo-Cut Deleted",
                color=otio.schema.MarkerColor.RED,
                marked_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, fps),
                    duration=otio.opentime.RationalTime(dur_frames, fps),
                ),
            )
            gap.markers.append(marker)
            items.append(gap)

    return items


def export_otio(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
    *,
    fade_duration: float = 0.0,
    mode: str = "clean",
    fade_mode: str = "crossfade",
) -> dict:
    """Export OpenTimelineIO (.otio) using the opentimelineio library.

    The .otio file is saved next to the source video for easy relocation.
    All RationalTime values are strict integers for NLE compatibility.
    """
    import opentimelineio as otio

    try:
        fps = media_info.get("fps", 25.0)
        media_path = media_info.get("path", "")
        source_duration = media_info.get("duration", 0)

        keep_ranges = _build_keep_ranges(segments, edits, source_duration, fps)

        media_filename = Path(media_path).name
        available_dur_frames = _sec_to_frames(source_duration, fps)

        # Track items for full_timeline mode (no fades supported)
        if mode == "full_timeline":
            track_items = _build_full_timeline_items(
                keep_ranges, edits, fps, media_filename, available_dur_frames,
            )
            video_track = otio.schema.Track(
                name="Video 1",
                kind=otio.schema.TrackKind.Video,
            )
            audio_track = otio.schema.Track(
                name="Audio 1",
                kind=otio.schema.TrackKind.Audio,
            )
            for item in track_items:
                video_track.append(item)
                audio_track.append(item.deepcopy())
        else:
            # Build clips using OTIO schema objects
            otio_clips: list[otio.schema.Clip] = []
            for idx, (start, end) in enumerate(keep_ranges):
                clip_dur = end - start
                if clip_dur <= 0:
                    continue
                src_start_frames = _sec_to_frames(start, fps)
                src_dur_frames = _sec_to_frames(clip_dur, fps)

                clip = otio.schema.Clip(
                    name=f"Clip {idx + 1}",
                    source_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(src_start_frames, fps),
                        duration=otio.opentime.RationalTime(src_dur_frames, fps),
                    ),
                    media_reference=otio.schema.ExternalReference(
                        target_url=media_filename,
                        available_range=otio.opentime.TimeRange(
                            start_time=otio.opentime.RationalTime(0, fps),
                            duration=otio.opentime.RationalTime(available_dur_frames, fps),
                        ),
                    ),
                )
                otio_clips.append(clip)

            # Build timeline with separate Video and Audio tracks
            video_track = otio.schema.Track(
                name="Video 1",
                kind=otio.schema.TrackKind.Video,
            )
            audio_track = otio.schema.Track(
                name="Audio 1",
                kind=otio.schema.TrackKind.Audio,
            )

            # OTIO per-clip fade effects are not supported by major NLEs.
            # Both "crossfade" and "separate" modes use SMPTE_Dissolve transitions.
            track_items: list = list(otio_clips)
            if fade_duration > 0 and len(otio_clips) > 1:
                track_items = _build_otio_clips_with_transitions(
                    otio_clips, fps, fade_duration, keep_ranges, source_duration,
                )
            for item in track_items:
                video_track.append(item)
                audio_track.append(item.deepcopy())

        timeline = otio.schema.Timeline(
            name=Path(media_path).stem + "_edited",
            global_start_time=otio.opentime.RationalTime(0, fps),
        )
        timeline.tracks.append(video_track)
        timeline.tracks.append(audio_track)

        # Serialize via OTIO adapter (ensures valid schema output)
        otio.adapters.write_to_file(timeline, output_path)
        logger.info("Exported OTIO to {}", output_path)
        return {"success": True, "data": output_path}

    except Exception as e:
        logger.exception("Failed to export OTIO")
        return {"success": False, "error": str(e)}


def _build_otio_clips_with_transitions(
    clips: list,
    fps: float,
    fade_duration: float,
    keep_ranges: list[tuple[float, float]],
    source_duration: float,
) -> list:
    """Insert SMPTE_Dissolve Transition objects between OTIO Clips.

    Handles check: clips at source boundaries are skipped because there
    is no extra media available for crossfade.

    Note: Python 3 round() uses banker's rounding (round-half-to-even).
    For example, round(2.5) -> 2, round(3.5) -> 4. This means the total
    transition duration may be off by one frame, keeping in_offset and
    out_offset perfectly symmetric. This is acceptable in NLE workflows.
    """
    import opentimelineio as otio

    half_fade_frames = _sec_to_frames(fade_duration / 2, fps)
    if half_fade_frames <= 0:
        return list(clips)

    epsilon = 0.001
    interleaved: list = []
    for i, clip in enumerate(clips):
        interleaved.append(clip)
        if i >= len(clips) - 1:
            break

        a_start, a_end = keep_ranges[i]
        b_start, _ = keep_ranges[i + 1]

        a_has_handle = (a_end + fade_duration / 2) <= (source_duration + epsilon)
        b_has_handle = b_start >= (fade_duration / 2 - epsilon)

        if not (a_has_handle and b_has_handle):
            continue

        transition = otio.schema.Transition(
            name=f"Crossfade {i + 1}",
            transition_type="SMPTE_Dissolve",
            in_offset=otio.opentime.RationalTime(half_fade_frames, fps),
            out_offset=otio.opentime.RationalTime(half_fade_frames, fps),
        )
        interleaved.append(transition)

    return interleaved



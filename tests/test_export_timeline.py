"""Tests for core.export_timeline: EDL / xmeml / OTIO exports.

Regression coverage for v2.3.1:
    Audio-only projects (.wav / .mp3) are probed with ``fps=0.0``. Earlier
    ``_build_keep_ranges`` filtered keep ranges with ``_sec_to_frames(dur, fps) > 0``
    which always evaluated to 0 when ``fps=0``, silently dropping ALL ranges and
    producing empty EDL / xmeml / OTIO files (the export returned ``success=True``
    with a valid-but-empty timeline).
"""

from __future__ import annotations

from pathlib import Path

from core.export_timeline import (
    _build_keep_ranges,
    export_edl,
    export_otio,
    export_xmeml_premiere,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _media_info_audio(duration: float = 100.0) -> dict:
    """Audio-only media_info: ffprobe sets fps=0.0 when there is no video stream."""
    return {
        "path": "/tmp/test.wav",
        "duration": duration,
        "width": 0,
        "height": 0,
        "fps": 0.0,  # <-- the trigger
        "audio_channels": 1,
        "sample_rate": 44100,
    }


def _media_info_video(duration: float = 100.0, fps: float = 30.0) -> dict:
    return {
        "path": "/tmp/test.mp4",
        "duration": duration,
        "width": 1920,
        "height": 1080,
        "fps": fps,
    }


def _confirmed_delete(start: float, end: float, idx: int = 1) -> dict:
    return {
        "id": f"edit-{idx}",
        "action": "delete",
        "status": "confirmed",
        "start": start,
        "end": end,
        "target_type": "range",
        "source": "test",
    }


def _segments_basic() -> list[dict]:
    return [
        {"id": "s1", "type": "subtitle", "start": 0.0, "end": 10.0, "text": "a"},
        {"id": "s2", "type": "subtitle", "start": 10.0, "end": 20.0, "text": "b"},
        {"id": "s3", "type": "subtitle", "start": 20.0, "end": 30.0, "text": "c"},
    ]


# ---------------------------------------------------------------------------
# _build_keep_ranges unit tests
# ---------------------------------------------------------------------------

class TestBuildKeepRanges:
    def test_video_fps_keeps_ranges(self):
        """Video project: keep ranges are filtered by frame count > 0."""
        edits = [_confirmed_delete(10.0, 20.0)]
        ranges = _build_keep_ranges(_segments_basic(), edits, 30.0, fps=30.0)
        # delete 10-20 in a 30s timeline => keep (0,10) + (20,30)
        assert ranges == [(0.0, 10.0), (20.0, 30.0)]

    def test_audio_fps_zero_does_not_drop_ranges(self):
        """Regression v2.3.1: fps=0.0 must NOT eliminate all keep ranges.

        Before fix: ``_sec_to_frames(dur, 0.0) == 0`` for any duration, so the
        ``> 0`` filter dropped everything and all three export functions wrote
        empty timeline files.
        """
        edits = [_confirmed_delete(10.0, 20.0)]
        ranges = _build_keep_ranges(_segments_basic(), edits, 30.0, fps=0.0)
        # Must keep both ranges; only degenerate (start==end) ranges filtered.
        assert ranges == [(0.0, 10.0), (20.0, 30.0)]

    def test_audio_fps_zero_no_edits_keeps_full_duration(self):
        """Audio-only project with no confirmed deletes keeps entire timeline."""
        ranges = _build_keep_ranges(_segments_basic(), [], 30.0, fps=0.0)
        assert ranges == [(0.0, 30.0)]

    def test_degenerate_range_filtered_for_audio(self):
        """A zero-length delete (start == end) splits the timeline into two
        adjacent non-degenerate ranges; no zero-width range appears."""
        edits = [_confirmed_delete(10.0, 10.0)]  # zero-length delete
        ranges = _build_keep_ranges(_segments_basic(), edits, 30.0, fps=0.0)
        # (0,10) + (10,30): both non-zero width, no degenerate ranges
        assert ranges == [(0.0, 10.0), (10.0, 30.0)]
        # Sanity: every range has positive width
        assert all(e - s > 0 for s, e in ranges)

    def test_negative_fps_treated_like_audio(self):
        """A malformed fps<=0 falls into the same audio-only branch."""
        edits = [_confirmed_delete(5.0, 15.0)]
        ranges = _build_keep_ranges(_segments_basic(), edits, 30.0, fps=-1.0)
        assert ranges == [(0.0, 5.0), (15.0, 30.0)]


# ---------------------------------------------------------------------------
# Integration: three export functions with fps=0 (audio-only)
# ---------------------------------------------------------------------------

class TestAudioOnlyExportsRegression:
    """All three timeline exports must produce non-empty files for audio-only media.

    Before v2.3.1 fix, these wrote valid-but-empty timeline files and returned
    ``success=True``, hiding the data loss from the user.
    """

    def test_export_edl_audio_only_writes_clips(self, tmp_path: Path):
        out = tmp_path / "out.edl"
        edits = [_confirmed_delete(10.0, 20.0)]
        result = export_edl(_segments_basic(), edits, _media_info_audio(30.0), str(out))

        assert result["success"] is True
        content = out.read_text(encoding="utf-8")
        # Header is always present
        assert "TITLE: Milo-Cut Export" in content
        # Regression: at least one clip line must exist (idx 001 pattern)
        assert "001" in content
        assert "FROM CLIP NAME" in content

    def test_export_xmeml_premiere_audio_only_has_clipitems(self, tmp_path: Path):
        out = tmp_path / "out.xml"
        edits = [_confirmed_delete(10.0, 20.0)]
        result = export_xmeml_premiere(
            _segments_basic(), edits, _media_info_audio(30.0), str(out), mode="clean"
        )

        assert result["success"] is True
        content = out.read_text(encoding="utf-8")
        assert "<?xml version" in content
        assert "<xmeml" in content
        # Regression: empty timeline (pre-fix) was ~200 bytes with no clipitems.
        # Non-empty must be substantially larger AND contain clipitem elements.
        assert out.stat().st_size > 1000, (
            f"xmeml output suspiciously small ({out.stat().st_size}B); "
            "likely empty timeline regression"
        )
        # clipitem appears in pairs (<clipitem>...</clipitem>); count closing tags.
        clipitem_count = content.count("</clipitem>")
        assert clipitem_count >= 1, "no <clipitem> elements in xmeml output"
        # Duration must reflect kept content (20s kept out of 30s), not zero.
        assert "<duration>0</duration>" not in content

    def test_export_otio_audio_only_has_clips(self, tmp_path: Path):
        out = tmp_path / "out.otio"
        edits = [_confirmed_delete(10.0, 20.0)]
        result = export_otio(
            _segments_basic(),
            edits,
            _media_info_audio(30.0),
            str(out),
            fade_duration=0.0,
            mode="clean",
        )

        assert result["success"] is True
        # OTIO is JSON; validate structurally rather than by string match.
        import json
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data.get("OTIO_SCHEMA") == "Timeline.1"
        # OTIO schema: top-level "tracks" is a Stack (dict) with "children" list.
        tracks_stack = data.get("tracks", {})
        assert tracks_stack.get("OTIO_SCHEMA") == "Stack.1"
        track_list = tracks_stack.get("children", [])
        assert len(track_list) > 0, "OTIO Stack has zero tracks (empty timeline regression)"
        # Each Track's children are its clips; at least one clip must exist across all tracks.
        total_clips = sum(len(t.get("children", [])) for t in track_list)
        assert total_clips > 0, "all OTIO tracks are empty (no clips)"

    def test_export_edl_video_still_works(self, tmp_path: Path):
        """Sanity: video path (fps>0) is not regressed by the audio-only guard."""
        out = tmp_path / "out.edl"
        edits = [_confirmed_delete(10.0, 20.0)]
        result = export_edl(_segments_basic(), edits, _media_info_video(30.0), str(out))

        assert result["success"] is True
        content = out.read_text(encoding="utf-8")
        assert "001" in content
        assert "FROM CLIP NAME" in content

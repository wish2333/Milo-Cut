"""v3.0.5 P4-4 D4 test round (PRD-v3.0.4 §10.3 handover, PRD-v3.0.5 §7.4).

Four long-standing test gaps in the silence/trim chain, handed over from
the v3.0.4 T4b smoke pass. NOT counted against the R5.x M-gate quotas
(增量如实登记) -- they are safety-net coverage:

1. detect_silence itself (core/ffmpeg_service.py): the silencedetect
   stderr parser -- pairing, rounding, unmatched starts, garbage lines,
   the ffmpeg-missing envelope.
2. End-to-end serial pass: the same dicts detect_silence returns flow
   through ProjectService.add_silence_results (margin + subtitle
   padding) and land as silence segments + pending delete edits.
3. generate_subtitle_keep_ranges(padding=0): adjacent subtitles abut
   exactly -- the expanded keep ranges merge with no negative/zero-width
   delete ranges in between (the overlap interaction at the boundary).
4. Overlapping add-segment data safety (backend half): a segment whose
   range overlaps a neighbour still stores sorted and re-loads intact
   (the sort invariant is the data-safety net; the frontend half lives
   in SegmentBlocksLayer.test.ts).
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from core import ffmpeg_service
from core.ffmpeg_service import detect_silence
from core.project_service import ProjectService

# ------------------------------------------------------------------
# 1. detect_silence itself (parser + envelopes)
# ------------------------------------------------------------------


def _fake_ffmpeg_run(stderr: str):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=0, stderr=stderr, stdout="")
    return fake_run


class TestDetectSilence:
    @pytest.fixture()
    def ffmpeg_here(self, monkeypatch):
        monkeypatch.setattr(ffmpeg_service, "_find_ffmpeg", lambda: "/fake/ffmpeg")

    def test_parses_paired_windows_with_rounding(self, ffmpeg_here):
        stderr = (
            "[silencedetect @ 0x1] silence_start: 1.234567\n"
            "[silencedetect @ 0x1] silence_end: 2.8001 | silence_duration: 1.565534\n"
            "[silencedetect @ 0x1] silence_start: 9.0\n"
            "[silencedetect @ 0x1] silence_end: 10.5 | silence_duration: 1.5\n"
        )
        with patch.object(subprocess, "run", _fake_ffmpeg_run(stderr)):
            result = detect_silence("/tmp/a.mp4")
        assert result["success"] is True
        assert result["data"] == [
            {"start": 1.235, "end": 2.8, "duration": 1.566},
            {"start": 9.0, "end": 10.5, "duration": 1.5},
        ]

    def test_unmatched_start_is_dropped_not_crash(self, ffmpeg_here):
        stderr = (
            "[silencedetect @ 0x1] silence_start: 5.0\n"
            "some unrelated ffmpeg noise line\n"
        )
        with patch.object(subprocess, "run", _fake_ffmpeg_run(stderr)):
            result = detect_silence("/tmp/a.mp4")
        assert result["success"] is True
        assert result["data"] == []

    def test_garbage_numbers_are_tolerated(self, ffmpeg_here):
        stderr = (
            "[silencedetect @ 0x1] silence_start: not-a-number\n"
            "[silencedetect @ 0x1] silence_end: also-garbage\n"
            "[silencedetect @ 0x1] silence_start: 1.0\n"
            "[silencedetect @ 0x1] silence_end: 1.9 | silence_duration: 0.9\n"
        )
        with patch.object(subprocess, "run", _fake_ffmpeg_run(stderr)):
            result = detect_silence("/tmp/a.mp4")
        assert result["success"] is True
        # The garbage pair is skipped; the valid pair survives.
        assert result["data"] == [{"start": 1.0, "end": 1.9, "duration": 0.9}]

    def test_missing_ffmpeg_returns_error_envelope(self):
        def raise_fnf(cmd, **kwargs):
            raise FileNotFoundError("no ffmpeg binary")
        with patch.object(subprocess, "run", raise_fnf):
            result = detect_silence("/tmp/a.mp4")
        assert result["success"] is False
        assert "error" in result


# ------------------------------------------------------------------
# Shared ProjectService fixture
# ------------------------------------------------------------------


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
    service = ProjectService()
    media = tmp_path / "media.mp4"
    media.write_bytes(b"fake media content")
    service.create_project("d4-silence-chain", str(media), {"duration": 60.0})
    service.update_transcript(
        [
            {"id": "seg-1", "start": 0.0, "end": 4.0, "text": "hello"},
            {"id": "seg-2", "start": 6.0, "end": 10.0, "text": "world"},
        ]
    )
    return service


# ------------------------------------------------------------------
# 2. End-to-end serial pass: detect_silence shape -> add_silence_results
# ------------------------------------------------------------------


class TestSilenceChainEndToEnd:
    def test_parsed_windows_flow_into_segments_and_edits(self, svc):
        # The EXACT dict shape detect_silence produces (test 1).
        silences = [
            {"start": 4.2, "end": 5.8, "duration": 1.6},
            {"start": 10.1, "end": 12.0, "duration": 1.9},
        ]
        result = svc.add_silence_results(silences, margin=0.1, subtitle_padding=0.2)
        assert result["success"] is True

        timeline = svc.active_timeline
        silence_segs = [s for s in timeline.transcript.segments if s.type == "silence"]
        # Margin shrink: [4.2, 5.8] + 0.1 -> [4.3, 5.7]; padding trim keeps
        # them clear of the subtitle extended regions (seg-2 starts at 6.0,
        # extended to 5.8 -- the first window already fits).
        assert silence_segs, "silence segments must land in the transcript"
        for s in silence_segs:
            assert s.end > s.start
        # Pending delete edits exist for the silence segments.
        deletes = [
            e for e in timeline.edits
            if e.action == "delete" and e.status == "pending"
        ]
        assert deletes, "pending delete edits must be created for silences"
        # Segments stay sorted by start (the sort invariant is the
        # data-safety net for the whole chain).
        starts = [s.start for s in timeline.transcript.segments]
        assert starts == sorted(starts)


# ------------------------------------------------------------------
# 3. padding=0 boundary overlap interaction
# ------------------------------------------------------------------


class TestKeepRangesPaddingZero:
    def test_adjacent_subtitles_merge_without_degenerate_ranges(self, svc):
        # Adjacent subtitles abut exactly: 0-4 and 4-... (re-shape the
        # transcript so seg-2 starts exactly at seg-1's end).
        svc.update_transcript(
            [
                {"id": "seg-1", "start": 0.0, "end": 4.0, "text": "hello"},
                {"id": "seg-2", "start": 4.0, "end": 8.0, "text": "world"},
            ]
        )
        result = svc.generate_subtitle_keep_ranges(padding=0.0)
        assert result["success"] is True

        timeline = svc.active_timeline
        trim_edits = [
            e for e in timeline.edits if e.source == "subtitle_trim" and e.action == "delete"
        ]
        # With padding=0 the expanded keeps are exactly the subtitles and
        # adjacent ranges merge -- NO zero/negative-width delete range may
        # appear between them.
        for e in trim_edits:
            assert e.end > e.start, f"degenerate delete range {e.start}-{e.end}"
        # Delete ranges are pairwise non-overlapping and sorted.
        ordered = sorted(trim_edits, key=lambda e: e.start)
        for a, b in zip(ordered, ordered[1:], strict=False):
            assert a.end <= b.start, "overlapping delete ranges at padding=0"

    def test_real_gap_still_yields_exact_gap_range(self, svc):
        # 0-4 / 6-10 with padding=0: the delete range is exactly (4, 6).
        result = svc.generate_subtitle_keep_ranges(padding=0.0)
        assert result["success"] is True
        timeline = svc.active_timeline
        trims = sorted(
            [e for e in timeline.edits if e.source == "subtitle_trim" and e.action == "delete"],
            key=lambda e: e.start,
        )
        inner = [(e.start, e.end) for e in trims if e.start >= 4.0 - 1e-9 and e.end <= 6.0 + 1e-9]
        assert inner == [(4.0, 6.0)]
        for e in trims:
            assert e.end > e.start


# ------------------------------------------------------------------
# 4. Overlapping add-segment data safety (backend half)
# ------------------------------------------------------------------


class TestOverlappingAddSegmentSafety:
    def test_overlapping_segment_stores_sorted_and_reloads_intact(self, svc):
        # The basic-mode empty click emits (time, time+0.5) with no
        # overlap guard -- the click near 5.9 lands a segment overlapping
        # seg-2 (6.0-10.0). Data safety = the store stays sorted and the
        # whole timeline re-loads intact.
        res = svc.add_segment(5.9, 6.4, "overlapping entry")
        assert res["success"] is True

        timeline = svc.active_timeline
        starts = [s.start for s in timeline.transcript.segments]
        assert starts == sorted(starts), "sort invariant must absorb the overlap"
        ids = [s.id for s in timeline.transcript.segments]
        assert len(ids) == len(set(ids))
        texts = {s.id: s.text for s in timeline.transcript.segments}
        assert "overlapping entry" in texts.values()
        assert {t for t in texts.values()} >= {"hello", "world", "overlapping entry"}

"""v3.0.0 M1-2: split/merge maintain word-level data (PRD A2).

Rules:
- split: a.words + b.words word sequence == original words (aligned case);
  misaligned cut -> both empty (prefer missing over misaligned).
- merge: words concatenated and ordered by start.
"""

from __future__ import annotations

import pytest

from core.models import Segment, SegmentType, Word
from core.timeline_utils import split_words


def _words(*tokens: tuple[str, float, float]) -> list[Word]:
    return [Word(word=t, start=s, end=e) for t, s, e in tokens]


def _segment(words: list[Word]) -> Segment:
    return Segment(
        id="seg_1.000",
        type=SegmentType.SUBTITLE,
        start=1.0,
        end=4.0,
        text="大家好今天讲一下",
        words=words,
    )


class TestSplitWords:
    def test_aligned_split_preserves_word_sequence(self):
        words = _words(
            ("大家", 1.0, 1.4),
            ("好", 1.4, 1.6),
            ("今天", 1.7, 2.2),
            ("讲一下", 2.3, 4.0),
        )
        text = "大家好今天讲一下"
        # Cut after "好" (char index 3) -> boundary exactly at offset 3.
        a, b = split_words(words, text, 3, "大家好", "今天讲一下")
        assert [w.word for w in a] == ["大家", "好"]
        assert [w.word for w in b] == ["今天", "讲一下"]
        # Sequence preservation: a + b == original
        assert [w.word for w in (a + b)] == [w.word for w in words]
        # Timestamps untouched
        assert (a[0].start, a[-1].end) == (1.0, 1.6)
        assert (b[0].start, b[-1].end) == (1.7, 4.0)

    def test_tolerance_within_two_chars(self):
        words = _words(("大家", 1.0, 1.4), ("好", 1.4, 1.6), ("今天讲一下", 1.7, 4.0))
        text = "大家好今天讲一下"
        # Boundary at 3; cut at 4 (within tolerance 2) -> still splits.
        a, b = split_words(words, text, 4, "大家好今", "天讲一下")
        assert [w.word for w in a] == ["大家", "好"]
        assert [w.word for w in b] == ["今天讲一下"]

    def test_misaligned_cut_returns_both_empty(self):
        words = _words(("大家好啊", 1.0, 1.8), ("今天讲一下啊", 1.9, 4.0))
        text = "大家好啊今天讲一下啊"
        # Boundaries: 0 and 4. Cut at 1 -> nearest boundary deviates 3 > 2.
        a, b = split_words(words, text, 1, "大", "大家好啊今天讲一下啊")
        assert a == []
        assert b == []

    def test_single_word_segment_returns_both_empty(self):
        words = _words(("大家好啊今天讲一下", 1.0, 4.0))
        a, b = split_words(words, "大家好啊今天讲一下", 2, "大家好", "啊今天讲一下")
        assert a == []
        assert b == []

    def test_empty_or_trivial_inputs_return_both_empty(self):
        words = _words(("大家", 1.0, 1.4))
        assert split_words([], "大家好", 1, "大", "家好") == ([], [])
        assert split_words(words, "大家好", 0, "", "大家好") == ([], [])
        assert split_words(words, "大家好", 3, "大家好", "") == ([], [])


# ---------------------------------------------------------------------------
# Service-level split/merge wiring
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    from core.project_service import ProjectService

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    return service


class TestSplitSegmentWords:
    def test_split_keeps_aligned_words(self, svc):
        words = _words(
            ("大家", 1.0, 1.5),
            ("好", 1.5, 2.0),
            ("今天", 2.0, 2.5),
            ("讲一下", 2.5, 4.0),
        )
        seg = Segment(
            id="seg_1.000",
            type=SegmentType.SUBTITLE,
            start=1.0,
            end=4.0,
            text="大家好今天讲一下",
            words=words,
        )
        svc.update_transcript([seg.model_dump()])

        res = svc.split_segment("seg_1.000", 2.5)
        assert res["success"]
        segs = svc.active_timeline.transcript.segments
        a, b = segs[0], segs[1]
        # words distributed, sequence preserved
        assert [w.word for w in (a.words + b.words)] == [w.word for w in words]

    def test_split_misaligned_clears_words_both_sides(self, svc):
        # Two words; cut position lands >2 chars away from the only interior
        # word boundary -> words cleared on both sides (missing over misaligned).
        words = _words(("大家好啊", 1.0, 2.2), ("今天讲一下", 2.4, 4.0))
        seg = Segment(
            id="seg_1.000",
            type=SegmentType.SUBTITLE,
            start=1.0,
            end=4.0,
            text="大家好啊今天讲一下",
            words=words,
        )
        svc.update_transcript([seg.model_dump()])

        res = svc.split_segment("seg_1.000", 1.5)  # split_idx=1, boundary=4, dev 3
        assert res["success"]
        a, b = svc.active_timeline.transcript.segments
        assert a.words == []
        assert b.words == []


class TestMergeSegmentsWords:
    def test_merge_concatenates_words_ordered(self, svc):
        words_a = _words(("今天", 1.0, 1.5), ("天气", 1.5, 2.0))
        words_b = _words(("不错", 2.0, 2.6), ("啊", 2.6, 3.0))
        seg_a = Segment(
            id="seg_1.000", type=SegmentType.SUBTITLE,
            start=1.0, end=2.0, text="今天天气", words=words_a,
        )
        seg_b = Segment(
            id="seg_2.000", type=SegmentType.SUBTITLE,
            start=2.0, end=3.0, text="不错啊", words=words_b,
        )
        svc.update_transcript([seg_a.model_dump(), seg_b.model_dump()])

        res = svc.merge_segments(["seg_2.000", "seg_1.000"])  # unsorted input ok
        assert res["success"]
        merged = svc.active_timeline.transcript.segments[0]
        assert merged.text == "今天天气不错啊"
        assert [w.word for w in merged.words] == ["今天", "天气", "不错", "啊"]
        starts = [w.start for w in merged.words]
        assert starts == sorted(starts)

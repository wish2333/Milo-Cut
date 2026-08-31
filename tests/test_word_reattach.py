"""v3.0.0 P4-1 M11-1: correction word reattachment (PRD D1.2).

Rules ("prefer missing over misaligned"):
- Local edits keep unchanged words with their original timestamps; text in
  uncovered regions gets synthesized words with interpolated timestamps.
- Similarity < 0.5 (or no reliable anchor word) -> [] (clear all words).
- No partial misalignment is ever emitted: the emitted word tokens always
  concatenate exactly to the new text.
"""

from __future__ import annotations

import pytest

from core.models import Segment, SegmentType, Word
from core.project_service import ProjectService
from core.timeline_utils import reattach_words


def _words(*tokens: tuple[str, float, float]) -> list[Word]:
    return [Word(word=t, start=s, end=e) for t, s, e in tokens]


# 大家(0,2) 好(2,3) 今天(3,5) 讲一下(5,8) in "大家好今天讲一下"
WORDS = _words(
    ("大家", 1.0, 1.4),
    ("好", 1.4, 1.6),
    ("今天", 1.7, 2.2),
    ("讲一下", 2.3, 4.0),
)
OLD_TEXT = "大家好今天讲一下"
SEG_START, SEG_END = 1.0, 4.5


class TestReattachWordsPure:
    def test_identical_text_returns_words_unchanged(self):
        result = reattach_words(WORDS, OLD_TEXT, SEG_START, SEG_END)
        assert result == WORDS
        assert [w.end for w in result] == [1.4, 1.6, 2.2, 4.0]

    def test_local_change_keeps_unchanged_timestamps(self):
        # 讲 -> 说 inside the last word: first three words untouched.
        new_text = "大家好今天说一下"
        result = reattach_words(WORDS, new_text, SEG_START, SEG_END)
        assert [w.word for w in result] == ["大家", "好", "今天", "说", "一", "下"]
        # Unchanged words keep exact original timestamps.
        assert (result[0].start, result[0].end) == (1.0, 1.4)
        assert (result[1].start, result[1].end) == (1.4, 1.6)
        assert (result[2].start, result[2].end) == (1.7, 2.2)
        # Synthesized tail fills up to the segment end.
        assert result[-1].end == SEG_END
        # Full coverage: emitted tokens concatenate exactly to the new text.
        assert "".join(w.word for w in result) == new_text

    def test_word_deletion_keeps_later_word_timestamps(self):
        # "今天" deleted from the text: "讲一下" survives with its old times.
        new_text = "大家好讲一下"
        result = reattach_words(WORDS, new_text, SEG_START, SEG_END)
        assert [w.word for w in result] == ["大家", "好", "讲一下"]
        assert (result[2].start, result[2].end) == (2.3, 4.0)
        assert "".join(w.word for w in result) == new_text

    def test_tail_append_interpolates_new_word(self):
        new_text = OLD_TEXT + "啊"
        result = reattach_words(WORDS, new_text, SEG_START, SEG_END)
        assert [w.word for w in result] == ["大家", "好", "今天", "讲一下", "啊"]
        assert all(
            (w.start, w.end) == (s, e)
            for w, (s, e) in zip(
                result[:4], [(1.0, 1.4), (1.4, 1.6), (1.7, 2.2), (2.3, 4.0)], strict=True
            )
        )
        assert (result[4].start, result[4].end) == (4.0, SEG_END)

    def test_punctuation_insert_between_words(self):
        # LLM adds a comma: every original word keeps its timestamps and the
        # comma is synthesized into the 1.6-1.7 gap between 好 and 今天.
        new_text = "大家好，今天讲一下"
        result = reattach_words(WORDS, new_text, SEG_START, SEG_END)
        assert [w.word for w in result] == ["大家", "好", "，", "今天", "讲一下"]
        assert (result[2].start, result[2].end) == (1.6, 1.7)
        assert (result[3].start, result[3].end) == (1.7, 2.2)
        assert (result[4].start, result[4].end) == (2.3, 4.0)

    def test_big_change_clears_all_words(self):
        result = reattach_words(WORDS, "这个问题完全不同啊", SEG_START, SEG_END)
        assert result == []

    def test_no_words_returns_empty(self):
        assert reattach_words([], OLD_TEXT, SEG_START, SEG_END) == []

    def test_empty_new_text_returns_empty(self):
        assert reattach_words(WORDS, "", SEG_START, SEG_END) == []

    def test_no_anchor_word_returns_empty(self):
        # Single coarse word: no word fits fully inside the equal region ->
        # no reliable timestamp anchor -> prefer clearing over fabricating.
        coarse = _words(("大家好啊今天讲一下", 1.0, 4.0))
        result = reattach_words(coarse, "大家好啊今天讲一哈", 1.0, 4.0)
        assert result == []

    def test_interior_replacement_spreads_across_original_span(self):
        # Replace the interior word "今天": synthesized tokens interpolate
        # between the surrounding kept words' timestamps.
        new_text = "大家好聊天讲一下"
        result = reattach_words(WORDS, new_text, SEG_START, SEG_END)
        assert [w.word for w in result] == ["大家", "好", "聊", "天", "讲一下"]
        assert (result[0].start, result[0].end) == (1.0, 1.4)
        assert (result[4].start, result[4].end) == (2.3, 4.0)
        # Interpolated block sits within [prev_end, next_start].
        assert result[2].start >= 1.6
        assert result[3].end <= 2.3
        assert "".join(w.word for w in result) == new_text


# ---------------------------------------------------------------------------
# Service-level wiring: correction accept / batch apply reattach words
# ---------------------------------------------------------------------------


@pytest.fixture
def svc(monkeypatch, tmp_path):
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)

    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    return service


def _segment_with_words() -> Segment:
    return Segment(
        id="seg-0001",
        type=SegmentType.SUBTITLE,
        start=SEG_START,
        end=4.0,
        text=OLD_TEXT,
        words=WORDS,
    )


def _corrected_apply(svc, corrected_text: str):
    seg = _segment_with_words()
    svc._current = svc._current.model_copy(
        update={
            "timelines": [
                svc._current.timelines[0].model_copy(
                    update={
                        "transcript": svc._current.timelines[0].transcript.model_copy(
                            update={"segments": [seg]}
                        )
                    }
                )
            ]
        }
    )
    return svc.correction.apply_subtitle_corrections(
        [{"segment_id": seg.id, "corrected_text": corrected_text, "confidence": 0.9}]
    )


class TestCorrectionApplyWordReattach:
    def test_apply_reattaches_words(self, svc):
        res = _corrected_apply(svc, "大家好今天说一下")
        assert res["success"]
        seg = svc.active_timeline.transcript.segments[0]
        assert seg.text == "大家好今天说一下"
        assert [w.word for w in seg.words] == ["大家", "好", "今天", "说", "一", "下"]
        # Unchanged words keep original timestamps on disk-bound models.
        assert (seg.words[0].start, seg.words[0].end) == (1.0, 1.4)
        assert (seg.words[2].start, seg.words[2].end) == (1.7, 2.2)

    def test_apply_big_change_clears_words(self, svc):
        res = _corrected_apply(svc, "这句话已经面目全非了啊")
        assert res["success"]
        seg = svc.active_timeline.transcript.segments[0]
        assert seg.words == []

    def test_apply_segment_without_words_keeps_empty(self, svc):
        seg = Segment(
            id="seg-0001",
            type=SegmentType.SUBTITLE,
            start=SEG_START,
            end=4.0,
            text=OLD_TEXT,
            words=[],
        )
        svc._current = svc._current.model_copy(
            update={
                "timelines": [
                    svc._current.timelines[0].model_copy(
                        update={
                            "transcript": svc._current.timelines[0].transcript.model_copy(
                                update={"segments": [seg]}
                            )
                        }
                    )
                ]
            }
        )
        res = svc.correction.apply_subtitle_corrections(
            [{"segment_id": seg.id, "corrected_text": "大家好今天说一下", "confidence": 0.9}]
        )
        assert res["success"]
        assert svc.active_timeline.transcript.segments[0].words == []


class TestCorrectionAcceptWordReattach:
    def test_accept_reattaches_words(self, svc):
        seg = _segment_with_words()
        svc._current = svc._current.model_copy(
            update={
                "timelines": [
                    svc._current.timelines[0].model_copy(
                        update={
                            "transcript": svc._current.timelines[0].transcript.model_copy(
                                update={"segments": [seg]}
                            )
                        }
                    )
                ]
            }
        )
        store = svc.correction.store_subtitle_corrections(
            [
                {
                    "segment_id": seg.id,
                    "corrected_text": "大家好今天说一下",
                    "changes": ["错字"],
                    "category": "homophone",
                    "confidence": 0.9,
                }
            ],
            "default",
        )
        assert store["success"] and store["data"]["stored_count"] == 1

        results = [
            r
            for r in svc.active_timeline.analysis.results
            if r.type == "llm_subtitle_correction"
        ]
        res = svc.correction.accept_subtitle_correction(results[0].id)
        assert res["success"]

        accepted = svc.active_timeline.transcript.segments[0]
        assert accepted.text == "大家好今天说一下"
        assert [w.word for w in accepted.words] == ["大家", "好", "今天", "说", "一", "下"]
        assert (accepted.words[2].start, accepted.words[2].end) == (1.7, 2.2)

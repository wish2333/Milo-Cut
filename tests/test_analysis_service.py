"""Tests for core.analysis_service."""

from core.analysis_service import detect_errors, detect_fillers, run_full_analysis
from core.models import Segment, SegmentType


class TestDetectFillers:
    def test_no_fillers(self, sample_segments):
        # Only seg-0003 has "Filler" but filler_words are Chinese
        results = detect_fillers(sample_segments, filler_words=["嗯", "啊"])
        assert len(results) == 0

    def test_chinese_fillers(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="嗯这个功能很好"),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=5.0, end=10.0, text="然后我们可以看到"),
            Segment(id="s3", type=SegmentType.SUBTITLE, start=10.0, end=15.0, text="正常文本无填充词"),
        ]
        results = detect_fillers(segments, filler_words=["嗯", "然后"])
        assert len(results) == 2
        assert results[0].type == "filler"
        assert results[0].segment_ids == ["s1"]
        assert "嗯" in results[0].detail
        assert results[1].segment_ids == ["s2"]

    def test_longest_first_matching(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="怎么说呢这个"),
        ]
        results = detect_fillers(segments, filler_words=["怎么", "怎么说呢"])
        assert len(results) == 1
        assert "怎么说呢" in results[0].detail

    def test_skips_silence_segments(self):
        segments = [
            Segment(id="s1", type=SegmentType.SILENCE, start=0.0, end=5.0, text=""),
        ]
        results = detect_fillers(segments, filler_words=["嗯"])
        assert len(results) == 0

    def test_confidence(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="嗯好"),
        ]
        results = detect_fillers(segments, filler_words=["嗯"])
        assert results[0].confidence == 0.90


class TestDetectErrors:
    def test_no_errors(self, sample_segments):
        results = detect_errors(sample_segments, trigger_words=["不存在的词"])
        assert len(results) == 0

    def test_error_trigger_with_lookahead(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="正常开始"),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=5.0, end=10.0, text="不对重来说错了"),
            Segment(id="s3", type=SegmentType.SUBTITLE, start=10.0, end=15.0, text="重新说的内容"),
            Segment(id="s4", type=SegmentType.SUBTITLE, start=15.0, end=20.0, text="继续"),
            Segment(id="s5", type=SegmentType.SUBTITLE, start=20.0, end=25.0, text="再继续"),
        ]
        results = detect_errors(segments, trigger_words=["不对"], lookahead=3)
        assert len(results) == 1
        assert results[0].type == "error"
        assert results[0].segment_ids == ["s2", "s3", "s4", "s5"]

    def test_lookahead_boundary(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="重来"),
            Segment(id="s2", type=SegmentType.SUBTITLE, start=5.0, end=10.0, text="next"),
        ]
        results = detect_errors(segments, trigger_words=["重来"], lookahead=3)
        assert len(results) == 1
        # Only 2 segments total, so lookahead captures s1 + s2
        assert results[0].segment_ids == ["s1", "s2"]

    def test_confidence(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="不对"),
        ]
        results = detect_errors(segments, trigger_words=["不对"])
        assert results[0].confidence == 0.85


class TestRunFullAnalysis:
    def test_combined_results(self):
        segments = [
            Segment(id="s1", type=SegmentType.SUBTITLE, start=0.0, end=5.0, text="嗯不对重来"),
        ]
        settings = {
            "filler_words": ["嗯"],
            "error_trigger_words": ["不对"],
        }
        results = run_full_analysis(segments, settings)
        types = {r.type for r in results}
        assert "filler" in types
        assert "error" in types

    def test_empty_settings(self, sample_segments):
        results = run_full_analysis(sample_segments, {})
        assert len(results) == 0

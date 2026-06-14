"""Tests for Phase 4c: P2 highlight extraction + P3 semantic search."""

from __future__ import annotations

import json

from core.export_service import detect_jump_cuts, get_highlight_ranges
from core.llm_service import analyze_highlights, semantic_search

# ================================================================
# P2: Jump cut detection
# ================================================================


class TestDetectJumpCuts:
    def test_no_jump_cuts(self):
        """Adjacent segments with small gaps produce no jump cuts."""
        segs = [
            {"start": 0.0, "end": 5.0},
            {"start": 5.5, "end": 10.0},
            {"start": 10.3, "end": 15.0},
        ]
        cuts = detect_jump_cuts(segs, threshold_s=2.0)
        assert len(cuts) == 0

    def test_single_jump_cut(self):
        """One large gap detected."""
        segs = [
            {"start": 0.0, "end": 5.0},
            {"start": 30.0, "end": 35.0},  # 25s gap
        ]
        cuts = detect_jump_cuts(segs, threshold_s=2.0)
        assert len(cuts) == 1
        assert cuts[0]["index"] == 0
        assert cuts[0]["gap_duration"] == 25.0
        assert cuts[0]["from_end"] == 5.0
        assert cuts[0]["to_start"] == 30.0

    def test_multiple_jump_cuts(self):
        """Multiple gaps detected."""
        segs = [
            {"start": 0.0, "end": 5.0},
            {"start": 20.0, "end": 25.0},  # 15s gap
            {"start": 26.0, "end": 30.0},  # 1s gap -- not a jump cut
            {"start": 60.0, "end": 65.0},  # 30s gap
        ]
        cuts = detect_jump_cuts(segs, threshold_s=2.0)
        assert len(cuts) == 2
        assert cuts[0]["index"] == 0
        assert cuts[1]["index"] == 2

    def test_empty_or_single(self):
        """Empty or single segment produces no jump cuts."""
        assert detect_jump_cuts([]) == []
        assert detect_jump_cuts([{"start": 0.0, "end": 5.0}]) == []

    def test_custom_threshold(self):
        """Custom threshold affects detection."""
        segs = [
            {"start": 0.0, "end": 5.0},
            {"start": 8.0, "end": 10.0},  # 3s gap
        ]
        assert len(detect_jump_cuts(segs, threshold_s=2.0)) == 1
        assert len(detect_jump_cuts(segs, threshold_s=5.0)) == 0


# ================================================================
# P2: get_highlight_ranges
# ================================================================


class TestGetHighlightRanges:
    def test_extract_keep_edits(self):
        """Extract ranges from llm_highlight keep edits."""
        edits = [
            {"action": "keep", "source": "llm_highlight", "start": 0.0, "end": 5.0},
            {"action": "keep", "source": "llm_highlight", "start": 10.0, "end": 15.0},
            {"action": "delete", "source": "manual", "start": 5.0, "end": 10.0},
        ]
        ranges = get_highlight_ranges(edits)
        assert len(ranges) == 2
        assert ranges[0] == (0.0, 5.0)
        assert ranges[1] == (10.0, 15.0)

    def test_no_highlights(self):
        """No highlight edits returns empty."""
        edits = [
            {"action": "delete", "source": "manual", "start": 0.0, "end": 5.0},
        ]
        assert get_highlight_ranges(edits) == []

    def test_sorted_by_start(self):
        """Ranges are sorted by start time."""
        edits = [
            {"action": "keep", "source": "llm_highlight", "start": 20.0, "end": 25.0},
            {"action": "keep", "source": "llm_highlight", "start": 0.0, "end": 5.0},
        ]
        ranges = get_highlight_ranges(edits)
        assert ranges[0] == (0.0, 5.0)
        assert ranges[1] == (20.0, 25.0)


# ================================================================
# P2: analyze_highlights (mocked LLM)
# ================================================================


class TestAnalyzeHighlights:
    def test_not_configured(self):
        from core.models import LlmConfig, LlmProvider

        config = LlmConfig(provider=LlmProvider.CUSTOM, base_url="", api_key="", model="")
        result = analyze_highlights(
            [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}],
            config=config,
        )
        assert result["success"] is False

    def test_empty_segments(self):
        from core.models import LlmConfig, LlmProvider

        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = analyze_highlights([], config=config)
        assert result["success"] is False

    def test_mock_llm_response(self, monkeypatch):
        """Full flow with mocked LLM."""
        from core.models import LlmConfig, LlmProvider

        segments = [
            {"id": "s1", "text": "核心观点是AI很重要", "start": 0.0, "end": 5.0},
            {"id": "s2", "text": "嗯然后那个", "start": 5.0, "end": 8.0},
            {"id": "s3", "text": "实验数据显示性能提升50%", "start": 8.0, "end": 15.0},
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": "s1", "highlight_reason": "核心论点", "density": "high"},
                        {"segment_id": "s3", "highlight_reason": "关键数据", "density": "high"},
                    ]),
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = analyze_highlights(segments, target_duration_minutes=1, config=config)
        assert result["success"] is True
        assert len(result["data"]["results"]) == 2
        assert result["data"]["total_highlight_duration"] > 0

    def test_duration_trimming(self, monkeypatch):
        """Results are trimmed when exceeding target duration."""
        from core.models import LlmConfig, LlmProvider

        # 6 segments of 30s each = 180s total. Target 60s.
        segments = [
            {"id": f"s{i}", "text": f"content {i}", "start": i * 30.0, "end": (i + 1) * 30.0}
            for i in range(6)
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": f"s{i}", "highlight_reason": f"reason {i}", "density": "high"}
                        for i in range(6)
                    ]),
                    "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = analyze_highlights(segments, target_duration_minutes=1, config=config)
        assert result["success"] is True
        # Should trim to roughly 2 segments (60s) with ±20% tolerance
        total = result["data"]["total_highlight_duration"]
        assert total <= 72.0  # 60 * 1.2


# ================================================================
# P3: semantic_search (mocked LLM)
# ================================================================


class TestSemanticSearch:
    def test_not_configured(self):
        from core.models import LlmConfig, LlmProvider

        config = LlmConfig(provider=LlmProvider.CUSTOM, base_url="", api_key="", model="")
        result = semantic_search(
            "query",
            [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}],
            config=config,
        )
        assert result["success"] is False

    def test_empty_query(self):
        from core.models import LlmConfig, LlmProvider

        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = semantic_search(
            "",
            [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}],
            config=config,
        )
        assert result["success"] is False

    def test_mock_llm_search(self, monkeypatch):
        """Full search with mocked LLM."""
        from core.models import LlmConfig, LlmProvider

        segments = [
            {"id": "s1", "text": "性能优化很重要", "start": 0.0, "end": 3.0},
            {"id": "s2", "text": "今天天气不错", "start": 3.0, "end": 6.0},
            {"id": "s3", "text": "缓存策略提升响应速度", "start": 6.0, "end": 10.0},
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": "s1", "relevance": 0.9, "match_reason": "性能相关"},
                        {"segment_id": "s3", "relevance": 0.8, "match_reason": "优化策略"},
                    ]),
                    "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = semantic_search("性能优化", segments, top_k=5, config=config)
        assert result["success"] is True
        assert len(result["data"]["results"]) == 2
        # Sorted by relevance descending
        assert result["data"]["results"][0]["relevance"] >= result["data"]["results"][1]["relevance"]
        assert result["data"]["query"] == "性能优化"

    def test_top_k_limit(self, monkeypatch):
        """Results are limited to top_k."""
        from core.models import LlmConfig, LlmProvider

        segments = [
            {"id": f"s{i}", "text": f"content {i}", "start": i * 3.0, "end": (i + 1) * 3.0}
            for i in range(10)
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": f"s{i}", "relevance": 1.0 - i * 0.1, "match_reason": "match"}
                        for i in range(10)
                    ]),
                    "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="test",
            model="test",
        )
        result = semantic_search("test", segments, top_k=3, config=config)
        assert result["success"] is True
        assert len(result["data"]["results"]) <= 3

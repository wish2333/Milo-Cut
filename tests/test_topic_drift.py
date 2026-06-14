"""Unit tests for topic drift analysis (core.llm_service + core.models)."""

import threading
from unittest.mock import patch

import pytest

from core.llm_service import (
    _build_topic_drift_prompt,
    _parse_topic_drift_response,
    analyze_topic_drift,
)
from core.models import (
    LlmConfig,
    LlmProvider,
    Project,
    TopicDriftData,
    TopicDriftResult,
)

# ------------------------------------------------------------------
# TopicDriftResult / TopicDriftData models
# ------------------------------------------------------------------


class TestTopicDriftModels:
    def test_topic_drift_result_defaults(self) -> None:
        r = TopicDriftResult(segment_id="s1")
        assert r.segment_id == "s1"
        assert r.topic == ""
        assert r.relevance == 1.0
        assert r.confidence == 1.0
        assert r.reason == ""

    def test_topic_drift_result_frozen(self) -> None:
        from pydantic import ValidationError

        r = TopicDriftResult(segment_id="s1", relevance=0.5)
        with pytest.raises(ValidationError):
            r.relevance = 0.9  # type: ignore

    def test_topic_drift_data_defaults(self) -> None:
        d = TopicDriftData()
        assert d.topic_description == ""
        assert d.results == []
        assert d.transcript_hash == ""
        assert d.last_run is None
        assert d.token_usage == {}

    def test_topic_drift_data_with_results(self) -> None:
        r = TopicDriftResult(segment_id="s1", relevance=0.8, topic="intro")
        d = TopicDriftData(
            topic_description="AI",
            results=[r],
            transcript_hash="abc",
            token_usage={"total_tokens": 100},
        )
        assert len(d.results) == 1
        assert d.results[0].relevance == 0.8
        assert d.token_usage["total_tokens"] == 100

    def test_project_v2_schema_no_topic_drift(self) -> None:
        """v2 Project schema does not have flat topic_drift field (moved to timeline)."""
        p = Project()
        assert p.schema_version == 2
        assert not hasattr(p, "topic_drift")  # removed in v2
        assert hasattr(p, "timelines")
        assert len(p.timelines) == 1  # auto-created default

    def test_project_round_trip_preserves_timelines(self) -> None:
        """v2 Project round-trips through dump/validate preserving timeline data."""
        p = Project()
        dumped = p.model_dump()
        restored = Project.model_validate(dumped)
        assert restored.schema_version == 2
        assert len(restored.timelines) == 1
        assert restored.active_timeline_id == "default"


# ------------------------------------------------------------------
# _parse_topic_drift_response
# ------------------------------------------------------------------


class TestParseTopicDriftResponse:
    def test_bare_json(self) -> None:
        content = '[{"segment_id": "s1", "topic": "intro", "relevance": 0.9}]'
        results = _parse_topic_drift_response(content)
        assert len(results) == 1
        assert results[0]["segment_id"] == "s1"
        assert results[0]["relevance"] == 0.9

    def test_markdown_code_block(self) -> None:
        content = 'Here are results:\n```json\n[{"segment_id": "s1", "relevance": 0.5}]\n```\n'
        results = _parse_topic_drift_response(content)
        assert len(results) == 1
        assert results[0]["segment_id"] == "s1"

    def test_missing_fields(self) -> None:
        content = '[{"segment_id": "s1"}]'
        results = _parse_topic_drift_response(content)
        assert len(results) == 1
        assert results[0]["topic"] == ""
        assert results[0]["relevance"] == 1.0  # default

    def test_relevance_clamp_high(self) -> None:
        content = '[{"segment_id": "s1", "relevance": 1.5}]'
        results = _parse_topic_drift_response(content)
        assert results[0]["relevance"] == 1.0

    def test_relevance_clamp_negative(self) -> None:
        content = '[{"segment_id": "s1", "relevance": -0.3}]'
        results = _parse_topic_drift_response(content)
        assert results[0]["relevance"] == 0.0

    def test_invalid_json_returns_empty(self) -> None:
        content = "This is not JSON at all"
        results = _parse_topic_drift_response(content)
        assert results == []

    def test_missing_segment_id_skipped(self) -> None:
        content = '[{"topic": "no id"}, {"segment_id": "s1"}]'
        results = _parse_topic_drift_response(content)
        assert len(results) == 1
        assert results[0]["segment_id"] == "s1"

    def test_confidence_clamp(self) -> None:
        content = '[{"segment_id": "s1", "confidence": 2.0}]'
        results = _parse_topic_drift_response(content)
        assert results[0]["confidence"] == 1.0

    def test_non_dict_items_skipped(self) -> None:
        content = '["string", 42, {"segment_id": "s1"}]'
        results = _parse_topic_drift_response(content)
        assert len(results) == 1
        assert results[0]["segment_id"] == "s1"


# ------------------------------------------------------------------
# _build_topic_drift_prompt
# ------------------------------------------------------------------


class TestBuildTopicDriftPrompt:
    def test_includes_topic_description(self) -> None:
        segs = [{"id": "s1", "start": 0, "end": 5, "text": "hello"}]
        prompt = _build_topic_drift_prompt(segs, "AI presentation")
        assert "AI presentation" in prompt

    def test_includes_segment_ids(self) -> None:
        segs = [
            {"id": "s1", "start": 0, "end": 5, "text": "first"},
            {"id": "s2", "start": 5, "end": 10, "text": "second"},
        ]
        prompt = _build_topic_drift_prompt(segs, "topic")
        assert "[s1]" in prompt
        assert "[s2]" in prompt
        assert "first" in prompt
        assert "second" in prompt

    def test_empty_topic_uses_default(self) -> None:
        segs = [{"id": "s1", "start": 0, "end": 5, "text": "x"}]
        prompt = _build_topic_drift_prompt(segs, "")
        assert "未指定" in prompt


# ------------------------------------------------------------------
# analyze_topic_drift (with mocked LLM)
# ------------------------------------------------------------------


_TEST_CONFIG = LlmConfig(
    provider=LlmProvider.CUSTOM,
    base_url="http://fake",
    api_key="key",
    model="model",
)


class TestAnalyzeTopicDrift:
    def test_unconfigured_returns_error(self) -> None:
        result = analyze_topic_drift([{"id": "s1", "start": 0, "end": 1, "text": "x"}])
        assert result["success"] is False
        assert "not configured" in result["error"]

    def test_empty_segments_returns_error(self) -> None:
        result = analyze_topic_drift([], config=_TEST_CONFIG)
        assert result["success"] is False
        assert "No segments" in result["error"]

    def test_successful_analysis(self) -> None:
        mock_response = {
            "success": True,
            "data": {
                "content": '[{"segment_id": "s1", "topic": "intro", "relevance": 0.9}]',
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        }
        with patch("core.llm_service.call_llm", return_value=mock_response):
            result = analyze_topic_drift(
                [{"id": "s1", "start": 0, "end": 5, "text": "hello"}],
                "test topic",
                config=_TEST_CONFIG,
            )
        assert result["success"] is True
        assert len(result["data"]["results"]) == 1
        assert result["data"]["results"][0]["segment_id"] == "s1"
        assert result["data"]["token_usage"]["total_tokens"] == 150

    def test_chunk_callback_invoked(self) -> None:
        mock_response = {
            "success": True,
            "data": {
                "content": '[{"segment_id": "s1", "relevance": 0.8}]',
                "usage": {"total_tokens": 10},
            },
        }
        chunks_received: list[dict] = []
        with patch("core.llm_service.call_llm", return_value=mock_response):
            result = analyze_topic_drift(
                [{"id": "s1", "start": 0, "end": 5, "text": "hello"}],
                config=_TEST_CONFIG,
                chunk_callback=lambda r: chunks_received.extend(r),
            )
        assert result["success"] is True
        assert len(chunks_received) >= 1

    def test_cancel_event(self) -> None:
        cancel = threading.Event()
        cancel.set()
        result = analyze_topic_drift(
            [{"id": "s1", "start": 0, "end": 5, "text": "hello"}],
            config=_TEST_CONFIG,
            cancel_event=cancel,
        )
        assert result["success"] is False
        assert result["error"] == "Cancelled"

    def test_overlap_dedup_keeps_last(self) -> None:
        """Segments in overlap region should be deduplicated, keeping last value."""
        responses = [
            {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s_overlap", "relevance": 0.9}]',
                    "usage": {"total_tokens": 10},
                },
            },
            {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s_overlap", "relevance": 0.2}]',
                    "usage": {"total_tokens": 10},
                },
            },
            {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s_overlap", "relevance": 0.1}]',
                    "usage": {"total_tokens": 10},
                },
            },
        ]
        call_count = [0]

        def mock_call(*args, **kwargs):
            r = responses[call_count[0]]
            call_count[0] += 1
            return r

        # Segments spanning 3 chunks with overlap
        segs = [
            {"id": f"s{i}", "start": i * 100, "end": i * 100 + 5, "text": f"text{i}"}
            for i in range(8)
        ]
        with patch("core.llm_service.call_llm", side_effect=mock_call):
            result = analyze_topic_drift(segs, "topic", config=_TEST_CONFIG)

        assert result["success"] is True
        # Only one unique segment_id "s_overlap" across all chunks
        unique_ids = {r["segment_id"] for r in result["data"]["results"]}
        assert unique_ids == {"s_overlap"}
        # Should keep the last occurrence (0.1)
        assert result["data"]["results"][0]["relevance"] == 0.1

    def test_llm_failure_continues_to_next_chunk(self) -> None:
        """If one chunk fails, analysis should continue to next chunk."""
        responses = [
            {"success": False, "error": "timeout"},
            {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s1", "relevance": 0.5}]',
                    "usage": {"total_tokens": 10},
                },
            },
            {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s1", "relevance": 0.5}]',
                    "usage": {"total_tokens": 10},
                },
            },
        ]
        call_count = [0]

        def mock_call(*args, **kwargs):
            r = responses[call_count[0]]
            call_count[0] += 1
            return r

        segs = [
            {"id": f"s{i}", "start": i * 100, "end": i * 100 + 5, "text": f"text{i}"}
            for i in range(8)
        ]
        with patch("core.llm_service.call_llm", side_effect=mock_call):
            result = analyze_topic_drift(segs, "topic", config=_TEST_CONFIG)

        assert result["success"] is True
        assert len(result["data"]["results"]) >= 1

    def test_progress_callback(self) -> None:
        mock_response = {
            "success": True,
            "data": {
                "content": '[{"segment_id": "s1", "relevance": 0.5}]',
                "usage": {"total_tokens": 10},
            },
        }
        progress_calls: list[tuple[float, str]] = []
        with patch("core.llm_service.call_llm", return_value=mock_response):
            analyze_topic_drift(
                [{"id": "s1", "start": 0, "end": 5, "text": "hello"}],
                config=_TEST_CONFIG,
                progress_cb=lambda pct, msg: progress_calls.append((pct, msg)),
            )
        # Should have at least start and end progress calls
        assert len(progress_calls) >= 1
        assert progress_calls[-1][0] == 100.0  # ends at 100%

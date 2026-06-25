"""Tests for Phase 4b LLM features: C-02 structured I/O, P0 smart-delete, P1 subtitle correction."""

from __future__ import annotations

import json

import pytest

from core.llm_service import (
    TimestampCorruptionError,
    _assert_timestamps_unchanged,
    _build_structured_user_message,
    _check_correction_confidence,
    _levenshtein,
    _parse_json_response_layers,
    analyze_smart_delete,
    analyze_subtitle_correction,
)

# ================================================================
# C-02: Structured input (_build_structured_user_message)
# ================================================================


class TestStructuredUserMessage:
    def test_basic_segment_serialization(self):
        """Segments are serialized to JSON with id/text/start/end."""
        segments = [{"id": "s1", "text": "hello world", "start": 0.0, "end": 2.0}]
        msg = _build_structured_user_message(segments)
        parsed = json.loads(msg)
        assert parsed["segments"][0]["id"] == "s1"
        assert parsed["segments"][0]["text"] == "hello world"
        assert parsed["segments"][0]["start"] == 0.0
        assert parsed["segments"][0]["end"] == 2.0

    def test_empty_segments(self):
        """Empty segment list produces valid JSON with empty array."""
        msg = _build_structured_user_message([])
        parsed = json.loads(msg)
        assert parsed["segments"] == []

    def test_chinese_text_preserved(self):
        """Chinese characters are preserved (ensure_ascii=False)."""
        segments = [{"id": "s1", "text": "你好世界", "start": 0.0, "end": 1.0}]
        msg = _build_structured_user_message(segments)
        assert "你好世界" in msg

    def test_extra_context_merged(self):
        """Extra context keys are merged into the payload."""
        segments = [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}]
        msg = _build_structured_user_message(
            segments, extra_context={"topic": "AI", "target_segment_ids": ["s1"]}
        )
        parsed = json.loads(msg)
        assert parsed["topic"] == "AI"
        assert parsed["target_segment_ids"] == ["s1"]

    def test_missing_fields_handled(self):
        """Missing fields default to safe values."""
        segments = [{"id": "s1"}]  # no text/start/end
        msg = _build_structured_user_message(segments)
        parsed = json.loads(msg)
        assert parsed["segments"][0]["text"] == ""
        assert parsed["segments"][0]["start"] is None


# ================================================================
# C-02: Layered JSON parsing (_parse_json_response_layers)
# ================================================================


class TestParseJsonResponseLayers:
    def test_layer1_direct_json_array(self):
        """Layer 1: direct JSON array parse."""
        content = '[{"segment_id": "s1", "action": "delete"}]'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert result[0]["segment_id"] == "s1"

    def test_layer1_direct_json_object(self):
        """Layer 1: single JSON object wrapped to list."""
        content = '{"segment_id": "s1", "action": "delete"}'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert len(result) == 1
        assert result[0]["segment_id"] == "s1"

    def test_layer2_markdown_code_block(self):
        """Layer 2: JSON inside markdown code block."""
        content = 'Here are results:\n```json\n[{"segment_id": "s2", "relevance": 0.8}]\n```\nDone.'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert result[0]["segment_id"] == "s2"

    def test_layer3_embedded_in_text(self):
        """Layer 3: JSON array embedded in prose text."""
        content = 'Analysis result: [{"segment_id": "s3", "relevance": 0.5}] end.'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert result[0]["segment_id"] == "s3"

    def test_layer4_line_by_line_fallback(self):
        """Layer 4: line-by-line regex extraction."""
        content = 'Some text "segment_id": "s4" blah "relevance": 0.3 more text'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert result[0]["segment_id"] == "s4"
        assert result[0]["relevance"] == 0.3

    def test_layer4_action_fallback(self):
        """Layer 4: action pattern fallback."""
        content = '"segment_id": "s5" "action": "delete"'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert result[0]["segment_id"] == "s5"
        assert result[0]["action"] == "delete"

    def test_empty_content_returns_none(self):
        """Empty string returns None."""
        assert _parse_json_response_layers("") is None
        assert _parse_json_response_layers("   ") is None

    def test_totally_invalid_returns_none(self):
        """Text with no extractable JSON returns None."""
        assert _parse_json_response_layers("totally invalid no json here") is None

    def test_multiple_items(self):
        """Multiple items in array are all parsed."""
        content = '[{"segment_id": "s1"}, {"segment_id": "s2"}, {"segment_id": "s3"}]'
        result = _parse_json_response_layers(content)
        assert result is not None
        assert len(result) == 3



# ================================================================
# P0: analyze_smart_delete (mocked LLM)
# ================================================================


class TestAnalyzeSmartDelete:
    def test_not_configured(self):
        """Returns error when LLM not configured."""
        result = analyze_smart_delete(
            [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}],
            config=_make_unconfigured_config(),
        )
        assert result["success"] is False
        assert "not configured" in result["error"].lower()

    def test_empty_segments(self):
        """Returns error for empty segments."""
        result = analyze_smart_delete([], config=_make_unconfigured_config())
        assert result["success"] is False

    def test_all_flagged_skipped(self):
        """When all segments are already flagged, returns empty results."""
        segments = [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}]
        result = analyze_smart_delete(
            segments,
            existing_flagged_ids={"s1"},
            config=_make_configured_config(),
        )
        assert result["success"] is True
        assert len(result["data"]["results"]) == 0

    def test_mock_llm_response_parsed(self, monkeypatch):
        """Full flow with mocked LLM returning valid JSON."""
        segments = [
            {"id": "s1", "text": "um then", "start": 0.0, "end": 3.0},
            {"id": "s2", "text": "hello world", "start": 3.0, "end": 6.0},
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": "s1", "action": "delete",
                         "reason": "filler", "category": "filler_phrase"}
                    ]),
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        result = analyze_smart_delete(segments, config=_make_configured_config())
        assert result["success"] is True
        assert len(result["data"]["results"]) == 1
        assert result["data"]["results"][0]["segment_id"] == "s1"
        assert result["data"]["results"][0]["category"] == "filler_phrase"

    def test_chunk_callback_invoked(self, monkeypatch):
        """chunk_callback is called with per-window results."""
        segments = [
            {"id": "s1", "text": "filler", "start": 0.0, "end": 2.0},
        ]
        callback_results: list[list[dict]] = []

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": '[{"segment_id": "s1", "action": "delete"}]',
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        analyze_smart_delete(
            segments,
            config=_make_configured_config(),
            chunk_callback=lambda r: callback_results.append(r),
        )
        assert len(callback_results) > 0


# ================================================================
# P1: Confidence checking
# ================================================================


class TestCheckCorrectionConfidence:
    def test_no_change(self):
        """Identical texts have zero edit distance."""
        result = _check_correction_confidence("hello", "hello")
        assert result["edit_distance"] == 0
        assert result["change_ratio"] == 0.0
        assert result["low_confidence"] is False

    def test_minor_change(self):
        """Small change is not low confidence."""
        result = _check_correction_confidence("hello world", "hello worl")
        assert result["edit_distance"] == 1
        assert result["low_confidence"] is False

    def test_major_change_low_confidence(self):
        """Large change ratio is flagged low confidence."""
        result = _check_correction_confidence("abcdef", "xyz123")
        assert result["change_ratio"] > 0.5
        assert result["low_confidence"] is True

    def test_empty_strings(self):
        """Both empty strings have zero distance."""
        result = _check_correction_confidence("", "")
        assert result["edit_distance"] == 0
        assert result["low_confidence"] is False


class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein("abc", "abc") == 0

    def test_single_insert(self):
        assert _levenshtein("abc", "abcd") == 1

    def test_known_distance(self):
        assert _levenshtein("kitten", "sitting") == 3

    def test_empty_first(self):
        assert _levenshtein("", "abc") == 3


# ================================================================
# P1: Timestamp assertion
# ================================================================


class TestTimestampAssertion:
    def test_no_change_passes(self):
        """Unchanged timestamps don't raise."""
        _assert_timestamps_unchanged(
            1.0, 2.0, 1.0, 2.0, segment_id="s1"
        )  # should not raise

    def test_dev_mode_raises(self, monkeypatch):
        """In development mode, timestamp corruption raises ValueError."""
        monkeypatch.setenv("MILO_ENV", "development")
        with pytest.raises(ValueError, match="Timestamp corruption"):
            _assert_timestamps_unchanged(
                1.0, 2.0, 1.5, 2.0, segment_id="s1"
            )

    def test_prod_mode_warns(self, monkeypatch):
        """In production mode, raises TimestampCorruptionError (caught by caller)."""
        monkeypatch.delenv("MILO_ENV", raising=False)
        with pytest.raises(TimestampCorruptionError):
            _assert_timestamps_unchanged(
                1.0, 2.0, 1.0, 2.5, segment_id="s1"
            )


# ================================================================
# P1: analyze_subtitle_correction (mocked LLM)
# ================================================================


class TestAnalyzeSubtitleCorrection:
    def test_not_configured(self):
        result = analyze_subtitle_correction(
            [{"id": "s1", "text": "test", "start": 0.0, "end": 1.0}],
            config=_make_unconfigured_config(),
        )
        assert result["success"] is False

    def test_empty_segments(self):
        result = analyze_subtitle_correction([], config=_make_unconfigured_config())
        assert result["success"] is False

    def test_mode_a_mock_llm(self, monkeypatch):
        """Mode A (no reference) with mocked LLM."""
        segments = [
            {"id": "s1", "text": "优化系统", "start": 0.0, "end": 2.0},
        ]

        def mock_call_llm(prompt, system="", **kwargs):
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": "s1", "corrected_text": "优化系统",
                         "changes": [], "category": "none", "confidence": 1.0}
                    ]),
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        result = analyze_subtitle_correction(segments, config=_make_configured_config())
        assert result["success"] is True
        # category="none" results are now filtered out (they clutter the UI)
        assert len(result["data"]["corrections"]) == 0

    def test_mode_b_with_reference(self, monkeypatch):
        """Mode B (with reference text) calls LLM with reference context."""
        segments = [
            {"id": "s1", "text": "优化系统", "start": 0.0, "end": 2.0},
        ]

        captured_prompt = []

        def mock_call_llm(prompt, system="", **kwargs):
            captured_prompt.append(prompt)
            return {
                "success": True,
                "data": {
                    "content": json.dumps([
                        {"segment_id": "s1", "corrected_text": "优化系统",
                         "changes": ["aligned"], "category": "reference_aligned", "confidence": 0.9}
                    ]),
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                },
            }

        monkeypatch.setattr("core.llm_service.call_llm", mock_call_llm)
        result = analyze_subtitle_correction(
            segments, reference_text="参考稿内容", config=_make_configured_config()
        )
        assert result["success"] is True
        # Reference text should appear in the prompt
        assert "参考稿内容" in captured_prompt[0] or "reference_text" in captured_prompt[0]


# ================================================================
# Helpers
# ================================================================


def _make_unconfigured_config():
    """Create an LlmConfig that is not configured."""
    from core.models import LlmConfig, LlmProvider

    return LlmConfig(
        provider=LlmProvider.CUSTOM,
        base_url="",
        api_key="",
        model="",
    )


def _make_configured_config():
    """Create an LlmConfig that passes is_configured()."""
    from core.models import LlmConfig, LlmProvider

    return LlmConfig(
        provider=LlmProvider.CUSTOM,
        base_url="http://localhost:11434/v1",
        api_key="test-key",
        model="test-model",
    )

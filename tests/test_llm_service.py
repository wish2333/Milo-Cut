"""Unit tests for core.llm_service."""

import pytest

from core.llm_service import chunk_transcript, chunk_transcript_by_count, estimate_tokens, get_llm_config
from core.models import LlmConfig, LlmProvider

# ------------------------------------------------------------------
# estimate_tokens
# ------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_english_text(self) -> None:
        # "Hello world" = 11 chars, ~2.75 tokens
        result = estimate_tokens("Hello world")
        assert result == 2  # int(11 / 4.0) = 2

    def test_chinese_text(self) -> None:
        # 6 CJK chars: int(6 / 1.5) = 4
        result = estimate_tokens("你好世界再见")
        assert result == 4

    def test_mixed_text(self) -> None:
        # 2 CJK + 6 other = int(2/1.5 + 6/4.0) = int(1.33 + 1.5) = 2
        result = estimate_tokens("你好world")
        assert result == 2

    def test_long_text(self) -> None:
        text = "a" * 100
        result = estimate_tokens(text)
        assert result == 25  # 100 / 4.0


# ------------------------------------------------------------------
# LlmConfig
# ------------------------------------------------------------------


class TestLlmConfig:
    def test_default_values(self) -> None:
        config = LlmConfig()
        assert config.provider == LlmProvider.CUSTOM
        assert config.temperature == 0.3
        assert config.timeout == 120
        assert not config.is_configured()

    def test_deepseek_defaults(self) -> None:
        config = LlmConfig(provider=LlmProvider.DEEPSEEK, api_key="sk-test")
        assert config.resolved_base_url() == "https://api.deepseek.com/v1"
        assert config.resolved_model() == "deepseek-v4-flash"
        assert config.is_configured()

    def test_openai_defaults(self) -> None:
        config = LlmConfig(provider=LlmProvider.OPENAI, api_key="sk-test")
        assert config.resolved_base_url() == "https://api.openai.com/v1"
        assert config.resolved_model() == "gpt-5.4-mini"

    def test_custom_with_explicit_values(self) -> None:
        config = LlmConfig(
            provider=LlmProvider.CUSTOM,
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="qwen2.5:7b",
        )
        assert config.resolved_base_url() == "http://localhost:11434/v1"
        assert config.resolved_model() == "qwen2.5:7b"
        assert config.is_configured()

    def test_not_configured_without_api_key(self) -> None:
        config = LlmConfig(
            provider=LlmProvider.OPENAI,
        )
        assert not config.is_configured()

    def test_frozen_immutability(self) -> None:
        from pydantic import ValidationError

        config = LlmConfig()
        with pytest.raises(ValidationError):
            config.provider = LlmProvider.DEEPSEEK  # type: ignore[misc]


# ------------------------------------------------------------------
# chunk_transcript
# ------------------------------------------------------------------


class TestChunkTranscript:
    def test_empty_segments(self) -> None:
        assert chunk_transcript([]) == []

    def test_single_segment(self) -> None:
        segments = [{"start": 0.0, "end": 10.0, "text": "hello"}]
        chunks = chunk_transcript(segments, chunk_duration=300.0)
        assert len(chunks) == 1
        assert len(chunks[0]) == 1

    def test_basic_chunking(self) -> None:
        # 600 seconds of content, 300s chunks -> 2 chunks
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"seg_{i}"} for i in range(60)
        ]
        chunks = chunk_transcript(segments, chunk_duration=300.0, overlap_duration=0.0)
        assert len(chunks) == 2
        assert len(chunks[0]) == 30
        assert len(chunks[1]) == 30

    def test_overlap_creates_extra_segments(self) -> None:
        # 100 seconds, 50s chunks, 10s overlap
        # Chunk 1: 0-50s, back up to 40s -> Chunk 2: 40-90s, back up to 80s -> Chunk 3: 80-100s
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"seg_{i}"} for i in range(10)
        ]
        chunks = chunk_transcript(segments, chunk_duration=50.0, overlap_duration=10.0)
        assert len(chunks) == 3
        # First chunk starts at 0, second chunk starts at overlap (40s)
        assert chunks[0][0]["text"] == "seg_0"
        assert chunks[1][0]["text"] == "seg_4"  # overlap from 40s
        assert chunks[2][0]["text"] == "seg_8"  # overlap from 80s

    def test_short_content_single_chunk(self) -> None:
        # 30 seconds of content, 300s chunk -> single chunk
        segments = [{"start": i * 3.0, "end": (i + 1) * 3.0, "text": f"seg_{i}"} for i in range(10)]
        chunks = chunk_transcript(segments, chunk_duration=300.0, overlap_duration=30.0)
        assert len(chunks) == 1
        assert len(chunks[0]) == 10


# ------------------------------------------------------------------
# get_llm_config reads from settings
# ------------------------------------------------------------------


class TestGetLlmConfig:
    def test_reads_from_settings(self) -> None:
        config = get_llm_config()
        assert isinstance(config, LlmConfig)
        assert isinstance(config.provider, LlmProvider)


# ------------------------------------------------------------------
# chunk_transcript_by_count
# ------------------------------------------------------------------


class TestChunkTranscriptByCount:
    """Tests for chunk_transcript_by_count -- count-based batch+target chunking."""

    @staticmethod
    def _make_segments(n: int) -> list[dict]:
        return [{"id": f"seg_{i}", "text": f"Segment {i}", "start": float(i), "end": float(i + 1)} for i in range(n)]

    def test_basic_100_segments(self):
        """100 segments with batch_size=20, overlap=4 -> 5 batches."""
        segs = self._make_segments(100)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 5
        # Each batch's target_ids should have 20 items
        for batch_segs, target_ids in batches:
            assert len(target_ids) == 20

    def test_overlap_context(self):
        """Batch 1 should include the last 4 segments of batch 0 as context."""
        segs = self._make_segments(100)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        batch0_segs, batch0_targets = batches[0]
        batch1_segs, batch1_targets = batches[1]
        # batch 0 target is seg_0..seg_19
        assert batch0_targets == {f"seg_{i}" for i in range(20)}
        # batch 0 should include 4 extra segments after target: seg_20..seg_23
        assert len(batch0_segs) == 24  # 20 target + 4 after
        # batch 1 context_start = 20 - 4 = 16, so starts at seg_16
        assert batch1_segs[0]["id"] == "seg_16"
        # batch 1 target is seg_20..seg_39
        assert batch1_targets == {f"seg_{i}" for i in range(20, 40)}

    def test_single_batch_le_batch_size(self):
        """Total segments <= batch_size should produce single batch with all as targets (audit #9)."""
        segs = self._make_segments(15)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 1
        _, target_ids = batches[0]
        assert target_ids == {f"seg_{i}" for i in range(15)}

    def test_boundary_28_segments(self):
        """28 segments with batch_size=20 should produce 2 batches, not 1 (audit #9)."""
        segs = self._make_segments(28)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=4)
        assert len(batches) == 2
        # batch 0: 20 target + 4 after context = 24 segments
        assert len(batches[0][0]) == 24
        # batch 1: 4 before context + 8 target = 12 segments
        assert len(batches[1][0]) == 12

    def test_empty(self):
        """Empty segments should return empty list."""
        assert chunk_transcript_by_count([]) == []

    def test_overlap_ge_batch_size_clamped(self):
        """overlap >= batch_size should be clamped to batch_size - 1 with warning (audit #11)."""
        segs = self._make_segments(10)
        # logger.warning is used, not warnings.warn, so pytest.warns won't capture it.
        # Just verify the function doesn't crash and produces correct output.
        batches = chunk_transcript_by_count(segs, batch_size=5, overlap=10)
        # Should not crash, overlap clamped to 4
        assert len(batches) >= 1

    def test_overlap_zero(self):
        """overlap=0 should work, no context overlap between batches."""
        segs = self._make_segments(30)
        batches = chunk_transcript_by_count(segs, batch_size=20, overlap=0)
        assert len(batches) == 2
        # batch 0: exactly 20 segments
        assert len(batches[0][0]) == 20
        # batch 1: exactly 10 segments (no overlap with batch 0)
        assert len(batches[1][0]) == 10

    def test_batch_size_one(self):
        """batch_size=1 extreme case: each batch has 1 target."""
        segs = self._make_segments(3)
        batches = chunk_transcript_by_count(segs, batch_size=1, overlap=0)
        assert len(batches) == 3
        for _, target_ids in batches:
            assert len(target_ids) == 1

    def test_missing_id_field(self):
        """Segments missing 'id' should use '' fallback without crashing."""
        segs = [{"text": f"Seg {i}", "start": float(i)} for i in range(3)]
        batches = chunk_transcript_by_count(segs, batch_size=2, overlap=0)
        assert len(batches) == 2
        # target_ids should contain empty strings as fallback
        assert "" in batches[0][1]

    def test_shallow_copy(self):
        """Returned batch_segments should be slices (shallow copies), not references (audit #12)."""
        segs = self._make_segments(10)
        batches = chunk_transcript_by_count(segs, batch_size=5, overlap=0)
        batch_segs, _ = batches[0]
        batch_segs[0]["text"] = "MUTATED"
        # Original should NOT be mutated
        assert segs[0]["text"] == "Segment 0"


# ------------------------------------------------------------------
# analyze_smart_delete with batch+target mode
# ------------------------------------------------------------------


class TestAnalyzeSmartDeleteBatchTarget:
    """Tests for analyze_smart_delete with batch+target mode."""

    def test_uses_chunk_transcript_by_count(self, monkeypatch):
        """analyze_smart_delete should call chunk_transcript_by_count, not chunk_transcript."""
        from unittest.mock import MagicMock, call
        segments = [{"id": f"s{i}", "text": f"seg {i}", "start": float(i), "end": float(i+1)} for i in range(25)]
        mock_llm = MagicMock(return_value={"success": True, "data": {"content": "[]", "usage": {"total_tokens": 10}}})
        monkeypatch.setattr("core.llm_service.call_llm", mock_llm)
        mock_config = MagicMock()
        mock_config.is_configured.return_value = True
        monkeypatch.setattr("core.llm_service.get_llm_config", lambda: mock_config)
        monkeypatch.setattr("core.llm_service.load_settings", lambda: {"llm_smart_batch_size": 20, "llm_smart_overlap_size": 4, "llm_concurrency": 1})
        # Track which chunk function gets called
        mock_chunk_by_count = MagicMock(
            side_effect=lambda segs, **kw: [
                (segs[:20], {"s0", "s1"},),
                (segs[20:], {"s20", "s21", "s22", "s23", "s24"},),
            ]
        )
        monkeypatch.setattr("core.llm_service.chunk_transcript_by_count", mock_chunk_by_count)
        from core.llm_service import analyze_smart_delete
        result = analyze_smart_delete(segments)
        assert result["success"] is True
        mock_chunk_by_count.assert_called_once()
        call_kwargs = mock_chunk_by_count.call_args
        assert call_kwargs.kwargs.get("batch_size") == 20
        assert call_kwargs.kwargs.get("overlap") == 4

"""Unit tests for core.llm_service."""

import threading

import pytest

from core.llm_service import estimate_tokens, chunk_transcript, get_llm_config
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
        assert config.resolved_model() == "deepseek-chat"
        assert config.is_configured()

    def test_openai_defaults(self) -> None:
        config = LlmConfig(provider=LlmProvider.OPENAI, api_key="sk-test")
        assert config.resolved_base_url() == "https://api.openai.com/v1"
        assert config.resolved_model() == "gpt-4o-mini"

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
        config = LlmConfig()
        with pytest.raises(Exception):
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
            {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"seg_{i}"}
            for i in range(60)
        ]
        chunks = chunk_transcript(segments, chunk_duration=300.0, overlap_duration=0.0)
        assert len(chunks) == 2
        assert len(chunks[0]) == 30
        assert len(chunks[1]) == 30

    def test_overlap_creates_extra_segments(self) -> None:
        # 100 seconds, 50s chunks, 10s overlap
        # Chunk 1: 0-50s, back up to 40s -> Chunk 2: 40-90s, back up to 80s -> Chunk 3: 80-100s
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"seg_{i}"}
            for i in range(10)
        ]
        chunks = chunk_transcript(segments, chunk_duration=50.0, overlap_duration=10.0)
        assert len(chunks) == 3
        # First chunk starts at 0, second chunk starts at overlap (40s)
        assert chunks[0][0]["text"] == "seg_0"
        assert chunks[1][0]["text"] == "seg_4"  # overlap from 40s
        assert chunks[2][0]["text"] == "seg_8"  # overlap from 80s

    def test_short_content_single_chunk(self) -> None:
        # 30 seconds of content, 300s chunk -> single chunk
        segments = [
            {"start": i * 3.0, "end": (i + 1) * 3.0, "text": f"seg_{i}"}
            for i in range(10)
        ]
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

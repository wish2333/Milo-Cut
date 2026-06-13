"""LLM service for Milo-Cut.

Uses the OpenAI Python SDK to communicate with any OpenAI-compatible API
(DeepSeek, Qwen, Ollama, etc.). No max_tokens is set so the model can
produce complete analysis output without truncation.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

from core.config import load_settings
from core.logging import get_logger
from core.models import LlmConfig, LlmProvider

logger = get_logger()

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


# ------------------------------------------------------------------
# Token estimation
# ------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string.

    Uses simple heuristic based on character type:
    - Chinese chars: ~1.5 tokens per char
    - English/other: ~0.25 tokens per char (4 chars per token)
    """
    if not text:
        return 0

    cjk_count = 0
    for ch in text:
        if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿":
            cjk_count += 1

    other_count = len(text) - cjk_count
    return int(cjk_count / 1.5 + other_count / 4.0)


# ------------------------------------------------------------------
# Config helpers
# ------------------------------------------------------------------


def get_llm_config() -> LlmConfig:
    """Read LLM config from settings file."""
    settings = load_settings()
    return LlmConfig(
        provider=LlmProvider(settings.get("llm_provider", "custom")),
        base_url=settings.get("llm_base_url", ""),
        api_key=settings.get("llm_api_key", ""),
        model=settings.get("llm_model", ""),
        temperature=settings.get("llm_temperature", 0.3),
        timeout=settings.get("llm_timeout", 120),
    )


def _build_client(config: LlmConfig) -> OpenAI:
    """Create an OpenAI client from LlmConfig."""
    return OpenAI(
        api_key=config.api_key,
        base_url=config.resolved_base_url(),
        timeout=config.timeout,
        max_retries=0,  # we handle retries ourselves
    )


# ------------------------------------------------------------------
# Core LLM call
# ------------------------------------------------------------------


def call_llm(
    prompt: str,
    system: str = "",
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Call the LLM with a prompt and return the parsed response.

    Args:
        prompt: User message content.
        system: System message content.
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.
        progress_cb: Optional progress callback (percent, message).

    Returns:
        {"success": True, "data": {"content": str, "usage": dict}}
        {"success": False, "error": str}
    """
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    client = _build_client(config)
    model = config.resolved_model()

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    last_error: str = ""
    for attempt in range(_MAX_RETRIES):
        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}

        if progress_cb:
            progress_cb(
                0.1 + attempt * 0.05,
                f"Calling LLM (attempt {attempt + 1}/{_MAX_RETRIES})...",
            )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config.temperature,
                # No max_tokens -- let model produce full output
            )

            content = response.choices[0].message.content or ""
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            logger.info(
                f"LLM call completed: model={model}, "
                f"tokens={usage.get('total_tokens', 'unknown')}, "
                f"attempts={attempt + 1}"
            )

            return {
                "success": True,
                "data": {"content": content, "usage": usage},
            }

        except APITimeoutError:
            last_error = f"LLM request timed out (attempt {attempt + 1})"
            logger.warning(last_error)
        except RateLimitError:
            last_error = f"Rate limited (attempt {attempt + 1})"
            logger.warning(last_error)
        except APIError as e:
            last_error = f"API error: {e}"
            logger.error(last_error)
            # Non-retryable API errors -- abort immediately
            break
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            logger.error(last_error)
            break

        # Exponential backoff before retry
        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            if cancel_event:
                cancel_event.wait(timeout=delay)
            else:
                import time

                time.sleep(delay)

    return {"success": False, "error": last_error}


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------


def test_connection(config: LlmConfig | None = None) -> dict[str, Any]:
    """Test LLM connectivity by sending a minimal request.

    Returns:
        {"success": True, "data": {"model": str, "response_time_ms": int}}
        {"success": False, "error": str}
    """
    import time

    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    client = _build_client(config)
    model = config.resolved_model()

    try:
        start = time.monotonic()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if response.choices:
            return {
                "success": True,
                "data": {
                    "model": model,
                    "response_time_ms": elapsed_ms,
                },
            }
        return {"success": False, "error": "Empty response from LLM"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------------
# Transcript chunking
# ------------------------------------------------------------------


def chunk_transcript(
    segments: list[dict],
    chunk_duration: float = 300.0,
    overlap_duration: float = 30.0,
) -> list[list[dict]]:
    """Split transcript segments into time-based chunks with overlap.

    Each chunk covers `chunk_duration` seconds of content with
    `overlap_duration` seconds of overlap with adjacent chunks.
    This ensures topic drift detection works across chunk boundaries.

    Args:
        segments: List of segment dicts with 'start', 'end', 'text'.
        chunk_duration: Target chunk length in seconds (default 5 min).
        overlap_duration: Overlap between chunks in seconds (default 30s).

    Returns:
        List of chunk groups, each a list of segments.
    """
    if not segments:
        return []

    chunks: list[list[dict]] = []
    i = 0

    while i < len(segments):
        chunk_start = segments[i]["start"]
        chunk_end_time = chunk_start + chunk_duration
        chunk: list[dict] = []

        while i < len(segments) and segments[i]["start"] < chunk_end_time:
            chunk.append(segments[i])
            i += 1

        if chunk:
            chunks.append(chunk)

            # Back up to create overlap with next chunk
            if i < len(segments):
                overlap_start = chunk_end_time - overlap_duration
                while i > 0 and segments[i - 1]["start"] >= overlap_start:
                    i -= 1

    return chunks


# ------------------------------------------------------------------
# Topic drift analysis
# ------------------------------------------------------------------

_TOPIC_DRIFT_SYSTEM = (
    "你是一位视频内容分析专家。你需要分析视频转录片段与给定主题的相关性，"
    "并为每个片段打分（0.0 到 1.0，1.0 表示完全相关）。"
    "请严格按照 JSON 数组格式输出，不要添加额外说明。"
)

_TOPIC_DRIFT_USER_TEMPLATE = """请分析以下视频转录片段与主题的相关性。

{topic_line}

转录片段：
{segments_text}

输出格式（JSON 数组，每个元素对应一个片段）：
```json
[
  {{"segment_id": "片段ID", "topic": "实际讨论的话题", "relevance": 0.0到1.0, "reason": "简短理由"}}
]
```

要求：
1. 为每个片段输出一条结果
2. relevance: 0.0-1.0，1.0 表示与主题完全相关，0.0 表示完全不相关
3. topic: 简述该片段实际讨论的内容
4. reason: 一句话说明评分理由
"""


def _build_topic_drift_prompt(
    segments: list[dict], topic_description: str
) -> str:
    """Build the user prompt for topic drift analysis."""
    topic_line = (
        f"分析主题：{topic_description}"
        if topic_description.strip()
        else "分析主题：未指定（请根据视频整体内容判断片段是否偏离主流话题）"
    )

    lines: list[str] = []
    for seg in segments:
        seg_id = seg.get("id", seg.get("segment_id", "?"))
        text = seg.get("text", "").strip()
        lines.append(f"[{seg_id}] {text}")

    segments_text = "\n".join(lines)
    return _TOPIC_DRIFT_USER_TEMPLATE.format(
        topic_line=topic_line, segments_text=segments_text
    )


def _parse_topic_drift_response(content: str) -> list[dict]:
    """Parse LLM response into list of topic drift result dicts.

    Handles markdown code blocks, bare JSON, and is tolerant of
    missing fields or out-of-range values.
    """
    import re

    # Extract JSON from markdown code block or bare text
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    raw_json = json_match.group(1).strip() if json_match else content.strip()

    # Find the JSON array
    start = raw_json.find("[")
    end = raw_json.rfind("]")
    if start == -1 or end == -1:
        return []

    try:
        items = json.loads(raw_json[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return []

    results: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        seg_id = str(item.get("segment_id", item.get("id", "")))
        if not seg_id:
            continue

        # Clamp relevance to [0, 1]
        try:
            relevance = float(item.get("relevance", 1.0))
        except (TypeError, ValueError):
            relevance = 1.0
        relevance = max(0.0, min(1.0, relevance))

        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 1.0
        confidence = max(0.0, min(1.0, confidence))

        results.append(
            {
                "segment_id": seg_id,
                "topic": str(item.get("topic", "")),
                "relevance": relevance,
                "confidence": confidence,
                "reason": str(item.get("reason", "")),
            }
        )

    return results


def analyze_topic_drift(
    segments: list[dict],
    topic_description: str = "",
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:
    """Run topic drift analysis on transcript segments.

    Chunks the transcript, calls LLM per chunk, and streams per-chunk
    results via ``chunk_callback``.

    Args:
        segments: List of segment dicts with 'id', 'start', 'end', 'text'.
        topic_description: Optional topic description for relevance scoring.
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.
        progress_cb: Optional progress callback (percent, message).
        chunk_callback: Optional callback receiving per-chunk results.

    Returns:
        {"success": True, "data": {"results": [...], "token_usage": {...}}}
        {"success": False, "error": str}
    """
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    if not segments:
        return {"success": False, "error": "No segments to analyze"}

    chunks = chunk_transcript(segments)
    total_chunks = len(chunks)
    all_results: list[dict] = []
    total_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    for idx, chunk in enumerate(chunks):
        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}

        if progress_cb:
            pct = (idx / total_chunks) * 100 if total_chunks > 0 else 0
            progress_cb(
                pct,
                f"Analyzing chunk {idx + 1}/{total_chunks}...",
            )

        prompt = _build_topic_drift_prompt(chunk, topic_description)
        result = call_llm(
            prompt,
            system=_TOPIC_DRIFT_SYSTEM,
            config=config,
            cancel_event=cancel_event,
        )

        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Topic drift chunk {idx + 1} failed: {error}")
            # Continue to next chunk rather than abort entirely
            continue

        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        for key in total_usage:
            total_usage[key] += usage.get(key, 0)

        chunk_results = _parse_topic_drift_response(content)
        if chunk_results and chunk_callback:
            chunk_callback(chunk_results)

        all_results.extend(chunk_results)

    # Deduplicate by segment_id, keeping the last occurrence (handles overlap)
    seen: dict[str, dict] = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(deduped)} segments analyzed")

    logger.info(
        f"Topic drift analysis done: {len(deduped)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}"
    )

    return {
        "success": True,
        "data": {"results": deduped, "token_usage": total_usage},
    }

"""LLM service for Milo-Cut.

Uses the OpenAI Python SDK to communicate with any OpenAI-compatible API
(DeepSeek, Qwen, Ollama, etc.). No max_tokens is set so the model can
produce complete analysis output without truncation.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

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
    json_mode: bool = False,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Call the LLM with a prompt and return the parsed response.

    Args:
        prompt: User message content.
        system: System message content.
        json_mode: If True, request JSON output format from providers that
            support it (OpenAI, DeepSeek). Other providers rely on prompt
            constraints + layered parsing on the caller side.
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

    # Build kwargs -- only enable response_format for providers that support it
    request_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": config.temperature,
        # No max_tokens -- let model produce full output
    }
    if json_mode and config.provider in (LlmProvider.OPENAI, LlmProvider.DEEPSEEK):
        request_kwargs["response_format"] = {"type": "json_object"}

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
            response = client.chat.completions.create(**request_kwargs)

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
            delay = _RETRY_BASE_DELAY * (2**attempt)
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


def chunk_transcript_short(
    segments: list[dict],
    window_duration: float = 25.0,
    overlap_duration: float = 5.0,
) -> list[list[dict]]:
    """Split transcript into short overlapping windows for local-phenomenon analysis.

    Used by P0 smart-delete where the phenomena (semantic dup, self-correction,
    filler phrases) are local -- 15-30s windows catch them better than 5min chunks.

    Args:
        segments: List of segment dicts with 'start', 'end', 'text'.
        window_duration: Target window length in seconds (default 25s).
        overlap_duration: Overlap between windows in seconds (default 5s).

    Returns:
        List of window groups, each a list of segments.
    """
    return chunk_transcript(
        segments,
        chunk_duration=window_duration,
        overlap_duration=overlap_duration,
    )


# ------------------------------------------------------------------
# Structured message building + layered JSON parsing (C-02)
# ------------------------------------------------------------------


def _build_structured_user_message(
    segments: list[dict],
    extra_context: dict[str, Any] | None = None,
) -> str:
    """Build structured JSON user message for LLM analysis.

    Replaces ad-hoc ``[id] text`` formatting with JSON, eliminating
    segment_id parsing ambiguity and special-character breakage.

    Args:
        segments: List of segment dicts with 'id', 'text', 'start', 'end'.
        extra_context: Additional top-level keys to merge into the payload
            (e.g. ``{"topic": "...", "reference_text": "..."}``).

    Returns:
        JSON string suitable for the LLM user message.
    """
    payload: dict[str, Any] = {
        "segments": [
            {
                "id": str(s.get("id", s.get("segment_id", "?"))),
                "text": str(s.get("text", "")).strip(),
                "start": s.get("start"),
                "end": s.get("end"),
            }
            for s in segments
        ],
    }
    if extra_context:
        payload.update(extra_context)
    return json.dumps(payload, ensure_ascii=False)


def _parse_json_response_layers(content: str) -> list[dict] | None:
    """4-layer degraded JSON parsing for cross-provider robustness.

    Layer 1: Direct ``json.loads`` (fastest, model follows format).
    Layer 2: Extract markdown code block then ``json.loads``.
    Layer 3: Regex extract ``[...]`` or ``{...}`` substring then ``json.loads``.
    Layer 4: Line-by-line regex extract key fields (extreme fallback).

    Returns:
        List of parsed dicts, or ``None`` if all layers fail.
    """
    if not content or not content.strip():
        return None

    # Layer 1: Direct parse
    try:
        result = json.loads(content.strip())
        return result if isinstance(result, list) else [result]
    except (json.JSONDecodeError, ValueError):
        pass

    # Layer 2: Markdown code block
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            return result if isinstance(result, list) else [result]
        except (json.JSONDecodeError, ValueError):
            pass

    # Layer 3: Regex extract array or object
    arr_start = content.find("[")
    arr_end = content.rfind("]")
    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        try:
            return json.loads(content[arr_start : arr_end + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    obj_start = content.find("{")
    obj_end = content.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        try:
            result = json.loads(content[obj_start : obj_end + 1])
            return result if isinstance(result, list) else [result]
        except (json.JSONDecodeError, ValueError):
            pass

    # Layer 4: Line-by-line fallback -- extract common fields
    items: list[dict] = []
    # Try segment_id + relevance (topic drift / semantic search pattern)
    pattern_relevance = re.compile(
        r'"segment_id"\s*:\s*"([^"]+)".*?"relevance"\s*:\s*([\d.]+)'
    )
    for match in pattern_relevance.finditer(content):
        items.append(
            {"segment_id": match.group(1), "relevance": float(match.group(2))}
        )
    if items:
        return items

    # Try segment_id + action (smart delete pattern)
    pattern_action = re.compile(
        r'"segment_id"\s*:\s*"([^"]+)".*?"action"\s*:\s*"(\w+)"'
    )
    for match in pattern_action.finditer(content):
        items.append(
            {"segment_id": match.group(1), "action": match.group(2)}
        )
    if items:
        return items

    return None


# ------------------------------------------------------------------
# P0: Smart delete analysis
# ------------------------------------------------------------------

_SMART_DELETE_SYSTEM = """你是视频剪辑助手。用户以 JSON 格式提供一组转录片段。
请识别其中可安全删除的片段:
1. semantic_dup: 语义重复 -- 同一观点换措辞重述 (规则引擎只能识别字面重复)
2. self_correct: 无触发词口误 -- 说错后自然纠正的完整区域
3. filler_phrase: 上下文口头禅 -- 无实义过渡句如"然后接下来就是我们要讲的那个"

输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase"}]
只输出建议删除的片段，无需删除的不要输出。
"""


def analyze_smart_delete(
    segments: list[dict],
    existing_flagged_ids: set[str] | None = None,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:
    """Short-window LLM analysis to catch what the rule engine misses.

    Identifies semantic duplicates, self-corrections, and context filler
    phrases that rule-based detection cannot catch.

    Args:
        segments: List of segment dicts with 'id', 'start', 'end', 'text'.
        existing_flagged_ids: segment IDs already flagged by rule engine --
            these are skipped to avoid redundant analysis.
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

    # Filter out segments already flagged by rule engine (incremental analysis)
    flagged = existing_flagged_ids or set()
    to_analyze = [s for s in segments if str(s.get("id", "")) not in flagged]
    if not to_analyze:
        return {
            "success": True,
            "data": {"results": [], "token_usage": {}, "skipped": len(segments)},
        }

    chunks = chunk_transcript_short(to_analyze)
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
            progress_cb(pct, f"Smart-delete analyzing window {idx + 1}/{total_chunks}...")

        prompt = _build_structured_user_message(chunk)
        result = call_llm(
            prompt,
            system=_SMART_DELETE_SYSTEM,
            json_mode=True,
            config=config,
            cancel_event=cancel_event,
        )

        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Smart-delete window {idx + 1} failed: {error}")
            continue

        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        for key in total_usage:
            total_usage[key] += usage.get(key, 0)

        chunk_results = _parse_json_response_layers(content)
        if not chunk_results:
            logger.warning(f"Smart-delete window {idx + 1}: JSON parse returned None")
            continue

        # Normalize: ensure each result has required fields
        normalized = []
        for item in chunk_results:
            if not isinstance(item, dict):
                continue
            seg_id = str(item.get("segment_id", ""))
            if not seg_id:
                continue
            normalized.append(
                {
                    "segment_id": seg_id,
                    "action": str(item.get("action", "delete")),
                    "reason": str(item.get("reason", "")),
                    "category": str(item.get("category", "filler_phrase")),
                    "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.8)))),
                }
            )

        if normalized and chunk_callback:
            chunk_callback(normalized)
        all_results.extend(normalized)

    # Deduplicate by segment_id, keeping the last occurrence
    seen: dict[str, dict] = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(deduped)} smart-delete suggestions")

    logger.info(
        f"Smart-delete analysis done: {len(deduped)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}"
    )

    return {
        "success": True,
        "data": {"results": deduped, "token_usage": total_usage},
    }


# ------------------------------------------------------------------
# P1: Subtitle correction
# ------------------------------------------------------------------

_SUBTITLE_CORRECTION_SYSTEM_A = """你是视频字幕纠错专家。用户以 JSON 格式提供转录片段列表。
请修正每个片段中的 ASR 识别错误:
- 同音错字 (如"由于"误识为"优化")
- 专有名词错误 (如人名、地名、术语)
- 断句/标点问题

注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容。

输出格式: JSON 数组，每个元素对应输入中的一个片段:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明1", "变更说明2"], "category": "homophone|proper_noun|punctuation|none"}]
如果某片段无需修正，corrected_text 设为与原文相同，category 设为 "none"。
"""

_SUBTITLE_CORRECTION_SYSTEM_B = """你是视频字幕对齐专家。用户以 JSON 格式提供 ASR 转录片段和参考稿全文。
请将每个 ASR 片段与参考稿内容对齐，用参考稿内容修正 ASR 文本错误。

注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容使其与参考稿一致。

输出格式: JSON 数组:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明"], "category": "reference_aligned|none", "confidence": 0.0到1.0}]
如果某片段无需修正，corrected_text 设为与原文相同，category 设为 "none"。
"""


def analyze_subtitle_correction(
    segments: list[dict],
    reference_text: str | None = None,
    context_window: int = 3,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """LLM-powered ASR subtitle correction.

    Mode A (reference_text=None): LLM self-correction -- fixes homophones,
        proper nouns, punctuation based on language model knowledge.
    Mode B (reference_text provided): Reference-aligned -- uses a reference
        transcript to correct ASR errors via alignment.

    Args:
        segments: List of segment dicts with 'id', 'start', 'end', 'text'.
        reference_text: None for mode A, non-empty for mode B.
        context_window: Number of adjacent segments to include as context
            (helps LLM disambiguate homophones).
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.
        progress_cb: Optional progress callback (percent, message).

    Returns:
        {"success": True, "data": {"corrections": [...], "token_usage": {...}}}
        {"success": False, "error": str}
    """
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    if not segments:
        return {"success": False, "error": "No segments to analyze"}

    is_mode_b = bool(reference_text and reference_text.strip())
    system = _SUBTITLE_CORRECTION_SYSTEM_B if is_mode_b else _SUBTITLE_CORRECTION_SYSTEM_A

    # Build context-rich segment windows
    # Each LLM call gets a batch of segments + their neighbors for context
    batch_size = 20  # segments per LLM call
    all_corrections: list[dict] = []
    total_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    total_batches = (len(segments) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}

        if progress_cb:
            pct = (batch_idx / total_batches) * 100 if total_batches > 0 else 0
            progress_cb(pct, f"Subtitle correction batch {batch_idx + 1}/{total_batches}...")

        # Select batch + context window
        start_i = batch_idx * batch_size
        end_i = min(start_i + batch_size, len(segments))
        ctx_start = max(0, start_i - context_window)
        ctx_end = min(len(segments), end_i + context_window)

        batch_with_context = segments[ctx_start:ctx_end]
        # Mark which ones are the "target" segments (the batch itself)
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}

        extra_ctx: dict[str, Any] = {"target_segment_ids": sorted(target_ids)}
        if is_mode_b:
            extra_ctx["reference_text"] = reference_text

        prompt = _build_structured_user_message(batch_with_context, extra_context=extra_ctx)
        result = call_llm(
            prompt,
            system=system,
            json_mode=True,
            config=config,
            cancel_event=cancel_event,
        )

        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Subtitle correction batch {batch_idx + 1} failed: {error}")
            continue

        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        for key in total_usage:
            total_usage[key] += usage.get(key, 0)

        parsed = _parse_json_response_layers(content)
        if not parsed:
            logger.warning(f"Subtitle correction batch {batch_idx + 1}: parse returned None")
            continue

        # Normalize: only keep results for target segment IDs
        for item in parsed:
            if not isinstance(item, dict):
                continue
            seg_id = str(item.get("segment_id", ""))
            if not seg_id or seg_id not in target_ids:
                continue
            all_corrections.append(
                {
                    "segment_id": seg_id,
                    "corrected_text": str(item.get("corrected_text", "")),
                    "changes": item.get("changes", []),
                    "category": str(item.get("category", "none")),
                    "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.9)))),
                }
            )

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(all_corrections)} corrections")

    logger.info(
        f"Subtitle correction done: {len(all_corrections)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}, mode={'B' if is_mode_b else 'A'}"
    )

    return {
        "success": True,
        "data": {"corrections": all_corrections, "token_usage": total_usage},
    }


def _check_correction_confidence(original_text: str, corrected_text: str) -> dict[str, Any]:
    """Flag low-confidence corrections via edit distance ratio.

    Uses a simple character-level change ratio as a proxy for confidence.
    High change ratio (>50%) suggests the correction might be unreliable.

    Args:
        original_text: Original ASR text.
        corrected_text: LLM-corrected text.

    Returns:
        {"edit_distance": int, "change_ratio": float, "low_confidence": bool}
    """
    if not original_text and not corrected_text:
        return {"edit_distance": 0, "change_ratio": 0.0, "low_confidence": False}

    # Simple Levenshtein distance (no external dependency)
    dist = _levenshtein(original_text, corrected_text)
    max_len = max(len(original_text), len(corrected_text), 1)
    ratio = dist / max_len
    return {
        "edit_distance": dist,
        "change_ratio": ratio,
        "low_confidence": ratio > 0.5,
    }


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


# ------------------------------------------------------------------
# Timestamp safety assertion (P1)
# ------------------------------------------------------------------


class TimestampCorruptionError(Exception):
    """Raised when subtitle correction alters start/end timestamps.

    In development mode this is raised; in production it's caught by the
    caller to trigger a rollback of the specific segment.
    """


def _assert_timestamps_unchanged(
    original_start: float,
    original_end: float,
    corrected_start: float,
    corrected_end: float,
    *,
    segment_id: str,
) -> None:
    """Double-layer assertion: dev raises, prod warns + signal rollback.

    Ensures subtitle correction NEVER alters start/end physical values.
    """
    if original_start != corrected_start or original_end != corrected_end:
        msg = (
            f"Timestamp corruption detected on segment {segment_id}: "
            f"start {original_start}->{corrected_start}, "
            f"end {original_end}->{corrected_end}"
        )
        import os

        if os.environ.get("MILO_ENV") == "development":
            raise ValueError(msg)
        else:
            logger.warning(msg)
            raise TimestampCorruptionError(segment_id, msg)


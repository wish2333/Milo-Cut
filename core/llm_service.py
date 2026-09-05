"""LLM service for Milo-Cut.

Uses the OpenAI Python SDK to communicate with any OpenAI-compatible API
(DeepSeek, Qwen, Ollama, etc.). No max_tokens is set so the model can
produce complete analysis output without truncation.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from core.config import load_settings
from core.llm_prompts import get_effective_prompt
from core.logging import get_logger
from core.models import LlmConfig, LlmProvider

logger = get_logger()

# Retry configuration
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds
# AR-2: RateLimitError (429) uses a longer dedicated backoff than generic errors.
_RATE_LIMIT_BASE_DELAY = 5.0  # -> 5s, 10s, 20s


# ------------------------------------------------------------------
# M3-1: batch ledger (v3.0.0) -- no silent batch loss
# ------------------------------------------------------------------


@dataclass
class BatchLedger:
    """Per-task accounting of batch processing outcomes.

    ``uncovered_segment_ids`` lists target segment IDs whose batches failed
    even after the single automatic retry -- the UI must surface these as a
    coverage gap, never silently drop them.
    """

    total: int = 0
    succeeded: int = 0
    retried_ok: int = 0
    failed: list[int] = field(default_factory=list)
    uncovered_segment_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "retried_ok": self.retried_ok,
            "failed": list(self.failed),
            "uncovered_segment_ids": list(self.uncovered_segment_ids),
        }


# ------------------------------------------------------------------
# M3-4: SSRF guard (v3.0.0) -- reject loopback/private base URLs
# ------------------------------------------------------------------

_PRIVATE_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_base_url_security(config: LlmConfig) -> str | None:
    """Return an error message when the base URL resolves to a private net.

    Loopback/private/link-local addresses are rejected to prevent SSRF via a
    user-configured base URL. Local inference endpoints (e.g. Ollama on
    localhost:11434) must set ``llm_allow_local_urls: true`` in settings.
    Returns None when the URL is allowed.
    """
    if load_settings().get("llm_allow_local_urls", False):
        return None

    base_url = config.resolved_base_url()
    if not base_url:
        return None

    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/:?#]+)", base_url)
    if not match:
        return None  # unparseable; let the SDK surface the error
    host = match.group(1)

    try:
        addr_infos = socket.getaddrinfo(host, None)
    except OSError:
        return None  # DNS failure: let the API call report the real error

    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if any(ip in net for net in _PRIVATE_NETS):
            return (
                f"LLM base_url '{base_url}' 指向本机/内网地址，已被 SSRF 防护拒绝。"
                "本地模型（如 Ollama）请在 settings 中设置 llm_allow_local_urls: true 放行。"
            )
    return None


# ------------------------------------------------------------------
# M3-3: response sanitization (v3.0.0) -- 5th-layer parse fallback
# ------------------------------------------------------------------


def _sanitize_response(text: str) -> str:
    """Strip common LLM response noise around the JSON payload.

    Order: remove ``<think>...</think>`` blocks (DeepSeek R1 family), remove
    markdown code fences, then keep only the span from the first ``{`` or
    ``[`` to the last ``}`` or ``]``. Purely subtractive -- content is never
    rewritten.
    """
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```[a-zA-Z]*\s*", "", cleaned)
    cleaned = cleaned.replace("```", "")

    first_obj = cleaned.find("{")
    first_arr = cleaned.find("[")
    candidates = [c for c in (first_obj, first_arr) if c >= 0]
    if not candidates:
        return cleaned.strip()
    start = min(candidates)
    end_obj = cleaned.rfind("}")
    end_arr = cleaned.rfind("]")
    end = max(end_obj, end_arr)
    if end <= start:
        return cleaned.strip()
    return cleaned[start : end + 1]


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
        provider=LlmProvider(settings.get("llm_provider", "deepseek")),
        base_url=settings.get("llm_base_url", "").strip(),
        api_key=settings.get("llm_api_key", "").strip(),
        model=settings.get("llm_model", "").strip(),
        temperature=settings.get("llm_temperature", 0.1),
        timeout=settings.get("llm_timeout", 120),
        thinking_enabled=settings.get("llm_thinking_enabled", False),
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

    # v3.0.0 M3-4: SSRF guard on user-configured base URLs.
    ssrf_error = validate_base_url_security(config)
    if ssrf_error:
        return {"success": False, "error": ssrf_error}

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
        "temperature": config.effective_temperature(),
        # No max_tokens -- let model produce full output
    }
    if json_mode and config.provider in (LlmProvider.OPENAI, LlmProvider.DEEPSEEK):
        request_kwargs["response_format"] = {"type": "json_object"}

    # Thinking mode: pass extra_body for providers that support it
    extra_body = config.thinking_extra_body()
    if extra_body:
        request_kwargs["extra_body"] = extra_body

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
            # AR-2: 429 uses a longer dedicated backoff (5s/10s/20s) before the
            # generic exponential backoff at the bottom of the loop runs.
            if attempt < _MAX_RETRIES - 1:
                delay = _RATE_LIMIT_BASE_DELAY * (2 ** attempt)
                if cancel_event:
                    cancel_event.wait(timeout=delay)
                else:
                    time.sleep(delay)
                continue
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
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    ssrf_error = validate_base_url_security(config)
    if ssrf_error:
        return {"success": False, "error": ssrf_error}

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


def chunk_transcript_by_count(
    segments: list[dict],
    batch_size: int = 20,
    overlap: int = 4,
    max_chars: int | None = None,
) -> list[tuple[list[dict], set[str]]]:
    """Split transcript by segment count using P1-style batch+target mode.

    Each batch contains ``batch_size + 2 * overlap`` segments (context
    at boundaries), with ``target_ids`` marking the ``batch_size`` central
    segments the LLM should analyze. Overlap segments provide context only.

    v3.0.0 M3-2: when ``max_chars`` is set, a batch is truncated early once
    the accumulated text length would exceed the limit (a single target
    segment is never split in half). The effective limit is whichever of
    ``batch_size`` / ``max_chars`` is reached first.

    Args:
        segments: List of segment dicts (must have 'id' key).
        batch_size: Target analysis segments per batch. min=1.
        overlap: Context overlap on each side. min=0. Clamped to
            ``batch_size - 1`` if >= batch_size (audit #11).
        max_chars: Optional per-batch character budget (None = unlimited).

    Returns:
        [(batch_segments, target_ids), ...] where batch_segments are
        shallow-copy slices and target_ids is a set of segment ID strings.
    """
    if not segments:
        return []

    # audit #11: overlap >= batch_size guard
    if overlap >= batch_size:
        logger.warning(
            f"chunk_transcript_by_count: overlap ({overlap}) >= batch_size "
            f"({batch_size}), clamping to {batch_size - 1}"
        )
        overlap = max(0, batch_size - 1)

    total = len(segments)

    batches: list[tuple[list[dict], set[str]]] = []
    start_i = 0
    while start_i < total:
        # M3-2: honor the character budget by shrinking this batch's target
        # window (context is then derived from the shrunken window).
        end_i = min(start_i + batch_size, total)
        if max_chars is not None and max_chars > 0:
            acc = 0
            probe = start_i
            while probe < end_i:
                seg_len = len(str(segments[probe].get("text", "")))
                if probe > start_i and acc + seg_len > max_chars:
                    break
                acc += seg_len
                probe += 1
            end_i = probe if probe > start_i else start_i + 1
        ctx_start = max(0, start_i - overlap)
        ctx_end = min(total, end_i + overlap)
        batch_with_context = [dict(s) for s in segments[ctx_start:ctx_end]]  # independent copies
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}
        batches.append((batch_with_context, target_ids))
        start_i = end_i  # char-budget mode may produce smaller steps

    return batches



# ------------------------------------------------------------------
# Structured message building + layered JSON parsing (C-02)
# ------------------------------------------------------------------


def _build_opaque_id_mapping(segments: list[dict]) -> dict[str, str]:
    """Build real-id -> opaque-id (``t1..tN``) mapping (v3.0.0 M3-5).

    The mapping never leaves the local process; the model only sees opaque
    IDs and never real segment ids or timestamps.
    """
    return {str(s.get("id", s.get("segment_id", "?"))): f"t{i}" for i, s in enumerate(segments, 1)}


def _build_structured_user_message(
    segments: list[dict],
    extra_context: dict[str, Any] | None = None,
    opaque_ids: dict[str, str] | None = None,
) -> str:
    """Build structured JSON user message for LLM analysis.

    Replaces ad-hoc ``[id] text`` formatting with JSON, eliminating
    segment_id parsing ambiguity and special-character breakage.

    Args:
        segments: List of segment dicts with 'id', 'text', 'start', 'end'.
        extra_context: Additional top-level keys to merge into the payload
            (e.g. ``{"topic": "...", "reference_text": "..."}``).
        opaque_ids: When given (v3.0.0 M3-5), real ids are replaced by the
            mapping's opaque ids and ``start``/``end`` are omitted entirely --
            the model receives only ``{id, text}`` (plus optional edit_hint).

    Returns:
        JSON string suitable for the LLM user message.
    """
    seg_list: list[dict[str, Any]] = []
    for s in segments:
        real_id = str(s.get("id", s.get("segment_id", "?")))
        item: dict[str, Any] = {
            "id": opaque_ids.get(real_id, real_id) if opaque_ids else real_id,
            "text": str(s.get("text", "")).strip(),
        }
        if not opaque_ids:
            item["start"] = s.get("start")
            item["end"] = s.get("end")
        # v2.2.0: forward optional edit_hint (e.g. partial_delete reason)
        # so downstream LLM features can leverage prior edit decisions.
        edit_hint = s.get("edit_hint")
        if edit_hint:
            item["edit_hint"] = str(edit_hint)
        # v3.0.4 M2-5/R2.5: forward optional aligned main-track text.
        aligned_main_text = s.get("aligned_main_text")
        if aligned_main_text:
            item["aligned_main_text"] = str(aligned_main_text)
        seg_list.append(item)
    payload: dict[str, Any] = {"segments": seg_list}
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

    # Layer 5 (v3.0.0 M3-3): sanitize think-blocks/fences/noise, retry JSON.
    # Purely subtractive fallback after the 4 structural layers all failed.
    sanitized = _sanitize_response(content)
    if sanitized != content.strip():
        try:
            result = json.loads(sanitized)
            return result if isinstance(result, list) else [result]
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ------------------------------------------------------------------
# P0: Smart delete analysis
# ------------------------------------------------------------------


def _normalize_smart_delete_items(chunk_results: list[dict]) -> list[dict]:
    """Normalize parsed smart-delete results into a stable schema."""
    normalized: list[dict] = []
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
    return normalized


def analyze_smart_delete(
    segments: list[dict],
    existing_flagged_ids: set[str] | None = None,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
    system_prompt: str | None = None,
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

    # Batch+target mode: configurable batch_size and overlap (settings.json).
    settings = load_settings()
    batch_size = max(5, int(settings.get("llm_smart_batch_size", 20)))
    overlap_size = max(0, int(settings.get("llm_smart_overlap_size", 4)))
    concurrency = max(1, int(settings.get("llm_concurrency", 5)))
    max_chars = int(settings.get("llm_max_batch_chars", 4000) or 0) or None
    batches = chunk_transcript_by_count(
        to_analyze, batch_size=batch_size, overlap=overlap_size, max_chars=max_chars
    )
    total_batches = len(batches)
    ledger = BatchLedger(total=total_batches)

    # Resolve effective system prompt (caller override > layered default)
    effective_system = system_prompt or get_effective_prompt("smart_delete")

    results_by_index: dict[int, list[dict]] = {}
    total_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    def _call_batch(idx: int, batch_segments: list[dict], target_ids: set[str]) -> tuple[int, list[dict] | None, dict, str | None]:
        """Single smart-delete attempt (no retry)."""
        if cancel_event and cancel_event.is_set():
            return (idx, None, {}, "Cancelled")
        # M3-5: opaque id mapping -- model only sees t1..tN, no timestamps.
        id_map = _build_opaque_id_mapping(batch_segments)
        reverse_map = {v: k for k, v in id_map.items()}
        target_ids_ordered = [
            id_map[str(s.get("id", ""))]
            for s in batch_segments
            if str(s.get("id", "")) in target_ids
        ]
        extra_ctx: dict[str, Any] = {"target_segment_ids": target_ids_ordered}
        prompt = _build_structured_user_message(
            batch_segments, extra_context=extra_ctx, opaque_ids=id_map
        )
        result = call_llm(
            prompt,
            system=effective_system,
            json_mode=True,
            config=config,
            cancel_event=cancel_event,
        )
        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Smart-delete batch {idx + 1} failed: {error}")
            return (idx, None, {}, error)
        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        chunk_results = _parse_json_response_layers(content)
        if not chunk_results:
            logger.warning(f"Smart-delete batch {idx + 1}: JSON parse returned None")
            return (idx, None, usage, None)
        normalized = _normalize_smart_delete_items(chunk_results)
        # Translate opaque ids back to real ids; drop unknown ids.
        for r in normalized:
            r["segment_id"] = reverse_map.get(r.get("segment_id", ""), r.get("segment_id", ""))
        # Filter: only keep results for target_ids (same as P1, llm_service.py:783)
        normalized = [r for r in normalized if r.get("segment_id") in target_ids]
        return (idx, normalized or None, usage, None)

    def _process_chunk(idx: int, batch_segments: list[dict], target_ids: set[str]) -> tuple[int, list[dict] | None, dict, str | None, bool]:
        """Process a smart-delete batch with one automatic retry (M3-1).

        Returns:
            (idx, normalized_results_or_None, usage, error_or_None, retried)
        """
        idx_, normalized, usage, error = _call_batch(idx, batch_segments, target_ids)
        retried = False
        if normalized is None and error != "Cancelled":
            # M3-1: one automatic retry with the identical payload.
            logger.info(f"Smart-delete batch {idx + 1} failed, retrying once...")
            retried = True
            idx_, normalized, usage, error = _call_batch(idx, batch_segments, target_ids)
        return (idx_, normalized, usage, error, retried)

    # AR-2: track consecutive 429s; after 3 in a row, finish remaining chunks
    # serially to avoid hammering a rate-limited (free-tier) endpoint.
    consecutive_429 = 0
    _MAX_CONSECUTIVE_429 = 3
    serial_fallback = False
    pending_indices: set[int] = set(range(total_batches))
    completed = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_chunk, idx, batch_segs, target_ids): idx
            for idx, (batch_segs, target_ids) in enumerate(batches)
        }

        try:
            for future in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                idx, normalized, usage, error, retried = future.result()
                completed += 1
                pending_indices.discard(idx)

                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)

                # M3-1: ledger bookkeeping
                if error is None and error != "Cancelled":
                    if retried:
                        ledger.retried_ok += 1
                    else:
                        ledger.succeeded += 1
                elif error != "Cancelled":
                    if idx not in ledger.failed:
                        ledger.failed.append(idx)

                if error == "Cancelled":
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                # AR-2 adaptive downgrade on sustained 429
                if error and "Rate limited" in error:
                    consecutive_429 += 1
                    if consecutive_429 >= _MAX_CONSECUTIVE_429 and not serial_fallback and pending_indices:
                        logger.warning(
                            f"Rate limited {consecutive_429}x, switching remaining "
                            f"{len(pending_indices)} batches to serial"
                        )
                        serial_fallback = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                else:
                    consecutive_429 = 0

                if normalized:
                    results_by_index[idx] = normalized
                    if chunk_callback:
                        chunk_callback(normalized)

                if progress_cb:
                    pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                    target_count = len(batches[idx][1]) if idx < len(batches) else 0
                    progress_cb(pct, f"Smart-delete batch {completed}/{total_batches} (target={target_count} segs)...")
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    # Serial fallback for remaining chunks after sustained 429 (AR-2)
    if serial_fallback:
        for idx in sorted(pending_indices):
            if cancel_event and cancel_event.is_set():
                return {"success": False, "error": "Cancelled"}
            if progress_cb:
                pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                target_count = len(batches[idx][1])
                progress_cb(pct, f"Smart-delete batch {completed}/{total_batches} (serial, target={target_count} segs)...")
            idx_, normalized, usage, _, retried = _process_chunk(idx, batches[idx][0], batches[idx][1])
            completed += 1
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)
            if retried and normalized is not None:
                ledger.retried_ok += 1
            elif normalized is None:
                if idx not in ledger.failed:
                    ledger.failed.append(idx)
            else:
                ledger.succeeded += 1
            if normalized:
                results_by_index[idx] = normalized
                if chunk_callback:
                    chunk_callback(normalized)

    # Merge results in original chunk order for timeline consistency
    all_results: list[dict] = []
    for idx in range(total_batches):
        if idx in results_by_index:
            all_results.extend(results_by_index[idx])

    # Deduplicate by segment_id, keeping the last occurrence
    seen: dict[str, dict] = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())

    # M3-1: uncovered = target segments of batches that failed even after retry
    uncovered: list[str] = []
    for idx in ledger.failed:
        if idx < len(batches):
            uncovered.extend(sorted(batches[idx][1]))
    ledger.uncovered_segment_ids = sorted(set(uncovered))
    if ledger.uncovered_segment_ids:
        logger.warning(
            f"Smart-delete coverage gap: {len(ledger.uncovered_segment_ids)} segment(s) "
            f"in failed batches {ledger.failed}"
        )

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(deduped)} smart-delete suggestions")

    logger.info(
        f"Smart-delete analysis done: {len(deduped)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}, "
        f"ledger={ledger.total}b/{ledger.succeeded}+{ledger.retried_ok}ok/{len(ledger.failed)}fail"
    )

    return {
        "success": True,
        "data": {
            "results": deduped,
            "token_usage": total_usage,
            "ledger": ledger.to_dict(),
        },
    }


# ------------------------------------------------------------------
# P1: Subtitle correction
# ------------------------------------------------------------------

def analyze_subtitle_correction(
    segments: list[dict],
    reference_text: str | None = None,
    context_window: int = 3,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    system_prompt_a: str | None = None,
    system_prompt_b: str | None = None,
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
    # Resolve effective system prompt (caller override > layered default)
    if is_mode_b:
        system = system_prompt_b or get_effective_prompt("subtitle_correction_b")
    else:
        system = system_prompt_a or get_effective_prompt("subtitle_correction_a")

    # v2.1.1 M2: batch_size/context_window are configurable (settings.json).
    settings = load_settings()
    batch_size = max(1, int(settings.get("llm_correction_batch_size", 30)))
    # Caller-supplied context_window wins over settings for back-compat.
    effective_ctx = context_window if context_window != 3 else int(
        settings.get("llm_correction_context_window", 5)
    )
    concurrency = max(1, int(settings.get("llm_concurrency", 5)))
    max_chars = int(settings.get("llm_max_batch_chars", 4000) or 0) or None

    # M3-2: apply character budget by shrinking target windows first.
    target_windows: list[tuple[int, int]] = []
    start_i = 0
    while start_i < len(segments):
        end_i = min(start_i + batch_size, len(segments))
        if max_chars:
            acc = 0
            probe = start_i
            while probe < end_i:
                seg_len = len(str(segments[probe].get("text", "")))
                if probe > start_i and acc + seg_len > max_chars:
                    break
                acc += seg_len
                probe += 1
            end_i = probe if probe > start_i else start_i + 1
        target_windows.append((start_i, end_i))
        start_i = end_i

    total_batches = len(target_windows)
    ledger = BatchLedger(total=total_batches)

    # Pre-compute each batch's payload (batch_with_context, target_ids, prompt).
    batch_payloads: list[tuple[set[str], str, dict[str, str]]] = []
    for _batch_idx, (start_i, end_i) in enumerate(target_windows):
        ctx_start = max(0, start_i - effective_ctx)
        ctx_end = min(len(segments), end_i + effective_ctx)
        batch_with_context = segments[ctx_start:ctx_end]
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}
        id_map = _build_opaque_id_mapping(batch_with_context)  # M3-5
        extra_ctx: dict[str, Any] = {
            "target_segment_ids": [id_map[i] for i in sorted(target_ids)]
        }
        if is_mode_b:
            extra_ctx["reference_text"] = reference_text
        prompt = _build_structured_user_message(
            batch_with_context, extra_context=extra_ctx, opaque_ids=id_map
        )
        batch_payloads.append((target_ids, prompt, id_map))

    def _call_batch(batch_idx: int) -> tuple[int, list[dict], dict, str | None]:
        """Single correction attempt (no retry)."""
        if cancel_event and cancel_event.is_set():
            return (batch_idx, [], {}, "Cancelled")
        target_ids, prompt, id_map = batch_payloads[batch_idx]
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
            return (batch_idx, [], {}, error)
        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        parsed = _parse_json_response_layers(content)
        if not parsed:
            logger.warning(f"Subtitle correction batch {batch_idx + 1}: parse returned None")
            return (batch_idx, [], usage, None)

        start_i, end_i = target_windows[batch_idx]
        ctx_start = max(0, start_i - effective_ctx)
        ctx_end = min(len(segments), end_i + effective_ctx)
        orig_text_by_id = {
            str(s.get("id", "")): str(s.get("text", "")).strip()
            for s in segments[ctx_start:ctx_end]
        }
        corrections: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            seg_id = str(item.get("segment_id", ""))
            # M3-5: translate opaque id back to the real segment id
            reverse_map = {v: k for k, v in id_map.items()}
            seg_id = reverse_map.get(seg_id, seg_id)
            if not seg_id or seg_id not in target_ids:
                continue
            category = str(item.get("category", "none"))
            corrected = str(item.get("corrected_text", "")).strip()
            if category == "none":
                continue
            if corrected == orig_text_by_id.get(seg_id, ""):
                continue
            corrections.append(
                {
                    "segment_id": seg_id,
                    "corrected_text": corrected,
                    "changes": item.get("changes", []),
                    "category": category,
                    "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.9)))),
                }
            )
        return (batch_idx, corrections, usage, None)

    def _process_batch(batch_idx: int) -> tuple[int, list[dict], dict, str | None, bool]:
        """Process one correction batch with one automatic retry (M3-1)."""
        idx_, corrections, usage, error = _call_batch(batch_idx)
        retried = False
        if not corrections and error != "Cancelled":
            logger.info(f"Subtitle correction batch {batch_idx + 1} failed, retrying once...")
            retried = True
            idx_, corrections, usage, error = _call_batch(batch_idx)
        return (idx_, corrections, usage, error, retried)

    corrections_by_index: dict[int, list[dict]] = {}
    total_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    # AR-2: sustained 429 -> finish remaining batches serially.
    consecutive_429 = 0
    _MAX_CONSECUTIVE_429 = 3
    serial_fallback = False
    pending: set[int] = set(range(total_batches))
    completed = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_batch, batch_idx): batch_idx
            for batch_idx in range(total_batches)
        }
        try:
            for future in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                batch_idx, corrections, usage, error, retried = future.result()
                completed += 1
                pending.discard(batch_idx)

                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)

                # M3-1: ledger bookkeeping
                if error is None:
                    if retried:
                        ledger.retried_ok += 1
                    else:
                        ledger.succeeded += 1
                elif error != "Cancelled":
                    if batch_idx not in ledger.failed:
                        ledger.failed.append(batch_idx)

                if error == "Cancelled":
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                if error and "Rate limited" in error:
                    consecutive_429 += 1
                    if consecutive_429 >= _MAX_CONSECUTIVE_429 and not serial_fallback and pending:
                        logger.warning(
                            f"Rate limited {consecutive_429}x, switching remaining "
                            f"{len(pending)} batches to serial"
                        )
                        serial_fallback = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                else:
                    consecutive_429 = 0

                if corrections:
                    corrections_by_index[batch_idx] = corrections

                if progress_cb:
                    pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                    progress_cb(pct, f"Subtitle correction batch {completed}/{total_batches}...")
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    if serial_fallback:
        for batch_idx in sorted(pending):
            if cancel_event and cancel_event.is_set():
                return {"success": False, "error": "Cancelled"}
            if progress_cb:
                pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                progress_cb(pct, f"Subtitle correction batch {completed}/{total_batches} (serial)...")
            _, corrections, usage, _, retried = _process_batch(batch_idx)
            completed += 1
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)
            if retried and corrections:
                ledger.retried_ok += 1
            elif not corrections and batch_idx not in ledger.failed:
                ledger.failed.append(batch_idx)
            if corrections:
                corrections_by_index[batch_idx] = corrections

    # M3-1: uncovered = target segments of batches that failed even after retry
    uncovered: list[str] = []
    for batch_idx in ledger.failed:
        if batch_idx < len(batch_payloads):
            uncovered.extend(sorted(batch_payloads[batch_idx][0]))
    ledger.uncovered_segment_ids = sorted(set(uncovered))
    if ledger.uncovered_segment_ids:
        logger.warning(
            f"Correction coverage gap: {len(ledger.uncovered_segment_ids)} segment(s) "
            f"in failed batches {ledger.failed}"
        )

    # Merge in original batch order
    all_corrections: list[dict] = []
    for batch_idx in range(total_batches):
        if batch_idx in corrections_by_index:
            all_corrections.extend(corrections_by_index[batch_idx])

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(all_corrections)} corrections")

    logger.info(
        f"Subtitle correction done: {len(all_corrections)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}, mode={'B' if is_mode_b else 'A'}"
    )

    return {
        "success": True,
        "data": {
            "corrections": all_corrections,
            "token_usage": total_usage,
            "ledger": ledger.to_dict(),
        },
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


# ------------------------------------------------------------------
# P2: Highlight extraction
# ------------------------------------------------------------------

def analyze_highlights(
    segments: list[dict],
    target_duration_minutes: int = 10,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Full-transcript LLM analysis to extract highlight segments.

    Identifies high-information-density segments for generating a highlight
    reel. Uses 5-min chunks (full context needed for structure understanding).

    Args:
        segments: List of segment dicts with 'id', 'start', 'end', 'text'.
        target_duration_minutes: Target highlight reel duration in minutes.
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.
        progress_cb: Optional progress callback (percent, message).
        chunk_callback: Optional callback receiving per-chunk results.

    Returns:
        {"success": True, "data": {"results": [...], "token_usage": {...},
         "total_highlight_duration": float}}
        {"success": False, "error": str}
    """
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    if not segments:
        return {"success": False, "error": "No segments to analyze"}

    target_seconds = target_duration_minutes * 60

    # Highlight needs full context for structure understanding -- use large
    # chunks (30 min) so most videos are analyzed in a single LLM call and
    # multi-sentence arguments stay intact. Only 30+ min recordings split.
    # v2.1.1 M2: chunk/overlap durations are configurable (settings.json).
    settings = load_settings()
    chunk_dur = float(settings.get("llm_highlight_chunk_duration", 1800.0))
    overlap_dur = float(settings.get("llm_highlight_overlap_duration", 60.0))
    chunks = chunk_transcript(segments, chunk_duration=chunk_dur, overlap_duration=overlap_dur)
    total_chunks = len(chunks)

    # Resolve effective system prompt (caller override > layered default)
    effective_system = system_prompt or get_effective_prompt("highlight")

    # Full-transcript analysis produces long output -- extend the timeout so
    # large inputs don't fail before the model finishes generating.
    highlight_config = config.model_copy(update={"timeout": max(config.timeout, 300)})

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
            progress_cb(pct, f"Highlight analysis chunk {idx + 1}/{total_chunks}...")

        extra_ctx = {
            "target_duration_minutes": target_duration_minutes,
            "instruction": "请按信息密度优先级标记亮点片段",
        }
        prompt = _build_structured_user_message(chunk, extra_context=extra_ctx)
        result = call_llm(
            prompt,
            system=effective_system,
            json_mode=True,
            config=highlight_config,
            cancel_event=cancel_event,
        )

        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Highlight chunk {idx + 1} failed: {error}")
            continue

        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        for key in total_usage:
            total_usage[key] += usage.get(key, 0)

        chunk_results = _parse_json_response_layers(content)
        if not chunk_results:
            logger.warning(f"Highlight chunk {idx + 1}: parse returned None")
            continue

        normalized = []
        for item in chunk_results:
            if not isinstance(item, dict):
                continue
            seg_id = str(item.get("segment_id", ""))
            if not seg_id:
                continue
            density = str(item.get("density", "medium")).lower()
            if density not in ("high", "medium", "low"):
                density = "medium"
            normalized.append(
                {
                    "segment_id": seg_id,
                    "highlight_reason": str(item.get("highlight_reason", "")),
                    "density": density,
                }
            )

        if normalized and chunk_callback:
            chunk_callback(normalized)
        all_results.extend(normalized)

    # Deduplicate by segment_id
    seen: dict[str, dict] = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())

    # Duration-based trimming: sort by density priority, trim to target
    seg_map = {str(s.get("id", "")): s for s in segments}
    density_rank = {"high": 0, "medium": 1, "low": 2}
    deduped.sort(key=lambda r: density_rank.get(r["density"], 1))

    selected: list[dict] = []
    total_dur = 0.0
    for r in deduped:
        seg = seg_map.get(r["segment_id"])
        if seg is None:
            continue
        dur = seg.get("end", 0) - seg.get("start", 0)
        if total_dur + dur > target_seconds * 1.2 and total_dur >= target_seconds * 0.8:
            break
        selected.append(r)
        total_dur += dur

    # Re-sort by start time for natural playback order
    selected.sort(key=lambda r: seg_map.get(r["segment_id"], {}).get("start", 0))

    if progress_cb:
        progress_cb(
            100.0,
            f"Completed: {len(selected)} highlights, {total_dur:.1f}s / {target_seconds:.1f}s target",
        )

    logger.info(
        f"Highlight analysis done: {len(selected)} segments, "
        f"duration={total_dur:.1f}s, tokens={total_usage.get('total_tokens', 0)}"
    )

    return {
        "success": True,
        "data": {
            "results": selected,
            "token_usage": total_usage,
            "total_highlight_duration": total_dur,
            "target_duration": target_seconds,
        },
    }


# ------------------------------------------------------------------
# P3: Semantic search
# ------------------------------------------------------------------

def semantic_search(
    query: str,
    segments: list[dict],
    top_k: int = 5,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Natural language semantic search over transcript segments.

    Uses LLM to find semantically relevant segments (not just keyword match).

    Args:
        query: Natural language search query.
        segments: List of segment dicts with 'id', 'start', 'end', 'text'.
        top_k: Maximum number of results to return.
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.

    Returns:
        {"success": True, "data": {"results": [...], "query": str}}
        {"success": False, "error": str}
    """
    if config is None:
        config = get_llm_config()

    # M3-5: semantic search is a deterministic retrieval task -> temperature 0.
    config = config.model_copy(update={"temperature_override": 0.0})

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    if not query.strip():
        return {"success": False, "error": "Empty query"}

    if not segments:
        return {"success": False, "error": "No segments to search"}

    # Single LLM call (no chunking -- context window limited)
    # For very long transcripts, truncate to last N segments
    max_segments = 200
    search_segments = segments[-max_segments:] if len(segments) > max_segments else segments

    extra_ctx = {"query": query.strip(), "top_k": top_k}
    # Resolve effective system prompt (caller override > layered default)
    effective_system = system_prompt or get_effective_prompt("search")

    prompt = _build_structured_user_message(search_segments, extra_context=extra_ctx)
    result = call_llm(
        prompt,
        system=effective_system,
        json_mode=True,
        config=config,
        cancel_event=cancel_event,
    )

    if not result.get("success"):
        return result

    content = result["data"]["content"]
    usage = result["data"].get("usage", {})
    parsed = _parse_json_response_layers(content)
    if not parsed:
        return {
            "success": False,
            "error": "Failed to parse LLM search response",
        }

    # Normalize results
    normalized = []
    seg_map = {str(s.get("id", "")): s for s in segments}
    for item in parsed[:top_k]:
        if not isinstance(item, dict):
            continue
        seg_id = str(item.get("segment_id", ""))
        if not seg_id or seg_id not in seg_map:
            continue
        try:
            relevance = float(item.get("relevance", 0.5))
        except (TypeError, ValueError):
            relevance = 0.5
        relevance = max(0.0, min(1.0, relevance))
        normalized.append(
            {
                "segment_id": seg_id,
                "relevance": relevance,
                "match_reason": str(item.get("match_reason", "")),
            }
        )

    # Sort by relevance descending
    normalized.sort(key=lambda r: r["relevance"], reverse=True)

    logger.info(f"Semantic search '{query}': {len(normalized)} results")

    return {
        "success": True,
        "data": {
            "results": normalized[:top_k],
            "query": query.strip(),
            "token_usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        },
    }


# ------------------------------------------------------------------
# v3.0.4 M1-2: AI translation pipeline (P1-3)
# ------------------------------------------------------------------


def _translation_segment_id(seg: dict) -> str:
    """Real segment id from a translation source segment dict.

    The translation handler passes source segments as ``{"segment_id",
    "start", "end", "text"}`` (SPEC M1-2); the shared correction-skeleton
    helpers read ``id`` first, so translation normalizes every input to the
    internal ``{"id", "text"}`` shape via this extractor (``segment_id``
    wins, ``id`` is the fallback for direct service-level callers).
    """
    return str(seg.get("segment_id", seg.get("id", "")))


def _validate_translation_coverage(
    parsed_items: list[dict] | None,
    target_ids: set[str],
    id_map: dict[str, str],
) -> tuple[list[dict], str | None]:
    """Reverse coverage check: the output must conserve the target id set.

    Unlike correction (subset semantics -- segments needing no fix are
    simply omitted), translation requires a full-output conservation: every
    target id must come back exactly once. Missing ids mean untranslated
    segments; unknown or duplicated ids mean hallucinated output. Either
    violation fails the batch (and, after its retry, the whole task).

    Returns:
        (translations, None) on conservation, ([], error message) otherwise.
    """
    if not parsed_items:
        return [], "Empty translation output"

    reverse_map = {v: k for k, v in id_map.items()}
    translations: list[dict] = []
    seen_ids: set[str] = set()
    unknown_ids: list[str] = []
    duplicate_ids: list[str] = []
    for item in parsed_items:
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("segment_id", ""))
        # M3-5 pattern: translate opaque id back to the real segment id
        seg_id = reverse_map.get(raw_id, raw_id)
        if seg_id not in target_ids:
            if seg_id not in unknown_ids:
                unknown_ids.append(seg_id)
            continue
        if seg_id in seen_ids:
            if seg_id not in duplicate_ids:
                duplicate_ids.append(seg_id)
            continue
        seen_ids.add(seg_id)
        translations.append(
            {
                "segment_id": seg_id,
                "translated_text": str(item.get("translated_text", "")).strip(),
            }
        )

    missing_ids = sorted(target_ids - seen_ids)
    problems: list[str] = []
    if missing_ids:
        problems.append(f"missing ids: {missing_ids}")
    if unknown_ids:
        problems.append(f"unknown ids: {unknown_ids}")
    if duplicate_ids:
        problems.append(f"duplicate ids: {duplicate_ids}")
    if problems:
        return [], "Translation coverage violation (" + "; ".join(problems) + ")"
    return translations, None


def analyze_subtitle_translation(
    segments: list[dict],
    target_language: str,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """LLM-powered subtitle translation into a target language (v3.0.4 M1-2).

    Replicates the ``analyze_subtitle_correction`` batch skeleton (batch
    windows of ``llm_correction_batch_size`` shrunk by the
    ``llm_max_batch_chars`` budget, ``llm_concurrency`` pool, opaque ids,
    4-layer JSON parsing, BatchLedger, one retry per batch, sustained-429
    serial fallback, per-batch cancel checks and batch-granularity
    progress) with the translation-specific differences:

    - Context is SOURCE text only (+/- ``llm_correction_context_window``
      adjacent segments pre-built into each payload). Concurrent dispatch
      cannot see finalized translations of other batches, so the
      "finalized-translation sliding window" is out of scope by design.
    - Reverse coverage validation: every batch output must conserve the
      target id set exactly (missing / unknown / duplicated ids all fail).
      Any batch failing after its single retry fails the WHOLE task --
      the caller must persist nothing.

    Args:
        segments: Source segment dicts ``{"segment_id", "start", "end",
            "text"}``. No track/deletion filtering happens here -- the
            handler owns segment selection (SPEC M1-2 boundary).
        target_language: Target language (display name; injected into the
            system prompt by the handler's ``{{target_language}}``
            replacement, not by this function).
        config: LLM config (loads from settings if None).
        cancel_event: Thread-safe cancellation signal.
        progress_cb: Optional progress callback (percent, message).
        system_prompt: Caller-resolved system prompt override; falls back
            to the layered ``translation`` default (which still carries the
            raw ``{{target_language}}`` placeholder -- the handler replaces
            it, SPEC M1-3).

    Returns:
        {"success": True, "data": {"translations": [...], "token_usage":
         {...}, "ledger": {...}}} with translations ordered like the input
        segments (full conservation).
        {"success": False, "error": str, "data": {"ledger", "token_usage"}}
        when any batch failed after its retry (coverage violation, parse
        failure, or API error) -- "data" is attached for observability
        only; cancelled runs return a bare error envelope like correction.
    """
    if config is None:
        config = get_llm_config()

    if not config.is_configured():
        return {"success": False, "error": "LLM not configured"}

    if not segments:
        return {"success": False, "error": "No segments to translate"}

    if not target_language or not str(target_language).strip():
        return {"success": False, "error": "Empty target language"}

    # Resolve effective system prompt (caller override > layered default).
    system = system_prompt or get_effective_prompt("translation")

    # Same settings knobs as the correction skeleton (no new config keys).
    settings = load_settings()
    batch_size = max(1, int(settings.get("llm_correction_batch_size", 30)))
    effective_ctx = max(0, int(settings.get("llm_correction_context_window", 5)))
    concurrency = max(1, int(settings.get("llm_concurrency", 5)))
    max_chars = int(settings.get("llm_max_batch_chars", 4000) or 0) or None

    # Normalize handler input ({"segment_id", ...}) to the internal
    # {"id", "text"} shape the shared correction-skeleton helpers expect.
    source_segments: list[dict] = [
        {"id": _translation_segment_id(s), "text": str(s.get("text", ""))}
        for s in segments
    ]

    # M3-2 pattern: apply character budget by shrinking target windows first.
    target_windows: list[tuple[int, int]] = []
    start_i = 0
    while start_i < len(source_segments):
        end_i = min(start_i + batch_size, len(source_segments))
        if max_chars:
            acc = 0
            probe = start_i
            while probe < end_i:
                seg_len = len(str(source_segments[probe].get("text", "")))
                if probe > start_i and acc + seg_len > max_chars:
                    break
                acc += seg_len
                probe += 1
            end_i = probe if probe > start_i else start_i + 1
        target_windows.append((start_i, end_i))
        start_i = end_i

    total_batches = len(target_windows)
    ledger = BatchLedger(total=total_batches)

    # Pre-compute each batch's payload (context = SOURCE text +/- ctx only:
    # batches dispatch concurrently, so finalized translations of sibling
    # batches are unavailable by construction -- SPEC M1-2 ruling).
    batch_payloads: list[tuple[set[str], str, dict[str, str]]] = []
    for _batch_idx, (start_i, end_i) in enumerate(target_windows):
        ctx_start = max(0, start_i - effective_ctx)
        ctx_end = min(len(source_segments), end_i + effective_ctx)
        batch_with_context = source_segments[ctx_start:ctx_end]
        target_ids = {str(source_segments[i].get("id", "")) for i in range(start_i, end_i)}
        id_map = _build_opaque_id_mapping(batch_with_context)  # M3-5
        extra_ctx: dict[str, Any] = {
            "target_segment_ids": [id_map[i] for i in sorted(target_ids)],
        }
        prompt = _build_structured_user_message(
            batch_with_context, extra_context=extra_ctx, opaque_ids=id_map
        )
        batch_payloads.append((target_ids, prompt, id_map))

    def _call_batch(batch_idx: int) -> tuple[int, list[dict], dict, str | None]:
        """Single translation attempt (no retry)."""
        if cancel_event and cancel_event.is_set():
            return (batch_idx, [], {}, "Cancelled")
        target_ids, prompt, id_map = batch_payloads[batch_idx]
        result = call_llm(
            prompt,
            system=system,
            json_mode=True,
            config=config,
            cancel_event=cancel_event,
        )
        if not result.get("success"):
            error = result.get("error", "LLM call failed")
            logger.warning(f"Translation batch {batch_idx + 1} failed: {error}")
            return (batch_idx, [], {}, error)
        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        parsed = _parse_json_response_layers(content)
        if not parsed:
            logger.warning(f"Translation batch {batch_idx + 1}: parse returned None")
            return (batch_idx, [], usage, "Unparseable LLM translation response")
        translations, coverage_error = _validate_translation_coverage(
            parsed, target_ids, id_map
        )
        if coverage_error:
            logger.warning(
                f"Translation batch {batch_idx + 1} coverage check failed: {coverage_error}"
            )
            return (batch_idx, [], usage, coverage_error)
        return (batch_idx, translations, usage, None)

    def _process_batch(batch_idx: int) -> tuple[int, list[dict], dict, str | None, bool]:
        """Process one translation batch with one automatic retry (M1-2)."""
        idx_, translations, usage, error = _call_batch(batch_idx)
        retried = False
        if error != "Cancelled" and (error is not None or not translations):
            logger.info(f"Translation batch {batch_idx + 1} failed, retrying once...")
            retried = True
            idx_, translations, usage, error = _call_batch(batch_idx)
        return (idx_, translations, usage, error, retried)

    translations_by_index: dict[int, list[dict]] = {}
    total_usage: dict[str, int] = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    # AR-2 pattern: sustained 429 -> finish remaining batches serially.
    consecutive_429 = 0
    _MAX_CONSECUTIVE_429 = 3
    serial_fallback = False
    pending: set[int] = set(range(total_batches))
    completed = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(_process_batch, batch_idx): batch_idx
            for batch_idx in range(total_batches)
        }
        try:
            for future in as_completed(futures):
                if cancel_event and cancel_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                batch_idx, translations, usage, error, retried = future.result()
                completed += 1
                pending.discard(batch_idx)

                for key in total_usage:
                    total_usage[key] += usage.get(key, 0)

                # M3-1 pattern: ledger bookkeeping
                if error is None:
                    if retried:
                        ledger.retried_ok += 1
                    else:
                        ledger.succeeded += 1
                elif error != "Cancelled":
                    if batch_idx not in ledger.failed:
                        ledger.failed.append(batch_idx)

                if error == "Cancelled":
                    executor.shutdown(wait=False, cancel_futures=True)
                    return {"success": False, "error": "Cancelled"}

                if error and "Rate limited" in error:
                    consecutive_429 += 1
                    if consecutive_429 >= _MAX_CONSECUTIVE_429 and not serial_fallback and pending:
                        logger.warning(
                            f"Rate limited {consecutive_429}x, switching remaining "
                            f"{len(pending)} batches to serial"
                        )
                        serial_fallback = True
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                else:
                    consecutive_429 = 0

                if translations:
                    translations_by_index[batch_idx] = translations

                if progress_cb:
                    pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                    progress_cb(pct, f"Translation batch {completed}/{total_batches}...")
        except Exception:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    if serial_fallback:
        for batch_idx in sorted(pending):
            if cancel_event and cancel_event.is_set():
                return {"success": False, "error": "Cancelled"}
            if progress_cb:
                pct = (completed / total_batches) * 100 if total_batches > 0 else 0
                progress_cb(pct, f"Translation batch {completed}/{total_batches} (serial)...")
            _, translations, usage, error, retried = _process_batch(batch_idx)
            completed += 1
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)
            if error is None:
                if retried:
                    ledger.retried_ok += 1
                else:
                    ledger.succeeded += 1
            elif error != "Cancelled" and batch_idx not in ledger.failed:
                ledger.failed.append(batch_idx)
            if translations:
                translations_by_index[batch_idx] = translations

    # M3-1 pattern: uncovered = target segments of failed batches.
    uncovered: list[str] = []
    for batch_idx in ledger.failed:
        if batch_idx < len(batch_payloads):
            uncovered.extend(sorted(batch_payloads[batch_idx][0]))
    ledger.uncovered_segment_ids = sorted(set(uncovered))

    # M1-2 key difference vs correction: full-output conservation -- a batch
    # that still fails after its retry fails the WHOLE task (zero persistence
    # upstream), instead of returning partial results.
    if ledger.failed:
        if ledger.uncovered_segment_ids:
            logger.warning(
                f"Translation coverage gap: {len(ledger.uncovered_segment_ids)} segment(s) "
                f"in failed batches {sorted(ledger.failed)}"
            )
        error = (
            f"Translation incomplete: {len(ledger.failed)}/{total_batches} batch(es) "
            f"failed after retry (batches {sorted(ledger.failed)}), "
            f"{len(ledger.uncovered_segment_ids)} segment(s) uncovered"
        )
        return {
            "success": False,
            "error": error,
            "data": {"ledger": ledger.to_dict(), "token_usage": total_usage},
        }

    # Merge in original segment order (conservation guarantees each target
    # id appears exactly once, so the index sort is total and stable).
    order_by_id = {
        str(s.get("id", "")): i for i, s in enumerate(source_segments)
    }
    all_translations: list[dict] = []
    for batch_idx in range(total_batches):
        if batch_idx in translations_by_index:
            all_translations.extend(translations_by_index[batch_idx])
    all_translations.sort(key=lambda t: order_by_id.get(t["segment_id"], len(order_by_id)))

    if progress_cb:
        progress_cb(100.0, f"Completed: {len(all_translations)} translations")

    logger.info(
        f"Translation done: {len(all_translations)} results, "
        f"tokens={total_usage.get('total_tokens', 0)}, target={target_language}, "
        f"ledger={ledger.total}b/{ledger.succeeded}+{ledger.retried_ok}ok/{len(ledger.failed)}fail"
    )

    return {
        "success": True,
        "data": {
            "translations": all_translations,
            "token_usage": total_usage,
            "ledger": ledger.to_dict(),
        },
    }

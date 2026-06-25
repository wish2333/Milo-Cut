"""Inline diff computation for subtitle correction review.

Uses ``difflib.SequenceMatcher`` to compute character-level diffs between the
original and corrected subtitle text. Chinese text is compared per Unicode
character (D-56); the frontend aggregates adjacent delete/insert blocks into
visual "replace" fragments when their gap is small (D-69).

The token model is intentionally minimal -- only ``text`` + ``type`` -- so the
frontend can apply its own aggregation rules without backend-specific
fragments leaking through.
"""

from __future__ import annotations

import difflib
from typing import Any, Literal

DiffTokenType = Literal["equal", "delete", "insert"]


def compute_inline_diff(original: str, corrected: str) -> dict[str, Any]:
    """Compute a character-level inline diff between two strings.

    Args:
        original: The original (ASR) subtitle text.
        corrected: The LLM-corrected subtitle text.

    Returns:
        ``{"tokens": [{"text": str, "type": "equal"|"delete"|"insert"}, ...]}``.
        Identical inputs yield a single ``equal`` token spanning the whole
        string. Empty inputs are handled gracefully.
    """
    if original == corrected:
        # No differences -- single equal token (or empty if both blank).
        if not original:
            return {"tokens": []}
        return {"tokens": [{"text": original, "type": "equal"}]}

    matcher = difflib.SequenceMatcher(None, original, corrected, autojunk=False)
    tokens: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            tokens.append({"text": original[i1:i2], "type": "equal"})
        elif tag == "replace":
            # difflib "replace" -> emit delete then insert so the frontend can
            # aggregate them into a visual replace block (D-69).
            tokens.append({"text": original[i1:i2], "type": "delete"})
            tokens.append({"text": corrected[j1:j2], "type": "insert"})
        elif tag == "delete":
            tokens.append({"text": original[i1:i2], "type": "delete"})
        elif tag == "insert":
            tokens.append({"text": corrected[j1:j2], "type": "insert"})
    return {"tokens": tokens}


def compute_diffs_batch(pairs: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Compute inline diffs for multiple original/corrected pairs.

    Args:
        pairs: List of ``{"original": str, "corrected": str}``.

    Returns:
        List of diff result dicts, one per input pair (same order).
    """
    return [
        compute_inline_diff(p.get("original", ""), p.get("corrected", ""))
        for p in pairs
    ]

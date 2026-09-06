"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from core.models import AnalysisResult, EditStatus, Timeline, Word

# Tolerance (characters) when matching the text split index against word
# boundaries. Punctuation/whitespace noise around the cut point is expected;
# a larger deviation means alignment is unreliable.
_WORD_ALIGN_TOLERANCE_CHARS = 2

# v3.0.0 P4-1: correction word reattachment. Similarity below this threshold
# means the correction rewrote more than half the segment -- the remaining
# timestamp anchors are untrustworthy, so words are cleared entirely.
_REATTACH_MIN_SIMILARITY = 0.5

# Same tokenization convention as scripts/fabricate_words.py: one token per
# CJK char, latin/digit runs stay a single token, other chars (punctuation)
# are single tokens, whitespace is dropped.
_FRAGMENT_TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+|[\u4e00-\u9fff\u3400-\u4dbf]"
    r"|[^\sA-Za-z0-9\u4e00-\u9fff\u3400-\u4dbf]"
)


def _tokenize_fragment(fragment: str) -> list[str]:
    """Split a new-text fragment into word tokens (house convention)."""
    return _FRAGMENT_TOKEN_RE.findall(fragment)


def _synthesize_words(
    fragment: str, t_prev: float, t_next: float
) -> list[Word]:
    """Build words for an uncovered new-text region by time interpolation.

    The region's time window is [t_prev, t_next] (anchors from the
    surrounding kept words, falling back to the segment bounds). Tokens are
    distributed proportionally to their character length; synthesized words
    carry ``confidence=0.0`` to mark estimated timing.
    """
    tokens = _tokenize_fragment(fragment)
    if not tokens:
        return []
    total = sum(len(t) for t in tokens)
    span = max(t_next - t_prev, 0.0)
    out: list[Word] = []
    cur = t_prev
    for tok in tokens:
        share = len(tok) / total * span
        out.append(Word(word=tok, start=cur, end=cur + share, confidence=0.0))
        cur += share
    return out


def reattach_words(
    words: list[Word],
    new_text: str,
    seg_start: float | None = None,
    seg_end: float | None = None,
) -> list[Word]:
    """Re-align a segment's words against corrected text (PRD D1.2).

    Alignment source is the concatenation of the existing word tokens (the
    ground truth of where words sit in the old text), diffed against
    ``new_text`` with a character-level ``SequenceMatcher``:

    - words fully inside an ``equal`` region keep their original timestamps;
    - uncovered regions of the new text (replaced / inserted / straddled
      spans) are re-tokenized and get interpolated timestamps between the
      surrounding anchors (segment bounds as outer fallback), with
      ``confidence=0.0``;
    - deleted text simply drops its words.

    Reliability rules ("prefer missing over misaligned"):
    - similarity < 0.5 -> ``[]`` (rewrite too large, anchors untrustworthy);
    - no word fits fully inside an equal region -> ``[]`` (no anchor);
    - on success the emitted tokens concatenate exactly to ``new_text``.

    Args:
        words: Existing word list (ordered by start); empty -> ``[]``.
        new_text: Corrected segment text.
        seg_start: Segment start (interpolation fallback for leading gaps).
        seg_end: Segment end (interpolation fallback for trailing gaps).

    Returns:
        The re-aligned word list, or ``[]`` when alignment is unreliable.
    """
    if not words or not new_text:
        return []

    old_concat = "".join(w.word for w in words)
    if old_concat == new_text:
        return list(words)

    sm = SequenceMatcher(None, old_concat, new_text, autojunk=False)
    if sm.ratio() < _REATTACH_MIN_SIMILARITY:
        return []

    # Character span of each old word inside old_concat.
    spans: list[tuple[int, int]] = []
    off = 0
    for w in words:
        spans.append((off, off + len(w.word)))
        off += len(w.word)

    # 1. Old words fully inside an equal region keep their timestamps; their
    #    new-text positions are the equal region's offset plus the in-span
    #    delta (equal regions are character-identical by definition).
    kept: list[tuple[int, int, Word]] = []
    for op, i1, i2, j1, _j2 in sm.get_opcodes():
        if op != "equal":
            continue
        for w, (ws, we) in zip(words, spans, strict=True):
            if ws >= i1 and we <= i2:
                kept.append((j1 + ws - i1, j1 + we - i1, w))
    kept.sort(key=lambda k: k[0])
    if not kept:
        return []

    # 2. Coverage walk over the new text: emit kept words in order and
    #    synthesize tokens for every uncovered region between them. A gap's
    #    right anchor is the kept word that follows it (``w.start``).
    result: list[Word] = []
    b_pos = 0
    prev_end: float | None = None
    for j_start, j_end, w in kept:
        if j_start > b_pos:
            t_prev = prev_end if prev_end is not None else (
                seg_start if seg_start is not None else w.start
            )
            result.extend(_synthesize_words(new_text[b_pos:j_start], t_prev, w.start))
        result.append(w)
        b_pos = j_end
        prev_end = w.end
    if b_pos < len(new_text):
        t_prev = prev_end if prev_end is not None else (
            seg_start if seg_start is not None else 0.0
        )
        t_next = seg_end if seg_end is not None else t_prev
        result.extend(_synthesize_words(new_text[b_pos:], t_prev, t_next))
    return result


def split_words(
    words: list[Word],
    text: str,
    position: int,
    a_text: str,
    b_text: str,
) -> tuple[list[Word], list[Word]]:
    """Split a segment's words at the given text character position.

    Strategy: walk the cumulative per-word text length to find the word
    boundary closest to ``position``; if the best boundary deviates by more
    than 2 characters (punctuation/whitespace noise), alignment is deemed
    unreliable and ``([], [])`` is returned -- prefer missing words over
    misaligned ones.

    Args:
        words: The segment's word list (assumed ordered by start).
        text: The original full text (unused for alignment itself, kept for
              signature clarity / future validation).
        position: Character index in ``text`` where the split happens.
        a_text: Resulting text of segment a (must be non-empty).
        b_text: Resulting text of segment b (must be non-empty).

    Returns:
        (a_words, b_words): both empty when alignment fails; the concatenation
        preserves the original word order when it succeeds.
    """
    if not words or len(words) < 2 or position <= 0 or position >= len(text):
        return ([], [])
    if not a_text or not b_text:
        return ([], [])

    # Cumulative character offsets at the START of each word.
    offsets: list[int] = []
    acc = 0
    for w in words:
        offsets.append(acc)
        acc += len(w.word)

    total_chars = acc
    if total_chars == 0:
        return ([], [])

    # Candidate split: number of words assigned to a = k (1 <= k < len(words)).
    # Boundary after word k-1 lands at offset[k] (start of word k). Pick the
    # boundary closest to the requested position.
    candidates = range(1, len(words))
    best_k = min(candidates, key=lambda k: abs(offsets[k] - position))

    boundary = offsets[best_k]
    if abs(boundary - position) > _WORD_ALIGN_TOLERANCE_CHARS:
        return ([], [])

    a_words = list(words[:best_k])
    b_words = list(words[best_k:])
    if not a_words or not b_words:
        return ([], [])
    return (a_words, b_words)


def collect_confirmed_deleted_seg_ids(timeline: Timeline) -> set[str]:
    """Return segment IDs targeted by confirmed delete decisions.

    Only ``action="delete" AND status=confirmed`` edits with
    ``target_type="segment"`` contribute. Used by P0/P1 to skip
    already-confirmed-deleted segments from LLM analysis input.
    """
    result: set[str] = set()
    for edit in timeline.edits:
        if (
            edit.action == "delete"
            and edit.status == EditStatus.CONFIRMED
            and edit.target_type == "segment"
            and edit.target_id
        ):
            result.add(edit.target_id)
    return result


def collect_partial_delete_hints(timeline: Timeline) -> dict[str, str]:
    """Return ``{segment_id: hint_text}`` for partial_delete analysis results.

    v2.2.0: Subtitle correction leverages prior "partial delete" smart-delete
    decisions. A partial_delete indicates the segment contains intra-sentence
    errors (e.g. "他是那段历史中的他是那段历史的亲历者") that cannot be
    wholesale deleted but *should* be cleaned up textually.

    This collects those hints so they can be forwarded to the subtitle
    correction LLM as ``edit_hint`` metadata on the segment payload.
    """
    hints: dict[str, str] = {}
    for ar in timeline.analysis.results:
        if not isinstance(ar, AnalysisResult):
            continue
        if ar.category != "partial_delete":
            continue
        reason = ar.detail.strip() if ar.detail else ""
        for seg_id in ar.segment_ids:
            if seg_id and seg_id not in hints:
                hints[seg_id] = reason or "句内含口误/重复，建议修正"
    return hints

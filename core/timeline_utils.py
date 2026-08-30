"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

from core.models import AnalysisResult, EditStatus, Timeline, Word

# Tolerance (characters) when matching the text split index against word
# boundaries. Punctuation/whitespace noise around the cut point is expected;
# a larger deviation means alignment is unreliable.
_WORD_ALIGN_TOLERANCE_CHARS = 2


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

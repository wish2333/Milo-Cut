"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

from core.models import AnalysisResult, EditStatus, Timeline


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

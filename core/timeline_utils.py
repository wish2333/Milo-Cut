"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

from core.models import EditStatus, Timeline


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

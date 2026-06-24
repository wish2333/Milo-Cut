"""Tests for core/timeline_utils.py"""

from __future__ import annotations

from core.models import EditDecision, EditStatus, Timeline, TranscriptData
from core.timeline_utils import collect_confirmed_deleted_seg_ids


def _make_timeline(*edits: EditDecision) -> Timeline:
    """Build a Timeline with the given edits for testing."""
    return Timeline(
        id="default",
        label="Test",
        source="test",
        transcript=TranscriptData(segments=[]),
        edits=list(edits),
    )


def test_confirmed_delete_segment_collected():
    """Confirmed delete with target_type=segment should be collected."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="delete", source="test", analysis_id=None,
        status=EditStatus.CONFIRMED, priority=50,
        target_type="segment", target_id="seg_1",
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == {"seg_1"}


def test_keep_action_not_collected():
    """Confirmed keep should NOT be collected."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="keep", source="test", analysis_id=None,
        status=EditStatus.CONFIRMED, priority=50,
        target_type="segment", target_id="seg_1",
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == set()


def test_pending_delete_not_collected():
    """Pending delete should NOT be collected."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="delete", source="test", analysis_id=None,
        status=EditStatus.PENDING, priority=50,
        target_type="segment", target_id="seg_1",
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == set()


def test_rejected_delete_not_collected():
    """Rejected delete should NOT be collected."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="delete", source="test", analysis_id=None,
        status=EditStatus.REJECTED, priority=50,
        target_type="segment", target_id="seg_1",
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == set()


def test_range_target_type_ignored():
    """Confirmed delete with target_type=range should NOT be collected."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="delete", source="test", analysis_id=None,
        status=EditStatus.CONFIRMED, priority=50,
        target_type="range", target_id="seg_1",
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == set()


def test_missing_target_id_ignored():
    """Confirmed delete with target_type=range and no target_id should NOT crash."""
    edit = EditDecision(
        id="edit_1", start=0.0, end=1.0,
        action="delete", source="test", analysis_id=None,
        status=EditStatus.CONFIRMED, priority=50,
        target_type="range", target_id=None,
    )
    result = collect_confirmed_deleted_seg_ids(_make_timeline(edit))
    assert result == set()


def test_multiple_edits_mixed():
    """Only confirmed-delete-segment edits should be returned."""
    edits = [
        EditDecision(
            id="edit_1", start=0.0, end=1.0,
            action="delete", source="test", analysis_id=None,
            status=EditStatus.CONFIRMED, priority=50,
            target_type="segment", target_id="seg_1",
        ),
        EditDecision(
            id="edit_2", start=1.0, end=2.0,
            action="keep", source="test", analysis_id=None,
            status=EditStatus.CONFIRMED, priority=50,
            target_type="segment", target_id="seg_2",
        ),
        EditDecision(
            id="edit_3", start=2.0, end=3.0,
            action="delete", source="test", analysis_id=None,
            status=EditStatus.PENDING, priority=50,
            target_type="segment", target_id="seg_3",
        ),
        EditDecision(
            id="edit_4", start=3.0, end=4.0,
            action="delete", source="test", analysis_id=None,
            status=EditStatus.CONFIRMED, priority=50,
            target_type="segment", target_id="seg_4",
        ),
        EditDecision(
            id="edit_5", start=4.0, end=5.0,
            action="delete", source="test", analysis_id=None,
            status=EditStatus.CONFIRMED, priority=50,
            target_type="range", target_id="seg_5",
        ),
    ]
    result = collect_confirmed_deleted_seg_ids(_make_timeline(*edits))
    assert result == {"seg_1", "seg_4"}


def test_empty_edits():
    """Empty edits list should return empty set."""
    result = collect_confirmed_deleted_seg_ids(_make_timeline())
    assert result == set()

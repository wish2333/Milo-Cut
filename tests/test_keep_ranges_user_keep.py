"""v3.0.4 P3-9 M4-4: user keep awareness in generate_subtitle_keep_ranges.

Locks (SPEC M4-4 / PLAN P3-9, controlled change 1):
- keep set awareness: confirmed keep ranges (action=keep, status=confirmed,
  target_type=range, SOURCE-AGNOSTIC) merge into the auto keep ranges, so
  kept spans are subtracted from the delete complement (partial keeps split
  a gap; whole-gap keeps remove it; keeps bridging segments collapse the
  keep set through adjacency).
- stale trim invalidation: a pre-existing source="subtitle_trim" delete
  edit intersecting a user keep is removed on re-run, counted in returned
  data.invalidated_count; NON-intersecting subtitle_trim edits survive
  (count is exactly the intersecting ones, not all).
- zero regression: pending/rejected keeps never participate (behavior
  identical to the no-keep case); the byte-for-byte golden criterion
  itself lives in tests/test_keep_ranges_golden.py (P3-1 baseline) and
  must stay green untouched.
- export priority: keep + confirmed manual delete on the same range
  coexist -- generation succeeds, the manual delete survives in edits,
  and _get_confirmed_deletions (export consumer, delete-only) still
  carries the range: export obeys delete (SPEC M4-4 boundary 3).
- extracted helper: _merge_time_ranges (the former inline adjacent-merge
  fold) unit-tested on adjacent/overlapping/out-of-order/nested input.

Segment fixture: two subtitle segments (2.0-4.0 / 6.0-8.0), padding=0.3
-> auto keep ranges (1.7, 4.3) and (5.7, 8.0) (total duration = max end
= 8.0), auto delete ranges (0.0, 1.7) and (4.3, 5.7).

Mock style follows tests/test_add_range_decision.py (paths monkeypatched
+ real ProjectService; no bridge/LLM plumbing needed here).
"""

from __future__ import annotations

import pytest

from core.export_service import _get_confirmed_deletions
from core.models import EditStatus, Segment, SegmentType
from core.project_service import ProjectService, _merge_time_ranges

# ================================================================
# Helpers (mirror tests/test_add_range_decision.py)
# ================================================================


def _subtitle_segments(bounds: list[tuple[float, float]]) -> list[Segment]:
    return [
        Segment(
            id=f"seg-{i}",
            type=SegmentType.SUBTITLE,
            start=start,
            end=end,
            text=f"句{i}",
        )
        for i, (start, end) in enumerate(bounds)
    ]


def _install_segments(svc: ProjectService, segs: list[Segment]) -> None:
    """Install main-track segments the way the service sees them 'now'."""
    tl = svc.active_timeline
    svc._current = svc._current.model_copy(
        update={
            "timelines": [
                tl.model_copy(
                    update={
                        "transcript": tl.transcript.model_copy(
                            update={"segments": segs}
                        )
                    }
                )
            ]
        }
    )


def _confirmed_keep(svc: ProjectService, start: float, end: float, source: str = "manual"):
    """Create + confirm a user keep range via the real M4-1 entry point.

    The create call returns a ProjectPatch envelope (only the idempotent
    duplicate path returns edit_id), so the new edit is fetched from the
    timeline by its bounds.
    """
    created = svc.add_range_decision(start, end, action="keep", source=source)
    assert created["success"] is True, created
    (edit,) = [
        e for e in svc.active_timeline.edits
        if e.action == "keep" and (e.start, e.end) == (start, end)
    ]
    confirmed = svc.update_edit_decision(edit.id, "confirmed")
    assert confirmed["success"] is True, confirmed
    return edit.id


def _delete_edits(svc: ProjectService) -> list:
    return [e for e in svc.active_timeline.edits if e.action == "delete"]


def _trim_edits(svc: ProjectService) -> list:
    return [
        e for e in svc.active_timeline.edits if e.source == "subtitle_trim"
    ]


def _overlaps(span: tuple[float, float], edit) -> bool:
    return edit.start < span[1] and span[0] < edit.end


@pytest.fixture
def svc(monkeypatch, tmp_path) -> ProjectService:
    monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
    monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
    # Bound import inside project_service (create_project writes).
    monkeypatch.setattr(
        "core.project_service.get_projects_dir", lambda: tmp_path / "projects"
    )
    service = ProjectService()
    service.create_project("t", "/fake/media.mp4", {"duration": 10.0})
    _install_segments(service, _subtitle_segments([(2.0, 4.0), (6.0, 8.0)]))
    return service


# ================================================================
# 1. keep punches through the auto delete ranges
# ================================================================


class TestKeepPunchThrough:
    def test_confirmed_keep_punches_hole_in_auto_delete_gap(self, svc):
        """A partial keep inside the middle gap splits it: the kept span is
        inside NO delete edit, the two gap remainders become deletes, and
        the untouched gap keeps its whole delete."""
        _confirmed_keep(svc, 4.5, 5.0)

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True

        # Gap (4.3, 5.7) split into (4.3, 4.5) + (5.0, 5.7); leading gap intact
        assert result["data"]["delete_ranges"] == 3
        assert result["data"]["invalidated_count"] == 0  # no pre-existing trim

        deletes = _delete_edits(svc)
        assert sorted((e.start, e.end) for e in deletes) == [
            (0.0, 1.7),
            (4.3, 4.5),
            (5.0, 5.7),
        ]
        # The keep span is inside no delete edit (any source)
        for e in deletes:
            assert not _overlaps((4.5, 5.0), e), (e.start, e.end)
        # The keep range itself survives in edits
        assert any(
            e.action == "keep" and (e.start, e.end) == (4.5, 5.0)
            for e in svc.active_timeline.edits
        )

    def test_keep_covering_whole_gap_removes_it_source_agnostic(self, svc):
        """A keep exactly covering the middle gap removes it from the delete
        complement entirely. Source is NOT restricted to "manual" -- the
        collection is source-agnostic (future producers inherit)."""
        _confirmed_keep(svc, 4.3, 5.7, source="future_producer")

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True
        assert result["data"]["delete_ranges"] == 1

        # Only the leading gap remains as a delete; none overlaps the keep
        trims = _trim_edits(svc)
        assert [(e.start, e.end) for e in trims] == [(0.0, 1.7)]
        for e in _delete_edits(svc):
            assert not _overlaps((4.3, 5.7), e), (e.start, e.end)

    def test_keep_bridging_segments_merges_keep_ranges(self, svc):
        """A keep spanning segment tail + whole gap + next segment head
        merges the auto keep ranges into one via the adjacency rule."""
        _confirmed_keep(svc, 3.5, 6.5)

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True
        # (1.7,4.3) + (3.5,6.5) + (5.7,8.0) collapse into a single keep
        assert result["data"]["keep_ranges"] == 1
        assert result["data"]["delete_ranges"] == 1
        assert [(e.start, e.end) for e in _trim_edits(svc)] == [(0.0, 1.7)]


# ================================================================
# 2. stale subtitle_trim invalidation
# ================================================================


class TestStaleTrimInvalidation:
    def test_intersecting_trim_invalidated_counted_others_kept(self, svc):
        """Re-run scenario: keep lands inside an existing subtitle_trim
        delete -> that stale edit is removed (invalidated_count == 1, NOT
        2), the non-intersecting trim edit survives by id, and the two gap
        remainders are regenerated as fresh subtitle_trim deletes."""
        first = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert first["success"] is True
        assert first["data"]["delete_ranges"] == 2
        original_ids = [e.id for e in _trim_edits(svc)]
        untouched_id = original_ids[0]  # edit-subtitle-trim-0000 (0.0, 1.7)
        # original_ids[1] is the stale whole-gap edit (4.3, 5.7); its serial
        # id may be legitimately reused by a regenerated partial below, so
        # removal is asserted on BOUNDS, not on id.

        # User keeps (5.0, 5.5): intersects ONLY the second trim edit
        _confirmed_keep(svc, 5.0, 5.5)

        second = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert second["success"] is True
        assert second["data"]["invalidated_count"] == 1  # exactly one, not 2
        assert second["data"]["new_edits"] == 2  # (4.3, 5.0) + (5.5, 5.7)

        trims = _trim_edits(svc)
        # Untouched trim survives with its original id and bounds
        untouched = [e for e in trims if e.id == untouched_id]
        assert [(e.start, e.end) for e in untouched] == [(0.0, 1.7)]
        # The stale whole-gap edit is gone; its span is covered by the
        # two regenerated remainders instead
        trim_bounds = sorted((e.start, e.end) for e in trims)
        assert trim_bounds == [(0.0, 1.7), (4.3, 5.0), (5.5, 5.7)]
        assert (4.3, 5.7) not in trim_bounds
        # Whole timeline: 1 kept old trim + 2 new partials + 1 keep range
        assert len(svc.active_timeline.edits) == 4
        # The stale id may be reused by a regenerated partial (serial ids
        # depend on enumerate order) -- the invariant is bounds, not ids.


# ================================================================
# 3. keep vs manual delete: export obeys delete
# ================================================================


class TestKeepVsManualDelete:
    def test_coexist_generation_ok_delete_wins_for_export(self, svc):
        """Confirmed keep + confirmed manual delete on the same range:
        generation succeeds, the manual delete survives in edits (only
        subtitle_trim is ever invalidated), and the export consumer
        (_get_confirmed_deletions, delete-only) carries the range."""
        # Cross-action same-range coexistence is legal (M4-1 contract 3)
        keep_id = _confirmed_keep(svc, 4.3, 5.7)
        del_created = svc.add_range_decision(4.3, 5.7, action="delete")
        assert del_created["success"] is True
        (manual_del,) = [
            e for e in svc.active_timeline.edits
            if e.action == "delete" and e.source == "manual"
        ]
        del_id = manual_del.id
        assert svc.update_edit_decision(del_id, "confirmed")["success"]

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True

        edits = svc.active_timeline.edits
        # The manual delete survives generation untouched
        manual_delete = [e for e in edits if e.id == del_id]
        assert len(manual_delete) == 1
        assert manual_delete[0].action == "delete"
        assert manual_delete[0].status == EditStatus.CONFIRMED
        # The keep survives too (generation never removes user keeps)
        assert any(e.id == keep_id for e in edits)
        # The gap is punched out of the AUTO ranges (no subtitle_trim there)
        for e in _trim_edits(svc):
            assert not _overlaps((4.3, 5.7), e), (e.start, e.end)
        # Export consumption is delete-only: the range still exports as a
        # deletion -- delete wins over keep (SPEC M4-4 boundary 3)
        deletions = _get_confirmed_deletions(
            [e.model_dump(mode="json") for e in edits]
        )
        assert (4.3, 5.7) in deletions
        assert (0.0, 1.7) in deletions


# ================================================================
# 4. pending / rejected keeps never participate
# ================================================================


class TestNonConfirmedKeeps:
    def test_pending_and_rejected_keeps_do_not_participate(self, svc):
        """Pending keep on the middle gap + rejected keep on the leading
        gap: behavior identical to no keeps at all -- both gaps stay whole
        delete ranges, invalidated_count == 0."""
        pending = svc.add_range_decision(4.5, 5.0, action="keep")
        assert pending["success"] is True
        rejected = svc.add_range_decision(0.5, 1.0, action="keep")
        assert rejected["success"] is True
        (rejected_edit,) = [
            e for e in svc.active_timeline.edits
            if e.action == "keep" and (e.start, e.end) == (0.5, 1.0)
        ]
        assert svc.update_edit_decision(rejected_edit.id, "rejected")["success"]

        result = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert result["success"] is True
        # Same shape as the no-keep v3.0.3 output
        assert result["data"]["keep_ranges"] == 2
        assert result["data"]["delete_ranges"] == 2
        assert result["data"]["invalidated_count"] == 0
        assert sorted((e.start, e.end) for e in _trim_edits(svc)) == [
            (0.0, 1.7),
            (4.3, 5.7),
        ]


# ================================================================
# 5. extracted helper (_merge_time_ranges) self-verification
# ================================================================


class TestMergeTimeRanges:
    """The former inline adjacent-merge fold, now a module-level helper
    (extraction is the sanctioned refactor of P3-9; these tests lock the
    rule itself: adjacent merge <=, overlap merge, order irrelevance)."""

    def test_adjacent_ranges_merge(self):
        # Touching ranges (start == current end) merge -- the "<=" rule
        assert _merge_time_ranges([(0.0, 1.0), (1.0, 2.0)]) == [(0.0, 2.0)]
        # A chain of touching ranges collapses into one
        assert _merge_time_ranges([(0.0, 1.0), (1.0, 2.0), (2.0, 3.5)]) == [
            (0.0, 3.5)
        ]

    def test_overlapping_and_nested_ranges_merge(self):
        assert _merge_time_ranges([(0.0, 2.0), (1.0, 3.0)]) == [(0.0, 3.0)]
        # Nested range is absorbed
        assert _merge_time_ranges([(0.0, 10.0), (2.0, 3.0)]) == [(0.0, 10.0)]
        # Exact duplicate collapses
        assert _merge_time_ranges([(1.0, 2.0), (1.0, 2.0)]) == [(1.0, 2.0)]
        # Disjoint ranges stay separate
        assert _merge_time_ranges([(0.0, 1.0), (2.0, 3.0)]) == [
            (0.0, 1.0),
            (2.0, 3.0),
        ]

    def test_out_of_order_input_sorted_before_merging(self):
        assert _merge_time_ranges(
            [(5.0, 6.0), (0.0, 1.0), (1.5, 3.0), (0.5, 0.8)]
        ) == [(0.0, 1.0), (1.5, 3.0), (5.0, 6.0)]
        # Out-of-order chain still collapses via sort-then-fold
        assert _merge_time_ranges([(2.0, 3.0), (0.0, 1.0), (1.0, 2.0)]) == [
            (0.0, 3.0)
        ]

    def test_empty_and_single_input(self):
        assert _merge_time_ranges([]) == []
        assert _merge_time_ranges([(1.0, 2.0)]) == [(1.0, 2.0)]

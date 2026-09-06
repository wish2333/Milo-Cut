"""Boundary-case table for the backend constraint kernel (SPEC M1/M2).

Mirror of ``frontend/src/utils/trackConstraints.test.ts`` -- the SAME
case list pins the TS kernel (M0-1). Keep both sides in sync.
"""

import math

import pytest

from core.models import Segment
from core.track_constraints import (
    MIN_SEGMENT_DURATION,
    NeighborBounds,
    clamp_extension_range,
    constrain_bound_extension_panel_edit,
    constrain_cue_range_to_track,
    get_track_neighbor_bounds,
    overlaps_neighbors,
    rebuild_binding_offsets,
    reconcile_extension_track,
    snap_to_step,
    sync_bound_extension_for_main,
)


def seg(id: str, start: float, end: float) -> Segment:
    return Segment(id=id, start=start, end=end)


# ------------------------------------------------------------------
# snap_to_step + constants
# ------------------------------------------------------------------


class TestSnapToStep:
    def test_bit_identical_to_legacy_for_default_step(self):
        # JS Math.round semantics (half-up); Python round() is banker's and
        # diverges on exact ties (12.345*100 == 1234.5 -> JS 1235, Py 1234).
        for t in (0.3, 0.07, 1.005, 12.345, 99.999):
            assert snap_to_step(t) == math.floor(t * 100 + 0.5) / 100

    def test_snaps_to_nearest_step(self):
        assert snap_to_step(0.123) == 0.12
        assert snap_to_step(0.125) == 0.13
        assert snap_to_step(2.04, 0.1) == pytest.approx(2.0, abs=1e-9)

    def test_rejects_bad_input(self):
        with pytest.raises(ValueError):
            snap_to_step(float("nan"))
        with pytest.raises(ValueError):
            snap_to_step(float("inf"))
        with pytest.raises(ValueError):
            snap_to_step(1, 0)

    def test_constants_match_legacy_values(self):
        assert MIN_SEGMENT_DURATION == 0.1


# ------------------------------------------------------------------
# get_track_neighbor_bounds
# ------------------------------------------------------------------


class TestGetTrackNeighborBounds:
    track = [seg("a", 0, 1), seg("b", 1, 2), seg("c", 2, 3)]

    def test_empty_track(self):
        assert get_track_neighbor_bounds([], "a") == NeighborBounds()

    def test_unknown_id(self):
        assert get_track_neighbor_bounds(self.track, "zz") == NeighborBounds()

    def test_first_segment(self):
        assert get_track_neighbor_bounds(self.track, "a") == NeighborBounds(None, 1)

    def test_last_segment(self):
        assert get_track_neighbor_bounds(self.track, "c") == NeighborBounds(2, None)

    def test_middle_segment(self):
        assert get_track_neighbor_bounds(self.track, "b") == NeighborBounds(1, 2)

    def test_moved_ids_are_exempt(self):
        assert get_track_neighbor_bounds(self.track, "c", {"b"}) == NeighborBounds(1, None)
        assert get_track_neighbor_bounds(self.track, "a", {"b"}) == NeighborBounds(None, 2)

    def test_tolerates_unsorted_input(self):
        shuffled = [seg("c", 2, 3), seg("a", 0, 1), seg("b", 1, 2)]
        assert get_track_neighbor_bounds(shuffled, "b") == NeighborBounds(1, 2)


# ------------------------------------------------------------------
# constrain_cue_range_to_track
# ------------------------------------------------------------------


class TestConstrainCueRangeToTrack:
    def test_passes_through_without_neighbors(self):
        r = constrain_cue_range_to_track(5, 6, NeighborBounds())
        assert (r.ok, r.start, r.end) == (True, 5, 6)

    def test_clamps_against_previous_only(self):
        r = constrain_cue_range_to_track(0.5, 1.5, NeighborBounds(1, None))
        assert (r.ok, r.start, r.end) == (True, 1, 1.5)

    def test_clamps_against_next_only(self):
        r = constrain_cue_range_to_track(1.5, 2.5, NeighborBounds(None, 2))
        assert (r.ok, r.start, r.end) == (True, 1.5, 2)

    def test_clamps_into_gap_spanning_both(self):
        r = constrain_cue_range_to_track(0, 10, NeighborBounds(1, 2))
        assert (r.ok, r.start, r.end) == (True, 1, 2)

    def test_blocks_when_gap_narrower_than_min(self):
        r = constrain_cue_range_to_track(1, 1.05, NeighborBounds(1, 1.05))
        assert r.ok is False and r.reason == "gap-too-narrow"
        assert r.gap == pytest.approx(0.05, abs=1e-9)

    def test_gap_exactly_min_is_allowed(self):
        r = constrain_cue_range_to_track(1, 1.1, NeighborBounds(1, 1.1))
        assert r.ok is True

    def test_slides_hugging_previous(self):
        # gap [1,3]; dragged [2.95, 3.05]: clamped width 0.05 < min -> slide [1, 1.1]
        r = constrain_cue_range_to_track(2.95, 3.05, NeighborBounds(1, 3))
        assert (r.ok, r.start, r.end) == (True, 1, 1.1)

    def test_caps_when_both_hugs_overflow(self):
        # gap [1,3]; dragged [2.99, 5.49] (width 2.5): hug-prev [1,3.5] X,
        # hug-next [0.5,3] X -> cap [1,3]
        r = constrain_cue_range_to_track(2.99, 5.49, NeighborBounds(1, 3))
        assert (r.ok, r.start, r.end) == (True, 1, 3)

    def test_caps_width_to_gap_when_wider(self):
        r = constrain_cue_range_to_track(0, 10, NeighborBounds(1, 1.5))
        assert (r.ok, r.start, r.end) == (True, 1, 1.5)

    def test_touching_edges_legal(self):
        r = constrain_cue_range_to_track(1, 2, NeighborBounds(1, 2))
        assert (r.ok, r.start, r.end) == (True, 1, 2)

    def test_swaps_reversed_input(self):
        r = constrain_cue_range_to_track(6, 5, NeighborBounds())
        assert (r.ok, r.start, r.end) == (True, 5, 6)

    def test_rejects_non_finite(self):
        with pytest.raises(ValueError):
            constrain_cue_range_to_track(float("nan"), 1, NeighborBounds())
        with pytest.raises(ValueError):
            constrain_cue_range_to_track(1, float("inf"), NeighborBounds())


# ------------------------------------------------------------------
# clamp_extension_range
# ------------------------------------------------------------------


class TestClampExtensionRange:
    def test_in_bounds_with_round3(self):
        assert clamp_extension_range(1, 2, 10) == (1, 2)
        assert clamp_extension_range(1.12345, 2.00004, 10) == (1.123, 2)

    def test_clamps_negative_start(self):
        assert clamp_extension_range(-1, 0.5, 10) == (0, 0.5)

    def test_clamps_end_beyond_duration(self):
        assert clamp_extension_range(9.5, 11, 10) == (9.5, 10)

    def test_widens_below_min_away_from_zero(self):
        assert clamp_extension_range(1, 1.05, 10) == (1, 1.1)

    def test_widens_toward_tail_at_last_slot(self):
        assert clamp_extension_range(9.95, 10, 10) == (9.9, 10)

    def test_degenerates_when_duration_le_min(self):
        assert clamp_extension_range(0, 0.05, 0.05) == (0, 0.05)
        assert clamp_extension_range(2, 3, 0.05) == (0, 0.05)

    def test_collapses_non_positive_duration(self):
        assert clamp_extension_range(1, 2, 0) == (0, 0)
        assert clamp_extension_range(1, 2, -5) == (0, 0)

    def test_rejects_non_finite(self):
        for args in ((float("nan"), 1, 10), (1, float("inf"), 10), (1, 2, float("nan"))):
            with pytest.raises(ValueError):
                clamp_extension_range(*args)


# ------------------------------------------------------------------
# overlaps_neighbors
# ------------------------------------------------------------------


class TestOverlapsNeighbors:
    lane = [seg("a", 0, 1), seg("b", 2, 3), seg("c", 4, 5)]

    def test_detects_true_overlap(self):
        assert overlaps_neighbors(2.5, 3.5, self.lane, "x") is True
        assert overlaps_neighbors(0.5, 2.5, self.lane, "x") is True

    def test_touching_edges_are_not_overlap(self):
        assert overlaps_neighbors(1, 2, self.lane, "x") is False
        assert overlaps_neighbors(3, 4, self.lane, "x") is False

    def test_disjoint_is_false(self):
        assert overlaps_neighbors(1.2, 1.8, self.lane, "x") is False

    def test_skips_self_and_moved(self):
        assert overlaps_neighbors(2.2, 2.8, self.lane, "b") is False
        assert overlaps_neighbors(2.2, 2.8, self.lane, "x", {"b"}) is False


# ------------------------------------------------------------------
# reconcile_extension_track
# ------------------------------------------------------------------


class TestReconcileExtensionTrack:
    def test_keeps_non_intersecting_untouched(self):
        r = reconcile_extension_track([seg("x", 0, 1)], [(5, 6)])
        assert r.segments == [{"id": "x", "start": 0, "end": 1}]
        assert r.removed_ids == []
        assert (r.counters.squeezed, r.counters.removed, r.counters.unbound) == (0, 0, 0)

    def test_keeps_longer_left_side(self):
        # covered [3,4]; segment [1,5]: left 2s > right 1s -> keep left
        r = reconcile_extension_track([seg("x", 1, 5)], [(3, 4)])
        assert r.segments == [{"id": "x", "start": 1, "end": 3}]
        assert r.counters.squeezed == 1 and r.counters.removed == 0

    def test_keeps_right_side_on_tie_takes_left(self):
        # covered [1,4.5]; segment [0.5,5]: left 0.5, right 0.5 -> tie keeps left
        r = reconcile_extension_track([seg("x", 0.5, 5)], [(1, 4.5)])
        assert r.segments == [{"id": "x", "start": 0.5, "end": 1}]

    def test_deletes_fully_covered(self):
        r = reconcile_extension_track([seg("x", 2, 3)], [(1, 4)])
        assert r.segments == [] and r.removed_ids == ["x"]
        assert (r.counters.removed, r.counters.unbound) == (1, 1)

    def test_deletes_when_longest_side_below_min(self):
        # segment [1, 2.05]; covered [1.05, 2]: both sides 0.05 < min
        r = reconcile_extension_track([seg("x", 1, 2.05)], [(1.05, 2)])
        assert r.removed_ids == ["x"] and r.counters.removed == 1

    def test_keeps_side_exactly_at_min(self):
        # segment [1, 1.3]; covered [1.1, 2]: left side [1, 1.1] = 0.1 == min
        r = reconcile_extension_track([seg("x", 1, 1.3)], [(1.1, 2)])
        assert r.segments == [{"id": "x", "start": 1, "end": 1.1}]
        assert r.counters.squeezed == 1

    def test_picks_longest_gap_straddling_two_covered(self):
        # segment [0,10]; covered [1,4] & [6,9]: gaps 1 / 2 / 1 -> keep [4,6]
        r = reconcile_extension_track([seg("x", 0, 10)], [(1, 4), (6, 9)])
        assert r.segments == [{"id": "x", "start": 4, "end": 6}]

    def test_untouched_segment_not_counted_squeezed(self):
        r = reconcile_extension_track([seg("x", 0, 1)], [(1, 2)])
        assert r.counters.squeezed == 0

    def test_custom_min_duration(self):
        # uncovered left [0, 0.25] = 0.25 < custom min 0.3 -> removed
        r = reconcile_extension_track([seg("x", 0, 0.35)], [(0.25, 1)], min_duration=0.3)
        assert r.removed_ids == ["x"]


# ------------------------------------------------------------------
# sync_bound_extension_for_main / rebuild_binding_offsets
# ------------------------------------------------------------------


class TestLinkageFollow:
    def test_move_shifts_whole_segment(self):
        assert sync_bound_extension_for_main((1, 2), (3, 4), (1.5, 2.5)) == (3.5, 4.5)

    def test_left_trim_follows_left_edge_only(self):
        assert sync_bound_extension_for_main((1, 3), (1.5, 3), (0.5, 4)) == (1, 4)

    def test_right_trim_follows_right_edge_only(self):
        assert sync_bound_extension_for_main((1, 3), (1, 2), (0.5, 4)) == (0.5, 3)

    def test_double_trim_stacks(self):
        assert sync_bound_extension_for_main((1, 3), (1.25, 2.5), (0.5, 4)) == (0.75, 3.5)


class TestRebuildBindingOffsets:
    def test_basic_round3(self):
        assert rebuild_binding_offsets((1, 2), (1.5, 2.5)) == {
            "start_offset": 0.5,
            "end_offset": 0.5,
        }

    def test_negative_offsets_survive_float_noise(self):
        r = rebuild_binding_offsets((2, 4), (1.0000000001, 3.1234999))
        assert r["start_offset"] == -1
        assert r["end_offset"] == -0.877


# ------------------------------------------------------------------
# constrain_bound_extension_panel_edit
# ------------------------------------------------------------------


class TestConstrainBoundExtensionPanelEdit:
    main = (5, 6)

    def test_full_delta_applies(self):
        r = constrain_bound_extension_panel_edit(0.5, self.main, NeighborBounds())
        assert (r.ok, r.main_start, r.main_end, r.shifted) == (True, 5.5, 6.5, 0.5)

    def test_partial_delta_clamped_by_neighbor(self):
        # prevEnd 5.5: proposed [4,5] clamps start to 5.5 -> shifted +0.5
        r = constrain_bound_extension_panel_edit(-1, self.main, NeighborBounds(5.5, None))
        assert (r.ok, r.main_start, r.main_end, r.shifted) == (True, 5.5, 6.5, 0.5)

    def test_fails_closed_on_blocked_gap(self):
        r = constrain_bound_extension_panel_edit(1, self.main, NeighborBounds(7, 7.05))
        assert (r.ok, r.main_start, r.main_end, r.shifted) == (False, 5, 6, 0.0)

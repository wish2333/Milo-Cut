"""v3.0.4 P3-5 M4-1: add_range_decision service + expose.

Locks (SPEC M4-1 contract 1-5 / PLAN P3-5):
- clamp: start<0 / end>duration clamped to media duration; media missing
  -> upper bound = max subtitle-segment end; media missing AND no
  subtitle segments -> early rejection (empty-max() guard, same
  caliber as generate_subtitle_keep_ranges).
- inverted range rejected after clamp (both direct and clamp-induced).
- action validation ("delete" / "keep" only).
- dedup: same action + |start-diff|<0.05 AND |end-diff|<0.05 (any
  status) -> idempotent duplicate return with ZERO writes (no patch,
  no revision bump); cross-action same range coexist; beyond-threshold
  / one-sided diffs create new edits.
- full lifecycle: create pending -> update_edit_decision confirm ->
  export preview (_get_confirmed_deletions) carries the manual range
  alongside subtitle_trim auto ranges with no duplicates ->
  delete_edit_decisions_batch single delete -> recreate same params is
  a NEW edit (idempotency only holds while an existing near-equal edit
  is present) -> duplicate=True returns the NEW id.
- expose: main.py add_range_decision thin passthrough (success
  envelope + service called + PROJECT_DIRTY via _mark_dirty).

Mock style follows tests/test_translation_expose.py (MiloCutApi.__new__
shell + real ProjectService), no LLM/task plumbing needed here.
"""

from __future__ import annotations

import pytest

from core.export_service import _get_confirmed_deletions
from core.models import EditStatus, Segment, SegmentType
from core.project_service import ProjectService
from main import MiloCutApi

# ================================================================
# Helpers
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


def _drop_media(svc: ProjectService) -> None:
    """Simulate a project without media info (media=None branch)."""
    svc._current = svc._current.model_copy(update={"media": None})


def _manual_edits(svc: ProjectService) -> list:
    return [e for e in svc.active_timeline.edits if e.source == "manual"]


# ================================================================
# Fixtures
# ================================================================


class _Api:
    """ProjectService sandbox + optional MiloCutApi shell for expose tests."""

    def __init__(self, monkeypatch, tmp_path):
        monkeypatch.setattr("core.paths.get_projects_dir", lambda: tmp_path / "projects")
        monkeypatch.setattr("core.paths.get_data_dir", lambda: tmp_path)
        # Bound import inside project_service (create_project writes).
        monkeypatch.setattr(
            "core.project_service.get_projects_dir", lambda: tmp_path / "projects"
        )

        self.service = ProjectService()
        self.service.create_project("t", "/fake/media.mp4", {"duration": 10.0})

        self.events: list[tuple] = []
        self.instance = MiloCutApi.__new__(MiloCutApi)
        self.instance._project = self.service
        self.instance._emit = lambda event, data=None: self.events.append(
            (event, data)
        )


@pytest.fixture
def api(monkeypatch, tmp_path):
    return _Api(monkeypatch, tmp_path)


# ================================================================
# 1. Full lifecycle (create -> confirm -> export preview -> delete ->
#    recreate -> idempotent duplicate)
# ================================================================


class TestLifecycle:
    def test_full_lifecycle_confirm_preview_delete_recreate(self, api):
        svc = api.service
        # Two subtitle segments (2.0-4.0 / 6.0-8.0): subtitle_trim
        # (padding=0.3) auto-generates confirmed delete ranges
        # (0.0, 1.7) and (4.3, 5.7) in the inter-subtitle gaps -- the
        # manual range must coexist with these, not dedup against them
        # (different bounds). NOTE: the generator's total duration is
        # the max segment END (not media.duration), so no trailing
        # range appears after the last segment.
        _install_segments(svc, _subtitle_segments([(2.0, 4.0), (6.0, 8.0)]))
        trim = svc.generate_subtitle_keep_ranges(padding=0.3)
        assert trim["success"] is True
        assert len(svc.active_timeline.edits) == 2

        # (a) create: pending manual range, patch envelope back
        result = svc.add_range_decision(2.0, 4.0)
        assert result["success"] is True
        (edit,) = _manual_edits(svc)
        assert edit.id.startswith("edit-manual-")
        assert edit.status == EditStatus.PENDING  # NOT confirmed-at-creation
        assert edit.action == "delete"
        assert edit.target_type == "range"
        assert edit.target_id is None
        assert edit.priority == 100
        assert (edit.start, edit.end) == (2.0, 4.0)
        # Patch envelope: edits layer carries the new edit, revision present
        patch = result["data"]
        assert any(e["id"] == edit.id for e in patch["edits"])
        assert isinstance(patch["revision"], int)

        # (b) confirm via the existing lifecycle method
        upd = svc.update_edit_decision(edit.id, "confirmed")
        assert upd["success"] is True

        # (c) export preview: manual range rides alongside the two
        #     subtitle_trim auto ranges, deduped (no repeated entries)
        deletions = _get_confirmed_deletions(
            [e.model_dump(mode="json") for e in svc.active_timeline.edits]
        )
        assert (2.0, 4.0) in deletions
        assert (0.0, 1.7) in deletions
        assert (4.3, 5.7) in deletions
        assert len(deletions) == len(set(deletions)) == 3

        # (d) single delete via the existing batch endpoint
        dele = svc.delete_edit_decisions_batch([edit.id])
        assert dele["success"] is True
        assert _manual_edits(svc) == []
        assert len(svc.active_timeline.edits) == 2  # subtitle_trim intact

        # (e) recreate same params: NEW edit (idempotency only holds
        #     while a near-equal edit EXISTS -- deletion cleared it)
        again = svc.add_range_decision(2.0, 4.0)
        assert again["success"] is True
        assert "duplicate" not in again["data"]
        (recreated,) = _manual_edits(svc)
        assert recreated.id != edit.id
        assert recreated.status == EditStatus.PENDING
        assert len(svc.active_timeline.edits) == 3

        # (f) same params once more, existing near-equal edit present:
        #     idempotent duplicate returning the NEW id, zero writes
        dup = svc.add_range_decision(2.0, 4.0)
        assert dup == {
            "success": True,
            "data": {"edit_id": recreated.id, "duplicate": True},
        }
        assert len(svc.active_timeline.edits) == 3


# ================================================================
# 2. clamp (contract 1)
# ================================================================


class TestClamp:
    def test_clamp_to_media_duration(self, api):
        svc = api.service  # media duration 10.0
        result = svc.add_range_decision(-2.0, 99.0)
        assert result["success"] is True
        (edit,) = svc.active_timeline.edits
        assert (edit.start, edit.end) == (0.0, 10.0)

    def test_media_missing_upper_bound_from_subtitle_segments(self, api):
        svc = api.service
        _drop_media(svc)
        _install_segments(svc, _subtitle_segments([(1.0, 3.0), (4.0, 6.0)]))
        result = svc.add_range_decision(0.0, 99.0)
        assert result["success"] is True
        (edit,) = svc.active_timeline.edits
        assert (edit.start, edit.end) == (0.0, 6.0)

    def test_media_missing_no_segments_rejected(self, api):
        svc = api.service
        _drop_media(svc)
        _install_segments(svc, [])
        result = svc.add_range_decision(0.0, 5.0)
        assert result["success"] is False
        assert result["error"] == "无媒体时长且无字幕段，无法确定范围上界"
        assert svc.active_timeline.edits == []

    def test_inverted_range_rejected_after_clamp(self, api):
        svc = api.service  # media duration 10.0
        # Direct inversion
        r1 = svc.add_range_decision(5.0, 3.0)
        assert r1["success"] is False
        assert "Invalid range" in r1["error"]
        # Clamp-induced inversion: start beyond duration, end clamped down
        r2 = svc.add_range_decision(12.0, 15.0)
        assert r2["success"] is False
        assert "Invalid range" in r2["error"]
        assert svc.active_timeline.edits == []


# ================================================================
# 3. action validation (contract 2)
# ================================================================


class TestActionValidation:
    def test_invalid_action_rejected_zero_writes(self, api):
        svc = api.service
        for bad in ("mute", "DELETE", ""):
            result = svc.add_range_decision(1.0, 2.0, action=bad)
            assert result["success"] is False, bad
            assert "Invalid action" in result["error"]
        assert svc.active_timeline.edits == []


# ================================================================
# 4. cross-action pass-through (contract 3)
# ================================================================


class TestCrossAction:
    def test_same_range_delete_and_keep_coexist(self, api):
        svc = api.service
        first = svc.add_range_decision(2.0, 4.0, action="delete")
        assert first["success"] is True
        # keep punches through delete: identical bounds still land
        second = svc.add_range_decision(2.0, 4.0, action="keep")
        assert second["success"] is True
        assert "duplicate" not in second["data"]
        edits = svc.active_timeline.edits
        assert len(edits) == 2
        assert {e.action for e in edits} == {"delete", "keep"}
        assert len({e.id for e in edits}) == 2


# ================================================================
# 5. +-0.05s idempotency (contract 3)
# ================================================================


class TestIdempotency:
    def test_near_equal_same_action_duplicate_zero_writes(self, api):
        svc = api.service
        assert svc.add_range_decision(2.0, 4.0)["success"] is True
        (edit,) = svc.active_timeline.edits
        # Any status qualifies: confirm it, then double-submit nearby
        assert svc.update_edit_decision(edit.id, "confirmed")["success"] is True
        revision_before = svc._revision

        near = svc.add_range_decision(2.03, 3.98)  # both diffs < 0.05
        assert near == {
            "success": True,
            "data": {"edit_id": edit.id, "duplicate": True},
        }
        # Zero writes: no new edit, no patch, no revision bump.
        # (Re-fetch: frozen models never mutate in place, the stored
        # copy was REPLACED by update_edit_decision's model_copy.)
        (stored,) = svc.active_timeline.edits
        assert stored.id == edit.id
        assert stored.status == EditStatus.CONFIRMED
        assert svc._revision == revision_before

        # Beyond threshold on start (|2.06 - 2.0| = 0.06 >= 0.05): passes
        far = svc.add_range_decision(2.06, 4.0)
        assert far["success"] is True
        assert "duplicate" not in far["data"]
        assert len(svc.active_timeline.edits) == 2

        # One-sided near-equal only (start close, end far): passes
        one_sided = svc.add_range_decision(2.04, 4.9)
        assert one_sided["success"] is True
        assert len(svc.active_timeline.edits) == 3


# ================================================================
# 6. expose thin passthrough (main.py)
# ================================================================


class TestExpose:
    def test_expose_passthrough_mark_dirty_and_service_called(self, api):
        result = api.instance.add_range_decision(1.0, 2.0)
        assert result["success"] is True
        # Service was called: the pending manual edit landed
        (edit,) = _manual_edits(api.service)
        assert edit.id.startswith("edit-manual-")
        assert (edit.start, edit.end) == (1.0, 2.0)
        # Envelope is the service's ProjectPatch passthrough
        assert any(e["id"] == edit.id for e in result["data"]["edits"])
        assert isinstance(result["data"]["revision"], int)
        # _mark_dirty wiring: PROJECT_DIRTY emitted on success
        assert ("project:dirty", None) in api.events

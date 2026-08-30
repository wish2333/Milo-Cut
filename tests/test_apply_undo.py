"""Protocol-consistency tests for v3.0.0 M5 layered undo (P2-1 Day 1).

``ProjectService.apply_undo(layers_payload, base_revision)`` is the single
backend entry point for the new layered undo path (SPEC M5-2). Red lines
(risk review 4.3):

- revision must strictly increase after every undo (never rewind)
- ``is_stale_patch`` semantics unchanged (stale base_revision rejected)
- cross-layer undo is atomic (split: segments+edits roll back together)
- invalid snapshots must be rejected without mutating any layer
"""

from __future__ import annotations

import pytest

from core.project_service import ProjectService


def _create_service(tmp_path, monkeypatch) -> ProjectService:
    monkeypatch.setattr("core.project_service.get_projects_dir", lambda: tmp_path)
    svc = ProjectService()
    media = tmp_path / "v.mp4"
    media.write_bytes(b"stub")
    svc.create_project("undo-test", str(media), {"duration": 100.0})
    return svc


@pytest.fixture
def svc(tmp_path, monkeypatch) -> ProjectService:
    return _create_service(tmp_path, monkeypatch)


def _seed_segments(svc: ProjectService) -> int:
    """Seed two subtitle segments; returns the service revision after.

    ``update_transcript`` still uses the legacy full-Project envelope, so
    the revision is read off the service counter after the call.
    """
    svc.update_transcript([
        {"id": "s1", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "first"},
        {"id": "s2", "type": "subtitle", "start": 10.0, "end": 15.0, "text": "second"},
    ])
    return svc._revision


class TestRevisionMonotonic:
    def test_undo_bumps_revision(self, svc: ProjectService) -> None:
        rev_before = _seed_segments(svc)
        before_segments = [
            s.model_dump(mode="json")
            for s in svc.active_timeline.transcript.segments
        ]
        res = svc.apply_undo({"segments": before_segments}, base_revision=rev_before)
        assert res["success"], res
        rev_after = res["data"]["revision"]
        assert rev_after == rev_before + 1
        assert rev_after > rev_before  # red line: never rewinds

    def test_undo_patch_carries_restored_layers(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        before = [
            {"id": "old1", "type": "subtitle", "start": 0.0, "end": 4.0, "text": "old"},
        ]
        res = svc.apply_undo({"segments": before}, base_revision=svc._revision)
        assert res["success"]
        patch = res["data"]
        assert [s["id"] for s in patch["segments"]] == ["old1"]
        assert svc.active_timeline.transcript.segments[0].text == "old"

    def test_repeated_undo_keeps_monotonic_revision(self, svc: ProjectService) -> None:
        rev = _seed_segments(svc)
        snapshots = []
        for _ in range(3):
            snapshots.append([
                s.model_dump(mode="json")
                for s in svc.active_timeline.transcript.segments
            ])
            svc.update_transcript([
                {"id": f"s{len(snapshots)}x", "type": "subtitle",
                 "start": 20.0 + len(snapshots), "end": 25.0 + len(snapshots),
                 "text": f"gen{len(snapshots)}"},
            ])
            rev = svc._revision
        seen = []
        for snap in reversed(snapshots):
            res = svc.apply_undo({"segments": snap}, base_revision=rev)
            assert res["success"]
            rev = res["data"]["revision"]
            seen.append(rev)
        assert seen == sorted(seen) and len(set(seen)) == len(seen)


class TestStaleRejection:
    def test_stale_base_revision_rejected(self, svc: ProjectService) -> None:
        rev = _seed_segments(svc)
        stale = rev - 1  # simulate out-of-order frontend state
        res = svc.apply_undo({"segments": []}, base_revision=stale)
        assert res["success"] is False
        assert "stale" in res["error"].lower() or "过期" in res["error"]
        # revision untouched by the rejected call
        assert svc._revision == rev

    def test_future_base_revision_rejected(self, svc: ProjectService) -> None:
        rev = _seed_segments(svc)
        res = svc.apply_undo({"segments": []}, base_revision=rev + 5)
        assert res["success"] is False
        assert svc._revision == rev

    def test_current_base_revision_accepted(self, svc: ProjectService) -> None:
        rev = _seed_segments(svc)
        res = svc.apply_undo({"segments": []}, base_revision=rev)
        assert res["success"]


class TestCrossLayerAtomicity:
    def test_segments_and_edits_rollback_together(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        # capture pre-state of both layers
        before_segments = [
            s.model_dump(mode="json")
            for s in svc.active_timeline.transcript.segments
        ]
        res = svc.mark_segments(["s1"], status="confirmed", action="delete")
        assert res["success"]
        rev = res["data"]["revision"]
        assert len(svc.active_timeline.edits) >= 1

        # undo replaces BOTH layers atomically
        res = svc.apply_undo(
            {"segments": before_segments, "edits": []},
            base_revision=rev,
        )
        assert res["success"]
        patch = res["data"]
        assert patch["segments"][0]["id"] == "s1"
        assert patch["edits"] == []
        tl = svc.active_timeline
        assert [s.id for s in tl.transcript.segments] == ["s1", "s2"]
        assert tl.edits == []

    def test_invalid_layer_rejects_without_partial_apply(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        rev = svc._revision
        good = [s.model_dump(mode="json") for s in svc.active_timeline.transcript.segments]
        res = svc.apply_undo(
            {"segments": good, "edits": [{"not_a_field": True}]},
            base_revision=rev,
        )
        assert res["success"] is False
        # atomic: segments layer untouched
        assert [s.id for s in svc.active_timeline.transcript.segments] == ["s1", "s2"]
        assert svc._revision == rev


class TestValidation:
    def test_unknown_layer_rejected(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        res = svc.apply_undo({"bogus_layer": []}, base_revision=svc._revision)
        assert res["success"] is False

    def test_segments_require_list_of_dicts(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        res = svc.apply_undo({"segments": "nope"}, base_revision=svc._revision)
        assert res["success"] is False

    def test_segment_missing_required_field_rejected(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        res = svc.apply_undo(
            {"segments": [{"id": "x"}]}, base_revision=svc._revision,
        )
        assert res["success"] is False

    def test_empty_payload_rejected(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        res = svc.apply_undo({}, base_revision=svc._revision)
        assert res["success"] is False

    def test_no_project_open_rejected(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("core.project_service.get_projects_dir", lambda: tmp_path)
        svc = ProjectService()
        res = svc.apply_undo({"segments": []}, base_revision=0)
        assert res["success"] is False

    def test_segments_sort_invariant_after_undo(self, svc: ProjectService) -> None:
        _seed_segments(svc)
        # restore an unordered snapshot - invariant must re-sort it
        res = svc.apply_undo(
            {"segments": [
                {"id": "b", "type": "subtitle", "start": 20.0, "end": 25.0, "text": "b"},
                {"id": "a", "type": "subtitle", "start": 0.0, "end": 5.0, "text": "a"},
            ]},
            base_revision=svc._revision,
        )
        assert res["success"]
        ids = [s.id for s in svc.active_timeline.transcript.segments]
        assert ids == ["a", "b"]

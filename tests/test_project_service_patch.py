"""Patch-envelope contract tests for migrated ProjectService methods.

Validates the response shape changes introduced in v2.3.2 stage 2:
migrated write methods now return
``{"success": True, "data": ProjectPatch.model_dump(mode="json")}``
instead of the legacy full-Project dump.

These tests deliberately check the *envelope shape* and *revision*
semantics, not the underlying state mutation (those are covered by
``test_project_service.py``).
"""

from __future__ import annotations

import pytest

from core.models import SegmentType
from core.project_patch import apply_project_patch, is_stale_patch
from core.project_service import ProjectService


def _bootstrap_service(tmp_path, monkeypatch) -> ProjectService:
    """Create a ProjectService with one subtitle + one silence segment."""
    monkeypatch.setattr("core.project_service.get_projects_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "core.config.get_projects_dir", lambda: tmp_path, raising=False
    )
    svc = ProjectService()
    media = tmp_path / "video.mp4"
    media.write_bytes(b"stub")
    svc.create_project("patch-test", str(media), {"duration": 60.0})
    svc.update_transcript(
        [
            {"id": "seg-a", "type": "subtitle", "start": 1.0, "end": 5.0, "text": "alpha"},
            {"id": "seg-b", "type": "subtitle", "start": 6.0, "end": 10.0, "text": "beta"},
        ]
    )
    svc.add_silence_results([{"start": 5.0, "end": 6.0}])
    return svc


def _is_patch_envelope(result: dict) -> bool:
    """True when ``result`` carries a ProjectPatch instead of a full Project."""
    return (
        result.get("success") is True
        and isinstance(result.get("data"), dict)
        and "revision" in result["data"]
    )


@pytest.fixture
def svc(tmp_path, monkeypatch) -> ProjectService:
    return _bootstrap_service(tmp_path, monkeypatch)


class TestPatchEnvelopeShape:
    def test_update_edit_decision_returns_patch_envelope(self, svc: ProjectService) -> None:
        edit_id = svc.current.active_timeline.edits[0].id
        result = svc.update_edit_decision(edit_id, "confirmed")
        assert _is_patch_envelope(result)
        data = result["data"]
        assert data["revision"] == 1
        assert data["timeline_id"] == "default"
        assert data["edits"] is not None
        assert data["segments"] is None
        assert data["media"] is None
        assert data["full_project"] is None

    def test_update_edit_decisions_batch_returns_patch_envelope(self, svc: ProjectService) -> None:
        edit_id = svc.current.active_timeline.edits[0].id
        result = svc.update_edit_decisions_batch([edit_id], "rejected")
        assert _is_patch_envelope(result)
        assert result["data"]["edits"] is not None
        assert result["data"]["segments"] is None

    def test_mark_segments_returns_patch_envelope(self, svc: ProjectService) -> None:
        result = svc.mark_segments(["seg-a"], "delete")
        assert _is_patch_envelope(result)
        assert result["data"]["edits"] is not None
        assert result["data"]["segments"] is None

    def test_update_segment_returns_segments_patch(self, svc: ProjectService) -> None:
        result = svc.update_segment("seg-a", {"text": "new text"})
        assert _is_patch_envelope(result)
        data = result["data"]
        assert data["segments"] is not None
        assert data["edits"] is None  # subtitle edit does not cascade to silence edits

    def test_update_segment_text_returns_segments_patch(self, svc: ProjectService) -> None:
        result = svc.update_segment_text("seg-a", "patched text")
        assert _is_patch_envelope(result)
        assert result["data"]["segments"] is not None
        assert result["data"]["edits"] is None

    def test_update_segment_for_silence_time_change_emits_combined_patch(
        self, svc: ProjectService
    ) -> None:
        silence_seg = next(
            s
            for s in svc.current.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        )
        result = svc.update_segment(silence_seg.id, {"start": 5.5, "end": 5.8})
        assert _is_patch_envelope(result)
        data = result["data"]
        # Both layers must be present so the frontend re-renders atomically.
        assert data["segments"] is not None
        assert data["edits"] is not None


class TestRevisionSemantics:
    def test_revision_is_monotonic(self, svc: ProjectService) -> None:
        edit_id = svc.current.active_timeline.edits[0].id
        r1 = svc.update_edit_decision(edit_id, "confirmed")["data"]["revision"]
        r2 = svc.update_edit_decision(edit_id, "rejected")["data"]["revision"]
        r3 = svc.update_edit_decision(edit_id, "pending")["data"]["revision"]
        assert r1 < r2 < r3
        assert r1 == 1 and r3 == 3

    def test_revision_starts_at_1_for_first_write(self, svc: ProjectService) -> None:
        result = svc.update_segment("seg-a", {"text": "first write"})
        assert result["data"]["revision"] == 1

    def test_revision_advances_across_different_methods(self, svc: ProjectService) -> None:
        r1 = svc.update_segment("seg-a", {"text": "x"})["data"]["revision"]
        r2 = svc.mark_segments(["seg-b"], "delete")["data"]["revision"]
        r3 = svc.update_segment("seg-a", {"text": "y"})["data"]["revision"]
        assert r1 == 1 and r2 == 2 and r3 == 3

    def test_failed_write_does_not_advance_revision(self, svc: ProjectService) -> None:
        before = svc._revision
        result = svc.update_edit_decision("nonexistent-id", "confirmed")
        assert result["success"] is False
        assert svc._revision == before


class TestPatchReconstructsToServiceState:
    """End-to-end: applying the returned patch to a stale snapshot must
    reproduce the service's current state exactly."""

    def test_round_trip_after_update_edit_decision(
        self, svc: ProjectService
    ) -> None:
        from core.models import ProjectPatch

        snapshot = svc.current.model_copy(deep=True)
        edit_id = svc.current.active_timeline.edits[0].id
        result = svc.update_edit_decision(edit_id, "confirmed")

        patch = ProjectPatch.model_validate(result["data"])
        reconstructed = apply_project_patch(snapshot, patch)
        assert reconstructed.model_dump() == svc.current.model_dump()

    def test_round_trip_after_update_segment(
        self, svc: ProjectService
    ) -> None:
        from core.models import ProjectPatch

        snapshot = svc.current.model_copy(deep=True)
        result = svc.update_segment("seg-a", {"text": "round trip"})

        patch = ProjectPatch.model_validate(result["data"])
        reconstructed = apply_project_patch(snapshot, patch)
        assert reconstructed.model_dump() == svc.current.model_dump()

    def test_round_trip_after_silence_time_change_with_cascaded_edits(
        self, svc: ProjectService
    ) -> None:
        from core.models import ProjectPatch

        snapshot = svc.current.model_copy(deep=True)
        silence_seg = next(
            s
            for s in svc.current.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        )
        result = svc.update_segment(
            silence_seg.id, {"start": 5.2, "end": 5.9}
        )

        patch = ProjectPatch.model_validate(result["data"])
        reconstructed = apply_project_patch(snapshot, patch)
        assert reconstructed.model_dump() == svc.current.model_dump()

    def test_round_trip_after_mark_segments(
        self, svc: ProjectService
    ) -> None:
        from core.models import ProjectPatch

        snapshot = svc.current.model_copy(deep=True)
        result = svc.mark_segments(["seg-a", "seg-b"], "delete", "confirmed")

        patch = ProjectPatch.model_validate(result["data"])
        reconstructed = apply_project_patch(snapshot, patch)
        assert reconstructed.model_dump() == svc.current.model_dump()


class TestStalenessDefence:
    def test_concurrent_writes_produce_strictly_increasing_revisions(
        self, svc: ProjectService
    ) -> None:
        edit_id = svc.current.active_timeline.edits[0].id
        revisions = []
        for _ in range(5):
            r = svc.update_edit_decision(edit_id, "confirmed")
            revisions.append(r["data"]["revision"])
        # Apply staleness check against the last revision in the sequence
        last = revisions[-1]
        from core.models import ProjectPatch

        for older in revisions[:-1]:
            stale_patch = ProjectPatch(revision=older)
            assert is_stale_patch(stale_patch, last_seen_revision=last) is True

        fresh_patch = ProjectPatch(revision=last + 1)
        assert is_stale_patch(fresh_patch, last_seen_revision=last) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

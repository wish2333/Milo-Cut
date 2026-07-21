"""Unit tests for ProjectPatch schema and apply_project_patch.

Validates the contract documented in
``docs/2.3.0/2.3.2-stage1-evaluation-plan.md`` §4 阶段 2 and the
Oracle consultation: layer-replacement semantics, fallback priority,
revision-based staleness check.
"""

from __future__ import annotations

import pytest

from core.models import (
    AnalysisData,
    EditDecision,
    EditStatus,
    MediaInfo,
    Project,
    ProjectPatch,
    Segment,
    SegmentType,
    Timeline,
    TranscriptData,
)
from core.project_patch import (
    PatchApplicationError,
    apply_project_patch,
    is_stale_patch,
)
from tests.mocks import make_edit_decision, make_project, make_segment


@pytest.fixture
def base_project() -> Project:
    seg_a = make_segment(id="seg-a", start=0.0, end=2.0, text="alpha")
    seg_b = make_segment(id="seg-b", start=2.0, end=4.0, text="beta")
    edit_x = make_edit_decision(
        id="edit-x", start=0.0, end=1.0, status=EditStatus.PENDING
    )
    return make_project(segments=[seg_a, seg_b], edits=[edit_x])


class TestSchemaContract:
    def test_minimal_patch_requires_only_revision(self) -> None:
        patch = ProjectPatch(revision=1)
        assert patch.revision == 1
        assert patch.segments is None
        assert patch.full_project is None

    def test_full_project_fallback_flag(self) -> None:
        project = make_project()
        patch_with_full = ProjectPatch(revision=1, full_project=project)
        patch_without = ProjectPatch(revision=1, segments=[make_segment()])
        assert patch_with_full.is_full_project_fallback() is True
        assert patch_without.is_full_project_fallback() is False

    def test_patch_is_frozen(self) -> None:
        patch = ProjectPatch(revision=1)
        with pytest.raises(Exception):
            patch.revision = 2  # type: ignore[misc]


class TestApplyPatch:
    def test_full_project_fallback_short_circuits(self, base_project: Project) -> None:
        replacement = make_project(
            segments=[make_segment(id="only-seg", text="replaced")]
        )
        patch = ProjectPatch(revision=1, full_project=replacement)

        result = apply_project_patch(base_project, patch)
        assert result == replacement
        # Identity check: full_project replacement returns the same object
        assert result is replacement

    def test_segments_layer_replaces_active_timeline_segments(
        self, base_project: Project
    ) -> None:
        new_segs = [
            make_segment(id="seg-c", start=0.0, end=1.0, text="gamma"),
            make_segment(id="seg-d", start=1.0, end=2.0, text="delta"),
        ]
        patch = ProjectPatch(revision=1, segments=new_segs)

        result = apply_project_patch(base_project, patch)
        active = result.active_timeline
        assert [s.id for s in active.transcript.segments] == ["seg-c", "seg-d"]
        # Edits preserved (untouched layer)
        assert [e.id for e in active.edits] == ["edit-x"]

    def test_edits_layer_replaces_active_timeline_edits(
        self, base_project: Project
    ) -> None:
        new_edits = [
            make_edit_decision(
                id="edit-y", start=5.0, end=6.0, status=EditStatus.CONFIRMED
            )
        ]
        patch = ProjectPatch(revision=1, edits=new_edits)

        result = apply_project_patch(base_project, patch)
        active = result.active_timeline
        assert [e.id for e in active.edits] == ["edit-y"]
        # Segments preserved (untouched layer)
        assert [s.id for s in active.transcript.segments] == ["seg-a", "seg-b"]

    def test_combined_segments_and_edits_in_single_patch(
        self, base_project: Project
    ) -> None:
        new_segs = [make_segment(id="seg-only", start=0.0, end=10.0)]
        new_edits = [
            make_edit_decision(id="edit-only", start=0.0, end=5.0)
        ]
        patch = ProjectPatch(revision=1, segments=new_segs, edits=new_edits)

        result = apply_project_patch(base_project, patch)
        active = result.active_timeline
        assert [s.id for s in active.transcript.segments] == ["seg-only"]
        assert [e.id for e in active.edits] == ["edit-only"]

    def test_none_layers_keep_existing_reference(self, base_project: Project) -> None:
        original_active = base_project.active_timeline
        patch = ProjectPatch(revision=1)  # no layers

        result = apply_project_patch(base_project, patch)
        # Same timeline object reused (no replacement) when no layers changed
        new_active = result.active_timeline
        assert new_active.transcript.segments is original_active.transcript.segments
        assert new_active.edits is original_active.edits

    def test_media_layer_replaces_project_media(self, base_project: Project) -> None:
        new_media = MediaInfo(
            path="/tmp/new.mp4", duration=120.0, width=3840, height=2160
        )
        patch = ProjectPatch(revision=1, media=new_media)

        result = apply_project_patch(base_project, patch)
        assert result.media is new_media
        # Timeline data untouched
        assert len(result.active_timeline.transcript.segments) == 2

    def test_analysis_layer_replaces_active_timeline_analysis(
        self, base_project: Project
    ) -> None:
        new_analysis = AnalysisData(last_run="2026-07-21T00:00:00")
        patch = ProjectPatch(revision=1, analysis=new_analysis)

        result = apply_project_patch(base_project, patch)
        assert result.active_timeline.analysis is new_analysis

    def test_active_timeline_id_override(self, base_project: Project) -> None:
        second_timeline = Timeline(
            id="second",
            label="Second",
            transcript=TranscriptData(
                segments=[make_segment(id="seg-second", start=0.0, end=1.0)]
            ),
        )
        project = base_project.model_copy(
            update={
                "timelines": [*base_project.timelines, second_timeline],
                "active_timeline_id": "default",
            }
        )
        patch = ProjectPatch(revision=1, active_timeline_id="second")

        result = apply_project_patch(project, patch)
        assert result.active_timeline_id == "second"

    def test_explicit_timeline_id_targets_non_active_timeline(
        self, base_project: Project
    ) -> None:
        second_segs = [make_segment(id="seg-second", start=0.0, end=1.0)]
        second_timeline = Timeline(
            id="second",
            label="Second",
            transcript=TranscriptData(segments=second_segs),
        )
        project = base_project.model_copy(
            update={"timelines": [*base_project.timelines, second_timeline]}
        )
        new_segs = [make_segment(id="seg-patched", start=0.0, end=5.0)]
        patch = ProjectPatch(
            revision=1, timeline_id="second", segments=new_segs
        )

        result = apply_project_patch(project, patch)
        # Active timeline still "default" with original segments
        assert result.active_timeline_id == "default"
        assert [s.id for s in result.active_timeline.transcript.segments] == [
            "seg-a",
            "seg-b",
        ]
        # Second timeline patched
        second = result.get_timeline("second")
        assert second is not None
        assert [s.id for s in second.transcript.segments] == ["seg-patched"]

    def test_unknown_timeline_id_raises(self, base_project: Project) -> None:
        patch = ProjectPatch(
            revision=1,
            timeline_id="does-not-exist",
            segments=[make_segment()],
        )
        with pytest.raises(PatchApplicationError) as exc_info:
            apply_project_patch(base_project, patch)
        assert "does-not-exist" in str(exc_info.value)

    def test_no_layer_updates_with_unknown_timeline_id_is_silent(
        self, base_project: Project
    ) -> None:
        # When the patch only carries project-level updates (media /
        # active_timeline_id) and no layer updates, an arbitrary
        # timeline_id value is allowed (and ignored).
        patch = ProjectPatch(
            revision=1,
            timeline_id="does-not-exist",
            media=MediaInfo(path="/tmp/x.mp4"),
        )
        result = apply_project_patch(base_project, patch)
        assert result.media is not None
        assert result.media.path == "/tmp/x.mp4"

    def test_original_project_not_mutated(self, base_project: Project) -> None:
        original_segments = list(base_project.active_timeline.transcript.segments)
        patch = ProjectPatch(
            revision=1, segments=[make_segment(id="brand-new", start=0.0, end=1.0)]
        )

        apply_project_patch(base_project, patch)
        # base_project still holds its original segments
        assert [
            s.id for s in base_project.active_timeline.transcript.segments
        ] == [s.id for s in original_segments]


class TestStalenessCheck:
    def test_first_patch_is_always_fresh(self) -> None:
        patch = ProjectPatch(revision=1)
        assert is_stale_patch(patch, last_seen_revision=0) is False

    def test_equal_revision_is_stale(self) -> None:
        patch = ProjectPatch(revision=5)
        assert is_stale_patch(patch, last_seen_revision=5) is True

    def test_lower_revision_is_stale(self) -> None:
        patch = ProjectPatch(revision=3)
        assert is_stale_patch(patch, last_seen_revision=5) is True

    def test_higher_revision_is_fresh(self) -> None:
        patch = ProjectPatch(revision=10)
        assert is_stale_patch(patch, last_seen_revision=5) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

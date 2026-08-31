"""Unit tests for the synthetic project generator.

Validates the contract documented in
``docs/2.3.0/2.3.2-stage1-evaluation-plan.md`` §4 阶段 0:
deterministic output, configurable size, realistic distribution.
"""

from __future__ import annotations

import pytest

from core.models import Project, SegmentType
from tests.fixtures.generate_synthetic_project import (
    DEFAULT_EDIT_COUNT,
    DEFAULT_SEGMENT_COUNT,
    EDIT_SOURCE_WEIGHTS,
    SILENCE_RATIO,
    generate_synthetic_project,
)


class TestDeterminism:
    def test_same_seed_produces_identical_projects(self) -> None:
        p1 = generate_synthetic_project(seed=42)
        p2 = generate_synthetic_project(seed=42)
        assert p1 == p2
        assert p1.model_dump_json() == p2.model_dump_json()

    def test_different_seeds_produce_different_projects(self) -> None:
        p1 = generate_synthetic_project(seed=1)
        p2 = generate_synthetic_project(seed=2)
        assert p1 != p2

    def test_default_seed_matches_eval_plan_target(self) -> None:
        p = generate_synthetic_project()
        assert len(p.active_timeline.transcript.segments) == DEFAULT_SEGMENT_COUNT
        assert len(p.active_timeline.edits) == DEFAULT_EDIT_COUNT


class TestSizeAndDistribution:
    def test_segment_count_matches_request(self) -> None:
        for size in (10, 100, 500, 1167):
            p = generate_synthetic_project(segment_count=size, edit_count=0)
            assert len(p.active_timeline.transcript.segments) == size

    def test_edit_count_matches_request(self) -> None:
        p = generate_synthetic_project(segment_count=50, edit_count=37)
        assert len(p.active_timeline.edits) == 37

    def test_silence_ratio_close_to_target(self) -> None:
        p = generate_synthetic_project(segment_count=1000, edit_count=0)
        silence = sum(
            1
            for s in p.active_timeline.transcript.segments
            if s.type == SegmentType.SILENCE
        )
        actual_ratio = silence / 1000
        assert abs(actual_ratio - SILENCE_RATIO) < 0.02

    def test_segments_are_time_sorted(self) -> None:
        p = generate_synthetic_project(segment_count=200, edit_count=0)
        starts = [s.start for s in p.active_timeline.transcript.segments]
        assert starts == sorted(starts)

    def test_all_edit_sources_are_known(self) -> None:
        p = generate_synthetic_project(segment_count=100, edit_count=50)
        known = {src for src, _ in EDIT_SOURCE_WEIGHTS}
        actual = {e.source for e in p.active_timeline.edits}
        assert actual.issubset(known)

    def test_edit_target_ids_reference_real_segments(self) -> None:
        p = generate_synthetic_project(segment_count=100, edit_count=50)
        seg_ids = {s.id for s in p.active_timeline.transcript.segments}
        for edit in p.active_timeline.edits:
            assert edit.target_id in seg_ids


class TestModelContract:
    def test_generated_project_passes_validation(self) -> None:
        p = generate_synthetic_project(segment_count=50, edit_count=10)
        assert isinstance(p, Project)
        assert p.schema_version == 2
        assert len(p.timelines) == 1
        assert p.active_timeline_id == "default"

    def test_media_duration_accommodates_all_segments(self) -> None:
        p = generate_synthetic_project(segment_count=2000, edit_count=0)
        last_end = p.active_timeline.transcript.segments[-1].end
        assert p.media.duration > last_end

    def test_small_smoke_run_is_fast(self) -> None:
        # Sanity: small generation should complete in well under 1 second.
        import time

        t0 = time.perf_counter()
        generate_synthetic_project(segment_count=50, edit_count=20)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert elapsed_ms < 1000, f"generation too slow: {elapsed_ms:.1f}ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

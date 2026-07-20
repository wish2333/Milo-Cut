"""Unit tests for the backend benchmark harness.

Validates that the benchmark produces well-formed percentile stats and
that the harness itself doesn't drift silently between invocations.
"""

from __future__ import annotations

import pytest

from tests.perf.backend_benchmark import _percentiles, run_benchmark


class TestPercentiles:
    def test_empty_samples_return_zeros(self) -> None:
        stats = _percentiles([])
        assert stats["p50"] == 0.0
        assert stats["p95"] == 0.0
        assert stats["max"] == 0.0

    def test_single_sample(self) -> None:
        stats = _percentiles([5.0])
        assert stats["p50"] == 5.0
        assert stats["p95"] == 5.0
        assert stats["max"] == 5.0

    def test_known_sequence(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        stats = _percentiles(samples)
        assert stats["min"] == 1.0
        assert stats["max"] == 10.0
        assert stats["mean"] == 5.5
        # 10 samples (0-indexed 0..9), _pct(50) -> idx = round(0.50 * 9) = 4
        # (banker's rounding), samples[4] = 5.0
        assert stats["p50"] == 5.0


class TestBenchmarkRun:
    @pytest.fixture(scope="class")
    def small_summary(self):
        return run_benchmark(runs=3, segment_count=50, edit_count=10)

    def test_metadata_fields_present(self, small_summary) -> None:
        meta = small_summary["metadata"]
        assert meta["runs"] == 3
        assert meta["segment_count"] == 50
        assert meta["edit_count"] == 10
        assert "python_version" in meta
        assert "timestamp" in meta

    def test_required_operations_measured(self, small_summary) -> None:
        results = small_summary["results"]
        required = {
            "generate_synthetic_project",
            "project_model_dump",
            "project_model_dump_json",
            "project_payload_size",
            "update_edit_decision",
            "update_segment",
            "mark_segments_single",
            "mark_segments_batch_10",
        }
        assert required.issubset(results.keys())

    def test_stats_have_positive_values(self, small_summary) -> None:
        results = small_summary["results"]
        for op_name, op_data in results.items():
            if "stats" not in op_data:
                continue
            stats = op_data["stats"]
            assert stats["max"] >= stats["p50"] >= 0.0, (
                f"{op_name}: max={stats['max']} p50={stats['p50']}"
            )

    def test_payload_size_matches_actual_dump(self, small_summary) -> None:
        from tests.fixtures.generate_synthetic_project import (
            generate_synthetic_project,
        )

        project = generate_synthetic_project(
            segment_count=50, edit_count=10, seed=42
        )
        actual_bytes = len(project.model_dump_json().encode("utf-8"))
        measured_bytes = small_summary["results"]["project_payload_size"]["value_bytes"]
        assert measured_bytes == actual_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

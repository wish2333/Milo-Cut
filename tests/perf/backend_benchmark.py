"""Backend performance benchmark for v2.3.2 baselines.

Measures the cost of operations that the evaluation plan flags as hot
paths (``docs/2.3.0/2.3.2-stage1-evaluation-plan.md`` §5):

- ``Project.model_dump()`` -- wholesale serialization that dominates every
  write response envelope.
- ``Project.model_dump_json()`` -- wire-format equivalent.
- ``ProjectService.update_edit_decision`` / ``update_segment`` /
  ``mark_segments`` -- the write paths that return full Project today and
  will return ProjectPatch after 阶段 2.

Outputs a JSON document with p50/p95/p99/max timings so subsequent stages
can compare regressions quantitatively rather than by static estimation.

CLI usage::

    uv run python -m tests.perf.backend_benchmark \\
        --runs 30 --output tests/perf/results/baseline_stage0.json

Library usage::

    from tests.perf.backend_benchmark import run_benchmark
    summary = run_benchmark(runs=30)
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from core.models import Project
from core.project_service import ProjectService
from tests.fixtures.generate_synthetic_project import (
    DEFAULT_EDIT_COUNT,
    DEFAULT_SEGMENT_COUNT,
    DEFAULT_SEED,
    generate_synthetic_project,
)


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    """Return p50/p95/p99/max/min/mean in milliseconds."""
    if not samples_ms:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "min": 0.0, "mean": 0.0}
    s = sorted(samples_ms)
    n = len(s)

    def _pct(p: float) -> float:
        idx = max(0, min(n - 1, int(round((p / 100.0) * (n - 1)))))
        return round(s[idx], 3)

    return {
        "p50": _pct(50),
        "p95": _pct(95),
        "p99": _pct(99),
        "max": round(s[-1], 3),
        "min": round(s[0], 3),
        "mean": round(statistics.fmean(s), 3),
    }


def _measure(fn: Callable[[], object], runs: int) -> list[float]:
    """Run ``fn`` ``runs`` times, returning per-run durations in ms."""
    samples: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        samples.append(round(elapsed_ms, 3))
    return samples


def _prepare_service(project: Project) -> ProjectService:
    """Build a ProjectService with ``project`` loaded as current."""
    svc = ProjectService()
    svc._current = project
    return svc


def run_benchmark(
    *,
    runs: int = 30,
    segment_count: int = DEFAULT_SEGMENT_COUNT,
    edit_count: int = DEFAULT_EDIT_COUNT,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Run the full benchmark suite and return a structured summary.

    Each measured operation runs ``runs`` times against a freshly
    regenerated project (the project is rebuilt once per outer loop to
    avoid state drift between operations on the same instance).
    """
    summary: dict = {
        "metadata": {
            "runs": runs,
            "segment_count": segment_count,
            "edit_count": edit_count,
            "seed": seed,
            "python_version": sys.version.split()[0],
            "timestamp": datetime.now().isoformat(),
        },
        "results": {},
    }

    # --- 1. Project construction cost -------------------------------
    build_samples = _measure(
        lambda: generate_synthetic_project(
            segment_count=segment_count, edit_count=edit_count, seed=seed
        ),
        runs=min(runs, 10),  # construction is cheap; 10 runs is enough
    )
    summary["results"]["generate_synthetic_project"] = {
        "samples_ms": build_samples,
        "stats": _percentiles(build_samples),
        "unit": "ms",
        "note": "Project construction cost; not a hot path, sanity check only.",
    }

    # Build one canonical project for all subsequent measurements.
    project = generate_synthetic_project(
        segment_count=segment_count, edit_count=edit_count, seed=seed
    )

    # --- 2. Serialization -------------------------------------------
    dump_samples = _measure(lambda: project.model_dump(), runs)
    summary["results"]["project_model_dump"] = {
        "samples_ms": dump_samples,
        "stats": _percentiles(dump_samples),
        "unit": "ms",
        "note": "Full Project.model_dump() -- dominates every write response today.",
    }

    dump_json_samples = _measure(lambda: project.model_dump_json(), runs)
    summary["results"]["project_model_dump_json"] = {
        "samples_ms": dump_json_samples,
        "stats": _percentiles(dump_json_samples),
        "unit": "ms",
        "note": "Full Project.model_dump_json() -- wire-format serialization.",
    }

    payload_size_bytes = len(project.model_dump_json().encode("utf-8"))
    summary["results"]["project_payload_size"] = {
        "value_bytes": payload_size_bytes,
        "value_kb": round(payload_size_bytes / 1024.0, 2),
        "unit": "bytes",
        "note": "Serialized Project size; the volume of data the bridge ships per write.",
    }

    # --- 3. Write operations (each builds a fresh service) -----------
    target_edit_id = project.active_timeline.edits[0].id if project.active_timeline.edits else None
    target_segment_id = (
        project.active_timeline.transcript.segments[0].id
        if project.active_timeline.transcript.segments
        else None
    )

    if target_edit_id:
        samples: list[float] = []
        for _ in range(runs):
            svc = _prepare_service(project)
            t0 = time.perf_counter()
            svc.update_edit_decision(target_edit_id, "confirmed")
            samples.append(round((time.perf_counter() - t0) * 1000.0, 3))
        summary["results"]["update_edit_decision"] = {
            "samples_ms": samples,
            "stats": _percentiles(samples),
            "unit": "ms",
            "note": "Includes the full model_dump() in the response envelope.",
        }

    if target_segment_id:
        samples = []
        for _ in range(runs):
            svc = _prepare_service(project)
            t0 = time.perf_counter()
            svc.update_segment(target_segment_id, {"text": "benchmark patch text"})
            samples.append(round((time.perf_counter() - t0) * 1000.0, 3))
        summary["results"]["update_segment"] = {
            "samples_ms": samples,
            "stats": _percentiles(samples),
            "unit": "ms",
            "note": "Includes the full model_dump() in the response envelope.",
        }

    if target_segment_id:
        samples = []
        for _ in range(runs):
            svc = _prepare_service(project)
            t0 = time.perf_counter()
            svc.mark_segments([target_segment_id], "delete", "confirmed")
            samples.append(round((time.perf_counter() - t0) * 1000.0, 3))
        summary["results"]["mark_segments_single"] = {
            "samples_ms": samples,
            "stats": _percentiles(samples),
            "unit": "ms",
            "note": "Single-id mark_segments; cost dominated by EditDecision rebuild.",
        }

    # mark_segments with realistic batch size (10 ids)
    if len(project.active_timeline.transcript.segments) >= 10:
        batch_ids = [
            s.id for s in project.active_timeline.transcript.segments[:10]
        ]
        samples = []
        for _ in range(runs):
            svc = _prepare_service(project)
            t0 = time.perf_counter()
            svc.mark_segments(batch_ids, "delete", "confirmed")
            samples.append(round((time.perf_counter() - t0) * 1000.0, 3))
        summary["results"]["mark_segments_batch_10"] = {
            "samples_ms": samples,
            "stats": _percentiles(samples),
            "unit": "ms",
            "note": "10-id mark_segments batch; reflects bulk operation cost.",
        }

    return summary


def _format_summary(summary: dict) -> str:
    """Render the summary as a human-readable table for CLI output."""
    lines = []
    meta = summary["metadata"]
    lines.append(
        f"# Benchmark (segments={meta['segment_count']} "
        f"edits={meta['edit_count']} seed={meta['seed']} runs={meta['runs']})"
    )
    lines.append("")
    lines.append(
        f"{'operation':<32} {'p50 (ms)':>12} {'p95 (ms)':>12} "
        f"{'p99 (ms)':>12} {'max (ms)':>12}"
    )
    lines.append("-" * 84)
    for op_name, op_data in summary["results"].items():
        if "stats" not in op_data:
            continue
        stats = op_data["stats"]
        lines.append(
            f"{op_name:<32} {stats['p50']:>12.3f} {stats['p95']:>12.3f} "
            f"{stats['p99']:>12.3f} {stats['max']:>12.3f}"
        )
    if "project_payload_size" in summary["results"]:
        size = summary["results"]["project_payload_size"]
        lines.append("")
        lines.append(
            f"# Serialized Project size: {size['value_kb']:.2f} KB ({size['value_bytes']} bytes)"
        )
    return "\n".join(lines)


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the v2.3.2 backend performance benchmark."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=30,
        help="Number of iterations per operation (default 30).",
    )
    parser.add_argument(
        "--segments",
        type=int,
        default=DEFAULT_SEGMENT_COUNT,
        help=f"Synthetic segment count (default {DEFAULT_SEGMENT_COUNT}).",
    )
    parser.add_argument(
        "--edits",
        type=int,
        default=DEFAULT_EDIT_COUNT,
        help=f"Synthetic edit count (default {DEFAULT_EDIT_COUNT}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed (default {DEFAULT_SEED}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path (parent directories are created).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the human-readable table; emit JSON only.",
    )
    args = parser.parse_args()

    summary = run_benchmark(
        runs=args.runs,
        segment_count=args.segments,
        edit_count=args.edits,
        seed=args.seed,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if not args.quiet:
            print(f"# wrote {args.output}", file=sys.stderr)

    if not args.quiet:
        print(_format_summary(summary))


if __name__ == "__main__":
    _main()

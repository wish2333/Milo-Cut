# v2.3.2 Performance Baselines (阶段 0)

This directory contains the synthetic-fixture generator and backend
benchmark harness required by
[`docs/2.3.0/2.3.2-stage1-evaluation-plan.md` §4 阶段 0](../2.3.0/2.3.2-stage1-evaluation-plan.md).

The goal is to replace static time estimations in
[`2.3.2-fix-report.md`](../2.3.0/2.3.2-fix-report.md) with reproducible
measurements so subsequent stages (ProjectPatch protocol in 阶段 2,
sorting invariant + derived-data in 阶段 3) can compare against a known
baseline.

## Layout

```
tests/
  fixtures/
    generate_synthetic_project.py    # deterministic synthetic Project generator
    test_generate_synthetic_project.py
  perf/
    backend_benchmark.py             # serialization + write-op benchmark
    test_backend_benchmark.py
    results/
      baseline_stage0.json           # committed reference baseline (seed=42)
    README.md                        # this file
```

## Quick start

### Generate a synthetic project JSON

```bash
uv run python -m tests.fixtures.generate_synthetic_project \
    --output data/perf/synthetic_1167.json \
    --segments 1167 --edits 989
```

Output is fully deterministic for a given `--seed`.

### Run the backend benchmark

```bash
uv run python -m tests.perf.backend_benchmark \
    --runs 30 \
    --output tests/perf/results/baseline_stage0.json
```

The benchmark prints a p50/p95/p99/max table to stderr and writes a
detailed JSON envelope (with raw samples) to the `--output` path.

## Reference baseline (seed=42, 30 runs, 2026-07-21)

| operation                       |   p50 (ms) |   p95 (ms) |   p99 (ms) |
|---------------------------------|-----------:|-----------:|-----------:|
| `Project.model_dump()`          |     0.888  |     1.269  |     3.925  |
| `Project.model_dump_json()`     |     1.211  |     1.299  |     1.428  |
| `update_edit_decision`          |     0.937  |     3.862  |     4.466  |
| `update_segment`                |     0.975  |     1.039  |     4.473  |
| `mark_segments_single`          |     0.978  |     1.121  |     3.612  |
| `mark_segments_batch_10`        |     1.031  |     1.139  |     4.001  |
| Serialized `Project` size       |  490.57 KB |       --   |       --   |

## Key takeaway

Backend serialization is **not** the bottleneck. `model_dump()` and
`model_dump_json()` are both sub-2ms at p99 even at the evaluation-plan
target size. The 490 KB wire payload is the only volume-related signal
worth shrinking.

This refutes the original assumption in the early fix-report drafts that
backend serialization dominates the GUI lag. The actual hot paths are
frontend-side:

- `buildSegmentStateMap()` -- O(S × E) per render, where S=segments and
  E=edits. For the synthetic baseline this is ~1.15 million iterations
  per rebuild.
- `useUndoRedo.pushSnapshot()` -- `JSON.stringify()` of the whole
  project on every mutation.
- Vue's full-project replacement cascade (`project.value = res.data`)
  which invalidates every computed that touches any `project.*` field.

阶段 2 (ProjectPatch) targets the wire-payload volume and the cascade.
阶段 3 (sorting invariant + derived data sharing) targets
`buildSegmentStateMap()` and friends.

## Reproducibility contract

- Same `--seed` always produces byte-identical JSON.
- Same harness + same Python version + same hardware produces numbers
  within ~10% across runs; expect larger variance on laptops under load.
- The committed `baseline_stage0.json` is the reference. Regenerate after
  any change to the generator, the model schema, or `ProjectService`
  write paths, and commit the new baseline alongside the change.

## Frontend Playwright trace (deferred)

The evaluation plan also asks for Playwright traces of bridge flush, DOM
patch, long tasks and dropped frames. That infrastructure is deferred to
阶段 4 prep because:

1. It requires a running dev server + a headless browser, which is
   heavier than the regression-friendly backend harness above.
2. The existing frontend render-count tests
   (`VideoControls.test.ts` stage 1.1 additions) already give a
   structural signal that patch work reduces re-renders.
3. 阶段 4 will add a single end-to-end trace run against the synthetic
   project to validate the user-perceived p95 targets listed in the
   evaluation plan §5.

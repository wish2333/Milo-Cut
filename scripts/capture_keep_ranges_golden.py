#!/usr/bin/env python3
"""Capture the golden baseline for ProjectService.generate_subtitle_keep_ranges.

P3-1 deliverable (PLAN Phase 3 / SPEC M4-4 zero-regression criterion, hard
prerequisite = M0-3 constraint 1): the golden baseline MUST be captured from a
pristine v3.0.3 worktree BEFORE any change touches generate_subtitle_keep_ranges
(v3.0.3 anchor project_service.py:2560-2661). Capturing after the change would
bake the change itself into the "baseline" and void the byte-for-byte
comparison that P3-9 relies on.

This module is the single source of truth shared by capture and comparison:

- the fixed 30-segment set (deterministic, no randomness);
- the padding scan tiers (0.0 / 0.2 / 0.5 / 1.0 -- parameter name ``padding``);
- the stable serialization (json.dumps(sort_keys=True, ensure_ascii=False,
  indent=2)) applied to the returned edits dump.

tests/test_keep_ranges_golden.py imports this module (repo-root/scripts on
sys.path) and calls build_capture_results() so the capture run and the
comparison test always share one code path.

Capture usage (inside the v3.0.3 worktree, output back into the dev repo):

    cd /tmp/milo-golden-v303 && uv run --no-sync python \
        scripts/capture_keep_ranges_golden.py \
        --output <dev-repo>/tests/fixtures/golden_keep_ranges_v3.0.3.json \
        --capture-mode "worktree-primary"

Fallback when uv cannot provide an environment inside the worktree (run from
the dev repo, main-repo venv + worktree code first via PYTHONPATH):

    PYTHONPATH=/tmp/milo-golden-v303 uv run --no-sync python \
        scripts/capture_keep_ranges_golden.py --output ... --capture-mode "pythonpath-fallback"

Both modes are verified at runtime: main() asserts that the imported
core.project_service comes from the milo-golden-v303 worktree and that the
git HEAD of that origin repo is exactly the v3.0.3 commit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- baseline identity (asserted at capture time, recorded in golden meta) ---
BASELINE_TAG = "v3.0.3"
BASELINE_COMMIT_FULL = "55c68da5e273ea9df6b7994f49ff86cf4e3934a1"
WORKTREE_MARKER = "milo-golden-v303"

GOLDEN_BASENAME = "golden_keep_ranges_v3.0.3.json"

# Media info handed to create_project (generate_subtitle_keep_ranges derives
# the total duration from segments, not from media; value kept >= segment span).
MEDIA_DURATION = 90.0

# Padding scan tiers -- the only function parameter (signature:
# generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict).
PADDING_TIERS: list[float] = [0.0, 0.2, 0.5, 1.0]

# Fixed 30-segment set: (id, start, end, text). Deterministic, hand-authored,
# no randomness. Text never influences the computation but is fixed anyway so
# the segment set is fully reconstructible from the golden meta alone.
#
# Shape coverage (gap = start - previous end; merge rule is gap <= 2*padding,
# so the tiers 0.0/0.2/0.5/1.0 give merge thresholds 0.0/0.4/1.0/2.0):
#   - consecutive segments (gap 0.0): #2 #3 #20 #25 #26
#   - gaps below the smallest nonzero tier: 0.1 (#4 #17 #18)
#   - gaps straddling every merge threshold:
#     0.4 (#5) / 0.5 (#6, #12-#16) / 0.6 (#22) / 0.8 (#7 #19) / 1.0 (#8)
#     1.1 (#23) / 1.2 (#24) / 1.5 (#9 #27) / 2.0 (#10 #21 #29 #30)
#     2.5 (#28, splits at every tier) / 4.0 (#11, splits at every tier)
#   - equal-length runs: #11-#16 six 2.0s with constant 0.5 gap; #1-#2 2.0s
#   - varied lengths: 0.2 (#18) 0.3 (#17 #29) 0.4 (#4 #20) 1.0 (#8) 1.5 (#3)
#     1.9 (#23) 2.2 (#10) 2.4 (#22) 2.6 (#21) 3.2 (#28) 3.8 (#26) 4.0 (#19 #25)
#     4.5 (#30)
#   - first segment starts at 1.0 (leading delete range for padding < 1.0
#     tiers; no leading range at padding = 1.0)
#   - final segment ends at 86.5 = total duration (no trailing delete range
#     with a subtitle-only segment set -- that is the documented v3.0.3 shape)
FIXED_SEGMENTS: list[tuple[str, float, float, str]] = [
    ("gseg-0001", 1.0, 3.0, "golden 固定段 01"),
    ("gseg-0002", 3.0, 5.0, "golden 固定段 02"),
    ("gseg-0003", 5.0, 6.5, "golden 固定段 03"),
    ("gseg-0004", 6.6, 7.0, "golden 固定段 04"),
    ("gseg-0005", 7.4, 9.0, "golden 固定段 05"),
    ("gseg-0006", 9.5, 11.5, "golden 固定段 06"),
    ("gseg-0007", 12.3, 14.3, "golden 固定段 07"),
    ("gseg-0008", 15.3, 16.3, "golden 固定段 08"),
    ("gseg-0009", 17.8, 19.8, "golden 固定段 09"),
    ("gseg-0010", 21.8, 24.0, "golden 固定段 10"),
    ("gseg-0011", 28.0, 30.0, "golden 固定段 11"),
    ("gseg-0012", 30.5, 32.5, "golden 固定段 12"),
    ("gseg-0013", 33.0, 35.0, "golden 固定段 13"),
    ("gseg-0014", 35.5, 37.5, "golden 固定段 14"),
    ("gseg-0015", 38.0, 40.0, "golden 固定段 15"),
    ("gseg-0016", 40.5, 42.5, "golden 固定段 16"),
    ("gseg-0017", 42.6, 42.9, "golden 固定段 17"),
    ("gseg-0018", 43.0, 43.2, "golden 固定段 18"),
    ("gseg-0019", 44.0, 48.0, "golden 固定段 19"),
    ("gseg-0020", 48.0, 48.4, "golden 固定段 20"),
    ("gseg-0021", 50.4, 53.0, "golden 固定段 21"),
    ("gseg-0022", 53.6, 56.0, "golden 固定段 22"),
    ("gseg-0023", 57.1, 59.0, "golden 固定段 23"),
    ("gseg-0024", 60.2, 61.0, "golden 固定段 24"),
    ("gseg-0025", 61.0, 65.0, "golden 固定段 25"),
    ("gseg-0026", 65.0, 68.8, "golden 固定段 26"),
    ("gseg-0027", 70.3, 72.0, "golden 固定段 27"),
    ("gseg-0028", 74.5, 77.7, "golden 固定段 28"),
    ("gseg-0029", 79.7, 80.0, "golden 固定段 29"),
    ("gseg-0030", 82.0, 86.5, "golden 固定段 30"),
]

SEGMENT_SHAPE_NOTES = [
    "consecutive zero-gap run: gseg-0002/0003, gseg-0020 after 0019, gseg-0025/0026",
    "gaps below smallest nonzero tier: 0.1s (gseg-0004/0017/0018)",
    "gaps straddling every merge threshold 2*padding in {0.0, 0.4, 1.0, 2.0}:"
    " 0.4/0.5/0.6/0.8/1.0/1.1/1.2/1.5/2.0/2.5/4.0",
    "equal-length run: gseg-0011..0016 (six 2.0s, constant 0.5 gap)",
    "varied lengths: 0.2 .. 4.5 (see module docstring)",
    "first segment starts at 1.0 (leading delete range exercised for padding < 1.0)",
    "final segment ends at 86.5 = total duration (subtitle-only set: no trailing range)",
]


def _bootstrap_syspath() -> None:
    """Make the core/ next to this script's repo importable -- unless an
    explicit PYTHONPATH entry already provides a core package (fallback mode
    keeps the v3.0.3 worktree code first, so it must keep priority)."""
    if importlib.util.find_spec("core") is None:
        sys.path.insert(0, str(REPO_ROOT))


def fixed_transcript_dicts() -> list[dict]:
    """The fixed segment set as update_transcript payloads."""
    return [
        {"id": seg_id, "type": "subtitle", "start": start, "end": end, "text": text}
        for seg_id, start, end, text in FIXED_SEGMENTS
    ]


def _make_isolated_service(tmp_dir: Path):
    """Real ProjectService against an isolated tmp data dir.

    Mirrors the service-level construction used by the existing tests
    (tests/test_project_service.py::_create_service): patch core.paths data-dir
    helpers, then build the service. No monkeypatch needed outside pytest.
    """
    import core.paths as paths_mod

    paths_mod.get_projects_dir = lambda: tmp_dir / "projects"  # type: ignore[assignment]
    paths_mod.get_data_dir = lambda: tmp_dir  # type: ignore[assignment]

    from core.project_service import ProjectService

    return ProjectService()


def run_one_tier(padding: float) -> dict:
    """Fresh project + fixed transcript + generate_subtitle_keep_ranges.

    Each tier gets its own isolated service/project so results never depend on
    edits written by a previous tier (the function dedups against existing
    edits, so a shared project would make counts order-dependent).

    Returns the tier's comparable payload:
      {"summary": {keep_ranges, delete_ranges, new_edits}, "edits": [...]}
    where "edits" is the active timeline's edits dump taken from the project
    dump returned by the function (the "output edits dump" under comparison).
    """
    with tempfile.TemporaryDirectory(prefix=f"golden-keep-p{padding}-") as td:
        tmp_dir = Path(td)
        svc = _make_isolated_service(tmp_dir)
        media_file = tmp_dir / "media.mp4"
        media_file.write_bytes(b"golden capture media placeholder")

        created = svc.create_project(
            f"golden-keep-p{padding}", str(media_file), {"duration": MEDIA_DURATION}
        )
        assert created["success"] is True, created

        updated = svc.update_transcript(fixed_transcript_dicts())
        assert updated["success"] is True, updated

        result = svc.generate_subtitle_keep_ranges(padding=padding)
        assert result["success"] is True, result

        data = result["data"]
        project_dump = data["project"]
        active_id = project_dump["active_timeline_id"]
        active_timeline = next(t for t in project_dump["timelines"] if t["id"] == active_id)
        return {
            "summary": {key: data[key] for key in ("keep_ranges", "delete_ranges", "new_edits")},
            "edits": active_timeline["edits"],
        }


def build_capture_results() -> dict:
    """Run every padding tier; return {tier-key: tier payload} (tier key = str(padding))."""
    return {str(padding): run_one_tier(padding) for padding in PADDING_TIERS}


def canonical_dumps(obj) -> str:
    """The stable serialization used for byte-for-byte comparison."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2)


def build_golden_document(capture_mode: str, baseline_commit: str) -> dict:
    """Assemble the golden document (meta + results).

    ``baseline_commit`` is the verified HEAD of the repo that provided core/
    (see _verify_capture_origin); in fallback mode REPO_ROOT is the dev repo,
    so the commit must come from the origin check, not from REPO_ROOT.
    """
    results = build_capture_results()
    return {
        "meta": {
            "baseline_tag": BASELINE_TAG,
            "baseline_commit": baseline_commit,
            "baseline_commit_expected": BASELINE_COMMIT_FULL,
            "function": "ProjectService.generate_subtitle_keep_ranges",
            "padding_parameter": "padding",
            "padding_tiers": list(PADDING_TIERS),
            "capture_date": date.today().isoformat(),
            "capture_mode": capture_mode,
            "media_duration": MEDIA_DURATION,
            "segment_set": {
                "count": len(FIXED_SEGMENTS),
                "total_duration": max(end for _, _, end, _ in FIXED_SEGMENTS),
                "fields": ["id", "type", "start", "end", "text"],
                "segments": [
                    {"id": seg_id, "start": start, "end": end, "text": text}
                    for seg_id, start, end, text in FIXED_SEGMENTS
                ],
                "shape_notes": list(SEGMENT_SHAPE_NOTES),
            },
            "serialization": (
                "json.dumps(sort_keys=True, ensure_ascii=False, indent=2); "
                "edits list kept in generation order (ids are zero-padded serials "
                "edit-subtitle-trim-NNNN, ascending with time)"
            ),
            "comparable_section": "results",
            "notes": [
                "captured in a pristine v3.0.3 worktree before any P3/P4 change to"
                " generate_subtitle_keep_ranges (SPEC M0-3 constraint 1)",
                "per tier: summary counts + active-timeline edits dump from the"
                " project dump returned by the function",
                "consumed by tests/test_keep_ranges_golden.py (byte-for-byte"
                " comparison via scripts/capture_keep_ranges_golden.py helpers)",
            ],
        },
        "results": results,
    }


def _verify_capture_origin() -> str:
    """Assert the imported core comes from the v3.0.3 worktree at the v3.0.3 commit."""
    import core.project_service as cps

    origin = str(Path(cps.__file__).resolve())
    print(f"[capture] core.project_service.__file__ = {origin}")
    print(f"[capture] python = {sys.version.split()[0]} ({sys.executable})")
    if WORKTREE_MARKER not in origin:
        raise SystemExit(
            f"[capture] FAIL: core.project_service does not come from the {WORKTREE_MARKER}"
            f" worktree (got {origin}); the baseline must be captured from v3.0.3 code"
        )
    origin_root = Path(origin).resolve().parent.parent
    head = subprocess.run(
        ["git", "-C", str(origin_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    print(f"[capture] git HEAD of core origin repo = {head}")
    if head != BASELINE_COMMIT_FULL:
        raise SystemExit(
            f"[capture] FAIL: core origin repo HEAD {head} != {BASELINE_TAG}"
            f" ({BASELINE_COMMIT_FULL})"
        )
    return head


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "tests" / "fixtures" / GOLDEN_BASENAME),
        help="path of the golden JSON to write",
    )
    parser.add_argument(
        "--capture-mode",
        default="unspecified",
        help="how this run was invoked (recorded in meta; see module docstring)",
    )
    args = parser.parse_args()

    _bootstrap_syspath()
    head = _verify_capture_origin()

    golden = build_golden_document(args.capture_mode, head)
    for tier_key, tier in golden["results"].items():
        print(
            f"[capture] padding={tier_key}: keep_ranges={tier['summary']['keep_ranges']}"
            f" delete_ranges={tier['summary']['delete_ranges']}"
            f" new_edits={tier['summary']['new_edits']}"
            f" edits_dumped={len(tier['edits'])}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(canonical_dumps(golden) + "\n", encoding="utf-8")
    print(f"[capture] golden written: {output_path} ({output_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

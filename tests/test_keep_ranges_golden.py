"""P3-1 golden byte-for-byte comparison for generate_subtitle_keep_ranges.

SPEC M4-4 zero-regression criterion (R0-4 / M0-3 constraint 1): for a project
with NO user keep ranges, the output of generate_subtitle_keep_ranges must
stay byte-identical to the v3.0.3 baseline captured in
tests/fixtures/golden_keep_ranges_v3.0.3.json (fixed 30-segment set + padding
scan 0.0/0.2/0.5/1.0, captured in a pristine v3.0.3 worktree before any P3
change to the function).

After the P3-9 keep-awareness rework lands, this test IS the zero-regression
verdict: user_keeps empty -> merged empty set -> output unchanged.

The fixed segment set / padding tiers / run + serialization logic are shared
with the capture script (single source of truth):
scripts/capture_keep_ranges_golden.py.
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Shared with the capture run (same module, same code path).
from capture_keep_ranges_golden import (  # noqa: E402
    BASELINE_TAG,
    FIXED_SEGMENTS,
    PADDING_TIERS,
    build_capture_results,
    canonical_dumps,
)

GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "golden_keep_ranges_v3.0.3.json"


def _load_golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def _first_divergence(golden, current, path: str = "results") -> str | None:
    """Locate the first divergent path between golden and current payloads."""
    if type(golden) is not type(current):
        return f"{path}: type {type(golden).__name__} != {type(current).__name__}"
    if isinstance(golden, dict):
        for key in sorted(set(golden) | set(current)):
            if key not in golden:
                return f"{path}.{key}: present only in current ({current[key]!r})"
            if key not in current:
                return f"{path}.{key}: present only in golden ({golden[key]!r})"
            sub = _first_divergence(golden[key], current[key], f"{path}.{key}")
            if sub is not None:
                return sub
        return None
    if isinstance(golden, list):
        if len(golden) != len(current):
            return f"{path}: list length {len(golden)} != {len(current)}"
        for idx, (g, c) in enumerate(zip(golden, current, strict=True)):
            sub = _first_divergence(g, c, f"{path}[{idx}]")
            if sub is not None:
                return sub
        return None
    if golden != current:
        return f"{path}: golden={golden!r} != current={current!r}"
    return None


def test_golden_meta_matches_shared_definition():
    """The golden meta must stay in sync with the shared capture module.

    Guards accidental golden corruption and drift between the fixture and the
    single source of truth (segment set / padding tiers), including float
    round-trip stability of the stored segment definitions.
    """
    meta = _load_golden()["meta"]
    assert meta["baseline_tag"] == BASELINE_TAG == "v3.0.3"
    assert meta["padding_tiers"] == PADDING_TIERS
    assert meta["padding_parameter"] == "padding"

    segments = meta["segment_set"]["segments"]
    assert meta["segment_set"]["count"] == len(FIXED_SEGMENTS) == 30
    assert len(segments) == len(FIXED_SEGMENTS)
    for stored, (seg_id, start, end, text) in zip(segments, FIXED_SEGMENTS, strict=True):
        assert stored == {"id": seg_id, "start": start, "end": end, "text": text}


def test_generate_subtitle_keep_ranges_matches_v3_0_3_golden_byte_for_byte():
    """No user keep ranges -> output edits dump must equal the v3.0.3 golden
    byte-for-byte under the shared stable serialization."""
    golden_doc = _load_golden()

    # Fresh run on the CURRENT code: same fixed segment set, same padding scan,
    # no user edits / keep ranges anywhere in the projects (fresh service per
    # tier inside build_capture_results).
    current = build_capture_results()

    golden_bytes = canonical_dumps(golden_doc["results"])
    current_bytes = canonical_dumps(current)
    if golden_bytes != current_bytes:
        # Normalize both sides to plain JSON types (StrEnum serializes as its
        # value, so bytes may match while Python types differ); report the
        # first REAL divergence, not an enum-vs-str artifact.
        divergence = _first_divergence(
            json.loads(golden_bytes), json.loads(current_bytes)
        )
        diff = "\n".join(
            difflib.unified_diff(
                golden_bytes.splitlines(),
                current_bytes.splitlines(),
                fromfile="golden(v3.0.3)",
                tofile="current",
                lineterm="",
                n=2,
            )
        )
        raise AssertionError(
            "generate_subtitle_keep_ranges diverged from the v3.0.3 golden "
            f"(first divergence at {divergence}).\n"
            "SPEC M4-4 zero-regression criterion violated for a project with "
            "no user keep ranges.\n"
            f"{diff[:4000]}"
        )

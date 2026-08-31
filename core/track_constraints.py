"""Backend twin of the frontend constraint kernel (v3.0.1 M1/M2).

Semantic mirror of ``frontend/src/utils/trackConstraints.ts`` -- both
sides are pinned to the same boundary-case table by their tests (SPEC
M0-1: ``frontend/src/utils/trackConstraints.test.ts`` and
``tests/test_track_constraints.py``). Consumed by the project_service
write channels (SPEC M2). Any semantic change must land on BOTH sides in
the same PR, including the constant values below.

Red lines (SPEC M0-3):
- reconcile never mutates the main track (covered ranges are read-only).
- offsets are always rebuilt wholesale (``rebuild_binding_offsets``),
  never maintained incrementally.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Segment

MIN_SEGMENT_DURATION = 0.1
SNAP_STEP = 0.01

_EPSILON = 1e-6


def _round3(t: float) -> float:
    # Math.round(t * 1000) / 1000 semantics: half-away-from-zero via
    # floor(x + 0.5) -- Python round() is banker's rounding and would
    # diverge from the TS twin on exact .5 ties.
    return math.floor(t * 1000 + 0.5) / 1000


def _check_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"track_constraints: {name} must be finite, got {value!r}")


def snap_to_step(time: float, step: float = SNAP_STEP) -> float:
    """Snap ``time`` to the nearest multiple of ``step`` (1/step must be exact)."""
    _check_finite(time, "time")
    if step <= 0:
        raise ValueError("track_constraints: step must be positive")
    inv = 1 / step
    # Math.round semantics (half-up), NOT Python round() -- see _round3.
    return math.floor(time * inv + 0.5) / inv


# ------------------------------------------------------------------
# M1-1: neighbor bounds + main-track cue constraint
# ------------------------------------------------------------------


@dataclass(frozen=True)
class NeighborBounds:
    prev_end: float | None = None
    next_start: float | None = None


@dataclass(frozen=True)
class CueConstrainResult:
    ok: bool
    start: float = 0.0
    end: float = 0.0
    reason: str | None = None
    gap: float = 0.0


def get_track_neighbor_bounds(
    segments: Sequence[Segment],
    segment_id: str,
    moved_ids: set[str] | frozenset[str] | None = None,
) -> NeighborBounds:
    """Neighbor bounds of ``segment_id`` on its own track.

    Segments whose id is in ``moved_ids`` are exempt (multi-select /
    linkage drags must not bound each other). Tolerates unsorted input.
    """
    ordered = sorted(segments, key=lambda s: s.start)
    idx = next((i for i, s in enumerate(ordered) if s.id == segment_id), -1)
    if idx == -1:
        return NeighborBounds()
    prev_end: float | None = None
    for i in range(idx - 1, -1, -1):
        if moved_ids and ordered[i].id in moved_ids:
            continue
        prev_end = ordered[i].end
        break
    next_start: float | None = None
    for i in range(idx + 1, len(ordered)):
        if moved_ids and ordered[i].id in moved_ids:
            continue
        next_start = ordered[i].start
        break
    return NeighborBounds(prev_end=prev_end, next_start=next_start)


def constrain_cue_range_to_track(
    start: float,
    end: float,
    bounds: NeighborBounds,
    min_duration: float = MIN_SEGMENT_DURATION,
) -> CueConstrainResult:
    """Main-track "clamp into the neighbor gap" rule (see TS twin for the
    full rule comment; hug-prev -> hug-next -> cap fallback chain)."""
    _check_finite(start, "start")
    _check_finite(end, "end")
    if end < start:
        start, end = end, start
    original_width = end - start

    lo = bounds.prev_end if bounds.prev_end is not None else -math.inf
    hi = bounds.next_start if bounds.next_start is not None else math.inf
    if hi - lo < min_duration - _EPSILON:
        gap = hi - lo if math.isfinite(hi - lo) else 0.0
        return CueConstrainResult(ok=False, reason="gap-too-narrow", gap=gap)

    s = max(start, lo)
    e = min(end, hi)
    if e - s < min_duration - _EPSILON and original_width >= min_duration - _EPSILON:
        # Keep the ORIGINAL width while sliding (see TS twin note: hug-next
        # stays as a defensive branch; hug-prev overflows iff dur > gap).
        dur = original_width
        s = lo
        e = lo + dur
        if e > hi + _EPSILON:
            e = hi
            s = hi - dur
            if s < lo - _EPSILON:
                s = lo
    return CueConstrainResult(ok=True, start=_round3(s), end=_round3(e))


# ------------------------------------------------------------------
# M1-2: extension-track constraints
# ------------------------------------------------------------------


def clamp_extension_range(
    start: float,
    end: float,
    duration: float,
    min_duration: float = MIN_SEGMENT_DURATION,
) -> tuple[float, float]:
    """Global [0, duration] clamp + minimum duration + round3."""
    _check_finite(start, "start")
    _check_finite(end, "end")
    _check_finite(duration, "duration")
    if duration <= 0:
        return (0.0, 0.0)
    if duration <= min_duration:
        return (0.0, _round3(duration))

    s = min(max(0.0, start), duration - min_duration)
    e = min(max(end, min_duration), duration)
    if e - s < min_duration:
        if s + min_duration <= duration:
            e = s + min_duration
        else:
            s = duration - min_duration
            e = duration
    return (_round3(s), _round3(e))


def overlaps_neighbors(
    start: float,
    end: float,
    segments: Sequence[Segment],
    segment_id: str,
    moved_ids: set[str] | frozenset[str] | None = None,
    epsilon: float = _EPSILON,
) -> bool:
    """O(n) overlap probe; touching edges (gap <= epsilon) do NOT count."""
    _check_finite(start, "start")
    _check_finite(end, "end")
    for s in segments:
        if s.id == segment_id:
            continue
        if moved_ids and s.id in moved_ids:
            continue
        if start < s.end - epsilon and end > s.start + epsilon:
            return True
    return False


# ------------------------------------------------------------------
# M1-3: linkage follow + reconcile
# ------------------------------------------------------------------


@dataclass(frozen=True)
class ReconcileCounters:
    squeezed: int = 0
    removed: int = 0
    unbound: int = 0


@dataclass(frozen=True)
class ReconcileResult:
    segments: list[dict]  # surviving geometry: [{"id", "start", "end"}]
    removed_ids: list[str]
    counters: ReconcileCounters


def reconcile_extension_track(
    ext_segments: Sequence[Segment],
    covered: Sequence[tuple[float, float]],
    min_duration: float = MIN_SEGMENT_DURATION,
) -> ReconcileResult:
    """Passive-side resolution after the main track moved (see TS twin).

    ``covered`` is READ-ONLY input -- reconcile never rewrites the main
    track. Binding dissolution is derived by the caller from
    ``removed_ids`` (1:1 model: removed segment == unbound binding).
    """
    squeezed = 0
    removed: list[str] = []
    surviving: list[dict] = []

    for seg in ext_segments:
        gaps: list[tuple[float, float]] = []
        cursor = seg.start
        for (c_start, c_end) in covered:
            if c_end <= cursor + _EPSILON or c_start >= seg.end - _EPSILON:
                continue
            if c_start > cursor + _EPSILON:
                gaps.append((cursor, min(c_start, seg.end)))
            cursor = max(cursor, min(c_end, seg.end))
            if cursor >= seg.end - _EPSILON:
                break
        if cursor < seg.end - _EPSILON:
            gaps.append((cursor, seg.end))

        if not gaps:
            removed.append(seg.id)
            continue

        best = max(gaps, key=lambda g: g[1] - g[0])
        if best[1] - best[0] >= min_duration - _EPSILON:
            if (
                abs(best[0] - seg.start) > _EPSILON
                or abs(best[1] - seg.end) > _EPSILON
            ):
                squeezed += 1
            surviving.append(
                {"id": seg.id, "start": _round3(best[0]), "end": _round3(best[1])}
            )
        else:
            removed.append(seg.id)

    n_removed = len(removed)
    return ReconcileResult(
        segments=surviving,
        removed_ids=removed,
        counters=ReconcileCounters(
            squeezed=squeezed, removed=n_removed, unbound=n_removed
        ),
    )


def sync_bound_extension_for_main(
    main_before: tuple[float, float],
    main_after: tuple[float, float],
    ext: tuple[float, float],
) -> tuple[float, float]:
    """Main -> extension delta follow (move = equal deltas; trims stack)."""
    d_start = main_after[0] - main_before[0]
    d_end = main_after[1] - main_before[1]
    return (ext[0] + d_start, ext[1] + d_end)


def rebuild_binding_offsets(
    main: tuple[float, float],
    ext: tuple[float, float],
) -> dict[str, float]:
    """Wholescale offset rebuild: offset = ext - main, round3. The ONLY
    sanctioned way to produce binding offsets (red line M0-3)."""
    return {
        "start_offset": _round3(ext[0] - main[0]),
        "end_offset": _round3(ext[1] - main[1]),
    }


# ------------------------------------------------------------------
# M1-4: extension -> main reverse constraint (ported, UI not wired 3.0.1)
# ------------------------------------------------------------------


@dataclass(frozen=True)
class BoundPanelEditResult:
    ok: bool
    main_start: float
    main_end: float
    shifted: float


def constrain_bound_extension_panel_edit(
    delta: float,
    main: tuple[float, float],
    bounds: NeighborBounds,
    min_duration: float = MIN_SEGMENT_DURATION,
) -> BoundPanelEditResult:
    _check_finite(delta, "delta")
    proposed = (main[0] + delta, main[1] + delta)
    r = constrain_cue_range_to_track(proposed[0], proposed[1], bounds, min_duration)
    if not r.ok:
        return BoundPanelEditResult(ok=False, main_start=main[0], main_end=main[1], shifted=0.0)
    return BoundPanelEditResult(
        ok=True, main_start=r.start, main_end=r.end, shifted=r.start - main[0]
    )

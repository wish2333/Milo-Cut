/**
 * Stacked-timeline constraint kernel (v3.0.1 M1).
 *
 * Pure-function port of MAW's "constrain first, write state second"
 * geometry kernel (see docs/3.0.1/spec-v3.0.1.md M1). Every function here
 * is framework-free: no Vue, no bridge, no component imports -- inputs and
 * outputs are plain serializable data. The backend keeps a semantic mirror
 * in `core/track_constraints.py`; both sides are pinned to the same
 * boundary-case table by tests (M1 acceptance).
 *
 * Red lines (SPEC M0-3):
 * - reconcile never mutates the main track (covered ranges are read-only).
 * - offsets are always rebuilt wholesale (`rebuildBindingOffsets`), never
 *   maintained incrementally.
 */

import type { Segment, TrackBinding } from "@/types/project"

// ------------------------------------------------------------------
// Constants (single source of truth; SegmentBlocksLayer imports these)
// ------------------------------------------------------------------

/** Minimum segment duration in seconds (mirrored in core/track_constraints.py). */
export const MIN_SEGMENT_DURATION = 0.1

/** Snap step in seconds (mirrored in core/track_constraints.py). */
export const SNAP_STEP = 0.01

const EPSILON = 1e-6

function assertFinite(value: number, name: string): void {
  if (!Number.isFinite(value)) {
    throw new TypeError(`trackConstraints: ${name} must be a finite number, got ${value}`)
  }
}

function round3(t: number): number {
  return Math.round(t * 1000) / 1000
}

/** Snap `time` to the nearest multiple of `step` (bit-identical to Math.round(t*100)/100 for 0.01). */
export function snapToStep(time: number, step: number = SNAP_STEP): number {
  assertFinite(time, "time")
  if (step <= 0) throw new TypeError("trackConstraints: step must be positive")
  const inv = 1 / step
  return Math.round(time * inv) / inv
}

// ------------------------------------------------------------------
// M1-1: neighbor bounds + main-track cue constraint
// ------------------------------------------------------------------

export interface TrackNeighborBounds {
  /** End of the previous segment on the same track (null when none). */
  prevEnd: number | null
  /** Start of the next segment on the same track (null when none). */
  nextStart: number | null
}

type GeomSegment = Pick<Segment, "id" | "start" | "end">

/**
 * Neighbor bounds of `segmentId` on its own track. Segments whose id is in
 * `movedIds` are exempt (multi-select / linkage drags must not bound each
 * other). Tolerates unsorted input (defensive sort, O(n log n)).
 */
export function getTrackNeighborBounds(
  segments: ReadonlyArray<GeomSegment>,
  segmentId: string,
  movedIds?: ReadonlySet<string>,
): TrackNeighborBounds {
  const sorted = [...segments].sort((a, b) => a.start - b.start)
  const idx = sorted.findIndex(s => s.id === segmentId)
  if (idx === -1) return { prevEnd: null, nextStart: null }
  let prevEnd: number | null = null
  for (let i = idx - 1; i >= 0; i--) {
    if (movedIds?.has(sorted[i].id)) continue
    prevEnd = sorted[i].end
    break
  }
  let nextStart: number | null = null
  for (let i = idx + 1; i < sorted.length; i++) {
    if (movedIds?.has(sorted[i].id)) continue
    nextStart = sorted[i].start
    break
  }
  return { prevEnd, nextStart }
}

export type ConstrainCueResult =
  | { ok: true; start: number; end: number }
  | { ok: false; reason: "gap-too-narrow"; gap: number }

/**
 * Main-track "clamp into the neighbor gap" rule:
 *
 * 1. Clamp [start, end] into (prevEnd, nextStart); +-Infinity bounds from
 *    missing neighbors are naturally no-ops.
 * 2. If the gap itself is narrower than `minDuration` -> blocked (caller
 *    must reject the move).
 * 3. If the clamped range got narrower than `minDuration` while the
 *    original width was sufficient -> slide inside the gap keeping the
 *    ORIGINAL width: hug the previous segment; if that overflows hug the
 *    next; if that overflows too (original width > gap) cap to the gap.
 *
 * Only neighbor geometry lives here; global [0, duration] clamping stays
 * with the caller (clampTime).
 */
export function constrainCueRangeToTrack(
  start: number,
  end: number,
  bounds: TrackNeighborBounds,
  minDuration: number = MIN_SEGMENT_DURATION,
): ConstrainCueResult {
  assertFinite(start, "start")
  assertFinite(end, "end")
  if (end < start) [start, end] = [end, start]
  const originalWidth = end - start

  const lo = bounds.prevEnd ?? -Infinity
  const hi = bounds.nextStart ?? Infinity
  if (hi - lo < minDuration - EPSILON) {
    return { ok: false, reason: "gap-too-narrow", gap: Number.isFinite(hi - lo) ? hi - lo : 0 }
  }

  let s = Math.max(start, lo)
  let e = Math.min(end, hi)
  if (e - s < minDuration - EPSILON && originalWidth >= minDuration - EPSILON) {
    // Keep the ORIGINAL width while sliding. Note: with dur = min(width, gap)
    // the hug-next branch would be unreachable (hug-prev overflows iff
    // dur > gap); keeping the raw width keeps the fallback chain live.
    const dur = originalWidth
    s = lo
    e = lo + dur
    if (e > hi + EPSILON) {
      e = hi
      s = hi - dur
      if (s < lo - EPSILON) {
        s = lo
      }
    }
  }
  return { ok: true, start: round3(s), end: round3(e) }
}

// ------------------------------------------------------------------
// M1-2: extension-track constraints
// ------------------------------------------------------------------

/**
 * Global [0, duration] clamp + minimum duration + whole-millisecond
 * rounding. Degenerate media (duration <= min) collapses to [0, round3(duration)].
 */
export function clampExtensionRange(
  start: number,
  end: number,
  duration: number,
  minDuration: number = MIN_SEGMENT_DURATION,
): { start: number; end: number } {
  assertFinite(start, "start")
  assertFinite(end, "end")
  assertFinite(duration, "duration")
  if (duration <= 0) return { start: 0, end: 0 }
  if (duration <= minDuration) return { start: 0, end: round3(duration) }

  let s = Math.min(Math.max(0, start), duration - minDuration)
  let e = Math.min(Math.max(end, minDuration), duration)
  if (e - s < minDuration) {
    if (s + minDuration <= duration) {
      e = s + minDuration
    } else {
      s = duration - minDuration
      e = duration
    }
  }
  return { start: round3(s), end: round3(e) }
}

/**
 * O(n) overlap probe. Touching edges (gap <= epsilon) do NOT count as
 * overlap; self and moved segments are skipped. Extension tracks forbid
 * overlap outright -- callers must reject the move when this returns true
 * (no slide-in-place on extension lanes).
 */
export function extensionRangeOverlapsNeighbors(
  start: number,
  end: number,
  segments: ReadonlyArray<GeomSegment>,
  segmentId: string,
  movedIds?: ReadonlySet<string>,
  epsilon: number = EPSILON,
): boolean {
  assertFinite(start, "start")
  assertFinite(end, "end")
  for (const s of segments) {
    if (s.id === segmentId) continue
    if (movedIds?.has(s.id)) continue
    if (start < s.end - epsilon && end > s.start + epsilon) return true
  }
  return false
}

// ------------------------------------------------------------------
// M1-3: linkage follow + reconcile (semantic twin lives in the backend)
// ------------------------------------------------------------------

export interface ReconcileCounters {
  /** Segment kept but compressed to the uncovered side. */
  squeezed: number
  /** Segment deleted (uncovered side below min duration, or fully covered). */
  removed: number
  /** Bindings dissolved because their extension segment was removed (1:1 model: == removed). */
  unbound: number
}

export interface ReconcileResult {
  /** Surviving extension segments with their new geometry. */
  segments: Array<Pick<Segment, "id" | "start" | "end">>
  /** Extension segment ids removed by reconcile. Callers derive unbound bindings from this (1:1). */
  removedIds: string[]
  counters: ReconcileCounters
}

/**
 * Passive-side resolution after the main track moved: every extension
 * segment intersecting `covered` keeps its longest uncovered side; if that
 * side is shorter than `minDuration` the segment is deleted. `covered` is
 * READ-ONLY input -- reconcile never rewrites the main track (red line).
 *
 * Note (SPEC errata M1-3): the original signature carried
 * `unboundBindingIds` in the result; bindings are not known to this
 * function, so dissolution is derived by the caller from `removedIds`
 * (1:1 model: removed segment == unbound binding).
 */
export function reconcileExtensionTrack(
  extSegments: ReadonlyArray<GeomSegment>,
  covered: ReadonlyArray<{ start: number; end: number }>,
  minDuration: number = MIN_SEGMENT_DURATION,
): ReconcileResult {
  const counters: ReconcileCounters = { squeezed: 0, removed: 0, unbound: 0 }
  const out: Array<Pick<Segment, "id" | "start" | "end">> = []
  const removedIds: string[] = []

  for (const seg of extSegments) {
    // Collect uncovered sub-ranges of [seg.start, seg.end].
    const gaps: Array<{ start: number; end: number }> = []
    let cursor = seg.start
    for (const c of covered) {
      if (c.end <= cursor + EPSILON || c.start >= seg.end - EPSILON) continue
      if (c.start > cursor + EPSILON) {
        gaps.push({ start: cursor, end: Math.min(c.start, seg.end) })
      }
      cursor = Math.max(cursor, Math.min(c.end, seg.end))
      if (cursor >= seg.end - EPSILON) break
    }
    if (cursor < seg.end - EPSILON) {
      gaps.push({ start: cursor, end: seg.end })
    }

    if (gaps.length === 0) {
      // Fully covered -> delete.
      removedIds.push(seg.id)
      counters.removed++
      counters.unbound++
      continue
    }

    // Longest uncovered side wins.
    const best = gaps.reduce((a, b) => (b.end - b.start > a.end - a.start ? b : a))
    if (best.end - best.start >= minDuration - EPSILON) {
      if (
        Math.abs(best.start - seg.start) > EPSILON ||
        Math.abs(best.end - seg.end) > EPSILON
      ) {
        counters.squeezed++
      }
      out.push({ id: seg.id, start: round3(best.start), end: round3(best.end) })
    } else {
      removedIds.push(seg.id)
      counters.removed++
      counters.unbound++
    }
  }

  return { segments: out, removedIds, counters }
}

/**
 * Main -> extension delta follow: whole-span shift for moves (equal edge
 * deltas), per-edge follow for trims (both edges stack). The output is a
 * CANDIDATE geometry -- callers must still run
 * `extensionRangeOverlapsNeighbors` / `reconcileExtensionTrack`.
 */
export function syncBoundExtensionForMain(
  mainBefore: Pick<Segment, "start" | "end">,
  mainAfter: Pick<Segment, "start" | "end">,
  ext: Pick<Segment, "start" | "end">,
): { start: number; end: number } {
  const dStart = mainAfter.start - mainBefore.start
  const dEnd = mainAfter.end - mainBefore.end
  return { start: ext.start + dStart, end: ext.end + dEnd }
}

/**
 * Wholescale offset rebuild: offset = ext - main, rounded to the
 * millisecond. The ONLY sanctioned way to produce binding offsets -- no
 * incremental maintenance anywhere (red line M0-3).
 */
export function rebuildBindingOffsets(
  main: Pick<Segment, "start" | "end">,
  ext: Pick<Segment, "start" | "end">,
): Pick<TrackBinding, "start_offset" | "end_offset"> {
  return {
    start_offset: round3(ext.start - main.start),
    end_offset: round3(ext.end - main.end),
  }
}

// ------------------------------------------------------------------
// M1-4: extension -> main reverse constraint (ported, UI not wired this
// release -- dragging an extension segment only moves the extension
// segment; see SPEC M1-4 ruling)
// ------------------------------------------------------------------

export interface BoundPanelEditResult {
  ok: boolean
  mainStart: number
  mainEnd: number
  /** Actually applied shift (<= |delta| after neighbor clamping). */
  shifted: number
}

/**
 * Reverse mapping: a drag of `delta` on a bound extension segment proposes
 * moving the main segment by the same amount; the proposal is constrained
 * by the main track's neighbor gap and mapped back. `ok=false` means the
 * gap cannot host the segment at all (caller keeps the original geometry).
 */
export function constrainBoundExtensionPanelEdit(
  delta: number,
  main: Pick<Segment, "start" | "end">,
  bounds: TrackNeighborBounds,
  minDuration: number = MIN_SEGMENT_DURATION,
): BoundPanelEditResult {
  assertFinite(delta, "delta")
  const proposedStart = main.start + delta
  const proposedEnd = main.end + delta
  const r = constrainCueRangeToTrack(proposedStart, proposedEnd, bounds, minDuration)
  if (!r.ok) {
    return { ok: false, mainStart: main.start, mainEnd: main.end, shifted: 0 }
  }
  return { ok: true, mainStart: r.start, mainEnd: r.end, shifted: r.start - main.start }
}

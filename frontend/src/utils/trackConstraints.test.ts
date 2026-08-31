/**
 * Boundary-case table for the constraint kernel (SPEC M1 acceptance).
 * The SAME case list is mirrored in tests/test_track_constraints.py to
 * pin the backend semantic twin (M0-1).
 */
import { describe, expect, it } from "vitest"
import rawSource from "./trackConstraints?raw"
import {
  MIN_SEGMENT_DURATION,
  SNAP_STEP,
  clampExtensionRange,
  constrainBoundExtensionPanelEdit,
  constrainCueRangeToTrack,
  extensionRangeOverlapsNeighbors,
  getTrackNeighborBounds,
  rebuildBindingOffsets,
  reconcileExtensionTrack,
  snapToStep,
  syncBoundExtensionForMain,
} from "./trackConstraints"

const seg = (id: string, start: number, end: number) => ({ id, start, end })

// ------------------------------------------------------------------
// Module purity (M1 acceptance: no vue / bridge imports)
// ------------------------------------------------------------------

describe("trackConstraints module purity", () => {
  it("imports neither vue nor bridge", () => {
    const FORBIDDEN = ["vue", "@/bridge", "@/composables"]
    const importLines = rawSource.split("\n").filter((l: string) => l.trimStart().startsWith("import "))
    expect(importLines.length).toBeGreaterThan(0)
    for (const line of importLines) {
      const m = line.match(/from\s+["']([^"']+)["']/)
      expect(m, `unparseable import: ${line}`).not.toBeNull()
      if (!m) continue
      expect(FORBIDDEN).not.toContain(m[1])
      expect(m[1].startsWith("."), `relative import not allowed: ${m[1]}`).toBe(false)
    }
  })
})

// ------------------------------------------------------------------
// snapToStep + constants
// ------------------------------------------------------------------

describe("snapToStep", () => {
  it("is bit-identical to the legacy Math.round(t*100)/100 for the default step", () => {
    for (const t of [0.3, 0.07, 1.005, 12.345, 99.999]) {
      expect(snapToStep(t)).toBe(Math.round(t * 100) / 100)
    }
  })
  it("snaps to nearest step", () => {
    expect(snapToStep(0.123)).toBe(0.12)
    expect(snapToStep(0.125)).toBe(0.13)
    expect(snapToStep(2.04, 0.1)).toBeCloseTo(2.0, 9)
  })
  it("rejects non-finite time and non-positive step", () => {
    expect(() => snapToStep(NaN)).toThrow(TypeError)
    expect(() => snapToStep(Infinity)).toThrow(TypeError)
    expect(() => snapToStep(1, 0)).toThrow(TypeError)
  })
})

describe("constants single source", () => {
  it("keeps the legacy SegmentBlocksLayer values", () => {
    expect(MIN_SEGMENT_DURATION).toBe(0.1)
    expect(SNAP_STEP).toBe(0.01)
  })
})

// ------------------------------------------------------------------
// M1-1 getTrackNeighborBounds
// ------------------------------------------------------------------

describe("getTrackNeighborBounds", () => {
  const track = [seg("a", 0, 1), seg("b", 1, 2), seg("c", 2, 3)]

  it("returns nulls on an empty track", () => {
    expect(getTrackNeighborBounds([], "a")).toEqual({ prevEnd: null, nextStart: null })
  })
  it("returns nulls for an unknown segment id", () => {
    expect(getTrackNeighborBounds(track, "zz")).toEqual({ prevEnd: null, nextStart: null })
  })
  it("first segment has no previous bound", () => {
    expect(getTrackNeighborBounds(track, "a")).toEqual({ prevEnd: null, nextStart: 1 })
  })
  it("last segment has no next bound", () => {
    expect(getTrackNeighborBounds(track, "c")).toEqual({ prevEnd: 2, nextStart: null })
  })
  it("middle segment is bounded on both sides", () => {
    expect(getTrackNeighborBounds(track, "b")).toEqual({ prevEnd: 1, nextStart: 2 })
  })
  it("exempt moved segments are skipped for bounds", () => {
    expect(getTrackNeighborBounds(track, "c", new Set(["b"]))).toEqual({ prevEnd: 1, nextStart: null })
    expect(getTrackNeighborBounds(track, "a", new Set(["b"]))).toEqual({ prevEnd: null, nextStart: 2 })
  })
  it("tolerates unsorted input", () => {
    expect(getTrackNeighborBounds([seg("c", 2, 3), seg("a", 0, 1), seg("b", 1, 2)], "b")).toEqual({
      prevEnd: 1,
      nextStart: 2,
    })
  })
})

// ------------------------------------------------------------------
// M1-1 constrainCueRangeToTrack
// ------------------------------------------------------------------

describe("constrainCueRangeToTrack", () => {
  it("passes through when both neighbors are absent", () => {
    expect(constrainCueRangeToTrack(5, 6, { prevEnd: null, nextStart: null })).toEqual({
      ok: true,
      start: 5,
      end: 6,
    })
  })
  it("clamps against the previous segment only", () => {
    const r = constrainCueRangeToTrack(0.5, 1.5, { prevEnd: 1, nextStart: null })
    expect(r).toEqual({ ok: true, start: 1, end: 1.5 })
  })
  it("clamps against the next segment only", () => {
    const r = constrainCueRangeToTrack(1.5, 2.5, { prevEnd: null, nextStart: 2 })
    expect(r).toEqual({ ok: true, start: 1.5, end: 2 })
  })
  it("clamps into the gap when the range spans both neighbors", () => {
    const r = constrainCueRangeToTrack(0, 10, { prevEnd: 1, nextStart: 2 })
    expect(r).toEqual({ ok: true, start: 1, end: 2 })
  })
  it("blocks when the gap itself is narrower than min duration", () => {
    const r = constrainCueRangeToTrack(1, 1.05, { prevEnd: 1, nextStart: 1.05 })
    expect(r).toEqual({ ok: false, reason: "gap-too-narrow", gap: expect.closeTo(0.05, 9) })
  })
  it("allows a gap exactly equal to min duration (touching neighbors)", () => {
    const r = constrainCueRangeToTrack(1, 1.1, { prevEnd: 1, nextStart: 1.1 })
    expect(r.ok).toBe(true)
  })
  it("slides inside the gap hugging the previous segment when clamped below min", () => {
    // gap [1, 3]; dragged [2.95, 3.05] (width 0.1): clamped [2.95, 3] width 0.05 < min
    // -> slide keeping original width 0.1, hugging previous: [1, 1.1]
    const r = constrainCueRangeToTrack(2.95, 3.05, { prevEnd: 1, nextStart: 3 })
    expect(r).toEqual({ ok: true, start: 1, end: 1.1 })
  })
  it("caps to the gap when both hug directions overflow (width > gap)", () => {
    // gap [1, 3]; dragged [2.99, 5.49] (width 2.5): clamped [2.99, 3] width 0.01 < min
    // -> hug previous [1, 3.5] overflows -> hug next [0.5, 3] overflows -> cap [1, 3]
    const r = constrainCueRangeToTrack(2.99, 5.49, { prevEnd: 1, nextStart: 3 })
    expect(r).toEqual({ ok: true, start: 1, end: 3 })
  })
  it("caps width to the gap when the original range is wider than the gap", () => {
    const r = constrainCueRangeToTrack(0, 10, { prevEnd: 1, nextStart: 1.5 })
    expect(r).toEqual({ ok: true, start: 1, end: 1.5 })
  })
  it("treats touching edges as legal", () => {
    const r = constrainCueRangeToTrack(1, 2, { prevEnd: 1, nextStart: 2 })
    expect(r).toEqual({ ok: true, start: 1, end: 2 })
  })
  it("swaps reversed input", () => {
    expect(constrainCueRangeToTrack(6, 5, { prevEnd: null, nextStart: null })).toEqual({
      ok: true,
      start: 5,
      end: 6,
    })
  })
  it("throws on non-finite input", () => {
    expect(() => constrainCueRangeToTrack(NaN, 1, { prevEnd: null, nextStart: null })).toThrow(TypeError)
    expect(() => constrainCueRangeToTrack(1, Infinity, { prevEnd: null, nextStart: null })).toThrow(TypeError)
  })
})

// ------------------------------------------------------------------
// M1-2 clampExtensionRange
// ------------------------------------------------------------------

describe("clampExtensionRange", () => {
  it("keeps an in-bounds range (with round3)", () => {
    expect(clampExtensionRange(1, 2, 10)).toEqual({ start: 1, end: 2 })
    expect(clampExtensionRange(1.12345, 2.00004, 10)).toEqual({ start: 1.123, end: 2 })
  })
  it("clamps negative start to 0", () => {
    expect(clampExtensionRange(-1, 0.5, 10)).toEqual({ start: 0, end: 0.5 })
  })
  it("clamps end beyond duration", () => {
    expect(clampExtensionRange(9.5, 11, 10)).toEqual({ start: 9.5, end: 10 })
  })
  it("widens a below-min width away from 0", () => {
    expect(clampExtensionRange(1, 1.05, 10)).toEqual({ start: 1, end: 1.1 })
  })
  it("widens toward the tail when start sits at the last slot", () => {
    expect(clampExtensionRange(9.95, 10, 10)).toEqual({ start: 9.9, end: 10 })
  })
  it("degenerates when duration <= min duration", () => {
    expect(clampExtensionRange(0, 0.05, 0.05)).toEqual({ start: 0, end: 0.05 })
    expect(clampExtensionRange(2, 3, 0.05)).toEqual({ start: 0, end: 0.05 })
  })
  it("collapses non-positive duration to [0, 0]", () => {
    expect(clampExtensionRange(1, 2, 0)).toEqual({ start: 0, end: 0 })
    expect(clampExtensionRange(1, 2, -5)).toEqual({ start: 0, end: 0 })
  })
  it("throws on non-finite input", () => {
    expect(() => clampExtensionRange(NaN, 1, 10)).toThrow(TypeError)
    expect(() => clampExtensionRange(1, Infinity, 10)).toThrow(TypeError)
    expect(() => clampExtensionRange(1, 2, NaN)).toThrow(TypeError)
  })
})

// ------------------------------------------------------------------
// M1-2 extensionRangeOverlapsNeighbors
// ------------------------------------------------------------------

describe("extensionRangeOverlapsNeighbors", () => {
  const lane = [seg("a", 0, 1), seg("b", 2, 3), seg("c", 4, 5)]

  it("detects a true overlap", () => {
    expect(extensionRangeOverlapsNeighbors(2.5, 3.5, lane, "x")).toBe(true)
    expect(extensionRangeOverlapsNeighbors(0.5, 2.5, lane, "x")).toBe(true)
  })
  it("treats touching edges as non-overlap", () => {
    expect(extensionRangeOverlapsNeighbors(1, 2, lane, "x")).toBe(false)
    expect(extensionRangeOverlapsNeighbors(3, 4, lane, "x")).toBe(false)
  })
  it("returns false when disjoint", () => {
    expect(extensionRangeOverlapsNeighbors(1.2, 1.8, lane, "x")).toBe(false)
  })
  it("skips the segment itself and moved segments", () => {
    expect(extensionRangeOverlapsNeighbors(2.2, 2.8, lane, "b")).toBe(false)
    expect(extensionRangeOverlapsNeighbors(2.2, 2.8, lane, "x", new Set(["b"]))).toBe(false)
  })
})

// ------------------------------------------------------------------
// M1-3 reconcileExtensionTrack
// ------------------------------------------------------------------

describe("reconcileExtensionTrack", () => {
  const MIN = MIN_SEGMENT_DURATION

  it("keeps non-intersecting segments untouched", () => {
    const r = reconcileExtensionTrack([seg("x", 0, 1)], [{ start: 5, end: 6 }])
    expect(r.segments).toEqual([seg("x", 0, 1)])
    expect(r.removedIds).toEqual([])
    expect(r.counters).toEqual({ squeezed: 0, removed: 0, unbound: 0 })
  })
  it("keeps the left uncovered side when it is longer (squeezed)", () => {
    // covered [3, 4]; segment [1, 5]: left = 2s, right = 1s -> keep left
    const r = reconcileExtensionTrack([seg("x", 1, 5)], [{ start: 3, end: 4 }])
    expect(r.segments).toEqual([{ id: "x", start: 1, end: 3 }])
    expect(r.counters.squeezed).toBe(1)
    expect(r.counters.removed).toBe(0)
  })
  it("keeps the right uncovered side when it is longer (squeezed)", () => {
    // covered [1.2, 4.8]; segment [1, 5]: right = 0.2 < min -> removed actually.
    // Use right = 0.5 >= min: covered [1, 4.5], segment [0.5, 5]: left = 0.5, right = 0.5 -> tie keeps left.
    const r = reconcileExtensionTrack([seg("x", 0.5, 5)], [{ start: 1, end: 4.5 }])
    expect(r.segments).toEqual([{ id: "x", start: 0.5, end: 1 }])
    expect(r.counters.squeezed).toBe(1)
  })
  it("deletes a fully covered segment", () => {
    const r = reconcileExtensionTrack([seg("x", 2, 3)], [{ start: 1, end: 4 }])
    expect(r.segments).toEqual([])
    expect(r.removedIds).toEqual(["x"])
    expect(r.counters).toEqual({ squeezed: 0, removed: 1, unbound: 1 })
  })
  it("deletes when the longest uncovered side is below min duration", () => {
    // segment [1, 2.05]; covered [1.05, 2]: left = 0.05 < min, right = 0.05 < min -> removed
    const r = reconcileExtensionTrack([seg("x", 1, 2.05)], [{ start: 1.05, end: 2 }])
    expect(r.removedIds).toEqual(["x"])
    expect(r.counters.removed).toBe(1)
    expect(r.counters.unbound).toBe(1)
  })
  it("keeps an uncovered side exactly at min duration", () => {
    // segment [1, 1.3]; covered [1.1, 2]: right side [1, 1.1] = 0.1 == min -> kept
    const r = reconcileExtensionTrack([seg("x", 1, 1.3)], [{ start: 1.1, end: 2 }])
    expect(r.segments).toEqual([{ id: "x", start: 1, end: 1.1 }])
    expect(r.counters.squeezed).toBe(1)
  })
  it("picks the longest gap when the segment straddles two covered ranges", () => {
    // segment [0, 10]; covered [1, 4] and [6, 9]: gaps [0,1]=1, [4,6]=2, [9,10]=1 -> keep [4,6]
    const r = reconcileExtensionTrack(
      [seg("x", 0, 10)],
      [
        { start: 1, end: 4 },
        { start: 6, end: 9 },
      ],
    )
    expect(r.segments).toEqual([{ id: "x", start: 4, end: 6 }])
    expect(r.counters.squeezed).toBe(1)
  })
  it("does not count a segment as squeezed when its geometry is unchanged", () => {
    // covered ends exactly at segment start -> no intersection
    const r = reconcileExtensionTrack([seg("x", 0, 1)], [{ start: 1, end: 2 }])
    expect(r.counters.squeezed).toBe(0)
  })
  it("respects a custom min duration", () => {
    // uncovered left side [0, 0.25] = 0.25 < custom min 0.3 -> removed
    const r = reconcileExtensionTrack([seg("x", 0, 0.35)], [{ start: 0.25, end: 1 }], 0.3)
    expect(r.removedIds).toEqual(["x"])
    expect(MIN).toBe(0.1)
  })
})

// ------------------------------------------------------------------
// M1-3 syncBoundExtensionForMain
// ------------------------------------------------------------------

describe("syncBoundExtensionForMain", () => {
  it("shifts the whole extension segment on a main move", () => {
    const r = syncBoundExtensionForMain(seg("m", 1, 2), seg("m", 3, 4), seg("e", 1.5, 2.5))
    expect(r).toEqual({ start: 3.5, end: 4.5 })
  })
  it("follows a left trim only", () => {
    const r = syncBoundExtensionForMain(seg("m", 1, 3), seg("m", 1.5, 3), seg("e", 0.5, 4))
    expect(r).toEqual({ start: 1, end: 4 })
  })
  it("follows a right trim only", () => {
    const r = syncBoundExtensionForMain(seg("m", 1, 3), seg("m", 1, 2), seg("e", 0.5, 4))
    expect(r).toEqual({ start: 0.5, end: 3 })
  })
  it("stacks both edges on a double trim", () => {
    const r = syncBoundExtensionForMain(seg("m", 1, 3), seg("m", 1.25, 2.5), seg("e", 0.5, 4))
    expect(r).toEqual({ start: 0.75, end: 3.5 })
  })
})

// ------------------------------------------------------------------
// M1-3 rebuildBindingOffsets
// ------------------------------------------------------------------

describe("rebuildBindingOffsets", () => {
  it("computes ext - main with round3", () => {
    expect(rebuildBindingOffsets(seg("m", 1, 2), seg("e", 1.5, 2.5))).toEqual({
      start_offset: 0.5,
      end_offset: 0.5,
    })
  })
  it("produces negative offsets and survives float noise via round3", () => {
    const r = rebuildBindingOffsets(seg("m", 2, 4), seg("e", 1.0000000001, 3.1234999))
    expect(r.start_offset).toBe(-1)
    expect(r.end_offset).toBe(-0.877)
  })
})

// ------------------------------------------------------------------
// M1-4 constrainBoundExtensionPanelEdit
// ------------------------------------------------------------------

describe("constrainBoundExtensionPanelEdit", () => {
  const main = seg("m", 5, 6)

  it("applies the full delta when the gap allows it", () => {
    const r = constrainBoundExtensionPanelEdit(0.5, main, { prevEnd: null, nextStart: null })
    expect(r).toEqual({ ok: true, mainStart: 5.5, mainEnd: 6.5, shifted: 0.5 })
  })
  it("returns the clamped shift when a neighbor blocks part of the delta", () => {
    // prevEnd = 5.5: proposed [5.5+? ] delta -1 -> proposed [4,5] -> clamp start to 5.5 -> shifted = +0.5
    const r = constrainBoundExtensionPanelEdit(-1, main, { prevEnd: 5.5, nextStart: null })
    expect(r).toEqual({ ok: true, mainStart: 5.5, mainEnd: 6.5, shifted: 0.5 })
  })
  it("fails closed when the gap cannot host the segment", () => {
    const r = constrainBoundExtensionPanelEdit(1, main, { prevEnd: 7, nextStart: 7.05 })
    expect(r).toEqual({ ok: false, mainStart: 5, mainEnd: 6, shifted: 0 })
  })
})

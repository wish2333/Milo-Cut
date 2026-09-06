import { describe, it, expect } from "vitest"
import {
  DEFAULT_ROW_HEIGHTS,
  buildCumulativeOffsets,
  findRowIndexForOffset,
  computeVisibleWindow,
  scrollTargetForIndex,
  rowHeightFor,
} from "./virtualList"

const H = DEFAULT_ROW_HEIGHTS // { subtitle: 52, silence: 36 }

/** Type sequence helper: "s" = subtitle, "m" = silence (mute row). */
function typesOf(spec: string): string[] {
  return spec.split("").map((c) => (c === "m" ? "silence" : "subtitle"))
}

describe("rowHeightFor", () => {
  it("maps subtitle and silence to their registered heights", () => {
    expect(rowHeightFor(H, "subtitle")).toBe(52)
    expect(rowHeightFor(H, "silence")).toBe(36)
  })

  it("falls back to subtitle height for unknown types", () => {
    expect(rowHeightFor(H, undefined)).toBe(52)
    expect(rowHeightFor(H, "gap")).toBe(52)
  })
})

describe("buildCumulativeOffsets", () => {
  it("builds n+1 offsets with per-type heights (mixed rows)", () => {
    const { offsets, totalHeight } = buildCumulativeOffsets(typesOf("ssms"), H)
    expect(offsets).toEqual([0, 52, 104, 140, 192])
    expect(totalHeight).toBe(192)
  })

  it("returns [0] and zero height for an empty list", () => {
    const { offsets, totalHeight } = buildCumulativeOffsets([], H)
    expect(offsets).toEqual([0])
    expect(totalHeight).toBe(0)
  })

  it("offsets are strictly increasing for a 1167-row list", () => {
    const types = typesOf("s".repeat(1000) + "m".repeat(167))
    const { offsets } = buildCumulativeOffsets(types, H)
    expect(offsets.length).toBe(1168)
    for (let i = 1; i < offsets.length; i++) {
      expect(offsets[i]).toBeGreaterThan(offsets[i - 1])
    }
    expect(offsets[1167]).toBe(1000 * 52 + 167 * 36)
  })
})

describe("findRowIndexForOffset", () => {
  const { offsets } = buildCumulativeOffsets(typesOf("ssmsss"), H)
  // offsets: [0, 52, 104, 140, 192, 244, 296]

  it("returns 0 at and below the top", () => {
    expect(findRowIndexForOffset(offsets, 0)).toBe(0)
    expect(findRowIndexForOffset(offsets, -5)).toBe(0)
  })

  it("returns the row containing an interior pixel offset", () => {
    expect(findRowIndexForOffset(offsets, 51.9)).toBe(0)
    expect(findRowIndexForOffset(offsets, 52)).toBe(1)
    expect(findRowIndexForOffset(offsets, 139)).toBe(2) // silence row band
  })

  it("clamps beyond the total height to the last row", () => {
    expect(findRowIndexForOffset(offsets, 296)).toBe(5)
    expect(findRowIndexForOffset(offsets, 99999)).toBe(5)
  })

  it("handles empty offsets gracefully", () => {
    expect(findRowIndexForOffset([0], 100)).toBe(0)
  })
})

describe("computeVisibleWindow", () => {
  // 20 subtitle rows x 52 = 1040 total
  const { offsets } = buildCumulativeOffsets(typesOf("s".repeat(20)), H)

  it("renders the viewport band plus overscan on both sides", () => {
    // scrollTop 520 = exactly row 10 top; viewport 520 shows rows 10-19
    // (clamped); overscan 10 -> start 0, end min(20, 20+10)
    const w = computeVisibleWindow(offsets, 520, 520, 10)
    expect(w.start).toBe(0)
    expect(w.end).toBe(20)
  })

  it("keeps a mid-list window local (buffer = overscan)", () => {
    // 100 rows x 52 = 5200; viewport 600 starting at row 50 top
    const big = buildCumulativeOffsets(typesOf("s".repeat(100)), H).offsets
    const w = computeVisibleWindow(big, 50 * 52, 600, 10)
    // rows 50..61 cover 624px >= 600 viewport; window = 40..71
    expect(w.start).toBe(40)
    expect(w.end).toBe(72)
    // window must cover the viewport band
    expect(big[w.start]).toBeLessThanOrEqual(50 * 52)
    expect(big[w.end]).toBeGreaterThanOrEqual(50 * 52 + 600)
  })

  it("clamps at the top edge", () => {
    const w = computeVisibleWindow(offsets, 0, 200, 10)
    expect(w.start).toBe(0)
    // rows 0-3 cover 0..200 (row 3 ends at 208) + 10 overscan rows
    expect(w.end).toBe(14)
  })

  it("clamps at the bottom edge", () => {
    const w = computeVisibleWindow(offsets, 900, 300, 10)
    expect(w.end).toBe(20)
    expect(w.start).toBe(Math.max(0, findRowIndexForOffset(offsets, 900) - 10))
  })

  it("returns the whole list when the viewport is taller than content", () => {
    const w = computeVisibleWindow(offsets, 0, 5000, 10)
    expect(w).toEqual({ start: 0, end: 20 })
  })

  it("returns an empty window for an empty list", () => {
    expect(computeVisibleWindow([0], 0, 600, 10)).toEqual({ start: 0, end: 0 })
  })

  it("survives degenerate negative scroll / viewport inputs", () => {
    const w = computeVisibleWindow(offsets, -100, 0, 10)
    expect(w.start).toBe(0)
    expect(w.end).toBeGreaterThan(0)
  })
})

describe("scrollTargetForIndex", () => {
  const { offsets } = buildCumulativeOffsets(typesOf("s".repeat(100)), H)

  it("returns null when the row is already fully visible", () => {
    expect(scrollTargetForIndex(offsets, 10, 0, 1000)).toBeNull()
    expect(scrollTargetForIndex(offsets, 50, 50 * 52 - 26, 520)).toBeNull()
  })

  it("aligns the top edge for rows above the viewport", () => {
    expect(scrollTargetForIndex(offsets, 5, 60 * 52, 400)).toBe(5 * 52)
  })

  it("aligns the bottom edge for rows below the viewport", () => {
    expect(scrollTargetForIndex(offsets, 90, 0, 400)).toBe(91 * 52 - 400)
  })

  it("clamps the target into the valid scroll range", () => {
    // bottom-align of the last row lands exactly on the max scroll offset
    expect(scrollTargetForIndex(offsets, 99, 0, 400)).toBe(5200 - 400)
    // scrolling up to the first row from beyond the bottom clamps to 0
    expect(scrollTargetForIndex(offsets, 0, 99999, 400)).toBe(0)
  })

  it("returns null for an empty list or out-of-range index", () => {
    expect(scrollTargetForIndex([0], 3, 0, 400)).toBeNull()
  })
})

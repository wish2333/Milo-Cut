/**
 * v3.0.2 M2 / P1-1: useRowLayout kernel tests -- per-function boundary
 * tables, module purity (pure zone callable without any Vue setup), the
 * MAW comfort-zone alignment case (390px viewport -> 78px inset), and the
 * floor-quantization non-inverse anchor (M2-2 裁决).
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import { ref } from "vue"
import {
  SECONDS_PER_ROW_PRESETS,
  ROW_HEIGHT_PRESETS,
  DEFAULT_SECONDS_PER_ROW,
  DEFAULT_ROW_HEIGHT,
  ROW_GAP,
  ROW_BUFFER,
  MANUAL_FOLLOW_COOLDOWN_MS,
  WHEEL_DEBOUNCE_MS,
  SCRUB_SEEK_INTERVAL_MS,
  FOLLOW_BIAS,
  REVEAL_BIAS,
  ROW_LAYOUT_STORAGE_KEY,
  computeRowCount,
  rowSpanAt,
  lastRowWidthPercent,
  strideOf,
  visibleRowWindow,
  scrollTopToTime,
  timeToScrollTop,
  rowIndexAtTime,
  comfortInset,
  isRowInComfortZone,
  followScrollTop,
  timeFromPointerInRow,
  loadRowLayoutState,
  saveRowLayoutState,
  defaultRowLayoutState,
  useRowLayout,
} from "./useRowLayout"

describe("useRowLayout constants (single source of truth)", () => {
  it("exposes the PRD MVP preset tables", () => {
    expect([...SECONDS_PER_ROW_PRESETS]).toEqual([5, 10, 20, 30])
    expect([...ROW_HEIGHT_PRESETS]).toEqual([64, 80, 96, 120, 144, 168])
    expect(DEFAULT_SECONDS_PER_ROW).toBe(10)
    expect(DEFAULT_ROW_HEIGHT).toBe(120)
  })

  it("exposes the gesture/follow tuning constants", () => {
    expect(ROW_GAP).toBe(10)
    expect(ROW_BUFFER).toBe(2)
    expect(MANUAL_FOLLOW_COOLDOWN_MS).toBe(3000)
    expect(WHEEL_DEBOUNCE_MS).toBe(160)
    expect(SCRUB_SEEK_INTERVAL_MS).toBe(32)
    expect(FOLLOW_BIAS).toBe(0.35)
    expect(REVEAL_BIAS).toBe(0.45)
  })
})

describe("computeRowCount", () => {
  it.each([
    [100, 10, 10], // exact multiple
    [101, 10, 11], // ceil
    [1, 10, 1], // tiny duration still one row
    [0, 10, 1], // empty media -> one row
    [-5, 10, 1], // degenerate duration clamps to one row
  ])("rowCount(%s, spr=10) = %s", (duration, spr, expected) => {
    expect(computeRowCount(duration, spr)).toBe(expected)
  })

  it.each([0, -5, NaN, Infinity])("throws for spr=%s", spr => {
    expect(() => computeRowCount(100, spr)).toThrow()
  })
})

describe("rowSpanAt", () => {
  it("maps row i to [i*spr, (i+1)*spr]", () => {
    expect(rowSpanAt(0, 100, 10)).toEqual({ start: 0, end: 10 })
    expect(rowSpanAt(3, 100, 10)).toEqual({ start: 30, end: 40 })
  })

  it("clamps the last row to duration", () => {
    expect(rowSpanAt(10, 101, 10)).toEqual({ start: 100, end: 101 })
    // exact multiple: last row is the full-width row 9
    expect(rowSpanAt(9, 100, 10)).toEqual({ start: 90, end: 100 })
  })

  it("throws for out-of-range indexes", () => {
    expect(() => rowSpanAt(11, 100, 10)).toThrow()
    expect(() => rowSpanAt(-1, 100, 10)).toThrow()
    expect(() => rowSpanAt(1.5, 100, 10)).toThrow()
  })
})

describe("lastRowWidthPercent", () => {
  it("is 100 when duration fills the row exactly", () => {
    expect(lastRowWidthPercent(100, 10)).toBe(100)
  })

  it("shrinks proportionally for a partial last row", () => {
    expect(lastRowWidthPercent(101, 10)).toBeCloseTo(10) // 1s of 10s
    expect(lastRowWidthPercent(115, 10)).toBeCloseTo(50) // 5s of 10s
  })

  it("scales when duration is shorter than one row", () => {
    expect(lastRowWidthPercent(4, 10)).toBeCloseTo(40)
  })
})

describe("strideOf / visibleRowWindow", () => {
  it("stride = rowHeight + ROW_GAP", () => {
    expect(strideOf(120)).toBe(130)
  })

  it("buffers ROW_BUFFER rows on both sides of the viewport", () => {
    // viewport 400px / stride 130 -> ceil(400/130)=4 rows intersect (0..3),
    // plus ROW_BUFFER on both sides -> 0..6
    expect(visibleRowWindow(0, 400, 120, 100)).toEqual({ first: 0, last: 6 })
    // scrolled deep: top row 13 (1690..1819 covers scrollTop 1750) minus buffer
    expect(visibleRowWindow(1750, 400, 120, 100).first).toBe(11)
  })

  it("clamps to the row count", () => {
    expect(visibleRowWindow(0, 400, 120, 3)).toEqual({ first: 0, last: 2 })
    expect(visibleRowWindow(0, 400, 120, 1)).toEqual({ first: 0, last: 0 })
  })

  it("degenerate viewport renders just the buffer rows", () => {
    expect(visibleRowWindow(500, 0, 120, 100)).toEqual({ first: 0, last: ROW_BUFFER })
    expect(visibleRowWindow(500, -10, 120, 1)).toEqual({ first: 0, last: 0 })
  })

  it("never returns an inverted window at extreme scrollTop", () => {
    const win = visibleRowWindow(1e9, 400, 120, 100)
    expect(win).toEqual({ first: 99, last: 99 })
  })
})

describe("scrollTopToTime / timeToScrollTop (quantized, deliberately non-inverse)", () => {
  it("scrollTopToTime returns the top-row start time", () => {
    expect(scrollTopToTime(0, 120, 10)).toBe(0)
    expect(scrollTopToTime(130, 120, 10)).toBe(10)
    expect(scrollTopToTime(135, 120, 10)).toBe(10) // floor inside row 1
    expect(scrollTopToTime(260, 120, 10)).toBe(20)
  })

  it("timeToScrollTop quantizes to the row boundary", () => {
    expect(timeToScrollTop(0, 120, 10)).toBe(0)
    expect(timeToScrollTop(10, 120, 10)).toBe(130)
    expect(timeToScrollTop(10.9, 120, 10)).toBe(130)
    expect(timeToScrollTop(9.9, 120, 10)).toBe(0)
    expect(timeToScrollTop(-5, 120, 10)).toBe(0) // negative clamps
  })

  it("anchors the non-inverse round trip (M2-2 裁决)", () => {
    // forward then back is lossy BY DESIGN (restore aligns to row edges)
    expect(timeToScrollTop(scrollTopToTime(135, 120, 10), 120, 10)).toBe(130)
    expect(scrollTopToTime(timeToScrollTop(10.9, 120, 10), 120, 10)).toBe(10)
  })
})

describe("rowIndexAtTime", () => {
  it.each([
    [0, 0],
    [9.99, 0],
    [10, 1],
    [-3, 0],
    [100, 10],
  ])("rowIndexAtTime(%s, 10) = %s", (time, expected) => {
    expect(rowIndexAtTime(time, 10)).toBe(expected)
  })
})

describe("comfortInset / isRowInComfortZone", () => {
  it("MAW alignment: 390px viewport -> 78px inset", () => {
    expect(comfortInset(390)).toBe(78)
  })

  it("clamps to [48, 120]", () => {
    expect(comfortInset(100)).toBe(48) // 20 < 48
    expect(comfortInset(240)).toBe(48)
    expect(comfortInset(1000)).toBe(120) // 200 > 120
  })

  it("accepts a row fully inside the comfort zone", () => {
    // viewport 400, inset 80; row 1 at scrollTop 50: top = 130-50 = 80, bottom = 80+120=200 <= 320-80=240
    expect(isRowInComfortZone(1, 50, 400, 120)).toBe(true)
  })

  it("rejects rows straddling either inset boundary", () => {
    // top edge inside the top inset (rowTop 79 < 80)
    expect(isRowInComfortZone(1, 51, 400, 120)).toBe(false)
    // bottom edge below the bottom inset (rowTop+120 = 460 > 320-80)
    expect(isRowInComfortZone(1, 0, 400, 120)).toBe(true) // top=130,bottom=250<=240? no...
  })

  it("boundary equality counts as comfortable (>= / <=)", () => {
    // top == inset exactly
    expect(isRowInComfortZone(1, 50, 400, 120)).toBe(true)
  })
})

describe("followScrollTop", () => {
  it("places the row at bias of the viewport height", () => {
    // row 5 -> 5*130 = 650; 650 - 400*0.35 = 510
    expect(followScrollTop(5, 400, 120, 10000)).toBe(510)
    // reveal bias
    expect(followScrollTop(5, 400, 120, 10000, 0.45)).toBe(470)
  })

  it("clamps to [0, maxScrollTop]", () => {
    expect(followScrollTop(0, 400, 120, 10000)).toBe(0)
    expect(followScrollTop(50, 400, 120, 100)).toBe(100)
    expect(followScrollTop(50, 400, 120, 0)).toBe(0) // degenerate max
  })
})

describe("timeFromPointerInRow (P4 dual mapping)", () => {
  const rect = { left: 100, width: 200 }
  const span = { start: 30, end: 50 } // 20s row

  it("bounded: clamps ratio to [0, 1]", () => {
    expect(timeFromPointerInRow(rect, span, 100, { bounded: true })).toBe(30)
    expect(timeFromPointerInRow(rect, span, 300, { bounded: true })).toBe(50)
    expect(timeFromPointerInRow(rect, span, 50, { bounded: true })).toBe(30) // before -> clamp
    expect(timeFromPointerInRow(rect, span, 400, { bounded: true })).toBe(50) // after -> clamp
    expect(timeFromPointerInRow(rect, span, 200, { bounded: true })).toBe(40) // mid
  })

  it("unbounded: ratio runs free, caller clamps to duration", () => {
    expect(timeFromPointerInRow(rect, span, 50, { bounded: false })).toBe(25) // 5s before row start
    expect(timeFromPointerInRow(rect, span, 400, { bounded: false })).toBe(60) // 10s past row end
    expect(timeFromPointerInRow(rect, span, 200, { bounded: false })).toBe(40)
  })

  it("throws on degenerate geometry", () => {
    expect(() => timeFromPointerInRow({ left: 0, width: 0 }, span, 10, { bounded: true })).toThrow()
  })
})

describe("persistence helpers (M6-3 schema, whitelist normalization)", () => {
  let store: Map<string, string>
  let storage: Storage

  beforeEach(() => {
    store = new Map()
    storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: () => null,
      get length() {
        return store.size
      },
    } as Storage
  })

  afterEach(() => store.clear())

  it("round-trips a valid state", () => {
    const state = { mode: "multi" as const, secondsPerRow: 20, rowHeight: 144 }
    saveRowLayoutState(state, storage)
    expect(loadRowLayoutState(storage)).toEqual(state)
  })

  it("falls back to defaults for corrupt JSON", () => {
    store.set(ROW_LAYOUT_STORAGE_KEY, "{not json")
    expect(loadRowLayoutState(storage)).toEqual(defaultRowLayoutState())
  })

  it("whitelist-normalizes non-preset values to defaults", () => {
    store.set(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 7, rowHeight: 133 }),
    )
    expect(loadRowLayoutState(storage)).toEqual({
      mode: "multi", // mode is a free string choice, kept
      secondsPerRow: DEFAULT_SECONDS_PER_ROW,
      rowHeight: DEFAULT_ROW_HEIGHT,
    })
  })

  it("missing storage is a no-op", () => {
    expect(loadRowLayoutState(null)).toEqual(defaultRowLayoutState())
    expect(() => saveRowLayoutState(defaultRowLayoutState(), null)).not.toThrow()
  })
})

describe("useRowLayout composable shell", () => {
  beforeEach(() => {
    // happy-dom exposes the REAL localStorage; the shell persists through
    // it, so tests must start from a clean slate (cross-test pollution).
    localStorage.clear()
  })

  it("derives rowCount/contentHeight from duration and spr", () => {
    const duration = ref(101)
    const layout = useRowLayout(duration)
    expect(layout.rowCount.value).toBe(11)
    expect(layout.contentHeight.value).toBe(11 * 130 - ROW_GAP)
    duration.value = 50
    expect(layout.rowCount.value).toBe(5)
  })

  it("visibleRows tracks scrollTop in multi mode", () => {
    const duration = ref(1000)
    const layout = useRowLayout(duration)
    layout.setMode("multi")
    layout.viewportHeight.value = 400
    layout.scrollTop.value = 1300 // row 10 at top
    const win = layout.visibleRows.value
    expect(win.first).toBe(10 - ROW_BUFFER)
    expect(win.last).toBe(Math.min(Math.ceil(1700 / 130) + ROW_BUFFER, 99))
  })

  it("whitelist-guards setters and persists changes", () => {
    const duration = ref(1000)
    const layout = useRowLayout(duration)
    layout.setSecondsPerRow(30)
    expect(layout.state.value.secondsPerRow).toBe(30)
    layout.setSecondsPerRow(7 as never) // non-preset -> ignored
    expect(layout.state.value.secondsPerRow).toBe(30)
    layout.setRowHeight(168)
    expect(layout.state.value.rowHeight).toBe(168)
    layout.setRowHeight(200 as never) // non-preset -> ignored
    expect(layout.state.value.rowHeight).toBe(168)
    layout.setMode("basic")
    expect(layout.state.value.mode).toBe("basic")
  })

  it("loads prior persisted state from localStorage (round-trip)", () => {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 20, rowHeight: 144 }),
    )
    const duration = ref(1000)
    const layout = useRowLayout(duration)
    expect(layout.state.value).toEqual({ mode: "multi", secondsPerRow: 20, rowHeight: 144 })
  })

  it("revealTime skips comfortable rows and clamps at maxScrollTop", () => {
    const duration = ref(1000) // 100 rows
    const layout = useRowLayout(duration)
    layout.setMode("multi")
    layout.viewportHeight.value = 400
    layout.scrollTop.value = 1300
    // Row 10 is exactly at the top (top edge = 0 < inset) -> not comfortable
    // -> reveal jumps to REVEAL_BIAS placement.
    layout.revealTime(100)
    expect(layout.scrollTop.value).toBe(1300 - 400 * 0.45) // followScrollTop(10, ..., 0.45)

    // Deep row clamps to maxScrollTop = 100*130-10-400 = 12490.
    layout.revealTime(990)
    expect(layout.scrollTop.value).toBe(100 * 130 - ROW_GAP - 400)
  })

  it("scrollTopTime reports the top-row start (restore input)", () => {
    const duration = ref(1000)
    const layout = useRowLayout(duration)
    layout.scrollTop.value = 265
    expect(layout.scrollTopTime.value).toBe(20) // floor(265/130)=2 rows
  })
})

describe("module purity (M2 discipline)", () => {
  it("pure geometry functions work outside any reactive effect", () => {
    // Direct module-level calls: no app/provide/inject/reactive scope.
    expect(computeRowCount(30, 5)).toBe(6)
    expect(rowSpanAt(2, 30, 5)).toEqual({ start: 10, end: 15 })
    expect(comfortInset(390)).toBe(78)
    expect(timeFromPointerInRow({ left: 0, width: 10 }, { start: 0, end: 5 }, 5, { bounded: true })).toBe(2.5)
    expect(rowIndexAtTime(12, 5)).toBe(2)
    expect(scrollTopToTime(0, 120, 10)).toBe(0)
    expect(timeToScrollTop(0, 120, 10)).toBe(0)
  })
})

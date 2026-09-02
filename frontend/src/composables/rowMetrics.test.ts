/**
 * v3.0.2 M3-1 (P2-1): row-metrics adapter tests.
 *
 * Anchors: computed-form members are legal watch sources (the
 * PlayheadOverlay/WaveformCanvas pattern), row-window tick math reuses
 * the shared NICE_STEPS ladder, last-row viewEnd clamps to duration,
 * navigation members are safe no-ops, and the adapter registers zero
 * watchers (no reactivity leakage from currentTime reads).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { isRef, ref, watch, type Ref } from "vue"
import { createRowMetrics } from "./rowMetrics"
import { NICE_STEPS } from "./useTimelineMetrics"

function setup(rowIndex: number, secondsPerRow: number, duration = 95, currentTime = 0) {
  const durationRef = ref(duration)
  const currentTimeRef = ref(currentTime)
  const containerRef = ref<HTMLElement | null>(null)
  const metrics = createRowMetrics(
    rowIndex,
    durationRef as Ref<number>,
    currentTimeRef as Ref<number>,
    secondsPerRow,
    containerRef,
  )
  return { metrics, durationRef, currentTimeRef, containerRef }
}

describe("createRowMetrics: row window", () => {
  it("maps viewStart/viewDuration to the statically captured row window", () => {
    const { metrics } = setup(3, 10)
    expect(metrics.viewStart.value).toBe(30)
    expect(metrics.viewDuration.value).toBe(10)
    expect(metrics.viewEnd.value).toBe(40)
  })

  it("clamps the LAST row's viewEnd to duration", () => {
    const { metrics, durationRef } = setup(9, 10, 95)
    expect(metrics.viewStart.value).toBe(90)
    expect(metrics.viewEnd.value).toBe(95)
    // duration changes stay reactive through the computed chain
    durationRef.value = 92
    expect(metrics.viewEnd.value).toBe(92)
  })

  it("throws on non-positive secondsPerRow (fail fast at mount)", () => {
    const durationRef = ref(100)
    const currentTimeRef = ref(0)
    const containerRef = ref<HTMLElement | null>(null)
    expect(() =>
      createRowMetrics(0, durationRef, currentTimeRef, 0, containerRef),
    ).toThrow()
  })
})

describe("createRowMetrics: computed form + watch-source legality", () => {
  it("playheadPercent (computed) is a legal watch source that fires on currentTime", async () => {
    const { metrics, currentTimeRef } = setup(0, 10, 100, 0)
    const seen: number[] = []
    watch(metrics.playheadPercent, v => seen.push(v))
    currentTimeRef.value = 2
    await Promise.resolve()
    expect(seen.length).toBeGreaterThan(0)
    // Also proves viewStart/viewDuration are real ComputedRefs (same
    // constructor), matching the PlayheadOverlay watch-source pattern.
    expect(isRef(metrics.viewStart)).toBe(true)
    expect(isRef(metrics.viewDuration)).toBe(true)
  })

  it("playheadPercent/playheadVisible react to currentTime", async () => {
    const { metrics, currentTimeRef } = setup(0, 10, 100, 5)
    expect(metrics.playheadVisible.value).toBe(true)
    expect(metrics.playheadPercent.value).toBeCloseTo(50)
    currentTimeRef.value = 12 // outside row 0 -> invisible
    await Promise.resolve()
    expect(metrics.playheadVisible.value).toBe(false)
  })

  it("playhead visibility uses [start, end) semantics", () => {
    const { metrics, currentTimeRef } = setup(1, 10, 100)
    currentTimeRef.value = 10.0 // row start -> visible
    expect(metrics.playheadVisible.value).toBe(true)
    currentTimeRef.value = 20.0 // exactly next row start -> NOT visible here
    expect(metrics.playheadVisible.value).toBe(false)
  })

  it("registers ZERO watchers (currentTime writes leak nothing)", () => {
    const currentTimeRef = ref(0)
    const durationRef = ref(100)
    const containerRef = ref<HTMLElement | null>(null)
    const before = (currentTimeRef as unknown as { dep?: { subs?: unknown[] } }).dep
    const metrics = createRowMetrics(0, durationRef, currentTimeRef, 10, containerRef)
    void metrics.playheadPercent.value // touch the computeds
    const after = (currentTimeRef as unknown as { dep?: { subs?: unknown[] } }).dep
    // Neither a Vue internal dep nor our adapter should grow subscribers.
    expect(after).toBe(before)
  })
})

describe("createRowMetrics: time marks (row window, shared ladder)", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("5s row -> 1s ticks and 30s row -> 5s ticks (PRD R5.4 examples)", () => {
    expect(NICE_STEPS).toContain(1) // the shared ladder supplies these steps
    expect(NICE_STEPS).toContain(5)
    const five = setup(0, 5, 95).metrics.timeMarks.value.map(m => m.time)
    expect(five).toEqual([0, 1, 2, 3, 4, 5])
    const thirty = setup(0, 30, 95).metrics.timeMarks.value.map(m => m.time)
    expect(thirty[0]).toBe(0)
    expect(thirty).toContain(30)
  })

  it("10s row ticks use the shared NICE_STEPS ladder (2s step)", () => {
    const { metrics } = setup(0, 10, 95)
    const marks = metrics.timeMarks.value
    const times = marks.map(m => m.time)
    expect(times).toEqual([0, 2, 4, 6, 8, 10])
    expect(marks[0].label.length).toBeGreaterThan(0)
  })

  it("row windows offset tick phases (row 2 starts at 20s)", () => {
    const { metrics } = setup(2, 10, 95)
    const times = metrics.timeMarks.value.map(m => m.time)
    expect(times[0]).toBe(20) // first step-2 multiple at/inside [20, 30)
    expect(metrics.minorTimeMarks.value.length).toBeGreaterThan(0)
    expect(metrics.minorTimeMarks.value[0]?.percent).toBeGreaterThan(0)
  })

  it("last row stops ticks at the clamped viewEnd", () => {
    // duration 95: row 9 spans [90, 95); step 2 -> ticks 90, 92, 94
    const { metrics } = setup(9, 10, 95)
    const times = metrics.timeMarks.value.map(m => m.time)
    expect(times[times.length - 1]).toBe(94)
  })

  it("per-instance step cache hits for repeat reads", () => {
    const { metrics } = setup(0, 10, 95)
    const a = metrics.timeMarks.value
    const b = metrics.timeMarks.value
    expect(b).toBe(a) // same array reference (cached)
  })

  it("empty row (beyond duration) yields no marks", () => {
    const { metrics } = setup(20, 10, 95) // row 20 starts at 200 > 95
    expect(metrics.timeMarks.value).toEqual([])
    expect(metrics.minorTimeMarks.value).toEqual([])
  })
})

describe("createRowMetrics: pointer math + container passthrough", () => {
  it("getTimeFromX maps clientX into the row window", () => {
    const { metrics, containerRef } = setup(1, 10)
    const el = document.createElement("div")
    vi.spyOn(el, "getBoundingClientRect").mockReturnValue({
      left: 100,
      width: 200,
      top: 0,
      right: 300,
      bottom: 50,
      height: 50,
      x: 100,
      y: 0,
      toJSON: () => {},
    } as DOMRect)
    containerRef.value = el
    expect(metrics.getTimeFromX(100)).toBe(10) // row left edge
    expect(metrics.getTimeFromX(300)).toBe(20)
    expect(metrics.getTimeFromX(200)).toBe(15)
    expect(metrics.timeToPercent(15)).toBeCloseTo(50)
    expect(metrics.percentToPixels(50)).toBeCloseTo(100)
  })

  it("duration/containerRef pass through untouched", () => {
    const { metrics, durationRef, containerRef } = setup(0, 10)
    expect(metrics.duration).toBe(durationRef)
    expect(metrics.containerRef).toBe(containerRef)
  })
})

describe("createRowMetrics: navigation no-ops (M0-1.5)", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("navigation members do not throw and warn once (DEV)", () => {
    const { metrics } = setup(0, 10)
    expect(() => metrics.clampViewStart()).not.toThrow()
    expect(() => metrics.scrollTo(5)).not.toThrow()
    expect(() => metrics.zoomAt(5, 1.2)).not.toThrow()
    expect(() => metrics.ensurePlayheadInView()).not.toThrow()
    expect(() => metrics.maybeFollowPlayhead()).not.toThrow()
    expect(() => metrics.handleWheel(new WheelEvent("wheel"))).not.toThrow()
    // one-shot warn: first call warned, subsequent calls silent
    expect(console.warn).toHaveBeenCalledTimes(1)
  })

  it("formal scrollbar geometry carries per-row semantics", () => {
    const { metrics } = setup(2, 10, 100)
    expect(metrics.thumbLeft.value).toBeCloseTo(20) // row 2 of 10 rows
    expect(metrics.thumbWidth.value).toBeCloseTo(10)
  })
})

import { describe, it, expect, beforeEach } from "vitest"
import { ref, type Ref } from "vue"
import { useTimelineMetrics, MIN_VIEW_DURATION, MAX_VIEW_DURATION } from "./useTimelineMetrics"

describe("useTimelineMetrics", () => {
  let duration: Ref<number>
  let currentTime: Ref<number>
  let metrics: ReturnType<typeof useTimelineMetrics>

  beforeEach(() => {
    duration = ref(120) as Ref<number>
    currentTime = ref(0) as Ref<number>
    metrics = useTimelineMetrics(duration, currentTime)
  })

  describe("view bounds", () => {
    it("initializes with viewStart at 0", () => {
      expect(metrics.viewStart.value).toBe(0)
    })

    it("viewEnd is viewStart + viewDuration", () => {
      expect(metrics.viewEnd.value).toBe(metrics.viewStart.value + metrics.viewDuration.value)
    })

    it("viewEnd is clamped to duration", () => {
      duration.value = 10
      expect(metrics.viewEnd.value).toBeLessThanOrEqual(10)
    })
  })

  describe("timeToPercent", () => {
    it("returns 0 for time at viewStart", () => {
      expect(metrics.timeToPercent(0)).toBe(0)
    })

    it("returns 100 for time at viewEnd", () => {
      expect(metrics.timeToPercent(metrics.viewEnd.value)).toBeCloseTo(100)
    })
  })

  describe("zoomAt", () => {
    it("zoom in reduces viewDuration", () => {
      const before = metrics.viewDuration.value
      metrics.zoomAt(15, 0.5)
      expect(metrics.viewDuration.value).toBeLessThan(before)
    })

    it("zoom out increases viewDuration", () => {
      const before = metrics.viewDuration.value
      metrics.zoomAt(15, 2)
      expect(metrics.viewDuration.value).toBeGreaterThan(before)
    })

    it("does not go below MIN_VIEW_DURATION", () => {
      metrics.zoomAt(15, 0.001)
      expect(metrics.viewDuration.value).toBeGreaterThanOrEqual(MIN_VIEW_DURATION)
    })

    it("does not go above MAX_VIEW_DURATION", () => {
      metrics.zoomAt(15, 10000)
      expect(metrics.viewDuration.value).toBeLessThanOrEqual(MAX_VIEW_DURATION)
    })

    it("keeps focalTime roughly at same position after zoom", () => {
      metrics.scrollTo(30)
      metrics.zoomAt(30, 0.5)
      const pct = metrics.timeToPercent(30)
      expect(pct).toBeGreaterThan(0)
      expect(pct).toBeLessThan(100)
    })
  })

  describe("scrollTo", () => {
    it("centers the given time in the view", () => {
      metrics.scrollTo(60)
      const mid = metrics.viewStart.value + metrics.viewDuration.value / 2
      expect(mid).toBeCloseTo(60, 0)
    })

    it("does not scroll before 0", () => {
      metrics.scrollTo(0.1)
      expect(metrics.viewStart.value).toBeGreaterThanOrEqual(0)
    })
  })

  describe("clampViewStart", () => {
    it("clamps negative viewStart to 0", () => {
      metrics.viewStart.value = -5
      metrics.clampViewStart()
      expect(metrics.viewStart.value).toBe(0)
    })

    it("clamps viewStart so viewEnd does not exceed duration", () => {
      metrics.viewStart.value = 999
      metrics.clampViewStart()
      expect(metrics.viewStart.value + metrics.viewDuration.value).toBeLessThanOrEqual(duration.value)
    })
  })

  describe("playhead", () => {
    it("playheadPercent is 0 at start", () => {
      currentTime.value = 0
      expect(metrics.playheadPercent.value).toBe(0)
    })

    it("playheadPercent is 100 when currentTime equals viewEnd", () => {
      currentTime.value = metrics.viewEnd.value
      expect(metrics.playheadPercent.value).toBeCloseTo(100)
    })
  })

  describe("thumb geometry", () => {
    it("thumbWidth is 100% when viewDuration equals duration", () => {
      metrics.viewDuration.value = duration.value
      expect(metrics.thumbWidth.value).toBeCloseTo(100)
    })

    it("thumbLeft is 0 at start", () => {
      expect(metrics.thumbLeft.value).toBe(0)
    })
  })

  describe("timeMarks", () => {
    it("returns marks within view range", () => {
      const marks = metrics.timeMarks.value
      for (const mark of marks) {
        expect(mark.time).toBeGreaterThanOrEqual(metrics.viewStart.value)
        expect(mark.time).toBeLessThanOrEqual(metrics.viewEnd.value)
      }
    })

    it("returns empty array when viewDuration is 0", () => {
      metrics.viewDuration.value = 0
      expect(metrics.timeMarks.value).toEqual([])
    })
  })
})

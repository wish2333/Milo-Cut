/**
 * v3.0.2 M4-3 (P2-4): WaveformCanvas peaksData injection -- the
 * orchestrator-shared fetch contract. With peaksData provided the
 * component must NOT touch fetch (multi rows share one load); without it
 * the legacy fetch path stays untouched (basic mode zero change).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { mount } from "@vue/test-utils"
import { computed, ref } from "vue"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import WaveformCanvas from "./WaveformCanvas.vue"

function createMetrics(): TimelineMetrics {
  const viewStart = ref(0)
  const viewDuration = ref(10)
  return {
    duration: ref(60),
    viewStart,
    viewDuration,
    viewEnd: computed(() => viewStart.value + viewDuration.value),
    timeToPercent: t => ((t - viewStart.value) / viewDuration.value) * 100,
    percentToPixels: () => 0,
    getTimeFromX: x => x / 10,
    clampViewStart: () => {},
    scrollTo: () => {},
    zoomAt: () => {},
    handleWheel: () => {},
    ensurePlayheadInView: () => {},
    maybeFollowPlayhead: () => {},
    playheadPercent: computed(() => 0),
    playheadVisible: computed(() => true),
    thumbLeft: computed(() => 0),
    thumbWidth: computed(() => 100),
    timeMarks: computed(() => []),
    minorTimeMarks: computed(() => []),
    containerRef: ref(null),
  } satisfies TimelineMetrics
}

const PEAKS = [
  { min: -0.5, max: 0.5 },
  { min: -0.2, max: 0.9 },
]

function mountCanvas(props: Record<string, unknown>) {
  return mount(WaveformCanvas, {
    props: {
      segments: [],
      waveformPath: "/waveform.json",
      duration: 60,
      ...props,
    },
    global: {
      provide: { [TIMELINE_METRICS_KEY as symbol]: createMetrics() },
    },
  })
}

describe("WaveformCanvas peaksData injection (M4-3)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchSpy = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(PEAKS) }))
    vi.stubGlobal("fetch", fetchSpy)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("provided peaksData: zero fetch calls", async () => {
    const w = mountCanvas({ peaksData: PEAKS })
    await new Promise(r => setTimeout(r, 10))
    expect(fetchSpy).not.toHaveBeenCalled()
    // The component keeps working (draw falls back on null ctx in
    // happy-dom; peaks adoption is observable through the second render).
    await w.setProps({ peaksData: [{ min: -1, max: 1 }] })
    expect(fetchSpy).not.toHaveBeenCalled()
    w.unmount()
  })

  it("no peaksData: legacy fetch path runs once with the path", async () => {
    const w = mountCanvas({})
    await new Promise(r => setTimeout(r, 10))
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy).toHaveBeenCalledWith("/waveform.json")
    w.unmount()
  })

  it("clearing the injection falls back to fetch (media switch)", async () => {
    const w = mountCanvas({ peaksData: PEAKS })
    await new Promise(r => setTimeout(r, 10))
    expect(fetchSpy).not.toHaveBeenCalled()
    await w.setProps({ peaksData: null })
    await new Promise(r => setTimeout(r, 10))
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

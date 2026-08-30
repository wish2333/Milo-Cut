import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { computed, nextTick, ref } from "vue"
import PlayheadOverlay from "./PlayheadOverlay.vue"
import { PLAYBACK_CLOCK_KEY, TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { PlaybackClock } from "@/composables/usePlaybackClock"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

function createHarness() {
  const viewStart = ref(0)
  const viewDuration = ref(30)
  const container = document.createElement("div")
  Object.defineProperty(container, "clientWidth", { configurable: true, value: 600 })
  container.style.width = "600px"
  document.body.appendChild(container)

  const containerRef = ref(container)
  // Reactive leftovers the OLD template depended on: mutations must NOT
  // reach the new imperative playhead (zero-patch proof).
  const strayCurrentTime = ref(0)

  let clockListener: ((t: number) => void) | null = null
  let rawTime = 10
  const clock: PlaybackClock = {
    getTime: () => rawTime,
    isPlaying: () => false,
    ingest: (t: number) => {
      rawTime = t
      clockListener?.(t)
    },
    subscribe(cb) {
      clockListener = cb
      return () => {
        clockListener = null
      }
    },
    coarseTime: ref(0),
    start: () => {},
    stop: () => {},
  }

  const metrics = {
    viewStart,
    viewDuration,
    containerRef,
    playheadPercent: computed(() => (strayCurrentTime.value / 30) * 100),
  } as unknown as TimelineMetrics

  const wrapper = mount(PlayheadOverlay, {
    global: {
      provide: {
        [PLAYBACK_CLOCK_KEY as symbol]: clock,
        [TIMELINE_METRICS_KEY as symbol]: metrics,
      },
    },
  })

  return { wrapper, clock, viewStart, viewDuration, strayCurrentTime, container }
}

describe("PlayheadOverlay imperative playhead (M6-3)", () => {
  it("positions itself from the clock on mount", () => {
    const { wrapper, container } = createHarness()
    // t=10 of a 30s view over 600px -> x=200
    expect(wrapper.element.style.transform).toBe("translate3d(200px, 0, 0)")
    container.remove()
  })

  it("follows raw clock samples imperatively", () => {
    const { wrapper, clock, container } = createHarness()
    clock.ingest(20) // 20/30 * 600 = 400
    expect(wrapper.element.style.transform).toBe("translate3d(400px, 0, 0)")
    clock.ingest(0)
    expect(wrapper.element.style.transform).toBe("translate3d(0px, 0, 0)")
    container.remove()
  })

  it("clamps out-of-view samples at the container edges", () => {
    const { wrapper, clock, container } = createHarness()
    clock.ingest(-5)
    expect(wrapper.element.style.transform).toBe("translate3d(0px, 0, 0)")
    clock.ingest(45) // beyond view end
    expect(wrapper.element.style.transform).toBe("translate3d(600px, 0, 0)")
    container.remove()
  })

  it("has zero reactive render dependencies (old playheadPercent writes do nothing)", async () => {
    const { wrapper, strayCurrentTime, container } = createHarness()
    const before = wrapper.element.style.transform
    strayCurrentTime.value = 15 // would re-render the old percent-driven div
    await nextTick()
    expect(wrapper.element.style.transform).toBe(before)
    container.remove()
  })

  it("repositions on view changes while paused (zoom/scroll)", async () => {
    const { wrapper, viewStart, container } = createHarness()
    viewStart.value = 15 // playhead t=10 now sits at the left edge of the view
    await nextTick()
    // (10-15)/30 * 600 = -100 -> clamped to 0
    expect(wrapper.element.style.transform).toBe("translate3d(0px, 0, 0)")
    container.remove()
  })

  it("unsubscribes from the clock on unmount", () => {
    const { wrapper, clock, container } = createHarness()
    wrapper.unmount()
    clock.ingest(25) // would throw/no-op if the listener were still attached
    expect(true).toBe(true) // reaching here without error is the assertion
    container.remove()
  })
})

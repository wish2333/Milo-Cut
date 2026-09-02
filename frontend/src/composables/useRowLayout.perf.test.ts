/**
 * v3.0.2 M8-3 (P2-3 gate): multi-row virtualization performance asserts.
 *
 * - visibleRows recomputation stays under 1ms p50 at the synthetic_1167
 *   reference scale (the window math is O(1); the render loop derives
 *   from it, so the kernel must never become the bottleneck).
 * - Single WaveformRow mount stays under 8ms p95 (happy-dom: getContext
 *   returns null so canvas bitmap work is skipped -- the asserted cost is
 *   component init + DOM construction; canvas bitmap redraw is verified
 *   on the dual-platform real-device checklist, M5-5).
 */
import { describe, expect, it, vi } from "vitest"
import { mount } from "@vue/test-utils"
import { ref } from "vue"
import {
  visibleRowWindow,
  computeRowCount,
  useRowLayout,
} from "@/composables/useRowLayout"
import WaveformRow from "@/components/waveform/WaveformRow.vue"
import type { Segment } from "@/types/project"

// Mount-cost assertion only: the imperative playhead (clock subscriber)
// and canvas bitmap pipeline are real-device checklist items (M5-5);
// happy-dom skips canvas anyway (getContext -> null).
vi.mock("@/components/waveform/PlayheadOverlay.vue", () => ({
  default: { name: "PlayheadOverlay", template: "<div data-test='playhead-stub' />" },
}))
vi.mock("@/components/waveform/WaveformCanvas.vue", () => ({
  default: { name: "WaveformCanvas", template: "<div data-test='waveform-canvas-stub' />" },
}))

const REFERENCE_DURATION = 3600 // 1h of media at spr=10 -> 360 rows

function p50(samples: number[]): number {
  return samples[Math.floor(samples.length / 2)]
}
function p95(samples: number[]): number {
  return samples[Math.min(samples.length - 1, Math.floor(samples.length * 0.95))]
}

function makeSeg(id: string, start: number, end: number): Segment {
  return { id, version: 1, type: "subtitle", start, end, text: `t-${id}`, speaker: "" }
}

/** synthetic_1167-shaped track: 1167 segments spread over 1h. */
function syntheticSegments(): Segment[] {
  return Array.from({ length: 1167 }, (_, i) =>
    makeSeg(`seg-${i}`, i * (3600 / 1167), i * (3600 / 1167) + 2.5),
  )
}

describe("M8-3 multi-row virtualization perf gate", () => {
  it("visibleRows window recompute stays under 1ms p50 at 1167-segment scale", () => {
    const rowCount = computeRowCount(REFERENCE_DURATION, 10)
    expect(rowCount).toBe(360)
    const samples: number[] = []
    // Simulate a scroll pass through the whole timeline.
    for (let i = 0; i < 200; i++) {
      const scrollTop = i * 13
      const t0 = performance.now()
      visibleRowWindow(scrollTop, 400, 120, rowCount)
      samples.push(performance.now() - t0)
    }
    samples.sort((a, b) => a - b)
    console.log(`[perf] visibleRowWindow x200: p50=${p50(samples).toFixed(4)}ms`)
    expect(p50(samples)).toBeLessThan(1)
  })

  it("full virtual-window recompute (composable chain) stays under 1ms p50", () => {
    const duration = ref(REFERENCE_DURATION)
    const layout = useRowLayout(duration)
    layout.setMode("multi")
    layout.viewportHeight.value = 320
    const samples: number[] = []
    for (let i = 0; i < 100; i++) {
      const t0 = performance.now()
      layout.scrollTop.value = i * 130
      void layout.visibleRows.value
      void layout.contentHeight.value
      samples.push(performance.now() - t0)
    }
    samples.sort((a, b) => a - b)
    console.log(`[perf] rowLayout.visibleRows chain x100: p50=${p50(samples).toFixed(4)}ms`)
    expect(p50(samples)).toBeLessThan(1)
  })

  it("single WaveformRow mount stays under 8ms p95 (mount cost, happy-dom)", async () => {
    const segments = syntheticSegments()
    // Steady-state mount cost is the scroll-relevant metric: warm up JIT
    // with throwaway mounts, then measure.
    const warmups: ReturnType<typeof mount>[] = []
    for (let i = 0; i < 3; i++) {
      warmups.push(
        mount(WaveformRow, {
          props: {
            rowIndex: 400 + i,
            secondsPerRow: 10,
            top: 0,
            rowHeight: 120,
            duration: REFERENCE_DURATION,
            currentTime: 5.5,
            segments,
            edits: [],
          },
        }),
      )
    }
    warmups.forEach(w => w.unmount())

    const samples: number[] = []
    const wrappers: ReturnType<typeof mount>[] = []
    for (let i = 0; i < 20; i++) {
      const t0 = performance.now()
      const w = mount(WaveformRow, {
        props: {
          rowIndex: i % 350,
          secondsPerRow: 10,
          top: (i % 350) * 130,
          rowHeight: 120,
          duration: REFERENCE_DURATION,
          currentTime: 5.5,
          segments,
          edits: [],
        },
      })
      samples.push(performance.now() - t0)
      wrappers.push(w)
    }
    wrappers.forEach(w => w.unmount())
    samples.sort((a, b) => a - b)
    console.log(`[perf] WaveformRow mount x20 (1167 segs, warmed): p95=${p95(samples).toFixed(3)}ms`)
    expect(p95(samples)).toBeLessThan(8)
  })
})

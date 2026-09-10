/**
 * v3.0.5 R5.16 (M9 顺带表): the wall-clock perf gate is RETIRED.
 *
 * The v3.0.2 M8-3 suite asserted p50/p95 millisecond thresholds
 * (1ms window recompute / 8ms row mount). Those numbers are environment
 * samples, not code properties -- every CI box with a busy scheduler
 * flunked the mount gate, so the suite carried a permanent exemption in
 * the gates script (「唯一失败 = useRowLayout.perf.test.ts」). This
 * rewrite keeps the two things that ARE deterministic:
 *
 *  1. the virtual-window math: for every scrollTop of a full scroll
 *     sweep the window is clamped, contiguous and viewport-shaped (its
 *     span depends only on the viewport + overscan, never on rowCount);
 *  2. the mount path: a WaveformRow at the synthetic_1167 reference
 *     scale mounts, renders its positioned surface and cleans up.
 *
 * Wall-clock telemetry is still LOGGED (console) for eyeballing, but no
 * threshold is asserted. The gates exemption retires with this commit
 * (全绿口径).
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

// Mount-path coverage only: the imperative playhead (clock subscriber)
// and canvas bitmap pipeline are real-device checklist items (M5-5);
// happy-dom skips canvas anyway (getContext -> null).
vi.mock("@/components/waveform/WaveformCanvas.vue", () => ({
  default: { name: "WaveformCanvas", template: "<div data-test='waveform-canvas-stub' />" },
}))
vi.mock("@/components/waveform/PlayheadOverlay.vue", () => ({
  default: { name: "PlayheadOverlay", template: "<div data-test='playhead-stub' />" },
}))

const REFERENCE_DURATION = 3600 // 1h of media at spr=10 -> 360 rows
const ROW_HEIGHT = 120

function makeSeg(id: string, start: number, end: number): Segment {
  return { id, version: 1, type: "subtitle", start, end, text: `t-${id}`, speaker: "" }
}

/** synthetic_1167-shaped track: 1167 segments spread over 1h. */
function syntheticSegments(): Segment[] {
  return Array.from({ length: 1167 }, (_, i) =>
    makeSeg(`seg-${i}`, i * (3600 / 1167), i * (3600 / 1167) + 2.5),
  )
}

describe("M8-3 multi-row virtualization gate (R5.16: deterministic)", () => {
  it("visibleRowWindow: full scroll sweep stays clamped and viewport-shaped (never rowCount-shaped)", () => {
    const rowCount = computeRowCount(REFERENCE_DURATION, 10)
    expect(rowCount).toBe(360)
    const stride = ROW_HEIGHT + 10 // strideOf(rowHeight) adds the 10px gap
    const worstFirst = -1
    const t0 = performance.now()
    let sawFirst = -1
    let maxSpan = 0
    // Simulate a scroll pass through the WHOLE timeline (telemetry only):
    // 200 steps across the full content height (360 rows x 130px stride).
    const fullHeight = rowCount * (ROW_HEIGHT + 10)
    for (let i = 0; i < 200; i++) {
      const scrollTop = Math.round((i * fullHeight) / 199)
      const win = visibleRowWindow(scrollTop, 400, ROW_HEIGHT, rowCount)
      // Deterministic invariants: clamped, contiguous, overscan-bounded.
      expect(win.first).toBeGreaterThanOrEqual(0)
      expect(win.first).toBeLessThanOrEqual(win.last)
      expect(win.last).toBeLessThan(rowCount)
      const span = win.last - win.first + 1
      // viewport rows (ceil(400/120)=4) + 2x ROW_BUFFER (=2) overscan on
      // BOTH edges + stride rounding (fractional first/last offsets):
      // 10 is the exact ceiling (4 + 2*2 + rounding 2).
      expect(span).toBeLessThanOrEqual(Math.ceil(400 / ROW_HEIGHT) + 6)
      maxSpan = Math.max(maxSpan, span)
      sawFirst = Math.max(sawFirst, win.first)
    }
    void stride
    void worstFirst
    const elapsed = performance.now() - t0
    console.log(
      `[perf-telemetry] visibleRowWindow x200 sweep: ${elapsed.toFixed(4)}ms total ` +
        `(no threshold asserted; deepest first=${sawFirst} maxSpan=${maxSpan})`,
    )
    // The sweep actually traversed the row space (not a degenerate loop).
    expect(sawFirst).toBeGreaterThanOrEqual(rowCount - Math.ceil(400 / ROW_HEIGHT) - 2)
  })

  it("composable chain: the visible window tracks scrollTop monotonically", () => {
    const duration = ref(REFERENCE_DURATION)
    const layout = useRowLayout(duration)
    layout.setMode("multi")
    layout.viewportHeight.value = 320
    const t0 = performance.now()
    let prevFirst = -1
    let sawFirst = -1
    for (let i = 0; i < 100; i++) {
      layout.scrollTop.value = i * 130
      const win = layout.visibleRows.value
      void layout.contentHeight.value
      // Deterministic: the window's first row never moves backwards while
      // scrollTop only increases, and stays in range.
      expect(win.first).toBeGreaterThanOrEqual(prevFirst)
      expect(win.first).toBeLessThan(360)
      prevFirst = win.first
      sawFirst = Math.max(sawFirst, win.first)
    }
    const elapsed = performance.now() - t0
    console.log(
      `[perf-telemetry] rowLayout.visibleRows chain x100: ${elapsed.toFixed(4)}ms total ` +
        `(no threshold asserted; deepest first=${sawFirst})`,
    )
    // The chain actually advanced across the sweep.
    expect(sawFirst).toBeGreaterThan(0)
  })

  it("WaveformRow mounts at the 1167-segment scale render positioned surfaces", async () => {
    const segments = syntheticSegments()
    const t0 = performance.now()
    const wrappers: ReturnType<typeof mount>[] = []
    for (let i = 0; i < 20; i++) {
      wrappers.push(
        mount(WaveformRow, {
          props: {
            rowIndex: i % 350,
            secondsPerRow: 10,
            top: (i % 350) * 130,
            rowHeight: ROW_HEIGHT,
            duration: REFERENCE_DURATION,
            currentTime: 5.5,
            segments,
            edits: [],
          },
        }),
      )
    }
    const elapsed = performance.now() - t0
    // Deterministic: every mount produced a positioned, indexed row surface.
    for (const [i, w] of wrappers.entries()) {
      const root = w.find(".waveform-row")
      expect(root.exists()).toBe(true)
      expect(root.attributes("data-row-index")).toBe(String(i % 350))
    }
    console.log(
      `[perf-telemetry] WaveformRow mount x20 (1167 segs): ${elapsed.toFixed(3)}ms total ` +
        "(no threshold asserted)",
    )
    wrappers.forEach(w => w.unmount())
  })
})

/**
 * v3.0.1 M4-3/M4-5: SegmentBlock-specific behavior beyond what the layer
 * tests already anchor (extension styling, trim drag wiring, Alt snap
 * inversion, trim-end payload, trim-disabled read-only mode).
 */
import { describe, expect, it, vi } from "vitest"
import { mount } from "@vue/test-utils"
import { computed, ref } from "vue"
import type { Segment } from "@/types/project"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import SegmentBlock from "./SegmentBlock.vue"

function seg(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "seg-1",
    version: 1,
    type: "subtitle",
    start: 1.0,
    end: 5.0,
    text: "hello",
    speaker: "",
    ...overrides,
  }
}

function createMetrics(getTimeFromX: (x: number) => number = x => x / 10): TimelineMetrics {
  const viewStart = ref(0)
  const viewDuration = ref(10)
  return {
    duration: ref(10),
    viewStart,
    viewDuration,
    viewEnd: computed(() => viewStart.value + viewDuration.value),
    timeToPercent: (time: number) => ((time - viewStart.value) / viewDuration.value) * 100,
    percentToPixels: () => 0,
    getTimeFromX,
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
  }
}

function mountBlock(overrides: {
  seg?: Segment
  trackKind?: "main" | "extension"
  selected?: boolean
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  currentTime?: number
  getTimeFromX?: (x: number) => number
  getTimeFromPointer?: (x: number) => number
  rowStart?: number
  rowEnd?: number
} = {}) {
  const metrics = createMetrics(overrides.getTimeFromX)
  return mount(SegmentBlock, {
    props: {
      seg: overrides.seg ?? seg(),
      leftPercent: 10,
      widthPercent: 40,
      segments: [overrides.seg ?? seg()],
      trackKind: overrides.trackKind,
      selected: overrides.selected,
      updateTime: overrides.updateTime,
      ...(overrides.currentTime !== undefined ? { currentTime: overrides.currentTime } : {}),
      ...(overrides.getTimeFromPointer ? { getTimeFromPointer: overrides.getTimeFromPointer } : {}),
      ...(overrides.rowStart !== undefined ? { rowStart: overrides.rowStart } : {}),
      ...(overrides.rowEnd !== undefined ? { rowEnd: overrides.rowEnd } : {}),
    },
    global: {
      provide: { [TIMELINE_METRICS_KEY as symbol]: metrics },
    },
  })
}

function mockRect(block: { element: Element }) {
  ;(block.element as HTMLElement).getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 200,
    height: 50,
    right: 200,
    bottom: 50,
    x: 0,
    y: 0,
    toJSON: () => {},
  })
}

describe("SegmentBlock rendering", () => {
  it("renders the block with text", () => {
    const wrapper = mountBlock()
    expect(wrapper.find(".rounded.border").exists()).toBe(true)
    expect(wrapper.text()).toContain("hello")
  })

  it("extension blocks wear violet secondary styling", () => {
    const wrapper = mountBlock({ trackKind: "extension" })
    expect(wrapper.find('[class*="bg-violet-200"]').exists()).toBe(true)
  })

  it("main blocks keep EditDecision styling", () => {
    const wrapper = mountBlock()
    expect(wrapper.find('[class*="bg-blue-100"]').exists()).toBe(true)
  })

  it("shows the selection ring when selected", () => {
    const wrapper = mountBlock({ selected: true })
    expect(wrapper.find('[class*="ring-2"]').exists()).toBe(true)
  })
})

describe("SegmentBlock interaction", () => {
  it("emits select-range on body mousedown", async () => {
    const wrapper = mountBlock()
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    await block.trigger("mousedown", { clientX: 100 })
    expect(wrapper.emitted("select-range")![0]).toEqual([1, 5])
  })

  it("emits contextmenu with the segment id", async () => {
    const wrapper = mountBlock()
    const block = wrapper.find(".rounded.border")
    await block.trigger("contextmenu", { clientX: 5, clientY: 5 })
    const calls = wrapper.emitted("contextmenu")!
    expect(calls[0][0]).toBe("seg-1")
  })

  it("emits seek-segment on click", async () => {
    const wrapper = mountBlock()
    await wrapper.find(".rounded.border").trigger("click")
    expect(wrapper.emitted("seek-segment")![0][0]).toMatchObject({ id: "seg-1" })
  })
})

describe("SegmentBlock trim drag (M2-1 clamp + M4-5 Alt)", () => {
  it("forwards clamped trim values to updateTime and emits trim-end", async () => {
    const updateTime = vi.fn()
    const wrapper = mountBlock({ updateTime })
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // clientX 10 -> left edge (<16px); getTimeFromX(10) = 1.0 = seg.start,
    // so drag offset == 0 and raw values map 1:1.
    await block.trigger("mousedown", { clientX: 10 })
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 20 }))
    // raw = 2.0; clamp(2.0, left, seg[1..5]) -> 2.0
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 2.0)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 23 }))
    // raw = 2.3 -> snap 2.3 -> clamp -> 2.3; altKey false
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 2.3)
    const end = wrapper.emitted("trim-end")![0][0]
    expect(end).toMatchObject({ segmentId: "seg-1", field: "start", value: 2.3, altKey: false })
  })

  it("Alt skips snapping but keeps the neighbor clamp", async () => {
    const updateTime = vi.fn()
    const wrapper = mountBlock({
      updateTime,
      getTimeFromX: x => x * 0.1234,
    })
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // mousedown at 8: raw 0.9872 -> offset = 1.0 - 0.9872 = 0.0128
    await block.trigger("mousedown", { clientX: 8 })
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 10, altKey: true }))
    // raw = 1.234 + 0.0128 = 1.2468 -> alt: no snap -> clamp keeps 1.2468
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 1.2468)
    const end = wrapper.emitted("trim-end")![0][0] as { altKey: boolean; value: number }
    expect(end.altKey).toBe(true)
    expect(end.value).toBe(1.2468)
  })

  it("without Alt the same drag snaps to the step grid", async () => {
    const updateTime = vi.fn()
    const wrapper = mountBlock({
      updateTime,
      getTimeFromX: x => x * 0.1234,
    })
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    await block.trigger("mousedown", { clientX: 8 })
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 10, altKey: false }))
    // raw = 1.2468 -> snap -> 1.25
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 1.25)
  })

  it("read-only mode (no updateTime) disables trim drags", async () => {
    const wrapper = mountBlock({})
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // Edge mousedown without updateTime: no trim listeners, and select-range
    // is NOT emitted (edge branch returns before it).
    await block.trigger("mousedown", { clientX: 8 })
    expect(wrapper.emitted("select-range")).toBeFalsy()
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 20 }))
    // No crash, nothing emitted.
    expect(wrapper.emitted("trim-end")).toBeFalsy()
  })

  it("blocks trim beyond the neighbor gap (constrain-first)", async () => {
    const updateTime = vi.fn()
    const s1 = seg({ id: "a", start: 0, end: 2 })
    const s2 = seg({ id: "seg-1", start: 2, end: 5 })
    const wrapper = mountBlock({ updateTime, seg: s2 })
    // give the block both siblings for neighbor bounds
    wrapper.setProps({ segments: [s1, s2] })
    await wrapper.vm.$nextTick()
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // mousedown at 8 on the left edge: offset = 2.0 - 0.8 = 1.2.
    await block.trigger("mousedown", { clientX: 8 })
    // Drag left below the previous segment's end: raw = 0.5 + 1.2 = 1.7
    // -> clamped up to prevEnd (2.0), never overlaps "a".
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 5 }))
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 2)
  })

  // v3.0.2 M3-2 (③): the frozen pointer->time converter (multi-row trim)
  // drives the drag INSTEAD of metrics.getTimeFromX.
  it("trim uses the injected getTimeFromPointer source when provided", async () => {
    const updateTime = vi.fn()
    // Frozen converter: deliberately different from the metrics-based
    // x/10 mapping (a row-recycled drag keeps its original geometry).
    const getTimeFromPointer = vi.fn((x: number) => 3 + x / 100)
    const wrapper = mountBlock({ updateTime, getTimeFromPointer })
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // mousedown at 10: pointerTime = 3.1 -> offset = 1.0 - 3.1 = -2.1
    await block.trigger("mousedown", { clientX: 10 })
    // mousemove at 60: pointerTime = 3.6 -> raw = 3.6 - 2.1 = 1.5
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 60 }))
    expect(getTimeFromPointer).toHaveBeenCalled()
    expect(updateTime).toHaveBeenLastCalledWith("seg-1", "start", 1.5)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 60 }))
  })

  // v3.0.2 M3-2 (②): row boundaries gate HANDLE VISIBILITY only --
  // an out-of-row edge press degrades to a body select.
  it("treats an out-of-row edge press as a body select", async () => {
    const updateTime = vi.fn()
    const wrapper = mountBlock({
      updateTime,
      seg: seg({ id: "seg-1", start: 8, end: 12 }),
      rowStart: 0,
      rowEnd: 10,
    })
    const block = wrapper.find(".rounded.border")
    mockRect(block)
    // Row window [0, 10): the right edge (12) lives outside -> press on the
    // right 16px strip selects instead of trimming.
    await block.trigger("mousedown", { clientX: 195 })
    expect(wrapper.emitted("select-range")).toBeTruthy()
    expect(wrapper.emitted("trim-end")).toBeFalsy()
    // Left edge (8) is inside the row -> trim still engages.
    await block.trigger("mousedown", { clientX: 10 })
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 20 }))
    expect(updateTime).toHaveBeenCalled()
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 20 }))
  })
})

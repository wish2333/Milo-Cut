import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { ref, computed } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"

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

function edit(overrides: Partial<EditDecision> = {}): EditDecision {
  return {
    id: "ed-1",
    start: 1.0,
    end: 5.0,
    action: "delete",
    source: "silence",
    status: "pending",
    priority: 100,
    target_type: "range",
    ...overrides,
  }
}

function createMetrics(): TimelineMetrics {
  const viewStart = ref(0)
  const viewDuration = ref(10)
  return {
    duration: ref(10),
    viewStart,
    viewDuration,
    viewEnd: computed(() => viewStart.value + viewDuration.value),
    timeToPercent: (time: number) => ((time - viewStart.value) / viewDuration.value) * 100,
    percentToPixels: () => 0,
    getTimeFromX: () => 0,
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

function mountLayer(segments: Segment[], edits: EditDecision[] = []) {
  const metrics = createMetrics()
  const wrapper = mount(SegmentBlocksLayer, {
    props: { segments, edits },
    global: {
      provide: {
        [TIMELINE_METRICS_KEY as symbol]: metrics,
      },
    },
  })
  return { wrapper, metrics }
}

describe("SegmentBlocksLayer", () => {
  it("renders segment blocks", () => {
    const { wrapper } = mountLayer([seg()])
    expect(wrapper.find(".rounded.border").exists()).toBe(true)
  })

  it("renders segment text", () => {
    const { wrapper } = mountLayer([seg({ text: "test text" })])
    expect(wrapper.text()).toContain("test text")
  })

  it("applies masked style for delete edits", () => {
    const { wrapper } = mountLayer(
      [seg()],
      [edit({ target_id: "seg-1", action: "delete" })],
    )
    expect(wrapper.find(".bg-red-200").exists()).toBe(true)
  })

  it("applies kept style for keep edits", () => {
    const { wrapper } = mountLayer(
      [seg()],
      [edit({ target_id: "seg-1", action: "keep" })],
    )
    expect(wrapper.find(".bg-green-200").exists()).toBe(true)
  })

  it("applies normal style for subtitle without edits", () => {
    const { wrapper } = mountLayer([seg()])
    expect(wrapper.find(".bg-blue-100").exists()).toBe(true)
  })

  it("applies silence style for silence segments", () => {
    const { wrapper } = mountLayer([seg({ type: "silence" })])
    expect(wrapper.find(".bg-gray-200").exists()).toBe(true)
  })

  it("emits select-range on body click", async () => {
    const { wrapper } = mountLayer([seg()])
    const block = wrapper.find(".rounded.border")
    const element = block.element as HTMLElement
    // Mock getBoundingClientRect for edge detection
    element.getBoundingClientRect = () => ({
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
    await block.trigger("mousedown", { clientX: 100 })
    expect(wrapper.emitted("select-range")).toBeTruthy()
  })

  it("filters segments outside view range", () => {
    const { wrapper, metrics } = mountLayer([seg({ start: 20, end: 25 })])
    metrics.viewStart.value = 0
    metrics.viewDuration.value = 10
    expect(wrapper.findAll(".rounded.border")).toHaveLength(0)
  })

  it("shows segments partially in view", () => {
    const { wrapper, metrics } = mountLayer([seg({ start: 8, end: 12 })])
    metrics.viewStart.value = 0
    metrics.viewDuration.value = 10
    expect(wrapper.findAll(".rounded.border")).toHaveLength(1)
  })
})

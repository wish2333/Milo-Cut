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

function mountLayer(
  segments: Segment[],
  edits: EditDecision[] = [],
  currentTime?: number,
) {
  const metrics = createMetrics()
  const wrapper = mount(SegmentBlocksLayer, {
    props: { segments, edits, ...(currentTime !== undefined ? { currentTime } : {}) },
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
    expect(wrapper.find('[class*="bg-red-200"]').exists()).toBe(true)
  })

  it("applies kept style for keep edits", () => {
    const { wrapper } = mountLayer(
      [seg()],
      [edit({ target_id: "seg-1", action: "keep" })],
    )
    expect(wrapper.find('[class*="bg-green-200"]').exists()).toBe(true)
  })

  it("applies normal style for subtitle without edits", () => {
    const { wrapper } = mountLayer([seg()])
    expect(wrapper.find('[class*="bg-blue-100"]').exists()).toBe(true)
  })

  it("applies silence style for silence segments", () => {
    const { wrapper } = mountLayer([seg({ type: "silence" })])
    expect(wrapper.find('[class*="bg-gray-200"]').exists()).toBe(true)
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

  // v3.0.0 P4-1: word highlight while hovering (pure display)
  const WORDY = seg({
    id: "seg-w",
    text: "大家好",
    start: 1.0,
    end: 2.0,
    words: [
      { word: "大", start: 1.0, end: 1.5, confidence: 1 },
      { word: "家", start: 1.5, end: 2.0, confidence: 1 },
    ],
  })

  async function hoverBlock(wrapper: ReturnType<typeof mountLayer>["wrapper"]) {
    const block = wrapper.find(".rounded.border")
    const element = block.element as HTMLElement
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
    await block.trigger("mousemove", { clientX: 100 })
  }

  it("highlights the word at playback time while hovering", async () => {
    const { wrapper } = mountLayer([WORDY], [], 1.2)
    await hoverBlock(wrapper)
    const spans = wrapper.findAll("span span")
    expect(spans).toHaveLength(2)
    expect(spans[0].classes().join(" ")).toContain("bg-blue-500")
    expect(spans[1].classes().join(" ")).not.toContain("bg-blue-500")
  })

  it("clamps out-of-range playback time to the hovered segment", async () => {
    const { wrapper } = mountLayer([WORDY], [], 9.9)
    await hoverBlock(wrapper)
    // Clamped to seg.end (2.0) -> end-exclusive -> no word matched, the
    // block falls back to the plain-text branch (no word spans at all).
    expect(wrapper.findAll("span span").length).toBe(0)
    expect(wrapper.text()).toContain("大家好")
  })

  it("clears the highlight on mouse leave", async () => {
    const { wrapper } = mountLayer([WORDY], [], 1.2)
    const block = wrapper.find(".rounded.border")
    await hoverBlock(wrapper)
    expect(wrapper.findAll("span span").length).toBe(2)
    await block.trigger("mouseleave")
    expect(wrapper.findAll("span span").length).toBe(0)
  })

  it("renders plain text for segments without words", async () => {
    const { wrapper } = mountLayer([seg({ id: "plain", text: "no words" })], [], 1.2)
    await hoverBlock(wrapper)
    expect(wrapper.findAll("span span").length).toBe(0)
    expect(wrapper.text()).toContain("no words")
  })
})

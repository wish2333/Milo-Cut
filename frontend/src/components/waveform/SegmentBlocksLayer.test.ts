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

// ------------------------------------------------------------------
// v3.0.2 M5-3: emptyAreaMode dual semantics
// ------------------------------------------------------------------

describe("SegmentBlocksLayer emptyAreaMode (M5-3)", () => {
  function mountWithMode(mode?: "add" | "seek", getTimeFromX?: (x: number) => number) {
    const metrics = createMetrics()
    if (getTimeFromX) metrics.getTimeFromX = getTimeFromX
    const wrapper = mount(SegmentBlocksLayer, {
      props: { segments: [], edits: [], ...(mode ? { emptyAreaMode: mode } : {}) },
      global: { provide: { [TIMELINE_METRICS_KEY as symbol]: metrics } },
    })
    return wrapper
  }

  function emptyMousedown(wrapper: ReturnType<typeof mountWithMode>, init: Record<string, number | boolean> = {}) {
    return wrapper.find("div[tabindex='0']").trigger("mousedown", { clientX: 300, ...init })
  }

  it("add mode (default) keeps the legacy empty-click add-segment", async () => {
    for (const mode of [undefined, "add"] as const) {
      const wrapper = mountWithMode(mode)
      await emptyMousedown(wrapper)
      expect(wrapper.emitted("add-segment")?.length).toBe(1)
      expect(wrapper.emitted("empty-press")).toBeFalsy()
      wrapper.unmount()
    }
  })

  it("seek mode: empty press forwards bounded time + modifiers, never add-segment", async () => {
    const wrapper = mountWithMode("seek", x => (x / 600) * 10)
    await emptyMousedown(wrapper, { shiftKey: true })
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    const presses = wrapper.emitted("empty-press") ?? []
    expect(presses.length).toBe(1)
    const payload = presses[0][0] as {
      clientX: number
      clientY: number
      ctrlKey: boolean
      shiftKey: boolean
      time: number
    }
    expect(payload.clientX).toBe(300)
    expect(payload.time).toBe(5) // bounded row time (300/600 * 10)
    expect(payload.shiftKey).toBe(true)
    expect(payload.ctrlKey).toBe(false)
    // Modifiers pass through for the editor's gesture routing.
    await emptyMousedown(wrapper, { ctrlKey: true })
    expect(((wrapper.emitted("empty-press") ?? [])[1]?.[0] as { ctrlKey: boolean }).ctrlKey).toBe(true)
    wrapper.unmount()
  })

  it("seek mode: empty double click asks for play/pause; add mode stays silent", async () => {
    const seekWrapper = mountWithMode("seek")
    await seekWrapper.find("div[tabindex='0']").trigger("dblclick")
    expect(seekWrapper.emitted("empty-double-click")?.length).toBe(1)
    seekWrapper.unmount()

    const addWrapper = mountWithMode("add")
    await addWrapper.find("div[tabindex='0']").trigger("dblclick")
    expect(addWrapper.emitted("empty-double-click")).toBeFalsy()
    addWrapper.unmount()
  })
})

describe("SegmentBlocksLayer context menu kbd badges (R9.4)", () => {
  it("renders a Del badge on the delete item and none on split items", async () => {
    const { wrapper } = mountLayer([seg()])
    await wrapper.find(".rounded.border").trigger("contextmenu")
    // The menu teleports to body: query the document, not the wrapper.
    const menu = document.body.querySelector(".fixed.z-dropdown")
    expect(menu).not.toBeNull()
    const badges = menu!.querySelectorAll("kbd")
    expect(badges.length).toBe(1)
    expect(badges[0].textContent).toBe("Del")
    expect(badges[0].getAttribute("data-test")).toBe("menu-kbd-delete")
    // Split items have no invented shortcuts: text only.
    expect(menu!.textContent).toContain("按时间指针分割")
    expect(menu!.textContent).toContain("从中点分割")
    wrapper.unmount()
    expect(document.body.querySelector(".fixed.z-dropdown")).toBeNull()
  })
})

describe("SegmentBlocksLayer fillContainer (smoke fix)", () => {
  it("default keeps the badge clearance; fillContainer fills its parent", () => {
    const def = mountLayer([seg()])
    const defRoot = def.wrapper.find("div[tabindex='0']")
    expect(defRoot.classes()).toContain("top-6")
    expect(defRoot.classes()).toContain("bottom-0")
    def.wrapper.unmount()

    const metrics = createMetrics()
    const wrapper = mount(SegmentBlocksLayer, {
      props: { segments: [], edits: [], fillContainer: true },
      global: { provide: { [TIMELINE_METRICS_KEY as symbol]: metrics } },
    })
    const root = wrapper.find("div[tabindex='0']")
    expect(root.classes()).toContain("inset-0")
    expect(root.classes()).not.toContain("top-6")
    wrapper.unmount()
  })
})

describe("SegmentBlocksLayer menu re-open (smoke fix #3)", () => {
  it("right-clicking another block swaps to the NEW menu (no shared-ref wipe)", async () => {
    const { wrapper } = mountLayer([
      seg({ id: "s1", start: 0.5, end: 2.0 }),
      seg({ id: "s2", start: 6.0, end: 8.0 }),
    ])
    const blocks = wrapper.findAll(".rounded.border")
    await blocks[0].trigger("contextmenu")
    expect(document.body.querySelector(".fixed.z-dropdown")).not.toBeNull()
    // Right-click closes menu #1 AND must open menu #2 for the new block.
    await blocks[1].trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")
    expect(menu).not.toBeNull()
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.4 M4-2 (P3-6): emptyAreaMode "range" -- the basic direct-child
// press channel (payload shape = empty-press; branch BEFORE "seek").
// ------------------------------------------------------------------

describe("SegmentBlocksLayer range mode (M4-2)", () => {
  it("range mode: empty press forwards range-press (bounded time + modifiers), never add-segment/empty-press; dblclick stays silent", async () => {
    const metrics = createMetrics()
    metrics.getTimeFromX = x => (x / 600) * 10
    const wrapper = mount(SegmentBlocksLayer, {
      props: { segments: [], edits: [], emptyAreaMode: "range" },
      global: { provide: { [TIMELINE_METRICS_KEY as symbol]: metrics } },
    })
    const empty = wrapper.find("div[tabindex='0']")
    await empty.trigger("mousedown", { clientX: 300, clientY: 20, shiftKey: true })
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    expect(wrapper.emitted("empty-press")).toBeFalsy()
    const presses = wrapper.emitted("range-press") ?? []
    expect(presses.length).toBe(1)
    expect(presses[0][0]).toEqual({
      clientX: 300,
      clientY: 20,
      ctrlKey: false,
      shiftKey: true,
      time: 5, // bounded row time (300/600 * 10)
    })
    // Ctrl passes through too (editor-side routing keeps modifiers).
    await empty.trigger("mousedown", { clientX: 120, clientY: 20, ctrlKey: true })
    expect(((wrapper.emitted("range-press") ?? [])[1]?.[0] as { ctrlKey: boolean; time: number }).ctrlKey).toBe(true)
    expect(((wrapper.emitted("range-press") ?? [])[1]?.[0] as { ctrlKey: boolean; time: number }).time).toBe(2)
    // Double click stays a play/pause SEEK-mode affordance only.
    await empty.trigger("dblclick")
    expect(wrapper.emitted("empty-double-click")).toBeFalsy()
    wrapper.unmount()
  })
})

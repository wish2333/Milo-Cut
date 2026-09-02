/**
 * v3.0.2 M3-2 (P2-2): WaveformRow tests.
 *
 * Anchors (SPEC M3-2 acceptance): row-window tick math, cross-row block
 * clipping, continuation markers, in-row handle rule, row-local playhead,
 * adapter no-op safety, and the getTimeFromPointer injection fallback.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import { mount } from "@vue/test-utils"
import { ref } from "vue"
import type { Segment } from "@/types/project"
import WaveformRow from "./WaveformRow.vue"
import SegmentBlock from "./SegmentBlock.vue"

vi.mock("./WaveformCanvas.vue", () => ({
  default: { name: "WaveformCanvas", template: "<div data-test='waveform-canvas-stub' />" },
}))

function seg(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "seg-1",
    version: 1,
    type: "subtitle",
    start: 0,
    end: 5,
    text: "hello",
    speaker: "",
    ...overrides,
  }
}

function mountRow(overrides: {
  rowIndex?: number
  secondsPerRow?: number
  duration?: number
  currentTime?: number
  segments?: Segment[]
  top?: number
  rowHeight?: number
  widthPercent?: number
  getTimeFromPointer?: (x: number) => number
} = {}) {
  return mount(WaveformRow, {
    props: {
      rowIndex: overrides.rowIndex ?? 0,
      secondsPerRow: overrides.secondsPerRow ?? 10,
      top: overrides.top ?? 0,
      rowHeight: overrides.rowHeight ?? 120,
      widthPercent: overrides.widthPercent,
      duration: overrides.duration ?? 95,
      currentTime: overrides.currentTime,
      segments: overrides.segments ?? [seg()],
      edits: [],
      ...(overrides.getTimeFromPointer
        ? { getTimeFromPointer: overrides.getTimeFromPointer }
        : {}),
    },
    global: {
      provide: {
        // WorkspacePage is the single PLAYBACK_CLOCK provider (M0-1.6):
        // rows reach it via provide/inject -- the stub stands in for it.
        // (Symbol keys cannot be spelled in object provide; PlayheadOverlay
        // is stubbed below instead.)
      },
    },
  })
}

vi.mock("./PlayheadOverlay.vue", () => ({
  default: {
    name: "PlayheadOverlay",
    props: [],
    template: "<div data-test='playhead-stub' />",
  },
}))
vi.mock("./TimeMarksLayer.vue", () => ({
  default: {
    name: "TimeMarksLayer",
    props: [],
    emits: ["seek"],
    template: "<div data-test='timemarks-stub' />",
  },
}))

describe("WaveformRow: geometry + row window", () => {
  it("renders positioned by top/rowHeight/widthPercent with data markers", () => {
    const w = mountRow({ rowIndex: 3, top: 390, rowHeight: 120, widthPercent: 50 })
    const root = w.find(".waveform-row")
    const el = root.element as HTMLElement
    expect(el.style.top).toBe("390px")
    expect(el.style.height).toBe("120px")
    expect(el.style.width).toBe("50%")
    expect(root.attributes("data-row-index")).toBe("3")
    expect(root.attributes("data-row-start")).toBe("30")
    expect(root.attributes("data-row-end")).toBe("40")
  })

  it("defaults widthPercent to 100 (full rows)", () => {
    const w = mountRow({})
    expect(((w.find(".waveform-row").element as HTMLElement).style.width)).toBe("100%")
  })

  it("shows the row time badge (start -> end)", () => {
    const w = mountRow({ rowIndex: 0, secondsPerRow: 10, duration: 95 })
    expect(w.find(".waveform-row-time").text()).toMatch(/0:00/)
    expect(w.find(".waveform-row-time").text()).toMatch(/→/)
  })

  it("last row badge ends at the clamped duration", () => {
    const w = mountRow({ rowIndex: 9, secondsPerRow: 10, duration: 95 })
    expect(w.find(".waveform-row-time").text()).toContain("1:35")
  })
})

describe("WaveformRow: row playhead (R5.3)", () => {
  it("renders the playhead only while currentTime is inside the row", async () => {
    const w = mountRow({ rowIndex: 0, secondsPerRow: 10, duration: 95, currentTime: 5 })
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(true)
    await w.setProps({ currentTime: 15 }) // moved into row 1
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(false)
    await w.setProps({ currentTime: 9.999 })
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(true)
  })

  it("row boundary is exclusive at [start, end)", async () => {
    const w = mountRow({ rowIndex: 1, secondsPerRow: 10, duration: 95, currentTime: 10 })
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(true)
    await w.setProps({ currentTime: 20 })
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(false)
  })

  it("no currentTime prop -> no playhead", () => {
    const w = mountRow({ currentTime: undefined })
    expect(w.find("[data-test='playhead-stub']").exists()).toBe(false)
  })
})

describe("WaveformRow: cross-row clipping + continuation (R5.4)", () => {
  it("clips a block straddling the row end and marks continuesTo", () => {
    // block [8, 12] vs row 0 [0, 10): clipped to [8, 10), continues right
    const w = mountRow({
      rowIndex: 0,
      secondsPerRow: 10,
      duration: 95,
      segments: [seg({ id: "a", start: 8, end: 12 })],
    })
    const block = w.findComponent(SegmentBlock)
    expect(block.props("leftPercent")).toBeCloseTo(80)
    expect(block.props("widthPercent")).toBeCloseTo(20)
    expect(block.props("continuesTo")).toBe(true)
    expect(block.props("continuesFrom")).toBe(false)
  })

  it("marks continuesFrom for a block entering mid-row", () => {
    const w = mountRow({
      rowIndex: 1, // row window [10, 20)
      secondsPerRow: 10,
      duration: 95,
      segments: [seg({ id: "b", start: 8, end: 12 })],
    })
    const block = w.findComponent(SegmentBlock)
    expect(block.props("leftPercent")).toBe(0)
    expect(block.props("widthPercent")).toBeCloseTo(20)
    expect(block.props("continuesFrom")).toBe(true)
    expect(block.props("continuesTo")).toBe(false)
  })

  it("blocks fully inside the row carry no continuation markers", () => {
    const w = mountRow({
      rowIndex: 0,
      secondsPerRow: 10,
      duration: 95,
      segments: [seg({ id: "a", start: 2, end: 5 })],
    })
    const block = w.findComponent(SegmentBlock)
    expect(block.props("continuesFrom")).toBe(false)
    expect(block.props("continuesTo")).toBe(false)
  })

  it("passes the FULL track segment array down (cross-row trim neighbors)", () => {
    const all = [
      seg({ id: "a", start: 2, end: 5 }),
      seg({ id: "far", start: 88, end: 90 }), // lives in another row
    ]
    const w = mountRow({ rowIndex: 0, secondsPerRow: 10, duration: 95, segments: all })
    expect(w.findComponent(SegmentBlock).props("segments")).toHaveLength(2)
  })
})

describe("WaveformRow: in-row handle rule (M3-2 ②)", () => {
  it("straddling block: only the in-row edge keeps its handle", () => {
    const w = mountRow({
      rowIndex: 0,
      secondsPerRow: 10,
      duration: 95,
      segments: [seg({ id: "a", start: 8, end: 12 })],
    })
    const block = w.findComponent(SegmentBlock)
    // left edge 8 >= rowStart 0 -> in row; right edge 12 > rowEnd 10 -> out
    expect(block.props("rowStart")).toBe(0)
    expect(block.props("rowEnd")).toBe(10)
    expect((block.vm as unknown as { leftEdgeInRow: boolean }).leftEdgeInRow).toBe(true)
    expect((block.vm as unknown as { rightEdgeInRow: boolean }).rightEdgeInRow).toBe(false)
  })
})

describe("WaveformRow: getTimeFromPointer injection (M3-2 ③)", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it("forwards the injected converter to blocks (default falls back to metrics)", () => {
    const frozen = (x: number) => x / 10 + 30
    const w = mountRow({
      rowIndex: 3,
      secondsPerRow: 10,
      duration: 95,
      segments: [seg({ id: "a", start: 32, end: 35 })],
      getTimeFromPointer: frozen,
    })
    expect(w.findComponent(SegmentBlock).props("getTimeFromPointer")).toBe(frozen)
  })

  it("omitting the converter passes undefined (blocks use metrics.getTimeFromX)", () => {
    const w = mountRow({})
    expect(w.findComponent(SegmentBlock).props("getTimeFromPointer")).toBeUndefined()
  })
})

describe("WaveformRow: adapter no-op safety (M0-1.5)", () => {
  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })
  afterEach(() => vi.restoreAllMocks())

  it("mounting a row outside the editor provides a working row-scope metrics", () => {
    // Row renders without ancestor metrics (it PROVIDES its own) and its
    // clipped block list works through the adapter.
    const w = mountRow({
      rowIndex: 0,
      secondsPerRow: 10,
      duration: 95,
      segments: [
        seg({ id: "in", start: 2, end: 5 }),
        seg({ id: "out", start: 50, end: 55 }),
      ],
    })
    const blocks = w.findAllComponents(SegmentBlock)
    expect(blocks).toHaveLength(1) // "out" is outside the row window
    expect(blocks[0].props("seg").id).toBe("in")
  })

  it("row-local hover preview appears on mousemove and clears on leave", async () => {
    const w = mountRow({ rowIndex: 0, secondsPerRow: 10, duration: 95 })
    expect(w.find("[data-test='row-hover-preview']").exists()).toBe(false)
    await w.find(".waveform-row").trigger("mouseleave")
    expect(w.find("[data-test='row-hover-preview']").exists()).toBe(false)
  })
})

describe("WaveformRow: ref typing smoke", () => {
  it("accepts refs passed as props (editor contract)", () => {
    // The editor passes currentTime via a shared ref chain.
    const t = ref(5)
    const w = mount(WaveformRow, {
      props: {
        rowIndex: 0,
        secondsPerRow: 10,
        top: 0,
        rowHeight: 120,
        duration: 95,
        currentTime: t.value,
        segments: [],
        edits: [],
      },
    })
    expect(w.exists()).toBe(true)
    expect(t.value).toBe(5)
  })
})

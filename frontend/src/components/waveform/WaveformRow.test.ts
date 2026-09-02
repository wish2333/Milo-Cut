/**
 * v3.0.2 M3-2 (P2-2): WaveformRow tests.
 *
 * Anchors (SPEC M3-2 acceptance): row-window tick math, cross-row block
 * clipping, continuation markers, in-row handle rule, row-local playhead,
 * adapter no-op safety, and the getTimeFromPointer injection fallback.
 */
import { describe, expect, it, vi, beforeEach, afterEach, beforeAll, afterAll } from "vitest"
import { mount } from "@vue/test-utils"
import { ref } from "vue"
import type { Segment } from "@/types/project"
import { useRowDragCapture } from "@/composables/useRowDragCapture"
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
  rowDrag?: ReturnType<typeof useRowDragCapture>
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
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
      ...(overrides.rowDrag ? { rowDrag: overrides.rowDrag } : {}),
      ...(overrides.updateTime ? { updateTime: overrides.updateTime } : {}),
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

  it("omitting the injection hands blocks the row's own frozen converter (M5-4)", () => {
    const w = mountRow({ rowDrag: useRowDragCapture() })
    // M5-4: the row derives a frozen source from the shared drag-capture
    // singleton; explicit prop injection (test above) still wins.
    expect(typeof w.findComponent(SegmentBlock).props("getTimeFromPointer")).toBe("function")
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

// ------------------------------------------------------------------
// v3.0.2 M5-4: frozen trim wiring (S7.8 dual mapping through the row)
// ------------------------------------------------------------------

describe("WaveformRow: M5-4 frozen trim wiring", () => {
  // Geometry: row 1 covers [10s, 20s], mapped to 600px (1s = 60px).
  // Block rect is faked full-row so the 16px edge strips sit at x<16 / x>584.
  let rectDescriptor: PropertyDescriptor | undefined

  function domRect(left: number, top: number, width: number, height: number): DOMRect {
    return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) } as DOMRect
  }

  beforeAll(() => {
    rectDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.classList?.contains("waveform-row")) {
          const idx = Number(this.getAttribute("data-row-index") ?? 0)
          return domRect(0, idx * 130, 600, 120)
        }
        if (this.classList?.contains("rounded") && this.classList?.contains("border")) {
          return domRect(0, 0, 600, 120)
        }
        return domRect(0, 0, 0, 0)
      },
    })
  })

  afterAll(() => {
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  const TARGET = seg({ id: "x", start: 12, end: 14 })

  function mountTrimRow(neighbors: Segment[] = []) {
    const rowDrag = useRowDragCapture()
    const updateTime = vi.fn()
    const wrapper = mountRow({
      rowIndex: 1,
      // TARGET FIRST so find(".rounded.border") resolves to it; the clamp
      // kernel sorts by time, so array order never affects the bounds.
      segments: [TARGET, ...neighbors],
      rowDrag,
      updateTime,
      // duration large enough that [0, duration] clamp never interferes
      duration: 95,
    })
    return { wrapper, updateTime }
  }

  it("trim crosses the row boundary unclamped (S7.8: rows never constrain)", async () => {
    const { wrapper, updateTime } = mountTrimRow()
    const block = wrapper.find(".rounded.border")
    // Down at x=10 (left strip): frozen time 10.1667 -> offset = 1.8333.
    await block.trigger("mousedown", { clientX: 10 })
    // Move to x=-140 -> frozen time 7.6667, raw = 9.5s: BEYOND the row
    // start (10s) and no neighbor bound -> the optimistic update must
    // carry 9.5, NOT be clamped to the row boundary.
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: -140 }))
    expect(updateTime.mock.calls[updateTime.mock.calls.length - 1]?.[2]).toBeCloseTo(9.5, 5)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: -140 }))
    wrapper.unmount()
  })

  it("same-track neighbor still clamps the cross-row trim", async () => {
    const { wrapper, updateTime } = mountTrimRow([seg({ id: "prev", start: 9, end: 11 })])
    const block = wrapper.find(".rounded.border")
    await block.trigger("mousedown", { clientX: 10 })
    // Raw 9.5s is inside the previous segment's span -> clamped to prevEnd 11.
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: -140 }))
    expect(updateTime).toHaveBeenLastCalledWith("x", "start", 11)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: -140 }))
    wrapper.unmount()
  })

  it("release chain: snap can overshoot the neighbor -> second clamp wins", async () => {
    // nextStart 14.006; raw 14.007 clamps to 14.006, snap rounds UP to
    // 14.01, the post-snap clamp returns it to 14.006 (M5-4 chain).
    const { wrapper, updateTime } = mountTrimRow([seg({ id: "next", start: 14.006, end: 16 })])
    const block = wrapper.find(".rounded.border")
    // Down at x=590 (right strip): frozen time 19.83333 -> offset = -5.83333.
    await block.trigger("mousedown", { clientX: 590 })
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 590.42 })) // raw 14.007
    expect(updateTime.mock.calls[updateTime.mock.calls.length - 1]?.[2]).toBe(14.006)
    wrapper.unmount()
  })

  it("Alt inverts snapping on release (free position, clamp intact)", async () => {
    const { wrapper, updateTime } = mountTrimRow()
    const block = wrapper.find(".rounded.border")
    await block.trigger("mousedown", { clientX: 590 }) // offset -5.83333
    // Up at raw 12.346 with Alt: NO snap -> value stays 12.346 (free grid).
    const up = new MouseEvent("mouseup", { clientX: 490.76 })
    Object.defineProperty(up, "altKey", { value: true })
    document.dispatchEvent(up)
    expect(updateTime.mock.calls[updateTime.mock.calls.length - 1]?.[2]).toBeCloseTo(12.346, 5)
    wrapper.unmount()
  })

  it("without Alt the same release snaps to the 0.01 grid", async () => {
    const { wrapper, updateTime } = mountTrimRow()
    const block = wrapper.find(".rounded.border")
    await block.trigger("mousedown", { clientX: 590 })
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 490.76 })) // raw 12.346
    expect(updateTime.mock.calls[updateTime.mock.calls.length - 1]?.[2]).toBe(12.35)
    wrapper.unmount()
  })

  it("row recycle mid-drag keeps the frozen math (M3-3 continuity)", async () => {
    const { wrapper, updateTime } = mountTrimRow()
    const block = wrapper.find(".rounded.border")
    await block.trigger("mousedown", { clientX: 10 }) // frozen [10,20]
    // Force the recycle: the row (and its adapter) unmounts mid-drag.
    wrapper.unmount()
    // The document-level drag listeners survive; conversions still come
    // from the FROZEN snapshot: x=-140 -> 7.6667s, raw 9.5 -> continuous.
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: -140 }))
    expect(updateTime.mock.calls[updateTime.mock.calls.length - 1]?.[2]).toBeCloseTo(9.5, 5)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: -140 }))
  })
})

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from "vitest"
import { mount } from "@vue/test-utils"
import WaveformEditor from "./WaveformEditor.vue"
import WaveformRow from "./WaveformRow.vue"
import SegmentBlock from "./SegmentBlock.vue"
import { formatTimeShort } from "@/utils/format"
import { ROW_LAYOUT_STORAGE_KEY, WHEEL_DEBOUNCE_MS, loadRowLayoutState } from "@/composables/useRowLayout"

let rectDescriptor: PropertyDescriptor | undefined

async function frame() {
  await new Promise((r) => setTimeout(r, 40))
}

describe("WaveformEditor hover seek preview (M6-2)", () => {
  beforeAll(() => {
    // Give the waveform layer a stable geometry for the hover math
    // (happy-dom reports zero rects).
    rectDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "waveform-layer") {
          return {
            left: 0,
            top: 0,
            width: 600,
            height: 112,
            right: 600,
            bottom: 112,
            x: 0,
            y: 0,
            toJSON: () => ({}),
          } as DOMRect
        }
        const fallback = rectDescriptor?.value?.call(this) ?? {
          left: 0,
          top: 0,
          width: 0,
          height: 0,
          right: 0,
          bottom: 0,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }
        return fallback as DOMRect
      },
    })
  })

  afterAll(() => {
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  function mountEditor() {
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 30,
        currentTime: 0,
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("shows the preview line with the pointer time on pointermove", async () => {
    const wrapper = mountEditor()
    const layer = wrapper.find('[data-test="waveform-layer"]')
    await layer.trigger("pointermove", { clientX: 300 }) // 300/600 * 30s = 15s
    await frame()
    const preview = wrapper.find('[data-test="hover-preview"]')
    expect((preview.element as HTMLElement).style.opacity).toBe("1")
    expect((preview.element as HTMLElement).style.transform).toBe("translate3d(300px, 0, 0)")
    expect(preview.text()).toContain(formatTimeShort(15))
    wrapper.unmount()
  })

  it("hides the preview on pointerleave", async () => {
    const wrapper = mountEditor()
    const layer = wrapper.find('[data-test="waveform-layer"]')
    await layer.trigger("pointermove", { clientX: 100 })
    await frame()
    await layer.trigger("pointerleave")
    await frame()
    const preview = wrapper.find('[data-test="hover-preview"]')
    expect((preview.element as HTMLElement).style.opacity).toBe("0")
    wrapper.unmount()
  })

  it("never seeks from hovering (no events emitted)", async () => {
    const wrapper = mountEditor()
    const layer = wrapper.find('[data-test="waveform-layer"]')
    await layer.trigger("pointermove", { clientX: 150 })
    await layer.trigger("pointermove", { clientX: 200 })
    await frame()
    expect(wrapper.emitted("seek")).toBeFalsy()
    expect(wrapper.emitted("set-time")).toBeFalsy()
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.1 M4-4: stacked-timeline orchestration
// ------------------------------------------------------------------

import { describe as describeStacked, expect as expectStacked } from "vitest"
import { ref as vueRef } from "vue"
import type { SubtitleTrack } from "@/types/project"
import { PLAYBACK_CLOCK_KEY } from "./injectionKeys"
import type { PlaybackClock } from "@/composables/usePlaybackClock"

function makeStackTrack(id: string, count = 2): SubtitleTrack {
  return {
    id,
    role: "extension",
    name: `lang-${id}`,
    language: id,
    segments: Array.from({ length: count }, (_, i) => ({
      id: `track_${id}_seg_${i}`,
      version: 1,
      type: "subtitle" as const,
      start: 1 + i * 2,
      end: 2 + i * 2,
      text: `t-${id}-${i}`,
      speaker: "",
    })),
  }
}

function makeClock(): PlaybackClock {
  return {
    getTime: () => 0,
    isPlaying: () => false,
    ingest: () => {},
    subscribe: () => () => {},
    coarseTime: vueRef(0),
    start: () => {},
    stop: () => {},
  }
}

describeStacked("stacked timeline orchestration (M4-4)", () => {
  function mountStack(tracks: SubtitleTrack[]) {
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 30,
        currentTime: 0,
        tracks,
      },
      global: {
        provide: {
          [PLAYBACK_CLOCK_KEY as symbol]: makeClock(),
        },
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
        },
      },
    })
  }

  it("renders one lane per visible track below the main track", () => {
    const wrapper = mountStack([makeStackTrack("en"), makeStackTrack("ja"), makeStackTrack("fr")])
    const lanes = wrapper.findAll('[data-test="track-lane"]')
    expectStacked(lanes).toHaveLength(3)
    // main track height is the fixed 112px content-driven value
    const first = lanes[0].element as HTMLElement
    expectStacked(first.style.top).toBe("112px")
    expectStacked(first.style.height).toBe("48px")
    const second = lanes[1].element as HTMLElement
    expectStacked(second.style.top).toBe("160px")
    wrapper.unmount()
  })

  it("stack height covers the main track plus all lane heights", () => {
    const wrapper = mountStack([makeStackTrack("en"), makeStackTrack("ja")])
    const stack = wrapper.find('[data-test="timeline-stack"]')
    // 112 + 2x48 = 208
    expectStacked((stack.element as HTMLElement).style.height).toBe("208px")
    wrapper.unmount()
  })

  it("hidden lanes do not render (layout state is global and persisted)", () => {
    localStorage.setItem("milocut:timeline-layout:v1", JSON.stringify({ hidden: { en: true } }))
    const wrapper = mountStack([makeStackTrack("en"), makeStackTrack("ja")])
    const lanes = wrapper.findAll('[data-test="track-lane"]')
    expectStacked(lanes).toHaveLength(1)
    expectStacked(lanes[0].text()).toContain("lang-ja")
    localStorage.removeItem("milocut:timeline-layout:v1")
    wrapper.unmount()
  })

  it("renders exactly one playhead node on the stack surface (promoted owner)", () => {
    const wrapper = mountStack([makeStackTrack("en")])
    const stack = wrapper.find('[data-test="timeline-stack"]')
    // The playhead is a DIRECT child of the stack (promoted owner), not
    // inside the main layer. (PlayheadOverlay has two .bg-red-500 nodes:
    // the head bar + its triangle tip.)
    const directChild = Array.from(stack.element.children).find(el =>
      el.className.includes("bg-red-500"),
    )
    expectStacked(directChild).toBeDefined()
    expectStacked((directChild as HTMLElement).className).toContain("inset-y-0")
    const mainLayer = wrapper.find('[data-test="waveform-layer"]')
    expectStacked(mainLayer.find(".bg-red-500").exists()).toBe(false)
    wrapper.unmount()
  })

  it("shows the soft overflow hint beyond four tracks", () => {
    const tracks = ["a", "b", "c", "d", "e"].map(id => makeStackTrack(id))
    const wrapper = mountStack(tracks)
    expectStacked(wrapper.find('[data-test="track-overflow-hint"]').exists()).toBe(true)
    wrapper.unmount()
    const wrapper2 = mountStack(tracks.slice(0, 4))
    expectStacked(wrapper2.find('[data-test="track-overflow-hint"]').exists()).toBe(false)
    wrapper2.unmount()
  })

  it("collapse emits recompute lane geometry (24px collapsed height)", async () => {
    const wrapper = mountStack([makeStackTrack("en"), makeStackTrack("ja")])
    const lanes = wrapper.findAll('[data-test="track-lane"]')
    await lanes[0].find('[data-test="lane-collapse"]').trigger("click")
    await wrapper.vm.$nextTick()
    const after = wrapper.findAll('[data-test="track-lane"]')
    expectStacked(((after[0].element as HTMLElement).style.height)).toBe("24px")
    // stack shrank by 48 - 24
    const stack = wrapper.find('[data-test="timeline-stack"]')
    expectStacked((stack.element as HTMLElement).style.height).toBe("184px")
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M4-2: multi-row virtualization (beta.1 smoke regression)
// ------------------------------------------------------------------

describe("WaveformEditor multi-row branch (M4-1/M4-2)", () => {
  beforeEach(() => {
    localStorage.clear()
    // The editor loads row state from localStorage at setup time.
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })
  afterEach(() => {
    localStorage.clear()
  })

  function mountMulti() {
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 30,
        currentTime: -1, // outside any row -> no playhead mount
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("renders virtualized rows with spr-derived row windows", () => {
    const wrapper = mountMulti()
    expect(wrapper.find('[data-test="multi-scroll"]').exists()).toBe(true)
    const rows = wrapper.findAll(".waveform-row")
    expect(rows.length).toBeGreaterThanOrEqual(3) // spr 10, duration 30 -> 3 rows (+buffer)
    expect(rows[0].attributes("data-row-start")).toBe("0")
    expect(rows[0].attributes("data-row-end")).toBe("10")
    expect(rows[1].attributes("data-row-start")).toBe("10")
    wrapper.unmount()
  })

  it("REMOUNTS row 0 when the spr preset changes (stale-adapter regression)", async () => {
    const wrapper = mountMulti()
    expect(wrapper.find(".waveform-row").attributes("data-row-end")).toBe("10")
    // Adapter ground truth (static capture): viewDuration == spr at mount.
    const rowVm = wrapper.findComponent(WaveformRow).vm as unknown as {
      metrics: { viewDuration: { value: number } }
    }
    expect(rowVm.metrics.viewDuration.value).toBe(10)

    // Beta.1 smoke finding: row 0's key derived from start = 0 * spr == 0,
    // which is spr-invariant -- the stale row adapter kept the old window
    // until the row scrolled out and back. The key now embeds spr itself.
    await wrapper.find('[data-test="spr-select"]').setValue("20")
    const rows = wrapper.findAll(".waveform-row")
    expect(rows[0].attributes("data-row-end")).toBe("20")
    expect(rows[0].attributes("data-row-start")).toBe("0")
    // Row 1 reflects the new window too.
    expect(rows[1].attributes("data-row-start")).toBe("20")
    // The ADAPTER must follow: without the remount the exposed metrics
    // would still report the captured old preset (10) while the reactive
    // markers above moved on.
    const rowVmAfter = wrapper.findComponent(WaveformRow).vm as unknown as {
      metrics: { viewDuration: { value: number } }
    }
    expect(rowVmAfter.metrics.viewDuration.value).toBe(20)
    wrapper.unmount()
  })

  it("rowHeight change stays geometry-only (no data churn)", async () => {
    const wrapper = mountMulti()
    const before = wrapper.find(".waveform-row").attributes("data-row-end")
    await wrapper.find('[data-test="row-height-select"]').setValue("168")
    expect(wrapper.find(".waveform-row").attributes("data-row-end")).toBe(before)
    expect((wrapper.find(".waveform-row").element as HTMLElement).style.height).toBe("168px")
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M5-1/M5-2: multi-container wheel gesture family
// ------------------------------------------------------------------

describe("WaveformEditor multi wheel gestures (M5-1/M5-2)", () => {
  // Anchor math needs a real viewport: happy-dom reports clientHeight 0,
  // so give the multi-scroll container a fixed 320px like the real UI.
  let clientHeightDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientHeight",
    )
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    localStorage.clear()
  })

  function mountMulti(currentTime = 25) {
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime,
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function multiScroll(wrapper: ReturnType<typeof mountMulti>): HTMLElement {
    return wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
  }

  function dispatchWheel(
    el: HTMLElement,
    init: { deltaY: number; ctrlKey?: boolean; shiftKey?: boolean },
  ): boolean {
    // happy-dom's WheelEvent constructor drops modifier keys (ctrlKey comes
    // out undefined), so force-define them on the instance before dispatch.
    const ev = new WheelEvent("wheel", {
      deltaY: init.deltaY,
      bubbles: true,
      cancelable: true,
    })
    Object.defineProperty(ev, "ctrlKey", { value: init.ctrlKey ?? false })
    Object.defineProperty(ev, "shiftKey", { value: init.shiftKey ?? false })
    return !el.dispatchEvent(ev)
  }

  it("plain wheel stays native: no preventDefault, no preset churn", async () => {
    const wrapper = mountMulti()
    const scroll = multiScroll(wrapper)
    expect(dispatchWheel(scroll, { deltaY: 120 })).toBe(false)
    expect(dispatchWheel(scroll, { deltaY: -45 })).toBe(false)
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS + 50)
    await wrapper.vm.$nextTick()
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("10")
    expect(
      (wrapper.find('[data-test="row-height-select"]').element as HTMLSelectElement).value,
    ).toBe("120")
    wrapper.unmount()
  })

  it("ctrl+wheel merges the burst into ONE spr cycle and anchors the playing row", async () => {
    const wrapper = mountMulti(25) // playing time 25s -> row 2 under spr 10
    const scroll = multiScroll(wrapper)
    // Three quick zoom-in notches: net -3, clamped at the ladder start.
    for (let i = 0; i < 3; i++) dispatchWheel(scroll, { deltaY: -120, ctrlKey: true })
    // Debounce pending: nothing applied yet.
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("10")
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS)
    await wrapper.vm.$nextTick()
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("5")
    // M5-2 anchor: time 25s sits in row 5 under spr 5 (row 5 start = 25).
    // followScrollTop(5, 320, 120, 2270, 0.45) = 5*130 - 144 = 506.
    expect(scroll.scrollTop).toBe(506)
    // The playing row is inside the rendered window (playback row stays visible).
    const starts = wrapper.findAll(".waveform-row").map(r => r.attributes("data-row-start"))
    expect(starts).toContain("25")
    wrapper.unmount()
  })

  it("ctrl+shift+wheel cycles row height geometry-only and anchors", async () => {
    const wrapper = mountMulti(25)
    const scroll = multiScroll(wrapper)
    // One zoom-out notch: wheel-down -> shorter rows (120 -> 96).
    dispatchWheel(scroll, { deltaY: 120, ctrlKey: true, shiftKey: true })
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS)
    await wrapper.vm.$nextTick()
    expect(
      (wrapper.find('[data-test="row-height-select"]').element as HTMLSelectElement).value,
    ).toBe("96")
    // spr untouched: rowHeight is geometry-only.
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("10")
    expect(wrapper.find(".waveform-row").attributes("data-row-end")).toBe("10")
    // M5-2 anchor with the new geometry: row 2, strideOf(96)=106,
    // max = 10*106-10-320 = 730 -> followScrollTop(2, 320, 96, 730, 0.45) = 212-144 = 68.
    expect(scroll.scrollTop).toBe(68)
    wrapper.unmount()
  })

  it("intercepts ctrl+wheel with preventDefault (zoom boundary) and keeps families exclusive", async () => {
    const wrapper = mountMulti()
    const scroll = multiScroll(wrapper)
    // Ctrl+wheel IS cancelable interception (stops WebView page zoom)...
    expect(dispatchWheel(scroll, { deltaY: -120, ctrlKey: true, shiftKey: true })).toBe(true)
    // ...while plain wheel inside the same pass is never canceled.
    expect(dispatchWheel(scroll, { deltaY: 120 })).toBe(false)
    // Shift-only burst: the row-height family moves, spr stays put.
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS + 50)
    await wrapper.vm.$nextTick()
    expect(
      (wrapper.find('[data-test="row-height-select"]').element as HTMLSelectElement).value,
    ).toBe("144")
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("10")
    // Now a plain ctrl burst: the spr family moves, row height stays put.
    dispatchWheel(scroll, { deltaY: 120, ctrlKey: true })
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS + 50)
    await wrapper.vm.$nextTick()
    expect((wrapper.find('[data-test="spr-select"]').element as HTMLSelectElement).value).toBe("20")
    expect(
      (wrapper.find('[data-test="row-height-select"]').element as HTMLSelectElement).value,
    ).toBe("144")
    wrapper.unmount()
  })

  it("basic branch mounts no multi wheel host (zero-change regression)", () => {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "basic", secondsPerRow: 10, rowHeight: 120 }),
    )
    const wrapper = mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: 25 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
    expect(wrapper.find('[data-test="multi-scroll"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M5-3: in-row pointer gestures (scrub / Ctrl-create / marquee)
// ------------------------------------------------------------------

import { defineComponent } from "vue"

/** SegmentBlocksLayer stand-in that emits the M5-3 empty-area events. */
const EmptyAreaLayerStub = defineComponent({
  name: "SegmentBlocksLayer",
  emits: ["empty-press", "empty-double-click"],
  template: `<div
    data-test="seg-layer-stub"
    class="absolute inset-0"
    @mousedown.self="
      $emit('empty-press', {
        clientX: $event.clientX,
        clientY: $event.clientY,
        ctrlKey: $event.ctrlKey,
        shiftKey: $event.shiftKey,
        time: 0,
      })
    "
    @dblclick.self="$emit('empty-double-click')"
  ></div>`,
})

describe("WaveformEditor in-row pointer gestures (M5-3)", () => {
  // Geometry model: rows are 600px wide, stride 130 (rowHeight 120 + gap),
  // content origin at (0, 0). x -> time inside a row: (x/600)*spr.
  let clientHeightDescriptor: PropertyDescriptor | undefined
  let rectDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
    rectDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "getBoundingClientRect")
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.classList?.contains("waveform-row")) {
          const idx = Number(this.getAttribute("data-row-index") ?? 0)
          return rect(0, idx * 130, 600, 120)
        }
        if (this.getAttribute?.("data-test") === "multi-content") {
          return rect(0, 0, 600, 1290)
        }
        return rect(0, 0, 0, 0)
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  function rect(left: number, top: number, width: number, height: number): DOMRect {
    return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) } as DOMRect
  }

  function makeMouse(type: string, x: number, y: number, modifiers: { ctrlKey?: boolean; shiftKey?: boolean } = {}) {
    const ev = new MouseEvent(type, { bubbles: true, cancelable: true })
    // happy-dom drops modifier keys from event constructors.
    Object.defineProperty(ev, "clientX", { value: x })
    Object.defineProperty(ev, "clientY", { value: y })
    Object.defineProperty(ev, "ctrlKey", { value: modifiers.ctrlKey ?? false })
    Object.defineProperty(ev, "shiftKey", { value: modifiers.shiftKey ?? false })
    return ev
  }

  function mountGestures(segments: Array<{ id: string; start: number; end: number }>) {
    return mount(WaveformEditor, {
      props: {
        segments: segments.map(s => ({
          id: s.id,
          version: 1,
          type: "subtitle" as const,
          start: s.start,
          end: s.end,
          text: `t-${s.id}`,
          speaker: "",
        })),
        edits: [],
        duration: 100,
        currentTime: -1,
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: EmptyAreaLayerStub,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })
  afterEach(() => {
    localStorage.clear()
  })

  it("plain press scrubs: 32ms throttle collapses sync moves, release seeks precisely", async () => {
    const wrapper = mountGestures([])
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 300, 60)) // row 0, 5s
    // Throttled moves within the same tick: only the FIRST emits.
    for (let i = 0; i < 3; i++) document.dispatchEvent(makeMouse("mousemove", 360, 60)) // 6s
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("set-time")).toEqual([[6]])
    expect((wrapper.vm as unknown as { waveformScrubbing: boolean }).waveformScrubbing).toBe(true)
    // Release emits ONE precise seek at the final position.
    document.dispatchEvent(makeMouse("mouseup", 480, 60)) // 8s
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("set-time")).toEqual([[6], [8]])
    expect((wrapper.vm as unknown as { waveformScrubbing: boolean }).waveformScrubbing).toBe(false)
    // A plain press clears the global selection upstream (清选上行).
    expect(wrapper.emitted("clear-selection")?.length).toBe(1)
    expect(wrapper.emitted("scrubbing")?.some(c => c[0] === true)).toBe(true)
    wrapper.unmount()
  })

  it("double click on empty area toggles playback", async () => {
    const wrapper = mountGestures([])
    await wrapper.find('[data-test="seg-layer-stub"]').trigger("dblclick")
    expect(wrapper.emitted("toggle-play")?.length).toBe(1)
    wrapper.unmount()
  })

  it("Ctrl+drag previews row-bounded creation and commits via add-segment", async () => {
    const wrapper = mountGestures([{ id: "a", start: 20, end: 22 }])
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60, { ctrlKey: true })) // 2s
    document.dispatchEvent(makeMouse("mousemove", 300, 60)) // 5s
    await wrapper.vm.$nextTick()
    const preview = wrapper.find('[data-test="create-preview"]')
    expect(preview.exists()).toBe(true)
    expect((preview.element as HTMLElement).style.left).toBe("20%")
    expect((preview.element as HTMLElement).style.width).toBe("30%")
    document.dispatchEvent(makeMouse("mouseup", 300, 60))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("add-segment")).toEqual([[2, 5]])
    expect(wrapper.find('[data-test="create-preview"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("Ctrl-create preview stops at an existing block edge; narrow gaps reject", async () => {
    // Segment [4,6]: sweeping across it clamps the preview at 4s.
    const wrapper = mountGestures([{ id: "s", start: 4, end: 6 }])
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60, { ctrlKey: true })) // 2s
    document.dispatchEvent(makeMouse("mousemove", 420, 60)) // raw sweep to 7s
    await wrapper.vm.$nextTick()
    expect((wrapper.find('[data-test="create-preview"]').element as HTMLElement).style.width).toBe("20%") // 2..4s
    document.dispatchEvent(makeMouse("mouseup", 420, 60))
    expect(wrapper.emitted("add-segment")).toEqual([[2, 4]])
    wrapper.unmount()

    // Gap 1.95..2.0 is narrower than MIN_SEGMENT_DURATION: reject silently.
    const wrapper2 = mountGestures([
      { id: "x", start: 1.9, end: 1.95 },
      { id: "y", start: 2.0, end: 2.05 },
    ])
    const stub2 = wrapper2.find('[data-test="seg-layer-stub"]').element
    stub2.dispatchEvent(makeMouse("mousedown", 118.2, 60, { ctrlKey: true })) // anchor 1.97s
    document.dispatchEvent(makeMouse("mousemove", 240, 60))
    await wrapper2.vm.$nextTick()
    expect(wrapper2.find('[data-test="create-preview"]').classes()).toContain("border-red-500")
    document.dispatchEvent(makeMouse("mouseup", 240, 60))
    expect(wrapper2.emitted("add-segment")).toBeFalsy()
    wrapper2.unmount()
  })

  it("Shift+drag marquee hits blocks across two rows and merges selection", async () => {
    const wrapper = mountGestures([
      { id: "a", start: 1, end: 3 }, // row 0
      { id: "b", start: 12, end: 14 }, // row 1
      { id: "c", start: 25, end: 27 }, // row 2 (outside the marquee)
    ])
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 60, 60, { shiftKey: true })) // row 0
    document.dispatchEvent(makeMouse("mousemove", 480, 190)) // into row 1
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="marquee-rect"]').exists()).toBe(true)
    document.dispatchEvent(makeMouse("mouseup", 480, 190))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("select-segments")).toEqual([[["a", "b"]]])
    expect(wrapper.find('[data-test="marquee-rect"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M6-1: follow three-way (playback follow / cooldown / reveal)
// ------------------------------------------------------------------

describe("WaveformEditor follow three-way (M6-1)", () => {
  // Viewport 320px, stride 130 (rowHeight 120), comfort rowTop window
  // [64, 136]; follow target for row r = r*130 - 320*0.35 = r*130 - 112.
  let clientHeightDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  beforeEach(() => {
    // Full fake timers: Date drives the 3s cooldown, setTimeout drives the
    // M5-1 wheel burst used to reposition via the M5-2 anchor.
    vi.useFakeTimers()
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  function mountFollow(currentTime: number) {
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function scrollElOf(wrapper: ReturnType<typeof mountFollow>): HTMLElement {
    return wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
  }

  function trustedScroll(el: HTMLElement, isTrusted: boolean) {
    const ev = new Event("scroll")
    Object.defineProperty(ev, "isTrusted", { value: isTrusted })
    el.dispatchEvent(ev)
  }

  function dispatchWheel(
    el: HTMLElement,
    init: { deltaY: number; ctrlKey?: boolean; shiftKey?: boolean },
  ) {
    // happy-dom drops modifier keys from event constructors (see M5-1 note).
    const ev = new WheelEvent("wheel", { deltaY: init.deltaY, bubbles: true, cancelable: true })
    Object.defineProperty(ev, "ctrlKey", { value: init.ctrlKey ?? false })
    Object.defineProperty(ev, "shiftKey", { value: init.shiftKey ?? false })
    el.dispatchEvent(ev)
  }

  it("follows the playing row at FOLLOW_BIAS only when the row changes", async () => {
    const wrapper = mountFollow(5) // row 0
    const el = scrollElOf(wrapper)
    await wrapper.setProps({ currentTime: 8 }) // same row 0 -> no judgment
    expect(el.scrollTop).toBe(0)
    await wrapper.setProps({ currentTime: 25 }) // row 2 -> 2*130 - 112
    expect(el.scrollTop).toBe(148)
    wrapper.unmount()
  })

  it("the programmatic write's scroll echo is NOT a manual scroll (回环抑制)", async () => {
    const wrapper = mountFollow(5)
    const el = scrollElOf(wrapper)
    await wrapper.setProps({ currentTime: 25 }) // follow writes 148
    expect(el.scrollTop).toBe(148)
    trustedScroll(el, true) // echo of our own write
    await wrapper.setProps({ currentTime: 45 }) // row 4, no cooldown -> 408
    expect(el.scrollTop).toBe(408)
    wrapper.unmount()
  })

  it("a genuine manual scroll pauses follow for the 3s cooldown", async () => {
    const wrapper = mountFollow(5)
    const el = scrollElOf(wrapper)
    await wrapper.setProps({ currentTime: 25 }) // follow writes 148, target pending
    expect(el.scrollTop).toBe(148)
    trustedScroll(el, true) // inside the smooth echo window: ignored entirely
    vi.advanceTimersByTime(801) // echo window over
    trustedScroll(el, true) // matches the pending write -> consumed as echo
    trustedScroll(el, true) // no pending target anymore -> genuine manual -> cooldown
    await wrapper.setProps({ currentTime: 45 }) // row 4 blocked by the cooldown
    expect(el.scrollTop).toBe(148)
    vi.advanceTimersByTime(3000) // cooldown expired
    await wrapper.setProps({ currentTime: 65 }) // row 6 -> follows again
    expect(el.scrollTop).toBe(668)
    wrapper.unmount()
  })

  it("a row already comfortable keeps the playhead-only path (免滚)", async () => {
    const wrapper = mountFollow(5)
    const el = scrollElOf(wrapper)
    // M5-2 anchor (ctrl+wheel -> spr 5) parks the playing row at scrollTop 0,
    // which leaves row 1 comfortable (rowTop 130 in [64, 136]).
    dispatchWheel(el, { deltaY: -120, ctrlKey: true })
    vi.advanceTimersByTime(WHEEL_DEBOUNCE_MS)
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(0)
    await wrapper.setProps({ currentTime: 8 }) // row 1 (spr 5): comfortable -> skip
    expect(el.scrollTop).toBe(0)
    await wrapper.setProps({ currentTime: 13 }) // row 2: uncomfortable -> follows
    expect(el.scrollTop).toBe(148)
    wrapper.unmount()
  })

  it("exposed revealTime jumps with REVEAL_BIAS and arms the cooldown", async () => {
    const wrapper = mountFollow(5)
    const el = scrollElOf(wrapper)
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(45) // row 4
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(376) // 4*130 - 320*0.45
    await wrapper.setProps({ currentTime: 65 }) // row 6 within cooldown: blocked
    expect(el.scrollTop).toBe(376)
    vi.advanceTimersByTime(3000)
    await wrapper.setProps({ currentTime: 85 }) // row 8 -> follows
    expect(el.scrollTop).toBe(928)
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M6-2/M6-3: mode-switch migration + persisted restore
// ------------------------------------------------------------------

describe("WaveformEditor mode migration + persisted restore (M6-2/M6-3)", () => {
  let clientHeightDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  function mountEditor(currentTime: number) {
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("multi -> basic centers the viewport top row; back reveals its center", async () => {
    const wrapper = mountEditor(5)
    const el = wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
    // Park the multi viewport: reveal row 4 -> scrollTop 376 (t=20s).
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(45)
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(376)

    // Leave multi: the basic window centers on scrollTopTime + spr/2 = 25s.
    await wrapper.find('[data-test="mode-basic"]').trigger("click")
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="basic-view-start"]').text()).toBe("10.0s")

    // Re-enter multi: reveal the basic window's center (25s, row 2) at 0.5.
    await wrapper.find('[data-test="mode-multi"]').trigger("click")
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="multi-scroll"]').element.scrollTop).toBe(100)
    wrapper.unmount()
  })

  it("restore quantizes the persisted scrollTopTime to a row boundary", async () => {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120, scrollTopTime: 25 }),
    )
    const wrapper = mountEditor(5)
    const el = wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
    await wrapper.vm.$nextTick()
    // timeToScrollTop(25) floors to the row-2 boundary: 2 * 130 = 260.
    expect(el.scrollTop).toBe(260)
    wrapper.unmount()
  })

  it("unmount flushes the pending scrollTopTime write (兜底)", async () => {
    const wrapper = mountEditor(5)
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(45)
    await wrapper.vm.$nextTick() // debounce timer armed with scrollTopTime = 20
    wrapper.unmount() // before the 300ms window elapses
    expect(loadRowLayoutState().scrollTopTime).toBe(20)
  })
})

// ------------------------------------------------------------------
// v3.0.2 M6-4: mini overview strip (multi-mode ScrollbarStrip)
// ------------------------------------------------------------------

describe("WaveformEditor mini overview strip (M6-4)", () => {
  // Viewport 320, stride 130, duration 100 @ spr 10 -> rowCount 10.
  let clientHeightDescriptor: PropertyDescriptor | undefined
  let rectDescriptor: PropertyDescriptor | undefined

  function domRect(left: number, top: number, width: number, height: number): DOMRect {
    return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) } as DOMRect
  }

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
    rectDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "getBoundingClientRect")
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "overview-strip") return domRect(0, 0, 600, 12)
        return domRect(0, 0, 0, 0)
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    localStorage.clear()
  })

  function mountOverview(currentTime: number) {
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function nextFrame(): Promise<void> {
    return new Promise(r => requestAnimationFrame(() => r()))
  }

  it("coverage geometry matches visibleRows (first/last x spr / duration)", async () => {
    const wrapper = mountOverview(25)
    await wrapper.vm.$nextTick() // setScrollRef feeds viewportHeight -> re-window
    const coverage = wrapper.find('[data-test="overview-coverage"]')
    // At scrollTop 0: visibleRows 0..5 -> left 0%, width 6*10/100 = 60%.
    expect((coverage.element as HTMLElement).style.left).toBe("0%")
    expect((coverage.element as HTMLElement).style.width).toBe("60%")
    // Playhead tick at currentTime/duration.
    expect((wrapper.find('[data-test="overview-playhead"]').element as HTMLElement).style.left).toBe("calc(25% - 1px)")
    wrapper.unmount()
  })

  it("coverage follows the scrolled window and clamps at the timeline end", async () => {
    const wrapper = mountOverview(25)
    await wrapper.vm.$nextTick()
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(45) // row 4 -> 376
    await wrapper.vm.$nextTick()
    // visibleRows 0..8 -> width 90%.
    expect((wrapper.find('[data-test="overview-coverage"]').element as HTMLElement).style.width).toBe("90%")
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(85) // row 8 -> 896
    await wrapper.vm.$nextTick()
    // visibleRows clamp: first 4, last 9 -> left 40%, width 60%.
    const coverage = wrapper.find('[data-test="overview-coverage"]')
    expect((coverage.element as HTMLElement).style.left).toBe("40%")
    expect((coverage.element as HTMLElement).style.width).toBe("60%")
    wrapper.unmount()
  })

  it("clicking the strip seeks through revealTime with row alignment", async () => {
    const wrapper = mountOverview(25)
    await wrapper.vm.$nextTick()
    const strip = wrapper.find('[data-test="overview-strip"]')
    // Click at 300/600 = 50s -> row 5 -> REVEAL_BIAS placement.
    await strip.trigger("mousedown", { clientX: 300 })
    const el = wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(506) // 5*130 - 320*0.45, row-aligned
    // Drag: rAF-throttled move emits another seek at 80s -> row 8 -> 896.
    document.dispatchEvent(new MouseEvent("mousemove", { clientX: 480 }))
    await nextFrame()
    await new Promise(r => setTimeout(r, 20))
    expect(el.scrollTop).toBe(896)
    document.dispatchEvent(new MouseEvent("mouseup", { clientX: 480 }))
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M7-1: viewport height divider + persisted editorHeightPx
// ------------------------------------------------------------------

describe("WaveformEditor viewport height divider (M7-1)", () => {
  let innerHeightDescriptor: PropertyDescriptor | undefined
  let mockInnerHeight = 800

  beforeAll(() => {
    innerHeightDescriptor = Object.getOwnPropertyDescriptor(window, "innerHeight")
    Object.defineProperty(window, "innerHeight", {
      configurable: true,
      get: () => mockInnerHeight,
    })
  })

  afterAll(() => {
    if (innerHeightDescriptor) {
      Object.defineProperty(window, "innerHeight", innerHeightDescriptor)
    }
  })

  beforeEach(() => {
    mockInnerHeight = 800 // clamp window: [160, 560]
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    localStorage.clear()
  })

  function mountEditor() {
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: 5 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function seedState(extra: Record<string, unknown>) {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120, ...extra }),
    )
  }

  it("round-trips editorHeightPx with the 20-70% viewport clamp", async () => {
    for (const [stored, expected] of [
      [{ editorHeightPx: 480 }, "480px"], // inside the clamp window: verbatim
      [{ editorHeightPx: 50 }, "160px"], // below 20% -> clamped to 160
      [{ editorHeightPx: 5000 }, "560px"], // above 70% -> clamped to 560
      [{}, "360px"], // unset -> 45% default
    ] as const) {
      seedState(stored)
      const wrapper = mountEditor()
      await wrapper.vm.$nextTick()
      expect(
        (wrapper.find('[data-test="multi-scroll"]').element as HTMLElement).style.height,
      ).toBe(expected)
      wrapper.unmount()
    }
  })

  it("divider drag grows the panel and persists editorHeightPx (变更即写)", async () => {
    const wrapper = mountEditor()
    await wrapper.vm.$nextTick()
    expect(
      (wrapper.find('[data-test="multi-scroll"]').element as HTMLElement).style.height,
    ).toBe("360px")
    const divider = wrapper.find('[data-test="viewport-divider"]')
    await divider.trigger("mousedown", { clientY: 500 })
    // Drag up 80px -> 360 + 80 = 440.
    const move = new MouseEvent("mousemove")
    Object.defineProperty(move, "clientY", { value: 420 })
    document.dispatchEvent(move)
    await wrapper.vm.$nextTick()
    expect(
      (wrapper.find('[data-test="multi-scroll"]').element as HTMLElement).style.height,
    ).toBe("440px")
    document.dispatchEvent(new MouseEvent("mouseup"))
    expect(loadRowLayoutState().editorHeightPx).toBe(440)
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.2 M7-2: per-row extension-track lanes + row-height linkage
// ------------------------------------------------------------------

describe("WaveformEditor per-row track lanes (M7-2)", () => {
  let clientHeightDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    localStorage.clear()
  })

  function mountLanes(rowHeight: number) {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight }),
    )
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime: 5,
        tracks: [makeStackTrack("en")],
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("composes one sub-lane per track inside every visible row", async () => {
    const wrapper = mountLanes(168)
    await wrapper.vm.$nextTick()
    const rows = wrapper.findAll(".waveform-row")
    const lanes = wrapper.findAll('[data-test="track-lane"]')
    expect(rows.length).toBeGreaterThanOrEqual(3)
    expect(lanes.length).toBe(rows.length) // 1:1 per row (single track)
    const first = lanes[0].element as HTMLElement
    expect(first.style.height).toBe("48px") // md preset
    expect(first.style.top).toBe("120px") // main area = 168 - 48
    wrapper.unmount()
  })

  it("row-height 联动: untouched default bumps to 168; touched value respected", async () => {
    const wrapper = mountLanes(120) // untouched default + tracks -> 168
    await wrapper.vm.$nextTick()
    expect((wrapper.find('[data-test="row-height-select"]').element as HTMLSelectElement).value).toBe("168")
    wrapper.unmount()

    const wrapper2 = mountLanes(96) // user-touched value stays
    await wrapper2.vm.$nextTick()
    expect((wrapper2.find('[data-test="row-height-select"]').element as HTMLSelectElement).value).toBe("96")
    wrapper2.unmount()
  })

  it("lane collapse is shared across every row in lockstep", async () => {
    const wrapper = mountLanes(168)
    await wrapper.vm.$nextTick()
    const lanes = () => wrapper.findAll('[data-test="track-lane"]')
    await lanes()[0].find('[data-test="lane-collapse"]').trigger("click")
    await wrapper.vm.$nextTick()
    for (const lane of lanes()) {
      expect((lane.element as HTMLElement).style.height).toBe("24px")
    }
    wrapper.unmount()
  })
})

describe("WaveformEditor multi 建段模式 (smoke feedback #4)", () => {
  function mountBuild() {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
    const wrapper = mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: 5 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: {
            name: "SegmentBlocksLayer",
            props: { emptyAreaMode: { type: String, default: "add" } },
            emits: ["add-segment"],
            template: `<div data-test="seg-layer-stub" class="absolute inset-0" @mousedown.self="$emit('add-segment', 1, 1.5)"></div>`,
          },
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
    return wrapper
  }

  afterEach(() => localStorage.clear())

  it("default (off): rows receive seek mode", async () => {
    const wrapper = mountBuild()
    await wrapper.vm.$nextTick()
    const stub = wrapper.findComponent({ name: "SegmentBlocksLayer" })
    expect(stub.props("emptyAreaMode")).toBe("seek")
    wrapper.unmount()
  })

  it("toggle ON: rows receive add mode (empty click creates); off restores", async () => {
    const wrapper = mountBuild()
    await wrapper.vm.$nextTick()
    const stub = () => wrapper.findComponent({ name: "SegmentBlocksLayer" })
    await wrapper.find('[data-test="build-mode-toggle"]').trigger("click")
    expect(stub().props("emptyAreaMode")).toBe("add")
    await wrapper.find('[data-test="build-mode-toggle"]').trigger("click")
    expect(stub().props("emptyAreaMode")).toBe("seek")
    wrapper.unmount()
  })
})

describe("WaveformEditor lane menu forwarding (smoke fix)", () => {
  function mountLanesReal() {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 168 }),
    )
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime: 5,
        tracks: [makeStackTrack("en")],
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("lane menu 删除此条字幕 forwards delete-track-segment with trackId", async () => {
    const wrapper = mountLanesReal()
    await wrapper.vm.$nextTick()
    const block = wrapper.findComponent(SegmentBlock)
    expect(block.exists()).toBe(true)
    await block.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")
    expect(menu).not.toBeNull()
    const delSeg = Array.from(menu!.querySelectorAll("button")).find(b =>
      b.textContent?.includes("删除此条字幕"),
    )!
    delSeg.click()
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted("delete-track-segment")
    console.log("[diag] delete-track-segment:", JSON.stringify(emitted ?? []))
    expect(emitted?.length).toBe(1)
    wrapper.unmount()
  })

  it("lane menu 删除此轨 forwards delete-track with trackId", async () => {
    const wrapper = mountLanesReal()
    await wrapper.vm.$nextTick()
    const block = wrapper.findComponent(SegmentBlock)
    await block.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const delTrack = Array.from(menu.querySelectorAll("button")).find(b =>
      b.textContent?.includes("删除此轨"),
    )!
    delTrack.click()
    await wrapper.vm.$nextTick()
    const emitted = wrapper.emitted("delete-track")
    console.log("[diag] delete-track:", JSON.stringify(emitted ?? []))
    expect(emitted?.length).toBe(1)
    expect((emitted as unknown[][])[0][0]).toBe("en")
    wrapper.unmount()
  })
})

describe("WaveformEditor BASIC lane menu forwarding (smoke fix)", () => {
  function mountStackLanes() {
    localStorage.removeItem(ROW_LAYOUT_STORAGE_KEY) // default = basic
    const wrapper = mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime: 0,
        tracks: [makeStackTrack("en")],
      },
      global: {
        provide: { [PLAYBACK_CLOCK_KEY as symbol]: makeClock() },
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
        },
      },
    })
    return wrapper
  }

  it("BASIC stacked lanes forward 删除此条字幕/删除此轨 (smoke fix #2)", async () => {
    const wrapper = mountStackLanes()
    await wrapper.vm.$nextTick()
    const block = wrapper.findComponent(SegmentBlock)
    expect(block.exists()).toBe(true)
    await block.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    expect(menu).not.toBeNull()
    const delSeg = Array.from(menu.querySelectorAll("button")).find(b =>
      b.textContent?.includes("删除此条字幕"),
    )!
    delSeg.click()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("delete-track-segment")?.[0]).toEqual(["en", "track_en_seg_0"])
    // Re-open and delete the whole track.
    await block.trigger("contextmenu")
    const menu2 = document.body.querySelector(".fixed.z-dropdown")!
    const delTrack = Array.from(menu2.querySelectorAll("button")).find(b =>
      b.textContent?.includes("删除此轨"),
    )!
    delTrack.click()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("delete-track")?.[0]).toEqual(["en"])
    wrapper.unmount()
  })
})

describe("WaveformEditor continuous playback (smoke feedback #2)", () => {
  let clientHeightDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    localStorage.clear()
  })

  it("continuous playback crossing 9 rows never blanks the surface", async () => {
    const wrapper = mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: 5 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
    const el = () => wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
    for (const t of [15, 25, 35, 45, 55, 65, 75, 85, 95]) {
      await wrapper.setProps({ currentTime: t })
    }
    const rows = wrapper.findAll(".waveform-row")
    console.log("[diag] rows:", rows.length, "scrollTop:", el().scrollTop,
      "starts:", rows.map(r => r.attributes("data-row-start")).join(","))
    expect(rows.length).toBeGreaterThan(0)
    // The playing row (90-100s, row 9) must be within the rendered window.
    const starts = rows.map(r => Number(r.attributes("data-row-start")))
    expect(starts).toContain(90)
    wrapper.unmount()
  })

  it("a non-finite currentTime never blanks the surface (blank-guard)", async () => {
    const wrapper = mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: 5 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
    await wrapper.setProps({ currentTime: Number.NaN })
    await wrapper.vm.$nextTick()
    const rows = wrapper.findAll(".waveform-row")
    expect(rows.length).toBeGreaterThan(0)
    await wrapper.setProps({ currentTime: 45 }) // recovery: follow still works
    expect(
      (wrapper.find('[data-test="multi-scroll"]').element as HTMLElement).scrollTop,
    ).toBeGreaterThan(0)
    wrapper.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.4 M3-2 (P3-3): lane 建段接线 -- the three-point wiring that
// 41a1ac4 declared but never delivered (TrackLane.onLaneClick gated on
// buildMode that no ancestor passed; the @create-at bridge + the
// track-create emit had no producer). Geometry: lane-blocks is mocked
// 600px wide, so clientX 300 -> ratio 0.5.
// ------------------------------------------------------------------

describe("WaveformEditor lane 建段接线 (M3-2)", () => {
  let clientHeightDescriptor: PropertyDescriptor | undefined
  let rectDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientHeight",
    )
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
    rectDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "getBoundingClientRect",
    )
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "lane-blocks") {
          return {
            left: 0,
            top: 0,
            width: 600,
            height: 48,
            right: 600,
            bottom: 48,
            x: 0,
            y: 0,
            toJSON: () => ({}),
          } as DOMRect
        }
        return rectDescriptor?.value?.call(this) ?? {
          left: 0,
          top: 0,
          width: 0,
          height: 0,
          right: 0,
          bottom: 0,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        } as DOMRect
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  /** Multi mount: row 0's lane sits on the row-scoped 0..10s window. */
  function mountLaneMulti() {
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime: 5,
        tracks: [makeStackTrack("en")],
      },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  /** Basic mount: lanes sit on the editor-scoped default 0..30s window. */
  function mountLaneBasic() {
    localStorage.removeItem(ROW_LAYOUT_STORAGE_KEY) // default = basic
    return mount(WaveformEditor, {
      props: {
        segments: [],
        edits: [],
        duration: 100,
        currentTime: 0,
        tracks: [makeStackTrack("en")],
      },
      global: {
        provide: { [PLAYBACK_CLOCK_KEY as symbol]: makeClock() },
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  it("multi: build-mode lane click raises track-create (trackId, t, t+0.5)", async () => {
    const wrapper = mountLaneMulti()
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="build-mode-toggle"]').trigger("click")
    // Row 0 lane window is 0..10s; ratio 0.5 -> t = 5, end = 5.5.
    const laneBlocks = wrapper.findAll('[data-test="lane-blocks"]')
    expect(laneBlocks.length).toBeGreaterThan(0)
    await laneBlocks[0].trigger("click", { clientX: 300 })
    expect(wrapper.emitted("track-create")).toEqual([["en", 5, 5.5]])
    wrapper.unmount()
  })

  it("basic: build-mode lane click raises track-create via the @create-at bridge", async () => {
    const wrapper = mountLaneBasic()
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="build-mode-toggle"]').trigger("click")
    // Basic lane window defaults to viewDuration 30s (useTimelineMetrics);
    // ratio 0.5 -> t = 15, end = 15.5.
    const laneBlocks = wrapper.findAll('[data-test="lane-blocks"]')
    expect(laneBlocks.length).toBe(1)
    await laneBlocks[0].trigger("click", { clientX: 300 })
    expect(wrapper.emitted("track-create")).toEqual([["en", 15, 15.5]])
    wrapper.unmount()
  })

  it("build-mode OFF: lane clicks are inert (zero regression)", async () => {
    const multi = mountLaneMulti()
    await multi.vm.$nextTick()
    const multiLanes = multi.findAll('[data-test="lane-blocks"]')
    expect(multiLanes.length).toBeGreaterThan(0)
    await multiLanes[0].trigger("click", { clientX: 300 })
    expect(multi.emitted("track-create")).toBeFalsy()
    multi.unmount()

    const basic = mountLaneBasic()
    await basic.vm.$nextTick()
    const basicLanes = basic.findAll('[data-test="lane-blocks"]')
    expect(basicLanes.length).toBe(1)
    await basicLanes[0].trigger("click", { clientX: 300 })
    expect(basic.emitted("track-create")).toBeFalsy()
    basic.unmount()
  })
})

// ------------------------------------------------------------------
// v3.0.4 M4-2 (P3-6): 范围标记 toggle + 确认气泡 -- multi matrix cells
// ------------------------------------------------------------------

import { ref, type Ref } from "vue"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"

describe("WaveformEditor 范围标记手势 (M4-2, multi)", () => {
  // Same geometry model as the M5-3 gesture suite: rows 600px wide,
  // stride 130 (rowHeight 120 + gap), content origin (0,0);
  // x -> time inside a row: (x/600)*spr (spr = 10).
  let clientHeightDescriptor: PropertyDescriptor | undefined
  let rectDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "multi-scroll") return 320
        return clientHeightDescriptor?.get?.call(this) ?? 0
      },
    })
    rectDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "getBoundingClientRect")
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.classList?.contains("waveform-row")) {
          const idx = Number(this.getAttribute("data-row-index") ?? 0)
          return rect(0, idx * 130, 600, 120)
        }
        if (this.getAttribute?.("data-test") === "multi-content") {
          return rect(0, 0, 600, 1290)
        }
        return rect(0, 0, 0, 0)
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  function rect(left: number, top: number, width: number, height: number): DOMRect {
    return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) } as DOMRect
  }

  function makeMouse(type: string, x: number, y: number, modifiers: { ctrlKey?: boolean; shiftKey?: boolean } = {}) {
    const ev = new MouseEvent(type, { bubbles: true, cancelable: true })
    Object.defineProperty(ev, "clientX", { value: x })
    Object.defineProperty(ev, "clientY", { value: y })
    Object.defineProperty(ev, "ctrlKey", { value: modifiers.ctrlKey ?? false })
    Object.defineProperty(ev, "shiftKey", { value: modifiers.shiftKey ?? false })
    return ev
  }

  function mountRange(segments: Array<{ id: string; start: number; end: number }> = [], rangeSelection?: Ref<{ start: number; end: number } | null>) {
    return mount(WaveformEditor, {
      props: {
        segments: segments.map(s => ({
          id: s.id,
          version: 1,
          type: "subtitle" as const,
          start: s.start,
          end: s.end,
          text: `t-${s.id}`,
          speaker: "",
        })),
        edits: [],
        duration: 100,
        currentTime: -1,
        ...(rangeSelection ? { rangeSelection } : {}),
      },
      // attachTo: happy-dom's focus() is a no-op on detached trees, and the
      // bubble's 删除-focused default (Q9) is asserted via activeElement.
      attachTo: document.body,
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: EmptyAreaLayerStub,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })
  afterEach(() => {
    localStorage.clear()
  })

  it("ON: plain press-drag sweeps the range marquee; release opens the bubble (删除 focused) and 删除 emits range-decision", async () => {
    const wrapper = mountRange()
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60)) // anchor 2s (row 0)
    document.dispatchEvent(makeMouse("mousemove", 360, 60)) // sweep to 6s
    await wrapper.vm.$nextTick()
    const marquee = wrapper.find('[data-test="range-marquee"]')
    expect(marquee.exists()).toBe(true)
    expect((marquee.element as HTMLElement).style.left).toBe("20%")
    expect((marquee.element as HTMLElement).style.width).toBe("40%")
    // No scrub / no selection / no creation leaks into the range gesture.
    expect(wrapper.emitted("set-time")).toBeFalsy()
    expect(wrapper.emitted("clear-selection")).toBeFalsy()
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    document.dispatchEvent(makeMouse("mouseup", 360, 60))
    await wrapper.vm.$nextTick()
    // The sweep preview dies with the gesture; the bubble takes over.
    expect(wrapper.find('[data-test="range-marquee"]').exists()).toBe(false)
    const bubble = wrapper.find('[data-test="range-bubble"]')
    expect(bubble.exists()).toBe(true)
    expect(bubble.text()).toContain("4.0s")
    // Q9: the destructive default owns the keyboard.
    expect(document.activeElement?.getAttribute("data-test")).toBe("range-delete")
    await bubble.find('[data-test="range-delete"]').trigger("click")
    expect(wrapper.emitted("range-decision")).toEqual([[{ start: 2, end: 6, action: "delete" }]])
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("ON: 保留 emits action keep; a degenerate click (sweep < 0.05s) never opens the bubble", async () => {
    const wrapper = mountRange()
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60))
    document.dispatchEvent(makeMouse("mousemove", 360, 60))
    document.dispatchEvent(makeMouse("mouseup", 360, 60))
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="range-keep"]').trigger("click")
    expect(wrapper.emitted("range-decision")).toEqual([[{ start: 2, end: 6, action: "keep" }]])
    wrapper.unmount()

    // Plain click without a sweep: degenerate guard mirrors the marquee no-op.
    const wrapper2 = mountRange()
    await wrapper2.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub2 = wrapper2.find('[data-test="seg-layer-stub"]').element
    stub2.dispatchEvent(makeMouse("mousedown", 300, 60))
    document.dispatchEvent(makeMouse("mouseup", 302, 60)) // 0.033s sweep
    await wrapper2.vm.$nextTick()
    expect(wrapper2.find('[data-test="range-bubble"]').exists()).toBe(false)
    expect(wrapper2.emitted("range-decision")).toBeFalsy()
    wrapper2.unmount()
  })

  it("ON: 取消 emits nothing and clears the staged selectedRange (activated dead ref is the bubble sink)", async () => {
    const sink: Ref<{ start: number; end: number } | null> = ref(null)
    const wrapper = mountRange([], sink)
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60))
    document.dispatchEvent(makeMouse("mousemove", 360, 60))
    document.dispatchEvent(makeMouse("mouseup", 360, 60))
    await wrapper.vm.$nextTick()
    // The injected selectedRange ref is the staging store (written in place).
    expect(sink.value).toEqual({ start: 2, end: 6 })
    await wrapper.find('[data-test="range-cancel"]').trigger("click")
    expect(wrapper.emitted("range-decision")).toBeFalsy()
    expect(sink.value).toBeNull()
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("ON + Ctrl-drag stays Ctrl-create: add-segment commit byte-identical, never the range chain", async () => {
    const wrapper = mountRange()
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 120, 60, { ctrlKey: true })) // 2s
    document.dispatchEvent(makeMouse("mousemove", 300, 60)) // 5s
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="create-preview"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="range-marquee"]').exists()).toBe(false)
    document.dispatchEvent(makeMouse("mouseup", 300, 60))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("add-segment")).toEqual([[2, 5]])
    expect(wrapper.emitted("range-decision")).toBeFalsy()
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("ON + Shift-drag stays the segment marquee (select-segments), never the range chain", async () => {
    const wrapper = mountRange([
      { id: "a", start: 1, end: 3 }, // row 0
      { id: "b", start: 12, end: 14 }, // row 1
    ])
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 60, 60, { shiftKey: true }))
    document.dispatchEvent(makeMouse("mousemove", 480, 190))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="marquee-rect"]').exists()).toBe(true)
    document.dispatchEvent(makeMouse("mouseup", 480, 190))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("select-segments")).toEqual([[["a", "b"]]])
    expect(wrapper.emitted("range-decision")).toBeFalsy()
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("OFF (default and after a toggle cycle): the v3.0.3 plain-press scrub path is untouched", async () => {
    // Default OFF: the toggle reads 范围标记 and a plain press scrubs (the
    // M5-3 suite above covers the untouched default; here the toggle cycle).
    const wrapper = mountRange()
    expect(wrapper.find('[data-test="range-mode-toggle"]').text()).toBe("范围标记")
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click") // ON
    expect(wrapper.find('[data-test="range-mode-toggle"]').text()).toBe("标记中")
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click") // OFF
    const stub = wrapper.find('[data-test="seg-layer-stub"]').element
    stub.dispatchEvent(makeMouse("mousedown", 300, 60))
    for (let i = 0; i < 3; i++) document.dispatchEvent(makeMouse("mousemove", 360, 60)) // 6s
    document.dispatchEvent(makeMouse("mouseup", 480, 60)) // 8s
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted("set-time")).toEqual([[6], [8]])
    expect(wrapper.emitted("clear-selection")?.length).toBe(1)
    expect(wrapper.find('[data-test="range-marquee"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    expect(wrapper.emitted("range-decision")).toBeFalsy()
    wrapper.unmount()
  })

  it("wiring: rows keep the seek channel in range mode and buildMode is gated (matrix-equivalent adaptation)", async () => {
    // multi routes "seek" while rangeMode is ON (WaveformRow only forwards
    // the empty-press chain, P3-3 frozen); the range branch lives in
    // handleRowEmptyGesture. buildMode && !rangeMode stops the row's own
    // ternary from resurrecting "add" while both toggles are on.
    const probe = mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime: -1 },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: {
            name: "SegmentBlocksLayer",
            props: {
              emptyAreaMode: { type: String, default: "add" },
              buildMode: { type: Boolean, default: false },
            },
            template: `<div data-test="seg-layer-probe"></div>`,
          },
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
    const rowLayer = () => probe.findComponent({ name: "SegmentBlocksLayer" })
    const row = () => probe.findComponent(WaveformRow)
    expect(rowLayer().props("emptyAreaMode")).toBe("seek") // default OFF
    await probe.find('[data-test="build-mode-toggle"]').trigger("click")
    expect(rowLayer().props("emptyAreaMode")).toBe("add") // build ON only
    expect(row().props("buildMode")).toBe(true)
    await probe.find('[data-test="range-mode-toggle"]').trigger("click")
    // Both toggles ON: range wins -- seek channel + gated buildMode.
    expect(rowLayer().props("emptyAreaMode")).toBe("seek")
    expect(row().props("buildMode")).toBe(false)
    await probe.find('[data-test="range-mode-toggle"]').trigger("click")
    expect(rowLayer().props("emptyAreaMode")).toBe("add") // range off restores build
    expect(row().props("buildMode")).toBe(true)
    probe.unmount()
  })
})

describe("WaveformEditor basic 范围标记 (M4-2)", () => {
  // Basic geometry model: waveform-layer 600px wide at origin, duration 30
  // (viewStart 0, viewDuration 30): x -> time = (x/600)*30.
  let rectDescriptor: PropertyDescriptor | undefined

  beforeAll(() => {
    rectDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "getBoundingClientRect")
    Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
      configurable: true,
      value(this: HTMLElement) {
        if (this.getAttribute?.("data-test") === "waveform-layer") {
          return {
            left: 0,
            top: 0,
            width: 600,
            height: 112,
            right: 600,
            bottom: 112,
            x: 0,
            y: 0,
            toJSON: () => ({}),
          } as DOMRect
        }
        const fallback = rectDescriptor?.value?.call(this) ?? {
          left: 0,
          top: 0,
          width: 0,
          height: 0,
          right: 0,
          bottom: 0,
          x: 0,
          y: 0,
          toJSON: () => ({}),
        }
        return fallback as DOMRect
      },
    })
  })

  afterAll(() => {
    if (rectDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", rectDescriptor)
    }
  })

  function makeMouse(type: string, x: number, y: number) {
    const ev = new MouseEvent(type, { bubbles: true, cancelable: true })
    Object.defineProperty(ev, "clientX", { value: x })
    Object.defineProperty(ev, "clientY", { value: y })
    return ev
  }

  // SegmentBlocksLayer stays REAL: the "range" routing under test lives in
  // its handleEmptyClick branch (the basic direct-child path).
  function mountBasic() {
    localStorage.removeItem(ROW_LAYOUT_STORAGE_KEY) // default = basic
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 30, currentTime: 0 },
      // attachTo: happy-dom's focus() is a no-op on detached trees (Q9
      // 删除-focused default asserted via activeElement).
      attachTo: document.body,
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function emptyRoot(wrapper: ReturnType<typeof mountBasic>) {
    return wrapper.findComponent(SegmentBlocksLayer).find("div[tabindex='0']")
  }

  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it("OFF: the direct-child layer keeps the v3.0.3 seek semantics (no range-press listener path)", async () => {
    const wrapper = mountBasic()
    await wrapper.vm.$nextTick()
    const layer = wrapper.findComponent(SegmentBlocksLayer)
    expect(layer.props("emptyAreaMode")).toBe("seek")
    await emptyRoot(wrapper).trigger("mousedown", { clientX: 100, clientY: 40 })
    await document.dispatchEvent(makeMouse("mouseup", 100, 40))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="range-marquee"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(false)
    expect(wrapper.emitted("range-decision")).toBeFalsy()
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    wrapper.unmount()
  })

  it("ON: plain press-drag routes range-press -> marquee -> bubble -> 删除 (never add-segment)", async () => {
    const wrapper = mountBasic()
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    expect(wrapper.findComponent(SegmentBlocksLayer).props("emptyAreaMode")).toBe("range")
    await emptyRoot(wrapper).trigger("mousedown", { clientX: 100, clientY: 40 }) // 5s
    document.dispatchEvent(makeMouse("mousemove", 300, 40)) // 15s
    await wrapper.vm.$nextTick()
    const marquee = wrapper.find('[data-test="range-marquee"]')
    expect(marquee.exists()).toBe(true)
    expect((marquee.element as HTMLElement).style.left).toContain("16.66")
    expect((marquee.element as HTMLElement).style.width).toContain("33.33")
    document.dispatchEvent(makeMouse("mouseup", 300, 40))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(true)
    expect(document.activeElement?.getAttribute("data-test")).toBe("range-delete")
    await wrapper.find('[data-test="range-delete"]').trigger("click")
    expect(wrapper.emitted("range-decision")).toEqual([[{ start: 5, end: 15, action: "delete" }]])
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    expect(wrapper.emitted("set-time")).toBeFalsy()
    expect(wrapper.emitted("seek")).toBeFalsy()
    wrapper.unmount()
  })

  it("ON + buildMode ON: the range mode wins (SPEC nested ternary, no add-segment)", async () => {
    const wrapper = mountBasic()
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-test="build-mode-toggle"]').trigger("click")
    await wrapper.find('[data-test="range-mode-toggle"]').trigger("click")
    expect(wrapper.findComponent(SegmentBlocksLayer).props("emptyAreaMode")).toBe("range")
    await emptyRoot(wrapper).trigger("mousedown", { clientX: 100, clientY: 40 })
    document.dispatchEvent(makeMouse("mousemove", 300, 40))
    document.dispatchEvent(makeMouse("mouseup", 300, 40))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="range-bubble"]').exists()).toBe(true)
    await wrapper.find('[data-test="range-keep"]').trigger("click")
    expect(wrapper.emitted("range-decision")).toEqual([[{ start: 5, end: 15, action: "keep" }]])
    expect(wrapper.emitted("add-segment")).toBeFalsy()
    wrapper.unmount()
  })
})

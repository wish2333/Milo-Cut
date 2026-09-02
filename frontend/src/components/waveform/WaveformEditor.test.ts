import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from "vitest"
import { mount } from "@vue/test-utils"
import WaveformEditor from "./WaveformEditor.vue"
import WaveformRow from "./WaveformRow.vue"
import { formatTimeShort } from "@/utils/format"
import { ROW_LAYOUT_STORAGE_KEY, WHEEL_DEBOUNCE_MS } from "@/composables/useRowLayout"

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
    trustedScroll(el, true) // first trusted event: echo of our write (no cooldown)
    trustedScroll(el, true) // second: no pending target -> genuine manual -> cooldown
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

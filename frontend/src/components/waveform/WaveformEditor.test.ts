import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach } from "vitest"
import { mount } from "@vue/test-utils"
import WaveformEditor from "./WaveformEditor.vue"
import WaveformRow from "./WaveformRow.vue"
import { formatTimeShort } from "@/utils/format"
import { ROW_LAYOUT_STORAGE_KEY } from "@/composables/useRowLayout"

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

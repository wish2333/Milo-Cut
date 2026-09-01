import { describe, it, expect, beforeAll, afterAll } from "vitest"
import { mount } from "@vue/test-utils"
import WaveformEditor from "./WaveformEditor.vue"
import { formatTimeShort } from "@/utils/format"

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

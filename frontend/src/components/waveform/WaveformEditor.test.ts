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

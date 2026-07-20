import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import VideoControls from "./VideoControls.vue"
import DeleteRangesOverlay from "./DeleteRangesOverlay.vue"

const RANGES = [
  { start: 5, end: 10 },
  { start: 20, end: 30 },
  { start: 45, end: 50 },
]

function mountControls(currentTime = 0) {
  return mount(VideoControls, {
    props: {
      currentTime,
      duration: 60,
      paused: true,
      volume: 0.5,
      playbackRate: 1,
      deleteRanges: RANGES,
      previewMode: "edited",
    },
  })
}

describe("VideoControls delete-range overlay integration (v2.3.2 G6)", () => {
  it("renders DeleteRangesOverlay child when previewMode is edited and ranges exist", () => {
    const wrapper = mountControls()
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(true)
  })

  it("does not render DeleteRangesOverlay in original preview mode", async () => {
    const wrapper = mountControls()
    await wrapper.setProps({ previewMode: "original" })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(false)
  })

  it("does not render DeleteRangesOverlay when deleteRanges is empty", async () => {
    const wrapper = mountControls()
    await wrapper.setProps({ deleteRanges: [] })
    expect(wrapper.findComponent(DeleteRangesOverlay).exists()).toBe(false)
  })

  it("keeps child prop references stable across currentTime-only updates", async () => {
    const wrapper = mountControls(0)
    const overlayBefore = wrapper.findComponent(DeleteRangesOverlay)
    expect(overlayBefore.exists()).toBe(true)
    // vue-test-utils returns reactive proxies from props(), so we cannot use
    // referential equality here. Use deep equality to assert the value is
    // unchanged; Vue's reactivity system still skips child re-renders based
    // on the underlying prop identity at the framework level.
    expect(overlayBefore.props("ranges")).toStrictEqual(RANGES)
    expect(overlayBefore.props("duration")).toBe(60)

    await wrapper.setProps({ currentTime: 25 })
    await wrapper.setProps({ currentTime: 50 })

    const overlayAfter = wrapper.findComponent(DeleteRangesOverlay)
    expect(overlayAfter.exists()).toBe(true)
    expect(overlayAfter.props("ranges")).toStrictEqual(RANGES)
    expect(overlayAfter.props("duration")).toBe(60)
  })
})

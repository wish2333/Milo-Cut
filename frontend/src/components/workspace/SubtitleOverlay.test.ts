/**
 * v3.0.1 M6-2: secondary (extension-track) subtitle overlay.
 *
 * The component drives off a real <video> element; these tests mount with
 * a stubbed video-like object (the component only reads currentTime and
 * attaches listeners). happy-dom provides HTMLMediaElement.
 */
import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import type { Segment, SubtitleTrack, TrackBinding } from "@/types/project"
import SubtitleOverlay from "./SubtitleOverlay.vue"

function seg(id: string, start: number, end: number, text: string): Segment {
  return { id, version: 1, type: "subtitle", start, end, text, speaker: "" }
}

function makeVideo(t: number) {
  const el = document.createElement("video")
  Object.defineProperty(el, "currentTime", { value: t, configurable: true })
  Object.defineProperty(el, "paused", { value: true, configurable: true })
  return el
}

const MAIN = [
  seg("s1", 0, 2, "你好"),
  seg("s2", 3, 5, "世界"),
]
const EXT_TRACK: SubtitleTrack = {
  id: "trk1",
  role: "extension",
  name: "en",
  language: "en",
  segments: [seg("e1", 0.2, 2.2, "hello"), seg("e2", 3.2, 5.0, "world")],
}
const BINDINGS: TrackBinding[] = [
  { id: "b1", track_id: "trk1", main_segment_id: "s1", extension_segment_id: "e1", start_offset: 0.2, end_offset: 0.2 },
  // e2 is NOT bound to s2 (drifted away) -> no secondary line for s2
]

async function mountOverlay(t: number, opts: { secondary?: boolean } = {}) {
  const video = makeVideo(t)
  const wrapper = mount(SubtitleOverlay, {
    props: {
      segments: MAIN,
      videoRef: video,
      secondary:
        opts.secondary === false
          ? null
          : { tracks: [EXT_TRACK], bindings: BINDINGS },
      showSecondary: opts.secondary !== false,
    },
  })
  // the timeupdate listener reads currentTime synchronously; the reactive
  // render lands on the next tick.
  video.dispatchEvent(new Event("timeupdate"))
  await wrapper.vm.$nextTick()
  return { wrapper, video }
}

describe("SubtitleOverlay secondary line (M6-2)", () => {
  it("renders the bound extension text under the main line", async () => {
    const { wrapper } = await mountOverlay(1.0)
    expect(wrapper.text()).toContain("你好")
    const secondary = wrapper.find('[data-test="secondary-subtitle"]')
    expect(secondary.exists()).toBe(true)
    expect(secondary.text()).toBe("hello")
    wrapper.unmount()
  })

  it("shows no secondary line for an unbound main segment", async () => {
    const { wrapper } = await mountOverlay(4.0)
    expect(wrapper.text()).toContain("世界")
    expect(wrapper.find('[data-test="secondary-subtitle"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("hides the secondary line when the setting is off", async () => {
    const { wrapper, video } = await mountOverlay(1.0, { secondary: true })
    // re-render with showSecondary=false
    wrapper.setProps({ showSecondary: false })
    await wrapper.vm.$nextTick()
    // timeupdate re-fires after the flip via the watcher
    video.dispatchEvent(new Event("timeupdate"))
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain("你好")
    expect(wrapper.find('[data-test="secondary-subtitle"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("shows nothing when no secondary data is provided at all", async () => {
    const { wrapper } = await mountOverlay(1.0, { secondary: false })
    expect(wrapper.text()).toContain("你好")
    expect(wrapper.find('[data-test="secondary-subtitle"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

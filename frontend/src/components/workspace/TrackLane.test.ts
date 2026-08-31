import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import type { SubtitleTrack } from "@/types/project"
import TrackLane from "./TrackLane.vue"

function makeTrack(overrides: Partial<SubtitleTrack> = {}): SubtitleTrack {
  return {
    id: "trk_ab12cd34",
    role: "extension",
    name: "en.srt",
    language: "en",
    segments: [
      {
        id: `track_${overrides.id ?? "trk_ab12cd34"}_seg_1.000`,
        version: 1,
        type: "subtitle",
        start: 1.0,
        end: 2.0,
        text: "hello world",
        speaker: "",
      },
      {
        id: `track_${overrides.id ?? "trk_ab12cd34"}_seg_3.000`,
        version: 1,
        type: "subtitle",
        start: 3.0,
        end: 4.0,
        text: "second line",
        speaker: "",
      },
    ],
    ...overrides,
  }
}

describe("TrackLane", () => {
  it("renders nothing when there are no tracks", () => {
    const wrapper = mount(TrackLane, { props: { tracks: [] } })
    expect(wrapper.find('[data-test="track-lane"]').exists()).toBe(false)
  })

  it("renders read-only rows with timestamps and text", () => {
    const wrapper = mount(TrackLane, { props: { tracks: [makeTrack()] } })
    const rows = wrapper.findAll('[data-test^="track-row-"]')
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain("hello world")
    expect(wrapper.text()).toContain("0:01.0 - 0:02.0")
  })

  it("seeks on row click (read-only: no edit events)", async () => {
    const wrapper = mount(TrackLane, { props: { tracks: [makeTrack()] } })
    await wrapper.find('[data-test^="track-row-"]').trigger("click")
    expect(wrapper.emitted("seek")![0]).toEqual([1.0])
  })

  it("collapses and expands via the toggle", async () => {
    const wrapper = mount(TrackLane, { props: { tracks: [makeTrack()] } })
    expect(wrapper.findAll('[data-test^="track-row-"]').length).toBe(2)
    await wrapper.find('[data-test="track-lane"] button').trigger("click")
    expect(wrapper.findAll('[data-test^="track-row-"]').length).toBe(0)
    await wrapper.find('[data-test="track-lane"] button').trigger("click")
    expect(wrapper.findAll('[data-test^="track-row-"]').length).toBe(2)
  })

  it("shows track badges for multiple tracks", () => {
    const wrapper = mount(TrackLane, {
      props: {
        tracks: [makeTrack(), makeTrack({ id: "trk_2", name: "ja.srt", language: "ja" })],
      },
    })
    expect(wrapper.text()).toContain("副轨字幕 (2)")
    expect(wrapper.text()).toContain("en.srt · en")
    expect(wrapper.text()).toContain("ja.srt · ja")
  })
})

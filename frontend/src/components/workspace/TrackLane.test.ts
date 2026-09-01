/**
 * v3.0.1 M4-2: geometric lane tests (rewrite of the v3.0.0 read-only text
 * list suite). Anchors: percent positioning, collapse/hidden emits, empty
 * lane hint, badge content.
 */
import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import { computed, ref } from "vue"
import type { SubtitleTrack } from "@/types/project"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import type { LaneLayoutItem } from "@/composables/useLaneLayout"
import { TIMELINE_METRICS_KEY } from "@/components/waveform/injectionKeys"
import TrackLane from "./TrackLane.vue"

function makeTrack(overrides: Partial<SubtitleTrack> = {}): SubtitleTrack {
  const id = overrides.id ?? "trk_ab12cd34"
  return {
    id,
    role: "extension",
    name: "en.srt",
    language: "en",
    segments: [
      {
        id: `track_${id}_seg_1.000`,
        version: 1,
        type: "subtitle",
        start: 1.0,
        end: 2.0,
        text: "hello world",
        speaker: "",
      },
      {
        id: `track_${id}_seg_3.000`,
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

function makeLane(overrides: Partial<LaneLayoutItem> = {}): LaneLayoutItem {
  return { trackId: "trk_ab12cd34", top: 112, height: 48, collapsed: false, hidden: false, ...overrides }
}

function createMetrics() {
  const viewStart = ref(0)
  const viewDuration = ref(10)
  return {
    duration: ref(10),
    viewStart,
    viewDuration,
    viewEnd: computed(() => viewStart.value + viewDuration.value),
    timeToPercent: (time: number) => ((time - viewStart.value) / viewDuration.value) * 100,
    percentToPixels: () => 0,
    getTimeFromX: () => 0,
    clampViewStart: () => {},
    scrollTo: () => {},
    zoomAt: () => {},
    handleWheel: () => {},
    ensurePlayheadInView: () => {},
    maybeFollowPlayhead: () => {},
    playheadPercent: computed(() => 0),
    playheadVisible: computed(() => true),
    thumbLeft: computed(() => 0),
    thumbWidth: computed(() => 100),
    timeMarks: computed(() => []),
    minorTimeMarks: computed(() => []),
    containerRef: ref(null),
  } satisfies TimelineMetrics
}

function mountLane(track: SubtitleTrack, lane: LaneLayoutItem = makeLane()) {
  return mount(TrackLane, {
    props: { track, lane },
    global: {
      provide: { [TIMELINE_METRICS_KEY as symbol]: createMetrics() },
    },
  })
}

describe("TrackLane (geometric)", () => {
  it("renders as a positioned lane with height from the layout item", () => {
    const wrapper = mountLane(makeTrack())
    const lane = wrapper.find('[data-test="track-lane"]')
    expect(lane.exists()).toBe(true)
    expect((lane.element as HTMLElement).style.top).toBe("112px")
    expect((lane.element as HTMLElement).style.height).toBe("48px")
  })

  it("renders extension blocks percent-positioned in view", () => {
    const wrapper = mountLane(makeTrack())
    const blocks = wrapper.findAll(".rounded.border")
    expect(blocks).toHaveLength(2)
    // seg 1.0-2.0 in a 0-10s view -> left 10%, width 10%
    expect((blocks[0].element as HTMLElement).style.left).toBe("10%")
    expect((blocks[0].element as HTMLElement).style.width).toBe("10%")
    // extension blocks wear the secondary violet styling
    expect(blocks[0].classes().join(" ")).toContain("bg-violet-200")
    expect(wrapper.text()).toContain("hello world")
  })

  it("filters segments outside the view window", () => {
    const far = makeTrack({
      segments: [
        {
          id: "track_x_seg_20.000",
          version: 1,
          type: "subtitle",
          start: 20,
          end: 25,
          text: "offscreen",
          speaker: "",
        },
      ],
    })
    const w2 = mountLane(far)
    expect(w2.findAll(".rounded.border")).toHaveLength(0)
    w2.unmount()
  })

  it("shows the empty-lane hint for a track without segments", () => {
    const empty = makeTrack({ segments: [] })
    const wrapper = mountLane(empty)
    expect(wrapper.find('[data-test="lane-empty"]').exists()).toBe(true)
    expect(wrapper.findAll(".rounded.border")).toHaveLength(0)
  })

  it("emits seek with the segment start on block click", async () => {
    const wrapper = mountLane(makeTrack())
    await wrapper.findAll(".rounded.border")[0].trigger("click")
    expect(wrapper.emitted("seek")![0]).toEqual([1.0])
  })

  it("emits toggle-collapse from the title strip button", async () => {
    const wrapper = mountLane(makeTrack())
    await wrapper.find('[data-test="lane-collapse"]').trigger("click")
    expect(wrapper.emitted("toggle-collapse")![0]).toEqual(["trk_ab12cd34"])
  })

  it("hides the block area and shows a collapsed hint when collapsed", () => {
    const wrapper = mountLane(makeTrack(), makeLane({ collapsed: true, height: 24 }))
    expect(wrapper.find('[data-test="lane-blocks"]').exists()).toBe(false)
    expect(wrapper.text()).toContain("已折叠")
  })

  it("shows track badge with name and language", () => {
    const wrapper = mountLane(makeTrack())
    expect(wrapper.text()).toContain("en.srt · en")
    expect(wrapper.text()).toContain("2 段")
  })
})

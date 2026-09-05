import { describe, it, expect, beforeAll, afterAll } from "vitest"
import { mount, type VueWrapper } from "@vue/test-utils"
import { nextTick } from "vue"
import Timeline from "./Timeline.vue"
import { mockSegment } from "@/test/helpers/mockProject"
import type { Segment } from "@/types/project"

const ROW_H = 52 // TranscriptRow min-h (virtualList default)
const VIEW_H = 600

function longSegments(count: number): Segment[] {
  return Array.from({ length: count }, (_, i) =>
    mockSegment({
      id: `seg-${i + 1}`,
      start: i * 5 + 1,
      end: i * 5 + 5,
      text: `segment ${i + 1}`,
    }),
  )
}

function mountTimeline(segments: Segment[], extraProps: Record<string, unknown> = {}) {
  return mount(Timeline, {
    props: {
      segments,
      edits: [],
      analysisResults: [],
      subtitleCount: segments.filter((s) => s.type === "subtitle").length,
      silenceCount: segments.filter((s) => s.type === "silence").length,
      ...extraProps,
    },
    // Sidebar panels are out of scope here; stub to keep the mount light.
    global: {
      stubs: {
        SuggestionPanel: true,
        AIAssistantPanel: true,
        HighlightModeView: true,
        Transition: false,
      },
    },
  })
}

function listEl(wrapper: VueWrapper) {
  return wrapper.find('[data-test="segment-list"]')
}

function renderedIds(wrapper: VueWrapper): Set<string> {
  const ids = new Set<string>()
  for (const w of wrapper.findAll("[data-segment-id]")) {
    const id = w.attributes("data-segment-id")
    if (id) ids.add(id)
  }
  return ids
}

async function settle(wrapper: VueWrapper) {
  // rAF-throttled scroll handling + nextTick chains
  await new Promise((r) => setTimeout(r, 60))
  await wrapper.vm.$nextTick()
}

let clientHeightDescriptor: PropertyDescriptor | undefined

describe("Timeline virtual scrolling (M7-2)", () => {
  beforeAll(() => {
    // happy-dom reports clientHeight 0; give the scroll container a real
    // viewport so the window math has something to work with.
    clientHeightDescriptor = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "clientHeight",
    )
    Object.defineProperty(HTMLElement.prototype, "clientHeight", {
      configurable: true,
      get() {
        return this.hasAttribute?.("data-test") && this.getAttribute("data-test") === "segment-list"
          ? VIEW_H
          : 0
      },
    })
  })

  afterAll(() => {
    if (clientHeightDescriptor) {
      Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
    }
  })

  it("renders every row for a short list", () => {
    const wrapper = mountTimeline(longSegments(8))
    expect(renderedIds(wrapper).size).toBe(8)
  })

  it("renders only the window plus overscan for a long list", async () => {
    const wrapper = mountTimeline(longSegments(200))
    await settle(wrapper)
    const ids = renderedIds(wrapper)
    // viewport 600px ~= 12 rows, + 10 overscan per side -> well under half
    expect(ids.size).toBeLessThan(60)
    expect(ids.size).toBeGreaterThanOrEqual(12)
    expect(ids.has("seg-1")).toBe(true) // scrollTop 0 -> first row mounted
    // full-height spacer
    const spacer = wrapper.find(".relative[style]")
    expect(spacer.attributes("style")).toContain("10400px")
    wrapper.unmount()
  })

  it("shifts the window when the list scrolls", async () => {
    const wrapper = mountTimeline(longSegments(200))
    await settle(wrapper)
    const el = listEl(wrapper).element as HTMLElement
    el.scrollTop = 100 * ROW_H
    await listEl(wrapper).trigger("scroll")
    await settle(wrapper)
    const ids = renderedIds(wrapper)
    expect(ids.has("seg-1")).toBe(false)
    expect(ids.has("seg-101")).toBe(true) // row at scrollTop
    expect(ids.has("seg-91")).toBe(true) // overscan above (index 100 - 10)
    expect(ids.has("seg-122")).toBe(true) // overscan below
    expect(ids.size).toBeLessThan(60)
    wrapper.unmount()
  })

  it("positions the scroll for an out-of-view selected segment", async () => {
    const wrapper = mountTimeline(longSegments(200))
    await settle(wrapper)
    const el = listEl(wrapper).element as HTMLElement
    await wrapper.setProps({ selectedSegmentId: "seg-150" })
    // row below the viewport -> bottom edge aligned: offsets[150] - VIEW_H
    expect(el.scrollTop).toBe(150 * ROW_H - VIEW_H)
    // the browser then fires scroll; simulate and verify the window follows
    await listEl(wrapper).trigger("scroll")
    await settle(wrapper)
    const ids = renderedIds(wrapper)
    expect(ids.has("seg-150")).toBe(true)
    expect(ids.has("seg-1")).toBe(false)
    wrapper.unmount()
  })

  it("keeps an in-view selected segment without scrolling", async () => {
    const wrapper = mountTimeline(longSegments(200))
    await settle(wrapper)
    const el = listEl(wrapper).element as HTMLElement
    await wrapper.setProps({ selectedSegmentId: "seg-5" })
    expect(el.scrollTop).toBe(0)
    wrapper.unmount()
  })

  it("preserves an unsaved edit draft across virtual unmount/remount", async () => {
    const wrapper = mountTimeline(longSegments(200), { globalEditMode: true })
    await settle(wrapper)
    // type into the seg-2 input (global edit mode = every row is an input)
    const input = wrapper.find('[data-segment-id="seg-2"] input')
    expect(await input.exists()).toBe(true)
    await input.setValue("draft text for seg-2")
    // scroll far away so seg-2 unmounts
    const el = listEl(wrapper).element as HTMLElement
    el.scrollTop = 120 * ROW_H
    await listEl(wrapper).trigger("scroll")
    await settle(wrapper)
    expect(renderedIds(wrapper).has("seg-2")).toBe(false)
    // scroll back: the row remounts and restores the draft
    el.scrollTop = 0
    await listEl(wrapper).trigger("scroll")
    await settle(wrapper)
    expect(renderedIds(wrapper).has("seg-2")).toBe(true)
    const restored = wrapper.find('[data-segment-id="seg-2"] input')
    expect((restored.element as HTMLInputElement).value).toBe("draft text for seg-2")
    wrapper.unmount()
  })

  it("renders mixed subtitle and silence rows through the type dispatch", async () => {
    const segments = [
      mockSegment({ id: "a1", type: "subtitle", start: 1, end: 5, text: "first" }),
      mockSegment({ id: "s1", type: "silence", start: 5, end: 8 }),
      mockSegment({ id: "a2", type: "subtitle", start: 8, end: 12, text: "second" }),
    ]
    const wrapper = mountTimeline(segments)
    await settle(wrapper)
    const ids = renderedIds(wrapper)
    expect(ids.has("a1")).toBe(true)
    expect(ids.has("s1")).toBe(true)
    expect(ids.has("a2")).toBe(true)
    expect(wrapper.text()).toContain("静音")
    // spacer height accounts for per-type heights: 52 + 36 + 52
    const spacer = wrapper.find(".relative[style]")
    expect(spacer.attributes("style")).toContain("140px")
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// v3.0.3 M1-1: list track selector (header segmented control). Pure view
// state: the component only re-emits select-track; the parent owns the
// data-source switch.
// ---------------------------------------------------------------------------
describe("Timeline list track selector (M1-1)", () => {
  const trackOptions = [
    { id: "t_en", name: "English", segmentCount: 2 },
    { id: "t_zh", name: "中文翻译", segmentCount: 0 },
  ]

  it("renders no selector without tracks (main-track branch zero diff)", () => {
    const wrapper = mountTimeline(longSegments(3))
    expect(wrapper.find('[data-test="list-track-selector"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("renders main + first track as buttons; further tracks live in the dropdown", () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: null,
    })
    const selector = wrapper.find('[data-test="list-track-selector"]')
    expect(selector.exists()).toBe(true)
    expect(wrapper.find('[data-test="select-main-track"]').exists()).toBe(true)
    // first track keeps its segmented button + live count badge
    expect(wrapper.find('[data-test="select-track-t_en"]').text()).toContain("English")
    expect(wrapper.find('[data-test="track-count-t_en"]').text()).toBe("2")
    // second track is NOT a button anymore -- it lives in the dropdown menu
    expect(wrapper.find('[data-test="select-track-t_zh"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="track-more"]').exists()).toBe(true)
    const menuZh = wrapper.find('[data-test="select-track-menu-t_zh"]')
    expect(menuZh.text()).toContain("中文翻译")
    expect(menuZh.text()).toContain("0")
    wrapper.unmount()
  })

  it("single-track projects keep the plain segmented selector (no dropdown)", () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: [trackOptions[0]],
      activeTrackId: null,
    })
    expect(wrapper.find('[data-test="select-track-t_en"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="track-more"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("picking from the dropdown emits select-track and closes the menu", async () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: null,
    })
    await wrapper.find('[data-test="select-track-menu-t_zh"]').trigger("click")
    expect(wrapper.emitted("select-track")?.[0]).toEqual(["t_zh"])
    expect(wrapper.find('[data-test="track-more"]').attributes("open")).toBeUndefined()
    wrapper.unmount()
  })

  it("an active overflow track shows its name in the dropdown trigger", () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: "t_zh",
    })
    const toggle = wrapper.find('[data-test="track-more-toggle"]')
    expect(toggle.text()).toContain("中文翻译")
    expect(toggle.classes()).toContain("bg-gray-700")
    expect(wrapper.find('[data-test="track-count-t_zh"]').text()).toBe("0")
    wrapper.unmount()
  })

  it("marks the main track active by default and on null", () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: null,
    })
    expect(wrapper.find('[data-test="select-main-track"]').classes()).toContain("bg-gray-700")
    expect(wrapper.find('[data-test="select-track-t_en"]').classes()).not.toContain("bg-gray-700")
    wrapper.unmount()
  })

  it("moves the active mark to the selected track", () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: "t_en",
    })
    expect(wrapper.find('[data-test="select-track-t_en"]').classes()).toContain("bg-gray-700")
    expect(wrapper.find('[data-test="select-main-track"]').classes()).not.toContain("bg-gray-700")
    wrapper.unmount()
  })

  it("emits select-track with the track id / null (round-trip payload)", async () => {
    const wrapper = mountTimeline(longSegments(3), {
      tracks: trackOptions,
      activeTrackId: null,
    })
    await wrapper.find('[data-test="select-track-t_en"]').trigger("click")
    expect(wrapper.emitted("select-track")?.[0]).toEqual(["t_en"])
    await wrapper.setProps({ activeTrackId: "t_en" })
    await wrapper.find('[data-test="select-main-track"]').trigger("click")
    expect(wrapper.emitted("select-track")?.[1]).toEqual([null])
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// v3.0.3 M1-2: track-mode list rendering + empty-track create entry.
// ---------------------------------------------------------------------------
describe("Timeline track list rendering (M1-2)", () => {
  const trackSegments = [
    mockSegment({ id: "en-1", start: 1, end: 4, text: "hello" }),
    mockSegment({ id: "en-2", start: 6, end: 9, text: "world" }),
  ]

  function mountTrackList(segments: Segment[], extraProps: Record<string, unknown> = {}) {
    return mountTimeline(segments, {
      tracks: [{ id: "t_en", name: "English", segmentCount: segments.length }],
      activeTrackId: "t_en",
      ...extraProps,
    })
  }

  it("renders track rows through the same list dispatch", async () => {
    const wrapper = mountTrackList(trackSegments)
    await settle(wrapper)
    expect(renderedIds(wrapper)).toEqual(new Set(["en-1", "en-2"]))
    // duration chips visible (track variant active)
    expect(wrapper.find('[data-test="track-duration"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it("marks bound segments with the binding icon", async () => {
    const wrapper = mountTrackList(trackSegments, {
      bindings: [{ id: "b1", track_id: "t_en", main_segment_id: "main-1", extension_segment_id: "en-1", start_offset: 0, end_offset: 0 }],
    })
    await settle(wrapper)
    const boundRow = wrapper.find('[data-segment-id="en-1"]')
    expect(boundRow.find('[data-test="track-bound-mark"]').exists()).toBe(true)
    const unboundRow = wrapper.find('[data-segment-id="en-2"]')
    expect(unboundRow.find('[data-test="track-bound-mark"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("renders the main-track empty state when the MAIN list is empty (zero diff)", () => {
    const wrapper = mountTimeline([])
    expect(wrapper.text()).toContain("暂无字幕片段")
    expect(wrapper.find('[data-test="track-empty-state"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("renders the empty-track card with a create entry for an empty extension track", async () => {
    const wrapper = mountTrackList([], { currentTime: 12.5 })
    await settle(wrapper)
    const card = wrapper.find('[data-test="track-empty-state"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain("该副轨暂无字幕")
    await wrapper.find('[data-test="track-empty-create"]').trigger("click")
    expect(wrapper.emitted("create-track-segment")?.[0]).toEqual(["t_en", 12.5])
    wrapper.unmount()
  })

  it("main mode never shows the track empty card", () => {
    const wrapper = mountTimeline([])
    expect(wrapper.find('[data-test="track-empty-state"]').exists()).toBe(false)
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// v3.0.3 M1-3/M1-4: track-row edit/delete events forwarded with trackId.
// ---------------------------------------------------------------------------
describe("Timeline track row edit forwarding (M1-3/M1-4)", () => {
  const trackSegments = [
    mockSegment({ id: "en-1", start: 1, end: 4, text: "hello" }),
  ]

  function mountTrackList(extraProps: Record<string, unknown> = {}) {
    return mountTimeline(trackSegments, {
      tracks: [{ id: "t_en", name: "English", segmentCount: trackSegments.length }],
      activeTrackId: "t_en",
      ...extraProps,
    })
  }

  it("forwards row text commit as update-track-text with trackId", async () => {
    const wrapper = mountTrackList()
    await settle(wrapper)
    await wrapper.find('[data-segment-id="en-1"]').trigger("dblclick")
    const input = wrapper.find('[data-segment-id="en-1"] input.edit-text-input')
    expect(input.exists()).toBe(true)
    await input.setValue("changed")
    await input.trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("update-track-text")?.[0]).toEqual(["t_en", "en-1", "changed"])
    wrapper.unmount()
  })

  it("forwards row time commit as update-track-time with trackId", async () => {
    const wrapper = mountTrackList()
    await settle(wrapper)
    await wrapper.find('[data-segment-id="en-1"] [data-test="track-end"]').trigger("mousedown", { button: 0 })
    const input = wrapper.find('[data-segment-id="en-1"] input')
    await input.setValue("00:06.000")
    await input.trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("update-track-time")?.[0]).toEqual(["t_en", "en-1", "end", 6])
    wrapper.unmount()
  })

  it("forwards 删除此条字幕 as delete-track-segment with trackId", async () => {
    const wrapper = mountTrackList()
    await settle(wrapper)
    await wrapper.find('[data-segment-id="en-1"]').trigger("contextmenu")
    const del = document.body.querySelector('[data-test="track-menu-delete"]') as HTMLButtonElement
    del.click()
    await nextTick()
    expect(wrapper.emitted("delete-track-segment")?.[0]).toEqual(["t_en", "en-1"])
    wrapper.unmount()
  })
})

describe("Timeline empty-track create backfill (M1-2: patch tracks 层回填)", () => {
  it("a new segment arriving via the tracks patch replaces the empty card immediately", async () => {
    const wrapper = mountTimeline([], {
      tracks: [{ id: "t_en", name: "English", segmentCount: 0 }],
      activeTrackId: "t_en",
      currentTime: 12.5,
    })
    await wrapper.vm.$nextTick()
    // empty state first; the create entry emits with the playback anchor
    expect(wrapper.find('[data-test="track-empty-state"]').exists()).toBe(true)
    await wrapper.find('[data-test="track-empty-create"]').trigger("click")
    expect(wrapper.emitted("create-track-segment")?.[0]).toEqual(["t_en", 12.5])

    // parent applies the returned patch -> tracks/segments props update
    await wrapper.setProps({
      segments: [mockSegment({ id: "en-new", start: 12.5, end: 14.5, text: "new cue" })],
      tracks: [{ id: "t_en", name: "English", segmentCount: 1 }],
    })
    expect(wrapper.find('[data-test="track-empty-state"]').exists()).toBe(false)
    expect(wrapper.find('[data-segment-id="en-new"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("new cue")
    wrapper.unmount()
  })
})

// ---------------------------------------------------------------------------
// v3.0.4 M2-4 B: highlight tab gating (R3 must-fix #2). The highlight entry
// is THIS third tab (not an AIAssistantPanel card): in track mode it is
// greyed out -- disabled + title「仅主轨可用」-- never hidden (three-tab
// layout stays stable), and resting on it when track mode turns on falls
// back to the ungated suggestion tab.
// ---------------------------------------------------------------------------
describe("Timeline highlight tab gating (M2-4)", () => {
  const trackProps = {
    tracks: [{ id: "t_en", name: "English", segmentCount: 3 }],
  }

  it("greys out the highlight tab in track mode (disabled + title) and blocks the switch", async () => {
    const wrapper = mountTimeline(longSegments(3), { ...trackProps, activeTrackId: "t_en" })
    const highlight = wrapper.find('[data-test="sidebar-tab-highlight"]')
    expect(highlight.attributes("disabled")).toBeDefined()
    expect(highlight.attributes("title")).toBe("仅主轨可用")
    expect(highlight.classes()).toContain("opacity-50")
    // trigger bypasses the disabled attr in happy-dom -- the guarded switch
    // must not land on the gated tab
    await highlight.trigger("click")
    expect(highlight.classes()).not.toContain("bg-primary-soft")
    // suggestion tab stays open and ungated in track mode
    const suggestion = wrapper.find('[data-test="sidebar-tab-suggestion"]')
    expect(suggestion.attributes("disabled")).toBeUndefined()
    expect(suggestion.classes()).toContain("bg-primary-soft")
    wrapper.unmount()
  })

  it("falls back to suggestion when track mode turns on while highlight is open", async () => {
    const wrapper = mountTimeline(longSegments(3), trackProps)
    await wrapper.find('[data-test="sidebar-tab-highlight"]').trigger("click")
    expect(wrapper.find('[data-test="sidebar-tab-highlight"]').classes()).toContain("bg-primary-soft")

    await wrapper.setProps({ activeTrackId: "t_en" })
    await nextTick()
    // never rest on the disabled view: activeTab falls back automatically
    expect(wrapper.find('[data-test="sidebar-tab-suggestion"]').classes()).toContain("bg-primary-soft")
    expect(wrapper.find('[data-test="sidebar-tab-highlight"]').classes()).not.toContain("bg-primary-soft")
    wrapper.unmount()
  })

  it("keeps the highlight tab fully enabled in main-track view (zero regression)", async () => {
    const wrapper = mountTimeline(longSegments(3), trackProps)
    const highlight = wrapper.find('[data-test="sidebar-tab-highlight"]')
    expect(highlight.attributes("disabled")).toBeUndefined()
    expect(highlight.classes()).not.toContain("opacity-50")
    await highlight.trigger("click")
    expect(highlight.classes()).toContain("bg-primary-soft")
    wrapper.unmount()
  })
})

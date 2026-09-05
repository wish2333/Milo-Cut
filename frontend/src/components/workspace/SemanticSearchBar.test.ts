/**
 * SemanticSearchBar tests (v3.0.4 M3-3 / P3-4).
 *
 * Backend semantic_search always searches the MAIN track. In track mode
 * `segments` carries the extension track's list, so the lookup map must
 * be built from `mainSegments` (main-track ids) while the no-prop path
 * stays identical to v3.0.3.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount, flushPromises } from "@vue/test-utils"
import { call } from "@/bridge"
import type { Segment } from "@/types/project"
import SemanticSearchBar from "./SemanticSearchBar.vue"

// Mock bridge
vi.mock("@/bridge", () => ({
  call: vi.fn(),
  onEvent: vi.fn(),
}))

function makeSegment(overrides: Partial<Segment> & { id: string }): Segment {
  return {
    version: 1,
    type: "subtitle",
    start: 0,
    end: 1,
    text: "",
    speaker: "",
    ...overrides,
  }
}

function mockSearchResults(results: { segment_id: string; relevance: number; match_reason?: string }[]) {
  vi.mocked(call).mockResolvedValue({
    success: true,
    data: { results, query: "q" },
  })
}

async function runSearch(wrapper: ReturnType<typeof mount>, queryText: string) {
  await wrapper.find('input[type="text"]').setValue(queryText)
  await wrapper.find("button").trigger("click")
  await flushPromises()
}

describe("SemanticSearchBar", () => {
  beforeEach(() => {
    vi.mocked(call).mockReset()
  })

  it("track mode: resolves result text and seek time from mainSegments (main-track ids)", async () => {
    // Track mode: segments = extension track, mainSegments = main track.
    const trackSegments = [makeSegment({ id: "track-1", start: 100, end: 105, text: "副轨翻译文本" })]
    const mainSegments = [makeSegment({ id: "main-1", start: 12.5, end: 20, text: "主轨命中段落：讲性能优化的部分" })]
    mockSearchResults([{ segment_id: "main-1", relevance: 0.87, match_reason: "语义匹配" }])

    const wrapper = mount(SemanticSearchBar, {
      props: { segments: trackSegments, mainSegments, llmConfigured: true },
    })
    await runSearch(wrapper, "性能优化")

    // Result text comes from the main-track segment (non-empty preview).
    expect(wrapper.text()).toContain("主轨命中段落：讲性能优化的部分")

    // Click locates the main-track hit segment (seek with its start time).
    const hit = wrapper.find(".cursor-pointer")
    expect(hit.exists()).toBe(true)
    await hit.trigger("click")
    expect(wrapper.emitted("seek")).toEqual([[12.5]])
  })

  it("track mode: same id in both lists resolves against the main track", async () => {
    // Map must be built from mainSegments only, never merged with segments.
    const trackSegments = [makeSegment({ id: "seg-x", start: 50, end: 55, text: "TRACK LIST TEXT" })]
    const mainSegments = [makeSegment({ id: "seg-x", start: 8.25, end: 9, text: "MAIN LIST TEXT" })]
    mockSearchResults([{ segment_id: "seg-x", relevance: 0.9 }])

    const wrapper = mount(SemanticSearchBar, {
      props: { segments: trackSegments, mainSegments, llmConfigured: true },
    })
    await runSearch(wrapper, "x")

    expect(wrapper.text()).toContain("MAIN LIST TEXT")
    expect(wrapper.text()).not.toContain("TRACK LIST TEXT")
    await wrapper.find(".cursor-pointer").trigger("click")
    expect(wrapper.emitted("seek")).toEqual([[8.25]])
  })

  it("main-track mode: without mainSegments the map falls back to segments (v3.0.3 behavior)", async () => {
    const mainTrackSegments = [makeSegment({ id: "s1", start: 1, end: 5, text: "hello world" })]
    mockSearchResults([{ segment_id: "s1", relevance: 0.75 }])

    const wrapper = mount(SemanticSearchBar, {
      props: { segments: mainTrackSegments, llmConfigured: true },
    })
    await runSearch(wrapper, "hello")

    expect(wrapper.text()).toContain("hello world")
    await wrapper.find(".cursor-pointer").trigger("click")
    expect(wrapper.emitted("seek")).toEqual([[1]])
  })
})

import { describe, it, expect, beforeAll, afterAll } from "vitest"
import { mount, type VueWrapper } from "@vue/test-utils"
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

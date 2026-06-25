/**
 * HighlightModeView integration tests.
 *
 * Tests highlight display, duration summary, jump-cut warnings,
 * start extraction flow, and empty/loading states.
 */
import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import HighlightModeView from "./HighlightModeView.vue"
import { mockSegment } from "@/test/helpers/mockProject"

describe("HighlightModeView", () => {
  const segments = [
    mockSegment({ id: "seg-1", start: 0, end: 5, text: "intro" }),
    mockSegment({ id: "seg-2", start: 10, end: 20, text: "main point" }),
    mockSegment({ id: "seg-3", start: 30, end: 40, text: "conclusion" }),
  ]

  const highlights = [
    { segment_id: "seg-2", highlight_reason: "core argument", density: "high" as const },
    { segment_id: "seg-1", highlight_reason: "good intro", density: "medium" as const },
  ]

  it("shows empty state when no highlights", () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights: [], segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("暂无高光片段")
  })

  it("shows warning when LLM not configured", () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights: [], segments, llmConfigured: false },
    })
    expect(wrapper.text()).toContain("请先在设置中配置")
  })

  it("renders highlights sorted by start time", () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights, segments, llmConfigured: true },
    })
    // seg-1 (start=0) should appear before seg-2 (start=10)
    const text = wrapper.text()
    const introIdx = text.indexOf("good intro")
    const mainIdx = text.indexOf("core argument")
    expect(introIdx).toBeLessThan(mainIdx)
  })

  it("shows density dot with title and segment text", () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights, segments, llmConfigured: true },
    })
    // Density is now shown as colored dots with title attributes
    const dots = wrapper.findAll("span.rounded-full")
    expect(dots.length).toBeGreaterThanOrEqual(2)
    // Check title attributes (not text content since dots are visual)
    const titles = dots.map(d => d.attributes("title")).filter(Boolean)
    expect(titles).toContain("高密度")
    expect(titles).toContain("中密度")
    // Segment text should be displayed alongside the time
    expect(wrapper.text()).toContain("intro")
    expect(wrapper.text()).toContain("main point")
  })

  it("shows duration summary", () => {
    const wrapper = mount(HighlightModeView, {
      props: {
        highlights,
        segments,
        totalDuration: 15,
        targetDuration: 60,
        llmConfigured: true,
      },
    })
    expect(wrapper.text()).toContain("已选 15s / 目标 60s")
  })

  it("shows jump cut warnings", () => {
    const wrapper = mount(HighlightModeView, {
      props: {
        highlights,
        segments,
        jumpCuts: [
          { index: 0, gap_duration: 5, from_end: 5, to_start: 10 },
        ],
        llmConfigured: true,
      },
    })
    expect(wrapper.text()).toContain("检测到 1 处跳切")
  })

  it("shows loading progress bar", () => {
    const wrapper = mount(HighlightModeView, {
      props: {
        highlights: [],
        segments,
        loading: true,
        progress: 50,
        llmConfigured: true,
      },
    })
    expect(wrapper.text()).toContain("正在提取")
    expect(wrapper.find('[style*="width"]').exists()).toBe(true)
  })

  it("emits start-highlight with target minutes", async () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights: [], segments, llmConfigured: true },
    })
    const input = wrapper.find('input[type="number"]')
    await input.setValue(5)
    const btn = wrapper.findAll("button").find((b) => b.text().includes("开始提取"))
    await btn!.trigger("click")
    expect(wrapper.emitted("start-highlight")).toBeTruthy()
    expect(wrapper.emitted("start-highlight")![0]).toEqual([5])
  })

  it("emits seek on highlight time click", async () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights, segments, llmConfigured: true },
    })
    const timeLinks = wrapper.findAll("button").filter((b) =>
      /\d+:\d+/.test(b.text()),
    )
    expect(timeLinks.length).toBeGreaterThan(0)
    await timeLinks[0].trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
  })

  it("counts highlight segments in header", () => {
    const wrapper = mount(HighlightModeView, {
      props: { highlights, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("2 个高光片段")
  })
})

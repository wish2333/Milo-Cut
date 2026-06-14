/**
 * SubtitleCorrectionReview integration tests.
 *
 * Tests correction display, diff view, accept/reject flow,
 * high-confidence batch accept, and category badges.
 */
import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import SubtitleCorrectionReview from "./SubtitleCorrectionReview.vue"
import { mockSegment } from "@/test/helpers/mockProject"

describe("SubtitleCorrectionReview", () => {
  const segments = [
    mockSegment({ id: "seg-1", start: 0, end: 5, text: "这是错字" }),
    mockSegment({ id: "seg-2", start: 10, end: 20, text: "正确文字" }),
    mockSegment({ id: "seg-3", start: 30, end: 40, text: "另一个错" }),
  ]

  const corrections = [
    {
      segment_id: "seg-1",
      corrected_text: "这是正字",
      changes: ["正"],
      category: "homophone",
      confidence: 0.95,
    },
    {
      segment_id: "seg-3",
      corrected_text: "另一个对",
      changes: ["对"],
      category: "homophone",
      confidence: 0.3,
    },
  ]

  it("shows empty state with start button when no corrections", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections: [], segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("开始字幕修正")
  })

  it("shows warning when LLM not configured", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections: [], segments, llmConfigured: false },
    })
    expect(wrapper.text()).toContain("请先在设置中配置")
  })

  it("renders corrections sorted by start time", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    // seg-1 (start=0) before seg-3 (start=30)
    const text = wrapper.text()
    expect(text.indexOf("这是正字")).toBeLessThan(text.indexOf("另一个对"))
  })

  it("shows diff view with original (strikethrough) and corrected text", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("这是错字")
    expect(wrapper.text()).toContain("这是正字")
  })

  it("shows category badge", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("同音错字")
  })

  it("shows confidence label", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("高置信度")
    expect(wrapper.text()).toContain("低置信度")
  })

  it("splits high and low confidence sections", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("高置信度修正")
    // Low confidence section
    expect(wrapper.text()).toContain("低置信度")
  })

  it("counts corrections and pending in header", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("2 条修正")
    expect(wrapper.text()).toContain("2 待审阅")
  })

  it("shows accept/reject buttons for pending items", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    const acceptBtns = wrapper.findAll("button").filter((b) =>
      b.text().includes("接受"),
    )
    expect(acceptBtns.length).toBeGreaterThan(0)
  })

  it("shows trust high-confidence button with count", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("信任高置信度")
    expect(wrapper.text()).toContain("(1)")
  })

  it("shows partial warning when uncoveredIds provided", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: {
        corrections,
        segments,
        uncoveredIds: ["seg-2"],
        partial: true,
        llmConfigured: true,
      },
    })
    expect(wrapper.text()).toContain("1 个片段未被修正覆盖")
  })

  it("shows loading progress", () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: {
        corrections: [],
        segments,
        loading: true,
        progress: 60,
        llmConfigured: true,
      },
    })
    expect(wrapper.text()).toContain("正在分析字幕")
    expect(wrapper.find("progress").exists()).toBe(true)
  })

  it("emits start-correction with reference text", async () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections: [], segments, llmConfigured: true },
    })
    const btn = wrapper.findAll("button").find((b) =>
      b.text().includes("开始字幕修正"),
    )
    await btn!.trigger("click")
    expect(wrapper.emitted("start-correction")).toBeTruthy()
    // Empty reference text (mode A)
    expect(wrapper.emitted("start-correction")![0]).toEqual([""])
  })

  it("emits seek on time link click", async () => {
    const wrapper = mount(SubtitleCorrectionReview, {
      props: { corrections, segments, llmConfigured: true },
    })
    const timeLinks = wrapper.findAll("button").filter((b) =>
      b.classes().some((c) => c.includes("link")),
    )
    expect(timeLinks.length).toBeGreaterThan(0)
    await timeLinks[0].trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
  })
})

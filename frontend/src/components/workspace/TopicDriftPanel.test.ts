import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import TopicDriftPanel from "./TopicDriftPanel.vue"
import type { Segment, TopicDriftResult } from "@/types/project"

const segments: Segment[] = [
  { id: "s1", version: 1, type: "subtitle", start: 0, end: 5, text: "Welcome to the talk", speaker: "" },
  { id: "s2", version: 1, type: "subtitle", start: 5, end: 10, text: "Unrelated tangent", speaker: "" },
  { id: "s3", version: 1, type: "subtitle", start: 10, end: 15, text: "Back on main topic", speaker: "" },
]

const results: TopicDriftResult[] = [
  { segment_id: "s1", topic: "intro", relevance: 0.9, confidence: 0.9, reason: "directly on topic" },
  { segment_id: "s2", topic: "tangent", relevance: 0.2, confidence: 0.8, reason: "off-topic" },
  { segment_id: "s3", topic: "main", relevance: 0.6, confidence: 0.7, reason: "somewhat relevant" },
]

describe("TopicDriftPanel", () => {
  it("renders empty state when no results", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results: [], segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("暂无分析结果")
  })

  it("renders results with segment text", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("Welcome to the talk")
    expect(wrapper.text()).toContain("Unrelated tangent")
    expect(wrapper.text()).toContain("Back on main topic")
  })

  it("sorts results by relevance ascending (lowest first)", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results, segments, llmConfigured: true },
    })
    const items = wrapper.findAll(".flex.items-start")
    // First item should be s2 (relevance 0.2 -- lowest)
    expect(items[0].text()).toContain("Unrelated tangent")
  })

  it("shows correct relevance color coding", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results, segments, llmConfigured: true },
    })
    // s2 has relevance 0.2 (< 0.4) -> red
    const badges = wrapper.findAll(".shrink-0.font-medium")
    const redBadge = badges.find((b) => b.text().includes("建议删除"))
    expect(redBadge).toBeTruthy()

    // s1 has relevance 0.9 (>= 0.7) -> green
    const greenBadge = badges.find((b) => b.text().includes("保留"))
    expect(greenBadge).toBeTruthy()
  })

  it("disables analyze button when LLM not configured", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results: [], segments, llmConfigured: false },
    })
    const btn = wrapper.find("button")
    expect(btn.attributes("disabled")).toBeDefined()
    expect(wrapper.text()).toContain("需要配置 LLM")
  })

  it("emits start-analysis with topic description", async () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results: [], segments, llmConfigured: true },
    })
    const input = wrapper.find("input")
    await input.setValue("AI in education")
    const btn = wrapper.find("button")
    await btn.trigger("click")
    expect(wrapper.emitted("start-analysis")).toBeTruthy()
    expect(wrapper.emitted("start-analysis")![0]).toEqual(["AI in education"])
  })

  it("emits seek when result item clicked", async () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results, segments, llmConfigured: true },
    })
    // Click on the first sorted item (s2, start=5)
    const items = wrapper.findAll(".flex.items-start")
    await items[0].trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
    expect(wrapper.emitted("seek")![0]).toEqual([5])
  })

  it("shows batch actions when low-relevance items exist", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results, segments, llmConfigured: true },
    })
    expect(wrapper.text()).toContain("接受删除建议 (1)")
  })

  it("hides batch actions when no low-relevance items", () => {
    const highResults: TopicDriftResult[] = [
      { segment_id: "s1", topic: "main", relevance: 0.9, confidence: 1, reason: "" },
    ]
    const wrapper = mount(TopicDriftPanel, {
      props: { results: highResults, segments, llmConfigured: true },
    })
    expect(wrapper.text()).not.toContain("接受删除建议")
  })

  it("shows progress bar when loading", () => {
    const wrapper = mount(TopicDriftPanel, {
      props: { results: [], segments, loading: true, progress: 50, llmConfigured: true },
    })
    expect(wrapper.find(".h-full.bg-blue-500").exists()).toBe(true)
  })
})

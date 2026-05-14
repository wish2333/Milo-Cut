import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import TranscriptRow from "./TranscriptRow.vue"
import type { Segment } from "@/types/project"

const baseSegment: Segment = {
  id: "seg-0001",
  version: 1,
  type: "subtitle",
  start: 1.0,
  end: 5.0,
  text: "Hello world",
  speaker: "",
}

describe("TranscriptRow", () => {
  it("renders segment text", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    expect(wrapper.text()).toContain("Hello world")
  })

  it("renders timestamp", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    expect(wrapper.text()).toContain("00:01")
  })

  it("emits seek on click", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    await wrapper.trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
    expect(wrapper.emitted("seek")![0]).toEqual([1.0])
  })

  it("shows pending status buttons", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, editStatus: "pending" },
    })
    expect(wrapper.text()).toContain("建议删除")
    expect(wrapper.text()).toContain("保留")
  })

  it("shows confirmed status with strikethrough class", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, editStatus: "confirmed" },
    })
    expect(wrapper.classes()).toContain("line-through")
  })

  it("applies selected ring style", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, isSelected: true },
    })
    expect(wrapper.classes()).toContain("ring-1")
  })

  it("enables inline editing on double click", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    await wrapper.trigger("dblclick")
    const input = wrapper.find("input")
    expect(input.exists()).toBe(true)
  })

  it("emits update-text on edit blur with changed text", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    await wrapper.trigger("dblclick")
    const input = wrapper.find("input")
    await input.setValue("Changed text")
    await input.trigger("blur")
    expect(wrapper.emitted("update-text")).toBeTruthy()
    expect(wrapper.emitted("update-text")![0]).toEqual(["seg-0001", "Changed text"])
  })
})

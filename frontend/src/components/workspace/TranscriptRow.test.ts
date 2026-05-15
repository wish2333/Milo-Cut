import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
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
      props: { segment: baseSegment, displayStatus: "pending" },
    })
    expect(wrapper.text()).toContain("建议删除")
    expect(wrapper.text()).toContain("保留")
  })

  it("shows confirmed status with strikethrough class", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, displayStatus: "confirmed", styleClass: "masked" },
    })
    expect(wrapper.classes()).toContain("line-through")
  })

  it("applies selected ring style", () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, isSelected: true },
    })
    expect(wrapper.classes()).toContain("ring-1")
  })

  it("enters edit mode on edit button click", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    expect(wrapper.find("input").exists()).toBe(true)
    expect(wrapper.find("input").element.value).toBe("Hello world")
  })

  it("emits update-text on save with changed text", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    const input = wrapper.find("input")
    await input.setValue("Changed text")
    const saveBtn = wrapper.find("[title='Save changes']")
    await saveBtn.trigger("click")
    expect(wrapper.emitted("update-text")).toBeTruthy()
    expect(wrapper.emitted("update-text")![0]).toEqual(["seg-0001", "Changed text"])
    expect(wrapper.find("input").exists()).toBe(false)
  })

  it("cancels edit on Esc and restores original text", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    const input = wrapper.find("input")
    await input.setValue("Changed text")
    await input.trigger("keydown", { key: "Escape" })
    expect(wrapper.emitted("update-text")).toBeFalsy()
    expect(wrapper.find("input").exists()).toBe(false)
    expect(wrapper.text()).toContain("Hello world")
  })

  it("saves edit on blur", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    const input = wrapper.find("input")
    await input.setValue("Changed text")
    await input.trigger("blur")
    expect(wrapper.emitted("update-text")).toBeTruthy()
    expect(wrapper.emitted("update-text")![0]).toEqual(["seg-0001", "Changed text"])
    expect(wrapper.find("input").exists()).toBe(false)
  })

  it("saves edit on row click and seeks", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    const input = wrapper.find("input")
    await input.setValue("Changed text")
    await wrapper.trigger("click")
    expect(wrapper.emitted("update-text")).toBeTruthy()
    expect(wrapper.emitted("update-text")![0]).toEqual(["seg-0001", "Changed text"])
    expect(wrapper.find("input").exists()).toBe(false)
    expect(wrapper.emitted("seek")).toBeTruthy()
    expect(wrapper.emitted("seek")![0]).toEqual([1.0])
  })

  it("enters edit mode when globalEditMode becomes true", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, globalEditMode: false },
    })
    expect(wrapper.find("input").exists()).toBe(false)
    await wrapper.setProps({ globalEditMode: true })
    expect(wrapper.find("input").exists()).toBe(true)
    expect(wrapper.find("input").element.value).toBe("Hello world")
  })

  it("saves and exits when globalEditMode becomes false", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, globalEditMode: true },
    })
    await nextTick()
    expect(wrapper.find("input").exists()).toBe(true)
    const input = wrapper.find("input")
    await input.setValue("Edited in global mode")
    await wrapper.setProps({ globalEditMode: false })
    await nextTick()
    expect(wrapper.emitted("update-text")).toBeTruthy()
    expect(wrapper.emitted("update-text")![0]).toEqual(["seg-0001", "Edited in global mode"])
    expect(wrapper.find("input").exists()).toBe(false)
  })

  it("shows save and cancel buttons when editing", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    expect(wrapper.find("[title='Save changes']").exists()).toBe(true)
    expect(wrapper.find("[title='Cancel editing']").exists()).toBe(true)
  })

  it("does not emit update-text when save with unchanged text", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    const editBtn = wrapper.find("[title='Edit text']")
    await editBtn.trigger("click")
    const saveBtn = wrapper.find("[title='Save changes']")
    await saveBtn.trigger("click")
    expect(wrapper.emitted("update-text")).toBeFalsy()
    expect(wrapper.find("input").exists()).toBe(false)
  })
})

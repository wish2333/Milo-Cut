/**
 * TimelineSwitcher integration tests.
 *
 * Tests switching, create, delete emit flows and active state display.
 */
import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import TimelineSwitcher from "./TimelineSwitcher.vue"
import { mockTimeline } from "@/test/helpers/mockProject"

describe("TimelineSwitcher", () => {
  const timelines = [
    mockTimeline({ id: "tl-a", label: "Timeline A", source: "default" }),
    mockTimeline({ id: "tl-b", label: "Timeline B", source: "fork" }),
    mockTimeline({ id: "tl-c", label: "Timeline C", source: "manual" }),
  ]

  it("renders active timeline label", () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-b" },
    })
    expect(wrapper.text()).toContain("Timeline B")
  })

  it("renders all timeline labels in dropdown", () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-a" },
    })
    expect(wrapper.text()).toContain("Timeline A")
    expect(wrapper.text()).toContain("Timeline B")
    expect(wrapper.text()).toContain("Timeline C")
  })

  it("emits switch on timeline click", async () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-a" },
    })
    const items = wrapper.findAll("a")
    // Find the Timeline B item (not the create/delete buttons)
    const tlBItem = items.find((a) => a.text().includes("Timeline B"))
    expect(tlBItem).toBeDefined()
    await tlBItem!.trigger("click")
    expect(wrapper.emitted("switch")).toBeTruthy()
    expect(wrapper.emitted("switch")![0]).toEqual(["tl-b"])
  })

  it("emits create on new timeline button click", async () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-a" },
    })
    const createBtn = wrapper.findAll("a").find((a) => a.text().includes("新建"))
    expect(createBtn).toBeDefined()
    await createBtn!.trigger("click")
    expect(wrapper.emitted("create")).toBeTruthy()
  })

  it("shows delete button when more than one timeline", () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-a" },
    })
    expect(wrapper.text()).toContain("删除当前")
  })

  it("hides delete button when only one timeline", () => {
    const wrapper = mount(TimelineSwitcher, {
      props: {
        timelines: [mockTimeline({ id: "only", label: "Only" })],
        activeTimelineId: "only",
      },
    })
    expect(wrapper.text()).not.toContain("删除当前")
  })

  it("emits delete with active timeline id", async () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-c" },
    })
    const deleteBtn = wrapper.findAll("a").find((a) => a.text().includes("删除"))
    await deleteBtn!.trigger("click")
    expect(wrapper.emitted("delete")).toBeTruthy()
    expect(wrapper.emitted("delete")![0]).toEqual(["tl-c"])
  })

  it("marks active timeline with checkmark indicator", () => {
    const wrapper = mount(TimelineSwitcher, {
      props: { timelines, activeTimelineId: "tl-b" },
    })
    const activeItem = wrapper.findAll("a").find((a) =>
      a.text().includes("Timeline B"),
    )
    expect(activeItem?.classes()).toContain("active")
  })
})

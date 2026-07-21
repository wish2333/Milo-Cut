import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import SilenceRow from "./SilenceRow.vue"
import { mockSegment } from "@/test/helpers/mockProject"

const silenceSegment = mockSegment({
  id: "sil-0001",
  type: "silence",
  start: 5.0,
  end: 7.5,
  text: "",
})

describe("SilenceRow", () => {
  it("renders silence duration", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment },
    })
    expect(wrapper.text()).toContain("2.5s")
  })

  it("renders default background without edit status", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment },
    })
    expect(wrapper.classes()).toContain("bg-parchment")
  })

  it("renders pending status with suggestion label", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, displayStatus: "pending" },
    })
    expect(wrapper.text()).toContain("建议删除")
    expect(wrapper.classes()).toContain("bg-status-pending")
  })

  it("renders confirmed status", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, displayStatus: "confirmed" },
    })
    expect(wrapper.text()).toContain("已删除")
    expect(wrapper.classes()).toContain("bg-status-confirmed")
  })

  it("renders rejected status", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, displayStatus: "rejected", styleClass: "kept" },
    })
    expect(wrapper.text()).toContain("已保留")
    expect(wrapper.classes()).toContain("bg-status-rejected")
  })

  it("emits seek on click", async () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment },
    })
    await wrapper.trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
    expect(wrapper.emitted("seek")![0]).toEqual([5.0])
  })
})

import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import SilenceRow from "./SilenceRow.vue"
import type { Segment } from "@/types/project"

const silenceSegment: Segment = {
  id: "sil-0001",
  version: 1,
  type: "silence",
  start: 5.0,
  end: 7.5,
  text: "",
  speaker: "",
}

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
    expect(wrapper.classes()).toContain("bg-gray-100")
  })

  it("renders pending status with suggestion label", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, editStatus: "pending" },
    })
    expect(wrapper.text()).toContain("建议删除")
    expect(wrapper.classes()).toContain("bg-yellow-50")
  })

  it("renders confirmed status", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, editStatus: "confirmed" },
    })
    expect(wrapper.text()).toContain("已确认")
    expect(wrapper.classes()).toContain("bg-red-50")
  })

  it("renders rejected status", () => {
    const wrapper = mount(SilenceRow, {
      props: { segment: silenceSegment, editStatus: "rejected" },
    })
    expect(wrapper.text()).toContain("已保留")
    expect(wrapper.classes()).toContain("bg-green-50")
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

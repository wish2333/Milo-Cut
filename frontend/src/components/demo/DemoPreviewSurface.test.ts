import { describe, expect, it } from "vitest"
import { mount } from "@vue/test-utils"
import DemoPreviewSurface from "./DemoPreviewSurface.vue"
import { createDemoProject } from "@/demo/demoProject"

describe("DemoPreviewSurface", () => {
  it("shows the active subtitle and preview mode without a video element", () => {
    const project = createDemoProject()
    const segments = project.timelines[0].transcript.segments
    const wrapper = mount(DemoPreviewSurface, {
      props: { segments, currentTime: 4, duration: 90, previewMode: "edited", deleteRanges: [] },
    })
    expect(wrapper.text()).toContain("大家好")
    expect(wrapper.text()).toContain("已编辑预览")
    expect(wrapper.find("video").exists()).toBe(false)
    expect(wrapper.attributes("aria-label")).toContain("0:04")
  })
})

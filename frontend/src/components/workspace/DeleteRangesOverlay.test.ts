import { describe, it, expect } from "vitest"
import { mount, flushPromises } from "@vue/test-utils"
import { nextTick } from "vue"
import DeleteRangesOverlay from "./DeleteRangesOverlay.vue"

const SAMPLE_RANGES = [
  { start: 5, end: 10 },
  { start: 20, end: 30 },
  { start: 45, end: 50 },
]

describe("DeleteRangesOverlay", () => {
  it("renders one element per range", () => {
    const wrapper = mount(DeleteRangesOverlay, {
      props: { ranges: SAMPLE_RANGES, duration: 60 },
    })
    const rangeEls = wrapper.findAll(".bg-red-500\\/30")
    expect(rangeEls.length).toBe(3)
  })

  it("renders nothing visible when ranges array is empty", () => {
    const wrapper = mount(DeleteRangesOverlay, {
      props: { ranges: [], duration: 60 },
    })
    expect(wrapper.findAll(".bg-red-500\\/30").length).toBe(0)
  })

  it("computes left and width based on duration", () => {
    const wrapper = mount(DeleteRangesOverlay, {
      props: { ranges: [{ start: 15, end: 30 }], duration: 60 },
    })
    const el = wrapper.find(".bg-red-500\\/30")
    expect(el.attributes("style")).toContain("left: 25%")
    expect(el.attributes("style")).toContain("width: 25%")
  })

  it("clamps left/width to 0% when duration is zero", () => {
    const wrapper = mount(DeleteRangesOverlay, {
      props: { ranges: [{ start: 5, end: 10 }], duration: 0 },
    })
    const el = wrapper.find(".bg-red-500\\/30")
    expect(el.attributes("style")).toContain("left: 0%")
    expect(el.attributes("style")).toContain("width: 0%")
  })

  it("uses stable composite keys so range identity is preserved across re-renders", async () => {
    const wrapper = mount(DeleteRangesOverlay, {
      props: { ranges: SAMPLE_RANGES, duration: 60 },
    })
    const firstElBefore = wrapper.findAll(".bg-red-500\\/30")[0].element

    // Re-set same props - elements should be reused, not recreated
    await wrapper.setProps({ ranges: [...SAMPLE_RANGES], duration: 60 })
    await nextTick()
    await flushPromises()

    const firstElAfter = wrapper.findAll(".bg-red-500\\/30")[0].element
    expect(firstElAfter).toBe(firstElBefore)
  })
})

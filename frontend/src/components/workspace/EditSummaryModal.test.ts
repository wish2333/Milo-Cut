import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import EditSummaryModal from "./EditSummaryModal.vue"
import type { EditSummary } from "@/types/edit"

const normalSummary: EditSummary = {
  total_duration: 3600,
  delete_duration: 600,
  delete_percent: 16.7,
  edit_count: 5,
  warnings: [],
}

const warningSummary: EditSummary = {
  total_duration: 3600,
  delete_duration: 1800,
  delete_percent: 50,
  edit_count: 20,
  warnings: [
    "Warning: 50% of total duration marked for deletion",
    "Warning: edit-005 spans 120.0s (>60s threshold)",
    "Warning: 3+ consecutive subtitle segments marked for deletion",
  ],
}

describe("EditSummaryModal", () => {
  it("does not render when visible is false", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: false },
    })
    expect(wrapper.find(".fixed").exists()).toBe(false)
  })

  it("renders when visible is true", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: true },
    })
    expect(wrapper.find(".fixed").exists()).toBe(true)
    expect(wrapper.text()).toContain("导出汇总摘要")
  })

  it("displays hero statistics", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: true },
    })
    // 3600s = 60:00
    expect(wrapper.text()).toContain("60:00")
    // 600s = 10:00
    expect(wrapper.text()).toContain("-10:00")
    expect(wrapper.text()).toContain("16.7%")
  })

  it("shows warning color when delete percent > 40", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: warningSummary, visible: true },
    })
    expect(wrapper.text()).toContain("50%")
    expect(wrapper.find(".text-red-600").exists()).toBe(true)
  })

  it("displays warnings list", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: warningSummary, visible: true },
    })
    expect(wrapper.text()).toContain("50%")
    expect(wrapper.text()).toContain("120.0s")
    expect(wrapper.findAll(".bg-yellow-50").length).toBe(3)
  })

  it("shows extra warning for >40% deletion", () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: warningSummary, visible: true },
    })
    expect(wrapper.find(".bg-red-50").exists()).toBe(true)
    expect(wrapper.text()).toContain("40%")
  })

  it("emits confirm on confirm button click", async () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: true },
    })
    const buttons = wrapper.findAll("button")
    await buttons[0].trigger("click")
    expect(wrapper.emitted("confirm")).toBeTruthy()
  })

  it("emits cancel on cancel button click", async () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: true },
    })
    const buttons = wrapper.findAll("button")
    await buttons[1].trigger("click")
    expect(wrapper.emitted("cancel")).toBeTruthy()
  })

  it("emits cancel on backdrop click", async () => {
    const wrapper = mount(EditSummaryModal, {
      props: { summary: normalSummary, visible: true },
    })
    await wrapper.find(".fixed").trigger("click.self")
    expect(wrapper.emitted("cancel")).toBeTruthy()
  })
})

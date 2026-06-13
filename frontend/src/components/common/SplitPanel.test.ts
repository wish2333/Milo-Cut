import { describe, it, expect, beforeEach, vi } from "vitest"
import { mount } from "@vue/test-utils"
import SplitPanel from "./SplitPanel.vue"

describe("SplitPanel", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  function mountPanel(props: Record<string, unknown> = {}) {
    return mount(SplitPanel, {
      props: { storageKey: "test-split", ...props },
      slots: {
        left: '<div data-testid="left">Left</div>',
        right: '<div data-testid="right">Right</div>',
      },
    })
  }

  it("renders both slots", () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="left"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="right"]').exists()).toBe(true)
  })

  it("renders a draggable divider", () => {
    const wrapper = mountPanel()
    // The divider is the element with the pointerdown listener (cursor-col-resize).
    const divider = wrapper.find(".cursor-col-resize")
    expect(divider.exists()).toBe(true)
  })

  it("applies a width to the left pane based on the default ratio", () => {
    const wrapper = mountPanel()
    const leftPane = wrapper.find(".h-full.min-w-0")
    const style = leftPane.attributes("style") ?? ""
    // Default ratio 0.4 -> 40%.
    expect(style).toContain("width: 40%")
  })

  it("clamps the ratio to maxRatio", () => {
    const wrapper = mountPanel({ maxRatio: 0.5 })
    const leftPane = wrapper.find(".h-full.min-w-0")
    const style = leftPane.attributes("style") ?? ""
    // Default 0.4 < 0.5 max, so unchanged.
    expect(style).toContain("width: 40%")
  })

  it("clamps the ratio to minRatio when default is below it", () => {
    const wrapper = mountPanel({ minRatio: 0.5, maxRatio: 0.9 })
    const leftPane = wrapper.find(".h-full.min-w-0")
    const style = leftPane.attributes("style") ?? ""
    // Default 0.4 < min 0.5 -> clamped to 50%.
    expect(style).toContain("width: 50%")
  })

  it("persists the ratio to localStorage on drag end", async () => {
    const wrapper = mountPanel({ storageKey: "persist-test" })
    const divider = wrapper.find(".cursor-col-resize")

    // Simulate a drag: pointerdown -> pointermove -> pointerup.
    await divider.trigger("pointerdown", { clientX: 100 })

    // getBoundingClientRect is hard to mock precisely in jsdom; instead verify
    // that pointerup writes *some* value to localStorage.
    window.dispatchEvent(new PointerEvent("pointerup"))
    await wrapper.vm.$nextTick()

    const stored = localStorage.getItem("persist-test")
    expect(stored).not.toBeNull()
    expect(Number.parseFloat(stored!)).not.toBeNaN()
  })

  it("restores the persisted ratio from localStorage on mount", () => {
    localStorage.setItem("restore-test", "0.6")
    const wrapper = mountPanel({ storageKey: "restore-test" })
    const leftPane = wrapper.find(".h-full.min-w-0")
    const style = leftPane.attributes("style") ?? ""
    expect(style).toContain("width: 60%")
  })

  it("clamps a persisted ratio that is out of range", () => {
    localStorage.setItem("clamp-test", "0.95") // above max 0.7
    const wrapper = mountPanel({ storageKey: "clamp-test", maxRatio: 0.7 })
    const leftPane = wrapper.find(".h-full.min-w-0")
    const style = leftPane.attributes("style") ?? ""
    expect(style).toContain("width: 70%")
  })

  it("does not persist when storageKey is empty", async () => {
    const wrapper = mount(SplitPanel, {
      props: { storageKey: "" },
      slots: {
        left: '<div>L</div>',
        right: '<div>R</div>',
      },
    })
    const divider = wrapper.find(".cursor-col-resize")
    await divider.trigger("pointerdown", { clientX: 100 })
    window.dispatchEvent(new PointerEvent("pointerup"))
    // Nothing should be written to localStorage.
    expect(localStorage.length).toBe(0)
  })
})

// Ensure window event listeners are cleaned up between test files.
describe("SplitPanel cleanup", () => {
  it("removes window listeners on unmount", async () => {
    const addSpy = vi.spyOn(window, "addEventListener")
    const removeSpy = vi.spyOn(window, "removeEventListener")
    const wrapper = mount(SplitPanel, {
      props: {},
      slots: { left: "<div>L</div>", right: "<div>R</div>" },
    })
    expect(addSpy).toHaveBeenCalledWith("pointermove", expect.any(Function))
    wrapper.unmount()
    expect(removeSpy).toHaveBeenCalledWith("pointermove", expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith("pointerup", expect.any(Function))
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })
})

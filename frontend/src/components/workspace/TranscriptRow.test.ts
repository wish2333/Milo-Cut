import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
import TranscriptRow from "./TranscriptRow.vue"
import { mockSegment } from "@/test/helpers/mockProject"

const baseSegment = mockSegment({
  id: "seg-0001",
  text: "Hello world",
})

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
    // v2.2.1: handleTextEditBlur uses setTimeout(150ms), wait for it
    await new Promise((r) => setTimeout(r, 160))
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

  // v3.0.0 M7-2: draft cache sync (virtual scrolling unmounts rows)
  it("mirrors typed text as draft-change events", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment },
    })
    await wrapper.find("[title='Edit text']").trigger("click")
    await wrapper.find("input").setValue("typed draft")
    const emitted = wrapper.emitted("draft-change")
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual(["seg-0001", "typed draft"])
  })

  it("restores the draft prop when entering edit mode", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, draft: "restored draft" },
    })
    await wrapper.find("[title='Edit text']").trigger("click")
    expect(wrapper.find("input").element.value).toBe("restored draft")
  })

  it("clears the draft on save", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, draft: "pending draft" },
    })
    await wrapper.find("[title='Edit text']").trigger("click")
    const input = wrapper.find("input")
    await input.setValue("final text")
    await input.trigger("blur")
    // blur-save is deferred 150ms (v2.2.1 drag-out guard)
    await new Promise((r) => setTimeout(r, 160))
    const emitted = wrapper.emitted("draft-change")!
    expect(emitted[emitted.length - 1]).toEqual(["seg-0001", null])
  })

  it("clears the draft on cancel", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, draft: "pending draft" },
    })
    await wrapper.find("[title='Edit text']").trigger("click")
    await wrapper.find("input").trigger("keydown", { key: "Escape" })
    const emitted = wrapper.emitted("draft-change")!
    expect(emitted[emitted.length - 1]).toEqual(["seg-0001", null])
  })
})

// ---------------------------------------------------------------------------
// v3.0.3 M1-2: track variant -- display-only extension-track list row
// (text/start/end + duration + binding mark, zero main-track machinery).
// ---------------------------------------------------------------------------
describe("TranscriptRow track variant (M1-2)", () => {
  const trackSeg = mockSegment({
    id: "track_en_seg_1.000",
    start: 2,
    end: 6,
    text: "Hello track",
  })

  function mountTrack(extra: Record<string, unknown> = {}) {
    return mount(TranscriptRow, {
      props: { segment: trackSeg, variant: "track", ...extra },
    })
  }

  it("renders text, start and end stamps", () => {
    const wrapper = mountTrack()
    expect(wrapper.text()).toContain("Hello track")
    expect(wrapper.find('[data-test="track-start"]').text()).toContain("00:02")
    expect(wrapper.find('[data-test="track-end"]').text()).toContain("00:06")
    wrapper.unmount()
  })

  it("renders the duration chip from end - start", () => {
    const wrapper = mountTrack()
    expect(wrapper.find('[data-test="track-duration"]').text()).toBe("0:04")
    wrapper.unmount()
  })

  it("shows the binding mark only when bound", () => {
    const unbound = mountTrack()
    expect(unbound.find('[data-test="track-bound-mark"]').exists()).toBe(false)
    unbound.unmount()
    const bound = mountTrack({ isBound: true })
    expect(bound.find('[data-test="track-bound-mark"]').exists()).toBe(true)
    bound.unmount()
  })

  it("renders no edit button, no status buttons, main menu only", async () => {
    const wrapper = mountTrack()
    expect(wrapper.find("[title='Edit text']").exists()).toBe(false)
    expect(wrapper.text()).not.toContain("无标注")
    expect(wrapper.text()).not.toContain("标记删除")
    wrapper.unmount()
  })

  it("never enters text edit under globalEditMode", async () => {
    const wrapper = mountTrack({ globalEditMode: true })
    await nextTick()
    expect(wrapper.find("input.edit-text-input").exists()).toBe(false)
    wrapper.unmount()
  })

  it("enters time edit from a stamp click and commits via track-time", async () => {
    const wrapper = mountTrack()
    await wrapper.find('[data-test="track-start"]').trigger("mousedown", { button: 0 })
    const input = wrapper.find("input")
    expect(input.exists()).toBe(true)
    await input.setValue("00:03.000")
    await input.trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("track-time")).toBeTruthy()
    expect(wrapper.emitted("track-time")![0]).toEqual(["start", 3])
    // main-path event never fired for a track row
    expect(wrapper.emitted("update-time")).toBeUndefined()
    wrapper.unmount()
  })

  it("commits text edits via track-text (dblclick entry)", async () => {
    const wrapper = mountTrack()
    await wrapper.trigger("dblclick")
    const input = wrapper.find("input.edit-text-input")
    expect(input.exists()).toBe(true)
    await input.setValue("changed text")
    await input.trigger("keydown", { key: "Enter" })
    expect(wrapper.emitted("track-text")).toBeTruthy()
    expect(wrapper.emitted("track-text")![0]).toEqual(["changed text"])
    expect(wrapper.emitted("update-text")).toBeUndefined()
    wrapper.unmount()
  })

  it("opens the track menu with 定位/编辑/删除此条字幕 and no main items", async () => {
    const wrapper = mountTrack()
    await wrapper.trigger("contextmenu")
    // The menu teleports to body: query the document, not the wrapper.
    const menu = document.body.querySelector(".fixed.z-dropdown")
    expect(menu).not.toBeNull()
    expect(menu!.textContent).toContain("定位")
    expect(menu!.textContent).toContain("编辑")
    expect(menu!.querySelector('[data-test="track-menu-delete"]')).not.toBeNull()
    expect(menu!.textContent).not.toContain("编辑文本")
    expect(menu!.textContent).not.toContain("标记删除")
    wrapper.unmount()
  })

  it("menu 删除此条字幕 emits track-delete immediately (no confirm)", async () => {
    const wrapper = mountTrack()
    await wrapper.trigger("contextmenu")
    const del = document.body.querySelector('[data-test="track-menu-delete"]') as HTMLButtonElement
    expect(del).not.toBeNull()
    del.click()
    await nextTick()
    expect(wrapper.emitted("track-delete")).toBeTruthy()
    wrapper.unmount()
  })

  it("menu 定位 seeks to the segment start", async () => {
    const wrapper = mountTrack()
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const first = menu.querySelectorAll("button")[0] as HTMLButtonElement
    first.click()
    await nextTick()
    expect(wrapper.emitted("seek")![0]).toEqual([2])
    wrapper.unmount()
  })

  it("emits seek on row click", async () => {
    const wrapper = mountTrack()
    await wrapper.trigger("click")
    expect(wrapper.emitted("seek")).toBeTruthy()
    expect(wrapper.emitted("seek")![0]).toEqual([2])
    wrapper.unmount()
  })
})

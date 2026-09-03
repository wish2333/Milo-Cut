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

// ---------------------------------------------------------------------------
// v3.0.3 M3 (S3): config-driven context menus with kbd badges.
// Registry (ShortcutsSettingsTab) maps exactly ONE menu action to a real
// shortcut: 标记删除 -> Delete. Everything else stays text-only; no empty
// <kbd> shells.
// ---------------------------------------------------------------------------
describe("TranscriptRow context menu kbd badges (M3)", () => {
  it("main menu: 标记删除 carries the Del badge in the R9.4 style", async () => {
    const wrapper = mount(TranscriptRow, { props: { segment: baseSegment } })
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const badges = menu.querySelectorAll("kbd")
    expect(badges).toHaveLength(1)
    expect(badges[0].getAttribute("data-test")).toBe("menu-kbd")
    expect(badges[0].textContent).toBe("Del")
    expect(badges[0].className).toContain("font-mono")
    // the badge sits inside the 标记删除 item
    const delItem = badges[0].closest("button")!
    expect(delItem.textContent).toContain("标记删除")
    wrapper.unmount()
  })

  it("main menu: items without a registered shortcut render no kbd node", async () => {
    const wrapper = mount(TranscriptRow, { props: { segment: baseSegment, isPlayheadInside: true } })
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const buttons = [...menu.querySelectorAll("button")]
    // full main menu with the playhead inside (split item present)
    const labels = buttons.map(b => b.querySelector("span")!.textContent!.trim())
    expect(labels).toEqual([
      "编辑文本",
      "标记删除",
      "从时间指针分割",
      "从中点分割",
      "加入精华",
      "删除段落",
    ])
    expect(menu.querySelectorAll("kbd")).toHaveLength(1) // only 标记删除
    wrapper.unmount()
  })

  it("main menu: 取消删除 keeps the badge when the status is confirmed", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, displayStatus: "confirmed" },
    })
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const badge = menu.querySelector("kbd")!
    expect(badge.closest("button")!.textContent).toContain("取消删除")
    wrapper.unmount()
  })

  it("track menu: no invented shortcuts -- zero badges, actions intact", async () => {
    const wrapper = mount(TranscriptRow, {
      props: { segment: baseSegment, variant: "track" } as never,
    })
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    expect(menu.querySelectorAll("kbd")).toHaveLength(0)
    const labels = [...menu.querySelectorAll("button")].map(b => b.textContent!.trim())
    expect(labels).toEqual(["定位", "编辑", "删除此条字幕"])
    wrapper.unmount()
  })

  it("menu actions still fire through the config layer (split guarded by playhead)", async () => {
    const wrapper = mount(TranscriptRow, { props: { segment: baseSegment } })
    await wrapper.trigger("contextmenu")
    const menu = document.body.querySelector(".fixed.z-dropdown")!
    const labels = [...menu.querySelectorAll("button")].map(b => b.textContent!.trim())
    expect(labels).not.toContain("从时间指针分割") // show: false hidden entirely
    const edit = buttonsOf(menu).find(b => b.textContent!.includes("编辑文本"))!
    edit.click()
    await nextTick()
    expect(wrapper.find("input").exists()).toBe(true)
    wrapper.unmount()

    function buttonsOf(m: Element): HTMLButtonElement[] {
      return [...m.querySelectorAll("button")] as HTMLButtonElement[]
    }
  })
})

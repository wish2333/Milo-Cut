/**
 * ConflictResolutionView tests (v2.1.0 Phase 4).
 *
 * Tests conflict rendering, resolution actions, and skip.
 * Uses global Teleport stub to capture teleported content.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount } from "@vue/test-utils"
import { ref } from "vue"

// Create reactive refs that the mock will return
const _showConflictView = ref(false)
const _conflicts = ref<unknown[]>([])
const _resolveConflict = vi.fn()
const _applyWorkflow = vi.fn()

vi.mock("@/composables/useWorkflow", () => ({
  useWorkflow: () => ({
    conflicts: _conflicts,
    showConflictView: _showConflictView,
    resolveConflict: _resolveConflict,
    applyWorkflow: _applyWorkflow,
  }),
}))

import ConflictResolutionView from "./ConflictResolutionView.vue"

// Helper to create a conflict
function makeConflict(overrides: Record<string, unknown> = {}) {
  return {
    segment_id: "seg-1",
    segment_text: "hello world",
    segment_start: 0,
    segment_end: 5,
    decisions: [
      {
        edit_id: "e1",
        action: "delete",
        source: "llm_smart_delete",
        step_type: "llm_smart_delete",
        step_index: 0,
        reason: "filler",
      },
      {
        edit_id: "e2",
        action: "keep",
        source: "llm_highlight",
        step_type: "llm_highlight",
        step_index: 1,
        reason: "key point",
      },
    ],
    ...overrides,
  }
}

describe("ConflictResolutionView", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _showConflictView.value = false
    _conflicts.value = []
  })

  it("renders nothing when showConflictView is false", () => {
    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    expect(wrapper.text()).toBe("")
  })

  it("renders conflict header with count when active", () => {
    _conflicts.value = [makeConflict(), makeConflict({ segment_id: "seg-2" })]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    expect(wrapper.text()).toContain("2")
    expect(wrapper.text()).toContain("冲突")
  })

  it("renders empty state when no conflicts", () => {
    _conflicts.value = []
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    expect(wrapper.text()).toContain("没有需要解决的冲突")
  })

  it("shows current conflict details", () => {
    _conflicts.value = [makeConflict({ segment_text: "test segment" })]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    expect(wrapper.text()).toContain("test segment")
    expect(wrapper.text()).toContain("00:00 - 00:05")
  })

  it("displays both decision cards", () => {
    _conflicts.value = [makeConflict()]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    const text = wrapper.text()
    expect(text).toContain("P0")
    expect(text).toContain("P2")
  })

  it("calls resolveConflict with keep_first on button click", async () => {
    _conflicts.value = [makeConflict()]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    const buttons = wrapper.findAll("button")
    const keepFirstBtn = buttons.find((b) => b.text().includes("保留"))
    await keepFirstBtn?.trigger("click")

    expect(_resolveConflict).toHaveBeenCalledWith("seg-1", "keep_first")
  })

  it("calls resolveConflict with keep_all on button click", async () => {
    _conflicts.value = [makeConflict()]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    const buttons = wrapper.findAll("button")
    const keepAllBtn = buttons.find((b) => b.text().includes("两者都保留"))
    await keepAllBtn?.trigger("click")

    expect(_resolveConflict).toHaveBeenCalledWith("seg-1", "keep_all")
  })

  it("hides overlay on skip click", async () => {
    _conflicts.value = [makeConflict()]
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    const buttons = wrapper.findAll("button")
    const skipBtn = buttons.find((b) => b.text().includes("跳过"))
    await skipBtn?.trigger("click")

    expect(_showConflictView.value).toBe(false)
  })

  it("calls applyWorkflow on finish button after all resolved", async () => {
    _conflicts.value = []
    _showConflictView.value = true

    const wrapper = mount(ConflictResolutionView, {
      global: { stubs: { Teleport: true } },
    })
    const buttons = wrapper.findAll("button")
    const finishBtn = buttons.find((b) => b.text().includes("全部解决"))
    await finishBtn?.trigger("click")

    expect(_applyWorkflow).toHaveBeenCalled()
  })
})

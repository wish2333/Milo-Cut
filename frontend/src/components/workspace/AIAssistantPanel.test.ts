/**
 * AIAssistantPanel workflow mode tests (v2.1.0 Phase 4).
 *
 * Tests mode switching, workflow CRUD, execution progress, and cancel.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount } from "@vue/test-utils"
import { nextTick, ref } from "vue"
import { call } from "@/bridge"

// Mock bridge
vi.mock("@/bridge", () => ({
  call: vi.fn(),
  onEvent: vi.fn(),
}))

// Create reactive refs for singleton state
const _workflows = ref<unknown[]>([])
const _isActive = ref(false)
const _instanceId = ref<string | null>(null)
const _workflowName = ref("")
const _currentStepIndex = ref(0)
const _totalSteps = ref(0)
const _stepResults = ref<unknown[]>([])
const _stepProgress = ref<Record<string, unknown>>({})
const _cancelMode = ref("")
const _errorMsg = ref<string | null>(null)
const _conflicts = ref<unknown[]>([])
const _showConflictView = ref(false)
const _showFailureDialog = ref(false)
const _failureInfo = ref<{ stepName: string; error: string } | null>(null)

const _loadWorkflows = vi.fn()
const _saveWorkflow = vi.fn()
const _deleteWorkflow = vi.fn()
const _startWorkflow = vi.fn()
const _cancelWorkflow = vi.fn()
const _handleStepFailure = vi.fn()
const _refreshStatus = vi.fn()
const _detectConflicts = vi.fn()
const _resolveConflict = vi.fn()
const _applyWorkflow = vi.fn()
const _discardWorkflow = vi.fn()

vi.mock("@/composables/useWorkflow", () => ({
  useWorkflow: () => ({
    workflows: _workflows,
    isActive: _isActive,
    instanceId: _instanceId,
    workflowName: _workflowName,
    currentStepIndex: _currentStepIndex,
    totalSteps: _totalSteps,
    stepResults: _stepResults,
    stepProgress: _stepProgress,
    cancelMode: _cancelMode,
    errorMsg: _errorMsg,
    conflicts: _conflicts,
    showConflictView: _showConflictView,
    showFailureDialog: _showFailureDialog,
    failureInfo: _failureInfo,
    overallProgress: { value: 0 },
    loadWorkflows: _loadWorkflows,
    saveWorkflow: _saveWorkflow,
    deleteWorkflow: _deleteWorkflow,
    startWorkflow: _startWorkflow,
    cancelWorkflow: _cancelWorkflow,
    handleStepFailure: _handleStepFailure,
    refreshStatus: _refreshStatus,
    detectConflicts: _detectConflicts,
    resolveConflict: _resolveConflict,
    applyWorkflow: _applyWorkflow,
    discardWorkflow: _discardWorkflow,
  }),
}))

// Mock useLlmSettings
const _presetsByFunc = ref<Record<string, unknown[]>>({})

vi.mock("@/composables/useLlmSettings", () => ({
  useLlmSettings: () => ({
    presetsByFunc: _presetsByFunc,
    loadPresets: vi.fn(),
  }),
}))

import AIAssistantPanel from "./AIAssistantPanel.vue"

const baseProps = {
  segments: [
    { id: "s1", version: 1, type: "subtitle" as const, start: 1.0, end: 5.0, text: "hello", speaker: "" },
  ],
  llmConfigured: true,
  llmModel: "test-model",
  isRunning: false,
  progress: 0,
  errorMsg: null,
  subtitleCorrectionCount: null,
}

function mountPanel() {
  return mount(AIAssistantPanel, {
    props: baseProps,
    global: { stubs: { Teleport: true, SemanticSearchBar: true } },
  })
}

function mountTranslationPanel(extraProps: Record<string, unknown> = {}) {
  return mount(AIAssistantPanel, {
    props: { ...baseProps, ...extraProps },
    global: { stubs: { Teleport: true, SemanticSearchBar: true } },
  })
}

function subtitleSegments(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `ms-${i + 1}`,
    version: 1,
    type: "subtitle" as const,
    start: i * 5 + 1,
    end: i * 5 + 5,
    text: `main ${i + 1}`,
    speaker: "",
  }))
}

// settle microtasks + one render tick (settings read is async)
async function nextTickSteadle() {
  await Promise.resolve()
  await nextTick()
}

describe("AIAssistantPanel -- workflow mode", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _isActive.value = false
    _instanceId.value = null
    _workflows.value = []
    _stepResults.value = []
    _cancelMode.value = ""
  })

  it("shows mode switch tabs", () => {
    const wrapper = mountPanel()
    const text = wrapper.text()
    expect(text).toContain("单功能")
    expect(text).toContain("工作流")
  })

  it("switches to workflow mode on tab click", async () => {
    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    expect(wrapper.text()).toContain("选择已保存工作流")
    expect(wrapper.text()).toContain("步骤 (按勾选顺序执行)")
  })

  it("shows step checkboxes in workflow config", async () => {
    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    const text = wrapper.text()
    expect(text).toContain("P0 智能删除")
    expect(text).toContain("P1 字幕修正")
    expect(text).toContain("P2 精华提取")
  })

  it("calls loadWorkflows on mount", () => {
    mountPanel()
    expect(_loadWorkflows).toHaveBeenCalled()
  })

  it("shows execution progress when workflow is active", async () => {
    _isActive.value = true
    _totalSteps.value = 3
    _currentStepIndex.value = 1
    _workflowName.value = "Test Workflow"
    _stepResults.value = [
      { index: 0, type: "llm_smart_delete", status: "completed", edits_count: 5 },
      { index: 1, type: "llm_smart_delete", status: "running", edits_count: 0 },
      { index: 2, type: "llm_highlight", status: "pending", edits_count: 0 },
    ]

    const wrapper = mountPanel()
    // Switch to workflow mode
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    const text = wrapper.text()
    expect(text).toContain("Test Workflow")
    expect(text).toContain("1/3")
    expect(text).toContain("5 条")
  })

  it("shows queued state text for queued steps", async () => {
    _isActive.value = true
    _totalSteps.value = 2
    _currentStepIndex.value = 0
    _stepResults.value = [
      { index: 0, type: "llm_smart_delete", status: "queued", edits_count: 0 },
      { index: 1, type: "llm_smart_delete", status: "pending", edits_count: 0 },
    ]

    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    expect(wrapper.text()).toContain("等待系统资源")
  })

  it("shows completion status and return-to-config button after workflow completes", async () => {
    _isActive.value = false
    _instanceId.value = "wfi-test"

    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    const text = wrapper.text()
    // v2.2.0: Apply/Discard removed; completion view shows status + return button
    expect(text).toContain("工作流已完成")
    expect(text).toContain("返回配置")
    expect(text).not.toContain("应用结果到项目")
    expect(text).not.toContain("放弃")
  })
})

describe("AIAssistantPanel -- translation card (v3.0.4 M1-6)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(call).mockResolvedValue({ success: false, error: "no settings" })
  })

  it("is greyed out and emits nothing when mainSegments has no subtitle segments", async () => {
    // Track mode: `segments` (a secondary track WITH subtitles) must NOT
    // un-grey the card -- the judgment source is mainSegments.
    const wrapper = mountTranslationPanel({
      mainSegments: [{ id: "gap", version: 1, type: "silence" as const, start: 0, end: 1, text: "", speaker: "" }],
    })
    const card = wrapper.find('[data-test="translation-card"]')
    expect(card.exists()).toBe(true)
    expect(card.attributes("disabled")).toBeDefined()
    expect(card.classes()).toContain("opacity-50")
    expect(wrapper.text()).toContain("主轨无字幕")

    await card.trigger("click")
    expect(wrapper.find('[data-test="translation-dialog"]').exists()).toBe(false)
    expect(wrapper.emitted("start-translation")).toBeUndefined()
  })

  it("opens the dialog on card click and emits start-translation with the selected language", async () => {
    const wrapper = mountTranslationPanel({ mainSegments: subtitleSegments(3) })
    const card = wrapper.find('[data-test="translation-card"]')
    expect(card.attributes("disabled")).toBeUndefined()

    await card.trigger("click")
    expect(wrapper.find('[data-test="translation-dialog"]').exists()).toBe(true)

    const select = wrapper.find('[data-test="translation-language"]')
    await select.setValue("ja")

    await wrapper.find('[data-test="translation-dialog"] button.bg-blue-500').trigger("click")
    const emitted = wrapper.emitted("start-translation")
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual({ targetLanguage: "ja" })
  })

  it("defaults the dialog selection to the remembered settings language", async () => {
    vi.mocked(call).mockResolvedValue({
      success: true,
      data: { llm_translation_target_language: "ru" },
    })
    const wrapper = mountTranslationPanel({ mainSegments: subtitleSegments(2) })
    await wrapper.find('[data-test="translation-card"]').trigger("click")
    // get_settings is read through the existing settings channel on open.
    expect(call).toHaveBeenCalledWith("get_settings")
    await Promise.resolve()
    await nextTickSteadle()
    const select = wrapper.find('[data-test="translation-language"]')
    expect((select.element as HTMLSelectElement).value).toBe("ru")
  })

  it("falls back to the default language when settings carry no valid value", async () => {
    vi.mocked(call).mockResolvedValue({ success: true, data: {} })
    const wrapper = mountTranslationPanel({ mainSegments: subtitleSegments(2) })
    await wrapper.find('[data-test="translation-card"]').trigger("click")
    await Promise.resolve()
    await nextTickSteadle()
    const select = wrapper.find('[data-test="translation-language"]')
    expect((select.element as HTMLSelectElement).value).toBe("en")
  })

  it("estimates the batch count as ceil(mainSegments / 30)", () => {
    const wrapper = mountTranslationPanel({ mainSegments: subtitleSegments(1250) })
    expect(wrapper.find('[data-test="translation-batches"]').text()).toBe("约 42 批")
  })

  it("lists uncovered ids from the translation notice prop", () => {
    const wrapper = mountTranslationPanel({
      mainSegments: subtitleSegments(2),
      translationNotice: {
        trackName: "English",
        language: "en",
        uncoveredIds: ["seg-1", "seg-7"],
      },
    })
    const notice = wrapper.find('[data-test="translation-notice"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain("2 段未覆盖")
    expect(notice.text()).toContain("seg-1、seg-7")
  })
})

// ---------------------------------------------------------------------------
// v3.0.4 M2-4 A: track-view gating. Track mode = non-empty activeTrackId;
// smart delete + the workflow entry are main-track-only (greyed out +
// 「仅主轨可用」), the correction card stays usable with the locked-track
// badge, search stays usable. Main-track view must stay byte-identical.
// ---------------------------------------------------------------------------
describe("AIAssistantPanel -- track-view gating (v3.0.4 M2-4)", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(call).mockResolvedValue({ success: false, error: "no settings" })
  })

  function mountTrackPanel(extraProps: Record<string, unknown> = {}) {
    return mountTranslationPanel({
      activeTrackId: "t_en",
      activeTrackName: "English",
      ...extraProps,
    })
  }

  it("greys out the smart delete card in track mode and never emits start on click", async () => {
    const wrapper = mountTrackPanel()
    const card = wrapper.find('[data-test="feature-card-smart_delete"]')
    expect(card.exists()).toBe(true)
    expect(card.attributes("disabled")).toBeDefined()
    expect(card.classes()).toContain("opacity-50")
    expect(card.attributes("title")).toBe("仅主轨可用")
    expect(card.find('[data-test="track-gated-label"]').text()).toBe("仅主轨可用")

    // trigger bypasses the disabled attr in happy-dom -- the guard, not the
    // styling, is what must keep the start path silent (SPEC M2-4 验收).
    await card.trigger("click")
    expect(wrapper.text()).not.toContain("开始智能分析")
    expect(wrapper.emitted("start-smart-delete")).toBeUndefined()
    wrapper.unmount()
  })

  it("shows the locked-track badge 「当前轨：{track_name}」 on the correction card", async () => {
    const wrapper = mountTrackPanel()
    const card = wrapper.find('[data-test="feature-card-subtitle_correction"]')
    // correction stays usable in track mode (it targets the viewed track)
    expect(card.attributes("disabled")).toBeUndefined()
    expect(card.classes()).not.toContain("opacity-50")
    const badge = card.find('[data-test="correction-track-badge"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toBe("当前轨：English")

    await card.trigger("click")
    expect(wrapper.text()).toContain("开始字幕修正")
    wrapper.unmount()
  })

  it("greys out the workflow mode entry in track mode and blocks the switch", async () => {
    const wrapper = mountTrackPanel()
    const workflowTab = wrapper.find('[data-test="mode-switch-workflow"]')
    expect(workflowTab.attributes("disabled")).toBeDefined()
    expect(workflowTab.attributes("title")).toBe("仅主轨可用")
    await workflowTab.trigger("click")
    expect(wrapper.text()).not.toContain("选择已保存工作流")
    wrapper.unmount()
  })

  it("keeps the search card enabled in track mode (read-only, not gated)", () => {
    const wrapper = mountTrackPanel()
    const searchCard = wrapper
      .findAll("button")
      .find((b) => b.text().includes("内容搜索"))
    expect(searchCard).toBeDefined()
    expect(searchCard!.attributes("disabled")).toBeUndefined()
    wrapper.unmount()
  })

  it("main-track view shows no gating artifacts (explicit zero-regression)", () => {
    const wrapper = mountTranslationPanel()
    expect(
      wrapper.find('[data-test="feature-card-smart_delete"]').attributes("disabled"),
    ).toBeUndefined()
    // 空即主轨：no track badge, no gating label, workflow entry enabled
    expect(wrapper.find('[data-test="correction-track-badge"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="track-gated-label"]').exists()).toBe(false)
    expect(
      wrapper.find('[data-test="mode-switch-workflow"]').attributes("disabled"),
    ).toBeUndefined()
    wrapper.unmount()
  })

  it("closes an open smart-delete detail when the view switches to a track", async () => {
    // Open the detail on the main track, then switch the list to a track:
    // the gated feature's detail must fall back closed (never rest on a
    // disabled view), and no start can be emitted from it afterwards.
    const wrapper = mountTranslationPanel()
    await wrapper.find('[data-test="feature-card-smart_delete"]').trigger("click")
    expect(wrapper.text()).toContain("开始智能分析")
    await wrapper.setProps({ activeTrackId: "t_en", activeTrackName: "English" })
    expect(wrapper.text()).not.toContain("开始智能分析")
    wrapper.unmount()
  })
})

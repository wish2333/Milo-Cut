/**
 * AIAssistantPanel workflow mode tests (v2.1.0 Phase 4).
 *
 * Tests mode switching, workflow CRUD, execution progress, and cancel.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount } from "@vue/test-utils"
import { ref } from "vue"

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
    expect(text).toContain("规则分析")
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
      { index: 0, type: "full_analysis", status: "completed", edits_count: 5 },
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
      { index: 0, type: "full_analysis", status: "queued", edits_count: 0 },
      { index: 1, type: "llm_smart_delete", status: "pending", edits_count: 0 },
    ]

    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    expect(wrapper.text()).toContain("等待系统资源")
  })

  it("shows apply/discard buttons after workflow completes", async () => {
    _isActive.value = false
    _instanceId.value = "wfi-test"

    const wrapper = mountPanel()
    const tabs = wrapper.findAll("button")
    const workflowTab = tabs.find((t) => t.text() === "工作流")
    await workflowTab?.trigger("click")

    const text = wrapper.text()
    expect(text).toContain("应用结果到项目")
    expect(text).toContain("放弃")
  })
})

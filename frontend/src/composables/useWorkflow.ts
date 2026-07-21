/**
 * v2.1.0 Phase 3 -- Workflow composable.
 *
 * Manages workflow definition CRUD, execution lifecycle, progress tracking,
 * conflict resolution, and apply/discard. Singleton state shared across all
 * useWorkflow() callers.
 */
import { ref, computed } from "vue"
import { call, onEvent } from "@/bridge"
import type { ApiResponse } from "@/bridge"
import {
  EVENT_WORKFLOW_STARTED,
  EVENT_WORKFLOW_STEP_STARTED,
  EVENT_WORKFLOW_STEP_PROGRESS,
  EVENT_WORKFLOW_STEP_COMPLETED,
  EVENT_WORKFLOW_STEP_FAILED,
  EVENT_WORKFLOW_COMPLETED,
  EVENT_WORKFLOW_CANCELLED,
  EVENT_WORKFLOW_CONFLICTS_DETECTED,
  EVENT_WORKFLOW_HEARTBEAT,
  EVENT_DEMO_RESET,
} from "@/utils/events"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WorkflowStep {
  type: "llm_smart_delete" | "llm_subtitle_correction" | "llm_highlight"
  preset_id: string | null
}

export interface WorkflowDef {
  id: string
  name: string
  steps: WorkflowStep[]
  created_at: string
  updated_at?: string
}

export interface StepResult {
  index: number
  type: string
  status: "pending" | "running" | "queued" | "completed" | "skipped" | "failed"
  edits_count: number
}

export interface WorkflowStatus {
  active: boolean
  workflow_instance_id?: string
  workflow_name?: string
  timeline_id?: string
  status?: string
  current_step_index?: number
  total_steps?: number
  cancel_mode?: string
  step_results?: StepResult[]
}

export interface WorkflowConflict {
  segment_id: string
  segment_text: string
  segment_start: number
  segment_end: number
  decisions: Array<{
    edit_id: string
    action: string
    source: string
    step_type: string
    step_index: number
    reason: string
  }>
}

// ---------------------------------------------------------------------------
// Singleton state
// ---------------------------------------------------------------------------

const workflows = ref<WorkflowDef[]>([])
const isActive = ref(false)
const instanceId = ref<string | null>(null)
const workflowName = ref("")
const currentStepIndex = ref(0)
const totalSteps = ref(0)
const stepResults = ref<StepResult[]>([])
const stepProgress = ref<Record<number, { percent: number; message: string }>>({})
const cancelMode = ref("")
const errorMsg = ref<string | null>(null)
const conflicts = ref<WorkflowConflict[]>([])
const showConflictView = ref(false)
const showFailureDialog = ref(false)
const failureInfo = ref<{ stepName: string; error: string } | null>(null)

// Heartbeat watchdog (D-72)
let heartbeatTimer: ReturnType<typeof setTimeout> | null = null
const HEARTBEAT_TIMEOUT = 45_000 // 45s (3x heartbeat interval)

let listenersRegistered = false

// ---------------------------------------------------------------------------
// Listener registration
// ---------------------------------------------------------------------------

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  onEvent(EVENT_DEMO_RESET, () => {
    stopHeartbeat()
    workflows.value = []
    isActive.value = false
    instanceId.value = null
    workflowName.value = ""
    currentStepIndex.value = 0
    totalSteps.value = 0
    stepResults.value = []
    stepProgress.value = {}
    cancelMode.value = ""
    errorMsg.value = null
    conflicts.value = []
    showConflictView.value = false
  })

  onEvent(EVENT_WORKFLOW_STARTED, (d: Record<string, unknown>) => {
    isActive.value = true
    instanceId.value = d.workflow_instance_id as string
    workflowName.value = d.workflow_name as string
    totalSteps.value = d.total_steps as number
    currentStepIndex.value = 0
    stepResults.value = (d.steps as StepResult[]) || []
    stepProgress.value = {}
    errorMsg.value = null
    conflicts.value = []
    resetHeartbeat()
  })

  onEvent(EVENT_WORKFLOW_STEP_STARTED, (d: Record<string, unknown>) => {
    const idx = d.step_index as number
    const status = d.status as string
    // Update step status (queued -> running)
    stepResults.value = stepResults.value.map((s) =>
      s.index === idx ? { ...s, status: status as StepResult["status"] } : s,
    )
  })

  onEvent(EVENT_WORKFLOW_STEP_PROGRESS, (d: Record<string, unknown>) => {
    const idx = d.step_index as number
    stepProgress.value = {
      ...stepProgress.value,
      [idx]: { percent: d.percent as number, message: d.message as string },
    }
  })

  onEvent(EVENT_WORKFLOW_STEP_COMPLETED, (d: Record<string, unknown>) => {
    const idx = d.step_index as number
    stepResults.value = stepResults.value.map((s) =>
      s.index === idx
        ? { ...s, status: "completed", edits_count: d.edits_count as number }
        : s,
    )
    currentStepIndex.value = idx + 1
  })

  onEvent(EVENT_WORKFLOW_STEP_FAILED, (d: Record<string, unknown>) => {
    showFailureDialog.value = true
    failureInfo.value = {
      stepName: d.step_name as string,
      error: d.error as string,
    }
  })

  onEvent(EVENT_WORKFLOW_COMPLETED, (d: Record<string, unknown>) => {
    isActive.value = false
    cancelMode.value = ""
    currentStepIndex.value = totalSteps.value
    stopHeartbeat()
    // Store total edits for potential conflict detection
    const _total = d.total_edits as number
    void _total
  })

  onEvent(EVENT_WORKFLOW_CANCELLED, (d: Record<string, unknown>) => {
    isActive.value = false
    cancelMode.value = ""
    stopHeartbeat()
    const _completed = d.completed_steps as number
    void _completed
  })

  onEvent(EVENT_WORKFLOW_CONFLICTS_DETECTED, (d: Record<string, unknown>) => {
    conflicts.value = (d.conflicts as WorkflowConflict[]) || []
    if (conflicts.value.length > 0) {
      showConflictView.value = true
    }
  })

  onEvent(EVENT_WORKFLOW_HEARTBEAT, () => {
    resetHeartbeat()
  })
}

function resetHeartbeat() {
  if (heartbeatTimer) clearTimeout(heartbeatTimer)
  heartbeatTimer = setTimeout(() => {
    errorMsg.value = "工作流可能已中断，请检查应用状态"
    isActive.value = false
  }, HEARTBEAT_TIMEOUT)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearTimeout(heartbeatTimer)
    heartbeatTimer = null
  }
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

async function loadWorkflows() {
  const res = await call<WorkflowDef[]>("get_workflows")
  if (res.success && res.data) {
    workflows.value = res.data
  }
  return res
}

async function saveWorkflow(
  name: string,
  steps: WorkflowStep[],
  workflowId = "",
): Promise<ApiResponse<WorkflowDef>> {
  const res = await call<WorkflowDef>("save_workflow", name, steps, workflowId)
  if (res.success) {
    await loadWorkflows()
  }
  return res
}

async function deleteWorkflow(workflowId: string) {
  const res = await call("delete_workflow", workflowId)
  if (res.success) {
    await loadWorkflows()
  }
  return res
}

async function startWorkflow(workflowId: string, timelineId = "") {
  errorMsg.value = null
  conflicts.value = []
  showConflictView.value = false
  const res = await call("start_workflow", workflowId, timelineId)
  if (!res.success && res.error) {
    errorMsg.value = res.error
  }
  return res
}

async function cancelWorkflow(mode: "immediate" | "after_current" = "immediate") {
  const res = await call("cancel_workflow", mode)
  if (res.success) {
    cancelMode.value = mode
  }
  return res
}

async function handleStepFailure(action: "retry" | "skip" | "abort") {
  showFailureDialog.value = false
  return call("handle_step_failure", action)
}

async function refreshStatus() {
  const res = await call<WorkflowStatus>("get_workflow_status")
  if (res.success && res.data) {
    const d = res.data
    isActive.value = d.active
    if (d.active) {
      instanceId.value = d.workflow_instance_id || null
      workflowName.value = d.workflow_name || ""
      currentStepIndex.value = d.current_step_index || 0
      totalSteps.value = d.total_steps || 0
      stepResults.value = d.step_results || []
      cancelMode.value = d.cancel_mode || ""
    }
  }
  return res
}

async function detectConflicts() {
  const res = await call<{ conflicts: WorkflowConflict[]; total_conflicts: number }>(
    "detect_workflow_conflicts",
  )
  if (res.success && res.data) {
    conflicts.value = res.data.conflicts
    if (conflicts.value.length > 0) {
      showConflictView.value = true
    }
  }
  return res
}

async function resolveConflict(
  segmentId: string,
  resolution: "keep_first" | "keep_last" | "keep_all",
) {
  return call("resolve_workflow_conflict", segmentId, resolution)
}

async function applyWorkflow() {
  const res = await call("apply_workflow")
  if (res.success) {
    isActive.value = false
    conflicts.value = []
    showConflictView.value = false
    instanceId.value = null
  }
  return res
}

async function discardWorkflow() {
  const res = await call("discard_workflow")
  if (res.success) {
    isActive.value = false
    conflicts.value = []
    showConflictView.value = false
    instanceId.value = null
  }
  return res
}

// ---------------------------------------------------------------------------
// Composable export
// ---------------------------------------------------------------------------

export function useWorkflow() {
  ensureListeners()

  const overallProgress = computed(() => {
    if (totalSteps.value === 0) return 0
    return Math.round((currentStepIndex.value / totalSteps.value) * 100)
  })

  return {
    // State
    workflows,
    isActive,
    instanceId,
    workflowName,
    currentStepIndex,
    totalSteps,
    stepResults,
    stepProgress,
    cancelMode,
    errorMsg,
    conflicts,
    showConflictView,
    showFailureDialog,
    failureInfo,
    overallProgress,

    // CRUD
    loadWorkflows,
    saveWorkflow,
    deleteWorkflow,

    // Execution
    startWorkflow,
    cancelWorkflow,
    handleStepFailure,
    refreshStatus,

    // Conflict resolution
    detectConflicts,
    resolveConflict,
    applyWorkflow,
    discardWorkflow,
  }
}

/**
 * Composable for managing LLM analysis tasks (P0 smart-delete, P1 subtitle
 * correction, P2 highlight extraction).
 *
 * Generalized framework for all LLM feature lifecycle + result streaming.
 */
import { ref, computed } from "vue"
import { call, onEvent } from "@/bridge"
import type { MiloTask } from "@/types/task"
import type { Project } from "@/types/project"
import {
  EVENT_LLM_ANALYSIS_FAILED,
  EVENT_LLM_SMART_DELETE_PROGRESS,
  EVENT_LLM_SMART_DELETE_COMPLETED,
  EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED,
  EVENT_LLM_HIGHLIGHT_PROGRESS,
  EVENT_LLM_HIGHLIGHT_COMPLETED,
} from "@/utils/events"

interface SmartDeleteResult {
  segment_id: string
  action: string
  reason: string
  category: string
  confidence: number
}

interface SubtitleCorrectionResult {
  corrected_count: number
  uncovered_count: number
  uncovered_ids: string[]
  orphaned_count: number
  rolled_back_count: number
  partial: boolean
}

interface HighlightResult {
  segment_id: string
  highlight_reason: string
  density: "high" | "medium" | "low"
}

interface JumpCut {
  index: number
  gap_duration: number
  from_end: number
  to_start: number
}

// Singleton state shared across all useLlmTasks() callers
const smartDeleteResults = ref<SmartDeleteResult[]>([])
const subtitleCorrectionResult = ref<SubtitleCorrectionResult | null>(null)
const highlightResults = ref<HighlightResult[]>([])
const highlightTotalDuration = ref(0)
const highlightTargetDuration = ref(600) // 10 min default
const jumpCuts = ref<JumpCut[]>([])
const isRunning = ref(false)
const progress = ref(0)
const errorMsg = ref<string | null>(null)

// LLM configuration status (Phase 2 D-04, D-12)
interface LlmConfigStatus {
  configured: boolean
  model: string
  baseUrl: string
}
const llmConfig = ref<LlmConfigStatus>({ configured: false, model: "", baseUrl: "" })

let listenersRegistered = false

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  // P0 smart-delete: live progress updates
  onEvent<{ results?: SmartDeleteResult[] }>(
    EVENT_LLM_SMART_DELETE_PROGRESS,
    (detail) => {
      if (!detail?.results) return
      // Upsert by segment_id (later results override earlier)
      for (const r of detail.results) {
        const idx = smartDeleteResults.value.findIndex(
          (x) => x.segment_id === r.segment_id,
        )
        if (idx >= 0) {
          smartDeleteResults.value[idx] = r
        } else {
          smartDeleteResults.value.push(r)
        }
      }
    },
  )

  // P0 smart-delete: completed
  onEvent<{ results?: SmartDeleteResult[] }>(
    EVENT_LLM_SMART_DELETE_COMPLETED,
    (detail) => {
      isRunning.value = false
      if (detail?.results) {
        smartDeleteResults.value = detail.results
      }
    },
  )

  // P1 subtitle correction: completed
  onEvent<SubtitleCorrectionResult>(
    EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED,
    (detail) => {
      isRunning.value = false
      if (detail) {
        subtitleCorrectionResult.value = detail
      }
    },
  )

  // P2 highlight: live progress updates
  onEvent<{ results?: HighlightResult[] }>(
    EVENT_LLM_HIGHLIGHT_PROGRESS,
    (detail) => {
      if (!detail?.results) return
      for (const r of detail.results) {
        const idx = highlightResults.value.findIndex(
          (x) => x.segment_id === r.segment_id,
        )
        if (idx >= 0) {
          highlightResults.value[idx] = r
        } else {
          highlightResults.value.push(r)
        }
      }
    },
  )

  // P2 highlight: completed
  onEvent<{
    results?: HighlightResult[]
    total_duration?: number
    target_duration?: number
  }>(EVENT_LLM_HIGHLIGHT_COMPLETED, (detail) => {
    isRunning.value = false
    if (detail?.results) {
      highlightResults.value = detail.results
    }
    if (detail?.total_duration !== undefined) {
      highlightTotalDuration.value = detail.total_duration
    }
    if (detail?.target_duration !== undefined) {
      highlightTargetDuration.value = detail.target_duration
    }
    // Fetch jump cuts after completion
    call<{ jump_cuts?: JumpCut[]; highlight_count?: number }>(
      "detect_highlight_jump_cuts",
    ).then((res) => {
      if (res.success && res.data?.jump_cuts) {
        jumpCuts.value = res.data.jump_cuts
      }
    })
  })

  // LLM failed
  onEvent<{ error?: string }>(EVENT_LLM_ANALYSIS_FAILED, (detail) => {
    isRunning.value = false
    errorMsg.value = detail?.error ?? "LLM analysis failed"
  })
}

export function useLlmTasks() {
  ensureListeners()

  const hasSmartDeleteResults = computed(() => smartDeleteResults.value.length > 0)
  const hasHighlightResults = computed(() => highlightResults.value.length > 0)

  // Load LLM configuration status from backend (Phase 2 D-04/D-12).
  // Stores result in the singleton llmConfig ref so AIAssistantPanel can
  // reflect configured/unconfigured state without repeated calls.
  async function loadLlmConfig(): Promise<void> {
    const res = await call<{
      model?: string
      base_url?: string
      api_key_masked?: string
    }>("get_llm_config")
    if (res.success && res.data) {
      const model = res.data.model ?? ""
      const baseUrl = res.data.base_url ?? ""
      // is_configured requires base_url + api_key + model all non-empty.
      // api_key is masked out by backend, so we treat non-empty model +
      // non-empty base_url as "configured" (api_key presence is implied --
      // the backend masks but doesn't blank base_url/model).
      llmConfig.value = {
        configured: Boolean(model && baseUrl && (res.data.api_key_masked ?? "")),
        model,
        baseUrl,
      }
    }
  }

  function resetSmartDelete() {
    smartDeleteResults.value = []
    progress.value = 0
    errorMsg.value = null
  }

  function resetSubtitleCorrection() {
    subtitleCorrectionResult.value = null
    progress.value = 0
    errorMsg.value = null
  }

  async function startSmartDelete(): Promise<void> {
    isRunning.value = true
    progress.value = 0
    errorMsg.value = null
    resetSmartDelete()

    const res = await call<MiloTask>("start_smart_delete")
    if (!res.success) {
      isRunning.value = false
      errorMsg.value = res.error ?? "Failed to start smart delete"
    }
  }

  async function startSubtitleCorrection(referenceText = ""): Promise<void> {
    isRunning.value = true
    progress.value = 0
    errorMsg.value = null
    resetSubtitleCorrection()

    const res = await call<MiloTask>("start_subtitle_correction", referenceText)
    if (!res.success) {
      isRunning.value = false
      errorMsg.value = res.error ?? "Failed to start subtitle correction"
    }
  }

  function resetHighlight() {
    highlightResults.value = []
    highlightTotalDuration.value = 0
    jumpCuts.value = []
    progress.value = 0
    errorMsg.value = null
  }

  async function startHighlight(targetMinutes = 10): Promise<void> {
    isRunning.value = true
    progress.value = 0
    errorMsg.value = null
    resetHighlight()

    const res = await call<MiloTask>("start_highlight", targetMinutes)
    if (!res.success) {
      isRunning.value = false
      errorMsg.value = res.error ?? "Failed to start highlight extraction"
    }
  }

  async function confirmAllFromSource(
    source: string,
    minConfidence = 0,
  ): Promise<Project | null> {
    const res = await call<Project & { confirmed_count?: number }>(
      "confirm_all_from_source",
      source,
      minConfidence,
    )
    if (res.success && res.data) {
      return res.data
    }
    return null
  }

  return {
    // P0 smart-delete
    smartDeleteResults,
    hasSmartDeleteResults,
    startSmartDelete,
    resetSmartDelete,
    // P1 subtitle correction
    subtitleCorrectionResult,
    startSubtitleCorrection,
    resetSubtitleCorrection,
    // P2 highlight
    highlightResults,
    hasHighlightResults,
    highlightTotalDuration,
    highlightTargetDuration,
    jumpCuts,
    startHighlight,
    resetHighlight,
    // Shared
    isRunning,
    progress,
    errorMsg,
    // LLM configuration (Phase 2)
    llmConfig,
    loadLlmConfig,
    // Batch trust
    confirmAllFromSource,
  }
}

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
  EVENT_TASK_CANCELLED,
  EVENT_DEMO_RESET,
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
  stored_count?: number
}

// v2.1.0 Phase 2: pending correction item (parsed from AnalysisResult detail)
interface SubtitleCorrection {
  id: string
  segment_id: string
  confidence: number
  original_text: string
  corrected_text: string
  changes: string[]
  category: string
  start: number
  end: number
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
// v2.1.0 Phase 2: pending corrections awaiting user review
const pendingCorrections = ref<SubtitleCorrection[]>([])
const correctionsLoading = ref(false)
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

  onEvent(EVENT_DEMO_RESET, () => {
    smartDeleteResults.value = []
    subtitleCorrectionResult.value = null
    pendingCorrections.value = []
    correctionsLoading.value = false
    highlightResults.value = []
    highlightTotalDuration.value = 0
    jumpCuts.value = []
    isRunning.value = false
    progress.value = 0
    errorMsg.value = null
  })

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

  // P1 subtitle correction: completed -> load pending corrections for review
  onEvent<{ stored_count?: number } & Partial<SubtitleCorrectionResult>>(
    EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED,
    async (detail) => {
      isRunning.value = false
      if (detail) {
        subtitleCorrectionResult.value = detail as SubtitleCorrectionResult
        // v2.1.0 Phase 2: auto-load stored corrections for the review UI.
        // The caller must pass the active timeline_id via loadCorrections.
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

  // v2.1.1 M1-2: task cancelled (single-function cancel button). The backend
  // emits TASK_CANCELLED instead of TASK_FAILED; reset the running state so
  // the UI stops spinning and shows the cancel as a clean stop.
  onEvent<{ task_id?: string }>(EVENT_TASK_CANCELLED, () => {
    isRunning.value = false
    progress.value = 0
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
    pendingCorrections.value = []
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

  // v2.1.1: Hydrate highlight state from persisted project data on reopen
  async function hydrateHighlightsFromProject(project: Project): Promise<void> {
    const tl = project.timelines.find(t => t.id === project.active_timeline_id)
    if (!tl) return

    const hlResults = (tl.analysis?.results ?? [])
      .filter(r => r.type === "llm_highlight")

    if (hlResults.length === 0) {
      highlightResults.value = []
      highlightTotalDuration.value = 0
      jumpCuts.value = []
      return
    }

    // Hydrate highlightResults from AnalysisResult records
    highlightResults.value = hlResults.flatMap(r =>
      r.segment_ids.map(sid => ({
        segment_id: sid,
        highlight_reason: r.detail ?? "",
        // confidence 1.0 → high, 0.7 → medium (symmetric with storage logic)
        density: (r.confidence >= 0.9 ? "high" : "medium") as "high" | "medium" | "low",
      }))
    )

    // Recalculate totalDuration from segments
    const segMap = new Map((tl.transcript?.segments ?? []).map(s => [s.id, s]))
    highlightTotalDuration.value = hlResults.reduce((sum, r) => {
      const segs = r.segment_ids.filter(sid => segMap.has(sid)).map(sid => segMap.get(sid)!)
      if (segs.length === 0) return sum
      return sum + (Math.max(...segs.map(s => s.end)) - Math.min(...segs.map(s => s.start)))
    }, 0)

    // Recalculate jumpCuts via backend API
    const jcRes = await call<{ jump_cuts?: JumpCut[]; highlight_count?: number }>(
      "detect_highlight_jump_cuts",
    )
    if (jcRes.success && jcRes.data?.jump_cuts) {
      jumpCuts.value = jcRes.data.jump_cuts
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

  // v2.1.0 Phase 2: P1 correction review methods
  async function loadCorrections(timelineId: string): Promise<void> {
    correctionsLoading.value = true
    const res = await call<SubtitleCorrection[]>("get_subtitle_corrections", timelineId)
    correctionsLoading.value = false
    if (res.success && res.data) {
      pendingCorrections.value = res.data
    }
  }

  async function computeDiff(
    original: string,
    corrected: string,
  ): Promise<{ tokens: { text: string; type: string }[] } | null> {
    const res = await call<{ tokens: { text: string; type: string }[] }>(
      "compute_diff",
      original,
      corrected,
    )
    return res.success && res.data ? res.data : null
  }

  async function acceptCorrection(resultId: string): Promise<boolean> {
    const res = await call<{ segment_id: string }>("accept_correction", resultId)
    if (res.success) {
      pendingCorrections.value = pendingCorrections.value.filter(
        (c) => c.id !== resultId,
      )
      return true
    }
    return false
  }

  async function rejectCorrection(resultId: string): Promise<boolean> {
    const res = await call<{ segment_id: string }>("reject_correction", resultId)
    if (res.success) {
      pendingCorrections.value = pendingCorrections.value.filter(
        (c) => c.id !== resultId,
      )
      return true
    }
    return false
  }

  async function acceptHighConfidenceCorrections(
    timelineId: string,
    threshold = 0.8,
  ): Promise<{ accepted: number; remaining: number } | null> {
    const res = await call<{ accepted_count: number; remaining_count: number }>(
      "accept_high_confidence_corrections",
      timelineId,
      threshold,
    )
    if (res.success && res.data) {
      // Reload to reflect the remaining low-confidence items
      await loadCorrections(timelineId)
      return { accepted: res.data.accepted_count, remaining: res.data.remaining_count }
    }
    return null
  }

  async function clearCorrections(timelineId: string): Promise<boolean> {
    const res = await call<{ cleared_count: number }>(
      "clear_subtitle_corrections",
      timelineId,
    )
    if (res.success) {
      pendingCorrections.value = []
      return true
    }
    return false
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
    // v2.1.0 Phase 2: P1 correction review
    pendingCorrections,
    correctionsLoading,
    loadCorrections,
    computeDiff,
    acceptCorrection,
    rejectCorrection,
    acceptHighConfidenceCorrections,
    clearCorrections,
    // P2 highlight
    highlightResults,
    hasHighlightResults,
    highlightTotalDuration,
    highlightTargetDuration,
    jumpCuts,
    startHighlight,
    resetHighlight,
    hydrateHighlightsFromProject,
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

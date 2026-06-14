/**
 * Composable for managing LLM analysis tasks (P0 smart-delete, P1 subtitle correction).
 *
 * Replaces the old useTopicDrift with a generalized framework that handles
 * task lifecycle, progress events, and result streaming for all LLM features.
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

// Singleton state shared across all useLlmTasks() callers
const smartDeleteResults = ref<SmartDeleteResult[]>([])
const subtitleCorrectionResult = ref<SubtitleCorrectionResult | null>(null)
const isRunning = ref(false)
const progress = ref(0)
const errorMsg = ref<string | null>(null)

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

  // LLM failed
  onEvent<{ error?: string }>(EVENT_LLM_ANALYSIS_FAILED, (detail) => {
    isRunning.value = false
    errorMsg.value = detail?.error ?? "LLM analysis failed"
  })
}

export function useLlmTasks() {
  ensureListeners()

  const hasSmartDeleteResults = computed(() => smartDeleteResults.value.length > 0)

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
    // Shared
    isRunning,
    progress,
    errorMsg,
    // Batch trust
    confirmAllFromSource,
  }
}

import { ref, computed } from "vue"
import { call, onEvent } from "@/bridge"
import { useBridge } from "@/composables/useBridge"
import {
  EVENT_LLM_ANALYSIS_PROGRESS,
  EVENT_LLM_ANALYSIS_COMPLETED,
  EVENT_LLM_ANALYSIS_FAILED,
  EVENT_LLM_TOKEN_USAGE,
} from "@/utils/events"
import type { TopicDriftResult } from "@/types/project"
import type { MiloTask } from "@/types/task"

interface ProgressPayload {
  results: TopicDriftResult[]
  topic_description: string
}

interface TokenUsagePayload {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

let listenersRegistered = false

// Singleton state shared across all useTopicDrift() callers
const results = ref<TopicDriftResult[]>([])
const loading = ref(false)
const progress = ref(0)
const error = ref<string | null>(null)
const topicDescription = ref("")
const tokenUsage = ref<Record<string, number>>({})
const currentTaskId = ref<string | null>(null)

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  onEvent<ProgressPayload>(EVENT_LLM_ANALYSIS_PROGRESS, (detail) => {
    if (!detail?.results) return

    // Upsert: merge chunk results into existing results by segment_id
    const map = new Map(results.value.map((r) => [r.segment_id, r]))
    for (const r of detail.results) {
      map.set(r.segment_id, r)
    }
    results.value = Array.from(map.values())

    // Roughly estimate progress: each progress event advances loading
    if (loading.value && progress.value < 90) {
      progress.value = Math.min(90, progress.value + 10)
    }
  })

  onEvent<{ results?: TopicDriftResult[] }>(EVENT_LLM_ANALYSIS_COMPLETED, (detail) => {
    if (detail?.results) {
      const map = new Map(results.value.map((r) => [r.segment_id, r]))
      for (const r of detail.results) {
        map.set(r.segment_id, r)
      }
      results.value = Array.from(map.values())
    }
    loading.value = false
    progress.value = 100
    currentTaskId.value = null
  })

  onEvent<{ error?: string }>(EVENT_LLM_ANALYSIS_FAILED, (detail) => {
    error.value = detail?.error ?? "Analysis failed"
    loading.value = false
    progress.value = 0
    currentTaskId.value = null
  })

  onEvent<TokenUsagePayload>(EVENT_LLM_TOKEN_USAGE, (detail) => {
    if (!detail) return
    tokenUsage.value = {
      prompt_tokens: (tokenUsage.value.prompt_tokens ?? 0) + (detail.prompt_tokens ?? 0),
      completion_tokens: (tokenUsage.value.completion_tokens ?? 0) + (detail.completion_tokens ?? 0),
      total_tokens: (tokenUsage.value.total_tokens ?? 0) + (detail.total_tokens ?? 0),
    }
  })
}

export function useTopicDrift() {
  ensureListeners()

  // useBridge for component-scoped cleanup (in case we add component-specific listeners later)
  useBridge()

  const sortedResults = computed(() =>
    [...results.value].sort((a, b) => b.relevance - a.relevance),
  )

  const lowRelevanceCount = computed(
    () => results.value.filter((r) => r.relevance < 0.4).length,
  )

  async function startAnalysis(description?: string): Promise<string | null> {
    // Reset state
    results.value = []
    error.value = null
    progress.value = 0
    tokenUsage.value = {}
    topicDescription.value = description ?? ""
    loading.value = true

    const desc = description ?? ""
    const createRes = await call<MiloTask>("start_topic_drift", desc)
    if (!createRes.success || !createRes.data) {
      error.value = createRes.error ?? "Failed to start analysis"
      loading.value = false
      return null
    }

    const taskId = createRes.data.id
    currentTaskId.value = taskId

    const startRes = await call<MiloTask>("start_task", taskId)
    if (!startRes.success) {
      error.value = startRes.error ?? "Failed to start task"
      loading.value = false
      currentTaskId.value = null
      return null
    }

    return taskId
  }

  async function loadResults(): Promise<void> {
    const res = await call<{
      topic_description: string
      results: TopicDriftResult[]
      transcript_hash: string
      last_run: string | null
      token_usage: Record<string, number>
    }>("get_topic_drift_results")

    if (res.success && res.data) {
      results.value = res.data.results ?? []
      topicDescription.value = res.data.topic_description ?? ""
      tokenUsage.value = res.data.token_usage ?? {}
    }
  }

  async function cancelAnalysis(): Promise<void> {
    if (!currentTaskId.value) return
    await call("cancel_task", currentTaskId.value)
    loading.value = false
    progress.value = 0
    currentTaskId.value = null
  }

  function clearResults(): void {
    results.value = []
    error.value = null
    progress.value = 0
    tokenUsage.value = {}
  }

  return {
    results,
    sortedResults,
    loading,
    progress,
    error,
    topicDescription,
    tokenUsage,
    lowRelevanceCount,
    startAnalysis,
    loadResults,
    cancelAnalysis,
    clearResults,
  }
}

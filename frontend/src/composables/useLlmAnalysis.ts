import { ref, computed } from "vue"
import { onEvent } from "@/bridge"
import { EVENT_LLM_TOKEN_USAGE } from "@/utils/events"

interface TokenUsagePayload {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

// Singleton token usage state shared across all useLlmAnalysis() callers
const totalUsage = ref<{
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}>({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 })

const lastUsage = ref<{
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
} | null>(null)

let listenersRegistered = false

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  onEvent<TokenUsagePayload>(EVENT_LLM_TOKEN_USAGE, (detail) => {
    if (!detail) return
    const usage = {
      prompt_tokens: detail.prompt_tokens ?? 0,
      completion_tokens: detail.completion_tokens ?? 0,
      total_tokens: detail.total_tokens ?? 0,
    }
    lastUsage.value = usage
    totalUsage.value = {
      prompt_tokens: totalUsage.value.prompt_tokens + usage.prompt_tokens,
      completion_tokens: totalUsage.value.completion_tokens + usage.completion_tokens,
      total_tokens: totalUsage.value.total_tokens + usage.total_tokens,
    }
  })
}

export function useLlmAnalysis() {
  ensureListeners()

  const formattedTotal = computed(() => {
    const t = totalUsage.value.total_tokens
    if (t >= 1000) return `${(t / 1000).toFixed(1)}k`
    return String(t)
  })

  function resetUsage(): void {
    totalUsage.value = { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }
    lastUsage.value = null
  }

  return {
    totalUsage,
    lastUsage,
    formattedTotal,
    resetUsage,
  }
}

import { ref } from "vue"
import { call } from "@/bridge"

export interface LlmConnectionResult {
  model: string
  response_time_ms: number
}

const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

// Phase 3: Prompt management state
export interface PromptDefaults {
  system: string
  params: Record<string, string[]>
}

export interface PromptOverride {
  system_override?: string | null
  params?: Record<string, string[]>
}

export interface LlmPromptsData {
  defaults: Record<string, PromptDefaults>
  overrides: Record<string, PromptOverride>
}

const promptsData = ref<LlmPromptsData | null>(null)
const loadingPrompts = ref(false)

export function useLlmSettings() {
  async function testConnection(): Promise<boolean> {
    testing.value = true
    testResult.value = null

    const res = await call<LlmConnectionResult>("test_llm_connection")
    testing.value = false

    if (res.success && res.data) {
      testResult.value = {
        success: true,
        message: `Connected to ${res.data.model} (${res.data.response_time_ms}ms)`,
      }
      return true
    }

    testResult.value = {
      success: false,
      message: res.error ?? "Connection failed",
    }
    return false
  }

  // Phase 3: Load all prompt configurations (defaults + overrides)
  async function loadPrompts(): Promise<void> {
    loadingPrompts.value = true
    const res = await call<LlmPromptsData>("get_llm_prompts")
    loadingPrompts.value = false
    if (res.success && res.data) {
      promptsData.value = res.data
    }
  }

  // Phase 3: Update a single prompt's override
  async function updatePrompt(
    funcKey: string,
    updates: PromptOverride,
  ): Promise<boolean> {
    const res = await call<{ func_key: string }>(
      "update_llm_prompt",
      funcKey,
      updates,
    )
    if (res.success) {
      // Refresh local cache
      await loadPrompts()
      return true
    }
    return false
  }

  // Phase 3: Reset a single prompt to default
  async function resetPrompt(funcKey: string): Promise<boolean> {
    const res = await call<{ func_key: string }>(
      "reset_llm_prompt",
      funcKey,
    )
    if (res.success) {
      await loadPrompts()
      return true
    }
    return false
  }

  return {
    testing,
    testResult,
    testConnection,
    // Phase 3: Prompt management
    promptsData,
    loadingPrompts,
    loadPrompts,
    updatePrompt,
    resetPrompt,
  }
}

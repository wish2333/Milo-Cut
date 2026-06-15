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

// v2.1.0 Phase 1: Prompt preset (parameter snapshot per LLM feature)
export interface PromptPreset {
  id: string
  name: string
  params: Record<string, string[]>
  system_override: string
  model: string // D-73 reserved (Phase 1 stores without UI)
  created_at: string
}

const promptsData = ref<LlmPromptsData | null>(null)
const loadingPrompts = ref(false)

// Preset state keyed by func_key
const presetsByFunc = ref<Record<string, PromptPreset[]>>({})
const loadingPresets = ref<Record<string, boolean>>({})

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

  // v2.1.0 Phase 1: Load presets for a feature
  async function loadPresets(funcKey: string): Promise<void> {
    loadingPresets.value[funcKey] = true
    const res = await call<PromptPreset[]>("get_prompt_presets", funcKey)
    loadingPresets.value[funcKey] = false
    if (res.success && res.data) {
      presetsByFunc.value[funcKey] = res.data
    }
  }

  // v2.1.0 Phase 1: Save current params as a new preset
  async function savePreset(
    funcKey: string,
    name: string,
    params: Record<string, string[]>,
    systemOverride = "",
  ): Promise<PromptPreset | null> {
    const res = await call<PromptPreset>(
      "save_prompt_preset",
      funcKey,
      name,
      params,
      systemOverride,
    )
    if (res.success && res.data) {
      // Refresh local cache
      await loadPresets(funcKey)
      return res.data
    }
    return null
  }

  // v2.1.0 Phase 1: Apply a preset (writes to current override)
  async function applyPreset(
    funcKey: string,
    presetId: string,
  ): Promise<boolean> {
    const res = await call<{ func_key: string; preset_id: string }>(
      "apply_prompt_preset",
      funcKey,
      presetId,
    )
    if (res.success) {
      // Refresh override cache so the editor reflects the applied preset
      await loadPrompts()
      return true
    }
    return false
  }

  // v2.1.0 Phase 1: Delete a preset (built-in default is protected)
  async function deletePreset(
    funcKey: string,
    presetId: string,
  ): Promise<boolean> {
    const res = await call<{ func_key: string; preset_id: string }>(
      "delete_prompt_preset",
      funcKey,
      presetId,
    )
    if (res.success) {
      await loadPresets(funcKey)
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
    // v2.1.0 Phase 1: Preset management
    presetsByFunc,
    loadingPresets,
    loadPresets,
    savePreset,
    applyPreset,
    deletePreset,
  }
}

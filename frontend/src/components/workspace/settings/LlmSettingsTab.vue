<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import { useLlmSettings } from "@/composables/useLlmSettings"
import PresetManager from "./PresetManager.vue"
import PromptEditor from "./PromptEditor.vue"

/**
 * LLM settings tab (v3.0.0 M8-1, extracted from SettingsModal.vue).
 *
 * Owns: provider/api-key/base-url/model/thinking/temperature/advanced
 * parameters, test connection, and the full prompt + preset editing logic
 * (moved verbatim; PromptEditor/PresetManager are presentational children).
 * Settings mutations are emitted as patches; busy bubbles to the modal so
 * the footer save button reflects the silent persist before a test.
 */
const props = defineProps<{
  settings: AppSettings
  saving: boolean
}>()

const emit = defineEmits<{
  update: [patch: Partial<AppSettings>]
  busy: [value: boolean]
}>()

// LLM settings (shared singleton composable state)
const {
  testing: llmTesting,
  testResult: llmTestResult,
  testConnection,
  promptsData,
  loadPrompts,
  updatePrompt,
  resetPrompt,
  // v2.1.0 Phase 1: Preset management
  presetsByFunc,
  loadPresets,
  savePreset,
  applyPreset,
  deletePreset,
} = useLlmSettings()
const showLlmKey = ref(false)

// Phase 3: Prompt editing state
const promptFuncKeys = [
  { key: "smart_delete", label: "智能删除" },
  { key: "subtitle_correction_a", label: "字幕修正 (模式 A)" },
  { key: "subtitle_correction_b", label: "字幕修正 (模式 B)" },
  { key: "highlight", label: "精华提取" },
  { key: "search", label: "语义搜索" },
] as const

const selectedPromptKey = ref<string>("smart_delete")
const promptEditMode = ref<"simple" | "advanced">("simple")
const promptParamText = ref<Record<string, string>>({})  // textarea text per param
const promptSystemOverride = ref("")
const promptSaving = ref(false)
const promptStatusMsg = ref("")

// Param labels for simple mode UI
const promptParamLabels: Record<string, string> = {
  custom_fillers: "自定义口头禅 (每行一个)",
  glossary: "术语表 (每行一个)",
  focus_keywords: "关注关键词 (每行一个)",
}

// Placeholder hint text for advanced mode (avoid {{ }} in template)
const placeholderHint = "留空使用默认提示词 + 简单模式参数"

// v2.1.0 Phase 1: Preset management state
// search (P3) has no presets per D-41.
const presetSupportedKeys = new Set(["smart_delete", "subtitle_correction_a", "subtitle_correction_b", "highlight"])
const selectedPresetId = ref<string>("")
const showSavePresetInput = ref(false)
const newPresetName = ref("")
const presetBusy = ref(false)

const currentPresets = computed(() => presetsByFunc.value[selectedPromptKey.value] ?? [])
const presetSupported = computed(() => presetSupportedKeys.has(selectedPromptKey.value))
const defaultSystem = computed(() => promptsData.value?.defaults?.[selectedPromptKey.value]?.system)

function loadPromptEditor(funcKey: string) {
  const defaults = promptsData.value?.defaults?.[funcKey]
  const override = promptsData.value?.overrides?.[funcKey]
  // Initialize param text from override or default
  promptParamText.value = {}
  if (defaults?.params) {
    for (const [k, v] of Object.entries(defaults.params)) {
      const overrideVals = override?.params?.[k]
      promptParamText.value[k] = (overrideVals ?? v).join("\n")
    }
  }
  promptSystemOverride.value = override?.system_override ?? ""
}

async function handlePromptKeyChange(key: string) {
  selectedPromptKey.value = key
  if (!promptsData.value) await loadPrompts()
  loadPromptEditor(key)
  // Reset preset selection on feature switch
  selectedPresetId.value = ""
  showSavePresetInput.value = false
  // Load presets for the newly selected feature (if supported)
  if (presetSupportedKeys.has(key)) {
    await loadPresets(key)
  }
}

async function handleSavePrompt() {
  promptSaving.value = true
  promptStatusMsg.value = ""
  const funcKey = selectedPromptKey.value
  if (promptEditMode.value === "advanced") {
    const success = await updatePrompt(funcKey, {
      system_override: promptSystemOverride.value,
    })
    promptStatusMsg.value = success ? "已保存" : "保存失败"
  } else {
    // Convert textarea text to list arrays
    const params: Record<string, string[]> = {}
    for (const [k, text] of Object.entries(promptParamText.value)) {
      params[k] = text.split("\n").map(s => s.trim()).filter(Boolean)
    }
    const success = await updatePrompt(funcKey, { params })
    promptStatusMsg.value = success ? "已保存" : "保存失败"
  }
  promptSaving.value = false
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleResetPrompt() {
  const funcKey = selectedPromptKey.value
  const success = await resetPrompt(funcKey)
  if (success) {
    loadPromptEditor(funcKey)
    promptStatusMsg.value = "已重置为默认"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
  }
}

// v2.1.0 Phase 1: Preset handlers
async function handleApplyPreset() {
  if (!selectedPresetId.value) return
  presetBusy.value = true
  promptStatusMsg.value = ""
  const ok = await applyPreset(selectedPromptKey.value, selectedPresetId.value)
  presetBusy.value = false
  if (ok) {
    // Reload editor so the textareas reflect the applied preset
    loadPromptEditor(selectedPromptKey.value)
    promptStatusMsg.value = "预设已应用"
  } else {
    promptStatusMsg.value = "应用失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleSaveAsPreset() {
  const name = newPresetName.value.trim()
  if (!name) {
    promptStatusMsg.value = "请输入预设名称"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
    return
  }
  const funcKey = selectedPromptKey.value
  // Snapshot current editor contents (same logic as handleSavePrompt)
  const params: Record<string, string[]> = {}
  for (const [k, text] of Object.entries(promptParamText.value)) {
    params[k] = text.split("\n").map(s => s.trim()).filter(Boolean)
  }
  presetBusy.value = true
  promptStatusMsg.value = ""
  const created = await savePreset(
    funcKey,
    name,
    params,
    promptEditMode.value === "advanced" ? promptSystemOverride.value : "",
  )
  presetBusy.value = false
  if (created) {
    showSavePresetInput.value = false
    newPresetName.value = ""
    selectedPresetId.value = created.id
    promptStatusMsg.value = "预设已保存"
  } else {
    promptStatusMsg.value = "保存失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleDeletePreset() {
  if (!selectedPresetId.value) return
  const preset = currentPresets.value.find(p => p.id === selectedPresetId.value)
  if (!preset) return
  // Built-in default is protected server-side; double-check client-side.
  if (preset.id === "default") {
    promptStatusMsg.value = "内置默认预设不可删除"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
    return
  }
  if (!window.confirm(`确认删除预设「${preset.name}」？`)) return
  presetBusy.value = true
  promptStatusMsg.value = ""
  const ok = await deletePreset(selectedPromptKey.value, selectedPresetId.value)
  presetBusy.value = false
  if (ok) {
    selectedPresetId.value = ""
    promptStatusMsg.value = "预设已删除"
  } else {
    promptStatusMsg.value = "删除失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

function handleCancelSavePreset() {
  showSavePresetInput.value = false
  newPresetName.value = ""
}

const llmProviders = [
  { id: "deepseek" as const, label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-v4-flash" },
  { id: "openai" as const, label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-5.4-mini" },
  { id: "qwen" as const, label: "Qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { id: "glm" as const, label: "GLM (智谱)", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5-turbo" },
  { id: "custom" as const, label: "Custom (自定义)", baseUrl: "", model: "" },
]

// Providers that do NOT support thinking mode (OpenAI GPT series).
// DeepSeek, Qwen, GLM, Custom all support thinking via extra_body.
const _NO_THINK_PROVIDERS = new Set(["openai"])

function onLlmProviderChange(provider: string) {
  const current = props.settings
  const oldProvider = current.llm_provider

  // Persist current provider's values before switching
  const configs = { ...(current.llm_provider_configs ?? {}) }
  configs[oldProvider] = {
    base_url: current.llm_base_url,
    api_key: current.llm_api_key,
    model: current.llm_model,
  }

  // Restore target provider's persisted values, or fall back to defaults
  const info = llmProviders.find(p => p.id === provider)
  const cached = configs[provider]
  emit("update", {
    llm_provider: provider as AppSettings["llm_provider"],
    llm_base_url: cached?.base_url ?? info?.baseUrl ?? "",
    llm_api_key: cached?.api_key ?? "",
    llm_model: cached?.model ?? info?.model ?? "",
    llm_provider_configs: configs,
  })
}

function providerSupportsThinking(providerId: string): boolean {
  return !_NO_THINK_PROVIDERS.has(providerId)
}

function isOllamaUrl(url?: string): boolean {
  return typeof url === "string" && url.includes("localhost:11434")
}

// Test Connection: persist current form to backend first, then run the test.
// Without saving, the backend would test the previously-stored config rather
// than what the user just typed into the form.
async function handleTestConnection() {
  // Persist silently -- we don't want "Settings saved" flashing before the test
  emit("busy", true)
  const res = await call<AppSettings>("update_settings", props.settings)
  emit("busy", false)
  if (!res.success) {
    llmTestResult.value = { success: false, message: "Failed to save settings before test" }
    return
  }
  await testConnection()
}

onMounted(async () => {
  // Phase 3: Load LLM prompt configurations
  await loadPrompts()
  loadPromptEditor(selectedPromptKey.value)
  // v2.1.0 Phase 1: Load presets for the default selected feature
  if (presetSupportedKeys.has(selectedPromptKey.value)) {
    await loadPresets(selectedPromptKey.value)
  }
})
</script>

<template>
  <div class="space-y-6">
    <p class="text-xs text-gray-400">API Key is stored locally and never sent to our servers.</p>

    <section>
      <label class="block text-sm font-medium text-gray-700 mb-1">Provider</label>
      <select
        :value="props.settings.llm_provider"
        class="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        @change="onLlmProviderChange(($event.target as HTMLSelectElement).value)"
      >
        <option v-for="p in llmProviders" :key="p.id" :value="p.id">{{ p.label }}</option>
      </select>
    </section>

    <section>
      <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
      <div class="flex gap-2">
        <input
          :type="showLlmKey ? 'text' : 'password'"
          :value="props.settings.llm_api_key"
          placeholder="sk-..."
          class="flex-1 rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          @input="emit('update', { llm_api_key: ($event.target as HTMLInputElement).value })"
        />
        <button
          type="button"
          class="rounded border border-gray-300 px-3 py-2 text-xs text-gray-600 hover:bg-gray-50"
          @click="showLlmKey = !showLlmKey"
        >
          {{ showLlmKey ? 'Hide' : 'Show' }}
        </button>
      </div>
    </section>

    <!-- Base URL --- visible for all, editable for power users -->
    <section>
      <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
      <input
        type="text"
        :value="props.settings.llm_base_url"
        placeholder="https://api.openai.com/v1"
        class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        @input="emit('update', { llm_base_url: ($event.target as HTMLInputElement).value })"
      />
      <p v-if="isOllamaUrl(props.settings.llm_base_url)" class="mt-1 text-xs text-green-600">Ollama detected</p>

      <!-- Custom provider tutorial -->
      <div v-if="props.settings.llm_provider === 'custom'" class="mt-2 rounded border border-blue-100 bg-blue-50 p-2 text-xs text-blue-700 space-y-1">
        <p><strong>自定义供应商说明:</strong></p>
        <p>1. 在 <strong>Base URL</strong> 填入 API 的完整地址，以 <code>/v1</code> 结尾</p>
        <p>2. 在 <strong>Model</strong> 填入你想要使用的模型名称</p>
        <p>3. 确保 API 兼容 OpenAI 格式 (如 Ollama、vLLM、LiteLLM 等)</p>
      </div>
    </section>

    <section>
      <label class="block text-sm font-medium text-gray-700 mb-1">Model</label>
      <input
        type="text"
        :value="props.settings.llm_model"
        :placeholder="providerSupportsThinking(props.settings.llm_provider) ? 'deepseek-v4-flash' : 'gpt-5.4-mini'"
        class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        @input="emit('update', { llm_model: ($event.target as HTMLInputElement).value })"
      />
    </section>

    <!-- Thinking mode toggle (not supported by OpenAI GPT models) -->
    <section>
      <label class="relative flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          :checked="props.settings.llm_thinking_enabled ?? false"
          :disabled="!providerSupportsThinking(props.settings.llm_provider)"
          class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
          @change="emit('update', { llm_thinking_enabled: ($event.target as HTMLInputElement).checked })"
        />
        <span class="text-sm font-medium text-gray-700 select-none" :class="{ 'opacity-40': !providerSupportsThinking(props.settings.llm_provider) }">
          深度思考 (Thinking)
        </span>
      </label>
      <p v-if="!providerSupportsThinking(props.settings.llm_provider)" class="mt-1 text-xs text-gray-400">
        OpenAI GPT 系列模型不支持深度思考模式
      </p>
      <p v-else class="mt-1 text-xs text-gray-400">
        启用链式推理 (Chain-of-Thought)，让模型在回答前进行深度思考。适合复杂推理任务，但会增加响应时间和 Token 消耗
      </p>
    </section>

    <section>
      <label class="block text-sm font-medium text-gray-700 mb-1">
        Temperature: {{ props.settings.llm_temperature.toFixed(1) }}
      </label>
      <input
        type="range"
        min="0"
        max="1"
        step="0.1"
        :value="props.settings.llm_temperature"
        class="w-full"
        @input="emit('update', { llm_temperature: parseFloat(($event.target as HTMLInputElement).value) })"
      />
    </section>

    <!-- v2.1.1 M2: Advanced LLM parameters (chunking / batching / concurrency) -->
    <section class="border-t border-gray-200 pt-4">
      <details class="group">
        <summary class="flex cursor-pointer items-center gap-1 text-sm font-medium text-gray-700 select-none">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
          高级参数
        </summary>
        <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="text-xs text-gray-600">智能删除批次大小 (条)</span>
            <input
              type="number"
              step="1"
              min="5"
              :value="props.settings.llm_smart_batch_size"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); emit('update', { llm_smart_batch_size: Number.isNaN(v) ? 20 : v }) })()"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">智能删除重叠 (条)</span>
            <input
              type="number"
              step="1"
              min="0"
              :value="props.settings.llm_smart_overlap_size"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); emit('update', { llm_smart_overlap_size: Number.isNaN(v) ? 4 : v }) })()"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">批字符上限 (v3.0.0, 0=不限)</span>
            <input
              type="number"
              step="100"
              min="0"
              :value="props.settings.llm_max_batch_chars ?? 4000"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); emit('update', { llm_max_batch_chars: Number.isNaN(v) ? 4000 : v }) })()"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">字幕修正批次大小</span>
            <input
              type="number"
              step="1"
              min="1"
              :value="props.settings.llm_correction_batch_size"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="emit('update', { llm_correction_batch_size: parseInt(($event.target as HTMLInputElement).value) || 30 })"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">字幕修正上下文窗口</span>
            <input
              type="number"
              step="1"
              min="0"
              :value="props.settings.llm_correction_context_window"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="emit('update', { llm_correction_context_window: parseInt(($event.target as HTMLInputElement).value) || 5 })"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">精华提取窗口 (秒)</span>
            <input
              type="number"
              step="10"
              min="60"
              :value="props.settings.llm_highlight_chunk_duration"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="emit('update', { llm_highlight_chunk_duration: parseFloat(($event.target as HTMLInputElement).value) || 1800.0 })"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">精华提取重叠 (秒)</span>
            <input
              type="number"
              step="1"
              min="0"
              :value="props.settings.llm_highlight_overlap_duration"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="emit('update', { llm_highlight_overlap_duration: parseFloat(($event.target as HTMLInputElement).value) || 60.0 })"
            />
          </label>
          <label class="block">
            <span class="text-xs text-gray-600">LLM 并发数</span>
            <input
              type="number"
              step="1"
              min="1"
              max="20"
              :value="props.settings.llm_concurrency"
              class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              @change="emit('update', { llm_concurrency: parseInt(($event.target as HTMLInputElement).value) || 5 })"
            />
          </label>
        </div>
        <p class="mt-2 text-xs text-gray-400">
          较大批次减少 API 调用次数但单次耗时更长。并发数过高可能触发 API 限流。
          取消后已发出的请求仍会消耗少量 Token。
        </p>
      </details>
    </section>

    <section class="flex items-center gap-3">
      <button
        type="button"
        :disabled="llmTesting || saving || !props.settings.llm_api_key"
        class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        @click="handleTestConnection"
      >
        {{ llmTesting ? 'Testing...' : (saving ? 'Saving...' : 'Test Connection') }}
      </button>
      <span v-if="llmTestResult" :class="llmTestResult.success ? 'text-green-600' : 'text-red-600'" class="text-sm">
        {{ llmTestResult.message }}
      </span>
    </section>

    <PromptEditor
      :func-keys="promptFuncKeys"
      :selected-prompt-key="selectedPromptKey"
      :prompt-edit-mode="promptEditMode"
      :prompt-param-text="promptParamText"
      :prompt-param-labels="promptParamLabels"
      :prompt-system-override="promptSystemOverride"
      :prompt-saving="promptSaving"
      :prompt-status-msg="promptStatusMsg"
      :placeholder-hint="placeholderHint"
      :default-system="defaultSystem"
      @change-key="handlePromptKeyChange"
      @update:mode="promptEditMode = $event"
      @update:param="(key, value) => promptParamText[key] = value"
      @update:override="promptSystemOverride = $event"
      @save="handleSavePrompt"
      @reset="handleResetPrompt"
    >
      <template #preset-bar>
        <PresetManager
          :preset-supported="presetSupported"
          :presets="currentPresets"
          :selected-preset-id="selectedPresetId"
          :preset-busy="presetBusy"
          :show-save-preset-input="showSavePresetInput"
          :new-preset-name="newPresetName"
          @select="selectedPresetId = $event"
          @toggle-save-input="showSavePresetInput = !showSavePresetInput"
          @apply="handleApplyPreset"
          @save-as="handleSaveAsPreset"
          @delete="handleDeletePreset"
          @update-new-name="newPresetName = $event"
          @cancel-save="handleCancelSavePreset"
        />
      </template>
    </PromptEditor>
  </div>
</template>

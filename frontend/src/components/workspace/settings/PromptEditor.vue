<script setup lang="ts">
/**
 * Prompt editing panel for the LLM tab (v3.0.0 M8-1).
 * Presentational only: function selector, simple/advanced mode toggle,
 * parameter textareas, full-prompt override textarea and action buttons.
 * The `preset-bar` slot keeps the preset bar inside this section (between
 * the function selector and the mode toggle) exactly as in the original
 * SettingsModal layout. All state and handlers live in LlmSettingsTab.vue.
 */
defineProps<{
  funcKeys: readonly { key: string; label: string }[]
  selectedPromptKey: string
  promptEditMode: "simple" | "advanced"
  promptParamText: Record<string, string>
  promptParamLabels: Record<string, string>
  promptSystemOverride: string
  promptSaving: boolean
  promptStatusMsg: string
  placeholderHint: string
  defaultSystem: string | undefined
}>()

const emit = defineEmits<{
  "change-key": [key: string]
  "update:mode": [mode: "simple" | "advanced"]
  "update:param": [key: string, value: string]
  "update:override": [value: string]
  save: []
  reset: []
}>()
</script>

<template>
  <!-- Phase 3: Prompt editing section -->
  <section class="border-t border-gray-200 pt-4">
    <h3 class="text-sm font-semibold text-gray-700 mb-3">提示词编辑</h3>

    <!-- Function selector -->
    <div class="flex items-center gap-2 mb-3">
      <label class="text-xs text-gray-500">功能:</label>
      <select
        :value="selectedPromptKey"
        class="px-2 py-1 text-xs border border-gray-300 rounded"
        @change="emit('change-key', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="f in funcKeys" :key="f.key" :value="f.key">
          {{ f.label }}
        </option>
      </select>
    </div>

    <!-- Preset bar renders here (original DOM position preserved) -->
    <slot name="preset-bar"></slot>

    <!-- Mode toggle -->
    <div class="flex items-center gap-3 mb-3">
      <label class="flex items-center gap-1 text-xs">
        <input
          type="radio"
          value="simple"
          :checked="promptEditMode === 'simple'"
          @change="emit('update:mode', 'simple')"
        />
        简单模式
      </label>
      <label class="flex items-center gap-1 text-xs">
        <input
          type="radio"
          value="advanced"
          :checked="promptEditMode === 'advanced'"
          @change="emit('update:mode', 'advanced')"
        />
        高级模式
      </label>
    </div>

    <!-- Simple mode: parameter fields -->
    <div v-if="promptEditMode === 'simple'" class="space-y-3">
      <div
        v-for="(_text, paramKey) in promptParamText"
        :key="paramKey"
      >
        <label class="block text-xs font-medium text-gray-600 mb-1">
          {{ promptParamLabels[paramKey] ?? paramKey }}
        </label>
        <textarea
          :value="promptParamText[paramKey]"
          class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
          rows="3"
          :placeholder="'每行一个'"
          @input="emit('update:param', paramKey, ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </div>
      <p v-if="Object.keys(promptParamText).length === 0" class="text-xs text-gray-400">
        此功能无可配置参数
      </p>
    </div>

    <!-- Advanced mode: full prompt textarea -->
    <div v-else class="space-y-2">
      <label class="block text-xs font-medium text-gray-600">
        完整提示词 (含标记位)
      </label>
      <textarea
        :value="promptSystemOverride"
        class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
        rows="10"
        :placeholder="placeholderHint"
        @input="emit('update:override', ($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <details class="text-xs text-gray-500">
        <summary class="cursor-pointer">查看默认提示词</summary>
        <pre class="mt-2 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">{{ defaultSystem ?? '(无)' }}</pre>
      </details>
    </div>

    <!-- Action buttons -->
    <div class="flex items-center gap-2 mt-3">
      <button
        class="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
        :disabled="promptSaving"
        @click="emit('save')"
      >
        {{ promptSaving ? '保存中...' : '保存' }}
      </button>
      <button
        class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
        @click="emit('reset')"
      >
        重置为默认
      </button>
      <span v-if="promptStatusMsg" class="text-xs text-green-600">
        {{ promptStatusMsg }}
      </span>
    </div>
  </section>
</template>

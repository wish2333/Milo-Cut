<script setup lang="ts">
import type { PromptPreset } from "@/composables/useLlmSettings"

/**
 * Preset management bar for the LLM prompt editor (v3.0.0 M8-1).
 * Presentational only: preset selection, apply / save-as / delete actions
 * and the inline save-as input. All state and handlers live in
 * LlmSettingsTab.vue (logic moved verbatim from SettingsModal.vue).
 */
defineProps<{
  presetSupported: boolean
  presets: PromptPreset[]
  selectedPresetId: string
  presetBusy: boolean
  showSavePresetInput: boolean
  newPresetName: string
}>()

const emit = defineEmits<{
  select: [id: string]
  "toggle-save-input": []
  apply: []
  "save-as": []
  delete: []
  "update-new-name": [value: string]
  "cancel-save": []
}>()
</script>

<template>
  <!-- v2.1.0 Phase 1: Preset management (only for supported features) -->
  <div v-if="presetSupported" class="border border-gray-200 rounded p-2 mb-3 bg-gray-50">
    <div class="flex items-center gap-2 flex-wrap">
      <label class="text-xs text-gray-500">预设:</label>
      <select
        :value="selectedPresetId"
        class="px-2 py-1 text-xs border border-gray-300 rounded bg-white"
        @change="emit('select', ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>(选择预设)</option>
        <option v-for="p in presets" :key="p.id" :value="p.id">
          {{ p.name }}{{ p.id === 'default' ? ' (内置)' : '' }}
        </option>
      </select>
      <button
        class="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
        :disabled="!selectedPresetId || presetBusy"
        @click="emit('apply')"
      >应用</button>
      <button
        class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
        :disabled="presetBusy"
        @click="emit('toggle-save-input')"
      >另存为预设</button>
      <button
        class="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
        :disabled="!selectedPresetId || presetBusy"
        @click="emit('delete')"
      >删除</button>
    </div>
    <!-- Save-as-preset inline input -->
    <div v-if="showSavePresetInput" class="flex items-center gap-2 mt-2">
      <input
        :value="newPresetName"
        class="flex-1 px-2 py-1 text-xs border border-gray-300 rounded"
        placeholder="预设名称 (如: 学术报告)"
        @input="emit('update-new-name', ($event.target as HTMLInputElement).value)"
        @keyup.enter="emit('save-as')"
      />
      <button
        class="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700 disabled:opacity-50"
        :disabled="presetBusy"
        @click="emit('save-as')"
      >保存</button>
      <button
        class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        @click="emit('cancel-save')"
      >取消</button>
    </div>
    <p class="text-xs text-gray-400 mt-1">应用预设会将参数写入当前配置;另存为预设将当前编辑区参数保存为新预设</p>
  </div>
</template>

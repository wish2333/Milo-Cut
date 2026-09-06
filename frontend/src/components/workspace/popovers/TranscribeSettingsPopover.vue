<script setup lang="ts">
import type { ModelInfo } from "@/types/project"

/**
 * Transcription settings popover (v3.0.0 M8-2a, moved verbatim from
 * WorkspacePage.vue toolbar). Positioning/visibility stays controlled by
 * the parent (`v-if` + relative anchor). All ASR engine state flows in via
 * named v-models; the save action bubbles up (parent persists to settings
 * and closes the popover).
 */
interface InstalledEngine {
  engine: string
  displayName: string
  pluginId: string
  ready: boolean
}

defineProps<{
  hasInstalledEngines: boolean
  installedEngines: InstalledEngine[]
  availableModels: ModelInfo[]
  asrEngine: string
  isMlx: boolean
  isDarwin: boolean
  supportsGpu: boolean
  computeTypeOptions: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  save: []
}>()

const asrPluginId = defineModel<string>("asrPluginId", { required: true })
const modelSize = defineModel<string>("modelSize", { required: true })
const language = defineModel<string>("language", { required: true })
const device = defineModel<string>("device", { required: true })
const computeType = defineModel<string>("computeType", { required: true })
const vadFilter = defineModel<boolean>("vadFilter", { required: true })
const vadThreshold = defineModel<number>("vadThreshold", { required: true })
const vadMinSilenceMs = defineModel<number>("vadMinSilenceMs", { required: true })
</script>

<template>
  <div
    class="absolute top-full left-0 mt-1 w-72 rounded-md border border-gray-200 bg-white shadow-lg z-dropdown p-3"
  >
    <div class="mb-2 text-xs font-semibold text-ink">转写设置</div>

    <!-- No engines installed warning -->
    <div v-if="!hasInstalledEngines" class="text-xs text-amber-600 mb-2 p-2 bg-amber-50 rounded">
      No ASR engine installed. Please install an engine in Settings > AI Engine.
    </div>

    <template v-else>
      <!-- Engine selector -->
      <label class="block mb-2">
        <span class="text-xs text-gray-500">Engine</span>
        <select
          v-model="asrPluginId"
          class="w-full mt-1 rounded border-gray-300 text-xs"
        >
          <option v-for="eng in installedEngines" :key="eng.pluginId" :value="eng.pluginId">
            {{ eng.displayName }} {{ eng.ready ? '' : '(model not downloaded)' }}
          </option>
        </select>
      </label>

      <!-- Model selector -->
      <label class="block mb-2">
        <span class="text-xs text-gray-500">Model</span>
        <select
          v-model="modelSize"
          class="w-full mt-1 rounded border-gray-300 text-xs"
        >
          <option v-for="m in availableModels" :key="m.model_id" :value="m.model_id">
            {{ m.display_name }} {{ m.status === 'downloaded' ? '' : '(not downloaded)' }}
          </option>
        </select>
      </label>

      <!-- Language -->
      <label class="block mb-2">
        <span class="text-xs text-gray-500">Language</span>
        <select v-model="language" class="w-full mt-1 rounded border-gray-300 text-xs">
          <option value="auto">Auto-detect</option>
          <option value="zh">Chinese</option>
          <option value="en">English</option>
          <option value="ja">Japanese</option>
          <option value="ko">Korean</option>
        </select>
      </label>

      <!-- Device (hidden for MLX -- always uses Apple Silicon) -->
      <label v-if="!isMlx" class="block mb-2">
        <span class="text-xs text-gray-500">Device</span>
        <select v-model="device" class="w-full mt-1 rounded border-gray-300 text-xs">
          <option v-if="!isDarwin" value="cpu">CPU</option>
          <option v-if="supportsGpu" value="cuda">CUDA (GPU)</option>
          <option v-if="asrEngine === 'faster-whisper'" value="auto">Auto</option>
          <option v-if="isDarwin && asrEngine === 'qwen3-asr'" value="mps">MPS</option>
        </select>
        <span v-if="isDarwin && asrEngine === 'faster-whisper'" class="text-xs text-gray-400 mt-0.5 block">MPS (Metal Performance Shaders)</span>
        <span v-else-if="isDarwin && asrEngine === 'qwen3-asr'" class="text-xs text-gray-400 mt-0.5 block">Metal Performance Shaders (Apple GPU)</span>
        <span v-else-if="!supportsGpu" class="text-xs text-gray-400 mt-0.5 block">GPU not available for this engine plugin</span>
      </label>
      <div v-else class="text-xs text-gray-400 mb-2">Apple Silicon (Metal)</div>

      <!-- Compute type (hidden for MLX) -->
      <label v-if="!isMlx && computeTypeOptions.length > 0" class="block mb-2">
        <span class="text-xs text-gray-500">Compute Type</span>
        <select v-model="computeType" class="w-full mt-1 rounded border-gray-300 text-xs">
          <option v-for="opt in computeTypeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>

      <!-- VAD filter -->
      <label class="flex items-center gap-2 mb-2 cursor-pointer">
        <input
          type="checkbox"
          v-model="vadFilter"
          class="w-4 h-4 accent-blue-600"
        />
        <span class="text-xs text-gray-500">VAD filter (reduce hallucinations)</span>
      </label>

      <!-- VAD sliders (visible when vad_filter is on) -->
      <template v-if="vadFilter">
        <label class="block mb-2">
          <span class="text-xs text-gray-500">
            VAD Threshold: {{ vadThreshold.toFixed(2) }}
          </span>
          <input
            type="range"
            v-model.number="vadThreshold"
            min="0.0"
            max="1.0"
            step="0.05"
            class="w-full mt-1"
          />
        </label>
        <label class="block mb-3">
          <span class="text-xs text-gray-500">
            Min Silence (ms): {{ vadMinSilenceMs }}
          </span>
          <input
            type="range"
            v-model.number="vadMinSilenceMs"
            min="100"
            max="2000"
            step="50"
            class="w-full mt-1"
          />
        </label>
      </template>

      <!-- Save button -->
      <button
        class="mc-button mc-button-secondary w-full px-2 text-xs"
        @click="emit('save')"
      >
       保存为默认设置
      </button>
    </template>
  </div>
</template>

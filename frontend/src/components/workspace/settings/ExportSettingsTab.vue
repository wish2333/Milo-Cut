<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import { useAsrEngines, deriveEngineChangePatch } from "@/composables/useAsrEngines"

/**
 * Export & ASR defaults settings tab (v3.0.0 M8-1, extracted from
 * SettingsModal.vue; ASR section re-wired in M8-2b).
 *
 * Owns: export codec/bitrate/preset/CRF/resolution/transitions and the
 * hardware encoder detection feeding the codec list.
 * The ASR defaults section is a view of the shared `useAsrEngines` domain
 * (single source together with WorkspacePage): edits update the shared
 * state immediately (the other UI follows) AND emit an AppSettings patch
 * so the modal 保存 persists the same values.
 */
const props = defineProps<{
  settings: AppSettings
}>()

const emit = defineEmits<{
  update: [patch: Partial<AppSettings>]
}>()

// -- Shared ASR engine domain (M8-2b) ------------------------------------

const {
  asrEngine,
  asrPluginId,
  currentSettings,
  installedEngines,
  availableModels,
  isDarwin,
  isMlx,
  supportsGpu,
  ensureLoaded,
} = useAsrEngines()

// Engine dropdown source (original modal filter: faster-whisper/qwen3-asr engines)
const installedAsrEngines = computed(() =>
  installedEngines.value.filter(e => e.engine === "faster-whisper" || e.engine === "qwen3-asr"),
)

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  emit("update", { [key]: value } as Partial<AppSettings>)
}

// Handle engine plugin change: derive engine type, reset device/compute defaults.
// Updates the shared domain state (workspace follows) + emits the settings patch.
function handleEnginePluginChange(pluginId: string) {
  const eng = installedEngines.value.find(e => e.pluginId === pluginId)
  if (!eng) return  // fallback option (engine name only, nothing installed)
  asrPluginId.value = pluginId
  emit("update", (deriveEngineChangePatch(pluginId, eng.engine) ?? {}) as Partial<AppSettings>)
}

function changeModelSize(value: string) {
  currentSettings.value.model_size = value
  emit("update", { asr_model_size: value })
}

function changeLanguage(value: string) {
  currentSettings.value.language = value
  emit("update", { asr_language: value })
}

function changeDevice(value: "cpu" | "cuda" | "auto" | "mps") {
  currentSettings.value.device = value
  emit("update", { asr_device: value })
}

function changeComputeType(value: string) {
  currentSettings.value.compute_type = value
  emit("update", asrEngine.value === "faster-whisper"
    ? { whisper_compute_type: value as AppSettings["whisper_compute_type"] }
    : { qwen_compute_type: value as AppSettings["qwen_compute_type"] })
}

function changeVadFilter(checked: boolean) {
  currentSettings.value.vad_filter = checked
  emit("update", { asr_vad_filter: checked })
}

function changeVadThreshold(value: number) {
  currentSettings.value.vad_threshold = value
  emit("update", { whisper_vad_threshold: value })
}

function changeVadMinSilenceMs(value: number) {
  currentSettings.value.vad_min_silence_ms = value
  emit("update", { whisper_vad_min_silence_ms: value })
}

// -- Export section: hardware encoder detection ---------------------------

interface EncoderMeta {
  label: string
  qualityMode: string
  recommendedQuality: number
  qualityRange: [number, number]
}

const gpuEncoders = ref<string[]>([])
const encoderMeta = ref<Record<string, EncoderMeta>>({})

// Display order for hardware encoders; CPU encoders are always available.
const HW_ENCODER_ORDER = [
  "h264_nvenc", "hevc_nvenc", "av1_nvenc",
  "h264_qsv", "hevc_qsv", "av1_qsv",
  "h264_amf", "hevc_amf",
  "h264_videotoolbox", "hevc_videotoolbox",
]

const availableVideoCodecs = computed(() => {
  const list: { value: string; label: string }[] = [
    { value: "libx264", label: encoderMeta.value["libx264"]?.label ?? "libx264 (CPU)" },
    { value: "libx265", label: encoderMeta.value["libx265"]?.label ?? "libx265 (CPU)" },
  ]
  if (gpuEncoders.value.includes("libsvtav1")) {
    list.push({ value: "libsvtav1", label: encoderMeta.value["libsvtav1"]?.label ?? "libsvtav1 (CPU)" })
  }
  for (const enc of HW_ENCODER_ORDER) {
    if (gpuEncoders.value.includes(enc)) {
      list.push({ value: enc, label: encoderMeta.value[enc]?.label ?? enc })
    }
  }
  // Preserve persisted selection even if detection missed it (e.g. custom ffmpeg build)
  const selected = props.settings.export_video_codec
  if (selected && !list.some(c => c.value === selected)) {
    list.unshift({ value: selected, label: encoderMeta.value[selected]?.label ?? selected })
  }
  return list
})

onMounted(async () => {
  // Shared ASR domain load (single-flight; engines before settings hydration)
  // runs alongside the export-specific encoder detection.
  const encodersLoaded = Promise.all([
    call<{ encoders: string[] }>("detect_gpu_encoders"),
    call<Record<string, EncoderMeta>>("get_encoder_metadata"),
  ])
  await ensureLoaded()
  const [encodersRes, metaRes] = await encodersLoaded
  if (encodersRes.success && encodersRes.data) {
    gpuEncoders.value = encodersRes.data.encoders
  }
  if (metaRes.success && metaRes.data) {
    encoderMeta.value = metaRes.data
  }
})
</script>

<template>
  <div class="space-y-6">
    <!-- ASR Settings Section -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">ASR Settings</h3>
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Default engine</label>
          <select
            :value="asrPluginId || asrEngine"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="handleEnginePluginChange(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="p in installedAsrEngines" :key="p.pluginId" :value="p.pluginId">
              {{ p.displayName }}
            </option>
            <option v-if="installedAsrEngines.length === 0" value="faster-whisper">Faster Whisper</option>
            <option v-if="installedAsrEngines.length === 0" value="qwen3-asr">Qwen3 ASR</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Model</label>
          <select
            :value="currentSettings.model_size"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="changeModelSize(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="m in availableModels" :key="m.model_id" :value="m.model_id">
              {{ m.display_name }}
            </option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Language</label>
          <select
            :value="currentSettings.language"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="changeLanguage(($event.target as HTMLSelectElement).value)"
          >
            <option value="zh">Chinese</option>
            <option value="en">English</option>
            <option value="ja">Japanese</option>
            <option value="ko">Korean</option>
            <option value="auto">Auto-detect</option>
          </select>
        </div>
        <div v-if="!isMlx" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Device</label>
          <select
            :value="currentSettings.device"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="changeDevice(($event.target as HTMLSelectElement).value as 'cpu' | 'cuda' | 'auto' | 'mps')"
          >
            <option v-if="!isDarwin" value="cpu">CPU</option>
            <option v-if="supportsGpu" value="cuda">CUDA (GPU)</option>
            <option v-if="asrEngine === 'faster-whisper'" value="auto">Auto</option>
            <option v-if="isDarwin && asrEngine === 'qwen3-asr'" value="mps">MPS</option>
          </select>
          <span v-if="isDarwin && asrEngine === 'faster-whisper'" class="text-xs text-gray-400 ml-2">MPS (Metal Performance Shaders)</span>
          <span v-else-if="isDarwin && asrEngine === 'qwen3-asr'" class="text-xs text-gray-400 ml-2">Metal Performance Shaders (Apple GPU)</span>
          <span v-else-if="!supportsGpu" class="text-xs text-gray-400 ml-2">GPU not available for this plugin</span>
        </div>
        <div v-else class="text-xs text-gray-400">Apple Silicon (Metal)</div>
        <div v-if="!isMlx" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Compute type</label>
          <select
            :value="currentSettings.compute_type"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="changeComputeType(($event.target as HTMLSelectElement).value)"
          >
            <template v-if="asrEngine === 'faster-whisper'">
              <option value="int8">INT8 (fastest)</option>
              <option v-if="!isDarwin" value="int8_float16">INT8 FP16 (balanced)</option>
              <option v-if="!isDarwin" value="float16">FP16</option>
              <option value="float32">FP32 (highest quality)</option>
            </template>
            <template v-else>
              <option v-if="!isDarwin" value="bfloat16">BF16 (recommended)</option>
              <option value="float16">FP16</option>
              <option value="float32">FP32</option>
            </template>
          </select>
        </div>
        <div v-if="asrEngine === 'faster-whisper'" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">VAD filter</label>
          <div class="flex items-center gap-2">
            <input
              type="checkbox"
              :checked="currentSettings.vad_filter"
              class="w-4 h-4 mt-0.5 accent-blue-600"
              @change="changeVadFilter(($event.target as HTMLInputElement).checked)"
            />
            <span class="text-xs text-gray-500">Reduce hallucinations in noisy audio</span>
          </div>
        </div>
        <!-- VAD sliders (visible when vad_filter is on and engine is faster-whisper) -->
        <template v-if="asrEngine === 'faster-whisper' && currentSettings.vad_filter">
          <label class="block mb-2">
            <span class="text-xs text-gray-500">
              VAD Threshold: {{ currentSettings.vad_threshold.toFixed(2) }}
            </span>
            <input
              type="range"
              :value="currentSettings.vad_threshold"
              min="0"
              max="1"
              step="0.05"
              class="w-full mt-1"
              @input="changeVadThreshold(parseFloat(($event.target as HTMLInputElement).value))"
            />
          </label>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">
              Min Silence (ms): {{ currentSettings.vad_min_silence_ms }}
            </span>
            <input
              type="range"
              :value="currentSettings.vad_min_silence_ms"
              min="100"
              max="2000"
              step="50"
              class="w-full mt-1"
              @input="changeVadMinSilenceMs(parseInt(($event.target as HTMLInputElement).value))"
            />
          </label>
        </template>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Duplicate threshold</label>
          <input
            type="number"
            :value="props.settings.duplicate_threshold"
            step="0.05"
            min="0.5"
            max="1.0"
            class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
            @input="updateField('duplicate_threshold', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>
    </section>

    <!-- Export Settings Section -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Export</h3>
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Video codec</label>
          <select
            :value="props.settings.export_video_codec"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('export_video_codec', ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="codec in availableVideoCodecs" :key="codec.value" :value="codec.value">
              {{ codec.label }}
            </option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Audio codec</label>
          <select
            :value="props.settings.export_audio_codec"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('export_audio_codec', ($event.target as HTMLSelectElement).value)"
          >
            <option value="aac">AAC</option>
            <option value="libmp3lame">MP3</option>
            <option value="libopus">Opus</option>
            <option value="flac">FLAC</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Audio bitrate</label>
          <input
            type="text"
            :value="props.settings.export_audio_bitrate"
            class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
            @input="updateField('export_audio_bitrate', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Preset</label>
          <select
            :value="props.settings.export_preset"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('export_preset', ($event.target as HTMLSelectElement).value)"
          >
            <option value="ultrafast">ultrafast</option>
            <option value="superfast">superfast</option>
            <option value="veryfast">veryfast</option>
            <option value="faster">faster</option>
            <option value="fast">fast</option>
            <option value="medium">medium</option>
            <option value="slow">slow</option>
            <option value="slower">slower</option>
            <option value="veryslow">veryslow</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">CRF</label>
          <input
            type="number"
            :value="props.settings.export_crf"
            min="0"
            max="51"
            class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
            @input="updateField('export_crf', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Resolution</label>
          <select
            :value="props.settings.export_resolution"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('export_resolution', ($event.target as HTMLSelectElement).value)"
          >
            <option value="original">Original</option>
            <option value="1920x1080">1080p</option>
            <option value="1280x720">720p</option>
            <option value="854x480">480p</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">FFmpeg transitions</label>
          <input
            type="checkbox"
            :checked="props.settings.export_ffmpeg_transitions"
            class="checkbox checkbox-sm"
            @change="updateField('export_ffmpeg_transitions', ($event.target as HTMLInputElement).checked)"
          />
        </div>
        <div v-if="props.settings.export_ffmpeg_transitions" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Fade duration (s)</label>
          <input
            type="number"
            :value="props.settings.export_ffmpeg_fade_duration"
            step="0.1"
            min="0"
            class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
            @input="updateField('export_ffmpeg_fade_duration', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div v-if="props.settings.export_ffmpeg_transitions" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Fade mode</label>
          <select
            :value="props.settings.export_ffmpeg_fade_mode"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('export_ffmpeg_fade_mode', ($event.target as HTMLSelectElement).value)"
          >
            <option value="crossfade">Crossfade</option>
            <option value="fade_black">Fade through black</option>
          </select>
        </div>
      </div>
    </section>
  </div>
</template>

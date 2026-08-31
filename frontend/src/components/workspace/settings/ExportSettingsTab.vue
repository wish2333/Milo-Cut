<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import type { ModelInfo, PluginInfo } from "@/types/project"
import { usePluginManager } from "@/composables/usePluginManager"

/**
 * Export & ASR defaults settings tab (v3.0.0 M8-1, extracted from
 * SettingsModal.vue).
 *
 * Owns: ASR defaults (engine/model/language/device/compute/VAD), export
 * codec/bitrate/preset/CRF/resolution/transitions, and the hardware encoder
 * detection feeding the codec list. Plugin manager state is instance-local.
 * Settings mutations are emitted as patches.
 */
const props = defineProps<{
  settings: AppSettings
}>()

const emit = defineEmits<{
  update: [patch: Partial<AppSettings>]
}>()

const pluginManager = usePluginManager()
const pluginList = ref<PluginInfo[]>([])
const modelList = ref<ModelInfo[]>([])

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

// ASR models filtered by current engine, excluding ForcedAligner, deduplicated
const asrModels = computed(() => {
  const engine = props.settings.asr_engine
  const seen = new Set<string>()
  return modelList.value.filter(m => {
    if (m.engine !== engine || m.model_id.includes("ForcedAligner") || seen.has(m.model_id)) return false
    seen.add(m.model_id)
    return true
  })
})

// Installed ASR engine plugins (CPU + GPU variants), deduplicated by plugin_id
const installedAsrPlugins = computed(() => {
  const seen = new Set<string>()
  return pluginList.value.filter(p => {
    if (p.status !== "installed") return false
    if ((p.engine !== "faster-whisper" && p.engine !== "qwen3-asr") || seen.has(p.plugin_id)) return false
    seen.add(p.plugin_id)
    return true
  })
})

// Whether the currently selected ASR plugin supports GPU — macOS has no NVIDIA CUDA
const isDarwin = navigator.platform.toLowerCase().includes('mac')
const isMlxPlugin = computed(() => (props.settings.asr_plugin_id ?? '').includes('-mlx'))
const asrSupportsGpu = computed(() => {
  if (isDarwin || isMlxPlugin.value) return false
  const pid = props.settings.asr_plugin_id ?? ''
  return pid.length > 0 && !pid.includes('-cpu')
})

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  emit("update", { [key]: value } as Partial<AppSettings>)
}

onMounted(async () => {
  const [pluginsRes, encodersRes, metaRes] = await Promise.all([
    pluginManager.listPlugins(),
    call<{ encoders: string[] }>("detect_gpu_encoders"),
    call<Record<string, EncoderMeta>>("get_encoder_metadata"),
  ])
  pluginList.value = pluginsRes
  modelList.value = await pluginManager.listModels()
  if (encodersRes.success && encodersRes.data) {
    gpuEncoders.value = encodersRes.data.encoders
  }
  if (metaRes.success && metaRes.data) {
    encoderMeta.value = metaRes.data
  }
})

// Handle engine plugin change: derive engine type, reset device/compute defaults
function handleEnginePluginChange(pluginId: string) {
  const plugin = installedAsrPlugins.value.find(p => p.plugin_id === pluginId)
  if (!plugin) return
  const gpu = !isDarwin && !pluginId.includes('-cpu')
  const engine = plugin.engine
  const defaults: Partial<AppSettings> = {
    asr_plugin_id: pluginId,
    asr_engine: engine,
    asr_device: gpu ? 'cuda' : (isDarwin && engine === 'faster-whisper') ? 'auto' : (isDarwin && engine === 'qwen3-asr') ? 'mps' : 'cpu',
    asr_language: engine === 'qwen3-asr' ? 'auto' : 'zh',
  }
  if (engine === 'qwen3-asr') {
    defaults.qwen_compute_type = gpu ? 'bfloat16' : 'float32'
  } else {
    defaults.whisper_compute_type = gpu ? 'int8_float16' : 'int8'
  }
  emit("update", defaults)
}
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
            :value="props.settings.asr_plugin_id || props.settings.asr_engine"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="handleEnginePluginChange(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="p in installedAsrPlugins" :key="p.plugin_id" :value="p.plugin_id">
              {{ p.display_name }}
            </option>
            <option v-if="installedAsrPlugins.length === 0" value="faster-whisper">Faster Whisper</option>
            <option v-if="installedAsrPlugins.length === 0" value="qwen3-asr">Qwen3 ASR</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Model</label>
          <select
            :value="props.settings.asr_model_size"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('asr_model_size', ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="m in asrModels" :key="m.model_id" :value="m.model_id">
              {{ m.display_name }}
            </option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Language</label>
          <select
            :value="props.settings.asr_language"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('asr_language', ($event.target as HTMLSelectElement).value)"
          >
            <option value="zh">Chinese</option>
            <option value="en">English</option>
            <option value="ja">Japanese</option>
            <option value="ko">Korean</option>
            <option value="auto">Auto-detect</option>
          </select>
        </div>
        <div v-if="!isMlxPlugin" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Device</label>
          <select
            :value="props.settings.asr_device"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('asr_device', ($event.target as HTMLSelectElement).value as 'cpu' | 'cuda' | 'auto' | 'mps')"
          >
            <option v-if="!isDarwin" value="cpu">CPU</option>
            <option v-if="asrSupportsGpu" value="cuda">CUDA (GPU)</option>
            <option v-if="props.settings.asr_engine === 'faster-whisper'" value="auto">Auto</option>
            <option v-if="isDarwin && props.settings.asr_engine === 'qwen3-asr'" value="mps">MPS</option>
          </select>
          <span v-if="isDarwin && props.settings.asr_engine === 'faster-whisper'" class="text-xs text-gray-400 ml-2">MPS (Metal Performance Shaders)</span>
          <span v-else-if="isDarwin && props.settings.asr_engine === 'qwen3-asr'" class="text-xs text-gray-400 ml-2">Metal Performance Shaders (Apple GPU)</span>
          <span v-else-if="!asrSupportsGpu" class="text-xs text-gray-400 ml-2">GPU not available for this plugin</span>
        </div>
        <div v-else class="text-xs text-gray-400">Apple Silicon (Metal)</div>
        <div v-if="!isMlxPlugin" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Compute type</label>
          <select
            :value="props.settings.asr_engine === 'faster-whisper' ? props.settings.whisper_compute_type : props.settings.qwen_compute_type"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField(props.settings.asr_engine === 'faster-whisper' ? 'whisper_compute_type' : 'qwen_compute_type', ($event.target as HTMLSelectElement).value as 'int8' | 'int8_float16' | 'float16' | 'float32' | 'bfloat16')"
          >
            <template v-if="props.settings.asr_engine === 'faster-whisper'">
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
        <div v-if="props.settings.asr_engine === 'faster-whisper'" class="flex items-center justify-between">
          <label class="text-sm text-gray-600">VAD filter</label>
          <div class="flex items-center gap-2">
            <input
              type="checkbox"
              :checked="props.settings.asr_vad_filter"
              class="w-4 h-4 mt-0.5 accent-blue-600"
              @change="updateField('asr_vad_filter', ($event.target as HTMLInputElement).checked)"
            />
            <span class="text-xs text-gray-500">Reduce hallucinations in noisy audio</span>
          </div>
        </div>
        <!-- VAD sliders (visible when vad_filter is on and engine is faster-whisper) -->
        <template v-if="props.settings.asr_engine === 'faster-whisper' && props.settings.asr_vad_filter">
          <label class="block mb-2">
            <span class="text-xs text-gray-500">
              VAD Threshold: {{ (props.settings.whisper_vad_threshold ?? 0.5).toFixed(2) }}
            </span>
            <input
              type="range"
              :value="props.settings.whisper_vad_threshold ?? 0.5"
              min="0"
              max="1"
              step="0.05"
              class="w-full mt-1"
              @input="updateField('whisper_vad_threshold', parseFloat(($event.target as HTMLInputElement).value))"
            />
          </label>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">
              Min Silence (ms): {{ props.settings.whisper_vad_min_silence_ms ?? 500 }}
            </span>
            <input
              type="range"
              :value="props.settings.whisper_vad_min_silence_ms ?? 500"
              min="100"
              max="2000"
              step="50"
              class="w-full mt-1"
              @input="updateField('whisper_vad_min_silence_ms', parseInt(($event.target as HTMLInputElement).value))"
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

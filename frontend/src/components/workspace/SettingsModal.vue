<script setup lang="ts">
import { ref, onMounted } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const settings = ref<AppSettings | null>(null)
const ffmpegInfo = ref<{ ffmpeg_path: string; ffprobe_path: string; version: string }>({ ffmpeg_path: "", ffprobe_path: "", version: "" })
const gpuEncoders = ref<string[]>([])
const saving = ref(false)
const statusMsg = ref("")

onMounted(async () => {
  const [settingsRes, ffmpegRes, gpuRes] = await Promise.all([
    call<AppSettings>("get_settings"),
    call<{ ffmpeg_path: string; ffprobe_path: string; version: string }>("get_ffmpeg_info"),
    call<{ encoders: string[] }>("detect_gpu"),
  ])
  if (settingsRes.success && settingsRes.data) {
    settings.value = settingsRes.data
  }
  if (ffmpegRes.success && ffmpegRes.data) {
    ffmpegInfo.value = ffmpegRes.data
  }
  if (gpuRes.success && gpuRes.data) {
    gpuEncoders.value = gpuRes.data.encoders
  }
})

async function handleSave() {
  if (!settings.value) return
  saving.value = true
  statusMsg.value = ""
  const res = await call<AppSettings>("update_settings", settings.value)
  saving.value = false
  if (res.success) {
    statusMsg.value = "Settings saved"
    setTimeout(() => { statusMsg.value = "" }, 2000)
  } else {
    statusMsg.value = "Save failed"
  }
}

async function handleBrowseFfmpeg() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0 && settings.value) {
    settings.value = { ...settings.value, ffmpeg_path: res.data[0] }
  }
}

async function handleBrowseFfprobe() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0 && settings.value) {
    settings.value = { ...settings.value, ffprobe_path: res.data[0] }
  }
}

async function handleDownloadFfmpeg() {
  statusMsg.value = "Downloading FFmpeg..."
  const res = await call<{ path: string }>("download_ffmpeg")
  if (res.success && res.data && settings.value) {
    settings.value = { ...settings.value, ffmpeg_path: res.data.path }
    ffmpegInfo.value.ffmpeg_path = res.data.path
    statusMsg.value = "FFmpeg downloaded"
  } else {
    statusMsg.value = res.error ?? "Download failed"
  }
}

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  if (settings.value) {
    settings.value = { ...settings.value, [key]: value }
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('close')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-[640px] max-w-[90vw] max-h-[85vh] overflow-hidden flex flex-col">
      <div class="px-6 pt-6 pb-4 border-b border-gray-100">
        <h2 class="text-lg font-semibold text-gray-800">Settings</h2>
      </div>

      <div class="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        <!-- FFmpeg Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">FFmpeg</h3>
          <div class="space-y-2 text-sm">
            <div class="flex items-center justify-between">
              <span class="text-gray-500">Version</span>
              <span class="text-gray-800">{{ ffmpegInfo.version || "Not found" }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-500">FFmpeg path</span>
              <span class="text-gray-800 truncate max-w-[300px]">{{ ffmpegInfo.ffmpeg_path || "Not found" }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-500">FFprobe path</span>
              <span class="text-gray-800 truncate max-w-[300px]">{{ ffmpegInfo.ffprobe_path || "Not found" }}</span>
            </div>
          </div>

          <div class="mt-3 space-y-2">
            <div class="flex gap-2">
              <input
                v-if="settings"
                type="text"
                :value="settings.ffmpeg_path"
                placeholder="Custom FFmpeg path (leave empty for auto)"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                @input="updateField('ffmpeg_path', ($event.target as HTMLInputElement).value)"
              />
              <button
                class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                @click="handleBrowseFfmpeg"
              >
                Browse
              </button>
            </div>
            <div class="flex gap-2">
              <input
                v-if="settings"
                type="text"
                :value="settings.ffprobe_path"
                placeholder="Custom FFprobe path (leave empty for auto)"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                @input="updateField('ffprobe_path', ($event.target as HTMLInputElement).value)"
              />
              <button
                class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                @click="handleBrowseFfprobe"
              >
                Browse
              </button>
            </div>
            <button
              class="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              @click="handleDownloadFfmpeg"
            >
              Download FFmpeg
            </button>
          </div>
        </section>

        <!-- GPU / Encoders Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Hardware Encoders</h3>
          <div v-if="gpuEncoders.length > 0" class="flex flex-wrap gap-1.5">
            <span
              v-for="enc in gpuEncoders"
              :key="enc"
              class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800"
            >
              {{ enc }}
            </span>
          </div>
          <p v-else class="text-sm text-gray-500">No encoders detected</p>
        </section>

        <!-- Silence Detection Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Silence Detection</h3>
          <div v-if="settings" class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Threshold (dB)</label>
              <input
                type="number"
                :value="settings.silence_threshold_db"
                step="1"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_threshold_db', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Min duration (s)</label>
              <input
                type="number"
                :value="settings.silence_min_duration"
                step="0.1"
                min="0.1"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_min_duration', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Margin (s)</label>
              <input
                type="number"
                :value="settings.silence_margin"
                step="0.01"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_margin', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Subtitle padding (s)</label>
              <input
                type="number"
                :value="settings.silence_subtitle_padding"
                step="0.01"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_subtitle_padding', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Trim subtitles on overlap</label>
              <input
                type="checkbox"
                :checked="settings.trim_subtitles_on_silence_overlap"
                class="checkbox checkbox-sm"
                @change="updateField('trim_subtitles_on_silence_overlap', ($event.target as HTMLInputElement).checked)"
              />
            </div>
          </div>
        </section>

        <!-- Export Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Export</h3>
          <div v-if="settings" class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Video codec</label>
              <select
                :value="settings.export_video_codec"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_video_codec', ($event.target as HTMLSelectElement).value)"
              >
                <option value="libx264">libx264 (CPU)</option>
                <option value="libx265">libx265 (CPU)</option>
                <option value="libsvtav1">libsvtav1 (CPU)</option>
                <option value="h264_nvenc">h264_nvenc (NVIDIA)</option>
                <option value="hevc_nvenc">hevc_nvenc (NVIDIA)</option>
                <option value="av1_nvenc">av1_nvenc (NVIDIA)</option>
                <option value="h264_qsv">h264_qsv (Intel)</option>
                <option value="hevc_qsv">hevc_qsv (Intel)</option>
                <option value="h264_amf">h264_amf (AMD)</option>
                <option value="hevc_amf">hevc_amf (AMD)</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Audio codec</label>
              <select
                :value="settings.export_audio_codec"
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
                :value="settings.export_audio_bitrate"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_audio_bitrate', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Preset</label>
              <select
                :value="settings.export_preset"
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
                :value="settings.export_crf"
                min="0"
                max="51"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_crf', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Resolution</label>
              <select
                :value="settings.export_resolution"
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
                :checked="settings.export_ffmpeg_transitions"
                class="checkbox checkbox-sm"
                @change="updateField('export_ffmpeg_transitions', ($event.target as HTMLInputElement).checked)"
              />
            </div>
            <div v-if="settings.export_ffmpeg_transitions" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Fade duration (s)</label>
              <input
                type="number"
                :value="settings.export_ffmpeg_fade_duration"
                step="0.1"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_ffmpeg_fade_duration', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div v-if="settings.export_ffmpeg_transitions" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Fade mode</label>
              <select
                :value="settings.export_ffmpeg_fade_mode"
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

      <div class="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
        <span class="text-sm text-gray-500">{{ statusMsg }}</span>
        <div class="flex gap-2">
          <button
            class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
            @click="emit('close')"
          >
            Close
          </button>
          <button
            class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? "Saving..." : "Save" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

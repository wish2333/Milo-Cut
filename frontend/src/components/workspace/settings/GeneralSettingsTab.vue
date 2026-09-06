<script setup lang="ts">
import { onMounted, ref } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"

/**
 * General settings tab (v3.0.0 M8-1, extracted from SettingsModal.vue).
 *
 * Owns: FFmpeg paths/info, hardware encoder badges, silence detection
 * thresholds, proxy video options, data directory + cleanup actions.
 * Settings mutations are emitted as patches; status messages bubble to
 * the modal footer via `status(message, timeout)`.
 */
const props = defineProps<{
  settings: AppSettings
}>()

const emit = defineEmits<{
  update: [patch: Partial<AppSettings>]
  status: [message: string, timeout: number]
}>()

const ffmpegInfo = ref<{ ffmpeg_path: string; ffprobe_path: string; version: string }>({ ffmpeg_path: "", ffprobe_path: "", version: "" })
const gpuEncoders = ref<string[]>([])
const pluginDataDir = ref("")
const cleaningUp = ref(false)

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  emit("update", { [key]: value } as Partial<AppSettings>)
}

onMounted(async () => {
  const [ffmpegRes, encodersRes, dataDirRes] = await Promise.all([
    call<{ ffmpeg_path: string; ffprobe_path: string; version: string }>("get_ffmpeg_info"),
    call<{ encoders: string[] }>("detect_gpu_encoders"),
    call<{ path: string }>("get_plugin_data_dir"),
  ])
  if (ffmpegRes.success && ffmpegRes.data) {
    ffmpegInfo.value = ffmpegRes.data
  }
  if (encodersRes.success && encodersRes.data) {
    gpuEncoders.value = encodersRes.data.encoders
  }
  if (dataDirRes.success && dataDirRes.data) {
    pluginDataDir.value = dataDirRes.data.path
  }
})

async function handleBrowseFfmpeg() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0) {
    emit("update", { ffmpeg_path: res.data[0] })
  }
}

async function handleBrowseFfprobe() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0) {
    emit("update", { ffprobe_path: res.data[0] })
  }
}

async function handleDownloadFfmpeg() {
  emit("status", "Downloading FFmpeg...", 0)
  const res = await call<{ path: string }>("download_ffmpeg")
  if (res.success && res.data) {
    emit("update", { ffmpeg_path: res.data.path })
    ffmpegInfo.value.ffmpeg_path = res.data.path
    emit("status", "FFmpeg downloaded", 0)
  } else {
    emit("status", res.error ?? "Download failed", 0)
  }
}

async function handleOpenDataDirectory() {
  const res = await call("open_data_directory")
  if (!res.success) {
    emit("status", res.error || "Failed to open directory", 3000)
  }
}

async function handleCleanupTasks() {
  if (cleaningUp.value) return
  if (!window.confirm('Are you sure you want to clean up task files? This will delete all log and result files.')) return
  cleaningUp.value = true
  emit("status", "Cleaning up task files...", 0)
  try {
    const res = await call<{ deleted: number; size_freed: number }>("cleanup_tasks_folder")
    if (res.success && res.data) {
      const sizeMB = (res.data.size_freed / 1024 / 1024).toFixed(1)
      emit("status", `Cleaned up ${res.data.deleted} task files (${sizeMB} MB freed)`, 5000)
    } else {
      emit("status", res.error || "Cleanup failed", 5000)
    }
  } finally {
    cleaningUp.value = false
  }
}

async function handleCleanupTranscripts() {
  if (cleaningUp.value) return
  if (!window.confirm('Are you sure you want to clean up silence detection data?')) return
  cleaningUp.value = true
  emit("status", "Cleaning up transcript files...", 0)
  try {
    const res = await call<{ deleted: number; size_freed: number }>("cleanup_transcripts_folder")
    if (res.success && res.data) {
      const sizeMB = (res.data.size_freed / 1024 / 1024).toFixed(1)
      emit("status", `Cleaned up ${res.data.deleted} transcript files (${sizeMB} MB freed)`, 5000)
    } else {
      emit("status", res.error || "Cleanup failed", 5000)
    }
  } finally {
    cleaningUp.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
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
            type="text"
            :value="props.settings.ffmpeg_path"
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
            type="text"
            :value="props.settings.ffprobe_path"
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
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Threshold (dB)</label>
          <input
            type="number"
            :value="props.settings.silence_threshold_db"
            step="1"
            class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
            @input="updateField('silence_threshold_db', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Min duration (s)</label>
          <input
            type="number"
            :value="props.settings.silence_min_duration"
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
            :value="props.settings.silence_margin"
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
            :value="props.settings.silence_subtitle_padding"
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
            :checked="props.settings.trim_subtitles_on_silence_overlap"
            class="checkbox checkbox-sm"
            @change="updateField('trim_subtitles_on_silence_overlap', ($event.target as HTMLInputElement).checked)"
          />
        </div>
        <!-- v3.0.1 M6-2: secondary subtitle overlay (extension tracks) -->
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">播放时显示副轨字幕</label>
          <input
            type="checkbox"
            :checked="props.settings.show_secondary_subtitle"
            class="checkbox checkbox-sm"
            data-test="show-secondary-toggle"
            @change="updateField('show_secondary_subtitle', ($event.target as HTMLInputElement).checked)"
          />
        </div>
      </div>
    </section>

    <!-- Proxy Video Section -->
    <section>
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Proxy Video</h3>
      <p class="text-xs text-gray-400 mb-3">Proxy videos are lower-resolution copies used for faster preview playback.</p>
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Proxy resolution</label>
          <select
            :value="props.settings.proxy_resolution"
            class="px-2 py-1 text-sm border border-gray-300 rounded"
            @change="updateField('proxy_resolution', ($event.target as HTMLSelectElement).value)"
          >
            <option value="854x480">480p</option>
            <option value="1280x720">720p</option>
            <option value="1920x1080">1080p</option>
          </select>
        </div>
        <div class="flex items-center justify-between">
          <label class="text-sm text-gray-600">Auto-generate proxy on import</label>
          <input
            type="checkbox"
            :checked="props.settings.auto_generate_proxy"
            @change="updateField('auto_generate_proxy', ($event.target as HTMLInputElement).checked)"
          />
        </div>
      </div>
    </section>

    <!-- Data Directory & Cleanup -->
    <section class="pt-3 border-t border-gray-200">
      <div class="mt-4 pt-3 border-t border-gray-200">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-600">Data directory</p>
            <p class="text-xs text-gray-400 mt-0.5 max-w-[350px] truncate">{{ pluginDataDir || 'Loading...' }}</p>
          </div>
          <button
            class="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors"
            @click="handleOpenDataDirectory"
          >
            Open folder
          </button>
        </div>
        <div class="flex gap-2 mt-3">
          <button
            class="px-3 py-1.5 text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded-lg transition-colors disabled:opacity-50"
            :disabled="cleaningUp"
            @click="handleCleanupTasks"
          >
            {{ cleaningUp ? 'Cleaning...' : 'Cleanup task files' }}
          </button>
          <button
            class="px-3 py-1.5 text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded-lg transition-colors disabled:opacity-50"
            :disabled="cleaningUp"
            @click="handleCleanupTranscripts"
          >
            {{ cleaningUp ? 'Cleaning...' : 'Cleanup transcripts' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

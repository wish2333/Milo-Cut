<script setup lang="ts">
import { computed, ref } from "vue"
import type { Project } from "@/types/project"
import EncodingSettings from "@/components/export/EncodingSettings.vue"
import PreviewPlayer from "@/components/export/PreviewPlayer.vue"
import { call } from "@/bridge"
import { useExport } from "@/composables/useExport"
import { useToast } from "@/composables/useToast"

const { showToast } = useToast()

const props = defineProps<{
  project: Project
}>()

const emit = defineEmits<{
  "go-back": []
  "project-updated": [project: Project]
}>()

const {
  isExporting,
  exportProgress,
  confirmedEdits,
  estimatedSaving,
  exportVideo,
  exportSrt,
  exportAudio,
} = useExport(computed(() => props.project))

const encodingSettings = ref({
  outputFormat: "mp4",
  quality: 23,
  resolution: "original",
  videoCodec: "libx264",
  audioCodec: "aac",
  audioBitrate: "192k",
  preset: "medium",
})

const statusMessage = ref("")
const errorMessage = ref("")
const otioFadeDuration = ref(0)
const otioExportMode = ref<"clean" | "full_timeline">("clean")
const otioFadeMode = ref<"crossfade" | "separate">("crossfade")

const subtitleCount = computed(() =>
  props.project.transcript?.segments?.filter(s => s.type === "subtitle").length ?? 0
)

function handleEncodingSettingsUpdate(settings: typeof encodingSettings.value) {
  encodingSettings.value = settings
}

async function handleExportVideo() {
  errorMessage.value = ""
  statusMessage.value = "正在导出视频..."
  await call("update_settings", {
    export_video_codec: encodingSettings.value.videoCodec,
    export_audio_codec: encodingSettings.value.audioCodec,
    export_audio_bitrate: encodingSettings.value.audioBitrate,
    export_preset: encodingSettings.value.preset,
    export_crf: encodingSettings.value.quality,
    export_resolution: encodingSettings.value.resolution,
    export_ffmpeg_fade_duration: otioFadeDuration.value,
    export_ffmpeg_fade_mode: otioFadeMode.value,
  })
  const ok = await exportVideo()
  statusMessage.value = ""
  if (!ok) {
    showToast("视频导出失败", "error")
  } else {
    showToast("视频导出完成", "success")
  }
}

async function handleExportAudio() {
  errorMessage.value = ""
  statusMessage.value = "正在导出音频..."
  await call("update_settings", {
    export_ffmpeg_fade_duration: otioFadeDuration.value,
    export_ffmpeg_fade_mode: otioFadeMode.value,
  })
  const ok = await exportAudio()
  statusMessage.value = ""
  if (!ok) {
    showToast("音频导出失败", "error")
  } else {
    showToast("音频导出完成", "success")
  }
}

async function handleExportSrt() {
  errorMessage.value = ""
  statusMessage.value = "正在导出字幕..."
  const ok = await exportSrt()
  statusMessage.value = ""
  if (!ok) {
    showToast("字幕导出失败", "error")
  } else {
    showToast("字幕导出完成", "success")
  }
}

async function handleExportEdl() {
  statusMessage.value = "正在导出 EDL..."
  errorMessage.value = ""
  try {
    const mediaPath = props.project.media?.path
    if (!mediaPath) {
      showToast("无法获取源文件路径", "error")
      return
    }
    const outputPath = mediaPath.replace(/\.[^.]+$/, ".edl")
    const exportRes = await call<string>("export_edl", outputPath)
    if (exportRes.success) {
      showToast("EDL 导出完成", "success")
    } else {
      showToast(`EDL 导出失败: ${exportRes.error}`, "error")
    }
  } catch (e) {
    showToast(`EDL 导出失败: ${e}`, "error")
  } finally {
    statusMessage.value = ""
  }
}

async function handleExportXmemlPremiere() {
  statusMessage.value = "正在导出 Premiere XML..."
  errorMessage.value = ""
  try {
    const mediaPath = props.project.media?.path
    if (!mediaPath) {
      showToast("无法获取源文件路径", "error")
      return
    }
    const outputPath = mediaPath.replace(/\.[^.]+$/, ".xml")
    const exportRes = await call<string>("export_xmeml_premiere", outputPath, otioExportMode.value)
    if (exportRes.success) {
      showToast("Premiere XML 导出完成", "success")
    } else {
      showToast(`Premiere XML 导出失败: ${exportRes.error}`, "error")
    }
  } catch (e) {
    showToast(`Premiere XML 导出失败: ${e}`, "error")
  } finally {
    statusMessage.value = ""
  }
}

async function handleExportOtio() {
  statusMessage.value = "正在导出 OTIO..."
  errorMessage.value = ""
  try {
    const mediaPath = props.project.media?.path
    if (!mediaPath) {
      showToast("无法获取源文件路径", "error")
      return
    }
    const outputPath = mediaPath.replace(/\.[^.]+$/, ".otio")
    const exportRes = await call<string>("export_otio", outputPath, otioFadeDuration.value, otioExportMode.value, otioFadeMode.value)
    if (exportRes.success) {
      showToast("OTIO 导出完成", "success")
    } else {
      showToast(`OTIO 导出失败: ${exportRes.error}`, "error")
    }
  } catch (e) {
    showToast(`OTIO 导出失败: ${e}`, "error")
  } finally {
    statusMessage.value = ""
  }
}

function formatTimeShort(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50">
    <!-- Top navigation -->
    <div class="flex items-center gap-3 border-b bg-white px-4 py-3">
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-200 transition-colors"
        @click="emit('go-back')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
        返回编辑
      </button>
      <h1 class="text-lg font-semibold">导出</h1>
      <div class="flex-1" />
      <span v-if="statusMessage" class="text-sm text-blue-600">{{ statusMessage }}</span>
      <span v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</span>
      <span v-if="confirmedEdits.length > 0" class="text-sm text-gray-500">
        {{ confirmedEdits.length }} edits | -{{ formatTimeShort(estimatedSaving) }}
      </span>
    </div>

    <!-- Progress bar -->
    <div v-if="isExporting && exportProgress" class="border-b bg-white px-4 py-2">
      <div class="flex items-center gap-3">
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            class="h-full bg-blue-500 rounded-full transition-all duration-300"
            :style="{ width: `${exportProgress.percent ?? 0}%` }"
          />
        </div>
        <span class="text-xs text-gray-500 shrink-0">{{ exportProgress.message ?? '' }}</span>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Settings panel -->
      <div class="w-80 border-r bg-white overflow-y-auto p-4">
        <h3 class="font-medium mb-3">导出设置</h3>
        <EncodingSettings @update:settings="handleEncodingSettingsUpdate" />
      </div>

      <!-- Center: Preview area -->
      <div class="flex-1 overflow-hidden">
        <PreviewPlayer
          :media-path="props.project.media?.path ?? null"
          :proxy-path="props.project.media?.proxy_path ?? null"
          :edits="props.project.edits ?? []"
          :duration="props.project.media?.duration ?? 0"
        />
      </div>

      <!-- Right: Export actions -->
      <div class="w-64 border-l bg-white overflow-y-auto p-4">
        <h3 class="font-medium mb-3">导出选项</h3>

        <div class="space-y-3">
          <button
            class="w-full flex items-center gap-2 rounded-md bg-green-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-700 transition-colors"
            :disabled="isExporting || confirmedEdits.length === 0"
            @click="handleExportVideo"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
            导出视频
          </button>

          <button
            class="w-full flex items-center gap-2 rounded-md bg-green-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-green-700 transition-colors"
            :disabled="isExporting || confirmedEdits.length === 0"
            @click="handleExportAudio"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" /></svg>
            导出音频
          </button>

          <button
            class="w-full flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            :disabled="isExporting"
            @click="handleExportSrt"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
            导出 SRT
          </button>

          <!-- Transition settings (applies to OTIO + FFmpeg export) -->
          <div class="border-t border-gray-200 pt-3 mt-3">
            <h4 class="text-xs font-medium text-gray-500 mb-2">过渡设置</h4>
            <div :class="{ 'opacity-50 pointer-events-none': otioExportMode === 'full_timeline' }">
              <label class="block">
                <span class="text-xs text-gray-500">
                  过渡时长 (s): {{ otioFadeDuration.toFixed(2) }}
                </span>
                <input
                  type="range"
                  v-model.number="otioFadeDuration"
                  min="0" max="2.0" step="0.1"
                  class="w-full mt-1"
                />
                <p v-if="otioFadeDuration > 0" class="text-xs text-gray-400 mt-0.5">
                  时长 > 0 时 OTIO / FFmpeg 导出自动启用过渡
                </p>
              </label>
              <div
                v-if="otioFadeDuration > 0"
                class="mt-1.5 space-y-1"
              >
                <label class="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                  <input type="radio" v-model="otioFadeMode" value="crossfade" class="accent-indigo-600" />
                  Crossfade (audio dissolves with video)
                </label>
                <label class="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                  <input type="radio" v-model="otioFadeMode" value="separate" class="accent-indigo-600" />
                  Separate Fade In/Out (audio per-clip, no cross-mix)
                </label>
                <p v-if="otioFadeMode === 'separate'" class="text-xs text-amber-600">
                  OTIO export falls back to crossfade (per-clip not supported)
                </p>
              </div>
            </div>
          </div>

          <!-- Timeline formats -->
          <div class="border-t border-gray-200 pt-3 mt-3">
            <h4 class="text-xs font-medium text-gray-500 mb-2">时间线格式</h4>
            <button
              class="w-full flex items-center gap-2 rounded-md bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
              :disabled="isExporting"
              @click="handleExportOtio"
            >
              导出 OTIO (DaVinci / New PR / Others)
            </button>
            <button
              class="w-full flex items-center gap-2 rounded-md bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200 transition-colors mt-2"
              :disabled="isExporting"
              @click="handleExportXmemlPremiere"
            >
              导出 XML (FCP 7)
            </button>
            <button
              class="w-full flex items-center gap-2 rounded-md bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200 transition-colors mt-2"
              :disabled="isExporting"
              @click="handleExportEdl"
            >
              导出 EDL (DaVinci Only)
            </button>
            <div class="mt-2 space-y-1.5">
              <label class="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                <input type="radio" v-model="otioExportMode" value="clean" class="accent-indigo-600" />
                Clean Export
              </label>
              <label class="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                <input type="radio" v-model="otioExportMode" value="full_timeline" class="accent-indigo-600" />
                Full Timeline
              </label>
              <p v-if="otioExportMode === 'full_timeline'" class="text-xs text-amber-600">
                Full Timeline mode does not support transitions
              </p>
            </div>
          </div>
          </div>

        <!-- Project info -->
        <div class="mt-6 pt-4 border-t border-gray-200">
          <h4 class="text-xs font-medium text-gray-500 mb-2">项目信息</h4>
          <div class="space-y-1 text-xs text-gray-600">
            <p>字幕段: {{ subtitleCount }}</p>
            <p>待删除: {{ confirmedEdits.length }}</p>
            <p>预计节省: {{ formatTimeShort(estimatedSaving) }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

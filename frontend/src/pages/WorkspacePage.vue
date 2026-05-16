<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import type { Project, Segment, EditDecision } from "@/types/project"
import { formatTimeShort } from "@/utils/format"
import { call } from "@/bridge"
import { useAnalysis } from "@/composables/useAnalysis"
import { useExport } from "@/composables/useExport"
import { useEdit } from "@/composables/useEdit"
import { useSegmentEdit } from "@/composables/useSegmentEdit"
import { useToast } from "@/composables/useToast"
import ProgressBar from "@/components/common/ProgressBar.vue"
import Timeline from "@/components/workspace/Timeline.vue"
import WaveformEditor from "@/components/waveform/WaveformEditor.vue"
import SearchReplaceBar from "@/components/workspace/SearchReplaceBar.vue"
import VideoControls from "@/components/workspace/VideoControls.vue"

interface Props {
  project: Project
}

interface Emits {
  (e: "project-updated", project: Project): void
  (e: "project-closed"): void
  (e: "go-to-export"): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const projectRef = computed({
  get: () => props.project,
  set: (val) => emit("project-updated", val),
})

const {
  isDetecting,
  detectionProgress,
  runSilenceDetection,
  runFillerDetection,
  runErrorDetection,
  runFullAnalysis,
  confirmEdit,
  rejectEdit,
} = useAnalysis(projectRef)

const {
  isExporting,
  exportProgress,
  confirmedEdits,
  estimatedSaving,
} = useExport(projectRef)

const {
  searchReplace,
  confirmAllSuggestions,
  rejectAllSuggestions,
  generateSubtitleKeepRanges,
  deleteSegment,
  deleteSilenceSegments,
  deleteSubtitleTrimEdits,
} = useEdit(projectRef)

const {
  selectedSegmentId: editSelectedSegmentId,
  selectRange: selectEditRange,
  updateSegmentTime,
  updateSegmentText,
  toggleEditStatus,
} = useSegmentEdit(projectRef as any, (val: Project) => emit("project-updated", val))

const { showToast } = useToast()

const statusMessage = ref("")
const errorMessage = ref("")
let statusTimer: ReturnType<typeof setTimeout> | null = null
const showAnalysisDropdown = ref(false)
const showSilenceSettings = ref(false)
const videoUrl = ref("")
const waveformUrl = ref("")
const videoRef = ref<HTMLVideoElement | null>(null)
const currentTime = ref(0)
const videoPaused = ref(true)
const videoVolume = ref(0.75)
const videoPlaybackRate = ref(1)

const silenceThreshold = ref(-30)
const silenceMinDuration = ref(0.5)
const trimSubtitlesOnOverlap = ref(true)
const globalEditMode = ref(false)
const showConfirmDeleteSilence = ref(false)
const subtitleTrimPadding = ref(0.3)
const showSubtitleTrimSettings = ref(false)

watch(statusMessage, (msg) => {
  if (statusTimer) {
    clearTimeout(statusTimer)
    statusTimer = null
  }
  if (msg) {
    statusTimer = setTimeout(() => {
      statusMessage.value = ""
      statusTimer = null
    }, 5000)
  }
})

const segments = computed<Segment[]>(() => props.project.transcript?.segments ?? [])
const edits = computed<EditDecision[]>(() => props.project.edits ?? [])
const duration = computed(() => props.project.media?.duration ?? 0)
const analysisResults = computed(() => props.project.analysis?.results ?? [])

const mergedSegments = computed<Segment[]>(() => {
  return [...segments.value].sort((a, b) => a.start - b.start)
})

const silenceCount = computed(() => segments.value.filter(s => s.type === "silence").length)
const subtitleCount = computed(() => segments.value.filter(s => s.type === "subtitle").length)

async function loadVideoUrl() {
  const mediaPath = props.project.media?.path
  if (!mediaPath) return
  const res = await call<{ url: string; port: number }>("get_video_url", mediaPath)
  if (res.success && res.data) {
    videoUrl.value = res.data.url
  }
}

async function resolveWaveformUrl() {
  const res = await call<{ url: string }>("get_waveform_url")
  if (res.success && res.data) {
    waveformUrl.value = res.data.url
  }
}

onMounted(async () => {
  await loadVideoUrl()
  await resolveWaveformUrl()
  await loadSilenceSettings()
})

watch(() => props.project.media?.waveform_path, () => {
  resolveWaveformUrl()
})

watch(() => props.project.media?.path, loadVideoUrl)

async function loadSilenceSettings() {
  const res = await call<Record<string, unknown>>("get_settings")
  if (res.success && res.data) {
    silenceThreshold.value = Number(res.data.silence_threshold_db ?? -30)
    silenceMinDuration.value = Number(res.data.silence_min_duration ?? 0.5)
    trimSubtitlesOnOverlap.value = res.data.trim_subtitles_on_silence_overlap !== false
  }
}

async function saveSilenceSettings() {
  await call("update_settings", {
    silence_threshold_db: silenceThreshold.value,
    silence_min_duration: silenceMinDuration.value,
    trim_subtitles_on_silence_overlap: trimSubtitlesOnOverlap.value,
  })
  showSilenceSettings.value = false
}

function handleSeek(time: number) {
  if (videoRef.value) {
    videoRef.value.currentTime = time
    videoRef.value.play()
  }
}

function handleVideoLoaded() {
  if (videoRef.value) {
    videoRef.value.volume = 0.25
  }
}

function handleTimeUpdate() {
  if (videoRef.value) {
    currentTime.value = videoRef.value.currentTime
  }
}

function handleTogglePlay() {
  if (!videoRef.value) return
  if (videoRef.value.paused) {
    videoRef.value.play()
  } else {
    videoRef.value.pause()
  }
}

function handleSeekTo(time: number) {
  if (!videoRef.value) return
  videoRef.value.currentTime = time
}

function handleVolumeChange(vol: number) {
  if (!videoRef.value) return
  videoRef.value.volume = vol
  videoVolume.value = vol
}

function handleRateChange(rate: number) {
  if (!videoRef.value) return
  videoRef.value.playbackRate = rate
  videoPlaybackRate.value = rate
}

function handleFullscreen() {
  const container = videoRef.value?.parentElement
  if (!container) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    container.requestFullscreen()
  }
}

async function handleToggleEditStatus(segment: Segment, nextStatus?: string) {
  await toggleEditStatus(segment, nextStatus)
}

async function handleImportSrt() {
  errorMessage.value = ""
  statusMessage.value = "Selecting file..."
  const fileRes = await call<string>("select_file")
  if (!fileRes.success || !fileRes.data) {
    statusMessage.value = ""
    return
  }
  statusMessage.value = "Importing SRT..."
  const importRes = await call<Project>("import_srt", fileRes.data)
  if (importRes.success && importRes.data) {
    emit("project-updated", importRes.data)
    statusMessage.value = ""
  } else {
    errorMessage.value = importRes.error ?? "Failed to import SRT"
    statusMessage.value = ""
  }
}

async function handleDetectSilence() {
  errorMessage.value = ""
  await runSilenceDetection()
}

async function handleRunAnalysis(type: string) {
  showAnalysisDropdown.value = false
  errorMessage.value = ""
  switch (type) {
    case "filler": await runFillerDetection(); break
    case "error": await runErrorDetection(); break
    case "full": await runFullAnalysis(); break
  }
}

async function handleConfirmAllSuggestions() {
  errorMessage.value = ""
  await confirmAllSuggestions()
}

async function handleRejectAllSuggestions() {
  errorMessage.value = ""
  await rejectAllSuggestions()
}

async function handleSaveProject() {
  const res = await call("save_project")
  if (res.success) {
    showToast("Project saved", "success", 2000)
  } else {
    showToast("Save failed", "error", 3000)
  }
}

async function handleSubtitleTrim() {
  errorMessage.value = ""
  statusMessage.value = "Generating subtitle-based trim ranges..."
  const result = await generateSubtitleKeepRanges(subtitleTrimPadding.value)
  statusMessage.value = ""
  if (result) {
    showToast(`Generated ${result.new_edits} delete ranges from ${result.keep_ranges} subtitle groups`, "success", 5000)
  } else {
    showToast("Failed to generate subtitle trim ranges", "error", 5000)
  }
}

async function handleDeleteSubtitleTrimEdits() {
  const ok = await deleteSubtitleTrimEdits()
  if (ok) {
    showToast("All subtitle trim markers cleared", "success", 3000)
  } else {
    showToast("Failed to clear subtitle trim markers", "error", 3000)
  }
}

async function handleConfirmDeleteSilence() {
  showConfirmDeleteSilence.value = false
  const ok = await deleteSilenceSegments()
  if (ok) {
    showToast("All silence markers deleted", "success", 3000)
  } else {
    showToast("Failed to delete silence markers", "error", 3000)
  }
}

async function handleUpdateText(segmentId: string, text: string) {
  await updateSegmentText(segmentId, text)
}

async function handleUpdateTime(segmentId: string, field: "start" | "end", value: number) {
  await updateSegmentTime(segmentId, field, value)
}



async function handleSearchReplace(query: string, replacement: string, scope: string) {
  const result = await searchReplace(query, replacement, scope)
  if (result) {
    statusMessage.value = `Replaced ${result.count} occurrences`
  }
}

function handleSelectRange(start: number, end: number) {
  selectEditRange(start, end)
}

async function handleAddSegment(start: number, end: number) {
  const res = await call<Project>("add_segment", start, end, "", "subtitle")
  if (res.success && res.data) {
    emit("project-updated", res.data)
  } else {
    errorMessage.value = res.error ?? "Failed to add segment"
  }
}

async function handleDeleteSegment(segmentId: string) {
  errorMessage.value = ""
  const ok = await deleteSegment(segmentId)
  if (!ok) {
    errorMessage.value = "Failed to delete segment"
  }
}

function handleSeekSegment(seg: Segment) {
  editSelectedSegmentId.value = seg.id
  if (videoRef.value) {
    videoRef.value.currentTime = seg.start
  }
}


async function handleCloseProject() {
  await call("close_project")
  videoUrl.value = ""
  emit("project-closed")
}

function isTextInput(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === "INPUT" || tag === "TEXTAREA") return true
  if (el.isContentEditable) return true
  return false
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (isTextInput(e.target)) return

  if (e.key === " ") {
    e.preventDefault()
    handleTogglePlay()
    return
  }
  if (e.ctrlKey && e.key === "s") {
    e.preventDefault()
    handleSaveProject()
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleGlobalKeydown)
})

onUnmounted(() => {
  document.removeEventListener("keydown", handleGlobalKeydown)
})
</script>

<template>
  <div class="flex h-screen flex-col bg-white">
    <!-- Top nav -->
    <nav class="flex h-11 items-center justify-between border-b border-gray-200 bg-gray-900 px-4">
      <div class="flex items-center gap-3">
        <button
          class="rounded p-1 text-gray-400 hover:text-white transition-colors"
          title="Back to home"
          @click="handleCloseProject"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
        <span class="text-xs text-gray-400">
          {{ subtitleCount }} subtitles | {{ silenceCount }} silence | {{ formatTimeShort(duration) }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="confirmedEdits.length > 0" class="text-xs text-yellow-300">
          {{ confirmedEdits.length }} edits | -{{ formatTimeShort(estimatedSaving) }}
        </span>
        <button
          class="rounded px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
          title="Save project (Ctrl+S)"
          @click="handleSaveProject"
        >
          Save
        </button>
      </div>
    </nav>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting"
        @click="handleImportSrt"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        Import SRT
      </button>
      <div class="relative inline-flex items-center">
        <button
          class="inline-flex items-center gap-1.5 rounded-md rounded-r-none bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting"
          @click="handleDetectSilence"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" /><path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
          {{ isDetecting ? 'Detecting...' : 'Detect Silence' }}
        </button>
        <button
          class="inline-flex items-center rounded-md rounded-l-none bg-blue-600 px-1.5 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50 transition-colors border-l border-blue-400"
          :disabled="isDetecting || isExporting"
          title="Silence detection settings"
          @click="showSilenceSettings = !showSilenceSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <div
          v-if="showSilenceSettings"
          class="absolute top-full left-0 mt-1 w-64 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
        >
          <div class="text-xs font-medium text-gray-700 mb-2">Silence Detection Settings</div>
          <label class="block mb-2">
            <span class="text-xs text-gray-500">Threshold (dB): {{ silenceThreshold }}</span>
            <input
              type="range"
              v-model.number="silenceThreshold"
              min="-60"
              max="-10"
              step="1"
              class="w-full mt-1"
            />
          </label>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">Min Duration (s): {{ silenceMinDuration.toFixed(1) }}</span>
            <input
              type="range"
              v-model.number="silenceMinDuration"
              min="0.1"
              max="3.0"
              step="0.1"
              class="w-full mt-1"
            />
          </label>
          <label class="flex items-center gap-2 mb-3 cursor-pointer">
            <input
              type="checkbox"
              v-model="trimSubtitlesOnOverlap"
              class="rounded border-gray-300"
            />
            <span class="text-xs text-gray-500">Trim overlapping subtitles</span>
          </label>
          <button
            class="w-full rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-600"
            @click="saveSilenceSettings"
          >
            Save Settings
          </button>
        </div>
      </div>

      <!-- Delete all silence markers -->
      <button
        class="inline-flex items-center rounded-md bg-red-500 px-2 py-1.5 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting || silenceCount === 0"
        title="Delete all silence markers"
        @click="showConfirmDeleteSilence = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <!-- Separator: silence group | subtitle group -->
      <div class="h-6 w-px bg-gray-300"></div>

      <div class="relative inline-flex items-center">
        <button
          class="inline-flex items-center gap-1.5 rounded-md rounded-r-none bg-orange-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting"
          title="Auto-trim: delete gaps between subtitle segments"
          @click="handleSubtitleTrim"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L4.939 4.939m7.061 7.061l-2.879-2.879M12 12l2.879-2.879" /></svg>
          Subtitle Trim
        </button>
        <button
          class="inline-flex items-center rounded-md rounded-l-none bg-orange-600 px-1.5 py-1.5 text-xs text-white hover:bg-orange-700 disabled:opacity-50 transition-colors border-l border-orange-400"
          :disabled="isDetecting || isExporting"
          title="Subtitle trim settings"
          @click="showSubtitleTrimSettings = !showSubtitleTrimSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <div
          v-if="showSubtitleTrimSettings"
          class="absolute top-full left-0 mt-1 w-56 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
        >
          <div class="text-xs font-medium text-gray-700 mb-2">Subtitle Trim Settings</div>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">Padding (s): {{ subtitleTrimPadding.toFixed(2) }}</span>
            <input
              type="range"
              v-model.number="subtitleTrimPadding"
              min="0"
              max="2.0"
              step="0.05"
              class="w-full mt-1"
            />
          </label>
        </div>
      </div>

      <!-- Clear subtitle trim markers -->
      <button
        class="inline-flex items-center rounded-md bg-red-500 px-2 py-1.5 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting"
        title="Clear all subtitle trim markers"
        @click="handleDeleteSubtitleTrimEdits"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <!-- Analysis dropdown -->
      <div class="relative">
        <button
          class="inline-flex items-center gap-1.5 rounded-md bg-purple-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting"
          @click="showAnalysisDropdown = !showAnalysisDropdown"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
          {{ isDetecting ? 'Analyzing...' : 'Analysis' }}
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" /></svg>
        </button>
        <div
          v-if="showAnalysisDropdown"
          class="absolute top-full left-0 mt-1 w-48 rounded-md border border-gray-200 bg-white shadow-lg z-10"
        >
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
            @click="handleRunAnalysis('filler')"
          >
            Detect Filler Words
          </button>
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
            @click="handleRunAnalysis('error')"
          >
            Detect Error Triggers
          </button>
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
            @click="handleRunAnalysis('full')"
          >
            Full Analysis
          </button>
        </div>
      </div>

      <div class="flex-1" />

      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="emit('go-to-export')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
        导出...
      </button>

      <div v-if="isDetecting && detectionProgress" class="flex-1 max-w-xs">
        <ProgressBar :percent="detectionProgress.percent" :message="detectionProgress.message" />
      </div>
      <div v-else-if="isExporting && exportProgress" class="flex-1 max-w-xs">
        <ProgressBar :percent="exportProgress.percent" :message="exportProgress.message" />
      </div>
    </div>

    <!-- Search replace bar -->
    <SearchReplaceBar @search-replace="handleSearchReplace" />

    <!-- Status messages -->
    <div v-if="statusMessage" class="flex items-center border-b border-gray-200 bg-blue-50 px-4 py-1 text-xs text-blue-600">
      <span class="flex-1">{{ statusMessage }}</span>
      <button
        class="ml-2 shrink-0 rounded p-0.5 hover:bg-blue-100 transition-colors"
        @click="statusMessage = ''"
      >
        <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="errorMessage" class="border-b border-gray-200 bg-red-50 px-4 py-1 text-xs text-red-600">
      {{ errorMessage }}
    </div>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Video player area -->
      <div class="flex w-2/5 min-w-[400px] flex-col border-r border-gray-200 bg-gray-900">
        <div class="flex flex-1 items-center justify-center p-2 overflow-hidden">
          <div v-if="videoUrl" class="flex flex-col w-full h-full items-center justify-center">
            <video
              ref="videoRef"
              :src="videoUrl"
              class="max-h-full max-w-full rounded"
              preload="metadata"
              @loadedmetadata="handleVideoLoaded"
              @timeupdate="handleTimeUpdate"
              @play="videoPaused = false"
              @pause="videoPaused = true"
              @click="handleTogglePlay"
            />
          </div>
          <div v-else class="text-center text-gray-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">Loading video...</p>
          </div>
        </div>
        <VideoControls
          :current-time="currentTime"
          :duration="duration"
          :paused="videoPaused"
          :volume="videoVolume"
          :playback-rate="videoPlaybackRate"
          @update:current-time="handleSeekTo"
          @update:volume="handleVolumeChange"
          @update:playback-rate="handleRateChange"
          @toggle-play="handleTogglePlay"
          @toggle-fullscreen="handleFullscreen"
        />
      </div>

      <!-- Right: Timeline (transcript editor + suggestion panel) -->
      <Timeline
        :segments="mergedSegments"
        :edits="edits"
        :analysis-results="analysisResults"
        :subtitle-count="subtitleCount"
        :silence-count="silenceCount"
        :selected-segment-id="editSelectedSegmentId"
        :global-edit-mode="globalEditMode"
        @seek="handleSeek"
        @update-text="handleUpdateText"
        @update-time="handleUpdateTime"
        @toggle-status="(seg) => handleToggleEditStatus(seg)"
        @confirm-segment="(seg) => handleToggleEditStatus(seg, 'confirmed')"
        @reject-segment="(seg) => handleToggleEditStatus(seg, 'rejected')"
        @delete-segment="(seg) => handleDeleteSegment(seg.id)"
        @confirm-suggestion="confirmEdit"
        @reject-suggestion="rejectEdit"
        @confirm-all="handleConfirmAllSuggestions"
        @reject-all="handleRejectAllSuggestions"
        @seek-suggestion="handleSeek"
        @toggle-edit-mode="globalEditMode = !globalEditMode"
      />
    </div>

    <!-- Bottom: Waveform editor -->
    <WaveformEditor
      :segments="mergedSegments"
      :edits="edits"
      :duration="duration"
      :current-time="currentTime"
      :waveform-path="waveformUrl"
      :update-time="updateSegmentTime"
      @seek="handleSeek"
      @select-range="handleSelectRange"
      @add-segment="handleAddSegment"
      @delete-segment="handleDeleteSegment"
      @seek-segment="handleSeekSegment"
    />

    <!-- Delete silence confirmation dialog -->
    <Teleport to="body">
      <div
        v-if="showConfirmDeleteSilence"
        class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
        @click.self="showConfirmDeleteSilence = false"
      >
        <div class="rounded-lg bg-white p-5 shadow-xl max-w-sm w-full mx-4">
          <h3 class="text-sm font-semibold text-gray-900">Delete All Silence Markers</h3>
          <p class="mt-2 text-xs text-gray-500">
            Delete all {{ silenceCount }} silence detection markers? This cannot be undone.
          </p>
          <div class="mt-4 flex justify-end gap-2">
            <button
              class="rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 transition-colors"
              @click="showConfirmDeleteSilence = false"
            >
              Cancel
            </button>
            <button
              class="rounded bg-red-500 px-3 py-1.5 text-xs text-white hover:bg-red-600 transition-colors"
              @click="handleConfirmDeleteSilence"
            >
              Delete All
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

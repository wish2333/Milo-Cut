<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import type { Project, Segment, EditDecision } from "@/types/project"
import type { EditSummary } from "@/types/edit"
import { formatTimeShort } from "@/utils/format"
import { call } from "@/bridge"
import { useAnalysis } from "@/composables/useAnalysis"
import { useExport } from "@/composables/useExport"
import { useEdit } from "@/composables/useEdit"
import ProgressBar from "@/components/common/ProgressBar.vue"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"
import SearchReplaceBar from "@/components/workspace/SearchReplaceBar.vue"
import EditSummaryModal from "@/components/workspace/EditSummaryModal.vue"

interface Props {
  project: Project
}

interface Emits {
  (e: "project-updated", project: Project): void
  (e: "project-closed"): void
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
  getExportSummary,
  exportVideo,
  exportSrt,
} = useExport(projectRef)

const {
  updateSegmentText,
  searchReplace,
  confirmAllSuggestions,
  rejectAllSuggestions,
} = useEdit(projectRef)

const statusMessage = ref("")
const errorMessage = ref("")
const showAnalysisDropdown = ref(false)
const showExportSummary = ref(false)
const exportSummaryData = ref<EditSummary | null>(null)
const selectedSegmentId = ref<string | null>(null)
const videoUrl = ref("")
const videoRef = ref<HTMLVideoElement | null>(null)

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
  const res = await call<string>("get_video_url", mediaPath)
  if (res.success && res.data) {
    videoUrl.value = res.data
  }
}

onMounted(loadVideoUrl)

watch(() => props.project.media?.path, loadVideoUrl)

function getEditForSegment(seg: Segment): EditDecision | undefined {
  return edits.value.find(e =>
    Math.abs(e.start - seg.start) < 0.01 && Math.abs(e.end - seg.end) < 0.01,
  )
}

function getEditStatus(seg: Segment): EditDecision["status"] | null {
  return getEditForSegment(seg)?.status ?? null
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

async function handleToggleEditStatus(segment: Segment) {
  const edit = edits.value.find(e =>
    Math.abs(e.start - segment.start) < 0.01 && Math.abs(e.end - segment.end) < 0.01,
  )
  if (!edit) return
  const nextStatus = edit.status === "confirmed" ? "pending" : edit.status === "rejected" ? "pending" : null
  if (!nextStatus) return
  await call<Project>("update_edit_decision", edit.id, nextStatus)
  const projRes = await call<Project>("get_project")
  if (projRes.success && projRes.data) {
    emit("project-updated", projRes.data)
  }
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

async function handleUpdateText(segmentId: string, text: string) {
  await updateSegmentText(segmentId, text)
}

async function handleSearchReplace(query: string, replacement: string, scope: string) {
  const result = await searchReplace(query, replacement, scope)
  if (result) {
    statusMessage.value = `Replaced ${result.count} occurrences`
  }
}

async function handleExportVideo() {
  errorMessage.value = ""
  const summary = await getExportSummary()
  if (summary) {
    exportSummaryData.value = summary
    showExportSummary.value = true
  } else {
    statusMessage.value = "Exporting video..."
    const ok = await exportVideo()
    if (!ok) errorMessage.value = "Export failed"
  }
}

async function handleConfirmExport() {
  showExportSummary.value = false
  statusMessage.value = "Exporting video..."
  const ok = await exportVideo()
  statusMessage.value = ""
  if (!ok) errorMessage.value = "Export failed"
}

async function handleExportSrt() {
  errorMessage.value = ""
  statusMessage.value = "Exporting SRT..."
  const ok = await exportSrt()
  statusMessage.value = ""
  if (!ok) errorMessage.value = "Failed to export SRT"
}

async function handleCloseProject() {
  await call("close_project")
  videoUrl.value = ""
  emit("project-closed")
}

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === "s") {
    e.preventDefault()
    call("save_project")
  }
}
</script>

<template>
  <div class="flex h-screen flex-col bg-white" @keydown="handleKeydown">
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
          @click="call('save_project')"
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
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting"
        @click="handleDetectSilence"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" /><path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
        {{ isDetecting ? 'Detecting...' : 'Detect Silence' }}
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

      <div class="mx-1 h-4 w-px bg-gray-300" />

      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportVideo"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
        {{ isExporting ? 'Exporting...' : 'Export Video' }}
      </button>
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportSrt"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        Export SRT
      </button>

      <div class="flex-1" />

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
    <div v-if="statusMessage" class="border-b border-gray-200 bg-blue-50 px-4 py-1 text-xs text-blue-600">
      {{ statusMessage }}
    </div>
    <div v-if="errorMessage" class="border-b border-gray-200 bg-red-50 px-4 py-1 text-xs text-red-600">
      {{ errorMessage }}
    </div>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Video player area -->
      <div class="flex w-2/5 min-w-[400px] flex-col border-r border-gray-200 bg-gray-900">
        <div class="flex flex-1 items-center justify-center p-2">
          <video
            v-if="videoUrl"
            ref="videoRef"
            :src="videoUrl"
            controls
            class="max-h-full max-w-full rounded"
            preload="metadata"
            @loadedmetadata="handleVideoLoaded"
          />
          <div v-else class="text-center text-gray-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">Loading video...</p>
          </div>
        </div>
      </div>

      <!-- Right: Transcript editor + suggestion panel -->
      <div class="flex w-3/5 min-w-[500px] flex-col">
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <span class="text-sm font-medium">Timeline</span>
          <span class="text-xs text-gray-500">{{ subtitleCount }} subtitles + {{ silenceCount }} silence</span>
        </div>

        <div class="flex flex-1 overflow-hidden">
          <!-- Transcript list -->
          <div class="flex-1 overflow-y-auto">
            <div v-if="mergedSegments.length === 0" class="flex h-full items-center justify-center">
              <div class="text-center">
                <p class="text-sm text-gray-500">No segments loaded</p>
                <p class="mt-1 text-xs text-gray-400">Click "Import SRT" to load subtitles</p>
              </div>
            </div>

            <div v-else>
              <template v-for="seg in mergedSegments" :key="seg.id">
                <TranscriptRow
                  v-if="seg.type === 'subtitle'"
                  :segment="seg"
                  :edit-status="getEditStatus(seg)"
                  :is-selected="selectedSegmentId === seg.id"
                  @seek="handleSeek"
                  @update-text="handleUpdateText"
                  @toggle-status="handleToggleEditStatus(seg)"
                  @mark-delete="() => { const e = edits.find(ed => Math.abs(ed.start - seg.start) < 0.01); if (e) confirmEdit(e.id) }"
                />
                <SilenceRow
                  v-else
                  :segment="seg"
                  :edit-status="getEditStatus(seg)"
                  @seek="handleSeek"
                />
              </template>
            </div>
          </div>

          <!-- Suggestion panel (right sidebar) -->
          <div v-if="analysisResults.length > 0 || edits.some(e => e.status === 'pending')" class="w-72 border-l border-gray-200 overflow-y-auto">
            <SuggestionPanel
              :analysis-results="analysisResults"
              :edits="edits"
              :segments="segments"
              @confirm-edit="confirmEdit"
              @reject-edit="rejectEdit"
              @confirm-all="handleConfirmAllSuggestions"
              @reject-all="handleRejectAllSuggestions"
              @seek="handleSeek"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Export summary modal -->
    <EditSummaryModal
      v-if="exportSummaryData"
      :summary="exportSummaryData"
      :visible="showExportSummary"
      @confirm="handleConfirmExport"
      @cancel="showExportSummary = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue"
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

const segments = computed<Segment[]>(() => props.project.transcript?.segments ?? [])
const edits = computed<EditDecision[]>(() => props.project.edits ?? [])
const duration = computed(() => props.project.media?.duration ?? 0)
const analysisResults = computed(() => props.project.analysis?.results ?? [])

const mergedSegments = computed<Segment[]>(() => {
  return [...segments.value].sort((a, b) => a.start - b.start)
})

const silenceCount = computed(() => segments.value.filter(s => s.type === "silence").length)
const subtitleCount = computed(() => segments.value.filter(s => s.type === "subtitle").length)

function getEditForSegment(seg: Segment): EditDecision | undefined {
  return edits.value.find(e =>
    Math.abs(e.start - seg.start) < 0.01 && Math.abs(e.end - seg.end) < 0.01,
  )
}

function getEditStatus(seg: Segment): EditDecision["status"] | null {
  return getEditForSegment(seg)?.status ?? null
}

function handleSeek(_time: number) {
  // TODO: Wire up video player seek
}

async function handleImportSrt() {
  errorMessage.value = ""
  statusMessage.value = "..."
  const fileRes = await call<string>("select_file")
  if (!fileRes.success || !fileRes.data) {
    statusMessage.value = ""
    return
  }
  statusMessage.value = "..."
  const importRes = await call<Project>("import_srt", fileRes.data)
  if (importRes.success && importRes.data) {
    emit("project-updated", importRes.data)
    statusMessage.value = ""
  } else {
    errorMessage.value = importRes.error ?? "SRT"
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
    statusMessage.value = "..."
    const ok = await exportVideo()
    if (!ok) errorMessage.value = ""
  }
}

async function handleConfirmExport() {
  showExportSummary.value = false
  statusMessage.value = "..."
  const ok = await exportVideo()
  statusMessage.value = ""
  if (!ok) errorMessage.value = ""
}

async function handleExportSrt() {
  errorMessage.value = ""
  statusMessage.value = " SRT..."
  const ok = await exportSrt()
  statusMessage.value = ""
  if (!ok) errorMessage.value = " SRT"
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
        <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
        <span class="text-xs text-gray-400">
          {{ subtitleCount }} | {{ silenceCount }} | {{ formatTimeShort(duration) }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="confirmedEdits.length > 0" class="text-xs text-yellow-300">
          {{ confirmedEdits.length }} | {{ formatTimeShort(estimatedSaving) }}
        </span>
      </div>
    </nav>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
      <button
        class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isDetecting || isExporting"
        @click="handleImportSrt"
      >
        SRT
      </button>
      <button
        class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isDetecting || isExporting"
        @click="handleDetectSilence"
      >
        {{ isDetecting ? '...' : '' }}
      </button>

      <!-- Analysis dropdown -->
      <div class="relative">
        <button
          class="rounded-md bg-purple-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
          :disabled="isDetecting || isExporting"
          @click="showAnalysisDropdown = !showAnalysisDropdown"
        >
          {{ isDetecting ? '...' : '' }}
        </button>
        <div
          v-if="showAnalysisDropdown"
          class="absolute top-full left-0 mt-1 w-40 rounded-md border border-gray-200 bg-white shadow-lg z-10"
        >
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
            @click="handleRunAnalysis('filler')"
          >
            Filler
          </button>
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
            @click="handleRunAnalysis('error')"
          >
            Error
          </button>
          <button
            class="block w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
            @click="handleRunAnalysis('full')"
          >
            Full
          </button>
        </div>
      </div>

      <div class="mx-2 h-4 w-px bg-gray-300" />

      <button
        class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportVideo"
      >
        {{ isExporting ? '...' : '' }}
      </button>
      <button
        class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportSrt"
      >
        SRT
      </button>

      <div v-if="isDetecting && detectionProgress" class="ml-4 flex-1">
        <ProgressBar :percent="detectionProgress.percent" :message="detectionProgress.message" />
      </div>
      <div v-else-if="isExporting && exportProgress" class="ml-4 flex-1">
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
      <div class="flex w-2/5 min-w-[400px] flex-col border-r border-gray-200">
        <div class="flex flex-1 items-center justify-center bg-gray-900">
          <div class="text-center text-gray-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm"></p>
            <p class="text-xs text-gray-500"></p>
          </div>
        </div>
      </div>

      <!-- Right: Transcript editor + suggestion panel -->
      <div class="flex w-3/5 min-w-[500px] flex-col">
        <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <span class="text-sm font-medium"></span>
          <span class="text-xs text-gray-500">{{ subtitleCount }} + {{ silenceCount }}</span>
        </div>

        <div class="flex flex-1 overflow-hidden">
          <!-- Transcript list -->
          <div class="flex-1 overflow-y-auto">
            <div v-if="mergedSegments.length === 0" class="flex h-full items-center justify-center">
              <div class="text-center">
                <p class="text-sm text-gray-500"></p>
                <p class="mt-1 text-xs text-gray-400"> SRT</p>
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

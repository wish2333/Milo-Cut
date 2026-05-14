<script setup lang="ts">
import { computed, ref } from "vue"
import type { Project, Segment, EditDecision } from "@/types/project"
import { formatTimeShort } from "@/utils/format"
import { call } from "@/bridge"
import { useAnalysis } from "@/composables/useAnalysis"
import { useExport } from "@/composables/useExport"
import ProgressBar from "@/components/common/ProgressBar.vue"

interface Props {
  project: Project
}

interface Emits {
  (e: "project-updated", project: Project): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const projectRef = computed(() => props.project)

const {
  isDetecting,
  detectionProgress,
  runSilenceDetection,
  confirmEdit,
  rejectEdit,
  confirmAllEdits,
} = useAnalysis(projectRef)

const {
  isExporting,
  exportProgress,
  confirmedEdits,
  estimatedSaving,
  exportVideo,
  exportSrt,
} = useExport(projectRef)

const statusMessage = ref("")
const errorMessage = ref("")

const segments = computed<Segment[]>(() => props.project.transcript?.segments ?? [])
const edits = computed<EditDecision[]>(() => props.project.edits ?? [])
const duration = computed(() => props.project.media?.duration ?? 0)

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

function getEditStatusColor(status: string): string {
  switch (status) {
    case "confirmed": return "bg-red-100 text-red-700"
    case "rejected": return "bg-green-100 text-green-700"
    default: return "bg-yellow-100 text-yellow-700"
  }
}

function getEditStatusLabel(status: string): string {
  switch (status) {
    case "confirmed": return "删除"
    case "rejected": return "保留"
    default: return "待定"
  }
}

async function handleImportSrt() {
  errorMessage.value = ""
  statusMessage.value = "选择 SRT 文件..."

  const fileRes = await call<string>("select_file")
  if (!fileRes.success || !fileRes.data) {
    statusMessage.value = ""
    return
  }

  statusMessage.value = "导入 SRT..."
  const importRes = await call<Project>("import_srt", fileRes.data)
  if (importRes.success && importRes.data) {
    emit("project-updated", importRes.data)
    statusMessage.value = ""
  } else {
    errorMessage.value = importRes.error ?? "导入 SRT 失败"
    statusMessage.value = ""
  }
}

async function handleDetectSilence() {
  errorMessage.value = ""
  await runSilenceDetection()
}

async function handleConfirmAll() {
  errorMessage.value = ""
  await confirmAllEdits()
}

async function handleExportVideo() {
  errorMessage.value = ""
  statusMessage.value = "导出视频..."
  const ok = await exportVideo()
  statusMessage.value = ok ? "" : ""
  if (!ok) {
    errorMessage.value = "导出视频失败"
  }
}

async function handleExportSrt() {
  errorMessage.value = ""
  statusMessage.value = "导出 SRT..."
  const ok = await exportSrt()
  statusMessage.value = ok ? "" : ""
  if (!ok) {
    errorMessage.value = "导出 SRT 失败"
  }
}
</script>

<template>
  <div class="flex h-screen flex-col bg-canvas">
    <!-- Top nav -->
    <nav class="flex h-11 items-center justify-between border-b border-hairline bg-surface-tile-1 px-4">
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
        <span class="text-xs text-ink-muted">
          {{ subtitleCount }} 字幕 | {{ silenceCount }} 静音 | {{ formatTimeShort(duration) }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="confirmedEdits.length > 0" class="text-xs text-yellow-300">
          {{ confirmedEdits.length }} 段待删 | {{ formatTimeShort(estimatedSaving) }}
        </span>
      </div>
    </nav>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 border-b border-hairline bg-parchment px-4 py-2">
      <button
        class="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isDetecting || isExporting"
        @click="handleImportSrt"
      >
        导入 SRT
      </button>
      <button
        class="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isDetecting || isExporting"
        @click="handleDetectSilence"
      >
        {{ isDetecting ? '检测中...' : '检测静音' }}
      </button>
      <button
        v-if="silenceCount > 0"
        class="rounded-md bg-yellow-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isDetecting || isExporting"
        @click="handleConfirmAll"
      >
        全部确认删除
      </button>

      <div class="mx-2 h-4 w-px bg-hairline" />

      <button
        class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportVideo"
      >
        {{ isExporting ? '导出中...' : '导出视频' }}
      </button>
      <button
        class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        :disabled="isExporting || confirmedEdits.length === 0"
        @click="handleExportSrt"
      >
        导出 SRT
      </button>

      <div v-if="isDetecting && detectionProgress" class="ml-4 flex-1">
        <ProgressBar :percent="detectionProgress.percent" :message="detectionProgress.message" />
      </div>
      <div v-else-if="isExporting && exportProgress" class="ml-4 flex-1">
        <ProgressBar :percent="exportProgress.percent" :message="exportProgress.message" />
      </div>
    </div>

    <!-- Status messages -->
    <div v-if="statusMessage" class="border-b border-hairline bg-blue-50 px-4 py-1 text-xs text-primary">
      {{ statusMessage }}
    </div>
    <div v-if="errorMessage" class="border-b border-hairline bg-red-50 px-4 py-1 text-xs text-red-600">
      {{ errorMessage }}
    </div>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Video player area -->
      <div class="flex w-2/5 min-w-[400px] flex-col border-r border-hairline">
        <div class="flex flex-1 items-center justify-center bg-surface-tile-1">
          <div class="text-center text-ink-muted">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">视频预览区</p>
            <p class="text-xs text-ink-muted-48">Phase 0 - 视频预览 P1 实现</p>
          </div>
        </div>
      </div>

      <!-- Right: Transcript editor with merged timeline -->
      <div class="flex w-3/5 min-w-[500px] flex-col">
        <div class="flex items-center justify-between border-b border-hairline px-4 py-2">
          <span class="text-sm font-medium text-ink">时间轴</span>
          <span class="text-xs text-ink-muted">{{ subtitleCount }} 字幕 + {{ silenceCount }} 静音</span>
        </div>

        <div class="flex-1 overflow-y-auto">
          <div v-if="mergedSegments.length === 0" class="flex h-full items-center justify-center">
            <div class="text-center">
              <p class="text-sm text-ink-muted">暂无数据</p>
              <p class="mt-1 text-xs text-ink-muted-48">请导入 SRT 字幕或检测静音</p>
            </div>
          </div>

          <div v-else class="divide-y divide-hairline">
            <div
              v-for="seg in mergedSegments"
              :key="seg.id"
              :class="[
                'flex items-start gap-3 px-4 py-2.5 transition-colors',
                seg.type === 'silence' ? 'bg-status-pending hover:bg-yellow-100' : 'hover:bg-parchment',
              ]"
            >
              <!-- Timestamp -->
              <span class="mt-0.5 shrink-0 text-xs text-ink-muted font-mono">
                {{ formatTimeShort(seg.start) }}
              </span>

              <!-- Content -->
              <div class="flex-1 min-w-0">
                <!-- Subtitle row -->
                <template v-if="seg.type === 'subtitle'">
                  <p class="text-sm leading-relaxed text-ink">{{ seg.text }}</p>
                </template>

                <!-- Silence row -->
                <template v-else>
                  <div class="flex items-center gap-2">
                    <span class="text-sm text-ink-muted">
                      静音 {{ (seg.end - seg.start).toFixed(1) }}s
                    </span>
                    <span
                      :class="['rounded px-1.5 py-0.5 text-xs font-medium', getEditStatusColor(getEditForSegment(seg)?.status ?? 'pending')]"
                    >
                      {{ getEditStatusLabel(getEditForSegment(seg)?.status ?? 'pending') }}
                    </span>
                  </div>
                  <div v-if="getEditForSegment(seg)?.status === 'pending'" class="mt-1 flex gap-1.5">
                    <button
                      class="rounded bg-red-500 px-2 py-0.5 text-xs text-white hover:bg-red-600"
                      @click="getEditForSegment(seg) && confirmEdit(getEditForSegment(seg)!.id)"
                    >
                      确认删除
                    </button>
                    <button
                      class="rounded bg-green-500 px-2 py-0.5 text-xs text-white hover:bg-green-600"
                      @click="getEditForSegment(seg) && rejectEdit(getEditForSegment(seg)!.id)"
                    >
                      保留
                    </button>
                  </div>
                </template>
              </div>

              <!-- End timestamp -->
              <span class="mt-0.5 shrink-0 text-xs text-ink-muted-48 font-mono">
                {{ formatTimeShort(seg.end) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

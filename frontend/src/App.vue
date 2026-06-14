<script setup lang="ts">
import { ref } from "vue"
import WelcomePage from "@/pages/WelcomePage.vue"
import WorkspacePage from "@/pages/WorkspacePage.vue"
import ExportPage from "@/pages/ExportPage.vue"
import ToastContainer from "@/components/common/ToastContainer.vue"
import RelinkMediaDialog from "@/components/workspace/RelinkMediaDialog.vue"
import { waitForPyWebView, call, onEvent } from "./bridge"
import { useUvAvailability } from "@/composables/useUvAvailability"
import { EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project, MediaInfo } from "@/types/project"

const ready = ref(false)
const bridgeError = ref("")
const { checkUvAvailable } = useUvAvailability()
const project = ref<Project | null>(null)
const showExportPage = ref(false)
const isDragging = ref(false)
const showRelinkDialog = ref(false)
const relinkLostPath = ref("")
let dragCounter = 0

// Page order for directional slide transitions: 0=welcome, 1=workspace, 2=export.
// Forward (index increases) slides left; backward slides right.
const transitionName = ref<"slide-forward" | "slide-backward">("slide-forward")
function pageOrder(): number {
  if (!project.value) return 0
  return showExportPage.value ? 2 : 1
}
function setDirection(before: number, after: number) {
  transitionName.value = after > before ? "slide-forward" : "slide-backward"
}

waitForPyWebView(10_000)
  .then(() => {
    ready.value = true
    checkUvAvailable()
  })
  .catch((err: unknown) => {
    bridgeError.value = err instanceof Error ? err.message : "Bridge init failed"
  })

function triggerWaveformGeneration() {
  if (!project.value?.media || project.value.media.waveform_path) return
  call("create_task", "waveform_generation").then(res => {
    if (res.success && res.data) {
      call("start_task", (res.data as { id: string }).id)
    }
  })
}

onEvent<{ task_id: string; task_type?: string; result?: { project?: Project } }>(
  EVENT_TASK_COMPLETED,
  (data) => {
    if (data.task_type === "waveform_generation" && data.result?.project) {
      project.value = data.result.project
    }
  },
)

function onProjectCreated(data: Project) {
  setDirection(pageOrder(), 1)
  project.value = data
  triggerWaveformGeneration()
}

function onRelinkNeeded(lostPath: string, _projectPath: string) {
  // _projectPath retained in signature for future use (multi-project relink context)
  void _projectPath
  relinkLostPath.value = lostPath
  showRelinkDialog.value = true
}

function onProjectUpdated(data: Project) {
  project.value = data
}

function onProjectClosed() {
  setDirection(pageOrder(), 0)
  project.value = null
  showExportPage.value = false
}

function onGoToExport() {
  setDirection(pageOrder(), 2)
  showExportPage.value = true
}

function onGoBackToWorkspace() {
  setDirection(pageOrder(), 1)
  showExportPage.value = false
}

function handleWindowDragEnter(e: DragEvent) {
  e.preventDefault()
  dragCounter++
  if (dragCounter === 1) {
    isDragging.value = true
  }
}

function handleWindowDragOver(e: DragEvent) {
  e.preventDefault()
}

function handleWindowDragLeave(e: DragEvent) {
  e.preventDefault()
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    isDragging.value = false
  }
}

async function handleWindowDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter = 0
  isDragging.value = false

  await new Promise(r => setTimeout(r, 100))
  const res = await call<string[]>("get_dropped_files")
  if (!res.success || !res.data || res.data.length === 0) return

  const filePath = res.data[0]
  const filename = filePath.split(/[/\\]/).pop() ?? ""
  const isMedia = /\.(mp4|mkv|avi|mov|webm|mp3|wav|aac|flac|ogg|m4a)$/i.test(filePath)
  const isSrt = /\.srt$/i.test(filePath)
  const isProjectJson = filename === "project.json"

  if (!project.value && isProjectJson) {
    // Open existing project from project.json
    const openRes = await call<Project>("open_project", filePath)
    if (openRes.success && openRes.data) {
      setDirection(pageOrder(), 1)
      project.value = openRes.data
      triggerWaveformGeneration()
    } else if (openRes.error === "MEDIA_NOT_FOUND" && openRes.data) {
      const data = openRes.data as unknown as { path: string }
      relinkLostPath.value = data.path
      showRelinkDialog.value = true
    }
  } else if (!project.value && isMedia) {
    const probeRes = await call<MediaInfo>("probe_media", filePath)
    if (!probeRes.success || !probeRes.data) return
    const name = filePath.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
    const createRes = await call<Project>("create_project", name, filePath)
    if (createRes.success && createRes.data) {
      setDirection(pageOrder(), 1)
      project.value = createRes.data
      triggerWaveformGeneration()
    }
  } else if (project.value && isSrt) {
    const importRes = await call<Project>("import_srt", filePath)
    if (importRes.success && importRes.data) {
      project.value = importRes.data
    }
  } else if (!project.value && isSrt) {
    // Can't import SRT without a project - ignore
  }
}

async function handleRelink(newPath: string) {
  const res = await call<Project>("relink_media", newPath)
  if (res.success && res.data) {
    showRelinkDialog.value = false
    relinkLostPath.value = ""
    project.value = res.data
    triggerWaveformGeneration()
  }
}

function handleRelinkCancel() {
  showRelinkDialog.value = false
  relinkLostPath.value = ""
}
</script>

<template>
  <div
    class="relative min-h-screen overflow-x-hidden overflow-y-hidden"
    @dragenter="handleWindowDragEnter"
    @dragover="handleWindowDragOver"
    @dragleave="handleWindowDragLeave"
    @drop="handleWindowDrop"
  >
    <!-- Full-window drag overlay -->
    <div
      v-if="isDragging"
      class="fixed inset-0 z-[9999] flex items-center justify-center bg-blue-500/10 backdrop-blur-sm pointer-events-none"
    >
      <div class="rounded-2xl border-2 border-dashed border-blue-400 bg-white/90 px-16 py-12 text-center shadow-2xl">
        <p class="text-xl font-semibold text-blue-600">
          {{ project ? "松开以导入 SRT 文件" : "松开以导入媒体文件或打开项目" }}
        </p>
        <p class="mt-2 text-sm text-gray-500">
          {{ project ? "支持 .srt 字幕文件" : "支持视频、音频、project.json" }}
        </p>
      </div>
    </div>

    <div v-if="bridgeError" class="flex min-h-screen items-center justify-center bg-canvas">
      <div class="text-center">
        <p class="text-lg font-semibold text-status-warning">Bridge Error</p>
        <p class="mt-2 text-sm text-ink-muted">{{ bridgeError }}</p>
      </div>
    </div>

    <div v-else-if="!ready" class="flex min-h-screen items-center justify-center bg-canvas">
      <div class="text-center">
        <p class="text-lg font-semibold text-ink">Milo-Cut</p>
        <p class="mt-2 text-sm text-ink-muted">正在连接后端...</p>
      </div>
    </div>

    <Transition :name="transitionName">
      <WelcomePage
        v-if="!project"
        key="welcome"
        @project-created="onProjectCreated"
        @relink-needed="onRelinkNeeded"
      />

      <ExportPage
        v-else-if="showExportPage"
        key="export"
        :project="project!"
        @go-back="onGoBackToWorkspace"
        @project-updated="onProjectUpdated"
      />

      <WorkspacePage
        v-else
        key="workspace"
        :project="project!"
        @project-updated="onProjectUpdated"
        @project-closed="onProjectClosed"
        @go-to-export="onGoToExport"
      />
    </Transition>

    <RelinkMediaDialog
      :visible="showRelinkDialog"
      :lost-path="relinkLostPath"
      @relink="handleRelink"
      @cancel="handleRelinkCancel"
    />

    <ToastContainer />
  </div>
</template>

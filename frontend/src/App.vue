<script setup lang="ts">
import { ref } from "vue"
import WelcomePage from "@/pages/WelcomePage.vue"
import WorkspacePage from "@/pages/WorkspacePage.vue"
import ExportPage from "@/pages/ExportPage.vue"
import ToastContainer from "@/components/common/ToastContainer.vue"
import RelinkMediaDialog from "@/components/workspace/RelinkMediaDialog.vue"
import ConflictResolutionView from "@/components/workspace/ConflictResolutionView.vue"
import { waitForPyWebView, call, onEvent, isDemoMode } from "./bridge"
import { resetDemoRuntime } from "@/demo/demoBridge"
import { useUvAvailability } from "@/composables/useUvAvailability"
import { EVENT_DEMO_PROJECT_UPDATED, EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project, MediaInfo, ProjectResponse } from "@/types/project"
import { isProjectPatch } from "@/types/project"
import { applyProjectPatch, isStalePatch } from "@/utils/projectPatch"

const ready = ref(false)
const bridgeError = ref("")
const { checkUvAvailable } = useUvAvailability()
const project = ref<Project | null>(null)
// v2.3.2 stage 2: monotonic revision tracker. Backend includes ``revision``
// in every ProjectPatch envelope; we reject patches whose revision is not
// strictly greater than this value, defending against out-of-order bridge
// responses (e.g. user clicks toggle twice rapidly and the older response
// lands after the newer one).
const lastSeenRevision = ref(0)
const showExportPage = ref(false)
const isDragging = ref(false)
const showRelinkDialog = ref(false)
const relinkLostPath = ref("")
const demoMode = isDemoMode()
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

if (demoMode) {
  ready.value = true
  call<Project>("get_project").then((res) => {
    if (res.success && res.data) project.value = res.data
  })
} else {
  waitForPyWebView(10_000)
    .then(() => {
      ready.value = true
      checkUvAvailable()
    })
    .catch((err: unknown) => {
      bridgeError.value = err instanceof Error ? err.message : "Bridge init failed"
    })
}

function resetDemo() {
  resetDemoRuntime()
  project.value = null
  showExportPage.value = false
  call<Project>("get_project").then((res) => {
    if (res.success && res.data) project.value = res.data
  })
}

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

onEvent<Project>(EVENT_DEMO_PROJECT_UPDATED, (data) => {
  if (demoMode) project.value = data
})

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

function onProjectUpdated(data: ProjectResponse) {
  if (!project.value) {
    if (data && !isProjectPatch(data)) {
      project.value = data
    }
    return
  }
  if (isProjectPatch(data)) {
    if (isStalePatch(data, lastSeenRevision.value)) {
      // Drop stale patch; current state is newer than this response.
      return
    }
    lastSeenRevision.value = data.revision
    project.value = applyProjectPatch(project.value, data)
  } else {
    project.value = data
  }
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

const isFileDrag = (e: DragEvent): boolean => {
  return e.dataTransfer?.types.includes("Files") ?? false
}

function handleWindowDragEnter(e: DragEvent) {
  if (!isFileDrag(e)) return
  e.preventDefault()
  dragCounter++
  if (dragCounter === 1) {
    isDragging.value = true
  }
}

function handleWindowDragOver(e: DragEvent) {
  if (!isFileDrag(e)) return
  e.preventDefault()
}

function handleWindowDragLeave(e: DragEvent) {
  if (!isFileDrag(e)) return
  e.preventDefault()
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    isDragging.value = false
  }
}

async function handleWindowDrop(e: DragEvent) {
  if (!isFileDrag(e)) return
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
    class="relative h-screen overflow-x-hidden overflow-y-hidden"
    @dragenter="handleWindowDragEnter"
    @dragover="handleWindowDragOver"
    @dragleave="handleWindowDragLeave"
    @drop="handleWindowDrop"
  >
    <div
      v-if="demoMode"
      class="demo-mode-badge fixed right-4 top-3 z-[100] flex items-center gap-2 rounded-[var(--radius-control)] bg-surface-tile-1 px-3 py-1.5 text-xs text-white shadow-lg max-[1199px]:top-14"
    >
      <span class="text-white/70">浏览器演示模式</span>
      <button class="mc-button mc-button-secondary min-h-7 border-white/20 bg-transparent px-2 py-0.5 text-white hover:bg-white/10" @click="resetDemo">
        重置演示
      </button>
    </div>
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

    <!-- v2.1.0 Phase 3: workflow conflict resolution overlay -->
    <ConflictResolutionView />
  </div>
</template>

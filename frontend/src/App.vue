<script setup lang="ts">
import { ref } from "vue"
import WelcomePage from "@/pages/WelcomePage.vue"
import WorkspacePage from "@/pages/WorkspacePage.vue"
import ExportPage from "@/pages/ExportPage.vue"
import ToastContainer from "@/components/common/ToastContainer.vue"
import { waitForPyWebView, call } from "./bridge"
import type { Project, MediaInfo } from "@/types/project"

const ready = ref(false)
const bridgeError = ref("")
const project = ref<Project | null>(null)
const showExportPage = ref(false)
const isDragging = ref(false)
let dragCounter = 0

waitForPyWebView(10_000)
  .then(() => {
    ready.value = true
  })
  .catch((err: unknown) => {
    bridgeError.value = err instanceof Error ? err.message : "Bridge init failed"
  })

function onProjectCreated(data: Project) {
  project.value = data
}

function onProjectUpdated(data: Project) {
  project.value = data
}

function onProjectClosed() {
  project.value = null
  showExportPage.value = false
}

function onGoToExport() {
  showExportPage.value = true
}

function onGoBackToWorkspace() {
  showExportPage.value = false
}

function onProjectClosed() {
  project.value = null
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
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  const isMedia = /\.(mp4|mkv|avi|mov|webm|mp3|wav|aac|flac|ogg|m4a)$/i.test(filePath)
  const isSrt = /\.srt$/i.test(filePath)
  const isProjectJson = filename === "project.json"

  if (!project.value && isProjectJson) {
    // Open existing project from project.json
    const openRes = await call<Project>("open_project", filePath)
    if (openRes.success && openRes.data) {
      project.value = openRes.data
      // Show warnings if media file is not reachable
      if (openRes.warnings && openRes.warnings.length > 0) {
        console.warn("Project opened with warnings:", openRes.warnings)
      }
    }
  } else if (!project.value && isMedia) {
    const probeRes = await call<MediaInfo>("probe_media", filePath)
    if (!probeRes.success || !probeRes.data) return
    const name = filePath.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
    const createRes = await call<Project>("create_project", name, filePath)
    if (createRes.success && createRes.data) {
      project.value = createRes.data
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
</script>

<template>
  <div
    class="min-h-screen"
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

    <WelcomePage v-else-if="!project" @project-created="onProjectCreated" />

    <ExportPage
      v-else-if="showExportPage"
      :project="project"
      @go-back="onGoBackToWorkspace"
      @project-updated="onProjectUpdated"
    />

    <WorkspacePage
      v-else
      :project="project"
      @project-updated="onProjectUpdated"
      @project-closed="onProjectClosed"
      @go-to-export="onGoToExport"
    />

    <ToastContainer />
  </div>
</template>

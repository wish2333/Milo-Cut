<script setup lang="ts">
import { onMounted, ref } from "vue"
import FileDropInput from "@/components/common/FileDropInput.vue"
import { call } from "@/bridge"
import type { MediaInfo, Project } from "@/types/project"
import type { RecentProject } from "@/types/edit"

interface Emits {
  (e: "project-created", project: Project): void
}

const emit = defineEmits<Emits>()

const status = ref("")
const error = ref("")
const recentProjects = ref<RecentProject[]>([])
const loadingRecent = ref(false)

onMounted(async () => {
  const res = await call<RecentProject[]>("get_recent_projects")
  if (res.success && res.data) {
    recentProjects.value = res.data
  }
})

async function openRecentProject(rp: RecentProject) {
  error.value = ""
  status.value = "正在打开项目..."
  loadingRecent.value = true

  const res = await call<Project>("open_project", rp.path)
  loadingRecent.value = false

  if (!res.success || !res.data) {
    error.value = res.error ?? "打开项目失败"
    status.value = ""
    return
  }

  status.value = ""
  emit("project-created", res.data)
}

async function handleFilesSelected(paths: string[]) {
  if (paths.length === 0) return
  const mediaPath = paths[0]
  error.value = ""
  status.value = "正在分析视频..."

  const probeRes = await call<MediaInfo>("probe_media", mediaPath)
  if (!probeRes.success) {
    error.value = probeRes.error ?? "无法读取视频信息"
    status.value = ""
    return
  }

  const name = mediaPath.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
  status.value = "正在创建项目..."

  const createRes = await call<Project>("create_project", name, mediaPath)
  if (!createRes.success || !createRes.data) {
    error.value = createRes.error ?? "创建项目失败"
    status.value = ""
    return
  }

  status.value = ""
  emit("project-created", createRes.data)
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return "刚刚"
  if (diffMin < 60) return `${diffMin} 分钟前`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour} 小时前`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 30) return `${diffDay} 天前`
  return date.toLocaleDateString()
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-canvas p-8">
    <div class="w-full max-w-xl">
      <div class="mb-10 text-center">
        <h1 class="text-4xl font-semibold tracking-tight text-ink">Milo-Cut</h1>
        <p class="mt-2 text-base text-ink-muted">AI 驱动的口播视频预处理工具</p>
      </div>

      <FileDropInput @files-selected="handleFilesSelected" />

      <div v-if="status" class="mt-4 text-center text-sm text-primary">
        {{ status }}
      </div>
      <div v-if="error" class="mt-4 text-center text-sm text-status-warning">
        {{ error }}
      </div>

      <div v-if="recentProjects.length > 0" class="mt-8">
        <h2 class="text-sm font-medium text-ink-muted mb-3">最近项目</h2>
        <div class="rounded-lg border border-gray-200 divide-y divide-gray-100 overflow-hidden">
          <button
            v-for="rp in recentProjects"
            :key="rp.path"
            class="w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors flex items-center justify-between gap-3 disabled:opacity-50"
            :disabled="loadingRecent"
            @click="openRecentProject(rp)"
          >
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-ink truncate">{{ rp.name }}</div>
              <div class="text-xs text-ink-muted truncate mt-0.5">{{ rp.path }}</div>
            </div>
            <div class="text-xs text-ink-muted-48 shrink-0">
              {{ formatRelativeTime(rp.updated_at) }}
            </div>
          </button>
        </div>
      </div>

      <div class="mt-8 text-center text-xs text-ink-muted-48">
        Phase 0 - 技术验证
      </div>
    </div>
  </div>
</template>

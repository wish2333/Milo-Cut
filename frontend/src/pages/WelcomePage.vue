<script setup lang="ts">
import { onMounted, ref } from "vue"
import FileDropInput from "@/components/common/FileDropInput.vue"
import SettingsModal from "@/components/workspace/SettingsModal.vue"
import { call } from "@/bridge"
import type { MediaInfo, Project } from "@/types/project"
import type { RecentProject } from "@/types/edit"

interface Emits {
  (e: "project-created", project: Project): void
  (e: "relink-needed", lostPath: string, projectPath: string): void
}

const emit = defineEmits<Emits>()

const status = ref("")
const error = ref("")
const recentProjects = ref<RecentProject[]>([])
const loadingRecent = ref(false)
const showSettings = ref(false)
const appVersion = ref("")

onMounted(async () => {
  const [recentRes, infoRes] = await Promise.all([
    call<RecentProject[]>("get_recent_projects"),
    call<{ version: string }>("get_app_info"),
  ])
  if (recentRes.success && recentRes.data) {
    recentProjects.value = recentRes.data
  }
  if (infoRes.success && infoRes.data) {
    appVersion.value = infoRes.data.version
  }
})

async function openRecentProject(rp: RecentProject) {
  error.value = ""
  status.value = "正在打开项目..."
  loadingRecent.value = true

  const res = await call<Project>("open_project", rp.path)
  loadingRecent.value = false

  if (!res.success || !res.data) {
    if (res.error === "MEDIA_NOT_FOUND" && res.data) {
      const data = res.data as unknown as { path: string }
      status.value = ""
      emit("relink-needed", data.path, rp.path)
      return
    }
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
      <div class="mb-10 text-center relative">
        <h1 class="text-4xl font-semibold tracking-tight text-ink">Milo-Cut</h1>
        <p class="mt-2 text-base text-ink-muted">AI 驱动的口播视频预处理工具</p>
        <button
          class="absolute top-0 right-0 p-2 text-ink-muted hover:text-ink transition-colors"
          title="Settings"
          @click="showSettings = true"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
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
        {{ appVersion ? `v${appVersion}` : 'Milo-Cut' }}
      </div>
    </div>
  </div>

  <SettingsModal
    :visible="showSettings"
    @close="showSettings = false"
  />
</template>

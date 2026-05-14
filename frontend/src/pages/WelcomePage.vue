<script setup lang="ts">
import { ref } from "vue"
import FileDropInput from "@/components/common/FileDropInput.vue"
import { call } from "@/bridge"
import type { MediaInfo, Project } from "@/types/project"

interface Emits {
  (e: "project-created", project: Project): void
}

const emit = defineEmits<Emits>()

const status = ref("")
const error = ref("")

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

      <div class="mt-8 text-center text-xs text-ink-muted-48">
        Phase 0 - 技术验证
      </div>
    </div>
  </div>
</template>

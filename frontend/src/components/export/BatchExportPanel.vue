<script setup lang="ts">
import { onMounted, ref, computed } from "vue"
import { call } from "@/bridge"
import { useBatch } from "@/composables/useBatch"
import { useToast } from "@/composables/useToast"
import type { RecentProject } from "@/types/edit"
import EncodingSettings from "@/components/export/EncodingSettings.vue"

const emit = defineEmits<{
  "go-back": []
}>()

const { showToast } = useToast()
const {
  completedCount,
  failedCount,
  totalCount,
  taskIds,
  progressPercent,
  isRunning,
  isCompleted,
  isIdle,
  createBatch,
  reset,
} = useBatch()

const recentProjects = ref<RecentProject[]>([])
const selectedPaths = ref<Set<string>>(new Set())
const loading = ref(true)

const encodingSettings = ref({
  outputFormat: "mp4",
  quality: 23,
  resolution: "original",
  videoCodec: "libx264",
  audioCodec: "aac",
  audioBitrate: "192k",
  preset: "medium",
})

onMounted(async () => {
  const res = await call<RecentProject[]>("get_recent_projects")
  loading.value = false
  if (res.success && res.data) {
    recentProjects.value = res.data
  }
})

const selectedCount = computed(() => selectedPaths.value.size)
const allSelected = computed(
  () => recentProjects.value.length > 0 && selectedPaths.value.size === recentProjects.value.length,
)

function toggleProject(path: string) {
  const next = new Set(selectedPaths.value)
  if (next.has(path)) {
    next.delete(path)
  } else {
    next.add(path)
  }
  selectedPaths.value = next
}

function toggleAll() {
  if (allSelected.value) {
    selectedPaths.value = new Set()
  } else {
    selectedPaths.value = new Set(recentProjects.value.map(p => p.path))
  }
}

function handleEncodingSettingsUpdate(settings: typeof encodingSettings.value) {
  encodingSettings.value = settings
}

async function handleStartBatch() {
  if (selectedPaths.value.size === 0) {
    showToast("请至少选择一个项目", "error")
    return
  }

  const paths = Array.from(selectedPaths.value)
  const ok = await createBatch(paths)
  if (!ok) {
    showToast("批量导出创建失败", "error")
    return
  }
  showToast(`已启动 ${paths.length} 个项目的批量导出`, "success")
}

function handleReset() {
  reset()
  selectedPaths.value = new Set()
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
  } catch {
    return iso
  }
}
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50">
    <!-- Top navigation -->
    <div class="flex items-center gap-3 border-b bg-white px-4 py-3">
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-200 transition-colors"
        @click="emit('go-back')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" /></svg>
        返回
      </button>
      <h1 class="text-lg font-semibold">批量导出</h1>
      <div class="flex-1" />
      <span v-if="isRunning" class="text-sm text-blue-600">
        {{ completedCount }}/{{ totalCount }} 已完成
      </span>
      <span v-if="isCompleted" class="text-sm text-green-600">
        批量导出完成
      </span>
    </div>

    <!-- Progress bar (only when running or completed) -->
    <div v-if="!isIdle" class="border-b bg-white px-4 py-2">
      <div class="flex items-center gap-3">
        <div class="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            class="h-full rounded-full transition-all duration-300"
            :class="failedCount > 0 ? 'bg-amber-500' : 'bg-blue-500'"
            :style="{ width: `${progressPercent}%` }"
          />
        </div>
        <span class="text-xs text-gray-500 shrink-0">
          {{ completedCount }}/{{ totalCount }}
          <span v-if="failedCount > 0" class="text-red-500 ml-1">({{ failedCount }} 失败)</span>
        </span>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Project selector + Settings -->
      <div class="w-96 border-r bg-white overflow-y-auto flex flex-col">
        <!-- Project list -->
        <div class="p-4 flex-1">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-medium">选择项目</h3>
            <span class="text-xs text-gray-500">{{ selectedCount }} 已选</span>
          </div>

          <!-- Select all -->
          <label
            v-if="recentProjects.length > 0"
            class="flex items-center gap-2 px-2 py-1.5 text-xs text-gray-500 cursor-pointer hover:bg-gray-50 rounded"
          >
            <input
              type="checkbox"
              :checked="allSelected"
              class="rounded border-gray-300 accent-blue-600"
              @change="toggleAll"
            >
            全选
          </label>

          <!-- Loading state -->
          <div v-if="loading" class="py-8 text-center text-sm text-gray-400">
            加载项目列表...
          </div>

          <!-- Empty state -->
          <div v-else-if="recentProjects.length === 0" class="py-8 text-center text-sm text-gray-400">
            暂无历史项目
          </div>

          <!-- Project list -->
          <div v-else class="space-y-0.5 mt-1">
            <label
              v-for="project in recentProjects"
              :key="project.path"
              class="flex items-start gap-2 px-2 py-2 rounded cursor-pointer hover:bg-gray-50 transition-colors"
              :class="{ 'bg-blue-50': selectedPaths.has(project.path) }"
            >
              <input
                type="checkbox"
                :checked="selectedPaths.has(project.path)"
                class="mt-0.5 rounded border-gray-300 accent-blue-600"
                :disabled="!isIdle"
                @change="toggleProject(project.path)"
              >
              <div class="min-w-0 flex-1">
                <p class="text-sm font-medium text-gray-800 truncate">{{ project.name }}</p>
                <p class="text-xs text-gray-400 truncate">{{ project.path }}</p>
                <p class="text-xs text-gray-400 mt-0.5">{{ formatDate(project.updated_at) }}</p>
              </div>
            </label>
          </div>
        </div>

        <!-- Settings section -->
        <div class="border-t p-4">
          <h3 class="font-medium mb-3 text-sm">导出设置</h3>
          <EncodingSettings @update:settings="handleEncodingSettingsUpdate" />
        </div>
      </div>

      <!-- Right: Actions + Status -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Action area -->
        <div class="max-w-md mx-auto">
          <div class="mb-6">
            <button
              v-if="isIdle"
              class="w-full flex items-center justify-center gap-2 rounded-md bg-green-600 px-4 py-3 text-sm font-medium text-white hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="selectedCount === 0"
              @click="handleStartBatch"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
              开始批量导出 ({{ selectedCount }} 个项目)
            </button>

            <button
              v-if="isCompleted"
              class="w-full flex items-center justify-center gap-2 rounded-md bg-gray-600 px-4 py-3 text-sm font-medium text-white hover:bg-gray-700 transition-colors"
              @click="handleReset"
            >
              新建批量任务
            </button>
          </div>

          <!-- Status summary -->
          <div v-if="!isIdle" class="rounded-lg border bg-white p-4 mb-6">
            <h4 class="text-sm font-medium text-gray-700 mb-3">导出进度</h4>
            <div class="grid grid-cols-3 gap-4 text-center">
              <div>
                <p class="text-2xl font-semibold text-green-600">{{ completedCount }}</p>
                <p class="text-xs text-gray-500">已完成</p>
              </div>
              <div>
                <p class="text-2xl font-semibold text-blue-600">{{ totalCount - completedCount - failedCount }}</p>
                <p class="text-xs text-gray-500">进行中</p>
              </div>
              <div>
                <p class="text-2xl font-semibold text-red-600">{{ failedCount }}</p>
                <p class="text-xs text-gray-500">失败</p>
              </div>
            </div>
          </div>

          <!-- Per-project status (during/after batch) -->
          <div v-if="!isIdle && taskIds.length > 0" class="rounded-lg border bg-white p-4">
            <h4 class="text-sm font-medium text-gray-700 mb-3">项目状态</h4>
            <div class="space-y-1.5">
              <div
                v-for="(path, idx) in Array.from(selectedPaths)"
                :key="path"
                class="flex items-center gap-2 px-2 py-1.5 rounded text-sm"
              >
                <!-- Status indicator dot -->
                <span
                  class="h-2 w-2 rounded-full shrink-0"
                  :class="{
                    'bg-green-500': idx < completedCount,
                    'bg-blue-400 animate-pulse': idx >= completedCount && idx < completedCount + (totalCount - completedCount - failedCount),
                    'bg-red-500': idx >= totalCount - failedCount && failedCount > 0,
                    'bg-gray-300': idx >= completedCount + (totalCount - completedCount - failedCount) && idx < totalCount - failedCount,
                  }"
                />
                <span class="truncate text-gray-700">{{ path.split(/[/\\]/).pop() }}</span>
                <span class="ml-auto text-xs shrink-0" :class="{
                  'text-green-600': idx < completedCount,
                  'text-blue-500': idx >= completedCount && idx < completedCount + (totalCount - completedCount - failedCount),
                  'text-red-500': idx >= totalCount - failedCount && failedCount > 0,
                  'text-gray-400': idx >= completedCount + (totalCount - completedCount - failedCount) && idx < totalCount - failedCount,
                }">
                  {{ idx < completedCount ? '完成' : idx >= totalCount - failedCount && failedCount > 0 ? '失败' : idx >= completedCount && idx < completedCount + (totalCount - completedCount - failedCount) ? '运行中' : '等待中' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Idle state info -->
          <div v-if="isIdle" class="rounded-lg border border-dashed bg-white p-6 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 mx-auto text-gray-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>
            <p class="text-sm text-gray-500">从左侧选择要批量导出的项目</p>
            <p class="text-xs text-gray-400 mt-1">所有项目将使用相同的导出设置</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

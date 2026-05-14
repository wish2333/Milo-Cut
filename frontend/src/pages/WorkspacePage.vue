<script setup lang="ts">
import { computed } from "vue"
import type { Project, MediaInfo, Segment } from "@/types/project"
import { formatTimeShort } from "@/utils/format"

interface Props {
  project: Project
}

const props = defineProps<Props>()

const segments = computed<Segment[]>(() => props.project.transcript?.segments ?? [])
const mediaInfo = computed<MediaInfo | null>(() => props.project.media ?? null)
const segmentCount = computed(() => segments.value.length)
const duration = computed(() => mediaInfo.value?.duration ?? 0)

const statusText = computed(() => {
  if (segmentCount.value === 0) return "暂无字幕数据，请导入 SRT 文件"
  return `共 ${segmentCount.value} 条字幕 | 时长 ${formatTimeShort(duration.value)}`
})
</script>

<template>
  <div class="flex h-screen flex-col bg-canvas">
    <!-- Top nav -->
    <nav class="flex h-11 items-center justify-between border-b border-hairline bg-surface-tile-1 px-4">
      <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
      <span class="text-xs text-ink-muted">{{ statusText }}</span>
    </nav>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Video player area -->
      <div class="flex w-2/5 min-w-[480px] flex-col border-r border-hairline">
        <div class="flex flex-1 items-center justify-center bg-surface-tile-1">
          <div class="text-center text-ink-muted">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">视频预览区</p>
            <p class="text-xs text-ink-muted-48">Phase 0 骨架</p>
          </div>
        </div>
      </div>

      <!-- Right: Transcript editor -->
      <div class="flex w-3/5 min-w-[600px] flex-col">
        <div class="flex items-center justify-between border-b border-hairline px-4 py-2">
          <span class="text-sm font-medium text-ink">字幕编辑</span>
          <span class="text-xs text-ink-muted">{{ segmentCount }} 条</span>
        </div>

        <div class="flex-1 overflow-y-auto">
          <div v-if="segments.length === 0" class="flex h-full items-center justify-center">
            <p class="text-sm text-ink-muted">暂无字幕，请导入 SRT 文件</p>
          </div>

          <div v-else class="divide-y divide-hairline">
            <div
              v-for="seg in segments"
              :key="seg.id"
              class="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-parchment"
            >
              <span class="mt-0.5 shrink-0 text-xs text-ink-muted">
                {{ formatTimeShort(seg.start) }}
              </span>
              <p class="text-sm leading-relaxed text-ink">{{ seg.text }}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

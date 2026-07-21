<script setup lang="ts">
import { computed } from "vue"
import type { Segment } from "@/types/project"
import { formatTimeShort } from "@/utils/format"

const props = defineProps<{
  segments: Segment[]
  currentTime: number
  duration: number
  previewMode: "original" | "edited"
  deleteRanges: Array<{ start: number; end: number }>
}>()

const currentSegment = computed(() => {
  const active = props.segments.find((segment) =>
    segment.type === "subtitle" && props.currentTime >= segment.start && props.currentTime <= segment.end,
  )
  if (active) return active
  const firstSubtitle = props.segments.find((segment) => segment.type === "subtitle")
  return firstSubtitle && props.currentTime < firstSubtitle.start ? firstSubtitle : undefined
})

const inDeleteRange = computed(() => props.deleteRanges.some((range) =>
  props.currentTime >= range.start && props.currentTime <= range.end,
))

const progress = computed(() => props.duration > 0 ? (props.currentTime / props.duration) * 100 : 0)
</script>

<template>
  <div
    class="relative flex h-full w-full max-w-4xl flex-col justify-between overflow-hidden bg-surface-tile-1 p-5 text-white shadow-[3px_5px_30px_rgba(0,0,0,0.28)]"
    tabindex="0"
    :aria-label="`模拟媒体预览，当前时间 ${formatTimeShort(currentTime)}`"
  >
    <div class="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(135deg,transparent_0%,rgba(255,255,255,0.18)_45%,transparent_46%),linear-gradient(45deg,transparent_0%,rgba(255,255,255,0.08)_50%,transparent_51%)] [background-size:240px_180px,180px_140px]" />
    <div class="relative flex items-start justify-between text-xs text-white/60">
      <span>模拟媒体画面</span>
      <span>{{ previewMode === "edited" ? "已编辑预览" : "原始预览" }}</span>
    </div>
    <div class="relative mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center text-center">
      <div class="mb-4 text-3xl font-semibold tracking-tight text-white/90">Milo-Cut</div>
      <div class="text-sm text-white/55">浏览器演示模式 · 不读取真实媒体文件</div>
      <div
        v-if="inDeleteRange && previewMode === 'edited'"
        class="mt-5 rounded-[var(--radius-control)] border border-status-warning/50 bg-status-warning/15 px-3 py-1.5 text-xs text-white/80"
      >
        此处为待确认删除区间
      </div>
    </div>
    <div class="relative space-y-3">
      <p class="min-h-12 text-center text-base font-medium leading-relaxed text-white">
        {{ currentSegment?.text || "点击时间轴，查看对应字幕与建议" }}
      </p>
      <div class="flex items-center gap-3 text-[11px] text-white/55">
        <span>{{ formatTimeShort(currentTime) }}</span>
        <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-white/15">
          <div class="h-full bg-primary transition-[width] duration-100" :style="{ width: `${progress}%` }" />
        </div>
        <span>{{ formatTimeShort(duration) }}</span>
      </div>
    </div>
  </div>
</template>

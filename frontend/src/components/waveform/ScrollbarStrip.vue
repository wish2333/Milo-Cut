<script setup lang="ts">
import { inject, ref } from "vue"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

/**
 * M6-4: dual-mode scrollbar strip.
 * - Legacy (basic, no `overview` prop): single-window thumb driven by the
 *   injected TimelineMetrics -- behavior byte-for-byte unchanged.
 * - Overview (multi, `overview` prop): full-timeline mini strip -- coverage
 *   rectangle from the editor's visibleRows geometry, a playhead tick, and
 *   click/drag seeking via the `overview-seek` event (the editor routes it
 *   through revealTime so jumps stay row-aligned).
 */
const props = defineProps<{
  overview?: {
    leftPercent: number
    widthPercent: number
    playheadPercent: number
    /** Media duration in seconds (pointer -> time mapping). */
    duration: number
  }
}>()

const emit = defineEmits<{
  "overview-seek": [time: number]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const scrollbarRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const dragOriginX = ref(0)
const dragOriginViewStart = ref(0)

function handleMouseDown(e: MouseEvent) {
  isDragging.value = true
  dragOriginX.value = e.clientX
  dragOriginViewStart.value = metrics.viewStart.value

  let rafId: number | null = null

  const onMove = (e: MouseEvent) => {
    if (rafId !== null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      const el = scrollbarRef.value
      if (!el) return
      const rect = el.getBoundingClientRect()
      const deltaPx = e.clientX - dragOriginX.value
      const duration = metrics.duration.value
      if (duration <= 0 || rect.width <= 0) return
      metrics.viewStart.value = dragOriginViewStart.value + deltaPx * duration / rect.width
      metrics.clampViewStart()
    })
  }

  const onUp = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    isDragging.value = false
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }

  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

// -- M6-4: overview seeking (multi) ----------------------------------------

function emitSeekAt(clientX: number): void {
  const el = scrollbarRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const duration = props.overview?.duration ?? 0
  if (rect.width <= 0 || duration <= 0) return
  const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
  emit("overview-seek", ratio * duration)
}

function handleOverviewMouseDown(e: MouseEvent) {
  isDragging.value = true
  emitSeekAt(e.clientX)

  let rafId: number | null = null

  const onMove = (e: MouseEvent) => {
    if (rafId !== null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      emitSeekAt(e.clientX)
    })
  }

  const onUp = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
    isDragging.value = false
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }

  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}
</script>

<template>
  <!-- Overview branch (multi): coverage + playhead tick + seek -->
  <div
    v-if="overview"
    ref="scrollbarRef"
    data-test="overview-strip"
    class="relative h-3 bg-gray-100 cursor-pointer"
    @mousedown="handleOverviewMouseDown"
  >
    <!-- covered rows -->
    <div
      data-test="overview-coverage"
      class="absolute h-full rounded-sm transition-colors"
      :class="isDragging ? 'bg-gray-400' : 'bg-gray-300 hover:bg-gray-400'"
      :style="{ left: overview.leftPercent + '%', width: overview.widthPercent + '%' }"
    />
    <!-- playhead tick -->
    <div
      data-test="overview-playhead"
      class="absolute top-0 h-full w-0.5 bg-red-500"
      :style="{ left: `calc(${overview.playheadPercent}% - 1px)` }"
    />
  </div>

  <!-- Legacy branch (basic): single-window thumb, zero-change -->
  <div v-else ref="scrollbarRef" class="relative h-3 bg-gray-100 cursor-pointer" @mousedown="handleMouseDown">
    <div
      class="absolute h-full rounded-sm transition-colors"
      :class="isDragging ? 'bg-gray-400' : 'bg-gray-300 hover:bg-gray-400'"
      :style="{
        left: metrics.thumbLeft.value + '%',
        width: metrics.thumbWidth.value + '%',
        maxWidth: Math.max(0, 100 - metrics.thumbLeft.value) + '%',
      }"
    />
  </div>
</template>

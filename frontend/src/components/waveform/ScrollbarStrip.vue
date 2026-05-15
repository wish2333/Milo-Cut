<script setup lang="ts">
import { inject, ref } from "vue"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const scrollbarRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const dragOriginX = ref(0)
const dragOriginViewStart = ref(0)

function handleMouseDown(e: MouseEvent) {
  isDragging.value = true
  dragOriginX.value = e.clientX
  dragOriginViewStart.value = metrics.viewStart.value

  const onMove = (e: MouseEvent) => {
    const el = scrollbarRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const deltaPx = e.clientX - dragOriginX.value
    const duration = metrics.duration.value
    if (duration <= 0 || rect.width <= 0) return
    metrics.viewStart.value = dragOriginViewStart.value + deltaPx * duration / rect.width
    metrics.clampViewStart()
  }

  const onUp = () => {
    isDragging.value = false
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }

  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}
</script>

<template>
  <div ref="scrollbarRef" class="relative h-3 bg-gray-100 cursor-pointer" @mousedown="handleMouseDown">
    <div
      class="absolute h-full rounded-sm transition-colors"
      :class="isDragging ? 'bg-gray-400' : 'bg-gray-300 hover:bg-gray-400'"
      :style="{
        left: metrics.thumbLeft.value + '%',
        width: metrics.thumbWidth.value + '%',
      }"
    />
  </div>
</template>

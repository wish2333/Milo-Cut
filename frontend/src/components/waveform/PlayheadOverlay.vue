<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref, watch } from "vue"
import { PLAYBACK_CLOCK_KEY, TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { PlaybackClock } from "@/composables/usePlaybackClock"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

// v3.0.0 M6-3: the playhead is fully imperative. Position arrives from the
// playback clock (raw, non-reactive rAF samples) and is written straight to
// style.transform -- the component has ZERO reactive render dependencies, so
// Vue patch count during playback is 0 (plan acceptance). Zoom/scroll while
// paused repositions via an explicit view watch; nothing else re-renders it.
const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!
const clock = inject<PlaybackClock>(PLAYBACK_CLOCK_KEY)!

const rootRef = ref<HTMLDivElement | null>(null)

let unsubscribe: (() => void) | null = null
let containerWidth = 0
let widthObserver: ResizeObserver | null = null

function positionAt(time: number) {
  const el = rootRef.value
  if (!el) return
  const vd = metrics.viewDuration.value
  if (vd <= 0) return
  const vs = metrics.viewStart.value
  const x = ((time - vs) / vd) * containerWidth
  // Same clamp semantics as the old reactive playheadPercent (0..100%):
  // the head parks at the edge while the playhead is out of view.
  const clamped = Math.max(0, Math.min(containerWidth, x))
  el.style.transform = `translate3d(${clamped}px, 0, 0)`
}

function syncNow() {
  positionAt(clock.getTime())
}

function measureWidth() {
  const container = metrics.containerRef.value
  containerWidth = container ? container.clientWidth : 0
  syncNow()
}

onMounted(() => {
  measureWidth()
  if (typeof ResizeObserver !== "undefined") {
    widthObserver = new ResizeObserver(() => measureWidth())
    const container = metrics.containerRef.value
    if (container) widthObserver.observe(container)
  }
  unsubscribe = clock.subscribe(positionAt)
  watch([metrics.viewStart, metrics.viewDuration], syncNow)
})

onUnmounted(() => {
  unsubscribe?.()
  unsubscribe = null
  widthObserver?.disconnect()
  widthObserver = null
})
</script>

<template>
  <div
    ref="rootRef"
    class="absolute inset-y-0 left-0 w-0.5 bg-red-500 will-change-transform"
  >
    <div
      class="absolute -top-0.5 -left-1 h-2 w-2.5 bg-red-500"
      style="clip-path: polygon(0 0, 100% 0, 50% 100%)"
    />
  </div>
</template>

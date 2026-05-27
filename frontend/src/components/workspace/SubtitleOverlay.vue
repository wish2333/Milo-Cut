<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue"
import type { Segment } from "@/types/project"

const props = defineProps<{
  segments: Segment[]
  videoRef: HTMLVideoElement | null
}>()

const currentText = ref("")
let rafId: number | null = null
let cursor = 0

function findCurrentSubtitle(time: number): string {
  const segs = props.segments
  if (segs.length === 0) return ""

  // Fast path: check cursor position (99% of frames hit here)
  const cur = segs[cursor]
  if (cur && cur.type === "subtitle" && time >= cur.start && time <= cur.end) {
    return cur.text
  }

  // Check next segment (normal forward playback)
  const next = segs[cursor + 1]
  if (next && next.type === "subtitle" && time >= next.start && time <= next.end) {
    cursor++
    return next.text
  }

  // Seek/jump: binary search for subtitle segment
  let lo = 0
  let hi = segs.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1
    const s = segs[mid]
    if (s.type !== "subtitle") {
      lo = mid + 1
      continue
    }
    if (time < s.start) {
      hi = mid - 1
    } else if (time > s.end) {
      lo = mid + 1
    } else {
      cursor = mid
      return s.text
    }
  }

  cursor = Math.max(0, lo)
  return ""
}

function tick() {
  if (!props.videoRef) return
  currentText.value = findCurrentSubtitle(props.videoRef.currentTime)
  rafId = requestAnimationFrame(tick)
}

function startTracking() {
  if (rafId) return
  tick()
}

function stopTracking() {
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
}

watch(() => props.videoRef, (video, _old, onCleanup) => {
  if (!video) return
  video.addEventListener("play", startTracking)
  video.addEventListener("pause", stopTracking)
  video.addEventListener("loadeddata", () => { if (!video.paused) startTracking() })
  if (!video.paused) startTracking()

  onCleanup(() => {
    stopTracking()
    video.removeEventListener("play", startTracking)
    video.removeEventListener("pause", stopTracking)
  })
}, { immediate: true })

// Reset cursor on segment change
watch(() => props.segments, () => {
  cursor = 0
})

onUnmounted(() => {
  stopTracking()
})
</script>

<template>
  <div
    v-if="currentText"
    class="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-black/70 text-white text-sm rounded max-w-[80%] text-center pointer-events-none"
  >
    {{ currentText }}
  </div>
</template>

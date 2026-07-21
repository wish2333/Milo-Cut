<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from "vue"
import type { Segment } from "@/types/project"
import { buildSubtitleIndex, findSubtitleAtTime } from "@/utils/editedPlayback"

const props = defineProps<{
  segments: Segment[]
  videoRef: HTMLVideoElement | null
}>()

const currentText = ref("")
let rafId: number | null = null

const subtitleSegments = computed(() => buildSubtitleIndex(props.segments))

function findCurrentSubtitle(time: number): string {
  return findSubtitleAtTime(subtitleSegments.value, time)?.text ?? ""
}

function tick() {
  if (!props.videoRef) return
  currentText.value = findCurrentSubtitle(props.videoRef.currentTime)
  rafId = requestAnimationFrame(tick)
}

function updateOnce() {
  if (!props.videoRef) return
  currentText.value = findCurrentSubtitle(props.videoRef.currentTime)
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
  // v2.3.2 stage 3: seeked/timeupdate keep subtitle text correct when
  // the video is paused (RAF is off) or when the browser throttles RAF.
  video.addEventListener("seeked", updateOnce)
  video.addEventListener("timeupdate", updateOnce)
  video.addEventListener("loadeddata", () => { if (!video.paused) startTracking() })
  if (!video.paused) startTracking()

  onCleanup(() => {
    stopTracking()
    video.removeEventListener("play", startTracking)
    video.removeEventListener("pause", stopTracking)
    video.removeEventListener("seeked", updateOnce)
    video.removeEventListener("timeupdate", updateOnce)
  })
}, { immediate: true })

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

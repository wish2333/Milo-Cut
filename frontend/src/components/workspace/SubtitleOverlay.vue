<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from "vue"
import type { Segment, SubtitleTrack, TrackBinding } from "@/types/project"
import { buildSubtitleIndex, findSubtitleAtTime } from "@/utils/editedPlayback"

const props = withDefaults(
  defineProps<{
    segments: Segment[]
    videoRef: HTMLVideoElement | null
    /** v3.0.1 M6-2: extension tracks + bindings for the secondary line. */
    secondary?: { tracks: SubtitleTrack[]; bindings: TrackBinding[] } | null
    /** Product setting (settings.json show_secondary_subtitle). */
    showSecondary?: boolean
  }>(),
  {
    secondary: null,
    showSecondary: true,
  },
)

const currentText = ref("")
const currentSecondaryText = ref("")
let rafId: number | null = null

const subtitleSegments = computed(() => buildSubtitleIndex(props.segments))

// v3.0.1 M6-2: main-segment -> bound extension text (R10.1: only bound
// segments show a secondary line; unbound extension segments never do).
const secondaryByMainId = computed(() => {
  const map = new Map<string, string>()
  if (!props.secondary) return map
  const extText = new Map<string, string>()
  for (const t of props.secondary.tracks) {
    for (const s of t.segments) extText.set(s.id, s.text)
  }
  for (const b of props.secondary.bindings) {
    const text = extText.get(b.extension_segment_id)
    if (text && !map.has(b.main_segment_id)) {
      map.set(b.main_segment_id, text)
    }
  }
  return map
})

function resolveAt(time: number): { main: string; secondary: string } {
  const hit = findSubtitleAtTime(subtitleSegments.value, time)
  const main = hit?.text ?? ""
  const secondary = main ? (secondaryByMainId.value.get(hit!.id) ?? "") : ""
  return { main, secondary }
}

function tick() {
  if (!props.videoRef) return
  const r = resolveAt(props.videoRef.currentTime)
  currentText.value = r.main
  currentSecondaryText.value = props.showSecondary ? r.secondary : ""
  rafId = requestAnimationFrame(tick)
}

function updateOnce() {
  if (!props.videoRef) return
  const r = resolveAt(props.videoRef.currentTime)
  currentText.value = r.main
  currentSecondaryText.value = props.showSecondary ? r.secondary : ""
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

// Setting flips re-evaluate immediately even while paused.
watch(() => props.showSecondary, updateOnce)
watch(() => props.secondary, updateOnce, { deep: true })

onUnmounted(() => {
  stopTracking()
})
</script>

<template>
  <div
    v-if="currentText"
    class="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-black/70 text-white text-sm rounded max-w-[80%] text-center pointer-events-none"
  >
    <div>{{ currentText }}</div>
    <!-- v3.0.1 M6-2: secondary line -- smaller + dimmed, distinguishable
         from the main subtitle (PRD R10.2) -->
    <div
      v-if="showSecondary && currentSecondaryText"
      class="mt-0.5 text-xs text-white/70"
      data-test="secondary-subtitle"
    >
      {{ currentSecondaryText }}
    </div>
  </div>
</template>

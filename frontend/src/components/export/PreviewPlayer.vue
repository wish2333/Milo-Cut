<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue"
import { call } from "@/bridge"
import type { EditDecision } from "@/types/project"

const props = defineProps<{
  mediaPath: string | null
  proxyPath: string | null
  edits: EditDecision[]
  duration: number
}>()

const emit = defineEmits<{
  "time-update": [time: number]
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const videoDuration = ref(0)
const videoSrc = ref("")
const volume = ref(0.75)
const isMuted = ref(false)
let rafId: number | null = null

const deleteRanges = computed(() => {
  return props.edits
    .filter(e => e.status === "confirmed" && e.action === "delete")
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})

async function loadVideoUrl() {
  const path = props.proxyPath || props.mediaPath
  if (!path) {
    videoSrc.value = ""
    return
  }
  try {
    const res = await call<{ url: string; port: number }>("get_video_url", path)
    if (res.success && res.data) {
      videoSrc.value = res.data.url
    }
  } catch {
    videoSrc.value = ""
  }
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

function togglePlay() {
  if (!videoRef.value) return
  if (isPlaying.value) {
    videoRef.value.pause()
  } else {
    videoRef.value.play()
  }
}

function toggleMute() {
  if (!videoRef.value) return
  isMuted.value = !isMuted.value
  videoRef.value.muted = isMuted.value
}

function setVolume(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  volume.value = val
  if (videoRef.value) {
    videoRef.value.volume = val
    if (val > 0 && isMuted.value) {
      isMuted.value = false
      videoRef.value.muted = false
    }
  }
}

function seekToPosition(e: MouseEvent) {
  if (!videoRef.value || !videoDuration.value) return
  const target = e.currentTarget as HTMLElement
  const ratio = e.offsetX / target.clientWidth
  videoRef.value.currentTime = ratio * videoDuration.value
}

function checkSkip(time: number): boolean {
  for (const range of deleteRanges.value) {
    if (time >= range.start && time < range.end) {
      videoRef.value!.currentTime = range.end
      return true
    }
  }
  return false
}

function animationLoop() {
  if (videoRef.value && !videoRef.value.paused) {
    const time = videoRef.value.currentTime
    if (!checkSkip(time)) {
      currentTime.value = time
      emit("time-update", time)
    }
  }
  rafId = requestAnimationFrame(animationLoop)
}

function onTimeUpdate() {
  if (videoRef.value) {
    currentTime.value = videoRef.value.currentTime
  }
}

function onLoadedMetadata() {
  if (videoRef.value) {
    videoDuration.value = videoRef.value.duration
    videoRef.value.volume = volume.value
  }
}

function onPlay() {
  isPlaying.value = true
}

function onPause() {
  isPlaying.value = false
}

function onSeeked() {
  if (videoRef.value && !videoRef.value.paused) {
    checkSkip(videoRef.value.currentTime)
  }
}

onMounted(() => {
  rafId = requestAnimationFrame(animationLoop)
  loadVideoUrl()
})

onUnmounted(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
  }
})

watch(() => [props.mediaPath, props.proxyPath], () => {
  loadVideoUrl()
})
</script>

<template>
  <div class="relative w-full h-full flex flex-col bg-black">
    <!-- Video element -->
    <div class="flex-1 flex items-center justify-center overflow-hidden">
      <video
        v-if="videoSrc"
        ref="videoRef"
        :src="videoSrc"
        class="max-w-full max-h-full"
        @timeupdate="onTimeUpdate"
        @loadedmetadata="onLoadedMetadata"
        @play="onPlay"
        @pause="onPause"
        @seeked="onSeeked"
      />
      <div v-else class="text-center">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        <p class="mt-2 text-sm text-gray-400">无媒体文件</p>
      </div>
    </div>

    <!-- Controls -->
    <div class="bg-gray-900 px-4 py-2">
      <!-- Progress bar -->
      <div
        class="relative h-1 bg-gray-700 rounded-full mb-2 cursor-pointer"
        @click="seekToPosition"
      >
        <div
          class="absolute h-full bg-blue-500 rounded-full"
          :style="{ width: `${videoDuration ? (currentTime / videoDuration) * 100 : 0}%` }"
        />
        <!-- Delete ranges overlay -->
        <div
          v-for="(range, i) in deleteRanges"
          :key="i"
          class="absolute h-full bg-red-500 opacity-50"
          :style="{
            left: `${videoDuration ? (range.start / videoDuration) * 100 : 0}%`,
            width: `${videoDuration ? ((range.end - range.start) / videoDuration) * 100 : 0}%`,
          }"
        />
      </div>

      <!-- Buttons -->
      <div class="flex items-center gap-3">
        <button
          class="text-white hover:text-gray-300 transition-colors"
          @click="togglePlay"
        >
          <svg v-if="isPlaying" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </button>

        <span class="text-sm text-gray-400 font-mono">
          {{ formatTime(currentTime) }} / {{ formatTime(videoDuration) }}
        </span>

        <div class="flex-1" />

        <!-- Volume control -->
        <button
          class="text-gray-400 hover:text-white transition-colors"
          @click="toggleMute"
        >
          <svg v-if="isMuted || volume === 0" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /><path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
          <svg v-else-if="volume < 0.5" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
        </button>
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          :value="volume"
          class="w-20 h-1 accent-blue-500 cursor-pointer"
          @input="setVolume"
        />

        <span v-if="deleteRanges.length > 0" class="text-xs text-gray-500">
          {{ deleteRanges.length }} 个删除区域
        </span>
      </div>
    </div>
  </div>
</template>

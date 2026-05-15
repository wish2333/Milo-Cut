<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue"
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
const duration = ref(0)
let rafId: number | null = null

const deleteRanges = computed(() => {
  return props.edits
    .filter(e => e.status === "confirmed" && e.action === "delete")
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})

const videoSrc = computed(() => {
  return props.proxyPath || props.mediaPath
})

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

function seek(time: number) {
  if (!videoRef.value) return
  videoRef.value.currentTime = time
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
    duration.value = videoRef.value.duration
  }
}

function onPlay() {
  isPlaying.value = true
}

function onPause() {
  isPlaying.value = false
}

function onSeeked() {
  // Re-check after seek to handle edge cases
  if (videoRef.value && !videoRef.value.paused) {
    checkSkip(videoRef.value.currentTime)
  }
}

onMounted(() => {
  rafId = requestAnimationFrame(animationLoop)
})

onUnmounted(() => {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
  }
})

watch(() => props.mediaPath, () => {
  if (videoRef.value) {
    videoRef.value.load()
  }
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
      <div class="relative h-1 bg-gray-700 rounded-full mb-2 cursor-pointer" @click="seek($event.offsetX / $event.currentTarget.clientWidth * duration)">
        <div
          class="absolute h-full bg-blue-500 rounded-full"
          :style="{ width: `${(currentTime / duration) * 100}%` }"
        />
        <!-- Delete ranges overlay -->
        <div
          v-for="(range, i) in deleteRanges"
          :key="i"
          class="absolute h-full bg-red-500 opacity-50"
          :style="{
            left: `${(range.start / duration) * 100}%`,
            width: `${((range.end - range.start) / duration) * 100}%`,
          }"
        />
      </div>

      <!-- Buttons -->
      <div class="flex items-center gap-4">
        <button
          class="text-white hover:text-gray-300 transition-colors"
          @click="togglePlay"
        >
          <svg v-if="isPlaying" xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" /><path stroke-linecap="round" stroke-linejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
        </button>

        <span class="text-sm text-gray-400 font-mono">
          {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
        </span>

        <div class="flex-1" />

        <span v-if="deleteRanges.length > 0" class="text-xs text-gray-500">
          {{ deleteRanges.length }} 个删除区域
        </span>
      </div>
    </div>
  </div>
</template>

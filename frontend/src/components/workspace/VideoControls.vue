<script setup lang="ts">
import { ref, computed, onUnmounted } from "vue"
import { formatTime } from "@/utils/format"

const props = defineProps<{
  currentTime: number
  duration: number
  paused: boolean
  volume: number
  playbackRate: number
}>()

const emit = defineEmits<{
  "update:currentTime": [time: number]
  "update:volume": [vol: number]
  "update:playbackRate": [rate: number]
  "toggle-play": []
  "toggle-fullscreen": []
}>()

// Progress bar interaction
const progressRef = ref<HTMLDivElement | null>(null)
const isSeeking = ref(false)

function getTimeFromEvent(e: MouseEvent): number {
  if (!progressRef.value || props.duration <= 0) return 0
  const rect = progressRef.value.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  return ratio * props.duration
}

function handleProgressMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  isSeeking.value = true
  emit("update:currentTime", getTimeFromEvent(e))
  document.addEventListener("mousemove", handleProgressMouseMove)
  document.addEventListener("mouseup", handleProgressMouseUp)
}

function handleProgressMouseMove(e: MouseEvent) {
  if (!isSeeking.value) return
  emit("update:currentTime", getTimeFromEvent(e))
}

function handleProgressMouseUp() {
  isSeeking.value = false
  document.removeEventListener("mousemove", handleProgressMouseMove)
  document.removeEventListener("mouseup", handleProgressMouseUp)
}

const progressPercent = computed(() => {
  if (props.duration <= 0) return 0
  return (props.currentTime / props.duration) * 100
})

// Volume
const showVolume = ref(false)
const volumeRef = ref<HTMLDivElement | null>(null)
const isAdjustingVolume = ref(false)
let volumeHideTimer: ReturnType<typeof setTimeout> | null = null

function showVolumePopup() {
  if (volumeHideTimer) {
    clearTimeout(volumeHideTimer)
    volumeHideTimer = null
  }
  showVolume.value = true
}

function hideVolumePopup() {
  if (volumeHideTimer) clearTimeout(volumeHideTimer)
  volumeHideTimer = setTimeout(() => {
    showVolume.value = false
    volumeHideTimer = null
  }, 300)
}

function handleVolumeMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  isAdjustingVolume.value = true
  emit("update:volume", getVolumeFromEvent(e))
  document.addEventListener("mousemove", handleVolumeMouseMove)
  document.addEventListener("mouseup", handleVolumeMouseUp)
}

function handleVolumeMouseMove(e: MouseEvent) {
  if (!isAdjustingVolume.value) return
  emit("update:volume", getVolumeFromEvent(e))
}

function handleVolumeMouseUp() {
  isAdjustingVolume.value = false
  document.removeEventListener("mousemove", handleVolumeMouseMove)
  document.removeEventListener("mouseup", handleVolumeMouseUp)
}

function getVolumeFromEvent(e: MouseEvent): number {
  if (!volumeRef.value) return 0
  const rect = volumeRef.value.getBoundingClientRect()
  return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
}

// Playback speed
const speeds = [0.5, 0.75, 1, 1.25, 1.5, 2]
const showSpeedMenu = ref(false)

function setSpeed(rate: number) {
  emit("update:playbackRate", rate)
  showSpeedMenu.value = false
}

// Keyboard shortcuts (space is handled globally in WorkspacePage)
function handleKeydown(e: KeyboardEvent) {
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
  switch (e.key) {
    case "ArrowLeft":
      e.preventDefault()
      emit("update:currentTime", Math.max(0, props.currentTime - 5))
      break
    case "ArrowRight":
      e.preventDefault()
      emit("update:currentTime", Math.min(props.duration, props.currentTime + 5))
      break
    case "ArrowUp":
      e.preventDefault()
      emit("update:volume", Math.min(1, props.volume + 0.1))
      break
    case "ArrowDown":
      e.preventDefault()
      emit("update:volume", Math.max(0, props.volume - 0.1))
      break
    case "f":
      e.preventDefault()
      emit("toggle-fullscreen")
      break
    case "m":
      e.preventDefault()
      emit("update:volume", props.volume > 0 ? 0 : 0.75)
      break
  }
}

// Volume icon
const volumeIcon = computed(() => {
  if (props.volume === 0) return "muted"
  if (props.volume < 0.5) return "low"
  return "high"
})

onUnmounted(() => {
  if (volumeHideTimer) clearTimeout(volumeHideTimer)
  document.removeEventListener("mousemove", handleProgressMouseMove)
  document.removeEventListener("mouseup", handleProgressMouseUp)
  document.removeEventListener("mousemove", handleVolumeMouseMove)
  document.removeEventListener("mouseup", handleVolumeMouseUp)
})
</script>

<template>
  <div
    class="flex items-center gap-2 bg-gray-900/95 px-3 py-1.5 text-white text-xs"
    @keydown="handleKeydown"
    tabindex="0"
  >
    <!-- Play/Pause -->
    <button
      class="flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 transition-colors"
      :title="paused ? 'Play (Space)' : 'Pause (Space)'"
      @click="emit('toggle-play')"
    >
      <svg v-if="paused" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
        <path d="M8 5v14l11-7z" />
      </svg>
      <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
        <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
      </svg>
    </button>

    <!-- Skip back 5s -->
    <button
      class="flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 transition-colors"
      title="Back 5s (Left Arrow)"
      @click="emit('update:currentTime', Math.max(0, currentTime - 5))"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M12.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0019 16V8a1 1 0 00-1.6-.8l-5.333 4zM4.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0011 16V8a1 1 0 00-1.6-.8l-5.334 4z" />
      </svg>
    </button>

    <!-- Skip forward 5s -->
    <button
      class="flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 transition-colors"
      title="Forward 5s (Right Arrow)"
      @click="emit('update:currentTime', Math.min(duration, currentTime + 5))"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M11.933 12.8a1 1 0 000-1.6L6.6 7.2A1 1 0 005 8v8a1 1 0 001.6.8l5.333-4zM19.933 12.8a1 1 0 000-1.6l-5.333-4A1 1 0 0013 8v8a1 1 0 001.6.8l5.333-4z" />
      </svg>
    </button>

    <!-- Time display -->
    <span class="font-mono text-[11px] text-gray-300 w-24 text-center tabular-nums">
      {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
    </span>

    <!-- Progress bar -->
    <div
      ref="progressRef"
      class="flex-1 h-5 flex items-center cursor-pointer group"
      @mousedown="handleProgressMouseDown"
    >
      <div class="relative w-full h-1 group-hover:h-1.5 bg-gray-600 rounded-full transition-all">
        <div
          class="absolute top-0 left-0 h-full bg-blue-500 rounded-full transition-none"
          :style="{ width: progressPercent + '%' }"
        />
        <div
          class="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-blue-400 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
          :style="{ left: progressPercent + '%', transform: 'translate(-50%, -50%)' }"
        />
      </div>
    </div>

    <!-- Volume -->
    <div class="relative flex items-center">
      <button
        class="flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 transition-colors"
        :title="volume > 0 ? 'Mute (M)' : 'Unmute (M)'"
        @click="emit('update:volume', volume > 0 ? 0 : 0.75)"
        @mouseenter="showVolumePopup"
        @mouseleave="hideVolumePopup"
      >
        <!-- Muted -->
        <svg v-if="volumeIcon === 'muted'" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
        </svg>
        <!-- Low -->
        <svg v-else-if="volumeIcon === 'low'" xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072" />
        </svg>
        <!-- High -->
        <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" />
          <path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728" />
        </svg>
      </button>
      <div
        v-show="showVolume"
        class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 p-2 bg-gray-800 rounded shadow-lg"
        @mouseenter="showVolumePopup"
        @mouseleave="hideVolumePopup"
      >
        <div
          ref="volumeRef"
          class="w-20 h-2 bg-gray-600 rounded-full cursor-pointer"
          @mousedown="handleVolumeMouseDown"
        >
          <div
            class="h-full bg-blue-500 rounded-full"
            :style="{ width: (volume * 100) + '%' }"
          />
        </div>
      </div>
    </div>

    <!-- Playback speed -->
    <div class="relative">
      <button
        class="px-1.5 py-0.5 rounded hover:bg-white/10 transition-colors font-mono text-[10px]"
        title="Playback speed"
        @click="showSpeedMenu = !showSpeedMenu"
      >
        {{ playbackRate }}x
      </button>
      <div
        v-if="showSpeedMenu"
        class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 py-1 bg-gray-800 rounded shadow-lg"
      >
        <button
          v-for="speed in speeds"
          :key="speed"
          class="block w-full px-3 py-1 text-left hover:bg-white/10 transition-colors whitespace-nowrap"
          :class="{ 'text-blue-400': playbackRate === speed }"
          @click="setSpeed(speed)"
        >
          {{ speed }}x
        </button>
      </div>
    </div>

    <!-- Fullscreen -->
    <button
      class="flex items-center justify-center w-7 h-7 rounded hover:bg-white/10 transition-colors"
      title="Fullscreen (F)"
      @click="emit('toggle-fullscreen')"
    >
      <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import type { SubtitleTrack } from "@/types/project"

/**
 * v3.0.0 M11-2 MVP: read-only extension-track lane at the bottom of the
 * Timeline. Collapsible; rows display original timestamps + text and seek
 * on click. No editing surface -- bindings are write-only this version.
 */
defineProps<{
  tracks: SubtitleTrack[]
}>()

const emit = defineEmits<{
  seek: [time: number]
}>()

const open = ref(true)

function formatTime(t: number): string {
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return `${m}:${s.toFixed(1).padStart(4, "0")}`
}
</script>

<template>
  <div v-if="tracks.length > 0" class="border-t border-hairline" data-test="track-lane">
    <button
      class="flex w-full items-center gap-2 px-4 py-1.5 text-xs text-ink-muted transition-colors hover:bg-parchment"
      :title="open ? '收起副轨' : '展开副轨'"
      @click="open = !open"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 transition-transform"
        :class="open ? 'rotate-90' : ''" fill="none" viewBox="0 0 24 24"
        stroke="currentColor" stroke-width="2"
      >
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
      </svg>
      <span class="font-semibold">副轨字幕 ({{ tracks.length }})</span>
      <span
        v-for="track in tracks" :key="track.id"
        class="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] text-primary"
      >
        {{ track.name || track.id }}{{ track.language ? ` · ${track.language}` : '' }}
      </span>
      <span class="ml-auto text-[10px]">只读</span>
    </button>

    <div v-if="open" class="max-h-40 overflow-y-auto">
      <div v-for="track in tracks" :key="track.id" class="px-4 pb-2">
        <div
          v-for="seg in track.segments" :key="seg.id"
          class="flex cursor-pointer items-baseline gap-3 rounded px-2 py-1 text-xs transition-colors hover:bg-parchment"
          :data-test="`track-row-${seg.id}`"
          @click="emit('seek', seg.start)"
        >
          <span class="shrink-0 font-mono text-[10px] text-ink-muted">
            {{ formatTime(seg.start) }} - {{ formatTime(seg.end) }}
          </span>
          <span class="truncate text-ink">{{ seg.text }}</span>
        </div>
        <p v-if="track.segments.length === 0" class="px-2 py-1 text-xs text-ink-muted">
          空轨道
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { inject } from "vue"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const emit = defineEmits<{
  seek: [time: number]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

function handleStripClick(e: MouseEvent) {
  const time = metrics.getTimeFromX(e.clientX)
  emit("seek", time)
}
</script>

<template>
  <div class="absolute inset-x-0 top-0 h-6 cursor-pointer" @click="handleStripClick">
    <div
      v-for="mark in metrics.timeMarks.value"
      :key="mark.time"
      class="absolute top-0 flex flex-col items-center"
      :style="{ left: mark.percent + '%' }"
    >
      <div class="h-2 w-px bg-gray-300" />
      <span class="whitespace-nowrap text-[10px] leading-none text-gray-400 select-none">
        {{ mark.label }}
      </span>
    </div>
  </div>
</template>

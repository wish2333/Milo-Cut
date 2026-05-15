<script setup lang="ts">
import { inject } from "vue"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!
</script>

<template>
  <div
    class="absolute inset-y-0 w-0.5 bg-red-500"
    :style="{ left: metrics.playheadPercent.value + '%' }"
  >
    <div
      class="absolute -top-0.5 -left-1 h-2 w-2.5 bg-red-500"
      style="clip-path: polygon(0 0, 100% 0, 50% 100%)"
    />
  </div>
</template>

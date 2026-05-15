<script setup lang="ts">
import { toRef, provide, onMounted, onUnmounted } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { useTimelineMetrics, type TimelineMetrics } from "@/composables/useTimelineMetrics"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import WaveformCanvas from "./WaveformCanvas.vue"
import TimeMarksLayer from "./TimeMarksLayer.vue"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"
import PlayheadOverlay from "./PlayheadOverlay.vue"
import ScrollbarStrip from "./ScrollbarStrip.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  duration: number
  currentTime: number
  waveformPath?: string
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
}>()

const emit = defineEmits<{
  seek: [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
}>()

const durationRef = toRef(props, "duration")
const currentTimeRef = toRef(props, "currentTime")
const metrics = useTimelineMetrics(durationRef, currentTimeRef)

provide<TimelineMetrics>(TIMELINE_METRICS_KEY, metrics)

let layerEl: HTMLElement | null = null

function setLayerRef(el: unknown) {
  const htmlEl = el instanceof HTMLElement ? el : null
  layerEl = htmlEl
  metrics.containerRef.value = htmlEl
}

onMounted(() => {
  if (layerEl) {
    layerEl.addEventListener("wheel", metrics.handleWheel, { passive: false })
  }
})

onUnmounted(() => {
  if (layerEl) {
    layerEl.removeEventListener("wheel", metrics.handleWheel)
  }
})

function handleSeek(time: number) {
  emit("seek", time)
}

function handleSelectRange(start: number, end: number) {
  emit("select-range", start, end)
}

function handleAddSegment(start: number, end: number) {
  emit("add-segment", start, end)
}

function handleDeleteSegment(segmentId: string) {
  emit("delete-segment", segmentId)
}
</script>

<template>
  <div class="flex flex-col">
    <!-- Controls bar -->
    <div class="flex h-6 items-center gap-2 border-b border-gray-200 px-2 text-xs text-gray-500">
      <span>{{ metrics.viewStart.value.toFixed(1) }}s</span>
      <span class="flex-1 text-center">{{ metrics.viewDuration.value.toFixed(1) }}s window</span>
      <span>{{ metrics.viewEnd.value.toFixed(1) }}s</span>
    </div>

    <!-- Layer container -->
    <div
      :ref="setLayerRef"
      class="relative h-28 overflow-hidden"
    >
      <WaveformCanvas
        :segments="segments"
        :waveform-path="waveformPath"
        :duration="duration"
        style="z-index: 0; pointer-events: none"
      />
      <TimeMarksLayer
        style="z-index: 1"
        @seek="handleSeek"
      />
      <SegmentBlocksLayer
        :segments="segments"
        :edits="edits"
        :update-time="updateTime"
        style="z-index: 2"
        @select-range="handleSelectRange"
        @add-segment="handleAddSegment"
        @delete-segment="handleDeleteSegment"
      />
      <PlayheadOverlay style="z-index: 10; pointer-events: none" />
    </div>

    <!-- Scrollbar -->
    <ScrollbarStrip />
  </div>
</template>

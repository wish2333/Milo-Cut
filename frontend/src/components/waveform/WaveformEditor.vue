<script setup lang="ts">
import { toRef, provide, ref, computed, onMounted, onUnmounted } from "vue"
import type { Segment, EditDecision, SubtitleTrack } from "@/types/project"
import { useTimelineMetrics, type TimelineMetrics } from "@/composables/useTimelineMetrics"
import {
  useLaneLayout,
  computeLaneLayout,
  LANE_COLLAPSED_HEIGHT,
  LANE_PRESET_HEIGHTS,
} from "@/composables/useLaneLayout"
import { createRafScheduler } from "@/utils/rafScheduler"
import { formatTimeShort } from "@/utils/format"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import WaveformCanvas from "./WaveformCanvas.vue"
import TimeMarksLayer from "./TimeMarksLayer.vue"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"
import PlayheadOverlay from "./PlayheadOverlay.vue"
import ScrollbarStrip from "./ScrollbarStrip.vue"
import TrackLane from "@/components/workspace/TrackLane.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  duration: number
  currentTime: number
  waveformPath?: string
  demoMode?: boolean
  /** v3.0.0 M11-2: extension tracks for the stacked lanes (v3.0.1 M4-4). */
  tracks?: SubtitleTrack[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  /** v3.0.1 M5-2: extension-track trim (useTrackEdit in WorkspacePage). */
  updateTrackTime?: (trackId: string, segmentId: string, field: "start" | "end", value: number) => void
  /** v2.1.1 A-03: full-text edit mode — blocks structural ops */
  globalEditMode?: boolean
  /** v2.1.1 A-03: multi-select mode — move pointer without playing */
  selectionMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "set-time": [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
  "regenerate-waveform": []
  "split-segment": [segmentId: string, position: number]
  toast: [msg: string]
}>()

const durationRef = toRef(props, "duration")
const currentTimeRef = toRef(props, "currentTime")
const metrics = useTimelineMetrics(durationRef, currentTimeRef)

provide<TimelineMetrics>(TIMELINE_METRICS_KEY, metrics)

// -- v3.0.1 M4-4: stacked-timeline orchestration --------------------------
//
// Content-driven heights: the main track keeps its h-28 (112px) height and
// lanes stack below at their preset heights, so the WorkspacePage layout
// flows naturally (SPEC M4-4 squeeze rules remain available in
// computeLaneLayout for fixed-height containers; in this mode the input
// height equals desired height, so compression never triggers).
const MAIN_TRACK_HEIGHT = 112

const tracksRef = computed(() => props.tracks ?? [])
const laneCtl = useLaneLayout(() => tracksRef.value.map(t => t.id))

const laneLayout = computed(() => {
  const tracks = tracksRef.value
  const desired = tracks.reduce((sum, t) => {
    if (laneCtl.state.value.hidden[t.id]) return sum
    return (
      sum +
      (laneCtl.state.value.collapsed[t.id]
        ? LANE_COLLAPSED_HEIGHT
        : LANE_PRESET_HEIGHTS[laneCtl.state.value.preset[t.id] ?? "md"])
    )
  }, 0)
  return computeLaneLayout(
    MAIN_TRACK_HEIGHT + desired,
    tracks.map(t => t.id),
    laneCtl.state.value,
  )
})

const stackHeight = computed(() => MAIN_TRACK_HEIGHT + laneLayout.value.totalLanesHeight)

const trackById = computed(() => new Map(tracksRef.value.map(t => [t.id, t])))
const trackOverflow = computed(() => tracksRef.value.length > 4)

// -- v3.0.0 M6-2: hover seek preview (unchanged, scoped to the main track) --
const hoverLineRef = ref<HTMLElement | null>(null)
const hoverLabelRef = ref<HTMLElement | null>(null)
let pendingHover: { x: number; t: number } | null = null
let containerRect: DOMRect | null = null

const hoverScheduler = createRafScheduler(applyHover)

function applyHover() {
  const line = hoverLineRef.value
  if (!line) return
  if (!pendingHover) {
    line.style.opacity = "0"
    return
  }
  const { x, t } = pendingHover
  pendingHover = null
  line.style.opacity = "1"
  line.style.transform = `translate3d(${x}px, 0, 0)`
  if (hoverLabelRef.value) {
    hoverLabelRef.value.textContent = formatTimeShort(t)
  }
}

function handleHoverMove(e: PointerEvent) {
  const rect = containerRect
  if (!rect || rect.width <= 0) return
  const x = e.clientX - rect.left
  if (x < 0 || x > rect.width) return
  pendingHover = {
    x,
    t: metrics.viewStart.value + (x / rect.width) * metrics.viewDuration.value,
  }
  hoverScheduler.schedule()
}

function handleHoverLeave() {
  pendingHover = null
  hoverScheduler.schedule()
}

let hoverResizeObserver: ResizeObserver | null = null

let layerEl: HTMLElement | null = null
let stackEl: HTMLElement | null = null

function setLayerRef(el: unknown) {
  const htmlEl = el instanceof HTMLElement ? el : null
  layerEl = htmlEl
  metrics.containerRef.value = htmlEl
  if (htmlEl) containerRect = htmlEl.getBoundingClientRect()
}

function setStackRef(el: unknown) {
  stackEl = el instanceof HTMLElement ? el : null
}

onMounted(() => {
  // v3.0.1 M4-4: wheel zoom/scroll moves to the WHOLE stack so lanes share
  // the main-track navigation (one listener -- no double handling).
  if (stackEl) {
    stackEl.addEventListener("wheel", metrics.handleWheel, { passive: false })
  }
  if (layerEl) {
    containerRect = layerEl.getBoundingClientRect()
    if (typeof ResizeObserver !== "undefined") {
      hoverResizeObserver = new ResizeObserver(() => {
        containerRect = layerEl ? layerEl.getBoundingClientRect() : null
      })
      hoverResizeObserver.observe(layerEl)
    }
  }
})

onUnmounted(() => {
  if (stackEl) {
    stackEl.removeEventListener("wheel", metrics.handleWheel)
  }
  hoverScheduler.cancel()
  hoverResizeObserver?.disconnect()
  hoverResizeObserver = null
  laneCtl.cleanup()
})

function handleSeek(time: number) {
  // v2.1.1 A-03: globalEditMode blocks time-axis clicks entirely
  if (props.globalEditMode) return
  // selectionMode: move pointer without playing
  if (props.selectionMode) {
    emit("set-time", time)
    return
  }
  // normal mode: seek and play
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

function handleSeekSegment(segment: Segment) {
  // v2.1.1 A-03: same logic as handleSeek
  if (props.globalEditMode) return
  if (props.selectionMode) {
    emit("set-time", segment.start)
    return
  }
  emit("seek-segment", segment)
}

function handleSplitSegment(segmentId: string, position: number) {
  emit("split-segment", segmentId, position)
}

</script>

<template>
  <div class="flex flex-col">
    <!-- Controls bar -->
    <div class="flex h-6 items-center gap-2 border-b border-gray-200 px-2 text-xs text-gray-500">
      <button
        class="shrink-0 rounded bg-gray-200 px-2 py-0.5 text-[11px] leading-none text-gray-600 hover:bg-gray-300 transition-colors"
        title="Regenerate waveform"
        @click="emit('regenerate-waveform')"
      >
        Regen
      </button>
      <span>{{ metrics.viewStart.value.toFixed(1) }}s</span>
      <span class="flex-1 text-center">{{ metrics.viewDuration.value.toFixed(1) }}s window</span>
      <span>{{ metrics.viewEnd.value.toFixed(1) }}s</span>
    </div>

    <!-- Stacked surface: main track + N extension lanes + single playhead -->
    <div
      :ref="setStackRef"
      data-test="timeline-stack"
      class="relative overflow-hidden"
      :style="{ height: stackHeight + 'px' }"
    >
      <!-- Main track area (z0-z10 layering unchanged) -->
      <div
        :ref="setLayerRef"
        data-test="waveform-layer"
        class="relative overflow-hidden"
        :style="{ height: laneLayout.mainTrackHeight + 'px' }"
        @pointermove="handleHoverMove"
        @pointerleave="handleHoverLeave"
      >
        <WaveformCanvas
          :segments="segments"
          :waveform-path="waveformPath"
          :duration="duration"
          :demo-mode="demoMode"
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
          :current-time="currentTime"
          :duration="duration"
          :global-edit-mode="globalEditMode"
          style="z-index: 2"
          @select-range="handleSelectRange"
          @add-segment="handleAddSegment"
          @delete-segment="handleDeleteSegment"
          @seek-segment="handleSeekSegment"
          @split-segment="handleSplitSegment"
          @set-time="emit('set-time', $event)"
          @toast="emit('toast', $event)"
          @trim-end="emit('toast', '裁剪已应用')"
        />
        <!-- v3.0.0 M6-2: hover seek preview (imperative, pointer-events:none) -->
        <div
          ref="hoverLineRef"
          data-test="hover-preview"
          class="pointer-events-none absolute inset-y-0 left-0 opacity-0"
          style="z-index: 5"
        >
          <div class="h-full w-px bg-ink-muted/60"></div>
          <div
            ref="hoverLabelRef"
            class="absolute left-1 top-6 whitespace-nowrap rounded bg-surface-tile-1 px-1 py-0.5 text-[10px] leading-none text-ink-muted shadow-sm"
          ></div>
        </div>
      </div>

      <!-- Extension lanes (v3.0.1 M4-2/M4-4) -->
      <template v-for="lane in laneLayout.lanes" :key="lane.trackId">
        <TrackLane
          v-if="!lane.hidden && trackById.get(lane.trackId)"
          :track="trackById.get(lane.trackId)!"
          :lane="{ ...lane, top: laneLayout.mainTrackHeight + lane.top }"
          :update-time="
            updateTrackTime
              ? (sid, f, v) => updateTrackTime!(lane.trackId, sid, f, v)
              : undefined
          "
          @seek="(t) => handleSeek(t)"
          @toggle-collapse="laneCtl.toggleCollapse"
        />
      </template>

      <!-- v3.0.1 M4-4: single playhead promoted to the stack surface --
           inset-y-0 spans the main track AND every lane (one owner, red
           line M0-3 / design-spec "promote the owner" rule). -->
      <PlayheadOverlay style="z-index: 10; pointer-events: none" />

      <!-- v3.0.1 R3.4: soft track-count hint (no hard cap) -->
      <div
        v-if="trackOverflow"
        data-test="track-overflow-hint"
        class="absolute bottom-0 right-1 rounded bg-amber-50 px-1 py-px text-[10px] leading-tight text-amber-700"
        style="z-index: 6"
      >
        副轨较多（{{ tracksRef.length }} 条），建议合并或隐藏
      </div>
    </div>

    <!-- Scrollbar -->
    <ScrollbarStrip />
  </div>
</template>

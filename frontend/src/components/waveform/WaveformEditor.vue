<script setup lang="ts">
import { toRef, provide, ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue"
import type { Segment, EditDecision, SubtitleTrack } from "@/types/project"
import { useTimelineMetrics, type TimelineMetrics } from "@/composables/useTimelineMetrics"
import {
  SECONDS_PER_ROW_PRESETS,
  ROW_HEIGHT_PRESETS,
  useRowLayout,
  strideOf,
  lastRowWidthPercent,
} from "@/composables/useRowLayout"
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
import WaveformRow from "./WaveformRow.vue"

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
  attachBasicWheel()
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

// Basic-mode wheel listener lifecycle: the stack unmounts in multi mode,
// so the listener re-attaches when basic mode remounts it (M4-1: the multi
// container uses NATIVE scrolling; the JS wheel family lands in P3-1).
// Defined AFTER the multi-state block (isMulti TDZ) -- see watch below.
function attachBasicWheel() {
  if (stackEl && !isMulti.value) {
    stackEl.addEventListener("wheel", metrics.handleWheel, { passive: false })
  }
}
function detachBasicWheel() {
  if (stackEl) stackEl.removeEventListener("wheel", metrics.handleWheel)
}

onUnmounted(() => {
  detachBasicWheel()
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

// -- v3.0.2 M4-1/M4-2: multi-row timeline branch --------------------------
//
// mode === "basic" renders the v3.0.1 stacked single-window path EXACTLY
// as before (red line M0-1.5). mode === "multi" replaces it with a
// virtualized WaveformRow list driven by useRowLayout. Row preferences
// persist in localStorage only (P6) -- never project.json/patches/undo.

const rowLayout = useRowLayout(durationRef)
const isMulti = computed(() => rowLayout.state.value.mode === "multi")

const sprPresets = SECONDS_PER_ROW_PRESETS
const rowHeightPresets = ROW_HEIGHT_PRESETS

/** Scroll container element (multi mode only). */
let scrollEl: HTMLElement | null = null
let scrollResizeObserver: ResizeObserver | null = null

function setScrollRef(el: unknown) {
  scrollEl = el instanceof HTMLElement ? el : null
  if (scrollEl) {
    rowLayout.viewportHeight.value = scrollEl.clientHeight
    scrollEl.scrollTop = rowLayout.scrollTop.value
    if (typeof ResizeObserver !== "undefined") {
      scrollResizeObserver?.disconnect()
      scrollResizeObserver = new ResizeObserver(() => {
        if (scrollEl) rowLayout.viewportHeight.value = scrollEl.clientHeight
      })
      scrollResizeObserver.observe(scrollEl)
    }
  }
}

// rAF-coalesced scroll -> virtual window recompute (M4-2).
const scrollScheduler = createRafScheduler(() => {
  if (scrollEl) rowLayout.scrollTop.value = scrollEl.scrollTop
})

function handleScroll() {
  scrollScheduler.schedule()
}

// Programmatic scroll writes (revealTime / mode switch / clamp) reflect
// into the container. A write that equals the DOM position is a no-op, so
// user scrolling never fights this watcher in practice (P4-1 adds the
// explicit autoScrollTarget loop suppression for smooth follow).
watch(
  () => rowLayout.scrollTop.value,
  top => {
    if (scrollEl && Math.abs(scrollEl.scrollTop - top) > 0.5) {
      scrollEl.scrollTop = top
    }
  },
)

// Duration shrink (re-open / media change): clamp scrollTop to maxScrollTop.
watch(
  () => rowLayout.maxScrollTop.value,
  max => {
    if (rowLayout.scrollTop.value > max) rowLayout.scrollTop.value = max
  },
)

/**
 * Virtualized row descriptors. The key embeds the spr itself (M4-2):
 * changing the spr preset changes every key -> wholesale row remount
 * (adapters statically capture spr). Keying on the derived start alone is
 * NOT enough -- row 0's start is 0*spr == 0 under every preset, so its
 * key would never change and the stale adapter kept rendering (fixed
 * after beta.1 smoke finding: first row ignored spr changes until
 * scrolled out and back). Changing rowHeight only mutates top/height
 * props -> geometry-only keyed reuse.
 */
const renderedRows = computed(() => {
  if (!isMulti.value) return []
  const spr = rowLayout.state.value.secondsPerRow
  const stride = strideOf(rowLayout.state.value.rowHeight)
  const rows: Array<{ index: number; start: number; top: number; key: string }> = []
  for (let i = rowLayout.visibleRows.value.first; i <= rowLayout.visibleRows.value.last; i++) {
    const start = i * spr
    rows.push({
      index: i,
      start,
      top: i * stride,
      key: `r${i}-${start}@${spr}`,
    })
  }
  return rows
})

/** Beta.1 fixed multi viewport (px); P5-1 replaces it with the draggable divider + persistence. */
const MULTI_VIEWPORT_HEIGHT = 320
const multiViewportHeight = computed(() => MULTI_VIEWPORT_HEIGHT)

/** Controls-bar middle info (beta.1 minimal form; coverage range lands P5-1). */
const rowCountLabel = computed(() => {
  const { first, last } = rowLayout.visibleRows.value
  return `行 ${first + 1}–${last + 1} / 共 ${rowLayout.rowCount.value} 行`
})

/** Last row shrinks to the remaining duration (R4.1). */
function rowWidthPercent(index: number): number {
  const last = rowLayout.rowCount.value - 1
  if (index !== last) return 100
  return lastRowWidthPercent(props.duration, rowLayout.state.value.secondsPerRow)
}

// Mode switch (M6-2 minimal form; follow-state reset/refinement lands P4):
// multi -> reveal the playing row; basic -> the single window keeps its own
// state (v3.0.1 semantics untouched).
watch(isMulti, async multi => {
  if (multi) {
    await nextTick()
    rowLayout.revealTime(props.currentTime, true)
  } else {
    nextTick(attachBasicWheel)
  }
})

onUnmounted(() => {
  scrollResizeObserver?.disconnect()
  scrollResizeObserver = null
  scrollScheduler.cancel()
})

// Multi-mode row event forwarding: the editor owns all navigation/edit
// routing, rows are windowed views (M3-2).
function handleRowSetTime(t: number) {
  emit("set-time", t)
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
      <!-- v3.0.2 M4-1: mode switch (multi rows / basic focus) -->
      <div class="flex shrink-0 overflow-hidden rounded border border-gray-300" data-test="mode-switch">
        <button
          class="px-1.5 py-px text-[11px] leading-none transition-colors"
          :class="isMulti ? 'bg-gray-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          data-test="mode-multi"
          title="Multi-row timeline"
          @click="rowLayout.setMode('multi')"
        >
          多行
        </button>
        <button
          class="px-1.5 py-px text-[11px] leading-none transition-colors"
          :class="!isMulti ? 'bg-gray-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          data-test="mode-basic"
          title="Single-window timeline"
          @click="rowLayout.setMode('basic')"
        >
          聚焦
        </button>
      </div>
      <template v-if="isMulti">
        <select
          class="shrink-0 rounded border border-gray-300 bg-surface px-1 py-0 text-[11px]"
          data-test="spr-select"
          :value="rowLayout.state.value.secondsPerRow"
          title="Seconds per row"
          @change="rowLayout.setSecondsPerRow(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="s in sprPresets" :key="s" :value="s">{{ s }}s/行</option>
        </select>
        <select
          class="shrink-0 rounded border border-gray-300 bg-surface px-1 py-0 text-[11px]"
          data-test="row-height-select"
          :value="rowLayout.state.value.rowHeight"
          title="Row height"
          @change="rowLayout.setRowHeight(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="h in rowHeightPresets" :key="h" :value="h">{{ h }}px</option>
        </select>
        <span class="flex-1 text-center">{{ rowCountLabel }}</span>
      </template>
      <template v-else>
        <span>{{ metrics.viewStart.value.toFixed(1) }}s</span>
        <span class="flex-1 text-center">{{ metrics.viewDuration.value.toFixed(1) }}s window</span>
        <span>{{ metrics.viewEnd.value.toFixed(1) }}s</span>
      </template>
    </div>

    <!-- v3.0.2 M4-1: multi-row virtualized surface -->
    <div
      v-if="isMulti"
      :ref="setScrollRef"
      data-test="multi-scroll"
      class="relative overflow-y-auto overscroll-contain"
      :style="{ height: multiViewportHeight + 'px' }"
      @scroll="handleScroll"
    >
      <div data-test="multi-content" class="relative" :style="{ height: rowLayout.contentHeight.value + 'px' }">
        <WaveformRow
          v-for="row in renderedRows"
          :key="row.key"
          :row-index="row.index"
          :seconds-per-row="rowLayout.state.value.secondsPerRow"
          :top="row.top"
          :row-height="rowLayout.state.value.rowHeight"
          :width-percent="rowWidthPercent(row.index)"
          :duration="duration"
          :current-time="currentTime"
          :segments="segments"
          :edits="edits"
          :waveform-path="waveformPath"
          :demo-mode="demoMode"
          :update-time="updateTime"
          :global-edit-mode="globalEditMode"
          @select-range="handleSelectRange"
          @add-segment="handleAddSegment"
          @delete-segment="handleDeleteSegment"
          @seek-segment="handleSeekSegment"
          @split-segment="handleSplitSegment"
          @set-time="handleRowSetTime"
          @toast="(msg: string) => emit('toast', msg)"
        />
        <!-- Mini-map placeholder (P4-3 implements the mini overview strip) -->
      </div>
    </div>

    <!-- Stacked surface: main track + N extension lanes + single playhead (basic) -->
    <div
      v-else
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

    <!-- Scrollbar (basic mode only; multi gets the mini overview strip in P4-3) -->
    <ScrollbarStrip v-if="!isMulti" />
  </div>
</template>

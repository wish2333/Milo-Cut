<script setup lang="ts">
import { computed, provide, ref } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import type { WaveformPeak } from "@/utils/waveformPeaks"
import { formatTimeShort } from "@/utils/format"
import { createRowMetrics } from "@/composables/rowMetrics"
import type { UseRowDragCaptureReturn, RowEmptyGesture } from "@/composables/useRowDragCapture"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import WaveformCanvas from "./WaveformCanvas.vue"
import TimeMarksLayer from "./TimeMarksLayer.vue"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"
import PlayheadOverlay from "./PlayheadOverlay.vue"

/**
 * v3.0.2 M3-2 (P2-2): one rendered row of the multi-row timeline
 * ("one row = one single-window view", PRD P2).
 *
 * The row builds a row-scoped TimelineMetrics adapter (rowMetrics.ts) and
 * PROVIDES it row-scope, overriding the ancestor injection -- the existing
 * WaveformCanvas / TimeMarksLayer / SegmentBlocksLayer / PlayheadOverlay
 * children render the row window with ZERO changes to themselves.
 *
 * Architecture invariants (M3-2 / M4-3):
 * - NO cross-pointer-event state lives here: drag geometry belongs to the
 *   orchestrator's useRowDragCapture singleton (P1 skeleton, wired P2/P3).
 * - PLAYBACK_CLOCK_KEY is NOT re-provided (M0-1.6 red line): rows reach
 *   the single WorkspacePage-provided clock through the ancestor chain.
 * - `secondsPerRow` is captured per instance; the editor remounts rows
 *   wholesale when it changes (key includes the row start, M4-2).
 */
const props = defineProps<{
  rowIndex: number
  /** Row window length in seconds (the editor's current spr preset). */
  secondsPerRow: number
  /** Row geometry (px/percent) -- editor-owned, row-height changes stay geometry-only. */
  top: number
  rowHeight: number
  /** Horizontal width as a percentage of the timeline content (last row shrinks). */
  widthPercent?: number
  duration: number
  currentTime?: number
  /** FULL same-track segment array (cross-row trim neighbor bounds need all siblings). */
  segments: Segment[]
  edits?: EditDecision[]
  waveformPath?: string
  demoMode?: boolean
  /** v3.0.2 M4-3: orchestrator-shared peaks (skips per-row fetch when set). */
  peaksData?: WaveformPeak[] | null
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  globalEditMode?: boolean
  /** P3 (M5-4): frozen drag-capture converter forwarded to blocks. */
  getTimeFromPointer?: (clientX: number) => number
  /**
   * v3.0.2 M5-3: empty-area semantics handed to SegmentBlocksLayer.
   * The editor passes "seek" in multi mode; undefined keeps "add".
   */
  emptyAreaMode?: "add" | "seek"
  /**
   * v3.0.2 M5-3: the EDITOR-owned drag-capture singleton. On an empty-area
   * press the row freezes its CURRENT rect+span into it (the frozen
   * snapshot survives row recycling mid-gesture) and emits `empty-gesture`
   * -- the gesture machines themselves live in the editor (M3-2: no
   * cross-pointer-event state in rows).
   */
  rowDrag?: UseRowDragCaptureReturn | null
}>()

const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
  "split-segment": [segmentId: string, position: number]
  "set-time": [time: number]
  toast: [msg: string]
  "trim-end": [payload: { segmentId: string; field: "start" | "end"; value: number; altKey: boolean }]
  /** R5.8: row-local hover time preview (editor may consume or ignore). */
  "hover-time": [time: number | null]
  /** v3.0.2 M5-3: empty-area press, geometry frozen, routed by the editor. */
  "empty-gesture": [gesture: RowEmptyGesture]
  /** v3.0.2 M5-3: double click on empty area (play/pause). */
  "toggle-play": []
}>()

// -- Row geometry ---------------------------------------------------------

const rowStart = computed(() => props.rowIndex * props.secondsPerRow)
const rowEnd = computed(() =>
  Math.min(props.rowIndex * props.secondsPerRow + props.secondsPerRow, props.duration),
)

// -- Row-scoped metrics (row-scope provide overrides the ancestor) --------

const rootRef = ref<HTMLElement | null>(null)
const currentTimeRef = computed(() => props.currentTime ?? 0)
const durationRef = computed(() => props.duration)
const metrics = createRowMetrics(
  props.rowIndex,
  durationRef,
  currentTimeRef,
  props.secondsPerRow,
  rootRef,
)
provide(TIMELINE_METRICS_KEY, metrics)

// -- Row playhead (R5.3: only the playing row renders one) ----------------

const playheadInRow = computed(() => {
  const t = props.currentTime
  if (t === undefined) return false
  return t >= rowStart.value && t < rowEnd.value
})

// -- Row-local hover preview (R5.8: only the hovered row renders it) ------

const hover = ref<{ x: number; time: number } | null>(null)

function handleHoverMove(e: MouseEvent) {
  const el = rootRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const time = metrics.getTimeFromX(e.clientX)
  hover.value = { x: e.clientX - rect.left, time }
  emit("hover-time", time)
}

function handleHoverLeave() {
  hover.value = null
  emit("hover-time", null)
}

// -- M5-4: frozen trim source ----------------------------------------------

/**
 * M5-4: ANY mousedown in this row first freezes the row geometry into the
 * editor's drag-capture singleton (capture-phase listener -- it must run
 * BEFORE the block's own trim handler reads the pointer time). In-flight
 * drags then convert through the FROZEN snapshot and survive row recycling
 * (M3-3): unmounting this row never disturbs a live trim.
 */
function captureFrozenGeometry(e: MouseEvent) {
  const el = rootRef.value
  const rect = el?.getBoundingClientRect()
  if (rect && props.rowDrag) {
    props.rowDrag.capture(e.clientX, {
      rowLeft: rect.left,
      rowWidth: rect.width,
      rowStart: rowStart.value,
      rowSpan: { start: rowStart.value, end: rowEnd.value },
    })
  }
}

/**
 * Frozen pointer->time converter (P4 dual mapping, unbounded): clamps to
 * [0, duration] ONLY -- row boundaries never enter the trim constraint
 * chain (S7.8). Falls back to the row adapter when no gesture is captured
 * (stray reads outside a drag). Explicit prop injection still wins.
 */
function frozenTimeFromPointer(clientX: number): number {
  const t = props.rowDrag?.timeAt(clientX, { bounded: false })
  if (t === null || t === undefined) return metrics.getTimeFromX(clientX)
  return Math.min(Math.max(0, t), props.duration)
}

const trimTimeSource = computed(() => props.getTimeFromPointer ?? frozenTimeFromPointer)

// -- Badge ----------------------------------------------------------------

const badgeText = computed(
  () => `${formatTimeShort(rowStart.value)} → ${formatTimeShort(rowEnd.value)}`,
)

// -- M5-3: empty-area gesture conduit --------------------------------------

/**
 * Freeze THIS row's current geometry into the editor's capture singleton
 * and hand the press upward. The editor owns the decision (scrub vs
 * Ctrl-create vs Shift-marquee) and the document-level gesture listeners;
 * the row contributes only the pointerdown snapshot (M3-2).
 */
function handleEmptyPress(payload: {
  clientX: number
  clientY: number
  ctrlKey: boolean
  shiftKey: boolean
  time: number
}) {
  const el = rootRef.value
  const rect = el?.getBoundingClientRect()
  if (rect && props.rowDrag) {
    props.rowDrag.capture(payload.clientX, {
      rowLeft: rect.left,
      rowWidth: rect.width,
      rowStart: rowStart.value,
      rowSpan: { start: rowStart.value, end: rowEnd.value },
    })
  }
  emit("empty-gesture", { ...payload, rowIndex: props.rowIndex })
}

// Test/debug surface: the STATICALLY CAPTURED row adapter. Exposure lets
// the editor regression test observe the stale-adapter failure mode
// (spr change without remount leaves viewDuration frozen at the old
// preset even though the reactive props move on).
defineExpose({ metrics })
</script>

<template>
  <div
    ref="rootRef"
    class="waveform-row absolute left-0 overflow-hidden bg-surface-tile-0/40"
    :style="{
      top: top + 'px',
      height: rowHeight + 'px',
      width: (widthPercent ?? 100) + '%',
    }"
    :data-row-index="rowIndex"
    :data-row-start="rowStart"
    :data-row-end="rowEnd"
    @mousedown.capture="captureFrozenGeometry"
    @mousemove="handleHoverMove"
    @mouseleave="handleHoverLeave"
  >
    <!-- Row time badge (R5.4): row start -> row end, mono 11px -->
    <span
      class="waveform-row-time absolute left-1 top-0.5 rounded bg-surface px-1 py-px font-mono text-[11px] leading-none text-ink-muted shadow-sm"
      style="z-index: 4; pointer-events: none"
    >{{ badgeText }}</span>

    <!-- Waveform (row-window sampling via the provided row metrics) -->
    <WaveformCanvas
      :segments="segments"
      :waveform-path="waveformPath"
      :duration="duration"
      :demo-mode="demoMode"
      :peaks-data="peaksData"
      style="z-index: 0; pointer-events: none"
    />

    <!-- Row-local ruler (tick density adapts to the row seconds) -->
    <TimeMarksLayer style="z-index: 1" @seek="(t: number) => emit('set-time', t)" />

    <!-- Blocks: FULL track array (cross-row trim neighbors), row-window clipping -->
    <SegmentBlocksLayer
      :segments="segments"
      :edits="edits ?? []"
      :update-time="updateTime"
      :current-time="currentTime"
      :duration="duration"
      :global-edit-mode="globalEditMode"
      :row-start="rowStart"
      :row-end="rowEnd"
      :get-time-from-pointer="trimTimeSource"
      :empty-area-mode="emptyAreaMode"
      style="z-index: 2"
      @select-range="(s, e) => emit('select-range', s, e)"
      @add-segment="(s, e) => emit('add-segment', s, e)"
      @delete-segment="(id) => emit('delete-segment', id)"
      @seek-segment="(seg) => emit('seek-segment', seg)"
      @split-segment="(id, pos) => emit('split-segment', id, pos)"
      @set-time="(t) => emit('set-time', t)"
      @toast="(msg) => emit('toast', msg)"
      @trim-end="(p) => emit('trim-end', p)"
      @empty-press="handleEmptyPress"
      @empty-double-click="emit('toggle-play')"
    />

    <!-- Row playhead (R5.3): rendered only while the playhead is in THIS row -->
    <PlayheadOverlay
      v-if="playheadInRow"
      style="z-index: 10; pointer-events: none"
    />

    <!-- Hover preview (R5.8): row-local imperative-style line + time label -->
    <div
      v-if="hover"
      data-test="row-hover-preview"
      class="pointer-events-none absolute inset-y-0"
      style="z-index: 5"
    >
      <div
        class="h-full w-px bg-ink-muted/60"
        :style="{ transform: `translate3d(${hover.x}px, 0, 0)` }"
      />
      <span
        class="absolute top-5 whitespace-nowrap rounded bg-surface-tile-1 px-1 py-0.5 text-[10px] leading-none text-ink-muted shadow-sm"
        :style="{ transform: `translate3d(${Math.max(0, hover.x - 14)}px, 0, 0)` }"
      >{{ formatTimeShort(hover.time) }}</span>
    </div>
  </div>
</template>

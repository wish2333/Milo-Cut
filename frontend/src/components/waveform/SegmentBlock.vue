<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { Segment } from "@/types/project"
import type { SegmentState } from "@/utils/segmentHelpers"
import { findWordIndexAtTime } from "@/utils/wordHighlight"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
// v3.0.1 M1: constants live in the constraint kernel (single source of truth)
import {
  snapToStep,
  clampTimeToNeighbors,
} from "@/utils/trackConstraints"

/**
 * v3.0.1 M4-3: single segment block extracted from SegmentBlocksLayer so
 * main-track and extension-track lanes share rendering + trim interaction
 * (PRD R5.1). Per-block concerns live here: geometry, status color, hover
 * edge detection, trim drag (document listeners), word highlight.
 * Container concerns (empty click, context menu, keyboard, edit ranges)
 * stay in the layer component. Metrics arrive via the same provide/inject
 * the layer uses, so the block works in any lane sharing the timeline.
 */
const props = withDefaults(
  defineProps<{
    seg: Segment
    leftPercent: number
    widthPercent: number
    /** Same-track siblings -- neighbor bounds for the trim clamp. */
    segments: Segment[]
    state?: SegmentState
    /** "main" uses EditDecision styling; "extension" uses secondary styling. */
    trackKind?: "main" | "extension"
    selected?: boolean
    /** undefined disables trim (read-only lane). */
    updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
    currentTime?: number
    duration?: number
    globalEditMode?: boolean
    /** v3.0.2 M3-2 (①): cross-row continuation markers (multi-row mode). */
    continuesFrom?: boolean
    continuesTo?: boolean
    /**
     * v3.0.2 M3-2 (②): row window in seconds. When provided, trim handles
     * render only for edges living inside this row (S7.8: row boundaries
     * gate handle VISIBILITY only, never the trim constraint math).
     */
    rowStart?: number
    rowEnd?: number
    /**
     * v3.0.2 M3-2 (③): optional pointer->time source override. Defaults
     * to metrics.getTimeFromX; multi-row mode injects the frozen drag
     * capture converter so in-flight drags survive row recycling (M5-4).
     */
    getTimeFromPointer?: (clientX: number) => number
  }>(),
  {
    state: undefined,
    trackKind: "main",
    selected: false,
    updateTime: undefined,
    currentTime: undefined,
    duration: undefined,
    globalEditMode: false,
    continuesFrom: false,
    continuesTo: false,
    rowStart: undefined,
    rowEnd: undefined,
    getTimeFromPointer: undefined,
  },
)

const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "seek-segment": [segment: Segment]
  contextmenu: [segmentId: string, event: MouseEvent]
  /** Fired after a trim drag commits (Phase 3 linkage consumes altKey). */
  "trim-end": [payload: { segmentId: string; field: "start" | "end"; value: number; altKey: boolean }]
  toast: [msg: string]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const EDGE_HANDLE_HIT_PX = 16
const hoverEdge = ref<"left" | "right" | "body" | null>(null)

function detectEdge(el: HTMLElement, e: MouseEvent): "left" | "right" | "body" {
  const rect = el.getBoundingClientRect()
  const x = e.clientX - rect.left
  if (x < EDGE_HANDLE_HIT_PX) return "left"
  if (x > rect.width - EDGE_HANDLE_HIT_PX) return "right"
  return "body"
}

// -- Styling -------------------------------------------------------------

function statusColor(): string {
  if (props.trackKind === "extension") {
    // v3.0.1 M4-3: extension blocks wear secondary (violet) styling so
    // main/extension lanes are distinguishable at a glance (PRD R3.1).
    return "bg-violet-200/50 border-violet-400"
  }
  if (props.state?.styleClass === "masked") return "bg-red-200/60 border-red-400"
  if (props.state?.styleClass === "kept") return "bg-green-200/60 border-green-400"
  if (props.seg.type === "silence") return "bg-gray-200/50 border-gray-300"
  return "bg-blue-100/60 border-blue-300"
}

// -- Trim (one-edge neighbor clamp, v3.0.1 M2-1) --------------------------

const EDGE_EPSILON = 1e-6

/** v3.0.2 M3-2 (②): is the segment's left/right edge inside this row? */
const leftEdgeInRow = computed(
  () => props.rowStart === undefined || props.seg.start >= props.rowStart - EDGE_EPSILON,
)
const rightEdgeInRow = computed(
  () => props.rowEnd === undefined || props.seg.end <= props.rowEnd + EDGE_EPSILON,
)

/** Pointer->time source: injected frozen converter, else row metrics. */
function pointerTime(clientX: number): number {
  return props.getTimeFromPointer
    ? props.getTimeFromPointer(clientX)
    : metrics.getTimeFromX(clientX)
}

function clampTime(raw: number, edge: "left" | "right", seg: Segment): number {
  // Single kernel implementation (v3.0.2 M3-2 ④): one-edge clamp against
  // the same-track neighbor gap; blocked keeps the edge.
  return clampTimeToNeighbors(raw, edge, seg, props.segments)
}

function snapToFrame(time: number): number {
  return snapToStep(time)
}

function handleBlockMouseMove(e: MouseEvent) {
  hoverEdge.value = detectEdge(e.currentTarget as HTMLElement, e)
}

function handleBlockMouseLeave() {
  hoverEdge.value = null
}

function handleBlockMouseDown(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const edge = detectEdge(el, e)
  if (edge === "body") {
    emit("select-range", props.seg.start, props.seg.end)
    return
  }
  // v3.0.2 M3-2 (②): an edge living outside this row has no handle --
  // treat the press as a body select (row boundaries gate visibility).
  if (edge === "left" && !leftEdgeInRow.value) {
    emit("select-range", props.seg.start, props.seg.end)
    return
  }
  if (edge === "right" && !rightEdgeInRow.value) {
    emit("select-range", props.seg.start, props.seg.end)
    return
  }
  if (!props.updateTime) return

  e.stopPropagation()
  const initialValue = edge === "left" ? props.seg.start : props.seg.end
  const offset = initialValue - pointerTime(e.clientX)

  const onMove = (ev: MouseEvent) => {
    const raw = pointerTime(ev.clientX) + offset
    const clamped = clampTime(raw, edge, props.seg)
    props.updateTime!(props.seg.id, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = (ev: MouseEvent) => {
    const raw = pointerTime(ev.clientX) + offset
    // v3.0.1 M4-5 Alt semantics: holding Alt inverts snapping (free
    // position); the neighbor clamp still applies. The trim-end payload
    // carries altKey for the Phase 3 linkage skip.
    const clamped = clampTime(raw, edge, props.seg)
    const snapped = ev.altKey ? clamped : snapToFrame(clamped)
    const final = clampTime(snapped, edge, props.seg)
    props.updateTime!(props.seg.id, edge === "left" ? "start" : "end", final)
    emit("trim-end", {
      segmentId: props.seg.id,
      field: edge === "left" ? "start" : "end",
      value: final,
      altKey: ev.altKey,
    })
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
    document.body.style.cursor = ""
  }

  document.body.style.cursor = edge === "left" ? "w-resize" : "e-resize"
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

// -- Word highlight (hover, pure display, v3.0.0 P4-1) --------------------

const hovered = ref(false)

const wordHighlight = computed<{ index: number } | null>(() => {
  if (
    props.seg.type !== "subtitle" ||
    !props.seg.words ||
    props.seg.words.length === 0 ||
    !hovered.value
  ) {
    return null
  }
  const t = Math.min(Math.max(props.currentTime ?? 0, props.seg.start), props.seg.end)
  const index = findWordIndexAtTime(props.seg.words, t)
  return index < 0 ? null : { index }
})

function isWordHighlighted(wordIndex: number): boolean {
  return wordHighlight.value !== null && wordHighlight.value.index === wordIndex
}
</script>

<template>
  <div
    class="absolute top-1 bottom-1 rounded border select-none group"
    :class="[
      statusColor(),
      hoverEdge === 'left' || hoverEdge === 'right' ? 'cursor-ew-resize' : 'cursor-grab',
      selected ? 'ring-2 ring-blue-500' : '',
      continuesFrom ? 'continues-from' : '',
      continuesTo ? 'continues-to' : '',
    ]"
    :style="{
      left: leftPercent + '%',
      width: widthPercent + '%',
      // v3.0.2 (①): square off the side that continues into the next row
      // (inline style wins over the `rounded` utility deterministically).
      ...(continuesFrom
        ? { borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }
        : null),
      ...(continuesTo
        ? { borderTopRightRadius: 0, borderBottomRightRadius: 0 }
        : null),
    }"
    :title="seg.text || `[${seg.type}]`"
    @mousemove="handleBlockMouseMove($event); hovered = true"
    @mouseleave="handleBlockMouseLeave(); hovered = false"
    @mousedown="handleBlockMouseDown"
    @contextmenu="emit('contextmenu', seg.id, $event)"
    @click="emit('seek-segment', seg)"
  >
    <!-- Left edge handle (only when the left edge lives in this row, v3.0.2 ②) -->
    <div
      v-if="leftEdgeInRow"
      class="absolute left-0 top-0 bottom-0 w-2 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-400 rounded-l"
      style="pointer-events: none"
    />
    <!-- Right edge handle (only when the right edge lives in this row, v3.0.2 ②) -->
    <div
      v-if="rightEdgeInRow"
      class="absolute right-0 top-0 bottom-0 w-2 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-400 rounded-r"
      style="pointer-events: none"
    />
    <!-- Content -->
    <div class="flex h-full items-center overflow-hidden px-2">
      <span
        v-if="seg.type === 'subtitle' && seg.words?.length && wordHighlight"
        class="truncate text-[10px] leading-tight text-gray-700"
      >
        <span
          v-for="(w, wi) in seg.words"
          :key="wi"
          :class="isWordHighlighted(wi) ? 'rounded-sm bg-blue-500/40' : ''"
        >{{ w.word }}</span>
      </span>
      <span v-else class="truncate text-[10px] leading-tight text-gray-700">
        {{ seg.text || (seg.type === 'silence' ? '...' : '') }}
      </span>
    </div>
  </div>
</template>

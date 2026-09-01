<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { Segment } from "@/types/project"
import type { SegmentState } from "@/utils/segmentHelpers"
import { findWordIndexAtTime } from "@/utils/wordHighlight"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
// v3.0.1 M1: constants live in the constraint kernel (single source of truth)
import {
  MIN_SEGMENT_DURATION,
  getTrackNeighborBounds,
  snapToStep,
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
  }>(),
  {
    state: undefined,
    trackKind: "main",
    selected: false,
    updateTime: undefined,
    currentTime: undefined,
    duration: undefined,
    globalEditMode: false,
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

function clampTime(raw: number, edge: "left" | "right", seg: Segment): number {
  // Trim is a one-edge clamp against the same-track neighbor gap: no
  // slide-in-place semantics. Blocked (empty legal range) keeps the edge.
  const bounds = getTrackNeighborBounds(props.segments, seg.id)
  if (edge === "left") {
    const hi = seg.end - MIN_SEGMENT_DURATION
    const lo = bounds.prevEnd ?? Number.NEGATIVE_INFINITY
    if (lo > hi) return seg.start
    return Math.min(Math.max(raw, lo), hi)
  }
  const lo = seg.start + MIN_SEGMENT_DURATION
  const hi = bounds.nextStart ?? Number.POSITIVE_INFINITY
  if (hi < lo) return seg.end
  return Math.min(Math.max(raw, lo), hi)
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
  if (!props.updateTime) return

  e.stopPropagation()
  const initialValue = edge === "left" ? props.seg.start : props.seg.end
  const offset = initialValue - metrics.getTimeFromX(e.clientX)

  const onMove = (ev: MouseEvent) => {
    const raw = metrics.getTimeFromX(ev.clientX) + offset
    const clamped = clampTime(raw, edge, props.seg)
    props.updateTime!(props.seg.id, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = (ev: MouseEvent) => {
    const raw = metrics.getTimeFromX(ev.clientX) + offset
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
    ]"
    :style="{
      left: leftPercent + '%',
      width: widthPercent + '%',
    }"
    :title="seg.text || `[${seg.type}]`"
    @mousemove="handleBlockMouseMove($event); hovered = true"
    @mouseleave="handleBlockMouseLeave(); hovered = false"
    @mousedown="handleBlockMouseDown"
    @contextmenu="emit('contextmenu', seg.id, $event)"
    @click="emit('seek-segment', seg)"
  >
    <!-- Left edge handle -->
    <div
      class="absolute left-0 top-0 bottom-0 w-2 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-400 rounded-l"
      style="pointer-events: none"
    />
    <!-- Right edge handle -->
    <div
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

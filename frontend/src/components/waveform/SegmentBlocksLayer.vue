<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { getEditForSegment, getEffectiveStatus } from "@/utils/segmentHelpers"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
}>()

const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const MIN_SEGMENT_DURATION = 0.1
const hoverEdge = ref<"left" | "right" | "body" | null>(null)
const EDGE_HANDLE_HIT_PX = 16

interface Block {
  seg: Segment
  leftPercent: number
  widthPercent: number
  edit: EditDecision | undefined
  effectiveStatus: "normal" | "masked" | "kept"
}

const visibleBlocks = computed<Block[]>(() => {
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return []

  return props.segments
    .filter(seg => seg.end > vs && seg.start < ve)
    .map(seg => {
      const clampStart = Math.max(seg.start, vs)
      const clampEnd = Math.min(seg.end, ve)
      const edit = getEditForSegment(props.edits, seg)
      return {
        seg,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
        edit,
        effectiveStatus: getEffectiveStatus(props.edits, seg),
      }
    })
})

function statusColor(block: Block): string {
  if (block.effectiveStatus === "masked") return "bg-red-200 border-red-400"
  if (block.effectiveStatus === "kept") return "bg-green-200 border-green-400"
  if (block.seg.type === "silence") return "bg-gray-200 border-gray-300"
  return "bg-blue-100 border-blue-300"
}

function handleEmptyClick(e: MouseEvent) {
  const time = metrics.getTimeFromX(e.clientX)
  emit("add-segment", time, time + 0.5)
}

function snapToFrame(time: number): number {
  // Snap to nearest 0.01s boundary
  return Math.round(time * 100) / 100
}

function clampTime(
  raw: number,
  edge: "left" | "right",
  seg: Segment,
): number {
  if (edge === "left") {
    return Math.min(raw, seg.end - MIN_SEGMENT_DURATION)
  }
  return Math.max(raw, seg.start + MIN_SEGMENT_DURATION)
}

function detectEdge(e: MouseEvent): "left" | "right" | "body" {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const x = e.clientX - rect.left
  if (x < EDGE_HANDLE_HIT_PX) return "left"
  if (x > rect.width - EDGE_HANDLE_HIT_PX) return "right"
  return "body"
}

function handleBlockMouseMove(e: MouseEvent) {
  hoverEdge.value = detectEdge(e)
}

function handleBlockMouseLeave() {
  hoverEdge.value = null
}

function handleBlockMouseDown(
  block: Block,
  e: MouseEvent,
) {
  const edge = detectEdge(e)
  if (edge === "body") {
    emit("select-range", block.seg.start, block.seg.end)
    return
  }
  if (!props.updateTime) return

  e.stopPropagation()
  const initialValue = edge === "left" ? block.seg.start : block.seg.end
  const offset = initialValue - metrics.getTimeFromX(e.clientX)

  const onMove = (e: MouseEvent) => {
    const raw = metrics.getTimeFromX(e.clientX) + offset
    const clamped = clampTime(raw, edge, block.seg)
    props.updateTime!(block.seg.id, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = (e: MouseEvent) => {
    const raw = metrics.getTimeFromX(e.clientX) + offset
    const snapped = snapToFrame(clampTime(raw, edge, block.seg))
    props.updateTime!(block.seg.id, edge === "left" ? "start" : "end", snapped)
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
    document.body.style.cursor = ""
  }

  document.body.style.cursor = edge === "left" ? "w-resize" : "e-resize"
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

</script>

<template>
  <div class="absolute inset-x-0 top-6 bottom-0" @mousedown.self="handleEmptyClick">
    <div
      v-for="block in visibleBlocks"
      :key="block.seg.id"
      class="absolute top-1 bottom-1 rounded border select-none group"
      :class="[
        statusColor(block),
        hoverEdge === 'left' || hoverEdge === 'right' ? 'cursor-ew-resize' : 'cursor-grab',
      ]"
      :style="{
        left: block.leftPercent + '%',
        width: block.widthPercent + '%',
      }"
      :title="block.seg.text || `[${block.seg.type}]`"
      @mousemove="handleBlockMouseMove"
      @mouseleave="handleBlockMouseLeave"
      @mousedown="handleBlockMouseDown(block, $event)"
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
        <span class="truncate text-[10px] leading-tight text-gray-700">
          {{ block.seg.text || (block.seg.type === 'silence' ? '...' : '') }}
        </span>
      </div>
    </div>
  </div>
</template>

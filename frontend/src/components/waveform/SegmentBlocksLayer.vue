<script setup lang="ts">
import { computed, inject, ref, onMounted, onUnmounted } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { buildSegmentStateMap } from "@/utils/segmentHelpers"
import type { SegmentState } from "@/utils/segmentHelpers"
import { openContextMenu } from "@/utils/contextMenuManager"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  currentTime?: number
  duration?: number
  /** v2.1.1 A-03: edit mode interception for structural ops */
  globalEditMode?: boolean
}>()

const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
  "split-segment": [segmentId: string, position: number]
  /** v2.1.1 A-03: move playhead without playing (arrow keys, selection mode) */
  "set-time": [time: number]
  /** v2.1.1 A-03: edit mode toast notification */
  toast: [msg: string]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const MIN_SEGMENT_DURATION = 0.1
const hoverEdge = ref<"left" | "right" | "body" | null>(null)
const EDGE_HANDLE_HIT_PX = 16
const selectedBlockId = ref<string | null>(null)
const contextMenu = ref<{ x: number; y: number; segmentId: string } | null>(null)
const containerRef = ref<HTMLElement | null>(null)

const menuMaxY = typeof window !== "undefined" ? window.innerHeight - 180 : 0

// Focus the container on any interaction so arrow keys go to our handler,
// not to the HTML5 video element (which seeks ±5s natively).
function focusContainer() {
  const el = containerRef.value
  if (el && document.activeElement !== el) el.focus()
}

interface Block {
  seg: Segment
  leftPercent: number
  widthPercent: number
  state: SegmentState
}

interface EditRangeBlock {
  edit: EditDecision
  leftPercent: number
  widthPercent: number
}

const segmentStateMap = computed(() => buildSegmentStateMap(props.segments, props.edits))
const EMPTY_SEGMENT_STATE: SegmentState = {
  displayStatus: "none",
  styleClass: "normal",
  activeEdit: undefined,
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
      const state = segmentStateMap.value.get(seg.id) ?? EMPTY_SEGMENT_STATE
      return {
        seg,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
        state,
      }
    })
})

const visibleEditRanges = computed<EditRangeBlock[]>(() => {
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return []

  return props.edits
    .filter(e => e.target_type === "range" && e.end > vs && e.start < ve)
    .map(e => {
      const clampStart = Math.max(e.start, vs)
      const clampEnd = Math.min(e.end, ve)
      return {
        edit: e,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
      }
    })
})

function statusColor(block: Block): string {
  if (block.state.styleClass === "masked") return "bg-red-200/60 border-red-400"
  if (block.state.styleClass === "kept") return "bg-green-200/60 border-green-400"
  if (block.seg.type === "silence") return "bg-gray-200/50 border-gray-300"
  return "bg-blue-100/60 border-blue-300"
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
  focusContainer()
  selectedBlockId.value = block.seg.id
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

function handleBlockContextMenu(block: Block, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  selectedBlockId.value = block.seg.id
  contextMenu.value = { x: e.clientX, y: e.clientY, segmentId: block.seg.id }
  // v3.0.0 M9-1: single-instance mutex via the shared manager -- opening
  // here closes any other open menu (e.g. the Timeline row menu); the
  // former `closeallcontextmenus` broadcast is retired.
  openContextMenu(() => { contextMenu.value = null })
}

function handleBlockClick(block: Block) {
  selectedBlockId.value = null
  emit("seek-segment", block.seg)
}

function closeContextMenu() {
  contextMenu.value = null
}

function splitSelectedAtCursor() {
  // v2.1.1 A-03: block structural ops in edit mode
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  const id = contextMenu.value?.segmentId
  if (!id) return
  const seg = props.segments.find(s => s.id === id)
  const pos = props.currentTime ?? 0
  if (!seg || pos <= seg.start || pos >= seg.end) return
  emit("split-segment", id, pos)
  closeContextMenu()
}

function splitSelectedAtMidpoint() {
  // v2.1.1 A-03: block structural ops in edit mode
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  const id = contextMenu.value?.segmentId
  if (!id) return
  const seg = props.segments.find(s => s.id === id)
  if (!seg) return
  const mid = (seg.start + seg.end) / 2
  emit("split-segment", id, mid)
  closeContextMenu()
}

function deleteSelected() {
  // v2.1.1 A-03: block structural ops in edit mode
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  if (selectedBlockId.value) {
    emit("delete-segment", selectedBlockId.value)
    selectedBlockId.value = null
  }
  closeContextMenu()
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === "Delete" || e.key === "Backspace") {
    if (selectedBlockId.value) {
      e.preventDefault()
      deleteSelected()
    }
  }
  if (e.key === "Escape") {
    selectedBlockId.value = null
    closeContextMenu()
  }
  // v2.1.1 A-03: ←/→ move playhead without playing (arrow keys are positioning tools)
  if (e.key === "ArrowLeft") {
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    const t = Math.max(0, (props.currentTime ?? 0) - step)
    emit("set-time", t)
  }
  if (e.key === "ArrowRight") {
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    const t = Math.min(props.duration ?? 99999, (props.currentTime ?? 0) + step)
    emit("set-time", t)
  }
}

// Document-level capture listener: intercept arrow keys BEFORE the video
// element's native ±5s handler. Delegates to handleKeyDown when waveform active.
function handleDocKeyCapture(e: KeyboardEvent) {
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") &&
      containerRef.value && document.activeElement === containerRef.value) {
    e.preventDefault()
    e.stopPropagation()
    handleKeyDown(e)
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleDocKeyCapture, { capture: true })
})

onUnmounted(() => {
  document.removeEventListener("keydown", handleDocKeyCapture, { capture: true })
})

</script>

<template>
  <div
    ref="containerRef"
    class="absolute inset-x-0 top-6 bottom-0 focus:outline-none"
    tabindex="0"
    @mousedown="focusContainer"
    @mousedown.self="handleEmptyClick"
    @keydown="handleKeyDown"
    @click.self="selectedBlockId = null; closeContextMenu()"
  >
    <div
      v-for="block in visibleBlocks"
      :key="block.seg.id"
      class="absolute top-1 bottom-1 rounded border select-none group"
      :class="[
        statusColor(block),
        hoverEdge === 'left' || hoverEdge === 'right' ? 'cursor-ew-resize' : 'cursor-grab',
        selectedBlockId === block.seg.id ? 'ring-2 ring-blue-500' : '',
      ]"
      :style="{
        left: block.leftPercent + '%',
        width: block.widthPercent + '%',
      }"
      :title="block.seg.text || `[${block.seg.type}]`"
      @mousemove="handleBlockMouseMove"
      @mouseleave="handleBlockMouseLeave"
      @mousedown="handleBlockMouseDown(block, $event)"
      @contextmenu="handleBlockContextMenu(block, $event)"
      @click="handleBlockClick(block)"
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

    <!-- Edit range overlays (e.g., subtitle trim delete ranges) -->
    <div
      v-for="rangeBlock in visibleEditRanges"
      :key="rangeBlock.edit.id"
      class="absolute top-0 bottom-0 border border-red-400/60 bg-red-300/30 pointer-events-none"
      :style="{
        left: rangeBlock.leftPercent + '%',
        width: rangeBlock.widthPercent + '%',
      }"
      :title="`Delete range: ${rangeBlock.edit.start.toFixed(1)}s - ${rangeBlock.edit.end.toFixed(1)}s`"
    >
      <div class="h-full w-full" style="background-image: repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(239,68,68,0.15) 3px, rgba(239,68,68,0.15) 6px);" />
    </div>

    <!-- Context Menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-dropdown bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[140px]"
        :style="{ left: contextMenu.x + 'px', top: Math.min(contextMenu.y, menuMaxY) + 'px' }"
        @click="closeContextMenu"
      >
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="splitSelectedAtCursor"
        >
          按时间指针分割
        </button>
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="splitSelectedAtMidpoint"
        >
          从中点分割
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
          @click="deleteSelected"
        >
          删除
        </button>
      </div>
    </Teleport>
  </div>
</template>

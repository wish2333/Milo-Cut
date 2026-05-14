<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { formatTime, formatTimeShort } from "@/utils/format"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  duration: number
  currentTime: number
}>()

const emit = defineEmits<{
  seek: [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
}>()

// View window state
const viewDuration = ref(30)
const viewStart = ref(0)
const rulerRef = ref<HTMLDivElement | null>(null)
const scrollbarRef = ref<HTMLDivElement | null>(null)

const MIN_VIEW = 2
const MAX_VIEW_SECONDS = 600

const viewEnd = computed(() => Math.min(viewStart.value + viewDuration.value, props.duration))

// Selection state
const selectionStart = ref<number | null>(null)
const selectionEnd = ref<number | null>(null)
const isSelecting = ref(false)
const isDraggingHandle = ref<"left" | "right" | null>(null)
const dragOriginX = ref(0)
const dragOriginValue = ref(0)

// Snap toggle
const snapEnabled = ref(false)
const SNAP_THRESHOLD = 0.1 // seconds

// ================================================================
// View navigation
// ================================================================

function clampViewStart() {
  const maxStart = Math.max(0, props.duration - viewDuration.value)
  viewStart.value = Math.max(0, Math.min(viewStart.value, maxStart))
}

function scrollTo(time: number) {
  const center = time - viewDuration.value / 2
  viewStart.value = Math.max(0, Math.min(center, Math.max(0, props.duration - viewDuration.value)))
}

function ensurePlayheadInView() {
  const t = props.currentTime
  if (t < viewStart.value || t > viewEnd.value) {
    scrollTo(t)
  }
}

// Auto-follow playhead
let lastFollowTime = 0
function maybeFollowPlayhead() {
  const now = Date.now()
  if (now - lastFollowTime < 200) return
  lastFollowTime = now
  ensurePlayheadInView()
}

// ================================================================
// Zoom (Ctrl+scroll)
// ================================================================

function zoomAt(centerTime: number, factor: number) {
  const newDuration = Math.max(MIN_VIEW, Math.min(
    Math.min(props.duration, MAX_VIEW_SECONDS),
    viewDuration.value * factor,
  ))
  // Keep centerTime at the same relative position
  const centerRatio = (centerTime - viewStart.value) / viewDuration.value
  viewDuration.value = newDuration
  viewStart.value = centerTime - centerRatio * newDuration
  clampViewStart()
}

function handleWheel(e: WheelEvent) {
  e.preventDefault()
  if (e.ctrlKey || e.metaKey) {
    // Ctrl+scroll = zoom at cursor position
    const rect = rulerRef.value?.getBoundingClientRect()
    if (!rect) return
    const ratio = (e.clientX - rect.left) / rect.width
    const timeAtCursor = viewStart.value + ratio * viewDuration.value
    const factor = e.deltaY > 0 ? 1.15 : 0.87
    zoomAt(timeAtCursor, factor)
  } else {
    // Plain scroll = horizontal scroll
    // deltaY for vertical scroll wheels, deltaX for horizontal trackpads
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
    const scrollAmount = (delta / 120) * viewDuration.value * 0.15
    viewStart.value += scrollAmount
    clampViewStart()
  }
}

// ================================================================
// Timecode click (top strip) -> seek
// ================================================================

function handleTimecodeClick(e: MouseEvent) {
  if (!rulerRef.value) return
  const rect = rulerRef.value.getBoundingClientRect()
  const ratio = (e.clientX - rect.left) / rect.width
  const time = viewStart.value + ratio * viewDuration.value
  emit("seek", Math.max(0, Math.min(time, props.duration)))
}

// ================================================================
// Selection area (middle) -> select range
// ================================================================

function snapTime(time: number): number {
  if (!snapEnabled.value) return time
  // Snap to segment boundaries
  for (const seg of props.segments) {
    if (Math.abs(time - seg.start) < SNAP_THRESHOLD) return seg.start
    if (Math.abs(time - seg.end) < SNAP_THRESHOLD) return seg.end
  }
  return time
}

function getTimeFromX(clientX: number): number {
  if (!rulerRef.value) return 0
  const rect = rulerRef.value.getBoundingClientRect()
  const ratio = (clientX - rect.left) / rect.width
  return snapTime(viewStart.value + ratio * viewDuration.value)
}

function handleSelectionMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  const time = getTimeFromX(e.clientX)

  // Check if clicking inside existing selection (or on its handles)
  if (selectionStart.value !== null && selectionEnd.value !== null) {
    const startPct = ((selectionStart.value - viewStart.value) / viewDuration.value) * 100
    const endPct = ((selectionEnd.value - viewStart.value) / viewDuration.value) * 100
    const clickPct = ((time - viewStart.value) / viewDuration.value) * 100

    // Handle drag (edges)
    if (Math.abs(clickPct - startPct) < 1.5) {
      isDraggingHandle.value = "left"
      dragOriginX.value = e.clientX
      dragOriginValue.value = selectionStart.value
      document.addEventListener("mousemove", handleHandleDrag)
      document.addEventListener("mouseup", handleHandleDragEnd)
      return
    }
    if (Math.abs(clickPct - endPct) < 1.5) {
      isDraggingHandle.value = "right"
      dragOriginX.value = e.clientX
      dragOriginValue.value = selectionEnd.value
      document.addEventListener("mousemove", handleHandleDrag)
      document.addEventListener("mouseup", handleHandleDragEnd)
      return
    }

    // Body drag (move entire selection)
    if (clickPct > startPct && clickPct < endPct) {
      isDraggingSelection.value = true
      dragOriginX.value = e.clientX
      dragOriginValue.value = time
      selDragStartStart.value = selectionStart.value
      selDragStartEnd.value = selectionEnd.value
      document.addEventListener("mousemove", handleSelectionBodyDrag)
      document.addEventListener("mouseup", handleSelectionBodyDragEnd)
      return
    }
  }

  // Start new selection
  isSelecting.value = true
  selectionStart.value = time
  selectionEnd.value = time
  document.addEventListener("mousemove", handleSelectionMouseMove)
  document.addEventListener("mouseup", handleSelectionMouseUp)
}

function handleSelectionMouseMove(e: MouseEvent) {
  if (!isSelecting.value) return
  const time = getTimeFromX(e.clientX)
  if (time < selectionStart.value!) {
    selectionStart.value = time
    selectionEnd.value = selectionStart.value
  } else {
    selectionEnd.value = time
  }
}

function handleSelectionMouseUp() {
  isSelecting.value = false
  document.removeEventListener("mousemove", handleSelectionMouseMove)
  document.removeEventListener("mouseup", handleSelectionMouseUp)

  // Normalize
  if (selectionStart.value !== null && selectionEnd.value !== null) {
    const s = Math.min(selectionStart.value, selectionEnd.value)
    const e = Math.max(selectionStart.value, selectionEnd.value)
    if (e - s < 0.1) {
      // Too small, treat as click -> seek
      emit("seek", s)
      selectionStart.value = null
      selectionEnd.value = null
    } else {
      selectionStart.value = s
      selectionEnd.value = e
      emit("select-range", s, e)
    }
  }
}

// ================================================================
// Selection body dragging (move entire selection)
// ================================================================
const isDraggingSelection = ref(false)
const selDragStartStart = ref(0)
const selDragStartEnd = ref(0)

function handleSelectionBodyDrag(e: MouseEvent) {
  if (!isDraggingSelection.value) return
  const time = getTimeFromX(e.clientX)
  const dt = time - dragOriginValue.value
  const duration = selDragStartEnd.value - selDragStartStart.value
  let newStart = selDragStartStart.value + dt
  let newEnd = selDragStartEnd.value + dt

  // Clamp to valid range
  if (newStart < 0) {
    newStart = 0
    newEnd = duration
  }
  if (newEnd > props.duration) {
    newEnd = props.duration
    newStart = newEnd - duration
  }

  selectionStart.value = newStart
  selectionEnd.value = newEnd
}

function handleSelectionBodyDragEnd() {
  isDraggingSelection.value = false
  document.removeEventListener("mousemove", handleSelectionBodyDrag)
  document.removeEventListener("mouseup", handleSelectionBodyDragEnd)
  if (selectionStart.value !== null && selectionEnd.value !== null) {
    emit("select-range", selectionStart.value, selectionEnd.value)
  }
}

// ================================================================
// Handle dragging (edges)
// ================================================================

function handleHandleDrag(e: MouseEvent) {
  if (!isDraggingHandle.value || !rulerRef.value) return
  const time = getTimeFromX(e.clientX)

  if (isDraggingHandle.value === "left") {
    selectionStart.value = Math.min(time, selectionEnd.value! - 0.1)
  } else {
    selectionEnd.value = Math.max(time, selectionStart.value! + 0.1)
  }
}

function handleHandleDragEnd() {
  isDraggingHandle.value = null
  document.removeEventListener("mousemove", handleHandleDrag)
  document.removeEventListener("mouseup", handleHandleDragEnd)
  if (selectionStart.value !== null && selectionEnd.value !== null) {
    emit("select-range", selectionStart.value, selectionEnd.value)
  }
}

// ================================================================
// Scrollbar
// ================================================================

const scrollbarDragging = ref(false)
const scrollbarDragStartX = ref(0)
const scrollbarDragStartViewStart = ref(0)

function handleScrollbarMouseDown(e: MouseEvent) {
  if (e.button !== 0) return
  scrollbarDragging.value = true
  scrollbarDragStartX.value = e.clientX
  scrollbarDragStartViewStart.value = viewStart.value
  document.addEventListener("mousemove", handleScrollbarMouseMove)
  document.addEventListener("mouseup", handleScrollbarMouseUp)
}

function handleScrollbarMouseMove(e: MouseEvent) {
  if (!scrollbarDragging.value || !scrollbarRef.value) return
  const rect = scrollbarRef.value.getBoundingClientRect()
  const dx = e.clientX - scrollbarDragStartX.value
  const ratio = dx / rect.width
  const dt = ratio * props.duration
  viewStart.value = scrollbarDragStartViewStart.value + dt
  clampViewStart()
}

function handleScrollbarMouseUp() {
  scrollbarDragging.value = false
  document.removeEventListener("mousemove", handleScrollbarMouseMove)
  document.removeEventListener("mouseup", handleScrollbarMouseUp)
}

// Scrollbar thumb dimensions
const thumbLeft = computed(() => {
  if (props.duration <= 0) return 0
  return (viewStart.value / props.duration) * 100
})

const thumbWidth = computed(() => {
  if (props.duration <= 0) return 100
  return Math.max(5, (viewDuration.value / props.duration) * 100)
})

// ================================================================
// Segment blocks
// ================================================================

interface Block {
  id: string
  leftPercent: number
  widthPercent: number
  type: "subtitle" | "silence"
  editStatus: string | null
  text: string
}

const visibleBlocks = computed<Block[]>(() => {
  if (viewDuration.value <= 0) return []
  return props.segments
    .filter(seg => seg.end > viewStart.value && seg.start < viewEnd.value)
    .map(seg => {
      const edit = props.edits.find(e =>
        Math.abs(e.start - seg.start) < 0.01 && Math.abs(e.end - seg.end) < 0.01,
      )
      const clampStart = Math.max(seg.start, viewStart.value)
      const clampEnd = Math.min(seg.end, viewEnd.value)
      return {
        id: seg.id,
        leftPercent: ((clampStart - viewStart.value) / viewDuration.value) * 100,
        widthPercent: Math.max(0.3, ((clampEnd - clampStart) / viewDuration.value) * 100),
        type: seg.type,
        editStatus: edit?.status ?? null,
        text: seg.text || (seg.type === "silence" ? `silence ${(seg.end - seg.start).toFixed(1)}s` : ""),
      }
    })
})

// ================================================================
// Time marks
// ================================================================

const timeMarks = computed(() => {
  if (viewDuration.value <= 0) return []
  const targetCount = 10
  const rawStep = viewDuration.value / targetCount
  const niceSteps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
  const step = niceSteps.find(s => s >= rawStep) ?? rawStep
  const marks: { percent: number; label: string; time: number }[] = []
  const start = Math.ceil(viewStart.value / step) * step
  for (let t = start; t <= viewEnd.value; t += step) {
    marks.push({
      percent: ((t - viewStart.value) / viewDuration.value) * 100,
      label: formatTimeShort(t),
      time: t,
    })
  }
  return marks
})

// ================================================================
// Playhead
// ================================================================

const playheadPercent = computed(() => {
  if (viewDuration.value <= 0) return 0
  const pct = ((props.currentTime - viewStart.value) / viewDuration.value) * 100
  return Math.max(0, Math.min(100, pct))
})

const playheadVisible = computed(() => {
  return props.currentTime >= viewStart.value && props.currentTime <= viewEnd.value
})

// ================================================================
// Selection overlay
// ================================================================

const selectionLeftPercent = computed(() => {
  if (selectionStart.value === null || viewDuration.value <= 0) return 0
  return Math.max(0, ((selectionStart.value - viewStart.value) / viewDuration.value) * 100)
})

const selectionWidthPercent = computed(() => {
  if (selectionStart.value === null || selectionEnd.value === null || viewDuration.value <= 0) return 0
  const s = Math.max(viewStart.value, selectionStart.value)
  const e = Math.min(viewEnd.value, selectionEnd.value)
  return Math.max(0, ((e - s) / viewDuration.value) * 100)
})

const selectionVisible = computed(() => {
  if (selectionStart.value === null || selectionEnd.value === null) return false
  return selectionEnd.value > viewStart.value && selectionStart.value < viewEnd.value
})

// ================================================================
// Segment block click -> select that segment
// ================================================================

function handleBlockClick(segId: string, e: MouseEvent) {
  e.stopPropagation()
  const seg = props.segments.find(s => s.id === segId)
  if (seg) {
    selectionStart.value = seg.start
    selectionEnd.value = seg.end
    emit("select-range", seg.start, seg.end)
  }
}

// ================================================================
// Add segment button
// ================================================================

function handleAddSegment() {
  const start = selectionStart.value ?? props.currentTime
  const end = selectionEnd.value ?? (start + 2)
  emit("add-segment", start, end)
}

function clearSelection() {
  selectionStart.value = null
  selectionEnd.value = null
}

// ================================================================
// Watchers
// ================================================================

watch(() => props.currentTime, maybeFollowPlayhead)
watch(() => props.duration, (d) => {
  if (viewDuration.value > d) {
    viewDuration.value = Math.min(30, d)
  }
  clampViewStart()
})

onMounted(() => {
  if (props.duration > 0) {
    viewDuration.value = Math.min(30, props.duration)
  }
  rulerRef.value?.addEventListener("wheel", handleWheel, { passive: false })
})

onUnmounted(() => {
  rulerRef.value?.removeEventListener("wheel", handleWheel)
  document.removeEventListener("mousemove", handleHandleDrag)
  document.removeEventListener("mouseup", handleHandleDragEnd)
  document.removeEventListener("mousemove", handleSelectionBodyDrag)
  document.removeEventListener("mouseup", handleSelectionBodyDragEnd)
  document.removeEventListener("mousemove", handleScrollbarMouseMove)
  document.removeEventListener("mouseup", handleScrollbarMouseUp)
  document.removeEventListener("mousemove", handleSelectionMouseMove)
  document.removeEventListener("mouseup", handleSelectionMouseUp)
})
</script>

<template>
  <div class="flex flex-col border-t border-gray-200 bg-gray-800 select-none">
    <!-- Controls bar -->
    <div class="flex items-center gap-2 px-3 py-1 bg-gray-900">
      <button
        class="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        title="Zoom in (Ctrl+Scroll)"
        @click="zoomAt(viewStart + viewDuration / 2, 0.7)"
      >
        +
      </button>
      <button
        class="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        title="Zoom out (Ctrl+Scroll)"
        @click="zoomAt(viewStart + viewDuration / 2, 1.4)"
      >
        -
      </button>
      <span class="text-[10px] text-gray-500 font-mono">
        {{ formatTimeShort(viewDuration) }}
      </span>
      <div class="mx-1 h-3 w-px bg-gray-700" />
      <button
        class="px-2 py-0.5 text-xs rounded transition-colors"
        :class="snapEnabled ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'"
        title="Snap to segment boundaries"
        @click="snapEnabled = !snapEnabled"
      >
        Snap
      </button>
      <div class="flex-1" />
      <span v-if="selectionStart !== null && selectionEnd !== null" class="text-[10px] text-blue-400 font-mono">
        {{ formatTime(selectionStart) }} - {{ formatTime(selectionEnd) }}
        ({{ (selectionEnd - selectionStart).toFixed(1) }}s)
      </span>
      <button
        v-if="selectionStart !== null"
        class="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
        title="Add clip region at selection"
        @click="handleAddSegment"
      >
        + Clip
      </button>
      <button
        v-if="selectionStart !== null"
        class="px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-400 hover:bg-gray-600 transition-colors"
        title="Clear selection"
        @click="clearSelection"
      >
        x
      </button>
      <span class="text-[10px] text-gray-600 font-mono ml-2">
        {{ formatTime(viewStart) }} / {{ formatTime(viewEnd) }}
      </span>
    </div>

    <!-- Ruler area -->
    <div ref="rulerRef" class="relative h-28 overflow-hidden">
      <!-- Time marks (top strip - click to seek) -->
      <div
        class="absolute top-0 left-0 right-0 h-6 cursor-pointer bg-gray-850"
        @mousedown.stop="handleTimecodeClick"
      >
        <span
          v-for="(mark, i) in timeMarks"
          :key="i"
          class="absolute text-[9px] text-gray-500 -translate-x-1/2 top-1 font-mono"
          :style="{ left: mark.percent + '%' }"
        >
          {{ mark.label }}
        </span>
      </div>

      <!-- Tick lines -->
      <div class="absolute top-5 left-0 right-0 bottom-8">
        <div
          v-for="(mark, i) in timeMarks"
          :key="'tick-' + i"
          class="absolute top-0 w-px h-full bg-gray-700 opacity-50"
          :style="{ left: mark.percent + '%' }"
        />
      </div>

      <!-- Selection area (middle - click/drag to select range) -->
      <div
        class="absolute top-5 left-0 right-0 bottom-8 cursor-crosshair"
        @mousedown="handleSelectionMouseDown"
      >
        <!-- Selection highlight -->
        <div
          v-if="selectionVisible"
          class="absolute top-0 bottom-0 bg-blue-500/20 border-y border-blue-400/40 pointer-events-none"
          :style="{
            left: selectionLeftPercent + '%',
            width: selectionWidthPercent + '%',
          }"
        >
          <!-- Left handle -->
          <div
            class="absolute top-0 bottom-0 left-0 w-2 bg-blue-400/50 cursor-ew-resize hover:bg-blue-400/80 pointer-events-auto"
          />
          <!-- Right handle -->
          <div
            class="absolute top-0 bottom-0 right-0 w-2 bg-blue-400/50 cursor-ew-resize hover:bg-blue-400/80 pointer-events-auto"
          />
        </div>

        <!-- Segment blocks -->
        <div
          v-for="block in visibleBlocks"
          :key="block.id"
          class="absolute top-0 bottom-0 cursor-pointer transition-opacity hover:opacity-80 rounded-sm"
          :class="{
            'bg-blue-500/40': block.type === 'subtitle' && !block.editStatus,
            'bg-yellow-500/40': block.editStatus === 'pending',
            'bg-red-500/40 opacity-60': block.editStatus === 'confirmed',
            'bg-green-500/40': block.editStatus === 'rejected',
            'bg-gray-600/40': block.type === 'silence' && !block.editStatus,
          }"
          :style="{
            left: block.leftPercent + '%',
            width: block.widthPercent + '%',
          }"
          :title="block.text"
          @mousedown.stop
          @click.stop="handleBlockClick(block.id, $event)"
        >
          <span
            v-if="block.widthPercent > 4"
            class="text-[9px] text-gray-300 px-0.5 truncate block leading-6"
          >
            {{ block.text }}
          </span>
        </div>
      </div>

      <!-- Playhead -->
      <div
        v-if="playheadVisible"
        class="absolute top-0 bottom-0 w-0.5 bg-red-500 z-10 pointer-events-none"
        :style="{ left: playheadPercent + '%' }"
      >
        <div class="absolute -top-0 -left-1 w-2.5 h-2 bg-red-500 rounded-full" />
      </div>
    </div>

    <!-- Scrollbar -->
    <div
      ref="scrollbarRef"
      class="relative h-4 bg-gray-900 cursor-pointer"
      @mousedown="handleScrollbarMouseDown"
    >
      <!-- Track -->
      <div class="absolute inset-x-2 top-1 bottom-1 bg-gray-700 rounded-full" />
      <!-- Thumb -->
      <div
        class="absolute top-0.5 bottom-0.5 bg-gray-500 rounded-full hover:bg-gray-400 transition-colors"
        :style="{
          left: 'calc(' + thumbLeft + '% + 8px)',
          width: 'calc(' + thumbWidth + '% - 16px)',
          minWidth: '20px',
        }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, onMounted, onUnmounted } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { buildSegmentStateMap } from "@/utils/segmentHelpers"
import type { SegmentState } from "@/utils/segmentHelpers"
import { openContextMenu } from "@/utils/contextMenuManager"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import SegmentBlock from "./SegmentBlock.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  currentTime?: number
  duration?: number
  /** v2.1.1 A-03: edit mode interception for structural ops */
  globalEditMode?: boolean
  /**
   * v3.0.2 M3-2: row window (multi-row mode). When set, cross-row blocks
   * get continuesFrom/continuesTo markers and trim handles render only
   * for edges inside the row. Undefined = single-window (basic) behavior.
   */
  rowStart?: number
  rowEnd?: number
  /** v3.0.2 M3-2 (③): frozen pointer->time converter (multi-row trim). */
  getTimeFromPointer?: (clientX: number) => number
  /**
   * v3.0.2 M5-3: empty-area click semantics. "add" (default, basic) keeps
   * the v3.0.1 add-segment behavior EXACTLY; "seek" (multi, injected by
   * WaveformRow) clears selection and hands the press to the orchestrator
   * (scrub / Ctrl-create / Shift-marquee via empty-press). Undefined = "add".
   *
   * v3.0.4 M4-2 (P3-6): "range" (basic direct-child path) hands the press
   * to the orchestrator as `range-press` -- the editor runs the range
   * marquee + confirmation bubble. Payload shape = empty-press.
   */
  emptyAreaMode?: "add" | "seek" | "range"
  /**
   * v3.0.2 smoke fix: when the PARENT already owns the badge clearance
   * (multi-row main-area wrapper sits at top-6), the layer fills its
   * container (inset-0) instead of re-applying top-6 bottom-0 -- the
   * double 24px offset crushed the blocks area at small row heights
   * (64/80px showed nothing). Default false = basic unchanged.
   */
  fillContainer?: boolean
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
  /** v3.0.1 M4-3: forwarded from SegmentBlock (Phase 3 linkage consumes). */
  "trim-end": [payload: { segmentId: string; field: "start" | "end"; value: number; altKey: boolean }]
  /** v3.0.2 M5-3: seek-mode empty press (row forwards to the editor). */
  "empty-press": [
    payload: { clientX: number; clientY: number; ctrlKey: boolean; shiftKey: boolean; time: number },
  ]
  /** v3.0.2 M5-3: seek-mode empty double click (play/pause). */
  "empty-double-click": []
  /** v3.0.4 M4-2 (P3-6): range-mode empty press (payload shape = empty-press). */
  "range-press": [
    payload: { clientX: number; clientY: number; ctrlKey: boolean; shiftKey: boolean; time: number },
  ]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

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
  /** v3.0.2: cross-row continuation markers (row-window mode only). */
  continuesFrom?: boolean
  continuesTo?: boolean
}

interface EditRangeBlock {
  edit: EditDecision
  /** v3.0.4 M4-3 (P3-8): three-state inputs -- action drives the stripe
   * color axis (red delete / blue keep), status drives the opacity axis
   * (pending dims). Rejected is NOT filtered here (status quo kept). */
  action: EditDecision["action"]
  status: EditDecision["status"]
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
        continuesFrom:
          props.rowStart !== undefined ? seg.start < props.rowStart - 1e-6 : undefined,
        continuesTo:
          props.rowEnd !== undefined ? seg.end > props.rowEnd + 1e-6 : undefined,
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
        action: e.action,
        status: e.status,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
      }
    })
})

// v3.0.4 M4-3 (P3-8): overlay three-state styling. Two orthogonal axes:
// color = action (red delete / blue keep), opacity = status (pending dims
// to 50%). The confirmed-delete string below is BYTE-IDENTICAL to the
// v3.0.3 stripe -- it must stay that way (SPEC M4-3 hard requirement).
const EDIT_RANGE_RED_BOX = "border border-red-400/60 bg-red-300/30"
const EDIT_RANGE_BLUE_BOX = "border border-blue-400/60 bg-blue-300/30"
const EDIT_RANGE_RED_HATCH = "rgba(239,68,68,0.15)"
const EDIT_RANGE_BLUE_HATCH = "rgba(59,130,246,0.15)"

function editRangeClasses(block: EditRangeBlock): string {
  const box = block.action === "keep" ? EDIT_RANGE_BLUE_BOX : EDIT_RANGE_RED_BOX
  return block.status === "pending"
    ? `absolute top-0 bottom-0 ${box} pointer-events-none opacity-50`
    : `absolute top-0 bottom-0 ${box} pointer-events-none`
}

function editRangeHatchStyle(block: EditRangeBlock): { backgroundImage: string } {
  const hatch = block.action === "keep" ? EDIT_RANGE_BLUE_HATCH : EDIT_RANGE_RED_HATCH
  return {
    backgroundImage:
      `repeating-linear-gradient(45deg, transparent, transparent 3px, ${hatch} 3px, ${hatch} 6px)`,
  }
}

function handleEmptyClick(e: MouseEvent) {
  // v3.0.2 M5-3: dual empty-area semantics. "seek" (multi) clears the
  // row-local selection and forwards the press (modifiers included) so the
  // orchestrator can route scrub / Ctrl-create / Shift-marquee; "add"
  // (default/basic) is the untouched v3.0.1 path.
  // v3.0.4 M4-2 (P3-6): "range" (basic direct-child) forwards the press the
  // same way as "seek" but as `range-press` -- the editor owns the range
  // marquee + bubble. Branch sits BEFORE "seek" (SPEC wiring point 2).
  if (props.emptyAreaMode === "range") {
    selectedBlockId.value = null
    closeContextMenu()
    emit("range-press", {
      clientX: e.clientX,
      clientY: e.clientY,
      ctrlKey: e.ctrlKey,
      shiftKey: e.shiftKey,
      time: metrics.getTimeFromX(e.clientX),
    })
    return
  }
  if (props.emptyAreaMode === "seek") {
    selectedBlockId.value = null
    closeContextMenu()
    emit("empty-press", {
      clientX: e.clientX,
      clientY: e.clientY,
      ctrlKey: e.ctrlKey,
      shiftKey: e.shiftKey,
      time: metrics.getTimeFromX(e.clientX),
    })
    return
  }
  const time = metrics.getTimeFromX(e.clientX)
  emit("add-segment", time, time + 0.5)
}

/** v3.0.2 M5-3: double-click empty area in seek mode toggles playback. */
function handleEmptyDoubleClick() {
  if (props.emptyAreaMode === "seek") emit("empty-double-click")
}

function handleBlockContextMenu(segmentId: string, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  // Mutex FIRST: the previous menu's close fn nulls this SAME ref -- if we
  // set the new state before registering, the close wiped it (reported:
  // right-click-close then the next right-click opened nothing).
  openContextMenu(() => { contextMenu.value = null })
  selectedBlockId.value = segmentId
  contextMenu.value = { x: e.clientX, y: e.clientY, segmentId }
}

function handleBlockClick(seg: Segment) {
  selectedBlockId.value = null
  emit("seek-segment", seg)
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
    class="absolute inset-x-0 focus:outline-none"
    :class="fillContainer ? 'inset-0' : 'top-6 bottom-0'"
    tabindex="0"
    @mousedown="focusContainer"
    @mousedown.self="handleEmptyClick"
    @dblclick.self="handleEmptyDoubleClick"
    @keydown="handleKeyDown"
    @click.self="selectedBlockId = null; closeContextMenu()"
  >
    <SegmentBlock
      v-for="block in visibleBlocks"
      :key="block.seg.id"
      :seg="block.seg"
      :left-percent="block.leftPercent"
      :width-percent="block.widthPercent"
      :state="block.state"
      :segments="segments"
      :selected="selectedBlockId === block.seg.id"
      :update-time="updateTime"
      :current-time="currentTime"
      :duration="duration"
      :global-edit-mode="globalEditMode"
      :continues-from="block.continuesFrom"
      :continues-to="block.continuesTo"
      :row-start="rowStart"
      :row-end="rowEnd"
      :get-time-from-pointer="getTimeFromPointer"
      @select-range="(s, e) => emit('select-range', s, e)"
      @seek-segment="handleBlockClick"
      @contextmenu="handleBlockContextMenu"
      @trim-end="emit('trim-end', $event)"
      @toast="emit('toast', $event)"
    />

    <!-- Edit range overlays (e.g., subtitle trim delete ranges).
         v3.0.4 M4-3 (P3-8): three-state -- color axis = action (red
         delete / blue keep), opacity axis = status (pending dims to
         opacity-50). confirmed delete renders the v3.0.3 red stripe
         byte-for-byte; rejected is NOT filtered (status quo kept). -->
    <div
      v-for="rangeBlock in visibleEditRanges"
      :key="rangeBlock.edit.id"
      :class="editRangeClasses(rangeBlock)"
      :style="{
        left: rangeBlock.leftPercent + '%',
        width: rangeBlock.widthPercent + '%',
      }"
      :title="`Delete range: ${rangeBlock.edit.start.toFixed(1)}s - ${rangeBlock.edit.end.toFixed(1)}s`"
    >
      <div class="h-full w-full" :style="editRangeHatchStyle(rangeBlock)" />
    </div>

    <!-- Context Menu (R9.4: kbd badges turn the menu into a cheat sheet --
         only shortcuts that actually exist get a badge) -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-dropdown bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[140px]"
        :style="{ left: contextMenu.x + 'px', top: Math.min(contextMenu.y, menuMaxY) + 'px' }"
        @click="closeContextMenu"
      >
        <button
          class="w-full flex items-center justify-between gap-3 text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="splitSelectedAtCursor"
        >
          <span>按时间指针分割</span>
        </button>
        <button
          class="w-full flex items-center justify-between gap-3 text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="splitSelectedAtMidpoint"
        >
          <span>从中点分割</span>
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          class="w-full flex items-center justify-between gap-3 text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
          @click="deleteSelected"
        >
          <span>删除</span>
          <kbd
            data-test="menu-kbd-delete"
            class="rounded border border-gray-200 bg-gray-50 px-1 font-mono text-[10px] leading-4 text-gray-400"
          >Del</kbd>
        </button>
      </div>
    </Teleport>
  </div>
</template>

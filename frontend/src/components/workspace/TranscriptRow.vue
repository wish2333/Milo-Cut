<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from "vue"
import type { Segment } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"
import { openContextMenu, closeContextMenu as closeContextMenuManager } from "@/utils/contextMenuManager"

const props = defineProps<{
  segment: Segment
  displayStatus?: string
  styleClass?: string
  isSelected?: boolean
  isAdjacentHighlighted?: boolean
  globalEditMode?: boolean
  // v2.1.1 M4-1: multi-select mode
  selectionMode?: boolean
  isMultiSelected?: boolean
  /** v2.1.1: waveform playhead time for split-at-cursor */
  currentTime?: number
  /** v2.1.1 A-2.1: playhead is currently inside this segment's [start, end] */
  isPlayheadInside?: boolean
  /** v2.1.1 A-2.1: externally-driven temporary highlight (e.g. SuggestionPanel click) */
  isHighlighted?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
  "delete": []
  // v2.1.1 M4-1/M4-3: selection click + split
  "segment-click": [segmentId: string, event: MouseEvent]
  "toggle-multi-selected": []
  "split": []
  "split-at-pointer": [position: number]
  /** v2.1.1 A-03: edit mode toast notification */
  toast: [msg: string]
  // Spec-6 §11.5.2: right-click add to highlights
  "add-to-highlight": [segmentId: string]
}>()

// Context menu
const contextMenu = ref<{ x: number; y: number } | null>(null)

function handleContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  contextMenu.value = { x: e.clientX, y: e.clientY }
  openContextMenu(() => { contextMenu.value = null })
}

// v2.1.1 A-02: distinguish left-click edit from right-click menu on time stamps
function onTimeMouseDown(field: "start" | "end", e: MouseEvent) {
  // e.button === 0 is left, e.button === 2 is right
  if (e.button !== 0) {
    // Right-click: do nothing, let contextmenu event fire normally
    return
  }
  // Left-click: stop propagation and enter time edit mode
  e.stopPropagation()
  e.preventDefault()
  startTimeEdit(field, e)
}

function closeContextMenu() {
  contextMenu.value = null
  closeContextMenuManager()
}

// v2.1.1 A-03: menu handlers that check globalEditMode before structural ops
function handleSplitAtPointer() {
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  emit("split-at-pointer", props.currentTime ?? 0)
  closeContextMenu()
}

function handleSplitAtMidpoint() {
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  emit("split")
  closeContextMenu()
}

function handleDeleteSegment() {
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  emit("delete")
  closeContextMenu()
}

// Text editing
const isEditingText = ref(false)
const editText = ref("")
const originalText = ref("")

// Time editing (click on time value)
const editingTimeField = ref<"start" | "end" | null>(null)
const editingTimeValue = ref("")
const editingTimeSeconds = ref<number>(0)
const timeInputRef = ref<HTMLInputElement | null>(null)

function startTimeEdit(field: "start" | "end", e: MouseEvent) {
  e.stopPropagation()
  const seconds = field === "start" ? props.segment.start : props.segment.end
  editingTimeSeconds.value = seconds
  editingTimeValue.value = formatTime(seconds)
  editingTimeField.value = field
  nextTick(() => timeInputRef.value?.select())
}

function applyTimeEdit() {
  // Prefer parsed input value (user may have typed manually)
  const parsed = parseTime(editingTimeValue.value)
  const finalSeconds = parsed !== null ? parsed : editingTimeSeconds.value
  if (editingTimeField.value) {
    emit("update-time", props.segment.id, editingTimeField.value, finalSeconds)
  }
  editingTimeField.value = null
}

function cancelTimeEdit() {
  editingTimeField.value = null
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    applyTimeEdit()
  } else if (e.key === "Escape") {
    cancelTimeEdit()
  } else if (e.key === "ArrowUp") {
    // v2.1.1 M4-2: ArrowUp = +0.1s (Shift = +1.0s)
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    editingTimeSeconds.value += step
    editingTimeValue.value = formatTime(editingTimeSeconds.value)
  } else if (e.key === "ArrowDown") {
    // v2.1.1 M4-2: ArrowDown = -0.1s (Shift = -1.0s)
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    editingTimeSeconds.value = Math.max(0, editingTimeSeconds.value - step)
    editingTimeValue.value = formatTime(editingTimeSeconds.value)
  }
}

// Text edit functions
function startEdit() {
  originalText.value = props.segment.text
  editText.value = props.segment.text
  isEditingText.value = true
}

function saveEdit() {
  if (editText.value !== props.segment.text) {
    emit("update-text", props.segment.id, editText.value)
  }
  isEditingText.value = false
}

function cancelEdit() {
  editText.value = originalText.value
  isEditingText.value = false
}

// Enter edit mode when globalEditMode turns on, save when it turns off

onMounted(() => {
  if (props.globalEditMode) startEdit()
})
watch(() => props.globalEditMode, (val) => {
  if (val && !isEditingText.value) {
    startEdit()
  } else if (!val && isEditingText.value) {
    saveEdit()
  }
})

// v2.1.1 A-2.2: drag-out text selection can slip past the input boundary and
// trigger blur mid-drag -- the user is still selecting text, not done editing.
// Defer the save by 150ms and re-check focus: if focus has returned to any
// edit-text-input (continued drag, or user clicked another row's edit field),
// treat the blur as a non-commit and keep editing mode on.
let blurSaveTimer: ReturnType<typeof setTimeout> | null = null
function handleTextEditBlur() {
  if (props.globalEditMode) return
  if (blurSaveTimer) clearTimeout(blurSaveTimer)
  blurSaveTimer = setTimeout(() => {
    const active = document.activeElement as HTMLElement | null
    if (active && active.tagName === "INPUT" && active.classList.contains("edit-text-input")) {
      // Focus is back on an edit input -- this was a drag-out, ignore the blur.
      return
    }
    saveEdit()
  }, 150)
}

function handleTextEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") saveEdit()
  else if (e.key === "Escape") cancelEdit()
}

// Row click: in selection mode toggle selection; otherwise seek to segment.
function handleRowClick(e: MouseEvent) {
  if (editingTimeField.value) return
  // v2.1.1 M4-1: selection mode intercepts the click
  if (props.selectionMode) {
    emit("segment-click", props.segment.id, e)
    return
  }
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()
  }
  emit("seek", props.segment.start)
}

const statusClass = computed(() => {
  switch (props.styleClass) {
    case "masked": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "kept": return "border-l-3 border-green-400 bg-green-50"
    default:
      if (props.isAdjacentHighlighted) return "border-l-3 border-amber-400 bg-amber-50"
      return ""
  }
})
</script>

<template>
  <div
    class="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
    :class="[statusClass, {
      'ring-1 ring-blue-500': isSelected && !isMultiSelected,
      'ring-2 ring-blue-500 bg-blue-50': isMultiSelected,
      'bg-blue-50 border-l-2 border-blue-400': isPlayheadInside && !isSelected && !isMultiSelected && !isHighlighted,
      'ring-2 ring-yellow-400 bg-yellow-50': isHighlighted,
    }]" 
    :data-segment-id="segment.id"
    @click="handleRowClick"
    @contextmenu="handleContextMenu"
  >
    <!-- Multi-select indicator (selection mode) -->
    <div
      v-if="selectionMode"
      class="absolute left-0 top-0 bottom-0 w-1"
      :class="isMultiSelected ? 'bg-blue-500' : 'bg-transparent'"
    ></div>
    <!-- Time column: fixed width, no overlap -->
    <div class="text-xs text-gray-400 w-[150px] shrink-0 pt-0.5 font-mono overflow-hidden whitespace-nowrap">
      <template v-if="editingTimeField === 'start'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit (Arrows = ±0.1s)" @mousedown="onTimeMouseDown('start', $event)">{{ formatTime(segment.start) }}</span>
      </template>
      <span class="mx-0.5">&rarr;</span>
      <template v-if="editingTimeField === 'end'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit (Arrows = ±0.1s)" @mousedown="onTimeMouseDown('end', $event)">{{ formatTime(segment.end) }}</span>
      </template>
    </div>

    <!-- Text column -->
    <div class="flex-1 min-w-0 overflow-hidden">
      <input
        v-if="isEditingText"
        v-model="editText"
        class="edit-text-input w-full min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm outline-none box-border"
        @blur="handleTextEditBlur"
        @keydown="handleTextEditKeydown"
        @mousedown.stop
        @click.stop
      />
      <span v-else class="text-sm block truncate">{{ segment.text }}</span>
    </div>

    <!-- Edit/Save button -->
    <div class="flex items-center gap-1 shrink-0">
      <template v-if="isEditingText">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 cursor-pointer hover:bg-blue-200 transition-colors"
          title="Save changes"
          @click.stop="saveEdit"
        >
          保存
        </span>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 cursor-pointer hover:bg-gray-200 transition-colors"
          title="Cancel editing"
          @click.stop="cancelEdit"
        >
          取消
        </span>
      </template>
      <template v-else>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 cursor-pointer hover:bg-gray-200 transition-colors"
          title="Edit text"
          @click.stop="startEdit"
        >
          编辑
        </span>
      </template>
    </div>

    <!-- Status column -->
    <div class="flex items-center gap-1 shrink-0">
      <template v-if="displayStatus === 'pending'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 cursor-pointer hover:bg-yellow-200 transition-colors"
          title="Click to confirm delete"
          @click.stop="emit('confirm-edit')"
        >
          建议删除
        </span>
        <button
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
          title="Keep this segment"
          @click.stop="emit('reject-edit')"
        >
          保留
        </button>
      </template>
      <template v-else-if="displayStatus === 'confirmed'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 cursor-pointer hover:bg-red-200 transition-colors"
          title="Click to keep"
          @click.stop="emit('toggle-status')"
        >
          已删除
        </span>
      </template>
      <template v-else-if="displayStatus === 'rejected'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
          title="Click to delete"
          @click.stop="emit('toggle-status')"
        >
          已保留
        </span>
      </template>
      <template v-else>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 cursor-pointer hover:bg-gray-200 transition-colors"
          title="Click to mark for deletion"
          @click.stop="emit('toggle-status')"
        >
          无标注
        </span>
      </template>
    </div>
    <!-- Context Menu -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-[9999] bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[140px]"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click="closeContextMenu"
      >
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="startEdit"
        >
          编辑文本
        </button>
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          @click="emit('toggle-status')"
        >
          {{ displayStatus === 'confirmed' ? '取消删除' : '标记删除' }}
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          v-if="isPlayheadInside"
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          title="在时间指针位置分割"
          @click="handleSplitAtPointer"
        >
          从时间指针分割
        </button>
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          title="从此段中间分为两段"
          @click="handleSplitAtMidpoint"
        >
          从中点分割
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-blue-600 hover:bg-blue-50 transition-colors"
          @click="emit('add-to-highlight', segment.id); closeContextMenu()"
        >
          加入精华
        </button>
        <div class="border-t border-gray-100 my-1" />
        <button
          class="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
          @click="handleDeleteSegment"
        >
          删除段落
        </button>
      </div>
    </Teleport>
  </div>
</template>

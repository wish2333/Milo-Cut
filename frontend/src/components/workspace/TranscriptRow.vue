<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from "vue"
import type { Segment } from "@/types/project"
import { formatTime, formatTimeShort, parseTime } from "@/utils/format"
import { openContextMenu, closeContextMenu as closeContextMenuManager } from "@/utils/contextMenuManager"

const props = defineProps<{
  segment: Segment
  /**
   * v3.0.3 M1-2 (P1-2): row variant. "main" = v3.0.2 behavior untouched
   * (status column, edit buttons, context menu, click-to-edit times).
   * "track" = extension-track list row: display-only text/start/end +
   * duration + binding mark, no main-track edit machinery.
   */
  variant?: "main" | "track"
  /** v3.0.3 M1-2: segment has a main-track binding (linkage mark). */
  isBound?: boolean
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
  /** v3.0.0 M7-2: unsaved edit draft restored on remount after virtual-scroll unmount */
  draft?: string | null
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
  // v3.0.0 M7-2: draft cache sync (null clears the stored draft)
  "draft-change": [segmentId: string, text: string | null]
  // ---- v3.0.3 M1-3/M1-4: track-variant entries (segment/track ids are
  // bound by the parent -- Timeline attaches activeTrackId) ----
  /** Text committed from the track row editor (dblclick / menu). */
  "track-text": [text: string]
  /** Time field committed from the track row stamp editor. */
  "track-time": [field: "start" | "end", value: number]
  /** Delete this track subtitle (no confirm -- undo covers, 3.0.2 ruling). */
  "track-delete": []
}>()

// Context menu
const contextMenu = ref<{ x: number; y: number } | null>(null)

const isTrackVariant = computed(() => props.variant === "track")

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

// v3.0.3 M1-4: track-row menu actions -- 定位 / 编辑 / 删除此条字幕.
// Delete has NO confirm dialog: undo covers it (3.0.2 ruling).
function handleTrackSeek() {
  emit("seek", props.segment.start)
  closeContextMenu()
}

function handleTrackEdit() {
  startEdit()
  closeContextMenu()
}

function handleTrackDelete() {
  emit("track-delete")
  closeContextMenu()
}

// -- v3.0.3 M3 (S3): config-driven menu with optional kbd badges -----------
//
// Badges annotate REAL shortcuts only (R9.4 principle: no invented
// shortcuts -- ShortcutsSettingsTab registry). Per that registry exactly
// one menu action has one: 标记删除 = Delete (selection-mode main rows).
// Everything else renders text-only; `kbd` absent -> no <kbd> node.
interface RowMenuItem {
  id: string
  label: string
  /** Registered shortcut label (ShortcutsSettingsTab registry). */
  kbd?: string
  tone?: "default" | "primary" | "danger"
  dividerBefore?: boolean
  title?: string
  /** false = conditionally hidden (从时间指针分割 needs the playhead). */
  show?: boolean
  action: () => void
}

const toneClass: Record<NonNullable<RowMenuItem["tone"]> | "default", string> = {
  default: "text-gray-700 hover:bg-gray-50",
  primary: "text-blue-600 hover:bg-blue-50",
  danger: "text-red-600 hover:bg-red-50",
}

const trackMenuItems = computed<RowMenuItem[]>(() => [
  { id: "track-seek", label: "定位", action: handleTrackSeek },
  { id: "track-edit", label: "编辑", action: handleTrackEdit },
  {
    id: "track-delete",
    label: "删除此条字幕",
    tone: "danger",
    dividerBefore: true,
    action: handleTrackDelete,
  },
])

const mainMenuItems = computed<RowMenuItem[]>(() => [
  { id: "edit-text", label: "编辑文本", action: startEdit },
  {
    id: "toggle-status",
    label: props.displayStatus === "confirmed" ? "取消删除" : "标记删除",
    kbd: "Del",
    action: () => emit("toggle-status"),
  },
  {
    id: "split-pointer",
    label: "从时间指针分割",
    title: "在时间指针位置分割",
    show: props.isPlayheadInside,
    action: handleSplitAtPointer,
  },
  {
    id: "split-mid",
    label: "从中点分割",
    title: "从此段中间分为两段",
    dividerBefore: true,
    action: handleSplitAtMidpoint,
  },
  {
    id: "highlight",
    label: "加入精华",
    tone: "primary",
    dividerBefore: true,
    action: () => {
      emit("add-to-highlight", props.segment.id)
      closeContextMenu()
    },
  },
  {
    id: "delete-segment",
    label: "删除段落",
    tone: "danger",
    dividerBefore: true,
    action: handleDeleteSegment,
  },
])

const activeMenuItems = computed<RowMenuItem[]>(() =>
  isTrackVariant.value ? trackMenuItems.value : mainMenuItems.value,
)

// Text editing
const isEditingText = ref(false)
const editText = ref("")
const originalText = ref("")

// v3.0.0 M7-2: virtual scrolling unmounts rows that leave the window. The
// unsaved draft is mirrored to the parent (Timeline) on every keystroke and
// restored in startEdit(), so scrolling never loses an in-progress edit.
watch(editText, (val) => {
  if (isEditingText.value) emit("draft-change", props.segment.id, val)
})
function clearDraft() {
  emit("draft-change", props.segment.id, null)
}

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
    // v3.0.3 M1-3: track rows route through the track-time entry (parent
    // attaches the track id); main rows keep the update-time path.
    if (isTrackVariant.value) {
      emit("track-time", editingTimeField.value, finalSeconds)
    } else {
      emit("update-time", props.segment.id, editingTimeField.value, finalSeconds)
    }
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
  if (isEditingText.value) return
  originalText.value = props.segment.text
  editText.value = props.draft ?? props.segment.text
  isEditingText.value = true
}

function saveEdit() {
  if (editText.value !== props.segment.text) {
    // v3.0.3 M1-3: track rows emit the track entry (parent attaches the
    // track id); main rows keep update-text.
    if (isTrackVariant.value) emit("track-text", editText.value)
    else emit("update-text", props.segment.id, editText.value)
  }
  clearDraft()
  isEditingText.value = false
}

function cancelEdit() {
  editText.value = originalText.value
  clearDraft()
  isEditingText.value = false
}

// Enter edit mode when globalEditMode turns on, save when it turns off.
// v3.0.3 M1-3: track rows opt out of the global-edit sweep -- they enter
// editing only via dblclick / their own menu item.
onMounted(() => {
  if (props.globalEditMode && !isTrackVariant.value) startEdit()
})
watch(() => props.globalEditMode, (val) => {
  if (isTrackVariant.value) return
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
  // v3.0.3 M1-3: track rows never join selection mode (M1-1 boundary:
  // selection stays main-track-only).
  if (props.selectionMode && !isTrackVariant.value) {
    emit("segment-click", props.segment.id, e)
    return
  }
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()
  }
  emit("seek", props.segment.start)
}

// v3.0.3 M1-3: double-click a track row to edit its text (R1.3 entry).
function handleRowDblclick() {
  if (!isTrackVariant.value) return
  if (editingTimeField.value) return
  startEdit()
}

function handleRowKeydown(e: KeyboardEvent) {
  if (e.key !== "Enter" && e.key !== " ") return
  e.preventDefault()
  if (props.selectionMode) {
    emit("segment-click", props.segment.id, new MouseEvent("click"))
    return
  }
  if (isEditingText.value && !props.globalEditMode) saveEdit()
  emit("seek", props.segment.start)
}

const statusClass = computed(() => {
  switch (props.styleClass) {
    case "masked": return "border-l-3 border-red-400 bg-status-confirmed line-through opacity-60"
    case "kept": return "border-l-3 border-green-400 bg-status-rejected"
    default:
      if (props.isAdjacentHighlighted) return "border-l-3 border-amber-400 bg-status-pending"
      return ""
  }
})

// v3.0.3 M1-2: track-row duration label (same format utilities as the
// main row; the backend clamp keeps end >= start).
const durationLabel = computed(() => formatTimeShort(Math.max(0, props.segment.end - props.segment.start)))
</script>

<template>
  <div
    class="flex min-h-[52px] cursor-pointer items-start gap-3 px-3 py-3 transition-colors hover:bg-parchment"
    tabindex="0"
    :class="[statusClass, {
      'ring-1 ring-blue-500': isSelected && !isMultiSelected,
      'ring-2 ring-primary bg-primary-soft': isMultiSelected,
      'bg-primary-soft border-l-2 border-primary': isPlayheadInside && !isSelected && !isMultiSelected && !isHighlighted,
      'ring-2 ring-amber-400 bg-status-pending': isHighlighted,
    }]" 
    :data-segment-id="segment.id"
    @click="handleRowClick"
    @dblclick="handleRowDblclick"
    @keydown="handleRowKeydown"
    @contextmenu="handleContextMenu"
  >
    <!-- Multi-select indicator (selection mode) -->
    <div
      v-if="selectionMode"
      class="absolute left-0 top-0 bottom-0 w-1"
      :class="isMultiSelected ? 'bg-blue-500' : 'bg-transparent'"
    ></div>
    <!-- Time column: fixed width, no overlap. Track variant (v3.0.3
         M1-3): same click-to-edit stamps, routed via track-time. -->
    <div class="w-[150px] shrink-0 overflow-hidden whitespace-nowrap pt-0.5 font-mono text-xs text-ink-muted">
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
      <template v-else-if="isTrackVariant">
        <span data-test="track-start" class="cursor-pointer hover:text-blue-500 hover:underline" title="点击编辑开始时间（±0.1s）" @mousedown="onTimeMouseDown('start', $event)">{{ formatTime(segment.start) }}</span>
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
      <template v-else-if="isTrackVariant">
        <span data-test="track-end" class="cursor-pointer hover:text-blue-500 hover:underline" title="点击编辑结束时间（±0.1s）" @mousedown="onTimeMouseDown('end', $event)">{{ formatTime(segment.end) }}</span>
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
      <span v-else class="block truncate text-base leading-6">{{ segment.text }}</span>
    </div>

    <!-- Edit/Save button (main variant only; track rows enter editing via
         their own entry in M1-3) -->
    <div v-if="!isTrackVariant" class="flex items-center gap-1 shrink-0">
      <template v-if="isEditingText">
        <span
          class="rounded bg-primary-soft px-1.5 py-0.5 text-xs text-primary transition-colors hover:bg-primary/15"
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

    <!-- Status column (main) / duration + binding mark (track, M1-2) -->
    <div v-if="isTrackVariant" class="flex items-center gap-1 shrink-0">
      <span
        data-test="track-duration"
        class="rounded bg-parchment px-1.5 py-0.5 text-xs text-ink-muted"
        :title="`时长 ${durationLabel}`"
      >{{ durationLabel }}</span>
      <span
        v-if="isBound"
        data-test="track-bound-mark"
        class="flex items-center rounded bg-primary-soft px-1 py-0.5 text-primary"
        title="与主轨字幕联动绑定（时间编辑会同步偏移）"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M13.828 10.172a4 4 0 010 5.656l-3 3a4 4 0 01-5.656-5.656l1.5-1.5m7.5-1.5l1.5-1.5a4 4 0 015.656 0 4 4 0 010 5.656l-3 3a4 4 0 01-5.656 0" />
        </svg>
      </span>
    </div>
    <div v-else class="flex items-center gap-1 shrink-0">
      <template v-if="displayStatus === 'pending'">
        <span
          class="rounded bg-status-pending px-1.5 py-0.5 text-xs text-yellow-700 transition-colors hover:bg-yellow-100"
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
          class="rounded bg-status-confirmed px-1.5 py-0.5 text-xs text-red-700 transition-colors hover:bg-red-100"
          title="Click to keep"
          @click.stop="emit('toggle-status')"
        >
          已删除
        </span>
      </template>
      <template v-else-if="displayStatus === 'rejected'">
        <span
          class="rounded bg-status-rejected px-1.5 py-0.5 text-xs text-green-700 transition-colors hover:bg-green-100"
          title="Click to delete"
          @click.stop="emit('toggle-status')"
        >
          已保留
        </span>
      </template>
      <template v-else>
        <span
          class="rounded bg-parchment px-1.5 py-0.5 text-xs text-ink-muted transition-colors hover:bg-hairline"
          title="Click to mark for deletion"
          @click.stop="emit('toggle-status')"
        >
          无标注
        </span>
      </template>
    </div>
    <!-- Context Menu (v3.0.3 M3: config-driven; kbd badges annotate REAL
         shortcuts only -- no badge node when `kbd` is absent) -->
    <Teleport to="body">
      <div
        v-if="contextMenu"
        class="fixed z-dropdown bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[140px]"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click="closeContextMenu"
      >
        <template v-for="item in activeMenuItems" :key="item.id">
          <div v-if="item.dividerBefore" class="border-t border-gray-100 my-1" />
          <button
            v-if="item.show !== false"
            :data-test="item.id === 'track-delete' ? 'track-menu-delete' : undefined"
            :title="item.title"
            class="w-full flex items-center justify-between gap-3 text-left px-3 py-1.5 text-sm transition-colors"
            :class="toneClass[item.tone ?? 'default']"
            @click="item.action()"
          >
            <span>{{ item.label }}</span>
            <kbd
              v-if="item.kbd"
              data-test="menu-kbd"
              class="rounded border border-gray-200 bg-gray-50 px-1 font-mono text-[10px] leading-4 text-gray-400"
            >{{ item.kbd }}</kbd>
          </button>
        </template>
      </div>
    </Teleport>
  </div>
</template>

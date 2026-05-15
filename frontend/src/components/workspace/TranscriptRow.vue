<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from "vue"
import type { Segment } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  displayStatus?: string
  styleClass?: string
  isSelected?: boolean
  globalEditMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
}>()

// Text editing
const isEditingText = ref(false)
const editText = ref("")
const originalText = ref("")

// Time editing (click on time value)
const editingTimeField = ref<"start" | "end" | null>(null)
const editingTimeValue = ref("")
const timeInputRef = ref<HTMLInputElement | null>(null)

function startTimeEdit(field: "start" | "end", e: MouseEvent) {
  e.stopPropagation()
  editingTimeValue.value = formatTime(field === "start" ? props.segment.start : props.segment.end)
  editingTimeField.value = field
  nextTick(() => timeInputRef.value?.select())
}

function applyTimeEdit() {
  const parsed = parseTime(editingTimeValue.value)
  if (parsed !== null && editingTimeField.value) {
    emit("update-time", props.segment.id, editingTimeField.value, parsed)
  }
  editingTimeField.value = null
}

function cancelTimeEdit() {
  editingTimeField.value = null
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") applyTimeEdit()
  else if (e.key === "Escape") cancelTimeEdit()
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

function handleTextEditBlur() {
  if (props.globalEditMode) return
  saveEdit()
}

function handleTextEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") saveEdit()
  else if (e.key === "Escape") cancelEdit()
}

// Row click: seek to segment. In normal mode, also save if editing.
function handleRowClick() {
  if (editingTimeField.value) return
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()
  }
  emit("seek", props.segment.start)
}

const statusClass = computed(() => {
  switch (props.styleClass) {
    case "masked": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "kept": return "border-l-3 border-green-400 bg-green-50"
    default: return ""
  }
})
</script>

<template>
  <div
    class="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
    :class="[statusClass, { 'ring-1 ring-blue-500': isSelected }]"
    :data-segment-id="segment.id"
    @click="handleRowClick"
  >
    <!-- Time column: fixed width, no overlap -->
    <div class="text-xs text-gray-400 w-[130px] shrink-0 pt-0.5 font-mono overflow-hidden whitespace-nowrap">
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
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('start', $event)">{{ formatTime(segment.start) }}</span>
      </template>
      <span class="mx-0.5">→</span>
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
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('end', $event)">{{ formatTime(segment.end) }}</span>
      </template>
    </div>

    <!-- Text column -->
    <div class="flex-1 min-w-0 overflow-hidden">
      <input
        v-if="isEditingText"
        v-model="editText"
        class="w-full min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm outline-none box-border"
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
  </div>
</template>

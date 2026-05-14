<script setup lang="ts">
import { ref, computed } from "vue"
import type { Segment, EditStatus } from "@/types/project"
import { formatTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  editStatus?: EditStatus | null
  isSelected?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "mark-delete": [segmentId: string]
}>()

const isEditing = ref(false)
const editText = ref("")

function handleClick() {
  emit("seek", props.segment.start)
}

function handleDoubleClick() {
  editText.value = props.segment.text
  isEditing.value = true
}

function handleEditBlur() {
  if (editText.value !== props.segment.text) {
    emit("update-text", props.segment.id, editText.value)
  }
  isEditing.value = false
}

function handleEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    handleEditBlur()
  } else if (e.key === "Escape") {
    isEditing.value = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Delete" || e.key === "Backspace") {
    e.preventDefault()
    emit("mark-delete", props.segment.id)
  }
}

const statusClass = computed(() => {
  switch (props.editStatus) {
    case "pending": return "border-l-3 border-yellow-400 bg-yellow-50"
    case "confirmed": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "rejected": return "border-l-3 border-green-400 bg-green-50"
    default: return ""
  }
})
</script>

<template>
  <div
    class="flex items-start gap-3 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
    :class="[statusClass, { 'ring-1 ring-blue-500': isSelected }]"
    tabindex="0"
    @click="handleClick"
    @dblclick="handleDoubleClick"
    @keydown="handleKeydown"
  >
    <span class="text-xs text-gray-400 w-14 shrink-0 pt-0.5 font-mono">
      {{ formatTime(segment.start) }}
    </span>
    <div class="flex-1 min-w-0">
      <input
        v-if="isEditing"
        v-model="editText"
        class="w-full bg-white border border-blue-400 rounded px-1 py-0.5 text-sm outline-none"
        @blur="handleEditBlur"
        @keydown="handleEditKeydown"
      />
      <span v-else class="text-sm">{{ segment.text }}</span>
    </div>
    <span
      v-if="editStatus"
      class="text-xs px-1.5 py-0.5 rounded shrink-0"
      :class="{
        'bg-yellow-100 text-yellow-700': editStatus === 'pending',
        'bg-red-100 text-red-700': editStatus === 'confirmed',
        'bg-green-100 text-green-700': editStatus === 'rejected',
      }"
    >
      {{ editStatus === "pending" ? "待定" : editStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>

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
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
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
    @click="handleClick"
    @dblclick="handleDoubleClick"
  >
    <span class="text-xs text-gray-400 w-28 shrink-0 pt-0.5 font-mono">
      {{ formatTime(segment.start) }} → {{ formatTime(segment.end) }}
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
    <div class="flex items-center gap-1 shrink-0">
      <template v-if="editStatus === 'pending'">
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
      <template v-else-if="editStatus === 'confirmed'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 cursor-pointer hover:bg-red-200 transition-colors"
          title="Click to keep"
          @click.stop="emit('toggle-status')"
        >
          已删除
        </span>
      </template>
      <template v-else-if="editStatus === 'rejected'">
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
          class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
          title="Click to mark for deletion"
          @click.stop="emit('toggle-status')"
        >
          已保留
        </span>
      </template>
    </div>
  </div>
</template>
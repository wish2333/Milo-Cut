<script setup lang="ts">
import { computed, ref, nextTick } from "vue"
import type { Segment } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  displayStatus?: string
  styleClass?: string
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
  "delete": []
}>()

// Time editing
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

function handleRowClick() {
  if (editingTimeField.value) return
  emit("seek", props.segment.start)
}

const duration = computed(() => {
  return (props.segment.end - props.segment.start).toFixed(1)
})
</script>

<template>
  <div
    class="flex items-center gap-2 px-3 h-8 cursor-pointer transition-colors"
    :data-segment-id="segment.id"
    :class="{
      'bg-gray-50': !displayStatus || displayStatus === 'none',
      'bg-yellow-50 border-l-3 border-yellow-400': displayStatus === 'pending',
      'bg-red-50 border-l-3 border-red-400 opacity-60': displayStatus === 'confirmed' || styleClass === 'masked',
      'bg-green-50 border-l-3 border-green-400': styleClass === 'kept',
    }"
    @click="handleRowClick"
  >
    <div class="text-xs text-gray-400 w-[130px] shrink-0 font-mono overflow-hidden whitespace-nowrap">
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
    <span class="text-xs text-gray-500 flex-1 text-center">
      --- 静音 {{ duration }}s ---
    </span>
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
          title="Click to toggle status"
          @click.stop="emit('toggle-status')"
        >
          已删除
        </span>
      </template>
      <template v-else-if="displayStatus === 'rejected'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
          title="Click to toggle status"
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
      <!-- Delete button: always visible -->
      <button
        class="text-xs px-1 py-0.5 rounded text-red-400 hover:bg-red-50 hover:text-red-600 transition-colors"
        title="Delete this silence segment"
        @click.stop="emit('delete')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>
    </div>
  </div>
</template>

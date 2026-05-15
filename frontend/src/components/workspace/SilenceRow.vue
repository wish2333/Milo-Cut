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
    <span
      v-if="displayStatus && displayStatus !== 'none'"
      class="text-xs px-1.5 py-0.5 rounded shrink-0 cursor-pointer transition-colors"
      :class="{
        'bg-yellow-100 text-yellow-700 hover:bg-yellow-200': displayStatus === 'pending',
        'bg-red-100 text-red-700 hover:bg-red-200': displayStatus === 'confirmed',
        'bg-green-100 text-green-700 hover:bg-green-200': displayStatus === 'rejected',
      }"
      title="Click to toggle confirmed/rejected"
      @click.stop="emit('toggle-status')"
    >
      {{ displayStatus === "pending" ? "建议删除" : displayStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>

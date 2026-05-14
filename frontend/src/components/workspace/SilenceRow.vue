<script setup lang="ts">
import { computed } from "vue"
import type { Segment, EditStatus } from "@/types/project"
import { formatTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  editStatus?: EditStatus | null
}>()

const emit = defineEmits<{
  seek: [time: number]
  "toggle-status": []
}>()

function handleClick() {
  emit("seek", props.segment.start)
}

const duration = computed(() => {
  return (props.segment.end - props.segment.start).toFixed(1)
})
</script>

<template>
  <div
    class="flex items-center gap-3 px-3 h-8 cursor-pointer transition-colors"
    :class="{
      'bg-gray-50': !editStatus,
      'bg-yellow-50 border-l-3 border-yellow-400': editStatus === 'pending',
      'bg-red-50 border-l-3 border-red-400 opacity-60': editStatus === 'confirmed',
      'bg-green-50 border-l-3 border-green-400': editStatus === 'rejected',
    }"
    @click="handleClick"
  >
    <span class="text-xs text-gray-400 w-28 shrink-0 font-mono">
      {{ formatTime(segment.start) }} → {{ formatTime(segment.end) }}
    </span>
    <span class="text-xs text-gray-500 flex-1 text-center">
      --- 静音 {{ duration }}s ---
    </span>
    <span
      v-if="editStatus"
      class="text-xs px-1.5 py-0.5 rounded shrink-0 cursor-pointer transition-colors"
      :class="{
        'bg-yellow-100 text-yellow-700 hover:bg-yellow-200': editStatus === 'pending',
        'bg-red-100 text-red-700 hover:bg-red-200': editStatus === 'confirmed',
        'bg-green-100 text-green-700 hover:bg-green-200': editStatus === 'rejected',
      }"
      title="Click to toggle confirmed/rejected"
      @click.stop="emit('toggle-status')"
    >
      {{ editStatus === "pending" ? "建议删除" : editStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import type { Segment, EditStatus } from "@/types/project"

const props = defineProps<{
  segment: Segment
  editStatus?: EditStatus | null
}>()

const emit = defineEmits<{
  seek: [time: number]
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
    class="flex items-center justify-center h-8 cursor-pointer transition-colors"
    :class="{
      'bg-gray-100': !editStatus,
      'bg-yellow-50 border-l-3 border-yellow-400': editStatus === 'pending',
      'bg-red-50 border-l-3 border-red-400 opacity-60': editStatus === 'confirmed',
      'bg-green-50 border-l-3 border-green-400': editStatus === 'rejected',
    }"
    @click="handleClick"
  >
    <span class="text-xs text-gray-500">
      --- 静音 {{ duration }}s ---
    </span>
    <span
      v-if="editStatus"
      class="text-xs px-1.5 py-0.5 rounded ml-2"
      :class="{
        'bg-yellow-100 text-yellow-700': editStatus === 'pending',
        'bg-red-100 text-red-700': editStatus === 'confirmed',
        'bg-green-100 text-green-700': editStatus === 'rejected',
      }"
    >
      {{ editStatus === "pending" ? "建议删除" : editStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>

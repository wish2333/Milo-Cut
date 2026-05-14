<script setup lang="ts">
import { computed } from "vue"
import type { EditSummary } from "@/types/edit"

const props = defineProps<{
  summary: EditSummary
  visible: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const formattedTotal = computed(() => formatDuration(props.summary.total_duration))
const formattedDelete = computed(() => formatDuration(props.summary.delete_duration))
const isWarning = computed(() => props.summary.delete_percent > 40)

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, "0")}`
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('cancel')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-[480px] max-w-[90vw] overflow-hidden">
      <div class="px-6 pt-6 pb-4 text-center">
        <h2 class="text-lg font-semibold text-gray-800">导出汇总摘要</h2>
      </div>

      <div class="flex justify-center gap-8 px-6 pb-4">
        <div class="text-center">
          <div class="text-3xl font-bold text-blue-600">{{ formattedTotal }}</div>
          <div class="text-xs text-gray-500 mt-1">预计时长</div>
        </div>
        <div class="text-center">
          <div class="text-3xl font-bold text-gray-500">-{{ formattedDelete }}</div>
          <div class="text-xs text-gray-500 mt-1">裁剪掉时长</div>
        </div>
        <div class="text-center">
          <div
            class="text-3xl font-bold"
            :class="isWarning ? 'text-red-600' : 'text-blue-600'"
          >
            {{ summary.delete_percent }}%
          </div>
          <div class="text-xs text-gray-500 mt-1">占比</div>
        </div>
      </div>

      <div v-if="summary.warnings.length > 0" class="mx-6 mb-4">
        <div class="text-sm font-medium text-gray-700 mb-2">检测到以下异常情况:</div>
        <div class="space-y-1">
          <div
            v-for="(warning, i) in summary.warnings"
            :key="i"
            class="flex items-start gap-2 px-3 py-2 bg-yellow-50 rounded text-sm text-yellow-800"
          >
            <span class="shrink-0">[!]</span>
            <span>{{ warning }}</span>
          </div>
        </div>
      </div>

      <div v-if="isWarning" class="mx-6 mb-4 px-3 py-2 bg-red-50 rounded text-sm text-red-700">
        删除内容占总时长超过 40%，请确认是否继续导出。
      </div>

      <div class="flex flex-col gap-2 px-6 pb-6">
        <button
          class="w-full py-2.5 rounded-full bg-blue-500 text-white font-medium hover:bg-blue-600 transition-colors"
          @click="emit('confirm')"
        >
          确认导出
        </button>
        <button
          class="w-full py-2.5 rounded-full border border-blue-500 text-blue-500 font-medium hover:bg-blue-50 transition-colors"
          @click="emit('cancel')"
        >
          返回检查
        </button>
      </div>
    </div>
  </div>
</template>

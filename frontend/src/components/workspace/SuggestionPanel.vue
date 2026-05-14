<script setup lang="ts">
import { computed, ref } from "vue"
import type { AnalysisResult, EditDecision, Segment } from "@/types/project"
import { formatTime } from "@/utils/format"

const props = defineProps<{
  analysisResults: AnalysisResult[]
  edits: EditDecision[]
  segments: Segment[]
}>()

const emit = defineEmits<{
  "confirm-edit": [editId: string]
  "reject-edit": [editId: string]
  "confirm-all": []
  "reject-all": []
  "seek": [time: number]
}>()

const expandedGroups = ref<Set<string>>(new Set(["filler", "error"]))

interface GroupedResult {
  type: string
  label: string
  results: AnalysisResult[]
}

const groups = computed<GroupedResult[]>(() => {
  const fillerResults = props.analysisResults.filter(r => r.type === "filler")
  const errorResults = props.analysisResults.filter(r => r.type === "error")
  const result: GroupedResult[] = []
  if (fillerResults.length > 0) {
    result.push({ type: "filler", label: "口头禅", results: fillerResults })
  }
  if (errorResults.length > 0) {
    result.push({ type: "error", label: "口误触发", results: errorResults })
  }
  return result
})

const pendingEdits = computed(() =>
  props.edits.filter(e => e.status === "pending" && e.action === "delete")
)

function toggleGroup(type: string) {
  if (expandedGroups.value.has(type)) {
    expandedGroups.value.delete(type)
  } else {
    expandedGroups.value.add(type)
  }
}

function isExpanded(type: string): boolean {
  return expandedGroups.value.has(type)
}

function getEditForResult(result: AnalysisResult): EditDecision | undefined {
  return props.edits.find(e => e.analysis_id === result.id)
}

function handleSeek(result: AnalysisResult) {
  const seg = props.segments.find(s => result.segment_ids.includes(s.id))
  if (seg) {
    emit("seek", seg.start)
  }
}
</script>

<template>
  <div class="border border-gray-200 rounded-lg overflow-hidden">
    <div class="px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-medium text-gray-700">
        发现 {{ analysisResults.length }} 处建议
        <template v-if="pendingEdits.length > 0">
          | {{ pendingEdits.length }} 处待处理
        </template>
      </span>
    </div>

    <div v-if="groups.length === 0" class="px-3 py-4 text-center text-sm text-gray-400">
      暂无分析结果
    </div>

    <div v-for="group in groups" :key="group.type" class="border-b border-gray-100 last:border-b-0">
      <button
        class="flex items-center justify-between w-full px-3 py-2 hover:bg-gray-50 transition-colors"
        @click="toggleGroup(group.type)"
      >
        <span class="text-sm font-medium">
          {{ isExpanded(group.type) ? "v" : ">" }} {{ group.label }} ({{ group.results.length }})
        </span>
      </button>

      <div v-if="isExpanded(group.type)" class="divide-y divide-gray-50">
        <div
          v-for="result in group.results"
          :key="result.id"
          class="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 cursor-pointer"
          @click="handleSeek(result)"
        >
          <span class="text-xs text-gray-400 w-14 shrink-0 font-mono">
            {{ result.segment_ids.length > 0 ? formatTime(segments.find(s => s.id === result.segment_ids[0])?.start ?? 0) : "" }}
          </span>
          <span class="flex-1 text-sm truncate">
            {{ result.detail }}
          </span>
          <template v-if="getEditForResult(result)">
            <button
              class="text-xs px-2 py-0.5 rounded bg-blue-500 text-white hover:bg-blue-600"
              @click.stop="emit('confirm-edit', getEditForResult(result)!.id)"
            >
              确认
            </button>
            <button
              class="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600 hover:bg-gray-300"
              @click.stop="emit('reject-edit', getEditForResult(result)!.id)"
            >
              忽略
            </button>
          </template>
        </div>
      </div>
    </div>

    <div v-if="pendingEdits.length > 0" class="flex gap-2 px-3 py-2 bg-gray-50">
      <button
        class="flex-1 text-sm px-3 py-1.5 rounded-full bg-blue-500 text-white hover:bg-blue-600 transition-colors"
        @click="emit('confirm-all')"
      >
        全部确认删除
      </button>
      <button
        class="flex-1 text-sm px-3 py-1.5 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
        @click="emit('reject-all')"
      >
        忽略所有建议
      </button>
    </div>
  </div>
</template>

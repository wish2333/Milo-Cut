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

interface SuggestionItem {
  id: string
  start: number
  end: number
  label: string
  type: "filler" | "error" | "silence"
}

interface GroupedResult {
  type: string
  label: string
  items: SuggestionItem[]
}

const groups = computed<GroupedResult[]>(() => {
  const result: GroupedResult[] = []

  // Filler results
  const fillerResults = props.analysisResults.filter(r => r.type === "filler")
  if (fillerResults.length > 0) {
    result.push({
      type: "filler",
      label: "口头禅",
      items: fillerResults.map(r => ({
        id: r.id,
        start: props.segments.find(s => r.segment_ids.includes(s.id))?.start ?? 0,
        end: props.segments.find(s => r.segment_ids.includes(s.id))?.end ?? 0,
        label: r.detail,
        type: "filler" as const,
      })),
    })
  }

  // Error results
  const errorResults = props.analysisResults.filter(r => r.type === "error")
  if (errorResults.length > 0) {
    result.push({
      type: "error",
      label: "口误触发",
      items: errorResults.map(r => ({
        id: r.id,
        start: props.segments.find(s => r.segment_ids.includes(s.id))?.start ?? 0,
        end: props.segments.find(s => r.segment_ids.includes(s.id))?.end ?? 0,
        label: r.detail,
        type: "error" as const,
      })),
    })
  }

  // Silence results
  const silenceEdits = props.edits.filter(
    e => e.source === "silence_detection" && e.status === "pending"
  )
  if (silenceEdits.length > 0) {
    result.push({
      type: "silence",
      label: "静音检测",
      items: silenceEdits.map(e => ({
        id: e.id,
        start: e.start,
        end: e.end,
        label: `静音 ${(e.end - e.start).toFixed(1)}s`,
        type: "silence" as const,
      })),
    })
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

function getEditForItem(item: SuggestionItem): EditDecision | undefined {
  if (item.type === "silence") {
    return props.edits.find(e => e.id === item.id)
  }
  return props.edits.find(e => e.analysis_id === item.id)
}

function handleSeek(item: SuggestionItem) {
  emit("seek", item.start)
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
          {{ isExpanded(group.type) ? "v" : ">" }} {{ group.label }} ({{ group.items.length }})
        </span>
      </button>

      <div v-if="isExpanded(group.type)" class="divide-y divide-gray-50">
        <div
          v-for="item in group.items"
          :key="item.id"
          class="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-50 cursor-pointer"
          @click="handleSeek(item)"
        >
          <span class="text-xs text-gray-400 w-14 shrink-0 font-mono">
            {{ formatTime(item.start) }}
          </span>
          <span class="flex-1 text-sm truncate">
            {{ item.label }}
          </span>
          <template v-if="getEditForItem(item)">
            <button
              class="text-xs px-2 py-0.5 rounded bg-blue-500 text-white hover:bg-blue-600"
              @click.stop="emit('confirm-edit', getEditForItem(item)!.id)"
            >
              确认
            </button>
            <button
              class="text-xs px-2 py-0.5 rounded bg-gray-200 text-gray-600 hover:bg-gray-300"
              @click.stop="emit('reject-edit', getEditForItem(item)!.id)"
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

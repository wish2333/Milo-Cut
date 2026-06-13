<script setup lang="ts">
import { computed } from "vue"
import type { Segment, TopicDriftResult } from "@/types/project"
import { formatTimeShort } from "@/utils/format"

const props = defineProps<{
  results: TopicDriftResult[]
  segments: Segment[]
  loading?: boolean
  progress?: number
  error?: string | null
  llmConfigured: boolean
}>()

const emit = defineEmits<{
  "start-analysis": [topicDescription: string]
  cancel: []
  "accept-all": []
  "reject-all": []
  seek: [time: number]
}>()

// Local input state for topic description
const topicDescription = defineModel<string>("topicDescription", { default: "" })

// Build a segment lookup map for time + text
const segmentMap = computed(() => {
  const m = new Map<string, Segment>()
  for (const s of props.segments) {
    m.set(s.id, s)
  }
  return m
})

interface DisplayItem {
  result: TopicDriftResult
  segment: Segment | undefined
  startTime: number
  textPreview: string
}

// Sort by relevance ascending (lowest relevance first -- most likely to cut)
const sortedItems = computed<DisplayItem[]>(() => {
  return props.results
    .map((r) => {
      const seg = segmentMap.value.get(r.segment_id)
      return {
        result: r,
        segment: seg,
        startTime: seg?.start ?? 0,
        textPreview: seg?.text?.trim() ?? r.topic,
      }
    })
    .sort((a, b) => a.result.relevance - b.result.relevance)
})

const lowRelevanceItems = computed(() =>
  sortedItems.value.filter((i) => i.result.relevance < 0.4),
)

function relevanceClass(relevance: number): string {
  if (relevance >= 0.7) return "bg-green-100 text-green-700 border-green-300"
  if (relevance < 0.4) return "bg-red-100 text-red-700 border-red-300"
  return "bg-yellow-100 text-yellow-700 border-yellow-300"
}

function relevanceLabel(relevance: number): string {
  if (relevance >= 0.7) return "保留"
  if (relevance < 0.4) return "建议删除"
  return "待定"
}

function handleAnalyze() {
  emit("start-analysis", topicDescription.value || "")
}

function handleSeek(item: DisplayItem) {
  emit("seek", item.startTime)
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Header / Controls -->
    <div class="px-3 py-2 border-b border-gray-200 space-y-2">
      <div class="flex items-center gap-2">
        <input
          v-model="topicDescription"
          type="text"
          placeholder="主题描述（可选，如：AI 在教育中的应用）"
          class="flex-1 text-sm px-2 py-1 border border-gray-300 rounded focus:outline-none focus:border-blue-400"
          :disabled="loading || !llmConfigured"
          @keydown.enter="handleAnalyze"
        />
        <button
          v-if="!loading"
          class="text-sm px-3 py-1 rounded bg-blue-500 text-white hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!llmConfigured"
          :title="llmConfigured ? '' : '请先在设置中配置 LLM'"
          @click="handleAnalyze"
        >
          分析
        </button>
        <button
          v-else
          class="text-sm px-3 py-1 rounded bg-gray-500 text-white hover:bg-gray-600 transition-colors"
          @click="emit('cancel')"
        >
          取消
        </button>
      </div>

      <!-- LLM not configured warning -->
      <div v-if="!llmConfigured" class="text-xs text-gray-400">
        需要配置 LLM 才能使用主题漂移分析。请在设置中配置 API Key。
      </div>

      <!-- Error -->
      <div v-if="error" class="text-xs text-red-500">
        {{ error }}
      </div>

      <!-- Progress bar -->
      <div v-if="loading" class="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div
          class="h-full bg-blue-500 transition-all duration-300"
          :style="{ width: `${progress ?? 0}%` }"
        />
      </div>
    </div>

    <!-- Results list -->
    <div class="flex-1 overflow-y-auto">
      <div
        v-if="sortedItems.length === 0 && !loading"
        class="px-3 py-4 text-center text-sm text-gray-400"
      >
        暂无分析结果{{ !llmConfigured ? "" : "，点击「分析」开始" }}
      </div>

      <div
        v-for="item in sortedItems"
        :key="item.result.segment_id"
        class="flex items-start gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer border-b border-gray-50"
        @click="handleSeek(item)"
      >
        <span class="text-xs text-gray-400 w-12 shrink-0 font-mono pt-0.5">
          {{ formatTimeShort(item.startTime) }}
        </span>
        <div class="flex-1 min-w-0">
          <div class="text-sm truncate text-gray-700">
            {{ item.textPreview || "(无文本)" }}
          </div>
          <div v-if="item.result.reason" class="text-xs text-gray-400 truncate mt-0.5">
            {{ item.result.reason }}
          </div>
        </div>
        <span
          class="text-xs px-2 py-0.5 rounded border shrink-0 font-medium"
          :class="relevanceClass(item.result.relevance)"
        >
          {{ relevanceLabel(item.result.relevance) }}
          {{ item.result.relevance.toFixed(2) }}
        </span>
      </div>
    </div>

    <!-- Batch actions -->
    <div
      v-if="lowRelevanceItems.length > 0"
      class="flex gap-2 px-3 py-2 bg-gray-50 border-t border-gray-200"
    >
      <button
        class="flex-1 text-sm px-3 py-1.5 rounded-full bg-red-500 text-white hover:bg-red-600 transition-colors"
        @click="emit('accept-all')"
      >
        接受删除建议 ({{ lowRelevanceItems.length }})
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

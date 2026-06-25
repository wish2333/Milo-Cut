<script setup lang="ts">
/**
 * P3 Semantic Search Bar.
 *
 * Natural language search over transcript segments.
 */
import { computed, ref } from "vue"
import type { Segment } from "@/types/project"
import { call } from "@/bridge"

interface SearchResult {
  segment_id: string
  relevance: number
  match_reason: string
}

const props = defineProps<{
  segments: Segment[]
  llmConfigured: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
}>()

const query = ref("")
const results = ref<SearchResult[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const hasSearched = ref(false)

// Segment lookup map for text preview and time resolution
const segmentMap = computed(() => {
  const m = new Map<string, Segment>()
  for (const s of props.segments) {
    m.set(s.id, s)
  }
  return m
})

interface DisplayResult {
  result: SearchResult
  segment: Segment | undefined
  textPreview: string
  startTime: number
}

// Sort results by relevance descending
const sortedResults = computed<DisplayResult[]>(() => {
  return results.value
    .map((r) => {
      const seg = segmentMap.value.get(r.segment_id)
      const fullText = seg?.text?.trim() ?? ""
      return {
        result: r,
        segment: seg,
        textPreview: fullText.slice(0, 80),
        startTime: seg?.start ?? 0,
      }
    })
    .sort((a, b) => b.result.relevance - a.result.relevance)
})

async function handleSearch() {
  const q = query.value.trim()
  if (!q || loading.value) return
  if (!props.llmConfigured) return

  loading.value = true
  error.value = null
  hasSearched.value = true

  try {
    const res = await call<{ results: SearchResult[]; query: string }>(
      "semantic_search",
      q,
      5,
    )
    if (res.success && res.data) {
      results.value = res.data.results
    } else {
      error.value = res.error ?? "搜索失败"
      results.value = []
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    results.value = []
  } finally {
    loading.value = false
  }
}

function handleSeek(time: number) {
  emit("seek", time)
}

function relevancePercent(relevance: number): number {
  return Math.round(relevance * 100)
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <!-- Not configured warning -->
    <div v-if="!llmConfigured" class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
      <span>请先在设置中配置 LLM 连接</span>
    </div>

    <!-- Search input row -->
    <div class="flex items-center gap-2">
      <input
        v-model="query"
        type="text"
        class="flex-1 rounded border border-gray-300 px-2 py-1 text-xs"
        placeholder="输入自然语言查询，如 '讲性能优化的那段'"
        :disabled="!llmConfigured || loading"
        @keydown.enter="handleSearch"
      />
      <button
        class="rounded bg-blue-500 px-3 py-1 text-xs text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="!llmConfigured || loading || !query.trim()"
        @click="handleSearch"
      >
        <span v-if="loading" class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
        搜索
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">
      <span>{{ error }}</span>
    </div>

    <!-- Results -->
    <div v-if="sortedResults.length > 0" class="flex flex-col gap-1">
      <div
        v-for="item in sortedResults"
        :key="item.result.segment_id"
        class="cursor-pointer rounded-lg border border-gray-200 bg-white p-2 text-xs transition-colors hover:bg-gray-50"
        @click="handleSeek(item.startTime)"
      >
        <div class="flex items-start gap-2">
          <div class="flex-1">
            <p class="line-clamp-2 text-gray-600">{{ item.textPreview }}</p>
            <p class="mt-1 text-gray-400">{{ item.result.match_reason }}</p>
          </div>
          <span class="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-medium text-blue-700 shrink-0">
            {{ relevancePercent(item.result.relevance) }}%
          </span>
        </div>
      </div>
    </div>

    <!-- Empty state (searched but no results) -->
    <div
      v-else-if="hasSearched && !loading && !error"
      class="py-4 text-center text-xs text-gray-400"
    >
      未找到相关片段
    </div>

    <!-- Initial empty state -->
    <div
      v-else-if="!hasSearched && !loading"
      class="py-2 text-center text-xs text-gray-400"
    >
      输入自然语言查询，如 "讲性能优化的那段"
    </div>
  </div>
</template>

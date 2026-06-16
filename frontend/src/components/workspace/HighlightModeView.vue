<script setup lang="ts">
/**
 * P2 Highlight Mode View.
 *
 * Shows LLM-extracted highlight segments. Users can start analysis with
 * a target duration, view highlights with reasons, and see jump-cut warnings.
 */
import { computed, ref } from "vue"
import type { Segment } from "@/types/project"
import { formatTimeShort } from "@/utils/format"

interface HighlightItem {
  segment_id: string
  highlight_reason: string
  density: "high" | "medium" | "low"
}

interface JumpCut {
  index: number
  gap_duration: number
  from_end: number
  to_start: number
}

const props = withDefaults(
  defineProps<{
    highlights: HighlightItem[]
    segments: Segment[]
    totalDuration?: number
    targetDuration?: number
    jumpCuts?: JumpCut[]
    loading?: boolean
    progress?: number
    error?: string | null
    llmConfigured: boolean
  }>(),
  {
    totalDuration: 0,
    targetDuration: 0,
    jumpCuts: () => [],
    loading: false,
    progress: 0,
    error: null,
  },
)

const emit = defineEmits<{
  "start-highlight": [targetMinutes: number]
  seek: [time: number]
}>()

// Target duration input (default 10 minutes)
const targetMinutes = ref(10)

// Segment lookup map for time resolution
const segmentMap = computed(() => {
  const m = new Map<string, Segment>()
  for (const s of props.segments) {
    m.set(s.id, s)
  }
  return m
})

interface DisplayHighlight {
  highlight: HighlightItem
  segment: Segment | undefined
  startTime: number
  endTime: number
}

// Sort highlights by segment start time
const sortedHighlights = computed<DisplayHighlight[]>(() => {
  return props.highlights
    .map((h) => {
      const seg = segmentMap.value.get(h.segment_id)
      return {
        highlight: h,
        segment: seg,
        startTime: seg?.start ?? 0,
        endTime: seg?.end ?? 0,
      }
    })
    .sort((a, b) => a.startTime - b.startTime)
})

function densityBadge(density: "high" | "medium" | "low"): string {
  switch (density) {
    case "high":
      return "bg-green-100 text-green-800"
    case "medium":
      return "bg-yellow-100 text-yellow-800"
    case "low":
    default:
      return "bg-gray-100 text-gray-500"
  }
}

function densityLabel(density: "high" | "medium" | "low"): string {
  switch (density) {
    case "high":
      return "高密度"
    case "medium":
      return "中密度"
    case "low":
    default:
      return "低密度"
  }
}

function startExtraction() {
  emit("start-highlight", targetMinutes.value)
}

function handleSeek(time: number) {
  emit("seek", time)
}
</script>

<template>
  <div class="flex h-full flex-col gap-3 overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-700">高光提取</h3>
      <span v-if="sortedHighlights.length > 0" class="text-xs text-gray-400">
        {{ sortedHighlights.length }} 个高光片段
      </span>
    </div>

    <!-- Not configured warning -->
    <div v-if="!llmConfigured" class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
      <span>请先在设置中配置 LLM 连接</span>
    </div>

    <!-- Error -->
    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">
      <span>{{ error }}</span>
    </div>

    <!-- Loading progress -->
    <div v-if="loading" class="flex flex-col gap-2">
      <div class="h-2 w-full overflow-hidden rounded bg-gray-200">
        <div
          class="h-full rounded bg-blue-500 transition-all duration-300"
          :style="{ width: (progress ?? 0) + '%' }"
        ></div>
      </div>
      <p class="text-center text-xs text-gray-400">正在提取高光片段...</p>
    </div>

    <!-- Input area (only when idle) -->
    <div
      v-if="!loading && llmConfigured"
      class="flex items-center gap-2"
    >
      <input
        v-model.number="targetMinutes"
        type="number"
        min="1"
        class="w-24 rounded border border-gray-300 px-2 py-1 text-xs"
        placeholder="分钟"
      />
      <span class="text-xs text-gray-400">分钟</span>
      <button
        class="rounded bg-blue-500 px-3 py-1 text-xs text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading || !llmConfigured || targetMinutes <= 0"
        @click="startExtraction"
      >
        开始提取
      </button>
    </div>

    <!-- Duration summary -->
    <div
      v-if="sortedHighlights.length > 0"
      class="text-xs text-gray-500"
    >
      已选 {{ totalDuration }}s / 目标 {{ targetDuration }}s
    </div>

    <!-- Jump cut warnings -->
    <div v-if="jumpCuts.length > 0" class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
      <div class="flex flex-col gap-1">
        <span class="font-semibold">检测到 {{ jumpCuts.length }} 处跳切</span>
        <ul class="ml-4 list-disc">
          <li v-for="(jc, i) in jumpCuts" :key="i">
            片段 {{ jc.index }}->{{ jc.index + 1 }} 间隔
            {{ Math.round(jc.gap_duration) }}s 可能产生音频跳变
          </li>
        </ul>
      </div>
    </div>

    <!-- Highlight list -->
    <div
      v-if="sortedHighlights.length > 0"
      class="flex-1 overflow-y-auto pr-1"
    >
      <div
        v-for="item in sortedHighlights"
        :key="item.highlight.segment_id"
        class="mb-2 rounded-lg border border-gray-200 bg-white p-2 text-xs"
      >
        <!-- Segment header -->
        <div class="mb-1 flex items-center gap-2">
          <button
            class="cursor-pointer text-gray-500 hover:text-gray-700 hover:underline"
            @click="handleSeek(item.startTime)"
          >
            {{ formatTimeShort(item.startTime) }}
          </button>
          <span
            class="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium"
            :class="densityBadge(item.highlight.density)"
          >
            {{ densityLabel(item.highlight.density) }}
          </span>
        </div>

        <!-- Reason text -->
        <div class="text-gray-600">
          {{ item.highlight.highlight_reason }}
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="sortedHighlights.length === 0 && !loading"
      class="flex flex-1 items-center justify-center text-xs text-gray-400"
    >
      暂无高光片段，输入目标时长后开始提取
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AI Assistant Panel (Phase 2 D-02, D-04, D-12, D-14).
 *
 * Central entry point for all LLM-powered features:
 *   - 快速清理 (智能删除 P0): launches analysis, results merge into
 *     SuggestionPanel as the "llm_smart" group (D-15).
 *   - 字幕纠错 (字幕修正 P1): launches analysis, then shows a "view
 *     results" button that opens the fullscreen diff view (D-16).
 *   - 内容搜索 (语义搜索 P3): inline SemanticSearchBar (D-02).
 *
 * Feature cards show 场景名 (primary) + 功能名 (subtitle) per D-14.
 * When LLM is not configured, cards are greyed out per D-12.
 */
import { computed, ref } from "vue"
import SemanticSearchBar from "@/components/workspace/SemanticSearchBar.vue"
import type { Segment } from "@/types/project"

type FeatureKey = "smart_delete" | "subtitle_correction" | "search"

const props = defineProps<{
  segments: Segment[]
  llmConfigured: boolean
  llmModel: string
  isRunning: boolean
  progress: number
  errorMsg: string | null
  // P1 subtitle correction result count (null = not run yet)
  subtitleCorrectionCount: number | null
}>()

const emit = defineEmits<{
  "start-smart-delete": []
  "switch-to-suggestion": []
  "start-subtitle-correction": [referenceText: string]
  "open-subtitle-fullscreen": []
  "go-to-settings": []
  seek: [time: number]
}>()

const selectedFeature = ref<FeatureKey | null>(null)
const referenceText = ref("")

interface FeatureCard {
  key: FeatureKey
  title: string
  subtitle: string
  description: string
  icon: string
}

const features: FeatureCard[] = [
  {
    key: "smart_delete",
    title: "快速清理",
    subtitle: "智能删除",
    description: "AI 自动识别口头禅、重复、口误等可删片段",
    icon: "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16",
  },
  {
    key: "subtitle_correction",
    title: "字幕纠错",
    subtitle: "字幕修正",
    description: "AI 修正同音错字、专有名词、标点断句",
    icon: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z",
  },
  {
    key: "search",
    title: "内容搜索",
    subtitle: "语义搜索",
    description: "用自然语言查找视频中的相关片段",
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  },
]

const hasCorrectionResults = computed(
  () => props.subtitleCorrectionCount !== null && props.subtitleCorrectionCount > 0,
)

function selectFeature(key: FeatureKey) {
  if (!props.llmConfigured) return
  selectedFeature.value = selectedFeature.value === key ? null : key
}

async function handleStartSmartDelete() {
  emit("start-smart-delete")
}

function handleStartSubtitleCorrection() {
  emit("start-subtitle-correction", referenceText.value)
}

function handleOpenFullscreen() {
  emit("open-subtitle-fullscreen")
}

function handleSearchSeek(time: number) {
  emit("seek", time)
}
</script>

<template>
  <div class="flex h-full flex-col gap-3 overflow-hidden">
    <!-- LLM status indicator (D-04) -->
    <div class="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2">
      <div class="flex items-center gap-2">
        <span
          class="inline-block h-2 w-2 rounded-full"
          :class="llmConfigured ? 'bg-green-500' : 'bg-amber-500'"
        ></span>
        <span class="text-xs font-medium" :class="llmConfigured ? 'text-gray-700' : 'text-amber-700'">
          {{ llmConfigured ? `LLM 已配置` : `未配置` }}
        </span>
        <span v-if="llmConfigured && llmModel" class="text-xs text-gray-500 truncate max-w-[120px]">
          {{ llmModel }}
        </span>
      </div>
      <button
        v-if="!llmConfigured"
        class="text-xs text-blue-600 hover:text-blue-800 underline"
        @click="emit('go-to-settings')"
      >
        去设置
      </button>
    </div>

    <!-- Error message -->
    <div v-if="errorMsg" class="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
      {{ errorMsg }}
    </div>

    <!-- Progress bar (shared) -->
    <div v-if="isRunning" class="flex flex-col gap-1">
      <div class="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
        <div
          class="h-full bg-blue-500 transition-all duration-300"
          :style="{ width: `${progress}%` }"
        ></div>
      </div>
      <p class="text-center text-xs text-gray-500">分析中...</p>
    </div>

    <!-- Feature cards (D-14) -->
    <div class="grid grid-cols-2 gap-2">
      <button
        v-for="feat in features.slice(0, 2)"
        :key="feat.key"
        class="relative flex flex-col items-start rounded-lg border p-2 text-left transition-colors"
        :class="[
          llmConfigured
            ? selectedFeature === feat.key
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
            : 'cursor-not-allowed border-gray-200 bg-gray-100 opacity-50',
        ]"
        :disabled="!llmConfigured"
        @click="selectFeature(feat.key)"
      >
        <svg
          v-if="!llmConfigured"
          class="absolute right-1 top-1 h-3 w-3 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
        <span v-if="!llmConfigured" class="absolute right-1 top-1 text-[10px] text-gray-400">未配置</span>
        <div class="flex items-center gap-1.5">
          <svg
            class="h-4 w-4 text-gray-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            stroke-width="2"
          >
            <path stroke-linecap="round" stroke-linejoin="round" :d="feat.icon" />
          </svg>
          <span class="text-sm font-medium text-gray-800">{{ feat.title }}</span>
        </div>
        <span class="text-xs text-gray-400">({{ feat.subtitle }})</span>
      </button>
    </div>
    <button
      class="flex items-center justify-between rounded-lg border p-2 text-left transition-colors"
      :class="[
        llmConfigured
          ? selectedFeature === 'search'
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
          : 'cursor-not-allowed border-gray-200 bg-gray-100 opacity-50',
      ]"
      :disabled="!llmConfigured"
      @click="selectFeature('search')"
    >
      <div class="flex items-center gap-1.5">
        <svg
          class="h-4 w-4 text-gray-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" :d="features[2].icon" />
        </svg>
        <span class="text-sm font-medium text-gray-800">内容搜索</span>
        <span class="text-xs text-gray-400">(语义搜索)</span>
      </div>
    </button>

    <!-- Operation area (selected feature detail) -->
    <div v-if="selectedFeature" class="flex flex-1 flex-col gap-2 overflow-y-auto">
      <!-- Smart delete (P0) -->
      <div v-if="selectedFeature === 'smart_delete'" class="flex flex-col gap-2">
        <p class="text-xs text-gray-600">{{ features[0].description }}</p>
        <button
          class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50"
          :disabled="isRunning"
          @click="handleStartSmartDelete"
        >
          开始智能分析
        </button>
        <p class="text-xs text-gray-400">
          分析完成后结果将自动合并到「建议」面板的「智能删除」分组
        </p>
      </div>

      <!-- Subtitle correction (P1) -->
      <div v-if="selectedFeature === 'subtitle_correction'" class="flex flex-col gap-2">
        <p class="text-xs text-gray-600">{{ features[1].description }}</p>
        <textarea
          v-model="referenceText"
          class="w-full rounded-md border border-gray-200 p-2 text-xs"
          rows="4"
          placeholder="参考稿（可选，模式 B）-- 留空使用 LLM 自主纠错（模式 A）"
          :disabled="isRunning"
        ></textarea>
        <button
          class="rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50"
          :disabled="isRunning"
          @click="handleStartSubtitleCorrection"
        >
          开始字幕修正
        </button>
        <button
          v-if="hasCorrectionResults"
          class="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
          @click="handleOpenFullscreen"
        >
          查看修正结果 ({{ subtitleCorrectionCount }} 条)
        </button>
      </div>

      <!-- Semantic search (P3) -->
      <div v-if="selectedFeature === 'search'" class="flex flex-col gap-2">
        <SemanticSearchBar
          :segments="segments"
          :llm-configured="llmConfigured"
          @seek="handleSearchSeek"
        />
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else
      class="flex flex-1 items-center justify-center text-xs text-gray-400"
    >
      选择一个功能开始
    </div>
  </div>
</template>

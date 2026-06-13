<script setup lang="ts">
import { computed, ref } from "vue"
import type { Segment, EditDecision, AnalysisResult, TopicDriftResult } from "@/types/project"
import { resolveSegmentState } from "@/utils/segmentHelpers"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"
import TopicDriftPanel from "@/components/workspace/TopicDriftPanel.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  analysisResults: AnalysisResult[]
  subtitleCount: number
  silenceCount: number
  selectedSegmentId?: string | null
  globalEditMode?: boolean
  topicDriftResults?: TopicDriftResult[]
  topicDriftLoading?: boolean
  topicDriftProgress?: number
  topicDriftError?: string | null
  llmConfigured?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": [segment: Segment]
  "confirm-segment": [segment: Segment]
  "reject-segment": [segment: Segment]
  "delete-segment": [segment: Segment]
  "confirm-suggestion": [editId: string]
  "reject-suggestion": [editId: string]
  "confirm-all": []
  "reject-all": []
  "seek-suggestion": [time: number]
  "toggle-edit-mode": []
  "start-topic-drift": [topicDescription: string]
  "cancel-topic-drift": []
  "accept-topic-drift": []
  "reject-topic-drift": []
}>()

function getSegmentState(seg: Segment) {
  return resolveSegmentState(props.edits, seg)
}

// Cross-validation highlight: when a silence segment is selected,
// find the adjacent subtitle segments for visual highlighting.
const adjacentSubtitleIds = computed(() => {
  if (!props.selectedSegmentId) return { prev: null, next: null }
  const idx = props.segments.findIndex(s => s.id === props.selectedSegmentId)
  if (idx < 0 || props.segments[idx].type !== "silence") return { prev: null, next: null }

  let prev: string | null = null
  for (let i = idx - 1; i >= 0; i--) {
    if (props.segments[i].type === "subtitle") { prev = props.segments[i].id; break }
  }
  let next: string | null = null
  for (let i = idx + 1; i < props.segments.length; i++) {
    if (props.segments[i].type === "subtitle") { next = props.segments[i].id; break }
  }
  return { prev, next }
})

import { watch, nextTick } from "vue"

// Right sidebar tab state
const sidebarTab = ref<"suggestions" | "topic-drift">("suggestions")

watch(
  () => props.selectedSegmentId,
  (id) => {
    if (!id) return
    nextTick(() => {
      const el = document.querySelector(`[data-segment-id="${id}"]`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" })
      }
    })
  },
)
</script>

<template>
  <div class="flex h-full w-full min-w-0 flex-col">
    <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
      <span class="text-sm font-medium">Timeline</span>
      <div class="flex items-center gap-2">
        <button
          v-if="!globalEditMode"
          class="text-xs px-2 py-1 rounded bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors"
          title="Edit all subtitles"
          @click="emit('toggle-edit-mode')"
        >
          编辑字幕
        </button>
        <button
          v-else
          class="text-xs px-2 py-1 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
          title="Exit edit mode"
          @click="emit('toggle-edit-mode')"
        >
          退出编辑
        </button>
        <span class="text-xs text-gray-500">{{ subtitleCount }} subtitles + {{ silenceCount }} silence</span>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <!-- Transcript list -->
      <div ref="listContainer" class="flex-1 overflow-y-auto">
        <div v-if="segments.length === 0" class="flex h-full items-center justify-center">
          <div class="text-center">
            <p class="text-sm text-gray-500">No segments loaded</p>
            <p class="mt-1 text-xs text-gray-400">Click "Import SRT" to load subtitles</p>
          </div>
        </div>

        <div v-else>
          <template v-for="seg in segments" :key="seg.id">
            <TranscriptRow
              v-if="seg.type === 'subtitle'"
              :segment="seg"
              :display-status="getSegmentState(seg).displayStatus"
              :style-class="getSegmentState(seg).styleClass"
              :is-selected="selectedSegmentId === seg.id"
              :is-adjacent-highlighted="seg.id === adjacentSubtitleIds.prev || seg.id === adjacentSubtitleIds.next"
              :global-edit-mode="globalEditMode"
              @seek="(t) => emit('seek', t)"
              @update-text="(id, text) => emit('update-text', id, text)"
              @update-time="(id, field, val) => emit('update-time', id, field, val)"
              @toggle-status="emit('toggle-status', seg)"
              @confirm-edit="emit('confirm-segment', seg)"
              @reject-edit="emit('reject-segment', seg)"
              @delete="emit('delete-segment', seg)"
            />
            <SilenceRow
              v-else
              :segment="seg"
              :display-status="getSegmentState(seg).displayStatus"
              :style-class="getSegmentState(seg).styleClass"
              @seek="(t) => emit('seek', t)"
              @update-time="(id, field, val) => emit('update-time', id, field, val)"
              @toggle-status="emit('toggle-status', seg)"
              @confirm-edit="emit('confirm-segment', seg)"
              @reject-edit="emit('reject-segment', seg)"
              @delete="emit('delete-segment', seg)"
            />
          </template>
        </div>
      </div>

      <!-- Right sidebar with tab switcher -->
      <div class="w-72 border-l border-gray-200 flex flex-col">
        <!-- Tab switcher -->
        <div class="flex border-b border-gray-200 text-xs">
          <button
            class="flex-1 px-2 py-1.5 font-medium transition-colors"
            :class="sidebarTab === 'suggestions' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-400' : 'text-gray-500 hover:bg-gray-50'"
            @click="sidebarTab = 'suggestions'"
          >
            建议
          </button>
          <button
            class="flex-1 px-2 py-1.5 font-medium transition-colors"
            :class="sidebarTab === 'topic-drift' ? 'bg-blue-50 text-blue-600 border-b-2 border-blue-400' : 'text-gray-500 hover:bg-gray-50'"
            @click="sidebarTab = 'topic-drift'"
          >
            主题漂移
          </button>
        </div>

        <!-- Tab content -->
        <div class="flex-1 overflow-y-auto">
          <SuggestionPanel
            v-if="sidebarTab === 'suggestions'"
            :analysis-results="analysisResults"
            :edits="edits"
            :segments="segments"
            @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
            @reject-edit="(editId) => emit('reject-suggestion', editId)"
            @confirm-all="emit('confirm-all')"
            @reject-all="emit('reject-all')"
            @seek="(t) => emit('seek-suggestion', t)"
          />
          <TopicDriftPanel
            v-else
            :results="topicDriftResults ?? []"
            :segments="segments"
            :loading="topicDriftLoading"
            :progress="topicDriftProgress"
            :error="topicDriftError"
            :llm-configured="llmConfigured ?? false"
            @start-analysis="(desc) => emit('start-topic-drift', desc)"
            @cancel="emit('cancel-topic-drift')"
            @accept-all="emit('accept-topic-drift')"
            @reject-all="emit('reject-topic-drift')"
            @seek="(t) => emit('seek-suggestion', t)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

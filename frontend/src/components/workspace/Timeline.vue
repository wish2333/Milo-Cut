<script setup lang="ts">
import type { Segment, EditDecision, AnalysisResult } from "@/types/project"
import { resolveSegmentState } from "@/utils/segmentHelpers"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  analysisResults: AnalysisResult[]
  subtitleCount: number
  silenceCount: number
  selectedSegmentId?: string | null
  globalEditMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": [segment: Segment]
  "confirm-segment": [segment: Segment]
  "reject-segment": [segment: Segment]
  "confirm-suggestion": [editId: string]
  "reject-suggestion": [editId: string]
  "confirm-all": []
  "reject-all": []
  "seek-suggestion": [time: number]
  "toggle-edit-mode": []
}>()

function getSegmentState(seg: Segment) {
  return resolveSegmentState(props.edits, seg)
}
</script>

<template>
  <div class="flex w-3/5 min-w-[500px] flex-col">
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
      <div class="flex-1 overflow-y-auto">
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
              :global-edit-mode="globalEditMode"
              @seek="(t) => emit('seek', t)"
              @update-text="(id, text) => emit('update-text', id, text)"
              @update-time="(id, field, val) => emit('update-time', id, field, val)"
              @toggle-status="emit('toggle-status', seg)"
              @confirm-edit="emit('confirm-segment', seg)"
              @reject-edit="emit('reject-segment', seg)"
            />
            <SilenceRow
              v-else
              :segment="seg"
              :display-status="getSegmentState(seg).displayStatus"
              :style-class="getSegmentState(seg).styleClass"
              @seek="(t) => emit('seek', t)"
              @update-time="(id, field, val) => emit('update-time', id, field, val)"
              @toggle-status="emit('toggle-status', seg)"
            />
          </template>
        </div>
      </div>

      <!-- Suggestion panel (right sidebar) -->
      <div v-if="edits.some(e => e.status === 'pending')" class="w-72 border-l border-gray-200 overflow-y-auto">
        <SuggestionPanel
          :analysis-results="analysisResults"
          :edits="edits"
          :segments="segments"
          @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
          @reject-edit="(editId) => emit('reject-suggestion', editId)"
          @confirm-all="emit('confirm-all')"
          @reject-all="emit('reject-all')"
          @seek="(t) => emit('seek-suggestion', t)"
        />
      </div>
    </div>
  </div>
</template>

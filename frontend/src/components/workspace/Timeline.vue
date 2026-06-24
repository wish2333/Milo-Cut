<script setup lang="ts">
import { computed, ref, watch, nextTick } from "vue"
import type { Segment, EditDecision, AnalysisResult } from "@/types/project"
import { resolveSegmentState } from "@/utils/segmentHelpers"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"
import AIAssistantPanel from "@/components/workspace/AIAssistantPanel.vue"
import HighlightModeView from "@/components/workspace/HighlightModeView.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  analysisResults: AnalysisResult[]
  subtitleCount: number
  silenceCount: number
  selectedSegmentId?: string | null
  globalEditMode?: boolean
  // v2.1.1 M4-1: multi-select mode
  selectionMode?: boolean
  selectedSegmentIds?: Set<string>
  selectedCount?: number
  // v2.1.1 M4-4: search bar visibility
  showSearchBar?: boolean
  /** v2.1.1: waveform playhead position for split-at-cursor */
  currentTime?: number
  // Phase 2: LLM integration props (passed through to AIAssistantPanel)
  llmConfigured?: boolean
  llmModel?: string
  llmIsRunning?: boolean
  llmProgress?: number
  llmErrorMsg?: string | null
  subtitleCorrectionCount?: number | null
  /** v2.1.0 Phase 2: pending P1 corrections count for SuggestionPanel banner */
  pendingCorrectionCount?: number
  highlightItems?: Array<{
    segment_id: string
    highlight_reason: string
    density: "high" | "medium" | "low"
  }>
  highlightTotalDuration?: number
  highlightTargetDuration?: number
  jumpCuts?: Array<{
    index: number
    gap_duration: number
    from_end: number
    to_start: number
  }>
  /** v2.1.0 Phase 4: pessimistic lock when workflow active (D-67) */
  workflowLocked?: boolean
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
  "reset-suggestion": [editId: string]
  "confirm-suggestion-batch": [editIds: string[]]
  "reject-suggestion-batch": [editIds: string[]]
  "reset-suggestion-batch": [editIds: string[]]
  "delete-suggestion-batch": [editIds: string[]]
  "confirm-all": []
  "reject-all": []
  "seek-suggestion": [time: number]
  "toggle-edit-mode": []
  // Phase 2: LLM events
  "start-smart-delete": []
  "start-subtitle-correction": [referenceText: string]
  "open-subtitle-fullscreen": []
  "start-highlight": [targetMinutes: number]
  "go-to-settings": []
  "cancel-single": []
  // v2.1.1 M4-1: selection mode
  "toggle-selection-mode": []
  "merge-selected": []
  "segment-click": [segmentId: string, event: MouseEvent]
  "clear-selection": []
  // v2.1.1 M4-3: split
  "split-segment": [segmentId: string]
  "split-at-pointer": [segmentId: string, position: number]
  // v2.1.1 M4-4: search bar toggle
  "toggle-search-bar": []
  // v2.1.1 A-03: toast notification from child components
  toast: [msg: string]
}>()

// Phase 2: right panel tab state (D-18). Using ref + v-show preserves
// component state across tab switches (SuggestionPanel expandedGroups,
// SemanticSearchBar query, SubtitleCorrectionReview acceptedIds).
type RightPanelTab = "suggestion" | "ai" | "highlight"
const activeTab = ref<RightPanelTab>("suggestion")

// v2.1.1 A-2.1: ref of the scrollable segment list, used for scrollIntoView on
// external highlight (SuggestionPanel click).
const listContainer = ref<HTMLElement | null>(null)

// v2.1.1 A-3: right-side panel is now an overlay (default hidden). Keeps the
// transcript list full-width when collapsed and floats over it when expanded.
const sidebarOpen = ref(false)

// v2.1.1: resizable sidebar width (persisted across sessions).
const SIDEBAR_MIN = 320
const SIDEBAR_MAX_RATIO = 0.85
const SIDEBAR_STORAGE_KEY = "milo-sidebar-width"
const sidebarWidth = ref<number>(
  Number(localStorage.getItem(SIDEBAR_STORAGE_KEY)) || 384,
)
const sidebarMaxWidth = ref<number>(Math.max(SIDEBAR_MIN, Math.floor(window.innerWidth * SIDEBAR_MAX_RATIO)))

function onSidebarResizeStart(e: MouseEvent) {
  e.preventDefault()
  const startX = e.clientX
  const startWidth = sidebarWidth.value
  const onMove = (ev: MouseEvent) => {
    const delta = startX - ev.clientX
    const next = Math.min(
      sidebarMaxWidth.value,
      Math.max(SIDEBAR_MIN, startWidth + delta),
    )
    sidebarWidth.value = next
  }
  const onUp = () => {
    window.removeEventListener("mousemove", onMove)
    window.removeEventListener("mouseup", onUp)
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarWidth.value))
  }
  window.addEventListener("mousemove", onMove)
  window.addEventListener("mouseup", onUp)
}

if (typeof window !== "undefined") {
  window.addEventListener("resize", () => {
    sidebarMaxWidth.value = Math.max(SIDEBAR_MIN, Math.floor(window.innerWidth * SIDEBAR_MAX_RATIO))
    if (sidebarWidth.value > sidebarMaxWidth.value) sidebarWidth.value = sidebarMaxWidth.value
  })
}

const tabs: Array<{ key: RightPanelTab; label: string }> = [
  { key: "suggestion", label: "建议" },
  { key: "ai", label: "AI 助手" },
  { key: "highlight", label: "精华" },
]

// v2.1.1 A-2.1: playhead-aware highlight + external (SuggestionPanel) click highlight.
// playheadSegmentId is a computed based on currentTime -- the TranscriptRow that
// contains the playhead gets a visual cue (left blue border + light bg) via the
// is-playhead-inside prop. v-memo deps use the boolean per-row, so continuous
// playhead movement only re-renders the two rows where playhead crosses boundary.
const playheadSegmentId = computed<string | null>(() => {
  const t = props.currentTime ?? 0
  const seg = props.segments.find(s => s.type === "subtitle" && t >= s.start && t <= s.end)
  return seg?.id ?? null
})

// External-click highlight: when user clicks a suggestion / AI assistant item,
// we briefly flash the target TranscriptRow (yellow ring) and scroll it into view.
const highlightedSegmentId = ref<string | null>(null)
let highlightTimer: ReturnType<typeof setTimeout> | null = null
function highlightSegment(segmentId: string) {
  highlightedSegmentId.value = segmentId
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => { highlightedSegmentId.value = null }, 2000)
  // Scroll into view via DOM query on the segment list container.
  nextTick(() => {
    const el = listContainer.value?.querySelector(
      `[data-segment-id="${segmentId}"]`
    ) as HTMLElement | null
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  })
}

// Handle SuggestionPanel / AIAssistantPanel / HighlightModeView @seek:
// seek the video AND flash the matching transcript row.
function handleSuggestionSeek(time: number) {
  emit("seek-suggestion", time)
  const seg = props.segments.find(s => s.type === "subtitle" && time >= s.start && time <= s.end)
  if (seg) highlightSegment(seg.id)
}

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
        <!-- v2.1.1 M4-1: selection mode toggle -->
        <button
          class="rounded p-1.5 transition-colors"
          :class="selectionMode ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'"
          :title="selectionMode ? '退出选择模式' : '选择模式 (框选字幕)'"
          @click="emit('toggle-selection-mode')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>
        <!-- v2.1.1 M4-4: search toggle -->
        <button
          class="rounded p-1.5 transition-colors"
          :class="showSearchBar ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'"
          title="搜索替换 (Ctrl+F)"
          @click="emit('toggle-search-bar')"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </button>
        <!-- v2.1.1 M4-1: selected count + merge button -->
        <span v-if="selectionMode && (selectedCount ?? 0) > 0" class="text-xs text-blue-600">
          已选 {{ selectedCount }} 段
        </span>
        <button
          v-if="selectionMode && (selectedCount ?? 0) >= 2"
          class="rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-600 transition-colors"
          @click="emit('merge-selected')"
        >
          合并选中
        </button>
        <button
          class="text-xs px-2 py-1 rounded transition-colors"
          :class="globalEditMode ? 'bg-amber-500 text-white hover:bg-amber-600' : 'bg-amber-100 text-amber-700 hover:bg-amber-200'"
          :title="globalEditMode ? 'Exit edit mode' : 'Edit all subtitles'"
          @click="emit('toggle-edit-mode')"
        >
          {{ globalEditMode ? '退出编辑' : '编辑字幕' }}
        </button>
        <span class="text-xs text-gray-500">{{ subtitleCount }} subtitles + {{ silenceCount }} silence</span>
      </div>
    </div>

    <div class="relative flex flex-1 overflow-hidden">
      <!-- Transcript list -->
      <div ref="listContainer" class="flex-1 overflow-y-auto">
        <!-- v2.1.1 M4-1: selection mode banner -->
        <div
          v-if="selectionMode"
          class="sticky top-0 z-10 flex items-center gap-2 bg-blue-50 px-4 py-2 text-xs text-blue-700 border-b border-blue-100"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span>选择模式 — 点击多选 Ctrl 切换 Shift 范围选 Enter 合并 Delete 删除</span>
        </div>
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
              v-memo="[seg, getSegmentState(seg).displayStatus, selectedSegmentIds?.has(seg.id) ?? false, selectedSegmentId === seg.id, seg.id === playheadSegmentId, seg.id === highlightedSegmentId, globalEditMode, selectionMode]"
              :segment="seg"
              :display-status="getSegmentState(seg).displayStatus"
              :style-class="getSegmentState(seg).styleClass"
              :is-selected="selectedSegmentId === seg.id"
              :is-adjacent-highlighted="seg.id === adjacentSubtitleIds.prev || seg.id === adjacentSubtitleIds.next"
              :is-playhead-inside="seg.id === playheadSegmentId"
              :is-highlighted="seg.id === highlightedSegmentId"
              :global-edit-mode="globalEditMode"
              :selection-mode="selectionMode ?? false"
              :is-multi-selected="selectedSegmentIds?.has(seg.id) ?? false"
              :current-time="currentTime ?? 0"
              @seek="(t) => emit('seek', t)"
              @update-text="(id, text) => emit('update-text', id, text)"
              @update-time="(id, field, val) => emit('update-time', id, field, val)"
              @toggle-status="emit('toggle-status', seg)"
              @confirm-edit="emit('confirm-segment', seg)"
              @reject-edit="emit('reject-segment', seg)"
              @delete="emit('delete-segment', seg)"
              @segment-click="(id, ev) => emit('segment-click', id, ev)"
              @split="emit('split-segment', seg.id)"
              @split-at-pointer="(pos) => emit('split-at-pointer', seg.id, pos)"
              @toast="(msg) => emit('toast', msg)"
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

      <!-- v2.1.1: toggle button -- shown only when sidebar is collapsed.
           Lives inside Timeline (absolute top-right) so it never clashes
           with the top nav Save button. When sidebar opens this one hides
           and the close button inside the sidebar header takes over. -->
      <button
        v-show="!sidebarOpen"
        class="absolute right-2 top-2 z-30 rounded p-1.5 text-gray-500 bg-white/40 backdrop-blur-sm hover:bg-gray-100/80 hover:text-gray-700 transition-colors"
        title="显示侧栏"
        @click="sidebarOpen = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <!-- v2.1.1: Right sidebar -- teleported to body so it can overlay the
           whole window (covering the Timeline toolbar and any ancestor
           chrome) instead of being clipped by Timeline's overflow-hidden
           wrapper. Width is user-resizable via the drag handle on its
           left edge, and remembered across sessions. -->
      <Teleport to="body">
        <Transition
          enter-active-class="transition transform duration-200 ease-out"
          enter-from-class="translate-x-full"
          enter-to-class="translate-x-0"
          leave-active-class="transition transform duration-200 ease-in"
          leave-from-class="translate-x-0"
          leave-to-class="translate-x-full"
        >
          <div
            v-if="sidebarOpen"
            class="fixed top-0 bottom-0 right-0 bg-white shadow-2xl border-l border-gray-200 z-40 flex flex-col"
            :style="{ width: sidebarWidth + 'px' }"
          >
            <!-- Resize drag handle -->
            <div
              class="absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize bg-gray-200/0 hover:bg-blue-400/40 transition-colors"
              title="拖动调整宽度"
              @mousedown="onSidebarResizeStart"
            ></div>

        <!-- Tab header (D-18) -->
        <div class="flex items-center border-b border-gray-200 bg-gray-50">
          <!-- Left: Tab buttons (flex-1 + min-w-0 + truncate to prevent squeeze by right button) -->
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="flex-1 min-w-0 truncate px-2 py-2 text-xs font-medium transition-colors"
            :class="
              activeTab === tab.key
                ? 'border-b-2 border-blue-500 text-blue-600 bg-white'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            "
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>

          <!-- Right: inline close button (flex-shrink-0 to avoid squeeze; relative z-10 for dropdown visibility) -->
          <button
            class="relative z-10 flex-shrink-0 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="隐藏侧栏"
            @click="sidebarOpen = false"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Tab content (v-show preserves component state across switches) -->
        <div class="flex-1 overflow-y-auto p-2">
          <SuggestionPanel
            v-show="activeTab === 'suggestion'"
            :analysis-results="analysisResults"
            :edits="edits"
            :segments="segments"
            :pending-correction-count="pendingCorrectionCount ?? 0"
            @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
            @reject-edit="(editId) => emit('reject-suggestion', editId)"
            @reset-edit="(editId) => emit('reset-suggestion', editId)"
            @confirm-edit-batch="(ids) => emit('confirm-suggestion-batch', ids)"
            @reject-edit-batch="(ids) => emit('reject-suggestion-batch', ids)"
            @reset-edit-batch="(ids) => emit('reset-suggestion-batch', ids)"
            @delete-edit-batch="(ids) => emit('delete-suggestion-batch', ids)"
            @confirm-all="emit('confirm-all')"
            @reject-all="emit('reject-all')"
            @seek="handleSuggestionSeek"
            @review-corrections="emit('open-subtitle-fullscreen')"
          />

          <AIAssistantPanel
            v-show="activeTab === 'ai'"
            :segments="segments"
            :llm-configured="llmConfigured ?? false"
            :llm-model="llmModel ?? ''"
            :is-running="llmIsRunning ?? false"
            :progress="llmProgress ?? 0"
            :error-msg="llmErrorMsg ?? null"
            :subtitle-correction-count="subtitleCorrectionCount ?? null"
            @start-smart-delete="emit('start-smart-delete')"
            @switch-to-suggestion="activeTab = 'suggestion'"
            @start-subtitle-correction="(text) => emit('start-subtitle-correction', text)"
            @open-subtitle-fullscreen="emit('open-subtitle-fullscreen')"
            @go-to-settings="emit('go-to-settings')"
            @seek="handleSuggestionSeek"
            @cancel-single="emit('cancel-single')"
          />

          <HighlightModeView
            v-show="activeTab === 'highlight'"
            :highlights="highlightItems ?? []"
            :segments="segments"
            :total-duration="highlightTotalDuration ?? 0"
            :target-duration="highlightTargetDuration ?? 0"
            :jump-cuts="jumpCuts ?? []"
            :loading="llmIsRunning ?? false"
            :progress="llmProgress ?? 0"
            :error="llmErrorMsg ?? null"
            :llm-configured="llmConfigured ?? false"
            @start-highlight="(minutes) => emit('start-highlight', minutes)"
            @seek="handleSuggestionSeek"
          />
        </div>
        </div>
      </Transition>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, watch, nextTick, onMounted, onUnmounted } from "vue"
import type { Segment, EditDecision, AnalysisResult } from "@/types/project"
import {
  buildSubtitleIndex,
  findSubtitleAtTime,
} from "@/utils/editedPlayback"
import { buildSegmentStateMap, type SegmentState } from "@/utils/segmentHelpers"
import {
  DEFAULT_ROW_HEIGHTS,
  buildCumulativeOffsets,
  computeVisibleWindow,
  scrollTargetForIndex,
  type RowTypeHeights,
} from "@/utils/virtualList"
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
  "confirm-suggestion-batch": [editIds: string[]]
  "reject-suggestion-batch": [editIds: string[]]
  "delete-suggestion-batch": [editIds: string[]]
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
  // Spec-6 §11.5.2: highlight context-menu actions
  "remove-highlight": [segmentId: string]
  "add-to-highlight": [segmentId: string]
}>()

// Phase 2: right panel tab state (D-18). Using ref + v-show preserves
// component state across tab switches (SuggestionPanel expandedGroups,
// SemanticSearchBar query, SubtitleCorrectionReview acceptedIds).
type RightPanelTab = "suggestion" | "ai" | "highlight"
const activeTab = ref<RightPanelTab>("suggestion")

// v2.1.1 A-2.1: ref of the scrollable segment list, used for scrollIntoView on
// external highlight (SuggestionPanel click).
const listContainer = ref<HTMLElement | null>(null)

// ---------------------------------------------------------------------------
// v3.0.0 M7-2: virtual scrolling (PRD B3 / SPEC M7-2 / risk review 2.6)
//
// Only the viewport window (+OVERSCAN rows per side) is mounted. Mixed row
// types (TranscriptRow 52px vs SilenceRow 36px) go through the per-type
// height registry + cumulative offsets of utils/virtualList.ts; positioning
// is binary-search based so variable-height rows cost nothing extra later.
// ---------------------------------------------------------------------------
const VIRTUAL_OVERSCAN = 10

const scrollTopValue = ref(0)
const viewportHeight = ref(0)
const measuredHeights = ref<Partial<RowTypeHeights>>({})

const rowHeights = computed<RowTypeHeights>(() => ({
  subtitle: measuredHeights.value.subtitle ?? DEFAULT_ROW_HEIGHTS.subtitle,
  silence: measuredHeights.value.silence ?? DEFAULT_ROW_HEIGHTS.silence,
}))

const virtualOffsets = computed(() => buildCumulativeOffsets(
  props.segments.map((s) => s.type),
  rowHeights.value,
))
const totalHeight = computed(() => virtualOffsets.value.totalHeight)

const visibleWindow = computed(() =>
  computeVisibleWindow(
    virtualOffsets.value.offsets,
    scrollTopValue.value,
    viewportHeight.value,
    VIRTUAL_OVERSCAN,
  ),
)
const windowSegments = computed(() =>
  props.segments.slice(visibleWindow.value.start, visibleWindow.value.end),
)
const windowTopOffset = computed(
  () => virtualOffsets.value.offsets[visibleWindow.value.start] ?? 0,
)

const segmentIndexById = computed(() => {
  const m = new Map<string, number>()
  props.segments.forEach((s, i) => m.set(s.id, i))
  return m
})

const segmentById = computed(() => {
  const m = new Map<string, Segment>()
  for (const s of props.segments) m.set(s.id, s)
  return m
})

// rAF-throttled scroll tracking: at most one scrollTop read per frame.
let scrollRafId: number | null = null
function onListScroll() {
  if (scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    if (listContainer.value) scrollTopValue.value = listContainer.value.scrollTop
  })
}

function measureViewport() {
  const el = listContainer.value
  if (el) viewportHeight.value = el.clientHeight
}

let resizeObserver: ResizeObserver | null = null
let fallbackResizeListener = false
onMounted(() => {
  measureViewport()
  if (typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => measureViewport())
    if (listContainer.value) resizeObserver.observe(listContainer.value)
  } else {
    fallbackResizeListener = true
    window.addEventListener("resize", measureViewport)
  }
  void probeRowHeights()
})

onUnmounted(() => {
  if (scrollRafId !== null) cancelAnimationFrame(scrollRafId)
  resizeObserver?.disconnect()
  if (fallbackResizeListener) window.removeEventListener("resize", measureViewport)
})

/**
 * Height probe per row type: reads real offsetHeight from the rendered
 * window and updates the registry when CSS differs from the defaults.
 * happy-dom reports 0, which the `h <= 0` guard ignores (defaults keep).
 */
async function probeRowHeights() {
  await nextTick()
  const el = listContainer.value
  if (!el) return
  let subtitleH = 0
  let silenceH = 0
  for (const node of el.querySelectorAll<HTMLElement>("[data-segment-id]")) {
    const h = node.offsetHeight
    if (h <= 0) continue
    const seg = segmentById.value.get(node.getAttribute("data-segment-id") ?? "")
    if (!seg) continue
    if (seg.type === "silence") {
      if (!silenceH) silenceH = h
    } else if (!subtitleH) {
      subtitleH = h
    }
    if (subtitleH && silenceH) break
  }
  if (subtitleH && subtitleH !== rowHeights.value.subtitle) measuredHeights.value.subtitle = subtitleH
  if (silenceH && silenceH !== rowHeights.value.silence) measuredHeights.value.silence = silenceH
}

watch(() => props.segments, (segs) => {
  void probeRowHeights()
  // Draft hygiene: drop entries for segments that no longer exist.
  if (drafts.size > 0) {
    const alive = new Set(segs.map((s) => s.id))
    for (const id of drafts.keys()) {
      if (!alive.has(id)) drafts.delete(id)
    }
  }
})

/**
 * Bring a segment row into view. Out-of-window targets are positioned
 * instantly (plan P2-4 acceptance: "跳转不可见行先滚动定位无跳变" -- a long
 * smooth scroll would be both slow and disorienting). The math is exact
 * because the height probe keeps the offsets registry in sync with the
 * real rendered row heights; no post-scroll fine-tuning needed.
 */
function scrollToSegment(id: string) {
  const el = listContainer.value
  const index = segmentIndexById.value.get(id)
  if (!el || index === undefined) return
  const target = scrollTargetForIndex(
    virtualOffsets.value.offsets,
    index,
    el.scrollTop,
    el.clientHeight || viewportHeight.value,
  )
  if (target !== null) {
    // Direct scrollTop assignment == behavior:"auto" instant scroll, and is
    // the one primitive that behaves identically across WebView2/WKWebView.
    el.scrollTop = target
    scrollTopValue.value = target
  }
}

// v3.0.0 M7-2: draft cache. Virtual scrolling unmounts rows that leave the
// window; TranscriptRow mirrors its unsaved edit text here on every keystroke
// and restores it on remount, so scrolling never loses an in-progress edit
// (same observable behavior as the pre-virtualization always-mounted rows).
const drafts = reactive(new Map<string, string>())
function onDraftChange(id: string, text: string | null) {
  if (text === null) drafts.delete(id)
  else drafts.set(id, text)
}

// v2.1.1 A-3: right-side panel — inline flex child (default open).
const sidebarOpen = ref(true)

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

const segmentStateMap = computed(() => buildSegmentStateMap(props.segments, props.edits))
const subtitleSegments = computed(() => buildSubtitleIndex(props.segments))
const EMPTY_SEGMENT_STATE: SegmentState = {
  displayStatus: "none",
  styleClass: "normal",
  activeEdit: undefined,
}

// v2.1.1 A-2.1: playhead-aware highlight + external (SuggestionPanel) click highlight.
// playheadSegmentId is a computed based on currentTime -- the TranscriptRow that
// contains the playhead gets a visual cue (left blue border + light bg) via the
// is-playhead-inside prop. v-memo deps use the boolean per-row, so continuous
// playhead movement only re-renders the two rows where playhead crosses boundary.
const playheadSegmentId = computed<string | null>(() => {
  const t = props.currentTime ?? 0
  const seg = findSubtitleAtTime(subtitleSegments.value, t)
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
  // M7-2: position the (possibly virtualized-out) row first, then fine-tune.
  scrollToSegment(segmentId)
}

// Handle SuggestionPanel / AIAssistantPanel / HighlightModeView @seek:
// seek the video AND flash the matching transcript row.
function handleSuggestionSeek(time: number) {
  emit("seek-suggestion", time)
  const seg = props.segments.find(s => s.type === "subtitle" && time >= s.start && time <= s.end)
  if (seg) highlightSegment(seg.id)
}

function getSegmentState(seg: Segment) {
  return segmentStateMap.value.get(seg.id) ?? EMPTY_SEGMENT_STATE
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
    // M7-2: virtualization may keep the row unmounted; position first.
    scrollToSegment(id)
  },
)
</script>

<template>
  <div class="flex h-full w-full min-w-0 flex-col">
    <div class="flex items-center justify-between border-b border-hairline px-4 py-2">
      <!-- LEFT: Timeline title + tools -->
      <div class="flex items-center gap-2 flex-1 min-w-0">
        <span class="text-sm font-semibold">字幕时间线</span>
        <!-- v2.1.1 M4-1: selection mode toggle -->
        <button
          class="rounded p-1.5 transition-colors"
          :class="selectionMode ? 'bg-primary-soft text-primary' : 'text-ink-muted hover:bg-parchment'"
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
          :class="showSearchBar ? 'bg-primary-soft text-primary' : 'text-ink-muted hover:bg-parchment'"
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
          class="mc-button mc-button-primary min-h-8 px-2 py-1 text-xs"
          @click="emit('merge-selected')"
        >
          合并选中
        </button>
        <button
          class="text-xs px-2 py-1 rounded-md transition-all duration-150 active:scale-95"
          :class="globalEditMode ? 'mc-button-primary' : 'mc-button-secondary'"
          :title="globalEditMode ? 'Exit edit mode' : 'Edit all subtitles'"
          @click="emit('toggle-edit-mode')"
        >
          {{ globalEditMode ? '退出编辑' : '编辑字幕' }}
        </button>
        <span class="text-xs text-ink-muted">{{ subtitleCount }} 条字幕 · {{ silenceCount }} 段静音</span>
      </div>
      <!-- RIGHT: sidebar tabs + collapse arrow -->
      <div class="flex items-center gap-1 flex-shrink-0">
        <template v-for="tab in tabs" :key="tab.key">
          <button
            v-if="sidebarOpen"
            class="rounded px-2 py-1 text-xs font-semibold transition-colors"
            :class="activeTab === tab.key
              ? 'bg-primary-soft text-primary'
              : 'text-ink-muted hover:bg-parchment hover:text-ink'"
            @click="activeTab = tab.key"
          >{{ tab.label }}</button>
        </template>
        <button
          class="flex h-8 w-8 items-center justify-center rounded text-ink-muted transition-colors hover:bg-parchment hover:text-ink"
          :title="sidebarOpen ? '隐藏侧栏' : '显示侧栏'"
          @click="sidebarOpen = !sidebarOpen"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path v-if="sidebarOpen" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
            <path v-else stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      </div>
    </div>

    <div class="relative flex flex-1 overflow-hidden">
      <!-- Transcript list (virtualized, v3.0.0 M7-2) -->
      <div ref="listContainer" data-test="segment-list" class="flex-1 overflow-y-auto" @scroll.passive="onListScroll">
        <!-- v2.1.1 M4-1: selection mode banner -->
        <div
          v-if="selectionMode"
          class="sticky top-0 z-raised flex items-center gap-2 border-b border-hairline bg-primary-soft px-4 py-2 text-xs text-primary"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span>选择模式 — 点击多选 Ctrl 切换 Shift 范围选 Enter 合并 Delete 删除</span>
        </div>
        <div v-if="segments.length === 0" class="flex h-full items-center justify-center">
          <div class="text-center">
            <p class="text-sm text-ink-muted">暂无字幕片段</p>
            <p class="mt-1 text-xs text-ink-muted">点击“导入 SRT”开始编辑</p>
          </div>
        </div>

        <!-- Windowed renderer: full-height spacer + absolutely positioned
             slice at its cumulative offset. Mixed row types keep per-type
             heights via the offsets array (utils/virtualList.ts). -->
        <div v-else class="relative" :style="{ height: totalHeight + 'px' }">
          <div class="absolute left-0 right-0" :style="{ top: windowTopOffset + 'px' }">
            <!-- v-memo is intentionally retained for the large transcript list. -->
            <!-- eslint-disable vue/valid-v-memo -->
            <template v-for="seg in windowSegments" :key="seg.id">
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
                :draft="drafts.get(seg.id) ?? null"
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
                @add-to-highlight="(id) => emit('add-to-highlight', id)"
                @draft-change="onDraftChange"
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
            <!-- eslint-enable vue/valid-v-memo -->
          </div>
        </div>
      </div>

      <!-- Sidebar panel + divider wrapped together for smooth animation -->
      <Transition name="sidebar">
        <div
          v-if="sidebarOpen"
          class="flex shrink-0 overflow-hidden"
          :style="{ width: sidebarWidth + 'px' }"
        >
          <!-- Divider with resize handle -->
          <div
            class="relative w-px shrink-0 cursor-ew-resize bg-hairline transition-colors hover:bg-primary"
            @mousedown="onSidebarResizeStart"
          >
            <div class="absolute -left-1.5 -right-1.5 top-0 bottom-0 z-raised"></div>
          </div>

          <!-- Inline sidebar -->
          <div class="flex flex-1 flex-col overflow-hidden border-l border-hairline bg-parchment">
            <div class="flex-1 overflow-y-auto p-2">
            <SuggestionPanel
              v-show="activeTab === 'suggestion'"
              :analysis-results="analysisResults"
              :edits="edits"
              :segments="segments"
              :pending-correction-count="pendingCorrectionCount ?? 0"
              @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
              @reject-edit="(editId) => emit('reject-suggestion', editId)"
              @confirm-edit-batch="(ids) => emit('confirm-suggestion-batch', ids)"
              @reject-edit-batch="(ids) => emit('reject-suggestion-batch', ids)"
              @delete-edit-batch="(ids) => emit('delete-suggestion-batch', ids)"
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
              @remove-highlight="(id) => emit('remove-highlight', id)"
            />
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.sidebar-enter-active,
.sidebar-leave-active {
  transition: width 200ms ease-out;
  overflow: hidden;
  will-change: width;
}
.sidebar-enter-from,
.sidebar-leave-to {
  width: 0 !important;
}
</style>

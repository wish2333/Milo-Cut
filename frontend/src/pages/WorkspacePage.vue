<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, provide, ref, watch } from "vue"
import type { Project, Segment, EditDecision, Timeline as TimelineData, ProjectResponse } from "@/types/project"
import { formatTimeShort } from "@/utils/format"
import { call, onEvent, isDemoMode } from "@/bridge"
import { useAnalysis } from "@/composables/useAnalysis"
import { useExport } from "@/composables/useExport"
import { useEdit } from "@/composables/useEdit"
import { useSegmentEdit } from "@/composables/useSegmentEdit"
import { useTrackEdit } from "@/composables/useTrackEdit"
import { useSettings } from "@/composables/useSettings"
import { useToast } from "@/composables/useToast"
import { useUndoRedo } from "@/composables/useUndoRedo"
import { useAsrEngines } from "@/composables/useAsrEngines"
import { createWorkspaceActions, provideWorkspaceActions } from "@/composables/useWorkspaceActions"
import { useUvAvailability } from "@/composables/useUvAvailability"
import { useLlmTasks } from "@/composables/useLlmTasks"
import { useEditedPlayback } from "@/composables/useEditedPlayback"
import { createPlaybackClock } from "@/composables/usePlaybackClock"
import { PLAYBACK_CLOCK_KEY } from "@/components/waveform/injectionKeys"
import {
  EVENT_TASK_COMPLETED,
  EVENT_TASK_CANCELLED,
  EVENT_PROJECT_DIRTY,
  EVENT_PROJECT_SAVED,
  EVENT_WORKFLOW_ROLLED_BACK,
} from "@/utils/events"
import ProgressBar from "@/components/common/ProgressBar.vue"
import SplitPanel from "@/components/common/SplitPanel.vue"
import Timeline from "@/components/workspace/Timeline.vue"
import TimelineSwitcher from "@/components/workspace/TimelineSwitcher.vue"
import WaveformEditor from "@/components/waveform/WaveformEditor.vue"
import SearchReplaceBar from "@/components/workspace/SearchReplaceBar.vue"
import VideoControls from "@/components/workspace/VideoControls.vue"
import SubtitleOverlay from "@/components/workspace/SubtitleOverlay.vue"
import SettingsModal from "@/components/workspace/SettingsModal.vue"
import TranscribeSettingsPopover from "@/components/workspace/popovers/TranscribeSettingsPopover.vue"
import SilenceSettingsPopover from "@/components/workspace/popovers/SilenceSettingsPopover.vue"
import SubtitleTrimSettingsPopover from "@/components/workspace/popovers/SubtitleTrimSettingsPopover.vue"
import DemoPreviewSurface from "@/components/demo/DemoPreviewSurface.vue"
import DemoResponsiveWorkspace from "@/components/demo/DemoResponsiveWorkspace.vue"
import { useDemoPlayback } from "@/composables/useDemoPlayback"

interface Props {
  project: Project
}

interface Emits {
  (e: "project-updated", project: ProjectResponse): void
  (e: "project-closed"): void
  (e: "go-to-export"): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()
const demoMode = isDemoMode()
const isCompactDemo = ref(demoMode && window.innerWidth < 1200)

function syncCompactDemo() {
  isCompactDemo.value = demoMode && window.innerWidth < 1200
}

// Phase 2: LLM integration
const {
  llmConfig,
  loadLlmConfig,
  isRunning: llmIsRunning,
  progress: llmProgress,
  errorMsg: llmErrorMsg,
  subtitleCorrectionResult,
  // v2.1.0 Phase 2: P1 correction review
  pendingCorrections,
  correctionsLoading,
  loadCorrections,
  computeDiff,
  acceptCorrection,
  rejectCorrection,
  acceptHighConfidenceCorrections,
  clearCorrections,
  highlightResults,
  highlightTotalDuration,
  highlightTargetDuration,
  jumpCuts,
  startSmartDelete,
  startSubtitleCorrection,
  startHighlight,
  hydrateHighlightsFromProject,
  coverageGap,
} = useLlmTasks()

// v3.0.0 M3-1: surface batch coverage gaps from LLM tasks (never silent)
watch(coverageGap, (n) => {
  if (n > 0) {
    showToast(`本次分析未覆盖 ${n} 段（批次失败，已跳过），建议重试`, "error", 5000)
  }
})

// P1 fullscreen diff view state (D-16)
const showSubtitleFullscreen = ref(false)
// Settings modal (opened from AI assistant "go to settings")
const showSettingsModal = ref(false)

// v2.1.0 Phase 2: P1 review -- corrections come from backend pending list.
// subtitleCorrectionResult now only carries stored_count metadata.
const subtitleCorrectionCount = computed(() => pendingCorrections.value.length)

let correctionToastShown = false

// §10.3: Show toast when subtitle correction completes (with dedup guard).
// Also auto-load stored corrections so the "查看修正结果" button appears.
watch(subtitleCorrectionResult, async (result) => {
  if (result === null) {
    correctionToastShown = false
    return
  }
  if (result?.stored_count && result.stored_count > 0) {
    // Auto-load corrections from backend so the review entry button shows.
    const tlId = props.project.active_timeline_id
    if (tlId) {
      await loadCorrections(tlId)
    }
    if (!correctionToastShown) {
      correctionToastShown = true
      showToast(`字幕修正完成，发现 ${result.stored_count} 条修改`, "success", 3000)
    }
  }
})
const highConfidenceCorrections = computed(() =>
  pendingCorrections.value.filter((c) => c.confidence >= 0.8),
)
const lowConfidenceCorrections = computed(() =>
  pendingCorrections.value.filter((c) => c.confidence < 0.8),
)

const projectRef = computed({
  get: () => props.project,
  set: (val) => emit("project-updated", val),
})

// v3.0.0 M5: layered undo via the backend apply_undo channel. The legacy
// full-JSON snapshot path was removed after the beta.2 smoke (rollback
// anchor: tag pre-undo-cleanup).
const { pushSnapshot, undo, redo, canUndo, canRedo, clearHistory } = useUndoRedo()

const {
  isDetecting,
  detectionProgress,
  activeTask,
  runSilenceDetection,
  runTranscription,
  confirmEdit,
  rejectEdit,
  batchUpdateEdits,
  deleteEdits,
} = useAnalysis(projectRef, pushSnapshot)

const {
  isExporting,
  exportProgress,
  confirmedEdits,
  estimatedSaving,
} = useExport(projectRef)

const {
  searchReplace,
  mergeSegments,
  splitSegment,
  confirmAllSuggestions,
  rejectAllSuggestions,
  generateSubtitleKeepRanges,
  deleteSegment,
  deleteSilenceSegments,
  deleteSubtitleTrimEdits,
} = useEdit(projectRef, pushSnapshot)

const { showToast } = useToast()

const {
  selectedSegmentId: editSelectedSegmentId,
  selectRange: selectEditRange,
  updateSegmentTime,
  updateSegmentText,
  toggleEditStatus,
  flushPendingUpdates,
  // v2.1.1 M4-1: multi-select mode
  selectionMode,
  selectedSegmentIds,
  selectedCount,
  toggleSelectionMode,
  handleSegmentClick,
  clearMultiSelection,
} = useSegmentEdit(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  projectRef as any,
  (val: ProjectResponse) => emit("project-updated", val),
  pushSnapshot,
  // v3.0.1 R7.5: destructive reconcile is never silent -- counters toast.
  (c) =>
    showToast(
      `联动消解：挤压 ${c.squeezed} · 移除 ${c.removed} · 解绑 ${c.unbound}`,
      "info",
      4000,
    ),
)

// v3.0.1 M5-2: extension-track editing (optimistic + debounced, separate
// composable by design -- see SPEC M5-2 ruling).
const { updateTrackSegmentTime, flushPendingTrackUpdates } = useTrackEdit(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  projectRef as any,
  (val: ProjectResponse) => emit("project-updated", val),
  pushSnapshot,
)

// v3.0.1 M6-2: secondary subtitle overlay setting; reloaded when the
// settings modal closes so flips take effect immediately.
const { settings: appSettings, loadSettings: reloadAppSettings } = useSettings()
const showSecondarySubtitle = computed(() => appSettings.value?.show_secondary_subtitle !== false)
const activeBindings = computed(
  () => activeTimeline.value?.transcript?.bindings ?? [],
)

const statusMessage = ref("")
const errorMessage = ref("")
let statusTimer: ReturnType<typeof setTimeout> | null = null
const showSilenceSettings = ref(false)
const showTranscribeSettings = ref(false)
const videoUrl = ref("")
const waveformUrl = ref("")
const videoRef = ref<HTMLVideoElement | null>(null)
// v3.0.0 M6-3: per-frame media time lives in the playback clock (non-reactive)
// and reaches the playhead overlay imperatively. `currentTime` below is the
// clock's COARSE reactive mirror (<=10 writes/s while playing, immediate on
// pause/seek) -- the template consumers (controls text, segment highlight,
// follow logic) intentionally never see per-frame updates, so playback no
// longer re-renders the WorkspacePage tree at 60Hz.
const playbackClock = createPlaybackClock({
  getVideoTime: () => videoRef.value?.currentTime ?? 0,
  isPlaying: () => videoRef.value !== null && !videoRef.value.paused,
})
provide(PLAYBACK_CLOCK_KEY, playbackClock)
const currentTime = playbackClock.coarseTime
const videoPaused = ref(true)
const videoVolume = ref(0.75)
const { uvAvailable } = useUvAvailability()
const videoPlaybackRate = ref(1)
const isGeneratingProxy = ref(false)

// Preview mode: "edited" skips delete ranges, "original" plays full video
const previewMode = ref<"edited" | "original">("edited")

// v2.3.1 Bug D fix: declare activeTimeline/segments/edits BEFORE deleteRanges.
// useEditedPlayback's internal watch(playbackRanges, ...) evaluates
// playbackRanges.value during setup registration, which cascades through
// deleteRanges into edits.value. If edits is still in TDZ at that point the
// whole WorkspacePage setup crashes with "Cannot access 'edits' before
// initialization". Moving these three computeds up keeps the data dependency
// order correct without changing useEditedPlayback's contract.
const activeTimeline = computed<TimelineData | null>(() =>
  props.project.timelines.find(t => t.id === props.project.active_timeline_id) ?? null
)
const segments = computed<Segment[]>(() => activeTimeline.value?.transcript?.segments ?? [])
const edits = computed<EditDecision[]>(() => activeTimeline.value?.edits ?? [])
// v3.0.0 M11-2: read-only extension tracks for the Timeline bottom lane
const activeTracks = computed(() => activeTimeline.value?.transcript?.tracks ?? [])

const deleteRanges = computed(() => {
  return edits.value
    .filter(e => e.action === "delete" && (e.status === "confirmed" || e.source === "subtitle_trim"))
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})

const {
  handleTimeUpdate: handlePlaybackTimeUpdate,
  handleSeeked: handlePlaybackSeeked,
  seek: seekPlayback,
} = useEditedPlayback({
  videoRef,
  previewMode,
  paused: videoPaused,
  rawDeleteRanges: deleteRanges,
  // M6-3: raw samples feed the clock (imperative playhead), not the ref.
  onTimeUpdate: (time) => { playbackClock.ingest(time) },
})

// M6-3: original-mode playback has no controller rAF loop (its skip logic is
// edited-only); the clock runs its own loop there. Edited mode feeds the
// clock through the controller's publish path above.
watch([previewMode, videoPaused], ([mode, paused]) => {
  if (!paused && mode === "original") playbackClock.start()
  else playbackClock.stop()
}, { immediate: true })

// M6-3 demo bridge: useDemoPlayback writes the coarse ref directly (no video
// element exists). Ingest mirrors each write into the raw domain so the
// imperative playhead stays smooth in demo; identical-value coarse writes are
// skipped inside ingest, so this watch cannot loop.
if (demoMode) {
  watch(currentTime, (t) => { playbackClock.ingest(t) })
}

const demoPlayback = useDemoPlayback({
  currentTime,
  duration: computed(() => props.project.media?.duration ?? 0),
  paused: videoPaused,
  playbackRate: videoPlaybackRate,
  enabled: demoMode,
})

function togglePreviewMode() {
  previewMode.value = previewMode.value === "edited" ? "original" : "edited"
}

// v3.0.0 M8-2b: ASR engine domain unified in useAsrEngines (single source
// shared with the settings tabs -- plugin discovery, per-engine settings,
// GPU/compute derivation, persistence). State is a module-level singleton.
const {
  asrEngine,
  asrPluginId,
  asrSettingsPerEngine,
  installedEngines,
  hasInstalledEngines,
  availableModels,
  isDarwin,
  isMlx,
  supportsGpu,
  computeTypeOptions,
  ensureLoaded: ensureAsrEnginesLoaded,
  saveAsrSettings,
  checkEngineReady,
} = useAsrEngines()

const silenceThreshold = ref(-30)
const silenceMinDuration = ref(0.5)
const silenceMargin = ref(0.0)
const silenceSubtitlePadding = ref(0.0)
const trimSubtitlesOnOverlap = ref(true)
const globalEditMode = ref(false)
const showConfirmDeleteSilence = ref(false)
const subtitleTrimPadding = ref(0.3)
const showSubtitleTrimSettings = ref(false)
// v2.1.1 M4-4: search bar visibility (driven by toolbar button + Ctrl+F)
const showSearchBar = ref(false)
// v2.1.1 M4-5: timeline rename inline-edit state
const renamingTimelineId = ref<string | null>(null)
const renameValue = ref("")
// v2.1.1 M4-4: search bar component ref (to focus on open)
const searchBarRef = ref<{ show: () => void; hide: () => void } | null>(null)

watch(statusMessage, (msg) => {
  if (statusTimer) {
    clearTimeout(statusTimer)
    statusTimer = null
  }
  if (msg) {
    statusTimer = setTimeout(() => {
      statusMessage.value = ""
      statusTimer = null
    }, 5000)
  }
})

// Auto-save state
const isDirty = ref(false)
const isSaving = ref(false)
const lastSavedAt = ref<number | null>(null)

// v3.0.0 M3-6: workflow failure rollback restored layers on the backend --
// pull the updated project and surface the outcome.
onEvent<{ workflow_instance_id: string; rolled_back_to_step: number; total_steps: number }>(
  EVENT_WORKFLOW_ROLLED_BACK,
  async (data) => {
    const res = await call<Project>("get_project")
    if (res.success && res.data) emit("project-updated", res.data)
    if (data.rolled_back_to_step >= 0) {
      showToast(`已回滚到步骤 ${data.rolled_back_to_step + 1} 前，工作流已结束`, "info", 4000)
    } else {
      showToast("回滚失败：快照缺少层级数据，请手动检查项目状态", "error", 5000)
    }
  },
)

onEvent<void>(EVENT_PROJECT_DIRTY, () => {
  isDirty.value = true
})

onEvent<void>(EVENT_PROJECT_SAVED, () => {
  isDirty.value = false
})

watch(isDirty, (dirty, _old, onCleanup) => {
  if (!dirty || isSaving.value) return
  const timer = setTimeout(async () => {
    if (isSaving.value) return
    isSaving.value = true
    try {
      const res = await call<void>("save_project")
      if (res.success) {
        isDirty.value = false
        lastSavedAt.value = Date.now()
      }
    } finally {
      isSaving.value = false
    }
  }, 2000)
  onCleanup(() => clearTimeout(timer))
})

const duration = computed(() => props.project.media?.duration ?? 0)
const analysisResults = computed(() => activeTimeline.value?.analysis?.results ?? [])

// v2.3.2 stage 3: relies on backend _enforce_segment_sort_invariant.
// See tests/test_segment_sort_invariant.py and core/project_service.py.
const mergedSegments = computed<Segment[]>(() => segments.value)

const silenceCount = computed(() => segments.value.filter(s => s.type === "silence").length)
const subtitleCount = computed(() => segments.value.filter(s => s.type === "subtitle").length)
const isTranscribing = computed(() => {
  const t = activeTask.value
  return t !== null && t.type === "transcription" && t.status === "running"
})

async function loadVideoUrl() {
  if (demoMode) return
  const proxyPath = props.project.media?.proxy_path
  const originalPath = props.project.media?.path
  // Prefer proxy_path when available, fallback to original
  const mediaPath = proxyPath || originalPath
  if (!mediaPath) return
  const res = await call<{ url: string; port: number }>("get_video_url", mediaPath)
  if (res.success && res.data) {
    videoUrl.value = res.data.url
  }
}

const regenPoll = { current: null as ReturnType<typeof setInterval> | null }  // M8-2c: polled from useWorkspaceActions

async function resolveWaveformUrl() {
  if (demoMode) return
  const res = await call<{ url: string }>("get_waveform_url")
  if (res.success && res.data) {
    waveformUrl.value = res.data.url + "?t=" + Date.now()
  }
  // If not available yet, the watcher on waveform_path or the
  // waveform_generation task completed event will re-trigger this.
}

onMounted(async () => {
  // Prioritize visible content (video + waveform) so the slide animation
  // isn't blocked. Settings/engine/model loads are deferred to idle time.
  await loadVideoUrl()
  await resolveWaveformUrl()

  // Deferred: non-visible configuration loads, run when the browser is idle
  // so they don't compete with the transition animation for the main thread.
  const runIdle = (cb: () => void | Promise<void>) => {
    if ("requestIdleCallback" in window) {
      requestIdleCallback(() => { cb() })
    } else {
      setTimeout(cb, 50)
    }
  }

  runIdle(async () => {
    await loadSilenceSettings()
    // M8-2b: engine discovery -> settings hydration contract lives inside
    // ensureLoaded (single-flight, shared with the settings tabs).
    await ensureAsrEnginesLoaded()
    // Phase 2: load LLM config status for AI assistant panel
    await loadLlmConfig()
  })
})

watch(() => props.project.media?.waveform_path, () => {
  resolveWaveformUrl()
})

// When waveform generation task completes, the backend updates the project's
// waveform_path which triggers the watcher above. But as a safety net, also
// listen for the task completed event and retry the URL resolution.
onEvent<{ task_id: string; task_type?: string; result?: { project?: Project }; result_meta?: { project_stripped?: boolean } }>(
  EVENT_TASK_COMPLETED,
  async (data) => {
    if (data.task_type === "waveform_generation") {
      resolveWaveformUrl()
    }
    if (data.task_type === "proxy_generation") {
      isGeneratingProxy.value = false
      // v3.0.0 M4: pull the project when the event payload is stripped.
      if (data.result?.project) {
        emit("project-updated", data.result.project)
      } else if (data.result_meta?.project_stripped) {
        const res = await call<Project>("get_project")
        if (res.success && res.data) emit("project-updated", res.data)
      }
      loadVideoUrl()
      showToast("Proxy video ready", "success", 2000)
    }
    // Phase 2: LLM task completion refreshes project (edits/analysis applied)
    if (
      data.task_type === "llm_smart_delete" ||
      data.task_type === "llm_subtitle_correction" ||
      data.task_type === "llm_highlight"
    ) {
      if (data.result?.project) {
        emit("project-updated", data.result.project)
      } else if (data.result_meta?.project_stripped) {
        const res = await call<Project>("get_project")
        if (res.success && res.data) emit("project-updated", res.data)
      }
    }
  },
)

// v2.1.1 M1-2: LLM single-function cancel completed cleanly.
// Show the "已取消" toast only once the backend confirms the cancel.
onEvent<{ task_id: string; task_type?: string }>(
  EVENT_TASK_CANCELLED,
  (data) => {
    if (
      data.task_type === "llm_smart_delete" ||
      data.task_type === "llm_subtitle_correction" ||
      data.task_type === "llm_highlight" ||
      data.task_type === "llm_semantic_search"
    ) {
      showToast("已取消", "info", 2000)
    }
  },
)

// When proxy_path or media path changes, reload video URL
watch(() => props.project.media?.proxy_path, () => {
  loadVideoUrl()
})
watch(() => props.project.media?.path, () => {
  loadVideoUrl()
})
watch(() => props.project.project?.name, () => { clearHistory() })
// v2.1.1: Hydrate highlight state from persisted project data on reopen (Bug C).
// Also hydrate subtitle corrections so the "查看修正结果" button persists across
// sessions (Issue 4).
watch(() => props.project, async (newProject) => {
  hydrateHighlightsFromProject(newProject)
  const tlId = newProject.active_timeline_id
  if (tlId) {
    await loadCorrections(tlId)
  }
}, { immediate: true })

async function loadSilenceSettings() {
  const res = await call<Record<string, unknown>>("get_settings")
  if (res.success && res.data) {
    silenceThreshold.value = Number(res.data.silence_threshold_db ?? -30)
    silenceMinDuration.value = Number(res.data.silence_min_duration ?? 0.5)
    silenceMargin.value = Number(res.data.silence_margin ?? 0.0)
    silenceSubtitlePadding.value = Number(res.data.silence_subtitle_padding ?? 0.0)
    trimSubtitlesOnOverlap.value = res.data.trim_subtitles_on_silence_overlap !== false
  }
}

// M8-2b: persistence logic moved into useAsrEngines.saveAsrSettings; the
// page wrapper keeps the original UI side effect of closing the popover.
async function handleSaveAsrSettings(): Promise<boolean> {
  const ok = await saveAsrSettings()
  if (ok) {
    showTranscribeSettings.value = false
  }
  return ok
}

async function saveSilenceSettings() {
  await call("update_settings", {
    silence_threshold_db: silenceThreshold.value,
    silence_min_duration: silenceMinDuration.value,
    silence_margin: silenceMargin.value,
    silence_subtitle_padding: silenceSubtitlePadding.value,
    trim_subtitles_on_silence_overlap: trimSubtitlesOnOverlap.value,
  })
  showSilenceSettings.value = false
}

// -- Timeline operations ----------------------------------------------

// v2.1.1 A-4: in-app modal replacement for window.confirm.
// window.confirm is a blocking native dialog that steals focus from the
// DaisyUI dropdown, causing the whole TimelineSwitcher panel to collapse
// after delete. Using <dialog> + a Promise resolver keeps focus inside the
// app and lets the dropdown stay open.
interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}
const confirmModalRef = ref<HTMLDialogElement | null>(null)
const confirmState = ref<ConfirmOptions>({ title: "", message: "" })
let confirmResolver: ((v: boolean) => void) | null = null

function confirmAction(opts: ConfirmOptions): Promise<boolean> {
  confirmState.value = opts
  nextTick(() => confirmModalRef.value?.showModal())
  return new Promise<boolean>((resolve) => {
    confirmResolver = resolve
  })
}

function resolveConfirm(value: boolean) {
  confirmModalRef.value?.close()
  if (confirmResolver) {
    confirmResolver(value)
    confirmResolver = null
  }
}

// ===== Phase 2: LLM task handlers =====

// v2.1.1 M4-4: toggle search bar visibility (toolbar button)
function handleToggleSearchBar() {
  showSearchBar.value = !showSearchBar.value
  if (showSearchBar.value) {
    searchBarRef.value?.show()
  } else {
    searchBarRef.value?.hide()
  }
}

// v2.1.1 M4-5: timeline rename
function startRenameTimeline(timelineId: string) {
  const tl = props.project.timelines.find(t => t.id === timelineId)
  if (!tl) return
  renamingTimelineId.value = timelineId
  renameValue.value = tl.label
}

async function confirmRenameTimeline() {
  const id = renamingTimelineId.value
  const label = renameValue.value.trim()
  renamingTimelineId.value = null
  if (!id || !label) return
  const res = await call<Project>("rename_timeline", id, label)
  if (res.success && res.data) {
    emit("project-updated", res.data)
    showToast("已重命名", "success", 1500)
  } else {
    showToast(res.error ?? "重命名失败", "error", 3000)
  }
}

function cancelRenameTimeline() {
  renamingTimelineId.value = null
  renameValue.value = ""
}

// ESC key closes P1 fullscreen diff view (D-16 UX补齐)
function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Escape" && showSubtitleFullscreen.value) {
    showSubtitleFullscreen.value = false
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener("keydown", handleKeydown)
})

function isTextInput(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === "INPUT" || tag === "TEXTAREA") return true
  if (el.isContentEditable) return true
  return false
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (isTextInput(e.target)) return

  // v3.0.0 fix (macOS smoke): Cmd is the primary modifier on macOS
  const mod = e.ctrlKey || e.metaKey

  if (e.shiftKey && e.code === "Space") {
    e.preventDefault()
    previewMode.value = previewMode.value === "original" ? "edited" : "original"
    return
  }
  if (e.key === " ") {
    e.preventDefault()
    handleTogglePlay()
    return
  }
  if (mod && e.key === "s") {
    e.preventDefault()
    handleSaveProject()
    return
  }
  if (mod && e.key === "z" && !e.shiftKey) {
    e.preventDefault()
    handleUndo()
    return
  }
  if (mod && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
    e.preventDefault()
    handleRedo()
    return
  }
  // §8: Ctrl/Cmd+F toggle search/replace bar
  if (mod && e.key === "f") {
    e.preventDefault()
    handleToggleSearchBar()
    return
  }
  // §8: I / O — jump to selected segment start / end
  if (e.key === "i" || e.key === "I") {
    if (editSelectedSegmentId.value) {
      const seg = segments.value.find(s => s.id === editSelectedSegmentId.value)
      if (seg) {
        e.preventDefault()
        handleSeek(seg.start)
        return
      }
    }
  }
  if (e.key === "o" || e.key === "O") {
    if (editSelectedSegmentId.value) {
      const seg = segments.value.find(s => s.id === editSelectedSegmentId.value)
      if (seg) {
        e.preventDefault()
        handleSeek(seg.end)
        return
      }
    }
  }
  // §8: Ctrl+Shift+A confirm all, Ctrl+Shift+D reject all
  if (e.ctrlKey && e.shiftKey && e.key === "A") {
    e.preventDefault()
    handleConfirmAllSuggestions()
    return
  }
  if (e.ctrlKey && e.shiftKey && e.key === "D") {
    e.preventDefault()
    handleRejectAllSuggestions()
    return
  }
  // v2.1.1 M4-1: selection-mode keyboard shortcuts
  if (selectionMode.value) {
    if (e.key === "Escape") {
      e.preventDefault()
      if (selectedCount.value > 0) {
        clearMultiSelection()
      } else {
        toggleSelectionMode()
      }
      return
    }
    if (e.key === "Enter" && selectedCount.value >= 2) {
      e.preventDefault()
      handleMergeSelected()
      return
    }
    if (e.key === "Delete" && selectedCount.value > 0) {
      e.preventDefault()
      // batch mark selected segments for deletion (toggle-status, not erase)
      void markSelectedForDeletion()
      return
    }
  }
}

function handleClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  // Close transcribe settings popup when clicking outside
  if (showTranscribeSettings.value && !target.closest(".relative.inline-flex.items-center")) {
    showTranscribeSettings.value = false
  }
}

async function handleUndo() {
  await flushPendingUpdates()
  await flushPendingTrackUpdates()
  if (!projectRef.value) return
  const res = await undo(projectRef.value)
  if (res.ok) {
    if (res.patch) {
      // Apply the backend ProjectPatch through the standard channel
      // (App.vue updates lastSeenRevision, no full-project emit).
      emit("project-updated", res.patch)
    }
    showToast("Undo", "success", 1500)
  } else if (res.error !== "empty") {
    await recoverFromUndoFailure()
  }
}

async function handleRedo() {
  await flushPendingUpdates()
  await flushPendingTrackUpdates()
  if (!projectRef.value) return
  const res = await redo(projectRef.value)
  if (res.ok) {
    if (res.patch) {
      emit("project-updated", res.patch)
    }
    showToast("Redo", "success", 1500)
  } else if (res.error !== "empty") {
    await recoverFromUndoFailure()
  }
}

/**
 * v3.0.0 M5 red line: a failed apply_undo (e.g. stale revision) must never
 * leave the UI stuck. Refresh the full project from the backend and drop
 * the history stacks.
 */
async function recoverFromUndoFailure() {
  clearHistory()
  const res = await call<Project>("get_project")
  if (res.success && res.data) {
    emit("project-updated", res.data)
  }
  showToast("撤销失败，已刷新项目状态", "error", 2500)
}

// v3.0.0 M8-2c: handler bodies grouped in useWorkspaceActions (five domains:
// playback / timeline / edit / llm / project) and provided to the component
// tree via WORKSPACE_ACTIONS_KEY. Undo/redo, global keydown, outside-click
// and search/popover UI state intentionally stay in the page.
const workspaceActions = createWorkspaceActions({
  emit, showToast,
  getProject: () => props.project,
  errorMessage, statusMessage,
  videoRef, videoUrl, waveformUrl, videoVolume, videoPlaybackRate,
  isGeneratingProxy, demoMode, regenPoll,
  subtitleTrimPadding, showConfirmDeleteSilence, showSettingsModal, showSubtitleFullscreen,
  isDirty, isSaving, lastSavedAt, mergedSegments,
  seekPlayback, demoPlayback, handlePlaybackTimeUpdate,
  runTranscription, runSilenceDetection, toggleEditStatus,
  updateSegmentText, updateSegmentTime, searchReplace, mergeSegments, splitSegment,
  deleteSegment, selectEditRange, generateSubtitleKeepRanges, deleteSubtitleTrimEdits,
  deleteSilenceSegments, confirmAllSuggestions, rejectAllSuggestions,
  selectedSegmentIds, editSelectedSegmentId,
  toggleSelectionMode, clearMultiSelection, handleSegmentClick,
  pushSnapshot, projectRef, flushPendingUpdates,
  llmConfig, loadLlmConfig,
  startSmartDelete, startSubtitleCorrection, startHighlight,
  highlightResults, hydrateHighlightsFromProject,
  pendingCorrections, loadCorrections, computeDiff,
  acceptCorrection, rejectCorrection, acceptHighConfidenceCorrections, clearCorrections,
  asr: { asrEngine, asrPluginId, asrSettingsPerEngine, installedEngines, checkEngineReady },
  handleSaveAsrSettings,
  confirmAction,
})
provideWorkspaceActions(workspaceActions)

// v3.0.2 M5-3: Shift-marquee hits on the multi-row waveform merge into the
// SAME global selection set the subtitle list uses (M3-2 ownership ruling).
function handleWaveformSelectSegments(ids: string[]) {
  if (ids.length === 0) return
  const next = new Set(selectedSegmentIds.value)
  for (const id of ids) next.add(id)
  selectedSegmentIds.value = next
}

// v3.0.2 smoke fix: whole-track deletion from the lane menu (确认后删除轨道及其全部字幕)。
async function handleDeleteTrackWaveform(trackId: string) {
  // 撤销可恢复（M5-1 快照），无需确认弹窗。
  await handleDeleteTrack(trackId)
}

// v3.0.2 smoke fix 3rd round: clear a track = ONE backend call.
async function handleClearTrack(trackId: string) {
  await handleClearTrackSegments(trackId)
}

// v3.0.2 smoke fix 3rd round: 建段模式 + lane click/drag -> add to that track.
function handleTrackCreate(trackId: string, start: number, end: number) {
  void handleAddTrackSegment(trackId, start, end)
}

// v3.0.2 M6-1: subtitle-list navigation jumps share the waveform's reveal
// semantics (REVEAL_BIAS + comfort skip + follow cooldown) so the playing
// row is actually in view after a list click. No-op in basic mode.
const waveformEditorRef = ref<InstanceType<typeof WaveformEditor> | null>(null)

// v3.0.2 smoke fix: surface a stale Python process EARLY -- the track
// deletion methods only exist after a full app restart (pywebview freezes
// the API surface at launch; the frontend hot-reloads, the backend does not).
onMounted(() => {
  window.setTimeout(() => {
    const api = (window as { pywebview?: { api?: Record<string, unknown> } }).pywebview?.api
    if (api && typeof api.delete_track !== "function") {
      showToast("检测到后端进程为旧版本（无轨道删除能力）：请完全退出 Milo-Cut 后重新运行 dev.py", "error", 10000)
    }
  }, 3000)
})
/** M5-3: true while the waveform playhead is scrubbed (list follow skips). */
const waveformScrubbing = ref(false)
function handleListSeek(time: number) {
  handleSeek(time)
  waveformEditorRef.value?.revealTime(time)
}

const {
  handleRegenerateWaveform, handleRequestProxy, handleSeek, handleSetTime,
  handleVideoLoaded, handleTimeUpdate, handleTogglePlay, handleSeekTo,
  handleVolumeChange, handleRateChange, handleFullscreen,
  handleSwitchTimeline, handleCreateTimeline, handleDeleteTimeline,
  handleImportSrt, handleImportSrtAsTrack, handleDetectSilence, handleClearSubtitles, handleTranscribe,
  handleDeleteTrackSegment,
  handleDeleteTrack,
  handleAddTrack,
  handleAddTrackSegment,
  handleClearTrackSegments,
  handleToggleEditStatus, handleSegmentClickInSelection, handleToggleSelectionMode,
  handleMergeSelected, handleSplitSegment, handleUpdateText, handleUpdateTime,
  handleSelectRange, handleAddSegment, handleDeleteSegment, handleSeekSegment,
  handleSubtitleTrim, handleDeleteSubtitleTrimEdits, handleConfirmDeleteSilence,
  markSelectedForDeletion,
  handleConfirmAllSuggestions, handleRejectAllSuggestions,
  handleStartSmartDelete, handleStartSubtitleCorrection, handleStartHighlight,
  handleCancelSingle, handleOpenSubtitleFullscreen,
  handleAcceptCorrection, handleRejectCorrection, handleAcceptHighConfidence,
  handleClearCorrections, handleRemoveHighlight, handleAddToHighlight,
  renderDiff, categoryLabel,
  handleCloseProject, handleSaveProject, handleSettingsClosed,
  handleGoToSettings, handleSearchReplace,
} = workspaceActions

onMounted(() => {
  document.addEventListener("keydown", handleGlobalKeydown)
  document.addEventListener("mousedown", handleClickOutside)
  syncCompactDemo()
  window.addEventListener("resize", syncCompactDemo)
})

onUnmounted(() => {
  document.removeEventListener("keydown", handleGlobalKeydown)
  document.removeEventListener("mousedown", handleClickOutside)
  window.removeEventListener("resize", syncCompactDemo)
  if (regenPoll.current) clearInterval(regenPoll.current)
})
</script>

<template>
  <DemoResponsiveWorkspace
    v-if="demoMode && isCompactDemo"
    :project="props.project"
    :current-time="currentTime"
    :duration="duration"
    :paused="videoPaused"
    :volume="videoVolume"
    :playback-rate="videoPlaybackRate"
    :preview-mode="previewMode"
    :delete-ranges="deleteRanges"
    :llm-configured="llmConfig.configured"
    :llm-is-running="llmIsRunning"
    :llm-progress="llmProgress"
    :llm-error-msg="llmErrorMsg"
    :corrections="pendingCorrections"
    @update:current-time="handleSeekTo"
    @update:volume="handleVolumeChange"
    @update:playback-rate="handleRateChange"
    @toggle-play="handleTogglePlay"
    @toggle-preview="togglePreviewMode"
    @seek="handleSeek"
    @update-text="handleUpdateText"
    @confirm-edit="confirmEdit"
    @reject-edit="rejectEdit"
    @start-smart-delete="handleStartSmartDelete"
    @start-subtitle-correction="handleStartSubtitleCorrection"
    @accept-correction="handleAcceptCorrection"
    @reject-correction="handleRejectCorrection"
    @start-highlight="handleStartHighlight"
    @go-to-export="emit('go-to-export')"
    @project-closed="handleCloseProject"
  />

  <div v-else class="flex h-screen flex-col bg-canvas">
    <!-- Top nav -->
    <nav class="flex h-11 items-center justify-between border-b border-white/10 bg-surface-tile-1 px-4">
      <div class="flex items-center gap-3">
        <button
          class="mc-button mc-button-quiet min-h-8 p-1 text-gray-400 hover:bg-white/10 hover:text-white"
          title="返回项目"
          aria-label="返回项目"
          @click="handleCloseProject"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
        <span class="text-xs text-gray-400">
          {{ subtitleCount }} 条字幕 · {{ silenceCount }} 段静音 · {{ formatTimeShort(duration) }}
        </span>
        <TimelineSwitcher
          :timelines="props.project.timelines"
          :active-timeline-id="props.project.active_timeline_id"
          :renaming-id="renamingTimelineId"
          :rename-val="renameValue"
          @switch="handleSwitchTimeline"
          @create="handleCreateTimeline"
          @delete="handleDeleteTimeline"
          @rename-start="startRenameTimeline"
          @rename-input="(_id: string, val: string) => (renameValue = val)"
          @rename-confirm="confirmRenameTimeline"
          @rename-cancel="cancelRenameTimeline"
        />
        <button
          v-if="!props.project.media?.proxy_path"
          class="mc-button mc-button-quiet ml-2 min-h-7 border border-white/20 px-2 py-0.5 text-xs hover:border-white/50 hover:bg-white/10 hover:text-white"
          :disabled="isGeneratingProxy"
          title="生成代理视频以提升预览速度"
          @click="handleRequestProxy"
        >
          {{ isGeneratingProxy ? "生成中…" : "生成代理视频" }}
        </button>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="confirmedEdits.length > 0" class="text-xs text-status-pending">
          {{ confirmedEdits.length }} 处修改 · -{{ formatTimeShort(estimatedSaving) }}
        </span>
        <!-- Inline auto-save indicator -->
        <span v-if="isSaving" class="text-xs text-blue-300">保存中…</span>
        <span v-else-if="isDirty" class="text-xs text-gray-400">●</span>
        <span v-else-if="lastSavedAt" class="text-xs text-green-400">已保存</span>
        <!-- v3.0.0 fix (macOS smoke): explicit undo/redo buttons -->
        <button
          class="mc-button mc-button-quiet min-h-8 px-2 py-1 text-xs hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canUndo"
          title="撤销（⌘/Ctrl+Z）"
          @click="handleUndo"
        >
          ↩ 撤销
        </button>
        <button
          class="mc-button mc-button-quiet min-h-8 px-2 py-1 text-xs hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="!canRedo"
          title="重做（⌘/Ctrl+Shift+Z / Ctrl+Y）"
          @click="handleRedo"
        >
          ↪ 重做
        </button>
        <button
          class="mc-button mc-button-quiet min-h-8 px-2 py-1 text-xs hover:bg-white/10 hover:text-white"
          title="保存项目（⌘/Ctrl+S）"
          @click="handleSaveProject"
        >
          Save
        </button>
      </div>
    </nav>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 border-b border-hairline bg-parchment px-4 py-2">
      <button
        class="mc-button mc-button-primary"
        :disabled="isDetecting || isExporting"
        @click="handleImportSrt"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        导入 SRT
      </button>
      <!-- v3.0.0 M11-2: import an SRT as a read-only extension track -->
      <button
        class="mc-button mc-button-secondary"
        :disabled="isDetecting || isExporting"
        title="作为只读副轨导入 SRT（与主轨自动对齐绑定）"
        @click="handleImportSrtAsTrack"
      >
        导入副轨
      </button>
      <button
        class="mc-button"
        data-test="add-track-button"
        title="新建一条空的副轨（建段模式下在其上点击即可添加字幕）"
        @click="handleAddTrack"
      >
        新建副轨
      </button>
      <button
        class="mc-button"
        :class="previewMode === 'edited'
          ? 'mc-button-primary'
          : 'mc-button-secondary'"
        :disabled="isDetecting || isExporting"
        title="Toggle original/edited preview (Shift+Space)"
        @click="togglePreviewMode"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
        {{ previewMode === 'edited' ? '已剪辑预览' : '原始预览' }}
      </button>
      <div class="relative inline-flex items-center">
        <button
          class="mc-button mc-button-primary rounded-r-none"
          :disabled="isDetecting || isExporting || isTranscribing || !hasInstalledEngines || uvAvailable === false"
          :title="uvAvailable === false ? '需要安装 uv' : undefined"
          @click="handleTranscribe"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
          {{ isTranscribing ? '转写中…' : '开始转写' }}
        </button>
        <button
          class="mc-button mc-button-primary min-w-8 rounded-l-none border-l border-white/30 px-1.5"
          :disabled="isDetecting || isExporting || isTranscribing || uvAvailable === false"
          :title="uvAvailable === false ? '需要安装 uv' : 'Transcription settings'"
          @click="showTranscribeSettings = !showTranscribeSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <TranscribeSettingsPopover
          v-if="showTranscribeSettings && uvAvailable !== false"
          v-model:asr-plugin-id="asrPluginId"
          v-model:model-size="asrSettingsPerEngine[asrEngine].model_size"
          v-model:language="asrSettingsPerEngine[asrEngine].language"
          v-model:device="asrSettingsPerEngine[asrEngine].device"
          v-model:compute-type="asrSettingsPerEngine[asrEngine].compute_type"
          v-model:vad-filter="asrSettingsPerEngine[asrEngine].vad_filter"
          v-model:vad-threshold="asrSettingsPerEngine[asrEngine].vad_threshold"
          v-model:vad-min-silence-ms="asrSettingsPerEngine[asrEngine].vad_min_silence_ms"
          :has-installed-engines="hasInstalledEngines"
          :installed-engines="installedEngines"
          :available-models="availableModels"
          :asr-engine="asrEngine"
          :is-mlx="isMlx"
          :is-darwin="isDarwin"
          :supports-gpu="supportsGpu"
          :compute-type-options="computeTypeOptions"
          @save="handleSaveAsrSettings"
        />
      </div>
      <button
        class="mc-button mc-button-danger"
        :disabled="isDetecting || isExporting || isTranscribing || subtitleCount === 0"
        title="Delete all subtitle segments"
        @click="handleClearSubtitles"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
        清空字幕
      </button>
      <div class="relative inline-flex items-center">
        <button
          class="mc-button mc-button-primary rounded-r-none"
          :disabled="isDetecting || isExporting"
          @click="handleDetectSilence"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" /><path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
          {{ isDetecting ? '检测中…' : '检测静音' }}
        </button>
        <button
          class="mc-button mc-button-primary min-w-8 rounded-l-none border-l border-white/30 px-1.5"
          :disabled="isDetecting || isExporting"
          title="Silence detection settings"
          @click="showSilenceSettings = !showSilenceSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <SilenceSettingsPopover
          v-if="showSilenceSettings"
          v-model:threshold="silenceThreshold"
          v-model:min-duration="silenceMinDuration"
          v-model:margin="silenceMargin"
          v-model:subtitle-padding="silenceSubtitlePadding"
          v-model:trim-subtitles="trimSubtitlesOnOverlap"
          @save="saveSilenceSettings"
        />
      </div>

      <!-- Delete all silence markers -->
      <button
        class="mc-button mc-button-danger min-w-8 px-2"
        :disabled="isDetecting || isExporting || silenceCount === 0"
        title="Delete all silence markers"
        @click="showConfirmDeleteSilence = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <!-- Separator: silence group | subtitle group -->
      <div class="h-6 w-px bg-hairline"></div>

      <div class="relative inline-flex items-center">
        <button
          class="mc-button mc-button-secondary rounded-r-none"
          :disabled="isDetecting || isExporting"
          title="Auto-trim: delete gaps between subtitle segments"
          @click="handleSubtitleTrim"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L4.939 4.939m7.061 7.061l-2.879-2.879M12 12l2.879-2.879" /></svg>
          自动裁剪字幕间隙
        </button>
        <button
          class="mc-button mc-button-secondary min-w-8 rounded-l-none border-l border-hairline px-1.5"
          :disabled="isDetecting || isExporting"
          title="Subtitle trim settings"
          @click="showSubtitleTrimSettings = !showSubtitleTrimSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <SubtitleTrimSettingsPopover
          v-if="showSubtitleTrimSettings"
          v-model:padding="subtitleTrimPadding"
        />
      </div>

      <!-- Clear subtitle trim markers -->
      <button
        class="mc-button mc-button-danger min-w-8 px-2"
        :disabled="isDetecting || isExporting"
        title="Clear all subtitle trim markers"
        @click="handleDeleteSubtitleTrimEdits"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <div class="flex-1" />

      <button
        class="mc-button mc-button-primary"
        :disabled="isExporting || (confirmedEdits.length === 0 && subtitleCount === 0)"
        @click="emit('go-to-export')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
        导出
      </button>

      <div v-if="isDetecting && detectionProgress" class="flex-1 max-w-xs">
        <ProgressBar :percent="detectionProgress.percent" :message="detectionProgress.message" />
      </div>
      <div v-else-if="isExporting && exportProgress" class="flex-1 max-w-xs">
        <ProgressBar :percent="exportProgress.percent" :message="exportProgress.message" />
      </div>
    </div>

    <!-- Search replace bar (v2.1.1 M4-4: also toggled via toolbar button) -->
    <SearchReplaceBar ref="searchBarRef" @search-replace="handleSearchReplace" @close="showSearchBar = false" />

    <!-- Status messages -->
    <div v-if="statusMessage" class="flex items-center border-b border-hairline bg-primary-soft px-4 py-1 text-xs text-primary">
      <span class="flex-1">{{ statusMessage }}</span>
      <button
        class="ml-2 shrink-0 rounded p-0.5 hover:bg-white transition-colors"
        @click="statusMessage = ''"
      >
        <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="errorMessage" class="border-b border-hairline bg-status-confirmed px-4 py-1 text-xs text-status-warning">
      {{ errorMessage }}
    </div>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <SplitPanel storage-key="milo-split-workspace" :min-ratio="0.25" :max-ratio="0.75">
        <template #left>
          <!-- Left: Video player area -->
          <div class="flex h-full min-w-0 flex-col bg-surface-tile-1">
        <div class="flex flex-1 items-center justify-center p-2 overflow-hidden">
          <div v-if="demoMode" class="relative flex h-full w-full items-center justify-center">
            <DemoPreviewSurface
              :segments="mergedSegments"
              :current-time="currentTime"
              :duration="duration"
              :preview-mode="previewMode"
              :delete-ranges="deleteRanges"
            />
          </div>
          <div v-else-if="videoUrl" class="relative flex flex-col w-full h-full items-center justify-center">
            <video
              ref="videoRef"
              :src="videoUrl"
              class="max-h-full max-w-full rounded-[var(--radius-control)] shadow-[3px_5px_30px_rgba(0,0,0,0.28)]"
              preload="metadata"
              @loadedmetadata="handleVideoLoaded"
              @timeupdate="handleTimeUpdate"
              @play="videoPaused = false"
              @pause="videoPaused = true"
              @seeked="handlePlaybackSeeked"
              @click="handleTogglePlay"
            />
            <SubtitleOverlay
              :segments="mergedSegments"
              :video-ref="videoRef"
              :secondary="{ tracks: activeTracks, bindings: activeBindings }"
              :show-secondary="showSecondarySubtitle"
            />
            <!-- Proxy generation overlay -->
            <div
              v-if="isGeneratingProxy"
              class="absolute inset-0 z-raised flex flex-col items-center justify-center rounded-[var(--radius-control)] bg-black/60"
            >
              <svg class="animate-spin h-8 w-8 text-white mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span class="text-sm font-semibold text-white">正在生成代理视频…</span>
            </div>
          </div>
          <div v-else class="text-center text-ink-muted">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">正在加载视频…</p>
          </div>
        </div>
        <VideoControls
          :current-time="currentTime"
          :duration="duration"
          :paused="videoPaused"
          :volume="videoVolume"
          :playback-rate="videoPlaybackRate"
          :delete-ranges="deleteRanges"
          :preview-mode="previewMode"
          @update:current-time="handleSeekTo"
          @update:volume="handleVolumeChange"
          @update:playback-rate="handleRateChange"
          @toggle-play="handleTogglePlay"
          @toggle-fullscreen="handleFullscreen"
        />
          </div>
        </template>

        <template #right>
          <!-- Right: Timeline (transcript editor + suggestion panel) -->
          <div class="relative flex flex-1 flex-col overflow-hidden bg-canvas">
          <Timeline
            :segments="mergedSegments"
            :edits="edits"
            :analysis-results="analysisResults"
            :subtitle-count="subtitleCount"
            :silence-count="silenceCount"
            :selected-segment-id="editSelectedSegmentId"
            :global-edit-mode="globalEditMode"
            :selection-mode="selectionMode"
            :selected-segment-ids="selectedSegmentIds"
            :selected-count="selectedCount"
            :show-search-bar="showSearchBar"
            :current-time="currentTime"
            :scrubbing="waveformScrubbing"
            :llm-configured="llmConfig.configured"
            :llm-model="llmConfig.model"
            :llm-is-running="llmIsRunning"
            :llm-progress="llmProgress"
            :llm-error-msg="llmErrorMsg"
            :subtitle-correction-count="subtitleCorrectionCount"
            :pending-correction-count="pendingCorrections.length"
            :highlight-items="highlightResults"
            :highlight-total-duration="highlightTotalDuration"
            :highlight-target-duration="highlightTargetDuration"
            :jump-cuts="jumpCuts"
            @seek="handleListSeek"
            @update-text="handleUpdateText"
            @update-time="handleUpdateTime"
            @toggle-status="(seg) => handleToggleEditStatus(seg)"
            @confirm-segment="(seg) => handleToggleEditStatus(seg, 'confirmed')"
            @reject-segment="(seg) => handleToggleEditStatus(seg, 'rejected')"
            @delete-segment="(seg) => handleDeleteSegment(seg.id)"
            @confirm-suggestion="confirmEdit"
            @reject-suggestion="rejectEdit"
            @confirm-suggestion-batch="(ids: string[]) => batchUpdateEdits(ids, 'confirmed')"
            @reject-suggestion-batch="(ids: string[]) => batchUpdateEdits(ids, 'rejected')"
            @delete-suggestion-batch="(ids: string[]) => deleteEdits(ids)"
            @seek-suggestion="handleListSeek"
            @toggle-edit-mode="globalEditMode = !globalEditMode"
            @start-smart-delete="handleStartSmartDelete"
            @start-subtitle-correction="handleStartSubtitleCorrection"
            @open-subtitle-fullscreen="handleOpenSubtitleFullscreen"
            @start-highlight="handleStartHighlight"
            @go-to-settings="handleGoToSettings"
            @cancel-single="handleCancelSingle"
            @toggle-selection-mode="handleToggleSelectionMode"
            @segment-click="handleSegmentClickInSelection"
            @merge-selected="handleMergeSelected"
            @clear-selection="clearMultiSelection"
            @split-segment="handleSplitSegment"
            @split-at-pointer="handleSplitSegment"
            @toggle-search-bar="handleToggleSearchBar"
            @toast="(msg: string) => showToast(msg, 'info', 3000)"
            @remove-highlight="handleRemoveHighlight"
            @add-to-highlight="handleAddToHighlight"
          />
          </div>
        </template>
      </SplitPanel>
    </div>

    <!-- Bottom: Waveform editor -->
    <WaveformEditor
      ref="waveformEditorRef"
      :segments="mergedSegments"
      :edits="edits"
      :duration="duration"
      :current-time="currentTime"
      :waveform-path="demoMode ? undefined : waveformUrl"
      :demo-mode="demoMode"
      :tracks="activeTracks"
      :update-time="updateSegmentTime"
      :update-track-time="updateTrackSegmentTime"
      :global-edit-mode="globalEditMode"
      :selection-mode="selectionMode"
      @seek="handleSeek"
      @set-time="handleSetTime"
      @select-range="handleSelectRange"
      @add-segment="handleAddSegment"
      @delete-segment="handleDeleteSegment"
      @seek-segment="handleSeekSegment"
      @regenerate-waveform="handleRegenerateWaveform"
      @split-segment="handleSplitSegment"
      @toast="(msg) => showToast(msg, 'info', 3000)"
      @toggle-play="handleTogglePlay"
      @select-segments="handleWaveformSelectSegments"
      @clear-selection="clearMultiSelection"
      @delete-track-segment="handleDeleteTrackSegment"
      @clear-track="handleClearTrack"
      @delete-track="handleDeleteTrackWaveform"
      @track-create="handleTrackCreate"
      @scrubbing="waveformScrubbing = $event"
    />

    <!-- Delete silence confirmation dialog -->
    <Teleport to="body">
      <div
        v-if="showConfirmDeleteSilence"
        class="fixed inset-0 z-modal flex items-center justify-center bg-black/40"
        @click.self="showConfirmDeleteSilence = false"
      >
        <div class="rounded-lg bg-white p-5 shadow-xl max-w-sm w-full mx-4">
          <h3 class="text-sm font-semibold text-gray-900">Delete All Silence Markers</h3>
          <p class="mt-2 text-xs text-gray-500">
            Delete all {{ silenceCount }} silence detection markers? This cannot be undone.
          </p>
          <div class="mt-4 flex justify-end gap-2">
            <button
              class="rounded px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 transition-colors"
              @click="showConfirmDeleteSilence = false"
            >
              Cancel
            </button>
            <button
              class="rounded bg-red-500 px-3 py-1.5 text-xs text-white hover:bg-red-600 transition-colors"
              @click="handleConfirmDeleteSilence"
            >
              Delete All
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Phase 2: Settings modal (opened from AI assistant "go to settings") -->
    <SettingsModal
      v-if="showSettingsModal"
      :visible="showSettingsModal"
      @close="handleSettingsClosed(); reloadAppSettings()"
    />

    <!-- Phase 2: P1 subtitle correction fullscreen diff view (D-16) -->
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="showSubtitleFullscreen"
          class="fixed inset-0 z-modal bg-white flex flex-col"
        >
          <div class="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <h2 class="text-base font-semibold text-gray-800">字幕修正审阅</h2>
            <button
              class="rounded-md px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-100 transition-colors"
              @click="showSubtitleFullscreen = false"
            >
              返回 (ESC)
            </button>
          </div>
          <div class="flex-1 overflow-y-auto p-6">
            <!-- Loading -->
            <div v-if="correctionsLoading" class="flex items-center gap-2 text-sm text-gray-500">
              <span class="loading loading-spinner loading-sm"></span>
              加载修正列表...
            </div>

            <!-- Empty -->
            <p v-else-if="pendingCorrections.length === 0" class="text-sm text-gray-500">
              暂无待审阅的修正。运行 P1 字幕修正后，修正建议将在此显示供逐条审阅。
            </p>

            <!-- Correction list -->
            <template v-else>
              <!-- Batch action bar -->
              <div class="mb-4 flex items-center gap-3">
                <button
                  class="rounded-md bg-green-600 px-3 py-1.5 text-xs text-white hover:bg-green-700 disabled:opacity-50"
                  :disabled="highConfidenceCorrections.length === 0"
                  @click="handleAcceptHighConfidence"
                >
                  信任全部高置信度 ({{ highConfidenceCorrections.length }})
                </button>
                <button
                  class="rounded-md border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                  @click="handleClearCorrections"
                >清除全部</button>
                <span class="text-xs text-gray-400">
                  共 {{ pendingCorrections.length }} 条
                </span>
              </div>

              <!-- High confidence section -->
              <div v-if="highConfidenceCorrections.length > 0" class="mb-6">
                <h3 class="mb-2 text-xs font-semibold text-green-700">
                  高置信度修正 ({{ highConfidenceCorrections.length }})
                </h3>
                <div
                  v-for="corr in highConfidenceCorrections"
                  :key="corr.id"
                  class="mb-2 rounded-lg border border-gray-200 bg-white p-3 text-sm"
                >
                  <div class="mb-1 flex items-center gap-2 text-xs text-gray-500">
                    <span>{{ formatTimeShort(corr.start) }}</span>
                    <span class="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">{{ categoryLabel(corr.category) }}</span>
                    <span>置信度 {{ corr.confidence.toFixed(2) }}</span>
                  </div>
                  <!-- Inline diff -->
                  <!-- M9-3: content is built by renderDiff() which escapes all text via
         escapeHtml() before wrapping in fixed, code-controlled spans. -->
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="leading-relaxed" v-html="renderDiff(corr)"></div>
                  <!-- Actions -->
                  <div class="mt-2 flex gap-2">
                    <button
                      class="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                      @click="handleAcceptCorrection(corr.id)"
                    >接受</button>
                    <button
                      class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                      @click="handleRejectCorrection(corr.id)"
                    >拒绝</button>
                  </div>
                </div>
              </div>

              <!-- Low confidence section (collapsed) -->
              <details v-if="lowConfidenceCorrections.length > 0" class="mb-4">
                <summary class="cursor-pointer text-xs font-semibold text-amber-700">
                  低置信度修正 ({{ lowConfidenceCorrections.length }}) -- 需手动确认
                </summary>
                <div
                  v-for="corr in lowConfidenceCorrections"
                  :key="corr.id"
                  class="mb-2 mt-2 rounded-lg border border-amber-200 bg-amber-50/40 p-3 text-sm"
                >
                  <div class="mb-1 flex items-center gap-2 text-xs text-gray-500">
                    <span>{{ formatTimeShort(corr.start) }}</span>
                    <span class="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">{{ categoryLabel(corr.category) }}</span>
                    <span>置信度 {{ corr.confidence.toFixed(2) }}</span>
                  </div>
                  <!-- M9-3: content is built by renderDiff() which escapes all text via
         escapeHtml() before wrapping in fixed, code-controlled spans. -->
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="leading-relaxed" v-html="renderDiff(corr)"></div>
                  <div class="mt-2 flex gap-2">
                    <button
                      class="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700"
                      @click="handleAcceptCorrection(corr.id)"
                    >接受</button>
                    <button
                      class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-50"
                      @click="handleRejectCorrection(corr.id)"
                    >拒绝</button>
                  </div>
                </div>
              </details>
            </template>
          </div>
        </div>
      </Transition>
    </Teleport>
    <!-- v2.1.1 A-4: in-app confirm modal (replaces window.confirm) -->
    <dialog ref="confirmModalRef" class="modal">
      <div class="modal-box">
        <h3 class="font-bold text-lg">{{ confirmState.title }}</h3>
        <p class="py-4 text-sm text-gray-600">{{ confirmState.message }}</p>
        <div class="modal-action">
          <button class="btn btn-sm" @click="resolveConfirm(false)">
            {{ confirmState.cancelText || "取消" }}
          </button>
          <button
            class="btn btn-sm"
            :class="confirmState.danger ? 'btn-error' : 'btn-primary'"
            @click="resolveConfirm(true)"
          >
            {{ confirmState.confirmText || "确定" }}
          </button>
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button @click="resolveConfirm(false)">close</button>
      </form>
    </dialog>
  </div>
</template>

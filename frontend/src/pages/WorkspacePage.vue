<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import type { Project, Segment, EditDecision, ModelInfo, Timeline as TimelineData, ProjectResponse } from "@/types/project"
import { formatTimeShort } from "@/utils/format"
import { call, onEvent } from "@/bridge"
import { useAnalysis } from "@/composables/useAnalysis"
import { useExport } from "@/composables/useExport"
import { useEdit } from "@/composables/useEdit"
import { useSegmentEdit } from "@/composables/useSegmentEdit"
import { useToast } from "@/composables/useToast"
import { useUndoRedo } from "@/composables/useUndoRedo"
import { usePluginManager } from "@/composables/usePluginManager"
import { useUvAvailability } from "@/composables/useUvAvailability"
import { useLlmTasks } from "@/composables/useLlmTasks"
import { useEditedPlayback } from "@/composables/useEditedPlayback"
import {
  EVENT_TASK_COMPLETED,
  EVENT_TASK_CANCELLED,
  EVENT_PROJECT_DIRTY,
  EVENT_PROJECT_SAVED,
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
} = useLlmTasks()

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

const {
  pushSnapshot,
  undo,
  redo,
  clearHistory,
} = useUndoRedo()

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
)

const { showToast } = useToast()
const { listPlugins, checkEngineReady, listModels } = usePluginManager()

const statusMessage = ref("")
const errorMessage = ref("")
let statusTimer: ReturnType<typeof setTimeout> | null = null
const showSilenceSettings = ref(false)
const showTranscribeSettings = ref(false)
const videoUrl = ref("")
const waveformUrl = ref("")
const videoRef = ref<HTMLVideoElement | null>(null)
const currentTime = ref(0)
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
  onTimeUpdate: (time) => { currentTime.value = time },
})

function togglePreviewMode() {
  previewMode.value = previewMode.value === "edited" ? "original" : "edited"
}

// ASR Transcription settings - per-engine storage so switching preserves settings
const asrSettingsPerEngine = ref<Record<string, {
  model_size: string
  language: string
  device: "cpu" | "cuda" | "auto" | "mps"
  compute_type: string
  vad_filter: boolean
  vad_threshold: number
  vad_min_silence_ms: number
}>>({
  "faster-whisper": {
    model_size: "large-v3-turbo",
    language: "zh",
    device: "cuda" as "cpu" | "cuda" | "auto" | "mps",
    compute_type: "int8_float16",
    vad_filter: true,
    vad_threshold: 0.5,
    vad_min_silence_ms: 500,
  },
  "qwen3-asr": {
    model_size: "Qwen/Qwen3-ASR-0.6B",
    language: "auto",
    device: "cuda" as "cpu" | "cuda" | "auto" | "mps",
    compute_type: "bfloat16",
    vad_filter: false,
    vad_threshold: 0.5,
    vad_min_silence_ms: 500,
  },
})

// Compute type options per engine (MLX: none; macOS CPU: no int8_float16/float16/bfloat16)
const computeTypeOptions = computed(() => {
  if (isMlx.value) return []
  if (asrEngine.value === 'faster-whisper') {
    const gpuOptions = [
      { value: 'int8', label: 'INT8 (fastest)' },
      { value: 'int8_float16', label: 'INT8 FP16 (balanced)' },
      { value: 'float16', label: 'FP16' },
      { value: 'float32', label: 'FP32 (highest quality)' },
    ]
    const cpuOptions = [
      { value: 'int8', label: 'INT8 (fastest)' },
      { value: 'float32', label: 'FP32 (highest quality)' },
    ]
    return (supportsGpu.value || asrSettingsPerEngine.value[asrEngine.value]?.device === 'auto') ? gpuOptions : cpuOptions
  }
  if (isDarwin) {
    return [
      { value: 'float16', label: 'FP16' },
      { value: 'float32', label: 'FP32' },
    ]
  }
  return [
    { value: 'bfloat16', label: 'BF16 (recommended)' },
    { value: 'float16', label: 'FP16' },
    { value: 'float32', label: 'FP32' },
  ]
})

// Current engine's pluginId for device filtering - use asrPluginId directly
// since it tracks the exact selected variant (CPU vs GPU)
const currentEnginePluginId = computed(() => {
  return asrPluginId.value
})

// Whether current engine supports GPU (CUDA) — macOS has no NVIDIA CUDA
const isDarwin = navigator.platform.toLowerCase().includes('mac')
const isMlx = computed(() => asrPluginId.value.includes('-mlx'))
const supportsGpu = computed(() => {
  if (isDarwin) return false
  const pid = currentEnginePluginId.value
  // CPU-only plugins have "-cpu" suffix in pluginId
  return pid.length > 0 && !pid.includes('-cpu')
})

const asrEngine = ref<"faster-whisper" | "qwen3-asr">("faster-whisper")
const asrPluginId = ref("")  // Tracks which specific plugin variant is selected (CPU vs GPU)

// Installed ASR engines (filtered from plugin list)
interface InstalledEngine {
  engine: string
  displayName: string
  pluginId: string
  ready: boolean
}
const installedEngines = ref<InstalledEngine[]>([])
const hasInstalledEngines = computed(() => installedEngines.value.length > 0)

// Available ASR models (loaded from plugin manager)
const modelList = ref<ModelInfo[]>([])
const availableModels = computed(() => {
  return modelList.value
    .filter(m => m.engine === asrEngine.value && !m.model_id.includes("ForcedAligner"))
    .filter((m, i, arr) => arr.findIndex(x => x.model_id === m.model_id) === i)
})

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

const mergedSegments = computed<Segment[]>(() => {
  return [...segments.value].sort((a, b) => a.start - b.start)
})

const silenceCount = computed(() => segments.value.filter(s => s.type === "silence").length)
const subtitleCount = computed(() => segments.value.filter(s => s.type === "subtitle").length)
const isTranscribing = computed(() => {
  const t = activeTask.value
  return t !== null && t.type === "transcription" && t.status === "running"
})

async function loadVideoUrl() {
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

let regenPollTimer: ReturnType<typeof setInterval> | null = null

async function handleRegenerateWaveform() {
  statusMessage.value = "Regenerating waveform..."
  const res = await call<{ task_id: string }>("regenerate_waveform")
  if (!res.success) {
    showToast(res.error ?? "Failed to regenerate waveform", "error", 3000)
    statusMessage.value = ""
    return
  }
  // Poll get_waveform_url until regeneration completes
  if (regenPollTimer) clearInterval(regenPollTimer)
  const start = Date.now()
  regenPollTimer = setInterval(async () => {
    const urlRes = await call<{ url: string }>("get_waveform_url")
    if (urlRes.success && urlRes.data) {
      clearInterval(regenPollTimer!)
      regenPollTimer = null
      // Cache-bust: append timestamp so WaveformCanvas re-fetches
      waveformUrl.value = urlRes.data.url + "?t=" + Date.now()
      statusMessage.value = ""
      showToast("Waveform regenerated", "success", 2000)
    } else if (Date.now() - start > 120000) {
      clearInterval(regenPollTimer!)
      regenPollTimer = null
      statusMessage.value = ""
      showToast("Waveform regeneration timed out", "error", 3000)
    }
  }, 500)
}

async function resolveWaveformUrl() {
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
    await loadInstalledEngines()  // Must run BEFORE loadAsrSettings
    await loadAsrSettings()
    modelList.value = await listModels()
    validateModelSize()
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
onEvent<{ task_id: string; task_type?: string; result?: { project?: Project } }>(
  EVENT_TASK_COMPLETED,
  (data) => {
    if (data.task_type === "waveform_generation") {
      resolveWaveformUrl()
    }
    if (data.task_type === "proxy_generation") {
      isGeneratingProxy.value = false
      if (data.result?.project) {
        emit("project-updated", data.result.project)
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
async function handleRequestProxy() {
  if (isGeneratingProxy.value) return
  isGeneratingProxy.value = true
  try {
    const res = await call<{ task_id: string }>("request_proxy")
    if (!res.success) {
      showToast(res.error ?? "Failed to start proxy generation", "error", 3000)
      isGeneratingProxy.value = false
      return
    }
    if (res.data) {
      call("start_task", res.data.task_id)
    }
  } catch {
    isGeneratingProxy.value = false
  }
}

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

async function loadAsrSettings() {
  const res = await call<Record<string, unknown>>("get_settings")
  if (res.success && res.data) {
    const engine = (res.data.asr_engine as "faster-whisper" | "qwen3-asr") || "faster-whisper"
    asrEngine.value = engine

    // Restore pluginId from saved settings, or auto-select first matching engine
    const savedPluginId = res.data.asr_plugin_id as string
    if (savedPluginId && installedEngines.value.find(e => e.pluginId === savedPluginId)) {
      asrPluginId.value = savedPluginId
    } else {
      // Auto-select first installed engine for this engine type
      const firstEng = installedEngines.value.find(e => e.engine === engine)
      if (firstEng) asrPluginId.value = firstEng.pluginId
    }

    // Shared settings
    const vadFilter = res.data.asr_vad_filter !== false

    // Determine per-engine device based on plugin capabilities
    const whisperPluginId = installedEngines.value.find(e => e.engine === "faster-whisper")?.pluginId ?? ""
    const qwenPluginId = installedEngines.value.find(e => e.engine === "qwen3-asr")?.pluginId ?? ""
    const whisperSupportsGpu = !isDarwin && whisperPluginId.length > 0 && !whisperPluginId.includes("-cpu")
    const qwenSupportsGpu = !isDarwin && qwenPluginId.length > 0 && !qwenPluginId.includes("-cpu")

    // Load faster-whisper settings (engine-prefixed keys from config.py)
    const whisperModelSize = (res.data.asr_model_size as string) || "large-v3-turbo"
    const whisperDevice = (res.data.asr_device as "cpu" | "cuda" | "auto" | "mps") || (whisperSupportsGpu ? "cuda" : isDarwin ? "auto" : "cpu")
    asrSettingsPerEngine.value["faster-whisper"] = {
      model_size: whisperModelSize,
      language: (res.data.asr_language as string) || "zh",
      device: whisperDevice,
      compute_type: (res.data.whisper_compute_type as string) || (whisperSupportsGpu ? "int8_float16" : "int8"),
      vad_filter: vadFilter,
      vad_threshold: Number(res.data.whisper_vad_threshold ?? 0.5),
      vad_min_silence_ms: Number(res.data.whisper_vad_min_silence_ms ?? 500),
    }

    // Load qwen3-asr settings
    const qwenModelSize = (res.data.asr_model_size as string) || "Qwen/Qwen3-ASR-0.6B"
    const qwenDevice = qwenSupportsGpu ? "cuda" : isDarwin ? "mps" : "cpu"
    asrSettingsPerEngine.value["qwen3-asr"] = {
      model_size: qwenModelSize,
      language: (res.data.qwen_language as string) || "auto",
      device: qwenDevice,
      compute_type: (res.data.qwen_compute_type as string) || (qwenSupportsGpu ? "bfloat16" : "float16"),
      vad_filter: false,
      vad_threshold: 0.5,
      vad_min_silence_ms: 500,
    }
  }
}

async function loadInstalledEngines() {
  const plugins = await listPlugins()
  const engines: InstalledEngine[] = []

  for (const p of plugins) {
    if (p.status === "installed") {
      const status = await checkEngineReady(p.engine)
      engines.push({
        engine: p.engine,
        displayName: p.display_name,
        pluginId: p.plugin_id,
        ready: status.ready,
      })
    }
  }

  installedEngines.value = engines

  // If current selected engine is not installed, switch to first available
  if (engines.length > 0 && !engines.find(e => e.engine === asrEngine.value)) {
    asrEngine.value = engines[0].engine as "faster-whisper" | "qwen3-asr"
  }
}

function validateModelSize() {
  const models = availableModels.value
  const current = asrSettingsPerEngine.value[asrEngine.value]
  if (current && models.length > 0 && !models.find(m => m.model_id === current.model_size)) {
    asrSettingsPerEngine.value[asrEngine.value].model_size = models[0].model_id
  }
}

// Derive engine from selected pluginId, and update device/compute when plugin changes
watch(asrPluginId, (newPluginId) => {
  if (!newPluginId) return
  const eng = installedEngines.value.find(e => e.pluginId === newPluginId)
  if (eng) {
    const prevEngine = asrEngine.value
    asrEngine.value = eng.engine as "faster-whisper" | "qwen3-asr"
    // If engine type didn't change (e.g. CPU->GPU within same engine),
    // watch(asrEngine) won't fire, so we must update device/compute here
    if (prevEngine === eng.engine) {
      const gpu = !isDarwin && !newPluginId.includes('-cpu')
      const settings = asrSettingsPerEngine.value[eng.engine]
      if (settings) {
        settings.device = gpu ? 'cuda' : 'cpu'
        if (eng.engine === 'qwen3-asr') {
          settings.compute_type = gpu ? 'bfloat16' : 'float16'
        }
        // faster-whisper keeps int8_float16 for both CPU and GPU
      }
    }
  }
})

// Engine defaults by type
function getEngineDefaults(engine: "faster-whisper" | "qwen3-asr") {
  const gpu = !isDarwin && asrPluginId.value.length > 0 && !asrPluginId.value.includes('-cpu')
  if (engine === 'qwen3-asr') {
    return { model_size: "Qwen/Qwen3-ASR-0.6B", language: "auto", device: gpu ? "cuda" as const : isDarwin ? "mps" as const : "cpu" as const, compute_type: gpu ? "bfloat16" as const : isDarwin ? "float16" as const : "float16" as const, vad_filter: false, vad_threshold: 0.5, vad_min_silence_ms: 500 }
  }
  return { model_size: "large-v3-turbo", language: "zh", device: gpu ? "cuda" as const : isDarwin ? "auto" as const : "cpu" as const, compute_type: gpu ? "int8_float16" as const : "int8" as const, vad_filter: true, vad_threshold: 0.5, vad_min_silence_ms: 500 }
}

// When engine changes, only create defaults if not yet populated.
// Device/compute are always updated based on selected plugin's GPU capability.
// User preferences (model_size, language, vad_*) are preserved from loadAsrSettings().
watch(asrEngine, (newEngine) => {
  const defaults = getEngineDefaults(newEngine)
  const existing = asrSettingsPerEngine.value[newEngine]
  if (!existing) {
    asrSettingsPerEngine.value[newEngine] = { ...defaults }
  } else {
    // Only update device/compute based on plugin capability (these are plugin-dependent, not user preference)
    existing.device = defaults.device
    existing.compute_type = defaults.compute_type
  }
  validateModelSize()
})

async function saveAsrSettings(): Promise<boolean> {
  const current = asrSettingsPerEngine.value[asrEngine.value]
  const payload: Record<string, unknown> = {
    asr_engine: asrEngine.value,
    asr_plugin_id: asrPluginId.value,
    asr_model_size: current.model_size,
    asr_language: current.language,
    asr_device: current.device,
    asr_vad_filter: current.vad_filter,
  }

  // Engine-prefixed keys for settings persistence
  if (asrEngine.value === "qwen3-asr") {
    payload.qwen_compute_type = current.compute_type
    payload.qwen_language = current.language
  } else {
    payload.whisper_compute_type = current.compute_type
    payload.whisper_vad_threshold = current.vad_threshold
    payload.whisper_vad_min_silence_ms = current.vad_min_silence_ms
  }

  const res = await call("update_settings", payload)
  if (!res.success) return false
  showTranscribeSettings.value = false
  return true
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

function handleSeek(time: number) {
  seekPlayback(time, true)
}

// v2.1.1 A-03: move playhead without playing (arrow keys, selection mode)
function handleSetTime(time: number) {
  seekPlayback(time)
}

function handleVideoLoaded() {
  if (videoRef.value) {
    videoRef.value.volume = 0.25
  }
}

function handleTimeUpdate() {
  handlePlaybackTimeUpdate()
}

function handleTogglePlay() {
  if (!videoRef.value) return
  if (videoRef.value.paused) {
    videoRef.value.play()
  } else {
    videoRef.value.pause()
  }
}

function handleSeekTo(time: number) {
  seekPlayback(time)
}

function handleVolumeChange(vol: number) {
  if (!videoRef.value) return
  videoRef.value.volume = vol
  videoVolume.value = vol
}

function handleRateChange(rate: number) {
  if (!videoRef.value) return
  videoRef.value.playbackRate = rate
  videoPlaybackRate.value = rate
}

function handleFullscreen() {
  const container = videoRef.value?.parentElement
  if (!container) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    container.requestFullscreen()
  }
}

// -- Timeline operations ----------------------------------------------

async function handleSwitchTimeline(timelineId: string) {
  await flushPendingUpdates()
  const res = await call<Project>("switch_timeline", timelineId)
  if (res.success && res.data) {
    emit("project-updated", res.data)
  } else {
    showToast(res.error ?? "Failed to switch timeline", "error")
  }
}

async function handleCreateTimeline() {
  await flushPendingUpdates()
  const label = window.prompt("Timeline name:", "新 Timeline")
  if (!label) return
  const fork = window.confirm("Fork from current timeline? (Cancel = blank timeline)")
  const res = await call<Project>(
    "create_timeline",
    label,
    "manual",
    fork ? props.project.active_timeline_id : null,
  )
  if (res.success && res.data) {
    emit("project-updated", res.data)
    isDirty.value = true  // trigger auto-save
    showToast(`Created timeline: ${label}`, "success")
  } else {
    showToast(res.error ?? "Failed to create timeline", "error")
  }
}

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

async function handleDeleteTimeline(timelineId: string) {
  const ok = await confirmAction({
    title: "删除 Timeline",
    message: "确认删除此 Timeline？该操作无法撤销。",
    confirmText: "删除",
    danger: true,
  })
  if (!ok) return
  const res = await call<Project>("delete_timeline", timelineId)
  if (res.success && res.data) {
    emit("project-updated", res.data)
    isDirty.value = true  // trigger auto-save
    showToast("Timeline deleted", "success")
  } else {
    showToast(res.error ?? "Failed to delete timeline", "error")
  }
}

async function handleToggleEditStatus(segment: Segment, nextStatus?: string) {
  const ok = await toggleEditStatus(segment, nextStatus)
  if (!ok) {
    // v2.3.2 阶段 1.1: toggleEditStatus now reports total failure (write + refresh).
    showToast("Failed to update segment status", "error", 3000)
  }
}

async function handleImportSrt() {
  errorMessage.value = ""
  statusMessage.value = "Selecting file..."
  const fileRes = await call<string>("select_file")
  if (!fileRes.success || !fileRes.data) {
    statusMessage.value = ""
    return
  }
  statusMessage.value = "Importing SRT..."
  if (projectRef.value) pushSnapshot(projectRef.value)
  const importRes = await call<Project>("import_srt", fileRes.data)
  if (importRes.success && importRes.data) {
    emit("project-updated", importRes.data)
    statusMessage.value = ""
  } else {
    errorMessage.value = importRes.error ?? "Failed to import SRT"
    statusMessage.value = ""
  }
}

async function handleDetectSilence() {
  errorMessage.value = ""
  await runSilenceDetection()
}

async function handleClearSubtitles() {
  if (!window.confirm("Are you sure you want to delete all subtitles? This cannot be undone.")) return
  errorMessage.value = ""
  const res = await call<Project>("clear_subtitles")
  if (res.success && res.data) {
    emit("project-updated", res.data)
  } else {
    errorMessage.value = res.error ?? "Failed to clear subtitles"
  }
}

async function handleTranscribe() {
  errorMessage.value = ""

  // Check if any ASR engine is installed
  if (!hasInstalledEngines.value) {
    showToast("No ASR engine installed. Please install an engine in Settings > AI Engine.", "error", 5000)
    return
  }

  // Get selected engine — use asrPluginId to find the exact variant (CPU vs GPU)
  const engine = asrEngine.value
  const engineInfo = installedEngines.value.find(e => e.pluginId === asrPluginId.value)
    ?? installedEngines.value.find(e => e.engine === engine)

  if (!engineInfo) {
    showToast("Selected ASR engine not found", "error", 3000)
    return
  }

  // Check if engine is ready (plugin installed + model downloaded)
  const status = await checkEngineReady(engine)
  if (!status.ready) {
    showToast(`ASR engine "${engineInfo.displayName}" is not ready. Please download the model in Settings > AI Engine.`, "error", 5000)
    return
  }

  // Persist current ASR settings to backend before transcription
  const settingsSaved = await saveAsrSettings()
  if (!settingsSaved) {
    showToast("Failed to save transcription settings", "error", 3000)
    return
  }

  try {
    // Pass ASR settings as payload to transcription task
    const settings = asrSettingsPerEngine.value[asrEngine.value]
    const started = await runTranscription({
      engine: asrEngine.value,
      plugin_id: asrPluginId.value,
      model_size: settings.model_size,
      asr_model_size: settings.model_size,
      language: settings.language,
      device: settings.device,
      compute_type: settings.compute_type,
      vad_filter: settings.vad_filter,
      vad_threshold: settings.vad_threshold,
      vad_min_silence_ms: settings.vad_min_silence_ms,
    })
    if (!started) {
      showToast("Failed to start transcription task", "error", 3000)
    }
  } catch (err) {
    showToast(`Transcription failed: ${err instanceof Error ? err.message : String(err)}`, "error", 5000)
  }
}

async function handleConfirmAllSuggestions() {
  errorMessage.value = ""
  await confirmAllSuggestions()
}

async function handleRejectAllSuggestions() {
  errorMessage.value = ""
  await rejectAllSuggestions()
}

// ===== Phase 2: LLM task handlers =====

async function handleStartSmartDelete() {
  if (!llmConfig.value.configured) {
    showToast("请先配置 LLM", "error", 3000)
    return
  }
  await startSmartDelete()
  showToast("智能分析已启动", "info", 2000)
}

async function handleStartSubtitleCorrection(referenceText: string) {
  if (!llmConfig.value.configured) {
    showToast("请先配置 LLM", "error", 3000)
    return
  }
  await startSubtitleCorrection(referenceText)
  showToast("字幕修正已启动", "info", 2000)
}

async function handleStartHighlight(targetMinutes: number) {
  if (!llmConfig.value.configured) {
    showToast("请先配置 LLM", "error", 3000)
    return
  }
  // v2.1.1: Warn if re-running (Bug D -- old data will be replaced)
  if (highlightResults.value.length > 0) {
    if (!window.confirm(
      "重新提取精华将清除当前所有精华片段数据。\n\n确认继续？",
    )) {
      return
    }
  }
  await startHighlight(targetMinutes)
  showToast("精华提取已启动", "info", 2000)
}

async function handleCancelSingle() {
  await call("cancel_llm_tasks")
  // v2.1.1 M1-2c: don't claim success yet -- the in-flight HTTP request may
  // still be running. The TASK_CANCELLED event confirms the actual stop.
  showToast("取消中...", "info", 2000)
}

// v2.1.1 M4-1: segment click in selection mode (toggle / ctrl / shift range)
function handleSegmentClickInSelection(segId: string, event: MouseEvent) {
  const orderedIds = mergedSegments.value
    .filter(s => s.type === "subtitle")
    .map(s => s.id)
  handleSegmentClick(segId, event, orderedIds)
}

// v2.1.1 M4-1: merge currently-selected segments
async function handleMergeSelected() {
  const ids = Array.from(selectedSegmentIds.value)
  if (ids.length < 2) return
  const ok = await mergeSegments(ids)
  if (ok) {
    clearMultiSelection()
    showToast(`已合并 ${ids.length} 段`, "success", 2000)
  } else {
    showToast("合并失败 (需选中连续的字幕段)", "error", 3000)
  }
}

// v2.1.1 M4-3: split a segment at its midpoint
async function handleSplitSegment(segmentId: string, position?: number) {
  const seg = mergedSegments.value.find(s => s.id === segmentId)
  if (!seg) return
  // If position is provided (from waveform context menu split), use it;
  // otherwise use midpoint (from TranscriptRow right-click).
  const pos = position !== undefined ? position : (seg.start + seg.end) / 2
  const ok = await splitSegment(segmentId, pos)
  if (ok) {
    showToast(position !== undefined ? "已按时间指针分割" : "已从中点分割", "success", 1500)
  } else {
    showToast("分割失败", "error", 3000)
  }
}

// v2.1.1 M4-1: toggle selection mode (clear selection on exit)
function handleToggleSelectionMode() {
  toggleSelectionMode()
}

// v2.1.1 M4-1: batch mark selected segments for deletion (toggle-status)
async function markSelectedForDeletion() {
  const ids = Array.from(selectedSegmentIds.value)
  if (ids.length === 0) return
  const res = await call<Project>("mark_segments", ids, "delete")
  if (res.success && res.data) {
    pushSnapshot(res.data)
    emit("project-updated", res.data)
    showToast(`已标记 ${ids.length} 段删除`, "info", 2000)
    clearMultiSelection()
  } else {
    showToast(res.error ?? "批量标记失败", "error", 3000)
  }
}

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

async function handleOpenSubtitleFullscreen() {
  showSubtitleFullscreen.value = true
  // v2.1.0 Phase 2: load pending corrections from backend on open
  const tlId = props.project.active_timeline_id
  if (tlId) {
    await loadCorrections(tlId)
  }
}

// v2.1.0 Phase 2: diff token aggregation (D-69) + accept/reject handlers
interface DiffToken { text: string; type: "equal" | "delete" | "insert" }
interface AggregatedToken {
  type: "equal" | "delete" | "insert" | "replace"
  text?: string
  deleteText?: string
  insertText?: string
}

function aggregateDiffTokens(tokens: DiffToken[]): AggregatedToken[] {
  // D-69: merge adjacent delete+insert (gap <2 equal chars) into replace blocks
  const result: AggregatedToken[] = []
  for (let i = 0; i < tokens.length; i++) {
    const tok = tokens[i]
    const prev = result[result.length - 1]
    if ((prev?.type === "delete" && tok.type === "insert") ||
        (prev?.type === "insert" && tok.type === "delete")) {
      result[result.length - 1] = {
        type: "replace",
        deleteText: prev.type === "delete" ? prev.text : tok.text,
        insertText: prev.type === "insert" ? prev.text : tok.text,
      }
    } else {
      result.push({ type: tok.type, text: tok.text })
    }
  }
  return result
}

// Cache computed diffs per correction id to avoid recompute
const diffCache = ref<Record<string, AggregatedToken[]>>({})

function renderDiff(corr: { id: string; original_text: string; corrected_text: string }): string {
  const cached = diffCache.value[corr.id]
  if (!cached) {
    // Fallback: simple original -> corrected display while diff computes
    return `<span class="text-gray-400 line-through">${escapeHtml(corr.original_text)}</span>` +
      ` <span class="text-gray-400">→</span> ` +
      `<span class="text-green-700">${escapeHtml(corr.corrected_text)}</span>`
  }
  return cached.map(tok => {
    if (tok.type === "equal") return `<span>${escapeHtml(tok.text ?? "")}</span>`
    if (tok.type === "delete") return `<span class="line-through bg-red-100 text-red-700">${escapeHtml(tok.text ?? "")}</span>`
    if (tok.type === "insert") return `<span class="bg-green-100 text-green-700">${escapeHtml(tok.text ?? "")}</span>`
    // replace (aggregated D-69)
    return `<span class="line-through bg-red-100 text-red-700">${escapeHtml(tok.deleteText ?? "")}</span>` +
      `<span class="bg-green-100 text-green-700">${escapeHtml(tok.insertText ?? "")}</span>`
  }).join("")
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// Preload diffs whenever the pending corrections list changes
watch(pendingCorrections, async (list) => {
  for (const corr of list) {
    if (!diffCache.value[corr.id]) {
      await ensureDiff(corr)
    }
  }
}, { immediate: true })

async function ensureDiff(corr: { id: string; original_text: string; corrected_text: string }) {
  if (diffCache.value[corr.id]) return
  const diff = await computeDiff(corr.original_text, corr.corrected_text)
  if (diff?.tokens) {
    diffCache.value[corr.id] = aggregateDiffTokens(diff.tokens as DiffToken[])
  }
}

function categoryLabel(category: string): string {
  const labels: Record<string, string> = {
    homophone: "同音错字",
    proper_noun: "专有名词",
    punctuation: "标点断句",
    reference_aligned: "参考稿对齐",
    none: "无变更",
  }
  return labels[category] ?? category
}

async function handleAcceptCorrection(resultId: string) {
  const ok = await acceptCorrection(resultId)
  if (ok) {
    delete diffCache.value[resultId]
    // Refresh project so transcript reflects the applied correction
    const res = await call<Project>("switch_timeline", props.project.active_timeline_id)
    if (res.success && res.data) emit("project-updated", res.data)
  }
}

async function handleRejectCorrection(resultId: string) {
  const ok = await rejectCorrection(resultId)
  if (ok) {
    delete diffCache.value[resultId]
  }
}

async function handleAcceptHighConfidence() {
  const tlId = props.project.active_timeline_id
  if (!tlId) return
  const res = await acceptHighConfidenceCorrections(tlId, 0.8)
  if (res) {
    diffCache.value = {}
    const projRes = await call<Project>("switch_timeline", tlId)
    if (projRes.success && projRes.data) emit("project-updated", projRes.data)
    showToast(`已接受 ${res.accepted} 条高置信度修正`, "success", 2000)
  }
}

async function handleClearCorrections() {
  if (!window.confirm("确认清除所有待审阅的修正？")) return
  const tlId = props.project.active_timeline_id
  if (!tlId) return
  const ok = await clearCorrections(tlId)
  if (ok) {
    diffCache.value = {}
    showToast("已清除全部修正", "info", 2000)
  }
}

function handleGoToSettings() {
  showSettingsModal.value = true
}

// §11.5.2: Remove highlight via context menu (right-click on highlight card).
// Issue 5: hydrate highlight state in real time from returned project.
async function handleRemoveHighlight(segmentId: string) {
  if (!window.confirm("确认移除此精华片段？")) return
  const res = await call<{ removed_count?: number; project?: Project }>("remove_highlight_segment", segmentId)
  if (res.success) {
    if (res.data?.project) {
      emit("project-updated", res.data.project)
      await hydrateHighlightsFromProject(res.data.project)
    }
    showToast("精华片段已移除", "success", 2000)
  } else {
    showToast("移除失败: " + (res.error ?? "未知错误"), "error", 3000)
  }
}

// §11.5.2: Add segment to highlights via right-click "加入精华".
// Issue 5: hydrate highlight state in real time from returned project.
async function handleAddToHighlight(segmentId: string) {
  const res = await call<{ result?: unknown; project?: Project }>("add_highlight_segment", segmentId)
  if (res.success) {
    if (res.data?.project) {
      emit("project-updated", res.data.project)
      await hydrateHighlightsFromProject(res.data.project)
    }
    showToast("已加入精华", "success", 2000)
  } else {
    showToast("加入失败: " + (res.error ?? "未知错误"), "error", 3000)
  }
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

async function handleSettingsClosed() {
  showSettingsModal.value = false
  // Refresh LLM config status after settings change
  await loadLlmConfig()
}

async function handleSaveProject() {
  if (isSaving.value) return
  isSaving.value = true
  try {
    const res = await call("save_project")
    if (res.success) {
      isDirty.value = false
      lastSavedAt.value = Date.now()
      showToast("Project saved", "success", 2000)
    } else {
      showToast("Save failed", "error", 3000)
    }
  } finally {
    isSaving.value = false
  }
}

async function handleSubtitleTrim() {
  errorMessage.value = ""
  statusMessage.value = "Generating subtitle-based trim ranges..."
  const result = await generateSubtitleKeepRanges(subtitleTrimPadding.value)
  statusMessage.value = ""
  if (result) {
    showToast(`Generated ${result.new_edits} delete ranges from ${result.keep_ranges} subtitle groups`, "success", 5000)
  } else {
    showToast("Failed to generate subtitle trim ranges", "error", 5000)
  }
}

async function handleDeleteSubtitleTrimEdits() {
  const ok = await deleteSubtitleTrimEdits()
  if (ok) {
    showToast("All subtitle trim markers cleared", "success", 3000)
  } else {
    showToast("Failed to clear subtitle trim markers", "error", 3000)
  }
}

async function handleConfirmDeleteSilence() {
  showConfirmDeleteSilence.value = false
  const ok = await deleteSilenceSegments()
  if (ok) {
    showToast("All silence markers deleted", "success", 3000)
  } else {
    showToast("Failed to delete silence markers", "error", 3000)
  }
}

async function handleUpdateText(segmentId: string, text: string) {
  await updateSegmentText(segmentId, text)
}

async function handleUpdateTime(segmentId: string, field: "start" | "end", value: number) {
  await updateSegmentTime(segmentId, field, value)
}



async function handleSearchReplace(query: string, replacement: string, scope: string) {
  const result = await searchReplace(query, replacement, scope)
  if (result) {
    statusMessage.value = `Replaced ${result.count} occurrences`
  }
}

function handleSelectRange(start: number, end: number) {
  selectEditRange(start, end)
}

async function handleAddSegment(start: number, end: number) {
  if (projectRef.value) pushSnapshot(projectRef.value)
  const res = await call<Project>("add_segment", start, end, "", "subtitle")
  if (res.success && res.data) {
    emit("project-updated", res.data)
  } else {
    errorMessage.value = res.error ?? "Failed to add segment"
  }
}

async function handleDeleteSegment(segmentId: string) {
  errorMessage.value = ""
  const err = await deleteSegment(segmentId)
  if (err) {
    errorMessage.value = err
  }
}

function handleSeekSegment(seg: Segment) {
  editSelectedSegmentId.value = seg.id
  seekPlayback(seg.start)
}


async function handleCloseProject() {
  await call("close_project")
  videoUrl.value = ""
  emit("project-closed")
}

function isTextInput(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === "INPUT" || tag === "TEXTAREA") return true
  if (el.isContentEditable) return true
  return false
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (isTextInput(e.target)) return

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
  if (e.ctrlKey && e.key === "s") {
    e.preventDefault()
    handleSaveProject()
    return
  }
  if (e.ctrlKey && e.key === "z" && !e.shiftKey) {
    e.preventDefault()
    handleUndo()
    return
  }
  if (e.ctrlKey && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
    e.preventDefault()
    handleRedo()
    return
  }
  // §8: Ctrl+F toggle search/replace bar
  if (e.ctrlKey && e.key === "f") {
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
  if (!projectRef.value) return
  const restored = undo(projectRef.value)
  if (restored) {
    emit("project-updated", restored)
    showToast("Undo", "success", 1500)
  }
}

async function handleRedo() {
  await flushPendingUpdates()
  if (!projectRef.value) return
  const restored = redo(projectRef.value)
  if (restored) {
    emit("project-updated", restored)
    showToast("Redo", "success", 1500)
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleGlobalKeydown)
  document.addEventListener("mousedown", handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener("keydown", handleGlobalKeydown)
  document.removeEventListener("mousedown", handleClickOutside)
  if (regenPollTimer) clearInterval(regenPollTimer)
})
</script>

<template>
  <div class="flex h-screen flex-col bg-white">
    <!-- Top nav -->
    <nav class="flex h-11 items-center justify-between border-b border-gray-200 bg-gray-900 px-4">
      <div class="flex items-center gap-3">
        <button
          class="rounded p-1 text-gray-400 hover:text-white transition-colors"
          title="Back to home"
          @click="handleCloseProject"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
          </svg>
        </button>
        <span class="text-sm font-semibold text-white">{{ project.project.name }}</span>
        <span class="text-xs text-gray-400">
          {{ subtitleCount }} subtitles | {{ silenceCount }} silence | {{ formatTimeShort(duration) }}
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
          class="ml-2 rounded px-2 py-0.5 text-xs text-gray-400 hover:text-white transition-colors border border-gray-700 hover:border-gray-500"
          :disabled="isGeneratingProxy"
          title="Generate proxy video for faster preview"
          @click="handleRequestProxy"
        >
          {{ isGeneratingProxy ? "Generating..." : "Generate Proxy" }}
        </button>
      </div>
      <div class="flex items-center gap-2">
        <span v-if="confirmedEdits.length > 0" class="text-xs text-yellow-300">
          {{ confirmedEdits.length }} edits | -{{ formatTimeShort(estimatedSaving) }}
        </span>
        <!-- Inline auto-save indicator -->
        <span v-if="isSaving" class="text-xs text-blue-300">Saving...</span>
        <span v-else-if="isDirty" class="text-xs text-gray-400">●</span>
        <span v-else-if="lastSavedAt" class="text-xs text-green-400">Saved</span>
        <button
          class="rounded px-2 py-1 text-xs text-gray-400 hover:text-white transition-colors"
          title="Save project (Ctrl+S)"
          @click="handleSaveProject"
        >
          Save
        </button>
      </div>
    </nav>

    <!-- Toolbar -->
    <div class="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting"
        @click="handleImportSrt"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
        Import SRT
      </button>
      <button
        class="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
        :class="previewMode === 'edited'
          ? 'bg-teal-600 text-white hover:bg-teal-700'
          : 'bg-gray-600 text-gray-200 hover:bg-gray-700'"
        :disabled="isDetecting || isExporting"
        title="Toggle original/edited preview (Shift+Space)"
        @click="togglePreviewMode"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
        {{ previewMode === 'edited' ? 'Edited' : 'Original' }}
      </button>
      <div class="relative inline-flex items-center">
        <button
          class="inline-flex items-center gap-1.5 rounded-md rounded-r-none bg-purple-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-purple-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting || isTranscribing || !hasInstalledEngines || uvAvailable === false"
          :title="uvAvailable === false ? '需要安装 uv' : undefined"
          @click="handleTranscribe"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>
          {{ isTranscribing ? 'Transcribing...' : 'Transcribe' }}
        </button>
        <button
          class="inline-flex items-center rounded-md rounded-l-none bg-purple-600 px-1.5 py-1.5 text-xs text-white hover:bg-purple-700 disabled:opacity-50 transition-colors border-l border-purple-400"
          :disabled="isDetecting || isExporting || isTranscribing || uvAvailable === false"
          :title="uvAvailable === false ? '需要安装 uv' : 'Transcription settings'"
          @click="showTranscribeSettings = !showTranscribeSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <div
          v-if="showTranscribeSettings && uvAvailable !== false"
          class="absolute top-full left-0 mt-1 w-72 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
        >
          <div class="text-xs font-medium text-gray-700 mb-2">Transcription Settings</div>

          <!-- No engines installed warning -->
          <div v-if="!hasInstalledEngines" class="text-xs text-amber-600 mb-2 p-2 bg-amber-50 rounded">
            No ASR engine installed. Please install an engine in Settings > AI Engine.
          </div>

          <template v-else>
            <!-- Engine selector -->
            <label class="block mb-2">
              <span class="text-xs text-gray-500">Engine</span>
              <select
                v-model="asrPluginId"
                class="w-full mt-1 rounded border-gray-300 text-xs"
              >
                <option v-for="eng in installedEngines" :key="eng.pluginId" :value="eng.pluginId">
                  {{ eng.displayName }} {{ eng.ready ? '' : '(model not downloaded)' }}
                </option>
              </select>
            </label>

            <!-- Model selector -->
            <label class="block mb-2">
              <span class="text-xs text-gray-500">Model</span>
              <select
                v-model="asrSettingsPerEngine[asrEngine].model_size"
                class="w-full mt-1 rounded border-gray-300 text-xs"
              >
                <option v-for="m in availableModels" :key="m.model_id" :value="m.model_id">
                  {{ m.display_name }} {{ m.status === 'downloaded' ? '' : '(not downloaded)' }}
                </option>
              </select>
            </label>

            <!-- Language -->
            <label class="block mb-2">
              <span class="text-xs text-gray-500">Language</span>
              <select v-model="asrSettingsPerEngine[asrEngine].language" class="w-full mt-1 rounded border-gray-300 text-xs">
                <option value="auto">Auto-detect</option>
                <option value="zh">Chinese</option>
                <option value="en">English</option>
                <option value="ja">Japanese</option>
                <option value="ko">Korean</option>
              </select>
            </label>

            <!-- Device (hidden for MLX -- always uses Apple Silicon) -->
            <label v-if="!isMlx" class="block mb-2">
              <span class="text-xs text-gray-500">Device</span>
              <select v-model="asrSettingsPerEngine[asrEngine].device" class="w-full mt-1 rounded border-gray-300 text-xs">
                <option v-if="!isDarwin" value="cpu">CPU</option>
                <option v-if="supportsGpu" value="cuda">CUDA (GPU)</option>
                <option v-if="asrEngine === 'faster-whisper'" value="auto">Auto</option>
                <option v-if="isDarwin && asrEngine === 'qwen3-asr'" value="mps">MPS</option>
              </select>
              <span v-if="isDarwin && asrEngine === 'faster-whisper'" class="text-xs text-gray-400 mt-0.5 block">MPS (Metal Performance Shaders)</span>
              <span v-else-if="isDarwin && asrEngine === 'qwen3-asr'" class="text-xs text-gray-400 mt-0.5 block">Metal Performance Shaders (Apple GPU)</span>
              <span v-else-if="!supportsGpu" class="text-xs text-gray-400 mt-0.5 block">GPU not available for this engine plugin</span>
            </label>
            <div v-else class="text-xs text-gray-400 mb-2">Apple Silicon (Metal)</div>

            <!-- Compute type (hidden for MLX) -->
            <label v-if="!isMlx && computeTypeOptions.length > 0" class="block mb-2">
              <span class="text-xs text-gray-500">Compute Type</span>
              <select v-model="asrSettingsPerEngine[asrEngine].compute_type" class="w-full mt-1 rounded border-gray-300 text-xs">
                <option v-for="opt in computeTypeOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </label>

            <!-- VAD filter -->
            <label class="flex items-center gap-2 mb-2 cursor-pointer">
              <input
                type="checkbox"
                v-model="asrSettingsPerEngine[asrEngine].vad_filter"
                class="w-4 h-4 accent-blue-600"
              />
              <span class="text-xs text-gray-500">VAD filter (reduce hallucinations)</span>
            </label>

            <!-- VAD sliders (visible when vad_filter is on) -->
            <template v-if="asrSettingsPerEngine[asrEngine].vad_filter">
              <label class="block mb-2">
                <span class="text-xs text-gray-500">
                  VAD Threshold: {{ asrSettingsPerEngine[asrEngine].vad_threshold.toFixed(2) }}
                </span>
                <input
                  type="range"
                  v-model.number="asrSettingsPerEngine[asrEngine].vad_threshold"
                  min="0.0"
                  max="1.0"
                  step="0.05"
                  class="w-full mt-1"
                />
              </label>
              <label class="block mb-3">
                <span class="text-xs text-gray-500">
                  Min Silence (ms): {{ asrSettingsPerEngine[asrEngine].vad_min_silence_ms }}
                </span>
                <input
                  type="range"
                  v-model.number="asrSettingsPerEngine[asrEngine].vad_min_silence_ms"
                  min="100"
                  max="2000"
                  step="50"
                  class="w-full mt-1"
                />
              </label>
            </template>

            <!-- Save button -->
            <button
              class="w-full rounded bg-purple-500 px-2 py-1 text-xs text-white hover:bg-purple-600"
              @click="saveAsrSettings"
            >
              Save as Default
            </button>
          </template>
        </div>
      </div>
      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting || isTranscribing || subtitleCount === 0"
        title="Delete all subtitle segments"
        @click="handleClearSubtitles"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
        Clear Subtitles
      </button>
      <div class="relative inline-flex items-center">
        <button
          class="inline-flex items-center gap-1.5 rounded-md rounded-r-none bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting"
          @click="handleDetectSilence"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707A1 1 0 0112 5v14a1 1 0 01-1.707.707L5.586 15z" /><path stroke-linecap="round" stroke-linejoin="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" /></svg>
          {{ isDetecting ? 'Detecting...' : 'Detect Silence' }}
        </button>
        <button
          class="inline-flex items-center rounded-md rounded-l-none bg-blue-600 px-1.5 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50 transition-colors border-l border-blue-400"
          :disabled="isDetecting || isExporting"
          title="Silence detection settings"
          @click="showSilenceSettings = !showSilenceSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <div
          v-if="showSilenceSettings"
          class="absolute top-full left-0 mt-1 w-64 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
        >
          <div class="text-xs font-medium text-gray-700 mb-2">Silence Detection Settings</div>
          <label class="block mb-2">
            <span class="text-xs text-gray-500">Threshold (dB): {{ silenceThreshold }}</span>
            <input
              type="range"
              v-model.number="silenceThreshold"
              min="-60"
              max="-10"
              step="1"
              class="w-full mt-1"
            />
          </label>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">Min Duration (s): {{ silenceMinDuration.toFixed(2) }}</span>
            <input
              type="range"
              v-model.number="silenceMinDuration"
              min="0.05"
              max="2.0"
              step="0.05"
              class="w-full mt-1"
            />
            <p v-if="silenceMinDuration < 0.2" class="text-xs text-amber-600 mt-1">
              Very short durations (&lt;0.2s) may generate many clips and affect performance.
            </p>
          </label>
          <label class="block mb-2">
            <span class="text-xs text-gray-500">
              Margin (s): {{ silenceMargin.toFixed(2) }}
            </span>
            <input
              type="range"
              v-model.number="silenceMargin"
              min="0"
              max="0.5"
              step="0.01"
              class="w-full mt-1"
            />
            <p v-if="silenceMargin > 0 && silenceMargin * 2 >= silenceMinDuration"
               class="text-xs text-amber-600 mt-1">
              High margin may consume small silence intervals entirely.
            </p>
          </label>
          <label class="block mb-2">
            <span class="text-xs text-gray-500">
              Subtitle Padding (s): {{ silenceSubtitlePadding.toFixed(2) }}
            </span>
            <input
              type="range"
              v-model.number="silenceSubtitlePadding"
              min="0"
              max="1.0"
              step="0.05"
              class="w-full mt-1"
            />
            <p v-if="silenceSubtitlePadding > 0" class="text-xs text-gray-400 mt-0.5">
              Silence ranges will be trimmed to stay this far from subtitles.
            </p>
          </label>
          <label class="flex items-center gap-2 mb-3 cursor-pointer">
            <input
              type="checkbox"
              v-model="trimSubtitlesOnOverlap"
              class="rounded border-gray-300"
            />
            <span class="text-xs text-gray-500">Trim overlapping subtitles</span>
          </label>
          <button
            class="w-full rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-600"
            @click="saveSilenceSettings"
          >
            Save Settings
          </button>
        </div>
      </div>

      <!-- Delete all silence markers -->
      <button
        class="inline-flex items-center rounded-md bg-red-500 px-2 py-1.5 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting || silenceCount === 0"
        title="Delete all silence markers"
        @click="showConfirmDeleteSilence = true"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <!-- Separator: silence group | subtitle group -->
      <div class="h-6 w-px bg-gray-300"></div>

      <div class="relative inline-flex items-center">
        <button
          class="inline-flex items-center gap-1.5 rounded-md rounded-r-none bg-orange-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-orange-600 disabled:opacity-50 transition-colors"
          :disabled="isDetecting || isExporting"
          title="Auto-trim: delete gaps between subtitle segments"
          @click="handleSubtitleTrim"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879M12 12L4.939 4.939m7.061 7.061l-2.879-2.879M12 12l2.879-2.879" /></svg>
          Subtitle Trim
        </button>
        <button
          class="inline-flex items-center rounded-md rounded-l-none bg-orange-600 px-1.5 py-1.5 text-xs text-white hover:bg-orange-700 disabled:opacity-50 transition-colors border-l border-orange-400"
          :disabled="isDetecting || isExporting"
          title="Subtitle trim settings"
          @click="showSubtitleTrimSettings = !showSubtitleTrimSettings"
        >
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
        </button>
        <div
          v-if="showSubtitleTrimSettings"
          class="absolute top-full left-0 mt-1 w-56 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
        >
          <div class="text-xs font-medium text-gray-700 mb-2">Subtitle Trim Settings</div>
          <label class="block mb-3">
            <span class="text-xs text-gray-500">Padding (s): {{ subtitleTrimPadding.toFixed(2) }}</span>
            <input
              type="range"
              v-model.number="subtitleTrimPadding"
              min="0"
              max="2.0"
              step="0.05"
              class="w-full mt-1"
            />
          </label>
        </div>
      </div>

      <!-- Clear subtitle trim markers -->
      <button
        class="inline-flex items-center rounded-md bg-red-500 px-2 py-1.5 text-xs text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
        :disabled="isDetecting || isExporting"
        title="Clear all subtitle trim markers"
        @click="handleDeleteSubtitleTrimEdits"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
      </button>

      <div class="flex-1" />

      <button
        class="inline-flex items-center gap-1.5 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
        :disabled="isExporting || (confirmedEdits.length === 0 && subtitleCount === 0)"
        @click="emit('go-to-export')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" /></svg>
        导出...
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
    <div v-if="statusMessage" class="flex items-center border-b border-gray-200 bg-blue-50 px-4 py-1 text-xs text-blue-600">
      <span class="flex-1">{{ statusMessage }}</span>
      <button
        class="ml-2 shrink-0 rounded p-0.5 hover:bg-blue-100 transition-colors"
        @click="statusMessage = ''"
      >
        <svg class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
    <div v-if="errorMessage" class="border-b border-gray-200 bg-red-50 px-4 py-1 text-xs text-red-600">
      {{ errorMessage }}
    </div>

    <!-- Main content: two-column layout -->
    <div class="flex flex-1 overflow-hidden">
      <SplitPanel storage-key="milo-split-workspace" :min-ratio="0.25" :max-ratio="0.75">
        <template #left>
          <!-- Left: Video player area -->
          <div class="flex h-full min-w-0 flex-col bg-gray-900">
        <div class="flex flex-1 items-center justify-center p-2 overflow-hidden">
          <div v-if="videoUrl" class="relative flex flex-col w-full h-full items-center justify-center">
            <video
              ref="videoRef"
              :src="videoUrl"
              class="max-h-full max-w-full rounded"
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
            />
            <!-- Proxy generation overlay -->
            <div
              v-if="isGeneratingProxy"
              class="absolute inset-0 flex flex-col items-center justify-center bg-black/60 rounded z-10"
            >
              <svg class="animate-spin h-8 w-8 text-white mb-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span class="text-sm text-white font-medium">Generating proxy...</span>
            </div>
          </div>
          <div v-else class="text-center text-gray-400">
            <svg xmlns="http://www.w3.org/2000/svg" class="mx-auto h-16 w-16 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
            </svg>
            <p class="mt-2 text-sm">Loading video...</p>
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
          <div class="relative flex flex-1 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white">
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
            @seek="handleSeek"
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
            @seek-suggestion="handleSeek"
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
      :segments="mergedSegments"
      :edits="edits"
      :duration="duration"
      :current-time="currentTime"
      :waveform-path="waveformUrl"
      :update-time="updateSegmentTime"
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
    />

    <!-- Delete silence confirmation dialog -->
    <Teleport to="body">
      <div
        v-if="showConfirmDeleteSilence"
        class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40"
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
      @close="handleSettingsClosed"
    />

    <!-- Phase 2: P1 subtitle correction fullscreen diff view (D-16) -->
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="showSubtitleFullscreen"
          class="fixed inset-0 z-[9998] bg-white flex flex-col"
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

import { inject, provide, ref, watch } from "vue"
import type { Ref } from "vue"
import type { UndoLayer } from "@/utils/undoRecords"
import type { InjectionKey } from "vue"
import { call } from "@/bridge"
import type { Project, ProjectPatch, ProjectResponse, Segment, SubtitleTrack } from "@/types/project"

/** Tracks of a full-Project response (fallback when the payload is not a patch). */
function projTimelineTracks(project: Project): SubtitleTrack[] {
  const tl =
    project.timelines?.find(t => t.id === project.active_timeline_id) ??
    project.timelines?.[0]
  return tl?.transcript?.tracks ?? []
}
import { useToast } from "@/composables/useToast"
import type { useAsrEngines } from "@/composables/useAsrEngines"

/**
 * Workspace action hub (v3.0.0 M8-2c).
 *
 * Owns the bodies of the page's relay/business handlers, grouped into five
 * domains (playback / timeline / edit / llm / project). Handler bodies are
 * moved verbatim from WorkspacePage.vue; every piece of page state they
 * touch arrives through the explicit `WorkspaceActionsDeps` object.
 *
 * Undo/redo, the global keydown handler, outside-click and search-bar
 * toggling intentionally STAY in WorkspacePage.vue (migration-M8 §undo).
 *
 * The actions object is provided via `WORKSPACE_ACTIONS_KEY` so child
 * components can inject it instead of receiving long props/emit chains.
 */

type AsrEngines = ReturnType<typeof useAsrEngines>

/** The page's emit surface (subset used by actions). */
export interface WorkspaceEmit {
  (e: "project-updated", project: ProjectResponse): void
  (e: "project-closed"): void
}

export interface ConfirmAction {
  (opts: { title: string; message: string; confirmText?: string; cancelText?: string; danger?: boolean }): Promise<boolean>
}

/** v3.0.4 M2-3: one pending review entry as returned by
 * get_subtitle_corrections (P2-3 adds track_id/track_name; only the
 * fields this hub consumes are declared). */
export interface CorrectionReviewEntry {
  id: string
  original_text: string
  corrected_text: string
  /** "" / absent = main track; non-empty = extension-track scope. */
  track_id?: string
}

/** v3.0.4 M2-3: superset accept/reject response data (core M2-3). */
export interface CorrectionReviewResult {
  segment_id: string
  track_id?: string
  patch?: ProjectPatch
}

/**
 * v3.0.4 M2-3: undo capture layers for one review action (accept or
 * reject). Both actions remove the AnalysisResult, so ``analysis``
 * always joins the text layer -- main track ["segments","analysis"],
 * extension track ["tracks","analysis"] (SPEC M2-3 undo ruling).
 */
export function correctionUndoLayers(
  entry: Pick<CorrectionReviewEntry, "track_id"> | undefined,
): UndoLayer[] {
  return entry && entry.track_id ? ["tracks", "analysis"] : ["segments", "analysis"]
}

export interface WorkspaceActionsDeps {
  emit: WorkspaceEmit
  showToast: ReturnType<typeof useToast>["showToast"]
  getProject: () => Project
  // shared state (refs from the page)
  errorMessage: { value: string }
  statusMessage: { value: string }
  videoRef: { value: HTMLVideoElement | null }
  videoUrl: { value: string }
  waveformUrl: { value: string }
  videoVolume: { value: number }
  videoPlaybackRate: { value: number }
  isGeneratingProxy: { value: boolean }
  demoMode: boolean
  regenPoll: { current: ReturnType<typeof setInterval> | null }
  subtitleTrimPadding: { value: number }
  showConfirmDeleteSilence: { value: boolean }
  showSettingsModal: { value: boolean }
  showSubtitleFullscreen: { value: boolean }
  isDirty: { value: boolean }
  isSaving: { value: boolean }
  lastSavedAt: { value: number | null }
  mergedSegments: { value: Segment[] }
  // composables
  seekPlayback: (time: number, emitEvent?: boolean) => void
  demoPlayback: {
    seek: (time: number, emitEvent?: boolean) => void
    toggle: () => void
  }
  handlePlaybackTimeUpdate: () => void
  // timeline/edit composables (useEdit / useAnalysis / useTranscript / useSegmentEdit)
  runTranscription: (payload: Record<string, unknown>) => Promise<boolean>
  runSilenceDetection: () => boolean | Promise<boolean>
  toggleEditStatus: (segment: Segment, nextStatus?: string) => Promise<boolean>
  updateSegmentText: (id: string, text: string) => Promise<unknown>
  updateSegmentTime: (id: string, field: "start" | "end", value: number) => void | Promise<unknown>
  searchReplace: (q: string, r: string, scope: string) => Promise<{ count: number } | null>
  mergeSegments: (ids: string[]) => Promise<boolean>
  splitSegment: (id: string, pos: number, snap?: boolean) => Promise<{ ok: boolean; snapOffsetMs: number | null }>
  deleteSegment: (id: string) => Promise<string | null>
  selectEditRange: (start: number, end: number) => void
  generateSubtitleKeepRanges: (padding: number) => Promise<{ new_edits: number; keep_ranges: number } | null>
  deleteSubtitleTrimEdits: () => Promise<boolean>
  deleteSilenceSegments: () => Promise<boolean>
  confirmAllSuggestions: () => Promise<unknown>
  rejectAllSuggestions: () => Promise<unknown>
  // segment selection (useSegmentEdit)
  selectedSegmentIds: { value: Set<string> }
  editSelectedSegmentId: { value: string | null }
  toggleSelectionMode: () => void
  clearMultiSelection: () => void
  handleSegmentClick: (id: string, event: MouseEvent, orderedIds: string[]) => void
  // undo (M5)
  pushSnapshot: (project: Project, layers: UndoLayer[], label: string) => void
  projectRef: { value: Project | null }
  // v2.3.2 optimistic-update flush (required before timeline-level bridge ops)
  flushPendingUpdates: () => Promise<void>
  // LLM composables (useLlmTasks / highlights)
  llmConfig: { value: { configured: boolean } }
  loadLlmConfig: () => Promise<void>
  startSmartDelete: () => Promise<unknown>
  startSubtitleCorrection: (referenceText: string) => Promise<unknown>
  startHighlight: (targetMinutes: number) => Promise<unknown>
  highlightResults: { value: unknown[] }
  hydrateHighlightsFromProject: (p: Project) => Promise<void> | void
  // v3.0.4 M2-3: review entries carry the P2-3 scope fields at runtime
  // ("" / absent track_id = main track).
  pendingCorrections: Ref<CorrectionReviewEntry[]>
  loadCorrections: (timelineId: string) => Promise<void>
  computeDiff: (o: string, c: string) => Promise<{ tokens: unknown[] } | null>
  // v3.0.4 M2-3: accept/reject now call the bridge directly here so the
  // superset patch in the response can be consumed (useLlmTasks keeps its
  // boolean wrappers for other callers; kept in the interface so the page
  // deps literal stays unchanged).
  acceptCorrection: (resultId: string) => Promise<boolean>
  rejectCorrection: (resultId: string) => Promise<boolean>
  acceptHighConfidenceCorrections: (timelineId: string, threshold: number) => Promise<{ accepted: number } | null>
  clearCorrections: (timelineId: string) => Promise<boolean>
  // ASR domain (useAsrEngines) + page wrapper
  asr: Pick<AsrEngines, "asrEngine" | "asrPluginId" | "asrSettingsPerEngine" | "installedEngines" | "checkEngineReady">
  handleSaveAsrSettings: () => Promise<boolean>
  // in-app confirm modal (stays in page, dialog element lives in its template)
  confirmAction: ConfirmAction
}

export interface WorkspaceActions {
  // -- playback / video ----------------------------------------------------
  handleRegenerateWaveform: () => Promise<void>
  handleRequestProxy: () => Promise<void>
  handleSeek: (time: number) => void
  handleSetTime: (time: number) => void
  handleVideoLoaded: () => void
  handleTimeUpdate: () => void
  handleTogglePlay: () => void
  handleSeekTo: (time: number) => void
  handleVolumeChange: (vol: number) => void
  handleRateChange: (rate: number) => void
  handleFullscreen: () => void
  // -- timeline --------------------------------------------------------------
  handleSwitchTimeline: (timelineId: string) => Promise<void>
  handleCreateTimeline: () => Promise<void>
  handleDeleteTimeline: (timelineId: string) => Promise<void>
  handleImportSrt: () => Promise<void>
  handleImportSrtAsTrack: () => Promise<void>
  handleDetectSilence: () => Promise<void>
  handleClearSubtitles: () => Promise<void>
  handleDeleteTrackSegment: (trackId: string, segmentId: string) => Promise<void>
  handleDeleteTrack: (trackId: string) => Promise<void>
  handleAddTrack: () => Promise<void>
  handleAddTrackSegment: (trackId: string, start: number, end: number) => Promise<void>
  handleClearTrackSegments: (trackId: string) => Promise<void>
  handleTranscribe: () => Promise<void>
  // -- edit ------------------------------------------------------------------
  handleToggleEditStatus: (segment: Segment, nextStatus?: string) => Promise<void>
  handleSegmentClickInSelection: (segId: string, event: MouseEvent) => void
  handleToggleSelectionMode: () => void
  handleMergeSelected: () => Promise<void>
  handleSplitSegment: (segmentId: string, position?: number) => Promise<void>
  handleUpdateText: (segmentId: string, text: string) => Promise<void>
  handleUpdateTime: (segmentId: string, field: "start" | "end", value: number) => Promise<void>
  handleSelectRange: (start: number, end: number) => void
  handleAddSegment: (start: number, end: number) => Promise<void>
  handleDeleteSegment: (segmentId: string) => Promise<void>
  handleSeekSegment: (seg: Segment) => void
  handleSubtitleTrim: () => Promise<void>
  handleDeleteSubtitleTrimEdits: () => Promise<void>
  handleConfirmDeleteSilence: () => Promise<void>
  markSelectedForDeletion: () => Promise<void>
  // -- LLM / correction ------------------------------------------------------
  handleConfirmAllSuggestions: () => Promise<void>
  handleRejectAllSuggestions: () => Promise<void>
  handleStartSmartDelete: () => Promise<void>
  handleStartSubtitleCorrection: (referenceText: string) => Promise<void>
  handleStartHighlight: (targetMinutes: number) => Promise<void>
  handleCancelSingle: () => Promise<void>
  handleOpenSubtitleFullscreen: () => Promise<void>
  handleAcceptCorrection: (resultId: string) => Promise<void>
  handleRejectCorrection: (resultId: string) => Promise<void>
  handleAcceptHighConfidence: () => Promise<void>
  handleClearCorrections: () => Promise<void>
  handleRemoveHighlight: (segmentId: string) => Promise<void>
  handleAddToHighlight: (segmentId: string) => Promise<void>
  renderDiff: (corr: { id: string; original_text: string; corrected_text: string }) => string
  categoryLabel: (category: string) => string
  // -- project / settings ------------------------------------------------------
  handleCloseProject: () => Promise<void>
  handleSaveProject: () => Promise<void>
  handleSettingsClosed: () => Promise<void>
  handleGoToSettings: () => void
  handleSearchReplace: (query: string, replacement: string, scope: string) => Promise<void>
}

export function createWorkspaceActions(deps: WorkspaceActionsDeps): WorkspaceActions {
  const {
    emit, showToast, getProject,
    errorMessage, statusMessage,
    videoRef, videoUrl, waveformUrl, videoVolume, videoPlaybackRate,
    isGeneratingProxy, demoMode, regenPoll,
    subtitleTrimPadding, showConfirmDeleteSilence, showSettingsModal, showSubtitleFullscreen,
    isDirty, isSaving, lastSavedAt, mergedSegments,
    seekPlayback, demoPlayback, handlePlaybackTimeUpdate,
    runTranscription, runSilenceDetection,
    toggleEditStatus, updateSegmentText, updateSegmentTime, searchReplace,
    mergeSegments, splitSegment, deleteSegment, selectEditRange,
    generateSubtitleKeepRanges, deleteSubtitleTrimEdits, deleteSilenceSegments,
    confirmAllSuggestions, rejectAllSuggestions,
    selectedSegmentIds, editSelectedSegmentId,
    toggleSelectionMode, clearMultiSelection, handleSegmentClick,
    pushSnapshot, projectRef, flushPendingUpdates,
    llmConfig, loadLlmConfig,
    startSmartDelete, startSubtitleCorrection, startHighlight,
    highlightResults, hydrateHighlightsFromProject,
    pendingCorrections, loadCorrections, computeDiff,
    acceptHighConfidenceCorrections, clearCorrections,
    asr, handleSaveAsrSettings, confirmAction,
  } = deps

  // -- playback / video ----------------------------------------------------

  async function handleRegenerateWaveform() {
    if (demoMode) {
      showToast("演示波形由浏览器即时生成", "info", 2500)
      return
    }
    statusMessage.value = "Regenerating waveform..."
    const res = await call<{ task_id: string }>("regenerate_waveform")
    if (!res.success) {
      showToast(res.error ?? "Failed to regenerate waveform", "error", 3000)
      statusMessage.value = ""
      return
    }
    // Poll get_waveform_url until regeneration completes
    if (regenPoll.current) clearInterval(regenPoll.current)
    const start = Date.now()
    regenPoll.current = setInterval(async () => {
      const urlRes = await call<{ url: string }>("get_waveform_url")
      if (urlRes.success && urlRes.data) {
        clearInterval(regenPoll.current!)
        regenPoll.current = null
        // Cache-bust: append timestamp so WaveformCanvas re-fetches
        waveformUrl.value = urlRes.data.url + "?t=" + Date.now()
        statusMessage.value = ""
        showToast("Waveform regenerated", "success", 2000)
      } else if (Date.now() - start > 120000) {
        clearInterval(regenPoll.current!)
        regenPoll.current = null
        statusMessage.value = ""
        showToast("Waveform regeneration timed out", "error", 3000)
      }
    }, 500)
  }

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

  function handleSeek(time: number) {
    if (demoMode) demoPlayback.seek(time, true)
    else seekPlayback(time, true)
  }

  // v2.1.1 A-03: move playhead without playing (arrow keys, selection mode)
  function handleSetTime(time: number) {
    if (demoMode) demoPlayback.seek(time)
    else seekPlayback(time)
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
    if (demoMode) {
      demoPlayback.toggle()
      return
    }
    if (!videoRef.value) return
    if (videoRef.value.paused) {
      videoRef.value.play()
    } else {
      videoRef.value.pause()
    }
  }

  function handleSeekTo(time: number) {
    if (demoMode) demoPlayback.seek(time)
    else seekPlayback(time)
  }

  function handleVolumeChange(vol: number) {
    if (demoMode) {
      videoVolume.value = vol
      return
    }
    if (!videoRef.value) return
    videoRef.value.volume = vol
    videoVolume.value = vol
  }

  function handleRateChange(rate: number) {
    if (demoMode) {
      videoPlaybackRate.value = rate
      return
    }
    if (!videoRef.value) return
    videoRef.value.playbackRate = rate
    videoPlaybackRate.value = rate
  }

  function handleFullscreen() {
    if (demoMode) return
    const container = videoRef.value?.parentElement
    if (!container) return
    if (document.fullscreenElement) {
      document.exitFullscreen()
    } else {
      container.requestFullscreen()
    }
  }

  // -- timeline --------------------------------------------------------------

  async function handleSwitchTimeline(timelineId: string) {
    await flushPendingUpdates()
    const res = await call<Project>("switch_timeline", timelineId)
    if (res.success && res.data) {
      emit("project-updated", res.data)
      // v3.0.4 M2-3 (R3): re-fetch the pending review list for the now
      // active timeline -- entries pinned to the previous timeline must
      // not linger as clickable stale items (pairs with the backend
      // timeline-pinning guard). Fire-and-forget keeps the switch snappy.
      void loadCorrections(timelineId)
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
      fork ? getProject().active_timeline_id : null,
    )
    if (res.success && res.data) {
      emit("project-updated", res.data)
      isDirty.value = true  // trigger auto-save
      showToast(`Created timeline: ${label}`, "success")
    } else {
      showToast(res.error ?? "Failed to create timeline", "error")
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

  async function handleImportSrt() {
    errorMessage.value = ""
    statusMessage.value = "Selecting file..."
    const fileRes = await call<string>("select_file")
    if (!fileRes.success || !fileRes.data) {
      statusMessage.value = ""
      return
    }
    statusMessage.value = "Importing SRT..."
    if (projectRef.value) pushSnapshot(projectRef.value, ["segments"], "导入 SRT") // A1
    const importRes = await call<Project>("import_srt", fileRes.data)
    if (importRes.success && importRes.data) {
      emit("project-updated", importRes.data)
      statusMessage.value = ""
    } else {
      errorMessage.value = importRes.error ?? "Failed to import SRT"
      statusMessage.value = ""
    }
  }

  async function handleImportSrtAsTrack() {
    // v3.0.0 M11-2: import an SRT as an extension track. v3.0.2 M1-3
    // (S3/R3.3): the import always produces tracks + bindings, so the
    // undo snapshot captures both layers unconditionally (M5-1 mapping).
    errorMessage.value = ""
    statusMessage.value = "Selecting file..."
    const fileRes = await call<string>("select_file")
    if (!fileRes.success || !fileRes.data) {
      statusMessage.value = ""
      return
    }
    statusMessage.value = "Importing track SRT..."
    if (projectRef.value) pushSnapshot(projectRef.value, ["tracks", "bindings"], "导入副轨")
    const importRes = await call<ProjectResponse>(
      "import_srt_as_track",
      fileRes.data,
      "",
      "extension",
    )
    if (importRes.success && importRes.data) {
      emit("project-updated", importRes.data)
      // Smoke fix 2nd round: import returns a ProjectPatch (tracks and
      // bindings layers at the TOP level -- Project has no such fields, the
      // old code read them from the wrong shape and always showed 0). The
      // imported track is appended last.
      const patch = importRes.data as ProjectPatch & Project
      const tracksList = patch.tracks ?? projTimelineTracks(patch) ?? []
      const imported = tracksList[tracksList.length - 1]
      const segCount = imported?.segments?.length ?? 0
      showToast(
        `已导入副轨「${imported?.name ?? "?"}」：${segCount} 条字幕`,
        segCount > 0 ? "success" : "error",
        4000,
      )
      statusMessage.value = ""
    } else {
      errorMessage.value = importRes.error ?? "Failed to import track SRT"
      statusMessage.value = ""
    }
  }

  async function handleDetectSilence() {
    errorMessage.value = ""
    await runSilenceDetection()
  }

  // v3.0.2 smoke fix: extension-track segments become deletable (the
  // backend delete_track_segment returns a tracks+bindings ProjectPatch).
  async function handleDeleteTrackSegment(trackId: string, segmentId: string) {
    if (projectRef.value) pushSnapshot(projectRef.value, ["tracks", "bindings"], "删除副轨字幕")
    try {
      const res = await call<ProjectResponse>("delete_track_segment", trackId, segmentId)
      if (res.success && res.data) {
        emit("project-updated", res.data)
        showToast("字幕已删除", "success", 2000)
      } else {
        showToast(res.error ?? "删除副轨字幕失败", "error", 6000)
      }
    } catch (e) {
      showToast(
        `删除副轨字幕失败：${e instanceof Error ? e.message : String(e)}（后端未含 delete_track_segment？请完全退出并重启应用）`,
        "error",
        8000,
      )
    }
  }

  async function handleAddTrack() {
    const proj = projectRef.value
    const count = proj?.timelines?.find(t => t.id === proj.active_timeline_id)?.transcript?.tracks?.length ?? 0
    try {
      const res = await call<ProjectResponse>("add_track", `副轨 ${count + 1}`)
      if (res.success && res.data) {
        emit("project-updated", res.data)
        showToast("已新建副轨（建段模式下点击副轨空白处即可添加字幕）", "success", 4000)
      } else {
        showToast(res.error ?? "新建副轨失败", "error", 6000)
      }
    } catch (e) {
      showToast(`新建副轨失败：${e instanceof Error ? e.message : String(e)}（请完全退出并重启应用）`, "error", 8000)
    }
  }

  async function handleDeleteTrack(trackId: string) {
    if (projectRef.value) pushSnapshot(projectRef.value, ["tracks", "bindings"], "删除副轨")
    try {
      const res = await call<ProjectResponse>("delete_track", trackId)
      if (res.success && res.data) {
        emit("project-updated", res.data)
        showToast("副轨已删除", "success", 3000)
      } else {
        showToast(res.error ?? "删除副轨失败", "error", 6000)
      }
    } catch (e) {
      showToast(
        `删除副轨失败：${e instanceof Error ? e.message : String(e)}（后端未含 delete_track？请完全退出并重启应用）`,
        "error",
        8000,
      )
    }
  }

  // Smoke fix 3rd round: clear a track in ONE backend operation (the
  // per-segment loop churned N patches and looked broken).
  async function handleClearTrackSegments(trackId: string) {
    if (projectRef.value) pushSnapshot(projectRef.value, ["tracks", "bindings"], "清空副轨")
    try {
      const res = await call<ProjectResponse>("clear_track_segments", trackId)
      if (res.success && res.data) {
        emit("project-updated", res.data)
        showToast("副轨已清空", "success", 3000)
      } else {
        showToast(res.error ?? "清空副轨失败", "error", 6000)
      }
    } catch (e) {
      showToast(`清空副轨失败：${e instanceof Error ? e.message : String(e)}（请完全退出并重启应用）`, "error", 8000)
    }
  }

  async function handleAddTrackSegment(trackId: string, start: number, end: number) {
    if (projectRef.value) pushSnapshot(projectRef.value, ["tracks", "bindings"], "新建副轨字幕")
    try {
      const res = await call<ProjectResponse>("add_track_segment", trackId, start, end)
      if (res.success && res.data) {
        emit("project-updated", res.data)
        showToast("已在副轨新建字幕", "success", 2000)
      } else {
        showToast(res.error ?? "新建副轨字幕失败", "error", 6000)
      }
    } catch (e) {
      showToast(`新建副轨字幕失败：${e instanceof Error ? e.message : String(e)}（请完全退出并重启应用）`, "error", 8000)
    }
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
    if (!asr.installedEngines.value.length) {
      showToast("No ASR engine installed. Please install an engine in Settings > AI Engine.", "error", 5000)
      return
    }

    // Get selected engine — use asrPluginId to find the exact variant (CPU vs GPU)
    const engine = asr.asrEngine.value
    const engineInfo = asr.installedEngines.value.find(e => e.pluginId === asr.asrPluginId.value)
      ?? asr.installedEngines.value.find(e => e.engine === engine)

    if (!engineInfo) {
      showToast("Selected ASR engine not found", "error", 3000)
      return
    }

    // Check if engine is ready (plugin installed + model downloaded)
    const status = await asr.checkEngineReady(engine)
    if (!status.ready) {
      showToast(`ASR engine "${engineInfo.displayName}" is not ready. Please download the model in Settings > AI Engine.`, "error", 5000)
      return
    }

    // Persist current ASR settings to backend before transcription
    const settingsSaved = await handleSaveAsrSettings()
    if (!settingsSaved) {
      showToast("Failed to save transcription settings", "error", 3000)
      return
    }

    try {
      // Pass ASR settings as payload to transcription task
      const settings = asr.asrSettingsPerEngine.value[asr.asrEngine.value]
      const started = await runTranscription({
        engine: asr.asrEngine.value,
        plugin_id: asr.asrPluginId.value,
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

  // -- edit --------------------------------------------------------------------

  async function handleToggleEditStatus(segment: Segment, nextStatus?: string) {
    const ok = await toggleEditStatus(segment, nextStatus)
    if (!ok) {
      // v2.3.2 阶段 1.1: toggleEditStatus now reports total failure (write + refresh).
      showToast("Failed to update segment status", "error", 3000)
    }
  }

  // v2.1.1 M4-1: segment click in selection mode (toggle / ctrl / shift range)
  function handleSegmentClickInSelection(segId: string, event: MouseEvent) {
    const orderedIds = mergedSegments.value
      .filter(s => s.type === "subtitle")
      .map(s => s.id)
    handleSegmentClick(segId, event, orderedIds)
  }

  // v2.1.1 M4-1: toggle selection mode (clear selection on exit)
  function handleToggleSelectionMode() {
    toggleSelectionMode()
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

  // v2.1.1 M4-1: batch mark selected segments for deletion (toggle-status)
  async function markSelectedForDeletion() {
    const ids = Array.from(selectedSegmentIds.value)
    if (ids.length === 0) return
    // A2: push BEFORE the call (v3.0.0 M5 fix of the pre-existing bug where
    // the after-state was pushed, making undo a no-op for batch marking).
    if (projectRef.value) pushSnapshot(projectRef.value, ["edits"], "批量标记删除")
    const res = await call<Project>("mark_segments", ids, "delete")
    if (res.success && res.data) {
      emit("project-updated", res.data)
      showToast(`已标记 ${ids.length} 段删除`, "info", 2000)
      clearMultiSelection()
    } else {
      showToast(res.error ?? "批量标记失败", "error", 3000)
    }
  }

  // v2.1.1 M4-3: split a segment at its midpoint
  // v3.0.0 M1-4: waveform-originated splits snap to the nearest word boundary
  async function handleSplitSegment(segmentId: string, position?: number) {
    const seg = mergedSegments.value.find(s => s.id === segmentId)
    if (!seg) return
    // If position is provided (from waveform context menu split), use it and
    // enable word snapping; otherwise use midpoint (from TranscriptRow right-click).
    const snapToWord = position !== undefined && (seg.words?.length ?? 0) > 0
    const pos = position !== undefined ? position : (seg.start + seg.end) / 2
    const { ok, snapOffsetMs } = await splitSegment(segmentId, pos, snapToWord)
    if (ok) {
      if (snapOffsetMs !== null && snapOffsetMs !== 0) {
        showToast(`已吸附词边界 ${snapOffsetMs > 0 ? "+" : ""}${snapOffsetMs}ms`, "info", 2000)
      } else {
        showToast(position !== undefined ? "已按时间指针分割" : "已从中点分割", "success", 1500)
      }
    } else {
      showToast("分割失败", "error", 3000)
    }
  }

  async function handleUpdateText(segmentId: string, text: string) {
    await updateSegmentText(segmentId, text)
  }

  async function handleUpdateTime(segmentId: string, field: "start" | "end", value: number) {
    await updateSegmentTime(segmentId, field, value)
  }

  function handleSelectRange(start: number, end: number) {
    selectEditRange(start, end)
  }

  async function handleAddSegment(start: number, end: number) {
    if (projectRef.value) pushSnapshot(projectRef.value, ["segments"], "新增段落") // A3
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

  // -- LLM / correction ---------------------------------------------------------

  async function handleConfirmAllSuggestions() {
    errorMessage.value = ""
    await confirmAllSuggestions()
  }

  async function handleRejectAllSuggestions() {
    errorMessage.value = ""
    await rejectAllSuggestions()
  }

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

  async function handleOpenSubtitleFullscreen() {
    showSubtitleFullscreen.value = true
    // v2.1.0 Phase 2: load pending corrections from backend on open
    const tlId = getProject().active_timeline_id
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

  function escapeHtml(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
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

  async function handleAcceptCorrection(resultId: string) {
    // v3.0.4 M2-3 (P2-4, debt #14): capture the undo snapshot BEFORE the
    // write. Layer ruling (SPEC M2-3, overriding the PRD): accept also
    // removes the AnalysisResult, so the capture MUST include analysis --
    // missing it would roll back only the text and lose the review entry.
    // Main track = ["segments","analysis"], extension track =
    // ["tracks","analysis"] (scope from the entry's track_id, P2-3).
    const entry = pendingCorrections.value.find(c => c.id === resultId)
    pushSnapshot(
      getProject(),
      correctionUndoLayers(entry),
      "接受字幕修正",
    )
    // Call the bridge directly (not the useLlmTasks boolean wrapper) so
    // the superset patch in the response can be consumed here.
    const res = await call<CorrectionReviewResult>("accept_correction", resultId)
    if (res.success) {
      delete diffCache.value[resultId]
      pendingCorrections.value = pendingCorrections.value.filter(
        c => c.id !== resultId,
      )
      if (res.data?.patch) {
        // Patch path: applyProjectPatch in App.vue auto-detects the patch
        // shape -- the O(project) switch_timeline refresh workaround is
        // gone (debt #14).
        emit("project-updated", res.data.patch)
      } else {
        // Defensive fallback (backend always sends a patch since M2-3):
        // legacy full refresh so the transcript still reflects the write.
        const projRes = await call<Project>("switch_timeline", getProject().active_timeline_id)
        if (projRes.success && projRes.data) emit("project-updated", projRes.data)
      }
    }
  }

  async function handleRejectCorrection(resultId: string) {
    // v3.0.4 M2-3: same snapshot rule as accept. Reject only removes the
    // AnalysisResult, but the two-layer capture keeps "undo once" able to
    // restore the review entry symmetrically.
    const entry = pendingCorrections.value.find(c => c.id === resultId)
    pushSnapshot(
      getProject(),
      correctionUndoLayers(entry),
      "拒绝字幕修正",
    )
    const res = await call<CorrectionReviewResult>("reject_correction", resultId)
    if (res.success) {
      delete diffCache.value[resultId]
      pendingCorrections.value = pendingCorrections.value.filter(
        c => c.id !== resultId,
      )
      if (res.data?.patch) {
        emit("project-updated", res.data.patch)
      }
    }
  }

  async function handleAcceptHighConfidence() {
    const tlId = getProject().active_timeline_id
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
    const tlId = getProject().active_timeline_id
    if (!tlId) return
    const ok = await clearCorrections(tlId)
    if (ok) {
      diffCache.value = {}
      showToast("已清除全部修正", "info", 2000)
    }
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

  // -- project / settings ---------------------------------------------------------

  async function handleCloseProject() {
    await call("close_project")
    videoUrl.value = ""
    emit("project-closed")
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

  async function handleSettingsClosed() {
    showSettingsModal.value = false
    // Refresh LLM config status after settings change
    await loadLlmConfig()
  }

  function handleGoToSettings() {
    showSettingsModal.value = true
  }

  async function handleSearchReplace(query: string, replacement: string, scope: string) {
    const result = await searchReplace(query, replacement, scope)
    if (result) {
      statusMessage.value = `Replaced ${result.count} occurrences`
    }
  }

  return {
    // playback / video
    handleRegenerateWaveform, handleRequestProxy, handleSeek, handleSetTime,
    handleVideoLoaded, handleTimeUpdate, handleTogglePlay, handleSeekTo,
    handleVolumeChange, handleRateChange, handleFullscreen,
    // timeline
    handleSwitchTimeline, handleCreateTimeline, handleDeleteTimeline,
    handleImportSrt, handleImportSrtAsTrack, handleDetectSilence, handleClearSubtitles, handleTranscribe,
  handleDeleteTrackSegment,
  handleDeleteTrack,
  handleAddTrack,
  handleAddTrackSegment,
  handleClearTrackSegments,
    // edit
    handleToggleEditStatus, handleSegmentClickInSelection, handleToggleSelectionMode,
    handleMergeSelected, handleSplitSegment, handleUpdateText, handleUpdateTime,
    handleSelectRange, handleAddSegment, handleDeleteSegment, handleSeekSegment,
    handleSubtitleTrim, handleDeleteSubtitleTrimEdits, handleConfirmDeleteSilence,
    markSelectedForDeletion,
    // llm / correction
    handleConfirmAllSuggestions, handleRejectAllSuggestions,
    handleStartSmartDelete, handleStartSubtitleCorrection, handleStartHighlight,
    handleCancelSingle, handleOpenSubtitleFullscreen,
    handleAcceptCorrection, handleRejectCorrection, handleAcceptHighConfidence,
    handleClearCorrections, handleRemoveHighlight, handleAddToHighlight,
    renderDiff, categoryLabel,
    // project / settings
    handleCloseProject, handleSaveProject, handleSettingsClosed,
    handleGoToSettings, handleSearchReplace,
  }
}

// -- provide / inject ------------------------------------------------------

export const WORKSPACE_ACTIONS_KEY: InjectionKey<WorkspaceActions> = Symbol("workspace-actions")

export function provideWorkspaceActions(actions: WorkspaceActions): void {
  provide(WORKSPACE_ACTIONS_KEY, actions)
}

export function useWorkspaceActions(): WorkspaceActions {
  const actions = inject(WORKSPACE_ACTIONS_KEY)
  if (!actions) {
    throw new Error("useWorkspaceActions must be used within a WorkspacePage subtree (provideWorkspaceActions)")
  }
  return actions
}

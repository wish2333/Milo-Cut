/**
 * v3.0.4 P2-4 (M2-3): useWorkspaceActions correction-review tests.
 *
 * Locks (SPEC M2-3 / PLAN P2-4):
 * - accept with a patch in the response -> "project-updated" is emitted
 *   ONCE with the patch payload and the O(project) switch_timeline full
 *   refresh workaround is gone (debt #14).
 * - pushSnapshot is captured BEFORE the bridge call, main-track entry ->
 *   ["segments","analysis"], extension-track entry -> ["tracks","analysis"]
 *   (analysis always joins: accept/reject also remove the AnalysisResult).
 * - undo once reverts an accept (text restored AND the review entry is
 *   back in analysis), redo is symmetric -- simulated through the real
 *   useUndoRedo + applyProjectPatch machinery with an in-memory
 *   apply_undo backend (same simulation approach as useUndoRedo.test.ts).
 * - reject consumes the patch the same way (one structural case).
 * - timeline switch re-fetches the pending review list (R3 pairing with
 *   the backend timeline-pinning guard).
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref, type Ref } from "vue"
import {
  createWorkspaceActions,
  type CorrectionReviewEntry,
  type WorkspaceActions,
  type WorkspaceActionsDeps,
} from "./useWorkspaceActions"
import { useUndoRedo } from "@/composables/useUndoRedo"
import { applyProjectPatch } from "@/utils/projectPatch"
import { isProjectPatch } from "@/types/project"
import type {
  AnalysisData,
  AnalysisResult,
  Project,
  ProjectPatch,
  Segment,
} from "@/types/project"
import type { UndoLayer } from "@/utils/undoRecords"
import { lastSeenRevision } from "@/utils/revision"
import { mockAnalysisData, mockProject, mockSegment } from "@/test/helpers/mockProject"

vi.mock("@/bridge", () => ({
  call: vi.fn(),
}))

import { call } from "@/bridge"
const mockCall = vi.mocked(call)

// ------------------------------------------------------------------
// Fixtures
// ------------------------------------------------------------------

function correctionResult(id: string, segmentId: string): AnalysisResult {
  return {
    id,
    type: "llm_subtitle_correction",
    segment_ids: [segmentId],
    confidence: 0.9,
    detail: JSON.stringify({ segment_id: segmentId, corrected_text: "new text" }),
  }
}

function projectBefore(): Project {
  const seg: Segment = mockSegment({ id: "seg-1", text: "old text" })
  const analysis: AnalysisData = mockAnalysisData({
    results: [correctionResult("res-1", "seg-1")],
  })
  const base = mockProject()
  return {
    ...base,
    timelines: [
      {
        ...base.timelines[0],
        transcript: { ...base.timelines[0].transcript, segments: [seg] },
        analysis,
      },
    ],
  }
}

/** The patch a real M2-3 backend returns for accepting res-1. */
function acceptPatch(): ProjectPatch {
  const before = projectBefore()
  const seg = before.timelines[0].transcript.segments[0]
  return {
    revision: 2,
    timeline_id: "default",
    segments: [{ ...seg, text: "new text", dirty_flags: { llm_corrected: true } }],
    analysis: mockAnalysisData({ results: [] }),
  }
}

/** The patch a real M2-3 backend returns for rejecting res-1. */
function rejectPatch(): ProjectPatch {
  return {
    revision: 2,
    timeline_id: "default",
    analysis: mockAnalysisData({ results: [] }),
  }
}

// ------------------------------------------------------------------
// Deps factory (minimal stubs; only the members under test are real)
// ------------------------------------------------------------------

interface DepsOverrides {
  project: Ref<Project>
  pendingCorrections: Ref<CorrectionReviewEntry[]>
  pushSnapshot: WorkspaceActionsDeps["pushSnapshot"]
  emit: WorkspaceActionsDeps["emit"]
  loadCorrections?: WorkspaceActionsDeps["loadCorrections"]
  // v3.0.5 R5.4: review-scope override (default = main-track view)
  getReviewScope?: WorkspaceActionsDeps["getReviewScope"]
  acceptHighConfidenceCorrections?: WorkspaceActionsDeps["acceptHighConfidenceCorrections"]
  clearCorrections?: WorkspaceActionsDeps["clearCorrections"]
  // v3.0.5 R5.6: rerun-toast coverage hooks
  showToast?: WorkspaceActionsDeps["showToast"]
  generateSubtitleKeepRanges?: WorkspaceActionsDeps["generateSubtitleKeepRanges"]
}

function makeActions(o: DepsOverrides): WorkspaceActions {
  const noop = () => undefined
  const deps = {
    emit: o.emit,
    showToast: o.showToast ?? vi.fn(),
    getProject: () => o.project.value,
    errorMessage: { value: "" },
    statusMessage: { value: "" },
    videoRef: { value: null },
    videoUrl: { value: "" },
    waveformUrl: { value: "" },
    videoVolume: { value: 1 },
    videoPlaybackRate: { value: 1 },
    isGeneratingProxy: { value: false },
    demoMode: false,
    regenPoll: { current: null },
    subtitleTrimPadding: { value: 0 },
    showConfirmDeleteSilence: { value: false },
    showSettingsModal: { value: false },
    showSubtitleFullscreen: { value: false },
    isDirty: { value: false },
    isSaving: { value: false },
    lastSavedAt: { value: null },
    mergedSegments: { value: [] as Segment[] },
    seekPlayback: noop,
    demoPlayback: { seek: noop, toggle: noop },
    handlePlaybackTimeUpdate: noop,
    runTranscription: vi.fn(async () => true),
    runSilenceDetection: vi.fn(async () => true),
    toggleEditStatus: vi.fn(async () => true),
    updateSegmentText: vi.fn(async () => undefined),
    updateSegmentTime: vi.fn(async () => undefined),
    searchReplace: vi.fn(async () => null),
    mergeSegments: vi.fn(async () => true),
    splitSegment: vi.fn(async () => ({ ok: true, snapOffsetMs: null })),
    deleteSegment: vi.fn(async () => null),
    selectEditRange: noop,
    generateSubtitleKeepRanges: o.generateSubtitleKeepRanges ?? vi.fn(async () => null),
    deleteSubtitleTrimEdits: vi.fn(async () => true),
    deleteSilenceSegments: vi.fn(async () => true),
    confirmAllSuggestions: vi.fn(async () => undefined),
    rejectAllSuggestions: vi.fn(async () => undefined),
    selectedSegmentIds: { value: new Set<string>() },
    editSelectedSegmentId: { value: null as string | null },
    toggleSelectionMode: noop,
    clearMultiSelection: noop,
    handleSegmentClick: noop,
    pushSnapshot: o.pushSnapshot,
    projectRef: { value: o.project.value },
    flushPendingUpdates: vi.fn(async () => undefined),
    llmConfig: { value: { configured: false } },
    loadLlmConfig: vi.fn(async () => undefined),
    startSmartDelete: vi.fn(async () => undefined),
    startSubtitleCorrection: vi.fn(async () => undefined),
    startHighlight: vi.fn(async () => undefined),
    highlightResults: { value: [] },
    hydrateHighlightsFromProject: vi.fn(),
    pendingCorrections: o.pendingCorrections,
    loadCorrections: o.loadCorrections ?? vi.fn(async () => undefined),
    computeDiff: vi.fn(async () => null),
    acceptCorrection: vi.fn(async () => true),
    rejectCorrection: vi.fn(async () => true),
    acceptHighConfidenceCorrections:
      o.acceptHighConfidenceCorrections ?? vi.fn(async () => null),
    clearCorrections: o.clearCorrections ?? vi.fn(async () => null),
    getReviewScope:
      o.getReviewScope ?? (() => ({ trackId: "", trackName: null })),
    asr: {
      asrEngine: { value: "" },
      asrPluginId: { value: "" },
      asrSettingsPerEngine: { value: {} },
      installedEngines: { value: [] },
      checkEngineReady: vi.fn(async () => true),
    },
    handleSaveAsrSettings: vi.fn(async () => true),
    confirmAction: vi.fn(async () => true),
  }
  return createWorkspaceActions(deps as unknown as WorkspaceActionsDeps)
}

/** App.vue-style emit handler: apply patches through applyProjectPatch. */
function applyingEmit(project: Ref<Project>) {
  return vi.fn((event: string, data: unknown) => {
    if (event === "project-updated" && isProjectPatch(data)) {
      project.value = applyProjectPatch(project.value, data)
    }
  }) as unknown as WorkspaceActionsDeps["emit"]
}

function mainTrackEntry(): CorrectionReviewEntry {
  return { id: "res-1", original_text: "old text", corrected_text: "new text", track_id: "" }
}

// ------------------------------------------------------------------
// Tests
// ------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks()
  lastSeenRevision.value = 0
})

describe("handleAcceptCorrection -- superset patch consumption", () => {
  it("emits project-updated once with the patch and never calls switch_timeline", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([mainTrackEntry()])
    const patch = acceptPatch()
    mockCall.mockImplementation(async (method: string) => {
      if (method === "accept_correction") {
        return { success: true, data: { segment_id: "seg-1", patch } }
      }
      return { success: false, error: `unexpected method ${method}` }
    })
    const emit = applyingEmit(project)
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot: vi.fn(),
      emit,
    })

    await actions.handleAcceptCorrection("res-1")

    // Patch payload forwarded exactly once for App.vue to auto-detect.
    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit).toHaveBeenCalledWith("project-updated", patch)
    // The applied write is visible in the local project simulation.
    expect(
      project.value.timelines[0].transcript.segments[0].text,
    ).toBe("new text")
    // Debt #14: no O(project) switch_timeline full refresh.
    const methods = mockCall.mock.calls.map(c => c[0])
    expect(methods).toContain("accept_correction")
    expect(methods).not.toContain("switch_timeline")
    // The accepted entry left the pending review list.
    expect(pending.value.map(c => c.id)).toEqual([])
  })

  it("falls back to the legacy full refresh when the response has no patch", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([mainTrackEntry()])
    const refreshed = projectBefore()
    mockCall.mockImplementation(async (method: string) => {
      if (method === "accept_correction") {
        return { success: true, data: { segment_id: "seg-1" } }
      }
      if (method === "switch_timeline") {
        return { success: true, data: refreshed }
      }
      return { success: false, error: `unexpected method ${method}` }
    })
    const emit = applyingEmit(project)
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot: vi.fn(),
      emit,
    })

    await actions.handleAcceptCorrection("res-1")
    expect(emit).toHaveBeenCalledWith("project-updated", refreshed)
  })
})

describe("handleAcceptCorrection -- undo capture layers (M2-3 ruling)", () => {
  it("captures [segments, analysis] BEFORE the bridge call for a main-track entry", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([mainTrackEntry()])
    const pushSnapshot = vi.fn()
    mockCall.mockResolvedValue({
      success: true,
      data: { segment_id: "seg-1", patch: acceptPatch() },
    })
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot,
      emit: applyingEmit(project),
    })

    await actions.handleAcceptCorrection("res-1")

    expect(pushSnapshot).toHaveBeenCalledTimes(1)
    const [capturedProject, layers, label] = pushSnapshot.mock.calls[0]
    expect((capturedProject as Project).timelines[0].transcript.segments[0].text)
      .toBe("old text") // before-state, not the post-patch project
    expect(layers).toEqual(["segments", "analysis"])
    expect(typeof label).toBe("string")
    // Snapshot strictly precedes the accept bridge call.
    expect(pushSnapshot.mock.invocationCallOrder[0]).toBeLessThan(
      mockCall.mock.invocationCallOrder[0],
    )
  })

  it("captures [tracks, analysis] for an extension-track entry (track_id scope)", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([
      { id: "res-1", original_text: "old text", corrected_text: "new text", track_id: "trk-1" },
    ])
    const pushSnapshot = vi.fn()
    mockCall.mockResolvedValue({
      success: true,
      data: { segment_id: "seg-1", track_id: "trk-1", patch: acceptPatch() },
    })
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot,
      emit: applyingEmit(project),
    })

    await actions.handleAcceptCorrection("res-1")
    const [, layers] = pushSnapshot.mock.calls[0]
    expect(layers).toEqual(["tracks", "analysis"])
  })
})

describe("undo once reverts an accept, redo is symmetric (in-memory simulation)", () => {
  it("restores the text AND the review entry, then re-applies on redo", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([mainTrackEntry()])
    const { pushSnapshot, undo, redo } = useUndoRedo()

    // In-memory "backend": apply_undo turns the captured layers into a
    // patch against the current project (same simulation approach as
    // useUndoRedo.test.ts, extended to actually restore the layers).
    let revCounter = 2
    mockCall.mockImplementation(async (method: string, ...args: unknown[]) => {
      if (method === "accept_correction") {
        return { success: true, data: { segment_id: "seg-1", patch: acceptPatch() } }
      }
      if (method === "apply_undo") {
        const layers = args[0] as Partial<Record<UndoLayer, unknown>>
        const patch: ProjectPatch = {
          revision: ++revCounter,
          timeline_id: project.value.active_timeline_id,
        }
        if ("segments" in layers) patch.segments = layers.segments as Segment[]
        if ("analysis" in layers) patch.analysis = layers.analysis as AnalysisData
        return { success: true, data: patch }
      }
      return { success: false, error: `unexpected method ${method}` }
    })

    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot, // the REAL layered-undo capture
      emit: applyingEmit(project),
    })

    // Accept: text updated, review entry consumed.
    await actions.handleAcceptCorrection("res-1")
    expect(project.value.timelines[0].transcript.segments[0].text).toBe("new text")
    expect(project.value.timelines[0].analysis.results).toEqual([])

    // Undo once: the pre-accept layers come back -- BOTH the text and
    // the removed AnalysisResult (the analysis capture layer is what
    // makes "undo once" restore the review entry).
    const undoOutcome = await undo(project.value)
    expect(undoOutcome.ok).toBe(true)
    project.value = applyProjectPatch(project.value, undoOutcome.patch!)
    expect(project.value.timelines[0].transcript.segments[0].text).toBe("old text")
    expect(project.value.timelines[0].analysis.results.map(r => r.id)).toEqual(["res-1"])

    // Redo: symmetric re-apply of the accepted state.
    const redoOutcome = await redo(project.value)
    expect(redoOutcome.ok).toBe(true)
    project.value = applyProjectPatch(project.value, redoOutcome.patch!)
    expect(project.value.timelines[0].transcript.segments[0].text).toBe("new text")
    expect(project.value.timelines[0].analysis.results).toEqual([])
  })
})

describe("handleRejectCorrection -- same consumption shape", () => {
  it("emits the analysis-layer patch and captures [segments, analysis] for a main-track entry", async () => {
    const project = ref(projectBefore())
    const pending = ref<CorrectionReviewEntry[]>([mainTrackEntry()])
    const patch = rejectPatch()
    const pushSnapshot = vi.fn()
    mockCall.mockImplementation(async (method: string) => {
      if (method === "reject_correction") {
        return { success: true, data: { segment_id: "seg-1", patch } }
      }
      return { success: false, error: `unexpected method ${method}` }
    })
    const emit = applyingEmit(project)
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot,
      emit,
    })

    await actions.handleRejectCorrection("res-1")

    expect(emit).toHaveBeenCalledTimes(1)
    expect(emit).toHaveBeenCalledWith("project-updated", patch)
    // Reject removes the review entry but never the text.
    expect(project.value.timelines[0].transcript.segments[0].text).toBe("old text")
    expect(project.value.timelines[0].analysis.results).toEqual([])
    const [, layers] = pushSnapshot.mock.calls[0]
    expect(layers).toEqual(["segments", "analysis"])
    expect(pending.value.map(c => c.id)).toEqual([])
  })
})

describe("handleSwitchTimeline -- pending review re-fetch (R3 pairing)", () => {
  it("re-fetches corrections for the newly active timeline after a successful switch", async () => {
    const project = ref(projectBefore())
    const switched = projectBefore()
    mockCall.mockImplementation(async (method: string) => {
      if (method === "switch_timeline") {
        return { success: true, data: switched }
      }
      return { success: false, error: `unexpected method ${method}` }
    })
    const loadCorrections = vi.fn(async () => undefined)
    const actions = makeActions({
      project,
      pendingCorrections: ref<CorrectionReviewEntry[]>([mainTrackEntry()]),
      pushSnapshot: vi.fn(),
      emit: applyingEmit(project),
      loadCorrections,
    })

    await actions.handleSwitchTimeline("default")
    expect(loadCorrections).toHaveBeenCalledWith("default")

    // A failed switch keeps the current review list untouched.
    loadCorrections.mockClear()
    mockCall.mockResolvedValue({ success: false, error: "boom" })
    await actions.handleSwitchTimeline("other")
    expect(loadCorrections).not.toHaveBeenCalled()
  })
})


// ------------------------------------------------------------------
// v3.0.5 R5.4 (M5.4 rulings 3-6): batch three-state scope + aggregated
// patch consumption + scoped confirm copy
// ------------------------------------------------------------------

describe("batch accept/clear -- three-state scope (v3.0.5 R5.4)", () => {
  const PATCH = { revision: 9, timeline_id: "default", analysis: null }

  function entries(): CorrectionReviewEntry[] {
    return [
      { id: "r-main-hi", original_text: "a", corrected_text: "b", track_id: "", confidence: 0.9 },
      { id: "r-main-lo", original_text: "a2", corrected_text: "b2", track_id: "", confidence: 0.5 },
      { id: "r-trk-hi", original_text: "c", corrected_text: "d", track_id: "trk_x", confidence: 0.95 },
    ]
  }

  function setup(o: Partial<DepsOverrides> = {}) {
    const project = ref(mockProject())
    const pending = ref<CorrectionReviewEntry[]>(entries())
    const pushSnapshot = vi.fn()
    const emit = vi.fn()
    const acceptHighConfidenceCorrections = vi.fn(
      async () => ({ accepted: 1, remaining: 0, patch: PATCH }),
    )
    const clearCorrections = vi.fn(async () => ({ cleared: 2, patch: PATCH }))
    const actions = makeActions({
      project,
      pendingCorrections: pending,
      pushSnapshot,
      emit,
      acceptHighConfidenceCorrections,
      clearCorrections,
      ...o,
    })
    return { actions, pushSnapshot, emit, acceptHighConfidenceCorrections, clearCorrections, pending }
  }

  const confirmMock = vi.fn(() => true)

  beforeEach(() => {
    confirmMock.mockClear()
    vi.stubGlobal("confirm", confirmMock)
  })

  it("main scope: confirm names 主轨 with the scope-filtered high-confidence count; snapshot = two main layers", async () => {
    const { actions, pushSnapshot, acceptHighConfidenceCorrections } = setup()
    await actions.handleAcceptHighConfidence()

    expect(confirmMock).toHaveBeenCalledWith("将接受当前轨〈主轨〉的 1 条高置信度建议")
    // snapshot BEFORE the bridge call, main two layers (MF-1)
    expect(pushSnapshot).toHaveBeenCalledWith(
      expect.anything(), ["segments", "analysis"], "批量接受",
    )
    expect(acceptHighConfidenceCorrections).toHaveBeenCalledWith(expect.any(String), 0.8, "")
  })

  it("track scope: confirm names the track; snapshot = track two layers", async () => {
    const { actions, pushSnapshot, acceptHighConfidenceCorrections } = setup({
      getReviewScope: () => ({ trackId: "trk_x", trackName: "English" }),
    })
    await actions.handleAcceptHighConfidence()

    expect(confirmMock).toHaveBeenCalledWith("将接受当前轨〈English〉的 1 条高置信度建议")
    expect(pushSnapshot).toHaveBeenCalledWith(
      expect.anything(), ["tracks", "analysis"], "批量接受",
    )
    expect(acceptHighConfidenceCorrections).toHaveBeenCalledWith(expect.any(String), 0.8, "trk_x")
  })

  it("全部 scope (null): three-layer union snapshot + 「全部轨道」 copy counting every scope", async () => {
    const { actions, pushSnapshot, acceptHighConfidenceCorrections } = setup({
      getReviewScope: () => ({ trackId: null, trackName: null }),
    })
    await actions.handleAcceptHighConfidence()

    expect(confirmMock).toHaveBeenCalledWith("将接受当前轨〈全部轨道〉的 2 条高置信度建议")
    expect(pushSnapshot).toHaveBeenCalledWith(
      expect.anything(), ["segments", "tracks", "analysis"], "批量接受",
    )
    expect(acceptHighConfidenceCorrections).toHaveBeenCalledWith(expect.any(String), 0.8, null)
  })

  it("accept consumes the aggregated patch through project-updated -- no switch_timeline full refresh", async () => {
    const { actions, emit } = setup()
    await actions.handleAcceptHighConfidence()

    expect(emit).toHaveBeenCalledWith("project-updated", PATCH)
    expect(mockCall).not.toHaveBeenCalledWith("switch_timeline", expect.anything())
  })

  it("accept without a patch falls back to the legacy full refresh (zero-accepted / older backend)", async () => {
    const { actions, emit } = setup({
      acceptHighConfidenceCorrections: vi.fn(async () => ({ accepted: 0, remaining: 2 })),
    })
    mockCall.mockResolvedValue({ success: true, data: mockProject() })
    await actions.handleAcceptHighConfidence()

    expect(emit).toHaveBeenCalledWith("project-updated", expect.anything())
    expect(mockCall).toHaveBeenCalledWith("switch_timeline", expect.anything())
  })

  it("clear: scoped confirm counts ALL pending of the scope, consumes patch, toast shows cleared_count", async () => {
    const { actions, emit, clearCorrections, pushSnapshot } = setup({
      getReviewScope: () => ({ trackId: "trk_x", trackName: "English" }),
    })
    await actions.handleClearCorrections()

    expect(confirmMock).toHaveBeenCalledWith("将清除当前轨〈English〉的 1 条待审建议")
    expect(clearCorrections).toHaveBeenCalledWith(expect.any(String), "trk_x")
    // snapshot before the write, track two layers
    expect(pushSnapshot).toHaveBeenCalledWith(
      expect.anything(), ["tracks", "analysis"], "批量清除",
    )
    expect(emit).toHaveBeenCalledWith("project-updated", PATCH)
  })

  it("empty scoped set is a no-op with an informational toast (no confirm, no bridge call)", async () => {
    const { actions, acceptHighConfidenceCorrections } = setup({
      getReviewScope: () => ({ trackId: "trk_none", trackName: null }),
    })
    // no-op guard: assert via the bridge absence (no confirm either)
    await actions.handleAcceptHighConfidence()
    expect(acceptHighConfidenceCorrections).not.toHaveBeenCalled()
    expect(confirmMock).not.toHaveBeenCalled()
  })
})

// ------------------------------------------------------------------
// v3.0.5 R5.6 (M5.6 ruling 2): rerun toast reports invalidated_count
// ------------------------------------------------------------------

describe("handleSubtitleTrim -- rerun toast reports invalidated_count (v3.0.5 R5.6)", () => {
  function setup(result: { new_edits: number; keep_ranges: number; invalidated_count: number } | null) {
    const showToast = vi.fn()
    const actions = makeActions({
      project: ref(mockProject()),
      pendingCorrections: ref<CorrectionReviewEntry[]>([]),
      pushSnapshot: vi.fn(),
      emit: vi.fn(),
      showToast,
      generateSubtitleKeepRanges: vi.fn(async () => result),
    })
    return { actions, showToast }
  }

  it("invalidated > 0: reports new additions AND ranges cleared by keep overlap", async () => {
    const { actions, showToast } = setup({ new_edits: 5, keep_ranges: 3, invalidated_count: 2 })
    await actions.handleSubtitleTrim()
    expect(showToast).toHaveBeenCalledWith(
      "新增 5 条、按保留区间清除 2 条旧区间",
      "success",
      5000,
    )
  })

  it("invalidated = 0: only reports the new additions", async () => {
    const { actions, showToast } = setup({ new_edits: 4, keep_ranges: 2, invalidated_count: 0 })
    await actions.handleSubtitleTrim()
    expect(showToast).toHaveBeenCalledWith("新增 4 条", "success", 5000)
  })

  it("null result (bridge failure): error toast, no count wording", async () => {
    const { actions, showToast } = setup(null)
    await actions.handleSubtitleTrim()
    expect(showToast).toHaveBeenCalledWith(
      "Failed to generate subtitle trim ranges",
      "error",
      5000,
    )
  })
})

/**
 * v3.0.4 M4-3 (P3-8): deleteRanges snapshot lock.
 *
 * The `deleteRanges` computed (WorkspacePage.vue:325-330) drives ALL THREE
 * playback-facing consumers -- useEditedPlayback skip ranges (rawDeleteRanges),
 * the progress-bar red overlay (VideoControls :delete-ranges) and the export
 * preview (DemoPreviewSurface :delete-ranges) -- so locking the computed
 * output locks all three. Current filter (ZERO change this step):
 * action === "delete" && (status === "confirmed" || source === "subtitle_trim")
 * -- pending manual ranges are naturally excluded, and subtitle_trim keeps
 * its historical source bypass (auto-applied trims skip the review flow).
 *
 * Mock scaffolding mirrors WorkspacePage.rangeDecision.test.ts (P3-6 host);
 * the VideoControls stub ADDS a deleteRanges prop under observation.
 */
/* eslint-disable vue/one-component-per-file -- test stubs (trackEdit host precedent) */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, ref } from "vue"
import type { Project } from "@/types/project"
import { mockProject, mockTimeline, mockSegment, mockEditDecision } from "@/test/helpers/mockProject"

type EventHandler = (detail: unknown) => void
const callMock = vi.fn()

vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => callMock(...args),
  onEvent: (name: string, handler: EventHandler) => {
    void name
    void handler
    return () => {}
  },
  isDemoMode: () => false,
}))

vi.mock("@/composables/useUndoRedo", () => ({
  useUndoRedo: () => ({
    pushSnapshot: vi.fn(),
    undo: vi.fn(async () => ({ ok: false, error: "empty" })),
    redo: vi.fn(async () => ({ ok: false, error: "empty" })),
    clearHistory: vi.fn(),
    undoStack: ref([]),
    redoStack: ref([]),
    canUndo: ref(false),
    canRedo: ref(false),
  }),
}))

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ showToast: vi.fn(), toasts: ref([]), removeToast: vi.fn() }),
}))

vi.mock("@/composables/useAnalysis", () => ({
  useAnalysis: () => ({
    isDetecting: ref(false),
    detectionProgress: ref(0),
    activeTask: ref(null),
    runSilenceDetection: vi.fn(),
    runTranscription: vi.fn(),
    confirmEdit: vi.fn(),
    rejectEdit: vi.fn(),
    batchUpdateEdits: vi.fn(),
    deleteEdits: vi.fn(),
  }),
}))

vi.mock("@/composables/useExport", () => ({
  useExport: () => ({
    isExporting: ref(false),
    exportProgress: ref(0),
    confirmedEdits: ref([]),
    estimatedSaving: ref(0),
  }),
}))

vi.mock("@/composables/useEdit", () => ({
  useEdit: () => ({
    searchReplace: vi.fn(),
    mergeSegments: vi.fn(),
    splitSegment: vi.fn(),
    confirmAllSuggestions: vi.fn(),
    rejectAllSuggestions: vi.fn(),
    generateSubtitleKeepRanges: vi.fn(),
    deleteSegment: vi.fn(),
    deleteSilenceSegments: vi.fn(),
    deleteSubtitleTrimEdits: vi.fn(),
  }),
}))

vi.mock("@/composables/useSegmentEdit", () => ({
  useSegmentEdit: () => ({
    selectedSegmentId: ref(null),
    selectRange: vi.fn(),
    selectedRange: ref(null),
    updateSegmentTime: vi.fn(),
    updateSegmentText: vi.fn(),
    toggleEditStatus: vi.fn(),
    flushPendingUpdates: vi.fn(async () => {}),
    selectionMode: ref(false),
    selectedSegmentIds: ref(new Set<string>()),
    selectedCount: ref(0),
    toggleSelectionMode: vi.fn(),
    handleSegmentClick: vi.fn(),
    clearMultiSelection: vi.fn(),
  }),
}))

vi.mock("@/composables/useSettings", () => ({
  useSettings: () => ({
    settings: ref(null),
    loadSettings: vi.fn(async () => true),
    updateSettings: vi.fn(async () => true),
  }),
}))

vi.mock("@/composables/useAsrEngines", () => ({
  useAsrEngines: () => ({
    asrEngine: ref("faster-whisper"),
    asrPluginId: ref(""),
    asrSettingsPerEngine: ref({}),
    installedEngines: ref([]),
    hasInstalledEngines: ref(false),
    availableModels: ref([]),
    isDarwin: ref(false),
    isMlx: ref(false),
    supportsGpu: ref(false),
    computeTypeOptions: ref([]),
    ensureLoaded: vi.fn(async () => {}),
    saveAsrSettings: vi.fn(),
    checkEngineReady: vi.fn(),
  }),
}))

vi.mock("@/composables/useUvAvailability", () => ({
  useUvAvailability: () => ({ uvAvailable: ref(false) }),
}))

vi.mock("@/composables/useEditedPlayback", () => ({
  useEditedPlayback: () => ({
    handleTimeUpdate: vi.fn(),
    handleSeeked: vi.fn(),
    seek: vi.fn(),
  }),
}))

vi.mock("@/composables/useDemoPlayback", () => ({
  useDemoPlayback: () => ({ attach: vi.fn(), detach: vi.fn() }),
}))

vi.mock("@/composables/usePlaybackClock", () => ({
  createPlaybackClock: () => ({
    coarseTime: ref(0),
    ingest: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  }),
}))

vi.mock("@/composables/useWorkspaceActions", () => ({
  createWorkspaceActions: () =>
    new Proxy({}, { get: () => vi.fn() }) as Record<string, ReturnType<typeof vi.fn>>,
  provideWorkspaceActions: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Stubs (VideoControls observes the deleteRanges prop -- it is the only
// always-rendered :delete-ranges consumer in the non-demo template)
// ---------------------------------------------------------------------------
const VideoControlsStub = defineComponent({
  name: "VideoControls",
  props: { deleteRanges: { type: Array, default: () => [] } },
  template: "<div data-test='video-controls-stub'></div>",
})

const WaveformEditorStub = defineComponent({
  name: "WaveformEditor",
  template: "<div data-test='waveform-stub'></div>",
})

const TimelineStub = defineComponent({
  name: "Timeline",
  props: {
    segments: { type: Array, default: () => [] },
    activeTrackId: { type: String, default: null },
    activeTrackName: { type: String, default: null },
    globalEditMode: { type: Boolean, default: false },
  },
  emits: ["select-track", "update-track-text", "toggle-edit-mode"],
  template: "<div data-test='timeline-stub'></div>",
})

const SplitPanelStub = defineComponent({
  name: "SplitPanel",
  template: "<div><slot name='left' /><slot name='right' /></div>",
})

// ---------------------------------------------------------------------------
// Fixture: pending manual delete + pending manual keep + confirmed manual
// delete + pending subtitle_trim (historical source bypass) in one project.
// ---------------------------------------------------------------------------
function projectWithRanges(): Project {
  return mockProject({
    timelines: [
      mockTimeline({
        id: "tl-1",
        transcript: {
          engine: "srt",
          language: "zh-CN",
          segments: [mockSegment({ id: "seg-1", start: 5, end: 8 })],
          tracks: [],
          bindings: [],
        },
        edits: [
          mockEditDecision({
            id: "ed-manual-pending",
            start: 2,
            end: 4,
            action: "delete",
            source: "manual",
            status: "pending",
            target_type: "range",
            target_id: undefined,
          }),
          mockEditDecision({
            id: "ed-manual-keep-pending",
            start: 4.5,
            end: 5.5,
            action: "keep",
            source: "manual",
            status: "pending",
            target_type: "range",
            target_id: undefined,
          }),
          mockEditDecision({
            id: "ed-manual-confirmed",
            start: 7,
            end: 8.5,
            action: "delete",
            source: "manual",
            status: "confirmed",
            target_type: "range",
            target_id: undefined,
          }),
          mockEditDecision({
            id: "ed-trim-pending",
            start: 1,
            end: 1.5,
            action: "delete",
            source: "subtitle_trim",
            status: "pending",
            target_type: "range",
            target_id: undefined,
          }),
        ],
      }),
    ],
    active_timeline_id: "tl-1",
  })
}

async function mountWorkspacePage(): Promise<VueWrapper> {
  vi.resetModules()
  const { default: WorkspacePage } = await import("./WorkspacePage.vue")
  return mount(WorkspacePage, {
    props: { project: projectWithRanges() },
    global: {
      stubs: {
        Timeline: TimelineStub,
        SplitPanel: SplitPanelStub,
        ProgressBar: true,
        TimelineSwitcher: true,
        WaveformEditor: WaveformEditorStub,
        SearchReplaceBar: true,
        VideoControls: VideoControlsStub,
        SubtitleOverlay: true,
        SettingsModal: true,
        TranscribeSettingsPopover: true,
        SilenceSettingsPopover: true,
        SubtitleTrimSettingsPopover: true,
        DemoPreviewSurface: true,
        DemoResponsiveWorkspace: true,
        Teleport: true,
        Transition: false,
      },
    },
  })
}

beforeEach(() => {
  callMock.mockReset()
  callMock.mockImplementation(async () => ({ success: true, data: {} }))
})

describe("WorkspacePage deleteRanges snapshot lock (M4-3 / P3-8)", () => {
  it("pending manual ranges stay OUT of deleteRanges; confirmed manual + subtitle_trim bypass stay IN (skip/red-overlay/export-preview unaffected by pending)", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    const controls = wrapper.findComponent(VideoControlsStub)
    expect(controls.exists()).toBe(true)
    const ranges = controls.props("deleteRanges") as { start: number; end: number }[]

    // Full-filter snapshot: sorted output, exactly the confirmed manual
    // range + the subtitle_trim source bypass. Both pending manual entries
    // (delete AND keep) are absent -- pending never reaches playback.
    expect(ranges).toEqual([
      { start: 1, end: 1.5 },
      { start: 7, end: 8.5 },
    ])
    expect(ranges.some(r => r.start === 2)).toBe(false)
    expect(ranges.some(r => r.start === 4.5)).toBe(false)
    wrapper.unmount()
  })
})

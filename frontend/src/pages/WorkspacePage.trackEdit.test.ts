/**
 * v3.0.4 M3-1 (R3.1): page-level halves of the edit-sweep extension.
 *
 * C2 flush-on-switch: handleSelectListTrack awaits flushPendingTrackUpdates
 *    BEFORE selectListTrack (WorkspacePage) -- with the REAL useTrackEdit
 *    kernel (bridge mocked), a pending track-row text debounce (300ms,
 *    frozen via fake timers) is committed by the switch's flush ahead of
 *    the view change, so no draft is lost. Order is observed through a
 *    shared log: the bridge submit stamps "flush-commit", a watcher on the
 *    Timeline stub's activeTrackId stamps "select-track:<id>".
 * C3: globalEditMode is view-global state (Q1 ruling) -- switching tracks
 *    never resets it.
 *
 * Mock scaffolding mirrors WorkspacePage.correctionTrack.test.ts (all
 * composables except useLlmTasks / useListTrackSelector / useTrackEdit
 * mocked; useTrackEdit stays REAL -- it is the kernel under observation).
 * Fresh module graph per test via vi.resetModules.
 */
/* eslint-disable vue/one-component-per-file -- test stubs (translation host precedent) */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, ref, watch } from "vue"
import type { Project } from "@/types/project"
import { mockProject, mockTimeline, mockSegment } from "@/test/helpers/mockProject"

// ---------------------------------------------------------------------------
// Bridge mock: order-stamped call capture (update_track_segment = the flush
// kernel's backend submit) + captured event registrations
// ---------------------------------------------------------------------------
type EventHandler = (detail: unknown) => void
const eventHandlers = new Map<string, EventHandler[]>()
const orderLog: string[] = []
const callMock = vi.fn()

vi.mock("@/bridge", () => ({
  call: (...args: unknown[]) => callMock(...args),
  onEvent: (name: string, handler: EventHandler) => {
    const list = eventHandlers.get(name) ?? []
    list.push(handler)
    eventHandlers.set(name, list)
    return () => {}
  },
  isDemoMode: () => false,
}))

// ---------------------------------------------------------------------------
// Composable mocks (same shape as WorkspacePage.correctionTrack.test.ts;
// useTrackEdit deliberately NOT mocked -- real kernel under observation)
// ---------------------------------------------------------------------------
const showToastMock = vi.fn()

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
  useToast: () => ({ showToast: showToastMock, toasts: ref([]), removeToast: vi.fn() }),
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
// Stubs
// ---------------------------------------------------------------------------
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
// Fixtures / helpers
// ---------------------------------------------------------------------------
function projectWithTrack(): Project {
  return mockProject({
    timelines: [
      mockTimeline({
        id: "tl-1",
        transcript: {
          engine: "srt",
          language: "zh-CN",
          segments: [mockSegment({ id: "seg-1", start: 5, end: 8 })],
          tracks: [
            {
              id: "trk_x",
              role: "translation",
              name: "English",
              language: "en",
              segments: [mockSegment({ id: "tseg-1", start: 1.2, end: 3.4, text: "hello" })],
            },
          ],
          bindings: [],
        },
      }),
    ],
    active_timeline_id: "tl-1",
  })
}

async function mountWorkspacePage(): Promise<VueWrapper> {
  vi.resetModules()
  eventHandlers.clear()
  const { default: WorkspacePage } = await import("./WorkspacePage.vue")
  return mount(WorkspacePage, {
    props: { project: projectWithTrack() },
    global: {
      stubs: {
        Timeline: TimelineStub,
        SplitPanel: SplitPanelStub,
        ProgressBar: true,
        TimelineSwitcher: true,
        WaveformEditor: true,
        SearchReplaceBar: true,
        VideoControls: true,
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

function timelineStub(wrapper: VueWrapper) {
  return wrapper.findComponent(TimelineStub)
}

beforeEach(() => {
  callMock.mockReset()
  orderLog.length = 0
  showToastMock.mockReset()
  callMock.mockImplementation(async (method: string) => {
    if (method === "update_track_segment") orderLog.push("flush-commit")
    return { success: true, data: {} }
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe("WorkspacePage track edit sweep (M3-1)", () => {
  it("switching tracks flushes the pending draft BEFORE the view switches (no lost edits)", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()
    const stub = timelineStub(wrapper)

    // Enter the track view first (flush runs on an empty pendingMap).
    stub.vm.$emit("select-track", "trk_x")
    await flushPromises()
    expect(stub.props("activeTrackId")).toBe("trk_x")

    // Freeze the kernel's 300ms debounce: whatever commits below is
    // flush-driven, never timer-driven.
    vi.useFakeTimers()

    // A track-row text edit -> REAL useTrackEdit pendingMap entry.
    stub.vm.$emit("update-track-text", "trk_x", "tseg-1", "flushed draft")
    await vi.advanceTimersByTimeAsync(0)
    expect(orderLog).toEqual([]) // debounce still pending, nothing submitted

    // The view switch lands in the order log as it happens.
    const stop = watch(
      () => stub.props("activeTrackId"),
      (id) => { orderLog.push(`select-track:${id}`) },
    )

    // Switch back to the main view BEFORE the debounce fires.
    stub.vm.$emit("select-track", null)
    await vi.advanceTimersByTimeAsync(0)

    // Flush committed the old track's draft first, the view switched second.
    expect(orderLog).toEqual(["flush-commit", "select-track:null"])
    expect(callMock).toHaveBeenCalledWith(
      "update_track_segment",
      "trk_x",
      "tseg-1",
      { text: "flushed draft" },
    )
    expect(stub.props("activeTrackId")).toBeNull()
    vi.useRealTimers()
    stop()
    wrapper.unmount()
  })

  it("globalEditMode persists across track switches (Q1: the sweep is view-global)", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()
    const stub = timelineStub(wrapper)

    expect(stub.props("globalEditMode")).toBe(false)
    stub.vm.$emit("toggle-edit-mode")
    await flushPromises()
    expect(stub.props("globalEditMode")).toBe(true)

    // main -> track -> main: the mode never resets with the view.
    stub.vm.$emit("select-track", "trk_x")
    await flushPromises()
    expect(stub.props("activeTrackId")).toBe("trk_x")
    expect(stub.props("globalEditMode")).toBe(true)

    stub.vm.$emit("select-track", null)
    await flushPromises()
    expect(stub.props("activeTrackId")).toBeNull()
    expect(stub.props("globalEditMode")).toBe(true)
    wrapper.unmount()
  })
})

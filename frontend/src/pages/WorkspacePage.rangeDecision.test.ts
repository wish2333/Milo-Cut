/**
 * v3.0.4 M4-2 (P3-6): WorkspacePage halves of the range-marking gesture.
 *
 * Success path: WaveformEditor `range-decision` -> pushSnapshot(project,
 * ["edits"], "手动范围") BEFORE the bridge write (useWorkspaceActions.ts:652
 * precedent) -> call("add_range_decision", start, end, action) -> the
 * ProjectPatch envelope flows out through the standard project-updated
 * channel (App.vue applyProjectPatch path). Failure path: toast reports
 * 手动范围创建失败 and nothing is emitted. Wiring: the useSegmentEdit
 * `selectedRange` ref (activated dead code) travels down as the editor's
 * `rangeSelection` prop -- the bubble's staging sink.
 *
 * Mock scaffolding mirrors WorkspacePage.trackEdit.test.ts (all composables
 * except useLlmTasks / useListTrackSelector / useTrackEdit mocked; the
 * useSegmentEdit mock ADDS the selectedRange ref under observation).
 * Fresh module graph per test via vi.resetModules.
 */
/* eslint-disable vue/one-component-per-file -- test stubs (trackEdit host precedent) */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, ref } from "vue"
import type { Project } from "@/types/project"
import { mockProject, mockTimeline, mockSegment, mockEditDecision } from "@/test/helpers/mockProject"

// ---------------------------------------------------------------------------
// Bridge mock: order-stamped call capture + captured event registrations
// ---------------------------------------------------------------------------
type EventHandler = (detail: unknown) => void
const eventHandlers = new Map<string, EventHandler[]>()
const orderLog: string[] = []
const callMock = vi.fn()
const pushSnapshotMock = vi.fn()
const showToastMock = vi.fn()
/** The activated dead ref handed down as the editor's rangeSelection sink. */
const selectedRangeRef = ref<{ start: number; end: number } | null>(null)

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
// Composable mocks (same shape as WorkspacePage.trackEdit.test.ts; the
// useSegmentEdit mock adds selectedRange -- the M4-2 activation)
// ---------------------------------------------------------------------------
vi.mock("@/composables/useUndoRedo", () => ({
  useUndoRedo: () => ({
    pushSnapshot: pushSnapshotMock,
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
    selectedRange: selectedRangeRef,
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
const WaveformEditorStub = defineComponent({
  name: "WaveformEditor",
  props: { rangeSelection: { type: Object, default: null } },
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
// Fixtures / helpers
// ---------------------------------------------------------------------------
function projectFixture(): Project {
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
    props: { project: projectFixture() },
    global: {
      stubs: {
        Timeline: TimelineStub,
        SplitPanel: SplitPanelStub,
        ProgressBar: true,
        TimelineSwitcher: true,
        WaveformEditor: WaveformEditorStub,
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

beforeEach(() => {
  callMock.mockReset()
  pushSnapshotMock.mockReset()
  showToastMock.mockReset()
  orderLog.length = 0
  selectedRangeRef.value = null
  callMock.mockImplementation(async () => ({ success: true, data: {} }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe("WorkspacePage range decision (M4-2)", () => {
  it("range-decision: snapshots the edits layer BEFORE add_range_decision and streams the patch out via project-updated; selectedRange is wired down as rangeSelection", async () => {
    const patch = {
      revision: 7,
      edits: [
        mockEditDecision({
          id: "edit-manual-ab12cd34",
          start: 2,
          end: 6,
          action: "delete",
          source: "manual",
          status: "pending",
          target_type: "range",
          target_id: undefined,
        }),
      ],
    }
    pushSnapshotMock.mockImplementation(() => {
      orderLog.push("pushSnapshot")
    })
    callMock.mockImplementation(async (method: string) => {
      if (method === "add_range_decision") {
        orderLog.push("call:add_range_decision")
        return { success: true, data: patch }
      }
      return { success: true, data: {} }
    })
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    // Wiring: the activated useSegmentEdit ref IS the editor's bubble sink.
    const editor = wrapper.findComponent(WaveformEditorStub)
    expect(editor.exists()).toBe(true)
    expect(editor.props("rangeSelection")).toBe(selectedRangeRef)

    const before = (wrapper.emitted("project-updated") ?? []).length
    editor.vm.$emit("range-decision", { start: 2, end: 6, action: "delete" })
    await flushPromises()

    // Snapshot BEFORE the write, edits layer, 手动范围 label (P3-5 precedent).
    expect(pushSnapshotMock).toHaveBeenCalledTimes(1)
    expect(pushSnapshotMock).toHaveBeenCalledWith(expect.anything(), ["edits"], "手动范围")
    expect(callMock).toHaveBeenCalledWith("add_range_decision", 2, 6, "delete")
    expect(orderLog).toEqual(["pushSnapshot", "call:add_range_decision"])
    // The patch envelope leaves through the standard project-updated channel.
    const events = wrapper.emitted("project-updated") ?? []
    expect(events.length).toBe(before + 1)
    expect(events[events.length - 1]).toEqual([patch])
    wrapper.unmount()
  })

  it("failure branch: toast reports 手动范围创建失败 with the backend error and nothing is emitted", async () => {
    callMock.mockImplementation(async (method: string) => {
      if (method === "add_range_decision") return { success: false, error: "Invalid range" }
      return { success: true, data: {} }
    })
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    const editor = wrapper.findComponent(WaveformEditorStub)
    const before = (wrapper.emitted("project-updated") ?? []).length
    editor.vm.$emit("range-decision", { start: 6, end: 2, action: "keep" })
    await flushPromises()

    expect(callMock).toHaveBeenCalledWith("add_range_decision", 6, 2, "keep")
    expect(showToastMock).toHaveBeenCalledTimes(1)
    expect(showToastMock).toHaveBeenCalledWith("手动范围创建失败: Invalid range", "error", 3000)
    expect((wrapper.emitted("project-updated") ?? []).length).toBe(before)
    wrapper.unmount()
  })
})

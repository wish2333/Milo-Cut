/**
 * v3.0.4 M2-4 C/D: WorkspacePage correction track wiring + review badge.
 *
 * C: the deps literal passed to createWorkspaceActions is the page's call
 *    site for startSubtitleCorrection -- it wraps the useLlmTasks function
 *    so the VIEWED track id (activeListTrackId ?? "") rides through as the
 *    backend's 4th positional arg (P2-2 signature). useWorkspaceActions
 *    itself is P2-4-frozen, so it is mocked here purely to CAPTURE the deps
 *    object; driving deps.startSubtitleCorrection exercises the real page
 *    wrapper + the real useLlmTasks singleton end to end.
 * D: the review modal badges track-scoped entries with the source track
 *    name and consumes the backend-resolved scope values as-is.
 *
 * Mock scaffolding mirrors WorkspacePage.translation.test.ts (all
 * composables except useLlmTasks / useListTrackSelector mocked; fresh
 * module graph per test via vi.resetModules).
 */
/* eslint-disable vue/one-component-per-file -- test stubs (translation host precedent) */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, ref } from "vue"
import type { Project } from "@/types/project"
import { mockProject, mockTimeline, mockSegment } from "@/test/helpers/mockProject"
import { formatTimeShort } from "@/utils/format"

// ---------------------------------------------------------------------------
// Bridge mock: configurable call + captured event registrations
// ---------------------------------------------------------------------------
type EventHandler = (detail: unknown) => void
const eventHandlers = new Map<string, EventHandler[]>()
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
// Composable mocks (same shape as WorkspacePage.translation.test.ts)
// ---------------------------------------------------------------------------
const flushPendingTrackUpdatesMock = vi.fn(async () => {})
const showToastMock = vi.fn()

// v3.0.4 M2-4 C: capture the deps literal instead of discarding it -- the
// wrapper under test lives THERE (the hub itself is frozen by red line).
const capturedDeps: { current: Record<string, unknown> | null } = { current: null }

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

vi.mock("@/composables/useTrackEdit", () => ({
  useTrackEdit: () => ({
    updateTrackSegmentTime: vi.fn(),
    editTrackSegmentText: vi.fn(),
    editTrackSegmentTime: vi.fn(),
    flushPendingTrackUpdates: flushPendingTrackUpdatesMock,
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
  // Frozen by red line (P2-4 delivered): capture the deps literal, then
  // behave exactly like the translation host's Proxy stub.
  createWorkspaceActions: (deps: Record<string, unknown>) => {
    capturedDeps.current = deps
    return new Proxy({}, { get: () => vi.fn() }) as Record<string, ReturnType<typeof vi.fn>>
  },
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
    mainSegments: { type: Array, default: () => [] },
  },
  emits: ["select-track"],
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
  capturedDeps.current = null
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

function pageDeps(): Record<string, unknown> {
  expect(capturedDeps.current).not.toBeNull()
  return capturedDeps.current!
}

function timelineStub(wrapper: VueWrapper) {
  return wrapper.findComponent(TimelineStub)
}

// Review entry shape as returned by get_subtitle_corrections (P2-3): the
// useLlmTasks SubtitleCorrection type predates track_id/track_name, so the
// extra fields ride as an explicit local type (same reading the modal does).
interface ReviewEntry {
  id: string
  segment_id: string
  confidence: number
  original_text: string
  corrected_text: string
  changes: string[]
  category: string
  start: number
  end: number
  track_id?: string
  track_name?: string
}

beforeEach(() => {
  callMock.mockReset()
  flushPendingTrackUpdatesMock.mockReset()
  showToastMock.mockReset()
  callMock.mockResolvedValue({ success: true, data: {} })
})

describe("WorkspacePage correction track wiring (M2-4 C)", () => {
  it("deps.startSubtitleCorrection forwards the viewed track id as the 4th bridge arg", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    // Main-track view: "" = main track (v3.0.3 call semantics preserved).
    await (pageDeps().startSubtitleCorrection as (t: string) => Promise<unknown>)("ref-main")
    expect(callMock).toHaveBeenCalledWith("start_subtitle_correction", "ref-main", "", 3, "")
    callMock.mockClear()

    // Switch the list to the extension track via the Timeline stub, then
    // start again: the SAME wrapper now carries the viewed track id.
    timelineStub(wrapper).vm.$emit("select-track", "trk_x")
    await flushPromises()
    expect(timelineStub(wrapper).props("activeTrackId")).toBe("trk_x")

    await (pageDeps().startSubtitleCorrection as (t: string) => Promise<unknown>)("ref-track")
    expect(callMock).toHaveBeenCalledWith("start_subtitle_correction", "ref-track", "", 3, "trk_x")
    wrapper.unmount()
  })
})

describe("WorkspacePage correction review modal (M2-4 D)", () => {
  it("badges track-scoped entries with the source track name; main-track entries get none", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    // Same singleton the page uses (module graph is shared after mount).
    const { useLlmTasks } = await import("@/composables/useLlmTasks")
    const tasks = useLlmTasks()
    const entries: ReviewEntry[] = [
      {
        id: "c-track", segment_id: "tseg-1", confidence: 0.9,
        original_text: "hello", corrected_text: "Hello!", changes: ["case"],
        category: "typo", start: 1.2, end: 3.4,
        track_id: "trk_x", track_name: "English",
      },
      {
        id: "c-main", segment_id: "seg-1", confidence: 0.5,
        original_text: "x", corrected_text: "y", changes: ["typo"],
        category: "typo", start: 5, end: 8,
        track_id: "", track_name: "",
      },
    ]
    tasks.pendingCorrections.value = entries

    // Open the fullscreen review modal through the page's own ref (the
    // hub handler is mocked away; the modal reads this exact ref).
    ;(pageDeps().showSubtitleFullscreen as { value: boolean }).value = true
    await flushPromises()

    // Exactly one badge -- the track-scoped entry; "" = main track, none.
    const badges = wrapper.findAll('[data-test="correction-track-badge"]')
    expect(badges).toHaveLength(1)
    expect(badges[0].text()).toBe("来源轨：English")

    // Display side consumes the backend scope-resolved values as-is: the
    // track entry shows its own (track-resolved) time, the main one its own.
    expect(wrapper.text()).toContain(formatTimeShort(1.2))
    expect(wrapper.text()).toContain(formatTimeShort(5))
    // Both entries are listed (1 high-confidence + 1 low-confidence).
    expect(wrapper.text()).toContain("共 2 条")
    wrapper.unmount()
  })

  it("renders no badge at all when every entry is main-track scoped", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    const { useLlmTasks } = await import("@/composables/useLlmTasks")
    const entries: ReviewEntry[] = [
      {
        id: "c-main", segment_id: "seg-1", confidence: 0.9,
        original_text: "x", corrected_text: "y", changes: [],
        category: "typo", start: 5, end: 8,
        track_id: "", track_name: "",
      },
    ]
    useLlmTasks().pendingCorrections.value = entries

    ;(pageDeps().showSubtitleFullscreen as { value: boolean }).value = true
    await flushPromises()

    expect(wrapper.findAll('[data-test="correction-track-badge"]')).toHaveLength(0)
    expect(wrapper.text()).toContain("共 1 条")
    wrapper.unmount()
  })
})

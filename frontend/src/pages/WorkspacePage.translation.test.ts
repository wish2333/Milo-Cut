/**
 * v3.0.4 M1-6: WorkspacePage translation closed-loop tests.
 *
 * Covers the two page-level halves of the loop:
 *   1. start-translation -> pushSnapshot(["tracks","bindings"], "AI翻译副轨")
 *      BEFORE start_translation, then the remembered-language write-back via
 *      update_settings (snapshot ordering asserted through call order).
 *   2. EVENT_LLM_TRANSLATION_COMPLETED -> singleton lastTranslationCompletion
 *      -> watch -> handleSelectListTrack (flush-first) -> the Timeline stub
 *      receives the new track id; uncovered ids surface as toast + notice.
 *
 * The page pulls in nearly every composable, so all of them except useLlmTasks
 * (real, bridge-mocked) and useListTrackSelector (pure) are mocked. useLlmTasks
 * holds module-level singleton state, so each test re-imports a fresh module
 * graph via vi.resetModules + dynamic import.
 */
/* eslint-disable vue/one-component-per-file -- test stubs (VideoControls.test.ts precedent) */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { mount, flushPromises, type VueWrapper } from "@vue/test-utils"
import { defineComponent, ref } from "vue"
import type { Project } from "@/types/project"
import { mockProject, mockTimeline, mockSegment } from "@/test/helpers/mockProject"
import { EVENT_LLM_TRANSLATION_COMPLETED } from "@/utils/events"

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
// Composable mocks (fresh vi.fn per module graph, stable module-level refs)
// ---------------------------------------------------------------------------
const pushSnapshotMock = vi.fn()
const flushPendingTrackUpdatesMock = vi.fn(async () => {})
const showToastMock = vi.fn()

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
  // Every destructured action becomes a no-op vi.fn via the Proxy; the page
  // only re-exposes them, and these tests never invoke them directly.
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
    mainSegments: { type: Array, default: () => [] },
    translationNotice: { type: Object, default: null },
  },
  emits: ["start-translation", "select-track"],
  template: "<div data-test='timeline-stub'></div>",
})

const SplitPanelStub = defineComponent({
  name: "SplitPanel",
  template: "<div><slot name='left' /><slot name='right' /></div>",
})

// ---------------------------------------------------------------------------
// Fixtures / helpers
// ---------------------------------------------------------------------------
function projectWithTranslationTrack(): Project {
  return mockProject({
    timelines: [
      mockTimeline({
        id: "tl-1",
        transcript: {
          engine: "srt",
          language: "zh-CN",
          segments: [mockSegment({ id: "seg-1" }), mockSegment({ id: "seg-2" })],
          tracks: [
            {
              id: "trk_main",
              role: "translation",
              name: "Placeholder",
              language: "en",
              segments: [],
            },
            {
              id: "trk_x",
              role: "translation",
              name: "English",
              language: "en",
              segments: [mockSegment({ id: "tseg-1", text: "hello" })],
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
    props: { project: projectWithTranslationTrack() },
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
      },
    },
  })
}

function fire(name: string, detail: unknown) {
  for (const h of eventHandlers.get(name) ?? []) h(detail)
}

function timelineStub(wrapper: VueWrapper) {
  return wrapper.findComponent(TimelineStub)
}

// The page's llmConfig gates the start path; make the bridge report a
// configured LLM (get_llm_config) and succeed for everything else by default.
function bridgeConfiguredLlm() {
  callMock.mockImplementation(async (method: string) => {
    if (method === "get_llm_config") {
      return {
        success: true,
        data: { model: "test-model", base_url: "http://localhost", api_key_masked: "sk-***" },
      }
    }
    return { success: true, data: {} }
  })
}

beforeEach(() => {
  callMock.mockReset()
  pushSnapshotMock.mockReset()
  flushPendingTrackUpdatesMock.mockReset()
  showToastMock.mockReset()
  bridgeConfiguredLlm()
})

describe("WorkspacePage translation closed loop (M1-6)", () => {
  it("start-translation: snapshot BEFORE start_translation, then settings write-back", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    // loadLlmConfig is deferred to browser idle time inside onMounted
    // (requestIdleCallback / 50ms timeout fallback) -- flushPromises alone
    // never reaches it, so settle one idle tick before driving the start.
    await new Promise((r) => setTimeout(r, 120))
    await flushPromises()

    expect(timelineStub(wrapper).props("mainSegments")).toHaveLength(2)

    timelineStub(wrapper).vm.$emit("start-translation", { targetLanguage: "ja" })
    await flushPromises()

    // Undo snapshot: layered tracks+bindings capture taken before the task
    // starts (PRD R1.4 -- writes land on the background thread later).
    expect(pushSnapshotMock).toHaveBeenCalledTimes(1)
    expect(pushSnapshotMock).toHaveBeenCalledWith(
      projectWithTranslationTrack(),
      ["tracks", "bindings"],
      "AI翻译副轨",
    )

    expect(callMock).toHaveBeenCalledWith("start_translation", "ja")
    // Remembered-language write-back only happens after a successful start.
    expect(callMock).toHaveBeenCalledWith("update_settings", {
      llm_translation_target_language: "ja",
    })

    const startCall = callMock.mock.calls.find((c) => c[0] === "start_translation")
    expect(startCall).toBeDefined()
    expect(pushSnapshotMock.mock.invocationCallOrder[0]).toBeLessThan(
      callMock.mock.invocationCallOrder[callMock.mock.calls.indexOf(startCall!)],
    )
    expect(showToastMock).toHaveBeenCalledWith("翻译已启动", "info", 2000)
    wrapper.unmount()
  })

  it("completion event: switches the list to the new track with flush-first semantics", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    // Main track selected before completion.
    expect(timelineStub(wrapper).props("activeTrackId")).toBeNull()

    fire(EVENT_LLM_TRANSLATION_COMPLETED, {
      track_id: "trk_x",
      track_name: "English",
      language: "en",
      written_count: 2,
      target_count: 2,
      uncovered_ids: [],
      ledger: { uncovered_segment_ids: [] },
    })
    await flushPromises()

    // watch -> handleSelectListTrack -> (flush) -> selectTrack(trk_x)
    expect(flushPendingTrackUpdatesMock).toHaveBeenCalled()
    expect(timelineStub(wrapper).props("activeTrackId")).toBe("trk_x")
    expect(timelineStub(wrapper).props("activeTrackName")).toBe("English")
    expect(timelineStub(wrapper).props("translationNotice")).toBeNull()
    expect(showToastMock).toHaveBeenCalledWith(
      expect.stringContaining("已切换到译文轨"),
      "success",
      3000,
    )
    wrapper.unmount()
  })

  it("completion with uncovered ids: toast + panel notice carry the list", async () => {
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    fire(EVENT_LLM_TRANSLATION_COMPLETED, {
      track_id: "trk_x",
      track_name: "English",
      language: "en",
      written_count: 1,
      target_count: 2,
      uncovered_ids: ["seg-1", "seg-2"],
      ledger: { uncovered_segment_ids: ["seg-1", "seg-2"] },
    })
    await flushPromises()

    expect(timelineStub(wrapper).props("activeTrackId")).toBe("trk_x")
    expect(timelineStub(wrapper).props("translationNotice")).toEqual({
      trackName: "English",
      language: "en",
      uncoveredIds: ["seg-1", "seg-2"],
    })
    expect(showToastMock).toHaveBeenCalledWith(
      expect.stringContaining("2 段未覆盖"),
      "error",
      5000,
    )
    wrapper.unmount()
  })

  it("does not start when the LLM is not configured (no snapshot, no task)", async () => {
    callMock.mockImplementation(async () => ({ success: true, data: {} }))
    const wrapper = await mountWorkspacePage()
    await flushPromises()

    timelineStub(wrapper).vm.$emit("start-translation", { targetLanguage: "en" })
    await flushPromises()

    expect(pushSnapshotMock).not.toHaveBeenCalled()
    expect(callMock).not.toHaveBeenCalledWith("start_translation", "en")
    expect(showToastMock).toHaveBeenCalledWith("请先配置 LLM", "error", 3000)
    wrapper.unmount()
  })
})

/**
 * v3.0.2 M1-3 (S3/R3.4): undo capture-layer integration through the REAL
 * call sites (no hand-built UndoRecords).
 *
 * Wiring mirrors WorkspacePage/App.vue exactly: the shared project ref is
 * a writable computed whose setter emits upward -- App.vue applies the
 * ProjectPatch envelope via applyProjectResponse and notes the revision.
 * useSegmentEdit / useEdit push pre-snapshots through useUndoRedo.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { computed, ref, type Ref } from "vue"
import type { Project, ProjectResponse, Segment } from "@/types/project"
import { applyProjectResponse } from "@/utils/projectPatch"
import { lastSeenRevision, noteRevision } from "@/utils/revision"
import { useSegmentEdit } from "./useSegmentEdit"
import { useEdit } from "./useEdit"
import { useUndoRedo } from "./useUndoRedo"
import { mockProject, mockSegment } from "@/test/helpers/mockProject"

vi.mock("@/bridge", () => ({
  call: vi.fn(),
}))

import { call } from "@/bridge"
const mockCall = vi.mocked(call)

function makeExt(id: string, start: number, end: number, text: string): Segment {
  return mockSegment({ id, start, end, text })
}

function buildProject(): Project {
  const base = mockProject()
  return {
    ...base,
    timelines: [
      {
        ...base.timelines[0],
        transcript: {
          ...base.timelines[0].transcript,
          segments: [
            mockSegment({ id: "s1", start: 0, end: 5 }),
            mockSegment({ id: "s2", start: 10, end: 15 }),
          ],
          tracks: [
            {
              id: "trk1",
              role: "extension",
              name: "en",
              language: "en",
              segments: [
                makeExt("trk1_a", 0.2, 4.8, "en-1"),
                makeExt("trk1_b", 10.2, 14.8, "en-2"),
              ],
            },
          ],
          bindings: [
            {
              id: "bind_a",
              track_id: "trk1",
              main_segment_id: "s1",
              extension_segment_id: "trk1_a",
              start_offset: 0.2,
              end_offset: -0.2,
            },
            {
              id: "bind_b",
              track_id: "trk1",
              main_segment_id: "s2",
              extension_segment_id: "trk1_b",
              start_offset: 0.2,
              end_offset: -0.2,
            },
          ],
        },
      },
    ],
  }
}

/** Post-edit payload the mocked backend reports for the s1 trim. */
function s1TrimPatch(revision: number): ProjectResponse {
  return {
    revision,
    segments: [
      mockSegment({ id: "s1", start: 1.0, end: 5 }),
      mockSegment({ id: "s2", start: 10, end: 15 }),
    ],
    tracks: [
      {
        id: "trk1",
        role: "extension",
        name: "en",
        language: "en",
        segments: [
          makeExt("trk1_a", 1.2, 4.8, "en-1"), // followed the trim
          makeExt("trk1_b", 10.2, 14.8, "en-2"),
        ],
      },
    ],
    bindings: [
      {
        id: "bind_a",
        track_id: "trk1",
        main_segment_id: "s1",
        extension_segment_id: "trk1_a",
        start_offset: 0.2,
        end_offset: -0.2,
      },
      {
        id: "bind_b",
        track_id: "trk1",
        main_segment_id: "s2",
        extension_segment_id: "trk1_b",
        start_offset: 0.2,
        end_offset: -0.2,
      },
    ],
    meta: { linkage: { squeezed: 0, removed: 0, unbound: 0 } },
  }
}

function mainStateOf(p: Project) {
  const tl = p.timelines.find(t => t.id === p.active_timeline_id)!
  return {
    segments: tl.transcript.segments,
    tracks: tl.transcript.tracks ?? [],
    bindings: tl.transcript.bindings ?? [],
  }
}

describe("undo capture layers through real call sites (S3/R3.4)", () => {
  let backing: Ref<Project>
  // WorkspacePage's projectRef twin: set() emits upward, App.vue applies
  // patch-or-project and notes the revision. Writes accept the raw bridge
  // envelope (patch or full project), reads yield Project.
  let project: Ref<Project, ProjectResponse>
  let history: ReturnType<typeof useUndoRedo>
  let revisions: number[]

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.clearAllTimers()
    lastSeenRevision.value = 1
    backing = ref(buildProject())
    revisions = []
    // WritableComputedRef<Project, ProjectResponse>: reads are Project,
    // writes accept the raw bridge envelope (patch or full project).
    project = computed<Project, ProjectResponse>({
      get: () => backing.value,
      set: (val) => {
        backing.value = applyProjectResponse(backing.value, val)
        if (typeof (val as { revision?: unknown }).revision === "number") {
          noteRevision((val as { revision: number }).revision)
        }
        revisions.push((val as { revision?: number }).revision ?? -1)
      },
    })
    history = useUndoRedo()
  })

  /** Simulated backend: apply_undo echoes the restored layers at rev+1. */
  function mockApplyUndo() {
    mockCall.mockImplementation(async (method: string, ...args: unknown[]) => {
      if (method === "apply_undo") {
        const [records, baseRev] = args as [Record<string, unknown>, number]
        if (baseRev < lastSeenRevision.value) {
          return { success: false, error: "stale" }
        }
        const next = baseRev + 1
        noteRevision(next)
        return { success: true, data: { revision: next, ...records } }
      }
      throw new Error(`unexpected bridge call in test: ${method}`)
    })
  }

  function lastCapture(): Record<string, unknown> {
    return history.undoStack.value[history.undoStack.value.length - 1].records
  }

  it("bound-segment trim captures three layers, undo rolls all back, redo is symmetric", async () => {
    const edit = useSegmentEdit(project, (resp) => {
      project.value = resp
    }, (p, layers, label) => history.pushSnapshot(p, layers, label ?? ""))

    // Backend reply for the debounced trim (patch envelope, revision 2).
    mockCall.mockResolvedValue({ success: true, data: s1TrimPatch(2) })

    edit.updateSegmentTime("s1", "start", 1.0)
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(mockCall).toHaveBeenCalledWith("update_segment", "s1", { start: 1.0 })
    expect(mainStateOf(project.value).segments[0].start).toBe(1.0)
    expect(mainStateOf(project.value).tracks[0].segments[0].start).toBe(1.2)

    // The captured record holds exactly the mapped layers.
    expect(Object.keys(lastCapture()).sort()).toEqual(["bindings", "segments", "tracks"])

    // -- undo: all three layers roll back atomically -----------------------
    mockApplyUndo()
    const undoRes = await history.undo(project.value)
    expect(undoRes.ok).toBe(true)
    project.value = undoRes.patch!
    const restored = mainStateOf(project.value)
    expect(restored.segments[0].start).toBe(0)
    expect(restored.tracks[0].segments[0].start).toBe(0.2)
    expect(restored.bindings[0].start_offset).toBe(0.2)
    // No stale patch: apply_undo got the freshest revision as base.
    expect(mockCall).toHaveBeenLastCalledWith(
      "apply_undo",
      expect.objectContaining({
        segments: expect.anything(),
        tracks: expect.anything(),
        bindings: expect.anything(),
      }),
      2,
    )

    // -- redo: symmetric, three layers forward again -----------------------
    const redoRes = await history.redo(project.value)
    expect(redoRes.ok).toBe(true)
    project.value = redoRes.patch!
    const redone = mainStateOf(project.value)
    expect(redone.segments[0].start).toBe(1.0)
    expect(redone.tracks[0].segments[0].start).toBe(1.2)

    // Revision strictly increases across edit -> undo -> redo. (The
    // leading -1 is the optimistic full-Project apply: no revision yet.)
    expect(revisions).toEqual([-1, 2, 3, 4])
    expect(lastSeenRevision.value).toBe(4)
  })

  it("unbound-segment trim keeps the single segments layer", async () => {
    const p = buildProject()
    p.timelines[0].transcript.bindings = p.timelines[0].transcript.bindings!.filter(
      b => b.main_segment_id !== "s1",
    )
    backing.value = p

    const edit = useSegmentEdit(project, (resp) => {
      project.value = resp
    }, (pp, layers, label) => history.pushSnapshot(pp, layers, label ?? ""))

    mockCall.mockResolvedValue({
      success: true,
      data: { revision: 2, segments: [mockSegment({ id: "s1", start: 1, end: 5 })] },
    })

    edit.updateSegmentTime("s1", "start", 1.0)
    vi.advanceTimersByTime(300)
    await Promise.resolve()

    expect(Object.keys(lastCapture())).toEqual(["segments"])
  })

  it("useEdit.splitSegment captures four layers only when the target is bound", async () => {
    const editApi = useEdit(project, (p, layers, label) => history.pushSnapshot(p, layers, label ?? ""))

    const splitPatch = (revision: number): ProjectResponse => ({
      revision,
      segments: [
        mockSegment({ id: "s1", start: 0, end: 2 }),
        mockSegment({ id: "s1-split", start: 2, end: 5 }),
        mockSegment({ id: "s2", start: 10, end: 15 }),
      ],
      edits: [],
      tracks: mainStateOf(project.value).tracks,
      bindings: mainStateOf(project.value).bindings,
      meta: { linkage: { split: 1, rebound: 1, unbound: 0 } },
    })
    mockCall.mockResolvedValue({ success: true, data: splitPatch(2) } as never)

    await editApi.splitSegment("s1", 2.0) // bound target -> linked split
    expect(Object.keys(lastCapture()).sort()).toEqual([
      "bindings",
      "edits",
      "segments",
      "tracks",
    ])

    // Unbound target keeps the legacy two-layer capture: strip s2's
    // binding from the working state, then split it.
    backing.value = buildProject()
    backing.value.timelines[0].transcript.bindings = backing.value.timelines[0].transcript.bindings!.filter(
      b => b.main_segment_id !== "s2",
    )
    mockCall.mockResolvedValue({ success: true, data: splitPatch(3) } as never)
    await editApi.splitSegment("s2", 12.0)
    expect(Object.keys(lastCapture()).sort()).toEqual(["edits", "segments"])
  })

  it("useEdit.deleteSegment captures four layers only when the deletion cascades", async () => {
    const editApi = useEdit(project, (p, layers, label) => history.pushSnapshot(p, layers, label ?? ""))

    const deletePatch = (revision: number, dropBound: boolean): ProjectResponse => ({
      revision,
      segments: dropBound
        ? [mockSegment({ id: "s2", start: 10, end: 15 })]
        : [mockSegment({ id: "s1", start: 0, end: 5 })],
      edits: [],
      tracks: [
        {
          id: "trk1",
          role: "extension",
          name: "en",
          language: "en",
          segments: dropBound
            ? [makeExt("trk1_b", 10.2, 14.8, "en-2")] // paired ext removed
            : [makeExt("trk1_a", 0.2, 4.8, "en-1")],
        },
      ],
      bindings: dropBound
        ? [
            {
              id: "bind_b",
              track_id: "trk1",
              main_segment_id: "s2",
              extension_segment_id: "trk1_b",
              start_offset: 0.2,
              end_offset: -0.2,
            },
          ]
        : [
            {
              id: "bind_a",
              track_id: "trk1",
              main_segment_id: "s1",
              extension_segment_id: "trk1_a",
              start_offset: 0.2,
              end_offset: -0.2,
            },
          ],
      meta: dropBound ? { linkage: { removed: 1, unbound: 1 } } : undefined,
    })
    mockCall.mockResolvedValue({ success: true, data: deletePatch(2, true) } as never)

    await editApi.deleteSegment("s1") // bound -> paired cascade
    expect(Object.keys(lastCapture()).sort()).toEqual([
      "bindings",
      "edits",
      "segments",
      "tracks",
    ])

    // After the cascade the s2 chain is what remains; deleting s1 again in
    // a state where it has no binding must keep the legacy two-layer
    // capture (predicate evaluated on pre-call state).
    backing.value = buildProject()
    backing.value.timelines[0].transcript.bindings = []
    mockCall.mockResolvedValue({ success: true, data: deletePatch(3, false) } as never)
    await editApi.deleteSegment("s1")
    expect(Object.keys(lastCapture()).sort()).toEqual(["edits", "segments"])
  })
})

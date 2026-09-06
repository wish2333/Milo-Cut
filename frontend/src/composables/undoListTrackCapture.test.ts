/**
 * v3.0.3 M1-4: undo capture-layer predicate table for the SUBTITLE-LIST
 * track entries, through the REAL undo chain (no hand-built records).
 *
 * PRD R1.5 裁决表:
 * | 列表文本编辑（text）   | 恒真         | ["tracks"]            |
 * | 列表时间编辑（有绑定） | 绑定谓词命中 | ["tracks","bindings"] |
 * | 列表时间编辑（无绑定） | 绑定谓词未中 | ["tracks"]            |
 * | 删除此条字幕           | 恒真         | ["tracks","bindings"] | (3.0.2 既有
 *   handleDeleteTrackSegment 捕获，列表侧仅接线 —— Timeline.test.ts 覆盖)
 *
 * Wiring mirrors undoLinkageCapture.test.ts (WorkspacePage/App.vue twins):
 * writable computed project, useUndoRedo snapshots, apply_undo echoes the
 * restored layers at rev+1.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { computed, ref, type Ref } from "vue"
import type { Project, ProjectResponse, Segment } from "@/types/project"
import { applyProjectResponse } from "@/utils/projectPatch"
import { lastSeenRevision, noteRevision } from "@/utils/revision"
import { useTrackEdit } from "./useTrackEdit"
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
          segments: [mockSegment({ id: "s1", start: 0, end: 5 })],
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
          ],
        },
      },
    ],
  }
}

function trackStateOf(p: Project) {
  const tl = p.timelines.find(t => t.id === p.active_timeline_id)!
  return {
    track: tl.transcript.tracks![0],
    bindings: tl.transcript.bindings ?? [],
  }
}

describe("list track edits: undo predicate table through the real chain (M1-4)", () => {
  let backing: Ref<Project>
  let project: Ref<Project, ProjectResponse>
  let history: ReturnType<typeof useUndoRedo>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.clearAllTimers()
    lastSeenRevision.value = 1
    backing = ref(buildProject())
    project = computed<Project, ProjectResponse>({
      get: () => backing.value,
      set: (val) => {
        backing.value = applyProjectResponse(backing.value, val)
        if (typeof (val as { revision?: unknown }).revision === "number") {
          noteRevision((val as { revision: number }).revision)
        }
      },
    })
    history = useUndoRedo()
  })

  function makeEdit() {
    return useTrackEdit(project, (resp) => {
      project.value = resp
    }, (p, layers, label) => history.pushSnapshot(p, layers, label ?? ""))
  }

  function lastCapture(): Record<string, unknown> {
    return history.undoStack.value[history.undoStack.value.length - 1].records
  }

  function mockApplyUndo() {
    mockCall.mockImplementation(async (method: string, ...args: unknown[]) => {
      if (method === "apply_undo") {
        const [records, baseRev] = args as [Record<string, unknown>, number]
        if (baseRev < lastSeenRevision.value) return { success: false, error: "stale" }
        const next = baseRev + 1
        noteRevision(next)
        return { success: true, data: { revision: next, ...records } }
      }
      throw new Error(`unexpected bridge call in test: ${method}`)
    })
  }

  it("row 1: list TEXT edit always captures ['tracks'] (undo/redo symmetric)", async () => {
    const edit = makeEdit()
    // Backend echo: text commit at revision 2.
    mockCall.mockResolvedValue({
      success: true,
      data: {
        revision: 2,
        tracks: [
          { ...trackStateOf(project.value).track, segments: [makeExt("trk1_a", 0.2, 4.8, "HELLO"), makeExt("trk1_b", 10.2, 14.8, "en-2")] },
        ],
      } as unknown as ProjectResponse,
    })

    edit.editTrackSegmentText("trk1", "trk1_a", "HELLO")
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(mockCall).toHaveBeenCalledWith("update_track_segment", "trk1", "trk1_a", { text: "HELLO" })
    expect(trackStateOf(project.value).track.segments[0].text).toBe("HELLO")

    // The bound segment's text edit captured NO bindings layer (text never
    // triggers a rebuild downstream).
    expect(Object.keys(lastCapture()).sort()).toEqual(["tracks"])

    mockApplyUndo()
    const undoRes = await history.undo(project.value)
    expect(undoRes.ok).toBe(true)
    project.value = undoRes.patch!
    expect(trackStateOf(project.value).track.segments[0].text).toBe("en-1")

    const redoRes = await history.redo(project.value)
    expect(redoRes.ok).toBe(true)
    project.value = redoRes.patch!
    expect(trackStateOf(project.value).track.segments[0].text).toBe("HELLO")
  })

  it("row 2: list TIME edit on a BOUND segment captures ['tracks','bindings'] with offsets restore", async () => {
    const edit = makeEdit()
    // Backend reply: offsets rebuilt wholesale after the time change.
    mockCall.mockResolvedValue({
      success: true,
      data: {
        revision: 2,
        tracks: [
          { ...trackStateOf(project.value).track, segments: [makeExt("trk1_a", 1.0, 4.8, "en-1"), makeExt("trk1_b", 10.2, 14.8, "en-2")] },
        ],
        bindings: [
          { id: "bind_a", track_id: "trk1", main_segment_id: "s1", extension_segment_id: "trk1_a", start_offset: 0.0, end_offset: -0.2 },
        ],
      } as unknown as ProjectResponse,
    })

    edit.editTrackSegmentTime("trk1", "trk1_a", "start", 1.0, undefined)
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    const after = trackStateOf(project.value)
    expect(after.track.segments[0].start).toBe(1.0)
    expect(after.bindings[0].start_offset).toBe(0.0) // backend rebuilt

    expect(Object.keys(lastCapture()).sort()).toEqual(["bindings", "tracks"])

    // -- undo: tracks AND bindings roll back atomically (offsets restored) --
    mockApplyUndo()
    const undoRes = await history.undo(project.value)
    expect(undoRes.ok).toBe(true)
    project.value = undoRes.patch!
    const restored = trackStateOf(project.value)
    expect(restored.track.segments[0].start).toBe(0.2)
    expect(restored.bindings[0].start_offset).toBe(0.2) // pre-edit offset

    // -- redo: symmetric ---------------------------------------------------
    const redoRes = await history.redo(project.value)
    expect(redoRes.ok).toBe(true)
    project.value = redoRes.patch!
    const redone = trackStateOf(project.value)
    expect(redone.track.segments[0].start).toBe(1.0)
    expect(redone.bindings[0].start_offset).toBe(0.0)
  })

  it("row 3: list TIME edit on an UNBOUND segment captures ['tracks'] only", async () => {
    const p = buildProject()
    p.timelines[0].transcript.bindings = []
    backing.value = p

    const edit = makeEdit()
    mockCall.mockResolvedValue({
      success: true,
      data: {
        revision: 2,
        tracks: [
          { ...trackStateOf(project.value).track, segments: [makeExt("trk1_a", 0.2, 5.5, "en-1"), makeExt("trk1_b", 10.2, 14.8, "en-2")] },
        ],
      } as unknown as ProjectResponse,
    })

    edit.editTrackSegmentTime("trk1", "trk1_a", "end", 5.5, undefined)
    vi.advanceTimersByTime(300)
    await Promise.resolve()
    expect(trackStateOf(project.value).track.segments[0].end).toBe(5.5)
    expect(Object.keys(lastCapture()).sort()).toEqual(["tracks"])

    mockApplyUndo()
    const undoRes = await history.undo(project.value)
    expect(undoRes.ok).toBe(true)
    project.value = undoRes.patch!
    expect(trackStateOf(project.value).track.segments[0].end).toBe(4.8)

    const redoRes = await history.redo(project.value)
    expect(redoRes.ok).toBe(true)
    project.value = redoRes.patch!
    expect(trackStateOf(project.value).track.segments[0].end).toBe(5.5)
  })
})

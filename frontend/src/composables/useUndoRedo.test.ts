/**
 * v3.0.0 M5 layered undo tests (rewritten from the v2.3.2 full-snapshot
 * contract). Undo/redo go through the mocked "apply_undo" bridge call;
 * the backend owns the revision counter (mirrored here by the demoBridge
 * semantics: stale base_revision -> failure envelope).
 */
import { describe, expect, it, vi, beforeEach } from "vitest"
import { useUndoRedo } from "@/composables/useUndoRedo"
import { lastSeenRevision, noteRevision } from "@/utils/revision"
import type { Project, ProjectPatch, Segment } from "@/types/project"

// Mock the bridge module: capture apply_undo calls, respond with a patch.
const applyUndoCalls: Array<{ layers: unknown; baseRevision: number }> = []
let applyUndoResult: { success: boolean; data?: ProjectPatch; error?: string } = {
  success: true,
  data: { revision: 1 },
}

vi.mock("@/bridge", () => ({
  call: vi.fn(async (method: string, ...args: unknown[]) => {
    if (method === "apply_undo") {
      applyUndoCalls.push({
        layers: args[0],
        baseRevision: args[1] as number,
      })
      return applyUndoResult
    }
    return { success: false, error: `unexpected method ${method}` }
  }),
}))

function makeSegment(i: number): Segment {
  return {
    id: `seg-${i}`,
    version: 1,
    type: "subtitle",
    start: i * 10,
    end: i * 10 + 5,
    text: `segment ${i}`,
    speaker: "",
  }
}

function makeProject(text: string): Project {
  return {
    schema_version: 2,
    project: { name: text, created_at: "2026-07-21", updated_at: "2026-07-21" },
    media: null,
    timelines: [
      {
        id: "default",
        label: "原始",
        source: "default",
        created_at: "x",
        parent_id: "",
        transcript: { engine: "srt", language: "zh-CN", segments: [makeSegment(1)] },
        edits: [],
        analysis: { last_run: null, results: [] },
      },
    ],
    active_timeline_id: "default",
  }
}

function patchWithRevision(rev: number): ProjectPatch {
  return { revision: rev, timeline_id: "default" }
}

beforeEach(() => {
  applyUndoCalls.length = 0
  lastSeenRevision.value = 0
  applyUndoResult = { success: true, data: patchWithRevision(1) }
})

describe("useUndoRedo -- M5 layered path", () => {
  it("pushSnapshot captures layered before-state without stringify", async () => {
    const { pushSnapshot, undo } = useUndoRedo()
    const p1 = makeProject("v1")
    pushSnapshot(p1, ["segments"], "edit")
    const p2 = makeProject("v2")

    const res = await undo(p2)
    expect(res.ok).toBe(true)
    expect(applyUndoCalls[0].baseRevision).toBe(0)
    const layers = applyUndoCalls[0].layers as Record<string, unknown>
    expect(layers.segments).toEqual(p1.timelines[0].transcript.segments)
    expect("edits" in layers).toBe(false)
  })

  it("undo sends only requested layers and succeeds via apply_undo patch", async () => {
    const { pushSnapshot, undo } = useUndoRedo()
    const p1 = makeProject("v1")
    pushSnapshot(p1, ["edits"], "mark")
    const res = await undo(makeProject("v2"))
    expect(res.ok).toBe(true)
    const layers = applyUndoCalls[0].layers as Record<string, unknown>
    expect("segments" in layers).toBe(false)
    expect("edits" in layers).toBe(true)
    expect(res.patch).toEqual(patchWithRevision(1))
  })

  it("undo uses lastSeenRevision as base_revision and respects updates", async () => {
    const { pushSnapshot, undo } = useUndoRedo()
    noteRevision(41)
    pushSnapshot(makeProject("v1"), ["segments"], "x")
    await undo(makeProject("v2"))
    expect(applyUndoCalls[0].baseRevision).toBe(41)
  })

  it("redo pushes inverse record back through apply_undo", async () => {
    const { pushSnapshot, undo, redo } = useUndoRedo()
    const p1 = makeProject("v1")
    pushSnapshot(p1, ["segments"], "edit")
    await undo(makeProject("v2"))
    applyUndoResult = { success: true, data: patchWithRevision(2) }
    const res = await redo(makeProject("v2"))
    expect(res.ok).toBe(true)
    expect(applyUndoCalls.length).toBe(2)
    const layers = applyUndoCalls[1].layers as Record<string, unknown>
    // inverse record captured the state AFTER the undo target op (v2 state)
    expect(layers.segments).toEqual(makeProject("v2").timelines[0].transcript.segments)
  })

  it("failed apply_undo keeps the record on the undo stack", async () => {
    const { pushSnapshot, undo, canUndo } = useUndoRedo()
    pushSnapshot(makeProject("v1"), ["segments"], "edit")
    applyUndoResult = { success: false, error: "apply_undo: stale revision 0 (current 9)" }
    const res = await undo(makeProject("v2"))
    expect(res.ok).toBe(false)
    expect(canUndo.value).toBe(true) // not popped
  })

  it("caps layered history at 100 records", () => {
    const { pushSnapshot, undoStack } = useUndoRedo()
    for (let i = 0; i < 130; i++) {
      pushSnapshot(makeProject(`v${i}`), ["segments"], "x")
    }
    expect(undoStack.value.length).toBe(100)
  })

  it("empty stack undo returns error 'empty'", async () => {
    const { undo } = useUndoRedo()
    const res = await undo(makeProject("v1"))
    expect(res.ok).toBe(false)
    expect(res.error).toBe("empty")
  })
})

describe("useUndoRedo -- shared state", () => {
  it("clearHistory empties both stacks", () => {
    const { pushSnapshot, clearHistory, undoStack, redoStack } = useUndoRedo()
    pushSnapshot(makeProject("a"), ["segments"], "x")
    pushSnapshot(makeProject("b"), ["segments"], "y")
    expect(undoStack.value.length).toBeGreaterThan(0)
    clearHistory()
    expect(undoStack.value.length).toBe(0)
    expect(redoStack.value.length).toBe(0)
  })

  it("canUndo / canRedo reflect stack state (layered)", async () => {
    const { pushSnapshot, undo, canUndo, canRedo } = useUndoRedo()
    expect(canUndo.value).toBe(false)
    expect(canRedo.value).toBe(false)
    pushSnapshot(makeProject("a"), ["segments"], "x")
    expect(canUndo.value).toBe(true)
    await undo(makeProject("b"))
    expect(canUndo.value).toBe(false)
    expect(canRedo.value).toBe(true)
  })
})

// ------------------------------------------------------------------
// v3.0.1 M5-1: tracks/bindings capture layers
// ------------------------------------------------------------------

import { captureLayers, UNDO_LAYERS } from "@/utils/undoRecords"
import type { SubtitleTrack, TrackBinding } from "@/types/project"

describe("captureLayers with track layers (v3.0.1 M5-1)", () => {
  const track: SubtitleTrack = {
    id: "trk_1",
    role: "extension",
    name: "en",
    language: "en",
    segments: [],
  }
  const binding: TrackBinding = {
    id: "bind-1",
    track_id: "trk_1",
    main_segment_id: "seg-1",
    extension_segment_id: "track_trk_1_seg_0",
    start_offset: 0.1,
    end_offset: -0.1,
  }

  function projectWithTracks(): Project {
    const p = makeProject("tracks")
    p.timelines[0].transcript.tracks = [track]
    p.timelines[0].transcript.bindings = [binding]
    return p
  }

  it("registers tracks/bindings in the undoable layer set", () => {
    expect(UNDO_LAYERS).toContain("tracks")
    expect(UNDO_LAYERS).toContain("bindings")
  })

  it("captures shallow copies of the track layers", () => {
    const project = projectWithTracks()
    const snap = captureLayers(project, ["tracks", "bindings"])
    const tracks = snap.tracks as SubtitleTrack[]
    const bindings = snap.bindings as TrackBinding[]
    expect(tracks).toHaveLength(1)
    expect(bindings).toHaveLength(1)
    expect(tracks[0]).toBe(track) // shallow reference copy
    expect(bindings[0]).toBe(binding)
    expect(tracks).not.toBe(project.timelines[0].transcript.tracks)
  })

  it("returns empty arrays for projects without tracks", () => {
    const snap = captureLayers(makeProject("plain"), ["tracks", "bindings"])
    expect(snap.tracks).toEqual([])
    expect(snap.bindings).toEqual([])
  })

  it("omits track layers not requested", () => {
    const snap = captureLayers(projectWithTracks(), ["segments"])
    expect(snap.tracks).toBeUndefined()
    expect(snap.bindings).toBeUndefined()
  })
})

// ------------------------------------------------------------------
// v3.0.1 M5-3: three-layer atomic undo/redo integration
// ------------------------------------------------------------------

describe("three-layer atomic undo/redo (v3.0.1 M5-3)", () => {
  const track: SubtitleTrack = {
    id: "trk_1",
    role: "extension",
    name: "en",
    language: "en",
    segments: [
      { id: "track_trk_1_seg_0", version: 1, type: "subtitle", start: 0.5, end: 1.5, text: "en", speaker: "" },
    ],
  }
  const binding: TrackBinding = {
    id: "bind-1",
    track_id: "trk_1",
    main_segment_id: "seg-1",
    extension_segment_id: "track_trk_1_seg_0",
    start_offset: 0.5,
    end_offset: -3.5,
  }

  function projectWithTrack(label: string): Project {
    const p = makeProject(label)
    p.timelines[0].transcript.tracks = [track]
    p.timelines[0].transcript.bindings = [binding]
    return p
  }

  function splitApplied(p: Project): Project {
    // Simulate the post-linked-split state: main seg split into a/b, ext
    // seg split into two halves, binding split into two re-bound entries.
    const tl = p.timelines[0]
    const mainA = { ...makeSegment(1), id: "seg-1-a", end: 7 }
    const mainB = { ...makeSegment(1), id: "seg-1-b", start: 7, text: "segment 1 (b)" }
    return {
      ...p,
      timelines: [
        {
          ...tl,
          transcript: {
            ...tl.transcript,
            segments: [mainA, mainB],
            tracks: [
              {
                ...track,
                segments: [
                  { ...track.segments[0], id: "track_trk_1_seg_0__a", end: 1.0 },
                  { ...track.segments[0], id: "track_trk_1_seg_0__b", start: 1.0 },
                ],
              },
            ],
            bindings: [
              { ...binding, id: "bind-1__a", main_segment_id: "seg-1-a", extension_segment_id: "track_trk_1_seg_0__a" },
              { ...binding, id: "bind-1__b", main_segment_id: "seg-1-b", extension_segment_id: "track_trk_1_seg_0__b" },
            ],
          },
        },
      ],
    }
  }

  it("linked-split undo sends segments+tracks+bindings in ONE apply_undo", async () => {
    noteRevision(9)
    const { pushSnapshot, undo } = useUndoRedo()
    const before = projectWithTrack("before")
    pushSnapshot(before, ["segments", "tracks", "bindings"], "联动拆分")
    const after = splitApplied(projectWithTrack("after"))

    applyUndoResult = {
      success: true,
      data: {
        revision: 10,
        segments: before.timelines[0].transcript.segments,
        tracks: before.timelines[0].transcript.tracks,
        bindings: before.timelines[0].transcript.bindings,
      },
    }
    const res = await undo(after)
    expect(res.ok).toBe(true)
    expect(res.patch!.revision).toBe(10) // monotonic, never rewinds

    const call = applyUndoCalls[applyUndoCalls.length - 1]
    expect(Object.keys(call.layers as Record<string, unknown>).sort()).toEqual([
      "bindings",
      "segments",
      "tracks",
    ])
    expect(call.baseRevision).toBe(9)
  })

  it("redo replays the three-layer inverse symmetrically", async () => {
    noteRevision(3)
    const { pushSnapshot, undo, redo } = useUndoRedo()
    const before = projectWithTrack("before")
    pushSnapshot(before, ["segments", "tracks", "bindings"], "联动拆分")
    const after = splitApplied(projectWithTrack("after"))

    applyUndoResult = {
      success: true,
      data: { revision: 4, segments: before.timelines[0].transcript.segments },
    }
    const undoRes = await undo(after)
    expect(undoRes.ok).toBe(true)

    applyUndoResult = {
      success: true,
      data: {
        revision: 5,
        segments: after.timelines[0].transcript.segments,
        tracks: after.timelines[0].transcript.tracks,
        bindings: after.timelines[0].transcript.bindings,
      },
    }
    const redoRes = await redo(before)
    expect(redoRes.ok).toBe(true)
    expect(redoRes.patch!.revision).toBe(5) // strictly increasing
    const call = applyUndoCalls[applyUndoCalls.length - 1]
    expect(Object.keys(call.layers as Record<string, unknown>).sort()).toEqual([
      "bindings",
      "segments",
      "tracks",
    ])
  })

  it("a failed apply_undo keeps the three-layer record on the stack", async () => {
    noteRevision(2)
    const { pushSnapshot, undo, undoStack } = useUndoRedo()
    const before = projectWithTrack("before")
    pushSnapshot(before, ["segments", "tracks", "bindings"], "联动拆分")
    const after = splitApplied(projectWithTrack("after"))

    applyUndoResult = { success: false, error: "apply_undo: stale revision" }
    const res = await undo(after)
    expect(res.ok).toBe(false)
    expect(undoStack.value).toHaveLength(1) // record kept for retry
  })
})

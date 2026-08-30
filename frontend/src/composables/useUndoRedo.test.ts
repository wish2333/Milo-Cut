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

describe("useUndoRedo -- M5 layered path (undo_v2 on)", () => {
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

describe("useUndoRedo -- legacy path (undo_v2 off)", () => {
  it("pushSnapshot/undo/redo behave like the pre-M3 full snapshot", async () => {
    const { pushSnapshot, undo, redo } = useUndoRedo({ isUndoV2: () => false })
    const v1 = makeProject("v1")
    const v2 = makeProject("v2")

    pushSnapshot(v1)
    const res = await undo(v2)
    expect(res.ok).toBe(true)
    expect(res.project).toEqual(v1)
    expect(applyUndoCalls.length).toBe(0) // never touches the backend

    const res2 = await redo(v2)
    expect(res2.ok).toBe(true)
    expect(res2.project).toEqual(v2)
  })

  it("legacy undo caps history at 50", () => {
    const { pushSnapshot, legacyUndoStack } = useUndoRedo({ isUndoV2: () => false })
    for (let i = 0; i < 60; i++) {
      pushSnapshot(makeProject(`v${i}`))
    }
    expect(legacyUndoStack.value.length).toBe(50)
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

  it("flag-off undo with an empty legacy stack is a no-op", async () => {
    const flag = { on: true }
    const { pushSnapshot, undo, clearHistory } = useUndoRedo({ isUndoV2: () => flag.on })
    pushSnapshot(makeProject("a"), ["segments"], "x") // captured layered
    clearHistory()
    flag.on = false
    // undo now reads the legacy stack (empty) - no backend call
    const res = await undo(makeProject("b"))
    expect(res.ok).toBe(false)
    expect(res.error).toBe("empty")
    expect(applyUndoCalls.length).toBe(0)
  })
})

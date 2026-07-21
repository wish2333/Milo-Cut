import { describe, expect, it } from "vitest"
import { useUndoRedo } from "@/composables/useUndoRedo"
import type { Project, Segment } from "@/types/project"

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

describe("useUndoRedo -- v2.3.2 stage 2 snapshot contract", () => {
  it("pushSnapshot stores the project passed at call time (pre-patch state)", () => {
    const { pushSnapshot, undo } = useUndoRedo()
    const before = makeProject("before")
    const after = makeProject("after")

    pushSnapshot(before)
    const restored = undo(after)
    expect(restored).toEqual(before)
    expect(restored).not.toEqual(after)
  })

  it("undo/redo round-trip preserves full Project state", () => {
    const { pushSnapshot, undo, redo } = useUndoRedo()
    const v1 = makeProject("v1")
    const v2 = makeProject("v2")
    const v3 = makeProject("v3")

    pushSnapshot(v1)
    pushSnapshot(v2)

    const restored2 = undo(v3)
    expect(restored2).toEqual(v2)

    const restored3 = redo(v3)
    expect(restored3).toEqual(v3)
  })

  it("pushSnapshot before applyProjectPatch preserves pre-patch state", () => {
    // The actual v2.3.2 stage 2 lifecycle:
    //   1. composable calls pushSnapshot(currentProject)
    //   2. composable applies patch -> newProject
    //   3. undo() returns the pre-patch currentProject
    const { pushSnapshot, undo } = useUndoRedo()
    const original = makeProject("original")

    pushSnapshot(original)
    // Simulate patch application by mutating a local copy
    const patched: Project = {
      ...original,
      project: { ...original.project, name: "patched" },
    }
    expect(patched).not.toEqual(original)

    const restored = undo(patched)
    expect(restored).toEqual(original)
  })

  it("caps undo stack at DEFAULT_MAX_HISTORY (50) for small snapshots", () => {
    const { pushSnapshot, undoStack } = useUndoRedo()
    for (let i = 0; i < 100; i++) {
      pushSnapshot(makeProject(`v${i}`))
    }
    expect(undoStack.value.length).toBe(50)
  })

  it("clearHistory empties both stacks", () => {
    const { pushSnapshot, clearHistory, undoStack, redoStack } = useUndoRedo()
    pushSnapshot(makeProject("a"))
    pushSnapshot(makeProject("b"))
    expect(undoStack.value.length).toBeGreaterThan(0)
    clearHistory()
    expect(undoStack.value.length).toBe(0)
    expect(redoStack.value.length).toBe(0)
  })

  it("canUndo / canRedo reflect stack state", () => {
    const { pushSnapshot, undo, canUndo, canRedo } = useUndoRedo()
    expect(canUndo.value).toBe(false)
    expect(canRedo.value).toBe(false)
    pushSnapshot(makeProject("a"))
    expect(canUndo.value).toBe(true)
    undo(makeProject("b"))
    expect(canUndo.value).toBe(false)
    expect(canRedo.value).toBe(true)
  })
})

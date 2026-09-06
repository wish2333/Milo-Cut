/**
 * v3.0.0 M5 scale automation (plan P2-1 acceptance + perf-beta2 input):
 * a 1167-segment mock project, 50 consecutive edits, 50 undos back to the
 * initial state -- with main-thread undo cost sampling (target < 5ms per
 * undo: layered capture + applyProjectPatch, the parts Vue runs).
 *
 * The bridge is mocked with an in-test apply_undo mirror that follows the
 * backend contract (validate base_revision, replace layer, revision+1,
 * return the restored layer content as a ProjectPatch), so the whole
 * frontend undo path (undoRecords capture -> useUndoRedo -> apply_undo ->
 * applyProjectPatch) runs for real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { useUndoRedo } from "@/composables/useUndoRedo"
import { applyProjectPatch } from "@/utils/projectPatch"
import { captureLayers } from "@/utils/undoRecords"
import { lastSeenRevision, noteRevision } from "@/utils/revision"
import type { Project, ProjectPatch, Segment } from "@/types/project"

const SEGMENT_COUNT = 1167
const EDIT_ROUNDS = 50

// -- In-test backend mirror ------------------------------------------------
//
// Real apply_undo is stateless from the backend's view: the frontend sends
// the captured before-layers to restore; the backend validates base_revision,
// replaces the layers, bumps revision, and echoes the restored content as a
// ProjectPatch. The undo/redo stacks live entirely in useUndoRedo.

let revision = 0

vi.mock("@/bridge", () => ({
  call: vi.fn(async (method: string, ...args: unknown[]) => {
    if (method !== "apply_undo") return { success: false, error: `unexpected ${method}` }
    const layers = args[0] as Record<string, unknown>
    const baseRevision = args[1] as number
    if (baseRevision !== revision) {
      return { success: false, error: "stale base_revision" }
    }
    revision += 1
    return {
      success: true,
      data: { revision, timeline_id: "default", ...layers } as ProjectPatch,
    }
  }),
}))

// -- Fixtures --------------------------------------------------------------

function makeSegment(i: number): Segment {
  return {
    id: `seg_${(i * 3 + 1).toFixed(3)}`,
    version: 1,
    type: i % 3 === 2 ? "silence" : "subtitle",
    start: i * 5 + 1,
    end: i * 5 + 5,
    text: i % 3 === 2 ? "" : `segment ${i + 1} 口播内容`,
    speaker: "",
  }
}

function segmentsOf(segments: Segment[]): Segment[] {
  return segments
}

function cloneWithEdit(segments: Segment[], round: number): Segment[] {
  // One text mutation per edit round (the dominant real-world edit).
  const target = (round * 23) % segments.length
  return segments.map((s, i) =>
    i === target ? { ...s, text: `${s.text} #r${round}`, version: s.version + 1 } : s,
  )
}

function makeProject(segments: Segment[]): Project {
  return {
    schema_version: 2,
    project: { name: "undo-scale", created_at: "x", updated_at: "x" },
    media: null,
    timelines: [
      {
        id: "default",
        label: "原始",
        source: "default",
        created_at: "x",
        parent_id: "",
        transcript: { engine: "srt", language: "zh-CN", segments },
        edits: [],
        analysis: { last_run: null, results: [] },
      },
    ],
    active_timeline_id: "default",
  }
}

beforeEach(() => {
  revision = 0
  lastSeenRevision.value = 0
})

describe("undo scale automation: 1167 segments, 50 edits, 50 undos", () => {
  it("returns to the initial state with sub-5ms main-thread undo cost", async () => {
    const initial = Array.from({ length: SEGMENT_COUNT }, (_, i) => makeSegment(i))
    noteRevision(revision)
    const { pushSnapshot, undo } = useUndoRedo()

    let segments = segmentsOf(initial.map((s) => ({ ...s })))
    const applyMs: number[] = []
    const captureMs: number[] = []

    // 50 edits: capture layered before-state, mutate, bump revision like a
    // backend write would.
    for (let round = 0; round < EDIT_ROUNDS; round++) {
      const proj = makeProject(segments)
      const t0 = performance.now()
      captureLayers(proj, ["segments"])
      captureMs.push(performance.now() - t0)
      pushSnapshot(proj, ["segments"], `edit ${round}`)
      segments = cloneWithEdit(segments, round)
      revision += 1
      noteRevision(revision)
    }

    // 50 undos: real useUndoRedo path + real applyProjectPatch (in-place
    // merge with gate assertion), measuring the Vue main-thread share
    // (stack ops + bridge call resolution + in-place patch apply).
    let project = makeProject(segments)
    for (let i = 0; i < EDIT_ROUNDS; i++) {
      const t0 = performance.now()
      const res = await undo(project)
      expect(res.ok).toBe(true)
      expect(res.patch).toBeTruthy()
      project = applyProjectPatch(project, res.patch!) as Project
      applyMs.push(performance.now() - t0)
      noteRevision(revision)
    }

    // Roundtrip correctness: back to the exact initial state.
    const finalSegs = project.timelines[0].transcript.segments
    expect(finalSegs.length).toBe(SEGMENT_COUNT)
    expect(finalSegs).toEqual(initial)

    const p50 = (arr: number[]) => [...arr].sort((a, b) => a - b)[Math.floor(arr.length / 2)]
    const undoP50 = p50(applyMs)
    // plan acceptance: undo main-thread cost < 5ms (capture + patch apply)
    expect(undoP50).toBeLessThan(5)
    expect(p50(captureMs)).toBeLessThan(5)

    console.log(
      `[perf] undo(1167 segs) x50: apply_undo+patch p50=${undoP50.toFixed(3)}ms ` +
        `max=${Math.max(...applyMs).toFixed(3)}ms; capture p50=${p50(captureMs).toFixed(3)}ms`,
    )
  })
})

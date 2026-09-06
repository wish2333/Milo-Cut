/**
 * Layered undo record structures (v3.0.0 M5-1).
 *
 * A record captures the *before* state of only the layers an operation
 * touches. Undo replays the captured layers through the backend
 * ``apply_undo`` channel (SPEC M5-2); redo replays the inverse record
 * captured at undo time.
 *
 * v3.0.1 M5-1: tracks/bindings join the undoable layers -- linkage
 * operations snapshot all three transcript layers in ONE record
 * (segments + tracks + bindings) for atomic undo (PRD R8.1).
 */
import type { Project } from "@/types/project"

export type UndoLayer = "segments" | "edits" | "analysis" | "tracks" | "bindings"

export const UNDO_LAYERS: readonly UndoLayer[] = [
  "segments",
  "edits",
  "analysis",
  "tracks",
  "bindings",
]

export interface UndoRecord {
  id: string
  label: string
  createdAt: number
  /** before-state per layer; values are shallow reference copies */
  records: Partial<Record<UndoLayer, unknown>>
}

let idCounter = 0

export function nextUndoRecordId(): string {
  idCounter += 1
  return `undo-${Date.now().toString(36)}-${idCounter}`
}

/**
 * Capture shallow reference copies of the requested layers of the
 * active timeline. No JSON.stringify anywhere (perf red line: undo push
 * must stay O(layer size) without serialization).
 */
export function captureLayers(
  project: Project,
  layers: readonly UndoLayer[],
): Partial<Record<UndoLayer, unknown>> {
  const tl = project.timelines.find(t => t.id === project.active_timeline_id)
  if (!tl) return {}
  const out: Partial<Record<UndoLayer, unknown>> = {}
  if (layers.includes("segments")) {
    out.segments = [...tl.transcript.segments]
  }
  if (layers.includes("edits")) {
    out.edits = [...tl.edits]
  }
  if (layers.includes("analysis")) {
    out.analysis = tl.analysis ? { ...tl.analysis } : null
  }
  if (layers.includes("tracks")) {
    out.tracks = [...(tl.transcript.tracks ?? [])]
  }
  if (layers.includes("bindings")) {
    out.bindings = [...(tl.transcript.bindings ?? [])]
  }
  return out
}

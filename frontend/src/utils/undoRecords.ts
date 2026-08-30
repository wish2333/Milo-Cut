/**
 * Layered undo record structures (v3.0.0 M5-1).
 *
 * A record captures the *before* state of only the layers an operation
 * touches. Undo replays the captured layers through the backend
 * ``apply_undo`` channel (SPEC M5-2); redo replays the inverse record
 * captured at undo time.
 *
 * Decision (2026-08-30, plan P2-1 风险缓冲条款): the segments layer keeps
 * an array *shallow reference copy* instead of the spec's per-segment
 * diff (Map<id, Segment|null> + id_lineage). Rationale: undo goes through
 * the backend which replaces the whole layer anyway, so per-segment
 * diffing buys nothing on the restore path today; lineage only matters
 * once M7-1 lands in-place id-based patching. Recorded per plan Day 2
 * 降级条款; revisit after M7-1 (P2-3).
 */
import type { Project } from "@/types/project"

export type UndoLayer = "segments" | "edits" | "analysis"

export const UNDO_LAYERS: readonly UndoLayer[] = ["segments", "edits", "analysis"]

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
  return out
}

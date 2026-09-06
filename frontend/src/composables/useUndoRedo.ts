/**
 * Layered undo/redo (v3.0.0 M5).
 *
 * Undo/redo replay layer snapshots through the backend ``apply_undo``
 * @expose which owns the revision counter and returns a ProjectPatch. The
 * caller applies the patch via the existing ``project-updated`` emit;
 * revision never rewinds (red line).
 *
 * Records hold shallow reference copies (see utils/undoRecords.ts) -- no
 * JSON.stringify anywhere on this path.
 *
 * History note: a legacy full-JSON snapshot path coexisted behind the
 * ``undo_v2`` flag until the beta.2 smoke passed; it was removed afterwards
 * (rollback anchor: tag ``pre-undo-cleanup``).
 */
import { ref, computed } from "vue"
import { call } from "@/bridge"
import type { Project, ProjectPatch } from "@/types/project"
import {
  captureLayers,
  nextUndoRecordId,
  UNDO_LAYERS,
  type UndoLayer,
  type UndoRecord,
} from "@/utils/undoRecords"
import { lastSeenRevision } from "@/utils/revision"

/** Layered history cap (PRD B4 R4.3). */
const LAYERED_MAX_HISTORY = 100

export interface UndoOutcome {
  ok: boolean
  /** ProjectPatch on success (apply via project-updated). */
  patch?: ProjectPatch
  /** "empty" = nothing to undo/redo; other strings are real failures. */
  error?: string
}

export function useUndoRedo() {
  const undoStack = ref<UndoRecord[]>([])
  const redoStack = ref<UndoRecord[]>([])

  /**
   * Push a before-snapshot. ``layers`` narrows what gets captured; when
   * omitted, the union of undoable layers is captured so undo semantics
   * stay conservative.
   */
  function pushSnapshot(project: Project, layers?: UndoLayer[], label = "") {
    const ls = layers ?? UNDO_LAYERS
    const record: UndoRecord = {
      id: nextUndoRecordId(),
      label,
      createdAt: Date.now(),
      records: captureLayers(project, ls),
    }
    undoStack.value = [...undoStack.value, record].slice(-LAYERED_MAX_HISTORY)
    redoStack.value = []
  }

  async function applyThroughBackend(
    record: UndoRecord,
  ): Promise<UndoOutcome> {
    const res = await call<ProjectPatch>(
      "apply_undo",
      record.records,
      lastSeenRevision.value,
    )
    if (!res.success || !res.data) {
      return { ok: false, error: res.error ?? "apply_undo failed" }
    }
    return { ok: true, patch: res.data }
  }

  async function undo(project: Project): Promise<UndoOutcome> {
    if (undoStack.value.length === 0) return { ok: false, error: "empty" }
    const record = undoStack.value[undoStack.value.length - 1]
    const involved = Object.keys(record.records) as UndoLayer[]
    const inverse: UndoRecord = {
      ...record,
      id: nextUndoRecordId(),
      records: captureLayers(project, involved),
    }
    const res = await applyThroughBackend(record)
    if (!res.ok) return res
    undoStack.value = undoStack.value.slice(0, -1)
    redoStack.value = [...redoStack.value, inverse]
    return res
  }

  async function redo(project: Project): Promise<UndoOutcome> {
    if (redoStack.value.length === 0) return { ok: false, error: "empty" }
    const record = redoStack.value[redoStack.value.length - 1]
    const involved = Object.keys(record.records) as UndoLayer[]
    const inverse: UndoRecord = {
      ...record,
      id: nextUndoRecordId(),
      records: captureLayers(project, involved),
    }
    const res = await applyThroughBackend(record)
    if (!res.ok) return res
    redoStack.value = redoStack.value.slice(0, -1)
    undoStack.value = [...undoStack.value, inverse]
    return res
  }

  function clearHistory() {
    undoStack.value = []
    redoStack.value = []
  }

  return {
    undoStack,
    redoStack,
    pushSnapshot,
    undo,
    redo,
    clearHistory,
    canUndo: computed(() => undoStack.value.length > 0),
    canRedo: computed(() => redoStack.value.length > 0),
  }
}

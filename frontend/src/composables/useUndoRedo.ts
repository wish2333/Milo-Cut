/**
 * Layered undo/redo (v3.0.0 M5).
 *
 * New path (undo_v2, default): undo/redo replay layer snapshots through
 * the backend ``apply_undo`` @expose which owns the revision counter and
 * returns a ProjectPatch. The caller applies the patch via the existing
 * ``project-updated`` emit; revision never rewinds (red line).
 *
 * Legacy path (undo_v2 = false): the pre-v3 full-JSON snapshot stack is
 * kept verbatim as the rollback escape hatch (risk review 4.6). The
 * active path is chosen per-call via the injected ``isUndoV2`` getter so
 * a settings flip takes effect without remounting the workspace.
 *
 * Records hold shallow reference copies (see utils/undoRecords.ts);
 * JSON.stringify only happens on the legacy path.
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

const DEFAULT_MAX_HISTORY = 50
const LARGE_SNAPSHOT_THRESHOLD = 2 * 1024 * 1024 // 2MB
const REDUCED_MAX_HISTORY = 10
/** M5: layered history cap (PRD B4 R4.3). */
const LAYERED_MAX_HISTORY = 100

export interface UndoOutcome {
  ok: boolean
  /** ProjectPatch on layered-path success (apply via project-updated). */
  patch?: ProjectPatch
  /** Full Project on legacy-path success (apply via project-updated). */
  project?: Project
  /** "empty" = nothing to undo/redo; other strings are real failures. */
  error?: string
}

export function useUndoRedo(options?: { isUndoV2?: () => boolean }) {
  const isUndoV2 = options?.isUndoV2 ?? (() => true)

  // Layered stacks (M5).
  const undoStack = ref<UndoRecord[]>([])
  const redoStack = ref<UndoRecord[]>([])

  // Legacy full-JSON stacks (rollback path, kept until pre-undo-cleanup).
  const legacyUndoStack = ref<string[]>([])
  const legacyRedoStack = ref<string[]>([])

  function getEffectiveMaxHistory(): number {
    if (legacyUndoStack.value.length > 0) {
      const lastSize = legacyUndoStack.value[legacyUndoStack.value.length - 1].length
      if (lastSize > LARGE_SNAPSHOT_THRESHOLD) {
        return REDUCED_MAX_HISTORY
      }
    }
    return DEFAULT_MAX_HISTORY
  }

  /**
   * Push a before-snapshot. Layered path: ``layers`` narrows what gets
   * captured; when omitted (transition-period call sites not yet
   * migrated), the union of undoable layers is captured so undo semantics
   * stay conservative until Day 3 point-by-point migration narrows them.
   */
  function pushSnapshot(project: Project, layers?: UndoLayer[], label = "") {
    if (isUndoV2()) {
      const ls = layers ?? UNDO_LAYERS
      const record: UndoRecord = {
        id: nextUndoRecordId(),
        label,
        createdAt: Date.now(),
        records: captureLayers(project, ls),
      }
      undoStack.value = [...undoStack.value, record].slice(-LAYERED_MAX_HISTORY)
      redoStack.value = []
      return
    }
    // Legacy path: full JSON snapshot.
    const serialized = JSON.stringify(project)
    legacyUndoStack.value = [...legacyUndoStack.value, serialized]
    const maxHistory = getEffectiveMaxHistory()
    while (legacyUndoStack.value.length > maxHistory) {
      legacyUndoStack.value = legacyUndoStack.value.slice(1)
    }
    legacyRedoStack.value = []
  }

  async function undo(project: Project): Promise<UndoOutcome> {
    if (isUndoV2()) {
      if (undoStack.value.length === 0) return { ok: false, error: "empty" }
      const record = undoStack.value[undoStack.value.length - 1]
      const involved = Object.keys(record.records) as UndoLayer[]
      const inverse: UndoRecord = {
        ...record,
        id: nextUndoRecordId(),
        records: captureLayers(project, involved),
      }
      const res = await call<ProjectPatch>(
        "apply_undo",
        record.records,
        lastSeenRevision.value,
      )
      if (!res.success || !res.data) {
        return { ok: false, error: res.error ?? "apply_undo failed" }
      }
      undoStack.value = undoStack.value.slice(0, -1)
      redoStack.value = [...redoStack.value, inverse]
      return { ok: true, patch: res.data }
    }
    // Legacy path.
    if (legacyUndoStack.value.length === 0) return { ok: false, error: "empty" }
    const newUndo = [...legacyUndoStack.value]
    const snapshot = newUndo.pop()!
    legacyUndoStack.value = newUndo
    legacyRedoStack.value = [...legacyRedoStack.value, JSON.stringify(project)]
    return { ok: true, project: JSON.parse(snapshot) as Project }
  }

  async function redo(project: Project): Promise<UndoOutcome> {
    if (isUndoV2()) {
      if (redoStack.value.length === 0) return { ok: false, error: "empty" }
      const record = redoStack.value[redoStack.value.length - 1]
      const involved = Object.keys(record.records) as UndoLayer[]
      const inverse: UndoRecord = {
        ...record,
        id: nextUndoRecordId(),
        records: captureLayers(project, involved),
      }
      const res = await call<ProjectPatch>(
        "apply_undo",
        record.records,
        lastSeenRevision.value,
      )
      if (!res.success || !res.data) {
        return { ok: false, error: res.error ?? "apply_undo failed" }
      }
      redoStack.value = redoStack.value.slice(0, -1)
      undoStack.value = [...undoStack.value, inverse]
      return { ok: true, patch: res.data }
    }
    // Legacy path.
    if (legacyRedoStack.value.length === 0) return { ok: false, error: "empty" }
    const newRedo = [...legacyRedoStack.value]
    const snapshot = newRedo.pop()!
    legacyRedoStack.value = newRedo
    legacyUndoStack.value = [...legacyUndoStack.value, JSON.stringify(project)]
    return { ok: true, project: JSON.parse(snapshot) as Project }
  }

  function clearHistory() {
    undoStack.value = []
    redoStack.value = []
    legacyUndoStack.value = []
    legacyRedoStack.value = []
  }

  return {
    undoStack,
    redoStack,
    legacyUndoStack,
    legacyRedoStack,
    pushSnapshot,
    undo,
    redo,
    clearHistory,
    canUndo: computed(
      () =>
        (isUndoV2() ? undoStack.value.length : legacyUndoStack.value.length) > 0,
    ),
    canRedo: computed(
      () =>
        (isUndoV2() ? redoStack.value : legacyRedoStack.value).length > 0,
    ),
  }
}

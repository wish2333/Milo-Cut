import type { EditDecision, Segment } from "@/types/project"

export function isOverlapping(
  edit: EditDecision,
  seg: Segment,
  minOverlapSeconds = 0.0,
): boolean {
  const overlapStart = Math.max(edit.start, seg.start)
  const overlapEnd = Math.min(edit.end, seg.end)
  return overlapEnd - overlapStart > minOverlapSeconds
}

// -- Unified segment state -----------------------------------------------

export interface SegmentState {
  displayStatus: "none" | EditDecision["status"]
  styleClass: "normal" | "masked" | "kept"
  activeEdit: EditDecision | undefined
}

export function resolveSegmentState(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): SegmentState {
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg, 0.3),
  )

  const all = related
  const active = all.filter(e => e.status !== "rejected")
  const sortedActive = active.sort((a, b) => b.priority - a.priority)
  const sortedAll = all.sort((a, b) => b.priority - a.priority)
  const topActive = sortedActive[0]
  const topEdit = sortedAll[0]

  if (!topActive) {
    return {
      displayStatus: topEdit ? "rejected" : "none",
      styleClass: "normal",
      activeEdit: undefined,
    }
  }

  const rejectedOverrides =
    topEdit && topEdit.status === "rejected" && topEdit.priority > topActive.priority && topEdit.action !== topActive.action
  const displayStatus: SegmentState["displayStatus"] = rejectedOverrides ? "rejected" : topActive.status

  return {
    displayStatus,
    styleClass: topActive.action === "delete" ? "masked" : "kept",
    activeEdit: topActive,
  }
}

// -- Deprecated wrappers (kept for backwards compat) ---------------------

/** @deprecated Use resolveSegmentState instead */
export function getEditForSegment(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision | undefined {
  const byId = edits.find(e => e.target_id === seg.id)
  if (byId) return byId

  const overlapping = edits.filter(e => isOverlapping(e, seg, 0.3))
  if (overlapping.length > 0) {
    return [...overlapping].sort((a, b) => b.priority - a.priority)[0]
  }

  return undefined
}

/** @deprecated Use resolveSegmentState instead */
export function getEffectiveStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): "normal" | "masked" | "kept" {
  return resolveSegmentState(edits, seg).styleClass
}

/** @deprecated Use resolveSegmentState instead */
export function getEditStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision["status"] | null {
  const state = resolveSegmentState(edits, seg)
  return state.displayStatus === "none" ? null : state.displayStatus
}

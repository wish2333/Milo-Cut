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

export function getEditForSegment(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision | undefined {
  const byId = edits.find(e => e.target_id === seg.id)
  if (byId) return byId
  return edits.find(e =>
    e.target_type === "range" &&
    Math.abs(e.start - seg.start) < 0.01 &&
    Math.abs(e.end - seg.end) < 0.01,
  )
}

export function getEffectiveStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): "normal" | "masked" | "kept" {
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg, 0.3),
  )
  const active = related.filter(e => e.status !== "rejected")
  if (active.length === 0) return "normal"
  const top = [...active].sort((a, b) => b.priority - a.priority)[0]
  if (top.action === "delete") return "masked"
  return "kept"
}

export function getEditStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision["status"] | null {
  return getEditForSegment(edits, seg)?.status ?? null
}

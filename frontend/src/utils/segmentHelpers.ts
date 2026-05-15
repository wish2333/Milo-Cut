import type { EditDecision, Segment } from "@/types/project"

export function isOverlapping(edit: EditDecision, seg: Segment): boolean {
  return edit.start < seg.end && edit.end > seg.start
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
    e.target_id === seg.id || isOverlapping(e, seg),
  )
  if (related.length === 0) return "normal"
  const top = [...related].sort((a, b) => b.priority - a.priority)[0]
  if (top.action === "delete") return "masked"
  return "kept"
}

export function getEditStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision["status"] | null {
  return getEditForSegment(edits, seg)?.status ?? null
}

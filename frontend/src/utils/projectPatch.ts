import type { Project, ProjectPatch, ProjectResponse, Segment, Timeline, Word } from "@/types/project"
import { isProjectPatch } from "@/types/project"

export class PatchApplicationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "PatchApplicationError"
  }
}

/**
 * v3.0.0 M7-1: cheap equality check so untouched segments keep their
 * object identity (v-memo / computed dependency skip). ``words`` is the
 * only nested array; compare contents (ASR words are small).
 */
function wordsEqual(a: Word[] | undefined, b: Word[] | undefined): boolean {
  if (a === b) return true
  if (!a || !b || a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (
      a[i].word !== b[i].word ||
      a[i].start !== b[i].start ||
      a[i].end !== b[i].end
    ) {
      return false
    }
  }
  return true
}

function segmentEqual(a: Segment, b: Segment): boolean {
  return (
    a.id === b.id &&
    a.version === b.version &&
    a.type === b.type &&
    a.start === b.start &&
    a.end === b.end &&
    a.text === b.text &&
    a.speaker === b.speaker &&
    wordsEqual(a.words, b.words)
  )
}

/**
 * v3.0.0 M7-1: merge the backend's full segments array into the existing
 * array, reusing references for unchanged segments and keeping unchanged
 * rows at their old index. O(n) with a Map; backend guarantees start-
 * ascending order (sort invariant), new segments are inserted at the
 * position derived from the merged order.
 *
 * Gate assertion (risk review 4.3 M7): the result id sequence must match
 * the backend array exactly; otherwise fall back to wholesale replace
 * with a console.warn -- "宁可慢，不可错序".
 */
export function mergeSegmentsInPlace(
  oldSegs: Segment[],
  newSegs: Segment[],
): Segment[] {
  const newById = new Map(newSegs.map(s => [s.id, s]))
  const out: Segment[] = []
  for (const old of oldSegs) {
    const next = newById.get(old.id)
    if (next === undefined) continue // deleted segment
    out.push(segmentEqual(old, next) ? old : next)
  }
  // Insert segments that did not exist before, then restore start order
  // with a stable sort (unchanged rows already sit at valid positions).
  const consumed = new Set(out.map(s => s.id))
  for (const s of newSegs) {
    if (!consumed.has(s.id)) out.push(s)
  }
  const starts = new Map(newSegs.map(s => [s.id, s.start]))
  out.sort((a, b) => (starts.get(a.id) ?? 0) - (starts.get(b.id) ?? 0))

  // Gate: merged id sequence must equal the backend array verbatim.
  const oldIds = newSegs.map(s => s.id)
  const gotIds = out.map(s => s.id)
  for (let i = 0; i < oldIds.length; i++) {
    if (oldIds[i] !== gotIds[i]) {
      console.warn(
        "[projectPatch] segment id sequence mismatch after in-place merge; " +
          "falling back to wholesale replacement",
      )
      return [...newSegs]
    }
  }
  return out
}

export function applyProjectPatch(project: Project, patch: ProjectPatch): Project {
  if (patch.full_project) {
    return patch.full_project
  }

  const targetTimelineId = patch.timeline_id ?? project.active_timeline_id

  const hasLayerUpdates =
    patch.segments != null || patch.edits != null || patch.analysis != null

  if (hasLayerUpdates) {
    const targetExists = project.timelines.some((tl) => tl.id === targetTimelineId)
    if (!targetExists) {
      throw new PatchApplicationError(
        `Patch targets timeline_id=${targetTimelineId} which does not exist on project`,
      )
    }
  }

  const newTimelines: Timeline[] = project.timelines.map((tl) => {
    if (tl.id !== targetTimelineId) {
      return tl
    }
    let newTl: Timeline = tl
    if (patch.segments != null) {
      newTl = {
        ...newTl,
        transcript: {
          ...newTl.transcript,
          // v3.0.0 M7-1: in-place id merge keeps unchanged segment
          // references stable (v-memo effective); gate assertion falls
          // back to wholesale replace on id-sequence mismatch.
          segments: mergeSegmentsInPlace(newTl.transcript.segments, patch.segments),
        },
      }
    }
    if (patch.edits != null) {
      newTl = { ...newTl, edits: [...patch.edits] }
    }
    if (patch.analysis != null) {
      newTl = { ...newTl, analysis: patch.analysis }
    }
    return newTl
  })

  const result: Project = {
    ...project,
    timelines: newTimelines,
  }
  if (patch.media != null) {
    result.media = patch.media
  }
  if (patch.active_timeline_id != null) {
    result.active_timeline_id = patch.active_timeline_id
  }
  return result
}

export function isStalePatch(
  patch: ProjectPatch,
  lastSeenRevision: number,
): boolean {
  return patch.revision <= lastSeenRevision
}

export function applyProjectResponse(
  current: Project,
  response: ProjectResponse,
): Project {
  if (isProjectPatch(response)) {
    return applyProjectPatch(current, response)
  }
  return response
}

export type LayerChange =
  | "segments"
  | "edits"
  | "analysis"
  | "media"
  | "active_timeline"
  | "full_project"

export function describePatchLayers(patch: ProjectPatch): LayerChange[] {
  if (patch.full_project) {
    return ["full_project"]
  }
  const layers: LayerChange[] = []
  if (patch.segments != null) layers.push("segments")
  if (patch.edits != null) layers.push("edits")
  if (patch.analysis != null) layers.push("analysis")
  if (patch.media != null) layers.push("media")
  if (patch.active_timeline_id != null) layers.push("active_timeline")
  return layers
}

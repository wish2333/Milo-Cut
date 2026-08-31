import type { Project, ProjectPatch, ProjectResponse, Segment, SubtitleTrack, Timeline, TrackBinding, Word } from "@/types/project"
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

// ------------------------------------------------------------------
// v3.0.1 M3: tracks/bindings in-place merge (P1-4: functions land first,
// applyProjectPatch wiring activates in Phase 3 once linkage editing
// exists -- until then track layers stay wholesale-replace).
// ------------------------------------------------------------------

function segmentsArrayEqual(a: Segment[], b: Segment[]): boolean {
  if (a === b) return true
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (!segmentEqual(a[i], b[i])) return false
  }
  return true
}

function trackEqual(a: SubtitleTrack, b: SubtitleTrack): boolean {
  return (
    a.id === b.id &&
    a.role === b.role &&
    a.name === b.name &&
    a.language === b.language &&
    segmentsArrayEqual(a.segments, b.segments)
  )
}

function bindingEqual(a: TrackBinding, b: TrackBinding): boolean {
  return (
    a.id === b.id &&
    a.track_id === b.track_id &&
    a.main_segment_id === b.main_segment_id &&
    a.extension_segment_id === b.extension_segment_id &&
    a.start_offset === b.start_offset &&
    a.end_offset === b.end_offset
  )
}

/**
 * v3.0.1 M3: merge the backend's full tracks array into the existing one,
 * reusing references for unchanged tracks AND unchanged segments inside
 * changed tracks (single-segment drags must not invalidate sibling lanes
 * or unrelated segments -- perf gate R6.2). Backend order is the source of
 * truth; on any id-sequence mismatch fall back to wholesale replacement.
 */
export function mergeTracksInPlace(
  oldTracks: SubtitleTrack[],
  newTracks: SubtitleTrack[],
): SubtitleTrack[] {
  const newById = new Map(newTracks.map(t => [t.id, t]))
  const out: SubtitleTrack[] = []
  for (const old of oldTracks) {
    const next = newById.get(old.id)
    if (next === undefined) continue // deleted track
    if (trackEqual(old, next)) {
      out.push(old)
      continue
    }
    out.push({ ...next, segments: mergeSegmentsInPlace(old.segments, next.segments) })
  }
  const consumed = new Set(out.map(t => t.id))
  for (const t of newTracks) {
    if (!consumed.has(t.id)) out.push(t)
  }

  // Gate: backend order is authoritative.
  for (let i = 0; i < newTracks.length; i++) {
    if (out[i]?.id !== newTracks[i].id) {
      console.warn(
        "[projectPatch] track id sequence mismatch after in-place merge; " +
          "falling back to wholesale replacement",
      )
      return [...newTracks]
    }
  }
  return out
}

/**
 * v3.0.1 M3: bindings merge by binding id. Backend array order is the
 * source of truth; id-sequence mismatch falls back to wholesale replace.
 */
export function mergeBindingsInPlace(
  oldBindings: TrackBinding[],
  newBindings: TrackBinding[],
): TrackBinding[] {
  const newById = new Map(newBindings.map(b => [b.id, b]))
  const out: TrackBinding[] = []
  for (const old of oldBindings) {
    const next = newById.get(old.id)
    if (next === undefined) continue // dissolved binding
    out.push(bindingEqual(old, next) ? old : next)
  }
  const consumed = new Set(out.map(b => b.id))
  for (const b of newBindings) {
    if (!consumed.has(b.id)) out.push(b)
  }

  for (let i = 0; i < newBindings.length; i++) {
    if (out[i]?.id !== newBindings[i].id) {
      console.warn(
        "[projectPatch] binding id sequence mismatch after in-place merge; " +
          "falling back to wholesale replacement",
      )
      return [...newBindings]
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
    patch.segments != null ||
    patch.edits != null ||
    patch.analysis != null ||
    // v3.0.0 M11-2: track layers are timeline-scoped like the above.
    patch.tracks != null ||
    patch.bindings != null

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
    // v3.0.0 M11-2: subtitle-track layers (wholesale replace, grouped with
    // the timeline layers; independent so a bindings-only patch applies).
    if (patch.tracks != null) {
      newTl = {
        ...newTl,
        transcript: { ...newTl.transcript, tracks: patch.tracks },
      }
    }
    if (patch.bindings != null) {
      newTl = {
        ...newTl,
        transcript: { ...newTl.transcript, bindings: patch.bindings },
      }
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
  | "tracks"
  | "bindings"
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
  if (patch.tracks != null) layers.push("tracks")
  if (patch.bindings != null) layers.push("bindings")
  if (patch.media != null) layers.push("media")
  if (patch.active_timeline_id != null) layers.push("active_timeline")
  return layers
}

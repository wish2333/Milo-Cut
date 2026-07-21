import type { Project, ProjectPatch, ProjectResponse, Timeline } from "@/types/project"
import { isProjectPatch } from "@/types/project"

export class PatchApplicationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "PatchApplicationError"
  }
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
        transcript: { ...newTl.transcript, segments: [...patch.segments] },
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

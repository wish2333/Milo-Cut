import { type Ref } from "vue"
import { call } from "@/bridge"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"

export function useEdit(
  project: Ref<Project | null>,
  onBeforeProjectUpdate?: (project: Project) => void,
) {
  function snapshot() {
    if (onBeforeProjectUpdate && project.value) {
      onBeforeProjectUpdate(project.value)
    }
  }

  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    const res = await call<Project>("update_segment_text", segmentId, text)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function updateSegmentTime(segmentId: string, field: "start" | "end", value: number): Promise<boolean> {
    const res = await call<Project>("update_segment", segmentId, { [field]: value })
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function mergeSegments(segmentIds: string[]): Promise<boolean> {
    const res = await call<Project>("merge_segments", segmentIds)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function splitSegment(
    segmentId: string,
    position: number,
    snapToWord = false,
  ): Promise<{ ok: boolean; snapOffsetMs: number | null }> {
    // v3.0.0 M1-4: snap_to_word snaps the cut to the nearest word boundary;
    // backend replies with `snap_offset_ms` for UI toast feedback.
    const res = await call<Project>("split_segment", segmentId, position, snapToWord)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      // snap_offset_ms is a sibling of `data` on the envelope (M1-4)
      const snapOffsetMs =
        (res as unknown as { snap_offset_ms?: number }).snap_offset_ms ?? null
      return { ok: true, snapOffsetMs }
    }
    return { ok: false, snapOffsetMs: null }
  }

  async function searchReplace(
    query: string,
    replacement: string,
    scope: string = "all",
  ): Promise<{ count: number; modified_ids: string[] } | null> {
    const res = await call<{ count: number; modified_ids: string[] }>(
      "search_replace", query, replacement, scope,
    )
    if (res.success && res.data) {
      snapshot()
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data
    }
    return null
  }

  async function markSegments(segmentIds: string[], action: "delete" | "keep"): Promise<boolean> {
    const res = await call<Project>("mark_segments", segmentIds, action)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllSuggestions(): Promise<number | null> {
    const res = await call<{ confirmed_count: number }>("confirm_all_suggestions")
    if (res.success && res.data) {
      snapshot()
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data.confirmed_count
    }
    return null
  }

  async function rejectAllSuggestions(): Promise<number | null> {
    const res = await call<{ rejected_count: number }>("reject_all_suggestions")
    if (res.success && res.data) {
      snapshot()
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data.rejected_count
    }
    return null
  }

  async function getEditSummary(): Promise<EditSummary | null> {
    const res = await call<EditSummary>("get_edit_summary")
    if (res.success && res.data) {
      return res.data
    }
    return null
  }

  async function deleteSegment(segmentId: string): Promise<string | null> {
    const res = await call<Project>("delete_segment", segmentId)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return null
    }
    return res.error ?? "Failed to delete segment"
  }

  async function deleteSilenceSegments(): Promise<boolean> {
    const res = await call<Project>("delete_silence_segments")
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function deleteSubtitleTrimEdits(): Promise<boolean> {
    const res = await call<Project>("delete_subtitle_trim_edits")
    if (res.success && res.data) {
      snapshot()
      project.value = res.data
      return true
    }
    return false
  }

  async function generateSubtitleKeepRanges(padding: number = 0.3): Promise<{
    keep_ranges: number
    delete_ranges: number
    new_edits: number
  } | null> {
    const res = await call<{
      keep_ranges: number
      delete_ranges: number
      new_edits: number
      project: Project
    }>("generate_subtitle_keep_ranges", padding)
    if (res.success && res.data) {
      snapshot()
      project.value = res.data.project
      return {
        keep_ranges: res.data.keep_ranges,
        delete_ranges: res.data.delete_ranges,
        new_edits: res.data.new_edits,
      }
    }
    return null
  }

  return {
    updateSegmentText,
    updateSegmentTime,
    mergeSegments,
    splitSegment,
    searchReplace,
    markSegments,
    confirmAllSuggestions,
    rejectAllSuggestions,
    getEditSummary,
    deleteSegment,
    deleteSilenceSegments,
    deleteSubtitleTrimEdits,
    generateSubtitleKeepRanges,
  }
}

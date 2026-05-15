import { type Ref } from "vue"
import { call } from "@/bridge"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"

export function useEdit(project: Ref<Project | null>) {

  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    const res = await call<Project>("update_segment_text", segmentId, text)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function updateSegmentTime(segmentId: string, field: "start" | "end", value: number): Promise<boolean> {
    const res = await call<Project>("update_segment", segmentId, { [field]: value })
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function mergeSegments(segmentIds: string[]): Promise<boolean> {
    const res = await call<Project>("merge_segments", segmentIds)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function splitSegment(segmentId: string, position: number): Promise<boolean> {
    const res = await call<Project>("split_segment", segmentId, position)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
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
      // Refresh project to get updated segments
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
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllSuggestions(): Promise<number | null> {
    const res = await call<{ confirmed_count: number }>("confirm_all_suggestions")
    if (res.success && res.data) {
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
  }
}

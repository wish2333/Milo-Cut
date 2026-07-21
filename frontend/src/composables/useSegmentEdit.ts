import { type ComputedRef, computed, type Ref, ref } from "vue"
import type { EditDecision, Project, ProjectResponse, Segment } from "@/types/project"
import { call, type ApiResponse } from "@/bridge"
import { resolveSegmentState, getEditForSegment } from "@/utils/segmentHelpers"
import type { SegmentState } from "@/utils/segmentHelpers"

const DEBOUNCE_MS = 300

export interface UseSegmentEditReturn {
  selectedSegmentId: Ref<string | null>
  selectedRange: Ref<{ start: number; end: number } | null>
  selectSegment: (id: string | null) => void
  selectRange: (start: number, end: number) => void
  clearSelection: () => void

  // v2.1.1 M4-1: multi-select mode
  selectionMode: Ref<boolean>
  selectedSegmentIds: Ref<Set<string>>
  selectedCount: ComputedRef<number>
  toggleSelectionMode: () => void
  handleSegmentClick: (segId: string, event: MouseEvent, orderedIds: string[]) => void
  clearMultiSelection: () => void

  updateSegmentTime: (segmentId: string, field: "start" | "end", value: number) => void
  updateSegmentText: (segmentId: string, text: string) => Promise<boolean>
  toggleEditStatus: (segment: Segment, nextStatus?: string) => Promise<boolean>

  getEffectiveStatus: (seg: Segment) => "normal" | "masked" | "kept"
  getEditStatus: (seg: Segment) => EditDecision["status"] | null
  resolveState: (seg: Segment) => SegmentState

  flushPendingUpdates: () => Promise<void>
  pendingCount: ComputedRef<number>
}

function activeEdits(p: Project): EditDecision[] {
  return p.timelines.find(t => t.id === p.active_timeline_id)?.edits ?? []
}

function activeTranscriptSegments(p: Project): Segment[] {
  return p.timelines.find(t => t.id === p.active_timeline_id)?.transcript?.segments ?? []
}

function replaceSegment(project: Project, segId: string, patch: Partial<Segment>): Project {
  return {
    ...project,
    timelines: project.timelines.map(tl =>
      tl.id === project.active_timeline_id
        ? {
            ...tl,
            transcript: {
              ...tl.transcript,
              segments: tl.transcript.segments.map(s =>
                s.id === segId ? { ...s, ...patch } : s,
              ),
            },
          }
        : tl,
    ),
  }
}

export function useSegmentEdit(
  project: Ref<Project>,
  onProjectUpdate: (project: ProjectResponse) => void,
  onBeforeProjectUpdate?: (project: Project) => void,
): UseSegmentEditReturn {
  const selectedSegmentId = ref<string | null>(null)
  const selectedRange = ref<{ start: number; end: number } | null>(null)

  // v2.1.1 M4-1: multi-select mode state
  const selectionMode = ref(false)
  const selectedSegmentIds = ref<Set<string>>(new Set())
  const lastSelectedId = ref<string | null>(null)
  const selectedCount = computed(() => selectedSegmentIds.value.size)

  const pendingMap = new Map<string, { timer: ReturnType<typeof setTimeout>; callback: () => void }>()
  const pendingCount = computed(() => pendingMap.size)

  // -- Selection --------------------------------------------------------

  function selectSegment(id: string | null) {
    selectedSegmentId.value = id
  }

  function selectRange(start: number, end: number) {
    selectedRange.value = { start, end }
  }

  function clearSelection() {
    selectedSegmentId.value = null
    selectedRange.value = null
  }

  // v2.1.1 M4-1: multi-select mode ------------------------------------

  function toggleSelectionMode() {
    selectionMode.value = !selectionMode.value
    if (!selectionMode.value) {
      clearMultiSelection()
    }
  }

  function clearMultiSelection() {
    selectedSegmentIds.value = new Set()
    lastSelectedId.value = null
  }

  function handleSegmentClick(segId: string, event: MouseEvent, orderedIds: string[]) {
    if (!selectionMode.value) return // play mode: caller handles seek
    const set = selectedSegmentIds.value
    if (event.ctrlKey || event.metaKey) {
      // Ctrl/Cmd: toggle single
      const next = new Set(set)
      if (next.has(segId)) next.delete(segId)
      else next.add(segId)
      selectedSegmentIds.value = next
    } else if (event.shiftKey && lastSelectedId.value) {
      // Shift: range select from last to current
      const startIdx = orderedIds.indexOf(lastSelectedId.value)
      const endIdx = orderedIds.indexOf(segId)
      const next = new Set(set)
      if (startIdx >= 0 && endIdx >= 0) {
        const from = Math.min(startIdx, endIdx)
        const to = Math.max(startIdx, endIdx)
        for (let i = from; i <= to; i++) next.add(orderedIds[i])
      }
      selectedSegmentIds.value = next
    } else {
      // Plain click in selection mode: toggle
      const next = new Set(set)
      if (next.has(segId)) next.delete(segId)
      else next.add(segId)
      selectedSegmentIds.value = next
    }
    lastSelectedId.value = segId
  }

  // -- Status queries ---------------------------------------------------

  function getEffectiveStatus(seg: Segment): "normal" | "masked" | "kept" {
    return resolveSegmentState(activeEdits(project.value), seg).styleClass
  }

  function getEditStatus(seg: Segment): EditDecision["status"] | null {
    const state = resolveSegmentState(activeEdits(project.value), seg)
    return state.displayStatus === "none" ? null : state.displayStatus
  }

  function resolveState(seg: Segment): SegmentState {
    return resolveSegmentState(activeEdits(project.value), seg)
  }

  // -- Debounced time updates -------------------------------------------

  function updateSegmentTime(segmentId: string, field: "start" | "end", value: number) {
    const prev = project.value
    const seg = activeTranscriptSegments(prev).find(s => s.id === segmentId)
    if (!seg) return

    if (onBeforeProjectUpdate) onBeforeProjectUpdate(prev)
    const optimistic = replaceSegment(prev, segmentId, { [field]: value })
    onProjectUpdate(optimistic)

    const key = `${segmentId}:${field}`
    const existing = pendingMap.get(key)
    if (existing) clearTimeout(existing.timer)

    const callback = async () => {
      const res = await call<Project>("update_segment", segmentId, { [field]: value })
      if (res.success && res.data) {
        onProjectUpdate(res.data)
      } else {
        onProjectUpdate(prev)
      }
    }

    const timer = setTimeout(() => {
      pendingMap.delete(key)
      callback()
    }, DEBOUNCE_MS)

    pendingMap.set(key, { timer, callback })
  }

  // -- Immediate text updates -------------------------------------------

  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value)
    const res = await call<Project>("update_segment_text", segmentId, text)
    if (res.success && res.data) {
      onProjectUpdate(res.data)
      return true
    }
    return false
  }

  // -- Toggle edit status -----------------------------------------------
  //
  // v2.3.2 G3 fix: consume the write call's return value (the backend's
  // `update_edit_decision` / `mark_segments` already return the full updated
  // Project). Fallback to `get_project()` only when the write call did not
  // return a usable Project payload, so one toggle never triggers two bridge
  // round-trips in the happy path. See docs/2.3.0/2.3.2-fix-report.md G3.
  //
  // v2.3.2 阶段 1.1 (evaluation-plan §4 stage 1.1 tasks 4-5):
  // - Returns Promise<boolean>: true = UI updated (happy path or fallback
  //   refresh); false = total failure (write + refresh both failed).
  // - Failure paths log to console.{warn,error} for operator observability;
  //   callers should surface user-visible errors based on the return value.
  // - Reuses ApiResponse<Project> instead of hand-written response shape.

  async function toggleEditStatus(segment: Segment, nextStatus?: string): Promise<boolean> {
    if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value)
    const edits = activeEdits(project.value)
    const state = resolveSegmentState(edits, segment)

    let writeRes: ApiResponse<Project> | null = null

    if (state.activeEdit) {
      const status = nextStatus ?? (
        state.activeEdit.status === "confirmed" ? "rejected"
        : state.activeEdit.status === "rejected" ? "confirmed"
        : "confirmed"
      )
      writeRes = await call<Project>("update_edit_decision", state.activeEdit.id, status)
    } else if (state.displayStatus === "rejected") {
      const rejectedEdit = getEditForSegment(edits, segment)
      if (rejectedEdit) {
        writeRes = await call<Project>("update_edit_decision", rejectedEdit.id, "confirmed")
      } else {
        // Invariant violation: state reports rejected but no edit matches.
        console.error(
          "[useSegmentEdit.toggleEditStatus] displayStatus='rejected' but no edit found",
          { segmentId: segment.id },
        )
      }
    } else {
      writeRes = await call<Project>("mark_segments", [segment.id], "delete", "confirmed")
    }

    if (writeRes && writeRes.success && writeRes.data) {
      onProjectUpdate(writeRes.data)
      return true
    }

    // Defensive fallback: write call returned no usable payload (e.g. older
    // backend, schema mismatch, or unexpected error). Refresh from source so
    // the UI reflects authoritative backend state instead of going stale.
    const writeError = writeRes?.error ?? "no payload"
    const projRes = await call<Project>("get_project")
    if (projRes.success && projRes.data) {
      onProjectUpdate(projRes.data)
      // Partial success: refresh ok but original write silently failed.
      console.warn(
        "[useSegmentEdit.toggleEditStatus] write call fell back to get_project()",
        { segmentId: segment.id, writeError },
      )
      return true
    }

    console.error(
      "[useSegmentEdit.toggleEditStatus] toggle fully failed (write + refresh)",
      { segmentId: segment.id, writeError, refreshError: projRes.error ?? "no payload" },
    )
    return false
  }

  // -- Flush ------------------------------------------------------------

  async function flushPendingUpdates(): Promise<void> {
    const entries = [...pendingMap.values()]
    pendingMap.clear()
    for (const entry of entries) {
      clearTimeout(entry.timer)
      entry.callback()
    }
  }

  return {
    selectedSegmentId,
    selectedRange,
    selectSegment,
    selectRange,
    clearSelection,

    // v2.1.1 M4-1
    selectionMode,
    selectedSegmentIds,
    selectedCount,
    toggleSelectionMode,
    handleSegmentClick,
    clearMultiSelection,

    updateSegmentTime,
    updateSegmentText,
    toggleEditStatus,

    getEffectiveStatus,
    getEditStatus,
    resolveState,

    flushPendingUpdates,
    pendingCount,
  }
}

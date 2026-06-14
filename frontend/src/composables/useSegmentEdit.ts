import { type ComputedRef, computed, type Ref, ref } from "vue"
import type { EditDecision, Project, Segment } from "@/types/project"
import { call } from "@/bridge"
import { resolveSegmentState, getEditForSegment } from "@/utils/segmentHelpers"
import type { SegmentState } from "@/utils/segmentHelpers"

const DEBOUNCE_MS = 300

export interface UseSegmentEditReturn {
  selectedSegmentId: Ref<string | null>
  selectedRange: Ref<{ start: number; end: number } | null>
  selectSegment: (id: string | null) => void
  selectRange: (start: number, end: number) => void
  clearSelection: () => void

  updateSegmentTime: (segmentId: string, field: "start" | "end", value: number) => void
  updateSegmentText: (segmentId: string, text: string) => Promise<boolean>
  toggleEditStatus: (segment: Segment, nextStatus?: string) => Promise<void>

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
  onProjectUpdate: (project: Project) => void,
  onBeforeProjectUpdate?: (project: Project) => void,
): UseSegmentEditReturn {
  const selectedSegmentId = ref<string | null>(null)
  const selectedRange = ref<{ start: number; end: number } | null>(null)

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

  async function toggleEditStatus(segment: Segment, nextStatus?: string): Promise<void> {
    if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value)
    const edits = activeEdits(project.value)
    const state = resolveSegmentState(edits, segment)

    if (state.activeEdit) {
      const status = nextStatus ?? (
        state.activeEdit.status === "confirmed" ? "rejected"
        : state.activeEdit.status === "rejected" ? "confirmed"
        : "confirmed"
      )
      await call<Project>("update_edit_decision", state.activeEdit.id, status)
    } else if (state.displayStatus === "rejected") {
      const rejectedEdit = getEditForSegment(edits, segment)
      if (rejectedEdit) {
        await call<Project>("update_edit_decision", rejectedEdit.id, "confirmed")
      }
    } else {
      await call("mark_segments", [segment.id], "delete", "confirmed")
    }

    const projRes = await call<Project>("get_project")
    if (projRes.success && projRes.data) {
      onProjectUpdate(projRes.data)
    }
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

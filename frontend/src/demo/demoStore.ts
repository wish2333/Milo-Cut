import { computed, reactive, toRaw } from "vue"
import type { EditDecision, Project, Segment } from "@/types/project"
import { createDemoCorrections, createDemoProject, createDemoWorkflow, type DemoCorrection } from "./demoProject"

export interface DemoExportRecord {
  id: string
  type: string
  created_at: string
}

export interface DemoWorkflowSession {
  workflowId: string
  status: "running" | "completed" | "cancelled"
  resolvedSegments: Record<string, "keep_first" | "keep_last" | "keep_all">
}

export interface DemoTaskState {
  id: string
  type: string
  status: "queued" | "running" | "completed" | "failed" | "cancelled"
  progress: { task_id?: string; percent: number; message: string }
  payload: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface DemoState {
  project: Project
  currentTime: number
  isPlaying: boolean
  playbackRate: number
  activeTask: DemoTaskState | null
  corrections: DemoCorrection[]
  workflows: ReturnType<typeof createDemoWorkflow>[]
  workflowSession: DemoWorkflowSession | null
  exportHistory: DemoExportRecord[]
  tasks: DemoTaskState[]
  revision: number
}

const state = reactive<DemoState>({
  project: createDemoProject(),
  currentTime: 0,
  isPlaying: false,
  playbackRate: 1,
  activeTask: null,
  corrections: [],
  workflows: [],
  workflowSession: null,
  exportHistory: [],
  tasks: [],
  revision: 0,
})

function clone<T>(value: T): T {
  const unwrap = (input: unknown): unknown => {
    const raw = toRaw(input)
    if (Array.isArray(raw)) return raw.map(unwrap)
    if (raw && typeof raw === "object") {
      return Object.fromEntries(Object.entries(raw).map(([key, item]) => [key, unwrap(item)]))
    }
    return raw
  }
  return structuredClone(unwrap(value)) as T
}

function activeTimeline(): Project["timelines"][number] {
  return state.project.timelines.find((timeline) => timeline.id === state.project.active_timeline_id) ?? state.project.timelines[0]
}

function touchProject() {
  state.revision += 1
  state.project = {
    ...state.project,
    project: { ...state.project.project, updated_at: new Date().toISOString() },
  }
}

function mutateTimeline(mutator: (timeline: Project["timelines"][number]) => void) {
  const project = clone(state.project)
  const timeline = project.timelines.find((item) => item.id === project.active_timeline_id)
  if (!timeline) return
  mutator(timeline)
  timeline.transcript.segments.sort((a, b) => a.start - b.start)
  state.project = project
  touchProject()
}

function allSegments() {
  return activeTimeline().transcript.segments
}

function editSummary() {
  const edits = activeTimeline().edits
  const confirmed = edits.filter((edit) => edit.action === "delete" && edit.status === "confirmed")
  const deleteDuration = confirmed.reduce((sum, edit) => sum + Math.max(0, edit.end - edit.start), 0)
  return {
    total_duration: state.project.media?.duration ?? 0,
    delete_duration: deleteDuration,
    delete_percent: state.project.media?.duration ? (deleteDuration / state.project.media.duration) * 100 : 0,
    edit_count: confirmed.length,
    warnings: state.workflowSession?.resolvedSegments && Object.values(state.workflowSession.resolvedSegments).includes("keep_all")
      ? ["存在同时保留删除建议和精华结果的片段，导出时将以保留为准。"]
      : [],
  }
}

function findSegment(segmentId: string): Segment | undefined {
  return allSegments().find((segment) => segment.id === segmentId)
}

function setEditStatus(editId: string, status: EditDecision["status"]) {
  mutateTimeline((timeline) => {
    const edit = timeline.edits.find((item) => item.id === editId)
    if (edit) edit.status = status
  })
}

function addSmartDeleteEdits() {
  const timeline = activeTimeline()
  const targets = allSegments().filter((segment) => segment.type === "subtitle").slice(1, 4)
  mutateTimeline((nextTimeline) => {
    targets.forEach((segment, index) => {
      if (!nextTimeline.edits.some((edit) => edit.id === `demo-llm-edit-${index + 1}`)) {
        nextTimeline.edits.push(makeEditFromSegment(`demo-llm-edit-${index + 1}`, segment, "llm_smart"))
      }
    })
  })
  return timeline
}

function makeEditFromSegment(id: string, segment: Segment, source: string): EditDecision {
  return {
    id,
    start: segment.start,
    end: segment.end,
    action: "delete",
    source,
    status: "pending",
    priority: 80,
    target_type: "segment",
    target_id: segment.id,
  }
}

function addHighlightResult() {
  const ids = allSegments().filter((segment) => segment.type === "subtitle").slice(3, 5).map((segment) => segment.id)
  mutateTimeline((timeline) => {
    timeline.analysis.results = timeline.analysis.results.filter((result) => result.type !== "llm_highlight")
    timeline.analysis.results.push({
      id: "demo-highlight-generated",
      type: "llm_highlight",
      segment_ids: ids,
      confidence: 0.91,
      detail: "表达完整、信息密度高，适合作为精华片段。",
    })
  })
}

function reset() {
  state.project = createDemoProject()
  state.currentTime = 0
  state.isPlaying = false
  state.playbackRate = 1
  state.activeTask = null
  state.corrections = createDemoCorrections(state.project)
  state.workflows = [createDemoWorkflow()]
  state.workflowSession = null
  state.exportHistory = []
  state.tasks = []
  state.revision = 0
}

reset()

export const demoStore = {
  state,
  project: computed(() => state.project),
  corrections: computed(() => state.corrections),
  getProject: () => clone(state.project),
  getCorrections: () => clone(state.corrections),
  getTask: (id: string) => clone(state.tasks.find((task) => task.id === id) ?? null),
  getTasks: () => clone(state.tasks),
  getEditSummary: () => editSummary(),
  getSegment: findSegment,
  setCurrentTime: (time: number) => { state.currentTime = Math.max(0, Math.min(state.project.media?.duration ?? 0, time)) },
  setPlaying: (playing: boolean) => { state.isPlaying = playing },
  setPlaybackRate: (rate: number) => { state.playbackRate = rate },
  createTask: (task: DemoTaskState) => { state.tasks.push(task); state.activeTask = task; return clone(task) },
  updateTask: (id: string, updates: Partial<DemoTaskState>) => {
    const index = state.tasks.findIndex((task) => task.id === id)
    if (index < 0) return null
    state.tasks[index] = { ...state.tasks[index], ...updates }
    if (state.activeTask?.id === id) state.activeTask = state.tasks[index]
    return clone(state.tasks[index])
  },
  updateSegment: (segmentId: string, field: "start" | "end", value: number) => {
    mutateTimeline((timeline) => {
      const segment = timeline.transcript.segments.find((item) => item.id === segmentId)
      if (segment) segment[field] = Math.max(0, Math.min(state.project.media?.duration ?? 90, value))
    })
    return clone(state.project)
  },
  updateSegmentText: (segmentId: string, text: string) => {
    mutateTimeline((timeline) => {
      const segment = timeline.transcript.segments.find((item) => item.id === segmentId)
      if (segment) segment.text = text
    })
    return clone(state.project)
  },
  setEditStatus: (editId: string, status: EditDecision["status"]) => { setEditStatus(editId, status); return clone(state.project) },
  setEditStatuses: (editIds: string[], status: EditDecision["status"]) => {
    mutateTimeline((timeline) => timeline.edits.forEach((edit) => { if (editIds.includes(edit.id)) edit.status = status }))
    return clone(state.project)
  },
  addSmartDeleteEdits: () => { addSmartDeleteEdits(); return clone(state.project) },
  addHighlightResult: () => { addHighlightResult(); return clone(state.project) },
  acceptCorrection: (id: string) => {
    const correction = state.corrections.find((item) => item.id === id)
    if (correction) {
      mutateTimeline((timeline) => {
        const segment = timeline.transcript.segments.find((item) => item.id === correction.segment_id)
        if (segment) segment.text = correction.corrected_text
      })
      state.corrections = state.corrections.filter((item) => item.id !== id)
    }
    return clone(state.project)
  },
  rejectCorrection: (id: string) => { state.corrections = state.corrections.filter((item) => item.id !== id); return clone(state.project) },
  acceptHighConfidenceCorrections: (threshold: number) => {
    const ids = state.corrections.filter((item) => item.confidence >= threshold).map((item) => item.id)
    ids.forEach((id) => { demoStore.acceptCorrection(id) })
    return { accepted_count: ids.length, remaining_count: state.corrections.length }
  },
  clearCorrections: () => { const count = state.corrections.length; state.corrections = []; return { cleared_count: count } },
  reset,
  touchProject,
  getWorkflow: () => clone(state.workflows),
  saveWorkflow: (workflow: ReturnType<typeof createDemoWorkflow>) => {
    const index = state.workflows.findIndex((item) => item.id === workflow.id)
    if (index >= 0) state.workflows[index] = workflow
    else state.workflows.push(workflow)
    return clone(workflow)
  },
  deleteWorkflow: (id: string) => { state.workflows = state.workflows.filter((workflow) => workflow.id !== id) },
  startWorkflow: (workflowId: string) => {
    state.workflowSession = { workflowId, status: "running", resolvedSegments: {} }
  },
  finishWorkflow: () => { if (state.workflowSession) state.workflowSession.status = "completed" },
  cancelWorkflow: () => { if (state.workflowSession) state.workflowSession.status = "cancelled" },
  resolveConflict: (segmentId: string, resolution: "keep_first" | "keep_last" | "keep_all") => {
    if (!state.workflowSession) state.workflowSession = { workflowId: "demo-workflow", status: "completed", resolvedSegments: {} }
    state.workflowSession.resolvedSegments[segmentId] = resolution
    const deleteEdit = activeTimeline().edits.find((edit) => edit.target_id === segmentId && edit.source === "llm_smart")
    if (deleteEdit) setEditStatus(deleteEdit.id, resolution === "keep_first" ? "confirmed" : "rejected")
  },
  recordExport: (type: string) => { state.exportHistory.unshift({ id: `demo-export-${Date.now()}`, type, created_at: new Date().toISOString() }) },
}

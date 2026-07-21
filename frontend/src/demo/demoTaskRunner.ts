import type { MiloTask, TaskProgress, TaskType } from "@/types/task"
import { EVENT_DEMO_PROJECT_UPDATED, EVENT_LLM_HIGHLIGHT_COMPLETED, EVENT_LLM_HIGHLIGHT_PROGRESS, EVENT_LLM_SMART_DELETE_COMPLETED, EVENT_LLM_SMART_DELETE_PROGRESS, EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED, EVENT_TASK_CANCELLED, EVENT_TASK_COMPLETED, EVENT_TASK_PROGRESS, EVENT_WORKFLOW_COMPLETED, EVENT_WORKFLOW_CONFLICTS_DETECTED, EVENT_WORKFLOW_HEARTBEAT, EVENT_WORKFLOW_STARTED, EVENT_WORKFLOW_STEP_COMPLETED, EVENT_WORKFLOW_STEP_PROGRESS, EVENT_WORKFLOW_STEP_STARTED } from "@/utils/events"
import { demoStore, type DemoTaskState } from "./demoStore"

export function emitDemoEvent(name: string, detail: unknown) {
  window.dispatchEvent(new CustomEvent(`pywebvue:${name}`, { detail }))
}

let sequence = 0
let activeRun = 0
let timers: ReturnType<typeof setTimeout>[] = []

function nextId(prefix: string) {
  sequence += 1
  return `demo-${prefix}-${sequence}`
}

function clearTimers() {
  timers.forEach((timer) => clearTimeout(timer))
  timers = []
}

function schedule(callback: () => void, delay: number) {
  const timer = setTimeout(() => {
    timers = timers.filter((item) => item !== timer)
    callback()
  }, delay)
  timers.push(timer)
}

function makeTask(type: string, payload: Record<string, unknown> = {}): DemoTaskState {
  const now = new Date().toISOString()
  return { id: nextId("task"), type, status: "queued", progress: { percent: 0, message: "等待演示任务启动" }, payload, created_at: now }
}

function updateProgress(task: DemoTaskState, percent: number, message: string) {
  const progress: TaskProgress = { task_id: task.id, percent, message }
  const updated = demoStore.updateTask(task.id, { status: "running", progress, started_at: task.started_at ?? new Date().toISOString() })
  if (updated) emitDemoEvent(EVENT_TASK_PROGRESS, progress)
  return updated
}

function completeTask(task: DemoTaskState, result: Record<string, unknown> = {}) {
  const updated = demoStore.updateTask(task.id, { status: "completed", progress: { task_id: task.id, percent: 100, message: "演示完成" }, result, completed_at: new Date().toISOString() })
  if (updated) emitDemoEvent(EVENT_TASK_COMPLETED, { task_id: task.id, task_type: task.type, result })
  return updated
}

export function createDemoTask(type: TaskType | string, payload: Record<string, unknown> = {}) {
  const task = makeTask(type, payload)
  return demoStore.createTask(task) as unknown as MiloTask
}

export function startDemoTask(taskId: string) {
  const task = demoStore.getTask(taskId)
  if (!task) return null
  clearTimers()
  const run = ++activeRun
  demoStore.updateTask(taskId, { status: "running", started_at: new Date().toISOString() })
  const steps = [
    [15, "读取演示时间轴"],
    [42, "分析字幕和停顿"],
    [72, "整理可解释建议"],
  ] as const
  steps.forEach(([percent, message], index) => schedule(() => {
    if (run !== activeRun) return
    updateProgress(task, percent, message)
    if (index === steps.length - 1) finishTask(task, run)
  }, 180 + index * 240))
  return demoStore.getTask(taskId)
}

function finishTask(task: DemoTaskState, run: number) {
  if (run !== activeRun) return
  let project = demoStore.getProject()
  if (task.type === "llm_smart_delete") {
    project = demoStore.addSmartDeleteEdits()
    emitDemoEvent(EVENT_LLM_SMART_DELETE_PROGRESS, { results: project.timelines[0].edits.filter((edit) => edit.source === "llm_smart").map((edit) => ({ segment_id: edit.target_id, action: "delete", reason: "重复表达或口头禅", category: "表达优化", confidence: 0.88 })) })
    emitDemoEvent(EVENT_LLM_SMART_DELETE_COMPLETED, { results: project.timelines[0].edits.filter((edit) => edit.source === "llm_smart").map((edit) => ({ segment_id: edit.target_id, action: "delete", reason: "重复表达或口头禅", category: "表达优化", confidence: 0.88 })) })
  } else if (task.type === "llm_subtitle_correction") {
    emitDemoEvent(EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED, { corrected_count: 2, stored_count: demoStore.getCorrections().length, uncovered_count: 0, partial: false })
  } else if (task.type === "llm_highlight") {
    project = demoStore.addHighlightResult()
    const results = project.timelines[0].analysis.results
    const ids = results.length > 0 ? results[results.length - 1].segment_ids : []
    emitDemoEvent(EVENT_LLM_HIGHLIGHT_PROGRESS, { results: ids.map((segment_id: string) => ({ segment_id, highlight_reason: "信息密度高", density: "high" })) })
    emitDemoEvent(EVENT_LLM_HIGHLIGHT_COMPLETED, { results: ids.map((segment_id: string) => ({ segment_id, highlight_reason: "信息密度高", density: "high" })), total_duration: 13, target_duration: 30 })
  } else if (task.type.startsWith("export_")) {
    demoStore.recordExport(task.type)
  }
  completeTask(task, { project })
}

export function cancelDemoTask(taskId?: string) {
  activeRun += 1
  clearTimers()
  const task = taskId ? demoStore.getTask(taskId) : demoStore.state.activeTask
  if (!task) return
  demoStore.updateTask(task.id, { status: "cancelled", progress: { task_id: task.id, percent: 0, message: "演示任务已取消" } })
  emitDemoEvent(EVENT_TASK_CANCELLED, { task_id: task.id, task_type: task.type })
}

export function startDemoLlmTask(type: "llm_smart_delete" | "llm_subtitle_correction" | "llm_highlight") {
  const task = createDemoTask(type)
  startDemoTask(task.id)
  return task
}

export function startDemoWorkflow(workflowId: string) {
  clearTimers()
  const run = ++activeRun
  demoStore.startWorkflow(workflowId)
  const steps = ["llm_smart_delete", "llm_subtitle_correction", "llm_highlight"]
  emitDemoEvent(EVENT_WORKFLOW_STARTED, { workflow_instance_id: nextId("workflow"), workflow_name: "演示：从清理到精华", total_steps: steps.length, steps: steps.map((type, index) => ({ index, type, status: "queued", edits_count: 0 })) })
  steps.forEach((type, index) => {
    schedule(() => {
      if (run !== activeRun) return
      emitDemoEvent(EVENT_WORKFLOW_STEP_STARTED, { step_index: index, status: "running" })
      emitDemoEvent(EVENT_WORKFLOW_STEP_PROGRESS, { step_index: index, percent: 50, message: `正在执行 ${type}` })
      schedule(() => {
        if (run !== activeRun) return
        if (type === "llm_smart_delete") demoStore.addSmartDeleteEdits()
        if (type === "llm_highlight") demoStore.addHighlightResult()
        emitDemoEvent(EVENT_WORKFLOW_STEP_PROGRESS, { step_index: index, percent: 100, message: "步骤完成" })
        emitDemoEvent(EVENT_WORKFLOW_STEP_COMPLETED, { step_index: index, edits_count: type === "llm_smart_delete" ? 3 : 1 })
        emitDemoEvent(EVENT_WORKFLOW_HEARTBEAT, {})
        if (index === steps.length - 1) {
          demoStore.finishWorkflow()
          emitDemoEvent(EVENT_WORKFLOW_COMPLETED, { total_edits: 4 })
          const project = demoStore.getProject()
          const smartEdit = project.timelines[0].edits.find((edit) => edit.source === "llm_smart")
          const segment = project.timelines[0].transcript.segments.find((item) => item.id === smartEdit?.target_id)
          if (segment && smartEdit) {
            emitDemoEvent(EVENT_DEMO_PROJECT_UPDATED, project)
            emitDemoEvent(EVENT_WORKFLOW_CONFLICTS_DETECTED, { conflicts: [{ segment_id: segment.id, segment_text: segment.text, segment_start: segment.start, segment_end: segment.end, decisions: [{ edit_id: smartEdit.id, action: "delete", source: "llm_smart", step_type: "llm_smart_delete", step_index: 0, reason: "重复表达" }, { edit_id: "demo-highlight-generated", action: "keep", source: "llm_highlight", step_type: "llm_highlight", step_index: 2, reason: "高信息密度" }] }], total_conflicts: 1 })
          }
        }
      }, 420)
    }, index * 760)
  })
  return { success: true, data: { workflow_instance_id: "demo-workflow-instance" } }
}

export function resetDemoTasks() {
  activeRun += 1
  clearTimers()
}

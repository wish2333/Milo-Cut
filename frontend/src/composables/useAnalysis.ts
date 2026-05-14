import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { useTask } from "./useTask"
import { EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project } from "@/types/project"
import type { TaskType } from "@/types/task"

const ANALYSIS_TASKS: TaskType[] = [
  "silence_detection",
  "filler_detection",
  "error_detection",
  "full_analysis",
]

export function useAnalysis(project: Ref<Project | null>) {
  const { on } = useBridge()
  const { createTask, startTask, tasks, activeTask, isRunning } = useTask()

  const isDetecting = computed(() => {
    const t = activeTask.value
    return t !== null && ANALYSIS_TASKS.includes(t.type) && isRunning.value
  })

  const detectionProgress = computed(() => {
    const t = activeTask.value
    if (t && ANALYSIS_TASKS.includes(t.type)) {
      return t.progress
    }
    return null
  })

  on(EVENT_TASK_COMPLETED, (data: { task_id: string; result?: { project?: Project } }) => {
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task && ANALYSIS_TASKS.includes(task.type) && data.result?.project) {
      project.value = data.result.project
    }
  })

  async function runSilenceDetection(): Promise<boolean> {
    const task = await createTask("silence_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runFillerDetection(): Promise<boolean> {
    const task = await createTask("filler_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runErrorDetection(): Promise<boolean> {
    const task = await createTask("error_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runFullAnalysis(): Promise<boolean> {
    const task = await createTask("full_analysis")
    if (!task) return false
    return await startTask(task.id)
  }

  async function confirmEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "confirmed")
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function rejectEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "rejected")
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllEdits(): Promise<boolean> {
    const edits = project.value?.edits ?? []
    let ok = true
    for (const edit of edits) {
      if (edit.status === "pending" && edit.action === "delete") {
        const res = await confirmEdit(edit.id)
        if (!res) ok = false
      }
    }
    return ok
  }

  return {
    isDetecting,
    detectionProgress,
    runSilenceDetection,
    runFillerDetection,
    runErrorDetection,
    runFullAnalysis,
    confirmEdit,
    rejectEdit,
    confirmAllEdits,
  }
}

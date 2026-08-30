import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { useTask } from "./useTask"
import { EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project } from "@/types/project"
import type { TaskType } from "@/types/task"
import type { UndoLayer } from "@/utils/undoRecords"

const ANALYSIS_TASKS: TaskType[] = [
  "silence_detection",
  "transcription",
]

export function useAnalysis(
  project: Ref<Project | null>,
  onBeforeProjectUpdate?: (project: Project, layers?: UndoLayer[], label?: string) => void,
) {
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
      // C1: task results rebuild the transcript (silence/transcription)
      if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["segments", "edits"], "分析结果回填")
      project.value = data.result.project
    }
  })

  async function runSilenceDetection(): Promise<boolean> {
    const task = await createTask("silence_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runTranscription(payload?: Record<string, unknown>): Promise<boolean> {
    const task = await createTask("transcription", payload)
    if (!task) return false
    return await startTask(task.id)
  }

  async function confirmEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "confirmed")
    if (res.success && res.data) {
      if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["edits"], "编辑决策")
      project.value = res.data
      return true
    }
    return false
  }

  async function rejectEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "rejected")
    if (res.success && res.data) {
      if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["edits"], "编辑决策")
      project.value = res.data
      return true
    }
    return false
  }

  /** v2.1.1: Reset an edit back to pending (undo confirm/reject). */
  async function resetEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "pending")
    if (res.success && res.data) {
      if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["edits"], "编辑决策")
      project.value = res.data
      return true
    }
    return false
  }

  /** v2.1.1: Batch update edit statuses (group-level operations). */
  async function batchUpdateEdits(
    editIds: string[],
    status: "confirmed" | "rejected" | "pending",
  ): Promise<boolean> {
    if (editIds.length === 0) return false
    if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["edits"], "编辑决策")
    const res = await call<Project>("update_edit_decisions_batch", editIds, status)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  /** v2.1.1: Permanently delete a group of edits (not just reset status). */
  async function deleteEdits(editIds: string[]): Promise<boolean> {
    if (editIds.length === 0) return false
    if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value, ["edits"], "编辑决策")
    const res = await call<Project>("delete_edit_decisions_batch", editIds)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllEdits(): Promise<boolean> {
    const tl = project.value?.timelines.find(t => t.id === project.value?.active_timeline_id)
    const edits = tl?.edits ?? []
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
    activeTask,
    runSilenceDetection,
    runTranscription,
    confirmEdit,
    rejectEdit,
    resetEdit,
    batchUpdateEdits,
    deleteEdits,
    confirmAllEdits,
  }
}

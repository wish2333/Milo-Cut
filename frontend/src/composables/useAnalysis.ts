import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { useTask } from "./useTask"
import { EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project } from "@/types/project"

export function useAnalysis(project: Ref<Project | null>) {
  const { on } = useBridge()
  const { createTask, startTask, tasks, activeTask, isRunning } = useTask()

  const isDetecting = computed(() => {
    const t = activeTask.value
    return t !== null && t.type === "silence_detection" && isRunning.value
  })

  const detectionProgress = computed(() => {
    const t = activeTask.value
    if (t && t.type === "silence_detection") {
      return t.progress
    }
    return null
  })

  on(EVENT_TASK_COMPLETED, (data: { task_id: string; result?: { project?: Project } }) => {
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task?.type === "silence_detection" && data.result?.project) {
      project.value = data.result.project
    }
  })

  async function runSilenceDetection(): Promise<boolean> {
    const task = await createTask("silence_detection")
    if (!task) return false

    const startRes = await startTask(task.id)
    return startRes
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
    confirmEdit,
    rejectEdit,
    confirmAllEdits,
  }
}

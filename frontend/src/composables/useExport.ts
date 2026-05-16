import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useTask } from "./useTask"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"
import type { TaskType } from "@/types/task"

export function useExport(project: Ref<Project | null>) {
  const { createTask, startTask, activeTask, isRunning } = useTask()

  const isExporting = computed(() => {
    const t = activeTask.value
    return t !== null
      && (t.type === "export_video" || t.type === "export_subtitle" || t.type === "export_audio")
      && isRunning.value
  })

  const exportProgress = computed(() => {
    const t = activeTask.value
    if (t && (t.type === "export_video" || t.type === "export_subtitle" || t.type === "export_audio")) {
      return t.progress
    }
    return null
  })

  const confirmedEdits = computed(() =>
    (project.value?.edits ?? []).filter(e => e.status === "confirmed" && e.action === "delete")
  )

  const estimatedSaving = computed(() => {
    return confirmedEdits.value.reduce((sum, e) => sum + (e.end - e.start), 0)
  })

  async function getExportSummary(): Promise<EditSummary | null> {
    const res = await call<EditSummary>("get_edit_summary")
    if (res.success && res.data) {
      return res.data
    }
    return null
  }

  async function createExportTask(
    type: TaskType,
    payload?: Record<string, unknown>,
  ): Promise<string | null> {
    const task = await createTask(type, payload)
    if (!task) return null
    const ok = await startTask(task.id)
    if (!ok) return null
    return task.id
  }

  return {
    isExporting,
    exportProgress,
    confirmedEdits,
    estimatedSaving,
    getExportSummary,
    createExportTask,
  }
}

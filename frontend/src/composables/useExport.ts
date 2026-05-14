import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useTask } from "./useTask"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"

export function useExport(project: Ref<Project | null>) {
  const { createTask, startTask, activeTask, isRunning } = useTask()

  const isExporting = computed(() => {
    const t = activeTask.value
    return t !== null
      && (t.type === "export_video" || t.type === "export_subtitle")
      && isRunning.value
  })

  const exportProgress = computed(() => {
    const t = activeTask.value
    if (t && (t.type === "export_video" || t.type === "export_subtitle")) {
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

  async function exportVideo(outputPath?: string): Promise<boolean> {
    const payload: Record<string, string> = {}
    if (outputPath) {
      payload.output_path = outputPath
    }
    const task = await createTask("export_video", payload)
    if (!task) return false
    return await startTask(task.id)
  }

  async function exportSrt(outputPath?: string): Promise<boolean> {
    const payload: Record<string, string> = {}
    if (outputPath) {
      payload.output_path = outputPath
    }
    const task = await createTask("export_subtitle", payload)
    if (!task) return false
    return await startTask(task.id)
  }

  return {
    isExporting,
    exportProgress,
    confirmedEdits,
    estimatedSaving,
    getExportSummary,
    exportVideo,
    exportSrt,
  }
}

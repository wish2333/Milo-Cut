import { computed, type Ref } from "vue"
import { useTask } from "./useTask"
import type { Project } from "@/types/project"

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
    exportVideo,
    exportSrt,
  }
}

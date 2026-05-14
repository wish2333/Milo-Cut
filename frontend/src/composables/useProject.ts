import { ref, computed } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { EVENT_PROJECT_SAVED, EVENT_PROJECT_DIRTY } from "@/utils/events"
import type { Project, Segment, EditDecision, MediaInfo } from "@/types/project"

export function useProject() {
  const { on } = useBridge()

  const project = ref<Project | null>(null)
  const isDirty = ref(false)
  const loading = ref(false)

  const segments = computed<Segment[]>(() => project.value?.transcript?.segments ?? [])
  const edits = computed<EditDecision[]>(() => project.value?.edits ?? [])
  const mediaDuration = computed<number>(() => project.value?.media?.duration ?? 0)
  const mediaInfo = computed<MediaInfo | null>(() => project.value?.media ?? null)

  on(EVENT_PROJECT_SAVED, () => {
    isDirty.value = false
  })

  on(EVENT_PROJECT_DIRTY, () => {
    isDirty.value = true
  })

  async function createProject(name: string, mediaPath: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("create_project", name, mediaPath)
      if (res.success && res.data) {
        project.value = res.data
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function openProject(path: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("open_project", path)
      if (res.success && res.data) {
        project.value = res.data
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function saveProject(): Promise<boolean> {
    const res = await call<void>("save_project")
    return res.success
  }

  async function closeProject(): Promise<boolean> {
    const res = await call<void>("close_project")
    if (res.success) {
      project.value = null
      isDirty.value = false
    }
    return res.success
  }

  return {
    project,
    isDirty,
    loading,
    segments,
    edits,
    mediaDuration,
    mediaInfo,
    createProject,
    openProject,
    saveProject,
    closeProject,
  }
}

import { ref, computed } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { EVENT_TASK_PROGRESS, EVENT_TASK_COMPLETED, EVENT_TASK_FAILED } from "@/utils/events"
import type { MiloTask, TaskType } from "@/types/task"

const tasks = ref<MiloTask[]>([])

let listenersRegistered = false

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  const { on } = useBridge()

  on<{ task_id: string; percent: number; message: string }>(
    EVENT_TASK_PROGRESS,
    ({ task_id, percent, message }) => {
      const idx = tasks.value.findIndex((t) => t.id === task_id)
      if (idx >= 0) {
        tasks.value[idx] = {
          ...tasks.value[idx],
          progress: { percent, message },
        }
      }
    },
  )

  on<{ task_id: string; result?: Record<string, unknown> }>(
    EVENT_TASK_COMPLETED,
    ({ task_id, result }) => {
      const idx = tasks.value.findIndex((t) => t.id === task_id)
      if (idx >= 0) {
        tasks.value[idx] = {
          ...tasks.value[idx],
          status: "completed",
          progress: { percent: 100, message: "" },
          result,
        }
      }
    },
  )

  on<{ task_id: string; error: string }>(EVENT_TASK_FAILED, ({ task_id, error }) => {
    const idx = tasks.value.findIndex((t) => t.id === task_id)
    if (idx >= 0) {
      tasks.value[idx] = {
        ...tasks.value[idx],
        status: "failed",
        error,
      }
    }
  })
}

export function useTask() {
  ensureListeners()

  const activeTask = computed<MiloTask | null>(
    () => tasks.value.find((t) => t.status === "running") ?? null,
  )
  const isRunning = computed<boolean>(() => tasks.value.some((t) => t.status === "running"))

  async function createTask(
    type: TaskType,
    payload?: Record<string, unknown>,
  ): Promise<MiloTask | null> {
    const res = await call<MiloTask>("create_task", type, payload)
    if (res.success && res.data) {
      tasks.value = [...tasks.value, res.data]
      return res.data
    }
    return null
  }

  async function startTask(id: string): Promise<boolean> {
    const res = await call<MiloTask>("start_task", id)
    if (res.success && res.data) {
      const idx = tasks.value.findIndex((t) => t.id === id)
      if (idx >= 0) {
        tasks.value[idx] = res.data
      }
      return true
    }
    return false
  }

  async function cancelTask(id: string): Promise<boolean> {
    const res = await call<void>("cancel_task", id)
    if (res.success) {
      const idx = tasks.value.findIndex((t) => t.id === id)
      if (idx >= 0) {
        tasks.value[idx] = { ...tasks.value[idx], status: "cancelled" }
      }
    }
    return res.success
  }

  async function getTask(id: string): Promise<MiloTask | null> {
    const res = await call<MiloTask>("get_task", id)
    return res.success && res.data ? res.data : null
  }

  async function listTasks(): Promise<MiloTask[]> {
    const res = await call<MiloTask[]>("list_tasks")
    if (res.success && res.data) {
      tasks.value = res.data
      return res.data
    }
    return []
  }

  return {
    tasks,
    activeTask,
    isRunning,
    createTask,
    startTask,
    cancelTask,
    getTask,
    listTasks,
  }
}

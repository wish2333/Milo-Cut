import { ref, computed } from "vue"
import { call, onEvent } from "@/bridge"
import { EVENT_TASK_PROGRESS, EVENT_TASK_COMPLETED, EVENT_TASK_FAILED } from "@/utils/events"
import type { MiloTask, TaskType } from "@/types/task"

const tasks = ref<MiloTask[]>([])

// Track when each task started running, for fallback polling
const taskStartTimes = new Map<string, number>()
const POLL_DELAY_MS = 5000

async function fetchTask(id: string): Promise<MiloTask | null> {
  const res = await call<MiloTask>("get_task", id)
  return res.success && res.data ? res.data : null
}

let listenersRegistered = false

function ensureListeners() {
  if (listenersRegistered) return
  listenersRegistered = true

  // Use onEvent directly (not useBridge) so these singleton listeners
  // are NOT tied to any component's onUnmounted lifecycle.
  onEvent<{ task_id: string; percent: number; message: string }>(
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

  onEvent<{ task_id: string; result?: Record<string, unknown> }>(
    EVENT_TASK_COMPLETED,
    ({ task_id, result }) => {
      taskStartTimes.delete(task_id)
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

  onEvent<{ task_id: string; error: string }>(EVENT_TASK_FAILED, ({ task_id, error }) => {
    taskStartTimes.delete(task_id)
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

async function pollRunningTasks() {
  const now = Date.now()
  for (const task of tasks.value) {
    if (task.status !== "running") continue
    const startTime = taskStartTimes.get(task.id)
    if (!startTime || now - startTime < POLL_DELAY_MS) continue

    // Task has been running longer than POLL_DELAY_MS without an event — poll backend
    const backend = await fetchTask(task.id)
    if (backend && backend.status !== "running") {
      taskStartTimes.delete(task.id)
      const idx = tasks.value.findIndex((t) => t.id === task.id)
      if (idx >= 0) {
        tasks.value[idx] = backend
      }
    }
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

function ensurePolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollRunningTasks, 3000)
}

export function useTask() {
  ensureListeners()
  ensurePolling()

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
      // Track start time for fallback polling (in case TASK_COMPLETED event is lost)
      taskStartTimes.set(id, Date.now())
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
    return fetchTask(id)
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

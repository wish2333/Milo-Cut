import { ref, computed, onUnmounted } from "vue"
import { call, onEvent } from "@/bridge"
import { EVENT_TASK_COMPLETED, EVENT_TASK_FAILED } from "@/utils/events"

export interface BatchStatus {
  batch_id: string
  total_count: number
  completed_count: number
  failed_count: number
  running_count: number
  queued_count: number
  cancelled_count: number
  status: string
}

export function useBatch() {
  const batchId = ref<string | null>(null)
  const taskIds = ref<string[]>([])
  const totalCount = ref(0)
  const completedCount = ref(0)
  const failedCount = ref(0)
  const runningCount = ref(0)
  const queuedCount = ref(0)
  const cancelledCount = ref(0)
  const batchStatus = ref<string>("idle")
  const isPolling = ref(false)

  let pollTimer: ReturnType<typeof setInterval> | null = null
  const cleanups: (() => void)[] = []

  function setupEventListeners() {
    const off1 = onEvent<{ task_id: string }>(
      EVENT_TASK_COMPLETED,
      ({ task_id }) => {
        if (taskIds.value.includes(task_id)) {
          completedCount.value++
          updateDerivedStatus()
        }
      },
    )
    const off2 = onEvent<{ task_id: string; error: string }>(
      EVENT_TASK_FAILED,
      ({ task_id }) => {
        if (taskIds.value.includes(task_id)) {
          failedCount.value++
          updateDerivedStatus()
        }
      },
    )
    cleanups.push(off1, off2)
  }

  function updateDerivedStatus() {
    const done = completedCount.value + failedCount.value + cancelledCount.value
    if (done >= totalCount.value) {
      batchStatus.value = "completed"
      stopPolling()
    } else if (runningCount.value > 0) {
      batchStatus.value = "running"
    } else {
      batchStatus.value = "queued"
    }
  }

  async function createBatch(projectPaths: string[]): Promise<boolean> {
    const res = await call<{
      batch_id: string
      task_ids: string[]
      total_count: number
    }>("create_batch_export", projectPaths)

    if (!res.success || !res.data) return false

    batchId.value = res.data.batch_id
    taskIds.value = res.data.task_ids
    totalCount.value = res.data.total_count
    completedCount.value = 0
    failedCount.value = 0
    runningCount.value = 0
    queuedCount.value = res.data.total_count
    cancelledCount.value = 0
    batchStatus.value = "running"

    setupEventListeners()
    startPolling()
    return true
  }

  async function pollBatchStatus(): Promise<void> {
    if (!batchId.value) return

    const res = await call<BatchStatus>("get_batch_status", batchId.value)
    if (!res.success || !res.data) return

    completedCount.value = res.data.completed_count
    failedCount.value = res.data.failed_count
    runningCount.value = res.data.running_count
    queuedCount.value = res.data.queued_count
    cancelledCount.value = res.data.cancelled_count
    batchStatus.value = res.data.status

    if (res.data.status === "completed") {
      stopPolling()
    }
  }

  function startPolling() {
    if (pollTimer) return
    isPolling.value = true
    pollTimer = setInterval(pollBatchStatus, 3000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    isPolling.value = false
  }

  function reset() {
    stopPolling()
    for (const off of cleanups) off()
    cleanups.length = 0
    batchId.value = null
    taskIds.value = []
    totalCount.value = 0
    completedCount.value = 0
    failedCount.value = 0
    runningCount.value = 0
    queuedCount.value = 0
    cancelledCount.value = 0
    batchStatus.value = "idle"
  }

  onUnmounted(reset)

  const progressPercent = computed(() => {
    if (totalCount.value === 0) return 0
    return Math.round(
      ((completedCount.value + failedCount.value) / totalCount.value) * 100,
    )
  })

  const isRunning = computed(() => batchStatus.value === "running")
  const isCompleted = computed(() => batchStatus.value === "completed")
  const isIdle = computed(() => batchStatus.value === "idle")

  return {
    batchId,
    taskIds,
    totalCount,
    completedCount,
    failedCount,
    runningCount,
    queuedCount,
    cancelledCount,
    batchStatus,
    progressPercent,
    isRunning,
    isCompleted,
    isIdle,
    isPolling,
    createBatch,
    pollBatchStatus,
    reset,
  }
}

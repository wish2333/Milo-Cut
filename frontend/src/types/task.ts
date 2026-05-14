export type TaskStatus = "queued" | "running" | "completed" | "failed" | "cancelled"

export type TaskType =
  // MVP
  | "silence_detection"
  | "export_video"
  | "export_subtitle"
  // P1
  | "transcription"
  | "vad_analysis"
  | "waveform_generation"

export interface TaskProgress {
  percent: number
  message: string
}

export interface MiloTask {
  id: string
  type: TaskType
  status: TaskStatus
  progress: TaskProgress
  payload: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

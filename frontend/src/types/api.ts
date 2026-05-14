export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  code?: string
}

export type BridgeMethod =
  // System
  | "get_app_info"
  | "select_files"
  | "select_file"
  | "open_folder"
  | "get_dropped_files"
  // Project
  | "create_project"
  | "open_project"
  | "save_project"
  | "close_project"
  // Subtitle
  | "import_srt"
  // FFmpeg
  | "probe_media"
  | "detect_silence"
  // Tasks
  | "create_task"
  | "start_task"
  | "cancel_task"
  | "get_task"
  | "list_tasks"

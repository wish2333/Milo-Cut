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
  | "get_video_url"
  | "stop_media_server"
  // Tasks
  | "create_task"
  | "start_task"
  | "cancel_task"
  | "get_task"
  | "list_tasks"
  // Project State
  | "get_project"
  | "update_edit_decision"
  | "update_segment"
  | "select_export_path"
  // Phase 1: Edit Operations
  | "update_segment_text"
  | "merge_segments"
  | "split_segment" | "add_segment"
  | "search_replace"
  | "mark_segments"
  | "confirm_all_suggestions"
  | "reject_all_suggestions"
  | "get_edit_summary"
  | "validate_srt"
  | "get_recent_projects"
  | "get_settings"
  | "update_settings"

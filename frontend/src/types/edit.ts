export interface EditSummary {
  total_duration: number
  delete_duration: number
  delete_percent: number
  edit_count: number
  warnings: string[]
}

export interface RecentProject {
  name: string
  path: string
  updated_at: string
  created_at: string
}

export interface AppSettings {
  ffmpeg_path: string
  ffprobe_path: string
  theme: string
  language: string
  silence_threshold_db: number
  silence_min_duration: number
  filler_words: string[]
  error_trigger_words: string[]
}

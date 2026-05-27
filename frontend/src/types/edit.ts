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
  // FFmpeg paths
  ffmpeg_path: string
  ffprobe_path: string
  // General
  theme: string
  language: string
  // Silence detection
  silence_threshold_db: number
  silence_min_duration: number
  silence_margin: number
  silence_subtitle_padding: number
  trim_subtitles_on_silence_overlap: boolean
  // Analysis
  filler_words: string[]
  error_trigger_words: string[]
  // Export transitions
  export_fade_duration: number
  export_transition_mode: string
  // Export encoding
  export_video_codec: string
  export_audio_codec: string
  export_audio_bitrate: string
  export_preset: string
  export_crf: number
  export_resolution: string
  export_ffmpeg_transitions: boolean
  export_ffmpeg_fade_duration: number
  export_ffmpeg_fade_mode: string
  // ASR / AI
  asr_engine: "faster-whisper" | "qwen3-asr"
  asr_model_size: string
  asr_language: string
  asr_device: "cpu" | "cuda" | "auto"
  asr_compute_type: "int8" | "float16" | "float32"
  duplicate_threshold: number
  duplicate_min_length: number
}

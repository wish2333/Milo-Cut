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
  asr_plugin_id: string
  asr_model_size: string
  asr_language: string
  asr_device: "cpu" | "cuda" | "auto"
  asr_compute_type: "int8" | "float16" | "float32"
  asr_vad_filter: boolean
  // Engine-prefixed keys (flat dict, not nested)
  whisper_compute_type: "int8" | "int8_float16" | "float16" | "float32"
  qwen_compute_type: "bfloat16" | "float16" | "float32"
  whisper_vad_threshold: number
  whisper_vad_min_silence_ms: number
  duplicate_threshold: number
  duplicate_min_length: number
  model_dir: string
}

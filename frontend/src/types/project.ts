export type EditStatus = "pending" | "confirmed" | "rejected"

export type SegmentType = "subtitle" | "silence"

export interface Word {
  word: string
  start: number
  end: number
  confidence: number
}

export interface Segment {
  id: string
  version: number
  type: SegmentType
  start: number
  end: number
  text: string
  words?: Word[]
  speaker: string
  dirty_flags?: Record<string, boolean>
}

export interface EditDecision {
  id: string
  start: number
  end: number
  action: "delete" | "keep"
  source: string
  analysis_id?: string
  status: EditStatus
  priority: number
  target_type: "segment" | "range"
  target_id?: string
}

export interface MediaInfo {
  path: string
  media_hash: string
  duration: number
  format: string
  width: number
  height: number
  fps: number
  audio_channels: number
  sample_rate: number
  bit_rate: number
  proxy_path?: string
  waveform_path?: string
}

export interface ProjectMeta {
  name: string
  created_at: string
  updated_at: string
}

export interface TranscriptData {
  engine: string
  language: string
  segments: Segment[]
}

export interface AnalysisData {
  last_run: string | null
  results: AnalysisResult[]
}

export interface Project {
  schema_version: number
  project: ProjectMeta
  media: MediaInfo | null
  transcript: TranscriptData
  analysis: AnalysisData
  edits: EditDecision[]
  topic_drift: TopicDriftData
}

export interface AnalysisResult {
  id: string
  type: "filler" | "error" | "duplicate" | "punctuation" | "topic_drift"
  segment_ids: string[]
  confidence: number
  detail: string
}

export interface TopicDriftResult {
  segment_id: string
  topic: string
  relevance: number
  confidence: number
  reason: string
}

export interface TopicDriftData {
  topic_description: string
  results: TopicDriftResult[]
  transcript_hash: string
  last_run: string | null
  token_usage: Record<string, number>
}

// ================================================================
// Plugin / Model types
// ================================================================

export interface PluginInfo {
  plugin_id: string
  display_name: string
  engine: "faster-whisper" | "qwen3-asr"
  version: string
  status: "installed" | "installing" | "not_installed" | "error"
  installed_at: string
  venv_path: string
}

export interface ModelInfo {
  model_id: string
  display_name: string
  plugin_id: string
  engine: "faster-whisper" | "qwen3-asr"
  size_bytes: number
  local_path: string
  status: "downloaded" | "downloading" | "not_downloaded"
}



export interface ModelMirror {
  id: string
  display_name: string
}

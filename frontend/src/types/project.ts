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
}

export interface Project {
  schema_version: number
  project: ProjectMeta
  media: MediaInfo | null
  transcript: TranscriptData
  analysis: AnalysisData
  edits: EditDecision[]
}

export interface AnalysisResult {
  id: string
  type: "silence" | "filler" | "error" | "repetition"
  segment_ids: string[]
  confidence: number
  detail: string
}

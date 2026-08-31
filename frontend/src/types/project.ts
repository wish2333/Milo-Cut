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
  // v3.0.0 M11-2: read-only extension tracks (bindings written, not consumed)
  tracks?: SubtitleTrack[]
  bindings?: TrackBinding[]
}

export interface SubtitleTrack {
  id: string
  role: "extension" | "translation" | "caption"
  name: string
  language: string
  segments: Segment[]
}

export interface TrackBinding {
  id: string
  track_id: string
  main_segment_id: string
  extension_segment_id: string
  start_offset: number
  end_offset: number
}

export interface AnalysisData {
  last_run: string | null
  results: AnalysisResult[]
}

export interface Project {
  schema_version: number
  project: ProjectMeta
  media: MediaInfo | null
  timelines: Timeline[]
  active_timeline_id: string
}

// ================================================================
// v2.3.2 stage 2: ProjectPatch envelope
// ================================================================

export interface ProjectPatch {
  revision: number
  timeline_id?: string | null
  segments?: Segment[] | null
  edits?: EditDecision[] | null
  analysis?: AnalysisData | null
  // v3.0.0 M11-2: subtitle-track layers (timeline-scoped, wholesale replace)
  tracks?: SubtitleTrack[] | null
  bindings?: TrackBinding[] | null
  media?: MediaInfo | null
  active_timeline_id?: string | null
  full_project?: Project | null
}

export type ProjectResponse = Project | ProjectPatch

export function isProjectPatch(data: unknown): data is ProjectPatch {
  return (
    typeof data === "object" &&
    data !== null &&
    "revision" in data &&
    typeof (data as { revision: unknown }).revision === "number"
  )
}

export interface Timeline {
  id: string
  label: string
  source: string
  created_at: string
  parent_id: string
  transcript: TranscriptData
  edits: EditDecision[]
  analysis: AnalysisData
}

export interface AnalysisResult {
  id: string
  type:
    | "llm_smart_delete"
    | "llm_subtitle_correction"
    | "llm_highlight"
  segment_ids: string[]
  confidence: number
  detail: string
  category?: string
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

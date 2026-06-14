/**
 * Centralized test mock factories for the frontend (audit L-02).
 *
 * All test data construction should go through these factories to avoid
 * field-sync issues when types change.
 */
import type {
  Project,
  Segment,
  EditDecision,
  MediaInfo,
  Timeline,
  TranscriptData,
  AnalysisData,
} from "@/types/project"

export function mockSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "seg-1",
    version: 1,
    type: "subtitle",
    start: 1.0,
    end: 5.0,
    text: "hello",
    speaker: "",
    ...overrides,
  }
}

export function mockSegments(
  count = 3,
  overrides: Partial<Segment> = {},
): Segment[] {
  return Array.from({ length: count }, (_, i) =>
    mockSegment({
      id: `seg-${i + 1}`,
      start: i * 5.5 + 1,
      end: i * 5.5 + 5,
      text: `segment ${i + 1}`,
      ...overrides,
    }),
  )
}

export function mockEditDecision(
  overrides: Partial<EditDecision> = {},
): EditDecision {
  return {
    id: "ed-1",
    start: 1.0,
    end: 5.0,
    action: "delete",
    source: "test",
    status: "pending",
    priority: 100,
    target_type: "segment",
    target_id: "seg-1",
    ...overrides,
  }
}

export function mockMediaInfo(
  overrides: Partial<MediaInfo> = {},
): MediaInfo {
  return {
    path: "/tmp/test.mp4",
    media_hash: "",
    duration: 60.0,
    format: "mp4",
    width: 1920,
    height: 1080,
    fps: 30,
    audio_channels: 2,
    sample_rate: 44100,
    bit_rate: 0,
    ...overrides,
  }
}

export function mockTranscriptData(
  overrides: Partial<TranscriptData> = {},
): TranscriptData {
  return {
    engine: "srt",
    language: "zh-CN",
    segments: [mockSegment()],
    ...overrides,
  }
}

export function mockAnalysisData(
  overrides: Partial<AnalysisData> = {},
): AnalysisData {
  return {
    last_run: null,
    results: [],
    ...overrides,
  }
}

export function mockTimeline(overrides: Partial<Timeline> = {}): Timeline {
  return {
    id: "default",
    label: "原始",
    source: "default",
    created_at: "",
    parent_id: "",
    transcript: mockTranscriptData(),
    edits: [],
    analysis: mockAnalysisData(),
    ...overrides,
  }
}

export function mockProject(overrides: Partial<Project> = {}): Project {
  return {
    schema_version: 2,
    project: { name: "test", created_at: "", updated_at: "" },
    media: null,
    timelines: [mockTimeline()],
    active_timeline_id: "default",
    ...overrides,
  }
}

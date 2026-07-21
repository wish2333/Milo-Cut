import type {
  AnalysisData,
  EditDecision,
  Project,
  Segment,
  Timeline,
} from "@/types/project"

export interface DemoCorrection {
  id: string
  segment_id: string
  confidence: number
  original_text: string
  corrected_text: string
  changes: string[]
  category: string
  start: number
  end: number
}

const createdAt = "2026-07-21T00:00:00.000Z"

const subtitleSeeds: Array<[number, number, string]> = [
  [2, 8, "大家好，今天我们用一个真实的口播例子，看看剪辑前处理可以怎样变得更轻松。"],
  [10, 16, "第一步是把素材、字幕和时间轴放在同一个工作台里。"],
  [18, 24, "你可以直接在时间轴上修改文字，所有改动都会即使同步。"],
  [28, 35, "第二步，AI 会标记口头禅、重复表达和不必要的停顿。"],
  [38, 45, "建议不会直接替你做决定，而是把原因、置信度和影响范围展示出来。"],
  [49, 57, "确认删除之后，导出摘要会准确告诉你将节省多少时间。"],
  [61, 68, "如果字幕里有同音错字，也可以逐条审阅 AI 的修正建议。"],
  [72, 79, "最后，工作流会把清理、修正和精华提取串起来。"],
  [82, 88, "遇到冲突时，决定权仍然在你手里。"],
]

const silenceSeeds: Array<[number, number]> = [
  [8, 10],
  [16, 18],
  [24, 28],
  [35, 38],
  [45, 49],
  [57, 61],
  [68, 72],
  [79, 82],
]

function makeSegment(
  id: string,
  type: Segment["type"],
  start: number,
  end: number,
  text: string,
): Segment {
  return { id, version: 1, type, start, end, text, speaker: "讲述者" }
}

function makeEdit(
  id: string,
  segment: Segment,
  source: string,
  status: EditDecision["status"] = "pending",
  action: EditDecision["action"] = "delete",
): EditDecision {
  return {
    id,
    start: segment.start,
    end: segment.end,
    action,
    source,
    status,
    priority: 100,
    target_type: "segment",
    target_id: segment.id,
  }
}

export function createDemoProject(): Project {
  const subtitles = subtitleSeeds.map(([start, end, text], index) =>
    makeSegment(`demo-subtitle-${index + 1}`, "subtitle", start, end, text),
  )
  const silences = silenceSeeds.map(([start, end], index) =>
    makeSegment(`demo-silence-${index + 1}`, "silence", start, end, ""),
  )
  const segments = [...subtitles, ...silences].sort((a, b) => a.start - b.start)

  const edits = [
    makeEdit("demo-silence-edit-1", silences[0], "silence_detection"),
    makeEdit("demo-silence-edit-2", silences[2], "silence_detection"),
    makeEdit("demo-silence-edit-3", silences[4], "silence_detection"),
  ]

  const analysis: AnalysisData = {
    last_run: createdAt,
    results: [
      {
        id: "demo-highlight-1",
        type: "llm_highlight",
        segment_ids: [subtitles[3].id, subtitles[4].id],
        confidence: 0.94,
        detail: "核心观点清晰，适合作为精华片段。",
      },
    ],
  }

  const timeline: Timeline = {
    id: "demo-timeline-main",
    label: "演示时间轴",
    source: "demo",
    created_at: createdAt,
    parent_id: "",
    transcript: { engine: "demo", language: "zh-CN", segments },
    edits,
    analysis,
  }

  return {
    schema_version: 2,
    project: {
      name: "Milo-Cut 产品演示",
      created_at: createdAt,
      updated_at: createdAt,
    },
    media: {
      path: "demo://sample-media",
      media_hash: "demo-fixture-v1",
      duration: 90,
      format: "demo",
      width: 1920,
      height: 1080,
      fps: 30,
      audio_channels: 2,
      sample_rate: 48000,
      bit_rate: 0,
    },
    timelines: [timeline],
    active_timeline_id: timeline.id,
  }
}

export function createDemoCorrections(project = createDemoProject()): DemoCorrection[] {
  const segments = project.timelines[0].transcript.segments.filter((s) => s.type === "subtitle")
  return [
    {
      id: "demo-correction-1",
      segment_id: segments[2].id,
      confidence: 0.93,
      original_text: segments[2].text,
      corrected_text: "你可以直接在时间轴上修改文字，所有改动都会即时同步。",
      changes: ["修正“即使”到“即时”的用词"],
      category: "用词",
      start: segments[2].start,
      end: segments[2].end,
    },
    {
      id: "demo-correction-2",
      segment_id: segments[5].id,
      confidence: 0.76,
      original_text: segments[5].text,
      corrected_text: "确认删除之后，导出摘要会准确告诉你将节省多少时间。",
      changes: ["补充句号，统一标点"],
      category: "标点",
      start: segments[5].start,
      end: segments[5].end,
    },
  ]
}

export function createDemoWorkflow() {
  return {
    id: "demo-workflow",
    name: "演示：从清理到精华",
    steps: [
      { type: "llm_smart_delete" as const, preset_id: null },
      { type: "llm_subtitle_correction" as const, preset_id: null },
      { type: "llm_highlight" as const, preset_id: null },
    ],
    created_at: createdAt,
    updated_at: createdAt,
  }
}

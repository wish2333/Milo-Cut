import { describe, expect, it } from "vitest"
import type {
  AnalysisData,
  EditDecision,
  MediaInfo,
  Project,
  ProjectPatch,
  Segment,
  Timeline,
} from "@/types/project"
import {
  PatchApplicationError,
  applyProjectPatch,
  applyProjectResponse,
  describePatchLayers,
  isStalePatch,
} from "@/utils/projectPatch"
import { isProjectPatch } from "@/types/project"

function makeSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "seg-1",
    version: 1,
    type: "subtitle",
    start: 0,
    end: 1,
    text: "hello",
    speaker: "",
    ...overrides,
  }
}

function makeEdit(overrides: Partial<EditDecision> = {}): EditDecision {
  return {
    id: "edit-1",
    start: 0,
    end: 1,
    action: "delete",
    source: "manual",
    status: "pending",
    priority: 100,
    target_type: "range",
    ...overrides,
  }
}

function makeProject(overrides: Partial<Project> = {}): Project {
  const timeline: Timeline = {
    id: "default",
    label: "原始",
    source: "default",
    created_at: "2026-07-21T00:00:00",
    parent_id: "",
    transcript: { engine: "srt", language: "zh-CN", segments: [makeSegment()] },
    edits: [makeEdit()],
    analysis: { last_run: null, results: [] },
    ...overrides.timelines?.[0],
  }
  return {
    schema_version: 2,
    project: { name: "test", created_at: "2026-07-21", updated_at: "2026-07-21" },
    media: {
      path: "/tmp/test.mp4",
      media_hash: "",
      duration: 60,
      format: "mp4",
      width: 1920,
      height: 1080,
      fps: 30,
      audio_channels: 2,
      sample_rate: 48000,
      bit_rate: 8000000,
    },
    timelines: [timeline],
    active_timeline_id: "default",
    ...overrides,
  }
}

describe("isProjectPatch type guard", () => {
  it("returns true for objects with numeric revision", () => {
    expect(isProjectPatch({ revision: 1 })).toBe(true)
    expect(isProjectPatch({ revision: 1, segments: [] })).toBe(true)
  })

  it("returns false for plain Project objects", () => {
    expect(isProjectPatch(makeProject())).toBe(false)
    expect(isProjectPatch({ success: true, data: {} })).toBe(false)
    expect(isProjectPatch(null)).toBe(false)
    expect(isProjectPatch("string")).toBe(false)
  })

  it("rejects non-numeric revision", () => {
    expect(isProjectPatch({ revision: "1" })).toBe(false)
    expect(isProjectPatch({ revision: null })).toBe(false)
  })
})

describe("applyProjectPatch", () => {
  describe("full_project fallback", () => {
    it("returns the full_project as-is when present", () => {
      const original = makeProject()
      const replacement = makeProject({
        project: { name: "replaced", created_at: "x", updated_at: "x" },
      })
      const patch: ProjectPatch = { revision: 1, full_project: replacement }
      const result = applyProjectPatch(original, patch)
      expect(result).toBe(replacement)
    })
  })

  describe("segments layer", () => {
    it("replaces active timeline segments", () => {
      const project = makeProject()
      const newSegments = [makeSegment({ id: "seg-2", text: "gamma" })]
      const patch: ProjectPatch = { revision: 1, segments: newSegments }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.segments).toEqual(newSegments)
      expect(result.timelines[0].transcript.segments).not.toBe(
        project.timelines[0].transcript.segments,
      )
    })

    it("preserves edits when only segments patched", () => {
      const project = makeProject()
      const patch: ProjectPatch = {
        revision: 1,
        segments: [makeSegment({ id: "seg-2" })],
      }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].edits).toEqual(project.timelines[0].edits)
    })
  })

  describe("edits layer", () => {
    it("replaces active timeline edits", () => {
      const project = makeProject()
      const newEdits = [makeEdit({ id: "edit-2", status: "confirmed" })]
      const patch: ProjectPatch = { revision: 1, edits: newEdits }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].edits).toEqual(newEdits)
    })

    it("preserves segments when only edits patched", () => {
      const project = makeProject()
      const patch: ProjectPatch = { revision: 1, edits: [makeEdit()] }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.segments).toBe(
        project.timelines[0].transcript.segments,
      )
    })
  })

  describe("combined segments + edits", () => {
    it("applies both layers atomically", () => {
      const project = makeProject()
      const newSegments = [makeSegment({ id: "seg-X" })]
      const newEdits = [makeEdit({ id: "edit-X" })]
      const patch: ProjectPatch = {
        revision: 1,
        segments: newSegments,
        edits: newEdits,
      }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.segments).toEqual(newSegments)
      expect(result.timelines[0].edits).toEqual(newEdits)
    })
  })

  describe("media layer", () => {
    it("replaces project media", () => {
      const project = makeProject()
      const newMedia: MediaInfo = {
        path: "/tmp/new.mp4",
        media_hash: "abc",
        duration: 120,
        format: "mp4",
        width: 3840,
        height: 2160,
        fps: 60,
        audio_channels: 2,
        sample_rate: 48000,
        bit_rate: 16000000,
      }
      const patch: ProjectPatch = { revision: 1, media: newMedia }
      const result = applyProjectPatch(project, patch)
      expect(result.media).toEqual(newMedia)
    })
  })

  describe("analysis layer", () => {
    it("replaces active timeline analysis", () => {
      const project = makeProject()
      const newAnalysis: AnalysisData = { last_run: "2026-07-21T00:00:00", results: [] }
      const patch: ProjectPatch = { revision: 1, analysis: newAnalysis }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].analysis).toBe(newAnalysis)
    })
  })

  describe("active_timeline_id override", () => {
    it("switches active timeline when patch requests it", () => {
      const secondTimeline: Timeline = {
        id: "second",
        label: "Second",
        source: "manual",
        created_at: "x",
        parent_id: "",
        transcript: { engine: "srt", language: "zh-CN", segments: [] },
        edits: [],
        analysis: { last_run: null, results: [] },
      }
      const project = makeProject({
        timelines: [
          {
            id: "default",
            label: "原始",
            source: "default",
            created_at: "x",
            parent_id: "",
            transcript: { engine: "srt", language: "zh-CN", segments: [makeSegment()] },
            edits: [makeEdit()],
            analysis: { last_run: null, results: [] },
          },
          secondTimeline,
        ],
      })
      const patch: ProjectPatch = { revision: 1, active_timeline_id: "second" }
      const result = applyProjectPatch(project, patch)
      expect(result.active_timeline_id).toBe("second")
    })
  })

  describe("explicit timeline_id", () => {
    it("patches a non-active timeline", () => {
      const secondTimeline: Timeline = {
        id: "second",
        label: "Second",
        source: "manual",
        created_at: "x",
        parent_id: "",
        transcript: { engine: "srt", language: "zh-CN", segments: [makeSegment({ id: "seg-second" })] },
        edits: [],
        analysis: { last_run: null, results: [] },
      }
      const project = makeProject({
        timelines: [
          {
            id: "default",
            label: "原始",
            source: "default",
            created_at: "x",
            parent_id: "",
            transcript: { engine: "srt", language: "zh-CN", segments: [makeSegment()] },
            edits: [makeEdit()],
            analysis: { last_run: null, results: [] },
          },
          secondTimeline,
        ],
      })
      const newSegments = [makeSegment({ id: "seg-patched" })]
      const patch: ProjectPatch = {
        revision: 1,
        timeline_id: "second",
        segments: newSegments,
      }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.segments[0].id).toBe("seg-1")
      const secondTl = result.timelines.find((t) => t.id === "second")
      expect(secondTl?.transcript.segments[0].id).toBe("seg-patched")
    })

    it("throws when targeting unknown timeline with layer updates", () => {
      const project = makeProject()
      const patch: ProjectPatch = {
        revision: 1,
        timeline_id: "missing",
        segments: [makeSegment()],
      }
      expect(() => applyProjectPatch(project, patch)).toThrow(PatchApplicationError)
    })

    it("does not throw when targeting unknown timeline without layer updates", () => {
      const project = makeProject()
      const patch: ProjectPatch = {
        revision: 1,
        timeline_id: "missing",
        media: {
          path: "/tmp/x.mp4",
          media_hash: "",
          duration: 1,
          format: "",
          width: 0,
          height: 0,
          fps: 0,
          audio_channels: 0,
          sample_rate: 0,
          bit_rate: 0,
        },
      }
      expect(() => applyProjectPatch(project, patch)).not.toThrow()
    })
  })

  describe("reference stability for untouched layers", () => {
    it("preserves timeline object identity when no layers changed", () => {
      const project = makeProject()
      const patch: ProjectPatch = { revision: 1 }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0]).toBe(project.timelines[0])
    })

    it("does not mutate the original project", () => {
      const project = makeProject()
      const originalSegments = project.timelines[0].transcript.segments
      const patch: ProjectPatch = {
        revision: 1,
        segments: [makeSegment({ id: "brand-new" })],
      }
      applyProjectPatch(project, patch)
      expect(project.timelines[0].transcript.segments).toBe(originalSegments)
    })
  })
})

describe("isStalePatch", () => {
  it("returns false for the first patch (revision 1, last_seen 0)", () => {
    expect(isStalePatch({ revision: 1 }, 0)).toBe(false)
  })
  it("returns true when revision equals last seen", () => {
    expect(isStalePatch({ revision: 5 }, 5)).toBe(true)
  })
  it("returns true when revision is lower than last seen", () => {
    expect(isStalePatch({ revision: 3 }, 5)).toBe(true)
  })
  it("returns false when revision is strictly higher", () => {
    expect(isStalePatch({ revision: 10 }, 5)).toBe(false)
  })
})

describe("applyProjectResponse", () => {
  it("applies patch when response is a ProjectPatch", () => {
    const current = makeProject()
    const patch: ProjectPatch = {
      revision: 1,
      segments: [makeSegment({ id: "patched" })],
    }
    const result = applyProjectResponse(current, patch)
    expect(result.timelines[0].transcript.segments[0].id).toBe("patched")
  })
  it("returns the project as-is when response is a legacy Project", () => {
    const legacy: Project = makeProject({
      project: { name: "legacy", created_at: "x", updated_at: "x" },
    })
    const result = applyProjectResponse(makeProject(), legacy)
    expect(result).toBe(legacy)
  })
})

describe("describePatchLayers", () => {
  it("returns full_project when full_project is set", () => {
    expect(
      describePatchLayers({ revision: 1, full_project: makeProject() }),
    ).toEqual(["full_project"])
  })
  it("lists only populated layers", () => {
    expect(
      describePatchLayers({ revision: 1, segments: [], edits: [] }),
    ).toEqual(["segments", "edits"])
  })
  it("returns empty array for revision-only patch", () => {
    expect(describePatchLayers({ revision: 1 })).toEqual([])
  })
})

import { describe, expect, it, vi } from "vitest"
import type {
  AnalysisData,
  EditDecision,
  MediaInfo,
  Project,
  ProjectPatch,
  Segment,
  SubtitleTrack,
  Timeline,
  TrackBinding,
} from "@/types/project"
import {
  PatchApplicationError,
  applyProjectPatch,
  applyProjectResponse,
  describePatchLayers,
  isStalePatch,
  mergeBindingsInPlace,
  mergeTracksInPlace,
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

  describe("M7-1 in-place segment merge", () => {
    it("keeps unchanged segment references stable (toBe) after a single-segment text change", () => {
      const segA = makeSegment({ id: "a", start: 0, end: 1, text: "a" })
      const segB = makeSegment({ id: "b", start: 2, end: 3, text: "b" })
      const segC = makeSegment({ id: "c", start: 4, end: 5, text: "c" })
      const project = makeProject()
      project.timelines[0].transcript.segments = [segA, segB, segC]
      const patch: ProjectPatch = {
        revision: 1,
        segments: [
          makeSegment({ id: "a", start: 0, end: 1, text: "a" }),
          makeSegment({ id: "b", start: 2, end: 3, text: "b-changed" }),
          makeSegment({ id: "c", start: 4, end: 5, text: "c" }),
        ],
      }
      const result = applyProjectPatch(project, patch)
      const out = result.timelines[0].transcript.segments
      expect(out[0]).toBe(segA) // unchanged: identity preserved
      expect(out[2]).toBe(segC) // unchanged: identity preserved
      expect(out[1].text).toBe("b-changed")
      expect(out[1]).not.toBe(segB)
    })

    it("removes deleted ids and inserts new ids in start order", () => {
      const segA = makeSegment({ id: "a", start: 0, end: 1 })
      const segB = makeSegment({ id: "b", start: 2, end: 3 })
      const project = makeProject()
      project.timelines[0].transcript.segments = [segA, segB]
      const patch: ProjectPatch = {
        revision: 1,
        segments: [
          makeSegment({ id: "a", start: 0, end: 1 }),
          makeSegment({ id: "new", start: 1.5, end: 1.8 }),
          makeSegment({ id: "b", start: 2, end: 3 }),
        ],
      }
      const result = applyProjectPatch(project, patch)
      const out = result.timelines[0].transcript.segments
      expect(out.map(s => s.id)).toEqual(["a", "new", "b"])
      expect(out[0]).toBe(segA)
      expect(out[2]).toBe(segB)
    })

    it("preserves words identity for unchanged segments with words", () => {
      const words = [{ word: "hello", start: 0, end: 0.5, confidence: 0.9 }]
      const seg = makeSegment({ id: "a", words })
      const project = makeProject()
      project.timelines[0].transcript.segments = [seg]
      const patch: ProjectPatch = {
        revision: 1,
        segments: [makeSegment({ id: "a", words: [{ word: "hello", start: 0, end: 0.5, confidence: 0.9 }] })],
      }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.segments[0]).toBe(seg)
    })

    it("falls back to wholesale replace with console.warn on id-sequence mismatch", () => {
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
      // Old array has a,b sharing start=1 (in a,b order); the backend
      // array claims b,a -- the stable start-sort cannot derive that,
      // so the gate must trip and fall back to wholesale replacement.
      const segA = makeSegment({ id: "a", start: 1, end: 2, text: "old-a" })
      const segB = makeSegment({ id: "b", start: 1, end: 2, text: "old-b" })
      const project = makeProject()
      project.timelines[0].transcript.segments = [segA, segB]
      const patch: ProjectPatch = {
        revision: 1,
        segments: [
          makeSegment({ id: "b", start: 1, end: 2 }),
          makeSegment({ id: "a", start: 1, end: 2 }),
        ],
      }
      const result = applyProjectPatch(project, patch)
      const out = result.timelines[0].transcript.segments
      expect(out.map(s => s.id)).toEqual(["b", "a"])
      expect(warnSpy).toHaveBeenCalled()
      warnSpy.mockRestore()
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

  // v3.0.0 M11-2: subtitle-track layers
  describe("M11-2 track layers", () => {
    const makeTrack = (id = "trk_1"): SubtitleTrack => ({
      id,
      role: "extension",
      name: "en",
      language: "en",
      segments: [
        {
          id: `track_${id}_seg_1.000`,
          version: 1,
          type: "subtitle",
          start: 1,
          end: 2,
          text: "hello",
          speaker: "",
        },
      ],
    })
    const makeBinding = (trackId = "trk_1"): TrackBinding => ({
      id: "bind-1",
      track_id: trackId,
      main_segment_id: "seg-1",
      extension_segment_id: `track_${trackId}_seg_1.000`,
      start_offset: 0.05,
      end_offset: 0,
    })

    it("replaces active timeline tracks wholesale", () => {
      const project = makeProject()
      const track = makeTrack()
      const patch: ProjectPatch = { revision: 1, tracks: [track] }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.tracks).toEqual([track])
      // segments layer untouched by a tracks-only patch
      expect(result.timelines[0].transcript.segments).toBe(
        project.timelines[0].transcript.segments,
      )
    })

    it("replaces active timeline bindings wholesale", () => {
      const project = makeProject()
      const binding = makeBinding()
      const patch: ProjectPatch = { revision: 1, bindings: [binding] }
      const result = applyProjectPatch(project, patch)
      expect(result.timelines[0].transcript.bindings).toEqual([binding])
    })

    it("throws when a tracks patch targets a missing timeline", () => {
      const project = makeProject()
      const patch: ProjectPatch = {
        revision: 1,
        timeline_id: "missing",
        tracks: [makeTrack()],
      }
      expect(() => applyProjectPatch(project, patch)).toThrow(PatchApplicationError)
    })

    it("describePatchLayers reports tracks and bindings", () => {
      const patch: ProjectPatch = {
        revision: 1,
        tracks: [makeTrack()],
        bindings: [makeBinding()],
      }
      expect(describePatchLayers(patch)).toEqual(["tracks", "bindings"])
    })

    // v3.0.2 M1-2 (S2): the update_segment linkage path now ships the
    // resolved tracks+bindings layers alongside segments+meta. The
    // frontend merge path must surface the squeezed extension geometry
    // with zero frontend changes (R2.3).
    it("surfaces squeezed extension segments after a combined linkage patch", () => {
      const base = makeProject()
      const project = makeProject({
        timelines: [
          {
            ...base.timelines[0],
            transcript: {
              engine: "srt",
              language: "zh-CN",
              segments: [
                makeSegment({ id: "seg-1", start: 0, end: 5 }),
                makeSegment({ id: "seg-2", start: 10, end: 15 }),
              ],
              tracks: [
                {
                  id: "trk_1",
                  role: "extension",
                  name: "en",
                  language: "en",
                  segments: [
                    makeSegment({ id: "track_trk_1_a", start: 0.2, end: 4.8 }),
                    makeSegment({ id: "track_trk_1_c", start: 12, end: 16, text: "free" }),
                  ],
                },
              ],
              bindings: [
                {
                  id: "bind_a",
                  track_id: "trk_1",
                  main_segment_id: "seg-1",
                  extension_segment_id: "track_trk_1_a",
                  start_offset: 0.2,
                  end_offset: -0.2,
                },
              ],
            },
            edits: [],
          },
        ],
      })

      // The exact patch shape the backend linkage path emits after
      // moving seg-2 to [11, 15]: segments + resolved tracks (free
      // segment c squeezed to [15, 16]) + bindings + meta.linkage.
      const squeezedTrack: SubtitleTrack = {
        id: "trk_1",
        role: "extension",
        name: "en",
        language: "en",
        segments: [
          makeSegment({ id: "track_trk_1_a", start: 0.2, end: 4.8 }),
          makeSegment({ id: "track_trk_1_c", start: 15, end: 16, text: "free" }),
        ],
      }
      const patch: ProjectPatch = {
        revision: 2,
        segments: [
          makeSegment({ id: "seg-1", start: 0, end: 5 }),
          makeSegment({ id: "seg-2", start: 11, end: 15 }),
        ],
        tracks: [squeezedTrack],
        bindings: [
          {
            id: "bind_a",
            track_id: "trk_1",
            main_segment_id: "seg-1",
            extension_segment_id: "track_trk_1_a",
            start_offset: 0.2,
            end_offset: -0.2,
          },
        ],
        meta: { linkage: { squeezed: 1, removed: 0, unbound: 0 } },
      }

      const result = applyProjectPatch(project, patch)
      const tl = result.timelines.find(t => t.id === result.active_timeline_id)!
      // main layer moved atomically with the track layer
      expect(tl.transcript.segments[1].start).toBe(11)
      // the squeezed extension segment is immediately visible
      const c = tl.transcript.tracks![0].segments.find(s => s.id === "track_trk_1_c")!
      expect(c.start).toBe(15)
      expect(c.end).toBe(16)
      // unchanged sibling keeps reference identity (mergeTracksInPlace)
      const a = tl.transcript.tracks![0].segments.find(s => s.id === "track_trk_1_a")!
      expect(a).toBe(project.timelines[0].transcript.tracks![0].segments[0])
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

// ------------------------------------------------------------------
// v3.0.1 M3 (P1-4): tracks/bindings in-place merge
// ------------------------------------------------------------------

describe("mergeTracksInPlace", () => {
  const makeTrack = (
    id: string,
    segOverrides: Partial<Segment>[] = [{ start: 1, end: 2 }],
  ): SubtitleTrack => ({
    id,
    role: "extension",
    name: id,
    language: "en",
    segments: segOverrides.map((o, i) =>
      makeSegment({ id: `track_${id}_seg_${i}`, ...o }),
    ),
  })

  it("reuses the track reference when nothing changed", () => {
    const oldTracks = [makeTrack("trk_1"), makeTrack("trk_2")]
    const newTracks = [makeTrack("trk_1"), makeTrack("trk_2")]
    const out = mergeTracksInPlace(oldTracks, newTracks)
    expect(out[0]).toBe(oldTracks[0])
    expect(out[1]).toBe(oldTracks[1])
  })

  it("reuses unchanged segment references inside a changed track", () => {
    const oldTracks = [
      makeTrack("trk_1", [
        { start: 1, end: 2 },
        { start: 3, end: 4 },
      ]),
    ]
    const changed = [
      makeTrack("trk_1", [
        { start: 1.5, end: 2 }, // changed
        { start: 3, end: 4 }, // untouched
      ]),
    ]
    const out = mergeTracksInPlace(oldTracks, changed)
    expect(out[0]).not.toBe(oldTracks[0]) // track object replaced
    expect(out[0].segments[0]).not.toBe(oldTracks[0].segments[0])
    expect(out[0].segments[1]).toBe(oldTracks[0].segments[1]) // stable ref
  })

  it("drops deleted tracks and appends new ones in backend order", () => {
    const oldTracks = [makeTrack("trk_1"), makeTrack("trk_2")]
    const newTracks = [makeTrack("trk_2"), makeTrack("trk_3")]
    const out = mergeTracksInPlace(oldTracks, newTracks)
    expect(out.map(t => t.id)).toEqual(["trk_2", "trk_3"])
    expect(out[0]).toBe(oldTracks[1])
  })

  it("falls back to wholesale replacement on id-sequence mismatch", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const oldTracks = [makeTrack("trk_1"), makeTrack("trk_2")]
    // Backend order swapped -> merged order cannot match without reorder.
    const newTracks = [makeTrack("trk_2"), makeTrack("trk_1")]
    const out = mergeTracksInPlace(oldTracks, newTracks)
    expect(out).toEqual(newTracks)
    expect(out[0]).toBe(newTracks[0])
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe("mergeBindingsInPlace", () => {
  const makeBinding = (id: string, offset = 0): TrackBinding => ({
    id,
    track_id: "trk_1",
    main_segment_id: "seg-1",
    extension_segment_id: `track_trk_1_seg_${id}`,
    start_offset: offset,
    end_offset: offset,
  })

  it("reuses unchanged bindings, replaces changed ones by id", () => {
    const oldBindings = [makeBinding("b1"), makeBinding("b2", 0.5)]
    const newBindings = [makeBinding("b1"), makeBinding("b2", 0.7)]
    const out = mergeBindingsInPlace(oldBindings, newBindings)
    expect(out[0]).toBe(oldBindings[0])
    expect(out[1]).not.toBe(oldBindings[1])
    expect(out[1].start_offset).toBe(0.7)
  })

  it("drops dissolved bindings and appends new ones", () => {
    const oldBindings = [makeBinding("b1"), makeBinding("b2")]
    const newBindings = [makeBinding("b2"), makeBinding("b3")]
    const out = mergeBindingsInPlace(oldBindings, newBindings)
    expect(out.map(b => b.id)).toEqual(["b2", "b3"])
    expect(out[0]).toBe(oldBindings[1])
  })

  it("falls back to wholesale replacement on id-sequence mismatch", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const oldBindings = [makeBinding("b1"), makeBinding("b2")]
    const newBindings = [makeBinding("b2"), makeBinding("b1")]
    const out = mergeBindingsInPlace(oldBindings, newBindings)
    expect(out).toEqual(newBindings)
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

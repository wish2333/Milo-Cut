/**
 * Perf gate for the v3.0.1 M3 tracks/bindings in-place merge (R6.2).
 *
 * Scale: 1000 main segments + 4 extension tracks x 200 segments + 200
 * bindings (the PRD MVP ceiling). Assertion: applying a combined
 * segments+tracks+bindings patch stays under 5ms p50, and a single
 * extension-segment change keeps every sibling track/segment reference
 * stable (v-memo effectiveness).
 *
 * This file is the Phase 3 merge gate (plan P3-2): it runs green from
 * P1-4 (functions land, unwired) and MUST stay green once applyProjectPatch
 * switches to mergeTracksInPlace/mergeBindingsInPlace.
 */
import { describe, expect, it } from "vitest"
import type { Project, ProjectPatch, Segment, SubtitleTrack, TrackBinding } from "@/types/project"
import { applyProjectPatch, mergeTracksInPlace } from "@/utils/projectPatch"

function makeSeg(id: string, start: number, end: number): Segment {
  return { id, version: 1, type: "subtitle", start, end, text: `t-${id}`, speaker: "" }
}

function buildProject(): Project {
  const mainSegments: Segment[] = Array.from({ length: 1000 }, (_, i) =>
    makeSeg(`seg-${i}`, i * 2, i * 2 + 1),
  )
  const tracks: SubtitleTrack[] = Array.from({ length: 4 }, (_, t) => ({
    id: `trk_${t}`,
    role: "extension" as const,
    name: `lang-${t}`,
    language: `lang-${t}`,
    segments: Array.from({ length: 200 }, (_, i) =>
      makeSeg(`track_trk_${t}_seg_${i}`, i * 2 + 0.1, i * 2 + 0.9),
    ),
  }))
  const bindings: TrackBinding[] = tracks.flatMap((t, ti) =>
    t.segments.slice(0, 50).map((s, i) => ({
      id: `bind-${ti}-${i}`,
      track_id: t.id,
      main_segment_id: `seg-${i}`,
      extension_segment_id: s.id,
      start_offset: 0.1,
      end_offset: -0.1,
    })),
  )
  return {
    schema_version: 2,
    project: { name: "perf", created_at: "", updated_at: "" },
    media: null,
    timelines: [
      {
        id: "default",
        label: "原始",
        source: "default",
        created_at: "",
        parent_id: "",
        transcript: { engine: "srt", language: "zh-CN", segments: mainSegments, tracks, bindings },
        edits: [],
        analysis: { last_run: null, results: [] },
      },
    ],
    active_timeline_id: "default",
  }
}

function moveOneExtensionSegment(project: Project, revision: number): ProjectPatch {
  const tracks = project.timelines[0].transcript.tracks!.map((t, ti) =>
    ti === 2
      ? {
          ...t,
          segments: t.segments.map((s, i) =>
            i === 100 ? { ...s, start: s.start + 0.01, end: s.end + 0.01 } : s,
          ),
        }
      : t,
  )
  const bindings = project.timelines[0].transcript.bindings!
  return { revision, segments: project.timelines[0].transcript.segments, tracks, bindings }
}

describe("M3 tracks/bindings patch apply perf gate", () => {
  it("applies a combined full-layer patch under 5ms p50 at MVP scale", () => {
    const project = buildProject()
    const samples: number[] = []
    for (let i = 0; i < 50; i++) {
      const patch = moveOneExtensionSegment(project, i + 1)
      const t0 = performance.now()
      applyProjectPatch(project, patch)
      samples.push(performance.now() - t0)
    }
    samples.sort((a, b) => a - b)
    const p50 = samples[Math.floor(samples.length / 2)]
    // Same channel as undoScale.perf.test.ts: visible in vitest output.
    console.log(
      `[perf] applyProjectPatch(segments+tracks+bindings, 1000+4x200) x50: p50=${p50.toFixed(3)}ms`,
    )
    expect(p50).toBeLessThan(5)
  })

  it("keeps sibling track/segment references stable after merge (R6.2)", () => {
    const project = buildProject()
    const before = project.timelines[0].transcript.tracks!
    const patch = moveOneExtensionSegment(project, 1)
    // Wire-through preview: applyProjectPatch still wholesale-replaces the
    // tracks layer until P3-2, so assert on the merge function directly.
    const merged = mergeTracksInPlace(before, patch.tracks!)
    expect(merged.length).toBe(before.length)
    for (let t = 0; t < before.length; t++) {
      if (t === 2) continue
      expect(merged[t]).toBe(before[t]) // sibling tracks untouched
    }
    const changedTrack = merged[2]
    for (let s = 0; s < changedTrack.segments.length; s++) {
      if (s === 100) continue
      expect(changedTrack.segments[s]).toBe(before[2].segments[s]) // sibling segments untouched
    }
    expect(changedTrack.segments[100]).not.toBe(before[2].segments[100])
  })

  it("single-track merge scan stays O(total segments)", () => {
    // Structural smoke: merging is a single pass per track; assert roughly
    // linear scaling by doubling one track's segments.
    const mk = (n: number): SubtitleTrack[] => [
      {
        id: "trk_0",
        role: "extension",
        name: "x",
        language: "x",
        segments: Array.from({ length: n }, (_, i) => makeSeg(`s${i}`, i, i + 1)),
      },
    ]
    const run = (n: number) => {
      const oldT = mk(n)
      const newT = mk(n).map(t => ({
        ...t,
        segments: t.segments.map((s, i) => (i === 0 ? { ...s, start: 0.5 } : s)),
      }))
      const t0 = performance.now()
      mergeTracksInPlace(oldT, newT)
      return performance.now() - t0
    }
    const small = run(2000)
    const large = run(8000)
    // 4x input must not blow up quadratically (allow generous slack).
    expect(large).toBeLessThan(Math.max(small * 10, 10))
  })

  // v3.0.2 M1-2 (S2) / PLAN P05-2 gate: the update_segment linkage path
  // now ships all layers on EVERY bound main-track trim/move, so the
  // full-layer shape is the common case, not the exception.
  it("applies the S2 linkage patch shape under 5ms p50 at MVP scale", () => {
    const project = buildProject()
    const samples: number[] = []
    for (let i = 0; i < 50; i++) {
      // Backend linkage payload: moved main segment + resolved tracks
      // (one bound ext follows) + full bindings array + meta counters.
      const tracks = project.timelines[0].transcript.tracks!.map((t, ti) =>
        ti === 0
          ? {
              ...t,
              segments: t.segments.map((s, j) =>
                j === 0 ? { ...s, start: s.start + 0.5, end: s.end + 0.5 } : s,
              ),
            }
          : t,
      )
      const patch: ProjectPatch = {
        revision: i + 1,
        segments: project.timelines[0].transcript.segments.map((s, j) =>
          j === 0 ? { ...s, start: s.start + 0.5, end: s.end + 0.5 } : s,
        ),
        tracks,
        bindings: project.timelines[0].transcript.bindings!.map((b, j) =>
          j === 0 ? { ...b, start_offset: b.start_offset + 0.5 } : b,
        ),
        meta: { linkage: { squeezed: 0, removed: 0, unbound: 0 } },
      }
      const t0 = performance.now()
      applyProjectPatch(project, patch)
      samples.push(performance.now() - t0)
    }
    samples.sort((a, b) => a - b)
    const p50 = samples[Math.floor(samples.length / 2)]
    console.log(
      `[perf] applyProjectPatch(S2 linkage segments+tracks+bindings+meta, 1000+4x200) x50: p50=${p50.toFixed(3)}ms`,
    )
    expect(p50).toBeLessThan(5)
  })
})

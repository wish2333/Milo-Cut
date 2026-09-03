/**
 * v3.0.3 M1-1 (P1-1): list track selector tests.
 *
 * Coverage (PLAN P1-1): round-trip switching, delete-track fallback,
 * main-track branch zero-diff (identical array reference), options
 * building. The selector is pure view state -- nothing here may produce
 * patches or persist (asserted by the null-safe helpers, not by mocks).
 */
import { describe, it, expect } from "vitest"
import { ref, nextTick } from "vue"
import {
  buildListTrackOptions,
  resolveListSegments,
  resolveListTrackIdAfterTracksChange,
  useListTrackSelector,
} from "./useListTrackSelector"
import { mockSegment } from "@/test/helpers/mockProject"
import type { Segment, SubtitleTrack } from "@/types/project"

function mockTrack(overrides: Partial<SubtitleTrack> = {}): SubtitleTrack {
  return {
    id: "track_en",
    role: "extension",
    name: "English",
    language: "en",
    segments: [],
    ...overrides,
  }
}

describe("buildListTrackOptions", () => {
  it("extracts id/name/segmentCount from tracks", () => {
    const tracks = [
      mockTrack({ id: "t1", name: "English", segments: [mockSegment(), mockSegment()] }),
      mockTrack({ id: "t2", name: "中文翻译", segments: [mockSegment()] }),
    ]
    expect(buildListTrackOptions(tracks)).toEqual([
      { id: "t1", name: "English", segmentCount: 2 },
      { id: "t2", name: "中文翻译", segmentCount: 1 },
    ])
  })

  it("falls back to the track id when name is empty", () => {
    const tracks = [mockTrack({ id: "track_x", name: "", segments: [mockSegment()] })]
    expect(buildListTrackOptions(tracks)[0].name).toBe("track_x")
  })
})

describe("resolveListSegments (single data source)", () => {
  const merged: Segment[] = [mockSegment({ id: "main-1" })]
  const trackSegs: Segment[] = [mockSegment({ id: "en-1" })]
  const tracks = [mockTrack({ id: "t1", segments: trackSegs })]

  it("null -> mergedSegments (main-track branch)", () => {
    expect(resolveListSegments(null, tracks, merged)).toBe(merged)
  })

  it("track id -> that track's segments", () => {
    expect(resolveListSegments("t1", tracks, merged)).toBe(trackSegs)
  })

  it("unknown id -> empty array (never a dangling reference)", () => {
    expect(resolveListSegments("ghost", tracks, merged)).toEqual([])
  })
})

describe("resolveListTrackIdAfterTracksChange (delete fallback)", () => {
  const tracks = [mockTrack({ id: "t1" }), mockTrack({ id: "t2" })]

  it("keeps the selection while the track exists", () => {
    expect(resolveListTrackIdAfterTracksChange("t1", tracks)).toBe("t1")
  })

  it("nulls a deleted track id", () => {
    expect(resolveListTrackIdAfterTracksChange("t2", [tracks[0]])).toBeNull()
  })

  it("null stays null", () => {
    expect(resolveListTrackIdAfterTracksChange(null, tracks)).toBeNull()
  })
})

describe("useListTrackSelector (reactive)", () => {
  const mergedRaw: Segment[] = [mockSegment({ id: "main-1", start: 1, end: 5 })]
  const enRaw: Segment[] = [
    mockSegment({ id: "en-1", start: 1, end: 4, text: "hello" }),
    mockSegment({ id: "en-2", start: 6, end: 9, text: "world" }),
  ]
  const zhRaw: Segment[] = [mockSegment({ id: "zh-1", start: 1, end: 4, text: "你好" })]

  function setup() {
    const tracks = ref<SubtitleTrack[]>([
      mockTrack({ id: "t_en", name: "English", segments: enRaw }),
      mockTrack({ id: "t_zh", name: "中文", segments: zhRaw }),
    ])
    const mergedRef = ref<Segment[]>(mergedRaw)
    const sel = useListTrackSelector(tracks, mergedRef)
    // ref() deep-proxies arrays, so reference identity must be asserted
    // against the proxied .value (what the composable actually hands
    // through) -- the zero-diff property is "same proxy, no copy/reorder".
    const live = {
      merged: () => mergedRef.value,
      en: () => (tracks.value.find(t => t.id === "t_en") ?? tracks.value[0]).segments,
      zh: () => tracks.value.find(t => t.id === "t_zh")?.segments ?? [],
    }
    return { tracks, mergedRef, sel, live }
  }

  it("defaults to the main track with a zero-diff data source", () => {
    const { sel, live } = setup()
    expect(sel.activeListTrackId.value).toBeNull()
    // zero diff: the exact same array reference flows through -- no copy,
    // no reorder, no remount trigger on the v3.0.2 path.
    expect(sel.listSegments.value).toBe(live.merged())
  })

  it("round-trips main -> track -> main without residue", () => {
    const { sel, live } = setup()
    sel.selectTrack("t_zh")
    expect(sel.activeListTrackId.value).toBe("t_zh")
    expect(sel.listSegments.value).toBe(live.zh())
    sel.selectTrack(null)
    expect(sel.activeListTrackId.value).toBeNull()
    expect(sel.listSegments.value).toBe(live.merged())
  })

  it("switches between two tracks directly", () => {
    const { sel, live } = setup()
    sel.selectTrack("t_en")
    expect(sel.listSegments.value).toBe(live.en())
    sel.selectTrack("t_zh")
    expect(sel.listSegments.value).toBe(live.zh())
  })

  it("falls back to the main track when the viewed track is deleted", async () => {
    const { tracks, sel, live } = setup()
    sel.selectTrack("t_en")
    expect(sel.listSegments.value).toBe(live.en())
    tracks.value = tracks.value.filter(t => t.id !== "t_en")
    await nextTick()
    expect(sel.activeListTrackId.value).toBeNull()
    expect(sel.listSegments.value).toBe(live.merged())
  })

  it("falls back when the timeline (track set) switches underneath", async () => {
    const { tracks, sel } = setup()
    sel.selectTrack("t_en")
    tracks.value = [mockTrack({ id: "other", segments: [] })]
    await nextTick()
    expect(sel.activeListTrackId.value).toBeNull()
  })

  it("keeps the selection when an unrelated track changes", async () => {
    const { tracks, sel, live } = setup()
    sel.selectTrack("t_en")
    tracks.value = [...tracks.value, mockTrack({ id: "t_new", segments: [] })]
    await nextTick()
    expect(sel.activeListTrackId.value).toBe("t_en")
    expect(sel.listSegments.value).toBe(live.en())
  })

  it("exposes selector options for the header control", () => {
    const { sel } = setup()
    expect(sel.options.value).toEqual([
      { id: "t_en", name: "English", segmentCount: 2 },
      { id: "t_zh", name: "中文", segmentCount: 1 },
    ])
  })

  it("follows segment-count changes live (patch backfill)", () => {
    const { tracks, sel } = setup()
    sel.selectTrack("t_en")
    expect(sel.options.value[0].segmentCount).toBe(2)
    tracks.value = [
      mockTrack({
        id: "t_en",
        name: "English",
        segments: [...enRaw, mockSegment({ id: "en-3" })],
      }),
      tracks.value[1],
    ]
    expect(sel.options.value[0].segmentCount).toBe(3)
    expect(sel.listSegments.value).toHaveLength(3)
  })
})

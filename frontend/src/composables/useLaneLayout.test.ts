/**
 * Layout math + persistence tests (SPEC M4-1 acceptance):
 * 0/1/4 tracks, all collapsed, main-floor squeeze, corrupt JSON fallback.
 */
import { describe, expect, it, beforeEach, afterEach } from "vitest"
import {
  LANE_COLLAPSED_HEIGHT,
  LANE_MIN_HEIGHT,
  LANE_PRESET_HEIGHTS,
  MAIN_TRACK_MIN_HEIGHT,
  LAYOUT_STORAGE_KEY,
  computeLaneLayout,
  defaultLaneLayoutState,
  loadLaneLayoutState,
  saveLaneLayoutState,
} from "./useLaneLayout"

const IDS = ["trk_a", "trk_b", "trk_c", "trk_d"]

describe("computeLaneLayout", () => {
  it("zero tracks -> whole container is the main track", () => {
    const r = computeLaneLayout(400, [], defaultLaneLayoutState())
    expect(r.lanes).toEqual([])
    expect(r.mainTrackHeight).toBe(400)
    expect(r.totalLanesHeight).toBe(0)
    expect(r.overflowing).toBe(false)
  })

  it("single md lane takes its preset height", () => {
    const r = computeLaneLayout(400, ["trk_a"], defaultLaneLayoutState())
    expect(r.lanes[0]).toMatchObject({ trackId: "trk_a", top: 0, height: 48 })
    expect(r.mainTrackHeight).toBe(400 - 48)
  })

  it("four lanes stack with cumulative tops", () => {
    const r = computeLaneLayout(600, IDS, defaultLaneLayoutState())
    expect(r.lanes.map(l => l.height)).toEqual([48, 48, 48, 48])
    expect(r.lanes.map(l => l.top)).toEqual([0, 48, 96, 144])
    expect(r.mainTrackHeight).toBe(600 - 192)
  })

  it("hidden lanes take no space and produce no top advance", () => {
    const state = { ...defaultLaneLayoutState(), hidden: { trk_a: true } }
    const r = computeLaneLayout(400, IDS, state)
    expect(r.lanes[0]).toMatchObject({ hidden: true, height: 0 })
    expect(r.lanes[1]).toMatchObject({ top: 0 })
    expect(r.totalLanesHeight).toBe(3 * 48)
  })

  it("collapsed lanes shrink to the title bar height", () => {
    const state = { ...defaultLaneLayoutState(), collapsed: { trk_a: true, trk_b: true } }
    const r = computeLaneLayout(600, IDS, state)
    expect(r.lanes[0].height).toBe(LANE_COLLAPSED_HEIGHT)
    expect(r.lanes[1].height).toBe(LANE_COLLAPSED_HEIGHT)
    expect(r.mainTrackHeight).toBe(600 - 2 * 24 - 2 * 48)
  })

  it("honors per-lane presets", () => {
    const state = { ...defaultLaneLayoutState(), preset: { trk_a: "lg", trk_b: "sm" } }
    const r = computeLaneLayout(600, IDS, state)
    expect(r.lanes[0].height).toBe(72)
    expect(r.lanes[1].height).toBe(32)
  })

  it("compresses lanes in order when the main track floor is violated", () => {
    // 4x lg = 288; container 350 -> main would be 62 < 96 -> compress.
    const state = { ...defaultLaneLayoutState(), preset: { trk_a: "lg", trk_b: "lg", trk_c: "lg", trk_d: "lg" } }
    const r = computeLaneLayout(350, IDS, state)
    const main = r.mainTrackHeight
    expect(main).toBeGreaterThanOrEqual(MAIN_TRACK_MIN_HEIGHT)
    // compressed lanes stay >= absolute floor
    for (const lane of r.lanes) expect(lane.height).toBeGreaterThanOrEqual(LANE_MIN_HEIGHT)
  })

  it("flags overflow when even all-24 lanes cannot respect the floor", () => {
    // 8 lanes x 24 = 192; container 200 -> main 8 < 96 and nothing left to compress.
    const ids = Array.from({ length: 8 }, (_, i) => `trk_${i}`)
    const r = computeLaneLayout(200, ids, defaultLaneLayoutState())
    expect(r.lanes.every(l => l.height === LANE_MIN_HEIGHT)).toBe(true)
    expect(r.overflowing).toBe(true)
    expect(r.mainTrackHeight).toBe(200 - 8 * LANE_MIN_HEIGHT)
  })

  it("degenerate container (0 height) keeps lanes at floor and zero main", () => {
    const r = computeLaneLayout(0, ["trk_a"], defaultLaneLayoutState())
    expect(r.mainTrackHeight).toBe(0)
    expect(r.overflowing).toBe(true)
  })
})

describe("layout persistence", () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it("returns defaults when nothing stored", () => {
    expect(loadLaneLayoutState()).toEqual(defaultLaneLayoutState())
  })

  it("saves and loads a full round trip", () => {
    const state = {
      collapsed: { trk_a: true },
      hidden: { trk_b: true },
      preset: { trk_c: "lg" as const },
    }
    saveLaneLayoutState(state)
    expect(loadLaneLayoutState()).toEqual(state)
    expect(localStorage.getItem(LAYOUT_STORAGE_KEY)).toContain("trk_a")
  })

  it("falls back to defaults on corrupt JSON", () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, "{not json")
    expect(loadLaneLayoutState()).toEqual(defaultLaneLayoutState())
  })

  it("tolerates missing keys in stored payload", () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ collapsed: { trk_a: true } }))
    const loaded = loadLaneLayoutState()
    expect(loaded.collapsed).toEqual({ trk_a: true })
    expect(loaded.hidden).toEqual({})
    expect(loaded.preset).toEqual({})
  })
})

describe("preset height table", () => {
  it("keeps the documented sm/md/lg values", () => {
    expect(LANE_PRESET_HEIGHTS).toEqual({ sm: 32, md: 48, lg: 72 })
    expect(LANE_COLLAPSED_HEIGHT).toBe(24)
    expect(LANE_MIN_HEIGHT).toBe(24)
    expect(MAIN_TRACK_MIN_HEIGHT).toBe(96)
  })
})

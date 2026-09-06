/**
 * v3.0.2 M4-3 (P2-4): row-layer peak-slice cache tests -- hit counting,
 * key isolation, LRU refresh, cap eviction, clear, and the dpr cap in the
 * key derivation.
 */
import { describe, expect, it, vi } from "vitest"
import { createPeakSliceCache } from "./usePeakSliceCache"

describe("createPeakSliceCache", () => {
  it("computes once for repeated identical keys", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => [{ min: -1, max: 1 }])
    const key = { rowIndex: 3, widthPx: 800, dpr: 2 }
    expect(cache.get(key, compute)).toEqual([{ min: -1, max: 1 }])
    expect(cache.get(key, compute)).toEqual([{ min: -1, max: 1 }])
    expect(compute).toHaveBeenCalledTimes(1)
    expect(cache.size()).toBe(1)
  })

  it("isolates distinct rowIndex/widthPx/dpr keys", () => {
    const cache = createPeakSliceCache()
    const computeA = vi.fn(() => [{ min: -1, max: 1 }])
    const computeB = vi.fn(() => [{ min: -2, max: 2 }])
    cache.get({ rowIndex: 0, widthPx: 800, dpr: 1 }, computeA)
    cache.get({ rowIndex: 1, widthPx: 800, dpr: 1 }, computeB)
    expect(cache.get({ rowIndex: 0, widthPx: 800, dpr: 1 }, computeB)).toEqual([{ min: -1, max: 1 }])
    expect(computeB).toHaveBeenCalledTimes(1) // B computed once for its own key
  })

  it("caps dpr at 2 in key derivation (hidpi variants share)", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => null)
    cache.get({ rowIndex: 0, widthPx: 800, dpr: 3 }, compute)
    cache.get({ rowIndex: 0, widthPx: 800, dpr: 2 }, compute)
    cache.get({ rowIndex: 0, widthPx: 800, dpr: 1 }, compute)
    expect(compute).toHaveBeenCalledTimes(2) // dpr3 hit the dpr2 entry
    expect(cache.size()).toBe(2)
  })

  it("caches null results (empty windows) without recompute", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => null)
    expect(cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)).toBeNull()
    expect(cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)).toBeNull()
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it("clear() empties the cache", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => [{ min: 0, max: 0 }])
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    cache.clear()
    expect(cache.size()).toBe(0)
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it("evicts the oldest entry past the 64-entry cap", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => [{ min: 0, max: 0 }])
    for (let i = 0; i < 70; i++) {
      cache.get({ rowIndex: i, widthPx: 100, dpr: 1 }, compute)
    }
    expect(cache.size()).toBe(64)
    // Row 0 was evicted -> recomputing it is allowed; row 69 still cached.
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    expect(cache.size()).toBe(64)
  })

  it("refreshes LRU order on hits (recently used survives eviction)", () => {
    const cache = createPeakSliceCache()
    const compute = vi.fn(() => [{ min: 0, max: 0 }])
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    for (let i = 1; i < 64; i++) {
      cache.get({ rowIndex: i, widthPx: 100, dpr: 1 }, compute)
    }
    // Touch row 0 -> becomes most-recent.
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    expect(compute).toHaveBeenCalledTimes(64)
    // Insert one more -> evicts row 1 (oldest), not row 0.
    cache.get({ rowIndex: 64, widthPx: 100, dpr: 1 }, compute)
    cache.get({ rowIndex: 0, widthPx: 100, dpr: 1 }, compute)
    expect(compute).toHaveBeenCalledTimes(65) // row 0 was still cached
  })
})

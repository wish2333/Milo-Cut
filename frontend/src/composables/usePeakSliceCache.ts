/**
 * v3.0.2 M4-3 (P2-4): row-layer memoization for peak window slices.
 *
 * The slice math (computePeakSlice) is pure but not free at O(peaks)
 * scale; each visible row recomputes it on every view change. This cache
 * keys by {rowIndex, widthPx, dpr} -- identical geometry (same row, same
 * layout, same display density) reuses the previous slice. Basic mode
 * never wraps, so the single-window path is untouched (M4-3 裁决).
 */
import type { WaveformPeak } from "@/utils/waveformPeaks"
import { clampDpr } from "@/utils/waveformPeaks"

export interface PeakSliceCacheKey {
  rowIndex: number
  widthPx: number
  dpr: number
}

const MAX_ENTRIES = 64

export function createPeakSliceCache() {
  const cache = new Map<string, WaveformPeak[] | null>()

  function keyOf(k: PeakSliceCacheKey): string {
    // dpr capped at 2 so hidpi/ldpi switches share entries (M4-3).
    return `${k.rowIndex}|${k.widthPx}|${clampDpr(k.dpr)}`
  }

  function get(
    key: PeakSliceCacheKey,
    compute: () => WaveformPeak[] | null,
  ): WaveformPeak[] | null {
    const k = keyOf(key)
    if (cache.has(k)) {
      // Map iteration order = insertion order: refresh for LRU semantics.
      const hit = cache.get(k)!
      cache.delete(k)
      cache.set(k, hit)
      return hit
    }
    const value = compute()
    if (cache.size >= MAX_ENTRIES) {
      // Evict oldest (first inserted). Row count in view is
      // viewport-bounded, so steady-state never reaches the cap; the cap
      // only guards pathological resize loops.
      const oldest = cache.keys().next().value
      if (oldest !== undefined) cache.delete(oldest)
    }
    cache.set(k, value)
    return value
  }

  function clear(): void {
    cache.clear()
  }

  function size(): number {
    return cache.size
  }

  return { get, clear, size }
}

export type PeakSliceCache = ReturnType<typeof createPeakSliceCache>

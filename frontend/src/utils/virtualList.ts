/**
 * Virtual list windowing math (v3.0.0 M7-2 / PRD B3).
 *
 * Pure functions only -- no DOM, no Vue. The mixed row types of the
 * transcript list (TranscriptRow min-h-52px vs SilenceRow h-9) are handled
 * with a per-type height registry and a precomputed cumulative-offsets
 * array; positioning uses binary search so future variable-height rows
 * cost nothing extra (risk review section 2.6).
 */

export interface RowTypeHeights {
  subtitle: number
  silence: number
}

/** CSS-measured defaults: TranscriptRow min-h-[52px], SilenceRow h-9 (36px). */
export const DEFAULT_ROW_HEIGHTS: RowTypeHeights = {
  subtitle: 52,
  silence: 36,
}

/** Half-open window [start, end) of rendered rows. */
export interface VisibleWindow {
  start: number
  end: number
}

export function rowHeightFor(heights: RowTypeHeights, type: string | undefined): number {
  return type === "silence" ? heights.silence : heights.subtitle
}

/**
 * Prefix-sum offsets for a row sequence: offsets[i] is the top edge of
 * row i, offsets[n] is the total content height. Returns n+1 entries
 * (always at least [0]) so callers can read row bottom = offsets[i+1].
 */
export function buildCumulativeOffsets(
  types: ReadonlyArray<string | undefined>,
  heights: RowTypeHeights,
): { offsets: number[]; totalHeight: number } {
  const offsets = new Array<number>(types.length + 1)
  offsets[0] = 0
  for (let i = 0; i < types.length; i++) {
    offsets[i + 1] = offsets[i] + rowHeightFor(heights, types[i])
  }
  return { offsets, totalHeight: offsets[types.length] }
}

/**
 * Index of the row whose band contains pixel offset y (largest i with
 * offsets[i] <= y). Clamps out-of-range input to the valid row range.
 */
export function findRowIndexForOffset(offsets: ReadonlyArray<number>, y: number): number {
  const n = offsets.length - 1
  if (n <= 0) return 0
  if (y <= 0) return 0
  const total = offsets[n]
  if (y >= total) return n - 1
  // Binary search: largest i in [0, n-1] with offsets[i] <= y.
  let lo = 0
  let hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (offsets[mid] <= y) lo = mid
    else hi = mid - 1
  }
  return lo
}

/**
 * Window of rows covering scrollTop..scrollTop+viewportHeight, expanded
 * by `overscan` rows on each side and clamped to the list. An empty list
 * yields {start: 0, end: 0}; a viewport taller than the list yields the
 * whole list.
 */
export function computeVisibleWindow(
  offsets: ReadonlyArray<number>,
  scrollTop: number,
  viewportHeight: number,
  overscan: number,
): VisibleWindow {
  const n = offsets.length - 1
  if (n <= 0) return { start: 0, end: 0 }
  const first = findRowIndexForOffset(offsets, Math.max(0, scrollTop))
  const bottom = Math.max(0, scrollTop) + Math.max(0, viewportHeight)
  // Smallest row whose bottom edge reaches past the viewport bottom: the
  // row containing `bottom` is findRowIndexForOffset(bottom), and it must
  // be rendered, so the exclusive end is that index + 1.
  let end = findRowIndexForOffset(offsets, bottom) + 1
  const start = Math.max(0, first - overscan)
  end = Math.min(n, end + overscan)
  return { start, end }
}

/**
 * scrollTop that brings row `index` fully into view, or null when the row
 * is already visible (no scroll). Rows above the viewport align their top
 * edge to the viewport top; rows below align their bottom edge. Result is
 * clamped to the valid scroll range.
 */
export function scrollTargetForIndex(
  offsets: ReadonlyArray<number>,
  index: number,
  scrollTop: number,
  viewportHeight: number,
): number | null {
  const n = offsets.length - 1
  if (n <= 0) return null
  const i = Math.min(Math.max(0, index), n - 1)
  const top = offsets[i]
  const bottom = offsets[i + 1]
  const viewH = Math.max(0, viewportHeight)
  if (top >= scrollTop && bottom <= scrollTop + viewH) return null
  const total = offsets[n]
  const raw = top < scrollTop ? top : bottom - viewH
  return Math.min(Math.max(0, raw), Math.max(0, total - viewH))
}

/**
 * v3.0.2 M3-1 (P2-1): row-scoped TimelineMetrics adapter.
 *
 * "One row = one single-window view" (PRD P2): each WaveformRow builds an
 * adapter that satisfies the TimelineMetrics interface shape with the row
 * window (viewStart = rowIndex*spr, viewDuration = spr), so the seven
 * existing timeline sub-components (WaveformCanvas / TimeMarksLayer /
 * SegmentBlocksLayer / SegmentBlock / PlayheadOverlay / ...) render the
 * row unchanged through the same provide/inject contract.
 *
 * Invariants (SPEC M3-1):
 * - `useTimelineMetrics` itself is NOT modified -- no mode branches.
 * - Ref members are `computed()` (real Ref symbol) so existing
 *   `watch(viewStart)` / `watch(viewDuration)` sources stay legal.
 * - `rowIndex` / `secondsPerRow` are STATICALLY CAPTURED: correctness
 *   depends on the orchestrator remounting rows wholesale when spr
 *   changes (M4-2); row-height changes are geometry-only and safe.
 * - ZERO watcher registration: the adapter never calls `watch()` -- the
 *   row must not fight the editor over scroll/zoom/follow state
 *   (M0-1.5 red line).
 * - Navigation members are no-ops (one DEV warn): a row has no
 *   navigation duties; the editor orchestrator owns them.
 */
import { computed, type Ref } from "vue"
import { formatTimeShort } from "@/utils/format"
import { NICE_STEPS, type TimelineMetrics } from "./useTimelineMetrics"

const TIME_MARK_TARGET_COUNT = 6

export function createRowMetrics(
  rowIndex: number,
  duration: Ref<number>,
  currentTime: Ref<number>,
  secondsPerRow: number,
  containerRef: Ref<HTMLElement | null>,
): TimelineMetrics {
  if (!(secondsPerRow > 0)) {
    throw new Error(`createRowMetrics: secondsPerRow must be > 0, got ${secondsPerRow}`)
  }

  // -- Row window (statically captured row geometry) ---------------------

  const rowStart = rowIndex * secondsPerRow
  const viewStart = computed(() => rowStart)
  const viewDuration = computed(() => secondsPerRow)
  // Last row ends at the media duration, not at the full row length.
  const viewEnd = computed(() => Math.min(rowStart + secondsPerRow, duration.value))

  // DEV-only one-shot warning for navigation no-ops.
  let warned = false
  function noop(where: string): void {
    if (!warned && import.meta.env.DEV) {
      warned = true
      console.warn(
        `[rowMetrics] row #${rowIndex}: "${where}" is a no-op -- rows have no navigation duties (owned by WaveformEditor)`,
      )
    }
  }

  // -- Time / pixel conversion (row window) ------------------------------

  function timeToPercent(time: number): number {
    if (secondsPerRow <= 0) return 0
    return ((time - rowStart) / secondsPerRow) * 100
  }

  function percentToPixels(pct: number): number {
    const el = containerRef.value
    if (!el) return 0
    return (pct / 100) * el.getBoundingClientRect().width
  }

  function getTimeFromX(clientX: number): number {
    const el = containerRef.value
    if (!el) return rowStart
    const rect = el.getBoundingClientRect()
    const ratio = (clientX - rect.left) / rect.width
    return rowStart + ratio * secondsPerRow
  }

  // -- Playhead (row-local visibility; R5.3) ------------------------------

  const playheadPercent = computed(() => {
    if (secondsPerRow <= 0) return 0
    const pct = ((currentTime.value - rowStart) / secondsPerRow) * 100
    return Math.max(0, Math.min(100, pct))
  })

  const playheadVisible = computed(
    () => currentTime.value >= rowStart && currentTime.value < rowStart + secondsPerRow,
  )

  // -- Time marks (row window; shared NICE_STEPS ladder) ------------------
  // Target count 6 (vs 15 in the basic single window) so ticks stay
  // readable at row widths: 5s row -> 1s ticks, 30s row -> 5s ticks
  // (PRD R5.4). The LADDER itself is the shared export -- same source as
  // useTimelineMetrics (M3-1).
  // Per-instance step cache: row count in view is viewport-bounded, so the
  // cache footprint stays O(visible rows).

  let cachedStep = 0
  let cachedTimeMarks: Array<{ percent: number; label: string; time: number }> = []

  const timeMarks = computed(() => {
    const vd = viewDuration.value
    const ve = viewEnd.value
    if (vd <= 0 || ve <= rowStart) return []
    const rawStep = vd / TIME_MARK_TARGET_COUNT
    const step = NICE_STEPS.find(s => s >= rawStep) ?? rawStep
    if (step === cachedStep && cachedTimeMarks.length > 0) {
      return cachedTimeMarks
    }
    cachedStep = step
    const marks: { percent: number; label: string; time: number }[] = []
    const start = Math.ceil(rowStart / step) * step
    for (let t = start; t <= ve + 1e-9; t += step) {
      marks.push({
        percent: ((t - rowStart) / vd) * 100,
        label: formatTimeShort(t),
        time: t,
      })
    }
    cachedTimeMarks = marks
    return marks
  })

  const minorTimeMarks = computed(() => {
    const vd = viewDuration.value
    const ve = viewEnd.value
    if (vd <= 0 || ve <= rowStart) return []
    const rawStep = vd / TIME_MARK_TARGET_COUNT
    const step = NICE_STEPS.find(s => s >= rawStep) ?? rawStep
    const minorStep = step / 2
    if (minorStep < 0.025) return []
    const marks: { percent: number; time: number }[] = []
    const start = Math.ceil(rowStart / minorStep) * minorStep
    for (let t = start; t <= ve + 1e-9; t += minorStep) {
      const majorAligned = Math.abs(t % step) < 0.001 || Math.abs(t % step - step) < 0.001
      if (!majorAligned) {
        marks.push({
          percent: ((t - rowStart) / vd) * 100,
          time: t,
        })
      }
    }
    return marks
  })

  // -- Formal scrollbar geometry (per-row semantics, no consumer today) ---

  const thumbLeft = computed(() =>
    duration.value <= 0 ? 0 : (viewStart.value / duration.value) * 100,
  )
  const thumbWidth = computed(() =>
    duration.value <= 0 ? 100 : Math.max(0, (viewDuration.value / duration.value) * 100),
  )

  // -- Assembled interface (no watch() anywhere) --------------------------

  return {
    duration,

    viewStart,
    viewDuration,
    viewEnd,

    timeToPercent,
    percentToPixels,
    getTimeFromX,

    clampViewStart: () => noop("clampViewStart"),
    scrollTo: () => noop("scrollTo"),
    zoomAt: () => noop("zoomAt"),
    handleWheel: e => {
      noop("handleWheel")
      // Never preventDefault from a row: the multi-row container owns
      // native scrolling (M5-1).
      void e
    },

    ensurePlayheadInView: () => noop("ensurePlayheadInView"),
    maybeFollowPlayhead: () => noop("maybeFollowPlayhead"),
    playheadPercent,
    playheadVisible,

    thumbLeft,
    thumbWidth,

    timeMarks,
    minorTimeMarks,

    containerRef,
  } satisfies TimelineMetrics as TimelineMetrics
}

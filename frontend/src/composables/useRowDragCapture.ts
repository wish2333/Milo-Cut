/**
 * v3.0.2 M3-3 (P2-5): drag-state hoisting skeleton for the multi-row timeline.
 *
 * WHY THIS EXISTS: in multi-row mode the timeline virtualizes rows, so the
 * row component a drag started on can be UNMOUNTED mid-gesture (scroll,
 * window resize, row recycle). Any drag geometry kept inside that row's own
 * component state dies with it, freezing the trim/scrub. This composable
 * lifts the geometry to the orchestrator layer as a FROZEN SNAPSHOT taken
 * at pointerdown: `timeAt` keeps converting pointer positions to seconds
 * from the snapshot alone, so row destroy/remount never disturbs an
 * in-flight drag.
 *
 * CONSUMERS (wired in P3, not here): M5-4 trim handles and M5-3 playhead
 * scrub call `capture` on pointerdown, `timeAt` on every pointermove
 * (bounded/unbounded per the P4 dual-mapping contract -- callers clamp
 * unbounded results to [0, duration] themselves, the kernel never does),
 * and `release` on pointerup/cancel.
 *
 * Module discipline (SPEC M3): geometry math stays in the useRowLayout
 * pure kernel -- this file only adds the frozen-snapshot lifecycle around
 * `timeFromPointerInRow`. No Vue component, bridge, or store imports; the
 * only imports are `ref` from vue and the type/pure function from
 * useRowLayout.
 */
import { ref, type Ref } from "vue"
import { timeFromPointerInRow, type RowSpan } from "./useRowLayout"

/**
 * Frozen geometry of the row a drag started on, captured at pointerdown.
 * `rowLeft`/`rowWidth` come from the row element's immediate
 * getBoundingClientRect() at that moment (passed in by the caller -- the
 * composable never touches the DOM).
 */
export interface FrozenRowGeometry {
  /** Row element clientX basis: rect.left at pointerdown. */
  rowLeft: number
  /** Row element width: rect.width at pointerdown. */
  rowWidth: number
  /** Row start time in seconds (informational mirror of rowSpan.start). */
  rowStart: number
  /** Row time window {start, end} in seconds. */
  rowSpan: RowSpan
}

export interface UseRowDragCaptureReturn {
  /** Frozen pointerdown snapshot; null while no drag is active. */
  frozen: Ref<FrozenRowGeometry | null>
  /** Freeze the geometry of the row under the pointerdown (copies it). */
  capture: (clientX: number, geometry: FrozenRowGeometry) => void
  /**
   * Time under `clientX` from the frozen snapshot (null when nothing is
   * captured). `bounded: true` clamps to the row span (clicks/creation);
   * `bounded: false` runs free for scrub/trim (caller clamps to duration).
   */
  timeAt: (clientX: number, opts: { bounded: boolean }) => number | null
  /** Drop the snapshot (pointerup/cancel); timeAt returns null afterwards. */
  release: () => void
}

/**
 * Drag-capture singleton skeleton (M3-3). Callers own the DOM read:
 * on pointerdown they resolve the row under `clientX`, read its rect,
 * and hand both to `capture`. From then on the snapshot is detached from
 * the DOM -- destroying the row does not affect `timeAt` output.
 */
export function useRowDragCapture(): UseRowDragCaptureReturn {
  const frozen = ref<FrozenRowGeometry | null>(null)

  function capture(clientX: number, geometry: FrozenRowGeometry): void {
    // `clientX` anchors the gesture (P3 consumers may derive drag deltas
    // from it); the geometry is what timeAt needs. Copy it so later
    // mutations/replacement of the caller's object (e.g. the row's own
    // reactive geometry being torn down on unmount) cannot leak into the
    // snapshot -- that is the whole point of hoisting state here.
    void clientX
    frozen.value = {
      rowLeft: geometry.rowLeft,
      rowWidth: geometry.rowWidth,
      rowStart: geometry.rowStart,
      rowSpan: { ...geometry.rowSpan },
    }
  }

  function timeAt(clientX: number, opts: { bounded: boolean }): number | null {
    const snap = frozen.value
    if (!snap) return null
    try {
      return timeFromPointerInRow(
        { left: snap.rowLeft, width: snap.rowWidth },
        snap.rowSpan,
        clientX,
        opts,
      )
    } catch {
      // Defense: timeFromPointerInRow throws on width <= 0. A degenerate
      // rect can slip into a snapshot taken while a row is tearing down
      // (display:none reads 0 width); a scrub/trim gesture must never
      // crash mid-drag, so this sample degrades to null and callers skip
      // it. capture deliberately does NOT validate (keep pointerdown
      // cheap; the error surface lives in one place).
      return null
    }
  }

  function release(): void {
    frozen.value = null
  }

  return { frozen, capture, timeAt, release }
}

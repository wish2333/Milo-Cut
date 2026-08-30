/**
 * Coalescing rAF scheduler (v3.0.0 M6-1).
 *
 * Multiple schedule() calls within one frame collapse into a single task
 * run -- the canvas redraw counterpart of "连续 10 次 scheduleDraw 仅 1 次
 * draw". The injected frame functions keep the unit tests synchronous.
 */

export interface RafScheduler {
  /** Request a task run; no-op if one is already pending for this frame. */
  schedule(): void
  /** Drop a pending (not yet run) task. */
  cancel(): void
  /** True while a task is queued but has not run yet. */
  readonly pending: boolean
}

export function createRafScheduler(
  task: () => void,
  requestFrame: (cb: () => void) => number = (cb) => requestAnimationFrame(cb),
  cancelFrame: (id: number) => void = (id) => cancelAnimationFrame(id),
): RafScheduler {
  let frameId: number | null = null

  function run(): void {
    frameId = null
    task()
  }

  return {
    schedule() {
      if (frameId !== null) return
      frameId = requestFrame(run)
    },
    cancel() {
      if (frameId !== null) {
        cancelFrame(frameId)
        frameId = null
      }
    },
    get pending(): boolean {
      return frameId !== null
    },
  }
}

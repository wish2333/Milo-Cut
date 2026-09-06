import { ref, type Ref } from "vue"
/**
 * Playback clock (v3.0.0 M6-3) -- the non-reactive video time domain.
 *
 * Per-frame media time lives here and NEVER flows through Vue reactivity:
 * imperative consumers (PlayheadOverlay transform) subscribe to raw samples,
 * while coarse UI (controls text, playhead segment highlight, follow logic)
 * reads `coarseTime`, which is written at most once per
 * PLAYBACK_COARSE_INTERVAL_MS during playback and immediately when paused
 * (seek/pause events are single samples).
 *
 * Sample sources:
 * - edited-mode playback: the EditedPlaybackController's rAF loop publishes
 *   through `ingest` (its delete-range skip logic is kept intact).
 * - original-mode playback: `start()` runs a plain rAF loop of our own.
 * - paused updates (timeupdate/seeked/pause events): one `ingest` each.
 */
export interface PlaybackClock {
  /** Freshest non-reactive media time. */
  getTime(): number
  isPlaying(): boolean
  /**
   * Push a raw time sample: notifies raw subscribers and (throttled or
   * immediate-when-paused) mirrors into `coarseTime`. Value-identical
   * coarse writes are skipped, so an external writer of the same ref
   * (demo playback) can bridge through `ingest` without loops.
   */
  ingest(time: number): void
  /** Register a raw-sample listener; returns the unsubscribe function. */
  subscribe(cb: (time: number) => void): () => void
  /** Coarse reactive mirror -- at most ~10 writes/s while playing. */
  coarseTime: Ref<number>
  /** rAF loop for original-mode playback (no-op when paused). */
  start(): void
  stop(): void
}

export const PLAYBACK_COARSE_INTERVAL_MS = 100

export function createPlaybackClock(options: {
  getVideoTime: () => number
  isPlaying: () => boolean
  requestFrame?: (cb: () => void) => number
  cancelFrame?: (id: number) => void
  /** Monotonic ms source; injectable for deterministic tests. */
  now?: () => number
}): PlaybackClock {
  const requestFrame =
    options.requestFrame ?? ((cb: () => void) => requestAnimationFrame(cb))
  const cancelFrame =
    options.cancelFrame ?? ((id: number) => cancelAnimationFrame(id))
  const now = options.now ?? (() => performance.now())

  let rawTime = 0
  let lastCoarseAt = -Infinity
  let frameId: number | null = null
  const listeners = new Set<(time: number) => void>()
  const coarseTime = ref(0)

  function ingest(time: number): void {
    rawTime = time
    for (const cb of listeners) cb(time)
    const t = now()
    const immediate = !options.isPlaying()
    if (immediate || t - lastCoarseAt >= PLAYBACK_COARSE_INTERVAL_MS) {
      lastCoarseAt = t
      if (coarseTime.value !== time) coarseTime.value = time
    }
  }

  function loop(): void {
    frameId = null
    if (!options.isPlaying()) return
    ingest(options.getVideoTime())
    frameId = requestFrame(loop)
  }

  return {
    getTime: () => rawTime,
    isPlaying: options.isPlaying,
    ingest,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    coarseTime,
    start() {
      if (frameId === null) frameId = requestFrame(loop)
    },
    stop() {
      if (frameId !== null) {
        cancelFrame(frameId)
        frameId = null
      }
    },
  }
}

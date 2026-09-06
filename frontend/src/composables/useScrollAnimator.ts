/**
 * v3.0.3 M2-1 (P2-1): follow smooth animation scheduler.
 *
 * PURE logic module -- no component, bridge, or useRowLayout imports
 * (SPEC M0-1: "禁止 import 组件/bridge"). The editor hands in the per-frame
 * write channel (which does the echo marking) and injectable rAF/now for
 * vitest. One animator per WaveformEditor instance.
 *
 * Rulings (SPEC M2-1):
 * - ease-out cubic, ~140ms target duration; instant path = durationMs 0.
 * - animateTo while active RETARGETS from the current written value (no
 *   second loop -- 同帧单写).
 * - time-window echo suppression: scroll events arriving while the
 *   animator (or the grace window after its last write) is driving are
 *   animation echoes, not manual scrolls -- the 3.0.2 blank-suspicion
 *   defense extension to the markManualScroll/consumeAutoScroll loop.
 * - the smooth switch (localStorage) defaults FALSE (instant); A/B
 *   裁决 may flip the default and writes back to SPEC M2-1.
 */
export const FOLLOW_SMOOTH_DURATION_MS = 140
export const FOLLOW_SMOOTH_EASING = "easeOutCubic"
/** localStorage switch (M0-1.4: sibling view-state key, never persisted). */
export const FOLLOW_SMOOTH_STORAGE_KEY = "milocut:timeline-follow-smooth:v1"
/** Grace window after the last animation write that still counts as echo. */
export const SCROLL_ECHO_WINDOW_MS = 100

/** easeOutCubic: fast start, decelerating landing. */
export function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

function defaultStorage(): Storage | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage : null
  } catch {
    return null
  }
}

/**
 * Tolerant switch read (R2.3): missing / corrupt JSON / non-boolean ->
 * default FALSE (instant). Strict `=== true` keeps "1"/"yes" strings from
 * enabling smooth accidentally.
 */
export function readSmoothEnabled(storage: { getItem(key: string): string | null } = defaultStorage() as { getItem(key: string): string | null }): boolean {
  if (!storage || typeof storage.getItem !== "function") return false
  try {
    const raw = storage.getItem(FOLLOW_SMOOTH_STORAGE_KEY)
    if (raw === null) return false
    return JSON.parse(raw) === true
  } catch {
    return false
  }
}

/** A/B tooling counterpart of readSmoothEnabled (JSON-encoded boolean). */
export function writeSmoothEnabled(value: boolean, storage: { setItem(key: string, value: string): void } = defaultStorage() as { setItem(key: string, value: string): void }): void {
  if (!storage || typeof storage.setItem !== "function") return
  storage.setItem(FOLLOW_SMOOTH_STORAGE_KEY, JSON.stringify(value))
}

interface AnimatorDeps {
  /** Per-frame channel (editor supplies echo marking + scrollTop write). */
  write: (top: number) => void
  raf?: (cb: FrameRequestCallback) => number
  caf?: (handle: number) => void
  now?: () => number
}

export interface ScrollAnimator {
  /**
   * Animate the write channel to `target`. durationMs <= 0 = instant
   * passthrough. While active, retargets from the current value (single
   * loop, no stacking). `from` overrides the start value (jump wrapping).
   */
  animateTo(target: number, opts?: { durationMs?: number; from?: number }): void
  /** Redirect while active = continue from the current value to `target`. */
  redirect(target: number): void
  /** Stop the animation; the channel keeps its last written value. */
  cancel(): void
  isActive(): boolean
  /** Echo-window predicate for the scroll classifier (R2.2). */
  inEchoWindow(): boolean
  /** Unmount cleanup: cancel + permanently ignore further calls. */
  dispose(): void
}

export function createScrollAnimator(deps: AnimatorDeps): ScrollAnimator {
  const write = deps.write
  const raf = deps.raf ?? ((cb: FrameRequestCallback) => requestAnimationFrame(cb))
  const caf = deps.caf ?? ((handle: number) => cancelAnimationFrame(handle))
  const now = deps.now ?? (() => performance.now())

  let handle: number | null = null
  let from = 0
  let target = 0
  let startedAt = 0
  let durationMs = FOLLOW_SMOOTH_DURATION_MS
  let current: number | null = null // last written value (redirect basis)
  let lastWriteAt = -Infinity
  let disposed = false

  function stopLoop(): void {
    if (handle !== null) {
      caf(handle)
      handle = null
    }
  }

  function step(): void {
    handle = null
    if (disposed) return
    const t = durationMs > 0 ? Math.min(1, (now() - startedAt) / durationMs) : 1
    const value = from + (target - from) * easeOutCubic(t)
    current = value
    lastWriteAt = now()
    write(value)
    if (t >= 1) {
      return // landed exactly on target
    }
    handle = raf(step)
  }

  function animateTo(nextTarget: number, opts?: { durationMs?: number; from?: number }): void {
    if (disposed) return
    // Blank-guard parity with writeScrollTop: NaN/Inf never reach the channel.
    if (!Number.isFinite(nextTarget)) return
    const ms = opts?.durationMs ?? FOLLOW_SMOOTH_DURATION_MS
    if (!(ms > 0)) {
      // Instant passthrough (durationMs: 0 直通).
      cancel()
      current = nextTarget
      lastWriteAt = now()
      write(nextTarget)
      return
    }
    const start = opts?.from ?? current
    if (start === null || !Number.isFinite(start)) {
      // Nothing to animate from (fresh instance): land directly.
      cancel()
      current = nextTarget
      lastWriteAt = now()
      write(nextTarget)
      return
    }
    // (Re)arm ONE loop -- retargeting never stacks a second rAF chain.
    stopLoop()
    from = start
    target = nextTarget
    durationMs = ms
    startedAt = now()
    handle = raf(step)
  }

  function redirect(nextTarget: number): void {
    animateTo(nextTarget)
  }

  function cancel(): void {
    stopLoop()
  }

  function isActive(): boolean {
    return handle !== null
  }

  function inEchoWindow(): boolean {
    return isActive() || now() - lastWriteAt <= SCROLL_ECHO_WINDOW_MS
  }

  function dispose(): void {
    stopLoop()
    disposed = true
  }

  return { animateTo, redirect, cancel, isActive, inEchoWindow, dispose }
}

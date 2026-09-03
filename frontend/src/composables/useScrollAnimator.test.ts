import { describe, it, expect } from "vitest"
import {
  createScrollAnimator,
  easeOutCubic,
  readSmoothEnabled,
  writeSmoothEnabled,
  FOLLOW_SMOOTH_DURATION_MS,
  FOLLOW_SMOOTH_EASING,
  FOLLOW_SMOOTH_STORAGE_KEY,
  SCROLL_ECHO_WINDOW_MS,
} from "./useScrollAnimator"

/** Manual rAF/clock harness: frames advance only when pumpFrame runs. */
function makeHarness() {
  let nowMs = 0
  let nextHandle = 0
  const queue = new Map<number, FrameRequestCallback>()
  const raf = (cb: FrameRequestCallback): number => {
    queue.set(++nextHandle, cb)
    return nextHandle
  }
  const caf = (handle: number): void => {
    queue.delete(handle)
  }
  const now = () => nowMs

  /** Advance the clock and run every queued callback once (one frame). */
  function pumpFrame(deltaMs = 16): void {
    nowMs += deltaMs
    const cbs = [...queue.values()]
    queue.clear()
    for (const cb of cbs) cb(nowMs)
  }

  return { raf, caf, now, pumpFrame, queueSize: () => queue.size }
}

describe("useScrollAnimator constants (M2-1 contract)", () => {
  it("exposes the SPEC numbers", () => {
    expect(FOLLOW_SMOOTH_DURATION_MS).toBe(140)
    expect(FOLLOW_SMOOTH_EASING).toBe("easeOutCubic")
    expect(FOLLOW_SMOOTH_STORAGE_KEY).toBe("milocut:timeline-follow-smooth:v1")
    expect(easeOutCubic(0)).toBe(0)
    expect(easeOutCubic(1)).toBe(1)
    expect(easeOutCubic(0.5)).toBeCloseTo(0.875, 10)
  })
})

describe("createScrollAnimator", () => {
  it("durationMs 0 is an instant passthrough (直通): one write, no rAF", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(300, { durationMs: 0 })
    expect(writes).toEqual([300])
    expect(h.queueSize()).toBe(0)
    a.animateTo(400, { durationMs: 0 })
    expect(writes).toEqual([300, 400])
  })

  it("rejects non-finite targets (blank-guard parity)", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(Number.NaN)
    a.animateTo(Number.POSITIVE_INFINITY, { durationMs: 0 })
    expect(writes).toEqual([])
    expect(h.queueSize()).toBe(0)
  })

  it("animates from -> target and lands EXACTLY on target", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(500, { from: 0 })
    expect(a.isActive()).toBe(true)
    expect(writes).toEqual([])
    for (let i = 0; i < 20; i++) h.pumpFrame(16)
    expect(writes.length).toBeGreaterThan(0)
    expect(writes[writes.length - 1]).toBeCloseTo(500, 9)
    expect(writes[1]).toBeGreaterThan(writes[0]) // monotonic ease-out
    expect(a.isActive()).toBe(false)
    const countAtRest = writes.length
    h.pumpFrame(16)
    expect(writes.length).toBe(countAtRest) // loop is dead after landing
  })

  it("redirect mid-flight: no stacking (one rAF chain), continues from the current value", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(1000, { from: 0 })
    h.pumpFrame(16)
    h.pumpFrame(16)
    expect(a.isActive()).toBe(true)
    const chainBefore = h.queueSize()
    expect(chainBefore).toBe(1)
    // 3 more animateTo/redirect calls must NOT stack 3 more loops.
    a.redirect(300)
    a.animateTo(400)
    a.redirect(500)
    expect(h.queueSize()).toBe(1)
    for (let i = 0; i < 20; i++) h.pumpFrame(16)
    expect(writes[writes.length - 1]).toBeCloseTo(500, 9)
  })

  it("cancel stops writes; the channel keeps its last value", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(900, { from: 0 })
    h.pumpFrame(16)
    const stoppedAt = writes[writes.length - 1]
    a.cancel()
    expect(a.isActive()).toBe(false)
    h.pumpFrame(16)
    h.pumpFrame(16)
    expect(writes).toHaveLength(writes.indexOf(stoppedAt) + 1)
  })

  it("dispose: no rAF leak -- further calls are ignored after unmount", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(700, { from: 0 })
    expect(h.queueSize()).toBe(1)
    a.dispose()
    expect(h.queueSize()).toBe(0)
    h.pumpFrame(16)
    expect(writes).toEqual([])
    a.animateTo(700, { from: 0 })
    a.redirect(800)
    expect(h.queueSize()).toBe(0)
    expect(writes).toEqual([])
  })

  it("inEchoWindow: true while driving and during the grace, false after", () => {
    const h = makeHarness()
    const a = createScrollAnimator({ write: () => {}, raf: h.raf, caf: h.caf, now: h.now })
    expect(a.inEchoWindow()).toBe(false)
    a.animateTo(200, { from: 0 })
    h.pumpFrame(16)
    expect(a.inEchoWindow()).toBe(true) // active
    a.cancel()
    expect(a.inEchoWindow()).toBe(true) // grace window right after the last write
    h.pumpFrame(SCROLL_ECHO_WINDOW_MS + 1)
    expect(a.inEchoWindow()).toBe(false)
  })

  it("fresh instance with no `from` and no writes lands directly (nothing to animate)", () => {
    const h = makeHarness()
    const writes: number[] = []
    const a = createScrollAnimator({ write: v => writes.push(v), raf: h.raf, caf: h.caf, now: h.now })
    a.animateTo(150)
    expect(writes).toEqual([150])
    expect(a.isActive()).toBe(false)
  })
})

describe("smooth switch storage (R2.3 tolerant read)", () => {
  function fakeStorage(raw: string | null, broken = false) {
    return {
      getItem: () => {
        if (broken) throw new Error("quota")
        return raw
      },
      setItem: () => {},
    }
  }

  it("missing key -> false (default OFF)", () => {
    expect(readSmoothEnabled(fakeStorage(null))).toBe(false)
  })

  it("valid values round-trip", () => {
    expect(readSmoothEnabled(fakeStorage("true"))).toBe(true)
    expect(readSmoothEnabled(fakeStorage("false"))).toBe(false)
    const store = new Map<string, string>()
    writeSmoothEnabled(true, {
      setItem: (k, v) => store.set(k, v),
    })
    expect(store.get(FOLLOW_SMOOTH_STORAGE_KEY)).toBe("true")
  })

  it("corrupt JSON / wrong types / broken storage -> false (never throws)", () => {
    expect(readSmoothEnabled(fakeStorage("{not json"))).toBe(false)
    expect(readSmoothEnabled(fakeStorage('"yes"'))).toBe(false) // JSON string
    expect(readSmoothEnabled(fakeStorage("1"))).toBe(false) // JSON number
    expect(readSmoothEnabled(fakeStorage("null"))).toBe(false)
    expect(readSmoothEnabled(fakeStorage("true", true))).toBe(false) // getter throws
    expect(readSmoothEnabled(null as unknown as Storage)).toBe(false)
  })
})

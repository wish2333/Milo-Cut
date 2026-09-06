import { describe, it, expect } from "vitest"
import { nextTick, watch } from "vue"
import { createPlaybackClock, PLAYBACK_COARSE_INTERVAL_MS } from "./usePlaybackClock"

/** Manual frame queue so the loop is deterministic. */
function createFrameQueue() {
  const pending = new Map<number, () => void>()
  let nextId = 1
  return {
    get queue(): Array<() => void> {
      return [...pending.values()]
    },
    request: (cb: () => void) => {
      const id = nextId++
      pending.set(id, cb)
      return id
    },
    cancel: (id: number) => {
      pending.delete(id)
    },
    /** Fire every queued callback in order, then clear. */
    flush() {
      const queued = [...pending.values()]
      pending.clear()
      for (const cb of queued) cb()
    },
  }
}

/** Deterministic monotonic clock helpers live inline per-test (`let ms = 0`). */

describe("createPlaybackClock", () => {
  it("coarse mirror is throttled while playing, raw time stays fresh", () => {
    let ms = 0
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => true,
      now: () => ms,
    })
    clock.ingest(0.01) // first sample: lastCoarseAt = -Infinity -> writes
    expect(clock.coarseTime.value).toBe(0.01)

    ms = 50 // still inside the 100ms window
    clock.ingest(0.05)
    expect(clock.coarseTime.value).toBe(0.01) // throttled
    clock.ingest(0.09)
    expect(clock.coarseTime.value).toBe(0.01)
    expect(clock.getTime()).toBe(0.09) // raw stays fresh
  })

  it("coarse mirror writes immediately when paused", () => {
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => false,
      now: () => 0,
    })
    clock.ingest(5)
    expect(clock.coarseTime.value).toBe(5)
    clock.ingest(7)
    expect(clock.coarseTime.value).toBe(7)
  })

  it("resumes coarse writes once the interval elapses", () => {
    let ms = 0
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => true,
      now: () => ms,
    })
    clock.ingest(1)
    expect(clock.coarseTime.value).toBe(1)
    ms = PLAYBACK_COARSE_INTERVAL_MS + 1
    clock.ingest(2)
    expect(clock.coarseTime.value).toBe(2)
  })

  it("skips value-identical coarse writes (demo bridge cannot loop)", async () => {
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => false,
      now: () => 0,
    })
    const coarseWrites: number[] = []
    watch(clock.coarseTime, (t) => coarseWrites.push(t))
    clock.ingest(3)
    clock.ingest(3) // identical sample: no reactive write, no loop
    await nextTick()
    expect(clock.coarseTime.value).toBe(3)
    expect(clock.getTime()).toBe(3)
    expect(coarseWrites).toEqual([3])
  })

  it("notifies raw subscribers on every sample and supports unsubscribe", () => {
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => false,
      now: () => 0,
    })
    const a: number[] = []
    const b: number[] = []
    const un = clock.subscribe((t) => a.push(t))
    clock.subscribe((t) => b.push(t))
    clock.ingest(1)
    un()
    clock.ingest(2)
    expect(a).toEqual([1])
    expect(b).toEqual([1, 2])
  })

  it("start() runs a per-frame ingest loop only while playing", () => {
    const frames = createFrameQueue()
    const videoTime = { t: 0 }
    const clock = createPlaybackClock({
      getVideoTime: () => videoTime.t,
      isPlaying: () => videoTime.t < 10, // "ends" at t=10
      requestFrame: frames.request,
      cancelFrame: frames.cancel,
      now: () => 0,
    })
    const samples: number[] = []
    clock.subscribe((t) => samples.push(t))

    videoTime.t = 1
    clock.start()
    frames.flush() // frame 1: playing -> ingest(1), re-queue
    videoTime.t = 2
    frames.flush() // frame 2: ingest(2)
    expect(samples).toEqual([1, 2])
    expect(frames.queue.length).toBe(1)

    videoTime.t = 10 // not playing anymore
    frames.flush() // loop observes and does not re-queue
    expect(frames.queue.length).toBe(0)
    expect(samples).toEqual([1, 2])
  })

  it("stop() cancels the loop", () => {
    const frames = createFrameQueue()
    const clock = createPlaybackClock({
      getVideoTime: () => 0,
      isPlaying: () => true,
      requestFrame: frames.request,
      cancelFrame: frames.cancel,
      now: () => 0,
    })
    const samples: number[] = []
    clock.subscribe((t) => samples.push(t))
    clock.start()
    clock.stop()
    frames.flush()
    expect(samples).toEqual([])
    expect(frames.queue.length).toBe(0)
  })
})

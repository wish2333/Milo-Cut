import { describe, it, expect } from "vitest"
import { createRafScheduler } from "./rafScheduler"

/** Manual frame queue: tests decide exactly when frames fire. */
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

describe("createRafScheduler", () => {
  it("coalesces 10 schedule calls into a single task run", () => {
    const frames = createFrameQueue()
    let draws = 0
    const scheduler = createRafScheduler(() => draws++, frames.request, frames.cancel)

    for (let i = 0; i < 10; i++) scheduler.schedule()
    expect(draws).toBe(0)
    expect(scheduler.pending).toBe(true)
    expect(frames.queue.length).toBe(1) // only one frame requested

    frames.flush()
    expect(draws).toBe(1)
    expect(scheduler.pending).toBe(false)
  })

  it("schedules a new frame for calls made after the task ran", () => {
    const frames = createFrameQueue()
    let draws = 0
    const scheduler = createRafScheduler(() => draws++, frames.request, frames.cancel)

    scheduler.schedule()
    frames.flush()
    scheduler.schedule()
    frames.flush()
    expect(draws).toBe(2)
  })

  it("drops a pending task on cancel", () => {
    const frames = createFrameQueue()
    let draws = 0
    const scheduler = createRafScheduler(() => draws++, frames.request, frames.cancel)

    scheduler.schedule()
    scheduler.cancel()
    frames.flush()
    expect(draws).toBe(0)
    expect(scheduler.pending).toBe(false)
  })

  it("cancel without a pending task is a no-op", () => {
    const frames = createFrameQueue()
    const scheduler = createRafScheduler(() => {}, frames.request, frames.cancel)
    expect(() => scheduler.cancel()).not.toThrow()
  })
})

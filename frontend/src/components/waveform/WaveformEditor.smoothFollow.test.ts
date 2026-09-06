/**
 * v3.0.3 M2-1 (P2-1): WaveformEditor smooth follow integration.
 *
 * Editor-level contract on top of the pure useScrollAnimator tests:
 * - smooth switch ON -> navigation jumps (exposed revealTime / overview
 *   seek) animate 140ms ease-out; the DOM stays pinned at the start value
 *   until the first frame (no destination flash).
 * - smooth switch OFF (DEFAULT) -> jumps stay instant (v3.0.2 semantics).
 * - the playback-clock consumption path NEVER animates (R2.2 guard).
 * - a wheel gesture during an animation cancels it (manual priority).
 * - unmount disposes the animator (no rAF leak).
 * - trusted scroll events during the animation echo window never arm the
 *   manual cooldown (time-window suppression).
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from "vitest"
import { mount, type VueWrapper } from "@vue/test-utils"
import WaveformEditor from "./WaveformEditor.vue"
import { ROW_LAYOUT_STORAGE_KEY } from "@/composables/useRowLayout"
import {
  writeSmoothEnabled,
  FOLLOW_SMOOTH_DURATION_MS,
} from "@/composables/useScrollAnimator"

// Anchor math needs a real viewport (happy-dom reports 0): mirror the
// M5-1 harness -- multi-scroll container reads as 320px.
let clientHeightDescriptor: PropertyDescriptor | undefined

beforeAll(() => {
  clientHeightDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientHeight")
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get(this: HTMLElement) {
      if (this.getAttribute?.("data-test") === "multi-scroll") return 320
      return clientHeightDescriptor?.get?.call(this) ?? 0
    },
  })
})

afterAll(() => {
  if (clientHeightDescriptor) {
    Object.defineProperty(HTMLElement.prototype, "clientHeight", clientHeightDescriptor)
  }
})

// Manual rAF + clock: the editor's animator uses window rAF/performance.now
// by default, so stub the globals and drive frames deterministically.
let rafQueue: Map<number, FrameRequestCallback>
let rafSeq: number
let nowMs: number

function pumpFrame(deltaMs = 16): void {
  nowMs += deltaMs
  const cbs = [...rafQueue.values()]
  rafQueue.clear()
  for (const cb of cbs) cb(nowMs)
}

function pumpUntilLanded(maxFrames = 30): void {
  for (let i = 0; i < maxFrames && rafQueue.size > 0; i++) pumpFrame(FOLLOW_SMOOTH_DURATION_MS / 3)
  pumpFrame(16)
}

function trustedScroll(el: HTMLElement): void {
  const ev = new Event("scroll")
  Object.defineProperty(ev, "isTrusted", { value: true })
  el.dispatchEvent(ev)
}

function dispatchPlainWheel(el: HTMLElement): void {
  el.dispatchEvent(new WheelEvent("wheel", { deltaY: 120, bubbles: true, cancelable: true }))
}

describe("WaveformEditor smooth follow (M2-1)", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    nowMs = 0
    rafSeq = 0
    rafQueue = new Map()
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      rafQueue.set(++rafSeq, cb)
      return rafSeq
    })
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      rafQueue.delete(id)
    })
    vi.stubGlobal("performance", { now: () => nowMs })
    localStorage.clear()
    localStorage.setItem(
      ROW_LAYOUT_STORAGE_KEY,
      JSON.stringify({ mode: "multi", secondsPerRow: 10, rowHeight: 120 }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllTimers()
    vi.useRealTimers()
    localStorage.clear()
  })

  function mountSmooth(currentTime = 5): VueWrapper {
    return mount(WaveformEditor, {
      props: { segments: [], edits: [], duration: 100, currentTime },
      global: {
        stubs: {
          WaveformCanvas: true,
          TimeMarksLayer: true,
          SegmentBlocksLayer: true,
          ScrollbarStrip: true,
          PlayheadOverlay: true,
        },
      },
    })
  }

  function scrollElOf(wrapper: VueWrapper): HTMLElement {
    return wrapper.find('[data-test="multi-scroll"]').element as HTMLElement
  }

  function reveal(wrapper: VueWrapper, time: number): void {
    ;(wrapper.vm as unknown as { revealTime: (t: number) => void }).revealTime(time)
  }

  it("smooth ON: navigation jump animates (pinned at start, lands on the kernel target)", async () => {
    writeSmoothEnabled(true)
    const wrapper = mountSmooth()
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45) // kernel target 376 (row 4, REVEAL_BIAS 0.45)
    // NOT instant: DOM pinned at the start value, animation armed.
    expect(el.scrollTop).toBe(0)
    pumpFrame(16)
    const firstFrame = el.scrollTop
    expect(firstFrame).toBeGreaterThan(0)
    expect(firstFrame).toBeLessThan(376)
    pumpUntilLanded()
    expect(el.scrollTop).toBe(376)
    wrapper.unmount()
  })

  it("smooth OFF (default): navigation jump stays instant (v3.0.2 semantics)", async () => {
    const wrapper = mountSmooth()
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45)
    await wrapper.vm.$nextTick() // the reflector watcher is async
    expect(el.scrollTop).toBe(376) // immediate
    pumpFrame(16)
    expect(el.scrollTop).toBe(376)
    wrapper.unmount()
  })

  it("smooth ON: the playback-clock path NEVER starts an animation (R2.2 guard)", async () => {
    writeSmoothEnabled(true)
    const wrapper = mountSmooth(5)
    const el = scrollElOf(wrapper)
    await wrapper.setProps({ currentTime: 25 }) // row change -> follow write 148
    expect(el.scrollTop).toBe(148) // instant, no easing
    pumpFrame(16)
    pumpFrame(16)
    expect(el.scrollTop).toBe(148) // no animation took over
    wrapper.unmount()
  })

  it("smooth ON: a plain wheel gesture during the animation cancels it", async () => {
    writeSmoothEnabled(true)
    const wrapper = mountSmooth()
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45)
    pumpFrame(16)
    const stoppedAt = el.scrollTop
    expect(stoppedAt).toBeGreaterThan(0)
    dispatchPlainWheel(el)
    pumpFrame(16)
    pumpFrame(16)
    expect(el.scrollTop).toBe(stoppedAt) // no further writes
    wrapper.unmount()
  })

  it("unmount during an animation leaves no rAF leak", async () => {
    writeSmoothEnabled(true)
    const wrapper = mountSmooth()
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45)
    pumpFrame(16)
    expect(rafQueue.size).toBeGreaterThan(0)
    wrapper.unmount()
    expect(rafQueue.size).toBe(0)
    pumpFrame(16)
    expect(el.scrollTop).toBeGreaterThan(0) // channel kept its last value
  })

  it("trusted scroll during the animation echo window never arms the cooldown", async () => {
    writeSmoothEnabled(true)
    const wrapper = mountSmooth(5)
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45)
    pumpFrame(16)
    pumpFrame(16)
    trustedScroll(el) // mid-animation: echo window -> ignored entirely
    pumpUntilLanded()
    expect(el.scrollTop).toBe(376)
    // The kernel revealTime armed its own 3s jump cooldown; the animation's
    // echo events must NOT extend it with a manual cooldown.
    vi.advanceTimersByTime(3001)
    await wrapper.setProps({ currentTime: 65 }) // row 6 -> follows again
    expect(el.scrollTop).toBe(668)
    wrapper.unmount()
  })

  it("flipping the localStorage key mid-session takes effect on the next jump, no remount", async () => {
    // start OFF: jump is instant
    const wrapper = mountSmooth()
    const el = scrollElOf(wrapper)
    reveal(wrapper, 45)
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(376)
    pumpFrame(16)
    pumpFrame(16)

    // flip ON (same component instance): next jump animates
    writeSmoothEnabled(true)
    reveal(wrapper, 65) // row 6, REVEAL_BIAS 0.45 -> kernel target 636
    expect(el.scrollTop).not.toBe(636) // pinned at the previous position
    pumpUntilLanded()
    expect(el.scrollTop).toBe(636)

    // flip back OFF: instant again
    writeSmoothEnabled(false)
    reveal(wrapper, 85) // row 8 -> 896
    await wrapper.vm.$nextTick()
    expect(el.scrollTop).toBe(896)
    pumpFrame(16)
    expect(el.scrollTop).toBe(896)
    wrapper.unmount()
  })
})

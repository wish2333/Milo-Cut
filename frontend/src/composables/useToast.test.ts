/**
 * v3.0.2 R9.5: toast stack policy -- cap 3 + high-frequency cooldown.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest"
import {
  useToast,
  MAX_VISIBLE_TOASTS,
  TOAST_HIGH_FREQ_COOLDOWN_MS,
} from "./useToast"

describe("useToast stack policy (R9.5)", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    const { toasts } = useToast()
    toasts.value = []
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("keeps at most 3 toasts, dropping the oldest", () => {
    const { showToast, toasts } = useToast()
    for (const m of ["a", "b", "c", "d", "e"]) showToast(m, "info", 10_000)
    expect(toasts.value.map(t => t.message)).toEqual(["c", "d", "e"])
    expect(toasts.value.length).toBe(MAX_VISIBLE_TOASTS)
  })

  it("swallows an identical message inside the cooldown window", () => {
    const { showToast, toasts } = useToast()
    showToast("same", "info", 10_000)
    showToast("same", "info", 10_000) // within 500ms: swallowed
    expect(toasts.value.length).toBe(1)
    vi.advanceTimersByTime(TOAST_HIGH_FREQ_COOLDOWN_MS + 1)
    showToast("same", "info", 10_000) // cooldown expired: allowed
    expect(toasts.value.length).toBe(2)
  })

  it("different messages never cooldown-dedupe", () => {
    const { showToast, toasts } = useToast()
    showToast("x", "info", 10_000)
    showToast("y", "info", 10_000)
    showToast("z", "info", 10_000)
    expect(toasts.value.length).toBe(3)
  })

  it("toasts still expire after their duration", () => {
    const { showToast, toasts } = useToast()
    showToast("temp", "info", 3000)
    expect(toasts.value.length).toBe(1)
    vi.advanceTimersByTime(3000)
    expect(toasts.value.length).toBe(0)
  })
})

import { describe, it, expect } from "vitest"
import type { EditDecision, Segment } from "@/types/project"
import {
  isOverlapping,
  getEditForSegment,
  getEffectiveStatus,
  getEditStatus,
} from "./segmentHelpers"

function seg(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "seg-1",
    version: 1,
    type: "subtitle",
    start: 1.0,
    end: 5.0,
    text: "hello",
    speaker: "",
    ...overrides,
  }
}

function edit(overrides: Partial<EditDecision> = {}): EditDecision {
  return {
    id: "ed-1",
    start: 1.0,
    end: 5.0,
    action: "delete",
    source: "silence",
    status: "pending",
    priority: 100,
    target_type: "range",
    ...overrides,
  }
}

describe("isOverlapping", () => {
  it("returns true when edit overlaps segment", () => {
    expect(isOverlapping(edit({ start: 0, end: 3 }), seg())).toBe(true)
  })

  it("returns true when edit is fully inside segment", () => {
    expect(isOverlapping(edit({ start: 2, end: 4 }), seg())).toBe(true)
  })

  it("returns false when edit ends before segment starts", () => {
    expect(isOverlapping(edit({ start: 0, end: 1 }), seg())).toBe(false)
  })

  it("returns false when edit starts after segment ends", () => {
    expect(isOverlapping(edit({ start: 5, end: 8 }), seg())).toBe(false)
  })

  it("returns false when overlap is below threshold", () => {
    // seg: 1.0-5.0, edit: 4.9-6.0 => overlap 0.1s, threshold 0.3s
    expect(isOverlapping(edit({ start: 4.9, end: 6.0 }), seg(), 0.3)).toBe(false)
  })

  it("returns true when overlap exceeds threshold", () => {
    // seg: 1.0-5.0, edit: 4.5-6.0 => overlap 0.5s, threshold 0.3s
    expect(isOverlapping(edit({ start: 4.5, end: 6.0 }), seg(), 0.3)).toBe(true)
  })
})

describe("getEditForSegment", () => {
  it("matches by target_id first", () => {
    const byId = edit({ id: "by-id", target_id: "seg-1" })
    const byRange = edit({ id: "by-range", target_type: "range", start: 1, end: 5 })
    expect(getEditForSegment([byRange, byId], seg())).toBe(byId)
  })

  it("falls back to time-range match", () => {
    const byRange = edit({ target_type: "range", start: 1, end: 5 })
    expect(getEditForSegment([byRange], seg())).toBe(byRange)
  })

  it("returns undefined when no match", () => {
    const unrelated = edit({ target_type: "range", start: 10, end: 20 })
    expect(getEditForSegment([unrelated], seg())).toBeUndefined()
  })
})

describe("getEffectiveStatus", () => {
  it("returns normal when no edits", () => {
    expect(getEffectiveStatus([], seg())).toBe("normal")
  })

  it("returns masked when highest priority edit is delete", () => {
    const del = edit({ action: "delete", priority: 100, target_id: "seg-1" })
    expect(getEffectiveStatus([del], seg())).toBe("masked")
  })

  it("returns kept when highest priority edit is keep", () => {
    const keep = edit({ action: "keep", priority: 100, target_id: "seg-1" })
    expect(getEffectiveStatus([keep], seg())).toBe("kept")
  })

  it("picks highest priority when multiple edits conflict", () => {
    const low = edit({ action: "keep", priority: 50, target_id: "seg-1" })
    const high = edit({ action: "delete", priority: 200, target_id: "seg-1" })
    expect(getEffectiveStatus([low, high], seg())).toBe("masked")
  })

  it("returns normal when only edit is rejected", () => {
    const rejected = edit({ action: "delete", status: "rejected", target_id: "seg-1" })
    expect(getEffectiveStatus([rejected], seg())).toBe("normal")
  })

  it("falls through to lower priority when highest is rejected", () => {
    const rejectedHigh = edit({ action: "delete", priority: 200, status: "rejected", target_id: "seg-1" })
    const pendingLow = edit({ action: "delete", priority: 50, status: "pending", target_id: "seg-1" })
    expect(getEffectiveStatus([rejectedHigh, pendingLow], seg())).toBe("masked")
  })

  it("returns normal when all edits are rejected", () => {
    const r1 = edit({ id: "e1", action: "delete", status: "rejected", target_id: "seg-1" })
    const r2 = edit({ id: "e2", action: "keep", status: "rejected", target_id: "seg-1" })
    expect(getEffectiveStatus([r1, r2], seg())).toBe("normal")
  })

  it("ignores edits below overlap threshold", () => {
    // seg: 1.0-5.0, edit: 4.9-5.1 => overlap 0.1s < 0.3s threshold
    const marginal = edit({ start: 4.9, end: 5.1, action: "delete", status: "pending" })
    expect(getEffectiveStatus([marginal], seg())).toBe("normal")
  })
})

describe("getEditStatus", () => {
  it("returns status of matching edit", () => {
    const e = edit({ target_id: "seg-1", status: "confirmed" })
    expect(getEditStatus([e], seg())).toBe("confirmed")
  })

  it("returns null when no matching edit", () => {
    expect(getEditStatus([], seg())).toBeNull()
  })
})

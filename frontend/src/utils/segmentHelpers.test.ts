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

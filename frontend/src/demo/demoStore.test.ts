import { beforeEach, describe, expect, it } from "vitest"
import { createDemoProject } from "./demoProject"
import { demoStore } from "./demoStore"

describe("demoStore", () => {
  beforeEach(() => demoStore.reset())

  it("creates a stable fixture with valid segment references", () => {
    const project = createDemoProject()
    const segments = new Set(project.timelines[0].transcript.segments.map((segment) => segment.id))
    expect(project.media?.duration).toBe(90)
    expect(project.timelines[0].transcript.segments.length).toBeGreaterThanOrEqual(12)
    expect(project.timelines[0].edits.every((edit) => edit.target_id && segments.has(edit.target_id))).toBe(true)
    expect(project.timelines[0].transcript.segments).toEqual(
      [...project.timelines[0].transcript.segments].sort((a, b) => a.start - b.start),
    )
  })

  it("updates only the selected subtitle and increments revision", () => {
    const target = demoStore.state.project.timelines[0].transcript.segments.find((segment) => segment.type === "subtitle")!
    const before = demoStore.state.project.timelines[0].transcript.segments.map((segment) => segment.text)
    demoStore.updateSegmentText(target.id, "已编辑的演示字幕")
    expect(demoStore.state.project.timelines[0].transcript.segments.find((segment) => segment.id === target.id)?.text).toBe("已编辑的演示字幕")
    expect(demoStore.state.project.timelines[0].transcript.segments.filter((segment) => segment.id !== target.id).map((segment) => segment.text)).toEqual(before.slice(1))
    expect(demoStore.state.revision).toBe(1)
  })

  it("derives the export summary from confirmed edits", () => {
    const edit = demoStore.state.project.timelines[0].edits[0]
    demoStore.setEditStatus(edit.id, "confirmed")
    const summary = demoStore.getEditSummary()
    expect(summary.edit_count).toBe(1)
    expect(summary.delete_duration).toBe(edit.end - edit.start)
  })

  it("accepts a correction and removes it from the review queue", () => {
    const correction = demoStore.getCorrections()[0]
    demoStore.acceptCorrection(correction.id)
    expect(demoStore.getCorrections().some((item) => item.id === correction.id)).toBe(false)
    expect(demoStore.state.project.timelines[0].transcript.segments.find((segment) => segment.id === correction.segment_id)?.text).toBe(correction.corrected_text)
  })

  it("resets all mutable state to the initial demo", () => {
    demoStore.setCurrentTime(42)
    demoStore.state.exportHistory.push({ id: "x", type: "export_video", created_at: "" })
    demoStore.reset()
    expect(demoStore.state.currentTime).toBe(0)
    expect(demoStore.state.exportHistory).toHaveLength(0)
    expect(demoStore.getCorrections()).toHaveLength(2)
  })
})


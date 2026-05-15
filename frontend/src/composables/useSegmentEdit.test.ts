import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref, type Ref, nextTick } from "vue"
import type { Project, Segment } from "@/types/project"
import { useSegmentEdit } from "./useSegmentEdit"

vi.mock("@/bridge", () => ({
  call: vi.fn(),
}))

import { call } from "@/bridge"
const mockCall = vi.mocked(call)

function makeSegment(overrides: Partial<Segment> = {}): Segment {
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

function makeProject(segs: Segment[] = [makeSegment()]): Project {
  return {
    schema_version: 1,
    project: { name: "test", created_at: "", updated_at: "" },
    media: null,
    transcript: { engine: "test", language: "en", segments: segs },
    analysis: { last_run: null, results: [] },
    edits: [],
  }
}

describe("useSegmentEdit", () => {
  let project: Ref<Project>
  let onProjectUpdate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    project = ref(makeProject()) as Ref<Project>
    onProjectUpdate = vi.fn((p: Project) => { project.value = p })
  })

  describe("selection", () => {
    it("selects and clears segment", () => {
      const { selectedSegmentId, selectSegment, clearSelection } = useSegmentEdit(project, onProjectUpdate)
      selectSegment("seg-1")
      expect(selectedSegmentId.value).toBe("seg-1")
      clearSelection()
      expect(selectedSegmentId.value).toBeNull()
    })

    it("selects and clears range", () => {
      const { selectedRange, selectRange, clearSelection } = useSegmentEdit(project, onProjectUpdate)
      selectRange(1.0, 5.0)
      expect(selectedRange.value).toEqual({ start: 1, end: 5 })
      clearSelection()
      expect(selectedRange.value).toBeNull()
    })
  })

  describe("updateSegmentTime", () => {
    it("applies optimistic update immediately", () => {
      const { updateSegmentTime } = useSegmentEdit(project, onProjectUpdate)
      updateSegmentTime("seg-1", "start", 2.0)
      expect(onProjectUpdate).toHaveBeenCalled()
      const updated = onProjectUpdate.mock.calls[0][0] as Project
      expect(updated.transcript.segments[0].start).toBe(2.0)
    })

    it("debounces backend call", async () => {
      mockCall.mockResolvedValue({ success: true, data: makeProject() })
      const { updateSegmentTime } = useSegmentEdit(project, onProjectUpdate)
      updateSegmentTime("seg-1", "start", 2.0)

      // Backend not called yet
      expect(mockCall).not.toHaveBeenCalled()

      // Advance past debounce
      vi.advanceTimersByTime(300)
      await nextTick()
      expect(mockCall).toHaveBeenCalledWith("update_segment", "seg-1", { start: 2.0 })
    })

    it("cancels previous debounce on rapid updates", () => {
      mockCall.mockResolvedValue({ success: true, data: makeProject() })
      const { updateSegmentTime } = useSegmentEdit(project, onProjectUpdate)
      updateSegmentTime("seg-1", "start", 2.0)
      updateSegmentTime("seg-1", "start", 3.0)

      vi.advanceTimersByTime(300)
      // Only one backend call with the latest value
      expect(mockCall).toHaveBeenCalledTimes(1)
      expect(mockCall).toHaveBeenCalledWith("update_segment", "seg-1", { start: 3.0 })
    })
  })

  describe("updateSegmentText", () => {
    it("calls backend immediately", async () => {
      const updatedProj = makeProject([makeSegment({ text: "changed" })])
      mockCall.mockResolvedValue({ success: true, data: updatedProj })
      const { updateSegmentText } = useSegmentEdit(project, onProjectUpdate)
      const result = await updateSegmentText("seg-1", "changed")
      expect(result).toBe(true)
      expect(mockCall).toHaveBeenCalledWith("update_segment_text", "seg-1", "changed")
      expect(onProjectUpdate).toHaveBeenCalledWith(updatedProj)
    })

    it("returns false on failure", async () => {
      mockCall.mockResolvedValue({ success: false, error: "fail" })
      const { updateSegmentText } = useSegmentEdit(project, onProjectUpdate)
      const result = await updateSegmentText("seg-1", "changed")
      expect(result).toBe(false)
    })
  })

  describe("toggleEditStatus", () => {
    it("creates delete edit when none exists", async () => {
      mockCall.mockResolvedValue({ success: true, data: makeProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(makeSegment())
      expect(mockCall).toHaveBeenCalledWith("mark_segments", ["seg-1"], "delete", "confirmed")
    })

    it("toggles confirmed to rejected", async () => {
      project.value = {
        ...makeProject(),
        edits: [{
          id: "ed-1",
          start: 1,
          end: 5,
          action: "delete",
          source: "test",
          status: "confirmed",
          priority: 100,
          target_type: "segment",
          target_id: "seg-1",
        }],
      }
      mockCall.mockResolvedValue({ success: true, data: makeProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(makeSegment())
      expect(mockCall).toHaveBeenCalledWith("update_edit_decision", "ed-1", "rejected")
    })

    it("toggles rejected edit back to confirmed instead of creating keep edit", async () => {
      project.value = {
        ...makeProject(),
        edits: [{
          id: "ed-rejected",
          start: 1,
          end: 5,
          action: "delete",
          source: "silence",
          status: "rejected",
          priority: 100,
          target_type: "segment",
          target_id: "seg-1",
        }],
      }
      mockCall.mockResolvedValue({ success: true, data: makeProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(makeSegment())
      expect(mockCall).not.toHaveBeenCalledWith("mark_segments", expect.anything(), expect.anything(), expect.anything())
      expect(mockCall).toHaveBeenCalledWith("update_edit_decision", "ed-rejected", "confirmed")
    })
  })

  describe("resolveState", () => {
    it("returns SegmentState from resolveSegmentState", () => {
      const { resolveState } = useSegmentEdit(project, onProjectUpdate)
      const state = resolveState(makeSegment())
      expect(state.displayStatus).toBe("none")
      expect(state.styleClass).toBe("normal")
      expect(state.activeEdit).toBeUndefined()
    })

    it("reflects active edit when present", () => {
      project.value = {
        ...makeProject(),
        edits: [{
          id: "ed-active",
          start: 1,
          end: 5,
          action: "delete",
          source: "user",
          status: "confirmed",
          priority: 200,
          target_type: "segment",
          target_id: "seg-1",
        }],
      }
      const { resolveState } = useSegmentEdit(project, onProjectUpdate)
      const state = resolveState(makeSegment())
      expect(state.displayStatus).toBe("confirmed")
      expect(state.styleClass).toBe("masked")
      expect(state.activeEdit).toBeDefined()
    })
  })

  describe("status queries", () => {
    it("getEffectiveStatus returns normal when no edits", () => {
      const { getEffectiveStatus } = useSegmentEdit(project, onProjectUpdate)
      expect(getEffectiveStatus(makeSegment())).toBe("normal")
    })

    it("getEditStatus returns null when no edits", () => {
      const { getEditStatus } = useSegmentEdit(project, onProjectUpdate)
      expect(getEditStatus(makeSegment())).toBeNull()
    })
  })
})

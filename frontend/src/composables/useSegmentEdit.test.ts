import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref, type Ref, nextTick } from "vue"
import type { Project } from "@/types/project"
import { useSegmentEdit } from "./useSegmentEdit"
import { mockProject, mockSegment } from "@/test/helpers/mockProject"

vi.mock("@/bridge", () => ({
  call: vi.fn(),
}))

import { call } from "@/bridge"
const mockCall = vi.mocked(call)

describe("useSegmentEdit", () => {
  let project: Ref<Project>
  let onProjectUpdate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    project = ref(mockProject()) as Ref<Project>
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
      expect(updated.timelines.find(t => t.id === updated.active_timeline_id)?.transcript.segments[0].start).toBe(2.0)
    })

    it("debounces backend call", async () => {
      mockCall.mockResolvedValue({ success: true, data: mockProject() })
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
      mockCall.mockResolvedValue({ success: true, data: mockProject() })
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
      const updatedProj = mockProject({ timelines: [{ id: "default", label: "原始", source: "default", created_at: "", parent_id: "", transcript: { engine: "test", language: "en", segments: [mockSegment({ text: "changed" })] }, edits: [], analysis: { last_run: null, results: [] } }] })
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
      mockCall.mockResolvedValue({ success: true, data: mockProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())
      expect(mockCall).toHaveBeenCalledWith("mark_segments", ["seg-1"], "delete", "confirmed")
    })

    it("toggles confirmed to rejected", async () => {
      project.value = {
        ...mockProject(),
        timelines: [{ ...mockProject().timelines[0], edits: [{
          id: "ed-1",
          start: 1,
          end: 5,
          action: "delete",
          source: "test",
          status: "confirmed",
          priority: 100,
          target_type: "segment",
          target_id: "seg-1",
        }] }],
      }
      mockCall.mockResolvedValue({ success: true, data: mockProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())
      expect(mockCall).toHaveBeenCalledWith("update_edit_decision", "ed-1", "rejected")
    })

    it("toggles rejected edit back to confirmed instead of creating keep edit", async () => {
      project.value = {
        ...mockProject(),
        timelines: [{ ...mockProject().timelines[0], edits: [{
          id: "ed-rejected",
          start: 1,
          end: 5,
          action: "delete",
          source: "silence",
          status: "rejected",
          priority: 100,
          target_type: "segment",
          target_id: "seg-1",
        }] }],
      }
      mockCall.mockResolvedValue({ success: true, data: mockProject() })
      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())
      expect(mockCall).not.toHaveBeenCalledWith("mark_segments", expect.anything(), expect.anything(), expect.anything())
      expect(mockCall).toHaveBeenCalledWith("update_edit_decision", "ed-rejected", "confirmed")
    })

    // v2.3.2 G3 regression: one toggle must produce exactly one write request
    // in the happy path. The previous implementation always issued a second
    // `get_project()` even when the write call already returned the full
    // Project. See docs/2.3.0/2.3.2-fix-report.md G3.

    it("uses update_edit_decision return value and skips get_project", async () => {
      project.value = {
        ...mockProject(),
        timelines: [{ ...mockProject().timelines[0], edits: [{
          id: "ed-1",
          start: 1,
          end: 5,
          action: "delete",
          source: "test",
          status: "confirmed",
          priority: 100,
          target_type: "segment",
          target_id: "seg-1",
        }] }],
      }
      const returnedProj = mockProject({ project: { name: "after-update", created_at: "", updated_at: "" } })
      mockCall.mockResolvedValue({ success: true, data: returnedProj })

      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())

      const methods = mockCall.mock.calls.map(c => c[0])
      expect(methods).toContain("update_edit_decision")
      expect(methods).not.toContain("get_project")
      expect(methods.filter(m => m === "update_edit_decision").length).toBe(1)
      expect(onProjectUpdate).toHaveBeenCalledWith(returnedProj)
    })

    it("uses mark_segments return value and skips get_project", async () => {
      const returnedProj = mockProject({ project: { name: "after-mark", created_at: "", updated_at: "" } })
      mockCall.mockResolvedValue({ success: true, data: returnedProj })

      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())

      const methods = mockCall.mock.calls.map(c => c[0])
      expect(methods).toContain("mark_segments")
      expect(methods).not.toContain("get_project")
      expect(methods.filter(m => m === "mark_segments").length).toBe(1)
      expect(onProjectUpdate).toHaveBeenCalledWith(returnedProj)
    })

    it("falls back to get_project when write call returns no data", async () => {
      // Simulate an older backend or protocol mismatch: write succeeds but
      // returns no Project payload. The fallback must refresh from source.
      mockCall.mockImplementation(async (method: string) => {
        if (method === "get_project") {
          return { success: true, data: mockProject({ project: { name: "refreshed", created_at: "", updated_at: "" } }) }
        }
        return { success: true }
      })

      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())

      const methods = mockCall.mock.calls.map(c => c[0])
      expect(methods).toContain("mark_segments")
      expect(methods).toContain("get_project")
    })

    it("falls back to get_project when write call fails", async () => {
      mockCall.mockImplementation(async (method: string) => {
        if (method === "get_project") {
          return { success: true, data: mockProject() }
        }
        return { success: false, error: "write failed" }
      })

      const { toggleEditStatus } = useSegmentEdit(project, onProjectUpdate)
      await toggleEditStatus(mockSegment())

      const methods = mockCall.mock.calls.map(c => c[0])
      expect(methods).toContain("get_project")
    })
  })

  describe("resolveState", () => {
    it("returns SegmentState from resolveSegmentState", () => {
      const { resolveState } = useSegmentEdit(project, onProjectUpdate)
      const state = resolveState(mockSegment())
      expect(state.displayStatus).toBe("none")
      expect(state.styleClass).toBe("normal")
      expect(state.activeEdit).toBeUndefined()
    })

    it("reflects active edit when present", () => {
      project.value = {
        ...mockProject(),
        timelines: [{ ...mockProject().timelines[0], edits: [{
          id: "ed-active",
          start: 1,
          end: 5,
          action: "delete",
          source: "user",
          status: "confirmed",
          priority: 200,
          target_type: "segment",
          target_id: "seg-1",
        }] }],
      }
      const { resolveState } = useSegmentEdit(project, onProjectUpdate)
      const state = resolveState(mockSegment())
      expect(state.displayStatus).toBe("confirmed")
      expect(state.styleClass).toBe("masked")
      expect(state.activeEdit).toBeDefined()
    })
  })

  describe("status queries", () => {
    it("getEffectiveStatus returns normal when no edits", () => {
      const { getEffectiveStatus } = useSegmentEdit(project, onProjectUpdate)
      expect(getEffectiveStatus(mockSegment())).toBe("normal")
    })

    it("getEditStatus returns null when no edits", () => {
      const { getEditStatus } = useSegmentEdit(project, onProjectUpdate)
      expect(getEditStatus(mockSegment())).toBeNull()
    })
  })
})

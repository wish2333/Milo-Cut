/**
 * v3.0.2 M1-1 (S1/R1.3): useTrackEdit suite -- the test file the v3.0.1
 * plan checked off but never landed. Anchors the four contract groups:
 * optimistic update, debounce merge (same segment+field), failure
 * rollback, and the undo capture layers (bound -> ["tracks","bindings"],
 * unbound -> ["tracks"]).
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ref, type Ref } from "vue"
import type { Project, TrackBinding, SubtitleTrack } from "@/types/project"
import { useTrackEdit } from "./useTrackEdit"
import { mockProject, mockSegment } from "@/test/helpers/mockProject"

vi.mock("@/bridge", () => ({
  call: vi.fn(),
}))

import { call } from "@/bridge"
const mockCall = vi.mocked(call)

function mockTrack(overrides: Partial<SubtitleTrack> = {}): SubtitleTrack {
  return {
    id: "trk-1",
    role: "extension",
    name: "en.srt",
    language: "en",
    segments: [
      mockSegment({ id: "trk-1_seg-1", start: 1.0, end: 5.0, text: "hello" }),
      mockSegment({ id: "trk-1_seg-2", start: 6.0, end: 9.0, text: "second" }),
    ],
    ...overrides,
  }
}

function mockBinding(overrides: Partial<TrackBinding> = {}): TrackBinding {
  return {
    id: "bnd-1",
    track_id: "trk-1",
    main_segment_id: "seg-1",
    extension_segment_id: "trk-1_seg-1",
    start_offset: 0,
    end_offset: 0,
    ...overrides,
  }
}

function projectWithTracks(
  track: SubtitleTrack = mockTrack(),
  bindings: TrackBinding[] = [],
): Ref<Project> {
  return ref(
    mockProject({
      timelines: [
        {
          ...mockProject().timelines[0],
          transcript: {
            ...mockProject().timelines[0].transcript,
            tracks: [track],
            bindings,
          },
        },
      ],
    }),
  ) as Ref<Project>
}

/** The optimistic patch the composable applied, read from onProjectUpdate. */
function appliedProject(fn: ReturnType<typeof vi.fn>): Project {
  const last = [...fn.mock.calls].reverse()[0] as [Project]
  return last[0]
}

function trackSegmentOf(p: Project, segmentId: string) {
  const tl = p.timelines.find(t => t.id === p.active_timeline_id)!
  return tl.transcript.tracks!.find(t => t.id === "trk-1")!.segments.find(s => s.id === segmentId)!
}

describe("useTrackEdit", () => {
  let project: Ref<Project>
  let onProjectUpdate: ReturnType<typeof vi.fn>
  let onBeforeProjectUpdate: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    // Stale debounce timers from earlier tests must not fire inside later
    // tests' advanceTimersByTime windows (timer-hygiene guard).
    vi.clearAllTimers()
    project = projectWithTracks()
    onProjectUpdate = vi.fn((p: Project) => {
      project.value = p
    })
    onBeforeProjectUpdate = vi.fn()
  })

  describe("optimistic update", () => {
    it("applies the time change locally before any backend call", () => {
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)

      expect(mockCall).not.toHaveBeenCalled()
      expect(trackSegmentOf(appliedProject(onProjectUpdate), "trk-1_seg-1").start).toBe(2.0)
    })

    it("ignores unknown track segments", () => {
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "missing", "start", 2.0)
      expect(onProjectUpdate).not.toHaveBeenCalled()
    })

    it("does not touch sibling segments or the main track", () => {
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      const before = project.value
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "end", 5.5)
      const after = appliedProject(onProjectUpdate)
      const tlBefore = before.timelines.find(t => t.id === before.active_timeline_id)!
      const tlAfter = after.timelines.find(t => t.id === after.active_timeline_id)!
      expect(trackSegmentOf(after, "trk-1_seg-2")).toEqual(
        tlBefore.transcript.tracks![0].segments[1],
      )
      // Main-track segments array keeps reference identity (patch-ready).
      expect(tlAfter.transcript.segments).toBe(tlBefore.transcript.segments)
    })
  })

  describe("debounce merge", () => {
    it("collapses rapid updates to the same segment+field into one backend call", async () => {
      mockCall.mockResolvedValue({ success: true, data: project.value })
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.5)
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 3.0)

      vi.advanceTimersByTime(300)
      await Promise.resolve()
      expect(mockCall).toHaveBeenCalledTimes(1)
      expect(mockCall).toHaveBeenCalledWith("update_track_segment", "trk-1", "trk-1_seg-1", {
        start: 3.0,
      })
    })

    it("keeps distinct fields/segments as separate pending entries", async () => {
      mockCall.mockResolvedValue({ success: true, data: project.value })
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "end", 5.5)
      updateTrackSegmentTime("trk-1", "trk-1_seg-2", "start", 6.5)

      vi.advanceTimersByTime(300)
      await Promise.resolve()
      expect(mockCall).toHaveBeenCalledTimes(3)
    })
  })

  describe("failure rollback", () => {
    it("restores the pre-edit project when the backend call fails", async () => {
      mockCall.mockResolvedValue({ success: false, error: "boom" })
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      const before = project.value
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)

      vi.advanceTimersByTime(300)
      await Promise.resolve()
      // Last onProjectUpdate call carries the rollback snapshot.
      const restored = appliedProject(onProjectUpdate)
      expect(trackSegmentOf(restored, "trk-1_seg-1").start).toBe(
        trackSegmentOf(before, "trk-1_seg-1").start,
      )
    })

    it("adopts the backend project on success (no rollback)", async () => {
      const serverProject = projectWithTracks().value
      mockCall.mockResolvedValue({ success: true, data: serverProject })
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)

      vi.advanceTimersByTime(300)
      await Promise.resolve()
      expect(appliedProject(onProjectUpdate)).toBe(serverProject)
    })
  })

  describe("undo capture layers (M5-1 mapping)", () => {
    it("captures [tracks, bindings] when the segment is bound", () => {
      project = projectWithTracks(mockTrack(), [mockBinding()])
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      expect(onBeforeProjectUpdate).toHaveBeenCalledTimes(1)
      const [, layers, label] = onBeforeProjectUpdate.mock.calls[0]
      expect(layers).toEqual(["tracks", "bindings"])
      expect(label).toBe("调整副轨时间")
    })

    it("captures [tracks] only when the segment is unbound", () => {
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      const [, layers] = onBeforeProjectUpdate.mock.calls[0]
      expect(layers).toEqual(["tracks"])
    })

    it("binds only when THIS segment is the extension side (main-side unaffected)", () => {
      // Binding points at a different extension segment: trk-1_seg-2, so
      // trimming trk-1_seg-1 stays single-layer.
      project = projectWithTracks(mockTrack(), [
        mockBinding({ extension_segment_id: "trk-1_seg-2" }),
      ])
      const { updateTrackSegmentTime } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      const [, layers] = onBeforeProjectUpdate.mock.calls[0]
      expect(layers).toEqual(["tracks"])
    })
  })

  describe("flushPendingTrackUpdates", () => {
    it("submits pending entries immediately without waiting for the debounce", async () => {
      mockCall.mockResolvedValue({ success: true, data: project.value })
      const { updateTrackSegmentTime, flushPendingTrackUpdates } = useTrackEdit(
        project,
        onProjectUpdate,
        onBeforeProjectUpdate,
      )
      updateTrackSegmentTime("trk-1", "trk-1_seg-1", "start", 2.0)
      expect(mockCall).not.toHaveBeenCalled()

      await flushPendingTrackUpdates()
      expect(mockCall).toHaveBeenCalledTimes(1)

      // The canceled timer must not fire a duplicate submission.
      vi.advanceTimersByTime(300)
      await Promise.resolve()
      expect(mockCall).toHaveBeenCalledTimes(1)
    })
  })
})

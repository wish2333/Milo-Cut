/**
 * v3.0.1 M5-2: extension-track segment editing composable.
 *
 * Mirrors useSegmentEdit's optimistic+debounced pattern for track
 * segments: optimistic local update -> 300ms debounce -> backend
 * ``update_track_segment`` -> failure rollback. Kept separate from
 * useSegmentEdit on purpose (3.0.0 C2 lesson: composables must not
 * accrete).
 *
 * Undo capture (M5-1 mapping): extension trims always capture the tracks
 * layer; bindings join when the segment is bound (the backend rebuilds
 * their offsets).
 */
import { computed, type ComputedRef, type Ref } from "vue"
import type { Project, ProjectResponse, Segment } from "@/types/project"
import { call } from "@/bridge"
import type { UndoLayer } from "@/utils/undoRecords"

const DEBOUNCE_MS = 300

export interface UseTrackEditReturn {
  updateTrackSegmentTime: (
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
  ) => void
  flushPendingTrackUpdates: () => Promise<void>
  pendingTrackCount: ComputedRef<number>
}

interface PendingEntry {
  timer: ReturnType<typeof setTimeout>
  callback: () => void
}

function activeTimelineOf(p: Project) {
  return p.timelines.find(t => t.id === p.active_timeline_id)
}

function optimisticReplace(
  prev: Project,
  trackId: string,
  segmentId: string,
  patch: Partial<Segment>,
): Project {
  const newTracks = (activeTimelineOf(prev)?.transcript?.tracks ?? []).map(tr => {
    if (tr.id !== trackId) return tr
    return { ...tr, segments: tr.segments.map(s => (s.id === segmentId ? { ...s, ...patch } : s)) }
  })
  return {
    ...prev,
    timelines: prev.timelines.map(tl => {
      if (tl.id !== prev.active_timeline_id) return tl
      return {
        ...tl,
        transcript: { ...tl.transcript, tracks: newTracks },
      }
    }),
  }
}

export function useTrackEdit(
  project: Ref<Project>,
  onProjectUpdate: (p: ProjectResponse) => void,
  onBeforeProjectUpdate?: (p: Project, layers?: UndoLayer[], label?: string) => void,
): UseTrackEditReturn {
  const pendingMap = new Map<string, PendingEntry>()
  const pendingTrackCount = computed(() => pendingMap.size)

  const trimCaptureAt = new Map<string, number>()
  const TRIM_CAPTURE_COALESCE_MS = 1200

  function updateTrackSegmentTime(
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
  ) {
    const prev = project.value
    const track = activeTimelineOf(prev)?.transcript?.tracks?.find(t => t.id === trackId)
    const seg = track?.segments.find(s => s.id === segmentId)
    if (!seg) return

    // M5-1 mapping (capture at submit time): bindings join when the
    // segment is bound -- the backend rebuilds their offsets.
    const bound = (activeTimelineOf(prev)?.transcript?.bindings ?? []).some(
      b => b.extension_segment_id === segmentId,
    )
    const layers: UndoLayer[] = bound ? ["tracks", "bindings"] : ["tracks"]
    // v3.0.2 smoke fix: coalesce capture per segment+field (ONE undo point
    // per drag; pauses > 1.2s start a new one).
    const capKey = `${trackId}:${segmentId}:${field}`
    const now = Date.now()
    if (now - (trimCaptureAt.get(capKey) ?? -Infinity) >= TRIM_CAPTURE_COALESCE_MS) {
      trimCaptureAt.set(capKey, now)
      onBeforeProjectUpdate?.(prev, layers, "调整副轨时间")
    }

    onProjectUpdate(optimisticReplace(prev, trackId, segmentId, { [field]: value }))

    const key = `${trackId}:${segmentId}:${field}`
    const existing = pendingMap.get(key)
    if (existing) clearTimeout(existing.timer)

    const callback = async () => {
      const res = await call<Project>(
        "update_track_segment",
        trackId,
        segmentId,
        { [field]: value },
      )
      if (res.success && res.data) {
        onProjectUpdate(res.data)
      } else {
        onProjectUpdate(prev)
      }
    }

    const timer = setTimeout(() => {
      pendingMap.delete(key)
      callback()
    }, DEBOUNCE_MS)
    pendingMap.set(key, { timer, callback })
  }

  async function flushPendingTrackUpdates(): Promise<void> {
    const entries = [...pendingMap.values()]
    pendingMap.clear()
    for (const entry of entries) {
      clearTimeout(entry.timer)
      entry.callback()
    }
  }

  return {
    updateTrackSegmentTime,
    flushPendingTrackUpdates,
    pendingTrackCount,
  }
}

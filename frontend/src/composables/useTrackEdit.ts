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
 *
 * v3.0.3 M1-3 (list-side entries): ``editTrackSegmentText`` /
 * ``editTrackSegmentTime`` reuse the SAME kernel -- same debounce keys
 * (``trackId:segmentId:field``) so list and waveform edits of one field
 * merge naturally (later writer wins, rollback per the LAST snapshot,
 * SPEC M1-3 裁决). The waveform trim path keeps its silent rollback; the
 * list entries surface backend rejections through the optional onError
 * callback (toast 原文).
 */
import { computed, type ComputedRef, type Ref } from "vue"
import type { Project, ProjectResponse, Segment } from "@/types/project"
import { call } from "@/bridge"
import { MIN_SEGMENT_DURATION } from "@/utils/trackConstraints"
import type { UndoLayer } from "@/utils/undoRecords"

const DEBOUNCE_MS = 300

export interface UseTrackEditReturn {
  updateTrackSegmentTime: (
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
    onError?: (error: string) => void,
  ) => void
  /** v3.0.3 M1-3: subtitle-list text entry (debounce + rollback + toast). */
  editTrackSegmentText: (
    trackId: string,
    segmentId: string,
    text: string,
    onError?: (error: string) => void,
  ) => void
  /** v3.0.3 M1-3: subtitle-list time entry (local pre-validation first). */
  editTrackSegmentTime: (
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
    onError?: (error: string) => void,
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

  /** One undo point per key; pauses > 1.2s start a new one (3.0.2 ruling). */
  function captureOnce(key: string, prev: Project, layers: UndoLayer[], label: string): void {
    const now = Date.now()
    if (now - (trimCaptureAt.get(key) ?? -Infinity) >= TRIM_CAPTURE_COALESCE_MS) {
      trimCaptureAt.set(key, now)
      onBeforeProjectUpdate?.(prev, layers, label)
    }
  }

  /** Debounced backend submission; replaces any pending entry under `key`. */
  function submitAfterDebounce(
    key: string,
    callback: () => Promise<void>,
  ): void {
    const existing = pendingMap.get(key)
    if (existing) clearTimeout(existing.timer)
    const timer = setTimeout(() => {
      pendingMap.delete(key)
      callback()
    }, DEBOUNCE_MS)
    pendingMap.set(key, { timer, callback })
  }

  function updateTrackSegmentTime(
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
    onError?: (error: string) => void,
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
    captureOnce(capKey, prev, layers, "调整副轨时间")

    onProjectUpdate(optimisticReplace(prev, trackId, segmentId, { [field]: value }))

    submitAfterDebounce(capKey, async () => {
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
        if (onError) onError(res.error ?? "副轨时间更新失败")
      }
    })
  }

  function editTrackSegmentText(
    trackId: string,
    segmentId: string,
    text: string,
    onError?: (error: string) => void,
  ) {
    const prev = project.value
    const track = activeTimelineOf(prev)?.transcript?.tracks?.find(t => t.id === trackId)
    const seg = track?.segments.find(s => s.id === segmentId)
    if (!seg) return

    // M1-4 predicate row 1: text is ALWAYS ["tracks"] (text never triggers
    // a binding rebuild downstream).
    const key = `${trackId}:${segmentId}:text`
    captureOnce(key, prev, ["tracks"], "编辑副轨文本")

    onProjectUpdate(optimisticReplace(prev, trackId, segmentId, { text }))

    submitAfterDebounce(key, async () => {
      const res = await call<Project>(
        "update_track_segment",
        trackId,
        segmentId,
        { text },
      )
      if (res.success && res.data) {
        onProjectUpdate(res.data)
      } else {
        onProjectUpdate(prev)
        if (onError) onError(res.error ?? "副轨文本更新失败")
      }
    })
  }

  function editTrackSegmentTime(
    trackId: string,
    segmentId: string,
    field: "start" | "end",
    value: number,
    onError?: (error: string) => void,
  ) {
    const prev = project.value
    const track = activeTimelineOf(prev)?.transcript?.tracks?.find(t => t.id === trackId)
    const seg = track?.segments.find(s => s.id === segmentId)
    if (!seg) return

    // M1-3 local pre-validation: [0, media duration] bound + min duration.
    // The backend stays authoritative (clamp + same-track overlap reject);
    // a rejection after submission rolls back and surfaces via onError.
    if (!Number.isFinite(value)) {
      onError?.("时间格式无效")
      return
    }
    const mediaDuration = prev.media?.duration ?? 0
    const hasDuration = Number.isFinite(mediaDuration) && mediaDuration > 0
    const clamped = hasDuration ? Math.min(Math.max(0, value), mediaDuration) : Math.max(0, value)
    const other = field === "start" ? seg.end : seg.start
    if (Math.abs(clamped - other) < MIN_SEGMENT_DURATION - 1e-6) {
      onError?.(`字幕最短时长 ${MIN_SEGMENT_DURATION}s`)
      return
    }
    updateTrackSegmentTime(trackId, segmentId, field, clamped, onError)
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
    editTrackSegmentText,
    editTrackSegmentTime,
    flushPendingTrackUpdates,
    pendingTrackCount,
  }
}

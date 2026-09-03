/**
 * v3.0.3 M1-1 (P1-1): subtitle-list track selector view state.
 *
 * The selector is PURE SESSION VIEW STATE (SPEC M0-1.4): it never produces
 * a patch, never enters undo, never persists. `null` means the main track
 * -- the v3.0.2 default under which the whole list path must stay
 * byte-identical (M0-1.3), so every helper below resolves null-safe.
 *
 * Kept as a composable (not inline in WorkspacePage) so the round-trip /
 * delete-fallback behavior is vitest-exercisable at the reactive level;
 * WorkspacePage only wires it (same pattern as useLaneLayout in 3.0.2).
 */
import { computed, ref, watch, type ComputedRef, type Ref } from "vue"
import type { Segment, SubtitleTrack } from "@/types/project"

/** Selector entry shown in the Timeline header (name + segment count). */
export interface ListTrackOption {
  id: string
  name: string
  segmentCount: number
}

export function buildListTrackOptions(tracks: SubtitleTrack[]): ListTrackOption[] {
  return tracks.map(t => ({
    id: t.id,
    name: t.name || t.id,
    segmentCount: t.segments.length,
  }))
}

/**
 * THE single list data source (M1-1): main track -> mergedSegments,
 * extension track -> that track's segments. No second render path is
 * created downstream; rows are polymorphic over this one array.
 */
export function resolveListSegments(
  activeTrackId: string | null,
  tracks: SubtitleTrack[],
  mergedSegments: Segment[],
): Segment[] {
  if (activeTrackId === null) return mergedSegments
  return tracks.find(t => t.id === activeTrackId)?.segments ?? []
}

/**
 * Delete/switch fallback (M1-1 boundary): a stale track id (its track was
 * deleted, or the project/timeline switched underneath) snaps back to the
 * main track so the list never holds a dangling reference.
 */
export function resolveListTrackIdAfterTracksChange(
  current: string | null,
  tracks: SubtitleTrack[],
): string | null {
  if (current === null) return null
  return tracks.some(t => t.id === current) ? current : null
}

export interface UseListTrackSelectorReturn {
  /** null = main track (v3.0.2 default). Session view state only. */
  activeListTrackId: Ref<string | null>
  selectTrack: (trackId: string | null) => void
  options: ComputedRef<ListTrackOption[]>
  listSegments: ComputedRef<Segment[]>
}

export function useListTrackSelector(
  tracks: Ref<SubtitleTrack[]>,
  mergedSegments: Ref<Segment[]>,
): UseListTrackSelectorReturn {
  const activeListTrackId = ref<string | null>(null)

  function selectTrack(trackId: string | null) {
    activeListTrackId.value = trackId
  }

  const options = computed(() => buildListTrackOptions(tracks.value))
  const listSegments = computed(() =>
    resolveListSegments(activeListTrackId.value, tracks.value, mergedSegments.value),
  )

  // Delete-track fallback watch: any tracks change (delete_track, timeline
  // switch, project switch) that orphans the current selection snaps back
  // to the main track (M1-1: no dangling reference). Multi-source watch on
  // purpose: a single getter returning the resolved value would skip the
  // callback whenever consecutive flushes resolve equal (null -> null),
  // swallowing a needed correction; watching both sources fires on every
  // change and the guard makes no-op selections free.
  watch([activeListTrackId, tracks], ([current, list]) => {
    const resolved = resolveListTrackIdAfterTracksChange(current, list)
    if (resolved !== current) activeListTrackId.value = resolved
  })

  return {
    activeListTrackId,
    selectTrack,
    options,
    listSegments,
  }
}

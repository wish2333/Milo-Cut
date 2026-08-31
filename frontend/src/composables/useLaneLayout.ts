/**
 * v3.0.1 M4-1: lane geometry for the stacked timeline (SPEC M4-1).
 *
 * Pure layout math (computeLaneLayout) + a thin composable that owns the
 * persisted layout state (localStorage, GLOBAL user preference -- NOT per
 * project) and the container height (ResizeObserver). Layout state is a
 * pure-frontend layer: it never enters undo, patches, or settings.json
 * (PRD R8.2).
 */
import { computed, ref, watch, type Ref } from "vue"

export type LaneHeightPreset = "sm" | "md" | "lg"

export const LANE_PRESET_HEIGHTS: Record<LaneHeightPreset, number> = {
  sm: 32,
  md: 48,
  lg: 72,
}
/** A collapsed lane shrinks to its title bar. */
export const LANE_COLLAPSED_HEIGHT = 24
/** Absolute floor for lane compression. */
export const LANE_MIN_HEIGHT = 24
/** Main track area never voluntarily shrinks below this. */
export const MAIN_TRACK_MIN_HEIGHT = 96

export interface LaneLayoutState {
  collapsed: Record<string, boolean>
  hidden: Record<string, boolean>
  preset: Record<string, LaneHeightPreset>
}

export interface LaneLayoutItem {
  trackId: string
  top: number
  height: number
  collapsed: boolean
  hidden: boolean
}

export interface LaneLayout {
  lanes: LaneLayoutItem[]
  mainTrackHeight: number
  totalLanesHeight: number
  /** True when even fully-compressed lanes cannot fit (UI shows a hint). */
  overflowing: boolean
}

export const LAYOUT_STORAGE_KEY = "milocut:timeline-layout:v1"

export function defaultLaneLayoutState(): LaneLayoutState {
  return { collapsed: {}, hidden: {}, preset: {} }
}

export function loadLaneLayoutState(storage: Storage | null = typeof localStorage !== "undefined" ? localStorage : null): LaneLayoutState {
  if (!storage) return defaultLaneLayoutState()
  try {
    const raw = storage.getItem(LAYOUT_STORAGE_KEY)
    if (!raw) return defaultLaneLayoutState()
    const parsed = JSON.parse(raw) as Partial<LaneLayoutState>
    return {
      collapsed: parsed.collapsed ?? {},
      hidden: parsed.hidden ?? {},
      preset: parsed.preset ?? {},
    }
  } catch {
    // Corrupt JSON -> defaults (M4-1 acceptance).
    return defaultLaneLayoutState()
  }
}

export function saveLaneLayoutState(
  state: LaneLayoutState,
  storage: Storage | null = typeof localStorage !== "undefined" ? localStorage : null,
): void {
  if (!storage) return
  try {
    storage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Quota / privacy mode: layout persistence is best-effort.
  }
}

const DOWNGRADE: Record<number, number> = {
  [LANE_PRESET_HEIGHTS.lg]: LANE_PRESET_HEIGHTS.md,
  [LANE_PRESET_HEIGHTS.md]: LANE_PRESET_HEIGHTS.sm,
  [LANE_PRESET_HEIGHTS.sm]: LANE_MIN_HEIGHT,
}

/**
 * Stack math: main track gets whatever the visible lanes do not take,
 * with a voluntary floor of MAIN_TRACK_MIN_HEIGHT. Below the floor, lanes
 * compress in lane order (lg -> md -> sm -> 24) until it fits; if even
 * all-24 lanes overflow, `overflowing` flags a UI hint (PRD R3.4).
 */
export function computeLaneLayout(
  containerHeight: number,
  trackIds: readonly string[],
  state: LaneLayoutState,
): LaneLayout {
  const isHidden = (id: string) => state.hidden[id] === true
  const isCollapsed = (id: string) => state.collapsed[id] === true
  const rawHeight = (id: string) =>
    isCollapsed(id) ? LANE_COLLAPSED_HEIGHT : LANE_PRESET_HEIGHTS[state.preset[id] ?? "md"]

  const visibleIds = trackIds.filter(id => !isHidden(id))
  const heights = new Map<string, number>(visibleIds.map(id => [id, rawHeight(id)]))

  const totalOf = () => visibleIds.reduce((sum, id) => sum + (heights.get(id) ?? 0), 0)

  // Compress in lane order while the main track floor is violated.
  if (containerHeight - totalOf() < MAIN_TRACK_MIN_HEIGHT) {
    for (const id of visibleIds) {
      if (containerHeight - totalOf() >= MAIN_TRACK_MIN_HEIGHT) break
      if (isCollapsed(id)) continue
      const downgraded = DOWNGRADE[heights.get(id) ?? 0]
      if (downgraded !== undefined) heights.set(id, downgraded)
    }
    // Second pass: everything (non-collapsed) to the absolute floor.
    if (containerHeight - totalOf() < MAIN_TRACK_MIN_HEIGHT) {
      for (const id of visibleIds) {
        if (containerHeight - totalOf() >= MAIN_TRACK_MIN_HEIGHT) break
        if (!isCollapsed(id)) heights.set(id, LANE_MIN_HEIGHT)
      }
    }
  }

  const totalLanesHeight = totalOf()
  const mainTrackHeight = Math.max(0, containerHeight - totalLanesHeight)
  const overflowing =
    visibleIds.length > 0 && containerHeight - totalLanesHeight < MAIN_TRACK_MIN_HEIGHT

  let top = 0
  const lanes: LaneLayoutItem[] = trackIds.map(id => {
    const hidden = isHidden(id)
    const collapsed = isCollapsed(id)
    const height = hidden ? 0 : (heights.get(id) ?? LANE_COLLAPSED_HEIGHT)
    const item: LaneLayoutItem = { trackId: id, top, height, collapsed, hidden }
    if (!hidden) top += height
    return item
  })

  return { lanes, mainTrackHeight, totalLanesHeight, overflowing }
}

/**
 * Reactive wrapper for WaveformEditor. Call `setContainerEl` from a template
 * ref to let a ResizeObserver drive `containerHeight`.
 */
export function useLaneLayout(trackIds: () => string[]) {
  const state = ref<LaneLayoutState>(loadLaneLayoutState())
  const containerHeight = ref(0)

  const layout = computed(() =>
    computeLaneLayout(containerHeight.value, trackIds(), state.value),
  )

  watch(
    state,
    s => saveLaneLayoutState(s),
    { deep: true },
  )

  let observer: ResizeObserver | null = null
  let observedEl: HTMLElement | null = null

  function setContainerEl(el: unknown) {
    const htmlEl = el instanceof HTMLElement ? el : null
    if (htmlEl === observedEl) return
    observer?.disconnect()
    observedEl = htmlEl
    if (!htmlEl) {
      containerHeight.value = 0
      return
    }
    containerHeight.value = htmlEl.getBoundingClientRect().height
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(entries => {
        for (const entry of entries) {
          containerHeight.value = entry.contentRect.height
        }
      })
      observer.observe(htmlEl)
    }
  }

  function cleanup() {
    observer?.disconnect()
    observer = null
    observedEl = null
  }

  function toggleCollapse(trackId: string) {
    state.value = {
      ...state.value,
      collapsed: { ...state.value.collapsed, [trackId]: !state.value.collapsed[trackId] },
    }
  }

  function setHidden(trackId: string, hidden: boolean) {
    state.value = {
      ...state.value,
      hidden: { ...state.value.hidden, [trackId]: hidden },
    }
  }

  function setPreset(trackId: string, preset: LaneHeightPreset) {
    state.value = {
      ...state.value,
      preset: { ...state.value.preset, [trackId]: preset },
    }
  }

  return {
    state: state as Ref<LaneLayoutState>,
    containerHeight,
    layout,
    setContainerEl,
    cleanup,
    toggleCollapse,
    setHidden,
    setPreset,
  }
}

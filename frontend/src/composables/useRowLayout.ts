/**
 * v3.0.2 M2 (P0): row geometry kernel for the multi-row timeline.
 *
 * Module discipline (SPEC M2): the geometry functions below are
 * module-level PURE functions -- seconds units, no Vue reactivity, no
 * bridge/store imports -- so vitest can exercise them standalone. The
 * composable shell at the bottom only binds reactivity + localStorage.
 *
 * Design anchors (PRD §0.3):
 * - P1: rows are DERIVED geometry, never state -- everything is computed
 *   from (duration, secondsPerRow).
 * - P4: bounded/unbounded dual mapping -- timeFromPointerInRow is the
 *   single source for both click/creation clamping (bounded) and
 *   scrub/trim math (unbounded; callers clamp to [0, duration]).
 * - P6: zero backend schema change -- row preferences live in
 *   localStorage only, never in project.json, patches, or undo.
 */
import { computed, ref, watch, type ComputedRef, type Ref } from "vue"

// -- Constants (single source of truth, M2-1/R4.6) ------------------------

export const SECONDS_PER_ROW_PRESETS = [5, 10, 20, 30] as const
export const ROW_HEIGHT_PRESETS = [64, 80, 96, 120, 144, 168] as const
export const DEFAULT_SECONDS_PER_ROW = 10
export const DEFAULT_ROW_HEIGHT = 120
/** Vertical gap between consecutive rows (px). */
export const ROW_GAP = 10
/** Extra rows rendered above/below the viewport (virtualization buffer). */
export const ROW_BUFFER = 2
/** Manual scrolling pauses playhead-follow for this long (ms, M6-1). */
export const MANUAL_FOLLOW_COOLDOWN_MS = 3000
/** Wheel gesture merge window for spr/rowHeight cycling (ms, M5-1). */
export const WHEEL_DEBOUNCE_MS = 160
/** Scrub seek throttle while dragging the playhead (ms, M5-3). */
export const SCRUB_SEEK_INTERVAL_MS = 32
/** Playhead-follow bias: current line sits ~1/3 from the top (M6-1). */
export const FOLLOW_BIAS = 0.35
/** Jump/reveal bias: target line sits under 1/2 from the top (M6-1). */
export const REVEAL_BIAS = 0.45

/** localStorage key (M0-1.4) -- sibling of `milocut:timeline-layout:v1`. */
export const ROW_LAYOUT_STORAGE_KEY = "milocut:timeline-rows:v1"

export interface RowSpan {
  start: number
  end: number
}

export interface RowLayoutState {
  mode: "multi" | "basic"
  secondsPerRow: number
  rowHeight: number
}

// -- Pure geometry (seconds in, seconds/px out; no reactivity) ------------

/** Rows needed to cover `duration`; empty media still shows one row. */
export function computeRowCount(duration: number, secondsPerRow: number): number {
  if (!Number.isFinite(secondsPerRow) || secondsPerRow <= 0) {
    throw new Error(`useRowLayout: secondsPerRow must be > 0, got ${secondsPerRow}`)
  }
  if (!Number.isFinite(duration) || duration <= 0) return 1
  return Math.max(1, Math.ceil(duration / secondsPerRow))
}

/** Time window of row `index`; the last row is clamped to `duration`. */
export function rowSpanAt(index: number, duration: number, secondsPerRow: number): RowSpan {
  const rowCount = computeRowCount(duration, secondsPerRow)
  if (!Number.isInteger(index) || index < 0 || index >= rowCount) {
    throw new Error(`useRowLayout: row index ${index} out of range (rowCount=${rowCount})`)
  }
  return {
    start: index * secondsPerRow,
    end: Math.min(duration, (index + 1) * secondsPerRow),
  }
}

/** Last-row width as a percentage of a full row (100 when it fills). */
export function lastRowWidthPercent(duration: number, secondsPerRow: number): number {
  const remainder = duration % secondsPerRow
  return ((remainder || secondsPerRow) / secondsPerRow) * 100
}

/** Vertical distance between consecutive row tops (px). */
export function strideOf(rowHeight: number): number {
  return rowHeight + ROW_GAP
}

/**
 * Visible row window for virtualization: rows intersecting the viewport
 * extended by ROW_BUFFER rows on both sides.
 */
export function visibleRowWindow(
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  rowCount: number,
): { first: number; last: number } {
  if (rowCount <= 0) return { first: 0, last: 0 }
  if (!(viewportHeight > 0)) {
    const last = Math.min(ROW_BUFFER, rowCount - 1)
    return { first: 0, last }
  }
  const stride = strideOf(rowHeight)
  const first = Math.max(0, Math.min(Math.floor(scrollTop / stride) - ROW_BUFFER, rowCount - 1))
  const last = Math.max(
    0,
    Math.min(Math.ceil((scrollTop + viewportHeight) / stride) + ROW_BUFFER, rowCount - 1),
  )
  return { first: Math.min(first, last), last }
}

/** Time at the top row of the viewport (row-start quantized). */
export function scrollTopToTime(scrollTop: number, rowHeight: number, secondsPerRow: number): number {
  const stride = strideOf(rowHeight)
  return Math.floor(scrollTop / stride) * secondsPerRow
}

/**
 * Scroll position that puts `time`'s row at the viewport top, QUANTIZED
 * to the row boundary (browse-position restore). Deliberately not the
 * inverse of scrollTopToTime: both quantize down (M2-2 裁决, test-locked).
 */
export function timeToScrollTop(time: number, rowHeight: number, secondsPerRow: number): number {
  const stride = strideOf(rowHeight)
  return Math.floor(Math.max(0, time) / secondsPerRow) * stride
}

/** Row index holding `time` (negative times clamp to row 0). */
export function rowIndexAtTime(time: number, secondsPerRow: number): number {
  if (!Number.isFinite(secondsPerRow) || secondsPerRow <= 0) {
    throw new Error(`useRowLayout: secondsPerRow must be > 0, got ${secondsPerRow}`)
  }
  return Math.floor(Math.max(0, time) / secondsPerRow)
}

/** Comfort-zone inset: 20% of the viewport, clamped to [48, 120] px. */
export function comfortInset(viewportHeight: number): number {
  return Math.min(120, Math.max(48, viewportHeight * 0.2))
}

/**
 * True when row `rowIndex` sits fully inside the comfort zone of the
 * viewport (top edge below the top inset AND bottom edge above the
 * bottom inset). Playhead-follow is a no-op for comfortable rows.
 */
export function isRowInComfortZone(
  rowIndex: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
): boolean {
  const inset = comfortInset(viewportHeight)
  const rowTop = rowIndex * strideOf(rowHeight) - scrollTop
  return rowTop >= inset && rowTop + rowHeight <= viewportHeight - inset
}

/**
 * Scroll position placing row `rowIndex` at `bias` of the viewport
 * height (FOLLOW_BIAS for playback follow, REVEAL_BIAS for jumps).
 */
export function followScrollTop(
  rowIndex: number,
  viewportHeight: number,
  rowHeight: number,
  maxScrollTop: number,
  bias: number = FOLLOW_BIAS,
): number {
  const target = rowIndex * strideOf(rowHeight) - viewportHeight * bias
  return Math.min(Math.max(target, 0), Math.max(0, maxScrollTop))
}

/**
 * M5-1: cycle through a preset list by `steps` net wheel notches
 * (positive = toward larger values), clamped at both ends. Pure so the
 * editor's debounced wheel bursts and the vitest table share one ladder.
 */
export function cyclePreset<T>(presets: readonly T[], current: T, steps: number): T {
  const index = presets.indexOf(current)
  const base = index === -1 ? 0 : index
  const next = Math.min(presets.length - 1, Math.max(0, base + Math.trunc(steps)))
  return presets[next]
}

export interface RowPointerGeometry {
  left: number
  width: number
}

/**
 * Time under a pointer inside a row. `bounded: true` clamps the ratio to
 * [0, 1] (clicks/creation); `bounded: false` lets the ratio run free for
 * scrub/trim -- the caller then clamps to [0, duration] (P4 dual mapping).
 */
export function timeFromPointerInRow(
  rect: RowPointerGeometry,
  rowSpan: RowSpan,
  clientX: number,
  opts: { bounded: boolean },
): number {
  if (!(rect.width > 0)) {
    throw new Error(`useRowLayout: pointer geometry width must be > 0, got ${rect.width}`)
  }
  let ratio = (clientX - rect.left) / rect.width
  if (opts.bounded) ratio = Math.min(1, Math.max(0, ratio))
  return rowSpan.start + ratio * (rowSpan.end - rowSpan.start)
}

// -- Persistence helpers (M6-3 schema; injected storage for tests) --------

export function defaultRowLayoutState(): RowLayoutState {
  return {
    mode: "basic",
    secondsPerRow: DEFAULT_SECONDS_PER_ROW,
    rowHeight: DEFAULT_ROW_HEIGHT,
  }
}

function normalizeState(raw: Partial<RowLayoutState> | null | undefined): RowLayoutState {
  const def = defaultRowLayoutState()
  return {
    mode: raw?.mode === "multi" ? "multi" : def.mode,
    secondsPerRow: (SECONDS_PER_ROW_PRESETS as readonly number[]).includes(raw?.secondsPerRow ?? NaN)
      ? (raw!.secondsPerRow as number)
      : def.secondsPerRow,
    rowHeight: (ROW_HEIGHT_PRESETS as readonly number[]).includes(raw?.rowHeight ?? NaN)
      ? (raw!.rowHeight as number)
      : def.rowHeight,
  }
}

export function loadRowLayoutState(
  storage: Storage | null = typeof localStorage !== "undefined" ? localStorage : null,
): RowLayoutState {
  if (!storage) return defaultRowLayoutState()
  try {
    const raw = storage.getItem(ROW_LAYOUT_STORAGE_KEY)
    if (!raw) return defaultRowLayoutState()
    return normalizeState(JSON.parse(raw) as Partial<RowLayoutState>)
  } catch {
    // Corrupt JSON -> defaults (M6-3).
    return defaultRowLayoutState()
  }
}

export function saveRowLayoutState(
  state: RowLayoutState,
  storage: Storage | null = typeof localStorage !== "undefined" ? localStorage : null,
): void {
  if (!storage) return
  try {
    storage.setItem(ROW_LAYOUT_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Quota / privacy mode: best-effort persistence (P6).
  }
}

// -- Composable shell (reactive binding only) -----------------------------

export interface UseRowLayoutReturn {
  /** Persisted mode + presets (whitelist-validated). */
  state: Ref<RowLayoutState>
  rowCount: ComputedRef<number>
  /** Controlled scroll position of the multi-row container (px). */
  scrollTop: Ref<number>
  /** Viewport height of the scroll container (px; ResizeObserver-fed). */
  viewportHeight: Ref<number>
  visibleRows: ComputedRef<{ first: number; last: number }>
  contentHeight: ComputedRef<number>
  maxScrollTop: ComputedRef<number>
  setSecondsPerRow: (v: number) => void
  setRowHeight: (v: number) => void
  setMode: (m: "multi" | "basic") => void
  /** Time of the row currently at `scrollTop` (restore/anchor input). */
  scrollTopTime: ComputedRef<number>
  /** M6-1: scroll so `time`'s row sits at REVEAL_BIAS (no-op if comfortable). */
  revealTime: (time: number, center?: boolean) => void
  isRowVisibleInComfortZone: (rowIndex: number) => boolean
}

/**
 * Row-layout composable: owns the persisted state (localStorage, GLOBAL
 * user preference -- never per-project, P6) and derives the row geometry
 * from `duration`. The editor orchestrator feeds scrollTop/viewportHeight
 * and consumes visibleRows for keyed row rendering (M4-2).
 */
export function useRowLayout(duration: Ref<number>): UseRowLayoutReturn {
  const state = ref<RowLayoutState>(loadRowLayoutState())
  const scrollTop = ref(0)
  const viewportHeight = ref(0)

  const rowCount = computed(() => computeRowCount(duration.value, state.value.secondsPerRow))
  const stride = computed(() => strideOf(state.value.rowHeight))
  // Pure derived geometry (P1): no mode gating here -- the editor only
  // consumes these members in multi mode (M4-1); basic stays untouched.
  const contentHeight = computed(() => Math.max(0, rowCount.value * stride.value - ROW_GAP))
  const maxScrollTop = computed(() => Math.max(0, contentHeight.value - viewportHeight.value))
  const visibleRows = computed(() =>
    visibleRowWindow(scrollTop.value, viewportHeight.value, state.value.rowHeight, rowCount.value),
  )
  const scrollTopTime = computed(() =>
    scrollTopToTime(scrollTop.value, state.value.rowHeight, state.value.secondsPerRow),
  )

  // Persist changes immediately (M6-3: mode/spr/rowHeight 变更即写;
  // scrollTopTime/editorHeightPx join the schema in P4-2/P5-1).
  watch(
    state,
    s => saveRowLayoutState(s),
    { deep: true },
  )

  function setSecondsPerRow(v: number): void {
    if ((SECONDS_PER_ROW_PRESETS as readonly number[]).includes(v)) {
      state.value = { ...state.value, secondsPerRow: v }
    }
  }

  function setRowHeight(v: number): void {
    if ((ROW_HEIGHT_PRESETS as readonly number[]).includes(v)) {
      state.value = { ...state.value, rowHeight: v }
    }
  }

  function setMode(m: "multi" | "basic"): void {
    state.value = { ...state.value, mode: m }
  }

  function isRowVisibleInComfortZone(rowIndex: number): boolean {
    return isRowInComfortZone(rowIndex, scrollTop.value, viewportHeight.value, state.value.rowHeight)
  }

  function revealTime(time: number, center = false): void {
    const row = rowIndexAtTime(time, state.value.secondsPerRow)
    if (isRowVisibleInComfortZone(row)) return // comfort-zone skip (M6-1)
    // center=true (mode switch-in) centers the row; jumps use REVEAL_BIAS.
    scrollTop.value = followScrollTop(
      row,
      viewportHeight.value,
      state.value.rowHeight,
      maxScrollTop.value,
      center ? 0.5 : REVEAL_BIAS,
    )
  }

  return {
    state,
    rowCount,
    scrollTop,
    viewportHeight,
    visibleRows,
    contentHeight,
    maxScrollTop,
    setSecondsPerRow,
    setRowHeight,
    setMode,
    scrollTopTime,
    revealTime,
    isRowVisibleInComfortZone,
  }
}

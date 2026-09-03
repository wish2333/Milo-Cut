<script setup lang="ts">
import { toRef, provide, ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue"
import type { Segment, EditDecision, SubtitleTrack } from "@/types/project"
import { useTimelineMetrics, type TimelineMetrics } from "@/composables/useTimelineMetrics"
import {
  SECONDS_PER_ROW_PRESETS,
  ROW_HEIGHT_PRESETS,
  ROW_GAP,
  REVEAL_BIAS,
  FOLLOW_BIAS,
  SCRUB_SEEK_INTERVAL_MS,
  WHEEL_DEBOUNCE_MS,
  DEFAULT_ROW_HEIGHT,
  cyclePreset,
  computeRowCount,
  followScrollTop,
  rowIndexAtTime,
  shouldEmitScrubSeek,
  timeToScrollTop,
  useRowLayout,
  strideOf,
  lastRowWidthPercent,
} from "@/composables/useRowLayout"
import { useRowDragCapture, type RowEmptyGesture } from "@/composables/useRowDragCapture"
import {
  MIN_SEGMENT_DURATION,
  constrainCueRangeToTrack,
  type TrackNeighborBounds,
} from "@/utils/trackConstraints"
import {
  useLaneLayout,
  computeLaneLayout,
  LANE_COLLAPSED_HEIGHT,
  LANE_PRESET_HEIGHTS,
} from "@/composables/useLaneLayout"
import { createRafScheduler } from "@/utils/rafScheduler"
import { formatTimeShort } from "@/utils/format"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import WaveformCanvas from "./WaveformCanvas.vue"
import TimeMarksLayer from "./TimeMarksLayer.vue"
import SegmentBlocksLayer from "./SegmentBlocksLayer.vue"
import PlayheadOverlay from "./PlayheadOverlay.vue"
import ScrollbarStrip from "./ScrollbarStrip.vue"
import TrackLane from "@/components/workspace/TrackLane.vue"
import WaveformRow from "./WaveformRow.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  duration: number
  currentTime: number
  waveformPath?: string
  demoMode?: boolean
  /** v3.0.0 M11-2: extension tracks for the stacked lanes (v3.0.1 M4-4). */
  tracks?: SubtitleTrack[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
  /** v3.0.1 M5-2: extension-track trim (useTrackEdit in WorkspacePage). */
  updateTrackTime?: (trackId: string, segmentId: string, field: "start" | "end", value: number) => void
  /** v2.1.1 A-03: full-text edit mode — blocks structural ops */
  globalEditMode?: boolean
  /** v2.1.1 A-03: multi-select mode — move pointer without playing */
  selectionMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "set-time": [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
  "regenerate-waveform": []
  "split-segment": [segmentId: string, position: number]
  toast: [msg: string]
  /** v3.0.2 M5-3: empty-area double click toggles playback. */
  "toggle-play": []
  /** v3.0.2 M5-3: Shift-marquee hit ids merge into the global selection. */
  "select-segments": [segmentIds: string[]]
  /** v3.0.2 M5-3: plain empty-area press clears the global multi-selection. */
  "clear-selection": []
  /** v3.0.2 smoke fix: lane menu operations forwarded with track binding. */
  "delete-track-segment": [trackId: string, segmentId: string]
  "clear-track": [trackId: string]
  "delete-track": [trackId: string]
  /** v3.0.2 smoke fix 3rd round: 建段模式 lane click adds to that track. */
  "track-create": [trackId: string, start: number, end: number]
  /** v3.0.2 M5-3: scrubbing flag for list-follow suppression. */
  scrubbing: [active: boolean]
}>()

const durationRef = toRef(props, "duration")
const currentTimeRef = toRef(props, "currentTime")
const metrics = useTimelineMetrics(durationRef, currentTimeRef)

provide<TimelineMetrics>(TIMELINE_METRICS_KEY, metrics)

// -- v3.0.1 M4-4: stacked-timeline orchestration --------------------------
//
// Content-driven heights: the main track keeps its h-28 (112px) height and
// lanes stack below at their preset heights, so the WorkspacePage layout
// flows naturally (SPEC M4-4 squeeze rules remain available in
// computeLaneLayout for fixed-height containers; in this mode the input
// height equals desired height, so compression never triggers).
const MAIN_TRACK_HEIGHT = 112

const tracksRef = computed(() => props.tracks ?? [])
const laneCtl = useLaneLayout(() => tracksRef.value.map(t => t.id))

const laneLayout = computed(() => {
  const tracks = tracksRef.value
  const desired = tracks.reduce((sum, t) => {
    if (laneCtl.state.value.hidden[t.id]) return sum
    return (
      sum +
      (laneCtl.state.value.collapsed[t.id]
        ? LANE_COLLAPSED_HEIGHT
        : LANE_PRESET_HEIGHTS[laneCtl.state.value.preset[t.id] ?? "md"])
    )
  }, 0)
  return computeLaneLayout(
    MAIN_TRACK_HEIGHT + desired,
    tracks.map(t => t.id),
    laneCtl.state.value,
  )
})

const stackHeight = computed(() => MAIN_TRACK_HEIGHT + laneLayout.value.totalLanesHeight)

const trackById = computed(() => new Map(tracksRef.value.map(t => [t.id, t])))
const trackOverflow = computed(() => tracksRef.value.length > 4)


// -- v3.0.0 M6-2: hover seek preview (unchanged, scoped to the main track) --
const hoverLineRef = ref<HTMLElement | null>(null)
const hoverLabelRef = ref<HTMLElement | null>(null)
let pendingHover: { x: number; t: number } | null = null
let containerRect: DOMRect | null = null

const hoverScheduler = createRafScheduler(applyHover)

function applyHover() {
  const line = hoverLineRef.value
  if (!line) return
  if (!pendingHover) {
    line.style.opacity = "0"
    return
  }
  const { x, t } = pendingHover
  pendingHover = null
  line.style.opacity = "1"
  line.style.transform = `translate3d(${x}px, 0, 0)`
  if (hoverLabelRef.value) {
    hoverLabelRef.value.textContent = formatTimeShort(t)
  }
}

function handleHoverMove(e: PointerEvent) {
  const rect = containerRect
  if (!rect || rect.width <= 0) return
  const x = e.clientX - rect.left
  if (x < 0 || x > rect.width) return
  pendingHover = {
    x,
    t: metrics.viewStart.value + (x / rect.width) * metrics.viewDuration.value,
  }
  hoverScheduler.schedule()
}

function handleHoverLeave() {
  pendingHover = null
  hoverScheduler.schedule()
}

let hoverResizeObserver: ResizeObserver | null = null

let layerEl: HTMLElement | null = null
let stackEl: HTMLElement | null = null

function setLayerRef(el: unknown) {
  const htmlEl = el instanceof HTMLElement ? el : null
  layerEl = htmlEl
  metrics.containerRef.value = htmlEl
  if (htmlEl) containerRect = htmlEl.getBoundingClientRect()
}

function setStackRef(el: unknown) {
  stackEl = el instanceof HTMLElement ? el : null
}

onMounted(() => {
  // v3.0.1 M4-4: wheel zoom/scroll moves to the WHOLE stack so lanes share
  // the main-track navigation (one listener -- no double handling).
  attachBasicWheel()
  if (layerEl) {
    containerRect = layerEl.getBoundingClientRect()
    if (typeof ResizeObserver !== "undefined") {
      hoverResizeObserver = new ResizeObserver(() => {
        containerRect = layerEl ? layerEl.getBoundingClientRect() : null
      })
      hoverResizeObserver.observe(layerEl)
    }
  }
})

// Basic-mode wheel listener lifecycle: the stack unmounts in multi mode,
// so the listener re-attaches when basic mode remounts it (M4-1). The multi
// container runs its own wheel family (M5-1, handleMultiWheel above) --
// the two listeners never coexist because only one branch is mounted.
function attachBasicWheel() {
  if (stackEl && !isMulti.value) {
    stackEl.addEventListener("wheel", metrics.handleWheel, { passive: false })
  }
}
function detachBasicWheel() {
  if (stackEl) stackEl.removeEventListener("wheel", metrics.handleWheel)
}

onUnmounted(() => {
  detachBasicWheel()
  hoverScheduler.cancel()
  hoverResizeObserver?.disconnect()
  hoverResizeObserver = null
  laneCtl.cleanup()
})

function handleSeek(time: number) {
  // v2.1.1 A-03: globalEditMode blocks time-axis clicks entirely
  if (props.globalEditMode) return
  // selectionMode: move pointer without playing
  if (props.selectionMode) {
    emit("set-time", time)
    return
  }
  // normal mode: seek and play
  emit("seek", time)
}

function handleSelectRange(start: number, end: number) {
  emit("select-range", start, end)
}

function handleAddSegment(start: number, end: number) {
  emit("add-segment", start, end)
}

function handleDeleteSegment(segmentId: string) {
  emit("delete-segment", segmentId)
}

function handleSeekSegment(segment: Segment) {
  // v2.1.1 A-03: same logic as handleSeek
  if (props.globalEditMode) return
  if (props.selectionMode) {
    emit("set-time", segment.start)
    return
  }
  emit("seek-segment", segment)
}

function handleSplitSegment(segmentId: string, position: number) {
  emit("split-segment", segmentId, position)
}

// -- v3.0.2 M4-1/M4-2: multi-row timeline branch --------------------------
//
// mode === "basic" renders the v3.0.1 stacked single-window path EXACTLY
// as before (red line M0-1.5). mode === "multi" replaces it with a
// virtualized WaveformRow list driven by useRowLayout. Row preferences
// persist in localStorage only (P6) -- never project.json/patches/undo.

const rowLayout = useRowLayout(durationRef)
const isMulti = computed(() => rowLayout.state.value.mode === "multi")

/** M7-1 smoke feedback: multi 建段模式 toggle (default off = seek/scrub). */
const buildMode = ref(false)
function toggleBuildMode() {
  buildMode.value = !buildMode.value
}

// M7-2 行高联动: when extension tracks exist, the untouched default row
// height auto-bumps to 168 so main lane + sub-lanes fit. Any user-chosen
// value (persisted != default) is respected; no down-switch on removal.
watch(
  () => tracksRef.value.length > 0,
  has => {
    if (has && rowLayout.state.value.rowHeight === DEFAULT_ROW_HEIGHT) {
      rowLayout.setRowHeight(168)
    }
  },
  { immediate: true },
)


const sprPresets = SECONDS_PER_ROW_PRESETS
const rowHeightPresets = ROW_HEIGHT_PRESETS

/** Scroll container element (multi mode only). */
let scrollEl: HTMLElement | null = null
let scrollResizeObserver: ResizeObserver | null = null

function setScrollRef(el: unknown) {
  scrollEl = el instanceof HTMLElement ? el : null
  if (scrollEl) {
    rowLayout.viewportHeight.value = scrollEl.clientHeight
    scrollEl.scrollTop = rowLayout.scrollTop.value
    attachMultiWheel()
    if (typeof ResizeObserver !== "undefined") {
      scrollResizeObserver?.disconnect()
      scrollResizeObserver = new ResizeObserver(() => {
        if (scrollEl) rowLayout.viewportHeight.value = scrollEl.clientHeight
      })
      scrollResizeObserver.observe(scrollEl)
    }
  }
}

// rAF-coalesced scroll -> virtual window recompute (M4-2).
const scrollScheduler = createRafScheduler(() => {
  if (scrollEl) rowLayout.scrollTop.value = scrollEl.scrollTop
})

// M6-1: classify each scroll event. A TRUSTED event whose position matches
// the last programmatic write is our own echo (no cooldown); any other
// trusted event is the user's hand -> pause playback-follow for the 3s
// cooldown. Untrusted events skip classification entirely (test/programmatic).
// Smooth-follow echo window: while a smooth programmatic scroll animates,
// intermediate trusted events are neither classified as manual nor synced
// into state (state already holds the target).
const SMOOTH_ECHO_WINDOW_MS = 800
let programmaticUntil = 0

function writeScrollTop(top: number): void {
  rowLayout.scrollTop.value = top
  programmaticUntil = Date.now() + SMOOTH_ECHO_WINDOW_MS
  const el = scrollEl
  if (!el) return
  try {
    el.scrollTo({ top, behavior: "smooth" })
  } catch {
    el.scrollTop = top // happy-dom / older engines
  }
}

function handleScroll(e: Event) {
  const source = e.target as HTMLElement | null
  if (Date.now() < programmaticUntil) {
    return // smooth animation in flight: state is already the target
  }
  if (source && (e as Event & { isTrusted?: boolean }).isTrusted === true) {
    if (!rowLayout.consumeAutoScroll(source.scrollTop)) {
      rowLayout.markManualScroll()
    }
  }
  scrollScheduler.schedule()
}

// -- M6-1: playback follow (multi only; basic keeps maybeFollowPlayhead) ---
//
// 换行才判定: the row index must CHANGE before follow even evaluates.
// Comfortable row -> playhead-only (no scroll). Otherwise park the playing
// row at FOLLOW_BIAS, marking the write so its scroll echo is recognized.
// The manual cooldown gates BEFORE row tracking, so rows crossed while the
// user scrolls never trigger a late jump after the cooldown expires.
let lastFollowedRow: number | null = null

watch(
  () => props.currentTime,
  t => {
    if (!isMulti.value) return
    if (rowLayout.isFollowCoolingDown()) return
    const row = rowIndexAtTime(t, rowLayout.state.value.secondsPerRow)
    if (row === lastFollowedRow) return
    lastFollowedRow = row
    if (rowLayout.isRowVisibleInComfortZone(row)) return
    const target = followScrollTop(
      row,
      rowLayout.viewportHeight.value,
      rowLayout.state.value.rowHeight,
      rowLayout.maxScrollTop.value,
      FOLLOW_BIAS,
    )
    rowLayout.noteAutoScroll(target)
    writeScrollTop(target)
  },
)

// -- v3.0.2 M5-1: multi-container wheel gesture family --------------------
//
// Plain wheel / trackpad: NATIVE vertical row scrolling -- never
// preventDefault, no JS math (the WebView engine already normalizes
// deltaMode: mac pixels vs Windows line units). Ctrl/Cmd+wheel cycles the
// spr preset; Ctrl/Cmd+Shift+wheel cycles the row-height preset. Each
// family keeps its own burst accumulator: a 160ms debounce (M5-1) merges
// the burst's net notches into ONE preset jump, then re-anchors the
// playing row (M5-2) at REVEAL_BIAS under the new geometry. Zoom metaphor:
// wheel-down = zoom out = coarser spr / shorter rows. Gesture exclusivity:
// only ctrl/meta bursts are intercepted (preventDefault stops the WebView
// page zoom); the basic branch keeps metrics.handleWheel untouched (M0-1.5).

/** Net-notched burst accumulator for one gesture family. */
interface WheelBurst {
  steps: number
  timer: ReturnType<typeof setTimeout> | null
}

function createWheelBurst(): WheelBurst {
  return { steps: 0, timer: null }
}

const sprBurst = createWheelBurst()
const heightBurst = createWheelBurst()

function armBurst(burst: WheelBurst, commit: (netSteps: number) => void, steps: number): void {
  burst.steps += steps
  if (burst.timer !== null) clearTimeout(burst.timer)
  burst.timer = setTimeout(() => {
    burst.timer = null
    const net = burst.steps
    burst.steps = 0
    commit(net)
  }, WHEEL_DEBOUNCE_MS)
}

/** Discard half-finished bursts (mode switch / unmount) so a stale commit never fires. */
function resetWheelBursts(): void {
  for (const burst of [sprBurst, heightBurst]) {
    if (burst.timer !== null) clearTimeout(burst.timer)
    burst.timer = null
    burst.steps = 0
  }
}

/**
 * M5-2: put the playing row (the row containing currentTime under `spr`)
 * at REVEAL_BIAS of the viewport, computed against the NEW (spr,rowHeight)
 * geometry. Explicit inputs -- no dependency on state-update ordering.
 */
function anchorPlayingRow(spr: number, rowHeight: number): void {
  const vh = rowLayout.viewportHeight.value
  const rowCount = computeRowCount(props.duration, spr)
  const max = Math.max(0, rowCount * strideOf(rowHeight) - ROW_GAP - vh)
  const row = rowIndexAtTime(props.currentTime, spr)
  rowLayout.scrollTop.value = followScrollTop(row, vh, rowHeight, max, REVEAL_BIAS)
}

function commitSprCycle(netSteps: number): void {
  const current = rowLayout.state.value.secondsPerRow
  const next = cyclePreset(SECONDS_PER_ROW_PRESETS, current, netSteps)
  if (next === current) return
  rowLayout.setSecondsPerRow(next)
  anchorPlayingRow(next, rowLayout.state.value.rowHeight)
}

function commitRowHeightCycle(netSteps: number): void {
  const current = rowLayout.state.value.rowHeight
  const next = cyclePreset(ROW_HEIGHT_PRESETS, current, netSteps)
  if (next === current) return
  rowLayout.setRowHeight(next)
  anchorPlayingRow(rowLayout.state.value.secondsPerRow, next)
}

function handleMultiWheel(e: WheelEvent): void {
  if (!isMulti.value) return
  if (!(e.ctrlKey || e.metaKey)) return // plain wheel/trackpad: native scroll
  e.preventDefault() // boundary: stop WebView page/pinch zoom while cycling
  const direction = e.deltaY > 0 ? 1 : e.deltaY < 0 ? -1 : 0
  if (direction === 0) return
  if (e.shiftKey) {
    // Row height: wheel-down (zoom out) -> shorter rows -> smaller preset.
    armBurst(heightBurst, commitRowHeightCycle, -direction)
  } else {
    // Seconds per row: wheel-down (zoom out) -> coarser rows -> larger preset.
    armBurst(sprBurst, commitSprCycle, direction)
  }
}

function attachMultiWheel(): void {
  if (scrollEl && isMulti.value) {
    scrollEl.addEventListener("wheel", handleMultiWheel, { passive: false })
  }
}

function detachMultiWheel(): void {
  if (scrollEl) scrollEl.removeEventListener("wheel", handleMultiWheel)
}

// -- v3.0.2 M5-3: in-row pointer gestures (scrub / Ctrl-create / marquee) --
//
// The EDITOR owns every cross-pointer-event state (M3-2): rows only freeze
// their geometry into the shared drag-capture singleton on empty-press and
// emit the gesture descriptor up. Routing by modifier: plain = scrub,
// Ctrl = create segment, Shift = cross-row marquee. basic mode never gets
// here (rows do not exist there; its empty click still creates segments).

const rowDrag = useRowDragCapture()
/**
 * Orchestrator-level scrubbing flag (M5-3): the subtitle-list follow
 * consumer skips list scrolling while true. The list-side wiring lands
 * with the M6-1 follow three-way split; the contract is exposed now.
 */
const waveformScrubbing = ref(false)

/** multi-content element: marquee/create-preview coordinate basis. */
let contentEl: HTMLElement | null = null
function setContentRef(el: unknown) {
  contentEl = el instanceof HTMLElement ? el : null
}

/** Tear down the document gesture listeners + transient state. */
let gestureCleanup: (() => void) | null = null
function beginDocumentGesture(
  onMove: (e: MouseEvent) => void,
  onUp: (e: MouseEvent) => void,
): void {
  // onUp runs FIRST (it still reads frozen geometry / preview state),
  // cleanup then drops listeners and transient state.
  const up = (e: MouseEvent) => {
    try {
      onUp(e)
    } finally {
      cleanup()
    }
  }
  function cleanup() {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", up)
    gestureCleanup = null
    rowDrag.release()
    waveformScrubbing.value = false
    createPreview.value = null
    marquee.value = null
  }
  gestureCleanup = cleanup
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", up)
}

// Scrub: frozen unbounded time + clamp[0,duration], 32ms-throttled set-time
// while moving, ONE precise set-time on release. set-time (not seek) keeps
// the play state untouched -- scrub positions the playhead (M5-3 裁决).
function startScrubGesture(): void {
  waveformScrubbing.value = true
  let lastEmit = Number.NEGATIVE_INFINITY
  const seekAt = (clientX: number) => {
    const t = rowDrag.timeAt(clientX, { bounded: false })
    if (t === null) return
    emit("set-time", Math.min(Math.max(0, t), props.duration))
  }
  beginDocumentGesture(
    e => {
      const now = performance.now()
      if (!shouldEmitScrubSeek(lastEmit, now, SCRUB_SEEK_INTERVAL_MS)) return
      lastEmit = now
      seekAt(e.clientX)
    },
    e => seekAt(e.clientX),
  )
}

// Ctrl-create: row-bounded preview range from the frozen anchor, clamped
// against the neighbor gap around the anchor (preview STOPS at an existing
// block edge); release emits add-segment through the existing chain only
// when the range is legal.
interface CreatePreviewRect {
  rowIndex: number
  start: number
  end: number
  valid: boolean
}
const createPreview = ref<CreatePreviewRect | null>(null)

/** Neighbor gap around a PROSPECTIVE segment anchored at `anchor` (no id yet). */
function boundsAtAnchor(anchor: number): TrackNeighborBounds {
  let prevEnd: number | null = null
  let nextStart: number | null = null
  for (const s of props.segments) {
    if (s.end <= anchor + 1e-6 && (prevEnd === null || s.end > prevEnd)) prevEnd = s.end
    if (s.start >= anchor - 1e-6 && (nextStart === null || s.start < nextStart)) nextStart = s.start
  }
  return { prevEnd, nextStart }
}

function startCreateGesture(g: RowEmptyGesture): void {
  const anchor = rowDrag.timeAt(g.clientX, { bounded: true })
  if (anchor === null) return
  const bounds = boundsAtAnchor(anchor)
  const updatePreview = (clientX: number) => {
    const t = rowDrag.timeAt(clientX, { bounded: true })
    if (t === null) return
    const rawStart = Math.min(anchor, t)
    const rawEnd = Math.max(anchor, t)
    const r = constrainCueRangeToTrack(rawStart, rawEnd, bounds)
    createPreview.value = r.ok
      ? {
          rowIndex: g.rowIndex,
          start: r.start,
          end: r.end,
          valid: r.end - r.start >= MIN_SEGMENT_DURATION - 1e-6,
        }
      : { rowIndex: g.rowIndex, start: rawStart, end: rawEnd, valid: false }
  }
  updatePreview(g.clientX)
  beginDocumentGesture(
    e => updatePreview(e.clientX),
    () => {
      const p = createPreview.value
      if (p?.valid) handleAddSegment(p.start, p.end) // existing add-segment chain
    },
  )
}

// Shift-marquee: selection rectangle on multi-content (cross-row), hit ids
// merge into the global selectedSegmentIds via the select-segments event.
interface MarqueeRect {
  x: number
  y: number
  w: number
  h: number
}
const marquee = ref<MarqueeRect | null>(null)

function contentPoint(e: MouseEvent): { x: number; y: number } | null {
  if (!contentEl) return null
  const rect = contentEl.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function startMarqueeGesture(g: RowEmptyGesture): void {
  const anchor = { x: g.clientX, y: g.clientY }
  const updateRect = (e: MouseEvent) => {
    const p = contentPoint(e)
    if (!p) return
    marquee.value = {
      x: Math.min(anchor.x, p.x),
      y: Math.min(anchor.y, p.y),
      w: Math.abs(p.x - anchor.x),
      h: Math.abs(p.y - anchor.y),
    }
  }
  beginDocumentGesture(
    updateRect,
    () => {
      const rect = marquee.value
      // Degenerate rectangle (plain shift-click) is a selection no-op.
      if (rect && (rect.w > 2 || rect.h > 2)) {
        emit("select-segments", hitSegmentsInMarquee(rect))
      }
    },
  )
}

/** Rect-intersect every visible row's block band; returns hit segment ids. */
function hitSegmentsInMarquee(rect: MarqueeRect): string[] {
  if (!contentEl) return []
  const width = contentEl.getBoundingClientRect().width
  if (!(width > 0)) return []
  const spr = rowLayout.state.value.secondsPerRow
  const rowHeight = rowLayout.state.value.rowHeight
  const stride = strideOf(rowHeight)
  const x1 = rect.x
  const x2 = rect.x + rect.w
  const y1 = rect.y
  const y2 = rect.y + rect.h
  const firstRow = Math.max(0, Math.floor(y1 / stride))
  const lastRow = Math.min(rowLayout.rowCount.value - 1, Math.floor(y2 / stride))
  const hits = new Set<string>()
  for (let r = firstRow; r <= lastRow; r++) {
    // Skip rows whose band the rectangle does not actually cross (the
    // marquee may end inside a ROW_GAP).
    const bandTop = r * stride
    if (bandTop + rowHeight <= y1 || bandTop >= y2) continue
    const rowStartT = r * spr
    const t1 = rowStartT + (x1 / width) * spr
    const t2 = rowStartT + (x2 / width) * spr
    for (const s of props.segments) {
      if (s.end > t1 && s.start < t2) hits.add(s.id)
    }
  }
  return [...hits]
}

/** M5-3 router: rows freeze geometry, the editor picks the gesture. */
function handleRowEmptyGesture(g: RowEmptyGesture): void {
  if (!isMulti.value) return
  if (g.ctrlKey) startCreateGesture(g)
  else if (g.shiftKey) startMarqueeGesture(g)
  else {
    emit("clear-selection") // 清选上行 (M5-3)
    startScrubGesture()
  }
}

/** Preview rectangle style inside multi-content (row-local time mapping). */
const createPreviewStyle = computed(() => {
  const p = createPreview.value
  if (!p) return {}
  const spr = rowLayout.state.value.secondsPerRow
  const rowStartT = p.rowIndex * spr
  return {
    top: p.rowIndex * strideOf(rowLayout.state.value.rowHeight) + "px",
    height: rowLayout.state.value.rowHeight + "px",
    left: ((p.start - rowStartT) / spr) * 100 + "%",
    width: ((p.end - p.start) / spr) * 100 + "%",
  }
})

const marqueeStyle = computed(() => {
  const m = marquee.value
  if (!m) return {}
  return {
    left: m.x + "px",
    top: m.y + "px",
    width: m.w + "px",
    height: m.h + "px",
  }
})

// Programmatic scroll writes (revealTime / mode switch / clamp) reflect
// into the container. A write that equals the DOM position is a no-op, so
// user scrolling never fights this watcher in practice (P4-1 adds the
// explicit autoScrollTarget loop suppression for smooth follow).
watch(
  () => rowLayout.scrollTop.value,
  top => {
    if (scrollEl && Math.abs(scrollEl.scrollTop - top) > 0.5) {
      scrollEl.scrollTop = top
    }
  },
)

// Duration shrink (re-open / media change): clamp scrollTop to maxScrollTop.
watch(
  () => rowLayout.maxScrollTop.value,
  max => {
    if (rowLayout.scrollTop.value > max) rowLayout.scrollTop.value = max
  },
)

/**
 * Virtualized row descriptors. The key embeds the spr itself (M4-2):
 * changing the spr preset changes every key -> wholesale row remount
 * (adapters statically capture spr). Keying on the derived start alone is
 * NOT enough -- row 0's start is 0*spr == 0 under every preset, so its
 * key would never change and the stale adapter kept rendering (fixed
 * after beta.1 smoke finding: first row ignored spr changes until
 * scrolled out and back). Changing rowHeight only mutates top/height
 * props -> geometry-only keyed reuse.
 */
const renderedRows = computed(() => {
  if (!isMulti.value) return []
  const spr = rowLayout.state.value.secondsPerRow
  const stride = strideOf(rowLayout.state.value.rowHeight)
  const rows: Array<{ index: number; start: number; top: number; key: string }> = []
  for (let i = rowLayout.visibleRows.value.first; i <= rowLayout.visibleRows.value.last; i++) {
    const start = i * spr
    rows.push({
      index: i,
      start,
      top: i * stride,
      key: `r${i}-${start}@${spr}`,
    })
  }
  return rows
})

// -- M7-1 (P5-1): user-resizable multi viewport -----------------------------
//
// editorHeightPx persists in the M6-3 schema; unset -> 45% of the window,
// always clamped to [20%, 70%] of the current window height. Rows keep
// their preset rowHeight, so dragging only changes HOW MANY rows are
// visible (no canvas stretch/redraw needed in the row model). The divider
// sits on the container's top edge and writes through immediately (M6-3:
// heightPx is a write-on-change field).

const MIN_HEIGHT_RATIO = 0.2
const MAX_HEIGHT_RATIO = 0.7
const DEFAULT_HEIGHT_RATIO = 0.45

function windowInnerHeight(): number {
  return typeof window !== "undefined" ? window.innerHeight : 0
}

function clampEditorHeight(px: number): number {
  const vh = windowInnerHeight()
  if (!(vh > 0)) return Math.max(120, px)
  return Math.min(Math.max(px, Math.round(vh * MIN_HEIGHT_RATIO)), Math.round(vh * MAX_HEIGHT_RATIO))
}

const multiViewportHeight = computed(() => {
  const persisted = rowLayout.state.value.editorHeightPx
  if (persisted && persisted > 0) return clampEditorHeight(persisted)
  const vh = windowInnerHeight()
  if (!(vh > 0)) return 320 // headless fallback (tests / exotic shells)
  return Math.round(vh * DEFAULT_HEIGHT_RATIO)
})

let dividerDragStartY = 0
let dividerDragStartHeight = 0

function handleDividerMouseDown(e: MouseEvent) {
  dividerDragStartY = e.clientY
  dividerDragStartHeight = multiViewportHeight.value
  const onMove = (ev: MouseEvent) => {
    // Dragging UP grows the panel.
    rowLayout.state.value = {
      ...rowLayout.state.value,
      editorHeightPx: clampEditorHeight(dividerDragStartHeight + (dividerDragStartY - ev.clientY)),
    }
  }
  const onUp = () => {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

// M7-1: controls-bar middle label -- the time range the viewport covers.
const viewportCoverageLabel = computed(() => {
  const { first, last } = rowLayout.visibleRows.value
  const spr = rowLayout.state.value.secondsPerRow
  const start = rowLayout.scrollTopTime.value
  const end = Math.min(props.duration, (last + 1 - first) * spr + start)
  return `${formatTimeShort(start)}–${formatTimeShort(end)} / 全片 ${formatTimeShort(props.duration)}`
})

// -- M6-4: mini overview strip geometry (multi) -----------------------------
//
// Coverage comes from visibleRows x spr / duration -- deliberately NOT the
// single-window thumbLeft/thumbWidth (评审修正: those are single-window
// window geometry). The playhead tick is its own ratio. Seeking routes
// through revealTime so jumps stay row-aligned.
const overviewGeometry = computed(() => {
  const { first, last } = rowLayout.visibleRows.value
  const spr = rowLayout.state.value.secondsPerRow
  const duration = props.duration
  if (!(duration > 0)) {
    return { leftPercent: 0, widthPercent: 100, playheadPercent: 0, duration: 0 }
  }
  const leftPercent = Math.min(100, (first * spr * 100) / duration)
  const widthPercent = Math.min(
    100 - leftPercent,
    ((last + 1 - first) * spr * 100) / duration,
  )
  const playheadPercent = Math.min(100, Math.max(0, (props.currentTime * 100) / duration))
  return { leftPercent, widthPercent, playheadPercent, duration }
})

function handleOverviewSeek(time: number): void {
  rowLayout.revealTime(time)
}

/** Last row shrinks to the remaining duration (R4.1). */
function rowWidthPercent(index: number): number {
  const last = rowLayout.rowCount.value - 1
  if (index !== last) return 100
  return lastRowWidthPercent(props.duration, rowLayout.state.value.secondsPerRow)
}

// Mode switch (M6-2 minimal form; follow-state reset/refinement lands P4):
// multi -> reveal the playing row; basic -> the single window keeps its own
// state (v3.0.1 semantics untouched).
// M6-2: mode-switch state reset + bidirectional migration.
// multi -> reveal the BASIC WINDOW's center (the row the user was looking
// at), not the playhead; basic -> center the single window on the top row
// of the multi viewport (scrollTopTime + spr/2, the v3.0.1 centering
// semantics). Frozen gesture state never outlives its mode.
watch(isMulti, async multi => {
  if (multi) {
    lastFollowedRow = null // fresh follow semantics on each multi entry
    await nextTick()
    rowLayout.revealTime(
      metrics.viewStart.value + metrics.viewDuration.value / 2,
      true,
    )
  } else {
    resetWheelBursts() // half-finished ctrl+wheel bursts never outlive multi
    gestureCleanup?.() // nor do half-finished scrub/create/marquee gestures
    lastFollowedRow = null
    metrics.scrollTo(
      rowLayout.scrollTopTime.value + rowLayout.state.value.secondsPerRow / 2,
    )
    nextTick(attachBasicWheel)
  }
})

// M6-3 restore: a fresh editor in multi mode jumps back to the persisted
// browsing position, quantized to the row boundary and clamped to the
// (possibly shrunken) duration.
function restorePersistedScroll(): void {
  const st = rowLayout.state.value
  if (!st.scrollTopTime) return
  rowLayout.scrollTop.value = Math.min(
    timeToScrollTop(st.scrollTopTime, st.rowHeight, st.secondsPerRow),
    rowLayout.maxScrollTop.value,
  )
}

onMounted(() => {
  if (isMulti.value) restorePersistedScroll() // M6-3: re-open restores position
})

onUnmounted(() => {
  scrollResizeObserver?.disconnect()
  scrollResizeObserver = null
  scrollScheduler.cancel()
  detachMultiWheel()
  resetWheelBursts()
  gestureCleanup?.()
  rowLayout.flushScrollTopSave() // M6-3: unmount fallback write
})

// Multi-mode row event forwarding: the editor owns all navigation/edit
// routing, rows are windowed views (M3-2).
function handleRowSetTime(t: number) {
  emit("set-time", t)
}

// Test surface + M6-1 navigation entry: the subtitle-list seek path calls
// revealTime so jumps share the reveal semantics (REVEAL_BIAS, comfort
// skip, follow cooldown). No-op in basic mode (its window keeps its own
// navigation state).
watch(waveformScrubbing, v => emit("scrubbing", v))

function revealFromNavigation(time: number): void {
  if (!isMulti.value) return
  rowLayout.revealTime(time)
}

defineExpose({ waveformScrubbing, revealTime: revealFromNavigation })

</script>

<template>
  <div class="flex flex-col">
    <!-- Controls bar -->
    <div class="flex h-6 items-center gap-2 border-b border-gray-200 px-2 text-xs text-gray-500">
      <button
        class="shrink-0 rounded bg-gray-200 px-2 py-0.5 text-[11px] leading-none text-gray-600 hover:bg-gray-300 transition-colors"
        title="Regenerate waveform"
        @click="emit('regenerate-waveform')"
      >
        Regen
      </button>
      <!-- M7-1 smoke feedback: 建段 toggle applies to BOTH modes (default off) -->
      <button
        class="shrink-0 rounded px-1.5 py-0.5 text-[11px] leading-none transition-colors"
        :class="buildMode ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
        data-test="build-mode-toggle"
        title="建段模式：开启后点击时间轴空白区域直接新建字幕（关闭时点击为定位）"
        @click="toggleBuildMode"
      >
        {{ buildMode ? "建段中" : "建段" }}
      </button>
      <!-- v3.0.2 M4-1: mode switch (multi rows / basic focus) -->
      <div class="flex shrink-0 overflow-hidden rounded border border-gray-300" data-test="mode-switch">
        <button
          class="px-1.5 py-px text-[11px] leading-none transition-colors"
          :class="isMulti ? 'bg-gray-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          data-test="mode-multi"
          title="Multi-row timeline"
          @click="rowLayout.setMode('multi')"
        >
          多行
        </button>
        <button
          class="px-1.5 py-px text-[11px] leading-none transition-colors"
          :class="!isMulti ? 'bg-gray-700 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'"
          data-test="mode-basic"
          title="Single-window timeline"
          @click="rowLayout.setMode('basic')"
        >
          聚焦
        </button>
      </div>
      <!-- M6-2 note: wrapper DIVs (display:contents) instead of <template
           v-if> fragments -- happy-dom drops Vue's comment anchors, which
           crashed fragment removal in tests; a real browser never did. -->
      <div v-if="isMulti" class="contents">
        <select
          class="shrink-0 rounded border border-gray-300 bg-surface px-1 py-0 text-[11px]"
          data-test="spr-select"
          :value="rowLayout.state.value.secondsPerRow"
          title="Seconds per row"
          @change="rowLayout.setSecondsPerRow(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="s in sprPresets" :key="s" :value="s">{{ s }}s/行</option>
        </select>
        <select
          class="shrink-0 rounded border border-gray-300 bg-surface px-1 py-0 text-[11px]"
          data-test="row-height-select"
          :value="rowLayout.state.value.rowHeight"
          title="Row height"
          @change="rowLayout.setRowHeight(Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-for="h in rowHeightPresets" :key="h" :value="h">{{ h }}px</option>
        </select>
        <span class="flex-1 text-center" data-test="viewport-coverage">{{ viewportCoverageLabel }}</span>
      </div>
      <div v-else class="contents">
        <span data-test="basic-view-start">{{ metrics.viewStart.value.toFixed(1) }}s</span>
        <span class="flex-1 text-center">{{ metrics.viewDuration.value.toFixed(1) }}s window</span>
        <span>{{ metrics.viewEnd.value.toFixed(1) }}s</span>
      </div>
    </div>

    <!-- M7-1: viewport height divider (drag up = grow) -->
    <div
      v-if="isMulti"
      data-test="viewport-divider"
      class="h-1.5 shrink-0 cursor-ns-resize bg-transparent transition-colors hover:bg-gray-200"
      title="拖拽调整多行区高度"
      @mousedown="handleDividerMouseDown"
    ></div>

    <!-- v3.0.2 M4-1: multi-row virtualized surface -->
    <div
      v-if="isMulti"
      :ref="setScrollRef"
      data-test="multi-scroll"
      class="relative overflow-y-auto overscroll-contain"
      :style="{ height: multiViewportHeight + 'px' }"
      @scroll="handleScroll"
    >
      <div
        :ref="setContentRef"
        data-test="multi-content"
        class="relative"
        :style="{ height: rowLayout.contentHeight.value + 'px' }"
      >
        <WaveformRow
          v-for="row in renderedRows"
          :key="row.key"
          :row-index="row.index"
          :seconds-per-row="rowLayout.state.value.secondsPerRow"
          :top="row.top"
          :row-height="rowLayout.state.value.rowHeight"
          :width-percent="rowWidthPercent(row.index)"
          :duration="duration"
          :current-time="currentTime"
          :segments="segments"
          :edits="edits"
          :waveform-path="waveformPath"
          :demo-mode="demoMode"
          :update-time="updateTime"
          :global-edit-mode="globalEditMode"
          :empty-area-mode="buildMode ? 'add' : 'seek'"
          :row-drag="rowDrag"
          :tracks="tracks"
          :lane-state="laneCtl.state.value"
          :update-track-time="updateTrackTime"
          @seek="handleSeek"
          @toggle-collapse="laneCtl.toggleCollapse"
          @select-range="handleSelectRange"
          @add-segment="handleAddSegment"
          @delete-segment="handleDeleteSegment"
          @seek-segment="handleSeekSegment"
          @split-segment="handleSplitSegment"
          @set-time="handleRowSetTime"
          @toast="(msg: string) => emit('toast', msg)"
          @empty-gesture="handleRowEmptyGesture"
          @toggle-play="emit('toggle-play')"
          @delete-track-segment="(tid: string, sid: string) => emit('delete-track-segment', tid, sid)"
          @clear-track="(tid: string) => emit('clear-track', tid)"
          @delete-track="(tid: string) => emit('delete-track', tid)"
        />
        <!-- M5-3: Ctrl-create preview (row-local bounded range) -->
        <div
          v-if="createPreview"
          data-test="create-preview"
          class="pointer-events-none absolute rounded border"
          :class="createPreview.valid ? 'border-green-500 bg-green-300/30' : 'border-red-500 bg-red-300/30'"
          :style="createPreviewStyle"
        ></div>
        <!-- M5-3: Shift cross-row marquee -->
        <div
          v-if="marquee"
          data-test="marquee-rect"
          class="pointer-events-none absolute border border-blue-500 bg-blue-400/20"
          :style="marqueeStyle"
        ></div>
        <!-- Mini-map placeholder (P4-3 implements the mini overview strip) -->
      </div>
    </div>

    <!-- Stacked surface: main track + N extension lanes + single playhead (basic) -->
    <div
      v-else
      :ref="setStackRef"
      data-test="timeline-stack"
      class="relative overflow-hidden"
      :style="{ height: stackHeight + 'px' }"
    >
      <!-- Main track area (z0-z10 layering unchanged) -->
      <div
        :ref="setLayerRef"
        data-test="waveform-layer"
        class="relative overflow-hidden"
        :style="{ height: laneLayout.mainTrackHeight + 'px' }"
        @pointermove="handleHoverMove"
        @pointerleave="handleHoverLeave"
      >
        <WaveformCanvas
          :segments="segments"
          :waveform-path="waveformPath"
          :duration="duration"
          :demo-mode="demoMode"
          style="z-index: 0; pointer-events: none"
        />
        <TimeMarksLayer
          style="z-index: 1"
          @seek="handleSeek"
        />
        <SegmentBlocksLayer
          :segments="segments"
          :edits="edits"
          :update-time="updateTime"
          :current-time="currentTime"
          :duration="duration"
          :global-edit-mode="globalEditMode"
          :empty-area-mode="buildMode ? 'add' : 'seek'"
          style="z-index: 2"
          @select-range="handleSelectRange"
          @add-segment="handleAddSegment"
          @delete-segment="handleDeleteSegment"
          @seek-segment="handleSeekSegment"
          @split-segment="handleSplitSegment"
          @set-time="emit('set-time', $event)"
          @toast="emit('toast', $event)"
        />
        <!-- M5-4: trim-end carries no editor action -- the REAL chain is the
             optimistic updateTime path (linkage happens there and is never
             Alt-skippable); the beta.1 placeholder toast is gone. -->
        <!-- v3.0.0 M6-2: hover seek preview (imperative, pointer-events:none) -->
        <div
          ref="hoverLineRef"
          data-test="hover-preview"
          class="pointer-events-none absolute inset-y-0 left-0 opacity-0"
          style="z-index: 5"
        >
          <div class="h-full w-px bg-ink-muted/60"></div>
          <div
            ref="hoverLabelRef"
            class="absolute left-1 top-6 whitespace-nowrap rounded bg-surface-tile-1 px-1 py-0.5 text-[10px] leading-none text-ink-muted shadow-sm"
          ></div>
        </div>
      </div>

      <!-- Extension lanes (v3.0.1 M4-2/M4-4) -->
      <template v-for="lane in laneLayout.lanes" :key="lane.trackId">
        <TrackLane
          v-if="!lane.hidden && trackById.get(lane.trackId)"
          :track="trackById.get(lane.trackId)!"
          :lane="{ ...lane, top: laneLayout.mainTrackHeight + lane.top }"
          :update-time="
            updateTrackTime
              ? (sid, f, v) => updateTrackTime!(lane.trackId, sid, f, v)
              : undefined
          "
          @seek="(t) => handleSeek(t)"
          @toggle-collapse="laneCtl.toggleCollapse"
          @delete-segment="(sid: string) => emit('delete-track-segment', lane.trackId, sid)"
          @clear-track="emit('clear-track', lane.trackId)"
          @delete-track="emit('delete-track', lane.trackId)"
        />
      </template>

      <!-- v3.0.1 M4-4: single playhead promoted to the stack surface --
           inset-y-0 spans the main track AND every lane (one owner, red
           line M0-3 / design-spec "promote the owner" rule). -->
      <PlayheadOverlay style="z-index: 10; pointer-events: none" />

      <!-- v3.0.1 R3.4: soft track-count hint (no hard cap) -->
      <div
        v-if="trackOverflow"
        data-test="track-overflow-hint"
        class="absolute bottom-0 right-1 rounded bg-amber-50 px-1 py-px text-[10px] leading-tight text-amber-700"
        style="z-index: 6"
      >
        副轨较多（{{ tracksRef.length }} 条），建议合并或隐藏
      </div>
    </div>

    <!-- M6-4: basic keeps the single-window scrollbar; multi gets the mini
         overview strip (full-timeline coverage + playhead tick). -->
    <ScrollbarStrip
      v-if="!isMulti"
    />
    <ScrollbarStrip
      v-else
      :overview="overviewGeometry"
      @overview-seek="handleOverviewSeek"
    />
  </div>
</template>

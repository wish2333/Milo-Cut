import { computed, type ComputedRef, type Ref, ref, watch } from "vue"
import { formatTimeShort } from "@/utils/format"

export const MIN_VIEW_DURATION = 2
export const MAX_VIEW_DURATION = 600
const ZOOM_IN_FACTOR = 0.87
const ZOOM_OUT_FACTOR = 1.15
const AUTO_FOLLOW_THROTTLE_MS = 200
const NICE_STEPS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
const TIME_MARK_TARGET_COUNT = 10

export interface TimelineMetrics {
  duration: Ref<number>
  viewStart: Ref<number>
  viewDuration: Ref<number>
  viewEnd: ComputedRef<number>

  timeToPercent: (time: number) => number
  percentToPixels: (pct: number) => number
  getTimeFromX: (clientX: number) => number

  clampViewStart: () => void
  scrollTo: (time: number) => void
  zoomAt: (centerTime: number, factor: number) => void
  handleWheel: (e: WheelEvent) => void

  ensurePlayheadInView: () => void
  maybeFollowPlayhead: () => void
  playheadPercent: ComputedRef<number>
  playheadVisible: ComputedRef<boolean>

  thumbLeft: ComputedRef<number>
  thumbWidth: ComputedRef<number>

  timeMarks: ComputedRef<Array<{ percent: number; label: string; time: number }>>

  containerRef: Ref<HTMLElement | null>
}

export function useTimelineMetrics(
  duration: Ref<number>,
  currentTime: Ref<number>,
): TimelineMetrics {
  const viewStart = ref(0)
  const viewDuration = ref(30)
  const containerRef = ref<HTMLElement | null>(null)

  const viewEnd = computed(() =>
    Math.min(viewStart.value + viewDuration.value, duration.value),
  )

  // -- Time / pixel conversion ------------------------------------------

  function timeToPercent(time: number): number {
    if (viewDuration.value <= 0) return 0
    return ((time - viewStart.value) / viewDuration.value) * 100
  }

  function percentToPixels(pct: number): number {
    const el = containerRef.value
    if (!el) return 0
    return (pct / 100) * el.getBoundingClientRect().width
  }

  function getTimeFromX(clientX: number): number {
    const el = containerRef.value
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    const ratio = (clientX - rect.left) / rect.width
    return viewStart.value + ratio * viewDuration.value
  }

  // -- View navigation --------------------------------------------------

  function clampViewStart() {
    const maxStart = Math.max(0, duration.value - viewDuration.value)
    viewStart.value = Math.max(0, Math.min(viewStart.value, maxStart))
  }

  function scrollTo(time: number) {
    const center = time - viewDuration.value / 2
    viewStart.value = Math.max(
      0,
      Math.min(center, Math.max(0, duration.value - viewDuration.value)),
    )
  }

  // -- Zoom -------------------------------------------------------------

  function zoomAt(centerTime: number, factor: number) {
    const newDuration = Math.max(
      MIN_VIEW_DURATION,
      Math.min(Math.min(duration.value, MAX_VIEW_DURATION), viewDuration.value * factor),
    )
    const centerRatio = (centerTime - viewStart.value) / viewDuration.value
    viewDuration.value = newDuration
    viewStart.value = centerTime - centerRatio * newDuration
    clampViewStart()
  }

  function handleWheel(e: WheelEvent) {
    e.preventDefault()
    if (e.ctrlKey || e.metaKey) {
      const el = containerRef.value
      if (!el) return
      const rect = el.getBoundingClientRect()
      const ratio = (e.clientX - rect.left) / rect.width
      const timeAtCursor = viewStart.value + ratio * viewDuration.value
      const factor = e.deltaY > 0 ? ZOOM_OUT_FACTOR : ZOOM_IN_FACTOR
      zoomAt(timeAtCursor, factor)
    } else {
      const delta =
        Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
      const scrollAmount = (delta / 120) * viewDuration.value * 0.15
      viewStart.value += scrollAmount
      clampViewStart()
    }
  }

  // -- Playhead follow --------------------------------------------------

  function ensurePlayheadInView() {
    const t = currentTime.value
    if (t < viewStart.value || t > viewEnd.value) {
      scrollTo(t)
    }
  }

  let lastFollowTime = 0
  function maybeFollowPlayhead() {
    const now = Date.now()
    if (now - lastFollowTime < AUTO_FOLLOW_THROTTLE_MS) return
    lastFollowTime = now
    ensurePlayheadInView()
  }

  const playheadPercent = computed(() => {
    if (viewDuration.value <= 0) return 0
    const pct =
      ((currentTime.value - viewStart.value) / viewDuration.value) * 100
    return Math.max(0, Math.min(100, pct))
  })

  const playheadVisible = computed(
    () =>
      currentTime.value >= viewStart.value &&
      currentTime.value <= viewEnd.value,
  )

  // -- Scrollbar geometry -----------------------------------------------

  const thumbLeft = computed(() => {
    if (duration.value <= 0) return 0
    return (viewStart.value / duration.value) * 100
  })

  const thumbWidth = computed(() => {
    if (duration.value <= 0) return 100
    return Math.max(5, (viewDuration.value / duration.value) * 100)
  })

  // -- Time marks -------------------------------------------------------

  const timeMarks = computed(() => {
    if (viewDuration.value <= 0) return []
    const rawStep = viewDuration.value / TIME_MARK_TARGET_COUNT
    const step = NICE_STEPS.find(s => s >= rawStep) ?? rawStep
    const marks: { percent: number; label: string; time: number }[] = []
    const start = Math.ceil(viewStart.value / step) * step
    for (let t = start; t <= viewEnd.value; t += step) {
      marks.push({
        percent: ((t - viewStart.value) / viewDuration.value) * 100,
        label: formatTimeShort(t),
        time: t,
      })
    }
    return marks
  })

  // -- Watchers ---------------------------------------------------------

  watch(currentTime, maybeFollowPlayhead)

  watch(duration, d => {
    if (viewDuration.value > d) {
      viewDuration.value = Math.min(30, d)
    }
    clampViewStart()
  })

  return {
    duration,
    viewStart,
    viewDuration,
    viewEnd,

    timeToPercent,
    percentToPixels,
    getTimeFromX,

    clampViewStart,
    scrollTo,
    zoomAt,
    handleWheel,

    ensurePlayheadInView,
    maybeFollowPlayhead,
    playheadPercent,
    playheadVisible,

    thumbLeft,
    thumbWidth,

    timeMarks,

    containerRef,
  }
}

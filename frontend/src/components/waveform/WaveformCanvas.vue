<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from "vue"
import type { Segment } from "@/types/project"
import { createRafScheduler } from "@/utils/rafScheduler"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

interface PeakData {
  min: number
  max: number
}

const props = defineProps<{
  segments: Segment[]
  waveformPath?: string
  duration?: number
  demoMode?: boolean
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const canvasRef = ref<HTMLCanvasElement | null>(null)
const peaks = ref<PeakData[] | null>(null)
const loadError = ref(false)

// v2.3.1 Bug D 热点 5: Pre-compute a silence-only timeline so drawSilenceOverlay
// can use binary search instead of scanning all segments every redraw.
// For the user's reference project (1167 segments = 477 subtitle + 690 silence)
// this cuts each redraw from 1167 comparisons down to ~log2(690) + visible_count.
const silenceSegments = computed(() =>
  props.segments
    .filter(seg => seg.type === "silence")
    .sort((a, b) => a.start - b.start),
)

/**
 * Binary search for the first silence segment that might overlap the viewport.
 * Returns the smallest index i where silenceSegments[i].end >= viewStart, so
 * earlier segments (entirely left of viewport) are skipped in O(log N).
 */
function findFirstVisibleSilence(
  silences: readonly Segment[],
  viewStart: number,
): number {
  let lo = 0
  let hi = silences.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if (silences[mid].end < viewStart) {
      lo = mid + 1
    } else {
      hi = mid
    }
  }
  return lo
}

// -- Load waveform data -------------------------------------------------

async function loadWaveform(path: string) {
  try {
    const res = await fetch(path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (Array.isArray(data) && data.length > 0 && "min" in data[0]) {
      peaks.value = data
    } else {
      loadError.value = true
    }
  } catch {
    loadError.value = true
  }
}

function createDemoPeaks(count = 720): PeakData[] {
  let seed = 24681357
  return Array.from({ length: count }, (_, index) => {
    seed = (seed * 1664525 + 1013904223) >>> 0
    const noise = (seed / 4294967296) * 0.35
    const envelope = 0.25 + Math.abs(Math.sin(index / 21)) * 0.55
    const amplitude = Math.min(0.95, envelope + noise)
    return { min: -amplitude, max: amplitude }
  })
}

// -- Canvas rendering ---------------------------------------------------
//
// v3.0.0 M6-1: all redraws go through a rAF scheduler (burst of wheel/zoom
// events coalesces into at most one draw per frame -- the old 0.02s
// viewStart dedup is superseded and removed). The canvas bitmap resolution
// is only reset when CSS size / dpr actually change; regular redraws are
// clearRect + repaint with the transform kept from the last reset.

const scheduler = createRafScheduler(draw)

// CSS size (not bitmap size) cached from the ResizeObserver so draw() never
// touches layout (no getBoundingClientRect inside the frame).
let cssWidth = 0
let cssHeight = 0
let drawnWidth = -1
let drawnHeight = -1
let drawnDpr = -1

let dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1
let dprMql: MediaQueryList | null = null

function unwatchDpr() {
  if (dprMql) {
    // Safari < 14 only has addListener; WKWebView targets are new enough for
    // addEventListener but guard anyway.
    if (typeof dprMql.removeEventListener === "function") {
      dprMql.removeEventListener("change", onDprChange)
    } else if (typeof (dprMql as unknown as { removeListener?: (cb: () => void) => void }).removeListener === "function") {
      ;(dprMql as unknown as { removeListener: (cb: () => void) => void }).removeListener(onDprChange)
    }
    dprMql = null
  }
}

function onDprChange() {
  // Re-arm the query for the NEW resolution, then mark the bitmap dirty.
  unwatchDpr()
  dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1
  watchDpr()
  scheduler.schedule()
}

function watchDpr() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return
  try {
    dprMql = window.matchMedia(`(resolution: ${dpr}dppx)`)
    if (typeof dprMql.addEventListener === "function") {
      dprMql.addEventListener("change", onDprChange)
    } else if (typeof (dprMql as unknown as { addListener?: (cb: () => void) => void }).addListener === "function") {
      ;(dprMql as unknown as { addListener: (cb: () => void) => void }).addListener(onDprChange)
    } else {
      dprMql = null
    }
  } catch {
    dprMql = null
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext("2d")
  if (!ctx) return

  // Reset the bitmap only when geometry actually changed; otherwise keep
  // the canvas transform from the last reset (setting width/height clears
  // the bitmap AND the context state, which is what made every redraw
  // reallocate textures).
  if (cssWidth !== drawnWidth || cssHeight !== drawnHeight || dpr !== drawnDpr) {
    canvas.width = Math.max(1, Math.round(cssWidth * dpr))
    canvas.height = Math.max(1, Math.round(cssHeight * dpr))
    drawnWidth = cssWidth
    drawnHeight = cssHeight
    drawnDpr = dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  const w = cssWidth
  const h = cssHeight
  const mid = h / 2

  ctx.clearRect(0, 0, w, h)

  // Draw waveform or fallback flat line
  if (peaks.value && peaks.value.length > 0 && !loadError.value) {
    drawWaveform(ctx, w, h, mid)
  } else {
    drawFallback(ctx, w, mid)
  }

  // Draw silence overlay
  drawSilenceOverlay(ctx, w, h)
}

function drawWaveform(ctx: CanvasRenderingContext2D, w: number, _h: number, mid: number) {
  const peakData = peaks.value!
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value

  // Map peaks to viewport
  const totalBuckets = peakData.length
  const bucketsPerSecond = props.duration ? totalBuckets / props.duration : totalBuckets / (vs + vd)

  const startBucket = Math.floor(vs * bucketsPerSecond)
  const endBucket = Math.min(Math.ceil(ve * bucketsPerSecond), totalBuckets)
  const visibleBuckets = endBucket - startBucket

  if (visibleBuckets <= 0) return

  const bucketWidth = w / visibleBuckets

  // Draw filled polygon
  ctx.beginPath()
  ctx.moveTo(0, mid)

  // Top peaks (max values)
  for (let i = 0; i < visibleBuckets; i++) {
    const bucket = startBucket + i
    if (bucket >= totalBuckets) break
    const x = i * bucketWidth
    const y = mid - (peakData[bucket].max * mid * 1.3)
    ctx.lineTo(x, y)
  }

  // Bottom peaks (min values, mirrored)
  for (let i = visibleBuckets - 1; i >= 0; i--) {
    const bucket = startBucket + i
    if (bucket >= totalBuckets) break
    const x = i * bucketWidth
    const y = mid - (peakData[bucket].min * mid * 1.3)
    ctx.lineTo(x, y)
  }

  ctx.closePath()
  ctx.fillStyle = "#94a3b8" // slate-400
  ctx.fill()
  ctx.strokeStyle = "#64748b" // slate-500
  ctx.lineWidth = 0.5
  ctx.stroke()
}

function drawFallback(ctx: CanvasRenderingContext2D, w: number, mid: number) {
  ctx.beginPath()
  ctx.moveTo(0, mid)
  ctx.lineTo(w, mid)
  ctx.strokeStyle = "#94a3b8"
  ctx.lineWidth = 1
  ctx.stroke()
}

function drawSilenceOverlay(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const vs = metrics.viewStart.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return
  const ve = vs + vd

  // v2.3.1 Bug D 热点 5: Use binary search on the pre-computed silence-only
  // timeline instead of scanning every segment (including subtitles) on each
  // redraw. Break as soon as a silence starts past the viewport's right edge.
  const silences = silenceSegments.value
  for (let i = findFirstVisibleSilence(silences, vs); i < silences.length; i++) {
    const seg = silences[i]
    if (seg.start >= ve) break

    const clampStart = Math.max(seg.start, vs)
    const clampEnd = Math.min(seg.end, ve)
    const x = ((clampStart - vs) / vd) * w
    const width = ((clampEnd - clampStart) / vd) * w

    ctx.fillStyle = "rgba(148, 163, 184, 0.25)" // slate-400 @ 25%
    ctx.fillRect(x, 0, width, h)
  }
}

// -- Lifecycle -----------------------------------------------------------

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  const canvas = canvasRef.value
  if (canvas) {
    // Cache CSS size from the observer callback; the draw task itself stays
    // layout-read-free.
    resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[entries.length - 1]
      if (entry) {
        cssWidth = entry.contentRect.width
        cssHeight = entry.contentRect.height
      }
      scheduler.schedule()
    })
    resizeObserver.observe(canvas)
    cssWidth = canvas.clientWidth || cssWidth
    cssHeight = canvas.clientHeight || cssHeight
    watchDpr()
    scheduler.schedule()
  }
})

onUnmounted(() => {
  scheduler.cancel()
  resizeObserver?.disconnect()
  unwatchDpr()
})

// -- Watchers ------------------------------------------------------------

watch(() => props.waveformPath, (path) => {
  if (path) {
    loadWaveform(path)
  } else if (props.demoMode) {
    peaks.value = createDemoPeaks()
    loadError.value = false
  }
}, { immediate: true })

watch([metrics.viewDuration, peaks, () => props.segments], () => {
  scheduler.schedule()
})

watch(metrics.viewStart, () => {
  scheduler.schedule()
})
</script>

<template>
  <div class="absolute inset-0">
    <canvas ref="canvasRef" class="h-full w-full" />
  </div>
</template>

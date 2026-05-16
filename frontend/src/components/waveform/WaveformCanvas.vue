<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref, watch } from "vue"
import type { Segment } from "@/types/project"
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
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const canvasRef = ref<HTMLCanvasElement | null>(null)
const peaks = ref<PeakData[] | null>(null)
const loadError = ref(false)

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

// -- Canvas rendering ---------------------------------------------------

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext("2d")
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const w = rect.width
  const h = rect.height
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

  for (const seg of props.segments) {
    if (seg.type !== "silence") continue
    if (seg.end <= vs || seg.start >= vs + vd) continue

    const clampStart = Math.max(seg.start, vs)
    const clampEnd = Math.min(seg.end, vs + vd)
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
    resizeObserver = new ResizeObserver(() => draw())
    resizeObserver.observe(canvas)
    draw()
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

// -- Watchers ------------------------------------------------------------

watch(() => props.waveformPath, (path) => {
  if (path) {
    loadWaveform(path)
  }
}, { immediate: true })

watch([metrics.viewStart, metrics.viewDuration, peaks, () => props.segments], () => {
  draw()
})
</script>

<template>
  <div class="absolute inset-0">
    <canvas ref="canvasRef" class="h-full w-full" />
  </div>
</template>

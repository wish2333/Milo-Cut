/**
 * Waveform peaks JSON parsing (v3.0.0 M11-3).
 *
 * Accepts both on-disk shapes:
 * - legacy bare array: ``[{min, max}, ...]`` (project-dir waveform.json)
 * - sidecar envelope:  ``{version, media_signature, peaks: [{min, max}, ...]}``
 *   (``<媒体名>.peaks.json``, M11-3 cache sidecar)
 *
 * Returns the peaks array, or null when the payload is not a recognizable
 * peaks document (caller shows the load-error state).
 */
export interface WaveformPeak {
  min: number
  max: number
}

export function parseWaveformPeaks(data: unknown): WaveformPeak[] | null {
  const peaks = Array.isArray(data)
    ? data
    : data !== null && typeof data === "object" && Array.isArray((data as { peaks?: unknown }).peaks)
      ? (data as { peaks: unknown[] }).peaks
      : null
  if (!peaks || peaks.length === 0) return null
  const first = peaks[0]
  if (first === null || typeof first !== "object" || !("min" in first) || !("max" in first)) {
    return null
  }
  return peaks as WaveformPeak[]
}

// -- v3.0.2 M4-3 (P2-4): visible-window slice extraction ------------------

/**
 * The visible bucket window for a view range, extracted verbatim from
 * WaveformCanvas.drawWaveform (zero behavior change -- same floor/ceil
 * bucket math and the same bps fallback when duration is unknown).
 * Memoizable by {rowIndex, widthPx, dpr} at the row layer.
 */
export interface PeakSlice {
  /** First bucket index to draw (inclusive). */
  startBucket: number
  /** End bucket index (exclusive, clamped to peaks.length). */
  endBucket: number
  /** Buckets per second used for the mapping (fallback derived from the window). */
  bucketsPerSecond: number
}

export function computePeakSlice(
  peaks: WaveformPeak[],
  viewStart: number,
  viewEnd: number,
  duration: number,
): PeakSlice | null {
  // NOTE: a `widthPx` parameter is reserved for width-based decimation
  // (MAW mipmap-style); the current pipeline draws every visible bucket,
  // so width does not slice yet -- the signature stays 4-arg until then.
  const totalBuckets = peaks.length
  if (totalBuckets === 0) return null
  const vd = viewEnd - viewStart
  if (!(vd > 0)) return null
  const bucketsPerSecond = duration > 0 ? totalBuckets / duration : totalBuckets / (viewStart + vd)
  const startBucket = Math.floor(viewStart * bucketsPerSecond)
  const endBucket = Math.min(Math.ceil(viewEnd * bucketsPerSecond), totalBuckets)
  if (endBucket - startBucket <= 0) return null
  return { startBucket, endBucket, bucketsPerSecond }
}

/** Effective DPR for row canvas work, capped at 2 (M4-3 裁决). */
export function clampDpr(dpr: number): number {
  return Math.min(2, Math.max(1, dpr || 1))
}

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

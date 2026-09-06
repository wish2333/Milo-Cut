import { describe, expect, it } from "vitest"
import { clampDpr, computePeakSlice, parseWaveformPeaks } from "@/utils/waveformPeaks"

const PEAKS = [
  { min: -0.5, max: 0.5 },
  { min: -0.2, max: 0.9 },
]

describe("parseWaveformPeaks", () => {
  it("accepts the legacy bare-array shape", () => {
    expect(parseWaveformPeaks(PEAKS)).toEqual(PEAKS)
  })

  it("accepts the M11-3 sidecar envelope shape", () => {
    const sidecar = {
      version: 1,
      media_signature: { size: 1024, mtime_ms: 1756600000000 },
      peaks: PEAKS,
    }
    expect(parseWaveformPeaks(sidecar)).toEqual(PEAKS)
  })

  it("rejects empty and malformed payloads", () => {
    expect(parseWaveformPeaks([])).toBeNull()
    expect(parseWaveformPeaks({ peaks: [] })).toBeNull()
    expect(parseWaveformPeaks(null)).toBeNull()
    expect(parseWaveformPeaks("nope")).toBeNull()
    expect(parseWaveformPeaks([{ wrong: 1 }])).toBeNull()
    expect(parseWaveformPeaks({ version: 1 })).toBeNull()
  })
})

// v3.0.2 M4-3 (P2-4): computePeakSlice -- extracted verbatim from
// WaveformCanvas.drawWaveform, so the numbers below double as the
// behavior-preservation anchor for the refactor.

describe("computePeakSlice", () => {
  // 10 peaks over 10s -> 1 bucket/second.
  const peaks = Array.from({ length: 10 }, (_, i) => ({
    min: -0.1 - i / 100,
    max: 0.1 + i / 100,
  }))

  it("maps the view window to the bucket range (1 bps)", () => {
    const slice = computePeakSlice(peaks, 2, 5, 10)
    expect(slice).not.toBeNull()
    expect(slice!.startBucket).toBe(2) // floor(2 * 1)
    expect(slice!.endBucket).toBe(5) // ceil(5 * 1)
    expect(slice!.bucketsPerSecond).toBe(1)
  })

  it("fractional windows floor/ceil like the original draw math", () => {
    const slice = computePeakSlice(peaks, 2.2, 4.7, 10)
    expect(slice!.startBucket).toBe(2)
    expect(slice!.endBucket).toBe(5)
  })

  it("falls back to window-derived bps when duration is unknown (0)", () => {
    const slice = computePeakSlice(peaks, 0, 5, 0)
    // legacy fallback: totalBuckets / (vs + vd) = 10 / 5 = 2
    expect(slice!.bucketsPerSecond).toBe(2)
    expect(slice!.startBucket).toBe(0)
    expect(slice!.endBucket).toBe(10) // clamped to peaks.length
  })

  it("clamps the end bucket to the peaks array length", () => {
    const slice = computePeakSlice(peaks, 9, 15, 10)
    expect(slice!.startBucket).toBe(9)
    expect(slice!.endBucket).toBe(10)
  })

  it("degenerate inputs return null", () => {
    expect(computePeakSlice([], 0, 5, 10)).toBeNull()
    expect(computePeakSlice(peaks, 3, 3, 10)).toBeNull() // empty window
    expect(computePeakSlice(peaks, 5, 2, 10)).toBeNull() // inverted
  })

  it("high-bps sidecar (6000 buckets over 60s) slices a 10s row correctly", () => {
    const dense = Array.from({ length: 6000 }, () => ({ min: -0.1, max: 0.1 }))
    const slice = computePeakSlice(dense, 10, 20, 60)
    expect(slice!.bucketsPerSecond).toBeCloseTo(100)
    expect(slice!.startBucket).toBe(1000)
    expect(slice!.endBucket).toBe(2000)
  })
})

describe("clampDpr (M4-3 dpr cap 2)", () => {
  it("caps at 2 and floors at 1, tolerating junk", () => {
    expect(clampDpr(1)).toBe(1)
    expect(clampDpr(2)).toBe(2)
    expect(clampDpr(3)).toBe(2)
    expect(clampDpr(0.5)).toBe(1)
    expect(clampDpr(0)).toBe(1)
    expect(clampDpr(Number.NaN)).toBe(1)
  })
})

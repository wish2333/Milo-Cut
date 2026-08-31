import { describe, expect, it } from "vitest"
import { parseWaveformPeaks } from "@/utils/waveformPeaks"

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

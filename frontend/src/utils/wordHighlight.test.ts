import { describe, it, expect } from "vitest"
import { findWordIndexAtTime } from "@/utils/wordHighlight"
import type { Word } from "@/types/project"

function words(...tokens: [string, number, number][]): Word[] {
  return tokens.map(([word, start, end]) => ({ word, start, end, confidence: 1 }))
}

// Gap between 家(end 1.8) and 好(start 2.0).
const SAMPLE = words(
  ["大", 1.0, 1.4],
  ["家", 1.4, 1.8],
  ["好", 2.0, 2.5],
)

describe("findWordIndexAtTime", () => {
  it("hits the word containing the time", () => {
    expect(findWordIndexAtTime(SAMPLE, 1.2)).toBe(0)
    expect(findWordIndexAtTime(SAMPLE, 1.6)).toBe(1)
    expect(findWordIndexAtTime(SAMPLE, 2.3)).toBe(2)
  })

  it("start boundary is inclusive, end boundary is exclusive", () => {
    expect(findWordIndexAtTime(SAMPLE, 1.0)).toBe(0)
    expect(findWordIndexAtTime(SAMPLE, 1.4)).toBe(1)
    expect(findWordIndexAtTime(SAMPLE, 1.8)).toBe(-1) // end == next.start gap edge
    expect(findWordIndexAtTime(SAMPLE, 2.0)).toBe(2)
    expect(findWordIndexAtTime(SAMPLE, 2.5)).toBe(-1)
  })

  it("returns -1 in gaps, before first and after last word", () => {
    expect(findWordIndexAtTime(SAMPLE, 1.9)).toBe(-1)
    expect(findWordIndexAtTime(SAMPLE, 0.9)).toBe(-1)
    expect(findWordIndexAtTime(SAMPLE, 3.0)).toBe(-1)
  })

  it("handles empty and single-word lists", () => {
    expect(findWordIndexAtTime([], 1.0)).toBe(-1)
    expect(findWordIndexAtTime(words(["好", 1.0, 2.0]), 1.5)).toBe(0)
    expect(findWordIndexAtTime(words(["好", 1.0, 2.0]), 2.0)).toBe(-1)
  })

  it("never matches zero-width synthesized words", () => {
    const withSynth = [
      ...SAMPLE,
      { word: "啊", start: 2.5, end: 2.5, confidence: 0 },
    ]
    expect(findWordIndexAtTime(withSynth, 2.5)).toBe(-1)
  })

  it("stays accurate on a large word list (binary search)", () => {
    const large: Word[] = []
    for (let i = 0; i < 10000; i++) {
      large.push({ word: `w${i}`, start: i * 0.5, end: i * 0.5 + 0.4, confidence: 1 })
    }
    expect(findWordIndexAtTime(large, 0)).toBe(0)
    expect(findWordIndexAtTime(large, 2500 * 0.5 + 0.2)).toBe(2500)
    expect(findWordIndexAtTime(large, 9999 * 0.5)).toBe(9999)
    expect(findWordIndexAtTime(large, 10000 * 0.5)).toBe(-1)
  })
})

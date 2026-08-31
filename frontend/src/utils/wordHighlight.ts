import type { Word } from "@/types/project"

/**
 * Binary-search the word containing ``time`` (v3.0.0 P4-1 word highlight).
 *
 * Returns the index of the word with ``start <= time < end``, or -1 when the
 * time falls before the first word, after the last one, or in a gap between
 * words. Zero-width words (synthesized by correction reattachment) never
 * match. ``words`` must be ordered by ``start`` (ASR output and merge/split
 * maintenance guarantee this).
 */
export function findWordIndexAtTime(words: Word[], time: number): number {
  if (!words.length) return -1
  let lo = 0
  let hi = words.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (words[mid].start <= time) {
      ans = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  if (ans >= 0 && time < words[ans].end) return ans
  return -1
}

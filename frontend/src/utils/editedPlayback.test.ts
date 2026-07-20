import { describe, expect, it, vi } from "vitest"
import {
  createEditedPlaybackController,
  buildSubtitleIndex,
  findSubtitleAtTime,
  normalizeDeleteRanges,
  type PlaybackVideo,
} from "./editedPlayback"

function video(overrides: Partial<PlaybackVideo> = {}): PlaybackVideo {
  return {
    currentTime: 0,
    paused: false,
    play: vi.fn(),
    ...overrides,
  }
}

describe("normalizeDeleteRanges", () => {
  it("filters invalid ranges, sorts, and merges overlap without deleting gaps", () => {
    expect(normalizeDeleteRanges([
      { start: 8, end: 10 },
      { start: 2, end: 5 },
      { start: 4, end: 7 },
      { start: 5.01, end: 5.02 },
      { start: 9, end: 8 },
      { start: -2, end: -1 },
    ])).toEqual([
      { start: 2, end: 7 },
      { start: 8, end: 10 },
    ])
  })

  it("merges exactly adjacent ranges but preserves a real keep gap", () => {
    expect(normalizeDeleteRanges([
      { start: 0, end: 1 },
      { start: 1, end: 2 },
      { start: 2.001, end: 3 },
    ])).toEqual([
      { start: 0, end: 2 },
      { start: 2.001, end: 3 },
    ])
  })
})

describe("findSubtitleAtTime", () => {
  const segments = [
    { id: "s1", type: "subtitle" as const, start: 0, end: 1, text: "one" },
    { id: "sil", type: "silence" as const, start: 1, end: 2, text: "" },
    { id: "s2", type: "subtitle" as const, start: 2, end: 3, text: "two" },
  ]

  it("searches a subtitle-only index instead of skipping over silence", () => {
    const subtitleIndex = buildSubtitleIndex(segments)
    expect(findSubtitleAtTime(subtitleIndex, 0.5)?.id).toBe("s1")
    expect(findSubtitleAtTime(subtitleIndex, 2.5)?.id).toBe("s2")
    expect(findSubtitleAtTime(subtitleIndex, 1.5)).toBeUndefined()
  })
})

describe("createEditedPlaybackController", () => {
  it("skips a normalized delete range once and does not re-enter on seeked", () => {
    const currentVideo = video({ currentTime: 2 })
    const onTimeUpdate = vi.fn()
    const requestFrame = vi.fn(() => 1)
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([
        { start: 1, end: 3 },
        { start: 3, end: 4 },
      ]),
      onTimeUpdate,
      requestFrame,
      cancelFrame: vi.fn(),
    })

    controller.animationLoop()

    expect(currentVideo.currentTime).toBe(4)
    expect(onTimeUpdate).not.toHaveBeenCalled()

    controller.handleSeeked()

    expect(currentVideo.currentTime).toBe(4)
    expect(onTimeUpdate).toHaveBeenCalledWith(4)
  })

  it("does not schedule RAF while paused", () => {
    const currentVideo = video({ paused: true })
    const requestFrame = vi.fn(() => 1)
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => true,
      getRanges: () => [],
      onTimeUpdate: vi.fn(),
      requestFrame,
      cancelFrame: vi.fn(),
    })

    controller.sync()

    expect(requestFrame).not.toHaveBeenCalled()
  })

  it("cancels a pending programmatic seek when the user seeks again", () => {
    const currentVideo = video({ currentTime: 2 })
    const onTimeUpdate = vi.fn()
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([{ start: 1, end: 3 }]),
      onTimeUpdate,
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    controller.animationLoop()
    expect(currentVideo.currentTime).toBe(3)

    controller.seek(8)
    controller.handleSeeked()

    expect(currentVideo.currentTime).toBe(8)
    expect(onTimeUpdate).toHaveBeenLastCalledWith(8)
  })
})

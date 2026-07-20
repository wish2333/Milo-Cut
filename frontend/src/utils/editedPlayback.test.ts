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

  // v2.3.1 Bug D 回归测试：补齐 §4.5 约束 1 / 2 的边界覆盖

  it("treats range.start as inclusive and range.end as exclusive", () => {
    const currentVideo = video({ currentTime: 0 })
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([{ start: 5, end: 10 }]),
      onTimeUpdate: vi.fn(),
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    // start boundary: time === 5 is inside the delete range → skip
    currentVideo.currentTime = 5
    controller.animationLoop()
    expect(currentVideo.currentTime).toBe(10)

    // resolve the pending programmatic seek so subsequent loops run clean
    controller.handleSeeked()

    // end boundary: time === 10 is OUTSIDE [5,10) → no further skip
    currentVideo.currentTime = 10
    controller.animationLoop()
    expect(currentVideo.currentTime).toBe(10)
  })

  it("issues a single seek for adjacent ranges merged by normalizeDeleteRanges", () => {
    // Two raw ranges [1,3] and [3,5] touch at t=3 and must merge into [1,5].
    // A playhead entering at t=2 must skip directly to 5, not first to 3 then
    // to 5 (which would double the seeks and risk a seek storm per §4.4 热点 9).
    const seekLog: number[] = [2]
    const loggedVideo: PlaybackVideo = {
      get currentTime() { return seekLog[seekLog.length - 1] },
      set currentTime(value: number) { seekLog.push(value) },
      paused: false,
      play: vi.fn(),
    }
    const controller = createEditedPlaybackController({
      getVideo: () => loggedVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([
        { start: 1, end: 3 },
        { start: 3, end: 5 },
      ]),
      onTimeUpdate: vi.fn(),
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    controller.animationLoop() // detects skip, issues seek to 5
    controller.handleSeeked()  // resolves pendingSkip

    expect(seekLog[seekLog.length - 1]).toBe(5)
    // seekLog holds the initial value plus exactly one programmatic seek.
    expect(seekLog.length).toBe(2)
  })

  it("does not re-issue a skip while a programmatic seek is already pending", () => {
    // §4.5 约束 2: programmatic-skip source must suppress the next checkSkip
    // to avoid a seek storm when the video has not caught up to the target.
    const seekLog: number[] = [2]
    const loggedVideo: PlaybackVideo = {
      get currentTime() { return seekLog[seekLog.length - 1] },
      set currentTime(value: number) { seekLog.push(value) },
      paused: false,
      play: vi.fn(),
    }
    const controller = createEditedPlaybackController({
      getVideo: () => loggedVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([{ start: 1, end: 10 }]),
      onTimeUpdate: vi.fn(),
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    // First frame: detects skip, issues seek to 10, sets pendingSkip.
    controller.animationLoop()
    expect(seekLog.length).toBe(2) // initial + programmatic seek

    // Second frame BEFORE seeked fires: pendingSkip still active → no new seek.
    controller.animationLoop()
    expect(seekLog.length).toBe(2)

    // timeupdate arriving while pending: should be ignored (no publish, no skip).
    controller.handleTimeUpdate()
    expect(seekLog.length).toBe(2)
  })

  it("invalidatePendingSeek drops a stale programmatic seek", () => {
    // §4.5 约束 2: when deleteRanges change mid-skip, the in-flight seek
    // target may no longer be valid (the range could be gone). The composable
    // watches playbackRanges and calls invalidatePendingSeek; the subsequent
    // <seeked> event must not publish the stale target time.
    const currentVideo = video({ currentTime: 2 })
    const onTimeUpdate = vi.fn()
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => true,
      getRanges: () => normalizeDeleteRanges([{ start: 1, end: 10 }]),
      onTimeUpdate,
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    controller.animationLoop() // issues seek to 10
    expect(currentVideo.currentTime).toBe(10)

    // Simulate range change before browser fires <seeked>.
    controller.invalidatePendingSeek()

    // Browser eventually fires <seeked> with the (possibly partial) new time.
    currentVideo.currentTime = 4
    controller.handleSeeked()

    // Should not have published the stale "10" target; should re-evaluate
    // the current position (4) against whatever ranges are active.
    expect(onTimeUpdate).not.toHaveBeenCalledWith(10)
  })

  it("does not skip when isEdited is false (original mode)", () => {
    // Sanity check: previewMode === "original" must bypass checkSkip entirely
    // so users can scrub through the unedited video.
    const currentVideo = video({ currentTime: 2 })
    const controller = createEditedPlaybackController({
      getVideo: () => currentVideo,
      isEdited: () => false,
      getRanges: () => normalizeDeleteRanges([{ start: 1, end: 10 }]),
      onTimeUpdate: vi.fn(),
      requestFrame: vi.fn(() => 1),
      cancelFrame: vi.fn(),
    })

    controller.animationLoop()
    expect(currentVideo.currentTime).toBe(2) // unchanged
  })
})

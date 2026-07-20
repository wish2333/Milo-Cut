export interface TimeRange {
  start: number
  end: number
}

export interface PlaybackVideo {
  currentTime: number
  paused: boolean
  play?: () => Promise<void> | void
}

export interface TimedSegment {
  type: string
  start: number
  end: number
}

export interface EditedPlaybackOptions {
  getVideo: () => PlaybackVideo | null
  isEdited: () => boolean
  /** Must return normalized, sorted ranges. */
  getRanges: () => readonly TimeRange[]
  onTimeUpdate: (time: number) => void
  requestFrame?: (callback: FrameRequestCallback) => number
  cancelFrame?: (id: number) => void
}

export interface EditedPlaybackController {
  animationLoop: () => void
  handleTimeUpdate: () => void
  handleSeeked: () => void
  seek: (time: number, play?: boolean) => void
  sync: () => void
  stop: () => void
  invalidatePendingSeek: () => void
}

const TIME_EPSILON = 0.001

/**
 * Normalize ranges used by playback. UI overlays should continue to use the
 * raw edit ranges so that editing semantics and playback semantics stay
 * separate.
 */
export function normalizeDeleteRanges(
  ranges: readonly TimeRange[],
): TimeRange[] {
  const sorted = ranges
    .filter(range => Number.isFinite(range.start) && Number.isFinite(range.end))
    .map(range => ({
      start: Math.max(0, range.start),
      end: range.end,
    }))
    .filter(range => range.end > range.start)
    .sort((a, b) => a.start - b.start || a.end - b.end)

  const normalized: TimeRange[] = []
  for (const range of sorted) {
    const previous = normalized[normalized.length - 1]
    if (previous && range.start <= previous.end) {
      previous.end = Math.max(previous.end, range.end)
    } else {
      normalized.push({ ...range })
    }
  }
  return normalized
}

/** Return the last range whose start is <= time, then test containment. */
function findContainingRange(
  ranges: readonly TimeRange[],
  time: number,
): TimeRange | undefined {
  let lo = 0
  let hi = ranges.length - 1
  let candidate = -1

  while (lo <= hi) {
    const mid = (lo + hi) >>> 1
    if (ranges[mid].start <= time) {
      candidate = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }

  const range = candidate >= 0 ? ranges[candidate] : undefined
  return range && time < range.end ? range : undefined
}

/**
 * Build/search a subtitle-only timeline. The input may contain silence
 * segments; binary search must never run over that mixed array.
 */
export function findSubtitleAtTime<T extends TimedSegment>(
  subtitleSegments: readonly T[],
  time: number,
): T | undefined {
  let lo = 0
  let hi = subtitleSegments.length - 1
  let candidate = -1
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1
    if (subtitleSegments[mid].start <= time) {
      candidate = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }

  if (candidate < 0) return undefined
  if (time <= subtitleSegments[candidate].end) return subtitleSegments[candidate]

  // Normal subtitle timelines do not overlap. This short fallback preserves
  // correctness for manually overlapping subtitles without making the common
  // path linear.
  for (let i = candidate - 1; i >= 0; i--) {
    const segment = subtitleSegments[i]
    if (segment.start > time) continue
    if (time <= segment.end) return segment
  }
  return undefined
}

export function buildSubtitleIndex<T extends TimedSegment>(
  segments: readonly T[],
): T[] {
  return segments
    .filter(segment => segment.type === "subtitle")
    .sort((a, b) => a.start - b.start)
}

export function createEditedPlaybackController(
  options: EditedPlaybackOptions,
): EditedPlaybackController {
  const requestFrame = options.requestFrame ?? ((callback: FrameRequestCallback) =>
    requestAnimationFrame(callback))
  const cancelFrame = options.cancelFrame ?? ((id: number) => cancelAnimationFrame(id))

  let frameId: number | null = null
  let pendingSkip: { generation: number; target: number } | null = null
  let generation = 0

  function isPlaying(): boolean {
    const video = options.getVideo()
    return Boolean(video && !video.paused)
  }

  function shouldRun(): boolean {
    return options.isEdited() && isPlaying()
  }

  function publish(time: number): void {
    options.onTimeUpdate(time)
  }

  function issueSkip(target: number): void {
    const video = options.getVideo()
    if (!video) return
    generation += 1
    pendingSkip = { generation, target }
    video.currentTime = target
  }

  function checkSkip(time: number): boolean {
    if (!options.isEdited() || !isPlaying() || pendingSkip) return false
    const range = findContainingRange(options.getRanges(), time)
    if (!range) return false
    issueSkip(range.end)
    return true
  }

  function start(): void {
    if (frameId === null && shouldRun()) {
      frameId = requestFrame(animationLoop)
    }
  }

  function stop(): void {
    if (frameId !== null) {
      cancelFrame(frameId)
      frameId = null
    }
  }

  function animationLoop(): void {
    frameId = null
    const video = options.getVideo()
    if (video && !video.paused && options.isEdited()) {
      const time = video.currentTime
      if (!pendingSkip && !checkSkip(time)) {
        publish(time)
      }
    }
    start()
  }

  function handleTimeUpdate(): void {
    const video = options.getVideo()
    if (!video) return
    if (pendingSkip) return
    if (video.paused || !options.isEdited()) {
      publish(video.currentTime)
      return
    }
    if (!checkSkip(video.currentTime)) {
      publish(video.currentTime)
    }
  }

  function handleSeeked(): void {
    const video = options.getVideo()
    if (!video) return

    const pending = pendingSkip
    if (pending && pending.generation === generation) {
      const target = pending.target
      const reachedTarget = Math.abs(video.currentTime - target) <= TIME_EPSILON
      pendingSkip = null
      if (reachedTarget) {
        publish(video.currentTime)
        return
      }
      // A user seek superseded the programmatic seek. Continue processing the
      // actual position below instead of trusting the stale target.
    } else if (pending) {
      // A newer user seek or range update invalidated this native event.
      pendingSkip = null
    }

    if (!checkSkip(video.currentTime)) {
      publish(video.currentTime)
    }
  }

  function seek(time: number, play = false): void {
    const video = options.getVideo()
    if (!video) return
    generation += 1
    pendingSkip = null
    video.currentTime = time
    if (play && video.play) {
      void Promise.resolve(video.play()).catch(() => undefined)
    }
  }

  function sync(): void {
    if (!options.isEdited()) pendingSkip = null
    if (shouldRun()) start()
    else stop()
  }

  function invalidatePendingSeek(): void {
    generation += 1
    pendingSkip = null
  }

  return {
    animationLoop,
    handleTimeUpdate,
    handleSeeked,
    seek,
    sync,
    stop,
    invalidatePendingSeek,
  }
}

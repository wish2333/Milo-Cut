import type { InjectionKey } from "vue"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import type { PlaybackClock } from "@/composables/usePlaybackClock"

export const TIMELINE_METRICS_KEY: InjectionKey<TimelineMetrics> = Symbol("timeline-metrics")
export const PLAYBACK_CLOCK_KEY: InjectionKey<PlaybackClock> = Symbol("playback-clock")

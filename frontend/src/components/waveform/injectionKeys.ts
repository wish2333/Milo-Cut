import type { InjectionKey } from "vue"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

export const TIMELINE_METRICS_KEY: InjectionKey<TimelineMetrics> = Symbol("timeline-metrics")

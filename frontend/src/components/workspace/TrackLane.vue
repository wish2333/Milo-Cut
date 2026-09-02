<script setup lang="ts">
import { computed, inject } from "vue"
import type { SubtitleTrack } from "@/types/project"
import type { LaneLayoutItem } from "@/composables/useLaneLayout"
import { TIMELINE_METRICS_KEY } from "@/components/waveform/injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"
import SegmentBlock from "@/components/waveform/SegmentBlock.vue"

/**
 * v3.0.1 M4-2: geometric extension-track lane for the stacked timeline
 * (replaces the v3.0.0 read-only text list). Renders the track's segments
 * as percent-positioned SegmentBlocks sharing the timeline metrics with
 * the main track (same zoom/scroll). Positioned by the parent stack via
 * the `lane` layout item. v3.0.2 M1-1: `updateTime` is now forwarded to
 * SegmentBlock (v3.0.1 M5-2 reserved semantics) -- extension blocks become
 * trim-editable when the parent provides it; undefined keeps trim disabled
 * for read-only reuse.
 */
const props = defineProps<{
  track: SubtitleTrack
  lane: LaneLayoutItem
  /** v3.0.1 M5-2: when provided, extension blocks become trim-editable. */
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
}>()

const emit = defineEmits<{
  seek: [time: number]
  "toggle-collapse": [trackId: string]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const visibleSegments = computed(() => {
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return []
  return props.track.segments
    .filter(seg => seg.end > vs && seg.start < ve)
    .map(seg => {
      const clampStart = Math.max(seg.start, vs)
      const clampEnd = Math.min(seg.end, ve)
      return {
        seg,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
      }
    })
})
</script>

<template>
  <div
    class="absolute inset-x-0 border-t border-hairline bg-surface-tile-1/60"
    :style="{ top: lane.top + 'px', height: lane.height + 'px' }"
    data-test="track-lane"
  >
    <!-- Floating title strip (track identity + collapse) -->
    <div
      class="absolute left-1 top-0.5 flex items-center gap-1.5 rounded bg-surface px-1 py-px text-[10px] leading-none text-ink-muted shadow-sm"
      style="z-index: 1"
    >
      <button
        class="flex items-center hover:text-ink"
        :title="lane.collapsed ? '展开副轨' : '收起副轨'"
        data-test="lane-collapse"
        @click.stop="emit('toggle-collapse', track.id)"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg" class="h-2.5 w-2.5 transition-transform"
          :class="lane.collapsed ? '' : 'rotate-90'" fill="none" viewBox="0 0 24 24"
          stroke="currentColor" stroke-width="2.5"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <span class="font-semibold rounded bg-primary-soft px-1 py-px text-primary">
        {{ track.name || track.id }}{{ track.language ? ` · ${track.language}` : '' }}
      </span>
      <span>{{ track.segments.length }} 段</span>
      <span v-if="lane.collapsed" class="text-ink-muted/60">已折叠</span>
    </div>

    <!-- Block area (hidden while collapsed) -->
    <div
      v-if="!lane.collapsed"
      class="absolute inset-x-0 bottom-0 top-4"
      data-test="lane-blocks"
    >
      <SegmentBlock
        v-for="item in visibleSegments"
        :key="item.seg.id"
        :seg="item.seg"
        :left-percent="item.leftPercent"
        :width-percent="item.widthPercent"
        :segments="track.segments"
        track-kind="extension"
        :title="item.seg.text"
        :update-time="updateTime"
        @seek-segment="emit('seek', item.seg.start)"
      />
      <p
        v-if="track.segments.length === 0"
        class="absolute inset-0 flex items-center justify-center text-[10px] text-ink-muted"
        data-test="lane-empty"
      >
        空轨道
      </p>
    </div>
  </div>
</template>

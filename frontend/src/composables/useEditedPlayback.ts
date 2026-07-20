import { computed, onUnmounted, watch, type Ref } from "vue"
import {
  createEditedPlaybackController,
  normalizeDeleteRanges,
  type EditedPlaybackController,
  type PlaybackVideo,
  type TimeRange,
} from "@/utils/editedPlayback"

export function useEditedPlayback(options: {
  videoRef: Ref<PlaybackVideo | null>
  previewMode: Ref<"edited" | "original">
  paused: Ref<boolean>
  rawDeleteRanges: Ref<readonly TimeRange[]>
  onTimeUpdate: (time: number) => void
}): EditedPlaybackController & { playbackRanges: Readonly<Ref<TimeRange[]>> } {
  const playbackRanges = computed(() => normalizeDeleteRanges(options.rawDeleteRanges.value))
  const controller = createEditedPlaybackController({
    getVideo: () => options.videoRef.value,
    isEdited: () => options.previewMode.value === "edited",
    getRanges: () => playbackRanges.value,
    onTimeUpdate: options.onTimeUpdate,
  })

  watch([options.previewMode, options.paused], controller.sync, { immediate: true })
  watch(playbackRanges, controller.invalidatePendingSeek)
  onUnmounted(controller.stop)

  return { ...controller, playbackRanges }
}

<script setup lang="ts">
/**
 * Silence detection settings popover (v3.0.0 M8-2a, moved verbatim from
 * WorkspacePage.vue toolbar). Positioning/visibility stays controlled by
 * the parent (`v-if` + relative anchor). Threshold state flows in via
 * named v-models; the save action bubbles up (parent persists and closes).
 */
const emit = defineEmits<{
  save: []
}>()

const threshold = defineModel<number>("threshold", { required: true })
const minDuration = defineModel<number>("minDuration", { required: true })
const margin = defineModel<number>("margin", { required: true })
const subtitlePadding = defineModel<number>("subtitlePadding", { required: true })
const trimSubtitles = defineModel<boolean>("trimSubtitles", { required: true })
</script>

<template>
  <div
    class="absolute top-full left-0 mt-1 w-64 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
  >
    <div class="mb-2 text-xs font-semibold text-ink">静音检测设置</div>
    <label class="block mb-2">
      <span class="text-xs text-gray-500">Threshold (dB): {{ threshold }}</span>
      <input
        type="range"
        v-model.number="threshold"
        min="-60"
        max="-10"
        step="1"
        class="w-full mt-1"
      />
    </label>
    <label class="block mb-3">
      <span class="text-xs text-gray-500">Min Duration (s): {{ minDuration.toFixed(2) }}</span>
      <input
        type="range"
        v-model.number="minDuration"
        min="0.05"
        max="2.0"
        step="0.05"
        class="w-full mt-1"
      />
      <p v-if="minDuration < 0.2" class="text-xs text-amber-600 mt-1">
        Very short durations (&lt;0.2s) may generate many clips and affect performance.
      </p>
    </label>
    <label class="block mb-2">
      <span class="text-xs text-gray-500">
        Margin (s): {{ margin.toFixed(2) }}
      </span>
      <input
        type="range"
        v-model.number="margin"
        min="0"
        max="0.5"
        step="0.01"
        class="w-full mt-1"
      />
      <p v-if="margin > 0 && margin * 2 >= minDuration"
         class="text-xs text-amber-600 mt-1">
        High margin may consume small silence intervals entirely.
      </p>
    </label>
    <label class="block mb-2">
      <span class="text-xs text-gray-500">
        Subtitle Padding (s): {{ subtitlePadding.toFixed(2) }}
      </span>
      <input
        type="range"
        v-model.number="subtitlePadding"
        min="0"
        max="1.0"
        step="0.05"
        class="w-full mt-1"
      />
      <p v-if="subtitlePadding > 0" class="text-xs text-gray-400 mt-0.5">
        Silence ranges will be trimmed to stay this far from subtitles.
      </p>
    </label>
    <label class="flex items-center gap-2 mb-3 cursor-pointer">
      <input
        type="checkbox"
        v-model="trimSubtitles"
        class="rounded border-gray-300"
      />
      <span class="text-xs text-gray-500">Trim overlapping subtitles</span>
    </label>
    <button
      class="mc-button mc-button-primary w-full px-2 text-xs"
      @click="emit('save')"
    >
     保存设置
    </button>
  </div>
</template>

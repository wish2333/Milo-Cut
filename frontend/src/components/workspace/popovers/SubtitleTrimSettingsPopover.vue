<script setup lang="ts">
/**
 * Subtitle trim settings popover (v3.0.0 M8-2a, moved verbatim from
 * WorkspacePage.vue toolbar). Positioning/visibility stays controlled by
 * the parent (`v-if` + relative anchor).
 */
const padding = defineModel<number>("padding", { required: true })
</script>

<template>
  <div
    class="absolute top-full left-0 mt-1 w-56 rounded-md border border-gray-200 bg-white shadow-lg z-20 p-3"
  >
    <div class="mb-2 text-xs font-semibold text-ink">字幕间隙设置</div>
    <label class="block mb-3">
      <span class="text-xs text-gray-500">Padding (s): {{ padding.toFixed(2) }}</span>
      <input
        type="range"
        v-model.number="padding"
        min="0"
        max="2.0"
        step="0.05"
        class="w-full mt-1"
      />
    </label>
  </div>
</template>

<script setup lang="ts">
// v2.3.2 G6 fix: extracted from VideoControls.vue so that `currentTime`
// updates on the parent no longer re-evaluate the v-for + dynamic style
// bindings of every delete range. This child only re-renders when its own
// props (`ranges` / `duration`) change. See docs/2.3.0/2.3.2-fix-report.md G6.

interface DeleteRange {
  start: number
  end: number
}

defineProps<{
  ranges: DeleteRange[]
  duration: number
}>()
</script>

<template>
  <div
    v-for="(range, i) in ranges"
    :key="`${range.start}-${range.end}-${i}`"
    class="absolute top-0 h-full bg-red-500/30 pointer-events-none"
    :style="{
      left: duration > 0 ? (range.start / duration) * 100 + '%' : '0%',
      width: duration > 0 ? ((range.end - range.start) / duration) * 100 + '%' : '0%',
    }"
  />
</template>

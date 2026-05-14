<script setup lang="ts">
interface Props {
  percent: number
  message?: string
}

defineProps<Props>()
</script>

<template>
  <div class="w-full">
    <div class="h-1.5 w-full overflow-hidden rounded-full bg-parchment">
      <div
        class="h-full rounded-full bg-primary transition-all duration-300 ease-in-out"
        :style="{ width: `${Math.min(100, Math.max(0, percent))}%` }"
      />
    </div>
    <p v-if="message" class="mt-1 text-xs text-ink-muted">{{ message }}</p>
  </div>
</template>

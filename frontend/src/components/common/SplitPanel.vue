<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from "vue"

/**
 * Resizable two-pane horizontal split.
 *
 * - Left pane width is a ratio of the container (0..1), clamped to
 *   [minRatio, maxRatio].
 * - The ratio persists across sessions via localStorage when `storageKey` is set.
 * - Drag the divider with the mouse (pointer events) to resize.
 */

const props = withDefaults(
  defineProps<{
    /** Minimum left-pane ratio (0..1). Default 0.3. */
    minRatio?: number
    /** Maximum left-pane ratio (0..1). Default 0.7. */
    maxRatio?: number
    /** localStorage key for persisting the ratio. Omit to disable persistence. */
    storageKey?: string
  }>(),
  {
    minRatio: 0.3,
    maxRatio: 0.7,
    storageKey: "",
  },
)

const containerRef = ref<HTMLDivElement | null>(null)
const ratio = ref<number>(0.4) // left-pane ratio
const isDragging = ref(false)

// Restore the persisted ratio synchronously so the first render uses the
// correct value (avoids a flash of the default ratio on mount).
loadPersisted()

const clampedRatio = computed(() => {
  const r = ratio.value
  if (r < props.minRatio) return props.minRatio
  if (r > props.maxRatio) return props.maxRatio
  return r
})

const leftStyle = computed(() => ({
  width: `${clampedRatio.value * 100}%`,
}))
const rightStyle = computed(() => ({
  width: `${(1 - clampedRatio.value) * 100}%`,
}))

function clamp(value: number): number {
  if (value < props.minRatio) return props.minRatio
  if (value > props.maxRatio) return props.maxRatio
  return value
}

function loadPersisted() {
  if (!props.storageKey) return
  try {
    const raw = localStorage.getItem(props.storageKey)
    if (raw !== null) {
      const parsed = Number.parseFloat(raw)
      if (Number.isFinite(parsed)) {
        ratio.value = clamp(parsed)
      }
    }
  } catch {
    // localStorage may be unavailable (private mode); ignore.
  }
}

function persist() {
  if (!props.storageKey) return
  try {
    localStorage.setItem(props.storageKey, String(clampedRatio.value))
  } catch {
    // Ignore write failures.
  }
}

function onPointerMove(e: PointerEvent) {
  if (!isDragging.value || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  if (rect.width === 0) return
  const newRatio = (e.clientX - rect.left) / rect.width
  ratio.value = clamp(newRatio)
}

function onPointerUp() {
  if (!isDragging.value) return
  isDragging.value = false
  document.body.style.cursor = ""
  document.body.style.userSelect = ""
  persist()
}

function startDrag(e: PointerEvent) {
  e.preventDefault()
  isDragging.value = true
  document.body.style.cursor = "col-resize"
  document.body.style.userSelect = "none"
}

onMounted(() => {
  window.addEventListener("pointermove", onPointerMove)
  window.addEventListener("pointerup", onPointerUp)
})

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", onPointerMove)
  window.removeEventListener("pointerup", onPointerUp)
  // Defensive: clear any lingering body styles.
  document.body.style.cursor = ""
  document.body.style.userSelect = ""
})

defineExpose({ ratio: clampedRatio })
</script>

<template>
  <div ref="containerRef" class="flex h-full w-full overflow-hidden">
    <div class="h-full min-w-0 overflow-hidden" :style="leftStyle">
      <slot name="left" />
    </div>

    <!-- Divider -->
    <div
      class="group relative w-px shrink-0 cursor-col-resize bg-gray-200 transition-colors hover:bg-blue-400"
      @pointerdown="startDrag"
    >
      <!-- Wider invisible hit area centered on the 1px line -->
      <div class="absolute inset-y-0 -left-1.5 -right-1.5 z-10"></div>
      <!-- Visible grab handle, appears on hover/drag -->
      <div
        class="absolute top-1/2 left-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full transition-colors"
        :class="isDragging ? 'bg-blue-500' : 'bg-transparent group-hover:bg-blue-300'"
      ></div>
    </div>

    <div class="h-full min-w-0 flex-1 overflow-hidden" :style="rightStyle">
      <slot name="right" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue"
import { call } from "@/bridge"

interface Emits {
  (e: "files-selected", paths: string[]): void
}

const emit = defineEmits<Emits>()

const isDragging = ref(false)
const isProcessing = ref(false)

async function handleDrop() {
  isDragging.value = false
  isProcessing.value = true
  try {
    const res = await call<string[]>("get_dropped_files")
    if (res.success && res.data && res.data.length > 0) {
      emit("files-selected", res.data)
    }
  } finally {
    isProcessing.value = false
  }
}

async function openFileDialog() {
  isProcessing.value = true
  try {
    const res = await call<string[]>("select_files")
    if (res.success && res.data && res.data.length > 0) {
      emit("files-selected", res.data)
    }
  } finally {
    isProcessing.value = false
  }
}

function onDragOver() {
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}
</script>

<template>
  <div
    class="flex flex-col items-center justify-center gap-4 rounded-[var(--radius-apple-lg)] border-2 border-dashed p-12 transition-colors duration-200"
    :class="isDragging
      ? 'border-primary bg-primary/5'
      : 'border-hairline bg-parchment hover:border-primary/40'"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="handleDrop"
  >
    <div class="text-4xl text-ink-muted">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
      </svg>
    </div>
    <p class="text-base text-ink-muted">
      {{ isDragging ? "松开以导入视频" : "拖拽视频文件到此处" }}
    </p>
    <button
      class="rounded-[var(--radius-apple-pill)] bg-primary px-6 py-2.5 text-sm font-semibold text-white transition-transform active:scale-95"
      :disabled="isProcessing"
      @click="openFileDialog"
    >
      {{ isProcessing ? "处理中..." : "选择文件" }}
    </button>
    <p class="text-xs text-ink-muted-48">
      支持 MP4, MKV, AVI, MOV, WebM
    </p>
  </div>
</template>

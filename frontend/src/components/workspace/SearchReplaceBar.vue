<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"

const emit = defineEmits<{
  "search-replace": [query: string, replacement: string, scope: string]
}>()

const isVisible = ref(false)
const query = ref("")
const replacement = ref("")
const scope = ref("all")
const matchCount = ref(0)

function show() {
  isVisible.value = true
  query.value = ""
  replacement.value = ""
  matchCount.value = 0
}

function hide() {
  isVisible.value = false
}

function handleSearch() {
  if (!query.value) return
  emit("search-replace", query.value, replacement.value, scope.value)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === "f") {
    e.preventDefault()
    show()
  }
  if (e.key === "Escape" && isVisible.value) {
    hide()
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener("keydown", handleKeydown)
})

defineExpose({ show, hide })
</script>

<template>
  <div
    v-if="isVisible"
    class="flex items-center gap-2 px-3 py-2 bg-white border-b border-gray-200 shadow-sm"
  >
    <input
      v-model="query"
      class="flex-1 px-2 py-1 text-sm border border-gray-300 rounded outline-none focus:border-blue-400"
      placeholder="搜索..."
      @keydown.enter="handleSearch"
    />
    <input
      v-model="replacement"
      class="flex-1 px-2 py-1 text-sm border border-gray-300 rounded outline-none focus:border-blue-400"
      placeholder="替换为..."
      @keydown.enter="handleSearch"
    />
    <select
      v-model="scope"
      class="text-sm px-2 py-1 border border-gray-300 rounded"
    >
      <option value="all">全部</option>
      <option value="selected">选中段</option>
    </select>
    <button
      class="text-sm px-3 py-1 rounded bg-blue-500 text-white hover:bg-blue-600"
      @click="handleSearch"
    >
      替换
    </button>
    <button
      class="text-sm px-2 py-1 text-gray-500 hover:text-gray-700"
      @click="hide"
    >
      x
    </button>
  </div>
</template>

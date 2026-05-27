<script setup lang="ts">
import { ref } from "vue"
import { call } from "@/bridge"

defineProps<{
  visible: boolean
  lostPath: string
}>()

const emit = defineEmits<{
  relink: [newPath: string]
  cancel: []
}>()

const selectedPath = ref<string | null>(null)
const error = ref("")

async function handleBrowse() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0) {
    selectedPath.value = res.data[0]
    error.value = ""
  }
}

function handleConfirm() {
  if (!selectedPath.value) {
    error.value = "请选择文件"
    return
  }
  emit("relink", selectedPath.value)
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('cancel')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-[480px] max-w-[90vw] overflow-hidden">
      <div class="px-6 pt-6 pb-4">
        <h2 class="text-lg font-semibold text-gray-800 text-center">媒体文件丢失</h2>
      </div>

      <div class="px-6 pb-4 space-y-3">
        <p class="text-sm text-gray-600">
          无法找到以下媒体文件:
        </p>
        <p class="text-sm text-red-600 bg-red-50 rounded px-3 py-2 break-all">
          {{ lostPath }}
        </p>
        <p class="text-sm text-gray-500">
          请选择文件的新位置，或取消关闭项目。
        </p>

        <div v-if="selectedPath" class="text-sm text-green-700 bg-green-50 rounded px-3 py-2 break-all">
          已选择: {{ selectedPath }}
        </div>

        <p v-if="error" class="text-sm text-red-600">{{ error }}</p>
      </div>

      <div class="flex flex-col gap-2 px-6 pb-6">
        <button
          class="w-full py-2.5 rounded-full bg-blue-500 text-white font-medium hover:bg-blue-600 transition-colors"
          @click="handleBrowse"
        >
          浏览文件...
        </button>
        <button
          class="w-full py-2.5 rounded-full bg-green-600 text-white font-medium hover:bg-green-700 transition-colors disabled:opacity-50"
          :disabled="!selectedPath"
          @click="handleConfirm"
        >
          确认重链接
        </button>
        <button
          class="w-full py-2.5 rounded-full border border-gray-300 text-gray-600 font-medium hover:bg-gray-50 transition-colors"
          @click="emit('cancel')"
        >
          取消
        </button>
      </div>
    </div>
  </div>
</template>

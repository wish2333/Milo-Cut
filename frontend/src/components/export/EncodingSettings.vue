<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { call } from "@/bridge"

const emit = defineEmits<{
  "update:settings": [settings: EncodingSettings]
}>()

interface EncodingSettings {
  outputFormat: string
  quality: number
  resolution: string
  videoCodec: string
  audioCodec: string
  audioBitrate: string
  preset: string
}

const advancedMode = ref(false)

// Basic mode settings
const outputFormat = ref("mp4")
const quality = ref(23)
const resolution = ref("original")

// Advanced mode settings
const videoCodec = ref("libx264")
const audioCodec = ref("aac")
const audioBitrate = ref("192k")
const preset = ref("medium")

// GPU detection
const hasNvidiaGpu = ref(false)

const videoCodecs = computed(() => {
  const base = [
    { value: "libx264", label: "H.264 (CPU)" },
    { value: "libx265", label: "H.265 (CPU)" },
  ]
  if (hasNvidiaGpu.value) {
    base.push({ value: "av1_nvenc", label: "AV1 (NVIDIA GPU)" })
  }
  return base
})

const resolutions = [
  { value: "original", label: "原始分辨率" },
  { value: "1920x1080", label: "1920x1080 (1080p)" },
  { value: "1280x720", label: "1280x720 (720p)" },
  { value: "854x480", label: "854x480 (480p)" },
]

const presets = [
  { value: "ultrafast", label: "Ultrafast" },
  { value: "superfast", label: "Superfast" },
  { value: "veryfast", label: "Veryfast" },
  { value: "faster", label: "Faster" },
  { value: "fast", label: "Fast" },
  { value: "medium", label: "Medium" },
  { value: "slow", label: "Slow" },
  { value: "slower", label: "Slower" },
  { value: "veryslow", label: "Veryslow" },
]

const audioBitrates = [
  { value: "128k", label: "128 kbps" },
  { value: "192k", label: "192 kbps" },
  { value: "256k", label: "256 kbps" },
  { value: "320k", label: "320 kbps" },
]

const qualityLabel = computed(() => {
  if (quality.value <= 20) return "高质量"
  if (quality.value <= 24) return "中等质量"
  if (quality.value <= 27) return "小文件"
  return "极小文件"
})

onMounted(async () => {
  // Detect GPU
  try {
    const res = await call<{ nvidia: boolean }>("detect_gpu")
    if (res.success && res.data) {
      hasNvidiaGpu.value = res.data.nvidia
    }
  } catch {
    // GPU detection failed, assume no NVIDIA GPU
  }
})

function updateSettings() {
  emit("update:settings", {
    outputFormat: outputFormat.value,
    quality: quality.value,
    resolution: resolution.value,
    videoCodec: videoCodec.value,
    audioCodec: audioCodec.value,
    audioBitrate: audioBitrate.value,
    preset: preset.value,
  })
}
</script>

<template>
  <div class="space-y-4">
    <!-- Basic mode -->
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">输出格式</label>
      <select
        v-model="outputFormat"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        @change="updateSettings"
      >
        <option value="mp4">MP4</option>
        <option value="webm">WebM</option>
        <option value="mov">MOV</option>
      </select>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">
        质量: {{ qualityLabel }} (CRF {{ quality }})
      </label>
      <input
        v-model.number="quality"
        type="range"
        min="18"
        max="32"
        class="w-full"
        @input="updateSettings"
      />
      <div class="flex justify-between text-xs text-gray-500 mt-1">
        <span>高质量</span>
        <span>小文件</span>
      </div>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">分辨率</label>
      <select
        v-model="resolution"
        class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        @change="updateSettings"
      >
        <option v-for="r in resolutions" :key="r.value" :value="r.value">
          {{ r.label }}
        </option>
      </select>
    </div>

    <!-- Advanced mode toggle -->
    <button
      class="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700"
      @click="advancedMode = !advancedMode"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="h-4 w-4 transition-transform"
        :class="{ 'rotate-90': advancedMode }"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        stroke-width="2"
      >
        <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
      </svg>
      高级设置
    </button>

    <!-- Advanced mode -->
    <div v-if="advancedMode" class="space-y-4 pl-4 border-l-2 border-gray-200">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">视频编码器</label>
        <select
          v-model="videoCodec"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          @change="updateSettings"
        >
          <option v-for="codec in videoCodecs" :key="codec.value" :value="codec.value">
            {{ codec.label }}
          </option>
        </select>
        <p v-if="!hasNvidiaGpu" class="text-xs text-gray-500 mt-1">
          未检测到 NVIDIA GPU，硬件编码不可用
        </p>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">音频编码器</label>
        <select
          v-model="audioCodec"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          @change="updateSettings"
        >
          <option value="aac">AAC</option>
          <option value="opus">Opus</option>
          <option value="mp3">MP3</option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">音频码率</label>
        <select
          v-model="audioBitrate"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          @change="updateSettings"
        >
          <option v-for="br in audioBitrates" :key="br.value" :value="br.value">
            {{ br.label }}
          </option>
        </select>
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">编码速度</label>
        <select
          v-model="preset"
          class="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
          @change="updateSettings"
        >
          <option v-for="p in presets" :key="p.value" :value="p.value">
            {{ p.label }}
          </option>
        </select>
        <p class="text-xs text-gray-500 mt-1">
          越慢的预设压缩率越高，文件越小
        </p>
      </div>
    </div>
  </div>
</template>

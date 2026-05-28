<script setup lang="ts">
import { ref, onMounted } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import type { PluginInfo, ModelInfo } from "@/types/project"
import { usePluginManager } from "@/composables/usePluginManager"

defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const settings = ref<AppSettings | null>(null)
const ffmpegInfo = ref<{ ffmpeg_path: string; ffprobe_path: string; version: string }>({ ffmpeg_path: "", ffprobe_path: "", version: "" })
const gpuEncoders = ref<string[]>([])
const saving = ref(false)
const statusMsg = ref("")

// Plugin manager
const pluginManager = usePluginManager()
const pluginList = ref<PluginInfo[]>([])
const modelList = ref<ModelInfo[]>([])
const installingPlugin = ref<string | null>(null)
const installProgress = ref(0)
const installMessage = ref("")

// GPU detection
const gpuInfo = ref<{
  has_nvidia_gpu: boolean
  cuda_available: boolean
  cuda_version: string | null
  gpu_name: string | null
  recommendation: string
  cuda_download_url: string | null
} | null>(null)

// Mirror source and cache options
const selectedMirror = ref("official")
const clearCache = ref(false)
const availableMirrors = ref<Record<string, { name: string; note: string; stable: boolean }>>({})

// Installed plugins and downloaded models (filtered views)
const installedPlugins = ref<PluginInfo[]>([])
const downloadedModels = ref<ModelInfo[]>([])
const notDownloadedModels = ref<ModelInfo[]>([])

async function detectGpu() {
  const res = await call<{
    has_nvidia_gpu: boolean
    cuda_available: boolean
    cuda_version: string | null
    gpu_name: string | null
    recommendation: string
    cuda_download_url: string | null
  }>("detect_gpu")
  if (res.success && res.data) {
    gpuInfo.value = res.data
  }
}

function refreshInstalledLists() {
  installedPlugins.value = pluginList.value.filter(p => p.status === "installed")
  downloadedModels.value = modelList.value.filter(m => m.status === "downloaded")
  // Deduplicate by model_id (CPU/GPU plugins share the same models)
  const seen = new Set<string>()
  notDownloadedModels.value = modelList.value.filter(m => {
    if (m.status === "downloaded" || seen.has(m.model_id)) return false
    seen.add(m.model_id)
    return true
  })
}

onMounted(async () => {
  const [settingsRes, ffmpegRes, encodersRes] = await Promise.all([
    call<AppSettings>("get_settings"),
    call<{ ffmpeg_path: string; ffprobe_path: string; version: string }>("get_ffmpeg_info"),
    call<{ encoders: string[] }>("detect_gpu_encoders"),
  ])
  if (settingsRes.success && settingsRes.data) {
    settings.value = settingsRes.data
  }
  if (ffmpegRes.success && ffmpegRes.data) {
    ffmpegInfo.value = ffmpegRes.data
  }
  if (encodersRes.success && encodersRes.data) {
    gpuEncoders.value = encodersRes.data.encoders
  }
  // Load plugins and models
  pluginList.value = await pluginManager.listPlugins()
  modelList.value = await pluginManager.listModels()
  refreshInstalledLists()
  // Load plugin data directory
  await loadPluginDataDir()
  // Detect GPU capabilities
  await detectGpu()
  // Load available mirrors
  const mirrorsRes = await call<Record<string, { name: string; note: string; stable: boolean }>>("list_mirrors")
  if (mirrorsRes.success && mirrorsRes.data) {
    availableMirrors.value = mirrorsRes.data
  }
})

async function handleSave() {
  if (!settings.value) return
  saving.value = true
  statusMsg.value = ""
  const res = await call<AppSettings>("update_settings", settings.value)
  saving.value = false
  if (res.success) {
    statusMsg.value = "Settings saved"
    setTimeout(() => { statusMsg.value = "" }, 2000)
  } else {
    statusMsg.value = "Save failed"
  }
}

async function handleBrowseFfmpeg() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0 && settings.value) {
    settings.value = { ...settings.value, ffmpeg_path: res.data[0] }
  }
}

async function handleBrowseFfprobe() {
  const res = await call<string[]>("select_files")
  if (res.success && res.data && res.data.length > 0 && settings.value) {
    settings.value = { ...settings.value, ffprobe_path: res.data[0] }
  }
}

async function handleDownloadFfmpeg() {
  statusMsg.value = "Downloading FFmpeg..."
  const res = await call<{ path: string }>("download_ffmpeg")
  if (res.success && res.data && settings.value) {
    settings.value = { ...settings.value, ffmpeg_path: res.data.path }
    ffmpegInfo.value.ffmpeg_path = res.data.path
    statusMsg.value = "FFmpeg downloaded"
  } else {
    statusMsg.value = res.error ?? "Download failed"
  }
}

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  if (settings.value) {
    settings.value = { ...settings.value, [key]: value }
  }
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

async function handleInstallPlugin(pluginId: string) {
  installingPlugin.value = pluginId
  installProgress.value = 0
  installMessage.value = "Starting installation..."

  const success = await pluginManager.installPlugin(
    pluginId,
    undefined,
    (progress) => {
      installProgress.value = progress.percent
      installMessage.value = progress.message
    },
    selectedMirror.value,
    clearCache.value,
  )

  if (success) {
    statusMsg.value = "Plugin installed successfully"
    pluginList.value = await pluginManager.listPlugins()
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    statusMsg.value = pluginManager.error.value || "Installation failed"
  }

  installingPlugin.value = null
  setTimeout(() => { statusMsg.value = "" }, 3000)
}

async function handleUninstallPlugin(pluginId: string) {
  const success = await pluginManager.uninstallPlugin(pluginId)
  if (success) {
    statusMsg.value = "Plugin uninstalled"
    pluginList.value = await pluginManager.listPlugins()
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    statusMsg.value = pluginManager.error.value || "Uninstall failed"
  }
  setTimeout(() => { statusMsg.value = "" }, 3000)
}

async function handleDeleteModel(modelId: string) {
  const success = await pluginManager.deleteModel(modelId)
  if (success) {
    statusMsg.value = "Model deleted"
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    statusMsg.value = pluginManager.error.value || "Delete failed"
  }
  setTimeout(() => { statusMsg.value = "" }, 3000)
}

async function handleDownloadModel(modelId: string) {
  statusMsg.value = `Downloading model...`
  const success = await pluginManager.downloadModel(modelId, (progress) => {
    statusMsg.value = progress.message || "Downloading..."
  })
  if (success) {
    statusMsg.value = "Model downloaded"
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    statusMsg.value = pluginManager.error.value || "Download failed"
  }
  setTimeout(() => { statusMsg.value = "" }, 3000)
}

async function handleOpenDataDirectory() {
  const res = await call("open_data_directory")
  if (!res.success) {
    statusMsg.value = res.error || "Failed to open directory"
    setTimeout(() => { statusMsg.value = "" }, 3000)
  }
}

const pluginDataDir = ref("")
async function loadPluginDataDir() {
  const res = await call<{ path: string }>("get_plugin_data_dir")
  if (res.success && res.data) {
    pluginDataDir.value = res.data.path
  }
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('close')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-[640px] max-w-[90vw] max-h-[85vh] overflow-hidden flex flex-col">
      <div class="px-6 pt-6 pb-4 border-b border-gray-100">
        <h2 class="text-lg font-semibold text-gray-800">Settings</h2>
      </div>

      <div class="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        <!-- FFmpeg Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">FFmpeg</h3>
          <div class="space-y-2 text-sm">
            <div class="flex items-center justify-between">
              <span class="text-gray-500">Version</span>
              <span class="text-gray-800">{{ ffmpegInfo.version || "Not found" }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-500">FFmpeg path</span>
              <span class="text-gray-800 truncate max-w-[300px]">{{ ffmpegInfo.ffmpeg_path || "Not found" }}</span>
            </div>
            <div class="flex items-center justify-between">
              <span class="text-gray-500">FFprobe path</span>
              <span class="text-gray-800 truncate max-w-[300px]">{{ ffmpegInfo.ffprobe_path || "Not found" }}</span>
            </div>
          </div>

          <div class="mt-3 space-y-2">
            <div class="flex gap-2">
              <input
                v-if="settings"
                type="text"
                :value="settings.ffmpeg_path"
                placeholder="Custom FFmpeg path (leave empty for auto)"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                @input="updateField('ffmpeg_path', ($event.target as HTMLInputElement).value)"
              />
              <button
                class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                @click="handleBrowseFfmpeg"
              >
                Browse
              </button>
            </div>
            <div class="flex gap-2">
              <input
                v-if="settings"
                type="text"
                :value="settings.ffprobe_path"
                placeholder="Custom FFprobe path (leave empty for auto)"
                class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                @input="updateField('ffprobe_path', ($event.target as HTMLInputElement).value)"
              />
              <button
                class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
                @click="handleBrowseFfprobe"
              >
                Browse
              </button>
            </div>
            <button
              class="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600"
              @click="handleDownloadFfmpeg"
            >
              Download FFmpeg
            </button>
          </div>
        </section>

        <!-- GPU / Encoders Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Hardware Encoders</h3>
          <div v-if="gpuEncoders.length > 0" class="flex flex-wrap gap-1.5">
            <span
              v-for="enc in gpuEncoders"
              :key="enc"
              class="px-2 py-0.5 text-xs rounded-full bg-green-100 text-green-800"
            >
              {{ enc }}
            </span>
          </div>
          <p v-else class="text-sm text-gray-500">No encoders detected</p>
        </section>

        <!-- AI Engine Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">AI Engine</h3>

          <!-- Install progress -->
          <div v-if="installingPlugin" class="mb-3 p-3 bg-blue-50 rounded-lg">
            <div class="flex items-center justify-between text-sm mb-1">
              <span class="text-blue-700">{{ installMessage }}</span>
              <span class="text-blue-600">{{ Math.round(installProgress) }}%</span>
            </div>
            <div class="w-full bg-blue-200 rounded-full h-2">
              <div
                class="bg-blue-500 h-2 rounded-full transition-all duration-300"
                :style="{ width: `${installProgress}%` }"
              />
            </div>
          </div>

          <!-- GPU Detection Status -->
          <div v-if="gpuInfo" class="mb-3 p-3 rounded-lg text-sm space-y-1">
            <!-- Has NVIDIA GPU + CUDA available -->
            <div v-if="gpuInfo.has_nvidia_gpu && gpuInfo.cuda_available" class="text-green-700 bg-green-50 p-2 rounded">
              <span class="font-medium">{{ gpuInfo.gpu_name }}</span> detected,
              CUDA {{ gpuInfo.cuda_version }} available
            </div>
            <!-- Has NVIDIA GPU but no CUDA -->
            <div v-else-if="gpuInfo.has_nvidia_gpu && !gpuInfo.cuda_available" class="text-yellow-700 bg-yellow-50 p-2 rounded space-y-1">
              <div>
                <span class="font-medium">{{ gpuInfo.gpu_name }}</span> detected, CUDA not installed
              </div>
              <a
                v-if="gpuInfo.cuda_download_url"
                :href="gpuInfo.cuda_download_url"
                target="_blank"
                class="text-blue-600 hover:underline text-xs"
              >
                Download CUDA installer
              </a>
            </div>
            <!-- No NVIDIA GPU -->
            <div v-else class="text-gray-500 bg-gray-50 p-2 rounded">
              No NVIDIA GPU detected. GPU acceleration requires an NVIDIA graphics card.
            </div>
          </div>

          <!-- Available Engines (not yet installed) - independent of engine setting -->
          <div class="mb-3">
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Available Engines</p>
            <div class="space-y-2">
              <!-- Faster Whisper -->
              <div
                v-if="!pluginList.some(p => p.plugin_id === 'plugin-whisper' && p.status === 'installed')"
                class="flex items-center justify-between p-2 rounded-lg border border-gray-200"
              >
                <div>
                  <div class="text-sm font-medium text-gray-800">Faster Whisper ASR</div>
                  <div class="text-xs text-gray-500">Lightweight, CPU-optimized</div>
                </div>
                <button
                  class="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                  :disabled="!!installingPlugin"
                  @click.prevent="handleInstallPlugin('plugin-whisper')"
                >
                  Install
                </button>
              </div>

              <!-- Qwen3 CPU -->
              <div
                v-if="!pluginList.some(p => p.plugin_id === 'plugin-qwen-cpu' && p.status === 'installed')"
                class="flex items-center justify-between p-2 rounded-lg border border-gray-200"
              >
                <div>
                  <div class="text-sm font-medium text-gray-800">Qwen3 ASR (CPU)</div>
                  <div class="text-xs text-gray-500">Works everywhere, no GPU required</div>
                </div>
                <button
                  class="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                  :disabled="!!installingPlugin"
                  @click.prevent="handleInstallPlugin('plugin-qwen-cpu')"
                >
                  Install
                </button>
              </div>

              <!-- Qwen3 GPU -->
              <div
                v-if="!pluginList.some(p => p.plugin_id === 'plugin-qwen-gpu' && p.status === 'installed')"
                class="flex items-center justify-between p-2 rounded-lg border border-gray-200"
                :class="!gpuInfo?.has_nvidia_gpu ? 'opacity-50' : ''"
              >
                <div>
                  <div class="text-sm font-medium text-gray-800">Qwen3 ASR (GPU/CUDA 12.4)</div>
                  <div class="text-xs text-gray-500">
                    <span v-if="gpuInfo?.has_nvidia_gpu && gpuInfo?.cuda_available">{{ gpuInfo.gpu_name }}, CUDA {{ gpuInfo.cuda_version }}</span>
                    <span v-else-if="gpuInfo?.has_nvidia_gpu">NVIDIA GPU detected, CUDA required</span>
                    <span v-else>Requires NVIDIA GPU + CUDA driver</span>
                  </div>
                </div>
                <button
                  class="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                  :disabled="!gpuInfo?.has_nvidia_gpu || !!installingPlugin"
                  @click.prevent="handleInstallPlugin('plugin-qwen-gpu')"
                >
                  Install
                </button>
              </div>
            </div>
            <p v-if="!gpuInfo?.has_nvidia_gpu" class="text-xs text-gray-400 mt-1">
              No NVIDIA GPU detected. GPU version requires an NVIDIA graphics card.
            </p>
            <a
              v-if="gpuInfo?.has_nvidia_gpu && !gpuInfo?.cuda_available && gpuInfo?.cuda_download_url"
              :href="gpuInfo.cuda_download_url"
              target="_blank"
              class="text-xs text-blue-600 hover:underline mt-1 inline-block"
            >
              Download CUDA installer
            </a>
          </div>

          <!-- PyTorch Install Options (always visible, user decides when installing) -->
          <div class="mb-3 space-y-2 p-2 rounded-lg bg-gray-50">
            <p class="text-xs font-medium text-gray-500">PyTorch Install Options</p>
            <div>
              <label class="text-xs text-gray-500">Mirror Source</label>
              <select
                v-model="selectedMirror"
                class="w-full px-2 py-1.5 text-sm border border-gray-300 rounded-lg"
              >
                <option v-for="(mirror, key) in availableMirrors" :key="key" :value="key">
                  {{ mirror.name }}
                </option>
              </select>
              <p v-if="availableMirrors[selectedMirror]" class="text-xs text-gray-400">
                {{ availableMirrors[selectedMirror].note }}
              </p>
              <p v-if="selectedMirror !== 'official'" class="text-xs text-yellow-600">
                Domestic mirrors may lag behind on versions. Switch to official source if installation fails.
              </p>
            </div>
            <label class="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                v-model="clearCache"
                class="w-4 h-4 mt-0.5 accent-blue-600"
              />
              <div>
                <span class="text-xs text-gray-700">Clear cache before install</span>
                <p class="text-xs text-gray-400">Recommended when switching mirrors</p>
              </div>
            </label>
          </div>

          <!-- Installed Engines -->
          <div v-if="installedPlugins.length > 0" class="mb-3">
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Installed Engines</p>
            <div class="space-y-1.5">
              <div
                v-for="plugin in installedPlugins"
                :key="plugin.plugin_id"
                class="flex items-center justify-between py-1.5 px-2 rounded-lg bg-gray-50"
              >
                <div class="flex items-center gap-2">
                  <span class="text-sm text-gray-800">{{ plugin.display_name }}</span>
                  <span class="text-xs text-gray-400">{{ plugin.engine }}</span>
                </div>
                <button
                  class="px-2 py-1 text-xs border border-red-300 text-red-600 rounded hover:bg-red-50"
                  @click="handleUninstallPlugin(plugin.plugin_id)"
                >
                  Uninstall
                </button>
              </div>
            </div>
          </div>

          <!-- Downloaded Models -->
          <div v-if="downloadedModels.length > 0" class="mb-3">
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Downloaded Models</p>
            <div class="space-y-1.5">
              <div
                v-for="model in downloadedModels"
                :key="model.model_id"
                class="flex items-center justify-between py-1.5 px-2 rounded-lg bg-gray-50"
              >
                <div>
                  <span class="text-sm text-gray-800">{{ model.display_name }}</span>
                  <span class="text-xs text-gray-400 ml-1">({{ formatBytes(model.size_bytes) }})</span>
                </div>
                <button
                  class="px-2 py-1 text-xs border border-red-300 text-red-600 rounded hover:bg-red-50"
                  @click="handleDeleteModel(model.model_id)"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>

          <!-- Available Models (not yet downloaded) -->
          <div v-if="notDownloadedModels.length > 0" class="mb-3">
            <p class="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Available Models</p>
            <div class="space-y-1.5">
              <div
                v-for="model in notDownloadedModels"
                :key="model.model_id"
                class="flex items-center justify-between py-1.5 px-2 rounded-lg border border-gray-200"
              >
                <div>
                  <span class="text-sm text-gray-800">{{ model.display_name }}</span>
                  <span class="text-xs text-gray-400 ml-1">({{ formatBytes(model.size_bytes) }})</span>
                </div>
                <button
                  class="px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
                  :disabled="!!installingPlugin"
                  @click="handleDownloadModel(model.model_id)"
                >
                  Download
                </button>
              </div>
            </div>
          </div>

          <p v-if="pluginList.length === 0" class="text-sm text-gray-500">No plugins available</p>

          <!-- Data directory -->
          <div class="mt-4 pt-3 border-t border-gray-200">
            <div class="flex items-center justify-between">
              <div>
                <p class="text-sm text-gray-600">Data directory</p>
                <p class="text-xs text-gray-400 mt-0.5 max-w-[350px] truncate">{{ pluginDataDir || 'Loading...' }}</p>
              </div>
              <button
                class="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition-colors"
                @click="handleOpenDataDirectory"
              >
                Open folder
              </button>
            </div>
          </div>
        </section>

        <!-- ASR Settings Section -->
        <section v-if="settings">
          <h3 class="text-sm font-semibold text-gray-700 mb-3">ASR Settings</h3>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Default engine</label>
              <select
                :value="settings.asr_engine"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_engine', ($event.target as HTMLSelectElement).value as 'faster-whisper' | 'qwen3-asr')"
              >
                <option value="faster-whisper">Faster Whisper</option>
                <option value="qwen3-asr">Qwen3 ASR</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Language</label>
              <select
                :value="settings.asr_language"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_language', ($event.target as HTMLSelectElement).value)"
              >
                <option value="zh">Chinese</option>
                <option value="en">English</option>
                <option value="ja">Japanese</option>
                <option value="ko">Korean</option>
                <option value="auto">Auto-detect</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Device</label>
              <select
                :value="settings.asr_device"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_device', ($event.target as HTMLSelectElement).value as 'cpu' | 'cuda' | 'auto')"
              >
                <option value="cpu">CPU</option>
                <option value="cuda">CUDA (GPU)</option>
                <option v-if="settings.asr_engine === 'faster-whisper'" value="auto">Auto</option>
              </select>
            </div>
            <div v-if="settings.asr_engine === 'faster-whisper'" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Compute type</label>
              <select
                :value="settings.asr_compute_type"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_compute_type', ($event.target as HTMLSelectElement).value as 'int8' | 'float16' | 'float32')"
              >
                <option value="int8">INT8 (fastest, lower quality)</option>
                <option value="float16">FP16 (balanced)</option>
                <option value="float32">FP32 (highest quality)</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Duplicate threshold</label>
              <input
                type="number"
                :value="settings.duplicate_threshold"
                step="0.05"
                min="0.5"
                max="1.0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('duplicate_threshold', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
        </section>

        <!-- Silence Detection Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Silence Detection</h3>
          <div v-if="settings" class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Threshold (dB)</label>
              <input
                type="number"
                :value="settings.silence_threshold_db"
                step="1"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_threshold_db', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Min duration (s)</label>
              <input
                type="number"
                :value="settings.silence_min_duration"
                step="0.1"
                min="0.1"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_min_duration', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Margin (s)</label>
              <input
                type="number"
                :value="settings.silence_margin"
                step="0.01"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_margin', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Subtitle padding (s)</label>
              <input
                type="number"
                :value="settings.silence_subtitle_padding"
                step="0.01"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('silence_subtitle_padding', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Trim subtitles on overlap</label>
              <input
                type="checkbox"
                :checked="settings.trim_subtitles_on_silence_overlap"
                class="checkbox checkbox-sm"
                @change="updateField('trim_subtitles_on_silence_overlap', ($event.target as HTMLInputElement).checked)"
              />
            </div>
          </div>
        </section>

        <!-- Export Section -->
        <section>
          <h3 class="text-sm font-semibold text-gray-700 mb-3">Export</h3>
          <div v-if="settings" class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Video codec</label>
              <select
                :value="settings.export_video_codec"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_video_codec', ($event.target as HTMLSelectElement).value)"
              >
                <option value="libx264">libx264 (CPU)</option>
                <option value="libx265">libx265 (CPU)</option>
                <option value="libsvtav1">libsvtav1 (CPU)</option>
                <option value="h264_nvenc">h264_nvenc (NVIDIA)</option>
                <option value="hevc_nvenc">hevc_nvenc (NVIDIA)</option>
                <option value="av1_nvenc">av1_nvenc (NVIDIA)</option>
                <option value="h264_qsv">h264_qsv (Intel)</option>
                <option value="hevc_qsv">hevc_qsv (Intel)</option>
                <option value="h264_amf">h264_amf (AMD)</option>
                <option value="hevc_amf">hevc_amf (AMD)</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Audio codec</label>
              <select
                :value="settings.export_audio_codec"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_audio_codec', ($event.target as HTMLSelectElement).value)"
              >
                <option value="aac">AAC</option>
                <option value="libmp3lame">MP3</option>
                <option value="libopus">Opus</option>
                <option value="flac">FLAC</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Audio bitrate</label>
              <input
                type="text"
                :value="settings.export_audio_bitrate"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_audio_bitrate', ($event.target as HTMLInputElement).value)"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Preset</label>
              <select
                :value="settings.export_preset"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_preset', ($event.target as HTMLSelectElement).value)"
              >
                <option value="ultrafast">ultrafast</option>
                <option value="superfast">superfast</option>
                <option value="veryfast">veryfast</option>
                <option value="faster">faster</option>
                <option value="fast">fast</option>
                <option value="medium">medium</option>
                <option value="slow">slow</option>
                <option value="slower">slower</option>
                <option value="veryslow">veryslow</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">CRF</label>
              <input
                type="number"
                :value="settings.export_crf"
                min="0"
                max="51"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_crf', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Resolution</label>
              <select
                :value="settings.export_resolution"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_resolution', ($event.target as HTMLSelectElement).value)"
              >
                <option value="original">Original</option>
                <option value="1920x1080">1080p</option>
                <option value="1280x720">720p</option>
                <option value="854x480">480p</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">FFmpeg transitions</label>
              <input
                type="checkbox"
                :checked="settings.export_ffmpeg_transitions"
                class="checkbox checkbox-sm"
                @change="updateField('export_ffmpeg_transitions', ($event.target as HTMLInputElement).checked)"
              />
            </div>
            <div v-if="settings.export_ffmpeg_transitions" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Fade duration (s)</label>
              <input
                type="number"
                :value="settings.export_ffmpeg_fade_duration"
                step="0.1"
                min="0"
                class="w-24 px-2 py-1 text-sm border border-gray-300 rounded text-right"
                @input="updateField('export_ffmpeg_fade_duration', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div v-if="settings.export_ffmpeg_transitions" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Fade mode</label>
              <select
                :value="settings.export_ffmpeg_fade_mode"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('export_ffmpeg_fade_mode', ($event.target as HTMLSelectElement).value)"
              >
                <option value="crossfade">Crossfade</option>
                <option value="fade_black">Fade through black</option>
              </select>
            </div>
          </div>
        </section>
      </div>

      <div class="px-6 py-4 border-t border-gray-100 flex items-center justify-between">
        <span class="text-sm text-gray-500">{{ statusMsg }}</span>
        <div class="flex gap-2">
          <button
            class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
            @click="emit('close')"
          >
            Close
          </button>
          <button
            class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? "Saving..." : "Save" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

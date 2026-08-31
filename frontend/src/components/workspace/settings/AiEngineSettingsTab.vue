<script setup lang="ts">
import { onMounted, ref } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import type { PluginInfo, ModelInfo, ModelMirror } from "@/types/project"
import { usePluginManager } from "@/composables/usePluginManager"
import { useUvAvailability } from "@/composables/useUvAvailability"

/**
 * AI engine settings tab (v3.0.0 M8-1, extracted from SettingsModal.vue).
 *
 * Owns: uv availability overlay, model directory, plugin install/uninstall,
 * model download/delete, GPU detection, download mirrors. Plugin manager
 * state is instance-local; uv availability is a shared singleton composable.
 * Settings mutations are emitted as patches; status messages bubble to the
 * modal footer via `status(message, timeout)`.
 */
const props = defineProps<{
  settings: AppSettings
}>()

const emit = defineEmits<{
  update: [patch: Partial<AppSettings>]
  status: [message: string, timeout: number]
}>()

// Plugin manager (instance-local) + shared uv availability
const pluginManager = usePluginManager()
const pluginList = ref<PluginInfo[]>([])
const modelList = ref<ModelInfo[]>([])
const installingPlugin = ref<string | null>(null)
const installProgress = ref(0)
const installMessage = ref("")

const { uvAvailable, recheckUvAvailable } = useUvAvailability()

// Whether the platform is macOS -- macOS has no NVIDIA CUDA
const isDarwin = navigator.platform.toLowerCase().includes('mac')

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

// Model download mirror
const selectedModelMirror = ref<string | undefined>(undefined)
const modelMirrors = ref<ModelMirror[]>([])

// Installed plugins and downloaded models (filtered views)
const installedPlugins = ref<PluginInfo[]>([])
const downloadedModels = ref<ModelInfo[]>([])
const notDownloadedModels = ref<ModelInfo[]>([])

function updateField<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
  emit("update", { [key]: value } as Partial<AppSettings>)
}

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
  // Deduplicate by model_id (CPU/GPU plugins share the same models)
  const seen = new Set<string>()
  downloadedModels.value = modelList.value.filter(m => {
    if (m.status !== "downloaded" || seen.has(m.model_id)) return false
    seen.add(m.model_id)
    return true
  })
  const seenNotDownloaded = new Set<string>()
  notDownloadedModels.value = modelList.value.filter(m => {
    if (m.status === "downloaded" || seenNotDownloaded.has(m.model_id)) return false
    seenNotDownloaded.add(m.model_id)
    return true
  })
}

onMounted(async () => {
  pluginList.value = await pluginManager.listPlugins()
  modelList.value = await pluginManager.listModels()
  refreshInstalledLists()
  // Detect GPU capabilities
  await detectGpu()
  // Load available mirrors
  const mirrorsRes = await call<Record<string, { name: string; note: string; stable: boolean }>>("list_mirrors")
  if (mirrorsRes.success && mirrorsRes.data) {
    availableMirrors.value = mirrorsRes.data
  }
  // Load model download mirrors
  modelMirrors.value = await pluginManager.listModelMirrors()
})

async function handleBrowseModelDir() {
  const res = await call<string>("select_directory")
  if (res.success && res.data) {
    emit("update", { model_dir: res.data })
  }
}

function handleResetModelDir() {
  emit("update", { model_dir: "" })
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
    emit("status", "Plugin installed successfully", 3000)
    pluginList.value = await pluginManager.listPlugins()
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    emit("status", pluginManager.error.value || "Installation failed", 3000)
  }

  installingPlugin.value = null
}

async function handleUninstallPlugin(pluginId: string) {
  const success = await pluginManager.uninstallPlugin(pluginId)
  if (success) {
    emit("status", "Plugin uninstalled", 3000)
    pluginList.value = await pluginManager.listPlugins()
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    emit("status", pluginManager.error.value || "Uninstall failed", 3000)
  }
}

async function handleDeleteModel(modelId: string) {
  const success = await pluginManager.deleteModel(modelId)
  if (success) {
    emit("status", "Model deleted", 3000)
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    emit("status", pluginManager.error.value || "Delete failed", 3000)
  }
}

async function handleDownloadModel(modelId: string) {
  emit("status", `Downloading model...`, 3000)
  const success = await pluginManager.downloadModel(modelId, (progress) => {
    emit("status", progress.message || "Downloading...", 3000)
  }, selectedModelMirror.value)
  if (success) {
    emit("status", "Model downloaded", 3000)
    modelList.value = await pluginManager.listModels()
    refreshInstalledLists()
  } else {
    emit("status", pluginManager.error.value || "Download failed", 3000)
  }
}
</script>

<template>
  <div class="space-y-4">
    <!-- UV not available overlay -->
    <div v-if="uvAvailable === false" class="relative rounded-lg border border-amber-200 bg-amber-50 p-4 space-y-3">
      <div class="flex items-start gap-3">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-amber-500 mt-0.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
        <div>
          <h3 class="text-sm font-medium text-amber-800">uv Not Found</h3>
          <p class="text-xs text-amber-700 mt-1">
            ASR engine requires the uv package manager. Please install uv and restart the app, or click Re-check after installing.
          </p>
        </div>
      </div>
      <div class="flex gap-2">
        <a
          href="https://docs.astral.sh/uv/getting-started/installation/"
          target="_blank"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-amber-600 rounded hover:bg-amber-700 transition-colors"
        >
          Install uv
          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
        <button
          class="inline-flex items-center px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 rounded hover:bg-amber-200 transition-colors"
          @click="recheckUvAvailable"
        >
          Re-check
        </button>
      </div>
    </div>

    <!-- Model Directory -->
    <div class="space-y-1.5">
      <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Model Directory</p>
      <div class="flex gap-2">
        <input
          type="text"
          :value="props.settings.model_dir"
          placeholder="默认: 插件目录/models"
          class="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          @input="updateField('model_dir', ($event.target as HTMLInputElement).value)"
        />
        <button
          class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
          @click="handleBrowseModelDir"
        >
          Browse
        </button>
        <button
          class="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-500"
          @click="handleResetModelDir"
        >
          Reset
        </button>
      </div>
      <p class="text-xs text-gray-400">修改模型目录后需重启应用生效</p>
    </div>

    <!-- Install progress -->
    <div v-if="installingPlugin" class="p-3 bg-blue-50 rounded-lg">
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
    <div v-if="gpuInfo" class="p-3 rounded-lg text-sm space-y-1">
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

    <!-- Available Engines (not yet installed) -->
    <div>
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

        <!-- Qwen3 GPU (non-macOS only) -->
        <div
          v-if="!isDarwin && !pluginList.some(p => p.plugin_id === 'plugin-qwen-gpu' && p.status === 'installed')"
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

        <!-- Qwen3 MLX (macOS only) -->
        <div
          v-if="isDarwin && !pluginList.some(p => p.plugin_id === 'plugin-qwen-mlx' && p.status === 'installed')"
          class="flex items-center justify-between p-2 rounded-lg border border-gray-200"
        >
          <div>
            <div class="text-sm font-medium text-gray-800">Qwen3 ASR (Apple Silicon)</div>
            <div class="text-xs text-gray-500">Metal-accelerated via MLX, no PyTorch needed</div>
          </div>
          <button
            class="px-3 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
            :disabled="!!installingPlugin"
            @click.prevent="handleInstallPlugin('plugin-qwen-mlx')"
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

    <!-- PyTorch Install Options -->
    <div class="space-y-2 p-2 rounded-lg bg-gray-50">
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
    <div v-if="installedPlugins.length > 0">
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
    <div v-if="downloadedModels.length > 0">
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

    <!-- Model Download Source -->
    <div>
      <label class="text-xs font-medium text-gray-500 uppercase tracking-wide">Download Source</label>
      <select
        v-model="selectedModelMirror"
        class="mt-1 w-full px-2 py-1.5 text-sm border border-gray-300 rounded-lg bg-white"
      >
        <option :value="undefined">Auto Detect</option>
        <option v-for="m in modelMirrors" :key="m.id" :value="m.id">{{ m.display_name }}</option>
      </select>
      <p class="mt-1 text-xs text-gray-400">Select a mirror if auto-detection fails</p>
    </div>

    <!-- Available Models (not yet downloaded) -->
    <div v-if="notDownloadedModels.length > 0">
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
  </div>
</template>

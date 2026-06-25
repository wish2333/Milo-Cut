<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"
import type { PluginInfo, ModelInfo, ModelMirror } from "@/types/project"
import { usePluginManager } from "@/composables/usePluginManager"
import { useUvAvailability } from "@/composables/useUvAvailability"
import { useLlmSettings } from "@/composables/useLlmSettings"

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

// Phase 4: ESC key closes the fullscreen overlay (D-09 UX)
function handleEsc(e: KeyboardEvent) {
  if (e.key === "Escape" && props.visible) emit("close")
}
onMounted(() => window.addEventListener("keydown", handleEsc))
onUnmounted(() => window.removeEventListener("keydown", handleEsc))

interface EncoderMeta {
  label: string
  qualityMode: string
  recommendedQuality: number
  qualityRange: [number, number]
}

const settings = ref<AppSettings | null>(null)
const ffmpegInfo = ref<{ ffmpeg_path: string; ffprobe_path: string; version: string }>({ ffmpeg_path: "", ffprobe_path: "", version: "" })
const gpuEncoders = ref<string[]>([])
const encoderMeta = ref<Record<string, EncoderMeta>>({})
const saving = ref(false)

// Display order for hardware encoders; CPU encoders are always available.
const HW_ENCODER_ORDER = [
  "h264_nvenc", "hevc_nvenc", "av1_nvenc",
  "h264_qsv", "hevc_qsv", "av1_qsv",
  "h264_amf", "hevc_amf",
  "h264_videotoolbox", "hevc_videotoolbox",
]

const availableVideoCodecs = computed(() => {
  const list: { value: string; label: string }[] = [
    { value: "libx264", label: encoderMeta.value["libx264"]?.label ?? "libx264 (CPU)" },
    { value: "libx265", label: encoderMeta.value["libx265"]?.label ?? "libx265 (CPU)" },
  ]
  if (gpuEncoders.value.includes("libsvtav1")) {
    list.push({ value: "libsvtav1", label: encoderMeta.value["libsvtav1"]?.label ?? "libsvtav1 (CPU)" })
  }
  for (const enc of HW_ENCODER_ORDER) {
    if (gpuEncoders.value.includes(enc)) {
      list.push({ value: enc, label: encoderMeta.value[enc]?.label ?? enc })
    }
  }
  // Preserve persisted selection even if detection missed it (e.g. custom ffmpeg build)
  const selected = settings.value?.export_video_codec
  if (selected && !list.some(c => c.value === selected)) {
    list.unshift({ value: selected, label: encoderMeta.value[selected]?.label ?? selected })
  }
  return list
})
const statusMsg = ref("")
const activeTab = ref<"general" | "ai-engine" | "llm" | "export" | "shortcuts">("general")

// Plugin manager
const pluginManager = usePluginManager()
const pluginList = ref<PluginInfo[]>([])
const modelList = ref<ModelInfo[]>([])
const installingPlugin = ref<string | null>(null)

// ASR models filtered by current engine, excluding ForcedAligner, deduplicated
const asrModels = computed(() => {
  if (!settings.value) return []
  const engine = settings.value.asr_engine
  const seen = new Set<string>()
  return modelList.value.filter(m => {
    if (m.engine !== engine || m.model_id.includes("ForcedAligner") || seen.has(m.model_id)) return false
    seen.add(m.model_id)
    return true
  })
})

// Installed ASR engine plugins (CPU + GPU variants), deduplicated by plugin_id
const installedAsrPlugins = computed(() => {
  const seen = new Set<string>()
  return installedPlugins.value.filter(p => {
    if ((p.engine !== "faster-whisper" && p.engine !== "qwen3-asr") || seen.has(p.plugin_id)) return false
    seen.add(p.plugin_id)
    return true
  })
})

// Whether the currently selected ASR plugin supports GPU — macOS has no NVIDIA CUDA
const isDarwin = navigator.platform.toLowerCase().includes('mac')
const isMlxPlugin = computed(() => (settings.value?.asr_plugin_id ?? '').includes('-mlx'))
const asrSupportsGpu = computed(() => {
  if (isDarwin || isMlxPlugin.value) return false
  const pid = settings.value?.asr_plugin_id ?? ''
  return pid.length > 0 && !pid.includes('-cpu')
})
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

// Model download mirror
const selectedModelMirror = ref<string | undefined>(undefined)
const modelMirrors = ref<ModelMirror[]>([])

// Installed plugins and downloaded models (filtered views)
const installedPlugins = ref<PluginInfo[]>([])
const downloadedModels = ref<ModelInfo[]>([])
const notDownloadedModels = ref<ModelInfo[]>([])

// UV availability check (shared composable)
const { uvAvailable, recheckUvAvailable } = useUvAvailability()

// LLM settings
const {
  testing: llmTesting,
  testResult: llmTestResult,
  testConnection,
  promptsData,
  loadPrompts,
  updatePrompt,
  resetPrompt,
  // v2.1.0 Phase 1: Preset management
  presetsByFunc,
  loadPresets,
  savePreset,
  applyPreset,
  deletePreset,
} = useLlmSettings()
const showLlmKey = ref(false)

// Phase 3: Prompt editing state
const promptFuncKeys = [
  { key: "smart_delete", label: "智能删除" },
  { key: "subtitle_correction_a", label: "字幕修正 (模式 A)" },
  { key: "subtitle_correction_b", label: "字幕修正 (模式 B)" },
  { key: "highlight", label: "精华提取" },
  { key: "search", label: "语义搜索" },
] as const

const selectedPromptKey = ref<string>("smart_delete")
const promptEditMode = ref<"simple" | "advanced">("simple")
const promptParamText = ref<Record<string, string>>({})  // textarea text per param
const promptSystemOverride = ref("")
const promptSaving = ref(false)
const promptStatusMsg = ref("")

// Param labels for simple mode UI
const promptParamLabels: Record<string, string> = {
  custom_fillers: "自定义口头禅 (每行一个)",
  glossary: "术语表 (每行一个)",
  focus_keywords: "关注关键词 (每行一个)",
}

// Placeholder hint text for advanced mode (avoid {{ }} in template)
const placeholderHint = "留空使用默认提示词 + 简单模式参数"

// v2.1.0 Phase 1: Preset management state
// search (P3) has no presets per D-41.
const presetSupportedKeys = new Set(["smart_delete", "subtitle_correction_a", "subtitle_correction_b", "highlight"])
const selectedPresetId = ref<string>("")
const showSavePresetInput = ref(false)
const newPresetName = ref("")
const presetBusy = ref(false)

const currentPresets = computed(() => presetsByFunc.value[selectedPromptKey.value] ?? [])
const presetSupported = computed(() => presetSupportedKeys.has(selectedPromptKey.value))

function loadPromptEditor(funcKey: string) {
  const defaults = promptsData.value?.defaults?.[funcKey]
  const override = promptsData.value?.overrides?.[funcKey]
  // Initialize param text from override or default
  promptParamText.value = {}
  if (defaults?.params) {
    for (const [k, v] of Object.entries(defaults.params)) {
      const overrideVals = override?.params?.[k]
      promptParamText.value[k] = (overrideVals ?? v).join("\n")
    }
  }
  promptSystemOverride.value = override?.system_override ?? ""
}

async function handlePromptKeyChange(key: string) {
  selectedPromptKey.value = key
  if (!promptsData.value) await loadPrompts()
  loadPromptEditor(key)
  // Reset preset selection on feature switch
  selectedPresetId.value = ""
  showSavePresetInput.value = false
  // Load presets for the newly selected feature (if supported)
  if (presetSupportedKeys.has(key)) {
    await loadPresets(key)
  }
}

async function handleSavePrompt() {
  promptSaving.value = true
  promptStatusMsg.value = ""
  const funcKey = selectedPromptKey.value
  if (promptEditMode.value === "advanced") {
    const success = await updatePrompt(funcKey, {
      system_override: promptSystemOverride.value,
    })
    promptStatusMsg.value = success ? "已保存" : "保存失败"
  } else {
    // Convert textarea text to list arrays
    const params: Record<string, string[]> = {}
    for (const [k, text] of Object.entries(promptParamText.value)) {
      params[k] = text.split("\n").map(s => s.trim()).filter(Boolean)
    }
    const success = await updatePrompt(funcKey, { params })
    promptStatusMsg.value = success ? "已保存" : "保存失败"
  }
  promptSaving.value = false
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleResetPrompt() {
  const funcKey = selectedPromptKey.value
  const success = await resetPrompt(funcKey)
  if (success) {
    loadPromptEditor(funcKey)
    promptStatusMsg.value = "已重置为默认"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
  }
}

// v2.1.0 Phase 1: Preset handlers
async function handleApplyPreset() {
  if (!selectedPresetId.value) return
  presetBusy.value = true
  promptStatusMsg.value = ""
  const ok = await applyPreset(selectedPromptKey.value, selectedPresetId.value)
  presetBusy.value = false
  if (ok) {
    // Reload editor so the textareas reflect the applied preset
    loadPromptEditor(selectedPromptKey.value)
    promptStatusMsg.value = "预设已应用"
  } else {
    promptStatusMsg.value = "应用失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleSaveAsPreset() {
  const name = newPresetName.value.trim()
  if (!name) {
    promptStatusMsg.value = "请输入预设名称"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
    return
  }
  const funcKey = selectedPromptKey.value
  // Snapshot current editor contents (same logic as handleSavePrompt)
  const params: Record<string, string[]> = {}
  for (const [k, text] of Object.entries(promptParamText.value)) {
    params[k] = text.split("\n").map(s => s.trim()).filter(Boolean)
  }
  presetBusy.value = true
  promptStatusMsg.value = ""
  const created = await savePreset(
    funcKey,
    name,
    params,
    promptEditMode.value === "advanced" ? promptSystemOverride.value : "",
  )
  presetBusy.value = false
  if (created) {
    showSavePresetInput.value = false
    newPresetName.value = ""
    selectedPresetId.value = created.id
    promptStatusMsg.value = "预设已保存"
  } else {
    promptStatusMsg.value = "保存失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

async function handleDeletePreset() {
  if (!selectedPresetId.value) return
  const preset = currentPresets.value.find(p => p.id === selectedPresetId.value)
  if (!preset) return
  // Built-in default is protected server-side; double-check client-side.
  if (preset.id === "default") {
    promptStatusMsg.value = "内置默认预设不可删除"
    setTimeout(() => { promptStatusMsg.value = "" }, 2000)
    return
  }
  if (!window.confirm(`确认删除预设「${preset.name}」？`)) return
  presetBusy.value = true
  promptStatusMsg.value = ""
  const ok = await deletePreset(selectedPromptKey.value, selectedPresetId.value)
  presetBusy.value = false
  if (ok) {
    selectedPresetId.value = ""
    promptStatusMsg.value = "预设已删除"
  } else {
    promptStatusMsg.value = "删除失败"
  }
  setTimeout(() => { promptStatusMsg.value = "" }, 2000)
}

const llmProviders = [
  { id: "deepseek" as const, label: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-v4-flash" },
  { id: "openai" as const, label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-5.4-mini" },
  { id: "qwen" as const, label: "Qwen", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus" },
  { id: "glm" as const, label: "GLM (智谱)", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5-turbo" },
  { id: "custom" as const, label: "Custom (自定义)", baseUrl: "", model: "" },
]

// Providers that do NOT support thinking mode (OpenAI GPT series).
// DeepSeek, Qwen, GLM, Custom all support thinking via extra_body.
const _NO_THINK_PROVIDERS = new Set(["openai"])

function onLlmProviderChange(provider: string) {
  if (!settings.value) return
  const oldProvider = settings.value.llm_provider

  // Persist current provider's values before switching
  const configs = { ...(settings.value.llm_provider_configs ?? {}) }
  configs[oldProvider] = {
    base_url: settings.value.llm_base_url,
    api_key: settings.value.llm_api_key,
    model: settings.value.llm_model,
  }

  // Restore target provider's persisted values, or fall back to defaults
  const info = llmProviders.find(p => p.id === provider)
  const cached = configs[provider]
  settings.value = {
    ...settings.value,
    llm_provider: provider as AppSettings["llm_provider"],
    llm_base_url: cached?.base_url ?? info?.baseUrl ?? "",
    llm_api_key: cached?.api_key ?? "",
    llm_model: cached?.model ?? info?.model ?? "",
    llm_provider_configs: configs,
  }
}

function providerSupportsThinking(providerId: string): boolean {
  return !_NO_THINK_PROVIDERS.has(providerId)
}

function isOllamaUrl(url: string): boolean {
  return url.includes("localhost:11434")
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
  const [settingsRes, ffmpegRes, encodersRes, metaRes] = await Promise.all([
    call<AppSettings>("get_settings"),
    call<{ ffmpeg_path: string; ffprobe_path: string; version: string }>("get_ffmpeg_info"),
    call<{ encoders: string[] }>("detect_gpu_encoders"),
    call<Record<string, EncoderMeta>>("get_encoder_metadata"),
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
  if (metaRes.success && metaRes.data) {
    encoderMeta.value = metaRes.data
  }
  // Load plugins and models
  pluginList.value = await pluginManager.listPlugins()
  modelList.value = await pluginManager.listModels()
  refreshInstalledLists()
  // Load plugin data directory
  await loadPluginDataDir()
  // Phase 3: Load LLM prompt configurations
  await loadPrompts()
  loadPromptEditor(selectedPromptKey.value)
  // v2.1.0 Phase 1: Load presets for the default selected feature
  if (presetSupportedKeys.has(selectedPromptKey.value)) {
    await loadPresets(selectedPromptKey.value)
  }
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
  return res.success
}

// Test Connection: persist current form to backend first, then run the test.
// Without saving, the backend would test the previously-stored config rather
// than what the user just typed into the form.
async function handleTestConnection() {
  if (!settings.value) return
  // Persist silently -- we don't want "Settings saved" flashing before the test
  saving.value = true
  const res = await call<AppSettings>("update_settings", settings.value)
  saving.value = false
  if (!res.success) {
    llmTestResult.value = { success: false, message: "Failed to save settings before test" }
    return
  }
  await testConnection()
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

async function handleBrowseModelDir() {
  const res = await call<string>("select_directory")
  if (res.success && res.data && settings.value) {
    settings.value = { ...settings.value, model_dir: res.data }
  }
}

function handleResetModelDir() {
  if (settings.value) {
    settings.value = { ...settings.value, model_dir: "" }
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

// Handle engine plugin change: derive engine type, reset device/compute defaults
function handleEnginePluginChange(pluginId: string) {
  if (!settings.value) return
  const plugin = installedAsrPlugins.value.find(p => p.plugin_id === pluginId)
  if (!plugin) return
  const gpu = !isDarwin && !pluginId.includes('-cpu')
  const engine = plugin.engine
  const defaults: Partial<AppSettings> = {
    asr_plugin_id: pluginId,
    asr_engine: engine,
    asr_device: gpu ? 'cuda' : (isDarwin && engine === 'faster-whisper') ? 'auto' : (isDarwin && engine === 'qwen3-asr') ? 'mps' : 'cpu',
    asr_language: engine === 'qwen3-asr' ? 'auto' : 'zh',
  }
  if (engine === 'qwen3-asr') {
    defaults.qwen_compute_type = gpu ? 'bfloat16' : 'float32'
  } else {
    defaults.whisper_compute_type = gpu ? 'int8_float16' : 'int8'
  }
  settings.value = { ...settings.value, ...defaults }
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
  }, selectedModelMirror.value)
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

const cleaningUp = ref(false)
async function handleCleanupTasks() {
  if (cleaningUp.value) return
  if (!window.confirm('Are you sure you want to clean up task files? This will delete all log and result files.')) return
  cleaningUp.value = true
  statusMsg.value = "Cleaning up task files..."
  try {
    const res = await call<{ deleted: number; size_freed: number }>("cleanup_tasks_folder")
    if (res.success && res.data) {
      const sizeMB = (res.data.size_freed / 1024 / 1024).toFixed(1)
      statusMsg.value = `Cleaned up ${res.data.deleted} task files (${sizeMB} MB freed)`
    } else {
      statusMsg.value = res.error || "Cleanup failed"
    }
  } finally {
    cleaningUp.value = false
    setTimeout(() => { statusMsg.value = "" }, 5000)
  }
}

async function handleCleanupTranscripts() {
  if (cleaningUp.value) return
  if (!window.confirm('Are you sure you want to clean up silence detection data?')) return
  cleaningUp.value = true
  statusMsg.value = "Cleaning up transcript files..."
  try {
    const res = await call<{ deleted: number; size_freed: number }>("cleanup_transcripts_folder")
    if (res.success && res.data) {
      const sizeMB = (res.data.size_freed / 1024 / 1024).toFixed(1)
      statusMsg.value = `Cleaned up ${res.data.deleted} transcript files (${sizeMB} MB freed)`
    } else {
      statusMsg.value = res.error || "Cleanup failed"
    }
  } finally {
    cleaningUp.value = false
    setTimeout(() => { statusMsg.value = "" }, 5000)
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
  <Teleport to="body">
    <Transition name="overlay-fade">
  <div
    v-if="visible"
    class="fixed inset-0 z-[9998] bg-white"
  >
    <div class="flex h-full flex-col">
      <div class="flex items-center justify-between px-8 py-4 border-b border-gray-100">
        <h2 class="text-lg font-semibold text-gray-800">设置</h2>
        <button
          class="text-gray-400 hover:text-gray-600 transition-colors"
          title="关闭 (ESC)"
          @click="emit('close')"
        >
          <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto px-8 py-6">
        <!-- Tab Navigation -->
        <div role="tablist" class="flex gap-1 border-b border-gray-200 mb-4">
          <button
            v-for="tab in [
              { id: 'general' as const, label: '通用' },
              { id: 'ai-engine' as const, label: 'AI 引擎' },
              { id: 'llm' as const, label: 'LLM' },
              { id: 'export' as const, label: '导出' },
              { id: 'shortcuts' as const, label: '快捷键' },
            ]"
            :key="tab.id"
            role="tab"
            :aria-selected="activeTab === tab.id"
            class="px-4 py-2 text-sm font-medium transition-colors -mb-px border-b-2"
            :class="activeTab === tab.id
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- Tab 1: General -->
        <div v-if="activeTab === 'general'" class="space-y-6">
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

            <!-- Proxy Video Section -->
            <section>
              <h3 class="text-sm font-semibold text-gray-700 mb-3">Proxy Video</h3>
              <p class="text-xs text-gray-400 mb-3">Proxy videos are lower-resolution copies used for faster preview playback.</p>
          <div v-if="settings" class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Proxy resolution</label>
              <select
                :value="settings.proxy_resolution"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('proxy_resolution', ($event.target as HTMLSelectElement).value)"
              >
                <option value="854x480">480p</option>
                <option value="1280x720">720p</option>
                <option value="1920x1080">1080p</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Auto-generate proxy on import</label>
              <input
                type="checkbox"
                :checked="settings.auto_generate_proxy"
                @change="updateField('auto_generate_proxy', ($event.target as HTMLInputElement).checked)"
              />
            </div>
          </div>
            </section>

            <!-- Data Directory & Cleanup -->
            <section class="pt-3 border-t border-gray-200">
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
            <div class="flex gap-2 mt-3">
              <button
                class="px-3 py-1.5 text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded-lg transition-colors disabled:opacity-50"
                :disabled="cleaningUp"
                @click="handleCleanupTasks"
              >
                {{ cleaningUp ? 'Cleaning...' : 'Cleanup task files' }}
              </button>
              <button
                class="px-3 py-1.5 text-xs bg-amber-50 hover:bg-amber-100 text-amber-700 border border-amber-200 rounded-lg transition-colors disabled:opacity-50"
                :disabled="cleaningUp"
                @click="handleCleanupTranscripts"
              >
                {{ cleaningUp ? 'Cleaning...' : 'Cleanup transcripts' }}
              </button>
            </div>
          </div>
            </section>
          </div>

          <!-- Tab 2: AI Engine -->
          <div v-if="activeTab === 'ai-engine'" class="space-y-4">
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
            <div v-if="settings" class="space-y-1.5">
              <p class="text-xs font-medium text-gray-500 uppercase tracking-wide">Model Directory</p>
              <div class="flex gap-2">
                <input
                  type="text"
                  :value="settings.model_dir"
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

          <!-- Tab 3: LLM -->
          <div v-if="activeTab === 'llm'" class="space-y-6">
            <template v-if="settings">
            <p class="text-xs text-gray-400">API Key is stored locally and never sent to our servers.</p>

            <section>
              <label class="block text-sm font-medium text-gray-700 mb-1">Provider</label>
              <select
                :value="settings.llm_provider"
                class="w-full rounded border border-gray-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                @change="onLlmProviderChange(($event.target as HTMLSelectElement).value)"
              >
                <option v-for="p in llmProviders" :key="p.id" :value="p.id">{{ p.label }}</option>
              </select>
            </section>

            <section>
              <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
              <div class="flex gap-2">
                <input
                  :type="showLlmKey ? 'text' : 'password'"
                  :value="settings.llm_api_key"
                  placeholder="sk-..."
                  class="flex-1 rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                  @input="settings = { ...settings!, llm_api_key: ($event.target as HTMLInputElement).value }"
                />
                <button
                  type="button"
                  class="rounded border border-gray-300 px-3 py-2 text-xs text-gray-600 hover:bg-gray-50"
                  @click="showLlmKey = !showLlmKey"
                >
                  {{ showLlmKey ? 'Hide' : 'Show' }}
                </button>
              </div>
            </section>

            <!-- Base URL --- visible for all, editable for power users -->
            <section>
              <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
              <input
                type="text"
                :value="settings.llm_base_url"
                placeholder="https://api.openai.com/v1"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                @input="settings = { ...settings!, llm_base_url: ($event.target as HTMLInputElement).value }"
              />
              <p v-if="isOllamaUrl(settings.llm_base_url)" class="mt-1 text-xs text-green-600">Ollama detected</p>

              <!-- Custom provider tutorial -->
              <div v-if="settings.llm_provider === 'custom'" class="mt-2 rounded border border-blue-100 bg-blue-50 p-2 text-xs text-blue-700 space-y-1">
                <p><strong>自定义供应商说明:</strong></p>
                <p>1. 在 <strong>Base URL</strong> 填入 API 的完整地址，以 <code>/v1</code> 结尾</p>
                <p>2. 在 <strong>Model</strong> 填入你想要使用的模型名称</p>
                <p>3. 确保 API 兼容 OpenAI 格式 (如 Ollama、vLLM、LiteLLM 等)</p>
              </div>
            </section>

            <section>
              <label class="block text-sm font-medium text-gray-700 mb-1">Model</label>
              <input
                type="text"
                :value="settings.llm_model"
                :placeholder="providerSupportsThinking(settings.llm_provider) ? 'deepseek-v4-flash' : 'gpt-5.4-mini'"
                class="w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                @input="settings = { ...settings!, llm_model: ($event.target as HTMLInputElement).value }"
              />
            </section>

            <!-- Thinking mode toggle (not supported by OpenAI GPT models) -->
            <section>
              <label class="relative flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  :checked="settings.llm_thinking_enabled ?? false"
                  :disabled="!providerSupportsThinking(settings.llm_provider)"
                  class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
                  @change="settings = { ...settings!, llm_thinking_enabled: ($event.target as HTMLInputElement).checked }"
                />
                <span class="text-sm font-medium text-gray-700 select-none" :class="{ 'opacity-40': !providerSupportsThinking(settings.llm_provider) }">
                  深度思考 (Thinking)
                </span>
              </label>
              <p v-if="!providerSupportsThinking(settings.llm_provider)" class="mt-1 text-xs text-gray-400">
                OpenAI GPT 系列模型不支持深度思考模式
              </p>
              <p v-else class="mt-1 text-xs text-gray-400">
                启用链式推理 (Chain-of-Thought)，让模型在回答前进行深度思考。适合复杂推理任务，但会增加响应时间和 Token 消耗
              </p>
            </section>

            <section>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                Temperature: {{ settings.llm_temperature.toFixed(1) }}
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                :value="settings.llm_temperature"
                class="w-full"
                @input="settings = { ...settings!, llm_temperature: parseFloat(($event.target as HTMLInputElement).value) }"
              />
            </section>

            <!-- v2.1.1 M2: Advanced LLM parameters (chunking / batching / concurrency) -->
            <section class="border-t border-gray-200 pt-4">
              <details class="group">
                <summary class="flex cursor-pointer items-center gap-1 text-sm font-medium text-gray-700 select-none">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" /></svg>
                  高级参数
                </summary>
                <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label class="block">
                    <span class="text-xs text-gray-600">智能删除批次大小 (条)</span>
                    <input
                      type="number"
                      step="1"
                      min="5"
                      :value="settings.llm_smart_batch_size"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_batch_size: Number.isNaN(v) ? 20 : v } })()"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">智能删除重叠 (条)</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      :value="settings.llm_smart_overlap_size"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_overlap_size: Number.isNaN(v) ? 4 : v } })()"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">字幕修正批次大小</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      :value="settings.llm_correction_batch_size"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="settings = { ...settings!, llm_correction_batch_size: parseInt(($event.target as HTMLInputElement).value) || 30 }"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">字幕修正上下文窗口</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      :value="settings.llm_correction_context_window"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="settings = { ...settings!, llm_correction_context_window: parseInt(($event.target as HTMLInputElement).value) || 5 }"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">精华提取窗口 (秒)</span>
                    <input
                      type="number"
                      step="10"
                      min="60"
                      :value="settings.llm_highlight_chunk_duration"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="settings = { ...settings!, llm_highlight_chunk_duration: parseFloat(($event.target as HTMLInputElement).value) || 1800.0 }"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">精华提取重叠 (秒)</span>
                    <input
                      type="number"
                      step="1"
                      min="0"
                      :value="settings.llm_highlight_overlap_duration"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="settings = { ...settings!, llm_highlight_overlap_duration: parseFloat(($event.target as HTMLInputElement).value) || 60.0 }"
                    />
                  </label>
                  <label class="block">
                    <span class="text-xs text-gray-600">LLM 并发数</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      max="20"
                      :value="settings.llm_concurrency"
                      class="mt-0.5 w-full rounded border border-gray-300 px-2 py-1 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
                      @change="settings = { ...settings!, llm_concurrency: parseInt(($event.target as HTMLInputElement).value) || 5 }"
                    />
                  </label>
                </div>
                <p class="mt-2 text-xs text-gray-400">
                  较大批次减少 API 调用次数但单次耗时更长。并发数过高可能触发 API 限流。
                  取消后已发出的请求仍会消耗少量 Token。
                </p>
              </details>
            </section>

            <section class="flex items-center gap-3">
              <button
                type="button"
                :disabled="llmTesting || saving || !settings.llm_api_key"
                class="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                @click="handleTestConnection"
              >
                {{ llmTesting ? 'Testing...' : (saving ? 'Saving...' : 'Test Connection') }}
              </button>
              <span v-if="llmTestResult" :class="llmTestResult.success ? 'text-green-600' : 'text-red-600'" class="text-sm">
                {{ llmTestResult.message }}
              </span>
            </section>

            <!-- Phase 3: Prompt editing section -->
            <section class="border-t border-gray-200 pt-4">
              <h3 class="text-sm font-semibold text-gray-700 mb-3">提示词编辑</h3>

              <!-- Function selector -->
              <div class="flex items-center gap-2 mb-3">
                <label class="text-xs text-gray-500">功能:</label>
                <select
                  :value="selectedPromptKey"
                  class="px-2 py-1 text-xs border border-gray-300 rounded"
                  @change="handlePromptKeyChange(($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="f in promptFuncKeys" :key="f.key" :value="f.key">
                    {{ f.label }}
                  </option>
                </select>
              </div>

              <!-- v2.1.0 Phase 1: Preset management (only for supported features) -->
              <div v-if="presetSupported" class="border border-gray-200 rounded p-2 mb-3 bg-gray-50">
                <div class="flex items-center gap-2 flex-wrap">
                  <label class="text-xs text-gray-500">预设:</label>
                  <select
                    v-model="selectedPresetId"
                    class="px-2 py-1 text-xs border border-gray-300 rounded bg-white"
                  >
                    <option value="" disabled>(选择预设)</option>
                    <option v-for="p in currentPresets" :key="p.id" :value="p.id">
                      {{ p.name }}{{ p.id === 'default' ? ' (内置)' : '' }}
                    </option>
                  </select>
                  <button
                    class="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                    :disabled="!selectedPresetId || presetBusy"
                    @click="handleApplyPreset"
                  >应用</button>
                  <button
                    class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100 disabled:opacity-50"
                    :disabled="presetBusy"
                    @click="showSavePresetInput = !showSavePresetInput"
                  >另存为预设</button>
                  <button
                    class="rounded border border-red-300 px-2 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                    :disabled="!selectedPresetId || presetBusy"
                    @click="handleDeletePreset"
                  >删除</button>
                </div>
                <!-- Save-as-preset inline input -->
                <div v-if="showSavePresetInput" class="flex items-center gap-2 mt-2">
                  <input
                    v-model="newPresetName"
                    class="flex-1 px-2 py-1 text-xs border border-gray-300 rounded"
                    placeholder="预设名称 (如: 学术报告)"
                    @keyup.enter="handleSaveAsPreset"
                  />
                  <button
                    class="rounded bg-green-600 px-2 py-1 text-xs text-white hover:bg-green-700 disabled:opacity-50"
                    :disabled="presetBusy"
                    @click="handleSaveAsPreset"
                  >保存</button>
                  <button
                    class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
                    @click="showSavePresetInput = false; newPresetName = ''"
                  >取消</button>
                </div>
                <p class="text-xs text-gray-400 mt-1">应用预设会将参数写入当前配置;另存为预设将当前编辑区参数保存为新预设</p>
              </div>

              <!-- Mode toggle -->
              <div class="flex items-center gap-3 mb-3">
                <label class="flex items-center gap-1 text-xs">
                  <input
                    type="radio"
                    value="simple"
                    v-model="promptEditMode"
                  />
                  简单模式
                </label>
                <label class="flex items-center gap-1 text-xs">
                  <input
                    type="radio"
                    value="advanced"
                    v-model="promptEditMode"
                  />
                  高级模式
                </label>
              </div>

              <!-- Simple mode: parameter fields -->
              <div v-if="promptEditMode === 'simple'" class="space-y-3">
                <div
                  v-for="(_text, paramKey) in promptParamText"
                  :key="paramKey"
                >
                  <label class="block text-xs font-medium text-gray-600 mb-1">
                    {{ promptParamLabels[paramKey] ?? paramKey }}
                  </label>
                  <textarea
                    v-model="promptParamText[paramKey]"
                    class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
                    rows="3"
                    :placeholder="'每行一个'"
                  ></textarea>
                </div>
                <p v-if="Object.keys(promptParamText).length === 0" class="text-xs text-gray-400">
                  此功能无可配置参数
                </p>
              </div>

              <!-- Advanced mode: full prompt textarea -->
              <div v-else class="space-y-2">
                <label class="block text-xs font-medium text-gray-600">
                  完整提示词 (含标记位)
                </label>
                <textarea
                  v-model="promptSystemOverride"
                  class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
                  rows="10"
                  :placeholder="placeholderHint"
                ></textarea>
                <details class="text-xs text-gray-500">
                  <summary class="cursor-pointer">查看默认提示词</summary>
                  <pre class="mt-2 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">{{ promptsData?.defaults?.[selectedPromptKey]?.system ?? '(无)' }}</pre>
                </details>
              </div>

              <!-- Action buttons -->
              <div class="flex items-center gap-2 mt-3">
                <button
                  class="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                  :disabled="promptSaving"
                  @click="handleSavePrompt"
                >
                  {{ promptSaving ? '保存中...' : '保存' }}
                </button>
                <button
                  class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                  @click="handleResetPrompt"
                >
                  重置为默认
                </button>
                <span v-if="promptStatusMsg" class="text-xs text-green-600">
                  {{ promptStatusMsg }}
                </span>
              </div>
            </section>
            </template>
          </div>

          <!-- Tab 4: Export -->
          <div v-if="activeTab === 'export'" class="space-y-6">
            <!-- ASR Settings Section -->
            <section v-if="settings">
              <h3 class="text-sm font-semibold text-gray-700 mb-3">ASR Settings</h3>
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Default engine</label>
              <select
                :value="settings.asr_plugin_id || settings.asr_engine"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="handleEnginePluginChange(($event.target as HTMLSelectElement).value)"
              >
                <option v-for="p in installedAsrPlugins" :key="p.plugin_id" :value="p.plugin_id">
                  {{ p.display_name }}
                </option>
                <option v-if="installedAsrPlugins.length === 0" value="faster-whisper">Faster Whisper</option>
                <option v-if="installedAsrPlugins.length === 0" value="qwen3-asr">Qwen3 ASR</option>
              </select>
            </div>
            <div class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Model</label>
              <select
                :value="settings.asr_model_size"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_model_size', ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="m in asrModels" :key="m.model_id" :value="m.model_id">
                  {{ m.display_name }}
                </option>
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
            <div v-if="!isMlxPlugin" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Device</label>
              <select
                :value="settings.asr_device"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField('asr_device', ($event.target as HTMLSelectElement).value as 'cpu' | 'cuda' | 'auto' | 'mps')"
              >
                <option v-if="!isDarwin" value="cpu">CPU</option>
                <option v-if="asrSupportsGpu" value="cuda">CUDA (GPU)</option>
                <option v-if="settings.asr_engine === 'faster-whisper'" value="auto">Auto</option>
                <option v-if="isDarwin && settings.asr_engine === 'qwen3-asr'" value="mps">MPS</option>
              </select>
              <span v-if="isDarwin && settings.asr_engine === 'faster-whisper'" class="text-xs text-gray-400 ml-2">MPS (Metal Performance Shaders)</span>
              <span v-else-if="isDarwin && settings.asr_engine === 'qwen3-asr'" class="text-xs text-gray-400 ml-2">Metal Performance Shaders (Apple GPU)</span>
              <span v-else-if="!asrSupportsGpu" class="text-xs text-gray-400 ml-2">GPU not available for this plugin</span>
            </div>
            <div v-else class="text-xs text-gray-400">Apple Silicon (Metal)</div>
            <div v-if="!isMlxPlugin" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">Compute type</label>
              <select
                :value="settings.asr_engine === 'faster-whisper' ? settings.whisper_compute_type : settings.qwen_compute_type"
                class="px-2 py-1 text-sm border border-gray-300 rounded"
                @change="updateField(settings.asr_engine === 'faster-whisper' ? 'whisper_compute_type' : 'qwen_compute_type', ($event.target as HTMLSelectElement).value as 'int8' | 'int8_float16' | 'float16' | 'float32' | 'bfloat16')"
              >
                <template v-if="settings.asr_engine === 'faster-whisper'">
                  <option value="int8">INT8 (fastest)</option>
                  <option v-if="!isDarwin" value="int8_float16">INT8 FP16 (balanced)</option>
                  <option v-if="!isDarwin" value="float16">FP16</option>
                  <option value="float32">FP32 (highest quality)</option>
                </template>
                <template v-else>
                  <option v-if="!isDarwin" value="bfloat16">BF16 (recommended)</option>
                  <option value="float16">FP16</option>
                  <option value="float32">FP32</option>
                </template>
              </select>
            </div>
            <div v-if="settings.asr_engine === 'faster-whisper'" class="flex items-center justify-between">
              <label class="text-sm text-gray-600">VAD filter</label>
              <div class="flex items-center gap-2">
                <input
                  type="checkbox"
                  :checked="settings.asr_vad_filter"
                  class="w-4 h-4 mt-0.5 accent-blue-600"
                  @change="updateField('asr_vad_filter', ($event.target as HTMLInputElement).checked)"
                />
                <span class="text-xs text-gray-500">Reduce hallucinations in noisy audio</span>
              </div>
            </div>
            <!-- VAD sliders (visible when vad_filter is on and engine is faster-whisper) -->
            <template v-if="settings.asr_engine === 'faster-whisper' && settings.asr_vad_filter">
              <label class="block mb-2">
                <span class="text-xs text-gray-500">
                  VAD Threshold: {{ (settings.whisper_vad_threshold ?? 0.5).toFixed(2) }}
                </span>
                <input
                  type="range"
                  :value="settings.whisper_vad_threshold ?? 0.5"
                  min="0"
                  max="1"
                  step="0.05"
                  class="w-full mt-1"
                  @input="updateField('whisper_vad_threshold', parseFloat(($event.target as HTMLInputElement).value))"
                />
              </label>
              <label class="block mb-3">
                <span class="text-xs text-gray-500">
                  Min Silence (ms): {{ settings.whisper_vad_min_silence_ms ?? 500 }}
                </span>
                <input
                  type="range"
                  :value="settings.whisper_vad_min_silence_ms ?? 500"
                  min="100"
                  max="2000"
                  step="50"
                  class="w-full mt-1"
                  @input="updateField('whisper_vad_min_silence_ms', parseInt(($event.target as HTMLInputElement).value))"
                />
              </label>
            </template>
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

            <!-- Export Settings Section -->
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
                <option v-for="codec in availableVideoCodecs" :key="codec.value" :value="codec.value">
                  {{ codec.label }}
                </option>
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
          <!-- Tab 5: Shortcuts -->
          <div v-if="activeTab === 'shortcuts'" class="space-y-6">
            <!-- 播放控制 -->
            <section>
              <h3 class="text-sm font-semibold text-gray-700 mb-3">播放控制</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">从当前行播放视频</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Space</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">原片 / 剪后切换预览</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Space</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">跳到片段开头</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">I</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">跳到片段结尾</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">O</kbd>
                  </div>
                </div>
              </div>
            </section>

            <!-- 编辑操作 -->
            <section>
              <h3 class="text-sm font-semibold text-gray-700 mb-3">编辑操作</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">标记删除</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Delete</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">撤销上一步</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Z</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">保存项目</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">S</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">打开搜索替换</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">F</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">上下移动选中行</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↑</kbd>
                    <span class="text-gray-400 mx-1">/</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↓</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">多选字幕行</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <span class="text-gray-600">Click</span>
                  </div>
                </div>
              </div>
            </section>

            <!-- 时间微调 -->
            <section>
              <h3 class="text-sm font-semibold text-gray-700 mb-3">时间微调（时间编辑 input 聚焦时）</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">+0.1s / +1.0s (Shift)</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↑</kbd>
                    <span class="text-xs text-gray-400">(Shift+↑)</span>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">-0.1s / -1.0s (Shift)</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">↓</kbd>
                    <span class="text-xs text-gray-400">(Shift+↓)</span>
                  </div>
                </div>
              </div>
            </section>

            <!-- 建议面板 -->
            <section>
              <h3 class="text-sm font-semibold text-gray-700 mb-3">建议面板</h3>
              <div class="space-y-2">
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">全部确认建议</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">A</kbd>
                  </div>
                </div>
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-gray-600">忽略所有建议</span>
                  <div class="flex items-center gap-1">
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Ctrl</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">Shift</kbd>
                    <span class="text-gray-400 mx-1">+</span>
                    <kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">D</kbd>
                  </div>
                </div>
              </div>
            </section>
          </div>
      </div>

      <div class="px-8 py-4 border-t border-gray-100 flex items-center justify-between">
        <span class="text-sm text-gray-500">{{ statusMsg }}</span>
        <div class="flex gap-2">
          <button
            class="px-4 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
            @click="emit('close')"
          >
            关闭
          </button>
          <button
            class="px-4 py-2 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 active:scale-95 disabled:opacity-50 transition-all duration-150"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? "保存中..." : "保存" }}
          </button>
        </div>
      </div>
    </div>
  </div>
    </Transition>
  </Teleport>
</template>

<style>
/* Phase 4: 全屏覆盖层淡入淡出 -- 150ms 平滑过渡,避免突兀的白板闪现 */
.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 150ms ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>

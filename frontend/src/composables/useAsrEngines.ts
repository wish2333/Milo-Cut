import { computed, ref, watch } from "vue"
import { call } from "@/bridge"
import type { ModelInfo, PluginInfo } from "@/types/project"

/**
 * Shared ASR engine domain (v3.0.0 M8-2b).
 *
 * Single source of truth for engine/plugin selection, per-engine settings,
 * installed-engine discovery and GPU/compute capability derivation.
 * Consumed by WorkspacePage (transcription popover + handleTranscribe) and
 * by the settings tabs (ExportSettingsTab ASR section; AiEngineSettingsTab
 * refresh hook), so a change made through one UI is immediately visible in
 * the other -- eliminating the previous duplicated implementations.
 *
 * State and watchers live at module level (singleton, app lifetime).
 * `ensureLoaded()` preserves the startup-order contract: installed engines
 * are discovered BEFORE persisted settings are hydrated onto them
 * (previously `loadInstalledEngines() // Must run BEFORE loadAsrSettings`).
 */

export interface InstalledEngine {
  engine: string
  displayName: string
  pluginId: string
  ready: boolean
}

export interface AsrEngineSettings {
  model_size: string
  language: string
  device: "cpu" | "cuda" | "auto" | "mps"
  compute_type: string
  vad_filter: boolean
  vad_threshold: number
  vad_min_silence_ms: number
}

// Whether the platform is macOS -- macOS has no NVIDIA CUDA
const isDarwin = navigator.platform.toLowerCase().includes("mac")

const asrEngine = ref<"faster-whisper" | "qwen3-asr">("faster-whisper")
const asrPluginId = ref("")  // Tracks which specific plugin variant is selected (CPU vs GPU)

// ASR transcription settings - per-engine storage so switching preserves settings
const asrSettingsPerEngine = ref<Record<string, AsrEngineSettings>>({
  "faster-whisper": {
    model_size: "large-v3-turbo",
    language: "zh",
    device: "cuda",
    compute_type: "int8_float16",
    vad_filter: true,
    vad_threshold: 0.5,
    vad_min_silence_ms: 500,
  },
  "qwen3-asr": {
    model_size: "Qwen/Qwen3-ASR-0.6B",
    language: "auto",
    device: "cuda",
    compute_type: "bfloat16",
    vad_filter: false,
    vad_threshold: 0.5,
    vad_min_silence_ms: 500,
  },
})

const installedEngines = ref<InstalledEngine[]>([])
const modelList = ref<ModelInfo[]>([])

const hasInstalledEngines = computed(() => installedEngines.value.length > 0)
const isMlx = computed(() => asrPluginId.value.includes("-mlx"))
const supportsGpu = computed(() => {
  if (isDarwin) return false
  const pid = asrPluginId.value
  // CPU-only plugins have "-cpu" suffix in pluginId
  return pid.length > 0 && !pid.includes("-cpu")
})

// Available ASR models (filtered from plugin manager list)
const availableModels = computed(() => {
  return modelList.value
    .filter(m => m.engine === asrEngine.value && !m.model_id.includes("ForcedAligner"))
    .filter((m, i, arr) => arr.findIndex(x => x.model_id === m.model_id) === i)
})

// Settings object of the currently selected engine
const currentSettings = computed(() => asrSettingsPerEngine.value[asrEngine.value])

// Compute type options per engine (MLX: none; macOS CPU: no int8_float16/float16/bfloat16)
const computeTypeOptions = computed(() => {
  if (isMlx.value) return []
  if (asrEngine.value === 'faster-whisper') {
    const gpuOptions = [
      { value: 'int8', label: 'INT8 (fastest)' },
      { value: 'int8_float16', label: 'INT8 FP16 (balanced)' },
      { value: 'float16', label: 'FP16' },
      { value: 'float32', label: 'FP32 (highest quality)' },
    ]
    const cpuOptions = [
      { value: 'int8', label: 'INT8 (fastest)' },
      { value: 'float32', label: 'FP32 (highest quality)' },
    ]
    return (supportsGpu.value || asrSettingsPerEngine.value[asrEngine.value]?.device === 'auto') ? gpuOptions : cpuOptions
  }
  if (isDarwin) {
    return [
      { value: 'float16', label: 'FP16' },
      { value: 'float32', label: 'FP32' },
    ]
  }
  return [
    { value: 'bfloat16', label: 'BF16 (recommended)' },
    { value: 'float16', label: 'FP16' },
    { value: 'float32', label: 'FP32' },
  ]
})

// -- Thin bridge wrappers (faithful copies of usePluginManager methods;
//    kept instance-free so module-level loaders can use them) ------------

async function fetchPlugins(): Promise<PluginInfo[]> {
  const res = await call<PluginInfo[]>("list_plugins")
  if (res.success && res.data) return res.data
  return []
}

async function checkEngineReady(engine: string): Promise<{
  ready: boolean
  installed: boolean
  models: Record<string, boolean>
}> {
  const res = await call<{
    engine: string
    plugin_id: string
    installed: boolean
    models: Record<string, boolean>
    ready: boolean
  }>("check_plugin_status", engine)
  if (res.success && res.data) {
    return {
      ready: res.data.ready,
      installed: res.data.installed,
      models: res.data.models,
    }
  }
  return { ready: false, installed: false, models: {} }
}

async function fetchModels(): Promise<ModelInfo[]> {
  const res = await call<ModelInfo[]>("list_models")
  if (res.success && res.data) return res.data
  return []
}

// -- Domain logic (moved verbatim from WorkspacePage.vue) ----------------

async function loadAsrSettings() {
  const res = await call<Record<string, unknown>>("get_settings")
  if (res.success && res.data) {
    const engine = (res.data.asr_engine as "faster-whisper" | "qwen3-asr") || "faster-whisper"
    asrEngine.value = engine

    // Restore pluginId from saved settings, or auto-select first matching engine
    const savedPluginId = res.data.asr_plugin_id as string
    if (savedPluginId && installedEngines.value.find(e => e.pluginId === savedPluginId)) {
      asrPluginId.value = savedPluginId
    } else {
      // Auto-select first installed engine for this engine type
      const firstEng = installedEngines.value.find(e => e.engine === engine)
      if (firstEng) asrPluginId.value = firstEng.pluginId
    }

    // Shared settings
    const vadFilter = res.data.asr_vad_filter !== false

    // Determine per-engine device based on plugin capabilities
    const whisperPluginId = installedEngines.value.find(e => e.engine === "faster-whisper")?.pluginId ?? ""
    const qwenPluginId = installedEngines.value.find(e => e.engine === "qwen3-asr")?.pluginId ?? ""
    const whisperSupportsGpu = !isDarwin && whisperPluginId.length > 0 && !whisperPluginId.includes("-cpu")
    const qwenSupportsGpu = !isDarwin && qwenPluginId.length > 0 && !qwenPluginId.includes("-cpu")

    // Load faster-whisper settings (engine-prefixed keys from config.py)
    const whisperModelSize = (res.data.asr_model_size as string) || "large-v3-turbo"
    const whisperDevice = (res.data.asr_device as "cpu" | "cuda" | "auto" | "mps") || (whisperSupportsGpu ? "cuda" : isDarwin ? "auto" : "cpu")
    asrSettingsPerEngine.value["faster-whisper"] = {
      model_size: whisperModelSize,
      language: (res.data.asr_language as string) || "zh",
      device: whisperDevice,
      compute_type: (res.data.whisper_compute_type as string) || (whisperSupportsGpu ? "int8_float16" : "int8"),
      vad_filter: vadFilter,
      vad_threshold: Number(res.data.whisper_vad_threshold ?? 0.5),
      vad_min_silence_ms: Number(res.data.whisper_vad_min_silence_ms ?? 500),
    }

    // Load qwen3-asr settings
    const qwenModelSize = (res.data.asr_model_size as string) || "Qwen/Qwen3-ASR-0.6B"
    const qwenDevice = qwenSupportsGpu ? "cuda" : isDarwin ? "mps" : "cpu"
    asrSettingsPerEngine.value["qwen3-asr"] = {
      model_size: qwenModelSize,
      language: (res.data.qwen_language as string) || "auto",
      device: qwenDevice,
      compute_type: (res.data.qwen_compute_type as string) || (qwenSupportsGpu ? "bfloat16" : "float16"),
      vad_filter: false,
      vad_threshold: 0.5,
      vad_min_silence_ms: 500,
    }
  }
}

async function loadInstalledEngines() {
  const plugins = await fetchPlugins()
  const engines: InstalledEngine[] = []

  for (const p of plugins) {
    if (p.status === "installed") {
      const status = await checkEngineReady(p.engine)
      engines.push({
        engine: p.engine,
        displayName: p.display_name,
        pluginId: p.plugin_id,
        ready: status.ready,
      })
    }
  }

  installedEngines.value = engines

  // If current selected engine is not installed, switch to first available
  if (engines.length > 0 && !engines.find(e => e.engine === asrEngine.value)) {
    asrEngine.value = engines[0].engine as "faster-whisper" | "qwen3-asr"
  }
}

function validateModelSize() {
  const models = availableModels.value
  const current = asrSettingsPerEngine.value[asrEngine.value]
  if (current && models.length > 0 && !models.find(m => m.model_id === current.model_size)) {
    asrSettingsPerEngine.value[asrEngine.value].model_size = models[0].model_id
  }
}

// Derive engine from selected pluginId, and update device/compute when plugin changes
watch(asrPluginId, (newPluginId) => {
  if (!newPluginId) return
  const eng = installedEngines.value.find(e => e.pluginId === newPluginId)
  if (eng) {
    const prevEngine = asrEngine.value
    asrEngine.value = eng.engine as "faster-whisper" | "qwen3-asr"
    // If engine type didn't change (e.g. CPU->GPU within same engine),
    // watch(asrEngine) won't fire, so we must update device/compute here
    if (prevEngine === eng.engine) {
      const gpu = !isDarwin && !newPluginId.includes('-cpu')
      const settings = asrSettingsPerEngine.value[eng.engine]
      if (settings) {
        settings.device = gpu ? 'cuda' : 'cpu'
        if (eng.engine === 'qwen3-asr') {
          settings.compute_type = gpu ? 'bfloat16' : 'float16'
        }
        // faster-whisper keeps int8_float16 for both CPU and GPU
      }
    }
  }
})

// Engine defaults by type
function getEngineDefaults(engine: "faster-whisper" | "qwen3-asr") {
  const gpu = !isDarwin && asrPluginId.value.length > 0 && !asrPluginId.value.includes('-cpu')
  if (engine === 'qwen3-asr') {
    return { model_size: "Qwen/Qwen3-ASR-0.6B", language: "auto", device: gpu ? "cuda" as const : isDarwin ? "mps" as const : "cpu" as const, compute_type: gpu ? "bfloat16" as const : isDarwin ? "float16" as const : "float16" as const, vad_filter: false, vad_threshold: 0.5, vad_min_silence_ms: 500 }
  }
  return { model_size: "large-v3-turbo", language: "zh", device: gpu ? "cuda" as const : isDarwin ? "auto" as const : "cpu" as const, compute_type: gpu ? "int8_float16" as const : "int8" as const, vad_filter: true, vad_threshold: 0.5, vad_min_silence_ms: 500 }
}

// When engine changes, only create defaults if not yet populated.
// Device/compute are always updated based on selected plugin's GPU capability.
// User preferences (model_size, language, vad_*) are preserved from loadAsrSettings().
watch(asrEngine, (newEngine) => {
  const defaults = getEngineDefaults(newEngine)
  const existing = asrSettingsPerEngine.value[newEngine]
  if (!existing) {
    asrSettingsPerEngine.value[newEngine] = { ...defaults }
  } else {
    // Only update device/compute based on plugin capability (these are plugin-dependent, not user preference)
    existing.device = defaults.device
    existing.compute_type = defaults.compute_type
  }
  validateModelSize()
})

async function saveAsrSettings(): Promise<boolean> {
  const current = asrSettingsPerEngine.value[asrEngine.value]
  const payload: Record<string, unknown> = {
    asr_engine: asrEngine.value,
    asr_plugin_id: asrPluginId.value,
    asr_model_size: current.model_size,
    asr_language: current.language,
    asr_device: current.device,
    asr_vad_filter: current.vad_filter,
  }

  // Engine-prefixed keys for settings persistence
  if (asrEngine.value === "qwen3-asr") {
    payload.qwen_compute_type = current.compute_type
    payload.qwen_language = current.language
  } else {
    payload.whisper_compute_type = current.compute_type
    payload.whisper_vad_threshold = current.vad_threshold
    payload.whisper_vad_min_silence_ms = current.vad_min_silence_ms
  }

  const res = await call("update_settings", payload)
  return res.success
}

// -- Shared loaders -------------------------------------------------------

// Startup-order contract: installed engines BEFORE settings hydration.
// Single-flight guard so concurrent consumers share one load sequence.
let loadPromise: Promise<void> | null = null
async function ensureLoaded(): Promise<void> {
  if (!loadPromise) {
    loadPromise = (async () => {
      await loadInstalledEngines()  // Must run BEFORE loadAsrSettings
      await loadAsrSettings()
      modelList.value = await fetchModels()
      validateModelSize()
    })()
  }
  return loadPromise
}

// Re-discover engines/models after plugin installs/uninstalls or model
// downloads performed in the settings UI, so the workspace engine selector
// and readiness badges follow without an app restart.
async function refreshAfterPluginChange(): Promise<void> {
  await loadInstalledEngines()
  modelList.value = await fetchModels()
  validateModelSize()
}

// Settings-patch derivation for the settings-modal engine selector (moved
// verbatim from SettingsModal's Export tab `handleEnginePluginChange`).
// Returns null for unknown plugins (caller keeps the original no-op).
export function deriveEngineChangePatch(
  pluginId: string,
  engine: string,
): Record<string, unknown> | null {
  if (!pluginId) return null
  const gpu = !isDarwin && !pluginId.includes("-cpu")
  const patch: Record<string, unknown> = {
    asr_plugin_id: pluginId,
    asr_engine: engine,
    asr_device: gpu ? "cuda" : (isDarwin && engine === "faster-whisper") ? "auto" : (isDarwin && engine === "qwen3-asr") ? "mps" : "cpu",
    asr_language: engine === "qwen3-asr" ? "auto" : "zh",
  }
  if (engine === "qwen3-asr") {
    patch.qwen_compute_type = gpu ? "bfloat16" : "float32"
  } else {
    patch.whisper_compute_type = gpu ? "int8_float16" : "int8"
  }
  return patch
}

export function useAsrEngines() {
  return {
    // state
    asrEngine,
    asrPluginId,
    asrSettingsPerEngine,
    currentSettings,
    installedEngines,
    hasInstalledEngines,
    modelList,
    availableModels,
    isDarwin,
    isMlx,
    supportsGpu,
    computeTypeOptions,
    // actions
    ensureLoaded,
    refreshAfterPluginChange,
    saveAsrSettings,
    checkEngineReady,
  }
}

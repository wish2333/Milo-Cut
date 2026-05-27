/** Composable for managing ASR plugins and models. */

import { ref } from "vue"
import { call } from "@/bridge"
import { useBridge } from "@/composables/useBridge"
import type { PluginInfo, ModelInfo } from "@/types/project"
import type { TaskProgress } from "@/types/task"

export function usePluginManager() {
  const plugins = ref<PluginInfo[]>([])
  const models = ref<ModelInfo[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const { on } = useBridge()

  /** Fetch all registered plugins and their installation status. */
  async function listPlugins(): Promise<PluginInfo[]> {
    const res = await call<PluginInfo[]>("list_plugins")
    if (res.success && res.data) {
      plugins.value = res.data
      return res.data
    }
    error.value = res.error || "Failed to list plugins"
    return []
  }

  /** Fetch all registered models and their download status. */
  async function listModels(): Promise<ModelInfo[]> {
    const res = await call<ModelInfo[]>("list_models")
    if (res.success && res.data) {
      models.value = res.data
      return res.data
    }
    error.value = res.error || "Failed to list models"
    return []
  }

  /** Install a plugin. Listens for progress events. */
  async function installPlugin(
    pluginId: string,
    modelId?: string,
    onProgress?: (progress: TaskProgress) => void,
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const res = await call<{ task_id: string }>("install_plugin", pluginId, modelId || "")
      if (!res.success || !res.data) {
        error.value = res.error || "Failed to start installation"
        return false
      }

      // Listen for progress events
      if (onProgress) {
        on<TaskProgress>("task:progress", (detail) => {
          if (detail) onProgress(detail)
        })
      }

      return true
    } finally {
      loading.value = false
    }
  }

  /** Uninstall a plugin. */
  async function uninstallPlugin(pluginId: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const res = await call("uninstall_plugin", pluginId)
      if (!res.success) {
        error.value = res.error || "Failed to uninstall plugin"
        return false
      }
      await listPlugins()
      await listModels()
      return true
    } finally {
      loading.value = false
    }
  }

  /** Download a model. */
  async function downloadModel(
    modelId: string,
    onProgress?: (progress: TaskProgress) => void,
  ): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const res = await call<{ task_id: string }>("download_model", modelId)
      if (!res.success) {
        error.value = res.error || "Failed to start download"
        return false
      }

      if (onProgress) {
        on<TaskProgress>("task:progress", (detail) => {
          if (detail) onProgress(detail)
        })
      }

      return true
    } finally {
      loading.value = false
    }
  }

  /** Delete a downloaded model. */
  async function deleteModel(modelId: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const res = await call("delete_model", modelId)
      if (!res.success) {
        error.value = res.error || "Failed to delete model"
        return false
      }
      await listModels()
      return true
    } finally {
      loading.value = false
    }
  }

  /** Check if an ASR engine is ready (plugin installed + model downloaded). */
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

  /** Ensure an engine is ready. If not, return info about what's needed. */
  async function ensureReady(engine: string): Promise<{
    ready: boolean
    pluginId: string
    missingModels: string[]
  }> {
    const status = await checkEngineReady(engine)
    if (status.ready) {
      return { ready: true, pluginId: "", missingModels: [] }
    }

    // Find the plugin for this engine
    const pluginList = plugins.value.length > 0 ? plugins.value : await listPlugins()
    const plugin = pluginList.find((p) => p.engine === engine)
    const pluginId = plugin?.plugin_id || ""

    const missingModels = Object.entries(status.models)
      .filter(([, downloaded]) => !downloaded)
      .map(([modelId]) => modelId)

    return {
      ready: false,
      pluginId,
      missingModels,
    }
  }

  return {
    plugins,
    models,
    loading,
    error,
    listPlugins,
    listModels,
    installPlugin,
    uninstallPlugin,
    downloadModel,
    deleteModel,
    checkEngineReady,
    ensureReady,
  }
}

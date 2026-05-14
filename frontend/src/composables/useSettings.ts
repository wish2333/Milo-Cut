import { ref, onMounted } from "vue"
import { call } from "@/bridge"
import type { AppSettings } from "@/types/edit"

export function useSettings() {
  const settings = ref<AppSettings | null>(null)

  async function loadSettings(): Promise<boolean> {
    const res = await call<AppSettings>("get_settings")
    if (res.success && res.data) {
      settings.value = res.data
      return true
    }
    return false
  }

  async function updateSettings(updates: Partial<AppSettings>): Promise<boolean> {
    const res = await call<AppSettings>("update_settings", updates)
    if (res.success && res.data) {
      settings.value = res.data
      return true
    }
    return false
  }

  onMounted(() => {
    loadSettings()
  })

  return {
    settings,
    loadSettings,
    updateSettings,
  }
}

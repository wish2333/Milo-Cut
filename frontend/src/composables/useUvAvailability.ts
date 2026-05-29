import { ref } from "vue"
import { call } from "@/bridge"

/** Shared UV availability state -- checked once at app startup. */
const uvAvailable = ref<boolean | null>(null) // null = loading, true/false = checked
const uvPath = ref<string | null>(null)

async function checkUvAvailable() {
  try {
    const res = await call<{ available: boolean; path: string | null }>("check_uv_available")
    if (res.success && res.data) {
      uvAvailable.value = res.data.available
      uvPath.value = res.data.path
    }
  } catch {
    uvAvailable.value = false
  }
}

async function recheckUvAvailable() {
  try {
    const res = await call<{ available: boolean; path: string | null }>("check_uv_available", true)
    if (res.success && res.data) {
      uvAvailable.value = res.data.available
      uvPath.value = res.data.path
    }
  } catch {
    // keep current state on error
  }
}

export function useUvAvailability() {
  return { uvAvailable, uvPath, checkUvAvailable, recheckUvAvailable }
}

import { onUnmounted } from "vue"
import { onEvent } from "@/bridge"

export function useBridge() {
  const cleanups: (() => void)[] = []

  function on<T = unknown>(event: string, callback: (detail: T) => void) {
    const off = onEvent<T>(event, callback)
    cleanups.push(off)
    return off
  }

  function off(_event: string) {
    // Remove all listeners for a specific event
    const idx = cleanups.findIndex((fn) => {
      fn()
      return true
    })
    if (idx >= 0) {
      cleanups.splice(idx, 1)
    }
  }

  function cleanup() {
    cleanups.forEach((fn) => fn())
    cleanups.length = 0
  }

  onUnmounted(cleanup)

  return { on, off, cleanup }
}

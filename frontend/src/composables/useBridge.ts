import { onUnmounted } from "vue"
import { onEvent } from "@/bridge"

interface Registration {
  event: string
  cleanup: () => void
}

export function useBridge() {
  const registrations: Registration[] = []

  function on<T = unknown>(event: string, callback: (detail: T) => void) {
    const cleanup = onEvent<T>(event, callback)
    registrations.push({ event, cleanup })
    return cleanup
  }

  function off(event: string) {
    for (let i = registrations.length - 1; i >= 0; i--) {
      if (registrations[i].event === event) {
        registrations[i].cleanup()
        registrations.splice(i, 1)
      }
    }
  }

  function cleanup() {
    registrations.forEach((r) => r.cleanup())
    registrations.length = 0
  }

  onUnmounted(cleanup)

  return { on, off, cleanup }
}

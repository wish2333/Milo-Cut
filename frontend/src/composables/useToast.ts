import { ref } from "vue"

export interface Toast {
  id: number
  message: string
  type: "info" | "success" | "error"
  duration: number
}

/**
 * R9.5: toast stack policy -- at most MAX_VISIBLE_TOASTS visible at once
 * (oldest dropped) and an identical message within
 * TOAST_HIGH_FREQ_COOLDOWN_MS is swallowed (high-frequency events must not
 * stack-spam the corner).
 */
export const MAX_VISIBLE_TOASTS = 3
export const TOAST_HIGH_FREQ_COOLDOWN_MS = 500

const toasts = ref<Toast[]>([])
let nextId = 0
let lastMessage = ""
let lastShownAt = 0

export function useToast() {
  function showToast(
    message: string,
    type: "info" | "success" | "error" = "info",
    duration = 3000,
  ) {
    const now = Date.now()
    if (message === lastMessage && now - lastShownAt < TOAST_HIGH_FREQ_COOLDOWN_MS) {
      return // high-frequency cooldown: identical message, still warm
    }
    lastMessage = message
    lastShownAt = now

    const id = nextId++
    toasts.value = [...toasts.value, { id, message, type, duration }].slice(-MAX_VISIBLE_TOASTS)

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration)
    }
  }

  function removeToast(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return {
    toasts,
    showToast,
    removeToast,
  }
}

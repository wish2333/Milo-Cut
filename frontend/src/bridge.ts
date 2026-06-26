/** Core bridge functions for communicating with the Python backend. */

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  code?: string
}

function getRawApi(): PyWebViewApi {
  const pw = window.pywebview
  if (!pw || !pw.api) {
    throw new Error("pywebview API not available. Wait for pywebview to initialize.")
  }
  return pw.api
}

/**
 * Poll until the pywebview bridge is fully ready.
 *
 * Resolves only when *both* signals are true:
 *
 * 1. ``window.pywebview.api`` is populated (js_api injected).
 * 2. ``window.__BRIDGE_READY__`` is set by the backend's ``on_loaded``
 *    handler (fired after the ``loaded`` event).
 *
 * Checking only (1) is insufficient: pywebview injects ``js_api`` before
 * the ``loaded`` event fires, and calls made in that window are silently
 * dropped by WebKit (pywebview issue #431). Waiting for the explicit
 * ready flag guarantees the tick loop is draining the queue.
 */
export function waitForPyWebView(timeout = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now()
    const check = () => {
      if (window.pywebview?.api && window.__BRIDGE_READY__) {
        resolve()
        return
      }
      if (Date.now() - start > timeout) {
        reject(new Error("pywebview bridge did not initialize within timeout"))
        return
      }
      setTimeout(check, 50)
    }
    check()
  })
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`Bridge call timed out after ${ms}ms`)), ms),
    ),
  ])
}

/**
 * Call an ``@expose``-decorated Python method and return the typed result.
 *
 * ```ts
 * const res = await call<string[]>("get_items")
 * if (res.success) console.log(res.data)
 * ```
 */
export async function call<T = unknown>(
  method: string,
  ...args: unknown[]
): Promise<ApiResponse<T>> {
  // Defensive fallback: if a component fires a call before the bridge's
  // ready flag is set (e.g. an early mount that bypassed App.vue's
  // waitForPyWebView gate), wait for readiness first instead of letting
  // the call be silently dropped by WebKit.
  if (!window.__BRIDGE_READY__) {
    await waitForPyWebView().catch(() => {
      // waitForPyWebView already rejects with a descriptive error;
      // fall through so getRawApi() can surface its own message.
    })
  }
  const api = getRawApi()
  if (!(method in api)) {
    return { success: false, error: `Method '${method}' not found on bridge` }
  }
  return withTimeout(
    api[method](...args) as Promise<ApiResponse<T>>,
    30_000,
  )
}

/**
 * Listen for events dispatched by ``Bridge._emit()`` from the Python side.
 *
 * Event names are prefixed with ``pywebvue:``. Returns a cleanup function
 * that removes the listener.
 *
 * ```ts
 * const off = onEvent<{ percent: number }>("progress", (detail) => {
 *   console.log(detail.percent)
 * })
 * // later:
 * off()
 * ```
 */
export function onEvent<T = unknown>(
  name: string,
  handler: (detail: T) => void,
): () => void {
  const event = `pywebvue:${name}`
  const listener = (e: Event) => {
    handler((e as CustomEvent).detail)
  }
  window.addEventListener(event, listener)
  return () => window.removeEventListener(event, listener)
}

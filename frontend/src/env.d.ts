/** pywebview injects `window.pywebview` at runtime. */

/** Vite `?raw` imports (vite/client types are not referenced in this project). */
declare module "*?raw" {
  const content: string
  export default content
}

interface ImportMetaEnv {
  readonly VITE_DEMO_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface PyWebViewApi {
  [method: string]: (...args: unknown[]) => Promise<ApiResponse<unknown>>;
}

interface PyWebView {
  api: PyWebViewApi;
}

interface Window {
  pywebview?: PyWebView;
  /** Set by the backend's ``on_loaded`` handler once the bridge is ready. */
  __BRIDGE_READY__?: boolean;
}

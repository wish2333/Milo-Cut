/** pywebview injects `window.pywebview` at runtime. */

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

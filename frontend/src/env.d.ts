/** pywebview injects `window.pywebview` at runtime. */

interface PyWebViewApi {
  [method: string]: (...args: unknown[]) => Promise<ApiResponse<unknown>>;
}

interface PyWebView {
  api: PyWebViewApi;
}

interface Window {
  pywebview?: PyWebView;
}

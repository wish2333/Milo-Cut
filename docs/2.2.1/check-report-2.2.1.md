# v2.2.1 检查报告 — macOS 首次启动首页/设置页/LLM 页空白

## 一、问题现象

打包成 `.app` 在 macOS 上首次启动时，多个页面同时呈现"空白/检测失败"：

- 首页（WelcomePage）：不显示最近项目列表
- 设置页（SettingsModal）
  - 检测不到 FFmpeg / FFprobe
  - 检测不到数据目录
  - 检测不到 ASR 引擎（插件列表空）
  - 硬件编码器列表空、镜像列表空
- LLM 页：完全空白（依赖 `settings` 与 `promptsData`，两者均为 null）
- 应用日志（`~/Library/Application Support/MiloCut/data/logs/app_*.log`）无任何 ERROR / WARNING
- Terminal 直接运行 `Milo Cut.app/Contents/MacOS/milo-cut`，stderr 也无任何异常

**关键症状**：用户**打开任意一个媒体文件后**，上述所有内容恢复正常。

## 二、调查范围

阅读了以下文件全量代码路径：

- `main.py`（入口、`_fix_macos_path`、`MiloCutApi`、`__main__` 启动序列）
- `pywebvue/app.py`、`pywebvue/bridge.py`（窗口创建、`loaded` 事件、tick 循环、`_emit`）
- `core/paths.py`、`core/config.py`、`core/logging.py`（数据目录、设置、日志）
- `core/ffmpeg_service.py`（`_find_ffmpeg` 优先级链）
- `core/project_service.py`（`get_recent_projects`）
- `core/plugin_manager.py`（`PluginManager.__init__`、`list_plugins`）
- `frontend/src/main.ts`、`frontend/src/App.vue`、`frontend/src/bridge.ts`
- `frontend/src/pages/WelcomePage.vue`、`frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/workspace/SettingsModal.vue`
- `frontend/src/composables/usePluginManager.ts`、`useLlmSettings.ts`、`useUvAvailability.ts`、`useBridge.ts`
- `app.spec`、`build.py`（打包配置）

## 三、排除的候选根因

| 候选 | 排除理由 |
|---|---|
| 数据目录路径不一致（首次 vs. 之后） | `get_data_dir` 每次调用都 `mkdir(parents=True, exist_ok=True)`，且 macOS 系统模式路径固定为 `~/Library/Application Support/MiloCut/data`，无分支差异 |
| `_fix_macos_path()` 超时导致 PATH 缺失 | 该函数是同步 `subprocess.run(timeout=5)`，在 `main.py` 模块加载阶段执行完毕，远早于前端任何调用。即使超时，PATH 缺失只会让 `_find_ffmpeg` 失败，**无法解释最近列表、LLM 页、镜像列表同时为空** |
| `MiloCutApi` 未初始化完成 | `api = MiloCutApi()` 在 `app.run()` 之前完成，bridge HTTP 服务也已启动 |
| Python 端抛异常 | 用户确认 Terminal 启动无 stderr 输出，日志文件也无异常 |
| 模块级状态被污染 | `useLlmSettings` 的模块级 ref 是共享但只读语义；`usePluginManager` 每次返回新实例 |

## 四、根因（高置信度）

**`pywebview` 已知竞态 — 在 `window.events.loaded` 触发前调用 `js_api` 桥，调用会被 WebKit 静默丢弃或挂起。**

参考上游 issue：[pywebview #431 — "Main window failed to start" when using js_api](https://github.com/r0x0r/pywebview/issues/431)。issue 明确指出：**在 `loaded` 或 `shown` 事件触发前调用任何 `js_api` 方法都会失败**，且失败模式是静默丢失，不一定抛异常。

### 4.1 代码证据

**前端 `frontend/src/bridge.ts:22-38`** 的 `waitForPyWebView` 仅轮询 `window.pywebview.api` 是否存在：

```ts
export function waitForPyWebView(timeout = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now()
    const check = () => {
      if (window.pywebview?.api) {   // ← 只检查存在性
        resolve()
        return
      }
      // ...
    }
    check()
  })
}
```

**后端 `pywebvue/app.py:117-130`** 的 `on_loaded` 回调在 `loaded` 事件触发后才启动 tick 循环，**但完全没有给前端设置任何"桥已就绪"标志**：

```python
def on_loaded() -> None:
    # ... drop handler
    window.evaluate_js(
        f"(function loop() {{"
        f"  window.pywebview.api.tick()..."
        f"}})();"
    )

window.events.loaded += on_loaded
```

pywebview 在 `webview.create_window(js_api=...)` 时就把 `window.pywebview.api` 注入到 JS 上下文，**这一刻早于 `loaded` 事件**（前者只要 JS 上下文创建即可，后者需要 DOM 与资源全部 ready）。两者之间的窗口期里：

- 前端轮询到 `window.pywebview.api` → resolve → mount App
- `App.vue` `ready.value = true` → 渲染 `WelcomePage`
- `WelcomePage` 中 `<SettingsModal>`（**无 `v-if`**）立即 mount，`onMounted` 并发发起 10+ 调用：
  - `get_settings`、`get_ffmpeg_info`、`detect_gpu_encoders`、`get_encoder_metadata`
  - `pluginManager.listPlugins()`、`pluginManager.listModels()`、`pluginManager.listModelMirrors()`
  - `get_plugin_data_dir`、`detect_gpu`、`list_mirrors`
  - `loadPrompts()`、`loadPresets()`
- 这些调用全部在 `loaded` 事件之前发出 → **被 WebKit 桥丢弃** → 后端无任何异常与日志 → 前端 `Promise.all` 一直等到 30s 超时 → 数据保持 null

### 4.2 "打开文件后正常"的解释

| 时序 | 后端 / 桥 | 前端 |
|---|---|---|
| T1 | `create_window` 注入 `window.pywebview.api` | main.ts 轮询命中 → resolve |
| T2 | DOM 加载完成，触发 `loaded` → tick 循环启动 | App.vue mount、WelcomePage + SettingsModal mount，发起 10+ 调用 |
| T3 | **桥还没 ready，调用被丢弃** | 所有 onMounted 的 await 等到 30s 超时，状态保持 null |
| T4 | 桥完全就绪 | 用户点击"选择文件"→ `select_files`（用户交互调用）成功 |
| T5 | `probe_media`、`create_project` 等正常工作 | 进入 WorkspacePage |
| T6 | 桥持续稳定 | WorkspacePage 的 SettingsModal 重新 mount，onMounted 再次发起调用 → 全部成功 |

完美匹配用户所有症状：无错误、无日志、所有页面同时空白、打开文件后恢复。

## 五、修复方案

### 5.1 主修复 — 让"桥就绪"信号显式可观察

**后端 `pywebvue/app.py:_setup_bridge`**：`on_loaded` 中通过 `evaluate_js` 设置一个标志位，并 emit 一个事件：

```python
def on_loaded() -> None:
    from webview.dom import DOMEventHandler
    doc = window.dom.document
    handler = DOMEventHandler(self._bridge._on_drop, prevent_default=True)
    doc.on("drop", handler)

    # 标记桥完全就绪，前端 waitForPyWebView 会等待此标志
    window.evaluate_js("window.__BRIDGE_READY__ = true;")

    window.evaluate_js(
        f"(function loop() {{"
        f"  window.pywebview.api.tick()"
        f"    .catch(e => console.error('pywebvue.tick error:', e))"
        f"    .finally(() => setTimeout(loop, {self._tick_interval}));"
        f"}})();"
    )
```

**前端 `frontend/src/bridge.ts:waitForPyWebView`**：除检查 api 存在，再轮询 `window.__BRIDGE_READY__`：

```ts
export function waitForPyWebView(timeout = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now()
    const check = () => {
      if (window.pywebview?.api && (window as any).__BRIDGE_READY__) {
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
```

**类型补充 `frontend/src/env.d.ts`**：

```ts
interface Window {
  pywebview?: PyWebView;
  __BRIDGE_READY__?: boolean;
}
```

### 5.2 次要优化 — SettingsModal 延迟挂载

`WelcomePage.vue:154-157` 和 `WorkspacePage.vue:2190-2193` 当前都让 `<SettingsModal>` 始终挂载，导致冷启动时即便用户不打开设置页，也会发起一遍沉重的初始化调用风暴。

改为 `v-if="showSettings"` / `v-if="showSettingsModal"` 包裹，让 SettingsModal 只在用户真正点开设置时才 mount。同时考虑 SettingsModal 关闭后是否保留状态——若需要保留，可在外层保留一个 wrapper 控制销毁。

> 注意：此项只是减小冷启动负载与 blast radius，**不能替代 5.1**。即使做了 5.2，桥竞态依旧存在，只是触发概率降低。

### 5.3 防御性补充 — 调用层兜底

可选：在 `bridge.ts:call` 里，如果 `__BRIDGE_READY__` 还没置位，先 `await waitForPyWebView()` 再发起实际调用。这是对将来某个新组件绕过 App.vue 的早期调用做兜底。

## 六、验证方法

### 6.1 快速验证根因（不改代码）

临时在 `frontend/src/main.ts` 的 `waitForPyWebView().then(...)` 之前塞入固定延迟：

```ts
await new Promise(r => setTimeout(r, 1500))  // 临时
waitForPyWebView().then(() => createApp(App).mount("#app"))
```

重新打包 `.app`，**若延迟后首次启动一切正常，则根因 100% 坐实**。

### 6.2 修复后回归用例

1. 全新 macOS 环境安装（清空 `~/Library/Application Support/MiloCut/`）
2. 启动 `.app`，**立刻**（不点任何按钮）确认：
   - 首页最近列表正确显示（若有历史项目）
   - 打开设置 → FFmpeg / 数据目录 / 引擎 / 镜像 全部正确检测
   - 切到 LLM 页 → Provider / API Key / Base URL / 提示词编辑区正常渲染
3. 重启应用 5 次，每次都正常
4. 用 Terminal 启动 `Milo Cut.app/Contents/MacOS/milo-cut`，stderr 无异常

### 6.3 平台回归

虽然用户只报了 macOS，Windows / Linux 也建议跑一遍——`loaded` 事件竞态在所有平台都存在，只是触发概率不同。

## 七、风险与影响面

- **5.1 改动**影响所有平台（不止 macOS）。但 `loaded` 事件是 pywebview 跨平台契约，新行为对所有平台都更稳健。
- `__BRIDGE_READY__` 是新增全局，不破坏现有 API。
- 若 `loaded` 事件本身在某个边缘场景不触发（比如 WebKit 加载本地 `file://` 的极端情况），`waitForPyWebView` 的 10s 超时仍生效，会展示 bridge error 页面，行为退化为"显式失败"而非"静默挂起"。

## 八、参考

- [pywebview Issue #431 — WebViewException "Main window failed to start" when using js_api](https://github.com/r0x0r/pywebview/issues/431)
- [pywebview JavaScript–Python Bridge Documentation](https://pywebview.flowrl.com/guide/interdomain)
- [pywebview API Documentation](https://pywebview.flowrl.com/api/)

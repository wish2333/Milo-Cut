# v2.2.1 规格与实施记录

## 概述

v2.2.1 修复 macOS 首次启动时多个页面空白的竞态问题。

## BUG: macOS 首次启动首页/设置页/LLM 页空白

### 问题

打包成 `.app` 在 macOS 上首次启动时：
- 首页（WelcomePage）不显示最近项目列表
- 设置页所有检测项空白（FFmpeg、数据目录、ASR 引擎、编码器、镜像）
- LLM 页完全空白
- 无任何错误日志或 stderr 异常

**关键症状**：用户打开任意媒体文件后，上述所有内容恢复正常。

### 根因

**pywebview 已知竞态** — 在 `window.events.loaded` 触发前调用 `js_api` 桥的方法，调用会被 WebKit 静默丢弃（参考 [pywebview issue #431](https://github.com/r0x0r/pywebview/issues/431)）。

具体时序：
1. `webview.create_window(js_api=...)` 在 JS 上下文创建时即注入 `window.pywebview.api`，远早于 `loaded` 事件
2. 前端 `waitForPyWebView()` 仅轮询 `window.pywebview.api` 是否存在 — 命中，立即 resolve
3. App.vue mount、WelcomePage + SettingsModal mount，发起 10+ 桥调用（`get_settings`、`get_ffmpeg_info`、`detect_gpu_encoders`、`listPlugins` 等）
4. 此时 `loaded` 事件尚未触发，所有调用被 WebKit 桥静默丢弃
5. 后端无任何执行、无异常、无日志
6. 前端 `Promise.all` 等待 30s 超时，数据保持 `null`
7. 用户交互（选择文件）在 `loaded` 之后发起，桥已就绪，调用成功
8. WorkspacePage 重新挂载 SettingsModal，再次发起调用 → 全部成功

### 修复

#### 5.1 主修复 — 桥就绪信号显式可观察

**后端** `pywebvue/app.py:on_loaded`：
- 在启动 tick 循环之前，通过 `evaluate_js` 设置 `window.__BRIDGE_READY__ = true;`
- 前端可据此精确判断后端桥已就绪（tick 循环已启动、消息队列已开始 drain）

**前端** `frontend/src/bridge.ts:waitForPyWebView`：
- 同时轮询 `window.pywebview?.api` 与 `window.__BRIDGE_READY__`
- 两个条件都满足后才 resolve，缺一不可
- 轮询间隔由 100ms 缩至 50ms

**类型** `frontend/src/env.d.ts`：
- `Window` 接口新增 `__BRIDGE_READY__?: boolean;`
- `bridge.ts` 中删除 `(window as any)` 类型断言，使用类型化的 `window.__BRIDGE_READY__`

#### 5.2 次要优化 — SettingsModal 延迟挂载

`WelcomePage.vue` 和 `WorkspacePage.vue` 两处的 `<SettingsModal>` 此前始终挂载（无 `v-if`），导致冷启动时即便用户不打开设置页，其 `onMounted` 也会并发发起 10+ 桥调用，增加竞态窗口期内的调用数量。

改为 `v-if="showSettings"` / `v-if="showSettingsModal"` 包裹，使 SettingsModal 仅在用户打开设置时才 mount 并发起调用。

> 此项只是缩小 blast radius，**不能替代 5.1**。即使做了 5.2，桥竞态依旧存在，只是触发概率降低。

#### 5.3 防御性补充 — call 层兜底

在 `bridge.ts:call()` 入口处检查 `window.__BRIDGE_READY__`，若未置位则先 `await waitForPyWebView()`。对将来某个新组件绕过 `App.vue` 的早期调用做兜底。

### 改动文件

| 文件 | 改动 |
|------|------|
| `pywebvue/app.py` | `on_loaded` 中新增 `window.evaluate_js("window.__BRIDGE_READY__ = true;")` |
| `frontend/src/bridge.ts` | `waitForPyWebView` 两信号轮询；`call()` 入口未就绪等待；类型化 `__BRIDGE_READY__` |
| `frontend/src/env.d.ts` | `Window` 接口新增 `__BRIDGE_READY__?: boolean` |
| `frontend/src/pages/WelcomePage.vue` | `<SettingsModal>` 添加 `v-if="showSettings"` |
| `frontend/src/pages/WorkspacePage.vue` | `<SettingsModal>` 添加 `v-if="showSettingsModal"` |
| `docs/2.2.1/record-2.2.1.md` | 本记录 |

### 验证

| 项目 | 结果 |
|------|------|
| `vue-tsc --noEmit` 类型检查 | 通过 |
| `vite build` 构建 | 成功 |
| `vitest` 前端单测 | **171 全通过**（14 文件，含 `SettingsModal.test.ts` 6 个） |
| `app.py` 语法检查 | 通过 |

### 仍需用户验证

1. **macOS 全新环境回归**：清空 `~/Library/Application Support/MiloCut/` 后冷启动，确认所有页面正常；重启 5 次均正常
2. **平台回归**：Windows / Linux 运行一遍 — `loaded` 事件竞态跨平台存在，只是触发概率不同

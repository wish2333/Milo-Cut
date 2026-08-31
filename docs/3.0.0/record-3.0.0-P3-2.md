# Record: P3-2 M8-2 WorkspacePage 瘦身

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M8-2 / PRD C2 / plan P3-2 / migration-M8.md
> 状态: **步骤 a + b 完成**（本记录），步骤 c（handler 归口）随后续提交

## 步骤 a —— 3 个内联 popover 抽组件（纯搬移）

| 文件 | 说明 |
|---|---|
| `frontend/src/components/workspace/popovers/TranscribeSettingsPopover.vue`（新） | 转写设置弹层（引擎/模型/语言/设备/算力/VAD）。共享状态经 props 下行 + `defineModel(required)` 逐字段绑定（8 个 v-model），`save` 事件上行 |
| `frontend/src/components/workspace/popovers/SilenceSettingsPopover.vue`（新） | 静音检测阈值弹层（5 个 defineModel + save） |
| `frontend/src/components/workspace/popovers/SubtitleTrimSettingsPopover.vue`（新） | 字幕间隙 padding 弹层（单 defineModel） |
| `WorkspacePage.vue` | 3 处弹层模板块（原 :1826-1949/:1977-2054/:2088-2104）替换为组件调用；`show*` 开关、工具栏按钮、outside-click closest 判定、保存后自动关闭全部原地保留 |

实现决策：defineModel 逐字段而非传对象引用——eslint `flat/recommended` 启用 `vue/no-mutating-props`，弹层内直改 prop 对象嵌套字段会报错；逐字段 defineModel 保持模板 v-model 形态且类型安全。

## 步骤 b —— `useAsrEngines.ts` 抽取（消除双实现）

| 文件 | 说明 |
|---|---|
| `frontend/src/composables/useAsrEngines.ts`（新） | ASR 引擎域单一事实来源：`asrEngine/asrPluginId/asrSettingsPerEngine/installedEngines/modelList` + `hasInstalledEngines/isMlx/supportsGpu/availableModels/computeTypeOptions/currentSettings` computed + `loadAsrSettings/loadInstalledEngines/validateModelSize/saveAsrSettings/checkEngineReady` + 两个 watch（pluginId 派生引擎与设备/算力联动、engine 默认值填充）。逻辑自 WorkspacePage 原样搬移 |
| `WorkspacePage.vue` | ASR 域约 190 行删除，改为 composable 解构；idle 启动序列改 `ensureLoaded()`；`handleSaveAsrSettings` wrapper 保留"保存成功后关弹窗"的 UI 副作用（持久化逻辑入 composable）；handleTranscribe 链路不变 |
| `settings/ExportSettingsTab.vue` | ASR Settings 段改为绑定共享域：引擎切换经 `asrPluginId` 写共享状态（工作区弹窗即时跟随）+ `deriveEngineChangePatch`（原 handleEnginePluginChange 逻辑迁入 composable）emit AppSettings patch（modal 保存持久化路径不变）；model/language/device/compute/VAD 各字段同步写共享状态 + emit 对应持久化键 |
| `settings/AiEngineSettingsTab.vue` | 插件安装/卸载、模型下载/删除成功后调 `refreshAfterPluginChange()`——设置侧变更即时进入共享域，工作区引擎选择器与就绪徽标免重启跟随 |
| `composables/useAsrEngines.test.ts`（新） | 4 条单源验收：双消费者引用同一性（同一 ref 实例）、插件切换派生（engine 保持 + device 降级）、engine 前缀持久化键（whisper_* 落键、无 qwen_*/asr_compute_type 残留）、patch 派生（含 macOS 平台条件分支） |

### 关键设计

- **模块级单例**：状态与 watcher 在模块层注册一次（应用生命周期 == 单例生命周期）；`useAsrEngines()` 每次调用返回同一组 ref——双 UI"改一处两处生效"的结构性保证（测试以 `toBe` 引用同一性锁定）。
- **启动顺序契约封装**：原 `loadInstalledEngines() // Must run BEFORE loadAsrSettings` 的顺序要求封装进单飞 `ensureLoaded()`（并发调用共享一次加载序列）；ExportSettingsTab 挂载时调用同一入口，Welcome 阶段开设置也能拿到完整引擎数据。
- **bridge 直连**：composable 内 `list_plugins/check_plugin_status/list_models` 直连 bridge（usePluginManager 同款薄封装的忠实拷贝），避免 `usePluginManager()` 在组件外实例化触发 `useBridge` 的 `onUnmounted` 警告。
- **持久化双路径保持**：工作区弹窗保存 = `saveAsrSettings()` 立即持久化（原行为）；设置侧 = 共享状态即时 + patch 进 modal `settings`，由 modal 保存统一持久化（原行为）。两条路径写同一状态源，不再各自为政。

### 对 plan/SPEC 的偏差记录

1. **"SettingsModal AiEngine tab 接入"落实位置**：M8-1 拆分后 ASR 设置段实际位于 `ExportSettingsTab`（原 SettingsModal 导出 tab 内的 "ASR Settings" 区），双实现消除的主战场是 WorkspacePage ↔ ExportSettingsTab；AiEngineSettingsTab（插件/模型管理器）以 `refreshAfterPluginChange()` 钩子接入。migration-M8.md 已按实际落点勾销。
2. **a+b 单批提交**：步骤 a（popover 抽取）与 b（ASR 域抽取）共用 WorkspacePage.vue 同一文件面，拆分提交需 hunk 级手术且无独立回滚价值；沿用 P2-1 Day3 单批提交先例，每点差异可逐行审阅。
3. **handleTranscribe 弹窗关闭**：原 `saveAsrSettings` 无条件在成功后关弹窗（转写路径也触发）；现转写路径走同一 `handleSaveAsrSettings` wrapper，行为逐字节一致。

## 验证命令与实际输出（步骤 a+b 后）

```
cd frontend && bunx vue-tsc --noEmit   -> 0 错误
cd frontend && bun run test            -> 318 passed (30 files)（314 + 4 useAsrEngines）
cd frontend && bun run build           -> vue-tsc + vite 通过
bunx eslint <触及文件>                 -> 0 errors（2 个 v-html warning 为 M9-3 已登记存量）
uv run pytest                          -> 550 passed
uv run ruff check tests/test_asr_gui_e2e.py -> All checks passed!
```

体积：WorkspacePage.vue 96.5KB → **79.5KB**（a: −7.6KB，b: −9.4KB；目标 <40KB 待步骤 c）。

测试随迁：`test_asr_gui_e2e.py::test_workspace_handle_transcribe_saves_first` 改大小写不敏感匹配（兼容 `handleSaveAsrSettings` wrapper 命名），"先持久化后转写"不变量断言保留。

## 未验证边界（归批次双平台冒烟）

- 三个 popover 手感（开合/外点关闭/保存后自动关闭/保存值回填）
- 双 UI 同步实效：工作区弹窗改引擎 → 设置侧跟随；设置侧装插件 → 工作区选择器免重启跟随（单测已锁结构，真机手感待验）
- 转写全链路（选引擎 → 保存 → 启动 → 设置持久化核对）

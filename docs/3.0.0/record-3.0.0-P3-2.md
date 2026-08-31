# Record: P3-2 M8-2 WorkspacePage 瘦身

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M8-2 / PRD C2 / plan P3-2 / migration-M8.md
> 状态: **步骤 a + b + c 全部完成**；验收标准 "WorkspacePage.vue < 40KB" **未达标（61.3KB）**，偏差升级用户决策（见文末）

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

## 步骤 c —— `useWorkspaceActions.ts` handler 归口（provide/inject）

| 文件 | 说明 |
|---|---|
| `frontend/src/composables/useWorkspaceActions.ts`（新） | 五组 action 枢纽（playback 11 / timeline 7 / edit 15 / llm 13+diff 展示簇 / project 5，共 51 个具名动作）。handler bodies 自页面**原样搬移**；页面状态经显式 `WorkspaceActionsDeps`（约 45 项）注入；`provideWorkspaceActions`/`useWorkspaceActions`（WORKSPACE_ACTIONS_KEY）供子组件树注入 |
| `WorkspacePage.vue` | 45 个 handler 函数体 + diff 展示簇（aggregateDiffTokens/renderDiff/escapeHtml/diffCache/watch(pendingCorrections)/ensureDiff/categoryLabel）删除；同名解构自 actions（模板 35 处事件绑定零改动）；`provideWorkspaceActions(actions)` 接线；`regenPollTimer` let → `regenPoll` 状态对象（轮询体入 composable，卸载清理留页内） |

### 步骤 c 实现决策

1. **模板零改动策略**：actions 以 handler 原名扁平返回（分组以接口注释 + migration-M8 分组为准），页面解构同名局部量——35 处模板事件绑定与全部子组件 props/emits 原样保留，回归面收敛到 script 搬移本身。provide/inject 通道已就绪，子组件改注入为后续渐进项。
2. **undo/键盘按清单保留页内**：handleGlobalKeydown/handleKeydown/handleUndo/handleRedo/recoverFromUndoFailure/handleClickOutside/handleToggleSearchBar 未动（migration-M8 "undo/键盘不归口"）；键盘依赖的动作（handleTogglePlay/handleSaveProject/handleMergeSelected/markSelectedForDeletion 等）经同名解构引用 actions，行为一致。
3. **红线核对**：undo pushSnapshot 三迁移点 A1（导入 SRT）/A2（批量标记，操作前 push before-state）/A3（新增段落）随组搬移，行内注释保留；`flushPendingUpdates` 前置调用在 handleSwitchTimeline/handleCreateTimeline 原样保留（搬运初版遗漏，类型检查后补回并以页面原文件 diff 复核）；`projectRef` computed get/set 双向绑定未绕过（actions 经 deps 引用页内 projectRef）。
4. **测试随迁**：`test_asr_gui_e2e.py::test_workspace_handle_transcribe_saves_first` 源目标改指 `useWorkspaceActions.ts`（handleTranscribe 随组迁入），"先持久化后转写"不变量断言保留。

## 体积对账（验收：WorkspacePage.vue < 40KB —— 未达标）

| 步骤 | 体积 | 减量 |
|---|---|---|
| 基线（beta.2 后） | 96.5KB / 2481 行 | — |
| a：3 popover 抽组件 | 88.9KB | −7.6KB |
| b：useAsrEngines 抽取 | 79.5KB | −9.4KB |
| c：useWorkspaceActions 归口 | **61.3KB** / 1642 行 | −18.2KB |

剩余构成：模板 ~620 行（约 24KB，五组之外的控件/布局）+ 页内保留域（undo/键盘 ~170 行、popover/搜索/重命名/确认弹窗 UI ~150 行、视频/波形加载与 watches ~150 行、composable 接线 ~250 行）。<40KB 需再移出约 21KB，超出本步既定范围（迁移清单明示 undo/键盘保留页内），需用户决策后续路径（见文末）。

## 验证命令与实际输出（步骤 c 后，全量）

```
cd frontend && bunx vue-tsc --noEmit   -> 0 错误
cd frontend && bun run test            -> 318 passed (30 files)
cd frontend && bun run build           -> vue-tsc + vite 通过
bunx eslint <触及文件>                 -> 0 errors（2 个 v-html warning 为 M9-3 已登记存量）
uv run pytest                          -> 550 passed
uv run ruff check <触及文件>           -> All checks passed!
```

测试随迁：`test_asr_gui_e2e.py::test_workspace_handle_transcribe_saves_first` 改大小写不敏感匹配（兼容 `handleSaveAsrSettings` wrapper 命名），"先持久化后转写"不变量断言保留。

## 未验证边界（归批次双平台冒烟）

- 三个 popover 手感（开合/外点关闭/保存后自动关闭/保存值回填）
- 双 UI 同步实效：工作区弹窗改引擎 → 设置侧跟随；设置侧装插件 → 工作区选择器免重启跟随（单测已锁结构，真机手感待验）
- 转写全链路（选引擎 → 保存 → 启动 → 设置持久化核对）
- 全局 keydown 回归：文本框内 Delete/方向键不被拦截、Esc/多选/Delete 手测清单（handleGlobalKeydown 未移动，风险面未扩大）

## ★ 验收偏差（升级用户决策）

**验收标准 "WorkspacePage.vue < 40KB" 未达标：实际 61.3KB。** 五组归口（本步全部既定范围）已交付且全量门禁绿；差距 ~21KB 位于计划明示保留页内的区域（undo/键盘、popover/搜索/确认弹窗 UI、加载与 watch 接线）与模板本体。按 plan §0 变更控制升级决策，可选路径：

1. **降级目标**：接受 "~60KB" 为 M8-2 里程碑（计划制定时未计入 M5/M6 给页面新增的 undo patch 通道与播放时钟接线约 150 行）
2. **继续修**：追加 M8-2d——子组件（Timeline/VideoControls/AIAssistantPanel/SuggestionPanel 等）改注入 actions 与共享状态，移除模板 props/emits 链（影响 ~8 个子组件及其测试，工作量 ≈1 天）
3. **模板拆分**：工具栏/弹窗区再抽组件（不改行为，纯搬移）

任一路径不阻塞 P3-3（M9）按序开工。

# Record: P3-1 M8-1 SettingsModal 拆分

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M8-1 / PRD C1 / plan P3-1

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/components/workspace/SettingsModal.vue` | 94.5KB/2033 行 → **6.4KB/169 行**（-93%）：仅保留 modal 外壳（ESC/close）、tab 切换、`get_settings` 加载、`handleSave`/`saving`/`statusMsg`、footer；模板渲染 5 个 tab 组件（`v-if` + `settings` 非空守卫） |
| `frontend/src/components/workspace/settings/GeneralSettingsTab.vue`（新） | 12.2KB：FFmpeg 路径/版本、硬件编码器徽标、静音检测阈值、代理视频、数据目录与清理 |
| `frontend/src/components/workspace/settings/AiEngineSettingsTab.vue`（新） | 19.9KB：uv 可用性覆盖层、模型目录、插件安装/卸载、模型下载/删除、GPU 检测、下载镜像（usePluginManager 实例本地 + useUvAvailability 单例共享） |
| `frontend/src/components/workspace/settings/LlmSettingsTab.vue`（新） | 22.8KB：provider/key/base_url/model/thinking/temperature/高级参数/Test Connection + 全部提示词与预设逻辑（自 SettingsModal 原样搬移） |
| `frontend/src/components/workspace/settings/PromptEditor.vue`（新） | 4.7KB 纯展示：功能选择器、简单/高级模式、参数 textarea、完整提示词覆盖、动作按钮；`preset-bar` 具名插槽保持预设栏在 section 内的原 DOM 位置 |
| `frontend/src/components/workspace/settings/PresetManager.vue`（新） | 3.1KB 纯展示：预设选择/应用/另存为/删除 + 内联保存输入 |
| `frontend/src/components/workspace/settings/ExportSettingsTab.vue`（新） | 17.6KB：ASR 默认值（engine/model/language/device/compute/VAD）+ 导出编码/码率/preset/CRF/分辨率/转场 + 硬件编码器探测（availableVideoCodecs） |
| `frontend/src/components/workspace/settings/ShortcutsSettingsTab.vue`（新） | 8.8KB 纯静态，零 props 零状态 |
| `frontend/src/components/workspace/SettingsModal.test.ts` | 重写：composable mock 补齐全 API 面（原 mock 仅 5 点且 `saveNewPreset` 与真实 `savePreset` 签名不符）；原 6 条断言语义不变；新增 3 条 M8-1 懒挂载测试 |
| `tests/test_asr_gui_e2e.py` | `test_settings_modal_uses_engine_prefixed_keys` 断言目标更新：引擎前缀键随拆分移入 ExportSettingsTab，改为对 SettingsModal.vue + settings/*.vue 拼合源码断言（意图不变） |

## tab 通信契约（props/emits）

- props 下行：`settings: AppSettings`（母壳守卫非空后渲染）、`saving: boolean`（仅 LlmSettingsTab，Test Connection 按钮态）
- emits 上行：`update(patch: Partial<AppSettings>)`（母壳浅合并进 settings）、`status(message, timeout)`（footer 状态条，timeout 0 表示不自动清除，沿用原各 handler 的 2s/3s/5s 值）、`busy(value: boolean)`（LlmSettingsTab 静默持久化期间镜像 saving，footer 按钮态与原行为一致）

## 实现决策（对 plan/SPEC 的偏差记录）

1. **各 tab 数据加载惰性化**：原实现 modal 挂载即加载全部 11 类数据（ffmpeg 信息/编码器/插件/模型/镜像/GPU/提示词等）；现随各 tab 首次挂载加载——非活跃 tab 零实例化零加载（验收标准 3 的直接实现）。副作用：`detect_gpu_encoders` 在 General（徽标）与 Export（编码列表）各调用一次（两 tab 都访问过时）；`listPlugins/listModels` 在 AiEngine 与 Export 各一次。均为毫秒级只读调用，属 M8-1 可接受代价，P3-2b `useAsrEngines` 抽取后自然收敛。
2. **PromptEditor/PresetManager 取纯展示形态**：提示词/预设全部状态与 handler 留在 LlmSettingsTab 原样搬移（零逻辑改写），子组件仅 props/emits——避免"预设另存需编辑区快照、预设应用需编辑区重载"的跨子组件状态回路，行为漂移风险最低。
3. **tab 懒挂载用 `v-if` 而非 defineAsyncComponent**：验收口径是"非活跃 tab 状态零实例化"（组件树），v-if 已结构性满足；不做代码分割（bundle 328KB 不变，拆分收益为源码体积与状态隔离）。
4. **tab 根守卫**：母壳 `v-if="activeTab === ... && settings"`——settings 加载前（单次 IPC 窗口）tab 区为空；原实现 general tab 会先显示 FFmpeg version "Not found" 再回填，实际不可感知。
5. **后端源码断言测试随迁**：`test_asr_gui_e2e` 的引擎前缀键断言读 SettingsModal.vue 单文件，拆分后键在 ExportSettingsTab——断言目标改为拼合源码，测试意图（设置 UI 必须用 engine 前缀键、禁 asr_compute_type 落键）零变化。

## 验证命令与实际输出

```
cd frontend && bun run test   -> 314 passed (29 files)（311 存量 + 3 M8-1；SettingsModal.test.ts 9 条）
cd frontend && bun run build  -> vue-tsc + vite 通过
bunx eslint <触及文件>        -> 0 问题
uv run pytest                 -> 550 passed（后端仅测试断言目标随迁，550 锚定不变）
uv run ruff check tests/test_asr_gui_e2e.py -> All checks passed!
```

体积验收（目标：Modal <15KB，tab <25KB）：

| 文件 | 体积 | 结果 |
|---|---|---|
| SettingsModal.vue | 94.5KB → **6.4KB** | ✅ |
| GeneralSettingsTab.vue | 12.2KB | ✅ |
| AiEngineSettingsTab.vue | 19.9KB | ✅ |
| LlmSettingsTab.vue | 22.8KB | ✅（最大） |
| ExportSettingsTab.vue | 17.6KB | ✅ |
| ShortcutsSettingsTab.vue | 8.8KB | ✅ |
| PromptEditor.vue / PresetManager.vue | 4.7KB / 3.1KB | （子组件） |

## 未验证边界

- ★ 各 tab 全部控件手测（保存/取消/回填）、非活跃 tab 零实例化的 Vue DevTools 组件树复核 → 批次双平台冒烟（懒挂载已有组件测试自动化锁定）
- Test Connection 静默持久化期间 footer "Saving..." 态（busy 镜像链路）→ 冒烟顺手确认

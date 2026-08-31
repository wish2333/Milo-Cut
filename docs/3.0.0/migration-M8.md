# M8 迁移清单 —— WorkspacePage 职责搬迁（P3-2）

> 基线: `dev-3.0.0` @ v3.0.0-base，WorkspacePage.vue 共约 2386 行。
> 方法: 与 `handle[A-Z]` grep 交叉核对，覆盖 WorkspacePage 全部 handler。

## 一、3 个内联 popover 抽组件（步骤 a，纯搬移）

| # | popover | 状态变量 | 模板块起始 | 抽出组件 |
|---|---|---|---|---|
| P1 | 转写设置 | `showTranscribeSettings`（:189） | :1732（`v-if="showTranscribeSettings && uvAvailable !== false"`） | `TranscribeSettingsPopover.vue` |
| P2 | 静音检测设置 | `showSilenceSettings`（:188） | :1883（`v-if="showSilenceSettings"`） | `SilenceSettingsPopover.vue` |
| P3 | 字幕修剪设置 | `showSubtitleTrimSettings`（:351） | :1994（`v-if="showSubtitleTrimSettings"`） | `SubtitleTrimSettingsPopover.vue` |

关联状态/事件关闭点: :756/:768（操作后自动关闭）、:1558-1559（`handleClickOutside` outside-click 关闭，迁移后需保留对该 popover 根元素的 closest 判定语义）。

- [x] P1 TranscribeSettingsPopover（纯模板+局部状态搬移；共享状态经 props + defineModel 逐字段下行，规避 vue/no-mutating-props）✅ 2026-08-31
- [x] P2 SilenceSettingsPopover（同上）✅
- [x] P3 SubtitleTrimSettingsPopover（单字段）✅

## 二、ASR 引擎域抽取（步骤 b，`useAsrEngines.ts`）

现状范围（WorkspacePage.vue，约 L247-700 区间）：

| 内容 | 行号（约） |
|---|---|
| `asrSettingsPerEngine` 每引擎设置存储 | :247-278 |
| device/compute 选项 computed（gpuOptions/cpuOptions/支持判定） | :280-320 |
| `asrEngine` / `asrPluginId` 状态 | :322-323 |
| `installedEngines` / `availableModels`（插件管理器过滤，ForcedAligner 排除） | :325-339 |
| `loadAsrSettings()`（settings 读写 + 双引擎默认值） | :600-650 |
| `loadInstalledEngines()` / 模型默认回退 | :660-685 |
| `watch(asrPluginId)` 引擎切换联动（device/compute 同步） | :686-700+ |
| 启动顺序依赖: `loadInstalledEngines()` 先于 `loadAsrSettings()`（:494-495） | — |

**双实现消除**: SettingsModal AiEngine tab 内有同域逻辑副本，抽取后两处同接 `useAsrEngines`。
验收用例: 修改 `useAsrEngines` 一处（如默认 model_size），WorkspacePage 与 SettingsModal 两 UI 同步生效。

- [x] 抽取 `useAsrEngines.ts`（保持启动顺序契约: engines 加载先于 settings 回填 → 封装为单飞 `ensureLoaded()`）✅ 2026-08-31 模块级单例状态 + watcher 一次注册；bridge 直连（list_plugins/check_plugin_status/list_models）免除组件外 usePluginManager 实例耦合
- [x] WorkspacePage 接入（ASR 域 ~190 行删除，popover/save/转写链路全部走 composable；saveAsrSettings 的 UI 副作用"关弹窗"留页内 wrapper `handleSaveAsrSettings`）✅
- [x] SettingsModal 侧接入 + 双 UI 生效验证用例 ✅ **落实位置偏差**: M8-1 拆分后 ASR 设置段实际在 `ExportSettingsTab.vue`（原 SettingsModal 导出 tab 内的 ASR Settings 区），故该 tab 绑定共享状态并同步 emit AppSettings patch（modal 保存路径不变）；`AiEngineSettingsTab`（插件/模型管理）经 `refreshAfterPluginChange()` 在安装/卸载/下载/删除后刷新共享域。双 UI 生效用例: `useAsrEngines.test.ts` 4 条（单例引用同一性/插件切换派生/engine 前缀持久化键/patch 派生）

## 三、handler 归口 `useWorkspaceActions.ts`（步骤 c，provide/inject）

`handle[A-Z]` 全量清单（grep 核对，2386 行版本行号）：

### 播放/视频组
| handler | 行号 | 归口 |
|---|---|---|
| handleRegenerateWaveform | :433 | actions.timeline |
| handleRequestProxy | :552 | actions.media |
| handleSeek / handleSetTime | :771/:777 | actions.playback |
| handleVideoLoaded / handleTimeUpdate | :782/:788 | actions.playback |
| handleTogglePlay / handleSeekTo / handleVolumeChange / handleRateChange / handleFullscreen | :792-:830 | actions.playback |

### 时间线组
| handler | 行号 |
|---|---|
| handleSwitchTimeline / handleCreateTimeline / handleDeleteTimeline | :843/:853/:905 |
| handleImportSrt | :931 |
| handleDetectSilence / handleClearSubtitles | :951/:956 |
| handleTranscribe | :967 |

### 编辑组
| handler | 行号 |
|---|---|
| handleToggleEditStatus | :923 |
| handleSegmentClickInSelection / handleToggleSelectionMode | :1078/:1114 |
| handleMergeSelected / handleSplitSegment | :1086/:1099 |
| handleUpdateText / handleUpdateTime | :1405/:1409 |
| handleSelectRange / handleAddSegment / handleDeleteSegment / handleSeekSegment | :1422-:1444 |
| handleSubtitleTrim / handleDeleteSubtitleTrimEdits / handleConfirmDeleteSilence | :1374-:1395 |

### LLM/纠错组
| handler | 行号 |
|---|---|
| handleConfirmAllSuggestions / handleRejectAllSuggestions | :1023/:1028 |
| handleStartSmartDelete / handleStartSubtitleCorrection / handleStartHighlight | :1035-:1053 |
| handleCancelSingle | :1070 |
| handleOpenSubtitleFullscreen | :1170 |
| handleAcceptCorrection / handleRejectCorrection / handleAcceptHighConfidence / handleClearCorrections | :1261-:1290 |
| handleRemoveHighlight / handleAddToHighlight | :1307/:1323 |

### 项目/设置组
| handler | 行号 |
|---|---|
| handleCloseProject / handleSaveProject / handleSettingsClosed / handleGoToSettings | :1450/:1357/:1351/:1301 |
| handleSearchReplace | :1415 |

### undo/键盘（保留在页内，不归口）
| handler | 行号 | 说明 |
|---|---|---|
| handleKeydown（window keydown） | :1337 | 组件级监听 |
| handleGlobalKeydown（document keydown） | :1464 | 全局快捷键；迁移后必须手测文本框内 Delete/方向键不被拦截 |
| handleUndo / handleRedo | :1563/:1573 | M5 后走 apply_undo 通道 |
| handleClickOutside | :1555 | popover 关闭时序 |

- [ ] 归口播放/视频组
- [ ] 归口时间线组
- [ ] 归口编辑组
- [ ] 归口 LLM/纠错组
- [ ] 归口项目/设置组
- [ ] 全局 keydown 回归（文本框内 Delete/方向键不被拦截；Esc/多选/Delete 手测清单全过）

## 红线（每步勾销时核对）

1. undo pushSnapshot 调用点按 `migration-M5.md` 逐一 diff 核对，不得因搬移丢失
2. `projectRef` computed get/set 双向绑定不得被绕过——子组件只经 action 层写
3. 全局 keydown（:1464-1554）与 SegmentBlocksLayer capture 监听时序回归

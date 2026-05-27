# Milo-Cut 1.1.0 Development Record

## Overview

1.1.0 版本聚焦于安全防护、技术债务清理和核心交互补齐。按审计计划 `audit-plan-1.1.0.md` 分 4 个 Sprint 执行。

## Branch

`dev-1.1.0` (from `main`)

## Sprint 1: 安全防护与技术债务清理

### Task 1.1: EditSummaryModal 接入导出流程

**目标**: 导出视频/音频时弹出删除摘要确认对话框，防止误删。

**修改文件**:
- `frontend/src/pages/ExportPage.vue`

**实现细节**:
- 导入 `EditSummaryModal` 组件和 `EditSummary` 类型
- 从 `useExport` 解构 `getExportSummary` 方法
- 新增 `showSummaryModal`、`exportSummary`、`pendingExportAction` 响应式状态
- 实现 `interceptExport()` 拦截器模式：调用 `getExportSummary()` 获取摘要，若 `delete_percent > 0` 则弹出确认对话框，否则直接执行
- 将 `handleExportVideo` 和 `handleExportAudio` 包装为拦截器调用（原逻辑移至 `executeExportVideo` / `executeExportAudio`）
- 模板中添加 `<EditSummaryModal>` 组件，绑定 `confirm` / `cancel` 事件

**拦截器流程**:
```
用户点击导出 -> interceptExport() -> getExportSummary()
  -> delete_percent > 0 -> 弹出 EditSummaryModal -> 确认 -> 执行导出
  -> delete_percent == 0 -> 直接执行导出
```

---

### Task 1.2: 版本号统一

**目标**: 消除 main.py 硬编码版本号，统一从 pyproject.toml 读取。

**修改文件**:
- `main.py`

**实现细节**:
- 新增 `_get_version()` 函数，实现 3 级兜底：
  1. `importlib.metadata.version("milo-cut")` — 开发环境 / pip install
  2. 读取 `pyproject.toml` — PyInstaller/Nuitka 打包后兜底
  3. 返回 `"unknown"` — 最终兜底
- `get_app_info()` 中 `"version": "0.1.0"` 替换为 `"version": _get_version()`
- 验证：`_get_version()` 返回 `"0.2.1"`，与 pyproject.toml / package.json 一致

**修正说明**: 架构师指出 `importlib.metadata` 在 PyInstaller/Nuitka 打包后可能不存在，必须加 `try-except` 兜底读取 `pyproject.toml`。

---

### Task 1.3: 媒体丢失重链接

**目标**: 打开项目时检测媒体文件存在性，丢失时弹出重定位对话框。

**修改文件**:
- `core/project_service.py` — 后端核心逻辑
- `main.py` — 桥接方法
- `frontend/src/components/workspace/RelinkMediaDialog.vue` — 新建组件
- `frontend/src/composables/useProject.ts` — composable 扩展
- `frontend/src/App.vue` — 主入口集成
- `frontend/src/pages/WelcomePage.vue` — 最近项目打开集成
- `tests/test_project_service.py` — 测试修复

**后端实现**:

1. 新增 `compute_media_fingerprint(path)` — 轻量级指纹（size + mtime SHA-256），O(1) 复杂度
2. 新增 `compute_media_hash_deep(path)` — 完整 SHA-256，仅重链接确认时使用
3. `open_project()` 修改：
   - 媒体文件不存在时返回 `{"success": false, "error": "MEDIA_NOT_FOUND", "data": {"path": ...}}`
   - 媒体文件存在时检查指纹匹配，不匹配则返回 `warnings: ["MEDIA_HASH_MISMATCH"]`
4. `create_project()` — 创建项目时自动计算媒体指纹
5. 新增 `relink_media(new_path)` — 更新媒体路径 + 指针，自动保存

**前端实现**:

1. `RelinkMediaDialog.vue` — 模态对话框组件：
   - 显示丢失路径
   - 浏览文件按钮调用 `select_files`
   - 确认重链接 / 取消按钮
2. `useProject.ts` 扩展：
   - `pendingRelinkPath` — 待重链接的丢失路径
   - `pendingProjectPath` — 待重链接的项目路径
   - `openProject()` 返回值类型扩展为 `boolean | "MEDIA_NOT_FOUND"`
   - `relinkMedia(newPath)` — 调用桥接 `relink_media` 并更新项目状态
   - `cancelRelink()` — 清除重链接状态
3. `App.vue` 集成：
   - 导入 `RelinkMediaDialog`
   - 拖放打开 project.json 时捕获 `MEDIA_NOT_FOUND` 错误
   - `onRelinkNeeded()` 处理 WelcomePage 的重链接事件
   - `handleRelink()` 调用 `relink_media` 并更新项目
4. `WelcomePage.vue` 扩展：
   - 新增 `relink-needed` 事件 emit
   - `openRecentProject()` 捕获 `MEDIA_NOT_FOUND` 并触发重链接流程

**测试修复**:
- 新增 `_create_media_file()` 辅助方法创建临时媒体文件
- 所有使用 `/tmp/test.mp4` 的测试替换为 `self._create_media_file(tmp_dir)`
- 原因：`create_project()` 现在计算指纹，需要真实文件路径

**修正说明**: 架构师指出视频文件动辄几 GB，全量 SHA-256 在打开项目时会导致数十秒阻塞。改用 `size + mtime` 组合哈希作为弱校验（O(1)），仅在重链接确认时才计算深度 Hash。

---

## Files Modified Summary

### Backend (core/)
- `project_service.py` — 媒体指纹计算、重链接方法、open_project 增强
- `main.py` — 版本号统一、relink_media 桥接方法

### Frontend (frontend/src/)
- `pages/ExportPage.vue` — EditSummaryModal 拦截器集成
- `pages/WelcomePage.vue` — MEDIA_NOT_FOUND 处理、relink-needed 事件
- `composables/useProject.ts` — 重链接状态管理
- `components/workspace/RelinkMediaDialog.vue` — 新建：媒体重定位对话框
- `App.vue` — 重链接对话框集成

### Tests
- `tests/test_project_service.py` — 临时媒体文件修复

## Verification

- [x] 后端 76 个测试全部通过
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] `_get_version()` 返回 `"0.2.1"` 与 pyproject.toml 一致
- [x] EditSummaryModal 组件在 ExportPage 中正确挂载
- [x] RelinkMediaDialog 组件在 App.vue 中正确挂载

---

## Sprint 2: 核心交互补齐

### Task 2.4: AppSettings 接口同步（前置任务）

**目标**: 消除 AppSettings 类型与 settings.json 的字段偏差，为设置页开发打基础。

**修改文件**:
- `frontend/src/types/edit.ts`
- `core/config.py`

**实现细节**:

1. `AppSettings` 接口从 8 个字段扩展至 22 个，覆盖 `settings.json` 全部字段：
   - 新增：`silence_margin`、`silence_subtitle_padding`、`trim_subtitles_on_silence_overlap`
   - 新增：`export_fade_duration`、`export_transition_mode`
   - 新增：`export_video_codec`、`export_audio_codec`、`export_audio_bitrate`、`export_preset`、`export_crf`、`export_resolution`
   - 新增：`export_ffmpeg_transitions`、`export_ffmpeg_fade_duration`、`export_ffmpeg_fade_mode`
2. `config.py` 的 `_DEFAULT_SETTINGS` 新增 9 个导出相关默认值（`export_video_codec: "libx264"` 等）
   - 原因：删除 `settings.json` 后导出设置不应丢失

---

### Task 2.1: 项目自动保存

**目标**: 编辑操作后 debounce 2s 自动保存，防止数据丢失。

**修改文件**:
- `frontend/src/composables/useProject.ts` — composable 增加 auto-save 逻辑
- `frontend/src/pages/WorkspacePage.vue` — 编辑主界面增加 auto-save 逻辑

**实现细节**:

1. `useProject.ts` 扩展：
   - 新增 `isSaving` ref 和 `saveTimer` 变量
   - `watch(isDirty)` 监听脏标记，debounce 2000ms 后自动调用 `saveProject()`
   - `isSaving` 锁防止并发保存
   - 暴露 `isSaving` 到返回对象

2. `WorkspacePage.vue` 直接集成（不通过 useProject composable）：
   - 导入 `EVENT_PROJECT_DIRTY` 和 `EVENT_PROJECT_SAVED` 事件
   - 新增 `isDirty`、`isSaving` refs 和 `saveTimer`
   - `onEvent(EVENT_PROJECT_DIRTY)` 设置脏标记
   - `onEvent(EVENT_PROJECT_SAVED)` 清除脏标记
   - `watch(isDirty)` debounce 2000ms 自动保存，成功后显示 toast
   - `handleSaveProject()` 改造：检查 `isSaving` 锁、清除待执行定时器、保存期间锁定

**自动保存流程**:
```
后端编辑操作 -> emit EVENT_PROJECT_DIRTY -> isDirty = true
  -> watch 触发 -> debounce 2000ms -> isSaving = true
  -> call("save_project") -> 成功 -> toast "Auto-saved"
  -> EVENT_PROJECT_SAVED -> isDirty = false -> isSaving = false
```

**手动保存流程**:
```
Ctrl+S -> handleSaveProject() -> 检查 isSaving 锁
  -> 清除 saveTimer -> isSaving = true -> call("save_project")
  -> 成功 -> toast "Project saved" -> isSaving = false
```

---

### Task 2.2: 字幕叠加预览

**目标**: 播放视频时底部显示当前字幕文本，使用 rAF + 游标优化。

**修改文件**:
- `frontend/src/components/workspace/SubtitleOverlay.vue` — 新建组件
- `frontend/src/pages/WorkspacePage.vue` — 集成组件

**实现细节**:

1. `SubtitleOverlay.vue` 核心算法：
   - `findCurrentSubtitle(time)` 三级查找策略：
     - 快速路径：检查游标当前位置（99% 帧命中，O(1)）
     - 前进检查：检查下一个字幕段（正常播放推进时命中）
     - 二分查找：跳转场景时定位字幕段（O(log N)）
   - `requestAnimationFrame` 循环驱动，非 `@timeupdate` 事件
   - play 时启动 rAF 循环，pause 时取消
   - 切换项目时重置游标
   - `pointer-events-none` 避免阻挡视频交互

2. `WorkspacePage.vue` 集成：
   - 导入 `SubtitleOverlay` 组件
   - 视频容器添加 `relative` 定位
   - `<SubtitleOverlay :segments="segments" :video-ref="videoRef" />` 作为 `<video>` 的兄弟节点

---

### Task 2.3: FFmpeg 管理与设置页

**目标**: FFmpeg 路径设置优先链、跨平台 GPU 检测、设置页 UI。

**修改文件**:
- `core/ffmpeg_service.py` — 路径解析优先链
- `main.py` — detect_gpu 跨平台改造、get_ffmpeg_info 桥接方法
- `frontend/src/components/workspace/SettingsModal.vue` — 新建设置页组件
- `frontend/src/pages/WorkspacePage.vue` — 设置入口集成

**后端实现**:

1. `ffmpeg_service.py` 路径解析改造：
   - 新增 `_get_settings_ffmpeg_path()` / `_get_settings_ffprobe_path()` 读取用户配置
   - `_find_ffmpeg()` / `_find_ffprobe()` 优先链：用户设置 > PATH > static_ffmpeg 包
   - 错误消息提示用户在 Settings 中配置或安装 FFmpeg

2. `main.py` detect_gpu 改造：
   - 废弃 `nvidia-smi` 硬编码，改用 `ffmpeg -hwaccels` 探测
   - 支持 NVIDIA (cuda/nvenc)、Intel (qsv)、Apple (videotoolbox)、AMD (amf)、VAAPI
   - `libsvtav1` 软件编码器始终可用

3. `main.py` 新增 `get_ffmpeg_info()` 桥接方法：
   - 返回 FFmpeg/FFprobe 路径和版本信息
   - 供设置页显示 FFmpeg 状态

**前端实现**:

1. `SettingsModal.vue` 设置页组件：
   - FFmpeg 区域：版本、路径显示 + 自定义路径输入 + 浏览按钮 + 下载按钮
   - 硬件编码器区域：GPU 检测结果标签展示
   - 静音检测区域：阈值、最小持续时间、边距、字幕填充、修剪开关
   - 导出区域：视频编码器、音频编码器、码率、预设、CRF、分辨率、FFmpeg 转场开关及参数
   - 保存/关闭按钮，保存时调用 `update_settings`

2. `WelcomePage.vue` 集成：
   - 导入 `SettingsModal` 组件
   - 标题区右上角添加齿轮图标按钮（`absolute` 定位）
   - `showSettings` ref 控制模态框显隐
   - 底部挂载 `<SettingsModal>` 组件

---

## Files Modified Summary (Sprint 2)

### Backend (core/)
- `config.py` — `_DEFAULT_SETTINGS` 新增 9 个导出默认值
- `ffmpeg_service.py` — 路径解析优先链（用户设置 > PATH > static_ffmpeg）
- `main.py` — detect_gpu 跨平台改造、get_ffmpeg_info 桥接方法

### Frontend (frontend/src/)
- `types/edit.ts` — AppSettings 接口扩展至 22 个字段
- `composables/useProject.ts` — auto-save 逻辑（isSaving + debounce 2s）
- `pages/WorkspacePage.vue` — auto-save 集成、SubtitleOverlay 集成
- `pages/WelcomePage.vue` — Settings 入口（齿轮按钮 + SettingsModal 挂载）
- `components/workspace/SubtitleOverlay.vue` — 新建：字幕叠加预览
- `components/workspace/SettingsModal.vue` — 新建：设置页模态框

## Verification (Sprint 2)

- [x] 后端 76 个测试全部通过
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] AppSettings 接口与 settings.json 字段完全一致
- [x] config.py 默认值覆盖全部 settings.json 字段
- [x] SubtitleOverlay 组件在 WorkspacePage 中正确挂载
- [x] SettingsModal 组件在 WelcomePage 中正确挂载

---

## Sprint 3: Undo/Redo 与状态管理

### Task 3.1: 撤销/重做（Undo/Redo）

**目标**: 实现操作历史栈，支持 Ctrl+Z/Ctrl+Y 撤销重做，含动态内存保护。

**修改文件**:
- `frontend/src/composables/useUndoRedo.ts` — 新建：撤销重做 composable
- `frontend/src/composables/useEdit.ts` — 添加 onBeforeProjectUpdate 回调
- `frontend/src/composables/useSegmentEdit.ts` — 添加 onBeforeProjectUpdate 回调
- `frontend/src/composables/useAnalysis.ts` — 添加 onBeforeProjectUpdate 回调
- `frontend/src/pages/WorkspacePage.vue` — 集成撤销重做 + 键盘快捷键

**实现细节**:

1. `useUndoRedo.ts` 核心算法：
   - `undoStack` / `redoStack` 存储 JSON 序列化快照，避免引用共享
   - `pushSnapshot(project)` — 新操作入栈，清空 redo 栈，超出上限裁剪最旧快照
   - `undo(current)` — 弹出 undo 栈顶，当前状态压入 redo 栈，返回恢复的 Project
   - `redo(current)` — 弹出 redo 栈顶，当前状态压入 undo 栈，返回恢复的 Project
   - `clearHistory()` — 项目切换时清空双栈
   - 动态内存保护：快照超 2MB 时 MAX_HISTORY 从 50 自动降至 10

2. 三个 composable 添加 `onBeforeProjectUpdate` 回调：
   - `useEdit` — 在所有 12 个编辑操作的 `project.value = res.data` 前调用 snapshot
   - `useSegmentEdit` — 在 `updateSegmentTime`（乐观更新前）、`updateSegmentText`、`toggleEditStatus` 前调用 snapshot
   - `useAnalysis` — 在 `confirmEdit`、`rejectEdit`、任务完成更新前调用 snapshot

3. `WorkspacePage.vue` 集成：
   - 创建 `useUndoRedo()` 实例，解构 `pushSnapshot` / `undo` / `redo` / `clearHistory`
   - 将 `pushSnapshot` 传入三个 composable 的 `onBeforeProjectUpdate` 参数
   - 直接编辑操作（`handleAddSegment`、`handleImportSrt`）手动调用 `pushSnapshot`
   - `handleGlobalKeydown` 新增 Ctrl+Z（undo）和 Ctrl+Y / Ctrl+Shift+Z（redo）
   - undo/redo 前先 `flushPendingUpdates()` 刷新防抖中的时间编辑
   - 监听 `project.project?.name` 变化自动清空历史栈

**撤销流程**:
```
用户按 Ctrl+Z -> flushPendingUpdates() -> undo(currentProject)
  -> 弹出 undo 栈顶快照 -> 当前状态压入 redo 栈
  -> emit("project-updated", restored) -> Vue 更新全部 UI
```

**快照触发点（16 个编辑操作全覆盖）**:
- useEdit: updateSegmentText, updateSegmentTime, mergeSegments, splitSegment,
  searchReplace, markSegments, confirmAllSuggestions, rejectAllSuggestions,
  deleteSegment, deleteSilenceSegments, deleteSubtitleTrimEdits, generateSubtitleKeepRanges
- useSegmentEdit: updateSegmentTime (debounced), updateSegmentText, toggleEditStatus
- useAnalysis: confirmEdit, rejectEdit, task completion
- WorkspacePage direct: handleAddSegment, handleImportSrt

---

### Task 3.2: 前端状态管理评估（Pinia）

**评估结论**: 当前 composable 架构合理，暂不需要 Pinia。

**理由**:
1. 项目状态单一来源：`projectRef` 在 WorkspacePage 中通过 computed 与 App.vue 同步
2. composable 间耦合度低：useEdit、useSegmentEdit、useAnalysis 各自独立，通过回调通信
3. Undo/Redo 通过回调注入模式实现，未引入额外状态管理层
4. 当前规模（~10 个 composable）未达到需要集中式状态管理的复杂度

**建议**: 若后续引入多页面状态共享（如设置页实时预览、导出页读取编辑状态），再考虑 Pinia 迁移。

---

## Files Modified Summary (Sprint 3)

### Backend (core/)
- `main.py` — detect_gpu 改用 ffmpeg -encoders、select_files 添加 JSON 支持

### Frontend (frontend/src/)
- `composables/useUndoRedo.ts` — 新建：撤销重做 composable（双栈 + 动态内存保护）
- `composables/useEdit.ts` — 添加 onBeforeProjectUpdate 回调（12 个快照点）
- `composables/useSegmentEdit.ts` — 添加 onBeforeProjectUpdate 回调（3 个快照点）
- `composables/useAnalysis.ts` — 添加 onBeforeProjectUpdate 回调（3 个快照点）
- `pages/WorkspacePage.vue` — 集成 useUndoRedo、Ctrl+Z/Y 快捷键、flushPendingUpdates
- `main.ts` — waitForPyWebView 桥接初始化等待
- `pages/WelcomePage.vue` — 版本号动态显示
- `components/common/FileDropInput.vue` — 提示文字补充 JSON 支持
- `components/export/EncodingSettings.vue` — 多平台硬件编码器、设置加载同步
- `pages/ExportPage.vue` — 移除冗余 onMounted 设置加载

### Task 3.3: 桥接初始化竞态修复 + 文件选择器 JSON 支持

**目标**: 修复 dev 模式下首次加载时桥接未就绪导致的白屏/数据丢失，文件选择器支持打开项目文件。

**修改文件**:
- `frontend/src/main.ts` — 桥接初始化等待
- `frontend/src/pages/WelcomePage.vue` — 版本号动态显示
- `frontend/src/components/common/FileDropInput.vue` — 提示文字更新
- `main.py` — select_files 文件类型扩展

**实现细节**:

1. `main.ts` 桥接初始化修复：
   - 调用已有的 `waitForPyWebView()` 确保 `window.pywebview.api` 注入后再挂载 Vue
   - 解决 dev 模式下 `onMounted` 先于 pywebview 注入执行导致 `call()` 静默失败的问题
   - 降级策略：桥接超时仍挂载应用（避免完全白屏）

2. `WelcomePage.vue` 版本号修复：
   - `onMounted` 中并行调用 `get_recent_projects` + `get_app_info`
   - 底部版本显示从硬编码 "Phase 0 - 技术验证" 改为 `v{version}`

3. 文件选择器 JSON 支持：
   - `main.py` `select_files` 文件类型添加 `"Project files (*.json)"`
   - `FileDropInput.vue` 提示文字补充 "也可拖入 .json 项目文件"

---

### Task 3.4: 硬件编码器检测修复 + 导出设置同步

**目标**: 导出页正确显示所有平台硬件编码器，设置页参数同步至导出页。

**修改文件**:
- `main.py` — detect_gpu 检测逻辑重写
- `frontend/src/components/export/EncodingSettings.vue` — 多平台编码器支持 + 设置加载
- `frontend/src/pages/ExportPage.vue` — 移除冗余设置加载

**问题根因**:

1. `detect_gpu` 使用 `ffmpeg -hwaccels` 检测硬件加速 API，不等于编码器实际可用（CUDA 存在不代表 NVENC 可用）
2. `EncodingSettings.vue` 期望 `{ nvidia, gpu_name, encoders }` 但后端只返回 `{ encoders }`，`hasNvidiaGpu` 永远 `false`
3. 编码器列表仅检查 NVIDIA（`if (hasNvidiaGpu.value)`），Intel/AMD/Apple 编码器即使被检测到也不会显示
4. 导出页使用硬编码默认值，不读取设置页配置

**实现细节**:

1. `detect_gpu` 重写：
   - 废弃 `ffmpeg -hwaccels` 方案，改用 `ffmpeg -encoders` 直接查询编码器注册列表
   - 遍历 `ENCODER_METADATA` 中所有编码器逐一查找
   - libsvtav1 不再跳过检测（macOS FFmpeg 常缺失）
   - 结果更可靠：编码器注册 = 编码器可用

2. `EncodingSettings.vue` 修复：
   - 移除 `hasNvidiaGpu` / `gpuName`，改用 `hasHardwareEncoder` computed
   - `HARDWARE_ENCODER_ORDER` 覆盖 NVENC/QSV/AMF/VideoToolbox/VAAPI 全平台
   - `videoCodecs` 遍历完整硬件编码器列表，后端检测到什么就显示什么
   - 状态信息从 "未检测到 NVIDIA GPU" 改为 "未检测到硬件编码器"
   - `onMounted` 从 `get_settings` 加载保存的设置，末尾 `updateSettings()` 同步父组件

3. `ExportPage.vue` 简化：
   - 移除冗余 `onMounted` 设置加载（由 EncodingSettings 自行处理）
   - 移除未使用的 `onMounted` import

---

## Verification (Sprint 3)

- [x] 后端 76 个测试全部通过
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] useUndoRedo composable 正确导出
- [x] 所有 16 个编辑操作覆盖快照触发点
- [x] Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z 快捷键注册
- [x] waitForPyWebView 桥接初始化等待生效
- [x] 文件选择器支持 JSON 项目文件
- [x] 硬件编码器检测覆盖 NVENC/QSV/AMF/VideoToolbox/VAAPI
- [x] 设置页参数正确同步至导出页

---

## Sprint 4: 交叉高亮、右键菜单、VTT 导出

### Task 4.1: 交叉高亮

**目标**: 选中静音段时，高亮其前后相邻的字幕段，方便用户确认裁剪边界。

**修改文件**:
- `frontend/src/components/workspace/Timeline.vue`
- `frontend/src/components/workspace/TranscriptRow.vue`

**实现细节**:

1. `Timeline.vue` 新增 `adjacentSubtitleIds` 计算属性：
   - 接收 `selectedSegmentId` prop，查找其在 `segments` 数组中的索引
   - 仅当选中的是静音段时生效，否则返回 `{ prev: null, next: null }`
   - 从选中索引向前扫描找到前一个字幕段 ID（`prev`）
   - 从选中索引向后扫描找到后一个字幕段 ID（`next`）
   - 将结果通过 `is-adjacent-highlighted` prop 传递给 TranscriptRow

2. `TranscriptRow.vue` 新增 `isAdjacentHighlighted` prop：
   - `statusClass` 计算属性中，amber 高亮优先级最高（高于 confirmed/rejected/pending）
   - 样式：`border-l-3 border-amber-400 bg-amber-50`

---

### Task 4.2: 右键上下文菜单

**目标**: 为 TranscriptRow 和 SilenceRow 添加右键菜单，提供快捷操作入口。

**修改文件**:
- `frontend/src/components/workspace/TranscriptRow.vue`
- `frontend/src/components/workspace/SilenceRow.vue`
- `frontend/src/components/workspace/Timeline.vue`

**实现细节**:

1. 两个组件使用相同的上下文菜单模式：
   - `contextMenu` ref 存储 `{ x, y }` 坐标
   - `handleContextMenu(e)` 阻止默认行为，记录鼠标位置
   - `closeContextMenu()` 清除菜单状态
   - `watch(contextMenu)` 监听：显示时注册 `document.click` once 监听器自动关闭

2. TranscriptRow 菜单项：
   - 编辑文本 -- 调用 `startEdit()` 进入内联编辑模式
   - 标记删除/取消删除 -- 调用 `emit('toggle-status')`
   - 删除段落 -- 调用 `emit('delete')`（新增事件）

3. SilenceRow 菜单项：
   - 标记删除/取消删除 -- 调用 `emit('toggle-status')`
   - 删除段落 -- 调用 `emit('delete')`

4. Timeline.vue 为 TranscriptRow 接通 `@delete` 事件，转发为 `emit('delete-segment', seg)`

**技术细节**:
- 菜单使用 `fixed` 定位（相对于视口），`z-50` 确保层级在最上
- 使用 `document.addEventListener("click", closeContextMenu, { once: true })` 实现点击外部关闭
- 通过 `setTimeout(0)` 确保监听器在当前事件循环之后注册，避免立即触发

---

### Task 4.3: VTT 导出

**目标**: 新增 WebVTT 字幕格式导出，兼容更多播放器和剪辑软件。

**修改文件**:
- `core/export_service.py` -- VTT 导出逻辑
- `core/models.py` -- TaskType 枚举
- `main.py` -- 任务处理器注册
- `frontend/src/types/task.ts` -- 前端类型
- `frontend/src/composables/useExport.ts` -- 任务识别
- `frontend/src/pages/ExportPage.vue` -- 导出按钮

**实现细节**:

1. 后端 `export_service.py`：
   - 新增 `export_vtt(segments, edits, output_path, *, media_duration=0.0)` 函数
   - 逻辑与 `export_srt()` 相同，区别在于：
     - 文件头为 `WEBVTT\n\n`（VTT 规范要求）
     - 时间戳格式为 `HH:MM:SS.mmm`（句点而非逗号）
     - 不需要序号（VTT 规范可选）
   - 新增 `_format_vtt_time(seconds)` 辅助函数

2. 后端任务系统：
   - `models.py` TaskType 新增 `EXPORT_VTT = "export_vtt"`
   - `main.py` 注册 `_handle_export_vtt` 处理器，调用 `export_vtt()`
   - 默认输出文件名后缀 `_cut.vtt`

3. 前端集成：
   - `types/task.ts` TaskType 联合类型新增 `"export_vtt"`
   - `useExport.ts` 的 `isExporting` 和 `exportProgress` 计算属性识别 `export_vtt`
   - `ExportPage.vue` 新增 `handleExportVtt()` 函数和"导出 VTT"按钮

---

### Task 4.4: 测试覆盖与文档

**目标**: 为 Sprint 4 新增功能补充测试，更新文档。

**修改文件**:
- `tests/test_export_service.py` -- 新建：导出服务测试
- `tests/TEST_GUIDE.md` -- 测试指南更新

**新增测试**:

1. `test_export_service.py`（21 个测试）：
   - `TestFormatSrtTime`（6 个）：边界值、零值、大值、四舍五入
   - `TestFormatVttTime`（6 个）：同上，验证句点分隔符
   - `TestExportSrt`（3 个）：正常导出、编辑裁剪、空段落处理
   - `TestExportVtt`（6 个）：WEBVTT 头、时间戳格式、编辑裁剪、句点分隔符

2. 修复多根组件问题：
   - TranscriptRow.vue 和 SilenceRow.vue 添加上下文菜单后变为多根组件
   - Vue Test Utils 的 `wrapper.trigger("click")` 和 `wrapper.classes()` 在多根组件上行为不同
   - 修复方案：将上下文菜单 div 移入主 div 内部，恢复单根组件结构

3. `TEST_GUIDE.md` 更新：
   - 后端测试计数：97 tests across 6 modules
   - 前端测试计数：105 tests across 7 test files
   - 新增 `test_export_service.py` 行
   - 更新前端测试模块表（7 个文件全覆盖）

---

### Task 4.5: 上下文菜单关闭逻辑修复

**目标**: 修复右键菜单在右键其他位置、滚动、点击外部时不能正确关闭的问题。

**修改文件**:
- `frontend/src/utils/contextMenuManager.ts` — 新建：上下文菜单生命周期管理
- `frontend/src/components/workspace/TranscriptRow.vue` — 接入 manager
- `frontend/src/components/workspace/SilenceRow.vue` — 接入 manager
- `frontend/src/components/waveform/SegmentBlocksLayer.vue` — 接入 manager

**问题根因**:
1. 原方案使用 `watch(contextMenu)` 注册 `document.click` once 监听器，但 `stopPropagation()` 阻止了右键事件冒泡到 document
2. 右键其他位置时，`contextmenu` 事件被 `stopPropagation()` 拦截，旧菜单无法关闭
3. 滚动时菜单不跟随也不关闭，用户体验差

**实现细节**:

1. `contextMenuManager.ts` 模块级单例：
   - `openContextMenu(closeFn)` — 关闭旧菜单，注册 document 级 `click`、`contextmenu`、`scroll` 监听器
   - `closeContextMenu()` — 主动关闭当前菜单
   - `closeActive()` — 内部函数，清理监听器并调用关闭回调
   - 使用 `{ once: true }` 监听器，触发后自动清理
   - `setTimeout(0)` 确保监听器在当前事件循环之后注册

2. 三个组件统一接入模式：
   - `handleContextMenu()` 中调用 `openContextMenu(() => { contextMenu.value = null })`
   - `closeContextMenu()` 中调用 `closeContextMenuManager()` 清理 manager 状态
   - 移除原有的 `watch(contextMenu)` 监听器

---

### Task 4.6: 上下文菜单层级修复

**目标**: 修复上下文菜单被父容器 overflow: hidden 裁剪、层级不正确的问题。

**修改文件**:
- `frontend/src/components/workspace/TranscriptRow.vue`
- `frontend/src/components/workspace/SilenceRow.vue`
- `frontend/src/components/waveform/SegmentBlocksLayer.vue`

**问题根因**:
- 菜单 div 渲染在组件 DOM 内部，被父容器的 `overflow: hidden` 裁剪
- `z-50` 不够高，被其他元素遮挡

**实现细节**:
- 三个组件的上下文菜单均使用 `<Teleport to="body">` 逃逸父容器 DOM
- z-index 从 `z-50` 提升至 `z-[9999]`
- 移除不必要的 `opacity-90` 透明度（用户反馈太奇怪）

---

### Task 4.7: 导出页面字幕预览

**目标**: 导出页面播放器显示当前字幕文本，方便用户在导出前确认裁剪效果。

**修改文件**:
- `frontend/src/components/export/PreviewPlayer.vue` — 内联字幕渲染
- `frontend/src/pages/ExportPage.vue` — 传递排序后的 segments

**尝试过但失败的方案**:
1. 复用 SubtitleOverlay 组件 — 跨组件 videoRef watch 时序不可靠，字幕不显示
2. 添加 `immediate: true` + `loadeddata` 监听 — 仍不生效
3. 二分查找 — 混合类型 segments（subtitle + silence）可能跳过目标段

**最终方案**: 内联字幕渲染到 PreviewPlayer 自身，使用 computed 属性。

**实现细节**:

1. `PreviewPlayer.vue` 改造：
   - 移除 SubtitleOverlay 组件导入
   - 新增 `currentSubtitleText` computed 属性，从 `currentTime` + `segments` 派生
   - 使用线性扫描替代二分查找，兼容混合类型 segments
   - 字幕 div 使用 `absolute bottom-4` 定位，`pointer-events-none` 不阻挡交互
   - `currentTime` 在 `animationLoop`（每帧）、`onTimeUpdate`、`onLoadedMetadata`、`onSeeked` 中更新
   - Vue 响应式系统自动在 currentTime 变化时重新计算字幕文本

2. `ExportPage.vue` 改造：
   - 新增 `sortedSegments` computed，按 start 时间排序
   - PreviewPlayer 接收 `:segments="sortedSegments"`

**为什么 computed 比命令式更新更可靠**:
- 无跨组件 ref 时序问题（字幕逻辑完全在 PreviewPlayer 内部）
- 无游标状态管理（不需要 subtitleCursor 变量）
- Vue 响应式保证：currentTime 变化 -> computed 自动重算 -> 模板自动更新
- 无 rAF 生命周期耦合（不依赖 play/pause 事件启停）

---

## Files Modified Summary (Sprint 4)

### Backend (core/)
- `export_service.py` — VTT 导出逻辑（export_vtt + _format_vtt_time）
- `models.py` — TaskType 新增 EXPORT_VTT
- `main.py` — export_vtt 任务处理器注册

### Frontend (frontend/src/)
- `components/workspace/Timeline.vue` — 交叉高亮（adjacentSubtitleIds）、@delete 事件接通
- `components/workspace/TranscriptRow.vue` — 右键菜单 + Teleport + contextMenuManager + isAdjacentHighlighted
- `components/workspace/SilenceRow.vue` — 右键菜单 + Teleport + contextMenuManager
- `components/waveform/SegmentBlocksLayer.vue` — contextMenuManager 接入 + z-index 修复
- `utils/contextMenuManager.ts` — 新建：上下文菜单生命周期管理单例
- `components/export/PreviewPlayer.vue` — 内联字幕渲染（computed 属性 + 线性扫描）
- `pages/ExportPage.vue` — sortedSegments computed + VTT 导出按钮
- `types/task.ts` — TaskType 新增 export_vtt
- `composables/useExport.ts` — 识别 export_vtt 任务类型

### Tests
- `tests/test_export_service.py` — 新建：21 个导出服务测试

---

## Verification (Sprint 4)

- [x] 后端 97 个测试全部通过
- [x] 前端 105 个测试全部通过
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] 选中静音段时相邻字幕段 amber 高亮
- [x] TranscriptRow / SilenceRow 右键菜单功能正常
- [x] VTT 导出产生有效 WEBVTT 文件
- [x] 上下文菜单不影响现有测试（单根组件修复）
- [x] 右键菜单在右键其他位置时自动关闭
- [x] 右键菜单在滚动时自动关闭
- [x] 右键菜单不被父容器 overflow 裁剪（Teleport to body）
- [x] 导出页面字幕预览正常显示

---

## Commit Messages

### Sprint 1

```
feat(project): 安全防护与技术债务清理 -- EditSummaryModal、版本统一、媒体重链接

- ExportPage 接入 EditSummaryModal，导出前弹出删除摘要确认对话框
- _get_version() 三级兜底读取版本号，消除 main.py 硬编码
- open_project() 检测媒体文件存在性，丢失时返回 MEDIA_NOT_FOUND
- 新增 RelinkMediaDialog 组件，支持文件浏览和重链接确认
- 轻量级媒体指纹（size+mtime SHA-256），O(1) 不阻塞项目打开
- relink_media() 更新媒体路径和指纹并自动保存
- App.vue / WelcomePage.vue / useProject.ts 集成重链接流程
- 测试修复：临时媒体文件替代硬编码路径
```

### Sprint 2

```
feat(workspace): 核心交互补齐 -- 自动保存、字幕叠加、FFmpeg管理、设置页

- WorkspacePage 监听 PROJECT_DIRTY 事件，debounce 2s 自动保存 + isSaving 锁
- 新增 SubtitleOverlay 组件，rAF 驱动 + 游标优化 O(1) 字幕查找
- ffmpeg_service 路径解析优先链：用户设置 > PATH > static_ffmpeg
- detect_gpu 改用 ffmpeg -hwaccels 跨平台探测，支持 NVIDIA/Intel/AMD/Apple/VAAPI
- 新增 SettingsModal 设置页，首页齿轮图标入口
- 设置页覆盖 FFmpeg 状态、GPU 编码器、静音检测、导出编码配置
- AppSettings 接口从 8 字段扩展至 22 字段，与 settings.json 完全同步
- config.py 默认值补全 9 个导出相关设置
```

### Sprint 3

```
feat(workspace): Undo/Redo、桥接修复、硬件编码器检测、设置同步

- 新增 useUndoRedo composable，双栈存储 JSON 快照避免引用共享
- 动态内存保护：快照超 2MB 时 MAX_HISTORY 从 50 自动降至 10
- useEdit/useSegmentEdit/useAnalysis 添加 onBeforeProjectUpdate 回调
- 16 个编辑操作全覆盖快照触发点（含防抖时间编辑）
- Ctrl+Z 撤销、Ctrl+Y / Ctrl+Shift+Z 重做
- undo/redo 前 flushPendingUpdates() 刷新防抖中的时间编辑
- 项目切换时自动清空历史栈
- 评估结论：当前 composable 架构合理，暂不需要 Pinia
- main.ts 添加 waitForPyWebView 桥接初始化等待，修复 dev 模式首次加载白屏
- WelcomePage 版本号从 get_app_info 动态读取，消除硬编码
- 文件选择器支持 JSON 项目文件打开
- detect_gpu 改用 ffmpeg -encoders 直接查询编码器注册列表，结果更可靠
- EncodingSettings 移除 NVIDIA-only 门控，支持 NVENC/QSV/AMF/VideoToolbox/VAAPI 全平台
- EncodingSettings onMounted 从 get_settings 加载设置并同步父组件
- libsvtav1 不再跳过检测，兼容 macOS FFmpeg 缺失场景
```

### Sprint 4

```
feat(workspace): 交叉高亮、右键菜单、VTT 导出、上下文菜单修复、导出字幕预览

- Task 4.1: 选中静音段时高亮相邻字幕段（amber 边框+背景）
- Timeline.vue 新增 adjacentSubtitleIds 计算属性，双向扫描 segments 数组
- TranscriptRow 新增 isAdjacentHighlighted prop，statusClass 中 amber 样式优先级高于其他状态
- Task 4.2: TranscriptRow / SilenceRow 添加右键上下文菜单
- TranscriptRow 菜单项：编辑文本、标记删除/取消删除、删除段落
- SilenceRow 菜单项：标记删除/取消删除、删除段落
- Timeline.vue 为 TranscriptRow 接通 @delete 事件
- Task 4.3: WebVTT 字幕导出
- core/export_service.py 新增 export_vtt() 和 _format_vtt_time() 辅助函数
- core/models.py TaskType 新增 EXPORT_VTT
- main.py 注册 export_vtt 任务处理器
- frontend types/task.ts 新增 export_vtt 类型
- useExport composable 识别 export_vtt 任务类型
- ExportPage 新增"导出 VTT"按钮
- Task 4.4: 测试覆盖与文档
- 新增 tests/test_export_service.py（21 个测试：格式化、SRT 导出、VTT 导出）
- 修复上下文菜单导致的多根组件问题（Vue Test Utils 兼容）
- 更新 TEST_GUIDE.md 测试计数和模块列表
- Task 4.5: 上下文菜单关闭逻辑修复
- 新建 contextMenuManager.ts 模块级单例，管理菜单生命周期
- 解决 stopPropagation 阻止 document 监听器接收右键事件的问题
- 统一处理：右键其他位置关闭、点击外部关闭、滚动关闭
- TranscriptRow / SilenceRow / SegmentBlocksLayer 三个组件统一接入
- Task 4.6: 上下文菜单层级修复
- 上下文菜单使用 Teleport to body 逃逸父容器 overflow: hidden 裁剪
- z-index 从 z-50 提升至 z-[9999]
- Task 4.7: 导出页面字幕预览
- PreviewPlayer 内联字幕渲染，使用 computed 属性从 currentTime + segments 派生
- 线性扫描替代二分查找，兼容混合类型 segments
- ExportPage 新增 sortedSegments computed 按 start 时间排序
- 最终状态：97 后端测试 + 105 前端测试全部通过
```

---

## Merge Message

```
merge: dev-1.1.0 合入 main -- 安全防护、核心交互补齐、Undo/Redo、VTT 导出

Sprint 1: 安全防护与技术债务清理
- ExportPage 接入 EditSummaryModal，导出前弹出删除摘要确认
- 版本号统一：_get_version() 三级兜底，消除硬编码
- 媒体丢失重链接：RelinkMediaDialog + 轻量级指纹校验

Sprint 2: 核心交互补齐
- 项目自动保存：debounce 2s + isSaving 锁
- 字幕叠加预览：rAF 驱动 + 游标优化 O(1) 查找
- FFmpeg 管理：路径解析优先链 + 跨平台 GPU 检测
- 设置页：FFmpeg 状态、GPU 编码器、静音检测、导出编码全配置

Sprint 3: Undo/Redo 与状态管理
- useUndoRedo composable：双栈 JSON 快照 + 动态内存保护
- 16 个编辑操作全覆盖快照触发点
- 桥接初始化竞态修复 + 硬件编码器检测重写（ffmpeg -encoders）
- 设置页参数同步至导出页

Sprint 4: 交叉高亮、右键菜单、VTT 导出
- 选中静音段时高亮相邻字幕段
- TranscriptRow / SilenceRow / SegmentBlocksLayer 右键上下文菜单
- WebVTT 字幕导出
- 导出页面字幕预览
- 上下文菜单生命周期管理（contextMenuManager）

统计：51 files changed, 4612 insertions(+), 123 deletions(-)
测试：97 后端 + 105 前端全部通过
```

---

## Release Notes

### Milo-Cut v1.1.0

**安全防护**

- 导出前弹出删除摘要确认对话框，防止误删字幕段
- 打开项目时自动检测媒体文件完整性，丢失文件支持重链接

**核心交互**

- 编辑操作后 2 秒自动保存，Ctrl+S 手动保存带并发锁保护
- 播放视频时底部实时显示当前字幕文本
- 设置页：FFmpeg 路径管理、GPU 编码器检测、静音检测参数、导出编码配置

**Undo/Redo**

- Ctrl+Z 撤销、Ctrl+Y / Ctrl+Shift+Z 重做
- 覆盖全部 16 个编辑操作（文本编辑、时间调整、合并拆分、标记删除等）
- 动态内存保护：快照过大时自动缩减历史深度

**导出增强**

- 新增 WebVTT (.vtt) 字幕格式导出
- 导出页面播放器显示当前字幕预览
- 硬件编码器检测支持 NVENC / QSV / AMF / VideoToolbox / VAAPI 全平台
- 设置页导出参数自动同步至导出页

**编辑体验**

- 选中静音段时高亮显示前后相邻字幕段，方便确认裁剪边界
- 字幕行和静音段右键菜单：编辑文本、标记删除、删除段落
- 版本号从 pyproject.toml 动态读取，不再硬编码
- 桥接初始化等待机制，修复 dev 模式首次加载白屏

**技术改进**

- AppSettings 接口扩展至 22 字段，与 settings.json 完全同步
- config.py 默认值覆盖全部运行时设置
- 上下文菜单统一管理（contextMenuManager），支持右键/点击/滚动自动关闭
- 97 后端测试 + 105 前端测试全部通过

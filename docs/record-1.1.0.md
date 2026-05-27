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

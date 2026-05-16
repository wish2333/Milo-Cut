# Milo-Cut 0.2.0 Development Record

## Overview

0.2.0 版本聚焦于导出功能的完善，包括视频/音频/SRT 导出、EDL 和 XML 时间线格式导出，以及导出页面的 UI 实现。

## Branch

`dev-0.2.0` (from `main`)

## Commits (chronological)

| Hash | Message |
|------|---------|
| `0f1ffb9` | fix(export): 修复音频导出末尾截断与SRT时间轴对齐问题 |
| `b6fc63f` | fix(ui): implement audit plan 0.2.0-1 items I-1, I-3, I-2 |
| `0103202` | docs(0.2.0): 更新文档 |
| `cf4b092` | feat(export): implement ExportPage with encoding settings, preview player, and timeline export |
| `7865f96` | fix: remove duplicate onProjectClosed and fix heroicons import |
| `b64a21d` | fix(export): 修复导出页面多个Bug并改进GPU检测 |
| `e555282` | fix(export): 修复导出编码设置不生效、路径解析错误、预览无音量控制 |
| `8c15ece` | fix(export): 重写EDL/XML导出以兼容达芬奇和Premiere Pro |

## Key Changes

### ExportPage 实现
- 编码设置面板（编码器、CRF、分辨率、音频码率等）
- 预览播放器（带波形、剪辑区域标记、音量控制）
- 导出操作区（视频/音频/SRT/EDL/XML）
- 进度条显示

### 导出功能
- **视频导出**: FFmpeg 编码，支持 H.264/H.265/VP9，可配置 CRF/预设/分辨率
- **音频导出**: 独立音频文件导出
- **SRT 导出**: 字幕文件导出，时间轴自动调整
- **EDL 导出**: CMX3600 格式，达芬奇专用
- **XML 导出**: FCP 7 XML (xmeml v5) 格式，兼容 Premiere Pro 和达芬奇

### XML 导出演进
- 版本从 v4 改为 v5（符合 FCP 7 XML 规范）
- 时间参数使用整数帧数（非浮点数）
- 修正 duration 计算：clip duration = out - in = end - start
- 路径使用相对文件名（XML 与源文件同目录）
- 音频双轨道（L/R）分离，完整 link 链实现音视频同步切割
- 按帧数过滤零时长范围，避免生成无效 clipitem

### Bug 修复
- 音频导出末尾截断
- SRT 时间轴对齐问题
- 编码设置不生效
- GPU 检测改进
- 预览播放器音量控制
- 导出路径解析错误
- 重复 onProjectClosed 事件
- heroicons 导入问题

## Files Modified

### Backend (core/)
- `export_service.py` — 视频/音频/SRT 导出服务
- `export_timeline.py` — EDL/XML 时间线格式导出
- `models.py` — 数据模型更新
- `project_service.py` — 项目服务更新

### Backend (root)
- `main.py` — Bridge 方法注册

### Frontend (frontend/src/)
- `pages/ExportPage.vue` — 导出页面
- `components/export/EncodingSettings.vue` — 编码设置组件
- `components/export/PreviewPlayer.vue` — 预览播放器组件
- `composables/useExport.ts` — 导出逻辑 composable
- `App.vue` — 页面路由更新

## Known Issues

- EDL 格式仅达芬奇可用，Premiere Pro 无法自动链接素材
- XML 导入达芬奇需要手动确认音频链接

---

# Milo-Cut 0.2.1 Development Record

## Overview

0.2.1 版本修复了波形显示不工作的 Bug，并优化了时间线上波形与字幕块的视觉效果。

## Branch

`dev-0.2.1` (from `main`)

## Key Changes

### Bug Fix: 波形显示不工作

**根因分析:**
1. `useProject.ts` 是死代码（从未被导入），波形生成任务从未被触发
2. `WaveformCanvas.vue` 直接用 `fetch()` 访问本地文件系统路径，无法在 Web 上下文中工作
3. 波形生成任务完成后，没有监听 `task:completed` 事件来更新项目数据

**修复方案:**

#### 后端

| 文件 | 变更 |
|------|------|
| `core/media_server.py` | 扩展 HTTP Handler，在 `/waveform` 端点提供波形 JSON 文件服务；添加 `set_waveform()` 方法 |
| `core/task_manager.py` | `task:completed` 事件数据中添加 `task_type` 字段 |
| `main.py` | 添加 `get_waveform_url` 桥接方法；波形生成完成后调用 `set_waveform()`；加载已有项目时注册波形路径 |

#### 前端

| 文件 | 变更 |
|------|------|
| `frontend/src/App.vue` | 添加 `triggerWaveformGeneration()` 在项目创建/打开时触发波形生成；监听 `task:completed` 事件更新项目 |
| `frontend/src/pages/WorkspacePage.vue` | 添加 `waveformUrl` ref 通过 `get_waveform_url` 桥接获取 HTTP URL；监听 `waveform_path` 变化自动解析 |
| `frontend/src/composables/useProject.ts` | 添加 `task:completed` 监听器处理波形生成完成事件 |

### 视觉优化: 波形与字幕块

| 文件 | 变更 |
|------|------|
| `frontend/src/components/waveform/WaveformCanvas.vue` | 波形振幅放大 1.3 倍 |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 字幕块背景半透明（`bg-red-200/60` 等），文字保持完全不透明 |
| `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` | 更新测试选择器适配新的 class 命名 |

## Files Modified

### Backend
- `core/media_server.py` — 添加 `/waveform` HTTP 端点
- `core/task_manager.py` — 事件数据增加 `task_type`
- `main.py` — 桥接方法和波形注册逻辑

### Frontend
- `frontend/src/App.vue` — 波形生成触发和完成监听
- `frontend/src/pages/WorkspacePage.vue` — 波形 URL 解析
- `frontend/src/composables/useProject.ts` — 事件监听补充
- `frontend/src/components/waveform/WaveformCanvas.vue` — 振幅放大
- `frontend/src/components/waveform/SegmentBlocksLayer.vue` — 背景半透明
- `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` — 测试适配

### DetectSilence 增强

基于审计计划 `audit-plan-0.2.0-2`，对静音检测功能进行三项调整:

**D-3: Min Duration 标尺调整**
- 滑块范围从 0.1-3.0s (step 0.1) 改为 0.05-2.0s (step 0.05)
- 显示精度改为两位小数
- min_duration < 0.2s 时显示 amber 性能警告

**D-1: Margin 缩边**
- 静音检测后、创建 Segment 前，对每个静音区间两侧各收缩 margin 值
- 新增配置项 `silence_margin` (默认 0.0, 范围 0-0.5s, step 0.01)
- 缩边后区间 <= 0.01s 则丢弃，使用 `round(x, 3)` 防浮点误差
- 前端 amber 警告提示，不阻断运行按钮

**D-2: 字幕保护 Padding (v2)**
- 新增 `_trim_silences_around_subtitles()` 方法，在创建 EditDecision 前用字幕扩展区裁剪静音区间
- 静音主动避让字幕，字幕段本身不修改
- 废弃旧 `_resolve_subtitle_overlap()` 调用 (方法保留但不调用)
- 已确认删除的字幕块不参与扩展区计算
- 新增配置项 `silence_subtitle_padding` (默认 0.0, 范围 0-1.0s, step 0.05)
- 前端滑块仅在值 > 0 时显示说明文字

**流水线架构:**
```
FFmpeg 静音检测 -> margin 缩边 -> 字幕保护裁剪 -> 创建 Segment/EditDecision -> 去重 -> 保存
```

#### Files Modified

| 文件 | 变更 |
|------|------|
| `core/config.py` | 新增 `silence_margin`, `silence_subtitle_padding` 配置项 |
| `core/project_service.py` | 新增 `_trim_silences_around_subtitles()`; `add_silence_results()` 增加 margin/padding 参数和缩边逻辑; 废弃旧字幕裁剪调用 |
| `main.py` | 传递 `margin` 和 `subtitle_padding` 参数 |
| `frontend/src/pages/WorkspacePage.vue` | 新增 margin/padding 滑块 + 性能警告; min duration 标尺调整 |
| `tests/test_project_service.py` | 11 个新测试覆盖 margin 缩边和字幕保护裁剪 |
| `docs/audit-plan-0.2.0-2.md` | 审计报告 (新增) |

### 0.2.0

新增完整的导出功能，支持多种格式和编码配置：

- 导出页面：编码设置、实时预览、进度显示
- 视频导出：H.264/H.265/VP9，可配置质量/分辨率/预设
- 音频导出：独立音频文件
- SRT 字幕导出：时间轴自动调整
- EDL 时间线导出：CMX3600 格式（达芬奇）
- XML 时间线导出：FCP 7 XML 格式（Premiere Pro / 达芬奇）
- 多项 Bug 修复和稳定性改进

### B-1 修复: 波形滑块水平滚动条溢出

**问题**: 当 Waveform 滑块滑到最右边时，thumb 宽度溢出容器，引发窗口横向滚动条出现，遮挡波形滑块且无法消除。

**修复方案 (双层防御)**:

| 位置 | 变更 |
|------|------|
| `App.vue` 根 div | `min-h-screen` 改为 `min-h-screen overflow-x-hidden`，禁止窗口横向滚动条 |
| `ScrollbarStrip.vue` thumb | 添加 `maxWidth: Math.max(0, 100 - metrics.thumbLeft.value) + '%'` 约束 thumb 不超出右边界 |

### 波形重新生成按钮

在 WaveformEditor 控制栏左侧新增 "Regen" 按钮，用于清空缓存并重新触发生成波形，方便验证波形显示对齐。

**实现细节**:

| 文件 | 变更 |
|------|------|
| `main.py` | 新增 `regenerate_waveform` @expose 方法：调用 `update_media_waveform("")` 清空路径（frozen model 安全），重置 media server 波形路径，创建并启动 waveform_generation task |
| `frontend/src/components/waveform/WaveformEditor.vue` | 新增 `regenerate-waveform` emit 声明 + Regen 按钮（controls bar 左端） |
| `frontend/src/pages/WorkspacePage.vue` | 新增 `handleRegenerateWaveform` 处理函数 — 500ms 轮询 `get_waveform_url`（30s 超时），因为 regen 后 waveform_path 值不变，Vue watch 不会触发；清理定时器在 onUnmounted |

**关键教训**: Pydantic frozen model 不能直接赋值，必须使用 `model_copy(update={...})`.

### OTIO 导出

新增 OpenTimelineIO (.otio) 格式导出，使用 `opentimelineio` 库构建标准 schema，PR 2025+ 和达芬奇 18+ 均原生支持。

**实现细节**:

| 文件 | 变更 |
|------|------|
| `core/config.py` | 新增 `export_fade_duration` 配置项（默认 0.0） |
| `core/export_timeline.py` | 新增 `export_otio()` — 使用 OTIO schema 对象构建 Timeline、Track、Clip、ExternalReference；新增 `_build_otio_clips_with_transitions()` — 在片段间插入 SMPTE_Dissolve Transition（检查 source boundaries 确保有足够 handle）；修复 `_sec_to_frames()` 使用 `round()` 确保整数帧 |
| `main.py` | 新增 `export_otio` bridge 方法 |
| `frontend/src/pages/ExportPage.vue` | 新增 OTIO 导出按钮 + fade_duration 滑块（0-1s, step 0.05），带 amber 说明文字 |
| `pyproject.toml` | 新增 `opentimelineio>=0.18.1` 依赖 |

**注意事项**:
- 使用 `round()` 而非 `int()` 进行秒到帧的转换，确保 NLE 兼容性
- Python 3 `round()` 使用银行家舍入 (round-half-to-even)，跨帧过渡帧数可能差 1 帧，NLE 工作流可接受
- 过渡只插入有足够 handle 的片段之间（源边界检查）

### 审计计划 0.2.0-4 实施 (audit-plan-0.2.0-4)

基于审计报告 `audit-report-0.2.0-4.md` 的实施，涵盖 P0 阻断修复、P1 核心功能、P2 进阶功能共 8 个任务。

#### P0 阻断修复

**A-1: 导出页返回编辑页后波形消失**
- 根因: Python `HTTPServer` 单线程阻塞 + ExportPage 未主动释放 `<video>` 连接
- `core/media_server.py`: `HTTPServer` -> `ThreadingHTTPServer`，支持并发请求
- `frontend/src/components/export/PreviewPlayer.vue`: `onUnmounted` -> `onBeforeUnmount`，释放 video 连接 (pause + removeAttribute + load)
- `frontend/src/pages/WorkspacePage.vue`: `resolveWaveformUrl()` 添加最多 3 次重试，间隔 1s

**A-6: Waveform 滑块拖动性能优化**
- 根因: 每帧 mousemove 触发 Canvas 完整重绘 + computed 重建
- `frontend/src/components/waveform/ScrollbarStrip.vue`: `onMove` 添加 `requestAnimationFrame` 节流，`onUp` 中 `cancelAnimationFrame` 清理
- `frontend/src/components/waveform/WaveformCanvas.vue`: `draw()` 添加 viewStart 变化阈值检查 (< 0.02s 跳过重绘)；非 viewStart 触发器重置 `lastDrawnViewStart`
- `frontend/src/composables/useTimelineMetrics.ts`: `timeMarks` computed 添加步进缓存，仅当 viewStart 跨越刻度间隔后才重建数组

#### P1 核心功能

**A-7: OTIO 全量时间线导出 + 删除区域标记**
- `core/export_timeline.py`: 新增 `_build_full_timeline_items()` -- 合并 keep/deleted 区间，按 start 排序，deleted 生成 `Gap + Marker(name, color=RED)`；`export_otio()` 添加 `mode` 参数 (clean/full_timeline)；全量模式下强制 `fade_duration=0`
- `main.py`: bridge 方法传递 `mode` 参数
- `frontend/src/pages/ExportPage.vue`: 新增 `otioExportMode` ref，radio 组 UI (Clean Export / Full Timeline)，Full Timeline 时禁用 fade 滑块

**A-9-XML: XML 全量时间线导出**
- `core/export_timeline.py`: 新增 `_build_xmeml_full_timeline()` -- 使用累积帧计数器维护 `<start>`/`<end>` 偏移，deleted 区间生成 gap `<clipitem>` (name 标识删除区域)；`export_xmeml_premiere()` 添加 `mode` 参数；`_build_xmeml_core()` 传递 mode
- `main.py`: bridge 方法传递 `mode`
- `frontend/src/pages/ExportPage.vue`: XML 导出按钮联动 `otioExportMode`

**A-3: 时间线格式按钮重排**
- 已验证按钮顺序 OTIO -> XML -> EDL 符合要求，无需修改

**A-2: 旧通知改用 Toast 系统**
- `frontend/src/pages/ExportPage.vue`: 导入 `useToast`，所有 export handler 的成功/失败通知改为 `showToast`；保留 `statusMessage` 用于持续状态（正在导出...）；修复 EDL/XML/OTIO handler 的 `finally` 块 bug（成功消息被立即清除）

#### P2 进阶功能

**A-4: OTIO 音频转场模式选择**
- `core/export_timeline.py`: `export_otio()` 添加 `fade_mode` 参数 (crossfade/separate)；新增 `_build_otio_clips_with_fade_effects()` -- 为每个 Clip 添加 `AudioFadeIn`/`AudioFadeOut` Effect，duration 存储在 metadata；首个 Clip 仅 FadeOut，末个仅 FadeIn
- `main.py`: bridge 方法传递 `fade_mode`
- `frontend/src/pages/ExportPage.vue`: 新增 `otioFadeMode` ref，radio 组 UI (Crossfade / Separate Fade In/Out)，仅在 clean + fade > 0 时显示

**A-5: FFmpeg filter_complex 接口预留**
- `core/config.py`: 新增 `export_transition_mode` 设置（默认 "none"）
- `frontend/src/pages/ExportPage.vue`: 预留 disabled checkbox "FFmpeg video transitions (experimental)"

#### Files Modified

| 文件 | 涉及任务 | 改动规模 |
|------|----------|----------|
| `core/media_server.py` | A-1 | ~3 行 |
| `core/config.py` | A-5 | ~2 行 |
| `core/export_timeline.py` | A-4, A-7, A-9-XML | ~200 行 |
| `main.py` | A-4, A-7, A-9-XML | ~10 行 |
| `frontend/src/pages/ExportPage.vue` | A-1, A-2, A-3, A-4, A-5, A-7, A-9-XML | ~80 行 |
| `frontend/src/pages/WorkspacePage.vue` | A-1 | ~10 行 |
| `frontend/src/components/export/PreviewPlayer.vue` | A-1 | ~8 行 |
| `frontend/src/components/waveform/ScrollbarStrip.vue` | A-6 | ~15 行 |
| `frontend/src/components/waveform/WaveformCanvas.vue` | A-6 | ~15 行 |
| `frontend/src/composables/useTimelineMetrics.ts` | A-6 | ~15 行 |

---

# Milo-Cut 0.2.1 后期修复记录 (2026-05-16)

## 波形文件按项目隔离

**问题**: 波形文件使用全局 `data/projects/{media_hash}.waveform.json` 路径，`media_hash` 默认为空字串导致所有项目共享 `.waveform.json`，不同项目的波形互相覆盖。

**修复**:
- `main.py`: 波形路径改为 `data/projects/{project_name}/waveform.json`，存储在每个项目目录下
- `regenerate_waveform` 同步使用相同路径

## 波形重新生成后无法即时刷新

**问题**: 重新生成波形后 URL 不变 (`http://127.0.0.1:{port}/waveform`)，Vue 响应式无法检测变化，WaveformCanvas 不会重新拉取。

**修复**:
- `WorkspacePage.vue`: `resolveWaveformUrl()` 和 `handleRegenerateWaveform()` 中的轮询都添加 `?t=Date.now()` 缓存破坏参数

## Media Server CORS + 查询参数兼容

**问题**:
1. `self.path == "/waveform"` 精确匹配在 URL 含 `?t=xxx` 查询参数后返回 404
2. `send_error()` 不包含 CORS 头，浏览器同时报 CORS + 404

**修复** (`core/media_server.py`):
- 新增 `_route()` 方法: `split("?", 1)[0]` 去掉查询参数后再匹配路径
- 新增 `_send_cors_error()`: 所有错误响应带 `Access-Control-Allow-Origin: *`
- 新增 `do_OPTIONS()`: CORS 预检请求处理
- `do_HEAD()` 同步使用 `_route()` 并添加 CORS 头

## OTIO 分别淡入淡出回退为交叉溶解

**问题**: OTIO per-clip `Effect` 对象 (effect_name="Audio Fade In"/"Audio Fade Out") 不被 DaVinci Resolve 等主流 NLE 识别，且 `Effect.metadata` 属性无 setter 导致赋值报错。

**修复**:
- `export_timeline.py`: 移除 `_build_separate_fade_items()` 函数，OTIO 导出统一使用 `SMPTE_Dissolve` 过渡（交叉溶解）
- UI 选 separate 时显示 amber 提示 "OTIO export falls back to crossfade"

## FFmpeg 视频过渡实现

**概述**: 将预留的 disabled checkbox 替换为完整的视频/音频过渡系统。

### 视频过渡 (xfade chain)
- `export_service.py`: 新增 `_build_video_xfade_filter()` — video 使用 `xfade=transition=fade` 链式交叉溶解
- 追踪累积时长计算正确的 offset（修复了旧代码用原始 segment duration 导致视频卡住的 bug）

### 音频过渡 (两种模式)
- **Mode A (crossfade)**: `_build_audio_acrossfade_filter()` — `acrossfade` 链，音频段之间无缝交叉溶解
- **Mode B (separate)**: `_build_audio_fade_filter()` — 每段独立 `afade=t=in` + `afade=t=out`，段间 `concat` 拼接

### UI 重构
- 移除 "FFmpeg video transitions (experimental)" 复选框
- 过渡时长 `> 0` 时自动启用（时长 `= 0` 时不启用）
- 过渡时长滑块范围扩展至 0~2.0s (step 0.1)
- 现有 crossfade/separate 单选按钮同时控制 OTIO 和 FFmpeg 模式
- 过渡设置区块移至 "时间线格式" 上方

### 后端简化
- 移除 `use_transitions` 参数，后端从 `fade_duration > 0` 自行判断

## Files Modified

| 文件 | 改动规模 |
|------|----------|
| `core/export_service.py` | ~180 行 |
| `core/export_timeline.py` | ~100 行 |
| `core/media_server.py` | ~55 行 |
| `main.py` | ~20 行 |
| `frontend/src/pages/ExportPage.vue` | ~80 行 |
| `frontend/src/pages/WorkspacePage.vue` | ~10 行 |

---

# Milo-Cut 0.2.1 后期修复记录 (2026-05-17)

## 波形显示持久化修复

**问题**: 波形生成完成后 `waveform_path` 只更新了内存中的项目对象，未持久化到磁盘。用户关闭项目或重启应用后，`open_project` 从磁盘加载的 JSON 中 `waveform_path` 为空，波形不会加载。

**修复** (`main.py` `_handle_waveform_generation`):
- 波形生成成功后立即调用 `self._project.save_project()` 持久化 `waveform_path`
- 包裹 try-except 防止磁盘写入失败导致后台线程崩溃

## 波形加载事件驱动修复

**问题**: 新项目创建后 `resolveWaveformUrl()` 在 `onMounted` 中立即调用，但长文件波形生成需 30+ 秒，此时查询必然失败。原实现仅重试 3 次（总约 3 秒），之后静默放弃。依赖 `watch(waveform_path)` 来重新触发，但 Vue 替换整个 `project` 对象时对嵌套属性的 watcher 存在时序不可靠问题。

**修复** (`frontend/src/pages/WorkspacePage.vue`):
- 移除 3 次重试循环，改为单次尝试 + 事件驱动兜底
- 添加 `onEvent(EVENT_TASK_COMPLETED)` 监听器，当 `waveform_generation` 任务完成时直接调用 `resolveWaveformUrl()`
- 此时后端已调用 `set_waveform()` 设置了媒体服务器，查询必然成功
- `handleRegenerateWaveform` 轮询超时从 30s 增加到 120s，适配长文件

## 导出 Toast 通知时序修复

**问题**: `useExport` 的 `exportVideo/exportAudio/exportSrt` 通过任务系统执行，`startTask` 在线程启动后立即返回 `true`，但 `ExportPage` 将其视为导出完成，导致 Toast 在点击按钮时立即弹出。

**修复**:
- `useExport.ts`: 统一为 `createExportTask()` 方法，返回 task ID 而非 boolean
- `ExportPage.vue`: 添加 `pendingExportTasks` Map 跟踪进行中的导出任务
- 监听 `EVENT_TASK_COMPLETED/FAILED` 事件，匹配 task ID 后才显示成功/失败 Toast
- `statusMessage` 在任务开始时设置，在任务完成/失败时清除

## 过渡音视频同步修复

**问题**: 两种过渡模式下音视频时长不一致:

1. **crossfade 模式**: 音频 `acrossfade` 的 `cross_len` 被 `min(xfade_dur, half_prev, half_next)` 限制，但视频 `xfade` 始终使用完整 `xfade_dur`，短片段时两者时长偏差
2. **separate 模式**: 视频用 `xfade`（移除重叠），音频用 `concat`（不移除），必然导致音频比视频长 `(N-1)*xfade_dur` 秒

**修复** (`core/export_service.py` `_build_video_xfade_filter`):
- **crossfade 模式**: 视频 `xfade` duration 改为与音频相同的 clamp 计算 `min(xfade_dur, half_prev, half_next)`，保证每段过渡时长一致
- **separate 模式**: 音频从 `concat` 改为 `acrossfade` 链拼接，使用与视频相同的 clamp duration，保证总时长匹配；保留 per-clip `afade` 淡入淡出效果
- 所有时长计算保留 3 位小数精度

## 导出页面布局调整

**修复** (`ExportPage.vue`):
- 右侧导出按钮区域宽度从 `w-64` (256px) 扩宽到 `w-80` (320px)
- 预留滚动条空间，避免内容宽度比之前更窄

## Files Modified

| 文件 | 变更 |
|------|------|
| `main.py` | 波形生成后自动保存项目 |
| `frontend/src/pages/WorkspacePage.vue` | 事件驱动波形加载 + 轮询超时增加 |
| `frontend/src/pages/ExportPage.vue` | Toast 时序修复 + 面板宽度调整 |
| `frontend/src/composables/useExport.ts` | 重构为 `createExportTask` + 事件跟踪 |
| `core/export_service.py` | 过渡音视频同步修复 |

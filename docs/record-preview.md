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

## Release Notes

### 0.2.0

新增完整的导出功能，支持多种格式和编码配置：

- 导出页面：编码设置、实时预览、进度显示
- 视频导出：H.264/H.265/VP9，可配置质量/分辨率/预设
- 音频导出：独立音频文件
- SRT 字幕导出：时间轴自动调整
- EDL 时间线导出：CMX3600 格式（达芬奇）
- XML 时间线导出：FCP 7 XML 格式（Premiere Pro / 达芬奇）
- 多项 Bug 修复和稳定性改进

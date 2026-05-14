# Milo-Cut 开发记录

## Phase 0 Step 1: 项目骨架创建 (2026-05-14)

### 概述

基于 PyWebVue 框架创建了 Milo-Cut 完整项目骨架，建立了后端 `core/` 模块架构和前端 `src/` 类型/组合式函数/组件体系。骨架已通过编译验证，可端到端运行。

### 后端新增文件 (10 个)

| 文件 | 说明 |
|------|------|
| `pyproject.toml` | Python 项目配置，依赖：pywebview>=6.0, loguru>=0.7, pydantic>=2.0 |
| `core/__init__.py` | 包标记 |
| `core/events.py` | 桥接事件名常量，与前端 `utils/events.ts` 保持同步 |
| `core/paths.py` | 应用数据目录管理（迁移自 ff-intelligent-neo，APP_NAME 改为 milo-cut） |
| `core/config.py` | JSON 配置持久化，原子写入防止损坏 |
| `core/logging.py` | Loguru 日志系统，支持文件轮转和前端 sink |
| `core/models.py` | Pydantic v2 冻结数据模型：Project, Segment, MiloTask, MediaInfo, EditDecision 等 |
| `core/ffmpeg_service.py` | 媒体探测（ffprobe）+ 静音检测（FFmpeg silencedetect 滤镜） |
| `core/subtitle_service.py` | SRT 字幕解析器（完整实现，非占位） |
| `core/task_manager.py` | 统一后台任务系统：create/start/cancel，线程安全，进度事件上报 |
| `core/project_service.py` | 项目 CRUD，JSON 持久化到 data/projects/ |

### 前端新增文件 (14 个)

| 文件 | 说明 |
|------|------|
| `src/style.css` | TailwindCSS v4 主题配置 + DaisyUI v5 + Apple 设计令牌 |
| `src/types/api.ts` | ApiResponse\<T\>, BridgeMethod 联合类型 |
| `src/types/project.ts` | Project, Segment, MediaInfo, EditDecision, Word 等核心类型 |
| `src/types/task.ts` | MiloTask, TaskType, TaskStatus, TaskProgress |
| `src/utils/events.ts` | 事件名常量（与 core/events.py 同步） |
| `src/utils/format.ts` | formatTime, formatTimeShort, formatFileSize 工具函数 |
| `src/composables/useBridge.ts` | 桥接事件生命周期管理，组件卸载自动清理 |
| `src/composables/useProject.ts` | 项目状态管理（创建/打开/保存/关闭，脏标记追踪） |
| `src/composables/useTask.ts` | 统一任务管理（创建/启动/取消，实时进度同步） |
| `src/composables/useTranscript.ts` | 字幕数据操作（SRT 导入） |
| `src/components/common/FileDropInput.vue` | 拖拽/点击文件导入组件 |
| `src/components/common/ProgressBar.vue` | 任务进度条组件 |
| `src/pages/WelcomePage.vue` | 欢迎页：视频拖拽导入 + 项目创建 |
| `src/pages/WorkspacePage.vue` | 工作区：双栏布局骨架（视频预览 + 字幕编辑） |

### 修改文件

| 文件 | 变更 |
|------|------|
| `main.py` | 替换 DemoApi 为 MiloCutApi(Bridge)，17 个 @expose 方法 |
| `app.spec` | APP_NAME 改为 milo-cut，hiddenimports 添加 core 全部模块 |
| `frontend/package.json` | 新增 tailwindcss v4, @tailwindcss/vite, daisyui v5 |
| `frontend/vite.config.ts` | 添加 TailwindCSS 插件 + @ 路径别名 |
| `frontend/tsconfig.json` | 添加 baseUrl + paths 别名映射 |
| `frontend/index.html` | title 改为 Milo-Cut |
| `frontend/src/bridge.ts` | 添加 withTimeout 超时保护，轮询间隔改为 100ms |
| `frontend/src/main.ts` | 引入 style.css |
| `frontend/src/App.vue` | 重写为条件页面渲染（欢迎页/工作区） |

### Bridge API 清单 (17 个方法)

**系统：** get_app_info, select_files, select_file, open_folder, get_dropped_files

**项目：** create_project, open_project, save_project, close_project

**字幕：** import_srt

**FFmpeg：** probe_media, detect_silence

**任务：** create_task, start_task, cancel_task, get_task, list_tasks

### 验证结果

- Python 依赖安装成功（uv sync，23 packages）
- 前端依赖安装成功（bun install，67 packages）
- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：index.html 0.41 KB, CSS 17.17 KB, JS 69.87 KB
- 后端模块导入验证通过：所有 core 模块可正常加载
- MiloCutApi 实例化验证通过：get_app_info / create_task / list_tasks 正常返回

### 代码审查修复项

审查发现 1 个 CRITICAL + 4 个 HIGH 问题，已全部修复：

1. **[CRITICAL]** useTranscript 调用 4 个不存在的后端方法 -- 已移除未实现的方法，仅保留 import_srt
2. **[HIGH]** import_srt 返回类型不匹配 -- 已改为 `call<Project>` 对齐实际返回值
3. **[HIGH]** MiloCutApi 未传递 debug 标志 -- 已添加 `super().__init__(debug=True)`
4. **[HIGH]** task_manager._run_task 用过期快照覆盖进度 -- 已改为 re-read current task
5. **[HIGH]** App.vue 传入空对象导致 WorkspacePage 崩溃 -- 已改为传递真实 Project 数据

### 技术栈确认

| 层 | 技术 |
|----|------|
| 桌面容器 | pywebview 6.x (Windows: EdgeWebView2) |
| Python | 3.11+, Pydantic v2, Loguru |
| 桥接层 | PyWebVue (自定义 Bridge + @expose + tick 轮询) |
| 前端框架 | Vue 3.5 + TypeScript 5.7 |
| 样式 | TailwindCSS v4 + DaisyUI v5 |
| 构建 | Vite 6.x + vue-tsc |
| 包管理 | uv (Python) + bun (Node) |

### 下一步 (Phase 0 剩余步骤)

1. 迁移 FFmpeg 封装（从 ff-intelligent-neo 提取 command_builder 核心逻辑）
2. 完善 SRT 导入 + 静音检测端到端流程
3. 实现静音标记 + 字幕同步显示 UI
4. 实现 FFmpeg 导出剪切后视频

### 📝 Commit Message

```
feat(scaffold): 初始化 Milo-Cut 项目骨架（PyWebVue + Vue3 全栈架构）

- 后端：基于 Pydantic v2 定义核心数据模型，封装 FFmpeg 探测/静音检测、
  SRT 字幕解析、项目 CRUD 与统一任务管理模块
- 前端：建立 TypeScript 类型体系、组合式状态管理（项目/任务/字幕）、
  通用 UI 组件（文件拖拽、进度条）及欢迎页/工作区双页路由
- 桥接：实现 17 个 @expose 前后端通信方法，含超时保护与 100ms 轮询
- 修复 useTranscript 调用未实现接口、任务进度覆盖、返回值类型不匹配
  等 5 个关键问题（1 CRITICAL + 4 HIGH）
- 验证：vue-tsc 类型检查、vite build 构建、Python 模块导入全部通过
```

### 🚀 Release Notes

```
## 2026-05-14 - Milo-Cut 项目骨架初始化

### ✨ 新增
- 基于 PyWebVue + Vue3 的完整桌面应用项目架构，支持前后端桥接通信
- 项目管理功能：创建、打开、保存、关闭项目，JSON 持久化存储
- 支持 SRT 字幕文件导入与解析
- 音视频文件导入与媒体信息自动探测
- 统一后台任务系统，支持任务的创建、启动与取消
- 拖拽/点击导入文件的交互界面，包含欢迎页与工作区双页面
- 视频进度条、字幕编辑区等基础 UI 组件

### 🐛 修复
- 修复字幕模块调用未实现的后端接口导致功能不可用的问题
- 修复任务进度在运行过程中被旧数据覆盖的问题
- 修复字幕导入接口返回值类型不匹配的问题
- 修复 API 调试模式未正确启用的问题
- 修复工作区页面因接收空数据导致的崩溃问题
```

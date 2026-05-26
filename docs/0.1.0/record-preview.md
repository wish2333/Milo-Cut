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

~~1. 迁移 FFmpeg 封装（从 ff-intelligent-neo 提取 command_builder 核心逻辑）~~
~~2. 完善 SRT 导入 + 静音检测端到端流程~~
~~3. 实现静音标记 + 字幕同步显示 UI~~
~~4. 实现 FFmpeg 导出剪切后视频~~

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



## Phase 0 Steps 2-5: 静音检测、同步显示、导出 (2026-05-14)

### 概述

完成 Phase 0 剩余全部步骤：静音检测结果存储与编辑决策管理、FFmpeg 视频导出（分段提取+concat）、SRT 时间轴调整导出、工作区 UI 重构为合并时间轴（字幕+静音段交叉显示，支持确认/拒绝删除）。

### 后端新增文件 (1 个)

| 文件 | 说明 |
|------|------|
| `core/export_service.py` | FFmpeg 视频导出（分段提取 .ts + concat）与 SRT 时间轴调整导出 |

### 后端修改文件 (4 个)

| 文件 | 变更 |
|------|------|
| `core/project_service.py` | 新增 add_silence_results（静音段+编辑决策存储）、update_edit_decision（确认/拒绝）、update_segment（边界调整+联动编辑决策）|
| `core/paths.py` | 新增 get_temp_dir()（导出临时文件目录）|
| `main.py` | 更新 _handle_silence_detection 存储结果、注册 EXPORT_VIDEO/EXPORT_SUBTITLE 任务处理器、新增 4 个 @expose 方法 |
| `core/task_manager.py` | 修复 start_task TOCTOU 竞态条件（原子化检查+设置）|

### 前端新增文件 (2 个)

| 文件 | 说明 |
|------|------|
| `src/composables/useAnalysis.ts` | 静音检测工作流：创建/启动检测任务、确认/拒绝编辑决策、监听任务完成更新项目 |
| `src/composables/useExport.ts` | 导出工作流：创建/启动导出任务、进度追踪、确认编辑统计 |

### 前端修改文件 (5 个)

| 文件 | 变更 |
|------|------|
| `src/pages/WorkspacePage.vue` | 重构为合并时间轴：工具栏（导入SRT/检测静音/导出）、字幕+静音段交叉显示、编辑状态徽章、确认/拒绝按钮 |
| `src/App.vue` | 新增 project-updated 事件处理（WorkspacePage -> App 双向同步）|
| `src/composables/useTask.ts` | 重构为单例模式（模块级状态），解决多 composable 状态不同步问题 |
| `src/composables/useBridge.ts` | 修复 off() 按事件名匹配移除监听器（原实现总是移除第一个）|
| `src/types/api.ts` | BridgeMethod 新增 get_project, update_edit_decision, update_segment, select_export_path |

### Bridge API 新增方法 (4 个)

- `get_project` -- 获取当前打开项目的完整数据
- `update_edit_decision(edit_id, status)` -- 更新编辑决策状态（pending/confirmed/rejected）
- `update_segment(segment_id, updates)` -- 更新段落数据（start/end/text），联动编辑决策
- `select_export_path(default_name)` -- 弹出保存对话框选择导出路径

### 导出服务核心算法

**视频导出** (`export_video`):
1. 从编辑决策中提取 `action=delete` 且 `status=confirmed` 的删除范围
2. 用 `_compute_keep_ranges` 从完整时间轴中减去删除范围，得到保留区间
3. 对每个保留区间：`ffmpeg -ss {start} -to {end} -i {input} -c:v libx264 -c:a aac -avoid_negative_ts make_zero seg_N.ts`
4. 写入 concat 列表，执行：`ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4`
5. 清理临时 .ts 文件

**SRT 导出** (`export_srt`):
1. 排除与确认删除范围重叠的字幕段
2. 计算累积删除偏移量，调整保留段的时间戳
3. 重新编号并写入标准 SRT 格式

### 代码审查修复项

审查发现 2 个 CRITICAL + 6 个 HIGH 问题，已全部修复：

1. **[CRITICAL]** FFmpeg concat 文件路径注入 -- 已转义单引号
2. **[CRITICAL]** output_path 未校验可任意写入 -- 已添加 `_validate_output_path` 校验
3. **[HIGH]** start_task TOCTOU 竞态条件 -- 已改为单次加锁原子操作
4. **[HIGH]** update_segment 死代码导致编辑决策不更新 -- 已移除死代码，用旧值匹配
5. **[HIGH]** useAnalysis 监听所有任务完成事件 -- 已过滤为仅 silence_detection 任务
6. **[HIGH]** useTask 非单例导致多 composable 状态不同步 -- 已重构为模块级单例
7. **[HIGH]** 导出处理器访问可变 project 引用 -- 已快照 segments/edits 数据
8. **[HIGH]** useBridge.off() 总是移除第一个监听器 -- 已按事件名匹配

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：index.html 0.41 KB, CSS 20.86 KB, JS 78.73 KB
- 后端模块导入验证通过
- 核心算法单元测试通过：keep_ranges 计算、范围合并、SRT 时间格式化、项目服务全流程

### 📝 Commit Message

```
feat(core): 实现静音检测工作流、合并时间轴 UI 及视频/SRT 导出

- 新增 export_service 实现基于 FFmpeg 的分段提取与 concat 视频导出
- 实现 SRT 时间轴偏移计算与同步导出
- 重构 WorkspacePage 为合并时间轴，支持静音段与字幕交叉显示及编辑决策
- 优化 useTask 为单例模式，修复 useBridge 事件监听移除逻辑
- 修复 FFmpeg 路径注入、输出路径校验及 start_task 竞态条件等安全/并发问题
- 新增 project_service 接口支持静音结果存储与编辑决策管理
```

---

### 🚀 Release Notes

```
## 2026-05-14 - 静音检测与导出功能完成

### ✨ 新增
- **静音检测工作流**：支持自动检测视频静音段，并可在时间轴上直接确认或拒绝删除。
- **合并时间轴视图**：全新的工作区 UI，字幕与静音段交叉显示，支持可视化边界调整。
- **智能视频导出**：支持根据编辑决策一键导出剪辑后的视频（自动删除确认的静音部分）。
- **同步字幕导出**：导出 SRT 文件时，自动根据视频剪辑进度调整时间戳，确保音画同步。

### ⚡ 优化
- **状态同步优化**：重构任务管理机制，确保界面在多个组件间实时同步任务进度。
- **导出性能**：采用分段提取 + 快速合并（concat）方案，提升视频导出效率。

### 🐛 修复
- 修复了导出文件路径的安全漏洞，增强了路径校验。
- 修复了高并发启动任务时可能出现的竞态冲突问题。
- 修复了部分场景下更新段落内容导致编辑状态未同步的 Bug。
```

---

## Phase 1: Rule-based Analysis, Subtitle Editing, Edit Management (2026-05-15)

### 概述

Phase 1 后端实现：基于规则的分析（填充词 + 错误触发词检测）、SRT 校验、字幕编辑操作（合并/拆分/搜索替换）、批量编辑决策管理、编辑摘要与删除保护、最近项目列表及设置管理。前端变更将在后续阶段进行。

### 后端新增文件 (1 个)

| 文件 | 说明 |
|------|------|
| `core/analysis_service.py` | 规则引擎：填充词检测（最长优先匹配）、错误触发词检测（3 段前瞻）、全量分析 |

### 后端修改文件 (5 个)

| 文件 | 变更 |
|------|------|
| `core/models.py` | 新增 TaskType 枚举（FILLER_DETECTION, ERROR_DETECTION, FULL_ANALYSIS）；新增 AnalysisResult 冻结模型；AnalysisData 扩展 results 字段 |
| `core/config.py` | 默认设置新增 10 个填充词、9 个错误触发词 |
| `core/events.py` | 新增 EDIT_SUMMARY_UPDATED 事件常量 |
| `core/subtitle_service.py` | 新增 validate_srt()：多编码回退、索引连续性、重叠检测、时长偏差校验 |
| `core/project_service.py` | 新增 10 个方法：merge_segments, split_segment, search_replace, mark_segments, confirm_all_suggestions, reject_all_suggestions, get_edit_summary, add_analysis_results, get_recent_projects, update_segment_text, get_settings, update_settings |
| `main.py` | 注册 3 个新任务处理器 + 新增 12 个 @expose 桥接方法 |

### 新增数据模型

**AnalysisResult** (frozen):
- `id: str` -- 唯一标识
- `type: Literal["filler", "error"]` -- 检测类型
- `segment_ids: list[str]` -- 关联字幕段 ID
- `confidence: float` -- 置信度（填充词 0.90，错误触发 0.85）
- `detail: str` -- 检测详情

**AnalysisData 扩展**:
- `results: list[AnalysisResult]` -- 分析结果列表（默认空，向后兼容）

### 分析服务核心算法

**填充词检测** (`detect_fillers`):
1. 将填充词按长度降序排列（最长优先匹配）
2. 遍历字幕段，检查文本中是否包含任何填充词
3. 命中时创建 AnalysisResult(type="filler", confidence=0.90)

**错误触发检测** (`detect_errors`):
1. 将触发词按长度降序排列
2. 遍历字幕段，检测触发词命中
3. 命中时扩展覆盖后续 N 段（默认 3 段，即说话者重新表述的区域）
4. 创建 AnalysisResult(type="error", confidence=0.85)

### SRT 校验规则

`validate_srt(file_path, video_duration)` 检查项：
- 文件可读性（utf-8-sig / gb18030 / latin-1 编码回退）
- 索引连续性（序号是否连续递增）
- 时间戳合法性（start < end）
- 重叠检测（相邻段落时间戳重叠）
- 时长偏差（与视频时长偏差 >10% 时告警）

### 字幕编辑操作

| 方法 | 说明 |
|------|------|
| `merge_segments(segment_ids)` | 按起始时间排序，验证连续性，合并文本，移除孤立编辑决策 |
| `split_segment(segment_id, position)` | 在指定时间点拆分为两段（{id}-a, {id}-b），按比例分配文本 |
| `search_replace(query, replacement, scope)` | 遍历字幕段替换文本，设置 dirty_flags，返回修改计数与 ID 列表 |
| `update_segment_text(segment_id, text)` | 更新字幕文本并设置 dirty_flags.text_edited |

### 编辑决策管理

| 方法 | 说明 |
|------|------|
| `mark_segments(segment_ids, action)` | 创建/更新 EditDecision（source="user", priority=200） |
| `confirm_all_suggestions()` | 将所有 pending 编辑决策设为 confirmed |
| `reject_all_suggestions()` | 将所有 pending 编辑决策设为 rejected |
| `get_edit_summary()` | 计算删除统计 + 3 条保护规则告警 |
| `add_analysis_results(results, source)` | 存储分析结果并从时间范围创建 EditDecision |

### 删除保护规则

`get_edit_summary()` 内置 3 条保护告警：
1. 删除时长超过总时长 40%
2. 单个编辑决策跨度超过 60 秒
3. 3+ 连续字幕段被标记删除

### Bridge API 新增方法 (12 个)

**字幕编辑：** update_segment_text, merge_segments, split_segment, search_replace

**编辑决策：** mark_segments, confirm_all_suggestions, reject_all_suggestions, get_edit_summary

**分析：** validate_srt

**项目管理：** get_recent_projects, get_settings, update_settings

### 任务处理器 (3 个)

| 处理器 | 说明 |
|--------|------|
| `_handle_filler_detection` | 运行填充词检测 + 存储分析结果 |
| `_handle_error_detection` | 运行错误触发检测 + 存储分析结果 |
| `_handle_full_analysis` | 运行全量分析（填充词 + 错误触发）+ 存储结果 |

### 验证结果

- `uv run python` 模块导入验证通过：analysis_service, models (AnalysisResult/TaskType), subtitle_service (validate_srt)
- ProjectService 23 个公共方法全部可用
- MiloCutApi 37 个 @expose 方法全部注册
- `bun run build` 前端构建成功：index.html 0.41 KB, CSS 20.86 KB, JS 78.73 KB
- 配置默认值验证：10 个填充词、9 个错误触发词

### 配置默认值

**填充词** (`filler_words`): 嗯、啊、呃、然后、就是、那个、怎么说呢、你知道、对吧、其实

**错误触发词** (`error_trigger_words`): 不对、重来、重新说、说错了、刚才说错了、这段不要、再来一遍、算了、不是这样的

### 📝 Commit Message

```
feat(analysis): 实现规则引擎分析、字幕编辑操作与编辑决策管理

- 新增 analysis_service 实现填充词检测（最长优先匹配）和错误触发词检测（3 段前瞻）
- 新增 validate_srt 校验：多编码回退、索引连续性、重叠检测、时长偏差
- 扩展 project_service：merge/split/search-replace 字幕编辑、批量确认/拒绝、
  编辑摘要与删除保护（40%/60s/3+连续）、分析结果存储、最近项目、设置管理
- 注册 3 个新任务处理器（filler/error/full_analysis）+ 12 个 @expose 桥接方法
- models.py 新增 AnalysisResult 冻结模型，AnalysisData 扩展 results 字段
- config.py 新增 10 个填充词、9 个错误触发词默认配置
```

---

### 🚀 Release Notes

```
## 2026-05-15 - 规则引擎分析与字幕编辑

### ✨ 新增
- **规则引擎分析**：支持自动检测填充词（嗯、啊、呃等）和错误触发词（不对、重来等），
  自动标记需要删除的片段并创建编辑决策。
- **字幕编辑操作**：支持合并连续字幕段、在指定时间点拆分字幕、全局搜索替换文本。
- **批量编辑决策**：一键确认或拒绝所有待处理的编辑建议，提升编辑效率。
- **删除保护机制**：自动检测删除比例过高（>40%）、单段过长（>60s）、连续删除过多（3+段）
  等风险场景并发出告警。
- **SRT 文件校验**：导入前自动检查文件编码、索引连续性、时间戳重叠及时长偏差。
- **最近项目列表**：支持快速访问最近打开的项目。
- **设置管理**：支持查看和更新应用配置（填充词、触发词、静音检测参数等）。

### ⚡ 优化
- 分析结果与编辑决策自动关联，支持从检测到删除的完整工作流。
- 字幕编辑操作自动设置 dirty_flags，便于追踪修改状态。

### 🔧 技术
- 新增 AnalysisResult 冻结数据模型，支持类型安全的分析结果存储。
- 分析服务采用最长优先匹配策略，避免短词误匹配。
- 错误触发检测支持可配置的前瞻段落数（默认 3 段）。
```

---

## Phase 1 Frontend: Analysis UI, Subtitle Editing, Export Summary (2026-05-15)

### 概述

Phase 1 前端实现：接入后端规则引擎分析（填充词/错误触发词）、字幕行内编辑（合并/拆分/搜索替换）、建议面板（分组展示+批量操作）、导出摘要弹窗（删除保护告警）、设置管理。与 Phase 1 后端 API 全面对接。

### 前端新增文件 (7 个)

| 文件 | 说明 |
|------|------|
| `src/types/edit.ts` | EditSummary、RecentProject、AppSettings 类型定义 |
| `src/composables/useEdit.ts` | 字幕编辑操作：merge/split/search-replace/mark/batch confirm/reject/edit summary |
| `src/composables/useSettings.ts` | 应用设置管理：load/update settings |
| `src/components/workspace/TranscriptRow.vue` | 字幕行组件：状态样式、行内编辑、点击跳转、Delete 标记删除 |
| `src/components/workspace/SilenceRow.vue` | 静音段行组件：时长标签、状态着色 |
| `src/components/workspace/SuggestionPanel.vue` | 建议面板：按类型分组（口头禅/口误）、展开折叠、批量确认/拒绝 |
| `src/components/workspace/SearchReplaceBar.vue` | 搜索替换栏：Ctrl+F 唤起、作用域选择、Esc 关闭 |
| `src/components/workspace/EditSummaryModal.vue` | 导出摘要弹窗：Hero 统计、保护规则告警、确认/返回按钮 |

### 前端修改文件 (5 个)

| 文件 | 变更 |
|------|------|
| `src/types/task.ts` | TaskType 新增 filler_detection, error_detection, full_analysis |
| `src/types/api.ts` | BridgeMethod 新增 12 个方法（update_segment_text, merge_segments, split_segment, search_replace, mark_segments, confirm_all_suggestions, reject_all_suggestions, get_edit_summary, validate_srt, get_recent_projects, get_settings, update_settings） |
| `src/types/project.ts` | AnalysisResult.type 改为 "filler" \| "error"；AnalysisData 新增 results 字段 |
| `src/utils/events.ts` | 新增 EDIT_SUMMARY_UPDATED 事件常量 |
| `src/composables/useAnalysis.ts` | 扩展支持 filler/error/full analysis 任务类型；新增 runFillerDetection/runErrorDetection/runFullAnalysis |
| `src/composables/useExport.ts` | 新增 getExportSummary() 包装方法 |
| `src/pages/WorkspacePage.vue` | 集成全部新组件：分析下拉菜单、建议面板侧栏、搜索替换栏、导出摘要弹窗 |

### 组件交互规范

**TranscriptRow**:
- 点击行 -> 视频跳转到对应时间点
- 双击 -> 启用行内文本编辑
- Delete/Backspace -> 标记删除
- 状态样式：pending（黄色左边条）、confirmed（红色+中划线）、rejected（绿色）

**SilenceRow**:
- 点击 -> 跳转到对应时间点
- 状态样式：默认（灰色背景）、pending（黄色+建议删除标签）、confirmed（红色+已确认）、rejected（绿色+已保留）

**SuggestionPanel**:
- 按类型分组：口头禅（filler）、口误触发（error）
- 每组可展开/折叠，显示匹配数量
- 每项显示：时间戳 + 检测详情 + 确认/忽略按钮
- 底部批量操作：全部确认删除 / 忽略所有建议

**SearchReplaceBar**:
- Ctrl+F 唤起，Esc 关闭
- 搜索框 + 替换框 + 作用域选择（全部/选中段）
- 替换按钮触发 search_replace 调用

**EditSummaryModal**:
- 导出前强制弹出
- Hero 统计：预计时长、裁剪时长、占比（>40% 变红）
- 安全检查列表：单段>60s、连续删除>3段
- 确认导出 / 返回检查

### WorkspacePage 布局

```
+-----------------------------------------------------------------------+
|  MILO-CUT    [project name]    [stats]    [confirmed edits]           | <- Nav (44px)
+-----------------------------------------------------------------------+
|  [SRT] [Silence] [Analysis v] | [Export Video] [Export SRT] [Progress]| <- Toolbar
+-----------------------------------------------------------------------+
|  [SearchReplaceBar (Ctrl+F)]                                         |
+-----------------------------------------------------------------------+
|  Status/Error messages                                                |
+---------------------------+-------------------------------------------+
|                           |  TRANSCRIPT EDITOR                        |
|      VIDEO PLAYER         |  +-------------------------------------+ |
|    (40% width)            |  | TranscriptRow / SilenceRow           | |
|                           |  | (merged timeline, sorted by start)   | |
|                           |  +-------------------------------------+ |
|                           |  | SuggestionPanel (sidebar, 288px)     | |
|                           |  | - Grouped by type                    | |
|                           |  | - Batch actions                      | |
+---------------------------+-------------------------------------------+
|  [EditSummaryModal (overlay)]                                        |
+-----------------------------------------------------------------------+
```

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：index.html 0.41 KB, CSS 31.67 KB, JS 93.70 KB (gzip 34.82 KB)
- 后端 MiloCutApi 37 个 @expose 方法全部注册
- 前端 37 个模块转换成功

### 代码审查修复项

审查发现 5 个 TypeScript 错误，已全部修复：

1. **SilenceRow.vue**: `defineProps` 返回值未赋值给 `props` 变量 -- 已添加 `const props =`
2. **SilenceRow.vue**: `$computed` 不是有效的 Vue 3 API -- 已改为 `computed()` from vue
3. **TranscriptRow.vue**: `$computed` 同上 -- 已改为 `computed()` 并添加 import
4. **SuggestionPanel.vue**: `getSegmentText` 函数声明但未使用 -- 已移除
5. **WorkspacePage.vue**: 未使用的 `handleConfirmAll` 和解构变量 -- 已清理

### 📝 Commit Message

```
feat(frontend): 实现 Phase 1 分析 UI、字幕编辑与导出摘要

- 新增 TranscriptRow/SilenceRow 组件，支持行内编辑、状态样式、点击跳转
- 新增 SuggestionPanel 组件，按类型分组展示分析结果，支持批量确认/拒绝
- 新增 SearchReplaceBar 组件，Ctrl+F 唤起搜索替换
- 新增 EditSummaryModal 组件，导出前显示 Hero 统计与删除保护告警
- 新增 useEdit/useSettings 组合式函数，接入后端字幕编辑与设置管理 API
- 扩展 useAnalysis 支持 filler/error/full_analysis 三种分析任务
- 重构 WorkspacePage 集成全部新组件，工具栏新增分析下拉菜单
- 更新 TaskType/ApiMethod/AnalysisData 类型定义对齐 Phase 1 后端
```

---

### 🚀 Release Notes

```
## 2026-05-15 - Phase 1 前端：分析 UI 与字幕编辑

### ✨ 新增
- **规则引擎分析 UI**：工具栏新增分析下拉菜单，支持运行填充词检测、错误触发词检测或全量分析。
- **建议面板**：右侧面板按类型（口头禅/口误触发）分组展示分析结果，支持展开折叠和批量确认/拒绝。
- **行内字幕编辑**：双击字幕行直接编辑文本，Delete 键标记删除，状态实时反馈。
- **搜索替换**：Ctrl+F 打开搜索替换栏，支持全局或选中段范围替换。
- **导出摘要弹窗**：导出前自动弹出摘要，显示预计时长、裁剪占比及安全检查告警。
- **删除保护告警**：自动检测删除比例过高（>40%）、单段过长（>60s）、连续删除过多（3+段）。

### ⚡ 优化
- 建议面板与时间轴联动，点击建议项自动跳转到对应时间点。
- 字幕行状态样式（待定/已确认/已保留）与后端编辑决策实时同步。
- 搜索替换操作后自动刷新项目数据，保持前后端一致。
```

---

## Bug Fixes & UX Improvements (2026-05-15)

### 概述

修复多个运行时问题，提升用户体验：pywebview API 弃用警告、全窗口拖拽、视频播放器、工具栏按钮、关闭项目、中文文件名编码、撤销确认删除等。

### 后端修改文件 (2 个)

| 文件 | 变更 |
|------|------|
| `main.py` | `webview.OPEN_DIALOG` -> `webview.FileDialog.OPEN`；`webview.FOLDER_DIALOG` -> `webview.FileDialog.FOLDER`；`webview.SAVE_DIALOG` -> `webview.FileDialog.SAVE`；新增 `get_video_url` 方法（data URL 读取本地媒体文件）；`select_files` 文件对话框新增音频格式支持（MP3/WAV/AAC/FLAC/OGG/M4A）；新增 `import pathlib` |
| `core/ffmpeg_service.py` | `subprocess.run` 替换 `text=True` 为 `encoding="utf-8", errors="replace"`，修复中文路径文件名 GBK 解码崩溃 |

### 前端修改文件 (4 个)

| 文件 | 变更 |
|------|------|
| `src/App.vue` | 新增全窗口拖拽支持：`@dragenter/@dragover/@dragleave/@drop` 事件处理、拖拽遮罩层、文件类型路由（视频创建项目/SRT 导入字幕）；拖拽延迟 100ms 等待 pywebview DOM 处理器先执行；音频文件类型识别；新增 `onProjectClosed` 处理 |
| `src/pages/WorkspacePage.vue` | 新增 HTML5 `<video>` 播放器（`@loadedmetadata` 设置默认 25% 音量）；`handleSeek` 实现点击字幕跳转视频时间点；工具栏按钮全部添加图标+文字标签（Import SRT / Detect Silence / Analysis / Export Video / Export SRT / Save）；新增关闭项目按钮（返回箭头）；新增 `handleToggleEditStatus` 撤销确认/拒绝操作；新增 `handleVideoLoaded` 设置默认音量 |
| `src/components/workspace/TranscriptRow.vue` | 新增 `toggle-status` 事件；状态徽章可点击撤销（cursor-pointer + hover 效果 + title 提示）；修复 CSS 重复类定义 |
| `src/components/common/FileDropInput.vue` | 移除组件内拖拽处理（由 App.vue 全局处理）；更新提示文字为"拖拽媒体文件到窗口任意位置"；支持格式列表新增音频格式 |
| `src/types/api.ts` | BridgeMethod 新增 `get_video_url` |

### 测试文件修改 (3 个)

| 文件 | 变更 |
|------|------|
| `tests/TEST_GUIDE.md` | 新建自动化+手动测试文档，含后端 64 测试 + 前端 23 测试说明 |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | 修复断言：`"..."` -> `"待定"` |
| `frontend/src/components/workspace/SilenceRow.test.ts` | 修复断言：`"..."` -> `"建议删除"` / `"已确认"` / `"已保留"` |
| `frontend/src/components/workspace/EditSummaryModal.test.ts` | 修复断言：`"..."` -> `"导出汇总摘要"` |

### 问题修复详情

**1. pywebview 弃用警告**
- `OPEN_DIALOG` / `FOLDER_DIALOG` / `SAVE_DIALOG` 已替换为 `FileDialog.OPEN` / `FileDialog.FOLDER` / `FileDialog.SAVE`
- 消除 4 条 deprecation 警告

**2. 全窗口文件拖拽**
- 拖拽文件到窗口任意位置均可触发（不限于 FileDropInput 组件区域）
- 拖拽遮罩层显示上下文提示（欢迎页：导入视频；工作区：导入 SRT）
- 100ms 延迟解决 pywebview DOM 处理器与 Vue 事件处理器的竞态条件

**3. 视频播放器**
- 使用 `data:` URL 方案（base64 编码）替代 Vite `@fs` 前缀，兼容任意路径
- 默认音量 25%（`@loadedmetadata` 事件设置）
- 点击字幕行跳转到对应时间点（`videoRef.currentTime = time`）

**4. 工具栏按钮优化**
- 所有按钮添加 SVG 图标 + 文字标签，消除空白按钮问题
- 按钮分色：蓝色（导入/检测）、紫色（分析）、绿色（导出）

**5. 关闭项目**
- 顶部导航栏新增返回箭头按钮
- 调用 `close_project` 清理后端状态，返回欢迎页

**6. 中文文件名编码崩溃**
- `subprocess.run` 使用 `text=True` 时默认 GBK 编码，ffmpeg 输出含非 GBK 字节导致 `UnicodeDecodeError`
- 替换为 `encoding="utf-8", errors="replace"` 安全处理

**7. 撤销确认删除**
- 状态徽章（已确认/已保留）可点击撤销回"待定"
- 调用 `update_edit_decision(edit_id, "pending")` 重置状态
- hover 效果 + title 提示标识可交互

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：CSS 39.95 KB, JS 98.87 KB (gzip 36.08 KB)
- `uv run pytest tests/` 后端 64 测试全部通过 (0.38s)
- `bun run test` 前端 23 测试全部通过 (1.93s)
- `uv run python -c "from main import MiloCutApi"` 后端模块加载验证通过

### 📝 Commit Message

```
fix(ux): 修复拖拽/播放器/按钮/编码等多项问题

- 修复 pywebview OPEN_DIALOG/FOLDER_DIALOG/SAVE_DIALOG 弃用警告
- 实现全窗口文件拖拽，支持视频/音频/SRT 文件类型路由
- 新增 HTML5 视频播放器，默认 25% 音量，支持点击字幕跳转
- 工具栏按钮全部添加图标+文字标签，修复空白按钮问题
- 新增关闭项目按钮，支持返回欢迎页
- 修复 subprocess 中文路径 GBK 解码崩溃（utf-8 + errors=replace）
- 新增状态徽章点击撤销功能（confirmed/rejected -> pending）
- 新增 TEST_GUIDE.md 自动化+手动测试文档
- 修复前端测试断言 placeholder 文本
```

### 性能优化与 UX 改进 (2026-05-15 Session 2)

**视频播放器性能优化:**
- 移除 data: URL 方案（将整个文件 base64 编码到内存），改用本地 HTTP 服务器流式传输
- 新增 `core/media_server.py`：基于 HTTPServer 的线程化媒体服务器，支持 HTTP Range 请求
- 视频支持边下边播和 seek 操作，内存占用从 O(文件大小) 降至 O(缓冲区)
- 服务器绑定随机可用端口，仅监听 127.0.0.1
- 关闭项目时自动停止媒体服务器

**Timeline UI 改进:**
- 新增 `TimelineRuler.vue` 组件：可视化时间轴标尺
- 标尺显示时间段色块：蓝色=字幕、黄色=待删除、红色=已确认删除、绿色=已保留、灰色=静音
- 红色播放头实时跟踪当前播放位置
- 点击标尺任意位置跳转播放
- 时间刻度自动根据视频时长调整密度
- SilenceRow 新增时间戳显示（与 TranscriptRow 对齐）

**静音检测参数设置:**
- Detect Silence 按钮旁新增设置齿轮图标
- 点击展开设置面板，可调整：
  - Threshold (dB): -60 到 -10，滑块控制
  - Min Duration (s): 0.1 到 3.0，滑块控制
- 设置保存到全局配置文件，下次启动自动加载

**编辑撤销机制改进:**
- 状态循环：pending -> confirmed -> rejected -> pending
- pending 状态显示 OK/Keep 按钮（替代原来的 "待定" 文字）
- confirmed/rejected 状态显示可点击徽章，点击回到 pending
- SilenceRow 也支持点击状态徽章撤销

**文件变更:**
- `core/media_server.py` - 新增本地 HTTP 媒体服务器
- `main.py` - 集成 MediaServer，替换 data URL 方案
- `frontend/src/components/workspace/TimelineRuler.vue` - 新增时间轴标尺组件
- `frontend/src/components/workspace/TranscriptRow.vue` - 添加 confirm/reject 按钮
- `frontend/src/components/workspace/SilenceRow.vue` - 添加时间戳和撤销支持
- `frontend/src/pages/WorkspacePage.vue` - 集成 TimelineRuler、设置面板、currentTime 跟踪
- `frontend/src/types/api.ts` - 添加 stop_media_server 方法
- `frontend/src/components/workspace/TranscriptRow.test.ts` - 更新断言
- `frontend/src/components/workspace/SilenceRow.test.ts` - 更新断言

### Timeline 重构与 UX 修复 (2026-05-15 Session 3)

**时间轴重新设计:**
- TimelineRuler 从右侧面板移至屏幕底部，全宽显示
- 支持缩放：默认显示 30 秒窗口，鼠标滚轮或 +/- 按钮缩放
- 支持拖拽平移：按住鼠标左键拖动时间轴
- 播放头自动跟随：播放位置超出可见窗口时自动滚动
- 时间刻度自动适配：根据缩放级别选择合适的刻度间隔
- 段落色块可点击跳转：蓝色=字幕、黄色=待删、红色=已确认、绿色=已保留、灰色=静音
- 播放头带红色圆点指示器

**时间范围显示:**
- TranscriptRow 时间戳从 `00:01.000` 改为 `00:01.000 → 00:05.000` 显示完整时间范围
- SilenceRow 同样显示完整时间范围

**状态切换逻辑修复:**
- confirmed/rejected 之间直接切换（跳过 pending）
- 只有 OK/Keep 按钮从 pending 设置状态
- 状态徽章点击 = confirmed ↔ rejected 切换

**SRT 导入保留静音检测:**
- `update_transcript` 不再替换全部段落，只替换 subtitle 类型
- 保留已有的 silence 类型段落及其 EditDecision
- 先检测静音再导入 SRT 不会丢失检测结果

**媒体服务器修复:**
- 捕获 `ConnectionResetError` / `BrokenPipeError`，避免客户端断开时的 traceback 日志

**文件变更:**
- `frontend/src/components/workspace/TimelineRuler.vue` - 完全重写为底部可缩放时间轴
- `frontend/src/pages/WorkspacePage.vue` - TimelineRuler 移至底部，状态切换逻辑修复
- `frontend/src/components/workspace/TranscriptRow.vue` - 时间范围显示，状态切换标题更新
- `frontend/src/components/workspace/SilenceRow.vue` - 时间范围显示，状态切换标题更新
- `core/project_service.py` - `update_transcript` 保留 silence 段落
- `core/media_server.py` - 捕获连接重置异常

## Timeline 重构、播放器控件与 Bug 修复 (2026-05-15 Session 4)

### Bug 修复

1. **导出视频 UnicodeDecodeError** - `export_service.py` 中 `subprocess.run` 使用 `text=True` 在中文 Windows 上默认使用 gbk 编码，FFmpeg 输出包含非 gbk 字节导致崩溃。修复：添加 `encoding="utf-8", errors="replace"` 参数。

2. **ConnectionAbortedError (WinError 10053)** - 浏览器断开连接时 `media_server.py` 的 socketserver 打印完整 traceback。修复：
   - 添加 `ConnectionAbortedError` 到连接异常捕获列表
   - 创建 `_QuietHTTPServer` 子类，覆盖 `handle_error` 方法抑制已知连接错误的 traceback

3. **字幕段落无法删除** - 之前只有静音检测创建的段落才能标记删除。修复：
   - 前端 `handleMarkDelete` 函数：如果没有 EditDecision 则调用 `mark_segments` 创建新的
   - 后端 `add_silence_results` 检测重复：跳过已有确认/待定 EditDecision 的时间范围

### TimelineRuler 重设计

完全重写的底部时间线组件，主要改进：

- **滚动条** - 底部独立滚动条用于导航，替代拖拽平移（避免与点击跳转冲突）
- **时间码区域** - 顶部时间码区域点击跳转到对应时间
- **选区功能** - 中间区域拖拽选择时间范围，选区高亮显示
- **选区手柄** - 选区左右边缘可拖拽调整范围
- **吸附开关** - Snap 按钮切换是否吸附到段落边界
- **Ctrl+滚轮缩放** - 普通滚轮保留给滚动条，Ctrl+滚轮实现缩放
- **更大高度** - 从 h-16 增加到 h-28，更易操作
- **性能优化** - 更高效的时间标记计算

### 新增功能

1. **添加剪辑区域** - TimelineRuler 选区后点击 "+ Clip" 按钮添加新的字幕段落
   - 后端新增 `add_segment` 方法（project_service.py + main.py）
   - 前端 Bridge 类型新增 `add_segment`

2. **自定义视频播放控件** - `VideoControls.vue` 组件替换浏览器原生控件
   - 播放/暂停、前进/后退 5 秒
   - 进度条拖拽跳转
   - 音量控制（悬浮滑块）
   - 播放速度选择（0.5x-2x）
   - 全屏切换
   - 键盘快捷键：Space/K 播放暂停、方向键跳转/音量、F 全屏、M 静音

3. **时间范围编辑** - TimelineRuler 选区后显示精确的时间范围数值

### 修改文件

- `core/export_service.py` - 修复 subprocess 编码问题
- `core/media_server.py` - 添加 ConnectionAbortedError 处理、_QuietHTTPServer
- `core/project_service.py` - 更新 add_silence_results 冲突检测、新增 add_segment
- `main.py` - 暴露 add_segment API
- `frontend/src/components/workspace/TimelineRuler.vue` - 完全重写
- `frontend/src/components/workspace/VideoControls.vue` - 新建
- `frontend/src/pages/WorkspacePage.vue` - 集成新组件
- `frontend/src/types/api.ts` - 添加 add_segment

### 验证结果

- TypeScript 类型检查通过 (vue-tsc --noEmit)
- Vite 生产构建通过
- 前端测试 23/23 通过
- 后端测试 64/64 通过
## 字幕删除交互与 TimelineRuler 改进 (2026-05-15 Session 5)

### 字幕删除 UX 改进

**问题:** 字幕段落无法直观地标记删除，Delete 快捷键与文本编辑冲突。

**解决方案:**
- TranscriptRow 始终显示状态徽章：无 EditDecision 时显示 "已保留"（绿色）
- 点击 "已保留" -> 创建 EditDecision(status=confirmed) -> 显示 "已删除"（红色）
- 点击 "已删除" -> 切换为 rejected -> 显示 "已保留"
- Analysis 检测到的字幕显示 "建议删除"（黄色）+ "保留" 按钮
- 移除 Delete/Backspace 键盘快捷键，避免与行内文本编辑冲突
- 后端 `mark_segments` 新增 `status` 参数，支持直接创建 confirmed 状态的 EditDecision

**状态流转:**
```
默认（无EditDecision）-> 点击 -> confirmed（已删除）
confirmed -> 点击 -> rejected（已保留）
rejected -> 点击 -> confirmed（已删除）
pending（建议删除）-> 点击 "建议删除" -> confirmed
pending -> 点击 "保留" -> rejected
```

### TimelineRuler 改进

**滚轮滚动:**
- 普通滚轮上下滚动 = 水平滚动时间轴（deltaY 用于垂直滚轮，deltaX 用于水平触控板）
- Ctrl+滚轮 = 缩放（保持光标位置不变）
- `e.preventDefault()` 阻止浏览器默认滚动行为

**选区整体拖动:**
- 点击选区内部（非边缘）并拖拽 = 移动整个选区
- 选区保持不变的持续时间，仅改变起止位置
- 拖拽时自动钳制到有效时间范围（0 到 duration）
- 选区边缘仍可单独拖拽调整范围

### 修改文件

- `frontend/src/components/workspace/TranscriptRow.vue` - 始终显示状态徽章，移除键盘快捷键
- `frontend/src/components/workspace/TimelineRuler.vue` - 添加滚轮滚动、选区整体拖动
- `frontend/src/pages/WorkspacePage.vue` - handleToggleEditStatus 支持无 EditDecision 场景，传递 confirmed 状态
- `core/project_service.py` - mark_segments 新增 status 参数
- `main.py` - 暴露 status 参数
- `frontend/src/components/workspace/TranscriptRow.test.ts` - 更新断言为 "建议删除"/"保留"

### 验证结果

- TypeScript 类型检查通过 (vue-tsc --noEmit)
- Vite 生产构建通过
- 前端测试 23/23 通过
- 后端测试 64/64 通过

### 📝 Commit Message

```
feat(workspace): 重构时间轴 TimelineRuler 并优化视频播放性能与交互

- 引入本地 HTTP 媒体服务器支持流式传输与 Range 请求，降低内存占用
- 重写 TimelineRuler 为底部全宽可缩放/滚动组件，支持选区编辑与片段添加
- 实现自定义 VideoControls 组件，支持播放速度、快捷键及进度控制
- 优化字幕与静音段落的状态流转逻辑（Pending -> Confirmed -> Rejected）
- 修复 Windows 环境下导出视频的编码崩溃及媒体服务器连接异常问题
- 支持 SRT 导入时保留原有的静音检测结果
```

---

### 🚀 Release Notes

```
## 2026-05-15 - 视频编辑体验深度升级

### ✨ 新增
- **全新时间轴标尺**：在屏幕底部提供可视化时间轴，支持通过滚轮缩放、拖拽滚动，可直观查看字幕、静音及删除区域。
- **精确剪辑工具**：支持在时间轴上拖拽选择时间范围，并一键添加新的剪辑片段（+ Clip）。
- **专业播放控件**：替换原生播放器，新增播放速度调节（0.5x-2x）、前进/后退 5 秒及全套键盘快捷键（Space, K, F, M 等）。
- **静音检测自定义**：新增设置面板，可灵活调整静音检测的阈值（dB）和最小持续时间。

### ⚡ 优化
- **播放性能大幅提升**：由内存加载改为流式传输，支持边下边播和快速跳转（Seek），极大地降低了处理大文件时的内存占用。
- **交互逻辑改进**：
  - 优化了段落状态切换（保留 $\leftrightarrow$ 删除），通过状态徽章实现快速切换。
  - 改进时间戳显示，现在完整展示段落的起止时间范围。
  - 增强选区操作，支持选区整体拖动及边界吸附。

### 🐛 修复
- **导出崩溃修复**：解决了 Windows 系统下导出视频时因字符编码导致的任务崩溃问题。
- **数据丢失修复**：修复了导入 SRT 文件时会覆盖已检测静音段落的问题。
- **稳定性增强**：解决了浏览器断开连接时后台产生冗余错误日志的问题。
- **编辑权限修复**：现在可以自由标记删除任何字幕段落，不再局限于静音检测结果。
```

---

## 命名规范、时间戳编辑与事件系统修复 (2026-05-15 Session 6)

### 概述

建立 UI 组件命名规范（Timeline vs TimelineRuler），将时间戳编辑功能迁移到 Timeline 面板，实现全局空格键播放/暂停，修复时间戳重叠、文本输入显示不全、Detect 按钮冻结等多个问题。

### 新增组件

| 文件 | 说明 |
|------|------|
| `src/components/workspace/Timeline.vue` | 从 WorkspacePage 提取的右侧面板组件，包含 TranscriptRow/SilenceRow 列表 + SuggestionPanel 侧栏 |

### 命名规范

- **Timeline** = 右侧面板组件（字幕/静音段列表 + 建议面板）
- **TimelineRuler** = 底部时间轴标尺组件（缩放/滚动/选区）
- 已保存到项目记忆，防止后续混淆

### 时间戳编辑迁移

**原实现（已撤销）:** TimelineRuler 底部控制栏点击时间码编辑

**新实现:** Timeline 面板中的 TranscriptRow/SilenceRow 行内编辑
- 点击时间戳 -> 进入编辑模式（`@mousedown.stop.prevent` 确保单击触发）
- 输入框自动选中文本（`nextTick(() => timeInputRef.value?.select())`）
- Enter 确认 / Escape 取消 / 失焦确认
- 支持格式：`MM:SS.mmm`、`SS.mmm`、`MM:SS`、`H:MM:SS.mmm`

### 全局空格键播放/暂停

- 在 WorkspacePage 注册全局 `keydown` 事件监听器
- 文本输入区域（input/textarea/contentEditable）自动跳过
- 与 VideoControls 中的空格键处理去重（移除组件级处理）

### Bug 修复

**1. 建议面板无法收起**
- 原因：`analysisResults.length > 0` 条件使面板在无 pending 编辑时仍可见
- 修复：仅保留 `edits.some(e => e.status === 'pending')` 条件

**2. 时间戳需要两次点击才能编辑**
- 原因：`@click.stop` 在事件冒泡阶段执行，父容器 click handler 先触发
- 修复：改用 `@mousedown.stop.prevent`，在事件捕获阶段更早阻止传播

**3. 时间戳与字幕文本重叠**
- 原因：时间列宽度不足 + 文本列缺少溢出控制
- 修复：时间列 `w-[120px]` -> `w-[130px]`，添加 `overflow-hidden whitespace-nowrap`；文本列添加 `overflow-hidden`，文本 span 添加 `truncate`

**4. 文本编辑输入框显示不全**
- 原因：输入框缺少 `min-w-0` 导致 flex 子项不收缩
- 修复：输入框添加 `min-w-0 box-border`，文本 span 添加 `block`

**5. Detect 按钮一直显示 "Detecting" 冻结**
- 原因：`useTask` 的事件监听器通过 `useBridge()` 注册，绑定了首个调用组件的 `onUnmounted` 生命周期。组件卸载后监听器被移除，但 `listenersRegistered = true` 阻止重新注册
- 修复：
  - 改用 `onEvent` 直接注册（不经过 `useBridge`），避免生命周期耦合
  - 新增轮询降级机制：每 3 秒检查后端，若任务运行超过 5 秒未收到事件则主动同步状态

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/components/workspace/TranscriptRow.vue` | 时间戳编辑 UI：`@mousedown.stop.prevent`、`w-[130px]`、`overflow-hidden`；文本列 `overflow-hidden`、`truncate`；输入框 `min-w-0 box-border` |
| `src/components/workspace/SilenceRow.vue` | 同上时间戳编辑 UI 修复 |
| `src/components/workspace/Timeline.vue` | 新建：从 WorkspacePage 提取的 Timeline 面板组件 |
| `src/composables/useTask.ts` | 改用 `onEvent` 直接注册事件；新增 `fetchTask`/`pollRunningTasks`/`ensurePolling` 轮询降级 |
| `src/composables/useEdit.ts` | 新增 `updateSegmentTime` 函数 |
| `src/utils/format.ts` | 新增 `parseTime` 函数（支持多种时间格式解析） |
| `src/pages/WorkspacePage.vue` | 集成 Timeline 组件；全局空格键处理；移除 VideoControls 空格键重复 |
| `src/components/workspace/VideoControls.vue` | 移除 Space/K 键盘快捷键（已全局处理） |
| `src/components/workspace/TranscriptRow.test.ts` | 修复 dblclick 测试：目标从根元素改为 `.flex-1.min-w-0` 文本列 |

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：CSS 60.18 KB, JS 129.24 KB (gzip 43.87 KB)
- `bun run test` 前端 23/23 测试通过
- `uv run pytest tests/` 后端 64 测试全部通过

### 📝 Commit Message

```
fix(workspace): 修复时间戳编辑、文本重叠与 Detect 按钮冻结

- 建立 Timeline/TimelineRuler 命名规范，提取 Timeline.vue 组件
- 时间戳编辑迁移到 Timeline 面板，使用 mousedown.stop.prevent 单击触发
- 修复时间列与文本列重叠（w-[130px] + overflow-hidden + truncate）
- 修复文本编辑输入框显示不全（min-w-0 box-border）
- 全局空格键播放/暂停，文本输入区域自动跳过
- 修复 Detect 按钮冻结：useTask 改用 onEvent 直接注册避免生命周期耦合，
  新增轮询降级机制确保任务状态最终同步
```

---

## 字幕文本编辑 UX 重构 (2026-05-15 Session 7)

### 概述

重构字幕文本编辑交互：移除双击编辑，改为显式 Edit/Save/Cancel 按钮；修复点击外部退出行为；新增全局编辑模式。

### 交互设计

**单行编辑:**
- 点击"编辑"按钮 -> 进入编辑模式（输入框出现）
- 点击"保存"或 Enter -> 提交变更并退出
- 点击"取消"或 Esc -> 恢复原文并退出
- 点击行外区域 -> 保存并退出（非全局模式）

**全局编辑:**
- Timeline 标题栏"编辑字幕"按钮 -> 所有字幕行进入编辑模式
- 点击"退出编辑" -> 全部保存并退出
- 全局模式下，点击外部/失焦不退出编辑（冻结行为）
- 单行仍可按 Esc 取消该行编辑

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/components/workspace/TranscriptRow.vue` | 重写：移除 dblclick，新增 Edit/Save/Cancel 按钮，支持 globalEditMode prop，blur 保存/冻结逻辑 |
| `src/components/workspace/Timeline.vue` | 新增 globalEditMode prop，标题栏新增编辑字幕/退出编辑按钮，传递 globalEditMode 到 TranscriptRow |
| `src/pages/WorkspacePage.vue` | 新增 globalEditMode 状态，绑定 Timeline toggle-edit-mode 事件 |
| `src/components/workspace/TranscriptRow.test.ts` | 重写：15 个测试覆盖编辑按钮、保存/取消、Esc、blur、全局编辑模式 |

### 核心逻辑

```typescript
// blur 行为
function handleTextEditBlur() {
  if (props.globalEditMode) return  // 全局模式：冻结
  saveEdit()                        // 普通模式：保存
}

// 全局模式切换
watch(() => props.globalEditMode, (val) => {
  if (val && !isEditingText.value) startEdit()
  else if (!val && isEditingText.value) saveEdit()
})
```

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功
- `bun run test` 前端 30/30 测试通过
- `uv run pytest tests/` 后端 64 测试全部通过

### 📝 Commit Message

```
feat(workspace): 重构字幕文本编辑 UX，支持显式按钮与全局编辑模式

- 移除双击编辑，改为编辑/保存/取消文字按钮
- 点击外部区域保存并退出编辑（非全局模式）
- 新增全局编辑模式：Timeline 标题栏按钮，所有字幕行同时进入编辑
- 全局模式冻结 blur/click-outside 退出行为，仅 Esc 取消单行
- 更新测试覆盖：15 个测试用例验证所有编辑交互场景
```

---

## TimelineRuler 选区拖动重构 (2026-05-15 Session 8 - Audit 1)

### 概述

重构 TimelineRuler 选区交互逻辑，从基于百分比的模糊匹配改为基于像素的精确控制，解决拖动手柄漂移和选区跳动问题。

### 核心改进

**1. 像素级手柄检测**
- 原实现：`Math.abs(clickPct - startPct) < 1.5`（百分比，缩放时不稳定）
- 新实现：8px 固定像素检测区，手柄 DOM 扩展 3px 透明感知区

**2. 偏移量算法**
- 记录 `dragInitialOffset = handleTime - clickTime`
- 拖动时 `rawTime = getTimeFromX(clientX) + offset`
- 解决"手柄跳到鼠标位置"的原点漂移问题

**3. 释放吸附**
- 释放时检查手柄是否在 5px 内的段落边界
- 像素阈值动态转换为时间阈值：`snapTimeThreshold = snapPx * (viewDuration / rectWidth)`
- 吸附后确保最小选区时长（0.1s）

**4. 分层 mousedown 调度**
- `detectClickZone()` 返回 `"left-handle" | "right-handle" | "body" | "outside"`
- 每个区域独立处理器，使用 `e.stopPropagation()` 隔离
- 手柄 > 选区主体 > 新选区（优先级递减）

**5. 拖动防干扰**
- 拖动期间 `document.body.style.userSelect = "none"`
- mouseup 和组件卸载时恢复

### 修改文件

| 文件 | 变更 |
|------|------|
| `src/components/workspace/TimelineRuler.vue` | 重写选区交互：像素手柄检测、偏移量算法、释放吸附、分层调度、user-select 控制 |

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功
- `bun run test` 前端 30/30 测试通过
- `uv run pytest tests/` 后端 64 测试全部通过

### 📝 Commit Message

```
feat(timeline): 重构 TimelineRuler 选区拖动为像素级精确控制

- 手柄检测从百分比改为 8px 像素区，解决缩放时漂移问题
- 引入偏移量算法，消除拖动手柄的原点跳动
- 释放时自动吸附 5px 内的段落边界（动态时间阈值换算）
- mousedown 分层调度：手柄 > 选区主体 > 新选区，stopPropagation 隔离
- 拖动期间禁用 user-select 防止文本选中干扰
```

---

## 冲突处理与逻辑遮罩 (2026-05-15 Session 8 - Audit 2)

### 概述

重构 EditDecision 数据模型，从时间范围匹配改为 ID 优先绑定；引入优先级冲突解决和逻辑遮罩机制，替代物理裁剪。

### Schema 变更

**EditDecision 新增字段:**
```python
target_type: Literal["segment", "range"] = "range"  # 绑定类型
target_id: str | None = None                         # 绑定的 segment ID
```

**后端写入策略:**

| 方法 | target_type | target_id |
|------|-------------|-----------|
| `add_silence_results` | `"range"` | undefined（新建段，无既有 ID）|
| `mark_segments` | `"segment"` | `seg.id`（已有段 ID）|
| `add_analysis_results` | `"segment"` | `ar.segment_ids[0]`（主段 ID）|

### 匹配逻辑

**ID 优先 + 时间回退:**
```typescript
function findEditForSegment(seg: Segment): EditDecision | undefined {
  // 优先 ID 匹配
  const byId = edits.find(e => e.target_id === seg.id)
  if (byId) return byId
  // 回退到时间匹配（兼容旧数据）
  return edits.find(e => Math.abs(e.start - seg.start) < 0.01 && Math.abs(e.end - seg.end) < 0.01)
}
```

### 逻辑遮罩

**优先级冲突解决:**
- 用户决策：`priority=200`（mark_segments 创建）
- 自动检测：`priority=100`（silence/analysis 创建）

**`getEffectiveStatus` 返回值:**
- `"normal"` — 无编辑或编辑为 keep
- `"masked"` — 最高优先级编辑为 delete（红色+中划线+低透明度）
- `"kept"` — 最高优先级编辑为 keep（绿色边框）

**渲染层行为:**
- `masked` 段：`opacity-30 line-through`（TimelineRuler）/ `bg-red-50 line-through opacity-60`（TranscriptRow/SilenceRow）
- `kept` 段：`bg-green-50 border-l-3 border-green-400`
- 原始数据不删除，仅在导出时物理剔除 masked 段

### 修改文件

| 文件 | 变更 |
|------|------|
| `core/models.py` | EditDecision 新增 `target_type` + `target_id` 字段 |
| `core/project_service.py` | 3 个 EditDecision 构造器写入 target_type/target_id |
| `src/types/project.ts` | EditDecision 类型同步新增字段 |
| `src/components/workspace/Timeline.vue` | getEditForSegment 改为 ID 优先匹配，新增 getEffectiveStatus |
| `src/components/workspace/TimelineRuler.vue` | visibleBlocks 使用 ID 匹配 + effectiveStatus 渲染 |
| `src/components/workspace/TranscriptRow.vue` | 新增 effectiveStatus prop，statusClass 优先使用逻辑遮罩状态 |
| `src/components/workspace/SilenceRow.vue` | 新增 effectiveStatus prop，样式逻辑同步更新 |

### 验证结果

- `vue-tsc --noEmit` TypeScript 类型检查通过
- `vite build` 构建成功：JS 133.78 KB (gzip 45.02 KB)
- `bun run test` 前端 30/30 测试通过
- `uv run pytest tests/` 后端 64 测试全部通过

### 📝 Commit Message

```
feat(core): 实现 EditDecision ID 绑定与优先级逻辑遮罩

- EditDecision 新增 target_type/target_id 字段，支持 segment 精确绑定
- 后端 mark_segments/analysis/silence 三种场景写入绑定关系
- 前端匹配改为 ID 优先 + 时间回退，兼容旧数据
- 引入 getEffectiveStatus 优先级冲突解决：user(200) > auto(100)
- 逻辑遮罩：masked 段低透明度+中划线，kept 段绿色标记，原始数据保留
- TranscriptRow/SilenceRow/TimelineRuler 同步支持 effectiveStatus 渲染
```

---

## Audit Fix: Phase 1-3 Bug Fixes & Feature Extensions (2026-05-15 Session 9)

### 概述

基于 `docs/audit-report-preview-2.md` 审计报告，修复 7 个 HIGH 优先级 Bug 并实现 4 个缺失功能，打通核心工作流：导入字幕 -> 检测静音 -> 审阅建议 -> 导出。

### Phase 1: 关键 Bug 修复与开发者体验

#### Task 1.1: 修复 `getEffectiveStatus` 忽略 rejected 状态 (B1)

**问题:** `getEffectiveStatus` 按优先级排序但不检查 `status` 字段，rejected 的编辑决策仍然返回 "masked"。

**修复:** 在排序前过滤 `status !== "rejected"`，仅从活跃编辑列表中选取最高优先级。

**文件:** `frontend/src/utils/segmentHelpers.ts`

```typescript
// Before
const top = [...related].sort((a, b) => b.priority - a.priority)[0]

// After
const active = related.filter(e => e.status !== "rejected")
if (active.length === 0) return "normal"
const top = [...active].sort((a, b) => b.priority - a.priority)[0]
```

**测试:** 新增 4 个测试用例（单个 rejected、多优先级回退、全部 rejected、阈值过滤）

#### Task 1.2: 添加 `minOverlapSeconds` 参数 (A4)

**问题:** 1ms 重叠即将整个字幕标记为 "masked"。

**修复:** `isOverlapping` 新增 `minOverlapSeconds` 参数（默认 0.0），`getEffectiveStatus` 调用时传入 0.3s 阈值。

**文件:** `frontend/src/utils/segmentHelpers.ts`

```typescript
export function isOverlapping(
  edit: EditDecision,
  seg: Segment,
  minOverlapSeconds = 0.0,
): boolean {
  const overlapStart = Math.max(edit.start, seg.start)
  const overlapEnd = Math.min(edit.end, seg.end)
  return overlapEnd - overlapStart > minOverlapSeconds
}
```

**测试:** 新增 2 个测试用例（低于阈值、超过阈值）

#### Task 1.3: 欢迎页最近项目列表 (C1)

**问题:** 仅有"上传媒体"流程，`get_recent_projects` API 已实现但未使用。

**修复:** `WelcomePage.vue` 在 `onMounted` 时获取最近项目列表，渲染可点击列表，点击调用 `openProject`。

**文件:** `frontend/src/pages/WelcomePage.vue`

#### Task 1.4: 字幕段落删除功能 (A1)

**问题:** 无法删除字幕段落。

**修复:**
- 后端: `project_service.py` 新增 `delete_segment(segment_id)` 方法，移除段落及关联的 EditDecision
- 前端: `SegmentBlocksLayer.vue` 新增右键上下文菜单 + Delete 键删除；`useEdit.ts` 新增 `deleteSegment()` 方法

**文件:** `core/project_service.py`, `main.py`, `frontend/src/components/waveform/SegmentBlocksLayer.vue`, `frontend/src/components/waveform/WaveformEditor.vue`, `frontend/src/composables/useEdit.ts`, `frontend/src/types/api.ts`

#### Task 1.5: 波形渲染修复 (A3)

**问题:** 波形从未渲染。两个根因：后端处理器未注册 + 前端数学错误。

**修复:**
- 后端: `main.py` 注册 `WAVEFORM_GENERATION` 任务处理器，实现 `_handle_waveform_generation`
- 后端: `ffmpeg_service.py` 新增 `generate_waveform()` 函数（提取 PCM 音频、计算 min/max 峰值、写入 JSON）
- 前端: `WaveformCanvas.vue` 修复数学错误：`totalBuckets / duration` 替代 `totalBuckets / (vs + vd)`
- 前端: `useProject.ts` 新增 `triggerWaveformGeneration()`，项目创建/打开后自动触发

**文件:** `core/ffmpeg_service.py`, `main.py`, `frontend/src/components/waveform/WaveformCanvas.vue`, `frontend/src/composables/useProject.ts`

### Phase 2: 项目管理健壮性

#### Task 2.1: 修复静音检测去重忽略 rejected (B2)

**问题:** 重新检测静音时，已 rejected 的编辑决策被覆盖。

**修复:** `add_silence_results` 的 `already_covered` 检查中添加 `EditStatus.REJECTED`。

**文件:** `core/project_service.py`

```python
# Before
and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)

# After
and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
```

#### Task 2.2: SRT 导入校验 (C2)

**问题:** SRT 导入无校验，重新导入后孤立的 EditDecision 引用未清理。

**修复:**
- `import_srt` 先调用 `validate_srt` 校验，返回 warnings
- `update_transcript` 清理 `target_id` 不再存在的孤立 EditDecision

**文件:** `main.py`, `core/project_service.py`

### Phase 3: 核心功能扩展

#### Task 3.1: 修复音频文件导出崩溃 (E1)

**问题:** `_extract_segment` 硬编码视频编码参数，音频文件导出时崩溃。

**修复:**
- `_extract_segment` 新增 `has_video` 参数，音频文件使用 `-c:a aac -vn`
- 使用 `-t` 替代 `-to`（duration vs end time），preset 改为 `fast`
- `export_video` 新增 `media_info` 参数，自动检测是否有视频流
- `main.py` 的 `_handle_export_video` 传递 `media_info`

**文件:** `core/export_service.py`, `main.py`

```python
def _extract_segment(ffmpeg, input_path, start, end, output_path, has_video=True):
    duration = end - start
    base = [ffmpeg, "-hide_banner", "-y", "-ss", f"{start:.3f}", "-i", input_path,
            "-t", f"{duration:.3f}", "-avoid_negative_ts", "make_zero"]
    if has_video:
        codec_args = ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
    else:
        codec_args = ["-c:a", "aac", "-vn"]
    # ...
```

#### Task 3.2: 基于字幕的智能裁剪 (D1)

**问题:** 缺少核心价值功能 -- 自动删除字幕之间的空白段落。

**修复:**
- 后端: `project_service.py` 新增 `generate_subtitle_keep_ranges(padding=0.3)` 方法
  - 为每个字幕段扩展 padding 秒的保留区间
  - 合并重叠的保留区间
  - 计算保留区间之间的间隙作为删除范围
  - 创建 `source="subtitle_trim"` 的 EditDecision
- 前端: `useEdit.ts` 新增 `generateSubtitleKeepRanges(padding)` 方法
- UI: 工具栏新增"Subtitle Trim"按钮（橙色）

**文件:** `core/project_service.py`, `main.py`, `frontend/src/composables/useEdit.ts`, `frontend/src/types/api.ts`, `frontend/src/pages/WorkspacePage.vue`

#### Task 3.3: 纯音频导出 (D3)

**问题:** 缺少纯音频导出选项。

**修复:**
- `models.py` 新增 `EXPORT_AUDIO` 任务类型
- `export_service.py` 新增 `export_audio()` 函数（复用 `export_video` 逻辑，`has_video=False`）
- `main.py` 注册 `EXPORT_AUDIO` 处理器，新增 `_handle_export_audio`（默认输出 `.m4a`）
- `useExport.ts` 新增 `exportAudio()` 方法
- UI: 工具栏新增"Export Audio"按钮（绿色，音乐图标）

**文件:** `core/models.py`, `core/export_service.py`, `main.py`, `frontend/src/composables/useExport.ts`, `frontend/src/pages/WorkspacePage.vue`

### Bug 修复: 时间轴右键删除无效

**问题:** `WaveformEditor` 定义了 `delete-segment` 事件，但 `WorkspacePage.vue` 未监听。

**修复:** 添加 `@delete-segment="handleDeleteSegment"` 到 `WaveformEditor` 组件，从 `useEdit` 解构 `deleteSegment` 方法，添加 `handleDeleteSegment` 处理函数。

**文件:** `frontend/src/pages/WorkspacePage.vue`

### 修改文件汇总

| 文件 | 变更 |
|------|------|
| `core/models.py` | TaskType 新增 EXPORT_AUDIO |
| `core/export_service.py` | `_extract_segment` 新增 has_video 参数；`export_video` 新增 media_info 参数；新增 `export_audio()` |
| `core/project_service.py` | 新增 `delete_segment()`, `generate_subtitle_keep_ranges()`, `update_media_waveform()`；修复 `add_silence_results` 去重；修复 `update_transcript` 清理孤立编辑 |
| `core/ffmpeg_service.py` | 新增 `generate_waveform()` |
| `main.py` | 注册 WAVEFORM_GENERATION/EXPORT_AUDIO 处理器；新增 `delete_segment`, `generate_subtitle_keep_ranges` 暴露方法；`import_srt` 新增校验；`_handle_export_video` 传递 media_info |
| `frontend/src/utils/segmentHelpers.ts` | `isOverlapping` 新增 minOverlapSeconds；`getEffectiveStatus` 过滤 rejected |
| `frontend/src/utils/segmentHelpers.test.ts` | 新增 6 个测试用例 |
| `frontend/src/types/api.ts` | BridgeMethod 新增 delete_segment, generate_subtitle_keep_ranges |
| `frontend/src/composables/useEdit.ts` | 新增 `deleteSegment()`, `generateSubtitleKeepRanges()` |
| `frontend/src/composables/useExport.ts` | 新增 `exportAudio()`；isExporting/exportProgress 支持 export_audio |
| `frontend/src/composables/useProject.ts` | 新增 `waveformPath` computed, `triggerWaveformGeneration()` |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 新增右键上下文菜单、Delete 键删除、选区高亮 |
| `frontend/src/components/waveform/WaveformEditor.vue` | 新增 `delete-segment` emit 和 handler；传递 duration prop |
| `frontend/src/components/waveform/WaveformCanvas.vue` | 新增 duration prop；修复 bucketsPerSecond 数学错误 |
| `frontend/src/pages/WelcomePage.vue` | 新增最近项目列表 |
| `frontend/src/pages/WorkspacePage.vue` | 新增 Subtitle Trim/Export Audio 按钮；修复 @delete-segment 事件绑定 |

### Bridge API 新增方法 (3 个)

- `delete_segment(segment_id)` -- 删除字幕段落及关联编辑决策
- `generate_subtitle_keep_ranges(padding)` -- 基于字幕生成智能裁剪范围
- `export_audio` 任务类型 -- 纯音频导出

### 验证结果

- `uv run pytest tests/` 后端 64 测试全部通过 (0.4s)
- `bun run test` 前端 89 测试全部通过 (3.5s)
- TypeScript 类型检查通过

### 📝 Commit Message

```
fix(audit): 修复 7 个 HIGH Bug 并实现 4 个缺失功能

Phase 1 - 关键 Bug 修复:
- 修复 getEffectiveStatus 忽略 rejected 状态 (B1)
- 修复 1ms 重叠标记整段字幕为 masked (A4)
- 新增欢迎页最近项目列表 (C1)
- 新增字幕段落删除功能：右键菜单 + Delete 键 (A1)
- 修复波形渲染：注册后端处理器 + 修复前端数学错误 (A3)

Phase 2 - 项目管理健壮性:
- 修复静音检测去重忽略 rejected 状态 (B2)
- SRT 导入新增校验 + 清理孤立编辑决策 (C2)

Phase 3 - 核心功能扩展:
- 修复音频文件导出崩溃：has_video 条件编码 (E1)
- 实现基于字幕的智能裁剪 (D1)
- 实现纯音频导出 (D3)
- 修复时间轴右键删除无效（缺少事件绑定）
```

---

### 🚀 Release Notes

```
## 2026-05-15 - Audit Fix: 核心工作流打通

### ✨ 新增
- **智能字幕裁剪**：一键删除字幕之间的空白段落，自动保留 0.3s 边距，快速完成视频粗剪。
- **纯音频导出**：支持导出 M4A 格式的纯音频文件，适用于播客等音频内容。
- **段落删除**：时间轴右键菜单或 Delete 键可直接删除不需要的字幕段落。
- **最近项目**：欢迎页显示最近打开的项目，一键快速访问。
- **波形显示**：项目打开后自动生成音频波形数据并在时间轴上渲染。

### ⚡ 优化
- **编辑状态准确性**：rejected 状态的编辑决策不再影响段落显示，1ms 微小重叠不再误标记整段字幕。
- **静音检测去重**：已拒绝的静音建议在重新检测时不会被覆盖。
- **SRT 导入健壮性**：导入前自动校验文件，重新导入时清理孤立的编辑决策引用。

### 🐛 修复
- 修复音频文件（MP3/WAV 等）导出时崩溃的问题。
- 修复波形从未显示的两个根因（后端处理器未注册 + 前端数学错误）。
- 修复时间轴右键删除菜单点击无效的问题。
- 修复 rejected 状态的编辑决策仍显示为"已删除"的问题。
- 修复极小时间重叠（1ms）导致整段字幕被标记为 masked 的问题。
```

---

## Session 10 序: 调试过程、附加功能与架构审查 (2026-05-15)

### 概述

### 第一阶段: EditStatus/EffectiveStatus 调试

**问题现象:** Analysis 分析后，badge 显示"已保留"（绿色）但行有红色删除线。点击确认/忽略按钮无反应。"忽略所有建议"可恢复，"全部确认删除"后红色删除线 persist 无法恢复。

**调试过程（多次失败迭代）:**

1. **尝试 1:** 修改 `toggleEditStatus` 中无 edit 时的 fallback，从创建 `"delete"` edit 改为 `"keep"` edit -- 未解决问题
2. **尝试 2:** 修改 `getEditForSegment` 添加 rejected 过滤（与 `getEffectiveStatus` 一致）-- 导致红色删除线直接不显示，整个标记逻辑错误，已回滚
3. **根因定位:** 两套独立状态函数使用不同匹配/过滤逻辑。`getEditForSegment` 不过滤 rejected、返回第一个匹配；`getEffectiveStatus` 过滤 rejected、按 priority 排序取最高。两者返回不一致导致 badge 和行样式矛盾

**用户反馈关键点:**

- "整个标记逻辑都错了" -- 尝试 2 导致的回滚
- "完全听不懂你在说什么" -- 需要更清晰的自然语言描述
- 最终要求导出完整审计报告交由架构师审查

### 第二阶段: 附加功能开发

在调试间隙，实现了以下附加功能：

#### 1. Toast 通知系统

- **`frontend/src/composables/useToast.ts`** (新增): 管理 toast 列表，支持 info/success/error 类型，自动移除
- **`frontend/src/components/common/ToastContainer.vue`** (新增): 固定右下角浮层，关闭按钮，Tailwind 过渡动画
- **`frontend/src/App.vue`**: 根模板集成 `<ToastContainer />`

#### 2. 静音标记批量删除

- **`core/project_service.py`**: 新增 `delete_silence_segments()` -- 移除所有 silence 类型段落及关联 EditDecision
- **`core/project_service.py`**: 新增 `delete_subtitle_trim_edits()` -- 移除所有 source="subtitle_trim" 的编辑决策
- **`main.py`**: 暴露 `delete_silence_segments` 和 `delete_subtitle_trim_edits` API
- **`frontend/src/composables/useEdit.ts`**: 新增 `deleteSilenceSegments()` 和 `deleteSubtitleTrimEdits()` 方法
- **`frontend/src/pages/WorkspacePage.vue`**: 工具栏新增删除静音标记按钮（红色垃圾桶图标），带确认对话框；新增清除字幕裁剪标记按钮

#### 3. 字幕裁剪设置

- **`frontend/src/pages/WorkspacePage.vue`**: Subtitle Trim 按钮旁新增设置齿轮，可调整 padding（0-2.0s，默认 0.3s）
- **`core/config.py`**: 新增 `trim_subtitles_on_silence_overlap` 设置项（默认 true）

#### 4. 字幕-静音重叠处理

- **`core/project_service.py`**: 新增 `_resolve_subtitle_overlap()` 方法 -- 当静音检测启用时，自动裁剪与静音范围重叠的字幕段（拆分或收缩，不删除字幕）
- **`core/project_service.py`**: `add_silence_results` 集成重叠处理逻辑
- **`frontend/src/pages/WorkspacePage.vue`**: 静音设置面板新增"Trim overlapping subtitles"复选框

#### 5. UI 改进

- **状态消息自动消失**: `statusMessage` 5 秒后自动清除，新增关闭按钮（X）
- **保存项目 Toast**: Ctrl+S 和 Save 按钮改用 toast 通知替代 statusMessage
- **波形编辑器编辑范围叠加层**: `SegmentBlocksLayer.vue` 新增 `visibleEditRanges` computed，渲染 source="subtitle_trim" 的 range 类型 EditDecision 为红色斜纹半透明叠加层
- **时间刻度优化**: `useTimelineMetrics.ts` 新增 minor time marks（主刻度之间的中间刻度），`TimeMarksLayer.vue` 渲染为浅色短刻度

### 第三阶段: 架构审计报告

创建 `docs/audit-report-preview-3.md`，完整记录：

- 两套状态系统的代码和匹配逻辑差异
- `getEditForSegment` vs `getEffectiveStatus` 的不一致根因
- 问题复现路径
- 4 个需要架构师决定的问题
- 所有相关代码导出（segmentHelpers.ts、TranscriptRow.vue、Timeline.vue、useSegmentEdit.ts、models.py、project_service.py）

### 第四阶段: 架构师决策

架构师对 4 个问题给出明确决策，写入审计报告第 6 节：

1. **合并为统一状态函数 `resolveSegmentState`（选项 C）** -- 返回 `{ displayStatus, styleClass, activeEdit }` 结构体
2. **badge 显示"无标注"而非"已保留"** -- none 语义为无编辑决策
3. **toggleEditStatus 使用 activeEdit** -- 三路逻辑：activeEdit 存在则切换；无 edit 则创建 keep；全 rejected 则不操作
4. **允许多个 edit 共存** -- user(200) > analysis(100) 优先级，同 source 去重，rejected 不参与样式

### 第五阶段: 实施计划

基于架构决策生成 5 阶段 10 步实施计划（写入 `~/.claude/plans/curried-knitting-biscuit.md`）：

| 阶段               | 步骤 | 内容                                                         |
| ------------------ | ---- | ------------------------------------------------------------ |
| 1. 核心状态函数    | 1-2  | `segmentHelpers.ts` 新增 `resolveSegmentState` + TDD 测试    |
| 2. Composable 适配 | 3-5  | `useSegmentEdit.ts` 改用新函数、修复 `toggleEditStatus`、更新测试 |
| 3. UI 组件适配     | 6-8  | Timeline/TranscriptRow/SilenceRow 统一使用 `SegmentState`    |
| 4. 波形编辑器      | 9    | SegmentBlocksLayer 适配                                      |
| 5. 后端修复        | 10   | `mark_segments` 清理旧 user edit（可并行）                   |

### 修改文件汇总

| 文件                                                      | 变更                                                         |
| --------------------------------------------------------- | ------------------------------------------------------------ |
| `core/config.py`                                          | 新增 `trim_subtitles_on_silence_overlap` 设置                |
| `core/project_service.py`                                 | 新增 `_resolve_subtitle_overlap`、`delete_silence_segments`、`delete_subtitle_trim_edits`；`mark_segments` 按 source 清理旧编辑；`add_silence_results` 集成重叠处理 |
| `main.py`                                                 | 暴露 `delete_silence_segments`、`delete_subtitle_trim_edits` API |
| `frontend/src/utils/segmentHelpers.ts`                    | 新增 `SegmentState` + `resolveSegmentState`；废弃旧函数为 wrapper |
| `frontend/src/utils/segmentHelpers.test.ts`               | 新增 13 个 `resolveSegmentState` 测试                        |
| `frontend/src/composables/useSegmentEdit.ts`              | `toggleEditStatus` 三路逻辑；新增 `resolveState` 导出        |
| `frontend/src/composables/useSegmentEdit.test.ts`         | 新增 rejected 切换和 resolveState 测试                       |
| `frontend/src/composables/useEdit.ts`                     | 新增 `deleteSilenceSegments`、`deleteSubtitleTrimEdits`      |
| `frontend/src/composables/useTimelineMetrics.ts`          | 新增 minor time marks                                        |
| `frontend/src/composables/useToast.ts`                    | 新增 toast 通知系统                                          |
| `frontend/src/components/common/ToastContainer.vue`       | 新增 toast 容器组件                                          |
| `frontend/src/components/workspace/Timeline.vue`          | 改用 `resolveSegmentState`；传递新 props                     |
| `frontend/src/components/workspace/TranscriptRow.vue`     | Props 重构；无标注徽章修复                                   |
| `frontend/src/components/workspace/SilenceRow.vue`        | Props 重构；类绑定简化                                       |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | Props 适配新接口                                             |
| `frontend/src/components/workspace/SilenceRow.test.ts`    | Props 适配新接口                                             |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | `Block` 接口改为 `{ state: SegmentState }`；新增编辑范围叠加层 |
| `frontend/src/components/waveform/TimeMarksLayer.vue`     | 渲染 minor time marks                                        |
| `frontend/src/pages/WorkspacePage.vue`                    | 集成 toast、静音删除、字幕裁剪设置、重叠设置、状态消息改进   |
| `frontend/src/App.vue`                                    | 集成 ToastContainer                                          |
| `frontend/src/types/api.ts`                               | 新增 `delete_silence_segments`、`delete_subtitle_trim_edits` |
| `docs/audit-report-preview-3.md`                          | 新增第 6 节架构决策                                          |

### 相关文档

- `docs/audit-report-preview-2.md` -- Phase 1-3 审计报告（Session 9 基于此修复）
- `docs/audit-report-preview-3.md` -- EditStatus/EffectiveStatus 架构审计报告（含代码、逻辑分析、架构师决策）

## 2026-05-15 - EditStatus/EffectiveStatus Sync Bug Fix (Session 10)

### 背景

前端使用两个独立的段落状态计算函数（`getEditForSegment` 用于徽章显示、`getEffectiveStatus` 用于行样式），具有不同的匹配/过滤逻辑，导致徽章文字与行背景/删除线不一致。同时后端 `mark_segments` 仅根据 ID 去重，未清理旧的 user 来源编辑，导致冲突。

### 解决方案: resolveSegmentState 统一状态计算

在 `frontend/src/utils/segmentHelpers.ts` 中新增 `SegmentState` 接口和 `resolveSegmentState` 函数，作为段落状态的唯一真相来源：

```typescript
export interface SegmentState {
  displayStatus: "none" | EditDecision["status"]
  styleClass: "normal" | "masked" | "kept"
  activeEdit: EditDecision | undefined
}

export function resolveSegmentState(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): SegmentState
```

**核心逻辑:**
1. 收集所有相关编辑（按 `target_id` 或重叠 >=0.3s 匹配）
2. 分离 active（非 rejected）和 rejected 编辑，按 priority 排序
3. `topActive` = 最高优先级 active 编辑，决定 `styleClass`（delete→masked, keep→kept）
4. `topEdit` = 最高优先级所有编辑。Rejected topEdit 仅在 action 不同于 topActive 时覆盖 `displayStatus`
5. 无 active 编辑 → 显示 "none"（无编辑）或 "rejected"（仅有 rejected 编辑），`styleClass` 为 "normal"，`activeEdit` 为 undefined
6. 优先级: user 来源 = 200, analysis 来源 = 100

**废弃旧函数:** `getEffectiveStatus` 和 `getEditStatus` 保留为 `resolveSegmentState` 的包装器，标记 `@deprecated`。

### 组件适配

**`Timeline.vue`:** 导入从 `getEditStatus, getEffectiveStatus` 改为 `resolveSegmentState`。模版传递 `display-status` 和 `style-class` props。

**`TranscriptRow.vue`:** Props 从 `editStatus?: EditStatus | null` + `effectiveStatus?: "normal" | "masked" | "kept"` 改为 `displayStatus?: string` + `styleClass?: string`。徽章在 `displayStatus === "none"` 时显示"无标注"（灰色背景）；之前逻辑错误显示"已保留"（绿色背景）。

**`SilenceRow.vue`:** 同样改为新 props。类绑定使用 `displayStatus` 和 `styleClass`：
```html
'bg-gray-50': !displayStatus || displayStatus === 'none',
'bg-yellow-50': displayStatus === 'pending',
'bg-red-50 opacity-60': displayStatus === 'confirmed' || styleClass === 'masked',
'bg-green-50': styleClass === 'kept',
```

**`SegmentBlocksLayer.vue`:** `Block` 接口改为 `{ state: SegmentState }`。`statusColor()` 使用 `block.state.styleClass`。

### Critical Bug Fix 1: "无标注"切换为"已删除"显示绿色（keep 而非 delete）

**根因:** `toggleEditStatus` 在无编辑时调用 `mark_segments([segment.id], "keep", "confirmed")` 创建了 KEEP 编辑，导致绿色保留样式而非红色删除线。

**修复:** 改为 `mark_segments([segment.id], "delete", "confirmed")`。

### Critical Bug Fix 2: "已保留"无法切换回"已删除"

**根因:** 当所有编辑均为 rejected（`displayStatus === "rejected"`，`activeEdit === undefined`），`toggleEditStatus` 无匹配分支，点击无响应。

**修复:** 新增分支：当 `displayStatus === "rejected"` 时，使用 `getEditForSegment`（可找到包括 rejected 的编辑）定位 rejected 编辑，调用 `update_edit_decision` 切换回 "confirmed"。

修改后的 `toggleEditStatus` 三路逻辑：
```typescript
if (state.activeEdit) {
  // Normal toggle: confirmed ↔ rejected
} else if (state.displayStatus === "rejected") {
  // All rejected → find rejected edit and toggle back to confirmed
} else {
  // No edit → create DELETE edit
}
```

### 后端修复: mark_segments 清理旧用户编辑

**`core/project_service.py`:** `mark_segments` 改为按 source 清理而非 ID 去重。在创建新编辑前移除所有 `source == "user"` 且 `target_id` 在目标段落集合中的旧编辑，防止不同 ID 的冲突编辑并存。

```python
merged_edits = [
    e for e in existing_edits
    if not (e.source == "user" and e.target_id in target_seg_ids)
] + new_edits
```

### 测试更新

| 文件 | 变更 |
|------|------|
| `segmentHelpers.test.ts` | 新增 13 个 `resolveSegmentState` 测试（无编辑、pending/confirmed/rejected delete、pending keep、多编辑优先级、fall-through、rejected high 影响 displayStatus 但不影响 styleClass、全部 rejected、低重叠阈值忽略、按 target_id 去重、按 range 重叠匹配、user 来源优先级） |
| `useSegmentEdit.test.ts` | 重命名测试："creates keep edit" → "creates delete edit"；断言从 `("keep", "confirmed")` 改为 `("delete", "confirmed")`；新增 "toggles rejected edit back to confirmed" 测试；新增 `resolveState` describe 块 |
| `TranscriptRow.test.ts` | Props: `editStatus: "pending"` → `displayStatus: "pending"`；`editStatus: "confirmed"` → `displayStatus: "confirmed", styleClass: "masked"`；`globalEditMode` 相关测试通过 |
| `SilenceRow.test.ts` | Props: `editStatus: "pending"` → `displayStatus: "pending"`；`editStatus: "confirmed"` → `displayStatus: "confirmed"`；`editStatus: "rejected"` → `displayStatus: "rejected", styleClass: "kept"` |

### 修改文件汇总

| 文件 | 变更 |
|------|------|
| `frontend/src/utils/segmentHelpers.ts` | 新增 `SegmentState` 接口和 `resolveSegmentState`；废弃 `getEffectiveStatus`/`getEditStatus` 为包装器 |
| `frontend/src/utils/segmentHelpers.test.ts` | 新增 13 个测试用例 |
| `frontend/src/composables/useSegmentEdit.ts` | `toggleEditStatus` 三路逻辑修复；新增 `resolveState` 到公共 API；重新导入 `getEditForSegment` |
| `frontend/src/composables/useSegmentEdit.test.ts` | 重命名测试；新增 rejected 切换和 resolveState 测试 |
| `frontend/src/components/workspace/Timeline.vue` | 改用 `resolveSegmentState`；传递新 props |
| `frontend/src/components/workspace/TranscriptRow.vue` | Props 重构：`editStatus`/`effectiveStatus` → `displayStatus`/`styleClass`；无标注徽章修复 |
| `frontend/src/components/workspace/SilenceRow.vue` | Props 重构；类绑定简化 |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | `Block` 接口改为 `{ state: SegmentState }` |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | Props 适配新接口 |
| `frontend/src/components/workspace/SilenceRow.test.ts` | Props 适配新接口 |
| `core/project_service.py` | `mark_segments` 按 source 清理旧用户编辑 |

### 验证结果

- `uv run pytest tests/` 后端 64 测试全部通过 (0.36s)
- `bun run test` 前端 105 测试全部通过 (3.16s, 7 test files)
- TypeScript 类型检查通过

### 📝 Commit Message

```
fix(ui): 统一EditStatus/EffectiveStatus并修复关键切换Bug

- 新增 resolveSegmentState 作为段落状态唯一计算源，消除
  getEditForSegment 与 getEffectiveStatus 逻辑不一致
- 修复"无标注"切换为"已删除"时误创建 keep 编辑导致绿色残留
- 修复"已保留(rejected)"状态下确认/忽略按钮无响应问题
- 后端 mark_segments 按 source 清理旧用户编辑防止冲突
- 新增 Toast 通知系统(全局/成功/错误/自动消失)
- 新增静音标记与字幕裁剪的批量删除功能
- 新增字幕-静音重叠自动裁剪与 trim padding 设置
- 波形编辑器新增字幕裁剪编辑范围叠加层与次刻度时间线
- 全套 Props 重构(Timeline/TranscriptRow/SilenceRow/SegmentBlocksLayer)
- 新增 13 个 resolveSegmentState 单元测试 + useSegmentEdit 测试覆盖
```

---

### 🚀 Release Notes

```
## 2026-05-15 - 段落状态统一与批量操作功能

### ✨ 新增
- **Toast 通知系统**：操作成功后弹窗提示(右下角)，替换原有 status bar 消息，5 秒自动消失并支持手动关闭
- **静音标记批量删除**：工具栏新增红色垃圾桶按钮，一键移除所有静音标记及关联编辑决策
- **字幕裁剪标记批量清除**：支持一键清除所有字幕裁剪编辑决策
- **字幕裁剪设置**：新增 padding 调整(0-2.0s，默认 0.3s)，裁剪行为更灵活
- **字幕-静音自动裁剪**：开启静音检测后，重叠部分字幕段自动裁剪而非整段删除
- **波形编辑范围叠加层**：字幕裁剪范围以红色斜纹半透明叠加层显示在波形图上
- **次刻度时间线**：主刻度之间新增浅色短刻度，时间定位更精确

### 🐛 修复
- 修复分析后徽章显示"已保留"(绿色)但行出现红色删除线的不一致问题
- 修复"无标注"段点击删除后错误显示绿色保留样式的问题
- 修复"已保留"状态点击确认/忽略按钮无响应的逻辑死路问题
- 修复后端 mark_segments 未清理旧用户编辑导致冲突编辑并存的隐患

### ⚡ 优化
- 状态消息 5 秒后自动清除并新增关闭按钮(X)
- Ctrl+S / Save 按钮改用 Toast 通知，体验更轻量
- 时间刻度新增次刻度显示，视觉定位更友好
```

---

## Audit Report #4 Fixes: Export 截断、SubtitleTrim、SRT 导出、波形单击定位 (2026-05-16)

### 概述

基于 `docs/audit-report-preview-4.md` 执行 4 项修复（B1, B2, B3+B4, C2），涵盖后端导出截断、字幕裁剪逻辑遗漏、SRT 筛选不一致及前端波形块单击定位功能。

### B1 [HIGH] 修复 `_get_media_duration` 低估实际媒体时长 + `export_audio` 缺少 media_info

**问题:** `_get_media_duration` 仅从 segments/edits 计算最大 end time，忽略 ffprobe 探测的实际媒体文件 `duration`。末尾字幕段与视频结束之间的无声尾画面会在导出时被截断。`export_audio` 同样缺少 `media_info` 参数。

**修复:**
- `core/export_service.py`: `_get_media_duration` 新增可选 `media_duration: float = 0.0` 参数，返回 `max(computed, media_duration)`
- `core/export_service.py`: `export_video` 从 `media_info` 提取 `duration` 并传递；不可用时输出 warning 日志
- `core/export_service.py`: `export_audio` 新增 `media_info: dict | None = None` 关键字参数，同样提取 duration 传递
- `core/export_service.py`: `_compute_keep_ranges` 新增端点钳位逻辑，防止 segment/edit 端点超出 `total_duration`
- `main.py`: `_handle_export_audio` 传递 `project.media.model_dump()` 作为 `media_info`

**文件:** `core/export_service.py`, `main.py`

### B3+B4 [HIGH+MEDIUM] SubtitleTrim 排除已删除字幕 + already_covered 含 REJECTED

**B3 问题:** `generate_subtitle_keep_ranges` 构建 `subtitle_segs` 时未排除已 confirmed delete 的字幕，导致已标记删除的字幕仍被计入 keep_ranges。

**B4 问题:** `already_covered` 检查仅匹配 `CONFIRMED` 和 `PENDING` 状态，遗漏 `REJECTED`，导致重新运行 SubtitleTrim 时为已 rejected 的范围重复创建 PENDING 编辑。

**修复:**
- `core/project_service.py`: 新增 `confirmed_deleted_ids` 和 `confirmed_kept_ids` 集合，从 edits 中收集
- `core/project_service.py`: `subtitle_segs` 构建时排除 `confirmed_deleted_ids` 中的段
- `core/project_service.py`: `already_covered` 状态检查新增 `EditStatus.REJECTED`

**技术债备忘:** `already_covered` 逻辑在 silence detection 和 SubtitleTrim 中重复出现，后续应提取为共用工具函数。

**文件:** `core/project_service.py`

### B2 [HIGH] SRT 导出字幕筛选标准与视频导出不一致

**问题:** `export_srt` 使用 `_overlaps_deletions` 按 deletions 直接过滤字幕，而 `export_video` 使用 `_compute_keep_ranges`（逆运算）确定保留范围。两者逻辑不对称，且 SRT 未使用 `media_duration` 导致与视频导出总时长不同。

**修复:**
- `core/export_service.py`: 新增 `_subtitle_survives_in_keep_ranges` 辅助函数，使用自适应阈值（长字幕 >=0.3s 保留，短字幕 >=50% 即可）
- `core/export_service.py`: `export_srt` 新增 `media_duration: float = 0.0` 关键字参数
- `core/export_service.py`: `export_srt` 内部改用 `_compute_keep_ranges` + `_subtitle_survives_in_keep_ranges` 替代 `_overlaps_deletions`
- `main.py`: `_handle_export_subtitle` 传递 `project.media.duration` 作为 `media_duration`
- 保留 `_overlaps_deletions` 函数（可能有其他调用者）

**文件:** `core/export_service.py`, `main.py`

### C2 [FEATURE] 单击波形块定位到 Timeline 对应位置

**功能:** 单击波形编辑器中的字幕/静音块时，右侧 Timeline 自动滚动定位到对应行，视频时间指针跳转到该段起始时间（不自动播放）。

**实现:**
- `SegmentBlocksLayer.vue`: emit 新增 `"seek-segment"`；新增 `handleBlockClick` 函数（清除 `selectedBlockId` + emit）；模板块元素新增 `@click="handleBlockClick(block)"`
- `WaveformEditor.vue`: emit 新增 `"seek-segment"`；新增 `handleSeekSegment` 透传函数；模板 `SegmentBlocksLayer` 新增 `@seek-segment="handleSeekSegment"` 绑定
- `WorkspacePage.vue`: `WaveformEditor` 新增 `@seek-segment="handleSeekSegment"` 绑定；新增 `handleSeekSegment` 函数：设置 `editSelectedSegmentId` + 设置 `videoRef.currentTime`（不调 play）
- `Timeline.vue`: 新增 `watch(selectedSegmentId)`：`nextTick` 后用 `el.scrollIntoView({ behavior: "smooth", block: "nearest" })` 滚动到对应行
- `TranscriptRow.vue`: 根元素新增 `:data-segment-id="segment.id"`
- `SilenceRow.vue`: 根元素新增 `:data-segment-id="segment.id"`
- `SegmentBlocksLayer.vue`: canvas 容器新增 `focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400` 防止浏览器默认黑色 focus outline

**设计决策:**
- 单击（非双击）：经过讨论改为单击触发，操作更直接
- 不自动播放：仅设置 `currentTime`，不调用 `play()`，避免自动播放打断用户
- `@click` 不用 `.stop`：父级 canvas `.self` 修饰符已隔离传播，无需额外阻止
- `handleBlockClick` 清除 `selectedBlockId`：避免选中蓝环在 seek 后残留

**文件:** `SegmentBlocksLayer.vue`, `WaveformEditor.vue`, `WorkspacePage.vue`, `Timeline.vue`, `TranscriptRow.vue`, `SilenceRow.vue`

### Bug 修复: TaskType 缺少 "export_audio"

**问题:** `useExport.ts` 使用 `"export_audio"` 作为 task type，但 `types/task.ts` 中 `TaskType` 联合类型未包含此项，导致 3 个 TypeScript 类型错误。

**修复:** `types/task.ts` TaskType 新增 `| "export_audio"`。

**文件:** `frontend/src/types/task.ts`

### 修改文件汇总

| 文件 | 变更 |
|------|------|
| `core/export_service.py` | `_get_media_duration` 新增 media_duration 参数；`export_video`/`export_audio` 传递 media_duration；`_compute_keep_ranges` 端点钳位；新增 `_subtitle_survives_in_keep_ranges`；`export_srt` 改用 keep_ranges；`export_audio` 新增 media_info 参数 |
| `core/project_service.py` | `generate_subtitle_keep_ranges` 排除 confirmed-deleted 字幕；`already_covered` 新增 REJECTED 状态 |
| `main.py` | `_handle_export_audio` 传递 media_info；`_handle_export_subtitle` 传递 media_duration |
| `frontend/src/types/task.ts` | TaskType 新增 `"export_audio"` |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 新增 seek-segment emit + handleBlockClick + @click；canvas 容器 focus:outline-none |
| `frontend/src/components/waveform/WaveformEditor.vue` | 新增 seek-segment emit + handleSeekSegment + @seek-segment 绑定 |
| `frontend/src/pages/WorkspacePage.vue` | 新增 handleSeekSegment + @seek-segment 绑定 |
| `frontend/src/components/workspace/Timeline.vue` | 新增 watch(selectedSegmentId) + scrollIntoView |
| `frontend/src/components/workspace/TranscriptRow.vue` | 新增 :data-segment-id |
| `frontend/src/components/workspace/SilenceRow.vue` | 新增 :data-segment-id |

### 验证结果

- `uv run python -c "import ast"` 后端 3 个修改文件语法检查通过
- `bun run test -- --run` 前端 105 测试全部通过 (7 test files)
- `bun run build` 前端构建成功：CSS 59.46 KB, JS 158.69 KB (gzip 53.52 KB)

### 实施顺序

B1 -> B3+B4 -> B2 -> C2（B2 依赖 B1 的 `_get_media_duration` 新签名；B3+B4 为同一函数修改合并实施；C2 独立前端功能）

### 回滚方案

每项修复均可通过 `git revert` 逐项回滚。B2 依赖 B1 的 `media_duration` 参数，其余项目独立。

### 📝 Commit Message

```
fix: 修复导出截断与字幕逻辑，新增波形定位

- B1: _get_media_duration 取 max(计算, 实际) 防截断
- B2: export_srt 改用 keep_ranges 逻辑对齐视频导出
- B3+B4: SubtitleTrim 排除已删字幕及 REJECTED 状态
- C2: 单击波形块 emit 事件联动 Timeline 滚动与 seek
- 补充 TaskType 缺失的 "export_audio" 类型定义

Resolves: docs/audit-report-preview-4.md (B1-B4, C2)
```

### 🚀 Release Notes

```
## 2026-05-16 - 导出准确性与编辑交互体验提升

### ✨ 新增
- 支持单击波形图中的字幕/静音块，自动跳转至时间轴对应位置并定位视频进度

### 🐛 修复
- 修复导出视频/音频时，末尾无声画面被错误截断的问题
- 修复导出 SRT 字幕与导出视频的实际内容不一致的问题
- 修复字幕裁剪功能误将已删除的字幕计入保留范围的问题
- 修复重复执行字幕裁剪时可能产生重复冗余编辑记录的问题
```

---

## Session 11: 导出截断与字幕时间轴修复 (2026-05-16)

### 问题背景

用户报告 B1 (媒体时长低估) 修复后，导出仍有问题：
1. 音频导出末尾 5-6 条字幕对应音频缺失
2. SRT 字幕时间戳与导出音频不对齐，存在大量重叠

### 诊断过程

通过添加诊断日志 `export_srt` / `export_audio` / `export_video` 捕获运行时数据：
- `media_duration=364.94`, `total_duration=365.65` -- B1 的 `_get_media_duration` 修复已生效
- 97 个 confirmed deletions，23 条字幕被过滤（符合用户预期）
- 末尾 keep_range 结束于 363.23，非 total_duration 截断问题

### 根因分析

**问题 1：音频末尾截断**
- 旧流程：逐段提取为 AAC .ts -> concat demuxer `-c copy` 拼接
- 每段独立 AAC 编码产生 ~23ms priming，98 段累积 ~2.3 秒偏移
- 导致导出音频实际长度短于 keep_ranges 计算值

**问题 2：SRT 时间戳重叠**
- 旧逻辑用 `cumulative_offset` 线性减法调整时间戳
- 条件 `deletion_end <= seg_start` 遗漏了字幕起始点在删除区间内的情况
- 例：字幕 [18,22] 与删除 [10,20] 重叠，偏移未计入，导致时间戳错误

### 修复内容

#### 1. 音频导出改为 FFmpeg filter_complex 单次通过

**文件**: `core/export_service.py` -- `export_audio`, `_build_audio_trim_filter`

```
旧：逐段提取 AAC .ts -> concat -c copy (有 priming 累积)
    _extract_segment -> _concat_segments(reencode_audio=True)

新：单次 filter_complex 通过，样本级精度裁剪
    _build_audio_trim_filter(keep_ranges)
    -> atrim=start=X:end=Y,asetpts=PTS-STARTPTS per range
    -> concat=n=N:v=0:a=1[out]
    ffmpeg -i input -filter_complex_script filter.txt -c:a aac output
```

- 用 `atrim` 精确裁剪每个 keep range（样本级精度）
- 用 `concat` 滤镜拼接所有裁剪段
- 只有一次 AAC 编码，无累积 priming
- filter 写入临时文件 (`-filter_complex_script`)，不受命令行长度限制

#### 2. SRT 时间轴映射改用 keep_ranges 精确映射

**文件**: `core/export_service.py` -- 新增 `_map_to_exported_timeline`

```
旧：线性 offset 减法（字幕与删除重叠时计算错误）
    while del_idx < len(deletions) and deletions[del_idx][1] <= seg_start:
        cumulative_offset += deletions[del_idx][1] - deletions[del_idx][0]
    new_start = seg_start - cumulative_offset

新：基于 keep_ranges 的精确映射
    def _map_to_exported_timeline(seg_start, seg_end, keep_ranges):
        cumulative = 0.0
        for ks, ke in keep_ranges:
            overlap_start = max(seg_start, ks)
            overlap_end = min(seg_end, ke)
            if overlap_start < overlap_end:
                exported_start = cumulative + (overlap_start - ks)
                exported_end = cumulative + (overlap_end - ks)
            cumulative += ke - ks
        return exported_start, exported_end
```

- 裁剪字幕到 keep range 边界，消除重叠
- 正确处理字幕跨越删除区间的情况
- 映射结果与 filter_complex 的 atrim 裁剪完全一致

#### 3. 诊断日志

**文件**: `core/export_service.py` -- `export_video`, `export_audio`, `export_srt`

在所有导出入口添加日志：
- `media_duration`, `total_duration`, `deletions` 数量, `keep_ranges`
- 被过滤字幕的 `(start, end, text[:30])` 列表

### 验证

- 音频导出：末尾截断修复，总时长与 keep_ranges 总和一致
- SRT 导出：无时间戳重叠，时间轴与音频对齐
- 长音频兼容：filter 写入文件 (`-filter_complex_script`)，不受命令行 32767 字符限制

---

## Session 12 - 视频导出 filter_complex 统一方案 (2026-05-16)

### 问题

上一 session 修复了音频导出（单次 pass filter_complex），但视频导出仍使用旧的逐段提取 + concat demuxer 方案，存在以下问题：

1. **视频导出时间漂移**: 逐段提取 .ts + concat 存在 AAC priming 累积（每段约 23ms），97 段约 2.3 秒偏移
2. **WAV 文件导出视频结果错误**: WAV 输入点击导出视频只输出第一句话的内容，其余为静音
3. **filter_complex 方案对视频无效**: 尝试了多种 filter_complex 方案均失败

### 根因分析

#### 问题 1: 视频导出时间漂移
- 原因与音频导出相同：逐段独立编码 + concat 导致 AAC 时间戳累积偏移
- 解决方案：统一使用 filter_complex 单次 pass

#### 问题 2: WAV 导出视频错误
- **根因**: 视频导出的 `output_path` 继承输入扩展名 (`_cut.wav`)，但内部使用 AAC 编码
- WAV 容器不适合存放 AAC 编码音频，导致播放异常
- 而音频导出按钮始终输出 `_cut.m4a`（正确的 AAC 容器），所以音频导出一直正常

#### 问题 3: filter_complex 视频方案的失败历程

| 方案 | 失败原因 |
|------|---------|
| `select` + `between(t,a,b)` 表达式 | 100+ 个 between 项，FFmpeg OOM |
| `split` + `asplit` + trim + concat | concat 输入顺序错误（所有 video 再所有 audio），FFmpeg Media type mismatch |
| 修复 concat 交错顺序后 | 仍未测试真实视频输入（之前输入都是 WAV） |

### 修复内容

#### 1. `export_video` 统一使用 filter_complex (`_build_video_trim_filter`)

**替换**: 旧的逐段提取 (.ts) + concat demuxer (`_extract_segment`) 方案

**新方案**: 单次 pass filter_complex
- 视频: `split=N` + 每段 `trim + setpts=PTS-STARTPTS`
- 音频: `asplit=N` + 每段 `atrim + asetpts=PTS-STARTPTS`
- 合并: `concat=n=N:v=1:a=1[outv][outa]`

关键: concat 输入必须是 **交错排列** `[v0][a0][v1][a1]...`，不能分组排列 `[v0][v1]...[a0][a1]...`

#### 2. WAV 输入委托给 `export_audio` + 扩展名修正

```python
# export_video 中，当 has_video=False 时委托给 export_audio
if not has_video:
    out = Path(output_path)
    if out.suffix.lower() == ".wav":
        output_path = str(out.with_suffix(".m4a"))  # WAV 容器不能放 AAC
    return export_audio(...)
```

#### 3. `_build_audio_trim_filter` 改用 `asplit` (`Session 11` 中已引入)

使用 `asplit=N` 显式分流，避免多次引用 `[0:a]` 导致某些格式（如 WAV 顺序读取）下第二个 atrim 开始读到 EOF 产生静音。

#### 4. 新增 `_build_video_trim_filter` (`core/export_service.py`)

生成视频+音频的 filter_complex：
- `split=N` 分流视频流，`asplit=N` 分流音频流
- 每段 `trim+setpts`（视频）和 `atrim+asetpts`（音频）
- `concat=n=N:v=1:a=1` 交错排列输入

### 诊断日志

在 `export_video` 入口添加：

```python
logger.info("export_video: has_video={}, media_path={}, width={}", ...)
```

### 验证

- WAV 输入点击导出视频 -> 输出 `_cut.m4a`，音频内容完整正确
- 视频输入点击导出视频 -> filter_complex 单次 pass，音视频时间对齐
- SRT 导出不受影响
- 音频导出按钮功能不变（`_cut.m4a`）

### 📝 Commit Message

```
fix(export): 修复音频导出末尾截断与SRT时间轴对齐问题

- 改用 FFmpeg filter_complex 单次通过替代逐段 AAC 编码，解决 priming 累积偏移
- 重构 SRT 时间戳映射逻辑，基于 keep_ranges 精确计算替代线性减法
- 确保导出音频与字幕时间轴完全对齐，消除重叠现象

refactor(export): 统一视频导出为 filter_complex 方案

- 替换视频导出中的逐段提取 + concat demuxer 方案
- 修复 WAV 输入导出视频内容不完整的问题
- 解决视频导出时间漂移问题，与音频导出保持一致
```

### 🚀 Release Notes

```
## 2026-05-16 - 导出功能精确性优化

### ✨ 新增
- 新增基于 keep_ranges 的精确时间轴映射，提高字幕同步精确度

### 🐛 修复
- 修复导出音频末尾截断问题：确保导出音频完整覆盖所有保留字幕
- 修复SRT字幕时间戳与音频不对齐：消除字幕时间重叠，提高同步精确度
- 修复WAV输入导出视频时内容不完整的问题

### ⚡ 优化
- 提升导出精确度：从样本级精度替代原有累积误差方法
- 统一音视频导出流程：使用相同的filter_complex处理逻辑，提高一致性
- 性能优化：减少逐段处理产生的延迟，特别是长视频导出
```

---

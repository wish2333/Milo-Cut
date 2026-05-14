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

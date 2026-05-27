# Milo-Cut 1.2.0 Development Record

## Overview

1.2.0 版本聚焦于 AI 赋能引入，核心目标是通过 uv 驱动的插件化隔离环境管理 ASR 引擎，实现端到端语音转写流程。按审计计划 `audit-plan-1.2.0.md` 分 3 个 Sprint 执行。本文档记录 Sprint 1 完成情况。

## Branch

`dev-1.2.0` (from `main`)

## Architecture Decisions

### uv-driven 插件隔离

每个 ASR 引擎运行在独立的 uv 虚拟环境中，主程序保持 ~50MB 精简体积。通过 `sys.path` 注入插件 site-packages 实现同进程加载（Sprint 1 采用 subprocess IPC 方案）。

### 子进程 IPC 架构

ASR 推理在隔离子进程中执行，通过 stdout 行分隔 JSON 通信，结果写入文件避免管道溢出。子进程包含 stdin EOF 守护线程，主进程退出时自动终止孤儿进程。

### 跨平台数据目录

- Windows: `%LOCALAPPDATA%/MiloCut/`
- macOS: `~/Library/Application Support/MiloCut/`
- Linux: `~/.local/share/milocut/`

### 模型下载源自动探测

`_detect_download_source()` 按优先级尝试 HuggingFace -> hf-mirror -> ModelScope，确保国内外网络均可下载。

---

## Sprint 1: PluginManager + faster-whisper ASR + UI

### Task 1.1: PluginManager 后端

**目标**: 实现 uv 驱动的插件化隔离环境管理核心。

**新建文件**:
- `core/plugin_manager.py` (786 行)

**修改文件**:
- `core/paths.py` -- 新增 `get_plugin_data_dir()` 跨平台数据目录
- `core/models.py` -- 新增 `PLUGIN_INSTALL` 任务类型、`PluginInfo` / `ModelInfo` 模型
- `core/config.py` -- 新增 AI/ASR 设置默认值

**实现细节**:

1. `PLUGIN_REGISTRY` 字典定义两个插件:
   - `plugin-whisper`: Faster Whisper ASR (faster-whisper>=1.0.0)
   - `plugin-qwen`: Qwen3 ASR (transformers>=4.40.0, torch>=2.0.0, accelerate)

2. `PluginManager` 核心类:
   - `list_plugins()` -- 遍历 PLUGIN_REGISTRY，合并注册表状态
   - `is_installed(plugin_id)` -- 检查 venv 目录和 Python 可执行文件存在性
   - `get_plugin_python(plugin_id)` -- 返回插件 venv 的 Python 路径
   - `install_plugin(plugin_id, progress_cb)` -- `uv venv` + `uv pip install`
   - `uninstall_plugin(plugin_id)` -- 删除 venv 目录 + 注册表条目
   - `list_models()` -- 遍历所有插件的模型，检查本地下载状态
   - `ensure_model(model_id, progress_cb)` -- 确保模型已下载，自动选择下载源
   - `delete_model(model_id)` -- 删除模型文件
   - `run_in_plugin(plugin_id, script, args, ...)` -- 子进程执行核心

3. `SubprocessTask` / `SubprocessState` 数据类:
   - 状态枚举: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
   - 包含 process, state, result, error, log_path, cancel_event 字段

4. 子进程管理:
   - Windows 无窗口启动: `CREATE_NO_WINDOW` + `STARTUPINFO.wShowWindow=0`
   - stdin 管道用于孤儿进程防御
   - stdout 行分隔 JSON IPC（进度、结果、错误事件）
   - stderr 合并到日志文件
   - 结果写入文件（不走 stdout 管道，避免大结果集溢出）
   - 退出码分类: SIGSEGV/SIGABRT/Windows 异常码 -> 用户友好错误消息

5. 辅助函数:
   - `_get_uv_path()` -- 打包后与 exe 同目录查找 uv 二进制
   - `_clean_subprocess_env()` -- 清除 PyInstaller 注入的 PYTHONPATH/PYTHONHOME/LD_LIBRARY_PATH
   - `_detect_download_source()` -- 网络探测选择下载源
   - `_subprocess_kwargs()` -- 构建跨平台子进程参数
   - `_classify_exit_code()` -- 退出码分类和用户友好消息

6. 注册表持久化:
   - 路径: `<数据目录>/registry.json`
   - 原子写入: tmp 文件 + `os.replace()` 防止崩溃损坏

7. `get_plugin_data_dir()` 跨平台实现:
   - Windows: `Path(os.environ.get("LOCALAPPDATA", ...)) / "MiloCut"`
   - macOS: `Path.home() / "Library" / "Application Support" / "MiloCut"`
   - Linux: `Path(os.environ.get("XDG_DATA_HOME", ...)) / "milocut"`

8. `PluginInfo` Pydantic 模型 (frozen=True):
   - plugin_id, display_name, engine, version, status, installed_at, venv_path

9. `ModelInfo` Pydantic 模型 (frozen=True):
   - model_id, display_name, plugin_id, size_bytes, local_path, status

10. config.py 新增默认值:
    - asr_engine, asr_model_size, asr_language, asr_device, asr_compute_type
    - duplicate_threshold, duplicate_min_length

---

### Task 1.2: Pydantic 模型扩展

**目标**: 扩展数据模型以支持插件和 AI 功能。

**修改文件**:
- `core/models.py` -- PluginInfo、ModelInfo、TaskType 扩展、AnalysisResult.type 扩展
- `frontend/src/types/project.ts` -- PluginInfo、ModelInfo 接口、AnalysisResult.type
- `frontend/src/types/task.ts` -- TaskType 新增 plugin_install
- `frontend/src/types/edit.ts` -- AppSettings 新增 AI 设置字段

**实现细节**:

1. `TaskType` 新增 `PLUGIN_INSTALL = "plugin_install"`
2. `AnalysisResult.type` 从 `Literal["filler", "error"]` 扩展为 `Literal["filler", "error", "duplicate"]`
3. 前端 `AppSettings` 新增 7 个 AI 设置字段:
   - `asr_engine`, `asr_model_size`, `asr_language`, `asr_device`, `asr_compute_type`
   - `duplicate_threshold`, `duplicate_min_length`

---

### Task 1.3: PluginManager 桥接 API

**目标**: 将 PluginManager 能力暴露给前端。

**修改文件**:
- `main.py` (+198 行)

**实现细节**:

1. `MiloCutApi.__init__()` 初始化 `PluginManager` 实例

2. 注册 2 个任务处理器:
   - `PLUGIN_INSTALL` -> `_handle_plugin_install` -- 安装插件 + 可选模型下载
   - `TRANSCRIPTION` -> `_handle_transcription` -- 读取设置、调用 transcribe_with_whisper、更新项目

3. 新增 10 个 `@expose` 桥接方法:
   - `list_plugins()` -- 返回已注册插件列表及状态
   - `install_plugin(plugin_id)` -- 启动后台安装任务，返回 task_id
   - `uninstall_plugin(plugin_id)` -- 卸载插件
   - `list_models()` -- 返回已下载模型列表
   - `download_model(model_id)` -- 启动模型下载任务
   - `delete_model(model_id)` -- 删除模型
   - `check_plugin_status(engine)` -- 检查引擎是否就绪
   - `get_asr_log(task_id)` -- 返回指定 ASR 任务的日志内容
   - `list_asr_logs()` -- 返回 ASR 日志文件列表（按时间倒序）
   - `get_asr_task_state(task_id)` -- 返回子进程状态

---

### Task 1.4: faster-whisper ASR 服务

**目标**: 实现 faster-whisper 子进程推理脚本和主进程协调层。

**新建文件**:
- `core/asr_service.py` (158 行)
- `core/asr_scripts/__init__.py` (1 行)
- `core/asr_scripts/common.py` (87 行)
- `core/asr_scripts/whisper_transcribe.py` (152 行)

**实现细节**:

1. `asr_service.py` 协调层:
   - `transcribe_with_whisper(plugin_manager, media_path, ...)` -- 主进程侧协调
   - 检查插件安装 -> 确保模型下载 -> 构建参数 -> 启动子进程 -> 等待结果
   - `_resolve_whisper_model(model_size)` -- 解析简写到完整模型 ID
     - "large-v3-turbo" -> "Systran/faster-whisper-large-v3-turbo"
     - "base" -> "Systran/faster-whisper-base"

2. `common.py` 子进程公共模板:
   - `report(event_type, **kwargs)` -- stdout JSON 事件输出
   - `start_stdin_watchdog()` -- EOF 检测守护线程，检测到 stdin EOF 时 `os._exit(1)` 自杀
   - `parse_args()` -- 通用参数解析（result_path, log_path 等）
   - `write_result(path, data)` -- 原子写入结果 JSON 文件

3. `whisper_transcribe.py` 子进程脚本:
   - 解析参数（media_path, model_path, language, device, compute_type, word_timestamps, vad_filter）
   - 启动 stdin 守护线程
   - 加载 WhisperModel
   - 调用 `model.transcribe()` 逐段报告进度
   - 将 segments 和 words 写入 result_path 文件
   - 异常时 report("error") 并退出

4. `_handle_transcription` 任务处理器:
   - 从 settings.json 读取 ASR 配置
   - 调用 `transcribe_with_whisper()`
   - 将结果转换为 Segment 列表
   - 更新项目 TranscriptData

---

### Task 1.5: 插件管理 UI

**目标**: 设置页新增 AI 引擎管理区域。

**新建文件**:
- `frontend/src/composables/usePluginManager.ts` (197 行)

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue` (+280 行)

**实现细节**:

1. `usePluginManager` composable:
   - `plugins` / `models` 响应式列表
   - `listPlugins()` / `listModels()` -- 调用桥接获取数据
   - `installPlugin(pluginId)` -- 调用 install_plugin，返回 task_id
   - `uninstallPlugin(pluginId)` -- 调用 uninstall_plugin
   - `downloadModel(modelId)` / `deleteModel(modelId)`
   - `checkEngineReady(engine)` -- 检查插件+模型是否就绪
   - `ensureReady(engine)` -- 检查就绪状态，未就绪时提示安装

2. SettingsModal AI 引擎区域:
   - 插件列表: 名称、引擎类型、版本、状态标签
   - 安装/卸载按钮
   - 已安装插件展开: 关联模型列表 + 下载/删除按钮
   - 安装进度条（通过 task:progress 事件更新）
   - ASR 设置: 引擎下拉、语言、设备、计算类型、重复检测阈值

---

### Task 1.6: ASR UI 集成

**目标**: 工作区新增转写按钮，打通端到端 ASR 流程。

**修改文件**:
- `frontend/src/composables/useAnalysis.ts` (+9 行)
- `frontend/src/pages/WorkspacePage.vue` (+19 行)

**实现细节**:

1. `useAnalysis.ts` 扩展:
   - `ANALYSIS_TASKS` 新增 `"transcription"`
   - 新增 `runTranscription(payload?)` 函数
   - 导出 `activeTask` ref

2. `WorkspacePage.vue` 集成:
   - 从 useAnalysis 解构 `activeTask`
   - `isTranscribing` computed: `activeTask.value.type === "transcription" && status === "running"`
   - `handleTranscribe()` 函数调用 `runTranscription()`
   - 工具栏新增紫色 "Transcribe" 按钮（位于 "Import SRT" 和 "Detect Silence" 之间）
   - 按钮转写中显示进度，其他操作按钮禁用

---

## Files Modified Summary

### Backend (core/) -- New Files
- `plugin_manager.py` -- 786 行: 插件生命周期管理核心（PluginManager, PLUGIN_REGISTRY, SubprocessTask）
- `asr_service.py` -- 158 行: 主进程 ASR 协调层（transcribe_with_whisper）
- `asr_scripts/__init__.py` -- 1 行: 包初始化
- `asr_scripts/common.py` -- 87 行: 子进程公共模板（report, stdin_watchdog, parse_args）
- `asr_scripts/whisper_transcribe.py` -- 152 行: faster-whisper 子进程推理脚本

### Backend (core/) -- Modified Files
- `paths.py` -- +22 行: get_plugin_data_dir() 跨平台数据目录
- `models.py` -- +31 行: PluginInfo, ModelInfo 模型, PLUGIN_INSTALL 任务类型, AnalysisResult.type 扩展
- `config.py` -- +8 行: AI/ASR 设置默认值

### Backend -- Modified Files
- `main.py` -- +198 行: PluginManager 初始化, 2 个任务处理器, 10 个桥接方法

### Frontend (frontend/src/) -- New Files
- `composables/usePluginManager.ts` -- 197 行: 插件管理 composable

### Frontend (frontend/src/) -- Modified Files
- `components/workspace/SettingsModal.vue` -- +280 行: AI 引擎管理区域 + ASR 设置
- `composables/useAnalysis.ts` -- +9 行: runTranscription, activeTask 导出
- `pages/WorkspacePage.vue` -- +19 行: 转写按钮 + isTranscribing 状态
- `types/project.ts` -- +25 行: PluginInfo, ModelInfo 接口, AnalysisResult.type
- `types/task.ts` -- +1 行: plugin_install 类型
- `types/edit.ts` -- +8 行: AI 设置字段

### Other
- `uv.lock` -- 小幅更新

---

## Verification

- [x] 后端 97 个测试全部通过
- [x] 前端 105 个测试全部通过（7 个测试文件）
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] PluginManager 正确列出两个插件（均未安装状态）
- [x] 跨平台数据目录正确（Windows: %LOCALAPPDATA%/MiloCut/）
- [x] _clean_subprocess_env() 清除三个环境变量
- [x] _resolve_whisper_model() 正确解析简写和完整模型 ID
- [x] SettingsModal AI 引擎区域正确渲染
- [x] WorkspacePage 转写按钮正确显示和状态管理

---

## Commit Messages

### Sprint 1

```
feat(asr): 插件化 ASR 引擎基础设施 -- PluginManager、faster-whisper、UI 集成

- 新建 core/plugin_manager.py: uv 驱动的插件化隔离环境管理
- PLUGIN_REGISTRY 定义 plugin-whisper 和 plugin-qwen 两个插件
- PluginManager 核心: install/uninstall, ensure_model, run_in_plugin
- 子进程 IPC: stdout 行分隔 JSON, stdin EOF 孤儿进程防御
- Windows 无窗口启动: CREATE_NO_WINDOW + STARTUPINFO
- 注册表原子写入: tmp + os.replace() 防崩溃损坏
- 跨平台数据目录: Windows/macOS/Linux 自适应
- 模型下载源自动探测: HuggingFace -> hf-mirror -> ModelScope
- 新建 core/asr_service.py: 主进程 ASR 协调层
- 新建 core/asr_scripts/: common.py 公共模板 + whisper_transcribe.py 推理脚本
- _resolve_whisper_model() 解析简写到完整模型 ID
- main.py 新增 10 个桥接方法 + 2 个任务处理器
- core/models.py 新增 PluginInfo, ModelInfo, PLUGIN_INSTALL
- core/config.py 新增 AI/ASR 设置默认值
- core/paths.py 新增 get_plugin_data_dir() 跨平台路径
- 新建 usePluginManager composable: 插件/模型管理
- SettingsModal 新增 AI 引擎管理区域 + ASR 设置
- useAnalysis 新增 runTranscription + activeTask 导出
- WorkspacePage 新增转写按钮（紫色，带进度状态）
- 前端类型扩展: PluginInfo, ModelInfo, plugin_install, AI 设置字段
```

---

## Statistics

- New files: 6 (plugin_manager.py, asr_service.py, asr_scripts/__init__.py, common.py, whisper_transcribe.py, usePluginManager.ts)
- Modified files: 11
- Total new lines: ~1,980 (backend ~1,184, frontend ~796)
- Backend tests: 97 passing
- Frontend tests: 105 passing (7 test files)

---

## Next: Sprint 2

Sprint 2 将实现:
- Task 2.1: Qwen3-ASR 转写服务（qwen_transcribe.py 子进程脚本）
- Task 2.2: VAD 增强（复用 faster-whisper 内置 Silero VAD）
- Task 2.3: 重复句检测（analysis_service.py 新增 detect_duplicates）
- Task 2.4: ASR 设置完善（设置页 VAD 开关、引擎切换）

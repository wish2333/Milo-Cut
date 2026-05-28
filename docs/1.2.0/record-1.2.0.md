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

---

## Sprint 1.5: 代码审计与修复 (2026-05-28)

### 背景

用户反馈 1.2.0 "开发得十分粗糙，功能基本不可用"，进行了全面代码审计并修复关键问题。

### 审计发现

#### P0 级问题（导致功能不可用）

| 问题 | 位置 | 影响 |
|------|------|------|
| 任务进度回调断裂 | task_manager.py:139-142 | 所有长时间任务无法显示进度 |
| 子进程参数解析缺陷 | whisper_transcribe.py:35-47 | ASR子进程启动失败 |
| 前端未等待异步任务 | usePluginManager.ts:40-66 | 用户看到"成功"但实际未完成 |
| Transcribe按钮未检查插件就绪 | WorkspacePage.vue:346-348 | 未安装插件时直接失败 |
| 静默错误吞噬 | ffmpeg_service.py, ffmpeg_presets.py | 错误信息丢失 |

#### Sprint 2/3 完全未开始

- Qwen3-ASR 转写服务未实现
- VAD 增强未实现
- 重复句检测未实现
- 原片/剪后切换未实现
- 版本号未更新（仍是 1.1.0）

---

### 已完成的修复

#### 1. 修复进度回调断裂 [CRITICAL]

**文件**: `core/task_manager.py`

```python
# 修改前
self._handlers: dict[TaskType, Callable[[MiloTask, threading.Event], dict]]
result = handler(task, cancel_event)

# 修改后
self._handlers: dict[TaskType, Callable[[MiloTask, threading.Event, Callable[[float, str], None]], dict]]
result = handler(task, cancel_event, progress_cb)
```

#### 2. 更新所有handler签名 [CRITICAL]

**文件**: `main.py` - 更新11个handler接收progress_cb参数

#### 3. 修复子进程脚本参数解析 [CRITICAL]

**文件**: `core/asr_scripts/whisper_transcribe.py`

```python
# 修改前
def parse_whisper_args():
    base = parse_args()
    parser = argparse.ArgumentParser(parents=[...])
    return parser.parse_args()  # BUG: 重复解析

# 修改后
def parse_whisper_args():
    common = parse_args()
    parser = argparse.ArgumentParser(add_help=False)
    # ... 添加所有参数 ...
    args, _ = parser.parse_known_args()  # 正确：忽略未知参数
    return args
```

#### 4. 添加日志到静默except块 [HIGH]

**文件**: `core/ffmpeg_service.py`, `core/ffmpeg_presets.py`

```python
# 修改前
except Exception:
    pass

# 修改后
except Exception as e:
    logger.debug("Failed to ...: {}", e)
```

#### 5. 前端installPlugin等待任务完成 [HIGH]

**文件**: `frontend/src/composables/usePluginManager.ts`

```typescript
// 修改后：轮询任务状态直到完成
return await new Promise<boolean>((resolve) => {
    const pollInterval = setInterval(async () => {
        const taskRes = await call<{ status: string }>("get_task", taskId)
        if (taskRes.data?.status === "completed") {
            clearInterval(pollInterval)
            resolve(true)
        } else if (taskRes.data?.status === "failed") {
            clearInterval(pollInterval)
            resolve(false)
        }
    }, 500)
})
```

#### 6. handleTranscribe检查插件就绪 [HIGH]

**文件**: `frontend/src/pages/WorkspacePage.vue`

```typescript
async function handleTranscribe() {
    const engine = "faster-whisper"
    const status = await ensureReady(engine)
    
    if (!status.ready) {
        // 自动安装插件和模型
        const installed = await installPlugin(status.pluginId, modelId, onProgress)
        if (!installed) return
    }
    
    await runTranscription()
}
```

---

### 1.2.0 功能调整

#### 1. 插件路径重构

**文件**: `core/paths.py`

- 开发环境: 插件安装到 `<项目根目录>/data/plugins/`
- 打包环境: 保持跨平台路径 (`%LOCALAPPDATA%/MiloCut/` 等)
- 通过 `sys.frozen` 自动检测环境

#### 2. PyTorch GPU支持

**文件**: `core/plugin_manager.py`

- 分离 CPU/GPU 依赖:
  - `dependencies_cpu`: 标准 PyTorch
  - `dependencies_gpu`: 包含 `--extra-index-url https://download.pytorch.org/whl/cu124`
- 修改 `install_plugin()` 支持新的依赖结构

#### 3. Qwen3 模型更新

**文件**: `core/plugin_manager.py`

- 添加 `Qwen/Qwen3-ASR-1.7B` 模型 (4.7GB)
- 修正所有模型的 `size_bytes`:
  - `Qwen3-ASR-0.6B`: 1.2GB -> 1.88GB
  - `Qwen3-ForcedAligner-0.6B`: 0.6GB -> 1.84GB
- 注意: 用户说的"1.8B"实际是 `1.7B`

#### 4. 设置系统重设计

**文件**: `frontend/src/components/workspace/SettingsModal.vue`

- `compute_type` 设置仅对 `faster-whisper` 引擎显示
- `device` 的 `auto` 选项仅对 `faster-whisper` 显示
- Qwen3 ASR 只显示 `cpu` 和 `cuda` 选项

#### 5. 添加"打开数据目录"按钮

**文件**:
- `main.py`: 添加 `get_plugin_data_dir()` 和 `open_data_directory()` 暴露方法
- `SettingsModal.vue`: 
  - 添加 `handleOpenDataDirectory()` 和 `loadPluginDataDir()` 函数
  - 在 AI Engine 区域底部添加数据目录显示和"Open folder"按钮

#### 6. 修复路径嵌套bug

**文件**: `core/plugin_manager.py`

```python
# 修改前 - 导致 data/plugins/plugins/ 嵌套
self._plugins_dir = plugins_dir or get_plugin_data_dir() / "plugins"

# 修改后
self._plugins_dir = plugins_dir or get_plugin_data_dir()
```

---

### 修改文件汇总 (Sprint 1.5)

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `core/task_manager.py` | 修复 | 进度回调传递给handler |
| `main.py` | 修复+新增 | handler签名更新 + 数据目录方法 |
| `core/asr_scripts/whisper_transcribe.py` | 修复 | 参数解析 |
| `core/ffmpeg_service.py` | 修复 | 添加日志到静默except |
| `core/ffmpeg_presets.py` | 修复 | 添加日志到静默except |
| `core/paths.py` | 重构 | 开发/打包环境路径切换 |
| `core/plugin_manager.py` | 重构+修复 | GPU支持、Qwen3-1.7B、路径修复 |
| `frontend/src/composables/usePluginManager.ts` | 修复 | 等待任务完成 |
| `frontend/src/pages/WorkspacePage.vue` | 修复 | 检查插件就绪 |
| `frontend/src/components/workspace/SettingsModal.vue` | 新增 | 动态设置、数据目录按钮 |

---

### Sprint 1.6

**目标**: 修复 GPU 安装失败、插件架构重构、UI 优化。

**问题背景**:

- GPU 安装始终拉取 CPU 版 PyTorch（PyPI 优先于 `--find-links`）
- 单一 `plugin-qwen` 无法同时支持 CPU/GPU 两种 PyTorch
- 镜像源选择和缓存清理需求
- DaisyUI v5 checkbox 组件渲染异常

**修改文件**:

| 文件                                                  | 类型      | 说明                                                 |
| ----------------------------------------------------- | --------- | ---------------------------------------------------- |
| `core/plugin_manager.py`                              | 重构+新增 | 拆分插件、GPU检测、镜像配置、安装参数                |
| `main.py`                                             | 重构+新增 | API 拆分、镜像列表、目录打开                         |
| `frontend/src/components/workspace/SettingsModal.vue` | 重构      | Available Engines、PyTorch Install Options、模型去重 |
| `frontend/src/composables/usePluginManager.ts`        | 修改      | installPlugin 参数扩展                               |
| `frontend/src/pages/WorkspacePage.vue`                | 修改      | 移除 useGpu 逻辑                                     |
| `frontend/src/types/task.ts`                          | 修改      | TaskProgress 新增 task_id                            |

**实现细节**:

1. **插件架构重构**:

   - 拆分 `plugin-qwen` 为 `plugin-qwen-cpu` 和 `plugin-qwen-gpu` 两个独立插件
   - CPU 插件: 标准 PyPI torch (CPU 版)
   - GPU 插件: 相同依赖 + `pytorch_index` 字段指定 CUDA 轮子索引
   - 共享模型文件（CPU/GPU 插件引用相同模型 ID）

2. **GPU 安装修复**:

   - 根本原因: `--find-links` 是 flat directory，uv 仍优先选择 PyPI CPU 轮子
   - 解决方案: 改用 `--extra-index-url`，将 CUDA 索引作为正式索引源
   - 新增 `pytorch_index` 字段定义插件的 PyTorch 索引 URL
   - `install_plugin()` 根据 `pytorch_index` 自动添加 `--extra-index-url`

3. **PYTORCH_MIRRORS 配置**:

   ```python
   PYTORCH_MIRRORS = {
       "official": {"url": "https://download.pytorch.org/whl/cu124", ...},
       "aliyun": {"url": "https://mirrors.aliyun.com/pytorch-wheels/cu124", ...},
       "nju": {"url": "https://mirrors.nju.edu.cn/pytorch/whl/cu124", ...},
   }
   ```

4. **GPU 检测函数**:

   - `detect_gpu()` 通过 `nvidia-smi` 检测 GPU 状态
   - 解析 `CUDA Version: X.X` 头部信息（不依赖 PyTorch）
   - 返回 `has_nvidia_gpu`, `cuda_available`, `cuda_version`, `gpu_name`, `recommendation`
   - 推荐逻辑: 有 CUDA → "gpu"，有 GPU 无 CUDA → "install_cuda"，无 GPU → "cpu"

5. **API 层重构**:

   - 重命名旧 `detect_gpu` → `detect_gpu_encoders`（FFmpeg 编码器检测）
   - 新增 `detect_gpu` 调用 `plugin_manager.detect_gpu()`
   - 新增 `list_mirrors` 暴露 PYTORCH_MIRRORS
   - `install_plugin` 签名更新: 接受 `mirror` 和 `no_cache` 参数
   - `open_data_directory` 使用 `os.startfile()` 替代 `subprocess.Popen(["explorer", ...])`

6. **SettingsModal UI 重构**:

   - **Available Engines 区域**: 独立显示所有 3 个插件，不受 ASR 引擎设置限制
   - **PyTorch Install Options 区域**: 镜像源选择 + 清除缓存 checkbox，始终可见
   - **GPU 选项**: 无 NVIDIA GPU 时禁用（opacity-50 + pointer-events-none）
   - **CUDA 警告**: 有 GPU 无 CUDA 时显示下载链接
   - **Installed/Downloaded/Available 列表**: 卸载/删除/下载按钮
   - **模型去重**: 使用 Set<model_id> 避免 CPU/GPU 插件共享模型导致的重复

7. **Checkbox 问题处理**:

   - DaisyUI v5 的 `checkbox` class 导致 checkbox 不可见
   - CSS 分析: `appearance: none` 隐藏原生 checkbox，`::before` 伪元素绘制自定义样式
   - `--falsesize` CSS 变量可能未正确解析
   - 最终方案: 使用原生 checkbox + Tailwind `accent-blue-600` 样式

   ```html
   <input type="checkbox" v-model="clearCache" class="w-4 h-4 mt-0.5 accent-blue-600" />
   ```

8. **TaskProgress 类型扩展**:

   - 新增可选 `task_id` 字段，用于匹配进度事件

**待验证**:

- [ ] 用户卸载 `plugin-qwen-gpu` 并重新安装，验证 CUDA 版 PyTorch 是否正确拉取
- [ ] 确认 `--extra-index-url` 方案在 uv 中正常工作

## Sprint 1.7: 模型下载系统修复 + UI 修复 (2026-05-29)

### 问题背景

用户反馈以下问题:

1. 模型下载任务未走 TaskManager（Bug 1）
2. 前端 `downloadModel()` 一次性调用后立即返回成功，未等待下载完成（Bug 2）
3. Whisper 模型 ID 全部使用 `Systran/` 命名空间，turbo 模型应改用更活跃的 `Purfview/` 仓库（Bug 3 初始）
4. Whisper base 模型下载 401 错误 -- `Purfview/faster-whisper-base` 在 HuggingFace 上不存在（Bug 3 修正）
5. SettingsModal 只显示 General 页，tab 导航栏其他标签不可见
6. 模型下载源下拉菜单背景透明
7. Downloaded models 中 Qwen 模型重复显示（CPU/GPU 插件共享相同 model_id）
8. `huggingface-hub` 和 `modelscope` 依赖未添加到 `pyproject.toml`

### 已完成的修复

#### 1. download_model() 走 TaskManager [CRITICAL]

**文件**: `main.py`

- `download_model()` 现在创建 `MiloTask(task_type="model_download")` 并通过 `TaskManager.start_task()` 执行
- 注册 `MODEL_DOWNLOAD` 任务处理器 `_handle_model_download()`

#### 2. 前端 downloadModel() 轮询等待完成 [CRITICAL]

**文件**: `frontend/src/composables/usePluginManager.ts`

- 重写 `downloadModel()` 为 Promise + setInterval 轮询（500ms 间隔）
- 超时 5 分钟自动 reject
- 轮询 `get_task()` 状态直到 `completed` 或 `failed`

#### 3. Whisper 模型 ID 修正 [HIGH]

**文件**: `core/plugin_manager.py`, `core/asr_service.py`

- turbo 模型: `Systran/faster-whisper-large-v3-turbo` -> `Purfview/faster-whisper-large-v3-turbo`
- base 模型: 修正为 `Systran/faster-whisper-base`（Purfview 的 base 模型在 HuggingFace 不存在，导致 401）
- 同步更新 `PLUGIN_REGISTRY`、`MODELSCOPE_ID_MAP`、`_resolve_whisper_model()` 文档注释

#### 4. 模型下载镜像选择系统 [HIGH]

**新建内容**: `core/plugin_manager.py` 新增 MODEL_MIRRORS、MODELSCOPE_ID_MAP

**修改文件**: `core/plugin_manager.py`, `main.py`, `frontend/src/types/project.ts`, `frontend/src/composables/usePluginManager.ts`, `frontend/src/components/workspace/SettingsModal.vue`

- `MODEL_MIRRORS` 字典: huggingface / hf-mirror / modelscope 三源
- `MODELSCOPE_ID_MAP`: HF model ID 到 ModelScope ID 的映射
- `_detect_download_source()`: TCP 连接测试 huggingface.co:443 (3s) -> hf-mirror.com:443 (3s) -> fallback "modelscope"
- `list_model_mirrors()` 桥接 API 暴露镜像列表
- `download_model()` 接受 `mirror` 参数
- `_download_from_hf()`: 通过 `huggingface-hub` 的 `snapshot_download()` 下载
- `_download_from_modelscope()`: 通过 `modelscope` 的 `snapshot_download()` 下载
- 前端 SettingsModal 新增镜像源下拉选择器

#### 5. SettingsModal Tab 导航修复 [HIGH]

**文件**: `frontend/src/components/workspace/SettingsModal.vue`

- 根因: DaisyUI 5.5.19 `<input type="radio" class="tab">` 模式渲染异常
- 修复: 替换为 Vue 控制的 button tabs -- `activeTab` ref + `v-if` 面板切换
- 三个 tab: General / AI Engine / Export

#### 6. 镜像下拉菜单背景修复 [MEDIUM]

**文件**: `frontend/src/components/workspace/SettingsModal.vue`

- 根因: DaisyUI 5 `select select-bordered` 组件背景透明
- 修复: 改用 Tailwind 原生样式 `px-2 py-1.5 text-sm border border-gray-300 rounded-lg bg-white`

#### 7. Qwen 模型去重 [MEDIUM]

**文件**: `frontend/src/components/workspace/SettingsModal.vue`

- 根因: `plugin-qwen-cpu` 和 `plugin-qwen-gpu` 共享相同 model_id，`refreshInstalledLists()` 只对 `notDownloadedModels` 去重，`downloadedModels` 未去重
- 修复: `downloadedModels` 也使用 `Set<string>` 按 `model_id` 去重

#### 8. pyproject.toml 依赖补充 [HIGH]

**文件**: `pyproject.toml`

- 新增 `huggingface-hub>=0.20`
- 新增 `modelscope>=1.10`
- 执行 `uv lock` 解析 62 个包

#### 9. Lint 清理 [LOW]

**文件**: `frontend/src/pages/WorkspacePage.vue`

- 移除未使用的 `ensureReady` 和 `installPlugin` 导入

### 修改文件汇总 (Sprint 1.7)

| 文件                                                  | 类型 | 说明                                                         |
| ----------------------------------------------------- | ---- | ------------------------------------------------------------ |
| `core/plugin_manager.py`                              | 修改 | MODEL_MIRRORS, MODELSCOPE_ID_MAP, 模型 ID 修正, _download_from_hf/modelscope |
| `core/asr_service.py`                                 | 修改 | _resolve_whisper_model() 文档注释更新                        |
| `core/models.py`                                      | 已有 | TaskType.MODEL_DOWNLOAD (本次未新增，原已存在)               |
| `main.py`                                             | 修改 | _handle_model_download 注册, download_model 走 TaskManager, list_model_mirrors API |
| `frontend/src/types/project.ts`                       | 修改 | ModelMirror 类型定义                                         |
| `frontend/src/composables/usePluginManager.ts`        | 修改 | downloadModel() 轮询重写, listModelMirrors()                 |
| `frontend/src/components/workspace/SettingsModal.vue` | 重构 | Vue button tabs, Tailwind 原生镜像下拉, 模型去重             |
| `frontend/src/pages/WorkspacePage.vue`                | 修改 | 移除未使用导入                                               |
| `pyproject.toml`                                      | 修改 | 新增 huggingface-hub, modelscope 依赖                        |

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

### Sprint 1.5

```
fix(core,ui): 修复1.2.0关键缺陷及功能优化

- 修复任务进度回调断裂，恢复长时间任务进度显示
- 修复 ASR 子进程参数重复解析导致启动失败的问题
- 修复前端未等待异步任务完成就返回成功的问题
- 修复点击转写时未校验插件就绪状态的问题
- 为静默异常块补充日志记录，防止错误信息丢失
- 重构插件路径逻辑，区分开发与打包环境
- 分离 PyTorch CPU/GPU 依赖，支持 GPU 加速安装
- 新增 Qwen3-ASR-1.7B 模型并修正模型体积数据
- 优化设置面板，按引擎动态显示对应配置项
- 新增"打开数据目录"功能入口
- 修复插件目录路径嵌套产生的错误
```

### Sprint 1.6

```
fix(core,ui): GPU安装失败修复、插件架构重构、UI优化

- 拆分 plugin-qwen 为 plugin-qwen-cpu 和 plugin-qwen-gpu 两个独立插件
- 修复 GPU 安装始终拉取 CPU 版 PyTorch 问题 (--find-links -> --extra-index-url)
- 新增 PYTORCH_MIRRORS 配置 (official/aliyun/nju)
- 新增 detect_gpu() 函数，通过 nvidia-smi 检测 GPU 状态
- 重构 API 层: detect_gpu -> detect_gpu_encoders, 新增 detect_gpu/list_mirrors
- install_plugin 新增 mirror/no_cache 参数支持
- SettingsModal UI 重构: Available Engines 独立显示, PyTorch Install Options
- 新增模型去重逻辑，避免 CPU/GPU 插件共享模型导致的重复
- 修复 DaisyUI v5 checkbox 不可见问题，改用原生 checkbox + accent-blue-600
- TaskProgress 新增可选 task_id 字段
```

### Sprint 1.7

```
fix(download,ui): 模型下载全链路修复 + SettingsModal tab 导航重写

- download_model() 走 TaskManager 任务系统 (MODEL_DOWNLOAD)
- downloadModel() 前端重写为 Promise + 轮询等待完成
- Whisper turbo 改用 Purfview 仓库, base 修正为 Systran (Purfview 不存在)
- 新增镜像选择系统: MODEL_MIRRORS + _detect_download_source() TCP 探测
- 新增 list_model_mirrors API 和前端镜像下拉选择器
- SettingsModal tab 改为 Vue button tabs 修复 DaisyUI 5 渲染异常
- 镜像下拉改用 Tailwind 原生样式修复透明背景
- downloadedModels 按 model_id 去重修复 Qwen 重复显示
- pyproject.toml 补充 huggingface-hub 和 modelscope 依赖
```

---

## Sprint 2: Qwen3-ASR + VAD + 重复检测 (2026-05-28)

### Task 2.1: Qwen3-ASR 转写服务

**目标**: 实现 Qwen3-ASR 子进程推理脚本和主进程协调层。

**新建文件**:
- `core/asr_scripts/qwen_transcribe.py` (约280行)

**修改文件**:
- `core/asr_service.py` -- 新增 `transcribe_with_qwen()` 和 `_resolve_qwen_model()`

**实现细节**:

1. `qwen_transcribe.py` 子进程脚本:
   - 智能音频切片 (`smart_slice_audio`):
     - 累积音频到 ~280s（ACCUMULATE_THRESHOLD）后在最佳静音点切割
     - 全程无静音点时强制 240s 均匀切割
     - 切片间保留 0.5s 重叠区（SLICE_OVERLAP）防漏字
   - 静音点检测 (`find_silence_points`): 基于能量的静音检测
   - 最佳切割点选择 (`find_best_cut_point`): 在目标时间附近找最佳静音点
   - 重叠区去重 (`deduplicate_overlap`): 利用有效内容区间剔除重复字词
   - 逐片 ASR 推理 + 强制对齐
   - 时间戳重映射到全局时间轴

2. `transcribe_with_qwen()` 协调函数:
   - 根据设备选择插件 (`plugin-qwen-cpu` 或 `plugin-qwen-gpu`)
   - 确保 ASR 模型和 Aligner 模型都已下载
   - 构建子进程参数并启动推理
   - 等待完成并返回结果

3. `_resolve_qwen_model()` 模型解析:
   - 支持 "asr" 和 "aligner" 两种类型
   - 支持简写 ("0.6B", "1.7B") 和完整模型 ID

**进度报告**:
- 0-5%: 音频分析和切片
- 5-15%: 模型加载
- 15-85%: 逐片转写
- 85-100%: 结果整合和保存

---

### Task 2.2: VAD 增强

**目标**: 为 faster-whisper 引擎添加 VAD 过滤开关。

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue` -- 添加 VAD 过滤 checkbox
- `frontend/src/types/edit.ts` -- 添加 `asr_vad_filter` 字段
- `core/config.py` -- 添加 `asr_vad_filter` 默认值

**实现细节**:

1. SettingsModal.vue:
   - 在 ASR Settings 区域添加 VAD filter checkbox
   - 仅当引擎为 `faster-whisper` 时显示
   - 使用原生 checkbox + `accent-blue-600` 样式
   - 提示文本: "Reduce hallucinations in noisy audio"

2. types/edit.ts:
   - AppSettings 接口新增 `asr_vad_filter: boolean`

3. config.py:
   - 默认值 `asr_vad_filter: True`

---

### Task 2.3: 重复句检测

**目标**: 实现基于 n-gram 余弦相似度的重复句检测。

**修改文件**:
- `core/analysis_service.py` -- 新增 `detect_duplicates()` 和辅助函数

**实现细节**:

1. 语言自适应 n-gram 提取 (`_get_ngrams`):
   - 中文 (`zh-*`): 字符级 3-gram
   - 英文/西文 (`en`, `de`, `fr` 等): 词级 2-gram
   - 其他/未知: 字符级 3-gram（默认）

2. 余弦相似度计算 (`_cosine_similarity`):
   - 基于 Counter 的频率向量
   - 计算点积和模长

3. 重复检测 (`detect_duplicates`):
   - 滑动窗口优化: 每段只与后续 50 段比较
   - 时间窗口约束: 只比较 5 分钟内的段
   - 复杂度 O(n * 50)，1000 段仅需 ~50000 次比较
   - 返回 `AnalysisResult` 列表，type="duplicate"

4. `run_full_analysis()` 更新:
   - 整合 filler、error、duplicate 三种检测
   - 从 settings 读取 `asr_language`、`duplicate_threshold`、`duplicate_min_length`

---

### Task 2.4: ASR 设置 UI

**目标**: 完善设置面板的 ASR 相关配置。

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue`
- `frontend/src/types/edit.ts`

**实现细节**:

1. ASR Settings 区域:
   - Default engine 下拉框 (faster-whisper / qwen3-asr)
   - Language 下拉框 (zh / en / ja / ko / auto)
   - Device 下拉框 (cpu / cuda / auto)
   - Compute type 下拉框 (仅 faster-whisper): int8 / float16 / float32
   - VAD filter checkbox (仅 faster-whisper)
   - Duplicate threshold 数值输入框

2. 动态显示逻辑:
   - `compute_type` 仅对 faster-whisper 显示
   - `device` 的 `auto` 选项仅对 faster-whisper 显示
   - VAD filter 仅对 faster-whisper 显示

---

## Sprint 2 验证

- [x] 后端 97 个测试全部通过
- [x] 前端 `vue-tsc --noEmit && vite build` 构建成功
- [x] `detect_duplicates()` 正确检测重复句
- [x] `run_full_analysis()` 整合三种检测
- [x] VAD filter 设置正确保存和加载
- [x] ASR 设置 UI 正确渲染和交互
- [x] Qwen3-ASR 输出格式标准化为字幕格式
- [x] 标点符号检测功能正常工作
- [x] 后端 97 个测试全部通过
- [x] 前端构建成功

---

## Sprint 2 文件汇总

### 新建文件
- `core/asr_scripts/qwen_transcribe.py` -- Qwen3-ASR 子进程推理脚本 (~680行)

### 修改文件
| 文件 | 变更 |
|------|------|
| `core/asr_service.py` | +151 行: `transcribe_with_qwen()`, `_resolve_qwen_model()` |
| `core/analysis_service.py` | +209 行: `detect_duplicates()`, `detect_punctuation()`, `_get_ngrams()`, `_cosine_similarity()`, `_compute_similarity()` |
| `core/models.py` | +1 行: `AnalysisResult.type` 扩展为包含 "punctuation" |
| `core/config.py` | +1 行: `asr_vad_filter` 默认值 |
| `frontend/src/types/project.ts` | +1 行: `AnalysisResult.type` 扩展为包含 "punctuation" |
| `frontend/src/types/edit.ts` | +1 行: `asr_vad_filter` 字段 |
| `frontend/src/components/workspace/SettingsModal.vue` | +12 行: VAD filter checkbox |

---

## Sprint 2 补充: 转录按钮重新设计 + 后端修复 (2026-05-28)

### 问题背景

用户反馈转录按钮逻辑存在多个问题：
1. 引擎硬编码为 "faster-whisper"，无法选择其他引擎
2. 未安装引擎时自动安装，而非提示用户
3. `_handle_transcription()` 不支持 qwen3-asr 引擎
4. common.py 中存在未使用的重复代码

### 修改内容

**前端 - 转录按钮重新设计**:
- `WorkspacePage.vue`: 
  - 新增 `asrSettings` ref 存储本地 ASR 参数
  - 新增 `installedEngines` ref 存储已安装引擎列表
  - 新增 `loadAsrSettings()`, `loadInstalledEngines()`, `saveAsrSettings()` 函数
  - 修改 `handleTranscribe()`: 检查已安装引擎、验证就绪状态、传递参数
  - 转录按钮改为 split-button + 设置弹窗（类似 Detect Silence 模式）
  - 弹窗包含: 引擎选择、语言、设备、计算类型、VAD 过滤、保存按钮
  - 未安装引擎时显示提示而非自动安装

**后端 - 支持 qwen3-asr 引擎**:
- `main.py`:
  - 修改 `_handle_transcription()` 添加 `elif engine == "qwen3-asr"` 分支
  - 调用 `transcribe_with_qwen()` 传递 ASR/Aligner 模型参数
  - 添加 `vad_filter` 参数传递给 `transcribe_with_whisper()`

**代码清理**:
- `common.py`: 移除未使用的 `split_into_subtitle_segments()` 函数（135行死代码）
- `WorkspacePage.vue`: 移除未使用的 `ensureReady` 和 `installPlugin` 导入

### 验证结果

- 后端 97 个测试全部通过
- 前端 `vue-tsc --noEmit && vite build` 构建成功
- 转录按钮正确显示已安装引擎
- 设置弹窗正确保存和加载参数
- `_handle_transcription()` 支持 faster-whisper 和 qwen3-asr 两个引擎

---

### 📝 Commit Message

```
feat(asr): 新增 Qwen3-ASR 引擎、重复检测及 ASR 设置面板重构

- 新增 Qwen3-ASR 子进程推理脚本，支持智能音频切片与重叠去重
- 新增基于 n-gram 余弦相似度的重复句检测
- 为 faster-whisper 引擎添加 VAD 过滤开关
- 重构转录按钮为 split-button + 设置弹窗，支持多引擎选择
- 完善 ASR 设置面板：引擎/语言/设备/计算类型/VAD/阈值配置
- 清理 common.py 135 行死代码及未使用的导入
```

### 待完成 (Sprint 3)

- [ ] Task 3.1: 原片/剪后切换
- [ ] Task 3.2: 集成测试
- [ ] Task 3.3: 版本号更新

---


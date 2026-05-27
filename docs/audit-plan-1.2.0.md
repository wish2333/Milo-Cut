# Milo-Cut v1.2.0 执行计划

> 基于审计报告 v1.2.0-rc6 + 架构师四轮审查意见制定。
>
> 核心原则：先建隔离基础设施，再通端到端 ASR 流程，最后打磨集成。

---

## 1. Sprint 划分

共 3 个 Sprint，预估总周期 5-7 周。

```
Sprint 1 (2-2.5 周) -- 插件管理 + faster-whisper ASR (P0)
Sprint 2 (1.5-2 周) -- Qwen3-ASR + VAD + 重复检测 (P1)
Sprint 3 (1-1.5 周) -- 原片/剪后切换 + 集成打磨 (P1)
```

**关键路径**: 1.1 -> 1.3 -> 1.4 -> 1.6 -> 3.2

**并行策略**: Task 2.1/2.2/2.3 可在 Task 1.1 完成后并行开发。Task 3.1 独立于其他任务。

---

## 2. Sprint 1：插件管理 + faster-whisper ASR（第 1-2.5 周）

> 目标：建立 uv 驱动的插件化隔离环境基础设施，集成第一个 ASR 引擎（faster-whisper），打通端到端转写流程。

### Task 1.1: PluginManager 后端

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 3-4 天 |
| 依赖 | 无 |
| 负责人 | 后端 |

**新建文件**: `core/plugin_manager.py`

**实施步骤**：

1. 实现 `get_data_dir()` 跨平台数据目录（Windows: `%LOCALAPPDATA%/MiloCut/`，macOS: `~/Library/Application Support/MiloCut/`，Linux: `~/.local/share/milocut/`）

2. 实现 `PluginManager` 核心类:
   - `__init__(plugins_dir)` -- 初始化目录结构 + 注册表
   - `list_plugins() -> list[PluginInfo]` -- 列出已注册插件
   - `is_installed(plugin_id) -> bool` -- 检查插件是否可用
   - `get_plugin_python(plugin_id) -> Path` -- 获取插件 venv Python 路径
   - `install_plugin(plugin_id, progress_cb)` -- uv venv + uv pip install
   - `uninstall_plugin(plugin_id)` -- 删除 venv + 注册表
   - `ensure_model(model_id, progress_cb) -> Path` -- 确保 ML 模型已下载
   - `delete_model(model_id)` -- 删除模型文件

3. 实现 `_clean_subprocess_env()` -- 清除 PyInstaller 注入的 PYTHONPATH/PYTHONHOME/LD_LIBRARY_PATH

4. 实现 `_run_uv(args)` -- 封装 uv 命令调用，使用清洁环境

5. 实现 `_get_uv_path()` -- 打包后与 exe 同目录查找 uv 二进制

6. 实现 `_detect_download_source()` -- 探测网络选择下载源（HuggingFace / ModelScope / hf-mirror）

7. 实现插件清单 `PLUGIN_REGISTRY` 字典:
   ```python
   PLUGIN_REGISTRY = {
       "plugin-whisper": {
           "display_name": "Faster Whisper ASR",
           "engine": "faster-whisper",
           "dependencies": ["faster-whisper>=1.0.0"],
           "models": {
               "Systran/faster-whisper-large-v3-turbo": {"display_name": "Large V3 Turbo (推荐)", "size_bytes": 1_500_000_000},
               "Systran/faster-whisper-base": {"display_name": "Base (轻量)", "size_bytes": 74_000_000},
           },
       },
       "plugin-qwen": {
           "display_name": "Qwen3 ASR",
           "engine": "qwen3-asr",
           "dependencies": ["transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
           "models": {
               "Qwen/Qwen3-ASR-0.6B": {"display_name": "Qwen3 ASR 0.6B", "size_bytes": 1_200_000_000},
               "Qwen/Qwen3-ForcedAligner-0.6B": {"display_name": "Qwen3 ForcedAligner 0.6B", "size_bytes": 600_000_000},
           },
       },
   }
   ```

8. 注册表持久化: `<数据目录>/registry.json`，原子写入

9. uv 交互:
   - `uv venv {venv_path} --python 3.11` -- 创建隔离环境（在线）
   - `uv venv {venv_path} --python {local_python_path}` -- 创建隔离环境（离线，使用内嵌 Python）
   - `uv pip install {packages} --python {venv_python}` -- 安装依赖

**修改文件**:
- `core/models.py` -- 新增 `PluginInfo` 模型、`PLUGIN_INSTALL` 任务类型
- `core/config.py` -- 新增 AI 设置默认值

**验收标准**:
- [ ] 单元测试: 创建 PluginManager、模拟 uv 命令、验证注册表读写
- [ ] 集成测试: 用 uv 创建空 venv 验证流程
- [ ] 跨平台数据目录正确（Windows/macOS/Linux）
- [ ] `_clean_subprocess_env()` 清除三个环境变量

---

### Task 1.2: Pydantic 模型扩展

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 0.5 天 |
| 依赖 | 无 |
| 负责人 | 全栈 |

**修改文件**: `core/models.py` + 前端类型文件

**实施步骤**：

1. 新增 `PluginInfo` 模型:
   ```python
   class PluginInfo(BaseModel, frozen=True):
       plugin_id: str
       display_name: str
       engine: Literal["faster-whisper", "qwen3-asr"]
       version: str = "1.0.0"
       status: Literal["installed", "installing", "not_installed", "error"] = "not_installed"
       installed_at: str = ""
       venv_path: str = ""
   ```

2. 新增 `ModelInfo` 模型:
   ```python
   class ModelInfo(BaseModel, frozen=True):
       model_id: str
       display_name: str
       plugin_id: str
       size_bytes: int = 0
       local_path: str = ""
       status: Literal["downloaded", "downloading", "not_downloaded"] = "not_downloaded"
   ```

3. 扩展 `AnalysisResult.type`: `"filler" | "error"` -> `"filler" | "error" | "duplicate"`

4. 新增 `PLUGIN_INSTALL = "plugin_install"` 到 `TaskType` 枚举

5. 验证已有预留字段充足: `Word`、`Segment.words`、`Segment.speaker`、`TranscriptData.engine`/`language`

**前端修改**:
- `frontend/src/types/project.ts` -- 新增 `PluginInfo`、`ModelInfo` 接口，扩展 `AnalysisResult.type`
- `frontend/src/types/task.ts` -- 新增 `"plugin_install"` 到 TaskType
- `frontend/src/types/edit.ts` -- AppSettings 新增 AI 设置字段

**验收标准**:
- [ ] `bun run build` 成功
- [ ] `uv run pytest tests/test_models.py` 通过
- [ ] 旧项目文件可正常加载（`AnalysisResult.type` 向后兼容）

---

### Task 1.3: PluginManager 桥接 API

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 1 天 |
| 依赖 | Task 1.1, Task 1.2 |
| 负责人 | 后端 |

**修改文件**: `main.py`

**实施步骤**：

1. 在 `MiloCutApi.__init__()` 中初始化 `PluginManager` 实例

2. 新增 `@expose` 桥接方法:
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

3. 注册任务处理器: `TaskType.PLUGIN_INSTALL -> _handle_plugin_install`

**验收标准**:
- [ ] 前端调用 `list_plugins` 返回两个插件（均未安装）
- [ ] 调用 `check_plugin_status("faster-whisper")` 返回所需安装信息
- [ ] 所有桥接方法返回标准 `{"success", "data", "error"}` 信封

---

### Task 1.4: faster-whisper ASR 服务

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 2-3 天 |
| 依赖 | Task 1.1, Task 1.3 |
| 负责人 | 后端 |

**新建文件**:
- `core/asr_service.py` -- 主进程侧协调层
- `core/asr_scripts/whisper_transcribe.py` -- 子进程推理脚本

**实施步骤**：

1. 实现 `run_in_plugin()` 核心方法（在 `plugin_manager.py` 中）:
   - `SubprocessTask` 状态对象 + `SubprocessState` 枚举
   - Windows 无窗口启动: `CREATE_NO_WINDOW` + `STARTUPINFO.wShowWindow=0`
   - stdin 管道用于孤儿进程防御
   - stdout 行分隔 JSON IPC
   - stderr 合并到日志文件
   - 结果写入文件（不走 stdout 管道）
   - 异常退出码分类（SIGSEGV/SIGABRT/Windows ACCESS_VIOLATION 等）

2. 实现子进程脚本公共模板:
   - `report()` 函数 -- stdout JSON 事件
   - `_stdin_watchdog()` 守护线程 -- EOF 检测 -> `os._exit(1)` 自杀

3. 实现 `asr_service.py` 协调层:
   ```python
   def transcribe_with_whisper(
       plugin_manager, media_path, ffmpeg_path,
       model_size="large-v3-turbo", language="zh",
       device="cpu", compute_type="int8",
       word_timestamps=True, vad_filter=True,
       progress_cb=None, cancel_event=None,
   ) -> dict
   ```

4. 实现 `whisper_transcribe.py` 子进程脚本:
   - 加载 WhisperModel
   - 调用 `model.transcribe()` 逐段报告进度
   - 结果写入 `result_path` 文件
   - stdin 守护线程防孤儿进程

5. 在 `main.py` 注册 `TaskType.TRANSCRIPTION` handler

**验收标准**:
- [ ] 使用短中文音频 (<30s) 测试: segments 非空、时间戳合理、Word 列表已填充
- [ ] 子进程崩溃不影响主程序
- [ ] Windows 下无控制台弹窗
- [ ] ASR 日志文件可查看
- [ ] 取消操作干净终止子进程

---

### Task 1.5: 插件管理 UI

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 2 天 |
| 依赖 | Task 1.3 |
| 负责人 | 前端 |

**新建文件**: `frontend/src/composables/usePluginManager.ts`

**修改文件**: `frontend/src/components/workspace/SettingsModal.vue`

**实施步骤**：

1. 实现 `usePluginManager` composable:
   - `plugins: ref<PluginInfo[]>` -- 已注册插件列表
   - `models: ref<ModelInfo[]>` -- 已下载模型列表
   - `listPlugins()` -- 调用 `list_plugins` 桥接
   - `installPlugin(pluginId)` -- 调用 `install_plugin`，监听进度事件
   - `uninstallPlugin(pluginId)` -- 调用 `uninstall_plugin`
   - `downloadModel(modelId)` / `deleteModel(modelId)`
   - `ensureReady(engine)` -- 检查插件+模型，必要时提示安装

2. SettingsModal 新增 "AI 引擎" 区域:
   - 插件列表: 名称、引擎类型、版本、状态标签
   - 安装/卸载按钮
   - 已安装插件展开: 关联模型列表 + 下载/删除按钮
   - 安装进度条（通过 `task:progress` 事件更新）

**验收标准**:
- [ ] 打开设置页看到 AI 引擎区域
- [ ] 两个插件均显示 "未安装"
- [ ] 点击安装 faster-whisper，验证进度条和完成状态

---

### Task 1.6: ASR UI 集成

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 1-2 天 |
| 依赖 | Task 1.4, Task 1.5 |
| 负责人 | 前端 |

**修改文件**:
- `frontend/src/composables/useAnalysis.ts`
- `frontend/src/pages/WorkspacePage.vue`

**实施步骤**：

1. `useAnalysis.ts` 扩展:
   - 新增 `runTranscription()` -- 先 `ensureReady(engine)`，再 `createTask("transcription")` + `startTask`
   - 更新 `ANALYSIS_TASKS` 包含 `"transcription"`

2. `WorkspacePage.vue` 集成:
   - 工具栏新增 "转写" 按钮（位于 "导入 SRT" 和 "检测静音" 之间）
   - 按钮状态: 禁用（isDetecting/isExporting）、转写中（进度显示）
   - 转写完成后项目自动更新
   - 首次使用时弹出插件安装确认对话框

**验收标准**:
- [ ] 加载含中文音频的项目 -> 点击 "转写" -> 首次弹出安装确认 -> 安装+下载完成后自动转写 -> 时间线显示字幕段
- [ ] 转写中按钮显示进度，其他操作按钮禁用

---

## 3. Sprint 2：Qwen3-ASR + VAD + 重复检测（第 3-4.5 周）

> 目标：集成第二个 ASR 引擎、VAD 增强和重复句检测。

### Task 2.1: Qwen3-ASR 转写服务

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 3-4 天 |
| 依赖 | Task 1.1 |
| 负责人 | 后端 |

**新建文件**: `core/asr_scripts/qwen_transcribe.py`

**修改文件**: `core/asr_service.py`

**实施步骤**：

1. 实现 `transcribe_with_qwen()` 协调函数（与 whisper 版本类似，但需确保两个模型都下载）

2. 实现 `qwen_transcribe.py` 子进程脚本:
   - 加载 Qwen3-ASR 模型 + Qwen3-ForcedAligner
   - 长音频智能切片（`smart_slice_audio`）:
     - 累积音频到 ~280s（ACCUMULATE_THRESHOLD）后在最佳静音点切割
     - 全程无静音点时强制 240s 均匀切割
     - 切片间保留 0.5s 重叠区（SLICE_OVERLAP）防漏字
   - 逐片 ASR 推理 + 强制对齐
   - 时间戳重映射 + 重叠区去重（利用有效内容区间剔除重复字词）
   - 结果写入文件

3. 进度报告:
   - 0-10%: 插件环境检查/安装
   - 10-20%: 模型加载（ASR + 对齐器）
   - 20-60%: ASR 推理
   - 60-80%: 强制对齐
   - 80-100%: 结果解析

**验收标准**:
- [ ] 短中文音频测试: 字级时间戳精度
- [ ] 长音频 (>5min) 自动切片 + 时间戳正确重映射
- [ ] 切片边界处无漏字（重叠区机制生效）
- [ ] 对比 faster-whisper 输出验证一致性

---

### Task 2.2: VAD 增强

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 0.5 天 |
| 依赖 | Task 1.4 |
| 负责人 | 全栈 |

**实现方式**: 复用 faster-whisper 内置 Silero VAD（`vad_filter=True`），**不在主程序中引入任何 VAD 依赖**。

**修改文件**:
- `core/asr_scripts/whisper_transcribe.py` -- 传递 `vad_filter` 参数
- `frontend/src/components/workspace/SettingsModal.vue` -- ASR 设置中新增 VAD 过滤开关

**验收标准**:
- [ ] 对噪声环境音频，`vad_filter=True` 减少幻觉文本
- [ ] 设置页 VAD 开关正常工作

---

### Task 2.3: 重复句检测

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 1-2 天 |
| 依赖 | Task 1.1 |
| 负责人 | 后端 |

**修改文件**:
- `core/analysis_service.py` -- 新增 `detect_duplicates()`
- `core/config.py` -- 新增 `duplicate_threshold` 和 `duplicate_min_length` 设置

**实施步骤**：

1. 实现语言自适应 n-gram 余弦相似度:
   - 中文 (`zh-*`): 字符级 3-gram
   - 英文/西文: 词级 2-gram（先按空格分词）
   - 其他/未知: 默认字符级 3-gram

2. 滑动窗口约束:
   - `window_size=50` -- 每段只与后续 50 段比较
   - `time_window_sec=300` -- 只比较 5 分钟内的段
   - 复杂度 O(n * 50)，1000 段仅需 ~50000 次比较

3. 更新 `run_full_analysis()` 包含重复检测

**验收标准**:
- [ ] 构造含重复句的测试 segments，验证检测正确
- [ ] 相似但不同主题的段不被标记
- [ ] 中文字符 3-gram 和英文词级 2-gram 均正确工作

---

### Task 2.4: ASR 设置 UI

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 1 天 |
| 依赖 | Task 1.5 |
| 负责人 | 前端 |

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue`
- `frontend/src/types/edit.ts`

**实施步骤**：

1. AppSettings 新增字段:
   - `asr_engine: "faster-whisper" | "qwen3-asr"` -- 默认引擎
   - `asr_model_size: string` -- 模型大小
   - `asr_language: string` -- 语言
   - `asr_device: "cpu" | "cuda" | "auto"` -- 推理设备
   - `asr_compute_type: "int8" | "float16" | "float32"` -- 计算精度（faster-whisper 专用）
   - `duplicate_threshold: number` -- 重复检测阈值 (0.5-1.0)
   - `duplicate_min_length: number` -- 最小段长度

2. SettingsModal 新增 "ASR / AI" 区域:
   - 引擎选择下拉框
   - 模型大小下拉框（选项随引擎联动）
   - 语言/设备/计算精度下拉框
   - 重复检测阈值滑块

**验收标准**:
- [ ] 修改设置 -> 保存 -> 重启验证持久化
- [ ] 切换引擎后选项联动更新

---

## 4. Sprint 3：原片/剪后切换 + 集成打磨（第 5-6 周）

> 目标：原片/剪后切换预览、端到端集成测试、构建更新。

### Task 3.1: 原片/剪后切换预览

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 2-3 天 |
| 依赖 | 无 |
| 负责人 | 前端 |

**修改文件**:
- `frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/export/PreviewPlayer.vue`

**实施步骤**：

1. WorkspacePage:
   - 新增 `previewMode: ref<"edited" | "original">("edited")`
   - edited 模式跳过已确认删除段，original 模式不跳过
   - 进度条: original 模式下删除段用半透明红色显示
   - 控制栏新增切换按钮

2. PreviewPlayer（导出页）:
   - 同样新增 `previewMode` 和切换按钮

3. 快捷键: `Shift+Space` 切换模式

4. 性能设计 -- 轻量级事件监听开关:
   - 单视频流 + 动态事件监听开关，不重建底层播放轨
   - edited 模式: 激活 `timeupdate` 监听，检测到进入删除段时立即 seek
   - original 模式: `removeEventListener` 移除监听
   - 切换时仅切换监听器和 UI 标记，不重建视频源

**验收标准**:
- [ ] 加载含已确认删除段的项目 -> 播放（edited 自动跳过）-> 切换 original（完整播放）-> 切换回来（恢复跳过）
- [ ] 切换无画面闪烁，低配机器流畅

---

### Task 3.2: 集成测试与打磨

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 2-3 天 |
| 依赖 | 所有功能完成 |
| 负责人 | 全栈 |

**测试矩阵**:

| 场景 | 引擎 | 预期结果 |
|------|------|---------|
| 中文普通话短视频 (<1min) | faster-whisper | 字幕段 + 词级时间戳 |
| 中文普通话长视频 (>10min) | faster-whisper | 进度报告 + 可取消 |
| 中文方言（粤语） | Qwen3-ASR | 正确识别方言 |
| 带背景音乐 | Qwen3-ASR | 正常转写 |
| 噪声环境静音检测 | VAD | 检出短暂停顿 |
| 重复句项目 | 全分析 | 标记重复段 |
| 插件安装失败 | -- | 优雅错误提示 |
| 模型下载失败 | -- | 优雅错误提示 |
| 无 GPU 设备 | CPU | 正常推理（较慢） |
| 插件卸载后重装 | -- | 干净重建 |

**验收标准**:
- [ ] 全部测试矩阵场景通过
- [ ] 后端测试全部通过
- [ ] 前端构建成功
- [ ] 设置持久化正常

---

### Task 3.3: 依赖更新与构建

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 1 天 |
| 依赖 | Task 3.2 |
| 负责人 | 全栈 |

**修改文件**:
- `pyproject.toml` -- 版本号更新为 1.2.0
- `frontend/package.json` -- 版本号更新为 1.2.0
- `build.py` -- PyInstaller 配置嵌入 uv 二进制

**关键**: 主程序 pyproject.toml **不新增** ASR 相关依赖。ASR 依赖由插件管理器通过 uv 在隔离环境中按需安装。

PyInstaller 打包配置:
```python
--add-data "uv.exe;."  # Windows
--add-data "uv:."      # macOS
```

**验收标准**:
- [ ] `uv run dev.py` 无导入错误
- [ ] `bun run build` 成功
- [ ] `uv run build.py` 生成可执行文件，体积不显著增加（~50MB，不含 ASR 依赖）

---

## 5. 任务依赖关系

```
1.1 PluginManager Backend ─────┐
1.2 Pydantic Model Extensions ─┤
                                ├── 1.3 PluginManager Bridge API ──┐
                                │                                   │
                                │   1.4 faster-whisper ASR ─────────┤
                                │                                   ├── 1.6 ASR UI
                                │   1.5 Plugin Management UI ───────┤
                                │                                   │
2.1 Qwen3-ASR Service ─────────┤                                   │
2.2 VAD Enhancement ───────────┤                                   │
2.3 Duplicate Detection ───────┤                                   │
                                ├── 2.4 ASR Settings UI ────────────┤
                                                                3.1 Preview Toggle
                                                                3.2 Integration Test
                                                                3.3 Build Updates
```

**关键路径**: 1.1 -> 1.3 -> 1.4 -> 1.6 -> 3.2

**并行策略**:
- Task 1.1 / 1.2 可并行
- Task 2.1 / 2.2 / 2.3 可在 Task 1.1 完成后并行
- Task 3.1 完全独立

---

## 6. 风险与缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| PyInstaller 环境变量污染子进程 | 高 | 中 | `_clean_subprocess_env()` 清除 PYTHONPATH/PYTHONHOME/LD_LIBRARY_PATH |
| 孤儿进程残留 | 高 | 中 | stdin EOF 守护线程: 主进程退出 -> EOF -> `os._exit(1)` 自杀 |
| 大体积结果撑爆 stdout 管道 | 中 | 中 | 结果写入文件，stdout 仅传路径 |
| C 扩展崩溃 / GPU OOM | 高 | 中 | returncode 分类: SIGSEGV/SIGABRT/Windows 异常码 -> 针对性提示 |
| Windows MAX_PATH 路径超限 | 中 | 中 | 检测 LongPathsEnabled + 子目录压平 |
| 离线环境插件安装失败 | 高 | 中 | 内嵌 Python 解释器 + `uv venv --python <本地路径>` |
| Qwen 切片边界漏字 | 中 | 中 | 0.5s 重叠区 + 有效内容区间去重 |
| Qwen 切片无静音点 | 中 | 低 | 强制 240s 均匀切割兜底 |
| 重复检测 O(n^2) | 中 | 中 | 滑动窗口 (50段 + 5分钟) -> O(n*50) |
| 多语言 n-gram 精度下降 | 中 | 低 | 语言自适应: 中文字符 3-gram / 英文词级 2-gram |

---

## 7. 新增文件汇总

| 文件 | Sprint | 用途 |
|------|--------|------|
| `core/plugin_manager.py` | 1 | uv 驱动的插件生命周期管理（venv + 依赖 + 模型 + 子进程 IPC） |
| `core/asr_service.py` | 1-2 | ASR 转写协调层（安装检查 -> 模型下载 -> 子进程调用） |
| `core/asr_scripts/whisper_transcribe.py` | 1 | faster-whisper 子进程推理脚本 |
| `core/asr_scripts/qwen_transcribe.py` | 2 | Qwen3-ASR 子进程推理脚本（含长音频切片、时间戳重映射） |
| `frontend/src/composables/usePluginManager.ts` | 1 | 前端插件管理 composable |

---

## 8. 修改文件汇总

| 文件 | Sprint | 变更 |
|------|--------|------|
| `core/models.py` | 1 | 新增 `PluginInfo`、`ModelInfo`、`PLUGIN_INSTALL`、扩展 `AnalysisResult.type` |
| `core/config.py` | 1-2 | 新增 AI 设置（asr_engine, model_size, language, duplicate_threshold 等） |
| `core/analysis_service.py` | 2 | 新增 `detect_duplicates()`，更新 `run_full_analysis()` |
| `main.py` | 1-2 | 注册 TRANSCRIPTION/VAD_ANALYSIS/PLUGIN_INSTALL handler，新增桥接方法 |
| `build.py` | 3 | PyInstaller 配置嵌入 uv 二进制 |
| `frontend/src/types/project.ts` | 1 | 新增 `PluginInfo`、`ModelInfo`，扩展 `AnalysisResult.type` |
| `frontend/src/types/task.ts` | 1 | 新增 `"plugin_install"` |
| `frontend/src/types/edit.ts` | 1-2 | AppSettings 新增 AI 设置字段 |
| `frontend/src/composables/useAnalysis.ts` | 1-2 | 新增 `runTranscription()` |
| `frontend/src/components/workspace/SettingsModal.vue` | 1-2 | 新增 AI 插件管理区域 + ASR 设置区域（含 VAD 过滤开关） |
| `frontend/src/pages/WorkspacePage.vue` | 1-3 | 新增转写按钮、原片/剪后切换 |
| `frontend/src/components/export/PreviewPlayer.vue` | 3 | 新增原片/剪后切换 |

---

## 9. 验收检查清单

### P0 验收（Sprint 1）

- [ ] 设置页 AI 引擎区域显示已注册插件列表（faster-whisper、Qwen3-ASR）
- [ ] 首次使用 ASR 时弹出插件安装确认对话框（含磁盘空间预检）
- [ ] 插件安装使用 uv 创建隔离环境，进度实时显示
- [ ] 插件安装完成后自动下载 ML 模型（可选）
- [ ] faster-whisper 转写产生字幕段 + 词级时间戳
- [ ] ASR 子进程运行时无控制台弹窗（Windows）
- [ ] 主进程关闭/崩溃时子进程自动退出（无孤儿进程残留）
- [ ] ASR 日志文件可查看（`get_asr_log` / `list_asr_logs`）
- [ ] 插件安装/卸载不影响主程序稳定性
- [ ] 主程序打包体积不因 ASR 功能显著增加

### P1 验收（Sprint 2）

- [ ] faster-whisper VAD 过滤开关正常工作（`vad_filter=True`）
- [ ] Qwen3-ASR 转写支持中文方言
- [ ] Qwen3-ForcedAligner 提供字级对齐时间戳
- [ ] 长音频（>5 分钟）Qwen 转写自动切片 + 时间戳正确重映射
- [ ] 重复句检测正确标记重复段
- [ ] 全分析（静音+口头禅+口误+重复）正常运行
- [ ] 国内网络自动切换 ModelScope/hf-mirror 下载源
- [ ] 模型下载失败时显示友好错误提示
- [ ] 无 GPU 设备时 CPU 推理正常
- [ ] 设置持久化正常

### P1 验收（Sprint 3）

- [ ] 原片/剪后切换预览正常工作
- [ ] 后端测试全部通过
- [ ] 前端构建成功
- [ ] PyInstaller 打包成功，体积不显著增加

---

## 附录：架构师技术修正记录

> 以下修正来自架构师四轮审查，已全部消化吸收至对应任务。

### 修正 1：sys.path 注入 -> 子进程 IPC（根本性架构变更）

**问题**: CTranslate2 和 PyTorch 的 C 扩展在同一内存空间内极易导致 Segmentation Fault。PyInstaller 冻结进程的 importlib 和 sys.path 已被高度定制，注入外部原生二进制包会触发符号冲突。

**修正**: 所有 ASR 推理**必须**在插件 venv 的独立子进程中执行，通过 stdout JSON 流 IPC 通信。

**已更新**: Task 1.4、Section 4.7。

### 修正 2：孤儿进程防御（stdin EOF 守护线程）

**问题**: 主进程崩溃/用户强关窗口时，子进程成为孤儿进程持续消耗资源。

**修正**: 子进程启动 stdin 守护线程，阻塞读取 stdin；主进程退出时 stdin 管道关闭（EOF），子进程检测到 EOF 后调用 `os._exit(1)` 自杀。

**已更新**: Task 1.4 子进程脚本模板。

### 修正 3：结果文件输出（避免管道溢出）

**问题**: ASR 词级/字级时间戳数据量极大（5-10MB），直接通过 stdout 管道传输可能导致操作系统缓冲区写满，子进程和主进程双向死锁。

**修正**: 子进程将大体积 JSON 写入 `tasks/{task_id}_result.json` 文件，stdout 仅传递 `{"type":"result","status":"saved","path":"..."}` 路径引用。

**已更新**: Task 1.4、Task 2.1。

### 修正 4：Qwen 累积式智能切片 + 重叠区

**问题**: 简单的等长硬切或在每个静音点切割会导致切片过小，丢失 ASR 上下文语义连贯性。切片边界处因缺乏前后文容易漏字。

**修正**: 累积音频到 ~280s 后在最佳静音点切割；无静音点时强制 240s 均匀切割；切片间保留 0.5s 重叠区，时间戳重映射时利用有效内容区间剔除重叠区重复字词。

**已更新**: Task 2.1。

### 修正 5：移除主进程 VAD 依赖

**问题**: silero-vad 包依赖 torch (~2GB)，包含在主程序中会破坏 ~50MB 包大小目标。

**修正**: 不在主程序中引入任何 VAD 依赖，仅复用 faster-whisper 内置的 `vad_filter=True`。

**已更新**: Task 2.2。

### 修正 6：重复检测多语言自适应

**问题**: 字符级 3-gram 对英文会拆碎单词，降低语义重复捕捉准确度。

**修正**: `detect_duplicates()` 感知 `TranscriptData.language`，中文用字符 3-gram，英文/西文用词级 2-gram。

**已更新**: Task 2.3。

### 修正 7：C 扩展崩溃 / OOM 退出码分类

**问题**: PyTorch/CUDA OOM 触发 Segmentation Fault，Python 无法捕获，通用错误提示无指导意义。

**修正**: `run_in_plugin` 对异常 returncode 分类（SIGSEGV/SIGABRT/Windows 异常码），前端弹出针对性提示。

**已更新**: Task 1.4。

### 修正 8：离线 Python 解释器内嵌

**问题**: `uv venv --python 3.11` 在离线环境会尝试从 PyBI 下载 Python，导致失败。

**修正**: 离线分发包内嵌预下载的目标平台 Python 解释器压缩包，通过 `uv venv --python <本地路径>` 强制指定。

**已更新**: Task 1.1。

---

*制定人：代码执行负责人*
*审核人：架构师*
*制定日期：2026-05-27*
*版本：v1.0（含架构师四轮审查修正）*
*基于审计报告 v1.2.0-rc6*

# Milo-Cut 1.2.0 Audit Report -- AI 赋能引入

> 基于 v1.1.0 完成状态和 PRD-1.1.0 中 v1.2.0 路线图，评估实现方案、任务拆解和技术风险。

---

## 1. 版本概述

| 项目 | 内容 |
|------|------|
| 版本号 | v1.2.0 |
| 主题 | AI 赋能引入 |
| 基线 | v1.1.0 (已完成，18/18 任务，8/8 验收标准) |
| 预估周期 | 5-7 周 |
| 核心交付 | 双引擎 ASR 转写 + VAD 增强静音检测 + 重复句检测 + 原片/剪后切换预览 |

---

## 2. v1.1.0 基础设施就绪度

v1.1.0 为 v1.2.0 预留了完整的扩展点：

| 预留项 | 状态 | v1.2.0 利用方式 |
|--------|------|----------------|
| `TaskType.TRANSCRIPTION` 枚举 | 已声明，无 handler | 注册 ASR 任务处理器 |
| `TaskType.VAD_ANALYSIS` 枚举 | 已声明，无 handler | 注册 VAD 任务处理器 |
| `TranscriptData.engine` 字段 | 默认 "srt" | ASR 完成后设为引擎名 |
| `TranscriptData.language` 字段 | 默认 "zh-CN" | ASR 语言标识 |
| `Segment.speaker` 字段 | 空字符串 | v1.2.0 暂不使用（v2.0 说话人分离） |
| `Word` 模型 + `Segment.words` | 未填充 | ASR 词级时间戳数据结构 |
| `AnalysisResult.type` 联合类型 | "filler" / "error" | 扩展添加 "duplicate" |
| `EditDecision.source` / `analysis_id` | 已定义 | 关联回 ASR/分析来源 |
| `SettingsModal.vue` 设置页 | 已实现 FFmpeg/静音检测/导出设置 | 新增 AI 模型管理和 ASR 设置区域 |

**结论**：所有 v1.2.0 所需的数据模型扩展点已就绪，无需破坏性 schema 变更。

---

## 3. 架构决策

### 3.1 核心问题：重型依赖的隔离管理

v1.2.0 引入的 ASR 引擎依赖链极重：

| 引擎 | 依赖包 | 体积 |
|------|--------|------|
| faster-whisper | `ctranslate2`, `faster-whisper` | ~150MB |
| Qwen3-ASR | `torch`, `transformers`, `accelerate` | ~2-4GB |

如果将这些依赖打入主程序包，安装包将膨胀到数 GB，且不同引擎的依赖可能互相冲突。

### 3.2 方案选型：uv 驱动的插件化隔离环境

采用 **插件化架构 + uv 隔离环境** 方案：

| 方案 | 打包体积 | 隔离性 | 安装速度 | 复杂度 |
|------|---------|--------|---------|--------|
| 全部打入主包 | ~4GB | 无 | 无需额外安装 | 低 |
| pip 按需安装 | 不变 | 差（易污染） | 慢 | 中 |
| **uv 隔离环境** | **不变** | **完美** | **极快（10-100x pip）** | **中** |

**核心设计**：

```
Milo-Cut 主程序 (pyproject.toml)
  ├── 核心依赖: pywebview, pydantic, loguru, opentimelineio
  ├── uv 二进制 (~5MB, 随主程序分发)
  └── ASR 插件 (首次使用时按需安装)
       ├── plugin-whisper: uv venv -> faster-whisper + ctranslate2
       └── plugin-qwen:    uv venv -> torch + transformers
```

**关键优势**：
- 主程序打包体积不变（~50MB），ASR 依赖完全不打入
- 每个 ASR 引擎运行在独立的 uv 虚拟环境中，互不冲突
- uv 安装速度比 pip 快 10-100 倍，用户首次等待时间从分钟级降到秒级
- uv 是单个二进制文件（~5MB），可直接嵌入打包目录
- 隔离环境放在用户目录（`~/.milo-cut/plugins/`），不污染系统 Python
- PyInstaller 打包后兼容性优于 pip（无路径/权限错误）

### 3.3 双引擎 ASR 方案

| 引擎 | 包 | 推理框架 | 模型大小 | 特点 |
|------|-----|---------|---------|------|
| **faster-whisper** | `faster-whisper` | CTranslate2 | 144MB-3GB (按模型大小) | 4x 快于原版 Whisper，内置 Silero VAD，原生词级时间戳 |
| **Qwen3-ASR** | `transformers` + `torch` | PyTorch (CUDA/CPU) | ~1.2B-3.4B 参数 | 52 语言 + 22 中文方言，SOTA 级中文 ASR |

### 3.4 faster-whisper

- **包**: `faster-whisper` (PyPI)
- **依赖**: `ctranslate2>=4.0`, `huggingface-hub>=0.13`, `tokenizers>=0.13`
- **模型**: HuggingFace Hub 自动下载（Systran/faster-whisper-* 系列）
- **模型选择**:
  - `base` (74MB) -- 快速原型，准确率一般
  - `small` (244MB) -- 平衡选择
  - `medium` (769MB) -- 高准确率
  - `large-v3` (3GB) -- 最高准确率
  - `large-v3-turbo` (1.5GB) -- 推荐：接近 large 准确率，速度更快
- **词级时间戳**: 原生支持 `word_timestamps=True`
- **VAD 集成**: 内置 Silero VAD 过滤（`vad_filter=True`）
- **语言**: 自动检测或手动指定

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
segments, info = model.transcribe("audio.wav", language="zh", word_timestamps=True, vad_filter=True)

for segment in segments:
    for word in segment.words:
        print(f"[{word.start:.2f}s -> {word.end:.2f}s] {word.word}")
```

### 3.5 Qwen3-ASR + ForcedAligner

- **模型**: `Qwen/Qwen3-ASR-0.6B` (轻量) 或 `Qwen/Qwen3-ASR-1.7B` (高精度)
- **对齐模型**: `Qwen/Qwen3-ForcedAligner-0.6B`
- **框架**: `transformers` + `torch`（标准 PyTorch 推理，支持 CPU/CUDA）
- **许可**: Apache 2.0
- **特点**:
  - 30 语言 + 22 中文方言（粤语、闽南语、吴语等）
  - 支持语音、歌唱、带背景音乐的音频
  - 非自回归强制对齐器，支持词/字级时间戳
  - 对齐精度超越 NeMo-Forced-Aligner、WhisperX、Monotonic-Aligner
  - 最大单次推理 5 分钟音频（对齐器）/ 20 分钟（ASR）

```python
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

# ASR 转写
model = AutoModelForSpeechSeq2Seq.from_pretrained("Qwen/Qwen3-ASR-0.6B")
processor = AutoProcessor.from_pretrained("Qwen/Qwen3-ASR-0.6B")
# ... 推理流程

# 强制对齐
from qwen3_asr import Qwen3ForcedAligner
aligner = Qwen3ForcedAligner.from_pretrained("Qwen/Qwen3-ForcedAligner-0.6B")
results = aligner.align(audio="audio.wav", text="转写文本", language="Chinese")
# results 包含字/词级 start_time, end_time
```

### 3.6 引擎选择策略

| 场景 | 推荐引擎 | 理由 |
|------|---------|------|
| 中文普通话口播 | faster-whisper large-v3-turbo | 速度快，准确率高，原生时间戳 |
| 中文方言（粤语/闽南语等） | Qwen3-ASR-1.7B | 22 种方言覆盖 |
| 多语言混合 | Qwen3-ASR-1.7B | 52 语言自动检测 |
| 带背景音乐/歌唱 | Qwen3-ASR | 专门优化 |
| CPU 低配设备 | faster-whisper base/small | CTranslate2 高效推理 |
| GPU 设备 | Qwen3-ASR + PyTorch CUDA | 标准推理，FP16 加速 |

用户在设置页选择默认引擎，支持随时切换。

---

## 4. 插件化架构设计

### 4.1 目录结构（跨平台规范）

数据目录遵循各平台规范，避免在用户根目录创建 dotfile：

| 平台 | 路径 |
|------|------|
| Windows | `%LOCALAPPDATA%/MiloCut/`（如 `C:\Users\xxx\AppData\Local\MiloCut\`） |
| macOS | `~/Library/Application Support/MiloCut/` |
| Linux | `~/.local/share/milocut/` |

```python
def get_data_dir() -> Path:
    """获取跨平台数据目录。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "MiloCut"
```

```
<MiloCut 数据目录>/                  # get_data_dir() 返回值
  plugins/
  plugins/
    plugin-whisper/                    # faster-whisper 插件环境
      venv/                            # uv 创建的虚拟环境
        Scripts/python.exe             # 独立 Python 解释器
        Lib/site-packages/             # 隔离的包
      manifest.json                    # 插件清单
    plugin-qwen/                       # Qwen3-ASR 插件环境
      venv/
      manifest.json
  models/                              # ML 模型文件（插件共享）
    faster-whisper/
      large-v3-turbo/                  # CTranslate2 模型
    qwen3-asr/
      Qwen3-ASR-0.6B/                 # HuggingFace 模型
    qwen3-aligner/
      Qwen3-ForcedAligner-0.6B/
  logs/                                # ASR 子进程日志（每次运行一个文件）
    asr_task_001_20260528_143022.log
    asr_task_002_20260528_150512.log
  registry.json                        # 插件+模型注册表

项目源码（新增）:
  core/
    plugin_manager.py                  # 插件生命周期 + 子进程 IPC
    asr_service.py                     # ASR 转写协调层
    asr_scripts/                       # 子进程推理脚本（在插件 venv 中执行）
      whisper_transcribe.py            # faster-whisper 推理（含 stdin 守护、结果写文件）
      qwen_transcribe.py               # Qwen3-ASR 推理（含长音频切片、时间戳重映射）
```

### 4.2 插件清单 (manifest.json)

```json
{
  "plugin_id": "plugin-whisper",
  "display_name": "Faster Whisper ASR",
  "engine": "faster-whisper",
  "version": "1.0.0",
  "dependencies": [
    "faster-whisper>=1.0.0",
    "ctranslate2>=4.0"
  ],
  "models": [
    {
      "model_id": "Systran/faster-whisper-large-v3-turbo",
      "display_name": "Large V3 Turbo (推荐)",
      "size_bytes": 1500000000
    },
    {
      "model_id": "Systran/faster-whisper-base",
      "display_name": "Base (轻量)",
      "size_bytes": 74000000
    }
  ],
  "python_requires": ">=3.11",
  "installed_at": "2026-05-28T00:00:00Z",
  "status": "installed"
}
```

### 4.3 PluginManager 核心 API

```python
class PluginManager:
    """基于 uv 的插件化 ASR 引擎管理器。

    所有 ASR 推理均在插件子进程中执行（IPC 模式），
    避免 C 扩展冲突和 PyInstaller 冻结环境污染。
    """

    def __init__(self, plugins_dir: Path):
        self.plugins_dir = plugins_dir
        self.registry = self._load_registry()

    # -- 生命周期 --
    def list_plugins(self) -> list[PluginInfo]:
        """列出所有已注册的插件及其状态。"""

    def is_installed(self, plugin_id: str) -> bool:
        """检查插件环境是否已创建且依赖已安装。"""

    def get_plugin_python(self, plugin_id: str) -> Path:
        """获取插件 venv 的 Python 解释器路径。"""

    # -- 安装/卸载 --
    def install_plugin(self, plugin_id: str, progress_cb=None) -> dict:
        """创建 uv venv 并安装插件依赖。

        在线模式: uv venv --python 3.11 (自动从 PyBI 下载)
        离线模式: uv venv --python <内嵌Python路径> (使用离线分发包中预置的解释器)
        """
        # 1. 检测网络状态，决定 Python 来源
        # 2. uv venv {venv_path} --python {python_source}
        # 3. uv pip install {packages} --python {venv_python}
        # 4. 更新 registry.json

    def uninstall_plugin(self, plugin_id: str) -> dict:
        """删除插件虚拟环境和注册表条目。"""

    # -- 模型管理 --
    def ensure_model(self, model_id: str, progress_cb=None) -> Path:
        """确保 ML 模型已下载，返回本地路径。"""

    def delete_model(self, model_id: str) -> dict:
        """删除已下载的模型文件。"""

    # -- 运行时（子进程 IPC） --
    def run_in_plugin(
        self, plugin_id: str, script: str, args: dict,
        progress_cb: Callable | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict:
        """在插件子进程中执行 ASR 脚本，通过 stdout JSON 流通信。

        子进程输出格式：
          {"type": "progress", "value": 0.35}
          {"type": "result", "data": {...}}

        取消时直接 terminate 子进程，不污染主进程内存。
        """
```

### 4.4 uv 命令调用封装与子进程环境隔离

```python
def _clean_subprocess_env(self) -> dict:
    """清除 PyInstaller 注入的环境变量，防止子进程环境污染。

    PyInstaller 打包后会设置 PYTHONPATH/PYTHONHOME/LD_LIBRARY_PATH，
    这些变量会干扰 uv 和插件 venv 的 Python 解释器正常工作。
    """
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("LD_LIBRARY_PATH", None)
    return env

def _run_uv(self, args: list[str], verbose=False) -> bool:
    """调用 uv 二进制，跨平台兼容，使用清洁环境。"""
    uv_path = self._get_uv_path()
    try:
        result = subprocess.run(
            [str(uv_path)] + args,
            capture_output=True, text=True, check=True,
            env=self._clean_subprocess_env(),  # 关键：隔离 PyInstaller 环境
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"uv command failed: {e.stderr}")
        return False

def _get_uv_path(self) -> Path:
    """获取 uv 二进制路径（打包后与 exe 同目录）。"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / ("uv.exe" if sys.platform == "win32" else "uv")
    else:
        return Path(shutil.which("uv") or "uv")
```

### 4.5 插件安装流程

```
用户触发 ASR -> check_plugin_status(engine)
  -> 插件已安装 -> 直接启动子进程推理
  -> 插件未安装 -> 弹出确认对话框（显示依赖大小）
    -> 磁盘空间预检（不足则拦截并提示）
    -> 确认 -> 创建 PLUGIN_INSTALL 任务
      -> uv venv 创建隔离环境 (秒级)
      -> uv pip install 依赖 (10-100x 快于 pip)
      -> 进度事件推送
      -> 安装完成 -> 启动子进程推理
    -> 取消 -> 返回
```

### 4.6 模型下载流程（多源 + 空间预检）

```
插件已安装 -> ensure_model(model_id)
  -> 模型已下载 -> 返回本地路径
  -> 模型未下载 -> 磁盘空间预检
    -> 空间不足 -> 友好提示，拦截下载
    -> 空间充足 -> 弹出确认对话框（显示大小 + 预估时间）
      -> 确认 -> 探测网络环境选择下载源
        -> 中国大陆 -> ModelScope (modelscope.cn) 或 hf-mirror.com
        -> 其他 -> HuggingFace Hub
        -> 下载进度事件
        -> 完成 -> 返回路径
      -> 取消 -> 返回
```

**多源下载实现**:
```python
MODEL_SOURCES = {
    "huggingface": "https://huggingface.co/{model_id}",
    "modelscope": "https://modelscope.cn/api/v1/models/{model_id}",
    "hf-mirror": "https://hf-mirror.com/{model_id}",
}

def _detect_download_source(self) -> str:
    """探测网络环境，自动选择最优下载源。"""
    # 尝试 HuggingFace，超时则回退到 ModelScope/hf-mirror
    # 在 manifest.json 中配置 download_url_alias 支持自定义
```

### 4.7 子进程 IPC 协议（stdout JSON 流）

**架构决策**：ASR 推理**必须**在插件 venv 的独立子进程中执行，**禁止**通过 `sys.path` 注入在同一进程内加载。

**原因**（架构师审查结论）：
1. **C 扩展冲突**：CTranslate2 和 PyTorch 的 C 扩展、OpenMP 线程库、CUDA 运行时在同一内存空间内极易导致 Segmentation Fault
2. **PyInstaller 冻结环境污染**：冻结进程的 `importlib` 和 `sys.path` 已被高度定制，注入外部原生二进制包会触发符号冲突
3. **进程隔离 = 故障隔离**：子进程崩溃不影响主程序，kill 即清理

**IPC 协议设计**（stdout 行分隔 JSON）：

#### 子进程生命周期状态机

```
pending -> running -> completed
                   -> failed
                   -> cancelled
```

每个子进程运行对应：
- 一个 `SubprocessTask` 状态对象（主进程内存）
- 一个日志文件 `<数据目录>/logs/asr_{task_id}.log`（持久化）
- 一个结果文件 `<数据目录>/tasks/{task_id}_result.json`（大体积转写结果）
- 一条 stdin 管道（孤儿进程防御）

#### 子进程管理器

```python
import subprocess
import sys
import json
import threading
from pathlib import Path
from datetime import datetime
from enum import Enum

class SubprocessState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class SubprocessTask:
    """管理单个插件子进程的完整生命周期。"""

    def __init__(self, task_id: str, log_dir: Path):
        self.task_id = task_id
        self.state = SubprocessState.PENDING
        self.proc: subprocess.Popen | None = None
        self.result: dict = {}
        self.error: str = ""
        self.log_path = log_dir / f"asr_{task_id}_{datetime.now():%Y%m%d_%H%M%S}.log"
        self._log_file = None
        self._cancel_event = threading.Event()

    def cancel(self):
        """请求取消：terminate 子进程 + 标记状态。"""
        self._cancel_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    @property
    def is_active(self) -> bool:
        return self.state in (SubprocessState.PENDING, SubprocessState.RUNNING)
```

#### run_in_plugin 实现

```python
def run_in_plugin(
    self, plugin_id: str, script_path: str, args: dict,
    task_id: str,
    progress_cb: Callable | None = None,
) -> SubprocessTask:
    """在插件子进程中执行 ASR 脚本。

    - 子进程无窗口启动（Windows CREATE_NO_WINDOW）
    - stdout: JSON 流式 IPC（进度 + 结果）
    - stderr + stdout 同时写入日志文件，可事后查看
    - 子进程状态通过 SubprocessTask.state 实时可查
    """
    task = SubprocessTask(task_id, self.logs_dir)
    task.log_path.parent.mkdir(parents=True, exist_ok=True)
    task._log_file = open(task.log_path, "w", encoding="utf-8")

    python_path = self.get_plugin_python(plugin_id)
    clean_env = self._clean_subprocess_env()

    # Windows: 不弹出黑色控制台窗口
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    task.state = SubprocessState.RUNNING

    # stdin=subprocess.PIPE: 用于孤儿进程防御（主进程退出 -> stdin EOF -> 子进程自杀）
    # 结果写入文件: args 中传入 result_path，子进程将大体积 JSON 写文件而非 stdout
    result_path = self.tasks_dir / f"{task_id}_result.json"
    args["result_path"] = str(result_path)
    args["tmp_dir"] = str(self.tasks_dir / f"{task_id}_tmp")

    task.proc = subprocess.Popen(
        [str(python_path), "-u", script_path, json.dumps(args)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=clean_env,
        text=True,
        bufsize=1,
        startupinfo=startupinfo,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )

    def _read_output():
        """后台线程：逐行读取子进程输出，分发事件 + 写日志。"""
        result_file_path = None
        for line in task.proc.stdout:
            task._log_file.write(line)
            task._log_file.flush()

            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "progress" and progress_cb:
                progress_cb(msg["value"], msg.get("message", ""))
            elif msg.get("type") == "result":
                # 子进程将结果写入文件，stdout 仅传路径
                if msg.get("status") == "saved" and msg.get("path"):
                    result_file_path = Path(msg["path"])

        task.proc.wait()
        task._log_file.close()

        # 从结果文件加载转写数据
        if result_file_path and result_file_path.exists():
            task.result = json.loads(result_file_path.read_text(encoding="utf-8"))

        # 清理临时切片文件
        tmp_dir = Path(args.get("tmp_dir", ""))
        if tmp_dir.exists():
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

        if task._cancel_event.is_set():
            task.state = SubprocessState.CANCELLED
        elif task.proc.returncode == 0:
            task.state = SubprocessState.COMPLETED
        else:
            task.state = SubprocessState.FAILED
            # 对异常退出码分类，提供针对性错误信息
            rc = task.proc.returncode
            if rc == -11 or rc == 139:  # SIGSEGV (Linux/macOS)
                task.error = "子进程崩溃（Segmentation Fault），可能是显存不足或 C 扩展冲突。建议切换为 0.6B 模型或 CPU 推理。"
            elif rc == -6 or rc == 134:  # SIGABRT (Linux/macOS, 常见于 CUDA OOM)
                task.error = "子进程异常终止（SIGABRT），可能是 GPU 显存不足。建议切换为 CPU 推理或使用更小模型。"
            elif rc == 3221225477:  # Windows ACCESS_VIOLATION (0xC0000005)
                task.error = "子进程崩溃（内存访问违规），可能是显存不足。建议切换为 CPU 推理或 0.6B 模型。"
            elif rc == 3221225725:  # Windows stack buffer overrun (0xC0000409)
                task.error = "子进程崩溃（栈缓冲区溢出），可能是 CUDA 内存不足。建议切换为 CPU 推理。"
            else:
                task.error = f"Exit code {rc}, see log: {task.log_path}"

    thread = threading.Thread(target=_read_output, daemon=True)
    thread.start()
    return task
```

#### 子进程脚本模板（所有 ASR 脚本共享）

```python
# --- 子进程脚本公共头部 ---
import sys, json, os, threading

def report(msg_type, **kwargs):
    """向 stdout 写入 JSON 事件（主进程通过管道读取）。"""
    print(json.dumps({"type": msg_type, **kwargs}), flush=True)

# --- 孤儿进程防御：stdin EOF 守护线程 ---
def _stdin_watchdog():
    """监听 stdin 管道。主进程崩溃/退出时 stdin 关闭（EOF），子进程自杀。"""
    try:
        while True:
            data = sys.stdin.read(1)
            if data == "":
                # EOF: 主进程已退出，子进程自我终结
                os._exit(1)
    except Exception:
        os._exit(1)

_watchdog = threading.Thread(target=_stdin_watchdog, daemon=True)
_watchdog.start()

# --- 以下是各脚本的具体推理逻辑 ---
args = json.loads(sys.argv[1])
```

#### 日志文件格式

```
# asr_task_001_20260528_143022.log
# task_id: task_001
# plugin: plugin-whisper
# started: 2026-05-28T14:30:22
# ---
{"type": "progress", "value": 0.05, "message": "检查插件环境..."}
{"type": "progress", "value": 0.15, "message": "模型加载完成"}
{"type": "progress", "value": 0.50, "message": "转写中: 12.3s"}
# 非 JSON 行（Python warnings、CUDA 日志等）也会记录
/usr/lib/python3.11/site-packages/torch/cuda/__init__.py: UserWarning: ...
{"type": "result", "status": "saved", "path": "~/.milo-cut/tasks/task_001_result.json"}
```

#### 结果文件

转写结果不走 stdout 管道，由子进程直接写入文件：
- 路径：`<数据目录>/tasks/{task_id}_result.json`
- 格式：标准 JSON，含 `segments[]` + `words[]` + `language`
- 主进程在子进程退出后读取该文件，解析为 `Segment` + `Word` 对象
- 临时切片文件（`tasks/{task_id}_tmp/`）在读取后自动清理

#### 前端查看日志

桥接 API 新增：
```python
@expose
def get_asr_log(self, task_id: str) -> dict:
    """返回指定 ASR 任务的日志文件内容。"""
    log_path = self.plugin_manager.get_log_path(task_id)
    if log_path and log_path.exists():
        return {"success": True, "data": log_path.read_text(encoding="utf-8")}
    return {"success": False, "error": "Log file not found"}

@expose
def list_asr_logs(self) -> dict:
    """返回所有 ASR 日志文件列表（按时间倒序）。"""
    logs = sorted(self.plugin_manager.logs_dir.glob("asr_*.log"), reverse=True)
    return {"success": True, "data": [{"path": str(p), "name": p.name} for p in logs[:50]]}
```

#### 关键设计约束

| 约束 | 实现 |
|------|------|
| **无弹窗** | Windows: `CREATE_NO_WINDOW` + `STARTUPINFO.wShowWindow=0`。macOS/Linux 无此问题 |
| **无阻塞** | stdout 读取在 daemon 线程中，主线程通过 `SubprocessTask.state` 轮询或回调 |
| **状态可查** | `SubprocessTask.state` 枚举：pending/running/completed/failed/cancelled |
| **孤儿进程防御** | 子进程 stdin 守护线程：主进程退出 -> stdin EOF -> `os._exit(1)` 自杀 |
| **结果不撑管道** | 大体积转写结果写入 `tasks/{task_id}_result.json`，stdout 仅传进度和文件路径 |
| **日志持久化** | 每次运行独立日志文件 `<数据目录>/logs/asr_{task_id}_{timestamp}.log` |
| **stderr 不丢失** | `stderr=subprocess.STDOUT` 合并到 stdout，统一写入日志 |
| **非 JSON 行容错** | `json.JSONDecodeError` 跳过（Python warnings、CUDA 日志等），仅写入日志 |
| **取消干净** | `terminate()` + 状态标记，不残留僵尸进程 |
| **临时文件清理** | 切片临时文件在结果读取后自动 `shutil.rmtree` |
| **跨平台路径** | Windows: `%LOCALAPPDATA%/MiloCut/`，macOS: `~/Library/Application Support/MiloCut/`，Linux: `~/.local/share/milocut/` |
| **日志持久化** | 每次运行独立日志文件 `~/.milo-cut/logs/asr_{task_id}_{timestamp}.log` |
| **stderr 不丢失** | `stderr=subprocess.STDOUT` 合并到 stdout，统一写入日志 |
| **非 JSON 行容错** | `json.JSONDecodeError` 跳过（Python warnings、CUDA 日志等），仅写入日志 |
| **取消干净** | `terminate()` + 状态标记，不残留僵尸进程 |

---

## 5. Sprint 拆解

### Sprint 1: 插件管理 + faster-whisper ASR (P0)

Sprint 1 建立插件基础设施并集成第一个 ASR 引擎（faster-whisper），打通端到端转写流程。

#### Task 1.1: PluginManager 后端

**目标**: 实现基于 uv 的插件生命周期管理。

**新建文件**:
- `core/plugin_manager.py`

**实现细节**:

1. `PluginManager` 类:
   - `__init__(plugins_dir: Path)` -- 初始化目录和注册表
   - `list_plugins() -> list[PluginInfo]` -- 列出已注册插件
   - `is_installed(plugin_id: str) -> bool` -- 检查插件是否可用
   - `install_plugin(plugin_id: str, progress_cb=None) -> dict` -- uv venv + uv pip install
   - `uninstall_plugin(plugin_id: str) -> dict` -- 删除 venv + 注册表
   - `ensure_model(model_id: str, progress_cb=None) -> Path` -- 确保 ML 模型已下载
   - `delete_model(model_id: str) -> dict` -- 删除模型文件
   - `run_in_plugin(plugin_id, script, args, progress_cb, cancel_event) -> dict` -- 子进程 IPC 推理
   - `get_plugin_python(plugin_id: str) -> Path` -- 获取插件 venv 的 Python 解释器路径
   - `_clean_subprocess_env() -> dict` -- 清除 PyInstaller 环境变量
   - `_detect_download_source() -> str` -- 探测网络选择下载源

2. 插件清单定义:
   ```python
   PLUGIN_REGISTRY = {
       "plugin-whisper": {
           "display_name": "Faster Whisper ASR",
           "engine": "faster-whisper",
           "dependencies": ["faster-whisper>=1.0.0"],
           "models": {
               "Systran/faster-whisper-large-v3-turbo": {
                   "display_name": "Large V3 Turbo (推荐)", "size_bytes": 1_500_000_000
               },
               "Systran/faster-whisper-base": {
                   "display_name": "Base (轻量)", "size_bytes": 74_000_000
               },
           },
       },
       "plugin-qwen": {
           "display_name": "Qwen3 ASR",
           "engine": "qwen3-asr",
           "dependencies": ["transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
           "models": {
               "Qwen/Qwen3-ASR-0.6B": {
                   "display_name": "Qwen3 ASR 0.6B", "size_bytes": 1_200_000_000
               },
               "Qwen/Qwen3-ForcedAligner-0.6B": {
                   "display_name": "Qwen3 ForcedAligner 0.6B", "size_bytes": 600_000_000
               },
           },
       },
   }
   ```

3. uv 交互:
   - `uv venv {venv_path} --python 3.11` -- 创建隔离环境（在线，自动下载 Python）
   - `uv venv {venv_path} --python {local_python_path}` -- 创建隔离环境（离线，使用内嵌 Python）
   - `uv pip install {packages} --python {venv_python}` -- 安装依赖到隔离环境
   - 进度通过 stdout 解析或 TaskManager 事件转发
   - 离线分发时: `build.py` 需将目标平台 Python 解释器压缩包嵌入 `resources/python/` 目录

4. 注册表持久化: `~/.milo-cut/registry.json`，原子写入

**修改文件**:
- `core/models.py` -- 新增 `PluginInfo` 模型、`PLUGIN_INSTALL` 任务类型
- `core/config.py` -- 新增 AI 设置默认值

**验证**: 单元测试 -- 创建 PluginManager、模拟 uv 命令、验证注册表读写。集成测试 -- 用 uv 创建空 venv 验证流程。

---

#### Task 1.2: Pydantic 模型扩展

**目标**: 扩展数据模型以支持 ASR 输出和插件管理。

**修改文件**:
- `core/models.py`

**实现细节**:

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

**验证**: `bun run build` 成功。`uv run pytest tests/test_models.py` 通过。

---

#### Task 1.3: PluginManager 桥接 API

**目标**: 将插件管理能力暴露给前端。

**修改文件**:
- `main.py`

**实现细节**:

新增 `@expose` 方法:
- `list_plugins() -> dict` -- 返回已注册插件列表及状态
- `install_plugin(plugin_id: str) -> dict` -- 启动后台安装任务，返回 task_id
- `uninstall_plugin(plugin_id: str) -> dict` -- 卸载插件
- `list_models() -> dict` -- 返回已下载模型列表
- `download_model(model_id: str) -> dict` -- 启动模型下载任务
- `delete_model(model_id: str) -> dict` -- 删除模型
- `check_plugin_status(engine: str) -> dict` -- 检查引擎是否就绪
- `get_asr_log(task_id: str) -> dict` -- 返回指定 ASR 任务的日志内容
- `list_asr_logs() -> dict` -- 返回 ASR 日志文件列表（按时间倒序）
- `get_asr_task_state(task_id: str) -> dict` -- 返回子进程状态（pending/running/completed/failed/cancelled）

注册任务处理器:
- `TaskType.PLUGIN_INSTALL -> _handle_plugin_install`

在 `MiloCutApi.__init__()` 中初始化 `PluginManager` 实例。

**验证**: 前端调用 `list_plugins` 返回两个插件（均未安装）。调用 `check_plugin_status("faster-whisper")` 返回所需安装信息。

---

#### Task 1.4: faster-whisper ASR 服务

**目标**: 实现基于 faster-whisper 的 ASR 转写服务，通过子进程 IPC 在插件隔离环境中运行。

**新建文件**:
- `core/asr_service.py` -- 主进程侧：协调插件安装、模型下载、子进程调用
- `core/asr_scripts/whisper_transcribe.py` -- 子进程脚本：在插件 venv 中执行实际推理

**实现细节**:

1. 主进程协调层 (`asr_service.py`):
   ```python
   def transcribe_with_whisper(
       plugin_manager: PluginManager,
       media_path: str,
       ffmpeg_path: str,       # 从用户配置中读取
       model_size: str = "large-v3-turbo",
       language: str = "zh",
       device: str = "cpu",
       compute_type: str = "int8",
       word_timestamps: bool = True,
       vad_filter: bool = True,
       progress_cb: Callable | None = None,
       cancel_event: threading.Event | None = None,
   ) -> dict:
       """协调 faster-whisper 转写：安装检查 -> 模型下载 -> 子进程推理。"""
       if not plugin_manager.is_installed("plugin-whisper"):
           plugin_manager.install_plugin("plugin-whisper", progress_cb)
       plugin_manager.ensure_model(f"Systran/{model_size}", progress_cb)
       script = Path(__file__).parent / "asr_scripts" / "whisper_transcribe.py"
       args = {
           "media_path": media_path,
           "ffmpeg_path": ffmpeg_path,  # 显式传递用户配置的 FFmpeg 路径
           "model_size": model_size,
           "language": language,
           "device": device,
           "compute_type": compute_type,
           "word_timestamps": word_timestamps,
           "vad_filter": vad_filter,
       }
       return plugin_manager.run_in_plugin("plugin-whisper", str(script), args, progress_cb, cancel_event)
   ```

2. 子进程推理脚本 (`whisper_transcribe.py`):
   ```python
   # 此脚本在插件 venv 的 python.exe 中执行
   # sys.path 已天然包含插件的 site-packages，无需手动注入
   import sys, json
   from faster_whisper import WhisperModel

   args = json.loads(sys.argv[1])
   model = WhisperModel(args["model_size"], device=args["device"], compute_type=args["compute_type"])

   def report(msg_type, **kwargs):
       print(json.dumps({"type": msg_type, **kwargs}), flush=True)

   report("progress", value=0.1, message="模型加载完成")
   segments, info = model.transcribe(args["media_path"], language=args["language"],
       word_timestamps=args["word_timestamps"], vad_filter=args["vad_filter"])

   results = []
   for seg in segments:
       words = [{"word": w.word, "start": w.start, "end": w.end} for w in seg.words]
       results.append({"text": seg.text, "start": seg.start, "end": seg.end, "words": words})
       report("progress", value=0.1 + 0.8 * (seg.end / info.duration), message=f"转写中: {seg.end:.1f}s")

   # 结果写入文件（避免大体积 JSON 撑爆 stdout 管道）
   with open(args["result_path"], "w", encoding="utf-8") as f:
       json.dump({"segments": results, "language": info.language}, f, ensure_ascii=False)
   report("result", status="saved", path=args["result_path"])
   ```

3. 进度报告:
   - 0-10%: 插件环境检查/安装
   - 10-20%: 模型加载（首次需下载）
   - 20-90%: 转写推理（子进程 stdout 流式报告）
   - 90-100%: 结果解析

4. 取消支持: `cancel_event` 触发时 `terminate()` 子进程

**修改文件**:
- `main.py` -- 注册 `TaskType.TRANSCRIPTION` handler

**验证**: 使用短中文音频 (<30s) 测试。验证 segments 非空、时间戳合理、Word 列表已填充。验证子进程崩溃不影响主程序。

---

#### Task 1.5: 插件管理 UI

**目标**: 在设置页新增 AI 插件管理区域。

**新建文件**:
- `frontend/src/composables/usePluginManager.ts`

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue`

**实现细节**:

1. `usePluginManager` composable:
   - `plugins: ref<PluginInfo[]>` -- 已注册插件列表
   - `models: ref<ModelInfo[]>` -- 已下载模型列表
   - `listPlugins()` -- 调用 `list_plugins` 桥接
   - `installPlugin(pluginId)` -- 调用 `install_plugin`，监听进度事件
   - `uninstallPlugin(pluginId)` -- 调用 `uninstall_plugin`
   - `downloadModel(modelId)` -- 调用 `download_model`
   - `deleteModel(modelId)` -- 调用 `delete_model`
   - `ensureReady(engine)` -- 检查插件+模型，必要时提示安装

2. SettingsModal 新增 "AI 引擎" 区域（位于 FFmpeg 区域下方）:
   - 插件列表: 名称、引擎类型、版本、状态标签（已安装/未安装/安装中）
   - 安装/卸载按钮
   - 已安装插件展开: 关联模型列表 + 下载/删除按钮
   - 安装进度条（通过 task:progress 事件更新）

3. 样式复用现有 SettingsModal 的 Tailwind + DaisyUI 模式

**验证**: 打开设置页，看到 AI 引擎区域。两个插件均显示 "未安装"。点击安装 faster-whisper，验证进度条和完成状态。

---

#### Task 1.6: ASR UI 集成

**目标**: 在工作区添加 ASR 转写入口。

**修改文件**:
- `frontend/src/composables/useAnalysis.ts`
- `frontend/src/pages/WorkspacePage.vue`

**实现细节**:

1. `useAnalysis.ts` 扩展:
   - 新增 `runTranscription()` -- 先 `ensureReady(engine)`，再 `createTask("transcription")` + `startTask`
   - 更新 `ANALYSIS_TASKS` 包含 `"transcription"`

2. `WorkspacePage.vue` 集成:
   - 工具栏新增 "转写" 按钮（位于 "导入 SRT" 和 "检测静音" 之间）
   - 按钮状态: 禁用（isDetecting/isExporting）、转写中（进度显示）
   - 转写完成后，项目自动更新（与静音检测完成相同的模式）
   - 首次使用时弹出插件安装确认对话框

**验证**: 加载含中文音频的项目 -> 点击 "转写" -> 首次弹出安装确认 -> 安装+下载完成后自动转写 -> 时间线显示字幕段。

---

### Sprint 2: Qwen3-ASR + VAD + 重复检测 (P1)

Sprint 2 集成第二个 ASR 引擎、VAD 增强和重复句检测。

#### Task 2.1: Qwen3-ASR 转写服务

**目标**: 实现基于 Qwen3-ASR 的转写 + 强制对齐流水线，通过子进程 IPC 运行。

**新建文件**:
- `core/asr_scripts/qwen_transcribe.py` -- 子进程脚本：在 plugin-qwen venv 中执行

**修改文件**:
- `core/asr_service.py` -- 新增 `transcribe_with_qwen()` 协调函数

**实现细节**:

1. 主进程协调层 (`asr_service.py`):
   ```python
   def transcribe_with_qwen(
       plugin_manager: PluginManager,
       media_path: str,
       model_size: str = "0.6b",
       language: str = "Chinese",
       device: str = "cpu",
       progress_cb: Callable | None = None,
       cancel_event: threading.Event | None = None,
   ) -> dict:
       """协调 Qwen3-ASR 转写：安装检查 -> 模型下载 -> 子进程推理。"""
       # 1. 确保插件已安装
       # 2. 确保 ASR 模型 + 对齐模型已下载
       # 3. 子进程推理（IPC）
       script = Path(__file__).parent / "asr_scripts" / "qwen_transcribe.py"
       args = {"media_path": media_path, "model_size": model_size, ...}
       return plugin_manager.run_in_plugin("plugin-qwen", str(script), args, progress_cb, cancel_event)
   ```

2. 子进程推理脚本 (`qwen_transcribe.py`):
   ```python
   # 此脚本在 plugin-qwen venv 的 python.exe 中执行
   # torch/transformers 已天然可用
   import sys, json, os, subprocess, tempfile
   from pathlib import Path
   from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

   MAX_ALIGN_SECONDS = 295  # ForcedAligner 上限 ~5 分钟，留 5s 余量
   ACCUMULATE_THRESHOLD = 280  # 累积到此时长后寻找最佳切割点
   FALLBACK_SPLIT_SECONDS = 240  # 无静音点时强制均匀切割时长

   def report(msg_type, **kwargs):
       print(json.dumps({"type": msg_type, **kwargs}), flush=True)

   def detect_silence_points(audio_path: str, ffmpeg_path: str = "ffmpeg",
                              min_silence: float = 0.5, threshold: float = -35.0) -> list[float]:
       """用 FFmpeg silencedetect 检测静音段，返回每段静音的中间时间点。"""
       cmd = [
           ffmpeg_path, "-i", audio_path, "-af",
           f"silencedetect=noise={threshold}dB:d={min_silence}",
           "-f", "null", "-"
       ]
       result = subprocess.run(cmd, capture_output=True, text=True)
       # 解析 stderr 中的 silence_start / silence_end，取中间点
       points = []
       for line in result.stderr.splitlines():
           if "silence_start:" in line:
               start = float(line.split("silence_start:")[1].split()[0])
           elif "silence_end:" in line:
               end = float(line.split("silence_end:")[1].split()[0])
               points.append((start + end) / 2.0)
       return sorted(points)

   SLICE_OVERLAP = 0.5  # 切片重叠区（秒），防止边界处漏字

   def smart_slice_audio(audio_path: str, silence_points: list[float],
                          tmp_dir: str, ffmpeg_path: str, duration: float
                          ) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[str]]:
       """累积式智能切片：累积音频到接近上限时，在最佳静音点切割。

       返回: (content_slices, overlapped_slices, out_paths)
         - content_slices: 每片的有效内容区间（用于去重判定）
         - overlapped_slices: 实际切割区间（含重叠区）
         - out_paths: 切割后的 WAV 文件路径
       """
       slices = []
       seg_start = 0.0
       window_silence = []

       for sp in silence_points:
           if sp <= seg_start:
               continue
           accumulated = sp - seg_start
           window_silence.append(sp)

           if accumulated >= ACCUMULATE_THRESHOLD:
               mid = seg_start + accumulated / 2
               best = min(window_silence, key=lambda p: abs(p - mid))
               slices.append((seg_start, best))
               seg_start = best
               window_silence = []

       remaining = duration - seg_start
       if remaining > MAX_ALIGN_SECONDS:
           while remaining > MAX_ALIGN_SECONDS:
               cut = seg_start + FALLBACK_SPLIT_SECONDS
               slices.append((seg_start, cut))
               seg_start = cut
               remaining = duration - seg_start
       if remaining > 0.1:
           slices.append((seg_start, duration))

       if not slices:
           t = 0.0
           while t < duration:
               end = min(t + FALLBACK_SPLIT_SECONDS, duration)
               slices.append((t, end))
               t = end

       # 给每片添加重叠区（首片和末片不向外扩展）
       overlapped = []
       for i, (start, end) in enumerate(slices):
           ol_start = max(0.0, start - SLICE_OVERLAP) if i > 0 else start
           ol_end = min(duration, end + SLICE_OVERLAP) if i < len(slices) - 1 else end
           overlapped.append((ol_start, ol_end))

       out_paths = []
       for i, (start, end) in enumerate(overlapped):
           out = os.path.join(tmp_dir, f"slice_{i:03d}.wav")
           subprocess.run([
               ffmpeg_path, "-i", audio_path,
               "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
               "-ar", "16000", "-ac", "1", "-y", out
           ], capture_output=True, check=True)
           out_paths.append(out)

       report("info", message=f"切片完成: {len(out_paths)} 片, "
               f"时长范围 {min(e-s for s,e in overlapped):.0f}s-{max(e-s for s,e in overlapped):.0f}s, "
               f"重叠区 {SLICE_OVERLAP}s")
       return slices, overlapped, out_paths

   # --- 主流程 ---
   args = json.loads(sys.argv[1])
   result_path = args["result_path"]  # 结果写入文件，不走 stdout
   ffmpeg_path = args.get("ffmpeg_path", "ffmpeg")

   # 1. 长音频切片（>5 分钟时自动切割）
   duration = get_duration(args["media_path"], ffmpeg_path)
   if duration > MAX_ALIGN_SECONDS:
       report("progress", value=0.02,
              message=f"音频 {duration:.0f}s 超过 5 分钟限制，智能切片中...")
       silence_points = detect_silence_points(args["media_path"], ffmpeg_path)
       content_slices, overlapped, slice_paths = smart_slice_audio(
           args["media_path"], silence_points,
           args["tmp_dir"], ffmpeg_path, duration
       )
   else:
       content_slices = [(0.0, duration)]
       overlapped = [(0.0, duration)]
       slice_paths = [args["media_path"]]

   # 2. 逐片 ASR 推理 + 强制对齐 + 重叠区去重
   all_segments = []
   for i, slice_path in enumerate(slice_paths):
       report("progress", value=0.1 + 0.7 * (i / len(slice_paths)),
              message=f"转写切片 {i+1}/{len(slice_paths)}")
       seg_result = run_asr_and_align(model, processor, aligner, slice_path, args["language"])

       # 时间戳重映射 + 重叠区去重
       ol_start = overlapped[i][0]     # 该片在原始音频中的实际起始
       content_start = content_slices[i][0]  # 有效内容区间起始
       content_end = content_slices[i][1]    # 有效内容区间结束
       for seg in seg_result:
           abs_start = ol_start + seg["start"]
           abs_end = ol_start + seg["end"]
           # 只保留落在有效内容区间内的段，丢弃重叠区的重复内容
           if i > 0 and abs_end < content_start:
               continue  # 前向重叠区，丢弃
           if i < len(slice_paths) - 1 and abs_start > content_end:
               continue  # 后向重叠区，丢弃
           seg["start"] = abs_start
           seg["end"] = abs_end
           for w in seg.get("words", []):
               w["start"] = ol_start + w["start"]
               w["end"] = ol_start + w["end"]
           all_segments.append(seg)

   # 4. 结果写入文件（避免撑爆 stdout 管道）
   with open(result_path, "w", encoding="utf-8") as f:
       json.dump({"segments": all_segments, "language": args["language"]}, f, ensure_ascii=False)

   report("result", status="saved", path=result_path)
   ```

3. 流水线:
   - 音频提取: FFmpeg 提取 16kHz WAV
   - **长音频智能切片**: >5 分钟时，累积音频到 ~280s 后在最佳静音点切割；全程无静音点时强制 240s 均匀切割；保留足够上下文避免丢失语义
   - **切片重叠**: 每片首尾额外保留 0.5s 重叠区，防止边界处因缺乏上下文而漏字或时间戳偏移
   - ASR 推理: transformers 加载 Qwen3-ASR 模型转写（子进程内，逐片）
   - 强制对齐: Qwen3-ForcedAligner 获取字/词级时间戳（子进程内，逐片）
   - **时间戳重映射 + 重叠去重**: 每片结果累加偏移量，利用有效内容区间剔除重叠区的重复字词
   - 结果写入: `{data_dir}/tasks/{task_id}_result.json`，stdout 仅报进度

3. 模型管理:
   - ASR 模型: `Qwen/Qwen3-ASR-0.6B` 或 `Qwen/Qwen3-ASR-1.7B`
   - 对齐模型: `Qwen/Qwen3-ForcedAligner-0.6B`
   - 两个模型均通过 `plugin_manager.ensure_model()` 按需下载

4. 进度报告:
   - 0-10%: 插件环境检查/安装
   - 10-20%: 模型加载（ASR + 对齐器）
   - 20-60%: ASR 推理
   - 60-80%: 强制对齐
   - 80-100%: 结果解析

**验证**: 使用短中文音频测试。验证字级时间戳精度。对比 faster-whisper 输出。

---

#### Task 2.2: VAD 增强（复用 faster-whisper 内置 Silero VAD）

**目标**: 利用 faster-whisper 插件内置的 Silero VAD 过滤能力，提升噪声环境下的转写质量。**不在主程序中引入任何 VAD 依赖**，现有 FFmpeg silencedetect 保持不变。

**实现方式**:
- faster-whisper 的 `model.transcribe()` 原生支持 `vad_filter=True` 参数
- 该参数启用内置 Silero VAD，在转写前自动过滤静音段
- 运行在 plugin-whisper 子进程中，零额外依赖
- 用户在设置页可选择是否启用 VAD 过滤（默认开启）

**修改文件**:
- `core/asr_scripts/whisper_transcribe.py` -- 传递 `vad_filter` 参数
- `frontend/src/components/workspace/SettingsModal.vue` -- ASR 设置中新增 VAD 过滤开关

**验证**: 对噪声环境音频，对比 `vad_filter=True` 和 `vad_filter=False` 的转写结果。VAD 过滤应减少幻觉文本。

---

#### Task 2.3: 重复句检测

**目标**: 使用 n-gram 相似度检测重复句，无需额外 ML 模型。算法自动感知语言，中文使用字符级 n-gram，英文/西文使用词级 n-gram。

**修改文件**:
- `core/analysis_service.py` -- 新增 `detect_duplicates()`
- `core/config.py` -- 新增 `duplicate_threshold` 和 `duplicate_min_length` 设置

**实现细节**:

1. 算法: 语言自适应 n-gram 余弦相似度 + 滑动窗口约束
   ```python
   def detect_duplicates(
       segments: list[Segment],
       language: str = "zh-CN",       # 从 TranscriptData.language 读取
       similarity_threshold: float = 0.85,
       min_segment_length: int = 4,
       window_size: int = 50,        # 滑动窗口：只比较相邻 N 段
       time_window_sec: float = 300,  # 时间窗口：只比较 5 分钟内的段
   ) -> list[AnalysisResult]:
       """检测重复句，返回 AnalysisResult(type="duplicate")。

       语言自适应:
       - 中文 (zh-*): 字符级 3-gram（字即词，精度最高）
       - 英文/西文 (en/es/...): 以空格切词后提取 word 2-gram（避免拆碎单词）
       - 其他/未知: 默认字符级 3-gram

       滑动窗口约束避免 O(n^2) 全量比较：
       - 每段只与后续 window_size 段比较
       - 同时限制时间跨度在 time_window_sec 秒内
       实际复杂度 O(n * window_size)，对 1000 段仅需 ~50000 次比较。
       """
   ```

2. 逻辑:
   - 过滤掉长度 < min_segment_length 的段
   - 根据 `language` 选择 n-gram 策略:
     - 中文: `text[i:i+3]` 字符 3-gram
     - 英文/西文: `words[i:i+2]` 词级 2-gram（先按空格分词）
   - 对每段 i，只与 [i+1, i+window_size] 范围内且时间差 < time_window_sec 的段比较
   - 计算 n-gram 余弦相似度，超过阈值的配对生成 AnalysisResult
   - 返回按 confidence 降序排列

3. 更新 `run_full_analysis()` 包含重复检测

**验证**: 构造含重复句的测试 segments。验证检测结果正确，相似但不同主题的段不被标记。

---

#### Task 2.4: ASR 设置 UI

**目标**: 在设置页新增 ASR 配置区域。

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue`
- `frontend/src/types/edit.ts` -- AppSettings 扩展

**实现细节**:

1. AppSettings 新增字段:
   - `asr_engine: "faster-whisper" | "qwen3-asr"` -- 默认引擎
   - `asr_model_size: string` -- 模型大小（如 "large-v3-turbo" / "0.6b"）
   - `asr_language: string` -- 语言（"zh" / "Chinese" / "auto"）
   - `asr_device: "cpu" | "cuda" | "auto"` -- 推理设备
   - `asr_compute_type: "int8" | "float16" | "float32"` -- 计算精度（faster-whisper 专用）
   - `duplicate_threshold: number` -- 重复检测阈值 (0.5-1.0)
   - `duplicate_min_length: number` -- 最小段长度

2. SettingsModal 新增 "ASR / AI" 区域:
   - 引擎选择: 下拉框（faster-whisper / Qwen3-ASR）
   - 模型大小: 下拉框（选项随引擎变化）
   - 语言: 下拉框（中文/英文/自动检测）
   - 设备: 下拉框（CPU/CUDA/自动）
   - 计算精度: 下拉框（仅 faster-whisper）
   - 重复检测阈值: 滑块
   - 线程数: 滑块

**验证**: 修改设置 -> 保存 -> 重启验证持久化。切换引擎后选项联动更新。

---

### Sprint 3: 原片/剪后切换 + 集成打磨 (P1)

#### Task 3.1: 原片/剪后切换预览

**目标**: 工作区播放器支持在原片和剪后版本间切换。

**修改文件**:
- `frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/export/PreviewPlayer.vue`

**实现细节**:

1. WorkspacePage:
   - 新增 `previewMode: ref<"edited" | "original">("edited")`
   - 视频播放循环中: edited 模式跳过已确认删除段，original 模式不跳过
   - 进度条: original 模式下删除段用半透明红色显示（dimmed）
   - 控制栏新增切换按钮，original 模式时按钮高亮（amber）

2. PreviewPlayer（导出页）:
   - 同样新增 `previewMode` 和切换按钮
   - `checkSkip()` 函数根据模式决定是否跳过

3. 快捷键: `Shift+Space` 切换模式

4. 性能设计 -- 轻量级事件监听开关:
   - 采用**单视频流 + 动态事件监听开关**，不重建底层播放轨
   - edited 模式: 激活 `timeupdate` 监听，检测到 `currentTime` 进入删除段时立即 `video.currentTime = editDecision.end`
   - original 模式: `removeEventListener("timeupdate", ...)` 移除监听，时间线上的删除段高亮保留（半透明红色）
   - 切换时仅切换监听器和 UI 标记，不 seek、不重建视频源，避免画面闪烁
   - 比 OpenTimelineIO 虚拟切片方案性能更好，低配机器也能流畅切换

**验证**: 加载含已确认删除段的项目 -> 播放（edited 模式自动跳过）-> 切换到 original（完整播放）-> 切换回来（恢复跳过）。

---

#### Task 3.2: 集成测试与打磨

**目标**: 端到端验证全流程，修复集成问题。

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

---

#### Task 3.3: 依赖更新与构建

**目标**: 更新 pyproject.toml，确保构建成功。

**修改文件**:
- `pyproject.toml` -- 版本号更新为 1.2.0
- `frontend/package.json` -- 版本号更新为 1.2.0
- `build.py` -- 更新 PyInstaller 配置，嵌入 uv 二进制

**关键**: 主程序 pyproject.toml **不新增** ASR 相关依赖。ASR 依赖由插件管理器通过 uv 在隔离环境中按需安装。

主程序新增的唯一依赖:
```toml
dependencies = [
    # ... 现有依赖（不变）
    # v1.2.0 无需新增 ASR 依赖，由插件隔离环境管理
]
```

PyInstaller 打包配置:
```python
# build.py -- 嵌入 uv 二进制
--add-data "uv.exe;."  # Windows
--add-data "uv:."      # macOS
```

**验证**: `uv run dev.py` 无导入错误。`bun run build` 成功。`uv run build.py` 生成可执行文件，体积不显著增加。

---

## 6. 依赖关系图

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

关键路径: 1.1 -> 1.3 -> 1.4 -> 1.6 -> 3.2

2.1、2.2、2.3 可在 1.1 完成后并行开发。3.1 独立于其他任务。

---

## 7. 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| uv 二进制跨平台兼容性 | 高 | 低 | uv 支持 Windows/macOS/Linux，单文件嵌入，已广泛验证 |
| PyInstaller 打包后 uv 路径解析 | 中 | 中 | `sys.executable` 同目录查找，打包前测试验证 |
| PyInstaller 环境变量污染子进程 | 高 | 中 | `_clean_subprocess_env()` 清除 PYTHONPATH/PYTHONHOME/LD_LIBRARY_PATH |
| 子进程 IPC stdout 解析异常 | 中 | 低 | 严格的 JSON 解析 + 超时机制 + stderr 合并到日志 |
| 孤儿进程（主进程崩溃/用户强关窗口） | 高 | 中 | 子进程 stdin 守护线程：EOF 检测 -> `os._exit(1)` 自杀 |
| 大体积结果撑爆 stdout 管道 | 中 | 中 | 结果写入文件 `tasks/{task_id}_result.json`，stdout 仅传路径 |
| torch 依赖安装慢（首次） | 中 | 高 | uv 比 pip 快 10-100x。提供预下载离线 wheel 包方案 |
| 插件环境 Python 版本与主程序不一致 | 高 | 低 | `uv venv --python 3.11` 显式指定，与主程序一致 |
| Qwen3-ASR 模型下载慢（国内） | 高 | 中 | 多源切换：ModelScope / hf-mirror.com / HuggingFace，自动探测网络 |
| 磁盘空间不足导致下载/安装失败 | 高 | 中 | 下载前预检磁盘剩余空间，不足时提前拦截并友好提示 |
| faster-whisper CTranslate2 平台兼容性 | 中 | 低 | CTranslate2 4.x 已支持 Python 3.11 + Win/macOS |
| Qwen3-ForcedAligner 最大 5 分钟限制 | 中 | 中 | 子进程内 FFmpeg silencedetect 切片 + 时间戳重映射合并 |
| GPU 显存不足（Qwen3-ASR 1.7B） | 中 | 中 | 默认推荐 0.6B 版本。1.7B 需 ~4GB 显存 |
| 重复检测 O(n^2) 复杂度 | 中 | 中 | 滑动窗口约束（50 段 + 5 分钟），复杂度降为 O(n*50)；长视频也不会卡顿 |
| AnalysisResult.type 扩展破坏现有数据 | 低 | 低 | 仅添加新值，不修改已有值。旧项目文件兼容 |
| 数据目录权限（Windows 域控/杀毒） | 中 | 低 | 使用 `%LOCALAPPDATA%` 标准路径，避免用户根目录 dotfile |
| 离线环境插件安装失败 | 高 | 中 | uv 创建 venv 需下载 Python（若本地无匹配版本）。离线分发包需内嵌预下载的目标平台 Python 解释器压缩包，通过 `uv venv --python <本地路径>` 强制指定；同时检测离线状态时给出明确提示 |
| Qwen 切片无静音点时语义断裂 | 中 | 低 | 强制 240s 均匀切割兜底。实际音频中 4 分钟无任何静音的情况极少；即使出现，Qwen3-ASR 单次推理上限 5 分钟，240s 切片仍有足够余量 |
| 切片边界处 ASR 漏字/时间戳偏移 | 中 | 中 | 切片间保留 0.5s 重叠区（SLICE_OVERLAP），时间戳重映射时利用有效内容区间剔除重叠区重复字词 |
| Windows MAX_PATH 路径长度超限 | 中 | 中 | `LOCALAPPDATA` 路径 + `plugins/` 层级较深，torch 内部嵌套包可能超 260 字符。初始化时检测 `LongPathsEnabled` 注册表项；子目录结构尽量压平（如 `plugins/whisper/` 而非 `plugins/plugin-whisper/venv/`） |
| C 扩展崩溃 / GPU OOM（子进程硬崩溃） | 高 | 中 | PyTorch/CUDA OOM 触发 Segmentation Fault，Python 无法捕获。`run_in_plugin` 已通过 `returncode != 0` 判定失败。ASR 服务层对异常退出码分类：检测到 SIGSEGV/OOM 特征码时，前端弹出针对性提示（"显存不足，建议切换 0.6B 模型或 CPU 推理"），而非通用"请查看日志" |

---

## 8. 新增文件汇总

| 文件 | Sprint | 用途 |
|------|--------|------|
| `core/plugin_manager.py` | 1 | uv 驱动的插件生命周期管理（venv + 依赖 + 模型 + 子进程 IPC） |
| `core/asr_service.py` | 1-2 | ASR 转写协调层（安装检查 -> 模型下载 -> 子进程调用） |
| `core/asr_scripts/whisper_transcribe.py` | 1 | faster-whisper 子进程推理脚本（含 stdin 守护、结果写文件） |
| `core/asr_scripts/qwen_transcribe.py` | 2 | Qwen3-ASR 子进程推理脚本（含长音频切片、时间戳重映射） |
| `frontend/src/composables/usePluginManager.ts` | 1 | 前端插件管理 composable |

---

## 9. 修改文件汇总

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

## 10. 验收标准

- [ ] 设置页 AI 引擎区域显示已注册插件列表（faster-whisper、Qwen3-ASR）
- [ ] 首次使用 ASR 时弹出插件安装确认对话框（含磁盘空间预检）
- [ ] 插件安装使用 uv 创建隔离环境，进度实时显示
- [ ] 插件安装完成后自动下载 ML 模型（可选）
- [ ] faster-whisper 转写产生字幕段 + 词级时间戳
- [ ] faster-whisper VAD 过滤开关正常工作（`vad_filter=True`）
- [ ] Qwen3-ASR 转写支持中文方言
- [ ] Qwen3-ForcedAligner 提供字级对齐时间戳
- [ ] 长音频（>5 分钟）Qwen 转写自动切片 + 时间戳正确重映射
- [ ] 重复句检测正确标记重复段
- [ ] 全分析（静音+口头禅+口误+重复）正常运行
- [ ] 原片/剪后切换预览正常工作
- [ ] ASR 子进程运行时无控制台弹窗（Windows）
- [ ] 主进程关闭/崩溃时子进程自动退出（无孤儿进程残留）
- [ ] ASR 日志文件可查看（`get_asr_log` / `list_asr_logs`）
- [ ] 插件安装/卸载不影响主程序稳定性
- [ ] 模型下载失败时显示友好错误提示
- [ ] 国内网络自动切换 ModelScope/hf-mirror 下载源
- [ ] 无 GPU 设备时 CPU 推理正常
- [ ] 主程序打包体积不因 ASR 功能显著增加
- [ ] 后端测试全部通过
- [ ] 前端构建成功
- [ ] 设置持久化正常

---

*文档版本：v1.2.0-rc6*
*生成日期：2026-05-27*
*基于 Milo-Cut v1.1.0 完成状态 + PRD-1.1.0 v1.2.0 路线图*
*架构方案采用 uv 驱动的插件化隔离环境管理 + 子进程 IPC 推理*
*经架构师四轮审查修正：孤儿进程防御（stdin EOF）、结果文件输出（避免管道溢出）、跨平台数据目录、长音频累积式智能切片+0.5s 重叠区防漏字、移除主进程 VAD 依赖、FFmpeg 路径显式传递、重复检测滑动窗口约束+多语言自适应 n-gram、离线 Python 解释器内嵌方案、Windows MAX_PATH 风险识别、C 扩展崩溃/OOM 退出码分类与友好提示、原片剪后切换轻量级事件监听开关*

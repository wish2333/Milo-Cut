# Milo-Cut 1.2.1 审计报告: 数据目录与模型管理

**日期**: 2026-05-29
**审计范围**: 数据目录可配置性 + 模型目录可配置性 + 外部模型导入与验证
**审计方法**: 源码分析 + 需求评估 + 影响面追踪
**目标版本**: 1.2.1

---

## 需求摘要

| 需求 | 描述 |
|------|------|
| A. 数据目录可选 | 便携模式(数据保存在exe同目录) vs 系统目录模式 |
| B. 模型目录可选 | 用户可自行指定模型存储位置，复用已有模型 |
| C. 外部模型导入验证 | 支持用户自行下载的模型，需验证为指定模型 |
| D. 模型名单可更新 | 指定模型名单方便维护和更新 |

---

## 已知 Bug: 设置页清理按钮

### Bug 1: `NameError` -- `get_data_dir` 未导入

**现象**: 点击清理按钮报错 `NameError: name 'get_data_dir' is not defined`

**根因**: `main.py` 顶层只导入了 `from core.paths import migrate_if_needed` (line 28)。`cleanup_tasks_folder` (line 943) 和 `cleanup_transcripts_folder` (line 961) 使用了 `get_data_dir()` 但未导入。

对比同文件其他方法正确使用了局部导入 (line 320, line 462)，而清理方法遗漏了。

### Bug 2: 清理路径与 PluginManager 实际路径脱节

**现象**: 修复 Bug 1 的导入后，清理按钮不再报错，但在**生产系统目录模式**下**什么都删不掉**

**根因**: `cleanup_tasks_folder` 使用 `get_data_dir() / "plugins" / "tasks"` 构造路径，但 `PluginManager` 实际写入的是 `get_plugin_data_dir() / "tasks"`。

在非便携的生产模式下，两者指向不同位置:
- `get_data_dir() / "plugins" / "tasks"` -> `.../MiloCut/data/plugins/tasks` (不存在)
- `get_plugin_data_dir() / "tasks"` -> `%LOCALAPPDATA%/MiloCut/tasks` (实际写入位置)

**修复方案**: 清理函数必须改用 `get_plugin_data_dir()` 而非 `get_data_dir()`，保证与 `PluginManager` 维护的路径完全一致。(附录 A.1)

---

## 现状分析

### 1. 数据目录现状

**路径解析** (`core/paths.py`):

| 路径 | 函数 | 当前行为 |
|------|------|----------|
| 应用根目录 | `get_app_dir()` | frozen: exe所在目录; dev: 项目根目录 |
| 数据目录 | `get_data_dir()` | `get_app_dir() / "data"` |
| 项目目录 | `get_projects_dir()` | `get_data_dir() / "projects"` |
| 设置文件 | `get_settings_path()` | `get_data_dir() / "settings.json"` |
| 日志目录 | `get_log_dir()` | `get_data_dir() / "logs"` |
| 临时目录 | `get_temp_dir()` | `get_data_dir() / "temp"` |

**插件数据目录** (`get_plugin_data_dir()`) -- **已存在分叉逻辑**:

| 环境 | 路径 |
|------|------|
| 开发 | `<project_root>/data/plugins/` |
| 生产 Windows | `%LOCALAPPDATA%/MiloCut/` |
| 生产 macOS | `~/Library/Application Support/MiloCut/` |
| 生产 Linux | `~/.local/share/milocut/` |

**关键发现**: 插件目录(模型、venv)已经和数据目录分离了。生产环境下插件数据在系统目录，而项目/设置/日志仍在exe同目录的`data/`。这种不对称意味着路径改造需要区分"应用数据"和"模型数据"。

**消费路径的模块**:

| 模块 | 导入的路径函数 |
|------|----------------|
| `core/config.py` | `get_data_dir`, `get_settings_path` |
| `core/project_service.py` | `get_projects_dir` |
| `core/plugin_manager.py` | `get_plugin_data_dir` |
| `core/logging.py` | `get_log_dir` |
| `core/export_service.py` | `get_temp_dir` |
| `main.py` | `get_data_dir`, `get_projects_dir`, `get_plugin_data_dir`, `migrate_if_needed` |

### 2. 模型管理现状

**模型注册表** (`core/plugin_manager.py` `PLUGIN_REGISTRY`):

模型信息硬编码在代码中的 `PLUGIN_REGISTRY` dict 中:
- `plugin-whisper`: 2 个模型 (Purfview/faster-whisper-large-v3-turbo, Systran/faster-whisper-base)
- `plugin-qwen-cpu` / `plugin-qwen-gpu`: 3 个模型 (Qwen3-ASR-0.6B, Qwen3-ASR-1.7B, Qwen3-ForcedAligner-0.6B)

**模型存储路径** (`_get_model_path`):
```python
self._plugins_dir / "models" / model_id.replace("/", "--")
# 例: data/plugins/models/Purfview--faster-whisper-large-v3-turbo
```

**模型验证**: 当前仅检查目录是否存在 (`local_path.exists()`)。没有哈希校验、文件完整性检查或模型来源验证。

**模型下载**: `ensure_model()` 通过 `huggingface_hub.snapshot_download()` 或 `modelscope.snapshot_download()` 下载，三源自动切换 (HuggingFace -> hf-mirror -> ModelScope)。

### 3. 现有配置接口与架构陷阱

`PluginManager.__init__` 接受可选 `plugins_dir` 参数:
```python
def __init__(self, plugins_dir: Path | None = None) -> None:
    self._plugins_dir = plugins_dir or get_plugin_data_dir()
    self._plugins_dir.mkdir(parents=True, exist_ok=True)
    self._registry_path = self._plugins_dir / "registry.json"  # 插件状态
    self._tasks_dir = self._plugins_dir / "tasks"               # 高频临时文件
```

**架构陷阱: `plugins_dir` 不等于 `model_dir`**。如果直接将用户指定的模型目录作为 `plugins_dir` 传入:

1. `registry.json` (插件安装状态) 会被写到模型目录 -- 多实例共用时互相覆盖崩溃
2. `tasks/` (高频写入的日志和临时结果) 会被写到用户指定的低速盘 (如机械硬盘)
3. venv 也会被错误地创建到模型目录

**正确方案**: 在 `PluginManager` 中显式解耦插件根目录与模型目录:
```python
def __init__(self, plugins_dir: Path | None = None, model_dir: Path | None = None) -> None:
    self._plugins_dir = plugins_dir or get_plugin_data_dir()
    self._model_dir = model_dir or (self._plugins_dir / "models")
```

`_get_model_path` 改为基于 `self._model_dir`，而 `registry.json`、`tasks/`、`venv/` 仍在 `plugins_dir` 下。

---

## 需求评估

### 需求 A: 数据目录可选

**评估: 推荐实现，工作量中等**

**方案**: 便携模式标记文件检测

在 exe 同目录放置标记文件 `data/.portable` (内容为空)。启动时:
- 检测到 `.portable` -> 数据目录 = `exe所在目录/data/` (当前默认行为)
- 未检测到 `.portable` -> 数据目录 = 系统标准路径

**影响面**: 仅需修改 `core/paths.py` 中的 `get_data_dir()` 函数。所有下游模块通过函数调用获取路径，不需要逐个修改。

**需要注意的点**:
- PyInstaller onefile 模式下 exe 的"同目录"是临时解压目录，不适合存数据。需要用 `sys._MEIPASS` 的父级或其他机制定位真实 exe 路径
- **macOS .app Bundle 陷阱**: `sys.executable` 在 macOS .app 包中指向 `Milo-Cut.app/Contents/MacOS/Milo-Cut`，其 `.parent` 是 Bundle 内部只读目录。`get_app_dir()` 必须额外判断 macOS frozen 状态并跳出 `.app` 包，指向 `.app` 同级目录
- 迁移: 首次从旧目录切到新目录时需要数据迁移 (`migrate_if_needed` 已有先例)
- **便携模式必须覆盖 `get_plugin_data_dir()`**: 当前 `get_plugin_data_dir()` 在 frozen 状态下无条件写入系统目录 (`%LOCALAPPDATA%` 等)。一旦检测到 `.portable`，无论是否 frozen，必须强制降级为 `get_data_dir() / "plugins"`

### 需求 B: 模型目录可选

**评估: 推荐实现，工作量小 (但需解耦)**

**方案**: 在 `PluginManager` 中显式分离 `plugins_dir` 与 `model_dir`

**不能复用 `plugins_dir`** -- 参见"现状分析 > 3. 现有配置接口与架构陷阱"。正确做法:
1. `PluginManager.__init__` 新增 `model_dir` 参数，与 `plugins_dir` 独立
2. `_get_model_path` 改为基于 `self._model_dir`
3. `settings.json` 增加 `model_dir` 字段 (默认为空，表示使用 `plugins_dir / "models"`)
4. `main.py` 创建 `PluginManager` 时，读取设置并分别传入 `plugins_dir` 和 `model_dir`

**数据归属划分**:

| 数据 | 存储位置 | 说明 |
|------|----------|------|
| `registry.json` | `plugins_dir` | 插件安装状态，跟随应用实例 |
| `tasks/` | `plugins_dir` | 高频临时文件，跟随应用实例 |
| `venv/` | `plugins_dir / plugin-*/venv/` | 插件虚拟环境，跟随应用实例 |
| `models/` | `model_dir` (可配置) | 模型文件，可跨实例复用 |

**需要注意的点**:
- 模型目录变更后，已有下载的模型不会自动迁移。需要提示用户手动迁移或提供迁移工具

### 需求 C: 外部模型导入与验证

**评估: 推荐实现，但需明确验证粒度**

**方案**: 基于模型ID目录结构的验证

用户将模型放到指定目录时，通过以下方式验证:
1. **目录名匹配**: 目录名必须是 `OWNER--MODEL-NAME` 格式 (如 `Purfview--faster-whisper-large-v3-turbo`)
2. **必要文件检查**: 根据 `PLUGIN_REGISTRY` 中的模型类型，检查关键文件是否存在:
   - Whisper 模型: `model.bin` + `config.json`
   - Qwen 模型: `model.safetensors` + `config.json`
3. **不做哈希校验**: 模型文件大(1-5GB)，SHA256 计算耗时长且用户难以获取校验值。文件存在性 + 加载时错误处理已足够

**不建议做**: 完整哈希校验。原因:
- 模型文件大，校验耗时长，影响启动体验
- 哈希值需要随模型版本更新，维护成本高
- 模型加载时加载器(faster-whisper/transformers)本身会做格式验证

### 需求 D: 模型名单可更新

**评估: 建议实现，但优先级最低**

**当前状态**: 模型名单硬编码在 `PLUGIN_REGISTRY` 中，随代码发布。

**方案选项**:

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 保持硬编码 | 简单可靠，无需网络 | 更新需发版 |
| B. 远程配置文件 | 热更新，灵活 | 需要网络、需托管、需版本兼容 |
| C. 本地JSON覆盖 | 用户可自定义，离线可用 | 格式错误风险 |

**推荐**: 方案 A (保持硬编码)。原因:
1. 模型名单变更频率低 -- 新增/更换模型本身就需要代码适配(模型加载参数、预处理逻辑)
2. 模型与引擎强耦合 -- 不能只改名单不加代码
3. 远程配置增加了离线场景下的失败点和维护负担
4. 如果未来需要支持更多模型，应通过插件系统扩展，而非远程名单

**替代建议**: 如果确实需要灵活性，可以采用方案 C -- 在 `data/` 目录放置 `model_overrides.json`，格式与 `PLUGIN_REGISTRY["models"]` 一致，应用启动时合并。高级用户可以自行添加模型定义，但需要在 UI 中给出警告。

---

## 实施建议

### 推荐实施范围

| 需求 | 建议 | 优先级 | 工作量估计 |
|------|------|--------|-----------|
| A. 数据目录可选 | 实现 | P1 | 中 (修改 `paths.py` + macOS 适配 + 迁移逻辑) |
| B. 模型目录可选 | 实现(需解耦) | P1 | 中 (`PluginManager` 构造函数重构 + 设置字段) |
| C. 外部模型验证 | 实现(文件存在性检查) | P2 | 小 (验证函数) |
| D. 模型名单可更新 | 保持硬编码，暂不实现 | P3 | -- |

### 关键修改文件

| 文件 | 修改内容 |
|------|----------|
| `core/paths.py` | `get_data_dir()` 增加便携/系统模式切换; `get_plugin_data_dir()` 在便携模式下强制降级; `get_app_dir()` 适配 macOS .app Bundle |
| `core/config.py` | `_DEFAULT_SETTINGS` 增加 `model_dir` 字段 |
| `main.py` | 修复 `get_data_dir` 未导入的 bug; 读取 `model_dir` 设置，分别传 `plugins_dir` 和 `model_dir` 给 `PluginManager` |
| `core/plugin_manager.py` | `__init__` 新增 `model_dir` 参数，与 `plugins_dir` 解耦; `_get_model_path` 改用 `self._model_dir`; 新增 `validate_model()` 方法 |
| `frontend/src/types/edit.ts` | `AppSettings` 增加 `model_dir` 字段 |
| `frontend/src/components/workspace/SettingsModal.vue` | 模型目录设置 UI (路径选择 + 验证状态) |

### 不需要修改的文件

以下模块通过 `get_*_dir()` 函数间接获取路径，`paths.py` 修改后自动生效:
- `core/project_service.py`
- `core/logging.py`
- `core/export_service.py`

### 验证方案

1. **便携模式**: 在 `data/` 目录创建 `.portable` 文件，启动应用，确认所有数据写入 exe 同目录
2. **系统目录模式**: 删除 `.portable` 文件，启动应用，确认数据写入系统标准路径
3. **自定义模型目录**: 在设置中指定自定义模型目录，下载模型，确认模型存储在自定义目录
4. **外部模型**: 手动将模型文件复制到自定义目录的正确子目录中，重启应用，确认模型被识别
5. **模型验证**: 放置不完整的模型文件(缺少 `model.bin`)，确认应用报告验证失败

---

## 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| PyInstaller onefile 路径问题 | 便携模式可能指向临时目录 | 使用 `sys.executable` 而非 `__file__` 定位 exe |
| macOS .app Bundle 只读目录 | 便携模式写入 Bundle 内部触发 PermissionError | `get_app_dir()` 检测 macOS .app 路径并跳出到 `.app` 同级目录 |
| 便携模式插件目录不分叉 | frozen 状态下 `get_plugin_data_dir()` 无条件写入系统目录 | 便携模式优先级高于 frozen 检测，强制 `get_data_dir() / "plugins"` |
| `plugins_dir`/`model_dir` 未解耦 | 共享模型目录时 `registry.json` 互相覆盖 | 构造函数显式分离两个路径 |
| 自定义 `model_dir` 路径失效 | 启动时 `mkdir` 抛出 `OSError`，应用闪退，用户无法进入设置修正 | 构造函数中 try/except 包裹自定义路径创建，失败时降级回默认路径并记录日志 |
| 清理路径与实际写入路径脱节 | 生产模式下清理按钮静默无效，任务文件永久堆积 | 清理函数改用 `get_plugin_data_dir()` 而非 `get_data_dir()` |
| 数据迁移中断 | 用户丢失设置/项目数据 | 迁移前备份，原子操作 |
| 自定义目录权限不足 | 写入失败 | 启动时检测目录可写性，给出明确提示 |
| 模型路径变更后旧路径残留 | 磁盘空间浪费 | 在 UI 中提示用户清理旧模型 |

---

## 附录

### A.1 Bug: 清理按钮双重错误

**Bug 1 原代码** -- `main.py` 模块级导入 (line 28) 缺少 `get_data_dir`:
```python
from core.paths import migrate_if_needed
```

同文件其他方法正确使用了局部导入:
```python
# line 320
from core.paths import get_data_dir, get_projects_dir

# line 462
from core.paths import get_data_dir
```

**Bug 2 原代码** -- `cleanup_tasks_folder` (line 940-955) 路径与 PluginManager 脱节:
```python
@expose
def cleanup_tasks_folder(self) -> dict:
    try:
        tasks_dir = Path(get_data_dir()) / "plugins" / "tasks"  # Bug1: NameError
        # 即使修复导入后，Bug2: 生产模式下此路径与 PluginManager 实际路径不同
        # get_data_dir()/plugins/tasks != get_plugin_data_dir()/tasks
```

**修正方案** -- 两个清理方法统一改用 `get_plugin_data_dir()`:
```python
# cleanup_tasks_folder 修正
@expose
def cleanup_tasks_folder(self) -> dict:
    """安全清理历史转录任务文件"""
    try:
        from core.paths import get_plugin_data_dir
        tasks_dir = Path(get_plugin_data_dir()) / "tasks"

        if not tasks_dir.exists():
            return {"success": True, "data": {"deleted": 0, "message": "No tasks folder found"}}

        deleted = 0
        for f in tasks_dir.iterdir():
            if f.is_file() and (f.suffix in (".log", ".json")):
                f.unlink()
                deleted += 1

        return {"success": True, "data": {"deleted": deleted, "message": f"Cleaned up {deleted} task files"}}
    except Exception as e:
        return {"success": False, "error": str(e)}

# cleanup_transcripts_folder 修正 -- 此方法清理的是 data/transcripts，使用 get_data_dir 正确
@expose
def cleanup_transcripts_folder(self) -> dict:
    """Delete all auto-saved transcription SRT files."""
    try:
        from core.paths import get_data_dir
        transcripts_dir = get_data_dir() / "transcripts"
        # transcripts 保存在 data_dir/transcripts，不涉及 plugins_dir，此处 get_data_dir 正确
```

### A.2 core/paths.py -- 修正方案

```python
"""Centralized application data paths.

适配便携模式、macOS .app Bundle 只读逃逸、插件路径强制降级。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "milo-cut"


def get_app_dir() -> Path:
    """获取应用根目录，适配 Windows Exe 和 macOS .app Bundle。

    - macOS .app: sys.executable 指向 Milo-Cut.app/Contents/MacOS/Milo-Cut
      需要跳出 .app 包到同级可写目录
    - Windows/Linux: sys.executable.parent 即可
    - Development: 项目根目录
    """
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        # macOS .app Bundle 只读逃逸
        if "Contents/MacOS" in exe_path.parts:
            return exe_path.parents[3]  # 跳出 Milo-Cut.app，指向同级目录
        return exe_path.parent
    return Path(__file__).resolve().parent.parent


def is_portable_mode() -> bool:
    """通过标记文件检测是否为便携模式。"""
    return (get_app_dir() / "data" / ".portable").exists()


def get_data_dir() -> Path:
    """获取数据目录。

    - 便携模式或开发模式: exe同目录/data/
    - 系统目录模式: 平台标准路径
    """
    if is_portable_mode() or not getattr(sys, "frozen", False):
        d = get_app_dir() / "data"
    else:
        if sys.platform == "win32":
            d = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "MiloCut" / "data"
        elif sys.platform == "darwin":
            d = Path.home() / "Library" / "Application Support" / "MiloCut" / "data"
        else:
            d = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "milocut" / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_log_dir() -> Path:
    d = get_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_path() -> Path:
    return get_data_dir() / "settings.json"


def get_projects_dir() -> Path:
    d = get_data_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_temp_dir() -> Path:
    d = get_data_dir() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_plugin_data_dir() -> Path:
    """获取插件/模型根目录。

    便携模式拥有最高优先级，无论是否 frozen 都强制降级到 data/plugins/。
    """
    if is_portable_mode() or not getattr(sys, "frozen", False):
        d = get_data_dir() / "plugins"
    else:
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            d = base / "MiloCut"
        elif sys.platform == "darwin":
            d = Path.home() / "Library" / "Application Support" / "MiloCut"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            d = base / "milocut"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _old_appdata_dir() -> Path | None:
    if sys.platform == "win32":
        candidate = Path(os.environ.get("APPDATA", "")) / APP_NAME
    else:
        base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        candidate = Path(base) / APP_NAME
    return candidate if candidate.is_dir() else None


def migrate_if_needed() -> None:
    old = _old_appdata_dir()
    if old is None:
        return
    new = get_data_dir()
    if new.exists() and any(new.iterdir()):
        return
    shutil.copytree(old, new, dirs_exist_ok=True)
```

### A.3 core/config.py -- 默认设置与加载逻辑

```python
from core.paths import get_data_dir, get_settings_path

_DEFAULT_SETTINGS: dict[str, Any] = {
    "ffmpeg_path": "",
    "ffprobe_path": "",
    "theme": "light",
    "language": "zh-CN",
    "silence_threshold_db": -30,
    "silence_min_duration": 0.5,
    "silence_margin": 0.0,
    "silence_subtitle_padding": 0.0,
    "trim_subtitles_on_silence_overlap": True,
    "export_fade_duration": 0.0,
    "export_transition_mode": "none",
    "filler_words": ["嗯","啊","呃","然后","就是","那个","怎么说呢","你知道","对吧","其实"],
    "error_trigger_words": ["不对","重来","重新说","说错了","刚才说错了","这段不要","再来一遍","算了","不是这样的"],
    "export_video_codec": "libx264",
    "export_audio_codec": "aac",
    "export_audio_bitrate": "192k",
    "export_preset": "medium",
    "export_crf": 23,
    "export_resolution": "original",
    "export_ffmpeg_transitions": True,
    "export_ffmpeg_fade_duration": 0,
    "export_ffmpeg_fade_mode": "crossfade",
    # ASR / AI
    "asr_engine": "faster-whisper",
    "asr_model_size": "large-v3-turbo",
    "asr_language": "zh",
    "asr_device": "cpu",
    "asr_vad_filter": True,
    "whisper_compute_type": "int8_float16",
    "whisper_vad_threshold": 0.5,
    "whisper_vad_min_silence_ms": 500,
    "qwen_compute_type": "bfloat16",
    "qwen_language": "auto",
    "duplicate_threshold": 0.85,
    "duplicate_min_length": 5,
}

def load_settings() -> dict[str, Any]:
    path = get_settings_path()
    if not path.exists():
        return {**_DEFAULT_SETTINGS}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {**_DEFAULT_SETTINGS}
    merged = {**_DEFAULT_SETTINGS, **data}
    return merged

def save_settings(settings: dict[str, Any]) -> None:
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
```

### A.4 core/plugin_manager.py -- 模型相关核心逻辑

PLUGIN_REGISTRY (line 31-86):
```python
PLUGIN_REGISTRY: dict[str, dict[str, Any]] = {
    "plugin-whisper": {
        "display_name": "Faster Whisper ASR",
        "engine": "faster-whisper",
        "dependencies": ["faster-whisper>=1.0.0"],
        "models": {
            "Purfview/faster-whisper-large-v3-turbo": {
                "display_name": "Large V3 Turbo (recommended)",
                "size_bytes": 1_500_000_000,
            },
            "Systran/faster-whisper-base": {
                "display_name": "Base (lightweight)",
                "size_bytes": 74_000_000,
            },
        },
    },
    "plugin-qwen-cpu": {
        "display_name": "Qwen3 ASR (CPU)",
        "engine": "qwen3-asr",
        "dependencies": ["qwen-asr", "transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
        "models": {
            "Qwen/Qwen3-ASR-0.6B": { "display_name": "...", "size_bytes": 1_880_000_000 },
            "Qwen/Qwen3-ASR-1.7B": { "display_name": "...", "size_bytes": 4_700_000_000 },
            "Qwen/Qwen3-ForcedAligner-0.6B": { "display_name": "...", "size_bytes": 1_840_000_000 },
        },
    },
    "plugin-qwen-gpu": {
        "display_name": "Qwen3 ASR (GPU)",
        "engine": "qwen3-asr",
        "dependencies": ["qwen-asr", "transformers>=4.40.0", "torch>=2.0.0", "accelerate"],
        "pytorch_index": "https://download.pytorch.org/whl/cu124",
        "models": { /* 同 plugin-qwen-cpu */ },
    },
}
```

PluginManager 构造函数与模型路径 (line 352-569):
```python
# 当前实现 -- plugins_dir 与 model_dir 未解耦
class PluginManager:
    def __init__(self, plugins_dir: Path | None = None) -> None:
        self._plugins_dir = plugins_dir or get_plugin_data_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        # 问题: registry.json, tasks/, venv/ 全部跟随 plugins_dir
        self._registry_path = self._plugins_dir / "registry.json"
        self._tasks_dir = self._plugins_dir / "tasks"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, dict[str, Any]] = self._load_registry()
        self._subprocess_tasks: dict[str, SubprocessTask] = {}
        self._lock = threading.Lock()

    def _get_model_path(self, model_id: str) -> Path:
        safe_name = model_id.replace("/", "--")
        return self._plugins_dir / "models" / safe_name  # 模型路径与插件根目录耦合

    def is_model_downloaded(self, model_id: str) -> bool:
        return self._get_model_path(model_id).exists()
```

修正方案 -- 显式解耦 + 自定义路径防闪退:
```python
class PluginManager:
    def __init__(self, plugins_dir: Path | None = None, model_dir: Path | None = None) -> None:
        self._plugins_dir = plugins_dir or get_plugin_data_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)

        # 模型目录独立，默认 plugins_dir/models
        # 关键: 自定义路径必须防御性创建，防止用户配置了失效路径导致启动闪退
        default_model_dir = self._plugins_dir / "models"
        if model_dir:
            try:
                self._model_dir = Path(model_dir)
                self._model_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(
                    "Custom model_dir {} is invalid ({}), falling back to default",
                    model_dir, e,
                )
                self._model_dir = default_model_dir
                self._model_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._model_dir = default_model_dir
            self._model_dir.mkdir(parents=True, exist_ok=True)

        # registry/tasks/venv 仍在 plugins_dir 下
        self._registry_path = self._plugins_dir / "registry.json"
        self._tasks_dir = self._plugins_dir / "tasks"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, dict[str, Any]] = self._load_registry()
        self._subprocess_tasks: dict[str, SubprocessTask] = {}
        self._lock = threading.Lock()

    def _get_model_path(self, model_id: str) -> Path:
        safe_name = model_id.replace("/", "--")
        return self._model_dir / safe_name  # 基于 model_dir 而非 plugins_dir
```

ensure_model (line 571-627):
```python
def ensure_model(self, model_id: str, progress_cb=None, mirror=None) -> Path:
    local_path = self._get_model_path(model_id)
    if local_path.exists():
        return local_path

    model_meta = self._find_model_meta(model_id)
    if model_meta is None:
        raise ValueError(f"Unknown model: {model_id}")

    source = mirror if mirror else _detect_download_source()
    local_path.mkdir(parents=True, exist_ok=True)

    try:
        if source == "modelscope":
            self._download_from_modelscope(model_id, local_path, progress_cb)
        else:
            endpoint = "https://hf-mirror.com" if source == "hf-mirror" else "https://huggingface.co"
            self._download_from_hf(model_id, local_path, endpoint, progress_cb)
    except Exception as exc:
        shutil.rmtree(local_path, ignore_errors=True)
        raise RuntimeError(f"Model download failed: {exc}") from exc

    return local_path
```

### A.5 相关文件路径索引

```
core/paths.py              -- 路径解析中心 (107 行)
core/config.py             -- 设置加载/保存 (79 行)
core/plugin_manager.py     -- 插件和模型管理 (676+ 行)
core/asr_service.py        -- ASR 转录协调
main.py                    -- 应用入口，PluginManager 实例化
data/settings.json         -- 运行时设置
data/plugins/registry.json -- 插件安装状态
data/plugins/models/       -- 模型存储目录
frontend/src/types/edit.ts -- AppSettings TypeScript 类型
frontend/src/composables/usePluginManager.ts -- 前端插件管理 composable
frontend/src/components/workspace/SettingsModal.vue -- 设置弹窗 UI
```

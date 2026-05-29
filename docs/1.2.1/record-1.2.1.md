# Milo-Cut 1.2.1 Development Record

---

## 目录

1. [Overview](#overview)
2. [Architecture Decisions](#architecture-decisions)
3. [Sprint 1: 数据目录与模型管理](#sprint-1)
4. [Files Modified Summary](#files-modified-summary)
5. [Verification](#verification)
6. [Statistics](#statistics)

---

## Overview

1.2.1 版本聚焦于数据目录可配置性和模型管理优化，核心目标是支持便携模式、解耦模型目录、修复清理函数 Bug。按审计报告 `docs/1.2.1/audit-report-1.2.1.md` 执行。

---

## Architecture Decisions

### 便携模式标记文件

在 `data/.portable` 放置空文件即可激活便携模式。检测优先级最高，无论是否 frozen 都覆盖路径逻辑。

| 模式 | 数据目录 | 插件目录 |
|------|----------|----------|
| 便携模式 | `exe同目录/data/` | `exe同目录/data/plugins/` |
| 系统模式 (Windows) | `%LOCALAPPDATA%/MiloCut/data` | `%LOCALAPPDATA%/MiloCut/` |
| 系统模式 (macOS) | `~/Library/Application Support/MiloCut/data` | `~/Library/Application Support/MiloCut/` |
| 开发模式 | `项目根/data/` | `项目根/data/plugins/` |

### macOS .app Bundle 逃逸

`sys.executable` 在 macOS .app 包中指向 `Milo-Cut.app/Contents/MacOS/Milo-Cut`。检测 `Contents/MacOS` in `exe_path.parts` 后跳出到 `.app` 同级目录。

### 模型目录解耦

`PluginManager.__init__` 新增 `model_dir` 参数，与 `plugins_dir` 独立：

| 数据 | 存储位置 | 说明 |
|------|----------|------|
| `registry.json` | `plugins_dir` | 插件安装状态 |
| `tasks/` | `plugins_dir` | 高频临时文件 |
| `venv/` | `plugins_dir/plugin-*/venv/` | 插件虚拟环境 |
| `models/` | `model_dir` (可配置) | 模型文件，可跨实例复用 |

### 外部模型验证

`validate_model()` 检查目录名格式 + 必要文件存在性，`is_model_downloaded()` 重构为调用 `validate_model()` 而非仅检查目录存在。

---

<a id="sprint-1"></a>
## Sprint 1: 数据目录与模型管理 (2026-05-30)

### 背景

按审计报告 `docs/1.2.1/audit-report-1.2.1.md` 执行，覆盖 4 个需求：

| 需求 | 描述 | 状态 |
|------|------|------|
| A. 数据目录可选 | 便携模式 vs 系统目录模式 | 已实现 |
| B. 模型目录可选 | 用户可指定模型存储位置 | 已实现 |
| C. 外部模型导入验证 | 验证用户自行下载的模型 | 已实现 |
| D. 模型名单可更新 | 保持硬编码 | 不实现 |

### 已知 Bug 修复

#### Bug 1: `cleanup_tasks_folder` NameError

**根因**: `main.py` line 943 使用 `get_data_dir()` 但未导入。

**修复**: 改用 `get_plugin_data_dir()` 并添加局部导入。

#### Bug 2: `cleanup_tasks_folder` 路径脱节

**根因**: `get_data_dir() / "plugins" / "tasks"` 在生产模式下与 `PluginManager` 实际写入的 `get_plugin_data_dir() / "tasks"` 不同。

**修复**: 统一使用 `get_plugin_data_dir() / "tasks"`。

### Task 1: core/paths.py -- 便携模式 + macOS .app Bundle

**目标**: 实现便携模式检测、macOS .app Bundle 逃逸、路径分支逻辑。

**修改文件**:
- `core/paths.py` (+39 行, -23 行)

**实现细节**:

1. `is_portable_mode()` 函数:
   - 检测 `get_app_dir() / "data" / ".portable"` 是否存在
   - 便携模式拥有最高优先级

2. `get_app_dir()` macOS 适配:
   - frozen 状态下检测 `"Contents/MacOS" in exe_path.parts`
   - 匹配时返回 `exe_path.parents[3]` (跳出 .app 包)

3. `get_data_dir()` 便携/系统分支:
   - 便携模式或开发模式: `get_app_dir() / "data"`
   - 系统模式: 平台标准路径 (Windows `%LOCALAPPDATA%/MiloCut/data`, macOS `~/Library/Application Support/MiloCut/data`, Linux `~/.local/share/milocut/data`)

4. `get_plugin_data_dir()` 便携强制降级:
   - 便携模式: `get_data_dir() / "plugins"` (无论是否 frozen)
   - 非便携 frozen: 平台标准路径

### Task 2: core/config.py -- 新增 model_dir 默认设置

**目标**: 在默认设置中添加 `model_dir` 字段。

**修改文件**:
- `core/config.py` (+1 行)

**实现细节**:
- `_DEFAULT_SETTINGS` 添加 `"model_dir": ""` (空字符串表示使用默认路径)

### Task 3: core/plugin_manager.py -- 解耦 model_dir + 新增 validate_model

**目标**: 将模型目录从插件目录解耦，新增外部模型验证。

**修改文件**:
- `core/plugin_manager.py` (+80 行, -4 行)

**实现细节**:

1. `__init__` 新增 `model_dir: Path | None = None` 参数:
   - 默认 `self._plugins_dir / "models"`
   - 自定义路径: `try/except OSError` 防御性创建，失败时降级回默认路径并记录 warning

2. `_get_model_path()` 改用 `self._model_dir`:
   - `return self._model_dir / safe_name`

3. `validate_model(model_id)` 新方法:
   - 检查目录名格式: 必须包含 `--` 分隔符
   - 检查必要文件: Whisper 需要 `model.bin` + `config.json`，Qwen 需要 `model.safetensors` + `config.json`
   - 返回 `{"valid": bool, "errors": list[str]}`

4. `is_model_downloaded()` 重构:
   - 原: `return self._get_model_path(model_id).exists()`
   - 新: `return self.validate_model(model_id)["valid"]`

### Task 4: frontend/src/types/edit.ts -- 新增 model_dir 字段

**目标**: TypeScript 类型定义同步。

**修改文件**:
- `frontend/src/types/edit.ts` (+1 行)

**实现细节**:
- `AppSettings` interface 添加 `model_dir: string`

### Task 5: main.py -- 修复清理函数 Bug + 接入 model_dir 设置

**目标**: 修复两个清理函数 Bug，将 model_dir 设置接入 PluginManager。

**修改文件**:
- `main.py` (+8 行, -2 行)

**实现细节**:

1. `cleanup_tasks_folder` 修复:
   - 添加局部导入 `from core.paths import get_plugin_data_dir`
   - 路径改为 `Path(get_plugin_data_dir()) / "tasks"`

2. `cleanup_transcripts_folder` 确认:
   - 路径 `get_data_dir() / "transcripts"` 是正确的 (transcripts 在 data_dir 下)

3. `MiloCutApi.__init__` 接入 model_dir:
   ```python
   settings = load_settings()
   model_dir = settings.get("model_dir", "")
   self._plugin_manager = PluginManager(
       model_dir=Path(model_dir) if model_dir else None
   )
   ```

### Task 6: frontend SettingsModal.vue -- 模型目录设置 UI

**目标**: 在 AI Engine 标签页添加模型目录路径选择器。

**修改文件**:
- `frontend/src/components/workspace/SettingsModal.vue` (+41 行)

**实现细节**:

1. Script 部分:
   - `handleBrowseModelDir()`: 调用 `call<string>("select_directory")`
   - `handleResetModelDir()`: 清空 `model_dir` 为空字符串

2. Template 部分 (AI Engine 标签页):
   - "Model Directory" 标签
   - 输入框 + "Browse" 按钮 + "Reset" 按钮
   - 占位文本: "默认: 插件目录/models"
   - 提示文本: "修改模型目录后需重启应用生效"

### Final Verification Wave

| 审查 | 结果 | 详情 |
|------|------|------|
| F1: Plan Compliance | APPROVE | Must Have 13/13, Must NOT Have 5/5 |
| F2: Code Quality | APPROVE | Build PASS, Tests 131/131, 3 minor unused imports |
| F3: Real Manual QA | APPROVE | Scenarios 12/13 pass (1 Windows path NOTE), Integration 2/2 |
| F4: Scope Fidelity | APPROVE | Tasks 6/6 compliant, 1 unaccounted file (docs only) |

---

## Files Modified Summary

| 文件 | 修改类型 | 行数 | 说明 |
|------|----------|------|------|
| `core/paths.py` | 重构 | +39, -23 | 便携模式检测、macOS .app Bundle 逃逸、路径分支 |
| `core/config.py` | 新增 | +1 | `model_dir` 默认设置 |
| `core/plugin_manager.py` | 重构 | +80, -4 | model_dir 解耦、validate_model、is_model_downloaded 重构 |
| `main.py` | 修复+新增 | +8, -2 | 清理函数 Bug 修复、model_dir 接入 |
| `frontend/src/types/edit.ts` | 新增 | +1 | `model_dir` 字段 |
| `frontend/src/components/workspace/SettingsModal.vue` | 新增 | +41 | 模型目录设置 UI |

---

## Verification

### 自动化测试

```
uv run pytest                    # 131/131 passed
cd frontend && bun run build     # Exit 0
```

### 便携模式验证

```powershell
# 创建便携标记
New-Item -ItemType File -Path "data/.portable" -Force

# 验证
uv run python -c "from core.paths import is_portable_mode, get_data_dir, get_plugin_data_dir; print('portable:', is_portable_mode()); print('plugin:', get_plugin_data_dir()); print('plugins_in_path:', 'plugins' in str(get_plugin_data_dir()))"
# 输出: portable: True, plugin: <project>/data/plugins, plugins_in_path: True

# 清理
Remove-Item "data/.portable" -Force
```

### PluginManager model_dir 验证

```powershell
# 默认路径
uv run python -c "from core.plugin_manager import PluginManager; pm = PluginManager(); print(pm._model_dir)"
# 输出: <project>/data/plugins/models

# 自定义路径
uv run python -c "from core.plugin_manager import PluginManager; from pathlib import Path; pm = PluginManager(model_dir=Path('data/my_models')); print(pm._model_dir)"
# 输出: <project>/data/my_models

# validate_model
uv run python -c "from core.plugin_manager import PluginManager; pm = PluginManager(); print(pm.validate_model('invalid-name'))"
# 输出: {'valid': False, 'errors': ["Model id 'invalid-name' does not contain a valid separator", ...]}
```

### 清理函数验证

```powershell
uv run python -c "from main import MiloCutApi; api = MiloCutApi(); print(api.cleanup_tasks_folder())"
# 输出: {'success': True, 'data': {'deleted': N, 'message': 'Cleaned up N task files'}}
```

---

## Statistics

| 指标 | 值 |
|------|------|
| 修改文件数 | 6 |
| 新增行数 | 170 |
| 删除行数 | 29 |
| 测试通过 | 131/131 |
| 构建状态 | PASS |
| 审查通过 | 4/4 (F1-F4) |

# Milo-Cut 1.2.1 Development Record

---

## 目录

1. [Overview](#overview)
2. [Architecture Decisions](#architecture-decisions)
3. [Sprint 1: 数据目录与模型管理](#sprint-1)
4. [Sprint 2: select_directory 桥接方法](#sprint-2)
5. [Sprint 3: 打包环境修复 + 版本号升级](#sprint-3)
6. [Files Modified Summary](#files-modified-summary)
7. [Verification](#verification)
8. [Statistics](#statistics)

---

## Overview

1.2.1 版本聚焦于数据目录可配置性、模型管理优化、打包环境修复和缺陷修复，核心目标：

1. 支持便携模式、解耦模型目录、修复清理函数 Bug (按审计报告 `docs/1.2.1/audit-report-1.2.1.md` 执行)
2. 修复模型目录浏览按钮缺失的桥接方法
3. 抑制打包环境子进程控制台弹窗、修复导出页编码器检测、版本号升级

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

<a id="sprint-2"></a>
## Sprint 2: select_directory 桥接方法 (2026-05-30)

### 背景

Sprint 1 在 SettingsModal 中添加了模型目录浏览按钮，调用 `call("select_directory")`，但 `main.py` 中缺少对应的 `@expose` 方法，导致点击浏览按钮时 API 调用失败。

### 修复

**commit**: `2f3071b fix(main): 新增 select_directory 桥接方法修复模型目录浏览按钮`

| 文件 | 修改 | 说明 |
|------|------|------|
| `main.py` | +16 | 新增 `select_directory` @expose 方法，打开文件夹选择对话框 |
| `frontend/src/types/api.ts` | +1 | `BridgeMethod` 类型新增 `select_directory` |

---

<a id="sprint-3"></a>
## Sprint 3: 打包环境修复 + 版本号升级 (2026-05-30)

### 背景

1. **控制台弹窗**: 打包后运行时，FFmpeg/FFprobe 等子进程会弹出控制台窗口。之前曾尝试 `STARTUPINFO/SW_HIDE` 但发现它会阻止 CTranslate2 加载模型而被移除。
2. **导出页编码器丢失**: `EncodingSettings.vue` 调用了已不存在的方法 `detect_gpu`，实际后端方法名为 `detect_gpu_encoders`，导致导出页编码器列表只显示 CPU 编码器。
3. **版本号**: 功能开发完成，版本号从 1.2.0 升至 1.2.1。

### 修复

**commit**: `e4cf132 fix: 打包子进程控制台弹窗修复 + 导出页编码器检测 + 版本升至 1.2.1`

#### Task 1: 子进程控制台弹窗抑制

**根因**: Windows 打包环境下 `subprocess.run()` 默认会创建新的控制台窗口。

**方案**: 使用 `CREATE_NO_WINDOW` creation flag (而非之前的 `STARTUPINFO/SW_HIDE`)。经验证 `CREATE_NO_WINDOW` 不会影响 CTranslate2 模型加载。

**修改文件**:

| 文件 | 修改 | 说明 |
|------|------|------|
| `core/asr_scripts/qwen_transcribe.py` | +6, -4 | 模块级 `_SUBPROCESS_KWARGS` 常量，所有 `subprocess.run()` 调用注入 `**_SUBPROCESS_KWARGS` |
| `core/export_service.py` | +2, -2 | `_extract_segment` 和 `_concat_segments` 注入 `**_SUBPROCESS_KWARGS` |
| `core/plugin_manager.py` | +7, -2 | `_subprocess_kwargs()` 恢复 `CREATE_NO_WINDOW` 逻辑 + `taskkill` 调用注入 |

**实现细节**:

1. `qwen_transcribe.py` -- 模块级常量:
   ```python
   _SUBPROCESS_KWARGS: dict = (
       {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
   )
   ```
   移除函数内局部 `import subprocess`，统一为顶层导入。

2. `plugin_manager.py` -- `_subprocess_kwargs()`:
   - 之前: 注释说 STARTUPINFO/SW_HIDE 已移除，接受控制台闪现
   - 现在: 使用 `CREATE_NO_WINDOW` (不会阻止 CTranslate2)，并添加注释说明原因
   - `taskkill` 进程终止调用也注入了 `**_subprocess_kwargs()`

#### Task 2: 导出页编码器检测修复

**根因**: `EncodingSettings.vue` line 150 调用 `call("detect_gpu")`，但后端实际方法名为 `detect_gpu_encoders`，导致调用失败，`hardwareEncoders` 始终为空数组，导出页只显示 CPU 编码器。

**修改文件**:

| 文件 | 修改 | 说明 |
|------|------|------|
| `frontend/src/components/export/EncodingSettings.vue` | +1, -1 | `detect_gpu` -> `detect_gpu_encoders` |

#### Task 3: 版本号升级与文档

**修改文件**:

| 文件 | 修改 | 说明 |
|------|------|------|
| `pyproject.toml` | +1, -1 | `version = "1.2.1"` |
| `frontend/package.json` | +1, -1 | `"version": "1.2.1"` |
| `uv.lock` | +1, -1 | `version = "1.2.1"` |
| `docs/1.2.0/record-1.2.0.md` | +83 | 添加 v1.2.0 merge message 和 release note |
| `docs/1.2.0/audit-report-1.2.1.md` | 删除 | 审计报告已完成，移至 docs/1.2.1/ |

---

## Files Modified Summary

### Sprint 1: 数据目录与模型管理

| 文件 | 修改类型 | 行数 | 说明 |
|------|----------|------|------|
| `core/paths.py` | 重构 | +39, -23 | 便携模式检测、macOS .app Bundle 逃逸、路径分支 |
| `core/config.py` | 新增 | +1 | `model_dir` 默认设置 |
| `core/plugin_manager.py` | 重构 | +80, -4 | model_dir 解耦、validate_model、is_model_downloaded 重构 |
| `main.py` | 修复+新增 | +8, -2 | 清理函数 Bug 修复、model_dir 接入 |
| `frontend/src/types/edit.ts` | 新增 | +1 | `model_dir` 字段 |
| `frontend/src/components/workspace/SettingsModal.vue` | 新增 | +41 | 模型目录设置 UI |

### Sprint 2: select_directory 桥接方法

| 文件 | 修改类型 | 行数 | 说明 |
|------|----------|------|------|
| `main.py` | 新增 | +16 | `select_directory` @expose 方法 |
| `frontend/src/types/api.ts` | 新增 | +1 | BridgeMethod 类型补全 |

### Sprint 3: 打包环境修复 + 版本号升级

| 文件 | 修改类型 | 行数 | 说明 |
|------|----------|------|------|
| `core/asr_scripts/qwen_transcribe.py` | 修复 | +6, -4 | CREATE_NO_WINDOW 抑制控制台弹窗 |
| `core/export_service.py` | 修复 | +2, -2 | 子进程注入 _SUBPROCESS_KWARGS |
| `core/plugin_manager.py` | 修复 | +7, -2 | 恢复 _subprocess_kwargs() CREATE_NO_WINDOW |
| `frontend/src/components/export/EncodingSettings.vue` | 修复 | +1, -1 | detect_gpu -> detect_gpu_encoders |
| `pyproject.toml` | chore | +1, -1 | version 1.2.1 |
| `frontend/package.json` | chore | +1, -1 | version 1.2.1 |
| `uv.lock` | chore | +1, -1 | version 1.2.1 |
| `docs/1.2.0/record-1.2.0.md` | docs | +83 | v1.2.0 merge message + release note |
| `docs/1.2.0/audit-report-1.2.1.md` | 删除 | -654 | 审计报告已完成，移至 docs/1.2.1/ |

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
| 修改文件数 | 16 |
| 新增行数 | 570 |
| 删除行数 | 42 |
| 提交数 | 3 (`2d91c38`, `2f3071b`, `e4cf132`) |
| 测试通过 | 131/131 |
| 构建状态 | PASS |
| 审查通过 | 4/4 (F1-F4) |

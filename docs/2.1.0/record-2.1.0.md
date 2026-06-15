# v2.1.0 AI 能力深化 -- 实施记录

> **版本**: 2.1.0
> **主题**: AI 能力深化 -- 提示词风格预设、P1 完整 diff 审阅、一键清理工作流
> **基准**: v2.0.1 (基于 `dev-2.0.1` 分支)
> **分支**: `dev-2.1.0` (基于 `dev-2.0.1`)
> **规格文档**: `docs/2.1.0/spec-v2.1.0.md`

---

## 概要

v2.1.0 延续 v2.0.x 的 AI 主线，聚焦三个核心缺口：

1. **提示词缺乏预设管理** -- 参数化提示词系统只能维护"当前一套参数"，无法保存不同场景的参数组合
2. **P1 字幕修正审阅不完整** -- 自动 apply 全部修正，无逐条 accept/reject、无行内 diff、无批量操作、corrections 未持久化
3. **缺乏多任务编排能力** -- 需手动逐个运行规则分析 → P0 → P1 → P2，各任务产出的 EditDecision 可能时间范围冲突

版本定位为重量级功能版本 (6-8 周)，分 3 个 Phase 实施。

---

## Phase 1: 提示词风格预设 (已完成)

> 决策范围: D-40 ~ D-45 (预设来源/粒度/与参数关系/工作流交互/内置预设数量)

### 概要

Phase 1 为每个 LLM 功能 (P0/P1/P2，不含 P3 语义搜索) 支持保存多套参数组合预设，用户可快速切换不同场景 (如"学术报告" vs "日常 vlog") 的提示词配置。

1. **预设 CRUD** -- 每个功能独立的预设列表，支持保存/应用/删除
2. **内置默认预设** -- 每个功能自带一个"默认"预设 (空参数 + 空 system_override)，等同当前行为
3. **预留字段** -- `model` 字段 (D-73) 预留存储但 Phase 1 不启用 UI，为后续模型联动做准备
4. **设置页 UI** -- SettingsModal 提示词编辑区新增预设管理面板 (下拉 + 应用/另存为/删除)

### 变更文件 (共 6 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/llm_presets.py` | **新增** (~250 行) | 预设 CRUD 逻辑: get_presets/save_preset/apply_preset/delete_preset + 内置默认预设 (稳定 id="default"，受保护) + _ensure_default_presets + D-73 model 预留字段 |
| `core/config.py` | 修改 (+5/-3 行) | _DEFAULT_SETTINGS 新增 `llm_prompt_presets: {}` 字段; **load_settings 改用 copy.deepcopy 修复浅拷贝污染 bug** (详见架构决策) |
| `main.py` | 修改 (+111 行) | 新增 4 个 @expose 方法: get_prompt_presets / save_prompt_preset / apply_prompt_preset / delete_prompt_preset，委托 core.llm_presets 并返回标准 API envelope |
| `frontend/src/composables/useLlmSettings.ts` | 修改 (+88 行) | 新增 PromptPreset 接口 + presetsByFunc/loadingPresets state + loadPresets/savePreset/applyPreset/deletePreset 方法 |
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 (+152 行) | 功能选择器后新增预设管理 UI (下拉选择 + 应用/另存为/删除按钮 + 内联名称输入框); 仅对 P0/P1/P2 功能显示 (search 排除); handlePromptKeyChange 与 onMounted 加载预设 |
| `tests/test_llm_presets.py` | **新增** (~270 行) | 21 个单元测试: TestGetPresets (内置默认/未知 key) + TestSavePreset (UUID/去空格/预留 model/异常) + TestApplyPreset (写入 override/get_effective_prompt 集成/异常) + TestDeletePreset (内置默认保护/异常) + TestFeatureIsolation (跨功能隔离) |

### 架构决策

#### 预设数据模型 -- 参数快照 (D-42, D-33 弱类型存储)

预设 = 某个 LLM 功能当前参数 (简单模式 params) + 可选 system_override (高级模式) 的完整拷贝，存储在 `settings.json["llm_prompt_presets"]`:

```python
{
  "llm_prompt_presets": {
    "smart_delete": [
      {
        "id": "default",              # 内置默认，稳定 id
        "name": "默认",
        "params": {},
        "system_override": "",
        "model": "",                  # D-73 预留
        "created_at": "..."
      },
      {
        "id": "preset-a1b2c3d4e5f6",
        "name": "学术报告",
        "params": {"custom_fillers": ["那么", "那个"]},
        "system_override": "",
        "model": "",
        "created_at": "..."
      }
    ]
  }
}
```

预设不直接生效，必须"应用"后才写入 `llm_prompts[func_key]` (即 v2.0.1 的 override 机制)。`get_effective_prompt` 无需修改即可读取生效。

#### 内置默认预设 -- 稳定 id 保护机制

最初设计基于内容判断默认预设 (params 为空 + system_override 为空即视为默认)。实施中发现两个问题:
1. 用户创建的空参数预设会被误判为默认，导致删除逻辑混乱
2. 默认预设每次按需生成时 id 随机 (uuid)，无法稳定识别

**改为稳定 id 方案**: 内置默认预设 id 固定为 `"default"`，`_ensure_default_presets` 确保每个支持的功能恰好有一个 id="default" 的预设 (前置)。`delete_preset` 通过 `_is_default_preset(target)` (检查 id) 阻止删除，报错 "Cannot delete the built-in default preset"。

#### 预设与 override 的关系 -- 应用即写入

预设是"候选配置集合"，`llm_prompts` (settings.json) 存储"当前生效"的 override。应用预设 = 将预设内容写入 `llm_prompts[func_key]`:

```python
# apply_preset 核心逻辑
override["system_override"] = system_override if (system_override and system_override.strip()) else None
override["params"] = dict(target.get("params", {}))
prompts[func_key] = override
```

这与 v2.0.1 的 `update_llm_prompt` 语义一致，确保 `get_effective_prompt` 读取链路不变。

#### 重要 bug 修复 -- config.load_settings 浅拷贝污染

**发现过程**: 编写预设单元测试时，发现测试间状态泄漏 -- TestApplyPreset 创建的 preset 数据出现在 TestDeletePreset 的 get_presets 结果中，尽管每个测试有独立的 tmp_path 和 monkeypatch。

**根因**: `core/config.py:load_settings` 原实现:
```python
merged = {**_DEFAULT_SETTINGS, **data}  # 浅拷贝
return merged
```
`{**dict}` 只复制顶层 key-value，嵌套的可变对象 (如 `llm_prompt_presets: {}`、`filler_words: [...]`) 仍是 `_DEFAULT_SETTINGS` 中同一对象的引用。当 `save_preset` 通过 `settings.get("llm_prompt_presets", {})` 获取并原地修改 (append/ensure_default) 后，`_DEFAULT_SETTINGS["llm_prompt_presets"]` 全局单例被污染，所有后续 `load_settings()` 调用都返回被污染的默认值。

**修复**: 改用 `copy.deepcopy`:
```python
def load_settings() -> dict[str, Any]:
    path = get_settings_path()
    if not path.exists():
        return copy.deepcopy(_DEFAULT_SETTINGS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(_DEFAULT_SETTINGS)
    merged = copy.deepcopy(_DEFAULT_SETTINGS)
    merged.update(data)
    return merged
```

**影响范围**: 此 bug 潜伏于整个 settings 系统。任何通过 `load_settings()` 获取 settings 并修改嵌套 dict/list 的代码都会污染全局默认。v2.0.0/v2.0.1 之所以未暴露，是因为此前无功能像 `llm_prompt_presets` 这样高频原地修改嵌套结构。此修复对 `filler_words`、`error_trigger_words` 等列表型默认值同样有效。

> **注**: v2.0.1 的 record-2.0.1.md Phase 3 记录了"浅拷贝合并的安全性"决策，结论是"当前参数结构仅一层 list[str]，浅拷贝是安全的"。该结论针对 `llm_prompts` 内部的 params 合并是正确的，但未覆盖 `load_settings` 对 `_DEFAULT_SETTINGS` 顶层的浅拷贝问题。本次修复补齐了这一盲区。

#### 测试隔离策略 -- patch load_settings/save_settings 函数本身

`core.config` 模块级 `from core.paths import get_settings_path` 是绑定引用，`monkeypatch.setattr("core.paths.get_settings_path", ...)` 不影响已绑定的 `core.config.get_settings_path`。

最初按 test_config.py 的模式 patch `core.paths.get_settings_path`，发现对 `core.config.load_settings` 无效。最终方案: 在 `isolated_settings` fixture 中直接 patch `core.config.load_settings` 和 `core.config.save_settings` 函数本身 (替换为操作 tmp_path 的闭包版本)。由于 `llm_presets.py` 内部用 `from core.config import load_settings` (函数体局部 import，每次重新解析模块属性)，patch 模块属性后局部 import 能拿到 patched 版本。

### 决策映射

| 决策 | 实现 |
|------|------|
| D-33 (弱类型存储) | 预设存为 settings.json 的 dict/list，不新建 Pydantic 模型 |
| D-40 (预设来源) | 内置默认 (id="default") + 用户自定义 (save_preset 生成 UUID) |
| D-41 (预设粒度) | 单功能预设，PRESET_SUPPORTED_KEYS 排除 search (P3 无参数化) |
| D-42 (预设=参数快照) | params + system_override 完整拷贝，apply 时写入 llm_prompts |
| D-43 (工作流步骤选预设) | Phase 1 完成 CRUD 基础设施，get_prompt_presets API 可被 Phase 3 工作流配置 UI 复用 |
| D-44 (仅默认预设) | 内置仅一个"默认"预设 (空参数)，其他用户自建 |
| D-45 (预设可选) | 预设管理 UI 独立于提示词编辑，不强制使用 |
| D-73 (预留 model 字段) | save_preset 接受 model 参数并存储，Phase 1 前端无 UI 入口 |
| D-74 (预设导入导出) | 数据结构预留 (JSON list)，Phase 1 不实现 |

### 测试覆盖

| 验证项 | 结果 |
|--------|------|
| `uv run pytest tests/test_llm_presets.py` | 21 测试全部通过 (TestGetPresets 3 + TestSavePreset 7 + TestApplyPreset 6 + TestDeletePreset 4 + TestFeatureIsolation 1) |
| `uv run pytest tests/` (全量，排除 whisper/asr-gui) | 268 测试全部通过 |
| `uv run pytest tests/test_config.py tests/test_llm_prompts.py` | 33 测试全部通过 (deepcopy 修复未破坏现有行为) |
| `uv run ruff check` (本次改动 4 文件) | 全部通过 |
| `bun run build` (前端构建) | 通过 -- 91 modules，index.js 219.70 kB |
| `bun run test` (147 前端测试) | 全部通过 |
| `bunx eslint` (useLlmSettings.ts + SettingsModal.vue) | 零错误 |

### API 契约 (新增 4 个 @expose)

| 方法 | 签名 | 返回 data |
|------|------|-----------|
| `get_prompt_presets(func_key)` | 读预设列表 | `[preset, ...]` (含内置默认) |
| `save_prompt_preset(func_key, name, params, system_override, model)` | 保存新预设 | `preset` (含生成的 id + created_at) |
| `apply_prompt_preset(func_key, preset_id)` | 应用预设到 override | `{"func_key": str, "preset_id": str}` |
| `delete_prompt_preset(func_key, preset_id)` | 删除预设 (内置默认受保护) | `{"func_key": str, "preset_id": str}` |

所有方法返回标准 envelope `{"success": bool, "data": ..., "error": ...}`，无效 func_key / preset_id 返回 `{"success": False, "error": "..."}`。

---

## Phase 2: P1 完整 diff 审阅 (未开始)

> 决策范围: D-50 ~ D-57

**目标**: 将 P1 字幕修正从"自动 apply 全部修正"改为"生成 AnalysisResult → 用户逐条审阅 diff → 接受的修正才 apply"。

**计划内容**:
- `core/diff_service.py` (新增) -- difflib 字符级 diff 计算
- corrections 持久化为 AnalysisResult (type=llm_subtitle_correction，detail 存 JSON)
- 6 个新 @expose: get_subtitle_corrections / compute_diff / accept_correction / reject_correction / accept_high_confidence_corrections / clear_subtitle_corrections
- 全屏 diff 审阅 UI (行内 diff + 置信度分组 + 批量"信任高置信度"，默认阈值 0.8 per D-68)
- `_handle_subtitle_correction` 不再自动 apply

---

## Phase 3: 一键清理工作流 (未开始)

> 决策范围: D-10 ~ D-33

**目标**: 新建独立 WorkflowEngine，支持配置任务链 (规则分析 + P0 + P1 + P2 任意串联)，管理步骤间数据传递、冲突检测、跨会话恢复。

**计划内容**:
- `core/workflow_engine.py` (新增 ~400 行) -- 任务链编排 (定义 CRUD + 执行 + 取消 + 冲突检测 + 快照管理)
- 内存工作副本 (完整快照文件) + 悲观锁 (Timeline 编辑锁定)
- 冲突检测 (segment id 维度，一次性快照) + 可选冲突解决视图
- 9 个新 workflow:* 事件 (含 heartbeat 心跳检测)
- AI 助手面板新增"工作流"模式 (与"单功能"并列)

---

## 测试基线 (Phase 1 后)

| 类别 | 数量 | 说明 |
|------|------|------|
| 后端单元测试 | 268 | 含新增 test_llm_presets.py 21 个 |
| 前端测试 | 147 | 无新增 (Phase 1 为设置页 UI，无独立组件测试) |
| ruff | 零错误 | 本次改动 4 文件全部通过 |
| ESLint | 零错误 | useLlmSettings.ts + SettingsModal.vue |
| 排除 | test_transcription.py | 已知 ASR VadOptions 失败 |
| 排除 | test_asr_gui_e2e.py | 需完整 GUI 环境 |

---

## 发布前待办

- [ ] Phase 2: P1 完整 diff 审阅
- [ ] Phase 3: 一键清理工作流
- [ ] 版本号 bump (pyproject.toml 当前仍为 1.3.0，v2.0.0/v2.0.1 未合并 main)
- [ ] build.py --onefile 实际产物验证 (需完整 GUI 环境)

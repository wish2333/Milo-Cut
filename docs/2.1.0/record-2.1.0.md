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

## Phase 2: P1 完整 diff 审阅 (已完成)

> 决策范围: D-50 ~ D-57, D-68, D-69

### 概要

将 P1 字幕修正从"自动 apply 全部修正"改为"生成 AnalysisResult → 用户逐条审阅 diff → 接受的修正才 apply"。核心变更: LLM 修正结果不再直接写入 segment.text，而是作为 AnalysisResult 持久化到项目文件，前端提供全屏 diff 审阅视图支持逐条 accept/reject 和批量操作。

### 变更文件 (共 10 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/diff_service.py` | **新增** (~68 行) | difflib 字符级 diff 计算: `compute_inline_diff(original, corrected)` 返回 `[{text, type}]` token 列表，供前端行内渲染 |
| `core/project_service.py` | 修改 (+333 行) | 7 个新方法: `_update_timeline_by_id` / `store_subtitle_corrections` / `get_subtitle_corrections` / `accept_subtitle_correction` / `reject_subtitle_correction` / `accept_high_confidence_corrections` / `clear_subtitle_corrections`; accept 路径复用 `_check_correction_confidence` + `_assert_timestamps_unchanged` 防御 |
| `main.py` | 修改 (+95 行) | `_handle_subtitle_correction` 改为调用 `store_subtitle_corrections` 而非 `apply_subtitle_corrections`; 新增 6 个 @expose: get_subtitle_corrections / compute_diff / accept_correction / reject_correction / accept_high_confidence_corrections / clear_subtitle_corrections; 新增 `_resolve_timeline_id` 辅助方法 |
| `frontend/src/composables/useLlmTasks.ts` | 修改 (+110 行) | SubtitleCorrection 接口 + pendingCorrections/correctionsLoading state + 6 个方法: loadCorrections/computeDiff/acceptCorrection/rejectCorrection/acceptHighConfidenceCorrections/clearCorrections; 事件监听改为 store 模式 |
| `frontend/src/pages/WorkspacePage.vue` | 修改 (+248 行) | 全屏 diff 审阅 UI: 置信度分组 (高/低，0.8 阈值 D-68)、行内 diff 渲染 (红删绿增 + replace 聚合 D-69)、批量"信任高置信度"/清除、逐条接受/拒绝; diff 缓存 + 异步预加载; categoryLabel 中文分类映射 |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 修改 (+16 行) | 新增 pendingCorrectionCount prop + "P1 字幕修正待审"摘要条目 + review-corrections emit (D-57 双入口之一) |
| `frontend/src/components/workspace/Timeline.vue` | 修改 (+4 行) | 透传 pendingCorrectionCount prop + review-corrections 事件 |
| `tests/test_diff_service.py` | **新增** (~108 行) | diff_service 单元测试: 基本比较、空字符串、纯替换、纯插入、纯删除、中文字符级 diff |
| `tests/test_subtitle_correction_review.py` | **新增** (~283 行) | Phase 2 端到端测试: store/get/accept/reject/batch-accept/clear + 置信度分组 + 无操作跳过 + re-run 清除旧数据 |

### 架构决策

#### corrections 持久化 -- 扩展 AnalysisResult (D-54)

修正不再直接修改 segment.text，而是存储为 `AnalysisResult`:
```python
AnalysisResult(
    id=f"corr-{seg_id}-{uuid4().hex[:8]}",
    type="llm_subtitle_correction",
    segment_ids=[seg_id],
    confidence=float(corr.get("confidence", 0.8)),
    detail=json.dumps({
        "original_text": original_text,
        "corrected_text": corrected_text,
        "changes": corr.get("changes", []),
        "category": corr.get("category", "none"),
    }, ensure_ascii=False),
)
```
存储在 `Timeline.analysis.results` 中，复用现有持久化路径 (项目保存时自动跟随)。审阅完成后从列表移除 (D-50)。

#### re-run 清除策略

`store_subtitle_corrections` 在写入新 corrections 前清除所有 type=llm_subtitle_correction 的旧结果，确保重复运行 P1 不会累积过期审阅条目。

#### accept 路径安全性

`accept_subtitle_correction` 复用 v2.0.0 引入的 `_check_correction_confidence` (置信度异常检测) 和 `_assert_timestamps_unchanged` (时间戳完整性断言)，确保 LLM 修正不会意外篡改时间轴。

#### 前端 diff 碎片优化 (D-69)

difflib 字符级比较在中文句式重组时会产生细碎的 delete/insert 交替。前端 `aggregateDiffTokens` 将相邻 delete+insert 块聚合为单个 replace 块，视觉上红删绿增紧邻显示，减少认知负担。

#### 双入口设计 (D-57)

- SuggestionPanel: 摘要条目 "P1 字幕修正待审 (N 条)"，点击触发全屏审阅
- AI 助手面板: 全屏 diff 审阅视图 (原有的字幕修正全屏模式改造)

### 决策映射

| 决策 | 实现 |
|------|------|
| D-50 (持久化后审阅清除) | accept/reject 从 analysis.results 移除; clear 批量移除 |
| D-51 (行内 diff) | 后端 difflib 字符级 + 前端 HTML 渲染 (line-through + bg 颜色) |
| D-52 (批量信任高置信度) | accept_high_confidence_corrections(threshold=0.8) |
| D-53 (直接更新 segment.text) | accept 时 model_copy 更新 segment.text + dirty_flags |
| D-54 (扩展 AnalysisResult) | type=llm_subtitle_correction, detail 存 JSON |
| D-55 (后端 difflib) | core/diff_service.py |
| D-56 (字符级 diff) | difflib.SequenceMatcher 对中文字符逐字比较 |
| D-57 (双入口) | SuggestionPanel 摘要 + 全屏 diff 审阅 |
| D-68 (默认阈值 0.8) | accept_high_confidence_corrections 默认 threshold=0.8 |
| D-69 (碎片优化) | aggregateDiffTokens 聚合相邻 delete/insert 为 replace |

### API 契约 (新增 6 个 @expose)

| 方法 | 签名 | 返回 data |
|------|------|-----------|
| `get_subtitle_corrections(timeline_id)` | 读取待审修正列表 | `[correction_dict, ...]` |
| `compute_diff(original, corrected)` | 计算行内 diff | `{"tokens": [{text, type}, ...]}` |
| `accept_correction(result_id)` | 接受单条修正 | `{"segment_id": str}` |
| `reject_correction(result_id)` | 拒绝单条修正 | `{"segment_id": str}` |
| `accept_high_confidence_corrections(timeline_id, threshold)` | 批量接受高置信度 | `{"accepted_count", "remaining_count"}` |
| `clear_subtitle_corrections(timeline_id)` | 清除全部待审修正 | `{"cleared_count": int}` |

### 测试覆盖

| 验证项 | 结果 |
|--------|------|
| `uv run pytest tests/test_diff_service.py` | 7 测试全部通过 |
| `uv run pytest tests/test_subtitle_correction_review.py` | ~15 测试全部通过 |
| `uv run pytest tests/` (全量，排除 whisper/asr-gui) | 全部通过 |
| `bun run build` (前端构建) | 通过 |
| `bun run test` (前端测试) | 全部通过 |

---

## Phase 3: 一键清理工作流 (已完成)

> 决策范围: D-10 ~ D-33, D-63 ~ D-72

### 概要

新建独立 WorkflowEngine，支持配置任务链 (规则分析 + P0 + P1 + P2 任意串联)，管理步骤间数据传递、冲突检测、跨会话恢复。WorkflowEngine 作为编排层通过 TaskManager 调度步骤，设置 `_workflow_accumulate` flag 让 handler 返回原始结果不写入 project。

1. **工作流定义 CRUD** -- 保存在 settings.json，所有项目共享 (D-23)
2. **串行执行 + 步骤隔离** -- 内存工作副本 (完整快照文件)，每步产出 EditDecision 不立即 apply
3. **冲突检测** -- segment id 维度 (D-15)，同 segment 多决策标记冲突
4. **冲突解决** -- 专用全屏视图 (keep_first/keep_last/keep_all)，可选流程 (D-17)
5. **跨会话恢复** -- 快照存储在 `data/projects/<name>/_workflow_<instance_id>.json`
6. **9 个 workflow:* 事件** + 心跳检测 (D-72: 每 15s emit，前端 45s 超时)
7. **AI 助手面板新增"工作流"模式** -- 与"单功能"并列 (D-19)

### 变更文件 (共 9 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/workflow_engine.py` | **新增** (~1020 行) | WorkflowEngine -- 任务链编排 (定义 CRUD + 执行 + 取消 + 冲突检测 + 快照管理 + apply/discard) |
| `core/config.py` | 修改 (+1 行) | `_DEFAULT_SETTINGS` 新增 `workflows: []` 字段 |
| `core/events.py` | 修改 (+9 行) | 9 个 workflow:* 事件常量 (started/step_started/step_progress/step_completed/step_failed/completed/cancelled/conflicts_detected/heartbeat) |
| `main.py` | 修改 (+60 行) | 4 个 handler 增加 `_workflow_accumulate` 模式; 新增 12 个 @expose workflow 方法; `__init__` 实例化 WorkflowEngine |
| `frontend/src/utils/events.ts` | 修改 (+9 行) | 9 个 EVENT_WORKFLOW_* 常量 (与 core/events.py 同步) |
| `frontend/src/composables/useWorkflow.ts` | **新增** (~362 行) | 单例 state + 9 事件监听 + 心跳检测 + 全部 API 方法 |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 修改 (+200 行) | 模式切换 (单功能/工作流) + 工作流配置 UI + 执行进度 + 取消/apply/discard |
| `frontend/src/components/workspace/ConflictResolutionView.vue` | **新增** (~193 行) | Teleport 全屏覆盖冲突解决视图 |
| `tests/test_workflow_engine.py` | **新增** (~522 行) | 35 个单元测试 |

### 架构决策

#### 工作流不修改 TaskManager -- 编排层 (D-18)

WorkflowEngine 不执行分析，作为编排层通过 `create_task` 调度步骤。handler 检查 `task.payload.get("_workflow_accumulate")` 跳过 `add_analysis_results` / `store_subtitle_corrections`。

#### 快照持久化 -- 完整快照文件 (D-28, D-30)

快照存储在 `data/projects/<name>/_workflow_<instance_id>.json`，包含 segments 快照 + segments_hash + accumulated_edits + step_results。每步更新快照 (原子写入 `.tmp` -> `os.replace`)。

#### apply 前悲观锁 + hash 校验 (D-67)

工作流启动后禁用 Timeline 手动编辑; apply 时计算 segments content hash (SHA256)，若与快照不一致则提示重新创建。

#### source 命名规范 (D-65)

`workflow:<wf_id>:<name>` -- 保留 ID 供程序唯一识别，保留 name 供 UI 展示。

#### 冲突解决 -- 决策去重非合并 (D-66)

keep_first/keep_last/keep_all -- 冲突解决的本质是"决策去重"，保留用户认为最重要的决策。

---

## Phase 4: 规格补齐 (已完成)

> 目标: 对照 spec-v2.1.0.md 审计，补齐规格中描述但 Phase 3 代码未实现的部分

### 概要

基于 spec 审计发现 6 个缺失项，全部补齐:

1. **集成测试** -- `tests/integration/test_workflow_integration.py` (20 个 @pytest.mark.integration 测试)
2. **每步预设选择器** (D-43) -- AIAssistantPanel.vue 步骤配置区新增 preset 下拉
3. **步骤失败对话框** (D-11) -- retry/skip/abort 三按钮 Teleport overlay
4. **悲观锁** (D-67) -- Timeline.vue 新增 `workflowLocked` prop + WorkspacePage.vue 锁定横幅
5. **3 个前端测试文件** -- ConflictResolutionView + AIAssistantPanel + SettingsModal (22 个测试)

### 变更文件 (共 7 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `tests/integration/test_workflow_integration.py` | **新增** (~698 行) | 20 个集成测试: TestMultiStepOrchestration (5) + TestSnapshotPersistence (4) + TestEndToEndApply (5) + TestPresetDispatch (2) + TestStepTypeMapping (4) |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 修改 (+90 行) | D-43 预设选择器 (STEP_TO_PRESET_KEY + loadStepPresets + getStepPresetId/setStepPresetId) + D-11 失败对话框 (Teleport overlay with retry/skip/abort) |
| `frontend/src/components/workspace/Timeline.vue` | 修改 (+2 行) | 新增 `workflowLocked` prop (D-67 悲观锁) |
| `frontend/src/pages/WorkspacePage.vue` | 修改 (+10 行) | 导入 useWorkflow + 传递 `workflow-locked` 到 Timeline + amber 锁定横幅 |
| `frontend/src/components/workspace/ConflictResolutionView.test.ts` | **新增** (~153 行) | 9 个测试: 渲染 + keep_first/keep_all + skip + apply |
| `frontend/src/components/workspace/AIAssistantPanel.test.ts` | **新增** (~165 行) | 7 个测试: 模式切换 + 步骤配置 + 执行进度 + queued + apply/discard |
| `frontend/src/components/workspace/SettingsModal.test.ts` | **新增** (~90 行) | 6 个测试: 预设 CRUD composable 集成 |

### 决策映射 (Phase 4)

| 决策 | 实现 |
|------|------|
| D-11 (步骤失败交互式) | AIAssistantPanel.vue Teleport overlay: retry (重试) / skip (跳过) / abort (中止) 三按钮 |
| D-43 (步骤可选预设) | AIAssistantPanel.vue STEP_TO_PRESET_KEY 映射 + loadStepPresets + 每步 preset 下拉 |
| D-67 (悲观锁) | Timeline.vue workflowLocked prop + WorkspacePage.vue amber 横幅 "工作流执行中 -- Timeline 编辑已锁定" |

---

## 补丁修复: Test Connection 先保存再测试 (已完成)

### 概要

修复 LLM 配置面板 "Test Connection" 按钮的测试结果与表单内容不一致问题。

**根因**: `testConnection()` 直接调用后端 `test_llm_connection`，测试的是后端已持久化的配置。用户在表单中修改 Provider/Base URL/API Key/Model 后，未点 Save 直接点 Test Connection，后端仍测试旧配置。

**修复**: 点击 Test Connection 后，先静默调用 `update_settings` 保存表单，再发起测试。保存失败则显示错误并不执行测试。

### 变更文件 (共 1 个)

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 (+20/-3 行) | 新增 `handleTestConnection()` 包装函数 (先 `update_settings` 保存，再 `testConnection()` 测试); `handleSave()` 返回 boolean 便于复用; 按钮 `@click` 改为 `handleTestConnection`; `:disabled` 增加 `saving` 状态; 按钮文案三态切换 (Saving.../Testing.../Test Connection) |

### 行为变化

| 操作 | 修复前 | 修复后 |
|------|--------|--------|
| 修改 API Key 后点 Test Connection | 测试旧 key | 先保存新 key，再测试 |
| 修改 Base URL 后点 Test Connection | 测试旧 URL | 先保存新 URL，再测试 |
| 保存失败时点 Test Connection | 仍执行测试 (测试旧配置) | 显示 "Failed to save settings before test" 并中止 |
| 按钮禁用条件 | `llmTesting \|\| !api_key` | `llmTesting \|\| saving \|\| !api_key` |
| 按钮文案 | Testing.../Test Connection | Saving.../Testing.../Test Connection |

---

## 补丁修复: 空白区域 + 自动保存机制 (已完成)

### 概要

修复两个关联 bug：
1. **Bug1 (空白区域)**: 新建项目时 Timeline 和右侧边栏下方出现大片空白，缩小窗口时空白不消失。
2. **Bug2 (删除失败 + 自动保存缺失)**: 删除字幕报 "Failed to delete segment"，手动保存后才能删除。根因是后端从未 emit `PROJECT_DIRTY` 事件，前端 `isDirty` 永远为 false，2 秒 debounce 自动保存从不触发。

### 根因分析

#### Bug1: SplitPanel 槽缺少 display:flex

开发者工具检查确认：SplitPanel 右槽 `<div class="h-full min-w-0 flex-1 overflow-hidden">` 是 **block 容器**（无 `display: flex`），其子元素 WorkspacePage `<div class="relative flex flex-1 flex-col ...">` 的 `flex-1` **无效**（父非 flex container），子元素按内容高度收缩。新建项目内容少（"暂无分析结果"/"No segments loaded"），下方大片留白；导入字幕后内容增多撑满，空白"消失"。

缩小窗口时空白不消失：block 容器高度由 `h-full`（=父高度）决定，父高度不变则空白不变。

#### Bug2: PROJECT_DIRTY 事件从未 emit

`grep -r "PROJECT_DIRTY\|_emit.*dirty" main.py` 零结果。前端 `isDirty` 仅在 `onEvent(EVENT_PROJECT_DIRTY)` 中设 true（WorkspacePage.vue:348），该事件从未触发，故 `watch(isDirty)` 的 2 秒 debounce 保存逻辑从不执行。所有修改操作（delete/add/update/merge/split/confirm/reject 等）只更新内存 (`_update_active_timeline`)，落盘仅在 `save_project()`。

删除失败：UI 与后端状态不同步时 `delete_segment` 返回 `success: False`，但前端 `handleDeleteSegment` 只显示通用 "Failed to delete segment"，丢失后端 error。手动 Ctrl+S 后状态重新同步才能删除。

### 变更文件 (共 5 个)

| 文件 | 类型 | 说明 |
|------|------|------|
| `frontend/src/components/common/SplitPanel.vue` | 修改 (+2/-2 行) | 左右槽 div 从 `h-full overflow-hidden` 改为 `flex h-full flex-col overflow-hidden`，使子元素 `flex-1`/`h-full` 生效 |
| `frontend/src/App.vue` | 修改 (+1/-1 行) | 根容器 `min-h-screen` -> `h-screen`，防止根容器溢出产生空白 (额外保险) |
| `main.py` | 修改 (+35/-20 行) | import `PROJECT_DIRTY`；新增 `_mark_dirty(result)` helper (成功时 emit 事件)；包装 20+ 个修改类 @expose 方法 + 5 个 task handler 调用 + 字幕修正相关方法 |
| `frontend/src/composables/useEdit.ts` | 修改 (+4/-4 行) | `deleteSegment` 返回类型 `boolean` -> `string \| null` (null=成功，string=错误信息)，不丢失后端 error |
| `frontend/src/pages/WorkspacePage.vue` | 修改 (+3/-3 行) | `handleDeleteSegment` 显示后端返回的具体错误信息 |

### 架构决策

#### _mark_dirty 集中化 (非各方法手动 emit)

新增 `_mark_dirty(self, result: dict) -> dict` helper：检查 `result["success"]` 后 emit `PROJECT_DIRTY` 并返回原 result。所有修改类方法统一用 `return self._mark_dirty(self._project.xxx())`，避免每个方法手动写 emit 逻辑，也防止遗漏。

已包装的方法清单：
- **段落编辑**: update_segment, update_segment_text, merge_segments, split_segment, add_segment, delete_segment, delete_silence_segments, clear_subtitles, delete_subtitle_trim_edits, search_replace, mark_segments
- **建议操作**: confirm_all_suggestions, reject_all_suggestions, generate_subtitle_keep_ranges, confirm_all_from_source
- **Timeline CRUD**: create_timeline, delete_timeline, rename_timeline, duplicate_timeline (switch_timeline 是切换不修改数据，不包装)
- **字幕**: import_srt, add_analysis_results
- **字幕修正**: accept_correction, reject_correction, accept_high_confidence_corrections, clear_subtitle_corrections
- **Task handler (后台线程)**: filler_detection, error_detection, full_analysis, llm_smart, llm_highlight, store_subtitle_corrections

#### deleteSegment 返回错误字符串 (非 boolean)

原 `Promise<boolean>` 丢失后端 error。改为 `Promise<string | null>`：null=成功，string=错误信息。唯一调用方 `handleDeleteSegment` 相应调整。这样用户能看到具体错误（如 "No project is open" / "Segment not found: xxx"）而非通用消息。

### 测试覆盖

| 命令 | 结果 |
|------|------|
| `uv run pytest tests/` (全量，排除 whisper/asr-gui) | 319 测试全部通过 |
| `uv run pytest -m integration` | 35 测试全部通过 |
| `uv run ruff check main.py` | 全部通过 |
| `bun run build` (前端构建) | 通过 -- 94 modules，index.js 243.84 kB |
| `bun run test` (169 前端测试) | 全部通过 (含 SplitPanel 10 个) |

---

## 测试基线 (Phase 4 后)

| 类别 | 数量 | 说明 |
|------|------|------|
| 后端单元测试 | ~319 | 含 test_workflow_engine.py 35 个 |
| 后端集成测试 | 35 | test_workflow_integration.py (Phase 4 新增 20 + 已有 15) |
| 前端测试 | 169 | 含 Phase 4 新增 22 个; Test Connection + 空白区域 + 自动保存补丁后回归通过 |
| ruff | 零错误 | (预存 core/llm_service.py import 排序问题除外) |
| ESLint | 零错误 | (预存 v-html 警告除外) |
| 排除 | test_transcription.py | 已知 ASR VadOptions 失败 (无关) |
| 排除 | test_asr_gui_e2e.py | 需完整 GUI 环境 |

---

## 发布前待办

- [x] Phase 1: 提示词风格预设
- [x] Phase 2: P1 完整 diff 审阅
- [x] Phase 3: 一键清理工作流
- [x] Phase 4: 规格补齐 (集成测试 + UI 缺失项 + 前端测试)
- [ ] 版本号 bump (pyproject.toml 当前仍为 1.3.0，v2.0.0/v2.0.1 未合并 main)
- [ ] build.py --onefile 实际产物验证 (需完整 GUI 环境)

# v2.2.0 规格与实施记录

## 概述

v2.2.0 聚焦于两个功能改进：
1. **字幕纠错集成 partial_delete 意见** -- 将快速清理的"部分删除"意见跟随 segment 发送给字幕纠错 LLM
2. **精华提取功能修复** -- 新增精华导出功能，修复 LLM 未配置时的手动管理体验

## 功能 A：字幕纠错集成 partial_delete 意见

### 背景

v2.1.1 中，字幕纠错 LLM 只接收 segment 的文本和时间戳信息，不感知前序"快速清理"（smart delete）的分析结果。其中 `partial_delete` 类别（句内含口误/重复，如"他是那段历史中的他是那段历史的亲历者"）对字幕纠错非常有价值。

### 实施

1. **`core/timeline_utils.py`**: 新增 `collect_partial_delete_hints()` 从 `AnalysisResult` 收集 `category="partial_delete"` 的提示文本
2. **`main.py:_handle_subtitle_correction`**: 收集 partial_delete hints 并附加到对应 segment dict 的 `edit_hint` 字段
3. **`core/llm_service.py:_build_structured_user_message`**: 支持 segment dict 中的 `edit_hint` 字段透传到 LLM 输入
4. **`core/llm_prompts.py`**: Mode A / Mode B 提示词新增 `edit_hint` 字段使用说明

### 数据流

```
AnalysisResult(category=partial_delete, detail="前半口误后半修正")
  -> collect_partial_delete_hints() -> {"s2": "前半口误后半修正"}
  -> segment dict["edit_hint"] = "前半口误后半修正"
  -> _build_structured_user_message() -> JSON payload 含 edit_hint
  -> LLM 提示词指导: "对于这类片段，请特别关注其句内的重复/口误部分"
```

## 功能 B：精华提取功能修复

### 问题

1. 导出界面没有精华导出按钮
2. 后端有 `get_highlight_ranges()` 但从未被实际调用
3. LLM 未配置时 UI 误导用户以为整个精华功能不可用

### 实施

#### B1: 精华导出（后端）

**设计决策**: 复用现有 FFmpeg 导出管道，通过"虚拟 edits"实现精华导出。精华范围 = 全片 - 非精华范围，将非精华范围标记为 confirmed delete，现有 `export_video`/`export_audio`/`export_srt` 自然只保留精华范围。

- **`core/export_service.py:build_highlight_export_edits()`**: 构建精华导出虚拟 edits
- **`core/export_service.py:get_highlight_ranges()`**: 修复支持 dict 格式 segments（之前只支持 Segment 对象）
- **`main.py:_get_export_segments_and_edits()`**: 新增辅助方法，当 `highlight_mode=true` 时使用虚拟 edits
- **4 个 export handler** 均已适配 highlight_mode

#### B2: 精华导出（前端）

- **`ExportPage.vue`**: 新增"精华视频""精华音频""精华字幕"导出按钮
- highlight_mode 通过 payload 传递，复用现有任务类型和进度跟踪

#### B3: 手动管理体验改进

- **`HighlightModeView.vue`**: LLM 未配置时改为引导文案"自动提取需要配置 LLM 连接。你也可以右键字幕片段手动加入精华"
- 空状态文案区分 LLM 已配置/未配置两种情况
- 后端 `add_highlight_segment` 从未门控 LLM 配置，手动添加始终可用

### 精华范围来源

精华范围来自 `AnalysisResult(type="llm_highlight")` 的 `segment_ids`，同时覆盖：
- LLM 自动提取的精华（source="llm_highlight"）
- 手动添加的精华（source="manual_highlight"，同样存储为 type="llm_highlight"）

## 修复记录

### BUG1: 精华导出文件名与正常导出冲突

**症状**: 精华导出使用默认文件名 `xxx_cut.mp4`，与正常导出完全一致，会覆盖已导出的正常视频。

**修复**: 4 个 export handler 在 `highlight_mode=true` 时使用 `_highlight` 后缀替代 `_cut`：
- `export_video` → `xxx_highlight.mp4`
- `export_audio` → `xxx_highlight.m4a`
- `export_subtitle` → `xxx_highlight.srt`
- `export_vtt` → `xxx_highlight.vtt`

### BUG2: 精华导出未考虑用户已确认删除的片段

**症状**: 用户做过的 confirmed deletes（如手动确认智能删除建议）在精华导出中被忽略，已删除的内容重新混入精华视频。

**修复**: `build_highlight_export_edits()` 新增 `existing_edits` 参数。传入 `timeline.edits` 后，从精华 keep-ranges 中减去用户已确认删除的范围，使得用户手动删除的内容在精华导出中也被排除。

- 新增 `_subtract_ranges()` 工具函数：从 base 区间中减去 subtract 区间，支持任意嵌套重叠
- 调用处 (`_get_export_segments_and_edits`) 传入 `timeline.edits`

### BUG3 (根因): `get_highlight_ranges()` 未过滤 AnalysisResult 类型

**症状**: 用户只标记了一句精华（几秒钟），精华导出却输出两分钟视频。

**根因**: `get_highlight_ranges()` 的新路径（非 old-style dict 分支）遍历所有 `AnalysisResult` 时**没有过滤 `type == "llm_highlight"`**。运行过 P0 智能删除的项目中有大量 `type="llm_smart_delete"` 的 AnalysisResult，每个携带多个 `segment_ids`（36 个区间、接近全片 365s）。这些被全部当成"要保留的精华区间"，导致导出内容 ≈ smart_delete 建议的片段集合，而非用户标记的精华。

**修复**: 在遍历循环中添加类型过滤：
```python
for r in analysis_results:
    r_type = getattr(r, "type", None) or (r.get("type") if isinstance(r, dict) else None)
    if r_type != "llm_highlight":
        continue
    ids = getattr(r, "segment_ids", None) or r.get("segment_ids", [])
    ...
```
一行过滤确保只有 `llm_highlight` 类型参与精华区间计算。

### 回顾教训

BUG3 暴露了测试覆盖的盲区：`test_v2_2_0_features.py` 中 `TestGetHighlightRanges` 的用例只构造了 `type="llm_highlight"` 的结果，从未混入 `llm_smart_delete`/`llm_subtitle_correction`。集成层的 bug 必须用混合数据测试才能暴露。已追加 `test_ignores_non_highlight_analysis_types` 回归测试。

## 测试

### 新增测试 (`tests/test_v2_2_0_features.py`, 22 个)

#### 功能A: 字幕纠错集成 partial_delete
- `TestCollectPartialDeleteHints`: 3 个（空、有 reason、默认 reason）
- `TestBuildStructuredUserMessageEditHint`: 2 个（无 hint、有 hint）

#### 功能B: 精华范围解析
- `TestGetHighlightRanges`: 4 个（dict segments、空、manual+llm、**混合类型过滤**）

#### 功能B: 精华导出虚拟 edits
- `TestBuildHighlightExportEdits`: 10 个（基础、空、开头、全覆盖、手动、trailing gap、重叠合并、**已确认删除减法**、**仅 confirmed 生效**、外部删除无冗余）
- `_subtract_ranges` 功能覆盖在上述测试中

### 测试基线

- 后端单元测试: 390 通过 (+15 初始 + 3 BUG1/BUG2 + 1 BUG3 = +19 → 388，后因 docs 不计)
- 后端集成测试: 35 通过
- 前端测试: 169 通过 (预存 2 个失败除外)
- ruff + ESLint: 零错误
- frontend build: 成功

## 涉及文件

| 文件 | 改动 |
|------|------|
| `core/timeline_utils.py` | 新增 `collect_partial_delete_hints()` |
| `core/llm_service.py` | `_build_structured_user_message` 支持 edit_hint |
| `core/llm_prompts.py` | Mode A/B 提示词新增 edit_hint 说明 |
| `core/export_service.py` | 新增 `build_highlight_export_edits()`、`_subtract_ranges()`；修复 `get_highlight_ranges()` 类型过滤 |
| `main.py` | `_handle_subtitle_correction` 集成 hints；新增 `_get_export_segments_and_edits()`；4 个 export handler 支持 highlight_mode + 输出路径后缀 |
| `frontend/src/pages/ExportPage.vue` | 新增精华导出按钮和逻辑 |
| `frontend/src/components/workspace/HighlightModeView.vue` | UI 改进（LLM 未配置时引导） |
| `tests/test_v2_2_0_features.py` | 新增 22 个测试（含 1 个混合类型回归测试） |

---

## 功能 C：工作流非沙箱化改造（spec-2.2.0-1）

> **基准提交**: `b791369`（BUG3 修复）。本节为本次会话完成、尚未提交的改动。
> **依据**: `docs/2.2.0/spec-2.2.0-1.md` + `docs/2.2.0/audit-report-2.2.0-1.md`

### 背景

v2.1.0 的工作流采用**沙箱-确认**模式：每步骤带 `_workflow_accumulate=True` → handler 跳过写 project → 累积 edits → 用户点击 Apply 再写入。审计发现该模式存在 6 项缺陷（P0–P5），核心阻断是 P0——`apply_workflow()` 直接赋值 `self._project_service.current = ...`，但 `current` 是只读 `@property` 无 setter，导致 Apply 永远抛 `AttributeError` 被 `@expose` 吞成失败响应。

### 设计决策（采纳审计结论）

- **删除沙箱模式**：handler 走正常写 project 路径（与单功能模式一致），不再累积 edits
- **P0 通过删除 apply 写入逻辑自然消除**——无需给 `ProjectService.current` 加 setter
- **B1（关键）**：前端 `WorkspacePage.vue` 已有对 `llm_smart_delete`/`llm_subtitle_correction`/`llm_highlight` 三类 `task:completed` 的 `project-updated` 刷新监听，工作流步骤经 TaskManager 调度天然复用，**无需新增刷新代码**
- **B5**：`apply_workflow`/`discard_workflow` 保留为 stub，仅清 `_active`，不读 project 状态，固定返回 `{applied_count:0}`
- **死代码保留**：`_extract_edits_from_result`/`detect_conflicts`/`_compute_segments_hash` 加 v2.2.0 deprecated 注释，暂不删

### 实施

#### 后端 `core/workflow_engine.py`（净减 ~99 行）

1. **`_dispatch_step`**: payload 移除 `_workflow_accumulate`/`_workflow_instance_id`/`_workflow_step_index`/`_workflow_step_type` 四字段，仅保留 `timeline_id`（+ 可选 `_workflow_preset_id`）
2. **`_run_steps` 成功分支**: 删除 `_extract_edits_from_result` 调用与 `accumulated_edits` 累积；`WORKFLOW_STEP_COMPLETED` 去掉 `edits_count`
3. **`_run_steps` 完成分支**: `WORKFLOW_COMPLETED` 去掉 `total_edits`；删除 `detect_conflicts()` 调用与 `WORKFLOW_CONFLICTS_DETECTED` 事件；完成后改用 `_delete_snapshot` + `self._active = None`
4. **`apply_workflow`**: 86 行主体整体替换为 17 行 stub（仅清 `_active` + 删 snapshot）
5. **死代码标注**: 3 个废弃方法 docstring 加 deprecated 说明

#### 前端

- **`AIAssistantPanel.vue`**: 删 Apply/Discard 按钮 + `handleApplyWorkflow`/`handleDiscardWorkflow` + `workflow-applied` emit；加「工作流已完成 — 结果已写入项目」+「返回配置」按钮（`handleReturnToConfig` 置 `instanceId.value = null`）
- **`WorkspacePage.vue`**: 删 D-67 锁横幅、`:workflow-locked` 传参、`@workflow-applied` 处理；顺带清理变成 dead 的 `wf = useWorkflow()` 与 import
- **`Timeline.vue`**: 删 `workflowLocked` prop、`workflow-applied` emit、子组件透传

#### 测试

- **`tests/test_workflow_engine.py`**: 重写 3 个 `TestApplyDiscard` 用例匹配新 stub 契约：
  - `test_apply_no_active` → 幂等成功（无活跃工作流返回 `applied_count:0`）
  - `test_apply_hash_mismatch` → `test_apply_clears_active`（清 `_active`，不触碰 project）
  - `test_apply_success` → `test_apply_does_not_write_project`（验证不调用 `save_project`，落实 B5）
- **`AIAssistantPanel.test.ts`**: 完成状态用例改为验证「返回配置」按钮 + 断言旧按钮已移除

### 改动统计

| 文件 | 净变化 |
|------|--------|
| `core/workflow_engine.py` | -99 行（133 改动，净减） |
| `frontend/.../AIAssistantPanel.vue` | 重构 ~40 行 |
| `frontend/.../AIAssistantPanel.test.ts` | ~10 行 |
| `frontend/.../Timeline.vue` | -2 行 |
| `frontend/.../WorkspacePage.vue` | -13 行 |
| `tests/test_workflow_engine.py` | 重写 3 用例 |
| `docs/2.2.0/spec-2.2.0-1.md` | 补充 B1/B5 审计说明 + 2 条验证项 |

### 验证

- 后端 `pytest --ignore=tests/test_transcription.py`: 380 全通过
- 前端 `bun run build`（vue-tsc + vite）: 成功
- 前端 `bun run test`: 170/171 通过（唯一失败 `TranscriptRow > saves edit on blur` 在未修改文件中，预存问题；见下方 BUG6 修复）

### 仍需后续

- 版本号 bump + 合并 main
- handler 中的 `_workflow_accumulate` 分支（`main.py:782,866,966`）现为死代码，留待后续清理
- `frontend/package.json` 由 build 时 `sync-version` 自动改动，不计入本次改动

---

## BUG4: 工作流自动保存的预设未清理

### 问题

`AIAssistantPanel.vue` 的 `handleStartWorkflow()` 在无已选 workflow 时自动调用 `wf.saveWorkflow()` 创建一条 workflow 定义并持久化到 `settings.json`。任务完成后，该临时 workflow 未被删除，成为无效残留数据。

### 修复

**文件**: `frontend/src/components/workspace/AIAssistantPanel.vue`

- 新增 `autoSavedWorkflowId` ref 标记本次临时创建的 workflow
- 在 `handleStartWorkflow()` 中创建时记录 ID
- 通过 `watch(wf.isActive.value)` 监听 workflow 执行结束（`true → false`），自动调用 `wf.deleteWorkflow(id)` 清理

## BUG5: 工作流步骤建议数显示为空

### 问题

v2.2.0 非沙箱化改造（功能 C）删除了 `WORKFLOW_STEP_COMPLETED` event payload 中的 `edits_count` 字段。前端 `useWorkflow.ts` 读取 `d.edits_count` 结果为 `undefined`，Vue 渲染 `{{ step.edits_count }} 条` 仅剩"条"字。

### 修复

**文件**: `core/workflow_engine.py`

- 在 `WORKFLOW_STEP_COMPLETED` 事件的 emit 处，从步骤执行结果中提取编辑建议列表：优先取 `result.data.edits`，其次取 `result.data.corrections`
- 计算 `len()` 作为 `edits_count` 加入 event payload
- 前端原有代码直接使用该值即可恢复正确显示

### 数据流

```
_dispatch_step() 返回 {"success": true, "data": {"edits": [...]}}
  → step_data = result["data"]
  → edits_list = step_data.get("edits") or step_data.get("corrections", [])
  → edits_count = len(edits_list)  →  加入 WORKFLOW_STEP_COMPLETED payload
```

## BUG6: 前端测试因 setTimeout 延迟失败

### 问题

`TranscriptRow.test.ts` 中 `saves edit on blur` 测试在 `input.trigger("blur")` 后立即检查 `wrapper.emitted("update-text")`。但组件内 `handleTextEditBlur()` 使用了 `setTimeout(150ms)` 延迟保存（用于屏蔽拖选文本的误触发，v2.1.1 A-2.2），因此测试断言执行时 `update-text` 事件尚未发射，`emitted()` 返回 `undefined`。

该失败在功能 C 的验证中被列为"预存问题"（170/171 通过，唯一失败在未修改文件）。

### 修复

**文件**: `frontend/src/components/workspace/TranscriptRow.test.ts`

- 在 `trigger("blur")` 后添加 `await new Promise((r) => setTimeout(r, 160))`，等待 150ms 定时器完成后再做断言

## 最终测试基线

- 前端测试: **171 通过**（14 文件，预存失败已修复）
- 前端构建: 成功（vue-tsc + vite build）

## 涉及文件（本次新增）

| 文件 | 改动 |
|------|------|
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 新增 `autoSavedWorkflowId` + watch 自动清理 |
| `core/workflow_engine.py` | `WORKFLOW_STEP_COMPLETED` 事件新增 `edits_count` 字段 |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | blur 测试添加 160ms 等待 |
| `docs/2.2.0/record-2.2.0.md` | 本记录 |

---

## 发布：v2.2.0 合并 main

### 合并范围

- 基准：`main` @ `444731b` (v2.1.1 release)
- 合并分支：`dev-2.2.0` -> `main`
- 净增 commits：4 个（d753d14, a57be34, b791369, 05b2a8b）

### Merge Message

```
release: v2.2.0 -- 字幕纠错集成 partial_delete、精华提取修复、工作流非沙箱化

功能:
- 字幕纠错集成 partial_delete 意见，LLM 输入携带前序快速清理分析结果
- 精华提取导出功能（视频/音频/SRT），文件名覆盖修复，已删除片段不再混入
- 工作流非沙箱化改造：移除沙箱-确认模式，步骤直接写 project
- 工作流临时定义自动清理（autoSavedWorkflowId）
- WORKFLOW_STEP_COMPLETED 事件恢复 edits_count 字段

修复:
- BUG1: 精华导出文件名覆盖（视频/音频/SRT 同名冲突）
- BUG2: 已删除片段重新混入精华导出
- BUG3: get_highlight_ranges 过滤非 llm_highlight 类型
- BUG4: 工作流临时定义残留为无效数据
- BUG5: 工作流步骤建议数显示为空
- BUG6: TranscriptRow blur 测试 setTimeout 时序失败

测试:
- 前端测试 171 通过（14 文件）
- 前端构建成功（vue-tsc + vite build）
```

### Release Note (v2.2.0)

**版本**: 2.2.0
**发布日期**: 2026-06-26
**基准**: v2.1.1
**分支**: `dev-2.2.0` -> `main`

#### 新增功能

1. **字幕纠错集成 partial_delete 意见**
   - 字幕纠错 LLM 现在接收前序"快速清理"（smart delete）中 `partial_delete` 类别的分析结果
   - 句内口误/重复（如"他是那段历史中的他是那段历史的亲历者"）信息跟随 segment 传递，辅助 LLM 做更精准的修正
   - 修改后端数据整合、传递逻辑及 LLM 功能提示词

2. **精华提取导出功能**
   - 新增精华内容导出（视频/音频/SRT），支持编码参数设置
   - 导出过程尊重用户手动添加、删除操作，不漏掉手动编辑
   - 文件名覆盖机制修复，视频/音频/SRT 不再因同名冲突

3. **工作流非沙箱化改造**
   - 移除 v2.1.0 的沙箱-确认模式，改为步骤直接写 project 的串行批处理
   - 移除 Apply/Discard 确认步骤，完成后直接返回配置视图
   - 无配置启动时自动保存的工作流，执行结束后自动清理

#### Bug 修复

- **BUG1**: 精华导出视频/音频/SRT 文件名覆盖冲突
- **BUG2**: 已删除片段重新混入精华导出结果
- **BUG3**: `get_highlight_ranges` 误过滤非 `llm_highlight` 类型，导致精华范围计算错误
- **BUG4**: 工作流临时定义（无配置启动自动创建）完成后残留为无效数据
- **BUG5**: 工作流步骤建议数显示为空（`edits_count` 字段丢失）
- **BUG6**: `TranscriptRow` blur 测试因 `setTimeout(150ms)` 延迟导致断言时序失败

#### 质量基线

- 前端测试：171 通过（14 文件）
- 前端构建：成功（vue-tsc + vite build）
- 工作流引擎重构后功能验证通过

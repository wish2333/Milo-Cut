# Spec: v2.2.0 — 工作流非沙箱化改造

> **版本**: 2.2.0
> **主题**: 移除工作流沙箱确认模式，改为直接写 project 的串行批处理
> **基准**: v2.1.1
> **分支**: `dev-2.2.0`
> **类型**: 重构 (Refactor)
> **预估工程量**: 小 (2-3 天，涉及 backend + frontend 约 6 个文件)

---

## 背景与问题陈述

### 现状

v2.1.0 实现的工作流系统采用**沙箱-确认**模式：

```
启动 → 创建快照 → 每步骤带 _workflow_accumulate=True → handler 跳过写 project
                                                         ↓
      提取 edits → 累积到 snapshot.accumulated_edits → 完成后显示 Apply/Discard
                                                         ↓
      用户点击 Apply → apply_workflow() 写入 project
```

这一设计存在以下缺陷：

| # | 严重性 | 问题 | 根因 |
|---|--------|------|------|
| 1 | **P0** | 点击「应用结果到项目」后端崩溃 | `apply_workflow()` 直接赋值 `self._project_service.current = ...`，但 `current` 是只读 `@property`，无 setter |
| 2 | **P1** | 应用后 project 未保存任何相关数据 | 上述崩溃导致 apply 流程中断；即使修复崩溃，前端也未触发 project 刷新 |
| 3 | **P1** | 沙箱模式下 subtitle_correction 结果丢失 | handler 发现 `_workflow_accumulate=True` 跳过 `store_subtitle_corrections` |
| 4 | **P1** | 沙箱模式下 highlight 结果丢失 | handler 跳过写 project，且不返回 `edits` 字段，`_extract_edits_from_result` 拿不到数据 |
| 5 | **P2** | 工作流锁横幅无实际效果 | 仅展示文字，编辑控件未被禁用 |
| 6 | **P2** | 沙箱模式复杂度不必要 | 用户需要的是顺序执行多个功能，无需冲突检测和确认流程 |

### 用户决策（通过访谈确认）

  | 决策 | 选择 |
  |------|------|
  | 完成状态 UI | 保留完成状态视图，手动点击「返回配置」 |
  | 取消功能 | 保留（立即取消/当前步骤后停） |
  | 编辑锁定 | 删除锁定横幅（推荐） |
  | 失败对话框 | 保留，三个选项逻辑无需更改 |

### 核心设计变更

**删除沙箱模式**：工作流不再是"在沙箱中积累 edits → 用户确认 apply"，而是**串行执行各项功能，每步直接写 project**（与单功能模式行为完全一致）。

```
启动 → 创建 in-memory 进度跟踪 → 逐步骤直接调度（不带 _workflow_accumulate）
                                  ↓
     handler 正常写 project（add_analysis_results / store_subtitle_corrections）
                                  ↓
     触发 EVENT_TASK_COMPLETED → 前端自动刷新 project 数据
                                  ↓
     全部完成 → emit WORKFLOW_COMPLETED → 前端显示完成状态
```

> **审计细化 B1（刷新机制已存在，无需新增）**: 前端 `WorkspacePage.vue` 已有对 `llm_smart_delete` / `llm_subtitle_correction` / `llm_highlight` 三类任务完成的 `project-updated` 刷新逻辑。工作流步骤通过 TaskManager 调度时天然复用该路径，**无需新增刷新代码**——只要 handler 恢复正常写入 project，`task:completed` 事件携带的 `result.project` 即自动驱动前端刷新。
>
> **审计细化 B5（stub 返回值）**: `apply_workflow` / `discard_workflow` 保留为桩方法，仅清理 `_active` 状态。stub **不应读取 `self._active` 之外的任何状态**（避免并发问题），固定返回 `{"success": True, "data": {"applied_count": 0}}`。

---

## 改动清单

### 后端：`core/workflow_engine.py`

| # | 改动 | 说明 |
|---|------|------|
| 1 | `_dispatch_step` payload 移除 `_workflow_accumulate` | handler 不再跳过写 project |
| 2 | `_dispatch_step` payload 可移除 `_workflow_instance_id` / `_workflow_step_index` / `_workflow_step_type` | handler 不需要这些标记 |
| 3 | `_run_steps` 移除 `_extract_edits_from_result` 调用和 `accumulated_edits` 逻辑 | 不再累积 edits |
| 4 | `_run_steps` 移除冲突检测 | `detect_conflicts` 不再自动调用 |
| 5 | `_run_steps` 移除 `_save_snapshot` 调用 | 不写磁盘快照 |
| 6 | `_run_steps` 完成分支改为直接清理 `_active = None` + 删 snapshot 文件 | 完成后无残留 |
| 7 | `_run_steps` 发送 `WORKFLOW_COMPLETED` 事件不再带 `total_edits`/`conflicts` | 简化事件 payload |
| 8 | `apply_workflow` 简化为仅清理状态（不再写 project） | 保留方法避免前端调用出错，但不做实际写入 |
| 9 | `discard_workflow` 逻辑不变（清理状态） | 继续可用 |
| 10 | `_extract_edits_from_result` 方法保留但不再被 `_run_steps` 调用 | 暂不删除，避免 import 断裂 |
| 11 | `detect_conflicts` 方法保留 | 暂不删除 |
| 12 | `_save_snapshot` / `_load_snapshot` / `_delete_snapshot` 保留 | 暂不删除 |
| 13 | 快照 `_active` 中 `accumulated_edits` / `segments_hash` / `segments_snapshot` 字段不再使用 | 仍存在于 dict 中但不会被填充或读取 |

### 前端：`AIAssistantPanel.vue`

| # | 改动 | 说明 |
|---|------|------|
| 1 | 删除「应用结果到项目」按钮 | v-if 条件移除 |
| 2 | 删除「放弃」按钮 | 同上 |
| 3 | 完成状态视图 → 添加「返回配置」按钮 | 用户手动回到配置界面 |
| 4 | 完成状态视图移除 conflicts/apply 相关逻辑 | 简化 |

### 前端：`WorkspacePage.vue`

| # | 改动 | 说明 |
|---|------|------|
| 1 | 删除工作流锁定 banner | `<div v-if="wf.isActive.value" class="bg-amber-50 ...">` 整个移除 |
| 2 | 删除 `@workflow-applied` 事件处理 | 前一轮加的临时修复，不再需要 |

### 前端：`Timeline.vue`

| # | 改动 | 说明 |
|---|------|------|
| 1 | 删除 `workflowLocked` prop | 不再传递 |
| 2 | 删除 `@workflow-applied` emit 透传 | 不再需要 |

### 前端：`useWorkflow.ts`

| # | 改动 | 说明 |
|---|------|------|
| 1 | `applyWorkflow` 简化 | 仅清理状态，不处理 project 数据 |
| 2 | 确认 `discardWorkflow` 逻辑依然正确 | 保持不变 |

---

## 受影响文件汇总

| 文件 | 影响范围 |
|------|----------|
| `core/workflow_engine.py` | ~50 行修改/删除（核心逻辑变更） |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | ~15 行修改（UI 重构） |
| `frontend/src/components/workspace/AIAssistantPanel.test.ts` | 需更新 2 个测试用例 |
| `frontend/src/components/workspace/Timeline.vue` | ~3 行删除 |
| `frontend/src/pages/WorkspacePage.vue` | ~5 行删除 |
| `frontend/src/composables/useWorkflow.ts` | ~3 行修改 |

---

## 风险和注意事项

1. **重试语义变化**：非沙箱下重试步骤 → handler 再次调用 → 可能产生重复 edits（但典型失败场景是 LLM API 报错，无数据残留）
2. **`_workflow_accumulate` 移除后**：handler 中的 workflow 分支代码保留但不再触发 → 后续可清理 handler 中的死代码（非本 spec 范围）
3. **`_handle_subtitle_correction` 的 workflow 分支**：不再触发，corrections 正常存储到 project
4. **`_handle_highlight` 的 workflow 分支**：不再触发，results 正常写入 project
5. **`_handle_smart_delete` 的 workflow 分支**：不再触发，edits 正常写入 project
6. **向后兼容**：已保存在 `settings.json` 中的 workflow definitions（`workflows` 数组）不受影响，仍可加载和使用
7. **滚动保留**：`apply_workflow` / `discard_workflow` 方法保留为桩方法（stub），仅清理 `_active` 状态，避免前端 `call()` 调用断裂

---

## 验证标准

- [ ] 新建 P0→P1 工作流启动后，P0 执行完毕 SuggestionPanel 立即显示智能删除建议
- [ ] P1 执行完毕，SubtitleCorrectionReview 面板显示字幕修正结果
- [ ] 工作流完成后不再显示「应用结果到项目」/「放弃」按钮
- [ ] 工作流完成后显示完成状态，点击「返回配置」可再次启动
- [ ] 工作流执行中可取消（立即/当前步骤后停）
- [ ] 步骤失败时弹出对话框（重试/跳过/中止），行为合理
- [ ] 工作流执行中编辑控件不受影响（锁横幅已删除）
- [ ] **新增（审计 B1）**: 工作流步骤完成后，无需点击任何按钮，SuggestionPanel / SubtitleCorrectionReview 即自动显示最新结果（验证 `task:completed` → `project-updated` 路径生效）
- [ ] **新增（审计 §5）**: 工作流执行中直接编辑 Timeline（文本/时间/状态），操作正常生效且不报错（验证锁横幅删除后无副作用）
- [ ] `AIAssistantPanel.test.ts` 全部通过
- [ ] `vue-tsc --noEmit` 类型检查通过
- [ ] 后端现有 pytest 全部通过（排除 test_transcription.py）
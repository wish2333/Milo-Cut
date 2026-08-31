# Record: P4-4 M3-6 工作流失败回滚

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M3-6 / PRD A6 / plan P4-4（依赖 P2-1 M5 基建，已就绪）

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/workflow_engine.py` | ①`_create_snapshot` 增 `layer_snapshots`（步骤边界层快照字典，步骤 0 = 工作流前状态，segments 与既有 `segments_snapshot` 共享内存引用、edits 新捕获）；②新增 `_capture_layer_snapshot(timeline_id)`（segments/edits 逐 model_dump，纯 dict 载荷直接兼容跨会话 JSON 往返）；③`_run_steps` 每步派发前捕获一次该步前置快照并即时落盘（retry 复用同快照），失败分支新增 `rollback_step` / `rollback_all` 两动作 → `_rollback_to_step` → 终态 `status="rolled_back"`；④新增 `_rollback_to_step`：**复用 M5 `apply_undo` 通道**（全部层先校验后变更、sort invariant 恢复、revision 严格 +1、patch 信封），回滚前把工作流目标 timeline 置为 active（与批量纠错 accept 同模式）；⑤终态分支：`rolled_back` 发新事件 `WORKFLOW_ROLLED_BACK` 并清理快照文件；⑥失败步 `step_results[].status` 显式记 `failed` |
| `core/events.py` / `frontend/src/utils/events.ts` | 新增 `workflow:rolled_back`（双端同一提交，append-only） |
| `main.py` | `handle_step_failure` @expose 透传新动作（校验在 engine） |
| `tests/test_workflow_engine.py` | +5 条 `TestFailureRollback`（真实 ProjectService + 真实 WorkflowEngine + mock task 层模拟 v2.2.0「handler 直写 project」契约）：回滚本步（**第一步效果保留** + revision 单调 `rev_before < rev_at_failure < rev_after` + 终态/事件断言）、整体回滚（**第一步效果一并撤销**）、**跨会话**（新 engine 实例从磁盘加载快照后回滚成功）、legacy 快照缺 `layer_snapshots` 优雅失败、`handle_step_failure` 接受新动作拒绝非法值 |
| `frontend/src/composables/useWorkflow.ts` | `handleStepFailure` 动作类型扩展；监听 `workflow:rolled_back`（终止运行 UI、关失败弹窗、置 `rolledBack` ref） |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 失败确认弹窗新增「回滚本步」「全部回滚」按钮（琥珀色次级行，title 说明语义）——plan「UI 确认弹窗」的承载面（既有失败弹窗即确认点） |
| `frontend/src/pages/WorkspacePage.vue` | 监听 `workflow:rolled_back` → `get_project` 拉取 → `project-updated` 通道应用 + toast（成功报「已回滚到步骤 N 前」，失败报快照缺失）——复用 P2-2 M4 的 project_stripped 拉取模式 |

## 实现决策（对 plan/SPEC 的偏差记录）

1. **回滚应用复用 `apply_undo` 而非 SPEC 预想的 `export_layer_snapshot`**：M5 实际落地的基建是前端捕获层快照 + 后端 `apply_undo(layers_payload, base_revision)` 单一入口；M3-6 直接对齐既有协议（engine 侧捕获、经 apply_undo 恢复），共享全部红线保证（原子校验/revision 单调/stale 拒绝）。快照载荷为 dict（非引用），天然满足跨会话序列化。
2. **回滚即终态**：两模式执行后工作流以 `rolled_back` 状态结束（不再继续后续步骤），快照文件删除——回滚是对失败的中止式处置；「回滚后重跑」由用户重新发起工作流完成（且此时项目已在期望状态）。
3. **每步全量层快照的体积代价**：1167 段工程每步 ~0.8MB（segments dump），快照文件为运行期临时文件（完成/回滚即删），接受该代价换实现简单与跨会话可靠；`layer_snapshots["0"].segments` 与 `segments_snapshot` 共享内存引用减少一份运行期拷贝。
4. **既有 wart 未动**：失败后选「中止」的历史路径仍以 `completed` 状态收尾（v2.2.0 起行为）；本次只让 `rolled_back` 走明确终态，不扩大改动面。

## 验证命令与实际输出

```
uv run pytest                              -> 598 passed（593 + 5）
uv run ruff check .                        -> All checks passed!
cd frontend && bun run test                -> 343 passed (34 files)
cd frontend && bun run build               -> vue-tsc + vite 通过
bunx eslint <触及 4 文件>                   -> 0 问题
```

## 未验证边界（归批次冒烟 / 真实链路）

- ★ 真实两步工作流（如静音检测 + 智能删除）第二步 mock 失败的 UI 演练（验收方式原文）：自动化已由 handler 级 mock 等价覆盖，真机弹窗→回滚→项目刷新链路归批次冒烟
- 回滚 toast 与项目刷新在千段工程下的观感（get_project 全量拉取，与既有任务完成刷新同成本）
- 跨会话恢复入口（find_resumable_snapshots → resume）与回滚组合的真机路径（快照含 layer_snapshots 已有测试锁定）

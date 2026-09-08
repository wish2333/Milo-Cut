# record-3.0.5-P1-1：R5.0 duplicate 幂等返回防呆（SPEC M5.0；全版首个代码合入步——序 1）

> 步骤：PLAN P1-1 · 依据：[SPEC M5.0](./spec-v3.0.5.md)（实施裁决 1-4 / 触点表）· [PLAN](./plan-v3.0.5.md) P1-1
> 分支：`dev-3.0.5-P1-1`（已合入已删）· 提交：`94c4c91`（代码）→ `ba5a78c`（--no-ff 合入 `dev-3.0.5`，3.0.4 先例 `merge: P<n>-<m> ... 合入`）
> 对应缺陷：F1（数据安全，重复框选/双击/时间码重复提交 → 非法对象进 project-updated 通道）+ F-B-10（失败路径 undo 空步）

## 1. 顺序强制（序 1）核对

- 本步为全版首个代码合入步，先于一切 llm/correction 族改动（其后各 phase 门禁基线自此含 duplicate 态防护）。
- 本步 diff 不触 llm/correction 族：`git diff v3.0.4 --name-only -- core/ main.py` = **空输出**（后端零改动，红线 R0-1 实测 PASS）。
- 与 P1 其余项零冲突：改动面 = 前端 4 文件（WorkspacePage.vue / useUndoRedo.ts + 两测试宿主），与 R5.1-R5.13 触点无交集。

## 2. 改动清单（逐 hunk）

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `frontend/src/composables/useUndoRedo.ts` | :60-79（pushSnapshot 后插入） | 纯新增 `popSnapshot(): UndoRecord \| null`——undoStack 移除末条并返回之，空栈返回 null；docstring 写明 SG-6 不变量（**不触碰 redoStack**：pop 仅发生在「本次 push 之后、响应返回前」的同步窗口，该窗口内 redoStack 已被 pushSnapshot :57 清空且无再入路径） | 只增（前端面） |
| `frontend/src/composables/useUndoRedo.ts` | return 块 | 导出 `popSnapshot` 一行 | 只增（前端面） |
| `frontend/src/pages/WorkspacePage.vue` | :173 | 解构增 `popSnapshot`（useUndoRedo() 返回对象消费面） | 受控改点 (c) 前端面 |
| `frontend/src/pages/WorkspacePage.vue` | :994-1013（handleRangeDecision） | **受控改点 (c) 三分支化**：① duplicate（`res.success && res.data?.duplicate === true`，TS 面以 `{ duplicate?: boolean }` 局部窄化访问，ProjectPatch 类型零改动）→ 不 emit project-updated + `popSnapshot()` + `showToast("该范围已存在，已复用原条目", "info", 2500)`（轻提示自动消退，useToast 既有 info 态，零新增组件）；② 成功 → `if (res.success && res.data) { emit("project-updated", res.data) }` **逐字节不变**（SPEC M5.0 裁决 1② / PRD R5.0 ②字面锁定）；③ 失败 → toast 文案/级别/时长不变 + 前置 `popSnapshot()`（消除 F-B-10 undo 空步） | 受控改点 (c) |
| `frontend/src/pages/WorkspacePage.rangeDecision.test.ts` | mock 脚手架 | useUndoRedo mock 增 `popSnapshot: popSnapshotMock` 键 + `undoStack: undoStackRef`（模块级可观测 ref）；beforeEach 增两项 reset（非 expect 行，测试基建，3.0.4 §4.1 追认制口径无需登记——本文件无断言反转） | 只增（测试基建） |
| `frontend/src/pages/WorkspacePage.rangeDecision.test.ts` | 文件尾新增 describe | 3 新例（见 §3），既有 describe「WorkspacePage range decision (M4-2)」整块零改动 | 只增 |
| `frontend/src/composables/useUndoRedo.test.ts` | shared state describe 后新增 describe | 3 单元例（见 §3），既有 16 例零改动 | 只增 |

**两入口一处生效**（SPEC M5.0 裁决 4）：波形气泡与 SuggestionPanel 时间码 popover 共用同一 handleRangeDecision（provide `suggestion:add-range-decision` :958 / `@range-decision` :1619），分支改动天然覆盖双入口，未逐入口改码。

## 3. 用例登记（M-gate 前端 R5.0 ≥3，实际 +6）

| # | 宿主 | 用例 | 断言要点 |
|---|---|---|---|
| 1 | WorkspacePage.rangeDecision.test.ts | duplicate branch: the non-patch envelope never enters project-updated | project-updated 零新增（内存态不变）；toast = 「该范围已存在，已复用原条目」info/2500 一次；popSnapshot 恰一次 |
| 2 | 同上 | duplicate path restores the undo stack length | 预置 1 条历史 + push/pop 接线可观测栈：duplicate 后栈长度恢复 = before，prior 历史不损 |
| 3 | 同上 | failure path restores the undo stack length (F-B-10) | 失败后栈长度恢复 = before；toast 仍为既有 error 形态（M5.0 裁决 1③） |
| 4 | useUndoRedo.test.ts | pops the last pushed record, returns it and leaves the stack one shorter | 真实实现：末条弹出并返回（label + records 键集 = ["edits"]），前序记录存活 |
| 5 | 同上 | returns null on an empty stack (defensive path) | 空栈防御路径 null |
| 6 | 同上 | does not touch redoStack (SG-6) | 同步窗口内 redoStack 保持空——SG-6 不变量直证 |

既有例核对：rangeDecision.test.ts 前 2 例（:271/:321 原例，现位于 M4-2 describe 内零位移零改动）全绿；useUndoRedo.test.ts 既有 16 例全绿。

## 4. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  833 passed in 7.06s                        # pytest 全绿（后端零改动，= 基线 833）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====                           # bun 路径（本环境可用，record §2 勘误口径）
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 845 passed (846)    # 基线 840/839 + 6 新例；唯一失败 = useRowLayout.perf 环境例（豁免口径，脚本判定 PASS）
  [PASS] vitest 唯一失败 = useRowLayout.perf.test.ts (已登记环境例) 845/846
  ✓ built in 3.19s                           # vue-tsc --noEmit + vite build 通过
  [PASS] build 通过 / lint 0/0               # eslint 0 errors 0 warnings
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 为空                       # R0-1：core/ main.py 零改动（N3：不补 revision）
  [PASS] 禁改面为空
  [PASS] R0-2 events 双侧零改动
  [PASS] 后端断言白名单外零删改               # 本步 tests/ 零改动
  [PASS] 前端断言白名单外零删改               # 本步零 expect 删改（纯增）
  [INFO] config/llm_prompts diff 为空（逐行核对：无 diff）
  [PASS] dev.py / build.py 零改动
===== 门禁汇总: 全部通过 (exit 0) =====
```

目标文件先行验证：`vitest run src/pages/WorkspacePage.rangeDecision.test.ts src/composables/useUndoRedo.test.ts` → 2 files / 24 tests 全绿（5 = 既有 2 + 新 3；19 = 既有 16 + 新 3）。

## 5. 断言反转清单（M0-3 白名单核对）

本步**零反转**：不涉 test_llm_translation.py / AIAssistantPanel.test.ts / SegmentBlocksLayer.test.ts；前端 expect 删改 grep 命中 0（门禁 R0-3 PASS 实证）。

## 6. 未验证边界

- **真机双入口手感**（波形气泡 + SuggestionPanel 时间码 popover 的重复框选/双击/时间码重复提交三场景）：留待 beta.1 真机冒烟轮（PLAN 真机冒烟清单 beta.1 首项），单测已锁行为面（不 emit / 轻提示 / 栈恢复）。
- **popSnapshot 防御路径**（空栈返回 null）：单例覆盖； sanctioned 调用路径（push 后同步窗口内 pop）不会触达，无运行时观测计划。
- demo 模式（demoBridge）下 add_range_decision 的 duplicate 返回形状未核——demo bridge 非本版改动面，3.0.4 既有行为保持。

## 7. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步后端零改动，无追加行。前端面 4 文件登记入总表（类别：受控改点 (c) 前端面 ×2 hunk / 只增 ×4 hunk，见 §2）。

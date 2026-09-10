# record-3.0.5-P3-1：R5.5 纠错取消轮询化（Phase 3 全部；无独立 tag，随 P4 前合入）

> 步骤：PLAN P3-1 · 依据：[SPEC M5.5](./spec-v3.0.5.md)（焦点 3 状态矩阵落点 / MF2-1 判据冻结 / 裁决 5）· [PLAN](./plan-v3.0.5.md) P3-1 · [PRD](./PRD-v3.0.5.md) R5.5
> 分支：`dev-3.0.5-P3-1`（已合入已删）· 提交：见 §6

## 1. 改动清单

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `core/llm_service.py` | `analyze_subtitle_correction` 外层循环（原 :1134-1187 区） | **受控改点 (a) 轮询化**：`with ThreadPoolExecutor` 改 executor 变量 + `try/finally` 非阻塞 `shutdown(wait=False, cancel_futures=True)`；`as_completed` 改 `wait(outstanding, timeout=1.0, return_when=FIRST_COMPLETED)` 主循环；done 按 batch_idx 排序消化（ledger/progress 序稳定，保聚合等价）；轮询头 cancel 检测 → shutdown + return 裸 envelope；批消化体 `error == "Cancelled"` 立即 return（**不再消化本 poll 批 done 剩余**）；429 降级改「置 stop_polling 标志 + 双层 break」——逐行复刻翻译侧 smoke-fix-1c 样板（:1848-1876 + finally :1930-1934 原引位形） | 受控改点 (a) |
| 同上 | 串行降级循环（原 :1189-1205） | **MF2-1 记账判据冻结不动**：逐批 cancel 检查（原 :1191）与 not-corrections 记账判据（原 :1200-1203）逐字保留，未复刻翻译侧 error 判据（见 §5） | 零改动（登记确认） |

取消三返回保持**裸 envelope** `{"success": False, "error": "Cancelled"}`（裁决 5：纠错侧 token 上报本版不做，"Cancelled" 字符串不变，task_manager 双通道判据不受扰）。

## 2. 用例登记（M-gate 后端 R5.5 ≥4，实际 +5；`tests/test_correction_cancel_poll.py`）

| # | 用例 | 覆盖 |
|---|---|---|
| B1 | 取消 1s（栅栏法复刻 smoke-fix :139-172） | 全批 60s 栅栏阻塞 + t=0.3s 取消 → ≤4s 返回 Cancelled；裸 envelope（无 data 键，锁裁决 5）；栅栏放行后线程退出 |
| B2 | 聚合等价（成功路径） | 80 段 3 批：corrections 内容按批序全覆盖零重、token_usage 3/3/6 精确、ledger 集合 {succeeded:3, failed:[]} —— 不锁 list 顺序 |
| B3 | SG-2 (i) 转串行后取消 | 429 降级落地（concurrency=1，批 0-2 耗尽 429 预算、pending {3,4}）→ 第 6 次调用置 cancel → 串行循环头检查即返回 Cancelled，**mock 调用计数 == 6**（pending 零执行） |
| B4 | SG-2 (ii) 轮询内 429 降级 | 连续 429 mock → 置标志双层 break 正确进串行、两循环退出无悬挂（无 CancelledError 浮出）；串行批 3-4 补齐、failed=[0,1,2]、uncovered=前 90 段如实 |
| B5 | MF2-1 锁面例（串行 × parse 失败） | 串行批 `_call_batch` 返回 error=None + corrections 空（parse-None）→ not-corrections 判据仍记 **failed=[0,1,2,3,4]**、retried_ok=0——若误复刻翻译侧 error 判据则该批误记 succeeded，本例即挂 |

纠错既有断言**零改动**全绿（`test_llm_concurrency.py` 等 4 文件未触碰）。

## 3. 断言反转清单

本步**零反转**（纯新增用例 + 受控改点 (a) 白名单内改写；门禁 R0-3 后端 PASS 实证）。

## 4. 验证（全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  867 passed in 8.63s                        # P3 末期望 ≥863 ✓（beta.2 862 + 5）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 865 passed (866)    # 与 beta.2 持平 ✓；唯一失败 = useRowLayout.perf 环境例（已登记）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（后端 diff 文件集白名单内：config/correction_service/llm_service/project_service/main.py）
===== 门禁汇总: 全部通过 (exit 0) =====
```

**P3 末期望核对**：pytest ≥863 → **867** ✓；vitest 与 beta.2 持平 → **866 collected / 865 passed** ✓。

## 5. 解释登记与未验证边界

- **MF2-1 既有不对称（SPEC 明示登记，遗留）**：纠错两相记账判据不对称是 v3.0.4 现状事实——外层 error 判据（error=None 即 succeeded/retried_ok，parse-None 批在池相误记 succeeded）vs 串行 not-corrections 判据（parse-None 批正确记 failed）。根源 = `_call_batch` parse 失败返回 `error=None` 且 corrections 空（:1072-1074）。本轮只保聚合等价、不顺手统一（B5 锁面防回归）；统一需给纠错侧取消返回附 data 并动 :1125/:1146/:1174 三处（与裁决 5 同族），留后续版本评估。
- **串行相无「素成功」桶**：串行记账只分 retried_ok（retried 且有 corrections）/ failed（无 corrections）两桶——串行首试成功的批不进任何桶（succeeded 恒 0）。此为 :1182-1185 冻结现状，B4 断言如实锁定；同上不顺手改。
- **取消手感（约 1s）真机冒烟后置**：B1 栅栏法已锁轮询预算（<4s 含调度裕量）；beta.3 冒烟「大工程纠错取消约 1s 手感」项（plan :381）在 P3 合入后并入该轮验。
- **`as_completed` import 保留**：`core/llm_service.py:832`（smart delete 侧）仍在用，import 不动。

## 6. 后端改动登记表追加

| 步 | 文件 | 改动 | 关联 | 类别 |
|---|---|---|---|---|
| P3-1 | core/llm_service.py（1 文件） | analyze_subtitle_correction 外层循环轮询化（with→executor+finally / as_completed→wait(1.0, FIRST_COMPLETED) / done 排序消化 / 取消即退不消化余批 / 429 双层 break）；串行循环冻结不动；+5 测试（tests/test_correction_cancel_poll.py） | R5.5 | 受控改点 (a) |

# record-3.0.5-P2-1：R5.4 后端：三态作用域 + 聚合 patch（SPEC M5.4；序 3 同 commit 族）

> 步骤：PLAN P2-1 · 依据：[SPEC M5.4](./spec-v3.0.5.md)（实施裁决 1-2 / 触点表）· [PLAN](./plan-v3.0.5.md) P2-1 · [PRD](./PRD-v3.0.5.md) R5.4（S2 / F-A-05·06 / D7 第三项）
> 分支：`dev-3.0.5-P2-1`（已合入已删）· 提交：`bd19577`（代码）→ `81feae8`（--no-ff 合入 `dev-3.0.5`）
> 顺序：**序 3 同 commit 族已执行**——三态作用域形参与聚合 patch 在同一提交交付（聚合返回形状就是作用域改形的消费面，D7 第三项非独立交付物）；前端半边 P2-2 凭 data 纯增 patch 键超集兼容后置一步

## 1. 改动清单（逐 hunk）

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `core/correction_service.py` | :241-407（原 accept_subtitle_correction 整体重构） | **受控改点 (b) 第 1 面**：应用核心抽为 `_apply_one(result_id) -> (ok, dirty_layers, info)` 无 patch 方法——v3.0.4 M2-3 全量逻辑沿用（timeline 钉扎/解析/置信度标记/reattach_words/时间戳断言/双轨写回/结果移除），状态更新保留、patch 发射移交调用方；`accept_subtitle_correction` 变薄壳（_apply_one → 按脏层集构造单 patch → 返回形状逐字节不变，既有例全绿实证） | 受控改点 (b) |
| 同上 | :409-434（新增两私有辅助） | `_correction_track_scope(result)`（detail payload 的 track_id，"" = 主轨；malformed 回落 ""）+ `_scope_filter(track_id)` 三态谓词（None 恒真 / "" 主轨 / 非空该轨） | 只增 |
| 同上 | :491-585（accept_high_confidence_corrections） | **受控改点 (b) 第 2 面**：形参 `track_id: str \| None = None`（★B-1 三态）收窄 qualifying 过滤（阈值语义零触碰）；批量循环改驱动 `_apply_one` 消化脏层并集 → **单 `_success_patch(segments?/tracks?/analysis?)`**，revision 恰 +1（一次 undo 回退整批）；返回 = 旧键逐字保留 + **纯增 `patch` 键**（MF-3 超集）；零命中快速路径保持旧形零 revision；`remaining_count` 随作用域一致（None 恒全量 = 兼容；scoped 只计本作用域——主轨视图不把副轨余量报作自己的剩余，口径登记 §5） | 受控改点 (b) |
| 同上 | :587-645（clear_subtitle_corrections） | **受控改点 (b) 第 3 面**：三态形参同构；`cleared_count` 语义随作用域；**patch(analysis) 超集键**（活跃轴场景发射——_success_patch 契约绑定活跃轴；跨轴调用省略该键，边界登记 §5）；零清快速路径旧形零 revision | 受控改点 (b) |
| `main.py` | :2822-2852（两 expose） | **登记改点**：`accept_high_confidence_corrections` / `clear_subtitle_corrections` 增 `track_id: str \| None = None` 透传（旧调用位置兼容：第三参缺省 = None = timeline 级） | 登记改点 |
| `scripts/gates-v3.0.5.sh` | R0-3 后端段 | 排除面扩 `test_correction_accept_patch.py`（见 §3 追认；脚本头「SPEC 与本脚本冲突以 SPEC 为准当场修脚本」条款执行） | 工具修订（登记） |
| `tests/test_correction_accept_patch.py` | :148-180（spy 例重写）+ 文件尾两新类 | 见 §2/§3 | 只增 + 追认反转 1 行 |

**逐条 accept/reject 返回零改动**：既有 TestAcceptMainTrackSupertest / TestAcceptExtensionTrack / reject / pinning 全部例零改动全绿实证。

## 2. 用例登记（M-gate 后端 R5.4 ≥6，实际 +7 新 + 1 重写 + 既有零改动面佐证）

| # | 用例 | 覆盖 |
|---|---|---|
| B1 | test_main_scope_accept_leaves_track_pending | 三态 `""` 回归锁（★B-1）：主轨视图批收只动主轨；副轨待审集原样；remaining 作用域一致 |
| B2 | test_track_scope_accept_leaves_main_pending | 副轨视图不动主轨（互扰反向） |
| B3 | test_none_scope_aggregates_three_layers_one_patch | None（timeline 级）双轨齐收：**单 patch 三层并集**（segments+tracks+analysis 全非空）+ revision 恰 +1（4 收 1 bump）+ 两轨文本落地 |
| B4 | test_zero_accepted_keeps_old_shape_no_revision | 零命中：返回逐字节旧形（恰 accepted_count/remaining_count 两键）+ 零 revision |
| B5 | test_main_scope_clear_leaves_track_pending | clear 三态 `""`：只清主轨，副轨幸存断言 |
| B6 | test_clear_returns_analysis_patch_superset | clear 超集键：cleared_count 保留 + patch(analysis) + revision +1 + segments 层为 None |
| B7 | test_clear_empty_fast_path_old_shape | clear 零清快速路径旧形零 revision |
| R1（重写） | test_batch_accept_reuses_single_accept_superset | spy 锚 `_apply_one`（批复用同一应用核心）+ 聚合 patch revision+1 + 双层非空 |

「全部 = None 兼容」与「逐条路径形状零改动」由既有例零改动全绿证明（test_subtitle_correction_review.py TestBatchAccept 三例 + accept_patch 逐条三族，共 20+ 例未动）。

## 3. 断言反转清单登记（M0-3 + 本步追认）

| 文件:行 | 处置 | 意图与理由 |
|---|---|---|
| tests/test_correction_accept_patch.py:171 `assert all("patch" in d for d in captured)` | **追认反转（1 行删除）**：spy 例整体重写——spy 目标改 `_apply_one`，原「每 accepted item 的 data 携带 patch 键」断言由「聚合 patch 键 + revision 恰 +1 + 双层非空」三断言替代 | M5.4 裁决 2 明令批量改驱动 `_apply_one` + 单聚合 patch——「batch 委托逐条 accept 且逐条带 patch」契约被 SPEC 废除，断言锁定的正是被废除的架构；其余三断言行（`assert res["success"]` / `accepted_count == 2` / `assert captured, "batch must reuse the single-accept path"`）**逐字保留**（批复用应用核心的新语义下仍真）。门禁 R0-3 排除面按脚本头「SPEC 冲突以 SPEC 为准当场修脚本」条款扩至该文件并在脚本内注明 |

白名单外其他命中：零（R0-3 PASS 实证）。**本步为门禁脚本 R0-3 排除面首次扩充**（test_llm_translation.py 之外 +1 文件），P5-1 终检须按本条核对。

## 4. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  862 passed in 8.15s                        # pytest 全绿（beta.1 后 855 + 本步 7）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Tests  1 failed | 858 passed (859)         # 与 beta.1 持平（后端半边，前端零改动）；唯一失败 = perf 环境例
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 白名单内（correction_service 入列）
  [PASS] 禁改面为空 / R0-2 events 双侧零改动 / dev.py build.py 零改动
  [PASS] 后端断言白名单外零删改（排除面含 test_correction_accept_patch.py [追认 1 行]，见 §3）
  [PASS] 前端断言白名单外零删改
===== 门禁汇总: 全部通过 (exit 0) =====
```

## 5. 解释登记与未验证边界

- **remaining/cleared 作用域计数**：scoped 模式只计本作用域余量（主轨视图不把副轨待审报作自己的剩余——与「主轨视图操作不吞副轨待审集」同一语义面）；None 恒全量（既有断言零改动的兼容前提）。SPEC 未明文该口径，按作用域一致性实现并在此留痕。
- **clear 跨轴边界**：patch 键仅在「被清轴 == 活跃轴」时发射（_success_patch 契约绑定活跃轴；跨轴 clear 保持旧形返回）。既有调用面（前端）恒为活跃轴，P2-2 消费不受影响。
- **revision 语义变化（有意）**：clear 自本步起在「有清除写入」时 revision +1（旧版 _update_timeline_by_id 无 patch 无 bump）——使 clear 成为可 undo 的 patch 写（P2-2 前端 undo 三态层的后端前提）；既有 clear 三例零改动全绿（无一断言 revision 不变）。
- **expose 第三参位置兼容**：旧前端 `accept_high_confidence_corrections(timelineId, 0.8)` 位置调用 → 第三参缺省 None = timeline 级，行为不变；P2-2 前端升级传三态。
- **未验证边界**：跨轴 clear patch 省略路径（防御性，无生产调用面）；前端三态消费/确认文案/undo 三态层全部在 P2-2 交付。

## 6. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步追加：correction_service (b) 族 3 面 + 辅助 2 只增 / main.py 登记改点 2 行 / 门禁脚本 R0-3 修订 1 行 / 测试 +7 与追认 1 行，已汇总入总表。

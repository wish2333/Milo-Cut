# record-3.0.5-P5-1：门禁终检与登记核对（P5 收尾第一步）

> 步骤：PLAN P5-1 · 依据：[PLAN](./plan-v3.0.5.md) P5-1 · [SPEC M0 全局契约](./spec-v3.0.5.md)（M0-1 白名单 / M0-2 受控改点 / M0-3 反转追认 / M0-4 顺序）
> 本步零代码改动（纯核对 + 文档）；核对基准 = tag `v3.0.4`，核对对象 = `dev-3.0.5` @ `372a282`（beta.3 后 docs commit）

## 1. 全量复跑（P5 终检全量口径）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  875 passed in 9.43s                        # = beta.3 期望只增不减 ✓（833 → 875）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  64 passed (64)
  Tests       884 passed (884)               # 全绿维持（R5.16 豁免已退役）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 文件集全部在白名单内
  [PASS] 禁改面为空
  [PASS] R0-2 events 双侧零改动
  [PASS] 后端断言白名单外零删改
  [PASS] 前端断言白名单外零删改
  [PASS] dev.py / build.py 零改动
===== 门禁汇总: 全部通过 (exit 0) =====
```

## 2. 后端改动登记表逐条核对（SPEC 附录 A 口径）

**diff 文件集 ⊆ M0-1 白名单**（6 文件，逐一有登记行 + R5.x 编号）：

| diff 文件 | 登记行（总记录 §3） | R 编号覆盖 |
|---|---|---|
| `core/config.py` | P1-5（DEFAULTS +1 键行） | R5.8 |
| `core/correction_service.py` | P2-1（_apply_one 抽取 + 批量三态 + clear 三态 + 聚合 patch） | R5.4 |
| `core/llm_prompts.py` | P4-4（语义说明 1 行） | R5.12 |
| `core/llm_service.py` | P1-2（R5.1 三处附 data）/ P1-3（R5.2 Layer4 正则 + 文案）/ P1-4（R5.3 (d)）/ P1-5（R5.8 (f) 族）/ P3-1（R5.5 (a)） | R5.1/R5.2/R5.3/R5.8/R5.5 |
| `core/project_service.py` | P1-4（merge_translation_track 纯新增，R5.3）/ P4-4（add_silence_results 排序 1 行，D4-2 修复） | R5.3 / D4 |
| `main.py` | P1-2（R5.1 (e) handler 取消判据）/ P1-4（R5.3 (e) 合流/补译路由 + :3052 自动路由）/ P2-1（R5.4 expose track_id 透传）/ P4-2（R5.9 显示名 1 行） | R5.1/R5.3/R5.4/R5.9 |

**受控改点 (a)-(f) 与 M0-2 一一对应核对**（六处全落位，锚区间与实改面相符）：

| 改点 | M0-2 定义 | 落位登记行 | 核对 |
|---|---|---|---|
| (a) | R5.5 纠错取消轮询化（外层 :1116-1187 两循环） | P3-1（record-3.0.5-P3-1.md §1） | ✓ 串行循环 MF2-1 冻结不动 |
| (b) | R5.4 两 expose 三态 + 聚合 patch（:446-532） | P2-1 | ✓ 形参默认值等价 |
| (c) | R5.0 handleRangeDecision 三分支化（:990-999） | P1-1 前端面行 | ✓ 成功路径逐字节不变 |
| (d) | R5.3 翻译失败语义改判（:1957-1982） | P1-4 | ✓ 全批拒/部分落盘两分支 |
| (e) | R5.1/R5.3 main.py handler + 路由 + 合流 | P1-2 / P1-4 | ✓ MF2-2 合流口径 |
| (f) | R5.8 预构建改串行逐批（:1774-1790） | P1-5 | ✓ 默认关路径逐字节等价 |

**main.py 专项**：R5.3 合流 hunk 与 R5.4 expose 透传逐 hunk 在表（上表 main.py 行）；无「无对应者」diff hunk（六文件全部行组均有登记行对应）。

## 3. 断言反转清单终态核对（M0-3 追认制）

逐文件实计（`git diff v3.0.4` 删除断言行）：

| 文件 | 删除断言行 | 登记 | 白名单 |
|---|---|---|---|
| `tests/test_llm_translation.py` | **3**（:614 取消附 data [P1-2] / :217 整串断言 [P1-3] / 429 例翻转 [P1-4]） | 各分步 record §3 | ✓（后端白名单） |
| `tests/test_correction_accept_patch.py` | **1**（M5.4 裁决 2 废除 batch 逐条委托契约 [P2-1]） | P2-1 + 脚本注记 | ✓ |
| `AIAssistantPanel.test.ts` | **2**（:301 估算串断言改写 [P1-6]） | P1-6 | ✓ |
| `SegmentBlocksLayer.test.ts` | **1**（rejected 例反转 [P4-2]）+ findOverlays 选择器追认（非 expect 行） | P4-2 §3 | ✓ |
| `useRowLayout.perf.test.ts` | **3**（墙钟阈值移除 [P4-3 R5.16 根修]） | P4-3 §3 | ✓（P4-3 追认扩白名单） |

合计 **10 行**删除断言（后端 4 / 前端 6），全部白名单内；改写类 2 处（badge 例 [P4-3] / 选择器 [P4-2]）expect 零删。PLAN P5-1 预估「后端 2 行 + 前端 2 例 3 行 + 追认 1 行」为 P4 前估算值，实际终态如上——白名单外零命中（门禁 R0-3 双侧 PASS 实证）。

## 4. 禁改面终检

- `git diff v3.0.4 --name-only -- pywebvue/ core/models.py core/events.py core/task_manager.py core/export_service.py core/export_timeline.py core/track_constraints.py core/workflow_engine.py core/ffmpeg_service.py core/ffmpeg_presets.py core/subtitle_service.py core/timeline_utils.py core/diff_service.py core/migrations.py` → **空** ✓
- `frontend/src/utils/events.ts` diff = 0 行 ✓（R0-2 双侧）
- `dev.py` / `build.py` diff = 0 ✓

**两项「登记不修」现状缺陷核对**（勿误判漏改）：
- MF2-1 记账判据不对称（纠错池相 error 判据 vs 串行 not-corrections 判据）：**登记在案**（record-3.0.5-P3-1.md §5 遗留 + B5 锁面例防回归），非漏改 ✓
- SG2-2 非翻译 errorMsg 残留：**登记在案**（P1-2 前端面 useLlmTasks errorMsg 清空仅限 llm_translation 口径），非漏改 ✓

## 5. 终检结论

- 全套门禁 exit 0；pytest 875 / vitest 884·884 全绿，与 beta.3 一致（只增不减 ✓）
- 登记表 ↔ diff 全对齐（六后端文件、(a)-(f) 六受控改点、main.py 四编号）
- 断言反转 10 行全白名单内、逐条落档
- 禁改面全空；两项登记不修项在档
- **P5-1 通过，可进 P5-2（README 回填与版本池回写）**

## 6. 改动登记表追加

本步零代码改动；本文档为核对留痕（总记录 §1 索引行更新）。

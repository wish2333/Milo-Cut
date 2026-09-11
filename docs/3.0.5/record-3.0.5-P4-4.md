# record-3.0.5-P4-4：R5.12 prompt 语义说明 + D4 测试轮 + beta.3 节点（P4 收官）

> 步骤：PLAN P4-4 · 依据：[SPEC M9 表 R5.12 行](./spec-v3.0.5.md) · [PLAN](./plan-v3.0.5.md) P4-4 · [PRD](./PRD-v3.0.5.md) R5.12 / §7.4 D4 移交落点
> 分支：`dev-3.0.5-P4-4`（已合入已删）· 提交：见 §6
> **beta.3 节点**：tag `v3.0.5-beta.3` 打于本步 merge commit；P4 四步（R5.6 / R5.7+R5.9+R5.10+R5.14 / R5.11+R5.15+R5.16 / R5.12+D4）收口

## 1. R5.12：`_SUBTITLE_CORRECTION_SYSTEM_A` 受控增行

| 文件 | hunk | 内容 |
|---|---|---|
| `core/llm_prompts.py` | :66-67（edit_hint 说明块尾） | 增一行「aligned_main_text 为主轨参考稿，仅用于校对译文，勿照抄。」——注册表键集不变零改动（DEFAULT_PROMPTS :157-194 未触碰）；键集类测试零影响（门禁 R0-4 人工核对只增） |

## 2. D4 测试轮（PRD-v3.0.4 §10.3 移交四项；不占 ≥30/≥24 额度，增量如实登记）

| # | 项 | 用例（文件） | 覆盖 |
|---|---|---|---|
| D4-1 | detect_silence 本体 | `tests/test_d4_silence_gaps.py` TestDetectSilence ×4 | silencedetect stderr 解析：配对窗口 + 三位舍入直测 / 未配对 start 丢弃不崩 / 垃圾数字容忍（合法对存活）/ ffmpeg 缺失错误 envelope（mock `_find_ffmpeg` + `subprocess.run`，零真进程） |
| D4-2 | 端到端串测 | 同文件 TestSilenceChainEndToEnd ×1 | detect_silence 产出 dict 形状（D4-1 同款）→ `add_silence_results(margin=0.1, subtitle_padding=0.2)` → 静音段落位 + pending delete edits + **排序不变量**（本例发现真缺口，见 §3 修复） |
| D4-3 | padding=0 交叠 | 同文件 TestKeepRangesPaddingZero ×2 | 相邻字幕零间距：扩展 keep 恰好相接合并，**零退化（零/负宽）delete range** + delete ranges 两两不交且有序；真实间隙：delete range 恰为 (4.0, 6.0) 精确边界 |
| D4-4 | basic 空白点击建重叠段 | 前端 `SegmentBlocksLayer.test.ts` +1 + 后端同文件 TestOverlappingAddSegmentSafety ×1 | 前端：add-segment payload（time, time+0.5）经有界时间源不越界；后端：重叠段入库排序不变量吸收 + 全量段完整重载（数据安全双半） |

**D4-2 发现并修复真缺口（兜数据安全，D4 意图内）**：`add_silence_results` 追加静音段未排序——静音窗口与字幕交错时拼接结果非升序，而前端 `mergedSegments` 依赖排序不变量跳过每渲染排序（渲染契约破坏）。修复 = `all_segments.sort(key=lambda s: s.start)`（add_segment 同款先例，1 行 + 注释）；既有 pytest 全绿零反转。

## 3. 断言反转清单

本步**零反转**（D4 纯新增 9 例；project_service 修复为实现面非断言面；门禁 R0-3 双侧 PASS 实证）。

## 4. 验证（beta.3 节点全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  875 passed in 9.18s                        # beta.3 期望 ≥863 ✓（beta.2 867 → +8：D4 后端例；P4 后端零产品改动，含 R5.9 显示名 1 行）
  All checks passed!                         # ruff 0 problems（D4 文件 import 排序 + zip(strict=) 一轮修复后绿）
===== 前端门禁 =====
  Test Files  64 passed (64)
  Tests       884 passed (884)               # beta.3 期望 ≥864/≥863 ✓（P4-3 883 → +1：D4 前端例）；全绿维持（R5.16 豁免已退役）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（llm_prompts 只增 1 行；project_service 排序修复 1 行对照登记表；禁改面为空）
===== 门禁汇总: 全部通过 (exit 0) =====
```

**beta.3 期望总数核对**：pytest ≥863 → **875** ✓；vitest ≥864/≥863 → **884 collected / 884 passed（全绿）** ✓。tag `v3.0.5-beta.3` 落地。

## 5. 解释登记与未验证边界

- **D4-2 排序修复的兼容面**：静音段追加后排序仅在「静音与字幕交错」场景改变段序（既有测试全绿 = 各静音用例本就单序或后置）；前端渲染对排序段序本就按升序预期，修复严格向契约靠拢。
- **R5.12 增行位置**：落在 edit_hint 说明块尾（规则区内），不在 {{glossary}} 占位符与输出格式段之间——模板变量穿透不受扰（三层覆盖机制原样）。
- **D4 不占额度口径**：9 例（后端 8 + 前端 1）为移交缺口补齐，M-gate ≥30/≥24 产品额度核算不含（PRD §7.4 明示）；登记表单列。
- **beta.3 真机冒烟（后置，3.0.4 先例）**：keep invalidated toast 可见性与确认文案直显（R5.6）/ trim 冻结矩阵手感（R5.7）/ 时间码三态与取播放头（R5.11）/ 纠错取消约 1s（R5.5 并入本轮）/ rejected 覆层退场与建段半亮（R5.10）。

## 6. 改动登记表追加

| 步 | 文件 | 改动 | 关联 | 类别 |
|---|---|---|---|---|
| P4-4 | core/llm_prompts.py | _SUBTITLE_CORRECTION_SYSTEM_A 增 aligned_main_text 语义说明 1 行（:66-67） | R5.12 | 受控增行 |
| P4-4 | core/project_service.py | add_silence_results 段列表排序（:1303-1309，D4-2 发现缺口修复） | D4-2 | 修复 1 行 + 注释 |
| P4-4 | tests/test_d4_silence_gaps.py（新）+ SegmentBlocksLayer.test.ts | D4 四项 9 例（后端 8 + 前端 1） | D4 | 只增（测试，不占额度） |

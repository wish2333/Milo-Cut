# record-3.0.5-P1-4：R5.3 翻译增量补译 + uncovered 对账可读化（SPEC M5.3；本模块最高风险步；序 7 落点）

> 步骤：PLAN P1-4 · 依据：[SPEC M5.3](./spec-v3.0.5.md)（实施裁决 1-9 / 触点表）· [PLAN](./plan-v3.0.5.md) P1-4 · [PRD](./PRD-v3.0.5.md) R5.3（S1 / US-10 / F-A-04）
> 分支：`dev-3.0.5-P1-4`（已合入已删）· 提交：`a6ec740`（代码）→ `d91dbf2`（--no-ff 合入 `dev-3.0.5`）
> 顺序：序 4 第三环（R5.1×R5.2×R5.3 同族一次改透完成）；序 7 内部序硬约束已执行——MF2-2 合流 hunk 与消费端改造同 commit 落地（同一短分支同一提交，满足「先于或同 commit 于」），R5.11 的 reset 延后消费同一 lastTranslationCompletion 结构已定形（本步增 written_count 纯增键）

## 1. 顺序与落点核对（序 7）

- **completion payload 缺口合流 hunk**（main.py 事件 payload + 返回 dict 双侧同口径）与全部消费端改造（WorkspacePage watcher 补译 toast / AIAssistantPanel 对账渲染与一键补译 / useLlmTasks written_count 透传）**同一 commit**（`a6ec740`）合入——无中间态假绿窗口。
- **R5.8 主从（序 2）**：P1-5 将动 (f) :1774-1790 预构建段，与本步 (d) 改判区同函数不同段，本步未触碰预构建（P1-5 开工前置 = 本步已合入 ✓）。

## 2. 改动清单（逐 hunk）

### 后端

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `core/llm_service.py` | :1999-2037（uncovered 推导后改判区） | **受控改点 (d)** 两分支重构：`len(failed) >= total_batches` → 全批失败拒零写入（中文文案逐字保留，M5.2 文案 (i)）；`0 < len(failed) < total_batches` → **部分成功**：打点 partial 警告日志后流入既有合并序返回 success=True + 已完成批 translations + ledger（失败批号与 uncovered 保留）；uncovered 推导（:1992-1997）与无失败路径零改动 | 受控改点 (d) |
| `main.py` | :1319-1333（完成上报区） | **MF2-2 登记改点**：`uncovered_ids` 改「写侧对账 report ∪ ledger.uncovered_segment_ids」去重并集（`dict.fromkeys` 保序）；事件 payload（:1331-1346）与返回 dict（:1350-1362）同口径 | 登记改点（M0-1/M0-2 (e)） |
| `main.py` | :1230-1245（handler Step 1 后） | 补译分支：payload 带 `resumable_track_id` 时管线段源收窄为 `gap_segment_ids` 子集（运行时推导结果随 payload 传递，不持久化）；缺口全失效防御 raise | 受控改点 (e) |
| `main.py` | :1336-1362（写侧） | 路由分派：resumable → `merge_translation_track`（同轨合并单 patch）；否则 `create_translation_track` 原样；失败错误串透传不变 | 受控改点 (e) |
| `main.py` | :3052-3100（start_translation 校验段） | **受控改点 (e) 自动路由**：同语言轨存在 → 推导缺口集（主轨 subtitle 段 − confirmed-deleted − 该轨 bindings 的 main_segment_id 差集；只看 bindings 不考察 extension 存活，与导出映射同口径）；非空 → payload 纯增 `resumable_track_id`/`gap_segment_ids` 两键；为空 → :3000-3006 拒绝原文案逐字保留 | 受控改点 (e) |
| `core/project_service.py` | :871-1038（create_translation_track 之后单一插入） | **纯新增 `merge_translation_track`**（零删行实测）：入口双保险（timeline 钉扎 + 轨存在∧role="translation" 再查）→ 撞配拒（item 主 id 已绑定即整体拒零写入）→ 现主轨对账（消失 id 进 uncovered）→ 段号 `track_{track_id}_seg_{start:.3f}` 命名空间 + 轨内查重（撞号显式失败）→ `model_copy` 增段 + bindings（offset=0 同 create 法）→ 单 `_success_patch(tracks, bindings)` revision+1，meta 携带 `merged_count`（+ create 同形键）；SG2-3 自含实现**未抽**共享 helper | 只增（单一 hunk） |

### 前端

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `useLlmTasks.ts` | :59-67 / :181-200 | TranslationCompletion 纯增 `written_count: number`（监听透传 `?? 0`） | 只增 |
| `WorkspacePage.vue` | :1098-1112（标记）/ :1130-1160（watcher）/ :633-651（双保险清理） | `pendingResumable = {trackId, language}` 在 pushSnapshot **前**置位（同语言轨存在即补译路由）；watcher：`completion.track_id === pendingResumable.trackId` 命中才 toast「本次补译 N 段」并清标记（SG2-1 比对——新轨 id 天然不匹配 + 残留自愈）；未命中路径既有行为保持（uncovered 文案尾部改「可一键补译」；「（主轨已变更）」旧注记废除——MF2-2 后缺口含管线侧失败，原文案失实）；task:cancelled（llm_translation 分支内）+ 新增 task:failed 监听（llm_translation）显式清标记 | 只增 + 文案修正 |
| `AIAssistantPanel.vue` | script :267-321 / template :446-490 | 对账可读化（裁决 8）：`uncoveredEntries` computed 逐条经 mainSegments 解析 `{mm:ss} {前 20 字}`（主轨段消失回落裸 id 且禁用）；条目点击 `emit("seek", start)` 走既有定位链（Timeline handleSuggestionSeek 高亮主轨段）；尾部「补译这些段」按钮 `emit("start-translation", {targetLanguage: notice.language})` 走同一路由；裸 `join("、")` 渲染废除 | 渲染改造（裁决 8） |

### 测试（+16：后端 11 / 前端 5）

| # | 宿主 | 用例 | 覆盖裁决 |
|---|---|---|---|
| B1 | test_llm_translation.py | test_partial_failure_lands_completed_batches | 裁决 3（1/N 落盘：失败批 content 定向 mock，6/8 落盘原序）+ **SG-1 守恒双向**（uncovered == 目标集−覆盖集，双向无多无少） |
| B2 | 同上 | test_all_batches_failed_still_refuses_zero_write | 裁决 3（全批拒 + data 键集恰 {ledger, token_usage} + 补译文案） |
| B3 | 同上 | test_no_failure_path_returns_full_key_shape | 裁决 3（无失败全键等价：顶层/data 键集 + ledger 全形 + usage 键集） |
| B4-B8 | test_translation_track.py | merge 五例：单 patch revision+1+meta/命名空间/钉扎拒/轨缺失拒/撞配拒/消失 id 对账 | 裁决 5（单 patch、双保险、撞配、uncovered 数据结构） |
| B9 | test_translation_expose.py | test_gap_derivation_routes_patchup_payload | 裁决 1/2（缺口集 == 恰为未绑定 id 主序；payload 两键） |
| B10 | 同上 | test_resumable_task_writes_via_merge_not_create | 裁决 2（段源收窄恰为缺口集；merge spy 调用 + create 零调用；同轨落盘） |
| B11 | 同上 | test_completion_gap_is_write_side_union_pipeline_gap | **MF2-2**（写侧空时事件仍含管线缺口 id；事件与返回 dict 同口径） |
| F1 | AIAssistantPanel.test.ts | readable entries 渲染 | 裁决 8（mm:ss + 20 字截断验证；消失段回落裸 id 禁用） |
| F2 | 同上 | 点击定位 seek | 裁决 8（emit seek = 主轨段 start） |
| F3 | 同上 | 一键补译路由 | 裁决 8（start-translation 携 notice.language；notice 折叠） |
| F4 | WorkspacePage.translation.test.ts | 补译 toast 命中 | 裁决 7（同语言轨启动置标记 → 匹配 completion →「本次补译 7 段」；新轨切换 toast 不误发） |
| F5 | 同上 | 取消清标记（SG2-1） | 裁决 7（cancel 后同 id completion 不误报补译） |

M-gate 额度核对：后端 R5.3 ≥10 → 11；前端 ≥4 → 5。

## 3. 断言反转清单登记（M0-3 白名单 + 本步追认）

| 文件:行 | 处置 | 意图与理由 |
|---|---|---|
| （预登记面） | 本步无预登记反转行命中（:217/:614 已随 P1-3/P1-2 落地） | — |
| tests/test_llm_translation.py:467（429 多批例）`assert result["success"] is False` | **追认反转**：→ `is True` + translations == [seg-006, seg-007]；docstring 同步 | M5.3 裁决 3 必然结果：4 批中 3 败 1 成 = 部分成功场景，旧「全量拒」语义仅存于全批败分支；M0-3 ★B-4 复核时仅覆盖预登记四例（单批任务），本多批例不在其列；ledger 断言（failed/succeeded/uncovered）全保留 |
| tests/test_translation_expose.py `_install_translation_track` 夹具 | **追认改造（非 expect 行）**：夹具补全 bindings（完整轨） | R5.3 后拒绝条件收窄为「完整同语言轨」；夹具原为空轨零绑定 = 恰为新补译路由场景。测试 `test_duplicate_language_rejected_with_guidance` 断言**零改动**（拒绝文案逐字保留验证） |
| AIAssistantPanel.test.ts:311（裸 join 断言） | **追认改写**：`toContain("seg-1、seg-7")` → 两条逐 id contain | M5.3 裁决 8 明令「:465 裸 join 渲染废除」；断言锁定的是被废除的渲染形态（该文件在 R0-3 门禁白名单内，expect 行未删——断言对象改写） |
| useLlmTasks.translation.test.ts :98/:120（两处 toEqual 对象） | **纯增键（expect 行零删）**：对象内补 `written_count: 30` | TranslationCompletion 纯增键的透传契约更新；toEqual 全量比较必然含新键，语义为超集兼容 |

门禁实证：R0-3 双侧 PASS（白名单外零删改）；上述四处均为白名单文件内/非 expect 行/纯增键，逐条登记如上。

## 4. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  851 passed in 7.05s                        # pytest 全绿（P1-3 后 840 + 本步 11）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 857 passed (858)    # P1-3 后 853 + 本步 5；唯一失败 = useRowLayout.perf 环境例（豁免口径）
  [PASS] build 通过（vue-tsc + vite build；一轮 TS18048 optional chaining 修复后绿） / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 白名单内（llm_service / project_service / main.py 三文件均在 M0-1 表）
  [PASS] 禁改面为空 / R0-2 events 双侧零改动 / 断言白名单外零删改（双侧）/ dev.py build.py 零改动
===== 门禁汇总: 全部通过 (exit 0) =====
```

`git diff core/project_service.py` 删行数 = **0**（单一方法纯新增验收实证）。定向先行：后端三宿主 63 全绿；前端五宿主合跑全绿。

## 5. 解释登记与未验证边界

- **「（主轨已变更）」文案废除**：MF2-2 合流后 uncovered 含管线侧失败批缺口，「主轨已变更」不再是唯一成因，watcher toast 与面板 notice 的该注记一并移除（文案尾部统一「可一键补译（见 AI 助手面板）」）；既有测试 `stringContaining("N 段未覆盖")` 兼容面实证全绿。
- **补译请求集口径**：handler 段源收窄用 payload 携带的推导结果（start 时点快照）；运行中新增主轨段不在本轮补译集（下一轮差集天然涵盖）——与「运行时推导不持久化」裁决一致。
- **真机边界**：1/34 量级真机手感（缺口对账可读可定位可一键补译 + notice 必触发 + undo 一次回退）留 beta.1 真机冒烟轮「翻译失败→补译全链」项；merge 撞号防御路径（两主段同 start 浮点）单测覆盖、真机不可达（差集推导下同轨同 start 不可能）。
- **undo 一次回退**：补译走 start_translation 同一路由，handleStartTranslation 的 pushSnapshot(["tracks","bindings"]) 天然覆盖（裁决 6 零新增改动）；B4 单 patch revision+1 为其写侧前提。

## 6. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步追加：llm_service (d) 1 行 / main.py 4 行（MF2-2 登记改点 + (e) 三 hunk）/ project_service 只增 1 行 + 测试 3 行 + 前端 4 行，已汇总入总表。

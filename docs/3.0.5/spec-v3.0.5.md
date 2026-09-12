# v3.0.5 实施规格说明（SPEC）

> 版本：3.0.5（实施层定稿——2026-09，R2b 轮定稿 / R4 轮按 R3 意见修订；实施层裁决与 PRD 冲突处以本文为准，冲突逐条登记于附录 B ★ 回写清单）
> 依据链：[PRD-v3.0.5](./PRD-v3.0.5.md)（R5.0-R5.16 / §6 裁决与 trim 矩阵）· [研究报告-v3.0.5](./研究报告-v3.0.5.md)（§4 候选池 / §8.4 真机项）· [review-log-v3.0.5](./review-log-v3.0.5.md) R2（must-fix MF-1~4 / suggest SG-1~6 / 锚点勘误 E-1~3 / 焦点 1~5 裁决，全部吸收）· review-log R3（MF2-1/MF2-2、SG2-1~7、E-4~E-6、天数复核、顺序约束序 7/序 8，R4 轮逐条处理）· [record-3.0.4](../3.0.4/record-3.0.4.md)（§3 登记表列形态 / §8 遗留）· 代码锚点本人逐触点实查（2026-09，工作区 = v3.0.4 发布态；本文所有 file:line 均为本人打开代码核实值，R4 轮涉及锚点变化处已重新实查）
> 基线：tag `v3.0.4`；门禁 diff 基准恒为 `v3.0.4`。行号漂移时以符号名检索兜底。
> 基线数实跑复核（本人本轮实跑）：pytest --collect-only = **833**；vitest = **840 collected / 839 passed / 1 failed（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟环境例，豁免口径维持）**——与 PRD §9 完全一致。
> 规模口径注记（R3 复核，R4 登记）：**13.5-17.5 人日 / 日历 11-15 天**（以「顺带批与 P1-P3 并行开发」为显式前提，单人串行 15-19 天；低估段 = P1 的 M5.3/M5.8 与 P4 的 D4+顺带批）——终稿天数归 PRD §7，由 R5 轮 PM 回写（附录 B B-8）；并行假设的显式例外 = M0-4 序 8（R5.11 开发基线须含 M5.4）。

---

## 概要

| 模块 | 内容 | 对应 PRD | 批次 |
|---|---|---|---|
| M0 | 全局契约：白名单终表、受控改点 (a)-(f) 终表、断言反转白名单终态、交付顺序强制 | §1 全部前置 | 全程 |
| M5.0 | duplicate 幂等返回防呆（快照回滚 API + 三分支 + duplicate 态测试） | R5.0 | P1 首项 |
| M5.1 | 翻译失败/取消成本可见（事件判据 + token/ledger 上报 + 429 透出） | R5.1 | P1 |
| M5.2 | 行级解析兜底 translated_text + 失败中文出路指引 | R5.2 | P1 |
| M5.3 | 翻译增量补译 + uncovered 对账可读化（管线失败语义改判） | R5.3 | P1 |
| M5.4 | 批量审阅收口（三态作用域 + 聚合 patch + 批量 undo + D7 第三项） | R5.4 | P2 |
| M5.5 | 纠错取消轮询化（两循环 × 三退出状态矩阵） | R5.5 | P3 |
| M5.6 | keep 可感知收口（文案直显 + invalidated_count + 红蓝并存提示） | R5.6 | P4 |
| M5.7 | 波形编辑模式一致性（trim 冻结矩阵落地，轨角色条件守卫） | R5.7 | P4 |
| M5.8 | 质量模式开关（串行 + 定稿译文滑动窗，config 默认关） | R5.8 | P1 末 |
| M9 | 顺带批 R5.9-R5.16 + 门禁与用例矩阵 + 真机清单 | §5/§7/§9 | P4/P5 |

---

## M0: 全局契约

### M0-1: 后端 diff 白名单终表（PRD §1.5 六文件复核定稿）

`git diff v3.0.4 -- core/ main.py` 的全部输出必须落在下表内，且每条 hunk 对应一个 R 编号：

| 文件 | 允许的 diff 内容 | 登记号 |
|---|---|---|
| `core/llm_service.py` | R5.1 三处取消返回附 data（:1871/:1903/:1939，键级只增，`error` 串不变）；R5.2 第 4 层解析加 translated_text 模式（:612-634 末尾追加，只增）；R5.3 管线失败语义改判（受控改点 d，:1964-1982 区）+ 中文文案；R5.5 纠错取消轮询化（受控改点 a，:1116-1187 区）；R5.8 串行分支 + 滑动窗 payload（受控改点 f，:1774-1790 区）+ `_build_structured_user_message`（:518-563）增 `finalized_translations` 受控转发增行 | R5.1/R5.2/R5.3/R5.5/R5.8 |
| `core/correction_service.py` | **受控改点 b**：`accept_high_confidence_corrections`（:446-502）/ `clear_subtitle_corrections`（:504-532）三态作用域形参 + 逐条应用核心抽内部方法 + 聚合单 patch；逐条 accept/reject 既有返回零改动 | R5.4 |
| `core/project_service.py` | 仅新增 `merge_translation_track` 一个方法（:716 `create_translation_track` 之后插入，单一 hunk，零删改）；**其余零改动**（`generate_subtitle_keep_ranges` :2915-2989 零触碰——invalidated_count 已在 :2986 返回，R5.6 纯前端消费） | R5.3 |
| `main.py` | **受控改点 e**：`_handle_translation` 失败/取消分支（:1266-1269）；`start_translation` 同语言校验段改补译路由（:2996-3006 区，受控改点 e 同支登记）；R5.4 两 expose 透传 `track_id`（:2755-2768/:2771-2778，登记改点）；R5.3 completion payload 缺口合流（:1317-1331 区，:1328 `uncovered_ids` 改「写侧对账 ∪ ledger.uncovered_segment_ids」去重并集 + 返回 dict :1340 同步——**MF2-2 补登**，登记改点）；R5.9 重译拒绝文案显示名（:3002-3005，1 行） | R5.1/R5.3/R5.4/R5.9 |
| `core/llm_prompts.py` | **受控增行**：`_SUBTITLE_CORRECTION_SYSTEM_A`（:51）末尾增 aligned_main_text 语义说明一句（R5.12；注册表键集不变零改动——区间勘正 SG2-4：DEFAULT_PROMPTS 实跨 :157-194，translation 项 :186-193，实测值较 R3 建议值 :157-190 更精确） | R5.12 |
| `core/config.py` | **仅** DEFAULTS（:57-90 LLM 区块）追加 `"llm_translation_quality_mode": False` 一行（:82 `llm_translation_target_language` 之后） | R5.8 |
| `tests/` | 只增新文件/新用例；既有断言删改仅限 M0-3 白名单终态（5 处） | 全部 |

**禁改面**（diff 必须为空）：`core/models.py`（字段冻结红线，ProjectPatch :410-461 零触碰）、`core/events.py` 与 `frontend/src/utils/events.ts`（事件零新增预期，`llm:token_usage` events.py:29 / events.ts:19 双侧已在）、`core/task_manager.py`、`core/export_service.py`、`core/workflow_engine.py`、`core/track_constraints.py`、`core/ffmpeg_service.py`、`core/subtitle_service.py`、`core/diff_service.py`、`pywebvue/**`、`dev.py`、`build.py` 及白名单外一切 `core/**`。

### M0-2: 受控改点终表（PRD §1.6 五处 + MF-4 补登 (f) = 六处）

| 编号 | 主项 | 改「什么」 | 锚点（本人核实终值） | 性质边界 |
|---|---|---|---|---|
| (a) | R5.5 | `analyze_subtitle_correction` 既有 `with ThreadPoolExecutor + as_completed` 取消机制改 1s 轮询 + 非阻塞 shutdown | 外层循环 :1116-1166（with :1116 / as_completed :1122 / 取消返回 :1125、:1146）；串行降级循环 **:1171-1187**（取消返回 :1174，逐批 cancel 检查 :1173 已在位）——E-3 勘误后的补全区间（review-log 原引 :1166-1180 略偏） | 成功路径批序聚合语义不变；两循环同改 |
| (b) | R5.4 | `accept_high_confidence_corrections` / `clear_subtitle_corrections` 既有函数增三态作用域 + 聚合 patch | :446-502 / :504-532；qualifying 过滤 :471-474 现状不分轨 | 形参默认值 = 既有 timeline 级逐字节等价（语义裁决见 M5.4，形参类型改判见 ★B-1） |
| (c) | R5.0 | `WorkspacePage.vue` handleRangeDecision 既有快照与 emit 时序三分支化 | :990-999（pushSnapshot :992 先于桥调用 :993；成功 emit :994-995；失败 toast :996-997 现状无回滚） | 成功路径形态不变（PRD R5.0 ②字面锁定，时序后移方案被否决，见 M5.0 裁决 2） |
| (d) | R5.3 | `analyze_subtitle_translation` 失败语义改判（3.0.4 新增代码的改判，非 legacy） | :1957-1982（uncovered 推导 :1957-1962 / 全量守恒 fail 分支 :1964-1982） | 全批失败仍拒零写入；无失败路径逐字节等价 |
| (e) | R5.1/R5.3 | `main.py` 翻译 handler 失败/取消分支 + start_translation 补译路由 + completion payload 缺口合流 | :1266-1269（失败 raise 丢 data 属实）/ :1258-1264（cancel_event 传参在作用域）/ :2996-3006 / :1317-1331（:1328 合并口径，**MF2-2 补登**）+ 返回 dict :1340 | 成功路径 :1271-1344 **仅** :1317-1331 区与 :1340 按 MF2-2 合并口径增改（R5.3，登记改点），其余零改动 |
| (f) | R5.8 | **MF-4 补登**：翻译管线批 payload 预构建段改「串行分支内逐批构建」 | **:1774-1790**（「Pre-compute each batch's payload」:1774；`_call_batch` 消费 :1796） | 默认关路径预构建原样保留（逐字节等价）；**锚点勘误 E-4**：MF-4 原引 :1019-1028 为纠错管线同构段（`analyze_subtitle_correction` :939 起），翻译管线自身预构建在 :1774-1790，回写 review-log 时勘正 |

### M0-3: 断言反转白名单终态（PRD §1.3 预登记 5 例的逐 assert 行复核定稿）

**复核结论（改判，★B-4）**：PRD 预登记的 4 例 R5.3 相关测试场景均为**单批任务**（`_segments(2)`/`(3)`，默认批窗 30 → total_batches=1），按 R5.3 改判后落入「全部批失败仍拒绝零写入」分支——`success is False` 语义**不变**，仅失败文案因 R5.2 中文化需改写一条断言。白名单由「4 个测试函数整例反转」收窄为逐 assert 行：

| 文件:行（当前值） | 所属测试 | 处置 | 理由 |
|---|---|---|---|
| test_llm_translation.py:217 | test_missing_id_batch_fails_after_retry（:192） | **改写**：`assert "uncovered" in result["error"]` → 断言中文文案关键词（定稿要求新文案含「补译」二字，见 M5.2 裁决 3） | R5.2 中文文案落点即此 error 构造（:1973-1977） |
| test_llm_translation.py:224 | 同上 | **保留**（值不变：单批全失败时 uncovered = 全部目标 id；语义从「失败佐证」转「缺口集」，SG-1 守恒不变量断言另以新用例加强） | ledger 记录 failed 批的断言全保留（PRD §1.3 原则） |
| test_llm_translation.py:216/:219-223、:251-254、:281-284、:526-528 | 上述 :192/:226/:256/:518 三姊妹例 | **零改动**（预登记撤销，★B-4） | 单批场景 = 全批失败拒，语义未被 R5.3 触碰 |
| test_llm_translation.py:614 | test_cancel_midway_returns_bare_cancelled（:564） | **反转**：`result_holder == {"success": False, "error": "Cancelled"}` → 断言 `success is False` + `error == "Cancelled"` + `data` 含 `token_usage`/`ledger` 键（docstring :565-567 同步改） | R5.1 取消返回附 data（M0-2 受控改点同源）；:608/:612 两断言保留 |
| frontend AIAssistantPanel.test.ts:301 | estimates the batch count…（:299） | **改写**：`"约 42 批"` → `"约 N 批 · 约 X 万 token"`（N 按新估算式） | R5.13 + SG-5 字符累计估算式，文字必然变化（PRD「前端白名单初版为空」改判，★B-2） |
| frontend SegmentBlocksLayer.test.ts:364、:366 | rejected ranges are still rendered…（:359） | **反转**：「rejected 不过滤、全亮红纹」→「rejected 退场」（R5.10 裁决隐藏案；:359-368 整例意图与断言一起改）。**勘误 E-6**：rejected 过滤是**新增分支**——现状 visibleEditRanges :147-148 仅按 target_type 与视窗过滤、无 rejected 逻辑（:381 注释自证「NOT filtered」），R5.10 改动性质 = 只增，confirmed/pending 面 golden 锁零触碰；对应关系：:364 `toHaveLength(1)` 因新增过滤翻转为 0、:366 类串断言随例删除（★B-3） | R5.10 验收「rejected 覆层隐藏」直接冲突此例的现状锁定断言（★B-3）；PRD :189/:262 同措辞一并回写（★B-10） |

**非 expect 行的测试基建变更不受门禁 grep 约束，按 3.0.4 §4.1 追认制登记**：SegmentBlocksLayer.test.ts:292-294 `findOverlays` 选择器 `[title^="Delete range"]` → `[data-test="range-overlay"]`（R5.9 中文化 :390 title 的配套；overlay div :382-391 纯增 data-test 属性，:311 类名快照 golden 锁零触碰）。

### M0-4: 交付顺序强制

1. **R5.0 必须是全版首个合入项**（立项裁决①）：其后任何 phase 的门禁基线才包含 duplicate 态防护；R5.0 自己的 diff 不触碰 llm/correction 族，与 P1 其余项零冲突。
2. **S5×S1 主从**：R5.8 必须在 R5.3 之后合入（同 `analyze_subtitle_translation` 函数族；受控改点 (d) 与 (f) 同段相邻，:1957-1982 与 :1774-1790，乱序必冲突）；两者同在 P1 内一次改透，禁止跨 phase 交错（PRD §7 顺序约束①②延续）。
3. **S2×D7c 主从**：R5.4 的三态作用域与聚合 patch 是**同一 commit 族**（D7 第三项不是独立交付物——聚合返回形状就是作用域改形的消费面，拆开必产生中间破形）。
4. **R5.1×R5.2×R5.3 同族 hunk**（llm_service :1871-1982 邻域 + main.py handler）P1 内一次改透；R5.1 的 :614 断言反转与 R5.3 的 :217 文案改写随对应 phase 在 record 反转清单登记。
5. **R5.5 独立成相**（P3），但 (a) 的锚区间与 (d) 无重叠（纠错管线 :1116-1187 vs 翻译管线 :1774-1982），P3 与 P1 可并行开发、合入仍按 P1 → P3 序。
6. **golden 锁先行**：任何 SegmentBlocksLayer / keep 相关改动（R5.6/R5.9/R5.10/R5.7）合入前，先跑 `SegmentBlocksLayer.test.ts:287-381` 三态 describe + keep golden 2 例确认基线绿，再动手。
7. **M5.3 内部序（R3 序 7，MF2-2 派生）**：completion payload 缺口合流 hunk（main.py :1317-1331 区 + 返回 dict :1340）必须**先于或同 commit 于**对账渲染消费端改造（AIAssistantPanel :455-467 / WorkspacePage watcher :1069-1087）与 R5.11 的 reset 延后改造（useLlmTasks reset :308-313）——三者消费同一 lastTranslationCompletion 结构，先定数据形状后改消费端，防中间态假绿。
8. **R5.11（P4）与 M5.4（P2）同文件族例外（R3 序 8）**：R5.11 与 M5.4 都落 useWorkspaceActions.ts（handleAcceptHighConfidence / handleClearCorrections）与 pendingCorrections 消费面。P4∥P1-P3 并行开发假设在此收窄：R5.11 的开发基线必须包含 M5.4 的该文件改造，**禁止在未含 M5.4 的分支上并行开发**（P4 并行窗口的唯一显式例外点，PLAN 应登记）。

---

## M5.0: duplicate 幂等返回防呆（R5.0，P1 首项）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| `frontend/src/pages/WorkspacePage.vue` handleRangeDecision | :990-999（pushSnapshot :992 → call :993 → 成功 emit :994-995 / 失败 toast :996-997） | 受控改点 (c)：三分支化 |
| `frontend/src/composables/useUndoRedo.ts` | pushSnapshot :48-58（undoStack 追加 :56、redoStack 清空 :57） | 只增：新 API `popSnapshot()` |
| 后端返回形状（零改动，仅消费） | `core/project_service.py:1353-1356` duplicate 返回 `{"edit_id", "duplicate": True}`，无 revision、无 patch | 只读判据 |
| patch 通道误判护栏（复核，勿改） | `frontend/src/types/project.ts:120-127` isProjectPatch 以 revision 判真；`frontend/src/App.vue:119-136` onProjectUpdated legacy 整体替换 :134 | N3 理由成立的代码事实 |
| 测试宿主 | `frontend/src/pages/WorkspacePage.rangeDecision.test.ts`（describe :270，既有 2 例 :271/:321） | 补第三例 |

**实施裁决**：

1. **三分支**：① `res.success && res.data?.duplicate === true` → **不** emit project-updated、`popSnapshot()` 回滚本次快照、`showToast("该范围已存在，已复用原条目", "info", 2500)`（形态裁决：复用 useToast 轻提示，自动消退，不新增组件）；② 成功 → 维持 :994-995 现状形态逐字节不变；③ 失败 → toast（文案不变）+ `popSnapshot()`（消除 F-B-10 undo 空步）。
2. **快照回滚 API vs 纯时序后移——裁决 = 回滚 API，否决时序后移**：把 pushSnapshot 后移到「成功且非 duplicate」虽在技术上仍能捕获写前态（emit 未执行、projectRef 未变），但违背 PRD R5.0 ②「成功路径维持先行快照 + emit patch 现状形态**不变**」的字面承诺，且引入 await 恢复点后的新时序耦合。采纳 PRD 原案：useUndoRedo 纯新增 `popSnapshot(): UndoRecord | null`（语义 = `undoStack` 移除末条并返回之；空栈返回 null）。**SG-6 裁决**：popSnapshot **不触碰 redoStack**——pop 只发生在「本次 push 之后、响应返回之前」的同步窗口，该窗口内 redoStack 已被 pushSnapshot :57 清空且无再入路径，无需重复清理（在 API docstring 写明该不变量）。
3. **后端零改动**：`add_range_decision` 幂等幂等语义（±0.05s 同 action、零写入零 revision，:1346-1356）是正确设计，本条只修前端消费面（PRD 边界原文）；不补 revision（N3：带 revision 的非 patch 对象会误入 :120-127 patch 通道被 `applyProjectPatch` 空应用）。
4. **两入口一处生效**：波形气泡与 SuggestionPanel 时间码 popover 共用同一 handleRangeDecision，分支改动天然覆盖双入口（**证据勘误 E-5**：原引 App.vue:165-167 实为窗口拖拽 handler，非证据；实据 = WorkspacePage.vue:958 `provide("suggestion:add-range-decision", handleRangeDecision)` + :1619 `@range-decision="handleRangeDecision"` + SuggestionPanel.vue:161-169 注释，:165 明言 SAME handler）。

**验收**：duplicate 返回不进 project-updated（内存态不变）；轻提示出现且自动消退；duplicate 与失败路径 undo 栈长度恢复原值；新增 duplicate 态第三例绿；既有 2 例（:271/:321）零改动全绿。

**耦合点**：无（全前端、P1 首项）；其 `pushSnapshot(["edits"])` 形态是 R5.4 批量快照层的同族先例。

---

## M5.1: 翻译失败/取消成本可见（R5.1，F2+F5）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| 管线取消返回三处 | `core/llm_service.py:1871`（轮询主循环）、`:1903`（批内 Cancelled）、`:1939`（429 串行循环）——E-1 勘误的三处全数核实 | 白名单内键级只增：附 `data: {"token_usage": total_usage, "ledger": ledger.to_dict()}` |
| 管线失败返回 | :1978-1982 已带 `data: {ledger, token_usage}`（handler 现状在 :1266-1269 丢弃） | 零改动（数据源已在） |
| handler 失败/取消分支 | `main.py:1266-1269`（emit llm:analysis_failed + raise）；cancel_event 作用域 :1258-1264（:1261 传参） | 受控改点 (e) |
| 权威取消判据（参照，勿改） | `core/task_manager.py:299-301`（RuntimeError("Cancelled") 消息 or cancel_event.is_set()） | 只读同构参照 |
| 429 串行信号源 | `core/llm_service.py:1942` progress message `"(serial)"` 后缀（串行降级循环 :1937-1942） | 只读，前端子串匹配 |
| token_usage 前端消费 | `frontend/src/composables/useLlmAnalysis.ts:30-43`（TokenUsagePayload :5-9 无 status 键，未知键自然忽略） | 类型只增 status? 键 |
| 取消中性提示落点 | `frontend/src/pages/WorkspacePage.vue:604-616` EVENT_TASK_CANCELLED 分支——**现状不含 `llm_translation`**，翻译取消无任何提示 | 补 task_type 分支 |
| errorMsg 残留修复 | `frontend/src/composables/useLlmTasks.ts:245-248`（task:cancelled 只复位 isRunning/progress，不清 errorMsg） | 补 errorMsg 清空 |
| progress message 消费 | `frontend/src/composables/useLlmTasks.ts:256-264`（现状只取 percent，message 丢弃） | 新增 progressMessage 单例 ref |

**实施裁决**：

1. **取消判据 = handler 侧事件优先（焦点 5 / MF-2）**：`_handle_translation` 失败分支改为 `cancelled = cancel_event.is_set() or result.get("error") == "Cancelled"`——事件为主判据、字符串仅兜底，与 task_manager :299-301 双通道同构；**不**在 envelope 增 `cancelled` 标记键（三处返回点 :1871/:1903/:1939 天然全覆盖，无需逐点枚举）。管线取消返回附 data（token_usage/ledger）与「不加标记键」不矛盾：data 是 PRD 要求的上报载体，`error` 串保持 `"Cancelled"` 不变（test_translation_smoke_fix.py:169 既有断言因此零改动）。
2. **取消路径**：emit `llm:token_usage`，payload = 管线 data.token_usage + `status: "cancelled"`；**不再** emit `llm:analysis_failed`；仍 `raise RuntimeError("Cancelled")`（保 task_manager 取消判别，不产生失败红框）。前端：WorkspacePage :604-616 分支补 `llm_translation`，文案裁决 = `翻译已取消，已消耗约 X tokens`（X 取 useLlmAnalysis.lastUsage.total_tokens；事件时序天然有序——token_usage 先 emit、raise 后才有 task:cancelled，lastUsage 必已就位）；useLlmTasks :245-248 补 `errorMsg.value = null`（消除残留路径；**SG2-2 裁决：补 task_type 判据限定 `llm_translation`**——该监听现状无类型过滤 :245-248，不滤则行为面扩散至全部任务类型，违反改动面与需求面一致；其余类型取消残留 errorMsg 为既有独立缺陷，登记 record §8 遗留不顺手修复；前端已核无既有断言锁「取消后保留 errorMsg」）。
3. **失败路径**：handler 从 `result["data"]` 提取 ledger/token_usage → emit `llm:token_usage`（`status: "failed"`，另附 `failed_batches: ledger.failed`）→ 再 emit `llm:analysis_failed` → raise。验收「失败批 [n]/N」由 failed_batches 支撑。
4. **429 降级透出（零后端改动）**：useLlmTasks :256-264 handler 增存 `detail.message` 至新单例 `progressMessage`；AIAssistantPanel 进度区当 message 含 `"(serial)"` 子串时显示「限流中，已切串行，剩余批次处理中」（**裁决：前端子串映射中文，不新增事件、不加后端键**；N 的精确剩余数需管线额外上报，本版不做，避免 payload 结构变更）。
5. **成功路径零改动**：`llm:token_usage` 成功消费链（useLlmAnalysis :30-43 累计逻辑）与 handler :1332 成功 emit 均不动；status 纯增键向后兼容。**MF2-2 唯一例外（R5.3 hunk，非本项改动）**：completion payload 组装点 :1317-1331（:1328 `uncovered_ids`）按「写侧对账 ∪ 管线缺口」合并口径改造（见 M5.3 裁决 4），属 M5.3 登记改点；本项自身触点面不变。

**验收**：取消/失败均触发 token 上报且面板可见「已消耗 X tokens、失败批 [n]/N」；取消显示中文中性提示、无英文 "Cancelled" 红框、errorMsg 不残留到下一任务；连续 429 时进度区可见降级状态；既有 useLlmTasks.progress/translation 测试零改动全绿。

**耦合点**：M5.2 失败中文文案与本项失败上报同 commit 族交付（PRD R5.1 边界）；M5.5 复用本项确立的「事件优先判据」措辞。

---

## M5.2: 行级解析兜底 translated_text + 失败中文出路指引（R5.2，F3）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| 第 4 层行级解析 | `core/llm_service.py:612-634`（`_parse_json_response_layers` :565 起；relevance 模式 :615-623 → action 模式 :626-634） | 只增：末尾追加 translated_text 模式 |
| 失败 error 构造 | :1973-1977（英文 `Translation incomplete: ... failed after retry ... uncovered`） | 受控改点 (d) 文案面：中文化 + 出路指引 |
| 覆盖校验复用（零改动） | `_validate_translation_coverage` :1614 起；行级救回的批照走 coverage 反向校验（:1814-1821 调用点） | 只读边界确认 |
| 纠错无副作用确认 | 纠错输出键集 = segment_id/corrected_text/…（`analyze_subtitle_correction` :1066-1074 消费），无 translated_text 字段 | 只读核查结论 |

**实施裁决**：

1. **模式与优先序**：第 4 层追加第三正则 `pattern_translated = "segment_id"\s*:\s*"([^"]+)".*?"translated_text"\s*:\s*"((?:[^"\\]|\\.)*)"`，置于 relevance/action **之后**（裁决：顺序无语义冲突——relevance/action 输出不含 translated_text 键，互斥匹配；放末尾保证既有两模式路径零回归）。逐行条目归一为 `{"segment_id", "translated_text"}`，命中即随 :622-623 同款早退返回。
2. **救回批不绕校验**：行级救回的 translations 进入 `_call_batch` 既有 coverage 反向校验（:1814），漏译/未知 id 照旧进 ledger 不静默（PRD 边界原文，锚点已核）。
3. **中文文案落点分裂（R5.3 改判后的定稿）**：R5.3 改判后 :1967 `if ledger.failed:` 分支语义改变，R5.2 的中文文案因此落两处——(i) **全部批失败拒绝**（新分支，M5.3）：`翻译失败：{failed}/{total} 批处理失败（批 {ids}），本次未写入任何译文；可直接重试；反复失败建议更换模型或检查网络`；(ii) **部分成功通知**不再走 error 通道，改由完成事件 payload（uncovered_ids，含 MF2-2 管线缺口合流）驱动前端 toast（M5.3 裁决 4/7）。**定稿约束：两文案均含「补译」二字**——这是 M0-3 白名单 :217 断言改写的锚定关键词。
4. **确定性单测（焦点 1 三件套 + SG-1）**：不做 golden 文件。新增 ≥4 例：逐行 segment_id+translated_text（非 json_mode mock）解析成功且全量守恒；不可救回（垃圾输出）任务返回中文指引文案且 data 带 ledger/token_usage（与 M5.1 闭环）；relevance/action 两模式既有用例（test_llm_phase4b.py:68-130 区）零改动全绿；解析层共享函数直测 translated_text 模式对纠错形态输入（无该字段）返回走既有路径。

**验收**：非 json_mode 逐行近 JSON 输出可救回且守恒；批不可救回时错误为中文指引、红框无英文技术体；既有解析层断言零改动。

**耦合点**：文案 (i) 与 M5.3 全批失败拒绝共用同一构造点；测试与 M5.3 用例矩阵合并计数（PRD §7.4 R5.2 ≥4 / R5.3 ≥10）。

---

## M5.3: 翻译增量补译 + uncovered 对账可读化（R5.3，S1，本模块最高风险）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| 失败语义改判 | `core/llm_service.py:1957-1982`（uncovered 推导 :1957-1962；全量守恒 fail :1964-1982；旧口径注释 :1964-1966） | 受控改点 (d) |
| 入口同语言校验 | `main.py:2996-3006`（同语言轨存在 → 拒绝 +「可清空或删除该轨后重试」）；语言映射 `_TRANSLATION_LANGUAGES` :30-40 | 受控改点 (e)：改拒为条件路由 |
| 批窗口与预构建 | `core/llm_service.py:1753-1769`（target_windows 口径，SG-5 同式）、:1774-1790（预构建） | (d) 邻域只读（R5.8 才动 :1774-1790） |
| 新增合并写方法 | `core/project_service.py:716` create_translation_track 之后插入 `merge_translation_track` | 只增 |
| 既有 uncovered 先例 + **缺口合流触点（MF2-2）** | handler 完成上报 `main.py:1317-1331`（:1326 written_count；:1328 `uncovered_ids` 现只取写侧对账 report，改合并口径，返回 dict :1340 同步）；双语导出仅绑定段成双行 `core/export_service.py:467-484`（docstring :481-483 明示 unbound 单行） | :1317-1331/:1340 = **登记改点**（M0-1 main.py 行 / M0-2 (e)）；导出面只读同构依据 |
| 前端入口/快照 | `frontend/src/pages/WorkspacePage.vue` handleStartTranslation :1046-1061（pushSnapshot ["tracks","bindings"] :1051；语言记忆 :1057-1059 仅 started 后写回） | 补译标记 + toast 分支 |
| 完成消费 | useLlmTasks :181-190（lastTranslationCompletion 单例）→ WorkspacePage watcher :1069-1087（translationNotice :1072-1077） | toast 分支 + notice 结构扩展 |
| 对账可读化渲染 | `frontend/src/components/workspace/AIAssistantPanel.vue:455-467`（现状 `uncoveredIds.join("、")` :465 裸内部 id）；mainSegments prop :48/:219 已在 | 渲染改造 + 一键补译 |
| 管线返回消费 | `main.py:1286-1299` items 组装（source_by_id 反查）| 补译路由下段源=缺口子集，零改动复用 |

**实施裁决**：

1. **缺口推导（N1 / 焦点定稿）**：缺口集 = 主轨 subtitle 段（排除 confirmed-deleted）id 集 − 该翻译轨 bindings 的 `main_segment_id` 集合（**覆盖口径只看 bindings 差集，不考察 extension 侧存活**——与导出映射 :467-484 同口径）；运行时在 start_translation 校验段推导，不持久化 ledger（N1 原文）。
2. **自动路由（Q2）**：`start_translation` :2996 校验段改判——同语言轨存在且缺口集**非空** → 转补译：create_task payload 纯增 `resumable_track_id` 与 `gap_segment_ids` 两键（MVP 约束允许 payload 键增，非新 expose/新任务类型）；缺口集**为空** → 维持 :3000-3006 拒绝原文案不变（「同语言完整轨重译仍被拒」验收）。handler 按 payload 分支：补译时管线段源 = 缺口段子集、完成走 `merge_translation_track`。
3. **管线失败语义改判（受控改点 d 定稿）**：:1964-1982 重构为两分支——`len(ledger.failed) < total_batches` → **部分成功**：按 :1984-1993 既有合并序返回 `success=True` + 已完成批 translations + ledger（failed 批号与 uncovered 集保留记录，**PRD 已列的 1/34 落盘语义**）；`len(ledger.failed) == total_batches` → **全批失败拒绝零写入**：返回中文拒绝文案（M5.2 裁决 3 文案 (i)）+ data 照旧。无失败路径（:1984 起）逐字节等价。handler :1271 起对部分成功结果的**消费逻辑**零改动（completion payload 的缺口合流改造单列为裁决 4，登记改点）——items 天然只含已完成批，`create_translation_track` 既有 uncovered 对账（含空 items 拒绝）继续兜底「主轨变更落空」语义。
4. **completion payload 缺口合流（MF2-2，R4 新增裁决）**：管线部分成功分支返回的 `ledger.uncovered_segment_ids`（含失败批 id，:1957-1962）必须进 completion 事件——handler 完成分支 :1328 `uncovered_ids` 由「写侧对账 report 单源」改为「**写侧对账 ∪ result.data.ledger.uncovered_segment_ids**」去重并集，返回 dict :1340 同口径。否则 1/34 场景下 33 批 items 全部命中主轨 → 写侧 uncovered 为空 → WorkspacePage :1072 notice 不触发 → 对账可读化与一键补译（裁决 8）无渲染入口，验收首条必挂。「本次补译 N 段」（written_count :1326）与缺口差集推导（裁决 1）口径不受影响——差集推导天然涵盖失败批。登记面：M0-1 main.py 行 + M0-2 (e) + 附录 A（登记改点）。
5. **合并写方法契约**：`merge_translation_track(timeline_id, track_id, items, bind=True)` 单 hunk 只增——入口双保险再查（轨存在 ∧ role="translation" ∧ 缺口 id 与轨内既有 binding 无 1:1 撞配，撞配即拒零写入）→ 段 id 沿用 `track_{track_id}_seg_{start:.3f}` 命名空间，生成时对轨内既有段 id 查重、撞号即显式失败（差集推导下不应发生，防御性拒绝优于静默覆盖）→ `track.model_copy` 增段 + bindings 增补（offset=0，与 create_translation_track 同法）→ **单 `_success_patch(tracks, bindings)`**（:158-176 唯一构造入口，revision +1），meta side-channel 携带 `merged_count`。禁止逐段 patch。**SG2-3 裁决（改判：目标接受、手段否决）**：**不抽**共享私有 helper——抽 helper 必须改 `create_translation_track` 既有函数体为委托调用，破坏 M0-1「单一 hunk、零删改」承诺并扩大红线审查面；merge 自含实现、按 create 同法复制既有内部段（pinning/命名空间/bind offset=0/单 patch），维持 project_service 单一方法复制先例，约三成差异逻辑（免语言拒绝、撞配拒绝）本就须独立实现，hunk 面由本条契约收敛。
6. **undo 一次回退（零新增改动）**：补译走 start_translation 同一路由，handleStartTranslation :1051 的 `pushSnapshot(["tracks","bindings"])` 天然覆盖；merge 单 patch 落盘 → undo 一次整体回退整批补译。
7. **「本次补译 N 段」toast**：裁决前端判定——handleStartTranslation 在 pushSnapshot 前检查 `projectRef` 是否已存在同语言 translation 轨，置页面级 `pendingResumable = { trackId, language }` 标记；completion watcher :1069 命中标记 → toast「本次补译 {written_count} 段」并清标记（written_count 取 completion payload 既有键，main.py :1326）。零后端改动。**SG2-1 补清理路径（采纳）**：toast 前置 `completion.track_id === pendingResumable.trackId` 比对，命中才 toast 并清——补译不建新轨（同轨合并），新建翻译轨 id 天然不匹配，比对既防误报又使残留标记自愈；task:failed / task:cancelled 分支显式清 `pendingResumable`（双保险：补译任务失败/取消时 completion 不触发，无比对则标记跨任务残留、下次任一翻译完成将误报「本次补译 N 段」）。
8. **对账可读化（US-10 / F-A-04）**：AIAssistantPanel :455-467 改造——uncoveredIds 逐条经 mainSegments 解析为「{mm:ss} {text 截前 20 字}」列表（panel 已持有 mainSegments prop :48/:219，解析为纯前端 computed）；条目可点击定位主轨对应段（复用面板既有 seek/定位 emit 链）；尾部一键「补译这些段」按钮 → 经既有 translation 卡路由发起（语言取 completion.language 记忆值）。:465 裸 join 渲染废除。
9. **测试（≥10，PRD §7.4 + SG-1）**：失败批降级 uncovered（1/N mock：33/34 落盘 + 缺口可见）；全批失败拒零写入；无失败路径逐字节等价（断言全键）；**SG-1 守恒不变量**：`ledger.uncovered_segment_ids == 目标 id 集 − 实际返回 translations 覆盖 id 集`（双向无多无少）；**MF2-2 合流断言**：部分成功分支 completion payload `uncovered_ids` == 写侧对账 ∪ 管线缺口去重并集（1/N 场景写侧为空时事件仍含缺口 id）；补译缺口推导（请求 id 集恰为缺口集 mock）；merge 单 patch（revision +1、tracks+bindings 双层、无逐段 patch）；写侧双保险两拒例；uncovered 对账数据结构；同语言完整轨重拒；补译 mock 断言 merge 而非 create。

**验收**：1/34 失败其余 33 批落盘且缺口对账可读可定位可一键补译（**缺口含管线侧 ledger.uncovered——MF2-2 合流后管线缺口段可见**，1/N 场景 notice 必触发、一键补译入口必在）；补译 mock 请求集恰为缺口集；合并 revision +1、undo 一次回退；全批失败零写入中文拒；同语言完整轨重译仍拒且文案含指引。

**耦合点**：缺口合流 hunk 先行或同 commit 于消费端改造（M0-4 序 7）；R5.8 后于本项合入（M0-4 序 2）；payload 预构建段 :1774-1790 与本项改判区 :1957-1982 同函数相邻，P1 内一次改透；对账渲染与 R5.11 审阅过滤无文件冲突（AIAssistantPanel 不同区块）。

---

## M5.4: 批量审阅收口（R5.4，S2 + D7 第三项，MF-1/MF-3/SG-4 落点）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| accept_high 主体 | `core/correction_service.py:446-502`（qualifying 过滤 :471-474 现状**不分轨**；逐条循环 :484-487 失败静默跳过 :486-487；返回 :499-502 `{accepted_count, remaining_count}`） | 受控改点 (b) |
| clear 主体 | :504-532（cleared 计数 :519；零快速路径 :520-521；过滤 :523-526；返回 :532 `{cleared_count}`，走 `_update_timeline_by_id` 无 patch） | 受控改点 (b) |
| 逐条 accept 分流（复用） | :290-291（`scope_track_id = payload.get("track_id", "")`）；副轨写回 :296-301 | 只读，抽核心时复用其逻辑 |
| 聚合 patch 构造入口 | `core/project_service.py:158-176` `_success_patch(meta=None, **layers)`；ProjectPatch 层可选 `models.py:447-461` | 只读依据（焦点 2） |
| expose 透传 | `main.py:2755-2768` / :2771-2778（`_mark_dirty` 薄透传） | 登记改点 |
| 前端消费 | `frontend/src/composables/useWorkspaceActions.ts:993-1003` handleAcceptHighConfidence（**现状无快照**；diffCache 清 :998；switch_timeline 全量刷新 :999-1000）；handleClearCorrections :1005-1014（window.confirm :1006） | 受控消费面（D7c） |
| 快照层先例 | correctionUndoLayers :69-73（主轨 ["segments","analysis"] / 副轨 ["tracks","analysis"]，reject 用法 :976-980） | 三态扩展 |
| 批量按钮区 | `frontend/src/pages/WorkspacePage.vue:1692-1707`（「信任全部高置信度 (N)」:1698 /「清除全部」:1703） | 文案作用域化 |

**实施裁决**：

1. **三态作用域（★B-1 改判，覆盖 PRD N5 字面）**：后端形参定为 `track_id: str | None = None`——`None` = 既有 timeline 级无差别（既有调用与断言零改动、逐字节等价）；`""` = **主轨作用域**（qualifying 过滤 `detail.track_id == ""`）；非空 = 副轨作用域。**改判理由**：PRD N5 的 `str = ""` 无法区分「未传（timeline 级）」与「主轨」，按其字面则主轨视图传 `""` 仍是 timeline 级，直接违反 PRD 自己的验收「主轨视图批量接受/清除不动副轨待审集」；三态化是唯一同时满足 N5 兼容意图与验收的形状。前端三态传值：主轨视图传 `""`、副轨视图传 `activeListTrackId`、「全部」视图传 `null`（timeline 级 + 文案明示「含全部轨道 N 条」）。clear 同构：`None` 全型清（既有）、`""`/非空按型清。
2. **聚合单 patch（焦点 2）**：把逐条 accept 的应用核心抽为内部无 patch 方法 `_apply_one(result_id) -> (bool, set[Layer])`（复用 :269-301 既有逻辑含钉扎/时间断言/置信度），批量循环消化脏层并集后**一次** `_success_patch(segments=?, tracks=?, analysis=?)`，revision 恰 +1；返回 data = `{accepted_count, remaining_count, patch}`——**纯增 patch 键、旧键保留**（MF-3 超集兼容，3.0.4 accept 超集先例 review-log-v3.0.4 #14）。clear 返回 `{cleared_count, patch(analysis)}` 同口径。逐条 accept/reject 既有返回零改动。
3. **批量 undo 三态层（MF-1）**：`correctionUndoLayers(entry, scopeTrackId: string | null)` 扩展第二形参——`null`（全部）→ `["segments","tracks","analysis"]` 三层并集、`""` → 主轨两层、非空 → 副轨两层（「全部」视图 qualifying 天然混含主/副轨结果，两层快照必挂 undo，故三层）。与后端三态同构一一对应。
4. **前端消费链（D7c + MF-3）**：handleAcceptHighConfidence 改造——按三态层 pushSnapshot → `acceptHighConfidenceCorrections(tlId, 0.8, scopeTrackId)` → `res.data.patch` 存在则 `emit("project-updated", patch)` 单次 applyProjectPatch 驱动刷新（diffCache 失效 :998 保留在前），**移除** switch_timeline 全量刷新（:999-1000；防御：无 patch 键回落旧行为）→ toast 用返回值 `accepted_count`。handleClearCorrections 同构 + confirm 文案作用域化。
5. **计数口径（SG-4）**：确认文案 N = 前端按 scope 过滤 `pendingCorrections` 的计数（accept_high 区高置信度 + clear 区全部待审）；完成 toast N = 后端返回 accepted_count/cleared_count 如实展示（逐条失败被静默跳过 :486-487 的偏差由两处口径分工消化，不阻塞交互）。
6. **确认文案定稿**：主轨「将接受当前轨〈主轨〉的 N 条高置信度建议」；副轨「…〈{track_name}〉…」；全部「将接受**全部轨道**的 N 条高置信度建议」；clear 同型（「清除…待审建议」）。落点 = WorkspacePage :1692-1707 批量条改为确认按钮（confirm 交互形态沿用 window.confirm，不加弹窗组件）。
7. **测试（≥6）**：主轨视图批量接受不动副轨待审集（三态 `""` 用例，★B-1 回归锁）；副轨视图不动主轨；「全部」= timeline 级兼容（`None` 既有断言零改动全绿即证）；聚合单 patch revision +1 且含 patch 键；逐条路径返回形状零改动；undo 三态各一次回退（含三层并集例）。

**验收**：默认 `None` 路径逐字节等价既有行为；主/副轨互不误吞；undo 一次整体回退（三态）；确认文案含轨名/「全部」与条数；聚合单 patch 既有断言零改动全绿。

---

## M5.5: 纠错取消轮询化（R5.5，F4，焦点 3 状态矩阵落点）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| 纠错管线双循环 | `core/llm_service.py:1116-1166`（`with` :1116 / as_completed :1122 / 取消返回 :1125、:1146 / 429 降级 break :1148-1157）+ 串行循环 :1171-1187（取消返回 :1174、逐批 cancel 检查 :1173） | 受控改点 (a) |
| 翻译侧 1c 样板（复刻源） | :1848-1856（轮询动机注释 + `_CANCEL_POLL_SECONDS = 1.0`）、:1857-1862（无 with 的 executor）、:1865-1871（wait(timeout) + 取消即 shutdown(wait=False, cancel_futures=True) + return）、:1873-1876（两循环都必须能退出的教训注释）、:1930-1934（finally 非阻塞 shutdown） | 只读复刻源 |
| 串行信号恒定 | 纠错 :1177 `"(serial)"` message（与翻译 :1942 同构） | 只读 |
| 测试样板 | `tests/test_translation_smoke_fix.py::TestCancelLatency::test_cancel_observed_while_batches_blocked` :139-172（栅栏阻塞 + 0.3s 后 cancel + ~2s 断言返回）；:174 起 happy path 例 | 复刻样板 |
| 既有交织缺口 | 该文件仅 TestResolvedLlmConfig :82 / TestCancelLatency :138 两类，**无 429×取消交织例**（SG-2 证实） | 新增用例空间 |

**两循环 × 三退出状态矩阵（焦点 3 定稿）**：

| 退出 \ 循环 | 外层：轮询循环（改造后 :1122 位形的 `wait(timeout=1.0)` 主循环） | 内层：sorted(done) 批消化体 | 串行降级循环（:1171-1187 形位） |
|---|---|---|---|
| 正常完成 | outstanding 清空自然退出；finally 非阻塞 shutdown（翻译 :1930-1934 同款） | `future.result()` 正常取回（done 内 future 已完成，不会因 cancel_futures 抛 CancelledError——1c 教训 2 的边界） | 逐批完成自然退出；无 extra 条件 |
| 取消 | 轮询检测 `cancel_event.is_set()` → shutdown(wait=False, cancel_futures=True) → return 裸 envelope（新 :1125 形位）；**教训 1：必须两循环都能退出** | 批消化体内 `error == "Cancelled"`（`_process_batch` 逐批检查产生，对应现 :1144-1146）→ 同款立即 return；取消后**不得**继续消化 done 剩余 future | 循环头逐批 cancel 检查（:1173 已在位）→ return（:1174） |
| 429 转串行 | `consecutive_429 >= 3` → 置 serial_fallback + stop_polling 标志 + **break 两层**（翻译 :1877/:1913-1915 教训 1 的 429 侧：原单循环一个 break 即可，双循环必须置标志跨出消化体再跨出轮询体） | 消化体内检测到降级置标志即 break（不再消化本 poll 批次） | 不适用（降级后由串行循环接管 pending） |

> **记账判据注记（MF2-1，R4 冻结）**：本矩阵只裁「退出路径」，**不动记账**——串行循环记账判据 = not-corrections（:1182-1185 现状），**非翻译侧 error 判据**（:1947-1953）；两管线判据差异与聚合等价断言的对应口径见裁决 1/2。

**实施裁决**：

1. **纯轮询化，不做状态机重构**（焦点 3）：逐行复刻翻译侧形态——`with` 改 executor 变量 + try/finally 非阻塞 shutdown；as_completed 改 `wait(outstanding, timeout=1.0, return_when=FIRST_COMPLETED)`；done 按 batch_idx 排序消化（保 ledger/progress 序稳定，翻译 :1878-1882 注释同款）；429 降级改「置标志 + 双层 break」（上表）；串行循环体逐批 cancel 检查保留（:1173）。**记账判据冻结（MF2-1）**：串行循环记账保持 :1182-1185 现状 **not-corrections 判据，不复刻**翻译侧 :1947-1953 error 判据——两管线判据差异是 v3.0.4 现状事实（纠错外层 :1135-1142 error 判据 vs 纠错串行 :1182-1185 not-corrections 判据），根源 = `_call_batch` 解析失败 :1054-1056 返回 `error=None` 且 corrections 空：error 判据下该批误记 succeeded、not-corrections 判据正确记 failed，若照抄翻译侧则串行降级下的 parse-None 批从 failed 改记 succeeded → ledger 集合变化 → 聚合等价验收必挂。本轮只保聚合等价、不顺手统一两管线判据（record 登记该既有不对称）。
2. **成功路径等价口径**：聚合等价断言锁 `corrections_by_index` 内容 + `total_usage` 数值 + `ledger` 集合（failed/retried_ok/succeeded/uncovered），**不锁 list 顺序**（as_completed 完成序改轮询排序后 ledger.failed 追加序可能变）；锁面点名「**串行 × parse 失败**」组合：串行降级下 parse-None 批仍记 failed（not-corrections 判据，MF2-1 冻结），ledger 集合不变；纠错既有断言零改动全绿。
3. **串行降级 × 取消两交织用例（SG-2，R5.5 额度上修 ≥4）**：(i) 转串行后 cancel 立即置位 → 串行循环首批检查即返回且 pending 未执行批的 mock 调用计数为零；(ii) 轮询循环内触发 429 降级路径（连续 429 mock）→ 正确进入串行循环且两循环退出无悬挂；(iii) **串行 × parse 失败锁面例（MF2-1）**：串行循环内 `_call_batch` 返回 error=None 且 corrections 空 mock → 该批记 failed、聚合等价断言绿（锁 not-corrections 判据未被轮询化改变）。样板复刻 :139 栅栏法。
4. **取消 1s 断言样板**：复刻 :139-172（60s 栅栏阻塞全部 in-flight，0.3s 后 cancel，`worker.join(timeout=5)` 内返回 + `error == "Cancelled"`），针对 `analyze_subtitle_correction`。
5. **纠错侧 token 上报与中性提示——裁决本版不做**（PRD R5.5 边界「SPEC 评估」的答复）：取消延迟修复与上报机制分属两族改动，纠错侧上报需同样给 :1125/:1146/:1174 附 data 并扩 (a) hunk 面，收益/风险比劣于翻译侧（翻译侧已有失败 data 载体），维持 PRD §10.2 ② 登记不动。

**验收**：大批量纠错取消约 1s 返回（单测断言）；成功路径聚合等价断言绿；429×取消两交织例绿；纠错既有断言零改动全绿。

**耦合点**：(a) 区间与 (d)/(f) 无重叠（纠错 :1116-1187 vs 翻译 :1774-1982），P3 可与 P1 并行开发；「事件优先判据」与 M5.1 措辞一致。

---

## M5.6: keep 可感知收口（R5.6，S3，US-05 三要点）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| 确认文案现状 | `frontend/src/components/workspace/SuggestionPanel.vue` confirmTitle :154-159（manual 专用）→ 绑定于确认按钮 `:title` :496 | 直显化改造 |
| invalidated_count 后端（零改动） | `core/project_service.py:2915-2935`（计数 :2915-2927 + 日志 :2931-2935）；进入返回值 :2986（E-2 勘误后的精确行） | 只读，前端补收 |
| 前端丢弃点 | `frontend/src/composables/useEdit.ts:181-202`（返回类型 :181-185 与 call 泛型 :186-191 均无 invalidated_count，:195-199 丢弃） | 类型扩展 |
| 覆层 hover | `frontend/src/components/waveform/SegmentBlocksLayer.vue:390`（`Delete range: X - Y` 硬编码 title；:377-381 三态注释） | 中文化 + 语义化（与 R5.9 同 hunk） |
| 覆层数据源 | visibleEditRanges :141（纯前端计算，红蓝相交检测落点）；editRangeClasses :171（golden 锁面，零触碰） | 相交标注 computed |
| 导出确认页落点 | `frontend/src/pages/ExportPage.vue:415-416`（confirmedEdits 计数行，摘要区） | 增一句静态说明 |
| golden 锁 | `SegmentBlocksLayer.test.ts:287-381`（:289-290 类快照常量；:311 confirmed delete 全等断言；:364/:366 rejected 例见 M0-3 白名单） | 约束面：class 计算零触碰 |

**实施裁决**：

1. **直显形态（US-05 要点 1）**：manual 条目确认按钮旁内联小字（`<span class="text-[10px] text-ink-muted">确认 = 参与裁剪计算，非导出动作</span>`，keep 条目加「保留区间将从自动裁剪中扣除」）——裁决小字而非仅 toast：hover 依赖彻底消除且 DOM 变更局限于 :492-500 按钮容器内；:496 `:title` 保留（渐进增强不删）。确认动作 toast 差异化（keep/删除两文案）随小字一并交付。
2. **invalidated_count 透传**：useEdit.ts :186-191 泛型与 :181-185 返回类型补 `invalidated_count: number`，:195-199 返回对象补该键；重跑 toast 落在调用方（WorkspacePage keep 重跑 handler）——「新增 {new_edits} 条、按保留区间清除 {invalidated_count} 条旧区间」（invalidated=0 时只报新增）。后端零改动。
3. **红蓝并存提示（与 R5.9 合并施工）**：覆层 title 语义化为「{保留|删除}范围 {X}-{Y}s（{状态中文}）」；visibleEditRanges :141 computed 内做纯前端相交预聚合（keep×delete 相交的块追加「；与重叠区间导出按删除处理」尾注）。**裁决相交检测放 computed 层**（一次遍历成对比较，渲染层零逻辑）；editRangeClasses :171 与 :289-290 类快照面零触碰（confirmed delete 红纹逐字节 golden 锁不破，M0-4 序 6）。导出确认页在 ExportPage :415-416 摘要计数行下增静态说明一句「保留区间与删除区间重叠时，导出按删除处理」。
4. **不加确认弹窗**（PRD 边界）：三点均为文案/toast/类型面，零数据层改动（keep 计算 :2915-2989 与导出消费语义零触碰）。

**验收**：确认防误解文案不依赖 hover 可见；重跑 toast 汇报 invalidated_count 与 new_edits；红蓝重叠在覆层 hover 与导出确认页可见「按删除处理」；golden 锁 describe（:287-381）全绿。

---

## M5.7: 波形编辑模式一致性（R5.7，S4，trim 冻结矩阵落地，SG-3 + 焦点 4 落点）

**触点表（结构已实查——SG-3 的共享组件风险成立且比预登记更深一层）**：

| 触点 | 锚点（核实值） | 说明 |
|---|---|---|
| 副轨块渲染与 trim 使能 | `frontend/src/components/workspace/TrackLane.vue`：updateTime prop :24（**提供即 trim 可编辑**，docstring :16-18 明示）；无 globalEditMode prop | **守卫主落点 A**：TrackLane 本身就是轨角色（主轨块不经此组件） |
| lane 右键菜单 | TrackLane.vue openLaneMenu :84-91 / openBlockMenu :77-81；结构项渲染 :188-205（删除段 :190 / 清空轨 :196 / 删除轨 :202） | **守卫主落点 B** |
| 共享块组件 | `frontend/src/components/waveform/SegmentBlock.vue`：trim 手柄 :251-257、拖拽使能仅看 updateTime :162；globalEditMode prop :38/:63 **声明但未消费 trim 门** | 主轨 trim 编辑态可用 = 现状基线，零改动即零回退 |
| 主轨块层（勿动） | WaveformRow.vue 主 lane 区 :306-335（层实例 :312、trim 转发 :332）；WaveformEditor.vue 基础模式直挂层 :1470-1487 | 主轨零回退面 |
| TrackLane 两处实例化 | WaveformRow.vue :339-359（多行模式，update-time :350）；WaveformEditor.vue :1545-1562（基础模式，update-time :1550-1554） | **globalEditMode 透传点** |
| 守卫先例 | SegmentBlocksLayer.vue :249-289（split/delete 编辑态拦截 + `emit("toast", "请退出编辑模式后重试")`） | 文案与交互对齐源 |
| toggle title | WaveformEditor.vue :1243-1251（建段 toggle，title :1247）/:1252-1261（范围标记 toggle，title :1257） | 文档同步面 |

**实施裁决**：

1. **守卫落点轨角色条件化（SG-3 / 焦点 4b）**：守卫加在 **TrackLane**（组件边界即轨角色，主轨块物理上不经过它），**严禁**在共享的 SegmentBlock/SegmentBlocksLayer 内无差别拦截——后者会把主轨 trim 一并冻住，制造矩阵维度 3 明文禁止的「主轨行为收窄」。实现：TrackLane 增 `globalEditMode?: boolean` prop（WaveformRow :350 附近与 WaveformEditor :1550 附近两处透传，两父均已持有该状态）；trim 门 = 传给 SegmentBlock 的 `:update-time="globalEditMode ? undefined : updateTime"`（undefined 即既有只读语义 :17，零新机制）；lane 菜单结构项（:190/:196/:202 三 handler）编辑态拦截 + toast。
2. **toast 通道**：TrackLane 增 `toast` emit（:29-37 emits 纯增一项），两父转发至既有 toast 链（WaveformRow :331 同款转发、WaveformEditor :1556 附近增一行）；文案对齐守卫先例「请退出编辑模式后重试」。
3. **矩阵文档化（焦点 4a）**：双 toggle title（:1247/:1257）与 README 3.0.x 段写明——「编辑模式 = 文本校对独占态：副轨块 trim 与 lane 结构操作（建段/清空轨/删除轨）冻结并提示退出；**主轨块 trim/菜单/手势维持 2.x 基线不受限——主/副轨不对称是刻意结果**（主轨为 2.x 不可动基线，副轨为 3.0.x 新增面按新规则）」。toggle 的 title 点名主体，不写「冻结矩阵」四字了事。
4. **主轨零回退正反断言**：正向 = SegmentBlocksLayer/WaveformEditor 主轨手势与 trim 既有锁零改动全绿；反向 = 新增 1 例「globalEditMode ON 时主轨块 trim 手柄仍可拖动」（挂真实 SegmentBlock，断言 updateTime 被调用）——防未来有人在共享层补守卫误伤（PRD §4 R5.7 验收补强，SG-3 建议采纳）。
5. **查询类不拦（矩阵维度 2）**：lane 菜单折叠/定位/信息类项不拦（现状菜单仅 :190/:196/:202 三个结构项 + seek，边界天然清晰，无需白名单机制）。

**验收**：编辑态副轨 trim 与三结构项被拦且有中文 toast；退出后全部恢复；主轨手势矩阵既有断言零改动全绿 + 反向断言绿；README/toggle 文档含不对称理由。

---

## M5.8: 质量模式开关（R5.8，S5，MF-4 受控改点 (f) 落点）

**触点表**：

| 触点 | 锚点（核实值） | 改动性质 |
|---|---|---|
| config 键 | `core/config.py:57-90` DEFAULTS，:82 `llm_translation_target_language` 后追加 `"llm_translation_quality_mode": False`（1 行） | 白名单内只增 |
| 管线设置读取点 | `core/llm_service.py:1740-1744`（load_settings + batch_size/ctx/concurrency/max_chars 四键） | 增读第 5 键 |
| 串行分支 | :1743 `concurrency = max(1, ...)` 后裁决一行：quality_mode 为真 → `concurrency = 1` | 受控（值覆盖，不改读取式） |
| payload 预构建段 | :1774-1790（「Pre-compute each batch's payload」:1774；**锚点勘误 E-4**：MF-4 原引 :1019-1028 为纠错管线同构段，翻译管线自身在此） | 受控改点 (f) |
| 消息构建扩展点 | `_build_structured_user_message` :518-563（known-keys 白名单式转发，edit_hint/aligned_main_text 先例） | 受控增行：`finalized_translations` 键转发 |
| 串行循环取消检查 | :1937-1942（循环头 cancel 检查 :1938-1939 在位） | 只读——「串行模式下取消仍约 1s」的既有保障 |
| 消费方 | `_call_batch` :1796（`batch_payloads[batch_idx]`） | 逐批构建的接线点 |

**实施裁决**：

1. **开关读取**：管线内直接 `settings.get("llm_translation_quality_mode", False)`（:1740 settings 已加载），**不增函数形参**——handler（main.py）零改动，开关是全局设置而非调用方选项（与 N4「仅一条 config 布尔键」一致）。
2. **串行派发**：quality_mode → concurrency 有效值 1（轮询池自然退化为逐批）；取消 ~1s 语义不受影响（轮询 wait(1.0) 在位 :1866-1868，串行降级循环 cancel 检查在位 :1938）。
3. **滑动窗 payload（受控改点 (f) 定稿）**：默认关路径——:1774-1790 预构建**原样保留**（逐字节等价的判据面）；开启路径——预构建循环跳过 prompt 组装（仅保留 target_windows/id_map 结构），改在串行派发循环内**逐批构建**：批 N 的 extra_ctx 增 `finalized_translations`（= 批 N-1 定稿译文按源段序列表；**窗口 = 1 批定稿上下文**，PRD R5.8 原文），经 `_build_structured_user_message` 受控增行转发进消息体。补译组合（Q7）：补译请求走同管线，**同受串行开关约束**（全局开关不分新建/补译）；补译批的「上一批定稿译文」= 本轮补译序列内上一批（最简自洽，MF-4 建议）。
4. **「并发 5 与滑动窗互斥」结构结论不变**：布尔二选一，不参数化（N4）；时延约 5× 写入设置文案与 README 标注。
5. **测试（≥2 + PRD 既有）**：关闭路径逐字节等价（payload 逐键比对 mock）；开启时批 2 的 prompt 含批 1 定稿译文（mock 断言 `finalized_translations` 键）；开启时批 1 无该键（窗口边界）；串行 + 取消 1s（复用 M5.5 栅栏法）。**quality_mode × 429 组合路径（SG2-7 附注采纳）**：并发=1 下 429 降级分支仍可达（:1905-1915 判据不排除串行模式），行为冗余无害；用例断言该组合不产生双重 shutdown 副作用（串行循环接管前 shutdown 幂等），(f) hunk 审查按此口径。

**验收**：开关关闭与 v3.0.4 并发行为逐字节等价（既有断言零改动全绿）；开启时批 N+1 payload 含批 N 定稿译文；串行模式取消仍约 1s。

**耦合点**：必须后于 M5.3 合入（M0-4 序 2，:1774-1790 与 :1957-1982 同函数相邻）；(f) hunk 与 (d) 在 record 登记表中分行登记、逐 hunk 审查。

---

## M9: 顺带批（R5.9-R5.16）触点表

| 编号 | 触点（file:line 均实查） | 实施要点 |
|---|---|---|
| R5.9 | Timeline.vue:625（`'Exit edit mode' : 'Edit all subtitles'` 英文 title）；SegmentBlocksLayer.vue:390（`Delete range:` 硬编码 title）；main.py:3002-3005（重译拒绝文案裸语言码）+ `_TRANSLATION_LANGUAGES` :30-40 | tooltip 中文化并轨感知（编辑态/非编辑态两态中文）；覆层 title 按 action×status 中文语义化（与 M5.6 裁决 3 同一 hunk，selected 改用 data-test 选择器，见 M0-3 追认行）；拒绝文案语言码经映射转显示名（`{lang}` → `英文显示名（{lang}）`），后端 1 行 |
| R5.10 | SegmentBlocksLayer.vue:141 visibleEditRanges（**E-6 勘正：rejected 过滤为新增分支**——现状 :147-148 过滤仅 target_type 与视窗、无 rejected 逻辑，:381 注释自证「NOT filtered」；改动性质 = 只增）；WaveformEditor.vue:1243-1251（建段 toggle 亮灯 :1245/label :1250 与实际门 `buildMode && !rangeMode`（:1367/:1555）不符）；范围气泡区 :1504-1541 | rejected 退场（裁决**隐藏**——与 :359 测试反转一致且视觉噪音归零；**新增** rejected 过滤条件，confirmed/pending 面 golden 锁零触碰）；建段 toggle 显示态改绑实际门（`buildMode && rangeMode` → label「建段（已暂停）」+ 半亮，与 :1367/:1555 同一表达式）；气泡 Esc 关闭 + 点击波形区外消泡（keydown 捕获 + 容器外点检测，两关闭路径） |
| R5.11 | WorkspacePage.vue 审阅 modal :1690-1724（列表渲染；条目已带 track_id 数据源）；useLlmTasks.ts:337→:308-313（reset 先清 pendingCorrections 造成「暂无」假象）；时间码 popover（SuggestionPanel.vue :161-167 注释定位的 M4-3 组件区） | 审阅列表按 `activeListTrackId` 过滤 + 「全部」切换（「全部」= 现状不过滤）；reset 延后至新结果返回（启动时仅清进度/错误，保留旧列表至 task:completed/failed）；时间码 mm:ss.s 解析兼容纯秒 + 「取播放头」按钮 + clamp 回显 + 成功 toast |
| R5.12 | core/llm_prompts.py:51（`_SUBTITLE_CORRECTION_SYSTEM_A`） | 末尾增一句「aligned_main_text 为主轨参考稿，仅用于校对译文，勿照抄」（受控增行，注册表键集不变零改动——区间勘正 SG2-4：DEFAULT_PROMPTS 实跨 :157-194；键集类测试如受影响按 3.0.4 §4.1 追认制登记） |
| R5.13 | AIAssistantPanel.vue:223-227（`estimatedTranslationBatches` ceil(N/30)）+ :829-832（data-test="translation-batches" 显示点）+ :954 | SG-5 落地：估算式改按后端同式字符累计切批近似（llm_service.py:1753-1769 target_windows 口径，批窗 30 + 字符预算 4000 前端同式模拟），token ≈ Σ批字符 × 经验比（0.75，标注「约」）；显示「约 N 批 · 约 X 万 token」随主轨段数动态刷新；:301 断言改写入白名单（M0-3） |
| R5.14 | main.py:3002-3005（拒绝文案已有「可清空或删除该轨后重试」）；前端翻译卡错误显示（useLlmTasks errorMsg → AIAssistantPanel 错误区 :470-472） | **裁决 = 方案 B（文案指引）**：不新增选择器入口（useListTrackSelector 改动面大、语义重）；**SG2-6 裁决 = 渲染层拼接**：AIAssistantPanel 错误区 :470-472 按 error 含「同语言翻译轨已存在」子串条件拼接指引「（波形区右键该轨 → 清空轨道/删除轨道）」，**不在** useLlmTasks.ts:239 数据层拼（防污染全部任务类型错误显示，与 M5.1 progressMessage 同一渲染侧思路）；与 R5.9 显示名半条同 commit 施工 |
| R5.15 | useWorkspaceActions.ts:504（「字幕已删除」）/:539（「副轨已删除」，级联处 :536-545） | toast 补「已删除 N 段，可 Ctrl+Z 撤销」（单段 N=1；整轨 N = getProject() 该轨 segments 数；级联删除文案附「及其关联数据」说明）；不加确认框（record §7.1 裁决维持） |
| R5.16 | frontend/src/composables/useRowLayout.perf.test.ts（挂载墙钟环境例） | 裁决：改造为确定性计时（注入 clock / 采样次数化断言），移除墙钟阈值；完成后豁免口径退役、门禁按全绿判（PRD §9 决策树缓冲阀：未完成则维持豁免并回池） |

---

## M-gate: 门禁与用例矩阵

### 用例下限定稿（PRD §7.4 复核：后端 28→**30**（SG-2 R5.5 ≥2→≥4，R4 维持）；前端 22→**24**（R2b 定 23：R5.13 估算显示 +1；R4 上修：R5.15 ≥1，SG2-5 采纳）——PRD 回写终值以后端 ≥30 / 前端 ≥24 为准，见附录 B B-5/B-7）

- 后端 ≥30：R5.1 ≥4（取消/失败上报 + status 键 + handler 判据）；R5.2 ≥4（三件套含 SG-1 守恒不变量 + 解析直测）；R5.3 ≥10（降级/全拒/等价/推导/合并/双保险/对账/守恒）；R5.4 ≥6（三态互扰 ×2 + 兼容 + 聚合 + 逐条形状 + undo 三层例）；R5.5 ≥4（1s 断言 + 聚合等价 + SG-2 两交织）；R5.8 ≥2（滑窗 + 关闭等价，+取消 1s 合并计入 R5.5）。
- 前端 ≥24：R5.0 ≥3（duplicate 第三例 + 回滚 ×2）；R5.1 ≥3（中性态/errorMsg 清理/serial 消费）；R5.3 ≥4（对账渲染/定位/一键补译/toast）；R5.4 ≥3（确认文案三态/快照/patch 消费）；R5.6 ≥3（US-05 三要点）；R5.7 ≥4（trim 拦截/lane 三项拦截/退出恢复/主轨 trim 反向断言）；R5.10+R5.11 ≥2（合并计）+ R5.13 1 + R5.15 1（级联删除计数「整轨 N = getProject() 该轨 segments 数」useWorkspaceActions.ts:536-545 有真实断言面，SG2-5；R5.14 文案拼接无断言面，豁免并在此明示）。
- 断言反转白名单行级登记：M0-3 表即终态，随对应 phase 在 record §4 登记（后端 2 行 + 前端 2 例 + 追认制 1 行）。

### 红线检查命令（每 phase 合入前全绿；P5 终检全量复跑；diff 基准恒为 `v3.0.4`）

```bash
# 后端门禁
uv run pytest                                   # ≥833 + 新增全绿
uv run ruff check .                             # 0
# 红线 R0-1：后端 diff 白名单（输出文件集 ⊆ M0-1 六文件表，逐 hunk 对照登记表）
git diff v3.0.4 --name-only -- core/ main.py
# 禁改面必须为空输出：
git diff v3.0.4 --stat -- core/models.py core/events.py core/task_manager.py \
  core/export_service.py pywebvue/ dev.py build.py
# 红线 R0-3：后端断言删改仅限 M0-3 白名单行
git diff v3.0.4 -- tests/ | grep -E '^-[[:space:]]*(assert |self\.assert)'
# 前端门禁
cd frontend && bun run test && bun run build && bun run lint   # ≥840+新增全绿 / build 通过 / 0/0
# 前端断言白名单外零删改（命中行必须全部落在 M0-3 前端两例登记的 expect 行内）
git diff v3.0.4 -- frontend/src | grep -E '^-[[:space:]]*expect\('
# events 双侧（预期零 diff）
git diff v3.0.4 --stat -- core/events.py frontend/src/utils/events.ts
```

### 真机冒烟清单（P5 双平台；沿承 3.0.4 清单 + 研究报告 §8.4 新增，逐条见 PRD §9.3 1-8 项）

千段观测债回填（必填）/ keep invalidated toast + 确认直显 / 批量按钮作用域与文案 / 翻译失败→补译全链（至少一家非 json_mode 提供商）/ 大工程纠错取消 ~1s 手感 / trim 冻结矩阵手感（主轨零变化）/ 时间码三态 / rejected 退场 + 建段降档 + 气泡双关闭。异常走 smoke-fix 先例（合入分支、tag 不动）。

---

## 附录 A: 后端改动登记表模板（照 record-3.0.4 §3 列形态；record 逐 phase 追加，P5 终检逐条核对）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别（只增/受控改点a-f/登记改点） |
|---|---|---|---|---|
| P0 | （无——零改动基线；基线数登记 pytest 833 / vitest 840·839+perf 豁免） | | | |
| … | … | （每条 hunk 一行，摘要含锚点行号与契约要点，格式对照 record-3.0.4 §3 P1-3/P2-4 行样例） | R5.x | （六类枚举之一） |

预填提示：受控改点 (a)-(f) 与 M0-2 表一一对应，无对应 R 编号的 hunk 一律补登记或回退；前端文件同样登记（3.0.4 先例 P2-4/P2-5 行），类别按「受控改点(c)/(b) 前端面/登记改点」。main.py 两处「登记改点」hunk 随 M0-1 main.py 行逐 hunk 登记：R5.3 completion payload 缺口合流（:1317-1331 区 + 返回 dict :1340，MF2-2 补登）与 R5.4 两 expose 透传（:2755-2768/:2771-2778）。

## 附录 B: ★ 对 PRD 的改判回写清单（供 R5 轮 PM 执行；与 PRD 字面冲突处以本文为准）

| ★ | PRD 处 | 改判内容 | 本文落点 |
|---|---|---|---|
| B-1 | §4-N5 / §2 R5.4① | 批量形参 `track_id: str = ""` → `track_id: str | None = None` 三态（None=timeline 级兼容、""=主轨、"全部"=None+文案明示）；否则 PRD 自身验收「主轨视图不动副轨」不可满足 | M5.4 裁决 1/3 |
| B-2 | §9（前端白名单初版为空） | 前端断言反转白名单定稿 = 2 例：AIAssistantPanel.test.ts:301（R5.13/SG-5 文字必然变化）+ SegmentBlocksLayer.test.ts:359-368（:364/:366，R5.10 三态语义同步反转） | M0-3 |
| B-3 | §1.3（预登记 5 例整例反转） | 后端白名单收窄为逐 assert 行：仅 :217 文案改写 + :614 取消断言反转；:216/:219-224/:251-254/:281-284/:526-528 因单批场景=全批失败拒而**零改动** | M0-3 |
| B-4 | （review-log 追记项，非 PRD） | **新勘误 E-4**：MF-4 引 `llm_service.py:1019-1028` 为纠错管线预构建段（analyze_subtitle_correction :939 起），翻译管线自身预构建在 **:1774-1790**；E-3 串行循环精确区间 :1171-1187（原引 :1166-1180） | M0-2 (f) |
| B-5 | §7.4 | R5.5 用例额度 ≥2 → ≥4（SG-2）；前端总额 22→23 | M-gate |
| B-6 | §2 R5.1 边界 | 纠错侧取消 token 上报/中性提示 = **明确本版不做**，维持 §10.2 ② 登记（SPEC 评估的答复） | M5.5 裁决 5 |
| B-7 | §7.4（R4 增） | 前端用例总额 22 → **24**（R2b 终值 23 上修 +1：R5.15 级联删除计数 ≥1，SG2-5；R5.14 文案拼接豁免明示）；后端 ≥30 维持——合并终值 **后端 ≥30 / 前端 ≥24** | M-gate |
| B-8 | §7 规模裁决与各 phase 人日（R4 增） | 10-14 人日 → **13.5-17.5**（P1 4-5.5→6-8.5 / P2 1.5-2→2-2.5 / P4 2-3→3.5-5，P0/P3/P5 维持）；日历 8-12 天 → **11-15 天**（并行假设下）；PLAN 并行假设写成承诺口径并登记序 8 例外 | 头部规模口径注记 / M0-4 序 7/序 8 |
| B-9 | §1.5 白名单 main.py 行（R4 增） | 补登 R5.3 completion payload 缺口合流 hunk（:1317-1331 区 + 返回 dict :1340，登记改点）；「成功路径零改动」表述同步收窄 | M0-1 / M0-2 (e) / M5.3 裁决 4 |
| B-10 | §5 R5.10 行 + §8 风险表「过滤仅动 rejected 分支」（R4 增） | 改「**新增** rejected 过滤条件（现状无此分支，visibleEditRanges :147-148 仅 target_type 与视窗）」，改动性质 = 只增——E-6 勘误 | M0-3 前端例 / M9 R5.10 行 |
| B-11 | §2 R5.3 ④（R4 增，澄清非冲突） | 补一句：对账通知数据源 = completion payload 的 uncovered_ids，按「写侧对账 ∪ 管线缺口」合并口径（MF2-2）——防按 PRD 字面只查写侧对账导致 1/34 场景验收假挂 | M5.3 裁决 4 |

——本文完（R2b 轮架构师定稿 / R4 轮按 R3 意见修订并回写附录 B B-7~B-11；R5 轮 PM 执行 PRD 回写清单后定天数；执行者按 M0-4 顺序约束开工，逐 phase 回填附录 A）

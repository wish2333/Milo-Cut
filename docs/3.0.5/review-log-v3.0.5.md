# v3.0.5 PRD/SPEC/PLAN 多角色评审日志

> 日期：2026-09　形式：五角色接力（PM → 架构师 → 执行者 → 架构师 → PM → 项目经理 → 编排终检）
> 输入：`docs/3.0.5/PRD-v3.0.5.md`（324 行，评审对象）· `研究报告-v3.0.5.md`（§4 候选池 / §7 开放问题）· `用户反馈-A.md` / `用户反馈-B.md`（行为断言证据源）· `docs/3.0.4/review-log-v3.0.4.md`（格式先例）· 代码锚点抽样核实（R5.0-R5.8 各 1-2 关键锚点 + 立项裁决涉及面 + 断言白名单 5 例实查）
> 输出：`PRD-v3.0.5.md` 评审结论（本文件 R2 章节）；后续轮次追加

---

## R2（架构师）：PRD 评审

### 评审结论总览

| 类别 | 数量 | 条目 |
|---|---|---|
| must-fix | 4 | MF-1（R5.4「全部」路径 undo 快照层缺口）/ MF-2（R5.1 取消判据与三处返回点覆盖）/ MF-3（R5.4 聚合 patch 返回形状超集兼容与前端刷新链）/ MF-4（R5.8 受控改点漏登记 + payload 预构建结构冲突） |
| suggest | 6 | SG-1（R5.3 守恒不变量断言）/ SG-2（R5.5 用例额度与状态矩阵）/ SG-3（R5.7 守卫落点轨角色条件）/ SG-4（R5.4 计数与实际接受数偏差）/ SG-5（R5.13 估算式口径）/ SG-6（R5.0 快照回滚 redo 语义） |
| 锚点勘误 | 3 | E-1（R5.1 :1871 覆盖不全，实为三处）/ E-2（R5.6「已上报」实值在 :2986）/ E-3（R5.5 锚区间未含 429 串行降级循环） |

**总体结论**：评审通过。三裁决原样落实、候选池 25 编号登记无缺、Q1-Q8+N1-N5 自洽、锚点抽样核实 30+ 处仅 3 处偏差且均为覆盖面/行号偏窄、无方向性错误；4 条 must-fix 回写 PRD 后（R5 轮 PM 执行）可进 SPEC。

### 立项会裁决落实核对

| 裁决 | PRD 落实处 | 核对结论 |
|---|---|---|
| ① F1 入首项、v3.0.4 不出补丁 | §0.1 首行 / §0.3 做 / §2 R5.0 / §6-Q1 / §11 裁决① | 原样落实。R5.0 需求/边界/验收三段齐备；N3「纯前端分支 + 不补 revision」与代码事实相符（`core/project_service.py:1353-1356` duplicate 返回无 revision；`frontend/src/App.vue:136` legacy 整体替换 `project.value = data`；`frontend/src/types/project.ts:121-127` isProjectPatch 以 revision 存在判真——补 revision 确会误入 patch 通道，N3 理由成立） |
| ② 六主项全量 | §0.3 / §2 R5.1-R5.5 / §3 R5.6 / §4 R5.7-R5.8 / §11 裁决② | 原样落实。R5.0-R5.8 九条均有需求/边界/验收三段；S3/S4/S5 升格与 Q4/Q6/Q7 一致；超期决策树不可让名单含全部六主项 |
| ③ S6 留 3.1.x | §0.1 S6 行 / §0.3 不做 / §6-Q5 / §10.2 / §11 裁决③ | 原样落实。detail JSON 过渡案明确不做；本评审维持该裁决：detail 侧通道与 AnalysisResult 概念语义错位（`core/models.py:185-191` detail 为 str 字段），且 models.py 零改动红线延续 |

**完整性补充核对**：
- 候选池 25 编号：§0.1 登记表与研究报告 §4 逐一对照（F1-F4 / S1-S6 / P1-P7 / D1-D8 = 25）全部覆盖，无缺号；D7 拆分（第三项随 S2 入版、其余维持）与研究报告 §4 D7 处置建议一致。
- Q1-Q8 + N1-N5：§6 表格与 §11 修订记录互相印证，无悬空引用；§0.2 用户反馈逐条裁决表与 §0.1 登记表交叉一致（F5 并入 R5.1、F-A-04 归 R5.3/US-10 等映射无冲突）。
- 顺带批 R5.9-R5.16 独立交付性：逐条可独立交付（各有验收要点与落点文件）；仅两处显式依赖已注明——R5.14 与 R5.9 显示名半条合并施工、R5.16 挂任一前端 phase 且有让位回池口径，不阻塞主项。

### must-fix 逐条

**MF-1 R5.4「全部（track_id=""）」路径的 undo 快照层未定义**
- 问题：R5.4 ③ 只定义主轨 `["segments","analysis"]` / 副轨 `["tracks","analysis"]` 两案；①的 `activeListTrackId ?? ""` 在「全部」视图传 ""，按文面前端只能落回两案之一（大概率主轨两层）。"" 路径是 timeline 级，qualifying 集合天然混含主/副轨结果（`core/correction_service.py:471-483` 过滤不分轨；逐条 accept 按 detail 的 track_id 分流写主轨段或副轨段，`core/correction_service.py:291`）。若用户在全部视图批量接受含副轨建议而快照只捕两层，undo 缺 tracks 层，「undo 一次整体回退」验收必挂。
- 修改建议："" 路径快照层 = `["segments","tracks","analysis"]` 三层并集；SPEC 的作用域定稿表中为三态（主轨/副轨/全部）各配快照层与确认文案。
- 回写 PRD 处：§2 R5.4 需求③（补第三态）。

**MF-2 R5.1 取消判据「error == "Cancelled"」覆盖不全，应事件化**
- 问题：PRD 只锚 `core/llm_service.py:1871`，而翻译管线裸 envelope 取消返回共三处（:1871 轮询主循环 / :1903、:1939 串行降级两路径，见勘误 E-1）；按字面在 handler 做字符串判等需逐一覆盖，且与 TaskManager 既有权威判据形成第三处字符串耦合（`core/task_manager.py:299-301` is_cancelled = RuntimeError 消息判别 or cancel_event.is_set()）。
- 修改建议：handler 侧改 `cancel_event.is_set()` 事件判据（作用域已持有该对象，`main.py:1258-1262` 传参可见），"Cancelled" 字符串仅兜底；不改管线返回形状（详见焦点 5 裁决）。
- 回写 PRD 处：§2 R5.1 需求①判据措辞。

**MF-3 R5.4 聚合 patch 化的返回形状变更未声明超集兼容，前端刷新链未交代**
- 问题：现状 accept_high 返回 `data={"accepted_count","remaining_count"}`（`core/correction_service.py:501`），前端靠 `switch_timeline` 全量刷新消费（`frontend/src/composables/useWorkspaceActions.ts:993-1003`，diffCache 失效在 :998）。④改为返回聚合 patch 后 data 形状变化，PRD 边界只写「默认 "" 路径逐字节等价」与「既有断言零改动」，未声明新旧键并存；且移除 switch_timeline 后审阅面板/diffCache 的刷新驱动从「全量替换」变为「patch 消费」，消费链变化未登记。
- 修改建议：明示 data 纯增 `patch` 键、旧键保留（3.0.4 accept 超集先例，review-log-v3.0.4 #14）；clear 返回 `patch(analysis)` 同口径；SPEC 明确 diffCache 失效与 SuggestionPanel 刷新改由单次 applyProjectPatch 驱动的落点。
- 回写 PRD 处：§2 R5.4 需求④ + 边界。

**MF-4 R5.8 滑动窗与批 payload 预构建结构冲突，受控改点漏登记**
- 问题：翻译管线在派发前预构建全部批 payload（`core/llm_service.py:1019-1028`「Pre-compute each batch's payload」），滑动窗要求批 N+1 的 payload 携带批 N 定稿译文——预构建时批 N 未定稿，payload 构建必须移入串行循环逐批执行，这是对既有代码的结构性「改」，但 §1.6 受控改点五处（a-e）无 R5.8 条目。另 R5.3×R5.8 组合（Q7）下补译批次的「上一批定稿译文」取值未定义。
- 修改建议：§1.6 增 (f) R5.8 动 payload 构建时序（预构建改串行循环内逐批构建，仅质量模式分支；默认关路径预构建原样保留以保证逐字节等价）；SPEC 定稿补译滑动窗语义（建议 = 本轮补译上一批的定稿译文，最简自洽）。
- 回写 PRD 处：§1.6 受控改点清单 + §4 R5.8 边界。

### suggest 逐条

**SG-1** R5.3 部分成功建轨补一条守恒不变量断言：`ledger.uncovered_segment_ids` == 目标 id 集 − 实际建轨 bindings 覆盖 id 集（双向无多无少）。PRD 验收已有「1/34 失败落盘 + 全批拒」，缺该一致性锁（详见焦点 1 裁决，不要求 golden 文件）。回写：§7.4 R5.3 用例注记。

**SG-2** R5.5 用例额度 ≥2 不足：429 串行降级 × 取消交织两序列（转串行后取消立即返回且 pending 不再执行；轮询循环内 429 降级路径）无既有样板可复刻——`tests/test_translation_smoke_fix.py` 仅 4 例（:83/:111/:139/:174，已核实无 429 交织例）。建议 R5.5 额度上修 ≥4，SPEC 给两循环 × 三退出（成功/取消/429 转串行）状态矩阵。回写：§7.4。

**SG-3** R5.7 守卫落点风险：trim 手柄事件定义与转发在共享组件 SegmentBlocksLayer（`frontend/src/components/waveform/SegmentBlocksLayer.vue:60` trim-start/trim-end payload、:373 转发），主/副轨块同组件渲染；守卫必须带轨角色条件，否则误伤主轨（违反矩阵维度 3）。PRD 验收缺「编辑态主轨 trim 仍可用」显式正反断言，建议补入。回写：§4 R5.7 验收。

**SG-4** R5.4 确认文案计数 N（前端按 scope 预计）与后端实际 accepted 数可能不一致（逐条 accept 失败被静默跳过，`core/correction_service.py:484-486`）。建议确认框用前端计数、完成 toast 用返回值 accepted_count 如实展示。回写：§2 R5.4 需求②。

**SG-5** R5.13 估算式未定义：建议「约 N 批」按后端同式字符累计切批近似（`core/llm_service.py:1000-1016` target_windows 口径），token = N × 批均字符比近似，避免与实际批数系统性漂移。回写：§5 R5.13 细案（SPEC 定）。

**SG-6** R5.0 快照回滚 API 的 redo 语义：drop-last 回滚应同步清 redoStack（pushSnapshot 本就清，`frontend/src/composables/useUndoRedo.ts:57`），避免失败回滚后 redo 恢复出假工程态；API 命名 SPEC 定。回写：§2 R5.0 需求注记。

### 5 个焦点问题裁决

**焦点 1（R5.3 部分成功建轨是否需 golden 对拍）——裁决：不需要 golden 文件，用三件套确定性单测锁边界。**
理由：部分成功 = 目标集缩小后的一次正常建轨，建轨与对账链路全部是既有合法路径（`create_translation_track` 的 uncovered 对账经 `main.py:1298-1310` 上报；双语导出缺位段本就无第二行，`core/export_service.py:468-545` 仅 bindings 命中者成双行），新增的只有「失败批 id 并入 uncovered」管道。真正的风险点在守恒口径从全量收窄为已覆盖集（旧口径注释 `core/llm_service.py:1962-1968`「full-output conservation … fails the WHOLE task」），该口径用 mock 输出可精确断言；golden 文件维护脆、收益低。三件套 = 无失败路径逐字节等价（PRD 已列）+ 1/N 失败 mock 断言（PRD 已列）+ 全批失败零写入拒（PRD 已列），另按 SG-1 补守恒不变量断言。

**焦点 2（R5.4 聚合单 patch 的层选择）——裁决：层并集聚合，不做主/副二选一。**
后端把逐条 accept 的应用核心抽为无 patch 内部方法（返回脏层标记），批量循环消化后按实际写入面一次 `_success_patch(segments=?, tracks=?, analysis=...)`，revision 只 +1。代码依据：`core/project_service.py:158-176` `_success_patch(meta=None, **layers)` 层按需直传 ProjectPatch；`core/models.py:410+` ProjectPatch 各层均可选、None 即未触碰；`core/correction_service.py:291` 逐条路径已按 detail 的 track_id 分流写主/副轨。层二选一会迫使「全部」视图拆两次调用、两次 revision，破坏「revision +1」验收；聚合多个 ProjectPatch 拼接不可行（无 merge 语义）。前端 undo 快照三态对应（"" = 三层并集，即 MF-1）。逐条路径既有 patch 返回保持不变。

**焦点 3（R5.5 轮询化与 429 降级退出路径交织是否需专项状态机审阅）——裁决：需要，落 SPEC 状态矩阵，不做独立状态机重构。**
改造面是两循环 × 三退出：as_completed 主循环（`core/llm_service.py:1116-1174`，取消返回 :1125/:1146）+ 429 串行降级循环（:1166-1180，取消返回 :1174，逐批 cancel_event 检查已在位 :1169-1170）× 成功/取消/转串行三退出。翻译侧 1c 的两条教训必须逐条复刻（`core/llm_service.py:1856-1861` 注释原文：双循环都要能退出；shutdown(cancel_futures=True) 后被取消 future 在后续 result() 抛 CancelledError）。验收口径：聚合等价断言锁 corrections_by_index + total_usage + ledger 集合，不锁 list 顺序（as_completed 完成序改轮询排序后 ledger.failed 顺序可能变）。SG-2 补两交织用例。

**焦点 4（trim 矩阵主/副轨不对称的文档表述是否足够）——裁决：矩阵可用但有条件，防归因混淆靠「点名主体 + 一句理由 + 实现不走样」三件事。**
(a) toggle title 与 README 必须显式区分「主轨/副轨」两个主体并给一句不对称理由（主轨是 2.x 基线不可动、副轨是 3.0.x 新增面按新规则），只写「冻结矩阵」四字不够；(b) 守卫落点必须轨角色条件化（SG-3：trim 手柄在共享组件 SegmentBlocksLayer，无脑加守卫会把主轨也冻住，反而制造新的「有时能拖有时不能」）；(c) 补编辑态主轨 trim 可用的正反断言。PRD §6 矩阵 + R5.7 ③ 文档同步已覆盖 (a) 的骨架，措辞 SPEC 落。

**焦点 5（取消判据 "Cancelled" 字符串是否改结构化标记）——裁决：判据结构化，但方案是 handler 侧 `cancel_event.is_set()`，不在管线 envelope 增 `cancelled: true` 键。**
理由：(1) handler 作用域已持有 cancel_event（`main.py:1258-1262` 传参可见），零形状变更即可结构化；(2) TaskManager 的权威判据本就是双通道且事件优先（`core/task_manager.py:295-301`），事件是既有结构化源；(3) envelope 加键需动 `core/llm_service.py` 三处返回（:1871/:1903/:1939）且消除不了 task_manager 的消息判据，「结构化」收益不完整、diff 面反而大。字符串仅作兜底分支保留。对应 MF-2 回写与 E-1 勘误。

### 锚点勘误表

| 编号 | PRD 引用 | 代码事实 | 影响与处理 |
|---|---|---|---|
| E-1 | R5.1 引 `core/llm_service.py:1871`（取消返回裸 envelope，单一锚点） | 翻译管线共三处裸 envelope 取消返回：:1871（轮询主循环）、:1903 与 :1939（429 串行降级两路径） | R5.1 上报须覆盖三点；采纳焦点 5 事件判据后天然全覆盖，无需逐点枚举 |
| E-2 | R5.6 引 `core/project_service.py:2915-2935`（invalidated_count「已上报」） | 计数与日志在 :2915-2933；进入返回值在 :2986（return dict 键） | 实质成立（后端确已返回、`frontend/src/composables/useEdit.ts:184-187` 类型未收即丢弃），行号口径勘误给 SPEC |
| E-3 | R5.5 引 `core/llm_service.py:1116-1128`（with + as_completed） | with 在 :1116、as_completed 在 :1122、取消返回 :1125，区间本身准确；但同函数 429 串行降级循环 :1166-1180（含取消返回 :1174）在区间外 | 改轮询必须两循环同改；PRD 边界已有文字（「429 退出路径同步修正」）但锚点区间偏窄，SPEC 锚表补全 |

**锚点核验汇总**：抽样 30+ 处，其余全部逐字吻合，含：R5.0（WorkspacePage.vue:990-999 / useUndoRedo.ts:48-58 / project_service.py:1353-1356 / App.vue:119-136 / types/project.ts:120-127）；R5.1（main.py:1266-1269 失败 raise 丢 data 属实、llm_service.py:1942 串行信号、useLlmTasks.ts:245-248 task:cancelled 不清 errorMsg、:256-264 只取 percent）；R5.2（llm_service.py:612-634 仅 relevance/action 两模式）；R5.3（AIAssistantPanel.vue:465 join 内部 id、main.py:2996-3003 同语言拒绝 + _TRANSLATION_LANGUAGES:30）；R5.4（correction_service.py:446/504、useWorkspaceActions.ts:993-1003 无快照）；R5.5（test_translation_smoke_fix.py:139 样板在）；R5.6（SuggestionPanel.vue:154-159/:496 hover title）；R5.7（SegmentBlocksLayer.vue:249-289 守卫先例）；R5.9-R5.11（Timeline.vue:625 英文 tooltip、SegmentBlocksLayer.vue:378-393「Delete range」硬编码 + rejected 不过滤注释、WaveformEditor.vue:1243-1251 建段亮灯与 :1367/:1555 `buildMode && !rangeMode` 实际门不符、useLlmTasks.ts:337→:308-313 reset 先清）。**断言反转白名单 5 例实查全部存在且行号精确命中**（test_llm_translation.py :192/:226/:256/:518/:564），其固化旧语义的事实（全任务 fail 口径注释 llm_service.py:1962-1968、取消裸 envelope :1871）支持反转理由，预登记真实必要。

### 规模复核意见

量级认可（10-14 人日 / 日历 8-12 天），附两个条件。架构师逐项视角：R5.0 0.5 / R5.1 1-1.5 / R5.2 0.5-1 / R5.3 2-3 / R5.4 1.5-2 / R5.5 1-1.5（含 SG-2 加例）/ R5.6 0.5-1 / R5.7 1-1.5 / R5.8 1-1.5（含 MF-4 结构改动）/ 顺带批 R5.9-R5.16 合计 1.5-2 / 新增测试 ≥50 例 1.5-2 / P0+P5 1.5-2，合计约 12.5-17 人日——PRD 上限 14 偏乐观但在下述前提下成立：(1) 顺带批与 P1-P3 并行开发是日历 8-12 天的显式前提，建议 PLAN 把并行假设写成承诺口径的一部分（单人串行备份口径 14-17 人日 / 12-16 天）；(2) MF-4 若在 SPEC 阶段判定 R5.8 滑动窗实现成本超 1.5 人日，优先触发超期决策树首位让位（PRD 已预置）。精确复核归 R3 执行者。

### 留给 R3 执行者的核对重点

1. 基线数实跑核对：pytest ≥833 / vitest collected ≥840 passed ≥839 的当前真实值（本轮只核锚点未跑测试）。
2. 五例断言反转登记到 assert 行粒度：本轮核到测试函数定义行（:192/:226/:256/:518/:564），SPEC/record 反转清单须逐 assert 行登记，并确认 ledger 相关断言（failed 批记录）保留而非删除。
3. MF-1/MF-2/MF-3/MF-4 回写后的 SPEC 对应表：M0 白名单终态 6 文件复核 + 受控改点增 (f) R5.8 后共 6 处的逐 hunk 审查口径。
4. R5.5 两循环 × 三退出状态矩阵与聚合等价断言口径（corrections_by_index + total_usage + ledger 集合等价，不锁 list 顺序）；correction_service.py:1166-1180 串行循环的取消检查保持。
5. R5.3 缺口推导配对判定式 SPEC 定稿建议：以 bindings 的 main_segment_id 集合为覆盖口径（不考察 extension 侧存活），并按 SG-1 补守恒不变量断言；补译 mock 断言请求 id 集恰为缺口集。
6. R5.7 守卫落点的轨角色条件核实（SegmentBlocksLayer 共享组件内主/副轨块的区分字段）+ 编辑态主轨 trim 可用正反断言入用例矩阵。

---

## R3（代码执行者）：SPEC 逐触点核验

> 日期：2026-09　角色：代码执行者（R3 轮）　对象：`spec-v3.0.5.md`（407 行）逐触点核验
> 方式：对 M0 契约与 M5.0-M5.8 每主项触点表逐条打开代码核实（锚点行号 / 行内容 / 改动性质三对账），抽样密度对齐 3.0.4 R3 先例（每主项 4-8 处，合计 58 处）；基线数实跑；断言反转白名单核到 assert 行粒度。本轮不改 SPEC/PRD/代码与测试，结论供 R4 架构师修订。
> 工作区 = v3.0.4 发布态（pyproject `version = "3.0.4"`，HEAD b21c451），与 SPEC 第 5 行声明一致。

### 核验总览

| 项 | 结果 |
|---|---|
| 锚点抽查 | 逐行核对 58 处：命中 55 / 偏差 3（94.8%；3.0.4 先例为 92%） |
| 优先复核 | R2a 勘误 E-1/E-2/E-3 全部核实成立；R2b 新勘误 E-4（(f) 锚点 :1774-1790）核实成立（详见明细） |
| 断言反转白名单 | 后端 2 行（:217 改写 / :614 反转）+ 前端 2 例（AIAssistantPanel.test.ts:301 / SegmentBlocksLayer.test.ts:364/:366）+ 追认制 1 行，assert 行粒度全部命中，反转理由成立且无更小改法 |
| 基线数实跑 | `uv run pytest --collect-only -q` 汇总 = **833**；`cd frontend && ./node_modules/.bin/vitest list \| wc -l` = **840**——与 SPEC 头部及附录 A 声称一致。口径注记：pyproject.toml:59-60 `addopts = "--ignore=tests/integration -q"` 使 -q 输出无总数行，后端总数由每文件计数 awk 求和得 833；passed 数未在本轮实跑，沿 R2b 实跑声明（839 + useRowLayout.perf 豁免 1） |
| must-fix | 2 条（MF2-1 纠错串行记账判据陷阱 / MF2-2 部分成功缺口断链 + 白名单 hunk 漏登记） |
| suggest | 6 条（SG2-1…SG2-6） |
| 天数复核 | **13.5-17.5 人日**（PRD 10-14 上修；低估段 = P1 与 P4，无显著高估段）；日历建议 11-15 天 |
| 顺序约束 | 新增 2 条（序 7 payload 合流先行消费端 / 序 8 R5.11 开发基线须含 M5.4） |

R2a「留给 R3 执行者的核对重点」6 条逐条闭合：①基线数已实跑（见上）；②断言反转已核到 assert 行，ledger 断言（:221-224/:254/:284/:528）确认保留而非删除；③M0 白名单终态 6 文件 + 受控改点 (a)-(f) 六处逐 hunk 审查口径成立（MF-4 已落 (f)）；④R5.5 状态矩阵与聚合等价口径成立，但发现记账判据陷阱（MF2-1 补充）；⑤R5.3 覆盖口径与 `track_{track_id}_seg_{start:.3f}` 命名空间（project_service.py:745-746）一致，SG-1 已入 M-gate；⑥R5.7 轨角色条件成立——TrackLane 即轨角色边界、SegmentBlock 的 globalEditMode 声明未消费 trim 门（SegmentBlock.vue:38/:63 仅声明，拖拽使能仅看 :162 updateTime），正反断言已入 M-gate。

### 锚点核验明细（锚点 → 判定）

**M0 契约（白名单 / 受控改点 / 事件）**

| 锚点 | 判定 |
|---|---|
| llm_service.py:1740-1744 管线设置读取（:1740 load_settings，:1741-1744 四键） | 命中 |
| llm_service.py:1753-1769 target_windows（批窗 30 + 字符预算 4000，R5.13 同式依据） | 命中 |
| llm_service.py:1774-1790 预构建段（「Pre-compute each batch's payload」:1774；:1790 收尾） | 命中——**E-4 成立** |
| llm_service.py:1017-1033 纠错管线预构建（analyze_subtitle_correction :939 起；MF-4 原引 :1019-1028 落于其中） | 命中——E-4 的「同构段」判断属实 |
| llm_service.py:1796 `_call_batch` 消费 `batch_payloads[batch_idx]` | 命中 |
| llm_service.py:1116 / :1122 / :1125 / :1146 / :1148-1157（纠错外层 with/as_completed/取消两返回/429 break） | 命中 |
| llm_service.py:1171-1187 串行降级循环（:1173 cancel 检查 / :1174 返回 / :1177 "(serial)"） | 命中——**E-3 补全区间成立**（原 :1166-1180 确偏） |
| llm_service.py:1848-1856 / :1857-1862 / :1865-1871 / :1873-1876 / :1930-1934（翻译侧轮询样板与 finally） | 命中（:1856 `_CANCEL_POLL_SECONDS = 1.0`） |
| llm_service.py:1871 / :1903 / :1939 翻译管线三处裸 envelope 取消返回 | 命中——**E-1 三处全数核实** |
| llm_service.py:1957-1962 uncovered 推导 / :1964-1982 全量守恒 fail（:1973-1977 英文 error / :1978-1982 data 带 ledger+token_usage）/ :1984-1993 合并序 | 命中（受控改点 (d) 区间与「失败 data 已在、handler 丢弃」判断相符，main.py:1266-1269 属实） |
| llm_service.py:518-563 `_build_structured_user_message`（edit_hint :551-553 / aligned_main_text :555-557 转发先例） | 命中 |
| llm_service.py:565 起 `_parse_json_response_layers`；:612-634 第 4 层（relevance :615-623 → action :626-634） | 命中（注意 :636 起还有 Layer 5 sanitize，新模式须插在 :634 与 :636 之间，M5.2「末尾追加」可行） |
| llm_service.py:1614 `_validate_translation_coverage`；:1814-1821 调用点 | 命中 |
| llm_service.py:1066-1090 纠错输出消费（segment_id/corrected_text/…，无 translated_text） | 命中（M5.2「无副作用」结论成立） |
| correction_service.py:446-502（qualifying :471-474 现状不分轨 / 逐条 :484-487 / 静默跳过 :486-487 / 返回 :499-502）；:504-532（:519 / :520-521 / :523-526 / :532 走 `_update_timeline_by_id`）；:291 scope_track_id；:296-301 副轨写回 | 全部命中（受控改点 (b) 区间与性质标注准确） |
| project_service.py:158-176 `_success_patch(meta=None, **layers)`；:716 create_translation_track；:1346-1356 duplicate 幂等（:1353-1356 返回无 revision）；:2915-2935 invalidated 计数与日志；:2986 进入返回值 | 全部命中——**E-2 成立**（:2986 精确） |
| main.py:30-40 `_TRANSLATION_LANGUAGES`；:1258-1264 cancel_event 作用域（:1261 传参）；:1266-1269 失败分支；:1286-1299 items 组装；:1317-1331 完成上报（:1326 written_count / :1328 uncovered_ids）；:2754-2768 / :2770-2778 两 expose 薄透传；:2996-3006 同语言校验；:3002-3005 裸语言码 | 全部命中 |
| config.py:82（DEFAULTS LLM 区块，追加位可行）；llm_prompts.py:51 `_SUBTITLE_CORRECTION_SYSTEM_A` | 命中 |
| events.py:29 / events.ts:19 `llm:token_usage` 双侧已在；events.py:28 / events.ts:18 `llm:analysis_failed` 双侧已在 | 命中（零新增事件预期成立） |

**M5.0（duplicate 防呆）**

| 锚点 | 判定 |
|---|---|
| WorkspacePage.vue:990-999（pushSnapshot :992 → call :993 → emit :994-995 / toast :996-997） | 命中 |
| useUndoRedo.ts:48-58（undoStack 追加 :56、redoStack 清空 :57） | 命中（popSnapshot 纯新增可行；SG-6 不触碰 redoStack 的不变量与 :57 相符） |
| types/project.ts:120-127 isProjectPatch；App.vue:119-136（legacy 整体替换 :134） | 命中（N3 理由代码事实成立） |
| WorkspacePage.rangeDecision.test.ts describe :270、既有 2 例 :271/:321 | 命中（第三例宿主可行） |
| **App.vue:165-167「注入链注释即证」** | **偏差（勘误 E-5）**：App.vue:165-167 实为窗口拖拽 handler（handleWindowDragEnter/Over）。双入口共用 handleRangeDecision 的事实成立，真实证据 = WorkspacePage.vue:958 `provide("suggestion:add-range-decision", …)` 与 :1619 `@range-decision="handleRangeDecision"`，及 SuggestionPanel.vue:161-169 注释（:165 明言 SAME handler） |

**M5.1（翻译失败/取消成本可见）**

| 锚点 | 判定 |
|---|---|
| task_manager.py:299-301 双通道判据（RuntimeError 消息 or cancel_event） | 命中 |
| useLlmAnalysis.ts:5-9（TokenUsagePayload 无 status 键）/ :30-43 累计消费 | 命中（status 纯增键向后兼容成立；lastUsage 单例可为取消文案供数） |
| WorkspacePage.vue:604-616 EVENT_TASK_CANCELLED 分支现状不含 llm_translation | 命中（:608-611 仅 smart_delete/subtitle_correction/highlight/semantic_search） |
| useLlmTasks.ts:245-248（task:cancelled 只复位不清 errorMsg）/ :256-264（progress 只取 percent） | 命中（两处补法可行；全局影响面见 SG2-2） |
| test_translation_smoke_fix.py:169 `error == "Cancelled"` 断言 | 命中——M5.1 裁决 1「error 串不变故零改动」判定成立 |

**M5.2（行级解析兜底）**：解析层四处（上表 M0 区）+ test_llm_phase4b.py:68-130 既有 relevance/action 用例区命中；中文文案落点 :1973-1977 命中。警告文案子串（"missing ids"/"unknown ids"/"duplicate ids"）产生于 coverage 校验与 `_call_batch`（:1818-1820），不在 (d) 重构区 :1957-1982 内，:220/:253/:283 警告断言零改动判定成立。

**M5.3（补译 + 对账可读化）**

| 锚点 | 判定 |
|---|---|
| main.py:2996-3006 校验段改判路由 / :3008-3015 payload 字面量增键位 | 命中（MVP 键增可行） |
| WorkspacePage.vue:1046-1061（pushSnapshot ["tracks","bindings"] :1051 / 语言记忆 :1057-1059 仅 started 后写回）；completion watcher :1069-1087（notice :1072-1077） | 命中 |
| useLlmTasks.ts:181-190 lastTranslationCompletion（uncovered_ids :188） | 命中 |
| AIAssistantPanel.vue:455-467（:465 裸 join）；mainSegments :219（:49 声明，:46-48 注释，语义命中） | 命中（:48 记 1 行微偏，不计偏差） |
| export_service.py 缺位段单行先例 / project_service.py:716+ create 契约 1-5 | 命中（merge 与 create 重复度评估见 SG2-3） |
| **缺口可见性链路** | **偏差（升格 must-fix MF2-2）**：completion payload 的 uncovered_ids 只取写侧对账 report（main.py:1328），管线侧 ledger.uncovered_segment_ids（llm_service.py:1962）未入事件；1/34 场景下写侧 uncovered 为空 → WorkspacePage.vue:1072 notice 不触发，对账可读化与一键补译无入口 |

**M5.4（批量审阅收口）**：correction_service 四处（见 M0 区）+ project_service.py:158-176 + main.py 两 expose + useWorkspaceActions.ts:69-73（:72 两层案）/ :976-980（reject 先例）/ :993-1003（:998 diffCache / :999-1000 switch_timeline，现状无快照属实）/ :1005-1014（:1006 window.confirm）+ WorkspacePage.vue:1692-1707（:1698 / :1703）全部命中；models.py ProjectPatch 层可选结构与 `_success_patch` 直传可行性成立。三态 `str | None` 经 pywebview null→None 可行。

**M5.5（纠错取消轮询化）**：双循环八锚（见 M0 区）+ test_translation_smoke_fix.py（TestResolvedLlmConfig :82 / TestCancelLatency :138 / 栅栏样板 :139-172 / happy path :174-188）全部命中；「该文件仅 4 例、无 429×取消交织」证实（全文件 188 行 4 用例）。**但**串行循环记账判据存在跨管线差异，照抄翻译侧形态会破坏聚合等价（MF2-1）。

**M5.6（keep 可感知收口）**

| 锚点 | 判定 |
|---|---|
| SuggestionPanel.vue:154-159 confirmTitle（manual 专用）/ :496 `:title` 绑定 | 命中（内联小字落点 :492-500 按钮容器可行） |
| useEdit.ts:181-202（返回类型 :181-185 / call 泛型 :186-191 / 返回对象 :195-199 均无 invalidated_count） | 命中（后端 :2986 已上报、类型补收可行；注意后端该返回为 legacy 全量 dump 含 project :2987，非 patch） |
| SegmentBlocksLayer.vue:390 硬编码 title / :377-381 三态注释（:381「rejected is NOT filtered」）；:141 visibleEditRanges / :171 editRangeClasses / :166-169 类常量 | 命中（golden 锁面判断成立） |
| ExportPage.vue:415-416 confirmedEdits 计数行 | 命中 |
| SegmentBlocksLayer.test.ts:287-381 三态 describe（:289-290 快照常量 / :292-294 findOverlays / :311 全等断言 / keep golden 2 例 = :331-344 与 :346-357） | 命中（M0-4 序 6「golden 先行」对象存在且可执行） |

**M5.7（trim 冻结矩阵）**

| 锚点 | 判定 |
|---|---|
| TrackLane.vue:15-18 docstring / :24 updateTime prop / :29-37 emits / :77-81 openBlockMenu / :84-91 openLaneMenu / :187-205 三结构项（:190/:196/:202） | 全部命中（组件边界即轨角色，守卫主落点成立；无 globalEditMode prop 属实） |
| SegmentBlock.vue:34-35 / :38/:63（globalEditMode 声明未消费）/ :162（拖拽使能仅看 updateTime）/ :251-262 trim 手柄（pointer-events:none 视觉件，真手势在边缘拖拽） | 命中（`:update-time="globalEditMode ? undefined : updateTime"` 门机制可行） |
| WaveformRow.vue:306-335（层实例 :312 / global-edit-mode :318 / toast 转发 :331 / trim 转发 :332）/ :339-359（TrackLane 实例，:350 update-time） | 命中 |
| WaveformEditor.vue:1470-1487 基础直挂层 / :1545-1562 基础 TrackLane（:1550-1554）/ 双 toggle :1243-1251（title :1247）与 :1252-1261（title :1257）/ :1367 与 :1555 `buildMode && !rangeMode` | 全部命中（两父均已持有 globalEditMode，透传可行；toast 链 WaveformEditor 侧 :1485 先例在） |

**M5.8（质量模式开关）**：config.py:82 / llm_service.py:1740-1744 / :1743 / :1774-1790 / :1796 / :518-563 / :1937-1942 全部命中（见 M0 区）；「轮询池 concurrency=1 自然退化串行、取消 ~1s 不受影响」与 :1865-1868 wait(1.0) 相符。quality_mode 下 429 降级循环冗余触发问题见 SG2 补充（天数表后）。

**M9 顺带批抽查**：Timeline.vue:625 英文 title 命中；useRowLayout.perf.test.ts 存在命中；WorkspacePage 审阅区 :1690-1724 与 track_id 数据源注释 :149 区命中；useWorkspaceActions.ts:504/:539/:536-545 删除 toast 命中。**1 处偏差（勘误 E-6）**：R5.10 行「SegmentBlocksLayer.vue:141 visibleEditRanges（rejected 过滤分支）」——现状 :147-148 过滤仅 target_type 与视窗，**无 rejected 分支**（:381 注释明示现状不过滤），R5.10 实施为「新增 rejected 过滤条件」，红线措辞应从「过滤仅动 rejected 分支」改为「仅新增 rejected 过滤条件，confirmed/pending 面 golden 锁零触碰」。

### 断言反转白名单核验（assert 行粒度）

| 白名单行 | 代码事实 | 反转理由与更小改法核查 |
|---|---|---|
| test_llm_translation.py:217 | `assert "uncovered" in result["error"]`（:192 函数内） | 改写成立：M5.2/M5.3 文案 (i) 为中文且含「补译」，:217 字面子串断言必挂；无更小改法（保留英文 "uncovered" 子串与中文文案要求互斥）。同函数 :216/:219-223 零改动判定成立 |
| test_llm_translation.py:224 | `assert ledger["uncovered_segment_ids"] == ["seg-000","seg-001","seg-002"]` | 保留成立：`_segments(3)` 默认批窗 30 → total_batches=1，单批全失败时 uncovered = 全部目标 id，R5.3 改判后值不变（语义转「缺口集」）；ledger failed 断言 :222 同保 |
| test_llm_translation.py:216/:219-223、:251-254、:281-284、:526-528 | 四姊妹例均为 `_segments(2)/(3)` 单批任务（:194/:228/:258/:514 无批窗键 → batch_size 30） | 预登记撤销（★B-4）成立：单批 = 全批失败拒，`success is False` 语义未被 R5.3 触碰；警告子串断言 :220/:253/:283 的产生点（coverage 校验 + `_call_batch` :1818-1820）在 (d) 重构区外，不受影响 |
| test_llm_translation.py:614 | `assert result_holder == {"success": False, "error": "Cancelled"}`（:564 函数；docstring :565-567 同述裸 envelope） | 反转成立：R5.1 取消返回附 `data`（:1871/:1903/:1939 三处）与 dict 全等断言正面冲突；更小改法不存在——不附 data 则取消 token 上报（PRD R5.1①）落空。:608/:612 两断言保留，登记口径与 SPEC 一致 |
| AIAssistantPanel.test.ts:301 | `expect(...).toBe("约 42 批")`（:299 函数名 estimates the batch count…） | 改写成立：R5.13 显示文本改「约 N 批 · 约 X 万 token」，字面断言必挂；属文字必然变化，非语义反转 |
| SegmentBlocksLayer.test.ts:364、:366 | :364 `toHaveLength(1)` + :366 类串全等 `toBe(V303_CONFIRMED_DELETE_CLASS)`（:359 函数名 rejected…unfiltered） | 反转成立：R5.10 裁决「隐藏」使 :364 翻转为 0、:366 随例删除；若改选极淡描边则仅 :366 变——两案都与现状断言冲突，无更小改法。:292-294 findOverlays 选择器为非 expect 行（追认制登记口径正确） |
| （复核项）test_translation_smoke_fix.py:169 | `assert result["error"] == "Cancelled"` | 零改动判定成立：R5.1 保持 error 串不变、仅增 data 键 |

**结论**：白名单终态 5 例（后端 2 行 + 前端 2 例）+ 追认制 1 行全部到 assert 行核实，反转/改写理由成立且均已确认无更小改法；M0-3 表可作为门禁 R0-3 与前端 expect-grep 的终态依据。前端 expect 删除行合计 3 行（:301/:364/:366）落于登记 2 例内，口径自洽。

### must-fix

**MF2-1 R5.5 轮询化照抄翻译侧记账会破坏聚合等价（串行循环判据差异未点名）**
- 证据：纠错管线外层循环记账是 error 判据（llm_service.py:1135-1142，`error is None` 记成功），串行循环却是 not-corrections 判据（:1182-1185，`not corrections` 记失败），而 `_call_batch` 解析失败返回 `error=None` 且 corrections 为空（:1054-1056 `return (batch_idx, [], usage, None)`）。翻译侧串行循环是 error 判据（:1947-1953）。M5.5 裁决 1 要求「逐行复刻翻译侧形态」，若连串行记账一并复刻，则串行降级下的 parse-None 批从 failed 改记 succeeded → ledger 集合变化 → 「聚合等价断言锁 ledger 集合」验收必挂。
- 修改建议：M5.5 裁决 1 补一句——「串行循环记账保持 :1182-1185 现状 not-corrections 判据，不复刻翻译侧 :1947-1953」；record 登记该既有不对称（外层/串行判据不同构是 v3.0.4 现状事实，本轮只保等价、不顺手修复），并在聚合等价断言注记中点名「串行 × parse 失败」组合为锁面。
- 回写处：SPEC M5.5 裁决 1 + 验收注记。

**MF2-2 R5.3 部分成功场景缺口断链：管线缺口不进 completion 事件，US-10 无入口；且该 hunk 未入白名单**
- 证据：R5.3 把失败批 id 并入 `ledger.uncovered_segment_ids`（llm_service.py:1957-1962），但 completion 事件 payload 的 uncovered_ids 只取写侧对账 report（main.py:1317-1331，键值源 :1328 `report.get("uncovered_ids", [])`；create_translation_track 的对账只对 items 与当前主轨）。1/34 场景下 33 批 items 全部命中主轨 → 写侧 uncovered 为空 → WorkspacePage.vue:1072 `uncovered_ids.length > 0` 不成立 → translationNotice 不触发 → AIAssistantPanel.vue:449-467 对账清单与一键补译无渲染入口，R5.3 验收首条「缺口对账可见可读可一键补译」必挂。同时 M0-1 main.py 行只登记 :1266-1269 / :2996-3006 / :2755-2778 / :3002-3005，**未含 completion payload 组装 hunk（:1317-1331 区）**，改动将触白名单红线。
- 修改建议：M5.3 增一条裁决——handler 部分成功分支的 uncovered_ids 取「写侧对账 ∪ result.data.ledger.uncovered_segment_ids」去重并集（返回 dict :1340 同步），登记入 M0-1 main.py 行 R5.3 条目与受控改点 (e) 邻域；「本次补译 N 段」与 gap 推导口径不受影响（差集推导天然涵盖失败批）。
- 回写处：SPEC M5.3 裁决 3/7 之间 + M0-1 表 main.py 行 + 附录 A 预填提示。

### suggest

**SG2-1** M5.3 裁决 6 的 `pendingResumable` 页面标记无失败清理路径：补译启动后任务失败/取消时 completion 不触发，标记残留；用户随后发起任一新建翻译，完成时 watcher 命中残留标记将误报「本次补译 N 段」。建议 completion.track_id 与标记 trackId 比对命中才 toast 并清（新建轨 id 天然不匹配），或在 task:failed/cancelled 分支清标记。回写：M5.3 裁决 6。

**SG2-2** useLlmTasks.ts:245-248 task:cancelled 监听无 task_type 过滤，补 `errorMsg.value = null` 将同时作用于全部任务类型的取消路径（行为面宽于「翻译取消」；方向良性——各类取消残留一并消除）。建议补 task_type 判据或在 record 登记行为面变化，并确认无既有断言锁「取消后保留 errorMsg」。回写：M5.1 裁决 2。

**SG2-3** merge_translation_track 与 create_translation_track（project_service.py:716 起，契约 1/3/4/5：pinning、命名空间 :745-746、bind offset=0、单 patch）约七成同构，差异仅免语言拒绝、对账改撞配拒绝。建议抽共享私有 helper 或在 merge 内复用既有内部段，把 project_service 白名单 hunk 控制在「单一 hunk、零删改」承诺内，防 hunk 膨胀触红线审查争议。回写：M5.3 裁决 4。

**SG2-4** llm_prompts.py 注册表区间微勘误：DEFAULT_PROMPTS 实跨 :157-190（translation 项 :186-189），SPEC 引「:157-184 零改动」区间略窄；「键集不变」结论不受影响。回写：M0-1 llm_prompts.py 行。

**SG2-5** M-gate 前端 ≥23 未给 R5.15 额度：级联删除计数「整轨 N = getProject() 该轨 segments 数」（useWorkspaceActions.ts:536-545）有真实逻辑值得 ≥1 例；若维持不给，建议明示豁免理由。R5.14 文案拼接无断言面，可不设额度。回写：M-gate 前端行。

**SG2-6** R5.14 指引拼接落点：若在 errorMsg 数据层（useLlmTasks.ts:239）拼接会污染全部任务类型错误显示；建议在渲染层（AIAssistantPanel.vue:470-472 错误区）按 error 含「同语言翻译轨已存在」子串条件拼接，与 M5.1 progressMessage 同一渲染侧思路。回写：M9 R5.14 行。

**SG2-7（附注，不计条目）** M5.8 quality_mode（并发=1）下 429 降级循环逻辑仍会计数并可能进入串行分支（llm_service.py:1905-1915 判据不排除串行模式），行为冗余无害，但 (f) hunk 审查与用例设计应确认该组合路径不产生双重 shutdown 副作用，可在 M5.8 裁决 5 补一句用例覆盖说明。

### 天数复核（逐触点口径）

| Phase | PRD 估计 | R3 复核 | 逐项依据 |
|---|---|---|---|
| P0 | 0.5 | 0.5 | 基线数本轮已代跑（833/840），登记即可；准确 |
| P1 | 4-5.5 | **6-8.5** | M5.0 0.5（三分支 + popSnapshot + 1 例）；M5.1 1-1.5（三处返回 + handler 判据 + 前端三处 + 4 例）；M5.2 0.5-1（正则模式 + 两文案 + 4 例）；M5.3 2.5-3.5（(d) 改判 + merge 方法 + 路由 + MF2-2 合流 + 对账渲染改造 + ≥10 例）；M5.8 1-1.5（(f) 预构建改逐批 + 滑窗转发 + ≥4 验证面）；R5.13 0.5（前端同式估算 + 1 例）。M5.3+M5.8 同函数族一次改透的串行调试成本与 R5.3 用例体量被低估 |
| P2 | 1.5-2 | **2-2.5** | 逐条应用核心抽内部方法 + 聚合 patch + 三态形参 + 前端消费链重写（移除 switch_timeline 改 patch 驱动）+ ≥6 例含 undo 三层例 |
| P3 | 1-1.5 | 1-1.5 | 样板复刻成熟（:139-172 栅栏法在）；MF2-1 判据冻结是注意点非增量；SG-2 两交织例已计入 |
| P4 | 2-3 | **3.5-5** | M5.6 0.5-1 / M5.7 1-1.5（守卫两父透传 + toast 链 + 反向断言 + 双文档面）/ 顺带批 R5.9-R5.12/R5.14/R5.15/R5.16 1.5-2 / **D4 四项测试轮 0.5-1 被「不占产品主题」表述隐藏人日**（detect_silence 本体与端到端串测是真实工作量） |
| P5 | 1-1.5 | 1-1.5 | 门禁终检 + 真机清单 + README 回填；准确 |

**总区间：13.5-17.5 人日**（两端不同时取上界；PRD 10-14 上修，低估段 = P1 的 M5.3/M5.8 与 P4 的 D4+顺带批，无显著高估段）。与 R2a 架构师复核 12.5-17 人日互证，落于其上缘。**日历建议**：单人串行 15-19 天；维持「顺带批与 P1-P3 并行开发」假设可压至 **11-15 天**，建议 R5 轮 PM 重报日历 11-15 天，并把下节序 8（R5.11 开发基线须含 M5.4）作为并行假设的显式例外写入 PLAN；超期决策树让位顺序（R5.8 首让位）维持不变。

### 顺序约束新增（续 M0-4 编号）

7. **M5.3 内部序（MF2-2 派生）**：completion payload 缺口合流 hunk（main.py:1317-1331 区）必须先于或同 commit 于本项对账渲染消费端改造（AIAssistantPanel :455-467 / WorkspacePage watcher :1069-1087）与 R5.11 的 reset 延后改造——三者消费同一 lastTranslationCompletion 结构，先定数据形状后改消费端，防中间态假绿。
8. **R5.11（P4）与 M5.4（P2）同文件族例外**：R5.11 与 M5.4 都落 useWorkspaceActions.ts（handleAcceptHighConfidence/handleClearCorrections）与 pendingCorrections 消费面。P4∥P1-P3 并行开发假设在此收窄：R5.11 的开发基线必须包含 M5.4 的该文件改造，禁止在未含 M5.4 的分支上并行开发（P4 并行窗口的唯一显式例外点，PLAN 应登记）。

### 留给 R4 架构师的修订清单

1. **E-5 回写**：M5.0 裁决 4 锚点勘正——「App.vue :165-167 注释即证」改为「WorkspacePage.vue:958 provide / :1619 绑定 + SuggestionPanel.vue:161-169 注释」（事实不变，证据错置）。
2. **MF2-2 落地**：M5.3 增缺口合流裁决 + M0-1 main.py 行补 R5.3 completion hunk 登记 + 附录 A 预填提示同步。
3. **MF2-1 落地**：M5.5 裁决 1 补串行记账判据冻结句 + 验收注记点名「串行 × parse 失败」锁面。
4. **E-6 回写**：M9 R5.10 行措辞勘正（「新增 rejected 过滤条件」），并同步 M0-3 :359-368 整例反转描述（现状锁定断言 :364/:366 与新增过滤的对应关系）。
5. **SG2-1/SG2-2/SG2-6 措辞吸收**：M5.3 裁决 6 补标记清理路径；M5.1 裁决 2 补 task_type 判据或登记口径；M9 R5.14 行改渲染层拼接。
6. **SG2-3**：M5.3 裁决 4 补「复用 create 内部段 / 抽共享 helper，维持单一 hunk」的实施约束。
7. **SG2-4/SG2-5 勘正**：M0-1 llm_prompts 区间 :157-190；M-gate 前端行补 R5.15 额度 ≥1 或豁免注记。
8. **天数口径**：13.5-17.5 人日 / 日历 11-15 天回写 PRD §7（R5 轮 PM 裁决）；PLAN 并行假设补序 8 例外。
9. **基线数**：833/840 收集口径本轮已实跑确认，附录 A P0 行可据此定稿；passed 数沿 R2b 实跑声明，P0 首跑时复核一次即可。

——R3 轮完（代码执行者；等待 R4 架构师按上表修订 SPEC 后进 R5 轮 PM 天数裁决）

---

## R4（架构师）：按 R3 修订 SPEC

> 日期：2026-09　角色：架构师（R4 轮）　对象：`spec-v3.0.5.md`（407 行 → 修订后 418 行）
> 方式：R3「留给 R4 架构师的修订清单」9 项 + SG2-1~7 逐条裁决；涉及锚点变化处（E-5/MF2-1/MF2-2/SG2-4 及 SG2-5/SG2-6/E-6 引用锚点）全部重新打开代码实查——其中 SG2-4 实测 DEFAULT_PROMPTS 跨 :157-194（translation 项 :186-193），较 R3 建议值 :157-190 更精确，以实查为准。本轮不改 PRD、不改代码；PRD 回写归 R5 轮 PM（见下清单）。

### 逐条处理表

| R3 意见 | 处理 | SPEC 落点 | 一句话理由 |
|---|---|---|---|
| MF2-1 串行记账判据陷阱 | 接受 | M5.5 矩阵注记 + 裁决 1/2/3 | 判据差异实查成立（外层 :1135-1142 error vs 串行 :1182-1185 not-corrections，根源 `_call_batch` :1054-1056 parse 失败返回 error=None 且 corrections 空），冻结现状 = 聚合等价的最小保障；「串行 × parse 失败」点名为锁面并增第 (iii) 例 |
| MF2-2 缺口断链 + 白名单漏登 | 接受 | M5.3 新裁决 4 + 触点表 + M0-1/M0-2 (e) 补登 + 附录 A + 验收/测试 | 「写侧对账 ∪ 管线缺口」合并口径是 US-10 验收成立的必要条件；main.py 登记改点 1→2 已全链同步（M0-1 / M0-2 (e) / M5.1 裁决 5 例外注记 / M5.3 触点表与裁决 3 收窄 / 附录 A） |
| SG2-1 pendingResumable 残留标记 | 接受 | M5.3 裁决 7 | completion.track_id 比对命中才 toast（补译同轨合并、新建轨 id 天然不匹配，残留自愈）+ task:failed/cancelled 显式清，双保险零后端改动 |
| SG2-2 task:cancelled 无类型过滤 | 接受（择判据限定分支） | M5.1 裁决 2 | 补 task_type 判据限 llm_translation，改动面与需求面对齐；全类型放行属顺手修复，其余类型残留登记 record §8 不修；已核前端无既有断言锁「取消后保留 errorMsg」 |
| SG2-3 merge/create 七成同构 | 改判（目标接受、手段否决） | M5.3 裁决 5 | 抽共享 helper 必须改 create_translation_track 既有函数体为委托调用，破坏 M0-1「单一 hunk、零删改」承诺并扩大红线审查面；维持 project_service 单一方法复制先例，merge 自含实现，hunk 面由契约收敛 |
| SG2-4 llm_prompts 区间微偏 | 接受（实测再勘正） | M0-1 llm_prompts 行 + M9 R5.12 行 | 「键集不变零改动」结论维持；区间以实测 :157-194 为准 |
| SG2-5 前端缺 R5.15 额度 | 接受 | M-gate（前端 ≥23→≥24） | 级联删除计数（useWorkspaceActions.ts:536-545 实查）有真实断言面；R5.14 文案拼接无断言面，豁免并在 M-gate 明示 |
| SG2-6 R5.14 拼接落点 | 接受 | M9 R5.14 行 | 渲染层条件拼接（AIAssistantPanel :470-472 实查）不污染数据层全类型错误显示，与 M5.1 progressMessage 渲染侧思路一致 |
| SG2-7 quality_mode × 429 冗余 | 接受（附注采纳） | M5.8 裁决 5 | 冗余无害但需用例确认无双重 shutdown 副作用，(f) hunk 审查口径一句写清 |
| E-5 双入口证据错置 | 接受 | M5.0 裁决 4 | 实查 App.vue:165-167 为窗口拖拽 handler（handleWindowDragEnter/Over），非证据；证据改 WorkspacePage.vue:958 provide / :1619 绑定 + SuggestionPanel.vue:161-169 注释（:165 SAME handler 自证） |
| E-6 rejected 过滤分支误标 | 接受 | M0-3 前端例 + M9 R5.10 行 | 实查 :147-148 过滤仅 target_type 与视窗、:381 注释自证「NOT filtered」；改「新增分支 / 只增」，:364 翻转为 0、:366 随例删除的对应关系写明；PRD :189/:262 同措辞入回写清单（B-10） |
| 序 7 合流先行 | 接受 | M0-4 序 7 | 先定数据形状（completion payload）后改消费端（AIAssistantPanel / WorkspacePage watcher / useLlmTasks reset），防中间态假绿 |
| 序 8 R5.11 基线含 M5.4 | 接受 | M0-4 序 8 | 同文件族（useWorkspaceActions.ts + pendingCorrections 消费面），P4 并行唯一显式例外点，PLAN 应登记 |
| 天数复核 13.5-17.5 / 11-15 | 接受（注记落 SPEC） | SPEC 头部规模口径注记 | 终稿天数归 PRD §7，R5 轮 PM 回写（B-8）；并行假设例外（序 8）随注记登记 |
| 基线数 833/840 定稿 | 接受 | 附录 A P0 行维持 | 收集口径 R3 已实跑确认；passed 数沿 R2b 实跑声明，P0 首跑复核一次 |

**计数**：接受 13（其中 SG2-2 择其判据限定分支、SG2-4 按实测再勘正）/ 改判 1（SG2-3）/ 否决 0。

### SPEC 修订 diff 摘要（407 → 418 行）

- **头部**：版本行改「R2b 轮定稿 / R4 轮按 R3 意见修订」；依据链补 R3 条目；新增规模口径注记（13.5-17.5 人日 / 日历 11-15 天，终稿归 PRD §7）。
- **M0-1**：main.py 行补登 R5.3 completion 缺口合流 hunk（MF2-2，登记改点）；llm_prompts 行区间勘正 :157-184 → :157-194（SG2-4）。
- **M0-2**：(e) 行锚点补 :1317-1331/:1340，「成功路径 :1271-1344 零改动」收窄为「仅合流 hunk 增改」。
- **M0-3**：SegmentBlocksLayer 前端例补 E-6 勘正（新增分支 / 只增；:364/:366 与新增过滤对应关系）。
- **M0-4**：新增序 7（合流先行）/ 序 8（R5.11 基线含 M5.4）。
- **M5.0**：裁决 4 证据勘误 E-5（App.vue:165-167 → WorkspacePage.vue:958/:1619 + SuggestionPanel.vue:161-169）。
- **M5.1**：裁决 2 补 SG2-2 判据限定；裁决 5 补 MF2-2 唯一例外注记（合流 hunk 归 R5.3）。
- **M5.2**：裁决 3 交叉引用勘正（M5.3 裁决 5 → 裁决 4/7，随 M5.3 重编号）。
- **M5.3**：触点表「既有 uncovered 先例」行性质改「登记改点（MF2-2）」；新增裁决 4（缺口合流），原 4-8 重编号 5-9；裁决 3「handler 零改动」收窄为「消费逻辑零改动」；裁决 5 补 SG2-3 不抽 helper 约束；裁决 7 补 SG2-1 清理路径；裁决 9 补 MF2-2 合流断言；验收补「管线缺口段可见」；耦合点补序 7。
- **M5.5**：状态矩阵下新增记账判据注记（MF2-1 冻结 not-corrections、不照抄翻译侧 error 判据）；裁决 1 冻结句；裁决 2 点名「串行 × parse 失败」锁面；裁决 3 增第 (iii) 例。
- **M5.8**：裁决 5 补 quality_mode × 429 组合用例口径（SG2-7）。
- **M9**：R5.10 行 E-6 勘正；R5.12 行区间同步（SG2-4）；R5.14 行改渲染层拼接（SG2-6）。
- **M-gate**：前端总额 23 → 24（R5.15 ≥1）；后端 ≥30 维持——R2b 的 30 已含 R5.5 ≥4，与 R3 建议合并核对无冲突，合并终值 = 后端 ≥30 / 前端 ≥24。
- **附录**：A 预填提示补 main.py 两处「登记改点」逐 hunk 口径；B 新增 B-7~B-11；文末行更新。

### PRD 回写清单（汇总 R2b ★B-1~B-6 + R4 新增 B-7~B-11；供 R5 轮 PM 一次执行）

| ★ | PRD 章节行引用 | 修改内容 | 依据 |
|---|---|---|---|
| B-1 | §4-N5 / §2 R5.4① | 批量形参 `track_id: str = ""` → `str \| None = None` 三态（None=timeline 级兼容、""=主轨、「全部」=None+文案明示「含全部轨道 N 条」） | R2b：PRD 字面无法满足自身验收「主轨视图不动副轨」 |
| B-2 | §9（前端白名单初版为空） | 前端断言反转白名单定稿 2 例：AIAssistantPanel.test.ts:301 + SegmentBlocksLayer.test.ts:359-368（:364/:366） | R2b：R5.13 文字必然变化 + R5.10 三态语义反转 |
| B-3 | §1.3（预登记 5 例整例反转） | 收窄为逐 assert 行：仅 :217 改写 + :614 反转；单批场景四姊妹例零改动撤销 | R2b：单批 = 全批失败拒，语义未被 R5.3 触碰 |
| B-4 | （review-log 追记项，非 PRD 正文） | 锚点勘误 E-4/E-3 精确区间（受控改点 (f)=:1774-1790；纠错串行循环=:1171-1187） | R2b：MF-4 原引 :1019-1028 为纠错管线同构段 |
| B-5 | §7.4（:247-248） | R5.5 额度 ≥2→≥4；前端总额 22→23（**被 B-7 上修为 24，落笔以终值为准**） | R2b SG-2：429×取消交织无既有样板 |
| B-6 | §2 R5.1 边界（:112） | 纠错侧取消 token 上报/中性提示明确本版不做，维持 §10.2 ② 登记 | R2b：两族改动分离，收益/风险比劣于翻译侧 |
| B-7 | §7.4（:247-248） | 前端 ≥22 → **≥24**（+R5.15 级联删除计数 ≥1；R5.14 文案拼接豁免明示）；后端 ≥28 → **≥30** 维持——合并终值 **后端 ≥30 / 前端 ≥24** | R4 SG2-5：级联计数有真实断言面（useWorkspaceActions.ts:536-545） |
| B-8 | §7 规模裁决（:241）+ 各 phase 人日（:234-237） | 10-14 人日 → **13.5-17.5**（P1 4-5.5→6-8.5 / P2 1.5-2→2-2.5 / P4 2-3→3.5-5；P0/P3/P5 维持）；日历 8-12 → **11-15 天**（并行假设下，单人串行 15-19 天）；PLAN 并行假设写成承诺口径并登记序 8 例外 | R3 逐触点复核（低估段 = P1 的 M5.3/M5.8、P4 的 D4+顺带批）；终稿天数归 PRD §7 |
| B-9 | §1.5 白名单 main.py 行（:91） | 补登 R5.3 completion payload 缺口合流（:1317-1331 区 + 返回 dict :1340，登记改点） | R4 MF2-2：改动面进出必须与 SPEC M0-1 同步，防红线审查争议 |
| B-10 | §5 R5.10 行（:189）/ §8 风险表（:262） | 「过滤仅动 rejected 分支」→「**新增** rejected 过滤条件（现状无此分支，visibleEditRanges :147-148 仅 target_type 与视窗）」，改动性质只增——E-6 | R4 E-6：现状 :381 注释自证「NOT filtered」 |
| B-11 | §2 R5.3 ④（:126） | 澄清（非冲突）：对账通知数据源 = completion payload 的 uncovered_ids，按「写侧对账 ∪ 管线缺口」合并口径 | R4 MF2-2：防按 PRD 字面只查写侧对账导致 1/34 场景验收假挂 |

> 行号为 2026-09 PRD 版本参照；R5 执行时以关键词检索兜底。

### 留给 R5/R6 的注意点

1. **R5 轮 PM**：按 B-1~B-11 一次执行；B-5 与 B-7 前后覆盖，§7.4 落笔以终值（后端 ≥30 / 前端 ≥24）为准，勿留 23 中间值；天数终稿归 PRD §7（13.5-17.5 人日 / 日历 11-15 天）；超期决策树让位顺序不变（R5.8 首让位）。
2. **PLAN 回写两件事**：并行假设（顺带批与 P1-P3 并行开发）写成承诺口径的一部分 + 序 8 例外（R5.11 开发基线须含 M5.4，P4 并行唯一例外点）显式登记。
3. **R6 编排终检**：SPEC M5.0-M5.8 触点表与 M0 白名单一致性已自查（MF2-2 后 main.py 登记改点 1→2 全链同步：M0-1 / M0-2 (e) / M5.1 裁决 5 / M5.3 触点表·裁决 3·裁决 4 / 附录 A / B-9）；M5.3 裁决重编号后全文交叉引用仅 M5.2 一处、已同步为「裁决 4/7」，R6 复查无旧号残留（旧 4-8 → 新 5-9，语义映射：合并契约 / undo / toast / 对账 / 测试）。
4. **两项现状缺陷登记不修**（P5 终检勿误判漏改）：MF2-1 的外层/串行记账判据不对称（M5.5 裁决 1）、SG2-2 的非翻译任务取消 errorMsg 残留（M5.1 裁决 2）——均入 record §8 遗留。
5. **实施期硬约束**：序 7（合流 hunk 先行或同 commit 于消费端）与序 2（R5.3→R5.8 同函数族一次改透）是 P1 的两条硬约束；R5.10 触点按「只增 rejected 过滤」审查，勿扩触 editRangeClasses golden 面；M5.3 merge 按单一 hunk 自含实现验收，发现抽 helper 改动 create 即回退。

——R4 轮完（架构师；SPEC 修订完毕，待 R5 轮 PM 执行 B-1~B-11 回写后进天数终裁）

---

## R5（产品经理）：PRD 修订-1

> 日期：2026-09　角色：产品经理（R5 轮）　对象：`PRD-v3.0.5.md`（324 行 → 修订-1 后 332 行）
> 方式：对齐 3.0.4 R5 先例——按 R2/R3/R4 评审结论一次回写，PRD 逐处修订注明依据（MF / E / ★B / SG 编号）；本轮不改 SPEC、不改代码。修订全部为多次小 edit，未整文件重写。

### 回写处置表（B-1~B-11）

| ★ | 处置 | PRD 落点（修订-1） |
|---|---|---|
| B-1 | 落实 | §0.3 MVP 约束 + §4-N5 + §2 R5.4①/边界：形参改 `str \| None = None` 三态（None=timeline 级兼容 / ""=主轨 / 非空=副轨）；前端主轨传 ""、副轨传轨 id、「全部」传 null + 文案明示「含全部轨道 N 条」；「默认 "" 等价」同步改「默认 None 等价」 |
| B-2 | 落实 | §1.3 + §9 前端门禁：断言反转白名单定稿 2 例登记到 expect 行粒度（AIAssistantPanel.test.ts:301；SegmentBlocksLayer.test.ts:364/:366，共 3 行）+ 追认制 1 行（findOverlays 选择器，非 expect 行） |
| B-3 | 落实 | §1.3 + §9 后端门禁 + §10.3：白名单收窄为逐 assert 行 2 处（:217 随 R5.2 中文文案改写 / :614 随 R5.1 反转）；四姊妹例（:192/:226/:256/:518）整例反转撤销（单批 = 全批失败拒，语义未被 R5.3 触碰） |
| B-4 | 落实 | §1.6：(a) 锚区间改 :1116-1187（外层 + 429 串行两循环同改，E-3 补全）；新增 (f) 锚 :1774-1790（E-4 勘正后的翻译管线预构建段，注明 MF-4 原引 :1019-1028 为纠错同构段） |
| B-5 | 落实（被 B-7 覆盖） | §7.4：R5.5 额度 ≥4 落笔；前端总额不留 23 中间值，直接落终值 24 |
| B-6 | 落实 | §2 R5.1 边界：纠错侧取消 token 上报/中性提示明确本版不做（两族改动分离，收益/风险比劣于翻译侧），维持 §10.2 ② 登记 |
| B-7 | 落实 | §7.4：终值后端 ≥30 / 前端 ≥24（前端 +R5.13 估算显示 1 例 + R5.15 级联删除计数 1 例；R5.14 文案拼接豁免明示） |
| B-8 | 落实 | §7：人日 10-14 → 13.5-17.5（P1 6-8.5 / P2 2-2.5 / P4 3.5-5，P0/P3/P5 维持）；日历 8-12 → 11-15 天（并行假设写成承诺口径，序 8 例外入顺序约束⑥，单人串行备份日历 15-19 天）；超期决策树更新（首让 R5.8） |
| B-9 | 落实 | §1.5 白名单 main.py 行补登 R5.3 completion payload 缺口合流（:1317-1331 区 + 返回 dict :1340，登记改点） |
| B-10 | 落实 | §5 R5.10 行 + §8 风险表：「过滤仅动 rejected 分支」→「新增 rejected 过滤条件（现状 visibleEditRanges :147-148 无 rejected 逻辑，:381 注释自证）」，只增性质（E-6）；裁决定稿「隐藏」同步 |
| B-11 | 落实 | §2 R5.3④：对账通知数据源补「写侧对账 ∪ 管线缺口（ledger.uncovered_segment_ids）」合并口径（MF2-2 澄清，防 1/34 场景验收假挂） |

### R2 must-fix / suggest 同轮闭合（B 清单之外的 PRD 落点）

- MF-1 → §2 R5.4③ undo 快照层三态（「全部」= 三层并集）；MF-2 → §2 R5.1① 事件判据；MF-3 → §2 R5.4④ 超集兼容 + 刷新链；MF-4 → §1.6 (f) + §4 R5.8 边界（四处均落）。
- SG-1/SG-2 → §7.4（守恒不变量断言、MF2-2 合流断言、R5.5 ≥4 含「串行 × parse 失败」锁面例）；SG-3 → §4 R5.7 验收；SG-4 → §2 R5.4②；SG-5 → §5 R5.13；SG-6 → §2 R5.0（照 SPEC M5.0 裁决 2：popSnapshot 不触碰 redoStack）。
- 锚点勘误：E-1 / E-3 / E-6 随 PRD 正文勘正；E-4 经 B-4 影响 §1.6 (f) 取值；E-2 / E-5 为 SPEC 侧勘误，PRD 正文无错置锚点、不动。
- 联动修订：§8 风险表与 §10.3 的「受控改点 5 处」改 6 处；§9 断言反转登记改「后端 2 行 + 前端 2 例 + 追认制 1 行」；头部版本行与 §11 追加修订-1 条目。

### 修订记录追加摘要

§11 追加「修订-1（2026-09，架构师 R2/R4 + 执行者 R3 评审结论回落；已与 SPEC v3.0.5 终态对齐，冲突处按 SPEC 回写）」七个子条目：must-fix 4 条落点 / 焦点裁决 5 项结论 / 锚点勘误 E-1~E-6 / R2 suggest 6 条 / R3 意见回落（MF2-1、MF2-2 投影与序 7/序 8）/ 天数重报（13.5-17.5 人日 / 日历 11-15 天）/ B-1~B-11 处置，格式对齐 3.0.4 PRD §11 修订-1。

### 三文档对齐自查（四交叉点，抽查 R5.0-R5.8）

1. **R 编号映射**：PRD R5.0-R5.16 ↔ SPEC M5.0-M5.8/M9 逐条对应；B-11 后 R5.3④ 与 SPEC M5.3 裁决 4 同口径；B-1 后 R5.4①/§4-N5 与 M5.4 裁决 1 三态同形；R5.1① 与 M5.1 裁决 1 事件判据同措辞。无字面冲突。
2. **白名单**：§1.5 六文件 = SPEC M0-1 终表（main.py 含两处登记改点：R5.3 合流 hunk + R5.4 expose 透传）；§1.3 与 SPEC M0-3 同为「后端 2 行 + 前端 2 例 + 追认制 1 行」；§1.6 六处 = M0-2 (a)-(f)，(a)=:1116-1187、(f)=:1774-1790 一致。无字面冲突。
3. **天数**：§7 13.5-17.5 人日 / 日历 11-15 天 = SPEC 头部规模口径注记；并行假设 + 序 8 例外两文档同口径；超期决策树首让 R5.8 两文档一致。无字面冲突。
4. **测试额度**：§7.4 后端 ≥30 / 前端 ≥24 = SPEC M-gate 终值；分项额度（R5.5 ≥4、R5.3 ≥10 含 SG-1+MF2-2 断言、R5.13/R5.15 各 1、R5.14 豁免）与 M-gate 逐项一致。无字面冲突。

**自查结论**：抽查 R5.0-R5.8 验收条目、白名单、天数、测试额度四交叉点，PRD 修订-1 后与 SPEC 无字面冲突；E-2/E-5 两处 SPEC 侧勘误不涉 PRD 正文。

——R5 轮完（产品经理；PRD 修订-1 完毕，待 R6 项目经理排期）

---

## R6（项目经理）：PLAN 排期

> 日期：2026-09　角色：项目经理（R6 轮）　对象：新建 `plan-v3.0.5.md`（约 470 行，5 次增量写入）
> 方式：对齐 3.0.4 PLAN 先例（标题树骨架 / checkbox+门禁+record 三件套 / 里程碑触发式回填 / 立项会裁决登记表）；输入 = PRD 修订-1 §7 与 §10.3 / SPEC M0-4·M-gate·附录 A / review-log R5「留给 R6 排期输入」；本轮不改 PRD/SPEC/代码。

### R5「留给 R6 排期输入」逐条落点

| 输入 | PLAN 落点 |
|---|---|
| 并行假设为承诺口径 | 头部规模口径 + §0.4 #4（单人串行备份 15-19 天写入里程碑口径说明） |
| 序 8 例外（R5.11 开发基线须含 R5.4） | §0.3 序表 + P4-3 前置 checkbox——P4 并行唯一显式收窄点 |
| 序 7 合流 hunk 先行 | §0.3 序表 + P1-4 内部序硬约束（先 main.py 合流 hunk 后消费端） |
| 缓冲阀挂 R5.8 | 超期决策树触发 A 首让 R5.8（含 (f) 与 config 键；(d)/(f) 分行登记可独立回退、不牵连 R5.3） |
| 测试增量按 30/24 排入各 phase | §0.1 期望总数表：P1 后端+20/前端+11、P2 +6/+3、P3 +4/0、P4 0/+10——合计恰 = 30/24 |
| 单人串行备份 15-19 天 | 里程碑口径说明 + 决策树「仍超」分支重报口径 |

### 排期关键裁决（PM 新增，冲突处以 SPEC 为准）

1. **门禁脚本处置**：`scripts/gates-v3.0.4.sh` 复制为 `gates-v3.0.5.sh`，改基线 tag 与断言白名单核对方（R0-3 由「期望零」改「命中落 M0-3 白名单」）；旧脚本退役不删（P0-2）。
2. **P2 内部拆分**：R5.4 拆 P2-1 后端（序 3 同 commit 族内聚）与 P2-2 前端消费链——凭 data 纯增 patch 键超集兼容，两步门禁独立可回滚。
3. **P4 覆层族收口**：R5.6③ 覆层 hunk、R5.7④、R5.9、R5.10、R5.14 按 PRD 约束③与 M5.6 裁决 3 收口为 P4-2 一个 commit 族；R5.6 先行步只落不触该 hunk 的三面。
4. **R5.12 与 D4 同批置 P4-4**（llm_prompts 1 行零前端牵连；D4 不占 30/24 额度、增量如实登记）。
5. **每步门禁命令照 SPEC M-gate 原样**，node 回落条款内置（record-3.0.4 §2 先例）；P0 基线首跑复核 passed 数（沿 R4 裁决）。

### 留给 R7 编排终检的注意点

1. 自查已做：R5.0-R5.16 十七条全部有归属步骤（PLAN §0.3 归属总表）；M0-4 序 1-8 全部显式落点；测试额度合计 = 后端 30 / 前端 24 恰达下限（D4 另计）。
2. P1 期望总数（beta.1 = ≥853 / ≥851·850）由 M-gate 逐主项额度推导，P0 首跑与 P1 末各复核一次；R5.16 根修完成则豁免退役、门禁按全绿判。
3. 真机清单分 beta 轮落 PLAN（beta.1 含 duplicate 手感与失败→补译全链；RC 千段观测债必填），终检时与 SPEC M-gate 真机段、PRD §9.3 三方对读。
4. 两项「登记不修」缺陷（MF2-1 记账判据不对称 / SG2-2 errorMsg 残留）终检勿误判漏改；让位触发（如有）核对四要素留痕与回写。
5. PLAN 未给任何绝对日期（触发式回填延续）；执行期 SPEC 与 PLAN 冲突以 SPEC 为准并当场回写 PLAN。

——R6 轮完（项目经理；PLAN 定稿，待 R7 编排终检）

---

## R7（编排者）：跨文档一致性终检

> 日期：2026-09　角色：编排终检（R7 轮）　对象：`PRD-v3.0.5.md`（332 行）· `spec-v3.0.5.md`（418 行）· `plan-v3.0.5.md`（393 行）· 本日志 R2-R6 · `研究报告-v3.0.5.md`（§4/§6/§7/§8.4）
> 方式：对齐 3.0.4 R7「跨文档一致性终检」先例，11 项清单逐项判定（对齐 / 偏差（已修）/ 疑点（待裁决））；无歧义数值/交叉引用不一致仅修最年轻文档 PLAN（冲突一律以 SPEC 为准）并逐处留痕；PRD/SPEC 及评审记录疑点只登记不改动。

### 终检结论总览

| # | 清单项 | 判定 | 证据（文件+章节） |
|---|---|---|---|
| 1 | 编号映射链 | 对齐 | 研究报告 §4 全 25 编号（F1-F4/S1-S6/P1-P7/D1-D8）= PRD §0.1 全 25 行；R5.0-R5.16 由 SPEC 概要表 M5.0-M5.8+M9 全覆盖；PLAN §0.3 归属总表 17 条 + D4 全落步（P1-1…P4-4）；自 PLAN 步骤表反查每步 M/R 编号在 SPEC/PRD 均存在，无缺号、无悬空 |
| 2 | 用户故事映射 | 疑点（待裁决） | US-01~05/07/09~11 共 9 条在 PRD 条目头部或 §5 行内标注（R5.0=US-01、R5.1/R5.2=US-02、R5.2/R5.3=US-03、R5.4=US-04、R5.6=US-05、R5.11 行=US-07、R5.13 行=US-09、R5.3=US-10、R5.15 行=US-11）；R5.7 引草稿号 US-B-05（用户反馈-B §五实有，统一表无 S4 故事）、R5.8 引 R-A-05（用户反馈-A R 表实有）均成立；US-06（→R5.10）与 US-08（→R5.11 审阅半+S2 联动）PRD 全文无标注亦无不做映射说明，映射可由研究报告 §6 反查、无冲突——登记疑点 ① |
| 3 | 白名单与受控改点 | 对齐 | 文件集：PRD §1.5 六文件+tests = SPEC M0-1 终表；main.py 登记改点 = 2（R5.3 合流 hunk + R5.4 expose 透传）：SPEC M0-1/M0-2(e)/附录 A、PRD §1.5（★B-9）、PLAN P5-1 同值；llm_prompts 区间 :157-194（SPEC M0-1/M9 = PLAN P4-4）；受控改点 (a)-(f) 三文一致（(a)=:1116-1187、(f)=:1774-1790）；断言反转白名单终态三处一致 = 后端 2 行（test_llm_translation.py:217/:614）+ 前端 2 例 3 行（AIAssistantPanel.test.ts:301 + SegmentBlocksLayer.test.ts:364/:366）+ 追认制 1 行（findOverlays 选择器） |
| 4 | 数值四交叉 | 对齐 | 天数 13.5-17.5 人日 / 日历 11-15 / 串行 15-19：PRD §7 = SPEC 头部注记 = PLAN 头部+§0.4#4；额度后端 4+4+10+6+4+2=30、前端 3+3+4+3+3+4+2+1+1=24（PRD §7.4 = SPEC M-gate 逐项同值），PLAN §0.1 分配 P1+20/+11、P2+6/+3、P3+4/0、P4+0/+10 合计恰 30/24；基线 833 / 840·839 四处一致；节点推导 853·851·850 → 859·854·853 → 863 → 863·864·863 逐格算术成立。附注：总人日区间为 R3 逐项口径推导，非 phase 端值代数和（14-19.5），三文同口径，非冲突 |
| 5 | 门禁与红线命令 | 对齐 | PLAN §0.1 命令块与 SPEC M-gate 八条命令逐条同文（含注释口径）；diff 基线两文恒为 tag `v3.0.4`（PLAN 头部显式「不受文档入库与 tag v3.0.5-base 影响」）；node 回落条款 PLAN §0.1 在场（record-3.0.4 §2 先例内置） |
| 6 | 顺序约束 | 对齐 | SPEC M0-4 序 1-8 ↔ PLAN §0.3 序表 8 行一一映射无遗漏；序 1 = P1-1 全版首个代码合入步、序 7 = P1-4 内部硬约束、序 8 = P4-3 前置 = P2 已合入，三处落位与 review-log R6「留给 R7 编排终检的注意点」#1/#2 一致 |
| 7 | 立项会三裁决 | 对齐 | F1：PRD §0/§0.1/§6-Q1/§11 裁决①均为「并入 3.0.5 首项、v3.0.4 不出补丁」，无补丁表述残留（研究报告 TL;DR 补丁建议为待裁问题原文）；六主项全量：PRD §0.3/§11 = PLAN §0.4#2 = SPEC 概要表；S6：PRD §0.1/§6-Q5/§10.2① 3.1.x 登记在场 = PLAN §0.4#3 |
| 8 | 裁决表 | 对齐 | PRD §6 Q1-Q8 + N1-N5 + trim 四维矩阵与 SPEC M5.0-M5.8 相应裁决逐条同向（N5 三态经 ★B-1 两文同形；N2/M5.1 裁决 2 同为取消不再 emit analysis_failed）；焦点 1-5 SPEC 落点齐备：M5.2 裁决 4 + M5.3 裁决 9 / M5.4 裁决 2 / M5.5 矩阵+裁决 1 / M5.7 裁决 1/3/4 / M5.1 裁决 1 |
| 9 | 真机清单 | 对齐 | PRD §9.3 八项 = SPEC M-gate 真机段八项一一对应（SPEC 明注「逐条见 PRD §9.3 1-8 项」）= PLAN beta.1/2/3+RC 分轮清单全覆盖；千段观测债 RC 轮必填三文在场（PRD §9.3 第 1 项 / SPEC M-gate / PLAN RC 行） |
| 10 | 超期决策树 | 偏差（已修） | 首让 R5.8 / 次让序 R5.7 lane 半→R5.11 时间码半→R5.14 / 不可让 R5.0-R5.6 / 四要素留痕：PRD §7 与 PLAN 决策树逐条一致；PLAN §0.4#2 留痕要求原漏列首让项、与同文决策树触发 A 及 §0.4#5 授权交叉不一致——已修（修正 ①） |
| 11 | 遗留核对 | 对齐 | PLAN P1-2（SG2-2 其余类型残留「登记 record §8 不修」）/ P3-1（MF2-1「登记遗留、不顺手统一」）/ P5-1 与 record 落盘要求（「登记不修勿误判漏改」）均无「待修」误导表述 |

### 已修正清单（均落 `docs/3.0.5/plan-v3.0.5.md`，小 edit 逐处留痕）

1. **§0.4 立项会裁决登记表 #2「留痕要求」**：原「让位仅可按超期决策树部分让（R5.7 lane 半 / R5.11 时间码半 / R5.14）」漏列首让项 R5.8，与本文决策树触发 A（首让 R5.8 整体回池）、同表 #5 授权（首让 R5.8）及 PRD §7「首让 R5.8」交叉不一致——改为「让位仅可按超期决策树：首让 R5.8 整体回池（触发 A）；部分让 = R5.7 lane 半 / R5.11 时间码半 / R5.14（触发 B）」，不可让面 R5.0-R5.6 表述不变。依据：PRD §7 超期决策树 = SPEC 头部注记（R5.8 首让位）。
2. **§0.2 断言反转白名单登记**：四姊妹例（:192/:226/:256/:518）撤销的依据注「（★B-3/B-4）」中 B-4 为锚点勘误条目（E-3/E-4 精确区间，SPEC 附录 B 自证「review-log 追记项，非 PRD」），与姊妹例撤销无关，且本文 P1-3 步同事实已正确单引 ★B-3——改为「（★B-3）」。依据：SPEC 附录 B B-3/B-4 行界分。

### 疑点清单（登记不改动；待用户/后续轮次裁决）

1. **US-06 / US-08 标注缺口（PRD）**：US-06（→P2/R5.10）与 US-08（→P3 审阅半 + S2 联动）在 PRD 全文无任何标注、亦无「不做映射」说明；研究报告 §6 映射关系明确、无实质冲突，属需求条目用户故事标注完备性缺口。建议后续在 PRD §5 R5.10/R5.11 行补 US 标注或于 §2 说明映射口径。
2. **「R5 留给 R6 排期输入」引注错置（review-log R6 节头部与落点表标题 + PLAN 头部依据链同款）**：review-log 实际不存在该标题，对应内容为 R4 节「### 留给 R5/R6 的注意点」#1/#2（终值经 R5 节 B-7/B-8 落实承载）；实质输入链完整、无数值冲突。review-log 为历史评审记录本轮不改，建议归档时勘注，PLAN 头部引注随之同步。

### 终态文件清单

| 文件 | 行数（R7 后） |
|---|---|
| docs/3.0.5/PRD-v3.0.5.md | 332（本轮未动） |
| docs/3.0.5/spec-v3.0.5.md | 418（本轮未动） |
| docs/3.0.5/plan-v3.0.5.md | 393（两处行内替换，行数不变） |
| docs/3.0.5/review-log-v3.0.5.md | 497（446 + R7 章节 51 行） |

### 开工前置清单（照 3.0.4 先例，与 PLAN P0-1/P0-2 对应）

1. 文档入库：`docs/3.0.5/` 全部文档以 `docs(3.0.5): ...` 两段式提交落 `dev-3.0.5`；
2. 拉分支：`dev-3.0.5` 自 tag `v3.0.4` 拉出，打 tag `v3.0.5-base`（打在拉出点 = `v3.0.4` 所指 commit，先于文档入库——纯代码回滚锚点）；门禁 diff 基准恒为 `v3.0.4` 不受影响；
3. 基线首跑登记：pytest 833 全绿 / vitest 840 collected·839 passed（useRowLayout.perf 豁免口径确认，passed 数首跑复核一次）/ build / lint / ruff 全绿 / 红线命令零命中；建 `record-3.0.5.md` 骨架（§1 分步索引表 + 后端改动登记表 P0 零改动行）；
4. 门禁脚本：`scripts/gates-v3.0.4.sh` 复制为 `gates-v3.0.5.sh`（基线 tag 与 M0-3 白名单核对方更新、node 回落内置、基线 dry-run 三段 exit 0；旧脚本退役不删）。

——R7 轮完（编排终检；两处 PLAN 修正与两项疑点登记如上，四文档可入库，按 PLAN P0 开工）

### 编排者后记（R7 疑点处置，2026-09）

1. **疑点 1 已闭合**：PRD §5 顺带批表 R5.10 验收补「（US-06）」、R5.11 验收补「按轨过滤与『全部』切换可用（US-08）」——US-01~11 现已全部在 PRD 需求条目有落点（主项头部标注 + 顺带批行内标注），映射链研究报告 §6 → PRD → SPEC M 项 → PLAN 步骤完整。
2. **疑点 2 勘注归档**：review-log R6 节头部与 PLAN 头部依据链所引「R5 留给 R6 排期输入」，实指 R4 节「### 留给 R5/R6 的注意点」#1/#2（终值经 R5 节 B-7/B-8 落实承载）——历史轮次正文不改，以本勘注为归档口径，PLAN 头部引注随下次 PLAN 触碰时顺带勘正。

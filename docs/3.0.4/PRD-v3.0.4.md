# Milo-Cut v3.0.4 需求文档（PRD）

> 版本：3.0.4（立项定稿——2026-09；红线重启版，见 §1；修订-1：架构师 Round 2/4 + 执行者 Round 3 评审结论已回写，见 §11 修订记录）
> 主题：**副轨内容智能化 + 手动剪辑范围回归** —— AI 翻译生成翻译副轨、AI 纠错感知当前轨（主项）；编辑扫掠覆盖副轨、lane 建段接线、语义搜索修正、手动剪辑范围（顺带）
> 基线：v3.0.3（tag `v3.0.3`，含修订-1 选择器防挤占追补）
> 日期：2026-09
> 依据：[3.0.4 开发探索报告](探索报告-v3.0.4.md)（§1-§8 全文取证 + §7 范围草案）· [SPEC v3.0.4](spec-v3.0.4.md)（实施层终态；本 PRD 与 SPEC 冲突处以 SPEC 为准）· record-3.0.3 §4/§5 遗留登记
> 角色：产品经理

---

## 0. 版本定位

v3.0.4 的主题只有一个：**副轨内容智能化 + 手动剪辑范围回归**。3.0.0-3.0.3 连续四版把副轨的「显示与编辑闭环」逐层补齐——3.0.0 多轨数据结构、3.0.1 波形侧增删改与 SRT 导入导出、3.0.2 多行时间线与行内生命周期、3.0.3 列表轨感知——但「副轨的内容从哪来」始终只有两条路：手动建段或导入 SRT（探索报告 §1.4）。本版把副轨从「能编辑」升级为「能被 AI 读懂与生成」：AI 纠错感知当前轨（S2），AI 翻译一键生成绑定主轨的翻译副轨（S1，v3.0.0 预留的 `role="translation"` 与 3.0.1 登记暂缓项正式兑现）。

同时补回两条断掉的工作流：3.0.x 约束收紧中丢失的「剪辑范围」标记习惯以正规载体回归（S4——range 型 EditDecision 数据层从未消失，缺的只是创建与管理 UI，探索报告 §5.1）；用户直接反馈的「编辑字幕」按钮对副轨无效（S3，3.0.3 M1-3 有意豁免的书面裁决反转）。探索中顺带实锤的两处缺陷（X1 lane 建段断链、X2 语义搜索轨模式错位）一并修复。

副轨能力升级必然触碰后端：连续四版「后端零改动」红线在 3.0.4 **正式解除**，替换为「只增不改」约束（§1）——采纳探索报告 §0 总评与 §7.2 的建议，由本 PRD 定稿措辞。

### 0.1 立项来源登记表

| # | 登记项 | 登记处 | 本版裁决 |
|---|---|---|---|
| 1 | T1 列表「编辑字幕」按钮对副轨生效 | 探索报告 §2（用户直接反馈；3.0.3 SPEC M1-3 有意豁免的书面裁决，record-3.0.3-P1-3） | **入版，顺带 S3**（方案 A；裁决反转理由见 R3.1，方案 B 不入版见 #9） |
| 2 | T2 AI 功能感知轨道选择（只开纠错） | 探索报告 §3（用户本次；无既有登记，新立项） | **入版，主项 S2** |
| 3 | T3 翻译生成副轨 | 探索报告 §4；3.0.1 PRD:54 / spec-堆叠时间线分析:104「不做（沿承 v2 报告）」 | **入版，主项 S1**（出池——登记两年多的暂缓项，副轨价值主张的直接兑现） |
| 4 | T4a「剪辑范围」新承载 | 探索报告 §5（用户本次；2.x 占位块用法属未登记隐性行为，该报告已补登记） | **入版，顺带 S4**（方案 C+B，探索报告 §5.3 推荐） |
| 5 | T4b 静音检测 / 自动裁剪间隙回归检查 | 探索报告 §5.4（用户疑虑，无正式登记） | **已核销：未破坏**（代码与 716 例单测层面双证；测试缺口清单部分由 S4 新用例覆盖，§5 R4.1） |
| 6 | X1 波形区副轨 lane「建段模式点击建段」链路从未接通 | 探索报告 §6.1（本次探索新发现，引入时即断，两条调查线交叉确认） | **入版，顺带 S3** |
| 7 | X2 轨模式下语义搜索结果预览错位 | 探索报告 §6.2（本次探索新发现） | **入版，顺带 S3**（前端显示侧修正） |
| 8 | 副轨删除确认策略再评估 | record-3.0.3 §5 遗留 #2；探索报告 §7.4 | **入版**（轻量再评估任务：S1 交付后随真机反馈裁决，§10.1） |
| 9 | T1 方案 B 波形侧编辑模式一致性收口（lane trim/菜单守卫） | 探索报告 §2.4（可选加强）、§7.1（可选项） | **不入版**，登记版本池（§6-Q2：trim 冻结语义需先裁决，3.0.5 候选） |
| 10 | 谓词表第 4 行测试深化（createWorkspaceActions 轻量实例化） | record-3.0.3 §5 遗留 #3 | 不入版，登记维持（测试基建改造，与 S1-S4 无耦合） |
| 11 | README_zh 功能段回填（3.0.x 特性段落集中补） | record-3.0.3 §5 遗留 #4；探索报告 §7.4 | **入版**（P4 文档轮，含本版新特性与翻译轨级联语义说明） |
| 12 | 挂载墙钟 perf gate 环境差（useRowLayout.perf.test.ts） | record-3.0.3 §5 遗留 #5 | 维持已登记环境例豁免口径（§9 门禁照旧）；根修登记清债池，不阻塞本版 |
| 13 | smooth 默认值 A/B | record-3.0.3 §4 #1 | 已销账（`false` 终局），无动作 |
| 14 | T2 附带修复：accept 返回 patch 化 + accept 入 undo 快照 | 探索报告 §3.4.3/§3.4.4、§7.4 | **入版**（并入 S2 R2.3——超集方案，既有断言零改动，见该条） |
| 15 | 版本池 7 项维持（桥断连警示 / 点击字幕三模式 / 撤销恢复选区+视图 / 工作区预设 / 行设置随工程 / 二分切片 / 手工 DOM 行保留） | record-3.0.3 §5 #6 版本池注记 | **不入版**，版本池维持原样（含「需 schema 演进」两项——红线重启仍冻结既有字段，schema 演进留 3.1.x 专门重启，§6-Q14） |
| 16 | 2.x 遗留互相重叠字幕段的载入解交叠迁移 | 探索报告 §8-Q13 | 不入版，登记观察项（触发 = 收到真实旧工程受阻塞反馈） |
| 17 | 3.0.3 顺延双平台真机冒烟清单（含建议面板/红罩层多行视觉回归） | record-3.0.3（跳过冒烟裁决）；探索报告 §5.4/§8-Q15 | **入版**（并入 P4 真机清单，与 S4 新增面板分组合并补验） |

### 0.2 范围裁决

**做**：

- S1 AI 翻译生成翻译副轨（§2，主项）——翻译批处理管线 + 批量落盘与主轨绑定 + 前端闭环
- S2 AI 纠错感知当前轨（§3，主项）——payload 轨道参数 + pending 作用域化 + accept/reject 轨道感知与 patch 化 + 前端门控
- S3 前端顺带批（§4）——T1 方案 A（编辑扫掠覆盖副轨）+ X1（lane 建段三处接线）+ X2（语义搜索显示侧修正）
- S4 手动剪辑范围（§5）——`add_range_decision` expose + 「范围标记」toggle 框选/时间码创建手势 + 建议面板「手动范围」分组 + keep 完整闭环
- 清债：README_zh 回填、副轨删除确认策略再评估、3.0.3 顺延真机清单并入（§10）

**不做**（沿承登记裁决或本版新裁决，均注出处）：

- T1 方案 B（波形侧编辑模式一致性收口）——登记表 #9，版本池
- 语义搜索 track 维度化——X2 仅修显示侧数据源对齐（探索报告 §3.2.4：搜索只读无害，轨维度搜索未立项）
- 翻译增量补译 / 自动合并已译轨——MVP 拒绝重译 + 提示清空/删轨（§6-Q7）；ledger.uncovered 补译入口登记后续增强
- workflow_engine 纳入翻译/纠错 step——回滚层无 tracks（探索报告 §3.2.5、§4.4.6）
- 方案 A「剪辑范围轨」与 lane 形态范围标记——探索报告 §5.3 论证纯增成本（影子 edit 皮肤化）；§6-Q12
- 2.x 重叠段载入解交叠迁移——§6-Q13
- 版本池全部项目——登记表 #15
- 主轨既有行为、主轨视图交互的任何变更——超集原则（红线 §1.4）

**MVP 约束**：

- S1/S2 的轨道归属编码一律走 AnalysisResult **detail JSON**，不加模型字段（红线 §1.1 字段冻结的直接体现）
- S1 译文条目同 start/end 复制主轨时间；绑定 offset=0、按 id 精确 1:1
- S4 手动范围备注仅 `source="manual"` 固定标记，无自由文本（EditDecision 无备注字段，加字段违红线）
- track 选择器仍为纯会话视图态（3.0.3 裁决不变，本版仅消费不触碰）

---

## 1. 红线重启声明：「后端零改动」→「只增不改」

3.0.0-3.0.3 连续四版「后端零改动」红线（五文件 diff 为空）在 3.0.4 **正式解除**。解除理由：S1/S2/S4 是登记暂缓项与既有数据预留（`role="translation"`、`export_subtitle` track 先例、range 型 EditDecision）的正路实现，继续零改动等于无限期搁置副轨价值主张。替换为以下五条「只增不改」约束：

1. **models.py 只增、字段冻结**：`core/models.py` 允许新增枚举成员（`TaskType.llm_translation`）与常量；既有模型的字段**不加、不改、不删**——AnalysisResult 的轨道归属走 detail JSON 而非新字段，即为此条的直接应用。
2. **events 双侧同步**：新增事件（`llm:translation_completed`）必须在同一改动内于 `core/events.py` 与 `frontend/src/utils/events.ts` 双侧登记；门禁口径 = **本版新增事件名的双侧存在性检查**（§9，Round 2 suggest 精化）——不做全量常量集比对（events.ts 含 2 个前端专属 demo 常量、events.py 无对应项，属既有现状非违规，全量比对会误报）。
3. **既有测试不改断言**：`tests/` 与 `frontend/src/**/*.test.ts` 既有断言默认零改动。**唯一例外 = 裁决反转的固化断言白名单**：本版仅 1 处——`TranscriptRow.test.ts:270-276`「never enters text edit under globalEditMode」随 R3.1 裁决反转同步反转（断言与意图一起改，登记于 record 反转清单）。白名单外的断言删除/改写视为红线违规。
4. **主轨行为零回退**：track_id 缺省路径、无手动 range/keep 数据的工程、主轨视图交互（新增 toggle 全部默认 OFF）与 v3.0.3 完全一致（等价旧红线 M0-1.3 延续）。允许的「改」既有代码仅三个落点、均行为兼容：`generate_subtitle_keep_ranges` 的 keep 感知与陈旧 trim 剔除（R4.4，无用户 keep range 时行为逐字节不变，golden 对拍保障）、`core/correction_service.py` 的 store/get/accept/reject（R2.2 互清作用域化 + R2.3 超集 patch 化，主轨序列观测行为不变）、`main.py` `start_subtitle_correction` 增可选形参 `track_id=""`（R2.1，默认值零影响）。
5. **门禁从「五文件 diff 为空」改为「白名单 + diff 审查制」**：后端可 diff 文件白名单（终态以 SPEC M0-1 表为准，Round 2 补齐）= `core/models.py`（仅枚举成员/常量）、`core/events.py` + `frontend/src/utils/events.ts`（仅双侧新事件常量）、`core/config.py`（仅 DEFAULTS 追加 `llm_translation_target_language` 一行，S1 只增触点）、`core/llm_prompts.py`（仅 translation prompt 注册，S1 只增触点）、`core/llm_service.py`（仅新增 `analyze_subtitle_translation` 及私有辅助，S1 只增触点）、`core/project_service.py`（新增 `create_translation_track` / `add_range_decision` + 受控改点 ① `generate_subtitle_keep_ranges`）、**`core/correction_service.py`（Round 2 must-fix 补——R2.2 互清作用域化与 R2.3 accept/reject patch 化全部落此文件，初版清单漏列）**、`main.py`（新 handler/expose + 登记改点 `start_subtitle_correction` 增可选形参）；白名单外 `core/**` 与 `pywebvue/**` 为禁改面、diff 必须为空。每 phase 门禁执行 §9 固定命令产出后端 diff 清单，对照 SPEC 维护的「后端改动登记表」逐条核对——每条 diff 必须对应一个 R 编号；无对应者要么补登记要么回退。

顺带项 S3 维持局部零后端改动（纯前端）；S4 后端改动 = 1 个新 expose + R4.4 一处受控修改。

---

## 2. S1：AI 翻译生成翻译副轨（主项）

数据层全预留（探索报告 §4.1）：`SubtitleTrack.role` 含 `"translation"` + `language` 字段、`add_track(role=)`、`export_bilingual_subtitle`（要求 BOUND 段才参与双语导出——绑定的最硬证据）、播放双语第二行全部现成，本版只补「翻译管线」。

### R1.1 翻译入口与语言选择

**需求**：AIAssistantPanel 新增「翻译为新副轨」卡片（具体挂点 SPEC 定）；触发对话框内联选择目标语言（常用清单 + 记忆上次选择，`config.py` 新增 `llm_translation_target_language` 默认值）；入口展示预估批数与 token 量级提示；主轨无 subtitle 段时置灰。

**边界**：语言清单与 `SubtitleTrack.language` 填值规范（BCP-47 短码，如 `en`/`ja`/`zh-CN`）SPEC 定；源语言取 `transcript.language`，不做 LLM 自检；只译主轨，不支持选轨翻译。

**验收**：记忆上次语言跨会话生效；预估批数与实际**量级一致**（Round 2 ★ 放宽：按 30/批静态估算并标注「约」——字符预算动态收缩使精确批次只能后端算）；空主轨不可触发。

### R1.2 翻译批处理管线（后端）

**需求**：`TaskType` 新增 `llm_translation`；`start_translation` expose + `_handle_translation` handler（照纠错 handler 模式）；`analyze_subtitle_translation` 复刻纠错批处理骨架（batch_size 30 / 字符预算 4000 / 前后 ctx 5 条 / 并发 5 / opaque id / 4 层 JSON 解析兜底 / BatchLedger / 每批一次重试 / 连续 429 转串行——参数同 config 既有值）。**coverage 校验反向**：翻译必须每条输出（与纠错「无需修正不输出」相反），输出 id 集合 ≠ 目标 id 集合的批记入 ledger 失败、不落盘。**跨批上下文（Round 2 must-fix 改判）**：并发 5 与「上一批定稿译文滑动窗」互斥——纠错骨架在派发前**预构建全部批 payload**（llm_service.py:1013-1019），并发执行下批构建时上一批尚未定稿，引入批间依赖即事实串行（约 5× 时延）。本版裁「**保留并发 + 上下文 = 源文 ±ctx 窗口**」（术语一致性由 prompt 约束 + 三层覆盖 glossary 参数承担）；「定稿译文滑动窗」登记版本池（需串行模式/config 开关，3.0.5 候选，§10.2）。

**边界**：段源 = 主轨 subtitle 段、排除 confirmed-deleted（语义对齐导出映射）；prompt 注册 `translation` key——**注册 `params` 必须为 `{}`**（Round 2 suggest #9）：`_inject_placeholders` 只遍历注册 key，未注册 key 的 `{{target_language}}` 占位符原样穿透 `get_effective_prompt` 三层覆盖（若注册进 params 会被 `_format_param` 替换成空串、语言信息丢失）；handler 拿到 effective prompt 后执行 `{{target_language}}` **终替换**，替换后残留 `{{` 即 **fail-fast**（防 system_override 拼写错位静默降级）；非 json_mode 提供商（Qwen/GLM/Ollama）的解析鲁棒性须专项 mock 测试。

**验收**：全量输出守恒（漏译/多译批次进 ledger 不落盘）；部分失败时任务可取消、已完成批不写入；429 降级路径复用纠错语义。

### R1.3 批量落盘与主轨绑定（后端）

**需求**：全部批次成功后一次性落盘（后台线程）：**新增批量写方法**（照 `import_srt_as_track` 的 `transcript.model_copy` 整体替换写法）——`add_track(role="translation", language=target)` + N 段（同 start/end 复制主轨时间）+ 按 id 精确 1:1 建 offset=0 bindings + **单个** `_success_patch(tracks=…, bindings=…)` 保证 undo/redo 原子。**禁止循环调用 `add_track_segment`**（一段一 patch = 千次桥接往返 + 千个 revision + undo 污染，3.0.2 smoke 已证此坑）。

**边界**：同目标语言已有 translation 轨 → 拒绝并提示（可先清空/删轨后重跑）——**双保险**（Round 2 ★）：`start_translation` 入口校验 + 批量写方法入口再查一次（任务运行 1-3 分钟期间用户可能手动建同语言轨，写侧兜底拒并带指引文案）；MVP 不做自动合并/增量重译；翻译期间主轨被增删段导致 id 配对落空 → 不静默，结果面板明示未覆盖段清单（US-T3-4）。

**验收**：千段级单 patch 落盘（revision +1 而非 +N）；undo 一次回退整轨（含 bindings）；重译拒绝路径有明确提示；漏段对账可见。

### R1.4 前端闭环与事件

**需求**：useLlmTasks 扩展翻译任务；翻译卡「主轨无 subtitle 段置灰」判定所需的 **mainSegments 透传链**（WorkspacePage → Timeline → AIAssistantPanel）随 P1 交付，并与 M2-4 的 `active-track-id`/`active-track-name` 链**一次改动接通**（§7 顺序约束 2；X2/R3.3 于 P3 复用延伸）；**任务 start 前 `pushSnapshot(["tracks","bindings"], "AI翻译副轨")`**（后台线程完成写入时前端无法插入快照）；进度走通用 `task:progress`（批粒度）；完成事件 `llm:translation_completed`（events 双侧登记）+ 复用 `llm:token_usage`；完成后自动切到新轨（`activeListTrackId`，3.0.3 列表轨感知使体验闭环）。

**边界**：完成后刷新走 task:completed 剥离 → `get_project`（同纠错模式）；`llm:translation_progress` 逐批流式预览登记为后续增强，不入版。编辑态中的自动切轨组合行为（R3.1 编辑态跨轨延续 × 本条自动切轨）：两裁决均照常生效，组合结果 = 新译文轨直接进入扫掠校对态（恰服务 US-T3-2 校对流）；beta.1 真机若反馈突兀再加门控（SPEC 裁决）。

**验收**：事件双侧登记一致；完成后列表直接显示译文轨；undo 恢复现场三层一致（tracks/bindings/列表视图回退）。

---

## 3. S2：AI 纠错感知当前轨（主项）

裁决依据（探索报告 §3.2）：删除类 AI（smart_delete/highlight）产出 EditDecision 驱动**主轨剪辑契约**，AnalysisData 无 per-track 槽位；纠错是唯一「纯文本、不动时间轴、不进剪辑模型」的 AI，副轨 text 写回通道已就绪已测——**只开纠错，其余 AI 不开放**。

### R2.1 任务轨道参数与段源（后端）

**需求**：`start_subtitle_correction` payload 增 `track_id: str = ""`（默认空 = 主轨，既有调用零影响）；handler 在 track_id 非空时段源取对应 `tl.transcript.tracks`；**confirmed-deleted 主轨段对应的绑定副轨段跳过**（语义对齐导出映射）；partial hints 与 confirmed-deleted 过滤是主轨 EditDecision 概念，副轨路径默认跳过（改为主轨删除映射上下文的成本收益 SPEC 定）。

**边界**：智能删除 / 精华 / 工作流 / 语义搜索一律不开放副轨（§0.2 不做）；`export_subtitle` 的 track-aware payload 先例（仓库唯一）为本次范式。

**验收**：track_id 缺省时主轨行为与 v3.0.3 完全一致（既有测试不改断言全绿）；副轨段源不含已删除主轨段的绑定段。

### R2.2 pending 作用域化（后端，本项最高风险）

**需求**：`store_subtitle_corrections` 的 pending 互清从 timeline 级改为 **track 作用域**（按 (timeline, track_id)，空 = 主轨）：主轨审阅中启动副轨纠错**不得**清掉主轨待审集，反之亦然；AnalysisResult 不加模型字段，track 归属记 detail JSON；`get_subtitle_corrections` 输出附 track_id（审阅列表标注来源轨）。

**边界**：兼容规则——detail 无 track_id 的存量结果按主轨（""）作用域处理，`test_store_clears_previous_corrections`（主轨两次 store 计数 2 非 4）等既有断言零改动通过；副轨被 `delete_track` 时其 pending 纠错随轨失效（get 列表过滤悬空 track_id）。

**验收**：双轨各自 pending 互不干扰（新用例）；主轨回归序列既有断言全绿；审阅条目标注来源轨。

### R2.3 accept/reject 轨道感知与 patch 化（含清债 #14）

**需求**：accept 在 track 段上复用 `_assert_timestamps_unchanged` + `reattach_words`，写回 `track.model_copy(update={"segments"})` → 返回 **`_success_patch(tracks=…, analysis=…)`**（**Round 2 must-fix 勘误**：初版写 `tracks=…, bindings=…` 错层——accept 只改段 text 并移除 AnalysisResult，**不动 bindings**（text 无几何语义）、**必带 analysis**（漏层则 patch 应用后前端审阅列表与后端脱节）；主轨路径 patch 层 = `segments + analysis`）。**顺带修复既有缺口（登记表 #14）**：① accept 返回值升级为**超集**——保留既有 `segment_id` 键、新增 `patch` 键（`test_subtitle_correction_review.py:157` 断言 `res["data"]["segment_id"]` 零改动兼容），前端检测 `patch` 走 `applyProjectPatch`，替换 O(project) 的 `switch_timeline` 全量刷新 workaround；**reject 同步超集**（Round 2 ★）——返回附 `patch`（层 = analysis，reject 只移除结果不动文本），前端可选消费；② accept 入 undo——**Round 2 must-fix 勘误**：主轨 accept 捕获层 `["segments","analysis"]`，副轨 accept 捕获层 `["tracks","analysis"]`（初版漏 analysis——accept 同时移除 AnalysisResult，漏层则 undo 只回滚文本、审阅条目不恢复，「undo 一次回退 accept」验收必挂；analysis 为合法 undo 层），主轨副轨同规则，消除两套行为；③ **accept/reject 时间轴钉扎**（Round 3 ★）：store 时 detail JSON 写入 `timeline_id` 键，accept/reject 时该键非空且 ≠ 当前 active_timeline_id → 明确报错零写入（防审阅期间切时间轴的跨轨错写）；存量 detail 无该键缺省放行。

**边界**：副轨段多来自 SRT 导入/翻译生成、无 words——`reattach_words` 空输入跳过 reattach 并用例固化；`accept_high_confidence_corrections` 与 `clear_subtitle_corrections` **保持 timeline 级语义不动**（Round 2 suggest #13：既有行为，副轨审阅用逐条 accept/reject 即可；track 作用域化登记 3.0.5 可选项，§10.2）。

**验收**：accept 后前端走 applyProjectPatch（revision 单调递增）；undo 一次回退 accept；大工程下接受单条不再全量刷新。

### R2.4 前端门控与审阅（前端）

**需求**：`useLlmTasks.startSubtitleCorrection` 传 `activeListTrackId`；**轨模式下 AI 面板只亮纠错卡**——智能删除/精华/工作流置灰，纠错卡附显式轨徽标注明作用轨（锁定当前轨，不弹轨选择）；审阅 modal 按 track_id 解析显示段与时间（renderDiff 纯文本渲染不变）。

**边界**：主轨视图下面板与 v3.0.3 完全一致（超集原则：仅副轨视图加门控）；门控实现层（AIAssistantPanel prop vs WorkspacePage 拦截）SPEC 定。

**验收**：副轨视图下不可触发删除类 AI；轨徽标名称正确；主轨视图零回退。

### R2.5 可选增强：对齐主轨上下文

**需求**：副轨纠错时经 bindings 把主轨对齐文本附进 LLM 上下文（`_build_structured_user_message` 的 extra_context 既有通路）。

**边界**：无绑定的副轨段自动退化为无上下文；纯后端，前端零改动；SPEC 可裁后置（S4 排期紧张时最后让位）。

**验收**：有绑定段的请求上下文包含主轨对齐行；无绑定段正常出结果。

---

## 4. S3：前端顺带批（T1 方案 A + X1 + X2）

### R3.1 编辑扫掠覆盖副轨（T1 方案 A，裁决反转）

**需求**：去掉 `TranscriptRow.vue:327-337` 两处 track 早退（onMounted + watch）——副轨行随 `globalEditMode` 进入/退出行内编辑，退出 = 批量保存（保存路径已按 variant 分流，无需改）；同步**反转**固化对立断言的测试（`TranscriptRow.test.ts:270-276`，列入 §1.3 白名单）；补两条断言：按钮开启后副轨行进编辑、切换轨视图前未决防抖先 flush（flush-on-switch 机制已有）。

**裁决反转理由**：3.0.3 M1-3 把副轨行限定为双击/右键单项入口，是当时列表轨感知初版的保守面；一版实际使用后，用户直接反馈该豁免表现为「按钮坏了」（US-T1-1），且编辑通路（useTrackEdit 内核 + 撤销谓词）已全部就绪——豁免不再有成本理由。

**边界**：仅列表侧；波形侧一致性（方案 B）不入版（§6-Q2）；主轨路径 diff 为零（改动全在 `isTrackVariant` 分支内）；v-memo 依赖数组已含 `globalEditMode` 与 `isTrackMode`，无需改。**Q1 裁决落点**：按钮文案感知轨道视图（副轨视图下显示「编辑〈轨名〉」）；编辑态跨轨保持（`globalEditMode` 不随轨切换重置——US-T2-2）。

**验收**：副轨视图下按钮一键进入/退出全列编辑；切换轨视图草稿先 flush 无丢失；主轨既有断言全绿。

### R3.2 lane 建段接线（X1）

**需求**：接通 41a1ac4 声称但从未接通的链路（下游 `handleTrackCreate` 至今孤儿）——三处接线：① WaveformEditor 向 TrackLane 传 `:build-mode`（basic 直挂 + multi 经 WaveformRow 两路）；② WaveformRow `createAtInTrack` 透传；③ WaveformEditor 模板补 `@create-at → emit("track-create")` 桥。补 1 条 vitest（建段模式 lane 点击 → track-create 上抛）。

**边界**：仅接线 + 测试，不改 TrackLane 与 handler 既有逻辑；不借此做 lane 形态范围标记（§6-Q12）。

**验收**：建段模式下点击副轨 lane 空白建段且 toast 可见（原提交描述首次兑现）；basic/multi 两模式均通。

### R3.3 语义搜索轨模式错位修正（X2）

**需求**：SemanticSearchBar（挂点勘误：**内嵌于 AIAssistantPanel.vue:716**，非探索报告所引 Timeline:729 直挂）显示侧 segmentMap 数据源修正——轨模式下改用主轨 segments 建 map（后端 `semantic_search` 恒搜主轨，显示侧与执行侧对齐）。实现（Round 2 suggest #10）= 复用 R1.4 交付的 **mainSegments 透传链**延伸一级：SemanticSearchBar 新增 `mainSegments` prop，map 改建自 `props.mainSegments ?? props.segments`——该链 **P1 先行交付**（翻译卡置灰判定同源需要），本项 P3 延伸到搜索栏；主轨模式两值相同零变化。

**边界**：不扩展 `semantic_search` 为 track 维度（§0.2 不做）；后端零改动，修显示侧对齐即可；主轨模式零变化（不传 mainSegments 时行为与 v3.0.3 一致）。

**验收**：轨模式下搜索结果文本/时间正确显示、点击定位到主轨命中段（vitest 新建宿主 `SemanticSearchBar.test.ts`）；主轨模式零变化。

---

## 5. S4：手动剪辑范围（T4a 方案 C+B）

方案依据（探索报告 §5.3）：range 型 EditDecision 是唯一被导出消费的范围载体（`_get_confirmed_deletions` 不过滤 target_type），模型/持久化/patch/undo/导出/波形覆层全部现成，缺的只是前端 0 入口。**方案 C（range 第一公民 UI）为主 + 方案 B（波形「范围标记」toggle 框选/时间码作为创建手势——Round 2 改判载体，见 R4.2）合并实施**。

### R4.1 add_range_decision（后端 expose）

**需求**：新 expose `add_range_decision(start, end, action, source="manual")`：push `EditDecision(target_type="range", status=pending, action=delete|keep)`；时间参数 clamp 到媒体时长（media 缺失取主轨段 end 上界，空段先拒）。**去重语义（Round 2 suggest #12 定稿）**：与 subtitle_trim 生成侧（project_service.py:2614-2620）**同阈值同判据**——存在既有 edit 满足**同 action** 且 `|Δstart|<0.05 且 |Δend|<0.05`（任意 status）→ **幂等返回既有 edit**（`duplicate: True` 标记，防抖双击/重复提交不产重复条目）；**跨 action（delete vs keep）重叠放行**（keep 的存在意义就是打穿 delete 区间，见 R4.4）；其余任意宽度重叠的非近似区间均放行（范围重叠是合法状态，由 R4.4 计算语义消解）。id 用 **uuid**（`edit-manual-{uuid}`——防历史删除后撞号；subtitle_trim 序号 id 依赖整体重生成，不适用手动增量）；status 默认 **pending**（区别于 subtitle_trim 的 confirmed-at-creation——自动裁剪确定性可重生成，手动范围需人工审阅）。补用户级生命周期闭环用例（建→审→确认→导出裁剪→单条清除——探索报告 §5.4 测试缺口 #4）。

**边界**：range 编辑（target_id=None）不会被 update_transcript 孤儿清理误删（project_service.py:560-563 已验证）；模型/patch/导出零改动；主轨语义零改动。

**验收**：全生命周期用例绿；确认后导出预览包含该区间（与 subtitle_trim 自动范围并列去重）。

### R4.2 创建手势（方案 B 作为 C 的输入）

**需求**：① 波形新增**「范围标记」工具栏 toggle**（对齐建段模式先例 WaveformEditor.vue:1012-1017），**默认 OFF**——ON 时主轨空白区 press-drag 框选 → 确认气泡（删除/保留二选 + 取消）→ `add_range_decision`；OFF 时一切如旧（超集原则默认关零回退）；`selectedRange` 死代码激活为气泡数据源。**Round 2 must-fix 改判**：初版「Shift-marquee 框选（激活死代码零成本）」与代码不符——死代码仅 `selectedRange` ref，Shift-drag 手势本体是 multi 模式**在用的跨行段多选手势**（WaveformEditor.vue:742-750），占用即主轨交互回退违红线 §1.4；Ctrl-drag（Ctrl-create 建段）同理被占。**Ctrl/Shift 优先级高于范围模式**（双 toggle 同 ON 时范围模式优先于建段模式，UI 互斥提示）。② 时间码精确创建（起止两个输入，口播场景精确范围）**并入建议面板常驻头部条**「+ 时间码」popover（SPEC 裁决落点 SuggestionPanel.vue:190-199；Round 4 勘误：不放「手动范围」分组头——分组受 push 空组守卫影响，无手动范围时连入口一起隐藏，头部条常驻、空工程也能建第一条）；两入口共用 `add_range_decision`。

**边界**：范围标记/建段模式两 toggle × Ctrl/Shift 既有手势在 basic 与 multi 下的手势矩阵表 SPEC M4-2 定并逐格 vitest（ON 6 格 + OFF 3 格零回退断言）；范围标记仅主轨域（副轨 lane 不参与）；不引入新 track role（方案 A 不做）。

**验收**：toggle ON 框选 → 气泡 → 决策落盘 → 波形覆层即刻可见（pending 样式）；toggle OFF 一切如旧（零回退断言）；Ctrl-create 建段与 Shift 段多选行为与 v3.0.3 完全一致；时间码入口创建成功且非法输入（end≤start）被拒。

### R4.3 建议面板「手动范围」分组与覆层

**需求**：SuggestionPanel 新增「手动范围」分组（与静音/智能删除两源并列）：逐条确认/拒绝/删除，**确认操作文案显式「确认 = 参与裁剪计算」**（keep 类条目尤其需明示——用户须知道确认 keep 不是导出动作而是计算参与，见 R4.4 消费边界）；**覆层 action/status 感知（Round 2 ★ 补，keep 完整闭环必要改动点）**：现状 `visibleEditRanges` 只过滤 target_type、不过滤 action——keep 会渲染成红色删除纹（误导）、pending 与 confirmed 同样式（无法区分），改为三态：confirmed delete = 现状红色斜纹**逐字节不变**、pending = 同款半透明（opacity 降档）、keep（任意 status）= 蓝色系斜纹/描边（不用红）；**deleteRanges 裁决（Round 2 ★）**：pending 手动范围**不入** deleteRanges（跳播/进度条红罩/导出预览）——现状过滤（confirmed OR subtitle_trim）天然排除 pending，**零改动**，补 1 条快照锁定用例；撤销 `pushSnapshot(["edits"])`（全链现成）。

**边界**：默认 action=delete（§6-Q9）；source 固定 `"manual"` 作分组过滤键，自由备注不做（字段冻结）；静音/智能删除分组不受影响。

**验收**：手动范围生命周期闭环可见；undo 一次回退建范围；既有两分组断言全绿。

### R4.4 keep 语义（2.x「撑住间隙」习惯的现代化）

**需求**：手动范围支持 `action="keep"`（EditDecision 数据层现成，零 schema 变更）；`generate_subtitle_keep_ranges` 的 keep 集合计算纳入用户 confirmed keep range——keep 区间从自动裁剪生成的删除区间中扣除，即「保住一段不被自动裁剪剪掉」（2.x 占位块习惯的现代化等价，探索报告 §5.3-4）。**消费边界裁决（Round 2 ★ 定稿）**：keep **仅影响 `generate_subtitle_keep_ranges` 的删除区间计算，不参与导出消费**——导出端 `_get_confirmed_deletions` 只认 confirmed delete，keep 进导出需发明「从删除区间扣除」新语义、且与段级删除（target_type=segment）相交时语义无法自洽（用户已确认删的段被 keep「复活」是矛盾操作）；keep 与手动 delete range 并存时**导出服从 delete**（手动决策优先于 keep 标记，显式文档化）。

**keep 完整闭环的三点成本（Round 2 量化，本 PRD 裁决全吸收，见 §6-Q10）**：(a) 覆层 action/status 感知三态样式（R4.3——否则 keep 渲染成红色删除纹）；(b) **重跑自动裁剪后的陈旧区间剔除**——keep 生成时既有的 `source="subtitle_trim"` delete 区间与任一 confirmed keep 相交 → 从 edits 移除（计数入返回 data `invalidated_count`），不做则旧红纹不失效、「keep 覆盖区间不被删除」验收在重跑场景必挂；(c) 确认面板文案「确认 = 参与裁剪计算」（R4.3——防用户把确认 keep 误解为导出动作）。

**边界**：keep 决策不参与导出消费（见上裁决）；无用户 keep range 的工程 subtitle_trim 行为与 v3.0.3 **逐字节一致**（golden 对拍基线**先于任何 :2560-2661 改动**采集，§7 顺序约束 1；该函数三版本 untouched、T4b 刚核销，本版唯一「改」点之一，diff 审查制重点审查项）；**R4.4 仍为 S4 首砍项**——砍则 keep 入口整体移除（气泡「保留」选项 + R4.3 覆层 keep 样式 + 本节全部），不降级为「可标不消费」的半吊子。

**验收**：keep range 覆盖区间不被自动裁剪删除（含重跑场景：相交陈旧 subtitle_trim 区间被剔除、`invalidated_count` 上报）；无 keep range 工程的 subtitle_trim 既有断言全绿 + golden 对拍逐字节一致；keep 与手动 delete 并存时导出含 delete 区间（优先级用例）。

---

## 6. 开放问题逐条裁决（探索报告 §8 全 15 条）

| 编号 | 问题（摘要） | 裁决 | 理由 |
|---|---|---|---|
| Q1 | T1 按钮是否感知轨道视图；编辑态是否跨轨保持 | 采纳建议：文案感知（「编辑〈轨名〉」）+ 编辑态跨轨延续（R3.1） | `globalEditMode` 本就是全局态，随轨切换重置反而制造新的不对称；US-T1-1/T1-2 |
| Q2 | T1-B 副轨块 trim 与 lane 菜单是否纳入编辑模式守卫 | **改判：不入本版**，登记版本池（3.0.5 候选） | 报告建议「纳入，可延后」；本版 S1-S4 已占满产能，且 trim 冻结语义需先裁决（行为收窄类改动），当前主/副不对称是既状非回归；与 X1/R3.2 同文件族，留 3.0.5 顺带成本更低 |
| Q3 | 副轨纠错是否跳过已删除主轨段的绑定副轨段 | 采纳建议：跳过（R2.1） | 语义对齐导出映射；confirmed-deleted 段不应产生译文/纠错噪声 |
| Q4 | 纠错入口锁定当前轨还是弹轨选择 | 采纳建议：锁定 + 显式轨徽标（R2.4） | 「切到副轨点纠错」是用户直觉路径；弹选择多一步且与锁定心智冲突；US-T2-1/T2-3 |
| Q5 | pending 纠错作用域与互清策略 | 采纳建议：track 作用域化（R2.2）；归属编码走 detail JSON 不加模型字段 | 报告 §3.4.1 列为最高风险；detail JSON 路径向后兼容且符合红线字段冻结（报告 §3.4.2 二选一的裁决） |
| Q6 | 翻译目标语言放全局设置还是任务入口 | 采纳建议：任务入口选择 + 记忆上次（config 持久化默认值，R1.1） | 全局设置入口过深；任务内联是最短路径；记忆免除重复选择 |
| Q7 | 已存在同语言翻译轨时重译策略 | 采纳建议：MVP 拒绝 + 提示清空/删轨（R1.3） | 自动合并/增量重译规模 L 且语义复杂；`clear_track_segments`/`delete_track` 已给用户手动出路 |
| Q8 | 级联删除/拆分重绑语义的用户沟通方式 | 裁决：建轨完成 toast 附注一句 + README 功能段说明（随 P4 回填），不做首启阻断弹窗 | 最轻量；动作发生在另一轨，tooltip 触达不足；阻断弹窗打扰主流程 |
| Q9 | 手动范围默认 action 与备注字段 | 采纳建议：默认 delete；备注仅 `source="manual"` 固定标记（R4.3） | 自由备注需加模型字段（红线冻结）；固定 source 足够支撑分组过滤 |
| Q10 | keep 语义（范围是否参与 keep-range/自动裁剪计算） | **PM 裁决定稿（Round 2 回落）：维持完整闭环，三点成本全吸收**——创建 + subtitle_trim keep 集合感知 + 覆层三态/陈旧剔除/确认文案（R4.4/R4.3），导出消费仍仅 delete；R4.4 保留 S4 首砍项标注 | 三点隐藏成本经架构师量化后均有界且 SPEC 已落改动点，合计约 0.5-1 天、已在 P3 复核区间（§7）内，不构成砍项理由；「撑间隙」是 2.x 习惯两分支中仅 keep 可覆盖者，砍则该诉求无载体；半吊子 keep 违背克制原则（要么完整要么整体不做）；排期挤压时按首砍项标注整体移除，不降级；**立项会确认（2026-09，修订-2 ②）：维持完整闭环定稿，首砍触发须四要素留痕** |
| Q11 | 圈选手势与入口偏好（Ctrl-drag / marquee / 时间码） | **改判（Round 2 must-fix）：「范围标记」工具栏 toggle（默认 OFF）+ 时间码 popover 两入口**；Ctrl/Shift 既有手势优先级高于范围模式（R4.2） | 初判「Shift-marquee 为只写不读死代码、激活零成本」与代码不符——手势本体是 multi 模式在用的跨行段多选手势（WaveformEditor.vue:742-750），占用即主轨回退违红线；toggle 对齐建段模式先例（:1012-1017）、默认 OFF 天然满足超集原则；时间码覆盖精确场景，落建议面板常驻头部条（SPEC，Round 4 勘误） |
| Q12 | 修复 X1 后范围标记是否做成 lane 形态 | 裁决：不做（R3.2 仅恢复副轨建段原意） | 方案 A 若用影子 edit 实现导出即退化为 C 的皮肤，纯增成本（探索报告 §5.3）；范围呈现走既有斜纹覆层 |
| Q13 | 2.x 遗留重叠段是否载入时一次性解交叠迁移 | 裁决：本版不做，登记观察项（触发 = 真实旧工程受阻塞反馈） | 迁移是不可逆数据改写，裁短策略需真实数据实例佐证；问题为 2.x 存量、非 3.0.4 引入；migrations.py 先例不构成充分理由 |
| Q14 | 红线重启幅度 | 采纳建议：「只增不改」折中案，§1 定稿措辞 | 探索报告 §7.2；S1/S2/S4 全部改动面与该约束兼容（本 PRD 已逐条核过）；版本池「需 schema 演进」两项仍不入——字段冻结下 schema 演进留 3.1.x |
| Q15 | 3.0.3 顺延双平台真机清单是否并入 beta 轮补验 | 采纳建议：并入 P4 真机清单（登记表 #17） | S4 恰新增建议面板分组，两笔视觉回归债天然合并补验；beta 轮逐批带真机 |

---

## 7. 交付计划与规模估计

```
P0（0.5 天）     分支 dev-3.0.4（自 tag v3.0.3 拉出）/ 基线核对 / 红线重启登记
                 （「后端改动登记表」建表）/ PRD-SPEC 定稿
P1（4.5-6 人日） S1 翻译管线（R1.2 管线 → R1.3 批量写 → R1.4 事件与前端）——
                 含 mainSegments / active-track-id props 链一次接通（顺序约束 2）
                 → v3.0.4-beta.1
P2（3-4 人日）   S2 纠错轨道感知（R2.1 后端 → R2.2/R2.3 → R2.4 前端；
                 R2.5 为 P2 尾项、维持既定让位线）→ v3.0.4-beta.2
P3（4-5.5 人日） S3 前端顺带批（纯前端，可与 P1 并行开发、合入走 P3 门禁）；
                 S4 手动范围（M4-3 面板/覆层可与 M4-1 expose 并行开发）
                 → v3.0.4-beta.3
P4（1-1.5 天）   门禁终检 / README_zh 回填 / 双平台真机清单（并入 3.0.3 顺延债）
                 → v3.0.4-RC → 正式
```

**总量与天数裁决（Round 3 执行者复核回落）**：逐触点复核人日区间 = **13-17.5 人日**（P1 4.5-6 / P2 3-4 / P3 4-5.5 / P0+P4 1.5-2；初估 8-12 系 P3 严重低估——S3+S4 实为 4-5.5 而非 1-2）。**PM 裁决 = 保全量、重报日历 12-15 天**：① 人日口径尊重复核值不做乐观折减（初估已被证低）；② 日历压缩 1-2.5 天有据——SPEC M0-3 明确允许 M3 纯前端与 P1 **并行开发**（合入仍走 P3 门禁）、M4-3 与 M4-1 并行、P0 前置与探索收尾部分重叠；③ 用户诉求四主题（T1 编辑扫掠 / T2 纠错感知 / T3 翻译副轨 / T4 手动范围）核心与全部入口面向保全；④ R2.5 维持既定让位线（S4 开工即砍）作为**超期第一缓冲阀**而非预先砍除——预砍省 0.5-1 天却永久损失副轨纠错质量（主轨参考稿降误判），性价比为负；⑤ 备选组合「砍 R2.5 + M4-2 时间码入口保 10-12 天」否决——时间码是口播精确范围的唯一数值入口且 SPEC 已定低成本落点（面板头部条 popover），砍之所省不足 1 天。**开工前置**：tag `v3.0.3` 已落地（含修订-1 重打），无阻塞。**立项会确认（2026-09，修订-2 ①）**：日历 12-15 天与超期决策树授权生效，决策树每次触发须四要素留痕（见 PLAN「立项会裁决登记」）。

**顺序约束（Round 3 执行者提出，与上图同为强制，细则 SPEC M0-3）**：

1. **golden 基线先行**：M4-4 keep-ranges golden 对拍基线必须**先于任何** `generate_subtitle_keep_ranges`（project_service.py:2560-2661）改动、于 v3.0.3 基线工作区采集固化，随 P3 首个 commit 入库——先改后采会让「基线」自带本版改动，对拍失去意义；
2. **props 链 P1 一次改动**：M1-6 `mainSegments` 与 M2-4 `active-track-id`/`active-track-name` 走同一条 WorkspacePage → Timeline → AIAssistantPanel 透传链，P1 一并接通，P2 只加门控消费——消除 P1/P2 两阶段对 Timeline.vue 同一区域的重复改动冲突窗口；
3. **X1 先于 S4 手势合入**：R3.2（lane 建段接线）先于 M4-2（范围标记手势）——同文件族（WaveformEditor/SegmentBlocksLayer）防冲突；
4. **M4-3 可与 M4-1 并行开发**：面板分组与覆层只消费 edits 数据流、不依赖 expose 落地顺序；「建→审→确认→删除」生命周期验收在 M4-1 合入后串行执行。

**规模估计**（口径对齐探索报告 §4.3「前端 X 行 / 后端 Y 行」，不含测试）：

| 项 | 后端净新增 | 前端净新增 | 测试增量（已对齐 SPEC M5 用例矩阵下限，Round 3 口径） |
|---|---|---|---|
| S1 翻译管线 | ~350-450 行（models 1 行 / prompts / llm_service / project_service 批量写 ~80-120 / main handler+expose ~100-150 / events / config） | ~200-300 行（入口卡片 + 对话框 + useLlmTasks + 完成切轨） | 后端 ≥23 用例（管线 ≥12 + 批量写 ≥6 + expose/事件 ≥5）；前端并入 M1/M2 前端组 |
| S2 纠错轨道感知 | ~150-250 行（5 个后端触点：payload/段源/store 作用域化/accept-get/上下文增强） | ~150-250 行（useLlmTasks + 门控 + 轨徽 + 审阅 modal + patch 消费） | 后端 ≥13 用例（作用域化 ≥6 + 段源/accept ≥7）+ 前端 ≥7（含新建宿主 `useWorkspaceActions.test.ts`） |
| S3 前端顺带批 | **0 行**（纯前端） | ~120-200 行（T1-A 极小 diff + X1 接线三处 + X2 一处） | 前端 ≥7 用例（含新建宿主 `SemanticSearchBar.test.ts`） |
| S4 手动范围 | ~60-120 行（1 expose + R4.4 keep 感知与陈旧剔除） | ~300-450 行（范围标记 toggle + 气泡 + 时间码 + 面板分组 + 覆层三态） | 后端 ≥10 用例（expose ≥6 + keep ≥4，含 golden 对拍）+ 前端 ≥9（含新建宿主 `SuggestionPanel.test.ts`） |
| **合计** | **~600-850 行** | **~800-1100 行** | **后端 ≥45 / 前端 ≥22 新用例（SPEC 规模注记口径）** |

总量约为 3.0.3（前端 600-1000 / 后端 0）的两倍、3.0.2 的三分之二量级。

---

## 8. 风险表

| 风险 | 等级 | 关键缓解 |
|---|---|---|
| S1 LLM 输出守恒与解析鲁棒性（json_mode 仅 OpenAI/DeepSeek；Qwen/GLM/Ollama 靠 4 层兜底，翻译要求全量输出） | 高 | coverage 反向校验失败批不落盘；非 json_mode 提供商专项 mock 测试；重试/串行降级复用纠错骨架 |
| S2 pending 互清作用域化回归（主轨待审集被误清/误留） | 高 | track 作用域 + 兼容规则（存量无 track_id 按主轨处理）；双轨互扰新用例 + 主轨既有断言零改动全绿（R2.2） |
| S4 触碰 subtitle_trim（三版本 untouched、T4b 刚核销） | 中 | 仅存在用户 keep range 时行为变化；golden 对拍基线先于改动采集（§7 顺序约束 1）；陈旧 trim 剔除 invalidated_count；R4.4 列 S4 首砍项；diff 审查制重点项 |
| S1 token 成本与耗时（全量译文 completion ≈ 输入规模；千条约 1-3 分钟） | 中 | 入口预估批数/token 提示；复用 `llm:token_usage`；TaskManager 全程可取消 |
| S1 批量写原子性（千段级落盘 + undo） | 中 | 批量写方法单 patch 落盘（revision +1）；前端 start 前 pushSnapshot；undo/redo 原子用例 |
| S1 翻译期间主轨编辑导致 id 配对落空 | 中 | 完成时按 id 对账，结果面板明示未覆盖清单（US-T3-4），不静默 |
| S1 级联删除用户误解（主轨删段 → 译文段消失） | 中 | 建轨完成 toast 附注 + README 说明（Q8）；1:1 语义下合理 |
| S2 accept patch 化触及既有主轨契约 | 低（已核证） | 超集方案：保留 `segment_id` 键新增 `patch` 键，`test_subtitle_correction_review.py:157` 既有断言零改动兼容 |
| S4 手势冲突（范围标记 toggle × 建段模式 × Ctrl/Shift 既有手势矩阵） | 中 | 范围标记默认 OFF；Ctrl/Shift 优先级高于范围模式；SPEC 手势矩阵逐格 vitest（ON 6 格 + OFF 3 格零回退断言）；Ctrl-create 语义零改动断言 |
| 红线重启失序（diff 审查制依赖纪律） | 中 | 「后端改动登记表」+ §9 固定检查命令每 phase 执行；白名单外断言改动视为违规 |
| 多行时间线视觉回归债（建议面板/红罩层，3.0.3 顺延） | 中 | 并入 P4 真机清单与 S4 新分组合并补验（Q15） |

---

## 9. 验收总纲

- **后端门禁**：`uv run pytest` ≥716 **只增不减**全绿（新增用例对齐 SPEC M5 用例矩阵——后端 ≥45：翻译守恒/部分失败/取消、批量写+绑定原子、expose 契约、pending 作用域化、add_range_decision 生命周期与去重、keep 感知与陈旧 trim 剔除（invalidated_count）、golden 对拍、reattach_words 空输入）；`uv run ruff check .` 0
- **前端门禁**：`cd frontend && bun run test` 全量 collected ≥756（755 基线 + 新增）且 passed ≥755+新增全绿——**唯一允许失败 = `useRowLayout.perf.test.ts` 挂载墙钟（3.0.3 已登记环境例，维持豁免）**；`bun run build`（vue-tsc --noEmit + vite build）通过；`bun run lint` 0
- **新红线检查命令**（替换「五文件 diff 为空」）：
  - `git diff v3.0.3 -- core/models.py` 增量仅含枚举成员/常量/注释，无既有字段或签名改动
  - events 双侧同步 = **本版新增事件名双侧存在性检查**（Round 2 suggest #7 精化口径；不做全量常量集比对——events.ts 含 2 个前端专属 demo 常量，全量比对误报）：`git diff v3.0.3 -- core/events.py | grep -E '^\+.*(LLM_TRANSLATION_COMPLETED|llm:translation_completed)'` 与 events.ts 侧同款命令各命中本版新增行
  - 后端断言零删改（Round 2 suggest #8 精化——原 `'^-.*assert'` 过宽命中注释/字符串）：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = 0
  - 前端断言白名单外零删改：`git diff v3.0.3 -- frontend/src | grep -E '^-[[:space:]]*expect\(' | grep -v 'TranscriptRow.test.ts' | wc -l` = 0（白名单外命中即 fail）
  - 后端 diff 文件集 ⊆ §1.5 白名单（终态以 SPEC M0-1 表为准）；全量后端 diff（`git diff v3.0.3 -- core/ main.py`）逐条对应「后端改动登记表」的 R 编号
- **主轨零回退**：主轨视图 / 无 track_id 调用 / 无手动 range 与 keep 数据的工程，v3.0.3 全部既有交互与测试断言不变（超集原则）
- **真机回归**（双平台，P4）：3.0.4 清单（翻译全链 + undo、纠错双轨 + 轨徽门控、编辑扫掠副轨、lane 建段、语义搜索、手动范围（范围标记 toggle / 时间码 / 面板 / keep 重跑场景））+ 3.0.3 顺延清单（建议面板/红罩层多行视觉回归）
- **文档链**：README_zh 3.0.x 功能段集中回填（含翻译轨级联语义，Q8）、record 逐步落盘（含断言反转白名单登记）、开发报告版本池注记回写（§10.2）

---

## 10. 遗留与版本池回写

### 10.1 本版顺带清债裁决

| 债项 | 裁决 |
|---|---|
| 副轨删除确认策略再评估（record-3.0.3 #2） | 入版为**再评估任务**非功能项：S1 交付后副轨数量与使用频率上升，P3/P4 依真机观察裁决——默认维持「无确认框 + undo 兜底」（3.0.2 裁决），仅当误删率证据出现才加确认 |
| README_zh 功能段回填（record-3.0.3 #4） | 入版，P4 文档轮：3.0.x 特性段落集中回填 + 3.0.4 新特性（翻译/纠错轨道/手动范围）+ 翻译轨级联删除语义说明（Q8） |
| T2 附带修复：accept patch 化 + accept 入 undo（探索报告 §7.4） | 入版，并入 R2.3（超集方案，主轨/副轨同规则） |
| 挂载墙钟 perf gate 根修（record-3.0.3 #5） | 不入版：维持环境例豁免口径（§9）；根修方案（改造/拆分该用例）登记清债池，是否 3.0.5 处理待用户指示 |
| 谓词表第 4 行测试深化（record-3.0.3 #3） | 不入版，登记维持 |

### 10.2 版本池回写（开发报告版本池注记）

- **新增登记**：T1 方案 B 波形侧编辑模式一致性收口（含 trim 冻结语义裁决，3.0.5 候选，与 X1 接线同文件族）；2.x 重叠段解交叠载入迁移（观察项，触发 = 真实旧工程受阻塞反馈）；翻译增量补译入口（ledger.uncovered）；`llm:translation_progress` 逐批流式预览；**定稿译文滑动窗**（与并发 5 互斥，需串行模式/config 开关——R1.2 Round 2 改判随项）；**`accept_high_confidence_corrections` / `clear_subtitle_corrections` 的 track 作用域化**（本版维持 timeline 级语义——R2.3 边界，Round 2 suggest #13）
- **维持原样**：桥断连警示 / 点击字幕三模式 / 撤销恢复选区+视图 / 工作区预设（布局随工程走）/ 行设置随工程走 / 二分切片 / 手工 DOM 行保留——其中「需 schema 演进」两项（工作区预设、行设置随工程）**不因红线重启入版**：「只增不改」仍冻结既有模型字段，schema 演进留 3.1.x 专门重启（§6-Q14）
- **出池**：翻译管线（3.0.1 PRD:54 暂缓项 → 本版 S1 交付）

### 10.3 record 落盘要求

- 断言反转白名单（R3.1 的 TranscriptRow.test.ts 反转）在 P3 record 中登记反转条目与理由；
- 「后端改动登记表」由 SPEC 建表、每 phase record 追加，P4 终检逐条核对（§9）；
- T4b 核销结论（静音/裁剪链路未破坏）随本版文档链归档，测试缺口 #4 由 R4.1 用例覆盖，其余缺口（detect_silence 本体、端到端串测、padding=0 交叠交互、basic 空白点击建重叠段）移交 3.0.5 测试规划。

---

## 11. 修订记录

- **修订-2（2026-09，立项会结论回填——四项用户裁决留痕）**：
  - **① 日历与决策树**：用户同意日历 12-15 天（人日 13-17.5 不折减）与超期决策树授权（R2.5 → R4.4 keep → S4 剩余版本池化）；**约束：决策树每次触发必须留痕**（日期 / 触发信号 / 裁决与影响面 R 编号级 / 回写文档处四要素，登记于 PLAN「立项会裁决登记」表 + record-3.0.4.md，见 PLAN 里程碑与缓冲节）。
  - **② Q10 keep**：用户确认维持完整闭环（三点成本全吸收，§6-Q10 / R4.4）；R4.4 首砍缓冲阀授权同上留痕要求——触发即整体移除并按四要素登记，不降级。
  - **③ 副轨删除确认策略**：用户确认默认值 = 无确认框 + undo 兜底（§10.1 观察项维持，真机误删证据出现再议）。
  - **④ 里程碑绝对日期**：不强制限制——维持相对日程（D+n），触发式回填，不作门禁项（PLAN 里程碑表已改）。
- **修订-1（2026-09，架构师 Round 2/4 + 执行者 Round 3 评审结论回落；已与 SPEC v3.0.4 终态对齐，冲突处按 SPEC 回写）**：
  - **must-fix 6 条**：① §1.5 后端白名单补 `core/correction_service.py`（R2.2/R2.3 全部改动所在）并显式列 `config.py`/`llm_prompts.py`/`llm_service.py`（S1 只增触点），§1.4 受控「改」落点同步改为三处；② Q11/R4.2① 手势改判——Shift-marquee 系 multi 模式在用段多选手势（WaveformEditor.vue:742-750），改「范围标记」toggle 默认 OFF（对齐建段先例 :1012-1017），Ctrl/Shift 优先级高于范围模式；③ R1.2 内部矛盾修正——并发 5 与定稿译文滑动窗互斥（payload 预构建），裁「并发 + 源文 ±ctx 窗口」，滑动窗登记版本池；④ R2.3 accept patch 层勘误——主轨 segments+analysis / 副轨 tracks+analysis（原 tracks+bindings 错层：accept 不动 bindings、必带 analysis）；⑤ R2.3② undo 捕获层补 analysis（`["segments","analysis"]` / `["tracks","analysis"]`）；⑥ Q10 keep 三点成本裁决 = **维持完整闭环全吸收**（覆层三态 / 陈旧 trim 剔除 invalidated_count / 确认文案，理由见 Q10 行），R4.4 保留首砍项标注。
  - **suggest 7 条同步措辞**：⑦ 事件门禁口径 = 本版新增事件名双侧存在性（§1.2/§9）；⑧ 断言检查命令精化（§9）；⑨ prompt `params={}` 穿透 + handler 终替换 + 残留 fail-fast（R1.2）；⑩ X2 挂点勘误（AIAssistantPanel.vue:716 内嵌）+ mainSegments 链 P1 先交付、P3 延伸（R1.4/R3.3）；⑪ 时间码入口并入建议面板常驻头部条（R4.2②，Round 4 勘误避开分组空组守卫）；⑫ R4.1 去重语义定稿（±0.05s 同阈同判据 / 同 action 幂等 / 跨 action 放行 / uuid / 默认 pending）；⑬ accept_high_confidence 与 clear 维持 timeline 级（R2.3 边界，3.0.5 登记）。
  - **Round 3 天数与顺序**：§7 交付计划重排——人日 13-17.5（P1 4.5-6 / P2 3-4 / P3 4-5.5 / P0+P4 1.5-2）+ PM 裁决日历 12-15 天保全量（R2.5 让位线为超期缓冲阀，备选砍 R2.5+时间码组合否决）；4 条顺序约束（golden 先行 / props 链 P1 合并 / X1 先于 S4 手势 / M4-3∥M4-1）并入 §7；§7 规模估计测试增量列对齐 SPEC M5 用例矩阵（后端 ≥45 / 前端 ≥22，含三处新建测试宿主）。
  - **SPEC 附录 C ★ 项回写**：R1.1 预估批数放宽「量级一致」（R1.1 验收）；翻译同语言轨双保险拒绝（R1.3 边界）；R2.3 reject 同步超集 + accept/reject 时间轴钉扎（detail 增 `timeline_id` 键）；R4.3 覆层 action/status 感知三态 + deleteRanges 不含 pending（零改动 + 快照锁定用例）；R4.4 keep 消费边界 = 仅 subtitle_trim 计算 + 陈旧剔除 invalidated_count。
- **初版**（2026-09）：立项定稿（探索报告取证 + 15 问全裁决）。

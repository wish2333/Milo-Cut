# Milo-Cut v3.0.5 需求文档（PRD）

> 版本：3.0.5（立项定稿——2026-09；立项会三裁决已回填；修订-1：架构师 R2/R4 + 执行者 R3 评审结论已回写，见 §11 修订记录）
> 主题：**失败路径残值回收 + 批量审阅信任收口** —— F1 数据安全防呆（首项）、翻译失败成本三件套（T-5.1）、批量审阅收口（T-5.2）、纠错取消对齐（T-5.3）、keep 可感知收口（S3）、波形编辑模式一致性（S4）、质量模式开关（S5）六主项 + P 组顺带批与 D3 顺手根修
> 基线：v3.0.4（tag `v3.0.4`，3.0.x 首次回并主干后的当前发布态；门禁 diff 基准恒为 `v3.0.4`）
> 日期：2026-09
> 依据：[研究报告 v3.0.5](./研究报告-v3.0.5.md)（§3 问题清单 / §4 候选池 25 编号 / §5 延后设计 / §6 用户故事 US-01~11 / §7 开放问题 Q1-Q8 / §8 范围草案）· [用户反馈 A](./用户反馈-A.md) / [用户反馈 B](./用户反馈-B.md)（行为断言证据源，结论全部带 文件:行号，汇总者抽验 8/8 属实；本 PRD 关键锚点已二次复核）· [record-3.0.4](../3.0.4/record-3.0.4.md) §7 版本池 / §8 遗留清单 · [PRD v3.0.4](../3.0.4/PRD-v3.0.4.md)（结构模板与红线先例）
> 角色：产品经理

---

## 0. 版本定位

3.0.4 把「副轨内容智能化 + 手动剪辑范围回归」的骨架交付达标（研究报告 §2 双人共识：交付质量最高段 = 副轨纠错闭环；翻译 undo 三层一致、keep 数据闭环、smoke-fix 八项修复经代码求证全部成立）。3.0.5 **不再开新能力面**，主题收敛为把 3.0.4 已建立的功能从「能用」收口到「敢用」，用户价值集中在三类：

1. **失败路径的残值回收**（T-5.1）：非 json_mode 提供商（Qwen/GLM/Ollama）1/34 批解析失败 = 全量零落盘 100% 重烧；失败/取消后连「白烧了多少 token」都不可见；行级解析兜底缺 translated_text 模式（研究报告 §3 F2/F3）。失败账单（F2）+ 行级兜底（F3）+ 增量补译（S1）是同一件事的三半——「敢在大工程上点开始翻译」（用户 A Top1）。
2. **批量路径的作用域收口**（T-5.2）：逐条 accept/reject 已 patch 化 + 按轨隔离，但「信任全部高置信度/清除全部」仍是 timeline 级无差别扫射且批量接受不进 undo（S2）——修的不是功能缺口，而是 3.0.4 刚建立的「按轨隔离」信任。
3. **新习惯的可感知收口与双标消除**：keep 闭环「功能已通、信任未通」三要点（S3）；纠错取消延迟与翻译侧双标（T-5.3）；波形/列表编辑模式规则割裂（S4）；术语一致性诉求的可选串行（S5）。

另有一颗**已发布的数据安全级缺陷**（F1：duplicate 幂等返回把前端工程对象整体替换成假对象）经立项会裁决①并入本版**首项**，v3.0.4 不出补丁（理由与裁决留痕见 §4-Q1、§11）。

### 0.1 立项来源登记表（研究报告 §4 候选池全 25 编号）

| 编号 | 项 | 登记出处 | 本版裁决 |
|---|---|---|---|
| F1 | duplicate 幂等返回防呆（含 undo 空步与 duplicate 态测试缺口） | 本轮新发现（B，双向独立复核确认） | **入版，首项 R5.0**（裁决①：并入 3.0.5，v3.0.4 不出补丁） |
| F2 | 翻译失败/取消 token+ledger 上报、取消中性提示、429 降级信号透出 | 本轮新发现（A，F-A-01/02/03） | **入版，主项 T-5.1（R5.1）** |
| F3 | 行级解析兜底补 translated_text 模式 + 失败中文出路指引 | 本轮新发现（A，F-A-10） | **入版，主项 T-5.1（R5.2）** |
| F4 | 纠错管线取消延迟修复（复刻翻译侧轮询 + 非阻塞 shutdown） | record-3.0.4 §8.1 #1 | **入版，主项 T-5.3（R5.5）**——§8.1 首项出池 |
| S1 | 翻译增量补译入口（缺口只重跑 + 单 patch 合并 + uncovered 对账可读化） | 版本池（M1-2 边界随项） | **入版，主项 T-5.1（R5.3）**——版本池出池 |
| S2 | accept_high/clear 轨作用域化 + 批量接受入 undo + 确认文案作用范围 | record §8.1 #2 + F-A-05/06 | **入版，主项 T-5.2（R5.4）**——版本池出池；D7 第三项（handleAcceptHighConfidence patch 化）同函数族顺带 |
| S3 | keep 闭环可感知收口（确认文案直显 + invalidated_count toast + 红蓝并存提示） | 本轮新发现（B，F-B-02/03/07） | **入版，升格主项（R5.6）**，按 US-05 三要点全验（裁决②） |
| S4 | T1 方案 B 波形侧编辑模式一致性收口（trim/菜单守卫） | 版本池（PRD-v3.0.4 §6-Q2 改判随项） | **入版，升格主项（R5.7）**——trim 冻结语义矩阵本 PRD §6 完整定稿（裁决②）；版本池出池 |
| S5 | 质量模式开关（串行 + 定稿译文滑动窗） | 版本池（R1.2 改判随项）+ R-A-05 | **入版，升格主项（R5.8）**，config 默认关，与 S1 合并设计、补译可组合串行（裁决②）；版本池出池 |
| S6 | 手动范围自由备注 | 本轮新诉求（B，R-B-02）；受字段冻结红线限制 | **不入版**（裁决③）：登记 3.1.x schema 演进首发候选；研究报告 §5.2 两案对比与降级诉求随 §10 登记 |
| P1 | 文案收口批（Timeline 英文 tooltip / 覆层 title 中文化语义化 / 重译显示名 / 取消中性提示归 R5.1） | record §8.1 #4 + F-B-09 + F-A-07 前半 | **入版，顺带批（R5.9）** |
| P2 | 覆层三态语义诚实（rejected 弱化 / 建段降档 / 气泡 Esc 与点外消泡） | 新发现（B，F-B-04/05/08） | **入版，顺带批（R5.10）** |
| P3 | 审阅体验批（按轨过滤 / 启动不清列表 / 时间码 mm:ss·播放头·clamp 回显·成功 toast） | 新发现（A F-A-08 + B F-B-06） | **入版，顺带批（R5.11）** |
| P4 | aligned_main_text 系统 prompt 语义说明 | record §8.1 #5（P2-6 预登记） | **入版，顺带批（R5.12）**——Q8 裁决豁免观察前提 |
| P5 | 翻译入口 token 量级预估（「约 N 批 · 约 X 万 token」） | PRD-v3.0.4 R1.1 承诺收窄的补课（F-A-09） | **入版，顺带批（R5.13）** |
| P6 | 重译拒绝路径顺滑（列表轨选择器补清空/删除入口或指引） | 新发现（A，F-A-07） | **入版，顺带批（R5.14）**，与 P1 显示名半条合并施工 |
| P7 | 副轨删除 toast 提示「可撤销」（维持无确认框默认值） | record §7.1 观察项善后 + A/B 共识 | **入版，顺带批（R5.15）**；「无确认框 + undo 兜底」裁决维持不变 |
| D1 | SuggestionPanel provide/inject 键类型化（InjectionKey） | record §8.1 #3（P3-7 登记） | 不入版，维持登记；R5.11 若改 SuggestionPanel 接线则顺带（SPEC 定） |
| D2 | 悬空 pending 纠错物理清理 | record §8.1 #6（P2-3 登记） | 不入版，维持登记（存储卫生项；get 过滤行为已符合直觉） |
| D3 | useRowLayout.perf 环境例根修 | record §8.1 #7（清债池维持） | **入版，顺带批（R5.16）**：任一前端 phase 顺手根修，销掉每版门禁注记 |
| D4 | T4b 其余测试缺口（detect_silence 本体/端到端串测/padding=0 交叠/basic 空白点击建重叠段） | record §8.1 #8（PRD-v3.0.4 §10.3 移交） | **入版本版测试规划（§7.4），不占产品主题** |
| D5 | MiloCutApi 级写锁 | spec-v3.0.4 M1-5（review-log R3 must-fix #9） | 不入版，维持登记；死锁面延后设计要点见研究报告 §5.4（§10.2 引用） |
| D6 | 2.x 重叠段解交叠载入迁移 | 版本池（观察项） | 不入版，维持观察（触发 = 真实旧工程受阻塞反馈，未出现） |
| D7 | 散落四小项（accept/reject 失败 toast / watch 双取收敛 / handleAcceptHighConfidence patch 化 / correctionTrackName 类型源） | record-3.0.4-P2-4 §7 / P2-5 §7 | 第三项**随 S2 入版**（R5.4）；其余三项维持登记，R5.11 触及同面时顺带评估 |
| D8 | 版本池维持项（桥断连警示/点击字幕三模式/撤销恢复选区+视图/工作区预设/行设置随工程/二分切片/手工 DOM 行保留） | record §7 | 维持原样；其中四项本版出池（见 §10.1），「需 schema 演进」两项仍冻结至 3.1.x |

### 0.2 用户反馈逐条裁决（研究报告 §3：双人共报 20 条，去重后 19 条独立问题，按归组重编）

| 汇总编号 | 原始反馈编号 | 裁决去向 |
|---|---|---|
| F1 | F-B-01 + F-B-10（同源合并） | R5.0（首项） |
| F2 | F-A-01 + F-A-03 | R5.1 |
| F3 | F-A-10 | R5.2 |
| F4 | record §8.1 #1 | R5.5 |
| F5 | F-A-02（429 降级信号） | R5.1（与 F2 同面交付） |
| P1 | record §8.1 #4 + F-B-09 + F-A-07 前半 | R5.9（取消提示半条归 R5.1） |
| P2 | F-B-04 / F-B-05 / F-B-08 | R5.10 |
| P3 | F-A-08 + F-B-06 | R5.11 |
| P4 | record §8.1 #5 | R5.12（Q8 豁免观察前提） |
| P5 | F-A-09 | R5.13 |
| P6 | F-A-07 | R5.14 |
| P7 | record §7.1 善后 + A/B 共识 | R5.15 |
| S1 相关 | F-A-04（uncovered 对账不可读） | R5.3（US-10） |
| S2 相关 | F-A-05 + F-A-06 | R5.4 |
| S3 相关 | F-B-02 + F-B-03 + F-B-07 | R5.6（US-05 三要点全验） |
| D5 相关 | F-A J9 附带（api_key 必填对本地部署不友好） | 不入版，随 D5 维持登记；若 P5 触及模型设置文案可顺带一条提示（SPEC 定） |

### 0.3 范围裁决

**做**：F1 首项（R5.0）；T-5.1 翻译失败成本三件套（R5.1 + R5.2 + R5.3）；T-5.2 批量审阅收口（R5.4，含 D7 第三项）；T-5.3 纠错取消对齐（R5.5）；S3 keep 可感知收口（R5.6）；S4 T1 方案 B（R5.7，前置 trim 矩阵 §6 定稿）；S5 质量模式（R5.8）；顺带批 R5.9-R5.16（P1-P7 + D3）+ D4 并入测试规划（§7.4）。

**不做**（沿承裁决或本版新裁，均注出处）：S6 手动范围备注（裁决③，3.1.x schema 首发）；S6 的 detail JSON 过渡案（研究报告 §5.2，与 AnalysisResult 模型语义错位，无架构师确认不做）；D1/D2/D5/D6/D7 其余三项/D8 余项（维持登记）；`llm:translation_progress` 逐批流式预览（研究报告 §5.5，R5.3 交付后可顺带评估补译进度，本版不做）；workflow_engine 纳入翻译/纠错 step（3.0.4 先例延续）；主轨既有行为、主轨视图交互的任何变更（超集原则，红线 §1.4）。

**MVP 约束**：S1 补译不加模型字段、不加新 expose 入口（复用 `start_translation` 自动路由，§4-N1）；S5 质量模式仅一条 config 布尔键（§4-N4），不新增任务类型（复用 `llm_translation`）；S2 两个批量函数以可选形参 `track_id: str | None = None` 三态扩展、默认 None 保持既有 timeline 级语义（既有断言零改动；三态改判 ★B-1）；F1 防呆全部在前端分支解决，后端 `add_range_decision` 返回形状零改动（§4-N3）；本版预计零新增事件常量（§4-N2），若 SPEC 阶段引入须双侧同 commit。

---

## 1. 红线声明：「只增不改」延续

v3.0.4 确立的「只增不改」约束整体延续，3.0.5 不重启、不加码。差异点与执行口径如下：

1. **models.py 本版零改动**：字段冻结红线延续；F1 防呆不补后端字段（§4-N3），S1 补译缺口经 bindings 差集推导（§4-N1），均无需触碰数据模型。`core/models.py` **不入本版白名单**，diff 必须为空。
2. **事件零新增预期**：R5.1 取消/失败上报复用既有 `llm:token_usage`（payload 加 `status` 键，纯增键向后兼容）与既有 `task:cancelled`（§4-N2）；`core/events.py` 与 `frontend/src/utils/events.ts` 预计零 diff。若 SPEC 阶段确需新事件，必须在同一改动内双侧登记并回写本条（延续 3.0.4 双侧同步红线）。
3. **既有测试断言零改动 + 白名单制度延续**：`tests/` 与 `frontend/src/**/*.test.ts` 既有断言默认零改动。**断言反转白名单（修订-1 定稿，逐 assert/expect 行粒度，终态以 SPEC M0-3 为准）**：后端 2 行——`tests/test_llm_translation.py` :217 随 R5.2 失败文案中文化改写（新文案定稿含「补译」二字）、:614 随 R5.1 取消返回附 data 反转（`test_cancel_midway_returns_bare_cancelled` :564 意图与断言一起改，:608/:612 保留；ledger 记录 failed 批的断言全保留）；初版预登记的四例单批场景整例反转**撤销**（:192/:226/:256/:518 四函数——单批 = 全批失败拒，`success is False` 语义未被 R5.3 改判触碰，★B-3）；前端 2 例——AIAssistantPanel.test.ts:301 随 R5.13 显示文本改写、SegmentBlocksLayer.test.ts:364/:366 随 R5.10 rejected 退场反转（★B-2）；另按 3.0.4 §4.1 追认制登记非 expect 行 1 处（findOverlays 选择器）。白名单外的断言删除/改写视为红线违规。
4. **主轨行为零回退**：主轨视图交互、`track_id` 缺省路径、无翻译缺口/无 keep/无手动 range 数据的工程行为与 v3.0.4 完全一致（等价 3.0.4 超集原则）。S4 的主轨零回退特指：主轨块 trim/菜单/手势矩阵逐字节不变（§6 矩阵维度 3）；R5.6/R5.10 的覆层改动不得破坏 confirmed delete 红纹的快照式全等 golden 锁。
5. **门禁 = 白名单 + diff 审查制**：后端可 diff 白名单（初稿，终态以 SPEC M0 对应表为准）= `core/llm_service.py`（R5.1 取消返回值 / R5.2 行级兜底 / R5.3 失败语义改判与补译批构建 / R5.5 纠错取消轮询化 / R5.8 串行+滑动窗）、`core/correction_service.py`（R5.4 两批量函数受控改）、`core/project_service.py`（R5.3 新增补译合并写方法，只增）、`main.py`（R5.1 handler 失败/取消分支 / R5.3 start_translation 路由与 completion payload 缺口合流（:1317-1331 区 + 返回 dict :1340，登记改点，MF2-2 补登 ★B-9）/ R5.4 expose 透传）、`core/llm_prompts.py`（R5.12 受控增行）、`core/config.py`（R5.8 DEFAULTS 追加 1 行）；白名单外 `core/**` 与 `pywebvue/**` 禁改、diff 必须为空。前端触点（预期）：WorkspacePage、App.vue（仅 F1 消费面复核，预计零改动）、useLlmTasks、useWorkspaceActions、useEdit、useUndoRedo（R5.0 新增快照回滚 API）、AIAssistantPanel、SuggestionPanel、Timeline、WaveformEditor、SegmentBlocksLayer、events.ts（预计零 diff）。
6. **受控改点登记（本版「改」既有代码的全部落点，diff 审查制重点项）**：(a) R5.5 动 `analyze_subtitle_correction` 既有取消机制（`core/llm_service.py:1116-1187` 外层 `with ThreadPoolExecutor + as_completed` 与 429 串行降级循环两循环同改轮询——E-3 补全区间，成功路径批序聚合语义不变）；(b) R5.4 动 `accept_high_confidence_corrections` / `clear_subtitle_corrections` 既有函数（`core/correction_service.py:446-530+`，可选形参默认值保持 timeline 级）；(c) R5.0 动 `WorkspacePage.vue` handleRangeDecision 既有快照与 emit 时序（三分支化，成功路径形态不变）；(d) R5.3 动 `analyze_subtitle_translation` 失败语义（3.0.4 新增代码的改判，非 legacy 行为）；(e) R5.1 动 `main.py` 翻译 handler 失败/取消分支；(f) R5.8 动翻译管线批 payload 预构建时序（`core/llm_service.py:1774-1790`，MF-4 补登；锚点勘误 E-4：MF-4 原引 :1019-1028 为纠错管线同构段，翻译管线自身预构建在此区间）——质量模式分支预构建改串行循环内逐批构建，默认关路径预构建原样保留以保证逐字节等价。每条 diff 必须对应一个 R 编号并登记「后端改动登记表」，无对应者补登记或回退。

---

## 2. 主项需求（一）：首项 F1 与 T-5.1 / T-5.2 / T-5.3

> 编号沿用 3.0.5 候选池口径取 R5.x。升格主项 S3/S4/S5（R5.6-R5.8）见 §3/§4；顺带批 R5.9-R5.16 见 §5。每条标注【主项 · 用户故事 · 反馈编号】，行为断言锚点均已复核。

### R5.0 duplicate 幂等返回防呆【首项 · 用户故事 US-01 · 反馈 F-B-01 + F-B-10（数据安全级）】

**需求**：`WorkspacePage.vue` handleRangeDecision（:990-999）三分支化——① `res.data.duplicate === true`：**不** emit project-updated，回滚本次已入栈的快照，轻提示「该范围已存在，已复用原条目」（自动消退，形态 SPEC 定）；② 成功：维持「先行快照 + emit patch」现状形态不变；③ 失败：toast 报错并**回滚本次快照**（F-B-10 同源顺带，消除 undo 空步——现状 pushSnapshot 先于桥调用且无去重，useUndoRedo.ts:48-58）。useUndoRedo 新增删除末条快照 API `popSnapshot`（纯新增，零既有改动）以支撑回滚——不触碰 redoStack（pop 只发生在本次 push 之后、响应返回之前的同步窗口，该窗口内 redoStack 已被 pushSnapshot 清空且无再入路径，API docstring 写明该不变量；SG-6，照 SPEC M5.0 裁决 2 口径）。补 duplicate 态前端测试（`WorkspacePage.rangeDecision.test.ts` 宿主补第三例）。

**边界**：后端 `add_range_decision` 零改动、返回形状零改动（不补 revision，裁决理由见 §4-N3）；波形气泡与时间码 popover 两入口共用同一 handler，分支一处生效；后端幂等行为本身（±0.05s 同 action、零写入零 revision）是正确设计，本条只修前端消费面。

**验收**：duplicate 返回不进 project-updated（工程对象内存态不变）；轻提示出现；duplicate 路径 undo 栈零新增；新增 duplicate 态用例绿，成功/失败既有 2 例零改动全绿。

### R5.1 翻译失败/取消成本可见（F2 + F5）【主项 T-5.1 · 用户故事 US-02 · 反馈 F-A-01 / F-A-02 / F-A-03】

**需求**：① 取消上报——`analyze_subtitle_translation` 取消返回值从裸 envelope（翻译管线共三处：`core/llm_service.py` :1871/:1903/:1939，勘误 E-1）改为附 data（已消耗 token_usage 与当时 ledger）；handler（`main.py:1266-1269`）检测取消以 `cancel_event.is_set()` 事件判据为主、"Cancelled" 字符串仅兜底（MF-2/焦点 5，与 task_manager :299-301 双通道同构）→ emit `llm:token_usage`（payload 增 `status: "cancelled"` 纯增键）并**不再** emit `llm:analysis_failed`，取消界面态由既有 `task:cancelled` 驱动中性提示「翻译已取消，已消耗约 X tokens」自动消退（消除 `task:cancelled` 不清 errorMsg 的残留路径，useLlmTasks.ts:245-248）；② 失败上报——handler 从失败结果 data 提取 ledger/token_usage（现状被 raise 丢弃，`llm_service.py:1978-1982` 已带数据）→ 先 emit `llm:token_usage`（`status: "failed"`，附失败批号）再报错；③ 429 降级透出——useLlmTasks 的 task:progress 监听消费 message 字段（:256-264 现状只取 percent），进度区显示「限流中，已切串行，剩余 N 批」（后端信号源 `llm_service.py:1942` 既有）。

**边界**：零新增事件常量（§4-N2）；成功路径 `llm:token_usage` 消费零改动；「已消耗约 X tokens」= 管线累计 usage，不做单价换算；纠错侧取消 token 上报与中性提示**本版不做**（SPEC 评估结论：与取消延迟修复分属两族改动，收益/风险比劣于翻译侧，B-6；维持 §10.2 ② 登记）；失败文案的中文出路指引与 R5.2 合并交付。

**验收**：取消与失败路径均触发 token 上报，toast/面板含「已消耗 X tokens、失败批 [n]/N」；取消显示中文中性提示、无英文 "Cancelled" 红框、errorMsg 不残留到下一任务；连续 429 限流时进度区可见降级状态。

### R5.2 行级解析兜底 translated_text + 失败中文出路指引（F3）【主项 T-5.1 · 用户故事 US-02/US-03 · 反馈 F-A-10】

**需求**：① 第 4 层行级解析兜底（`core/llm_service.py:612-634`）新增 `segment_id + translated_text` 逐行提取模式，使 Qwen/GLM/Ollama 典型「逐行近 JSON」输出可被救回，不再直接判解析失败；② 失败任务错误文案中文化并附出路指引：「N/M 批翻译失败（批 [n]），已译段已保留，可直接重试补译缺失段；反复失败建议更换模型或检查网络」类（终稿措辞 SPEC 定），红框不再展示英文技术体原文。

**边界**：行级模式为只增（既有 relevance/action 两模式不动）；解析层为翻译/纠错共享，新字段模式对纠错输出无副作用（无该字段即不匹配）；行级救回的批仍走 coverage 反向校验，漏译照旧进 ledger 不静默。

**验收**：非 json_mode mock（逐行 segment_id+translated_text）解析成功且全量守恒；批不可救回 mock 下任务报中文指引文案且 data 带 ledger/token_usage（与 R5.1 闭环）。

### R5.3 翻译增量补译 + uncovered 对账可读化（S1）【主项 T-5.1 · 用户故事 US-03 / US-10 · 反馈 F-A-04 / R-A-02；版本池出池】

**需求**：① **管线失败语义改判**（受控改点 d）：任一批重试后仍失败 → 不再整任务 fail 零落盘；失败批的目标 id 并入 `ledger.uncovered_segment_ids`（failed 批号保留记录），任务按「部分成功」返回并正常建轨——缺口段缺位与既有 uncovered 先例（翻译期间主轨变更落空，PRD-v3.0.4 R1.3）语义完全同构；**全部批失败仍拒绝零写入**（中文文案）。依据：部分轨已是合法状态且已有对账 UI；缺位段在双语导出中本就不显示第二行（export_service.py:467-545 仅绑定段成双行），数据正确性由「缺口显式可见 + 可补译」兜底。② **补译入口自动路由**（Q2 定稿，§4-N1）：`start_translation` 同语言轨已存在时计算缺口集 = 主轨 subtitle 段（排除 confirmed-deleted）中与该轨 bindings 无 1:1 配对的 id 集——非空则自动转补译模式，仅请求缺口 id 集（复用批处理管线与 ledger），完成走**新增**补译合并写方法（既有 track `model_copy` 增段 + 增 bindings，单 `_success_patch(tracks, bindings)`，禁止逐段 patch）；缺口为空则维持拒绝 +「可清空或删除该轨后重试」指引。③ 完成后 toast 明示「本次补译 N 段」。④ **uncovered 对账可读化**（US-10）：通知数据源 = completion payload 的 uncovered_ids，按「写侧对账 ∪ 管线缺口（ledger.uncovered_segment_ids）」合并口径（MF2-2 澄清 ★B-11：非仅查写侧对账，否则 1/34 场景写侧为空、通知不触发；登记改点）；逐条显示「mm:ss + 段文本前 20 字」（前端由 mainSegments 解析 id，AIAssistantPanel.vue:465 现状 join 内部 id 废除），点击定位主轨对应段，附一键「补译这些段」（走同一路由）。

**边界**：不加新 expose、不加模型字段、不加任务类型；补译期间主轨再次变更 → 走同一 uncovered 对账语义不静默；前端 start 前 `pushSnapshot(["tracks","bindings"])`（R1.4 形态复用），合并落盘单 patch + undo 一次回退；写侧双保险延续（入口校验 + 合并方法入口再查同语言轨与 id 冲突）；与 R5.8 串行模式可组合。

**验收**：1/34 批失败场景其余 33 批译文落盘且缺口对账可见可读；补译 mock 断言请求 id 集恰为缺口集；合并 revision +1、undo 一次回退整批补译；同语言完整轨重译仍被拒（文案含指引）；对账清单逐条含时间码与文本、可定位、可一键补译。

### R5.4 批量审阅收口（S2 + D7 第三项）【主项 T-5.2 · 用户故事 US-04 · 反馈 F-A-05 / F-A-06 + record §8.1 #2；版本池出池】

**需求**：① `accept_high_confidence_corrections` / `clear_subtitle_corrections`（`core/correction_service.py:446-530+`，现状 timeline 级无差别）增可选形参 `track_id: str | None = None` 三态（★B-1 改判）——`None` = 既有 timeline 级无差别（既有调用与断言零改动、逐字节等价）、`""` = 主轨作用域、非空 = 副轨作用域；前端按视图传值：主轨传 `""`、副轨传当前列表轨 id、「全部」视图传 null（timeline 级 + 确认文案明示「含全部轨道 N 条」）（Q3 定稿：按轨作用 + 确认文案兜底，§4-N5）；② 确认文案作用范围明示：「将接受当前轨〈轨名〉的 N 条高置信度建议」「将清除当前轨〈轨名〉的 N 条待审建议」（计数口径两处分工，SG-4：确认框 N = 前端按 scope 计数，完成 toast N = 后端返回 accepted_count/cleared_count 如实展示——逐条 accept 失败被静默跳过的偏差由两处口径分工消化）；③ **批量接受入 undo**：handleAcceptHighConfidence 调用前按 correctionUndoLayers 规则 pushSnapshot，快照层随作用域三态（MF-1）：主轨 `["segments","analysis"]` 两层 / 副轨 `["tracks","analysis"]` 两层 /「全部」（null）= `["segments","tracks","analysis"]` 三层并集——「全部」视图 qualifying 天然混含主/副轨结果，两层快照 undo 必挂（useWorkspaceActions.ts:993-1003 现状无快照），undo 一次整体回退；④ **D7 第三项顺带**（同函数族）：批量接受返回聚合单 patch（后端循环内部消化、聚合 `_success_patch`，消除逐条 patch 风暴与 O(project) 重复消化），返回 data **纯增 `patch` 键、`accepted_count`/`remaining_count` 旧键保留**（超集兼容，3.0.4 accept 超集先例，MF-3）；前端单次 applyProjectPatch，刷新链由「switch_timeline 全量替换」改为「patch 消费驱动」（diffCache 失效保留在前，消费链变化随本条登记）；clear 同步返回 `patch(analysis)` 同口径。

**边界**：默认 `None` 路径逐字节等价既有行为（三态形参 ★B-1）；批量路径复用 P2-4 时间轴钉扎与 `_assert_timestamps_unchanged` 语义；「清除全部」的「全部」语义 = null + 确认文案明示（作用域定稿表三态快照层与文案由 SPEC 定）。

**验收**：主轨视图批量接受/清除不动副轨待审集（新用例）；批量接受 undo 一次整体回退；确认文案含轨名与条数；accept_high 聚合单 patch（revision +1）且既有断言零改动全绿。

### R5.5 纠错取消延迟对齐（F4）【主项 T-5.3 · 用户故事 = record-3.0.4 §8.1 #1（A Top2 / B 有感）· 反馈 F4；§8.1 出池】

**需求**：`analyze_subtitle_correction` 取消机制复刻翻译侧 smoke-fix-1c 形态（样板 `core/llm_service.py:1845-1875`）——外层 `with ThreadPoolExecutor + as_completed`（:1116-1166，取消需干等当前批）与 429 串行降级循环（:1171-1187）两循环同改为 1 秒轮询（E-3 补全区间） `wait(timeout=1.0)` + `shutdown(wait=False, cancel_futures=True)`，取消后约 1s 返回。

**边界**：成功路径批序结果聚合逐字节等价（新增等价断言）；429 串行降级的退出路径同步修正（翻译侧 1c 同款教训）；测试样板复刻 `tests/test_translation_smoke_fix.py::test_cancel_observed_while_batches_blocked`；纠错取消的 token 上报与中性提示不强制（R5.1 边界，SPEC 评估）。

**验收**：大批量纠错取消约 1s 返回（单测断言，样板复刻）；成功路径聚合结果与改造前等价；纠错既有断言零改动全绿。

---

## 3. 主项需求（二）：S3 keep 可感知收口

### R5.6 keep 可感知收口（S3）【主项（升格）· 用户故事 US-05 · 反馈 F-B-02 / F-B-03 / F-B-07】

三点恰为 PRD-v3.0.4 R4.4「三点成本」的前端可见性欠账；数据链已求证全部成立（`core/project_service.py:2888-2935` keep 参与重跑计算、`export_service.py:599-608` 导出只认 confirmed delete），本条**不改数据层**。

**需求**：① 确认文案直显——「确认 = 参与裁剪计算（非导出动作）」脱离 hover title（`SuggestionPanel.vue:154-159,496` 现状仅 `:title`）：按钮旁内联小字或确认后差异化 toast（形态 SPEC 定）；② invalidated_count 重跑 toast——useEdit 的 generateSubtitleKeepRanges 返回类型补 invalidated_count（`useEdit.ts:181-202` 现状丢弃，后端 `:2915-2935` 已上报），重跑完成 toast 汇报「新增 N 条、按保留区间清除 M 条旧区间」；③ 红蓝并存提示——keep 与 delete 重叠时覆层 hover 标注「重叠区间导出按删除处理」（与 R5.9 覆层中文化一并实现）+ 导出确认页一句说明（落点 SPEC 定；区间相交为纯前端计算）。

**边界**：keep 计算与导出消费语义零改动（R4.4 裁决延续）；confirmed delete 红纹快照式全等 golden 锁不破；不加确认弹窗。

**验收**：US-05 三要点全验——确认 keep 的防误解文案不依赖 hover 即可见；重跑 toast 汇报 invalidated_count 与 new_edits；红蓝重叠在覆层 hover 与导出确认页可见「按删除处理」。

---

## 4. 主项需求（三）：S4 波形编辑模式一致性 + S5 质量模式

### R5.7 T1 方案 B 波形侧编辑模式一致性收口（S4）【主项（升格）· 用户故事 US-B-05 · 反馈 = 候选 #9（B Top3）；版本池出池】

**需求**：按 §6 trim 冻结语义矩阵（本 PRD 定稿）实施——① 副轨块 trim 手柄纳入 globalEditMode 守卫（编辑态拦截 + toast「请退出编辑模式后重试」，对齐 `SegmentBlocksLayer.vue:249-289` 结构操作守卫先例）；② lane 右键菜单结构操作（建段/清空轨/删除轨）纳入编辑模式守卫，查询类项不拦；③ 双 toggle title 与文档同步写明冻结矩阵；④ 顺带收口 P1 的覆层 title 与 Timeline tooltip 两处文案（与 R5.9 同文件族合并施工）。

**边界**：主轨块 trim/菜单/手势逐字节不变（矩阵维度 3）；不引入新手势、不动范围标记模式既有手势矩阵；「有时能拖有时不能」的归因成本由矩阵 + 文案面消灭。

**验收**：编辑态下副轨 trim 与 lane 结构操作被拦且有中文 toast；退出编辑模式全部恢复；主轨手势矩阵既有断言零改动全绿，且含「编辑态主轨 trim 仍可用」反向断言（globalEditMode ON 时主轨块 trim 手柄仍可拖动——防共享组件层误加守卫，SG-3）。

### R5.8 质量模式开关（S5）【主项（升格）· 用户故事 = R-A-05 · 反馈 = 候选 #11；版本池出池】

**需求**：config 新增 `llm_translation_quality_mode`（bool，默认 false，§4-N4）——开启时翻译管线串行派发（并发有效值 = 1）+ 上一批定稿译文随下批 payload 携带（滑动窗 = 1 批定稿上下文），服务跨批术语一致；默认关时与 v3.0.4 并发行为逐字节等价。

**边界**：仅作用翻译管线（含 R5.3 补译路径，可组合串行——Q7 合并设计裁决），不作用纠错；「并发 5 与滑动窗互斥」的结构性结论（PRD-v3.0.4 R1.2）不变，本条以布尔开关二选一而非参数化；时延代价（约 5×）在设置文案与 README 标注；实现为受控改点 (f)（MF-4 补登）：质量模式分支批 payload 预构建改串行循环内逐批构建（:1774-1790），默认关路径预构建原样保留以保证逐字节等价。

**验收**：开关关闭路径逐字节等价既有并发行为（既有断言零改动）；开启时批 N+1 的 payload 含批 N 定稿译文（mock 断言）；串行模式下取消仍约 1s 生效。

---

## 5. 顺带批（P1-P7 + D3，纯前端小面为主，可与主项并行开发）

| 编号 | 项 | 需求与边界（细案 SPEC 定） | 验收要点 |
|---|---|---|---|
| R5.9 | P1 文案收口批 | Timeline 编辑按钮 tooltip 中文化并轨感知（`Timeline.vue:625` 现状英文）；覆层 title 按 action×status 中文语义化（`SegmentBlocksLayer.vue:378-393`「Delete range」硬编码废除，keep 蓝纹不再误显「Delete range」）；重译拒绝文案语言码「en」改显示名（`main.py:2996-3006`，`_TRANSLATION_LANGUAGES` 映射既有） | 全中文界面无英文 tooltip/title 残留；keep 覆层 hover 显示「保留范围 X-Y（状态）」 |
| R5.10 | P2 覆层语义诚实批 | rejected range 覆层隐藏（裁决定稿：与 SegmentBlocksLayer.test.ts:359-368 既有锁定断言反转对应）；rejected 过滤为**新增分支**——现状 visibleEditRanges :147-148 仅按 target_type 与视窗过滤、无 rejected 逻辑（:381 注释自证 NOT filtered），改动性质只增，confirmed/pending 面 golden 锁零触碰（E-6/★B-10）；双 toggle 同开时建段按钮降档或文案「建段（已暂停）」（`WaveformEditor.vue:1243-1251` 现状与实际 `buildMode && !rangeMode` 不符）；确认气泡 Esc 关闭 + 点击波形区外消泡 | 被忽略范围从波形退场（US-06）；同开状态 UI 与实际行为一致；气泡两新关闭路径可用；confirmed delete golden 锁不破 |
| R5.11 | P3 审阅体验批 | 审阅 modal 按当前列表轨过滤 + 「全部」切换（get 已返回 track_id）；启动新纠错不再先清本地待审列表（`useLlmTasks.ts:337→:308-313` reset 延后至新结果返回）；时间码支持 mm:ss.s 解析兼容纯秒 + 「取播放头」按钮 + clamp 回显 + 成功 toast | 主/副轨审阅互不稀释、按轨过滤与「全部」切换可用（US-08）；启动纠错无「暂无」假象；时间码三态反馈齐全（US-07） |
| R5.12 | P4 prompt 语义说明 | `llm_prompts.py` 系统 prompt 增一句 aligned_main_text 语义说明（「主轨参考稿，仅用于校对译文，勿照抄」类，受控增行）；Q8 裁决豁免观察前提 | 副轨纠错 prompt 含该说明；注册表键集类测试如受影响按 3.0.4 §4.1 增行追认先例处理 |
| R5.13 | P5 token 量级预估 | 翻译入口「约 N 批 · 约 X 万 token」纯前端估算（按段数与字符量、标注「约」；估算式按后端同式字符累计切批近似——批窗 30 + 字符预算 4000，token ≈ 累计字符 × 经验比，避免与实际批数系统性漂移，SG-5，细案 SPEC 定），随主轨段数动态刷新 | 预估显示且量级合理；失败启动不写回语言记忆（现状保持，US-09） |
| R5.14 | P6 重译拒绝路径顺滑 | 列表轨选择器补「清空/删除该轨」入口，或拒绝 toast 附「去波形右键该轨」指引（二选一 SPEC 定；与 R5.9 显示名半条合并施工） | 拒绝提示给出的出路在当前视图可达（US 视角 = F-A-07 收口） |
| R5.15 | P7 删除撤销提示 | 副轨删除/级联删除 toast 附「已删除 N 段，可 Ctrl+Z 撤销」；不加确认框（record-3.0.4 §7.1 裁决维持，US-11） | 删除 toast 含撤销提示与级联说明 |
| R5.16 | D3 perf 环境例根修 | `useRowLayout.perf.test.ts` 挂载墙钟环境例根修（改造/拆分用例），任一前端 phase 顺手完成，销掉每版门禁注记 | 根修后 vitest 全绿无豁免；未完成则 §9 维持豁免口径（决策树缓冲阀） |

**D4 移交说明**：T4b 其余测试缺口（detect_silence 本体 / 端到端串测 / padding=0 交叠 / basic 空白点击建重叠段）按 PRD-v3.0.4 §10.3 移交至本版测试规划，落点见 §7.4，不占产品主题。

---

## 6. 开放问题逐条裁决（研究报告 §7 全 8 条 + 新增设计裁决 + trim 矩阵）

| 编号 | 问题（摘要） | 裁决 | 理由 |
|---|---|---|---|
| Q1 | F1 走 3.0.4 smoke-fix 补丁还是并入 3.0.5 | **立项会裁决①：并入 3.0.5 首项（R5.0），v3.0.4 不出补丁** | 数据安全级 + 修复面小 + 本版周期短；触发场景（重复框选/双击/时间码重复提交）恰是幂等设计的服务对象，版本内最优先交付 |
| Q2 | S1 入口形态：自动路由补译 vs 独立「补译」入口 | **定稿 = 重译同语言自动路由补译 + toast 明示「本次补译 N 段」**（R5.3/N1） | 用户 A 明确接受补译模式而非新入口（R-A-02）；零新增 UI 面；缺口集可由 bindings 差集运行时推导、无需持久化 ledger；语义显式性由 toast + 对账清单兜住 |
| Q3 | S2 作用域语义：按轨作用 vs timeline 级 + 文案明示 | **定稿 = 按当前列表轨作用 + 确认文案兜底**（R5.4/N5；「全部」视图例外并明示条数） | 与 3.0.4「锁定当前轨」心智一致（PRD-v3.0.4 Q4 先例）；双案用户均可接受，按轨是信任缺口的根治；文案兜底覆盖残留面 |
| Q4 | S3 入主项还是顺带 | **立项会裁决②：升主项，按 US-05 三要点全验**（R5.6） | keep 是 2.x 占位块用户的迁移动机（B Top2）；三点为 R4.4 成本的可见性欠账，纯文案/toast 面成本极低收益高 |
| Q5 | S6：detail JSON 过渡 vs 3.1.x schema | **立项会裁决③：3.1.x schema 首发不入版**，detail 过渡案亦不做 | detail 侧通道与「detail 是 AnalysisResult 概念」的模型语义错位需架构师确认；字段冻结红线延续；降级诉求（hover 创建时间）随 §10 登记 |
| Q6 | S4 是否入 3.0.5 | **立项会裁决②：入版（R5.7）**，前置 trim 矩阵本 PRD §6 定稿 | 用户 B Top3、每日摩擦；矩阵先裁决消除「行为收窄类改动」的不确定面；与 R5.9 同文件族顺带收口两处文案 |
| Q7 | S5 是否入 3.0.5 | **立项会裁决②：入版（R5.8）**，config 默认关，与 S1 合并设计（补译可组合串行） | 用户 A R-A-05 诉求真实（重点课程 overnight）；与 R5.3 同管线函数族，一次改透成本最低 |
| Q8 | P4 观察前提是否豁免 | **定稿 = 豁免观察前提，直接入顺带批**（R5.12） | 预登记条件「观测到模型忽略/误用」真机未现，但用户 A 从质量侧倾向补且成本一句话，对逐条审阅时间有正向收益 |
| N1 | S1 缺口推导与失败批衔接（新增设计裁决） | 缺口集 = 主轨段（排除 confirmed-deleted）与目标轨 bindings 的 1:1 差集，运行时推导不持久化 ledger；失败批降级并入 uncovered（管线改判，受控改点 d） | 零 schema 变更；与既有 uncovered 先例同构；全批失败仍零写入拒绝 |
| N2 | F2 失败/取消上报的事件形态（新增设计裁决） | 复用 `llm:token_usage`（payload 增 `status` 键）+ 既有 `task:cancelled`；取消不再 emit `llm:analysis_failed`；零新增事件常量 | `task:cancelled` 已被前端监听且 UI 单飞（M1-5）下语义无歧义；status 纯增键向后兼容；避免事件面膨胀 |
| N3 | F1 前端分支 vs 后端补 revision（新增设计裁决） | **纯前端三分支 + 快照回滚 API；后端不补 revision** | 补 revision 会让「带 revision 的非 patch 对象」混入 isProjectPatch 通道被误判为空 patch 应用，制造新歧义；前端分支 + duplicate 态测试锁已完整覆盖 US-01 四要点 |
| N4 | S5 config 键名与形态（新增设计裁决） | `llm_translation_quality_mode`（bool，默认 false），DEFAULTS 追加 1 行 | 与既有 `llm_` 前缀命名一致；布尔二态对应「并发 vs 串行+滑动窗」的结构性互斥，不做参数化 |
| N5 | S2 形参默认值语义（新增设计裁决；修订-1 三态改判 ★B-1） | `track_id: str \| None = None` 三态：`None` 默认 = 既有 timeline 级（兼容层）、`""` = 主轨作用域、非空 = 副轨作用域；前端按视图传值（主轨传 ""、副轨传轨 id、「全部」传 null + 文案明示） | 既有断言零改动；作用域决策留在消费端，与 3.0.4 轨透传形态一致（R2.4 先例）；`str = ""` 字面无法区分「未传」与「主轨」，无法满足「主轨视图不动副轨」验收，故改判三态 |

### trim 冻结语义矩阵（S4 前置裁决，研究报告 §5.3 四维度，本 PRD 定稿）

| 维度 | 裁决 |
|---|---|
| 编辑态 × 副轨块 trim | **冻结**：globalEditMode ON 时副轨块 trim 手柄拦截 + toast「请退出编辑模式后重试」，对齐 SegmentBlocksLayer 结构操作守卫先例（:249-289，v2.1.1 A-03）；编辑模式语义统一为「文本校对独占态，结构/几何修改冻结」 |
| 编辑态 × lane 菜单 | **纳入守卫**：lane 右键结构操作（建段/清空轨/删除轨）编辑态拦截 + 同款 toast；查询/视图类菜单项不拦 |
| 主轨零回退 | 主轨块 trim/菜单/手势逐字节不变（含主轨 trim 现状不受守卫的差异——超集原则下主轨行为是 2.x 以来基线不可动，该不对称为刻意结果并写入文档） |
| 文案面 | 双 toggle title 与 README 3.0.x 段写明冻结矩阵；规则严但明确（用户 B 原话），消灭「点了没反应」的归因成本 |

---

## 7. 交付计划与规模

```text
P0（0.5 天）      分支 dev-3.0.5（自 v3.0.4 拉出）/ 基线核对（pytest 833 / vitest 840-839）/ 后端改动登记表建表 / PRD-SPEC 定稿
P1（6-8.5 人日）  R5.0 首项 → R5.1 → R5.2 → R5.3（T-5.1 三件套，管线族一次改透）→ R5.8（S5 同族收尾）+ R5.13 → beta.1
P2（2-2.5 人日）  R5.4（T-5.2 + D7 第三项聚合 patch）→ beta.2
P3（1-1.5 人日）  R5.5（T-5.3，样板复刻）
P4（3.5-5 人日）  R5.6（S3）+ R5.7（S4，trim 矩阵落地）+ 顺带批 R5.9-R5.12 / R5.14 / R5.15（纯前端，可与 P1-P3 并行开发）+ R5.16 → beta.3
P5（1-1.5 天）    门禁终检 / 真机清单 / README 回填 / 版本池回写 → v3.0.5-RC → 正式
```

- **规模裁决（修订-1 重报，R3 逐触点复核回落，★B-8）**：逐项复核估 **13.5-17.5 人日**（P0 0.5 / P1 6-8.5 / P2 2-2.5 / P3 1-1.5 / P4 3.5-5 / P5 1-1.5；两端不同时取上界；低估段 = P1 的 M5.3/M5.8 与 P4 的 D4+顺带批，无显著高估段）；日历 **11-15 天**（以「顺带批与 P1-P3 并行开发」为显式前提——并行假设属承诺口径的一部分，唯一显式例外见顺序约束⑥；单人串行备份口径日历 15-19 天）。初版 10-14 人日 / 8-12 天经 R3 逐触点复核证实偏乐观，本条为终值；代码量级（不含测试）后端约 350-550 行（llm_service 为主）、前端约 400-600 行不变。
- **顺序约束**：① R5.8 必须在 R5.3 之后合入（同 `analyze_subtitle_translation` 函数族防冲突）；② R5.1/R5.2/R5.3 同族 hunk 在 P1 内一次改透，禁止跨 phase 交错；③ R5.7 的覆层/tooltip 文案与 R5.9 同 commit 族合入（WaveformEditor/SegmentBlocksLayer 防冲突）；④ golden 锁（confirmed delete 全等断言、keep golden 对拍 2 例）在任何 SegmentBlocksLayer / keep 相关改动前先跑基线确认；⑤ R5.3 的 completion payload 缺口合流 hunk（main.py :1317-1331 区 + 返回 dict :1340）先于或同 commit 于对账渲染消费端改造（AIAssistantPanel / WorkspacePage watcher / R5.11 reset 延后——三者消费同一 lastTranslationCompletion 结构，先定数据形状防中间态假绿，SPEC M0-4 序 7）；⑥ R5.11 开发基线必须包含 R5.4 的 useWorkspaceActions.ts 改造（同文件族 + pendingCorrections 消费面，禁止在未含 R5.4 的分支上并行开发——P4∥P1-P3 并行假设的唯一显式例外点，PLAN 登记，SPEC M0-4 序 8）。
- **超期决策树（修订-1 更新，PLAN 定稿）**：首让 R5.8（S5 质量模式池化重启，最独立——含受控改点 (f) 滑动窗，实施期实测成本超 P1 预估上界即触发，R2 规模复核条件延续）；次让顺序 = R5.7 的 lane 菜单半（trim 半保留）→ R5.11 时间码增强半 → R5.14；不可让 = R5.0 / R5.1 / R5.2 / R5.3 / R5.4 / R5.5 / R5.6。每次触发照 3.0.4 修订-2① 先例四要素留痕（日期 / 触发信号 / 裁决与影响面 R 级 / 回写文档处），让位项按 §10.1 回池口径处理并回写 PLAN。

### 7.4 测试规划与新增用例矩阵（含 D4 落点）

- **后端 ≥30 用例**（终值，★B-5/★B-7）：R5.1 取消/失败 token 上报与 status 键（≥4）；R5.2 行级 translated_text 模式与不可救回中文文案（≥4）；R5.3 失败批降级 uncovered、全批失败拒、补译缺口推导、合并单 patch、写侧双保险、uncovered 对账数据，含 SG-1 守恒不变量断言（`ledger.uncovered_segment_ids` == 目标 id 集 − 实际返回 translations 覆盖 id 集，双向无多无少）与 MF2-2 合流断言（completion payload `uncovered_ids` == 写侧对账 ∪ 管线缺口去重并集）（≥10）；R5.4 轨作用域双轨互扰、默认 None 兼容、聚合单 patch（≥6）；R5.5 取消 1s 断言与聚合等价、429 串行降级 × 取消交织两序列、「串行 × parse 失败」锁面例（≥4，SG-2/MF2-1）；R5.8 串行/滑窗/关闭等价（≥2）。
- **前端 ≥24 用例**（终值，★B-7）：R5.0 duplicate 态第三例与快照回滚（≥3）；R5.1 取消中性态与 progress message 消费（≥3）；R5.3 对账可读化渲染与补译入口（≥4）；R5.4 确认文案作用域与快照（≥3）；R5.6 三要点（≥3）；R5.7 trim/lane 守卫矩阵含主轨 trim 反向断言（≥4，SG-3）；R5.10/R5.11 覆层过滤与按轨过滤/时间码（≥2，与上合并计）+ R5.13 估算显示 1 例 + R5.15 级联删除计数 1 例（R5.14 文案拼接无断言面，豁免明示）。
- **D4 移交落点**：detect_silence 本体、端到端串测、padding=0 交叠、basic 空白点击建重叠段四项并入 P4 测试轮（不占产品主题；其中 basic 重叠段兜数据安全，优先补）。

---

## 8. 风险表

| 风险 | 等级 | 关键缓解 |
|---|---|---|
| R5.3 管线失败语义改判回归（触及 3.0.4 新增管线核心语义） | 高 | 断言反转白名单预登记（§1.3）；全批失败仍零写入拒绝；缺口显式对账 + 补译闭环；无失败路径行为逐字节等价断言 |
| R5.4 批量作用域化回归（主/副轨待审集误清误留） | 中-高 | 默认 "" 兼容 + 既有断言零改动全绿；双轨互扰新用例；聚合 patch 层对照 R2.3 三裁决复用 |
| R5.5 纠错取消改造触及纠错主链路 | 中 | 翻译侧样板已证 + 成功路径聚合等价断言 + 429 退出路径同步修正 |
| R5.7 行为收窄类改动（trim 冻结）误伤主轨 | 中 | 矩阵四维度定稿 + 主轨逐字节零回退断言 + 手势矩阵既有锁零改动 |
| R5.8 串行模式与并发路径互扰 | 中 | 默认关 + 关闭路径逐字节等价 + 开关两态单测 + P1 内后于 R5.3 合入 |
| R5.10 覆层 rejected 过滤破坏 golden 锁 | 中 | 快照式全等断言不破 + 仅新增 rejected 过滤条件（现状无此分支，只增，E-6/★B-10）+ deleteRanges 零改动快照锁复用 |
| R5.1 事件消费面回归（token_usage/progress 新键） | 低-中 | status 纯增键向后兼容 + 成功路径既有消费零改动断言 |
| 红线 diff 审查制纪律（白名单 6 文件 + 受控改点 6 处，MF-4 补登 (f)） | 中 | 后端改动登记表 + 固定检查命令每 phase 执行；无 R 编号对应即回退 |
| 千段翻译耗时/token 真机观测债顺延（record-3.0.4 §6 ③） | 低 | 继续挂真机清单（§9.3），不阻塞发布 |

---

## 9. 验收总纲

- **后端门禁**：`uv run pytest` ≥833（3.0.4 发布终态基线）**只增不减**全绿（新增用例对齐 §7.4 矩阵）；`uv run ruff check .` 0
- **前端门禁**：`cd frontend && bun run test` collected ≥840 且 passed ≥839+新增全绿——**唯一允许失败 = `useRowLayout.perf.test.ts` 挂载墙钟（3.0.3 起登记环境例，维持豁免）**；若 R5.16 根修完成，该例转全绿、豁免口径退役并销账（验收按全绿判）；`bun run build`（vue-tsc --noEmit + vite build）通过；`bun run lint` 0/0
- **红线检查命令**（固定，diff 基准恒为 `v3.0.4`）：
  - 后端 diff 文件集 ⊆ §1.5 白名单（6 文件）；`core/models.py`、白名单外 `core/**` 与 `pywebvue/**`、`dev.py`/`build.py` diff 必须为空
  - 后端断言删改仅限断言反转白名单（§1.3 定稿 2 行：:217 随 R5.2 文案改写 / :614 随 R5.1 反转，全部位于 `tests/test_llm_translation.py`；初版预登记四例整例反转已撤销，★B-3）：`git diff v3.0.4 -- tests/ | grep -E '^-[[:space:]]*(assert |self\.assert)'` 命中行必须全部落在白名单登记的 assert 行内（record 逐条核对），白名单外命中即 fail
  - 前端断言白名单外零删改：`git diff v3.0.4 -- frontend/src | grep -E '^-[[:space:]]*expect\('` 命中行必须全部落在前端反转白名单 2 例的 expect 行内（AIAssistantPanel.test.ts:301 + SegmentBlocksLayer.test.ts:364/:366，共 3 行，★B-2），白名单外命中即 fail
  - events 双侧：`core/events.py` 与 `frontend/src/utils/events.ts` 预期零 diff；若 SPEC 阶段引入新事件，按本版新增事件名双侧存在性检查（3.0.4 精化口径延续）
- **主轨零回退与 golden 锁**：主轨视图交互、无翻译缺口/无 keep/无手动 range 数据的工程行为与 v3.0.4 一致；confirmed delete 红纹快照式全等断言、keep golden 对拍 2 例、手势矩阵锁零改动全绿；主轨纠错序列既有断言全绿
- **断言反转白名单登记**：终态 = 后端 2 行 + 前端 2 例 + 追认制 1 行（§1.3 定稿，与 SPEC M0-3 一致），随对应 phase 在 record 反转清单登记条目与理由（意图与断言同步反转，ledger 记录 failed 批的断言保留）
- **文档链**：README_zh/README 3.0.5 功能段回填（增量补译与缺口语义、质量模式、trim 冻结矩阵、覆层三态语义、取消中性提示）；record 逐步落盘（断言反转清单 / 受控改点逐 hunk 审查 / 后端改动登记表每 phase 追加、P5 终检逐条核对）；版本池注记回写（§10）

### 9.3 真机回归清单（双平台，P5；异常走 smoke-fix 先例：合入分支、tag 不动）

沿承 3.0.4 清单（翻译全链 + undo 三层一致 / 纠错双轨 + 轨徽门控 / 编辑扫掠副轨 / lane 建段 / 语义搜索 / 手动范围全链 / keep 重跑场景）+ 研究报告 §8.4 新增项：

1. 千段翻译耗时与 token 观测值回填（record-3.0.4 §6 ③ 顺延债，本版必填）
2. keep 重跑 invalidated toast 可见性（R5.6）与确认文案直显
3. 批量按钮作用域提示（R5.4：主轨视图操作不吞副轨待审集 + 文案轨名/条数）
4. 翻译失败 → 补译全链（至少一家非 json_mode 提供商：Qwen/GLM/Ollama；含中文指引、token 上报、补译合并、undo）
5. 大工程纠错取消即时性（R5.5，对照翻译侧约 1s 手感）
6. trim 冻结矩阵手感（R5.7：编辑态副轨 trim/lane 菜单拦截与退出恢复；主轨零变化）
7. 时间码 mm:ss/取播放头/clamp 回显/成功 toast（R5.11）
8. rejected 覆层退场、建段降档、气泡 Esc/点外消泡（R5.10）

---

## 10. 遗留与版本池回写

### 10.1 出池登记（登记处 → 本版交付）

- 版本池出池 4 项：翻译增量补译入口（→ R5.3）；定稿译文滑动窗（→ R5.8）；T1 方案 B 波形侧编辑模式一致性收口（→ R5.7）；accept_high/clear track 作用域化（→ R5.4）
- record-3.0.4 §8.1 出池 4 项：#1 纠错取消延迟（→ R5.5）；#2 批量作用域化（→ R5.4）；#4 英文 tooltip（→ R5.9）；#5 prompt 语义说明（→ R5.12）
- 散落登记出池 1 项：D7 第三项 handleAcceptHighConfidence patch 化（→ R5.4）；清债池出池 1 项：D3 perf 环境例根修（→ R5.16，若触发让位则回池并维持门禁注记）

### 10.2 新增登记与维持原样

- **新增登记**：① S6 手动范围备注——3.1.x schema 演进首发候选（与工作区预设/行设置随工程同批重启）；降级诉求「建议面板条目 hover 展示创建时间」可独立评估，登记版本池；② 纠错侧取消 token 上报与中性提示对齐（R5.1 边界未强制，视 SPEC 评估结果回写）；③ 补译进度逐批流式预览（`llm:translation_progress` 登记项再评估：R5.3 交付后补译进度可顺带，本版不做）
- **维持原样**：桥断连警示 / 点击字幕三模式 / 撤销恢复选区+视图 / 二分切片 / 手工 DOM 行保留；「需 schema 演进」两项与 S6 冻结至 3.1.x 专门重启；D1（InjectionKey 类型化，R5.11 触及接线则顺带）/ D2（悬空 pending 物理清理）/ D5（MiloCutApi 级写锁——延后设计要点：锁粒度、tick 回调重入递归锁策略、与 TaskManager 后台线程获取顺序表，重启触发 = 真实并发写错序证据或 workflow_engine 纳入翻译/纠错 step，见研究报告 §5.4）/ D6（2.x 重叠段迁移观察项）/ D7 其余三项 / D8 余项
- **观察项延续**：副轨删除确认策略（「无确认框 + undo 兜底」维持，误删证据出现再议）；千段观测值回填（§9.3 第 1 项）

### 10.3 record 落盘要求

断言反转清单（§1.3 定稿：后端 2 行 + 前端 2 例 + 追认制 1 行）随对应 phase record 登记；后端改动登记表由 SPEC 建表、每 phase 追加、P5 终检逐条核对；受控改点 6 处（§1.6，MF-4 补登 (f)）逐 hunk 审查留痕；超期决策树触发（如有）按四要素留痕并回写 PLAN。

---

## 11. 修订记录

- **修订-1（2026-09，架构师 R2/R4 + 执行者 R3 评审结论回落；已与 SPEC v3.0.5 终态对齐，冲突处按 SPEC 回写）**：
  - **must-fix 4 条落点**：① MF-1——R5.4③ 批量 undo 快照层三态化（主轨两层 / 副轨两层 /「全部」= ["segments","tracks","analysis"] 三层并集）；② MF-2——R5.1① 取消判据改 handler 侧 cancel_event.is_set() 事件优先、"Cancelled" 字符串仅兜底（焦点 5，不在 envelope 增标记键）；③ MF-3——R5.4④ 聚合 patch 返回 data 纯增 patch 键、旧键保留（超集兼容），前端刷新链改单次 applyProjectPatch 驱动（移除 switch_timeline 全量替换）；④ MF-4——§1.6 补受控改点 (f)（payload 预构建改串行循环内逐批构建，仅质量模式分支，默认关原样保留）+ R5.8 边界同步。
  - **焦点裁决 5 项结论**：焦点 1 = R5.3 部分成功用三件套确定性单测锁边界、不做 golden；焦点 2 = R5.4 聚合 patch 层并集（segments/tracks/analysis 按实际写入面）、revision 只 +1；焦点 3 = R5.5 纯轮询化不做状态机重构、两循环 × 三退出状态矩阵落 SPEC；焦点 4 = trim 矩阵可用，附点名主体 + 轨角色条件守卫 + 主轨 trim 正反断言三条件；焦点 5 = 取消判据结构化但方案为 handler 侧事件判据。
  - **锚点勘误 E-1~E-6**：E-1——R5.1 取消裸 envelope 实为三处（:1871/:1903/:1939），随 R5.1① 勘正；E-2——R5.6 invalidated_count 进入返回值在 project_service.py:2986（计数与日志 :2915-2933），SPEC 侧勘误、PRD 措辞不变；E-3——R5.5 串行降级循环精确区间 :1171-1187，随 §1.6(a)/R5.5 补全两循环口径；E-4——MF-4 原引 :1019-1028 为纠错管线同构段，翻译管线预构建在 :1774-1790，随 §1.6(f) 取值勘正；E-5——R5.0 双入口证据改 WorkspacePage.vue:958/:1619 + SuggestionPanel.vue:161-169，SPEC 侧勘误；E-6——R5.10 rejected 过滤为新增分支（现状无 rejected 逻辑），随 §5/§8 勘正（B-10）。
  - **R2 suggest 6 条**：SG-1（R5.3 守恒不变量断言）与 SG-2（R5.5 额度 ≥4、429×取消两交织序列）落 §7.4；SG-3（编辑态主轨 trim 反向断言）落 R5.7 验收；SG-4（确认框前端计数 / 完成 toast 用返回值）落 R5.4②；SG-5（估算式同式近似）落 R5.13；SG-6（回滚 API 与 redoStack）落 R5.0——照 SPEC M5.0 裁决 2 口径（popSnapshot 不触碰 redoStack）。
  - **R3 意见回落（R4 轮已逐条裁决入 SPEC）**：MF2-1 串行记账判据冻结（not-corrections 不照抄翻译侧）与 MF2-2 缺口断链为 SPEC 侧处置，PRD 投影经 B-9/B-11 落地；SG2-1~SG2-7 无 PRD 字面投影；顺序约束新增 ⑤（缺口合流先行，序 7）⑥（R5.11 基线须含 R5.4，序 8）。
  - **天数重报（R3 逐触点复核回落，★B-8）**：人日 10-14 → **13.5-17.5**（P1 6-8.5 / P2 2-2.5 / P4 3.5-5，P0/P3/P5 维持；两端不同时取上界）；日历 8-12 → **11-15 天**（以顺带批与 P1-P3 并行开发为承诺口径前提，单人串行备份日历 15-19 天）；超期决策树更新（首让 R5.8，次让顺序与四要素留痕照 3.0.4 修订-2① 先例）。
  - **SPEC 附录 B ★ B-1~B-11 处置（全部落实，无搁置项）**：B-1 三态形参（§0.3 / §4-N5 / R5.4①）；B-2 前端断言反转白名单 2 例（§1.3 / §9）；B-3 后端白名单收窄逐 assert 行 2 处、四姊妹例撤销（§1.3 / §9 / §10.3）；B-4 (a)/(f) 锚区间勘正（§1.6）；B-5+B-7 测试额度终值后端 ≥30 / 前端 ≥24（§7.4，不留 23 中间值）；B-6 纠错侧上报明确不做（R5.1 边界）；B-8 天数重报（§7）；B-9 main.py 缺口合流 hunk 补登（§1.5）；B-10 rejected 只增措辞（§5 / §8）；B-11 「写侧对账 ∪ 管线缺口」合并口径（R5.3④）。
- **初版（2026-09）：立项定稿**（研究报告取证 + 双人反馈逐条裁决 + 立项会三裁决留痕）：
  - **裁决①（F1 紧急通道）**：改判研究报告 §7-Q1 的 smoke-fix 补丁建议——F1 并入 3.0.5 **首项**（R5.0），v3.0.4 不出补丁（本版周期短，避免补丁双线流程开销；留痕备查）。
  - **裁决②（主项六项全量）**：T-5.1 翻译失败成本三件套（F2+F3+S1，R5.1-R5.3）/ T-5.2 批量审阅收口（S2 + D7 第三项，R5.4）/ T-5.3 纠错取消对齐（F4，R5.5）/ S3 keep 可感知收口升主项（R5.6，按 US-05 三要点全验）/ S4 T1 方案 B 入版（R5.7，trim 冻结语义矩阵本 PRD §6 定稿）/ S5 质量模式开关入版（R5.8，config 默认关，与 S1 合并设计、补译可组合串行）。
  - **裁决③（S6）**：手动范围自由备注 = 3.1.x schema 首发不入版；detail JSON 过渡案不做（§6-Q5）。
  - **开放问题定稿**：Q1/Q4/Q5/Q6/Q7 随三裁决覆盖；Q2 = 重译同语言自动路由补译 + toast 明示补译 N 段；Q3 = 按当前列表轨作用 + 确认文案兜底；Q8 = 豁免观察前提直接入顺带批（§6 各行含理由）。
  - **新增设计裁决 N1-N5 与 trim 冻结矩阵**由 PM 定稿（缺口差集推导 / 事件形态零新增 / F1 纯前端分支 / config 键名 / S2 形参默认值 / trim 四维度），设计级细节留 SPEC 空间。

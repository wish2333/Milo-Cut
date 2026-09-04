# v3.0.4 PRD/SPEC/PLAN 多角色评审日志

> 日期：2026-09　形式：四角色子代理接力协作（产品经理 → 架构师 → 代码执行者 → 架构师 → 产品经理 → 项目经理）+ 编排者终检
> 输入：`docs/3.0.4/探索报告-v3.0.4.md`（立项依据，先行完成）
> 输出：`PRD-v3.0.4.md`（369 行）· `spec-v3.0.4.md`（530 行）· `plan-v3.0.4.md`（435 行）

---

## 轮次总览

| 轮 | 角色 | 动作 | 关键产出 |
|---|---|---|---|
| R1 | 产品经理 | 起草 PRD | 11 节 / 15 开放问题全裁 / 红线重启初稿 |
| R2 | 架构师 | 评审 PRD + 起草 SPEC | 15 条评审意见（6 must-fix）；SPEC M0-M5 + 15 项实施层裁决 |
| R3 | 代码执行者 | 逐触点核验 SPEC | 45 处锚点抽查（92% 逐字吻合）；5 must-fix + 7 suggest；天数复核 13-17.5 人日（原 8-12 低估）；4 条新顺序约束 |
| R4 | 架构师 | 按 R3 修订 SPEC | 12/12 意见接受；3 项新裁决（钉扎 fail-fast / 不加锁 / 气泡内嵌）；530 行定稿 |
| R5 | 产品经理 | 按 R2/R3 修订 PRD | 16 条结论 + 4 项 SPEC 回写落地；keep 完整闭环维持；天数重报日历 12-15 |
| R6 | 项目经理 | 起草 PLAN | 5 Phase / 28 步 / 101 checkbox；门禁脚本化；golden 前置 P3-1 |
| R7 | 编排者 | 跨文档一致性终检 | patch 层/手势/白名单/天数/门禁命令/测试总数六交叉点全部对齐 |

## 关键争议与裁决（按发现轮次）

1. **Shift-marquee 手势冲突（R2 must-fix）**：PRD 初裁复用 marquee，架构师查证 multi 模式 Shift-drag 已是跨行段多选手势（WaveformEditor.vue:742-750），占用即主轨回退 → 改判「范围标记」工具栏 toggle（默认 OFF，对齐建段模式先例）。PRD/SPEC/PLAN 三处同步。
2. **accept patch 层错写（R2 must-fix）**：初版 `tracks+bindings` → 勘误为 `segments+analysis`（主轨）/`tracks+analysis`（副轨）；undo 捕获层同步补 analysis（漏层则「undo 一次回退 accept」验收必挂）。
3. **并发与滑动窗互斥（R2 must-fix）**：纠错骨架派发前预构建全部批 payload，批 N+1 取不到批 N 定稿译文 → 裁「并发 + 源文 ±ctx 窗口」，定稿译文滑动窗登记版本池。
4. **红线白名单缺文件（R2 must-fix）**：correction_service.py（R2.2/R2.3 全部改动所在）漏列 → 补列 + 显式列 config/llm_prompts/llm_service。
5. **Q10 keep 完整闭环成本（R2 量化 → R5 裁决）**：三点隐藏成本（覆层 action/status 感知、陈旧 trim 剔除 invalidated_count、确认文案）——PM 裁维持完整闭环全吸收（成本有界 ≈0.5-1 天；「撑间隙」是 2.x 习惯中仅 keep 可覆盖者），R4.4 保持 S4 内部首砍项。
6. **门禁命令永不命中（R3 must-fix）**：events grep 对大写常量名零匹配 → 修 `(LLM_TRANSLATION_COMPLETED|llm:translation_completed)`（events.ts 侧 EVENT_ 前缀名）。
7. **精华入口漏门控（R3 must-fix）**：精华在 Timeline 第三 tab 而非 AI 面板 features → M2-4 触点表补 Timeline tabs 行。
8. **时间轴钉扎缺失（R3 must-fix → R4 裁决）**：任务跑 1-3 分钟期间切 timeline 会写错轨 → fail-fast 校验（弃 _update_timeline_by_id：patch 错标 / undo 快照跨轴 / envelope 分叉三理由）；accept/reject 同步钉扎（detail 增 timeline_id 键）。
9. **「线程安全由 ProjectService 保证」假前提（R3 must-fix → R4 裁决）**：project_service 全文无锁 → 删假前提，固化「UI 单飞 + 测试序列化」为 MVP 约束，Api 级锁登记 3.0.5。
10. **天数复核（R3）**：实估 13-17.5 人日（P3 原估 1-2 严重低估，S3+S4 实为 4-5.5）→ PM 裁日历 12-15 天保全量（并行窗口压缩），超期决策树 = 超 1 天砍 R2.5 → 超 3 天砍 R4.4 keep → 再超 S4 剩余版本池化。
11. **X2 修复选型（R2 suggest）**：裁前端侧（不依赖 M2 排期）；勘误搜索栏实际挂点在 AIAssistantPanel 内嵌；mainSegments 透传链 P1 先交付（翻译卡置灰判定复用）。
12. **时间码入口位置（R2 suggest → R4 勘误）**：原裁建议面板分组头，R4 发现空组守卫（SuggestionPanel.vue:54）会连入口隐藏 → 改常驻头部条（:190-199）。
13. **断言反转白名单（R1 发现）**：T1 需反转 TranscriptRow.test.ts 固化断言，与「既有测试不改断言」红线正面冲突 → 白名单例外一处 + record 登记。
14. **accept 超集兼容（R1 发现并实跑核证）**：test_subtitle_correction_review.py:157 断言 `segment_id` → 超集方案（保留旧键 + 新增 patch 键）零断言改动。

## 过程中新增发现（文档外的代码事实）

- X1 lane 建段三断链（R1 前探索报告已录，R3 复核 WaveformEditor :91/:1108-1130/:1215-229 两处用法缺传值再次确认）
- 空组守卫对时间码入口的影响（R4，SuggestionPanel.vue:54）
- 禁改面 dev.py/build.py 不在门禁扫描范围（R6，PLAN R0-5 人工核对注记）
- PRD/SPEC 测试下限口径差 ≥45/46、≥22/23（R6，PLAN 取 PRD 值为承诺下限并注记）

## 立项会结论（2026-09，用户裁决留痕）

| # | 议题 | 裁决 | 落痕处 |
|---|---|---|---|
| 1 | 日历 12-15 天 + 超期决策树授权 | **同意** | PLAN「立项会裁决登记」表（含四要素留痕要求：日期/触发信号/裁决与影响面/回写文档处）+ PRD 修订-2 ① |
| 2 | Q10 keep 完整闭环 + R4.4 首砍授权 | **同意（留痕要求同上）** | PLAN 同上 + PRD §6-Q10 / 修订-2 ② |
| 3 | 副轨删除确认默认值（无确认框 + undo 兜底） | **同意** | PRD 修订-2 ③（§10.1 观察项维持） |
| 4 | 里程碑绝对日期 | **不强制限制**（相对日程 D+n，触发式回填，不作门禁项） | PLAN 里程碑表头改「触发式回填」+ 修订-2 ④ |

立项会待确认项全部销账；PLAN P0-1 ★ 立项会 checkbox 已勾销，开工前置仅剩：四文档入库 → 拉分支 `dev-3.0.4` + tag `v3.0.4-base` → 基线首跑登记。

## 终态文档与遗留

- 三份文档交叉点终检通过：patch 层、手势裁决、红线白名单、天数口径、门禁命令、测试总数递进（pytest 716→739→752→762；vitest collected 756→760→763→779）全对齐。
- ~~待用户确认（立项会）~~ **已全部销账**（见上「立项会结论」；PRD 修订-2 / PLAN 裁决登记表为唯一真源）。
- **开工前置**：docs/3.0.4/ 四份文档入库（当前 untracked）；tag `v3.0.4-base` 于拉出点补打。

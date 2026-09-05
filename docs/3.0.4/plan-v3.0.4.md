# Milo-Cut v3.0.4 实施计划（PLAN）

> **版本**: 3.0.4（定稿——PRD/SPEC 经五轮评审终态；开工前置：立项会 ★ 确认后启动）
> **基准**: v3.0.3（tag `v3.0.3`，含修订-1 选择器防挤占追补；行号引用以探索报告同基线工作区 `55c68da` 之后为准，漂移以符号名检索兜底）
> **分支**: `dev-3.0.4` 自 tag `v3.0.3` 拉出，开工即打 tag `v3.0.4-base`（全局回滚锚点）；每步短分支 `dev-3.0.4-<step>` 合入即删
> **依据**: [PRD](./PRD-v3.0.4.md) · [SPEC](./spec-v3.0.4.md)（实施层终态；与 PRD 冲突处以 SPEC 为准，附录 C 已回写）· [探索报告](./探索报告-v3.0.4.md)（§1-§8 证据库）· record-3.0.3 §4/§5 遗留登记
> **计划文档**: `docs/3.0.4/plan-v3.0.4.md`（每完成一步勾销并回填实际结果）
> **红线**: 3.0.0-3.0.3「后端零改动」正式解除，替换为「只增不改」五条约束（PRD §1 / SPEC M0-1）；门禁从「五文件 diff 为空」改为「白名单 + diff 审查制」

---

## 0. 全局约定（适用每一步）

### 验收基线（每步合入前必须全绿）

命令与期望输出**原样取自 SPEC M5 门禁命令块**（唯一真源，本文不改写；发现冲突以 SPEC 为准并当场修本文件）：

```bash
# 后端
uv run pytest                                # ≥716 只增不减全绿（P1 起每 phase 登记当期期望总数）
uv run ruff check .                          # 0 problems（触及文件）
# 前端
cd frontend && bun run test                  # collected ≥756 且 passed = collected - 1
                                             #（唯一失败 = useRowLayout.perf.test.ts 已登记环境例）
cd frontend && bun run build                 # vue-tsc --noEmit + vite build 通过
cd frontend && bun run lint                  # eslint 0 errors 0 warnings

# 红线 R0-1：后端 diff 白名单（输出文件集必须 ⊆ M0-1 表；逐 hunk 对应 R 编号）
git diff v3.0.3 --name-only -- core/ main.py
# 禁改面必须为空输出：
git diff v3.0.3 --name-only -- pywebvue/ core/task_manager.py core/export_service.py \
  core/export_timeline.py core/track_constraints.py core/workflow_engine.py \
  core/ffmpeg_service.py core/ffmpeg_presets.py core/subtitle_service.py \
  core/timeline_utils.py core/diff_service.py core/migrations.py

# 红线 R0-2：events 双侧同步（期望输出 = 恰好两侧各 1 行新增常量）
# R3 修正（must-fix #1）：新行形如 LLM_TRANSLATION_COMPLETED = "llm:translation_completed"，
# 常量名与值均不含连续下划线串 llm_translation_completed —— 旧模式零匹配、门禁恒假绿
git diff v3.0.3 -- core/events.py | grep -E '^\+.*(LLM_TRANSLATION_COMPLETED|llm:translation_completed)'
git diff v3.0.3 -- frontend/src/utils/events.ts | grep -E '^\+.*(EVENT_LLM_TRANSLATION_COMPLETED|llm:translation_completed)'

# 红线 R0-3：断言零删改（期望 = 0；白名单外命中即 fail）
git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'
git diff v3.0.3 -- frontend/src | grep -E '^-[[:space:]]*expect\(' | grep -v 'TranscriptRow.test.ts' | wc -l

# 红线 R0-4 专项：models 只增枚举（期望 diff 仅含 LLM_TRANSLATION 行）
git diff v3.0.3 -- core/models.py
# diff 审查制：全量后端 diff 逐条对照后端改动登记表
git diff v3.0.3 --stat -- core/ main.py
```

追加口径（不改命令，仅登记）：

- **断言修改白名单唯一一处** = `TranscriptRow.test.ts:270-275`（R3.1 裁决反转同步反转，SPEC R0-3）；后端 `tests/` 断言零删改。白名单外命中即红线违规，记阻塞不放宽。
- R0-2 两条 grep 在 P1-1 合入前输出为空（常量未加）：P0 基线首跑登记「红线命令全部空/零」，自 P1-1 起按期望输出核对。
- 禁改面中的 `dev.py` / `build.py` 不在上述任何命令扫描范围：随 R0-5 diff 审查制人工核对全量 `git diff v3.0.3 --name-only` 无此二文件（SPEC 遗漏，PLAN 注记）。
- 门禁期望总数登记（record 逐 phase 回填实际值；矩阵逐组合计后端 46 / 前端 23，PRD §7 口径 ≥45 / ≥22——下限承诺取 PRD 值，SPEC 矩阵为清单级示例）：

| 合入节点 | pytest（passed） | vitest（collected / passed） | 新增依据（SPEC M5 组） |
|---|---|---|---|
| P0 基线 | 716 | 756 / 755（+1 已登记环境例） | 干净起点首跑登记 |
| P1 末 beta.1 | ≥739 | ≥760 / ≥759 | M1 管线 ≥12 + 批量写 ≥6 + expose/事件 ≥5；M1/M2 前端组 P1 份额 ≥4 |
| P2 末 beta.2 | ≥752 | ≥763 / ≥762 | M2 作用域化 ≥6 + 段源/accept ≥7；M1/M2 前端组收齐 ≥7 |
| P3 末 beta.3 | ≥762 | ≥779 / ≥778 | M4 expose ≥6 + keep ≥4；M3 前端 ≥7 + M4 前端 ≥9 |
| P4 终检 | = P3 末 | = P3 末 | 全量复跑 + 断言反转白名单核对 |

### 提交与记录

- 一步一短分支一合入（`dev-3.0.4-<step>`，合入即删）；两段式提交（`type(module): 摘要` + `-` 列表，不带版本号）
- 每步完成即勾销本文件 + 写 `docs/3.0.4/record-3.0.4-<step>.md`（改动文件清单、验证命令与实际输出、未验证边界）
- **后端改动登记表**：每步 record 按 SPEC 附录 A 模板追加（phase / 文件 / hunk 摘要 / R 编号 / 红线类别），P4 终检逐条核对；无 R 编号对应的 diff 要么补登记要么回退
- 验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注「可并行」的步骤）
- 文档类提交（P0-1 入库、各步 record 与本文件勾销）走 `docs(...)` 两段式提交，直接落 `dev-3.0.4`；代码步骤一律走短分支

### 批次顺序强制（SPEC M0-3）

```
P1: M1（R1.2 管线 → R1.3 批量写 → R1.4/R1.5 事件与前端）→ v3.0.4-beta.1
    （R1.1 前端入口卡片依赖的 mainSegments 透传链在 P1 交付，P3 的 X2 复用，见 M3-3）
P2: M2（R2.1 后端 → R2.2/R2.3 → R2.4 前端；R2.5 为 P2 尾项，S4 开工即让位）→ beta.2
P3: M3（顺序强制 R3.1 → R3.2 → R3.3）→ M4（X1 合入后再上 M4-2 手势，同文件防冲突）→ beta.3
P4: M5 终检 + README_zh 回填 + 双平台真机清单（含 3.0.3 顺延债）→ RC → 正式
```

R3 增补 4 条顺序约束的落点：① golden 先行 → **P3-1**（本版首步，见下裁决）；② props 链 P1 合并 → **P1-6**；③ M4-3 ∥ M4-1 并行开发、生命周期验收在 M4-1 合入后 → **P3-5/P3-7**；④ 切轨完成分支进边界用例 → **P1-5**（M1 expose/事件组）。

**PM 排期裁决（本文件新增，冲突处以 SPEC M0-3 为准）**：golden 基线采集置为 **P3 首步（P3-1）**，而非 M3 三步之后——SPEC M0-3 约束 1 明文要求「随 P3 首个 commit 入库」，若排在 R3.1 之后则 P3 首 commit 已被占据；采集与 M3 无依赖、前置零成本，且距 `:2560-2661` 触碰点（P3-9）更远。

### 需要用户协助的事项（汇总，各步内不再重复标注 ★）

| 节点 | 请求内容 |
|---|---|
| 立项会（P0-1） | **已裁决（2026-09，四项结论见下方「立项会裁决登记」）**：① 日历 12-15 天 + 超期决策树授权——**每次触发须留痕**；② Q10 keep = 完整闭环维持 + R4.4 首砍授权——**砍项触发须留痕**；③ 副轨删除确认默认值 = 无确认框 + undo 兜底；④ 里程碑**不强制绝对日期**——维持相对日程 D+n，触发式回填 |
| beta.1（P1 末） | 双平台冒烟：**翻译全链路**（入口语言记忆 / 进度 / 完成自动切轨 / undo 整轨回退 / 千段耗时与 token 观测）+ **双语导出** + **播放双语第二行**（SPEC M5 清单 1）；建议至少覆盖一家非 json_mode provider（Qwen/GLM/Ollama） |
| beta.2（P2 末） | 双平台冒烟：**纠错双轨**（轨徽门控 / 主轨待审集不丢 / 审阅来源轨标注 / accept patch 无全量刷新 / undo）+ 主轨纠错回归（M5 清单 2） |
| beta.3（P3 末） | 双平台冒烟：M5 清单 3-6（编辑扫掠副轨 / lane 建段 / 语义搜索 / 手动范围含 keep 重跑场景） |
| RC（P4） | 双平台**全量回归**：M5 清单 1-7 全复跑 + **3.0.3 顺延债**（建议面板/红罩层多行视觉回归）+ 多行 × 列表联动组合态 → 签字 |
| 发布 | **tag 落地签字**：`v3.0.4-rc.1` → 合并主干 → `v3.0.4` |

### 立项会裁决登记（2026-09，留痕——后续任何范围/日程裁决同格式追加于此与 record-3.0.4.md）

| # | 议题 | 用户裁决 | 留痕要求 |
|---|---|---|---|
| 1 | 日历 12-15 天（人日 13-17.5 不折减）+ 超期决策树授权 | **同意** | 决策树**每次触发必须留痕**：日期 / 触发信号（偏差天数与观测点）/ 裁决内容 / 影响面（砍了什么、波及哪些 R 编号）/ 回写文档处（PLAN 步骤注记 + record-3.0.4.md 对应 phase 节 + PRD §0.2 与相关 R 条目 + SPEC 对应 M 条目「已砍（日期）」标注），四者齐备方可执行 |
| 2 | Q10 keep 完整闭环维持 + R4.4 首砍缓冲阀授权 | **同意（同上留痕要求）** | R4.4 砍项执行时按上表四要素登记；PRD §6-Q10 与 SPEC M4-4 同步标注 |
| 3 | 副轨删除确认策略默认值 | **同意**（无确认框 + undo 兜底） | 维持既有登记（PRD §10.1 观察项）；若真机误删证据出现而加确认框，按变更登记于 record |
| 4 | 里程碑绝对日期 | **不强制限制** | 里程碑维持相对日程（D+n）；绝对日期**触发式回填**（用户主动给出或 RC 排期需要时），不作为门禁项 |

---

## Phase 0: 开工准备（0.5-1 天）

### P0-1 分支、tag 与基线快照（含四文档入库）

- [x] ★ 立项会：确认 12-15 天日历 / Q10 keep 完整闭环 + R4.4 首砍授权（触发留痕）/ 副轨删除确认默认值 / 里程碑不强制绝对日期——**已裁决（2026-09），四项结论登记于「立项会裁决登记」表**
- [x] 从 tag `v3.0.3` 拉出 `dev-3.0.4`；打 tag `v3.0.4-base`（**打在拉出点 = `v3.0.3` 所指 commit**，先于文档入库——锚点是纯代码回滚点，门禁 diff 基准恒为 `v3.0.3` 不受影响）
- [x] **四文档入库**：`docs/3.0.4/` 探索报告 / PRD / SPEC / PLAN（当前 untracked，执行者 Round 3 核实）以 `docs(3.0.4): ...` 两段式提交（commit `83a61d6`，review-log 随同入库）
- [x] 建 `docs/3.0.4/record-3.0.4.md` 总记录骨架（含后端改动登记表总表，SPEC 附录 A 模板；每 phase 追加，P4 终检即归档处）
- [x] 门禁基线首跑登记：pytest 716 全绿 / vitest 756 collected·755 passed（唯一失败 = `useRowLayout.perf.test.ts` 已登记环境例）/ build / lint / ruff 全绿；红线命令输出全部为空/零（详见 record-3.0.4-P0-1.md；注：本执行环境 `bun run` 不可用已按 P0-2 回落条款以 node 直跑等价命令并登记）
- [x] ★ 通知用户计划启动

**验收方式**: `git tag` 存在 `v3.0.4-base`；`git status --short docs/3.0.4/` 干净；基线数字与红线空输出记录于 record-3.0.4-P0-1.md。
**验收标准**: 门禁命令首跑全绿（零改动的干净起点）。

### P0-2 红线门禁脚本化（PM 裁决：脚本固化，非手动命令块）

- [x] 新建 `scripts/gates-v3.0.4.sh`（仓库已有 scripts/ 惯例）：后端门禁 / 前端门禁 / 红线检查三段，**命令与期望输出原样封装 SPEC M5，零改写**（仅加段落标题与汇总 exit code）
- [x] 双环境 dry-run（macOS bash / Windows Git Bash）输出与手动逐条执行一致；P0 时点红线段全部空/零（**本执行环境仅 Linux bash 可用，双环境 dry-run 顺延 beta.1 真机补验，已登记 record-3.0.4-P0-2.md §4**；P0 时点红线段全部空/零已验证）
- [x] 固化执行约定：每 phase 合入前执行一次、stdout 全文贴当步 record；**SPEC 与脚本冲突以 SPEC 为准当场修脚本**；shell 环境受限时回落命令块手动执行 + record 登记（不得因脚本问题阻塞合入）

**裁决理由**: 红线命令从 3.0.3 的 1 条扩为 9+ 条判等式，人工逐条执行易漏且不可复核；脚本化后回到「一条命令」成本，输出可直接归档。脚本落 scripts/（新增文件，不在 `core/ main.py` diff 白名单审查范围，R0-5 不受影响），commit 用 `chore(gates): ...`。
**验收方式**: 脚本在基线工作区跑通且三段汇总 exit 0（红线段空/零）。

---

## Phase 1: S1 翻译副轨（4.5-6 人日，M1）→ `v3.0.4-beta.1`

### P1-1 任务类型与事件常量双侧（core/models.py · core/events.py · events.ts）

- [x] `core/models.py` TaskType 追加 `LLM_TRANSLATION = "llm_translation"`（LLM 区块末尾，1 行 + 注释）
- [x] `core/events.py` + `frontend/src/utils/events.ts` 双侧各新增 1 常量（`LLM_TRANSLATION_COMPLETED` / `EVENT_LLM_TRANSLATION_COMPLETED` = `"llm:translation_completed"`，**同一 commit**，R0-2）

**验收方式**: M5 组 = M1 expose/事件（事件双侧登记项）；R0-4 专项 `git diff v3.0.3 -- core/models.py` 仅含该行；R0-2 两条 grep 恰好各命中 1 行。
**验收标准**: 全套门禁全绿（红线命令自此步起按期望输出核对）。

### P1-2 translation prompt 注册（core/llm_prompts.py）

- [x] 新增 `_TRANSLATION_SYSTEM`（逐条 JSON 数组 / id 原样回传 / `{{target_language}}` 占位 / 不得增删条目）+ `DEFAULT_PROMPTS["translation"]`，**`params` 必须为 `{}`**（占位符穿透三层的前提）
- [x] 用例：`{{target_language}}` 穿透三层各一路（硬编码默认 / settings / 项目覆盖）+ override 路径替换正确（tests/test_translation_prompt.py 13 用例；override 路径本步断言「原文返回、占位符不动」，终替换断言随 P1-5）
- [x] 终替换与残留 `{{` fail-fast 用例的落点登记：替换逻辑在 handler（P1-5 步骤 2），用例随 P1-5 挂 M1 管线组（PLAN 微裁决，SPEC M1-3 未定测试宿主）——已落地：本步仅登记，用例随 P1-5

**验收方式**: M5 组 = M1 管线（占位符项）。
**验收标准**: 门禁全绿；`core/llm_prompts.py` diff 仅含注册项（白名单 R1.2）。

### P1-3 翻译批处理管线（core/llm_service.py）

- [x] 新增 `analyze_subtitle_translation(...)` 及私有辅助（复刻纠错骨架 :935-1218：批窗 30 / 字符预算 4000 / 并发 5 / opaque id / 4 层 JSON 解析 / BatchLedger / 每批一次重试 / 连续 429 转串行 / cancel 逐批检查 / progress 批粒度）
- [x] **coverage 反向校验**：全量输出守恒——输出 id 集 ≠ 目标 id 集（漏译或多译）的批重试后仍失败 → 记 ledger 失败、任务失败零落盘
- [x] 上下文 = **源文** ±ctx 窗口（并发 5 保留，「定稿译文滑动窗」登记版本池，SPEC M1-2 裁决）
- [x] 用例：批窗+字符预算收缩；漏译批/多译批进 ledger；429 转串行；非 json_mode 4 层解析 ×3（坏 JSON / 围栏 / 前后缀噪声）；取消中途退出已完成批不写；opaque id 回映射（tests/test_llm_translation.py 20 例，详见 record-3.0.4-P1-3.md §6）

**验收方式**: M5 组 = M1 管线 ≥12。
**验收标准**: 门禁全绿；`core/llm_service.py` diff 仅含新增函数（白名单 R1.2）。

### P1-4 批量落盘方法（core/project_service.py）

- [x] 新增 `create_translation_track(timeline_id, name, language, items, bind=True)`：写侧重复语言再查（双保险）→ 幂等对账（segment_id 逐个对照当下主轨，落空进 `uncovered_ids` 不静默，全部落空拒绝）→ 同 start/end 复制主轨时间 + 按 id 精确 1:1 建 offset=0 bindings → **单 `_success_patch(tracks=…, bindings=…)` 落盘**（禁止循环 `add_track_segment`）
- [x] 时间轴钉扎双保险：方法入口断言 `timeline_id == active_timeline_id`，不符零写入（M1-4 契约 6）
- [x] 用例：千段级（参数化 1000 段）单 patch revision 恰好 +1 / tracks+bindings 完整 / undo 一次回退整轨含 bindings；重复语言拒绝；部分落空落盘 + uncovered 上报；全部落空拒绝；bind=False 路径

**验收方式**: M5 组 = M1 批量写 ≥6。
**验收标准**: 门禁全绿；`core/project_service.py` diff 仅含本方法（`generate_subtitle_keep_ranges` 此时零触碰）。

### P1-5 handler 与 expose 接线（main.py）

- [x] 注册块追加 `_handle_translation`（main.py:140-167 区）+ `@expose start_translation(target_language, timeline_id, track_name)`（六步校验序：LLM configured → project open → 语言合法 → 主轨有 subtitle 段 → **同语言 translation 轨拒绝**（文案含「可清空或删除该轨后重试」）→ create_task）
- [x] `_handle_translation` 五步流程：读主轨段排除 confirmed-deleted → resolve prompt + `{{target_language}}` 终替换（残留 `{{` 即 fail-fast）→ `analyze_subtitle_translation` → **完成时时间轴钉扎校验**（payload.timeline_id ≠ active → failed 零落盘，文案带回到原时间轴重试指引）→ `create_translation_track` + emit `llm:translation_completed`（payload 含 uncovered_ids/ledger）+ emit `llm:token_usage`
- [x] 失败/取消/部分失败五情形语义按 SPEC M1-5 表落齐；并发约束 = UI 单飞 + 测试序列化（不构造并发写断言；MiloCutApi 级锁登记 3.0.5）
- [x] 用例：start_translation 四分支校验；handler 注册与调度（mock LLM）；uncovered 随完成事件上报；**运行期切时间轴 → 钉扎校验 failed 零落盘（M0-3 约束 4 边界用例）**；终替换 + 残留 fail-fast

**验收方式**: M5 组 = M1 expose/事件 ≥5。
**验收标准**: 门禁全绿；`main.py` diff 对应 R1.2/R1.5（登记表逐 hunk 登记）。

### P1-6 前端闭环与 props 链一次接通（AIAssistantPanel · Timeline · WorkspacePage · useLlmTasks）

- [x] AIAssistantPanel 第 4 卡「翻译为新副轨」+ `FeatureKey` 联合类型追加 `"translation"`（:22）+ 内联语言对话框（清单 9 项 BCP-47 / 记忆上次写 config 键 / 「约 N 批」= ceil(主轨段数/30) 标注「约」）+ 主轨无 subtitle 段置灰（判定源 = mainSegments）
- [x] **props 链一次改动全部接通（M0-3 约束 2）**：WorkspacePage → Timeline → AIAssistantPanel 透传 `mainSegments`，同链同 commit 接通 `active-track-id` / `active-track-name`（Timeline 已收 activeTrackId，缺的仅 Timeline→面板一级）——P2 的 M2-4 只消费不再动 props 链
- [x] useLlmTasks：`startTranslation(targetLanguage)` + 单例消费完成事件存 `lastTranslationCompletion`；WorkspacePage `watch` → `handleSelectListTrack`（自带 flush 前置）→ `selectTrack` 完成自动切轨
- [x] 任务 start 前 `pushSnapshot(["tracks","bindings"], "AI翻译副轨")`；完成后刷新走 task:completed 剥离 → `get_project`（同纠错模式）；uncovered 非空 toast + 结果面板明示清单
- [ ] 用例：翻译卡置灰 / 语言记忆跨会话 / 完成切轨（watch → handleSelectListTrack）/ undo 三层一致（M1/M2 前端组 P1 份额 ≥4）
- [ ] ★ beta.1 冒烟（用户协助表）+ 打 tag `v3.0.4-beta.1` + record（**登记 2026-09：代码闭环与全门禁已交付，tag `v3.0.4-beta.1` 已打在 P1-6 合入 commit；真机冒烟待用户执行，继承 3.0.3 冒烟后置先例，异常走 smoke-fix**）（代码闭环完成；真机冒烟待用户执行，tag 已按后文登记先行）

**验收方式**: M5 组 = M1/M2 前端（P1 份额）；vitest collected ≥760。
**验收标准**: 翻译全链路冒烟合并 beta.1 ★ 节点。

---

## Phase 2: S2 纠错感知当前轨（3-4 人日，M2）→ `v3.0.4-beta.2`

### P2-1 expose 轨道形参（main.py）

- [x] `start_subtitle_correction` 增可选形参 `track_id: str = ""`，非空时入 task payload（默认空 = 主轨，既有调用零影响）
- [x] 用例：track_id 缺省时主轨行为与 v3.0.3 完全一致（既有断言零改动全绿；新增 tests/test_correction_track_payload.py 双证）

**验收方式**: M5 组 = M2 段源/accept（缺省一致项）。
**验收标准**: 门禁全绿；diff 属登记改点（R2.1）。

### P2-2 handler 副轨分支（main.py）

- [ ] `_handle_subtitle_correction`：track_id 非空时段源取对应轨 segments；bindings 反查表跳过 confirmed-deleted 主轨段的绑定副轨段（无绑定段保留）；partial hints 跳过（裁决：主轨 EditDecision 概念不改造）；store 透传 `track_id`
- [ ] 轨不存在 → 任务 failed「Track not found」
- [ ] 用例：删除主轨段 + 绑定副轨段被跳过；无绑定段保留；轨不存在失败

**验收方式**: M5 组 = M2 段源/accept（段源三项）。
**验收标准**: 门禁全绿。

### P2-3 pending 作用域化（core/correction_service.py，本模块最高风险）

- [ ] `store_subtitle_corrections` 增形参 `track_id`：seg_map 按 scope 构建；detail JSON 增键 `track_id` 与 `timeline_id`（后者供 P2-4 钉扎）；互清精确到「detail.track_id == 本次 track_id」
- [ ] 兼容规则：存量 detail 无 track_id / timeline_id 键缺省按主轨作用域 / 放行（`test_store_clears_previous_corrections` 既有断言零改动通过）
- [ ] `get_subtitle_corrections`：输出逐条附 track_id / track_name；**悬空过滤**（detail.track_id 非空且轨已删除 → 跳过不出现在列表）
- [ ] 用例：双轨 pending 互不干扰（双向，**序列化调用编排**）；重跑同轨只清同轨；存量兼容；主轨两次 store 计数不翻倍复跑；悬空过滤；输出附轨（M2 作用域化 ≥6）

**验收方式**: M5 组 = M2 作用域化 ≥6。
**验收标准**: 门禁全绿；`accept_high_confidence_corrections` / `clear_subtitle_corrections` 保持 timeline 级零改动。

### P2-4 accept/reject 超集 patch 化（core/correction_service.py + useWorkspaceActions.ts）

- [ ] accept 主轨路径逻辑不变，返回值超集：保留 `segment_id` 键（:157 断言零改动兼容）+ 新增 `patch` 键（层 = **segments + analysis**）
- [ ] accept 副轨路径：定位轨与轨内段 → 复用 `_assert_timestamps_unchanged` + `reattach_words`（空输入跳过 reattach）→ `track.model_copy` 整体替换 → 返回 patch（层 = **tracks + analysis**，不动 bindings）
- [ ] reject 同步超集（层 = analysis）；**accept/reject 时间轴钉扎**：detail.timeline_id 非空且 ≠ active → 明确报错零写入
- [ ] 前端消费：`handleAcceptCorrection` / `handleRejectCorrection` 调用前按 scope `pushSnapshot`（捕获层主轨 `["segments","analysis"]` / 副轨 `["tracks","analysis"]`）；响应含 patch → 走 `applyProjectPatch`，**移除 `switch_timeline` 全量刷新 workaround**；时间轴切换后 pendingCorrections 重取
- [ ] 用例：accept 主轨超集 / 副轨写轨文本且 bindings 不变 / reject 超集 / reattach 空输入 / revision 单调 +1 不再 switch_timeline（**新建宿主 `useWorkspaceActions.test.ts`**）/ undo 一次回退 accept + redo 对称

**验收方式**: M5 组 = M2 段源/accept 余项 + M1/M2 前端（applyProjectPatch 项）。
**验收标准**: 门禁全绿；`test_subtitle_correction_review.py` 既有断言全绿。

### P2-5 前端门控与审阅（AIAssistantPanel · Timeline · WorkspacePage · useLlmTasks）

- [ ] AIAssistantPanel prop 门控：轨模式下智能删除/精华/工作流置灰 + 「仅主轨可用」文案；纠错卡可用 + 显式轨徽（「当前轨：{track_name}」，锁定不弹选择）；搜索卡不置灰
- [ ] Timeline tabs 精华门控：轨模式下「精华」tab 置灰（disabled + title）；`isTrackMode` 变 true 且停留在精华 → 自动回落 suggestion tab
- [ ] useLlmTasks `startSubtitleCorrection(referenceText, trackId?)` 透传；WorkspacePage 调用点传 `activeListTrackId ?? ""`
- [ ] 审阅 modal：条目按 track_id 解析显示段与时间 + 来源轨徽；renderDiff 纯文本渲染不变
- [ ] 用例：置灰态点击不 emit start；轨徽名称；精华 tab 置灰 + 停留回落；主轨视图零回退（M1/M2 前端组收齐 ≥7）
- [ ] ★ beta.2 冒烟（用户协助表）+ 打 tag `v3.0.4-beta.2` + record

**验收方式**: M5 组 = M1/M2 前端（门控项）；vitest collected ≥763。
**验收标准**: 纠错双轨冒烟合并 beta.2 ★ 节点。

### P2-6 可选尾项：对齐主轨上下文（core/llm_service.py，R2.5）

- [ ] 副轨纠错经 bindings 把主轨对齐文本附进 `_build_structured_user_message` 的 extra_context；无绑定段自动退化
- [ ] 用例：有绑定段请求上下文含主轨对齐行；无绑定段正常出结果（2 例）
- [ ] **让位线标注（超期第一缓冲阀）**：P3（S4）开工即砍，砍则不产生任何半成品代码

**验收方式**: M5 组 = M2 段源/accept（上下文增强项，可让位）。
**验收标准**: 若让位则在 record-3.0.4.md 登记砍项理由，Phase 2 里程碑不受阻。

---

## Phase 3: S3 前端顺带批 + S4 手动范围（4-5.5 人日，M3+M4）→ `v3.0.4-beta.3`

> M3 三步（P3-2/P3-3/P3-4）纯前端不依赖后端，**可与 P1 并行开发**，但合入统一走 P3 门禁（M0-3）。

### P3-1 golden 基线采集（tests/ golden 数据文件，M4-4 前置 = M0-3 约束 1）

- [ ] `git worktree` 检出 tag `v3.0.3` 干净基线工作区，以固定段集 + padding 扫描运行 `generate_subtitle_keep_ranges`，输出 dump 固化为 tests/ 下 golden 数据文件
- [ ] 采集生成脚本随 fixture 一并入库（SPEC 未定形态——PLAN 裁决：入库保可复跑，采集环境登记 record）
- [ ] 对拍用例骨架：无用户 keep 的工程 → 输出与 golden **逐字节一致**（P3-9 改造后该用例即零回退判据）
- [ ] 随 **P3 首个 commit** 入库（本步即 P3 第一短分支，先于 P3-2 合入）

**验收方式**: golden 文件 + 对拍用例在本步合入；`git diff v3.0.3 -- core/` 此时不包含 `:2560-2661` 任何改动。
**验收标准**: 先改后采 = 基线自带改动、对拍失义——本步是硬前置。

### P3-2 编辑扫掠覆盖副轨（TranscriptRow.vue · TranscriptRow.test.ts · Timeline.vue，R3.1）

- [ ] 删除 `TranscriptRow.vue:324-337` 两处 track 早退（onMounted 条件 + watch 守卫）——副轨行随 `globalEditMode` 进入/退出行内编辑
- [ ] **断言反转白名单执行**：`TranscriptRow.test.ts:270-275` 整体改写为「enters text edit under globalEditMode (track variant)」，record-P3 登记反转条目与理由（白名单唯一一处）
- [ ] 新增断言：切换轨视图前未决防抖先 flush（挂 WorkspacePage `handleSelectListTrack`：flush 回调先于 selectListTrack 执行）；编辑态跨轨保持固化 1 例
- [ ] Timeline 按钮文案感知轨道视图（副轨视图「编辑〈轨名〉」/「退出编辑」，主轨视图文案不变）
- [ ] 用例：反转用例 + flush + 跨轨保持（M3 前端 R3.1 部分 ≥3）

**验收方式**: M5 组 = M3 前端；前端断言 grep 白名单外命中 = 0。
**验收标准**: 主轨既有断言全绿；撤销谓词表零新增（text 恒 `["tracks"]`）。

### P3-3 lane 建段接线（WaveformEditor.vue · WaveformRow.vue，R3.2/X1）

- [ ] 三处接线：① multi 路径 WaveformRow 追加 `:build-mode` + `@create-at-in-track` 桥（0.5s 默认宽）；② WaveformRow 的 TrackLane 追加 `:build-mode`；③ basic 路径 TrackLane 追加 `:build-mode` + `@create-at` 桥
- [ ] 用例：建段模式 lane 点击 → `track-create` 上抛 `(trackId, t, t+0.5)`（multi / basic 各 1）；OFF 时 lane 点击无动作（零回退断言）

**验收方式**: M5 组 = M3 前端（X1 项 ≥3）。
**验收标准**: 不改 TrackLane.onLaneClick 与 handleTrackCreate 既有逻辑；本步先于 M4-2 手势合入（同文件防冲突，M0-3）。

### P3-4 语义搜索轨模式修正（SemanticSearchBar.vue · AIAssistantPanel.vue，R3.3/X2）

- [ ] SemanticSearchBar 新增 `mainSegments?: Segment[]` prop，segmentMap 改建自 `props.mainSegments ?? props.segments`；AIAssistantPanel 透传（复用 P1-6 链延伸一级）
- [ ] 用例：轨模式传副轨 segments + 主轨 mainSegments + 主轨 id 结果 → 文本非空且时间正确、点击定位主轨命中段；主轨模式零变化（不传时与 v3.0.3 一致）——**新建宿主 `SemanticSearchBar.test.ts`**

**验收方式**: M5 组 = M3 前端（X2 项 ≥2）。
**验收标准**: 后端零改动（显示侧数据源对齐）。

### P3-5 add_range_decision expose（core/project_service.py · main.py，R4.1）

- [ ] `ProjectService.add_range_decision(start, end, action, source="manual")`：clamp 到媒体时长（media 缺失取主轨段 end 上界，**空序列先拒**）→ clamp 后 end≤start 拒 → action 校验 → **±0.05s 同 action 幂等返回既有 edit（`duplicate: True`）/ 跨 action 放行 / 非近似重叠放行** → uuid id + 默认 pending + `_success_patch(edits=…)`
- [ ] main.py `@expose add_range_decision`；前端调用前 `pushSnapshot(["edits"], "手动范围")`
- [ ] 用例：全生命周期闭环（建 → 审 → 确认 → 导出预览包含该区间与 subtitle_trim 并列去重 → 单条删除 → 再建同参幂等）；clamp 越界；倒序拒绝；跨 action 放行（M4 expose ≥6）
- [ ] M4-3 面板/覆层可与本步**并行开发**（M0-3 约束 3），生命周期验收在本步合入后串行执行

**验收方式**: M5 组 = M4 expose ≥6（即探索报告 §5.4 测试缺口 #4 补测）。
**验收标准**: 门禁全绿；模型/patch/导出零改动。

### P3-6 范围标记 toggle 与确认气泡（WaveformEditor.vue · SegmentBlocksLayer.vue，R4.2）

- [ ] 波形工具栏新增「范围标记」toggle（对齐建段先例 :1012-1017），**默认 OFF**；ON 时主轨空白区 press-drag 框选 → 松手确认气泡（删除/保留二选 + 取消，内嵌 WaveformEditor 不建新组件，默认聚焦「删除」）→ `add_range_decision`；`selectedRange` 死代码激活为气泡数据源
- [ ] `emptyAreaMode` 联合类型增 `"range"`；两处绑定改嵌套三元 `rangeMode ? "range" : buildMode ? "add" : "seek"`（**双 toggle 同 ON 时范围模式获胜** + UI 互斥提示）；SegmentBlocksLayer `handleEmptyClick` 增 `"range"` 分支 emit `range-press`
- [ ] multi 侧路由置于 else 分支之前、ctrl/shift 判断之后（**Ctrl/Shift 优先级高于范围模式**）
- [ ] 用例：手势矩阵逐格 vitest（ON 6 格 + OFF 3 格零回退断言）；Ctrl-create 建段与 v3.0.3 完全一致；气泡二选一落盘 + 取消（M4 前端手势部分）

**验收方式**: M5 组 = M4 前端（手势矩阵项）。
**验收标准**: 既有 WaveformEditor 建段测试不改全绿；范围标记仅主轨域。

### P3-7 建议面板手动范围分组 + 时间码 popover（SuggestionPanel.vue，R4.3a）

- [ ] 新增第三源分组「手动范围」（`source === "manual"` 过滤，与静音/智能删除并列）：条目 label `删除/保留 {时长}s` + status 徽；逐条确认/拒绝复用 `update_edit_decision`、删除复用 `delete_edit_decisions_batch`（**后端零新增**）；确认文案显式「**确认 = 参与裁剪计算**」
- [ ] 时间码 popover：面板**常驻头部条**（:190-199）「+ 时间码」按钮 + 起止两输入（不放分组头——push 空组守卫会连入口一起隐藏）；非法输入 end≤start 拒；与气泡共用 `add_range_decision`
- [ ] `SUGGESTION_SOURCES` 与计数器并入 manual；全链 `pushSnapshot(["edits"])`
- [ ] 用例：面板分组生命周期闭环（建→审→确认→删除）+ 时间码入口（**新建宿主 `SuggestionPanel.test.ts`**）

**验收方式**: M5 组 = M4 前端（面板项）。
**验收标准**: 既有静音/智能删除两分组断言全绿。

### P3-8 覆层三态（SegmentBlocksLayer.vue，R4.3b）

- [ ] `visibleEditRanges` computed 增输出 `edit.action` / `edit.status`，模板三态：confirmed delete = 现状红色斜纹**逐字节不变**；pending = 同款半透明降档；keep（任意 status）= 蓝色系斜纹/描边
- [ ] `deleteRanges` 不含 pending 手动范围：现状过滤零改动，补 1 条快照锁定用例（跳播/进度条红罩/导出预览不受 pending 影响）
- [ ] 用例：覆层三态样式 + confirmed delete 样式与 v3.0.3 一致（M4 前端覆层部分）

**验收方式**: M5 组 = M4 前端（覆层项）。
**验收标准**: 门禁全绿。

### P3-9 keep 闭环（core/project_service.py 受控改点 ①，R4.4）——**S4 首砍项**

- [ ] keep 集合感知：收集 confirmed keep range（不限 source）→ 与自动 keep_ranges 排序合并 → keep 区间从删除区间补集中自然扣除
- [ ] **陈旧 trim 剔除**：既有 `source="subtitle_trim"` delete edit 与任一 confirmed keep 相交 → 从 edits 移除，计数入返回 data `invalidated_count` + log
- [ ] golden 对拍启用：无用户 keep 的工程输出与 v3.0.3 **逐字节一致**（P3-1 基线）；keep 与手动 delete 并存时导出服从 delete（优先级用例）
- [ ] **首砍项标注（超期第二缓冲阀）**：触发即整体移除——气泡「保留」选项 + P3-8 keep 样式 + 本节全部，**不降级为「可标不消费」半吊子**
- [ ] 用例：keep 打穿删除区间；陈旧剔除 + invalidated_count；golden 对拍；导出优先级（M4 keep ≥4）
- [ ] ★ beta.3 冒烟（用户协助表）+ 打 tag `v3.0.4-beta.3` + record（含断言反转白名单登记汇总）

**验收方式**: M5 组 = M4 keep ≥4；pytest ≥762 / vitest collected ≥779。
**验收标准**: `generate_subtitle_keep_ranges` 是本版唯一「改」点之一——diff 审查制重点审查项。

---

## Phase 4: 收尾与发布（1-1.5 天）→ `v3.0.4-RC → 正式`

### P4-1 门禁终检

- [ ] `scripts/gates-v3.0.4.sh` 全量复跑：后端/前端门禁 + 红线 R0-1~R0-4 全部按期望输出，stdout 贴 record
- [ ] **后端改动登记表逐条核对**（R0-5）：`git diff v3.0.3 --stat -- core/ main.py` 每 hunk 对应 R 编号；人工核对全量 name-only 无 `dev.py` / `build.py`
- [ ] 断言反转白名单核对：前端 expect 删除仅 TranscriptRow.test.ts 一处；后端 assert 删除 = 0

**验收方式**: 脚本三段 exit 0；登记表无「无对应 R 编号」残留。
**验收标准**: 期望总数达 P3 末登记值（pytest ≥762 / vitest ≥779）。

### P4-2 性能对账（口径说明）

- [ ] 本版**不新建后端 perf 基线**（PRD/SPEC 均未立项）：对账口径 = ① M1-4 千段单 patch（revision +1 而非 +N）；② M2-3 accept 后无 O(project) 全量刷新（revision 单调 +1）；③ beta.1 真机千段翻译耗时与 token 观测——三项落 record-3.0.4.md 性能对账段
- [ ] `useRowLayout.perf.test.ts` 环境例维持豁免口径，不新设基线（根修登记清债池）

**验收方式**: record 性能对账段回填。
**验收标准**: 与 3.0.3「无新基线文件则回填对账段」先例一致。

### P4-3 文档与版本池回写

- [ ] README_zh 集中回填：3.0.x 特性段落 + 3.0.4 新特性（翻译副轨 / 纠错轨道感知 / 手动范围）+ **翻译轨级联删除语义说明**（Q8）；README.md 补 3.0.4 增量段（对齐 3.0.3 先例）
- [ ] 版本池注记回写（PRD §10.2）：新增登记 6 项（T1-B / 重叠段迁移观察项 / 增量补译 / 逐批流式预览 / 定稿译文滑动窗 / accept_high_confidence 与 clear 作用域化）+ 出池 1 项（翻译管线）
- [ ] 副轨删除确认策略再评估结论落盘（§10.1：beta.1 起观察误删证据，默认维持无确认框 + undo 兜底）

**验收方式**: 文档 diff 入 record。
**验收标准**: record-3.0.3 §5 遗留 #2/#4 销账。

### P4-4 真机冒烟清单（双平台，含 3.0.3 顺延债并入）

- [ ] ★ SPEC M5 清单 1-7 全量复跑：翻译全链（含 undo、千段观测）/ 纠错双轨 / 编辑扫掠副轨 / lane 建段 / 语义搜索 / 手动范围（toggle / 气泡 / 面板 / keep 重跑 / 时间码 / Ctrl-create 回归）/ 主轨零回退抽查
- [ ] ★ **3.0.3 顺延债**：建议面板 / 红罩层多行视觉回归（与 S4 新分组合并补验，Q15）+ 多行 × 列表联动组合态

**验收方式**: 双平台清单逐项勾选，异常项走 smoke-fix 流程。
**验收标准**: 全绿或遗留登记后用户签字。

### P4-5 发布

- [ ] 版本号 bump 3.0.3 → 3.0.4（版本承载处照 3.0.3 release 先例）+ 门禁复跑
- [ ] ★ 用户 RC 签字 → tag `v3.0.4-rc.1` → 合并主干 → tag `v3.0.4`（tag 落地签字）
- [ ] `docs/3.0.4/record-3.0.4.md` 总记录归档：交付概览 / 门禁终态（脚本输出）/ 登记表终态 / 断言反转白名单 / 性能对账 / 版本池回写 / 遗留清单

**验收方式**: tag 链 `v3.0.4-base → beta.1 → beta.2 → beta.3 → rc.1 → v3.0.4` 完整。
**验收标准**: 总 record 归档，版本收口。

---

## 里程碑与缓冲

| 里程碑 | 内容 | 相对占位（开工日 D0） | 绝对日期（不强制——立项会裁决 2026-09：触发式回填） |
|---|---|---|---|
| `v3.0.4-beta.1` | P1 末：S1 翻译副轨全链 | D0+5 ~ D0+8 | （触发式回填） |
| `v3.0.4-beta.2` | P2 末：S2 纠错双轨 | D0+9 ~ D0+12 | （触发式回填） |
| `v3.0.4-beta.3` | P3 末：S3+S4（SPEC M0-3 锚点，较任务书三锚点补列） | D0+11 ~ D0+14 | （触发式回填） |
| `v3.0.4-rc.1` | P4 门禁终检 + 冒烟全绿 | D0+12 ~ D0+15 | （触发式回填） |
| `v3.0.4` 正式 | 签字 → 主干 → tag | rc.1 后 0-1 天 | （触发式回填） |

**口径说明**：人日 **13-17.5**（SPEC 规模注记：P1 4.5-6 / P2 3-4 / P3 4-5.5 / P0+P4 1.5-2，P0 0.5-1 与 P4 1-1.5 两端不同时取上界）；日历 **12-15 天** = PM 裁决（PRD §7）：人日不乐观折减，压缩全部来自并行开发窗口——M3 与 P1 并行开发（合入走 P3 门禁）、M4-3 与 M4-1 并行、P0 前置与探索收尾部分重叠。

**超期决策树**（触发即提请用户，PM 不擅自降级；**立项会授权 + 留痕约束 2026-09**——每次触发按「立项会裁决登记」表四要素留痕：日期 / 触发信号 / 裁决内容与影响面（R 编号级）/ 回写文档处（PLAN 步骤注记 + record-3.0.4.md + PRD 相关条目 + SPEC 对应 M 条目「已砍（日期）」），四者齐备方可执行）：

```
日历偏差 ≤ 1 天   → 第一缓冲阀：砍 R2.5（未开工即不入；P2 已过则等效冻结）
偏差 ≤ 3 天（或 R2.5 已耗尽仍超）→ 砍 R4.4 keep 整体（气泡「保留」+ 覆层 keep 样式 + M4-4 全部）
仍超              → S4 剩余版本池化（未合入步骤整体回退；M4-1 expose 去留随用户裁决）+ 立项会重报日历
```

## 风险登记表（PRD §8 转化，PM 视角）

| 风险 | 触发信号 | 缓解动作 | 负责角色 |
|---|---|---|---|
| S1 LLM 输出守恒与解析鲁棒性（高） | coverage 对账失败批占比、非 json_mode 解析用例失败 | 反向校验失败批不落盘；4 层解析专项 mock；重试/串行降级复用纠错骨架 | 执行者 |
| S2 pending 互清作用域化回归（高） | 主轨两次 store 计数断言失败 / 双轨互扰用例失败 | track 作用域 + 存量兼容规则；用例序列化编排；既有断言零改动全绿门禁 | 执行者 |
| S4 触碰 subtitle_trim（三版本 untouched，中） | golden 对拍不一致（无 keep 工程输出漂移） | golden 基线先行（P3-1 硬前置）；invalidated_count；R4.4 首砍项；diff 审查重点项 | 执行者 / 架构师（审查） |
| S1 token 成本与耗时（中） | 千段耗时 > 3 分钟 / token 超预估 | 入口预估批数提示；复用 `llm:token_usage`；TaskManager 全程可取消 | PM / 用户 |
| S1 批量写原子性（中） | revision 增量 > 1 / undo 回退不完整 | 单 patch 落盘用例（千段参数化）；start 前前端快照 | 执行者 |
| S1 翻译期间主轨编辑致 id 配对落空（中） | uncovered_ids 非空频率上升 | 完成时按 id 对账 + 面板明示清单，不静默 | 执行者 |
| S1 级联删除用户误解（中） | 用户反馈译文段消失 | 建轨完成 toast 附注 + README 说明（P4-3） | PM |
| S2 accept patch 化触及主轨契约（低，已核证） | `test_subtitle_correction_review.py:157` 断言失败 | 超集方案：保留 `segment_id` 键新增 `patch` 键 | 执行者 |
| S4 手势冲突（toggle × 建段 × Ctrl/Shift，中） | 手势矩阵逐格用例失败 / Ctrl-create 回归 | 默认 OFF；Ctrl/Shift 优先级高于范围模式；矩阵逐格 vitest | 执行者 |
| 红线重启失序（diff 审查制依赖纪律，中） | 门禁脚本禁改面命中 / 白名单外 diff / 断言检查非零 | 登记表逐 phase 追加 + 门禁脚本每 phase 复跑 + P4 终检逐条核对 | 架构师 / 执行者 |
| 多行时间线视觉回归债（3.0.3 顺延，中） | P4 冒烟第 7 项异常 | 并入 P4 清单与 S4 新分组合并补验 | PM / 用户 |
| 返工风险（行号漂移 / SPEC-PLAN 冲突，中） | 实施中 file:line 与代码不符或两文档冲突 | 符号名检索兜底（SPEC 头注）；冲突以 SPEC 为准，当场回写 PLAN + record 登记 | 执行者 / 架构师 |
| 天数超限（中） | 里程碑锚点滑动 | 缓冲阀顺序 R2.5 → R4.4 keep → S4 剩余版本池化（超期决策树） | PM（提请用户裁决） |
| LLM provider 兼容性真机风险（中） | beta.1 真机非 OpenAI/DeepSeek（Qwen/GLM/Ollama）翻译失败或格式漂移 | 4 层解析 mock 专项；beta.1 冒烟覆盖至少一家非 json_mode provider；失败批零落盘不污染工程 | 用户（真机）/ 执行者 |

## 规模对照

- 后端净新增 ~600-850 行（8 个白名单文件 + ≥46 用例）、前端 ~800-1100 行（+ ≥23 用例，含三处新建测试宿主）——约为 3.0.3 两倍量级（PRD §7）
- 高风险两项的缓解落点：S2 作用域化 → P2-3 兼容规则 + 序列化用例；S4 keep → P3-1 golden 先行 + P3-9 首砍标注

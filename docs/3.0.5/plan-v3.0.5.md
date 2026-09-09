# Milo-Cut v3.0.5 实施计划（PLAN）

> **版本**: 3.0.5（定稿——PRD 修订-1 终态 / SPEC R2b 定稿 + R4 修订终态；R5 轮 PM 已按附录 B B-1~B-11 完成回写）
> **基准**: tag `v3.0.4`（3.0.x 首次回并主干后的当前发布态，HEAD `b21c451`；行号引用以 SPEC M0 为准，漂移以符号名检索兜底）；**门禁 diff 基准恒为 `v3.0.4`**（不受文档入库与 tag `v3.0.5-base` 影响）
> **分支**: `dev-3.0.5` 自 tag `v3.0.4` 拉出，开工即打 tag `v3.0.5-base`（**打在拉出点 = `v3.0.4` 所指 commit**，先于文档入库——纯代码回滚锚点）；每步短分支 `dev-3.0.5-<step>` 合入即删
> **依据链**: [PRD-v3.0.5](./PRD-v3.0.5.md)（修订-1：R5.0-R5.16 / §6 裁决与 trim 矩阵 / §7 交付计划与人日终值）· [spec-v3.0.5](./spec-v3.0.5.md)（实施终态：M0 契约 / M5.0-M5.8 / M9 / M-gate；与 PRD 冲突处以 SPEC 为准）· [review-log-v3.0.5](./review-log-v3.0.5.md)（R2-R5 评审链；R5「留给 R6 排期输入」为本文排期直接依据）· [研究报告-v3.0.5](./研究报告-v3.0.5.md)（§8.4 真机项）· [record-3.0.4](../3.0.4/record-3.0.4.md)（§1 分步 record 命名与索引先例 / §2 node 回落先例）
> **计划文档**: `docs/3.0.5/plan-v3.0.5.md`（每完成一步勾销并回填实际结果）
> **规模口径（终值，PRD §7 = SPEC 头部注记）**: 13.5-17.5 人日（P0 0.5 / P1 6-8.5 / P2 2-2.5 / P3 1-1.5 / P4 3.5-5 / P5 1-1.5，两端不同时取上界）；日历 **11-15 天**——**并行假设（顺带批与 P1-P3 并行开发）是承诺口径的一部分**；单人串行备份口径 15-19 天；并行假设唯一显式例外 = SPEC M0-4 序 8（见 §0.3 与 P4-3 前置）
> **红线**: 「只增不改」延续（PRD §1）：`core/models.py` 零改动 / 事件零新增预期 / 断言反转白名单（后端 2 行 + 前端 2 例 + 追认制 1 行）/ 主轨零回退 + golden 锁 / 门禁 = 白名单 + diff 审查制（后端六文件 + 受控改点 (a)-(f)）

---

## 0. 全局约定（适用每一步）

### 0.1 验收基线（每步合入前必须全绿）

命令与期望输出**原样取自 SPEC M-gate 门禁命令块**（唯一真源，本文不改写；发现冲突以 SPEC 为准并当场修本文件）：

```bash
# 后端门禁
uv run pytest                                   # ≥833 + 新增全绿（当期期望总数见下表）
uv run ruff check .                             # 0
# 红线 R0-1：后端 diff 白名单（输出文件集 ⊆ M0-1 六文件表，逐 hunk 对照登记表）
git diff v3.0.4 --name-only -- core/ main.py
# 禁改面必须为空输出：
git diff v3.0.4 --stat -- core/models.py core/events.py core/task_manager.py \
  core/export_service.py pywebvue/ dev.py build.py
# 红线 R0-3：后端断言删改仅限 M0-3 白名单行（命中行全部落在 :217/:614 登记内即核对通过，白名单外命中即 fail）
git diff v3.0.4 -- tests/ | grep -E '^-[[:space:]]*(assert |self\.assert)'
# 前端门禁
cd frontend && bun run test && bun run build && bun run lint   # ≥840+新增全绿 / build 通过 / 0/0
# 前端断言白名单外零删改（命中行必须全部落在 M0-3 前端两例 3 行登记内）
git diff v3.0.4 -- frontend/src | grep -E '^-[[:space:]]*expect\('
# events 双侧（预期零 diff；实施期确需新事件须同一改动双侧登记并回写 PRD §1.2）
git diff v3.0.4 --stat -- core/events.py frontend/src/utils/events.ts
```

**node 回落条款（record-3.0.4 §2 先例内置）**：`bun run` 不可用时前端门禁以 node 直跑等价命令回落——`./node_modules/.bin/vitest run`、`./node_modules/.bin/vue-tsc --noEmit` + `./node_modules/.bin/vite build`、`./node_modules/.bin/eslint .`（package.json scripts 原样拆解，语义逐条一致）；回落执行在当步 record 登记，不得因环境问题阻塞合入。

**门禁期望总数登记**（下限承诺 = PRD §7.4 终值后端 ≥30 / 前端 ≥24，对齐 SPEC M-gate 逐主项额度；基线 = SPEC 头部实跑声明，P0 首跑复核一次；D4 四项测试不占额度、增量如实登记）：

| 合入节点 | pytest（passed） | vitest（collected / passed） | 新增依据（M-gate 逐主项额度） |
|---|---|---|---|
| P0 基线 | 833 | 840 / 839（唯一失败 = `useRowLayout.perf.test.ts` 挂载墙钟环境例，豁免口径确认） | 干净起点首跑复核登记 |
| P1 末 beta.1 | ≥853 | ≥851 / ≥850 | 后端 +≥20（R5.1 ≥4 / R5.2 ≥4 / R5.3 ≥10 / R5.8 ≥2）；前端 +≥11（R5.0 ≥3 / R5.1 ≥3 / R5.3 ≥4 / R5.13 1） |
| P2 末 beta.2 | ≥859 | ≥854 / ≥853 | 后端 +≥6（R5.4）；前端 +≥3（R5.4） |
| P3 末（无独立 tag） | ≥863 | = beta.2 | 后端 +≥4（R5.5） |
| P4 末 beta.3 | ≥863（D4 增量另计） | ≥864 / ≥863 | 前端 +≥10（R5.6 ≥3 / R5.7 ≥4 / R5.10+R5.11 合并 ≥2 / R5.15 1）；R5.16 根修完成则 perf 转绿、passed = collected 且豁免退役 |
| P5 终检 | = beta.3 | = beta.3 | 全量复跑 + 登记表与反转清单逐条核对 |

### 0.2 提交与记录

- 一步一短分支一合入（`dev-3.0.5-<step>`，合入即删）；两段式提交（`type(module): 摘要` + `-` 列表，不带版本号）
- 每步完成即勾销本文件 + 写 `docs/3.0.5/record-3.0.5-<step>.md`（改动文件清单、验证命令与实际输出、未验证边界；命名照 record-3.0.4 §1 先例）；总记录 `record-3.0.5.md` 于 P0 建骨架（含 §1 分步索引表）
- **后端改动登记表**：按 SPEC 附录 A 模板（phase / 文件 / hunk 摘要 / R 编号 / 红线类别——六类枚举：只增 / 受控改点 (a)-(f) / 登记改点），每步 record 追加、总表逐 phase 汇总，P5 终检逐条核对；前端文件同样登记；无 R 编号对应的 diff 要么补登记要么回退
- **断言反转白名单登记（SPEC M0-3 终态）**：后端 2 行 = `tests/test_llm_translation.py:217`（随 R5.2 文案改写，P1-3）+ `:614`（随 R5.1 取消返回附 data 反转，P1-2）；前端 2 例共 3 行 = `AIAssistantPanel.test.ts:301`（随 R5.13，P1-6）+ `SegmentBlocksLayer.test.ts:364、:366`（随 R5.10，P4-2）；追认制 1 行 = `findOverlays` 选择器改 `[data-test="range-overlay"]`（非 expect 行，P4-2）。预登记 5 例中四姊妹例（:192/:226/:256/:518）已撤销零改动（★B-3）。各条随对应 phase 在 record 反转清单登记条目、意图与理由；ledger 记 failed 批的断言全保留；白名单外命中即红线违规，记阻塞不放宽
- 验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注「可并行」的步骤）
- 文档类提交（P0-1 入库、各步 record 与本文件勾销）走 `docs(...)` 两段式提交，直接落 `dev-3.0.5`；代码步骤一律走短分支

### 0.3 批次顺序强制（SPEC M0-4 全 8 条落点；PM 排期裁决冲突处以 SPEC 为准）

```text
P0: 分支 / tag / 基线首跑 / 门禁脚本
P1: R5.0（序 1 首项）→ R5.1 → R5.2 → R5.3（序 4 同族一次改透；序 7 合流先行）→ R5.8（序 2）→ R5.13 → beta.1
P2: R5.4（序 3 同 commit 族，拆后端/前端两步、门禁独立可回滚）→ beta.2
P3: R5.5（序 5 独立成相；可与 P1/P2 并行开发，合入按 P1 → P3 序；无独立 tag）
P4: golden 锁先行确认（序 6）→ R5.6 → R5.7+R5.9+R5.10+R5.14（PRD 约束③ 同 commit 族）
    → R5.11+R5.15+R5.16（序 8 前置）→ R5.12+D4 → beta.3
P5: 门禁终检 → 文档回写 → 真机全量回归 → RC → 正式
```

| SPEC M0-4 序 | 内容（摘要） | PLAN 落点 |
|---|---|---|
| 序 1 | R5.0 全版首个合入项 | **P1-1 = 全版首个代码合入步**；其后各 phase 门禁基线才含 duplicate 态防护；R5.0 不触 llm/correction 族 |
| 序 2 | S5×S1 主从：R5.8 后于 R5.3（同函数族 (d)/(f) 同段相邻，禁止跨 phase 交错） | P1-4 → P1-5 同 phase 依序，P1-5 开工前置 = P1-4 已合入 |
| 序 3 | S2×D7c 同一 commit 族（聚合返回形状就是作用域改形的消费面） | P2-1 内聚：三态形参与聚合 patch 不拆分交付；前端消费（P2-2）凭 data 纯增 patch 键超集兼容可后置一步 |
| 序 4 | R5.1×R5.2×R5.3 同族 hunk P1 内一次改透 | P1-2 → P1-3 → P1-4 连续步；:614 / :217 反转随对应步登记 |
| 序 5 | R5.5 独立成相 P3，可并行开发、合入按 P1 → P3 序 | P3-1；(a) :1116-1187 与 (d)/(f) 无重叠；R5.1×R5.5 主从 = 取消判据措辞复用 M5.1「事件优先」口径 |
| 序 6 | golden 锁先行（任何 SegmentBlocksLayer / keep 相关改动前） | P4-1 首项 checkbox + P4-2 动手前复跑确认，输出贴当步 record |
| 序 7 | completion payload 缺口合流 hunk 先行或同 commit 于消费端 | P1-4 内部序（硬约束）：先落 main.py :1317-1331 区 + :1340，再落 AIAssistantPanel / WorkspacePage watcher；R5.11 reset 延后（P4-3）消费同一 lastTranslationCompletion 结构（P1-4 已定形） |
| 序 8 | R5.11 开发基线须含 M5.4 | P4-3 前置（硬约束）= P2 已合入；**P4∥P1-P3 并行假设的唯一显式收窄点** |

**PM 排期裁决（本文件新增，冲突处以 SPEC 为准）**：① R5.13 归 P1 末独立步（纯前端，随 beta.1 一并验证翻译入口估算）；② P4 覆层/文案族（R5.6③ 覆层 hunk + R5.7④ + R5.9 + R5.10 + R5.14）按 PRD §7 顺序约束③与 M5.6 裁决 3 收口为 P4-2 一个 commit 族，R5.6 先行步只落不触该 hunk 的三面；③ R5.12（llm_prompts 1 行受控增行）零前端牵连，与 D4 测试轮同批置 P4-4。

### R 编号归属总表（R5.0-R5.16 全覆盖自查，供 R7 终检）

| R 编号 | 步骤 | R 编号 | 步骤 |
|---|---|---|---|
| R5.0 | P1-1 | R5.7 | P4-2 |
| R5.1 | P1-2 | R5.8 | P1-5 |
| R5.2 | P1-3 | R5.9 | P4-2 |
| R5.3 | P1-4 | R5.10 | P4-2 |
| R5.4 | P2-1 + P2-2 | R5.11 | P4-3 |
| R5.5 | P3-1 | R5.12 | P4-4 |
| R5.6 | P4-1 | R5.13 | P1-6 |
| （D4 测试轮） | P4-4 | R5.14 / R5.15 / R5.16 | P4-2 / P4-3 / P4-3 |

### 0.4 立项会裁决登记（2026-09，留痕——后续任何范围/日程裁决同格式追加于此与 record-3.0.5.md）

| # | 议题 | 裁决 | 留痕要求 |
|---|---|---|---|
| 1 | F1 数据安全缺陷处置（Q1） | **裁决①：并入 3.0.5 首项（R5.0），v3.0.4 不出补丁** | R5.0 = 全版首个代码合入步（序 1）；触发场景（重复框选/双击/时间码重复提交）正是幂等设计服务对象 |
| 2 | 六主项全量（T-5.1 / T-5.2 / T-5.3 / S3 / S4 / S5） | **裁决②：全量入版** | 让位仅可按超期决策树：首让 R5.8 整体回池（触发 A）；部分让 = R5.7 lane 半 / R5.11 时间码半 / R5.14（触发 B）；R5.0-R5.6 为不可让面 |
| 3 | S6 手动范围自由备注 | **裁决③：3.1.x schema 首发不入版**（detail JSON 过渡案亦不做） | 降级诉求（hover 创建时间）随 PRD §10.2 登记版本池 |
| 4 | 日历 11-15 天（人日 13.5-17.5 不折减） | **同意** | **并行假设（顺带批与 P1-P3 并行开发）为承诺口径的一部分**；单人串行备份 15-19 天；序 8 例外显式登记（§0.3） |
| 5 | 超期决策树授权（首让 R5.8） | **同意（触发须留痕）** | 每次触发按四要素留痕：日期 / 触发信号（偏差与观测点）/ 裁决内容与影响面（R 编号级）/ 回写文档处（PLAN 步骤注记 + record-3.0.5.md 对应 phase + PRD §10.1 回池 + SPEC 对应 M 条目「已砍（日期）」），四者齐备方可执行 |
| 6 | 里程碑绝对日期 | **不强制** | 维持相对日程 D+n，绝对日期**触发式回填**（3.0.4 修订-2 ④ 先例延续），不作为门禁项 |

---

## Phase 0: 开工准备（0.5 天）

### P0-1 分支、tag 与基线快照（含文档入库）

- [x] ★ 立项会确认（2026-09 已裁决，登记于 §0.4）：三裁决①②③ + 日历 11-15 天（并行假设承诺口径）+ 超期决策树授权（首让 R5.8，四要素留痕）+ 里程碑不强制绝对日期
- [ ] 从 tag `v3.0.4` 拉出 `dev-3.0.5`；打 tag `v3.0.5-base`（打在拉出点，先于文档入库；门禁 diff 基准恒为 `v3.0.4` 不受影响）
- [ ] 文档入库：`docs/3.0.5/`（研究报告 / 用户反馈 A·B / PRD / SPEC / review-log / PLAN——PRD/SPEC 已于 R5 轮定稿，本步仅入库）以 `docs(3.0.5): ...` 两段式提交
- [ ] 建 `record-3.0.5.md` 总记录骨架：§0 交付概览 / §1 分步索引表（步 / record 文件 / 状态 / 合入 commit）/ §2 门禁基线 / §3 后端改动登记表总表（SPEC 附录 A 模板，P0 行 = 零改动基线）
- [ ] 门禁基线首跑登记并复核：pytest 833 全绿 / vitest 840 collected·839 passed（唯一失败 = useRowLayout.perf 环境例，**豁免口径确认**；SPEC 头部声明值，passed 数本轮首跑复核一次）/ build / lint / ruff 全绿；红线命令零改动点期望 = 白名单零命中、禁改面空输出、断言删改零

**验收方式**: `git tag` 存在 `v3.0.5-base`；`git status --short docs/3.0.5/` 干净。
**验收标准**: 零改动干净起点门禁全绿；实际值与 SPEC 声明（833 / 840·839）一致，偏差则先回写 SPEC 头部与本文 §0.1 表再开工。
**record**: `record-3.0.5-P0-1.md`

### P0-2 门禁脚本沿用与基线 tag 更新（处置裁决：复制改基线，非重写）

- [ ] `scripts/gates-v3.0.4.sh` 复制为 `scripts/gates-v3.0.5.sh`，沿用三段结构（后端门禁 / 前端门禁 / 红线检查）；新增文件不在 `core/ main.py` diff 审查范围，commit 用 `chore(gates): ...`
- [ ] 全部 diff 基线 `v3.0.3` → `v3.0.4`；红线段按 3.0.5 SPEC M-gate 更新：R0-3 后端断言检查由「期望零」改「命中行落 M0-3 白名单（:217/:614）即核对通过」；前端 expect 检查同口径（白名单 3 行）；events 双侧期望零 diff；禁改面清单对齐 M0-1 禁改面全列
- [ ] node 回落内置（bun 可用时优先 `bun run`；回落分支照 record-3.0.4 §2 措辞）
- [ ] dry-run：基线工作区三段汇总 exit 0（红线段空/零）；固化执行约定 = 每 phase 合入前执行一次、stdout 贴当步 record、shell 受限回落手动命令块 + record 登记；SPEC 与脚本冲突以 SPEC 为准当场修脚本；旧脚本 `gates-v3.0.4.sh` 退役不删（历史 record 引用保留）

**裁决理由**: 3.0.4 红线命令已脚本化且经执行验证，3.0.5 差异仅为基线 tag 与断言白名单核对方；复制改基线回归风险最低，重写引入与已验证脚本的结构漂移。
**验收方式**: 脚本在基线工作区跑通、三段汇总 exit 0。
**record**: `record-3.0.5-P0-2.md`

---

## Phase 1: 首项 F1 + T-5.1 三件套 + S5（6-8.5 人日，M5.0-M5.3 + M5.8）→ `v3.0.5-beta.1`

### P1-1 R5.0 duplicate 幂等返回防呆（前端；SPEC M5.0；**全版首个代码合入步——序 1**）

- [x] **序 1 顺序强制**：本步先于一切 llm/correction 族改动合入；本步 diff 不触 llm/correction 族，与 P1 其余项零冲突（后端零改动）
- [x] `WorkspacePage.vue` handleRangeDecision（:990-999）三分支化（受控改点 (c)）：duplicate → 不 emit project-updated + `popSnapshot()` + info 轻提示「该范围已存在，已复用原条目」自动消退；成功 → :994-995 现状形态逐字节不变；失败 → toast + `popSnapshot()`（消除 F-B-10 undo 空步）
- [x] `useUndoRedo.ts` 纯新增 `popSnapshot()`（不触碰 redoStack；docstring 写明「本次 push 后、响应返回前的同步窗口」不变量，SG-6 / M5.0 裁决 2）；后端不补 revision（N3：防带 revision 非 patch 对象误入 isProjectPatch 通道）
- [x] 用例 ≥3：duplicate 态第三例（宿主 `WorkspacePage.rangeDecision.test.ts`，既有 2 例 :271/:321 零改动全绿）+ duplicate/失败路径 undo 栈长度恢复

**实际结果（2026-09，record-3.0.5-P1-1.md）**：+6 例（宿主 3 = duplicate 第三例 + 回滚 ×2；useUndoRedo.test.ts 单元 3 = 末条弹出/空栈 null/SG-6 redoStack 不变量直证）；全套门禁 exit 0（pytest 833 / vitest 846·845 唯一失败 = perf 环境例 / build / lint 0/0 / 红线 R0-1~R0-5 零命中，后端 diff 为空实证）；`94c4c91` → merge `ba5a78c`，短分支已删。

**验收方式**: M-gate 前端 R5.0 ≥3；全套门禁全绿（红线自此步起按白名单口径核对）。
**验收标准**: duplicate 返回不进 project-updated（内存态不变）、undo 栈零新增；`core/` 与 `main.py` diff 为空。
**record**: `record-3.0.5-P1-1.md`

### P1-2 R5.1 翻译失败/取消成本可见（core/llm_service.py + main.py + 前端三处；SPEC M5.1；序 4 起步）

- [x] 管线三处取消返回附 data：:1871 / :1903 / :1939（E-1 三处全覆盖；键级只增、`error` 串不变——test_translation_smoke_fix.py:169 既有断言零改动）
- [x] handler 失败/取消分支（受控改点 (e)，main.py:1266-1269）：取消判据 = `cancel_event.is_set()` 事件优先、字符串仅兜底（MF-2/焦点 5，与 task_manager :299-301 双通道同构）；取消路径 emit `llm:token_usage`（payload 增 `status: "cancelled"` 纯增键）且**不再** emit `llm:analysis_failed`，仍 raise（保 task_manager 判别）
- [x] 失败路径：handler 从 result.data 提取 ledger/token_usage（:1978-1982 数据源已在）→ 先 emit `llm:token_usage`（`status: "failed"` + failed_batches）再报错
- [x] 前端三处：WorkspacePage :604-616 补 `llm_translation` 中性提示「翻译已取消，已消耗约 X tokens」；useLlmTasks :245-248 补 errorMsg 清空（**task_type 判据限定 llm_translation**，SG2-2；其余类型残留登记 record §8 不修）；:256-264 增 progressMessage + AIAssistantPanel「(serial)」子串映射「限流中，已切串行，剩余批次处理中」（零后端改动）
- [x] 用例：后端 ≥4（取消/失败上报 + status 键 + 事件判据）；前端 ≥3（中性态 / errorMsg 清理 / serial 消费）；**断言反转登记：test_llm_translation.py:614 反转随本步落 record 反转清单**（:608/:612 保留）

**实际结果（2026-09，record-3.0.5-P1-2.md）**：后端 +5（预置取消/串行取消附 data + handler 取消上报/失败上报顺序/事件优先判据）、前端 +7（progressMessage 存取/errorMsg 三态/串行提示渲染两例/取消中性 toast 两例）；:614 反转按 M0-3 落 record-3.0.5-P1-2.md §2 反转清单（含 docstring 同步改写与「无合并输出」不变量延续）；全套门禁 exit 0（pytest 838 / vitest 853·852 唯一失败 = perf 环境例 / 红线白名单外零命中，后端 diff = llm_service+main.py 恰两白名单文件）；`4ea180e` → merge `b5694ef`，短分支已删。

**验收方式**: M-gate 后端 R5.1 ≥4 + 前端 ≥3；门禁全绿。
**验收标准**: 取消/失败均 token 上报且「已消耗 X tokens、失败批 [n]/N」可见；无英文 "Cancelled" 红框、errorMsg 不残留；成功路径消费链零改动。
**record**: `record-3.0.5-P1-2.md`

### P1-3 R5.2 行级解析兜底 translated_text + 失败中文出路指引（core/llm_service.py；SPEC M5.2）

- [x] 第 4 层解析追加第三正则 translated_text 模式（:612-634 之后、Layer 5 sanitize :636 之前，只增；relevance/action 路径零回归；逐行条目归一 `{segment_id, translated_text}`，命中即同款早退）
- [x] 救回批不绕校验：照走 coverage 反向校验（:1814 调用点），漏译/未知 id 照旧进 ledger 不静默；解析层共享函数对纠错形态输入（无该字段）走既有路径零副作用
- [x] 全批失败中文拒绝文案（:1973-1977 区，**含「补译」二字**——:217 改写锚定关键词；部分成功通知不走 error 通道、改 payload 驱动随 P1-4 合流，M5.2 裁决 3 文案落点分裂）
- [x] 用例 ≥4：逐行模式 mock 守恒 / 不可救回中文指引 + data 带 ledger·token_usage（与 R5.1 闭环）/ relevance·action 既有例（test_llm_phase4b.py:68-130 区）零改动 / 解析直测纠错形态输入
- [x] **断言反转登记：test_llm_translation.py:217 改写随本步落 record 反转清单**（四姊妹例 :192/:226/:256/:518 零改动，★B-3 撤销）

**实际结果（2026-09，record-3.0.5-P1-3.md）**：后端 +4（近 JSON 行救回守恒 / 不可救回中文指引+data 闭环 / 解析直测含转义引号契约 / 纠错形态零副作用直证），前端零改动（vitest 持平 853·852）；:217 改写按 M0-3 落 record-3.0.5-P1-3.md §3 反转清单（关键词 = 「补译」）；文案 = 「翻译失败：N/M 批处理失败（批 [ids]），本次未写入任何译文；可直接重试补译；反复失败建议更换模型或检查网络」；全套门禁 exit 0（pytest 840）；`3df0f4f` → merge `3b037ca`，短分支已删。

**验收方式**: M-gate 后端 R5.2 ≥4；门禁全绿。
**验收标准**: 非 json_mode 逐行近 JSON 可救回且全量守恒；红框无英文技术体；既有解析层断言零改动。
**record**: `record-3.0.5-P1-3.md`

### P1-4 R5.3 翻译增量补译 + uncovered 对账可读化（本模块最高风险；SPEC M5.3；**序 7 落点**）

- [x] **序 7 内部序（硬约束）**：先落（或同 commit 落）main.py completion payload 缺口合流 hunk——:1317-1331 区 `uncovered_ids` 改「写侧对账 ∪ ledger.uncovered_segment_ids」去重并集 + 返回 dict :1340 同口径（MF2-2 登记改点）——后落消费端改造（AIAssistantPanel :455-467 / WorkspacePage watcher :1069-1087），防中间态假绿
- [x] 管线失败语义改判（受控改点 (d)，:1957-1982 两分支）：部分成功 = 失败批 id 并入 ledger.uncovered_segment_ids + 已完成批正常建轨；**全批失败仍拒零写入**（中文文案与 P1-3 同源）；无失败路径逐字节等价（断言全键）
- [x] start_translation 补译自动路由（受控改点 (e)，main.py:2996-3006）：缺口集 = 主轨段（排除 confirmed-deleted）− 目标轨 bindings 差集、运行时推导不持久化；非空转补译（payload 纯增 `resumable_track_id`/`gap_segment_ids` 两键）；为空维持拒绝原文案
- [x] `core/project_service.py` 仅新增 `merge_translation_track`（:716 后插入，单一 hunk 零删改；SG2-3 自含实现**不抽**共享 helper；入口双保险再查 + 撞号显式失败 + 单 `_success_patch(tracks, bindings)` revision+1，meta 携带 merged_count；禁止逐段 patch）
- [x] 前端：pendingResumable 标记 + completion.track_id 比对命中才 toast「本次补译 N 段」+ task:failed/cancelled 显式清（SG2-1 双保险）；对账清单逐条「mm:ss + 文本前 20 字」、点击定位主轨段、尾部一键「补译这些段」（走同一路由）
- [x] 用例 ≥10：1/N 降级落盘 + SG-1 守恒不变量 + MF2-2 合流断言 + 全批拒 + 等价断言 + 缺口推导 mock + merge 单 patch（revision+1 双层）+ 写侧双保险两拒例 + 对账数据结构 + 补译走 merge 非 create

**实际结果（2026-09，record-3.0.5-P1-4.md）**：序 7 以「同 commit」兑现（`a6ec740` 单提交含合流 hunk 与全部消费端）；后端 +11（含 SG-1 双向守恒、MF2-2 写侧空并集、merge 单 patch/四拒例/对账结构、缺口推导恰为差集、merge 非 create spy）+ 前端 +5；project_service 零删行实测；**追认反转 4 处**登记 record §3（429 多批例 success 翻转 / expose 完整轨夹具（拒绝断言零改动）/ 面板裸 join 断言随裁决 8 改逐 id / useLlmTasks 两处 toEqual 纯增 written_count 键——expect 行零删）；全套门禁 exit 0（pytest 851 / vitest 858·857 / 红线全 PASS）。

**验收方式**: M-gate 后端 R5.3 ≥10 + 前端 ≥4；门禁全绿。
**验收标准**: 1/34 场景 33 批落盘且缺口可读可定位可一键补译（notice 必触发）；合并 undo 一次回退；同语言完整轨重译仍拒；project_service diff = 单一方法纯新增。
**record**: `record-3.0.5-P1-4.md`

### P1-5 R5.8 质量模式开关（core/config.py + core/llm_service.py；SPEC M5.8；**序 2 落点**）

- [x] **序 2 顺序强制**：P1-4（R5.3）合入后方可开工——同 `analyze_subtitle_translation` 函数族，(d) :1957-1982 与 (f) :1774-1790 同段相邻，乱序必冲突；P1 内一次改透禁止跨 phase 交错
- [x] config DEFAULTS 追加 `"llm_translation_quality_mode": False` 1 行（:82 后；白名单内只增；开关为全局设置，handler 零改动不增形参）
- [x] 管线增读第 5 键 + 串行分支一行裁决（quality_mode → concurrency 有效值 1，:1743 后）；取消约 1s 不受影响（wait(1.0) :1865-1868 与串行循环 cancel 检查 :1938 在位）
- [x] 受控改点 (f)：质量模式分支预构建跳过 prompt 组装（仅保留 target_windows/id_map 结构）、串行派发循环内逐批构建 + 上一批定稿译文经 `_build_structured_user_message` 增 `finalized_translations` 受控转发增行（:518-563）；**默认关路径预构建原样保留**（逐字节等价判据面）；补译组合（Q7）= 补译批同受开关约束，「上一批」= 本轮补译序列内上一批
- [x] 用例：关闭路径 payload 逐键等价 / 批 2 prompt 含批 1 定稿译文 / 批 1 无该键（窗口边界）/ 串行 × 取消 1s（复用栅栏法）/ quality_mode × 429 组合无双重 shutdown（SG2-7）

**实际结果（2026-09，record-3.0.5-P1-5.md）**：后端 +4（B1 关闭路径键集逐键等价 / B2 滑窗批 2 携批 1 定稿 + 批 1 边界无键 + concurrency 强制 1 / B3 串行取消 1s 栅栏 / B4 quality×429 降级无双重 shutdown）；实现补强两处登记 record §5——future 反查表改逐 submit 注册（归纳消除即时 mock 下的注册竞态）、窗口数据源取 prev future result（工作者序列保证）而非主线程消费态；零反转；门禁 exit 0（pytest 855 / vitest 持平 858·857 / config diff 恰 1 键行）；`241ebb9` → merge `7f4b7ac`，短分支已删。

**验收方式**: M-gate 后端 R5.8 ≥2；门禁全绿。
**验收标准**: 开关关闭与 v3.0.4 并发行为逐字节等价（既有断言零改动）；config diff = 1 行；(f) hunk 在登记表与 (d) 分行登记。
**record**: `record-3.0.5-P1-5.md`

### P1-6 R5.13 token 量级预估（前端；SPEC M9）+ beta.1 节点

- [x] AIAssistantPanel 估算式改后端同式字符累计切批近似（llm_service.py:1753-1769 target_windows 口径前端同式模拟：批窗 30 + 字符预算 4000；token ≈ Σ批字符 × 0.75，标注「约」，SG-5 防系统性漂移）；随主轨段数动态刷新（:223-227 / :829-832 / :954）
- [x] 用例 1：估算显示（**断言反转登记：AIAssistantPanel.test.ts:301 改写随本步落 record 反转清单**）
- [x] ★ beta.1 节点：P1 末全套门禁（期望 ≥853 / ≥851·850）+ 打 tag `v3.0.5-beta.1` + record；★ 双平台真机冒烟按「真机冒烟清单」beta.1 轮（可后置执行，先例照 3.0.4 冒烟后置裁决；异常走 smoke-fix：合入分支、tag 不动）

**实际结果（2026-09，record-3.0.5-P1-6.md）**：:301 改写（「约 42 批 · 约 0.8 万 token」整串）+ 新增预算切批例（60 段 × 200 字 → 3 批，朴素 ceil 被证伪）；beta.1 期望达标（pytest **855** ≥853 / vitest **859·858** ≥851·850，P1 累计后端 +22 前端 +19）；tag `v3.0.5-beta.1` 落于 `34fba34`；beta.1 真机冒烟后置（四项清单登记 record §5）；`7b2323c` → merge `34fba34`，短分支已删。**P1 全六步收口（R5.0/R5.1/R5.2/R5.3/R5.8/R5.13）。**

**验收方式**: M-gate 前端 R5.13 1 例；beta.1 期望总数达标。
**验收标准**: 显示「约 N 批 · 约 X 万 token」且量级合理；失败启动不写回语言记忆（既有行为保持）。
**record**: `record-3.0.5-P1-6.md`

---

## Phase 2: T-5.2 批量审阅收口（2-2.5 人日，M5.4）→ `v3.0.5-beta.2`

### P2-1 R5.4 后端：三态作用域 + 聚合 patch（core/correction_service.py + main.py；SPEC M5.4；**序 3 落点**）

- [x] **序 3 同 commit 族（硬约束）**：三态作用域形参与聚合 patch 不拆分交付——聚合返回形状就是作用域改形的消费面，拆开必产生中间破形；D7 第三项不是独立交付物
- [x] `accept_high_confidence_corrections` / `clear_subtitle_corrections`（受控改点 (b)，:446-502 / :504-532）：形参 `track_id: str | None = None` 三态——None = 既有 timeline 级逐字节等价、`""` = 主轨作用域、非空 = 副轨作用域（★B-1）
- [x] 逐条应用核心抽内部无 patch 方法 `_apply_one(result_id) -> (bool, set[Layer])`（复用 :269-301 钉扎/时间断言/置信度），批量循环消化脏层并集后一次 `_success_patch(segments=?/tracks=?/analysis=?)`，revision 恰 +1；返回 data = 旧键保留 + **纯增 `patch` 键**（MF-3 超集兼容）；clear 返回 `{cleared_count, patch(analysis)}` 同口径；逐条 accept/reject 返回零改动
- [x] main.py 两 expose 透传 `track_id`（:2755-2768 / :2771-2778，**登记改点**）
- [x] 用例 ≥6：主轨视图不动副轨待审集（三态 `""` 回归锁）/ 副轨不动主轨 /「全部」= None 兼容（既有断言零改动即证）/ 聚合单 patch revision+1 且含 patch 键 / 逐条路径返回形状零改动 / undo 三层并集例（后端半边）

**实际结果（2026-09，record-3.0.5-P2-1.md）**：后端 +7（B1/B2 三态互扰 / B3 三层并集聚合单 patch revision+1 / B4 零命中旧形 / B5-B7 clear 三态与超集）+ spy 例按 M5.4 裁决 2 重写（**追认反转 1 行**：逐条 patch 契约被 SPEC 废除，门禁 R0-3 排除面按「SPEC 为准当场修脚本」扩 test_correction_accept_patch.py 并在脚本内注明——**R0-3 排除面首次扩充，P5-1 终检核对项**）；None 兼容与逐条形状由既有 20+ 例零改动全绿证明；remaining/cleared 作用域计数与 clear 跨轴边界两处口径登记 record §5；全套门禁 exit 0（pytest 862 / 前端持平 859·858）；`bd19577` → merge `81feae8`，短分支已删。

**验收方式**: M-gate 后端 R5.4 ≥6；门禁全绿。
**验收标准**: 默认 None 路径逐字节等价；correction_service diff 落 (b) 区间、expose hunk 落登记改点并在附录 A 登记。
**record**: `record-3.0.5-P2-1.md`

### P2-2 R5.4 前端：批量 undo 三态层 + patch 消费驱动 + 确认文案（useWorkspaceActions.ts + WorkspacePage.vue）+ beta.2 节点

- [x] `correctionUndoLayers(entry, scopeTrackId)` 扩展第二形参（MF-1 三态：null = `["segments","tracks","analysis"]` 三层并集 / `""` = 主轨两层 / 非空 = 副轨两层）；handleAcceptHighConfidence 调用前按三态 pushSnapshot（现状无快照 :993-1003）
- [x] 消费链改造（D7c）：res.data.patch 存在 → 单次 applyProjectPatch 驱动刷新（diffCache 失效 :998 保留在前），**移除** switch_timeline 全量替换（:999-1000；无 patch 键回落旧行为防御）；handleClearCorrections 同构
- [x] 确认文案作用域化（SG-4）：确认框 N = 前端按 scope 过滤 pendingCorrections 计数、完成 toast N = 后端 accepted_count/cleared_count 如实展示（逐条静默跳过偏差由两处口径分工消化）；「全部」文案明示「含全部轨道 N 条」；window.confirm 沿用，不加弹窗组件
- [x] 用例 ≥3：确认文案三态 / 快照三态各一次回退（含三层并集例）/ patch 消费（无全量刷新）
- [x] ★ beta.2 节点：P2 末全套门禁（期望 ≥859 / ≥854·853）+ 打 tag `v3.0.5-beta.2` + record；★ 真机冒烟按 beta.2 轮清单（后置先例同前）

**实际结果（2026-09，record-3.0.5-P2-2.md）**：前端 +7（F1-F3 确认文案+快照三态含 null 三层并集直测 / F4-F5 patch 消费与回落 / F6 clear 作用域 / F7 空集 no-op）；clear 改 reload（作用域清除不吞他轨待审）；「全部」入口随 R5.11（机制全通，getReviewScope 覆盖注入已测）；零反转；beta.2 期望达标（pytest **862** ≥859 / vitest **866·865** ≥854·853）；tag `v3.0.5-beta.2` 落于 `77d2827`；冒烟后置（record §5）；`481780a` → merge `77d2827`，短分支已删。**P2 收官。**

**验收方式**: M-gate 前端 R5.4 ≥3；beta.2 期望总数达标。
**验收标准**: undo 一次整体回退（三态各验证）；确认文案含轨名/「全部」与条数。
**record**: `record-3.0.5-P2-2.md`

---

## Phase 3: T-5.3 纠错取消对齐（1-1.5 人日，M5.5；无独立 tag，随 P4 前合入）

### P3-1 R5.5 纠错取消轮询化（core/llm_service.py；SPEC M5.5；**序 5 独立成相**）

- [ ] **序 5**：独立成相，可与 P1/P2 并行开发，合入按 P1 → P3 序（(a) :1116-1187 与 (d)/(f) 区间无重叠）；**R5.1×R5.5 主从**：取消判据措辞复用 P1-2 确立的「事件优先 + 字符串兜底」，样板复刻翻译侧 smoke-fix-1c（:1848-1876 + finally :1930-1934）
- [ ] 外层循环轮询化（受控改点 (a)）：`with` 改 executor 变量 + try/finally 非阻塞 shutdown；as_completed 改 `wait(timeout=1.0, return_when=FIRST_COMPLETED)`；done 按 batch_idx 排序消化（ledger/progress 序稳定）；429 降级改「置标志 + 双层 break」；串行循环 :1171-1187 同改、逐批 cancel 检查保留（:1173）
- [ ] **MF2-1 记账判据冻结**：串行循环记账保持 :1182-1185 not-corrections 判据，**不复刻**翻译侧 :1947-1953 error 判据；该既有不对称登记 record §8 遗留，不顺手统一
- [ ] 用例 ≥4：取消 1s（栅栏法复刻 :139-172）/ 聚合等价（锁 corrections_by_index + total_usage + ledger 集合，不锁 list 顺序）/ 429×取消两交织（转串行后取消 pending 零执行；轮询内降级两循环退出无悬挂）/「串行 × parse 失败」锁面例（parse-None 批仍记 failed）

**验收方式**: M-gate 后端 R5.5 ≥4；门禁全绿（P3 末期望 pytest ≥863 / vitest 与 beta.2 持平）。
**验收标准**: 大批量纠错取消约 1s 返回；成功路径聚合等价；纠错既有断言零改动全绿。
**record**: `record-3.0.5-P3-1.md`

---

## Phase 4: S3 + S4 + 顺带批 + D4（3.5-5 人日，M5.6 / M5.7 / M9）→ `v3.0.5-beta.3`

> **序 6 golden 锁先行**：P4-1 与 P4-2 动手前各复跑一次 `SegmentBlocksLayer.test.ts:287-381` 三态 describe + keep golden 2 例，确认基线绿、输出贴当步 record。

### P4-1 R5.6 keep 可感知收口（SuggestionPanel · useEdit · ExportPage；SPEC M5.6）

- [ ] golden 锁先行确认（序 6）
- [ ] 确认文案直显：SuggestionPanel 确认按钮旁内联小字（:492-500 按钮容器内，DOM 变更不出容器；`:title` :496 保留渐进增强；确认 toast 差异化 keep/删除两文案）
- [ ] invalidated_count 透传：useEdit.ts :181-202 返回类型 / call 泛型 / 返回对象补键（后端 :2986 已上报、零改动）；重跑 toast「新增 N 条、按保留区间清除 M 条旧区间」（invalidated=0 只报新增）
- [ ] 导出确认页静态说明一句（ExportPage :415-416 计数行下）；红蓝并存覆层 hover 尾注与 title 语义化 hunk **随 P4-2 与 R5.9 同 commit 合入**（M5.6 裁决 3 合并施工，防同文件 hunk 撕裂——约束③）
- [ ] 用例 ≥3：直显不依赖 hover / toast 汇报 invalidated 与 new_edits / 导出页说明（覆层面断言随 P4-2 收口补齐）

**验收方式**: M-gate 前端 R5.6 ≥3；门禁全绿。
**验收标准**: 防误解文案不依赖 hover 可见；keep 计算与导出消费语义零改动；golden 锁 describe 全绿。
**record**: `record-3.0.5-P4-1.md`

### P4-2 R5.7 + R5.9 + R5.10 + R5.14 覆层/文案/守卫族（TrackLane · WaveformEditor · SegmentBlocksLayer · Timeline · main.py 1 行；**约束③ 同 commit 族**）

- [ ] **约束③ 同 commit 族（硬约束）**：R5.7 覆层/tooltip 文案、R5.9、R5.10（含 R5.6③ 覆层 title 相交尾注）同 commit 族合入（WaveformEditor/SegmentBlocksLayer 防冲突）；R5.14 与 R5.9 显示名半条同 commit 施工
- [ ] R5.7（SPEC M5.7）：TrackLane 增 `globalEditMode` prop + trim 门 `:update-time="globalEditMode ? undefined : updateTime"`（WaveformRow :350 / WaveformEditor :1550 附近两父透传）；lane 三结构项（:190/:196/:202）编辑态拦截 + `toast` emit 纯增 + 文案「请退出编辑模式后重试」；**严禁**在共享 SegmentBlock/SegmentBlocksLayer 内无差别拦截（SG-3）；双 toggle title 与 README 写明冻结矩阵 + 主/副轨不对称理由（焦点 4a）
- [ ] R5.9：覆层 title 按 action×status 中文语义化（:390，含相交尾注）+ Timeline tooltip 中文化并轨感知（:625）+ main.py 重译拒绝文案显示名（:3002-3005，1 行）；R5.10：visibleEditRanges **新增** rejected 过滤条件（E-6 只增，confirmed/pending 面 golden 锁零触碰）+ 建段 toggle 显示态改绑实际门（「建段（已暂停）」半亮）+ 气泡 Esc 关闭与点外消泡；R5.14：渲染层条件拼接指引（AIAssistantPanel :470-472 按「同语言翻译轨已存在」子串，不在 useLlmTasks 数据层拼——SG2-6；文案拼接无断言面，M-gate 豁免明示）
- [ ] 用例：R5.7 ≥4（trim 拦截 / lane 三项拦截 / 退出恢复 / **主轨 trim 反向断言：globalEditMode ON 主轨仍可拖**）；R5.10+R5.11 合并 ≥2 的 R5.10 半边（rejected 退场）；**断言反转登记：SegmentBlocksLayer.test.ts:364/:366 反转 + findOverlays 选择器追认制登记（非 expect 行）随本步落 record 反转清单**

**验收方式**: M-gate 前端 R5.7 ≥4 + R5.10 半边；门禁全绿（动手前序 6 复跑）。
**验收标准**: 编辑态副轨 trim/lane 结构项被拦有中文 toast、退出全恢复；主轨手势矩阵既有断言零改动；golden 锁 describe 全绿。
**record**: `record-3.0.5-P4-2.md`

### P4-3 R5.11 + R5.15 + R5.16 审阅体验与清理批（useLlmTasks · WorkspacePage · AIAssistantPanel · useWorkspaceActions · perf 例；**序 8 落点**）

- [ ] **序 8 前置（硬约束）**：R5.11 开发基线必须包含 P2 的 useWorkspaceActions.ts 改造（同文件族 + pendingCorrections 消费面）——**P4∥P1-P3 并行假设的唯一显式收窄点**，本步开工前置 = P2 已合入
- [ ] R5.11：审阅 modal 按 activeListTrackId 过滤 + 「全部」切换（「全部」= 现状不过滤）；启动新纠错 reset 延后至新结果返回（useLlmTasks :308-313；消费 lastTranslationCompletion——结构已由 P1-4 序 7 定形）；时间码 mm:ss.s 解析兼容纯秒 + 「取播放头」+ clamp 回显 + 成功 toast
- [ ] R5.15：删除/级联删除 toast 补「已删除 N 段，可 Ctrl+Z 撤销」（:504/:539；整轨 N = getProject() 该轨 segments 数；级联附「及其关联数据」；不加确认框——record-3.0.4 §7.1 裁决维持）
- [ ] R5.16：useRowLayout.perf.test.ts 根修（确定性计时 / 注入 clock，移除墙钟阈值）；根修完成 → 豁免口径退役、门禁按全绿判销账；未完成 → 维持豁免并按超期决策树回池（缓冲阀）
- [ ] 用例：R5.10+R5.11 合并 ≥2 的 R5.11 半边（按轨过滤 / 时间码）+ R5.15 级联删除计数 1 例（整轨 N 断言面，SG2-5）

**验收方式**: M-gate 前端 R5.11 半边 + R5.15 1 例；门禁全绿。
**验收标准**: 主/副轨审阅互不稀释；启动纠错无「暂无」假象；时间码三态反馈齐全。
**record**: `record-3.0.5-P4-3.md`

### P4-4 R5.12 prompt 语义说明 + D4 测试轮 + beta.3 节点（core/llm_prompts.py · tests/）

- [ ] R5.12：`_SUBTITLE_CORRECTION_SYSTEM_A`（:51）末尾增 aligned_main_text 语义说明一句（受控增行；注册表键集不变零改动——区间实测 :157-194；键集类测试如受影响按 3.0.4 §4.1 追认制登记）
- [ ] D4 四项测试轮（PRD §7.4 移交落点；**不占 ≥30/≥24 额度、增量如实登记**）：detect_silence 本体 / 端到端串测 / padding=0 交叠 / basic 空白点击建重叠段（兜数据安全，优先补）
- [ ] ★ beta.3 节点：P4 末全套门禁（期望 ≥863 / ≥864·863）+ 打 tag `v3.0.5-beta.3` + record；★ 真机冒烟按 beta.3 轮清单（后置先例同前）

**验收方式**: beta.3 期望总数达标；R5.12 无独立用例额度（键集追认制）。
**验收标准**: 副轨纠错 prompt 含语义说明；D4 四项用例入库全绿。
**record**: `record-3.0.5-P4-4.md`

---

## Phase 5: 收尾与发布（1-1.5 天）→ `v3.0.5-rc.1` → `v3.0.5`

### P5-1 门禁终检与登记核对

- [ ] 全量复跑：pytest（= beta.3 期望，只增不减）/ vitest / build / lint / ruff / 红线命令全量（P5 终检全量复跑口径）
- [ ] 后端改动登记表逐条核对（SPEC 附录 A）：每 hunk 有 R 编号；受控改点 (a)-(f) 与 M0-2 一一对应；main.py 两处登记改点（R5.3 合流 hunk / R5.4 expose 透传）逐 hunk 在表；无对应者补登记或回退
- [ ] 断言反转清单核对：后端 2 行 + 前端 2 例 3 行 + 追认制 1 行逐条在 record 落档；白名单外零命中
- [ ] 禁改面终检：`core/models.py` / events 双侧 / `dev.py` / `build.py` / `pywebvue/**` diff 为空；两项「登记不修」现状缺陷（MF2-1 判据不对称 / SG2-2 非翻译 errorMsg 残留）勿误判漏改

**验收方式 / 标准**: 全套门禁 exit 0；核对记录贴 record。
**record**: `record-3.0.5-P5-1.md`

### P5-2 README 回填与版本池回写

- [ ] README_zh / README 3.0.5 功能段：增量补译与缺口语义 / 质量模式（含约 5× 时延标注）/ trim 冻结矩阵（含主/副轨不对称理由）/ 覆层三态语义 / 取消中性提示
- [ ] 版本池回写（PRD §10）：出池登记（版本池 4 + record §8.1 4 + 散落 1 + 清债池 1）；新增登记 ① S6（3.1.x）/ ② 纠错侧上报不做 / ③ 补译进度流式；D3 处置 = R5.16 完成则销账，未完成回池并维持门禁注记

**record**: `record-3.0.5-P5-2.md`

### P5-3 真机冒烟 + 发布

- [ ] ★ RC 全量回归（双平台）：「真机冒烟清单」全轮复跑 + 沿承 3.0.4 清单（翻译全链 undo 三层一致 / 纠错双轨轨徽门控 / 编辑扫掠副轨 / lane 建段 / 语义搜索 / 手动范围全链 / keep 重跑）→ 用户签字
- [ ] 版本 bump → `v3.0.5-rc.1` → 合并主干 → `v3.0.5`（tag 落地签字；异常走 smoke-fix 先例：合入分支、tag 不动）

**record**: `record-3.0.5-P5-3.md`

---

## 里程碑与缓冲

| 里程碑 | 内容 | 相对占位（开工日 D0） | 绝对日期（触发式回填——§0.4 #6，3.0.4 修订-2 ④ 先例延续） |
|---|---|---|---|
| `v3.0.5-beta.1` | P1 末：R5.0 首项 + T-5.1 三件套 + R5.8 + R5.13 | D0+6 ~ D0+9 | （触发式回填） |
| `v3.0.5-beta.2` | P2 末：R5.4 批量审阅收口 | D0+8 ~ D0+11 | （触发式回填） |
| `v3.0.5-beta.3` | P4 末：S3+S4+顺带批+D4（P3 R5.5 已并入门禁） | D0+10 ~ D0+14 | （触发式回填） |
| `v3.0.5-rc.1` | P5 门禁终检 + 真机全量回归绿 | D0+11 ~ D0+15 | （触发式回填） |
| `v3.0.5` 正式 | 签字 → 主干 → tag | rc.1 后 0-1 天 | （触发式回填） |

**口径说明**：日历 11-15 天成立前提 = 顺带批（P4-2/P4-3 纯前端面）与 P1-P3 并行开发（§0.4 #4 承诺口径）+ P3 与 P1/P2 并行开发（序 5）；单人串行备份 15-19 天；P4-3 受序 8 收窄（R5.11 须待 P2 合入）。人日 13.5-17.5 不乐观折减，压缩全部来自并行开发窗口。

**超期决策树**（触发即提请用户，PM 不擅自降级；授权与四要素留痕见 §0.4 #5）：

```text
触发 A（实施期即判）：R5.8 实测成本将超其 1-1.5 人日上界（R2 规模复核条件延续）
  → 首让 R5.8 整体回池（含受控改点 (f) 与 config 键；回池口径照 PRD §10.1；
    R5.3 不受牵连——(d)/(f) 在登记表分行登记、hunk 可独立回退）
触发 B：beta 锚点滑动使日历偏差 > 2 天
  → 按次让序让位：R5.7 lane 菜单半（trim 半保留）→ R5.11 时间码增强半 → R5.14；
    每次让位按四要素留痕并回写 PLAN 步骤注记
仍超：立项会重报日历（并行假设失效时按单人串行 15-19 天备份口径重报）
不可让：R5.0 / R5.1 / R5.2 / R5.3 / R5.4 / R5.5 / R5.6（首项 + 六主项核心面，裁决②）
```

## 真机冒烟清单（分 beta 轮；双平台；异常走 smoke-fix 先例：合入分支、tag 不动）

| 轮次 | 节点 | 清单（对齐 SPEC M-gate 真机清单 + 研究报告 §8.4 + PRD §9.3） |
|---|---|---|
| beta.1 | P1 末 | duplicate 防呆手感（重复框选/双击/时间码重复提交：轻提示、undo 栈不涨）；翻译失败→补译全链（至少一家非 json_mode 提供商 Qwen/GLM/Ollama：中文指引 / token 上报 / 缺口对账可读可定位 / 一键补译 / undo 一次回退）；取消中性提示与连续 429 降级可见；token 量级预估显示 |
| beta.2 | P2 末 | 批量按钮作用域（主轨视图操作不吞副轨待审集；确认文案轨名/条数；「全部」明示；批量 undo 一次回退手感） |
| beta.3 | P4 末 | keep invalidated toast 可见性与确认文案直显；trim 冻结矩阵手感（编辑态副轨 trim/lane 菜单拦截、退出恢复、主轨零变化）；时间码 mm:ss / 取播放头 / clamp 回显 / 成功 toast；rejected 覆层退场 + 建段降档 + 气泡 Esc/点外消泡；大工程纠错取消约 1s 手感（R5.5，P3 合入后并入本轮） |
| RC | P5 | **千段翻译耗时与 token 观测值回填（record-3.0.4 §6 ③ 顺延债，本版必填）** + 全量回归 + 签字 |

## record 落盘要求

- 命名（record-3.0.4 §1 先例）：每步 `record-3.0.5-<step>.md`（如 `record-3.0.5-P1-4.md`）；总记录 `record-3.0.5.md` §1 分步索引表逐步登记（步 / record 文件 / 状态 / 合入 commit）
- 后端改动登记表：SPEC 附录 A 模板，每步 record 追加 + 总表逐 phase 汇总，P5-1 逐条核对；前端文件同样登记（3.0.4 record P2-4/P2-5 行先例），类别按「受控改点 (c)/(b) 前端面 / 登记改点」
- 断言反转白名单登记：§0.2 全清单（后端 2 行 / 前端 2 例 3 行 / 追认制 1 行）随对应 phase 落 record 反转清单，含意图与理由；ledger 记 failed 批的断言全保留
- 超期决策树触发（如有）：按 §0.4 #5 四要素留痕并回写本文与 PRD/SPEC 对应条目（「已砍（日期）」）
- 现状缺陷登记不修（P5-1 勿误判漏改）：MF2-1 纠错外层/串行记账判据不对称、SG2-2 非翻译任务取消 errorMsg 残留——均入 record §8 遗留

## 风险登记表（PRD §8 转化，PM 视角）

| 风险 | 触发信号 | 缓解与落点 |
|---|---|---|
| R5.3 管线失败语义改判回归（高） | 1/N mock 用例失败 / SG-1 守恒不成立 | 断言白名单预登记；全批失败仍拒；序 7 合流先行；P1-4 独立短分支可整步回退 |
| R5.4 作用域化回归（中-高） | 双轨互扰用例失败 | 默认 None 逐字节等价门禁 + 三态回归锁；P2 拆两步、门禁独立可回滚 |
| R5.8 串行与并发互扰（中） | 关闭路径等价断言失败 | 默认关 + (f) 默认路径逐字节保留；首让位缓冲阀 |
| R5.7 行为收窄误伤主轨（中） | 主轨手势/trim 既有锁失败 | TrackLane 轨角色边界守卫 + 主轨 trim 反向断言（P4-2） |
| 红线 diff 审查纪律（中） | 白名单外 diff / 断言检查白名单外命中 | 登记表逐 phase 追加 + 门禁脚本每 phase 复跑 + P5-1 逐条核对 |
| 天数超限（中） | beta 锚点滑动 | 决策树首让 R5.8 → 次让序（R5.7 lane 半 → R5.11 时间码半 → R5.14）；四要素留痕 |
| 行号漂移 / SPEC-PLAN 冲突（低-中） | 实施中 file:line 不符 | 符号名检索兜底（SPEC 头注）；冲突以 SPEC 为准，当场修本文 + record 登记 |

## 规模对照

- 后端净变更约 350-550 行（llm_service 为主；六白名单文件 + ≥30 用例）、前端约 400-600 行（+ ≥24 用例）——PRD §7 终值口径，本版不开新能力面
- 高风险两项落点：R5.3 → P1-4（序 7 内部序 + SG-1/MF2-2 断言三件套）；R5.4 → P2-1/P2-2（默认 None 等价门禁 + 三态回归锁）

——本文完（R6 轮项目经理定稿；执行者按 §0.3 顺序约束开工，逐步勾销并落盘 record；R7 编排终检注意点见 review-log R6 章节）

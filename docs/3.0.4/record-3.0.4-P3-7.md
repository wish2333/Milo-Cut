# record-3.0.4-P3-7：建议面板手动范围分组 + 时间码 popover（M4-3 前半，R4.3a）

> 日期：2026-09-06　分支：`dev-3.0.4-p3-7`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-7　SPEC：M4-3 表第 1 行（SuggestionPanel.vue:63-99 触点）+ M4-2「时间码入口」段（R3 落点勘误 = 面板头部条，不放分组头）　PRD：R4.3a（SPEC 改裁后口径）
> 前置：P3-5（`add_range_decision` expose，pending 默认 / ±0.05 幂等 / clamp）、P3-6（气泡入口 `WorkspacePage.handleRangeDecision`）。**后端零新增**（逐条确认/拒绝复用 `update_edit_decision`、删除复用 `delete_edit_decisions_batch`，全部既有 expose）。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/workspace/SuggestionPanel.vue` | 改动 | +214/-17 | ① 第三源分组「手动范围」（`source === "manual"` 过滤，`push` 空组守卫照旧）；② `ItemKind` 增 `"manual"`、`SUGGESTION_SOURCES` 增 `"manual"`、计数器并入（keep 条目计数，§2.1）；③ 确认按钮 title 显式「确认 = 参与裁剪计算」（delete/keep 两变体）；④ manual pending 显式状态徽 `[·]`（§2.2）；⑤ 头部条「+ 时间码」按钮 + popover（起止数字输入 + 删除/保留二选 + 就地错误提示）；⑥ 窗口 click/Escape 关闭 popover（既有 context menu 监听扩展，context menu 在场时行为逐字节不变） |
| `frontend/src/pages/WorkspacePage.vue` | 改动（最小接线） | +8/-0 | `provide("suggestion:add-range-decision", handleRangeDecision)` 一行接线 + 注释（§2.3 裁决）；`handleRangeDecision` 本体零改动（P3-6 交付复用） |
| `frontend/src/components/workspace/SuggestionPanel.test.ts` | **本步新建宿主** | +303/-0（新文件） | 6 例（§4）：生命周期 / 确认文案 / 组删除顺序 / 时间码常驻 + 非法拒绝 / 合法提交链 / keep 二选 + 计数与既有两分组；harness 接真实 `useAnalysis`（生产同款接线） |
| `docs/3.0.4/record-3.0.4-P3-7.md`（本文）、`record-3.0.4.md` §1、`plan-v3.0.4.md` P3-7 | 文档 | — | 登记与勾销 |

其余全部零改动：**Timeline.vue / useWorkspaceActions.ts / useAnalysis.ts / WaveformEditor / SegmentBlocksLayer（P3-6 已定形）/ SegmentBlocksLayer 覆层样式（P3-8 才动）/ 后端全部 / 其他前端文件**（红线清单逐一核对，git diff 文件集 = 上表）。

## 2. 二选一裁决与实现选型（登记）

1. **计数器并入口径**：`isCounted(e) = SUGGESTION_SOURCES.has(e.source) && (e.source === "manual" || e.action === "delete")`——manual **两种 action 都计数**（SPEC「计数含 keep 条目」），静音/智能删除两 legacy 源保持 delete-only 过滤**逐字节不变**（两源从不产出 keep edit，既有场景计数零变化）；`totalPending`/`totalAll` 同口径。
2. **keep 与 delete 区分（SPEC 二选一）→ 取「条目 label 前缀」，不设分组内小节**：label = `删除 {end-start 1 位小数}s` / `保留 …s`，即条目级 action 徽（与静音「静音 X.Xs」/智能「智能删除 X.Xs」同构）；分组内不再切小节（分组本就只有 manual 一个 source，小节徒增层级）。status 三态样式对齐既有徽章：confirmed = 既有 `[Y]` 绿 / rejected = 既有 `[N]` 灰 / **pending = 新增 `[·]` 徽（仅 manual 条目，title 待处理）**——既有两分组 pending 保持无徽现状（DOM 零变化），manual 三态全显。
3. **时间码提交接线（任务书「读清事件流再定」的裁决）→ 取 provide/inject，不走 emit**：SuggestionPanel 实际挂载于 **Timeline.vue:775**（Timeline → WorkspacePage 两级），非任务书所述「WorkspacePage 绑定区」；Timeline 对 SuggestionPanel 的 emit 白名单是七事件全量转发（:781-787），新增 `add-range` 类事件必须改 Timeline 中转——**红线禁改 Timeline.vue**。故照 `WORKSPACE_ACTIONS_KEY` 先例（useWorkspaceActions.ts:1126「child components can inject it instead of receiving long props/emit chains」）由 WorkspacePage 直接 `provide` 回调、面板 `inject`：时间码入口与气泡**共用同一个 `handleRangeDecision`**（pushSnapshot(["edits"],"手动范围") → `call("add_range_decision",…)` → project-updated patch / 失败 toast），两入口零逻辑分叉。**key 用字符串 `"suggestion:add-range-decision"` 而非 InjectionKey**：红线文件清单（SuggestionPanel / WorkspacePage / 新测试宿主）无处安放共享 symbol 模块，SFC 双 script 块导出亦无本仓先例；两端各自声明函数类型，vue-tsc 全绿。
4. **popover action 二选一（SPEC 留白）→ 取「删除/保留二选，默认删除」**：与气泡同款（M4-2 Q9 默认 action=delete 聚焦先例），两个 mc-button 切换式按钮（选中态 primary / 未选 secondary），无第三态。
5. **manual 分组默认展开**（`expandedGroups` 初始集增 `"manual"`）：分组仅在已有手动范围时存在（空组守卫），首条范围创建后立即可见；静音/智能删除两分组默认态不变。
6. **提交后乐观关闭 popover**（面板侧无法观测 handleRangeDecision 成败——handler 返回 void，失败 toast 在页面层）：就地校验不过不关不调桥；合法提交即关。输入值保留不清空（口播场景常连续建邻近范围）。
7. **popover 形态 = 头部条内 `absolute top-full right-0` 下拉**（SilenceSettingsPopover 等三既有 popover 同款定位族）：面板根 `overflow-hidden` 只裁出界内容，popover 下拉落在面板体内列表区之上（z-dropdown），无裁剪问题；不用 Teleport（无出界需求）。

## 3. SPEC 对照（M4-3 表第 1 行 + M4-2 时间码入口段）

| SPEC 要求 | 实现 | 测试锚 |
|---|---|---|
| `source === "manual"` edits → 「手动范围」分组（与静音/智能删除并列） | `groups` computed 第四个 `push("manual", …)`，空组守卫照旧（无手动范围时分组整体隐藏） | #1 分组头渲染；#6 三分组并列 |
| 条目 label = `删除/保留 {时长}s` + status 徽 | label 前缀 + `[·]`/`[Y]`/`[N]` 三态徽（§2.2） | #1（删除 3.0s + 待处理徽 → confirmed `[Y]`）；#6（保留 1.5s） |
| 逐条确认/拒绝复用 `update_edit_decision` | 面板既有 `confirm-edit`/`reject-edit` emit → Timeline 中转（既有）→ WorkspacePage:1546-1547 → useAnalysis.confirmEdit/rejectEdit | #1：`call("update_edit_decision", id, "confirmed")` |
| 逐条/批量删除复用 `delete_edit_decisions_batch` | 组 context menu「删除本组建议」（既有 `delete-edit-batch` 链，confirm 弹窗照旧） | #3：`call("delete_edit_decisions_batch", ids)` |
| 确认文案显式「确认 = 参与裁剪计算」 | manual 条目确认按钮 title（keep 变体加「保留区间将从自动裁剪中扣除」） | #2：两变体 title 断言 |
| `SUGGESTION_SOURCES` 与计数器并入 manual（含 keep） | §2.1 | #6：共 3 处建议 / 3 处待处理（含 keep） |
| 时间码入口 = 面板头部条（:190-199 锚）右端「+ 时间码」+ popover | 头部条改 flex 布局右端按钮 + §2.7 popover；**头部条常驻**（v-if 无条件）——空工程也能创建第一条（R3 勘误落点理由兑现） | #4：`edits=[]` 时按钮在场 + 「共 0 处建议」 |
| 非法输入 end<=start / 空 / 非数 → 拒绝（就地提示，不调后端） | `submitTimecode` 就地校验：空/非数 → 「请输入有效的起止时间（秒，支持小数）」；end<=start → 「结束时间必须大于开始时间」；零桥调用、popover 不关 | #4：两种非法各断言 error 文本 + callMock/pushSnapshot 零调用 |
| 提交 → 与气泡共用 `add_range_decision`，调用前 `pushSnapshot(project, ["edits"], "手动范围")` | §2.3 共用 `handleRangeDecision`（P3-6 既有，本步零改动） | #5：pushSnapshot 参数 + 先于 call（invocationCallOrder）+ patch 经 project-updated 通道流出 |
| 撤销全链 pushSnapshot(["edits"]) | 建（时间码）= handleRangeDecision 内（P3-6）；确认/拒绝 = useAnalysis `onBeforeProjectUpdate(["edits"],"编辑决策")`（既有）；删除 = 同上且**先于桥调用**（不可逆操作先快照） | #3 顺序断言；#5 顺序断言 |

## 4. 测试（+6 例，新建宿主 `SuggestionPanel.test.ts`）

vitest **820 collected（814 → 820，+6）/ 819 passed**。harness = SuggestionPanel + **真实 useAnalysis**（`@/bridge` mock：call 捕获 + onEvent 空操作），接线 1:1 复刻生产链（SuggestionPanel `@confirm-edit/...` → Timeline :781-785 中转更名 → WorkspacePage:1546-1550 绑定 → useAnalysis），故桥断言命中的是生产调用路径；时间码注入目标 = `handleRangeDecision` 1:1 复刻件（**生产注入目标本体已由 WorkspacePage.rangeDecision.test.ts【P3-6 宿主】就气泡入口覆盖**——同一函数、同一注入值，本宿主补的是面板→注入→handler 的新链路段）。

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | 手动范围生命周期 | pending edit（2-5s）→ 分组头「手动范围」+ 条目「删除 3.0s」+ `[·]` 待处理徽 → 点确认 → 面板 emit `confirm-edit` `[[id]]` + **`call("update_edit_decision", id, "confirmed")`** → setProps 注入 confirmed → `[Y]` 徽在场 / `[·]` 与确认按钮退场 |
| 2 | 确认文案 | keep 条目（保留 1.0s）与 delete 条目（删除 2.0s）确认按钮 title 均含「**确认 = 参与裁剪计算**」；keep 变体另含「保留区间将从自动裁剪中扣除」 |
| 3 | 组删除顺序 | 组 context menu「删除本组建议」（Teleport→body，window.confirm stub true）→ **`call("delete_edit_decisions_batch", [两 id])`** + `pushSnapshot(anything, ["edits"], "编辑决策")` 且 **invocationCallOrder 先于 call**（快照先行，不可逆删除） |
| 4 | 时间码常驻 + 非法拒绝 | `edits=[]` → 「共 0 处建议」+ 「+ 时间码」按钮在场；10/10 提交 → 「结束时间必须大于开始时间」+ call/pushSnapshot 零调用 + popover 不关；空 start → 「请输入有效的起止时间」+ 零调用 |
| 5 | 合法提交链 | 2.5/7 默认 action → `pushSnapshot(anything, ["edits"], "手动范围")` **先于** `call("add_range_decision", 2.5, 7, "delete")`（默认 delete 断言）→ patch 经 project-updated 通道流出（`patchesOut == [patch]`）→ popover 乐观关闭 |
| 6 | keep 二选 + 计数 + 既有分组 | 静音/智能/manual-keep 各 1 pending → 「共 3 处建议 | 3 处待处理」（keep 计数）+ 三分组头并列 + legacy 条目 label 不变（静音 1.5s / 智能删除 1.5s）+ popover 选「保留」→ `call("add_range_decision", 3, 4.5, "keep")` |

- **既有 vitest 断言零删改**：全部 6 例在新宿主纯新增；Timeline.test.ts 对 SuggestionPanel 仍 stub（:35，本步未触碰），其余宿主零改动（全量 819 passed 自证）。
- 测试侧裁量登记：① harness 用真实 useAnalysis 而非 mock——桥调用与快照顺序断言才有生产意义（WorkspacePage 级三宿主均 mock useAnalysis，无法断言该链）；② `vi.stubGlobal("confirm")` 替换组删除 confirm 弹窗（happy-dom 原生 confirm 返回不可控）；③ context menu 经 Teleport 落 body，用 `document.body.querySelectorAll` 取菜单按钮（wrapper.find 不可见 Teleport 内容）。

## 5. 门禁（脚本命令逐项，全绿）

- pytest：**819 passed，exit 0**（后端零改动，与 P3-5/P3-6 持平）
- ruff：All checks passed（0 problems）
- vitest：**820 collected / 819 passed**（唯一失败 = `useRowLayout.perf.test.ts` 挂载墙钟 678ms vs 8ms 预算——record-3.0.3 §5 遗留 #5 已登记环境例，单独复跑同败自证与本步无关；814 → 820 = 本步 +6）
- build：`vue-tsc --noEmit` exit 0 + `vite build` exit 0
- lint：eslint **0 errors 0 warnings**
- redline 段（`bash scripts/gates-v3.0.4.sh redline`）：全部通过 exit 0（后端 diff 白名单 = P1/P2/P3-5 既有 8 文件，本步零新增；R0-2 events 双侧零新事件；dev.py/build.py 零改动）

## 6. 偏离与边界登记

- **接线机制偏离任务书措辞（裁决已登记 §2.3）**：任务书预期「SuggestionPanel 绑定区在 WorkspacePage.vue」——实际挂载在 Timeline.vue:775（WorkspacePage 绑定的是 Timeline，:1546-1550 为经中转更名后的建议事件）；红线禁改 Timeline.vue，故时间码提交走 provide/inject 而非 emit 上抛。行为等价：与气泡共用同一 `handleRangeDecision`（SPEC「两个入口共用 add_range_decision」字面达成），pushSnapshot/project-updated 全在既有函数内，useWorkspaceActions 零触碰（红线字面达成）。
- **popover action 二选一**：取「删除/保留二选 + 默认删除」（§2.4，SPEC 留白登记）；**keep/delete 区分**：取「条目 label 前缀」不设小节（§2.2，SPEC 二选一登记）。
- injection key 用字符串非 InjectionKey（§2.3 尾）：红线文件清单无处安放共享 symbol；如后续步骤放宽文件清单可升级为 symbol（行为不变）。
- 波形覆层三态（keep 蓝 / pending 降档）属 **P3-8**，本步覆层渲染零触碰；`deleteRanges` pending 排除的快照锁定用例亦归 P3-8。
- 时间码 popover 的真机观感（数字输入滚轮步进、popover 遮挡列表区的观感、连续建范围工作流）归 P4 冒烟清单；面板内 popover 在窄侧栏（默认宽）下的换行未专项适配（w-64 固定宽 + 头部条 flex 收缩，极端窄度下按钮 shrink-0 保在场）。
- 面板挂载链上 `provideWorkspaceActions` 与本步新增 provide 同层共存（无键冲突；字符串键本仓唯一，前缀 `suggestion:` 留有命名空间）。

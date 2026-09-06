# record-3.0.4-P2-5：前端门控与审阅（AIAssistantPanel prop 门控 · Timeline 精华 tab 门控 · 纠错轨透传 · 审阅轨徽）

> 日期：2026-09（P2 收官步）　分支：`dev-3.0.4-p2-5`（待合入 `dev-3.0.4`）
> 对应 PLAN：Phase 2 / P2-5　SPEC：M2-4（R2.4）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `frontend/src/components/workspace/AIAssistantPanel.vue` | +75/-7：① 新增 `isTrackMode` computed（= `Boolean(activeTrackId)`，SPEC 裁决「轨模式判定」）+ `MAIN_TRACK_ONLY_HINT` 常量 + `isFeatureTrackGated(key)`（轨模式下仅 `smart_delete` 命中）；② `selectFeature` 增轨门控早退（置灰态点击不开详情——守卫而非样式）+ 新增 `switchPanelMode(mode)`（工作流入口守卫）；③ `handleStartSmartDelete` 增 `isTrackMode` 早退（双保险：主轨开的详情切轨后也不 emit start）；④ watch `isTrackMode` 变 true 时关闭已开启的门控功能详情（回落裁决，同 Timeline 精华 tab 口径）；⑤ 模板：智能删除卡 disabled + 置灰类 + `title="仅主轨可用"` + 右上角「仅主轨可用」小字标签（对齐既有「未配置」样式位）；纠错卡不置灰 + 卡底显式轨徽 `当前轨：{track_name}`（`activeTrackName || activeTrackId` 防空回退，title 同文案；主轨视图不渲染）；工作流 mode-switch 按钮 disabled + title + 置灰类；搜索卡/翻译卡零触碰 | R2.4 | 登记改点 |
| `frontend/src/components/workspace/Timeline.vue` | +39/-5：① `isTrackMode` 之后新增 M2-4 B 块：`HIGHLIGHT_TAB` 常量 + `isTabTrackGated(key)`（轨模式下仅 highlight 命中）+ `selectTab(key)`（门控 tab 点击不落地，守卫而非样式）+ watch `isTrackMode` 变 true 且 `activeTab === "highlight"` → 自动回落 `"suggestion"`（不停留在不可用视图，R3 must-fix #2）；② tab 按钮区：`data-test="sidebar-tab-{key}"` + 门控 tab disabled + `title="仅主轨可用"` + `cursor-not-allowed opacity-50`（**置灰而非隐藏**，三 tab 布局稳定）；建议 tab 不门控。props 链零触碰（P1-6 已交付，本步只消费） | R2.4 | 登记改点 |
| `frontend/src/composables/useLlmTasks.ts` | +13/-2：仅 `startSubtitleCorrection(referenceText = "", trackId = "")` 增第二可选形参，桥调用改四位置参 `call("start_subtitle_correction", referenceText, "", 3, trackId)`（P2-2 后端签名 `(reference_text, timeline_id, context_window, track_id)`；中间两参保持后端默认 timeline=""=active / window=3；"" = 主轨，v3.0.3 语义不变）。SubtitleCorrection 接口零触碰（见 §6） | R2.4 | 登记改点 |
| `frontend/src/pages/WorkspacePage.vue` | +41/-1：① C 项：deps 字面量（:887 一带，本页对 startSubtitleCorrection 的唯一调用点）将裸函数改为包装 `(referenceText) => startSubtitleCorrection(referenceText, activeListTrackId.value ?? "")`——useWorkspaceActions 冻结（P2-4 红线）不改一字，hub 仍以单参调用，轨 id 在本页注入；② D 项：script 新增 `correctionTrackName(corr)` 窄类型扩展 helper（运行时条目带 track_name、本地 SubtitleCorrection 类型先于该字段——经 `CorrectionEntryWithTrack` 交叉类型读取，同 P2-4 CorrectionReviewEntry 手法）；审阅 modal 高/低置信度两区块各加来源轨徽 `<span v-if="correctionTrackName(corr)" data-test="correction-track-badge">来源轨：{track_name}</span>`（非空显示、空 = 主轨不显示）；renderDiff 与条目时间/文本渲染零改动（后端 get 已按 scope 解析，显示侧直接消费返回值，已核实 modal 无自行查段逻辑） | R2.4 | 登记改点 |
| `frontend/src/components/workspace/AIAssistantPanel.test.ts` | +99/-0：追加「track-view gating (v3.0.4 M2-4)」describe 6 例（§3 #1/#2/#3 及工作流/搜索/详情回落）；既有 13 例零改动 | R2.4 | 只增 |
| `frontend/src/components/workspace/Timeline.test.ts` | +53/-0：追加「highlight tab gating (M2-4)」describe 3 例（§3 #4/#5 + 主轨零回退）；既有 24 例零改动 | R2.4 | 只增 |
| `frontend/src/pages/WorkspacePage.correctionTrack.test.ts` | 新建 3 例（§3 #6/#7）；宿主仿 WorkspacePage.translation.test.ts（全 composable mock + vi.resetModules 新图），差异 = useWorkspaceActions mock **捕获 deps 字面量**（C 项注入点在场证明） | R2.4 | 只增 |

`useWorkspaceActions.ts` / `App.vue` / `SemanticSearchBar.vue` / `SuggestionPanel` / `TranscriptRow` / `Waveform*` **零改动**；后端 `git diff dev-3.0.4 -- core/ main.py` = 0 行。

## 2. SPEC M2-4 触点表逐行对照

| SPEC 触点 | 落实 |
|---|---|
| WorkspacePage / Timeline:727-743 透传 active-track-id/name | P1-6 已交付，本步零 diff 仅消费（按 R3 顺序约束） |
| Timeline :333-337/:578-586/:745-759 精华门控（R3 must-fix #2） | §1 Timeline.vue 行：置灰（disabled + title）非隐藏 + 停留回落 suggestion；建议 tab 不门控 |
| AIAssistantPanel :125-147 轨模式门控 | §1 AIAssistantPanel.vue 行：智能删除置灰 + 文案；纠错可用 + 轨徽（锁定不弹选择——面板本无轨选择 UI，徽即锁定声明）；搜索不置灰；工作流入口置灰（存在性核查见 §5）；翻译维持 M1-6（SPEC 未列，不加门控） |
| useLlmTasks :269-280 透传 + 调用点传 activeListTrackId | §1 useLlmTasks.ts + WorkspacePage.vue deps 包装两半；主轨视图调用形状 (`"", 3, ""`) 与后端默认等价零语义漂移 |
| 审阅 modal 条目按 track_id 解析 + 轨徽 | 后端 get（P2-3）已按 scope 解析时间/文本，前端渲染直接消费（测试断言 formatTimeShort(1.2) 轨段时间直显）；轨徽非空显示空不显示；renderDiff 零改动 |

边界遵守：主轨视图（activeTrackId 空）下面板与 Timeline 与 v3.0.3 完全一致——所有门控分支均以 `isTrackMode` 短路，主轨路径类名/disabled/事件与改动前逐字节等价（既有 37 例零改动全绿 + 两条显式零回退断言双证）；主轨纠错无轨徽。

## 3. 测试清单（PLAN P2-5 用例栏 7 项 → 实收 12 例）

| # | PLAN 要求 | 用例（文件 · 名称） | 锁定 |
|---|---|---|---|
| 1 | 轨模式智能删除卡置灰且点击不 emit start | AIAssistantPanel · "greys out the smart delete card ... never emits start on click" | disabled 属性 + opacity-50 + title「仅主轨可用」+ 可见小字标签；happy-dom trigger 绕过 disabled 属性仍零 emit（守卫非样式）；详情不打开 |
| 2 | 轨徽「当前轨：{track_name}」 | AIAssistantPanel · "shows the locked-track badge ... on the correction card" | 纠错卡不 disabled、无置灰类；徽文本恰 `当前轨：English`；点击可开详情（轨模式可用性） |
| 3 | 主轨视图零回退 | 既有 13 例零改动全绿 + · "main-track view shows no gating artifacts (explicit zero-regression)" | 无轨徽 / 无门控标签 / 智能删除与工作流入口均 enabled；另 Timeline · "keeps the highlight tab fully enabled ..." 主轨 highlight 可点选 |
| 4 | 轨模式精华 tab 置灰 + title | Timeline · "greys out the highlight tab in track mode ... blocks the switch" | disabled + title「仅主轨可用」+ opacity-50；trigger 绕过后不切换（selectTab 守卫）；建议 tab 在轨模式 enabled 且保持激活 |
| 5 | 停留精华时 isTrackMode 变 true → 回落 suggestion | Timeline · "falls back to suggestion when track mode turns on while highlight is open" | 主轨点开 highlight（bg-primary-soft）→ setProps activeTrackId → suggestion 激活、highlight 失活 |
| 6 | startSubtitleCorrection 透传 trackId | WorkspacePage.correctionTrack · "deps.startSubtitleCorrection forwards the viewed track id as the 4th bridge arg" | 主轨视图桥参 `("start_subtitle_correction","ref-main","",3,"")`；Timeline stub emit select-track trk_x 后同包装产出 `(...,"ref-track","",3,"trk_x")`——真实 useLlmTasks 单例 + 真实页面包装端到端 |
| 7 | 审阅条目轨徽（非空显示/空不显示） | WorkspacePage.correctionTrack · "badges track-scoped entries ... main-track entries get none" + "renders no badge at all when every entry is main-track scoped" | 混合列表恰 1 徽且文本 `来源轨：English`；全主轨列表 0 徽；两作用域时间（0:01 / 0:05）直显证「渲染直接消费返回值」；共 N 条计数 |
| + | 工作流入口置灰 | AIAssistantPanel · "greys out the workflow mode entry ... blocks the switch" | disabled + title + 点击不进工作流视图（switchPanelMode 守卫） |
| + | 搜索卡轨模式不置灰 | AIAssistantPanel · "keeps the search card enabled in track mode" | 内容搜索卡无 disabled |
| + | 门控详情切轨关闭 | AIAssistantPanel · "closes an open smart-delete detail when the view switches to a track" | 主轨开智能删除详情 → setProps 轨模式 → 详情回落关闭（与 handleStartSmartDelete 双保险互补） |

M1/M2 前端组 P2 份额：≥7 达成（7/7 全覆盖 + 5 补强）。

## 4. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**804 passed**（保持 804，本步零后端改动）
- ruff：0 problems
- vitest：**790 collected / 789 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，3.0.3 已登记环境例豁免；P2-4 基线 778/777 + 12 新例 = 790/789 吻合）
- build（vue-tsc --noEmit + vite build）：通过；lint（eslint .）：0 errors 0 warnings
- 红线 R0-1~R0-5 全 PASS；本步对 `dev-3.0.4` 的 `core/ main.py` diff = 0 行；白名单外 `expect(` 删除 grep = 0（本步前端测试纯追加）
- 环境注记：`bun run` 本沙箱不可用，按 P0-2 回落条款直跑 node_modules/.bin 等价命令（与 P2-4 及此前各步同口径）

## 5. 工作流入口存在性核查结论（交付指令要求）

**存在，已置灰。** 核查路径：AIAssistantPanel.vue 模板 mode-switch 区（D-19，「单功能/工作流」分段按钮）即工作流入口——`panelMode = 'workflow'` 切入工作流配置视图（内含 llm_smart_delete / llm_subtitle_correction / llm_highlight 三步骤与「工作流启动」）。本步对该入口做 disabled + title「仅主轨可用」+ 置灰类 + switchPanelMode 守卫（SPEC M2-4 AIAssistantPanel 行「工作流入口置灰 + 同文案」）。

边界注记（有意不做，待负责人裁）：
- 若轨模式激活**前**已在工作流视图（或工作流正在运行），本步不强制回落 single——运行中工作流的进度视图不应因切轨消失，SPEC 亦未列该回落；步骤内「精华提取」步骤在轨模式无独立置灰（工作流为主轨域整体入口，置灰粒度 = 入口级）。
- 精华入口确认**不在**本面板（R3 勘误成立）：features 仅 4 卡（智能删除/纠错/翻译/搜索），精华 = Timeline 右栏第三 tab，其门控在 B 项落点。

## 6. 未验证边界与交接

- **轨徽/门控真机视觉**（置灰类在 PyWebView 渲染、轨徽截断 truncate 表现）随 beta.2 ★ 冒烟。
- **双时间轴 + 轨模式组合**：切时间轴后 activeListTrackId 归主轨（useListTrackSelector 既有语义），门控随之解除——未专设跨时间轴用例（selector 归属 P1-6 已测）。
- **`correctionTrackName` 的类型读取**：useLlmTasks.SubtitleCorrection 未声明 track_id/track_name（本步红线将 useLlmTasks 限于 start 形参，故经 WorkspacePage 本地交叉类型读取，同 P2-4 §7 交接预判的替代落位）。若 P3 需在别处消费，建议届时在 useLlmTasks 补可选字段声明收敛为单一类型源（登记 3.0.5 候选）。
- **批路径 `handleAcceptHighConfidence`** 仍走 switch_timeline 全量刷新（P2-4 SPEC 边界，本步未触碰）；其与 D 项轨徽无交互（徽只读渲染）。
- **轨模式纠错启动后 SuggestionPanel 审阅入口横幅**：pendingCorrectionCount prop 已按轨语义计数（后端 scope 化 get），本步未加轨徽于横幅（SPEC 未列）。
- demo 模式（DemoResponsiveWorkspace）纠错入口走同一 handleStartSubtitleCorrection → 同一 deps 包装，轨透传天然覆盖；demo 桥 mock 忽略多余位置参（demoBridge.ts:115），无回归路径，未单设 demo 用例。

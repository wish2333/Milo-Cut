# record-3.0.4-P3-4：语义搜索轨模式修正（M3-3，R3.3，X2）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-4`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-4　SPEC：M3-3（根因 + 前端侧裁决 + 改动 + 边界 + 验收）　PRD：R3.3 / X2
> 根因（本步复核）：后端 `semantic_search`（main.py:2875）`timeline_id` 形参缺省回落 `project.active_timeline_id`，而前端 SemanticSearchBar 调用 `call("semantic_search", q, 5)` **从不传 timeline_id** → 恒搜主轨（后端事实，零改动）。轨模式下挂链 `WorkspacePage.vue:1480 :segments="listSegments"`（=副轨段）→ Timeline:729 → AIAssistantPanel:973 → SemanticSearchBar，segmentMap 建自 `props.segments` → 键为副轨 id，后端返回的主轨 segment_id 取值落空 → 文本空、时间 0。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/workspace/SemanticSearchBar.vue` | 受控改点（prop + map 数据源一行） | +9/-2 | 新增 `mainSegments?: Segment[]` prop 声明（含 4 行注释）；segmentMap 数据源 `props.segments` → `props.mainSegments ?? props.segments`（一行）；注释更新 3 行（§2） |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 受控改点（纯透传一行） | +1/-0 | 内嵌 SemanticSearchBar 用法追加 `:main-segments="mainSegments"`（:975，P1-6 链延伸一级；`mainSegments` prop :49 P1-6 既有） |
| `frontend/src/components/workspace/SemanticSearchBar.test.ts` | **新建宿主**（R3 核实该文件此前不存在） | +102/-0 | 3 例（§3）；SPEC 明示新建宿主，非挂既有 |
| `docs/3.0.4/record-3.0.4-P3-4.md`（本文）、`record-3.0.4.md` §1、`plan-v3.0.4.md` P3-4 | 文档 | — | 登记与勾销 |

后端 `core/`、`main.py`、`tests/`、`pywebvue/`：**零改动**。`WorkspacePage.vue` / `Timeline.vue`（P1-6 已交付的透传链上游）：**零改动**。

## 2. SPEC M3-3 改动对照（照表施工）

1. **SemanticSearchBar 新增可选 prop `mainSegments?: Segment[]`**：置于 `llmConfigured` 之后，附 M3-3 语义注释（后端恒搜主轨 / 轨模式 segments 为副轨表 / 结果 id 须对主轨解析）；
2. **segmentMap 数据源一行改**：`for (const s of props.segments)` → `for (const s of props.mainSegments ?? props.segments)`——与 SPEC 伪码 `for (const s of (props.mainSegments ?? props.segments))` 逐字一致；map 键与后端返回的主轨 segment_id 对齐；
3. **AIAssistantPanel 透传**：内嵌处（:973-978）追加 `:main-segments="mainSegments"`，复用 P1-6 的 `mainSegments` prop（:49）延伸一级；
4. **主轨模式零变化**：P1-6 交付的主轨链路 WorkspacePage:1488 `:main-segments="segments"`（`segments` computed = activeTimeline 主轨段）→ Timeline:793 → AIAssistantPanel:975 → 本步——主轨模式下 Timeline 层 `mainSegments ?? segments` 两值相同，不传时 SemanticSearchBar 回退 `props.segments`，行为与 v3.0.3 逐字节一致。

### 边界核对

- 后端零改动：`semantic_search` 不扩展 track 维度（轨维度搜索未立项，PRD §0.2）；
- 点击定位行为不变：命中卡片 click → `emit("seek", item.startTime)` 既有逻辑零触碰，轨模式下 startTime 取自主轨命中段（map 数据源改变的自然结果），定位主轨命中段语义与 SPEC 边界一致；
- `sortedResults` / `handleSearch` / 模板零改动（文本预览/排序/seek 全部经 segmentMap 单点受益）。

## 3. 测试（新建宿主 SemanticSearchBar.test.ts，3 例）

脚手架照 AIAssistantPanel.test.ts 惯例：`vi.mock("@/bridge")`（call + onEvent）；mount 直挂组件 + `llmConfigured: true`；输入 setValue + 搜索按钮 click + `flushPromises` 驱动真实 `handleSearch` 流程（非绕过搜索逻辑直改内部态）。

| # | 用例 | 断言 |
|---|---|---|
| 1 | 轨模式：副轨 segments（track-1）+ 主轨 mainSegments（main-1）+ mock 后端返回 main-1 | 结果文本 = 主轨段文本（非空预览）；点击 → `seek` = `[[12.5]]`（主轨段 start）——文本与时间均取自 mainSegments |
| 2 | 轨模式 id 双侧同名：seg-x 同时存在于副轨（TRACK LIST TEXT, 50s）与主轨（MAIN LIST TEXT, 8.25s） | 文本 = MAIN LIST TEXT 且 NOT TRACK LIST TEXT（map 纯建自主轨，非合并）；seek = `[[8.25]]` |
| 3 | 主轨模式零变化：不传 mainSegments，segments = 主轨段 | 文本正确解析（hello world）；seek = `[[1]]`——回退 props.segments 与 v3.0.3 行为一致 |

- SPEC 验收两条（轨模式文本/时间正确 + 主轨零变化）全覆盖，X2 项 ≥2 达标（实际 3 例）；
- 既有 vitest 断言零删改（新宿主纯新增，R0-3 前端白名单外命中 = 0）。

## 4. 勘误登记（非偏离，不产生额外 diff）

1. **锚点行号漂移**：任务书引 SemanticSearchBar.vue :25-49 / :33-39 锚与 AIAssistantPanel.vue :716 内嵌锚——后者实为 M2-4 卡片区注释位（v3.0.4 P2 批次代码致漂移），SemanticSearchBar 实际内嵌于 AIAssistantPanel.vue:973（SPEC M3-3 正文已自纠「非 Timeline 直挂——报告引 :729 为面板 bindings」）；segmentMap 实际 :33-39（本轮改后 :36-45），语义锚点无歧义；
2. **主轨链上游零触碰**：任务书红线允许面 = SemanticSearchBar.vue + AIAssistantPanel.vue + 新建 tests，WorkspacePage/Timeline 均不在内——P1-6 已把 `mainSegments` 送达 AIAssistantPanel（:49 prop / :219 翻译判定消费），本步仅在最后一棒延伸，红线遵守。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，**exit 0**）

- pytest：**810 passed**（当期期望总数保持，后端零改动）
- ruff：0 problems
- vitest：**801 collected / 800 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟 ~20.7ms，record-3.0.3 §5 遗留 #5 已登记环境例，门禁判定口径内；较 P3-3 基线 798 collected 净增 3 = 本步新宿主用例数，既有断言零删改）
- build：vue-tsc --noEmit + vite build 通过；lint：eslint 0/0
- 红线：R0-1 后端 diff 文件集 ⊆ 白名单（全部为 P1/P2 已登记 hunk，本步零新增）；禁改面空；R0-2 events 双侧一致；R0-3 后端断言零删改；R0-3 前端断言白名单外零删改 = 0；dev.py/build.py 零改动

## 6. 偏离登记

无实质偏离。prop 类型 `mainSegments?: Segment[]`、map 数据源 `props.mainSegments ?? props.segments`、AIAssistantPanel 透传一行均与 SPEC M3-3 改动条目逐字一致；测试 3 例 ≥ SPEC 明示 2 例（第 2 例为 id 双侧同名的对齐性强化断言，纯追加）。

## 7. 红线自证

- 本步改动文件集 = SemanticSearchBar.vue（prop + map 数据源一行 + 注释）/ AIAssistantPanel.vue（透传一行）/ SemanticSearchBar.test.ts（新建宿主）/ 文档——`git diff dev-3.0.4 --numstat -- frontend/` = 两文件 +9/-2、+1/-0，无越界文件；
- 后端零改动；其余前端文件零改动；既有 vitest 断言零删改（纯追加）；vue-tsc / eslint 0/0。

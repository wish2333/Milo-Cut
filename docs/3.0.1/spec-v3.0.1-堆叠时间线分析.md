# v3.0.1 版本分析：堆叠时间线（对照 MAW 参考项目深查）

> 定位说明：**v3.0.0 不作为发布版本**（内部里程碑版）。v3.0.1 的主题定为——把时间线从"单轨波形 + 只读副轨列表"升级为**堆叠时间线（Stacked Timeline）**：主轨与 N 条副轨字幕在同一个时间轴表面垂直堆叠、共享缩放/播放头、支持几何编辑与绑定联动。这是 MAW（`_competitor/moys-asr-workflow-main`）相对我们最重要的结构性优势，也是字幕剪辑工具的核心体验分水岭。
>
> 方法：两路并行逐行深查（MAW 侧：editor.js 17868 行 / waveform.js 5370 行 / editor-utils.js 4964 行 / gap-remove-core.js / DESIGN.md / docs；我方侧：Timeline/WaveformEditor/TrackLane/SegmentBlocksLayer 全组件、useTimelineMetrics/useSegmentEdit/usePlaybackClock/useUndoRedo、core/models.py、project_service、docs/3.0.0 全部 record），关键结论经本人对源码二次核验（TrackLane.vue、models.py:142-180、types/project.ts、projectPatch.ts 等均亲自复核）。

---

## 〇、总裁决

1. **MAW 的堆叠时间线，精华不在 UI，在"数据契约 + 约束算法 + 历史模型"三件套**，且三者全部是框架无关的纯逻辑，可以整体移植到 Vue3/Pydantic 技术栈；其 DOM 手工渲染层（17k 行 editor.js + 全局 DATA）恰恰是反面教材，不应模仿。
2. **我方 3.0.0 已经打好了一半地基**：M11-2 已落地 `SubtitleTrack` / `TrackBinding`（models.py:142-180）、ProjectPatch 的 `tracks`/`bindings` 双 layer、撤销层捕获、300ms 容差副轨 SRT 导入绑定。**缺的只是渲染层与交互层**——TrackLane.vue 目前只是一个 64 行的只读文本列表（TrackLane.vue:5-9 注释自认"bindings written but not consumed"）。
3. 因此 3.0.1 的本质是：**消费 3.0.0 挂账的 M11-2 数据层，把"轨道"从数据概念变成几何概念**。触碰面集中在前端五个模块 + 后端两处（联动编辑、副轨导出映射），不需要数据迁移。
4. 一个必须先纠正的认知：docs/competitor/MAW-竞品分析与优化报告-v2.md 第一节"多轨字幕完全缺失"**已过时**（v2 报告基于 2.3.2 现状写成，3.0.0 M11-2 已改变现状）。本报告以此为准。

---

## 一、MAW 堆叠时间线深查结论（值得移植的六个部件）

### 1.1 数据契约（已部分移植，补齐语义即可）

- 顶层 `segments` 永远是主轨唯一真源；副轨只存在于 `tracks[*].segments`，独立 id 命名空间。
- `bindings[i] = { track_id, main_segment_ids, extension_segment_ids, start_offset_ms, end_offset_ms }`，**offset = ext − main（相对偏移而非绝对时间）**，且 MAW 在任何时间变更后用 `rebuildBindingOffsets` 从当前时间**整体重算**，不做增量维护——避免漂移累积，实现极简（editor-utils.js:3051-3065）。
- `enabled` 只隐藏不删数据；稳定字符串 id 贯穿拆分/合并/绑定/选择恢复，"不得依赖数组下标"是其明文 schema 规则（MULTI_SUBTITLE.md:127）。
- **我方映射**：以上全部已存在（`TrackBinding.start/end_offset` 同为相对偏移语义，models.py:160-169）。缺的只是"消费"：联动编辑、绑定恢复、offset 重算钩子。

### 1.2 约束函数族（3.0.1 交互层的核心移植物，全部纯函数）

MAW 在 editor.js 顶部 ~600 行实现了一套"先算约束、后写状态"的几何编辑内核：

| 函数 | 语义 | 移植价值 |
|---|---|---|
| `getTrackNeighborBounds` (:260) | 同轨前驱 end / 后继 start，**豁免 movedSegments**（支持多选拖动） | 高——我方目前完全没有邻居约束概念 |
| `constrainCueRangeToTrack` (:485) | 主轨"夹在邻居缝隙里"：缝隙 < 最小时长则 blocked 拒动，否则 clamp + 缝内平移 | 高——主轨不可重叠的守卫 |
| `clampExtensionRange` (:229) | 全局 [0, duration] 夹取 + 最小时长 + 整毫秒 round | 直接对照现有 clampTime |
| `extensionRangeOverlapsNeighbors` (:275) | O(n) 相交检测，副轨禁止重叠 | 高 |
| `resolveExtensionFollowerRange` + `reconcileExtensionTrack` (:362-483) | **副轨策略与主轨相反：允许挤压/删除而非阻塞**。主段变更后，被穿越的副段保留未覆盖的最长一侧，不足最小时长则删除并解绑；绝不反向修改主轨；返回 squeezed/removed/unbound 计数供 UI 提示 | 最高——这是绑定联动的灵魂 |
| `syncBoundExtensionForMain` (:512) | 主→副 delta 跟随：move 整体平移、trim 单边跟随，再交 reconcile 消解 | 最高 |
| `constrainBoundExtensionPanelEdit` (:544) | 副→主限制：拖副段的 delta 反推主轨范围过约束后再映射回来 | 高 |

配套交互语义：联动拆分共用一个绝对切点、整次拆分一条原子撤销（editor.js:7170）；绑定对删除默认成对；Alt = 临时反转吸附 / 副轨独立拖动不联动（waveform.js:4157、:4920）；跨轨吸附目标经 options 回调从 editor 层注入 waveform 层，两层解耦。

**移植方式**：这套函数与 DOM 零耦合，可逐个翻译为 TS 纯函数放 `frontend/src/utils/trackConstraints.ts`（建议命名），vitest 逐函数覆盖——MAW 自己也是把它们抽到 editor-utils.js 来保可测性的。

### 1.3 历史模型：单一栈 + kind 化快照 + id 选择快照

- 一个 undo 栈管四类记录（segments/layout/gap_remove/preview），`pushUndo` 把主轨与 multi_subtitle 打进**同一份快照**——绑定/成对删除/联动拆分因此天然原子（editor.js:912-916 注释明示此意图）。
- 布局撤销（`pushLayoutUndo`）：divider 拖动先取 snapshot、**首次变化才入栈**，一次拖动只产生一条记录；行布局快照存 split 百分比/rows/settings。
- 选择恢复基于 id 而非下标（`restoreEditorSelection`），容忍重排。
- **我方对照**：M5 分层撤销（undoRecords.captureLayers）已是"层快照 + 后端 apply_undo 拥有 revision"的更优形态，**不必改架构**；要补的只是：① 联动编辑必须把 segments 与 bindings/tracks 层打进同一条快照（captureLayers 多层捕获已支持，白名单加层即可）；② 3.0.1 新增的"时间线布局状态"（lane 高度/折叠/显隐）可作为一个纯前端 layout 层，不入后端 revision。

### 1.4 gaps = 投影，导出期映射

- `gap-remove-core.js`（框架无关 IIFE）维护 removed 区间；导出时 `buildGapRemovedIntervals` 求补集得保留区间 → FFconcat 无损切片 + keep-regions JSON + **`buildGapRemovedDynamicSegments` 把每条字幕（主轨和副轨同一 removed 集）平移压缩到去空隙时间轴**（editor.js:11190-11260）。工程内绝对时间永不改动。
- **对我方的意义**：这正面回答了 v2 报告遗留的"剪辑区副字幕残留"问题——副轨导出映射与主轨共用同一 keep-ranges，实现放 `export_service` 一处。我们比 MAW 更该做对这一点：我们有 EditDecision 真源，副轨映射可以从 decisions 推导而非独立维护 gaps。

### 1.5 渲染性能策略（借鉴策略，不搬实现）

- **行级 canvas 虚拟化**：每行一个 canvas，视口缓冲 2 行滚动回收，segment 块是 DOM 百分比定位元素而非 canvas 绘制（waveform.js:2710、:2866）。
- rAF 合帧（`scheduleRender`）；**布局拖拽期不重绘、只 CSS 拉伸既有位图，松手后再高质量重绘**（:2699-2703）——廉价连续反馈 + 高质量终帧。
- hover seek 预览每帧最多消费一次事件（:1579-1609），天然丢帧。
- **我方对照**：M6-1/2/3 已实现 rAF 合帧、命令式播放头、hover 预览，单 canvas 方案在单轨下够用。3.0.1 多 lane 后单 canvas 需拆为**每 lane 一个 canvas**（与 MAW 行级 canvas 同构），但无需引入其虚拟行回收——我们的 lane 数量是 <5 的量级，不是 MAW 千行波形的量级。

### 1.6 布局形态与 CSS 契约

- MAW 用**同一行内 CSS 变量切双 lane**（`--multi-subtitle-lane-height`，主轨在上副轨在底，dotted outline + 10% 色底区分，轨道徽标 1/2），`trackAtPoint` 用几何计算而非 DOM 命中判定 lane（waveform.js:3646-3660）。
- 这是两轨特化解法。我方若支持 N 轨，应直接用 JS 计算 lane top/height（grid 或绝对定位），lane 几何由一个 `useLaneLayout` composable 单点管理。
- DESIGN.md:166-197 的 stacking context 四条规则（fixed 弹层被封印在 sticky 祖先的层级内，解法是提升 owner 而非提升弹层，同一坑连踩三次后固化）——我方 M9 已建层级契约，应把"提升 owner"这条规则补进 docs/design-spec.md。

---

## 二、Milo-Cut 3.0.0 时间线现状（摸清家底）

| 维度 | 现状 | 对 3.0.1 的意义 |
|---|---|---|
| 时间线形态 | 两个分离表面：`Timeline.vue`（虚拟滚动列表，非时间轴）+ `WaveformEditor.vue`（真时间轴，DOM 分层 z0-z10） | 堆叠区挂在 WaveformEditor 一侧；列表不动 |
| 副轨 | M11-2：数据层完整（SubtitleTrack/TrackBinding/patch 双 layer/撤销层捕获/300ms 导入绑定），UI 仅只读折叠文本列表 TrackLane.vue（64 行，无几何渲染无编辑面） | **3.0.1 的主战场** |
| Segment 几何编辑 | trim 拖拽（16px 命中区、0.1s 最小段长、0.01s snap、300ms 防抖乐观更新）硬编码在 SegmentBlocksLayer.vue:123-220；拆分/合并走后端；**无邻居约束、无重叠检测** | 需按 track 参数化 + 引入 1.2 约束函数族 |
| 波形 | 单 canvas、后端峰值 JSON（M11-3 sidecar）、M6-1 rAF 合帧 + 按需重置位图 | 拆每-lane canvas，复用现有 scheduler |
| zoom/pan/播放头 | useTimelineMetrics 唯一几何中枢（provide/inject）；M6-3 双域时钟，播放中 Vue 补丁为 0 | **基本零改动直接复用**——metrics 与轨道无关，这是 3.0.0 架构的红利 |
| patch/撤销 | segments 层 in-place merge（M7-1）；**tracks/bindings 层仍是整体替换**（projectPatch.ts:139-150）；M5 分层撤销 revision 永不回退 | tracks 层细粒度化是 3.0.1 最高风险点 |
| 持久化 | project.json 已含 tracks/bindings，无迁移需求 | 无 |

---

## 三、差距分析：从"只读副轨"到"堆叠时间线"

按用户可感知能力逐项列差（MAW 能力 → 我方现状）：

1. **副轨几何可见**：MAW 副轨段以块渲染在时间轴上、与主轨同缩放 → 我方仅文本列表，无法目视对齐。
2. **副轨编辑**：MAW 支持副轨拖动/trim/拆分，且与主轨约束联动 → 我方副轨零编辑面。
3. **绑定联动**：MAW 主段移动时副段跟随（offset 派生 + reconcile 消解）、成对删除、联动拆分 → 我方 bindings 只写不消费，任何主轨编辑都会静默漂移绑定。
4. **邻居/重叠约束**：MAW 全轨约束函数族 → 我方主轨自己都没有邻居约束（拖拽可造成视觉重叠，靠后端排序不变量兜底）。
5. **堆叠布局管理**：MAW lane 开关/行高预设 → 我方无。
6. **去空隙导出对副轨的映射**：MAW 同一 removed 集映射所有轨 → 我方导出管线尚不含副轨。

---

## 四、v3.0.1 实施方案

### 4.1 范围裁决

**做**：堆叠渲染（主轨 + 全部副轨 lane）、副轨几何编辑（移动/trim/拆分）、绑定联动（跟随 + 成对删除 + 联动拆分）、约束函数族、tracks/bindings patch 细粒度化、副轨删除区间导出映射、lane 布局状态（前端层）。
**不做**（沿承 v2 报告并复核成立）：一对多绑定、主副轨交换、轨道重排序、翻译管线、音频轨道堆叠、MAW 式行级 canvas 虚拟回收。轨数上限建议 MVP 定为每 Timeline ≤ 4 条副轨（UI 提示即可，不硬限），`trackId` 从第一天贯穿所有 API——这是 MAW 明确的欠账（`getActiveExtensionTrack` 全局唯一），我们不重复。

### 4.2 分批计划

**P0 约束内核（纯函数，无 UI，先行合入）**
1. `utils/trackConstraints.ts`：移植 1.2 全表函数族（TS 化 + 边界用例 vitest 覆盖；最小时长/snap 常量与主轨现值对齐：0.1s/0.01s）。
2. 后端 `project_service` 对 update_segment 增加同轨重叠拒绝（此前靠约定，现在显式化）。

**P1 堆叠渲染（只读几何化）**
3. `TrackLane.vue` 重写为几何轨道：复用 useTimelineMetrics percent 定位渲染块，支持折叠/显隐/高度档位；lane 几何由 `useLaneLayout` 统一计算。
4. WaveformEditor 引入堆叠编排：主轨（波形+blocks）+ N lane 垂直堆叠共享 metrics 与单条 PlayheadOverlay（跨 lane 贯穿）；波形 canvas 按需拆为每 lane 一个（复用 createRafScheduler）。
5. SegmentBlocksLayer 抽出通用 `SegmentBlock`（渲染 + trim 交互按 track 参数化），主副轨共用。

**P2 副轨编辑与联动（核心增量，最高风险批）**
6. tracks/bindings patch 细粒度化：仿 segments in-place merge（projectPatch.ts 按 trackId + segmentId 原位替换），否则联动拖拽的 patch 流量是 O(全部副轨段)。
7. 绑定联动消费：主轨 move/trim → offset 跟随 + reconcile（squeezed/removed/unbound 计数 toast 提示）；成对删除；联动拆分（单切点、原子撤销——captureLayers 一次捕获 segments+tracks+bindings 三层）。
8. Alt 语义：临时反转吸附 / 副轨独立拖动（不联动）。

**P3 导出与收尾**
9. `export_service`：删除区间 → keep-ranges 对副轨段做时间映射，SRT/VTT 按 track 参数化导出（主副各一份，双语可合并双行）。
10. SubtitleOverlay 按 bindings+offset 渲染当前副轨字幕；竞品报告 v2 第一节标注过时声明；`docs/design-spec.md` 补层级契约"提升 owner"规则。

### 4.3 规模与风险

- 规模估计：前端 ~1500-2500 行（TrackLane 重写 + SegmentBlock 泛化 + 堆叠编排 + 约束函数 + patch 细粒度化），后端 ~300-500 行（联动编辑 + 重叠拒绝 + 导出映射）。量级与 3.0.0 的 M11 单项相当，明显小于 M6/M7。
- 风险 1（最高）：tracks/bindings patch 细粒度化若不做，P2 上线即卡（拖拽 patch 风暴 + v-memo 失效全列表重渲染）。**必须在 P2 第一步完成并加性能断言测试**。
- 风险 2：联动编辑与 M5 撤销的原子性——联动拆分必须单条快照覆盖三层；undo 走 apply_undo 保持 revision 单调，无 stale 风险但需集成测试。
- 风险 3：副轨 reconcile 的"挤压/删除副段"是破坏性操作，必须有 undo 快照 + UI 计数提示，默认策略与 MAW 一致（保护目标段、绝不反向改主轨）。
- 风险 4：maOS/WKWebView 下堆叠区 pointer 事件的 wheel deltaMode 归一（v2 报告已提的已知坑，堆叠区交互密度更高，勿再踩）。

---

## 五、一句话结论

MAW 用 1.7 万行原生 JS 证明了一件我们用 3.0.0 已铺好数据地基的事：堆叠时间线的难点不在画布，而在**约束内核的纯函数化**（邻居/重叠/联动/reconcile）与**绑定 offset 的派生式重建**；v3.0.1 把这两块移植进我们现成的 metrics/patch/分层撤销基建，就能以约 3.0.0 单个里程碑的代价，补齐这条与竞品最大的结构性差距——并且从第一天就是 N 轨泛化、trackId 贯穿的形态，不背 MAW 的单副轨 MVP 欠账。

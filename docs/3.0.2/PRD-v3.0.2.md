# Milo-Cut v3.0.2 需求文档（PRD）

> 版本：3.0.2（PRD Draft）
> 主题：**多行时间线（Multi-Row Timeline）** —— 同一条时间轴按时间分行续接、垂直堆叠同时显示
> 基线：v3.0.1（堆叠时间线，2026-09-01 发布）
> 日期：2026-09
> 依据：[3.0.2-开发报告](./3.0.2-开发报告.md)（MAW 源码逐行深查 + 我方 3.0.1 现状二次核验，全部结论附行号证据）
> 角色：产品经理

---

## 0. 版本定位

v3.0.2 的主题只有一个：**多行时间线**。主轨时间轴按 `secondsPerRow`（每行秒数）切成连续的行，垂直堆叠在同一滚动表面上同时显示——在不缩小缩放级别（字幕块仍可读）的前提下，一屏同时看到更多字幕、覆盖更宽的时间范围，不用来回横向平移或把 zoom 压到不可读。

### 0.1 需求语义定式（三轮澄清的最终锚定，后续文档不得再跑偏）

> **同一条时间线，按时间先后切成若干「行（row）」，垂直堆叠、同时显示。**
> 行 1 显示 0:00–0:10，行 2 紧接 0:10–0:20……播放头随播放进度在行间换行推进，浏览沿行竖向滚动。

明确排除的相邻概念：

| 概念 | 含义 | 与本版关系 |
|---|---|---|
| ~~多层字幕~~ | 主轨 + N 副轨字幕堆叠与绑定联动 | v3.0.1 已交付；本版仅修其收口缺陷（§1），不改语义 |
| ~~多版本时间线~~ | project.timelines 多份 fork 切换对比 | 无关 |
| **多行时间线** | 时间轴自身的分行续接显示 | **本版主题** |

与 v3.0.1 堆叠时间线的关系：**正交组合**。v3.0.1 解决「主轨与副轨在同一时间窗内垂直堆叠」；v3.0.2 解决「同一时间轴切成连续多行、扩大同屏时间覆盖」。组合后的完整形态 = MAW 的「每个时间行内部主/副 lane，行序列垂直续接」排版（waveform.css:516-574 的 `multi-subtitle-row` 形态）。

### 0.2 与 v3.0.1 的关系：先收口，再多行化

开发报告深查发现 v3.0.1 有三处「文档已勾销但代码未闭环」的正确性缺陷（报告 §2.5，三项关键指控均经二次核验）：

1. **副轨编辑面断链**：TrackLane.vue:14 注释自认 "read-only -- no updateTime passed"，模板 :88-98 未把 `updateTime` 下传 SegmentBlock——3.0.1 宣称的副轨 trim 在 UI 上是死的；
2. **联动 patch 丢层**：project_service.py:1342-1348 把 `_tracks, _bindings` 丢弃、只留计数进 `meta`——主轨 trim 触发消解后前端轨道状态陈旧；
3. **撤销捕获层不符 SPEC M5-1 映射表**：useSegmentEdit.ts:168 只捕获 `["segments"]`，useEdit.ts:57/:133 只捕获 `["segments","edits"]`，副轨导入无快照——联动操作 undo 回退不原子。

**裁决：P0.5 收口批必须先于多行化动工**（S1-S3）。否则多行化的行级 trim/拖拽会建立在断链与丢层的地基上。

### 0.3 核心判断（来自竞品深查）

1. **MAW 多行时间线的精华是四件套，全部是框架无关纯逻辑，可整体平移**：时间→行映射（行 i = `[i×spr, (i+1)×spr]`，滚动位置与时间互相推导）；行级虚拟化（视口 ±2 行，增量 diff）；每行播放头（仅当前播放行可见）；舒适区自动跟随（48–120px 自适应边距）。
2. **我方唯一的结构性障碍是 `useTimelineMetrics` 的单窗模型**——但 7 个时间轴子组件全部只消费注入的 metrics（已逐一核验），因此**「一行 = 一个单窗视图」**：行组件 provide 行级 metrics 适配器（viewStart = 行起点、viewDuration = 每行秒数），现有子组件栈零改动按行复用。这是 3.0.0「metrics 与轨道无关」红利的第二次兑现。
3. **缩放语义在多行模式下重定义为「每行秒数」**（Ctrl+滚轮循环档位 5/10/20/30s）——行宽恒定，字幕块文本有确定的可用宽度，可读性有下限保证。
4. MAW 已知槽点「无全局总览 mini-map」→ 我方 `ScrollbarStrip` 转型**迷你总览条**反向超越。

由此确立六条设计原则：

| # | 原则 | 含义 |
|---|---|---|
| P1 | **rows 是派生几何，不是状态** | 行数/行区间全部由 `(duration, secondsPerRow)` 派生计算，不持久化行集合；纯函数先行（P0），vitest 逐函数覆盖 |
| P2 | **一行 = 一个单窗视图** | 行级 metrics 适配器满足现有 `TimelineMetrics` 接口形状；不侵入 useTimelineMetrics 加 mode 分支 |
| P3 | **虚拟化对交互透明** | 拖拽几何快照契约：拖拽状态上提到 composable，pointerdown 冻结行几何，行重建/卸载不影响进行中的拖拽。**状态上提骨架是 WaveformRow 的架构前提（P1 落地），交互消费与专项测试在 P2 接线** |
| P4 | **bounded / unbounded 双映射** | 点击/创建/框选钳制行内；播放头 scrub、范围拖拽、**块 trim** 跨行无界——trim 的约束以**轨道邻居边界**为准（行边界不参与约束，仅参与手柄可见性与视觉裁剪），杜绝「拖到行边缘跳到下一行开头」与「trim 被行边界错误钳制」。SegmentBlocksLayer 唯一交互改动 = `emptyAreaMode` prop（multi 空点 seek / basic 空点建段，SPEC M5-3） |
| P5 | **basic 模式 = 现状超集** | 多行/聚焦（单窗）双模式同组件分派；basic 模式行为与 v3.0.1 完全一致（含连续缩放） |
| P6 | **schema 冻结 + localStorage** | 零后端 schema 变更、零迁移、零新增 bridge 事件；行设置与浏览位置只入 localStorage（对位 useLaneLayout 先例） |

### 0.4 能力差距（MAW 能力 → 我方现状 3.0.1）

| # | 能力 | MAW | 我方现状（3.0.1） |
|---|---|---|---|
| 1 | 时间分行模型 | 行 i = `[i×spr,(i+1)×spr]`，滚动↔时间互转、可持久化恢复 | 无概念（单窗 viewStart/viewDuration） |
| 2 | 同屏时间覆盖 | 5-6 行 × 10s ≈ 50-60s 可读内容，可滚至全片 | ≤600s 窗且该窗下字幕不可读——「看得多」与「看得清」零和 |
| 3 | 行级虚拟化 | 视口 ±2 行，Set-diff 增量，留存行保 canvas 不重绘 | 无（单窗全量） |
| 4 | 播放头 | 每行一个，仅当前播放行可见 | 单窗百分比（贯穿堆叠区） |
| 5 | 缩放语义 | Ctrl+滚轮 = 每行秒数档位 | Ctrl+滚轮 = 连续窗长因子 |
| 6 | 自动跟随 | 舒适区（48-120px）+ 换行才判定 + 35%/45% 双偏置 + 3s 手动冷却 | 出窗即居中（200ms 节流） |
| 7 | 行高/每行秒数控件 | 设置 select + 手势（Ctrl+Shift+滚轮行高） | 无 |
| 8 | 总览定位 | 无（槽点） | 水平滚动条（multi 模式下需转型） |
| 9 | 单行/多行模式切换 | mode 开关，cinema 预设用 basic | 无 |

### 0.5 范围裁决

**做**：

- P0.5 收口批：3.0.1 三缺陷修复 + `export_track_srt` 废弃包装删除 + `useTrackEdit.test.ts` 补齐（§1）
- 多行渲染：分行续接、垂直堆叠、行级虚拟化（§3）
- 每行播放头 + 舒适区跟随 + 手势系统 + 单行/多行模式切换（§3/§4）
- 行设置与浏览位置持久化（localStorage）（§4）
- 底部时间线区高度可调 + 控件栏 + 迷你总览条（§5）
- 副轨 lanes 每行组合（P3 批，MAW `multi-subtitle-row` 形态）（§5）
- 行首时间徽章、跨行字幕延续标记、行内边缘 trim 手柄规则（§3）

**不做**（沿承开发报告裁决）：

- MAW 的 layoutTree 工作区模块拖拽系统与四套布局预设（取信息架构结论，不搬实现）
- 波形 mipmap / 多分辨率峰值（维持 v2 报告 L 级后置）；后端峰值 sidecar 零改动
- Shift+滚轮波形振幅缩放（无 waveformScale 概念，价值低，后置）
- 数据 schema / ProjectPatch / 撤销协议变更（除 S2/S3 的既有协议对齐修复外，零变更）
- `Timeline.vue` 字幕列表改造（右列列表不动）
- MAW 式手工 DOM 行保留优化（Vue keyed v-for 回收已覆盖 MVP；性能不达标时的后手）
- MAW「工作区随工程走」（波形设置入 project.json）——schema 冻结红线，记入后续版本池

**MVP 约束**：每行秒数预设 `[5, 10, 20, 30]`（默认 10s）；行高预设 `[64, 80, 96, 120, 144, 168]`（默认 120px，与现主轨 112px 同量级、留双行文本空间）；多行模式不设最大行数（**渲染/滚动成本与总行数无关**——虚拟化保证，行数本身 = ceil(duration/spr) 随时长线性增长）。

### 0.6 顺带项裁决（开发报告 §3.4 借鉴表的显式决定）

| 项 | 裁决 | 落点 |
|---|---|---|
| 右键菜单项带 kbd 快捷键角标（菜单即速查表） | **3.0.2 做**（成本低，随行/块右键菜单改动顺带） | S9.4 |
| toast 栈语义四色 + 上限 3 条 + 高频冷却 | **3.0.2 做**（useToast 已有，对齐上限与冷却策略） | S9.5 |
| 桥断连持久警示 banner / 点击行为三模式 / 撤销恢复选区视图 | 后置版本池 | 开发报告 §3.4 表 |

---

## 1. P0.5 批：3.0.1 一致性收口（先行合入，不单独发布）

### S1. 副轨编辑激活（断链修复）

**现状缺陷**：TrackLane.vue 未把 `updateTime` 下传 SegmentBlock（组件注释自认 read-only），链路 WorkspacePage→WaveformEditor→TrackLane 最后一跳断——SegmentBlock 的 trim 逻辑、`useTrackEdit`（乐观/防抖/回滚）、`update_track_segment` expose 全部就绪但无生产入口。

**需求**：

- R1.1 TrackLane 把 `updateTime` prop 下传 SegmentBlock 的 `update-time`（v3.0.1 M5-2 预留语义：when provided, extension blocks become trim-editable）
- R1.2 副轨 trim 生效：乐观更新 → 300ms 防抖 → `update_track_segment` → 失败回滚（useTrackEdit 既有链路，零新逻辑）
- R1.3 新建 `useTrackEdit.test.ts`：乐观更新、防抖合并（同段同字段去抖）、失败回滚、捕获层（有绑定 `["tracks","bindings"]` / 无绑定 `["tracks"]`）——补上 v3.0.1 plan 勾销但缺失的测试文件
- R1.4 TrackLane/SegmentBlock 既有测试更新：`updateTime` 下传后，TrackLane 8 例与 SegmentBlock 12 例中的只读断言（trim 禁用分支）需适配为「传入 updateTime 时可编辑/未传入时禁用」双路径

**验收**：vitest 新用例全绿；手工冒烟——副轨段可拖 trim、有邻居约束（blocked 拒动）、防抖提交无回跳。

### S2. 联动一致性（patch 带层）

**现状缺陷**：`update_segment` 联动路径（project_service.py:1342-1348）把消解后的 tracks/bindings 丢弃，patch 只含 segments + `meta.linkage` 计数——违背 v3.0.1 SPEC M2-1 第 5 步，前端轨道状态陈旧直至其他操作带回层。

**需求**：

- R2.1 `update_segment` 联动发生时，patch 携带 `tracks` + `bindings` 层（消解后全量数组）+ `meta.linkage` 计数（不变）
- R2.2 pytest 契约锚定：联动路径返回的 patch 含三层（segments/tracks/bindings）+ meta；无联动路径不变（仅 segments）
- R2.3 前端零改动验证：现有 `mergeTracksInPlace`/`mergeBindingsInPlace` 应用新层后，副段挤压/删除即时反映

**验收**：pytest 新用例全绿；手工冒烟——主轨 trim 挤压副段后，副轨 lane 即时显示消解结果（无需其他操作触发）。

### S3. 撤销捕获层对齐 + 清理

**现状缺陷**：四个真实调用点的 undo 捕获层不符 v3.0.1 SPEC M5-1 映射表——联动操作回退不原子。

**需求**：

- R3.1 `useSegmentEdit.updateSegmentTime`：**精确谓词——目标段存在绑定**时捕获 `["segments","tracks","bindings"]`（后端联动仅在此时触发），否则维持 `["segments"]`
- R3.2 `useEdit` 的拆分与成对删除：**操作涉及段存在绑定**（拆分目标段有绑定 / 删除触发成对级联）时捕获 `["segments","edits","tracks","bindings"]`，否则维持现状
- R3.3 副轨 SRT 导入（useWorkspaceActions）提交前 `pushSnapshot(["tracks","bindings"])`（导入必然产生两层，无条件捕获）
- R3.4 集成测试：经**真实调用点**（非手工构造）触发联动 trim → undo → 三层同时回退且无 stale patch；redo 对称；断言口径与 R3.1/R3.2 谓词一致（无绑定路径捕获层数不变）
- R3.5 删除 `export_track_srt` 废弃包装（export_service.py:384-396，注释明示 "remove in v3.0.2"）；**同步清理**：`tests/test_track_export.py`（:9/:83 引用与调用）与 `docs/PROJECT_SCHEMA.md:68`（副轨导出路径文档改为 `export_track_subtitle`）——main.py 无引用（已核实，桥接走 export_track_subtitle）

**验收**：pytest/vitest 全绿；`grep -r export_track_srt core/ tests/` 无残留（docs/3.0.1 历史记录不回改）。

---

## 2. P0 批：行几何内核（纯函数，无 UI，先行合入）

### S4. `useRowLayout` 纯逻辑层

**需求**：新 composable `frontend/src/composables/useRowLayout.ts`，核心为纯函数（模块纪律：禁止 import Vue 组件/bridge；可被 vitest 独立实例化）：

- R4.1 **行映射**：`rowCount = max(1, ceil(duration / secondsPerRow))`；`rowSpan(i) = { start: i×spr, end: min(duration, (i+1)×spr) }`；末行宽度百分比 = 剩余时长 / spr
- R4.2 **虚拟窗**：`visibleRows(scrollTop, viewportHeight, rowHeight) → { first, last }`，缓冲 `ROW_BUFFER = 2` 行；`stride = rowHeight + ROW_GAP`（`ROW_GAP = 10`）
- R4.3 **滚动↔时间互转**：`scrollTopToTime(scrollTop) = floor(scrollTop / stride) × spr`；`timeToScrollTop(time)` 反向且**量化到行边界**（恢复浏览位置用）
- R4.4 **舒适区**：`isRowInComfortZone(rowIndex, scrollTop, viewportHeight, rowHeight)`，`comfortInset = clamp(viewportHeight × 0.2, 48, 120)` px；跟随偏置常量 `FOLLOW_BIAS = 0.35`、`REVEAL_BIAS = 0.45`；`MANUAL_FOLLOW_COOLDOWN_MS = 3000`
- R4.5 **双映射**：`timeFromPointerInRow(rect, rowSpan, clientX, { bounded: true })`（ratio clamp 0-1）与 `bounded: false`（不钳，调用方再 clamp 到 [0, duration]）
- R4.6 **常量单一真源**：`SECONDS_PER_ROW_PRESETS = [5,10,20,30]`、`ROW_HEIGHT_PRESETS = [64,80,96,120,144,168]`、上述常量——全部从本模块导出，组件层禁止复制魔数
- R4.7 vitest 逐函数边界覆盖：空时长/单行/末行不足整行/scrollTop 恰在行边界/视口小于一行/恢复量化往返/舒适区三路径（上边距/下边距/内）/bounded 边界（拖出行首行尾）——**移植 MAW test_waveform_js.mjs 既有用例**（comfort zone :283-289 等）

**验收**：vitest 全绿；模块纯性测试（import 无 vue/bridge）。

---

## 3. P1 批：多行渲染（只读几何化）→ `v3.0.2-beta.1`

### S5. WaveformRow 组件与编排改造

**需求**：

- R5.1 新组件 `WaveformRow.vue`：内部构造**行级 metrics 适配器**（满足 `TimelineMetrics` 接口形状：`viewStart = i×spr`、`viewDuration = spr`；follow/zoom watcher 禁用）并 provide；组合现有 `WaveformCanvas` / `TimeMarksLayer` / `SegmentBlocksLayer`（零改动复用）
- R5.2 `WaveformEditor.vue` 编排改造：multi 模式下渲染滚动容器（内容高 = `rowCount × stride − ROW_GAP`）+ `v-for visibleRows`（keyed by rowIndex，视口 ±2 行）；basic 模式分支**原样保留现状渲染路径**（含 ScrollbarStrip 连续缩放）
- R5.3 行级播放头：每行渲染条件 `currentTime ∈ [rowStart, rowEnd)`，行内百分比定位；**块 active 高亮与行级播放头共享同一 usePlaybackClock 时间源**；编排层不再渲染全局 PlayheadOverlay（basic 保留）
- R5.4 行视觉：行首时间徽章（`行起始 → 行结束`，mono 11px）；刻度间隔按每行秒数自适应（复用 `NICE_STEPS`：5s 行 → 1s tick，30s 行 → 5s tick）；跨行字幕块裁剪渲染两份 + `continues-from/to` 类 + 相接侧去圆角；trim 手柄只在行内边缘渲染（`segment.start >= rowStart` 才有左柄）
- R5.5 行字幕切片：维持 SegmentBlocksLayer 现状 O(S) 过滤（可视行数 ≤ 视口+4，千段工程 ≈1.4 万次比较 <1ms；行级 trim 邻居约束本就需全轨数组）；`firstCueIndexOverlapping` 二分列为热点优化预案（SPEC M4-4 裁决）
- R5.6 虚拟化：滚动事件 rAF 合帧后重算 visibleRows；留存行不重挂载（keyed 复用）；字幕块增删/选中刷新只动块 DOM 不重绘行 canvas
- R5.7 **拖拽几何快照架构前提（P3 原则落地骨架）**：行相关交互状态（拖拽中几何、指针换算基准）归属**编排层 composable 而非 WaveformRow 组件实例**——WaveformRow 自身不持有跨指针事件状态；P2 的 S7 交互在此骨架上接线（届时零架构返工）
- R5.8 hover 预览线归属裁决：multi 模式下 hover 指示线与时间标签**仅在指针所在行渲染**（行级元素）；basic 模式保持现状全局单线

**验收**：4 副轨 + 千段主轨项目下行滚动/播放帧率不回退（对照 3.0.1 perf-baseline）；播放头只在当前行显示且换行推进；跨行字幕视觉连续；（`PLAYBACK_CLOCK_KEY` 由 WorkspacePage provide，行组件经祖先链共享——编排层勿重复 provide）。

### S6. peaks 共享与包络记忆化

**需求**：

- R6.1 peaks 加载提升到 WaveformEditor 编排层（单次 fetch + 解码），行组件注入只读——杜绝 N 行 N 次 fetch
- R6.2 行波形包络按 `{rowIndex, widthPx, dpr, scale}` 记忆化（同几何重复绘制零重算）；dpr cap 2
- R6.3 后端波形 sidecar 契约零改动（M11-3）

**验收**：网络面板确认波形 JSON 单次加载；同几何重绘无包络重算（性能断言测试）。

---

## 4. P2 批：交互与手势 → `v3.0.2-beta.2`

### S7. 手势系统与行内交互

**需求**（映射表见开发报告 §3.3）：

- R7.1 **wheel 家族**：普通滚轮 = 原生竖向滚行（deltaMode 归一沿用既有方案）；Ctrl/Cmd+滚轮 = 循环每行秒数档（重排后播放行锚定视口）；Ctrl/Cmd+Shift+滚轮 = 循环行高档（160ms debounce 合并）；basic 模式保留现状（Ctrl+滚轮连续缩放/普通滚轮平移）
- R7.2 行内点击空白：清选 + seek（bounded 映射）；按住拖动 = scrub 播放头（unbounded + 全媒体 clamp + **32ms 节流** seek、松手补一次精确 seek，拖拽期间抑制字幕列表跟随）
- R7.3 双击行内空白 = 播放/暂停；双击字幕块 = 编辑（现状语义）
- R7.4 行内 Ctrl+拖空白 = 按范围新建字幕（占用检查，预览遇已有段停边界）——现有 add-segment 交互按行参数化；vitest 覆盖占用拒绝与预览边界停止
- R7.5 Shift+拖空白 = 跨行框选（选框挂内容容器坐标系，对全部可视行矩形相交）——与现有多选模式衔接；vitest 覆盖跨两行的块命中
- R7.6 **拖拽几何快照接线**：在 S5.7 架构骨架上实现 pointerdown 冻结 `{rowLeft, rowWidth, rowStart, rowSpan}`；行卸载/重建不影响进行中拖拽（专项测试：拖拽中强制滚动触发行回收，拖拽继续有效）
- R7.7 Alt 语义（SPEC M5-4 矩阵回写）：**收敛为「反转 snap」唯一语义**（现状既有，保留）；「Alt = 副轨独立拖动」裁决不做——副轨编辑本就从不反改主轨（主轨保护红线），MAW Alt-independent 解决的问题在我方数据模型中不存在；主轨「Alt 跳过联动」违反 v3.0.1 SPEC M2-1「不提供跳过联动的通道」裁决且需后端变更
- R7.8 **多行模式块 trim**：块 trim 拖拽用 unbounded 映射，时间约束以**轨道邻居边界**（clampTime 语义，SPEC 裁决抽为 trackConstraints 导出）为准，**行边界不参与约束**（只参与手柄可见性与视觉裁剪，R5.4）；跨行段在两行各渲染手柄但约束连续；主轨/副轨 trim 均适用；Alt 仅反转 snap（R7.7 矩阵）

**验收**：双平台真机——滚轮/触控板手势全表、行内点击/拖拽 seek 数学正确、跨行拖播放头无跳变、拖拽中滚动不丢状态；vitest——占用检查（R7.4）、跨行框选（R7.5）、快照契约（R7.6）、多行 trim 约束（R7.8：trim 到行边界外不被钳制、被邻居钳制）。

### S8. 跟随、模式切换与持久化

**需求**：

- R8.1 **跟随三分**：手动滚动（`manualFollowUntil = now + 3000`，程序化滚动不打断）/ 播放跟随（换行才判定，35% 偏置，`autoScrollTarget` 回环抑制）/ 跳转 revealTime（45% 偏置 + 舒适区免滚 + 目标行在视口内只动播放头不重建）
- R8.2 模式切换（多行/聚焦）：控件栏 segmented 按钮；切换重置虚拟窗与跟随状态；basic 切回时以当前时间居中
- R8.3 设置持久化：localStorage key `milocut:timeline-rows:v1`，存 `{ mode, secondsPerRow, rowHeight, scrollTopTime }`（损坏 JSON 回退默认）；**浏览位置恢复经量化到行边界**；不产生 patch、不入 undo、不进 project.json（P6 红线）
- R8.4 **迷你总览条**：multi 模式下 ScrollbarStrip 转型——渲染全片缩略（视口覆盖区间 + 播放头位置），点击/拖拽跳转到对应行（scrollTop 写入经行对齐）；basic 模式保留现状语义

**验收**：设置 round-trip 测试；重开工程恢复浏览位置（行对齐）；总览条跳转正确；播放跟随在 3s 手动冷却内不抢滚动。

---

## 5. P3 批：排版与组合 → `v3.0.2-RC → 正式`

### S9. 底部时间线区排版

**需求**：

- R9.1 底部区高度用户可调（拖拽 divider，记忆 localStorage，round-trip 测试）；multi 模式默认给到视口高 40-50%
- R9.2 控件栏信息架构：左「Regen + 模式切换」、中「视口覆盖时间范围（如 12:00–12:50 / 全片 58:30）」、右「每行秒数 + 行高 select」
- R9.3 工作区其余骨架（顶栏/左视频/右字幕列表）不动
- R9.4 右键菜单项带 kbd 快捷键角标（§0.6 顺带项：涉及行/块右键菜单改动时一并落地）
- R9.5 toast 栈对齐语义策略（§0.6 顺带项：上限 3 条、高频事件冷却，useToast 既有机制上调参数）

**验收**：高度调整流畅无布局抖动且 round-trip 测试通过；控件栏状态与实际视口一致；右键菜单项标注快捷键。

### S10. 副轨每行组合 + 文档收尾

**需求**：

- R10.1 存在副轨时，每个时间行内部组合主 lane + 副轨 lanes（useLaneLayout 每行实例化；MAW `multi-subtitle-row` 形态）：行高预设联动上调（副轨存在时默认切 168 档），副轨 lane 高度压缩（35px 档）
- R10.2 文档：README 功能说明、docs/design-spec.md 增补多行时间线交互规范（手势表/跟随语义/双映射）、开发报告补「版本池」注记
- R10.3 性能基线对账：**开工批（Phase 0）采集 3.0.1 现状基线**落盘 `docs/3.0.2/perf-baseline.md`（本版新增产物），P3 末回填对账

**验收**：双语工程（主 + 副轨）多行显示正常、副轨 trim 在行内可用；文档链完整。

---

## 6. 交付计划与依赖

```
P0.5（~2-3 天）  S1 S2 S3     —— 3.0.1 收口，先行合入不发布
P0（~1 天）      S4           —— 行几何内核纯函数 + vitest
P1（~1 周）      S5 S6        —— 多行渲染只读几何化 + 拖拽状态上提骨架 → 3.0.2-beta.1
P2（~1 周）      S7 S8        —— 手势/跟随/模式/持久化/总览       → 3.0.2-beta.2
P3（~1 周）      S9 S10       —— 排版/副轨组合/文档/性能          → 3.0.2-RC → 正式
```

**批次裁决记录**：拖拽几何快照契约按开发报告归位 P1（S5.7 架构骨架——WaveformRow 状态归属设计），交互消费与专项测试在 P2（S7.6）接线；P1 为只读批无拖拽可保护，但骨架先行避免 P2 架构返工。

**规模估计**：前端 ~1500-2400 行，后端仅 P0.5 约 100-200 行；总量与 v3.0.1 相当。

### 依赖与风险（摘自开发报告 §3.6，PLAN 展开缓解步骤）

| 风险 | 等级 | 关键缓解 |
|---|---|---|
| 虚拟行重建 × 进行中拖拽（状态留在组件实例即丢） | 高 | S5.7 架构骨架（P1 落地）+ S7.6 接线与专项测试（P2） |
| bounded/unbounded 混淆 → 行边缘时间跳变 / trim 被行边界误钳 | 高 | S4.5 双映射显式 API + S7.8 trim 约束裁决 + 专项测试 |
| 行级 metrics 多实例 watcher 打架 | 高 | S5.1 适配器禁用 follow/zoom |
| peaks 重复 fetch | 高 | S6.1 编排层单次加载共享 |
| 行挂载/卸载的 canvas 重绘成本（滚动时连续 mount） | 中 | rAF 合帧 + 160ms debounce + 视口 ±2 缓冲 + keyed 回收 + 包络记忆化（S6.2）+ 覆盖层刷新保 canvas（S5.6）；不达标后手：MAW 式手工 DOM 行保留（范围外预案） |
| 连续缩放 → 档位缩放的 UX 变化 | 中 | 文档明示 + basic 模式保留连续缩放 |
| WKWebView/WebView2 wheel deltaMode（行区手势密度高） | 中 | 既有归一层 + 双平台真机回归必测 |
| 副轨每行组合行高膨胀 | 中 | S10.1 P3 才组合 + 预设联动上调 |
| 千段项目滚动流畅度 | 中 | S5.5 二分切片 + P3 性能基线对账 |

---

## 7. 验收总纲

- **P0.5**：联动路径 patch 三层携带契约（pytest）；真实调用点三层原子 undo/redo 对称（vitest 集成）；副轨 trim UI 可用；`export_track_srt` 无残留
- **前端 vitest 全绿且新增**：行几何内核逐函数（S4）、双映射边界（S4.5）、行级播放头可见性（S5.3）、跨行裁剪与手柄规则（S5.4）、占用检查与预览边界（R7.4）、跨行框选（R7.5）、快照契约（R7.6）、多行 trim 约束（R7.8）、设置持久化 round-trip（S8.3）、高度记忆 round-trip（R9.1）、useTrackEdit（S1.3）
- **性能不回退**（对照 docs/3.0.2/perf-baseline.md——Phase 0 采集的 3.0.1 现状基线，R10.3）：千段项目滚动/播放/行重排帧率不低于基线；单行挂载重绘 p95 < 8ms；peaks 单次加载
- **门禁**：pytest ≥702 / vitest ≥453 全绿；`uv run ruff check .` 0；`bun run lint` 0；`git diff core/events.py frontend/src/utils/events.ts` 为空（零新增事件红线）；零 schema 变更（除 S2/S3 既有协议对齐外）
- **真机回归**：Windows WebView2 + macOS WKWebView——行区滚轮/触控板（deltaMode）、Ctrl+滚轮换档时播放行锚定、舒适区跟随手感、模式切换往返、跨行 trim、跨行拖播放头

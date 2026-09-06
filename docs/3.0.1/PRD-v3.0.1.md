# Milo-Cut v3.0.1 需求文档（PRD）

> 版本：3.0.1（PRD Draft）
> 主题：堆叠时间线 —— 副轨从数据概念到几何概念
> 基线：v3.0.0（内部里程碑版，不独立发布；v3.0.1 为 3.x 首个发布版本）
> 日期：2026-08（草稿）
> 依据：[v3.0.1 堆叠时间线分析](./spec-v3.0.1-堆叠时间线分析.md)（MAW 源码逐行深查 + 我方 3.0.0 现状二次核验）
> 角色：产品经理

---

## 0. 版本定位

v3.0.1 的主题只有一个：**堆叠时间线（Stacked Timeline）**。主轨与 N 条副轨字幕在同一个时间轴表面垂直堆叠、共享缩放与播放头、支持几何编辑与绑定联动。这是 MAW（`_competitor/moys-asr-workflow-main`）相对我们最重要的结构性优势，也是字幕剪辑工具的核心体验分水岭。

### 0.1 与 v3.0.0 的关系：消费挂账，而非另起炉灶

v3.0.0 M11-2 已把多轨**数据层**全部铺好：`SubtitleTrack` / `TrackBinding` 模型（`core/models.py:142-180`）、ProjectPatch 的 `tracks`/`bindings` 双 layer、分层撤销层捕获、300ms 容差副轨 SRT 导入绑定。缺的只是**渲染层与交互层**——`TrackLane.vue` 目前是一个约 70 行的只读折叠文本列表（组件注释自认 "bindings are write-only this version"）。

因此 v3.0.1 的本质是：**消费 3.0.0 挂账的 M11-2 数据层，把"轨道"从数据概念变成几何概念**。触碰面集中在前端五个模块 + 后端两处（联动编辑、副轨导出映射），**零数据迁移、零 schema 变更**。

### 0.2 核心判断（来自竞品深查）

MAW 堆叠时间线的精华不在 UI，在**"数据契约 + 约束算法 + 历史模型"三件套**——且全部是框架无关纯逻辑，可整体移植到 Vue3/Pydantic 技术栈；其 17k 行手工 DOM 渲染层恰是反面教材，不应模仿。MAW 用 1.7 万行原生 JS 证明的事，我们用 3.0.0 已铺好的数据地基来实现：难点不在画布，在**约束内核的纯函数化**（邻居/重叠/联动/reconcile）与**绑定 offset 的派生式重建**。

由此确立五条设计原则，全部后续需求据此裁决：

| # | 原则 | 含义 |
|---|---|---|
| P1 | **约束先行** | 先算约束、后写状态；全部约束逻辑为纯函数，vitest 逐函数覆盖 |
| P2 | **offset 派生式重建** | 绑定偏移在任何时间变更后整体重算，不做增量维护——避免漂移累积 |
| P3 | **主轨保护** | reconcile 绝不反向修改主轨；副轨允许挤压/删除；破坏性操作必须有撤销快照 + UI 计数提示 |
| P4 | **N 轨泛化** | `trackId` 从第一天贯穿所有新 API，不做单副轨特化（不背 MAW `getActiveExtensionTrack` 全局唯一的欠账） |
| P5 | **复用 3.0.0 基建** | useTimelineMetrics 唯一几何中枢、ProjectPatch 分层协议、M5 分层撤销、rAF 调度器——零架构改动 |

### 0.3 能力差距（MAW 能力 → 我方现状）

| # | 能力 | MAW | 我方现状（3.0.0） |
|---|---|---|---|
| 1 | 副轨几何可见 | 副轨段以块渲染在时间轴上，与主轨同缩放 | 仅文本列表，无法目视对齐 |
| 2 | 副轨编辑 | 副轨拖动/trim/拆分，与主轨约束联动 | 副轨零编辑面 |
| 3 | 绑定联动 | 主段移动副段跟随（offset 派生 + reconcile 消解）、成对删除、联动拆分 | bindings 只写不消费，主轨编辑静默漂移绑定 |
| 4 | 邻居/重叠约束 | 全轨约束函数族 | 主轨自身都无邻居约束（拖拽可视觉重叠，靠后端排序不变量兜底） |
| 5 | 堆叠布局管理 | lane 开关/行高预设 | 无 |
| 6 | 去空隙导出对副轨的映射 | 同一 removed 集映射所有轨 | 导出管线尚不含副轨（`export_track_srt` 明示不参与删除映射） |

### 0.4 范围裁决

**做**：堆叠渲染（主轨 + 全部副轨 lane）、副轨几何编辑（移动/trim/拆分）、绑定联动（跟随 + 成对删除 + 联动拆分）、约束函数族、tracks/bindings patch 细粒度化、副轨删除区间导出映射、lane 布局状态（纯前端层）。

**不做**（沿承竞品报告 v2 并复核成立）：

- 一对多绑定、主副轨交换、轨道重排序
- 翻译管线、音频轨道堆叠
- MAW 式行级 canvas 虚拟回收（我方 lane 数量是 <5 的量级，不是千行波形的量级）
- 数据迁移 / schema 变更（project.json 已含 tracks/bindings）
- UI 视觉重设计（沿用现有 token 体系）

**MVP 约束**：每 Timeline 副轨数 ≤ 4 条（UI 提示即可，不硬限）。另须纠正一项认知：竞品报告 v2 第一节"多轨字幕完全缺失"**已过时**（基于 2.3.2 现状写成），本版收尾时在该报告补注声明（S11）。

---

## 1. 约束内核（P0，第一批交付：纯函数先行，无 UI）

### S1. 前端约束函数族 `frontend/src/utils/trackConstraints.ts`

移植 MAW "先算约束、后写状态" 的几何编辑内核（editor-utils.js 已验证可测形态），逐个翻译为 TS 纯函数，与 DOM 零耦合。

**需求**：

- R1.1 `getTrackNeighborBounds`：返回同轨前驱 `end` / 后继 `start`，支持 `movedSegments` 豁免参数（多选/联动拖动时被移动段不参与边界计算）
- R1.2 `constrainCueRangeToTrack`：主轨"夹在邻居缝隙里"——缝隙 < 最小时长则返回 blocked（拒动），否则 clamp + 缝内平移
- R1.3 `clampExtensionRange`：全局 `[0, duration]` 夹取 + 最小时长 + 整毫秒 round（对齐现有 `clampTime` 语义）
- R1.4 `extensionRangeOverlapsNeighbors`：O(n) 相交检测，副轨禁止重叠
- R1.5 `resolveExtensionFollowerRange` + `reconcileExtensionTrack`：主段变更后的副轨消解——被穿越副段保留未覆盖的最长一侧，不足最小时长则删除并解绑；**绝不反向修改主轨**；返回 `{squeezed, removed, unbound}` 计数供 UI 提示
- R1.6 `syncBoundExtensionForMain`：主→副 delta 跟随——move 整体平移、trim 单边跟随，再交 reconcile 消解
- R1.7 `constrainBoundExtensionPanelEdit`：副→主限制——拖副段的 delta 反推主轨范围，过约束后再映射回来（完整移植 + vitest 覆盖；MVP 交互面**不暴露**"副→主"入口——拖副段只动副段，本函数为 P2 末备用，见 SPEC M1-4 裁决）
- R1.8 常量单一来源：最小时长 `0.1s`、snap `0.01s` 与 `SegmentBlocksLayer.vue` 现值（`MIN_SEGMENT_DURATION`/`snapToFrame`）提取为共享常量，禁止复制魔数

**验收**：vitest 逐函数边界覆盖（空轨/首尾段/最小缝隙/恰好最小时长/多选豁免/reconcile 三种计数路径）；函数族不含任何组件或 bridge 依赖（纯函数可独立实例化测试）。

### S2. 后端同轨重叠拒绝

**现状缺陷**：`project_service.update_segment`（core/project_service.py:1074）对时间变更无重叠校验，主轨不重叠仅靠 `_enforce_segment_sort_invariant` 排序兜底——视觉重叠可静默落库。

**需求**：

- R2.1 `update_segment`（主轨）对变更后与同轨邻居的时间重叠**显式拒绝**，错误信息含冲突段 id
- R2.2 新增副轨段更新通道时同步施加同轨不重叠 + 时间合法性校验；副轨 id 命名空间（`track_{track_id}_seg_*`）不可被改写

**验收**：pytest 覆盖拒绝路径（前邻/后邻/双侧夹击）与放行路径（贴合邻居边界恰好不重叠）。

---

## 2. 堆叠渲染（P1，第二批交付：只读几何化）

### S3. TrackLane 几何化重写

**现状缺陷**：`TrackLane.vue` 是 Timeline 底部的只读折叠文本列表，无几何渲染、无编辑面。

**需求**：

- R3.1 重写为几何轨道：复用 `useTimelineMetrics` 的 percent 定位渲染副轨段块，与主轨同缩放（满足差距 #1）
- R3.2 lane 支持折叠 / 显隐 / 高度档位（至少三档）
- R3.3 新增 `useLaneLayout` composable 单点管理 lane 几何（JS 计算 top/height，N 轨泛化）；不采用 MAW 的 CSS 变量两轨特化解法
- R3.4 每 lane 显示轨道名 / language / 序号徽标；副轨数超 4 条时 UI 提示（不硬限）

### S4. 堆叠编排（WaveformEditor 多 lane）

**需求**：

- R4.1 WaveformEditor 引入垂直堆叠：主轨（波形 + blocks）+ N 条副轨 lane，共享同一 `useTimelineMetrics` 与**单条** `PlayheadOverlay`（播放头跨 lane 贯穿）
- R4.2 lane 按需引入 canvas（当前无数据源——`SubtitleTrack` 不含波形峰值，不引入；主轨保持单 WaveformCanvas）；`createRafScheduler` 复用于 lane 指针交互节流；不引入行级虚拟回收
- R4.3 堆叠区挂在 WaveformEditor 一侧；`Timeline.vue` 虚拟列表不动

**验收**：4 副轨 + 千段主轨项目下，缩放/平移/播放的帧率不回退（对照 3.0.0 perf-baseline）；播放头在全部 lane 上同步贯穿。

### S5. SegmentBlock 泛化

**需求**：

- R5.1 从 `SegmentBlocksLayer.vue` 抽出通用 `SegmentBlock`（渲染 + trim 交互），主副轨共用
- R5.2 交互参数按 track 注入：命中区（16px）、最小时长、snap、防抖乐观更新（300ms）——数值同源 S1 共享常量

---

## 3. 副轨编辑与绑定联动（P2，第三批交付：核心增量，最高风险批）

### S6. tracks/bindings patch 细粒度化（P2 第一步，先行完成）

**现状缺陷**：`projectPatch.ts` 对 `tracks`/`bindings` 层是整体替换（projectPatch.ts:139-150）。若不细粒度化，联动拖拽的 patch 流量是 O(全部副轨段)，且全列表引用失效导致 v-memo 失效、全量重渲染——**P2 上线即卡**。

**需求**：

- R6.1 仿 segments 层 in-place merge（M7-1 形态）：前端 `applyProjectPatch` 按 `trackId` + `segmentId` 原位替换，未变 segment/track 引用保持稳定；后端 patch 产出同步细粒度化
- R6.2 **性能断言测试**：单副轨段移动产生的 patch 应用，重渲染范围收敛到该 lane 局部；patch 流量 O(被改段) 而非 O(全部副轨段)

### S7. 绑定联动消费

**现状缺陷**：bindings 只写不消费，任何主轨编辑都会静默漂移绑定。

**需求**：

- R7.1 联动跟随：主轨 move/trim 提交时，绑定副段经 `syncBoundExtensionForMain` + `reconcileExtensionTrack` 消解后落库。交互期约束在前端纯函数层执行（乐观更新），落库终审在后端（重叠拒绝 + offset 重建）；两端以同一份语义规格约束，后端 pytest 锚定 reconcile 规则
- R7.2 offset 派生式重建：任何被绑定时间变更后**整体重算** `start_offset`/`end_offset`（ext − main），不做增量维护
- R7.3 成对删除：删除主段默认成对删除绑定副段并解绑
- R7.4 联动拆分：主副绑定段共用同一绝对切点；整次拆分为**一条原子撤销**（captureLayers 一次捕获 segments + tracks + bindings 三层）
- R7.5 UI 计数提示：reconcile 结果（squeezed / removed / unbound）toast 呈现，破坏性消解绝不静默
- R7.6 Alt 语义：临时反转吸附；按住 Alt 拖动副轨 = 独立拖动（不联动）

### S8. 撤销原子性与布局层

**需求**：

- R8.1 M5 分层撤销白名单扩展 `tracks`/`bindings` 层；所有联动操作单条快照覆盖三层，undo 经 `apply_undo` 走 patch 通道，revision 单调递增
- R8.2 时间线布局状态（lane 高度档 / 折叠 / 显隐）作为**纯前端 layout 层**，不入后端 revision、不产生 patch
- R8.3 集成测试锁定：联动拆分 → undo → 三层同时回退且无 stale patch；redo 对称

---

## 4. 导出与收尾（P3，第四批交付）

### S9. 副轨删除区间导出映射

**现状缺陷**：`export_track_srt`（core/export_service.py:384）明示副轨"不参与确认删除的时间轴映射"，导出的是原始时间 SRT；去空隙导出后主副字幕时间轴不一致。

**需求**：

- R9.1 副轨导出接入删除区间映射：从 EditDecision 推导 keep-ranges（我们比 MAW 更该做对——有 EditDecision 真源，不需独立维护 gaps），对副轨段做与主轨**同一映射**（平移压缩到去空隙时间轴）；实现收敛在 `export_service` 一处
- R9.2 SRT/VTT 按 track 参数化导出：主副各一份；可选"双语合并"模式（主副合并为双行同条）
- R9.3 视频/音频导出行为零变化（副轨不参与媒体产物）

**验收**：pytest 覆盖——删除区间跨越副段 / 副段被完整删除 / 空删除集 / 副段骑跨两段 keep-range 的映射正确性。

### S10. SubtitleOverlay 副轨字幕

**需求**：

- R10.1 播放预览时按 bindings + offset 实时渲染当前激活副轨字幕；无绑定覆盖的时间段不显示
- R10.2 副轨字幕视觉次级于主轨（区分主副），可在设置中开关

### S11. 文档与契约收尾

- R11.1 竞品报告 v2 第一节补"多轨字幕完全缺失已过时"声明（以本 PRD 现状描述为准）
- R11.2 `docs/design-spec.md` 层级契约补 MAW DESIGN.md 固化的"提升 owner 而非提升弹层"规则（stacking context 已知坑）

---

## 5. 交付计划与依赖

```
P0（先行合入，无 UI）    S1 S2          —— 约束函数族 + 后端重叠拒绝，vitest/pytest 锚定后合入
P1（~1 周）             S3 S4 S5       —— 堆叠渲染只读几何化            → 3.0.1-beta.1
P2（~1.5 周）           S6 → S7 S8     —— patch 细粒度化必须第一步      → 3.0.1-beta.2
P3（~1 周）             S9 S10 S11     —— 导出映射 + overlay + 文档收尾 → 3.0.1-RC → 正式
```

**规模估计**：前端 ~1500-2500 行（TrackLane 重写 + SegmentBlock 泛化 + 堆叠编排 + 约束函数 + patch 细粒度化），后端 ~300-500 行（联动编辑 + 重叠拒绝 + 导出映射）。量级与 3.0.0 的 M11 单项相当，明显小于 M6/M7。

### 依赖与风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| tracks/bindings patch 不细粒度化，P2 拖拽 patch 风暴 + v-memo 失效全列表重渲染 | 最高 | S6 必须为 P2 第一步，先落性能断言测试再接联动 |
| 联动编辑与 M5 撤销的原子性（拆分跨三层） | 高 | captureLayers 单条快照覆盖三层 + apply_undo revision 单调集成测试（R8.3） |
| reconcile 的"挤压/删除副段"是破坏性操作 | 高 | 默认策略与 MAW 一致（保护目标段、绝不反向改主轨）+ undo 快照 + toast 计数提示（R1.5/R7.5） |
| macOS WKWebView 堆叠区 pointer/wheel 的 deltaMode 未归一（报告 v2 已知坑，堆叠区交互密度更高） | 中 | 堆叠区手势统一走 deltaMode 归一层；真机回归必测项 |

---

## 6. 验收总纲

- **前端 vitest 全绿且新增**：trackConstraints 逐函数边界（S1）、patch 细粒度合并与引用稳定性 + 流量断言（S6）、useLaneLayout（S3）、三层原子撤销（S8）
- **后端 pytest 全绿且新增**：同轨重叠拒绝（S2）、副轨删除区间映射与参数化导出（S9）、reconcile 落库终审（S7）
- **性能不回退**：对照 3.0.0 perf-baseline——千段 + 4 副轨项目缩放/平移/播放帧率、undo < 5ms、单段 patch 重渲染局部化
- **真机回归**：Windows WebView2 + macOS WKWebView 各一轮——堆叠区滚轮/触控板手势（deltaMode）、Alt 独立拖动、trim 手感、播放头跨 lane 贯穿
- **工程门禁**：`uv run ruff check .` 0 问题；`bun run lint` 0 errors 0 warnings；`core/events.py` 与 `frontend/src/utils/events.ts` 若有新事件保持同步

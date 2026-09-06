# v3.0.2 实施规格说明（SPEC）

> 版本：3.0.2（SPEC Draft）
> 上游：[PRD-v3.0.2](./PRD-v3.0.2.md) / [3.0.2-开发报告](./3.0.2-开发报告.md)
> 基线：v3.0.1 工作树（行号引用以撰写时为准）
> 日期：2026-09
> 本文职责：把 PRD 的 10 个特性（S1-S10）细化为**输入 / 输出 / 边界 / 验收**四段齐全的可实施契约。所有"裁决"栏为本 spec 在实施层做出的唯一性决定，与 PRD 冲突时以本文为准并需回写 PRD。

---

## 概要

### 模块划分

| 模块 | 内容 | 对应 PRD | 批次 |
|---|---|---|---|
| M0 | 全局契约：红线、常量真源、协议不变量 | 全部前置 | 全程 |
| M1 | 3.0.1 收口：副轨编辑激活 / 联动带层 / 捕获层对齐 / 清理 | S1/S2/S3 | P0.5 |
| M2 | 行几何内核 `useRowLayout`（纯函数 + 常量） | S4 | P0 |
| M3 | 行级 metrics 适配器 + WaveformRow 组件 | S5.1/R5.2-R5.5/R5.7/R5.8 | P1 |
| M4 | 编排改造：多行容器/虚拟化/行级播放头/peaks 共享 | S5/S6 | P1 |
| M5 | 手势系统：wheel 家族 / 行内交互 / 拖拽快照接线 / 多行 trim | S7 | P2 |
| M6 | 跟随/模式切换/持久化/迷你总览条 | S8 | P2 |
| M7 | 排版：高度可调/控件栏/顺带项；副轨每行组合/文档 | S9/S10 | P3 |
| M8 | 测试与门禁：用例矩阵、性能断言、真机清单 | 全部 | 全程 |

### M0: 全局契约

#### M0-1: 红线（任何模块不得违反）

1. **零后端 schema 变更、零迁移**——本版不动 `core/models.py` 任何模型字段（S2/S3 为既有协议的对齐修复，载荷走 ProjectPatch 既有层）。
2. **零新增 bridge 事件**——`core/events.py` 与 `frontend/src/utils/events.ts` 本版零改动；行设置/浏览位置走 localStorage，不产生 patch、不入 undo。
3. **`_revision` 单调**——S2 联动带层不得改变 revision 语义；undo 仍经 `apply_undo`（base_revision 校验）。
4. **行设置不进 project.json**——localStorage key `milocut:timeline-rows:v1`（M6-3），与 `milocut:timeline-layout:v1` 平级互不干涉。
5. **basic 模式零行为变化**——现状单窗渲染路径（含 ScrollbarStrip 连续缩放、`maybeFollowPlayhead` 出窗居中）原样保留为 `mode === "basic"` 分支；现有 453 前端测试不改断言全绿是硬门禁。
6. **`PLAYBACK_CLOCK_KEY` 单点 provide**——由 WorkspacePage.vue:241 提供（现状），WaveformEditor/行组件经祖先链注入，**不得重复 provide**（双时钟源漂移）。
7. **常量单一真源**——行系统全部常量从 `useRowLayout` 导出（M2-6）；`MIN_SEGMENT_DURATION`/`SNAP_STEP` 沿用 `trackConstraints.ts` 既有真源。

#### M0-2: 数据契约现状（实施前提，勿改）

- `useTimelineMetrics` 返回 `TimelineMetrics` 接口（useTimelineMetrics.ts:12-39）。**消费成员实测清单**（grep 全仓核实）：
  - **有真实消费**：`viewStart` / `viewDuration` / `viewEnd` / `timeMarks` / `minorTimeMarks` / `getTimeFromX` / `containerRef` / `duration`；
  - **仅 ScrollbarStrip 使用且含写入**（basic 模式专属）：`viewStart` 写入（:30）、`duration`、`clampViewStart`；
  - **无消费方（接口完整性成员）**：`timeToPercent` / `percentToPixels` / `playheadPercent` / `playheadVisible`——适配器仍需提供（接口形状），但语义自由度最高；
  - **watch source 使用**：PlayheadOverlay:52 与 WaveformCanvas:309/:313 以 `viewStart`/`viewDuration` 为 watch source——适配器成员必须是**真 Ref/computed**（见 M3-1）。
- 7 个消费组件（已逐一核验）：WaveformCanvas / TimeMarksLayer / SegmentBlocksLayer / SegmentBlock / PlayheadOverlay / ScrollbarStrip / TrackLane。
- 峰值数据：M11-3 sidecar JSON（`parseWaveformPeaks` 兼容裸数组与 envelope），后端零改动。
- 3.0.1 既有约束内核（trackConstraints 双侧镜像）、patch in-place merge（mergeTracksInPlace/mergeBindingsInPlace）、五层撤销——本版直接消费，不改语义。风险与回退总表见 [PRD §6](./PRD-v3.0.2.md)。

#### M0-3: 交付顺序强制

```
P0.5: M1（S1 → S2 → S3 顺序强制：激活编辑面 → 修 patch 层 → 修捕获层）
P0:   M2
P1:   M3 → M4（先适配器后编排）
P2:   M5 → M6（先交互后跟随/持久化）
P3:   M7
```

---

## M1: 3.0.1 收口（P0.5）

### M1-1: 副轨编辑激活（S1）

**改动**：`TrackLane.vue` 模板内 SegmentBlock 增 `:update-time="updateTime"`（props 已定义 `updateTime?: (segmentId, field, value) => void`，v3.0.1 M5-2 预留语义）；删除组件头注释中 "P2 batch: read-only -- no updateTime passed" 过时说明，改为记录 v3.0.2 激活。

**行为链**（零新逻辑，全部既有）：SegmentBlock trim（16px 命中区 + clampTime 邻居约束）→ `updateTrackTime` → useTrackEdit 乐观 + 300ms 防抖 + `update_track_segment` + 失败回滚。

**边界**：
- `updateTime` 为 undefined 时（外部复用 TrackLane 的场景）trim 保持禁用——SegmentBlock.vue:125 既有 `if (!props.updateTime) return` 语义不变；
- 副轨 trim 的邻居约束为 blocked 拒动（extensionRangeOverlapsNeighbors 语义），无缝内平移；
- 主轨联动：副轨 trim 不触发主轨联动（主轨保护红线，3.0.1 既定）。

**验收**：`TrackLane.test.ts` 更新——传入 updateTime 时 trim 交互可用（emit update-time）、未传入时禁用（双路径各 ≥1 例）；`SegmentBlock.test.ts` 既有 12 例中只读断言适配双路径；新建 `useTrackEdit.test.ts`（S1.3 四组用例）。

### M1-2: 联动 patch 带层（S2）

**改动**：`project_service.update_segment` 的联动分支（:1342-1348）：

```python
if linkage is not None:
    _tracks, _bindings, linkage_counters = linkage   # 现状：丢弃前两者
    patch_kwargs["meta"] = {"linkage": linkage_counters}
```

改为：

```python
if linkage is not None:
    tracks_arr, bindings_arr, linkage_counters = linkage
    patch_kwargs["tracks"] = tracks_arr
    patch_kwargs["bindings"] = bindings_arr
    patch_kwargs["meta"] = {"linkage": linkage_counters}
```

**边界**：
- `linkage` 三元组中 tracks/bindings 为消解后全量数组（`_apply_main_linkage` 返回值语义不变）；
- 无联动路径（段无绑定）patch 形状不变（仅 segments + 可能的 edits）；
- 前端零改动：`mergeTracksInPlace`/`mergeBindingsInPlace` 按 trackId/bindingId 原位应用，引用稳定（v3.0.1 P1-4 已入库待此消费）。

**验收**：`tests/test_track_linkage.py` 新增契约组——联动路径 patch 含 `segments`+`tracks`+`bindings`+`meta.linkage`；无绑定路径 patch 不含 tracks/bindings；前端 `projectPatch.test.ts` 补一条「联动 patch 应用后副段挤压可见」集成用例。

### M1-3: 捕获层对齐与清理（S3）

**捕获层映射表（本表为唯一裁决，与 v3.0.1 SPEC M5-1 对齐补全）**：

| 调用点 | 谓词 | 捕获层 |
|---|---|---|
| useSegmentEdit.updateSegmentTime | 目标段存在绑定 | `["segments","tracks","bindings"]` |
| 同上 | 目标段无绑定 | `["segments"]`（现状） |
| useEdit 拆分 | 拆分目标段存在绑定 | `["segments","edits","tracks","bindings"]` |
| 同上 | 无绑定 | `["segments","edits"]`（现状） |
| useEdit 成对删除 | 删除触发成对级联（目标段有绑定） | `["segments","edits","tracks","bindings"]` |
| 同上 | 无绑定 | `["segments","edits"]`（现状） |
| useWorkspaceActions 副轨导入 | 恒真 | `["tracks","bindings"]` |

**实现**：谓词查询用既有 `activeBindings`（WorkspacePage computed）按 `main_segment_id` / `extension_segment_id` 判断，不新增数据通道。

**清理（S3/R3.5）**：删除 `export_service.py:384-396` `export_track_srt`；**同步清理清单（全量，已 grep 核实）**：`tests/test_track_export.py`（:9 import / :83 调用）、`tests/test_tracks_contract.py`（:10 / :269 注释 / :275 / :279 / :288 / :296 import 与调用——用例改走 `export_track_subtitle` 或删除）、`core/export_service.py:417`（`export_track_subtitle` docstring 中的 legacy 引用文字）、`docs/PROJECT_SCHEMA.md:68`（文档更新）。**已核实 main.py 无引用**。

**验收**：集成测试（vitest）——真实调用点：绑定段 trim → undo → segments/tracks/bindings 三层同回退 + redo 对称 + revision 单调；无绑定 trim → 捕获层与现状一致；`grep -rn export_track_srt core/ tests/` 空（docs/3.0.1 历史记录不回改）。

---

## M2: 行几何内核（P0，纯函数）

新文件 `frontend/src/composables/useRowLayout.ts`。**模块纪律：核心几何函数为模块级纯函数（禁止 import Vue 组件/bridge/store）；composable 壳只做响应式绑定**。逐函数可独立实例化测试。

### M2-1: 常量与类型

```ts
export const SECONDS_PER_ROW_PRESETS = [5, 10, 20, 30] as const
export const ROW_HEIGHT_PRESETS = [64, 80, 96, 120, 144, 168] as const
export const DEFAULT_SECONDS_PER_ROW = 10
export const DEFAULT_ROW_HEIGHT = 120
export const ROW_GAP = 10
export const ROW_BUFFER = 2                    // 视口前后缓冲行数
export const MANUAL_FOLLOW_COOLDOWN_MS = 3000
export const WHEEL_DEBOUNCE_MS = 160           // 行高/每行秒数滚轮合并
export const SCRUB_SEEK_INTERVAL_MS = 32       // scrub 节流（对位 MAW）
export const FOLLOW_BIAS = 0.35                // 播放跟随偏置
export const REVEAL_BIAS = 0.45                // 跳转偏置

export interface RowSpan { start: number; end: number }
```

### M2-2: 纯函数契约

```ts
export function computeRowCount(duration: number, secondsPerRow: number): number
// max(1, ceil(duration / spr))；duration<=0 → 1；spr<=0 → 抛 Error

export function rowSpanAt(index: number, duration: number, secondsPerRow: number): RowSpan
// { start: index*spr, end: min(duration, (index+1)*spr) }；index 越界抛 Error

export function lastRowWidthPercent(duration: number, secondsPerRow: number): number
// ((duration % spr) || spr) / spr * 100；末行不足整行时按比例缩短（100 为满行）

export function strideOf(rowHeight: number): number   // rowHeight + ROW_GAP

export function visibleRowWindow(
  scrollTop: number, viewportHeight: number, rowHeight: number, rowCount: number,
): { first: number; last: number }
// first = clamp(floor(scrollTop/stride) - ROW_BUFFER, 0, rowCount-1)
// last  = clamp(ceil((scrollTop+viewportHeight)/stride) + ROW_BUFFER, 0, rowCount-1)
// viewportHeight <= 0 → { first: 0, last: min(ROW_BUFFER, rowCount-1) }

export function scrollTopToTime(scrollTop: number, rowHeight: number, secondsPerRow: number): number
// floor(scrollTop / stride) * spr（视口顶行行首时间）

export function timeToScrollTop(time: number, rowHeight: number, secondsPerRow: number): number
// floor(max(0,time) / spr) * stride —— 量化到行边界（恢复浏览位置）

export function rowIndexAtTime(time: number, secondsPerRow: number): number
// floor(clamp(time, 0, ∞) / spr)

export function comfortInset(viewportHeight: number): number
// clamp(viewportHeight * 0.2, 48, 120)

export function isRowInComfortZone(
  rowIndex: number, scrollTop: number, viewportHeight: number, rowHeight: number,
): boolean
// rowTop = rowIndex*stride - scrollTop；rowTop >= inset && rowTop + rowHeight <= viewportHeight - inset

export function followScrollTop(
  rowIndex: number, viewportHeight: number, rowHeight: number, maxScrollTop: number,
  bias = FOLLOW_BIAS,
): number
// clamp(rowIndex*stride - viewportHeight*bias, 0, maxScrollTop)

export interface RowPointerGeometry { left: number; width: number }
export function timeFromPointerInRow(
  rect: RowPointerGeometry, rowSpan: RowSpan, clientX: number, opts: { bounded: boolean },
): number
// ratio = (clientX - rect.left) / rect.width
// bounded: ratio 钳 [0,1] → rowSpan.start + ratio*(end-start)
// unbounded: 不钳 ratio → 同式（调用方自行 clamp 到 [0, duration]）
// rect.width <= 0 → 抛 Error
```

**裁决**：
- 秒单位（float）不引入毫秒——与全仓 Segment 时间单位一致（trackConstraints round3 先例）；MAW 是 ms 我们是 s，语义对照而非数值照抄。
- `timeToScrollTop` 与 `scrollTopToTime` 非互逆（floor 双向量化）——这是刻意行为（恢复时对齐行边界），测试锚定。

**验收**：`useRowLayout.test.ts` 逐函数边界表（M8-1）+ 模块纯性（import 无 vue/bridge）+ 移植 MAW test_waveform_js.mjs 舒适区用例（:283-289 语义对位：390px 视口 inset=78px）。

### M2-3: composable 壳

```ts
export function useRowLayout(duration: Ref<number>): {
  state: Ref<{ mode: "multi" | "basic"; secondsPerRow: number; rowHeight: number }>  // localStorage 绑定
  rowCount: ComputedRef<number>
  scrollTop: Ref<number>                    // 滚动容器受控源
  visibleRows: ComputedRef<{ first: number; last: number }>
  setSecondsPerRow: (v: number) => void     // 预设白名单校验
  setRowHeight: (v: number) => void
  setMode: (m: "multi" | "basic") => void
  revealTime: (time: number, center?: boolean) => void   // M6-1 实现
  // ...
}
```

白名单校验：非预设值回退默认（对位 MAW normalizeLayoutData :503-543 语义）。

---

## M3: 行级 metrics 适配器 + WaveformRow（P1）

### M3-1: 行级 metrics 适配器

**裁决：不修改 `useTimelineMetrics` 本体，不新增 mode 分支**。新建工厂：

```ts
// frontend/src/composables/rowMetrics.ts
export function createRowMetrics(
  rowIndex: number, duration: Ref<number>, currentTime: Ref<number>,
  secondsPerRow: number, containerRef: Ref<HTMLElement | null>,
): TimelineMetrics
```

**实现形式裁决（评审修正）**：Ref 成员一律用 `computed()` 构造——`ComputedRef<T>` 继承 Ref 的名义标记（`[RefSymbol]`），可直接填入 `Ref<T>` 槽位，且 PlayheadOverlay:52 / WaveformCanvas:309/:313 以这些成员为 **watch source** 的既有用法保持合法。**禁止**裸 getter 对象冒充（缺 `[RefSymbol]` 与 setter，TS 报错 + watch source 非法）。

**显式前提（跨模块承重不变量）**：适配器**静态捕获** `rowIndex` 与 `secondsPerRow`（构造后不随 spr 变化）——正确性依赖 M4-2 的「spr 变更 → 全量重挂行」裁决；行高变更不重挂（几何-only），适配器不受影响。

**成员分类（依 M0-2 实测清单）**：

| 分类 | 成员 | 实现 |
|---|---|---|
| 重算组 | `viewStart` / `viewDuration` / `viewEnd` / `timeMarks` / `minorTimeMarks` / `getTimeFromX` | computed/闭包按行窗重算（`viewEnd = min(rowStart + spr, duration)`——末行语义）；刻度算法复用 `NICE_STEPS`（从 useTimelineMetrics 抽为共享导出，两处 import 同源）；行间独立 cachedStep 缓存（行数 ≤ 视口+4，量级安全） |
| 直通组 | `duration` / `containerRef` | 直接透传（containerRef 为行容器元素 ref） |
| 形式组 | `timeToPercent` / `percentToPixels` / `playheadPercent` / `playheadVisible` | 按行窗实现（无消费方，仅满足接口形状；仍按语义正确实现，防未来消费） |
| no-op 组 | `scrollTo` / `zoomAt` / `handleWheel` / `ensurePlayheadInView` / `maybeFollowPlayhead` / `thumbLeft` / `thumbWidth` / `clampViewStart` | no-op + DEV 模式 console.warn 一次（行实例无导航职责） |

**watch 零注册**：适配器自身不调用 `watch()`（M0-1 红线 5 具体化）；`currentTime` 仅作为形式组成员的依赖。行组件卸载时适配器随之 GC（无全局副作用）。

### M3-2: WaveformRow 组件

```vue
<script setup lang="ts">
// props: rowIndex, rowHeight, widthPercent(末行), duration, currentTime,
//        segments, edits, waveformPeaks(注入), updateTime 等（透传既有 props）
// provide: createRowMetrics(...) → TIMELINE_METRICS_KEY（行作用域覆盖祖先注入）
</script>
<template>
  <div class="waveform-row" :style="{ top, height, width }" :data-row-index :data-row-start :data-row-end>
    <span class="waveform-row-time">{{ 行起始 → 行结束 }}</span>
    <WaveformCanvas ... />          <!-- 零改动，按行窗采样 -->
    <TimeMarksLayer ... />          <!-- 零改动，行级标尺 -->
    <SegmentBlocksLayer ... />      <!-- 零改动，行窗内自动裁剪（percent 定位天然裁剪） -->
    <PlayheadOverlay v-if="currentTime ∈ rowSpan" ... />   <!-- 行级播放头 -->
    <div v-if="hover 本行" class="hover-preview" ... />    <!-- R5.8：仅指针所在行 -->
  </div>
</template>
```

**边界与裁决**：
- `SegmentBlocksLayer` 渲染层零改动成立（评审确认）：`visibleBlocks` 按注入 metrics 窗口 clamp（:79-87），行适配器按行窗重算后越界块自动截断；**但交互层有一处必须改动（M5-3 消解）**——其根节点 `@mousedown.self` 现状直接 `emit("add-segment")`（:110-113），与 multi「空点 = 清选 + seek」冲突，改动方案见 M5-3（`emptyAreaMode` prop）；
- **SegmentBlock 实际改动点清单（修正"唯一改动点"声明）**：① `continuesFrom/continuesTo` 可选计算 prop + class 绑定（默认 false，不影响 basic/主轨路径）；② 手柄渲染条件 `edgeInRow && 现有条件`；③ trim 时间源参数化——可选注入 `getTimeFromPointer?: (clientX) => number`（默认走现状 `metrics.getTimeFromX`；multi 模式由 WaveformRow 注入 useRowDragCapture 的 frozen 换算，M5-4）；④ `clampTime` 从组件私有函数抽为 `trackConstraints.ts` 导出（`clampTimeToNeighbors`，供主/副轨与行级复用，双侧镜像同步）；
- **WaveformRow 必须向 SegmentBlocksLayer 传全轨 segments 数组**（trim 邻居约束 `getTrackNeighborBounds` 需全量兄弟——跨行邻居），emits 转发矩阵：`select-range` / `add-segment` / `delete-segment` / `seek-segment` / `split-segment` / `trim-end` / `set-time` / `toast` 全量上行到 WaveformEditor（与现状 WaveformEditor 模板一致）；
- 跨行选择状态归属：行局部 `selectedBlockId` 仅管行内视觉；**跨行选择集合归属 WorkspacePage 既有 `selectedSegmentIds` 全局状态**（框选命中 id 集合并入，M5-3）；
- 块 active 高亮（R5.3）：沿用现状「currentTime ∈ [start,end)」判定——行窗裁剪后天然只有当前行的块命中，零改动；
- 双击块 = 编辑（R7.3）：现状语义零改动，multi 同；
- 行组件**不持有跨指针状态**（M4-3 架构前提）。

**验收**：`WaveformRow.test.ts`——行窗刻度正确、块裁剪（越界块不渲染出行）、延续类正确、手柄行内规则、播放头仅本行显示、适配器 no-op 不炸、`getTimeFromPointer` 注入后 trim 走注入源（默认回退现状）。

### M3-3: 拖拽状态上提骨架（S5.7，P1 落地）

新建 `frontend/src/composables/useRowDragCapture.ts`（骨架）：

```ts
export interface FrozenRowGeometry { rowLeft: number; rowWidth: number; rowStart: number; rowSpan: RowSpan }
export function useRowDragCapture() {
  const frozen = ref<FrozenRowGeometry | null>(null)
  function capture(clientX: number, rowIndex: number, geometry: FrozenRowGeometry): void
  function timeAt(clientX: number, opts: { bounded: boolean }): number | null  // 用 frozen 换算
  function release(): void
  return { frozen, capture, timeAt, release }
}
```

编排层单例持有（provide 给行组件消费）；P2 的 M5 在此骨架上接交互。**验收**：骨架单元测试（capture 后行销毁不影响 timeAt）。

---

## M4: 编排改造（P1）

### M4-1: WaveformEditor 多行分支

```
WaveformEditor.vue
├─ 控件栏（P1 最小形态：模式切换 + 每行秒数 + 行高 select，先服务 beta 冒烟；
│         P1 阶段变更 spr 允许 scrollTop 跳变——播放行锚定 M5-2 在 P2 落地，属已接受的临时行为）
├─ mode === "basic" → 现状渲染路径原样（单窗 + lanes + 全局 Playhead + ScrollbarStrip 现状语义）
└─ mode === "multi" → 多行容器
    ├─ .waveform-scroll（overflow-y: auto; overscroll-behavior: contain; 受控 scrollTop）
    │   └─ .waveform-content（height = rowCount×stride − ROW_GAP; position: relative）
    │       └─ v-for row in visibleRows :key="rowIndex" → WaveformRow
    └─ 迷你总览条（P2 M6-4 实装，P1 占位隐藏）
```

**边界**：
- 多行模式下**副轨 lanes 暂不渲染**（P3 M7-2 才组合）——beta.1 冒烟范围 = 主轨多行；
- wheel 监听挂 `.waveform-scroll`（multi）与现状 stack（basic）各自独立，切换 mode 时移除/重挂；
- `metrics.handleWheel` 仅 basic 使用；multi 的 wheel 家族在 M5-1 实现（P1 阶段 multi 容器普通滚动即可用——原生滚动不需要 JS）；
- duration 缩短（重开工程/换媒体）时 `scrollTop` clamp 到 `maxScrollTop`（`rowCount×stride − ROW_GAP − viewportHeight`，负值归零）。

### M4-2: 虚拟化与重挂策略

- `visibleRows` 依赖 `[scrollTop(rAF 合帧后), viewportHeight(ResizeObserver), rowHeight, rowCount]`；
- **每行秒数变更（spr 档位切换）→ 全量重挂**（key 含 spr 派生的 viewStart；简单可靠，MAW renderMulti 同款全量语义）；
- **行高变更 → 仅改 top/height/width 几何**（key 不含 rowHeight——Vue keyed 复用组件实例，行内 canvas 由 ResizeObserver 触发重绘）；对位 MAW updateMultiRowLayout 增量语义；
- scrollTop 保持：spr/rowHeight 变更后按「当前播放行锚定」重算（M5-2）。

**验收**：`WaveformEditor.test.ts` 扩展——multi 渲染行数 = 视口行数 + 4、spr 变更全量重挂、rowHeight 变更几何-only、basic 分支测试零改动全绿。

### M4-3: peaks 共享与包络记忆化（S6）

- `WaveformEditor` 编排层：peaks fetch + `parseWaveformPeaks` 单次执行，`provide` 只读数组（或模块级缓存 keyed by waveformPath）；
- `WaveformCanvas` 增可选注入 prop `peaksData`（提供时跳过自身 fetch）——**向后兼容**：未提供时走现状 fetch（basic 模式零改动）；
- 包络记忆化落点裁决：采样区间计算抽为**纯函数** `computePeakSlice(peaks, viewStart, viewEnd, duration, widthPx)`（入 `utils/waveformPeaks.ts`），WaveformCanvas 绘制路径调用；记忆化 wrapper（`{key → slice}` Map）挂在行组件层——**basic 模式不包 wrapper 零影响**，multi 行组件按 `{rowIndex, widthPx, dpr}` 缓存命中；dpr cap 2。

**验收**：vitest——peaks 注入时无 fetch 调用（mock spy 断言单次）；`computePeakSlice` 纯函数数值断言 + wrapper 缓存命中计数断言。

### M4-4: R5.5 二分切片处置裁决（差异回写记录项）

**裁决：不做**。SegmentBlocksLayer 维持 O(S) `visibleBlocks` 过滤（零改动），理由：可视行数 ≤ 视口+4（约 8-12 行），1167 段参考工程下每次 patch 应用或行挂载的过滤成本 ≈ 12 × 1167 ≈ 1.4 万次比较（<1ms，projectPatch.perf 先例同量级）；行级 trim 的邻居约束本就需要全轨数组（M3-2）。若 P3 性能对账显示热点，再引入 `firstCueIndexOverlapping` 二分（MAW 测试用例已就位可随时移植）。**登记附录差异记录并回写 PRD R5.5。**

---

## M5: 手势系统与行内交互（P2）

### M5-1: wheel 家族（multi 模式）

| 手势 | 行为 | 实现 |
|---|---|---|
| 普通滚轮/触控板 | 原生竖向滚行 | 不 preventDefault；deltaMode 归一沿既有方案（mac 触控板像素/Windows 行单位） |
| Ctrl/Cmd+滚轮 | 循环 spr 档 [5,10,20,30] | 160ms debounce 合并净步数；重排后播放行锚定（M5-2） |
| Ctrl/Cmd+Shift+滚轮 | 循环行高档 [64..168] | 160ms debounce；几何-only 更新 |
| （basic 模式） | 现状：Ctrl+滚轮连续缩放 / 普通滚轮平移 | 零改动 |

**边界**：ctrlKey 判断含 metaKey（mac Cmd）；gesture 事件（触控板 pinch）不处理（MAW 同款放弃，浏览器 pinch-zoom 由 WebView 层接管）。

### M5-2: 档位切换的播放行锚定

spr 变更前后 `rowIndexAtTime(currentTime)` 不变 → `scrollTop = followScrollTop(rowIndex, ..., REVEAL_BIAS)`；行高变更同理（不重排时间，仅几何，锚定策略同）。

### M5-3: 行内指针交互（S7.2-R7.5）

**空点语义冲突消解（评审必改项）**：SegmentBlocksLayer 根节点 `@mousedown.self` 现状 = `emit("add-segment", time, time+0.5)`（:110-113）。裁决：SegmentBlocksLayer 增可选 prop `emptyAreaMode: "add" | "seek" = "add"`——`"add"`（默认，basic 模式）行为零变化；`"seek"`（multi 模式，WaveformRow 注入）改为 `emit("set-time", boundedTime)` + 清选上行。改动点入 M8-1 用例矩阵（双模式各断言）。

- 点击空白：`timeFromPointerInRow(bounded)` → 清选 + seek（`emptyAreaMode="seek"` 链路）；
- scrub：pointerdown 起 `useRowDragCapture.capture` → pointermove `timeAt(unbounded)` + clamp[0,duration] → 32ms 节流 emit seek，pointerup 精确 seek 一次；`waveformScrubbing` 标志为编排层 ref——字幕列表跟随抑制走既有 `updateActiveCue` 等价链路（WorkspacePage 侧播放联动 composable），scrubbing 期间跳过列表滚动；
- 双击空白：播放/暂停（复用 handleTogglePlay 链路）；双击块 = 编辑（现状）；
- Ctrl+拖空白新建字幕：`emptyAreaMode="seek"` 下 Ctrl 修饰进入建段模式——预览矩形（行内 bounded）+ 占用检查（段时间重叠拒绝，复用 `extensionRangeOverlapsNeighbors` 语义对主轨用 `constrainCueRangeToTrack` 判定）+ 预览遇已有段停边界 → emit add-segment（现状链路）；
- Shift+拖空白框选：选框挂 `.waveform-content`（与行同坐标系，跨行），pointermove 对全部可视行块做矩形相交 → 命中 id 集合并入 WorkspacePage 既有 `selectedSegmentIds`（全局多选状态，见 M3-2 归属裁决）。

### M5-4: 多行 trim（S7.8，本模块核心裁决）

- 块 trim pointerdown → `capture`（冻结几何）→ pointermove 经 SegmentBlock 注入的 `getTimeFromPointer`（M3-2 改动点③）取 unbounded 时间 + clamp[0,duration]；
- **约束链（对齐现状 :142-144 的三段式）**：unbounded 时间 → `clampTimeToNeighbors`（M3-2 改动点④抽出的轨道邻居 clamp，blocked 拒动）→ snap（SNAP_STEP，Alt 反转）→ **snap 后二次 clamp**（snap 可能越出邻居边界，回邻）→ 乐观更新（useSegmentEdit / useTrackEdit）；
- **行边界不进入约束链**（只管手柄可见性与视觉裁剪）；
- 拖拽中滚动触发行回收：frozen 几何保证时间连续（M3-3 骨架的接线验证点）。

**Alt 语义行为矩阵（评审必改项，与 v3.0.1 既有裁决对齐后收敛）**：

| 场景 | Alt 行为 | 依据 |
|---|---|---|
| 任意轨道 trim/move | 反转 snap（SNAP_STEP 启停） | 现状既有（SegmentBlock :139-143），保留 |
| 主轨 trim + Alt + 有绑定 | **联动照常发生**（不提供跳过通道） | v3.0.1 SPEC M2-1 明文「不提供跳过联动的通道」；引入跳过需后端 update_segment 增参数，违反本版 schema 冻结红线 |
| 副轨 trim + Alt | **无特殊语义**（副轨编辑本就从不反改主轨——主轨保护红线；offsets 派生重建是数据一致性要求而非可跳过的联动） | MAW 的 Alt-independent 解决的「拖副段带偏移联动」问题在我方数据模型中不存在 |

**回写 PRD**：R7.7「Alt = 副轨独立拖动本版补全」修正为「Alt 语义收敛为反转吸附（唯一语义）；副轨独立拖动裁决不做，理由见 SPEC M5-4 矩阵」——登记附录差异记录。

**验收**：`useRowDragCapture` 专项（拖拽中强制 scrollTop 变更 + 行 unmount，timeAt 输出连续）；多行 trim 约束（trim 越过行边界不被钳、被邻居钳、snap 后二次 clamp、Alt 反转 snap 且联动不受 Alt 影响）。

### M5-5: 手势真机清单（双平台必测）

滚轮四手势 / 触控板双指滚动与 pinch（WebView 缩放接管确认）/ scrub 手感（32ms）/ 框选跨行 / trim 跨行 / Alt 独立。

---

## M6: 跟随、模式切换、持久化、总览条（P2）

### M6-1: 跟随三分

- **播放跟随**：`watch(currentTime)` → rowIndex 变化时（换行才判定）`isRowInComfortZone` 不满足 → `scrollTop = followScrollTop(rowIndex, FOLLOW_BIAS)`（smooth）；`autoScrollTarget` 记录目标防滚动事件回环；
- **手动滚动冷却**：scroll 事件 `isTrusted && !wasAutoScroll` → `manualFollowUntil = now + 3000`；跟随判定前检查冷却；
- **跳转 revealTime**：`revealTime(t, center)`——目标行在舒适区 → 只动播放头；否则 `followScrollTop(rowIndex, REVEAL_BIAS)` + `manualFollowUntil = now+3000`；字幕列表点击/seek 导航统一走此入口；
- 现状 `maybeFollowPlayhead`（出窗即居中 200ms 节流）**仅保留在 basic 分支**。

### M6-2: 模式切换

- 控件栏 segmented（多行/聚焦）；`setMode` 重置：`multiRange` 等价缓存、frozen 拖拽状态、跟随标志；
- basic 切入时 `scrollTo(currentTime)`（现状语义居中）；multi 切入时 `revealTime(currentTime, true)`。

### M6-3: 设置持久化

- localStorage key `milocut:timeline-rows:v1`：`{ mode, secondsPerRow, rowHeight, scrollTopTime, editorHeightPx }`；
- 写入时机（裁决）：mode/spr/rowHeight/heightPx **变更即写**；`scrollTopTime` **debounce 300ms**（滚动停止后写，避免滚动期高频 localStorage 写）+ 组件卸载时兜底写一次；
- 读取：`JSON.parse` try/catch，损坏回退默认；白名单校验非预设值回退默认；
- 恢复：`scrollTop = timeToScrollTop(scrollTopTime)`（量化行边界）+ duration 缩短 clamp（M4-1）；工程重开时恢复；
- **模式切换双向迁移**：basic → multi：`revealTime(viewStart + viewDuration/2, true)`；multi → basic：`scrollTo(scrollTopToTime(scrollTop) + spr/2)`（现状居中语义）。

### M6-4: 迷你总览条

- multi 模式 ScrollbarStrip 转型：全片缩略条——**新计算**覆盖区间几何（评审修正：`thumbLeft/thumbWidth` 是单窗窗口几何，不可直接复用）：`thumbLeft = visibleRows.first × spr / duration`、`thumbWidth = (visibleRows.last+1 − visibleRows.first) × spr / duration` + 播放头位置刻线（currentTime/duration）；
- 点击/拖拽 → `revealTime(对应时间)`（经行对齐 scrollTop）；
- basic 模式：现状语义与交互零改动。

**验收**：round-trip 测试（写读对称、损坏回退、debounce 生效）；总览条覆盖区间与实际 visibleRows 一致（vitest 数值断言）。

---

## M7: 排版与组合（P3）

### M7-1: 底部区高度与控件栏（S9）

- 高度 divider：拖拽写入 localStorage（`editorHeightPx`，clamp 到视口 20%-70%，multi 默认 45%）；布局拖拽期行 canvas CSS 拉伸、松手重绘（对位 MAW stretchWaveformCanvases :2709-2718）；
- 控件栏：左「Regen + 模式切换」/ 中「视口覆盖范围 `12:00–12:50 / 全片 58:30`」/ 右「每行秒数 + 行高 select」；
- R9.4 kbd 角标：行/块右键菜单项注快捷键（涉及菜单改动顺带）；R9.5 toast：上限 3 条 + 高频冷却参数上调（useToast 既有机制）。

### M7-2: 副轨每行组合（S10.1）

- 存在 tracks 时每行内部：主 lane（行高 − 副轨区）+ 副轨 lanes（useLaneLayout 每行实例化，**沿用现状 `LANE_PRESET_HEIGHTS` 档位**（sm 32/md 48/lg 72，min 24）——评审修正：不新造 35px 档，sm 32 已满足副轨行内显示）；
- 行高联动：存在副轨时默认档自动切 168（用户手动改过则尊重用户值，`userTouchedRowHeight` 标记）；
- 副轨 trim 在行内可用（M1-1 已激活，此处验证组合态）；
- 约束：每行 lanes 数 = 全局 tracks 数（同一时间窗的所有副轨都在每个行组内显示——MAW multi-subtitle-row 同款）。

### M7-3: 文档与性能（S10.2/R10.3）

- README 功能段、docs/design-spec.md 交互规范（手势表/跟随语义/双映射）、开发报告版本池注记；
- `docs/3.0.2/perf-baseline.md`：开工批采集 3.0.1 现状（项目打开/波形生成/undo/前端 patch apply），P3 末回填对账。

---

## M8: 测试与门禁（全程）

### M8-1: 用例矩阵

| 模块 | 文件 | 关键用例 |
|---|---|---|
| M2 | useRowLayout.test.ts | 逐函数边界表 + 纯性 + MAW 对位（舒适区 390px→78px） |
| M3 | rowMetrics.test.ts / WaveformRow.test.ts | 适配器 no-op、computed 形式（watch source 合法）、行窗刻度、块裁剪、延续类、手柄规则、播放头仅本行、getTimeFromPointer 注入回退 |
| M3 | useRowDragCapture.test.ts | capture/timeAt/release、行销毁后连续性 |
| M4 | WaveformEditor.test.ts 扩展 | 虚拟化行数、spr 全量重挂、rowHeight 几何-only、scrollTop clamp、basic 零改动 |
| M4 | peaks 共享 | fetch 单次 spy、computePeakSlice 数值、缓存命中计数 |
| M5 | 交互专项 | emptyAreaMode 双模式、双映射边界、scrub 节流、框选跨行并入全局选择、trim 约束链（含 snap 后二次 clamp）、Alt 反转 snap 且联动不受影响、拖拽中行回收 |
| M6 | 跟随与持久化 | 跟随三分（3s 冷却/回环抑制/revealTime 免滚）、round-trip、损坏回退、恢复量化、debounce、总览条覆盖区间数值 |
| M7 | 排版与组合 | 高度 round-trip、行高联动（副轨存在切 168 + userTouched 尊重）、副轨行内 trim |
| M1 | useTrackEdit.test.ts / test_track_linkage 扩展 / 集成 | 见 M1 各节 |

### M8-2: 门禁

每步合入前：`uv run pytest`（**≥702 且新增全绿**）/ `bun run test`（**≥453 且新增全绿**）/ `bun run build` / `uv run ruff check .` 全绿；P2 起追加 `projectPatch.perf` 与新增性能断言；P3 末 events-diff 为空、schema-diff 为空（除 S2/S3 修复外零后端模型改动）。

### M8-3: 性能断言（可执行形态，评审修正）

- 千段合成工程（synthetic_1167）多行滚动：visibleRows 重算 p50 < 1ms（纯计算，vitest 可执行）；
- **单行挂载 p95 < 8ms**（vitest 断言组件挂载成本——happy-dom 下 `getContext` 返回 null、canvas 位图重绘自然跳过，断言口径 = 组件初始化 + DOM 构造成本）；**canvas 位图重绘性能移交双平台真机清单**（M5-5）+ 以 `computePeakSlice` 缓存命中计数断言间接锚定重算成本；
- peaks 单次 fetch（spy 断言）；缓存命中计数断言；
- 对照 docs/3.0.2/perf-baseline.md 各项不回退。

---

## 附：与 PRD 的差异回写记录

| # | 差异 | SPEC 裁决 | PRD 回写 |
|---|---|---|---|
| 1 | R5.5 每行二分切片 | 不做（M4-4：O(S)×可视行 ≈ 1.4 万次比较 <1ms；行级 trim 邻居约束本就需全轨数组；热点再优化） | R5.5 改为「现状 O(S) 过滤维持，二分为热点优化预案」 |
| 2 | R7.7 Alt = 副轨独立拖动 | 不做（M5-4 矩阵：副轨编辑从不反改主轨，MAW Alt-independent 解决的问题在我方模型中不存在；主轨跳过联动违反 v3.0.1 M2-1 裁决且需 schema 变更） | R7.7 改为「Alt 收敛为反转吸附唯一语义」 |
| 3 | S5 「SegmentBlocksLayer 零改动」 | 交互层一处必须改：`emptyAreaMode` prop（M5-3 消解空点语义冲突） | PRD §0.3 原则 P2 补注「SegmentBlocksLayer 唯一改动 = emptyAreaMode」 |

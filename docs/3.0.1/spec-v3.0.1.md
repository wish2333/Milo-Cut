# v3.0.1 实施规格说明（SPEC）

> 版本：3.0.1（SPEC Draft）
> 上游：[PRD-v3.0.1](./PRD-v3.0.1.md) / [堆叠时间线分析](./spec-v3.0.1-堆叠时间线分析.md)
> 基线：v3.0.0 工作树（行号引用以撰写时为准）
> 日期：2026-08（草稿）
> 本文职责：把 PRD 的 11 个特性（S1-S11）细化为**输入 / 输出 / 边界 / 验收**四段齐全的可实施契约。所有"裁决"栏为本 spec 在实施层做出的唯一性决定，与 PRD 冲突时以本文为准并需回写 PRD。

---

## 概要

### 模块划分

| 模块 | 内容 | 对应 PRD | 批次 |
|---|---|---|---|
| M0 | 全局契约：常量真源、协议不变量、数据契约现状 | S1/S2 前置 | P0 |
| M1 | 约束函数族 `trackConstraints.ts`（前端纯函数） | S1 | P0 |
| M2 | 后端写入通道：重叠拒绝 + 联动编辑 + 成对删除 + 联动拆分 | S2/S7 | P0/P2 |
| M3 | patch 应用细粒度化（tracks/bindings in-place merge） | S6 | P2 第一步 |
| M4 | 堆叠渲染：useLaneLayout / TrackLane 几何化 / SegmentBlock 泛化 / 堆叠编排 | S3/S4/S5 | P1 |
| M5 | 撤销三层原子 + 布局层 | S8 | P2 |
| M6 | 导出映射 + SubtitleOverlay 副轨 + 文档收尾 | S9/S10/S11 | P3 |

### M0: 全局契约

#### M0-1: 常量单一真源

```
# 新文件 frontend/src/utils/trackConstraints.ts 顶部（M1 落地）
export const MIN_SEGMENT_DURATION = 0.1   // 段最小时长（秒）
export const SNAP_STEP = 0.01             // snap 步长（秒）
export const EDGE_HANDLE_HIT_PX = 16      // trim 命中区（留在组件层，见 M4-3）
```

- 现状：`MIN_SEGMENT_DURATION`、`snapToFrame`（0.01s）硬编码于 `SegmentBlocksLayer.vue:35,123-126`。M1 落地时提取到 `trackConstraints.ts`，`SegmentBlocksLayer` 改为 import，**删除本地定义**。
- `EDGE_HANDLE_HIT_PX`、防抖 300ms 属交互参数，真源留在 `useSegmentEdit.ts`（`DEBOUNCE_MS`）与组件层，不进纯函数模块。
- 后端重复定义最小时长常量 `core/track_constraints.py`（M2 新文件）：`MIN_SEGMENT_DURATION = 0.1`。前后端各一份是刻意的（无共享代码通道），由 M1/M2 的测试用例锚定同一数值；任何一方改值必须同步另一方并双侧改测试。

#### M0-2: 数据契约现状（实施前提，勿改）

- `SubtitleTrack`（models.py:142）：`{id, role: extension|translation|caption, name, language, segments: Segment[]}`。副轨段 id 命名空间 `track_{track_id}_seg_{start:.3f}`，**永不与主轨段 id 混用**。
- `TrackBinding`（models.py:157）是 **1:1 绑定**：`{id, track_id, main_segment_id, extension_segment_id, start_offset, end_offset}`，offset = ext − main（秒，float round3）。与 MAW 的复数 id 契约不同；PRD 已排除一对多绑定，**本版不迁移**。
- `ProjectPatch`（models.py:408）：层字段整体替换语义；`revision` 单调。前端 `isStalePatch` 拒绝 `revision <= last_seen_revision`。
- `_enforce_segment_sort_invariant`（project_service.py:112）MAIN TRACK ONLY 是 M11-2 明文契约；副轨自身维持 start 升序（由 M2 写入通道保证），**不得**把副轨纳入该不变量。

#### M0-3: 协议不变量（红线，任何模块不得违反）

1. **reconcile 绝不修改主轨 segments**——消解只发生在副轨段与 bindings 上。
2. **`apply_undo` 不触发联动**——快照恢复是忠实还原（原样替换层），不得在恢复路径上重算 offsets 或 reconcile。
3. **零新增 bridge 事件**——所有状态变更走 patch 通道；reconcile 计数经 patch 携带（M2-1），UI 提示用现有 toast emit。`core/events.py` 与 `frontend/src/utils/events.ts` 本版零改动。
4. **trackId 贯穿**——所有新增 expose 方法第一个业务参数必须是 `track_id`；所有新增前端纯函数不得隐式依赖"唯一副轨"。
5. **schema 变更仅限一处**：`ProjectPatch` 增加 `meta: dict | None = None` 可选字段（M2-1 载荷）。其余模型零变更、零迁移。
6. 破坏性操作（删除副段、解绑）必须同时满足：单条 undo 快照可整体回退 + toast 计数提示。

---

## M1: 约束函数族（P0，与 M2-1 同批合入）

新文件 `frontend/src/utils/trackConstraints.ts`。**模块纪律：禁止 import Vue、bridge、组件**；输入输出全部为可序列化数据；逐函数可独立实例化测试。

### M1-1: 邻居与主轨约束

```ts
export interface TrackNeighborBounds {
  prevEnd: number | null    // 同轨前驱 end；无前驱为 null
  nextStart: number | null  // 同轨后继 start；无后继为 null
}

export function getTrackNeighborBounds(
  segments: ReadonlyArray<Pick<Segment, "id" | "start" | "end">>,
  segmentId: string,
  movedIds?: ReadonlySet<string>,   // 豁免集合：多选/联动拖动中被移动的段不参与边界
): TrackNeighborBounds
```

```ts
export type ConstrainCueResult =
  | { ok: true; start: number; end: number }       // 已 clamp / 缝内平移后的合法区间
  | { ok: false; reason: "gap-too-narrow"; gap: number }

export function constrainCueRangeToTrack(
  start: number, end: number,
  bounds: TrackNeighborBounds,
  minDuration?: number,  // 默认 MIN_SEGMENT_DURATION
): ConstrainCueResult
```

**语义**（输入 start/end 先经 clampExtensionRange 归一）：

1. 若 `prevEnd` 存在且 `start < prevEnd`：将 start 提到 prevEnd；若 `nextStart` 存在且 `end > nextStart`：将 end 压到 nextStart。
2. 夹取后宽度 < minDuration 且原宽度 >= minDuration：**缝内平移**——保持原时长，优先贴前驱；再越界则贴后继。
3. 缝隙本身（nextStart − prevEnd）< minDuration：返回 blocked（`gap-too-narrow`），调用方必须拒动。

**边界**：空轨（bounds 双 null）→ 原样放行；区间恰好贴合邻居（start == prevEnd 或 end == nextStart）→ 放行（相等不算重叠）；NaN/负数输入 → 先经 clampExtensionRange 或直接抛 TypeError（选后者，纯函数快速失败）。

### M1-2: 副轨约束

```ts
export function clampExtensionRange(
  start: number, end: number, duration: number, minDuration?: number,
): { start: number; end: number }
// [0, duration] 夹取 + 最小时长 + Math.round(t * 1000) / 1000（整毫秒 round3）

export function extensionRangeOverlapsNeighbors(
  start: number, end: number,
  segments: ReadonlyArray<Pick<Segment, "id" | "start" | "end">>,
  segmentId: string,
  movedIds?: ReadonlySet<string>,
  epsilon?: number,  // 默认 1e-6；贴合（间隙 <= epsilon）不算重叠
): boolean
// O(n) 单遍扫描；调用方（TrackLane 拖拽）得到 true 必须拒动——副轨重叠一律 blocked，不做缝内平移
```

**裁决**：主轨拖拽 = clamp + 缝内平移（尽量成行），副轨拖拽 = blocked 拒动（禁止重叠）。与 MAW 语义一致（`constrainCueRangeToTrack` vs `extensionRangeOverlapsNeighbors` 分工）。

### M1-3: 联动跟随与消解（本 spec 的灵魂，后端 M2 按同一语义实现）

```ts
export interface ReconcileCounters { squeezed: number; removed: number; unbound: number }

export interface ReconcileResult {
  segments: Array<Pick<Segment, "id" | "start" | "end">>  // 存活副段的新几何（round3）
  removedIds: string[]        // 被删除的副段 id；解绑由调用方按 1:1 从此推导（P1-1 勘误）
  counters: ReconcileCounters // squeezed: 保留但被压缩; removed: 不足最小时长删除; unbound: 解绑(==removed)
}

export function reconcileExtensionTrack(
  extSegments: ReadonlyArray<Segment>,
  covered: ReadonlyArray<{ start: number; end: number }>, // 主轨变更后的覆盖区间
  minDuration?: number,
): ReconcileResult
```

**消解规则**（对每个与 covered 相交的副段）：

1. 计算未覆盖部分：`left = seg.start .. coveredStart`、`right = coveredEnd .. seg.end`，取**更长的一侧**保留。
2. 保留侧 >= minDuration：压缩到该侧（squeezed++）。
3. 保留侧 < minDuration：删除该副段（removed++），其 binding 一并解绑（unbound++）。
4. 与 covered 完全被覆盖（两侧皆空）：删除（removed++ / unbound++）。
5. **绝不修改 covered**（红线 M0-3.1 在纯函数层的体现：函数签名上主轨区间是只读输入）。

> **勘误（P1-1 实施时回写）**：a) `ReconcileResult` 去掉 `unboundBindingIds`——函数不持有 bindings，解绑由调用方按 1:1 模型从 `removedIds` 推导；b) `constrainCueRangeToTrack` 平移分支 dur 取**原始宽度**（不按缝 cap），"贴前驱 -> 贴后继 -> cap 到缝"三级回退，其中贴后继分支数学上仅防御路径可达（贴前驱溢出 ⟺ dur > 缝宽），保留与 MAW 结构对齐。

```ts
export function syncBoundExtensionForMain(
  mainBefore: Pick<Segment, "start" | "end">,
  mainAfter:  Pick<Segment, "start" | "end">,
  ext: Pick<Segment, "start" | "end">,
): { start: number; end: number }
// 主→副 delta 跟随：
//   move（时长不变）: 整体平移 delta = mainAfter.start - mainBefore.start
//   trim 左缘: ext.start += dLeft；trim 右缘: ext.end += dRight（双缘 trim 叠加）
//   输出仅为候选几何，必须再过 extensionRangeOverlapsNeighbors / reconcile

export function rebuildBindingOffsets(
  main: Pick<Segment, "start" | "end">,
  ext:  Pick<Segment, "start" | "end">,
): { start_offset: number; end_offset: number }
// offset = ext - main，round3。派生式重建的唯一实现；任何时间变更后全量重算，禁止增量维护
```

### M1-4: 副→主反推约束（完整移植，UI 暂不接线）

```ts
export function constrainBoundExtensionPanelEdit(
  delta: number,                       // 拖副段产生的时间位移
  main: Pick<Segment, "start" | "end">,
  bounds: TrackNeighborBounds,
  minDuration?: number,
): { ok: boolean; mainStart: number; mainEnd: number; shifted: number }
```

**裁决**：函数族完整移植 + vitest 覆盖（PRD R1.7），但本版交互面**不暴露**"拖副段带主轨"入口——拖副段只动副段（M2-2）。此函数为副→主联动预留，避免未来二次翻译 MAW 语义。

**输入**：见各签名；Segment 输入统一用 `Pick` 最小面，禁止整对象透传（保持与 Vue 响应式解耦）。
**输出**：见各签名；禁止返回组件可变引用。
**边界**：全部函数禁止持有模块级可变状态（reconcile 无跨调用记忆）。
**验收**：`frontend/src/utils/trackConstraints.test.ts` 逐函数边界用例——空轨 / 首尾段 / 缝隙恰好等于 minDuration / 缝隙不足 / 多选豁免生效 / reconcile 四条规则各一例 + counters 断言 / offset round3 / NaN 抛错。模块纯性用 lint 式测试锚定（扫描 import 列表无 `vue`/`@/bridge`）。

---

## M2: 后端写入通道与约束终审

新文件 `core/track_constraints.py`：M1-3 的 Python 镜像实现（`reconcile_extension_track` / `sync_bound_extension_for_main` / `rebuild_binding_offsets` / `clamp_extension_range` / `overlaps_neighbors`），供 M2 各写入通道复用。pytest 与前端 vitest 用**同一组边界用例表**（M1 验收栏）双侧锚定。

### M2-1: `update_segment` 增强——重叠拒绝 + 隐式联动（P0 重叠拒绝，P2 联动）

**输入**：`update_segment(segment_id: str, updates: dict)`，签名不变。
**输出**：

- 成功：`_success_patch(segments=..., tracks=..., bindings=..., meta={"linkage": {...}})`——携带哪几层由实际变更决定（见下）。
- 拒绝：`{"success": False, "error": "update_segment: segment {id} overlaps {conflict_id} ([s, e] vs [s, e])"}`。

**算法**（仅 start/end 变更路径；text-only 路径零改动）：

```
1. 若 segment_id 属于副轨命名空间（track_ 前缀）→ 拒绝并提示走 update_track_segment（M2-2）
2. new_seg = old | filtered_updates
3. 同轨重叠校验（排除自身，epsilon 贴合放行）→ 命中即拒绝（含冲突段 id）
4. 若存在 main_segment_id == segment_id 的 bindings（联动路径，P2 激活）:
     for binding:
       ext_candidate = sync_bound_extension_for_main(old, new, ext)
       按 track 分组收集候选
     对每个受影响 track 执行 reconcile_extension_track（covered = [new range]）
     重建受影响 binding 的 offsets（rebuild_binding_offsets，派生式）
     删除 removedIds 的段与对应 bindings
5. 返回 patch：segments 恒带；tracks/bindings 仅在第 4 步发生时携带；
   meta.linkage = {squeezed, removed, unbound}（无联动时不带 meta）
```

**边界**：

- `apply_undo` 恢复路径**不走本算法**（apply_undo 直接换层，红线 M0-3.2）。
- 无绑定的主段编辑行为与现状一致（除新增的重叠拒绝）。
- `_enforce_segment_sort_invariant` 保持现状调用点；重叠已在入口拒绝，不再出现"静默 sort 掩盖重叠"。
- meta 为 `dict | None`，旧前端忽略之（ProjectPatch.ts 类型补可选字段即可）。

**裁决（隐式联动 vs 显式方法）**：主轨 move/trim 提交**始终隐式联动**（绑定即跟随），不提供"编辑但跳过联动"的通道；Alt 独立语义只作用于副轨拖动方向（M4-5）。理由：绑定语义即"主变副随"，显式开关会让"静默漂移"以另一种形态回归——这正是 PRD 差距 #3 要消灭的。

**验收**：`tests/test_track_linkage.py`——重叠拒绝（前邻/后邻/双侧/贴合放行，错误信息含冲突 id）；move 跟随（整段平移、offset 不变）；trim 跟随（单边）；reconcile 三计数各一例；offset 重建正确；无绑定路径 patch 不带 tracks/bindings 层。

### M2-2: `update_track_segment` 新 expose（P2）

```
update_track_segment(track_id: str, segment_id: str, updates: dict) -> dict
```

**输入**：`updates` 仅允许 `{start, end, text}`；`start`/`end` 必须同时可推导出合法区间。
**输出**：`_success_patch(tracks=..., bindings=...)`（主轨 segments 层不携带）；`meta.linkage = {rebuilt: n}`。
**校验链（顺序固定）**：

1. track 存在（否则 `Track not found: {track_id}`）
2. segment 存在且属于该 track（否则 `Segment not found in track`）
3. 副轨命名空间 id 不可被改写（updates 中出现 id 一律剥离）
4. 时间归一（clampExtensionRange 同语义：[0, duration]、min、round3；duration 取 project.media，无 media 时上界为该段原 end 与 updates 值的较大者）
5. 同轨不重叠（blocked，含冲突 id）
6. 宽度 >= MIN_SEGMENT_DURATION

**联动语义**：变更提交后对该副段的 bindings `rebuild_binding_offsets`（派生式）；**绝不反向修改主轨**；binding 不存在时为纯时间编辑。
**裁决（Alt 独立拖动后的绑定去留）**：独立拖动只跳过"本次编辑的联动跟随"，提交后 offsets 仍派生式重建——**独立拖动 ≠ 解绑**。理由：P2 原则（offset 派生式重建）下绑定恒真；解绑是显式操作（本版不设副轨解绑 UI，unbound 仅由 reconcile 产生）。
**验收**：`tests/test_track_linkage.py` 补——校验链六条各一例；offset 重建；主轨段 id 零变更断言。

### M2-3: `delete_segment` 成对删除 + `split_segment` 联动拆分（P2）

**delete_segment**（签名不变）：

```
1. 命中 bindings where main_segment_id == segment_id（0..n 条，1:1 模型下实际 <=1，实现按 0..n 写）
2. 删除对应 extension_segment_id 的副段（各 track 内）+ 删除 bindings
3. 主轨删除的既有 edits 语义保持现状不动
4. 返回 _success_patch(segments, tracks, bindings)；meta.linkage = {removed, unbound: 0}
```

**split_segment**（签名不变，`position` 为主轨绝对切点）：

```
1. 主段拆为 a/b（现有逻辑与 id 规则）
2. for binding（main_segment_id == 被拆段）:
     cut_ext = position + binding.start_offset        # 共用绝对时刻，映射到副段时间轴
     if ext.start + MIN <= cut_ext <= ext.end - MIN:  # 可拆
         拆 ext -> ext_a / ext_b（id 沿用副轨命名空间规则）
         binding 重挂为两条：a<->ext_a、b<->ext_b（offsets 全部 rebuild）
         counters.split++
     else:
         binding 重挂到与 ext 时间重叠更大的那一侧（overlap(a) vs overlap(b)，相等取 a）
         若两侧重叠皆 < MIN：解绑，counters.unbound++
         counters.rebound++（重挂路径）
3. 返回 _success_patch(segments, tracks, bindings, meta.linkage)
```

**裁决（切点越界的 binding 去向）**：按"主副段时间重叠更大者"重挂而非一律解绑——切点擦边时保住绑定是用户直觉；完全无法归属才解绑并计数。
**验收**：切点可拆 / 切点越界重挂前侧 / 重挂后侧 / 解绑 + unbound 计数；undo 单条快照三层回退（配合 M5 集成测试）。

---

## M3: patch 应用细粒度化（P2 第一步，先于 M2 联动合入）

**输入**：现有 `ProjectPatch.tracks/bindings` 层——**schema 不变，后端仍发全量层**（与 M7-1 segments 层先例同构：传输全量、应用细粒度）。
**输出**：`applyProjectPatch` 应用后，未变更的 track / track 内 segment / binding **对象引用恒等**（`toBe` 级）。

```
# frontend/src/utils/projectPatch.ts 新增
function trackEqual(a, b): boolean          // id/role/name/language + 逐段 segmentEqual
export function mergeTracksInPlace(oldTracks, newTracks): SubtitleTrack[]
//   按 trackId 保序复用；track 内 segments 复用 mergeSegmentsInPlace；
//   track 级字段与全部段皆等 → 返回旧 track 引用
export function mergeBindingsInPlace(oldBindings, newBindings): TrackBinding[]
//   按 binding id 复用（TrackBinding 全字段比较）
```

- Gate assertion 沿袭 M7-1：合并后 id 序列必须与后端数组完全一致，否则 console.warn + 整体替换（"宁可慢，不可错序"）。
- 布局消费侧不动：`TrackLane` / `WaveformEditor` 的 props 引用稳定性由此自动获得。

**裁决（为何不做 ops 式增量协议）**：ops 协议（`{upserts, removals}`）要动 `ProjectPatch` schema、后端全部 track 写入点与 undo 快照往返形态，风险收益比劣于"全量传输 + 引用稳定"。传输体积先例：segments 层千段全量已在生产运行；副轨段量级（百段 x <=4 轨）更小。
**边界**：`mergeSegmentsInPlace` 的现有排序 gate 只管主轨；副轨排序 gate 在 `mergeTracksInPlace` 内对每 track 单独执行（副轨无全局 sort 不变量，见 M0-2）。
**验收**：`projectPatch.test.ts` 扩展——单副段变更后其余全部 track/segment/binding 引用 `toBe` 恒等；`projectPatch.perf.test.ts`（或 undoScale 同款 harness）——1000 主段 + 4x200 副段规模下 apply 耗时断言（p50 < 5ms）与 O(n) 单遍扫描结构断言；**此测试是 P2 其余工作的合入门禁**。

---

## M4: 堆叠渲染（P1）

### M4-1: `useLaneLayout`（新文件 `frontend/src/composables/useLaneLayout.ts`）

```ts
export type LaneHeightPreset = "sm" | "md" | "lg"   // 32 / 48 / 72 px
export interface LaneLayoutState {
  collapsed: Record<string, boolean>   // trackId -> 折叠
  hidden: Record<string, boolean>      // trackId -> 显隐
  preset: Record<string, LaneHeightPreset>
}
export interface LaneLayoutItem { trackId: string; top: number; height: number; collapsed: boolean; hidden: boolean }
export function computeLaneLayout(
  containerHeight: number, trackCount: number, state: LaneLayoutState,
): { lanes: LaneLayoutItem[]; mainTrackHeight: number; totalLanesHeight: number }
// 主轨高度 = containerHeight - Σ(可见 lane 高)；mainTrackHeight 有下限（>= 96px），
// 超限时按 lane 顺序压缩 lane 高至最小 24px，仍超限则提示轨数过多
```

- 布局状态持久化：`localStorage["milocut:timeline-layout:v1"]`，**全局偏好，不按项目区分**；trackId 失配条目容忍并惰性清理。纯前端层：不入 undo、不入 patch、不入 settings.json（PRD R8.2 的落地形态）。
- **验收**：`useLaneLayout.test.ts`——0/1/4 轨、全部折叠、主轨下限挤压、localStorage 损坏 JSON 回退默认值。

### M4-2: TrackLane 几何化重写（改写现有 `components/workspace/TrackLane.vue`）

- **迁移**：从 `Timeline.vue:611` 摘除，挂载点移入 `WaveformEditor` 堆叠区（Timeline 虚拟列表恢复不含 TrackLane 的原状）。
- **输入 props**：`{ track: SubtitleTrack, lane: LaneLayoutItem }`；inject `TIMELINE_METRICS_KEY`（共享缩放）。
- **输出 emits**：`seek`、`trim`、`move`、`split`、`toggle-collapse`（折叠切换经 useLaneLayout 状态，不入后端）。
- 渲染：可见副段过滤（同 SegmentBlocksLayer 的视口裁剪）+ percent 定位 `SegmentBlock`；折叠时 lane 高度收缩为标题条（轨道名 / language / 段数徽标 + 显隐与高度档位控件）。文本列表形态**删除**，由堆叠几何形态取代。
- 轨道数 > 4：lane 区顶部一次性提示"副轨较多，建议合并或隐藏"（不硬限）。
- **验收**：`TrackLane.test.ts` 重写——percent 定位正确性、折叠/显隐 emits、>4 提示；删除旧文本列表用例。

### M4-3: `SegmentBlock` 泛化（新文件 `components/waveform/SegmentBlock.vue`）

- 从 `SegmentBlocksLayer.vue` 抽出单块渲染 + trim 交互（16px 命中、snap、min duration、拖拽乐观更新回调）。
- **参数化 props**：`{ segment, leftPercent, widthPercent, state?, trackKind: "main" | "extension", onTrimStart/Move/End }`。
- `SegmentBlocksLayer` 改为组合 `SegmentBlock` 的主轨容器（行为零变化，现有测试必须全绿）；`TrackLane` 以 `trackKind="extension"` 复用。
- **验收**：新 `SegmentBlock.test.ts`；`SegmentBlocksLayer.test.ts` 全绿不改动断言（纯重构锚定）。

### M4-4: 堆叠编排（改造 `WaveformEditor.vue`）

- 结构：外层 flex-col，主轨区（现有 z0-z10 分层容器，含波形 canvas / TimeMarks / SegmentBlocksLayer / hover 预览）+ lane 区（N x TrackLane）。`useTimelineMetrics` 实例不变，containerRef 指向**整个堆叠容器**（getTimeFromX 对全堆叠区生效）。
- 播放头：`PlayheadOverlay` 从主轨层**提升**到堆叠容器直属子节点，`inset-y-0` 贯穿主轨 + 全部 lane；z 序维持 10（呼应"提升 owner 而非提升弹层"规则，R11.2 一并落 design-spec）。
- **核验修正（推翻 PRD R4.2 字面）**："波形 canvas 每 lane 一个"不成立——`SubtitleTrack` 无波形峰值数据源，lane 没有 canvas 输入。裁决：**主轨保持单 WaveformCanvas**；lane 为纯 DOM 块渲染；`createRafScheduler` 复用于 lane 拖拽的指针采样节流。PRD 回写时将 R4.2 改述为"lane 按需引入 canvas（当前无数据源，不引入）"。这样 M1.5 的"行级虚拟回收不引入"在结构上自动成立。
- **边界**：lane 区不响应 `add-segment`（副轨段只来自 SRT 导入与拆分，本版不设"空轨道点击建段"）；wheel 缩放/平移在整个堆叠容器生效。
- **验收**：`WaveformEditor.test.ts` 扩展——堆叠结构渲染 lane 数正确、播放头 DOM 为单节点且 inset-y-0、wheel 事件在 lane 区生效。

### M4-5: Alt 语义接线

- Alt（macOS 同时 Option）按住时：snap 临时反转（吸附失效）+ 副轨拖动不触发联动跟随。实现于 SegmentBlock 指针处理层（读 `e.altKey`），提交仍走 M2-2（offsets 派生重建，见 M2-2 裁决）。
- **验收**：`SegmentBlock.test.ts`——altKey 下 snap 偏移与联动回调参数断言。

---

## M5: 撤销三层原子与布局层（P2）

### M5-1: 撤销层扩展（前后端双侧同步，先于 M2-1 联动合入）

```
# frontend/src/utils/undoRecords.ts
UndoLayer += "tracks" | "bindings"；captureLayers 增加：
  tracks   -> [...tl.transcript.tracks]        // 浅拷贝引用数组（与 segments 层决策一致）
  bindings -> [...tl.transcript.bindings]

# core/project_service.py
_UNDO_LAYERS += ("tracks", "bindings")
apply_undo 校验：tracks -> list[SubtitleTrack.model_validate]，bindings -> list[TrackBinding.model_validate]
全部层 validate 通过后才整体替换（沿用现有 all-or-nothing 原子语义）；base_revision 校验不变
```

**操作 → 捕获层映射表**（`useTrackEdit.ts` / 既有调用点按此执行，`onBeforeProjectUpdate` 第二参）：

| 操作 | 捕获层 | 备注 |
|---|---|---|
| 主轨 trim/move（该段无绑定） | `["segments"]` | 现状不变 |
| 主轨 trim/move（有绑定） | `["segments","tracks","bindings"]` | 联动，单条快照 |
| 副轨 move/trim | `["tracks","bindings"]` | offset 重建 |
| 成对删除 | `["segments","tracks","bindings"]` | 单条原子 |
| 联动拆分 | `["segments","tracks","bindings"]` | 单条原子 |
| 副轨 SRT 导入 | `["tracks","bindings"]` | M11-2 现状 |
| lane 布局变更 | 不捕获 | 纯前端层（M4-1） |

**判定时机**：捕获层以**提交时**是否有绑定为准（乐观更新开始前前端可读当前 project 的 bindings）。

### M5-2: 副轨编辑 composable（新文件 `frontend/src/composables/useTrackEdit.ts`）

- **裁决**：不扩 `useSegmentEdit`（3.0.0 C2 教训：composable 膨胀）。新建，职责：副轨段选区、`updateTrackSegmentTime`（乐观更新 tracks 层 + 300ms 防抖提交 M2-2 + 失败回滚）、`flushPendingUpdates`。
- 防抖键：`${trackId}:${segmentId}:${field}`；失败回滚语义与 useSegmentEdit 一致（onProjectUpdate(prev)）。
- **验收**：`useTrackEdit.test.ts`——乐观更新/防抖合并/失败回滚/捕获层正确。

### M5-3: 原子性集成测试

`useUndoRedo.test.ts` 扩展：联动拆分 -> 单条 undo -> segments/tracks/bindings 三层同时回退且 `apply_undo` 收到三层 payload -> redo 对称 -> 全程 revision 单调（断言每次 patch.revision 严格递增）。布局状态变更前后 undo 栈深度不变（布局不入栈）。

---

## M6: 导出映射、副轨字幕与收尾（P3）

### M6-1: 副轨导出接入删除区间映射（`core/export_service.py`）

```
# 新统一入口（export_track_srt 保留为废弃包装：export_track_subtitle(..., fmt="srt", map_deletions=False)，
# 一个版本周期后删除）
def export_track_subtitle(
    track: dict, edits: list[dict], output_path: str, *,
    media_duration: float = 0.0,
    fmt: "srt" | "vtt" = "srt",
    map_deletions: bool = True,
) -> dict
```

- 映射复用**与主轨完全相同的四个内部函数**：`_get_confirmed_deletions` / `_compute_keep_ranges` / `_subtitle_survives_in_keep_ranges` / `_map_to_exported_timeline`（满足 R9.1"同一映射、实现一处"）。
- 幸存规则与主轨一致：整段落入 keep_ranges 才保留，跨边界整段丢弃 + lost 日志（对齐 export_srt:345-357 行为）。
- `map_deletions=False` 仅用于"原始时间戳副本"导出场景（旧 export_track_srt 语义）。

**双语合并**：新函数 `export_bilingual_subtitle(main_segments, track, bindings, edits, output_path, *, fmt="srt")`——主行 + 副行（副行仅取有 binding 的副段；无 binding 主段单行输出）；时间轴以主段映射后为准。

**输入（main.py `_handle_export_subtitle` payload 扩展）**：`track_id`（既有）、`format: "srt"|"vtt"`（缺省 srt）、`merge_bilingual: bool`（缺省 False）。前端 ExportPage 增对应选项。
**边界**：视频/音频导出零改动；`export_vtt` 主轨路径零改动。
**验收**：新 `tests/test_track_export.py`——删除区间完整覆盖副段（丢弃+lost 日志）/ 副段跨两段 keep-range（映射平移正确）/ 空删除集（时间不变）/ `map_deletions=False` 透传 / 双语合并行序与时间断言。

### M6-2: SubtitleOverlay 副轨字幕（`components/workspace/SubtitleOverlay.vue`）

- **输入 props 扩展**：`secondary?: { tracks: SubtitleTrack[]; bindings: TrackBinding[] } | null`、`showSecondary: boolean`。
- 查找：以 binding 建索引 `main_segment_id -> extension_segment`，当前主段激活时映射其副段文本；**无 binding 的副段不显示**（PRD R10.1）。渲染于主字幕下方，次级样式（小一号 + 降透明度）。
- 开关：`data/settings.json` 新增 `show_secondary_subtitle: bool = True`（`core/config.py` + SettingsModal general tab 一项）。localStorage 不用于此（与 lane 布局层区分：这是产品设置，不是窗口布局偏好）。
- **验收**：`SubtitleOverlay.test.ts` 扩展——绑定映射命中/未命中/开关关闭不渲染。

### M6-3: 文档收尾

- 竞品报告 v2 第一节顶部加过时声明块（指向 PRD §0.3 现状表与本 spec）。
- `docs/design-spec.md` 层级契约补"提升 owner 而非提升弹层"规则与 M4-4 播放头实例。
- `docs/PROJECT_SCHEMA.md`：补 `ProjectPatch.meta` 可选字段一行（唯一 schema 触碰点）。
- AGENTS.md 服务表补 `core/track_constraints.py` 一行。

---

## 交付顺序与合入门禁

```
P0   M1 + M2-1(重叠拒绝部分) —— 同批合入（红线：S2 先于前端约束落地会出现拖拽回跳）
     M3 前置测试就绪（mergeTracksInPlace 可先行入库，M2 联动未激活前无消费者）
P1   M4 全部（只读几何化；useTrackEdit 尚未接线，lane 拖拽此批只 emit 不提交）
P2   M5-1 -> M3 接线 -> M2-1(联动) -> M2-2 -> M2-3 -> M5-2/3   （顺序强制：性能门禁先行）
P3   M6-1 -> M6-2 -> M6-3
```

里程碑：beta.1 = P1；beta.2 = P2；RC = P3；随后 3.0.1 正式。

## 规模复核

前端：trackConstraints (~300) + merge (~120) + useLaneLayout (~120) + useTrackEdit (~150) + SegmentBlock (~250) + TrackLane 重写 (~200) + WaveformEditor 编排 (~150) + 测试 (~800)。后端：track_constraints.py (~200) + project_service 联动 (~180) + export (~120) + 测试 (~300)。总量与 PRD 估计一致。

## 验收总纲（门禁）

- **vitest**：M1 逐函数 / M3 引用恒等 + perf 断言 / M4 全组件 / M5 原子性——全绿。
- **pytest**：M2 全部拒绝与联动路径 / M6 导出映射——全绿；存量 `test_segment_sort_invariant.py` 13 例全绿（**P1-3 勘误**：其中 `test_moving_start_earlier_triggers_resort` 因 M2-1 重叠拒绝契约而演进——原"start 拖入邻居区间靠静默重排"的移动改为不重叠整段移动，测试意图不变。该测试原本锚定的恰是本版要消灭的静默重叠行为）。
- **性能**：M3 断言（apply p50 < 5ms、单遍扫描）；undo < 5ms 基线不回退；3.0.0 perf-baseline 各项不回退。
- **真机**：Windows WebView2 + macOS WKWebView——堆叠区 wheel/触控板（deltaMode 归一）、Alt 手势、trim 命中、播放头贯穿、成对删除与 undo。
- **工程**：`uv run ruff check .` 与 `bun run lint` 零问题；`core/events.py` / `events.ts` diff 为空（红线 M0-3.3 的机器可验形态）。

## 风险与回退

| 风险 | 触发信号 | 回退 |
|---|---|---|
| merge 引用失稳引发全列表重渲染 | perf 断言失败 | gate assertion 自动整体替换（正确性保底），修 merge 后再开性能门禁 |
| 隐式联动改变既有主轨编辑行为 | 存量编辑回归失败 | meta.linkage 置空 + 联动分支 feature flag（settings 一项），M2-1 第 4 步旁路 |
| reconcile 误删用户副段 | beta 反馈 | 单条 undo 完整回退（三层快照保证）；toast 计数可审计 |
| WKWebView 堆叠区手势异常 | 真机回归 | lane 指针处理统一走既有 wheel 归一层；必要时 lane 高度档位降级为固定值 |

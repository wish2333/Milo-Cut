# record-3.0.4-P3-3：lane 建段接线（M3-2，R3.2，X1）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-3`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-3　SPEC：M3-2（三处接线精确 diff 表 + 边界 + 验收）　PRD：R3.2 / X1 + §6（顺序约束：本步先于 M4-2 手势合入——同文件防冲突，M0-3）
> 断链考古：41a1ac4（v3.0.2 smoke fix 3rd round）声明了整条链但三处接线全部缺失——TrackLane `onLaneClick` 以 `props.buildMode` 门控却从未收到该 prop；WaveformRow `@create-at` 桥调 `createAtInTrack?.()` 可选调用静默 no-op；WaveformEditor 声明 `track-create` emit（:91）但无生产者。下游 `WorkspacePage.vue:1581 @track-create="handleTrackCreate"` → `handleAddTrackSegment`（快照 + add_track_segment + toast）自 41a1ac4 起孤儿，本步零改动直接兑现。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/waveform/WaveformEditor.vue` | 受控改点（两处用法追加绑定） | +4/-0 | ① multi 路径 WaveformRow 追加 `:build-mode` + `:create-at-in-track` 桥；③ basic 路径 TrackLane 追加 `:build-mode` + `@create-at` 桥（§2） |
| `frontend/src/components/waveform/WaveformRow.vue` | 受控改点（纯透传） | +1/-0 | ② TrackLane 用法追加 `:build-mode="buildMode"`（`buildMode` prop :78 既有，核实无需新增） |
| `frontend/src/components/workspace/TrackLane.vue` | **零改动** | 0/0 | `buildMode?: boolean` prop 声明 :26 既有（41a1ac4 已交付），onLaneClick / clamp01At / 事件面零触碰——SPEC「除非 prop 声明缺失才允许最小补声明」条款未触发 |
| `frontend/src/components/waveform/WaveformEditor.test.ts` | 新增用例（挂既有宿主） | +169/-0 | M3-2 describe 块 3 例（§3）；既有 45 例零改动 |
| `docs/3.0.4/record-3.0.4-P3-3.md`（本文）、`record-3.0.4.md` §1、`plan-v3.0.4.md` P3-3 | 文档 | — | 登记与勾销 |

后端 `core/`、`main.py`、`tests/`、`pywebvue/`：**零改动**。`WorkspacePage.vue` / `useWorkspaceActions.ts`（下游消费者）：**零改动**（门禁 R0-1 后端 diff 文件集与本步无关，§5）。

## 2. SPEC M3-2 三处接线逐条对照（照表施工）

### ① WaveformEditor multi 路径 WaveformRow 用法（原 :1108-1130）

追加两行（置于 `:update-track-time` 之后、`@seek` 之前）：

```html
:build-mode="buildMode"
:create-at-in-track="(tid: string, t: number) => emit('track-create', tid, t, Math.round((t + 0.5) * 100) / 100)"
```

- 0.5s 默认宽对齐 basic 建段先例 SegmentBlocksLayer.vue:165 `emit("add-segment", time, time + 0.5)`（核实原样）；`Math.round(... * 100) / 100` 与 TrackLane.onLaneClick 两位小数口径一致；
- `buildMode` = 编辑器本地 `ref(false)`（:280，`build-mode-toggle` :1010-1018 驱动），非 prop。

### ② WaveformRow 的 TrackLane 用法（原 :339-358）

追加一行：`:build-mode="buildMode"`（置于 `:update-time` 之后）。

- **核实结论：WaveformRow 自身 `buildMode` prop 已存在**（:78 `buildMode?: boolean`，M7-1 smoke feedback 交付，multi 空白建段已在用——:322 `:empty-area-mode="buildMode ? 'add' : ..."`），SPEC「若无则补一个纯透传 prop」条款未触发；
- `createAtInTrack` prop（:80）与 `@create-at` 桥（:357 `createAtInTrack?.(laneItem.track.id, time)`）均 41a1ac4 既有，本步仅从上游点亮。

### ③ WaveformEditor basic 路径 TrackLane 用法（原 :1218-1229）

追加两行：

```html
:build-mode="buildMode"
@create-at="(t: number) => emit('track-create', lane.trackId, t, Math.round((t + 0.5) * 100) / 100)"
```

- `lane.trackId` 来自既有 `v-for="lane in laneLayout.lanes"` 循环变量；trackId 绑定与同块 `@delete-track-segment` 等桥同构。

### 边界核对

- **TrackLane.onLaneClick 与 handleTrackCreate 既有逻辑零改动**（前者零触碰已由 numstat 0/0 证明；后者在 WorkspacePage/useWorkspaceActions，本步未触碰）；
- 不做 lane 形态范围标记（Q12 裁决维持）；lane 保持 click-only（TrackLane 的「drag-start」注释提及行为不扩）；
- 链路点亮后行为：建段模式 ON → 点击副轨 lane 空白 → `create-at(t)`（两位小数）→ `track-create(trackId, t, t+0.5)` → WorkspacePage.handleTrackCreate → 快照 + add_track_segment（clamp+重叠拒绝后端既有）+ toast——41a1ac4 提交描述「建段模式下点击副轨 lane 空白即在该轨新建 0.5s 字段」首次兑现。

## 3. 测试（挂既有宿主 WaveformEditor.test.ts，新增 describe 块 3 例）

脚手架照宿主惯例：multi 挂载照 M7-2（localStorage `ROW_LAYOUT_STORAGE_KEY` mode=multi + `clientHeight` mock 320）；basic 挂载照 BASIC lane menu 先例（默认 basic + `PLAYBACK_CLOCK_KEY` provide）；`getBoundingClientRect` 对 `[data-test="lane-blocks"]` 固定 600px 宽（ratio = clientX/600）。

| # | 用例 | 断言 |
|---|---|---|
| 1 | multi：`build-mode-toggle` 开启 → 点击 row 0 lane-blocks（clientX=300，row 窗口 0..10s，ratio 0.5） | `track-create` = `["en", 5, 5.5]`（经 WaveformRow createAtInTrack 函数 prop 全链） |
| 2 | basic：同上经 TrackLane `@create-at` 桥（basic 视窗默认 viewDuration=30s，ratio 0.5） | `track-create` = `["en", 15, 15.5]` |
| 3 | OFF 零回退：不开启建段模式，multi 与 basic 两挂载各点一次 lane-blocks | 两挂载 `track-create` 均 falsy |

- 用例 1 走真实 TrackLane DOM 点击（`@click.stop="onLaneClick"` 绑定于 `[data-test="lane-blocks"]`），覆盖 inject 行级 metrics → clamp01At → 两位小数舍入 → WaveformRow 桥 → 编辑器 emit 全链，非仅 props 驱动；
- 既有 45 例零改动（断言零删改，R0-3 白名单外命中 = 0）。

## 4. 勘误登记（非偏离，不产生额外 diff）

1. **SPEC/PLAN/任务书的 TrackLane 路径笔误**：多处引 `frontend/src/components/waveform/TrackLane.vue`，实际文件位于 `frontend/src/components/workspace/TrackLane.vue`（41a1ac4 stat 佐证）；按文件名 + :49-55 onLaneClick 锚点双重定位，无歧义。
2. **WorkspacePage `@track-create` 行号漂移**：任务书引 :1482，当前 `dev-3.0.4` 实际 :1581（P2 批次新增代码致漂移），消费语义不变，零改动。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**810 passed**（当期期望总数保持，后端零改动）
- ruff：0 problems
- vitest：**798 collected / 797 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，record-3.0.3 §5 遗留 #5 已登记环境例，门禁判定口径内；较 P3-2 基线 795 collected 净增 3 = 本步用例数，既有断言零删改）
- build：vue-tsc --noEmit + vite build 通过（built in 3.02s）；lint：eslint 0/0
- 红线：R0-1 后端 diff 文件集 ⊆ 白名单（全部为 P1/P2 已登记 hunk，本步零新增）；禁改面空；R0-2 events 双侧 1/1；R0-3 后端断言零删改；R0-3 前端断言白名单外零删改 = 0；dev.py/build.py 零改动

## 6. 偏离登记

无实质偏离。三处接线与 SPEC M3-2 精确 diff 表逐字一致；TrackLane 经核实 prop 声明已存在，零改动条款（SPEC 边界 + 红线）落实；0.5s 默认宽、两位小数舍入、`(tid: string, t: number)` / `(t: number)` 箭头参签名均照表。

## 7. 红线自证

- 本步改动文件集 = WaveformEditor.vue（两处用法追加绑定）/ WaveformRow.vue（build-mode 透传一行）/ WaveformEditor.test.ts（新增用例）/ 文档——TrackLane.vue、WorkspacePage.vue、useWorkspaceActions.ts 及其余前端文件零改动（`git diff dev-3.0.4 --numstat` 见 §1，无越界文件）；
- 既有 vitest 断言零删改（纯追加 +169/-0）；后端零改动；
- 顺序约束遵守：本步仅接线与测试，未触碰手势路由（M4-2 范围的 `handleRowEmptyGesture` / `emptyAreaMode` 等零接触）——X1 先于 M4-2 合入的可冲突面最小化。

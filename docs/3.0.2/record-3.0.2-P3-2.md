# record-3.0.2-P3-2: 行内指针交互（M5-3）

日期：2026-09-02　分支：`dev-3.0.2-p3-2`　合入：`dev-3.0.2`

## 交付范围（PLAN P3-2，SPEC M5-3）

| 交互 | 行为 | 实现落点 |
|---|---|---|
| 空点语义消解 | `emptyAreaMode` prop："add"（默认/basic）零变化；"seek"（multi）清选 + 定位 | `SegmentBlocksLayer.handleEmptyClick` 双分支 |
| 点击空白 | bounded 清选 + seek | seek 分支：清行内 `selectedBlockId` + `empty-press` 上行 → 编辑器 `clear-selection`（全局集合）+ scrub 机起点 |
| scrub | frozen unbounded + clamp[0,duration] + 32ms 节流 + 松手精确一次 | 编辑器 `startScrubGesture`（document mousemove/mouseup），发射 **set-time** |
| 双击空白 | 播放/暂停 | 层 `@dblclick.self` → 行 `toggle-play` → 编辑器 `toggle-play` → WorkspacePage `handleTogglePlay` |
| Ctrl+拖建段 | 预览停边界 + 占用检查 → add-segment 现有链路 | 编辑器 `startCreateGesture`：`boundsAtAnchor`（锚点邻缝）+ `constrainCueRangeToTrack`（窄缝 ok:false 拒绝）；预览矩形挂 multi-content（绿=合法/红=拒绝） |
| Shift+拖框选 | 跨行矩形相交 → 命中 id 并入全局选择 | 编辑器 `startMarqueeGesture` + `hitSegmentsInMarquee`（逐可视行 x→时间窗 × y 行带双判定）；`select-segments` 由 WorkspacePage **合并**进 `selectedSegmentIds` |

## 架构（M3-2 不变量维持）

- **行零跨事件状态**：`WaveformRow` 在空点按下时只做一件事——把当前 rect+span 冻结进编辑器传入的 `rowDrag` 单例（`useRowDragCapture`，P2-5 骨架首次真实消费），然后 `empty-gesture` 描述符上行。三台手势机（scrub/create/marquee）全在编辑器，document 级监听 + 统一 `beginDocumentGesture` 生命周期（onUp 先于 cleanup——精确末次 seek 需要冻结几何仍活着），卸载/切模兜底 `gestureCleanup?.()`。
- **手势路由**：plain → scrub；ctrl/meta → create；shift → marquee（happy-dom 丢修饰键已在测试 helper 强写实例属性）。
- **新事件**：编辑器 `toggle-play` / `select-segments` / `clear-selection`；层 `empty-press` / `empty-double-click`；行 `empty-gesture` / `toggle-play`。

## 裁决与登记

| # | 事项 | 裁决 |
|---|---|---|
| 1 | SPEC「32ms 节流 emit seek」的 seek 语义 | 实现为 **set-time**（`handleSetTime` = seekPlayback 不改播放态）——若走 `handleSeek` 每次 scrub 都会强制开播，违背 scrub 惯例；「seek」按 PRD 术语理解为播放头定位。回写 SPEC 备注 |
| 2 | scrubbing 抑制列表跟随 | `waveformScrubbing` 为编排层 ref 并 `defineExpose`；**现状 Timeline 无播放自动滚动**（仅选中/外链高亮滚动），无可抑制对象——列表侧消费随 M6-1 跟随三分落地（PLAN 勾销备注已登记） |
| 3 | 建段 snap | SPEC 未要求，create 预览不 snap（trim 才有 snap 链，M5-4）；占用检查语义 = `extensionRangeOverlapsNeighbors` 的「拒绝」分支 + `constrainCueRangeToTrack` 的「钳入缝隙」分支，按 M5-3 原文组合 |
| 4 | 框选合并 vs 替换 | 合并（并入），与字幕列表选择模式共用同一全局集合（M3-2 归属裁决）；退化矩形（shift 单击）为 no-op 不清选 |
| 5 | 普通按下即清全局选 | 「清选上行」落在空点 press 时刻（plain only）；ctrl/shift 修饰按下不清（建段/框选语境） |

## 测试（新增 10 例）

- 层 3 例（SegmentBlocksLayer.test）：add 默认与显式 "add" 空点 = add-segment 且无 empty-press；seek 空点 = 无 add-segment + bounded time(5) + 修饰键透传；双击仅 seek 模式发 empty-double-click。
- 编辑器 5 例（WaveformEditor.test，600px 行宽/130px stride 几何桩 + 发射型层 stub）：scrub 同步三连 move 仅首发（节流）+ 松手精确 [6,8] + waveformScrubbing 真假翻转 + clear-selection；双击 → toggle-play；Ctrl 建段预览 20%/30% + add-segment [2,5] + 卸除；**预览停边界**（[4,6] 段外钳 2..4 宽 20%）+ **窄缝拒绝**（0.05 缝 → 红框无发射）；**跨行框选**（行 0 拖至行 1 → 命中 a/b，c 不误伤）。
- 内核 2 例（useRowLayout.test）：`shouldEmitScrubSeek` 边界表（31.9 假/32 真/∞ 起点/自定义间隔）。

## 门禁（全绿）

pytest 708 ✓ / vitest 617 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓（零后端改动）

## 已知边界

- 行顶部 24px（badge 条，`top-6`）不属于层容器命中面，与 basic 单窗死区一致——非本步扩大；真机清单如反馈再收敛（登记待观察）。
- 框选拖拽中不自动滚动（spec 未要求，MAW 同款）；预留 M6 跟随机制统一处理。

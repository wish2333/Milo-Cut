# Record: P2-2 SegmentBlock 改造点 + WaveformRow 组件（Phase 2 / SPEC M3-2）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p2-2`（合入 `dev-3.0.2`）· 基点: P2-1 合入后

## 完成内容

### trackConstraints.ts（改动点④）

- 新增 `clampTimeToNeighbors(raw, edge, seg, segments)` 导出：从 SegmentBlock 私有 clampTime 迁移的内核实现（M2-1 单边邻居钳制语义不变，blocked 保边）；后端镜像评估——`core/track_constraints.py` 的消解逻辑走 `_apply_main_linkage` 通道，无此单边 trim clamp 的 Python 消费者，**仅前端导出**，按 PLAN P2-2 预案在 SPEC M3-2 登记偏差（避免死代码）

### SegmentBlock.vue 四改动点（SPEC M3-2）

1. `continuesFrom/continuesTo` 可选 props（默认 false）：延续侧内联 style 压制圆角（确定性覆盖 `rounded` 工具类，不破坏 `.rounded.border` 既有选择器契约）+ `continues-from/to` 标记类
2. `rowStart/rowEnd` 可选 props：`leftEdgeInRow/rightEdgeInRow` computed 门控手柄 v-if；行外边缘 mousedown 降级为 body select（行边界只管手柄可见性，钳制数学走内核不受行界——S7.8 前置）
3. `getTimeFromPointer` 可选注入：`pointerTime()` 封装（注入源 ?? metrics.getTimeFromX），onMove/onUp 全部走该源
4. clampTime 改为内核 `clampTimeToNeighbors` 直调

### SegmentBlocksLayer.vue（最小透传）

- 新增 `rowStart/rowEnd/getTimeFromPointer` 可选 props；`visibleBlocks` 派生每块 `continuesFrom/continuesTo`（rowStart/rowEnd 未定义 = basic 单窗行为零变化，旗标 undefined 不传）

### WaveformRow.vue（新组件）

- 行级 `createRowMetrics` provide（行作用域覆盖祖先注入）；**不重复 provide PLAYBACK_CLOCK_KEY**（M0-1.6 红线，PlayheadOverlay 经祖先链取单点时钟）
- 几何：`top/rowHeight/widthPercent` props 定位（行高变更 = 纯几何）；`data-row-index/start/end` 标记；`overflow-hidden` 视觉裁剪
- 行时间徽章（`formatTimeShort(start) → end`，mono 11px，pointer-events none）
- 组合 WaveformCanvas（z-0）/ TimeMarksLayer（z-1，seek 转 set-time 上行）/ SegmentBlocksLayer（z-2，**全轨 segments 数组**下传——跨行 trim 邻居依赖）
- 行级 PlayheadOverlay：`currentTime ∈ [rowStart, rowEnd)` 才渲染（R5.3）
- 行内 hover 预览线 + 时间标签（R5.8：行局部状态，仅本行渲染）+ `hover-time` emit 上行
- emits 全量转发矩阵：select-range/add-segment/delete-segment/seek-segment/split-segment/set-time/toast/trim-end/hover-time
- 零跨指针状态（M4-3 前提）：组件不持有拖拽几何

### 测试

- `WaveformRow.test.ts` 新增 17 例：几何定位与 data 标记、徽章（含末行钳 1:35）、行级播放头 [start,end) 门控与换行切换、跨行块裁剪数值 + 延续旗标双向、全轨数组透传、行内手柄规则（leftEdgeInRow/rightEdgeInRow）、getTimeFromPointer 注入/缺省、无祖先 metrics 独立挂载（适配器自给）、行窗外块过滤、hover 预览清理
- `SegmentBlock.test.ts` 扩展 2 例：注入 converter 驱动 trim 数值断言、行外边缘降级 select（行内边缘照常 trim）
- 既有 SegmentBlock 12 例 + 全量回归零改动通过

## 验证命令与实际输出

```
cd frontend && bun run test                       -> Test Files 44 passed / Tests 559 passed（540 + 19 新增）
cd frontend && bun run build                      -> ✓ vue-tsc + vite build
cd frontend && bun run lint                       -> 0 errors 0 warnings
```

## 实施裁决记录

- 延续侧去圆角用内联 style 而非 `rounded-l-none` 工具类：保持根类 `rounded border` 不变（既有测试选择器 + Tailwind 生成顺序不可控的双重保险）
- TimeMarksLayer 的 seek emit 在行内转为 `set-time` 上行（行无滚动/seek 职责，导航归编排层；P3 交互接线时统一消费）

## 未验证边界

- WaveformRow 尚无编排层消费者（P2-3 挂载）；peaks 仍每行 fetch（P2-4 修）；空点 add-segment 在 multi 下将上行使编辑器忽略（beta.1 已知临时行为，M5-3 换 emptyAreaMode）

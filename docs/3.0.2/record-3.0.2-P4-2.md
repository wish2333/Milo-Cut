# record-3.0.2-P4-2: 模式切换与持久化（M6-2/M6-3）

日期：2026-09-02　分支：`dev-3.0.2-p4-2`　合入：`dev-3.0.2`

## 交付范围（PLAN P4-2，SPEC M6-2/M6-3）

### 双向迁移（M6-2）

| 方向 | 公式 | 测试数值 |
|---|---|---|
| multi → basic | `metrics.scrollTo(scrollTopTime + spr/2)`（v3.0.1 居中语义） | scrollTop 376（scrollTopTime 20s）→ basic viewStart = 20+5−15 = **10.0s** |
| basic → multi | `revealTime(basic 视窗中心, center=true)`（REVEAL_BIAS→0.5 档） | viewStart 10 + 15 = 25s → row 2 → scrollTop **100** |

- 状态重置：`resetWheelBursts` / `gestureCleanup`（P3 已接）/ `lastFollowedRow = null`（双向都清）。
- multi 切入 reveal 的对象从「播放头」改为「basic 视窗中心」（M6-2 公式，覆盖 beta.1 的临时实现）。

### 持久化（M6-3，schema 一次定全）

- `RowLayoutState` 增 `scrollTopTime?: number`、`editorHeightPx?: number`——**本版 schema 冻结**，heightPx 只读默认（P5-1 接写入）。
- 写入时机：mode/spr/rowHeight 沿用变更即写；`scrollTopTime` 走 **300ms debounce**（`SCROLL_TOP_SAVE_DEBOUNCE_MS`，滚动停了才写，多段快速滚动合并为尾笔）。
- **卸载兜底直接写 storage**：unmount 时 composable 的 watcher 已被 Vue stop，经 state watch 的持久化不会再触发——`flushScrollTopSave` 同时写 state（一致性）与 storage（direct save）。编辑器 onUnmounted 调用。
- 读取：`normalizeState` 白名单扩展——scrollTopTime 须为有限非负数、editorHeightPx 须为有限正数，损坏即丢弃该字段（不进布局数学），核心三字段回退逻辑不变。
- 恢复：编辑器 onMounted（multi）`restorePersistedScroll` = `timeToScrollTop` 量化到行边界 + `Math.min(maxScrollTop)` 时长缩短钳制；工程重开即恢复浏览位置。

## 附带修复（pre-existing）

- controls 条 `<template v-if="isMulti">/<template v-else>` fragment 在 happy-dom 下卸载崩溃（`removeFragment` nextSibling of null：happy-dom 丢弃 Vue 的注释锚点节点）。真实浏览器从不受影响（beta.1 起真机模式切换正常），仅测试环境阻断模式切换用例。改用 `display:contents` 包裹 div（`class="contents"`），flex 布局逐像素等价。

## 测试（新增 8 例）

- 簿记 5 例（useRowLayout.test，全量 fake timers）：debounce 300ms 边界（299ms 未写/300ms 已写）；快速滚动三段合并为尾笔（10→20→30 只落 30）；flushScrollTopSave 立即落盘；扩展 schema round-trip（scrollTopTime 45.5 + editorHeightPx 480）；损坏可选字段丢弃（-7 / NaN → 字段消失、核心字段保留）。
- 编辑器 3 例（WaveformEditor.test）：双向迁移数值（376→"10.0s"→100，见上表）；重开恢复量化（scrollTopTime 25 → 260 = 行 2 边界）；卸载兜底（reveal 后未满 300ms 即卸载 → storage.scrollTopTime = 20）。
- 测试基建：Vue watcher 双层异步（scrollTopTime watch → state watch → storage）需要**两次 nextTick** 才落盘——簿记断言按此编排。

## 门禁（全绿）

pytest 708 ✓ / vitest 640 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

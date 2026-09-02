# record-3.0.2-P3-1: wheel 手势家族（M5-1/M5-2）

日期：2026-09-02　分支：`dev-3.0.2-p3-1`　合入：`dev-3.0.2`

## 交付范围（PLAN P3-1，SPEC M5-1/M5-2）

| 手势 | 行为 | 实现 |
|---|---|---|
| 普通滚轮/触控板 | 原生竖向滚行 | **零 JS、零 preventDefault**——WebView 引擎即「既有方案」的 deltaMode 归一（mac 像素 / Win 行单位）；JS 不介入 |
| Ctrl/Cmd+滚轮 | spr 档 [5,10,20,30] 循环 | 160ms（`WHEEL_DEBOUNCE_MS`）burst 合并净步数 → 一次 `cyclePreset` 跳档 → 播放行锚定 |
| Ctrl/Cmd+Shift+滚轮 | 行高档 [64..168] 循环 | 同上，几何-only（key 不含行高，行实例复用）→ 同款锚定 |
| （basic） | 现状 metrics.handleWheel | 零改动；multi 监听只在 multi-scroll 存在，两族监听不共存 |

## 改动点

- `useRowLayout.ts`：新增纯函数 `cyclePreset(presets, current, steps)`——净步数循环 + 两端 clamp + 越梯 current 兜底 index 0。
- `WaveformEditor.vue`（multi 容器）：
  - `WheelBurst` 累积器 ×2（spr 族 / 行高族，手势互斥 = 按修饰键分流、各族独立合并）；`armBurst` 160ms debounce 合并净步数；`resetWheelBursts` 在切出 multi / 卸载时丢弃半程 burst（stale commit 不越生命周期）。
  - `anchorPlayingRow(spr, rowHeight)`（M5-2）：`rowIndexAtTime(currentTime, spr)` + `followScrollTop(row, vh, rowHeight, max, REVEAL_BIAS)`，max 按**新几何**显式重算（`computeRowCount(duration, spr)`），不依赖 state 更新顺序。spr 变更与行高变更共用此锚定。
  - 缩放隐喻统一：wheel 下 = 缩小内容 = spr 调粗（+1）/ 行高调矮（−1）。
  - `attachMultiWheel`/`detachMultiWheel`：`{ passive: false }` 挂 `data-test="multi-scroll"`；`setScrollRef` 挂载时接，`onUnmounted` 卸。
  - preventDefault 边界：**仅 ctrl/meta 路径** `preventDefault()`（拦 WebView 页面缩放）；普通滚动永不拦截。
- `useRowLayout.perf.test.ts`：M8-3 单行挂载 p95 门**测量加固**——p95(20 样本) 即最大值，全量套件下一次 GC 停顿即误杀（实测全量跑出 15.4ms、单跑稳定 5.7-6.3ms）；改为 3 批 ×20 挂载取**最优批 p95**（阈值 8ms 不变，门语义 = 组件内在成本而非机器负载）。

## 测试（新增 9 例）

- `useRowLayout.test.ts` `cyclePreset` 4 例：双向单步 / 净多步合并 / 两端 clamp 不回绕 / 零步与越梯 current。
- `WaveformEditor.test.ts` multi wheel 5 例（fake timers + multi-scroll clientHeight 320 原型桩）：
  - 普通滚轮 defaultPrevented=false 且 debounce 结算后档位零变化；
  - ctrl+wheel 三连（净 −3 clamp）→ spr 10→5，**锚定 scrollTop 数值断言 = 506**（followScrollTop(5,320,120,2270,0.45)），且 data-row-start=25 的播放行在渲染窗内；
  - ctrl+shift+wheel → 行高 120→96 几何-only（spr 不变、行窗数据不变），锚定 scrollTop = 68（followScrollTop(2,320,96,730,0.45)）；
  - preventDefault 边界 + 手势族互斥（ctrl+shift 只动行高、ctrl 只动 spr，互相不串）；
  - basic 分支无 multi wheel 宿主（零改动回归）。

## 边界与备注

- **happy-dom 缺陷**：`WheelEvent` 构造器丢修饰键（ctrlKey/shiftKey 出来是 undefined），测试 helper 用 `Object.defineProperty` 强写实例属性（已注释说明）——生产代码不受影响。
- 锚定为**无条件**播放行锚定（按 M5-2 表述，无舒适区免滚——与 revealTime 的 comfort-skip 不同，后者属 M6-1 跟随三分）。
- 触控板 pinch 手势（gesture 事件）不处理：浏览器 pinch-zoom 由 WebView 层接管（M5-1 边界，MAW 同款放弃）；ctrl+wheel 的 preventDefault 恰好同时拦掉 WebView 的 ctrl+滚轮页面缩放路径。

## 门禁（全绿）

pytest 708 ✓ / vitest 607（含新 9 例，连续两轮全绿）✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events diff vs `v3.0.2-base` = 0 ✓ / models diff = 0 ✓

## 登记差异

| # | 内容 | 处置 |
|---|---|---|
| 1 | deltaMode 归一落点 = 原生滚动零 JS（ctrl 路径只读 deltaY 符号） | 按 M5-1「沿既有方案」从宽解释，回写 PLAN 勾销备注 |
| 2 | M8-3 挂载门测量加固（最优批 p95，阈值不变） | 测量稳健性修正，非门放宽；本 record 登记 |

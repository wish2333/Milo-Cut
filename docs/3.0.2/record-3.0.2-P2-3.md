# Record: P2-3 编排改造与虚拟化（Phase 2 / SPEC M4-1/M4-2 + M8-3 门禁）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p2-3`（合入 `dev-3.0.2`）· 基点: P2-2 合入后

## 完成内容

### WaveformEditor.vue 多行分支（M4-1）

- 接入 `useRowLayout(durationRef)`：mode/spr/rowHeight（localStorage `milocut:timeline-rows:v1`）、scrollTop/viewportHeight、visibleRows/contentHeight/maxScrollTop
- **basic 分支原样保留**：模板 v-else 切换，stack/lane/Playhead/ScrollbarStrip/连续缩放全部现状；wheel 监听生命周期改为 attach/detach 函数——multi 卸载 stack 时摘除、切回 basic 时 `nextTick` 重挂（修复模式往返后 basic 滚轮失效的隐患）
- multi 分支：`data-test="multi-scroll"` 容器（overflow-y-auto + overscroll-contain，beta.1 固定视口高 320px，P5-1 换 divider+持久化）+ `multi-content`（height = contentHeight）+ `v-for renderedRows` 渲染 WaveformRow
- 控件栏最小形态：模式 segmented（多行/聚焦）+ spr select + 行高 select（预设白名单来自内核常量）+ 中部「行 x–y / 共 N 行」信息
- 迷你总览条：占位注释（P4-3 实装）；ScrollbarStrip multi 下隐藏

### 虚拟化与重挂策略（M4-2）

- scroll → rAF 合帧（复用 createRafScheduler）→ scrollTop；ResizeObserver 喂 viewportHeight
- **行 key = `r{index}-{start}`**（start = i×spr）：spr 变更 → key 全变 → 全量重挂（适配器静态捕获前提）；rowHeight 不进 key → 仅 top/height prop 变化（几何-only keyed 复用）
- duration 缩短：watch maxScrollTop → scrollTop 钳制；程序化 scrollTop 写回容器（差值 >0.5px 才写，避免回环；P4-1 加显式 autoScrollTarget 抑制）
- 模式切换：multi 切入 `revealTime(currentTime, center)` 锚定播放行；P1 阶段 spr 变更 scrollTop 跳变仍为已知临时行为（M5-2 播放行锚定 P3 落地）
- 末行宽度：`rowWidthPercent(index)` 用内核 `lastRowWidthPercent`

### M8-3 性能断言（本步起为合入门禁）

- 新建 `useRowLayout.perf.test.ts` 3 例：`visibleRowWindow` p50 = 0.0002ms（<1ms）、composable 链 p50 = 0.0015ms（<1ms）、单行挂载 p95 = 5.9ms（<8ms；3 次预热排除 JIT 冷启动，1167 段全轨数组）
- `vite.config.ts` test 块加 `fileParallelism: false`：perf 门禁是墙钟断言，文件级并行 worker 的 CPU 争抢会翻转结果（实测单文件绿/全量红）；套件秒级，串行文件成本可忽略。**附带效果**：projectPatch.perf / undoScale.perf 同获稳定

### WaveformEditor.test.ts 既有用例

- 全量零改动通过（basic 分支行为红线 ✓）

## 验证命令与实际输出

```
cd frontend && bun run test          -> Test Files 45 passed / Tests 562 passed（两轮复跑稳定）
cd frontend && bun run build         -> ✓ vue-tsc + vite build
cd frontend && bun run lint          -> 0 errors 0 warnings
[perf] visibleRowWindow x200: p50=0.0002ms
[perf] rowLayout.visibleRows chain x100: p50=0.0014ms
[perf] WaveformRow mount x20 (1167 segs, warmed): p95=5.9ms
```

## 实施裁决记录

- `renderedRows` 在编排层计算行描述符（index/start/top/key），WaveformRow 只收几何 props——组件零跨指针状态、编排层单点持有行几何（P3 原则的 M4 落实面）
- MULTI_VIEWPORT_HEIGHT = 320 常量：P5-1 的 divider + localStorage（schema 已含 editorHeightPx）替换
- 多行模式下空点 add-segment 仍上行使编辑器转发（与 basic 行为一致）；M5-3 的 emptyAreaMode 在 P3-2 消解语义

## 未验证边界

- 千段滚动/播放帧率真机体感（beta.1 冒烟清单 A 项）；peaks 每行 fetch 待 P2-4 消解

## Beta.1 冒烟反馈修复（2026-09-02）

- **用户发现**：多行模式切换每行秒数档位后，第 0 行不刷新，滚出视口再滚回才更新
- **根因**：行 key 为 `r{index}-{start}`，第 0 行 start = 0×spr 恒为 0，key 对 spr 不变量 → Vue 复用旧实例 → 静态捕获旧 spr 的行适配器（M3-1 设计前提是 spr 变更全量重挂）继续渲染；其余行 start 随 spr 变化故正常
- **修复**：key 显式嵌入 spr（`r{index}-{start}@{spr}`），任何 spr 档位切换都强制全行重挂——恢复 M4-2「spr 变更 → 全量重挂」的完整语义
- **回归测试**：WaveformEditor.test.ts 新增 multi 分支 describe（3 例，localStorage 播种 multi 模式）：行窗标记、**row 0 stale-adapter 回归**（经 WaveformRow defineExpose(metrics) 断言适配器 viewDuration 随档位变化——已验证旧 key 下该测试失败复现症状）、rowHeight 变更几何-only
- 门禁：vitest 598 全绿（595 + 3）/ build ✓ / lint 0

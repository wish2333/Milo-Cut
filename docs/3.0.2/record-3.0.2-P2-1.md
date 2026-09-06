# Record: P2-1 行级 metrics 适配器（Phase 2 / SPEC M3-1）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p2-1`（合入 `dev-3.0.2`）· 基点: P1-1 合入后

## 完成内容

- `useTimelineMetrics.ts`：仅将 `NICE_STEPS` 抽为共享导出（附注释），零行为变化，无 mode 分支
- 新建 `frontend/src/composables/rowMetrics.ts` `createRowMetrics(rowIndex, duration, currentTime, secondsPerRow, containerRef)`：
  - **重算组**：`viewStart/viewDuration`（静态捕获行窗 computed）、`viewEnd = min(rowStart+spr, duration)`（末行语义）、`timeMarks/minorTimeMarks`（共享 NICE_STEPS 阶梯 + 行实例独立 step 缓存）、`getTimeFromX`（行窗闭包）
  - **直通组**：`duration` / `containerRef` 原样透传（toBe 级断言锚定）
  - **形式组**：`timeToPercent/percentToPixels/playheadPercent/playheadVisible`（行窗语义实现：可见性 [start,end)）、`thumbLeft/thumbWidth`（行窗语义，无消费方）
  - **no-op 组**：`clampViewStart/scrollTo/zoomAt/handleWheel/ensurePlayheadInView/maybeFollowPlayhead`（一次性 DEV warn；handleWheel 不 preventDefault——原生滚动归 multi 容器，M5-1）
  - **watch 零注册**：适配器不调用 `watch()`；测试以内建 dep 引用不增长锚定
- `env.d.ts` 补 `ImportMetaEnv.DEV?: boolean` 声明（项目未引 vite/client 类型，vite 内建名补齐）

## 实施裁决记录（PRD 回写候选）

- 行内刻度目标数 = **6**（basic 单窗为 15）：PRD R5.4 示例「5s 行 → 1s tick、30s 行 → 5s tick」只有 target≈6 才成立（5/6→1、30/6→5）；NICE_STEPS 阶梯本体共享同源（SPEC M3-1 字面为「复用 NICE_STEPS」而非复用目标数）。差异登记：P5-3 PRD 回写时在 R5.5/R5.4 补注「行内刻度密度 = 6 目标（R5.4 示例的成立条件）」
- 行首对齐刻度包含 t=0（`ceil(rowStart/step)*step` 与 basic 在 viewStart 对齐时行为一致，且与行首时间徽章呼应）

## 验证命令与实际输出

```
cd frontend && bun run test                                  -> Test Files 43 passed / Tests 540 passed（523 + 17 新增）
cd frontend && bun run test src/composables/useTimelineMetrics.test.ts -> 全绿（既有 20 例零改动）
cd frontend && bun run build                                 -> ✓ vue-tsc + vite build
cd frontend && bun run lint                                  -> 0 errors 0 warnings
```

新增用例锚点：行窗映射/末行钳制、computed 形式（playheadPercent 作为 watch source 触发回调 + isRef 断言）、[start,end) 可见性、R5.4 刻度示例、跨行相位偏移、末行刻度止于钳制 viewEnd、缓存命中（同引用）、空行无刻度、getTimeFromX/timeToPercent/percentToPixels 数值、no-op 不抛 + 单次 warn、形式组行窗语义

## 未验证边界

- 适配器实例由 WaveformRow 挂载消费（P2-2），本步为独立验收；spr 变更静态捕获前提（全量重挂）在 P2-3 编排层落地

# Record: P1-1 前端约束函数族（Phase 1）

> 日期: 2026-08-31 · 分支: `p1/p1-1-track-constraints` -> `dev-3.0.1`

## 完成内容

- 新建 `frontend/src/utils/trackConstraints.ts`（~340 行）：`MIN_SEGMENT_DURATION`/`SNAP_STEP` 常量真源、`snapToStep`、`getTrackNeighborBounds`、`constrainCueRangeToTrack`、`clampExtensionRange`、`extensionRangeOverlapsNeighbors`、`reconcileExtensionTrack`、`syncBoundExtensionForMain`、`rebuildBindingOffsets`、`constrainBoundExtensionPanelEdit`
- 新建 `trackConstraints.test.ts`：54 边界用例 + 模块纯性测试（`?raw` 扫描 import，禁 vue/bridge/相对导入）
- `SegmentBlocksLayer.vue` 切换共享常量：删除本地 `MIN_SEGMENT_DURATION` 硬编码；`snapToFrame` 委托 `snapToStep`（与 `Math.round(t*100)/100` 位级一致，测试锚定）
- `env.d.ts` 补 Vite `?raw` 模块声明

## SPEC 勘误（同步回写 spec M1-3）

- `reconcileExtensionTrack` 输出**去掉** `unboundBindingIds`——函数不持有 bindings 信息，解绑由调用方按 1:1 模型从 `removedIds` 推导（removed 段 == 解绑 binding）；counters.unbound 保留（恒等于 removed）。
- `constrainCueRangeToTrack` 平移分支语义精化：dur 取**原始宽度**（不按缝 cap），"贴前驱 -> 贴后继 -> cap 到缝"三级回退；数学上贴后继仅在防御路径可达（贴前驱溢出 ⟺ dur > 缝宽 ⟺ 贴后继必溢出），分支保留与 MAW 结构对齐。

## 验证命令与实际输出

```
cd frontend && bun run test      -> Test Files 35 passed, Tests 397 passed（含 54 新用例；SegmentBlocksLayer.test.ts 断言零改动全绿）
cd frontend && bun run build     -> vue-tsc + vite build 通过
grep 本地常量残留                 -> 仅注释行，零硬编码
```

## 未验证边界

- 纯函数无 UI 接线（按计划，P1-3 才接 trim 路径）；`constrainBoundExtensionPanelEdit` 为 M1-4 备用移植，本版无交互入口

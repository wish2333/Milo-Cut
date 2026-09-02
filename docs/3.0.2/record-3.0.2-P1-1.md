# Record: P1-1 useRowLayout 纯函数层（Phase 1 / SPEC M2 / S4）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p1-1`（合入 `dev-3.0.2`）· 基点: Phase 0.5 退出后

## 完成内容

- 新建 `frontend/src/composables/useRowLayout.ts`：
  - **常量单一真源（M2-1/R4.6）**：`SECONDS_PER_ROW_PRESETS [5,10,20,30]` / `ROW_HEIGHT_PRESETS [64,80,96,120,144,168]` / 默认值 / `ROW_GAP 10` / `ROW_BUFFER 2` / `MANUAL_FOLLOW_COOLDOWN_MS 3000` / `WHEEL_DEBOUNCE_MS 160` / `SCRUB_SEEK_INTERVAL_MS 32` / `FOLLOW_BIAS 0.35` / `REVEAL_BIAS 0.45` / `ROW_LAYOUT_STORAGE_KEY "milocut:timeline-rows:v1"`
  - **纯函数组（M2-2，模块级、零响应式依赖）**：`computeRowCount`（空时长→1，spr≤0 抛错）、`rowSpanAt`（越界抛错，末行钳 duration）、`lastRowWidthPercent`（整行→100）、`strideOf`、`visibleRowWindow`（±ROW_BUFFER，退化视口→缓冲行）、`scrollTopToTime` / `timeToScrollTop`（floor 双向量化，刻意非互逆——测试锚定）、`rowIndexAtTime`、`comfortInset`（20% 钳 [48,120]）、`isRowInComfortZone`（边界 >=/<= 含）、`followScrollTop`（bias 钳 [0,max]）、`timeFromPointerInRow`（P4 双映射：bounded 钳 [0,1] / unbounded 不钳；width≤0 抛错）
  - **持久化助手（M6-3 schema 首段）**：`load/saveRowLayoutState`（注入式 storage 参数对位 useLaneLayout 先例；损坏 JSON 回退默认；白名单归一化非预设值）
  - **composable 壳（M2-3）**：`useRowLayout(duration)` —— state/scrollTop/viewportHeight refs + rowCount/contentHeight/maxScrollTop/visibleRows/scrollTopTime computeds + 白名单守卫 setter 三件 + `revealTime`（舒适区免滚 + center 切入居中 / 跳转 REVEAL_BIAS）+ `isRowVisibleInComfortZone`；state 变更即写 localStorage（scrollTopTime/editorHeightPx 持久化在 P4-2/P5-1 并入）
  - **裁决落实**：kernel 几何无 mode 门控（P1 rows 是派生几何；basic 分支不消费这些成员，编排层 M4-1 门控）——实施中修正了初稿把 contentHeight/visibleRows 绑定 mode 的做法

- 新建 `useRowLayout.test.ts`（51 例）：逐函数边界表（含 0/负时长、spr≤0/NaN/∞ 抛错、越界索引、边界相等、1e9 scrollTop 窗口不倒挂）、MAW 对位（390px→78px）、floor 非互逆锚定、秒单位语义、双映射 bounded/unbounded 对偶、持久化 round-trip/损坏回退/白名单归一、composable 壳派生与 revealTime 钳制、模块纯性（纯函数区脱离响应式环境直调）

## 验证命令与实际输出

```
cd frontend && bun run test                      -> Test Files 42 passed / Tests 523 passed（472 + 51 新增）
cd frontend && bun run build                     -> ✓ vue-tsc + vite build
cd frontend && bun run lint                      -> 0 errors 0 warnings
```

## 实施偏差记录

- 初版测试暴露 happy-dom 真实 localStorage 跨用例污染（壳的持久化走全局存储）——composable 测试组 beforeEach 清理；与 useTrackEdit 的定时器卫生同类问题，记录在案
- `revealTime(time, center)` 的 center 语义在 P1 先落实为「居中 bias 0.5」，P4-1 跟随三分落地时若需调整以该步为准

## 未验证边界

- 无 UI，无需冒烟；性能断言（M8-3：visibleRows p50 < 1ms）在 P2-3 创建门禁时补挂

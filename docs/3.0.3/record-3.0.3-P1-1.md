# v3.0.3 P1-1 记录：track 选择器与数据源（SPEC M1-1 / R1.1）

> 日期：2026-09　分支：`dev-3.0.3`　基准：`v3.0.3-base`

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/composables/useListTrackSelector.ts` | **新增**。选择器视图态：`activeListTrackId`（null = 主轨）+ `selectTrack` + `options`（名称+段数）+ `listSegments` 单一数据源 computed + 删轨回退 watch |
| `frontend/src/composables/useListTrackSelector.test.ts` | **新增**。12 用例（见下） |
| `frontend/src/pages/WorkspacePage.vue` | 消费 composable（约 +12 行）：`useListTrackSelector(activeTracks, mergedSegments)`；Timeline 传入 `:segments="listSegments"` / `:tracks` / `:active-track-id` / `@select-track` |
| `frontend/src/components/workspace/Timeline.vue` | 新 props `tracks?: ListTrackOption[]` / `activeTrackId?: string \| null`，新 emit `select-track`；头部 segmented 切换控件（款式沿 3.0.2 控件栏 mode-switch）；无副轨时控件不渲染 |

## 实现要点 / 裁决

- **数据源单一**：`resolveListSegments(null) === mergedSegments`（引用不变，零拷贝零重排——"主轨分支零 diff"在此层锁定）；副轨 id → 该轨 `segments`。不建第二套行渲染，P1-1 阶段副轨数据流经既有行组件（P1-2 增副轨分支渲染）。
- **composable 落点裁决**：SPEC M1-1 写明 ref 建于 WorkspacePage；本实现以 `useListTrackSelector` 承载（WorkspacePage 仅接线），理由：往返/回退行为可在 reactive 层被 vitest 直接断言（WorkspacePage 无既有测试挂载通路），与 3.0.2 useLaneLayout 同模式；红线不受影响（视图态、零 patch、零持久化）。
- **删轨回退 watch 形态裁决**：多源 `watch([activeListTrackId, tracks])` 而非单 getter——单 getter 连续两次 flush 解析值相等（null → null）时回调被 Vue 跳过，会吞掉一次必要纠偏（测试实际踩中后修正）。回退覆盖：删当前轨、切换时间线、切换工程三种 tracks 集合变化。
- **样式**：segmented 沿 WaveformEditor 控件栏 mode-switch 既有款（`rounded border` 容器 + 选中 `bg-gray-700 text-white`），副轨项含名称（截断 80px）+ 段数徽章。

## 测试（新增 17，既有未动）

- composable（12）：options 构建（名称回退 id）、单一数据源（主轨引用恒等 / 副轨 / 未知 id 空数组）、回退纯函数 3 例、reactive 8 例——默认主轨零 diff、往返无残留、跨轨直切、删轨回退、时间线切换回退、无关轨变更保持、options 联动段数。
- Timeline（5）：无 tracks 不渲染控件（主轨零 diff）、主轨+每轨条目+计数徽章、默认/切换 active 款、click 发射 `select-track` payload（id / null 往返）。

## 门禁（本步实际输出）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **716 passed** in 6.33s ✅ |
| vitest 全量 | **686 passed / 1 failed**（687 总数；唯一失败仍为 P0-1 已登记的 happy-dom 挂载墙钟环境例，失败集合未扩大）✅ |
| `vue-tsc --noEmit` + `vite build` | 0 错误，built in 3.14s ✅ |
| eslint | 0 errors 0 warnings ✅ |
| `uv run ruff check .` | All checks passed! ✅ |
| `git diff core/events.py frontend/src/utils/events.ts core/models.py main.py core/project_service.py` | **空** ✅（红线达标） |

## 未验证边界

- WorkspacePage 接线（props/emit 通路）未做组件级挂载测试——依赖 composable 层断言 + beta.1 双平台冒烟合并验证（PLAN P1 末 ★ 节点）。
- 副轨行在 P1-1 暂以主轨行组件渲染（编辑/状态列语义属 P1-2/P1-3 范围），本步不做主轨交互验证外的手工冒烟。

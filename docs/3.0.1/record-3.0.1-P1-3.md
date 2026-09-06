# Record: P1-3 重叠拒绝 + trim 前端接线（Phase 1）

> 日期: 2026-09-01 · 分支: `p1/p1-3-overlap-rejection` -> `dev-3.0.1`

## 完成内容

- `core/project_service.py:update_segment`：
  - `track_` 命名空间 id 显式拒绝并引导至 `update_track_segment`（校验先于一切，含空 updates）
  - start/end 变更时同轨重叠显式拒绝（排除自身、`OVERLAP_EPSILON = 1e-6` 贴合放行），错误信息含双方段 id 与区间
  - text-only 更新跳过重叠检查（几何未动）
- `core/track_constraints.py`：新增公共常量 `OVERLAP_EPSILON`（M2 写入通道共用容差）
- `SegmentBlocksLayer.vue:clampTime` 邻居接线：trim 限定在「前驱 end / 后继 start」合法域内；域为空（缝隙 < min）时 edge 原地不动；onUp 采纳 snap 后**二次 clamp**（防 0.01 snap 半步越界撞后端拒绝）

## 实施偏差（SPEC M2-1 接线方式）

- SPEC P1-3 写"clampTime 调 `constrainCueRangeToTrack`"。实施改为**一维单边 clamp**（`getTrackNeighborBounds` + clamp）：trim 是单边交互，区间平移语义会把整段滑动（trim 不应移动段身）；`constrainCueRangeToTrack` 的平移语义保留给 P2 副轨整体 move。合规目标不变——trim 提交永不撞后端拒绝。

## 存量测试演进（1 例，已获 SPEC 勘误）

- `test_segment_sort_invariant.py::test_moving_start_earlier_triggers_resort`：原用例把 c 的 start 拖入 a 的区间、靠静默重排通过——恰是 M2-1 消灭的行为。改为不重叠整段移动（start+end 同改），测试意图（移动触发重排序）不变。

## 验证命令与实际输出

```
uv run pytest tests/test_track_linkage.py -> 12 passed（拒绝 7 / 放行 4 / 引导 2 组）
uv run pytest                             -> 663 passed（651 + 12）
uv run ruff check .                       -> All checks passed（全仓）
cd frontend && bun run test               -> 397 passed
cd frontend && bun run build              -> vue-tsc + vite build 通过
```

## 未验证边界

- 手工拖拽手感（挤压邻居时的拒动反馈）待真机冒烟——已并入 beta.1 冒烟清单第 3 项
- 倒挂区间（start > end）不判重叠：既有病态容忍，不在本步扩大战线（sort invariant 兜底重排）

# Record: P1-2 后端约束内核镜像（Phase 1）

> 日期: 2026-09-01 · 分支: `p1/p1-2-track-constraints-backend` -> `dev-3.0.1`

## 完成内容

- 新建 `core/track_constraints.py`：`snap_to_step`、`get_track_neighbor_bounds`、`constrain_cue_range_to_track`、`clamp_extension_range`、`overlaps_neighbors`、`reconcile_extension_track`、`sync_bound_extension_for_main`、`rebuild_binding_offsets`、`constrain_bound_extension_panel_edit`——与 TS 内核逐条语义对齐；常量 `MIN_SEGMENT_DURATION = 0.1` 双侧锚定
- 新建 `tests/test_track_constraints.py`：53 用例镜像前端边界用例表

## 实施发现（跨语言语义差异，已双侧消解）

- **Python `round()` 是 banker's rounding，JS `Math.round` 是 half-up**：`12.345 * 100` 恰为精确 tie `1234.5`，Python 给 1234、JS 给 1235。`snap_to_step`/`_round3` 统一采用 `floor(x + 0.5)` 消除差异；测试参考实现同步改为 JS 语义并注释说明。
- 该差异若不消解，P2 联动编辑中前端乐观值与后端终审值可能因尾数 tie 不一致而互相覆盖。

## 验证命令与实际输出

```
uv run pytest tests/test_track_constraints.py -> 53 passed
uv run pytest                                 -> 651 passed in 4.59s（全量，基线 598 + 53）
uv run ruff check core/track_constraints.py tests/test_track_constraints.py -> All checks passed
cd frontend && bun run test                   -> 397 passed（前端不受影响）
```

## 未验证边界

- `constrain_cue_range_to_track` 尚无生产调用方（P1-3 接线 trim 路径）；reconcile/sync 由 P2 联动激活

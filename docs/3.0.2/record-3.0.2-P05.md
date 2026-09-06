# Record: Phase 0.5 汇总 —— 3.0.1 三缺陷收口（P05-1/P05-2/P05-3）

> 日期: 2026-09-02 · 分支: `dev-3.0.2`（merge 前三短分支：`dev-3.0.2-p05-1/-2/-3`）
> 分支命名偏差：PLAN 的 `dev-3.0.2/<step-id>` 与常驻分支 `dev-3.0.2` git ref 互斥，全程改用 `dev-3.0.2-<step-id>`

## 三缺陷闭环证据

| 缺陷（开发报告 §2.5） | 修复 | 契约锚定 | record |
|---|---|---|---|
| S1 副轨编辑面断链（TrackLane 未下传 updateTime） | `TrackLane.vue` 模板下传 `:update-time`（v3.0.1 M5-2 预留语义激活） | TrackLane.test 双路径 + useTrackEdit.test 11 例（乐观/防抖/回滚/捕获层） | record-3.0.2-P05-1.md |
| S2 联动 patch 丢层（update_segment 丢弃消解 tracks/bindings） | 联动分支 patch 携带 `tracks`+`bindings` 全量数组，`meta.linkage` 不变 | `TestLinkagePatchCarriesLayers` 6 例 + 前端挤压可见集成 + S2 联动 patch apply p50 门禁（0.214ms < 5ms） | record-3.0.2-P05-2.md |
| S3 撤销捕获层不符 M5-1 映射表 | 三类真实调用点谓词化捕获（绑定段三层/四层，无绑定维持现状）+ 副轨导入无条件两层 | undoLinkageCapture.test 4 例（三层原子 undo/redo 对称/revision 单调/谓词双路径） | record-3.0.2-P05-3.md |

## 附带清理（S3/R3.5）

- `export_track_srt` 废弃包装删除：core/ 零引用；`tests/test_track_export.py`、`tests/test_tracks_contract.py`、`core/export_service.py` docstring、`docs/PROJECT_SCHEMA.md:68` 全部同步（grep 仅剩移除声明注释与 hasattr 锁定断言）

## Phase 0.5 退出检查（合入 dev-3.0.2 @ d3fe705 后实测）

| 门禁 | 结果 |
|---|---|
| `uv run pytest` | 全绿（基线 702 + P0.5 新增：TrackLane 2 / useTrackEdit 11 / linkage 契约 6 / track_export 改造 1 / tracks_contract 改造 0 净增） |
| `cd frontend && bun run test` | Test Files 41 / **Tests 472 passed**（基线 453 + 新增 19：useTrackEdit 11 + TrackLane 2 + projectPatch 集成 1 + projectPatch.perf 1 + undoLinkageCapture 4） |
| `cd frontend && bun run build` | ✓ vue-tsc + vite build |
| `cd frontend && bun run lint` | 0 errors 0 warnings |
| `uv run ruff check .` | All checks passed! |
| `projectPatch.perf` 门禁（P05-2 起） | 全层 0.234ms / S2 联动 0.214ms（< 5ms） |
| `git diff v3.0.2-base -- core/events.py frontend/src/utils/events.ts core/models.py` | **空**（红线 M0-1.2 + S2/S3 不动模型 ✓） |

## 手工冒烟（三项，待用户协助 ★）

1. 副轨段 trim 可拖、邻居 blocked 拒动、防抖提交无回跳、失败回滚
2. 主轨 trim 挤压副段后副轨 lane 即时更新（无需其他操作触发）
3. 绑定段 trim → undo → 三层同时回退且无 stale patch

> 三项的链路逻辑已由 vitest 覆盖（useTrackEdit / projectPatch 集成 / undoLinkageCapture）；真机 UI 拖拽冒烟合并到 Phase 2 末（beta.1）★ 节点一并执行，届时若发现回退再回本批修。

## 测试计数对账

- pytest：702 → 710+（全绿；PLAN 门禁 ≥702 且新增全绿 ✓）
- vitest：453 → 472（+19，全部为 P0.5 新增；现有 453 断言零改动全绿 ✓，basic 模式零行为变化红线 ✓）

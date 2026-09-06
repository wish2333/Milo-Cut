# Record: P05-3 捕获层对齐与清理（Phase 0.5 / SPEC M1-3 / S3）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p05-3`（合入 `dev-3.0.2`）· 基点: P05-2 合入后

## 完成内容

### 捕获层对齐（R3.1/R3.2/R3.3，映射表见 SPEC M1-3）

- `useSegmentEdit.ts`：`updateSegmentTime` 谓词捕获——`segmentHasBinding(prev, segmentId)`（查活动时间线 `transcript.bindings` 的 `main_segment_id`，不新增数据通道）为真时捕获 `["segments","tracks","bindings"]`，否则维持 `["segments"]`
- `useEdit.ts`：`splitSegment` / `deleteSegment` 谓词捕获——`segmentIsBound(segmentId)` 为真时捕获 `["segments","edits","tracks","bindings"]`，否则维持 `["segments","edits"]`
- `useWorkspaceActions.ts`：`handleImportSrtAsTrack` 提交前无条件 `pushSnapshot(["tracks","bindings"], "导入副轨")`（导入必然产生两层），删除「Not undoable this version」过时注释

### 清理（R3.5，export_track_srt 全量同步清理）

- `core/export_service.py`：删除 `export_track_srt` 废弃包装；`export_track_subtitle` docstring 中 legacy 引用文字移除
- `tests/test_track_export.py`：import 移除；legacy wrapper 用例改为 `test_legacy_srt_wrapper_removed`（hasattr 负断言锁定移除）；原时间戳语义由既有 `test_map_deletions_false_passes_through`（`map_deletions=False`）覆盖
- `tests/test_tracks_contract.py`：`TestExportTrackSrt` 改造为 `TestExportTrackOriginalTimestamps`——用例改走 `export_track_subtitle(map_deletions=False)`，保留 silence 行过滤的唯一覆盖
- `docs/PROJECT_SCHEMA.md:68`：副轨导出路径文档改为 `export_track_subtitle`（含删除映射语义与 v3.0.2 移除注记）

### 集成测试（R3.4）

- 新建 `frontend/src/composables/undoLinkageCapture.test.ts`（4 例），测试接线完整镜像生产链路（可写 computed setter → `applyProjectResponse` → `noteRevision`）：
  1. 绑定段 trim（真实 `useSegmentEdit` 调用点）→ 捕获记录恰含三层 → undo 三层同回退（segments/tracks/bindings 数值逐一断言）→ redo 对称 → `apply_undo` 基准 revision 为最新（无 stale patch）→ revision 全程单调 2→3→4
  2. 无绑定段 trim → 捕获仅 `["segments"]`（现状不变）
  3. `useEdit.splitSegment`：绑定目标四层 / 无绑定目标两层
  4. `useEdit.deleteSegment`：绑定段级联四层 / 无绑定两层

## 验证命令与实际输出

```
uv run pytest                                    -> 全绿
uv run ruff check core/export_service.py tests/test_track_export.py tests/test_tracks_contract.py -> All checks passed!
cd frontend && bun run test                      -> Test Files 41 passed / Tests 472 passed（468 + 4 新增）
cd frontend && bun run build                     -> ✓ built in 815ms
cd frontend && bun run lint                      -> 0 errors 0 warnings
grep -rn export_track_srt core/ tests/ main.py   -> 零功能性引用（仅移除声明注释与 hasattr 锁定断言；core/ 完全无引用）
```

## 判定口径记录

- R3.5 验收「grep 无残留」按**功能性引用**（import/调用）判定：`test_legacy_srt_wrapper_removed` 的 hasattr 负断言与注释刻意包含该字符串以锁定移除，属验收产物而非残留
- 集成测试中 -1 revision 条目为乐观全量 Project 应用（无 revision 字段），符合 App.vue 既有处理语义

## 未验证边界 / 待冒烟

- 联动 undo 原子性真机冒烟（副轨 trim / 联动即时显示 / 联动 undo）在 Phase 0.5 退出检查合并执行

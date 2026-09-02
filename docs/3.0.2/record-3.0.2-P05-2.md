# Record: P05-2 联动 patch 带层（Phase 0.5 / SPEC M1-2 / S2）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p05-2`（合入 `dev-3.0.2`）· 基点: P05-1 合入后

## 完成内容

- `core/project_service.py` `update_segment` 联动分支（原 :1345-1347）：`_tracks, _bindings` 丢弃改为 `patch_kwargs["tracks"]/["bindings"]` 携带消解后全量数组；`meta.linkage` 计数语义不变；`_revision` 单调不受影响（走既有 `_success_patch` → `_next_revision`）
- Scope 核查：`split_segment` 的联动路径（:1960 附近）已正确带层（`test_split_patch_carries_three_layers` 既有锚定），`update_segment` 是唯一丢层点——与 SPEC M1-2 的范围判断一致
- `tests/test_track_linkage.py` 新增 `TestLinkagePatchCarriesLayers` 契约组（6 例）：四部件齐全（segments+tracks+bindings+meta.linkage）、patch tracks 携带消解几何、patch bindings 携带重建 offsets、挤压几何 patch 可见、无联动路径 patch 形状不变（tracks/bindings 为 None + meta 缺省）、silence 级联 + 联动叠加时五部件齐全
- `frontend/src/utils/projectPatch.test.ts` 补集成用例（R2.3 前端零改动验证）：S2 联动 patch 应用后副段挤压可见 + 未变兄弟段引用恒等（mergeTracksInPlace 消费）
- `frontend/src/utils/projectPatch.perf.test.ts` 补联动路径用例：S2 全层 patch apply p50 < 5ms 断言——**本步起 projectPatch.perf 为合入门禁**

## 验证命令与实际输出

```
uv run pytest                                        -> 全绿（702 既有 + 6 新增）
uv run pytest tests/test_track_linkage.py::TestLinkagePatchCarriesLayers -v -> 6 passed
uv run ruff check core/project_service.py tests/test_track_linkage.py -> All checks passed!
cd frontend && bun run test                          -> Test Files 40 passed / Tests 468 passed（466 + 2 新增）
cd frontend && bun run build                         -> ✓ built in 825ms
cd frontend && bun run lint                          -> 0 errors 0 warnings
[perf] applyProjectPatch(S2 linkage ..., 1000+4x200) x50: p50=0.214ms（门禁 <5ms）
```

## 未验证边界 / 待冒烟

- 手工冒烟（主轨 trim 挤压副段后副轨 lane 即时更新）待 Phase 0.5 退出检查合并执行

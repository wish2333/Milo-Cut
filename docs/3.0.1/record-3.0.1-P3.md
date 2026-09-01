# Record: Phase 3 副轨编辑与绑定联动（P3-1 ~ P3-7，beta.2 代码完成）

> 日期: 2026-09-01 · 分支: `p3/linkage-editing` -> `dev-3.0.1`

## 完成内容（按强制顺序）

### P3-1 撤销层扩展（M5-1，前后端同 PR）
- 前端 `UndoLayer` + `tracks`/`bindings`；`captureLayers` 浅拷贝捕获
- 后端 `_UNDO_LAYERS` 扩展；`apply_undo` 校验新层；**transcript 三层合并为单次 model_copy**（原子）
- 9 用例（后端 5 + 前端 4）

### P3-2 merge 接线激活（M3）
- `applyProjectPatch` tracks/bindings 层切换 `mergeTracksInPlace`/`mergeBindingsInPlace`
- perf 门禁复跑 **p50 = 0.258ms**（门禁 5ms，19 倍余量）

### P3-3 `update_segment` 联动激活（M2-1 第 4 步）
- `_apply_main_linkage` 两阶段语义；`meta.linkage` 计数；patch 三层
- 前端 `useSegmentEdit` 第 4 参 `onLinkageCounters`，WorkspacePage toast 消费（R7.5 绝不静默）

### P3-4 `update_track_segment` expose（M2-2）
- 六步校验链；min 时长**显式拒绝**（非静默拉宽）；offsets 派生重建；主轨零变更红线测试锚定

### P3-5 成对删除 + 联动拆分（M2-3）
- `delete_segment`：成对删除 + 解绑 + track_ 命名空间防御
- `split_segment`：绝对切点映射（cut_ext = position + offset）；可拆双半段重挂（offsets 重建）/越界按重叠侧重挂/退化段解绑
- delete/split envelope 从 legacy 全量 dump 升级 ProjectPatch（revision 单调走 patch 通道）

### P3-6 `useTrackEdit` + 编辑面激活（M5-2）
- 独立 composable：乐观更新 + 300ms 防抖（键 `${trackId}:${segmentId}:${field}`）+ 失败回滚
- 捕获层按绑定状态判定：无绑定 `["tracks"]` / 有绑定 `["tracks","bindings"]`
- WaveformEditor `updateTrackTime` prop → TrackLane → SegmentBlock trim 激活；flush 挂入 handleUndo/handleRedo

### P3-7 原子性集成测试（M5-3）
- 联动拆分 undo 三层单条 apply_undo / redo 对称 revision 严格递增 / 失败保留记录可重试——3 用例

## 语义勘误（重要，须回写 SPEC）

1. **跟随优先（Follow Wins）**：绑定段的 synced 几何即预期状态——被主段新范围完全包裹**不是**冲突，不消解（否则联动 trim 每次都删字幕）。消解仅发生于：clamp 后仍与已放置兄弟段重叠（无空间）→ 删除 + 解绑（MVP 裁决：诚实移除 + undo，不做精细挤压）。
2. **Phase A 排除他段绑定段**：被动消解只作用于无绑定段；绑其他主段的段随各自主段，绝不被动挪动。
3. 挤压（squeezed）计数来自未绑定段压缩；removed 含两阶段全部删除；unbound = 解绑数。

## 验证命令与实际输出

```
cd frontend && bun run test   -> Test Files 38, Tests 449 passed
cd frontend && bun run build  -> 通过
cd frontend && bun run lint   -> 0 problems
uv run pytest                 -> 695 passed（基线 663 + 32）
uv run ruff check .           -> All checks passed
git diff core/events.py frontend/src/utils/events.ts -> 空（红线 M0-3.3）
```

## 未验证边界（P3-8 待办）

- ★ 双平台冒烟：联动跟随 / 成对删除 / 联动拆分 / Alt 独立拖动 / undo 三层回退 / toast 计数
- `v3.0.1-beta.2` tag 待冒烟后打

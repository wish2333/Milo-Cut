# Record: P4-2 M11-2 多轨数据结构 + MVP

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M11-2 / PRD D2 / 风险评审 §2.4 构造保护 / plan P4-2

## 改动文件

### 后端

| 文件 | 改动 |
|---|---|
| `core/models.py` | 新增 `SubtitleTrack`（frozen；`id: trk_<hex8>` / `role: extension|translation|caption` / `name` / `language` / `segments`）与 `TrackBinding`（`bind_<hex8>` / track_id / main_segment_id / extension_segment_id / start_offset / end_offset）；`TranscriptData` 增 `tracks` + `bindings`（default_factory 空列表，旧工程零迁移）；`ProjectPatch` 增 `tracks` / `bindings` 两层（timeline 内层组、analysis 与 media 之间，整体替换语义） |
| `core/project_service.py` | **构造保护**：`update_transcript` / `add_silence_results` / `add_segment` 三处 `TranscriptData(segments=...)` → `transcript.model_copy(update={"segments": ...})`（风险评审 §2.4 必做项；`update_transcript_meta` 已在 P1-1 用 model_copy，无需改）；`_enforce_segment_sort_invariant` docstring 锁定「只管主轨」契约；新增 `import_srt_as_track(file_path, language, role)` |
| `core/export_service.py` | 新增 `export_track_srt(track, output_path)`：副轨段按原始时间戳直出 SRT，不走确认删除/keep-range 映射（导出边界） |
| `main.py` | `@expose import_srt_as_track`（`_mark_dirty` 触发自动保存）；`_handle_export_subtitle` 支持 payload `track_id` 分支（副轨不存在返回明确错误；默认输出名 `<媒体>_<track.name>.srt`） |
| `tests/test_tracks_contract.py`（新） | 14 条：构造保护 4（update_transcript/add_silence_results/add_segment/update_transcript_meta 均保留 tracks+engine+language）、patch 往返 2、invariant 不波及副轨 1、旧工程兼容 2（缺字段 model_validate + save/open 落盘往返）、import_srt_as_track 3（命名空间隔离+300ms 绑定+offsets/孤儿不绑/空 SRT 拒绝/二次导入追加）、export_track_srt 2（原始时间戳+静音行过滤） |

### 前端

| 文件 | 改动 |
|---|---|
| `frontend/src/types/project.ts` | `SubtitleTrack` / `TrackBinding` 接口；`TranscriptData` / `ProjectPatch` 增可选 `tracks?` / `bindings?` |
| `frontend/src/utils/projectPatch.ts` | `applyProjectPatch` 应用 tracks/bindings 层（整体替换、独立应用、随 timeline 目标校验）；`hasLayerUpdates` 纳入两层；`describePatchLayers` 报告 `tracks` / `bindings` |
| `frontend/src/utils/projectPatch.test.ts` | +4 条（tracks 整体替换且 segments 层引用不动 / bindings 替换 / 目标 timeline 缺失抛 PatchApplicationError / describePatchLayers） |
| `frontend/src/components/workspace/TrackLane.vue`（新） | Timeline 底部折叠只读 lane：轨道徽标（name·language）、只读行（时间戳+文本，点击 seek）、折叠开关、空轨道占位 |
| `frontend/src/components/workspace/TrackLane.test.ts`（新） | 5 条（无轨道不渲染/行渲染/点击 seek/折叠展开/多轨徽标） |
| `frontend/src/components/workspace/Timeline.vue` | 新 prop `tracks?`；列表区底部接入 TrackLane（转发 seek） |
| `frontend/src/pages/WorkspacePage.vue` | `activeTracks` computed；Timeline 传 `:tracks`；工具栏新增「导入副轨」按钮 |
| `frontend/src/composables/useWorkspaceActions.ts` | 新增 `handleImportSrtAsTrack`：select_file → `import_srt_as_track` → patch 通道 `project-updated` + toast（N 条字幕/M 条绑定）；**不做 undo 快照**（undo 层白名单 segments/edits/analysis，见决策 3） |
| `frontend/src/pages/ExportPage.vue` | `subtitleTracks` computed + 每轨「导出副轨 SRT（name）」按钮 → `export_subtitle` 任务携带 `track_id` |

## 实现决策（对 plan/SPEC 的偏差记录）

1. **导入 UI 落点**：SPEC 写「导入对话框选作为副轨导入」；现导入 SRT 是工具栏按钮直选文件（无对话框），故按既有交互模式加并列按钮「导入副轨」，语义等价且零新弹层。
2. **id 命名空间**：track id `trk_<hex8>`，段 id 按 SPEC 字面格式 `track_{track_id}_seg_{start:.3f}`；测试断言副轨 id 永不以 `seg` 开头，主轨 merge/ED 系统不可能误匹配。绑定贪心一对一（时间序，主段消费后不复用），300ms 仅比对起点容差。
3. **副轨导入不可撤销（本版）**：`handleImportSrtAsTrack` 不 pushSnapshot——M5 undo 层白名单仅 segments/edits/analysis；track 导入是纯增量操作，redo/undo 不波及。v3.1 若开放副轨编辑再议。
4. **ProjectPatch tracks/bindings 为 timeline 内层组**（SPEC：插在 analysis 与 media 之间，对齐 models.py 字段分组）；前端应用独立判空（bindings-only patch 可单独生效），并纳入 target timeline 存在性校验。
5. **bindings 只写不消费**：TrackLane 不展示绑定关系（MVP 面锁定 plan 原文：折叠 lane 只读显示）；绑定联动/波形双 lane 挂 v3.1。
6. **demo 模式**：demoBridge 未镜像 `import_srt_as_track`（demo 无真实文件系统），点击导入副轨走失败 toast 分支；如需 demo 演示副轨可在 v3.1 补 demo 镜像。

## 验证命令与实际输出

```
uv run pytest                              -> 578 passed（564 + 14）
uv run ruff check .                        -> All checks passed!
uv run python -c "import main"             -> OK
cd frontend && bun run test                -> 340 passed (33 files)（331 + 9）
cd frontend && bun run build               -> vue-tsc + vite 通过
bunx eslint <触及 9 文件>                   -> 0 问题
```

## 未验证边界（归批次双平台冒烟 / 用户手测）

- ★ 双语项目手测：导入副轨 → Timeline 折叠 lane 显示 → 导出页导出主/副两份 SRT（验收方式原文）
- 副轨折叠 lane 在千段主轨 + 长副轨下的滚动观感（lane 自身 max-h-40 独立滚动）
- 旧工程（无 tracks 字段）真机打开（自动化已覆盖 model_validate + 落盘往返，真机归冒烟）

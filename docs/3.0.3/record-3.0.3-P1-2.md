# v3.0.3 P1-2 记录：副轨段渲染与空态（SPEC M1-2 / R1.2）

> 日期：2026-09　分支：`dev-3.0.3`（P1-2 短分支已合入并删除）

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/components/workspace/TranscriptRow.vue` | 新增 `variant?: "main" \| "track"` 与 `isBound?: boolean` props。track 分支：时间戳 display-only（`track-start`/`track-end`）、时长 chip（`track-duration`，`formatTimeShort(end-start)` 沿主轨既有格式化）、绑定标记（`track-bound-mark`，icon-only + title 主轨联动提示）；主轨专属机能在 track 分支全部关闭（编辑按钮/状态列/右键菜单/时间戳点击编辑/globalEditMode 自动进入编辑） |
| `frontend/src/components/workspace/Timeline.vue` | 新 prop `bindings?: TrackBinding[]`、新 emit `create-track-segment: [trackId, at]`；`isTrackMode` computed + `boundExtensionIds` 集合；空副轨空态卡（`track-empty-state` + `track-empty-create` 按钮）；TranscriptRow 派发传入 variant/isBound 并入 v-memo 依赖 |
| `frontend/src/pages/WorkspacePage.vue` | `:bindings="activeBindings"` + `@create-track-segment="handleListCreateTrackSegment"`；handler 走 `computeListCreateRange(at, duration)` → 既有 `handleAddTrackSegment`（同一 expose 与 toast） |
| `frontend/src/composables/useListTrackSelector.ts` | 新增纯函数 `computeListCreateRange`（默认 cue 2s，媒体上界 clamp，2 位小数与波形 lane 建段惯例一致）+ 常量 `LIST_CREATE_SEGMENT_DURATION_S` |
| 三个测试文件 | TranscriptRow +7、Timeline +5、selector +6（见下） |

## 实现要点 / 裁决

- **不建第二套行渲染（M1-1 边界延续）**：副轨行走同一 TranscriptRow 派发（`seg.type === "subtitle"` 分支天然命中），variant 多态；行高骨架与主轨行同款（52px min-h 不变）。
- **主轨零 diff**：`variant` 缺省 "main"，所有新分支以 `isTrackVariant` 前置守卫；主轨空态文案与渲染条件逐字节未动（新空态卡为独立 `v-if` 分支，仅 `isTrackMode && segments.length === 0` 时渲染）。
- **右键菜单暂缺裁决**：track 行在 P1-2 显式吞掉 contextmenu（防止主轨菜单误发 main 轨操作），P1-3 按计划补「定位/编辑/删除此条字幕」菜单。
- **空态建段入口**：按 SPEC M1-2 以当前播放时间为锚点，前端 `computeListCreateRange` 预成形 [start, end] 后走波形建段同一 expose（`add_track_segment`）与 toast；媒体上界 clamp 后仍由后端 clamp/重叠语义兜底。
- **绑定标记数据源**：既有 bindings 层（`bindings.extension_segment_id` 命中集合），无新数据通道（M0-1.6 红线）。

## 测试（新增 18）

- TranscriptRow track variant（7）：字段显示（text/start/end）、时长 chip、绑定标记有/无、主轨机能在 track 分支不存在（编辑按钮/状态按钮/右键菜单）、globalEditMode 不进编辑、时间戳 display-only、行点击 seek。
- Timeline（5）：副轨行走同一虚拟列表派发、绑定标记按 bindings 命中、主轨空态零 diff（无 track 空态卡）、空副轨空态卡 + 点击发射 `(trackId, currentTime)`、主模式不渲染 track 空态卡。
- computeListCreateRange（6）：常规/近末尾 clamp/短媒体/负值与 NaN/2 位小数舍入/无媒体时长。

## 门禁（本步实际输出）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | 716 passed（P1-1 已验证，后端本步零改动）✅ |
| vitest 全量 | **704 passed / 1 failed**（705 总数；唯一失败仍为 P0-1 已登记挂载墙钟环境例，失败集合未扩大）✅ |
| `vue-tsc --noEmit` + `vite build` | 0 错误，built in 3.42s ✅ |
| eslint | 0 errors 0 warnings ✅ |
| `uv run ruff check .` | All checks passed! ✅ |
| 红线五文件 diff | **空** ✅ |

## 未验证边界

- 空态建段的真实后端往返（add_track_segment → patch 回填列表）未在组件测试中桥接——由 beta.1 双平台冒烟（双语工程建段路径）覆盖。
- 绑定标记与波形区一致性属目视项（同一 bindings 数据源，逻辑等价），真机清单确认。

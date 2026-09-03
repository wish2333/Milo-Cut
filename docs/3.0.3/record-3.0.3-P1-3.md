# v3.0.3 P1-3 记录：文本/时间编辑与行操作 + 撤销谓词表（SPEC M1-3/M1-4 / R1.3-R1.5）

> 日期：2026-09　分支：`dev-3.0.3`（P1-3 短分支已合入并删除）

## 改动文件清单

| 文件 | 改动 |
|---|---|
| `frontend/src/composables/useTrackEdit.ts` | 列表侧入口：`editTrackSegmentText`（恒 `["tracks"]` 捕获，标签「编辑副轨文本」）/ `editTrackSegmentTime`（本地预校验：NaN 拒绝、媒体上界 clamp、min duration 0.1s，后传既有内核）；`updateTrackSegmentTime` 增可选 `onError`（波形路径不传保持静默回滚零变化）；内部提取 `captureOnce`/`submitAfterDebounce`（行为等价重构，防抖 key `trackId:segmentId:field` 与波形侧天然合并） |
| `frontend/src/components/workspace/TranscriptRow.vue` | track 变体：双击行/菜单「编辑」进文本编辑（复用既有 input + draft 机制，保存发 `track-text`）；时间戳点击编辑（提交发 `track-time`）；右键菜单 track 分支「定位 / 编辑 / 删除此条字幕」（删除无确认框，发 `track-delete`）；globalEditMode 全局扫描对 track 行不生效；选中模式点击对 track 行不生效（M1-1 边界） |
| `frontend/src/components/workspace/Timeline.vue` | 新 emits `update-track-text` / `update-track-time` / `delete-track-segment`（均附 activeTrackId）；track 行事件接线转发 |
| `frontend/src/pages/WorkspacePage.vue` | `handleUpdateTrackText`/`handleUpdateTrackTime`（onError → toast 错误原文）；`handleSelectListTrack`（flush-on-switch：先 `flushPendingTrackUpdates` 再切轨）；`@delete-track-segment` 接既有 `handleDeleteTrackSegment`（捕获层 `["tracks","bindings"]` 为 3.0.2 既有语义） |
| 测试 | `useTrackEdit.test.ts` +11、`undoListTrackCapture.test.ts` 新文件 +3、`Timeline.test.ts` +3、`TranscriptRow.test.ts` 调整（1 例 P1-2 显示锚点测试更新为 P1-3 编辑契约 + 新增 5 例） |

## 实现要点 / 裁决

- **谓词表落地（M0-1.6 唯一真源）**：text 恒 `["tracks"]`（后端 text 路径无几何语义）；start/end 按既有 `bindings.some(b => b.extension_segment_id === segmentId)` 谓词分流（与波形 trim 共用同一内核判定）；删除恒 `["tracks","bindings"]`（既有 handler，未触碰）。
- **防抖合并与回滚**：与波形侧同 key 合并——同段同字段 N 次输入 1 次提交；失败回滚以最后一次快照为准（SPEC M1-3 裁决原文执行）。列表与波形交替编辑后到者覆盖，无竞态（专测覆盖）。
- **编辑 UI**：文本双击/菜单进入、Enter 保存、Esc 取消、draft 虚拟滚动恢复全部复用主轨行机制；时间戳 ±0.1s 箭头微调同样复用。
- **flush-on-switch**：切轨前 flush 未决防抖（`flushScrollTopSave` 同模式）；切换主轨/副轨/另一副轨同通路。
- **播放跟随高亮**：复用主轨 `playheadSegmentId` 机制（track 模式下 `findSubtitleAtTime` 命中副轨段），P1-2 起即为免费行为，本步补验证。
- **P1-2 一例测试契约升级**：副轨时间戳由 display-only 改为可点击编辑（本步计划内容），对应测试改写为「进入编辑 + 提交 track-time」断言；既有其余断言零改动。

## 测试（新增 22，含谓词表 3 行全链路）

- useTrackEdit（11）：文本乐观+防抖提交、3 输入 1 提交合并、拒绝回滚+onError 原文、text 恒 `["tracks"]`；时间 min-duration 预校验（不调用不乐观写）、上界 clamp、NaN 拒绝、后端重叠拒绝回滚+原文、有绑定 `["tracks","bindings"]`、无绑定 `["tracks"]`、与波形路径共享防抖 key。
- undoListTrackCapture（3）：谓词表 1-3 行经真实链路（applyProjectResponse + useUndoRedo + apply_undo mock）——含绑定段时间编辑 undo 后 tracks/bindings offsets 双还原、redo 对称、revision 单调。
- Timeline（3）：trackId 附参转发 text/time/delete。
- TranscriptRow（+5/-1 改）：时间戳编辑提交 track-time（主轨事件不触发）、双击编辑提交 track-text、菜单三分支渲染（主轨项不出现）、删除即发无确认、定位 seek。

## 门禁（本步实际输出）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **716 passed** ✅ |
| vitest 全量 | **725 passed / 1 failed**（726 总数；唯一失败仍为 P0-1 已登记挂载墙钟环境例，失败集合未扩大）✅ |
| `vue-tsc --noEmit` + `vite build` | 0 错误 ✅ |
| eslint | 0 errors 0 warnings ✅ |
| `uv run ruff check .` | All checks passed! ✅ |
| 红线五文件 diff | **空** ✅ |

## 未验证边界

- 谓词表第 4 行（删除捕获）为 3.0.2 smoke-fix 既有 handler 行为，本步仅接线（Timeline 转发测试），未重复其捕获断言（useWorkspaceActions 无独立挂载测试通路）。
- 编辑全链路真机冒烟合并 beta.1 ★ 节点（PLAN）。

# record-3.0.4-P2-4：accept/reject 超集 patch 化（含清债 #14：accept 入 undo + 消灭 O(project) 全量刷新 workaround）

> 日期：2026-09（P2）　分支：`dev-3.0.4-p2-4`（待合入 `dev-3.0.4`）
> 对应 PLAN：Phase 2 / P2-4　SPEC：M2-3（R2.3）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/correction_service.py` | +134/-12，仅 accept/reject 两函数 + 新增模块级辅助：① 新增 `_detail_timeline_scope(detail)`（P2-3 `_detail_track_scope` 同款解析：存量 detail 无 `timeline_id` 键 → `""` 缺省放行【兼容规则】；非 JSON / 非 dict → `None` 跳过钉扎检查不猜归属）；② `accept_subtitle_correction`：解析 detail 后**时间轴钉扎**（`timeline_id` 非空且 ≠ `active_timeline_id` → `{"success": False, "error": "该结果属于其他时间轴，请切换后审阅"}` 零写入）→ 按 `detail.track_id` 分流。**主轨路径逻辑不变**（_assert_timestamps_unchanged + _check_correction_confidence + reattach_words + 时间戳腐化回滚 + _update_active_timeline），返回值超集 `{"segment_id", "patch": _success_patch(segments=…, analysis=…)["data"]}`；**副轨路径**（track_id 非空）：定位轨与轨内段（缺失 → 显式失败）→ 复用同一套校验/reattach（words=[] 原样返回空表）→ `track.model_copy(update={"segments": …})` 整体替换写回 `transcript.tracks` + 移除 AnalysisResult → 返回 `{"segment_id", "track_id", "patch": _success_patch(tracks=…, analysis=…)["data"]}`，**bindings 零触碰**；③ `reject_subtitle_correction`：同款钉扎守卫（malformed detail 跳过检查保持 v3.0.3 移除行为）+ 超集返回 `{"segment_id", "patch": _success_patch(analysis=…)["data"]}`。`accept_high_confidence_corrections` / `clear_subtitle_corrections` / store / get 零触碰 | R2.3 | 受控改点②（SPEC M0-1 明列 M2-3） |
| `frontend/src/composables/useWorkspaceActions.ts` | +90/-9：① `handleAcceptCorrection`：调用前按 scope `pushSnapshot`（scope 判定 = 条目 `track_id` 字段，P2-3 get 已输出）→ 直调 `call("accept_correction")`（不经 useLlmTasks 布尔包装，取回超集 patch）→ 成功后本地剔除 pendingCorrections 条目 + `emit("project-updated", res.data.patch)` 走 applyProjectPatch（App.vue 自动检测 patch 形态），**删除 `switch_timeline` 全量刷新 workaround（清债 #14）**；无 patch 防御回落旧全量刷新；② `handleRejectCorrection` 同构消费 patch；③ 新增模块级 `correctionUndoLayers(entry)`（捕获层裁决落点）与 `CorrectionReviewEntry` / `CorrectionReviewResult` 类型（deps.pendingsCorrections 放宽 `track_id?: string`）；④ `handleSwitchTimeline` 成功分支挂 `void loadCorrections(timelineId)` 重取钩子（R3 前端配套：时间轴切换后 pendingCorrections 单例重取，陈旧条目不残留可点；失败分支不重取）。deps 接口零字段增删（`acceptCorrection`/`rejectCorrection` 保留在接口、移出解构——WorkspacePage.vue deps 字面量零改动） | R2.3 | 登记改点 |
| `tests/test_correction_accept_patch.py` | 新建 10 例（§4），既有测试文件零改动 | R2.3 | 只增 |
| `frontend/src/composables/useWorkspaceActions.test.ts` | 新建 7 例（§5），前端既有 .test.ts 零改动（`expect(` 删除 grep = 0） | R2.3 | 只增 |

`useLlmTasks.ts` **零改动**：重取钩子挂在 useWorkspaceActions 的 switch_timeline 调用点（SPEC M2-3「找到 switchTimeline 的调用点挂重取钩子（最小侵入）」的最小侵入落位——loadCorrections 本就是 useWorkspaceActions 的 dep）；`main.py` **零改动**（已验证 `_mark_dirty` 仅在 success 时 emit PROJECT_DIRTY 后原样透传 envelope，`data.patch` 键无损到达前端）；`WorkspacePage.vue` / `App.vue` **零改动**（审阅 modal 的 `handleAcceptCorrection(corr.id)` 接线与 `onProjectUpdated` patch 自动检测均既有就绪）。

## 2. 三裁决落实对照（SPEC M2-3）

| 裁决 | SPEC 契约 | 落实 |
|---|---|---|
| **patch 层裁决**（覆盖 PRD：PRD 写 `tracks=…, bindings=…` 错层） | 主轨 = `segments + analysis`；副轨 = `tracks + analysis`（text 无几何语义，bindings 零变化；漏 analysis 则前端审阅列表与后端脱节） | accept 主轨 `_success_patch(segments=new_segments, analysis=new_analysis)`；副轨 `_success_patch(tracks=new_tracks, analysis=new_analysis)`——**bindings 层两路径均不传**（model_dump 后为 None）。后端测试 #2 断言 `patch["bindings"] is None` + 落盘 bindings 逐条 model_dump 相等 |
| **undo 捕获层裁决**（覆盖 PRD：PRD 漏 analysis） | 主轨 `["segments","analysis"]` / 副轨 `["tracks","analysis"]`（analysis 是合法 undo 层 undoRecords.ts:15-23；漏层则 undo 只回滚文本、审阅条目不恢复） | `correctionUndoLayers(entry)` 单一落点：`entry.track_id` 非空 → `["tracks","analysis"]`，否则 `["segments","analysis"]`；accept/reject 共用（reject 只动 analysis 但两层快照保证 undo 一次回退审阅条目恢复）。vitest #3 用真实 useUndoRedo + applyProjectPatch + 内存 apply_undo 后端仿真：undo 一次同时恢复文本**与** analysis.results 里的审阅条目，redo 对称 |
| **时间轴钉扎裁决**（fail-fast ✅ / 按 id 写 ❌） | detail.timeline_id 非空且 ≠ active → 明确报错零写入；无键存量放行 | `_detail_timeline_scope` 解析（同 P2-3 兼容规则）；accept 与 reject 均在**任何写入之前**校验。后端测试 #5 以「fork 时间轴共享 analysis 结果」构造真实漂移场景：accept/reject 双双 `{"success": False}`、error 含「其他时间轴」、revision 与时间轴 model_dump 均不变；#5d 存量无键 detail 放行成功 |

## 3. :157 兼容证据（硬门禁）

- `tests/test_subtitle_correction_review.py` **零改动**（`git diff dev-3.0.4 -- tests/test_subtitle_correction_review.py` = 0 行）：17 例全绿，其中 :157 `assert res["data"]["segment_id"] == segs[0].id` 原样通过——accept 主轨返回保留 `segment_id` 键（超集不破坏旧消费方）。
- 门禁「后端断言零删改」PASS（`git diff v3.0.3 -- tests/` 断言删除 grep = 0）；前端既有 .test.ts 零改动 → `expect(` 删除 grep = 0（门禁「前端断言白名单外零删改」PASS）。
- 批路径兼容：`accept_high_confidence_corrections` 内部逻辑与返回（accepted_count/remaining_count）零改动，其前端消费（`handleAcceptHighConfidence` 的 switch_timeline 刷新）原样保留（SPEC 边界：不改其前端消费）。

## 4. 后端测试（tests/test_correction_accept_patch.py，新建 10 例）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | test_returns_segment_id_plus_patch_with_revision_bump | 主轨超集：`segment_id` 键在（:157 兼容语义）+ `patch` 含 segments/analysis 层、tracks/bindings 层为 None；revision 恰 +1（`svc._revision` 与 patch["revision"] 同证）；analysis 层已无该结果、segments 层带修正文本 |
| 2 | test_batch_accept_reuses_single_accept_superset | 批路径：spy 包裹单 accept，2 条 accepted 的 data 全含 `patch` 键（超集自然获得，不改批内部逻辑） |
| 3 | test_accept_writes_track_segment_and_leaves_bindings_untouched | 副轨：轨内段 text 更新 + dirty_flags.llm_corrected；bindings 数量与内容（model_dump 逐条）零变化；主轨 segments 零变化；patch 层 = tracks+analysis（segments 层 None）；tracks 层带修正段 |
| 4 | test_accept_track_segment_with_empty_words | reattach 空输入：words=[] 的副轨段 accept 成功无异常，seg.words == []（reattach 跳过原样返回空表，不触发 TimestampCorruptionError） |
| 5 | test_accept_missing_track_fails | 悬空 scope 防御：轨删除后直接 accept 原始结果 id → 显式失败（error 含 "Track"） |
| 6 | test_reject_returns_analysis_only_patch | reject 超集：patch 层 = analysis（segments/tracks 均None）；结果被移除；段文本零变化；revision +1 |
| 7 | test_accept_on_other_timeline_fails_with_zero_writes | 钉扎：fork 场景 detail.timeline_id ≠ active → accept 失败、error 含「其他时间轴」、revision 不变、active 时间轴 model_dump 全等（零写入） |
| 8 | test_reject_on_other_timeline_fails_with_zero_writes | 钉扎：reject 同构失败零写入 |
| 9 | test_owning_timeline_still_accepts | 钉扎 id == active → 正常超集 accept（不误伤本时间轴审阅） |
| 10 | test_legacy_detail_without_timeline_key_passes | 存量兼容：手工构造无 track_id/timeline_id 键的 v3.0.3 形 detail → 放行成功（含 patch） |

编排口径：fork 场景 = model_copy 复制 'default' 时间轴（共享 analysis 结果，与 create_timeline fork 同构）后切 active——钉扎分支的真实触达路径（不共享结果的异时间轴只会走 not-found，测不到守卫）。

## 5. 前端测试（frontend/src/composables/useWorkspaceActions.test.ts，新建 7 例）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | emits project-updated once with the patch and never calls switch_timeline | accept 响应含 patch → project-updated 恰一次以 patch 载荷 emit；**switch_timeline 零调用**（清债 #14 判据）；本地 applyProjectPatch 仿真中文本已更新；pendingCorrections 条目剔除 |
| 2 | falls back to the legacy full refresh when the response has no patch | 防御：无 patch 回落旧 switch_timeline 全量刷新（理论不存在，锁定回落存在性） |
| 3 | captures [segments, analysis] BEFORE the bridge call for a main-track entry | undo 捕获层：主轨条目 `["segments","analysis"]`；快照捕获的是 before 态（"old text"）；`invocationCallOrder` 断言快照先于 accept 桥调用 |
| 4 | captures [tracks, analysis] for an extension-track entry (track_id scope) | 副轨条目（track_id="trk-1"）→ `["tracks","analysis"]` |
| 5 | restores the text AND the review entry, then re-applies on redo | undo 一次回退 accept：真实 useUndoRedo.pushSnapshot/undo/redo + 内存 apply_undo 后端（捕获层转 patch）+ 真实 applyProjectPatch——undo 后文本回 "old text" **且** analysis.results 恢复 "res-1"（analysis 捕获层的价值判据）；redo 对称回到 "new text" + 空结果 |
| 6 | emits the analysis-layer patch and captures [segments, analysis]（reject） | reject 同构 1 条：patch（analysis 层）emit 一次、文本不动、结果移除、捕获层正确、条目剔除 |
| 7 | re-fetches corrections for the newly active timeline after a successful switch | 重取钩子：switch 成功 → loadCorrections(新 id)；switch 失败 → 不重取 |

宿主注记：useWorkspaceActions.test.ts 此前不存在（R3 已核实），本步新建（PLAN P2-4 用例栏明示）；测试手法对齐 useTrackEdit.test.ts（mock @/bridge + vi.mocked）与 useUndoRedo.test.ts（apply_undo 桥 mock + patch 回放）。

## 6. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**804 passed**（794 + 10 新增，全绿）
- ruff：0 problems
- vitest：**778 collected / 777 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，3.0.3 已登记环境例豁免，PRD-v3.0.4 风险 #12 口径；本步不触波形代码，复跑单文件仍失败 = 环境例吻合）
- build（vue-tsc --noEmit + vite build）：通过；lint（eslint .）：0 errors 0 warnings
- 红线 R0-1~R0-5 全 PASS：禁改面 diff 为空（pywebvue/、task_manager、export*、track_constraints、workflow_engine、ffmpeg*、subtitle_service、timeline_utils、diff_service、migrations、models、events、config、llm_prompts、llm_service、project_service、main.py、dev.py、build.py 全零）；后端 diff 文件集仅 core/correction_service.py（白名单内，受控改点②）；断言删除 0；dev.py / build.py 零改动
- 环境注记：`bun run` 本沙箱不可用，按 P0-2 回落条款直跑 node_modules/.bin 等价命令（与 P2-3 及此前各步同口径）

## 7. 未验证边界与交接

- **accept/reject 失败的 UI 反馈**：钉扎拒绝（「该结果属于其他时间轴」）与 not-found 在前端维持既有静默语义（失败不 toast、条目保留）——与 v3.0.3 行为一致非本步引入；条目清理依赖切换后重取钩子（switch 回所属时间轴即恢复正确列表）。若需失败 toast 登记 3.0.5。
- **双时间轴真实 UI 冒烟**（审阅期间切时间轴 → 列表重取 → 切回继续审阅）随 beta.2 ★（P2-5）。
- `WorkspacePage.vue` 既有 `watch(props.project)` 会在每次 project 变化后额外 loadCorrections（含 accept patch 应用后）——与本步重取钩子叠加为幂等双取（同 timeline id 两次轻量读），非竞争；若要收敛为单入口登记 3.0.5。
- 批路径 `handleAcceptHighConfidence` 仍走 switch_timeline 全量刷新（SPEC 边界明示不改其前端消费）；其 O(project) 消化登记 3.0.5 候选。
- accept 高频连点的 in-flight 乱序：patch 走 revision 单调 + App.vue isStalePatch 丢弃，理论安全，未专设并发测试（SPEC M1-5 并发约束：序列化调用口径）。
- 前端 pendingCorrections 条目的 `track_id` 运行时存在但 useLlmTasks 的 SubtitleCorrection 接口未声明该字段（本步在 useWorkspaceActions 侧以 `CorrectionReviewEntry.track_id?` 消费，避免动 useLlmTasks 红线）；P2-5 审阅 modal 若需轨徽再在 useLlmTasks 补类型声明。

# record-3.0.4-P1-4：批量落盘方法 create_translation_track

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-4`（待负责人审查后合入 `dev-3.0.4`）
> 对应 PLAN：Phase 1 / P1-4　SPEC：M1-4（R1.3）

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/project_service.py` | **仅新增 `create_translation_track` 一个方法**（插入位 = `import_srt_as_track` 之后 `update_media_info` 之前，同属整轨写入区；单一 hunk `@@ -692,6 +692,161 @@`，155 行新增 / 0 行删改；`git diff v3.0.3 -- core/project_service.py \| grep -cE '^-[^-]'` = 0）。`generate_subtitle_keep_ranges` **零触碰**（diff 内 grep "keep_range" = 0，P3-9 才轮到它）。方法体内仅一处局部 import（`from uuid import uuid4`，import_srt_as_track :632 同款手法），模块头 import 区零改动 | R1.3 | 只增 |
| `tests/test_translation_track.py` | 新建（10 个测试函数 / 11 例，挂 M5 矩阵 M1 批量写组，目标 8-10 例达成），手法复用 test_tracks_contract.py（真实 ProjectService 实例 + monkeypatch 临时工程目录 + 直装主轨 segments） | M5 | 只增（新文件） |

`tests/` 既有文件零改动（本步 tests/ diff 仅新增文件）；禁改面（pywebvue/、task_manager、export_service 等）本步零触碰。

## 2. 实现要点（与 SPEC M1-4 契约逐条对账）

签名严格按 SPEC：`create_translation_track(self, timeline_id: str, name: str, language: str, items: list[dict], bind: bool = True) -> dict`。方法不做任何 LLM 相关工作（items 由 P1-5 handler 从管线输出组装）。

| 契约 | 落实 |
|---|---|
| ① 时间轴钉扎（入口第一件事） | `self._current is None` 守卫后立即 `timeline_id != self._current.active_timeline_id` → `{"success": False, "error": "Timeline no longer active: 翻译期间已切换时间轴"}` 零写入（属性名核实 = `self._current.active_timeline_id`，与 SPEC 写法一致） |
| ② 重复语言拒绝（写侧双保险） | `any(t.role == "translation" and t.language == language for t in tl.transcript.tracks)` 命中 → 拒绝，文案「同语言翻译轨已存在（{language}），可清空或删除该轨后重试」（含 M1-1 ⑤ 指引短语） |
| ③ 幂等对账 | 逐 item 的 `segment_id` 对照**当下** `tl.transcript.segments` 中 type=subtitle 的 id 集：仍存在 → 生成 track 段（**start/end 逐字段复制当下主轨段**，非 item 携带的拷贝时间——测试 8 以「item 时间被篡改为 99.0 仍以主轨为准」固化此语义；id 走 `track_{track_id}_seg_{start:.3f}`、text 用 item 译文）；不存在 → id 进 `uncovered_ids`（不静默）；`track_segments` 为空（含 items 为空）→ `{"success": False, "error": "所有目标段已被删除"}` 零写入 |
| ④ bind=True | 按 `segment_id ↔ 新 track 段` 精确 1:1 建 `TrackBinding(start_offset=0.0, end_offset=0.0)`（时间完全复制故 offset=0）；bind=False 跳过 binding 构建，tracks 层照写 |
| ⑤ 单 patch 落盘 | 照 import_srt_as_track 整体替换写法：`transcript.model_copy(update={"tracks": [*旧, 新轨], "bindings": [*旧, *新]})` → `_update_active_timeline` → `return self._success_patch(tracks=…, bindings=…)`——一次 revision +1、undo 一步回退整轨；**未调用 add_track_segment**（全方法无该符号） |
| ⑥ 返回 data 附报告 | `{track_id, written_count, target_count, uncovered_ids}` 经 patch `meta` side-channel 携带（`meta={"translation": {...}}`）——ProjectPatch 的 meta 是唯一合法附加数据槽（models.py:459-461「side-channel payload … old frontends ignore it」，clear_track_segments 的 linkage 计数同款先例），data 即 patch dump 故「data 附」语义成立；P1-5 handler 从 `data["meta"]["translation"]` 取数 |

新轨构造：`SubtitleTrack(id=f"trk_{uuid4().hex[:8]}", role="translation", name=name, language=language, segments=…)`——与 `add_track` 同款直接构造路径（add_track 本身是独立 patch 写，复用它会多一次 revision，故只复制其构造形态）；三个 id 生成器命名空间与 import_srt_as_track :634/:637/:670 逐字同源。边界：不动主轨 segments；不调 `_enforce_segment_sort_invariant`（track 段天然按主轨序）；无自动合并/增量重译。

## 3. 红线命令实际输出

- **`git diff v3.0.3 --stat -- core/project_service.py`**：`155 insertions(+)`，单一文件单一 hunk（`@@ -692,6 +692,161 @@`），0 删改；白名单 M0-1 表 project_service.py 行 =「新增 create_translation_track（M1-4）」逐字吻合 ✅
- **累计 `git diff v3.0.3 --stat -- core/ main.py`**（P1-1/P1-2/P1-3 既有 + 本步）：events.py +3 / llm_prompts.py +23 / llm_service.py +384 / models.py +2 / project_service.py +155，共 567 insertions 0 deletions，全部落在 M0-1 白名单内 ✅
- **禁改面 diff**：pywebvue/、task_manager.py、export_service.py、export_timeline.py、track_constraints.py、workflow_engine.py、ffmpeg_service.py、ffmpeg_presets.py、subtitle_service.py、timeline_utils.py、diff_service.py、migrations.py、correction_service.py、main.py、dev.py、build.py 全部为空 ✅
- **R0-3 断言零删改**：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = **0** ✅；本步 tests/ 只新增 test_translation_track.py
- **本步自身 diff（vs dev-3.0.4）**：core/project_service.py +155（唯一代码改动）+ tests/test_translation_track.py（新建）✅

## 4. 单 patch 千段断言的实现证据（验收核心）

测试 `test_revision_exactly_plus_one[1000]`（tests/test_translation_track.py）：

1. 写前 `rev_before = svc._revision`；1000 段主轨 → 一次 `create_translation_track(...)`；
2. 断言 `data["revision"] == rev_before + 1` **且** `svc._revision == rev_before + 1`——revision 恰好 +1（循环 add_track_segment 1000 次会是 +1000，该路径在实现里不存在）；
3. 断言同一 patch 的 `data["tracks"]` 层含新轨 1000 段、`data["bindings"]` 层 1000 条（两层同 envelope 一次往返）；
4. 断言 meta 报告 `written_count == 1000`、`target_count == 1000`、`uncovered_ids == []`；
5. 落盘态与 patch 一致（transcript.tracks[0].segments 1000 段 / bindings 1000 条）。

undo 侧（`test_undo_layers_revert_whole_track`）：patch 的 tracks/bindings 层恰为「写前态 + 新轨/全部新 bindings」，经后端 undo 唯一入口 `apply_undo({"tracks": 写前, "bindings": 写前}, base_revision=写后 revision)` 一次回退，transcript 恢复写前 tracks/bindings 逐 id 相等——前端 undo 行为归 P1-6，此为数据层完整性后端侧证据。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**760 passed**（749（P1-3 基线）+ 本步新增 11，全绿）
- ruff：All checks passed（触及文件 core/project_service.py / tests/test_translation_track.py 双零）
- vitest：756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确；本步纯后端未触前端）
- build（vue-tsc + vite）：通过；lint（eslint）：0/0
- 红线 R0-1 ~ R0-5 + dev/build.py：全部 PASS（明细见 §3）
- 门禁 exit code：**0**

## 6. 测试清单（10 函数 / 11 例 → M5 矩阵 M1 批量写组 ≥6 达成）

| # | 用例 | 对应要求 |
|---|---|---|
| 1-2 | `test_revision_exactly_plus_one[3]` / `[1000]`（参数化千段）：revision 恰 +1（内存计数与 patch 双证）、单 patch 双层（轨段数=1000、binding 数=1000）、meta 报告 written=1000/uncovered 空、落盘态一致 | 单 patch 千段（契约 ④⑤） |
| 3 | `test_undo_layers_revert_whole_track`：patch 层 = 写前态+新轨+全部 bindings，`apply_undo` 一次回退整轨含 bindings | undo 数据层完整性（后端侧） |
| 4 | `test_duplicate_language_rejected_zero_write`：先建同语言 translation 轨 → 拒绝 + 文案含「可清空或删除该轨后重试」+ revision 不变 + 零写入 | 契约 ①（重复语言） |
| 5 | `test_duplicate_check_ignores_other_roles_and_languages`：extension 轨（同语言）与日语 translation 轨共存 → en 仍可写入 | 契约 ① 判据精确性（role+language 双命中才算重复） |
| 6 | `test_timeline_pinning_rejects_stale_timeline_id`：切时间轴后传旧 id → 拒绝 + error 含「Timeline no longer active」+ revision 不变 + 两条时间轴均零写入 | 契约 ⑥（钉扎双保险） |
| 7 | `test_partial_uncovered_reported_and_written`：1 个不存在 id → 落盘成功 + uncovered_ids=[该 id] + written_count=3/target_count=4 | 契约 ③（部分落空不静默） |
| 8 | `test_all_uncovered_rejected_zero_write`：全部 id 不存在 → success=False + error「所有目标段已被删除」+ 零写入 | 契约 ③（全部落空） |
| 9 | `test_empty_items_rejected_zero_write`：items=[] → 同上拒绝 + 零写入 | 契约 ③（items 为空并入全部落空） |
| 10 | `test_id_namespace_time_copy_and_zero_offsets`：track 段 id == `track_{track_id}_seg_{main.start:.3f}`、start/end 与主轨段逐项相等（item 携带过期时间 99.0 被主轨当下时间覆盖）、binding 双 offset 全 0、1:1 配对、主轨 segments 逐 id 不动 | 契约 ③（命名空间+时间复制）+ 边界（不动主轨） |
| 11 | `test_bind_false_writes_segments_without_bindings`：轨段写入但 bindings 零新增（落盘态与 patch 层双证） | 契约 ④（bind=False） |

## 7. 未验证边界

- **meta 报告键位的消费方**：P1-5 handler 从 `data["meta"]["translation"]` 取 `{track_id, written_count, target_count, uncovered_ids}` 组装完成事件 payload——本步只固化键位契约，消费接线归 P1-5；
- **前端 undo 实操**：`apply_undo` 只证数据层可整体回退；前端 pushSnapshot(["tracks","bindings"]) → 一次回退整轨的 UI 行为归 P1-6；
- **items 字段缺失/类型异常**（无 segment_id/text 键）：按 handler 契约由 P1-3 管线输出保证，未加防御（KeyError 自然冒泡为任务失败）；
- **同一 segment_id 重复出现在 items**：会生成同 id track 段（主轨段 id 天然唯一 + 管线全量守恒保证不重复，同 P1-3 record 口径未加防御）；
- **千段以上规模**（5000/10000 段）：千段 0.15s 内完成（11 例总耗时），未做更大压力观测；千段级真实耗时与 token 观测随 beta.1 真机（M5）。

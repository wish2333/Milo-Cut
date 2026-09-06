# record-3.0.4-P2-2：handler 副轨分支（_handle_subtitle_correction 段源与过滤）

> 日期：2026-09（P2）　分支：`dev-3.0.4-p2-2`（待合入 `dev-3.0.4`）
> 对应 PLAN：Phase 2 / P2-2　SPEC：M2-1（R2.1）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `main.py` | `_handle_subtitle_correction`（现 :909-）新增 track_id 非空分支：① `tl.transcript.tracks` 定位轨，缺失 raise `RuntimeError("Track not found: {track_id}")`（文案含 track_id）→ 任务 failed；② 段源 = 该轨 segments（轨内全为 subtitle 型，无 type 过滤）；③ confirmed-deleted 映射 = bindings 反查表（`b.track_id == track_id` 过滤后 ext_id → main_id），主轨 id ∈ `collect_confirmed_deleted_seg_ids` 的绑定副轨段跳过，无绑定段保留；④ partial hints 不收集不透传（主轨 else 分支内原有 hints 逻辑逐字节不动，仅随分支整体缩进）；store 调用点透传 `track_id=track_id`（见 §2 裁决）；其余流程（prompt resolve / 管线 / 进度 / token_usage / 完成事件 / workflow accumulate）零改动 | R2.1 | 登记改点（SPEC M0-1 main.py 行明列 M2-1） |
| `core/correction_service.py` | 仅 `store_subtitle_corrections` 签名追加 `track_id: str = ""` + detail JSON 增键 `"track_id": track_id`（空串 = 主轨）+ docstring；**互清（kept_results 过滤）与 seg_map 构建零触碰** | R2.1（M2-2 前置形参） | 受控改点②（SPEC 允许的「顺带加形参」选项） |
| `tests/test_correction_track_source.py` | 新建 6 例（§3） | R2.1 | 只增 |

主轨路径说明：track_id 为空走 else 分支，其代码与 v3.0.3 逐字节一致（仅缩进 +4 进入 else；diff 显示为块移动，无任何逻辑/标识符/常量改动）；`deleted_seg_ids` 收集与空段集 `ValueError("No subtitle segments to correct")` 守卫两路径共用、原位未动。既有测试断言零改动全绿（776 → 782）。

## 2. store 形参二选一裁决（任务书 ⑤ 处置项）

**选择：B —— 本步顺带在 correction_service.py 加 `track_id: str = ""` 形参并仅存 detail JSON 键，handler 单调用点透传 `track_id=track_id`（SPEC M2-1 第三触点 main.py:969-971 的终态形状）。**

理由：
- handler store 调用点一步到位到终态形状，不留「按 track_id 分支但两支调用完全相同」的死分支（选项 A 的实际形态）；P2-3 无需回头改 main.py。
- detail JSON 键 `"track_id": track_id`（空串 = 主轨）正是 M2-2（P2-3）对该键的终态定义，非弃掷代码；P2-3 只需补 `timeline_id` 键 + seg_map 按 scope + 互清精确化。
- 调用方核查：`store_subtitle_corrections` 生产调用仅 main.py 一处（本人 grep 复核），默认值 `""` 保证零破坏；既有 `test_subtitle_correction_review.py` 15 处调用全部位置传参，零改动通过。

代价与边界（红线合规）：主轨 store 的 detail JSON 也多出 `"track_id": ""` 键（get 侧按需 `.get` 解析，超集无害，新用例锁定）；副轨路径的 corrections 引用轨命名空间段 id，在 P2-3 seg_map 作用域化之前会被既有主轨 seg_map 全量滤除（stored_count=0）——本步测试只锁管线输入段集契约（该契约为终态稳定面），不锁 stored_count，避免给 P2-3 留需反转的过渡断言。

## 3. 测试（tests/test_correction_track_source.py，新建 6 例；既有测试零改动）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | test_bound_to_deleted_main_skipped_others_kept | 1 主轨段 confirmed-deleted：其绑定副轨段不进管线段集；绑定存活主轨段与无绑定段保留（M2-1 ③） |
| 2 | test_unbound_segments_survive_main_deletion | 全无绑定时主轨删除不影响任何副轨段入源（M2-1 ③ 无绑定保留） |
| 3 | test_partial_hints_not_collected_on_track_path | 主轨 partial_delete 分析结果存在时，副轨段 payload 不携带 edit_hint（M2-1 ④ 裁决） |
| 4 | test_missing_track_fails_task | track_id="trk_missing" → 任务 failed，error 含 "Track not found" 与 track_id；管线零调用（M2-1 ① 失败路径） |
| 5 | test_default_payload_uses_main_subtitle_segments | track_id 缺省：段源 = 主轨 subtitle 段 - confirmed-deleted - silence（v3.0.3 快照） |
| 6 | test_main_path_store_records_empty_track_id | 选项 B 落地：主轨 store 后 detail JSON 含 `"track_id": ""` |

驱动手法：照 tests/test_translation_expose.py 的 `_Api` harness（MiloCutApi.__new__ + real ProjectService + monkeypatch 路径/config）+ `_register_task_handlers` + 预置 `_tasks` 后同步 `TaskManager._execute_task` 派发 + mock `core.llm_service.analyze_subtitle_correction` 捕获段集。

## 4. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**782 passed**（776 + 6，全绿）
- ruff：0 problems；vitest：771 collected / 770 passed（唯一失败 = useRowLayout.perf 环境例，已登记）；build / lint 通过
- 红线 R0-1~R0-5：全部 PASS（禁改面 diff 为空；断言删除 0；diff 属登记改点）

## 5. 未验证边界

- 副轨 corrections 的实际落盘（seg_map 作用域化 / 互清精确到同轨 / 悬空过滤 / get 附轨标注）随 P2-3 交付，本步 detail 键先行。
- bindings 反查表按 `b.track_id == track_id` 过滤（轨内绑定）；轨 id 命名空间本身保证 ext id 全局唯一，双保险。
- 真机副轨纠错冒烟随 beta.2 ★（P2-5）。

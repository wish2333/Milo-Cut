# record-3.0.4-P2-3：pending 作用域化（store / get 的 track scope，本模块最高风险步）

> 日期：2026-09（P2）　分支：`dev-3.0.4-p2-3`（待合入 `dev-3.0.4`）
> 对应 PLAN：Phase 2 / P2-3　SPEC：M2-2（R2.2）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/correction_service.py` | 仅两函数 + 模块级辅助：① 新增模块级 `_detail_track_scope(detail)`（存量 detail 无 `track_id` 键 → `""` 主轨作用域【兼容规则】；非 JSON / 非 dict → `None`，调用方保守不清不误删）；② `store_subtitle_corrections`：seg_map 按 scope 构建（空 track_id = 主轨 `tl.transcript.segments` 原路径逐字节保留；非空 = 对应轨 `track.segments`，**轨不存在防御行为见 §2 裁决**）+ 互清精确化（kept_results 只清除「type == llm_subtitle_correction 且 detail.track_id == 本次 track_id」，其余轨与主轨待审集不动；不可解析 detail 永不匹配）+ detail JSON 增键 `"timeline_id": timeline_id`（R3 补，供 M2-3/P2-4 accept/reject 时间轴钉扎校验；`"track_id"` 键 P2-2 已写，保留）；③ `get_subtitle_corrections`：输出逐条附 `track_id` / `track_name`（**主轨条目两字段均为 `""`，约定见 §3**）+ 悬空过滤（detail.track_id 非空且该轨已不存在 → 该条跳过不出现在列表）+ 段解析按 scope（空 → 主轨段、非空 → 轨内段，段缺失回退 0.0 原逻辑保留）；④ 两函数 docstring 同步。**`accept_subtitle_correction` / `reject_subtitle_correction` / `accept_high_confidence_corrections` / `clear_subtitle_corrections` 四函数零触碰**（diff hunk 全部落在 store/get/模块头部，grep 四函数名 0 命中；timeline 级语义留 P2-4 与 3.0.5 候选） | R2.2 | 受控改点②（SPEC M0-1 明列 M2-2） |
| `tests/test_correction_scope.py` | 新建 12 例（§4），既有测试文件零改动 | R2.2 | 只增 |

## 2. 二选一裁决：轨不存在时的防御行为（SPEC M2-2 允许两态）

**选择：直接返回失败 `{"success": False, "error": f"Track {track_id} not found"}`（非「seg_map 空 → 0 stored」）。**

理由：
- 生产路径上 main.py `_handle_subtitle_correction` 已在段源解析处先挡（P2-2 交付：raise `RuntimeError("Track not found: {track_id}")` → 任务 failed，store 根本不会被调）——本分支是纯防御纵深，两态都不会被生产触达。
- 失败返回是**显式契约**：错误 envelope 带轨 id，可观测、可断言；「空 seg_map → 0 stored」则是静默成功，会掩盖作用域拼错（如轨 id 传错）这类上游 bug，且仍会执行一次「清同 scope + 写回」的空转写。
- 与同文件既有防御风格一致（timeline 不存在同样显式返回失败，不静默）。
- 新用例 `test_missing_track_fails_and_clears_nothing` 锁定：失败返回 + 待审集原样（连互清都不发生）。

## 3. 主轨 track_name="" 约定（SPEC「输出逐条附 track_id 与 track_name」的落位）

- get 输出对**主轨条目**给 `track_id=""` **且** `track_name=""`：前端以 `track_name` 空串判主轨（SPEC M2-2 原文「主轨条目 track_name 给 ""（前端据空串判主轨）」），与 detail JSON 的 `"track_id": ""` 作用域语义同源同值，无双字段分叉。
- 副轨条目 `track_id` = detail 记录的轨 id、`track_name` = 该轨当下 `SubtitleTrack.name`（get 时实查，非 store 时快照——轨改名后列表标注自动跟随）。
- 不引入 `is_main` 之类第三字段：空串判据已足够且是 SPEC 指定口径；前端消费（轨徽显示）在 P2-5 审阅 modal 落地。

## 4. 测试（tests/test_correction_scope.py，新建 12 例；既有测试零改动）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | test_track_store_keeps_main_pending | 正向：主轨 store 后副轨 store → 主轨待审集计数不变（2），副轨 2，总数 4（M2-2 验收主句） |
| 2 | test_main_store_keeps_track_pending | 反向：副轨 store 后主轨 store → 副轨待审集不变 |
| 3 | test_track_rerun_clears_only_that_track | 重跑同轨只清同轨：副轨 store 两次 → 副轨 2 非 4，主轨 2 不动 |
| 4 | test_main_rerun_count_regression | 主轨回归：主轨两次 store 计数 2 非 4（作用域世界镜像既有 `test_store_clears_previous_corrections`，且有副轨在场） |
| 5 | test_legacy_detail_cleared_by_main_store | 存量兼容 A：手工构造无 track_id 键的 detail → 按 "" 主轨作用域，再 store 主轨会清它 |
| 6 | test_legacy_detail_survives_track_store | 存量兼容 B：副轨 store 不清无键存量记录 |
| 7 | test_unparseable_detail_never_cleared | 保守规则：非 JSON detail（`"not json {"`）主轨 store 也不清（不误删） |
| 8 | test_missing_track_fails_and_clears_nothing | 防御：track_id 非空且轨不存在 → 显式失败（error 含轨 id）+ 零清除零写入（§2 裁决锁定） |
| 9 | test_output_appends_track_id_and_name | get 输出附轨：主轨条目 `track_id=""`/`track_name=""`；副轨条目带轨 id 与轨名（§3 约定锁定） |
| 10 | test_segment_times_resolve_within_scope | 段解析按 scope：副轨条目 start/end 取轨内段时间（轨时间基 100.x，主轨 0-10，绝不串轨）；scope 内段缺失回退 0.0 |
| 11 | test_dangling_track_entries_filtered | 悬空过滤：副轨 store 后（真 API）delete_track → get 列表不含该轨条目，主轨条目不受影响 |
| 12 | test_store_writes_track_and_timeline_keys | detail JSON 落盘双键：读 AnalysisData 结果 detail 断言含 `timeline_id`（值 = "default"）与 `track_id`（""/轨 id 两态齐） |

编排口径：全部**序列化调用**（store 先后执行、断言中间态），不构造并发写断言（SPEC M1-5 并发约束 ②）。计数读取用原始 `tl.analysis.results` + 手工 json 解析（`_pending` helper），不依赖被测的 get 输出，避免自证。

## 5. 既有断言零改动核验（硬门禁证据）

- `git diff v3.0.3 -- tests/ | grep -cE '^-'` = **8**（本步合入后复跑），**8 行全部为 diff 元数据头**（`--- /dev/null` ×7 = P1/P2 各步新建测试文件 + 本步新文件；`--- a/tests/test_llm_prompts.py` ×1 = P1-2 已追认的 EXPECTED_KEYS +1 受控增行）；**剔除 `^---` 头后内容删除行数 = 0**：`git diff v3.0.3 -- tests/ | grep -E '^-' | grep -cvE '^---'` → 0。
- 断言级门禁（gates R0-3 同款）：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = **0**。
- 本步自身足迹：`git diff dev-3.0.4 --name-only -- tests/` 仅 `tests/test_correction_scope.py`（新建，纯新增 0 删除）；`tests/test_subtitle_correction_review.py` 17 例含 `test_store_clears_previous_corrections`（主轨两次 store 计数 2 非 4）**零改动通过**——这正是兼容规则（无键 → ""）正确实现的判据。

## 6. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**794 passed**（782 + 12 新增，全绿）
- ruff：0 problems
- vitest：771 collected / 770 passed（唯一失败 = useRowLayout.perf.test.ts，已登记环境例）
- build（vue-tsc + vite）：通过；lint（eslint）：0 errors 0 warnings
- 红线 R0-1~R0-5 全 PASS：禁改面 diff 为空；后端 diff 文件集全部白名单内（本步仅 `core/correction_service.py`，受控改点②）；断言删除 0；models.py diff 仅 P1-1 枚举行（本步零触碰）；dev.py / build.py 零改动

## 7. 未验证边界与交接

- accept/reject 副轨路径与时间轴钉扎校验、patch 超集返回 = P2-4（本步四函数零触碰红线）；`timeline_id` 键的**消费方**在 P2-4，本步只负责落盘。
- `accept_high_confidence_corrections` / `clear_subtitle_corrections` 保持 timeline 级全清语义（SPEC M2-2 边界：副轨用户用逐条 accept/reject；作用域化登记 3.0.5 候选）——注意副轨待审集会被这两个 timeline 级操作一并清掉，属既有语义非本步引入。
- 悬空条目只是 get 侧过滤，AnalysisResult 本体仍留在 analysis.results（随轨失效不落盘清除）；若需物理清理登记 3.0.5。
- 前端轨徽消费（track_name 显示、空串判主轨）随 P2-5 审阅 modal。
- 真机双轨纠错冒烟随 beta.2 ★（P2-5）。

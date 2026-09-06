# record-3.0.4-P3-9：keep 闭环（M4-4，R4.4，Q10 默认完整闭环）——受控改点 ①

> 日期：2026-09-06　分支：`dev-3.0.4-p3-9`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-9　SPEC：M4-4 全节（消费边界裁决 + 改动 3 条 + 边界 + 验收）+ M0-1 project_service.py 行「受控改点 ①」　PRD：R4.4 / Q10
> 前置：P3-1（golden 基线，`tests/fixtures/golden_keep_ranges_v3.0.3.json` 26509 字节，**未重采**）、P3-5（`add_range_decision`，keep range 可产出）、P3-6/P3-7（keep 入口与面板条目）、P3-8（覆层 keep 蓝系样式）。

## 0. 消费边界裁决落实（SPEC M4-4 架构师裁决的执行确认）

**keep 仅影响 `generate_subtitle_keep_ranges` 的删除区间计算，不参与导出消费**——本步零触碰导出链路（`export_service._get_confirmed_deletions` / `export_timeline` 全部未动，红线 diff 为空）。keep 与手动 delete 并存时导出服从 delete，由 §4.4 用例固化（导出消费端只认 `action=delete && status=confirmed`，keep 天然不入其视野）。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `core/project_service.py` | 改动（**受控改点 ①，本版唯一「改」点之一**） | +78/-7，5 hunk | 仅 `generate_subtitle_keep_ranges` 函数体受控改造 + 模块级合并小函数抽出（红线允许面）；**其余函数零触碰**（§2 逐 hunk） |
| `tests/test_keep_ranges_user_keep.py` | **本步新建** | +359/-0（新文件） | M4 keep 组 10 例（§4）；既有 tests/ 文件零改动 |
| `docs/3.0.4/record-3.0.4-P3-9.md`（本文）、`record-3.0.4.md` §1/§3、`plan-v3.0.4.md` P3-9 | 文档 | — | 登记与勾销 |

其余全部零改动：`main.py` / `core/` 其余文件 / `frontend/` / `pywebvue/` / `tests/` 既有文件（`git status` = 上表两项 + 文档；禁改面 diff 为空）。

## 2. 逐 hunk 改造说明（diff 审查制重点项——供负责人逐行审）

`git diff dev-3.0.4 -- core/project_service.py` = **5 hunk，+78/-7**。SPEC 锚行号（:2560-2661 基线）在本分支漂移为 :2817-2918（符号定位 `generate_subtitle_keep_ranges`），hunk 头行号以下为当前分支值。

| hunk | 位置（现分支） | 改动内容 | 对应 SPEC 条款 | 审查要点 |
|---|---|---|---|---|
| 1 | `@@ -54,6 +54,26 @@`（模块级，`compute_media_hash_deep` 之后） | **+21 纯新增**：模块级私有函数 `_merge_time_ranges(ranges)`——把原 `generate_subtitle_keep_ranges` keep_ranges 构建段的内联合并折（原 :2869-2873 的 `if start <= keep_ranges[-1][1]` 分支，任务书称 :2592-2594）**逐字抽出**：相邻或重叠（`start <= 当前合并尾`，**含相触合并**）则并入（尾取 max），否则追加；函数内先 `sorted(ranges)` 再折，故乱序输入亦正确 | SPEC 改动 1「复用 :2592-2594 同款合并逻辑抽出的小函数——抽函数是允许的重构，行为零变化」 | 判据 `<=`（相触即并）与原内联折**逐字相同**；sorted-by-start 输入下折结果与原内联折逐字节一致（golden 对拍即证，§3）；红线「允许抽出模块级/私有合并小函数」 |
| 2 | `@@ -2819,6 +2839,14 @@`（函数 docstring） | **+8 纯新增**：docstring 增 M4-4 段——confirmed keep range（不限 source）并入 keep 集、相交陈旧 subtitle_trim 剔除计入 `invalidated_count`、无 keep 时输出与 v3.0.3 逐字节一致（golden 判据） | 文档化 | 纯注释，零行为 |
| 3 | `@@ -2841,16 +2869,30 @@`（keep_ranges 构建段 → delete_ranges 补集计算之间） | **+14/-7**：① 构建段内联合并折删除，改「先收集 expanded 列表 → `keep_ranges = _merge_time_ranges(expanded)`」（行为零变化的抽函数复用，-7 即被抽走的内联折 7 行）；② **keep 集合感知（本步核心）**：`user_keeps = [(e.start, e.end) for e in edits if e.action == "keep" and e.status == CONFIRMED and e.target_type == "range"]`（**不限 source**，未来 keep range 生产者天然继承），`if user_keeps: keep_ranges = _merge_time_ranges([*keep_ranges, *user_keeps])`（排序 + 相邻合并）→ keep 区间从 delete_ranges 补集计算中**自然扣除**（补集段 :2875-2883 零改动） | SPEC 改动 1 | 插入点 = 构建段之后、补集之前（SPEC 锚 :2588-2596 → :2598-2606 之间）；`if user_keeps:` 守卫使空 keep 集路径**一行新代码都不执行**（零回退判据的结构性保证）；delete 补集/前导尾随区间逻辑零触碰 |
| 4 | `@@ -2864,6 +2906,34 @@`（`existing_edits = list(...)` 之后、new_edits 扫描之前） | **+28 纯新增**：**陈旧 trim 剔除**——`invalidated_count = 0`；`if user_keeps:` 时遍历既有 edits，凡 `source == "subtitle_trim" and action == "delete"` 且与任一 user_keep **相交**（半开区间严格相交 `edit.start < keep_end and keep_start < edit.end`，相触不算）者移除并计数；剔除后 `existing_edits` 被替换为幸存集 → 后续 `already_covered` 扫描只见幸存 edits；`if invalidated_count:` 时 `logger.info` 一条含计数 | SPEC 改动 2 | 只动 `source == "subtitle_trim"` 的 delete（手动决策永不触碰——keep 与手动 delete 并存时 delete 保留，§4.4 用例）；移除发生在 `already_covered` 扫描**之前**，使分裂出的残余区间不被陈旧整段 edit 的 ±0.05 判据误吸收（本用例段集下无影响，属语义正确性防御）；零 keep 路径整块跳过（含 log——无 keep 时零新日志行） |
| 5 | `@@ -2913,6 +2983,7 @@`（返回 data） | **+1**：data 增 `"invalidated_count": invalidated_count` 键 | SPEC 改动 2「计数入返回 data」 | 纯增键：golden 对拍只取 `keep_ranges/delete_ranges/new_edits` 三键 + edits dump，新增键不影响对拍（§3）；main.py expose 为整体透传（:2006-2011），前端忽略未知键 |

**净效果对照 SPEC 改动 3 条**：改动 1（keep 集合感知）= hunk 3②；改动 2（陈旧 trim 剔除 + invalidated_count + log）= hunk 4 + hunk 5；改动 3（零回退判据）= hunk 3① 的守卫式结构 + golden 对拍绿证（§3）。

## 3. golden 对拍绿证（零回退判据，本步最重要回归项）

- `tests/test_keep_ranges_golden.py` **既有 2 例零改动全绿**：
  - `test_generate_subtitle_keep_ranges_matches_v3_0_3_golden_byte_for_byte`——无用户 keep 的工程（固定 30 段 × padding 0.0/0.2/0.5/1.0 四档，每档独立临时工程）在**改造后代码**上重跑，输出 summary 计数 + 活动 timeline edits dump 经共享 `canonical_dumps` 序列化后与 `tests/fixtures/golden_keep_ranges_v3.0.3.json`（P3-1 于 v3.0.3 只读 worktree 采集，26509 字节）**逐字节一致**；
  - `test_golden_meta_matches_shared_definition`——golden meta 与共享采集模块防漂移。
- golden 文件**未重采**（`git status` 不含 fixtures；M0-3 约束 1 时序刚性的兑现——对拍基线仍为 v3.0.3 原始采集）。
- 逐字节一致的结构性依据：`user_keeps` 为空 → hunk 3 的 `if user_keeps:` 不执行、hunk 4 整块跳过、`invalidated_count` 恒 0 → 唯一经受的行为变化 = keep_ranges 构建折从内联改为 `_merge_time_ranges` 调用（同一判据、同一比较序，golden 四档全绿即数值恒等的直接证据）。
- 既有 subtitle_trim 断言（`tests/test_project_service.py` 2 例 + `tests/test_add_range_decision.py` 生命周期例）零改动全绿。

## 4. 测试（新建 `tests/test_keep_ranges_user_keep.py`，10 例；M4 keep 组 ≥4 达标）

段集 fixture：两段 subtitle（2.0-4.0 / 6.0-8.0），padding=0.3 → 自动 keep (1.7,4.3)+(5.7,8.0)、自动 delete (0.0,1.7)+(4.3,5.7)（总时长 = max end = 8.0，同 P3-5 生命周期例口径）。keep range 一律经真实 `add_range_decision`（M4-1 入口）+ `update_edit_decision` 确认产出。

| # | 用例（类/方法） | 锁定 |
|---|---|---|
| 1 | `TestKeepPunchThrough::test_confirmed_keep_punches_hole_in_auto_delete_gap` | **keep 打穿删除区间**（部分覆盖）：confirmed keep (4.5,5.0) 落中段 gap → `delete_ranges == 3`，deletes = (0,1.7)+(4.3,4.5)+(5.0,5.7)，keep 区间不在**任何** delete（任意 source）内；keep 条目在场；`invalidated_count == 0`（无预置 trim） |
| 2 | `TestKeepPunchThrough::test_keep_covering_whole_gap_removes_it_source_agnostic` | 整段覆盖：keep (4.3,5.7) 恰覆盖 gap → `delete_ranges == 1`，仅剩 (0,1.7)；**source 非限 manual**（本例 source="future_producer" 亦感知——不限 source 契约的正锁） |
| 3 | `TestKeepPunchThrough::test_keep_bridging_segments_merges_keep_ranges` | 跨段桥接：keep (3.5,6.5) 横跨段尾+整 gap+下段头 → 相邻合并把 keep 集塌缩为单区间 (1.7,8.0)：`keep_ranges == 1`、`delete_ranges == 1` |
| 4 | `TestStaleTrimInvalidation::test_intersecting_trim_invalidated_counted_others_kept` | **陈旧剔除 + invalidated_count**：先跑生成（2 trim edits）→ 加 confirmed keep (5.0,5.5)（只交第二条）→ 重跑：`invalidated_count == 1`（**非 2**）；不相交 trim edit 按 **id** 保留且界不变；陈旧整段 (4.3,5.7) 按界消失、代之以再生残余 (4.3,5.0)+(5.5,5.7)；`new_edits == 2`；edits 总数 4（1 旧 trim + 2 残余 + 1 keep） |
| 5 | `TestKeepVsManualDelete::test_coexist_generation_ok_delete_wins_for_export` | **导出优先级**：confirmed keep + confirmed manual delete 同区间 (4.3,5.7) 并存 → 生成 success；manual delete 按 id 存活（action=delete/status=confirmed）；keep 亦存活；自动 trim 不再覆盖该区间；`_get_confirmed_deletions`（导出消费端，零改动）输出**含 (4.3,5.7)**——delete 胜出（SPEC 边界 3 固化） |
| 6 | `TestNonConfirmedKeeps::test_pending_and_rejected_keeps_do_not_participate` | pending keep（中段 gap）+ rejected keep（前导 gap）→ 与无 keep 行为全同：`keep_ranges == 2`、`delete_ranges == 2`、trim 界恒为 (0,1.7)+(4.3,5.7)、`invalidated_count == 0` |
| 7-10 | `TestMergeTimeRanges`（4 例） | **抽函数重构自证**：相邻相触合并（`<=` 判据）+ 相触链塌缩 / 重叠与嵌套与重复与不相交 / **乱序输入**先排序后折（输出正确）/ 空与单元素 |

（M4 keep 组对 SPEC M5 矩阵的覆盖：打穿 = #1-#3；陈旧剔除 + invalidated_count = #4；golden 对拍 = P3-1 既有 2 例（§3，本步零改动全绿即判据）；keep vs delete 导出优先级 = #5。）

## 5. 门禁（`bash scripts/gates-v3.0.4.sh all`）

- pytest：**829 passed，exit 0**（819 + 10 新例，P3-1 起登记的当期期望 810 只增不减）
- ruff：All checks passed（0 problems）
- vitest：827 collected / 826 passed（唯一失败 = `useRowLayout.perf.test.ts` 已登记环境例；本步前端零改动，827 与 P3-8 持平）
- build：`bun run build`（vue-tsc --noEmit + vite build）exit 0（本执行环境 bun run 可用，脚本自动探测直用，未触发回落命令块）
- lint：`bun run lint` eslint 0 errors 0 warnings
- redline 段：全部通过——后端 diff 白名单 = 既有 8 文件零新增（project_service.py 本步 hunk 属白名单受控改点 ①）；禁改面为空；R0-2 events 零新事件；R0-3 后端断言删除 0 / 前端白名单外 expect 删除 0（本步 tests/ 纯新建 + core 纯受控改）；dev.py/build.py 零改动
- **汇总 exit 0**

## 6. 与 SPEC 的偏离登记

- **无实质偏离**。两处实现裁量（均在 SPEC 字面容许内）：
  1. SPEC 改动 1 伪码 `keep_ranges = merge_union(sorted([*keep_ranges, *user_keeps]))` 为无条件合并；实现取 `if user_keeps:` 守卫式（空集时不执行合并）——空集时 `merge_union(sorted(keep_ranges))` 本亦恒等，守卫使零回退判据**结构性成立**（无 keep 路径一行新代码不执行），语义与伪码等价且更严格。
  2. `sorted` 落在 `_merge_time_ranges` 函数体内（SPEC 伪码把 sorted 写在调用点）——对拍与乱序单测（#9 例）双证等价；构建段复用同函数时输入本已有序，sorted 为稳定幂等。
- log 取 `logger.info` 一条且仅在 `invalidated_count > 0` 时输出（SPEC「logger.info/debug 一条，含计数」；零 keep 路径零新日志行，逐字节一致的日志面延伸）。
- **行号漂移**：SPEC 锚 `project_service.py:2560-2661` 在本分支为 `:2837-2938`（P1/P2/P3 累积插入所致）；锚 :2588-2596（构建段）→ :2864-2889、:2598-2606（补集）→ :2891-2899、:2592-2594（相邻合并）→ 原内联折 :2887-2891（已抽为 `_merge_time_ranges`）、:2614-2620/:2646（edits 扫描/重生成）→ :2921-2962。符号定位全部核实。

## 7. 未验证边界（归 ★ beta.3 真机冒烟）

- **真机 keep 重跑全链路**（R4.4 验收的 UI 侧）：真机上「自动裁剪 → 框选/时间码建 keep → 确认（P3-7 面板）→ 重跑自动裁剪 → 波形旧红纹消失（P3-8 覆层随 edits 数据流自动更新）→ 导出不含 keep 区间且含并存 delete」端到端未在真机执行——服务层语义由 §4 十例锁定，GUI 数据流消费端（覆层/deleteRanges/导出预览）已有 P3-7/P3-8 各自用例，但「重跑后覆层刷新」的真人观测归 beta.3 冒烟。
- 大数据量表现（千段 + 多 keep 的重跑耗时）：本步新增计算为线性（keep 收集 O(E) + 合并 O(K log K) + 剔除 O(E·K)），未构造千段 keep 压测；P4-2 性能对账口径不含本函数，如冒烟发现卡顿再登记。
- tag `v3.0.4-beta.3` 由负责人打（执行者不打 tag）；真机冒烟待用户执行，异常走 smoke-fix（照 P1-6/P2-5 后置先例）。

# record-3.0.4-P3-5：add_range_decision expose（M4-1，R4.1）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-5`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-5　SPEC：M4-1（签名 + 契约 5 条 + 边界 + 验收）　PRD：R4.1
> 数据层前提（SPEC M4-1 探索结论）：`EditDecision(target_type="range")` 模型/持久化/patch/undo/导出（`_get_confirmed_deletions` 不过滤 target_type）全部现成；本步 = 补第 3 个后端生产者（前两个：subtitle_trim、高光虚拟仅导出时构造）+ 唯一手动入口 expose。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `core/project_service.py` | 仅新增 `add_range_decision` 一个方法（`delete_edit_decisions_batch` 之后、`_apply_main_linkage` 之前插入，单一 hunk）+ 1 行 `from uuid import uuid4` import | +102/-0 | SPEC M4-1 契约 5 条逐条落实（§2）；**`generate_subtitle_keep_ranges` 零触碰**（P3-9 受控改点 ① 才轮到它，本步 diff 零删除行自证） |
| `main.py` | 仅新 expose（`delete_edit_decisions_batch` 之后插入，单一 hunk） | +16/-0 | `@expose add_range_decision(start, end, action="delete", source="manual")`；**形态登记 = `_mark_dirty` 包裹薄透传**（§2.6） |
| `tests/test_add_range_decision.py` | **新建宿主**（该文件此前不存在） | +325/-0 | 9 例（§3），M4 expose 组 ≥6 达标（目标 8，实际 9） |
| `docs/3.0.4/record-3.0.4-P3-5.md`（本文）、`record-3.0.4.md` §1/§3、`plan-v3.0.4.md` P3-5 | 文档 | — | 登记与勾销 |

其余全部零改动：模型 / patch / 导出（`core/export_service.py` 等）/ 前端 / `pywebvue/` / 既有 tests。

## 2. SPEC M4-1 契约对照（照条施工）

1. **clamp**：`start = max(0, start)`、`end = min(upper, end)`；upper = `media.duration`（media 非 None 时）；**media 缺失**（`media is None`）→ upper = `max(s.end for s in 主轨 subtitle 段)`（同 `generate_subtitle_keep_ranges` 取段上界口径）；**空序列守卫**：media 缺失且主轨 subtitle 段为空 → 先拒，error 逐字「无媒体时长且无字幕段，无法确定范围上界」（对齐 :2581-2582 先拒空——守卫取「subtitle 段为空」即拒，同时涵盖 segments 全空与只有 silence 段两种 max() 空序列）；clamp 后 `end <= start` → 拒（error 含 `Invalid range` 与夹后值）；
2. **action 校验**：`action in ("delete", "keep")` 否则拒（模型 Literal 之外的入口校验；大小写敏感，`"DELETE"` 拒）；
3. **去重 ±0.05s**：遍历既有 edits，`action == 本次 action` 且 `|e.start - start| < 0.05 and |e.end - end| < 0.05`（**任意 status**，亦不限 target_type——与 subtitle_trim 生成侧 :2769-2775 同阈值同判据同扫描面）→ 幂等返回 `{"success": True, "data": {"edit_id": 既有id, "duplicate": True}}`——**无 patch、零写入、零 revision bump**；**跨 action 重叠放行**（keep 打穿 delete）；任意宽度重叠的非近似区间放行（`< 0.05` 严格不等号：一端差恰 0.05 亦放行）；
4. **新 edit**：`EditDecision(id=f"edit-manual-{uuid4().hex[:8]}", status=PENDING, source=<形参>, action=<形参>, target_type="range", target_id=None, priority=100)`——手动范围 **pending**（对照 subtitle_trim 的 confirmed-at-creation :2801——自动裁剪确定性可重生成，手动范围需人工审阅）；append → `_update_active_timeline(edits=...)`（既有 edits 写路径先例）→ `return self._success_patch(edits=updated)`；
5. **前端 pushSnapshot 属 P3-6/P3-7**（本步后端不管，plan 勾销行已注记）。

**校验序**（PLAN P3-5 箭头序）：No project open → clamp（含空序列守卫）→ clamp 后 end≤start 拒 → action 校验 → 幂等去重 → 新建落盘。

### 2.6 expose 形态登记（任务书要求登记所选形态）

选 **`_mark_dirty` 包裹薄透传**：`return self._mark_dirty(self._project.add_range_decision(start, end, action, source))`。依据：`_mark_dirty` docstring 明文「every @expose method that mutates the project state should `return self._mark_dirty(...)`」，且同簇邻居 `delete_edit_decisions_batch`（:1766）/ `add_analysis_results`（:1770）均此形态（`update_edit_decision` :1758 的裸透传为旧例滞后，不仿）。副作用注记：幂等 duplicate 返回 `success=True` 亦会 emit PROJECT_DIRTY（2s 防抖落盘等价数据，无害）；service 层仍零写入零 revision bump。

### 边界核对

- 不做 range 编辑修改 expose（改范围 = 删除重建，面板操作）——本步仅 add 一个方法；
- 模型 / patch / 导出零改动（§1 禁改面 diff 为空）；
- `source` 不做白名单拦截（模型层自由字符串，形参直传，默认 `"manual"`）。

## 3. 测试（新建宿主 tests/test_add_range_decision.py，9 例）

脚手架照 tests/test_translation_expose.py 惯例：monkeypatch `core.paths` / `core.project_service.get_projects_dir` 沙箱 + 真实 ProjectService（`create_project("t", ..., {"duration": 10.0})`）+ `MiloCutApi.__new__` 壳（仅 expose 例需要 `_project` / `_emit`）。导出预览消费面 = `_get_confirmed_deletions`（export_service.py:599，SPEC M4-1 锚定导出预览链的 confirmed delete 消费端）。

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | 全生命周期闭环 | 建两段跑 subtitle_trim 得 2 条 confirmed 自动区间 → `add_range_decision(2,4)` 建 pending（id `edit-manual-` 前缀 / target_type=range / target_id=None / priority=100 / patch envelope 含新 edit + revision）→ `update_edit_decision` confirm → `_get_confirmed_deletions` 含 (2,4) 与自动区间 (0,1.7)/(4.3,5.7) 并列且 3 条无重复 → `delete_edit_decisions_batch` 单条删（subtitle_trim 2 条不受扰）→ 同参重建 = **新建新 id**（幂等只对「存在既有」成立）→ 再同参 = `duplicate=True` 且 edit_id = **新建的** id、edits 数不再增 |
| 2 | clamp 越界（media 时长上界） | `(-2, 99)` → 夹为 `(0.0, 10.0)` |
| 3 | media 缺失 + 段上界 | media=None、段末 6.0 → `(0, 99)` 夹为 `(0.0, 6.0)` |
| 4 | media 缺失 + 空段先拒 | error 逐字「无媒体时长且无字幕段，无法确定范围上界」、零写入 |
| 5 | 倒序拒绝（clamp 后） | 直接倒序 (5,3) 拒；clamp 致倒序 (12,15)（end 夹到 10 < start 12）拒；error 含 Invalid range |
| 6 | action 校验 | `mute` / `DELETE` / `""` 全拒（Invalid action）、零写入 |
| 7 | 跨 action 放行 | 同区间 delete + keep 两条并存、两 id 不同、第二条非 duplicate |
| 8 | ±0.05 幂等 | 建后 confirm（覆盖「任意 status」）→ (2.03,3.98) → duplicate=True 指向既有 id、edits 不变、**`_revision` 不变**（无 patch 铁证）→ 超阈值 (2.06,4)（差 0.06≥0.05）放行新建 → 单端近似 (2.04,4.9) 放行新建 |
| 9 | expose 薄透传 | `MiloCutApi.add_range_decision(1,2)` 成功 envelope（data.edits 含新 id + revision int）、service 被调（edit 落盘）、`("project:dirty", None)` 事件 emit（_mark_dirty 接线） |

- SPEC 验收三组（全生命周期 / clamp / 跨 action）全覆盖；M4 expose 组 ≥6 达标（实际 9，超出目标 8 的 1 例 = action 校验专项，契约 2 条目补测）；
- 既有 tests 断言零删改（新宿主纯新增）。

## 4. 勘误登记（非偏离，不产生额外 diff）

1. **锚点行号漂移**：任务书引 `generate_subtitle_keep_ranges`（:2560-2661）/ :2585 / :2581-2582 / :2614-2620 / :2646 —— 实际位于 :2715-2816 / :2740 / :2736-2737 / :2769-2775 / :2801（v3.0.4 P1-4/P2 批次代码前插致整体下移 ~155 行），语义锚无歧义，按实际位置照施工；
2. **生命周期用例段布局勘误**：初版按「单段 (2,4) 于 10s media」期望 subtitle_trim 产出 2 条自动区间（含尾部 (4.3,10)）——实际生成器总时长口径 = **段 max end**（:2740，非 media.duration），单段仅产出头部 1 条；改为两段 (2,4)/(6,8) 布局，自动区间 = (0,1.7)/(4.3,5.7) 两条，并列去重断言语义不变；
3. **`_success_patch` 实为 :137**（任务书未锚行号，无冲突）：`edits=` 收 `list[EditDecision]`（`update_edit_decision` :1158 同款），非 dict 列表。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，**exit 0**）

- pytest：**819 passed**（810 基线 + 本步 9，只增不减）
- ruff：All checks passed（0 problems）
- vitest：**801 collected / 800 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，record-3.0.3 §5 遗留 #5 已登记环境例，门禁判定口径内；与 P3-4 基线持平，前端零改动）
- build：vue-tsc --noEmit + vite build 通过；lint：eslint 0/0
- 红线：R0-1 后端 diff 文件集 ⊆ 白名单（本步新增 hunk 仅 project_service.py +102 / main.py +16，均为本步登记行）；**禁改面 diff = 0**（pywebvue/ · task_manager · export_service · export_timeline · track_constraints · workflow_engine · ffmpeg_service · ffmpeg_presets · subtitle_service · timeline_utils · diff_service · migrations · models · events · config · llm_prompts · llm_service · correction_service · dev.py · build.py · frontend/，vs dev-3.0.4 全空）；R0-2 events 双侧一致；R0-3 后端断言零删改（`^-assert` = 0）；R0-3 前端白名单外零删改；R0-4 models diff 仅含 P1-1 既有 TaskType 追加；R0-5 dev.py/build.py 零改动

## 6. 偏离登记

无实质偏离。契约 5 条逐字落实（含先拒中文文案逐字、±0.05 严格不等号、uuid id 格式、pending 默认、`_success_patch(edits=…)` envelope）；测试 9 例 ≥ SPEC 明示 ≥6（目标 8，多的 1 例为 action 校验专项）。两处实现裁量已登记：① 校验序取 PLAN P3-5 箭头序（clamp → end≤start → action → 去重），SPEC 契约编号序与之同序，无冲突；② expose 形态二选一取 `_mark_dirty` 包裹（§2.6）。

## 7. 红线自证

- 改动文件集 = core/project_service.py（1 import + 单一方法 hunk，+102/-0）/ main.py（单一 expose hunk，+16/-0）/ tests/test_add_range_decision.py（新建 +325）/ 文档——`git diff dev-3.0.4 --numstat` 仅上述两生产文件，删除行数均为 0；
- `generate_subtitle_keep_ranges`（:2715-2816）零触碰（diff 无删除行 + hunk 落点 :1254/:1766 均在区间外）；
- 既有 tests/ 文件零改动；模型 / patch / 导出零改动；禁改面清单逐一 diff 为空。

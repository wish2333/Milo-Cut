# record-3.0.4-P1-5：handler 与 expose 接线（main.py + config.py）

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-5`（待负责人审查后合入 `dev-3.0.4`）
> 对应 PLAN：Phase 1 / P1-5　SPEC：M1-1（R1.5）+ M1-5（R1.2/R1.3）+ M1-3 终替换落点

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/config.py` | DEFAULTS LLM 区块追加 1 行 `"llm_translation_target_language": "en",`（+3 行注释，单一 hunk `@@ -76,6 +76,10 @@`）——前端「记忆上次语言」持久化键，P1-6 消费 | R1.1 | 只增 |
| `main.py` | **4 个纯新增 hunk，245 行新增 / 0 行删改**（`grep -cE '^-[^-]'` = 0）：① 模块级 `_TRANSLATION_LANGUAGES` 常量（9 语言 BCP-47 短码 → 英文显示名，`@@ -22,6 +22,23 @@`）；② 注册块追加 `register_handler(TaskType.LLM_TRANSLATION, self._handle_translation)` 1 行（`@@ -165,6 +182,9 @@`，置于 LLM handler 注册区末尾，与 models.py 枚举序一致）；③ `_handle_translation`（`@@ -1125,6 +1145,160 @@`，插入 `_handle_semantic_search` 之后 / region System 之前）；④ `@expose start_translation`（`@@ -2700,6 +2874,77 @@`，插入 `semantic_search` expose 之后）。**既有函数（`start_subtitle_correction` / `_handle_subtitle_correction` 等）零触碰** | R1.2/R1.5 | 只增 |
| `tests/test_translation_expose.py` | 新建（14 例，挂 M5 矩阵 M1 expose/事件组，目标 8 例左右超额达成），手法 = test_analysis_handlers.py（`MiloCutApi.__new__` + 真实 ProjectService + 捕获 `_emit`）+ test_task_cancel.py（`TaskManager._execute_task` 同步驱动 handler）+ test_llm_translation.py（mock 管线签名/返回形状） | M5 | 只增（新文件） |

`tests/` 既有文件零改动（本步 tests/ diff 仅新增文件）；禁改面（pywebvue/、task_manager、export_service、timeline_utils 等）本步零触碰。

## 2. 实现要点（与 SPEC 契约逐条对账）

### start_translation 校验序（M1-1，①-⑥顺序严格）

| 步 | 落实 |
|---|---|
| ① LLM configured | `get_llm_config().is_configured()` 同 `start_subtitle_correction` :2586-2588 模式（函数内局部 import `as _get_cfg` 同款） |
| ② project open | `self._project.current is None` → `"No project open"` |
| ③ 目标语言合法 | 非空且 `_TRANSLATION_LANGUAGES` 键命中，否则 `"Unsupported target language: {code or (empty)}"` |
| ④ 主轨存在 subtitle 段 | 解析时间轴（`timeline_id or active_timeline_id`，不存在 → `"Timeline {id} not found"`）后 `any(s.type == SegmentType.SUBTITLE ...)` |
| ⑤ 同语言 translation 轨拒绝 | `any(t.role == "translation" and t.language == target_language for t in timeline.transcript.tracks)`，文案「同语言翻译轨已存在（{code}），可清空或删除该轨后重试」（含 M1-4 写侧同款指引短语） |
| ⑥ create_task | `create_task("llm_translation", {"timeline_id": 解析后 id, "target_language": code, "track_name": 原样})`，返回 task 创建 envelope（同纠错 expose 形态） |

### _handle_translation 五步流程（M1-5）

1. **段源**：`_get_target_timeline(task)` 取时间轴（payload.timeline_id 优先、缺省 active，同纠错 handler :900-901）；`collect_confirmed_deleted_seg_ids(timeline)` 排除 confirmed-deleted（:908 先例）后过滤 `type == SUBTITLE`；空段源 `raise ValueError("No subtitle segments to translate")`；
2. **prompt 终替换**：`get_effective_prompt("translation", timeline.llm_prompts)`（项目 prompts 取法同纠错 handler :928-930）→ `.replace("{{target_language}}", _TRANSLATION_LANGUAGES[target_language])`（英文显示名）→ `if "{{" in system_prompt: raise RuntimeError(...)` **fail-fast**（防 system_override 拼写错位静默降级，M1-3 契约 2）；
3. **管线**：`analyze_subtitle_translation(segments, target_language, cancel_event=..., progress_cb=..., system_prompt=...)`——**传 code**（已核实 llm_service.py:1700-1702 docstring + :1963 实现：形参仅用于校验/日志，不进 prompt，语言信息由 system_prompt 携带）；失败 → `self._emit("llm:analysis_failed", ...)` + `raise RuntimeError`（task:failed 零落盘，同纠错 :948-951 模式）；`track_name` 缺省补全 = 语言显示名（步骤 3 前完成）；
4. **完成时时间轴钉扎**（R3 must-fix）：`timeline_id != self._project.current.active_timeline_id` → `raise RuntimeError("翻译期间已切换时间轴，结果已丢弃，请回到原时间轴重新发起")` **零落盘**；一致 → `create_translation_track(timeline_id=..., name=track_name, language=code, items=[...], bind=True)`，items 由 translations + handler 快照段组装（`{segment_id, start, end, text}`；start/end 取任务启动时快照——最终落盘时间由写侧以**当下**主轨为准逐字段覆盖，快照值仅符合契约形状）；
5. **事件与返回**：写侧 success=False（重复语言/全落空/钉扎双保险）→ `raise RuntimeError`（error 透传）；成功 → emit `LLM_TRANSLATION_COMPLETED`（payload = `{track_id, track_name, language, written_count, target_count, uncovered_ids, ledger}`，前五项从 `data["meta"]["translation"]` 取、ledger 来自管线 data.ledger；常量经函数内局部 `from core.events import LLM_TRANSLATION_COMPLETED` 引入——不动模块头 import 行即保持四 hunk 红线，事件值 `llm:translation_completed` 与 P1-1 登记双侧同步）+ emit `"llm:token_usage"`（纠错 :982 惯例）+ 返回 `{报告五项, token_usage, ledger, "project": model_dump()}`（:984-990 模式；TaskManager 剥离 project 后前端 get_project 刷新）。

### 失败语义五情形（SPEC M1-5 表逐条落实）

| 情形 | 落实 | 测试 |
|---|---|---|
| 任一批重试仍失败 | 管线返回 success=False → handler raise（task:failed，**零落盘**——写侧在成功分支之后才调用） | `test_pipeline_failure_fails_task_zero_writes` |
| 用户取消 | TaskManager 取消语义透传（cancel_event 接线同纠错；管线逐批检查、返回 `"Cancelled"` → handler raise → task_manager 归类 CANCELLED，已完成批不写入——管线层已有 test_llm_translation.py 取消用例，handler 侧不重复构造） | （管线层既有，本步接线同款） |
| 全批成功但主轨被增删段 | 落盘已配对部分 + completion payload 携带 `uncovered_ids`（写侧 M1-4 对账，事件 payload 从 meta 取） | `test_uncovered_ids_ride_completion_event`（mock 管线内删段模拟运行期删除） |
| 运行期手动建同语言轨 | 写侧 M1-4 双保险拒绝 → handler 透传 error（含指引文案）task:failed | （写侧已有 test_translation_track.py:4；handler 透传路径与管线失败同构） |
| 运行期切时间轴 | 完成时钉扎校验 failed、零落盘、error 含「回到原时间轴」 | `test_timeline_switch_fails_zero_writes`（mock 管线内切 active 时间轴） |

**并发约束**：未构造任何并发写断言（UI 单飞 + 测试序列化为 MVP 约束）；未加 MiloCutApi 级锁（3.0.5 候选登记，M1-5 裁决）。

## 3. 红线命令实际输出

- **`git diff v3.0.3 --stat -- core/ main.py`**（本步 + P1-1~P1-4 累计）：config.py +4 / events.py +3 / llm_prompts.py +23 / llm_service.py +384 / models.py +2 / project_service.py +155 / main.py +245，共 **816 insertions 0 deletions**，全部在 M0-1 白名单内（本步新增 config.py 与 main.py 两条登记，见总 record §3）✅
- **本步自身 diff（vs dev-3.0.4）**：core/config.py +4（唯一 DEFAULTS 增行 + 注释）、main.py +245（四 hunk 纯新增）、tests/test_translation_expose.py 新建；`git diff main.py | grep -cE '^-[^-]'` = **0** ✅
- **禁改面 diff**（pywebvue/、task_manager、export_service、export_timeline、track_constraints、workflow_engine、ffmpeg_service、ffmpeg_presets、subtitle_service、timeline_utils、diff_service、migrations、models、events、llm_prompts、llm_service、project_service、correction_service、dev.py、build.py）：本步零触碰（门禁 R0-1 段 PASS）✅
- **R0-3 断言零删改**：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = 0；本步 tests/ 只新增文件 ✅

## 4. 门禁（bash scripts/gates-v3.0.4.sh all）

- pytest：**774 passed**（760（P1-4 基线）+ 本步新增 14，全绿）
- ruff：All checks passed（触及文件 core/config.py / main.py / tests/test_translation_expose.py 三零）
- vitest：756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确；本步纯后端未触前端）
- build（vue-tsc + vite，bun 回落 node 等价命令）：通过；lint（eslint）：0/0
- 红线 R0-1 ~ R0-5 + dev/build.py：全部 PASS（明细见 §3）
- 门禁 exit code：**0**

## 5. 测试清单（5 类 14 例 → M5 矩阵 M1 expose/事件组 ≥5 达成）

| # | 用例 | 对应要求 |
|---|---|---|
| 1 | `test_llm_not_configured`：① 分支短路，无 task 创建 | 校验序 ① |
| 2 | `test_no_project_open`：② 分支 | 校验序 ② |
| 3 | `test_invalid_language_rejected`：""/xx/EN 三态均拒（③ 分支，参数化内联） | 校验序 ③ |
| 4 | `test_empty_main_track_rejected`：清空主轨 → "No subtitle segments to translate" | 校验序 ④ |
| 5 | `test_duplicate_language_rejected_with_guidance`：预置同语言 translation 轨 → 文案含「可清空或删除该轨后重试」 | 校验序 ⑤ |
| 6 | `test_happy_path_creates_task_with_payload`：task 类型/payload 三键逐字断言（timeline_id=default 解析后值） | 校验序 ⑥ |
| 7 | `test_handler_registered_for_task_type`：`_register_task_handlers` 后 `tm._handlers[LLM_TRANSLATION] == api._handle_translation` | 注册存在性 |
| 8 | `test_dispatch_completes_and_writes_track`：TaskManager 同步驱动 → completed、轨/绑定 3+3（offset 全 0）、track_name 缺省=English、完成事件 payload 七键、token_usage、task result 含 project 且 TASK_COMPLETED 事件剥离 project | 调度 + 落盘 + 事件 |
| 9 | `test_pipeline_failure_fails_task_zero_writes`：管线失败 → failed + 零轨 + 无完成事件 | 五情形 1 |
| 10 | `test_uncovered_ids_ride_completion_event`：mock 管线内删主轨段 → written=2/target=3/uncovered=[该 id] 随事件上报 | 五情形 3 |
| 11 | `test_timeline_switch_fails_zero_writes`：mock 管线内切 active 时间轴 → failed、error 含「翻译期间已切换时间轴」+「回到原时间轴」、两时间轴均零轨零绑定、无完成事件、TASK_FAILED 事件携带该 error（**M0-3 约束 4 边界用例**） | 五情形 5 |
| 12 | `test_display_name_injected_no_placeholder_left`：捕获 system_prompt 含 "Japanese"、无 `{{target_language}}`、无 `{{`；service 层 target_language 收 code | 终替换正确 |
| 13 | `test_residual_placeholder_fails_fast_zero_writes`：system_override 含 `{{target_lang}}`（他占位符）→ failed、error 含 "placeholder"、**管线未被调**、零轨 | 残留 fail-fast |
| 14 | `test_catalog_matches_spec_list`：9 语言键集与显示名抽查（单一事实来源防漂移） | 语言清单 |

## 6. 未验证边界

- **取消路径的 handler 侧专测**：cancel_event 接线与纠错 handler 逐字同款，管线层取消语义（已完成批不写入）已由 test_llm_translation.py 既有用例固化；本步未重复构造 handler 级取消（同构路径，五情形表第 2 行按管线层既有覆盖登记）；
- **真实 LLM 端到端**：全部走 mock 管线（P1-3 已固化管线对 call_llm 的契约）；真实提供商下的批窗/重试/429 降级随 beta.1 真机（M5）；
- **`llm_translation_target_language` 的消费端**：本步只落 DEFAULTS 键（R1.1），后端无读取方——P1-6 前端语言记忆经既有 settings 保存通路写回、启动时读默认值；
- **expose 分支的并发窗口**（⑤ 校验与 ⑥ 建任务之间用户手动建轨）：由写侧 M1-4 双保险兜底（SPEC 裁决的防线分工），未构造竞态断言（并发约束）；
- **`timeline_id` 形参传非 active 时间轴的 expose 路径**：校验序 ④⑤ 按显式时间轴判定，handler 钉扎同样按显式 id——与 active 缺省路径同构，未单列用例。

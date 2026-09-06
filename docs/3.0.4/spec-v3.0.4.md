# v3.0.4 实施规格说明（SPEC）

> 版本：3.0.4（定稿——2026-09 随 PRD 定稿；实施层裁决与 PRD 冲突处以本文为准，冲突清单见文末附录 C）
> 上游：[PRD-v3.0.4](./PRD-v3.0.4.md) / [3.0.4 开发探索报告](./探索报告-v3.0.4.md)（file:line 证据库）/ record-3.0.3 §4/§5 遗留登记
> 基线：tag `v3.0.3`；行号引用以探索报告同基线工作区（`55c68da` 之后）为准，漂移时以符号名检索兜底
> 本文职责：把 PRD 的 4 个特性（S1-S4）细化为**改动点（file:line）/ 契约 / 边界 / 验收**四段齐全的可实施契约。所有「裁决」栏为本 spec 在实施层做出的唯一性决定。每条契约锚定探索报告章节或本人抽查代码（附录 B 列抽查清单）。

---

## 概要

### 模块划分

| 模块 | 内容 | 对应 PRD | 批次 |
|---|---|---|---|
| M0 | 全局契约：红线「只增不改」的可执行定义、后端改动登记表、数据契约现状、交付顺序 | §1 全部前置 | 全程 |
| M1 | AI 翻译生成翻译副轨：任务/管线/prompt/批量写/事件/前端闭环 | S1（R1.1-R1.4） | P1 |
| M2 | AI 纠错感知当前轨：payload 透传/段源/pending 作用域化/accept 超集 patch/门控 | S2（R2.1-R2.5） | P2 |
| M3 | 前端顺带批：T1-A 编辑扫掠覆盖副轨 + X1 lane 建段接线 + X2 搜索数据源 | S3（R3.1-R3.3） | P3 |
| M4 | 手动剪辑范围：add_range_decision / 手势 / 面板分组 / keep 闭环 | S4（R4.1-R4.4） | P3 |
| M5 | 测试与门禁：用例矩阵、门禁命令、真机冒烟清单 | §9 全部 | 全程 |

### 规模注记（R3 天数复核，供 PRD/PLAN 对齐；最终天数由产品经理裁决）

| 批次 | 复核人日 |
|---|---|
| P1（M1） | 4.5 – 6 |
| P2（M2） | 3 – 4 |
| P3（M3 + M4） | 4 – 5.5 |
| P0 + P4（全局契约 + 终检） | 1.5 – 2 |
| **合计** | **13 – 17.5** |

该区间为 R3 逐触点核验后的复核值，写入目的仅为 PRD/PLAN 排期对齐；不做承诺口径。

---

## M0: 全局契约

### M0-1: 红线「只增不改」的可执行定义（PRD §1 五条的逐文件白名单化）

**R0-1 允许 diff 的后端文件清单**（`git diff v3.0.3 -- core/ main.py` 的全部输出必须落在下表内，且每条 hunk 对应一个 R 编号）：

| 文件 | 允许的 diff 内容 | 登记号 |
|---|---|---|
| `core/models.py` | **仅** `TaskType` 枚举追加 `LLM_TRANSLATION = "llm_translation"`（追加于 models.py:27-45 的 LLM 区块末尾，1 行 + 注释）。既有模型字段/签名/默认值/校验器零改动 | R1.2 |
| `core/events.py` 与 `frontend/src/utils/events.ts` | **仅** 双侧各新增 1 个常量：`LLM_TRANSLATION_COMPLETED = "llm:translation_completed"` / `EVENT_LLM_TRANSLATION_COMPLETED = "llm:translation_completed"`，同一改动内提交 | R1.4 |
| `core/config.py` | **仅** DEFAULTS 字典（config.py:58-91）追加 `"llm_translation_target_language": "en"` 一行 | R1.1 |
| `core/llm_prompts.py` | **仅** 新增 `_TRANSLATION_SYSTEM` 常量 + `DEFAULT_PROMPTS["translation"]` 注册项（注册表 models 锚 llm_prompts.py:142-171；`params` 必须为 `{}`，原因见 M1-3） | R1.2 |
| `core/llm_service.py` | **仅** 新增 `analyze_subtitle_translation(...)` 及其模块级私有辅助（复刻 analyze_subtitle_correction 骨架，llm_service.py:935-1218） | R1.2 |
| `core/project_service.py` | 新增 `create_translation_track`（M1-4）与 `add_range_decision`（M4-1）两方法；**受控改点 ①**：`generate_subtitle_keep_ranges`（project_service.py:2560-2661）keep 感知 + 陈旧 trim 剔除（M4-4，无用户 keep range 时行为逐字节不变） | R1.3 / R4.1 / R4.4 |
| `core/correction_service.py` | **受控改点 ②**：`store_subtitle_corrections` / `get_subtitle_corrections` / `accept_subtitle_correction` / `reject_subtitle_correction` 的 track 作用域化与 patch 超集（M2-2/M2-3；互清现状锚 correction_service.py:61-65，accept 现状锚 :154-226） | R2.2 / R2.3 |
| `main.py` | 新增 `_handle_translation` + 注册（main.py:140-167 注册块追加 1 行）+ `start_translation` / `add_range_decision` 两个 @expose；**登记改点**：`start_subtitle_correction`（main.py:2566-2602）增 `track_id: str = ""` 形参、`_handle_subtitle_correction`（:889-990）增副轨分支（M2-1） | R1.2 / R1.5 / R2.1 / R4.1 |
| `tests/` | 只增新文件/新用例；既有断言零改动（白名单见 R0-3） | 全部 |

**禁改面**（diff 必须为空）：`pywebvue/**`、`core/task_manager.py`、`core/export_service.py`、`core/export_timeline.py`、`core/track_constraints.py`、`core/workflow_engine.py`、`core/ffmpeg_service.py`、`core/ffmpeg_presets.py`、`core/subtitle_service.py`、`core/timeline_utils.py`、`core/diff_service.py`、`core/migrations.py`、`core/asr_service.py`、`core/plugin_manager.py`、`core/proxy_manager.py`、`core/media_server.py`、`core/bridge_service.py`、`core/paths.py`、`core/logging.py`、`dev.py`、`build.py`。

**R0-2 events 双侧同步**：新增事件常量双侧同 commit；门禁见 M5 命令块（口径：**本版新增事件名的双侧存在性**，非全量集合比对——events.ts:48-50 含 2 个前端专属 demo 常量，events.py 无对应项，属既有现状非违规）。

**R0-3 既有测试断言零改动**：唯一白名单 = `frontend/src/components/workspace/TranscriptRow.test.ts:270-275`「never enters text edit under globalEditMode」随 R3.1 裁决反转同步反转（断言与意图一起改，登记于 record 反转清单）。后端 `tests/` 断言零删改。

**R0-4 主轨零回退**：判据可执行化——
- `track_id` 缺省调用（`start_subtitle_correction` 既有签名/`store/accept/reject` 主轨路径）：与 v3.0.3 行为序列一致（既有断言不改全绿即证）；
- 无手动 range / keep 数据的工程：`generate_subtitle_keep_ranges` 输出与 v3.0.3 **逐字节一致**（新增 golden 对拍用例，M4-4）；
- 主轨视图交互（波形手势/列表/搜索）：默认态（新增 toggle 全部 OFF）与 v3.0.3 一致；
- 仅两处受控「改」：R4.4 keep 感知（触发条件=存在 confirmed keep range）、R2.2 互清作用域化（触发条件=track_id 非空 store；主轨序列观测行为不变，`test_store_clears_previous_corrections` 类断言零改动通过）。

**R0-5 diff 审查制**：每 phase 门禁产出 `git diff v3.0.3 --stat -- core/ main.py` 清单，对照**后端改动登记表**（附录 A 模板，record 逐 phase 追加）逐条核对 R 编号；无对应者补登记或回退。

### M0-2: 数据契约现状（实施前提，勿改）

- **ProjectPatch 层**：`revision / timeline_id / segments? / edits? / analysis? / tracks? / bindings? / media? / active_timeline_id? / full_project? / meta?`（models.py:408-459）；层语义 = 活动时间轴对应字段**整体替换**。`_success_patch(meta=None, **layers)`（project_service.py:137-155）是层 patch envelope 的唯一构造入口——**任何多层数据写入必须单 patch**（revision +1）。
- **undo 层**：`UndoLayer = "segments" | "edits" | "analysis" | "tracks" | "bindings"`（frontend/src/utils/undoRecords.ts:15-23）；`pushSnapshot(project, layers, label)` 在补丁应用**前**捕获（useUndoRedo.ts:48-58）。注意 **analysis 是合法捕获层**——凡写路径同时移除 AnalysisResult 的（M2-3 accept/reject），捕获层必须含 `analysis`。
- **轨道 id 命名空间**：track `trk_{uuid4().hex[:8]}`、track 段 `track_{track_id}_seg_{start:.3f}`、binding `bind_{uuid4().hex[:8]}`（project_service.py:634/637/670；docstring models.py:142-148「merge / edit-decision systems can never match them against main-track segments」）。翻译轨沿用同一命名空间生成器。
- **binding 模型**：`main_segment_id ↔ extension_segment_id + start_offset/end_offset`（= extension − main，秒）（models.py:157-170）。当前唯一 binding 生产者 = `import_srt_as_track`（300ms 容差贪心 1:1，project_service.py:650-677）；M1-4 成为第二个生产者（按 id 精确 1:1、offset=0）。
- **AnalysisResult.detail: str**：结构化 payload JSON 编码（correction_service.py:82-90 先例），轨道归属走 detail JSON 新键 `track_id`，模型零变更（PRD §0.2 MVP 约束）。
- **事件常量**：core/events.py:1-56 ↔ frontend/src/utils/events.ts:1-50 镜像（demo:* 2 项前端专属）。
- **门禁基线**：pytest 716 passed；vitest 755 passed / 756 collected（唯一失败 = `useRowLayout.perf.test.ts` 挂载墙钟，已登记环境例豁免）。

### M0-3: 交付顺序强制

```
P1: M1（R1.2 管线 → R1.3 批量写 → R1.4/R1.5 事件与前端）→ v3.0.4-beta.1
    （R1.1 前端入口卡片依赖的 mainSegments 透传链在 P1 交付，P3 的 X2 复用，见 M3-3）
P2: M2（R2.1 后端 → R2.2/R2.3 → R2.4 前端；R2.5 为 P2 尾项，S4 开工即让位）→ beta.2
P3: M3（顺序强制 R3.1 → R3.2 → R3.3）→ M4（X1 合入后再上 M4-2 手势，同文件防冲突）→ beta.3
P4: M5 终检 + README_zh 回填 + 双平台真机清单（含 3.0.3 顺延债）→ RC → 正式
```

M3 的 R3.1/R3.3 纯前端不依赖后端，可与 P1 并行**开发**，但合入统一走 P3 门禁。

**R3 增补的交付顺序约束（4 条，与上图同为强制）**：

1. **golden 先行**：M4-4 的 keep-ranges golden 对拍基线，必须在触碰 `generate_subtitle_keep_ranges`（project_service.py:2560-2661）**之前**、于 v3.0.3 基线工作区采集固化（产物 = tests/ 下 golden 数据文件，随 P3 首个 commit 入库）。先改后采会让「基线」自带本版改动，对拍失去意义。
2. **props 链 P1 合并**：M1-6 的 `mainSegments` 与 M2-4 的 `active-track-id` / `active-track-name` 走同一条 WorkspacePage → Timeline（:727-743）→ AIAssistantPanel 透传链，**P1 一次改动全部接通**（Timeline 本已接收 activeTrackId，Timeline.vue:348，缺的只是 Timeline → 面板一级）；M2-4 在 P2 只加门控消费，不再动 props 链——消除 P1/P2 两阶段对 Timeline.vue 同一区域的重复改动冲突窗口。
3. **M4-3 可与 M4-1 并行开发**：建议面板分组与覆层只消费 edits 数据流，不依赖 `add_range_decision` expose 的落地顺序；但「建→审→确认→删除」生命周期验收必须在 M4-1 合入后串行执行。
4. **切轨后完成分支进边界用例**：M1-5「完成时时间轴已切换 → 钉扎校验 failed」分支列入 M5 用例矩阵 M1 expose/事件组的边界用例（uncovered 类），不得只测 happy path。

---

## M1: AI 翻译生成翻译副轨（P1 / S1）

数据层全预留（探索报告 §4.1）：`SubtitleTrack.role` 含 `"translation"` + `language`（models.py:151-153）、`add_track(role=)`（project_service.py:1637-1658）、`export_bilingual_subtitle` 要求 BOUND 段（export_service.py:467-545）、播放双语第二行（SubtitleOverlay）全部现成。本模块只补「翻译管线」。

### M1-1: 任务类型与注册（R1.2）

**改动**：

| 触点 | 内容 |
|---|---|
| core/models.py:45 | `TaskType` 追加 `LLM_TRANSLATION = "llm_translation"` |
| main.py:140-167 | 注册块追加 `self._task_manager.register_handler(TaskType.LLM_TRANSLATION, self._handle_translation)` |
| main.py（expose 区） | 新增 `@expose start_translation(target_language: str = "", timeline_id: str = "", track_name: str = "") -> dict` |

**start_translation 校验序**（短路返回 `{"success": False, "error": …}`）：① LLM configured（同 main.py:2586-2588 模式）→ ② project open → ③ 目标语言合法（非空、在 M1-6 清单内）→ ④ 主轨存在 subtitle 段 → ⑤ **同语言 translation 轨拒绝**：`any(t.role == "translation" and t.language == target for t in tl.transcript.tracks)` 命中即拒，error 文案含「可清空或删除该轨后重试」→ ⑥ `create_task("llm_translation", {timeline_id, target_language, track_name})`。

**边界**：`_workflow_accumulate` 路径不适用（workflow_engine 不纳入翻译 step，PRD §0.2 不做）；payload 不携带 build 类标志。

**验收**：expose 契约用例（配置缺失/空主轨/重复语言/正常路径四分支）；`create_task` 可启动且 handler 被调度（mock LLM）。

### M1-2: `analyze_subtitle_translation` 契约（R1.2）

**签名**：`analyze_subtitle_translation(segments: list[dict], target_language: str, *, config=None, cancel_event=None, progress_cb=None, system_prompt: str | None = None) -> dict`，返回 `{"success": True, "data": {"translations": [{segment_id, translated_text}], "token_usage": {...}, "ledger": BatchLedger}}`。

**复刻纠错骨架的部分**（锚 llm_service.py:935-1218，逐项同源）：
- 批窗构建：`llm_correction_batch_size`（30，config.py:70）+ 字符预算收缩 `llm_max_batch_chars`（4000，config.py:77），算法同 :992-1008；
- 并发池 `llm_concurrency`（5，config.py:74）、`BatchLedger`、每批一次重试、连续 429 转串行；
- opaque id（批内 t1..tN 映射回真实 segment_id）；
- 4 层 JSON 解析兜底（非 json_mode 提供商 Qwen/GLM/Ollama 依赖此路径，llm_service.py:258-259 仅 OpenAI/DeepSeek 启用 response_format）；
- cancel_event 逐批检查；progress_cb 批粒度百分比。

**与纠错的关键差异**：

| 项 | 纠错 | 翻译 |
|---|---|---|
| coverage 校验 | 「无需修正不输出」，输出 ⊆ 目标 | **反向：全量输出守恒**——输出 id 集合 ≠ 目标 id 集合（漏译或多译）的批重试后仍失败 → 记 ledger 失败，**整任务 fail、零落盘**（M1-6 语义） |
| 输出字段 | corrected_text/changes/category | `segment_id + translated_text`（无 changes/category） |
| 上下文窗口 | 段源 ±ctx（`llm_correction_context_window`=5） | 同为**源文** ±ctx 窗口（见下裁决） |

**裁决（覆盖 PRD R1.2「定稿译文滑动窗」）：并发 5 与「上一批末尾已定稿译文随下批携带」互斥**——correction 骨架在派发前**预构建全部批 payload**（llm_service.py:1013-1019），并发执行下批 N+1 构建时批 N 未定稿；引入批间依赖即事实串行（≈5× 时延）。本版取舍：**保留并发，上下文 = 源文 ±ctx 窗口**（术语一致性由 prompt 约束 + 三层覆盖 glossary 参数承担）；「定稿译文滑动窗」登记版本池（需串行模式/config 开关，3.0.5 候选）。回写 PRD 项见附录 C。

**边界**：段源由 handler 传入（M1-5），service 层不做轨道/删除过滤；不做增量补译（ledger.uncovered 登记后续增强）。

**验收**：全量守恒（漏译批/多译批进 ledger 且任务失败）；429 降级路径复用纠错语义（mock 断言转串行）；非 json_mode 4 层解析专项 mock（坏 JSON/围栏代码块/前后缀噪声/单引号）；取消中途退出且已完成批不落盘。

### M1-3: prompt 注册与 `{{target_language}}`（R1.2）

**改动**：core/llm_prompts.py 新增 `_TRANSLATION_SYSTEM`（要求：逐条输出 JSON 数组、id 原样回传、目标语言位 `{{target_language}}`、不得增删条目）+ `DEFAULT_PROMPTS["translation"] = {"system": _TRANSLATION_SYSTEM, "params": {}}`。

**关键裁决——`params` 必须为 `{}`**：`_inject_placeholders`（llm_prompts.py:197-210）只遍历注册 params 的 key，`_format_param`（:178-194）对未注册 key 返回 **空串**——若把 `target_language` 注册进 params，占位符会被替换成空串、语言信息丢失。契约：
1. 注册 params 留空 → `{{target_language}}` 原样穿透 `get_effective_prompt`（三层：硬编码默认 → 全局 settings llm_prompts → 项目 timeline.llm_prompts 覆盖，llm_prompts.py:217-261；system_override 早返回路径同样穿透）；
2. handler 在拿到 effective prompt 后执行 `system_prompt.replace("{{target_language}}", target_language)`，并断言替换后无 `{{` 残留（残留即 fail-fast，防用户 system_override 拼写错位静默降级）。

**边界**：不新增 prompt 参数键；语言名注入用目标语言清单的英文显示名（M1-6）。

**验收**：占位符穿透三层各一路用例；override 路径替换正确；残留占位符 fail-fast 用例。

### M1-4: 批量写方法 `create_translation_track`（R1.3）

**签名**：`ProjectService.create_translation_track(self, timeline_id: str, name: str, language: str, items: list[dict], bind: bool = True) -> dict`，`items = [{"segment_id", "start", "end", "text"}]`（主轨段 id + 复制的主轨时间 + 译文）。

**契约**：
1. **重复语言拒绝**（同 M1-1 ⑤判据，双保险在写侧再查一次——任务运行期间用户可能手动建了同语言轨）；
2. 幂等对账：`items` 的 `segment_id` 逐个对照**当下**主轨 subtitle 段——仍存在 → 生成 track 段（同 start/end 复制主轨时间、id 走 `track_{track_id}_seg_{start:.3f}` 命名空间）；已不存在 → 进 `uncovered_ids`（**不静默**）；全部落空 → `{"success": False, "error": "所有目标段已被删除"}`；
3. bind=True：按 `segment_id ↔ 新 track 段` 精确 1:1 建 `TrackBinding(start_offset=0.0, end_offset=0.0)`（offset=0 因时间完全复制）；
4. **单 patch 落盘**：照 `import_srt_as_track` 的整体替换写法（project_service.py:679-693 锚）——`transcript.model_copy(update={"tracks": [*旧, 新轨], "bindings": [*旧, *新]})` → `_update_active_timeline` → `return self._success_patch(tracks=…, bindings=…)`。注意该写法的两个下游均**绑定当下 active timeline**（`_update_active_timeline` 取 active；`_success_patch` 的 `timeline_id` 恒取 `active_timeline_id`，project_service.py:151）——写入目标的时间轴正确性由契约 6 钉扎保证；
5. 返回 data 附 `{track_id, written_count, target_count, uncovered_ids}`；
6. **时间轴钉扎双保险（R3 补）**：方法入口断言 `timeline_id == self._current.active_timeline_id`，不符 → `{"success": False, "error": "Timeline no longer active: 翻译期间已切换时间轴"}` 零写入——与契约 1 的重复语言写侧再查同模式（任务运行 1-3 分钟，校验防的是「handler 侧校验通过后、写侧执行前」的极端窗口与未来新调用方漏检）。方案选型理由见 M1-5 步骤 4 裁决。

**禁止循环调用 `add_track_segment` 的原因（量化）**：一段一 patch = 每段一次桥接往返 + 一次 revision 递增 + 一条 undo 历史；千段工程 = 1000 次往返 + revision +1000 + undo 栈单次操作被污染为千条（3.0.2 smoke 已证此坑并为此把「清空」改成一次操作）。单 patch = revision +1、undo 一次回退整轨。

**边界**：不做自动合并/增量重译（PRD Q7）；不动主轨 segments；`_enforce_segment_sort_invariant` 不适用（track 段天然按主轨序）。

**验收**：千段级（参数化 1000 段）单 patch：revision 恰好 +1、tracks/bindings 层完整、undo 一次回退整轨含 bindings；重复语言拒绝；id 落空对账（部分落空落盘 + uncovered 上报 / 全部落空拒绝）。

### M1-5: `_handle_translation` 流程（R1.2/R1.3）

照 `_handle_subtitle_correction`（main.py:889-990）模式，后台线程：

1. 读主轨 subtitle 段，**排除 confirmed-deleted**（`collect_confirmed_deleted_seg_ids(timeline)`，语义对齐导出映射，main.py:908 先例）；
2. resolve prompt（`get_effective_prompt("translation", project_prompts)` + `{{target_language}}` 终替换）；
3. `analyze_subtitle_translation(...)`（M1-2）；失败 → `raise RuntimeError`（task:failed，零落盘）；
4. 成功 → **时间轴钉扎校验（R3 补，must-fix）**：`payload.timeline_id != project.active_timeline_id` → 任务 failed（error 文案「翻译期间已切换时间轴，结果已丢弃，请回到原时间轴重新发起」），**零落盘**；一致 → `create_translation_track(...)`（写侧 M1-4 契约 6 双保险）；
   **钉扎方案裁决（fail-fast 校验 ✅ / 改 `_update_timeline_by_id` 按 id 写 ❌）**：选 fail-fast。理由：① `_success_patch` 的 `timeline_id` 恒取 active（project_service.py:151）——按 id 写要么返回错标 timeline_id 的 patch（前端 `applyProjectPatch` 会把 tracks/bindings 层**错应用到 active 时间轴**），要么改走 `_success_full_fallback` 全量 envelope（O(project) 刷新正是 M2-3 要消灭的路径，且绕开「多层数据写入必须单 patch」红线）；② 前端在任务 start 前压的 undo 快照（`["tracks","bindings"]`）绑定快照时刻的 active 时间轴，完成后写入非活动时间轴会使快照与落盘目标错位，undo 跨时间轴回退即破坏；③ 频率与成本：1-3 分钟任务期间切时间轴是低频操作，fail-fast 的代价 = 一次重试，按 id 写的代价 = 新写路径 + envelope 分叉 + undo 语义破洞。`_update_timeline_by_id`（project_service.py:2496-2511）本身存在且可用，但启用它的前提（patch 构造器支持按 id + undo 快照跨时间轴语义）均不在本版范围；
5. emit `llm:translation_completed`（payload = `{track_id, track_name, language, written_count, target_count, uncovered_ids, ledger}`）+ emit `llm:token_usage`；
6. 返回 `{..., "project": model_dump()}`（task:completed 剥离后前端走 `get_project` 刷新，同纠错模式 main.py:984-990）。

**失败/取消/部分失败语义（裁决汇总）**：

| 情形 | 行为 |
|---|---|
| 任一批重试后仍失败（coverage 反向不过/解析失败/API 错误） | 任务 failed，**零落盘**（PRD R1.2 验收「已完成批不写入」） |
| 用户取消 | TaskManager 取消语义，已完成批不写入 |
| 全批成功但主轨被增删段 | 落盘已配对部分 + completion payload 携带 `uncovered_ids`，前端 toast + 结果面板明示（US-T3-4） |
| 运行期间手动建了同语言轨 | 写侧拒绝（M1-4 ② 前置），任务 failed 带指引文案 |
| 运行期间切换了时间轴（R3 补） | 完成时钉扎校验失败 → 任务 failed，零落盘，error 带回到原时间轴重试的指引文案 |

**并发约束（R3 勘误，must-fix #5）**：Round 2 版「写线程安全由 ProjectService 内部写路径保证，与 correction store 同模式」为**假前提**——project_service.py 全文无任何锁，后台任务线程与 UI 桥线程的读-改-写序列本就可能交错（v3.0.3 既有状况，非本版引入；本版不扩大暴露面）。3.0.4 MVP 约束固化为：① **UI 单飞**——同一时刻至多一个 LLM 任务在跑（useLlmTasks.isRunning 门控既有），任务运行期间用户写操作经 patch 协议的 revision 校验兜底（陈旧即拒）；② **测试序列化**——M2-2 双轨 store 等用例一律按先后序列化调用，不构造并发写断言。MiloCutApi 级写锁（覆盖全部 @expose 入口与 task handler 生命周期）登记 **3.0.5 候选**，不入本版白名单——锁需横扫 main.py 全部入口，违反最小 diff 红线，且死锁面（tick 循环内回调重入）需单独设计。

**验收**：五情形各有 pytest（mock LLM + 真服务，含运行期切时间轴 → 钉扎校验 failed 零落盘，M0-3 约束 4 已将该分支列入 M5 边界用例）；`uncovered_ids` 非空时事件 payload 携带。

### M1-6: 前端闭环（R1.1/R1.4）

**改动**：

| 触点 | 内容 |
|---|---|
| AIAssistantPanel.vue:125-147 | features 数组追加第 4 卡「翻译为新副轨」（icon/title/description 同款）；轨模式下智能删除/工作流置灰逻辑属 M2-4（**精华入口不在本面板**——features 仅 3 卡：智能删除/纠错/搜索；精华在 Timeline 第三 tab，其门控触点在 M2-4 补，R3 勘误），本卡在主轨视图可用 |
| AIAssistantPanel.vue:22 | `FeatureKey` 联合类型追加 `"translation"`（现状 `"smart_delete" \| "subtitle_correction" \| "search"`，R3 补触点——新卡 key 需进联合类型，否则 TS 编译错） |
| WorkspacePage.vue:1385 / Timeline.vue:727-743 / AIAssistantPanel | 新增 `mainSegments` 透传链（WorkspacePage `:main-segments="segments"`（主轨 computed，WorkspacePage.vue:290）→ Timeline → AIAssistantPanel）：翻译卡的「主轨无 subtitle 段置灰」判定用 mainSegments（轨模式下 panel 的 `segments` prop 是副轨段，不可用作判定源）。**该链 P1 交付，P3 的 X2 复用**；R3 顺序约束（M0-3 约束 2）：P1 同一改动把 `active-track-id`/`active-track-name` 一并接到本链（Timeline 已收 activeTrackId，Timeline.vue:348，缺的仅 Timeline→面板一级），M2-4 届时只加门控消费 |
| AIAssistantPanel（对话框） | 内联语言选择：常用清单 `["en","ja","ko","zh-CN","zh-TW","fr","de","es","ru"]`（BCP-47 短码，即 `SubtitleTrack.language` 填值规范）+ 记忆上次（启动成功后写回 config 键 `llm_translation_target_language`，经既有 settings 保存通路）；入口展示「约 N 批」（`Math.ceil(主轨段数/30)`，标注「约」——字符预算动态收缩使精确批次只能后端算，PRD R1.1 验收「预估批数与实际一致」放宽为量级一致，回写项见附录 C） |
| 新轨命名 | `track_name` 缺省 = 语言显示名（如 "English"），落 `SubtitleTrack.name`；`role="translation"`、`language=目标码` |
| useLlmTasks.ts | 新增 `startTranslation(targetLanguage)`（照 :269-280 模式）+ 消费 `EVENT_LLM_TRANSLATION_COMPLETED`（照 correction 完成事件消费模式，useLlmTasks.ts:12-20 import 区） |
| **undo 快照时序** | **任务 start 前** `pushSnapshot(projectRef.value, ["tracks","bindings"], "AI翻译副轨")`——写入发生在后台线程完成时，前端无法事后插快照（PRD R1.4）；快照失败/用户取消不产生 undo 条目错位：取消路径不入栈（start 前入栈 + 任务失败 = 空转一条，可接受；SPEC 裁决不为此加复杂度） |
| 进度 | 通用 `task:progress`（批粒度），复用面板进度条 |
| 完成切轨（R3 重设计，补接线通路） | **架构事实**：`useLlmTasks` 是模块级单例（useLlmTasks.ts:66-75），而 `activeListTrackId` 是 `useListTrackSelector()` 工厂每次调用**新建的实例 ref**（useListTrackSelector.ts:92-100）——单例够不到 WorkspacePage 持有的实例，Round 2 版「`activeListTrackId = payload.track_id`」缺执行主体。通路设计：① useLlmTasks 单例消费 `EVENT_LLM_TRANSLATION_COMPLETED`（ensureListeners 注册一次）→ 存模块级 `lastTranslationCompletion` ref（含 track_id/language/uncovered_ids）并随 return 暴露；② WorkspacePage `watch(lastTranslationCompletion, c => { if (c) void handleSelectListTrack(c.track_id) })`——复用 handleSelectListTrack（WorkspacePage.vue:952-957，自带 `await flushPendingTrackUpdates()` 前置，切换前先落主轨未决编辑）；③ 其内部经 selector 对外 API `selectTrack(trackId)`（`UseListTrackSelectorReturn`，useListTrackSelector.ts:84-90）完成切换。单一事件监听、无双注册；与 R3.1 编辑态跨轨延续组合 = 新译文轨直接进入扫掠校对态（服务 US-T3-2），beta.1 真机反馈突兀再加门控 |

**边界**：`llm:translation_progress` 逐批流式预览不入版（版本池）；完成后刷新不做第二套通路（task:completed 剥离 → get_project 既有模式）。

**验收**：语言记忆跨会话；空主轨置灰；完成后列表直接显示译文轨且自动切换；undo 一次回退三层一致（tracks/bindings 消失 + 列表视图回主轨）；uncovered 非空时面板明示清单。

---

## M2: AI 纠错感知当前轨（P2 / S2）

「只开纠错」的技术依据见探索报告 §3.2（删除类 AI 产 EditDecision 驱动主轨剪辑契约；纠错是唯一纯文本、不动时间轴、不进剪辑模型的 AI）。范式先例 = `export_subtitle` 的 track-aware payload（main.py:297-315，仓库唯一）。

### M2-1: payload 透传与段源（R2.1）

**改动**：

| 触点 | 内容 |
|---|---|
| main.py:2567-2602 | `start_subtitle_correction` 增形参 `track_id: str = ""`，非空时入 task payload（默认空 = 主轨，既有调用零影响） |
| main.py:889-921 | `_handle_subtitle_correction`：`track_id = task.payload.get("track_id", "")` 非空时——① 段源 = `tl.transcript.tracks` 对应轨的 segments（全为 subtitle 型）；② **confirmed-deleted 映射**：构建 `bindings` 反查表（ext_id → main_id），主轨 id ∈ `collect_confirmed_deleted_seg_ids(timeline)` 的副轨段**跳过**（语义对齐导出映射；无绑定的副轨段保留）；③ **partial hints 跳过**（裁决：hints 是主轨 EditDecision 概念，改造成本 M 收益负——探索报告 §3.3-2 两分支中取「跳过」） |
| main.py:969-971 | `store_subtitle_corrections(corrections, timeline_id, track_id=track_id)` 透传 |

**边界**：智能删除/精华/工作流/语义搜索一律不开放副轨（PRD §0.2）；`_get_target_timeline` 仍 timeline 粒度（main.py:415-431），track 解析在 handler 内做（轨不存在 → 任务 failed「Track not found」）。

**验收**：track_id 缺省时主轨行为与 v3.0.3 完全一致（既有测试不改断言全绿）；副轨段源不含已删除主轨段的绑定段（新用例：1 删除主轨段 + 绑定副轨段被跳过）；轨不存在失败路径。

### M2-2: pending 作用域化（R2.2，本模块最高风险）

**改动**（core/correction_service.py，受控改点 ②）：

| 触点 | 现状锚 | 契约 |
|---|---|---|
| `store_subtitle_corrections` | :59 seg_map 只建主轨；:61-65 互清清掉 timeline 全部同类型结果 | 增形参 `track_id: str = ""`；seg_map 按 scope 构建（空 = `tl.transcript.segments`，非空 = 对应 track.segments）；detail JSON 增键 **`"track_id": track_id`**（空串 = 主轨，字段名与 payload 一致）与 **`"timeline_id": <store 时所属时间轴 id>`**（R3 补：供 M2-3 accept/reject 时间轴钉扎校验，见该表）；**互清精确语义**：只清除「detail.track_id == 本次 track_id」的同类型结果（其余轨与主轨待审集不动） |
| 兼容规则 | 存量 detail 无 track_id 键 | 解析侧 `payload.get("track_id", "")` 缺省按主轨作用域——存量结果自动归主轨，`test_store_clears_previous_corrections`（主轨两次 store 计数不翻倍）等既有断言零改动通过 |
| `get_subtitle_corrections` | :121 seg_map 只建主轨；:130-141 段缺失回退 0.0 | 输出逐条附 `track_id` 与 `track_name`（审阅列表标注来源轨）；**悬空过滤**：detail.track_id 非空且该轨已不存在（delete_track 后）→ 该条**跳过不出现在列表**（随轨失效）；段解析按 scope 查主轨或轨内段 |
| 唯一调用方核查 | 本人 grep 证实 `store_subtitle_corrections` 生产代码仅 main.py:970 一处调用（workflow accumulate 路径跳过 store） | 形参默认值保证零破坏；workflow_engine 零改动 |

**边界**：AnalysisResult 模型零变更（PRD §0.2）；`accept_high_confidence_corrections` 与 `clear_subtitle_corrections` 保持 timeline 级全清语义不变（既有行为，本版不动——副轨用户用逐条 accept/reject；登记 3.0.5 可选作用域化）。

**验收**：双轨各自 pending 互不干扰（主轨审阅中启动副轨 store，主轨待审集计数不变，反向同；**用例按序列化调用编排**——两次 store 先后执行、断言中间态，不构造并发写，见 M1-5 并发约束，R3 明确）；存量无 track_id 结果按主轨处理（兼容用例）；get 过滤悬空 track_id；输出附 track_id/track_name。

### M2-3: accept/reject 超集 patch 化（R2.3，含清债 #14）

**改动**（core/correction_service.py:154-253 + 前端消费）：

| 项 | 契约 |
|---|---|
| accept 主轨路径 | 逻辑不变（`_assert_timestamps_unchanged` + `reattach_words` + `_update_active_timeline`，:195-224）；**返回值超集**：`{"success": True, "data": {"segment_id": …, "patch": ProjectPatch(segments=…, analysis=…).model_dump()}}` —— 保留 `segment_id` 键（test_subtitle_correction_review.py:157 断言零改动兼容），新增 `patch` 键 |
| accept 副轨路径 | detail.track_id 非空 → 定位轨与轨内段 → 复用 `_assert_timestamps_unchanged` + `_check_correction_confidence` + `reattach_words` → `track.model_copy(update={"segments"})` 整体替换写回 transcript.tracks → 移除该 AnalysisResult → 返回 `{"segment_id", "track_id", "patch": _success_patch(tracks=…, analysis=…)["data"]}` |
| **patch 层裁决（覆盖 PRD）** | PRD 写 `_success_patch(tracks=…, bindings=…)` **错层**：accept 只改段 text 与 analysis（结果移除），bindings 零变化（text 无几何语义）；漏 analysis 层则 patch 应用后前端审阅列表与后端脱节。正确层：主轨 = `segments + analysis`，副轨 = `tracks + analysis` |
| reject | 同步超集：返回附 `patch`（层 = `analysis`，reject 只移除结果不动文本）；前端可选消费 |
| `reattach_words` 空输入 | 副轨段多来自 SRT 导入/翻译生成、`words=[]` → reattach 跳过并原样返回空表（用例固化，防御性断言不触发 TimestampCorruptionError） |
| **undo 捕获层裁决（覆盖 PRD）** | PRD 定主轨 `["segments"]` / 副轨 `["tracks","bindings"]` **漏 analysis**——accept 同时移除 AnalysisResult，漏层则 undo 只回滚文本、审阅条目不恢复，「undo 一次回退 accept」验收必挂。正确捕获层：主轨 `["segments","analysis"]`，副轨 `["tracks","analysis"]`（analysis 为合法 undo 层，undoRecords.ts:15-23） |
| 前端消费 | useWorkspaceActions.ts:895-903 `handleAcceptCorrection`：调用前按 scope `pushSnapshot`（上表捕获层，主/副轨同规则，消除两套行为）；响应含 `patch` → `emit("project-updated", res.data.patch)` 走 `applyProjectPatch`（App.vue onProjectUpdated 自动检测 patch 形态），**移除** `switch_timeline` 全量刷新 workaround（:900-901，大工程 O(project) 消失）；`handleRejectCorrection` 同步消费 patch |
| **accept/reject 时间轴钉扎（R3 补）** | 审阅期间用户可能切换时间轴，而 accept/reject 走 `self._project.active_timeline`（correction_service.py:173，R3 核实）——存在漂移风险（轻则含混 not-found，重则跨时间轴同 id 段错写）。守卫：store 时 detail JSON 已写入 `timeline_id` 键（M2-2 同一扩展点）；accept/reject 解析 detail 后，若 `timeline_id` 非空且 ≠ 当前 `active_timeline_id` → `{"success": False, "error": "该结果属于其他时间轴，请切换后审阅"}`（明确报错，不做任何写入）；存量 detail 无该键 → 缺省放行（兼容规则同 track_id）。前端配套：useLlmTasks 的 `pendingCorrections` 单例列表在时间轴切换（switch_timeline 后 get_project 刷新）时重新拉取，陈旧条目不残留可点 |

**边界**：`_mark_dirty` 包装（main.py:2497-2512）不改（envelope 透传）；`accept_high_confidence_corrections` 批路径复用单 accept，自然获得超集返回（不改其前端消费，避免范围膨胀）。

**验收**：`test_subtitle_correction_review.py` 既有断言全绿（:157 零改动）；accept 后前端 revision 单调 +1 而非全量刷新（vitest 断言不再调 switch_timeline）；undo 一次回退 accept（文本恢复 + 审阅条目回到列表 + redo 对称）；副轨 accept 写轨内段文本且 bindings 不变；reattach_words 空输入用例。

### M2-4: 前端门控与审阅（R2.4）

**改动**：

| 触点 | 内容 |
|---|---|
| WorkspacePage.vue / Timeline.vue:727-743 | 透传 `active-track-id` / `active-track-name` 至 AIAssistantPanel（现状不传任何轨道信息，Timeline.vue:727-743 核实；**R3 顺序约束（M0-3 约束 2）：该透传已在 P1 随 M1-6 mainSegments 链一次改动交付，本行在 P2 不再产生 diff，仅消费**） |
| Timeline.vue:333-337 / :578-586 / :745-759 | **精华入口门控（R3 补触点，must-fix #2）**：精华不在 AIAssistantPanel features（仅 3 卡），入口是 Timeline 右栏第三 tab → HighlightModeView（tabs 数组 :333-337、tab 按钮区 :578-586、视图挂载 :745-759，本人核实）。轨模式（isTrackMode，Timeline.vue:348）下「精华」tab **置灰**（disabled + title「仅主轨可用」）——裁决置灰而非隐藏：保持三 tab 布局稳定、切轨时侧栏不跳动，与面板置灰同口径；`isTrackMode` 变 true 且 `activeTab === "highlight"` → 自动回落 `activeTab = "suggestion"`（不停留在不可用视图）。「建议」tab 不门控（主轨建议只读展示无害，与搜索卡同口径） |
| AIAssistantPanel.vue:125-147 | 轨模式（activeTrackId 非空）下：智能删除/精华/工作流入口 **置灰 + 置灰原因文案**（「仅主轨可用」）；纠错卡正常可用 + 显式**轨徽**（「当前轨：{track_name}」，锁定当前轨不弹选择）；搜索卡不置灰（只读主轨无害，X2 修显示侧）。门控实现层**裁决 = AIAssistantPanel prop 门控**（组件自洽可测，优于 WorkspacePage 拦截分散） |
| useLlmTasks.ts:269-280 | `startSubtitleCorrection(referenceText, trackId?)` 透传 track_id；WorkspacePage 调用点传 `activeListTrackId ?? ""` |
| 审阅 modal（WorkspacePage.vue:1525-1639） | 条目按 `track_id` 解析显示段与时间（主轨或轨内段）；列表条目标注来源轨徽；renderDiff 纯文本渲染不变 |

**边界**：主轨视图下面板与 v3.0.3 完全一致（超集原则：仅 activeTrackId 非空分支加门控）；主轨纠错不显示轨徽（空即主轨，不加噪声）。

**验收**：副轨视图下删除类 AI 不可触发（vitest：置灰态点击不 emit start）；轨徽名称正确；轨模式下精华 tab 置灰不可点、正停留在精华 tab 时切轨自动回落 suggestion（vitest，R3 补）；主轨视图零回退（既有 AIAssistantPanel 测试不改全绿）。

### M2-5: 可选增强——对齐主轨上下文（R2.5）

副轨纠错时经 bindings 把主轨对齐文本附进 LLM 上下文（`_build_structured_user_message` 的 extra_context 通路，llm_service.py:1021-1028 报告锚）：binding 命中的副轨段附对应主轨段 text 作参考行；无绑定段自动退化无上下文。纯后端、前端零改动。**让位线：S4（M4）开工即砍**（PRD R2.5 边界），砍则不产生任何半成品代码。

**验收**：有绑定段的请求上下文包含主轨对齐行；无绑定段正常出结果（2 用例）。

---

## M3: 前端顺带批（P3 / S3）

### M3-1: 编辑扫掠覆盖副轨（R3.1，T1 方案 A，裁决反转）

**改动**：

| 触点 | 内容 |
|---|---|
| TranscriptRow.vue:324-337 | 删除两处 track 早退：onMounted 的 `&& !isTrackVariant.value` 条件（:328）与 watch 的 `if (isTrackVariant.value) return`（:331）——副轨行随 `globalEditMode` 进入/退出行内编辑；保存路径已按 variant 分流（`saveEdit` 内 `isTrackVariant ? emit("track-text") : emit("update-text")`，3.0.3 已交付），无需改 |
| TranscriptRow.test.ts:270-275 | **断言反转白名单执行方式**：该用例整体改写为「enters text edit under globalEditMode (track variant)」——断言 `input.edit-text-input` **存在**；原「never enters…」意图随裁决作废，record-P3 登记反转条目与理由（PRD §1.3）。白名单外任何 `expect(` 删除/改写 = 红线违规 |
| 新增断言 ×2 | ① 按钮开启后副轨行进编辑（即上条反转用例）；② 切换轨视图前未决防抖先 flush——**R3 锚点勘误（must-fix #4）**：真 flush 点 = WorkspacePage.vue:952-957 `handleSelectListTrack` 先 `await flushPendingTrackUpdates()`（useTrackEdit.ts:227-234）再 `selectListTrack(trackId)`；Round 2 所引 Timeline.vue:247-258 是**死段草稿清理 watch**（drafts 中已不存在段的条目回收），非 flush 机制。断言②挂 handleSelectListTrack：pendingMap 非空时切轨 → flush 回调先于 selectListTrack 执行，切轨后对旧轨的 pending 草稿已提交无丢失 |
| Timeline.vue:566-573 | 按钮文案感知轨道视图（Q1 裁决）：`isTrackMode` 下显示「编辑〈轨名〉」/「退出编辑」，主轨视图文案不变 |
| 编辑态跨轨保持 | `globalEditMode` 不随轨切换重置（Q1 裁决；现状即全局态零改动，补 1 条断言固化） |

**边界**：仅列表侧；波形侧一致性（方案 B）不入版（Q2 版本池）；主轨路径 diff 为零（改动全在 `isTrackVariant` 分支内）；v-memo 依赖数组已含 `globalEditMode` 与 `isTrackMode`（Timeline.vue:644 核实）无需改。

**验收**：副轨视图一键进入/退出全列编辑；切轨草稿先 flush 无丢失；主轨既有断言全绿；撤销走 3.0.3 谓词表（text 恒 `["tracks"]`）零新增。

### M3-2: lane 建段接线（R3.2，X1）

断链考古：41a1ac4 引入的四段链路断三处（探索报告 §6.1，本人逐点核实）——TrackLane `onLaneClick` 以 `props.buildMode` 门控（TrackLane.vue:49-55）但从未收到该 prop；WaveformRow 的 `@create-at` 桥调 `createAtInTrack?.()`（WaveformRow.vue:357）可选调用静默 no-op；WaveformEditor 声明了 `track-create` emit（:91）但无桥接；下游 `WorkspacePage.vue:1482 @track-create="handleTrackCreate"` → :918-920 → `handleAddTrackSegment`（快照 + add_track_segment + toast，useWorkspaceActions.ts:528-541）至今孤儿。

**三处接线（精确 diff）**：

| # | 触点 | 改动 |
|---|---|---|
| ① | WaveformEditor.vue multi 路径 WaveformRow 用法（:1108-1130） | 追加 `:build-mode="buildMode"` 与 `:create-at-in-track="(tid: string, t: number) => emit('track-create', tid, t, Math.round((t + 0.5) * 100) / 100)"`（0.5s 默认宽对齐 basic 建段先例 SegmentBlocksLayer.vue:165） |
| ② | WaveformRow.vue TrackLane 用法（:339-358） | 追加 `:build-mode="buildMode"`（prop 与 `@create-at` 桥 :357 已存在，仅缺上游传值） |
| ③ | WaveformEditor.vue basic 路径 TrackLane 用法（:1218-1229） | 追加 `:build-mode="buildMode"` + `@create-at="(t: number) => emit('track-create', lane.trackId, t, Math.round((t + 0.5) * 100) / 100)"` |

**边界**：仅接线 + 测试，不改 TrackLane.onLaneClick 与 handleTrackCreate 既有逻辑；不做 lane 形态范围标记（Q12）；TrackLane 的「drag-start」注释提及但未实现的行为不扩（保持 click-only）。

**验收**：建段模式下点击副轨 lane 空白 → 建段 + toast 可见（原提交描述首次兑现）；basic/multi 两模式均通（vitest ×2：WaveformEditor 挂载后 `build-mode-toggle`（:1013）开启 → TrackLane 点击 → `track-create` 上抛 `(trackId, t, t+0.5)`）；建段模式 OFF 时 lane 点击无动作（零回退断言）。

### M3-3: 语义搜索轨模式错位修正（R3.3，X2）

根因：后端 `semantic_search` 恒搜主轨（main.py:2680-2684 核实）；显示侧 segmentMap 建自 `props.segments`，而挂链是 WorkspacePage:1385 `:segments="listSegments"`（轨模式 = 副轨段）→ Timeline:729 → AIAssistantPanel → **内嵌 SemanticSearchBar（AIAssistantPanel.vue:716，非 Timeline 直挂——报告引 :729 为面板 bindings）** → SemanticSearchBar.vue:33-39 map 键为主轨 id，取值落空 → 文本空、时间 0。

**裁决：前端侧修正（M3 交付，不依赖 M2 后端排期）**；轨维度搜索未立项（PRD §0.2），后端零改动。

**改动**：复用 M1-6 交付的 `mainSegments` 透传链，延伸一级——SemanticSearchBar 新增 prop `mainSegments?: Segment[]`，segmentMap 改为 `for (const s of (props.mainSegments ?? props.segments))`；AIAssistantPanel 透传。主轨模式两值相同零变化；轨模式 map 键与后端返回的主轨 segment_id 对齐。

**边界**：不扩展 `semantic_search` 为 track 维度；点击定位行为不变（定位到主轨命中段，轨模式下经主轨 id 定位语义不变）。

**验收**：轨模式下结果文本/时间正确显示、点击定位到主轨命中段（vitest：轨模式传副轨 segments + 主轨 mainSegments + 主轨 id 结果 → 文本非空且时间正确）；主轨模式零变化（不传 mainSegments 时行为与 v3.0.3 一致）。

---

## M4: 手动剪辑范围（P3 / S4，方案 C+B）

数据层现状（探索报告 §5.1/§5.2 + 本人核实）：`EditDecision(target_type="range")` 模型/持久化/patch/undo/导出（`_get_confirmed_deletions` 不过滤 target_type，export_service.py:599-606）/波形覆层（SegmentBlocksLayer.vue:128-145）全部现成；后端仅 2 生产者（subtitle_trim project_service.py:2560-2661、高光虚拟仅导出时构造），前端 0 入口；range 编辑（target_id=None）不被 update_transcript 孤儿清理误删（project_service.py:560-563 报告锚）。

### M4-1: `add_range_decision` expose（R4.1）

**签名**：`@expose add_range_decision(start: float, end: float, action: str = "delete", source: str = "manual") -> dict`（main.py expose 区 + `ProjectService.add_range_decision` 实现）。

**契约**：
1. **clamp**：`start = max(0, start)`、`end = min(media.duration, end)`（media 缺失时上界取 `max(s.end for segments)`，同 generate_subtitle_keep_ranges :2585 口径；**空序列守卫（R3 补）**：media 缺失且主轨 segments 为空时 `max()` 抛 ValueError——须在此前先拒，对齐 project_service.py:2581-2582「No subtitle segments found」先拒空口径，error「无媒体时长且无字幕段，无法确定范围上界」）；clamp 后 `end <= start` → 拒绝；
2. **action 校验**：`action in ("delete", "keep")`，否则拒绝（模型 Literal 保护外的入口校验）；
3. **去重与 ±0.05s 规则的关系（裁决）**：与 subtitle_trim 生成侧（project_service.py:2614-2620）同阈值同判据——存在既有 edit 满足 `action == 本次 action` 且 `|e.start - start| < 0.05 and |e.end - end| < 0.05`（任意 status）→ **幂等返回既有 edit**（`{"success": True, "data": {"edit_id": 既有id, "duplicate": True}}`，防抖双击/重复提交不产生重复条目）；**跨 action 重叠必须放行**（delete 与 keep 语义对立，keep 的存在意义就是打穿 delete 区间，见 M4-4）；任意宽度重叠的非近似区间均放行（范围重叠是合法状态，由 M4-4 计算语义消解）；
4. **status 默认 `pending`**（区别于 subtitle_trim 的 CONFIRMED-at-creation :2646——自动裁剪是确定性可重生成工具，手动范围需人工审阅）；`source` 固定 `"manual"`（分组过滤键，自由备注不做——字段冻结）；`target_type="range"`、`target_id=None`、`priority=100`（模型默认）；id = `edit-manual-{uuid4().hex[:8]}`（uuid 防历史删除后撞号；subtitle_trim 的序号 id 依赖整体重生成，不适用手动增量）；
5. 返回 `_success_patch(edits=…)` patch envelope；前端调用前 `pushSnapshot(project, ["edits"], "手动范围")`（既有先例 useWorkspaceActions.ts:652）。

**边界**：不做 range 编辑修改 expose（改范围 = 删除重建，面板操作）；模型/patch/导出零改动；`source` 不做白名单拦截（模型层自由字符串，面板分组只消费 `"manual"`）。

**验收**：全生命周期用例（建 pending → confirm → 导出预览包含该区间（与 subtitle_trim 自动区间并列、去重后无重复）→ 单条删除（`delete_edit_decisions_batch`，main.py:1548 既有 expose）→ 再建同参幂等返回）；clamp 用例（越界/倒序拒绝）；跨 action 放行用例。此组即探索报告 §5.4 测试缺口 #4 的补测。

### M4-2: 创建手势（R4.2，**改裁 PRD**）

**PRD 裁决勘误（must-fix）**：PRD §6-Q11/R4.2① 称「Shift-marquee 为只写不读的死代码、激活零成本」——**与代码不符**。死代码仅指 `selectedRange` ref（useSegmentEdit.ts:85、:102-104 只写不读）；Shift-drag 手势本身是在用的 **multi 模式跨行段多选手势**：`handleRowEmptyGesture`（WaveformEditor.vue:742-750，本人核实）`else if (g.shiftKey) startMarqueeGesture(g)` → `emit("select-segments", …)`（:687-709）→ WorkspacePage.vue:1477 消费。占用 Shift-marquee = 主轨交互回退，违反红线 R0-4；且 marquee 输出的是**段 id 命中集**，非自由时间区间，语义也不匹配。Ctrl-drag 同理被占（Ctrl-create :742-744）；Alt+drag 现走 scrub 分支（else 兜底），占用同样构成回退。

**SPEC 裁决：新增「范围标记」工具栏 toggle（对齐建段模式先例 WaveformEditor.vue:280/:1012-1017）**，默认 OFF；ON 时主轨空白区 plain press-drag → range marquee → 松手出**确认气泡**（删除/保留二选一 + 取消）→ `add_range_decision`；OFF 时一切如旧（超集原则，默认关零回退）。`selectedRange` 死代码本次激活为气泡数据源（框选区间暂存）。**气泡形态 R3 裁决 = WaveformEditor 内嵌，不建新组件**：气泡是手势态的临时 UI，生命周期与框选起止同源，定位坐标（框选终点）与确认回调全部在编辑器层闭环；独立组件需跨层传递手势态/容器相对坐标，接口成本 > 复用收益（无第二消费场景）。落点：WaveformEditor.vue 模板尾部、波形容器内 absolute 定位（与既有覆层同坐标系）。

**手势矩阵（basic × multi 逐格，vitest 逐格覆盖）**：

| 模式 | 手势 | 范围标记 OFF（=v3.0.3） | 范围标记 ON |
|---|---|---|---|
| multi | plain press/drag | clear-selection + scrub（:746-748） | **range marquee → 气泡**（路由置于 else 分支之前、ctrl/shift 判断之后） |
| multi | Ctrl-drag | Ctrl-create 建段（:744，钳邻居缝隙 :642-666） | 不变（Ctrl 优先级高于范围模式） |
| multi | Shift-drag | 段多选 marquee（:745） | 不变（Shift 优先级高于范围模式） |
| basic | plain click/drag | emptyAreaMode 由 buildMode 决定（:1185：buildMode ON=add 建段 / OFF=seek 死 emit 无监听，:1178-1194 核实） | **range marquee → 气泡**（basic SegmentBlocksLayer 补 `@empty-press` 路由，当前无监听 = 零占用） |
| basic | buildMode ON plain click | add 0.5s 段（SegmentBlocksLayer.vue:164-165） | 范围模式优先（双 toggle 同 ON 时范围模式获胜，UI 互斥提示） |
| 两模式 | lane/副轨区 | 不涉及（范围标记仅主轨域） | 不涉及 |

**接线点（R3 补全，suggest #6——双 toggle 获胜语义的落点）**：`emptyAreaMode` 现仅 `"seek" | "add"` 两值，SegmentBlocksLayer 只在 `"seek"` 模式 emit `empty-press`（SegmentBlocksLayer.vue:152-162），`"add"` 模式直走 `add-segment`（:164-165）；而 WaveformEditor 两处绑定均为 `:empty-area-mode="buildMode ? 'add' : 'seek'"`（multi 路径 WaveformRow :1111 / basic 路径 SegmentBlocksLayer :1185，本人核实）→ **buildMode ON 时范围手势永远到不了**，矩阵「双 toggle 同 ON」格缺实现。改法：

1. `emptyAreaMode` 联合类型增第三值 `"range"`；两处绑定改嵌套三元 `rangeMode ? "range" : buildMode ? "add" : "seek"`（**范围模式获胜**，即该矩阵格的实现；默认两 toggle 均 OFF 时表达式退化为 `"seek"`，零回退）；
2. SegmentBlocksLayer `handleEmptyClick` 增 `"range"` 分支（置于 `"seek"` 分支之前）emit 新 `range-press` 手势（payload 形态同 empty-press：clientX/clientY/ctrlKey/shiftKey/time）；marquee 拖拽跟踪与松手气泡由 WaveformEditor 层处理（与 multi 侧 startMarqueeGesture 同层，press-drag 语义一致，复用同一套拖拽跟踪）；multi 路径的 range 路由按矩阵既定（`handleRowEmptyGesture` else 分支之前、ctrl/shift 判断之后）。

**时间码入口（改裁 PRD 位置；R3 补落点）**：PRD R4.2② 定工具栏——SPEC 裁决并入建议面板「+ 时间码」popover（起止两输入，口播场景精确范围；离管理视图最近，工具栏已拥挤）。**落点 = 面板头部条 SuggestionPanel.vue:190-199（「共 N 处建议」条右端加「+ 时间码」按钮 + popover）**——R3 裁决：**不放「手动范围」分组头（:216-231）**，分组由 push 守卫（:54 `if (items.length === 0) return`）在无手动范围时整体隐藏，入口会随空列表消失；头部条常驻，空工程也能创建第一条。两个入口共用 `add_range_decision`。

**边界**：不占用 Ctrl-drag（Ctrl-create 语义零回退，逐字节断言）；不引入新 track role（方案 A 不做，Q12）；气泡二选一默认聚焦「删除」（Q9 默认 action=delete）；副轨 lane 不参与范围标记。

**验收**：矩阵逐格 vitest（ON 六格 + OFF 三格零回退断言）；框选 → 气泡 → 决策落盘 → 波形覆层即刻可见（pending 样式）；Ctrl-create 与 v3.0.3 完全一致（既有 WaveformEditor 建段测试不改全绿）；时间码入口创建成功且非法输入（end≤start）被拒。

### M4-3: 建议面板「手动范围」分组与覆层（R4.3）

**改动**：

| 触点 | 内容 |
|---|---|
| SuggestionPanel.vue:63-99 | 新增第三源分组：`source === "manual"` 的 edits → 「手动范围」分组（与静音/智能删除并列）；条目 label = `删除/保留 {时长}s` + status 徽；逐条确认/拒绝复用 `update_edit_decision`（main.py:1540）、逐条/批量删除复用 `delete_edit_decisions_batch`（:1548）——**后端零新增**；`SUGGESTION_SOURCES`（:99）与计数器（:101-106）并入 manual（计数含 keep 条目，分组内再分小节） |
| SegmentBlocksLayer.vue:128-145/323-335 | 覆层** action/status 感知（PRD 未列的必要改动点）**：现状 `visibleEditRanges` 只过滤 `target_type === "range"`，**keep range 会渲染成红色删除纹（误导）**、pending 与 confirmed 同样式（无法区分）。改法：computed 增加输出 `edit.action`/`edit.status`，模板分三态——confirmed delete = 现状红色斜纹（**逐字节不变**）；pending = 同款半透明（opacity 降档）；keep（任意 status）= 蓝色系斜纹/描边（不用红） |
| WorkspacePage.vue:295-300 | **deleteRanges 裁决：pending 手动范围不入**。`deleteRanges` 驱动 `useEditedPlayback` 跳播 + 进度条红罩 + 导出预览——pending 不应跳播；现状过滤（confirmed OR subtitle_trim）天然排除 pending，**零改动**，补 1 条快照锁定用例（探索报告 §5.4 缺口 #6 顺带清偿） |
| 撤销 | 建/确认/拒绝/删范围全链 `pushSnapshot(["edits"])`（现成模式 useWorkspaceActions.ts:652） |

**边界**：静音/智能删除两分组断言零改动；自由备注不做（字段冻结，Q9）；`subtitle_trim` 生成区间仍走原分组外展示（现状斜纹，不入「手动范围」分组——source 过滤天然隔离）。

**验收**：手动范围生命周期在面板可见闭环（建→审→确认→删除）；undo 一次回退建范围；覆层三态样式正确且 confirmed delete 样式与 v3.0.3 一致；deleteRanges 不含 pending（快照用例）；既有两分组断言全绿。

### M4-4: keep 闭环（R4.4，Q10 默认完整闭环）

**keep 消费边界裁决（任务要求的架构师裁决）**：**keep 仅影响 `generate_subtitle_keep_ranges` 的删除区间计算，不参与导出消费**。理由：
1. 导出消费端 `_get_confirmed_deletions`（export_service.py:599-606）只认 `action=delete && status=confirmed`——keep 若进导出需发明「从删除区间扣除」的新语义，而删除区间来源含**段级删除**（target_type=segment 的 confirmed delete 对应整段裁剪），keep 与段删除相交时语义无法自洽（用户已确认删的段被 keep「复活」是矛盾操作）；
2. 2.x「撑住间隙」习惯的本义 = 阻止**自动裁剪**吃掉内容，即干预自动计算而非推翻手动决策——keep 的消费边界 = 自动计算侧，正是该习惯的现代化等价；
3. keep 与手动 delete range 并存时导出服从 delete（手动决策优先于 keep 标记），SPEC 显式文档化该优先级，避免歧义。

**改动（受控改点 ①，project_service.py:2560-2661）**：

1. **keep 集合感知**：在 keep_ranges 构建段（:2588-2596）之后、delete_ranges 补集计算（:2598-2606）之前，收集用户 confirmed keep 集合：`user_keeps = [(e.start, e.end) for e in edits if e.action == "keep" and e.status == CONFIRMED and e.target_type == "range"]`（不限 source——当前唯一 keep range 生产者即本特性 manual，未来生产者天然继承同一语义）；`keep_ranges = merge_union(sorted([*keep_ranges, *user_keeps]))`（排序 + 相邻合并，复用 :2592-2594 同款合并逻辑抽出的小函数）→ keep 区间从删除区间中自然扣除（补集语义）；
2. **陈旧 trim 剔除（PRD 未列的必要行为，裁决加入）**：生成时若某**既有** `source == "subtitle_trim"` 的 delete edit 与任一 user_keep 相交 → 从 edits 中移除该陈旧区间（计数入返回 data `invalidated_count` + log）。不做此项则「重跑自动裁剪后 keep 区间仍挂旧红纹」，R4.4 验收「keep range 覆盖区间不被自动裁剪删除」在重跑场景必挂；
3. **零回退判据**：`user_keeps` 为空 → 步骤 1 合并空集、步骤 2 零命中，函数输出与 v3.0.3 逐字节一致（golden 对拍用例：固定段集 + padding 扫描，比对 edits dump 与改造前基线）。**基线采集时机（R3 补，= M0-3 约束 1）**：golden 基线必须在触碰 :2560-2661 **之前**、于 v3.0.3 基线工作区采集固化并随 P3 首个 commit 入库——先改后采会让「基线」自带本版改动，对拍失去意义。

**边界**：导出链路零改动（`_get_confirmed_deletions` / `export_timeline` 不触碰）；keep 不阻止用户手动 delete range 的创建与导出（见消费边界 3）；若立项会砍 Q10——keep 入口（气泡「保留」选项 + action=keep 路径 + 本节全部）整体移除，不降级为「可标不消费」半吊子（PRD 边界维持）；M4-3 的覆层 keep 样式随砍。

**验收**：keep range 覆盖区间不被自动裁剪删除（生成后该区间无 subtitle_trim delete 且相交陈旧区间被剔除）；无 keep range 工程的 subtitle_trim 既有断言全绿 + golden 对拍；keep 与手动 delete 并存时导出含 delete 区间（优先级用例）。

---

## M5: 测试与门禁

### 用例矩阵（新增下限，清单级）

| 组 | 用例（≥N） |
|---|---|
| M1 管线（≥12） | 批窗+字符预算收缩；coverage 反向（漏译批/多译批 → ledger 失败不落盘）；429 转串行；非 json_mode 4 层解析 ×3（坏 JSON/围栏/前后缀）；取消退出已完成批不写；opaque id 回映射；占位符穿透三层 + 终替换 + 残留 fail-fast |
| M1 批量写（≥6） | 千段单 patch（revision +1 / tracks+bindings 完整 / undo 整轨回退）；重复语言拒绝；id 落空部分对账（落盘+uncovered）；全部落空拒绝；bind=False 路径 |
| M1 expose/事件（≥5） | start_translation 四分支校验；handler 注册与调度；事件双侧登记；uncovered 随完成事件上报；**运行期切时间轴 → 完成钉扎校验 failed 零落盘（R3 补，M0-3 约束 4 边界用例）** |
| M2 作用域化（≥6） | 双轨 pending 互不干扰（双向）；重跑同轨只清同轨；存量无 track_id 按主轨（兼容）；主轨两次 store 计数不翻倍（既有断言零改动复跑）；get 悬空过滤；输出附 track_id/track_name |
| M2 段源/accept（≥7） | track_id 缺省主轨一致；confirmed-deleted 绑定段跳过；无绑定段保留；轨不存在失败；accept 主轨超集（:157 兼容）；accept 副轨写轨文本 + patch 层 tracks+analysis；reject 超集；reattach_words 空输入 |
| M3 前端（≥7） | TranscriptRow 反转（进编辑）+ 切轨 flush（挂 handleSelectListTrack）+ 跨轨保持；X1 接线 multi/basic 各 1 + OFF 零回退；X2 轨模式 map 对齐 + 主轨模式零变化（**新建宿主 `SemanticSearchBar.test.ts`**，R3 核实该文件不存在） |
| M4 expose（≥6） | 生命周期闭环；clamp；倒序拒绝；±0.05 幂等（同 action）/跨 action 放行；导出预览并列去重；单条删除 |
| M4 keep（≥4） | keep 打穿删除区间；陈旧 trim 剔除 + invalidated_count；golden 对拍（无 keep 逐字节一致）；keep vs delete 导出优先级 |
| M4 前端（≥9） | 手势矩阵逐格（ON 6 格 + OFF 3 格零回退）；气泡二选一落盘 + 取消；面板分组生命周期；覆层三态；deleteRanges 不含 pending 快照；undo 回退（面板侧用例**新建宿主 `SuggestionPanel.test.ts`**，R3 核实不存在；手势侧挂既有 WaveformEditor/SegmentBlocksLayer 测试） |
| M1/M2 前端（≥7） | 翻译卡置灰/语言记忆/完成切轨（watch lastTranslationCompletion → handleSelectListTrack）/undo 三层；门控置灰 + 轨徽 + 精华 tab 置灰回落；accept 走 applyProjectPatch（不再 switch_timeline；**新建宿主 `useWorkspaceActions.test.ts`**，R3 核实无既有测试文件，composable 级先例 useTrackEdit.test.ts）；时间轴切换后 pendingCorrections 重取（R3 补） |

### 门禁命令（每 phase 合入前全绿；P4 终检全量复跑）

```bash
# 后端
uv run pytest                                # ≥716 只增不减全绿（P1 起每 phase 登记当期期望总数）
uv run ruff check .                          # 0 problems（触及文件）
# 前端
cd frontend && bun run test                  # collected ≥756 且 passed = collected - 1
                                             #（唯一失败 = useRowLayout.perf.test.ts 已登记环境例）
cd frontend && bun run build                 # vue-tsc --noEmit + vite build 通过
cd frontend && bun run lint                  # eslint 0 errors 0 warnings

# 红线 R0-1：后端 diff 白名单（输出文件集必须 ⊆ M0-1 表；逐 hunk 对应 R 编号）
git diff v3.0.3 --name-only -- core/ main.py
# 禁改面必须为空输出：
git diff v3.0.3 --name-only -- pywebvue/ core/task_manager.py core/export_service.py \
  core/export_timeline.py core/track_constraints.py core/workflow_engine.py \
  core/ffmpeg_service.py core/ffmpeg_presets.py core/subtitle_service.py \
  core/timeline_utils.py core/diff_service.py core/migrations.py

# 红线 R0-2：events 双侧同步（期望输出 = 恰好两侧各 1 行新增常量）
# R3 修正（must-fix #1）：新行形如 LLM_TRANSLATION_COMPLETED = "llm:translation_completed"，
# 常量名与值均不含连续下划线串 llm_translation_completed —— 旧模式零匹配、门禁恒假绿
git diff v3.0.3 -- core/events.py | grep -E '^\+.*(LLM_TRANSLATION_COMPLETED|llm:translation_completed)'
git diff v3.0.3 -- frontend/src/utils/events.ts | grep -E '^\+.*(EVENT_LLM_TRANSLATION_COMPLETED|llm:translation_completed)'

# 红线 R0-3：断言零删改（期望 = 0；白名单外命中即 fail）
git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'
git diff v3.0.3 -- frontend/src | grep -E '^-[[:space:]]*expect\(' | grep -v 'TranscriptRow.test.ts' | wc -l

# 红线 R0-4 专项：models 只增枚举（期望 diff 仅含 LLM_TRANSLATION 行）
git diff v3.0.3 -- core/models.py
# diff 审查制：全量后端 diff 逐条对照后端改动登记表
git diff v3.0.3 --stat -- core/ main.py
```

### 真机冒烟清单（P4，双平台；含 3.0.3 顺延债并入）

1. 翻译全链：入口选语言（记忆）→ 进度 → 完成自动切轨 → 列表校对（扫掠编辑）→ 播放双语第二行 → 双语/单轨 SRT 导出 → undo 一次整轨回退；千段工程耗时与 token 观测。
2. 纠错双轨：副轨视图只亮纠错卡 + 轨徽 → 副轨纠错 → 主轨待审集不丢 → 审阅列表来源轨标注 → accept 走 patch（无全量刷新卡顿）→ undo；主轨纠错回归。
3. 编辑扫掠副轨：副轨一键进/出编辑 → 切轨 flush → 主轨零回退。
4. lane 建段：建段模式点击副轨 lane（basic/multi）→ toast；OFF 无动作。
5. 语义搜索：轨模式下结果文本/时间/定位正确。
6. 手动范围：范围标记 toggle → 框选 → 气泡删除/保留 → 面板分组审阅 → 确认 → 红罩/导出预览 → keep 撑住自动裁剪 → undo；Ctrl-create 回归；时间码入口。
7. 3.0.3 顺延债：建议面板/红罩层多行视觉回归（与 S4 新分组合并补验，Q15）。

---

## 附录 A：后端改动登记表模板（record 逐 phase 追加，P4 终检逐条核对）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别（只增/受控改点①/受控改点②/登记改点） |
|---|---|---|---|---|

## 附录 B：本人抽查锚点清单（除探索报告外的二次取证）

project_service.py:137-155/602-693/2560-2661/1637-1658/980-1036 · models.py:27-45/99-115/142-189/408-459 · correction_service.py 全文（:59/:61-65/:82-90/:121/:130-141/:154-253）· main.py:140-167/290-334/885-990/2480-2538/2540-2701 · events.py/events.ts 全文 · llm_prompts.py:142-283（`_format_param` :178-194 / `get_effective_prompt` :217-261）· llm_service.py:935-1019 · config.py:58-91 · TranscriptRow.vue:324-337 / TranscriptRow.test.ts:270-275 · Timeline.vue:566-573/630-674/700-749 · TrackLane.vue:25-63（workspace/ 目录）· WaveformRow.vue:72-91/330-364 · WaveformEditor.vue:85-99/612-709/738-775/1100-1194/1218-1247 · SegmentBlocksLayer.vue:118-175/318-335 · SemanticSearchBar.vue:25-49 · SuggestionPanel.vue:55-109 · WorkspacePage.vue:288-312/360-377/905-934/1378-1395/1476-1489 · useWorkspaceActions.ts:398-541/885-914 · useLlmTasks.ts:1-80/255-299 · useUndoRedo.ts:39-60 · undoRecords.ts:15-67 · useSegmentEdit.ts:80-109 · export_service.py:590-606 · AIAssistantPanel.vue:115-149 · test_subtitle_correction_review.py:140-169 · `store_subtitle_corrections` 全仓调用方 grep（生产代码仅 main.py:970）。

**R3 复核增补（实施者 45 锚点核验 + 本人落笔前二次取证）**：useListTrackSelector.ts:84-125（工厂/实例 ref/`selectTrack` API）· useLlmTasks.ts:66-75（模块级单例）· WorkspacePage.vue:952-957（handleSelectListTrack flush 前置）· useTrackEdit.ts:227-234（flushPendingTrackUpdates）· Timeline.vue:333-337/578-586/745-759（tabs 数组/tab 按钮/HighlightModeView 精华入口）· SegmentBlocksLayer.vue:147-166（emptyAreaMode 分流：seek→empty-press / add→add-segment）· WaveformEditor.vue:1100-1130/1175-1194（两处 `buildMode ? 'add' : 'seek'` 绑定）· SuggestionPanel.vue:50-60/99/190-231（push 空组守卫/头部条/分组头）· AIAssistantPanel.vue:22（FeatureKey 联合类型）· correction_service.py:154-234（accept 走 `active_timeline` :173）· project_service.py:137-155（`_success_patch` timeline_id 恒取 active :151）/2496-2511（`_update_timeline_by_id`）/2581-2582（空段先拒先例）· 测试宿主 glob：SuggestionPanel.test.ts / SemanticSearchBar.test.ts / useWorkspaceActions.test.ts 均不存在（→ 新建宿主）；useListTrackSelector.test.ts / useTrackEdit.test.ts 为 composable 测试先例。

## 附录 C：SPEC 实施层裁决清单（与 PRD 冲突处以本文为准，需回写 PRD）

| # | 裁决 | 涉及 PRD 条目 | 回写动作 |
|---|---|---|---|
| 1 | 翻译上下文 = 源文 ±ctx 窗口 + 并发 5；「定稿译文滑动窗」与并发互斥（payload 预构建 + 并发执行取不到定稿），降级登记版本池 | R1.2 / §6-Q7 边界 | 改写 R1.2 跨批一致性段 |
| 2 | accept patch 层 = segments+analysis（主）/ tracks+analysis（副）；PRD 的 tracks+bindings 错层（accept 不动 bindings、必动 analysis） | R2.3 | 修正 R2.3 措辞 |
| 3 | accept/reject undo 捕获层 = ["segments","analysis"] / ["tracks","analysis"]；PRD 漏 analysis 层，undo 验收必挂 | R2.3 ② | 修正 R2.3 ② |
| 4 | 范围创建手势 = 「范围标记」toggle（Shift-marquee 是在用段多选手势非死代码，占用即主轨回退）；Ctrl/Shift 优先级高于范围模式 | R4.2① / §6-Q11 | 改写 Q11 裁决与 R4.2① |
| 5 | 时间码入口并入建议面板「手动范围」分组（非工具栏） | R4.2② | 修正位置 |
| 6 | 覆层须 action/status 感知（keep 会渲染成红色删除纹、pending 无区分）；confirmed delete 样式逐字节不变 | R4.3（未列） | 补改动点 |
| 7 | keep 消费边界 = 仅 subtitle_trim 计算；重跑时剔除与 confirmed keep 相交的陈旧 subtitle_trim 区间（invalidated_count） | R4.4 / §6-Q10 | 补边界与改动点 |
| 8 | deleteRanges 不含 pending 手动范围（维持现状过滤 + 快照锁定用例） | R4.3（开放式） | 落定裁决 |
| 9 | prompt 注册 params={} 使 `{{target_language}}` 穿透三层，handler 终替换 + 残留 fail-fast | R1.2（未定实现） | 补实现契约 |
| 10 | X2 = 前端侧 mainSegments 透传链（P1 交付供翻译卡判定复用，P3 延伸至搜索栏）；SemanticSearchBar 实际挂点在 AIAssistantPanel.vue:716 | R3.3 / §6 表 #7 | 修正挂点描述 |
| 11 | 红线白名单补 core/correction_service.py（R2.2/R2.3 全部改动所在，PRD §1 清单漏列）+ 显式列入 config.py/llm_prompts.py/llm_service.py | §1.5 / §9 | 扩充白名单 |
| 12 | 预估批数按 30/批静态估算标注「约」（字符预算动态收缩使精确一致不可达） | R1.1 验收 | 放宽验收措辞 |
| 13 | 门禁 events 检查口径 = 本版新增事件名双侧存在性（events.ts 含 2 个前端专属 demo 常量，全量比对误报） | §9 新红线检查 | 修正命令 |
| 14 | 门禁断言检查精化为 `^\-\s*(assert |self\.assert)` / `^\-\s*expect\(`（原 grep 过宽命中注释/字符串） | §9 新红线检查 | 修正命令 |
| 15 | reject 同步超集返回 patch（analysis 层）；`accept_high_confidence_corrections` / `clear_subtitle_corrections` 保持 timeline 级语义不动（3.0.5 可选作用域化登记） | R2.3 边界 | 补边界 |

## 附录 D：修订记录

- **R3（实施者 45 锚点逐触点核验后回落，本版修订）**：
  - **must-fix 5 条全部接受**：① M5 门禁 grep 模式修正（常量名/事件值均不含下划线串，旧模式恒假绿）；② M2-4 补 Timeline tabs 精华门控触点（:333-337/:578-586/:745-759，置灰 + 停留回落）；③ M1 时间轴钉扎 = 完成时 fail-fast 校验（M1-4 契约 6 写侧双保险 + M1-5 步骤 4 裁决含弃选 `_update_timeline_by_id` 的三条理由）；④ M3-1 断言② flush 锚点勘误至 WorkspacePage.vue:952-957（Timeline.vue:247-258 为死段草稿清理）；⑤ 删除「ProjectService 内部写线程安全」假前提，改「UI 单飞 + 测试序列化」MVP 约束（M1-5 并发约束节），MiloCutApi 级锁登记 3.0.5 候选、不入白名单。
  - **suggest 7 条全部接受**：⑥ M4-2 双 toggle 接线点（:1111/:1185 嵌套三元 + `emptyAreaMode` 增 `"range"`）；⑦ 气泡裁决 = WaveformEditor 内嵌、时间码 popover 落点 = 面板头部条 :190-199（分组头会被 push 空组守卫连入口一起隐藏）；⑧ M1-6 完成切轨重设计（useLlmTasks 单例暴露 `lastTranslationCompletion` → WorkspacePage watch → `handleSelectListTrack` → `selectTrack`）；⑨ M5 矩阵三处新建宿主标注（SuggestionPanel/SemanticSearchBar/useWorkspaceActions 测试文件均不存在）；⑩ FeatureKey 加 `"translation"`（AIAssistantPanel.vue:22）+ M4-1 空序列守卫（对齐 :2581 先拒空）；⑪ golden 基线先行（M0-3 约束 1 + M4-4 步骤 3）；⑫ M2-3 accept/reject 时间轴钉扎（detail 增 `timeline_id` 键 + 校验拒绝 + 前端列表切换重取）。
  - **其他**：概要新增「规模注记」节（P1=4.5-6 / P2=3-4 / P3=4-5.5 / P0+P4=1.5-2，合计 13-17.5 人日，供 PRD/PLAN 对齐，最终由产品经理裁决）；M0-3 增 4 条顺序约束（golden 先行 / props 链 P1 合并 / M4-3∥M4-1 / 切轨完成分支进边界用例）；M1-6 features 行「精华置灰属 M2-4」措辞勘误（精华不在面板，在 Timeline tabs）；附录 B 增 R3 复核锚点清单。
- **R2（定稿）**：初版。

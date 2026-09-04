# record-3.0.4-P1-3：翻译批处理管线

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-3`（待负责人审查后合入 `dev-3.0.4`）
> 对应 PLAN：Phase 1 / P1-3　SPEC：M1-2（R1.2）

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/llm_service.py` | **纯追加**（文件末尾、`semantic_search` 之后，单一 hunk `@@ -1588,3 +1588,387 @@`，384 行新增 / 0 行删改）：新增 `analyze_subtitle_translation(...)` 公开函数 + 2 个模块级私有辅助 `_translation_segment_id`（handler 形态 `segment_id` → 骨架内部 `id` 归一）与 `_validate_translation_coverage`（coverage 反向校验：missing/unknown/duplicate 三态判别 + 回映射），带 v3.0.4 M1-2 分节注释。既有任何函数/常量/docstring 零触碰（`git diff dev-3.0.4 -- core/llm_service.py | grep -cE '^-[^-]'` = 0） | R1.2 | 只增 |
| `tests/test_llm_translation.py` | 新建（20 用例，挂 M5 矩阵 M1 管线组），mock 手法复用 test_llm_phase4b.py（monkeypatch `core.llm_service.call_llm`）与 test_llm_concurrency.py（线程/取消/并发编排） | M5 | 只增（新文件） |

`tests/` 既有文件零改动；禁改面（pywebvue/、task_manager、export_service 等 20 项）本步零触碰。

## 2. 实现要点（与 SPEC M1-2 逐条对账）

**复刻纠错骨架（llm_service.py:935-1218 同源）**：

- 批窗构建：`llm_correction_batch_size`（30）+ 字符预算收缩 `llm_max_batch_chars`（4000），算法逐行同源（首段恒入窗、预算只算目标窗内文本、上下文不计预算）；不新增任何 config 键；
- 并发池 `llm_concurrency`（5，ThreadPoolExecutor）+ BatchLedger + 每批一次重试（`_process_batch`，重试条件含 coverage 不过/解析失败/API 错误）+ 连续 3 次批级 429 终错误 → 剩余批转串行（`cancel_futures` 后按 `sorted(pending)` 串行补跑，逐批 cancel 检查）；
- opaque id：批内 t1..tN（映射域 = 窗口 ±ctx 含上下文段，复用 `_build_opaque_id_mapping`），payload 经 `_build_structured_user_message` 只暴露 `{id, text}`（无 start/end、无真实 id），返回后经 reverse_map 回映射真实 segment_id；
- 4 层 JSON 解析兜底：直接复用 `_parse_json_response_layers`（含 v3.0.0 M3-3 第 5 层 sanitize），未做任何改写；
- cancel_event 逐批检查（`_call_batch` 入口 + as_completed 循环顶 + 串行段逐批）；progress_cb 批粒度百分比（completed/total×100，收尾 100.0），消息格式同纠错（"Translation batch N/M..." / "(serial)"）；
- token_usage 三键累加（每批取末次尝试 usage，同纠错）；失败/成功 ledger 形态 = `BatchLedger.to_dict()`（与纠错 handler 消费惯例同源：main.py:955 直接透传进事件 payload，dict 天然可 JSON 序列化，test_ledger_json_serializable_for_event_payload 固化）。

**关键差异（精确落实）**：

1. **coverage 反向校验（全量输出守恒）**：`_validate_translation_coverage` 要求输出 id 集 ≡ 目标 id 集——missing（漏译）/ unknown（多译·幻觉 id）/ duplicate（多译·重复 id）任一非空即批失败（error 明细进 WARNING 日志），随批重试一次；重试后仍失败 → `ledger.failed` + `ledger.uncovered_segment_ids`（= 失败批全部目标 id，同纠错 uncovered 语义）→ **整个任务 `{"success": False, "error": "Translation incomplete: ..."}`，translations 不产出（上游零落盘）**。失败响应附 `data: {ledger, token_usage}`（SPEC 失败契约指定 error 键，此处为超集增补，供 P1-5 task:failed payload 与测试断言消费；取消路径不附 data，见 §4）；
2. 输出条目仅 `segment_id + translated_text` 两字段（无 changes/category/confidence），译文文本 strip；
3. 上下文 = **源文** ±ctx 窗口（`llm_correction_context_window`=5）：payload 预构建时附窗口内相邻段源文（复刻 :1013-1019 预构建模式），未实现任何「定稿译文滑动窗」（SPEC M1-2 裁决：预构建 + 并发 5 下取不到定稿译文；版本池 3.0.5 候选）。输入段入口归一为 `{"id", "text"}`，service 层不做轨道/删除过滤；不做增量补译。

**payload 与 P1-2 prompt 的字段契约核对**：`{"segments": [{id, text}...], "target_segment_ids": [t1..tN]}`——与 `_TRANSLATION_SYSTEM` 引用的两字段名逐字一致（P1-2 record §6 注意项闭环）；输出条目 `segment_id + translated_text` 同 prompt 输出格式段。

## 3. 红线命令实际输出

- **`git diff v3.0.3 --stat -- core/llm_service.py`**：`384 insertions(+)`，单一文件单一末尾 hunk，0 删改 ✅；白名单 M0-1 表 `core/llm_service.py` 行 =「仅新增 analyze_subtitle_translation 及其模块级私有辅助」逐字吻合 ✅
- **累计 `git diff v3.0.3 --stat -- core/ main.py`**（P1-1/P1-2 既有 + 本步）：events.py +3 / llm_prompts.py +23 / llm_service.py +384 / models.py +2，共 412 insertions 0 deletions，全部落在 M0-1 白名单内 ✅
- **禁改面 diff**：pywebvue/、task_manager.py、export_service.py、export_timeline.py、track_constraints.py、workflow_engine.py、ffmpeg_service.py、ffmpeg_presets.py、subtitle_service.py、timeline_utils.py、diff_service.py、migrations.py、project_service.py、correction_service.py、main.py、dev.py、build.py 全部为空 ✅
- **R0-3 断言零删改**：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = **0** ✅；本步 tests/ 只新增 test_llm_translation.py（test_llm_prompts.py / test_translation_prompt.py 为 P1-2 既有改动，非本步触碰）
- **本步自身 diff（vs dev-3.0.4）**：core/llm_service.py +384（唯一改动文件）+ tests/test_llm_translation.py（新建）✅

## 4. 取消语义选型说明（任务项 7 裁决）

**选型 = 纠错取消语义同源对齐**：取消即返回裸信封 `{"success": False, "error": "Cancelled"}`（无 data、无已完成批合并结果、无 ledger）。理由：

1. 纠错实现（llm_service.py:1119-1121/:1140-1142/:1169-1170）在 as_completed 循环顶、批级 "Cancelled" 错误、串行段三处均裸返回——翻译逐处同源复刻；
2. 上游语义（M1-5 失败/取消表：「用户取消 → 已完成批不写入」）由「返回不含任何 translations」+ handler 对 success=False 统一 raise RuntimeError 双重保证：已完成批的译文在 service 层被丢弃（test_cancel_midway_returns_bare_cancelled 断言返回字典逐键等于裸信封），落盘侧无从产生副作用；
3. 不选「部分结果返回」：翻译的守恒语义下部分结果毫无消费方（coverage 不完整即整任务作废），返回只会诱导上游误落盘。

取消路径不附 data/ledger（失败路径附、取消路径不附的非对称 = 纠错同源；取消无需 coverage 观测）。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**749 passed**（729（P1-2 基线）+ 本步新增 20，全绿）
- ruff：All checks passed（触及文件 core/llm_service.py / tests/test_llm_translation.py 双零）
- vitest：756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确）
- build（vue-tsc + vite）：通过
- lint（eslint）：0/0
- 红线 R0-1 ~ R0-5 + dev/build.py：全部 PASS（明细见 §3）
- 门禁 exit code：**0**

## 6. 测试清单（20 例 → M5 矩阵 M1 管线组；组内 P1-2 已交 13，本步 +20）

| # | 用例 | 对应要求 |
|---|---|---|
| 1-3 | not configured / empty segments / empty target language | 守卫分支 |
| 4 | batch_size=30 分窗（70 段 → 30/30/10） | 批窗构建 |
| 5 | 字符预算收缩（10 段×10 字符、预算 60 → 6+4 两批） | 批窗构建+收缩 |
| 6 | 漏译批（输出缺 id）重试后仍缺 → ledger failed=[0] + uncovered=全批目标 + success=False | coverage 反向·missing |
| 7 | 多译批·未知 id（额外 t99）→ 同上（WARNING 含 "unknown ids"） | coverage 反向·unknown |
| 8 | 多译批·重复 id（全量+首 id 重复）→ 同上（"duplicate ids"） | coverage 反向·duplicate |
| 9 | 首试缺 id、重试补全 → success=True + retried_ok=1 | 每批一次重试恢复 |
| 10 | 全批成功：译文按输入原序全量返回（LLM 批内倒序作答亦然）+ ledger 3 成功 + token 三键累加 + 条目恰两字段 | 守恒 happy path |
| 11 | ledger 可 json.dumps 且键集恰 5 项 | 事件 payload 可序列化 |
| 12 | progress_cb 批粒度（1/3、2/3、100.0 + "Completed: 6 translations"） | 进度约定 |
| 13 | 连续 429 转串行：loguru WARNING 含 "switching remaining 1 batches to serial"、批 3 串行补跑（末次调用服务批 3）、批 0-2 计入 failed → 任务失败 | 429 降级 |
| 14 | 并发池并行（Barrier(3) 门控，串行池必超时破栅） | 并发 5 保留 |
| 15 | 坏 JSON 无法救 → 重试 2 次后 ledger failed + success=False | 4 层解析·坏 JSON |
| 16 | 围栏代码块（```json ... ```）→ 成功 | 4 层解析·围栏 |
| 17 | 前后缀噪声（"Sure, here it is: [...] Hope this helps!"）→ 成功 | 4 层解析·噪声 |
| 18 | 取消中途退出：批 0 已完成后取消 → 返回逐键等于 `{"success": False, "error": "Cancelled"}`（裸信封，零合并结果） | 取消语义（§4） |
| 19 | payload 仅 opaque id（t1..tN、条目恰 {id,text}、真实 id 不出现在原文）且输出回映射真实 segment_id | opaque id 回映射 |
| 20 | 上下文窗口存在性：批 1（窗 [0,4)+前向 ctx5）payload 9 段、目标 4、context=源文 text 4..8；中间批双侧 ctx 齐备 | 源文 ±ctx 窗口 |

注（任务项 6 的第 4 种「单引号」）：解析链复用 `_parse_json_response_layers` 原样（5 层含 sanitize），单引号 JSON 不在可救范围（同纠错行为，未做任何改写）——任务要求「照纠错解析链同源实现或复用同一辅助」即此语义，×3 必测项（坏 JSON/围栏/噪声）全覆盖。

## 7. 未验证边界

- **`{{target_language}}` 终替换与残留 fail-fast 不在本步**（SPEC M1-3 裁决归 handler，P1-5 步骤 2）；service 层 `system_prompt=None` 时回落分层默认 prompt（占位符原样），由 P1-5 传入已替换 prompt；
- **真实 LLM 的守恒遵循率**：coverage 反向校验、429 退避、非 json_mode 提供商（Qwen/GLM/Ollama）解析层均以 mock 验证；真机行为随 beta.1 冒烟（M5 真机清单 1）；
- **串行降级下的重复调用**：纠错同源语义——break 时仍在池内运行/排队的批，其结果被丢弃后于串行段重跑一次（429 用例以 `calls in (7,8)` + 末次调用断言容纳该竞态）；真实 429 场景的重复计费未在真机验证；
- **`call_llm` 内层重试与批级重试的叠加**（内层 3 次 API 重试 × 批级 1 次重试）沿纠错现状，未单独计时验证；
- **重复真实 segment_id 输入**：入口归一后 id 撞号会使 target_ids 去重、守恒按集合判——主轨段 id 天然唯一（模型约束），未为此加防御；
- **千段级长跑**：仅 70 段分窗验证；千段性能与 token 观测随 M1-4 千段用例与 beta.1 真机（M5）。

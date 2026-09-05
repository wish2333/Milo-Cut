# Milo-Cut v3.0.4 总记录（record）

> 分支：`dev-3.0.4`（自 tag `v3.0.3` = `55c68da` 拉出；回滚锚点 tag `v3.0.4-base` 打在拉出点）
> 门禁 diff 基准：恒为 `v3.0.3`（不受文档入库影响）
> 依据：[PLAN](./plan-v3.0.4.md) · [SPEC](./spec-v3.0.4.md)（冲突以 SPEC 为准）· [PRD](./PRD-v3.0.4.md) · [探索报告](./探索报告-v3.0.4.md)

---

## 0. 交付概览

- **P0 完成**：分支/tag/基线/门禁脚本（P0-1、P0-2）。
- **P1 完成（2026-09）**：S1 翻译副轨全链交付——P1-1 任务类型与事件双侧 / P1-2 prompt 注册（params={} 裁决）/ P1-3 批处理管线（coverage 反向守恒）/ P1-4 批量落盘单 patch / P1-5 handler 与 expose（五情形失败语义）/ P1-6 前端闭环与 props 链三级接通。P1 末门禁：pytest 774（期望 ≥739）/ vitest 771 collected·770 passed（期望 ≥760·759）/ build / lint / ruff / 红线全过。
- **tag `v3.0.4-beta.1`** 已打在 P1-6 合入 commit（代码闭环 + 全门禁绿）。★ beta.1 双平台真机冒烟**待用户执行**（继承 3.0.3「冒烟后置裁决」先例，record-3.0.3 已有先例登记）：清单 = 翻译全链路（入口语言记忆 / 进度 / 完成自动切轨 / undo 整轨回退 / 千段耗时与 token 观测）+ 双语导出 + 播放双语第二行，建议覆盖至少一家非 json_mode provider（Qwen/GLM/Ollama）；异常项走 smoke-fix 流程（合入 dev-3.0.4，tag 不动）。
- P2 起各 phase 完成态 / tag 链 / 规模对照实际值：P4 归档时汇总。

## 1. 分步记录索引

| 步 | record 文件 | 状态 | 合入 commit |
|---|---|---|---|
| P0-1 | [record-3.0.4-P0-1.md](./record-3.0.4-P0-1.md) | 已完成 | 文档入库 `83a61d6`；基线全绿 |
| P0-2 | [record-3.0.4-P0-2.md](./record-3.0.4-P0-2.md) | 已完成 | 门禁脚本三段 dry-run exit 0 |
| P1-1 | [record-3.0.4-P1-1.md](./record-3.0.4-P1-1.md) | 已完成 | 合入 `b4d71a6`（本行由 P1-2 补登记） |
| P1-2 | [record-3.0.4-P1-2.md](./record-3.0.4-P1-2.md) | 已完成（负责人已审查合并，EXPECTED_KEYS 增行已追认，见 §4） | 合入 `6925bae` |
| P1-3 | [record-3.0.4-P1-3.md](./record-3.0.4-P1-3.md) | 已完成（负责人已审查合并，llm_service.py +384 纯新增零删改，门禁复跑 exit 0） | 合入（merge P1-3，pytest 749 全绿） |
| P1-4 | [record-3.0.4-P1-4.md](./record-3.0.4-P1-4.md) | 已完成（负责人已审查合并；project_service.py +155 单一方法纯新增，报告经 patch meta side-channel 携带已登记） | 合入（merge P1-4，pytest 760 全绿） |
| P1-5 | [record-3.0.4-P1-5.md](./record-3.0.4-P1-5.md) | 已完成（负责人已审查合并；main.py +245 四 hunk 纯新增、config.py +1 键，五情形失败语义对照齐备） | 合入（merge P1-5，pytest 774 全绿） |
| P1-6 | [record-3.0.4-P1-6.md](./record-3.0.4-P1-6.md) | 已完成（负责人已审查合并；props 链三级接通，App.vue 零改动） | 合入（merge P1-6，pytest 774 / vitest 771-770 全绿） |
| P2-1 | [record-3.0.4-P2-1.md](./record-3.0.4-P2-1.md) | 已完成 | 合入（merge P2-1，pytest 776 全绿） |
| P2-2 | [record-3.0.4-P2-2.md](./record-3.0.4-P2-2.md) | 已完成（store 形参二选一取 B：correction_service 仅签名 + detail JSON 键，互清/seg_map 零触碰，裁决见 record §2） | 合入（merge P2-2 `d28568a`，pytest 782 全绿） |
| P2-3 | [record-3.0.4-P2-3.md](./record-3.0.4-P2-3.md) | 已完成（pending 作用域化：seg_map/互清/get 按 scope；防御行为二选一取「显式失败返回」；主轨 track_name="" 约定；accept/reject/accept_high/clear 四函数零触碰） | （待合入） |
| P2-4 | [record-3.0.4-P2-4.md](./record-3.0.4-P2-4.md) | 已完成（accept/reject 超集 patch 化：patch 层三裁决落实【主轨 segments+analysis / 副轨 tracks+analysis / reject analysis】+ undo 捕获层双层 + 时间轴钉扎 fail-fast；清债 #14 = switch_timeline 全量刷新 workaround 删除；useLlmTasks/main.py/WorkspacePage/App.vue 零改动） | （待合入） |
| P2-5 ~ P2-6 | （待建） | 未开始 | |
| P3-1 ~ P3-9 | （待建） | 未开始 | |
| P4-1 ~ P4-5 | （待建） | 未开始 | |

## 2. 门禁基线（P0 首跑登记，零改动干净起点）

登记口径：SPEC M0-2「门禁基线」+ PLAN P0-1。实际数字见 [record-3.0.4-P0-1.md](./record-3.0.4-P0-1.md)。

| 项 | 期望（SPEC） | 实际（P0 首跑） |
|---|---|---|
| pytest | 716 passed 全绿 | 716 collected + exit 0 全绿（pytest 9 本环境不打印汇总行，双证登记） |
| vitest | 756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例） | 756 collected / 755 passed / 1 failed（失败项 = useRowLayout.perf.test.ts 挂载墙钟 19.8ms，环境例吻合） |
| build（vue-tsc + vite） | 通过 | 通过 |
| lint（eslint） | 0 errors 0 warnings | 0/0 |
| ruff | 0 problems | All checks passed |
| 红线 R0-1 ~ R0-4 + dev/build.py 人工核对 | 全部空/零 | 全部空/零 |

### 执行环境偏差登记（PLAN P0-2 回落条款）

- 本执行环境（Linux 沙箱工作区）`bun run` 不可用：bun 1.3.9 内建 script runner 报 `CouldntReadCurrentDirectory`（`--shell=system` 同败；bun -e / Bun.spawnSync 正常），疑与路径组件 `/vol1/@appshare` 权限位解析有关。
- 回落方式：前端门禁以 node 直跑等价命令执行——`./node_modules/.bin/vitest run`、`./node_modules/.bin/vue-tsc --noEmit` + `./node_modules/.bin/vite build`、`./node_modules/.bin/eslint .`；语义与 `bun run test/build/lint` 逐条一致（package.json scripts 原样拆解）。
- 依据 PLAN P0-2：「shell 环境受限时回落命令块手动执行 + record 登记（不得因脚本问题阻塞合入）」。门禁脚本 `scripts/gates-v3.0.4.sh` 将内置该回落（bun 可用时优先 `bun run`）。

## 3. 后端改动登记表（SPEC 附录 A 模板；每 phase 追加，P4 终检逐条核对）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别（只增/受控改点①/受控改点②/登记改点） |
|---|---|---|---|---|
| P0 | （无——零改动基线） | | | |
| P1-1 | core/models.py | TaskType 追加 LLM_TRANSLATION（LLM 区块末尾，1 行+注释） | R1.2 | 只增 |
| P1-1 | core/events.py | 新增 LLM_TRANSLATION_COMPLETED 常量 | R1.4 | 只增 |
| P1-1 | frontend/src/utils/events.ts | 同 commit 新增 EVENT_LLM_TRANSLATION_COMPLETED（R0-2 双侧） | R1.4 | 只增 |
| P1-2 | core/llm_prompts.py | 新增 _TRANSLATION_SYSTEM 常量与 DEFAULT_PROMPTS["translation"] 注册项（params={} 空注册——SPEC M1-3 关键裁决：{{target_language}} 由 handler 终替换，不走 params 注入） | R1.2 | 只增 |
| P1-3 | core/llm_service.py | 文件末尾纯追加 384 行：新增 analyze_subtitle_translation 及模块级私有辅助 _translation_segment_id / _validate_translation_coverage（复刻纠错批处理骨架：批窗 30+字符预算 4000 / 并发 5 / opaque id / 4 层解析 / BatchLedger / 每批一次重试 / 连续 429 转串行 / cancel 逐批 / progress 批粒度；关键差异 = coverage 反向校验全量输出守恒，任一批重试后仍失败整任务 fail 零落盘；上下文 = 源文 ±ctx 窗口） | R1.2 | 只增 |
| P1-4 | core/project_service.py | 仅新增 create_translation_track 一个方法（import_srt_as_track 之后插入，单一 hunk +155 零删改）：入口时间轴钉扎 + 写侧重复语言双保险 + items 幂等对账当下主轨（落空进 uncovered_ids 不静默、全部落空含空 items 拒绝零写入）+ start/end 逐字段复制当下主轨段时间 + track_{track_id}_seg_{start:.3f} 命名空间 + bind=True 精确 1:1 建 offset=0 bindings + 单 _success_patch(tracks/bindings) 整体替换落盘（报告经 meta side-channel 携带 track_id/written_count/target_count/uncovered_ids）；generate_subtitle_keep_ranges 零触碰 | R1.3 | 只增 |
| P2-1 | main.py | start_subtitle_correction 增可选形参 track_id: str = "" 并入 payload（默认空 = 主轨，既有调用零影响） | R2.1 | 登记改点 |
| P2-2 | main.py | `_handle_subtitle_correction` 新增 track_id 非空分支（R2.1，SPEC M2-1）：轨定位（缺失 raise "Track not found: {track_id}" 任务 failed）→ 段源 = 轨内 segments（全 subtitle 型）→ bindings 反查表（b.track_id 过滤，ext_id→main_id）跳过主轨 confirmed-deleted 的绑定副轨段（无绑定保留，语义对齐导出映射）→ partial hints 不收集不透传（主轨 else 分支原逻辑逐字节不动，仅缩进）；store 调用点透传 track_id=track_id（二选一取 B，见 record-P2-2 §2）；其余流程共用零改动 | R2.1 | 登记改点 |
| P2-2 | core/correction_service.py | store_subtitle_corrections 签名追加 track_id: str = "" + detail JSON 增键 "track_id"（空串 = 主轨）+ docstring；互清（kept_results）与 seg_map 构建零触碰（作用域化 = P2-3） | R2.1 | 受控改点② |
| P2-3 | core/correction_service.py | store / get 两函数 track 作用域化（受控改点② 收口，R2.2，SPEC M2-2）：新增模块级 `_detail_track_scope`（存量无键 → "" 主轨作用域；非 JSON/非 dict → None 保守不清）；store seg_map 按 scope（空 = 主轨原路径；非空 = 轨内 segments，轨缺失防御性显式失败）+ 互清精确到「detail.track_id == 本次 track_id」同类型结果 + detail JSON 增键 "timeline_id"（供 P2-4 钉扎）；get 输出逐条附 track_id/track_name（主轨 ""/""，前端据空串判主轨）+ 悬空过滤（轨已删 → 跳过）+ 段解析按 scope（回退 0.0 保留）；accept/reject/accept_high_confidence/clear 四函数零触碰 | R2.2 | 受控改点② |
| P2-4 | core/correction_service.py | accept/reject 超集 patch 化（R2.3，SPEC M2-3）：新增模块级 `_detail_timeline_scope`（存量无 timeline_id 键 → "" 缺省放行；非 JSON/非 dict → None 跳过钉扎不猜归属）；accept 解析后时间轴钉扎（timeline_id 非空且 ≠ active → 「该结果属于其他时间轴，请切换后审阅」零写入）+ 按 detail.track_id 分流——主轨逻辑不变、返回超集 {segment_id, patch: _success_patch(segments+analysis)}（:157 兼容），副轨新路径（轨/段缺失显式失败 → 复用 _assert_timestamps_unchanged + _check_correction_confidence + reattach_words【words=[] 原样空表】→ track.model_copy 整体替换写回 transcript.tracks + 移除结果 → {segment_id, track_id, patch: _success_patch(tracks+analysis)}，bindings 零触碰）；reject 同款钉扎（malformed detail 跳过检查保 v3.0.3 行为）+ 超集 {segment_id, patch: _success_patch(analysis)}；accept_high_confidence/clear/store/get 零触碰 | R2.3 | 受控改点② |
| P2-4 | frontend/src/composables/useWorkspaceActions.ts | handleAccept/handleRejectCorrection 直调桥取回超集 patch：调用前按 scope pushSnapshot（correctionUndoLayers：主轨 [segments,analysis] / 副轨 [tracks,analysis]，条目 track_id 判 scope）→ emit("project-updated", patch) 走 applyProjectPatch，删除 switch_timeline 全量刷新 workaround（清债 #14；无 patch 防御回落）；handleSwitchTimeline 成功分支挂 void loadCorrections 重取钩子；新增 CorrectionReviewEntry/CorrectionReviewResult 类型 + correctionUndoLayers 辅助；deps 接口零字段增删（accept/rejectCorrection 保留接口移出解构） | R2.3 | 登记改点 |
| P1-5 | core/config.py | DEFAULTS LLM 区块追加 1 行 `"llm_translation_target_language": "en",`（+注释共 +4）：前端「记忆上次语言」持久化键（R1.1，P1-6 消费） | R1.1 | 只增 |
| P1-5 | main.py | 四 hunk 纯新增 +245 零删改：① 模块级 `_TRANSLATION_LANGUAGES` 常量（9 语言 BCP-47 → 英文显示名，expose 校验与 handler 终替换共用单一事实来源）；② 注册块追加 `register_handler(TaskType.LLM_TRANSLATION, self._handle_translation)`（R1.2）；③ `_handle_translation` 五步流程（R1.2/R1.3）：主轨段源排除 confirmed-deleted → get_effective_prompt("translation") + `{{target_language}}` 英文显示名终替换（残留 `{{` fail-fast）→ analyze_subtitle_translation（失败 raise 零落盘；target_language 传 code，已核实不进 prompt）→ 完成时时间轴钉扎校验（不一致 failed 零落盘带回到原时间轴指引）→ create_translation_track 单 patch 写入 + emit LLM_TRANSLATION_COMPLETED（payload 含 track_id/track_name/language/written_count/target_count/uncovered_ids/ledger，取自 meta.translation 与管线 ledger）+ emit llm:token_usage + 返回含 project dump；④ `@expose start_translation` 六步校验序（R1.5）：LLM configured → project open → 语言合法 → 主轨有 subtitle 段 → 同语言 translation 轨拒绝（文案含「可清空或删除该轨后重试」）→ create_task("llm_translation", {...})；既有函数零触碰 | R1.2/R1.5 | 只增 |

## 4. 断言反转白名单登记（R0-3 唯一例外）

| 文件:行 | 反转内容 | 理由 | 登记步 |
|---|---|---|---|
| （待 P3-2 执行后登记：TranscriptRow.test.ts:270-275「never enters text edit under globalEditMode」→「enters text edit under globalEditMode (track variant)」） | | R3.1 裁决反转（T1 方案 A） | P3-2 |

后端 `tests/` 断言零删改（反转白名单为空）。

### 4.1 既有测试文件受控增行登记（R0-3 门禁 grep 之外，负责人追认制）

| 文件:位置 | 增行内容 | 性质与理由 | 追认 | 登记步 |
|---|---|---|---|---|
| tests/test_llm_prompts.py EXPECTED_KEYS 集合 | `+ "translation",`（1 行，集合字面量） | 非断言删改（`^-` grep 恒 0）；既有 `test_all_expected_keys_present` 为注册表键集**精确等值**断言，translation 注册后不增该键必红；增行后断言严格性保持且覆盖扩为 6 键，符合「只增不改」精神 | 架构师已追认（P1-2 合并审查） | P1-2 |

## 5. 超期决策树触发留痕（立项会授权，四要素：日期/触发信号/裁决与影响面/回写文档处）

（无触发则本节记「未触发」）

## 6. 性能对账（P4-2 回填口径：千段单 patch revision+1 / accept 无全量刷新 / beta.1 真机耗时与 token 观测）

（待回填）

## 7. 版本池回写（P4-3：新增 6 项 + 出池 1 项，见 PRD §10.2）

（待回填）

## 8. 遗留清单（P4 归档：本版未尽事项 + 3.0.5 候选登记）

（待回填）

# Milo-Cut v3.0.4 总记录（record）

> 分支：`dev-3.0.4`（自 tag `v3.0.3` = `55c68da` 拉出；回滚锚点 tag `v3.0.4-base` 打在拉出点）
> 门禁 diff 基准：恒为 `v3.0.3`（不受文档入库影响）
> 依据：[PLAN](./plan-v3.0.4.md) · [SPEC](./spec-v3.0.4.md)（冲突以 SPEC 为准）· [PRD](./PRD-v3.0.4.md) · [探索报告](./探索报告-v3.0.4.md)

---

## 0. 交付概览

（P4 归档时回填：各 phase 完成态 / tag 链 / 规模对照实际值）

## 1. 分步记录索引

| 步 | record 文件 | 状态 | 合入 commit |
|---|---|---|---|
| P0-1 | [record-3.0.4-P0-1.md](./record-3.0.4-P0-1.md) | 已完成 | 文档入库 `83a61d6`；基线全绿 |
| P0-2 | [record-3.0.4-P0-2.md](./record-3.0.4-P0-2.md) | 已完成 | 门禁脚本三段 dry-run exit 0 |
| P1-1 | [record-3.0.4-P1-1.md](./record-3.0.4-P1-1.md) | 已完成 | 合入 `b4d71a6`（本行由 P1-2 补登记） |
| P1-2 | [record-3.0.4-P1-2.md](./record-3.0.4-P1-2.md) | 已完成（负责人已审查合并，EXPECTED_KEYS 增行已追认，见 §4） | 合入 `6925bae` |
| P1-3 | [record-3.0.4-P1-3.md](./record-3.0.4-P1-3.md) | 已完成（负责人已审查合并，llm_service.py +384 纯新增零删改，门禁复跑 exit 0） | 合入（merge P1-3，pytest 749 全绿） |
| P1-4 ~ P1-6 | （待建） | 未开始 | |
| P2-1 ~ P2-6 | （待建） | 未开始 | |
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

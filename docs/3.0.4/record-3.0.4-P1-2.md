# record-3.0.4-P1-2：translation prompt 注册

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-2`（待负责人审查后合入 `dev-3.0.4`）
> 对应 PLAN：Phase 1 / P1-2　SPEC：M1-3（R1.2）

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/llm_prompts.py` | 新增 `_TRANSLATION_SYSTEM` 常量（`_SEARCH_SYSTEM` 之后）+ `DEFAULT_PROMPTS["translation"]` 注册项（`search` 之后），`params` 空注册；两处均附裁决注释。英文指令，内容含 SPEC M1-3 四要素：逐条输出 JSON 数组、id 原样回传、`{{target_language}}` 占位、不得增删条目（输出条数 = target_segment_ids 数），并要求仅输出 JSON 数组无多余文本 | R1.2 | 只增 |
| `tests/test_translation_prompt.py` | 新建（13 用例，挂 M5 矩阵 M1 管线组「占位符项」）：占位符穿透硬编码默认层 ×3（空 settings / 空 settings+空 project_prompts / 隐式 None）、全局 settings 层、项目覆盖层、system_override 早返回路径 ×2（项目层 / settings 层，断言原文逐字返回含占位符）+ 注册表 `params == {}` 防回归 + `get_default_params("translation") == {}` + prompt 内容要求（target_segment_ids/segment_id/translated_text/不得增删/仅 JSON）+ `{{target_language}}` 为唯一占位符（P1-5 残留 fail-fast 的前提） | M5 | 只增（新文件） |
| `tests/test_llm_prompts.py` | `EXPECTED_KEYS` 集合追加 `"translation",` 1 行 + 注释（受控偏离，见 §5） | — | 受控偏离（仅增 1 行，断言行零改动） |

**关键裁决落实**：`DEFAULT_PROMPTS["translation"]["params"] == {}` ✅——`_inject_placeholders`（llm_prompts.py:197-210）只遍历注册 params 的 key，`_format_param`（:178-194）对未注册 key 返回空串；params 留空则 `{{target_language}}` 原样穿透 `get_effective_prompt` 三层（硬编码默认 → 全局 settings llm_prompts → 项目 timeline.llm_prompts）与 system_override 早返回路径，语言名由 handler（P1-5 步骤 2）终替换注入。注册处与常量处均落注释固化该裁决，`test_registry_params_empty` 为防回归断言。

## 2. 红线命令实际输出

- **`git diff v3.0.3 -- core/llm_prompts.py`**：仅 2 个新增 hunk——常量块（`_SEARCH_SYSTEM` 后，15 行含 3 行注释）与注册项（`search` 后，8 行含 4 行注释），共 23 行新增、**0 行删改**，既有函数/常量零触碰 ✅（输出见 §3 门禁 R0-5 段）
- **R0-1 白名单**：`core/llm_prompts.py` 在 SPEC M0-1 表内；禁改面（pywebvue/ 等 12 项）diff 为空 ✅
- **R0-3 后端断言零删改**：`git diff v3.0.3 -- tests/ | grep -cE '^-[[:space:]]*(assert |self\.assert)'` = **0** ✅（`tests/test_llm_prompts.py` 的断言行 `assert set(DEFAULT_PROMPTS.keys()) == self.EXPECTED_KEYS` 逐字节未动，仅集合字面量增 1 元素行）
- **R0-4 / R0-2**：models.py diff 仅 P1-1 的 2 行（本步零触碰）；events 双侧各 1 行（P1-1 既有）✅
- **R0-5**：`git diff v3.0.3 --stat -- core/ main.py` = events.py +3 / llm_prompts.py +23 / models.py +2；dev.py / build.py 零改动 ✅

## 3. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**729 passed in 5.89s**（基线 716 + 本步新增 13，全绿）
- ruff：All checks passed（首跑 I001 import 排序 1 错，已修：`_TRANSLATION_SYSTEM` 排序先于 `DEFAULT_PROMPTS`，复跑干净）
- vitest：756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确）
- build（vue-tsc + vite）：通过
- lint（eslint）：0/0
- 红线 R0-1 ~ R0-5 + dev/build.py：全部 PASS（明细见 §2）

## 4. 后端改动登记表追加（总表已同步）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别 |
|---|---|---|---|---|
| P1-2 | core/llm_prompts.py | 新增 _TRANSLATION_SYSTEM 常量与 DEFAULT_PROMPTS["translation"] 注册项（params={} 空注册，SPEC M1-3 关键裁决：{{target_language}} 由 handler 终替换，不走 params 注入） | R1.2 | 只增 |

## 5. 受控偏离登记：tests/test_llm_prompts.py 追加 1 行（待负责人追认）

- **冲突事实**：`TestDefaultPrompts.test_all_expected_keys_present` 对注册表键集做**精确等值**断言（`EXPECTED_KEYS` 恰 5 键，git 历史无「后加键」先例——5 键均出自文件创建 commit `1781e2c`）。注册 `translation`（SPEC M1-3 硬要求）与「pytest 全绿」（门禁验收标准）联立下，该既有测试必红；PLAN/SPEC 均未预见此点（docs/3.0.4/ 全文无 EXPECTED_KEYS 相关登记）。
- **处置**：`EXPECTED_KEYS` 集合字面量追加 `"translation",` 1 行 + 行尾注释。断言行零改动（R0-3 门禁 grep 删除断言行 = 0 不受影响）；该测试意图（键集精确性、防伪注册）保留且因 translation 成为期望键而增强。
- **执行环境注记**：本执行为委派 subagent 会话，人工确认通道不可用（ask_user_question 被运行时拒绝），按「SPEC M1-3 注册 + 门禁全绿为硬验收 > 白名单文件清单字面」优先序自主裁决；偏离面 = 白名单外 1 文件 1 行，可一键回退（删该行即复现 pytest 红，供权衡复核）。
- **回退方案**：revert 该行 + 移除注册项 = 回到冲突原点；若负责人另裁（如等 P1-5 一并处理），分支未合入前均可改。

## 6. 未验证边界

- **终替换与残留 `{{` fail-fast 用例不在本步**（PLAN P1-2 微裁决：替换逻辑在 handler，用例随 P1-5 挂 M1 管线组）。本步以「`{{target_language}}` 为 prompt 唯一占位符」用例覆盖其前提。
- prompt 中 `target_segment_ids` 字段名锚定 M1-2 批 payload 构造（复刻纠错骨架 `_build_structured_user_message` 的 `extra_ctx`，上下文 = 源文 ±ctx 窗口）；**P1-3 实现时若改用其他字段名/不含上下文段，需回看本 prompt 措辞**（登记为 P1-3 注意项）。
- `_TRANSLATION_SYSTEM` 的 LLM 实际遵循率（id 守恒/仅 JSON 输出）随 P1-3 coverage 反向校验（mock）与 beta.1 真机验证；本步仅静态断言内容要素。
- `core/llm_prompts.py` 模块 docstring 仍写「5 system prompts」且 Prompt keys 清单未列 translation——为保「diff 仅含新增注册项」未顺带改 docstring（属改既有行），登记为文档债（P4 终检或后续步可顺带）。
- `get_llm_prompts`（main.py:2266-2287）随注册表多返回 translation 项：前端简单模式按 params 渲染表单（translation params={} → 无表单项），无破坏；本步为后端步，未加前端用例。

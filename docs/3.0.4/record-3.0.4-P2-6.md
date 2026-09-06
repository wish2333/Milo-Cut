# record-3.0.4-P2-6：可选尾项——对齐主轨上下文（副轨纠错 LLM 上下文增强）

> 日期：2026-09（P2）　分支：`dev-3.0.4-p2-6`（待合入 `dev-3.0.4`）
> 对应 PLAN：Phase 2 / P2-6　SPEC：M2-5（R2.5）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/llm_service.py` | `_build_structured_user_message`（现 :518-562）edit_hint 转发块（:550-553）之后新增 `aligned_main_text` 转发受控增行 **+4**（:554-557：注释 1 行 + `s.get("aligned_main_text")` 存在则 `item["aligned_main_text"] = str(...)`，与 edit_hint 转发同款模式）；其余零改动，`analyze_subtitle_correction` 签名与批处理管线零触碰 | R2.5 | 只增（受控增行，总记录 §4.1 追认） |
| `main.py` | `_handle_subtitle_correction` track 分支（现 :935-967）注入 `aligned_main_text` **+10/-1**（:953-957 注释 3 行 + `main_text_by_id` 主轨文本反查表 1 行；循环内 :961-967：`seg_dict = s.model_dump()` 后，有绑定主伙伴且查得非空文本则 `seg_dict["aligned_main_text"] = <主轨段 text>`）。被 confirmed-deleted 主伙伴绑定的副轨段在上游 :959-960 已 `continue`，不会走到注入点；无绑定副轨段不注入（自动退化）；主轨 else 分支逐字节不动 | R2.5 | 登记改点（track 分支内，SPEC M0-1 main.py 行 M2-1 分支的顺带增强） |
| `tests/test_correction_aligned_context.py` | 新建 4 例（§3） | R2.5 | 只增 |

实现通路说明：handler 在 seg_dict 注入自描述字段，经 `_build_structured_user_message` 转发进每批 LLM user message 的段 JSON 行（`{"id","text"[,"start","end"][,"edit_hint"][,"aligned_main_text"]}`）。opaque id / 上下文窗口 / 批处理行为全部继承既有管线，零新逻辑分支。

## 2. 架构师预裁决落实对照（1/2/3）

| # | 预裁决 | 落实 |
|---|---|---|
| 1 | 实现通路 = handler 注入自描述字段 `aligned_main_text` + builder 同款转发（2 行级）；**不复用 edit_hint 通道**（系统 prompt 已把 edit_hint 语义锚定为「句内口误/重复」提示，复用会误导模型） | 已落实：独立字段 + 独立转发块（llm_service.py:554-557），edit_hint 通路与语义零触碰；未动 `analyze_subtitle_correction` 签名（extra_context 顶层的 target_segment_ids/reference_text 通路也零触碰——对齐文本走**段级**行字段而非批级顶层键，与段一一对应自描述） |
| 2 | SPEC M0-1 白名单行校准登记：M0-1 llm_service.py 行写「仅新增 analyze_subtitle_translation 及其私有辅助」，而 SPEC M2-5（R2.5）明文点名同一文件的 extra_context 通路——SPEC 内部行级滞后（M0-1 表先于 M2-5 定稿）。本步对 `_build_structured_user_message` 的受控增行由负责人（架构师）追认，登记落点 = P2-6 record（本节）+ 总记录 §4.1（受控增行追认制）+ §3 登记表 R2.5 行；文件级红线（llm_service.py 在白名单文件集内）不受影响 | 已登记：总记录 §4.1 追认表追加一行（追认栏「架构师预裁决（P2-6 委派时）」）；总记录 §3 新增 llm_service.py / R2.5 / 只增·受控增行 行。门禁 R0-1 文件级白名单 PASS（llm_service.py 在 case 白名单内），R0-5 diff 审查制下本 +4 行由登记表覆盖 |
| 3 | 不改 llm_prompts.py（系统 prompt 不新增 aligned_main_text 说明——字段名自描述）；语义清晰度权衡登记 record；prompt 增强登记 3.0.5 候选 | 已落实：llm_prompts.py 零改动（门禁 diff 佐证）；权衡 = 字段名 `aligned_main_text` 自描述（对齐的主轨文本），模型可零说明消费；若观测到模型忽略/误用该行，3.0.5 候选 = subtitle_correction_a/b 系统 prompt 补一句参考行语义说明（登记总记录 §8 由 P4 归档汇总，本 record 留痕） |

## 3. 测试（tests/test_correction_aligned_context.py，新建 4 例；既有测试零改动）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | test_forwarded_when_present_absent_when_missing（builder 单元，2 断言） | 带字段的段转发 `aligned_main_text`（值原样）；不带的段不出现该键（M2-5 builder 通路） |
| 2 | test_bound_segment_carries_main_text | 副轨纠错请求上下文：捕获传给 `analyze_subtitle_correction` 的段列表，绑定段含 `aligned_main_text` 且值 = 对应主轨段文本（两绑定段各断言一次） |
| 3 | test_unbound_segment_no_context_still_sourced | 无绑定段：不含 `aligned_main_text`、仍出现在段源、任务 completed 正常返回（M2-5 验收「无绑定段正常出结果」） |
| 4 | test_main_path_segments_never_carry_aligned_main_text | 主轨路径回归：时间轴**存在**副轨+bindings 的前提下走主轨纠错，段列表永不含 `aligned_main_text`（防泄漏） |

驱动手法：复用 P2-2 tests/test_correction_track_source.py 的 `_Api` harness（MiloCutApi.__new__ + real ProjectService + monkeypatch 路径/config + `_register_task_handlers` + 同步 `TaskManager._execute_task`）+ mock `core.llm_service.analyze_subtitle_correction` 捕获段集；builder 单元例直接调 `_build_structured_user_message` + json.loads 断言。

## 4. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**808 passed**（804 + 4，全绿）
- ruff：0 problems；vitest：790 collected / 789 passed（唯一失败 = useRowLayout.perf.test.ts，已登记环境例）；build（vue-tsc + vite）/ lint（eslint 0/0）通过
- 红线 R0-1~R0-5：全部 PASS（禁改面 diff 为空；后端断言删除 0；白名单文件集内；dev.py/build.py 零改动）
- 本次执行 bun run 前端段可用（无回落），与 P0-1 登记的环境偏差不冲突（脚本自动探测，bun 可用则优先）

## 5. 未验证边界

- 实机 LLM 对 `aligned_main_text` 参考行的消费效果（纠错质量增益/无增益）随 beta.2 ★ 真机冒烟观测（副轨纠错清单内）。
- prompt 增强（系统 prompt 补参考行说明）为 3.0.5 候选（预裁决 3），本版不做。
- 主伙伴文本为空串时不注入（`if main_text` 守卫，与 builder falsy 检查一致）——空参考行无信息量，非语义损失。

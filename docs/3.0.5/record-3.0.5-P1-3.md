# record-3.0.5-P1-3：R5.2 行级解析兜底 translated_text + 失败中文出路指引（SPEC M5.2）

> 步骤：PLAN P1-3 · 依据：[SPEC M5.2](./spec-v3.0.5.md)（实施裁决 1-4 / 触点表）· [PLAN](./plan-v3.0.5.md) P1-3 · [PRD](./PRD-v3.0.5.md) R5.2（F3 / US-03 / F-A-10）
> 分支：`dev-3.0.5-P1-3`（已合入已删）· 提交：`3df0f4f`（代码）→ `3b037ca`（--no-ff 合入 `dev-3.0.5`）
> 顺序：P1-2 之后，R5.1×R5.2×R5.3 同族 hunk（M0-4 序 4）第二环；本步为其中唯一纯后端环（前端零改动，vitest 持平）

## 1. 改动清单（逐 hunk）

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `core/llm_service.py` | :636-652（Layer 4 action 模式后、Layer 5 sanitize 前） | **只增第三正则** `pattern_translated = "segment_id"\s*:\s*"([^"]+)".*?"translated_text"\s*:\s*"((?:[^"\\]|\\.)*)"`；逐行条目归一 `{segment_id, translated_text}`，命中即随 relevance/action 同款早退返回。置于两模式**之后**（输出互斥——relevance/action 输出不含 translated_text 键；既有两路径零回归）；无 DOTALL（行内匹配，防跨条目贪婪） | 白名单内只增（R5.2 裁决 1） |
| `core/llm_service.py` | :2010-2019（失败 error 构造，:1973-1977 原址） | 全批失败拒绝文案中文化：`翻译失败：{failed}/{total} 批处理失败（批 {ids}），本次未写入任何译文；可直接重试补译；反复失败建议更换模型或检查网络`——含**「补译」**二字（:217 断言锚定关键词）+ 批号/计数 + 出路指引（重试/换模型/查网络）；上方 coverage-gap `logger.warning` 不动（日志面非用户面） | 受控改点 (d) 文案面（R5.2 裁决 3 文案 (i)；R5.3 改判的部分成功文案落点随 P1-4 合流，本步不触碰该分支语义） |
| `tests/test_llm_translation.py` | :216-219（:217 反转） | `assert "uncovered" in result["error"]` → `assert "补译" in result["error"]`（附注释锚定 M0-3）；:216/:219-224 全保留 | 白名单反转 1 行 |
| `tests/test_llm_translation.py` | 文件尾新类 | TestTranslatedTextLineFallback 2 例（见 §2） | 只增 |
| `tests/test_llm_phase4b.py` | TestParseJsonResponseLayers 尾部 | 直测 2 例（见 §2） | 只增 |

**救回批不绕校验**（裁决 2）：解析命中只替代 `_parse_json_response_layers` 返回值，`_call_batch` 内的 `_validate_translation_coverage` 反向校验调用点零改动——漏译/未知 id 照旧进 ledger；管线级守恒断言（B1'）实证。

## 2. 用例登记（M-gate 后端 R5.2 ≥4，实际 +4）

| # | 宿主 | 用例 | 要点 |
|---|---|---|---|
| 1 | tests/test_llm_translation.py | test_near_json_line_output_rescued_with_full_conservation | 近 JSON 行输出（无 []/{} 包裹 → Layers 1-3 全败）经第三正则救回；反向映射恢复真 id 原序守恒；translated_text 逐字透传（不透明 id 捕获式对照）；ledger 零失败 |
| 2 | 同上 | test_unrescuable_output_returns_chinese_guidance_with_cost_report | 垃圾输出 → 重试 → 全批拒：error 含「补译」「批」「更换模型」；data 带 ledger+token_usage（与 R5.1 上报闭环） |
| 3 | tests/test_llm_phase4b.py | test_layer4_translated_text_fallback | 直测：segment_id+translated_text 行提取；转义引号原样保留（与 relevance/action 同契约，不反转义） |
| 4 | 同上 | test_correction_shaped_line_input_still_returns_none | 直测：纠错形态输入（segment_id+corrected_text，无三键）走既有路径 → None，新模式对纠错零副作用 |

既有例核对：test_llm_phase4b.py relevance/action 两模式既有例（:68-130 区）零改动全绿；test_llm_translation.py :192 例（:217 反转后）全绿、:224 uncovered 全量断言保留；四姊妹例 :226/:256/:518 零改动（★B-3 撤销口径兑现）。

## 3. 断言反转清单登记（M0-3 白名单）

| 文件:行（反转前） | 处置 | 意图与理由 |
|---|---|---|
| tests/test_llm_translation.py:217 `assert "uncovered" in result["error"]` | **已按白名单改写**：`assert "补译" in result["error"]` | R5.2 失败文案中文化（M0-3 预登记处置：改写为中文文案关键词，定稿关键词 = 「补译」）；语义从「失败佐证」转「缺口集出口指引」，ledger 侧 uncovered 断言（:224）全保留 |

白名单外命中：零（门禁 R0-3 PASS 实证；本步为后端白名单文件内唯一 assert 改动行）。

## 4. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  840 passed in 7.03s                        # pytest 全绿（P1-2 后 838 + 本步 4）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 852 passed (853)    # 与 P1-2 持平（本步前端零改动）；唯一失败 = perf 环境例（豁免口径）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 文件集全部在白名单内（llm_service.py + main.py[P1-2 既有]）
  [PASS] 禁改面为空 / R0-2 events 双侧零改动 / 断言白名单外零删改（双侧）/ dev.py build.py 零改动
===== 门禁汇总: 全部通过 (exit 0) =====
```

定向先行：pytest 四文件（translation/phase4b/expose/smoke_fix）79 全绿。

## 5. 解释登记与未验证边界

- **部分成功文案落点**（M5.2 裁决 3 (ii)）：不走 error 通道、改 completion payload 驱动（uncovered toast）——随 P1-4（R5.3）合流交付，本步不触碰 `if ledger.failed:` 分支语义（:1967 区现仍全量拒，R5.3 改判在 P1-4）。
- **regex 无 DOTALL 的边界**：跨行条目（segment_id 与 translated_text 换行分隔）不救回——与「line-by-line fallback」层语义一致（SPEC 原文模式即无 DOTALL）；此类输出落入 Layer 5 → None → 全批拒 + 中文指引，出路可见。
- **真机边界**：非 json_mode 提供商（Qwen/GLM/Ollama）实际近 JSON 输出形态的救回率留 beta.1 真机轮（冒烟清单「至少一家非 json_mode 提供商」项）验证。
- 文案 (i) 中「可直接重试补译」同时满足 SPEC 草案「可直接重试」与定稿约束「含补译二字」；:217 锚定关键词即「补译」。

## 6. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步追加 2 行（llm_service 解析层只增 + 失败文案受控改点 (d) 文案面）+ 测试 2 行，已汇总入总表。

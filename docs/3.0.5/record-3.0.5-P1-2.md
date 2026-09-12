# record-3.0.5-P1-2：R5.1 翻译失败/取消成本可见（SPEC M5.1；序 4 起步）

> 步骤：PLAN P1-2 · 依据：[SPEC M5.1](./spec-v3.0.5.md)（实施裁决 1-5 / 触点表）· [PLAN](./plan-v3.0.5.md) P1-2 · [PRD](./PRD-v3.0.5.md) R5.1（F2+F5 / US-02 / F-A-01·02·03）
> 分支：`dev-3.0.5-P1-2`（已合入已删）· 提交：`4ea180e`（代码）→ `b5694ef`（--no-ff 合入 `dev-3.0.5`）
> 顺序：P1-1 之后（序 1 已合入，duplicate 态防护已入门禁基线）；本步为 R5.1×R5.2×R5.3 同族 hunk（M0-4 序 4）的起步步

## 1. 改动清单（逐 hunk）

### 后端（白名单内）

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `core/llm_service.py` | :1869-1878（轮询主循环取消） | 取消返回附 `data: {"token_usage": total_usage, "ledger": ledger.to_dict()}`——键级只增，`error` 串保持 `"Cancelled"`（task_manager 双通道判别与 test_translation_smoke_fix.py:169 既有断言零影响） | 白名单内只增（R5.1，E-1 三处之一） |
| `core/llm_service.py` | :1907-1915（批内 Cancelled） | 同款 data 附带 | 白名单内只增（R5.1，三处之二） |
| `core/llm_service.py` | :1949-1957（429 串行循环取消） | 同款 data 附带 | 白名单内只增（R5.1，三处之三） |
| `main.py` | :1266-1292（_handle_translation 失败/取消分支） | **受控改点 (e)**：① 取消判据 = `cancel_event.is_set()` 事件优先 + `error == "Cancelled"` 字符串兜底（task_manager :299-301 双通道同构，MF-2/焦点 5）；② 取消路径 = 有 data 则 emit `llm:token_usage`（`{**token_usage, "status": "cancelled"}`）且**不** emit `llm:analysis_failed`，`raise RuntimeError("Cancelled")`；③ 失败路径 = 有 data 则先 emit `llm:token_usage`（`status: "failed"` + `failed_batches: ledger.failed`）再 emit `llm:analysis_failed` 再 raise（成本先行，M5.1 裁决 3）；无 data 的失败 envelope 走原路径零变化（test_translation_expose 既有 :373 例全绿实证） | 受控改点 (e) |

修正管线（analyze_subtitle_correction :1125/:1146/:1174）**零触碰**（R5.5/P3 领地）；纠错侧取消 token 上报维持不做（B-6 裁决）。

### 前端（三处）

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `frontend/src/pages/WorkspacePage.vue` | :17-18 / :99-106 / :622-637 / 两处 Timeline 绑定 | EVENT_TASK_CANCELLED 分支补 `llm_translation`：中性提示 `翻译已取消，已消耗约 X tokens`（info/3000；X = useLlmAnalysis.lastUsage.total_tokens，事件时序 = token_usage 先 emit → raise → task:cancelled，lastUsage 必已就位）；lastUsage 消费为本步新接（useLlmAnalysis 此前无消费方）；`llmProgressMessage` 透传 Timeline（两处实例） | 只增（R5.1 裁决 2） |
| `frontend/src/composables/useLlmTasks.ts` | :91-95 / :125-129 / :263-277 / :336·:355·:379·:403 / :579 | ① EVENT_TASK_CANCELLED 补 `errorMsg.value = null`，**task_type 判据限定 `llm_translation`**（SG2-2；其余类型残留 = 既有独立缺陷，record §8 登记不修）；② 新单例 `progressMessage`（task:progress 监听存 `detail.message`，EVENT_DEMO_RESET + 四个 start* 复位，随 Shared 导出） | 只增 + SG2-2 限定 |
| `frontend/src/components/workspace/AIAssistantPanel.vue`（+ Timeline.vue 透传） | props 增 `progressMessage?` + 进度条块后新增提示 | 进度区当 message 含 `"(serial)"` 子串时显示「限流中，已切串行，剩余批次处理中」（data-test=serial-downgrade-notice；零新增事件、零后端键——后端信号源 = 串行降级循环 :1942 既有 message 后缀）；Timeline 增 `llmProgressMessage?` prop 单点透传 | 只增（R5.1 裁决 4） |
| `frontend/src/composables/useLlmAnalysis.ts` | :5-13 | TokenUsagePayload 只增 `status?: string` 键（累计逻辑 status 无关、未知值自然忽略） | 类型只增 |

### 测试（+12）

| # | 宿主 | 用例 | 要点 |
|---|---|---|---|
| B1 | tests/test_llm_translation.py | test_cancel_before_first_poll_carries_cost_report | 预置 cancel_event → 轮询 loop-top 检查（:1871 路径）返回 envelope 含 token_usage+ledger 键、ledger 零计数、无 translations |
| B2 | 同上 | test_cancel_during_serial_fallback_carries_cost_report | 3×429 降级 → 首个 "(serial)" progress 回调置 cancel → 串行循环 loop-top 检查（:1939 路径）返回含 data；ledger.failed 确定性前缀 [0,1,2] |
| B3 | tests/test_translation_expose.py | test_cancel_emits_token_usage_and_suppresses_failure_event | handler 级：任务终态 cancelled；恰一次 llm:token_usage（status=cancelled + token 值）；零 llm:analysis_failed；零写入 |
| B4 | 同上 | test_failure_emits_cost_before_failure_event_with_failed_batches | 任务终态 failed；token_usage 先于 analysis_failed（顺序断言）；payload status=failed + failed_batches==[1]；零写入 |
| B5 | 同上 | test_event_first_judging_set_event_beats_failure_string | cancel_event 已置 + error 为真实失败串（Rate limited）→ 判为取消：raise "Cancelled"、无 analysis_failed、无 data 时零 token 事件 |
| F1 | useLlmTasks.progress.test.ts | stores detail.message into progressMessage | 运行中存 message（含 serial 样例）；启动复位 null；普通 message 覆盖 serial（不粘滞） |
| F2 | 同上 | translation cancel clears errorMsg (SG2-2) | 失败残留后 llm_translation 取消 → errorMsg 清空、isRunning/progress 复位 |
| F3 | 同上 | non-translation cancel keeps errorMsg | llm_subtitle_correction 取消 → errorMsg 保留（record §8 遗留边界锁） |
| F4 | AIAssistantPanel.test.ts | shows the notice while running when progressMessage carries (serial) | isRunning + "(serial)" → 「限流中，已切串行，剩余批次处理中」渲染 |
| F5 | 同上 | hides the notice for plain messages and when not running | 普通 message / 非运行态 → 不渲染（双边界一例） |
| F6 | WorkspacePage.translation.test.ts | task:cancelled for llm_translation shows the neutral cost toast | 先 fire llm:token_usage(1200, cancelled) 再 fire task:cancelled → toast「翻译已取消，已消耗约 1200 tokens」info/3000 |
| F7 | 同上 | cancel without any token report shows the zero-cost variant | 无 token 事件 → 「已消耗约 0 tokens」防御态 |

M-gate 额度核对：后端 R5.1 ≥4 → 实际 5（B1-B5）；前端 ≥3 → 实际 7（F1-F7）。

## 2. 断言反转清单登记（M0-3 白名单）

| 文件:行（反转前） | 处置 | 意图与理由 |
|---|---|---|
| tests/test_llm_translation.py:614 `assert result_holder == {"success": False, "error": "Cancelled"}` | **已按白名单反转**：改为 `success is False` + `error == "Cancelled"` + `set(data.keys()) >= {"token_usage", "ledger"}` + `"translations" not in data` 四断言；docstring :565-567 同步改写（bare envelope → cancel envelope with cost report） | R5.1 取消返回附 data（M0-3 预登记处置：反转 + data 键断言）；「无合并输出」不变量以 `"translations" not in data` 延续（M1-5 持久化安全半边保留）；:608/:612 两断言保留未动 |

白名单外命中：零（门禁 R0-3 双侧 PASS 实证）。test_translation_smoke_fix.py:169 既有断言零改动全绿（error 串不变兑现）。

## 3. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  838 passed in 7.04s                        # pytest 全绿（基线 833 + 本步 5）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====                           # bun 路径
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 852 passed (853)    # 基线 846/845 + 本步 7；唯一失败 = useRowLayout.perf 环境例（豁免口径，脚本判定 PASS）
  [PASS] build 通过（vue-tsc + vite build） / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [INFO] 白名单内: core/llm_service.py / main.py（逐 hunk 见本 record §1 登记表）
  [PASS] 后端 diff 文件集全部在白名单内 / 禁改面为空
  [PASS] R0-2 events 双侧零改动（零新增事件兑现，status 走既有 llm:token_usage）
  [PASS] 后端断言白名单外零删改（:614 反转落在白名单文件内）
  [PASS] 前端断言白名单外零删改
  [PASS] dev.py / build.py 零改动
===== 门禁汇总: 全部通过 (exit 0) =====
```

定向先行：pytest 三文件 43 全绿（含 :614 反转后整例）；vitest 三宿主 37 全绿。

## 4. 解释登记与未验证边界

- **失败面「已消耗 X tokens」的展示口径（解释登记）**：失败路径的 token 成本经 `llm:token_usage`（status=failed）事件上报（B4 断言兑现「token 上报」）；用户可见文案面 = 红框错误文本自带「失败批 [n]/N」（现状英文，P1-3/R5.2 中文化收口）+ 取消态 toast 的 X tokens 消费链（F6/F7）。SPEC M5.1 触点表将 useLlmTasks/面板改动限定为三处（本步未加第四处失败专用展示），与 PLAN「前端三处」逐字一致；失败 token 的面板级独立展示行不在本步面内。
- **串行取消测试的确定性手法**：B2 以首个 "(serial)" progress 回调置 cancel（串行循环 iter-2 的 loop-top 检查确定性触发），避免线程时序竞态；ledger.failed 仅断言确定性前缀 [0,1,2]（串行批结局与取消竞速）。
- **真机边界**：连续 429 实际降级手感（限流提示出现时机）与取消 toast 手感留 beta.1 真机冒烟轮；B-6 裁决的纠错侧取消上报不做（维持 §10.2 ② 登记）。
- progressMessage 为全任务类型共享存储（非 translation 专属），显示门 = `isRunning && includes("(serial)")`——"(serial)" 后缀仅翻译管线产生，其余类型 message 天然不触发显示。

## 5. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步追加 4 行（llm_service 三 hunk 只增 + main.py 受控改点 (e)），已汇总入总表。

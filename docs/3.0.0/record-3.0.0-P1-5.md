# Record: P1-5 M3 LLM 可靠性协议

> 日期: 2026-08-30 · 分支: `dev-3.0.0`

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/llm_service.py` | M3-1 `BatchLedger` 数据类 + smart_delete/correction 双链路失败批重试 1 次 + `uncovered_segment_ids` 上报（失败批 target 并集）；M3-3 `_sanitize_response`（think 块/围栏/首尾噪声剥离，仅作第 5 层兜底，纯减法）；M3-4 `validate_base_url_security`（getaddrinfo + ipaddress 私网/环回/链路本地拒绝，`llm_allow_local_urls` 显式放行），call_llm 与 test_connection 双入口；M3-5 不透明 ID `t1..tN`（prompt 只含 `{id,text}`，剥离 start/end；解析结果经逆映射还原，未知 id 丢弃），`effective_temperature()` 支持 `temperature_override`；`semantic_search` 强制 0.0 |
| `core/models.py` | `LlmConfig.temperature` 默认 0.3→0.1；新增 `temperature_override: float \| None` 与 `effective_temperature()` |
| `core/config.py` | `llm_temperature` 默认 0.1；新增 `llm_max_batch_chars: 4000`、`llm_allow_local_urls: False` |
| `core/llm_service.chunk_transcript_by_count` | 新增 `max_chars` 参数（字符预算提前截断，单 target 段不拆散；单批快速路径并入统一循环以保证预算生效） |
| `main.py` | smart_delete / correction handler 透传 `ledger`（task 返回值 + `llm:*_completed` 事件） |
| `frontend/src/composables/useLlmTasks.ts` | 新增 `coverageGap` ref（从 completed 事件 ledger 读取） |
| `frontend/src/pages/WorkspacePage.vue` | `coverageGap > 0` 时 toast「本次分析未覆盖 N 段…」 |
| `frontend/src/components/workspace/SettingsModal.vue` | LLM tab 暴露「批字符上限」输入 |
| `frontend/src/types/edit.ts` / `frontend/src/demo/demoBridge.ts` | Settings 类型 + demo 默认值补齐/对齐 |
| `tests/test_llm_protocol.py`（新） | 19 条 |
| `tests/test_llm_service.py` / `tests/test_llm_concurrency.py` | 默认温度断言 0.1；并发测试 fake 适配不透明 ID 协议 |

## 实现决策（对 SPEC 的偏差记录）

1. **ollama preset 不存在**：本仓 LlmProvider 枚举无 ollama。SSRF 放行改为显式设置 `llm_allow_local_urls: true`（默认 false），错误信息引导配置；后续若新增 ollama preset 可在该 preset 自动置位。
2. **批账本 UI 深度接入**：后端 ledger 完整；前端本轮以 toast 呈现覆盖缺口（never silent）。SuggestionPanel 逐段标灰的完整交互挂起，与 M3 真实链路验证同批完成（避免与 M5/M7 对 SuggestionPanel 的改动冲突）。
3. **设置键命名**：`llm_max_batch_chars`（扁平键，对齐仓库既有 `llm_*` 风格），非 SPEC 草案的 `llm.max_batch_chars` 嵌套形式。

## 验证命令与实际输出

```
uv run pytest -q                     -> 全绿（521 passed；较 478 基线 +43）
uv run ruff check <触及文件>          -> 0 问题
cd frontend && bun run build         -> 通过
cd frontend && bun run test          -> 251 passed
```

## 未验证边界

- ★ 真实 Key 链路（智能删除 + 纠错各一次，账本数字对账）待用户提供
- DeepSeek R1 think 块真实响应已由消毒层单测覆盖，真实样本待链路验证

# Record: P2-1 Day 1 M5 分层撤销 —— 后端 apply_undo + feature flag

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M5-2 / 风险评审 §4.3 M5 红线 / migration-M5.md 步骤 1

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/project_service.py` | 新增 `apply_undo(layers_payload, base_revision)`：①层白名单 `segments/edits/analysis`；②空 payload / 未知层 / `base_revision != _revision`（stale 或超前）拒绝；③**全部层先校验后变更**（Pydantic model_validate，任一失败零落盘，跨层原子）；④segments 层替换后跑 `_enforce_segment_sort_invariant`；⑤复用 `_success_patch` 返回 ProjectPatch，revision 严格 +1 |
| `core/config.py` | 新增 `undo_v2: True`（M5 feature flag，扁平键风格） |
| `main.py` | 新增 `@expose apply_undo`：flag 关闭返回 `{"success": False, "error": "undo_v2 disabled"}` 引导前端回退旧全量路径；成功路径走 `_mark_dirty`（undo 后自动保存信号） |
| `tests/test_apply_undo.py`（新） | 14 条协议一致性测试（TDD：先红后绿） |

## 实现决策（对 SPEC 的偏差/澄清记录）

1. **撤销层白名单收窄为 segments/edits/analysis**：SPEC `UndoLayer` 类型含 `media/active_timeline_id`，但 migration-M5 清单 24 个调用点的层组合全部只涉及 segments/edits（analysis 层预留给未来）；media 与 timeline 切换本就不可撤销（走 `full_project` 信封）。后端对未知层显式拒绝，防止前端伪造层。
2. **flag 键名 `undo_v2`**：SPEC 写 `undo.v2` 嵌套形式，按 P1-5 已确立的扁平键先例（`llm_max_batch_chars`）改为扁平。
3. **stale 语义与 patch 协议一致**：`base_revision` 必须等于当前 revision（≠ 即拒绝，含超前），拒绝时 `data.current_revision` 回传当前值，供前端恢复 UI（红线：stale 时刷新全量 project 不卡死，Day 2 前端实现）。

## 测试覆盖（tests/test_apply_undo.py，14 条）

- 单调性: undo 后 revision == before+1；连续 3 次 undo 严格递增无重复
- patch 载荷: 返回的 ProjectPatch 携带恢复后的层内容，内存态同步更新
- stale 拒绝: base_revision 落后/超前均拒，revision 不被拒绝调用扰动；等于当前值接受
- 跨层原子: mark 后 segments+edits 同退；edits 载荷非法时 segments 层零变更（all-or-nothing）
- 校验: 未知层 / 非列表 / 缺必填字段 / 空 payload / 无工程打开 五类拒绝
- sort invariant: 乱序快照 undo 后自动按 start 重排

## 验证命令与实际输出

```
uv run pytest tests/test_apply_undo.py -q   -> 14 passed
uv run pytest -q                            -> 全绿 538 passed（524 + 14）
uv run ruff check <触及文件>                 -> All checks passed!
```

## 未验证边界

- 前端接入（undoRecords.ts / useUndoRedo 重写 / 24 调用点迁移）→ Day 2 / Day 3
- flag=false 走旧路径的端到端回退验证 → Day 2 前端新旧并存时覆盖
- undo <5ms perf 指标 → perf-beta2（本步为纯 Pydantic 校验+替换，无序列化全量 Project，预期达标）

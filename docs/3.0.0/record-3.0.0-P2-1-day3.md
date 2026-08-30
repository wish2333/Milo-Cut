# Record: P2-1 Day 3 M5 分层撤销 —— 24 调用点迁移完成

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: migration-M5.md 清单 / 风险评审 §4.2/§4.6

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/composables/useEdit.ts` | B1-B12 逐点迁移：`snapshot(layers, label)` 分层签名，层组合按清单（B3/B4/B9/B10 跨层 `[segments, edits]`） |
| `frontend/src/composables/useAnalysis.ts` | C1-C6 迁移；C1（task 回填）为 `[segments, edits]`（静音检测/转写重建 transcript），C2-C6 `[edits]` |
| `frontend/src/composables/useSegmentEdit.ts` | D1-D3 迁移；D1 乐观更新路径 push `prev`（flush 前 before-state），D2 `[segments]`，D3 `[edits]` |
| `frontend/src/pages/WorkspacePage.vue` | A1 `["segments"] 导入 SRT`；**A2 存量 bug 修复**：`markSelectedForDeletion` 原 push `res.data`（after 状态，undo 无效），改为操作前 push `[edits]`；A3 `["segments"] 新增段落` |

## 迁移核对

- 24/24 调用点全部携带层组合 + label（grep 验证，无旧单参签名残留）
- migration-M5.md 步骤 3-7 勾销；红线自查：revision 单调（Day1 协议测试）、stale 拦截行为不变（未动 is_stale_patch）、跨层原子（后端 all-or-nothing + B3/B4/B9/B10 双层记录）

## 决策与偏差记录

1. **旧全量路径删除推迟**：plan Day3 原文"打 tag pre-undo-cleanup 后删旧路径"；风险评审 §4.6 要求"apply_undo 与旧全量路径并存一个版本，异常时前端回退旧快照栈"。**取 §4.6**：tag `pre-undo-cleanup` 已打（回滚锚点），legacy 路径保留至 beta.2 双平台冒烟通过后删除（届时 plan Phase 2 门禁一并无痕清理）。
2. **提交粒度**：迁移以单批完成（24 点模式高度一致，逐点提交无独立回滚价值）；每点层组合在代码行内注释标注（// B1... // C6），可逐点审阅。
3. **逐点手测**：按 Phase 1 以来的既定口径，手动 undo/redo 归批次双平台冒烟清单（§5 第 6 项 undo/redo ×5），Windows 侧以 257 条 vitest + build 门禁覆盖。

## 验证命令与实际输出

```
cd frontend && bun run test   -> 257 passed (22 files)
cd frontend && bun run build  -> vue-tsc + vite 通过
grep pushSnapshot（排除 test） -> 24 命中全部新签名
```

## 未验证边界

- 千段 mock 项目连续 50 次编辑 + undo 50 次自动化脚本 → P2-1 收尾（perf-beta2 前补）
- undo <5ms perf 实测 → perf-beta2
- 双平台手测（含 macOS Cmd+Z 链路经 apply_undo 通道）→ 批次冒烟

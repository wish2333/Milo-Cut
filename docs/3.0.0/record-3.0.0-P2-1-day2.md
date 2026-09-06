# Record: P2-1 Day 2 M5 分层撤销 —— 前端 undoRecords + useUndoRedo 重写

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M5-1/M5-2 / 风险评审 §4.6 回滚预案 / plan P2-1 Day 2

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/utils/undoRecords.ts`（新） | `UndoLayer`/`UndoRecord` 类型 + `captureLayers`（浅引用拷贝，零 stringify）+ `nextUndoRecordId`。**降级决策**：segments 层用数组浅拷贝引用，段级 diff + id_lineage 待 P2-3 后重评（plan Day 2 风险缓冲条款，头注已记录理由） |
| `frontend/src/utils/revision.ts`（新） | 模块级共享 `lastSeenRevision` + `noteRevision`；App.vue 保持单写者，useUndoRedo 读取作为 `apply_undo` 的 `base_revision` |
| `frontend/src/composables/useUndoRedo.ts` | 重写：分层栈（上限 100）+ undo/redo 经 `call("apply_undo", records, lastSeenRevision)`，返回 `{ok, patch}`；旧全量 JSON 快照路径完整保留（`legacyUndoStack/legacyRedoStack`，50 条 + 2MB 降 10 条规则不变），由 `isUndoV2()` getter 逐调用选择路径（风险评审 §4.6 回滚预案：新旧并存一个版本） |
| `frontend/src/App.vue` | `lastSeenRevision` 改用共享模块（`noteRevision` 写入），行为不变 |
| `frontend/src/pages/WorkspacePage.vue` | `undoV2Enabled` ref（`loadSilenceSettings` 读 `undo_v2` 设置，默认 true）注入 `useUndoRedo`；handleUndo/Redo 改为：patch → `emit("project-updated", patch)`（App.vue 现有 patch 通道应用并同步 revision）；失败 → `recoverFromUndoFailure`（clearHistory + `get_project` 全量刷新 + toast，红线"stale 不卡死"） |
| `frontend/src/demo/demoStore.ts` | 镜像 `applyUndo(layers, baseRevision)`：stale 返回 null；替换层 + revision+1 + 返回 patch 形数据 |
| `frontend/src/demo/demoBridge.ts` | 新增 `case "apply_undo"` |
| `frontend/src/composables/useUndoRedo.test.ts` | 重写：12 条 |

## 关键设计

- **undo 不再伪造 revision**：逆快照在**调用前**捕获（失败不弹栈、不写入 redo），后端 `apply_undo` 校验 `base_revision == 当前 revision` 后替换层并 `_next_revision`，返回 ProjectPatch 走现有 patch 通道——`is_stale_patch` 语义零改动。
- **过渡期兼容**：`pushSnapshot(project, layers?, label?)` 未传 layers 的旧调用点（Day 3 未迁移的 24 处）默认捕获全部可撤销层，保证迁移逐点进行时 undo 语义始终保守正确。
- **legacy 路径即回滚开关**：设置 `undo_v2=false`（前端 `undo_v2 !== false` 读取）后 push/undo/redo 全部走旧 JSON 路径，满足验收④"flag 关闭可完整回退旧行为"。

## 测试覆盖（useUndoRedo.test.ts，12 条；257 全绿 +26）

- 分层捕获：仅请求层入 records（未请求层键不存在）；捕获的是调用时 before-state
- base_revision 取共享 `lastSeenRevision`
- redo 逆记录捕获 undo 后状态；两次调用均走 apply_undo
- apply_undo 失败：记录保留在 undo 栈（不弹栈）
- 上限 100（分层）/ 50（legacy）
- legacy 路径：行为与旧版逐字节一致（undo 返回全量 Project、零后端调用）；flag 运行时切换语义
- clearHistory / canUndo/canRedo（分层栈）

## 验证命令与实际输出

```
cd frontend && bun run test   -> 257 passed (22 files)
cd frontend && bun run build  -> vue-tsc + vite 通过
```

## 未验证边界

- 24 个调用点逐点迁移（Day 3）——当前旧调用点经默认全层捕获仍正确工作
- 真机 undo 手感（含 macOS Cmd 键）→ 批次冒烟
- undo <5ms perf → perf-beta2

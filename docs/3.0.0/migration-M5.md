# M5 迁移清单 —— 分层撤销快照（P2-1）

> 用途: pushSnapshot 全部调用点逐点迁移核对（SPEC 风险评审 §4.2）。每替换一点勾销一次。
> 现状: `useUndoRedo.ts:22 pushSnapshot(project)` 全量 JSON 快照；分层化后签名改为 `pushSnapshot(layers: UndoLayer[], label)`。

## 调用点总清单

全局 grep `pushSnapshot`（排除 *.test.ts）命中与清单逐行对应；composables 内部经注入参数 `onBeforeProjectUpdate` 间接调用，一并列入。

### A. WorkspacePage.vue 直接调用（3 处）

| # | 位置 | 所属操作 | 时机 | 待替换层组合 |
|---|---|---|---|---|
| A1 | WorkspacePage.vue:940 | `handleImportSrt` 手动导入 SRT | call 前 push 当前 | `[segments]`（import_srt 整体重建 transcript；无 ED 变更） |
| A2 | WorkspacePage.vue:1124 | `markSelectedForDeletion` 多选批量标记 | call 后 push（**注意: 现状推的是 after 状态，属存量 bug**，迁移时改为操作前 push `[edits]`） | `[edits]` |
| A3 | WorkspacePage.vue:1427 | `handleAddSegment` 波形区新增段 | call 前 push 当前 | `[segments]` |

### B. useEdit.ts 内部（注入参数，12 处 snapshot() 调用）

| # | useEdit.ts 行 | 所属操作 | 待替换层组合 |
|---|---|---|---|
| B1 | 19 | `updateSegmentText` | `[segments]` |
| B2 | 29 | `updateSegmentTime` | `[segments]` |
| B3 | 39 | `mergeSegments` | `[segments, edits]`（后端 ED-rebind 会改 edits） |
| B4 | 49 | `splitSegment` | `[segments, edits]`（同上，跨层原子） |
| B5 | 65 | `searchReplace` | `[segments]` |
| B6 | 78 | `markSegments` | `[edits]` |
| B7 | 88 | `confirmAllSuggestions` | `[edits]` |
| B8 | 101 | `rejectAllSuggestions` | `[edits]` |
| B9 | 122 | `deleteSegment` | `[segments, edits]`（删段会级联删 ED） |
| B10 | 132 | `deleteSilenceSegments` | `[segments, edits]` |
| B11 | 142 | `deleteSubtitleTrimEdits` | `[edits]` |
| B12 | 161 | `generateSubtitleKeepRanges` | `[edits]` |

### C. useAnalysis.ts 内部（注入参数，6 处）

| # | useAnalysis.ts 行 | 所属操作 | 待替换层组合 |
|---|---|---|---|
| C1 | 37 | `EVENT_TASK_COMPLETED` 事件回填 project（静音检测/转写完成） | `[segments, edits]` |
| C2 | 57 | `confirmEdit` | `[edits]` |
| C3 | 67 | `rejectEdit` | `[edits]` |
| C4 | 78 | `resetEdit` | `[edits]` |
| C5 | 91 | `batchUpdateEdits` | `[edits]` |
| C6 | 103 | `confirmAllEdits` / `deleteEdits`（该函数体内，复核时确认具体归属） | `[edits]` |

### D. useSegmentEdit.ts 内部（注入参数，3 处）

| # | useSegmentEdit.ts 行 | 所属操作 | 待替换层组合 |
|---|---|---|---|
| D1 | 161 | `updateSegmentTime`（本地乐观更新路径，flush 前推 prev） | `[segments]` |
| D2 | 189 | `updateSegmentText`（乐观更新路径） | `[segments]` |
| D3 | 214 | `toggleEditStatus` | `[edits]` |

## 迁移步骤（每点一个提交）

- [x] 1. 后端 `apply_undo` + feature flag `undo.v2` 落地（TDD 协议测试先行）✅ Day1（record-3.0.0-P2-1-day1，14 条协议测试）
- [x] 2. `utils/undoRecords.ts` + `useUndoRedo.ts` 重写（新旧并存，flag 切换）✅ Day2（record-3.0.0-P2-1-day2，12 条测试）
- [x] 3. A1 → A2 → A3 逐点替换，每点跑 `useUndoRedo.test.ts` + 手测 undo/redo ✅ A2 顺带修复存量 bug（:1146 原推 after 状态 → 改为操作前 push before-state）；手测归批次双平台冒烟
- [x] 4. B1-B12 逐点替换（useEdit 全函数过一遍）✅ 层组合按清单逐点标注
- [x] 5. C1-C6 逐点替换（useAnalysis）✅ C1 为 [segments, edits]（分析回填重建 transcript）
- [x] 6. D1-D3 逐点替换（useSegmentEdit）✅ D1 乐观更新路径 push prev
- [x] 7. 全局 grep `pushSnapshot` 确认无旧签名残留（应只剩新签名 `pushSnapshot(layers, label)`）✅ 24/24 新签名（A3 + B12 + C6 + D3 = 24 个调用点全部携带层组合与 label）
- [x] 8. 打 tag `pre-undo-cleanup`，删除旧全量 JSON 快照路径 ⚠️ tag 已打；**旧路径删除推迟至 beta.2 双平台冒烟通过后执行**（风险评审 §4.6：新旧并存一个版本，异常时回退旧快照栈；与 plan Day3 表述的偏差已记录）

## 红线自查（每点替换后）

- undo/redo 后 `project._revision` 严格递增（协议测试断言）
- `is_stale_patch` 拦截行为不变；stale 时 UI 刷新全量 project 不卡死
- 跨层记录（B3/B4/B9/B10）undo 原子应用

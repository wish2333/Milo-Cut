# 实施计划: EditStatus / EffectiveStatus 同步 Bug 修复

## 概述

前端存在两套独立的 segment 状态计算函数（`getEditForSegment` 用于 badge 显示，`getEffectiveStatus` 用于行样式），它们使用不同的匹配和过滤逻辑，导致 badge 文字与行背景色/删除线不一致。本计划将这两套逻辑合并为统一的 `resolveSegmentState` 函数，同时修复后端 `mark_segments` 未清理旧 user edit 的问题。

## 影响范围分析

| 文件                                                      | 消费的函数                                                 | 需要的改动                                             |
| --------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------ |
| `frontend/src/utils/segmentHelpers.ts`                    | 定义处                                                     | 新增 `resolveSegmentState`，保留旧函数作为兼容 wrapper |
| `frontend/src/composables/useSegmentEdit.ts`              | `getEditForSegment`, `getEditStatus`, `getEffectiveStatus` | 改用 `resolveSegmentState`，移除旧 import              |
| `frontend/src/components/workspace/Timeline.vue`          | `getEditStatus`, `getEffectiveStatus`                      | 传递 `SegmentState` 而非两个独立 prop                  |
| `frontend/src/components/workspace/TranscriptRow.vue`     | props `editStatus`, `effectiveStatus`                      | 改为接收 `SegmentState`，修改 badge 显示逻辑           |
| `frontend/src/components/workspace/SilenceRow.vue`        | props `editStatus`, `effectiveStatus`                      | 同 TranscriptRow                                       |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | `getEditForSegment`, `getEffectiveStatus`                  | 改用 `resolveSegmentState`                             |
| `core/project_service.py`                                 | `mark_segments` 方法                                       | 创建新 user edit 前清理同 segment 旧 user edit         |
| `frontend/src/utils/segmentHelpers.test.ts`               | 测试旧函数                                                 | 新增 `resolveSegmentState` 测试                        |
| `frontend/src/composables/useSegmentEdit.test.ts`         | 测试 composable                                            | 更新 `toggleEditStatus` 测试                           |

---

## 阶段 1: 核心状态函数 (segmentHelpers.ts)

### 步骤 1: 新增 `SegmentState` 类型和 `resolveSegmentState` 函数

- **文件**: `frontend/src/utils/segmentHelpers.ts`
- **操作**:
  - 新增 `SegmentState` 类型: `{ displayStatus, styleClass, activeEdit }`
  - 新增 `resolveSegmentState(edits, seg)` 函数（审计报告 6.1 逻辑）
  - 保留旧函数标记 `@deprecated`
- **依赖**: 无
- **风险**: 低

### 步骤 2: 编写 `resolveSegmentState` 单元测试 (TDD RED)

- **文件**: `frontend/src/utils/segmentHelpers.test.ts`
- **覆盖场景**:
  - 无 edit → `{ displayStatus: "none", styleClass: "normal", activeEdit: undefined }`
  - 单个 pending delete → `{ displayStatus: "pending", styleClass: "masked", activeEdit }`
  - 单个 confirmed delete → `{ displayStatus: "confirmed", styleClass: "masked", activeEdit }`
  - 单个 rejected delete → `{ displayStatus: "rejected", styleClass: "normal", activeEdit: undefined }`
  - 多 edit 共存按 priority 排序，user source 优先
  - rejected 高优先级 edit 不影响 styleClass 但影响 displayStatus
  - overlap < 0.3s 不匹配
  - target_id + overlap 去重
- **依赖**: 步骤 1
- **风险**: 低

---

## 阶段 2: Composable 适配 (useSegmentEdit.ts)

### 步骤 3: 修改 import 和状态查询函数

- **文件**: `frontend/src/composables/useSegmentEdit.ts`
- **操作**:
  - import 改为 `resolveSegmentState, SegmentState`
  - 新增 `resolveState(seg): SegmentState`
  - 保留 `getEffectiveStatus`/`getEditStatus` 作为兼容 wrapper
  - `UseSegmentEditReturn` 新增 `resolveState` 导出
- **依赖**: 步骤 1
- **风险**: 低

### 步骤 4: 修改 `toggleEditStatus` 使用 `resolveSegmentState`

- **文件**: `frontend/src/composables/useSegmentEdit.ts`
- **新逻辑**:
  - `state.activeEdit` 存在 → 切换状态 (confirmed <-> rejected)
  - `state.displayStatus === "none"` → 创建 keep confirmed edit
  - 全部 rejected → 不操作
- **依赖**: 步骤 3
- **风险**: 中

### 步骤 5: 更新 `toggleEditStatus` 测试

- **文件**: `frontend/src/composables/useSegmentEdit.test.ts`
- **新增测试**:
  - "uses activeEdit from resolveSegmentState"
  - "does not create keep edit when all edits are rejected"
- **依赖**: 步骤 4
- **风险**: 低

---

## 阶段 3: UI 组件适配 (Timeline + TranscriptRow + SilenceRow)

### 步骤 6: 修改 Timeline.vue 传递 SegmentState

- **文件**: `frontend/src/components/workspace/Timeline.vue`
- **操作**:
  - import 改为 `resolveSegmentState`
  - 新增 `getSegmentState(seg): SegmentState`
  - 修改 TranscriptRow/SilenceRow 的 props 绑定
- **依赖**: 步骤 1
- **风险**: 低

### 步骤 7: 修改 TranscriptRow.vue 接收 SegmentState

- **文件**: `frontend/src/components/workspace/TranscriptRow.vue`
- **操作**:
  - props: 移除 `editStatus`/`effectiveStatus`，新增 `displayStatus`/`styleClass`
  - `statusClass` computed 直接用 `props.styleClass` 映射样式
  - badge: `displayStatus === "none"` → 灰色 "无标注"
- **依赖**: 步骤 6
- **风险**: 低

### 步骤 8: 修改 SilenceRow.vue 接收 SegmentState

- **文件**: `frontend/src/components/workspace/SilenceRow.vue`
- **操作**: 同 TranscriptRow
- **依赖**: 步骤 6
- **风险**: 低

---

## 阶段 4: 波形编辑器适配 (SegmentBlocksLayer)

### 步骤 9: 修改 SegmentBlocksLayer.vue 使用 resolveSegmentState

- **文件**: `frontend/src/components/waveform/SegmentBlocksLayer.vue`
- **操作**:
  - import 改为 `resolveSegmentState`
  - `visibleBlocks` computed 用 `resolveSegmentState` 替代两个独立调用
  - `Block` 接口用 `state: SegmentState` 替代 `edit`/`effectiveStatus`
- **依赖**: 步骤 1
- **风险**: 低

---

## 阶段 5: 后端修复 (project_service.py)

### 步骤 10: 修改 `mark_segments` 清理旧 user edit

- **文件**: `core/project_service.py`
- **操作**:
  - 创建新 edit 前，删除同 segment 的旧 user edit (`source == "user" and target_id in target_seg_ids`)
  - 过滤后再拼接 new_edits
- **依赖**: 无（可并行）
- **风险**: 中 -- 需确保不误删 analysis edit

---

## 依赖关系图

```
步骤 1 (resolveSegmentState)
  ├── 步骤 2 (测试)
  ├── 步骤 3 (useSegmentEdit 适配)
  │     └── 步骤 4 (toggleEditStatus)
  │           └── 步骤 5 (composable 测试)
  ├── 步骤 6 (Timeline.vue)
  │     ├── 步骤 7 (TranscriptRow.vue)
  │     └── 步骤 8 (SilenceRow.vue)
  └── 步骤 9 (SegmentBlocksLayer.vue)

步骤 10 (后端 mark_segments) -- 独立，可并行
```

## 关键风险与缓解

| 风险                                                         | 缓解                                     |
| ------------------------------------------------------------ | ---------------------------------------- |
| topEdit rejected + activeEdit 存在 → badge "已保留" + 行红色删除线 | 这是预期行为，测试必须覆盖               |
| SilenceRow/TranscriptRow props 变更影响 Timeline             | 步骤 6/7/8 同一 PR 完成                  |
| SegmentBlocksLayer `Block.edit` 字段被其他逻辑使用           | 当前仅用于 `statusColor`，风险低         |
| 后端旧项目可能有冗余 user edit 残留                          | `resolveSegmentState` 优先级排序天然处理 |

## 成功标准

- [ ] badge 和行样式在所有场景下显示一致
- [ ] `displayStatus === "none"` 时 badge 显示 "无标注" 而非 "已保留"
- [ ] 点击 "确认"/"忽略" 按钮能正确切换 edit 状态
- [ ] 全部 rejected 的 segment 不会意外创建新 edit
- [ ] 后端 `mark_segments` 不会产生冲突 user edit
- [ ] 所有现有测试通过，新增测试覆盖核心场景
- [ ] 波形编辑器颜色与 Timeline 行样式一致

## 关键文件路径

- `frontend/src/utils/segmentHelpers.ts` -- 核心变更
- `frontend/src/composables/useSegmentEdit.ts` -- 适配 + toggleEditStatus 修复
- `frontend/src/components/workspace/Timeline.vue` -- 传递 SegmentState
- `frontend/src/components/workspace/TranscriptRow.vue` -- badge 修复
- `frontend/src/components/workspace/SilenceRow.vue` -- 适配
- `frontend/src/components/waveform/SegmentBlocksLayer.vue` -- 适配
- `core/project_service.py` -- 后端修复
- `frontend/src/utils/segmentHelpers.test.ts` -- 测试
- `frontend/src/composables/useSegmentEdit.test.ts` -- 测试
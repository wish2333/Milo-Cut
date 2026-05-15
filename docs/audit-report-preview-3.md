# Audit Report: EditStatus / EffectiveStatus 不同步问题

> **Generated:** 2026-05-15
> **Severity:** CRITICAL
> **Scope:** Analysis 建议确认/拒绝后的 UI 状态显示

---

## 1. 问题描述

用户运行 Analysis（如 filler detection）后：
- 行的背景/删除线显示为红色（"已删除"样式）
- 但 badge 显示的是"已保留"（绿色）
- 点击"确认"或"忽略"按钮无反应
- 点击"全部确认删除"后，红色删除线仍在，badge 仍显示"已保留"，无法恢复

**核心矛盾：红色删除线（行样式）和 badge（文字标签）显示的状态不一致。**

---

## 2. 两套状态系统

UI 中每个 segment 行有两个独立的状态来源，它们各自用不同的函数计算：

### 状态 A：`editStatus`（决定 badge 显示什么文字）

- **来源函数**：`getEditForSegment(edits, seg)` → 返回一个 `EditDecision` 对象
- **取值**：`edit.status`（`"pending"` / `"confirmed"` / `"rejected"` / `null`）
- **用途**：TranscriptRow 的 badge 模板
  - `"pending"` → 黄色 badge "建议删除"
  - `"confirmed"` → 红色 badge "已删除"
  - `"rejected"` → 绿色 badge "已保留"
  - `null` → 绿色 badge "已保留"（默认）

### 状态 B：`effectiveStatus`（决定行的背景色和删除线）

- **来源函数**：`getEffectiveStatus(edits, seg)` → 返回 `"normal"` / `"masked"` / `"kept"`
- **用途**：TranscriptRow 的 `statusClass` computed
  - `"masked"` → 红色背景 + 删除线
  - `"kept"` → 绿色背景
  - `"normal"` → 无特殊样式（回退到 editStatus 决定样式）

### 问题根因

这两个函数用 **不同的匹配逻辑** 来查找"属于这个 segment 的 edit"：

| | `getEditForSegment`（badge） | `getEffectiveStatus`（行样式） |
|---|---|---|
| 匹配方式 1 | `e.target_id === seg.id` | `e.target_id === seg.id` |
| 匹配方式 2 | `isOverlapping(e, seg, 0.3)` （后来加的） | `isOverlapping(e, seg, 0.3)` |
| 是否过滤 rejected | 不过滤（返回找到的第一个） | 过滤（`e.status !== "rejected"`） |
| 有多个匹配时 | 返回数组中第一个 | 按 priority 排序取最高的 |

**结果**：
1. 如果 edit 的 `target_id` 不匹配 segment 的 `id`，`getEditForSegment` 找不到 edit（badge = null → "已保留"），但 `getEffectiveStatus` 通过 overlap 找到了（行样式 = "masked" → 红色删除线）
2. 如果同一个 segment 有多个 edit，`getEditForSegment` 可能返回一个 rejected 的 edit（badge = "已保留"），但 `getEffectiveStatus` 过滤掉 rejected 后找到一个 active 的 delete edit（行样式 = "masked" → 红色删除线）

---

## 3. 相关代码

### 3.1 核心匹配逻辑 `segmentHelpers.ts`

```typescript
// ===== 决定 badge 的函数 =====

export function getEditForSegment(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision | undefined {
  // 匹配方式 1：target_id 精确匹配
  const byId = edits.find(e => e.target_id === seg.id)
  if (byId) return byId

  // 匹配方式 2：时间范围重叠（后加的，有 0.3s 阈值）
  const overlapping = edits.filter(e => isOverlapping(e, seg, 0.3))
  if (overlapping.length > 0) {
    return [...overlapping].sort((a, b) => b.priority - a.priority)[0]
  }

  return undefined
}

// ===== 决定行样式的函数 =====

export function getEffectiveStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): "normal" | "masked" | "kept" {
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg, 0.3),
  )
  const active = related.filter(e => e.status !== "rejected")  // <-- 过滤 rejected
  if (active.length === 0) return "normal"
  const top = [...active].sort((a, b) => b.priority - a.priority)[0]
  if (top.action === "delete") return "masked"
  return "kept"
}

// ===== 辅助函数 =====

export function getEditStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision["status"] | null {
  return getEditForSegment(edits, seg)?.status ?? null
}

export function isOverlapping(
  edit: EditDecision,
  seg: Segment,
  minOverlapSeconds = 0.0,
): boolean {
  const overlapStart = Math.max(edit.start, seg.start)
  const overlapEnd = Math.min(edit.end, seg.end)
  return overlapEnd - overlapStart > minOverlapSeconds
}
```

### 3.2 TranscriptRow 样式和 badge 逻辑 `TranscriptRow.vue`

```typescript
// 行样式（优先看 effectiveStatus，回退到 editStatus）
const statusClass = computed(() => {
  if (props.effectiveStatus === "masked") {
    return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"  // 红色删除线
  }
  if (props.effectiveStatus === "kept") {
    return "border-l-3 border-green-400 bg-green-50"
  }
  switch (props.editStatus) {
    case "pending": return "border-l-3 border-yellow-400 bg-yellow-50"
    case "confirmed": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "rejected": return "border-l-3 border-green-400 bg-green-50"
    default: return ""  // 无 edit 时无样式
  }
})
```

```html
<!-- Badge（只看 editStatus） -->
<template v-if="editStatus === 'pending'">
  <span @click.stop="emit('confirm-edit')">建议删除</span>
  <button @click.stop="emit('reject-edit')">保留</button>
</template>
<template v-else-if="editStatus === 'confirmed'">
  <span @click.stop="emit('toggle-status')">已删除</span>
</template>
<template v-else-if="editStatus === 'rejected'">
  <span @click.stop="emit('toggle-status')">已保留</span>
</template>
<template v-else>
  <!-- editStatus === null（getEditForSegment 返回 undefined） -->
  <span @click.stop="emit('toggle-status')">已保留</span>  <!-- 默认显示已保留 -->
</template>
```

### 3.3 Timeline 组件如何传递状态 `Timeline.vue`

```typescript
import { getEditStatus as queryEditStatus, getEffectiveStatus as queryEffectiveStatus } from "@/utils/segmentHelpers"

// 从 props.edits 计算，传给 TranscriptRow
function getEditStatus(seg: Segment): EditDecision["status"] | null {
  return queryEditStatus(props.edits, seg)
}
function getEffectiveStatus(seg: Segment): "normal" | "masked" | "kept" {
  return queryEffectiveStatus(props.edits, seg)
}
```

```html
<TranscriptRow
  :edit-status="getEditStatus(seg)"
  :effective-status="getEffectiveStatus(seg)"
  ...
/>
```

### 3.4 toggleEditStatus 逻辑 `useSegmentEdit.ts`

```typescript
async function toggleEditStatus(segment: Segment, nextStatus?: string): Promise<void> {
  const edits = project.value.edits
  const edit = getEditForSegment(edits, segment)  // 用 getEditForSegment 查找 edit

  if (edit) {
    // 找到 edit → 切换状态
    const status = nextStatus ?? (
      edit.status === "confirmed" ? "rejected"
      : edit.status === "rejected" ? "confirmed"
      : "confirmed"
    )
    await call<Project>("update_edit_decision", edit.id, status)
  } else {
    // 没找到 edit → 创建一个 "keep" edit
    await call("mark_segments", [segment.id], "keep", "confirmed")
  }

  const projRes = await call<Project>("get_project")
  if (projRes.success && projRes.data) {
    onProjectUpdate(projRes.data)
  }
}
```

### 3.5 后端 EditDecision 模型 `core/models.py`

```python
class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""                    # "filler_detection", "error_detection", "user", "subtitle_trim"
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING  # "pending" / "confirmed" / "rejected"
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None        # 指向 segment.id，或 None（range edit）
```

### 3.6 后端创建 edit 的两个来源

**来源 1：Analysis（`add_analysis_results`）**

```python
# project_service.py line 822
EditDecision(
    id=f"edit-{ar.id}",
    start=start,
    end=end,
    action="delete",
    source=source,                      # "filler_detection" 等
    analysis_id=ar.id,
    status=EditStatus.PENDING,
    priority=100,
    target_type="segment",
    target_id=ar.segment_ids[0],        # 指向 segment.id
)
```

**来源 2：用户操作（`mark_segments`）**

```python
# project_service.py line 668
EditDecision(
    id=f"edit-user-{seg.id}",
    start=seg.start,
    end=seg.end,
    action=action,                      # "delete" 或 "keep"
    source="user",
    status=edit_status,
    priority=200,                       # 比 analysis 的优先级高
    target_type="segment",
    target_id=seg.id,                   # 指向 segment.id
)
```

### 3.7 WorkspacePage 事件绑定

```html
<Timeline
  :edits="edits"
  @toggle-status="(seg) => handleToggleEditStatus(seg)"
  @confirm-segment="(seg) => handleToggleEditStatus(seg, 'confirmed')"
  @reject-segment="(seg) => handleToggleEditStatus(seg, 'rejected')"
  @confirm-all="handleConfirmAllSuggestions"
  @reject-all="handleRejectAllSuggestions"
/>
```

---

## 4. 问题复现路径

1. 导入 SRT → 创建 subtitle segments
2. 运行 Analysis（如 filler detection）→ 后端 `add_analysis_results` 创建 `EditDecision`（`status="pending"`, `action="delete"`, `target_id=segment.id`）
3. 前端收到更新 → `getEditForSegment` 应找到该 edit → badge 应显示"建议删除"
4. **实际表现**：badge 显示"已保留"，但行有红色删除线 → 两个状态函数返回不一致

---

## 5. 需要架构师决定的问题

1. **`getEditForSegment` 应该返回什么？**
   - 当前：返回找到的第一个 edit（不管 status），或 null
   - 问题：和 `getEffectiveStatus` 的逻辑不一致
   - 选项 A：让 `getEditForSegment` 使用和 `getEffectiveStatus` 完全相同的匹配 + 过滤逻辑
   - 选项 B：badge 改为用 `effectiveStatus` 驱动，不再用 `editStatus`
   - 选项 C：合并为一个统一的状态函数

2. **当 `getEditForSegment` 返回 null 时，badge 应该显示什么？**
   - 当前：默认显示"已保留"（绿色）
   - 这意味着"没有 edit = 保留"，但可能误导用户（segment 可能被其他 edit 遮罩了）

3. **`toggleEditStatus` 中，当找不到 edit 时应该做什么？**
   - 当前：创建一个 `"keep" "confirmed"` 的 edit
   - 问题：如果 segment 已经被 active delete edit 遮罩，创建 keep edit 会和 delete edit 冲突

4. **同一个 segment 是否应该允许多个 edit 共存？**
   - 当前：`mark_segments` 用 `edit-user-{seg.id}` 去重，但 `add_analysis_results` 用 `edit-{ar.id}` 不去重
   - 结果：同一个 segment 可能同时有 analysis edit 和 user edit

---

## 6. 架构决策（已确认）

> **决策日期：** 2026-05-15

### 6.1 决策 1：合并为统一状态函数 `resolveSegmentState`

**选择：选项 C** — 引入单一的 `resolveSegmentState` 函数，返回结构体，同时驱动 badge 和行样式。

**为什么不选 A 或 B：**
- 选项 A（让两函数逻辑一致）：仍是两个函数，未来单独修改又会分叉，本质上是修补而非修复
- 选项 B（badge 改用 effectiveStatus）：effectiveStatus 返回 `"masked"/"kept"/"normal"`，丢失 pending/confirmed/rejected 细分信息，badge 无法区分"建议删除"和"已删除"

**实现方案：**

```typescript
type SegmentState = {
  displayStatus: "pending" | "confirmed" | "rejected" | "none"  // 驱动 badge
  styleClass: "masked" | "kept" | "normal"                      // 驱动行样式
  activeEdit: EditDecision | undefined                           // 驱动按钮行为
}

export function resolveSegmentState(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): SegmentState {
  // 统一匹配逻辑：两种方式都用，结果合并去重
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg, 0.3)
  )
  if (related.length === 0) {
    return { displayStatus: "none", styleClass: "normal", activeEdit: undefined }
  }

  // 按 priority 降序，priority 相同时 user edit 优先（source === "user"）
  const sorted = [...related].sort((a, b) =>
    b.priority - a.priority || (b.source === "user" ? 1 : -1)
  )

  // activeEdit = 优先级最高的非 rejected edit
  const activeEdit = sorted.find(e => e.status !== "rejected")
  // topEdit = 优先级最高的（不管 rejected），用于显示 badge
  const topEdit = sorted[0]

  const styleClass: SegmentState["styleClass"] =
    activeEdit?.action === "delete" ? "masked"
    : activeEdit?.action === "keep" ? "kept"
    : "normal"

  return {
    displayStatus: topEdit.status ?? "none",
    styleClass,
    activeEdit,
  }
}
```

### 6.2 决策 2：badge 显示"无标注"而非"已保留"

**规则：** `displayStatus = "none"` 时显示中性"无标注"状态。

**关键原则：** `null/none` 的语义是"没有任何编辑决策"，而不是"已保留"。"已保留"只在明确存在 `action="keep"` 的 edit 时显示。

### 6.3 决策 3：toggleEditStatus 使用 activeEdit

**修复方案：** `toggleEditStatus` 改用 `resolveSegmentState` 提供的 `activeEdit`，而不是 `getEditForSegment`：

```typescript
async function toggleEditStatus(segment: Segment, nextStatus?: string): Promise<void> {
  const state = resolveSegmentState(project.value.edits, segment)

  if (state.activeEdit) {
    // 有 active edit → 切换状态
    const status = nextStatus ?? (
      state.activeEdit.status === "confirmed" ? "rejected"
      : state.activeEdit.status === "rejected" ? "confirmed"
      : "confirmed"
    )
    await call<Project>("update_edit_decision", state.activeEdit.id, status)
  } else if (state.displayStatus === "none") {
    // 真的没有任何 edit → 才创建 keep edit
    await call("mark_segments", [segment.id], "keep", "confirmed")
  }
  // 其他情况（有 edit 但全是 rejected）：不创建新 edit，让用户通过 badge 操作

  const projRes = await call<Project>("get_project")
  if (projRes.success && projRes.data) {
    onProjectUpdate(projRes.data)
  }
}
```

### 6.4 决策 4：允许多个 edit 共存，有优先级规则

| 规则 | 说明 |
|---|---|
| user edit 优先 | `priority=200` 的 user edit 始终覆盖 `priority=100` 的 analysis edit |
| 同 source 去重 | `mark_segments` 创建 user edit 时，应先删除同一 segment 的已有 user edit（当前已用 `edit-user-{seg.id}` 实现，保持即可） |
| analysis edit 不去重 | 多个 analysis 可能都检测到同一 segment，保留所有记录有审计价值，通过 priority 排序解决冲突 |
| rejected 不参与样式计算 | `effectiveStatus` 已有此逻辑，统一到 `resolveSegmentState` 后继续保持 |

**后端补充要求：** `mark_segments` 创建新 user edit 前，需将同 segment 的旧 user edit 标记为 superseded 或直接删除。当前 `edit-user-{seg.id}` 的 ID 去重只能防止重复创建，无法处理 action 从 delete 改为 keep 的情况。

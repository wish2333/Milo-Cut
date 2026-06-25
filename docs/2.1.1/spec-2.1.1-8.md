# Spec: 高光提取功能 Bug 修复 (v2.1.1-7)

基于 audit-2.1.1-6 的延续调查和用户访谈，本文档定义高光提取功能 7 个缺陷的修复规范。

---

## 问题总览

| ID | 严重性 | 模块 | 现象 | 根因 |
|----|--------|------|------|------|
| A | P0 | 前端 | Timeline 右键「加入精华」→ `Segment not found or not a subtitle` | `call()` 传参错误：传对象而非字符串 |
| B | P0 | 前端 | 侧边栏右键「删除高光」→ `No highlight found for segment` | 同 A |
| C | P1 | 前端 | 退出重进项目后高光 UI 记录消失 | `highlightResults` 仅从事件填充，不水合持久化数据 |
| D | P1 | 后端 | 每次重跑高光不清理旧数据导致堆积 | `add_analysis_results` 纯追加模式 |
| E | P1 | 后端 | `llm_highlight` 的 action 错误设为 `delete` | `add_analysis_results` L1318 硬编码 `action="delete"` |
| F | P1 | 后端 | 删除建议组不清理 `AnalysisResult` + `dirty_flags` | `delete_edit_decisions_batch` 仅操作 `edits` |
| G | P2 | 后端 | 删除高光不清理关联 `EditDecision` | `remove_highlight_segment` 仅更新 `analysis` |

---

## Bug A / B: 前端调用传参错误

### 位置

`frontend/src/pages/WorkspacePage.vue:1270-1288`

```typescript
// Bug A — L1281-1282
async function handleAddToHighlight(segmentId: string) {
  const res = await call("add_highlight_segment", { segment_id: segmentId })
  //                                              ^^^^^^^^^^^^^^^^^^^^^^^^ BUG: 传入对象
}

// Bug B — L1270-1272
async function handleRemoveHighlight(segmentId: string) {
  const res = await call("remove_highlight_segment", { segment_id: segmentId })
  //                                                  ^^^^^^^^^^^^^^^^^^^^^^^^ BUG: 传入对象
}
```

### 根因

`bridge.ts:call(method, ...args)` 使用可变位置参数。传入 `{segment_id: segmentId}` 作为第一个位置参数时，后端 `add_highlight_segment(self, segment_id: str, ...)` 收到的 `segment_id` 是整个对象 `{"segment_id": "xxx"}` 而非字符串 `"xxx"`，导致 `seg.id == segment_id` 永远不匹配。

### 修复

改为直接传字符串：

```typescript
// fix A
const res = await call("add_highlight_segment", segmentId)

// fix B
const res = await call("remove_highlight_segment", segmentId)
```

### 验证

1. 在 Timeline 任意字幕行右键 → 「加入精华」→ 不再报错，应提示「已加入精华」
2. 在侧边栏「精华」tab 高光卡片右键 → 「删除高光」→ 不再报错，应提示「精华片段已移除」

---

## Bug C: 重开项目后高光 UI 记录消失

### 位置

- `frontend/src/composables/useLlmTasks.ts:71` — `highlightResults` ref 初始化为 `[]`
- `frontend/src/composables/useLlmTasks.ts:137-178` — 仅从 `llm:highlight_progress` / `llm:highlight_completed` 事件填充
- `frontend/src/pages/WorkspacePage.vue:407` — `analysisResults` computed 正确从 `activeTimeline.analysis.results` 读取
- `frontend/src/pages/WorkspacePage.vue:2075` — `HighlightModeView` 接收 `highlightItems` = `highlightResults`（来自 useLlmTasks）

### 根因

`highlightResults` 是纯事件驱动内存状态，从不从持久化 project 数据水合。重开项目时事件不触发 → 空数组 → UI 显示「暂无高光片段」。

数据**确实持久化**在 `timeline.analysis.results`（type: `"llm_highlight"`），且 `analysisResults` computed 已正确读取，但 `HighlightModeView` 不消费它。

### 修复

在 project 加载时（WorkspacePage 收到 project prop 变化或 onMounted），从 `activeTimeline.analysis.results` 中提取 `type === "llm_highlight"` 的记录来水合 `highlightResults`。

具体方案：在 WorkspacePage 的 `watch(() => props.project, ...)` 或 `onMounted` 中添加水合逻辑：

```typescript
function hydrateHighlightResults(project: Project) {
  const tl = project.timelines.find(t => t.id === project.active_timeline_id)
  const hlResults = (tl?.analysis?.results ?? [])
    .filter(r => r.type === "llm_highlight")
  if (hlResults.length > 0) {
    highlightResults.value = hlResults.flatMap(r =>
      r.segment_ids.map(sid => ({
        segment_id: sid,
        highlight_reason: r.detail ?? "",
        density: (r.confidence >= 0.9 ? "high" : r.confidence >= 0.5 ? "medium" : "low") as "high" | "medium" | "low",
      }))
    )
    // also compute total duration from segments
  }
}
```

同时在 `EVENT_TASK_COMPLETED` 的 `llm_highlight` 分支中调用此函数替代仅依赖事件填充。

### 补充：也需水合 `jumpCuts`

`detect_highlight_jump_cuts` 后端端点已正确从 `analysis.results` 读取（`main.py:2490`），但前端只在 `llm:highlight_completed` 事件中调用它（`useLlmTasks.ts:171-177`）。重开项目时应也调用一次。

### 验证

1. 运行高光提取 → 退出项目 → 重新打开项目 → 切换到「精华」tab → 应看到之前提取的高光列表
2. `totalDuration`、`targetDuration` 应在重开后正确恢复
3. jump cut 警告应在重开后正确显示

---

## Bug D: 重跑高光不清理旧数据

### 位置

- `core/project_service.py:1286-1287` — `add_analysis_results` 纯追加
- `frontend/src/composables/useLlmTasks.ts:264-270` — `resetHighlight()` 仅清内存

### 根因

`add_analysis_results` 将新 `AnalysisResult` 与已有结果合并（L1286-1287），同时追加新 `EditDecision`（L1332）。每次重跑都在旧数据上叠加。

`resetHighlight()` 只清空前端 `highlightResults` ref，不调用任何后端 API。

### 修复

#### 后端：新增 `clear_highlight_results` 方法

在 `project_service.py` 中新增方法：

```python
def clear_highlight_results(self, preserve_manual: bool = True) -> dict:
    """Clear llm_highlight AnalysisResults and their EditDecisions.
    
    Args:
        preserve_manual: If True, keep manual_highlight entries.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}
    
    sources = {"manual_highlight"} if preserve_manual else set()
    tl = self.active_timeline
    
    # Find highlight AnalysisResult IDs to remove
    removed_ar_ids: set[str] = set()
    remaining_results = []
    for r in tl.analysis.results:
        if r.type == "llm_highlight" and r.id.split("_")[0] not in sources:
            removed_ar_ids.add(r.id)
        else:
            remaining_results.append(r)
    
    # Remove associated EditDecisions
    remaining_edits = [
        e for e in tl.edits
        if e.analysis_id not in removed_ar_ids
    ]
    
    self._update_active_timeline(
        analysis=tl.analysis.model_copy(update={"results": remaining_results}),
        edits=remaining_edits,
    )
    
    cleared = len(tl.analysis.results) - len(remaining_results)
    return {"success": True, "data": {"cleared": cleared}}
```

#### 后端：在 `_handle_highlight` 中先清理再追加

在 `main.py:_handle_highlight` 存储新结果前：

```python
if not task.payload.get("_workflow_accumulate"):
    # Clear old highlight results before adding new ones
    self._project.clear_highlight_results()
    store = self._mark_dirty(
        self._project.add_analysis_results(analysis_results, source="llm_highlight")
    )
```

#### 前端：重跑前弹窗确认

在 `WorkspacePage.vue` 的 `handleStartHighlight` （或 `startHighlight` composable 封装）中，执行高光提取前弹窗确认：

```typescript
async function handleStartHighlight(targetMinutes: number) {
  if (hasHighlightResults.value) {
    if (!window.confirm(
      `当前已有 ${highlightResults.value.length} 个高光片段。重新提取将清除现有结果，是否继续？`
    )) return
  }
  await startHighlight(targetMinutes)
}
```

### 验证

1. 第一次运行高光提取 → 得到 N 条结果
2. 第二次运行（不改参数）→ 弹窗确认 → 旧结果被清除，仅有第二次的 M 条结果（无 N+M 叠加）
3. 手动添加的高光片段（source=`manual_highlight`）不应被清除

---

## Bug E: llm_highlight action 错误设为 delete

### 位置

`core/project_service.py:1314-1325`

```python
new_edits.append(EditDecision(
    id=edit_id,
    start=start,
    end=end,
    action="delete",       # <-- 硬编码，对所有 source 生效
    source=source,
    analysis_id=ar.id,
    ...
))
```

### 根因

`add_analysis_results` 设计之初仅服务于 smart-delete（删除类建议），后续扩展支持 highlight（保留类标记）时未修改 action 逻辑。

### 连锁影响

1. 高光 `EditDecision` 被 `SuggestionPanel` 的 `totalPending` / `totalAll` 统计（它们按 `action === "delete"` 计数）
2. 高光条目不显示为任何 group（SuggestionPanel 的 group 按 source 过滤不包含 `llm_highlight`），但统计数被虚增

### 修复

根据 `source` 参数决定 action：

```python
# In add_analysis_results:
highlight_sources = {"llm_highlight", "manual_highlight"}
is_highlight = source in highlight_sources

new_edits.append(EditDecision(
    id=edit_id,
    start=start,
    end=end,
    action="keep" if is_highlight else "delete",
    source=source,
    analysis_id=ar.id,
    status=EditStatus.PENDING,
    priority=100,
    target_type="segment",
    target_id=ar.segment_ids[0],
))
```

### 验证

1. 运行高光提取 → 检查 `data/projects/<name>/project.json` 中 `source: "llm_highlight"` 的 EditDecision → `action` 应为 `"keep"`
2. SuggestionPanel 统计数不应包含高光条目（在 Bug E+F 同步修复后验证）

---

## Bug F: 删除建议组不清理 AnalysisResult + dirty_flags

### 位置

- `core/project_service.py:728-745` — `delete_edit_decisions_batch` 仅操作 `edits`
- `core/project_service.py:1280-1335` — `add_analysis_results` 追加 AnalysisResult（永不清理）

### 用户决策

删除建议组时 **同时清理关联 AnalysisResult 和 segment dirty_flags**。

### 修复

扩展 `delete_edit_decisions_batch` 为级联删除：

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    """Permanently remove edit decisions and associated data by id.

    Cascading cleanup:
    1. Remove EditDecision entries from timeline.edits
    2. Remove associated AnalysisResult entries from timeline.analysis.results
    3. Clear dirty_flags on affected segments for the deleted source type
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    ids_set = set(edit_ids)
    tl = self.active_timeline

    # 1. Find edits to remove + their analysis_ids
    removed_analysis_ids: set[str] = set()
    for e in tl.edits:
        if e.id in ids_set and e.analysis_id:
            removed_analysis_ids.add(e.analysis_id)

    updated_edits = [e for e in tl.edits if e.id not in ids_set]
    removed = len(tl.edits) - len(updated_edits)
    if removed == 0:
        return {"success": False, "error": "No matching edit decisions found"}

    # 2. Remove associated AnalysisResults
    updated_results = [
        r for r in tl.analysis.results
        if r.id not in removed_analysis_ids
    ]

    # 3. Clear dirty_flags on affected segments
    #    Determine the dirty_flag key based on deleted source types
    affected_seg_ids: set[str] = set()
    for e in tl.edits:
        if e.id in ids_set and e.target_id:
            affected_seg_ids.add(e.target_id)
    
    flag_map = {
        "llm_smart": "llm_smart_processed",
        "silence_detection": None,  # no dirty_flag for silence
        "llm_highlight": None,      # no dirty_flag for highlight
    }
    
    updated_segments = list(tl.transcript.segments)
    for i, seg in enumerate(updated_segments):
        if seg.id in affected_seg_ids:
            new_flags = dict(seg.dirty_flags)
            # Remove relevant flags (conservative: only remove known analysis flags)
            for key in ("llm_smart_processed", "llm_corrected", "llm_uncovered"):
                new_flags.pop(key, None)
            if new_flags != seg.dirty_flags:
                updated_segments[i] = seg.model_copy(update={"dirty_flags": new_flags})

    self._update_active_timeline(
        edits=updated_edits,
        analysis=tl.analysis.model_copy(update={"results": updated_results}),
        transcript=tl.transcript.model_copy(update={"segments": updated_segments}),
    )
    
    logger.info(
        "Permanently deleted %d edits + %d analysis results + cleaned %d segments",
        removed,
        len(tl.analysis.results) - len(updated_results),
        len([s for s in updated_segments if s.id in affected_seg_ids]),
    )
    return {"success": True, "data": self._current.model_dump()}
```

### 补充：SuggestionPanel 按 source 过滤（用户决策）

`frontend/src/components/workspace/SuggestionPanel.vue` 的 `totalPending` 和 `totalAll` 应排除非建议类 source：

```typescript
const SUGGESTION_SOURCES = new Set(["silence_detection", "llm_smart", "llm_smart_delete"])

const totalPending = computed(() =>
  props.edits.filter(e =>
    e.status === "pending" &&
    e.action === "delete" &&
    SUGGESTION_SOURCES.has(e.source)
  ).length
)
const totalAll = computed(() =>
  props.edits.filter(e =>
    e.action === "delete" &&
    SUGGESTION_SOURCES.has(e.source)
  ).length
)
```

### 验证

1. 运行智能删除分析 → 产生建议条目
2. 右键某组 → 「删除本组建议」→ 弹窗确认
3. 检查 `project.json` → 该组的 `EditDecision` 已删除、关联 `AnalysisResult` 已删除、受影响 segment 的 `dirty_flags` 已清理
4. SuggestionPanel 建议数正确减少
5. 高光 tab 的高光条目不受影响（source 不同，不应被级联）

---

## Bug G: 删除高光不清理关联 EditDecision

### 位置

`main.py:1466-1469`

```python
self._project._update_timeline_by_id(
    tl_id,
    analysis=timeline.analysis.model_copy(update={"results": remaining}),
)
# BUG: 只更新 analysis，不清理 edits 中的关联 EditDecision
```

### 根因

`remove_highlight_segment` 仅操作 `analysis.results`，但 `add_analysis_results` 同时写入了 `analysis.results` 和 `edits`。删除时不同步清理 `edits`，导致孤儿 `EditDecision` 残留。

### 修复

同时清理关联的 EditDecision：

```python
@expose
def remove_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
    if self._project.current is None:
        return {"success": False, "error": "No project open"}

    project = self._project.current
    tl_id = timeline_id or project.active_timeline_id
    timeline = project.get_timeline(tl_id)
    if timeline is None:
        return {"success": False, "error": f"Timeline {tl_id} not found"}

    results = timeline.analysis.results
    removed = [r for r in results if segment_id in r.segment_ids]
    if not removed:
        return {"success": False, "error": f"No highlight found for segment {segment_id}"}

    remaining = [r for r in results if segment_id not in r.segment_ids]
    removed_ar_ids = {r.id for r in removed}

    # Also remove associated EditDecisions
    remaining_edits = [
        e for e in timeline.edits
        if e.analysis_id not in removed_ar_ids
    ]

    self._project._update_timeline_by_id(
        tl_id,
        analysis=timeline.analysis.model_copy(update={"results": remaining}),
        edits=remaining_edits,
    )
    self._mark_dirty({"success": True})

    return {"success": True, "data": {"removed_count": len(removed)}}
```

### 验证

1. 添加高光片段 → 检查 `project.json` 中有对应 `AnalysisResult`(type=`llm_highlight`) 和 `EditDecision`(source=`manual_highlight`)
2. 删除该高光片段 → `AnalysisResult` 和 `EditDecision` 应同时被移除
3. 项目的 `edits` 数组中不应存在孤儿 `EditDecision`（source 为 `llm_highlight` 或 `manual_highlight` 但无对应 `AnalysisResult` 的）

---

## 实施计划

### Phase 1: 紧急修复（P0 — 阻断用户操作）

| 任务 | 文件 | 描述 |
|------|------|------|
| P1.1 | `WorkspacePage.vue:1272,1282` | 修复 `handleRemoveHighlight` / `handleAddToHighlight` 传参为字符串 |

### Phase 2: 后端数据完整性（P1 — 数据正确性）

| 任务 | 文件 | 描述 |
|------|------|------|
| P2.1 | `project_service.py:1314-1325` | 根据 source 决定 EditDecision.action（Bug E） |
| P2.2 | `project_service.py:728-745` | 扩展 `delete_edit_decisions_batch` 级联删除 AnalysisResult + dirty_flags（Bug F） |
| P2.3 | `project_service.py` (新方法) | 新增 `clear_highlight_results` 方法 |
| P2.4 | `main.py:909-913` | `_handle_highlight` 中先清理旧高光再写新结果（Bug D） |
| P2.5 | `main.py:1466-1469` | `remove_highlight_segment` 同步清理关联 EditDecision（Bug G） |

### Phase 3: 前端数据水合 + UI 完善（P1 — 用户体验）

| 任务 | 文件 | 描述 |
|------|------|------|
| P3.1 | `useLlmTasks.ts` | 新增 `hydrateHighlightsFromProject(project)` 函数 |
| P3.2 | `WorkspacePage.vue` | project 加载 / 变化时调用水合函数（Bug C） |
| P3.3 | `WorkspacePage.vue` | 高光重跑前弹窗确认（Bug D 前端部分） |
| P3.4 | `SuggestionPanel.vue:101-102` | totalPending/totalAll 按 source 过滤（Bug E 前端部分） |

### Phase 4: 屎山数据清理（一次性脚本）

| 任务 | 文件 | 描述 |
|------|------|------|
| P4.1 | `core/project_service.py` | 新增 `cleanup_orphan_edits()` 方法：遍历所有 project，删除无对应 AnalysisResult 的 highlight EditDecision |
| P4.2 | `core/project_service.py` | 新增 `cleanup_duplicate_highlights()` 方法：对同一 segment_id 的多条 AnalysisResult，保留最新一条 |

在应用启动时（`main.py` 初始化阶段）自动执行一次清理，清理完毕后置标志避免重复执行。

---

## 影响范围

| 组件 | 影响 |
|------|------|
| `core/project_service.py` | 新增 `clear_highlight_results`；修改 `add_analysis_results` action 逻辑；扩展 `delete_edit_decisions_batch`；修改 `_update_active_timeline` 调用点 |
| `main.py` | 修改 `_handle_highlight`、`remove_highlight_segment`；暴露新清理 API |
| `frontend/src/composables/useLlmTasks.ts` | 新增水合函数；修改 `resetHighlight` |
| `frontend/src/pages/WorkspacePage.vue` | 修复传参错误；新增水合调用；新增重跑弹窗 |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 按 source 过滤统计数 |

---

## 不做事项

- **不修改 `AnalysisResult` / `EditDecision` 数据模型结构** — 保持向后兼容
- **不修改 `segmentHelpers.ts:resolveSegmentState`** — 已有的 `e.source !== "llm_highlight"` 过滤逻辑无需变更（Bug E 修复后 action 变为 keep 自然不会被 resolveSegmentState 当作 pending 建议处理）
- **不触碰 workflow accumulation 模式的代码路径**（`_workflow_accumulate` flag）— 该路径仅在 v2.1.0 Phase 3 工作流中使用，不在本次修复范围

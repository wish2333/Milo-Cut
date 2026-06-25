# Audit Report -- spec-2.1.1-8: 高光提取功能 7 缺陷审计

> **审计日期**: 2026-07-12
> **审计范围**: `docs/2.1.1/spec-2.1.1-8.md` 问题 A~G
> **审计方式**: 逐项核对规范描述 vs 实际代码行号、根因、修复方案、影响范围

---

## 总览确认表

| ID | 严重性 | 规范判定 | 审计结论 | 偏差说明 |
|----|--------|----------|----------|----------|
| A | P0 | `call()` 传对象而非字符串 | **确认成立**，根因描述准确 | 修复方案正确 |
| B | P0 | 同 A | **确认成立**，根因描述准确 | 修复方案正确 |
| C | P1 | `highlightResults` 不水合持久化数据 | **确认成立**，但修复方案**不完整** | 缺少 `manual_highlight` 过滤；水合逻辑时间戳冲突 |
| D | P1 | 重跑不清旧数据 | **确认成立**，但 `clear_highlight_results` 实现有 **bug** | `preserve_manual` 的 ID 前缀匹配逻辑错误；`_handle_highlight` 调用顺序有 `_mark_dirty` 遗漏 |
| E | P1 | `action="delete"` 硬编码 | **确认成立**，影响范围比规范所述**更广** | 规范未提及 `manual_highlight` 也会产生 `action="delete"`（当前同样错误）；连锁影响还包括 `resolveSegmentState` 的 `manual_highlight` 过滤缺失 |
| F | P1 | 删除建议组不级联 | **确认成立**，但 `flag_map` 的 key **不存在于代码库** | `"llm_smart_processed"` 是虚构 key，实际不存在；dirty_flags 清理对 smart-delete 来源是无操作 |
| G | P2 | 删除高光不清理 EditDecision | **确认成立**，修复方案正确 | 无偏差 |

---

## 完整功能运行逻辑

### 数据流总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: 前端触发                              │
│                                                                       │
│  Timeline 右键 "加入精华" → handleAddToHighlight(segmentId)           │
│    → call("add_highlight_segment", { segment_id })  ← BUG A          │
│                                                                       │
│  HighlightModeView 右键 "删除高光" → handleRemoveHighlight(segmentId) │
│    → call("remove_highlight_segment", { segment_id }) ← BUG B        │
│                                                                       │
│  AIAssistantPanel "开始提取" → startHighlight(targetMinutes)          │
│    → resetHighlight()  [仅清内存, ← BUG D 前端侧]                    │
│    → call("start_highlight", targetMinutes)                           │
│    → 监听 llm:highlight_progress / llm:highlight_completed            │
│       → 填充 highlightResults (纯事件驱动, ← BUG C)                   │
│       → 调用 detect_highlight_jump_cuts                              │
│                                                                       │
│  SuggestionPanel 右键组 "删除本组建议" → deleteEdits(ids)             │
│    → call("delete_edit_decisions_batch", ids)  ← BUG F               │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     LAYER 2: Bridge (bridge.ts)                       │
│                                                                       │
│  call<T>(method: string, ...args: unknown[])                          │
│    → api[method](...args)   ← 可变位置参数, 不拆包                    │
│                                                                       │
│  call("add_highlight_segment", { segment_id: "s1" })                  │
│    → api.add_highlight_segment({ segment_id: "s1" })                  │
│                                                                       │
│  Python 侧: add_highlight_segment(self, segment_id: str)              │
│    → segment_id = {"segment_id": "s1"}  ← 整个对象!                   │
│    → seg.id == segment_id 永远 false → "Segment not found"           │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     LAYER 3: 后端 API (main.py)                       │
│                                                                       │
│  add_highlight_segment(segment_id, timeline_id="")                    │
│    → 创建 manual_hl_{uuid} AnalysisResult (type="llm_highlight")      │
│    → 调用 add_analysis_results([result], source="manual_highlight")   │
│       → 追加 AnalysisResult + 创建 EditDecision(action="delete")      │
│          ← BUG E: action 应为 "keep"                                 │
│                                                                       │
│  remove_highlight_segment(segment_id, timeline_id="")                 │
│    → 从 analysis.results 过滤掉包含 segment_id 的条目                 │
│    → 仅更新 analysis, 不清理 edits ← BUG G                           │
│                                                                       │
│  _handle_highlight(task, ...)                                         │
│    → LLM 返回 results → 构建 AnalysisResult(llm_hl_{timestamp})       │
│    → if not _workflow_accumulate:                                     │
│        add_analysis_results(results, source="llm_highlight")          │
│        ← BUG D: 纯追加, 不清旧数据                                    │
│        ← BUG E: action="delete" 而非 "keep"                           │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                 LAYER 4: 服务层 (project_service.py)                   │
│                                                                       │
│  add_analysis_results(results, source)                                │
│    → all_results = existing_results + new_results  (纯追加)           │
│    → 为每个 AnalysisResult 创建 EditDecision(action="delete")          │
│       ← BUG E: 硬编码, 对 highlight source 应是 "keep"                │
│    → _update_active_timeline(analysis=..., edits=existing+new)        │
│                                                                       │
│  delete_edit_decisions_batch(edit_ids)                                │
│    → 仅过滤 edits: updated_edits = [e not in ids_set]                 │
│    → 不清理 AnalysisResult 不清理 dirty_flags ← BUG F                  │
│                                                                       │
│  (不存在) clear_highlight_results 方法                                │
│    ← BUG D 需要新增                                                    │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   LAYER 5: 持久化 (project.json)                       │
│                                                                       │
│  timeline.analysis.results: [                                         │
│    { id: "llm_hl_1720234567890", type: "llm_highlight",              │
│      segment_ids: ["s42"], confidence: 0.7, detail: "精彩..." },     │
│    { id: "manual_hl_a1b2c3d4e5f6", type: "llm_highlight",            │
│      segment_ids: ["s12"], confidence: 1.0, detail: "手动添加" }      │
│  ]                                                                     │
│                                                                       │
│  timeline.edits: [                                                    │
│    { id: "edit-llm_hl_1720234567890", action: "delete",               │
│      source: "llm_highlight", analysis_id: "llm_hl_1720234567890" },  │
│    { id: "edit-manual_hl_a1b2c3d4e5f6", action: "delete",             │
│      source: "manual_highlight", analysis_id: "manual_hl_a1b2c3d4e5f6" } │
│  ]                                                                     │
│                                                                       │
│  ← 重开项目 → BUG C: highlightResults = [] → UI 显示 "暂无高光片段"   │
│  ← 重跑高光 → BUG D: results + edits 叠加                             │
│  ← 删除建议组 → BUG F: AnalysisResult + dirty_flags 残留              │
│  ← 删除高光 → BUG G: EditDecision 孤儿残留                            │
└──────────────────────────────────────────────────────────────────────┘
```

### ID 前缀约定

| 来源 | AnalysisResult ID 格式 | EditDecision ID 格式 | `type` | `source` |
|------|----------------------|---------------------|--------|----------|
| LLM 高光提取 | `llm_hl_{timestamp_ms}` | `edit-llm_hl_{timestamp_ms}` | `llm_highlight` | `llm_highlight` |
| 手动添加高光 | `manual_hl_{uuid_hex_12}` | `edit-manual_hl_{uuid_hex_12}` | `llm_highlight` | `manual_highlight` |
| LLM 智能删除 | `llm_smart_{ts}_{i}` | `edit-llm_smart_{ts}_{i}` | `llm_smart_delete` | `llm_smart` |

**关键**: `source` 是 EditDecision 的属性，AnalysisResult 没有 `source` 字段。区分 LLM 高光 vs 手动高光只能通过 **ID 前缀** (`llm_hl_` vs `manual_hl_`) 或通过 EditDecision 的 `analysis_id` 反查。

---

## Bug A / B: 前端调用传参错误

### 审计确认: **成立，无偏差**

**实际代码** `frontend/src/pages/WorkspacePage.vue:1270-1288`:

```typescript
// L1270-1272 — Bug B
async function handleRemoveHighlight(segmentId: string) {
  const res = await call("remove_highlight_segment", { segment_id: segmentId })
  //                                                  ^^^^^^^^^^^^^^^^^^^^^^^^ BUG
}

// L1281-1282 — Bug A
async function handleAddToHighlight(segmentId: string) {
  const res = await call("add_highlight_segment", { segment_id: segmentId })
  //                                              ^^^^^^^^^^^^^^^^^^^^^^^^ BUG
}
```

**Bridge 定义** `frontend/src/bridge.ts:57-68`:

```typescript
export async function call<T = unknown>(
  method: string,
  ...args: unknown[]    // <-- 可变位置参数，不做拆包
): Promise<ApiResponse<T>> {
  return api[method](...args)
}
```

**后端签名** `main.py:1397`:

```python
def add_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
```

**确认**: 传入 `{ segment_id: "xxx" }` 作为第一个位置参数 → `segment_id` = 整个对象 → `seg.id == segment_id` 永不成立。规范修复方案正确。

### 边界问题: 无额外遗漏

经检索，`add_highlight_segment` / `remove_highlight_segment` 仅有这两处调用点。其他 `call()` 调用（如 `start_highlight`、`detect_highlight_jump_cuts`）传参方式正确。

---

## Bug C: 重开项目后高光 UI 记录消失

### 审计确认: **成立，但修复方案不完整**

**实际代码确认**:

1. `useLlmTasks.ts:71` — `highlightResults = ref<HighlightResult[]>([])` 初始化为空
2. `useLlmTasks.ts:137-178` — 仅从 `llm:highlight_progress` / `llm:highlight_completed` 事件填充
3. `WorkspacePage.vue:407` — `analysisResults` computed 正确从 `activeTimeline.analysis.results` 读取
4. `WorkspacePage.vue:2075` — `:highlight-items="highlightResults"` 传给 HighlightModeView
5. `WorkspacePage.vue:472-497` — `onMounted` 无 hydration 逻辑
6. `WorkspacePage.vue:499-573` — `watch` 只在 waveform/proxy/path/name 变化时触发

**`detect_highlight_jump_cuts` 确认** (`main.py:2489-2496`):

```python
# P0-4: derive highlight ranges from AnalysisResult instead of timeline.edits
analysis_results = [r for r in timeline.analysis.results if r.type == "llm_highlight"]
```

后端正确从 `analysis.results` 读取，但前端仅在高光完成事件中调用它（`useLlmTasks.ts:171-177`）。重开项目时不会调用 → `jumpCuts` 为空。

### 规范修复方案的偏差

#### 偏差 1: 水合函数未过滤 `manual_highlight`

规范提出的 `hydrateHighlightResults`:

```typescript
const hlResults = (tl?.analysis?.results ?? [])
  .filter(r => r.type === "llm_highlight")
```

**问题**: `type === "llm_highlight"` 同时匹配 LLM 高光和手动高光。但手动高光的 `detail` 是 `"手动添加"`，LLM 高光的 `detail` 是 `highlight_reason`。当前水合后 `highlight_reason` 会是 `"手动添加"` 字符串，UI 显示不受影响，但语义不精确。

**推荐**: 通过 AnalysisResult ID 前缀区分来源 (`id.startsWith("llm_hl_")` / `id.startsWith("manual_hl_")`)。手动高光没有 `density` 概念，水合时用 `"medium"` 作为默认密度。

#### 偏差 2: 水合时 totalDuration 未计算

规范水合函数未设置 `highlightTotalDuration.value`。调用 `detect_highlight_jump_cuts` 时会返回 `total_highlight_duration`（`main.py:2508`），可复用。

#### 偏差 3: `_dt.now().timestamp()` 的精度问题

LLM 高光的 AnalysisResult ID 使用 `int(_dt.now().timestamp() * 1000)` 生成（`main.py:900`）。如果水合发生在高光完成事件的同一毫秒窗口内，新 ID 会与已有 ID 相同——但这在 rehydration 场景下不会发生（项目已持久化）。

### 推荐的水合实现

```typescript
function hydrateHighlightsFromProject(project: Project) {
  const tl = project.timelines.find(t => t.id === project.active_timeline_id)
  if (!tl) return

  const hlResults = (tl.analysis?.results ?? [])
    .filter(r => r.type === "llm_highlight")

  if (hlResults.length === 0) return

  highlightResults.value = hlResults.map(r => ({
    segment_id: r.segment_ids[0] ?? "",
    highlight_reason: r.detail ?? "",
    density: (
      r.confidence >= 0.9 ? "high" :
      r.confidence >= 0.5 ? "medium" : "low"
    ) as "high" | "medium" | "low",
  }))

  // Also fetch jump cuts + total duration from backend
  call<{ jump_cuts?: JumpCut[]; total_highlight_duration?: number }>(
    "detect_highlight_jump_cuts",
  ).then((res) => {
    if (res.success && res.data) {
      if (res.data.jump_cuts) jumpCuts.value = res.data.jump_cuts
      if (res.data.total_highlight_duration !== undefined)
        highlightTotalDuration.value = res.data.total_highlight_duration
    }
  })
}
```

### 调用时机

在 `WorkspacePage.vue` 的 `onMounted` 中，`loadVideoUrl()` 之后（确保 project 已加载）：

```typescript
// After loadVideoUrl() in onMounted
hydrateHighlightsFromProject(props.project)
```

---

## Bug D: 重跑高光不清理旧数据

### 审计确认: **成立，但规范中 `clear_highlight_results` 实现有 bug**

**实际代码确认**:

1. `core/project_service.py:1286-1287`:
   ```python
   existing_results = list(self.active_timeline.analysis.results)
   all_results = existing_results + analysis_results  # 纯追加
   ```

2. `useLlmTasks.ts:264-270`:
   ```typescript
   function resetHighlight() {
     highlightResults.value = []  // 仅清内存
     ...
   }
   ```

3. `main.py:910-913`:
   ```python
   if not task.payload.get("_workflow_accumulate"):
       store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_highlight"))
   ```

### 规范修复方案的两项偏差

#### 偏差 1 (严重): `clear_highlight_results` 的 `preserve_manual` 逻辑完全失效

规范代码:

```python
sources = {"manual_highlight"} if preserve_manual else set()
for r in tl.analysis.results:
    if r.type == "llm_highlight" and r.id.split("_")[0] not in sources:
        removed_ar_ids.add(r.id)
```

**问题分析**:

- `r.id = "llm_hl_1720234567890"` → `r.id.split("_")[0]` = `"llm"`
- `r.id = "manual_hl_a1b2c3d4e5f6"` → `r.id.split("_")[0]` = `"manual"`
- `sources = {"manual_highlight"}` — 永不匹配 `"llm"` 或 `"manual"`

**结果**: 所有高光 AnalysisResult 都被清除，包括手动添加的。`preserve_manual=True` 形同虚设。

**根因**: AnalysisResult **没有 `source` 字段**。区分来源只能通过 ID 前缀或通过 EditDecision 的 `analysis_id` 反查。

**正确实现**:

```python
def clear_highlight_results(self, preserve_manual: bool = True) -> dict:
    """Clear llm_highlight AnalysisResults and their EditDecisions.

    Args:
        preserve_manual: If True, keep manual_highlight entries (id starts with "manual_hl_").
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    tl = self.active_timeline

    # Find highlight AnalysisResult IDs to remove
    removed_ar_ids: set[str] = set()
    remaining_results: list = []
    for r in tl.analysis.results:
        if r.type == "llm_highlight":
            is_manual = r.id.startswith("manual_hl_")
            if preserve_manual and is_manual:
                remaining_results.append(r)
            else:
                removed_ar_ids.add(r.id)
        else:
            remaining_results.append(r)

    # Remove associated EditDecisions (those whose analysis_id matches)
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

#### 偏差 2: `_handle_highlight` 中 `_mark_dirty` 不包裹 `clear_highlight_results`

规范代码:

```python
if not task.payload.get("_workflow_accumulate"):
    self._project.clear_highlight_results()  # ← 无 _mark_dirty
    store = self._mark_dirty(
        self._project.add_analysis_results(...)
    )
```

**问题**: `clear_highlight_results` 自身会 mutate project state (`_update_active_timeline`)，但不触发 `PROJECT_DIRTY` 事件 → 前端不自动保存。虽然后续 `add_analysis_results` 会触发一次 `PROJECT_DIRTY`，但中间态缺少 save 信号。简洁方案：让 `clear_highlight_results` 内部不触发 save，调用处统一包裹；或让 `clear_highlight_results` 自身返回结果供 `_mark_dirty` 包装。

**推荐**: 将两步合并到一个 `_mark_dirty` 作用域内（如果 `clear_highlight_results` 返回 dict 则统一包装），或在 `main.py` 的 `_handle_highlight` 中连续调用两个 `_mark_dirty`。

---

## Bug E: llm_highlight action 错误设为 delete

### 审计确认: **成立，影响范围比规范所述更广**

**实际代码** `core/project_service.py:1314-1325`:

```python
new_edits.append(EditDecision(
    id=edit_id,
    start=start,
    end=end,
    action="delete",       # <-- 硬编码，所有 source 共用
    source=source,
    analysis_id=ar.id,
    ...
))
```

### 额外影响 1: `manual_highlight` 同样被误设为 `action="delete"`

`add_highlight_segment` (main.py:1430-1431) 调用:
```python
self._project.add_analysis_results([result], source="manual_highlight")
```

当前**同样**产生 `action="delete"` 的 EditDecision。规范 Bug E 修复后 (`action="keep"` if `source in highlight_sources`)，手动高光也会被正确设为 `keep`。

### 额外影响 2: `resolveSegmentState` 缺少 `manual_highlight` 过滤

`frontend/src/utils/segmentHelpers.ts:26`:

```typescript
const related = edits.filter(e =>
  (e.target_id === seg.id || isOverlapping(e, seg, 0.3)) && e.source !== "llm_highlight",
)
```

**现状分析**:
- **Bug E 修复前**: `manual_highlight` EditDecision 的 `action="delete"` → 被 `resolveSegmentState` 当作潜在删除建议 → `styleClass = "masked"` → Timeline 上手动高光的 segment 行会被红色遮罩
- **Bug E 修复后**: `action="keep"` → `styleClass = "kept"` → 显示为保留样式。虽非破坏性，但语义上高光条目不应参与 segment 状态解析

**推荐**: 将过滤条件扩展为：
```typescript
const HIGHLIGHT_SOURCES = new Set(["llm_highlight", "manual_highlight"])
const related = edits.filter(e =>
  (e.target_id === seg.id || isOverlapping(e, seg, 0.3)) && !HIGHLIGHT_SOURCES.has(e.source),
)
```

### 额外影响 3: `collect_confirmed_deleted_seg_ids` 潜在语义炸弹

`core/timeline_utils.py:16-23`:

```python
for edit in timeline.edits:
    if (
        edit.action == "delete"
        and edit.status == EditStatus.CONFIRMED
        ...
    ):
        result.add(edit.target_id)
```

如果高光 EditDecision 因任何原因被标记为 `confirmed`（目前 UI 无此路径，但可通过直接编辑 JSON 或未来功能触发），这些 segment 会被错误地排除在 LLM 分析输入之外（`_handle_highlight:851` 调用 `collect_confirmed_deleted_seg_ids`）。**Bug E 修复后自动消解**（action 变为 `keep`）。

### SuggestionPanel 统计数影响确认

`frontend/src/components/workspace/SuggestionPanel.vue:101-102`:

```typescript
const totalPending = computed(() => props.edits.filter(e => e.status === "pending" && e.action === "delete").length)
const totalAll = computed(() => props.edits.filter(e => e.action === "delete").length)
```

- **Bug E 修复前**: 高光 EditDecision (`action="delete"`) 被计入 → `totalPending` 和 `totalAll` 虚增
- **Bug E 修复后**: 高光 EditDecision (`action="keep"`) 不被计入 → 自动修正
- **Bug E 修复前 + source 过滤双重保险**: 即使未来有其他 `action="delete"` 的条目进入，source 过滤仍然生效

规范中 `SuggestionPanel.vue` 的 source 过滤修复是**防御性**的——在 Bug E 修复后并非必须，但作为双重保险是好的实践。

---

## Bug F: 删除建议组不清理 AnalysisResult + dirty_flags

### 审计确认: **成立，但 dirty_flags 清理 key 不存在于代码库**

**实际代码** `core/project_service.py:728-745`:

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    ids_set = set(edit_ids)
    updated_edits = [e for e in self.active_timeline.edits if e.id not in ids_set]
    # ... 仅更新 edits，不碰 analysis.results，不碰 segment dirty_flags
```

### dirty_flags 清理偏差

规范 `flag_map`:

```python
flag_map = {
    "llm_smart": "llm_smart_processed",
    "silence_detection": None,
    "llm_highlight": None,
}
```

**审计发现**: 代码库中**不存在** `"llm_smart_processed"` 这个 dirty_flag key。

代码库中实际存在的 dirty_flag key:

| Key | 设置位置 | 功能 |
|-----|---------|------|
| `text_edited` | `update_segment_text` | 手动编辑文本 |
| `merged` | `merge_segments` | 合并 segment |
| `split` | `split_segment` | 拆分 segment |
| `search_replaced` | `search_replace` | 搜索替换 |
| `llm_corrected` | `accept_correction` | P1 字幕修正已接受 |
| `llm_uncovered` | `rollback_corrections` | P1 字幕修正已回滚 |

**关键结论**: **smart-delete 不设置任何 dirty_flag**。删除建议组时 dirty_flags 清理对 `llm_smart` 来源是无操作。dirty_flags 清理仅对字幕修正（`llm_subtitle_correction`）有意义，但字幕修正在 `SuggestionPanel` 中由独立 review UI 管理，不通过 `delete_edit_decisions_batch` 删除。

**推荐**: 

**方案 A (保守)**: 从 `delete_edit_decisions_batch` 中移除 dirty_flags 清理逻辑（当前就是无操作），保持方法简洁。

**方案 B (前瞻)**: 保留 dirty_flags 清理框架，但基于实际存在的 key 修正：
```python
# dirty_flags 清理：仅字幕修正来源有 flag，smart-delete 无
KNOWN_ANALYSIS_FLAGS = {"llm_corrected", "llm_uncovered"}
for i, seg in enumerate(updated_segments):
    if seg.id in affected_seg_ids:
        new_flags = {k: v for k, v in seg.dirty_flags.items()
                     if k not in KNOWN_ANALYSIS_FLAGS}
        if new_flags != seg.dirty_flags:
            updated_segments[i] = seg.model_copy(update={"dirty_flags": new_flags})
```

**推荐方案 B**，因为代码库已存在 `llm_corrected` / `llm_uncovered` key，清理逻辑有实际意义（即使当前调用路径不触发），且为未来扩展留接口。

### 级联删除 AnalysisResult 的正确性

规范中 AnalysisResult 清理逻辑正确：通过 `analysis_id` 反查关联的 AnalysisResult。需要注意的是，多个 EditDecision 可能指向同一个 AnalysisResult（当前不会，但数据结构允许），使用 `set` 去重是安全的。

---

## Bug G: 删除高光不清理关联 EditDecision

### 审计确认: **成立，无偏差**

**实际代码** `main.py:1466-1469`:

```python
self._project._update_timeline_by_id(
    tl_id,
    analysis=timeline.analysis.model_copy(update={"results": remaining}),
)
# BUG: 只更新 analysis.results，不清理 edits
```

规范修复方案正确：同时清理 `edits` 中 `analysis_id` 在 `removed_ar_ids` 中的条目。

### 边界确认

`remove_highlight_segment` 清除 `segment_id` 出现在 **任意** `AnalysisResult.segment_ids` 中的条目。这意味如果一个手动高光和 LLM 高光都引用了同一个 `segment_id`，删除操作会清除两者。这是预期行为（删除该 segment 的所有高光标记），但应注意：如果 `preserve_manual` 参数被引入此方法（未来扩展），逻辑需相应调整。

---

## 规范遗漏问题

### 遗漏 1: `segmentHelpers.ts` 缺少 `manual_highlight` 过滤

已在 Bug E 额外影响 2 中详述。建议在 Bug E 修复时同步修改。

### 遗漏 2: `clear_highlight_results` 不应重复造轮子

代码库中已有正确的 "clear-then-add" 模式参考实现：`store_subtitle_corrections`（`project_service.py:1391-1395`）。该实现直接在同一方法内清理 + 新增，而非拆分为两个方法。`clear_highlight_results` 可借鉴此模式：

```python
# store_subtitle_corrections 模式：
kept_results = [r for r in tl.analysis.results if r.type != "llm_subtitle_correction"]
# ... append new results ...
all_results = kept_results + new_results
```

### 遗漏 3: Phase 4 屎山清理方法的 ID 前缀问题

规范 Phase 4 提出的 `cleanup_orphan_edits()` 和 `cleanup_duplicate_highlights()` 同样面临 AnalysisResult 无 `source` 字段的问题。清理逻辑依赖 `analysis_id` 关联查询，此方案不受 ID 前缀 bug 影响。

---

## 推荐实施计划（修订版）

### Phase 1: P0 紧急修复

| 任务 | 文件 | 描述 |
|------|------|------|
| P1.1 | `WorkspacePage.vue:1272,1282` | `handleRemoveHighlight` / `handleAddToHighlight` 传参改为字符串 |
| P1.2 | `segmentHelpers.ts:26` | `source !== "llm_highlight"` → `!HIGHLIGHT_SOURCES.has(e.source)` (含 `manual_highlight`) |

### Phase 2: 后端数据完整性

| 任务 | 文件 | 描述 |
|------|------|------|
| P2.1 | `project_service.py:1314-1325` | `add_analysis_results` 根据 source 决定 action (Bug E) |
| P2.2 | `project_service.py:728-745` | 扩展 `delete_edit_decisions_batch` 级联删除 AnalysisResult + dirty_flags (Bug F, 使用实际存在的 key) |
| P2.3 | `project_service.py` (新方法) | 新增 `clear_highlight_results`，使用 `startswith("manual_hl_")` 而非 `split("_")[0]` |
| P2.4 | `main.py:909-913` | `_handle_highlight` 先调用 `clear_highlight_results` 再写新结果 (Bug D) |
| P2.5 | `main.py:1466-1469` | `remove_highlight_segment` 同步清理关联 EditDecision (Bug G) |

### Phase 3: 前端数据水合 + UI

| 任务 | 文件 | 描述 |
|------|------|------|
| P3.1 | `useLlmTasks.ts` | 新增 `hydrateHighlightsFromProject(project)`（含 jumpCuts + totalDuration） |
| P3.2 | `WorkspacePage.vue:472` | `onMounted` 中调用 `hydrateHighlightsFromProject` (Bug C) |
| P3.3 | `WorkspacePage.vue` | 高光重跑前调用 `clear_highlight_results` 并弹窗确认 (Bug D 前端) |
| P3.4 | `SuggestionPanel.vue:101-102` | totalPending/totalAll 按 source 过滤（防御性双重保险） |

### Phase 4: 屎山数据清理

| 任务 | 文件 | 描述 |
|------|------|------|
| P4.1 | `project_service.py` | 新增 `cleanup_orphan_edits()` |
| P4.2 | `project_service.py` | 新增 `cleanup_duplicate_highlights()` |
| P4.3 | `main.py` 初始化 | 应用启动时自动执行一次清理 |

---

## 文件变动规则

### 修改文件清单

| 文件 | 修改项 | 只增不删 |
|------|--------|----------|
| `core/project_service.py` | `add_analysis_results` action 逻辑; `delete_edit_decisions_batch` 扩展; 新增 `clear_highlight_results`; 新增 `cleanup_orphan_edits`; 新增 `cleanup_duplicate_highlights` | 在现有方法后新增方法，不删除现有代码 |
| `main.py` | `_handle_highlight` 清理调用; `remove_highlight_segment` edits 同步; 启动清理 hook; 暴露 `clear_highlight_results` API | 在现有逻辑内插入清理步骤 |
| `frontend/src/composables/useLlmTasks.ts` | 新增 `hydrateHighlightsFromProject`; `resetHighlight` 可调用 `clear_highlight_results` | 新增导出函数 |
| `frontend/src/pages/WorkspacePage.vue` | 修复传参; `onMounted` 水合调用; 重跑弹窗 | 修改现有函数调用 |
| `frontend/src/components/workspace/SuggestionPanel.vue` | totalPending/totalAll 过滤 | 修改现有 computed |
| `frontend/src/utils/segmentHelpers.ts` | 扩展 `HIGHLIGHT_SOURCES` | 修改过滤条件 |

### 不变事项确认

| 项目 | 状态 | 说明 |
|------|------|------|
| `AnalysisResult` / `EditDecision` 数据模型 | 不变 | 无需新增字段，`source` 已在 EditDecision 中存在 |
| `resolveSegmentState` 核心逻辑 | 仅扩展过滤条件 | 从单值 `!== "llm_highlight"` 改为 Set 检查 |
| `_workflow_accumulate` 路径 | 不变 | 不在本次修复范围 |
| 测试约定 | 需新增 `test_highlight_segment.py` 测试用例 | 覆盖 `clear_highlight_results` + `remove_highlight_segment` edits 同步清理 |

---

## 测试影响

现有测试 `tests/test_highlight_segment.py` 的 `_ServiceStub.add_analysis_results` **不创建 EditDecision**（仅更新 `analysis.results`）。Bug E 修复后 `add_analysis_results` 创建的 EditDecision `action` 会从 `"delete"` 变为 `"keep"`（对 `llm_highlight` / `manual_highlight` source）。

需要在以下测试场景新增断言：
1. `clear_highlight_results` (新方法) — 清 LLM 高光保留手动高光的单元测试
2. `remove_highlight_segment` — 验证 `edits` 同步清理的集成测试
3. `delete_edit_decisions_batch` — 验证 AnalysisResult 级联删除

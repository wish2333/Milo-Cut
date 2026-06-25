# Audit Report -- v2.1.1 Spec-8 高光提取功能 Bug 诊断审计

> **审计日期**: 2026-06-26
> **审计范围**: `docs/2.1.1/spec-2.1.1-8.md` 所列 Bug A ~ G（7 项缺陷）
> **审计方式**: 直接读取当前代码库，逐项核对规范所述行号、根因、影响范围，并审查推荐修复方案的代码正确性
> **审计结论**: 7 项 Bug 全部确认成立，但推荐方案中存在 **3 处代码级缺陷** 和 **2 处边界遗漏**，需在实施前修正

---

## 总览确认表

| ID | 严重性 | 规范判定 | 审计结论 | 偏差说明 |
|----|--------|----------|----------|----------|
| A | P0 | 前端传参错误 | **确认成立**，根因准确 | 规范修复方案正确，无偏差 |
| B | P0 | 前端传参错误 | **确认成立**，根因准确 | 同 Bug A |
| C | P1 | 高光 UI 不水合持久化数据 | **确认成立**，且影响**比规范所述更广** | 规范未提及 `jumpCuts` 水合时也需重算 `highlightTotalDuration` |
| D | P1 | 重跑不清理旧数据 | **确认成立**，但推荐方案 `clear_highlight_results` **有严重 bug** | `r.id.split("_")[0]` 逻辑错误导致 `preserve_manual` 完全失效 |
| E | P1 | action 硬编码 delete | **确认成立**，且**有下游语义炸弹** | 规范未发现 `collect_confirmed_deleted_seg_ids` 的潜在误收风险 |
| F | P1 | 删除建议组不级联清理 | **确认成立**，但推荐方案 **dirty_flags 清理逻辑有误** | `flag_map` 引用了不存在的 `llm_smart_processed` key |
| G | P2 | 删除高光不清理 EditDecision | **确认成立**，根因准确 | 规范修复方案基本正确，但缺 `_mark_dirty` 时序说明 |
| 新增-1 | P1 | **规范遗漏** | `resolveSegmentState` 未过滤 `manual_highlight` | 手动高光 segment 被误显示为 "masked"（删除遮罩） |
| 新增-2 | P1 | **规范遗漏** | `clear_highlight_results` 的 `preserve_manual` 逻辑 bug | 规范推荐代码自身有 bug，详见 Bug D 审计 |
| 新增-3 | P2 | **规范遗漏** | `collect_confirmed_deleted_seg_ids` 语义炸弹 | 高光 EditDecision 的 `action="delete"` 可导致高光 segment 被误判为"已确认删除" |

下面逐项展开。

---

## Bug A / B: 前端调用传参错误 (P0)

### 审计结论：确认成立，根因准确，修复方案正确

### 当前代码与上下文

**规范所述文件**: `frontend/src/pages/WorkspacePage.vue:1270-1288`

**审计实际读取** -- `WorkspacePage.vue:1270-1288`：

```typescript
// line 1270 -- Bug B
async function handleRemoveHighlight(segmentId: string) {
  if (!window.confirm("确认移除此精华片段？")) return
  const res = await call("remove_highlight_segment", { segment_id: segmentId })
  //                                                  ^^^^^^^^^^^^^^^^^^^^^^^^ BUG
  // ...
}

// line 1281 -- Bug A
async function handleAddToHighlight(segmentId: string) {
  const res = await call("add_highlight_segment", { segment_id: segmentId })
  //                                            ^^^^^^^^^^^^^^^^^^^^^^^^ BUG
  // ...
}
```

行号**完全准确**。

### 根因验证

**`frontend/src/bridge.ts:57-69`** -- `call()` 签名：

```typescript
export async function call<T = unknown>(
  method: string,
  ...args: unknown[]          // 可变位置参数，不是 options 对象
): Promise<ApiResponse<T>> {
  // ...
  return withTimeout(
    api[method](...args) as Promise<ApiResponse<T>>,
    30_000,
  )
}
```

`call()` 使用 spread positional args (`...args: unknown[]`)。前端调用 `call("add_highlight_segment", { segment_id: segmentId })` 时，`{ segment_id: segmentId }` 整个对象被作为**第一个位置参数**传入。

**`main.py:1397`** -- 后端方法签名：

```python
@expose
def add_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
```

后端期望 `segment_id` 是字符串。前端传了 `{"segment_id": "xxx"}`，Python 端收到的 `segment_id` 参数值是整个 dict 而非字符串。

**`main.py:1417-1419`** -- 匹配逻辑：

```python
seg = next((s for s in timeline.transcript.segments if s.id == segment_id), None)
if seg is None or seg.type != "subtitle":
    return {"success": False, "error": f"Segment {segment_id} not found or not a subtitle"}
```

`seg.id`（字符串 `"s1"`）永远不等于 `segment_id`（dict `{"segment_id": "s1"}`）→ 永远返回错误。

`remove_highlight_segment`（`main.py:1440`）同理：`segment_id in r.segment_ids` 中 `segment_id` 是 dict，`r.segment_ids` 是 `list[str]`，永远不匹配。

### 推荐修复方案

规范推荐的修复方案**正确**：

```typescript
// fix A (line 1282)
const res = await call("add_highlight_segment", segmentId)

// fix B (line 1272)
const res = await call("remove_highlight_segment", segmentId)
```

### 影响边界

- **仅影响手动高光操作**：Timeline 右键「加入精华」和侧边栏右键「删除高光」
- **不影响 LLM 自动高光提取**：`startHighlight`（`useLlmTasks.ts:278`）使用 `call("start_highlight", targetMinutes)` 传参正确
- **阻断性**：用户完全无法手动添加/删除高光片段，每次操作必报错

---

## Bug C: 重开项目后高光 UI 记录消失 (P1)

### 审计结论：确认成立，但规范水合方案不完整（遗漏 `highlightTotalDuration` 重算）

### 当前代码与上下文

数据流分两层：

**层 1 -- 持久化层（正确）**：高光数据以 `AnalysisResult(type="llm_highlight")` 形式存储在 `timeline.analysis.results` 中。

- `_handle_highlight`（`main.py:898-908`）生成 AnalysisResult dict，通过 `add_analysis_results` 持久化
- `add_highlight_segment`（`main.py:1422-1428`）同样通过 `add_analysis_results` 持久化手动高光

**层 2 -- 前端状态层（有缺陷）**：

**`frontend/src/composables/useLlmTasks.ts:71-74`** -- 纯内存状态：

```typescript
const highlightResults = ref<HighlightResult[]>([])
const highlightTotalDuration = ref(0)
const highlightTargetDuration = ref(600) // 10 min default
const jumpCuts = ref<JumpCut[]>([])
```

这些 ref 是**模块级单例**（`useLlmTasks.ts:65` 注释明确标注 "Singleton state shared across all useLlmTasks() callers"），仅在以下事件中填充：

**`useLlmTasks.ts:137-178`** -- 仅事件驱动：

| 事件 | 填充内容 |
|------|----------|
| `llm:highlight_progress` (L137) | 增量 upsert 到 `highlightResults` |
| `llm:highlight_completed` (L159) | 全量替换 `highlightResults`、设 `highlightTotalDuration`、`highlightTargetDuration`，触发 `detect_highlight_jump_cuts` |

**`WorkspacePage.vue:2075-2078`** -- HighlightModeView 消费单例状态：

```html
:highlight-items="highlightResults"
:highlight-total-duration="highlightTotalDuration"
:highlight-target-duration="highlightTargetDuration"
:jump-cuts="jumpCuts"
```

### 根因验证

`WorkspacePage.vue` 中有 **3 个** `onMounted` 钩子（L472、L1297、L1539），其中 L472 的 `onMounted` 做了视频加载和延迟配置加载，**但没有任何地方从 `props.project` 水合 `highlightResults`**。

同时，`WorkspacePage.vue` 有多个 `watch`（L499 波形、L567 代理路径、L570 原始路径、L573 项目名清历史），**但没有任何 `watch(() => props.project, ...)` 来水合高光数据**。

因此：重开项目时 `llm:highlight_*` 事件不触发 → 单例 ref 保持空数组 → HighlightModeView 显示「暂无高光片段」。

### 规范推荐水合方案审查

规范提议在 WorkspacePage 中新增 `hydrateHighlightResults(project)` 函数：

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
    // also compute total duration from segments  ← 注释占位，无实现
  }
}
```

**审计发现此方案有 3 处不完整**：

1. **`highlightTotalDuration` 未重算**：注释 `// also compute total duration from segments` 只是占位，没有实际实现。重开后 `highlightTotalDuration` 保持 0，导致进度条显示错误。

2. **`jumpCuts` 未重算**：规范在「补充」节提到应调用 `detect_highlight_jump_cuts`，但未将其纳入 `hydrateHighlightResults` 函数体。

3. **density 映射不对称**：存储时 `confidence = 1.0 if density == "high" else 0.7`（`main.py:903`），即 `medium`/`low` 都映射为 0.7。水合时 `r.confidence >= 0.9 ? "high" : r.confidence >= 0.5 ? "medium" : "low"` 会把 0.7 全部映射回 `"medium"`，**`low` 永远无法恢复**。

### 推荐修复方案（修正版）

```typescript
// useLlmTasks.ts -- 新增水合函数
async function hydrateHighlightsFromProject(project: Project): Promise<void> {
  const tl = project.timelines.find(t => t.id === project.active_timeline_id)
  if (!tl) return

  const hlResults = (tl.analysis?.results ?? [])
    .filter(r => r.type === "llm_highlight")

  if (hlResults.length === 0) {
    highlightResults.value = []
    highlightTotalDuration.value = 0
    jumpCuts.value = []
    return
  }

  // 水合 highlightResults
  highlightResults.value = hlResults.flatMap(r =>
    r.segment_ids.map(sid => ({
      segment_id: sid,
      highlight_reason: r.detail ?? "",
      // confidence 1.0 → high, 0.7 → medium（与存储逻辑对称）
      density: (r.confidence >= 0.9 ? "high" : "medium") as "high" | "medium" | "low",
    }))
  )

  // 重算 totalDuration（从 segments 时间范围求和）
  const segMap = new Map((tl.transcript?.segments ?? []).map(s => [s.id, s]))
  highlightTotalDuration.value = hlResults.reduce((sum, r) => {
    const segs = r.segment_ids.filter(sid => segMap.has(sid)).map(sid => segMap.get(sid)!)
    if (segs.length === 0) return sum
    return sum + (Math.max(...segs.map(s => s.end)) - Math.min(...segs.map(s => s.start)))
  }, 0)

  // 重算 jumpCuts（调用后端 API）
  const jcRes = await call<{ jump_cuts?: JumpCut[]; highlight_count?: number }>(
    "detect_highlight_jump_cuts",
  )
  if (jcRes.success && jcRes.data?.jump_cuts) {
    jumpCuts.value = jcRes.data.jump_cuts
  }
}

// WorkspacePage.vue -- 在 project 加载时调用
watch(() => props.project, (newProject) => {
  hydrateHighlightsFromProject(newProject)
}, { immediate: true })
```

**关于 `highlightTargetDuration`**：该值不在持久化数据中（仅存在于运行时事件），无法从 project 水合。建议保持默认值 600 或新增持久化字段。

---

## Bug D: 重跑高光不清理旧数据 (P1)

### 审计结论：确认成立，但规范推荐的 `clear_highlight_results` 方法**有严重 bug**，会导致手动高光被误删

### 当前代码与上下文

**`core/project_service.py:1280-1335`** -- `add_analysis_results` 纯追加模式：

```python
def add_analysis_results(self, results: list[dict], source: str) -> dict:
    # ...
    analysis_results = [AnalysisResult.model_validate(r) for r in results]
    existing_results = list(self.active_timeline.analysis.results)
    all_results = existing_results + analysis_results    # ← 纯追加，不清理
    # ...
    self._update_active_timeline(
        analysis=self.active_timeline.analysis.model_copy(update={
            "results": all_results,                      # ← 旧 + 新叠加
            "last_run": datetime.now().isoformat(),
        }),
        edits=existing_edits + new_edits,                # ← 旧 + 新叠加
    )
```

**`main.py:909-913`** -- `_handle_highlight` 调用链：

```python
if not task.payload.get("_workflow_accumulate"):
    store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_highlight"))
```

每次重跑高光，`add_analysis_results` 将新的 `llm_highlight` AnalysisResult + EditDecision **追加**到已有列表上，不清理旧数据。

**`frontend/src/composables/useLlmTasks.ts:264-270`** -- `resetHighlight` 仅清前端内存：

```typescript
function resetHighlight() {
  highlightResults.value = []
  highlightTotalDuration.value = 0
  jumpCuts.value = []
  progress.value = 0
  errorMsg.value = null
}
```

`resetHighlight` 在 `startHighlight`（L276）中被调用，仅清空前端 ref，**不调用任何后端清理 API**。

### 根因验证：确认

叠加问题确实存在。假设第一次提取得到 5 个高光，第二次提取得到 3 个（完全不同的 segment），持久化数据中会有 8 条 AnalysisResult + 8 条 EditDecision。

### 规范推荐 `clear_highlight_results` 方法审查 -- 发现严重 bug

规范推荐代码（`spec-2.1.1-8.md:137-171`）：

```python
def clear_highlight_results(self, preserve_manual: bool = True) -> dict:
    sources = {"manual_highlight"} if preserve_manual else set()
    tl = self.active_timeline

    removed_ar_ids: set[str] = set()
    remaining_results = []
    for r in tl.analysis.results:
        if r.type == "llm_highlight" and r.id.split("_")[0] not in sources:
            #                                    ^^^^^^^^^^^^^^^^^^^^^^^^
            #                                    BUG: split 逻辑错误
            removed_ar_ids.add(r.id)
        else:
            remaining_results.append(r)
    # ...
```

**Bug 分析**：

AnalysisResult 的 ID 生成规则：
- LLM 高光：`f"llm_hl_{timestamp}"`（`main.py:900`）→ `split("_")` → `["llm", "hl", "1234567890"]` → `[0]` = `"llm"`
- 手动高光：`f"manual_hl_{uuid}"`（`main.py:1423`）→ `split("_")` → `["manual", "hl", "abc123def456"]` → `[0]` = `"manual"`

但 `sources` 集合是 `{"manual_highlight"}`（完整 source 名）。

- `"llm" not in {"manual_highlight"}` → `True` → LLM 高光被清除（正确）
- `"manual" not in {"manual_highlight"}` → **`True`** → **手动高光也被清除**（错误！`preserve_manual` 完全失效）

`split("_")[0]` 只取第一个下划线前的部分（`"manual"`），永远不可能匹配 `"manual_highlight"`。

### 推荐修复方案（修正版）

利用 AnalysisResult 的 `type` 字段和关联 EditDecision 的 `source` 字段来区分，而非 ID split：

```python
def clear_highlight_results(self, preserve_manual: bool = True) -> dict:
    """Clear llm_highlight AnalysisResults and their associated EditDecisions.

    Args:
        preserve_manual: If True, keep manual_highlight entries (source field
            on EditDecision, not AnalysisResult which has no source field).
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    tl = self.active_timeline

    # AnalysisResult 没有 source 字段，需通过关联 EditDecision 的 source 判断。
    # 先收集 manual 的 analysis_id 集合（用于保留）。
    manual_ar_ids: set[str] = set()
    if preserve_manual:
        for e in tl.edits:
            if e.source == "manual_highlight" and e.analysis_id:
                manual_ar_ids.add(e.analysis_id)

    # 分类 AnalysisResults：所有 type=llm_highlight 的都要检查
    removed_ar_ids: set[str] = set()
    remaining_results = []
    for r in tl.analysis.results:
        if r.type == "llm_highlight" and r.id not in manual_ar_ids:
            removed_ar_ids.add(r.id)
        else:
            remaining_results.append(r)

    # 清理关联的 EditDecision
    remaining_edits = [
        e for e in tl.edits
        if e.analysis_id not in removed_ar_ids
    ]

    self._update_active_timeline(
        analysis=tl.analysis.model_copy(update={"results": remaining_results}),
        edits=remaining_edits,
    )

    cleared = len(tl.analysis.results) - len(remaining_results)
    logger.info("Cleared %d highlight results (preserved %d manual)", cleared, len(manual_ar_ids))
    return {"success": True, "data": {"cleared": cleared}}
```

### `_handle_highlight` 修改审查 -- 发现时序问题

规范推荐代码（`spec-2.1.1-8.md:178-184`）：

```python
if not task.payload.get("_workflow_accumulate"):
    # Clear old highlight results before adding new ones
    self._project.clear_highlight_results()
    store = self._mark_dirty(
        self._project.add_analysis_results(analysis_results, source="llm_highlight")
    )
```

**问题**：`clear_highlight_results()` 内部已调用 `_update_active_timeline` 修改了 `self._current`，但没有调用 `_mark_dirty`（不发 `project:dirty` 事件）。这本身无害（紧接着 `add_analysis_results` 会被 `_mark_dirty` 包裹），但如果 `add_analysis_results` 因某种原因失败（如 segment 不存在），clear 操作已经执行且不会触发 auto-save，导致数据丢失但未持久化。

**修正**：将 clear + add 合并为一个原子操作，或确保 clear 失败时回滚。推荐方案：在 `add_analysis_results` 内部增加 `clear_existing` 参数，使清理和追加在同一个 `_update_active_timeline` 调用中完成：

```python
def add_analysis_results(
    self, results: list[dict], source: str, clear_existing: bool = False
) -> dict:
    """Store AnalysisResult entries and create EditDecisions from time ranges.

    Args:
        clear_existing: If True, remove existing results of the same type
            before adding new ones (used by highlight re-run).
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    analysis_results = [AnalysisResult.model_validate(r) for r in results]

    if clear_existing:
        # 清理同类型旧数据 + 关联 EditDecision
        existing_results = [
            r for r in self.active_timeline.analysis.results
            if r.type != analysis_results[0].type if analysis_results else True
        ]
        cleared_ar_ids = {
            r.id for r in self.active_timeline.analysis.results
            if r not in existing_results
        }
        existing_edits = [
            e for e in self.active_timeline.edits
            if e.analysis_id not in cleared_ar_ids
        ]
    else:
        existing_results = list(self.active_timeline.analysis.results)
        existing_edits = list(self.active_timeline.edits)

    all_results = existing_results + analysis_results
    # ... 后续逻辑不变
```

然后在 `_handle_highlight` 中：

```python
if not task.payload.get("_workflow_accumulate"):
    store = self._mark_dirty(
        self._project.add_analysis_results(
            analysis_results, source="llm_highlight", clear_existing=True
        )
    )
```

此方案**不需要单独的 `clear_highlight_results` 方法**，且清理 + 追加在单个 `_update_active_timeline` 中原子完成。

---

## Bug E: llm_highlight action 错误设为 delete (P1)

### 审计结论：确认成立，规范修复方案正确，但规范**遗漏了下游语义炸弹**

### 当前代码与上下文

**`core/project_service.py:1314-1325`** -- `add_analysis_results` 创建 EditDecision：

```python
new_edits.append(EditDecision(
    id=edit_id,
    start=start,
    end=end,
    action="delete",       # ← 硬编码，对所有 source 生效
    source=source,         # source 可能是 "llm_highlight" 或 "manual_highlight"
    analysis_id=ar.id,
    status=EditStatus.PENDING,
    priority=100,
    target_type="segment",
    target_id=ar.segment_ids[0],
))
```

`action` 字段硬编码为 `"delete"`，无论 `source` 是 `"llm_smart"`（删除建议）、`"llm_highlight"`（LLM 高光）还是 `"manual_highlight"`（手动高光）。

### 数据模型验证

**`core/models.py:99-103`**：

```python
class EditDecision(BaseModel, frozen=True):
    # ...
    action: Literal["delete", "keep"] = "delete"
    source: str = ""
```

`action` 合法值为 `"delete"` 和 `"keep"`，规范推荐改为 `"keep"` 是合法的。

### 连锁影响验证

#### 影响 1：SuggestionPanel 统计数虚增 -- **确认**

**`SuggestionPanel.vue:101-102`**：

```typescript
const totalPending = computed(() => props.edits.filter(e => e.status === "pending" && e.action === "delete").length)
const totalAll = computed(() => props.edits.filter(e => e.action === "delete").length)
```

两个 computed **只过滤 `action === "delete"`，不过滤 `source`**。由于 Bug E，所有高光 EditDecision 的 `action="delete"` 且 `status="pending"`，会被计入 `totalPending` 和 `totalAll`。

例如：用户提取了 10 个高光 → SuggestionPanel 头部显示「共 10 处建议 | 10 处待处理」，但实际高光条目不显示在 groups 列表中（groups 按 `source === "silence_detection"` / `source === "llm_smart"` 过滤，L65-70），用户看到的建议数为虚高数字。

#### 影响 2：`collect_confirmed_deleted_seg_ids` 语义炸弹 -- **规范遗漏，审计新发现**

**`core/timeline_utils.py:8-24`**：

```python
def collect_confirmed_deleted_seg_ids(timeline: Timeline) -> set[str]:
    """Return segment IDs targeted by confirmed delete decisions."""
    result: set[str] = set()
    for edit in timeline.edits:
        if (
            edit.action == "delete"               # ← 高光的 action 也是 "delete"
            and edit.status == EditStatus.CONFIRMED
            and edit.target_type == "segment"
            and edit.target_id
        ):
            result.add(edit.target_id)
    return result
```

此函数在 `_handle_highlight`（`main.py:851`）和 `_handle_smart_delete`（类似位置）中被调用，用于**过滤掉已确认删除的 segment**，使其不参与后续 LLM 分析。

**当前影响有限**：高光 EditDecision 的初始 `status="pending"`，不会被此函数收集。但如果用户通过任何路径将高光 EditDecision 的 status 改为 `confirmed`（例如批量操作误命中、或未来 UI 变更），高光 segment 会被错误地标记为"已确认删除"，从后续分析输入中被排除。

**这是语义炸弹**：Bug E 修复后（`action="keep"`），即使 status 被误改为 confirmed，`action == "delete"` 过滤也会排除高光，消除此风险。

### 推荐修复方案

规范推荐方案**正确**，根据 `source` 决定 action：

```python
# In add_analysis_results (project_service.py:1314-1325):
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

### 修复后的连锁效应

Bug E 修复后（高光 `action="keep"`）：

| 消费者 | 修复前 | 修复后 | 是否需额外处理 |
|--------|--------|--------|----------------|
| `SuggestionPanel.totalPending/totalAll` | 高光计入统计（虚增） | 高光 `action="keep"` 不再匹配 `=== "delete"`（自动排除） | **自动修复**（但建议同步加 source 过滤作为 defense-in-depth） |
| `collect_confirmed_deleted_seg_ids` | 语义炸弹（如 status 误改则误收） | `action="keep"` 永不匹配 `action == "delete"`（消除炸弹） | **自动修复** |
| `resolveSegmentState` (segmentHelpers.ts:26) | 已过滤 `source !== "llm_highlight"` | 修复后 `action="keep"` 走 `"kept"` 分支（L50），但 source 过滤已排除 | **无变化**（但 `manual_highlight` 未过滤，见新增-1） |
| `export_service.py:510` 旧格式兼容 | 高光 `action="delete"` 不匹配 `action == "keep"` | 高光 `action="keep"` 匹配，但走新路径（AnalysisResult） | **无影响**（新路径不读 action） |

---

## Bug F: 删除建议组不清理 AnalysisResult + dirty_flags (P1)

### 审计结论：确认成立，但规范推荐的 `delete_edit_decisions_batch` 扩展代码中 **dirty_flags 清理逻辑有误**

### 当前代码与上下文

**`core/project_service.py:728-745`** -- `delete_edit_decisions_batch` 仅操作 edits：

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    """Permanently remove edit decisions by id."""
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    ids_set = set(edit_ids)
    updated_edits = [e for e in self.active_timeline.edits if e.id not in ids_set]
    removed = len(self.active_timeline.edits) - len(updated_edits)
    if removed == 0:
        return {"success": False, "error": "No matching edit decisions found"}

    self._update_active_timeline(edits=updated_edits)     # ← 仅更新 edits
    logger.info("Permanently deleted {} edit decisions", removed)
    return {"success": True, "data": self._current.model_dump()}
```

EditDecision 被删除后，其关联的 `AnalysisResult` 和受影响 segment 的 `dirty_flags` 均不清理，导致：

1. **孤儿 AnalysisResult**：`analysis.results` 中保留了已删除 EditDecision 的来源记录
2. **脏 dirty_flags**：segment 上的 `llm_corrected`/`llm_uncovered` 等标记残留，阻止后续重新分析

### dirty_flags 实际 key 调查 -- 发现规范错误

规范推荐代码（`spec-2.1.1-8.md:320-332`）中的 `flag_map` 和清理逻辑：

```python
flag_map = {
    "llm_smart": "llm_smart_processed",        # ← 不存在的 key
    "silence_detection": None,
    "llm_highlight": None,
}

for key in ("llm_smart_processed", "llm_corrected", "llm_uncovered"):
    new_flags.pop(key, None)
```

**审计实际搜索 `project_service.py` 中所有 dirty_flags 赋值**：

| 代码位置 | dirty_flags key | 设置场景 |
|----------|-----------------|----------|
| `L808` | `"text_edited"` | 用户手动编辑 segment 文本 |
| `L951` | `"merged"` | segment 合并 |
| `L996, L1002` | `"split"` | segment 拆分 |
| `L1107` | `"search_replaced"` | 搜索替换 |
| `L1523, L1736` | `"llm_corrected"` | P1 字幕修正：修正被接受 |
| `L1759` | `"llm_uncovered"` | P1 字幕修正：uncovered 标记 |

**代码库中不存在 `"llm_smart_processed"` 这个 key**。规范中 `flag_map["llm_smart"] = "llm_smart_processed"` 引用了不存在的映射。

实际上，`llm_smart`（P0 智能删除）**不设置任何 dirty_flags**——它通过 `timeline.edits` 中的 EditDecision（status=pending/confirmed/rejected）来标记处理状态，不在 segment 上设 flag。

### 推荐修复方案（修正版）

`delete_edit_decisions_batch` 的级联删除应**精确清理实际存在的 dirty_flags**：

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    """Permanently remove edit decisions and associated data by id.

    Cascading cleanup:
    1. Remove EditDecision entries from timeline.edits
    2. Remove associated AnalysisResult entries from timeline.analysis.results
    3. Clear dirty_flags on affected segments (only correction-related flags)
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    ids_set = set(edit_ids)
    tl = self.active_timeline

    # 1. Find edits to remove + collect their analysis_ids and target segment_ids
    removed_analysis_ids: set[str] = set()
    affected_seg_ids: set[str] = set()
    for e in tl.edits:
        if e.id in ids_set:
            if e.analysis_id:
                removed_analysis_ids.add(e.analysis_id)
            if e.target_id:
                affected_seg_ids.add(e.target_id)

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
    #    Only clear correction-related flags that are tied to AnalysisResult
    #    lifecycle. Leave user-edit flags (text_edited, merged, split,
    #    search_replaced) untouched -- those are independent of edit decisions.
    CORRECTION_FLAGS = ("llm_corrected", "llm_uncovered")
    updated_segments = list(tl.transcript.segments)
    cleaned_count = 0
    for i, seg in enumerate(updated_segments):
        if seg.id in affected_seg_ids:
            # Only remove if the flag exists
            flags_to_remove = [k for k in CORRECTION_FLAGS if k in seg.dirty_flags]
            if flags_to_remove:
                new_flags = {k: v for k, v in seg.dirty_flags.items()
                             if k not in CORRECTION_FLAGS}
                updated_segments[i] = seg.model_copy(update={"dirty_flags": new_flags})
                cleaned_count += 1

    self._update_active_timeline(
        edits=updated_edits,
        analysis=tl.analysis.model_copy(update={"results": updated_results}),
        transcript=tl.transcript.model_copy(update={"segments": updated_segments}),
    )

    logger.info(
        "Permanently deleted %d edits + %d analysis results + cleaned %d segments",
        removed,
        len(tl.analysis.results) - len(updated_results),
        cleaned_count,
    )
    return {"success": True, "data": self._current.model_dump()}
```

### SuggestionPanel source 过滤审查 -- 确认正确

规范推荐（`spec-2.1.1-8.md:356-370`）对 `totalPending`/`totalAll` 增加 source 过滤：

```typescript
const SUGGESTION_SOURCES = new Set(["silence_detection", "llm_smart", "llm_smart_delete"])

const totalPending = computed(() =>
  props.edits.filter(e =>
    e.status === "pending" &&
    e.action === "delete" &&
    SUGGESTION_SOURCES.has(e.source)
  ).length
)
```

**审计确认**：当前 `groups` computed（`SuggestionPanel.vue:65-70`）已按 `source === "silence_detection"` 和 `source === "llm_smart"` 过滤。增加 source 过滤到 `totalPending`/`totalAll` 是正确的 defense-in-depth，即使 Bug E 修复后 `action="keep"` 已自动排除高光，source 过滤仍提供了额外的安全边界。

**修正**：`SUGGESTION_SOURCES` 应与 `groups` computed 的实际过滤逻辑一致。当前 `groups` 中 smart-delete 的 source 是 `"llm_smart"`（L70），`"llm_smart_delete"` 是 `AnalysisResult.type` 而非 `EditDecision.source`。因此：

```typescript
// 与 groups computed 的过滤逻辑保持一致
const SUGGESTION_SOURCES = new Set(["silence_detection", "llm_smart"])
```

---

## Bug G: 删除高光不清理关联 EditDecision (P2)

### 审计结论：确认成立，规范修复方案基本正确，但有一个 `_mark_dirty` 时序细节需注意

### 当前代码与上下文

**`main.py:1440-1472`** -- `remove_highlight_segment` 仅操作 `analysis.results`：

```python
@expose
def remove_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
    # ...
    results = timeline.analysis.results
    removed = [r for r in results if segment_id in r.segment_ids]
    if not removed:
        return {"success": False, "error": f"No highlight found for segment {segment_id}"}

    remaining = [r for r in results if segment_id not in r.segment_ids]
    self._project._update_timeline_by_id(
        tl_id,
        analysis=timeline.analysis.model_copy(update={"results": remaining}),
        # ↑ 只更新 analysis，不清理 edits 中的关联 EditDecision
    )
    self._mark_dirty({"success": True})

    return {"success": True, "data": {"removed_count": len(removed)}}
```

### 根因验证

`add_highlight_segment`（`main.py:1430-1431`）通过 `add_analysis_results` **同时写入** `analysis.results`（AnalysisResult）和 `edits`（EditDecision）。但 `remove_highlight_segment` 删除时**只清理 analysis.results**，不同步清理 `edits`。

### 孤儿 EditDecision 影响

删除高光后，`edits` 中残留的孤儿 EditDecision：

```json
{
  "id": "edit-manual_hl_abc123",
  "source": "manual_highlight",
  "analysis_id": "manual_hl_abc123",    // ← 对应的 AnalysisResult 已被删除
  "action": "delete",                    // ← Bug E 未修复时的值
  "status": "pending",
  "target_id": "s1"
}
```

下游影响：
- `resolveSegmentState`（segmentHelpers.ts:26）过滤了 `source !== "llm_highlight"`，但**未过滤 `manual_highlight`** → 孤儿 manual_highlight EditDecision 仍参与 segment 状态计算（见新增-1）
- `collect_confirmed_deleted_seg_ids` 不过滤 source，仅看 `action == "delete"` → 孤儿 EditDecision 如被误改 status 则有语义风险

### 规范推荐修复方案审查

规范推荐代码（`spec-2.1.1-8.md:406-438`）：

```python
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
```

**审计确认**：此方案逻辑正确。通过 `removed_ar_ids` 收集被删除 AnalysisResult 的 ID，然后过滤 `edits` 中 `analysis_id` 匹配的 EditDecision，在同一个 `_update_timeline_by_id` 调用中原子更新。

**`_mark_dirty` 时序细节**：`_mark_dirty`（`main.py:121-130`）仅检查 `result.get("success")` 并发 `project:dirty` 事件。当前代码 `self._mark_dirty({"success": True})` 在 `_update_timeline_by_id` 之后调用是正确的——`_update_timeline_by_id` 修改 `self._current` 后，`_mark_dirty` 触发 auto-save 持久化最新状态。

### 推荐修复方案

采用规范方案，增加日志和防御性检查：

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

    # 同步清理关联 EditDecision（Bug G 修复）
    remaining_edits = [
        e for e in timeline.edits
        if e.analysis_id not in removed_ar_ids
    ]
    removed_edit_count = len(timeline.edits) - len(remaining_edits)

    self._project._update_timeline_by_id(
        tl_id,
        analysis=timeline.analysis.model_copy(update={"results": remaining}),
        edits=remaining_edits,
    )
    self._mark_dirty({"success": True})

    logger.info(
        "Removed highlight for segment %s: %d results + %d edits",
        segment_id, len(removed), removed_edit_count,
    )
    return {"success": True, "data": {"removed_count": len(removed)}}
```

---

## 新增发现：规范遗漏的 3 项缺陷

### 新增-1 (P1): `resolveSegmentState` 未过滤 `manual_highlight`

**位置**：`frontend/src/utils/segmentHelpers.ts:25-27`

```typescript
const related = edits.filter(e =>
  (e.target_id === seg.id || isOverlapping(e, seg, 0.3)) && e.source !== "llm_highlight",
  //                                                                              ^^^^^^^^^^^^^^^^^^
  //                                                                              只过滤 llm_highlight
  //                                                                              未过滤 manual_highlight
)
```

**问题**：`add_highlight_segment`（`main.py:1431`）创建的 EditDecision 的 `source="manual_highlight"`。`resolveSegmentState` 只排除了 `source !== "llm_highlight"`，**没有排除 `manual_highlight`**。

**当前影响**（Bug E 未修复时）：手动高光的 EditDecision 有 `action="delete"` + `status="pending"`。当 `resolveSegmentState` 计算该 segment 的显示状态时：
- `related` 包含手动高光 EditDecision（source=`manual_highlight` 未被过滤）
- `topActive` = 手动高光 EditDecision（priority=100）
- `styleClass` = `topActive.action === "delete" ? "masked" : "kept"` = **`"masked"`**

**结果**：用户通过 Timeline 右键「加入精华」手动添加的高光 segment，在 Timeline 上被显示为**删除遮罩样式**（灰色/删除标记），而非高亮样式。这完全违背了高光的语义。

**修复**：

```typescript
// segmentHelpers.ts:25-27
const HIGHLIGHT_SOURCES = new Set(["llm_highlight", "manual_highlight"])

const related = edits.filter(e =>
  (e.target_id === seg.id || isOverlapping(e, seg, 0.3))
  && !HIGHLIGHT_SOURCES.has(e.source),
)
```

**与 Bug E 修复的关系**：Bug E 修复后手动高光的 `action` 变为 `"keep"`，`styleClass` 会变为 `"kept"` 而非 `"masked"`。但 `"kept"` 仍然不是高光的正确显示——高光 segment 应有独立的高亮样式，不应被 `resolveSegmentState` 的 delete/keep 逻辑处理。因此**即使 Bug E 已修复，此处的 source 过滤仍需补充**。

### 新增-2 (P1): `clear_highlight_results` 的 `preserve_manual` 逻辑 bug

已在 Bug D 审计中详细分析。`r.id.split("_")[0]` 永远不可能匹配 `"manual_highlight"`，导致 `preserve_manual=True` 时手动高光仍被清除。修正方案见 Bug D。

### 新增-3 (P2): 规范 Phase 4 屎山清理脚本的边界问题

**位置**：`spec-2.1.1-8.md:480-483`（Phase 4 一次性清理脚本）

规范提议新增 `cleanup_orphan_edits()` 和 `cleanup_duplicate_highlights()` 方法，在应用启动时自动执行。

**审计发现的问题**：

1. **启动时自动执行的时序风险**：`main.py` 初始化阶段执行数据清理，如果清理逻辑有 bug（如 Bug D 的 `split` 问题），会在用户不知情的情况下批量修改所有项目的 `project.json`。建议改为**延迟执行**（用户打开项目时检查）或**显式触发**（Settings 中提供清理按钮）。

2. **`cleanup_duplicate_highlights` 的"保留最新一条"策略**：规范未定义"最新"的判定标准。AnalysisResult 没有 `created_at` 字段（`models.py:148-154`），ID 中的时间戳（`llm_hl_{timestamp}`）可用于 LLM 高光排序，但手动高光的 UUID（`manual_hl_{uuid}`）**无时间序**。

3. **与 Bug E 修复的依赖**：清理脚本应同步将存量高光 EditDecision 的 `action` 从 `"delete"` 修正为 `"keep"`，否则旧数据仍带语义炸弹。

**推荐方案**：将 Phase 4 清理整合为 `project_service.py` 的 `migrate_highlights()` 方法，在 `load_project` 时按 project 粒度执行（而非全局启动时批量执行）：

```python
def migrate_highlights(self) -> dict:
    """One-time migration: fix highlight EditDecisions created before Bug E fix.

    - Set action="keep" for all highlight-source edits
    - Remove orphan edits whose analysis_id no longer exists
    Idempotent: safe to run multiple times.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    tl = self.active_timeline
    ar_ids = {r.id for r in tl.analysis.results}

    updated_edits = []
    fixed = 0
    orphan_removed = 0
    for e in tl.edits:
        is_highlight = e.source in ("llm_highlight", "manual_highlight")
        is_orphan = e.analysis_id and e.analysis_id not in ar_ids

        if is_highlight and is_orphan:
            # Bug G 遗留的孤儿 EditDecision
            orphan_removed += 1
            continue

        if is_highlight and e.action == "delete":
            # Bug E 遗留的错误 action
            updated_edits.append(e.model_copy(update={"action": "keep"}))
            fixed += 1
        else:
            updated_edits.append(e)

    if fixed > 0 or orphan_removed > 0:
        self._update_active_timeline(edits=updated_edits)
        logger.info("Highlight migration: fixed %d actions, removed %d orphans",
                     fixed, orphan_removed)

    return {"success": True, "data": {"fixed_actions": fixed, "removed_orphans": orphan_removed}}
```

---

## 高光提取功能完整运行逻辑

本节梳理高光功能的完整数据流，标注每个 Bug 的发生位置和修复后的预期行为。

### 运行时序图

```
┌─ 用户操作 ──────────────────────────────────────────────────────────────────┐
│                                                                              │
│  A. LLM 自动高光提取                                                         │
│     WorkspacePage.handleStartHighlight(minutes)                              │
│     → useLlmTasks.startHighlight(minutes)                                    │
│       → resetHighlight()                  [仅清前端内存]                      │
│       → call("start_highlight", minutes)                                     │
│         → TaskManager.spawn(_handle_highlight)                               │
│           │                                                                  │
│           ├─ emit("llm:highlight_progress", {results})  ──→ 前端增量填充     │
│           │                                                                  │
│           ├─ add_analysis_results(results, source="llm_highlight")           │
│           │   ├─ Bug D: 不清理旧数据（追加模式）                               │
│           │   ├─ Bug E: action 硬编码 "delete"                                │
│           │   └─ 写入 analysis.results + edits                               │
│           │                                                                  │
│           └─ emit("llm:highlight_completed", {results, total, target})       │
│              └─ 前端: 全量替换 highlightResults                               │
│                 └─ call("detect_highlight_jump_cuts") → 填充 jumpCuts        │
│                                                                              │
│  B. 手动添加高光（Timeline 右键）                                             │
│     WorkspacePage.handleAddToHighlight(segmentId)                            │
│     → call("add_highlight_segment", ???)                                     │
│       ↑ Bug A: 传 {segment_id: xxx} 而非 xxx                                 │
│       → main.add_highlight_segment(segment_id, timeline_id)                  │
│         → add_analysis_results([{...}], source="manual_highlight")           │
│           ├─ Bug E: action="delete"（应为 keep）                              │
│           └─ 新增-1: resolveSegmentState 未过滤 manual_highlight              │
│                                                                              │
│  C. 手动删除高光（侧边栏右键）                                                 │
│     WorkspacePage.handleRemoveHighlight(segmentId)                           │
│     → call("remove_highlight_segment", ???)                                  │
│       ↑ Bug B: 传 {segment_id: xxx} 而非 xxx                                 │
│       → main.remove_highlight_segment(segment_id, timeline_id)               │
│         └─ Bug G: 只清 analysis.results，不清 edits                          │
│                                                                              │
│  D. 退出重进项目                                                              │
│     App.vue 加载 project → WorkspacePage 接收 props.project                  │
│     → onMounted: 加载视频/波形/配置                                           │
│       ↑ Bug C: 无水合 highlightResults / jumpCuts / totalDuration            │
│     → HighlightModeView 收到空数组 → 显示「暂无高光片段」                      │
│                                                                              │
│  E. 删除建议组（SuggestionPanel 右键）                                        │
│     SuggestionPanel.runGroupAction(group, "delete")                          │
│     → emit("delete-suggestion-batch", ids)                                   │
│     → WorkspacePage.deleteEdits(ids)                                         │
│       → call("delete_edit_decisions_batch", ids)                             │
│         └─ Bug F: 仅删 edits，不级联清 analysis.results + dirty_flags        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 持久化数据结构

```json
{
  "timelines": [{
    "id": "default",
    "analysis": {
      "results": [
        {
          "id": "llm_hl_1719400000000",
          "type": "llm_highlight",
          "segment_ids": ["seg_001"],
          "confidence": 1.0,
          "detail": "核心观点：..."
        },
        {
          "id": "manual_hl_abc123def456",
          "type": "llm_highlight",
          "segment_ids": ["seg_005"],
          "confidence": 1.0,
          "detail": "手动添加"
        }
      ]
    },
    "edits": [
      {
        "id": "edit-llm_hl_1719400000000",
        "action": "delete",           ← Bug E: 应为 "keep"
        "source": "llm_highlight",
        "analysis_id": "llm_hl_1719400000000",
        "status": "pending",
        "target_type": "segment",
        "target_id": "seg_001"
      }
    ],
    "transcript": {
      "segments": [
        { "id": "seg_001", "dirty_flags": {} }
      ]
    }
  }]
}
```

---

## 文件变动规则

### 修改清单（按优先级排序）

| 优先级 | Bug | 文件 | 变动类型 | 变动内容 |
|--------|-----|------|----------|----------|
| P0 | A+B | `frontend/src/pages/WorkspacePage.vue` | 改 | L1272, L1282: `call("xxx", { segment_id: id })` → `call("xxx", id)` |
| P0 | 新增-1 | `frontend/src/utils/segmentHelpers.ts` | 改 | L25-27: 增加 `manual_highlight` 到过滤集合 |
| P1 | E | `core/project_service.py` | 改 | L1314-1325: `action="delete"` → 按 source 决定 `"keep"` / `"delete"` |
| P1 | D | `core/project_service.py` | 改 | L1280: `add_analysis_results` 增加 `clear_existing` 参数 |
| P1 | D | `main.py` | 改 | L910-913: 传入 `clear_existing=True` |
| P1 | F | `core/project_service.py` | 改 | L728-745: `delete_edit_decisions_batch` 增加级联清理 |
| P1 | F | `frontend/src/components/workspace/SuggestionPanel.vue` | 改 | L101-102: `totalPending`/`totalAll` 增加 source 过滤 |
| P1 | C | `frontend/src/composables/useLlmTasks.ts` | 新增 | `hydrateHighlightsFromProject(project)` 函数 |
| P1 | C | `frontend/src/pages/WorkspacePage.vue` | 改 | 新增 `watch(() => props.project, ...)` 调用水合 |
| P1 | D | `frontend/src/pages/WorkspacePage.vue` | 改 | 重跑前弹窗确认 |
| P2 | G | `main.py` | 改 | L1466-1469: `remove_highlight_segment` 同步清理 edits |
| P2 | Phase4 | `core/project_service.py` | 新增 | `migrate_highlights()` 方法 |
| P2 | Phase4 | `core/project_service.py` 或 `main.py` | 改 | `load_project` 后调用 `migrate_highlights()` |

### 不变动清单（确认安全）

| 文件 | 原因 |
|------|------|
| `core/models.py` | `EditDecision.action` 已支持 `Literal["delete", "keep"]`，无需改模型 |
| `core/export_service.py` | 新路径（L514-520）从 AnalysisResult 读 segment_ids，不依赖 EditDecision.action |
| `frontend/src/components/workspace/HighlightModeView.vue` | 纯展示组件，数据来源由父组件传入，无直接 bug |

### 测试变动

| 文件 | 变动 |
|------|------|
| `tests/test_highlight_segment.py` | 更新 `_ServiceStub.add_analysis_results` 以支持 `clear_existing` 参数；新增测试验证 `source="manual_highlight"` 时 `action="keep"` |
| `tests/test_project_service.py` | 新增 `delete_edit_decisions_batch` 级联清理测试 |
| `frontend/src/utils/segmentHelpers.test.ts` | 新增 `manual_highlight` source 的 resolveSegmentState 测试 |

---

## 实施顺序建议

```
Phase 1 (P0 紧急):
  1. Bug A+B: 修传参 (1 行改动 × 2)
  2. 新增-1: resolveSegmentState 过滤 manual_highlight

Phase 2 (P1 后端数据完整性):
  3. Bug E: add_analysis_results action 按 source 决定
  4. Bug D: add_analysis_results 增加 clear_existing + _handle_highlight 调用
  5. Bug F: delete_edit_decisions_batch 级联清理
  6. Bug G: remove_highlight_segment 清理 edits

Phase 3 (P1 前端水合 + UI):
  7. Bug C: hydrateHighlightsFromProject + watch
  8. Bug D 前端: 重跑弹窗确认
  9. Bug F 前端: SuggestionPanel source 过滤

Phase 4 (P2 屎山清理):
  10. migrate_highlights + load_project 集成
```

**依赖关系**：Bug E 必须在 Phase 4 之前完成（否则 migrate 脚本无法正确修正 action）。Bug D 的 `clear_existing` 方案依赖 Bug E 已修复（否则清理后重新追加的 EditDecision 仍有错误的 action）。


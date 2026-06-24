# Audit Report: Analysis 功能缺陷集群 & 架构评估 (v2.1.1-6)

## 摘要

本次审计覆盖 Analysis 功能的 4 个已知 bug：1 个为 WorkspacePage 通用 bug，3 个为 Analysis 专属架构债务。经评估，3 个专属 bug 并非独立的问题，而是同一套架构缺陷的不同症状。其中 1 个 bug（error detection 侧边栏不显示）经完整静态代码追踪仍未找到根因，怀疑涉及 runtime 数据流竞态，但无论原因如何，都不影响核心结论：**Analysis 功能的维护成本已超过其边际价值**。

---

## Bug 1（全局）：`isDirty` watch 在连续操作时可能丢失保存

### 严重性

- **影响范围**：全局（所有 edit 操作、edit status 变更、undo/redo）
- **修复成本**：低
- **与 Analysis 的绑定**：无关，是 WorkspacePage 的 watch 逻辑缺陷

### 当前代码及上下文

**文件**：`frontend/src/pages/WorkspacePage.vue` L362–L391

```typescript
// Auto-save state
const isDirty = ref(false)
const isSaving = ref(false)
const lastSavedAt = ref<number | null>(null)
let saveTimer: ReturnType<typeof setTimeout> | null = null

onEvent<void>(EVENT_PROJECT_DIRTY, () => {
  isDirty.value = true
})

onEvent<void>(EVENT_PROJECT_SAVED, () => {
  isDirty.value = false
})

watch(isDirty, (dirty) => {
  if (!dirty || isSaving.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    isSaving.value = true
    try {
      const res = await call<void>("save_project")
      if (res.success) {
        isDirty.value = false
        lastSavedAt.value = Date.now()
      }
    } finally {
      isSaving.value = false
    }
  }, 2000)
})
```

**事件触发源**：`main.py:123-132`

```python
def _mark_dirty(self, result: dict) -> dict:
    """Emit PROJECT_DIRTY if the wrapped mutation succeeded."""
    if result.get("success"):
        self._emit(PROJECT_DIRTY)
    return result
```

`_mark_dirty` 被所有修改类 `@expose` 方法和 5 个 task handler 调用。

### 问题描述

`watch(isDirty, ...)` 在 Vue 3 中只在 `isDirty` 的**值发生变化**时触发（即新值 !== 旧值时）。当用户连续操作时：

1. 操作 A → `isDirty = true`（false→true → watch 触发，启动 2s 计时器）
2. 操作 B（2s 内）→ `isDirty = true`（已经是 true，值不变 → **watch 不触发**）
3. 计时器到期 → 保存操作 A 的状态，**操作 B 的修改丢失**

"撤销之后 projects 文件并未改变，下次更新状态就会恢复标记"的直接原因：如果用户在 2s 窗口内执行了"确认全部"（操作 A）然后"撤销一个"（操作 B），操作 B 的撤销在 `isDirty` 已经是 true 的情况下不会重置计时器，可能在此之前已保存（只有 A 的状态），或者保存完成后才设 `isDirty = false` 但操作 B 的 dirty 信号在设为 true 时已不触发 watch。

**复现场景**：
1. 运行 analysis → 产生 10 条 PENDING edit
2. 右键组菜单 → "全部确认本组"（batch-update，isDirty → true，计时器启动）
3. 立刻右键某条 → "撤销"（resetEdit，isDirty 已为 true → watch 不响应）
4. 等 2 秒 → 保存的是步骤 2 的状态，步骤 3 的撤销丢失
5. 刷新或重开项目 → 所有 edit 仍是 CONFIRMED

### 审计建议

**修复方案**：改用 `watch` 的 `onCleanup` 模式或 debounce 工具函数，确保每次 `isDirty = true` 都重置计时器：

```typescript
// 方案 A：使用 watch 的 onCleanup
watch(isDirty, (dirty, _old, onCleanup) => {
  if (!dirty || isSaving.value) return
  const timer = setTimeout(async () => {
    isSaving.value = true
    try {
      const res = await call<void>("save_project")
      if (res.success) {
        isDirty.value = false
        lastSavedAt.value = Date.now()
      }
    } finally {
      isSaving.value = false
    }
  }, 2000)
  onCleanup(() => clearTimeout(timer))
})

// 方案 B：使用独立的 debounce ref，每次 PROJECT_DIRTY 都重置
// 不依赖 isDirty 的 true→true 转换
```

**优先级**：P0（不论 Analysis 是否保留，此 bug 都应修复）

---

## Bug 2（Analysis 专属）：`delete_edit_decisions_batch` 不清理 `AnalysisResult` → 侧边栏残余

### 严重性

- **影响范围**：Analysis 功能专属
- **修复成本**：中（需定义 AnalysisResult 与 EditDecision 的级联删除策略）
- **与 Analysis 的绑定**：强绑定

### 当前代码及上下文

**后端删除方法**：`core/project_service.py` L728–L745

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    """Permanently remove edit decisions by id.

    Unlike update_edit_decisions_batch (which changes status),
    this removes the edits entirely from the timeline.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    ids_set = set(edit_ids)
    updated_edits = [e for e in self.active_timeline.edits if e.id not in ids_set]
    removed = len(self.active_timeline.edits) - len(updated_edits)
    if removed == 0:
        return {"success": False, "error": "No matching edit decisions found"}

    self._update_active_timeline(edits=updated_edits)
    logger.info("Permanently deleted {} edit decisions", removed)
    return {"success": True, "data": self._current.model_dump()}
```

**注意**：该方法只操作 `edits`，完全不触及 `analysis.results`。

**前端侧边栏数据来源**：`frontend/src/components/workspace/SuggestionPanel.vue` L76–L92

```typescript
const fillerItems: SuggestionItem[] = props.analysisResults
    .filter(r => r.type === "filler")
    .map(r => {
      const range = findSegRange(r.segment_ids)
      const edit = props.edits.find(e => e.analysis_id === r.id)
      return { id: r.id, editId: edit?.id, start: range.start, end: range.end,
               label: r.detail, type: "filler", status: statusOf(edit) }
    })
push("filler", "口头禅", fillerItems)

const errorItems: SuggestionItem[] = props.analysisResults
    .filter(r => r.type === "error")
    .map(r => {
      const range = findSegRange(r.segment_ids)
      const edit = props.edits.find(e => e.analysis_id === r.id)
      return { id: r.id, editId: edit?.id, start: range.start, end: range.end,
               label: r.detail, type: "error", status: statusOf(edit) }
    })
push("error", "口误触发", errorItems)
```

filler/error 组的 item **来源于 `analysisResults`**（即 `timeline.analysis.results`），而非 `edits`。每个 item 通过 `props.edits.find(e => e.analysis_id === r.id)` 查找关联的 edit。

**前端操作按钮可见性**：`SuggestionPanel.vue` L295

```html
<span v-if="item.editId" class="flex items-center gap-1 shrink-0 pt-0.5">
```

操作按钮只在 `item.editId` 存在时渲染。

**AnalysisResult 追加逻辑**：`core/project_service.py` L1280–L1335

```python
def add_analysis_results(self, results: list[dict], source: str) -> dict:
    ...
    all_results = existing_results + analysis_results  # 纯追加，永不清理
    ...
    self._update_active_timeline(
        analysis=self.active_timeline.analysis.model_copy(update={
            "results": all_results,
            "last_run": datetime.now().isoformat(),
        }),
        edits=existing_edits + new_edits,
    )
```

### 问题描述

用户右键 → "删除本组建议" 的数据流：

```
右键"删除本组建议"
  → deleteEdits(editIds)
    → call("delete_edit_decisions_batch", editIds)
      → project_service.delete_edit_decisions_batch()
        → 从 timeline.edits 中移除 EditDecision（仅此而已）
        → timeline.analysis.results 不变 ← BUG！
    → project.value = res.data
  → SuggestionPanel 重算
    → analysisResults 仍然包含被删组的 AnalysisResult
    → editId 变为 undefined（对应 edit 已删除）
    → 条目仍在侧边栏，但操作按钮全部消失
    → 永远无法移除 ← 残留效应
```

**累计效应**：每次运行 Analysis 都追加新的 `AnalysisResult`（L1286-1287），旧的从不清理。多次运行后 `analysis.results` 积累大量孤儿条目。

### 审计建议

**修复路径**（若选择保留 Analysis）：
1. `delete_edit_decisions_batch` 扩展为**同时删除关联的 `AnalysisResult`**（通过 `analysis_id` 关联）
2. 或提供一个独立的 `clear_analysis_results()` 方法，一键清除所有 AnalysisResult + 关联 EditDecision
3. `add_analysis_results` 应考虑去重/替换而非纯追加（对同一 source 的结果）

**优先级**：P1（但如果决定移除 Analysis，此 bug 自然消亡）

---

## Bug 3（Analysis 专属）：`detect_errors` lookahead 无重叠处理 → 过度标记

### 严重性

- **影响范围**：Analysis 功能专属（Error Triggers 检测）
- **修复成本**：中-高（需引入 region overlap 检测 + 合并逻辑）
- **与 Analysis 的绑定**：强绑定

### 当前代码及上下文

**文件**：`core/analysis_service.py` L172–L212

```python
def detect_errors(
    segments: list[Segment],
    trigger_words: list[str],
    lookahead: int = 3,
) -> list[AnalysisResult]:
    """Detect error triggers in subtitle segments and mark the error region."""
    sorted_triggers = sorted(trigger_words, key=len, reverse=True)
    subtitle_segs = [s for s in segments if s.type == "subtitle"]
    results: list[AnalysisResult] = []

    for i, seg in enumerate(subtitle_segs):
        if not seg.text:
            continue
        matched_trigger: str | None = None
        for word in sorted_triggers:
            if word in seg.text:
                matched_trigger = word
                break
        if matched_trigger is None:
            continue

        region_ids: list[str] = [seg.id]
        for j in range(i + 1, min(i + 1 + lookahead, len(subtitle_segs))):
            region_ids.append(subtitle_segs[j].id)

        results.append(
            AnalysisResult(
                id=f"error-{uuid.uuid4().hex[:8]}",
                type="error",
                segment_ids=region_ids,
                confidence=0.85,
                detail=f"Error trigger: '{matched_trigger}' at segment {seg.id}",
            )
        )

    return results
```

**默认触发词**（`core/config.py`）：

```python
"error_trigger_words": [
    "不对", "重来", "重新说", "说错了",
    "刚才说错了", "这段不要", "再来一遍", "算了", "不是这样的",
],
```

**EditDecision 创建逻辑**（`add_analysis_results`）：每个 `AnalysisResult` 生成一个 `EditDecision`，其时间范围覆盖 `min→max` 所有 segment_ids，`target_id` 只指向 `segment_ids[0]`。

**Segment 视觉状态判定**（`frontend/src/utils/segmentHelpers.ts` L21–L53）：

```typescript
export function resolveSegmentState(edits, seg) {
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg, 0.3),
  )
  const active = related.filter(e => e.status !== "rejected")
  const sortedActive = active.sort((a, b) => b.priority - a.priority)
  const topActive = sortedActive[0]
  if (!topActive) return { displayStatus: ..., styleClass: "normal", ... }
  return {
    displayStatus: topActive.status,
    styleClass: topActive.action === "delete" ? "masked" : "kept",
    ...
  }
}
```

### 问题描述

**检测算法**：对每个 subtitle segment 做字符串包含匹配（`word in seg.text`）。匹配后，将该 segment + 后续 `lookahead=3` 个 segment 标记为一个"error region"。

**两个级联效应**：

**效应 A：单触发 cascade 覆盖多段**
- "不对"在 segment 5 出现 → region = [5, 6, 7, 8]
- 4 个 segment 全部变为 `styleClass="masked"`（红色删除划线）

**效应 B：相邻触发产生大量重叠 region**
- segment 3 匹配"不对" → region1 = [3, 4, 5, 6]
- segment 5 匹配"算了" → region2 = [5, 6, 7, 8]
- 产生 2 个独立 EditDecision，总覆盖 3-8（6 个 segment）

**语境问题**：`"不对"` 在中文口语中可能是否定句的一部分（"这个方案对不对..."），`"算了"` 可能是计算相关用语（"算了三遍"），`"重来"` 可能是回顾性用语（"我们重来一遍"）。字符串包含匹配无法区分这些语境，导致 FP（假阳性）较高。

### 审计建议

**修复路径**（若选择保留 Analysis）：
1. 引入 region 重叠检测：新生成的 error region 与现有 region 重叠时 **合并而非新增**
2. 添加置信度衰减：lookahead 越远的 segment 置信度递减（第 1 个 0.85 → 第 4 个 0.5）
3. 提供触发词集合的**消极匹配列表**（`"对不对"` 包含 `"不对"` 但不触发）
4. 或改用简单正则：`re.search(rf'\b{word}\b', text)` 对中文词边界更准确

**优先级**：P2（但如果决定移除 Analysis，此 bug 自然消亡）

---

## Bug 4（Analysis 专属）：Full Analysis 调用 `detect_punctuation` → 全部标记删除

### 严重性

- **影响范围**：Analysis 功能专属（Full Analysis / 规则分析）
- **修复成本**：低（一行默认值改动）
- **与 Analysis 的绑定**：强绑定

### 当前代码及上下文

**文件**：`core/analysis_service.py` L305–L332

```python
def run_full_analysis(
    segments: list[Segment],
    settings: dict,
) -> list[AnalysisResult]:
    """Run filler, error, duplicate, and punctuation detection, returning combined results."""
    filler_words = settings.get("filler_words", [])
    trigger_words = settings.get("error_trigger_words", [])
    language = settings.get("asr_language", "zh")
    duplicate_threshold = settings.get("duplicate_threshold", 0.85)
    duplicate_min_length = settings.get("duplicate_min_length", 5)
    detect_punct = settings.get("detect_punctuation", True)  # ← 默认启用

    fillers = detect_fillers(segments, filler_words)
    errors = detect_errors(segments, trigger_words)
    duplicates = detect_duplicates(
        segments,
        language=language,
        threshold=duplicate_threshold,
        min_length=duplicate_min_length,
    )

    result = fillers + errors + duplicates

    if detect_punct:                      # ← 默认启动
        punctuations = detect_punctuation(segments)
        result.extend(punctuations)

    return result
```

**`detect_punctuation` 默认标点列表**（`core/analysis_service.py` L232–L271）：

```python
punctuation_marks = [
    # Chinese punctuation
    "。", "！", "？", "，", "、", "；", "：",
    # ... 还包括 "", """, "'", "'", "（", "）", "【", "】", ...
    # English punctuation
    ".", "!", "?", ",", ";", ":", "(", ")", ...
]
```

**`detect_punctuation` 检测逻辑**（`core/analysis_service.py` L275–L301）：对每个 subtitle segment，检查是否包含列表中**任一**标点符号，只要包含就生成一个 `AnalysisResult(type="punctuation", action="delete")`。

### 问题描述

数据流（追踪用户点击"规则分析"按钮）：

```
用户点击 "规则分析"（Full Analysis）
  → WorkspacePage: case "full": await runFullAnalysis()
    → createTask("full_analysis") + startTask()
      → _handle_full_analysis()
        → run_full_analysis(segments, settings)
          → detect_fillers(segments, filler_words)    ← 少数段匹配
          → detect_errors(segments, trigger_words)    ← 少数段匹配
          → detect_duplicates(...)                     ← 视内容定
          → detect_punctuation(segments)               ← ❌ 几乎每段都匹配
        → add_analysis_results(all_results, "full_analysis")
          → 每个 result 创建 EditDecision(action="delete")
          → 全部追加到 timeline.edits
        → _mark_dirty() + TASK_COMPLETED
      → project.value 更新
      → resolveSegmentState() 计算每个段的 styleClass
        → 几乎所有段都有至少一条 action="delete" 的 edit
        → 全部变为 styleClass="masked"（红色删除线）
```

**根因**：ASR 输出的字幕段几乎每个都包含中文标点（逗号、句号等）。`detect_punctuation` 的默认标点列表包含 `"，"`、`"。"`、`"？"` 等 ASR 常见符号，因此对**几乎所有 subtitle segment** 返回了一个 `AnalysisResult`。`add_analysis_results` 将每个 result 生成一条 `action="delete"` 的 `EditDecision`，导致 timeline 上所有段都出现红色删除线。

**典型复现**：导入任意中文视频 → ASR 转录 → 点击"规则分析" → timeline 所有段被标记为删除。

### 审计建议

**修复路径**（若选择保留 Analysis）：

1. **改默认值**：将 `settings.get("detect_punctuation", True)` 改为 `settings.get("detect_punctuation", False)` — 最简修复，一行改动
2. **从 Full Analysis 去掉标点检测**：`run_full_analysis` 不调用 `detect_punctuation`，改由用户按需单独触发
3. **或重构标点检测语义**：标点检测不应默认生成 `action="delete"`，而应生成 `action="keep"` + 低优先级，仅标记而非删除

**优先级**：P1（但如果决定移除 Analysis，此 bug 自然消亡）

---

## Bug 5（架构）：AnalysisResult append-only 设计 → 累积债务

### 严重性

- **影响范围**：Analysis 功能专属
- **修复成本**：高（需重构数据模型）
- **与 Analysis 的绑定**：强绑定

### 当前代码

**`core/project_service.py` L1286–L1287**：

```python
existing_results = list(self.active_timeline.analysis.results)
all_results = existing_results + analysis_results  # 纯追加
```

`add_analysis_results` 每次都将新结果追加到 `existing_results` 末尾。没有去重机制、没有结果替换策略、没有手动清理方法（除直接编辑 `project.json`）。这与 `add_silence_results` 的"跳过已覆盖范围"形成对比（`project_service.py:639-646`）。

### 问题描述

AnalysisResult 的累积遵循以下规律：

```
第 1 次 runFullAnalysis → analysis.results = [A1, A2, A3]
第 2 次 runFullAnalysis → analysis.results = [A1, A2, A3, A4, A5, A6]
第 N 次 runFullAnalysis → analysis.results = [A1, ..., A(3N)]
```

每次运行的结果都是独立的，即使检测的 trigger 完全没变。结果之间没有版本号、没有覆盖标记。这是 Bug 1（侧边栏残余）和"每次 Analysis 都拉屎一样遗留一堆东西"的根本原因。

对比 `silence_detection` 的 covered-range 跳过机制（L639-646），`analysis` 没有任何等价保护。

### 审计建议

**修复路径**（若选择保留 Analysis）：
1. 引入"分析快照"概念：每次 `add_analysis_results` 前清除同一 source 的旧结果
2. 或至少提供 `clear_analysis_results(source: str)` 方法
3. 或将 `analysis.results` 改为按 source 分组的字典（`dict[str, list[AnalysisResult]]`）而非扁平列表

**优先级**：P1（但==如果决定移除 Analysis，此 bug 自然消亡==）

---

## 架构评估：Analysis 功能保留 vs 移除

### 已知缺陷汇总

| Bug # | 描述 | 范围 | 修复成本 | 保留与否 |
|-------|------|------|----------|----------|
| Bug 1 (原 Bug 3) | `isDirty` watch 不重置 | **全局** | 低 | 保留 Analysis 也必修 |
| Bug 2 (原 Bug 1) | 孤儿 AnalysisResult | Analysis | 中 | 只在保留 Analysis 时修 |
| Bug 3 (原 Bug 2) | Error detection 过度标记 | Analysis | 中-高 | 只在保留 Analysis 时修 |
| Bug 4 | Full Analysis 标点检测全覆盖（根因已确认） | Analysis | 低 | 只在保留 Analysis 时修 |
| Bug 5 | AnalysisResult append-only | Analysis | 高 | 只在保留 Analysis 时修 |

### 关键观察

| 维度 | Analysis（规则引擎） | LLM Smart Delete |
|------|---------------------|-----------------|
| 检测精度 | 字符串包含匹配，FP 率高 | 语义理解，可区分语境 |
| 触发词配置 | 9 个硬编码默认词，用户需手动管理 | 自然语言 prompt |
| 离线可用 | 是 | 否（需 LLM API） |
| 零配置 | 是 | 需 API key + 模型配置 |
| 当前 bug 数 | 4 个（全部确认根因） | 0 个（已知） |
| 维护负债 | 高 | 低（前端解析 + 后端入库） |

规则引擎仅存的护城河是"离线/零配置"，但默认触发词列表在中文口语中的 FP 率极高，导致实际用户体验反而不如 LLM 路径。lookahead=3 的无重叠处理进一步放大了 FP 的影响。

4 个 bug 中有 3 个（Bug 2、3、5）并非独立问题，而是同一架构缺陷（AnalysisResult 作为 append-only 列表、EditDecision 单向关联无级联删除、字符串匹配+固定 lookahead 代替语义理解）的不同症状。Bug 4（标点检测全覆盖）是独立的低修复成本 bug，但同样被 Analysis 的整体架构债务所裹挟。局部修补只会让代码更复杂，不会让功能更好用。

### 结论

**建议移除 Analysis 功能（规则引擎分支）**，保留 WorkspacePage 的 `isDirty` watch 修复作为独立 PR。理由：

1. **边际价值已被 LLM Smart Delete 覆盖**：规则引擎承诺的"无需 LLM"使用场景，在实际中因 FP 率过高而价值有限
2. **修复成本超过收益**：修复 3 个 Analysis 专属 bug 需要触及数据模型、检测算法、前端展示三层，每个修复都是架构层面的改动
3. **删除比保留更安全**：remove dead code 不会引入新 bug，而修补可能触发未预见的边缘情况
4. **降低认知负担**：新 contributor 看到 analysis_service.py + SuggestionPanel 的 analysis 分支 + project_service 的 analysis 接口，会误以为是产品核心功能

### 移除范围（如执行）

| 文件/模块 | 移除内容 | 备注 |
|-----------|----------|------|
| `core/analysis_service.py` | 整文件 | 4 个检测函数 + `run_full_analysis` |
| `core/models.py` | `AnalysisData`, `AnalysisResult` | 保留 `EditDecision.source` 字符串作为 LLM Smart Delete 使用 |
| `core/events.py` | `ANALYSIS_UPDATED` | LLM 相关事件保留 |
| `core/project_service.py` | `add_analysis_results`, `confirm_all_from_source` | 保留 `EditDecision` 相关方法 |
| `frontend/src/composables/useAnalysis.ts` | `runFillerDetection`, `runErrorDetection`, `runFullAnalysis` | 保留 `runSilenceDetection` 和 task 泛型方法 |
| `frontend/src/types/project.ts` | `AnalysisData`, `AnalysisResult` | |
| `frontend/src/utils/events.ts` | `EVENT_ANALYSIS_UPDATED` | |
| `frontend/src/components/workspace/SuggestionPanel.vue` | `filler`, `error` 分组逻辑 | 保留 `silence`, `llm_smart`, `partial_delete` |
| `main.py` | `_handle_filler_detection`, `_handle_error_detection`, `_handle_full_analysis` | |
| `core/config.py` | `filler_words`, `error_trigger_words` | |

---

文档版本：v2.1.1-6
日期：2025-06-24
审计范围：Analysis 功能全链路（core/analysis_service.py → project_service.py → main.py → frontend bridge → SuggestionPanel）

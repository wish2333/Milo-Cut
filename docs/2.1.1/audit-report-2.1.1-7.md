# Audit Report -- v2.1.1 Spec-6 执行阶段残余问题审计

> **审计日期**: 2026-06-25
> **审计范围**: `docs/2.1.1/residual-issues-spec-2.1.1-7.md` 所列 R-01 ~ R-06 + M1 ~ M5
> **当前分支**: `dev-2.1.1` (HEAD `77b6766`)
> **审计方式**: 直接读取当前代码库，逐项核对报告所述行号、根因、影响范围

---

## 总览确认表

| ID | 报告判定 | 审计结论 | 偏差说明 |
|----|----------|----------|----------|
| R-01 | P0 Bug | **确认成立**，且影响范围**比报告所述更广** | 报告只提到 `WorkspacePage.vue`，实际 `PreviewPlayer.vue` 也有同样缺陷 |
| R-02 | P0 数据 | **确认成立**，根因描述准确 | 计数 bug + 数据残留双重问题均验证 |
| R-03 | P1 UI | **确认成立**，两处问题均验证 | 跳切未折叠 + 小数未格式化 |
| R-04 | P1 UI | **确认成立**，行号需修正 | 报告行号 355-359/296-309 大致正确，实际为 355-360/296-309 |
| R-05 | P2 已验证 | **确认安全**，三层防护验证完整 | 报告描述准确 |
| R-06 M1 | Minor | **确认成立**，且**比报告所述更广** | 报告称"全局按钮"，实际 8 处分散在 4 个文件 |
| R-06 M2 | Minor | **确认成立** | SettingsModal save/cancel 均 `rounded-lg` |
| R-06 M3 | Minor | **确认成立** | Timeline merge 按钮 `rounded`（裸值） |
| R-06 M4 | Minor | **确认成立** | toast watch 无去重 guard |
| R-06 M5 | Minor | **确认缺失** | `add/remove_highlight_segment` 零测试覆盖 |

下面逐项展开。

---

## R-01: 编辑预览模式未跳过 `subtitle_trim` 间隙 (P0)

### 1.1 当前代码与上下文

**报告所述文件**: `WorkspacePage.vue:185-190`

**审计实际读取** -- `frontend/src/pages/WorkspacePage.vue:185-200`：

```typescript
// line 185
const deleteRanges = computed(() => {
  return edits.value
    .filter(e => e.status === "confirmed" && e.action === "delete")
    //                           ^^^^^^^^^^^^^^^^
    // 要求 status==="confirmed"，但 subtitle_trim 始终是 PENDING
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})

function checkSkip(time: number): boolean {
  for (const range of deleteRanges.value) {
    if (time >= range.start && time < range.end) {
      videoRef.value!.currentTime = range.end
      return true
    }
  }
  return false
}
```

报告行号**准确**。`deleteRanges` 在第 2027 行作为 `:delete-ranges` prop 传入 `VideoControls`，驱动进度条红色覆盖层 + `checkSkip` 跳转逻辑。

### 1.2 审计新发现：报告遗漏了第二处缺陷

报告**只提到** `WorkspacePage.vue`，但同样的过滤缺陷在**导出预览播放器**中也存在：

**`frontend/src/components/export/PreviewPlayer.vue:30-35`**：

```typescript
// line 30
const deleteRanges = computed(() => {
  return props.edits
    .filter(e => e.status === "confirmed" && e.action === "delete")
    //                            ^^^^^^^^^^^^^^^^
    // 同样的缺陷：subtitle_trim (PENDING) 被排除
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})
```

该 computed 被 `PreviewPlayer.vue` 的 `checkSkip()` (line 130)、删除区域可视化叠加层 (line 246)、"n 个删除区域"计数显示 (line 300-301) 使用。

> **影响**：导出页的预览播放器**同样不会跳过 subtitle_trim 间隙**，且导出预览的红色删除区域计数也会少算 subtitle_trim 的条数。报告 R-01 的修复方案只覆盖工作区，导出预览仍会残留此 bug。

### 1.3 后端 `subtitle_trim` 创建逻辑确认

**`core/project_service.py:1882-1907`**：

```python
# line 1882
existing_edits = list(self.active_timeline.edits)
new_edits: list[EditDecision] = []
for i, (start, end) in enumerate(delete_ranges):
    edit_id = f"edit-subtitle-trim-{i:04d}"
    already_covered = any(
        e.action == "delete"
        and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
        and abs(e.start - start) < 0.05
        and abs(e.end - end) < 0.05
        for e in existing_edits
    )
    if not already_covered:
        new_edits.append(EditDecision(
            id=edit_id,
            start=start,
            end=end,
            action="delete",              # line 1900
            source="subtitle_trim",       # line 1901
            status=EditStatus.PENDING,    # line 1902 -- 关键：PENDING
            priority=100,
            target_type="range",
        ))
self._update_active_timeline(edits=existing_edits + new_edits)
```

**`core/models.py:99-109`** -- EditDecision 模型，`status` 默认 `EditStatus.PENDING`：

```python
class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING   # line 106
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None
```

报告根因**完全准确**：subtitle_trim 创建为 `status=PENDING`，前端 `deleteRanges` 只认 `confirmed`，导致全部排除。

### 1.4 前端对 `subtitle_trim` source 的感知

`frontend/src/` 中搜索 `subtitle_trim` 仅命中 **API 调用名**，无任何逻辑判断：

| 文件 | 行 | 用途 |
|------|----|------|
| `composables/useEdit.ts:140` | `call<Project>("delete_subtitle_trim_edits")` | 删除全部 subtitle_trim 的后端调用 |
| `types/api.ts:42` | `"delete_subtitle_trim_edits"` | 联合类型 |

**结论**：前端完全不感知 `source === "subtitle_trim"`，这是 bug 的第二层根因 -- 前端 filter 维度缺失 `source`。

### 1.5 建议修复

报告的修复方案正确，但**必须同步修改 `PreviewPlayer.vue`**：

**`WorkspacePage.vue:187`**：

```typescript
.filter(e => e.action === "delete" && (e.status === "confirmed" || e.source === "subtitle_trim"))
```

**`PreviewPlayer.vue:32`**（报告遗漏，必须一并改）：

```typescript
.filter(e => e.action === "delete" && (e.status === "confirmed" || e.source === "subtitle_trim"))
```

**关于导出侧（`useExport.ts:28`）**：审计确认导出过滤条件 `e.status === "confirmed" && e.action === "delete"` **不应改动** -- 导出应该只删除用户显式确认的区间，subtitle_trim 作为自动检测的待定项，除非用户确认否则不应进入导出删除集。这是**正确的当前行为**。

> **安全性复核**：报告提到"REJECTED 的 subtitle_trim 也会被跳过，这是正确的"。审计认同：字幕间空白间隙不是内容，剪后预览跳过所有检测出的间隙（无论用户后续是否保留）符合预览语义。预览 != 最终导出。

---

## R-02: 字幕修正计数不归零 + AnalysisResult 残留 (P0)

### 2.1 问题 A -- 计数显示不归零

**报告所述**: `WorkspacePage.vue:81-83` 的 `subtitleCorrectionCount`

**审计实际读取** -- `frontend/src/pages/WorkspacePage.vue:80-96`：

```typescript
// line 80:  // subtitleCorrectionResult now only carries stored_count metadata.
const subtitleCorrectionCount = computed(
  () => subtitleCorrectionResult.value?.stored_count ?? pendingCorrections.value.length,
)
//         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^  -- 左侧非 null 永远优先
//                                                    ^^^  右侧仅在左侧为 null/undefined 时取

// line 85: watch for toast (与 M4 相关)
watch(subtitleCorrectionResult, (result) => {
  if (result && result.stored_count !== undefined && result.stored_count > 0) {
    showToast(`字幕修正完成，发现 ${result.stored_count} 条修改`, "success", 3000)
  }
})
```

报告行号**准确**，根因描述**完全正确**：`stored_count` 在 `llm:subtitle_correction_completed` 事件中赋值后永不递减，`??` 运算符优先取左侧非 null 的值。

### 2.2 `stored_count` 赋值与重置链路

**`useLlmTasks.ts:124-133`** -- 事件监听赋值：

```typescript
onEvent<{ stored_count?: number } & Partial<SubtitleCorrectionResult>>(
  EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED,
  async (detail) => {
    isRunning.value = false
    if (detail) {
      subtitleCorrectionResult.value = detail as SubtitleCorrectionResult
      // 赋值后，只在下次 resetSubtitleCorrection() 时置 null
    }
  },
)
```

**`useLlmTasks.ts:231-236`** -- `resetSubtitleCorrection` 定义：

```typescript
function resetSubtitleCorrection() {
  subtitleCorrectionResult.value = null
  pendingCorrections.value = []
  progress.value = 0
  errorMsg.value = null
}
```

**调用点** -- `useLlmTasks.ts:255`（`startSubtitleCorrection` 内部）：

```typescript
async function startSubtitleCorrection(referenceText = ""): Promise<void> {
  isRunning.value = true
  progress.value = 0
  errorMsg.value = null
  resetSubtitleCorrection()   // <-- 仅在重新启动 P1 时调用
  ...
}
```

### 2.3 关键缺陷：accept/reject/clear 后**不重置** `subtitleCorrectionResult`

**`useLlmTasks.ts:322-371`** -- 三个审阅操作都只更新 `pendingCorrections`，从不触碰 `subtitleCorrectionResult`：

```typescript
// acceptCorrection (line 322)
async function acceptCorrection(resultId: string): Promise<boolean> {
  const res = await call<{ segment_id: string }>("accept_correction", resultId)
  if (res.success) {
    pendingCorrections.value = pendingCorrections.value.filter((c) => c.id !== resultId)
    // subtitleCorrectionResult 未变 -> stored_count 仍为旧值
    return true
  }
  return false
}

// rejectCorrection (line 333) -- 同样模式
// clearCorrections (line 361) -- pendingCorrections = []，但 subtitleCorrectionResult 未变
```

**Bug 时序验证**：

| 时序 | `subtitleCorrectionResult` | `pendingCorrections` | `subtitleCorrectionCount` |
|------|---------------------------|----------------------|---------------------------|
| P1 完成，5 条 | `{ stored_count: 5 }` | `[5 items]` | `5`（取 stored_count）|
| 审阅完 5 条 | `{ stored_count: 5 }` | `[]` | **`5`** -- 应归零 |
| clearCorrections | `{ stored_count: 5 }` | `[]` | **`5`** -- 应归零 |

### 2.4 问题 B -- AnalysisResult 残留

**后端 accept/reject/clear 已正确删除** AnalysisResult（报告此处描述需修正）：

| 后端方法 | 位置 | 删除逻辑 | 状态 |
|----------|------|----------|------|
| `accept_subtitle_correction` | `project_service.py:1546` | `[r for r in tl.analysis.results if r.id != result_id]` | 删除该条 |
| `reject_subtitle_correction` | `project_service.py:1575` | `[r for r in tl.analysis.results if r.id != result_id]` | 删除该条 |
| `clear_subtitle_corrections` | `project_service.py:1659` | `[r for r in ... if r.type != "llm_subtitle_correction"]` | 删除全部 |
| `store_subtitle_corrections` | `project_service.py:1392` | `kept_results = [r for r in ... if r.type != "llm_subtitle_correction"]` | 重新运行时清除 |

> **审计修正报告措辞**：报告 R-02 问题 B 称"审阅完毕后没有触发清理" -- 实际上后端**已正确清理** AnalysisResult。真正的残留问题在于：
> 1. **前端状态残留**：`subtitleCorrectionResult.value` 在审阅后不重置，导致计数显示错误（问题 A）
> 2. **重新打开项目时**：残留的已处理 AnalysisResult 会被 `get_subtitle_corrections` 重新 load 到 `pendingCorrections`（如果审阅时用的是 accept/reject 单条删除，则无残留；但如果用户中途关闭未处理完，残留的未审阅项会重新出现 -- 这是**预期行为**，不算 bug）

因此 R-02 的核心修复点是**前端计数显示**，后端数据清理逻辑实际是健全的。

### 2.5 建议修复

**方案 1（推荐，最小改动）**：调整 `??` 优先级 -- `pendingCorrections` 优先，`stored_count` 仅 fallback：

```typescript
// WorkspacePage.vue:81-83
const subtitleCorrectionCount = computed(
  () => pendingCorrections.value.length || subtitleCorrectionResult.value?.stored_count ?? 0,
)
```

这样审阅完毕（`pendingCorrections` 归零）时，`||` 会跳到右侧，但右侧 `stored_count` 仍非零 -- **此方案不成立**，因为 `||` 对 `0 || 5` 返回 5。

**方案 2（正确）**：用 `pendingCorrections.length` 作为唯一真实来源，`stored_count` 仅用于首次 toast：

```typescript
// WorkspacePage.vue:81-83
const subtitleCorrectionCount = computed(() => pendingCorrections.value.length)
```

配合 toast watch 仍读取 `subtitleCorrectionResult.stored_count`（首次完成通知），计数显示则跟随实际待审数。这是最清晰的修复 -- 计数语义本就是"待审数量"。

**方案 3**：在 `accept/reject/clearCorrections` 中，当 `pendingCorrections` 归零时调用 `resetSubtitleCorrection()`。改动点多但语义最完整。

> **推荐方案 2**：单行改动，语义最清晰，且 `stored_count` 字段仍保留用于 toast。

---

## R-03: 高光提取 UI 问题 (P1)

### 3.1 问题 A -- 跳切列表未折叠

**报告所述**: `HighlightModeView.vue:175-185`

**审计实际读取** -- `frontend/src/components/workspace/HighlightModeView.vue:174-185`：

```html
<!-- line 174: Jump cut warnings -->
<div v-if="jumpCuts.length > 0" class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
  <div class="flex flex-col gap-1">
    <span class="font-semibold">检测到 {{ jumpCuts.length }} 处跳切</span>
    <ul class="ml-4 list-disc">
      <li v-for="(jc, i) in jumpCuts" :key="i">
        片段 {{ jc.index }}->{{ jc.index + 1 }} 间隔
        {{ Math.round(jc.gap_duration) }}s 可能产生音频跳变
      </li>
    </ul>
  </div>
</div>
```

报告行号**准确**。当前是 `<ul>` 无折叠无高度限制，跳切 10+ 处会撑爆可见区域。报告建议改为 `<details>` 默认折叠，方案正确。

### 3.2 问题 B -- "已选 xx s" 小数过多

**报告所述**: `HighlightModeView.vue:171`

**审计实际读取** -- `frontend/src/components/workspace/HighlightModeView.vue:166-172`：

```html
<!-- line 166: Duration summary -->
<div v-if="sortedHighlights.length > 0" class="text-xs text-gray-500">
  已选 {{ totalDuration }}s / 目标 {{ targetDuration }}s
</div>
```

**数据来源链路验证**：
- `totalDuration` 是 prop（`HighlightModeView.vue:29, 38`，默认 `0`）
- 父组件 `Timeline.vue:419` 传入 `:total-duration="highlightTotalDuration ?? 0"`
- `highlightTotalDuration` 在 `useLlmTasks.ts:165` 由事件 payload `detail.total_duration` 赋值
- 后端 `main.py:890` 取 `result["data"]["total_highlight_duration"]`
- 后端 `core/llm_service.py:1155-1164` 计算：`total_dur = 0.0; for r in deduped: ... total_dur += dur`（**逐段 float 累加，未 round**）

```python
# core/llm_service.py:1154-1164
selected: list[dict] = []
total_dur = 0.0
for r in deduped:
    seg = seg_map.get(r["segment_id"])
    if seg is None:
        continue
    dur = seg.get("end", 0) - seg.get("start", 0)
    ...
    total_dur += dur   # <-- float 累加，会产生如 615.378194
```

**确认**：`total_dur` 未经任何 `round()`，直接经 `main.py:919` emit 到前端，前端 `HighlightModeView.vue:171` 直接 `{{ totalDuration }}` 插值，**无 `toFixed`**。报告描述完全准确。

> **附带发现**：手动 `add_highlight_segment` / `remove_highlight_segment`（`main.py:1397/1440`）**不重新计算 total_duration**，导致手动增删后显示的已选时长与实际不符。这不属于 R-03 范围，但值得记录为已知限制。

### 3.3 建议修复

**问题 A** -- 改 `<details>`（报告方案正确）：

```html
<details v-if="jumpCuts.length > 0" class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
  <summary class="cursor-pointer font-semibold">
    检测到 {{ jumpCuts.length }} 处跳切（点击展开）
  </summary>
  <ul class="mt-1 ml-4 list-disc">
    <li v-for="(jc, i) in jumpCuts" :key="i">
      片段 {{ jc.index }} -> {{ jc.index + 1 }} 间隔
      {{ Math.round(jc.gap_duration) }}s 可能产生音频跳变
    </li>
  </ul>
</details>
```

**问题 B** -- `toFixed(1)`（报告方案正确）：

```html
已选 {{ totalDuration.toFixed(1) }}s / 目标 {{ targetDuration.toFixed(1) }}s
```

两处改动均在 `HighlightModeView.vue`，无需触碰后端。

---

## R-04: 建议面板 UI 精简 (P1)

### 4.1 当前代码与报告行号核对

**报告所述移除项**：
1. 右键"全部撤销本组" (`reset`) -- 报告行号 355-359
2. 底部"全部确认删除"大按钮 -- 报告行号 296-309
3. 底部"忽略所有建议"大按钮 -- 报告行号 296-309

**审计实际读取** -- `frontend/src/components/workspace/SuggestionPanel.vue`：

**移除项 1 -- 组级右键"全部撤销本组"（实际行 355-360）**：

```html
<!-- line 355 -->
<button
  class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
  @click="runGroupAction(contextMenu.group, 'reset')"
>
  全部撤销本组
</button>
```

报告行号 355-359，实际 355-360（含闭合 `</button>`），**偏差 1 行**，可忽略。

**移除项 2+3 -- 底部操作栏（实际行 296-309）**：

```html
<!-- line 296 -->
<div v-if="totalPending > 0" class="flex gap-2 px-3 py-2 bg-gray-50">
  <button
    class="flex-1 text-sm px-3 py-1.5 rounded-full bg-blue-500 text-white hover:bg-blue-600 transition-colors"
    @click="emit('confirm-all')"
  >
    全部确认删除
  </button>
  <button
    class="flex-1 text-sm px-3 py-1.5 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
    @click="emit('reject-all')"
  >
    忽略所有建议
  </button>
</div>
```

报告行号 296-309 **准确**。

### 4.2 移除后的连带清理

审计确认移除上述 UI 后，以下 emit 定义和逻辑会变为**无消费者**，应一并清理：

**`SuggestionPanel.vue:21-22`** -- emit 声明：

```typescript
const emit = defineEmits<{
  ...
  "confirm-all": []      // line 21 -- 仅底部按钮使用
  "reject-all": []       // line 22 -- 仅底部按钮使用
  ...
}>()
```

移除底部按钮后，`confirm-all` / `reject-all` 这两个 emit 在 SuggestionPanel 内**无其他消费者**，应从 `defineEmits` 删除，并检查父组件 `WorkspacePage.vue` 中对应的 `@confirm-all` / `@reject-all` 绑定。

**`SuggestionPanel.vue:149-164`** -- `runGroupAction` 的 `'reset'` 分支：

```typescript
function runGroupAction(group: GroupedResult, action: "confirm" | "reject" | "reset" | "delete") {
  ...
  else if (action === "reset") emit("reset-edit-batch", ids)  // line 154
  ...
}
```

移除"全部撤销本组"按钮后，`runGroupAction` 的 `'reset'` 分支失去唯一调用点。但 `reset-edit-batch` emit 仍被其他逻辑使用（组级操作），**建议保留 emit，仅从 `runGroupAction` 的类型签名移除 `'reset'`** -- 或者更保守地保留 `'reset'` 分支以备将来使用。

### 4.3 审计对移除决策的评估

报告的移除理由审计**部分认同**：

| 移除项 | 报告理由 | 审计意见 |
|--------|----------|----------|
| "全部撤销本组" | reset 已覆盖单项撤销，组级 reset 无使用场景 | **部分保留**：组级 reset 在"误批量确认后回退"场景有价值。建议保留但移到次要位置，而非完全删除 |
| 底部"全部确认删除" | 组级右键已覆盖 | **认同移除**：`rounded-full` 大按钮与整体 `rounded-md` 风格不一致，且组级操作已覆盖 |
| 底部"忽略所有建议" | 跨组批量忽略无意义 | **认同移除**：跨组忽略确实语义混乱 |

> **建议**：底部两个按钮移除无异议；"全部撤销本组"建议**保留** -- 批量操作的撤销是合理需求，完全移除会降低可用性。若一定要精简，可将其合并进组级右键的次级菜单而非直接删除。

---

## R-05: 字幕纠错重复执行安全性 (P2 -- 已验证安全)

### 5.1 三层防护审计

审计逐层验证报告所述的"两层防护"（实际为三层），**全部确认安全**。

**第一层 -- 后端写入前清除** `core/project_service.py:1391-1395`：

```python
# Clear previously-pending corrections (avoid duplicates on re-run).
kept_results = [
    r for r in tl.analysis.results
    if r.type != "llm_subtitle_correction"
]
```

写入新 corrections 前清除所有同类型旧记录。

**第二层 -- 前端执行前重置** `useLlmTasks.ts:231-236 + 255`：

```typescript
function resetSubtitleCorrection() {
  subtitleCorrectionResult.value = null
  pendingCorrections.value = []
  progress.value = 0
  errorMsg.value = null
}
// 在 startSubtitleCorrection 开头调用
```

每次 P1 启动前清空所有本地状态。

**第三层（报告未提及）-- 工作流累积模式跳过写入** `core/workflow_engine.py:763` + `main.py:810-816`：

```python
# main.py:810
if task.payload.get("_workflow_accumulate"):
    self._emit("llm:token_usage", token_usage)
    return {
        "corrections": corrections,
        "stored_count": len(corrections),
        "token_usage": token_usage,
    }   # <-- 工作流模式下不调用 store_subtitle_corrections，直接返回原始 corrections
```

`workflow_engine.py:735-764` 的 `_extract_edits_from_result` 明确注释：

```python
# subtitle_correction produces no segment-level EditDecisions
return edits   # <-- 永远返回空列表
```

工作流模式下 subtitle_correction 是纯分析步骤，不产生 EditDecision，不写入 project.json，结果仅在工作流 apply 阶段累积。

### 5.2 现有测试覆盖验证

`tests/test_subtitle_correction_review.py`（283 行，17 个测试）覆盖：
- `store_subtitle_corrections`: 正常写入、跳过 no-op、**清除旧记录**、保留其他类型、未知 timeline 失败
- `accept/reject/batch_accept/clear`: 全部 API 方法

其中 `test_store_clears_previous_corrections`（line 77-86）专门验证两次调用后结果仍为 2 条而非 4 条，**直接证明重复执行安全**。

### 5.3 审计结论

报告 R-05 "已验证安全"的判定**准确**。审计补充：实际防护是**三层**（报告只提了两层），工作流累积模式提供了额外的隔离。唯一的残留隐患是 R-02 已覆盖的前端状态问题，与重复执行安全性无关。

---

## R-06 M1: `active:scale-95` 缺少 transition (Minor)

### 6.1 审计发现：影响范围比报告更广

报告称"全局按钮组件"，实际审计在 `frontend/src/` 共发现 **9 处** `active:scale-95`，其中 **8 处有问题**：

**唯一正确的一处**：

| 文件 | 行 | 情况 |
|------|----|------|
| `components/common/FileDropInput.vue:39` | `transition-transform active:scale-95` | 有 `transition-transform`，transform 参与过渡 |

**8 处缺陷**（`transition-colors` 不含 transform，或完全无 transition）：

| # | 文件 | 行 | 当前 class 片段 | 问题 |
|---|------|----|-----------------|------|
| 1 | `HighlightModeView.vue` | 158 | `active:scale-95 transition-colors` | `transition-colors` 不含 transform |
| 2 | `SettingsModal.vue` | 1998 | `active:scale-95` **无任何 transition** | 完全缺失 |
| 3 | `Timeline.vue` | 258 | `active:scale-95 transition-colors` | 同 #1 |
| 4 | `Timeline.vue` | 264 | `transition-colors active:scale-95` | 同 #1 |
| 5 | `ExportPage.vue` | 348 | `active:scale-95 transition-colors` | 同 #1 |
| 6 | `ExportPage.vue` | 357 | 同上 | 同 #1 |
| 7 | `ExportPage.vue` | 366 | 同上 | 同 #1 |
| 8 | `ExportPage.vue` | 375 | 同上 | 同 #1 |

**根因**：Tailwind 的 `transition-colors` 生成的 CSS 是：

```css
transition-property: color, background-color, border-color, text-decoration-color, fill, stroke;
```

**不含 `transform`**，因此 `active:scale-95`（`transform: scale(.95)`）是瞬间跳变，无平滑动画。

### 6.2 建议修复

统一改为 `transition-all duration-150`（覆盖 color + transform）或分别加 `transition-transform`：

```html
<!-- 通用修复模式 -->
class="... active:scale-95 transition-all duration-150"
```

> **审计建议**：考虑到这些按钮同时有 hover 背景色变化，用 `transition-all duration-150` 最为稳妥，一次性覆盖 color 和 transform。9 处中 8 处需改（#2 还需补 `transition-all`）。

---

## R-06 M2: SettingsModal 按钮 `rounded-lg` (Minor)

### 7.1 审计确认

**`frontend/src/components/workspace/SettingsModal.vue`**：

**Cancel/关闭按钮 -- line 1992**：

```html
<button
  class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50"
  @click="emit('close')"
>
  关闭
</button>
```

**Save/保存按钮 -- line 1998**：

```html
<button
  class="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 active:scale-95 disabled:opacity-50"
  :disabled="saving"
  @click="handleSave"
>
  {{ saving ? "保存中..." : "保存" }}
</button>
```

两个按钮均使用 `rounded-lg`，应为 `rounded-md`。报告 M2 **确认成立**。

### 7.2 建议修复

两处 `rounded-lg` 改为 `rounded-md`（line 1992, 1998）。Save 按钮还叠加了 M1 的 transition 缺失问题（无 `transition-all duration-150`），应一并修复。

---

## R-06 M3: Timeline merge 按钮 `rounded` (Minor)

### 8.1 审计确认

**`frontend/src/components/workspace/Timeline.vue:258`**：

```html
<button
  v-if="selectionMode && (selectedCount ?? 0) >= 2"
  class="rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-600 active:scale-95 transition-colors"
  @click="emit('merge-selected')"
>
  合并选中
</button>
```

使用 `rounded`（裸值，即 `border-radius: 0.25rem`），应为 `rounded-md`（`0.375rem`）。报告 M3 **确认成立**。

### 8.2 建议修复

`rounded` 改为 `rounded-md`（line 258）。此按钮同时叠加 M1 问题（`transition-colors` 应改 `transition-all duration-150`）。

---

## R-06 M4: 字幕修正完成 toast 无去重 (Minor)

### 9.1 审计确认

**`frontend/src/pages/WorkspacePage.vue:85-90`**：

```typescript
// line 85: Show toast when subtitle correction completes
watch(subtitleCorrectionResult, (result) => {
  if (result && result.stored_count !== undefined && result.stored_count > 0) {
    showToast(`字幕修正完成，发现 ${result.stored_count} 条修改`, "success", 3000)
  }
})
```

**无去重 guard**。`watch(subtitleCorrectionResult, ...)` 监听 ref 引用变化，只要 `subtitleCorrectionResult.value` 被赋一个新对象引用（即使 `stored_count` 相同），watch 就会触发。

### 9.2 重复触发场景分析

1. **后端重复 emit**：若 `llm:subtitle_correction_completed` 事件被 emit 两次（PyWebView tick 机制下理论可能），`subtitleCorrectionResult` 被赋新对象两次 -> toast 弹两次
2. **reset 后再次完成**：`resetSubtitleCorrection()` 置 `null`，下次完成事件赋新对象 -> watch 触发（`null -> {stored_count: N}`） -- 这是**正常的首次通知**
3. **对象引用变化但值相同**：两次事件 payload 相同但 JSON 反序列化产生不同对象引用 -> watch 仍触发

### 9.3 建议修复

加 flag guard，每次 `resetSubtitleCorrection` 时重置 flag：

```typescript
let correctionToastShown = false

// 在 resetSubtitleCorrection 调用处或 watch result === null 时重置
watch(subtitleCorrectionResult, (result) => {
  if (result === null) {
    correctionToastShown = false
    return
  }
  if (result?.stored_count && result.stored_count > 0 && !correctionToastShown) {
    correctionToastShown = true
    showToast(`字幕修正完成，发现 ${result.stored_count} 条修改`, "success", 3000)
  }
})
```

---

## R-06 M5: `add/remove_highlight_segment` 后端单测缺失 (Minor)

### 10.1 审计确认

`tests/` 目录搜索 `add_highlight_segment|remove_highlight_segment|manual_highlight` -- **零命中**。这两个 API **完全无测试覆盖**。

### 10.2 待测代码定位

**`main.py:1396-1437`** -- `add_highlight_segment`：

```python
@expose
def add_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
    # 验证 project/timeline/segment 存在且为 subtitle 类型
    # 创建 AnalysisResult(type="llm_highlight", detail="手动添加")
    # 调用 add_analysis_results 持久化
```

**`main.py:1440-1472`** -- `remove_highlight_segment`：

```python
@expose
def remove_highlight_segment(self, segment_id: str, timeline_id: str = "") -> dict:
    # 查找所有 segment_ids 包含该 id 的 AnalysisResult
    # 移除并 _update_timeline_by_id 持久化
```

### 10.3 建议补充的测试场景

| 测试 | 目标方法 | 场景 |
|------|----------|------|
| `test_add_highlight_segment_success` | add | 正常添加，验证 results 中出现新 AnalysisResult |
| `test_add_highlight_segment_invalid_segment` | add | 不存在的 segment_id -> `success: False` |
| `test_add_highlight_segment_non_subtitle` | add | segment.type != "subtitle" -> `success: False` |
| `test_remove_highlight_segment_success` | remove | 正常移除，验证 results 中不再包含 |
| `test_remove_highlight_segment_not_found` | remove | 无对应 highlight -> `success: False` |
| `test_remove_highlight_segment_preserves_others` | remove | 移除一个不影响其他 segment 的 highlight |

> **审计附带发现**：`remove_highlight_segment`（`main.py:1465`）的过滤逻辑 `segment_id not in r.segment_ids` 会移除**所有**包含该 segment_id 的 AnalysisResult。如果一个 AnalysisResult 的 `segment_ids` 包含多个 segment（虽然当前 `add` 只加单个，但 LLM 批量提取可能产生多 segment 的 result），移除其中一个 segment 会导致整个多 segment result 被删除。这是**潜在的边界 bug**，建议测试中覆盖"多 segment AnalysisResult 移除其中一个"场景。

---

## 附：审计对报告准确性的总体评价

| 报告章节 | 行号准确性 | 根因准确性 | 审计修正/补充 |
|----------|-----------|-----------|---------------|
| R-01 | 准确 | 准确 | **遗漏 `PreviewPlayer.vue:32` 第二处缺陷**，修复必须同步 |
| R-02 | 准确 | 计数 bug 准确 | 问题 B 措辞需修正：后端清理逻辑**实际健全**，真正残留是前端状态 |
| R-03 | 准确 | 准确 | 补充：后端 `total_dur` 未 round 的确切位置 `llm_service.py:1155-1164` |
| R-04 | 偏差 1 行 | 准确 | 补充：移除后需清理 `confirm-all`/`reject-all` emit；建议保留"全部撤销本组" |
| R-05 | 准确 | 准确 | 补充：实际是**三层**防护（工作流累积模式未提及） |
| M1 | "全局按钮"模糊 | 准确 | 补充：实际 8 处分散在 4 个文件，给出完整清单 |
| M2 | 准确 | 准确 | -- |
| M3 | 准确 | 准确 | -- |
| M4 | 准确 | 准确 | -- |
| M5 | 准确 | 准确 | 补充：`remove_highlight_segment` 多 segment 边界 bug |

---

## 建议修复优先级与工作量预估

| 优先级 | 问题 | 涉及文件 | 改动量 | 风险 |
|--------|------|----------|--------|------|
| **P0** | R-01 | `WorkspacePage.vue` + `PreviewPlayer.vue` | 2 行 | 低（局部 filter） |
| **P0** | R-02 计数 | `WorkspacePage.vue` | 1 行 | 低（computed 改写） |
| **P1** | R-03 | `HighlightModeView.vue` | ~15 行 | 低（纯 UI） |
| **P1** | R-04 | `SuggestionPanel.vue` + 父组件 emit 清理 | ~20 行 | 中（emit 契约变更） |
| **Minor** | M1 | 4 个文件 8 处 | 8 行 | 低 |
| **Minor** | M2 | `SettingsModal.vue` | 2 行 | 低 |
| **Minor** | M3 | `Timeline.vue` | 1 行 | 低 |
| **Minor** | M4 | `WorkspacePage.vue` | ~5 行 | 低 |
| **Minor** | M5 | `tests/` 新建文件 | ~80 行 | 低（纯增量） |

**总预估**：约 130 行改动，集中在 6 个文件 + 1 个新测试文件。所有 P0/P1 修复均为局部改动，无架构级影响。

# Audit Report: spec-2.2.0-1 — 工作流非沙箱化改造

> **审计对象**: `docs/2.2.0/spec-2.2.0-1.md` (v2.2.0 工作流非沙箱化改造规范)
> **审计范围**: 问题诊断准确性 + 规范影响面 + 边界细化 + 推荐实现
> **审计基准代码**: 分支 `dev-2.2.0` @ `b791369`（规范尚未实施，当前仍为沙箱模式）
> **审计结论**: **诊断基本准确，但 P1 结论有误，且规范遗漏了一个关键的现有刷新机制，导致实现说明不够精确。规范整体可行，建议采纳并补充本文的边界细化。**

---

## 一、问题诊断逐条验证

### P0 — 点击「应用结果到项目」后端崩溃 ✅ **确认（根因准确）**

**规范声明**: `apply_workflow()` 直接赋值 `self._project_service.current = ...`，但 `current` 是只读 `@property`，无 setter。

**代码验证**:

`core/project_service.py:58-60`:
```python
@property
def current(self) -> Project | None:
    return self._current
```
该 property **没有定义 setter**（全文件搜索 `@current.setter` 无结果，`current =` 赋值仅出现在 `self._current = ...` 内部字段赋值，从未出现 `self.current = ...` 的外部赋值成功路径）。

`core/workflow_engine.py:907-909`（`apply_workflow` 内）:
```python
self._project_service.current = project.model_copy(update={
    "timelines": new_timelines,
})
```

**运行时行为**: 该行抛出 `AttributeError: property 'current' of 'ProjectService' object has no setter`。由于 `apply_workflow` 在 `MiloCutApi` 上通过 `@expose` 暴露（`main.py:2655-2657`），异常被 `@expose` 捕获并返回 `{"success": False, "error": "..."}`，前端收到失败响应，apply 流程中断。**确认为 P0 阻断 bug。**

> **补充说明**: 规范将其归为"崩溃"略有不精确——`@expose` 会吞掉异常转为错误响应，不会真正让进程崩溃。但效果等同：apply 永远失败，用户无法通过正常路径将工作流结果写入 project。此处属措辞问题，不影响结论。

---

### P1 — 应用后 project 未保存任何相关数据 ⚠️ **部分确认（根因描述有误）**

**规范声明**: 上述崩溃导致 apply 流程中断；即使修复崩溃，前端也未触发 project 刷新。

**代码验证**:

前半句（崩溃导致中断）正确，见 P0。

**后半句（"前端未触发 project 刷新"）经核实为不准确**。规范遗漏了一个已存在的、对非沙箱方案至关重要的刷新机制：

`frontend/src/pages/WorkspacePage.vue:528-537`:
```typescript
// Phase 2: LLM task completion refreshes project (edits/analysis applied)
if (
  data.task_type === "llm_smart_delete" ||
  data.task_type === "llm_subtitle_correction" ||
  data.task_type === "llm_highlight"
) {
  if (data.result?.project) {
    emit("project-updated", data.result.project)
  }
}
```

该监听器对 **所有** `llm_smart_delete` / `llm_subtitle_correction` / `llm_highlight` 任务完成事件触发 `project-updated`，**不区分任务是单功能模式触发还是工作流 `_dispatch_step` 触发**。工作流通过标准 TaskManager 调度（`workflow_engine.py:682` `create_task` → `start_task`），任务完成后 TaskManager 发出的 `task:completed` 事件携带 `task_type`，因此该刷新路径对工作流步骤天然生效。

**修正后的结论**:
- 在**当前沙箱模式**下，由于 handler 因 `_workflow_accumulate=True` 跳过写 project，`result.project` 反映的是写操作前的状态，刷新无实际效果——这是 P3/P4 数据丢失的体现，而非"前端没刷新"。
- 在**非沙箱模式**（规范目标态）下，handler 正常写 project，`result.project` 携带最新数据，上述监听器会自动刷新前端。**规范第 56 行架构图所述"触发 EVENT_TASK_COMPLETED → 前端自动刷新 project 数据"在代码层面已成立**，无需额外新增刷新逻辑。

> **影响**: 该结论不改变规范的整体方案（删除沙箱仍是正确方向），但使得"非沙箱方案可行"的论证更加扎实——刷新机制已存在，只需让 handler 恢复正常写入即可。规范应在此处补一句说明，避免实现者误以为需要新增刷新事件。

---

### P2 — 沙箱模式下 subtitle_correction 结果丢失 ✅ **确认**

**规范声明**: handler 发现 `_workflow_accumulate=True` 跳过 `store_subtitle_corrections`。

**代码验证**:

`main.py:864-872`（`_handle_subtitle_correction` 内）:
```python
# v2.1.0 Phase 3: workflow accumulation mode -- skip project write,
# return raw corrections for the engine to accumulate.
if task.payload.get("_workflow_accumulate"):
    self._emit("llm:token_usage", token_usage)
    return {
        "corrections": corrections,
        "stored_count": len(corrections),
        "token_usage": token_usage,
    }
```

当 `_workflow_accumulate=True` 时，handler 提前 return，**不调用** `store_subtitle_corrections`（`main.py:875-877`），corrections 仅作为返回值传给 engine。

**进一步追踪 — 数据在 engine 侧也丢失**:

`workflow_engine.py:735-764`（`_extract_edits_from_result`）:
```python
def _extract_edits_from_result(self, result, step_type, step_index):
    edits = []
    if step_type in ("llm_smart_delete", "llm_highlight"):
        # ... 提取 edits
    # subtitle_correction produces no segment-level EditDecisions
    return edits
```

`subtitle_correction` 类型被显式排除，`_extract_edits_from_result` 对其返回 `[]`。因此 corrections 既未写入 project，也未进入 `accumulated_edits`，**在沙箱模式下完全丢失**（仅存在于 step result 的瞬态返回值中，apply 时不会被处理）。

**确认**: P2 准确。非沙箱化后，`_workflow_accumulate` 不再传入，handler 走 `main.py:874-892` 正常存储路径，corrections 通过 `store_subtitle_corrections` 持久化。

---

### P3 — 沙箱模式下 highlight 结果丢失 ✅ **确认（双重丢失）**

**规范声明**: handler 跳过写 project，且不返回 `edits` 字段，`_extract_edits_from_result` 拿不到数据。

**代码验证**:

`main.py:965-971`（`_handle_highlight` 内）:
```python
# v2.1.0 Phase 3: workflow accumulation mode -- skip project write
if not task.payload.get("_workflow_accumulate"):
    store = self._mark_dirty(self._project.add_analysis_results(
        analysis_results, source="llm_highlight", clear_existing=True,
    ))
```
`_workflow_accumulate=True` 时跳过 `add_analysis_results`，highlight 分析结果不写入 project。

`main.py:983-988`（`_handle_highlight` 返回值）:
```python
return {
    "results": all_results,
    "total_duration": total_duration,
    "token_usage": token_usage,
    "project": self._project.current.model_dump() if self._project.current else None,
}
```
返回值**没有 `edits` 字段**。而 `_extract_edits_from_result`（`workflow_engine.py:746-761`）依赖 `result.get("edits", [])`，对 highlight 拿到空列表。

**确认**: P3 准确，highlight 在沙箱模式下既不入 project 也不入 `accumulated_edits`，apply 时无数据。

> **边界细化**: 注意 highlight 的语义——它本身**不产生 segment 级删除 edit**，而是产生"精华段标记"（`llm_highlight` 类型的 AnalysisResult）。旧的 `apply_workflow` 即使能拿到 highlight 的 edits 也不会处理（因为 `_extract_edits_from_result` 期望的 edits 结构是 smart_delete 风格的 `{start, end, action, target_id}`）。因此 highlight 的正确持久化路径就是 `add_analysis_results(source="llm_highlight")`，非沙箱化后自然恢复。规范无需为 highlight 构造 edits。

---

### P4 — 工作流锁横幅无实际效果 ✅ **确认（死 prop）**

**规范声明**: 仅展示文字，编辑控件未被禁用。

**代码验证**:

`frontend/src/pages/WorkspacePage.vue:2083-2089`（横幅）:
```html
<div v-if="wf.isActive.value"
     class="flex items-center gap-2 bg-amber-50 px-4 py-2 text-xs text-amber-700">
  <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400"></span>
  <span>工作流执行中 -- Timeline 编辑已锁定</span>
</div>
```

`frontend/src/pages/WorkspacePage.vue:2103`（向下传递）:
```html
<Timeline ... :workflow-locked="wf.isActive.value" />
```

`frontend/src/components/workspace/Timeline.vue:49-51`（声明）:
```typescript
/** v2.1.0 Phase 4: pessimistic lock when workflow active (D-67) */
workflowLocked?: boolean
```

**全文件搜索 `workflowLocked` 的使用点**（排除声明）: 结果为空——`workflowLocked` 在 `Timeline.vue` 模板和 script 中**从未被读取**，没有任何 `v-if`、`:disabled`、`computed` 或 guard 引用它。该 prop 是一个纯粹的死参数。

**确认**: P4 准确。横幅是装饰性的，Timeline 的所有编辑控件（文本编辑、时间拖拽、状态切换）在工作流执行期间完全可用。规范删除横幅的决定正确；同时应删除 `Timeline.vue` 的 `workflowLocked` prop 声明和 WorkspacePage 的 `:workflow-locked` 传参（规范已包含此条，见 Timeline 改动 #1）。

---

### P5 — 沙箱模式复杂度不必要 ✅ **确认（设计层面）**

**规范声明**: 用户需要的是顺序执行多个功能，无需冲突检测和确认流程。

**审计意见**: 从产品语义看，P0/P1/P2 三项功能作用于不同维度（P0=删除建议、P1=文本修正、P2=精华标记），它们之间不存在真正的"冲突"——同一 segment 可以既有删除建议、又有文本修正、又被标记为精华，这是合法的叠加状态。沙箱模式引入的 `detect_conflicts`（segment-id 维度）实际只在"多个步骤都产生 segment 级 delete edit"时才有意义，而当前三个步骤中只有 P0 产生 delete edit，冲突检测几乎永不出触发。**复杂度与收益不匹配，确认删除合理。**

---

## 二、规范遗漏 / 边界细化

### B1. （关键）非沙箱方案的刷新机制已存在，规范未点明

**发现**: 规范第 56 行架构图描述"触发 EVENT_TASK_COMPLETED → 前端自动刷新 project 数据"，但未在改动清单或验证标准中说明这是**已存在的机制**（`WorkspacePage.vue:528-537`），容易让实现者误以为需要新增事件监听。

**建议**: 在规范的"核心设计变更"或"风险和注意事项"中补充一句：
> 前端 `WorkspacePage.vue:528-537` 已有对 `llm_smart_delete` / `llm_subtitle_correction` / `llm_highlight` 三类任务完成的 `project-updated` 刷新逻辑，工作流步骤通过 TaskManager 调度时天然复用该路径，无需新增刷新代码。

---

### B2. 死代码保留策略需要明确"清理时机"

**规范声明**（改动 #10-#13）: `_extract_edits_from_result` / `detect_conflicts` / `_save_snapshot` 等方法保留但不再调用，"暂不删除，避免 import 断裂"。

**审计意见**: 保留死代码本身可接受（降低本次 PR 风险），但需要明确：

1. **`_extract_edits_from_result` 实际无外部引用**: 全文件搜索确认它只被 `_run_steps`（`workflow_engine.py:595`）调用。移除该调用后，该方法成为纯死代码，**不存在 import 断裂风险**（它是类的实例方法，不是模块级 import）。规范"避免 import 断裂"的措辞不准确。

2. **`detect_conflicts` 被 `@expose` 暴露给前端**: 需确认 `main.py` 是否暴露了 `detect_conflicts` / `resolve_conflict`。若暴露，则前端 `useWorkflow.ts` 可能仍在调用——保留后端方法可避免前端 `call()` 报错，但应返回"已废弃"语义。**建议**: 这两个方法保留但返回空结果（如 `{"success": True, "data": {"conflicts": [], "total_conflicts": 0}}`），而非报错。

**核实**: `main.py:2655-2662` 仅暴露了 `apply_workflow` 和 `discard_workflow`，未暴露 `detect_conflicts` / `resolve_conflict`。因此这两个方法当前无前端调用入口，死代码保留无害，后续可安全清理。

---

### B3. `add_analysis_results` 的 `clear_existing` 行为对工作流的影响

**发现**: P2（highlight）handler 调用 `add_analysis_results(..., source="llm_highlight", clear_existing=True)`（`main.py:967-969`）。`clear_existing=True` 会**清除同类型（`llm_highlight`）的既有 AnalysisResult 及其关联 edits**（`project_service.py:1382-1395`）。

**对工作流的影响**: 在非沙箱串行模式下，如果工作流包含两个 highlight 步骤（或重试 highlight 步骤），后一次会清除前一次的结果。这是**合理的幂等行为**（重跑 P2 应替换而非叠加），但在"工作流中途失败后重试"场景下需注意：若 P2 成功写入后被重试（用户手动触发），旧结果被清除再重写——语义正确。

**结论**: 该行为无需修改，但规范"风险和注意事项 #1"提到重试可能产生重复 edits，此处需细化：**`clear_existing=True` 的步骤（highlight）不会产生重复，只有 `clear_existing=False` 的步骤（smart_delete）重试时会产生重复 edit**。

`main.py:782-783`（smart_delete）:
```python
if not task.payload.get("_workflow_accumulate"):
    store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_smart"))
```
`add_analysis_results` 默认 `clear_existing=False`（`project_service.py:1368` 签名），因此 smart_delete 重试会叠加。但 smart_delete handler 内部对 edit id 使用时间戳（`main.py:744, 756` `f"llm_smart_{_ts}_{i}"`），重试会产生新 id，不会 id 冲突，但会**产生重复的删除建议**（同一 segment 出现两条 delete edit）。这与单功能模式下重跑 smart_delete 的行为一致，非工作流引入的回归。

---

### B4. `_handle_smart_delete` 的 workflow 分支只保护 analysis 写入，不保护 edit 构造

**发现**: `main.py:741-766` 中，smart_delete 的 edits 列表**无论是否 workflow 模式都会构造**（第 747-765 行在 `if edits:` 块之外），只有第 782-785 行的 `add_analysis_results` 调用被 `_workflow_accumulate` 守卫。

这意味着沙箱模式下，edits 被构造并返回给 engine，engine 的 `_extract_edits_from_result` 能正确提取（与 subtitle_correction / highlight 不同）。因此 **smart_delete 在沙箱模式下数据不丢失**——它通过 `accumulated_edits` → `apply_workflow` 路径写入（前提是 P0 的 `current` 赋值崩溃被修复）。

**对规范的影响**: 规范"风险和注意事项 #5"称"smart_delete 的 workflow 分支不再触发，edits 正常写入 project"——这里的"正常写入"指**直接通过 `add_analysis_results` 写入**（非沙箱路径），而非通过 `apply_workflow`。表述正确，但需理解 smart_delete 是唯一一个在沙箱模式下也没丢数据的步骤（只是被 P0 崩溃挡住了 apply）。

---

### B5. `apply_workflow` / `discard_workflow` stub 的返回值契约

**规范声明**（#7, #8）: `apply_workflow` 简化为仅清理状态（不再写 project），保留方法避免前端调用出错。

**审计意见**: 需明确 stub 的返回值，因为前端 `useWorkflow.ts:293-301` 检查 `res.success` 并读取 `d.project`（`AIAssistantPanel.vue:221-222`）:

```typescript
// useWorkflow.ts
async function applyWorkflow() {
  const res = await call("apply_workflow")
  if (res.success) {
    isActive.value = false
    // ...
  }
  return res
}
// AIAssistantPanel.vue:218-222
const res = await wf.applyWorkflow()
if (res.success) {
  const d = res.data as { applied_count?: number; project?: Project }
  if (d.project) {
    emit("workflow-applied", d.project)
  }
}
```

**但**：规范前端改动 #1（删除"应用结果到项目"按钮）会移除 `handleApplyWorkflow` 及其对 `d.project` 的读取。因此只要前端改动同步落地，stub 返回 `{"success": True, "data": {"applied_count": 0}}` 即可，无需返回 project。

**建议**: stub 实现应返回成功且不抛异常，但**不应再读取 `self._active` 之外的任何状态**（避免并发问题）。推荐实现见第三节。

---

## 三、推荐的解决方案与代码实现

### 3.1 后端 `core/workflow_engine.py`

#### 改动 A: `_dispatch_step` 移除 workflow 标记（规范 #1, #2）

```python
# core/workflow_engine.py — _dispatch_step (约 658-674 行)
def _dispatch_step(self, snapshot: dict, step_index: int, step_def: dict) -> dict | None:
    """Dispatch a single step through TaskManager and wait for completion.

    Returns None if cancelled, otherwise the task result envelope.
    """
    instance_id = snapshot["workflow_instance_id"]
    step_type = step_def["type"]
    task_type_str = STEP_TO_TASK_TYPE[step_type].value

    # v2.2.0: 非沙箱模式 — 不再传入 _workflow_accumulate 等标记，
    # handler 走正常路径直接写 project（与单功能模式行为一致）。
    payload: dict[str, Any] = {
        "timeline_id": snapshot["timeline_id"],
    }

    # Apply preset if specified (D-43, D-45) — 保留
    preset_id = step_def.get("preset_id")
    if preset_id:
        payload["_workflow_preset_id"] = preset_id

    # ... 其余 create_task / 等待逻辑不变
```

**说明**: 移除 `_workflow_accumulate` / `_workflow_instance_id` / `_workflow_step_index` / `_workflow_step_type` 四个字段。`_workflow_preset_id` 保留，因为 handler 侧可能用它选择 prompt preset（需核实，见下方风险）。

> **待核实项**: 搜索 `_workflow_preset_id` 在 handler 中的使用——若 handler 不读取该字段，可一并移除；若读取，保留。

#### 改动 B: `_run_steps` 移除 edits 累积 / 冲突检测 / 快照保存（规范 #3-#7）

```python
# core/workflow_engine.py — _run_steps 完成分支 (约 613-642 行)
        # Execution finished -- determine outcome
        with self._lock:
            was_cancelled = self._cancel_event.is_set()
            self._current_task_id = None

        if was_cancelled:
            snapshot["status"] = "cancelled"
            self._emit(WORKFLOW_CANCELLED, {
                "workflow_instance_id": instance_id,
                "completed_steps": snapshot["current_step_index"],
                "total_steps": total,
            })
        else:
            snapshot["status"] = "completed"
            self._emit(WORKFLOW_COMPLETED, {
                "workflow_instance_id": instance_id,
                "workflow_name": snapshot["workflow_name"],
                # v2.2.0: 移除 total_edits / conflicts，仅保留步骤状态
                "step_results": snapshot["step_results"],
            })

        # v2.2.0: 完成后清理（规范 #6）
        instance_id = snapshot["workflow_instance_id"]
        self._delete_snapshot(instance_id)
        with self._lock:
            self._active = None
```

**步骤成功分支**（约 594-603 行）也需简化——移除 `_extract_edits_from_result` 调用和 `accumulated_edits` 累积：

```python
                # Step succeeded — v2.2.0: handler 已直接写 project，无需累积 edits
                snapshot["step_results"][step_index]["status"] = "completed"
                snapshot["current_step_index"] = step_index + 1

                with self._lock:
                    self._active = snapshot
                # 注：快照保存可保留（跨会话恢复进度用），也可移除（规范 #5）
                # 建议保留 _save_snapshot 以支持取消后的状态查询，但完成后由上方 _delete_snapshot 清理
                self._save_snapshot(snapshot)

                self._emit(WORKFLOW_STEP_COMPLETED, {
                    "workflow_instance_id": instance_id,
                    "step_index": step_index,
                    "step_type": step_type,
                    "step_name": step_name,
                    # v2.2.0: 移除 edits_count（不再累积）
                })
```

> **注意**: `step_results` 中原有 `edits_count` 字段（`workflow_engine.py:276` 初始化为 0）将恒为 0。前端若显示该字段需同步调整，或保留 0 值不显示。建议保留字段以兼容 `get_workflow_status` 的返回结构。

#### 改动 C: `apply_workflow` 简化为 stub（规范 #8）

```python
# core/workflow_engine.py — apply_workflow (约 846-931 行整体替换)
def apply_workflow(self) -> dict:
    """v2.2.0: 非沙箱模式下，步骤已直接写入 project，本方法仅清理状态。

    保留方法签名以兼容前端 call()，不再执行任何 project 写入。
    """
    with self._lock:
        snap = self._active
        if snap is None:
            # 已完成或无活跃工作流 — 视为成功（幂等）
            return {"success": True, "data": {"applied_count": 0}}
        instance_id = snap["workflow_instance_id"]
        self._active = None

    self._delete_snapshot(instance_id)
    logger.info("Workflow {} state cleared (non-sandbox mode)", instance_id)
    return {"success": True, "data": {"applied_count": 0}}
```

#### 改动 D: 保留的死代码方法

以下方法**保留不动**，但添加注释标记为 v2.2.0 后废弃，供后续清理：
- `_extract_edits_from_result`（实例方法，无 import 风险）
- `detect_conflicts` / `resolve_conflict`（未通过 `@expose` 暴露，无前端调用）
- `_save_snapshot` / `_load_snapshot` / `_delete_snapshot`（`_delete_snapshot` 仍在完成/取消路径使用，**不能删**；`_load_snapshot` 可保留供 `find_resumable_snapshots` 用）
- `_compute_segments_hash`（仅 `apply_workflow` 旧实现使用，随 apply 简化而废弃，但保留无害）

---

### 3.2 前端 `AIAssistantPanel.vue`

#### 改动 E: 删除 Apply/Discard 按钮，添加「返回配置」按钮（规范 #1-#3）

```vue
<!-- 替换原 434-444 行的 Apply/Discard 块 -->
<!-- v2.2.0: 完成状态视图 — 移除 Apply/Discard，改为「返回配置」 -->
<div v-if="!wf.isActive.value && wf.instanceId.value" class="flex flex-col gap-2">
  <div class="rounded-md bg-green-50 px-3 py-2 text-xs text-green-700">
    工作流已完成 — 结果已写入项目
  </div>
  <button
    class="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
    @click="handleReturnToConfig"
  >返回配置</button>
</div>
```

```typescript
// script 中新增
function handleReturnToConfig() {
  // 清除 instanceId，回到配置视图（v-else 分支）
  wf.instanceId.value = null
}
```

> **核实项**: `wf.instanceId` 是否是可写 ref。`useWorkflow.ts` 中 `instanceId` 应为 `ref<string | null>`，组件内直接赋值需确认其是否被 export。若不可写，应在 composable 中新增 `resetInstance()` 方法。

#### 改动 F: 移除 `handleApplyWorkflow` / `handleDiscardWorkflow` 及 `workflow-applied` emit

删除 `AIAssistantPanel.vue:218-222`（`handleApplyWorkflow`）和第 44 行的 `"workflow-applied"` emit 声明。

---

### 3.3 前端 `WorkspacePage.vue`

#### 改动 G: 删除工作流锁定 banner（规范 #1）

删除 `WorkspacePage.vue:2083-2089` 的整个 `<div v-if="wf.isActive.value" ...>` 块。

#### 改动 H: 删除 `:workflow-locked` 传参（规范配套）

`WorkspacePage.vue:2103` 移除 `:workflow-locked="wf.isActive.value"`。

#### 改动 I: 删除 `@workflow-applied` 处理（规范 #2）

`WorkspacePage.vue:2144` 移除 `@workflow-applied="(p: ...) => emit('project-updated', p ...)"`。

> **说明**: 非沙箱模式下，工作流步骤的 project 更新已由 `WorkspacePage.vue:528-537` 的 `EVENT_TASK_COMPLETED` 监听器处理（见 B1），无需 `workflow-applied` 透传。

---

### 3.4 前端 `Timeline.vue`

#### 改动 J: 删除 `workflowLocked` prop 和 `workflow-applied` emit（规范 #1, #2）

```typescript
// Timeline.vue:49-51 移除
- /** v2.1.0 Phase 4: pessimistic lock when workflow active (D-67) */
- workflowLocked?: boolean

// Timeline.vue:89 移除
- "workflow-applied": [project: Record<string, unknown>]

// Timeline.vue:407 移除
- @workflow-applied="(p) => emit('workflow-applied', p)"
```

---

### 3.5 前端 `useWorkflow.ts`

#### 改动 K: `applyWorkflow` 简化（规范 #1）

`applyWorkflow`（`useWorkflow.ts:293-302`）保持不变即可——它已经只调用 `call("apply_workflow")` 并清理本地状态，后端 stub 返回 `success: True` 后前端正常清理。**无需修改**，但建议移除对 `conflicts` / `showConflictView` 的清理（若这些 ref 已不使用）。

`discardWorkflow`（`useWorkflow.ts:304-313`）逻辑不变。

---

### 3.6 前端测试 `AIAssistantPanel.test.ts`

#### 改动 L: 更新测试用例（规范已列）

现有测试 `AIAssistantPanel.test.ts:190`（"shows apply/discard buttons after workflow completes"）需改为验证「返回配置」按钮。涉及 2 个用例更新（规范已注明）。

---

## 四、工作流完整运行逻辑（非沙箱模式）

改造后的完整执行流程：

```
用户在 AIAssistantPanel 配置步骤 → 点击「工作流启动」
  ↓
useWorkflow.startWorkflow(workflow_id, timeline_id)
  → call("start_workflow", workflow_id, timeline_id)
  ↓
main.py:start_workflow → WorkflowEngine.start_workflow
  1. 校验 workflow 定义、timeline 存在、LLM 配置
  2. _create_snapshot() — 创建 in-memory 进度跟踪 dict（不再含有效 accumulated_edits）
  3. self._active = snapshot
  4. emit(WORKFLOW_STARTED, {...})
  5. _start_heartbeat() — 心跳线程
  6. 启动后台线程执行 _run_steps(snapshot)
  ↓
_run_steps (后台线程) — 串行循环每个 step:
  for step_index in range(total):
    a. 检查取消标志 → 若取消则 break
    b. emit(WORKFLOW_STEP_STARTED, {status: "queued"})
    c. _dispatch_step():
       - 构造 payload = {"timeline_id": ...}（无 _workflow_accumulate）
       - task_manager.create_task(task_type_str, payload) → 拿到 task_id
       - emit(WORKFLOW_STEP_STARTED, {status: "running", task_id})
       - 轮询 task_manager.get_task(task_id) 直到 completed/failed/cancelled
         · 期间 emit(WORKFLOW_STEP_PROGRESS, {percent, message})
       - 返回 task result
    d. handler 执行（在 TaskManager 线程内）:
       · smart_delete: add_analysis_results(source="llm_smart") → 写 project.edits
       · subtitle_correction: store_subtitle_corrections() → 写 project.analysis
       · highlight: add_analysis_results(source="llm_highlight", clear_existing=True)
       · handler 返回 {..., "project": current_project.model_dump()}
    e. ★ task:completed 事件发出（TaskManager 层）
       → WorkspacePage.vue:528-537 监听器匹配 task_type
       → emit("project-updated", result.project)
       → 父组件刷新 project.value → SuggestionPanel / SubtitleCorrectionReview 实时更新
    f. 若失败: emit(WORKFLOW_STEP_FAILED) → _wait_for_failure_action() → 重试/跳过/中止
    g. 若成功: snapshot.step_results[i].status = "completed"; _save_snapshot
       emit(WORKFLOW_STEP_COMPLETED)
  ↓
全部完成:
  emit(WORKFLOW_COMPLETED, {step_results})
  _delete_snapshot(instance_id); self._active = None
  ↓
前端 useWorkflow 收到 WORKFLOW_COMPLETED → instanceId 保留（显示完成视图）
  → AIAssistantPanel 显示「工作流已完成 — 结果已写入项目」+「返回配置」
  → 用户点击「返回配置」→ instanceId = null → 回到配置视图
```

### 文件变动规则汇总

| 文件 | 变动类型 | 行数估计 | 关键改动 |
|------|----------|----------|----------|
| `core/workflow_engine.py` | 修改 | ~40 行 | `_dispatch_step` 去标记；`_run_steps` 去累积/冲突；`apply_workflow` 转 stub；完成分支清理 snapshot |
| `main.py` | **不改** | 0 | handler 中的 `_workflow_accumulate` 分支成为死代码（规范明确不清理，留待后续） |
| `frontend/.../AIAssistantPanel.vue` | 修改 | ~20 行 | 删 Apply/Discard 按钮 + handler + emit；加「返回配置」按钮 + handler |
| `frontend/.../AIAssistantPanel.test.ts` | 修改 | ~15 行 | 更新 2 个用例 |
| `frontend/.../Timeline.vue` | 删除 | ~5 行 | 删 `workflowLocked` prop + `workflow-applied` emit + 透传 |
| `frontend/.../WorkspacePage.vue` | 删除 | ~10 行 | 删锁横幅 + `:workflow-locked` + `@workflow-applied` |
| `frontend/.../useWorkflow.ts` | 可选 | 0-3 行 | 基本不变；可选清理 `conflicts`/`showConflictView` |

**总改动**: 约 90 行（规范预估 ~50 行 backend + ~26 行 frontend = ~76 行，基本吻合）。

---

## 五、验证标准补充

规范的验证标准（第 139-150 行）基本完备，补充以下两条：

- [ ] **新增**: 工作流步骤完成后，无需点击任何按钮，SuggestionPanel / SubtitleCorrectionReview 即自动显示最新结果（验证 `task:completed` → `project-updated` 路径生效）
- [ ] **新增**: 工作流执行中直接编辑 Timeline（文本/时间/状态），操作正常生效且不报错（验证锁横幅删除后无副作用）

---

## 六、审计结论

| 维度 | 评价 |
|------|------|
| **诊断准确性** | P0/P2/P3/P4/P5 准确；P1 根因描述有误（前端刷新机制已存在），但不影响方案 |
| **方案可行性** | ✅ 高。非沙箱化是正确方向，且现有 `task:completed` 刷新路径天然支持 |
| **改动清单完整性** | ✅ 基本完整，覆盖所有受影响文件。建议明确 stub 返回值和死代码保留策略 |
| **风险评估** | ✅ 合理。重试重复 edit 风险存在但与单功能模式一致，非回归 |
| **遗漏项** | B1（刷新机制已存在）需补入规范说明；B5（stub 返回值）需明确 |

**建议**: 采纳规范方案，按本审计的边界细化（B1-B5）补充规范说明后实施。预估工程量 2-3 天准确。

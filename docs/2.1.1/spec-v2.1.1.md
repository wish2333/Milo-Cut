# v2.1.1 修复与交互增强 -- 实施规格说明

> **版本**: 2.1.1
> **基准**: v2.1.0 (`dev-2.1.0` 分支)
> **分支**: `dev-2.1.1`
> **规格文档**: `docs/2.1.1/spec-v2.1.1.md`
> **来源**: v2.1.0 手动检查清单 (QA) 发现的问题 + 用户反馈

---

## 概要

v2.1.0 发布后手动检查发现多项问题，涵盖崩溃 bug、性能瓶颈、交互缺失三大类。本版本一次性修复全部问题，分 5 个模块实施。

### 问题分类

| 类别 | 数量 | 严重程度 |
|------|------|---------|
| P0 崩溃 bug | 2 | 阻断核心功能 |
| 性能与配置 | 2 | 严重影响可用性 |
| 交互缺失 | 4 | 功能无法通过 GUI 使用 |
| 文档修正 | 1 | 检查清单与实际不符 |

### 模块划分

| 模块 | 内容 | 预估改动 |
|------|------|---------|
| M1: P0 bug 修复 | Analysis 崩溃 + 取消状态错误 | 后端 3 文件 |
| M2: LLM 参数可配置 | 窗口/批次/上下文/并发数 + Settings UI | 后端 2 文件 + 前端 2 文件 |
| M3: LLM chunk 级并发 | smart_delete/correction 并发调用 | 后端 1 文件 |
| M4: 字幕交互增强 | 多选模式 + 时间微调 + 合并/分割 + 搜索入口 + Timeline 重命名 | 前端 6 文件 |
| M5: 文档修正 | 检查清单 + record 更新 | 文档 2 文件 |

---

## M1: P0 Bug 修复

### M1-1: Analysis 功能崩溃 (filler/error/full_analysis)

**现象**: 运行「填充词检测」「错误触发词检测」「综合分析」任一功能，任务立即 FAILED，报错：
```
AttributeError: 'Project' object has no attribute 'transcript'
```

**根因**: v2.0.0 多 Timeline 重构后 `Project` 模型不再直接持有 `transcript`，改为通过 `active_timeline.transcript` 访问。但以下三个 handler 遗漏未改：

| 文件 | 行号 | 错误代码 |
|------|------|---------|
| `main.py` | 366 | `self._project.current.transcript.segments` (_handle_filler_detection) |
| `main.py` | 379 | `self._project.current.transcript.segments` (_handle_error_detection) |
| `main.py` | 401 | `project.transcript.segments` (_handle_full_analysis else 分支) |

**修复方案**: 统一改为通过 active_timeline 访问。

`_handle_filler_detection` / `_handle_error_detection`:
```python
# Before:
segments = list(self._project.current.transcript.segments)

# After:
project = self._project.current
timeline_id = task.payload.get("timeline_id", "")
if timeline_id:
    timeline = project.get_timeline(timeline_id)
    if timeline is None:
        raise ValueError(f"Timeline {timeline_id} not found")
else:
    timeline = project.get_timeline(project.active_timeline_id)
    if timeline is None:
        raise ValueError("No active timeline")
segments = list(timeline.transcript.segments)
```

`_handle_full_analysis` 的 else 分支 (line 401): 复用已有的 if 分支逻辑 (`timeline.transcript.segments`)，删除 else 分支的 `project.transcript.segments`。当 payload 无 timeline_id 时，回退到 `project.active_timeline_id`。

**测试**: `tests/test_analysis_handlers.py` 新增 3 个测试，验证每个 handler 从 active timeline 正确读取 segments。

### M1-2: 取消任务报错 + 状态错误

**现象**: 点击单功能模式「取消」按钮后：
1. toast 立即弹出「已取消」，但任务实际还要等当前 HTTP 请求返回
2. 后端日志打出 `ERROR | Task xxx failed` + `RuntimeError: Cancelled` 完整堆栈
3. 任务状态被标记为 FAILED 而非 CANCELLED

**根因**:

1. **task_manager 不区分取消和失败**: `_execute_task` (task_manager.py:283) 的 except 分支统一标记 FAILED + emit TASK_FAILED。LLM handler 收到 cancel_event 后 `raise RuntimeError("Cancelled")`，被当作普通异常处理。

2. **call_llm 无法中断 HTTP**: OpenAI SDK 的 `client.chat.completions.create()` 是同步阻塞调用，一旦请求发出，cancel_event 只能在下一个 chunk 边界被检查到。并发模式下同样，已提交到线程池的 HTTP 请求无法从外部中断。

**修复方案**:

#### M1-2a: task_manager 区分取消异常

`core/task_manager.py` `_execute_task` except 分支:

```python
except Exception as e:
    # Distinguish cancellation from real failure
    is_cancelled = (
        isinstance(e, RuntimeError) and str(e) == "Cancelled"
    ) or (
        cancel_event.is_set()
    )

    if is_cancelled:
        with self._lock:
            current = self._tasks.get(task_id)
            if current:
                self._tasks[task_id] = current.model_copy(
                    update={
                        "status": TaskStatus.CANCELLED,
                        "completed_at": datetime.now().isoformat(),
                    }
                )
        # No TASK_FAILED event for cancellation -- emit a dedicated one
        self._emit(TASK_CANCELLED, {"task_id": task_id})
    else:
        logger.exception("Task {} failed", task_id)
        with self._lock:
            current = self._tasks.get(task_id)
            if current:
                self._tasks[task_id] = current.model_copy(
                    update={
                        "status": TaskStatus.FAILED,
                        "error": str(e),
                        "completed_at": datetime.now().isoformat(),
                    }
                )
        self._emit(TASK_FAILED, {"task_id": task_id, "error": str(e)})
```

新增事件常量 `TASK_CANCELLED` 到 `core/events.py`，同步到 `frontend/src/utils/events.ts`。

#### M1-2b: call_llm 取消时短超时截断

`call_llm` 在发起请求前检查 cancel_event；在 catch 块中也检查。对于并发模式（M3），使用 daemon 线程 + 不 join 策略：cancel_event 设置后，主任务立即返回 CANCELLED，后台线程的响应被丢弃。

call_llm 内部不变（同步调用），但在 `analyze_smart_delete` / `analyze_subtitle_correction` 的并发循环中，cancel 后立即 `executor.shutdown(wait=False)` 并 return，不等已提交任务。

#### M1-2c: 前端 toast 文案调整

取消按钮点击后 toast 改为「取消中...」，监听 `TASK_CANCELLED` 事件后再弹「已取消」。避免用户以为已经取消但任务还在跑。

**测试**: `tests/test_task_cancel.py` 新增：
- 取消 queued 任务 → 状态 CANCELLED，不 emit TASK_FAILED
- 取消 running 任务 → cancel_event set → handler raise Cancelled → 状态 CANCELLED
- 正常失败 → 状态 FAILED，emit TASK_FAILED

---

## M2: LLM 参数可配置

### 新增 settings.json 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `llm_smart_window_duration` | float | 60.0 | 智能删除窗口时长 (秒) |
| `llm_smart_overlap_duration` | float | 10.0 | 智能删除窗口重叠 (秒) |
| `llm_correction_batch_size` | int | 30 | 字幕修正每批目标条数 |
| `llm_correction_context_window` | int | 5 | 字幕修正上下文窗口 (前后各 N 条) |
| `llm_highlight_chunk_duration` | float | 1800.0 | 精华提取窗口时长 (秒) |
| `llm_highlight_overlap_duration` | float | 60.0 | 精华提取窗口重叠 (秒) |
| `llm_concurrency` | int | 5 | LLM 调用并发数 |

### 参数传递链路

```
settings.json
  → core/config.py load_settings() (_DEFAULT_SETTINGS 新增 7 字段)
  → core/llm_service.py get_llm_config() 读取参数
  → analyze_smart_delete / analyze_subtitle_correction / analyze_highlight 使用参数
```

### llm_service.py 改动

#### analyze_smart_delete

```python
# Before:
chunks = chunk_transcript_short(to_analyze)

# After:
settings = load_settings()
window = float(settings.get("llm_smart_window_duration", 60.0))
overlap = float(settings.get("llm_smart_overlap_duration", 10.0))
chunks = chunk_transcript(to_analyze, chunk_duration=window, overlap_duration=overlap)
```

不再调用 `chunk_transcript_short` (保留函数但标记 deprecated)。

#### analyze_subtitle_correction

```python
# Before:
batch_size = 20
...
context_window = 3

# After:
settings = load_settings()
batch_size = int(settings.get("llm_correction_batch_size", 30))
...
context_window = int(settings.get("llm_correction_context_window", 5))
```

#### analyze_highlight

```python
# Before:
chunks = chunk_transcript(segments, chunk_duration=1800.0, overlap_duration=60.0)

# After:
settings = load_settings()
chunk_dur = float(settings.get("llm_highlight_chunk_duration", 1800.0))
overlap_dur = float(settings.get("llm_highlight_overlap_duration", 60.0))
chunks = chunk_transcript(segments, chunk_duration=chunk_dur, overlap_duration=overlap_dur)
```

### Settings UI

`SettingsModal.vue` LLM Tab 新增「高级参数」折叠区 (默认折叠)，包含：

```
[高级参数] ▶  (点击展开)
┌─────────────────────────────────────────────────┐
│  智能删除窗口 (秒)    [60.0    ]               │
│  智能删除重叠 (秒)    [10.0    ]               │
│  字幕修正批次大小      [30      ]               │
│  字幕修正上下文窗口    [5       ]               │
│  精华提取窗口 (秒)    [1800.0  ]               │
│  精华提取重叠 (秒)    [60.0    ]               │
│  LLM 并发数           [5       ]               │
│                                                 │
│  ℹ 较大窗口减少 API 调用次数但单次耗时更长。   │
│    并发数过高可能触发 API 限流。               │
└─────────────────────────────────────────────────┘
```

- 每个字段 `<input type="number">`，change 时调用 `update_settings` 保存
- 底部说明文字用 `text-xs text-gray-400`
- 折叠状态用 `<details>` 或 v-if 控制

### 默认值变更对照

| 参数 | v2.1.0 默认 | v2.1.1 默认 | 变化 |
|------|------------|------------|------|
| smart_delete 窗口 | 25s | 60s | 2.4x，窗口更大，块数更少 |
| smart_delete 重叠 | 5s | 10s | 更大重叠，减少边界遗漏 |
| correction batch | 20 条 | 30 条 | 1.5x，减少调用次数 |
| correction context | 3 条 | 5 条 | 更多上下文，修正质量提升 |
| highlight 窗口 | 1800s | 1800s | 不变 |
| highlight 重叠 | 60s | 60s | 不变 |
| 并发数 | 1 (串行) | 5 | 新增并发 |

### smart_delete 块数变化预估

以 15 分钟视频 (111 段) 为例：
- **v2.1.0** (25s/5s overlap): 约 50-60 块，串行 5-10 分钟
- **v2.1.1** (60s/10s overlap + 并发 5): 约 18-20 块，并发后 36-80 秒

---

## M3: LLM Chunk 级并发

### 适用范围

| 功能 | 并发 | 原因 |
|------|------|------|
| smart_delete | **是** | 20+ 个独立窗口，串行是主要瓶颈 |
| subtitle_correction | **是** | 4-6 个独立批次，串行 3-6 分钟 |
| highlight | **否** | 通常仅 1 块，无需并发 |
| semantic_search | **否** | 单次调用，无循环 |

### 实现方案 -- ThreadPoolExecutor + 顺序合并

`core/llm_service.py` `analyze_smart_delete` 和 `analyze_subtitle_correction` 的串行 for 循环改为并发。

#### analyze_smart_delete 改造

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def analyze_smart_delete(...):
    ...
    chunks = chunk_transcript(to_analyze, chunk_duration=window, overlap_duration=overlap)
    total_chunks = len(chunks)
    concurrency = int(settings.get("llm_concurrency", 5))

    # 并发调用 LLM，每个 chunk 独立
    results_by_index: dict[int, list[dict]] = {}

    def _process_chunk(idx: int, chunk: list[dict]) -> tuple[int, list[dict] | None, dict]:
        """Process a single chunk. Returns (index, normalized_results, usage)."""
        if cancel_event and cancel_event.is_set():
            return (idx, None, {})
        prompt = _build_structured_user_message(chunk)
        result = call_llm(prompt, system=effective_system, json_mode=True,
                          config=config, cancel_event=cancel_event)
        if not result.get("success"):
            logger.warning(f"Smart-delete window {idx + 1} failed: {result.get('error')}")
            return (idx, None, {})
        content = result["data"]["content"]
        usage = result["data"].get("usage", {})
        chunk_results = _parse_json_response_layers(content)
        if not chunk_results:
            return (idx, None, usage)
        normalized = [_normalize_smart_delete_item(item) for item in chunk_results]
        normalized = [n for n in normalized if n]
        return (idx, normalized, usage)

    all_results: list[dict] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all chunks
        futures = {
            executor.submit(_process_chunk, idx, chunk): idx
            for idx, chunk in enumerate(chunks)
        }
        completed = 0

        for future in as_completed(futures):
            # Check cancellation
            if cancel_event and cancel_event.is_set():
                # Don't wait for remaining futures -- discard
                executor.shutdown(wait=False, cancel_futures=True)
                return {"success": False, "error": "Cancelled"}

            idx, normalized, usage = future.result()
            completed += 1

            # Accumulate usage
            for key in total_usage:
                total_usage[key] += usage.get(key, 0)

            if normalized:
                results_by_index[idx] = normalized
                # Live update via chunk_callback
                if chunk_callback:
                    chunk_callback(normalized)

            # Progress
            if progress_cb:
                pct = (completed / total_chunks) * 100 if total_chunks > 0 else 0
                progress_cb(pct, f"Smart-delete window {completed}/{total_chunks}...")

    # Merge results in original chunk order
    for idx in range(total_chunks):
        if idx in results_by_index:
            all_results.extend(results_by_index[idx])

    # Deduplicate by segment_id (keep last occurrence)
    seen: dict[str, dict] = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())
    ...
```

#### analyze_subtitle_correction 改造

同样模式：`_process_batch(idx, batch_segments)` → ThreadPoolExecutor → 按原始 batch 顺序合并。

#### 取消行为

1. 用户点击取消 → `cancel_event.set()`
2. 主循环检测到 cancel → `executor.shutdown(wait=False, cancel_futures=True)`
   - `cancel_futures=True` (Python 3.9+): 取消未开始的任务
   - `wait=False`: 不等已运行的线程，立即返回
3. 已运行的 HTTP 请求在后台 daemon 线程中完成，响应被丢弃
4. 函数立即 return `{"success": False, "error": "Cancelled"}`
5. task_manager 标记任务为 CANCELLED (M1-2a)

#### 进度条行为

并发模式下进度条按 completed/total_chunks 计算，不再线性递增。chunk_callback 实时推送已完成窗口的结果到前端，但结果按原始顺序合并。

#### chunk 内部异常隔离

单个 chunk 的 LLM 调用失败 (timeout / parse error) 不影响其他 chunk。失败的 chunk 返回 None，跳过该窗口的结果，日志记录 warning。

### 线程安全分析

| 共享资源 | 访问方式 | 安全性 |
|---------|---------|--------|
| `config` (LlmConfig) | 只读传递 | 安全 (Pydantic frozen model) |
| `cancel_event` | 只读 .is_set() | 安全 (threading.Event 线程安全) |
| `total_usage` dict | 主线程聚合 (future.result() 后) | 安全 (单线程写入) |
| `results_by_index` dict | 主线程聚合 | 安全 |
| OpenAI client | 每个 chunk 独立调用 | 需确认 client 是否线程安全 |

> **OpenAI client 线程安全**: 官方 openai-python SDK 的 `OpenAI` client 实例是线程安全的 (内部使用 httpx 连接池)。复用同一 client 实例并发调用 `chat.completions.create()` 是支持的。

### 测试

`tests/test_llm_concurrency.py`:
- mock call_llm，验证多 chunk 并发后结果按原始顺序合并
- 验证取消后 executor.shutdown(wait=False) 立即返回
- 验证单 chunk 失败不影响其他 chunk
- 验证 chunk_callback 按完成顺序回调 (非原始顺序)

---

## M4: 字幕交互增强

### M4-1: 字幕多选模式

#### 交互设计

工具栏新增「选择模式」按钮 (checkbox 图标)。点击切换：
- **播放模式 (默认)**: 点击字幕段 = seek 跳转播放 (现有行为不变)
- **选择模式**: 点击字幕段 = 选中/取消选中 (蓝色高亮 ring-2)，不触发 seek

选择模式下额外支持：
- **Ctrl/Cmd + 点击**: 切换单个段的选中状态
- **Shift + 点击**: 范围选 -- 从上次选中的段到当前段全部选中
- **ESC**: 清空选区并退出选择模式
- **Enter**: 合并选中段 (需选中 ≥ 2 段)
- **Delete**: 批量标记选中段为删除 (非直接删除，走 toggle-status)

#### 状态管理

`useSegmentEdit.ts` 新增：

```typescript
// 选择模式状态
const selectionMode = ref(false)
const selectedSegmentIds = ref<Set<string>>(new Set())
const lastSelectedId = ref<string | null>(null)  // for Shift range

function toggleSelectionMode() {
  selectionMode.value = !selectionMode.value
  if (!selectionMode.value) {
    selectedSegmentIds.value.clear()
    lastSelectedId.value = null
  }
}

function handleSegmentClick(segId: string, event: MouseEvent) {
  if (!selectionMode.value) {
    // 播放模式: seek (现有行为)
    return
  }
  if (event.ctrlKey || event.metaKey) {
    // Ctrl: toggle single
    if (selectedSegmentIds.value.has(segId)) {
      selectedSegmentIds.value.delete(segId)
    } else {
      selectedSegmentIds.value.add(segId)
    }
  } else if (event.shiftKey && lastSelectedId.value) {
    // Shift: range select
    const segIds = activeTranscriptSegments(project.value).map(s => s.id)
    const startIdx = segIds.indexOf(lastSelectedId.value)
    const endIdx = segIds.indexOf(segId)
    if (startIdx >= 0 && endIdx >= 0) {
      const [from, to] = [Math.min(startIdx, endIdx), Math.max(startIdx, endIdx)]
      for (let i = from; i <= to; i++) {
        selectedSegmentIds.value.add(segIds[i])
      }
    }
  } else {
    // Plain click in selection mode: toggle
    if (selectedSegmentIds.value.has(segId)) {
      selectedSegmentIds.value.delete(segId)
    } else {
      selectedSegmentIds.value.add(segId)
    }
  }
  lastSelectedId.value = segId
}
```

#### UI 改动

**Timeline.vue** 工具栏区域:

```vue
<button
  class="rounded p-1.5 text-xs transition-colors"
  :class="selectionMode ? 'bg-blue-100 text-blue-700' : 'text-gray-500 hover:bg-gray-100'"
  @click="emit('toggle-selection-mode')"
  title="选择模式 (框选字幕)"
>
  <!-- checkbox SVG icon -->
</button>

<!-- 选中计数 (选择模式 + 有选中时显示) -->
<span v-if="selectionMode && selectedCount > 0" class="text-xs text-blue-600">
  已选 {{ selectedCount }} 段
</span>

<!-- 合并按钮 (选中 ≥ 2 时可用) -->
<button
  v-if="selectionMode && selectedCount >= 2"
  class="rounded bg-blue-500 px-2 py-1 text-xs text-white hover:bg-blue-600"
  @click="emit('merge-selected')"
>
  合并选中
</button>
```

**TranscriptRow.vue**:

```vue
<div
  ...
  @click="handleClick"
>
  <!-- 选中指示 (选择模式) -->
  <div
    v-if="isSelected"
    class="absolute left-0 top-0 bottom-0 w-1 bg-blue-500"
  ></div>
</div>

<script>
// 选中状态用 ring-2 ring-blue-500 替代现有的 ring-1
const isSelected = computed(() =>
  props.selectionMode && props.selectedSegmentIds?.has(props.segment.id)
)
</script>
```

#### right-click menu 自适应

选择模式下右键菜单根据选中数量变化：

| 选中数 | 菜单项 |
|--------|--------|
| 0 段 | (不弹菜单) |
| 1 段 | 编辑文本 / 标记删除 / 分割 / 删除段落 |
| ≥ 2 段 | 合并选中 / 批量标记删除 / 取消选中 |

### M4-2: 时间微调 (±0.1s 按钮 + 键盘)

#### TranscriptRow.vue 时间列改造

现有: 点击时间数字 → 变输入框 → 手动输入

新增: 时间数字旁加 ±0.1s 按钮，输入框支持方向键微调。

```vue
<template v-if="editingTimeField === 'start'">
  <div class="flex items-center gap-0.5">
    <button
      class="text-[10px] text-gray-400 hover:text-blue-500 px-0.5"
      @click.stop="adjustTime('start', -0.1)"
    >−</button>
    <input
      ref="timeInputRef"
      v-model="editingTimeValue"
      class="w-[55px] ..."
      @keydown="handleTimeEditKeydown"
      @blur="applyTimeEdit"
      @click.stop
    />
    <button
      class="text-[10px] text-gray-400 hover:text-blue-500 px-0.5"
      @click.stop="adjustTime('start', 0.1)"
    >+</button>
  </div>
</template>
```

```typescript
function adjustTime(field: "start" | "end", delta: number) {
  const current = parseFloat(editingTimeValue.value) || 0
  editingTimeValue.value = (current + delta).toFixed(1)
  applyTimeEdit()
}

// handleTimeEditKeydown 新增:
function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "ArrowUp") {
    e.preventDefault()
    adjustTime(editingTimeField.value!, 0.1)
  } else if (e.key === "ArrowDown") {
    e.preventDefault()
    adjustTime(editingTimeField.value!, -0.1)
  } else if (e.key === "Enter") {
    applyTimeEdit()
  } else if (e.key === "Escape") {
    cancelTimeEdit()
  }
}
```

- ±0.1s 按钮仅在编辑时间时显示 (跟输入框一起出现)
- 方向键 ↑ +0.1s，↓ -0.1s
- 按住 Shift + 方向键 = ±1.0s (大步长)

### M4-3: 合并 / 分割字幕 UI

#### 合并 (接 M4-1 选择模式)

后端 API `merge_segments(segment_ids)` 已存在。新增前端调用链路：

```
Timeline.vue emit("merge-selected")
  → WorkspacePage.vue handleMergeSelected()
  → useEdit.ts mergeSegments(Array.from(selectedSegmentIds.value))
  → call("merge_segments", segmentIds)
```

合并后清空选区，刷新段列表。

#### 分割 (右键菜单)

后端 API `split_segment(segment_id, position)` 已存在。右键菜单新增「分割」项：

```
TranscriptRow.vue context menu:
  编辑文本
  标记删除 / 取消删除
  ──────────
  分割 (从此段中间分为两段)   ← 新增
  ──────────
  删除段落
```

行为：
1. 点击「分割」→ 取该段 `(start + end) / 2` 作为分割点
2. 调用 `split_segment(segment_id, midpoint)`
3. 后端将原段分为两段，分割点前后各保留原文本
4. 前端刷新后，用户可点击时间数字 ±0.1s 微调分割点

```typescript
// WorkspacePage.vue
function handleSplitSegment(segmentId: string) {
  const seg = activeTranscriptSegments(project.value).find(s => s.id === segmentId)
  if (!seg) return
  const midpoint = (seg.start + seg.end) / 2
  splitSegment(segmentId, midpoint)
}
```

### M4-4: 搜索替换可见入口

现有: SearchReplaceBar 组件存在，但无可见入口，仅 Ctrl+F 触发。

改造: 工具栏新增搜索图标按钮。

```vue
<!-- Timeline.vue 工具栏 -->
<button
  class="rounded p-1.5 text-gray-500 hover:bg-gray-100 transition-colors"
  :class="{ 'bg-blue-100 text-blue-700': showSearchBar }"
  @click="showSearchBar = !showSearchBar"
  title="搜索替换 (Ctrl+F)"
>
  <!-- magnifying-glass SVG icon -->
</button>
```

- 点击展开/收起 SearchReplaceBar (v-show)
- Ctrl+F 快捷键保留，同时切换 showSearchBar 状态
- SearchReplaceBar 展开时自动聚焦输入框

### M4-5: Timeline 右键重命名

后端 API `rename_timeline(timeline_id, new_label)` 已存在。前端无入口。

改造: Timeline 标签右键菜单新增「重命名」。

```vue
<!-- Timeline 标签区域 (Timeline.vue 或 WorkspacePage.vue) -->
<div
  v-for="tl in timelines"
  @contextmenu="onTimelineContextMenu($event, tl.id)"
>
  {{ tl.label }}
</div>

<!-- 右键菜单 -->
<Teleport to="body">
  <div v-if="timelineContextMenu" ...>
    <button @click="activateTimeline(timelineContextMenu.id)">切换到此 Timeline</button>
    <button @click="startRenameTimeline(timelineContextMenu.id)">重命名</button>
    <hr />
    <button @click="deleteTimeline(timelineContextMenu.id)" class="text-red-600">删除</button>
  </div>
</Teleport>

<!-- 重命名: 内联编辑 -->
<div v-if="renamingTimelineId === tl.id">
  <input
    v-model="renameValue"
    @keydown.enter="confirmRename"
    @keydown.escape="cancelRename"
    @blur="confirmRename"
    class="..."
  />
</div>
<div v-else>{{ tl.label }}</div>
```

---

## M5: 文档修正

### M5-1: 检查清单修正

`docs/2.1.0/qa-checklist-2.1.0.md` 以下项标注为「后端已实现，前端无 UI」或更新预期：

| 检查项 | 修正 |
|--------|------|
| A-2.3 合并字幕 | 标注「v2.1.1 补 UI」+ 添加选择模式前置说明 |
| A-2.4 分割字幕 | 标注「v2.1.1 补 UI」+ 右键菜单分割说明 |
| A-2.6 搜索替换 | 更新为「工具栏搜索图标 + Ctrl+F 双入口」|
| A-4.2 重命名 Timeline | 标注「v2.1.1 补 UI」|
| A-4.3 复制 Timeline | 标注「后端有 API，前端仅新建时拷贝」|
| C-1 智能删除 | 更新预期耗时 (并发后 1-2 分钟) |
| C-5 取消功能 | 更新预期行为 (立即取消 + 不报错) |

### M5-2: record 更新

新增 `docs/2.1.1/record-2.1.1.md`，记录全部修复内容。

---

## 决策映射

| 决策 ID | 决策 | 理由 |
|---------|------|------|
| D-301 | Analysis handler 统一走 active_timeline | v2.0.0 多 Timeline 重构遗漏修复 |
| D-302 | task_manager 区分 Cancelled 异常 | 取消不应报错，用户不需要看到异常堆栈 |
| D-303 | 取消用 daemon 线程 + 丢弃响应 | OpenAI SDK 无法中断 HTTP，不等最干净 |
| D-304 | 7 个 LLM 参数存 settings.json | 用户可调，全局生效 |
| D-305 | smart_delete 窗口 25s→60s | 减少块数，配合并发大幅提速 |
| D-306 | correction batch 20→30 / context 3→5 | 提升单次调用质量，减少调用次数 |
| D-307 | highlight 不并发 | 通常仅 1 块，并发无意义 |
| D-308 | 全局统一并发数=5 | 简化配置，用户只调一个值 |
| D-309 | 并发结果按原始顺序合并 | 保持结果一致性 |
| D-310 | 选择模式用显式按钮 | 不改变默认点击=播放的习惯 |
| D-311 | 分割默认从中间分 | 用户用 ±0.1s 微调 |
| D-312 | Timeline 右键加重命名 | rename API 已存在，补 UI 入口 |
| D-313 | 清除操作后 toast 提示 | 不自动重跑，用户手动决定 |

---

## 变更文件清单

### 后端 (6 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `main.py` | M1 | _handle_filler_detection / _handle_error_detection / _handle_full_analysis 改为 active_timeline |
| `core/task_manager.py` | M1 | _execute_task 区分 Cancelled / FAILED |
| `core/events.py` | M1 | 新增 TASK_CANCELLED 事件常量 |
| `core/config.py` | M2 | _DEFAULT_SETTINGS 新增 7 个 LLM 参数字段 |
| `core/llm_service.py` | M2+M3 | 3 个 analyze 函数读取参数 + smart_delete/correction 改 ThreadPoolExecutor |
| `frontend/src/utils/events.ts` | M1 | 同步 TASK_CANCELLED 事件 |

### 前端 (8 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | M2 | LLM Tab 新增「高级参数」折叠区 |
| `frontend/src/composables/useSegmentEdit.ts` | M4 | 新增 selectionMode / selectedSegmentIds / handleSegmentClick |
| `frontend/src/components/workspace/TranscriptRow.vue` | M4 | 选择模式样式 + ±0.1s 按钮 + 右键菜单分割 + 键盘微调 |
| `frontend/src/components/workspace/Timeline.vue` | M4 | 选择模式按钮 + 搜索图标 + 合并按钮 + Timeline 右键菜单 |
| `frontend/src/pages/WorkspacePage.vue` | M4 | handleMergeSelected / handleSplitSegment / 搜索入口 / Timeline 重命名 |
| `frontend/src/composables/useEdit.ts` | M4 | mergeSegments / splitSegment 接入 |
| `frontend/src/types/edit.ts` | M2 | 新增 7 个 settings 字段到 TS 类型 |
| `frontend/src/types/api.ts` | M4 | 确认 merge_segments/split_segment/rename_timeline 方法签名 |

### 测试 (5 文件)

| 文件 | 模块 | 内容 |
|------|------|------|
| `tests/test_analysis_handlers.py` | M1 | 3 个 handler 从 active timeline 读取 |
| `tests/test_task_cancel.py` | M1 | 取消状态正确 (CANCELLED 非 FAILED) |
| `tests/test_llm_concurrency.py` | M3 | 并发结果顺序合并 + 取消 + 单块失败隔离 |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | M4 | 选择模式 + ±0.1s 按钮 |
| `frontend/src/components/workspace/Timeline.test.ts` | M4 | 选择模式切换 + 搜索入口 |

### 文档 (3 文件)

| 文件 | 模块 | 内容 |
|------|------|------|
| `docs/2.1.1/spec-v2.1.1.md` | — | 本文档 |
| `docs/2.1.1/record-2.1.1.md` | M5 | 实施记录 |
| `docs/2.1.0/qa-checklist-2.1.0.md` | M5 | 修正检查项标注 |

---

## 测试基线 (预期)

| 类别 | 数量 | 说明 |
|------|------|------|
| 后端单元测试 | ~325 (+6) | 含 test_analysis_handlers 3 + test_task_cancel 3 |
| 后端集成测试 | 35 | 不变 |
| 前端测试 | ~180 (+11) | 含 TranscriptRow / Timeline / useSegmentEdit 新增 |
| ruff | 零错误 | |
| ESLint | 零错误 | |

---

## 实施顺序

```
M1 (P0 bug) → M2 (参数) → M3 (并发，依赖 M2 参数) → M4 (交互) → M5 (文档)
```

M1 必须最先完成 (阻断核心功能)。M2 先于 M3 (并发数参数在 M2 定义)。M4 独立于 M1-M3，可并行。M5 最后。

---

## 附录 A: M1 当前运行逻辑与代码

### A-1: Analysis Handler 的 segment 读取 (当前 bug 代码)

三个规则分析 handler 当前通过 `self._project.current.transcript.segments` 读取字幕段。v2.0.0 多 Timeline 重构后 `Project` 模型已无 `transcript` 属性，改为 `timelines[].transcript`。

**当前代码** (`main.py:361-412`):

```python
# _handle_filler_detection (line 361-372)
def _handle_filler_detection(self, task, cancel_event, progress_cb):
    if self._project.current is None:
        raise ValueError("No project open")
    settings = load_settings()
    segments = list(self._project.current.transcript.segments)  # ← BUG: Project 无 transcript
    results = detect_fillers(segments, settings.get("filler_words", []))
    results_dicts = [r.model_dump() for r in results]
    store = self._mark_dirty(self._project.add_analysis_results(results_dicts, source="filler_detection"))
    if not store["success"]:
        raise RuntimeError(store.get("error", "Failed to store analysis results"))
    return {"project": store["data"], "results": results_dicts}

# _handle_error_detection (line 374-385) -- 同样的 bug
def _handle_error_detection(self, task, cancel_event, progress_cb):
    ...
    segments = list(self._project.current.transcript.segments)  # ← BUG
    results = detect_errors(segments, settings.get("error_trigger_words", []))
    ...

# _handle_full_analysis (line 387-412) -- if 分支已修，else 分支遗漏
def _handle_full_analysis(self, task, cancel_event, progress_cb):
    ...
    timeline_id = task.payload.get("timeline_id", "")
    project = self._project.current
    if timeline_id:
        timeline = project.get_timeline(timeline_id)
        if timeline is None:
            raise ValueError(f"Timeline {timeline_id} not found")
        segments = list(timeline.transcript.segments)  # ← 正确 (v2.1.0 Phase 3 已修)
    else:
        segments = list(project.transcript.segments)  # ← BUG: Project 无 transcript
    results = run_full_analysis(segments, settings)
    ...
```

**对比**: LLM handler (`_handle_smart_delete` line 690-702) 已正确使用 `project.active_timeline_id`:

```python
# _handle_smart_delete (line 690-702) -- 正确写法
project = self._project.current
timeline_id = task.payload.get("timeline_id", project.active_timeline_id)
timeline = project.get_timeline(timeline_id)
if timeline is None:
    raise ValueError(f"Timeline {timeline_id} not found")
segments = [s.model_dump() for s in timeline.transcript.segments if s.type == SegmentType.SUBTITLE]
```

### A-2: TaskManager 任务执行与取消 (当前代码)

**任务生命周期**:

```
create_task() → PriorityQueue → _process_queue() dispatch → _threaded_execution_wrapper()
  → semaphore.acquire() → _execute_task() → handler() → COMPLETED / FAILED
```

**并发控制** (`task_manager.py:29-55`):

```python
HEAVY_TASKS: set[TaskType] = {
    TaskType.EXPORT_VIDEO, TaskType.EXPORT_AUDIO,
    TaskType.TRANSCRIPTION, TaskType.SILENCE_DETECTION,
}
LIGHT_TASKS: set[TaskType] = {
    TaskType.WAVEFORM_GENERATION, TaskType.PROXY_GENERATION,
}
# LLM_* 任务类型不在两者中，走 else 分支 → _light_semaphore

self._heavy_semaphore = threading.Semaphore(1)   # GPU/CPU 密集
self._light_semaphore = threading.Semaphore(3)   # I/O 密集 (LLM 走这里)
```

**取消逻辑** (`task_manager.py:124-148`):

```python
def cancel_task(self, task_id: str) -> dict:
    with self._lock:
        task = self._tasks.get(task_id)
        if task is None:
            return {"success": False, "error": f"Task not found: {task_id}"}

        # Case A: 任务还在队列 → 标记 CANCELLED，worker 会跳过
        if task.status == TaskStatus.QUEUED:
            self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
            return {"success": True, "data": self._tasks[task_id].model_dump()}

        # Case B: 任务正在运行 → 触发 cancel_event
        if task.status == TaskStatus.RUNNING:
            event = self._cancel_events.get(task_id)
            if event:
                event.set()
            self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
            return {"success": True, "data": self._tasks[task_id].model_dump()}

    return {"success": False, "error": f"Task {task_id} is {task.status}, cannot cancel"}
```

**执行与异常处理** (`task_manager.py:228-306`):

```python
def _execute_task(self, task_id: str, task: MiloTask) -> None:
    handler = self._handlers.get(task.type)
    ...
    cancel_event = threading.Event()
    with self._lock:
        self._cancel_events[task_id] = cancel_event
        self._tasks[task_id] = current.model_copy(update={"status": TaskStatus.RUNNING, ...})

    try:
        def progress_cb(percent: float, message: str = "") -> None:
            self._update_progress(task_id, percent, message)

        result = handler(task, cancel_event, progress_cb)  # ← handler 执行

        # 成功路径
        with self._lock:
            self._tasks[task_id] = current.model_copy(update={"status": TaskStatus.COMPLETED, ...})
        self._emit(TASK_COMPLETED, {"task_id": task_id, "task_type": ..., "result": result})

    except Exception as e:
        # ← BUG: 不区分取消和失败，统一走 FAILED
        logger.exception("Task {} failed", task_id)
        with self._lock:
            self._tasks[task_id] = current.model_copy(update={
                "status": TaskStatus.FAILED,
                "error": str(e),
                "completed_at": datetime.now().isoformat(),
            })
        self._emit(TASK_FAILED, {"task_id": task_id, "error": str(e)})

    finally:
        with self._lock:
            self._cancel_events.pop(task_id, None)
```

**事件定义** (`core/events.py`):

```python
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"
# 缺少 TASK_CANCELLED
```

**前端监听** (`frontend/src/composables/useTask.ts:54-64`):

```typescript
onEvent<{ task_id: string; error: string }>(EVENT_TASK_FAILED, ({ task_id, error }) => {
  taskStartTimes.delete(task_id)
  const idx = tasks.value.findIndex((t) => t.id === task_id)
  if (idx >= 0) {
    tasks.value[idx] = { ...tasks.value[idx], status: "failed", error }
  }
})
// 没有 TASK_CANCELLED 监听
```

### A-3: call_llm 取消检查点 (当前代码)

`call_llm` (`llm_service.py:88-202`) 在以下位置检查 cancel_event:

```python
def call_llm(prompt, system, *, json_mode=False, config=None, cancel_event=None, progress_cb=None):
    ...
    for attempt in range(_MAX_RETRIES):  # 默认 3 次
        if cancel_event and cancel_event.is_set():       # ← 检查点 1: 每次重试前
            return {"success": False, "error": "Cancelled"}

        try:
            response = client.chat.completions.create(**request_kwargs)  # ← 阻塞调用，无法中断
            ...
            return {"success": True, "data": {"content": content, "usage": usage}}

        except APITimeoutError:
            last_error = f"LLM request timed out (attempt {attempt + 1})"
        except RateLimitError:
            last_error = f"Rate limited (attempt {attempt + 1})"
        except APIError as e:
            last_error = f"API error: {e}"
            break  # 不可重试，立即退出
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            break

        # 指数退避
        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_BASE_DELAY * (2**attempt)
            if cancel_event:
                cancel_event.wait(timeout=delay)   # ← 检查点 2: 退避等待时
            else:
                time.sleep(delay)

    return {"success": False, "error": last_error}
```

**关键限制**: `client.chat.completions.create()` 是同步 HTTP 请求，一旦发出，只有以下情况会返回:
1. 服务器响应到达
2. 客户端 timeout (config.timeout，默认 120s)
3. 网络异常

cancel_event 无法中断已发出的 HTTP 请求。

### A-4: 前端取消按钮调用链 (当前代码)

```
AIAssistantPanel.vue:handleCancelSingle()
  → emit("cancel-single")
  → Timeline.vue 透传 emit("cancel-single")
  → WorkspacePage.vue:handleCancelSingle()
  → call("cancel_llm_tasks")
  → main.py:MiloCutApi.cancel_llm_tasks()
```

**后端批量取消** (`main.py:1287-1301`):

```python
@expose
def cancel_llm_tasks(self) -> dict:
    """Cancel all currently running/queued LLM tasks (single-function mode)."""
    llm_types = {
        "llm_smart_delete", "llm_subtitle_correction",
        "llm_highlight", "llm_semantic_search",
    }
    tasks = self._task_manager.list_tasks()
    cancelled = 0
    for t in tasks.get("data", []):
        if t.get("type") in llm_types and t.get("status") in ("queued", "running"):
            self._task_manager.cancel_task(t["id"])
            cancelled += 1
    return {"success": True, "data": {"cancelled": cancelled}}
```

**前端 toast** (`WorkspacePage.vue:955-958`):

```typescript
async function handleCancelSingle() {
  await call("cancel_llm_tasks")
  showToast("已取消", "info", 2000)  // ← 立即弹 toast，但任务可能还在跑
}
```

---

## 附录 B: M2/M3 当前运行逻辑与代码

### B-1: LLM 配置读取 (当前代码)

**get_llm_config** (`llm_service.py:59-70`):

```python
def get_llm_config() -> LlmConfig:
    settings = load_settings()
    return LlmConfig(
        provider=LlmProvider(settings.get("llm_provider", "deepseek")),
        base_url=settings.get("llm_base_url", "").strip(),
        api_key=settings.get("llm_api_key", "").strip(),
        model=settings.get("llm_model", "").strip(),
        temperature=settings.get("llm_temperature", 0.3),
        timeout=settings.get("llm_timeout", 120),
        thinking_enabled=settings.get("llm_thinking_enabled", False),
    )
```

**_DEFAULT_SETTINGS 中 LLM 相关字段** (`config.py:76-93`):

```python
"llm_provider": "deepseek",
"llm_base_url": "",
"llm_api_key": "",
"llm_model": "",
"llm_temperature": 0.3,
"llm_timeout": 120,
"llm_thinking_enabled": False,
"llm_provider_configs": {},    # v2.1.0 供应商配置缓存
"llm_prompts": {},             # Phase 3 提示词
"llm_prompt_presets": {},      # v2.1.0 Phase 1 预设
"workflows": [],               # v2.1.0 Phase 3 工作流
# 缺少窗口/批次/并发参数
```

### B-2: 字幕分窗函数 (当前代码)

**chunk_transcript** (`llm_service.py:257-300`) -- 按时间切:

```python
def chunk_transcript(segments, chunk_duration=300.0, overlap_duration=30.0):
    """按时间切分，每个 chunk 覆盖 chunk_duration 秒，相邻 chunk 有 overlap_duration 秒重叠。"""
    chunks = []
    i = 0
    while i < len(segments):
        chunk_start = segments[i]["start"]
        chunk_end_time = chunk_start + chunk_duration
        chunk = []
        while i < len(segments) and segments[i]["start"] < chunk_end_time:
            chunk.append(segments[i])
            i += 1
        if chunk:
            chunks.append(chunk)
            # 回退创建重叠
            if i < len(segments):
                overlap_start = chunk_end_time - overlap_duration
                while i > 0 and segments[i - 1]["start"] >= overlap_start:
                    i -= 1
    return chunks
```

**chunk_transcript_short** (`llm_service.py:303-325`) -- smart_delete 专用:

```python
def chunk_transcript_short(segments, window_duration=25.0, overlap_duration=5.0):
    """smart_delete 用的短窗口，默认 25s 窗口 + 5s 重叠。"""
    return chunk_transcript(segments, chunk_duration=window_duration, overlap_duration=overlap_duration)
```

### B-3: analyze_smart_delete 串行循环 (当前代码)

**核心循环** (`llm_service.py:491-562`):

```python
def analyze_smart_delete(segments, existing_flagged_ids=None, *, config=None,
                          cancel_event=None, progress_cb=None, chunk_callback=None,
                          system_prompt=None):
    ...
    # 过滤已标注段
    flagged = existing_flagged_ids or set()
    to_analyze = [s for s in segments if str(s.get("id", "")) not in flagged]

    chunks = chunk_transcript_short(to_analyze)  # ← 硬编码 25s/5s
    total_chunks = len(chunks)

    all_results = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # ← 串行 for 循环，逐 chunk 调用 LLM
    for idx, chunk in enumerate(chunks):
        if cancel_event and cancel_event.is_set():       # ← chunk 边界检查取消
            return {"success": False, "error": "Cancelled"}

        if progress_cb:
            pct = (idx / total_chunks) * 100
            progress_cb(pct, f"Smart-delete analyzing window {idx + 1}/{total_chunks}...")

        prompt = _build_structured_user_message(chunk)
        result = call_llm(prompt, system=effective_system, json_mode=True,
                          config=config, cancel_event=cancel_event)

        if not result.get("success"):
            continue  # ← 单 chunk 失败跳过

        chunk_results = _parse_json_response_layers(content)
        ...
        if normalized and chunk_callback:
            chunk_callback(normalized)   # ← 实时推送给前端
        all_results.extend(normalized)

    # 按 segment_id 去重
    seen = {}
    for r in all_results:
        seen[r["segment_id"]] = r
    deduped = list(seen.values())
    ...
```

### B-4: analyze_subtitle_correction 串行循环 (当前代码)

**核心循环** (`llm_service.py:582-720`):

```python
def analyze_subtitle_correction(segments, reference_text=None, context_window=3, *,
                                 config=None, cancel_event=None, progress_cb=None,
                                 system_prompt_a=None, system_prompt_b=None):
    ...
    batch_size = 20  # ← 硬编码
    total_batches = (len(segments) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}

        # 选批 + 上下文窗口
        start_i = batch_idx * batch_size
        end_i = min(start_i + batch_size, len(segments))
        ctx_start = max(0, start_i - context_window)   # ← context_window 硬编码 3
        ctx_end = min(len(segments), end_i + context_window)

        batch_with_context = segments[ctx_start:ctx_end]
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}

        prompt = _build_structured_user_message(batch_with_context, extra_context=...)
        result = call_llm(prompt, system=system, json_mode=True, config=config, cancel_event=cancel_event)
        ...
```

### B-5: analyze_highlight (不并发，当前代码)

**核心循环** (`llm_service.py:863-895`):

```python
def analyze_highlight(segments, target_duration_minutes, *, config=None, ...):
    ...
    # 大窗口 30 分钟，通常单次调用
    chunks = chunk_transcript(segments, chunk_duration=1800.0, overlap_duration=60.0)  # ← 硬编码

    highlight_config = config.model_copy(update={"timeout": max(config.timeout, 300)})

    for idx, chunk in enumerate(chunks):
        if cancel_event and cancel_event.is_set():
            return {"success": False, "error": "Cancelled"}
        ...
        result = call_llm(prompt, system=effective_system, json_mode=True,
                          config=highlight_config, cancel_event=cancel_event)
        ...
```

### B-6: SettingsModal LLM Tab (当前代码)

**LLM Tab 结构** (`SettingsModal.vue:1190-1308`):

```
Provider: [下拉选择 DeepSeek/OpenAI/Qwen/GLM/Custom]
API Key:  [输入框]
Model:    [输入框]
深度思考: [复选框] (不支持的 Provider 禁用)
Temperature: [range 滑块 0-1]
[Test Connection 按钮]
```

缺少: 窗口/批次/上下文/并发数等高级参数区域。

---

## 附录 C: M4 当前运行逻辑与代码

### C-1: TranscriptRow 点击行为 (当前代码)

**handleRowClick** (`TranscriptRow.vue:117-124`):

```typescript
// 点击 = seek (跳转播放)，没有选择逻辑
function handleRowClick() {
  if (editingTimeField.value) return         // 正在编辑时间则不触发
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()                                // 编辑中则保存
  }
  emit("seek", props.segment.start)          // ← 跳转播放
}
```

**模板绑定** (`TranscriptRow.vue:138-143`):

```vue
<div
  class="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 ..."
  :class="[statusClass, { 'ring-1 ring-blue-500': isSelected }]"
  @click="handleRowClick"
  @contextmenu="handleContextMenu"
>
```

### C-2: 右键菜单 (当前代码)

**contextMenu** (`TranscriptRow.vue:26-39, 265-293`):

```typescript
const contextMenu = ref<{ x: number; y: number } | null>(null)

function handleContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  contextMenu.value = { x: e.clientX, y: e.clientY }
  openContextMenu(() => { contextMenu.value = null })
}
```

```vue
<!-- 右键菜单: 编辑文本 / 标记删除 / 删除段落 (无合并、无分割) -->
<Teleport to="body">
  <div v-if="contextMenu" ...>
    <button @click="startEdit">编辑文本</button>
    <button @click="emit('toggle-status')">
      {{ displayStatus === 'confirmed' ? '取消删除' : '标记删除' }}
    </button>
    <div class="border-t border-gray-100 my-1" />
    <button class="text-red-600" @click="emit('delete')">删除段落</button>
  </div>
</Teleport>
```

### C-3: 时间编辑 (当前代码)

**时间点击 → 输入框** (`TranscriptRow.vue:46-73, 146-174`):

```typescript
const editingTimeField = ref<"start" | "end" | null>(null)
const editingTimeValue = ref("")

function startTimeEdit(field: "start" | "end", e: MouseEvent) {
  e.stopPropagation()
  editingTimeValue.value = formatTime(field === "start" ? props.segment.start : props.segment.end)
  editingTimeField.value = field
  nextTick(() => timeInputRef.value?.select())
}

function applyTimeEdit() {
  const parsed = parseTime(editingTimeValue.value)
  if (parsed !== null && editingTimeField.value) {
    emit("update-time", props.segment.id, editingTimeField.value, parsed)
  }
  editingTimeField.value = null
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") applyTimeEdit()
  else if (e.key === "Escape") cancelTimeEdit()
  // ← 无方向键微调
}
```

```vue
<!-- 时间列: 点击数字变输入框，无 ±0.1s 按钮 -->
<template v-if="editingTimeField === 'start'">
  <input v-model="editingTimeValue" @keydown="handleTimeEditKeydown" @blur="applyTimeEdit" />
</template>
<template v-else>
  <span @mousedown.stop.prevent="startTimeEdit('start', $event)">{{ formatTime(segment.start) }}</span>
</template>
```

### C-4: useSegmentEdit 选择状态 (当前代码)

**单选，无多选** (`useSegmentEdit.ts:60-79`):

```typescript
const selectedSegmentId = ref<string | null>(null)
const selectedRange = ref<{ start: number; end: number } | null>(null)

function selectSegment(id: string | null) {
  selectedSegmentId.value = id  // ← 仅单选
}

function selectRange(start: number, end: number) {
  selectedRange.value = { start, end }  // ← 时间范围选，从未被调用
}

function clearSelection() {
  selectedSegmentId.value = null
  selectedRange.value = null
}
```

### C-5: useEdit 合并/分割/搜索 (当前代码，已定义但前端未接入)

**useEdit.ts:36-73**:

```typescript
// 已定义，但 WorkspacePage.vue 未解构使用
async function mergeSegments(segmentIds: string[]): Promise<boolean> {
  const res = await call<Project>("merge_segments", segmentIds)
  if (res.success && res.data) {
    snapshot()
    project.value = res.data
    return true
  }
  return false
}

async function splitSegment(segmentId: string, position: number): Promise<boolean> {
  const res = await call<Project>("split_segment", segmentId, position)
  if (res.success && res.data) {
    snapshot()
    project.value = res.data
    return true
  }
  return false
}

async function searchReplace(query: string, replacement: string, scope: string = "all") {
  const res = await call("search_replace", query, replacement, scope)
  ...
}
```

**WorkspacePage.vue 解构** (`WorkspacePage.vue:125-130`):

```typescript
const {
  deleteSegment,
  deleteSilenceSegments,
  deleteSubtitleTrimEdits,
} = useEdit(projectRef, pushSnapshot)
// ← mergeSegments / splitSegment 未解构
// ← searchReplace 单独解构 (line 123)
```

### C-6: 后端 merge_segments / split_segment / rename_timeline (已实现)

**project_service.py:838-925**:

```python
def merge_segments(self, segment_ids: list[str]) -> dict:
    """合并连续字幕段: 按 start 排序，拼接文本，移除孤立 EditDecision。"""
    targets = [s for s in segments if s.id in segment_ids and s.type == SegmentType.SUBTITLE]
    if len(targets) < 2:
        return {"success": False, "error": "Need at least 2 subtitle segments to merge"}
    targets.sort(key=lambda s: s.start)
    merged_text = "".join(s.text for s in targets)
    merged_seg = targets[0].model_copy(update={"end": targets[-1].end, "text": merged_text, ...})
    ...

def split_segment(self, segment_id: str, position: float) -> dict:
    """在指定时间点分割: 创建 {id}-a 和 {id}-b，文本按时长比例分割。"""
    target = next((s for s in segments if s.id == segment_id), None)
    if position <= target.start or position >= target.end:
        return {"success": False, "error": "Split position must be within segment bounds"}
    ratio = (position - target.start) / (target.end - target.start)
    split_idx = int(len(target.text) * ratio)
    seg_a = target.model_copy(update={"id": f"{segment_id}-a", "end": position, "text": target.text[:split_idx].strip()})
    seg_b = target.model_copy(update={"id": f"{segment_id}-b", "start": position, "text": target.text[split_idx:].strip()})
    ...

def rename_timeline(self, timeline_id: str, new_label: str) -> dict:
    """重命名 Timeline。"""
    new_timelines = [t.model_copy(update={"label": new_label}) if t.id == timeline_id else t
                     for t in self._current.timelines]
    self._current = self._current.model_copy(update={"timelines": new_timelines})
    ...
```

### C-7: SearchReplaceBar (当前代码)

**Ctrl+F 触发** (`SearchReplaceBar.vue:30-46`):

```typescript
// 组件自身监听 Ctrl+F，显示搜索栏
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.key === "f") {
    e.preventDefault()
    show()  // isVisible.value = true
  }
  if (e.key === "Escape" && isVisible.value) {
    hide()
  }
}

onMounted(() => {
  document.addEventListener("keydown", handleKeydown)
})
```

**无可见触发按钮**: SearchReplaceBar 默认 `isVisible = false`，只能 Ctrl+F 打开，没有工具栏图标。

---

## 附录 D: Timeline 组件事件透传与工具栏 (当前代码)

### D-1: Timeline.vue 工具栏 (当前代码)

**现有工具栏** (`Timeline.vue:118-141`):

```vue
<div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
  <span class="text-sm font-medium">Timeline</span>
  <div class="flex items-center gap-2">
    <!-- 编辑字幕 / 退出编辑 切换按钮 -->
    <button v-if="!globalEditMode" @click="emit('toggle-edit-mode')">编辑字幕</button>
    <button v-else @click="emit('toggle-edit-mode')">退出编辑</button>
    <span>{{ subtitleCount }} subtitles + {{ silenceCount }} silence</span>
  </div>
</div>
<!-- 缺少: 选择模式按钮、搜索图标、合并按钮 -->
```

### D-2: Timeline.vue emit 定义 (当前代码)

**事件列表** (`Timeline.vue:12-66`):

```typescript
const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": [segment: Segment]
  "confirm-segment": [segment: Segment]
  "reject-segment": [segment: Segment]
  "delete-segment": [segment: Segment]
  "toggle-edit-mode": []
  // SuggestionPanel 透传
  "confirm-suggestion": [editId: string]
  "reject-suggestion": [editId: string]
  "confirm-all": []
  "reject-all": []
  // AIAssistantPanel 透传
  "start-smart-delete": []
  "start-subtitle-correction": [referenceText: string]
  "open-subtitle-fullscreen": []
  "start-highlight": [targetMinutes: number]
  "go-to-settings": []
  "cancel-single": []          // v2.1.0 新增
  "seek-suggestion": [time: number]
}>()
```

缺少: `toggle-selection-mode`、`merge-selected`、`split-segment`、`toggle-search-bar`、`rename-timeline` 等 M4 新增事件。

### D-3: Timeline 标签区 (当前代码)

Timeline 切换标签区域目前只有点击切换 active timeline，无右键菜单:

```vue
<!-- 当前: 标签仅点击切换，无右键重命名/删除 -->
<div v-for="tl in timelines" @click="emit('switch-timeline', tl.id)">
  {{ tl.label }}
</div>
```

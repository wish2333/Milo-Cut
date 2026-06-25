# Spec: AI 智能删除输入过滤 + 条数分块模式

> **版本**: v2.1.1  
> **日期**: 2026-06-25  
> **状态**: 已审计修正 (Rev 2 — 审计报告 `spec-smart-delete-input-filter-batch-2.1.1-5.md` P0/P1/P2 已修)  
> **涉及模块**: `core/llm_service.py`, `core/config.py`, `core/llm_prompts.py`, `main.py` (或 `core/timeline_utils.py`), `frontend/` SettingsModal + types

---

## 1. 需求概述

两项互相独立的改进，合并在一个 spec 中：

| # | 需求 | 当前行为 | 目标行为 |
|---|------|---------|---------|
| A | AI 分析输入过滤 | smart_delete / subtitle_correction 传入所有 subtitle 段，不检查 EditDecision 状态 | 忽略已被用户确认删除 (`action=delete AND status=confirmed`) 的段 |
| B | 智能删除分块模式 | 时间窗口（默认 60s 窗口 + 10s 重叠），`chunk_transcript()` 按时间切分 | 条数批次（默认 20 条 + 4 条重叠），采用 P1 式 batch+target 模式 |

---

## 2. 需求 A：AI 分析输入过滤

### 2.1 过滤规则

**精确条件**: `EditDecision.action == "delete" AND EditDecision.status == "confirmed"`

- 仅忽略 `action=delete` 且 `status=confirmed` 的段。
- `action=keep`（如 partial_delete）即使是 `confirmed` 状态也**保留**在分析输入中。
- `pending` / `rejected` 状态的 EditDecision **不影响**分析输入。

### 2.2 过滤应用范围

| 功能 | 是否过滤 | 原因 |
|------|---------|------|
| **smart_delete (P0)** | 是 | 已确认删除的段不需要再次分析是否删除 |
| **subtitle_correction (P1)** | 是 | 已确认删除的段不需要修正文本 |
| highlight (P2) | 否 | 亮点提取需要完整上下文，即使段已标记删除 |
| semantic_search (P3) | 否 | 搜索需要全部内容可检索 |
| 规则引擎 (`run_full_analysis`) | 否 | 规则分析是全量扫描的基础层 |

### 2.3 与 existing_ids 的关系

两者**并存**，按顺序执行：

1. **第一步**：过滤 confirmed-delete 段（从 `timeline.edits` 获取）— 从 segments 列表中移除。
2. **第二步**：过滤 existing_ids（从 `timeline.analysis.results` 获取的规则引擎已标记段）— 从剩余 segments 中移除。
3. **第三步**：对最终剩余的 segments 进行分块 + LLM 分析。

### 2.4 实现位置

> **审计核对结论 (审计 #6)**：已核对 `core/models.py:102-118`，`EditDecision` 字段类型确认如下：
> - `action: Literal["delete", "keep"]` — 运行时为 Python `str`，`== "delete"` 比较有效
> - `target_type: Literal["segment", "range"]` — 运行时为 Python `str`，`== "segment"` 比较有效
> - `status: EditStatus` — `StrEnum` 子类，`== EditStatus.CONFIRMED` 和 `== "confirmed"` 均有效

**抽取公共 helper (审计 #8 — DRY)**：

confirmed-delete 过滤逻辑在 P0 和 P1 中完全一致，抽取为公共函数，放在 `core/timeline_utils.py`（新文件）或 `main.py` 私有方法。推荐独立文件以便后续单测和 P2/P3 复用：

```python
# core/timeline_utils.py (新建)
"""Timeline-level utility functions shared across LLM handlers."""

from __future__ import annotations

from core.models import EditStatus, Timeline


def collect_confirmed_deleted_seg_ids(timeline: Timeline) -> set[str]:
    """Return segment IDs targeted by confirmed delete decisions.

    Only ``action="delete" AND status=confirmed`` edits with
    ``target_type="segment"`` contribute. Used by P0/P1 to skip
    already-confirmed-deleted segments from LLM analysis input.
    """
    result: set[str] = set()
    for edit in timeline.edits:
        if (
            edit.action == "delete"
            and edit.status == EditStatus.CONFIRMED
            and edit.target_type == "segment"
            and edit.target_id
        ):
            result.add(edit.target_id)
    return result
```

**`main.py` `_handle_smart_delete` (line ~689)** 调用 helper：

```python
from core.timeline_utils import collect_confirmed_deleted_seg_ids

# 收集 confirmed-delete 的段 ID（审计 #8: 抽取公共 helper）
deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)

# 过滤：移除已确认删除的段
segments = [
    s.model_dump()
    for s in timeline.transcript.segments
    if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
]
```

**`main.py` `_handle_subtitle_correction` (line ~799)**：

同样调用 `collect_confirmed_deleted_seg_ids(timeline)` 并过滤 segments。

### 2.5 边角情况

- **过滤后剩余 0 条段**：`analyze_smart_delete` 已有处理（返回 `{"results": [], "skipped": N}`），P1 同理返回空结果。不需要额外报错。
- **过滤后剩余段数 ≤ batch_size**：整批作为一个批次处理（见需求 B 3.4）。

---

## 3. 需求 B：条数分块模式

### 3.1 分块算法：P1 式 batch + target

采用与 `analyze_subtitle_correction` (P1) 相同的 batch+context 模式。

**算法行为示例**（batch_size=20, overlap=4，总计 ≥ 28 条段时）：

```
batch_size = 20     # 每批次的目标分析段数
overlap = 4         # 上下文重叠段数（前后各 overlap 条）
step = 20           # 批次步长 = batch_size（target 不重叠）

批次 0: batch=segments[0:24]   target=segments[0:20]   (首批无前文上下文，含 4 条后文)
批次 1: batch=segments[16:44]  target=segments[20:40]  (含 4 条前文 + 4 条后文，共 28 条)
批次 2: batch=segments[36:64]  target=segments[40:60]  (同上)
...
末批:   batch=segments[N-4:N]  target=segments[N-4:N]  (自然截断，无后文上下文)
```

每个批次传给 LLM 的 payload 包含 `batch_size + 2 * overlap` 条段（首尾批次自然截断），同时附带 `target_segment_ids` 列表（**按段出现顺序，非字典序**），明确告知 LLM 只需分析 target 中的段。

### 3.2 为什么用 batch+target 而非简单滑窗

| 方案 | 优点 | 缺点 |
|------|------|------|
| P1 式 batch+target | 重叠段仅提供上下文不会被重复建议；无需依赖 last-wins 去重 | 实现稍复杂 |
| 简单滑窗+去重 | 实现简单 | 重叠段被重复分析、重复建议，浪费 token 且 last-wins 可能丢失更优结果 |

选 **P1 式 batch+target**。这同时意味着原来的 `seen` 去重逻辑（line 649-653）变为安全网而非主要去重手段。

### 3.3 Prompt 变更

`_SMART_DELETE_SYSTEM` (`core/llm_prompts.py:28`) 追加一句说明：

```
重要：仅输出 target_segment_ids 列表中包含的段的分析结果。不在 target_segment_ids 中的段仅作为上下文参考，不要在输出中包含。
```

**变更原因**：引入 target_segment_ids 后，LLM 需要明确知道哪些段是分析目标、哪些只是上下文，否则会对重叠上下文段产生多余建议。

### 3.4 边界处理

| 情况 | 处理方式 |
|------|---------|
| 首批（无前文上下文） | `ctx_start = max(0, start_i - overlap)`，自然截断 |
| 末批（无后文上下文） | `ctx_end = min(len(segments), end_i + overlap)`，自然截断 |
| 总段数 ≤ batch_size | 单批次，target = 全部段，1 次 LLM 调用 |
| 总段数 > batch_size 但 ≤ batch_size + 2*overlap | 正常分批循环（首批 target=[0:batch_size]，次批 target=[batch_size:N]），`batch_size` 语义保持一致 |
| overlap ≥ batch_size | **入口校验**：clamp `overlap = min(overlap, batch_size - 1)`，并在日志中 warning |
| overlap = 0 | 允许（无上下文重叠），正常分批 |

> **审计 #9 阈值修正**：原 spec 使用 `total ≤ batch_size + 2*overlap` 作为单批次降级阈值，会导致 `batch_size=20` 时实际单批次处理 28 条（违反配置契约）。修正为 `total ≤ batch_size` 才降级，使 `batch_size` 语义在所有情况下一致。

### 3.5 废弃项

| 废弃项 | 处理 |
|--------|------|
| `chunk_transcript_short()` (llm_service.py:312-339) | **直接删除**（已 deprecated，无调用方） |
| `llm_smart_window_duration` (config.py:88) | **废弃**，从 `_DEFAULT_SETTINGS` 移除 |
| `llm_smart_overlap_duration` (config.py:89) | **废弃**，从 `_DEFAULT_SETTINGS` 移除 |
| `llmSmartWindowDuration` / `llmSmartOverlapDuration` (frontend types) | 替换为新字段 |

### 3.6 新增设置项

`core/config.py` `_DEFAULT_SETTINGS`:

```python
# 旧（删除）:
# "llm_smart_window_duration": 60.0,
# "llm_smart_overlap_duration": 10.0,

# 新:
"llm_smart_batch_size": 20,       # 智能删除批次大小（条）
"llm_smart_overlap_size": 4,      # 智能删除重叠（条）
```

**旧设置清理机制 (审计 #10)**：

虽然不自动迁移，但会在 `load_settings()` 中增加一次性清理：检测到旧 key 时从返回的 merged dict 中 `pop` 掉并写回 settings.json，避免技术债累积：

```python
def load_settings() -> dict[str, Any]:
    # ... existing load logic ...
    merged = copy.deepcopy(_DEFAULT_SETTINGS)
    merged.update(data)
    
    # 审计 #10: 清理已废弃的旧设置项（一次性）
    _DEPRECATED_KEYS = {"llm_smart_window_duration", "llm_smart_overlap_duration"}
    removed = [k for k in _DEPRECATED_KEYS if k in merged]
    if removed:
        for k in removed:
            merged.pop(k, None)
        save_settings(merged)  # 写回清理后的版本
        logger.info(f"Cleaned deprecated settings keys: {removed}")
    
    return merged
```

前端类型也会同步更新，UI 不再显示旧字段。

---

## 4. 实现细节

### 4.1 `core/llm_service.py` 改动

#### 4.1.1 新增 `chunk_transcript_by_count()` 函数

替代 `chunk_transcript` 在 smart_delete 中的使用：

```python
def chunk_transcript_by_count(
    segments: list[dict],
    batch_size: int = 20,
    overlap: int = 4,
) -> list[tuple[list[dict], set[str]]]:
    """按段数分块，返回 (batch_with_context, target_ids) 列表。

    P1 式 batch+target 模式：每个批次包含 batch_size + 2*overlap 条段，
    target_ids 标记需要分析的中间 batch_size 条。

    Args:
        segments: 段列表。
        batch_size: 每批次目标分析段数。min=1。
        overlap: 前后上下文重叠段数。min=0。若 overlap >= batch_size，
            自动 clamp 为 batch_size - 1。

    Returns:
        [(batch_segments, target_ids), ...] -- batch_segments 为浅拷贝切片。
    """
    if not segments:
        return []

    # 审计 #11: overlap >= batch_size 防护
    if overlap >= batch_size:
        logger.warning(
            f"overlap ({overlap}) >= batch_size ({batch_size}), "
            f"clamping to {batch_size - 1}"
        )
        overlap = max(0, batch_size - 1)

    total = len(segments)
    # 审计 #9: 仅当 total <= batch_size 时降级为单批次
    if total <= batch_size:
        all_ids = {str(s.get("id", "")) for s in segments}
        # 审计 #12: 返回浅拷贝避免下游 in-place 修改污染原列表
        return [(segments[:], all_ids)]

    batches = []
    step = batch_size  # 步长 = batch_size（target 不重叠）
    start_i = 0
    while start_i < total:
        end_i = min(start_i + batch_size, total)
        ctx_start = max(0, start_i - overlap)
        ctx_end = min(total, end_i + overlap)
        batch_with_context = segments[ctx_start:ctx_end]  # 切片即为浅拷贝
        target_ids = {str(segments[i].get("id", "")) for i in range(start_i, end_i)}
        batches.append((batch_with_context, target_ids))
        start_i += step

    return batches
```

#### 4.1.2 改造 `analyze_smart_delete()`

**设置读取**：

```python
# 旧 (line 526-531):
settings = load_settings()
window = float(settings.get("llm_smart_window_duration", 60.0))
overlap = float(settings.get("llm_smart_overlap_duration", 10.0))
concurrency = max(1, int(settings.get("llm_concurrency", 5)))
chunks = chunk_transcript(to_analyze, chunk_duration=window, overlap_duration=overlap)

# 新:
settings = load_settings()
batch_size = max(1, int(settings.get("llm_smart_batch_size", 20)))
overlap_size = max(0, int(settings.get("llm_smart_overlap_size", 4)))
concurrency = max(1, int(settings.get("llm_concurrency", 5)))
batches = chunk_transcript_by_count(to_analyze, batch_size=batch_size, overlap=overlap_size)
total_batches = len(batches)
```

**主循环改造 (审计 #3)**：

`_process_chunk` 签名从 `(idx, chunk)` 变为 `(idx, batch_segments, target_ids)`，ThreadPoolExecutor 提交参数同步变更：

```python
# 旧:
with ThreadPoolExecutor(max_workers=concurrency) as executor:
    futures = {
        executor.submit(_process_chunk, idx, chunk): idx
        for idx, chunk in enumerate(chunks)
    }

# 新:
with ThreadPoolExecutor(max_workers=concurrency) as executor:
    futures = {
        executor.submit(_process_chunk, idx, batch_segs, target_ids): idx
        for idx, (batch_segs, target_ids) in enumerate(batches)
    }
```

下游的 `as_completed` 循环、`results_by_index` 合并、`seen` 去重逻辑**不变**——`_process_chunk` 仍返回 `(idx, normalized_or_None, usage, error_str_or_None)` tuple。

#### 4.1.3 改造 `_process_chunk`

> **审计 #4 验证结论**：`_build_structured_user_message(segments, extra_context=...)` **已支持** `extra_context` 参数（`llm_service.py:349,375-376`），P1 字幕修正已在用（`llm_service.py:740`）。无需修改该函数。

**函数签名与返回类型 (审计 #5)**：

```python
def _process_chunk(
    idx: int,
    batch_segments: list[dict],
    target_ids: set[str],
) -> tuple[int, list[dict] | None, dict[str, int], str | None]:
    """Process a single smart-delete batch.

    Returns:
        (idx, normalized_results_or_None, token_usage, error_message_or_None)
        - normalized=None 表示该批次无结果（空或解析失败）
        - error=None 表示成功；非 None 表示失败原因
    """
    if cancel_event and cancel_event.is_set():
        return (idx, None, {}, "Cancelled")

    # 审计 #7: target_segment_ids 按段在 batch 内的出现顺序构建，非字典序 sorted
    target_ids_ordered = [
        str(s.get("id", "")) for s in batch_segments if str(s.get("id", "")) in target_ids
    ]
    extra_ctx = {"target_segment_ids": target_ids_ordered}
    prompt = _build_structured_user_message(batch_segments, extra_context=extra_ctx)

    result = call_llm(
        prompt,
        system=effective_system,
        json_mode=True,
        config=config,
        cancel_event=cancel_event,
    )
    if not result.get("success"):
        error = result.get("error", "LLM call failed")
        logger.warning(f"Smart-delete batch {idx + 1} failed: {error}")
        return (idx, None, {}, error)

    content = result["data"]["content"]
    usage = result["data"].get("usage", {})
    chunk_results = _parse_json_response_layers(content)
    if not chunk_results:
        logger.warning(f"Smart-delete batch {idx + 1}: JSON parse returned None")
        return (idx, None, usage, None)

    normalized = _normalize_smart_delete_items(chunk_results)
    # 过滤：只保留 target_ids 内的结果（与 P1 行为一致，llm_service.py:783）
    normalized = [r for r in normalized if r["segment_id"] in target_ids]
    return (idx, normalized or None, usage, None)
```

> **审计 #7 修正**：原 spec 使用 `sorted(target_ids)`，字典序排序会导致 `seg_10` 排在 `seg_2` 前面，与 batch 内实际段顺序不一致，可能影响 LLM 理解。改为按段在 `batch_segments` 中的出现顺序构建 list。

#### 4.1.4 删除 `chunk_transcript_short()`

直接删除 line 312-339（已 deprecated，无调用方）。

#### 4.1.5 保留 seen 去重

line 649-653 的 last-wins 去重逻辑**保留**作为安全网（虽然 batch+target 模式下不应出现重复，但保留以防 LLM 不遵守 target 约束）。

### 4.2 `core/llm_prompts.py` 改动

`_SMART_DELETE_SYSTEM` 追加 target 说明：

```diff
+_SMART_DELETE_SYSTEM = """你是视频转录文本的清理助手。用户以 JSON 格式提供一组转录片段。
+请识别其中可安全删除的片段:
+...
+重要：仅输出 target_segment_ids 列表中包含的段的分析结果。不在 target_segment_ids 中的段仅作为上下文参考，不要在输出中包含。
```

### 4.3 `main.py` 改动

#### 4.3.1 `_handle_smart_delete` (line ~689)

调用公共 helper（§2.4 定义的 `collect_confirmed_deleted_seg_ids`）：

```python
from core.timeline_utils import collect_confirmed_deleted_seg_ids

# 审计 #8: 使用公共 helper 收集 confirmed-delete 段 ID
deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)

# 过滤 segments
segments = [
    s.model_dump()
    for s in timeline.transcript.segments
    if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
]
```

#### 4.3.2 `_handle_subtitle_correction` (line ~799)

同样调用 `collect_confirmed_deleted_seg_ids(timeline)` 并过滤 segments。

> **审计 #17: min=5 的依据**：`batch_size` 的 `min=5` 是因为 smart_delete 的语义重复/口误纠正检测需要至少几条段做上下文对比，小于 5 条时上下文不足以判断重复口癖。`overlap` 的 `min=0` 允许无重叠（代价是批次边界处可能遗漏跨段现象）。

### 4.4 `core/config.py` 改动

```diff
 _DEFAULT_SETTINGS: dict[str, Any] = {
     ...
-    "llm_smart_window_duration": 60.0,
-    "llm_smart_overlap_duration": 10.0,
+    "llm_smart_batch_size": 20,
+    "llm_smart_overlap_size": 4,
     ...
 }
```

### 4.5 前端改动

#### 4.5.1 `frontend/src/types/edit.ts`

```diff
-  llm_smart_window_duration: number
-  llm_smart_overlap_duration: number
+  llm_smart_batch_size: number
+  llm_smart_overlap_size: number
```

#### 4.5.2 `frontend/src/components/workspace/SettingsModal.vue`

> **审计 #1 (P0 Bug) 修正**：原 spec 使用 `parseInt(...) || 20` / `parseInt(...) || 4` 模式，但 `parseInt("0") === 0`，而 `0 || 4 === 4`，导致用户输入 0 会被强制改回默认值。改用 `Number.isNaN` 判断。

```diff
-<span class="text-xs text-gray-600">智能删除窗口 (秒)</span>
+<span class="text-xs text-gray-600">智能删除批次大小 (条)</span>
 <input
   type="number"
-  step="1"
-  min="5"
-  :value="settings.llm_smart_window_duration"
+  step="1"
+  min="5"
+  :value="settings.llm_smart_batch_size"
   ...
-  @change="settings = { ...settings!, llm_smart_window_duration: parseFloat(($event.target as HTMLInputElement).value) || 60.0 }"
+  @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_batch_size: Number.isNaN(v) ? 20 : v } })()"
 />

-<span class="text-xs text-gray-600">智能删除重叠 (秒)</span>
+<span class="text-xs text-gray-600">智能删除重叠 (条)</span>
 <input
   type="number"
-  step="1"
-  min="0"
-  :value="settings.llm_smart_overlap_duration"
+  step="1"
+  min="0"
+  :value="settings.llm_smart_overlap_size"
   ...
-  @change="settings = { ...settings!, llm_smart_overlap_duration: parseFloat(($event.target as HTMLInputElement).value) || 10.0 }"
+  @change="(() => { const v = parseInt(($event.target as HTMLInputElement).value); settings = { ...settings!, llm_smart_overlap_size: Number.isNaN(v) ? 4 : v } })()"
 />
```

> **实现提示**：实际代码中可将 IIFE 抽为一个 `handleNumberInput(defaultValue)` helper 函数避免重复。

---

## 5. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/config.py` | 修改 | 替换 2 个默认设置项；新增旧设置一次性清理逻辑 |
| `core/llm_service.py` | 修改 + 删除 | 新增 `chunk_transcript_by_count`；改造 `analyze_smart_delete` 分块 + 主循环 + `_process_chunk` 加 target_ids；删除 `chunk_transcript_short` |
| `core/llm_prompts.py` | 修改 | `_SMART_DELETE_SYSTEM` 追加 target_segment_ids 说明 |
| `core/timeline_utils.py` | **新增** | `collect_confirmed_deleted_seg_ids()` 公共 helper (审计 #8) |
| `main.py` | 修改 | `_handle_smart_delete` + `_handle_subtitle_correction` 调用 helper 过滤 confirmed-delete |
| `frontend/src/types/edit.ts` | 修改 | 替换 2 个字段 |
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 | 2 个输入框标签 + 绑定字段更新 + `Number.isNaN` 防 0 Bug (审计 #1) |

---

## 6. 不需要改动的部分

- **`chunk_transcript()` (llm_service.py:266)**：保留，highlight (P2) 仍使用时间窗口。已 grep 验证 P2 调用方读取的是 `llm_highlight_chunk_duration`/`llm_highlight_overlap_duration`，不是 `llm_smart_*`。
- **existing_ids 过滤逻辑**：保留，与 confirmed-delete 过滤并存。
- **`seen` 去重 (llm_service.py:649-653)**：保留作为安全网。
- **并发逻辑 (ThreadPoolExecutor)**：不变，仅替换 chunk 来源。
- **429 自适应降级 (AR-2)**：不变。
- **工作流引擎 (workflow_engine.py)**：不需改动，通过 `_handle_smart_delete` 自动继承新逻辑。已 grep 验证工作流步骤 `llm_smart_delete` 的唯一入口是 `_handle_smart_delete` (workflow_engine.py:64 映射 + main.py:158 注册)。
- **前端 AIAssistantPanel.vue**：不需改动，功能入口和交互不变。
- **highlight / semantic_search**：不需改动，不受影响。

### 6.1 日志/可观测性更新 (审计 #16)

分块策略从「时间窗口」变为「条数批次」后，进度日志文案需同步更新：

```python
# 旧:
progress_cb(pct, f"Smart-delete window {completed}/{total_chunks}...")

# 新:
progress_cb(pct, f"Smart-delete batch {completed}/{total_batches} (target={len(target_ids)} segs)...")
```

logger.info 末尾总结不变（`f"Smart-delete analysis done: {len(deduped)} results, tokens={...}"`）。

---

## 7. 测试要点

### 7.1 单元测试

| 测试 | 验证点 |
|------|--------|
| `test_chunk_transcript_by_count_basic` | 100 条段 → 5 批次，每批 target 20 条 |
| `test_chunk_transcript_by_count_overlap` | 批次 1 的上下文含批次 0 的末尾 4 条 (ctx_start=16) |
| `test_chunk_transcript_by_count_single_batch` | ≤ 20 条段 → 单批次，target = 全部 (审计 #9 阈值修正) |
| `test_chunk_transcript_by_count_boundary_28` | 28 条段 → 2 批次 (20+8)，不是单批次 (审计 #9) |
| `test_chunk_transcript_by_count_empty` | 0 条段 → 空列表 |
| `test_chunk_transcript_by_count_overlap_ge_batch` | overlap≥batch_size 时自动 clamp + warning (审计 #11) |
| `test_chunk_transcript_by_count_overlap_zero` | overlap=0 允许，正常分批 |
| `test_chunk_transcript_by_count_batch_size_one` | batch_size=1 极端值，每批 1 条 target |
| `test_chunk_transcript_by_count_missing_id` | 段缺 id 字段时 fallback "" 不崩溃 |
| `test_chunk_transcript_by_count_shallow_copy` | 返回的 batch_segments 是切片，修改不污染原列表 (审计 #12) |
| `test_smart_delete_filters_confirmed_delete` | confirmed-delete 段不出现在 LLM 输入中 |
| `test_smart_delete_keeps_partial_delete` | confirmed 的 partial_delete (action=keep) 段保留在输入中 |
| `test_smart_delete_keeps_pending` | pending 状态的 delete 段保留在输入中 |
| `test_subtitle_correction_filters_confirmed_delete` | P1 同步过滤 confirmed-delete |
| `test_target_ids_passed_to_prompt` | `_build_structured_user_message` 输出包含 target_segment_ids 且按段顺序 (审计 #7) |
| `test_results_filtered_by_target` | LLM 返回的非 target 段被过滤掉 |
| `test_llm_returns_duplicate_id_seen_dedup` | LLM 返回重复 id 时 seen 去重安全网生效 (审计 #15) |
| `test_analyze_smart_delete_unpacks_batches` | 主循环正确解包 `(batch_segs, target_ids)` tuple (审计 #3/#15) |
| `test_collect_confirmed_deleted_seg_ids` | helper 正确过滤 action+status+target_type 组合 (审计 #8) |

### 7.2 集成测试

| 测试 | 场景 |
|------|------|
| 运行 smart_delete → 确认部分结果 → 再次运行 | 第二次运行不应包含已确认删除的段 |
| 运行 subtitle_correction → 确认部分 delete → 再次运行 | 同上 |
| 工作流：规则分析 + smart_delete | smart_delete 不分析规则引擎已标记的段（existing_ids 仍然生效）|

### 7.3 前端测试

| 测试 | 验证点 |
|------|--------|
| SettingsModal 显示新字段 | 「智能删除批次大小 (条)」默认 20，「智能删除重叠 (条)」默认 4 |
| SettingsModal 输入 0 不被覆盖 | 输入 0 时 overlap 保持 0，不被强制改回 4 (审计 #1) |
| 旧设置兼容 | 已有 settings.json 中有旧 key 时不报错，且被自动清理 |

---

## 8. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 过滤范围 | 仅 EditDecision confirmed + delete | partial_delete (keep) 即使确认也需保留；pending/rejected 不代表最终决策 |
| 分块算法 | P1 式 batch+target | 避免重叠区重复建议，比简单滑窗更高效 |
| 设置迁移 | 新增+废弃旧+自动清理 | 语义不同（秒→条），复用 key 名会导致混淆；旧 key 自动清理避免技术债 (审计 #10) |
| existing_ids | 保留并存 | 规则引擎标记仍有效，confirmed-delete 是补充层 |
| prompt | 追加 target 说明 | target_segment_ids 是新概念，需 prompt 引导 |
| chunk_transcript_short | 删除 | 已 deprecated 无调用方 |
| P1 同步过滤 | 是 | 已确认删除的段修正文本无意义 |
| 首尾边界 | 自然截断 | 与 P1 行为一致 |
| 默认值 | 20/4 可调 | 用户指定值，min 分别为 5/0 (batch min=5 因重复检测需最少几条上下文) |
| 去重策略 | 保留 last-wins | 作为安全网，batch+target 模式下不应触发 |
| 单批次阈值 | total ≤ batch_size | 保持 batch_size 语义一致，避免实际处理超量 (审计 #9) |
| overlap 防护 | clamp < batch_size | 防止 overlap≥batch_size 时逻辑异常 (审计 #11) |
| target_ids 顺序 | 按段出现顺序 | 避免 sorted 字典序与 batch 实际顺序不一致 (审计 #7) |
| confirmed-delete 过滤 | 抽取公共 helper | DRY 原则，P0/P1 共用，便于单测 (审计 #8) |

---

## 9. 审计修正核对矩阵

本 spec 已根据审计报告 `spec-smart-delete-input-filter-batch-2.1.1-5.md` 修正以下项目：

### 9.1 Bug / 严重问题 (审计 §一)

| # | 审计项 | 优先级 | 修正位置 | 修正内容 |
|---|--------|--------|---------|----------|
| 1 | 前端 `|| 4` / `|| 20` 对 0 的处理 | P0 | §4.5.2 | 改用 `Number.isNaN(v) ? default : v` 模式 |
| 2 | §3.1 示例与 §4.1.1 算法不一致 | P0 | §3.1 | 补全尾部上下文，示例改为 `batch=segments[0:24] target=segments[0:20]` 等 |

### 9.2 Spec 空白 (审计 §二)

| # | 审计项 | 优先级 | 修正位置 | 修正内容 |
|---|--------|--------|---------|----------|
| 3 | 主循环改造未展示 | P0 | §4.1.2 | 补全 ThreadPoolExecutor 提交参数变更伪代码 |
| 4 | `_build_structured_user_message` 是否支持 extra_context | P0 | §4.1.3 | 已核对 `llm_service.py:349,375-376` 确认支持，补充验证结论 |
| 5 | `_process_chunk` 返回类型 | P0 | §4.1.3 | 补全 `(idx, normalized_or_None, usage, error_str_or_None)` 类型标注 + docstring |
| 6 | EditDecision 字段类型核对 | P0 | §2.4 | 已核对 `models.py:102-118`，action/target_type=Literal(string)，status=EditStatus(StrEnum)，比较有效 |

### 9.3 设计隐患 (审计 §三)

| # | 审计项 | 优先级 | 修正位置 | 修正内容 |
|---|--------|--------|---------|----------|
| 7 | `sorted(target_ids)` 不保证段顺序 | P1 | §4.1.3 | 改为按段在 batch 内出现顺序构建 list |
| 8 | confirmed-delete 过滤逻辑重复 (DRY) | P2 | §2.4, §4.3 | 抽取 `core/timeline_utils.py:collect_confirmed_deleted_seg_ids()` |
| 9 | `total ≤ batch_size + 2*overlap` 阈值语义漂移 | P2 | §3.4, §4.1.1 | 改为 `total ≤ batch_size` 才降级 |
| 10 | 旧设置项无清理机制 | P2 | §3.6 | `load_settings()` 增加一次性 pop + 写回 |
| 11 | `overlap ≥ batch_size` 未处理 | P1 | §3.4, §4.1.1 | 入口 clamp `overlap = min(overlap, batch_size-1)` + warning |
| 12 | 单批次返回 segments 引用风险 | P2 | §4.1.1 | 返回 `segments[:]` 浅拷贝 |

### 9.4 文档/一致性 (审计 §四)

| # | 审计项 | 优先级 | 修正位置 | 修正内容 |
|---|--------|--------|---------|----------|
| 13 | 命名不统一 (overlap vs overlap_size) | P2 | §4.1.1 | 函数参数保持 `overlap`，settings key 为 `llm_smart_overlap_size`，局部变量 `overlap_size`。已在代码注释中标明映射关系 |
| 14 | §3.4 表格内联「修正」残留 | P2 | §3.4 | 清理为最终结论 |
| 15 | 缺失测试用例 | P2 | §7.1 | 补全 7 条缺失测试（异常输入 + target 过滤 + 重复去重 + tuple 解包 + helper）|
| 16 | 日志/可观测性未提及 | P2 | §6.1 | 新增 §6.1 日志文案更新说明 |
| 17 | min=5 的依据 | P2 | §4.3 | 补充理由：重复检测需最少几条上下文 |

### 9.5 隐含假设验证 (审计 §五)

| # | 假设 | 验证结果 | 验证证据 |
|---|------|---------|----------|
| A1 | `timeline.edits` 中 confirmed-delete 的 `target_id` 是 segment id | **成立** (当前设计) | `EditDecision.target_type` 只有 `"segment"`/`"range"`；helper 已过滤 `target_type=="segment"`。未来若支持词级删除，helper 需扩展。 |
| A2 | `_handle_subtitle_correction` 的输入与 smart_delete 同源 | **成立** | `main.py:799` `_handle_subtitle_correction` 同样从 `timeline.transcript.segments` 获取输入。 |
| A3 | highlight(P2) 使用独立的时间窗口设置 | **成立** | `llm_service.py:1028-1029` P2 读取 `llm_highlight_chunk_duration`/`llm_highlight_overlap_duration`，不是 `llm_smart_*`。 |
| A4 | 工作流引擎不绕过 `_handle_smart_delete` | **成立** | `workflow_engine.py:64` 映射 `llm_smart_delete → TaskType.LLM_SMART_DELETE`；`main.py:158` 注册 `LLM_SMART_DELETE → _handle_smart_delete`。唯一入口。 |

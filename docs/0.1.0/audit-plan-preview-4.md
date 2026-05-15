# Milo-Cut 实施计划 -- 审计报告 #4 修复

**基于:** `docs/audit-report-preview-4.md`
**日期:** 2026-05-15
**最后修订:** 2026-05-16 (根据审计意见修正)
**范围:** B1, B2, B3, B4, C2 (排除 C1)
**实施顺序:** B1 -> B3+B4 -> B2 -> C2

---

## B1 [HIGH] `_get_media_duration` 低估实际媒体时长 + `export_audio` 缺少 media_info

### 目标

修复 `_get_media_duration` 忽略 `media_info.duration`（来自 ffprobe）导致的导出截断问题，同时补齐 `export_audio` 缺失的 `media_info` 参数。

### 涉及文件

- `core/export_service.py` -- `_get_media_duration`, `_compute_keep_ranges`, `export_video`, `export_audio`
- `main.py` -- `_handle_export_audio`

### Step 1: 修改 `_get_media_duration` (export_service.py:251-254)

**当前代码:**
```python
def _get_media_duration(segments: list[dict], edits: list[dict]) -> float:
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    return max(all_times) if all_times else 0.0
```

**替换为:**
```python
def _get_media_duration(
    segments: list[dict],
    edits: list[dict],
    media_duration: float = 0.0,
) -> float:
    """Compute total media duration from segments, edits, and optionally the actual media file duration.

    Uses the larger of the computed duration (from segments/edits) and the actual
    media file duration from ffprobe, so the export is never truncated by a gap
    after the last subtitle segment.
    """
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    computed = max(all_times) if all_times else 0.0
    return max(computed, media_duration)
```

### Step 2: 在 `export_video` 调用处添加防御日志 (export_service.py:49)

**当前代码:**
```python
total_duration = _get_media_duration(segments, edits)
```

**替换为:**
```python
media_duration = media_info.get("duration", 0.0) if media_info else 0.0
if media_duration <= 0.0:
    logger.warning("media_duration unavailable ({}), export may be truncated", media_duration)
total_duration = _get_media_duration(segments, edits, media_duration)
```

### Step 3: 修改 `_compute_keep_ranges` 端点钳位 (export_service.py:257-277)

**在函数末尾添加钳位逻辑:**

```python
def _compute_keep_ranges(
    total_duration: float,
    deletions: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    if not deletions:
        return [(0.0, total_duration)]

    merged = _merge_ranges(deletions)
    keep: list[tuple[float, float]] = []
    current = 0.0

    for del_start, del_end in merged:
        if current < del_start:
            keep.append((current, del_start))
        current = max(current, del_end)

    if current < total_duration:
        keep.append((current, total_duration))

    # Clamp to prevent segment/edit endpoints exceeding actual media duration
    return [(min(s, total_duration), min(e, total_duration)) for s, e in keep]
```

### Step 4: 为 `export_audio` 新增 `media_info` 参数 (export_service.py:112-118)

**当前签名:**
```python
def export_audio(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
```

**替换为:**
```python
def export_audio(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
```

**在 `export_audio` 内将 duration 获取改为:**
```python
media_duration = media_info.get("duration", 0.0) if media_info else 0.0
if media_duration <= 0.0:
    logger.warning("media_duration unavailable ({}), export may be truncated", media_duration)
total_duration = _get_media_duration(segments, edits, media_duration)
```

### Step 5: `main.py` `_handle_export_audio` 传递 `media_info` (main.py:130-155)

**当前调用:**
```python
return export_audio(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)
```

**替换为:**
```python
return export_audio(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    media_info=project.media.model_dump() if project.media else None,
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)
```

### B1 测试计划

1. **单元测试**: 构造 `segments=[{"end": 60}]`, `edits=[]`, `media_duration=90`，验证 `_get_media_duration` 返回 90
2. **单元测试**: `media_duration=0` 时退化回 computed 逻辑
3. **单元测试**: `_compute_keep_ranges` 端点钳位 -- 当 segment end 略大于 total_duration 时端点应被钳位
4. **集成测试**: 构造末尾有无声尾画面的视频，导出后不应被截断

---

## B3 [HIGH] SubtitleTrim 未忽略已标记删除的字幕

> **与 B4 合并说明：** B3 和 B4 修改同一函数 `generate_subtitle_keep_ranges`，实施时建议合并为单 commit。

### 目标

`generate_subtitle_keep_ranges` 在构建 `subtitle_segs` 时排除已 confirmed delete 的字幕，同时检查 confirmed keep 避免冲突。

### 涉及文件

- `core/project_service.py` -- `generate_subtitle_keep_ranges`

### 修改 `generate_subtitle_keep_ranges` (project_service.py:855-860)

**当前代码:**
```python
subtitle_segs = sorted(
    [s for s in self._current.transcript.segments if s.type == SegmentType.SUBTITLE],
    key=lambda s: s.start,
)
```

**替换为:**
```python
# Collect IDs of segments with confirmed delete edits
confirmed_deleted_ids: set[str] = {
    e.target_id for e in self._current.edits
    if e.status == EditStatus.CONFIRMED and e.action == "delete" and e.target_id
}

# Collect IDs of segments with confirmed keep edits
confirmed_kept_ids: set[str] = {
    e.target_id for e in self._current.edits
    if e.status == EditStatus.CONFIRMED and e.action == "keep" and e.target_id
}

# Exclude confirmed-deleted subtitles from keep ranges
subtitle_segs = sorted(
    [s for s in self._current.transcript.segments
     if s.type == SegmentType.SUBTITLE and s.id not in confirmed_deleted_ids],
    key=lambda s: s.start,
)
```

### 处理 confirmed keep 已存在于 keep_ranges 中

Confirmed kept 字幕自然保留在 `subtitle_segs` 中（因未在 `confirmed_deleted_ids` 中被排除），进而纳入 keep_ranges。SubtitleTrim 生成的 delete ranges 仅在 gaps 之间，不会覆盖 confirmed kept 字幕的范围。

### B3 测试计划

1. **单元测试**: 一条字幕标记为 confirmed delete 后，运行 SubtitleTrim，验证该字幕不在 keep_ranges 内
2. **单元测试**: 一条字幕标记为 confirmed keep 后，运行 SubtitleTrim，验证该字幕仍在 keep_ranges 内
3. **单元测试**: 同时存在 confirmed delete 和 confirmed keep 时，两者互不干扰

---

## B4 [MEDIUM] `already_covered` 检查忽略 REJECTED 状态

> **与 B3 合并说明：** B3 和 B4 修改同一函数 `generate_subtitle_keep_ranges`，实施时建议合并为单 commit（`fix: SubtitleTrim 排除已删除字幕并修复 already_covered 状态遗漏`），避免留下中间状态。

### 目标

`generate_subtitle_keep_ranges` 中的 `already_covered` 检查应包括 `REJECTED` 状态，防止重复创建已 rejected 的 PENDING 编辑。

### 涉及文件

- `core/project_service.py` -- `generate_subtitle_keep_ranges`

### 修改 project_service.py:894-900

**当前代码:**
```python
already_covered = any(
    e.action == "delete"
    and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)
    and abs(e.start - start) < 0.05
    and abs(e.end - end) < 0.05
    for e in existing_edits
)
```

**替换为:**
```python
already_covered = any(
    e.action == "delete"
    and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
    and abs(e.start - start) < 0.05
    and abs(e.end - end) < 0.05
    for e in existing_edits
)
```

### 技术债备忘

`already_covered` 逻辑在 silence detection 和 SubtitleTrim 中重复出现。后续应提取为共用工具函数 `_is_range_already_covered(edits, start, end)`，避免多处维护相同逻辑。本次暂不提取，保留在技术债列表中。

### B4 测试计划

1. **单元测试**: 对某一范围创建 SubtitleTrim edit -> reject 该 edit -> 重新运行 SubtitleTrim，验证不创建重复的 PENDING edit

---

## B2 [HIGH] SRT 导出字幕筛选标准与视频导出不一致

### 目标

SRT 导出改为以视频导出的 `keep_ranges` 为权威来源，与视频导出保持一致。

### 涉及文件

- `core/export_service.py` -- `export_srt`, 新增 `_subtitle_survives_in_keep_ranges`

### Step 1: 新增辅助函数

在 `_overlaps_deletions` 之后新增:

```python
def _subtitle_survives_in_keep_ranges(
    seg_start: float,
    seg_end: float,
    keep_ranges: list[tuple[float, float]],
    min_keep: float = 0.3,
) -> bool:
    """Return True if the subtitle segment has enough content preserved.

    For subtitles longer than `min_keep`, at least `min_keep` seconds must
    survive in the keep_ranges.  For shorter subtitles the threshold is
    lowered to 50% of the segment duration, so that brief but completely
    intact subtitles are not silently dropped.
    """
    seg_duration = seg_end - seg_start
    effective_min = min(min_keep, seg_duration * 0.5)
    for ks, ke in keep_ranges:
        overlap = max(0.0, min(seg_end, ke) - max(seg_start, ks))
        if overlap >= effective_min:
            return True
    return False
```

### Step 2: 修改 `export_srt` (export_service.py:188-233)

**当前逻辑:**
```python
deletions = _get_confirmed_deletions(edits)
subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

kept: list[dict] = []
for seg in subtitle_segs:
    if not _overlaps_deletions(seg["start"], seg["end"], deletions):
        kept.append(seg)
```

**替换为 (接受可选的 media_duration 参数):**

修改 `export_srt` 签名增加 `media_duration` 参数:

```python
def export_srt(
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_duration: float = 0.0,
) -> dict:
```

修改内部逻辑:

```python
deletions = _get_confirmed_deletions(edits)
total_duration = _get_media_duration(segments, edits, media_duration)
keep_ranges = _compute_keep_ranges(total_duration, deletions)

subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

kept: list[dict] = []
for seg in subtitle_segs:
    if _subtitle_survives_in_keep_ranges(seg["start"], seg["end"], keep_ranges):
        kept.append(seg)
```

### Step 3: `main.py` `_handle_export_subtitle` 传递 `media_duration` (main.py:111-129)

**当前调用:**
```python
return export_srt(
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
)
```

**替换为:**
```python
media_duration = project.media.duration if project.media else 0.0
return export_srt(
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    media_duration=media_duration,
)
```

> **参数模式说明：** `export_srt` 只需要 `media_duration: float`（单个数值），而 `export_video`/`export_audio` 需要完整的 `media_info: dict`（用于 `has_video` 检测等）。因此 B1 传递 `project.media.model_dump()` 而 B2 传递 `project.media.duration`，两者均正确。`media_duration` 直接通过 Pydantic model 属性访问，避免不必要的 `model_dump()` 字典分配。

### 保留 `_overlaps_deletions`

`_overlaps_deletions` 函数保留在文件中（可能有其他调用者），但 `export_srt` 不再使用它。

### 说明：时间轴调整逻辑无需修改

`export_srt` 的字幕筛选改用 `keep_ranges`（而非 deletions），但筛选通过后的 `cumulative_offset` 时间轴调整循环**仍使用 deletions 计算偏移量**。这是正确的：keep_ranges 用于判断"哪些字幕在导出视频中还活着"，deletions 用于计算"前面的删除总共移除了多少时间"。两者语义不同，但数据来源一致（deletions 是 keep_ranges 的逆），无需修改时间轴调整部分。

### B2 测试计划

1. **单元测试**: 构造 deletions=[(5, 15)], subtitle seg=(6, 10)，验证 `_subtitle_survives_in_keep_ranges` 返回 False（完全被覆盖）
2. **单元测试**: 构造 deletions=[(5, 15)], subtitle seg=(14, 20)，验证返回 True（有 1s 保留 > 0.3s 阈值）
3. **单元测试**: 短字幕 (0.2s 长) 完全位于 keep_range 中，验证返回 True（不会因 `min_keep=0.3` 误排）
4. **集成测试**: 同一 project 导出 video 和 SRT，验证 SRT 字幕时间线与视频中保留的内容对应

---

## C2 [FEATURE] 双击时间块定位到 Timeline 对应位置

### 目标

双击波形编辑器中的字幕/静音块时，右侧 Timeline 自动滚动定位到对应行，视频跳转到该段起始时间。

### 涉及文件

1. `frontend/src/components/waveform/SegmentBlocksLayer.vue` -- 新增 dblclick
2. `frontend/src/components/waveform/WaveformEditor.vue` -- 透传事件
3. `frontend/src/pages/WorkspacePage.vue` -- 处理事件
4. `frontend/src/components/workspace/Timeline.vue` -- 新增 `watch(selectedSegmentId)` + `scrollIntoView`

> **现状确认：** Timeline.vue 已有 `selectedSegmentId` prop（line 14），并在模板中用于高亮当前行（`is-selected="selectedSegmentId === seg.id"`），但**尚未实现** `watch(selectedSegmentId)` + `scrollIntoView` 自动滚动。此逻辑需在 C2 中新增。

### Step 1: SegmentBlocksLayer.vue -- 新增 emit 和 handler

**在 emit 定义中新增 `seek-segment` 事件 (line 16-19):**

当前:
```typescript
const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
}>()
```

替换为:
```typescript
const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
}>()
```

**新增 `handleBlockDoubleClick` 函数 (在 `handleBlockContextMenu` 之后):**

```typescript
function handleBlockDoubleClick(block: Block) {
  emit("seek-segment", block.seg)
}
```

**模板添加 `@dblclick`:**

在 `v-for="block in visibleBlocks"` 的 div 上:
```html
@dblclick="handleBlockDoubleClick(block)"
```

### Step 2: WaveformEditor.vue -- 透传 seek-segment

**emit 定义新增 `seek-segment` (line 21-26):**

当前:
```typescript
const emit = defineEmits<{
  seek: [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
}>()
```

替换为:
```typescript
const emit = defineEmits<{
  seek: [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]
}>()
```

**新增 handler (在 `handleDeleteSegment` 之后):**
```typescript
function handleSeekSegment(segment: Segment) {
  emit("seek-segment", segment)
}
```

**模板 SegmentBlocksLayer 上新增 `@seek-segment` 绑定:**
```html
@seek-segment="handleSeekSegment"
```

### Step 3: WorkspacePage.vue -- 处理 seek-segment 事件

**在 `<WaveformEditor>` 标签上添加事件绑定 (line 739-742 附近):**

```html
@seek-segment="handleSeekSegment"
```

**新增 handler 函数 `handleSeekSegment` (在 `handleDeleteSegment` 附近):**

```typescript
function handleSeekSegment(seg: Segment) {
  editSelectedSegmentId.value = seg.id
  handleSeek(seg.start)
}
```

WorkspacePage 已将 `editSelectedSegmentId` 绑定到 Timeline 的 `selectedSegmentId` prop（line 714）。

### Step 4: Timeline.vue -- 新增 scrollIntoView 自动滚动

**新增 `watch` (在 `<script setup>` 的 `getSegmentState` 函数之后):**

```typescript
import { watch, nextTick } from "vue"

watch(
  () => props.selectedSegmentId,
  (id) => {
    if (!id) return
    nextTick(() => {
      const el = document.querySelector(`[data-segment-id="${id}"]`)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" })
      }
    })
  },
)
```

**TranscriptRow.vue 根元素添加 `data-segment-id` 属性 (line 117):**

在 `<div class="flex items-start gap-2 px-3 py-2 ...">` 上新增:
```html
:data-segment-id="segment.id"
```

**SilenceRow.vue 根元素同样添加 `data-segment-id` 属性:**

```html
:data-segment-id="segment.id"
```

> `block: "nearest"` 避免多层嵌套滚动容器下 `scrollIntoView` 失效的问题。

### C2 测试计划

1. **手动测试**: 双击字幕块，验证右侧 Timeline 滚动到对应行，视频跳转到字幕开始时间
2. **手动测试**: 双击静音块，验证右侧 Timeline 高亮对应行
3. **手动测试**: 单击 body 行为不变（仅 select-range），不触发 Timeline 滚动
4. **单元测试**: 验证 SegmentBlocksLayer `@dblclick` emit 包含正确的 segment 数据

---

## 实施顺序总结

| 顺序 | ID | 严重度 | 预计改动文件数 | 理由 |
|------|-----|--------|---------------|------|
| 1 | **B1** | HIGH | 2 (export_service.py, main.py) | 导出截断直接根因，用户可感知 |
| 2 | **B3+B4** | HIGH+MEDIUM | 1 (project_service.py) | 同一函数修改，建议合并 commit |
| 3 | **B2** | HIGH | 2 (export_service.py, main.py) | 依赖 B1 的 `_get_media_duration` 新签名，需在 B1 完成后实施 |
| 4 | **C2** | FEATURE | 4 (.vue) | 独立的 UX 改进，不依赖其他修复 |

## 回滚方案

每项修复都是独立的小改动，可通过 `git revert` 逐项回滚。各修复之间依赖关系如上表所示：B2 依赖 B1 的 `media_duration` 参数，其余项目独立。

# Milo-Cut 审计报告 #4 -- 导出系统、SubtitleTrim、时间轴交互

**日期:** 2026-05-15
**审计范围:** 导出逻辑、SubtitleTrim 空白去除、时间轴交互、新导出界面需求
**审核:** 经架构师审计，已根据反馈修正（详见文末审计意见章节）

---

## B1 [HIGH] `_get_media_duration` 低估实际媒体时长导致导出截断（含 `export_audio` 缺少 media_info）

### 问题

`export_service.py` 中的 `_get_media_duration` 函数通过 segments 和 edits 的最大 end 值来计算媒体总时长：

```python
# export_service.py:251-254
def _get_media_duration(segments, edits):
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    return max(all_times) if all_times else 0.0
```

但 `MediaInfo` 模型已经包含 `duration` 字段（来自 ffprobe 探测的实际媒体时长），该字段完全未被使用。当实际媒体文件时长超过任何 segment/edit 的 end 值时（例如：字幕结束后还有一段无人声的片尾画面），`_compute_keep_ranges` 计算的最后一个 keep range 会在 segment 最大 end 处截断，导致导出视频的尾部丢失。

这就是用户报告的"最后几个字幕块内容缺漏"的根因：当末尾字幕块的音频/视频超出最后一个 segment end 时，超出部分被静默裁切。

**同时**，`export_audio` 函数签名完全不包含 `media_info` 参数（与 `export_video` 不一致），属于同一个根因的调用链缺口，合并修复。

### 受影响函数

- `export_video()` -- 传递 `media_info` 但仅用于 `has_video` 检测，未使用 `duration`
- `export_audio()` -- **根本不接收 `media_info` 参数**（同属于 B1）
- `export_srt()` -- 通过 `_get_media_duration` 隐式影响时间轴调整（`cumulative_offset` 依赖 deletions 完整性，B1 修复后自动解决）

### 修复方案

**Step 1:** 将 `_get_media_duration` 改为接受可选的 `media_duration` 参数：

```python
def _get_media_duration(segments, edits, media_duration=0.0):
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    computed = max(all_times) if all_times else 0.0
    return max(computed, media_duration)
```

**Step 2:** 在调用处添加防御性日志，防止 `media_duration = 0.0`（ffprobe 失败/未探测）静默退化：

```python
if media_duration <= 0.0:
    logger.warning("media_duration unavailable ({}), export may be truncated", media_duration)
```

**Step 3:** `_compute_keep_ranges` 对每个 keep range 端点做 min 钳位，防止 segment/edit 的 end 值因浮点精度问题略大于 ffprobe 的 duration：

```python
def _compute_keep_ranges(total_duration, deletions):
    # ... existing merge logic ...
    if current < total_duration:
        keep.append((min(current, total_duration), total_duration))
    # Also clamp earlier keep ranges:
    return [(min(s, total_duration), min(e, total_duration)) for s, e in keep]
```

**Step 4:** `export_video` 从 `media_info.get("duration", 0.0)` 提取实际时长并传入。

**Step 5:** `export_audio` 新增 `media_info` 参数，同样提取 duration 传入；`main.py` 中 `_handle_export_audio` 传递 `project.media.model_dump() if project.media else None`。

**文件:** `core/export_service.py`, `main.py`

---

## B2 [HIGH] SRT 导出与视频导出使用不同的字幕筛选标准

### 问题

`export_srt` 通过 `_overlaps_deletions` 判断字幕是否应被排除，使用 0.01s 重叠阈值：

```python
# export_service.py:294-305
def _overlaps_deletions(start, end, deletions):
    for del_start, del_end in deletions:
        overlap_start = max(start, del_start)
        overlap_end = min(end, del_end)
        if overlap_end - overlap_start > 0.01:   # <-- 0.01s
            return True
    return False
```

而前端的 `isOverlapping` 使用 **0.3s** 阈值。两个函数的语义不同：

- **前端 `isOverlapping` (0.3s)**：UI 层判断"是否应该标记这条字幕为受影响"——目的是容错，避免微小时间误差误标。
- **后端 `_overlaps_deletions` (0.01s)**：导出层判断"这条字幕是否应该从 SRT 导出中排除"——目的是精确。

简单统一阈值是错误的。例如将后端改为 0.3s：一条字幕与删除范围有 0.29s 的真实重叠，SRT 仍保留它，但视频导出已裁掉那 0.29s，字幕和视频依然不同步。

### 根因

前后端对"哪些字幕应该从导出中排除"的判断标准没有统一的数据源。SRT 当前独立地用 deletions 做重叠判断，而视频导出用 keep_ranges（deletions 的逆）做裁切。两者的计算路径不同，任何阈值调整都无法保证一致性。

### 修复方案（方向 A，推荐）

以视频导出的 `keep_ranges` 为权威，SRT 导出的字幕筛选依据 keep_ranges 而非 deletions：

```python
def _subtitle_survives_in_keep_ranges(seg_start, seg_end, keep_ranges, min_keep=0.3):
    """字幕在导出视频中至少有 min_keep 秒的内容被保留，才写入 SRT。"""
    for ks, ke in keep_ranges:
        overlap = max(0.0, min(seg_end, ke) - max(seg_start, ks))
        if overlap >= min_keep:
            return True
    return False
```

修改后的 `export_srt` 流程：

```python
def export_srt(segments, edits, output_path, media_duration=0.0):
    deletions = _get_confirmed_deletions(edits)
    total_duration = _get_media_duration(segments, edits, media_duration)
    keep_ranges = _compute_keep_ranges(total_duration, deletions)

    subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

    kept = []
    for seg in subtitle_segs:
        if _subtitle_survives_in_keep_ranges(seg["start"], seg["end"], keep_ranges):
            kept.append(seg)
    # ... 时间戳调整逻辑不变
```

**方向 B（长期方案）：** 在 confirmed edit 写入时，由后端统一计算并标记哪些字幕受影响，导出时直接读标记，前后端不再各自算一遍。

### 当前阶段选择

方向 A 在本次实现，方向 B 作为架构技术债列入下文"系统性问题观察"。

**文件:** `core/export_service.py`

---

## B3 [HIGH] SubtitleTrim 未忽略已标记删除的字幕

### 问题

用户需求：如果某条字幕已标记为删除（confirmed delete），SubtitleTrim 检测时应无视它。

当前 `generate_subtitle_keep_ranges` 的实现包含所有 `type == "subtitle"` 的段落：

```python
# project_service.py:857-860
subtitle_segs = sorted(
    [s for s in self._current.transcript.segments if s.type == SegmentType.SUBTITLE],
    key=lambda s: s.start,
)
```

如果一个字幕已被用户标记为 confirmed delete，它在 keep_ranges 中仍被当作"保留区域"对待，导致：
- 该字幕 + padding 的范围被纳入 keep_ranges
- 本应被删除的字幕区域反而阻止了删除范围的生成
- confirmed delete 标注被 SubtitleTrim 的结果"覆盖"

### 补充：confirmed keep 对称场景

**已 confirmed keep（用户手动标记保留）的字幕对应的时间范围**理论上不应被 SubtitleTrim 生成 pending delete 覆盖。否则产生 confirmed keep vs pending delete 的冲突，后续合并逻辑需额外处理。

### 修复方案

在构建 subtitle_segs 时排除已有 confirmed delete 编辑的字幕；同时检查 confirmed keep 编辑以避免冲突：

```python
# 收集已确认删除的字幕 ID
confirmed_deleted_ids = {
    e.target_id for e in self._current.edits
    if e.status == EditStatus.CONFIRMED and e.action == "delete" and e.target_id
}

# 收集已确认保留的字幕 ID
confirmed_kept_ids = {
    e.target_id for e in self._current.edits
    if e.status == EditStatus.CONFIRMED and e.action == "keep" and e.target_id
}

# 排除已确认删除的字幕
# 对 confirmed keep 的字幕，保留在 keep_ranges 中（不应生成 delete range 覆盖它们）
subtitle_segs = sorted(
    [s for s in self._current.transcript.segments
     if s.type == SegmentType.SUBTITLE and s.id not in confirmed_deleted_ids],
    key=lambda s: s.start,
)
```

confirmed kept 字幕自然保留在 keep_ranges 中（因为它们没被排除），而 SubtitleTrim 生成的 delete ranges 只在 gaps 之间，不会与 keep_ranges 内的 confirmed kept 字幕冲突。

**文件:** `core/project_service.py`

---

## B4 [MEDIUM] `generate_subtitle_keep_ranges` 的 already_covered 检查忽略 REJECTED 状态

### 问题

`already_covered` 检查仅匹配 `CONFIRMED` 和 `PENDING` 状态的编辑：

```python
# project_service.py:894-900
already_covered = any(
    e.action == "delete"
    and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)
    # REJECTED 被遗漏
    and abs(e.start - start) < 0.05
    and abs(e.end - end) < 0.05
    for e in existing_edits
)
```

如果用户之前对某个 SubtitleTrim 编辑做了"已保留"（rejected），重新运行 SubtitleTrim 时会创建**新的** PENDING 编辑覆盖同一范围。这与静音检测去重 B2 修复是同一个模式。

### 修复方案

```python
and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
```

### 技术债

`already_covered` 逻辑在静音检测和 SubtitleTrim 中重复出现，应提取为共用工具函数 `_is_range_already_covered(edits, start, end)`，而非在每个生成函数中各自维护一份判断逻辑。建议在本次或下一次重构中提取。

**文件:** `core/project_service.py`

---

## C1 [FEATURE] 新建导出界面

### 需求

用户要求：
1. **删除现有导出按钮**（Export Video、Export SRT、Export Audio），仅保留一个跳转导出界面的按钮
2. **导出界面允许编码设置**（视频编码器、音频编码器、码率、分辨率等）
3. **导出界面允许预览播放**（跳过所有标注已删除区域的播放）
4. **导出界面允许导出通用时间线格式**（EDL、FCPXML 等）

### 设计方案概要

#### 新建 ExportPage.vue

路由级别的新页面，从 WorkspacePage 的导出按钮跳转。接收 project 数据作为 props 或通过共享状态传递。

#### 编码设置

- 视频编码器选择：H.264 (libx264)、H.265 (libx265)、VP9 等
- 码率控制：CRF 值 / 目标码率
- 分辨率：原始 / 1080p / 720p / 自定义
- 音频编码器：AAC / MP3 / Opus
- 音频码率：128k / 192k / 256k
- 预设速度：fast / medium / slow

#### 预览播放（跳过删除区域）

使用 HTML5 video 元素 + 自定义逻辑跳过删除区域：

- 监听 `timeupdate` 事件，当 `currentTime` 进入 confirmed delete 范围时自动 `seek` 到范围 end
- 在时间轴上可视化显示保留/删除区域

**已知风险：** HTML5 video 的 `timeupdate` 触发间隔约 250ms。如果一个删除范围短于 250ms，播放器可能直接越过而不触发 seek。实现时需在 seek 后立即检查当前时间是否仍在删除区间内（防止 seek 精度不足），必要时使用 `requestAnimationFrame` 轮询替代 `timeupdate`。

#### 通用时间线格式导出

经调研 DaVinci Resolve 和 Premiere Pro 的导入支持，推荐格式优先级如下：

| 优先级 | 格式 | 理由 |
|--------|------|------|
| **第一优先** | **EDL (CMX3600) + FCPXML** | EDL 覆盖面最广，几乎所有 NLE 都能读，实现最简单；FCPXML 信息更丰富，Resolve 和 Premiere 都支持，且不需要 reel 号。两者并行实现成本不高。 |
| **第二优先** | **OTIO** | Python 官方库 `opentimelineio`，API 清晰。Resolve 原生支持，Premiere 26.0 起正式支持。实现成本低到中。 |
| **审阅用途** | **CSV** | Resolve/Premiere 不支持导入 CSV 作为时间线。定位为"人类可读的剪辑清单 / 审阅格式"，不作为 NLE 导入格式。 |
| **不推荐** | **AAF** | 实现复杂度远超需求，Python 侧缺少轻量级库，Milo-Cut 的简单剪辑结构不需要 AAF。 |

**EDL 帧率注意事项：** Milo-Cut 时间轴是秒数，生成 EDL 时需从 `media_info.fps` 换算为帧号。如果 fps 不可用，需要 fallback（默认 25fps）。

#### 实现范围

分阶段实施：
1. **Phase 1**: 基础界面框架 + 合并导出按钮（替换现有三个按钮）
2. **Phase 2**: 编码设置面板
3. **Phase 3**: 预览播放（跳过删除区域，注意 timeupdate 精度风险）
4. **Phase 4**: 通用时间线格式导出（EDL + FCPXML 优先，OTIO 后续，CSV 为审阅格式）

---

## C2 [FEATURE] 双击时间块定位到 Timeline 对应位置

### 需求

在波形编辑器（WaveformEditor / SegmentBlocksLayer）中**双击**某个时间块（包括字幕块和静音块）时，右侧 Timeline 面板应自动滚动定位到对应的行。

### UX 决策：双击而非单击

- **单击** body：保持现有行为 `select-range`（选择时间范围）。若同时触发 Timeline 滚动，用户浏览波形时随意点击会产生干扰。
- **双击** body：意图明确，不会与单击选范围冲突。适合"我要在 Timeline 中查看/编辑这一段"的明确意图。

### 现状分析

当前 `handleBlockMouseDown` 完全没有双击处理：

```
SegmentBlocksLayer (mousedown body → select-range)
  → WaveformEditor (select-range)
    → WorkspacePage (handleSelectRange → selectEditRange)
```

`selectEditRange` 只设了 `selectedRange`，**没有设 `selectedSegmentId`**，不触发 Timeline 滚动。

### 设计方案

1. **SegmentBlocksLayer** 新增 `@dblclick` 事件处理器，发出 `seek-segment` 事件
2. **WaveformEditor** 透传该事件
3. **WorkspacePage** 处理该事件，设置 `editSelectedSegmentId` + 调用 `handleSeek`
4. **Timeline** 利用已有 `selectedSegmentId` prop + `watch` + `scrollIntoView` 自动滚动

### 滚动实现注意事项

- `scrollIntoView` 在 Timeline 有多层嵌套滚动容器时可能失效。使用 `behavior: 'smooth', block: 'nearest'`
- 确认滚动容器的 `overflow` 设置是 `overflow-y: auto`（当前已是）

### 修改后的代码流

```
SegmentBlocksLayer @dblclick → emit("seek-segment", segment)   (新增)
  ↓
WaveformEditor 透传 seek-segment
  ↓
WorkspacePage.handleSeekSegment(seg)
  ├── editSelectedSegmentId.value = seg.id   → Timeline selectedSegmentId 更新
  ├── handleSeek(seg.start)                  → 视频跳转
  └── Timeline watch(selectedSegmentId)      → scrollIntoView 滚动
```

### 实现要点

```typescript
// SegmentBlocksLayer.vue - emit 新增 + dblclick handler
const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]          // C2: 新增
}>()

function handleBlockDoubleClick(block: Block) {
  emit("seek-segment", block.seg)
}
```

```html
<!-- 模板添加 @dblclick -->
<div
  v-for="block in visibleBlocks"
  @mousedown="handleBlockMouseDown(block, $event)"
  @dblclick="handleBlockDoubleClick(block)"    <!-- C2: 新增 -->
  @contextmenu="handleBlockContextMenu(block, $event)"
>
```

**涉及文件:** `SegmentBlocksLayer.vue`, `WaveformEditor.vue`, `WorkspacePage.vue`, `Timeline.vue`

---

## Bug 优先级汇总

| ID | 严重度 | 标题 | 文件 |
|----|--------|------|------|
| B1 | HIGH | `_get_media_duration` 低估媒体时长导致导出截断（含 `export_audio` 缺失 media_info） | `core/export_service.py`, `main.py` |
| B2 | HIGH | SRT 导出字幕筛选标准与视频导出不一致（方向 A：以 keep_ranges 为权威） | `core/export_service.py` |
| B3 | HIGH | SubtitleTrim 未忽略已标记删除/保留的字幕 | `core/project_service.py` |
| B4 | MEDIUM | `already_covered` 忽略 REJECTED 状态（+ 提取共用工具函数技术债） | `core/project_service.py` |

## Feature 任务

| ID | 标题 | 预计范围 |
|----|------|----------|
| C1 | 新建导出界面（编码设置 + 预览播放 + EDL/FCPXML/OTIO 导出） | 大（分 4 阶段） |
| C2 | 双击时间块定位到 Timeline | 小（4 文件） |

## 建议实施顺序

| 顺序 | ID | 理由 |
|------|-----|------|
| 1 | **B1** | 导出截断直接根因，用户可感知，优先级最高 |
| 2 | **B3** | SubtitleTrim 已删除字幕冲突，逻辑修复 |
| 3 | **B4** | 一行修复，配合提取 already_covered 共用函数 |
| 4 | **B2** | SRT/视频导出统一以 keep_ranges 为权威，需重新设计 |
| 5 | **C2** | 小而独立的 UX 改进，双击定位 |
| 6 | **C1** | 最后实施，依赖前面的 B1-B2 导出修复结果 |

---

## 系统性问题观察

### 1. 前后端没有共享的时间轴计算层

B2 暴露的"前后端各自独立判断字幕是否应被删除"，根因是时间轴计算逻辑分散在前端 TypeScript (`isOverlapping`, `resolveSegmentState`) 和后端 Python (`_overlaps_deletions`, `_compute_keep_ranges`) 两处。随着功能增加，这类不一致会继续出现。

**长期方案：** 让后端成为 keep_ranges / deletions 计算的唯一权威，前端仅做展示，所有判断通过 API 从后端获取。这是架构方向的选择，短期不一定要改，但应列入技术债。

### 2. EditStatus 状态机缺乏文档

B3、B4 的问题都源于开发者对 `CONFIRMED / PENDING / REJECTED` 三种状态的语义理解不统一。建议在代码库中补充状态机说明，明确每种状态下 edit 对各个功能模块（SubtitleTrim、静音检测、导出、去重检查）的可见性和行为，而非让每个函数各自决定要检查哪些状态。

---

## 附录: 涉及代码详情

### A. 导出完整链路 (`core/export_service.py`)

#### A1. 入口 -- `export_video` (line 29-109)

```python
def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,       # <-- 包含 duration 但只用了 width
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    try:
        output_path = _validate_output_path(output_path)
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits)  # <-- B1: 未用 media_info.duration

        has_video = True
        if media_info:
            has_video = media_info.get("width", 0) > 0  # <-- 仅取 width，忽略 duration

        # ... _compute_keep_ranges、逐段 _extract_segment、_concat_segments
```

#### A2. 入口 -- `export_audio` (line 112-185)

```python
def export_audio(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    # B1: 缺少 media_info 参数
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    try:
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits)  # <-- B1: 同样问题
```

#### A3. 入口 -- `export_srt` (line 188-233)

```python
def export_srt(
    segments: list[dict],
    edits: list[dict],
    output_path: str,
) -> dict:
    try:
        deletions = _get_confirmed_deletions(edits)
        subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

        kept: list[dict] = []
        for seg in subtitle_segs:
            if not _overlaps_deletions(seg["start"], seg["end"], deletions):  # <-- B2: 应用 keep_ranges 替代
                kept.append(seg)

        kept.sort(key=lambda s: s["start"])

        cumulative_offset = 0.0
        del_idx = 0
        adjusted: list[tuple[float, float, str]] = []

        for seg in kept:
            seg_start = seg["start"]
            seg_end = seg["end"]

            while del_idx < len(deletions) and deletions[del_idx][1] <= seg_start:
                cumulative_offset += deletions[del_idx][1] - deletions[del_idx][0]
                del_idx += 1

            new_start = max(0.0, seg_start - cumulative_offset)
            new_end = max(0.0, seg_end - cumulative_offset)
            adjusted.append((new_start, new_end, seg.get("text", "")))
```

#### A4. Helper -- `_get_media_duration` (line 251-254) **[B1 根因]**

```python
def _get_media_duration(segments: list[dict], edits: list[dict]) -> float:
    """Compute total media duration from segments and edits."""
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    return max(all_times) if all_times else 0.0
    # B1: 完全忽略了 media_info.duration。
    # 当媒体文件比所有 segment/edit end 更长时（如片尾无声画面），
    # 返回值小于实际媒体时长，导致 _compute_keep_ranges 截断末尾。
```

#### A5. Helper -- `_compute_keep_ranges` (line 257-277)

```python
def _compute_keep_ranges(
    total_duration: float,                        # <-- 来自 _get_media_duration
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
        keep.append((current, total_duration))    # <-- B1 修复后需对端点做 min 钳位

    return keep
```

#### A6. Helper -- `_overlaps_deletions` (line 294-305) **[B2 根因]**

```python
def _overlaps_deletions(
    start: float,
    end: float,
    deletions: list[tuple[float, float]],
) -> bool:
    for del_start, del_end in deletions:
        overlap_start = max(start, del_start)
        overlap_end = min(end, del_end)
        if overlap_end - overlap_start > 0.01:     # B2: 应改用 keep_ranges 判断而非 deletions
            return True
    return False
```

对比前端 `segmentHelpers.ts`：
```typescript
// frontend/src/utils/segmentHelpers.ts
const MIN_OVERLAP_SECONDS = 0.3  // UI 层容错阈值，与导出层语义不同

export function isOverlapping(
  edit: EditDecision,
  seg: Segment,
  minOverlap: number = MIN_OVERLAP_SECONDS,
): boolean {
  const overlap = Math.max(0, Math.min(edit.end, seg.end) - Math.max(edit.start, seg.start))
  return overlap > minOverlap
}
```

#### A7. Helper -- `_get_confirmed_deletions` (line 240-248)

```python
def _get_confirmed_deletions(edits: list[dict]) -> list[tuple[float, float]]:
    """Extract confirmed deletion ranges from edit decisions."""
    result = []
    for edit in edits:
        if (edit.get("action") == "delete"
                and edit.get("status") == "confirmed"):
            result.append((edit["start"], edit["end"]))
    result.sort(key=lambda x: x[0])
    return result
```

---

### B. `main.py` 导出处理器 (line 83-155)

```python
# _handle_export_video (line 83-109) -- 已传递 media_info
return export_video(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    media_info=project.media.model_dump() if project.media else None,  # <-- 已传
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)

# _handle_export_audio (line 130-155) -- B1: 缺少 media_info
return export_audio(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    # B1: 缺少 media_info=project.media.model_dump() if project.media else None
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)
```

---

### C. SubtitleTrim 后端 (`core/project_service.py`)

#### C1. `generate_subtitle_keep_ranges` (line 848-924) **[B3 + B4 修复点]**

```python
def generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict:
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    # B3: 包含了所有 subtitle，未排除已确认删除的字幕
    subtitle_segs = sorted(
        [s for s in self._current.transcript.segments if s.type == SegmentType.SUBTITLE],
        key=lambda s: s.start,
    )
    # ... keep_ranges 构建、delete_ranges 计算 ...

    # B4: already_covered 只检查 CONFIRMED + PENDING，未检查 REJECTED
    for i, (start, end) in enumerate(delete_ranges):
        already_covered = any(
            e.action == "delete"
            and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)  # <-- B4: 缺少 REJECTED
            and abs(e.start - start) < 0.05
            and abs(e.end - end) < 0.05
            for e in existing_edits
        )
        if not already_covered:
            new_edits.append(EditDecision(
                id=f"edit-subtitle-trim-{i:04d}",
                start=start, end=end,
                action="delete", source="subtitle_trim",
                status=EditStatus.PENDING, priority=100,
                target_type="range",
            ))

    updated = self._current.model_copy(update={"edits": existing_edits + new_edits})
    self._current = updated
```

#### C2. `delete_subtitle_trim_edits` (line 482-496)

```python
def delete_subtitle_trim_edits(self) -> dict:
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    remaining_edits = [
        e for e in self._current.edits
        if e.source != "subtitle_trim"
    ]
    updated = self._current.model_copy(update={"edits": remaining_edits})
    self._current = updated
```

---

### D. 前端导出 composable (`frontend/src/composables/useExport.ts`)

```typescript
export function useExport(project: Ref<Project | null>) {
  const { createTask, startTask, activeTask, isRunning } = useTask()

  async function exportVideo(outputPath?: string): Promise<boolean> { /* createTask("export_video") */ }
  async function exportSrt(outputPath?: string): Promise<boolean>   { /* createTask("export_subtitle") */ }
  async function exportAudio(outputPath?: string): Promise<boolean> { /* createTask("export_audio") */ }

  const confirmedEdits = computed(() =>
    (project.value?.edits ?? []).filter(e => e.status === "confirmed" && e.action === "delete")
  )
}
```

---

### E. Timeline 与导出联动

```
User confirms edits in Timeline (TranscriptRow / SilenceRow)
  -> WorkspacePage.handleToggleEditStatus(seg)
    -> useSegmentEdit.toggleEditStatus(seg)
      -> call("update_edit_decision" | "mark_segments")
        -> project_service 更新 edits
          -> call("get_project") 返回完整的 project
            -> emit("project-updated", project)
              -> projectRef 更新
                -> Timeline 重新渲染 (resolveSegmentState 计算新状态)
                -> exportVideo/exportSrt/exportAudio 读取同一份 project.edits

导出三种方式:
  export_video:  _get_confirmed_deletions → _compute_keep_ranges → ffmpeg 提取+concat
  export_srt:    exclude overlapped subtitles (→ B2: 改用 keep_ranges) → adjust timestamps
  export_audio:  _get_confirmed_deletions → _compute_keep_ranges → ffmpeg 提取+concat (has_video=False)
```

---

### F. 当前 WorkspacePage 导出按钮 (`frontend/src/pages/WorkspacePage.vue`, line 613-637)

```html
<!-- C1: 需替换为单个"跳转导出界面"按钮 -->
<button @click="handleExportVideo">Export Video</button>
<button @click="handleExportSrt">Export SRT</button>
<button @click="handleExportAudio">Export Audio</button>
```

---

### G. 时间轴区块组件 (`frontend/src/components/waveform/SegmentBlocksLayer.vue`)

#### G1. 当前无 dblclick 处理 (line 127-161)

```typescript
function handleBlockMouseDown(block: Block, e: MouseEvent) {
  selectedBlockId.value = block.seg.id
  const edge = detectEdge(e)
  if (edge === "body") {
    emit("select-range", block.seg.start, block.seg.end)  // 单击 body: 只选范围
    return
  }
  // edge drag: 调整边界...
}
// C2: 缺少 handleBlockDoubleClick
```

#### G2. 模板 -- 需添加 @dblclick

```html
<div
  v-for="block in visibleBlocks"
  :key="block.seg.id"
  @mousedown="handleBlockMouseDown(block, $event)"
  @dblclick="handleBlockDoubleClick(block)"           <!-- C2: 新增 -->
  @contextmenu="handleBlockContextMenu(block, $event)"
>
```

#### G3. WaveformEditor emit 新增 (line 21-26)

```typescript
const emit = defineEmits<{
  seek: [time: number]
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
  "delete-segment": [segmentId: string]
  "seek-segment": [segment: Segment]     // C2: 新增
}>()
```

---

### H. `MediaInfo` 模型 (`core/models.py`, line 76-88)

```python
class MediaInfo(BaseModel, frozen=True):
    path: str
    media_hash: str = ""
    duration: float = 0.0       # <-- ffprobe 探测的实际时长，B1: 导出未使用
    format: str = ""
    width: int = 0               # <-- export_video 只用了这个
    height: int = 0
    fps: float = 0.0             # <-- EDL 导出需要帧率（C1 Phase 4）
    audio_channels: int = 0
    sample_rate: int = 0
    bit_rate: int = 0
    proxy_path: str | None = None
    waveform_path: str | None = None
```

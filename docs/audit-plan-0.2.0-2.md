# Milo-Cut 实施计划 -- 审计报告 0.2.0-2 (v2)

**基于:** 用户需求 2026-05-16 + 架构师审计意见
**日期:** 2026-05-16
**范围:** D-1, D-2, D-3
**实施顺序:** D-3 -> D-1 -> D-2

---

## 需求概述

三项针对 DetectSilence 功能的调整:

1. **D-1 [FEATURE]** Margin 缩边 -- 静音检测后，对每个静音区间两侧各收缩 margin 值
2. **D-2 [FEATURE]** 字幕保护 Padding -- 静音区间主动避让字幕扩展区，裁剪静音而非字幕
3. **D-3 [TWEAK]** Min Duration 标尺调整 -- 范围从 0.1-3.0s (step 0.1) 改为 0.05-2.0s (step 0.05)

---

## 修正后的流水线架构 (v2)

v1 的致命错误: D-2 试图修改 `_resolve_subtitle_overlap` (遍历字幕段、裁剪字幕)，而实际需求是**裁剪静音区间以保护字幕**。v2 将 D-2 提前到创建 EditDecision 之前，直接裁剪 raw silence ranges。

```
FFmpeg 静音检测 -> raw silences
  |
  v
D-1: margin 缩边 (每个静音区间两侧收缩，丢弃 <=0 的)
  |
  v
D-2: padding 字幕保护 (用字幕扩展区裁剪静音区间)
  |
  v
创建 Segment(SILENCE) + EditDecision (基于裁剪后的 silences)
  |
  v
去重 + 保存
```

**关键变化:** `_resolve_subtitle_overlap()` 不再被调用。静音已主动避让字幕，字幕段无需任何修改。配置项 `trim_subtitles_on_silence_overlap` 废弃。

---

## D-3 [TWEAK] Min Duration 标尺调整

**严重度:** LOW | **风险:** LOW (含性能提示) | **预计改动:** 2 文件

### 目标

将 Min Duration 滑块范围从 `0.1-3.0s (step 0.1)` 调整为 `0.05-2.0s (step 0.05)`。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/WorkspacePage.vue` | 滑块 min/max/step + 显示精度 + 性能提示 |

### Step 1: 修改滑块参数 (WorkspacePage.vue:468-475)

**当前:**
```html
<input type="range" v-model.number="silenceMinDuration"
       min="0.1" max="3.0" step="0.1" class="w-full mt-1" />
```

**改为:**
```html
<input type="range" v-model.number="silenceMinDuration"
       min="0.05" max="2.0" step="0.05" class="w-full mt-1" />
```

### Step 2: 显示精度 (WorkspacePage.vue:467)

`silenceMinDuration.toFixed(1)` -> `silenceMinDuration.toFixed(2)`

### Step 3: 性能提示 (新增)

在滑块下方、`silenceMinDuration < 0.2` 时显示黄色提示:

```html
<p v-if="silenceMinDuration < 0.2" class="text-xs text-amber-600 mt-1">
  Very short durations (&lt;0.2s) may generate many clips and affect performance.
</p>
```

### D-3 测试计划

1. 滑块可拖至 0.05, 0.10, 0.15 ... 2.00，显示两位小数
2. min_duration < 0.2 时显示性能警告，>= 0.2 时隐藏
3. min_duration=0.05 后运行静音检测，验证短静音可被检出

---

## D-1 [FEATURE] Margin 缩边

**严重度:** MEDIUM | **风险:** LOW | **预计改动:** 4 文件

### 目标

在 FFmpeg 静音检测完成后、创建 Segment/EditDecision 之前，对每个静音区间两侧各收缩 `margin` 秒。收缩后区间长度 <= 0 则丢弃。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/project_service.py` | `add_silence_results()` 中插入缩边逻辑 |
| `core/config.py` | `_DEFAULT_SETTINGS` 添加 `silence_margin` |
| `main.py` | `_handle_silence_detection()` 传递 margin 参数 |
| `frontend/src/pages/WorkspacePage.vue` | 添加 margin 滑块 + 警告提示 |

### Step 1: 添加配置项 (core/config.py)

```python
"silence_margin": 0.0,
```

### Step 2: 缩边逻辑 (core/project_service.py)

在 `add_silence_results()` 中，**创建 Segment 之前**插入:

```python
def add_silence_results(self, silences: list[dict], margin: float = 0.0) -> dict:
    # ... 前置检查 ...

    # --- D-1: Margin shrink ---
    if margin > 0:
        shrunk = []
        for sil in silences:
            new_start = sil["start"] + margin
            new_end = sil["end"] - margin
            if new_end > new_start:
                shrunk.append({"start": new_start, "end": new_end, "duration": new_end - new_start})
        silences = shrunk

    if not silences:
        return {"success": True, "data": {"message": "No silence ranges after margin shrink"}}

    # ... 后续创建 Segment + EditDecision ...
```

缩边在去重之前执行 (缩边后时间范围变化，去重应基于新值)。

### Step 3: 传递参数 (main.py)

```python
margin = settings.get("silence_margin", 0.0)
store_result = self._project.add_silence_results(result["data"], margin=margin)
```

### Step 4: 前端 UI (WorkspacePage.vue)

#### 4a. 添加 ref + 设置读写

```typescript
const silenceMargin = ref(0.0)
// loadSettings: silenceMargin.value = Number(res.data.silence_margin ?? 0.0)
// saveSilenceSettings: silence_margin: silenceMargin.value,
```

#### 4b. 滑块 UI (Min Duration 之后)

```html
<label class="block mb-2">
  <span class="text-xs text-gray-500">
    Margin (s): {{ silenceMargin.toFixed(2) }}
  </span>
  <input type="range" v-model.number="silenceMargin"
         min="0" max="0.5" step="0.01" class="w-full mt-1" />
  <p v-if="silenceMargin > 0 && silenceMargin * 2 >= silenceMinDuration"
     class="text-xs text-amber-600 mt-1">
    High margin may consume small silence intervals entirely.
  </p>
</label>
```

#### 4c. 约束策略: 警告而非禁用

**不**在运行按钮的 `:disabled` 中添加 margin 约束。仅显示黄色警告提示。用户有权在长静音上使用大 margin。

### D-1 测试计划

1. **单元测试:** margin=0.1, 静音 [1.0, 2.0] -> [1.1, 1.9]
2. **单元测试:** margin=0.5, 静音 [1.0, 1.8] (0.8 < 1.0) -> 丢弃
3. **单元测试:** margin=0 -> 全部保持不变
4. **单元测试:** 全部丢弃后返回 message 而非空列表
5. **手动测试:** margin=0.3, min_duration=0.5 时，按钮仍可点击，显示 amber 警告
6. **手动测试:** 运行后波形上静音块两侧各缩 margin 值

---

## D-2 [FEATURE] 字幕保护 Padding (v2 重构)

**严重度:** MEDIUM | **风险:** MEDIUM | **预计改动:** 5 文件

### 目标 (v2)

在创建 EditDecision **之前**，用字幕扩展区 (字幕 + padding) 裁剪静音区间。静音主动避让字幕，字幕段本身不做任何修改。

### 设计原理

原始静音: [4.0, 9.0]
字幕: [5.0, 8.0], padding=0.3
字幕扩展区: [4.7, 8.3]
裁剪后静音: [4.0, 4.7] 和 [8.3, 9.0]

静音区间被字幕扩展区"切开"，两侧剩余部分保留。字幕段不触碰。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/project_service.py` | 新增 `_trim_silences_around_subtitles()` + 修改 `add_silence_results()` |
| `core/config.py` | 新增 `silence_subtitle_padding`，废弃 `trim_subtitles_on_silence_overlap` |
| `main.py` | 传递 `subtitle_padding` 参数 |
| `frontend/src/pages/WorkspacePage.vue` | 添加 padding 滑块，移除旧 checkbox |
| `tests/test_project_service.py` | 新增 `_trim_silences_around_subtitles` 单元测试 |

### Step 1: 新增裁剪函数 (core/project_service.py)

```python
def _trim_silences_around_subtitles(
    self,
    silences: list[dict[str, float]],
    padding: float = 0.0,
) -> list[dict[str, float]]:
    """Trim silence ranges to avoid subtitle extended regions.

    For each subtitle segment, computes an extended region
    [subtitle.start - padding, subtitle.end + padding].
    Silence ranges are split/cropped to avoid these regions.

    Args:
        silences: Raw silence intervals (after margin shrink).
        padding: Seconds to extend subtitle regions on both sides.

    Returns:
        Filtered/trimmed silence intervals.
    """
    if not silences or padding <= 0:
        return silences

    # Build sorted subtitle segments (SUBTITLE type only)
    subtitle_segs = sorted(
        [s for s in (self._current.transcript.segments if self._current else [])
         if s.type == SegmentType.SUBTITLE],
        key=lambda s: s.start,
    )
    if not subtitle_segs:
        return silences

    # Build subtitle extended regions (merge overlapping)
    extended: list[tuple[float, float]] = []
    for seg in subtitle_segs:
        ext_start = max(0.0, seg.start - padding)
        ext_end = seg.end + padding
        if extended and ext_start <= extended[-1][1]:
            extended[-1] = (extended[-1][0], max(extended[-1][1], ext_end))
        else:
            extended.append((ext_start, ext_end))

    # Trim each silence range against extended regions
    result: list[dict[str, float]] = []
    for sil in silences:
        parts = [(sil["start"], sil["end"])]

        for ext_start, ext_end in extended:
            new_parts: list[tuple[float, float]] = []
            for p_start, p_end in parts:
                if ext_end <= p_start or ext_start >= p_end:
                    # No overlap -- keep entire part
                    new_parts.append((p_start, p_end))
                else:
                    # Overlap -- keep non-overlapping portions
                    if p_start < ext_start:
                        new_parts.append((p_start, ext_start))
                    if ext_end < p_end:
                        new_parts.append((ext_end, p_end))
            parts = new_parts
            if not parts:
                break

        for p_start, p_end in parts:
            if p_end > p_start:
                result.append({"start": p_start, "end": p_end, "duration": p_end - p_start})

    return result
```

**核心逻辑:** 遍历每个静音区间，依次与每个字幕扩展区求差集。静音被切开后保留非重叠部分。

### Step 2: 修改 add_silence_results 签名和流程

```python
def add_silence_results(
    self,
    silences: list[dict],
    margin: float = 0.0,
    subtitle_padding: float = 0.0,
) -> dict:
    """Convert raw silence intervals to Segments + EditDecisions.

    Pipeline: raw silences -> margin shrink -> subtitle padding trim -> create segments/edits.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    # --- D-1: Margin shrink ---
    if margin > 0:
        shrunk = []
        for sil in silences:
            new_start = sil["start"] + margin
            new_end = sil["end"] - margin
            if new_end > new_start:
                shrunk.append({"start": new_start, "end": new_end, "duration": new_end - new_start})
        silences = shrunk

    # --- D-2: Subtitle padding trim ---
    if subtitle_padding > 0:
        silences = self._trim_silences_around_subtitles(silences, padding=subtitle_padding)

    if not silences:
        return {"success": True, "data": {"message": "No silence ranges after processing"}}

    # --- Create Segment + EditDecision (unchanged) ---
    existing = self._current.transcript.segments
    existing_edits = list(self._current.edits)
    new_segments: list[Segment] = []
    new_edits: list[EditDecision] = []
    sil_idx = len([s for s in existing if s.type == SegmentType.SILENCE])

    for sil in silences:
        sil_idx += 1
        seg_id = f"sil-{sil_idx:04d}"
        edit_id = f"edit-{sil_idx:04d}"
        new_segments.append(Segment(id=seg_id, type=SegmentType.SILENCE,
                                     start=sil["start"], end=sil["end"], text=""))
        # 去重 (unchanged)
        already_covered = any(
            e.action == "delete"
            and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING, EditStatus.REJECTED)
            and abs(e.start - sil["start"]) < 0.05
            and abs(e.end - sil["end"]) < 0.05
            for e in existing_edits
        )
        if not already_covered:
            new_edits.append(EditDecision(
                id=edit_id, start=sil["start"], end=sil["end"],
                action="delete", source="silence_detection",
                status=EditStatus.PENDING, target_type="segment", target_id=seg_id,
            ))

    all_segments = list(existing) + new_segments
    all_edits = existing_edits + new_edits

    # --- _resolve_subtitle_overlap 废弃 ---
    # 静音已通过 D-2 主动避让字幕，无需再裁剪字幕段。
    # 保留 trim_subtitles_on_silence_overlap 配置读取以兼容旧项目，
    # 但不再调用 _resolve_subtitle_overlap()。

    # ... 保存项目 (unchanged) ...
```

### Step 3: 废弃旧逻辑

在 `add_silence_results()` 中**移除**以下调用:

```python
# 删除: if settings.get("trim_subtitles_on_silence_overlap", True):
# 删除:     silence_ranges = [(s["start"], s["end"]) for s in silences]
# 删除:     all_segments = self._resolve_subtitle_overlap(all_segments, silence_ranges)
```

`_resolve_subtitle_overlap()` 方法本身保留但标记为 deprecated，避免破坏可能的外部调用。

### Step 4: 配置项 (core/config.py)

```python
# 新增
"silence_subtitle_padding": 0.0,
# 保留但废弃 (向后兼容)
"trim_subtitles_on_silence_overlap": True,
```

### Step 5: 传递参数 (main.py)

```python
subtitle_padding = settings.get("silence_subtitle_padding", 0.0)
store_result = self._project.add_silence_results(
    result["data"], margin=margin, subtitle_padding=subtitle_padding
)
```

### Step 6: 前端 UI (WorkspacePage.vue)

#### 6a. 添加 ref

```typescript
const silenceSubtitlePadding = ref(0.0)
// loadSettings: silenceSubtitlePadding.value = Number(res.data.silence_subtitle_padding ?? 0.0)
// saveSilenceSettings: silence_subtitle_padding: silenceSubtitlePadding.value,
```

#### 6b. 滑块 UI (Margin 滑块之后)

```html
<label class="block mb-2">
  <span class="text-xs text-gray-500">
    Subtitle Padding (s): {{ silenceSubtitlePadding.toFixed(2) }}
  </span>
  <input type="range" v-model.number="silenceSubtitlePadding"
         min="0" max="1.0" step="0.05" class="w-full mt-1" />
  <p v-if="silenceSubtitlePadding > 0" class="text-xs text-gray-400 mt-0.5">
    Silence ranges will be trimmed to stay this far from subtitles.
  </p>
</label>
```

#### 6c. 移除旧 checkbox

删除 "Trim overlapping subtitles" checkbox 及其绑定 (`trimSubtitlesOnOverlap`)。功能已被 `silence_subtitle_padding > 0` 替代。保留 `trimSubtitlesOnOverlap` 变量但不渲染，避免破坏 saveSettings 逻辑 (或从 saveSettings 中移除该字段)。

### Step 7: 单元测试 (tests/test_project_service.py)

```python
class TestTrimSilencesAroundSubtitles:
    """D-2: _trim_silences_around_subtitles"""

    def test_no_overlap_unchanged(self):
        """Silence and subtitle don't overlap -- silence unchanged."""
        # subtitle [10, 12], silence [1, 3], padding=0.3
        # result: [1, 3]

    def test_full_enclosure_split(self):
        """Silence fully encloses subtitle -- split into two parts."""
        # subtitle [5, 8], silence [4, 9], padding=0.3
        # extended: [4.7, 8.3]
        # result: [4, 4.7] and [8.3, 9]

    def test_partial_overlap_crop(self):
        """Silence partially overlaps subtitle -- crop the overlapping end."""
        # subtitle [5, 8], silence [6, 10], padding=0.3
        # extended: [4.7, 8.3]
        # result: [8.3, 10]

    def test_padding_zero_passthrough(self):
        """padding=0 returns all silences unchanged."""

    def test_no_subtitles_passthrough(self):
        """No subtitle segments returns all silences unchanged."""

    def test_adjacent_subtitles_merge(self):
        """Two close subtitles with overlapping extended regions merge."""
        # subtitle [5, 6], [6.2, 7], padding=0.3
        # extended: [4.7, 7.3] (merged)
        # silence [4, 8] -> [4, 4.7] and [7.3, 8]

    def test_silence_fully_inside_extended(self):
        """Silence entirely within extended region -- fully consumed."""
        # subtitle [5, 8], silence [6, 7], padding=0.3
        # extended: [4.7, 8.3]
        # result: [] (empty)

    def test_small_remainder_kept(self):
        """Tiny remaining silence parts are kept (no minimum threshold)."""
        # subtitle [5, 8], silence [4.9, 8.1], padding=0.3
        # extended: [4.7, 8.3]
        # result: [] (4.9 < 4.7 is false, 4.9 inside extended)
        # Actually: [4.9, 4.7] = negative -> skip; [8.3, 8.1] = negative -> skip
        # result: []
```

### D-2 测试计划

1. **单元测试:** 8 个 case 见 Step 7
2. **手动测试:** padding=0.3，运行静音检测，波形上字幕块与静音块之间有 ~0.3s 间隙
3. **手动测试:** padding=0 时行为与 margin-only 一致
4. **手动测试:** 验证字幕段的时间范围和文本未被修改 (字幕不可分割)
5. **回归测试:** 已有项目文件 (含 `trim_subtitles_on_silence_overlap` 设置) 正常加载

---

## D-1 与 D-2 的交互 (v2)

```
原始静音: [1.0, 4.0]
字幕: [2.0, 3.0]
margin=0.2, padding=0.3

Step 1 (D-1 margin): [1.2, 3.8]
Step 2 (D-2 padding):
  字幕扩展区: [1.7, 3.3]
  裁剪 [1.2, 3.8] by [1.7, 3.3] -> [1.2, 1.7] 和 [3.3, 3.8]

最终静音: [1.2, 1.7] 和 [3.3, 3.8]
```

margin 缩边后的静音如果完全落入字幕扩展区，则被完全丢弃。这是预期行为。

---

## 实施顺序总结

| 顺序 | ID | 严重度 | 改动文件 | 理由 |
|------|-----|--------|---------|------|
| 1 | **D-3** | LOW | 1 (WorkspacePage.vue) | 最小改动，独立 |
| 2 | **D-1** | MEDIUM | 4 | 独立功能，为 D-2 建立流水线上下文 |
| 3 | **D-2** | MEDIUM | 5 | 依赖 D-1 的流水线顺序，废弃旧字幕裁剪逻辑 |

### 依赖关系

```
D-3 (独立)
D-1 (独立)
D-2 (依赖 add_silence_results 签名由 D-1 扩展，废弃旧 _resolve_subtitle_overlap 调用)
```

### Commit 策略

| Commit | 范围 | 消息 |
|--------|------|------|
| 1 | D-3 | `fix(ui): 调整静音检测 min duration 标尺为 0.05-2.0s 并添加性能提示` |
| 2 | D-1 | `feat(silence): 静音检测后按 margin 值缩边，警告替代禁用` |
| 3 | D-2 | `feat(silence): 静音区间主动避让字幕扩展区，废弃旧字幕裁剪逻辑` |

### 回滚方案

- D-3: 独立回滚，无副作用
- D-1: 独立回滚，`silence_margin` 默认 0，无行为变化
- D-2: 回滚后需恢复 `add_silence_results` 中的 `_resolve_subtitle_overlap` 调用。由于方法本身保留 (deprecated)，恢复调用即可

---

## 新增/修改配置项汇总

| 键 | 类型 | 默认值 | 范围 | 所属 | 状态 |
|----|------|--------|------|------|------|
| `silence_margin` | float | 0.0 | 0.0 - 0.5 | D-1 | 新增 |
| `silence_subtitle_padding` | float | 0.0 | 0.0 - 1.0 | D-2 | 新增 |
| `silence_min_duration` | float | 0.5 | 0.05 - 2.0 | D-3 | 范围修改 |
| `trim_subtitles_on_silence_overlap` | bool | True | - | D-2 | 废弃 (保留兼容) |

---

## 附: v1 -> v2 变更记录

| 问题 | v1 设计 | v2 修正 |
|------|---------|---------|
| D-2 裁剪对象错误 | 修改 `_resolve_subtitle_overlap` 裁剪字幕 | 新增 `_trim_silences_around_subtitles` 裁剪静音 |
| D-2 流水线顺序错误 | 在创建 EditDecision 之后裁剪 | 在创建 EditDecision 之前裁剪 |
| D-1 前端禁用按钮 | `margin*2 >= min_duration` 禁用运行按钮 | 改为 amber 警告提示，不阻断操作 |
| D-3 无性能提示 | 无 | min_duration < 0.2 时显示 amber 提示 |
| `_resolve_subtitle_overlap` 命运 | 被 D-2 修改 | 被 D-2 废弃，方法保留但不调用 |

作为架构师，我已对你提交的《Milo-Cut 实施计划 -- 审计报告 0.2.0-2 (v2)》进行了复核。

## 审计结论：🟢 审核通过 (APPROVED)

**整体评价：**
这份 v2 版本的实施计划非常出色。你不仅精准地理解了上一轮审计中指出的所有严重缺陷，而且给出了极其优雅和严谨的重构方案。所有的架构冲突、逻辑反转和数学谬误均已得到彻底解决。当前的流水线设计逻辑清晰，鲁棒性强。

我可以放心地给予这份方案**“准予实施”**的绿灯。

以下是对各核心模块修正的简要复核意见：

---

### 1. D-2 字幕保护 Padding —— 满分重构 (EXCELLENT)
* **流水线位置修正**：将 D-2 提前到 `Segment` 和 `EditDecision` 创建之前是绝对正确的决定。这保证了底层数据结构（剪辑决策）的准确性。
* **核心算法设计**：`_trim_silences_around_subtitles` 的算法设计非常精妙。通过先计算**字幕扩展区 (Extended Regions)** 并进行合并（处理相邻字幕的重叠），再用静音区间与其求差集。这种“基于集合运算”的思路彻底解决了之前边界判断混乱的问题，并且完美覆盖了“完全包含”、“部分重叠”、“相邻合并”等所有复杂场景。
* **向后兼容**：废弃旧配置项但保留读取入口，废弃旧方法但保留代码实现，这是非常成熟的防御性编程和向后兼容策略。

### 2. D-1 Margin 缩边 —— 极佳的 UX 权衡 (GREAT)
* **约束降级**：从“强阻断 (disabled)”降级为“软警告 (amber warning)”是完全正确的决定。这既尽到了对用户的告知义务（你的短静音可能会消失），又保护了高级用户的使用自由（我就是要过滤掉所有短静音，只对长静音进行强力缩边）。逻辑严密，用户体验更佳。

### 3. D-3 Min Duration 调整 —— 务实的风险控制 (GOOD)
* **性能预警**：在追求细粒度控制 (0.05s) 的同时，引入前端 `v-if="silenceMinDuration < 0.2"` 的性能告警，以最低的成本规避了潜在的客诉问题（如界面卡死或 FFmpeg OOM），是一个非常务实的工程折衷。

---

### 给开发阶段的微小 Tips（无需修改计划文档）：

1. **浮点数精度陷阱**：在 D-2 的 `_trim_silences_around_subtitles` 算法中，由于涉及到大量的浮点数加减（如 `ext_end <= p_start`），在 Python 中可能会遇到诸如 `4.700000000000001 <= 4.7` 判定为 `False` 的极端精度问题。如果在单元测试中发现边缘相交时切出了 `0.0000001s` 的极小碎片，可以在比较时引入一个极小的 epsilon（例如 `round(val, 3)` 或加减 `1e-5`）来确保边界比较的稳定性。
2. **Margin 丢弃阈值**：在 D-1 缩边后 `if new_end > new_start:`，你也可以考虑 `if new_end - new_start > 0.01:`，避免生成时长仅为 `0.001s` 的无意义静音切片，但这取决于业务对“极短静音”的容忍度。

**结论**：方案已完全成熟，请按此 v2 计划推进代码实施与提交。祝编码顺利！

还有一个检测兼容问题，我希望如果执行检测时某个字幕块已经标注为已删除，则字幕保护裁剪忽略这一字幕块

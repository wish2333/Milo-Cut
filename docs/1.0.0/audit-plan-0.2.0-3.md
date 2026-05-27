# Milo-Cut 实施计划 -- 审计报告 0.2.0-3 (v2)

**基于:** 审计报告 0.2.0-3 + 架构师深度审计意见
**日期:** 2026-05-16
**范围:** B-1, E-1, T-1, T-2
**实施顺序:** B-1 -> E-1 -> T-1 -> T-2

---

## 需求概述

四项针对导出和前端的增强:

1. **B-1 [BUG]** Waveform 滑块溢出 -- 滑块滑到最右端时触发窗口横向滚动条，遮挡 Waveform 且无法消除
2. **E-1 [FEATURE]** FFmpeg filter_complex 导出优化 -- 确认并完善当前 filter_complex 单通道导出架构
3. **T-1 [FEATURE]** OTIO 时间线导出 -- 支持 OpenTimelineIO (.otio) 格式，达芬奇/PR 原生导入
4. **T-2 [FEATURE]** OTIO 淡入淡出 -- 可选为每个音频块添加 fade in/out 效果

---

## B-1 [BUG] Waveform 滑块溢出导致窗口横向滚动条

**严重度:** HIGH | **风险:** LOW | **预计改动:** 3 文件

### 问题分析

WaveformEditor 的 ScrollbarStrip 使用百分比定位 (`left` + `width`)。当 `thumbLeft + thumbWidth` 接近或达到 100% 时，由于以下原因可能溢出:

1. `ScrollbarStrip` 的 thumb 使用 `position: absolute` + `left: X%` + `width: Y%`，当 `X + Y = 100` 时，thumb 的右边缘恰好在容器右边界。但由于 `rounded-sm` 的圆角或子像素渲染，实际宽度可能略微超出
2. `WaveformEditor` 根元素 (`<div class="flex flex-col">`) 没有 `overflow: hidden`
3. `WorkspacePage` 中 WaveformEditor 放置在主布局的底部，其父容器 `overflow-hidden` 仅作用于上方的 flex 区域，不包含 WaveformEditor 本身

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/components/waveform/WaveformEditor.vue` | 根元素添加 `overflow-hidden` |
| `frontend/src/components/waveform/ScrollbarStrip.vue` | thumb 添加 `max-width` 约束 + 浮点容差 |
| `frontend/src/App.vue` | 根容器添加 `overflow-x-hidden` |

### Step 1: WaveformEditor 根元素添加 overflow-hidden

**当前:**
```html
<div class="flex flex-col">
```

**改为:**
```html
<div class="flex flex-col overflow-hidden">
```

### Step 2: ScrollbarStrip thumb 添加溢出约束

在 thumb 的 style 绑定中添加 `max-width` 约束，并引入浮点数容差:

**当前:**
```html
:style="{
  left: metrics.thumbLeft.value + '%',
  width: metrics.thumbWidth.value + '%',
}"
```

**改为:**
```html
:style="{
  left: metrics.thumbLeft.value + '%',
  width: metrics.thumbWidth.value + '%',
  maxWidth: Math.min(100, 100 - metrics.thumbLeft.value + 0.1) + '%',
}"
```

> **架构师修正:** +0.1% 容差防止 JS 浮点数精度误差 (如 `99.999999%`) 导致的微溢出。

### Step 3: App.vue 根容器添加 overflow-x-hidden

**当前:**
```html
<div class="min-h-screen" ...>
```

**改为:**
```html
<div class="min-h-screen overflow-x-hidden" ...>
```

### B-1 测试计划

1. 加载一个长视频项目 (duration > 60s)
2. 滚动 Waveform 滑块到最右端，验证无横向滚动条出现
3. 缩放至最小视图 (MIN_VIEW_DURATION=2s)，拖动滑块到两端，验证无溢出
4. 缩放至最大视图 (MAX_VIEW_DURATION)，验证滑块不溢出
5. 在 PyWebView 窗口中验证无横向滚动条

---

## E-1 [FEATURE] FFmpeg filter_complex 导出架构确认与加固

**严重度:** LOW | **风险:** LOW | **预计改动:** 0 文件 (确认现有实现)

### 现状审计

经过代码审查，`export_service.py` **已经**采用了 filter_complex 单通道架构:

- `export_video()` 使用 `_build_video_trim_filter()` 构建 filter，通过 `-filter_complex_script` 写入临时文件后让 FFmpeg 读取
- `export_audio()` 使用 `_build_audio_trim_filter()` 同样采用 `-filter_complex_script` 临时文件方式
- 已弃用旧的 `_extract_segment()` + `_concat_segments()` 多通道方案

### 架构师加固确认

> **关键发现:** 当前代码**已经使用** `-filter_complex_script <txt文件>` 方式 (见 `export_service.py` 第 87-91 行)，而非直接拼接命令行。这意味着 Windows 8191 字符限制**已被规避**。无需额外改动。

```python
# export_service.py 中已有的安全实现:
filter_path = str(temp_dir / "video_filter.txt")
with open(filter_path, "w", encoding="utf-8") as f:
    f.write(filter_complex)
cmd = [
    ffmpeg, "-hide_banner", "-y",
    "-i", media_path,
    "-filter_complex_script", filter_path,  # 从文件读取，不拼在命令行
    ...
]
```

### 结论

filter_complex 导出已实现，且已采用 `-filter_script` 文件方式规避命令行长度限制。无需额外改动。

---

## T-1 [FEATURE] OTIO 时间线导出

**严重度:** HIGH | **风险:** MEDIUM | **预计改动:** 4 文件

### 目标

新增 OpenTimelineIO (.otio) 格式导出，兼容 DaVinci Resolve 18+ 和 Premiere Pro 2025+ 的原生导入。

### 设计原理

**文件结构:** `.otio` 文件与源视频保存在同一目录，`target_url` 使用文件名。

```
源视频所在目录/
├─ 原始视频.mp4
└─ 原始视频_edited.otio
```

**关键约束:**
- `source_range` 的 `value` 必须为严格整型 (`int`)，达芬奇对浮点数帧零容忍
- 音视频轨道使用深拷贝 (`copy.deepcopy`)，防止共享引用导致意外同步修改

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/export_timeline.py` | 新增 `export_otio()` 函数 |
| `main.py` | 新增 OTIO 导出桥接方法 |
| `frontend/src/pages/ExportPage.vue` | 添加 OTIO 导出按钮 |
| `frontend/src/composables/useExport.ts` | 添加 `exportOtio` 方法 |

### Step 1: 帧数计算函数加固 (core/export_timeline.py)

现有 `_sec_to_frames` 函数返回 `int(seconds * fps)`。由于 Python 的 `int()` 对正数是截断而非四舍五入，需改为 `int(round(...))` 确保精度:

**当前:**
```python
def _sec_to_frames(seconds: float, fps: float) -> int:
    """Convert seconds to frame count."""
    return int(seconds * fps)
```

**改为:**
```python
def _sec_to_frames(seconds: float, fps: float) -> int:
    """Convert seconds to frame count (strict integer for NLE compatibility)."""
    return int(round(seconds * fps))
```

> **架构师修正:** 确保所有 `value` 输出为严格整型，达芬奇导入时不会报错。

### Step 2: OTIO 导出函数 (core/export_timeline.py)

```python
import copy

def export_otio(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
    *,
    fade_duration: float = 0.0,
) -> dict:
    """Export OpenTimelineIO (.otio) compatible with DaVinci Resolve / Premiere Pro."""
    import json
    try:
        fps = media_info.get("fps", 25.0)
        media_path = media_info.get("path", "")
        source_duration = media_info.get("duration", 0)

        keep_ranges = _build_keep_ranges(segments, edits, source_duration, fps)

        # OTIO 与源视频同目录，target_url 使用文件名即可
        media_filename = Path(media_path).name

        # Build clips from keep ranges
        clips = []
        for idx, (start, end) in enumerate(keep_ranges):
            clip_dur = end - start
            if clip_dur <= 0:
                continue
            src_start_frames = _sec_to_frames(start, fps)
            src_dur_frames = _sec_to_frames(clip_dur, fps)
            available_dur_frames = _sec_to_frames(source_duration, fps)

            clips.append({
                "OTIO_SCHEMA": "clip.1",
                "name": f"Clip {idx + 1}",
                "source_range": {
                    "OTIO_SCHEMA": "time_range.1",
                    "start_time": {"OTIO_SCHEMA": "rational_time.1", "rate": fps, "value": src_start_frames},
                    "duration": {"OTIO_SCHEMA": "rational_time.1", "rate": fps, "value": src_dur_frames},
                },
                "media_reference": {
                    "OTIO_SCHEMA": "external_reference.1",
                    "target_url": media_filename,
                    "available_range": {
                        "OTIO_SCHEMA": "time_range.1",
                        "start_time": {"OTIO_SCHEMA": "rational_time.1", "rate": fps, "value": 0},
                        "duration": {"OTIO_SCHEMA": "rational_time.1", "rate": fps, "value": available_dur_frames},
                    },
                },
            })

        # --- T-2: Fade transitions ---
        track_children = clips
        if fade_duration > 0 and len(clips) > 1:
            track_children = _build_clips_with_transitions(clips, fps, fade_duration, keep_ranges, source_duration)

        # 深拷贝: 音视频轨道独立，防止共享引用导致意外同步修改
        timeline = {
            "OTIO_SCHEMA": "timeline.1",
            "name": Path(media_path).stem + "_edited",
            "global_start_time": {
                "OTIO_SCHEMA": "rational_time.1",
                "rate": fps,
                "value": 0,
            },
            "tracks": [
                {
                    "OTIO_SCHEMA": "track.1",
                    "name": "Video 1",
                    "kind": "Video",
                    "children": track_children,
                },
                {
                    "OTIO_SCHEMA": "track.1",
                    "name": "Audio 1",
                    "kind": "Audio",
                    "children": copy.deepcopy(track_children),
                },
            ],
        }

        Path(output_path).write_text(
            json.dumps(timeline, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Exported OTIO to {}", output_path)
        return {"success": True, "data": output_path}

    except Exception as e:
        logger.exception("Failed to export OTIO")
        return {"success": False, "error": str(e)}
```

> **架构师修正:** Audio Track 使用 `copy.deepcopy(track_children)` 防止共享引用。

### Step 3: 桥接暴露 (main.py)

```python
elif format == "otio":
    from core.export_timeline import export_otio
    result = export_otio(segments, edits, media_info, output_path)
```

### Step 4: 前端导出页面 (ExportPage.vue)

```html
<button
  class="inline-flex items-center gap-1.5 rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 transition-colors"
  @click="handleExport('otio')"
>
  Export .otio (DaVinci/PR)
</button>
```

### T-1 测试计划

1. 导出 .otio 文件，验证 JSON 结构符合 OTIO schema
2. 验证所有 `value` 字段为严格整型 (无浮点数)
3. 验证音视频轨道 `children` 为独立对象 (修改一个不影响另一个)
4. 用 DaVinci Resolve 18+ 导入 .otio，验证时间线正确还原
5. 用 Premiere Pro 2025+ 导入 .otio，验证时间线正确还原
6. 移动整个文件夹后重新打开 .otio，验证素材链接不丢失
7. 验证 keep_ranges 为空时的错误处理

---

## T-2 [FEATURE] OTIO 淡入淡出效果

**严重度:** MEDIUM | **风险:** LOW | **预计改动:** 3 文件

### 目标

在 OTIO 导出时，可选为每个 Clip 之间添加交叉淡入淡出 (Crossfade) 效果。

### 设计原理

**Handles 概念 (架构师修正):**

在 NLE 中添加交叉溶解需要源素材的额外余量 (Handles):
- Clip A 在 10s 处切断，Clip B 在 10s 处开始
- 0.2s 交叉溶解需要 A 延续到 10.1s，B 从 9.9s 开始
- 如果 A 已到源素材绝对结尾或 B 从绝对开头开始，则**无余量可用**

**处理策略:** 检查每个 clip 的 source_range 边界，无足够 handles 时跳过该转场。

**时长定义修正 (架构师修正):**

OTIO 规范中总转场时长 = `in_offset + out_offset`。UI 输入 0.2s 应为总时长 0.2s，即 `in_offset = out_offset = 0.1s`。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/export_timeline.py` | 新增 `_build_clips_with_transitions()` + 修改 `export_otio()` |
| `core/config.py` | 新增 `export_fade_duration` 配置项 |
| `frontend/src/pages/ExportPage.vue` | 添加 fade duration 滑块 |

### Step 1: 转场构建函数 (core/export_timeline.py)

```python
def _build_clips_with_transitions(
    clips: list[dict],
    fps: float,
    fade_duration: float,
    keep_ranges: list[tuple[float, float]],
    source_duration: float,
) -> list[dict]:
    """Insert Transition objects between clips, respecting source handles.

    Handles: if a clip starts at the source's first frame or ends at the
    source's last frame, there is no extra media for crossfade. In that
    case, skip the transition (NLE will auto-fade or show black).
    """
    half_fade_frames = _sec_to_frames(fade_duration / 2, fps)
    if half_fade_frames <= 0:
        return clips

    interleaved: list[dict] = []
    for i, clip in enumerate(clips):
        interleaved.append(clip)
        if i >= len(clips) - 1:
            break

        # Check handles: does clip A have room after its end?
        # Does clip B have room before its start?
        a_start, a_end = keep_ranges[i]
        b_start, b_end = keep_ranges[i + 1]

        a_has_handle = a_end < source_duration - (fade_duration / 2)
        b_has_handle = b_start > (fade_duration / 2)

        if not (a_has_handle and b_has_handle):
            # No handles available -- skip transition
            continue

        interleaved.append({
            "OTIO_SCHEMA": "transition.1",
            "name": f"Crossfade {i + 1}",
            "transition_type": "SMPTE_Dissolve",
            "in_offset": {
                "OTIO_SCHEMA": "rational_time.1",
                "rate": fps,
                "value": half_fade_frames,
            },
            "out_offset": {
                "OTIO_SCHEMA": "rational_time.1",
                "rate": fps,
                "value": half_fade_frames,
            },
        })

    return interleaved
```

> **架构师修正:**
> - `in_offset` 和 `out_offset` 各取 `fade_duration / 2`，总转场时长 = 用户设定值
> - 边界检查: clip 到源素材头/尾时跳过转场

### Step 2: 配置项 (core/config.py)

```python
"export_fade_duration": 0.0,  # 0 = no fade, >0 = crossfade total seconds
```

### Step 3: 前端 UI (ExportPage.vue)

```html
<label class="block mb-2">
  <span class="text-xs text-gray-500">
    Crossfade (s): {{ fadeDuration.toFixed(2) }}
  </span>
  <input type="range" v-model.number="fadeDuration"
         min="0" max="1.0" step="0.05" class="w-full mt-1" />
  <p v-if="fadeDuration > 0" class="text-xs text-gray-400 mt-0.5">
    Adds crossfade transitions between clips. Clips at source boundaries will be skipped.
  </p>
</label>
```

### T-2 测试计划

1. `fade_duration=0` 时，OTIO 输出中无 Transition 对象
2. `fade_duration=0.2` 时，`in_offset` 和 `out_offset` 各为 0.1s (总时长 0.2s)
3. 仅一个 clip 时，`fade_duration > 0` 不生成 Transition
4. clip 到达源素材绝对开头/结尾时，跳过该处转场
5. 所有 clip 都有足够 handles 时，所有相邻 clip 之间均有 Transition
6. DaVinci Resolve 导入含 Transition 的 .otio，验证交叉淡入淡出效果
7. Premiere Pro 导入含 Transition 的 .otio，验证兼容性

---

## 实施顺序总结

| 顺序 | ID | 严重度 | 改动文件 | 理由 |
|------|-----|--------|---------|------|
| 1 | **B-1** | HIGH | 3 (WaveformEditor.vue, ScrollbarStrip.vue, App.vue) | Bug fix，影响基础 UX |
| 2 | **E-1** | INFO | 0 | 确认现有实现 (已用 -filter_complex_script) |
| 3 | **T-1** | HIGH | 4 (export_timeline.py, main.py, ExportPage.vue, useExport.ts) | 核心新功能 |
| 4 | **T-2** | MEDIUM | 3 (export_timeline.py, config.py, ExportPage.vue) | 依赖 T-1 |

### 依赖关系

```
B-1 (独立)
E-1 (独立，仅确认)
T-1 (独立)
T-2 (依赖 T-1 的 export_otio 函数)
```

### Commit 策略

| Commit | 范围 | 消息 |
|--------|------|------|
| 1 | B-1 | `fix(waveform): 修复滑块溢出导致窗口横向滚动条出现` |
| 2 | T-1 | `feat(export): 新增 OTIO 时间线导出，兼容达芬奇和 Premiere Pro` |
| 3 | T-2 | `feat(export): OTIO 导出支持可选交叉淡入淡出效果` |

### 回滚方案

- B-1: 独立回滚，移除 overflow-hidden 类即可
- E-1: 无代码改动，无需回滚
- T-1: 独立回滚，移除 `export_otio` 函数和前端按钮
- T-2: 回滚后 fade_duration 默认 0，OTIO 导出退化为无 Transition 模式

---

## 新增/修改配置项汇总

| 键 | 类型 | 默认值 | 范围 | 所属 | 状态 |
|----|------|--------|------|------|------|
| `export_fade_duration` | float | 0.0 | 0.0 - 1.0 | T-2 | 新增 |

---

## 附: 架构师审计修正清单

| 编号 | 问题 | 修正 |
|------|------|------|
| B-1-R1 | 浮点数精度溢出 | `maxWidth` 计算加 0.1% 容差 |
| E-1-R1 | FFmpeg 命令行超长 | 已确认使用 `-filter_complex_script` 文件方式，无需改动 |
| T-1-R1 | 音视频轨道共享引用 | Audio Track 使用 `copy.deepcopy(track_children)` |
| T-1-R2 | 帧数浮点精度 | `_sec_to_frames` 改用 `int(round(...))` |
| T-2-R1 | 缺少 Handles 检查 | 新增 `_build_clips_with_transitions()` 含边界检查 |
| T-2-R2 | 转场时长定义错误 | `in_offset` 和 `out_offset` 各取 `fade_duration / 2` |

---

## 附: OTIO 格式参考

### OTIO vs 现有导出格式

| 格式 | 达芬奇 | PR | 多轨道 | 元数据 | 路径策略 | 扩展性 |
|------|--------|-----|--------|--------|---------|--------|
| **OTIO** | 原生 18+ | 原生 2025+ | 完美 | 完整 | 同目录文件名 | 强 (JSON 可扩展) |
| EDL (CMX3600) | 支持 | 支持 | 仅视频 | 有限 | 绝对路径 | 弱 |
| FCP XML (xmeml) | 支持 | 支持 | 一般 | 部分丢失 | 绝对路径 | 弱 |

### OTIO Schema 速查

| Schema | 用途 | 关键字段 |
|--------|------|---------|
| `timeline.1` | 顶层容器 | `name`, `global_start_time`, `tracks[]` |
| `track.1` | 轨道 | `name`, `kind` (Video/Audio), `children[]` |
| `clip.1` | 片段 | `name`, `media_reference`, `source_range` |
| `external_reference.1` | 素材引用 | `target_url` (文件名，同目录), `available_range` |
| `time_range.1` | 时间范围 | `start_time`, `duration` |
| `rational_time.1` | 时间值 | `rate` (帧率), `value` (整型帧数) |
| `transition.1` | 过渡效果 | `transition_type`, `in_offset`, `out_offset` |

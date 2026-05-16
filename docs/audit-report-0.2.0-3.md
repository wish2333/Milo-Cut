# Milo-Cut 实施计划 -- 审计报告 0.2.0-3

**基于:** 用户需求 2026-05-16 + 代码库现状审计
**日期:** 2026-05-16
**范围:** B-1, T-1, T-2, E-1
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

**严重度:** HIGH | **风险:** LOW | **预计改动:** 2 文件

### 问题分析

WaveformEditor 的 ScrollbarStrip 使用百分比定位 (`left` + `width`)。当 `thumbLeft + thumbWidth` 接近或达到 100% 时，由于以下原因可能溢出:

1. `ScrollbarStrip` 的 thumb 使用 `position: absolute` + `left: X%` + `width: Y%`，当 `X + Y = 100` 时，thumb 的右边缘恰好在容器右边界。但由于 `rounded-sm` 的圆角或子像素渲染，实际宽度可能略微超出
2. `WaveformEditor` 根元素 (`<div class="flex flex-col">`) 没有 `overflow: hidden`
3. `WorkspacePage` 中 WaveformEditor 放置在主布局的底部，其父容器 `overflow-hidden` 仅作用于上方的 flex 区域，不包含 WaveformEditor 本身

当溢出发生时，浏览器在 `<html>` 或 `<body>` 上生成横向滚动条。PyWebView 窗口的 `min-h-screen` 类可能未设置 `overflow-x: hidden`，导致横向滚动条出现且无法通过正常交互消除。

### 涉及文件

| 文件 | 改动 |
|------|------|
| `frontend/src/components/waveform/WaveformEditor.vue` | 根元素添加 `overflow-hidden` |
| `frontend/src/components/waveform/ScrollbarStrip.vue` | thumb 添加 `max-width` 约束 |

### Step 1: WaveformEditor 根元素添加 overflow-hidden

**当前:**
```html
<div class="flex flex-col">
```

**改为:**
```html
<div class="flex flex-col overflow-hidden">
```

### Step 2: ScrollbarStrip thumb 添加 right: 0 约束

在 thumb 的 style 绑定中添加 `max-width` 和 `right` 约束，确保 thumb 绝对不会溢出容器:

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
  maxWidth: (100 - metrics.thumbLeft.value) + '%',
}"
```

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

## E-1 [FEATURE] FFmpeg filter_complex 导出架构确认

**严重度:** INFO | **风险:** LOW | **预计改动:** 0 文件 (确认现有实现)

### 现状审计

经过代码审查，`export_service.py` **已经**采用了 filter_complex 单通道架构:

- `export_video()` 使用 `_build_video_trim_filter()` 构建 `filter_complex_script`，通过 `split`/`asplit` + `trim`/`atrim` + `concat` 在单次 FFmpeg 调用中完成所有片段的裁剪和拼接
- `export_audio()` 使用 `_build_audio_trim_filter()` 同样采用 `asplit` + `atrim` + `concat` 单通道架构
- 已弃用旧的 `_extract_segment()` + `_concat_segments()` 多通道方案 (代码保留但未被调用)

### 结论

filter_complex 导出已实现，无需额外改动。此条目仅做审计确认。

---

## T-1 [FEATURE] OTIO 时间线导出

**严重度:** HIGH | **风险:** MEDIUM | **预计改动:** 4 文件

### 目标

新增 OpenTimelineIO (.otio) 格式导出，兼容 DaVinci Resolve 18+ 和 Premiere Pro 2025+ 的原生导入。OTIO 是 ASWF 开源的时间线交换标准，本质是 JSON，只存剪辑结构、时间码、轨道、元数据、素材路径。

### 设计原理

OTIO 核心结构:
- `Timeline` -- 顶层容器，包含 `global_start_time` 和 `tracks[]`
- `Track` -- 轨道 (Video/Audio)，包含 `children[]` (Clips)
- `Clip` -- 片段，包含 `media_reference` (素材路径) 和 `source_range` (源时间范围)
- `TimeRange` -- 由 `start_time` (RationalTime) 和 `duration` (RationalTime) 组成
- `RationalTime` -- 由 `rate` (帧率) 和 `value` (帧数) 组成

**关键约束:**
- `.otio` 文件与源视频保存在同一目录，`target_url` 使用文件名 (同目录相对路径)，方便后续整体移动文件夹
- `source_range` 的 value 为帧数 (整数)，rate 为帧率
- 每个 keep-range 对应一个 Clip，Clip 的 source_range 映射到原始素材的时间范围

**文件结构:**
```
源视频所在目录/
├─ 原始视频.mp4
└─ 原始视频_edited.otio    # OTIO 与源视频同目录
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/export_timeline.py` | 新增 `export_otio()` 函数 |
| `main.py` | 新增 `_handle_export_otio` 暴露方法 + 导出页面注册 |
| `frontend/src/pages/ExportPage.vue` | 添加 OTIO 导出按钮 |
| `frontend/src/composables/useExport.ts` | 添加 `exportOtio` 方法 |

### Step 1: OTIO 导出函数 (core/export_timeline.py)

在现有 `export_edl` 和 `export_xmeml_premiere` 之后新增:

```python
def export_otio(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export OpenTimelineIO (.otio) compatible with DaVinci Resolve / Premiere Pro."""
    import json
    try:
        fps = media_info.get("fps", 25.0)
        media_path = media_info.get("path", "")
        source_duration = media_info.get("duration", 0)
        width = media_info.get("width", 1920)
        height = media_info.get("height", 1080)

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
                    "children": clips,
                },
                {
                    "OTIO_SCHEMA": "track.1",
                    "name": "Audio 1",
                    "kind": "Audio",
                    "children": clips,
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

### Step 2: 桥接暴露 (main.py)

在 `_handle_export_timeline` 或类似方法中添加 OTIO 分支:

```python
elif format == "otio":
    from core.export_timeline import export_otio
    result = export_otio(segments, edits, media_info, output_path)
```

### Step 3: 前端导出页面 (ExportPage.vue)

在现有 EDL/FCPXML 导出按钮旁添加 OTIO 按钮:

```html
<button
  class="inline-flex items-center gap-1.5 rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-600 transition-colors"
  @click="handleExport('otio')"
>
  Export .otio (DaVinci/PR)
</button>
```

### Step 4: useExport.ts composable

在 `exportTimeline` 方法中添加 format 参数透传。

### T-1 测试计划

1. 导出 .otio 文件，验证 JSON 结构符合 OTIO schema
2. 用 DaVinci Resolve 18+ 导入 .otio，验证时间线正确还原
3. 用 Premiere Pro 2025+ 导入 .otio，验证时间线正确还原
4. 验证 `target_url` 为源视频文件名 (同目录)
5. 移动整个文件夹后在达芬奇/PR 中重新打开 .otio，验证素材链接不丢失
6. 验证 keep_ranges 为空时的错误处理

---

## T-2 [FEATURE] OTIO 淡入淡出效果

**严重度:** MEDIUM | **风险:** LOW | **预计改动:** 3 文件

### 目标

在 OTIO 导出时，可选为每个 Clip 之间添加淡入淡出效果。OTIO 使用 `LinearTimeEffect` (schema: `linear_time_warp.1`) 来表示时间效果，但更简洁的做法是使用 `effects` 字段附加 `TimeEffect`。

**OTIO 淡入淡出实现方式:**
- 每个 Clip 可以有 `effects[]` 字段
- 使用 `Transition` 对象在相邻 Clips 之间插入交叉淡入淡出
- `Transition` 包含 `in_offset` 和 `out_offset` (RationalTime) 定义交叉时长

### 设计原理

```
Clip A: [0s --- 10s]
Clip B: [10s --- 20s]
Transition: in_offset=0.2s, out_offset=0.2s

实际效果:
  Clip A 淡出: 9.8s - 10.0s
  Clip B 淡入: 10.0s - 10.2s
  交叉区间: 9.8s - 10.2s
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `core/export_timeline.py` | `export_otio()` 添加 fade 参数和 Transition 生成 |
| `core/config.py` | 新增 `export_fade_duration` 配置项 |
| `frontend/src/pages/ExportPage.vue` | 添加 fade duration 滑块 |

### Step 1: 扩展 export_otio 签名

```python
def export_otio(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
    *,
    fade_duration: float = 0.0,
) -> dict:
```

### Step 2: 生成 Transitions

在 clips 列表构建完成后，如果 `fade_duration > 0`，在相邻 clips 之间插入 Transition:

```python
if fade_duration > 0 and len(clips) > 1:
    fade_frames = _sec_to_frames(fade_duration, fps)
    # Build interleaved: clip, transition, clip, transition, clip
    interleaved = []
    for i, clip in enumerate(clips):
        interleaved.append(clip)
        if i < len(clips) - 1:
            interleaved.append({
                "OTIO_SCHEMA": "transition.1",
                "name": f"Crossfade {i + 1}",
                "transition_type": "SMPTE_Dissolve",
                "in_offset": {
                    "OTIO_SCHEMA": "rational_time.1",
                    "rate": fps,
                    "value": fade_frames,
                },
                "out_offset": {
                    "OTIO_SCHEMA": "rational_time.1",
                    "rate": fps,
                    "value": fade_frames,
                },
            })
    clips = interleaved
```

### Step 3: 配置项 (core/config.py)

```python
"export_fade_duration": 0.0,  # 0 = no fade, >0 = crossfade seconds
```

### Step 4: 前端 UI (ExportPage.vue)

在导出设置区域添加 fade duration 控件:

```html
<label class="block mb-2">
  <span class="text-xs text-gray-500">
    Crossfade (s): {{ fadeDuration.toFixed(2) }}
  </span>
  <input type="range" v-model.number="fadeDuration"
         min="0" max="1.0" step="0.05" class="w-full mt-1" />
  <p v-if="fadeDuration > 0" class="text-xs text-gray-400 mt-0.5">
    Adds crossfade transitions between clips in OTIO export.
  </p>
</label>
```

### T-2 测试计划

1. `fade_duration=0` 时，OTIO 输出中无 Transition 对象
2. `fade_duration=0.2` 时，OTIO 输出中相邻 clips 之间有 Transition，`in_offset` 和 `out_offset` 正确
3. 仅一个 clip 时，`fade_duration > 0` 不生成 Transition
4. DaVinci Resolve 导入含 Transition 的 .otio，验证交叉淡入淡出效果正确显示
5. Premiere Pro 导入含 Transition 的 .otio，验证兼容性

---

## 实施顺序总结

| 顺序 | ID | 严重度 | 改动文件 | 理由 |
|------|-----|--------|---------|------|
| 1 | **B-1** | HIGH | 2 (WaveformEditor.vue, ScrollbarStrip.vue, App.vue) | Bug fix，影响基础 UX，改动最小 |
| 2 | **E-1** | INFO | 0 | 确认现有实现，无需改动 |
| 3 | **T-1** | HIGH | 4 (export_timeline.py, main.py, ExportPage.vue, useExport.ts) | 核心新功能，独立于 T-2 |
| 4 | **T-2** | MEDIUM | 3 (export_timeline.py, config.py, ExportPage.vue) | 依赖 T-1 的 OTIO 导出基础 |

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

## 附: OTIO 格式参考

### OTIO vs 现有导出格式

| 格式 | 达芬奇 | PR | 多轨道 | 元数据 | 路径策略 | 扩展性 |
|------|--------|-----|--------|--------|---------|--------|
| **OTIO** | 原生 18+ | 原生 2025+ | 完美 | 完整 | 同目录文件名 | 强 (JSON 可扩展) |
| EDL (CMX3600) | 支持 | 支持 | 仅视频 | 有限 | 绝对路径 | 弱 |
| FCP XML (xmeml) | 支持 | 支持 | 一般 | 部分丢失 | 绝对路径 | 弱 |

### OTIO 文件结构

```
源视频所在目录/
├─ 原始视频.mp4
└─ 原始视频_edited.otio    # OTIO 与源视频同目录
```

- `.otio` 文件默认保存到源视频所在目录
- `target_url` 使用文件名 (如 `原始视频.mp4`)，因为 .otio 和源视频在同一目录
- 整个文件夹可直接移动/复制，素材链接自动保持有效

### OTIO Schema 速查

| Schema | 用途 | 关键字段 |
|--------|------|---------|
| `timeline.1` | 顶层容器 | `name`, `global_start_time`, `tracks[]` |
| `track.1` | 轨道 | `name`, `kind` (Video/Audio), `children[]` |
| `clip.1` | 片段 | `name`, `media_reference`, `source_range` |
| `external_reference.1` | 素材引用 | `target_url` (文件名，同目录), `available_range` |
| `time_range.1` | 时间范围 | `start_time`, `duration` |
| `rational_time.1` | 时间值 | `rate` (帧率), `value` (帧数) |
| `transition.1` | 过渡效果 | `transition_type`, `in_offset`, `out_offset` |

作为架构师，我对这份《Milo-Cut 实施计划 -- 审计报告 0.2.0-3》进行了深度审计。

整体来看，这份实施计划**结构清晰、逻辑严密、风险控制得当**。实现思路上充分考虑了前端 UI 边界情况（B-1）、复用了现有架构（E-1），并在时间线导出（T-1, T-2）上选择了极其现代且兼容性极佳的 OTIO 格式，是非常优秀的方案。

## 审计意见

但从底层工程实现、音视频剪辑专业逻辑以及极端边界情况的角度来看，我发现了一些**潜在的隐患和需要优化的架构细节**。以下是我的审计意见：

---

### 1. B-1 [BUG] Waveform 滑块溢出
**审计意见：方案可行，建议增加防抖防御**
*   **优点**：通过 CSS `max-width` 配合 Vue 动态绑定的方案非常轻量且精准，根节点增加 `overflow-hidden` 也是标准的防御性编程。
*   **改进建议**：
    *   **浮点数精度问题**：JS 在计算 `thumbLeft` + `thumbWidth` 时可能会产生浮点数精度误差（如 `99.999999%`）。建议在 Vue 模板中绑定的 `max-width` 计算加上一定的容差，或者确保 metrics 内部已经做了 `.toFixed(4)` 处理。
    *   **DOM 重绘性能**：频繁拖动滑块会高频触发 `style` 的重排。建议确认 `metrics.thumbLeft.value` 的更新是否已经接入了 `requestAnimationFrame` 或适当的防抖/节流。

### 2. E-1 [FEATURE] FFmpeg filter_complex 架构确认
**审计意见：确认通过，但需警惕“超长命令”陷阱**
*   **隐患提示（架构级风险）**：由于采用 `filter_complex` 单通道架构（将所有的 `split`, `trim`, `concat` 写在同一条命令中），当用户剪辑的片段非常多（比如超过 100-200 个 cuts）时，生成的 FFmpeg 命令行字符串会**极其庞大**。
*   **改进建议**：
    *   Windows 对命令行长度有 `8191` 字符的硬性限制，macOS/Linux 也有限制（通常较大，但也有上限）。
    *   **防御措施**：必须在 `export_service.py` 中增加**命令长度检测**。如果检测到 cuts 数量过多导致命令可能超长，应使用 `-filter_complex_script <txt文件>` 的方式（将 filter 内容写入临时 txt 文件，让 FFmpeg 读取），而不是直接拼在终端命令中。

### 3. T-1 [FEATURE] OTIO 时间线导出
**审计意见：设计优秀，但需注意引用方式和帧计算**
*   **对象引用问题（Bug 预警）**：
    在代码 Step 1 中，`Video 1` 和 `Audio 1` 的 `children` 都被赋值为 `clips`。在 Python 中，这意味着音视频轨道**引用了同一个字典列表的内存地址**。虽然导出为 JSON 字符串时不会有问题（`json.dumps` 会将其展开），但如果未来要单独对音频轨道做处理（比如 T-2 的音频淡入淡出，或者 J-cut/L-cut），会导致音视频轨道数据被意外同步修改。**建议在赋值给 Audio Track 时使用 `copy.deepcopy(clips)`**。
*   **JSON 构造 vs 官方库**：
    手动拼接 OTIO JSON 字典是可行的（避免了引入新依赖），但 OTIO 的解析器（特别是达芬奇）对 Schema 非常严格。手动构建时需绝对确保 `value` 必须是**整数或浮点数（依 NLE 容忍度）**。建议 `_sec_to_frames(clip_dur, fps)` 内部**必须进行严格的 `round()` 或 `int()` 处理**，决不能输出浮点数帧，否则达芬奇导入时会直接报错。
*   **相对路径（高度赞同）**：使用 `target_url: media_filename` (相对路径) 极大地提升了工程文件的可移植性，这是一个非常棒的架构决定。

### 4. T-2 [FEATURE] OTIO 淡入淡出效果
**审计意见：需修正音视频专业逻辑（Handles 概念）**
*   **转场覆盖与源素材余量（Handles）隐患**：
    在非线性剪辑（NLE）中，如果你要在片段 A 和片段 B 之间添加交叉溶解（Crossfade），片段 A 的真实结束点和片段 B 的真实开始点都需要**额外的素材（Handles）**。
    *   例如：A 在 10s 处切断，B 在 10s 处开始，如果要进行 0.2s 的转场（in=0.1s, out=0.1s），那么 A 的实际播放需要延续到 10.1s，B 的实际播放需要从 9.9s 开始。
    *   如果用户在 Milo-Cut 中把某个片段一直留到了视频的**绝对结尾**，或者从视频的**绝对开头**开始，那么该处**没有多余的素材**用来做 Crossfade。此时达芬奇或 PR 在导入该 OTIO 时，要么报错，要么强行缩短时间线，要么出现黑屏。
    *   **处理建议**：在插入 Transition 前，需进行边界检查。如果 `clip` 是源素材的第一帧，或者最后一帧，应该跳过该转场的生成，或者自动将其转换为单边 Fade in / Fade out。
*   **淡入淡出时长定义（UI 与底层的统一）**：
    在代码中，`in_offset` 和 `out_offset` 都被设为了 `fade_frames`。在 OTIO 规范中，总转场时长 = `in_offset + out_offset`。这意味着如果前端 UI 传入的是 `Crossfade: 0.2s`，那么实际在 OTIO 中生成的总转场时长是 `0.4s`。
    *   **修正建议**：应将 `fade_frames` 除以 2，即 `in_offset = fade_frames / 2`，`out_offset = fade_frames / 2`，以符合用户的直觉（设多少秒就是多少秒的转场）。

---

### 综合架构建议与放行结论

**实施顺序 (B-1 -> E-1 -> T-1 -> T-2) 非常合理。**

**建议在开发时补充以下 Action Items（无需改变主体计划，只需在编码时注意）：**
1.  **E-1 增强**：评估是否改用 `-filter_complex_script` 以彻底杜绝 FFmpeg 命令行超长崩溃问题。
2.  **T-1 增强**：Audio Track 绑定 `clips` 时使用深拷贝（Deep Copy）；确保所有 `value`（帧数）输出为严格的整型（Integer）。
3.  **T-2 增强**：转场的 `in_offset` 和 `out_offset` 各取 `fade_frames` 的一半，并增加极简的越界防护（比如检测素材头尾不加转场）。

**结论：审计通过（Approved with Minor Revisions）。**
该计划具备极高的可行性，请开发团队在采纳上述细节修正后，按照规划开始实施。

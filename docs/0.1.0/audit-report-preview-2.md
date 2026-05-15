# Milo-Cut v2 Comprehensive Audit Report

> **Generated:** 2026-05-15
> **Scope:** Timeline module, Detection module, Project management, Core feature gaps
> **Auditors:** Code review + Backend analysis

---

## Executive Summary

Milo-Cut 在 WaveformEditor 重构后，时间线可视化层已就位，但存在 **7 个高优先级缺陷** 和 **4 个功能缺失**，
导致核心工作流（导入字幕 -> 检测静音 -> 审查建议 -> 导出）无法走通。
最关键的问题是：建议拒绝后 UI 仍显示删除样式、无法删除误添加的区块、静音与字幕重叠逻辑有误、波形从未渲染。

---

## A. Timeline Module (时间线模块)

### A1. 无法删除误添加的区块

**Severity:** HIGH
**Status:** Missing feature (frontend + backend)

用户点击波形空白区域时会创建 0.5s 的新区块 (`SegmentBlocksLayer.vue:62-65`)，但没有任何删除手段：

- **前端**: 无右键菜单、无删除按钮、无键盘快捷键。`SegmentBlocksLayer.vue` 的 `handleBlockMouseDown` 仅处理边缘拖拽和 body 点击。
- **后端**: `project_service.py` 和 `main.py` 中均无 `delete_segment` / `remove_segment` 方法。`add_segment` (line 312) 只做追加，无对应删除。
- **Timeline.vue**: emits 中有 `toggle-status` / `confirm-segment` / `reject-segment`，但无 `delete-segment`。

**Impact:** 误操作无法撤销，区块永久存在。

**Recommendation:**
1. 后端新增 `delete_segment(segment_id)` RPC
2. 前端在区块上增加 Delete 键监听 + 右键菜单 "Delete"
3. 在 `handleEmptyClick` 前检查是否与已有区块重叠，避免误创建

---

### A2. 新增区块与字幕重叠 — 建议双时间轴方案

**Severity:** HIGH
**Status:** Design issue

当前问题:
- `add_segment` (后端 `project_service.py:312-343`) 无任何重叠检查，可创建与已有字幕完全重叠的区块
- `handleEmptyClick` (前端 `SegmentBlocksLayer.vue:62-65`) 直接传 `time` 到 `time+0.5`，不验证冲突
- 字幕区块和静音检测区块混在同一条时间轴上，操作互相干扰

**Proposed Solution — 双时间轴:**

```
┌─────────────────────────────────────────────────────┐
│  Subtitle Timeline (字幕时间轴)                       │
│  [====seg-1====]  [====seg-2====]  [====seg-3====]  │
│  操作: 新增字幕 / 编辑文本 / 拖拽边界                  │
├─────────────────────────────────────────────────────┤
│  Edit Decision Timeline (编辑决策时间轴)               │
│  [~~silence-1~~]        [~~silence-2~~]             │
│  操作: 确认删除 / 拒绝删除 / 新增删除区域               │
└─────────────────────────────────────────────────────┘
```

好处:
- 字幕编辑和删除决策互不干扰
- 新增字幕不会误触删除区域
- 静音检测结果可以独立审查
- 两层各自有独立的添加/删除操作

---

### A3. 音频波形未显示

**Severity:** MEDIUM
**Status:** Bug (backend handler missing + frontend math error)

**Root Cause 1 — 后端未注册波形生成任务:**
- `TaskType.WAVEFORM_GENERATION` 定义在 `core/models.py:38`
- 但 `main.py` 的 `_register_task_handlers` (line 38-57) 注册了 silence_detection、export_video、export_subtitle、filler_detection、error_detection、full_analysis —— **唯独没有 waveform_generation**
- 因此 `project.media.waveform_path` 永远为 `None`，前端 `WaveformCanvas.vue` 永远走 fallback 分支画一条直线

**Root Cause 2 — 前端波形渲染数学错误:**
`WaveformCanvas.vue:80`:
```typescript
const bucketsPerSecond = totalBuckets / (vs + vd)  // BUG: should be totalBuckets / totalDuration
```
`vs` 是 `viewStart`，会随用户滚动变化。这意味着 `bucketsPerSecond` 在不同滚动位置取不同值，波形会扭曲。
正确公式: `totalBuckets / duration` (需要传入媒体总时长)

**Impact:** 波形功能完全不可用。

**Recommendation:**
1. 后端: 实现 `waveform_generation` 任务处理器，用 ffmpeg 提取 peaks 数据写入 JSON
2. 前端: 将 `duration` 传入 `WaveformCanvas`，修正 `bucketsPerSecond` 计算
3. 加载失败时在 UI 上显示提示而非静默画直线

> **架构师补充 — 波形格式约定:**
> - 总 bucket 数量: `Math.ceil(duration * 100)`，即每秒 100 个 bucket
> - 输出路径: `media_hash + ".waveform.json"` 写到项目目录旁
> - 前端 `WaveformCanvas` 新增 `duration` prop，来源: `useProject` 已有 `mediaDuration`，直接透传
> - 修正: `const bucketsPerSecond = peakData.length / props.duration`

---

### A4. 静音检测覆盖字幕 — 整条标记删除

**Severity:** HIGH
**Status:** Logic bug (frontend)

**Root Cause:** `segmentHelpers.ts:20-31` 的 `getEffectiveStatus` 使用简单的二元重叠判断:

```typescript
export function isOverlapping(edit: EditDecision, seg: Segment): boolean {
  return edit.start < seg.end && edit.end > seg.start  // 任何重叠，哪怕是 0.001s
}
```

只要静音 EditDecision 与字幕 Segment 有哪怕 1ms 的时间重叠，整条字幕就被标记为 `"masked"` (红色删除线)。

**Additional issue:** 优先级排序 (`sort by priority`) 只取最高优先级的 edit 决定状态，不考虑重叠比例。
一条字幕可能 99% 是有效内容，但因为尾部 1% 与静音重叠就被整条标红。

**Impact:** 大量有效字幕被误标为删除，用户无法区分"完全在静音区"和"仅边缘重叠"。

**Recommendation:**
1. 为 `isOverlapping` 增加 `minOverlapSeconds` 参数，使用**绝对时长阈值**而非比例阈值
2. 或改为"仅标记重叠区间"而非"标记整条字幕"
3. 考虑双时间轴方案（A2），让静音 edit 和字幕完全解耦

```typescript
export function isOverlapping(
  edit: EditDecision,
  seg: Segment,
  minOverlapSeconds = 0.0,
): boolean {
  const overlapStart = Math.max(edit.start, seg.start)
  const overlapEnd = Math.min(edit.end, seg.end)
  return overlapEnd - overlapStart > minOverlapSeconds
}
// 调用处: isOverlapping(edit, seg, 0.3) 即可缓解绝大多数误标
```

> **架构师补充:** 比例阈值有陷阱——字幕 0.3s、静音 0.2s、边缘重叠 0.15s 占字幕 50%，
> 但这条字幕不该被删。绝对阈值更稳健。短期只需在调用处加 `minOverlapSeconds=0.3`，
> 代价极低，不需要等双时间轴方案。

---

## B. Detection Module (检测模块)

### B1. Analysis 建议无法拒绝 — 拒绝后仍显示删除线

**Severity:** HIGH
**Status:** Bug (frontend)

**Root Cause:** `getEffectiveStatus` (segmentHelpers.ts:20-31) 完全忽略 `EditDecision.status` 字段:

```typescript
const top = [...related].sort((a, b) => b.priority - a.priority)[0]
if (top.action === "delete") return "masked"  // BUG: 不检查 status
return "kept"
```

即使后端正确将 status 设为 `"rejected"`，前端仍返回 `"masked"` 因为只看 `action` 不看 `status`。

**受影响的 UI 组件:**
- `TranscriptRow.vue:107-123` — `statusClass` 优先使用 `effectiveStatus`，导致 rejected 的 edit 仍显示红底+删除线+半透明
- `SilenceRow.vue:60-65` — `effectiveStatus === 'masked'` 与 `editStatus === 'rejected'` 同时为 true，产生冲突样式
- `SegmentBlocksLayer.vue:54-59` — 波形区块颜色同理
- 测试 `segmentHelpers.test.ts` 中无任何 rejected 状态的测试用例

**Impact:** 用户点击"忽略"或"保留"无效，建议系统形同虚设。

**Recommendation:**
```typescript
// 修复 getEffectiveStatus — 在排序前过滤掉 rejected:
const active = related.filter(e => e.status !== "rejected")
if (active.length === 0) return "normal"
const top = [...active].sort((a, b) => b.priority - a.priority)[0]
if (top.action === "delete") return "masked"
return "kept"
```

> **架构师补充:** 仅检查最高优先级 edit 的 status 不够——`related` 里可能有多个 edit，
> 最高优先级被 reject 后，次高的 pending delete 仍应生效。正确做法是**先过滤掉所有 rejected，再取最高优先级**。

### B2. 重复运行静音检测覆盖用户已拒绝的建议

**Severity:** MEDIUM
**Status:** Bug (backend)

`project_service.py:182-188` 的去重检查只看 `CONFIRMED` 和 `PENDING`，不检查 `REJECTED`:

```python
already_covered = any(
    e.action == "delete"
    and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)  # 缺少 REJECTED
    ...
)
```

如果用户拒绝了某段静音建议，再次运行静音检测会创建新的 PENDING edit 覆盖用户的拒绝。

**Recommendation:** 去重条件加入 `EditStatus.REJECTED`。

---

## C. Project Management (项目管理)

### C1. 首页无法打开已有项目

**Severity:** MEDIUM → **建议提升至 HIGH** (开发体验阻断)
**Status:** Missing feature (frontend)

**现状:**
- `WelcomePage.vue:16-41` 只有"上传媒体文件"流程，始终调用 `create_project`
- 后端 API `get_recent_projects` 已定义 (`api.ts:48`)，`RecentProject` 类型已定义 (`edit.ts:9-14`)，`useProject.ts:41-53` 已实现 `openProject()` —— **但均未被任何页面组件使用**
- `App.vue:68-75` 的拖放处理也始终调用 `create_project`

**Impact:** 上传同一文件会创建重复项目；无法继续编辑之前的项目。每次调试都要重新上传文件，开发摩擦极大。

> **架构师补充:** `useProject.openProject()` 已完整实现，`WelcomePage` 只需:
> 1. `onMounted` 时调用 `get_recent_projects` (API 已定义)
> 2. 渲染一个列表
> 3. 点击调用 `openProject(path)`
>
> 工作量约半天，应提前到 Phase 1。

**Recommendation:**
1. `WelcomePage` 增加"最近项目"列表，调用 `get_recent_projects`
2. 点击项目调用 `open_project` (useProject 已实现)
3. `create_project` 前检查是否已存在同路径项目

### C2. 导入 SRT 不校验已有项目

**Severity:** LOW
**Status:** Bug (backend)

`import_srt` (main.py:240-244) 直接替换字幕，不检查:
- 是否已导入过相同 SRT
- SRT 时间戳是否与媒体时长匹配 (`validate_srt` 存在但未在 import 流程中调用)
- 旧 EditDecision 的 `target_id` 引用会变为孤儿 (新导入生成新 `seg-NNNN` ID)

---

## D. Core Feature Gaps (核心功能缺失)

### D1. 基于字幕的智能裁剪工作流

**Severity:** HIGH (用户核心需求)
**Status:** Not implemented

**用户场景:**
1. 用户上传视频 + SRT 字幕
2. 系统自动保留每条字幕时间范围 + 前后 N 秒（如 0.3s）的安全边距
3. 静音检测可叠加使用，进一步精细裁剪
4. 导出裁剪后的音频 + 与裁剪后音频时间轴匹配的新 SRT

**当前状态:**
- 字幕导入 ✓ (import_srt)
- 静音检测 ✓ (detect_silence)
- 但"基于字幕自动生成保留区间"功能不存在
- 导出只支持"删除 confirmed 的 edit"，不支持"保留字幕区间 + padding"
- 导出 SRT 会丢弃与删除区间重叠 >0.01s 的字幕，不生成匹配新时间轴的 SRT

**Recommendation:**
1. 新增 "Subtitle-based trimming" 模式:
   - 输入: 字幕 segments + padding 参数 (默认 0.3s)
   - 计算: 每条字幕 [start - padding, end + padding] 合并为保留区间
   - 输出: 对应的 EditDecision (action="delete") 覆盖保留区间之外的部分
2. 可与静音检测叠加: 静音区间在保留区间内的部分可以额外标记
3. 导出时:
   - 生成匹配新时间轴的 SRT
   - 可选: 在拼接点添加短静音 (如 0.1-0.2s)

> **架构师补充 — 后端 API 设计:**
> ```python
> def generate_subtitle_keep_ranges(self, padding: float = 0.3) -> dict:
>     """为每条字幕生成带 padding 的保留区间，合并重叠后创建 EditDecision。"""
>     segments = [s for s in self._current.transcript.segments
>                 if s.type == SegmentType.SUBTITLE]
>     raw_ranges = [(max(0, s.start - padding), s.end + padding) for s in segments]
>     merged = _merge_ranges(raw_ranges)  # 复用 export_service 已有逻辑
>     # 取反: merged 区间外的部分 = 建议删除区间
>     delete_ranges = _invert_ranges(merged, total_duration=self._current.media.duration)
>     # 创建 EditDecision(action="delete", status=PENDING, source="subtitle_trim")
>     ...
> ```
> 生成的 EditDecision 与静音检测格式完全一致，现有 confirm/reject 流程、导出逻辑均可复用。
> 导出 SRT 时 `_overlaps_deletions` 的阈值应从 `0.01` 改为与 padding 相关的值，避免边缘 case。

### D2. 淡入淡出 / 拼接过渡

**Severity:** MEDIUM
**Status:** Not implemented

**用户需求:** 删除静音后两段声音直接硬切，听感不自然。希望可选地在每句话之间加入:
- 短淡入淡出 (如 50-100ms)
- 一小段静音间隔 (如 0.1-0.2s)

**当前状态:**
- `export_service.py` 使用 ffmpeg concat demuxer + `-c copy` (流拷贝)，无任何后处理
- 无 `crossfade` / `acrossfade` / `xfade` 相关代码
- 无静音间隔插入逻辑

**Recommendation:**
1. 导出选项增加: `crossfade_ms` (默认 0, 可选 50-200ms) 和 `silence_gap_ms` (默认 0, 可选 50-500ms)
2. 实现方式:
   - 淡入淡出: 每个拼接点前后各截取 crossfade_ms 的音频，用 ffmpeg `acrossfade` 滤镜混合
   - 静音间隔: 在拼接点插入指定时长的静音段
3. 前端: 导出摘要弹窗中增加对应选项

### D3. 音频导出

**Severity:** LOW
**Status:** Not implemented

当前仅支持视频导出 (`export_video`) 和 SRT 导出 (`export_srt`)。
播客/音频用户无法单独导出音频。

**Recommendation:** 新增 `exportAudio()` + 后端 `export_audio` 任务，输出 mp3/wav。

---

## E. Export Pipeline (导出流水线)

### E1. `_extract_segment` 硬编码视频编解码器 — 纯音频输入会崩溃

**Severity:** HIGH
**Status:** Bug (backend)

`export_service.py:234-244` 的 `_extract_segment` 写死了 `-c:v libx264 -c:a aac`：

```python
cmd = [
    ffmpeg, "-hide_banner", "-y",
    "-ss", f"{start:.3f}",
    "-to", f"{end:.3f}",
    "-accurate_seek",
    "-i", input_path,
    "-c:v", "libx264", "-preset", "medium",
    "-c:a", "aac",
    "-avoid_negative_ts", "make_zero",
    output_path,
]
```

问题:
1. **纯音频输入 (mp3/wav/m4a/flac) 会崩溃** — 没有视频流可编码，ffmpeg 报错
2. **`-accurate_seek` + `-ss`/`-to` 位置混用** — `-to` 在输入 seek 模式下相对文件开头，混用导致片段时长计算错误
3. **`-preset medium` 对长视频编码速度偏慢** — 应改为 `fast` 或 `veryfast`

> **架构师补充 — 修正后的实现:**
> ```python
> def _extract_segment(
>     ffmpeg: str, input_path: str, start: float, end: float,
>     output_path: str, has_video: bool,
> ) -> None:
>     duration = end - start
>     base = [
>         ffmpeg, "-hide_banner", "-y",
>         "-ss", f"{start:.3f}",   # 输入端粗定位
>         "-i", input_path,
>         "-t", f"{duration:.3f}", # 输出端精确时长 (替代 -to)
>         "-avoid_negative_ts", "make_zero",
>     ]
>     if has_video:
>         codec_args = ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
>     else:
>         codec_args = ["-c:a", "aac", "-vn"]
>     cmd = base + codec_args + [output_path]
>     ...
> ```
>
> 关键变更:
> - 新增 `has_video` 参数，根据输入类型动态构建命令
> - 用 `-t` (相对时长) 替代 `-to` (绝对时间)，避免 seek 模式混用问题
> - `has_video` 判断: `MediaInfo.width == 0` 或 `format` 在音频格式列表中
> - preset 改为 `fast`，画质损失在此场景下几乎感知不到，速度快 2-4 倍
> - concat 阶段 `-c copy` 无需改动，拼接的是已精确截取的 `.ts` 片段
>
> 此修复是 D3 (音频导出) 的前提条件，建议合并为一个任务。

### E2. 输出容器格式兼容性

**Severity:** LOW
**Status:** Design concern

`_extract_segment` 输出 `.ts` (MPEG-TS)，`_concat_segments` 用 `-c copy` 拼接。
如果源文件是 H.265 或 VP9，最终 concat 出来的文件可能有容器格式问题。

**建议:** Phase 3 做导出选项时，将输出格式参数化:
- 视频: 中间 `.ts`，最终 concat 到 `.mp4` (H.264 + AAC，兼容性最好)
- 音频: 中间 `.ts` 或 `.aac`，最终 concat 到 `.m4a` 或 `.mp3`

---

## Summary Matrix

| # | Issue | Severity | Type | Frontend | Backend |
|---|-------|----------|------|----------|---------|
| A1 | 无法删除区块 | HIGH | Missing | SegmentBlocksLayer, WorkspacePage | project_service, main.py |
| A2 | 字幕/静音区块重叠 | HIGH | Design | SegmentBlocksLayer, Timeline | project_service |
| A3 | 波形未显示 | MEDIUM | Bug | WaveformCanvas (math) | main.py (handler) |
| A4 | 静音重叠整条标删 | HIGH | Bug | segmentHelpers.ts | - |
| B1 | 建议无法拒绝 | HIGH | Bug | segmentHelpers.ts, TranscriptRow, SilenceRow | - |
| B2 | 重复检测覆盖拒绝 | MEDIUM | Bug | - | project_service.py:182 |
| C1 | 无法打开已有项目 | MEDIUM→HIGH | Missing | WelcomePage, App.vue | - |
| C2 | SRT 导入不校验 | LOW | Bug | - | main.py, project_service |
| D1 | 字幕智能裁剪 | HIGH | Missing | useExport | export_service |
| D2 | 淡入淡出过渡 | MEDIUM | Missing | useExport | export_service |
| D3 | 音频导出 | LOW | Missing | useExport | export_service |
| E1 | 纯音频输入崩溃 | HIGH | Bug | - | export_service.py |
| E2 | 输出容器兼容性 | LOW | Design | - | export_service.py |

---

## Recommended Implementation Order

> 已根据架构师 review 调整优先级和分组。

### Phase 1 — 修复阻断性 Bug + 开发体验 (估计 2-3 天)
1. **B1** — 修复 `getEffectiveStatus` (过滤 rejected 后再排序)，加测试用例 (~1h)
2. **A4** — `isOverlapping` 加 `minOverlapSeconds` 参数，临时缓解误标 (~0.5h)
3. **C1** — WelcomePage 加最近项目列表 (useProject.openProject 已实现，~0.5d)
4. **A1** — 区块删除: 前端 Delete 键 + 右键菜单，后端 `delete_segment` RPC
5. **A3** — 波形生成任务处理器 + 前端 duration 修正

### Phase 2 — 项目管理健壮性
6. **B2** — 去重加 REJECTED
7. **C2** — SRT 导入校验 (`validate_srt` 已存在，顺手做掉)

### Phase 3 — 核心功能扩展
8. **E1** — `_extract_segment` 重构 (has_video + seek fix) — **D3 的前提**
9. **D1** — 字幕智能裁剪工作流 (需单独设计 API，见架构师补充)
10. **D3** — 音频导出 (与 E1 合并为一个任务)
11. **D2** — 淡入淡出过渡
12. **A2** — 双时间轴 (等 D1 完成后结合用户反馈决定)
13. **E2** — 输出容器格式参数化

---

## Architect Review Notes (架构师反馈)

> 以下为架构师对本报告的补充和修正意见，已整合到上述各条目中。
> 此处保留原始反馈作为决策记录。

### 1. B1 修复方案需考虑多 edit 场景

报告原方案只检查最高优先级 edit 的 status。实际场景中 `related` 可能包含多个 edit，
最高优先级被 reject 后，次高的 pending delete 仍应生效。正确做法是**先过滤 rejected 再排序**。

### 2. A4 用绝对阈值替代比例阈值

比例阈值 (>50%) 在短字幕场景下有陷阱。绝对时长阈值 (`minOverlapSeconds=0.3`) 更稳健，
实现成本极低，不需要等双时间轴方案。

### 3. A3 波形格式需要明确约定

前端 `WaveformCanvas` 期望 `{ min: number, max: number }[]` 格式。
需要约定: bucket 数量 (`duration * 100`)、输出路径 (`media_hash.waveform.json`)、
前端 `duration` prop 来源 (`useProject.mediaDuration`)。

### 4. C1 应提前到 Phase 1

`useProject.openProject()` 已完整实现，`WelcomePage` 只需半天工作量。
对日常开发调试的摩擦影响极大（每次都要重新上传文件）。

### 5. D1 后端 API 设计

`generate_subtitle_keep_ranges(padding)` 生成的 EditDecision 与静音检测格式一致，
现有 confirm/reject 流程和导出逻辑均可复用。详见 D1 条目中的架构师补充。

### 6. 导出流水线隐患 (新增 E1/E2)

- `_extract_segment` 硬编码视频编解码器，纯音频输入会崩溃
- `-accurate_seek` + `-ss`/`-to` 位置混用导致时长计算错误
- 应用 `-t` (相对时长) 替代 `-to`，新增 `has_video` 参数
- `-preset medium` 改为 `fast`，速度提升 2-4 倍
- E1 是 D3 (音频导出) 的前提条件，建议合并为一个任务

---

## Appendix A: Frontend Source Code

### A-1. `frontend/src/utils/segmentHelpers.ts`

```typescript
import type { EditDecision, Segment } from "@/types/project"

export function isOverlapping(edit: EditDecision, seg: Segment): boolean {
  return edit.start < seg.end && edit.end > seg.start
}

export function getEditForSegment(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision | undefined {
  const byId = edits.find(e => e.target_id === seg.id)
  if (byId) return byId
  return edits.find(e =>
    e.target_type === "range" &&
    Math.abs(e.start - seg.start) < 0.01 &&
    Math.abs(e.end - seg.end) < 0.01,
  )
}

export function getEffectiveStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): "normal" | "masked" | "kept" {
  const related = edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg),
  )
  if (related.length === 0) return "normal"
  const top = [...related].sort((a, b) => b.priority - a.priority)[0]
  if (top.action === "delete") return "masked"  // BUG: 不检查 status
  return "kept"
}

export function getEditStatus(
  edits: ReadonlyArray<EditDecision>,
  seg: Segment,
): EditDecision["status"] | null {
  return getEditForSegment(edits, seg)?.status ?? null
}
```

### A-2. `frontend/src/types/project.ts`

```typescript
export type EditStatus = "pending" | "confirmed" | "rejected"

export type SegmentType = "subtitle" | "silence"

export interface Word {
  word: string
  start: number
  end: number
  confidence: number
}

export interface Segment {
  id: string
  version: number
  type: SegmentType
  start: number
  end: number
  text: string
  words?: Word[]
  speaker: string
  dirty_flags?: Record<string, boolean>
}

export interface EditDecision {
  id: string
  start: number
  end: number
  action: "delete" | "keep"
  source: string
  analysis_id?: string
  status: EditStatus
  priority: number
  target_type: "segment" | "range"
  target_id?: string
}

export interface MediaInfo {
  path: string
  media_hash: string
  duration: number
  format: string
  width: number
  height: number
  fps: number
  audio_channels: number
  sample_rate: number
  bit_rate: number
  proxy_path?: string
  waveform_path?: string
}

export interface ProjectMeta {
  name: string
  created_at: string
  updated_at: string
}

export interface TranscriptData {
  engine: string
  language: string
  segments: Segment[]
}

export interface AnalysisData {
  last_run: string | null
  results: AnalysisResult[]
}

export interface Project {
  schema_version: number
  project: ProjectMeta
  media: MediaInfo | null
  transcript: TranscriptData
  analysis: AnalysisData
  edits: EditDecision[]
}

export interface AnalysisResult {
  id: string
  type: "filler" | "error"
  segment_ids: string[]
  confidence: number
  detail: string
}
```

### A-3. `frontend/src/components/waveform/SegmentBlocksLayer.vue`

```vue
<script setup lang="ts">
import { computed, inject, ref } from "vue"
import type { Segment, EditDecision } from "@/types/project"
import { getEditForSegment, getEffectiveStatus } from "@/utils/segmentHelpers"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  updateTime?: (segmentId: string, field: "start" | "end", value: number) => void
}>()

const emit = defineEmits<{
  "select-range": [start: number, end: number]
  "add-segment": [start: number, end: number]
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const MIN_SEGMENT_DURATION = 0.1
const hoverEdge = ref<"left" | "right" | "body" | null>(null)
const EDGE_HANDLE_HIT_PX = 16

interface Block {
  seg: Segment
  leftPercent: number
  widthPercent: number
  edit: EditDecision | undefined
  effectiveStatus: "normal" | "masked" | "kept"
}

const visibleBlocks = computed<Block[]>(() => {
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return []

  return props.segments
    .filter(seg => seg.end > vs && seg.start < ve)
    .map(seg => {
      const clampStart = Math.max(seg.start, vs)
      const clampEnd = Math.min(seg.end, ve)
      const edit = getEditForSegment(props.edits, seg)
      return {
        seg,
        leftPercent: ((clampStart - vs) / vd) * 100,
        widthPercent: ((clampEnd - clampStart) / vd) * 100,
        edit,
        effectiveStatus: getEffectiveStatus(props.edits, seg),
      }
    })
})

function statusColor(block: Block): string {
  if (block.effectiveStatus === "masked") return "bg-red-200 border-red-400"
  if (block.effectiveStatus === "kept") return "bg-green-200 border-green-400"
  if (block.seg.type === "silence") return "bg-gray-200 border-gray-300"
  return "bg-blue-100 border-blue-300"
}

function handleEmptyClick(e: MouseEvent) {
  const time = metrics.getTimeFromX(e.clientX)
  emit("add-segment", time, time + 0.5)
}

function snapToFrame(time: number): number {
  return Math.round(time * 100) / 100
}

function clampTime(
  raw: number,
  edge: "left" | "right",
  seg: Segment,
): number {
  if (edge === "left") {
    return Math.min(raw, seg.end - MIN_SEGMENT_DURATION)
  }
  return Math.max(raw, seg.start + MIN_SEGMENT_DURATION)
}

function detectEdge(e: MouseEvent): "left" | "right" | "body" {
  const el = e.currentTarget as HTMLElement
  const rect = el.getBoundingClientRect()
  const x = e.clientX - rect.left
  if (x < EDGE_HANDLE_HIT_PX) return "left"
  if (x > rect.width - EDGE_HANDLE_HIT_PX) return "right"
  return "body"
}

function handleBlockMouseMove(e: MouseEvent) {
  hoverEdge.value = detectEdge(e)
}

function handleBlockMouseLeave() {
  hoverEdge.value = null
}

function handleBlockMouseDown(
  block: Block,
  e: MouseEvent,
) {
  const edge = detectEdge(e)
  if (edge === "body") {
    emit("select-range", block.seg.start, block.seg.end)
    return
  }
  if (!props.updateTime) return

  e.stopPropagation()
  const initialValue = edge === "left" ? block.seg.start : block.seg.end
  const offset = initialValue - metrics.getTimeFromX(e.clientX)

  const onMove = (e: MouseEvent) => {
    const raw = metrics.getTimeFromX(e.clientX) + offset
    const clamped = clampTime(raw, edge, block.seg)
    props.updateTime!(block.seg.id, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = (e: MouseEvent) => {
    const raw = metrics.getTimeFromX(e.clientX) + offset
    const snapped = snapToFrame(clampTime(raw, edge, block.seg))
    props.updateTime!(block.seg.id, edge === "left" ? "start" : "end", snapped)
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
    document.body.style.cursor = ""
  }

  document.body.style.cursor = edge === "left" ? "w-resize" : "e-resize"
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}
</script>

<template>
  <div class="absolute inset-x-0 top-6 bottom-0" @mousedown.self="handleEmptyClick">
    <div
      v-for="block in visibleBlocks"
      :key="block.seg.id"
      class="absolute top-1 bottom-1 rounded border select-none group"
      :class="[
        statusColor(block),
        hoverEdge === 'left' || hoverEdge === 'right' ? 'cursor-ew-resize' : 'cursor-grab',
      ]"
      :style="{
        left: block.leftPercent + '%',
        width: block.widthPercent + '%',
      }"
      :title="block.seg.text || `[${block.seg.type}]`"
      @mousemove="handleBlockMouseMove"
      @mouseleave="handleBlockMouseLeave"
      @mousedown="handleBlockMouseDown(block, $event)"
    >
      <div
        class="absolute left-0 top-0 bottom-0 w-2 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-400 rounded-l"
        style="pointer-events: none"
      />
      <div
        class="absolute right-0 top-0 bottom-0 w-2 opacity-0 group-hover:opacity-100 transition-opacity bg-blue-400 rounded-r"
        style="pointer-events: none"
      />
      <div class="flex h-full items-center overflow-hidden px-2">
        <span class="truncate text-[10px] leading-tight text-gray-700">
          {{ block.seg.text || (block.seg.type === 'silence' ? '...' : '') }}
        </span>
      </div>
    </div>
  </div>
</template>
```

### A-4. `frontend/src/components/waveform/WaveformCanvas.vue`

```vue
<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref, watch } from "vue"
import type { Segment } from "@/types/project"
import { TIMELINE_METRICS_KEY } from "./injectionKeys"
import type { TimelineMetrics } from "@/composables/useTimelineMetrics"

interface PeakData {
  min: number
  max: number
}

const props = defineProps<{
  segments: Segment[]
  waveformPath?: string
}>()

const metrics = inject<TimelineMetrics>(TIMELINE_METRICS_KEY)!

const canvasRef = ref<HTMLCanvasElement | null>(null)
const peaks = ref<PeakData[] | null>(null)
const loadError = ref(false)

async function loadWaveform(path: string) {
  try {
    const res = await fetch(path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    if (Array.isArray(data) && data.length > 0 && "min" in data[0]) {
      peaks.value = data
    } else {
      loadError.value = true
    }
  } catch {
    loadError.value = true
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext("2d")
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const w = rect.width
  const h = rect.height
  const mid = h / 2

  ctx.clearRect(0, 0, w, h)

  if (peaks.value && peaks.value.length > 0 && !loadError.value) {
    drawWaveform(ctx, w, h, mid)
  } else {
    drawFallback(ctx, w, mid)
  }

  drawSilenceOverlay(ctx, w, h)
}

function drawWaveform(ctx: CanvasRenderingContext2D, w: number, _h: number, mid: number) {
  const peakData = peaks.value!
  const vs = metrics.viewStart.value
  const ve = metrics.viewEnd.value
  const vd = metrics.viewDuration.value

  const totalBuckets = peakData.length
  const bucketsPerSecond = totalBuckets / (vs + vd)  // BUG: should be totalBuckets / duration

  const startBucket = Math.floor(vs * bucketsPerSecond)
  const endBucket = Math.min(Math.ceil(ve * bucketsPerSecond), totalBuckets)
  const visibleBuckets = endBucket - startBucket

  if (visibleBuckets <= 0) return

  const bucketWidth = w / visibleBuckets

  ctx.beginPath()
  ctx.moveTo(0, mid)

  for (let i = 0; i < visibleBuckets; i++) {
    const bucket = startBucket + i
    if (bucket >= totalBuckets) break
    const x = i * bucketWidth
    const y = mid - (peakData[bucket].max * mid)
    ctx.lineTo(x, y)
  }

  for (let i = visibleBuckets - 1; i >= 0; i--) {
    const bucket = startBucket + i
    if (bucket >= totalBuckets) break
    const x = i * bucketWidth
    const y = mid - (peakData[bucket].min * mid)
    ctx.lineTo(x, y)
  }

  ctx.closePath()
  ctx.fillStyle = "#94a3b8"
  ctx.fill()
  ctx.strokeStyle = "#64748b"
  ctx.lineWidth = 0.5
  ctx.stroke()
}

function drawFallback(ctx: CanvasRenderingContext2D, w: number, mid: number) {
  ctx.beginPath()
  ctx.moveTo(0, mid)
  ctx.lineTo(w, mid)
  ctx.strokeStyle = "#94a3b8"
  ctx.lineWidth = 1
  ctx.stroke()
}

function drawSilenceOverlay(ctx: CanvasRenderingContext2D, w: number, h: number) {
  const vs = metrics.viewStart.value
  const vd = metrics.viewDuration.value
  if (vd <= 0) return

  for (const seg of props.segments) {
    if (seg.type !== "silence") continue
    if (seg.end <= vs || seg.start >= vs + vd) continue

    const clampStart = Math.max(seg.start, vs)
    const clampEnd = Math.min(seg.end, vs + vd)
    const x = ((clampStart - vs) / vd) * w
    const width = ((clampEnd - clampStart) / vd) * w

    ctx.fillStyle = "rgba(148, 163, 184, 0.25)"
    ctx.fillRect(x, 0, width, h)
  }
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  const canvas = canvasRef.value
  if (canvas) {
    resizeObserver = new ResizeObserver(() => draw())
    resizeObserver.observe(canvas)
    draw()
  }
})

onUnmounted(() => {
  resizeObserver?.disconnect()
})

watch(() => props.waveformPath, (path) => {
  if (path) {
    loadWaveform(path)
  }
}, { immediate: true })

watch([metrics.viewStart, metrics.viewDuration, peaks, () => props.segments], () => {
  draw()
})
</script>

<template>
  <div class="absolute inset-0">
    <canvas ref="canvasRef" class="h-full w-full" />
  </div>
</template>
```

### A-5. `frontend/src/composables/useSegmentEdit.ts`

```typescript
import { type ComputedRef, computed, type Ref, ref } from "vue"
import type { EditDecision, Project, Segment } from "@/types/project"
import { call } from "@/bridge"
import {
  getEditForSegment,
  getEditStatus as queryEditStatus,
  getEffectiveStatus as queryEffectiveStatus,
} from "@/utils/segmentHelpers"

const DEBOUNCE_MS = 300

export interface UseSegmentEditReturn {
  selectedSegmentId: Ref<string | null>
  selectedRange: Ref<{ start: number; end: number } | null>
  selectSegment: (id: string | null) => void
  selectRange: (start: number, end: number) => void
  clearSelection: () => void

  updateSegmentTime: (segmentId: string, field: "start" | "end", value: number) => void
  updateSegmentText: (segmentId: string, text: string) => Promise<boolean>
  toggleEditStatus: (segment: Segment, nextStatus?: string) => Promise<void>

  getEffectiveStatus: (seg: Segment) => "normal" | "masked" | "kept"
  getEditStatus: (seg: Segment) => EditDecision["status"] | null

  flushPendingUpdates: () => Promise<void>
  pendingCount: ComputedRef<number>
}

function replaceSegment(project: Project, segId: string, patch: Partial<Segment>): Project {
  return {
    ...project,
    transcript: {
      ...project.transcript,
      segments: project.transcript.segments.map(s =>
        s.id === segId ? { ...s, ...patch } : s,
      ),
    },
  }
}

export function useSegmentEdit(
  project: Ref<Project>,
  onProjectUpdate: (project: Project) => void,
): UseSegmentEditReturn {
  const selectedSegmentId = ref<string | null>(null)
  const selectedRange = ref<{ start: number; end: number } | null>(null)

  const pendingMap = new Map<string, { timer: ReturnType<typeof setTimeout>; callback: () => void }>()
  const pendingCount = computed(() => pendingMap.size)

  function selectSegment(id: string | null) {
    selectedSegmentId.value = id
  }

  function selectRange(start: number, end: number) {
    selectedRange.value = { start, end }
  }

  function clearSelection() {
    selectedSegmentId.value = null
    selectedRange.value = null
  }

  function getEffectiveStatus(seg: Segment): "normal" | "masked" | "kept" {
    return queryEffectiveStatus(project.value.edits, seg)
  }

  function getEditStatus(seg: Segment): EditDecision["status"] | null {
    return queryEditStatus(project.value.edits, seg)
  }

  function updateSegmentTime(segmentId: string, field: "start" | "end", value: number) {
    const prev = project.value
    const seg = prev.transcript.segments.find(s => s.id === segmentId)
    if (!seg) return

    const optimistic = replaceSegment(prev, segmentId, { [field]: value })
    onProjectUpdate(optimistic)

    const key = `${segmentId}:${field}`
    const existing = pendingMap.get(key)
    if (existing) clearTimeout(existing.timer)

    const callback = async () => {
      const res = await call<Project>("update_segment", segmentId, { [field]: value })
      if (res.success && res.data) {
        onProjectUpdate(res.data)
      } else {
        onProjectUpdate(prev)
      }
    }

    const timer = setTimeout(() => {
      pendingMap.delete(key)
      callback()
    }, DEBOUNCE_MS)

    pendingMap.set(key, { timer, callback })
  }

  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    const res = await call<Project>("update_segment_text", segmentId, text)
    if (res.success && res.data) {
      onProjectUpdate(res.data)
      return true
    }
    return false
  }

  async function toggleEditStatus(segment: Segment, nextStatus?: string): Promise<void> {
    const edits = project.value.edits
    const edit = getEditForSegment(edits, segment)

    if (!edit) {
      await call("mark_segments", [segment.id], "delete", "confirmed")
    } else {
      const status = nextStatus ?? (
        edit.status === "confirmed" ? "rejected"
        : edit.status === "rejected" ? "confirmed"
        : "confirmed"
      )
      await call<Project>("update_edit_decision", edit.id, status)
    }

    const projRes = await call<Project>("get_project")
    if (projRes.success && projRes.data) {
      onProjectUpdate(projRes.data)
    }
  }

  async function flushPendingUpdates(): Promise<void> {
    const entries = [...pendingMap.values()]
    pendingMap.clear()
    for (const entry of entries) {
      clearTimeout(entry.timer)
      entry.callback()
    }
  }

  return {
    selectedSegmentId,
    selectedRange,
    selectSegment,
    selectRange,
    clearSelection,
    updateSegmentTime,
    updateSegmentText,
    toggleEditStatus,
    getEffectiveStatus,
    getEditStatus,
    flushPendingUpdates,
    pendingCount,
  }
}
```

### A-6. `frontend/src/composables/useExport.ts`

```typescript
import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useTask } from "./useTask"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"

export function useExport(project: Ref<Project | null>) {
  const { createTask, startTask, activeTask, isRunning } = useTask()

  const isExporting = computed(() => {
    const t = activeTask.value
    return t !== null
      && (t.type === "export_video" || t.type === "export_subtitle")
      && isRunning.value
  })

  const exportProgress = computed(() => {
    const t = activeTask.value
    if (t && (t.type === "export_video" || t.type === "export_subtitle")) {
      return t.progress
    }
    return null
  })

  const confirmedEdits = computed(() =>
    (project.value?.edits ?? []).filter(e => e.status === "confirmed" && e.action === "delete")
  )

  const estimatedSaving = computed(() => {
    return confirmedEdits.value.reduce((sum, e) => sum + (e.end - e.start), 0)
  })

  async function getExportSummary(): Promise<EditSummary | null> {
    const res = await call<EditSummary>("get_edit_summary")
    if (res.success && res.data) {
      return res.data
    }
    return null
  }

  async function exportVideo(outputPath?: string): Promise<boolean> {
    const payload: Record<string, string> = {}
    if (outputPath) {
      payload.output_path = outputPath
    }
    const task = await createTask("export_video", payload)
    if (!task) return false
    return await startTask(task.id)
  }

  async function exportSrt(outputPath?: string): Promise<boolean> {
    const payload: Record<string, string> = {}
    if (outputPath) {
      payload.output_path = outputPath
    }
    const task = await createTask("export_subtitle", payload)
    if (!task) return false
    return await startTask(task.id)
  }

  return {
    isExporting,
    exportProgress,
    confirmedEdits,
    estimatedSaving,
    getExportSummary,
    exportVideo,
    exportSrt,
  }
}
```

### A-7. `frontend/src/composables/useProject.ts`

```typescript
import { ref, computed } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { EVENT_PROJECT_SAVED, EVENT_PROJECT_DIRTY } from "@/utils/events"
import type { Project, Segment, EditDecision, MediaInfo } from "@/types/project"

export function useProject() {
  const { on } = useBridge()

  const project = ref<Project | null>(null)
  const isDirty = ref(false)
  const loading = ref(false)

  const segments = computed<Segment[]>(() => project.value?.transcript?.segments ?? [])
  const edits = computed<EditDecision[]>(() => project.value?.edits ?? [])
  const mediaDuration = computed<number>(() => project.value?.media?.duration ?? 0)
  const mediaInfo = computed<MediaInfo | null>(() => project.value?.media ?? null)

  on(EVENT_PROJECT_SAVED, () => {
    isDirty.value = false
  })

  on(EVENT_PROJECT_DIRTY, () => {
    isDirty.value = true
  })

  async function createProject(name: string, mediaPath: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("create_project", name, mediaPath)
      if (res.success && res.data) {
        project.value = res.data
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function openProject(path: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("open_project", path)
      if (res.success && res.data) {
        project.value = res.data
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function saveProject(): Promise<boolean> {
    const res = await call<void>("save_project")
    return res.success
  }

  async function closeProject(): Promise<boolean> {
    const res = await call<void>("close_project")
    if (res.success) {
      project.value = null
      isDirty.value = false
    }
    return res.success
  }

  return {
    project,
    isDirty,
    loading,
    segments,
    edits,
    mediaDuration,
    mediaInfo,
    createProject,
    openProject,
    saveProject,
    closeProject,
  }
}
```

### A-8. `frontend/src/composables/useAnalysis.ts`

```typescript
import { computed, type Ref } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { useTask } from "./useTask"
import { EVENT_TASK_COMPLETED } from "@/utils/events"
import type { Project } from "@/types/project"
import type { TaskType } from "@/types/task"

const ANALYSIS_TASKS: TaskType[] = [
  "silence_detection",
  "filler_detection",
  "error_detection",
  "full_analysis",
]

export function useAnalysis(project: Ref<Project | null>) {
  const { on } = useBridge()
  const { createTask, startTask, tasks, activeTask, isRunning } = useTask()

  const isDetecting = computed(() => {
    const t = activeTask.value
    return t !== null && ANALYSIS_TASKS.includes(t.type) && isRunning.value
  })

  const detectionProgress = computed(() => {
    const t = activeTask.value
    if (t && ANALYSIS_TASKS.includes(t.type)) {
      return t.progress
    }
    return null
  })

  on(EVENT_TASK_COMPLETED, (data: { task_id: string; result?: { project?: Project } }) => {
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task && ANALYSIS_TASKS.includes(task.type) && data.result?.project) {
      project.value = data.result.project
    }
  })

  async function runSilenceDetection(): Promise<boolean> {
    const task = await createTask("silence_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runFillerDetection(): Promise<boolean> {
    const task = await createTask("filler_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runErrorDetection(): Promise<boolean> {
    const task = await createTask("error_detection")
    if (!task) return false
    return await startTask(task.id)
  }

  async function runFullAnalysis(): Promise<boolean> {
    const task = await createTask("full_analysis")
    if (!task) return false
    return await startTask(task.id)
  }

  async function confirmEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "confirmed")
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function rejectEdit(editId: string): Promise<boolean> {
    const res = await call<Project>("update_edit_decision", editId, "rejected")
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllEdits(): Promise<boolean> {
    const edits = project.value?.edits ?? []
    let ok = true
    for (const edit of edits) {
      if (edit.status === "pending" && edit.action === "delete") {
        const res = await confirmEdit(edit.id)
        if (!res) ok = false
      }
    }
    return ok
  }

  return {
    isDetecting,
    detectionProgress,
    runSilenceDetection,
    runFillerDetection,
    runErrorDetection,
    runFullAnalysis,
    confirmEdit,
    rejectEdit,
    confirmAllEdits,
  }
}
```

### A-9. `frontend/src/composables/useEdit.ts`

```typescript
import { type Ref } from "vue"
import { call } from "@/bridge"
import type { Project } from "@/types/project"
import type { EditSummary } from "@/types/edit"

export function useEdit(project: Ref<Project | null>) {

  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    const res = await call<Project>("update_segment_text", segmentId, text)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function updateSegmentTime(segmentId: string, field: "start" | "end", value: number): Promise<boolean> {
    const res = await call<Project>("update_segment", segmentId, { [field]: value })
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function mergeSegments(segmentIds: string[]): Promise<boolean> {
    const res = await call<Project>("merge_segments", segmentIds)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function splitSegment(segmentId: string, position: number): Promise<boolean> {
    const res = await call<Project>("split_segment", segmentId, position)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function searchReplace(
    query: string,
    replacement: string,
    scope: string = "all",
  ): Promise<{ count: number; modified_ids: string[] } | null> {
    const res = await call<{ count: number; modified_ids: string[] }>(
      "search_replace", query, replacement, scope,
    )
    if (res.success && res.data) {
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data
    }
    return null
  }

  async function markSegments(segmentIds: string[], action: "delete" | "keep"): Promise<boolean> {
    const res = await call<Project>("mark_segments", segmentIds, action)
    if (res.success && res.data) {
      project.value = res.data
      return true
    }
    return false
  }

  async function confirmAllSuggestions(): Promise<number | null> {
    const res = await call<{ confirmed_count: number }>("confirm_all_suggestions")
    if (res.success && res.data) {
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data.confirmed_count
    }
    return null
  }

  async function rejectAllSuggestions(): Promise<number | null> {
    const res = await call<{ rejected_count: number }>("reject_all_suggestions")
    if (res.success && res.data) {
      const projRes = await call<Project>("get_project")
      if (projRes.success && projRes.data) {
        project.value = projRes.data
      }
      return res.data.rejected_count
    }
    return null
  }

  async function getEditSummary(): Promise<EditSummary | null> {
    const res = await call<EditSummary>("get_edit_summary")
    if (res.success && res.data) {
      return res.data
    }
    return null
  }

  return {
    updateSegmentText,
    updateSegmentTime,
    mergeSegments,
    splitSegment,
    searchReplace,
    markSegments,
    confirmAllSuggestions,
    rejectAllSuggestions,
    getEditSummary,
  }
}
```

### A-10. `frontend/src/pages/WelcomePage.vue`

```vue
<script setup lang="ts">
import { ref } from "vue"
import FileDropInput from "@/components/common/FileDropInput.vue"
import { call } from "@/bridge"
import type { MediaInfo, Project } from "@/types/project"

interface Emits {
  (e: "project-created", project: Project): void
}

const emit = defineEmits<Emits>()

const status = ref("")
const error = ref("")

async function handleFilesSelected(paths: string[]) {
  if (paths.length === 0) return
  const mediaPath = paths[0]
  error.value = ""
  status.value = "正在分析视频..."

  const probeRes = await call<MediaInfo>("probe_media", mediaPath)
  if (!probeRes.success) {
    error.value = probeRes.error ?? "无法读取视频信息"
    status.value = ""
    return
  }

  const name = mediaPath.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
  status.value = "正在创建项目..."

  const createRes = await call<Project>("create_project", name, mediaPath)
  if (!createRes.success || !createRes.data) {
    error.value = createRes.error ?? "创建项目失败"
    status.value = ""
    return
  }

  status.value = ""
  emit("project-created", createRes.data)
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-canvas p-8">
    <div class="w-full max-w-xl">
      <div class="mb-10 text-center">
        <h1 class="text-4xl font-semibold tracking-tight text-ink">Milo-Cut</h1>
        <p class="mt-2 text-base text-ink-muted">AI 驱动的口播视频预处理工具</p>
      </div>

      <FileDropInput @files-selected="handleFilesSelected" />

      <div v-if="status" class="mt-4 text-center text-sm text-primary">
        {{ status }}
      </div>
      <div v-if="error" class="mt-4 text-center text-sm text-status-warning">
        {{ error }}
      </div>

      <div class="mt-8 text-center text-xs text-ink-muted-48">
        Phase 0 - 技术验证
      </div>
    </div>
  </div>
</template>
```

### A-11. `frontend/src/components/workspace/TranscriptRow.vue`

```vue
<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted } from "vue"
import type { Segment, EditStatus } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  editStatus?: EditStatus | null
  effectiveStatus?: "normal" | "masked" | "kept"
  isSelected?: boolean
  globalEditMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
}>()

const isEditingText = ref(false)
const editText = ref("")
const originalText = ref("")

const editingTimeField = ref<"start" | "end" | null>(null)
const editingTimeValue = ref("")
const timeInputRef = ref<HTMLInputElement | null>(null)

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

function cancelTimeEdit() {
  editingTimeField.value = null
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") applyTimeEdit()
  else if (e.key === "Escape") cancelTimeEdit()
}

function startEdit() {
  originalText.value = props.segment.text
  editText.value = props.segment.text
  isEditingText.value = true
}

function saveEdit() {
  if (editText.value !== props.segment.text) {
    emit("update-text", props.segment.id, editText.value)
  }
  isEditingText.value = false
}

function cancelEdit() {
  editText.value = originalText.value
  isEditingText.value = false
}

onMounted(() => {
  if (props.globalEditMode) startEdit()
})
watch(() => props.globalEditMode, (val) => {
  if (val && !isEditingText.value) {
    startEdit()
  } else if (!val && isEditingText.value) {
    saveEdit()
  }
})

function handleTextEditBlur() {
  if (props.globalEditMode) return
  saveEdit()
}

function handleTextEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") saveEdit()
  else if (e.key === "Escape") cancelEdit()
}

function handleRowClick() {
  if (editingTimeField.value) return
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()
  }
  emit("seek", props.segment.start)
}

const statusClass = computed(() => {
  if (props.effectiveStatus === "masked") {
    return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
  }
  if (props.effectiveStatus === "kept") {
    return "border-l-3 border-green-400 bg-green-50"
  }

  switch (props.editStatus) {
    case "pending": return "border-l-3 border-yellow-400 bg-yellow-50"
    case "confirmed": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "rejected": return "border-l-3 border-green-400 bg-green-50"
    default: return ""
  }
})
</script>

<template>
  <div
    class="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
    :class="[statusClass, { 'ring-1 ring-blue-500': isSelected }]"
    @click="handleRowClick"
  >
    <div class="text-xs text-gray-400 w-[130px] shrink-0 pt-0.5 font-mono overflow-hidden whitespace-nowrap">
      <template v-if="editingTimeField === 'start'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('start', $event)">{{ formatTime(segment.start) }}</span>
      </template>
      <span class="mx-0.5">→</span>
      <template v-if="editingTimeField === 'end'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('end', $event)">{{ formatTime(segment.end) }}</span>
      </template>
    </div>

    <div class="flex-1 min-w-0 overflow-hidden">
      <input
        v-if="isEditingText"
        v-model="editText"
        class="w-full min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm outline-none box-border"
        @blur="handleTextEditBlur"
        @keydown="handleTextEditKeydown"
        @mousedown.stop
        @click.stop
      />
      <span v-else class="text-sm block truncate">{{ segment.text }}</span>
    </div>

    <div class="flex items-center gap-1 shrink-0">
      <template v-if="isEditingText">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 cursor-pointer hover:bg-blue-200 transition-colors"
          title="Save changes"
          @click.stop="saveEdit"
        >
          保存
        </span>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 cursor-pointer hover:bg-gray-200 transition-colors"
          title="Cancel editing"
          @click.stop="cancelEdit"
        >
          取消
        </span>
      </template>
      <template v-else>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 cursor-pointer hover:bg-gray-200 transition-colors"
          title="Edit text"
          @click.stop="startEdit"
        >
          编辑
        </span>
      </template>
    </div>

    <div class="flex items-center gap-1 shrink-0">
      <template v-if="editStatus === 'pending'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 cursor-pointer hover:bg-yellow-200 transition-colors"
          title="Click to confirm delete"
          @click.stop="emit('confirm-edit')"
        >
          建议删除
        </span>
        <button
          class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
          title="Keep this segment"
          @click.stop="emit('reject-edit')"
        >
          保留
        </button>
      </template>
      <template v-else-if="editStatus === 'confirmed'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 cursor-pointer hover:bg-red-200 transition-colors"
          title="Click to keep"
          @click.stop="emit('toggle-status')"
        >
          已删除
        </span>
      </template>
      <template v-else-if="editStatus === 'rejected'">
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
          title="Click to delete"
          @click.stop="emit('toggle-status')"
        >
          已保留
        </span>
      </template>
      <template v-else>
        <span
          class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
          title="Click to mark for deletion"
          @click.stop="emit('toggle-status')"
        >
          已保留
        </span>
      </template>
    </div>
  </div>
</template>
```

### A-12. `frontend/src/components/workspace/SilenceRow.vue`

```vue
<script setup lang="ts">
import { computed, ref, nextTick } from "vue"
import type { Segment, EditStatus } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  editStatus?: EditStatus | null
  effectiveStatus?: "normal" | "masked" | "kept"
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
}>()

const editingTimeField = ref<"start" | "end" | null>(null)
const editingTimeValue = ref("")
const timeInputRef = ref<HTMLInputElement | null>(null)

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

function cancelTimeEdit() {
  editingTimeField.value = null
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") applyTimeEdit()
  else if (e.key === "Escape") cancelTimeEdit()
}

function handleRowClick() {
  if (editingTimeField.value) return
  emit("seek", props.segment.start)
}

const duration = computed(() => {
  return (props.segment.end - props.segment.start).toFixed(1)
})
</script>

<template>
  <div
    class="flex items-center gap-2 px-3 h-8 cursor-pointer transition-colors"
    :class="{
      'bg-gray-50': !editStatus && (!effectiveStatus || effectiveStatus === 'normal'),
      'bg-yellow-50 border-l-3 border-yellow-400': editStatus === 'pending',
      'bg-red-50 border-l-3 border-red-400 opacity-60': editStatus === 'confirmed' || effectiveStatus === 'masked',
      'bg-green-50 border-l-3 border-green-400': editStatus === 'rejected' || effectiveStatus === 'kept',
    }"
    @click="handleRowClick"
  >
    <div class="text-xs text-gray-400 w-[130px] shrink-0 font-mono overflow-hidden whitespace-nowrap">
      <template v-if="editingTimeField === 'start'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('start', $event)">{{ formatTime(segment.start) }}</span>
      </template>
      <span class="mx-0.5">→</span>
      <template v-if="editingTimeField === 'end'">
        <input
          ref="timeInputRef"
          v-model="editingTimeValue"
          class="w-[55px] bg-white border border-blue-400 rounded px-0.5 py-0 text-[11px] font-mono outline-none"
          @keydown="handleTimeEditKeydown"
          @blur="applyTimeEdit"
          @click.stop
        />
      </template>
      <template v-else>
        <span class="cursor-pointer hover:text-blue-500 hover:underline" title="Click to edit" @mousedown.stop.prevent="startTimeEdit('end', $event)">{{ formatTime(segment.end) }}</span>
      </template>
    </div>
    <span class="text-xs text-gray-500 flex-1 text-center">
      --- 静音 {{ duration }}s ---
    </span>
    <span
      v-if="editStatus"
      class="text-xs px-1.5 py-0.5 rounded shrink-0 cursor-pointer transition-colors"
      :class="{
        'bg-yellow-100 text-yellow-700 hover:bg-yellow-200': editStatus === 'pending',
        'bg-red-100 text-red-700 hover:bg-red-200': editStatus === 'confirmed',
        'bg-green-100 text-green-700 hover:bg-green-200': editStatus === 'rejected',
      }"
      title="Click to toggle confirmed/rejected"
      @click.stop="emit('toggle-status')"
    >
      {{ editStatus === "pending" ? "建议删除" : editStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>
```

---

## Appendix B: Backend Source Code

### B-1. `core/models.py` (Types & Enums)

```python
"""Pydantic v2 data models for Milo-Cut.

All models are frozen (immutable) by default.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ================================================================
# Enums / Literal types
# ================================================================

class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(StrEnum):
    # MVP
    SILENCE_DETECTION = "silence_detection"
    EXPORT_VIDEO = "export_video"
    EXPORT_SUBTITLE = "export_subtitle"
    # P1
    FILLER_DETECTION = "filler_detection"
    ERROR_DETECTION = "error_detection"
    FULL_ANALYSIS = "full_analysis"
    TRANSCRIPTION = "transcription"
    VAD_ANALYSIS = "vad_analysis"
    WAVEFORM_GENERATION = "waveform_generation"


class EditStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SegmentType(StrEnum):
    SUBTITLE = "subtitle"
    SILENCE = "silence"


# ================================================================
# Core data models
# ================================================================

class Word(BaseModel, frozen=True):
    word: str
    start: float
    end: float
    confidence: float = 1.0


class Segment(BaseModel, frozen=True):
    id: str
    version: int = 1
    type: SegmentType = SegmentType.SUBTITLE
    start: float
    end: float
    text: str = ""
    words: list[Word] = Field(default_factory=list)
    speaker: str = ""
    dirty_flags: dict[str, bool] = Field(default_factory=dict)


class MediaInfo(BaseModel, frozen=True):
    path: str
    media_hash: str = ""
    duration: float = 0.0
    format: str = ""
    width: int = 0
    # ... (additional fields omitted for brevity)
```

### B-2. `main.py` (Task Handler Registration, lines 38-57)

```python
def _register_task_handlers(self) -> None:
    """Register handlers for each task type."""
    self._task_manager.register_handler(
        TaskType.SILENCE_DETECTION, self._handle_silence_detection
    )
    self._task_manager.register_handler(
        TaskType.EXPORT_VIDEO, self._handle_export_video
    )
    self._task_manager.register_handler(
        TaskType.EXPORT_SUBTITLE, self._handle_export_subtitle
    )
    self._task_manager.register_handler(
        TaskType.FILLER_DETECTION, self._handle_filler_detection
    )
    self._task_manager.register_handler(
        TaskType.ERROR_DETECTION, self._handle_error_detection
    )
    self._task_manager.register_handler(
        TaskType.FULL_ANALYSIS, self._handle_full_analysis
    )
    # NOTE: TaskType.WAVEFORM_GENERATION is NOT registered here
```

### B-3. `main.py` (import_srt, lines 240-244)

```python
@expose
def import_srt(self, file_path: str) -> dict:
    result = parse_srt(file_path)
    if not result["success"]:
        return result
    return self._project.update_transcript(result["data"])
    # NOTE: No validation of SRT against media duration
    # NOTE: No check for duplicate imports
    # NOTE: Old EditDecision target_id references become orphaned
```

### B-4. `core/project_service.py` (add_silence_results, lines 152-211)

```python
def add_silence_results(self, silences: list[dict]) -> dict:
    """Convert raw silence intervals to Segments + EditDecisions.

    Skips creating EditDecisions for silence ranges that already have
    a confirmed edit (e.g. from subtitle deletion).
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    existing = self._current.transcript.segments
    existing_edits = list(self._current.edits)

    new_segments: list[Segment] = []
    new_edits: list[EditDecision] = []
    sil_idx = len([s for s in existing if s.type == SegmentType.SILENCE])

    for sil in silences:
        sil_idx += 1
        seg_id = f"sil-{sil_idx:04d}"
        edit_id = f"edit-{sil_idx:04d}"

        new_segments.append(Segment(
            id=seg_id,
            type=SegmentType.SILENCE,
            start=sil["start"],
            end=sil["end"],
            text="",
        ))

        # Skip edit if range already covered by an existing edit
        already_covered = any(
            e.action == "delete"
            and e.status in (EditStatus.CONFIRMED, EditStatus.PENDING)  # BUG: missing REJECTED
            and abs(e.start - sil["start"]) < 0.05
            and abs(e.end - sil["end"]) < 0.05
            for e in existing_edits
        )
        if not already_covered:
            new_edits.append(EditDecision(
                id=edit_id,
                start=sil["start"],
                end=sil["end"],
                action="delete",
                source="silence_detection",
                status=EditStatus.PENDING,
                target_type="range",
            ))

    all_segments = list(existing) + new_segments
    all_edits = existing_edits + new_edits

    from core.models import AnalysisData
    updated = self._current.model_copy(update={
        "transcript": TranscriptData(segments=all_segments),
        "edits": all_edits,
        "analysis": AnalysisData(last_run=datetime.now().isoformat()),
    })
    self._current = updated
    logger.info("Added {} silence segments to project", len(new_segments))
    return {"success": True, "data": updated.model_dump()}
```

### B-5. `core/project_service.py` (update_edit_decision, lines 213-237)

```python
def update_edit_decision(self, edit_id: str, status: str) -> dict:
    """Update the status of an edit decision."""
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    try:
        new_status = EditStatus(status)
    except ValueError:
        return {"success": False, "error": f"Invalid status: {status}"}

    updated_edits = []
    found = False
    for edit in self._current.edits:
        if edit.id == edit_id:
            updated_edits.append(edit.model_copy(update={"status": new_status}))
            found = True
        else:
            updated_edits.append(edit)

    if not found:
        return {"success": False, "error": f"Edit decision not found: {edit_id}"}

    updated = self._current.model_copy(update={"edits": updated_edits})
    self._current = updated
    return {"success": True, "data": updated.model_dump()}
    # NOTE: No state machine validation (e.g. rejected -> confirmed should be allowed,
    #       but pending -> rejected without going through confirmed might be unexpected)
```

### B-6. `core/project_service.py` (add_segment, lines 312-343)

```python
def add_segment(self, start: float, end: float, text: str = "", seg_type: str = "subtitle") -> dict:
    """Add a new segment to the transcript."""
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    segment_type = SegmentType(seg_type)
    existing = self._current.transcript.segments
    # Generate unique ID
    type_prefix = "sub" if segment_type == SegmentType.SUBTITLE else "sil"
    existing_ids = {s.id for s in existing}
    idx = 1
    while f"{type_prefix}-user-{idx:04d}" in existing_ids:
        idx += 1
    seg_id = f"{type_prefix}-user-{idx:04d}"

    new_seg = Segment(
        id=seg_id,
        type=segment_type,
        start=start,
        end=end,
        text=text,
    )

    all_segments = list(existing) + [new_seg]
    all_segments.sort(key=lambda s: s.start)

    updated = self._current.model_copy(update={
        "transcript": TranscriptData(segments=all_segments),
    })
    self._current = updated
    logger.info("Added segment {} ({:.3f}s - {:.3f}s)", seg_id, start, end)
    return {"success": True, "data": updated.model_dump()}
    # NOTE: No overlap check with existing segments
    # NOTE: No validation that start < end
    # NOTE: No minimum duration enforcement
```

### B-7. `core/project_service.py` (mark_segments, lines 487-529)

```python
def mark_segments(self, segment_ids: list[str], action: str, status: str = "pending") -> dict:
    """Create or update EditDecisions for the given segments.

    Args:
        segment_ids: List of segment IDs to mark.
        action: "delete" or "keep".
        status: "pending" (default) or "confirmed" or "rejected".
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    segments = self._current.transcript.segments
    target_segs = [s for s in segments if s.id in segment_ids]
    if not target_segs:
        return {"success": False, "error": "No matching segments found"}

    try:
        edit_status = EditStatus(status)
    except ValueError:
        edit_status = EditStatus.PENDING

    existing_edits = list(self._current.edits)
    new_edit_ids_set: set[str] = set()
    new_edits: list[EditDecision] = []

    for seg in target_segs:
        edit_id = f"edit-user-{seg.id}"
        new_edit_ids_set.add(edit_id)
        new_edits.append(EditDecision(
            id=edit_id,
            start=seg.start,
            end=seg.end,
            action=action,
            source="user",
            status=edit_status,
            priority=200,
            target_type="segment",
            target_id=seg.id,
        ))

    # Merge: keep non-target edits, replace/add new ones
    merged_edits = [e for e in existing_edits if e.id not in new_edit_ids_set] + new_edits
```

### B-8. `core/export_service.py` (Full file)

```python
"""Export service: FFmpeg-based video and SRT export.

Exports cut video by extracting keep-ranges (non-deleted segments) and
concatenating them via FFmpeg. Also exports SRT with adjusted timestamps.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from loguru import logger

from core.ffmpeg_service import _find_ffmpeg
from core.paths import get_temp_dir


def _validate_output_path(output_path: str) -> str:
    """Validate and normalize an output file path."""
    p = Path(output_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Export cut video by keeping non-deleted ranges.

    Steps:
    1. Collect confirmed deletions from edits
    2. Compute keep-ranges (inverse of deletions)
    3. Extract each keep-range as .ts segment via FFmpeg
    4. Concat all segments via FFmpeg concat demuxer
    """
    try:
        output_path = _validate_output_path(output_path)
        ffmpeg = _find_ffmpeg()
        deletions = _get_confirmed_deletions(edits)
        total_duration = _get_media_duration(segments, edits)

        if not deletions:
            logger.info("No confirmed deletions, copying original file")
            import shutil
            shutil.copy2(media_path, output_path)
            if progress_callback:
                progress_callback(100.0, "Done (no cuts)")
            return {"success": True, "data": {"path": output_path}}

        keep_ranges = _compute_keep_ranges(total_duration, deletions)
        if not keep_ranges:
            return {"success": False, "error": "Nothing to export after applying all cuts"}

        temp_dir = get_temp_dir()
        seg_paths: list[str] = []
        total_segments = len(keep_ranges)

        for i, (start, end) in enumerate(keep_ranges):
            if cancel_event and cancel_event.is_set():
                _cleanup_files(seg_paths)
                return {"success": False, "error": "Cancelled"}

            seg_path = str(temp_dir / f"seg_{i:04d}.ts")
            if progress_callback:
                pct = (i / total_segments) * 80.0
                progress_callback(pct, f"Extracting segment {i + 1}/{total_segments}")

            _extract_segment(ffmpeg, media_path, start, end, seg_path)
            seg_paths.append(seg_path)

        concat_list = str(temp_dir / "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for p in seg_paths:
                escaped = p.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        if progress_callback:
            progress_callback(85.0, "Concatenating segments...")
        _concat_segments(ffmpeg, concat_list, output_path)

        _cleanup_files(seg_paths + [concat_list])

        file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
        if progress_callback:
            progress_callback(100.0, "Export complete")

        logger.info("Exported video to {} ({} bytes)", output_path, file_size)
        return {"success": True, "data": {"path": output_path, "size": file_size}}

    except Exception as e:
        logger.exception("export_video failed")
        return {"success": False, "error": str(e)}


def export_srt(
    segments: list[dict],
    edits: list[dict],
    output_path: str,
) -> dict:
    """Export SRT with only kept subtitle segments and adjusted timestamps."""
    try:
        output_path = _validate_output_path(output_path)
        deletions = _get_confirmed_deletions(edits)
        subtitle_segs = [s for s in segments if s.get("type") == "subtitle"]

        kept: list[dict] = []
        for seg in subtitle_segs:
            if not _overlaps_deletions(seg["start"], seg["end"], deletions):
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

        with open(output_path, "w", encoding="utf-8") as f:
            for idx, (start, end, text) in enumerate(adjusted, 1):
                f.write(f"{idx}\n")
                f.write(f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n")
                f.write(f"{text}\n\n")

        logger.info("Exported {} subtitle segments to {}", len(adjusted), output_path)
        return {"success": True, "data": {"path": output_path, "segment_count": len(adjusted)}}

    except Exception as e:
        logger.exception("export_srt failed")
        return {"success": False, "error": str(e)}


# ================================================================
# Helpers
# ================================================================

def _get_confirmed_deletions(edits: list[dict]) -> list[tuple[float, float]]:
    """Extract confirmed deletion ranges from edit decisions."""
    result = []
    for edit in edits:
        if (edit.get("action") == "delete"
                and edit.get("status") == "confirmed"):
            result.append((edit["start"], edit["end"]))
    result.sort(key=lambda x: x[0])
    return result


def _get_media_duration(segments: list[dict], edits: list[dict]) -> float:
    """Compute total media duration from segments and edits."""
    all_times = [s["end"] for s in segments] + [e["end"] for e in edits]
    return max(all_times) if all_times else 0.0


def _compute_keep_ranges(
    total_duration: float,
    deletions: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Subtract deletion ranges from full timeline to get keep ranges."""
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

    return keep


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping ranges."""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlaps_deletions(
    start: float,
    end: float,
    deletions: list[tuple[float, float]],
) -> bool:
    """Check if a range overlaps significantly with any deletion range."""
    for del_start, del_end in deletions:
        overlap_start = max(start, del_start)
        overlap_end = min(end, del_end)
        if overlap_end - overlap_start > 0.01:
            return True
    return False


def _extract_segment(
    ffmpeg: str,
    input_path: str,
    start: float,
    end: float,
    output_path: str,
) -> None:
    """Extract a single segment as MPEG-TS via FFmpeg re-encode."""
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-accurate_seek",
        "-i", input_path,
        "-c:v", "libx264", "-preset", "medium",
        "-c:a", "aac",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment extraction failed: {result.stderr[-500:]}")


def _concat_segments(
    ffmpeg: str,
    concat_list: str,
    output_path: str,
) -> None:
    """Concatenate .ts segments via FFmpeg concat demuxer."""
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        output_path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-500:]}")


def _format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp HH:MM:SS,mmm."""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds % 1) * 1000)) % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _cleanup_files(paths: list[str]) -> None:
    """Remove temporary files."""
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
```

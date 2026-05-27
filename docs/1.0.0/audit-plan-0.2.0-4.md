# Milo-Cut 0.2.1 实施计划

**基于:** audit-report-0.2.0-4.md + 审查意见 + 代码现状
**日期:** 2026-05-16
**状态:** APPROVED

**实施顺序:** A-1 -> A-6 -> A-7 -> A-9-XML -> A-3 -> A-2 -> A-4 -> A-5

---

## Phase 1: P0 阻断修复

### Task 1: A-1 导出页返回编辑页后波形消失

**问题:** ExportPage 切回 WorkspacePage 后，波形空白约 30s，无法回到导入页
**根因:** Python `HTTPServer` 单线程阻塞 + ExportPage 未主动释放 `<video>` 连接

#### Step 1.1: MediaServer 改用 ThreadingHTTPServer

**文件:** `core/media_server.py`

**改动:**
1. Line 13: 将 `from http.server import HTTPServer` 改为 `from http.server import ThreadingHTTPServer`
2. Line 21: `_QuietHTTPServer` 基类从 `HTTPServer` 改为 `ThreadingHTTPServer`
3. 其余代码无需改动（`ThreadingHTTPServer` 是 `HTTPServer` 的直接子类，API 完全兼容）

**验证:** 启动应用 -> 导出页预览播放 -> 切回编辑页 -> 波形应在 1-2s 内恢复（不再是 30s）

#### Step 1.2: ExportPage 释放 video 连接

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:**
1. 在 PreviewPlayer 区域或 ExportPage 中添加 `onUnmounted` 钩子
2. 在钩子中找到 `<video>` 元素，调用 `video.pause()` 并设置 `video.src = ""` + `video.load()` 主动释放 HTTP 连接

**验证:** 同 Step 1.1 验证

#### Step 1.3: WorkspacePage 波形加载重试

**文件:** `frontend/src/pages/WorkspacePage.vue`

**改动:**

1. `resolveWaveformUrl()` (line 161-166) 添加简单重试：失败后最多重试 3 次，间隔 1s
2. 使用 async/await + for 循环实现，不引入额外依赖

**验证:** 断点调试确认重试逻辑生效

---

### Task 2: A-6 Waveform 滑块拖动性能优化

**问题:** ScrollbarStrip 拖动时每帧 mousemove 都触发 Canvas 完整重绘 + computed 重建，造成严重卡顿

#### Step 2.1: ScrollbarStrip 添加 RAF 节流

**文件:** `frontend/src/components/waveform/ScrollbarStrip.vue`

**改动:**
1. 在 `onMove` 函数外层添加 `requestAnimationFrame` 包装
2. 维护 `rafId` 变量，每帧最多执行一次 viewStart 更新
3. 仅在 `rafId === null` 时请求新帧，帧回调中置 `rafId = null`

```typescript
let rafId: number | null = null
function onMove(e: MouseEvent) {
  if (rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    const rect = trackRef.value.getBoundingClientRect()
    const x = e.clientX - rect.left
    const ratio = Math.max(0, Math.min(1, x / rect.width))
    metrics.viewStart.value = ratio * (duration - metrics.viewDuration.value)
    metrics.clampViewStart()
  })
}
```

**验证:** 拖动滑块时帧率应接近 60fps，无卡顿感

#### Step 2.2: WaveformCanvas 添加变化阈值检查

**文件:** `frontend/src/components/waveform/WaveformCanvas.vue`

**改动:**
1. 在 `draw()` 函数开头添加 `viewStart` 变化阈值检查
2. 如果 `viewStart` 变化 < 0.02s（约半个像素），跳过重绘
3. 维护 `lastDrawnViewStart` 变量记录上次绘制的 viewStart

**验证:** 快速拖动时 Canvas 更新平滑，微抖动不触发多余重绘

#### Step 2.3: timeMarks 计算优化

**文件:** `frontend/src/composables/useTimelineMetrics.ts`

**改动:**
1. `timeMarks` computed 中添加步进检查：仅当 `viewStart` 跨越一个刻度间隔后才重建数组
2. 刻度间距 = 当前 `step` 值（已由 `NICE_STEPS` 约束）
3. 维护 `lastStepViewStart` 变量，当 `floor(viewStart / step) === floor(lastStepViewStart / step)` 时返回缓存结果

**验证:** 拖动时 timeMarks 数组重建频率大幅降低

---

## Phase 2: P1 核心功能

### Task 3: A-7 OTIO 全量时间线导出 + 删除区域标记

**需求:** OTIO 导出支持两种模式 -- Clean Export (当前) 和 Full Timeline (包含删除区域 Gap + Marker)

**审查意见 (必须遵守):** 所有 Duration 必须用**绝对帧数相减**计算，禁止用时长舍入，避免 1 帧缝隙

#### Step 3.1: 后端 -- 新增 `_build_full_timeline_items()` 函数

**文件:** `core/export_timeline.py`

**改动:**
1. 新增函数 `_build_full_timeline_items(keep_ranges, deleted_ranges, fps, media_filename, available_dur) -> list`
2. 合并 keep_ranges 和 deleted_ranges，按 start 时间排序
3. 遍历所有区间：
   - keep -> `otio.schema.Clip`（同现有逻辑）
   - deleted -> `otio.schema.Gap` + `otio.schema.Marker(name="Milo-Cut Deleted", color="RED")`
4. **关键算法：绝对帧数相减**
   ```python
   start_frame = _sec_to_frames(start, fps)
   end_frame = _sec_to_frames(end, fps)
   dur_frames = end_frame - start_frame  # 禁止用 round((end-start)*fps)
   ```
5. 返回 items 列表（Clip 和 Gap 交替排列）

**验证:** 单元测试验证 items 列表长度和类型正确

#### Step 3.2: 后端 -- `export_otio()` 添加 mode 参数

**文件:** `core/export_timeline.py`

**改动:**
1. `export_otio()` 添加参数 `mode: str = "clean"`（值为 `"clean"` 或 `"full_timeline"`）
2. 当 `mode == "full_timeline"` 时：
   - 调用 `_build_full_timeline_items()` 替代现有 Clip 构建逻辑
   - **强制 `fade_duration = 0`**（Full Timeline 模式禁用过渡）
   - 构建 deleted_ranges：从 edits 中提取所有 confirmed delete 的区间
3. 当 `mode == "clean"` 时保持现有行为不变

**验证:** 两种模式均能正确输出 .otio 文件

#### Step 3.3: 后端 -- bridge 方法传递 mode 参数

**文件:** `main.py`

**改动:**
1. `export_otio` bridge 方法 (line 612-622) 添加 `mode: str = "clean"` 参数
2. 传递给 `_export_otio(... mode=mode)`

**验证:** API 调用参数正确传递

#### Step 3.4: 前端 -- 添加导出模式选择 UI

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:**
1. 新增 ref `otioExportMode: Ref<"clean" | "full_timeline">`，默认 `"clean"`
2. 在 OTIO fade_duration 滑块上方添加 radio 组：
   - `(o) Clean Export` -- 仅保留片段，可加过渡
   - `( ) Full Timeline` -- 包含删除标记，无法添加过渡
3. 联动逻辑：
   - `otioExportMode === "full_timeline"` 时：`otioFadeDuration` 置 0 并 disabled
   - 选择 Full Timeline 时显示 amber 提示："全量时间线模式下不适用过渡"
4. `handleExportOtio()` 传递 `mode` 参数到后端

**验证:** UI 交互正确，两种模式均可导出

---

### Task 4: A-9-XML XML 全量时间线导出

**需求:** FCP 7 XML 也支持 Full Timeline 模式（`<clipitem>` + `<gap>` 交替）

**审查意见:** XML 的 `<gap>` 不支持 Marker，仅通过 `<name>` 标识删除区域

#### Step 4.1: 后端 -- XML 导出添加 full_timeline 模式

**文件:** `core/export_timeline.py`

**改动:**
1. `export_xmeml_premiere()` 添加参数 `mode: str = "clean"`
2. 当 `mode == "full_timeline"` 时：
   - 合并 keep_ranges 和 deleted_ranges，按 start 排序
   - keep -> `<clipitem>`（同现有逻辑）
   - deleted -> `<gap>` 元素，`<name>` 填入 `Milo-Cut Deleted ({start}-{end})`
   - **同样使用绝对帧数相减**计算 duration
3. 注意 `<start>`/`<end>` 偏移量需连续（gap 结束后 clip 从 gap 的 end 开始）

**验证:** 生成的 XML 文件包含交替的 clipitem 和 gap 元素

#### Step 4.2: 后端 -- bridge 方法传递 mode 参数

**文件:** `main.py`

**改动:**
1. `export_xmeml_premiere` bridge 方法添加 `mode: str = "clean"` 参数
2. 传递给底层函数

**验证:** API 调用参数正确传递

#### Step 4.3: 前端 -- XML 导出按钮联动 mode

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:**
1. `handleExportXml()` 读取 `otioExportMode` ref 的值传递给 XML 导出
2. Full Timeline 模式对 XML 和 OTIO 共用同一个 radio 选择

**验证:** XML 和 OTIO 均可导出 Full Timeline 模式

---

## Phase 3: P1 UX 改善

### Task 5: A-3 时间线格式按钮重排 + 标签修正

**现状:** 按钮已按正确顺序排列 (OTIO -> XML -> EDL)，标签已更新

**待确认:** 需验证当前按钮顺序是否与审计报告一致
- OTIO (DaVinci / New PR / Others) -- bg-indigo-600
- XML (FCP 7) -- bg-gray-100
- EDL (DaVinci Only) -- bg-gray-100

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:** 如已符合要求则跳过；否则调整按钮顺序和标签

---

### Task 6: A-2 旧通知改用 Toast 系统

**现状:** ExportPage 使用内联 `statusMessage`/`errorMessage`，项目已有完整的 Toast 系统 (`useToast.ts`)

**原则:** Toast 用于一次性通知（成功/失败），内联 statusMessage 保留用于持续状态（进度中）

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:**
1. 添加 `import { useToast } from "@/composables/useToast"`
2. 在 setup 中调用 `const { showToast } = useToast()`
3. 修改所有 export handler：
   - 导出开始：保留 `statusMessage = "正在导出..."`（持续状态）
   - 导出成功：改为 `showToast("xxx 导出完成", "success")`，清除 statusMessage
   - 导出失败：改为 `showToast("导出失败: ...", "error")`，清除 statusMessage
4. 修复 line 159-161 的 `finally` 块 bug（成功消息被立即清除）

**验证:** 导出成功/失败时右下角出现 Toast 通知，进度中状态保留在内联位置

---

## Phase 4: P2 进阶功能

### Task 7: A-4 OTIO 音频转场模式选择

**需求:** OTIO 导出时提供两种转场模式 -- Crossfade (已实现) + Separate Fade In/Out (待实现)

**审查意见:** 需注意 NLE 兼容性风险 -- 达芬奇/PR 的 OTIO Adapter 可能不识别自定义 Effect。实现后需实际导入达芬奇和 PR 验证，如果 NLE 忽略 Effect，在 UI 上添加 tooltip 提示。

#### Step 7.1: 后端 -- 新增 fade 模式参数和 Effect 构建函数

**文件:** `core/export_timeline.py`

**改动:**
1. `export_otio()` 添加参数 `fade_mode: str = "crossfade"`（值为 `"crossfade"` 或 `"separate"`）
2. 新增 `_build_otio_clips_with_fade_effects(clips, fade_duration, fps) -> list`
   - 为每个 Clip 开头附加 `FadeIn Effect`，结尾附加 `FadeOut Effect`
   - 使用 `otio.schema.Effect(name="AudioFadeIn", effect_name="Audio Fade In")`
   - duration 存储在 `metadata={"duration": RationalTime(frames, fps)}`
   - 首个 Clip 仅 FadeOut，末个 Clip 仅 FadeIn
   - 单个 Clip 时 FadeIn + FadeOut 都附加
3. 仅在 `mode == "clean"` 且 `fade_duration > 0` 时生效
4. **同样使用绝对帧数**计算 Effect duration

**验证:** 生成 .otio 文件中 Clip 包含正确的 Effect 对象

#### Step 7.2: 后端 -- bridge 方法传递 fade_mode

**文件:** `main.py`

**改动:**
1. `export_otio` bridge 方法添加 `fade_mode: str = "crossfade"` 参数
2. 传递给底层函数

#### Step 7.3: 前端 -- 添加转场模式选择 UI

**文件:** `frontend/src/pages/ExportPage.vue`

**改动:**
1. 新增 ref `otioFadeMode: Ref<"crossfade" | "separate">`，默认 `"crossfade"`
2. 在 `otioFadeDuration` 滑块下方添加 radio 组：
   - `(o) Crossfade` -- 相邻片段交叉淡入淡出
   - `( ) Separate Fade In/Out` -- 每个片段独立淡入淡出
3. 仅在 `otioExportMode === "clean"` 且 `otioFadeDuration > 0` 时显示
4. 添加 tooltip 提示："分离淡入淡出依赖特定剪辑软件的支持"
5. `handleExportOtio()` 传递 `fade_mode` 参数

**验证:** 两种模式均可正确导出

---

### Task 8: A-5 FFmpeg filter_complex 音视频过渡 (P2/P3)

**风险:** HIGH -- 级联 xfade 对内存消耗极大，offset 精度要求极高
**建议:** 作为实验性功能，cuts > 20 时弹窗警告

**本迭代状态:** 仅做调研和接口预留，不实际实现

**预留接口:**
1. `core/config.py` 添加 `export_transition_mode: "none" | "crossfade"` 设置（默认 `"none"`）
2. `ExportPage.vue` 预留 checkbox UI 位置（disabled 状态）
3. `export_service.py` 预留 transition 参数

---

## 不在本计划范围

| 项目 | 原因 |
|------|------|
| A-8 AAF 导出 | P3 backlog，OTIO 已覆盖主流 NLE |
| A-9-AAF Full Timeline | P3 backlog，同上 |

---

## 关键架构约束 (审查意见)

### 1. 绝对帧数法则 (A-7 / A-9-XML)

构建 Full Timeline 时，**禁止**用时长舍入计算 Duration：

```python
# WRONG
dur_frames = round((end - start) * fps)

# CORRECT
start_frame = _sec_to_frames(start, fps)
end_frame = _sec_to_frames(end, fps)
dur_frames = end_frame - start_frame
```

适用于所有 OTIO/XML 时间线构建中的 Duration 计算。

### 2. ThreadingHTTPServer 为 P0 必须项 (A-1)

前端释放 video 连接只是防御手段，**必须**同时改后端为 `ThreadingHTTPServer` 才能根治。

### 3. NLE 兼容性验证 (A-4)

Separate Fade In/Out 模式生成的自定义 Effect 需在达芬奇/PR 中实测。如果 NLE 不识别，添加 UI 提示而非尝试 workaround。

### 4. xfade 级联陷阱 (A-5)

如未来实现 FFmpeg 过渡，必须使用绝对时间戳推算 offset，cuts > 20 时警告用户。

---

## 涉及文件汇总

| 文件 | 涉及任务 | 改动规模 |
|------|----------|----------|
| `core/media_server.py` | A-1 | ~3 行 (导入+基类替换) |
| `frontend/src/pages/ExportPage.vue` | A-1, A-2, A-3, A-4, A-7, A-9-XML | ~100 行 |
| `frontend/src/pages/WorkspacePage.vue` | A-1 | ~15 行 |
| `frontend/src/components/waveform/ScrollbarStrip.vue` | A-6 | ~15 行 |
| `frontend/src/components/waveform/WaveformCanvas.vue` | A-6 | ~10 行 |
| `frontend/src/composables/useTimelineMetrics.ts` | A-6 | ~15 行 |
| `core/export_timeline.py` | A-4, A-7, A-9-XML | ~150 行 |
| `main.py` | A-4, A-7, A-9-XML | ~15 行 |
| `core/config.py` | A-5 (预留) | ~2 行 |

---

## 验证检查清单

每个 Task 完成后：

- [ ] 后端测试通过 (`uv run pytest`)
- [ ] 前端构建通过 (`cd frontend && bun run build`)
- [ ] 前端建构通过后回到根目录`cd ..`
- [ ] 手动验证功能正确性
- [ ] 无 emoji 引入代码或 commit message
- [ ] API envelope 格式正确 (`{success, data, error}`)

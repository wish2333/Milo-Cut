# Milo-Cut v1.1.0 代码审计报告

> 审计范围：PRD v1.1.0 规划的全部 P0/P1/P2 功能项，对照 v1.0.0 代码库逐文件核实实现状态。
>
> 审计方法：静态代码分析 + 交叉引用 PRD 验收标准。

---

## 1. 审计结论总览

| 类别 | PRD 状态判定 | 审计结果 | 是否一致 |
|------|-------------|---------|---------|
| EditSummaryModal 未接入 | P0 紧急 | 确认：组件开发+测试完成，未挂载到任何页面 | 一致 |
| 版本号不一致 | P0 | 确认：main.py 硬编码 "0.1.0"，pyproject.toml/package.json 为 "0.2.1" | 一致 |
| 无自动保存 | P0 新增 | 确认：project_service.py 无任何 debounce/autosave 逻辑 | 一致 |
| 媒体丢失重链接 | P0 新增 | 确认：open_project 无路径存在性校验，media_hash 始终为空 | 一致 |
| FFmpeg 管理 | P0 新增 | 确认：无检测/下载/管理代码，ffmpeg_path 设置从未被读取 | 一致 |
| 字幕叠加预览 | P0 | 确认：播放器为纯 `<video>` 元素，无任何叠加层 | 一致 |
| AppSettings 类型不匹配 | 未在 PRD 中 | **新发现**：前端类型仅 8 字段，settings.json 有 20+ 键 | -- |
| detect_gpu 仅 NVIDIA | 未在 PRD 中 | **新发现**：无 AMD/Intel/Apple 检测 | -- |

**结论**：PRD v1.1.0 对实现状态的描述与代码实际状态一致。审计发现 2 个 PRD 未覆盖的技术债务，经架构师审核已确认纳入 v1.1.0 P0。

---

## 2. P0 功能项逐项审计

### 2.1 EditSummaryModal 接入导出流程

**PRD 描述**：组件已开发完成（含测试），仅需挂载到 ExportPage。

**审计发现**：

- `EditSummaryModal.vue` 存在于 `frontend/src/components/workspace/`，92 行，功能完整
- 测试文件 `EditSummaryModal.test.ts` 存在
- 后端 `get_edit_summary()` 位于 `project_service.py:865-935`，计算逻辑完整（40%/60s/连续删除三项警告）
- `main.py:555-556` 已通过 `@expose` 暴露桥接方法
- 前端 `useExport.ts:35` 已有 `getExportSummary()` 调用
- **但**：全局搜索 `EditSummaryModal` 在 `.vue` 文件中无任何 import，确认未挂载

**风险**：用户导出时无法看到删除摘要，误删防护形同虚设。

**建议**：在 ExportPage.vue 的导出按钮点击流程中插入确认弹窗，工作量极小。

---

### 2.2 项目文件自动保存

**PRD 描述**：编辑操作后自动保存到 project.json，需 debounce 300-500ms。

**审计发现**：

- `project_service.py:save_project()` 使用原子写入（tmp + os.replace），机制可靠
- `useProject.ts` 暴露 `saveProject()` 方法，调用 `call("save_project")`
- 搜索 `auto.?save|autosave|_save_timer|debounce.*save`：**零匹配**
- `isDirty` 状态通过 `EVENT_PROJECT_DIRTY` 事件维护，但无任何自动触发保存的逻辑

**风险**：崩溃/刷新/意外关闭导致全部编辑丢失。

**建议**：在 useProject.ts 中监听 isDirty 变化，debounce 后调用 saveProject()。

---

### 2.3 媒体丢失重链接

**PRD 描述**：打开项目时检测 media.path 是否存在，不存在则弹出重定位对话框；计算 media_hash 校验。

**审计发现**：

- `open_project()` 无路径存在性校验逻辑
- `MediaInfo.media_hash` 字段在模型中定义，但始终为空字符串
- 无任何 SHA-256 计算代码

**风险**：源文件移动/删除后打开项目直接崩溃。

---

### 2.4 版本号统一

**PRD 描述**：修复 main.py 硬编码 "0.1.0"。

**审计发现**：

- `main.py:301` -- `"version": "0.1.0"` （硬编码，过时）
- `pyproject.toml:3` -- `version = "0.2.1"`
- `frontend/package.json:4` -- `"version": "0.2.1"`
- 三处不一致

**建议**：从 pyproject.toml 读取版本，或建立单点版本源。

---

### 2.5 字幕叠加预览

**PRD 描述**：播放器底部实时字幕叠加显示，跟随当前播放时间，纯前端实现。

**审计发现**：

- `WorkspacePage.vue` 的视频播放器为纯 `<video>` 元素，无任何叠加层
- `PreviewPlayer.vue` 同样无字幕叠加
- 全局搜索 `SubtitleOverlay|subtitle.*overlay|字幕叠加`：**零匹配**
- README 声称 "built-in video player with subtitle overlay" 但功能未实现

**建议**：在 `<video>` 元素上叠加绝对定位的字幕 div，通过 `timeupdate` 事件同步当前字幕文本。

---

### 2.6 FFmpeg 管理与设置页

**PRD 描述**：新增设置页面，集成 FFmpeg 检测/下载/版本切换功能。

**审计发现**：

- `ffmpeg_service.py:_find_ffmpeg()` 和 `_find_ffprobe()` 仅使用 `shutil.which()`
- `settings.json` 中 `ffmpeg_path` 和 `ffprobe_path` 字段存在但**从未被读取**
- 无 FFmpeg 下载、安装、版本管理代码
- `detect_gpu()` 仅检测 NVIDIA（通过 nvidia-smi），无 AMD/Intel/Apple 检测
- 无设置页面 UI 组件

**新发现 -- 设置字段不匹配**：

- `settings.json` 有 20+ 键（含 export_video_codec、export_crf、silence_margin 等）
- 前端 `AppSettings` 类型仅定义 8 个字段
- 导致部分设置无法通过前端读取/修改

---

## 3. P1 功能项审计

### 3.1 撤销/重做（Undo/Redo）

**PRD 描述**：基于 Command 模式，利用 Pydantic 不可变模型。

**审计发现**：

- 全局搜索 `undo|redo|history.*stack|command.*pattern`：**零匹配**
- Pydantic 模型已使用 `frozen=True`，具备不可变基础
- 当前所有编辑操作直接修改 `self._current` 状态，无历史快照

**评估**：PRD 方案 A（Command 模式 + 快照栈）可行，Pydantic 不可变模型是良好基础。

---

### 3.2 前端状态管理评估（Pinia）

**PRD 描述**：评估是否需要迁移 composables 到 Pinia。

**审计发现**：

- 当前 13 个 composables，均使用模块级 ref 实现全局单例
- 搜索 `pinia|createStore|defineStore`：**零匹配**
- 搜索 `package.json` 中 pinia 依赖：**未找到**

**评估**：当前 composable 架构合理，Pinia 主要价值为 DevTools。建议 Undo/Redo 完成后再评估。

---

## 4. P2 功能项审计

### 4.1 交叉验证高亮

- 搜索静音段选中与字幕高亮的联动代码：**零匹配**
- 当前仅支持点击行跳转，无反向联动

### 4.2 TranscriptRow/SilenceRow 右键菜单

- `SegmentBlocksLayer.vue` 有右键菜单实现
- `TranscriptRow.vue` 和 `SilenceRow.vue` 无右键菜单

### 4.3 VTT 导出

- 搜索 `vtt|webvtt|export.*vtt`：**零匹配**
- 仅支持 SRT 导出

---

## 5. 预留字段审计

PRD 列出了 8 个有意保留的预留字段。审计确认：

| 字段 | 模型中存在 | 被生产代码填充 | 被前端消费 | 结论 |
|------|-----------|--------------|-----------|------|
| MediaInfo.proxy_path | 是 | 否 | 是（PreviewPlayer fallback） | 保留 |
| MediaInfo.media_hash | 是 | 否 | 否 | v1.1.0 需填充 |
| Segment.speaker | 是 | 否 | 否 | 保留 |
| Word 模型 + Segment.words | 是 | 否 | 否 | 保留 |
| TaskType.TRANSCRIPTION | 是 | 无 handler | 否 | 保留 |
| TaskType.VAD_ANALYSIS | 是 | 无 handler | 否 | 保留 |
| TranscriptData.engine | 是 | 默认 "srt" | 否 | 保留 |
| AnalysisResult.type 联合类型 | 是 | "filler"/"error" | 否 | 保留 |

**结论**：所有预留字段均为未来版本有意保留，不应作为死代码清理。PRD 描述准确。

---

## 6. 技术债务新发现

以下问题未在 PRD 中明确列出，但审计过程中发现：

### 6.1 settings.json 与前端 AppSettings 类型不匹配

- **位置**：`frontend/src/types/edit.ts:16` 的 `AppSettings` 接口仅 8 字段
- **影响**：`silence_margin`、`silence_subtitle_padding`、所有 `export_*` 字段无法通过前端 settings UI 管理
- **建议**：同步 AppSettings 类型与 settings.json 全部字段

### 6.2 detect_gpu 仅检测 NVIDIA

- **位置**：`main.py:385-411`
- **影响**：Intel/AMD/Apple Silicon 用户看不到可用硬件编码器
- **建议**：扩展检测逻辑，参考 ffmpeg -encoders 输出解析

### 6.3 ffmpeg_path/ffprobe_path 设置项死代码

- **位置**：`data/settings.json` + `core/config.py` 定义了路径设置
- **影响**：`ffmpeg_service.py` 从未读取这些设置，用户手动配置路径无效
- **建议**：FFmpeg 管理功能实现时，优先读取 settings 中的路径，fallback 到 shutil.which()

---

## 7. v1.1.0 工作量评估复核

| 功能 | PRD 预估 | 审计复核 | 说明 |
|------|---------|---------|------|
| EditSummaryModal 接入 | 0.5-1 天 | **0.5 天** | 组件已就绪，仅需挂载 + 导出流程串联 |
| 项目自动保存 | 2-3 天 | **1-2 天** | useProject.ts 中加 debounce 即可，后端 save 已就绪 |
| 媒体重链接 | 2-3 天 | **2-3 天** | 需新建对话框组件 + SHA-256 计算 |
| 版本号统一 | 0.5 天 | **0.5 天** | 单点读取 pyproject.toml |
| 字幕叠加预览 | 2-3 天 | **2 天** | 纯前端，叠加 div + timeupdate 同步 |
| FFmpeg 管理与设置页 | 1 周 | **1-1.5 周** | 需新建设置页 + 6 级检测 + 下载管理，含 AppSettings 类型修复 |
| Undo/Redo | 1-2 周 | **1-2 周** | Pydantic frozen 模型是良好基础 |
| Pinia 评估 | 2-3 天 | **2-3 天** | 依赖 Undo/Redo 完成 |

---

## 8. 验收标准逐项对照

| 验收标准 | 当前状态 | 可行性 |
|---------|---------|--------|
| 导出前弹出 EditSummaryModal 确认 | 未实现，组件已就绪 | 可行 |
| 编辑后自动保存（debounce） | 未实现，无任何自动保存逻辑 | 可行，useProject.ts 加 debounce |
| 媒体文件移动后弹出重定位对话框 | 未实现，open_project 无路径校验 | 可行 |
| 打开项目时计算 media_hash SHA-256 | 未实现，字段始终为空 | 可行 |
| 版本号三处一致 | 不一致（0.1.0 vs 0.2.1） | 可行 |
| Ctrl+Z 撤销 / Ctrl+Y 重做 | 未实现 | 可行，Pydantic frozen 模型支持 |
| 播放视频时显示字幕叠加 | 未实现 | 可行，纯前端 |
| 设置页 FFmpeg 检测/下载/切换 | 未实现，无设置页 | 可行，需新建 |

---

## 附录 A：关键代码片段

### A.1 EditSummaryModal.vue（完整）

`frontend/src/components/workspace/EditSummaryModal.vue`（92 行）

```vue
<script setup lang="ts">
import { computed } from "vue"
import type { EditSummary } from "@/types/edit"

const props = defineProps<{
  summary: EditSummary
  visible: boolean
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const formattedTotal = computed(() => formatDuration(props.summary.total_duration))
const formattedDelete = computed(() => formatDuration(props.summary.delete_duration))
const isWarning = computed(() => props.summary.delete_percent > 40)

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, "0")}`
}
</script>

<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    @click.self="emit('cancel')"
  >
    <div class="bg-white rounded-2xl shadow-2xl w-[480px] max-w-[90vw] overflow-hidden">
      <div class="px-6 pt-6 pb-4 text-center">
        <h2 class="text-lg font-semibold text-gray-800">导出汇总摘要</h2>
      </div>

      <div class="flex justify-center gap-8 px-6 pb-4">
        <div class="text-center">
          <div class="text-3xl font-bold text-blue-600">{{ formattedTotal }}</div>
          <div class="text-xs text-gray-500 mt-1">预计时长</div>
        </div>
        <div class="text-center">
          <div class="text-3xl font-bold text-gray-500">-{{ formattedDelete }}</div>
          <div class="text-xs text-gray-500 mt-1">裁剪掉时长</div>
        </div>
        <div class="text-center">
          <div
            class="text-3xl font-bold"
            :class="isWarning ? 'text-red-600' : 'text-blue-600'"
          >
            {{ summary.delete_percent }}%
          </div>
          <div class="text-xs text-gray-500 mt-1">占比</div>
        </div>
      </div>

      <div v-if="summary.warnings.length > 0" class="mx-6 mb-4">
        <div class="text-sm font-medium text-gray-700 mb-2">检测到以下异常情况:</div>
        <div class="space-y-1">
          <div
            v-for="(warning, i) in summary.warnings"
            :key="i"
            class="flex items-start gap-2 px-3 py-2 bg-yellow-50 rounded text-sm text-yellow-800"
          >
            <span class="shrink-0">[!]</span>
            <span>{{ warning }}</span>
          </div>
        </div>
      </div>

      <div v-if="isWarning" class="mx-6 mb-4 px-3 py-2 bg-red-50 rounded text-sm text-red-700">
        删除内容占总时长超过 40%，请确认是否继续导出。
      </div>

      <div class="flex flex-col gap-2 px-6 pb-6">
        <button
          class="w-full py-2.5 rounded-full bg-blue-500 text-white font-medium hover:bg-blue-600 transition-colors"
          @click="emit('confirm')"
        >
          确认导出
        </button>
        <button
          class="w-full py-2.5 rounded-full border border-blue-500 text-blue-500 font-medium hover:bg-blue-50 transition-colors"
          @click="emit('cancel')"
        >
          返回检查
        </button>
      </div>
    </div>
  </div>
</template>
```

### A.2 main.py 版本号硬编码

`main.py:299-309`

```python
@expose
def get_app_info(self) -> dict:
    return {
        "success": True,
        "data": {
            "name": "Milo-Cut",
            "version": "0.1.0",   # 硬编码，与 pyproject.toml 的 0.2.1 不一致
            "python": sys.version,
            "platform": sys.platform,
        },
    }
```

### A.3 project_service.py save_project（无自动保存）

`core/project_service.py:136-158`

```python
def save_project(self) -> dict:
    """Save the current project to disk."""
    if self._current is None or self._current_path is None:
        return {"success": False, "error": "No project is open"}

    try:
        updated = self._current.model_copy(update={
            "project": self._current.project.model_copy(update={
                "updated_at": datetime.now().isoformat(),
            }),
        })
        self._current = updated

        tmp = self._current_path.with_suffix(".tmp")
        tmp.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, self._current_path)

        logger.info("Saved project to {}", self._current_path)
        return {"success": True}

    except Exception as e:
        logger.exception("Failed to save project")
        return {"success": False, "error": str(e)}
```

### A.4 project_service.py get_edit_summary

`core/project_service.py:865-935`

```python
def get_edit_summary(self) -> dict:
    """Compute delete statistics and protection warnings."""
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    segments = self._current.transcript.segments
    edits = self._current.edits
    warnings: list[str] = []

    total_duration = 0.0
    for seg in segments:
        total_duration = max(total_duration, seg.end)

    delete_duration = 0.0
    confirmed_edits = [e for e in edits if e.action == "delete" and e.status in (EditStatus.PENDING, EditStatus.CONFIRMED)]
    for edit in confirmed_edits:
        delete_duration += edit.end - edit.start

    if total_duration > 0 and delete_duration / total_duration > 0.40:
        warnings.append(
            f"Warning: {delete_duration:.1f}s marked for deletion ({delete_duration / total_duration:.0%} of total duration)"
        )

    for edit in confirmed_edits:
        seg_dur = edit.end - edit.start
        if seg_dur > 60:
            warnings.append(
                f"Warning: edit {edit.id} spans {seg_dur:.1f}s (>60s threshold)"
            )

    subtitle_segs = sorted(
        [s for s in segments if s.type == SegmentType.SUBTITLE],
        key=lambda s: s.start,
    )
    edit_seg_ids = set()
    for edit in confirmed_edits:
        for seg in subtitle_segs:
            if abs(seg.start - edit.start) < 0.01 and abs(seg.end - edit.end) < 0.01:
                edit_seg_ids.add(seg.id)

    consecutive = 0
    for seg in subtitle_segs:
        if seg.id in edit_seg_ids:
            consecutive += 1
            if consecutive >= 3:
                warnings.append("Warning: 3+ consecutive subtitle segments marked for deletion")
                break
        else:
            consecutive = 0

    return {
        "success": True,
        "data": {
            "total_duration": round(total_duration, 2),
            "delete_duration": round(delete_duration, 2),
            "delete_percent": round(delete_duration / total_duration * 100, 1) if total_duration > 0 else 0,
            "edit_count": len(confirmed_edits),
            "warnings": warnings,
        },
    }
```

### A.5 ffmpeg_service.py 路径解析（仅 shutil.which）

`core/ffmpeg_service.py:28-38`

```python
def _find_ffprobe() -> str:
    """Find ffprobe binary on PATH."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise FileNotFoundError("ffprobe not found on PATH")
    return ffprobe

def _find_ffmpeg() -> str:
    """Find ffmpeg binary on PATH."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg not found on PATH")
    return ffmpeg
```

### A.6 main.py detect_gpu（仅 NVIDIA）

`main.py:385-411`

```python
@expose
def detect_gpu(self) -> dict:
    """Detect GPU availability and return supported hardware encoders."""
    encoders: list[str] = []
    gpu_name = ""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
            **_SUBPROCESS_KWARGS,
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = stdout.strip().split("\n")[0]
            encoders.extend(["h264_nvenc", "hevc_nvenc", "av1_nvenc"])
    except FileNotFoundError:
        pass
    if sys.platform != "darwin":
        encoders.append("libsvtav1")
    return {"success": True, "data": {"nvidia": bool(gpu_name), "gpu_name": gpu_name, "encoders": encoders}}
```

### A.7 data/settings.json（完整）

```json
{
  "ffmpeg_path": "",
  "ffprobe_path": "",
  "theme": "light",
  "language": "zh-CN",
  "silence_threshold_db": -30,
  "silence_min_duration": 0.2,
  "silence_margin": 0.05,
  "silence_subtitle_padding": 0.05,
  "trim_subtitles_on_silence_overlap": true,
  "export_fade_duration": 0.0,
  "export_transition_mode": "none",
  "filler_words": ["嗯","啊","呃","然后","就是","那个","怎么说呢","你知道","对吧","其实"],
  "error_trigger_words": ["不对","重来","重新说","说错了","刚才说错了","这段不要","再来一遍","算了","不是这样的"],
  "export_video_codec": "av1_nvenc",
  "export_audio_codec": "aac",
  "export_audio_bitrate": "192k",
  "export_preset": "medium",
  "export_crf": 36,
  "export_resolution": "original",
  "export_ffmpeg_transitions": true,
  "export_ffmpeg_fade_duration": 0,
  "export_ffmpeg_fade_mode": "crossfade"
}
```

### A.8 前端 AppSettings 类型（字段不匹配）

`frontend/src/types/edit.ts:16-27`

```typescript
export interface AppSettings {
  ffmpeg_path: string
  ffprobe_path: string
  theme: string
  language: string
  silence_threshold_db: number
  silence_min_duration: number
  filler_words: string[]
  error_trigger_words: string[]
}
```

对比 settings.json，缺少以下字段：`silence_margin`、`silence_subtitle_padding`、`trim_subtitles_on_silence_overlap`、`export_fade_duration`、`export_transition_mode`、`export_video_codec`、`export_audio_codec`、`export_audio_bitrate`、`export_preset`、`export_crf`、`export_resolution`、`export_ffmpeg_transitions`、`export_ffmpeg_fade_duration`、`export_ffmpeg_fade_mode`。

### A.9 useSettings.ts（完整）

`frontend/src/composables/useSettings.ts`

```typescript
export function useSettings() {
  const settings = ref<AppSettings | null>(null)

  async function loadSettings(): Promise<boolean> {
    const res = await call<AppSettings>("get_settings")
    if (res.success && res.data) { settings.value = res.data; return true }
    return false
  }

  async function updateSettings(updates: Partial<AppSettings>): Promise<boolean> {
    const res = await call<AppSettings>("update_settings", updates)
    if (res.success && res.data) { settings.value = res.data; return true }
    return false
  }

  onMounted(() => { loadSettings() })
  return { settings, loadSettings, updateSettings }
}
```

### A.10 WorkspacePage.vue 视频播放器（无字幕叠加）

`frontend/src/pages/WorkspacePage.vue` 视频区域模板：

```html
<video
  ref="videoRef"
  :src="videoUrl"
  class="max-h-full max-w-full rounded"
  preload="metadata"
  @loadedmetadata="handleVideoLoaded"
  @timeupdate="handleTimeUpdate"
  @play="videoPaused = false"
  @pause="videoPaused = true"
  @click="handleTogglePlay"
/>
```

无任何字幕叠加层元素。

### A.11 useProject.ts 关键状态（无自动保存）

`frontend/src/composables/useProject.ts` 关键部分：

```typescript
const project = ref<Project | null>(null)
const isDirty = ref(false)
const loading = ref(false)

// 事件监听
onEvent(EVENT_PROJECT_SAVED, () => { isDirty.value = false })
onEvent(EVENT_PROJECT_DIRTY, () => { isDirty.value = true })

// 手动保存
async function saveProject(): Promise<boolean> {
  const res = await call("save_project")
  if (res.success) { isDirty.value = false; return true }
  return false
}
```

无 debounce、无 watcher、无自动触发保存逻辑。

### A.12 media_server.py 路由

`core/media_server.py:63-68`

```python
def _route(self):
    clean = self.path.split("?", 1)[0]
    if clean == "/waveform":
        return (self.waveform_path, "application/json")
    if clean == "/media":
        return (self.file_path, self.mime_type)
    return (None, None)
```

### A.13 ExportPage.vue 三栏布局

`frontend/src/pages/ExportPage.vue` 模板结构：

```html
<template>
  <!-- Top nav: back button, title, status -->
  <!-- Progress bar (if exporting) -->
  <div class="flex h-full">
    <!-- Left: EncodingSettings (w-80) -->
    <!-- Center: PreviewPlayer (flex-1) -->
    <!-- Right: Export actions (w-80) -->
  </div>
</template>
```

EditSummaryModal 应挂载在此页面，导出按钮点击时弹出。

---

## 附录 B：架构师审查意见与落地指导

> 以下为架构师基于本审计报告的最终审查意见，已批准按 PRD v1.1.0 开发。

### B.1 必须补充进 PRD 的遗漏项（已确认纳入 P0）

#### B.1.1 AppSettings 接口断层

**问题**：前端 `types/edit.ts` 仅定义 8 个字段，后端 `settings.json` 包含 20+ 核心字段（包括导出参数、静音边距等）。

**架构要求**：开发设置页之前，必须先统一全栈配置数据模型。以 Pydantic 模型为 Single Source of Truth，通过工具（pydantic2ts 或手动维护）严格同步到前端 TypeScript 接口。

#### B.1.2 detect_gpu 平台局限性

**问题**：当前强依赖 `nvidia-smi`，Mac（Apple Silicon/VideoToolbox）和 Intel/AMD 用户无法被识别。

**架构要求**：废弃 `nvidia-smi` 硬编码检测，改用 `ffmpeg -hwaccels` 或 1 秒 Dummy 编码探测可用性。此修复纳入 P0。

### B.2 核心功能架构落地指导

#### A. 自动保存防丢机制

- debounce 时间调整为 **2000ms**（PRD 原写的 300-500ms 偏短，几 MB JSON 文件不宜过频）
- 前端必须持有 **isSaving 锁**，避免快速连续操作引发多线程写文件冲突

#### B. 撤销/重做

- 采用**状态快照（State Snapshot）**而非命令增量
- 每次 `isDirty = true` 操作前，将 `project.value` 深度克隆压入 `undoStack`
- 设置 `MAX_HISTORY = 50` 防止内存泄漏

#### C. 字幕叠加预览

- **不使用 `@timeupdate`**（触发频率仅 3-4 次/秒，字幕延迟明显）
- **正确做法**：`play` 时启动 `requestAnimationFrame` 循环，高频读取 `video.currentTime` 匹配字幕；`pause` 时取消循环

#### D. EditSummaryModal 拦截器模式

在 ExportPage.vue 导出按钮点击事件中：

```javascript
async function onExportClicked() {
   const summary = await getExportSummary();
   if (summary.delete_percent > 0) {
       showModal.value = true; // 等待弹窗内 confirm
   } else {
       executeExport();
   }
}
```

### B.3 预留字段保留 -- 架构师肯定

在客户端应用的本地 JSON 存储中，频繁变动 Schema 会导致严重的数据迁移难题。当前模型已具备向前兼容性，是优秀底层架构的体现。

### B.4 审计结论

**批准按照修改后的 PRD v1.1.0 进行开发**。Sprint 计划中需补充"AppSettings 接口断层"与"跨平台 GPU 检测"两个任务。

---

*审计人：代码执行负责人*
*审计日期：2026-05-27*
*审计版本：v1.1.0-rc4（含架构师审查意见）*
*基于 Milo-Cut v1.0.0 代码库逐文件静态分析*
*经架构师最终审查批准*

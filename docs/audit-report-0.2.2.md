# Milo-Cut 审计报告 -- 视频编码参数完善 (0.2.2)

**审计日期:** 2026-05-26
**审计范围:** 导出视频编码参数配置，参照 ff-intelligent-neo 2.1.0+ 的编码器推荐参数
**当前分支:** dev-0.2.2

---

## 1. 审计背景

Milo-Cut 当前的视频导出编码配置存在以下结构性问题：

- 所有编码器共享同一套 CRF 范围 (18-32) 和 preset 列表，缺少编码器特定的推荐值
- 未传递 `-pix_fmt` (像素格式)，依赖 FFmpeg 默认值，可能导致兼容性问题
- 未传递 `-movflags +faststart`，MP4 文件不适合网络流式播放
- 前端默认 `preset: "medium"` 与后端默认 `preset: "fast"` 不一致
- 硬件编码器 (NVENC/QSV/AMF) 使用 `-crf` 参数，但这些编码器应使用 `-cq`/`-qp` 参数

ff-intelligent-neo 在 2.1.0 之后对编码器系统进行了全面改造，引入了编码器注册表、推荐质量值、质量模式映射等机制。本报告评估将这些改进移植到 Milo-Cut 的可行性和具体方案。

---

## 2. 现状分析

### 2.1 当前 FFmpeg 命令构建 (export_service.py:130-138)

```python
cmd = [
    ffmpeg, "-hide_banner", "-y",
    "-i", media_path,
    "-filter_complex_script", filter_path,
    "-map", "[outv]", "-map", "[outa]",
    "-c:v", video_codec,
    "-preset", preset,
    "-crf", str(crf),
    "-c:a", audio_codec,
    "-b:a", audio_bitrate,
]
```

**问题:**
- `-crf` 对 NVENC/QSV/AMF 编码器无效，这些编码器使用 `-cq`/`-qp`/`-q:v`
- 无 `-pix_fmt`，部分播放器可能不支持 FFmpeg 自动选择的像素格式
- 无 `-movflags +faststart`，MP4 的 moov atom 在文件末尾，不利于网络播放
- `_extract_segment` 硬编码 `-c:v libx264 -preset fast`，无法使用用户选择的编码器

### 2.2 当前前端编码器配置 (EncodingSettings.vue)

| 参数 | 当前选项 | 问题 |
|------|---------|------|
| 视频编码器 | libx264, libx265, libsvtav1, h264_nvenc, hevc_nvenc, av1_nvenc | 所有编码器共享同一 CRF 范围 |
| CRF | 18-32 滑块 | NVENC 的 CQ 推荐值为 28-36，不在该范围内 |
| Preset | ultrafast ~ veryslow (9 项) | NVENC 使用 different/fast/medium/slow 等不同 preset 名称 |
| 像素格式 | 未暴露 | 默认值不可控 |

### 2.3 默认值不一致

| 参数 | 前端默认 | 后端默认 (main.py) | 后端默认 (export_service.py) |
|------|---------|-------------------|---------------------------|
| preset | medium | fast | fast |
| crf | 23 | 23 | 23 |
| video_codec | libx264 | libx264 | libx264 |

---

## 3. ff-intelligent-neo 编码器推荐参数 (2.1.0+)

### 3.1 编码器注册表与推荐质量值

| 编码器 | 推荐质量值 | 质量模式 | FFmpeg 标志 | 说明 |
|--------|-----------|---------|------------|------|
| **P0: 首选** | | | | |
| av1_nvenc | 36 | cq | -cq 36 | RTX 40+ 推荐，最佳压缩效率 |
| libx265 | 24 | crf | -crf 24 | 质量/体积最佳平衡 |
| libsvtav1 | 32 | crf | -crf 32 | 开源 AV1，优秀压缩 |
| **P1: 备选** | | | | |
| libx264 | 23 | crf | -crf 23 | 最佳兼容性 |
| hevc_nvenc | 28 | cq | -cq 28 | NVIDIA 快速 H.265 |
| h264_nvenc | 28 | cq | -cq 28 | NVIDIA 快速 H.264 |
| av1_qsv | 32 | qp | -qp 32 | Intel AV1 硬件编码 |
| libvpx-vp9 | 31 | crf | -crf 31 | Web 友好格式 |
| **P2: 硬件特定** | | | | |
| h264_amf | 34 | qp | -qp 34 | AMD GPU |
| hevc_amf | 32 | qp | -qp 32 | AMD GPU H.265 |
| h264_qsv | 28 | qp | -qp 28 | Intel Quick Sync |
| hevc_qsv | 30 | qp | -qp 30 | Intel Quick Sync H.265 |

### 3.2 默认预设参数

| 预设 | 视频编码器 | 质量模式 | 质量值 | Preset | 像素格式 | 音频比特率 |
|------|-----------|---------|--------|--------|---------|-----------|
| MP4 H.264 | libx264 | crf | 20 | medium | yuv420p | 192k |
| MP4 H.265 | libx265 | crf | 22 | medium | yuv420p | 192k |
| 720p H.264 | libx264 | crf | 20 | medium | yuv420p | 128k |

### 3.3 质量模式映射机制

```python
_QUALITY_FLAG_MAP = {
    "crf": "-crf",    # libx264, libx265, libsvtav1, libvpx-vp9
    "cq": "-cq",      # av1_nvenc, hevc_nvenc, h264_nvenc
    "qp": "-qp",      # h264_qsv, hevc_qsv, av1_qsv, h264_amf, hevc_amf
    "q": "-q:v",      # h264_videotoolbox, hevc_videotoolbox (macOS)
}
```

---

## 4. 问题清单与实施计划

### E-1 [BUG] 硬件编码器使用错误的质量参数

**严重度:** HIGH
**现状:** 所有编码器统一使用 `-crf` 参数，但 NVENC 编码器需要 `-cq`，QSV/AMF 编码器需要 `-qp`
**影响:** 使用硬件编码器时，CRF 参数被忽略，编码质量不可控
**方案:** 引入编码器 -> 质量模式映射表，根据编码器自动选择正确的质量参数

**具体改动:**

`core/export_service.py` -- 新增编码器配置映射:

```python
# 编码器质量模式映射
ENCODER_QUALITY_MODE: dict[str, str] = {
    "libx264": "crf", "libx265": "crf", "libsvtav1": "crf", "libvpx-vp9": "crf",
    "h264_nvenc": "cq", "hevc_nvenc": "cq", "av1_nvenc": "cq",
    "h264_qsv": "qp", "hevc_qsv": "qp", "av1_qsv": "qp",
    "h264_amf": "qp", "hevc_amf": "qp",
}

# 编码器推荐质量值
ENCODER_RECOMMENDED_QUALITY: dict[str, int] = {
    "libx264": 23, "libx265": 24, "libsvtav1": 32, "libvpx-vp9": 31,
    "h264_nvenc": 28, "hevc_nvenc": 28, "av1_nvenc": 36,
    "h264_qsv": 28, "hevc_qsv": 30, "av1_qsv": 32,
    "h264_amf": 34, "hevc_amf": 32,
}

QUALITY_FLAG_MAP: dict[str, str] = {
    "crf": "-crf", "cq": "-cq", "qp": "-qp", "q": "-q:v",
}
```

`core/export_service.py` -- 修改命令构建:

```python
# 原: "-crf", str(crf),
# 改:
quality_mode = ENCODER_QUALITY_MODE.get(video_codec, "crf")
quality_flag = QUALITY_FLAG_MAP[quality_mode]
cmd.extend([quality_flag, str(crf)])
```

---

### E-2 [BUG] 缺少像素格式参数 (-pix_fmt)

**严重度:** HIGH
**现状:** FFmpeg 命令不包含 `-pix_fmt`，依赖自动选择
**影响:** 某些播放器/平台不支持非 yuv420p 格式，可能导致播放失败
**方案:** 默认传递 `-pix_fmt yuv420p`，这是最广泛兼容的像素格式

**具体改动:**

`core/export_service.py`:

```python
cmd.extend(["-pix_fmt", "yuv420p"])
```

---

### E-3 [FEATURE] MP4/MOV 容器添加 movflags +faststart

**严重度:** MEDIUM
**现状:** MP4 文件的 moov atom 位于文件末尾
**影响:** 网络播放需要完整下载后才能开始播放，不利于流式传输
**方案:** 对 MP4/MOV 容器自动添加 `-movflags +faststart`

**具体改动:**

`core/export_service.py`:

```python
# 在命令构建中，根据输出格式判断
if output_path.endswith((".mp4", ".mov")):
    cmd.extend(["-movflags", "+faststart"])
```

---

### E-4 [BUG] 前端/后端 preset 默认值不一致

**严重度:** MEDIUM
**现状:** 前端默认 `preset: "medium"`，后端 fallback 默认 `preset: "fast"`
**影响:** 用户未修改 preset 时，实际使用的是后端的 "fast"，与 UI 显示不符
**方案:** 统一为 "medium"，与 ff-intelligent-neo 保持一致

**具体改动:**

`main.py:_handle_export_video`:

```python
# 原: preset = settings.get("export_preset", "fast")
# 改:
preset = settings.get("export_preset", "medium")
```

`core/export_service.py` 函数签名:

```python
# 原: preset: str = "fast"
# 改:
preset: str = "medium"
```

---

### E-5 [FEATURE] 编码器切换时自动调整推荐质量值

**严重度:** MEDIUM
**现状:** 用户切换编码器后，CRF 值保持不变
**影响:** 从 libx264 (CRF 23) 切换到 av1_nvenc 时，CRF 23 对 NVENC 来说质量过高
**方案:** 编码器切换时自动应用推荐质量值

**具体改动:**

`frontend/src/components/export/EncodingSettings.vue`:

```typescript
const ENCODER_RECOMMENDED_QUALITY: Record<string, number> = {
  "libx264": 23, "libx265": 24, "libsvtav1": 32,
  "h264_nvenc": 28, "hevc_nvenc": 28, "av1_nvenc": 36,
}

watch(videoCodec, (newCodec) => {
  const recommended = ENCODER_RECOMMENDED_QUALITY[newCodec]
  if (recommended !== undefined) {
    quality.value = recommended
  }
  updateSettings()
})
```

---

### E-6 [FEATURE] CRF 滑块范围根据编码器动态调整

**严重度:** LOW
**现状:** CRF 滑块固定范围 18-32
**影响:** NVENC 的 CQ 有效范围约 0-51，推荐 28-36；当前范围无法覆盖
**方案:** 根据编码器类型动态调整滑块范围和标签

**具体改动:**

`frontend/src/components/export/EncodingSettings.vue`:

```typescript
const qualityRange = computed(() => {
  const codec = videoCodec.value
  if (codec.includes("nvenc")) return { min: 0, max: 51, label: "CQ" }
  if (codec.includes("qsv") || codec.includes("amf")) return { min: 0, max: 51, label: "QP" }
  return { min: 18, max: 32, label: "CRF" }
})
```

---

### E-7 [FEATURE] 段提取使用用户选择的编码器

**严重度:** LOW
**现状:** `_extract_segment` 硬编码 `-c:v libx264 -preset fast -c:a aac`
**影响:** 导出过程中段提取始终使用 H.264，无法利用硬件加速
**方案:** 将用户选择的编码器参数传递到段提取函数

**具体改动:**

`core/export_service.py` -- `_extract_segment` 函数:

```python
def _extract_segment(
    ffmpeg: str, media_path: str, start: float, end: float,
    output_path: str, *,
    video_codec: str = "libx264",
    preset: str = "medium",
    crf: int = 23,
) -> str:
    # 使用编码器映射获取正确的质量参数
    quality_mode = ENCODER_QUALITY_MODE.get(video_codec, "crf")
    quality_flag = QUALITY_FLAG_MAP[quality_mode]

    base = [ffmpeg, "-hide_banner", "-y", "-ss", str(start), "-to", str(end),
            "-i", media_path, "-avoid_negative_ts", "make_zero"]
    codec_args = ["-c:v", video_codec, "-preset", preset,
                  quality_flag, str(crf), "-pix_fmt", "yuv420p", "-c:a", "aac"]
    cmd = base + codec_args + [output_path]
    ...
```

---

## 5. 前端编码器推荐值同步

参照 ff-intelligent-neo 的 `encoders.ts` 注册表，为 Milo-Cut 的 EncodingSettings.vue 添加编码器元数据:

```typescript
interface EncoderMeta {
  label: string
  recommendedQuality: number
  qualityMode: string   // "crf" | "cq" | "qp"
  qualityRange: [number, number]
}

const ENCODER_META: Record<string, EncoderMeta> = {
  "libx264":     { label: "H.264 (CPU)",     recommendedQuality: 23, qualityMode: "crf", qualityRange: [18, 28] },
  "libx265":     { label: "H.265 (CPU)",     recommendedQuality: 24, qualityMode: "crf", qualityRange: [18, 28] },
  "libsvtav1":   { label: "AV1 (CPU)",       recommendedQuality: 32, qualityMode: "crf", qualityRange: [20, 40] },
  "h264_nvenc":  { label: "H.264 (NVIDIA)",  recommendedQuality: 28, qualityMode: "cq",  qualityRange: [20, 36] },
  "hevc_nvenc":  { label: "H.265 (NVIDIA)",  recommendedQuality: 28, qualityMode: "cq",  qualityRange: [20, 36] },
  "av1_nvenc":   { label: "AV1 (NVIDIA)",    recommendedQuality: 36, qualityMode: "cq",  qualityRange: [24, 44] },
}
```

---

## 6. 变更影响矩阵

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/export_service.py` | BUGFIX + FEATURE | 编码器质量模式映射、pix_fmt、movflags、段提取编码器参数 |
| `main.py` | BUGFIX | preset 默认值统一为 medium |
| `frontend/src/components/export/EncodingSettings.vue` | FEATURE | 编码器推荐值、动态 CRF 范围、质量模式标签 |
| `frontend/src/pages/ExportPage.vue` | FEATURE | qualityMode 字段传递到后端 |

---

## 7. 实施优先级

| 优先级 | 编号 | 类型 | 描述 | 工作量 |
|--------|------|------|------|--------|
| P0 | E-1 | BUGFIX | 硬件编码器质量参数修正 | 0.5h |
| P0 | E-2 | BUGFIX | 添加 -pix_fmt yuv420p | 0.1h |
| P1 | E-3 | FEATURE | movflags +faststart | 0.1h |
| P1 | E-4 | BUGFIX | preset 默认值统一 | 0.1h |
| P1 | E-5 | FEATURE | 编码器切换自动调整质量值 | 0.5h |
| P2 | E-6 | FEATURE | CRF 范围动态调整 | 0.5h |
| P2 | E-7 | FEATURE | 段提取使用用户编码器 | 0.5h |

---

## 8. 参考来源

- ff-intelligent-neo `frontend/src/data/encoders.ts` -- 编码器注册表与推荐质量值
- ff-intelligent-neo `core/command_builder.py` -- 质量模式映射与 FFmpeg 命令构建
- ff-intelligent-neo `presets/default_presets.json` -- 默认预设参数 (CRF 20/22, yuv420p, medium)
- ff-intelligent-neo v2.1.0+ commits: 8ce9049, baad3e9, 50f287f, dbf192f, 015a944

---

## 附录 A: 当前代码 -- 完整引用

### A.1 export_service.py -- FFmpeg 命令构建 (行 30-142)

```python
def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    video_codec: str = "libx264",          # <-- 默认值
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    preset: str = "fast",                  # <-- 与前端 "medium" 不一致
    crf: int = 23,
    resolution: str = "original",
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    fade_duration: float = 0.0,
    fade_mode: str = "crossfade",
) -> dict:
    # ... 省略前处理 ...

    # 行 128-138: FFmpeg 命令构建 -- 所有编码器统一使用 -crf
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", media_path,
        "-filter_complex_script", filter_path,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", video_codec,
        "-preset", preset,
        "-crf", str(crf),                   # <-- E-1: NVENC/QSV/AMF 应用 -cq/-qp
        "-c:a", audio_codec,
        "-b:a", audio_bitrate,
    ]
    # 行 140-141: 分辨率缩放
    if resolution and resolution != "original":
        cmd.extend(["-vf", f"scale={resolution.replace('x', ':')}"])
    cmd.append(output_path)
    # 问题: 无 -pix_fmt (E-2), 无 -movflags (E-3)
```

### A.2 export_service.py -- 段提取函数 (行 679-706)

```python
def _extract_segment(
    ffmpeg: str,
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    has_video: bool = True,
) -> None:
    """Extract a single segment as MPEG-TS via FFmpeg re-encode."""
    duration = end - start
    base = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-avoid_negative_ts", "make_zero",
    ]
    if has_video:
        codec_args = ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
        #   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        #   E-7: 硬编码 H.264 + fast preset，无法使用用户选择的编码器
    else:
        codec_args = ["-c:a", "aac", "-vn"]
    cmd = base + codec_args + [output_path]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment extraction failed: {result.stderr[-500:]}")
```

### A.3 main.py -- 导出任务处理 (行 89-133)

```python
def _handle_export_video(self, task, cancel_event):
    """Export cut video as a background task."""
    if self._project.current is None:
        raise ValueError("No project open")
    if self._project.current.media is None:
        raise ValueError("No media in project")
    project = self._project.current
    segments_data = [s.model_dump() for s in project.transcript.segments]
    edits_data = [e.model_dump() for e in project.edits]
    media_path = project.media.path
    output_path = task.payload.get("output_path", "")
    if not output_path:
        base, ext = os.path.splitext(media_path)
        output_path = f"{base}_cut{ext}"

    # 行 105-113: 从设置文件读取编码参数
    settings = load_settings()
    video_codec = settings.get("export_video_codec", "libx264")
    audio_codec = settings.get("export_audio_codec", "aac")
    audio_bitrate = settings.get("export_audio_bitrate", "192k")
    preset = settings.get("export_preset", "fast")       # <-- E-4: 应为 "medium"
    crf = int(settings.get("export_crf", 23))
    resolution = settings.get("export_resolution", "original")
    fade_dur = float(settings.get("export_ffmpeg_fade_duration", 0.0))
    fade_mode = str(settings.get("export_ffmpeg_fade_mode", "crossfade"))

    def progress_cb(percent: float, message: str = "") -> None:
        self._task_manager._update_progress(task.id, percent, message)

    return export_video(
        media_path=media_path,
        segments=segments_data,
        edits=edits_data,
        output_path=output_path,
        media_info=project.media.model_dump() if project.media else None,
        video_codec=video_codec,
        audio_codec=audio_codec,
        audio_bitrate=audio_bitrate,
        preset=preset,
        crf=crf,
        resolution=resolution,
        progress_callback=progress_cb,
        cancel_event=cancel_event,
        fade_duration=fade_dur,
        fade_mode=fade_mode,
    )
```

### A.4 EncodingSettings.vue -- 完整前端组件 (行 1-248)

```vue
<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { call } from "@/bridge"

const emit = defineEmits<{
  "update:settings": [settings: EncodingSettings]
}>()

interface EncodingSettings {
  outputFormat: string
  quality: number
  resolution: string
  videoCodec: string
  audioCodec: string
  audioBitrate: string
  preset: string
}

const advancedMode = ref(false)

// Basic mode settings
const outputFormat = ref("mp4")
const quality = ref(23)                    // <-- CRF 默认 23，所有编码器共享同一范围 18-32
const resolution = ref("original")

// Advanced mode settings
const videoCodec = ref("libx264")
const audioCodec = ref("aac")
const audioBitrate = ref("192k")
const preset = ref("medium")              // <-- 与后端 "fast" 不一致 (E-4)

// GPU detection
const hasNvidiaGpu = ref(false)
const gpuName = ref("")
const hardwareEncoders = ref<string[]>([])

const videoCodecs = computed(() => {
  const base = [
    { value: "libx264", label: "H.264 (CPU)" },
    { value: "libx265", label: "H.265 (CPU)" },
  ]
  if (hardwareEncoders.value.includes("libsvtav1")) {
    base.push({ value: "libsvtav1", label: "AV1 (CPU, SVT-AV1)" })
  }
  if (hasNvidiaGpu.value) {
    if (hardwareEncoders.value.includes("h264_nvenc")) {
      base.push({ value: "h264_nvenc", label: "H.264 (NVIDIA GPU)" })
    }
    if (hardwareEncoders.value.includes("hevc_nvenc")) {
      base.push({ value: "hevc_nvenc", label: "H.265 (NVIDIA GPU)" })
    }
    if (hardwareEncoders.value.includes("av1_nvenc")) {
      base.push({ value: "av1_nvenc", label: "AV1 (NVIDIA GPU)" })
    }
  }
  return base
  // 问题: 无编码器推荐质量值，切换编码器后 CRF 不自动调整 (E-5)
})

const presets = [
  { value: "ultrafast", label: "Ultrafast" },
  { value: "superfast", label: "Superfast" },
  { value: "veryfast", label: "Veryfast" },
  { value: "faster", label: "Faster" },
  { value: "fast", label: "Fast" },
  { value: "medium", label: "Medium" },
  { value: "slow", label: "Slow" },
  { value: "slower", label: "Slower" },
  { value: "veryslow", label: "Veryslow" },
]

const qualityLabel = computed(() => {
  if (quality.value <= 20) return "高质量"
  if (quality.value <= 24) return "中等质量"
  if (quality.value <= 27) return "小文件"
  return "极小文件"
  // 问题: 标签对所有编码器相同，NVENC CQ 28 应显示为 "中等质量" 而非 "小文件" (E-6)
})

onMounted(async () => {
  try {
    const res = await call<{ nvidia: boolean; gpu_name: string; encoders: string[] }>("detect_gpu")
    if (res.success && res.data) {
      hasNvidiaGpu.value = res.data.nvidia
      gpuName.value = res.data.gpu_name ?? ""
      hardwareEncoders.value = res.data.encoders ?? []
    }
  } catch {
    // GPU detection failed, assume no hardware encoders
  }
})

function updateSettings() {
  emit("update:settings", {
    outputFormat: outputFormat.value,
    quality: quality.value,
    resolution: resolution.value,
    videoCodec: videoCodec.value,
    audioCodec: audioCodec.value,
    audioBitrate: audioBitrate.value,
    preset: preset.value,
  })
}
</script>

<template>
  <div class="space-y-4">
    <!-- Basic mode -->
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">输出格式</label>
      <select v-model="outputFormat" @change="updateSettings" ...>
        <option value="mp4">MP4</option>
        <option value="webm">WebM</option>
        <option value="mov">MOV</option>
      </select>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">
        质量: {{ qualityLabel }} (CRF {{ quality }})
      </label>
      <input v-model.number="quality" type="range" min="18" max="32"
             @input="updateSettings" />
      <!-- E-6: min/max 固定，不随编码器变化 -->
    </div>

    <!-- ... 分辨率选择省略 ... -->

    <!-- Advanced mode -->
    <div v-if="advancedMode" class="space-y-4 pl-4 border-l-2 border-gray-200">
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">视频编码器</label>
        <select v-model="videoCodec" @change="updateSettings" ...>
          <option v-for="codec in videoCodecs" :key="codec.value" :value="codec.value">
            {{ codec.label }}
          </option>
        </select>
        <!-- E-5: 切换编码器时不自动调整 quality 值 -->
      </div>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">编码速度</label>
        <select v-model="preset" @change="updateSettings" ...>
          <option v-for="p in presets" :key="p.value" :value="p.value">
            {{ p.label }}
          </option>
        </select>
      </div>
    </div>
  </div>
</template>
```

### A.5 ExportPage.vue -- 编码设置传递 (行 30-105)

```typescript
// 行 30-38: 编码设置默认值
const encodingSettings = ref({
  outputFormat: "mp4",
  quality: 23,
  resolution: "original",
  videoCodec: "libx264",
  audioCodec: "aac",
  audioBitrate: "192k",
  preset: "medium",
})

// 行 93-114: 导出时将设置写入后端
async function handleExportVideo() {
  errorMessage.value = ""
  statusMessage.value = "正在导出视频..."
  await call("update_settings", {
    export_video_codec: encodingSettings.value.videoCodec,
    export_audio_codec: encodingSettings.value.audioCodec,
    export_audio_bitrate: encodingSettings.value.audioBitrate,
    export_preset: encodingSettings.value.preset,
    export_crf: encodingSettings.value.quality,
    export_resolution: encodingSettings.value.resolution,
    export_ffmpeg_fade_duration: otioFadeDuration.value,
    export_ffmpeg_fade_mode: otioFadeMode.value,
    // 问题: 未传递 quality_mode (crf/cq/qp)，后端无法区分 (E-1)
  })
  const task = await createExportTask("export_video")
  // ...
}
```

---

## 附录 B: ff-intelligent-neo 参考代码

### B.1 encoders.ts -- 编码器注册表与推荐质量值

```typescript
export const VIDEO_ENCODERS: EncoderConfigDTO[] = [
  // Special (shown first)
  { name: "copy", displayName: "Copy (no re-encode)", category: "video", priority: "P0" },
  { name: "none", displayName: "No Video", category: "video", priority: "P0" },

  // P0: First choice recommendations
  { name: "av1_nvenc",  displayName: "AV1 (NVIDIA)",  recommendedQuality: 36, qualityMode: "cq",  priority: "P0" },
  { name: "libx265",    displayName: "H.265/HEVC",    recommendedQuality: 24, qualityMode: "crf", priority: "P0" },
  { name: "libsvtav1",  displayName: "SVT-AV1",       recommendedQuality: 32, qualityMode: "crf", priority: "P0" },

  // P1: Good alternatives
  { name: "libx264",    displayName: "H.264/AVC",      recommendedQuality: 23, qualityMode: "crf", priority: "P1" },
  { name: "hevc_nvenc", displayName: "HEVC (NVIDIA)",  recommendedQuality: 28, qualityMode: "cq",  priority: "P1" },
  { name: "h264_nvenc", displayName: "H.264 (NVIDIA)", recommendedQuality: 28, qualityMode: "cq",  priority: "P1" },
  { name: "av1_qsv",    displayName: "AV1 (Intel QSV)",recommendedQuality: 32, qualityMode: "qp",  priority: "P1" },
  { name: "libvpx-vp9", displayName: "VP9",            recommendedQuality: 31, qualityMode: "crf", priority: "P1" },

  // P2: Hardware-specific (conditional)
  { name: "h264_amf",   displayName: "H.264 (AMD)",    recommendedQuality: 34, qualityMode: "qp",  priority: "P2" },
  { name: "hevc_amf",   displayName: "HEVC (AMD)",     recommendedQuality: 32, qualityMode: "qp",  priority: "P2" },
  { name: "h264_qsv",   displayName: "H.264 (Intel)",  recommendedQuality: 28, qualityMode: "qp",  priority: "P2" },
  { name: "hevc_qsv",   displayName: "HEVC (Intel)",   recommendedQuality: 30, qualityMode: "qp",  priority: "P2" },

  // Apple (macOS only)
  { name: "h264_videotoolbox", displayName: "H.264 (Apple)", recommendedQuality: 65, qualityMode: "q", priority: "P1" },
  { name: "hevc_videotoolbox", displayName: "HEVC (Apple)",  recommendedQuality: 65, qualityMode: "q", priority: "P1" },
]
```

### B.2 command_builder.py -- 质量模式映射与验证

```python
# 行 48-55: 有效编码器集合
VALID_VIDEO_CODECS = {
    "libx264", "libx265", "libsvtav1", "libvpx-vp9",
    "av1_nvenc", "hevc_nvenc", "h264_nvenc",
    "h264_amf", "hevc_amf", "h264_qsv", "hevc_qsv", "av1_qsv",
    "h264_videotoolbox", "hevc_videotoolbox",
    "copy", "none",
}

# 行 61-63: 有效值集合
VALID_PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
VALID_PIXEL_FORMATS = {"yuv420p", "yuv420p10le", "yuv422p", "yuv444p"}
VALID_QUALITY_MODES = {"crf", "cq", "qp", "q"}

# 行 266: 质量模式 -> FFmpeg 标志映射
_QUALITY_FLAG_MAP = {
    "crf": "-crf",    # libx264, libx265, libsvtav1, libvpx-vp9
    "cq":  "-cq",     # av1_nvenc, hevc_nvenc, h264_nvenc
    "qp":  "-qp",     # h264_qsv, hevc_qsv, av1_qsv, h264_amf, hevc_amf
    "q":   "-q:v",    # h264_videotoolbox, hevc_videotoolbox (macOS)
}

# 行 277-285: 质量值范围验证
# crf/cq/qp: 0-51
# q (VideoToolbox): 0-100
```

### B.3 default_presets.json -- 默认预设参数 (关键字段)

```json
[
  {
    "id": "mp4-h264",
    "config": {
      "transcode": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "quality_mode": "crf",
        "quality_value": 20,
        "preset": "medium",
        "pixel_format": "yuv420p"
      }
    }
  },
  {
    "id": "mp4-h265",
    "config": {
      "transcode": {
        "video_codec": "libx265",
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "quality_mode": "crf",
        "quality_value": 22,
        "preset": "medium",
        "pixel_format": "yuv420p"
      }
    }
  },
  {
    "id": "720p-h264",
    "config": {
      "transcode": {
        "video_codec": "libx264",
        "audio_codec": "aac",
        "audio_bitrate": "128k",
        "resolution": "1280x720",
        "quality_mode": "crf",
        "quality_value": 20,
        "preset": "medium",
        "pixel_format": "yuv420p"
      }
    }
  }
]
```

---

## 附录 C: 改动后代码示例

### C.1 export_service.py -- 编码器配置映射 (新增)

```python
# 编码器质量模式映射 (E-1)
ENCODER_QUALITY_MODE: dict[str, str] = {
    "libx264": "crf", "libx265": "crf", "libsvtav1": "crf", "libvpx-vp9": "crf",
    "h264_nvenc": "cq", "hevc_nvenc": "cq", "av1_nvenc": "cq",
    "h264_qsv": "qp", "hevc_qsv": "qp", "av1_qsv": "qp",
    "h264_amf": "qp", "hevc_amf": "qp",
}

ENCODER_RECOMMENDED_QUALITY: dict[str, int] = {
    "libx264": 23, "libx265": 24, "libsvtav1": 32, "libvpx-vp9": 31,
    "h264_nvenc": 28, "hevc_nvenc": 28, "av1_nvenc": 36,
    "h264_qsv": 28, "hevc_qsv": 30, "av1_qsv": 32,
    "h264_amf": 34, "hevc_amf": 32,
}

QUALITY_FLAG_MAP: dict[str, str] = {
    "crf": "-crf", "cq": "-cq", "qp": "-qp", "q": "-q:v",
}
```

### C.2 export_service.py -- export_video 命令构建 (修改)

```python
def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    preset: str = "medium",               # <-- E-4: 统一为 medium
    crf: int = 23,
    resolution: str = "original",
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    fade_duration: float = 0.0,
    fade_mode: str = "crossfade",
) -> dict:
    # ... 省略前处理 ...

    # E-1: 根据编码器选择正确的质量参数
    quality_mode = ENCODER_QUALITY_MODE.get(video_codec, "crf")
    quality_flag = QUALITY_FLAG_MAP[quality_mode]

    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", media_path,
        "-filter_complex_script", filter_path,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", video_codec,
        "-preset", preset,
        quality_flag, str(crf),            # <-- E-1: 动态质量标志
        "-c:a", audio_codec,
        "-b:a", audio_bitrate,
        "-pix_fmt", "yuv420p",             # <-- E-2: 显式像素格式
    ]
    if resolution and resolution != "original":
        cmd.extend(["-vf", f"scale={resolution.replace('x', ':')}"])
    # E-3: MP4/MOV 容器添加 faststart
    if output_path.endswith((".mp4", ".mov")):
        cmd.extend(["-movflags", "+faststart"])
    cmd.append(output_path)
    # ...
```

### C.3 export_service.py -- _extract_segment (修改)

```python
def _extract_segment(
    ffmpeg: str,
    input_path: str,
    start: float,
    end: float,
    output_path: str,
    has_video: bool = True,
    video_codec: str = "libx264",          # <-- E-7: 新增参数
    preset: str = "medium",                # <-- E-7: 新增参数
    crf: int = 23,                         # <-- E-7: 新增参数
) -> None:
    """Extract a single segment as MPEG-TS via FFmpeg re-encode."""
    duration = end - start
    base = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{start:.3f}",
        "-i", input_path,
        "-t", f"{duration:.3f}",
        "-avoid_negative_ts", "make_zero",
    ]
    if has_video:
        # E-7: 使用编码器映射获取正确的质量参数
        quality_mode = ENCODER_QUALITY_MODE.get(video_codec, "crf")
        quality_flag = QUALITY_FLAG_MAP[quality_mode]
        codec_args = [
            "-c:v", video_codec,
            "-preset", preset,
            quality_flag, str(crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
        ]
    else:
        codec_args = ["-c:a", "aac", "-vn"]
    cmd = base + codec_args + [output_path]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment extraction failed: {result.stderr[-500:]}")
```

### C.4 EncodingSettings.vue -- 编码器元数据与动态调整 (修改)

```typescript
// E-5: 编码器推荐质量值映射
interface EncoderMeta {
  label: string
  recommendedQuality: number
  qualityMode: string
  qualityRange: [number, number]
}

const ENCODER_META: Record<string, EncoderMeta> = {
  "libx264":    { label: "H.264 (CPU)",     recommendedQuality: 23, qualityMode: "crf", qualityRange: [18, 28] },
  "libx265":    { label: "H.265 (CPU)",     recommendedQuality: 24, qualityMode: "crf", qualityRange: [18, 28] },
  "libsvtav1":  { label: "AV1 (CPU)",       recommendedQuality: 32, qualityMode: "crf", qualityRange: [20, 40] },
  "h264_nvenc": { label: "H.264 (NVIDIA)",  recommendedQuality: 28, qualityMode: "cq",  qualityRange: [20, 36] },
  "hevc_nvenc": { label: "H.265 (NVIDIA)",  recommendedQuality: 28, qualityMode: "cq",  qualityRange: [20, 36] },
  "av1_nvenc":  { label: "AV1 (NVIDIA)",    recommendedQuality: 36, qualityMode: "cq",  qualityRange: [24, 44] },
}

// E-5: 编码器切换时自动调整推荐质量值
watch(videoCodec, (newCodec) => {
  const meta = ENCODER_META[newCodec]
  if (meta) {
    quality.value = meta.recommendedQuality
  }
  updateSettings()
})

// E-6: CRF 滑块范围根据编码器动态调整
const qualityRange = computed(() => {
  const meta = ENCODER_META[videoCodec.value]
  if (meta) return meta.qualityRange
  return [18, 32] as [number, number]
})

const qualityModeLabel = computed(() => {
  const meta = ENCODER_META[videoCodec.value]
  if (!meta) return "CRF"
  if (meta.qualityMode === "cq") return "CQ"
  if (meta.qualityMode === "qp") return "QP"
  return "CRF"
})

// 模板中:
// <input v-model.number="quality" type="range"
//        :min="qualityRange[0]" :max="qualityRange[1]" />
// 质量: {{ qualityLabel }} ({{ qualityModeLabel }} {{ quality }})
```

### C.5 ExportPage.vue -- 传递 quality_mode (修改)

```typescript
async function handleExportVideo() {
  // ...
  await call("update_settings", {
    export_video_codec: encodingSettings.value.videoCodec,
    export_audio_codec: encodingSettings.value.audioCodec,
    export_audio_bitrate: encodingSettings.value.audioBitrate,
    export_preset: encodingSettings.value.preset,
    export_crf: encodingSettings.value.quality,
    export_resolution: encodingSettings.value.resolution,
    export_ffmpeg_fade_duration: otioFadeDuration.value,
    export_ffmpeg_fade_mode: otioFadeMode.value,
    // 不再需要传递 quality_mode，后端根据 video_codec 自动推导
  })
  // ...
}
```

---

## 附录 D: Milo-Cut 与 ff-intelligent-neo 编码器能力对比

| 能力 | Milo-Cut (当前) | ff-intelligent-neo (2.1.0+) | 差距 |
|------|----------------|---------------------------|------|
| 编码器注册表 | 无，硬编码列表 | 完整注册表含推荐值 | 需新增 |
| 质量模式映射 | 统一 -crf | crf/cq/qp/q 自动映射 | 需新增 |
| 像素格式 | 未传递 | yuv420p 默认 | 需新增 |
| movflags | 未传递 | 无 (非 Web 场景) | 需新增 (Milo-Cut 适合) |
| 推荐质量值 | 无 | 每编码器独立推荐 | 需新增 |
| 动态 CRF 范围 | 固定 18-32 | 按编码器调整 | 需新增 |
| 编码器切换联动 | 无 | 自动应用推荐值 | 需新增 |
| 段提取编码器 | 硬编码 H.264 | N/A (不同架构) | 需修改 |
| GPU 检测 | 有 (NVIDIA) | 有 (NVIDIA/AMD/Intel/Apple) | 可扩展 |
| 预设系统 | 无 | 7 个内置预设 | 可选扩展 |

---

## 附录 E: 架构师评审意见与修订

**评审日期:** 2026-05-27
**评审结论:** 审核通过，建议按以下修订意见实施

### E.1 技术架构深度分析

#### A. 编码参数映射 (E-1) -- 正确且必要

**分析:** 在 FFmpeg 中，`-crf` 是 x264/x265 的私有参数。硬件编码器（如 `h264_nvenc`）如果接收到 `-crf`，通常会回退到默认码率控制模式（通常是 VBR，质量不可控）。

**架构修订:** 引入 `QUALITY_FLAG_MAP` 是解耦的最佳实践。建议将此映射表封装在 `core/ffmpeg_presets.py` 中，作为静态配置，以便未来支持更多的编码器（如 Apple 的 `videotoolbox`）。

#### B. 像素格式强制 (E-2) -- 风险提示与优化

**分析:** 强制 `-pix_fmt yuv420p` 确实解决了 99% 的播放兼容性问题。

**风险:** 如果输入视频是 HDR 或 10bit（如 `yuv420p10le`），强制转为 `yuv420p` 会导致严重的色阶断层。

**优化方案:** 建议增加探测逻辑：如果用户未指定 HDR 导出且输入是 8bit，则强制 `yuv420p`；如果用户有高级需求，允许通过设置覆盖。

```python
# 优化后的像素格式选择逻辑
def _select_pixel_format(media_info: dict | None, user_override: str = "") -> str:
    """选择像素格式: 用户指定 > 输入探测 > 安全默认值"""
    if user_override:
        return user_override
    if media_info:
        pix_fmt = media_info.get("pix_fmt", "")
        # 10bit 输入保留原始格式，避免色阶断层
        if "10le" in pix_fmt or "10be" in pix_fmt:
            return pix_fmt
    return "yuv420p"  # 8bit 安全默认值
```

#### C. 网络流优化 (E-3) -- 硬编码默认行为

**分析:** `+faststart` 通过将 `moov` 原子移至文件头，对于 Web 端预览和云端存储至关重要。

**架构修订:** 这是一个低开销、高收益的改动，应当作为 MP4 格式的**硬编码默认行为**，无需暴露给用户。

### E.2 核心代码审计建议

#### E-7 (段提取编码器同步) -- 性能/质量陷阱警告

报告建议在 `_extract_segment` 中使用用户选择的编码器。这里存在潜在的**二次编码风险**:

1. 段提取如果是为了后续的 `filter_complex` 合并，那么在这里进行一次有损编码（如 H.264），在最后导出时又进行一次有损编码，会导致**二次质量损伤**
2. 建议方案:
   - 如果 FFmpeg 脚本支持，尽量通过 `-ss` 和 `-to` 在主导出命令中直接读取原文件
   - 如果必须先提取段，且追求速度，应使用硬件编码器，但必须设置极高的码率（或 `-qp 0` 接近无损），以保证最终合成质量

```python
# 优化方案: 段提取使用接近无损的参数
def _extract_segment(
    ffmpeg: str, input_path: str, start: float, end: float,
    output_path: str, has_video: bool = True,
    video_codec: str = "libx264",
) -> None:
    """段提取: 使用 -qp 0 (近无损) 避免二次编码质量损失"""
    quality_args = ["-c:v", video_codec, "-preset", "ultrafast"]
    if "nvenc" in video_codec:
        quality_args.extend(["-qp", "0"])       # NVENC 近无损
    elif "qsv" in video_codec or "amf" in video_codec:
        quality_args.extend(["-qp", "0"])       # QSV/AMF 近无损
    else:
        quality_args.extend(["-crf", "0"])      # x264/x265 无损
    quality_args.extend(["-pix_fmt", "yuv420p", "-c:a", "aac"])
    # ...
```

#### E-5/E-6 (前后端联动) -- 单一事实来源

**分析:** 报议在前端监听 `videoCodec` 变化。

**架构修订:** 为了保证一致性，建议后端提供一个 API `get_encoder_metadata`，返回 `ENCODER_META` 字典。

**理由:** 这样如果未来后端升级了 FFmpeg 版本或调整了推荐参数，只需改动后端代码，前端会自动适配，避免前后端逻辑重复定义。

```python
# main.py -- 新增 API
@expose
def get_encoder_metadata(self) -> dict:
    """返回编码器元数据，供前端动态调整 UI"""
    return {
        "success": True,
        "data": {
            "encoders": ENCODER_META,
            "quality_modes": QUALITY_FLAG_MAP,
        },
    }
```

```typescript
// EncodingSettings.vue -- 从后端获取元数据
onMounted(async () => {
  // ... GPU detection ...
  const metaRes = await call<Record<string, EncoderMeta>>("get_encoder_metadata")
  if (metaRes.success && metaRes.data) {
    encoderMeta.value = metaRes.data.encoders
  }
})
```

### E.3 实施优先级修订

| 优先级 | 编号 | 类型 | 描述 | 理由 |
|--------|------|------|------|------|
| **P0** | E-1 | BUGFIX | 硬件编码器质量参数修正 | 修复硬件编码失效，编码质量不可控 |
| **P0** | E-2 | BUGFIX | 像素格式探测与安全默认值 | 修复播放兼容性，HDR 输入需特殊处理 |
| **P1** | E-3 | FEATURE | movflags +faststart 硬编码 | 低开销高收益，MP4 秒开播放 |
| **P1** | E-4 | BUGFIX | preset 默认值统一 | 消除 UI 显示歧义 |
| **P2** | E-5 | FEATURE | 编码器切换自动调整质量值 | 防止用户误设无效参数 |
| **P2** | E-6 | FEATURE | CRF 范围动态调整 | UI 易用性增强 |
| **P3** | E-7 | FEATURE | 段提取编码器同步 | 需审慎处理二次编码质量衰减 |

### E.4 补充需求: FFmpeg 编码器可用性探测

**缺失项:** 报告未覆盖环境适配性。

**场景:** 用户选择了 `av1_nvenc` 但显卡驱动不支持，或 FFmpeg 版本未编译该编码器。

**方案:** 在 `export_service.py` 中增加编码器可用性检查，导出前验证编码器是否可用，不可用时自动回退并提示用户。

```python
# core/ffmpeg_presets.py -- 新增编码器可用性检查
def check_encoder_availability(ffmpeg: str, codec: str) -> bool:
    """检查 FFmpeg 是否支持指定编码器"""
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return codec in result.stdout
    except Exception:
        return False

def get_fallback_codec(ffmpeg: str, requested: str) -> str:
    """获取可用的回退编码器"""
    if check_encoder_availability(ffmpeg, requested):
        return requested
    # 回退链: 硬件编码器 -> 对应 CPU 编码器 -> libx264
    FALLBACK_CHAIN = {
        "av1_nvenc": "libsvtav1", "hevc_nvenc": "libx265", "h264_nvenc": "libx264",
        "av1_qsv": "libsvtav1", "hevc_qsv": "libx265", "h264_qsv": "libx264",
        "h264_amf": "libx264", "hevc_amf": "libx265",
        "libsvtav1": "libx264", "libx265": "libx264",
    }
    fallback = FALLBACK_CHAIN.get(requested, "libx264")
    if check_encoder_availability(ffmpeg, fallback):
        return fallback
    return "libx264"  # 最终回退
```

```python
# main.py -- 导出前检查编码器可用性
def _handle_export_video(self, task, cancel_event):
    # ...
    ffmpeg = _find_ffmpeg()
    original_codec = video_codec
    video_codec = get_fallback_codec(ffmpeg, video_codec)
    if video_codec != original_codec:
        logger.warning("Encoder {} not available, falling back to {}", original_codec, video_codec)
        # 通过事件通知前端
        self._emit("encoder:fallback", {
            "requested": original_codec,
            "fallback": video_codec,
        })
    # ...
```

### E.5 架构师签名

**审核结论:** 审核通过，建议按照修订后的方案实施。核心改动点:
1. 新增 `core/ffmpeg_presets.py` 作为编码器配置的单一事实来源
2. E-2 增加像素格式探测逻辑，避免 HDR 内容色阶断层
3. E-7 段提取使用近无损参数，避免二次编码质量损失
4. 新增编码器可用性探测与自动回退机制
5. 后端提供 `get_encoder_metadata` API，前端从后端获取编码器元数据

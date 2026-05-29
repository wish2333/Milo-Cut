# Milo-Cut v1.1.0 执行计划

> 基于审计报告 v1.1.0-rc4 + 架构师最终审查意见制定。
>
> 核心原则：先补安全，再加交互，最后固架构。

---

## 1. Sprint 划分

共 4 个 Sprint，预估总周期 5-7 周。

```
Sprint 1 (1 周)  -- 安全防护 + 技术债务清理
Sprint 2 (1.5 周) -- 核心交互补齐
Sprint 3 (1.5 周) -- Undo/Redo + 状态管理
Sprint 4 (1 周)  -- 交互打磨 + 收尾
```

---

## 2. Sprint 1：安全防护与技术债务清理（第 1 周）

> 目标：消除崩溃风险、统一版本号、接入误删防护。

### 任务 1.1：EditSummaryModal 接入导出流程

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 0.5 天 |
| 依赖 | 无 |
| 负责人 | 前端 |

**实施步骤**：

1. 在 `ExportPage.vue` 中 import `EditSummaryModal`
2. 添加 `showSummaryModal` ref 控制显隐
3. 导出按钮点击时，先调用 `getExportSummary()` 获取摘要数据
4. 若 `delete_percent > 0`，弹出 `EditSummaryModal`；否则直接执行导出
5. 弹窗 `confirm` 事件触发 `executeExport()`，`cancel` 事件关闭弹窗

**验收标准**：
- [ ] 导出时弹出删除摘要确认对话框
- [ ] 确认后才允许导出
- [ ] 取消后返回编辑页面

**架构师指导（拦截器模式）**：

```typescript
async function onExportClicked() {
  const summary = await getExportSummary()
  if (summary.delete_percent > 0) {
    showSummaryModal.value = true
  } else {
    executeExport()
  }
}
```

---

### 任务 1.2：版本号统一

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 0.5 天 |
| 依赖 | 无 |
| 负责人 | 后端 |

**实施步骤**：

1. 修改 `main.py:get_app_info()` 从 `pyproject.toml` 读取版本号，必须加打包兼容兜底：

```python
def _get_version() -> str:
    """Get app version with packaging fallback."""
    # 方法 1：importlib.metadata（开发环境 / pip install）
    try:
        from importlib.metadata import version
        return version("milo-cut")
    except Exception:
        pass
    # 方法 2：读取 pyproject.toml（PyInstaller/Nuitka 打包后兜底）
    try:
        import tomllib
        with open(Path(__file__).parent / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        pass
    # 方法 3：最终兜底
    return "unknown"

@expose
def get_app_info(self) -> dict:
    return {
        "success": True,
        "data": {
            "name": "Milo-Cut",
            "version": _get_version(),
            "python": sys.version,
            "platform": sys.platform,
        },
    }
```

2. 确认 `pyproject.toml` 和 `package.json` 版本号一致
3. 后续发版时只需更新 `pyproject.toml`，`package.json` 同步更新

**架构师修正**：`importlib.metadata` 在 PyInstaller/Nuitka 打包后可能不存在，必须加 `try-except` 兜底读取 `pyproject.toml`。

**验收标准**：
- [ ] `get_app_info()` 返回的版本与 `pyproject.toml` 一致
- [ ] main.py 无硬编码版本字符串
- [ ] PyInstaller 打包后版本读取不崩溃

---

### 任务 1.3：媒体丢失重链接

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 2-3 天 |
| 依赖 | 无 |
| 负责人 | 全栈 |

**实施步骤**：

1. **后端**：在 `project_service.py:open_project()` 中添加路径存在性校验：

```python
def open_project(self, path: str) -> dict:
    # ... 加载 project.json ...
    media_path = self._current.media.path
    if media_path and not Path(media_path).exists():
        return {"success": False, "error": "MEDIA_NOT_FOUND", "data": {"path": media_path}}
    # ... 继续正常流程 ...
```

2. **后端**：实现轻量级文件指纹（size + mtime），避免全量 SHA-256 阻塞：

```python
import hashlib
import os

def compute_media_fingerprint(path: str) -> str:
    """Lightweight fingerprint: size + mtime hash. O(1) regardless of file size."""
    stat = os.stat(path)
    raw = f"{stat.st_size}:{stat.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()

def compute_media_hash_deep(path: str) -> str:
    """Full SHA-256. Only use on relink confirmation, NOT on project open."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
```

3. **后端**：实现 `relink_media(new_path)` 方法：

```python
def relink_media(self, new_path: str) -> dict:
    """Relink media to a new path. Updates path + fingerprint."""
    if not Path(new_path).is_file():
        return {"success": False, "error": "File not found"}
    media = self._current.media.model_copy(update={
        "path": new_path,
        "media_hash": compute_media_fingerprint(new_path),
    })
    self._current = self._current.model_copy(update={"media": media})
    self.save_project()
    return {"success": True}
```

4. **前端**：新建 `RelinkMediaDialog.vue` 组件，显示丢失路径并提供文件选择器
5. **前端**：在 `open_project()` 调用中捕获 `MEDIA_NOT_FOUND` 错误，弹出重链接对话框
6. **前端**：重链接成功后重新打开项目

**架构师修正**：视频文件动辄几 GB，全量 SHA-256 在打开项目时会导致数十秒阻塞。改用 `size + mtime` 组合哈希作为弱校验（O(1)），仅在重链接确认时才计算深度 Hash。

**验收标准**：
- [ ] 打开项目时检测媒体文件存在性
- [ ] 媒体丢失时弹出重定位对话框
- [ ] 重定位后项目正常加载
- [ ] 打开项目时基于 size+mtime 计算轻量指纹（不阻塞）
- [ ] 源文件被覆盖时检测到指纹不匹配并警告
- [ ] 重链接时可选深度 SHA-256 校验

---

## 3. Sprint 2：核心交互补齐（第 2-3 周前半）

> 目标：自动保存防丢 + 字幕叠加预览 + FFmpeg 管理基础。

### 任务 2.1：项目自动保存

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 1-2 天 |
| 依赖 | 无 |
| 负责人 | 前端 |

**实施步骤**：

1. 在 `useProject.ts` 中添加 `isSaving` 锁和 debounce 逻辑：

```typescript
import { watch } from "vue"

const isSaving = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

// 监听 isDirty 变化，debounce 2000ms 后自动保存
watch(isDirty, (dirty) => {
  if (!dirty || isSaving.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    isSaving.value = true
    try {
      await saveProject()
    } finally {
      isSaving.value = false
    }
  }, 2000)
})
```

2. 确保手动保存（Ctrl+S）也经过 `isSaving` 锁
3. 关闭项目时，若 `isDirty` 为 true，先等待保存完成或提示用户

**验收标准**：
- [ ] 编辑操作后 2 秒自动保存
- [ ] 快速连续操作不会触发多次保存（isSaving 锁）
- [ ] 关闭项目时数据不丢失

**架构师指导**：debounce 2000ms，前端必须持有 isSaving 锁。

---

### 任务 2.2：字幕叠加预览

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 2 天 |
| 依赖 | 无 |
| 负责人 | 前端 |

**实施步骤**：

1. 新建 `SubtitleOverlay.vue` 组件，使用游标优化避免 O(N) 线性扫描：

```vue
<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue"
import type { Segment } from "@/types/edit"

const props = defineProps<{
  segments: Segment[]
  videoRef: HTMLVideoElement | null
}>()

const currentText = ref("")
let rafId: number | null = null
let cursor = 0  // 游标：记录当前字幕段索引，避免每次从头扫描

function findCurrentSubtitle(time: number): string {
  const segs = props.segments
  if (segs.length === 0) return ""

  // 快速路径：检查游标当前位置（99% 的帧命中此处）
  const cur = segs[cursor]
  if (cur && cur.type === "subtitle" && time >= cur.start && time <= cur.end) {
    return cur.text
  }

  // 游标失效：向前或向后搜索最近的字幕段
  // 优先检查下一个段（播放正常推进时命中）
  const next = segs[cursor + 1]
  if (next && next.type === "subtitle" && time >= next.start && time <= next.end) {
    cursor++
    return next.text
  }

  // 跳转场景：二分查找定位
  let lo = 0, hi = segs.length - 1
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1
    const s = segs[mid]
    if (s.type !== "subtitle") { lo = mid + 1; continue }
    if (time < s.start) { hi = mid - 1 }
    else if (time > s.end) { lo = mid + 1 }
    else { cursor = mid; return s.text }
  }

  cursor = Math.max(0, lo)
  return ""
}

function tick() {
  if (!props.videoRef) return
  currentText.value = findCurrentSubtitle(props.videoRef.currentTime)
  rafId = requestAnimationFrame(tick)
}

// play 时启动 rAF 循环，pause 时取消
watch(() => props.videoRef, (video) => {
  if (!video) return
  video.addEventListener("play", () => { tick() })
  video.addEventListener("pause", () => {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null }
  })
})

// 切换项目时重置游标
watch(() => props.segments, () => { cursor = 0 })

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div
    v-if="currentText"
    class="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-black/70 text-white text-sm rounded max-w-[80%] text-center"
  >
    {{ currentText }}
  </div>
</template>
```

2. 在 `WorkspacePage.vue` 的 `<video>` 外层包裹 `relative` 容器，叠加 `SubtitleOverlay`
3. 传入 `videoRef` 和当前项目的 `segments`

**验收标准**：
- [ ] 播放视频时底部显示当前字幕文本
- [ ] 字幕切换无明显延迟（rAF 高频同步）
- [ ] 暂停时字幕保持显示
- [ ] 无字幕时间段不显示叠加层

**架构师指导**：使用 `requestAnimationFrame` 而非 `@timeupdate`，确保高频同步无延迟。游标优化避免 O(N) 线性扫描。

---

### 任务 2.3：FFmpeg 管理与设置页

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 1-1.5 周 |
| 依赖 | 任务 2.4（AppSettings 同步） |
| 负责人 | 全栈 |

**实施步骤**：

**阶段一：设置页基础架构（2 天）**

1. 新建 `SettingsPage.vue` 或 `SettingsModal.vue`
2. 新建 `useSettingsPage.ts` composable 管理设置页状态
3. 在 `App.vue` 或 `WorkspacePage.vue` 中添加设置入口（齿轮图标）

**阶段二：FFmpeg 检测与路径解析（2 天）**

4. 修改 `ffmpeg_service.py` 的路径解析逻辑，优先读取 settings：

```python
def _find_ffmpeg() -> str:
    settings = get_settings()
    # 1. 用户指定路径
    if settings.get("ffmpeg_path") and Path(settings["ffmpeg_path"]).is_file():
        return settings["ffmpeg_path"]
    # 2. static_ffmpeg 包
    try:
        import static_ffmpeg
        return static_ffmpeg.utils.get_or_fetch_platform_executables_else_raise()[0]
    except Exception:
        pass
    # 3. PATH 查找
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    raise FileNotFoundError("FFmpeg not found")
```

5. 实现 6 级优先链检测（用户指定 > 打包 > 本地 > 平台路径 > PATH > static_ffmpeg）

**阶段三：跨平台 GPU 检测（1 天）**

6. 废弃 `nvidia-smi` 硬编码，改用 `ffmpeg -hwaccels` 探测：

```python
@expose
def detect_gpu(self) -> dict:
    """Detect GPU via ffmpeg -hwaccels + dummy encoding probe."""
    ffmpeg = _find_ffmpeg()
    encoders: list[str] = ["libsvtav1"]  # 软件编码器始终可用

    # 方法 1：ffmpeg -hwaccels
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=5,
        )
        hwaccels = result.stdout.strip().split("\n")[1:]  # 跳过标题行
        for hw in hwaccels:
            hw = hw.strip().lower()
            if "cuda" in hw or "nvenc" in hw:
                encoders.extend(["h264_nvenc", "hevc_nvenc", "av1_nvenc"])
            elif "qsv" in hw:
                encoders.extend(["h264_qsv", "hevc_qsv"])
            elif "videotoolbox" in hw:
                encoders.extend(["h264_videotoolbox", "hevc_videotoolbox"])
            elif "vaapi" in hw:
                encoders.extend(["h264_vaapi", "hevc_vaapi"])
            elif "amf" in hw:
                encoders.extend(["h264_amf", "hevc_amf"])
    except Exception:
        pass

    # 方法 2：Dummy 编码验证（可选，用于确认编码器真正可用）
    # ... 1 秒空编码测试 ...

    return {"success": True, "data": {"encoders": list(set(encoders))}}
```

**阶段四：FFmpeg 下载管理（1-2 天）**

7. 集成 `static_ffmpeg` 包的下载能力
8. 设置页显示当前 FFmpeg 版本、路径、可用编码器
9. 提供"一键下载"按钮

**验收标准**：
- [ ] 设置页可用，显示 FFmpeg 状态
- [ ] 6 级优先链检测正常工作
- [ ] 用户可手动指定 FFmpeg 路径
- [ ] NVIDIA/Intel/AMD/Apple 编码器均可被检测
- [ ] FFmpeg 不存在时提供一键下载

---

### 任务 2.4：AppSettings 接口同步（前置任务）

| 属性 | 内容 |
|------|------|
| 优先级 | P0 |
| 预估 | 0.5 天 |
| 依赖 | 无 |
| 负责人 | 前端 |

**实施步骤**：

1. 以 `settings.json` 的全部字段为准，更新 `frontend/src/types/edit.ts` 中的 `AppSettings` 接口：

```typescript
export interface AppSettings {
  // FFmpeg 路径
  ffmpeg_path: string
  ffprobe_path: string
  // 通用
  theme: string
  language: string
  // 静音检测
  silence_threshold_db: number
  silence_min_duration: number
  silence_margin: number
  silence_subtitle_padding: number
  trim_subtitles_on_silence_overlap: boolean
  // 分析
  filler_words: string[]
  error_trigger_words: string[]
  // 导出
  export_fade_duration: number
  export_transition_mode: string
  export_video_codec: string
  export_audio_codec: string
  export_audio_bitrate: string
  export_preset: string
  export_crf: number
  export_resolution: string
  export_ffmpeg_transitions: boolean
  export_ffmpeg_fade_duration: number
  export_ffmpeg_fade_mode: string
}
```

2. 后续设置页开发时，所有字段均可通过 `useSettings()` 读写

**验收标准**：
- [ ] `AppSettings` 接口与 `settings.json` 字段完全一致
- [ ] 现有功能（导出设置、静音检测配置）不受影响

---

## 4. Sprint 3：Undo/Redo 与状态管理（第 3-4 周）

> 目标：实现操作历史栈，为后续状态管理评估打基础。

### 任务 3.1：撤销/重做（Undo/Redo）

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 1-2 周 |
| 依赖 | 任务 2.1（自动保存） |
| 负责人 | 全栈 |

**实施步骤**：

1. **前端**：新建 `useUndoRedo.ts` composable，含动态内存保护：

```typescript
import { ref, computed } from "vue"
import type { Project } from "@/types/edit"

const DEFAULT_MAX_HISTORY = 50
const LARGE_SNAPSHOT_THRESHOLD = 2 * 1024 * 1024  // 2MB
const REDUCED_MAX_HISTORY = 10

const undoStack = ref<string[]>([])  // 存储 JSON 字符串，避免引用共享
const redoStack = ref<string[]>([])

function getEffectiveMaxHistory(): number {
  // 动态调整：如果单次快照超过 2MB，降低历史步数防止内存溢出
  if (undoStack.value.length > 0) {
    const lastSize = undoStack.value[undoStack.value.length - 1].length
    if (lastSize > LARGE_SNAPSHOT_THRESHOLD) {
      return REDUCED_MAX_HISTORY
    }
  }
  return DEFAULT_MAX_HISTORY
}

function pushSnapshot(project: Project) {
  const serialized = JSON.stringify(project)
  undoStack.value.push(serialized)
  const maxHistory = getEffectiveMaxHistory()
  while (undoStack.value.length > maxHistory) {
    undoStack.value.shift()
  }
  redoStack.value = [] // 新操作清空 redo 栈
}

function undo(currentProject: Project): Project | null {
  if (undoStack.value.length === 0) return null
  redoStack.value.push(JSON.stringify(currentProject))
  return JSON.parse(undoStack.value.pop()!)
}

function redo(currentProject: Project): Project | null {
  if (redoStack.value.length === 0) return null
  undoStack.value.push(JSON.stringify(currentProject))
  return JSON.parse(redoStack.value.pop()!)
}

export function useUndoRedo() {
  return {
    undoStack,
    redoStack,
    pushSnapshot,
    undo,
    redo,
    canUndo: computed(() => undoStack.value.length > 0),
    canRedo: computed(() => redoStack.value.length > 0),
  }
}
```

2. 在所有编辑操作（合并/拆分/标记/文本编辑/时间戳修改）前调用 `pushSnapshot()`
3. 注册全局快捷键 Ctrl+Z / Ctrl+Y

**架构师修正**：大型项目（2 小时视频、数万 Segment）单次快照可达数 MB，50 步历史可能消耗数百 MB 前端内存。增加动态保护：快照超过 2MB 时自动将 MAX_HISTORY 从 50 降至 10。

**验收标准**：
- [ ] Ctrl+Z 可撤销最近操作
- [ ] Ctrl+Y 可重做
- [ ] 合并/拆分/标记/文本编辑均可撤销
- [ ] 最大历史步数 50，超出后丢弃最早快照
- [ ] 新操作后清空 redo 栈
- [ ] 大项目快照超 2MB 时自动降低历史步数，防止内存溢出

---

### 任务 3.2：前端状态管理评估（Pinia）

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 2-3 天评估 + 实施 |
| 依赖 | 任务 3.1（Undo/Redo 完成后） |
| 负责人 | 前端 |

**实施步骤**：

1. 评估 Undo/Redo 实现后的 composable 架构复杂度
2. 若 composables 间状态耦合明显，制定 Pinia 迁移计划
3. 若架构合理（当前预期），记录评估结论即可

**验收标准**：
- [ ] 输出评估文档：是否需要 Pinia，理由
- [ ] 如需迁移，制定分阶段迁移计划

---

## 5. Sprint 4：交互打磨与收尾（第 5 周）

> 目标：P2 交互细节 + 测试覆盖 + 文档更新。

### 任务 4.1：交叉验证高亮

| 属性 | 内容 |
|------|------|
| 优先级 | P2 |
| 预估 | 1-2 天 |
| 依赖 | 无 |

静音段选中时高亮前后相邻字幕段。

---

### 任务 4.2：TranscriptRow/SilenceRow 右键菜单

| 属性 | 内容 |
|------|------|
| 优先级 | P2 |
| 预估 | 2-3 天 |
| 依赖 | 无 |

段落右键菜单：标记删除/保留、合并、拆分、跳转到时间。参考 `SegmentBlocksLayer.vue` 现有右键菜单实现。

---

### 任务 4.3：VTT 导出

| 属性 | 内容 |
|------|------|
| 优先级 | P2 |
| 预估 | 1-2 天 |
| 依赖 | 无 |

Web 字幕格式支持，参考现有 `export_srt()` 实现。

---

### 任务 4.4：测试覆盖与文档更新

| 属性 | 内容 |
|------|------|
| 优先级 | P1 |
| 预估 | 2-3 天 |
| 依赖 | 所有功能完成 |

1. 为新增功能编写单元测试（自动保存、Undo/Redo、媒体重链接）
2. 更新 `docs/frontend-guide.md` 和 `docs/backend-guide.md`
3. 更新 `tests/TEST_GUIDE.md` 添加新功能的手动测试流程
4. 确保测试覆盖率 >= 80%

---

## 6. 任务依赖关系

```
1.1 EditSummaryModal  ─────────────────────────────────────────> (独立)
1.2 版本号统一        ─────────────────────────────────────────> (独立)
1.3 媒体重链接        ─────────────────────────────────────────> (独立)

2.4 AppSettings 同步  ──> 2.3 FFmpeg 管理与设置页 ─────────────> (依赖)
2.1 自动保存          ──> 3.1 Undo/Redo ──> 3.2 Pinia 评估 ──> (依赖链)
2.2 字幕叠加          ─────────────────────────────────────────> (独立)

4.1 交叉验证高亮      ─────────────────────────────────────────> (独立)
4.2 右键菜单          ─────────────────────────────────────────> (独立)
4.3 VTT 导出          ─────────────────────────────────────────> (独立)
4.4 测试与文档        <───────────────────────────────────────── (依赖所有)
```

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| FFmpeg 下载在企业网络受限 | 设置页功能不完整 | 提供手动路径配置作为 fallback |
| Undo/Redo 内存占用过高 | 大项目卡顿 | 动态 MAX_HISTORY：快照超 2MB 时自动降至 10 步 |
| rAF 字幕同步在低端设备卡顿 | 播放不流畅 | 游标优化 O(1) 查找 + rAF 回退 timeupdate 兜底 |
| AppSettings 同步遗漏字段 | 设置页功能不全 | 以 settings.json 为 SSOT，逐字段对照 |
| 大文件 SHA-256 阻塞项目打开 | 应用假死数十秒 | 已改用 size+mtime 轻量指纹（O(1)），仅重链接时深度校验 |
| PyInstaller 打包后版本读取崩溃 | 应用启动报错 | importlib.metadata + pyproject.toml 双重兜底 |

---

## 8. 验收检查清单

### P0 验收（Sprint 1-2）

- [ ] 导出前弹出 EditSummaryModal 删除摘要确认对话框
- [ ] 编辑操作后自动保存（debounce 2000ms + isSaving 锁）
- [ ] 媒体文件移动/删除后弹出重定位对话框
- [ ] 打开项目时基于 size+mtime 计算轻量指纹（不阻塞）
- [ ] 重链接时可选深度 SHA-256 校验
- [ ] 版本号在 main.py / pyproject.toml / package.json 三处一致
- [ ] PyInstaller 打包后版本读取不崩溃
- [ ] 播放视频时底部显示当前字幕文本（rAF + 游标优化）
- [ ] 设置页可用，FFmpeg 检测/下载/版本切换功能正常
- [ ] AppSettings 接口与 settings.json 字段完全一致
- [ ] detect_gpu 支持 NVIDIA/Intel/AMD/Apple 跨平台检测

### P1 验收（Sprint 3）

- [ ] Ctrl+Z 可撤销最近操作，Ctrl+Y 可重做
- [ ] 合并/拆分/标记/文本编辑均可撤销
- [ ] 大项目快照超 2MB 时自动降低历史步数，防止内存溢出
- [ ] 前端状态管理评估文档输出

### P2 验收（Sprint 4）

- [ ] 静音段选中时高亮前后相邻字幕段
- [ ] TranscriptRow/SilenceRow 有右键菜单
- [ ] VTT 导出功能可用
- [ ] 测试覆盖率 >= 80%

---

---

## 附录：架构师技术修正记录

> 以下 4 项修正来自架构师对执行计划的技术审查，已全部消化吸收至对应任务。

### 修正 1：大文件 SHA-256 阻塞（任务 1.3）

**问题**：视频文件动辄几 GB，单线程计算 SHA-256 需数十秒，直接导致后端接口超时、前端假死。

**修正**：将 `media_hash` 从"强制完整性校验"降级为"弱校验（size + mtime 组合哈希）"，O(1) 复杂度。仅在执行重链接动作时才进行深度 SHA-256 校验。

**已更新**：任务 1.3 实施步骤、验收标准、风险表。

### 修正 2：字幕叠加 O(N) 搜索（任务 2.2）

**问题**：`findCurrentSubtitle()` 线性扫描放入 rAF（60fps），2000 个字幕段 = 每秒 12 万次循环，严重消耗主线程。

**修正**：引入游标（Cursor）状态，优先检查当前位置（99% 帧命中），失效时使用二分查找定位。

**已更新**：任务 2.2 代码示例、验收标准、风险表。

### 修正 3：Undo/Redo 内存泄漏（任务 3.1）

**问题**：2 小时视频的 Project 快照可达数 MB，50 步历史可能消耗数百 MB 前端内存。

**修正**：增加动态保护机制——`pushSnapshot` 时评估序列化大小，超过 2MB 阈值自动将 MAX_HISTORY 从 50 降至 10。

**已更新**：任务 3.1 代码示例、验收标准、风险表。

### 修正 4：importlib.metadata 打包兼容（任务 1.2）

**问题**：PyInstaller/Nuitka 打包后环境中无 `milo-cut` 包的 metadata，`version()` 会抛出 `PackageNotFoundError`。

**修正**：`_get_version()` 函数增加三层兜底：importlib.metadata -> pyproject.toml 读取 -> "unknown"。

**已更新**：任务 1.2 代码示例、验收标准。

---

*制定人：代码执行负责人*
*审核人：架构师*
*制定日期：2026-05-27*
*版本：v1.1（含架构师 4 项技术修正）*

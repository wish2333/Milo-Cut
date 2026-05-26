# Milo-Cut 实施计划 -- 审计报告 0.2.0-1

**基于:** `docs/audit-report-0.2.0-1.md`
**日期:** 2026-05-16
**范围:** I-1, I-2, I-3, C1
**实施顺序:** I-1 -> I-3 -> I-2 -> C1

---

## I-1 [MEDIUM] Analysis 按钮位置调整到 SubtitleTrim 右侧

### 目标

将 Analysis 下拉按钮从当前位置（Detect Silence 删除按钮和 SubtitleTrim 之间）移动到 SubtitleTrim 删除按钮右侧，并增加静音组与字幕组之间的视觉分隔线。

### 涉及文件

- `frontend/src/pages/WorkspacePage.vue` -- 工具栏按钮布局

### 布局变更

**当前布局:**
```
[Import SRT] [Detect Silence + Settings] [Delete Silence] [Analysis] [SubtitleTrim + Settings] [Clear SubtitleTrim] | [Export...]
```

**目标布局:**
```
[Import SRT] [Detect Silence + Settings] [Delete Silence] | [SubtitleTrim + Settings] [Clear SubtitleTrim] [Analysis] | [Export...]
```

### Step 1: 插入静音组分隔线 (WorkspacePage.vue)

在 "Delete all silence markers" 按钮（第520行附近）的 `</button>` 之后，Analysis 按钮 `<div class="relative">` 之前，插入:

```html
<!-- 分隔线: 静音组 | 字幕组 -->
<div class="h-6 w-px bg-gray-300"></div>
```

### Step 2: 移动 Analysis 按钮块

将 Analysis 下拉按钮的完整 `<div class="relative">` 块（包含按钮和下拉菜单，约第536-568行）从当前位置（Delete Silence 按钮之后）**剪切**到 SubtitleTrim 删除按钮（Clear SubtitleTrim）的 `</button>` 之后。

移动后的顺序应为:
1. SubtitleTrim + Settings (split button)
2. Clear SubtitleTrim (垃圾桶按钮)
3. **Analysis 下拉按钮** (从上方移入)

### Step 3: 验证下拉菜单行为

移动后需验证:
- `showAnalysisDropdown` 的下拉方向不会被 Export 按钮遮挡（下拉菜单使用 `absolute` 定位，从按钮底部展开）
- z-index 层叠正常（下拉菜单 z-index 应 >= 30）
- `v-click-outside` 或 `@blur` 关闭逻辑不受分隔线影响

### I-1 测试计划

1. **手动测试**: 验证工具栏布局为新顺序
2. **手动测试**: 点击 Analysis 下拉菜单，验证下拉方向和 z-index 正常
3. **手动测试**: 验证静音组和字幕组之间显示分隔线
4. **手动测试**: 验证 Analysis 各选项（检测填充词/口误触发/全量分析）功能不受影响

---

## I-3 [MEDIUM] 首页拖拽支持 project.json 打开项目

### 目标

在 App.vue 的窗口级拖拽处理中增加对 `project.json` 文件的识别和打开逻辑，并在后端 `open_project` 中增加媒体路径可达性警告。

### 涉及文件

- `frontend/src/App.vue` -- `handleWindowDrop` 函数
- `frontend/src/App.vue` -- 拖拽覆盖层文本
- `core/project_service.py` -- `open_project` 方法

### Step 1: 修改 `handleWindowDrop` (App.vue:56-85)

**在 `for (const path of paths)` 循环的 `if/else if` 链中，在 media 判断之前插入 project.json 判断:**

```typescript
for (const path of paths) {
  const ext = path.split(".").pop()?.toLowerCase() ?? ""
  const filename = path.split(/[/\\]/).pop() ?? ""
  const mediaExtensions = ["mp4", "mkv", "avi", "mov", "webm", "mp3", "wav", "aac", "flac", "ogg", "m4a"]

  // 新增: project.json 文件拖入 -> 打开已有项目
  if (filename === "project.json" && !project.value) {
    const openRes = await call<Project>("open_project", path)
    if (openRes.success && openRes.data) {
      project.value = openRes.data
      // 如果有媒体不可达警告，显示给用户
      if (openRes.warnings && openRes.warnings.length > 0) {
        // TODO: 使用 toast/notification 组件展示警告
        console.warn("Project opened with warnings:", openRes.warnings)
      }
      break  // 成功打开项目后立即跳出，避免多文件状态竞争
    }
  } else if (mediaExtensions.includes(ext) && !project.value) {
    // 无项目时: 导入媒体文件创建新项目
    const probeRes = await call<MediaInfo>("probe_media", path)
    if (!probeRes.success || !probeRes.data) continue
    const name = path.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
    const createRes = await call<Project>("create_project", name, path)
    if (createRes.success && createRes.data) {
      project.value = createRes.data
      triggerWaveformGeneration()
      break  // 创建项目后也跳出
    }
  } else if (ext === "srt" && project.value) {
    // 有项目时: 导入 SRT 字幕
    await call("import_srt", path)
  }
}
```

**关键改动说明:**
- `project.json` 判断基于 **filename**（不是 ext），因为 `.json` 扩展名太通用
- `project.json` 判断必须在 media 判断之前，避免被通用扩展名匹配拦截
- 成功操作后添加 `break`，防止多文件同时拖入时触发多次状态变更

### Step 2: 更新拖拽覆盖层文本 (App.vue:97-109)

**无项目时的提示文本:**

```html
<template v-if="!project">
  <p class="text-lg font-medium text-blue-700">松开以导入媒体文件或打开项目</p>
  <p class="text-sm text-blue-500 mt-1">支持视频、音频、project.json</p>
</template>
```

### Step 3: 后端 `open_project` 添加媒体路径警告 (project_service.py:71-88)

**在 `open_project` 中 project 加载成功后，返回结果之前插入:**

```python
# 媒体路径可达性检查
warnings = []
if project.media and project.media.path:
    if not Path(project.media.path).exists():
        warnings.append(f"Media file not found: {project.media.path}")

result = {"success": True, "data": project.model_dump()}
if warnings:
    result["warnings"] = warnings
return result
```

**注意:** 路径可达性检查不阻塞项目打开（warning 而非 error），允许用户只读查看项目元数据。

### I-3 测试计划

1. **手动测试**: 从文件管理器拖入 `project.json`，验证项目正确打开并进入 WorkspacePage
2. **手动测试**: 拖入媒体文件（无 project.json），验证仍正常创建新项目
3. **手动测试**: 同时拖入多个文件（含 project.json），验证只打开第一个 project.json
4. **手动测试**: 拖入媒体文件路径不存在但 project.json 存在的项目，验证打开后控制台显示警告
5. **手动测试**: 有项目时拖入 SRT 文件，验证仍正常导入字幕

---

## I-2 [HIGH] DetectSilence 单独删除静音段 + EditDecision 数据模型修复

### 目标

实现静音段的单独确认/拒绝/删除功能，修复 EditDecision 的 `target_id` 数据模型缺陷，消除 `delete_segment` 的孤儿 EditDecision 问题。

本项修改覆盖 5 层: 数据模型 -> 后端 API -> 前端事件链 -> UI 组件 -> SuggestionPanel。

### 涉及文件

| 层 | 文件 | 改动 |
|----|------|------|
| 5-数据模型 | `core/models.py` | EditDecision 添加 model_validator |
| 5-后端 | `core/project_service.py` | 静音 EditDecision 绑定 target_id |
| 4-事件转发 | `frontend/src/components/workspace/Timeline.vue` | SilenceRow 事件绑定 |
| 3-UI组件 | `frontend/src/components/workspace/SilenceRow.vue` | 拆分 emit + badge 布局 |
| 2-事件处理 | `frontend/src/pages/WorkspacePage.vue` | 静音段 handler |
| 1-SuggestionPanel | `frontend/src/components/workspace/SuggestionPanel.vue` | 新增静音分组 |

### 实施子顺序

数据模型修复 (Step 1-2) -> SilenceRow UI (Step 3) -> Timeline 事件转发 (Step 4) -> WorkspacePage 处理 (Step 5) -> SuggestionPanel 静音组 (Step 6)

### Step 1: EditDecision 模型约束 (core/models.py)

**在 `EditDecision` 类中添加 model_validator:**

```python
from pydantic import model_validator

class EditDecision(BaseModel):
    # ... 现有字段 ...

    @model_validator(mode='after')
    def validate_target(self) -> 'EditDecision':
        if self.target_type == 'segment' and self.target_id is None:
            raise ValueError('target_id is required when target_type is "segment"')
        return self
```

**注意:** 此约束添加后，现有的静音 EditDecision（`target_type="range"`, `target_id=None`）不受影响，因为约束仅在 `target_type="segment"` 时生效。Step 2 将静音 EditDecision 改为 `target_type="segment"` + `target_id=segment.id`。

### Step 2: 静音 EditDecision 绑定 target_id (core/project_service.py:257-282)

**修改静音检测中 EditDecision 的创建逻辑:**

```python
sil_segment = Segment(
    id=f"sil-{sil_idx:04d}",
    type=SegmentType.SILENCE,
    start=silence["start"],
    end=silence["end"],
    text="",
)

sil_edit = EditDecision(
    id=f"siledit-{sil_idx:04d}",
    start=silence["start"],
    end=silence["end"],
    action="delete",
    source="silence_detection",
    status=EditStatus.PENDING,
    priority=100,
    target_type="segment",          # 改: "range" -> "segment"
    target_id=sil_segment.id,       # 改: None -> sil_segment.id
)
```

**同时更新 `delete_silence_segments` (project_service.py:457-480):**

```python
def delete_silence_segments(self) -> dict:
    if not self._current:
        return {"success": False, "error": "No project open"}

    silence_ids = {
        s.id for s in self._current.transcript.segments
        if s.type == SegmentType.SILENCE
    }

    remaining_segments = [
        s for s in self._current.transcript.segments
        if s.type != SegmentType.SILENCE
    ]

    # 统一按 target_id 过滤（静音 EditDecision 已绑定 segment.id）
    remaining_edits = [
        e for e in self._current.edits
        if e.target_id not in silence_ids
    ]

    self._current.transcript.segments = remaining_segments
    self._current.edits = remaining_edits
    self._mark_dirty()
    return {"success": True}
```

**迁移注意:** 已有项目中静音 EditDecision 的 `target_id` 为 None 且 `target_type="range"`。需添加迁移逻辑:

```python
# 在 detect_silence 方法的 EditDecision 创建循环中
# 无需额外迁移：detect_silence 每次重新检测会覆盖旧的静音段和 EditDecision
# 但需确认 load_project / open_project 对旧格式数据的兼容性
```

对于已有项目文件的兼容性，在 `open_project` 加载后添加一次性迁移:

```python
def _migrate_silence_edits(self) -> None:
    """将旧格式静音 EditDecision 的 target_type 改为 segment 并绑定 target_id。"""
    if not self._current:
        return

    silence_map = {
        s.id: s for s in self._current.transcript.segments
        if s.type == SegmentType.SILENCE
    }

    migrated = []
    for edit in self._current.edits:
        if (edit.source == "silence_detection"
                and edit.target_type == "range"
                and edit.target_id is None):
            # 尝试通过时间范围匹配到 segment
            matched = next(
                (s for s in silence_map.values()
                 if abs(s.start - edit.start) < 0.05 and abs(s.end - edit.end) < 0.05),
                None,
            )
            if matched:
                migrated.append(edit.model_copy(update={
                    "target_type": "segment",
                    "target_id": matched.id,
                }))
            else:
                migrated.append(edit)  # 无法匹配则保留原样
        else:
            migrated.append(edit)

    self._current.edits = migrated
```

在 `open_project` 中 `self._current = project` 之后调用 `self._migrate_silence_edits()`。

### Step 3: SilenceRow.vue 拆分 emit + 对齐 badge 布局

#### 3a. 修改 emit 定义

**当前 (SilenceRow.vue:12-16):**
```typescript
const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
}>()
```

**替换为:**
```typescript
const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
  "confirm-edit": []
  "reject-edit": []
  "delete": []
}>()
```

#### 3b. 替换 badge 区域

**当前 (SilenceRow.vue:99-113) -- 单一 toggle badge:**

替换为与 TranscriptRow 对齐的三态 badge 布局:

```html
<div class="flex items-center gap-1 shrink-0">
  <template v-if="displayStatus === 'pending'">
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
  <template v-else-if="displayStatus === 'confirmed'">
    <span
      class="text-xs px-1.5 py-0.5 rounded bg-red-100 text-red-700 cursor-pointer hover:bg-red-200 transition-colors"
      title="Click to toggle status"
      @click.stop="emit('toggle-status')"
    >
      已删除
    </span>
  </template>
  <template v-else-if="displayStatus === 'rejected'">
    <span
      class="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 cursor-pointer hover:bg-green-200 transition-colors"
      title="Click to toggle status"
      @click.stop="emit('toggle-status')"
    >
      已保留
    </span>
  </template>
  <template v-else>
    <span
      class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 cursor-pointer hover:bg-gray-200 transition-colors"
      title="Click to mark for deletion"
      @click.stop="emit('toggle-status')"
    >
      无标注
    </span>
  </template>
  <!-- 独立删除按钮: 始终显示 -->
  <button
    class="text-xs px-1 py-0.5 rounded text-red-400 hover:bg-red-50 hover:text-red-600 transition-colors"
    title="Delete this silence segment"
    @click.stop="emit('delete')"
  >
    <TrashIcon class="w-3 h-3" />
  </button>
</div>
```

**需要在 `<script setup>` 中导入 TrashIcon:**
```typescript
import { TrashIcon } from "@heroicons/vue/24/outline"
```

### Step 4: Timeline.vue 转发静音段事件

**当前 SilenceRow 绑定 (Timeline.vue:104-112):**
```html
<SilenceRow
  v-else
  :segment="seg"
  :display-status="getSegmentState(seg).displayStatus"
  :style-class="getSegmentState(seg).styleClass"
  @seek="(t) => emit('seek', t)"
  @update-time="(id, field, val) => emit('update-time', id, field, val)"
  @toggle-status="emit('toggle-status', seg)"
/>
```

**替换为:**
```html
<SilenceRow
  v-else
  :segment="seg"
  :display-status="getSegmentState(seg).displayStatus"
  :style-class="getSegmentState(seg).styleClass"
  @seek="(t) => emit('seek', t)"
  @update-time="(id, field, val) => emit('update-time', id, field, val)"
  @toggle-status="emit('toggle-status', seg)"
  @confirm-edit="emit('confirm-segment', seg)"
  @reject-edit="emit('reject-segment', seg)"
  @delete="emit('delete-segment', seg)"
/>
```

**同时在 Timeline 的 defineEmits 中添加对应事件 (如尚未定义):**

确认 Timeline 的 emit 定义包含:
```typescript
"confirm-segment": [seg: Segment]
"reject-segment": [seg: Segment]
"delete-segment": [seg: Segment]
```

### Step 5: WorkspacePage.vue 处理静音段事件

**在 Timeline 组件标签上添加事件绑定 (约第714行附近):**

```html
@confirm-segment="handleConfirmSegment"
@reject-segment="handleRejectSegment"
@delete-segment="handleDeleteSegment"
```

验证 `handleConfirmSegment`、`handleRejectSegment`、`handleDeleteSegment` 三个函数是否已支持静音段:
- `handleConfirmSegment` 和 `handleRejectSegment` 调用 `useSegmentEdit` composable 中的对应方法，这些方法通过 segment ID 查找 EditDecision，应能正确处理静音段（Step 2 修复后静音 EditDecision 已绑定 `target_id=segment.id`）
- `handleDeleteSegment` 调用后端 `delete_segment(segment_id)`，Step 2 修复后 `delete_segment` 会正确清理关联的 EditDecision

### Step 6: SuggestionPanel.vue 新增静音分组

**6a. 修改分组逻辑 (SuggestionPanel.vue:35-47):**

```typescript
const groups = computed<GroupedResult[]>(() => {
  const fillerResults = props.analysisResults.filter(r => r.type === "filler")
  const errorResults = props.analysisResults.filter(r => r.type === "error")
  const result: GroupedResult[] = []
  if (fillerResults.length > 0) {
    result.push({ type: "filler", label: "口头禅", results: fillerResults })
  }
  if (errorResults.length > 0) {
    result.push({ type: "error", label: "口误触发", results: errorResults })
  }
  // 新增: 静音检测分组
  const silenceEdits = props.edits.filter(
    e => e.source === "silence_detection" && e.status === "pending"
  )
  if (silenceEdits.length > 0) {
    result.push({ type: "silence", label: "静音检测", results: silenceEdits })
  }
  return result
})
```

**注意:** 此处需要确认 `GroupedResult` 类型是否兼容。当前 `GroupedResult.results` 是 `AnalysisResult[]` 类型，静音数据来自 `edits`（EditDecision[]）。需要扩展 `GroupedResult` 使其能容纳两种数据源。

**方案:** 定义通用展示接口:

```typescript
interface SuggestionItem {
  id: string
  start: number
  end: number
  label: string
  type: "filler" | "error" | "silence"
}

interface GroupedResult {
  type: string
  label: string
  items: SuggestionItem[]
}
```

在分组逻辑中将 `AnalysisResult` 和 `EditDecision` 统一映射为 `SuggestionItem`。

**6b. 模板中新增静音组渲染:**

```html
<!-- 静音组 -->
<template v-if="group.type === 'silence'">
  <div v-for="item in group.items" :key="item.id" class="...">
    <span class="text-xs text-gray-400 font-mono">
      {{ formatTime(item.start) }} -> {{ formatTime(item.end) }}
    </span>
    <span class="text-xs text-gray-500">--- 静音 {{ (item.end - item.start).toFixed(1) }}s ---</span>
    <div class="flex gap-1">
      <button @click="emit('confirm-edit', item.id)">删除</button>
      <button @click="emit('reject-edit', item.id)">保留</button>
    </div>
  </div>
</template>
```

### I-2 测试计划

1. **单元测试**: 创建静音 EditDecision，验证 `target_type="segment"` + `target_id` 非空
2. **单元测试**: `delete_segment(silence_id)` 后，关联的静音 EditDecision 被清理（无孤儿残留）
3. **单元测试**: `delete_silence_segments()` 后，所有静音段和关联 EditDecision 被清理
4. **集成测试**: 迁移逻辑 -- 加载旧格式项目文件（`target_type="range"`, `target_id=None`），验证迁移后 `target_id` 正确绑定
5. **手动测试**: Timeline 中点击静音段 "保留" 按钮，验证状态变为 rejected
6. **手动测试**: Timeline 中点击静音段删除按钮（垃圾桶），验证静音段从列表消失
7. **手动测试**: SuggestionPanel 中静音组显示正确，"全部确认"/"全部拒绝" 覆盖静音段
8. **手动测试**: 波形层右键删除静音段，验证无孤儿 EditDecision

---

## C1 [FEATURE] 新建导出界面

### 目标

将 WorkspacePage 的三个独立导出按钮（Export Video、Export SRT、Export Audio）合并为一个入口，跳转到新的 ExportPage 路由页面，支持编码设置、预览播放、通用时间线格式导出。

### 涉及文件

| Phase | 文件 | 改动 |
|-------|------|------|
| P1 | `frontend/src/pages/ExportPage.vue` (新建) | 导出页面主框架 |
| P1 | `frontend/src/router/index.ts` | 新增路由 |
| P1 | `frontend/src/pages/WorkspacePage.vue` | 替换导出按钮为跳转按钮 |
| P1 | `frontend/src/stores/project.ts` (新建或扩展) | Pinia store 管理全局 project 状态 |
| P2 | `frontend/src/components/export/EncodingSettings.vue` (新建) | 编码设置面板 |
| P3 | `frontend/src/components/export/PreviewPlayer.vue` (新建) | 预览播放器 |
| P4 | `core/export_timeline.py` (新建) | EDL/FCPXML 导出 |
| P4 | `main.py` | 新增时间线导出 API |

### Phase 1: 基础界面框架 + 合并导出按钮

#### P1-Step 1: 创建 Pinia store (或确认已有)

如果项目中尚未使用 Pinia store 管理 project 全局状态，需要新建:

```typescript
// frontend/src/stores/project.ts
import { defineStore } from "pinia"
import { ref, type Ref } from "vue"
import type { Project } from "@/types/project"

export const useProjectStore = defineStore("project", () => {
  const project = ref<Project | null>(null)

  function setProject(p: Project | null) {
    project.value = p
  }

  return { project, setProject }
})
```

同时修改 App.vue 中 `project` 的管理方式，使用 store 替代本地 ref。

#### P1-Step 2: 新增路由

```typescript
// frontend/src/router/index.ts
{
  path: "/export",
  name: "Export",
  component: () => import("@/pages/ExportPage.vue"),
  meta: { requiresProject: true },
}
```

#### P1-Step 3: 替换 WorkspacePage 导出按钮

将 WorkspacePage 的三个导出按钮（约第613-637行）替换为:

```html
<button
  class="... bg-green-600 hover:bg-green-700 ..."
  @click="router.push('/export')"
>
  <ArrowRightCircleIcon class="w-4 h-4" /> 导出...
</button>
```

#### P1-Step 4: 创建 ExportPage.vue 基础框架

```vue
<script setup lang="ts">
import { useProjectStore } from "@/stores/project"
import { useRouter } from "vue-router"

const store = useProjectStore()
const router = useRouter()

function goBack() {
  router.push("/")
}
</script>

<template>
  <div class="h-screen flex flex-col bg-gray-50">
    <!-- 顶部导航 -->
    <div class="flex items-center gap-3 border-b bg-white px-4 py-3">
      <button @click="goBack" class="...">返回编辑</button>
      <h1 class="text-lg font-semibold">导出</h1>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <!-- 左侧: 设置面板 -->
      <div class="w-80 border-r bg-white overflow-y-auto p-4">
        <!-- Phase 2: 编码设置 -->
        <!-- Phase 4: 时间线格式导出 -->
      </div>

      <!-- 中间: 预览播放器 -->
      <div class="flex-1 flex items-center justify-center bg-black">
        <!-- Phase 3: PreviewPlayer -->
        <p class="text-gray-400">预览区域</p>
      </div>

      <!-- 右侧: 导出操作 -->
      <div class="w-64 border-l bg-white overflow-y-auto p-4">
        <h3 class="font-medium mb-3">导出选项</h3>
        <!-- 导出视频、音频、字幕按钮 -->
      </div>
    </div>
  </div>
</template>
```

### Phase 2: 编码设置面板

#### P2-Step 1: 创建 EncodingSettings.vue

```vue
<script setup lang="ts">
import { ref, computed } from "vue"

const advancedMode = ref(false)

// 基础模式
const quality = ref(23)       // CRF 值
const resolution = ref("original")  // original / 1080p / 720p / custom
const outputFormat = ref("mp4")

// 高级模式
const videoCodec = ref("libx264")
const audioCodec = ref("aac")
const audioBitrate = ref("192k")
const preset = ref("medium")

// GPU 检测
const hasNvidiaGpu = ref(false)  // 通过后端 API 检测

const videoCodecs = computed(() => {
  const base = [
    { value: "libx264", label: "H.264 (CPU)" },
    { value: "libx265", label: "H.265 (CPU)" },
  ]
  if (hasNvidiaGpu.value) {
    base.push({ value: "av1_nvenc", label: "AV1 (NVIDIA GPU)" })
  }
  return base
})
</script>
```

**分级暴露:**
- 基础模式: 质量 slider + 分辨率选择 + 输出格式
- 高级模式 (折叠): 编码器选择 + 音频码率 + 预设速度
- `av1_nvenc` 仅在有 NVIDIA GPU 时可选

#### P2-Step 2: 后端 GPU 检测 API

```python
# main.py 新增
@expose
def detect_gpu(self) -> dict:
    """检测 NVIDIA GPU 是否可用。"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        return {"success": True, "data": {"nvidia": result.returncode == 0}}
    except FileNotFoundError:
        return {"success": True, "data": {"nvidia": False}}
```

#### P2-Step 3: 导出函数传递编码参数

修改 `export_video` 和 `export_audio` 的后端接口，接受编码参数:

```python
# export_service.py export_video 签名扩展
def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    video_codec: str = "libx264",
    crf: int = 23,
    preset: str = "medium",
    resolution: str | None = None,   # "1920x1080" etc.
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    progress_callback: ... = None,
    cancel_event: ... = None,
) -> dict:
```

### Phase 3: 预览播放（跳过删除区域）

#### P3-Step 1: 创建 PreviewPlayer.vue

核心逻辑:
- 使用 HTML5 `<video>` 加载 `proxy_path`（优先）或原始媒体
- 监听 `timeupdate`，当 `currentTime` 进入 confirmed delete 范围时 `seek` 到范围结束
- 使用 `requestAnimationFrame` 轮询替代 `timeupdate` 处理短于 250ms 的删除段

```typescript
// PreviewPlayer.vue 核心逻辑
const deleteRanges = computed(() => {
  // 从 project.edits 中提取 confirmed delete 范围
  return store.project?.edits
    .filter(e => e.status === "confirmed" && e.action === "delete")
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start) ?? []
})

function checkSkip(time: number) {
  for (const range of deleteRanges.value) {
    if (time >= range.start && time < range.end) {
      videoRef.value!.currentTime = range.end
      return true
    }
  }
  return false
}

// requestAnimationFrame 轮询替代 timeupdate
function animationLoop() {
  if (videoRef.value && !videoRef.value.paused) {
    checkSkip(videoRef.value.currentTime)
  }
  rafId = requestAnimationFrame(animationLoop)
}
```

**已知风险:** seek 精度不足时，删除段末尾可能播放几帧。需在 seek 后立即 re-check。

### Phase 4: 通用时间线格式导出

#### P4-Step 1: 创建 `core/export_timeline.py`

```python
def export_edl(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export CMX3600 EDL file."""
    ...
```

```python
def export_fcpxml(
    segments: list[dict],
    edits: list[dict],
    media_info: dict,
    output_path: str,
) -> dict:
    """Export FCPXML file."""
    ...
```

**EDL 注意事项:**
- 帧率换算: `media_info["fps"]` 将秒数转为帧号，fallback 25fps
- Reel Name: 媒体文件名（不含扩展名），截断至 8 字符
- FCM 头部: `FCM: NON-DROP FRAME`（默认）

#### P4-Step 2: 注册后端 API

```python
# main.py
@expose
def _handle_export_edl(self, output_path: str) -> dict:
    ...
```

#### P4-Step 3: ExportPage 添加时间线导出选项

在右侧导出面板添加 "导出 EDL" / "导出 FCPXML" 按钮。

### C1 测试计划

#### Phase 1 测试
1. **手动测试**: 点击 "导出..." 按钮跳转到 ExportPage
2. **手动测试**: ExportPage 点击 "返回编辑" 回到 WorkspacePage
3. **手动测试**: ExportPage 能正确读取 project 状态（字幕段、编辑等）

#### Phase 2 测试
4. **手动测试**: 编码设置面板基础模式/高级模式切换正常
5. **手动测试**: NVIDIA GPU 检测后 av1_nvenc 编码器可选/灰化
6. **集成测试**: 使用自定义编码参数导出视频，验证输出文件编码正确

#### Phase 3 测试
7. **手动测试**: 预览播放跳过 confirmed delete 区域
8. **手动测试**: 短删除段（<250ms）也能正确跳过
9. **手动测试**: 使用 proxy_path 预览时性能流畅

#### Phase 4 测试
10. **单元测试**: EDL 导出的帧率换算正确
11. **单元测试**: FCPXML 导出的 XML 格式有效
12. **集成测试**: DaVinci Resolve / Premiere Pro 能成功导入 EDL 和 FCPXML

---

## 实施顺序总结

| 顺序 | ID | 严重度 | 预计改动文件数 | 理由 |
|------|-----|--------|---------------|------|
| 1 | **I-1** | MEDIUM | 1 (WorkspacePage.vue) | 最小改动，独立，快速完成 |
| 2 | **I-3** | MEDIUM | 2 (App.vue, project_service.py) | 独立小改动，不影响其他功能 |
| 3 | **I-2** | HIGH | 6 (models.py, project_service.py, SilenceRow.vue, Timeline.vue, WorkspacePage.vue, SuggestionPanel.vue) | 核心数据模型修复 + UI 完善，改动量大但逻辑自洽 |
| 4 | **C1** | FEATURE | 5+ (新建多个文件) | 大型特性，依赖 I-2 修复后的 EditDecision 模型，分 4 个 Phase 迭代 |

### 依赖关系

```
I-1 (独立)
I-3 (独立)
I-2 (独立，但 C1 的 Phase 3 预览播放依赖 I-2 修复后的 EditDecision 状态)
C1-P1 -> C1-P2 -> C1-P3 -> C1-P4 (顺序依赖)
```

### Commit 策略

| Commit | 范围 | 消息 |
|--------|------|------|
| 1 | I-1 | `fix(ui): 调整 Analysis 按钮位置到 SubtitleTrim 右侧并增加分组分隔线` |
| 2 | I-3 | `feat(ui): 支持拖入 project.json 打开项目并增加媒体路径警告` |
| 3 | I-2 Step 1-2 | `fix(backend): 修复静音 EditDecision target_id 模型缺陷并统一删除逻辑` |
| 4 | I-2 Step 3-5 | `feat(ui): SilenceRow 支持 confirm/reject/delete 操作对齐 TranscriptRow` |
| 5 | I-2 Step 6 | `feat(ui): SuggestionPanel 新增静音检测分组` |
| 6 | C1-P1 | `feat(export): 新建 ExportPage 并合并导出按钮入口` |
| 7 | C1-P2 | `feat(export): 编码设置面板（分级暴露 + GPU 检测）` |
| 8 | C1-P3 | `feat(export): 预览播放器（跳过删除区域）` |
| 9 | C1-P4 | `feat(export): 通用时间线格式导出（EDL + FCPXML）` |

## 回滚方案

I-1 和 I-3 为独立小改动，可通过 `git revert` 独立回滚。

I-2 的 Step 1-2（数据模型修复）与 Step 3-6（UI）分为两个 commit，可分别回滚。注意回滚 Step 1-2 后需确认旧项目文件的兼容性。

C1 各 Phase 按顺序独立回滚。P1 是基础框架，回滚 P1 将同时移除 P2-P4 的所有 UI。

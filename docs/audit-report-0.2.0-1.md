# Audit Report 0.2.0-1

**Date:** 2026-05-16
**Scope:** UI Layout / Silence Editing / Project Import
**Issues:** 3 + 1 Feature
**Reviewed by:** Architect

---

## I-1 [MEDIUM] Analysis 按钮位置不合理

### 现状

当前工具栏按钮从左到右的排列顺序为:

```
[Import SRT] [Detect Silence ⚙] [🗑 Delete Silence] [Analysis ▼] [Subtitle Trim ⚙] [🗑 Clear Subtitle Trim] | [Export...]
```

Analysis 按钮（紫色，第536-568行）位于 Detect Silence 删除按钮和 SubtitleTrim 按钮组之间，与两侧功能均无直接关联。

### 问题

- Analysis 下拉菜单（检测填充词/错误触发/全量分析）是对字幕内容的分析操作，应与 SubtitleTrim 在同一功能区域
- 用户操作流：Analysis 分析字幕 -> SubtitleTrim 基于分析结果裁剪 -> 两者应在视觉上相邻
- 当前 Analysis 和 SubtitleTrim 被 Delete Silence 按钮隔开，操作逻辑不连贯

### 建议调整

将 Analysis 按钮移到 SubtitleTrim 删除按钮右侧，并在静音组和字幕组之间增加视觉分隔线:

```
[Import SRT] [Detect Silence ⚙] [🗑 Delete Silence] | [Subtitle Trim ⚙] [🗑 Clear Subtitle Trim] [Analysis ▼] | [Export...]
```

### 实施注意事项

1. **Analysis 数据流向确认**: 需确认 Analysis 的"全量分析"选项是否也输出静音相关结论。若 Analysis 对 DetectSilence 有输入关系，则 Analysis 放在最右端与静音组在视觉上完全脱离，需在按钮 tooltip 中说明
2. **组间分隔线**: 调整后工具栏形成三个语义组（静音组 / 字幕组 / 导出组），组间应增加 `<div class="h-6 w-px bg-gray-300">` 分隔线
3. **下拉菜单关闭逻辑**: `showAnalysisDropdown` 的关闭依赖 `v-click-outside` 或 `@blur`，移动到分隔线右侧后需验证 z-index 层叠和下拉方向不会被 Export 按钮遮挡

### 涉及文件

| 文件 | 行号 | 说明 |
|------|------|------|
| `frontend/src/pages/WorkspacePage.vue` | 536-568 | Analysis 下拉按钮 |
| `frontend/src/pages/WorkspacePage.vue` | 571-616 | SubtitleTrim 按钮组 + 删除按钮 |
| `frontend/src/pages/WorkspacePage.vue` | 618 | 现有分隔线位置参考 |

---

## I-2 [HIGH] DetectSilence 无法单独删除静音段

### 现状

- DetectSilence 检测出的静音区域只能通过工具栏的红色垃圾桶按钮 **全部清除**
- 每个静音段可以切换状态（pending/confirmed/rejected），但无法单独删除某一个静音段
- 与 SubtitleTrim 不同：SubtitleTrim 可以通过调整字幕块后重新检测来间接"删除"某些段，但 DetectSilence 不具备这种能力

### 根因分析

问题存在五个层面:

**1. SilenceRow 状态 badge 仅显示 toggle，缺少确认/拒绝/删除操作按钮**

`SilenceRow.vue`（第99-113行）只有一个可点击的 status badge，点击后循环切换 confirmed/rejected:
```html
<span
  v-if="displayStatus && displayStatus !== 'none'"
  :class="{
    'bg-yellow-100 text-yellow-700': displayStatus === 'pending',
    'bg-red-100 text-red-700': displayStatus === 'confirmed',
    'bg-green-100 text-green-700': displayStatus === 'rejected',
  }"
  @click.stop="emit('toggle-status')"
>
  {{ displayStatus === "pending" ? "建议删除" : ... }}
</span>
```

对比 `TranscriptRow.vue`（第195-228行），字幕段有三个独立按钮:
- pending 状态: "建议删除" badge + "保留" 按钮 + 确认删除
- confirmed 状态: "已删除" badge + 点击可切换
- rejected 状态: "已保留" badge + 点击可切换
- 无状态: "无标注" badge

SilenceRow 缺少:
- 独立的 "保留" 按钮（pending 时）
- 独立的 "删除" 按钮
- 无状态时的 "无标注" badge（`v-if="displayStatus && displayStatus !== 'none'"` 在无状态时不显示任何 badge）

**2. Timeline 侧边栏 SuggestionPanel 不显示静音检测结果**

`Timeline.vue`（第113-119行）右侧 SuggestionPanel 的显示条件:
```html
<div v-if="edits.some(e => e.status === 'pending')" class="w-72 border-l border-gray-200 overflow-y-auto">
```
仅当有任何 pending 编辑时显示面板。但 `SuggestionPanel.vue` 的分组逻辑（第39-47行）只处理 `filler` 和 `error` 两种类型:
```typescript
const fillerResults = props.analysisResults.filter(r => r.type === "filler")
const errorResults = props.analysisResults.filter(r => r.type === "error")
```
静音检测结果不属于 `analysisResults`（它存储在 `segments` 中），因此即使面板因静音 pending 编辑而显示，也不会列出任何静音相关建议。静音段在 SuggestionPanel 中完全不可见。

**3. SilenceRow 无删除入口**

`SilenceRow.vue` 的 emit 定义（第12-16行）:
```typescript
const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
}>()
```
没有 `delete` 事件，也没有删除按钮 UI。

**4. Timeline 未为静音段转发 delete 事件**

`Timeline.vue`（第104-112行）为 SilenceRow 只绑定了三个事件:
```html
<SilenceRow
  @seek="(t) => emit('seek', t)"
  @update-time="(id, field, val) => emit('update-time', id, field, val)"
  @toggle-status="emit('toggle-status', seg)"
/>
```
没有 `@delete-segment` 事件。对比 TranscriptRow 绑定了 `@confirm-edit` 和 `@reject-edit`（第97-98行），SilenceRow 的绑定明显更少。

注: `SegmentBlocksLayer.vue`（波形编辑器，第197-215行）有右键菜单可删除任何 segment（包括静音），并通过 `@delete-segment` 事件上传。该事件链路最终由 `WorkspacePage.handleDeleteSegment` 处理，调用后端 `delete_segment()`。由于 `delete_segment()` 存在孤儿 EditDecision 问题（见第5层），**波形层的静音删除当前同样存在孤儿残留**，需一并修复。

**5. 后端 delete_segment 对静音段存在孤儿 EditDecision 问题（数据模型缺陷）**

`project_service.py` 的 `delete_segment()`（第436-455行）通过 `target_id` 删除关联的 EditDecision:
```python
remaining_edits = [e for e in self._current.edits if e.target_id != segment_id]
```
但静音段的 EditDecision 的 `target_type="range"` 且 `target_id=None`（第274-282行），因此 `delete_segment()` 不会清理静音段的 EditDecision，导致孤儿数据残留。

批量删除方法 `delete_silence_segments()`（第457-480行）正确处理了这个问题，因为它额外按 `source == "silence_detection"` 过滤。

**根因本质**: `EditDecision` 的 `target_type="range"` 与 `target_type="segment"` 两套语义被混用，且 `target_id` 在 `target_type="segment"` 时本应为必填，但模型层无约束。

### 建议方案

**方案 A: SilenceRow 完善操作按钮 + SuggestionPanel 增加静音组 + 数据模型修复**

1. **`SilenceRow.vue`**:
   - 拆分 `toggle-status` 为独立的 `confirm` / `reject` / `delete` 三个 emit，与 TranscriptRow 的事件命名体系对齐
   - WorkspacePage 可复用同一套 `handleConfirmSegment` / `handleRejectSegment` 逻辑，减少条件分支
   - 对齐 TranscriptRow 的 badge 布局: pending 时显示 "建议删除" + "保留" + "删除" 三个操作
   - 无状态时显示 "无标注" badge（当前被 `v-if` 过滤）

2. **`Timeline.vue`**: 为 SilenceRow 绑定 `@confirm` / `@reject` / `@delete` 事件并向上转发

3. **`WorkspacePage.vue`**: 处理静音段确认/拒绝/删除事件，复用字幕段的 handler

4. **`SuggestionPanel.vue`**: 新增 "silence" 分组。接口设计:
   - 静音数据来源: 复用已有的 `segments` prop，内部过滤 `type === 'silence'`
   - 静音的 confirm/reject 操作路径: 与 NLP 分析结果统一，通过 `editId` 操作（静音 EditDecision 有唯一 `id`）
   - "全部确认/全部拒绝" 按钮应覆盖静音段（SuggestionPanel 的 `pendingEdits` 已包含静音 pending 编辑）
   - 静音段展示: 时间戳 + "--- 静音 Xs ---" + confirm/reject 按钮

5. **`project_service.py` 数据模型修复（核心改动）**:
   - 修改静音 EditDecision 创建逻辑: `target_id=sil_segment.id`（绑定 segment ID）
   - `delete_segment()` 的现有逻辑直接生效，无需修改删除函数
   - `delete_silence_segments()` 也改为按 `target_id` 过滤，统一清理策略
   - 在 `EditDecision` 的 Pydantic 模型中添加 `model_validator`:
     ```python
     @model_validator(mode='after')
     def validate_target(self):
         if self.target_type == 'segment' and self.target_id is None:
             raise ValueError('target_id is required when target_type is segment')
         return self
     ```
   - **迁移注意**: 已有项目中静音 EditDecision 的 `target_id` 为 None，需添加迁移逻辑将现有静音 EditDecision 补上 `target_id`

**方案 B: 仅完善 SilenceRow 操作按钮（不含 SuggestionPanel 和数据模型修复）**

只做 1-3，不在 SuggestionPanel 中显示静音，不修改数据模型。改动量更小但修复不彻底，孤儿问题仍存在于波形层删除路径。

推荐方案 A。

### 涉及文件

| 文件 | 行号 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/SilenceRow.vue` | 12-16 | emit 定义，需拆分为 confirm/reject/delete |
| `frontend/src/components/workspace/SilenceRow.vue` | 99-113 | badge 仅 toggle，需对齐 TranscriptRow |
| `frontend/src/components/workspace/Timeline.vue` | 104-112 | SilenceRow 事件绑定，缺少 confirm/reject/delete |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 39-47 | 分组仅含 filler/error，需新增 silence 组 |
| `frontend/src/components/workspace/TranscriptRow.vue` | 195-228 | 参照: 字幕段完整的 badge 按钮布局 |
| `frontend/src/pages/WorkspacePage.vue` | 749 | 波形层 @delete-segment 也存在孤儿问题 |
| `frontend/src/pages/WorkspacePage.vue` | 762-786 | 批量删除静音段逻辑 |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 197-215 | 波形层右键删除（同样需修复） |
| `core/project_service.py` | 274-282 | 静音 EditDecision 创建，需改为 target_id=segment.id |
| `core/project_service.py` | 436-455 | delete_segment（修复后直接生效） |
| `core/project_service.py` | 457-480 | delete_silence_segments 需统一为按 target_id 过滤 |
| `core/models.py` | 91-101 | EditDecision 模型需添加 model_validator |

---

## I-3 [MEDIUM] 首页不支持拖入 project.json 打开项目

### 现状

当前 App.vue 的窗口级拖拽处理（第56-85行）仅支持两种文件类型:
1. **媒体文件**（无项目时）: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.m4a` -> 创建新项目
2. **SRT 文件**（有项目时）: `.srt` -> 导入字幕

不支持:
- 拖入 `project.json` 文件直接打开已有项目
- 拖入包含 `project.json` 的文件夹来打开项目

WelcomePage 的最近项目列表（第103-122行）可以点击打开已有项目，但这只显示 `data/projects/` 目录下的项目。如果用户的项目文件在别处（如移动硬盘、其他目录），只能通过最近列表访问。

### 当前拖拽流程

```
App.vue handleWindowDrop():
  get_dropped_files() -> 获取文件路径列表
  for path in paths:
    ext = path extension
    if ext in media_extensions and !project:
      -> probe_media -> create_project -> 显示 WorkspacePage
    elif ext == ".srt" and project:
      -> import_srt
    else:
      -> 忽略（静默）
```

### 建议方案

#### Phase 1: project.json 文件拖放（确定可行）

在 `handleWindowDrop` 中增加对 `project.json` 文件的处理:

```
if ext === "json" && filename === "project.json" && !project:
  -> call open_project(path)
  -> break  // 成功后立即跳出循环，避免多文件状态竞争
```

后端 `open_project`（`project_service.py` 第71-88行）已支持从任意路径打开项目文件，无需后端修改。

#### Phase 2: 文件夹拖放（需单独验证平台兼容性）

文件夹拖放在当前 bridge 架构下**实现复杂度显著高于初步估计**:
- `bridge.py` 的 `_on_drop` 使用 `dataTransfer.files` + `pywebviewFullPath`，标准 `files` 列表**不包含文件夹**
- 文件夹拖放需要 `DataTransferItem.webkitGetAsEntry()` 遍历目录条目
- macOS/Windows 的系统 WebView 对文件夹拖放行为不一致

应从本期范围中拆出，单独验证 pywebview 对文件夹拖放的支持后实施。

#### 其他改动

- 拖拽覆盖层提示文本更新为 "松开以打开项目或导入媒体文件"
- 循环中增加状态检查: 一旦有成功的项目打开/创建操作即 `break`，避免多文件同时拖入时触发多次 `create_project` 导致状态竞争

#### 媒体路径不可达的错误处理

`open_project` 后端仅验证 `project_path.exists()`，不验证 project 内 `media.path` 的可达性。当用户从移动硬盘拖入 `project.json` 但媒体文件未挂载时，前端会静默进入 WorkspacePage 并在后续操作中陆续报错。

建议在 `open_project` 中增加 `media_path` 可达性检查，返回 warning 字段（非 error，允许只读打开）:
```python
media_path = Path(project.media.path) if project.media else None
warnings = []
if media_path and not media_path.exists():
    warnings.append(f"Media file not found: {media_path}")
return {"success": True, "data": project.model_dump(), "warnings": warnings}
```

### 涉及文件

| 文件 | 行号 | 说明 |
|------|------|------|
| `frontend/src/App.vue` | 56-85 | handleWindowDrop 拖拽处理 |
| `frontend/src/App.vue` | 97-109 | 拖拽覆盖层文本 |
| `frontend/src/pages/WelcomePage.vue` | 26-42 | openRecentProject 逻辑 |
| `core/project_service.py` | 71-88 | open_project 后端（需添加 media_path 警告） |
| `pywebvue/bridge.py` | 197-215 | 拖拽文件路径获取 |

---

## 总结

| ID | 严重度 | 类型 | 概述 | 改动量 |
|----|--------|------|------|--------|
| I-1 | MEDIUM | UI/UX | Analysis 按钮位置调整到 SubtitleTrim 右侧 | 小 |
| I-2 | HIGH | 功能缺失 + 数据模型 | DetectSilence 静音段不支持单独删除 + EditDecision target_id 模型缺陷 | 中-大 |
| I-3 | MEDIUM | 功能缺失 | 首页拖拽不支持 project.json 打开项目（文件夹拖放单独验证） | 小（Phase 1） |

---

## 系统性架构观察

### 1. Segment Row 接口不统一

SilenceRow 是后来补充的功能，复用了 Timeline 的骨架但未完整实现接口（TranscriptRow 6 个事件，SilenceRow 仅 3 个）。建议定义统一的 **Segment Row Interface**（TypeScript interface），明确每种 segment type 必须支持的事件集合:

```typescript
interface SegmentRowEmits {
  seek: [time: number]
  'update-time': [segmentId: string, field: 'start' | 'end', value: number]
  'toggle-status': []
  'confirm': []   // 统一命名: confirm-edit / confirm-silence -> confirm
  'reject': []    // 统一命名: reject-edit / reject-silence -> reject
  'delete': []    // 单独删除本段
}
```

### 2. EditDecision 数据模型约束缺失

`target_id` 应在 `target_type="segment"` 时为必填，但 Pydantic 模型无此约束。静音 EditDecision 使用 `target_type="range"` + `target_id=None` 的组合，导致所有按 `target_id` 过滤的代码路径失效。应在模型层添加 `model_validator` 并将静音 EditDecision 改为绑定 `target_id=segment.id`。

---

## 附录 A: I-1 工具栏布局代码

### A.1 WorkspacePage.vue 工具栏完整结构（第455-620行）

```html
<!-- WorkspacePage.vue:455 -->
<div class="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2">

  <!-- 1. Import SRT -->
  <button class="... bg-blue-500 ..." @click="handleImportSRT">
    <SrtIcon class="w-4 h-4" /> 导入SRT
  </button>

  <!-- 2. Detect Silence + Settings (split button) -->
  <div class="relative inline-flex items-center">
    <button class="... bg-blue-500 rounded-r-none ..." @click="handleDetectSilence">
      <SpeakerWaveIcon class="w-4 h-4" /> 静音检测
    </button>
    <button class="... bg-blue-600 rounded-l-none ..." @click="toggleSilenceSettings">
      <Cog6ToothIcon class="w-3 h-3" />
    </button>
    <!-- silence settings dropdown (lines 488-519) -->
  </div>

  <!-- 3. Delete all silence markers -->
  <button class="... bg-red-500 ..." @click="showDeleteSilenceConfirm = true">
    <TrashIcon class="w-4 h-4" />
  </button>

  <!-- 4. Analysis dropdown *** 当前位置 *** -->
  <div class="relative">
    <button class="... bg-purple-500 ..." @click="showAnalysisDropdown = !showAnalysisDropdown">
      <SparklesIcon class="w-4 h-4" /> 分析 <ChevronDownIcon class="w-3 h-3" />
    </button>
    <!-- analysis dropdown menu (lines 549-568) -->
  </div>

  <!-- 5. Subtitle Trim + Settings (split button) -->
  <div class="relative inline-flex items-center">
    <button class="... bg-orange-500 rounded-r-none ..." @click="handleSubtitleTrim">
      <ScissorsIcon class="w-4 h-4" /> 字幕裁剪
    </button>
    <button class="... bg-orange-600 rounded-l-none ..." @click="toggleTrimSettings">
      <Cog6ToothIcon class="w-3 h-3" />
    </button>
    <!-- trim settings dropdown (lines 589-606) -->
  </div>

  <!-- 6. Clear subtitle trim markers -->
  <button class="... bg-red-500 ..." @click="handleDeleteSubtitleTrimEdits">
    <TrashIcon class="w-4 h-4" />
  </button>

  <!-- 7. Divider -->
  <div class="h-6 w-px bg-gray-300"></div>

  <!-- 8. Export buttons ... -->
</div>
```

---

## 附录 B: I-2 静音段相关完整代码

### B.1 SilenceRow.vue 完整代码

```vue
<!-- frontend/src/components/workspace/SilenceRow.vue -->
<script setup lang="ts">
import { computed, ref, nextTick } from "vue"
import type { Segment } from "@/types/project"
import { formatTime, parseTime } from "@/utils/format"

const props = defineProps<{
  segment: Segment
  displayStatus?: string
  styleClass?: string
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": []
}>()

// Time editing
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
    :data-segment-id="segment.id"
    :class="{
      'bg-gray-50': !displayStatus || displayStatus === 'none',
      'bg-yellow-50 border-l-3 border-yellow-400': displayStatus === 'pending',
      'bg-red-50 border-l-3 border-red-400 opacity-60': displayStatus === 'confirmed' || styleClass === 'masked',
      'bg-green-50 border-l-3 border-green-400': styleClass === 'kept',
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
      v-if="displayStatus && displayStatus !== 'none'"
      class="text-xs px-1.5 py-0.5 rounded shrink-0 cursor-pointer transition-colors"
      :class="{
        'bg-yellow-100 text-yellow-700 hover:bg-yellow-200': displayStatus === 'pending',
        'bg-red-100 text-red-700 hover:bg-red-200': displayStatus === 'confirmed',
        'bg-green-100 text-green-700 hover:bg-green-200': displayStatus === 'rejected',
      }"
      title="Click to toggle confirmed/rejected"
      @click.stop="emit('toggle-status')"
    >
      {{ displayStatus === "pending" ? "建议删除" : displayStatus === "confirmed" ? "已确认" : "已保留" }}
    </span>
  </div>
</template>
```

### B.2 TranscriptRow.vue 状态 badge 区域（参照，第195-228行）

```html
<!-- TranscriptRow.vue:195-228 — Status column (字幕段的完整 badge 布局) -->
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
      title="Click to keep"
      @click.stop="emit('toggle-status')"
    >
      已删除
    </span>
  </template>
  <template v-else-if="displayStatus === 'rejected'">
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
      class="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 cursor-pointer hover:bg-gray-200 transition-colors"
      title="Click to mark for deletion"
      @click.stop="emit('toggle-status')"
    >
      无标注
    </span>
  </template>
</div>
```

### B.3 Timeline.vue 中 SilenceRow 与 TranscriptRow 事件绑定对比（第88-112行）

```html
<!-- Timeline.vue:88-112 -->
<template v-for="seg in segments" :key="seg.id">

  <!-- 字幕段: 6 个事件绑定 -->
  <TranscriptRow
    v-if="seg.type === 'subtitle'"
    :segment="seg"
    :display-status="getSegmentState(seg).displayStatus"
    :style-class="getSegmentState(seg).styleClass"
    :is-selected="selectedSegmentId === seg.id"
    :global-edit-mode="globalEditMode"
    @seek="(t) => emit('seek', t)"
    @update-text="(id, text) => emit('update-text', id, text)"
    @update-time="(id, field, val) => emit('update-time', id, field, val)"
    @toggle-status="emit('toggle-status', seg)"
    @confirm-edit="emit('confirm-segment', seg)"
    @reject-edit="emit('reject-segment', seg)"
  />

  <!-- 静音段: 仅 3 个事件绑定，缺少 confirm/reject/delete -->
  <SilenceRow
    v-else
    :segment="seg"
    :display-status="getSegmentState(seg).displayStatus"
    :style-class="getSegmentState(seg).styleClass"
    @seek="(t) => emit('seek', t)"
    @update-time="(id, field, val) => emit('update-time', id, field, val)"
    @toggle-status="emit('toggle-status', seg)"
  />

</template>
```

### B.4 Timeline.vue SuggestionPanel 显示条件（第113-119行）

```html
<!-- Timeline.vue:113-119 -->
<div
  v-if="edits.some(e => e.status === 'pending')"
  class="w-72 border-l border-gray-200 overflow-y-auto"
>
  <SuggestionPanel
    :analysis-results="analysisResults"
    :edits="edits"
    :segments="segments"
    @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
    @reject-edit="(editId) => emit('reject-suggestion', editId)"
    @confirm-all="emit('confirm-all')"
    @reject-all="emit('reject-all')"
    @seek="(t) => emit('seek-suggestion', t)"
  />
</div>
```

### B.5 SuggestionPanel.vue 分组逻辑（第35-47行）

```typescript
// SuggestionPanel.vue:35-47
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
  return result
})
```

### B.6 SegmentBlocksLayer.vue 波形层删除功能（右键菜单，第197-215行）

```html
<!-- SegmentBlocksLayer.vue:197-215 — 波形层有删除能力，但 Timeline 列表视图没有 -->
<Teleport to="body">
  <div
    v-if="contextMenu"
    class="fixed z-50 bg-white rounded-md shadow-lg border border-gray-200 py-1 min-w-[120px]"
    :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
    @click="closeContextMenu"
  >
    <button
      class="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
      @click="deleteSelected"
    >
      删除
    </button>
  </div>
</Teleport>
```

### B.7 project_service.py 静音 EditDecision 创建（第257-282行）

```python
# project_service.py:257-282
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
    target_type="range",
    target_id=None,          # <-- 数据模型缺陷: 应改为 target_id=sil_segment.id
)
```

### B.8 project_service.py delete_segment 孤儿问题（第436-455行）

```python
# project_service.py:436-455
def delete_segment(self, segment_id: str) -> dict:
    """Delete a single segment and its associated edits."""
    if not self._current:
        return {"success": False, "error": "No project open"}

    # Remove the segment
    remaining = [s for s in self._current.transcript.segments if s.id != segment_id]

    if len(remaining) == len(self._current.transcript.segments):
        return {"success": False, "error": f"Segment {segment_id} not found"}

    # Remove edits targeting this segment
    remaining_edits = [
        e for e in self._current.edits
        if e.target_id != segment_id       # <-- 修复后: 静音 EditDecision 的 target_id = segment.id
                                           # <-- 此逻辑直接生效，无需修改
    ]
    # ...
```

### B.9 project_service.py delete_silence_segments 正确实现（第457-480行）

```python
# project_service.py:457-480 — 批量删除需统一为按 target_id 过滤
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

    # 修复后: 统一按 target_id 过滤（静音 EditDecision 已绑定 segment.id）
    remaining_edits = [
        e for e in self._current.edits
        if e.target_id not in silence_ids
        # 不再需要 and e.source != "silence_detection" 的特殊处理
    ]
    # ...
```

---

## 附录 C: I-3 拖拽导入相关代码

### C.1 App.vue handleWindowDrop（第56-85行）

```typescript
// App.vue:56-85
async function handleWindowDrop() {
  isDragOver.value = false
  dragCounter.value = 0

  const res = await call<string[]>("get_dropped_files")
  if (!res.success || !res.data || res.data.length === 0) return

  const paths = res.data

  for (const path of paths) {
    const ext = path.split(".").pop()?.toLowerCase() ?? ""
    const mediaExtensions = ["mp4", "mkv", "avi", "mov", "webm", "mp3", "wav", "aac", "flac", "ogg", "m4a"]

    if (mediaExtensions.includes(ext) && !project.value) {
      // 无项目时: 导入媒体文件创建新项目
      const probeRes = await call<MediaInfo>("probe_media", path)
      if (!probeRes.success || !probeRes.data) continue
      const name = path.split(/[/\\]/).pop()?.replace(/\.[^.]+$/, "") ?? "Untitled"
      const createRes = await call<Project>("create_project", name, path)
      if (createRes.success && createRes.data) {
        project.value = createRes.data
        triggerWaveformGeneration()
      }
    } else if (ext === "srt" && project.value) {
      // 有项目时: 导入 SRT 字幕
      await call("import_srt", path)
    }
    // 其他情况: 静默忽略（包括 project.json 和文件夹）
  }
}
```

### C.2 App.vue 拖拽覆盖层（第97-109行）

```html
<!-- App.vue:97-109 -->
<div
  v-if="isDragOver"
  class="fixed inset-0 z-50 flex items-center justify-center bg-blue-500/20 border-2 border-dashed border-blue-500"
>
  <div class="text-center">
    <template v-if="!project">
      <p class="text-lg font-medium text-blue-700">松开以导入媒体文件</p>
      <p class="text-sm text-blue-500 mt-1">支持拖拽到窗口任意位置</p>
    </template>
    <template v-else>
      <p class="text-lg font-medium text-blue-700">松开以导入 SRT 文件</p>
    </template>
  </div>
</div>
```

### C.3 WelcomePage.vue openRecentProject（第26-42行）

```typescript
// WelcomePage.vue:26-42
async function openRecentProject(rp: RecentProject) {
  loading.value = true
  errorMsg.value = ""
  try {
    const res = await call<Project>("open_project", rp.path)
    if (!res.success || !res.data) {
      errorMsg.value = res.error || "Failed to open project"
      return
    }
    emit("project-created", res.data)
  } catch (err: any) {
    errorMsg.value = err.message || "Unknown error"
  } finally {
    loading.value = false
  }
}
```

### C.4 project_service.py open_project 后端（第71-88行）

```python
# project_service.py:71-88 — 已支持从任意路径打开，需添加 media_path 警告
def open_project(self, path: str) -> dict:
    """Open an existing project from a JSON file."""
    project_path = Path(path)
    if not project_path.exists():
        return {"success": False, "error": f"Project file not found: {path}"}

    try:
        data = json.loads(project_path.read_text(encoding="utf-8"))
        project = Project.model_validate(data)
        self._current = project
        self._current_path = project_path

        # 建议新增: media_path 可达性检查
        warnings = []
        if project.media and project.media.path:
            if not Path(project.media.path).exists():
                warnings.append(f"Media file not found: {project.media.path}")

        result = {"success": True, "data": project.model_dump()}
        if warnings:
            result["warnings"] = warnings
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### C.5 bridge.py 拖拽文件路径获取（第197-215行）

```python
# pywebvue/bridge.py:197-215
# 注意: dataTransfer.files + pywebviewFullPath 仅对文件有效
# 文件夹拖放需要 webkitGetAsEntry()，当前不支持
def _on_drop(self, event: dict) -> None:
    """Handle native file drop events from pywebview."""
    files = event.get("dataTransfer", {}).get("files", [])
    paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
    if paths:
        with self._drop_lock:
            self._dropped_paths.extend(paths)

@expose
def get_dropped_files(self) -> dict[str, Any]:
    """Retrieve and clear buffered dropped file paths."""
    with self._drop_lock:
        paths = list(self._dropped_paths)
        self._dropped_paths.clear()
    return {"success": True, "data": paths}
```

---

## 附录 D: C1 新建导出界面（来自 audit-report-preview-4.md）

### D.1 C1 [FEATURE] 新建导出界面

#### 需求

用户要求：
1. **删除现有导出按钮**（Export Video、Export SRT、Export Audio），仅保留一个跳转导出界面的按钮
2. **导出界面允许编码设置**（视频编码器、音频编码器、码率、分辨率等）
3. **导出界面允许预览播放**（跳过所有标注已删除区域的播放）
4. **导出界面允许导出通用时间线格式**（EDL、FCPXML 等）

#### 设计方案概要

##### 新建 ExportPage.vue

路由级别的新页面，从 WorkspacePage 的导出按钮跳转。

**状态共享方案: 使用全局状态（Pinia store）管理 project**

- ExportPage 直接订阅全局 store 中的 project，状态始终最新
- 与现有的 "projectRef 更新 -> Timeline 重新渲染" 模式一致
- 不通过 props 传递（大型 project 对象在路由跳转时序列化有性能问题）

##### 编码设置

- 视频编码器选择：H.264 (libx264)、H.265 (libx265)、AV1(libsvtav1/av1_nvenc) 等，必须包含av1_nvenc，测试环境支持，且速度快，方便测试
- 码率控制：CRF 值 / 目标码率
- 分辨率：原始 / 1080p / 720p / 自定义
- 音频编码器：AAC / MP3 / Opus
- 音频码率：128k / 192k / 256k
- 预设速度：fast / medium / slow

**编码参数分级暴露**（避免用户误操作）:

- **基础模式**（默认）: 仅暴露 "质量" 滑块（映射到 CRF）、分辨率选择、输出格式
- **高级模式**（折叠展开）: 暴露编码器选择、音频码率、预设速度
- `av1_nvenc` 编码器仅在检测到 NVIDIA GPU 时显示，否则灰化并提示 "需要 NVIDIA GPU"

##### 预览播放（跳过删除区域）

使用 HTML5 video 元素 + 自定义逻辑跳过删除区域：

- 监听 `timeupdate` 事件，当 `currentTime` 进入 confirmed delete 范围时自动 `seek` 到范围 end
- 在时间轴上可视化显示保留/删除区域

**媒体源**: 应优先使用 `proxy_path`（低分辨率代理），而非直接加载原始媒体文件（可能是 4K 源文件）。若直接加载原始文件，在低配机器上预览本身会卡顿，掩盖删除段跳跃逻辑的真实问题。

**已知风险:** HTML5 video 的 `timeupdate` 触发间隔约 250ms。如果一个删除范围短于 250ms，播放器可能直接越过而不触发 seek。实现时需在 seek 后立即检查当前时间是否仍在删除区间内（防止 seek 精度不足），必要时使用 `requestAnimationFrame` 轮询替代 `timeupdate`。

##### 通用时间线格式导出

经调研 DaVinci Resolve 和 Premiere Pro 的导入支持，推荐格式优先级如下：

| 优先级 | 格式 | 理由 |
|--------|------|------|
| **第一优先** | **EDL (CMX3600) + FCPXML** | EDL 覆盖面最广，几乎所有 NLE 都能读，实现最简单；FCPXML 信息更丰富，Resolve 和 Premiere 都支持，且不需要 reel 号。两者并行实现成本不高。 |
| **第二优先** | **OTIO** | Python 官方库 `opentimelineio`，API 清晰。Resolve 原生支持，Premiere 26.0 起正式支持。实现成本低到中。 |
| **审阅用途** | **CSV** | Resolve/Premiere 不支持导入 CSV 作为时间线。定位为"人类可读的剪辑清单 / 审阅格式"，不作为 NLE 导入格式。 |
| **不推荐** | **AAF** | 实现复杂度远超需求，Python 侧缺少轻量级库，Milo-Cut 的简单剪辑结构不需要 AAF。 |

**EDL 规范注意事项:**
- 帧率换算: Milo-Cut 时间轴是秒数，生成 EDL 时需从 `media_info.fps` 换算为帧号。如果 fps 不可用，需要 fallback（默认 25fps）
- Reel Name: 使用媒体文件名（不含扩展名），最多 8 字符（CMX3600 标准限制），超出截断。Reel Name 填写不当会导致 NLE 导入后无法自动关联媒体
- 帧率模式: EDL 头部 `FCM` 字段需确认 `NON-DROP FRAME` vs `DROP FRAME`，与 fps fallback 问题同等重要

##### 实现范围

分阶段实施：
1. **Phase 1**: 基础界面框架 + 合并导出按钮（替换现有三个按钮）
2. **Phase 2**: 编码设置面板（分级暴露）
3. **Phase 3**: 预览播放（跳过删除区域，使用 proxy_path，注意 timeupdate 精度风险）
4. **Phase 4**: 通用时间线格式导出（EDL + FCPXML 优先，OTIO 后续，CSV 为审阅格式）

### D.2 C1 相关代码

#### D.2.1 当前 WorkspacePage 导出按钮（需替换为单个"跳转导出界面"按钮）

```html
<!-- WorkspacePage.vue:613-637 -->
<button @click="handleExportVideo">Export Video</button>
<button @click="handleExportSrt">Export SRT</button>
<button @click="handleExportAudio">Export Audio</button>
```

#### D.2.2 前端导出 composable

```typescript
// frontend/src/composables/useExport.ts
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

#### D.2.3 后端导出入口（main.py）

```python
# main.py:83-109 -- _handle_export_video（已传递 media_info）
return export_video(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    media_info=project.media.model_dump() if project.media else None,
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)

# main.py:130-155 -- _handle_export_audio
return export_audio(
    media_path=media_path,
    segments=segments_data,
    edits=edits_data,
    output_path=output_path,
    progress_callback=progress_cb,
    cancel_event=cancel_event,
)
```

#### D.2.4 导出服务核心函数（export_service.py）

```python
# export_service.py:29-109 -- export_video
def export_video(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    media_info: dict | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:

# export_service.py:112-185 -- export_audio
def export_audio(
    media_path: str,
    segments: list[dict],
    edits: list[dict],
    output_path: str,
    *,
    progress_callback: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> dict:

# export_service.py:188-233 -- export_srt
def export_srt(
    segments: list[dict],
    edits: list[dict],
    output_path: str,
) -> dict:
```

#### D.2.5 MediaInfo 模型（编码设置需要读取的字段）

```python
# core/models.py:76-88
class MediaInfo(BaseModel, frozen=True):
    path: str
    media_hash: str = ""
    duration: float = 0.0       # ffprobe 探测的实际时长
    format: str = ""
    width: int = 0               # 编码设置: 原始分辨率
    height: int = 0
    fps: float = 0.0             # EDL 导出需要帧率
    audio_channels: int = 0
    sample_rate: int = 0
    bit_rate: int = 0
    proxy_path: str | None = None  # 预览播放应优先使用此字段
    waveform_path: str | None = None
```

#### D.2.6 导出链路概览

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
  export_video:  _get_confirmed_deletions -> _compute_keep_ranges -> ffmpeg 提取+concat
  export_srt:    exclude overlapped subtitles -> adjust timestamps
  export_audio:  _get_confirmed_deletions -> _compute_keep_ranges -> ffmpeg 提取+concat (has_video=False)

C1 目标:
  三种导出合并为 ExportPage 单一入口 (Pinia store 管理状态)
  + 编码设置面板 (基础/高级分级暴露, GPU 检测)
  + 预览播放 (跳过 confirmed delete 区域, 优先使用 proxy_path)
  + 通用时间线导出 (EDL + FCPXML 优先, EDL Reel Name / 帧率模式规范)
```

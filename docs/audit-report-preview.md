# Milo-Cut Workspace UI 审计报告

**日期:** 2026-05-15
**项目:** Milo-Cut (pywebview + Vue 3 + Python)
**审计范围:** Workspace 时间轴编辑区域 — 波形显示、块编辑、字幕同步
**目标读者:** 外部 UI/UX 专家、前端架构师

---

## 核心期望 (用户原话)

> 我最希望能够实现的是在时间轴上直观显示**音频波形**、**字幕块及字幕间的空隙**、**空白检测的有声与静音区域**，并能够通过**拖拽块的左右两边快速编辑时间戳**，这个时间戳与 Timeline 模块中保持**双向同步**（Timeline 中修改了也会同步到时间轴上）。感觉现在这种叠叠乐的模式会影响这一期望的实现。

**一句话总结:** TimelineRuler 应该是一个 **波形+块编辑器**，而不是一个 **选区+标尺**。

---

## 一、项目上下文

### 1.1 产品定位

Milo-Cut 是一款桌面视频预处理工具，核心功能是**基于字幕的视频剪辑**：用户导入视频和 SRT 字幕，系统自动检测静音段和口头禅，用户审核后导出剪辑后的视频。

技术栈:
- **前端:** Vue 3 (Composition API) + TypeScript + Tailwind CSS
- **后端:** Python (Pydantic v2) + pywebview (桌面桥接)
- **通信:** pywebview 的 `call()` RPC + `onEvent()` 事件系统

### 1.2 核心数据模型

```
Segment (字幕/静音段)
  ├── id: string          (如 "sub-0001", "sil-0001")
  ├── type: "subtitle" | "silence"
  ├── start/end: number   (秒)
  └── text: string

EditDecision (编辑决策)
  ├── id: string
  ├── start/end: number   (时间范围)
  ├── action: "delete" | "keep"
  ├── source: "user" | "silence_detection" | "filler_detection"
  ├── status: "pending" | "confirmed" | "rejected"
  ├── priority: number    (用户=200, 自动=100)
  ├── target_type: "segment" | "range"
  └── target_id?: string  (绑定的 Segment ID)
```

### 1.3 组件架构

```
WorkspacePage.vue
  └── Timeline.vue (右侧字幕列表面板)
        ├── TranscriptRow.vue (字幕行 — 编辑/状态/时间)
        ├── SilenceRow.vue (静音行 — 时间/状态)
        └── SuggestionPanel.vue (建议面板 — 分析结果)
  └── TimelineRuler.vue (底部时间标尺 — 选区/波形)
```

---

## 二、当前实现 vs 期望效果

### 2.1 TimelineRuler 的现状: "叠叠乐"

当前 TimelineRuler 是一个**选区工具**，所有 UI 元素堆叠在同一个容器中:

```
┌─────────────────────────────────────────────────────┐
│ 时间刻度 (点击 seek)                                   │  ← h-6, 独立层
├─────────────────────────────────────────────────────┤
│ 选区高亮 (蓝色半透明)                                  │
│  ├── 左句柄 (8px, cursor-ew-resize)                  │  ← pointer-events: all
│  ├── 右句柄 (8px, cursor-ew-resize)                  │  ← pointer-events: all
│  └── 选区主体 (cursor-move)                           │  ← pointer-events: all
│                                                       │
│  Segment 块 (蓝色/黄色/红色/绿色)                      │  ← @mousedown.stop
│  └── 块内文字 (truncated)                             │
│                                                       │
│  播放头 (红色竖线, z-10)                               │  ← pointer-events: none
├─────────────────────────────────────────────────────┤
│ 滚动条                                                │
└─────────────────────────────────────────────────────┘
```

**问题:** 选区、segment 块、播放头全部在同一层，事件冒泡复杂，无法实现"拖拽块边缘编辑时间戳"的需求。

### 2.2 期望的 TimelineRuler: "波形+块编辑器"

```
┌─────────────────────────────────────────────────────┐
│ 时间刻度                                              │  ← 独立层, seek
├─────────────────────────────────────────────────────┤
│ 音频波形 (高低起伏的灰色区域)                           │  ← 独立层, 背景
│                                                       │
│  [sub-001]  [  sub-002  ]  [sil-001]  [sub-003]      │  ← 块编辑层
│   ←|拖拽|→    ←|拖拽|→      (静音)     ←|拖拽|→       │
│                                                       │
│  有声区域 = 波形密集    静音区域 = 波形平坦              │  ← 波形层
│                                                       │
│  播放头                                               │
├─────────────────────────────────────────────────────┤
│ 滚动条                                                │
└─────────────────────────────────────────────────────┘
```

**关键差异:**

| 维度 | 当前 | 期望 |
|------|------|------|
| 核心交互 | 选区拖动 (select range) | 块边缘拖拽 (resize segment) |
| 视觉主体 | 选区高亮 (蓝色半透明) | 音频波形 (灰色高低起伏) |
| Segment 块 | 叠加在选区层上，点击选中 | 独立层，边缘可拖拽 |
| 静音区域 | 与字幕块同层，颜色区分 | 波形平坦区域，视觉上自然区分 |
| 时间戳编辑 | 在 Timeline 的 TranscriptRow 中 | 在 TimelineRuler 中拖拽边缘 |
| 同步机制 | 单向 (Timeline → TimelineRuler) | 双向 (拖拽 ↔ Timeline) |

### 2.3 字幕文本编辑 (TranscriptRow)

**现状:** 基本功能正常（编辑/保存/取消/Esc），全局编辑模式可工作。
**期望:** 文本编辑保留在 Timeline 中，时间戳编辑下沉到 TimelineRuler。

### 2.4 冲突遮罩 (Logical Masking)

**现状:** `effectiveStatus` 在渲染层决定 "normal"/"masked"/"kept"。
**期望:** 在波形视图中，静音区域自然可见，不需要额外的遮罩层。

---

## 三、面临的核心问题

### 问题 1 (根本): TimelineRuler 的架构定位错误

**现状:** TimelineRuler 是一个"选区工具"，核心交互是 `mousedown → select range → emit("select-range")`。Segment 块只是叠加在选区层上的视觉元素，不支持独立交互。

**期望:** TimelineRuler 应该是一个"块编辑器"，核心交互是 `mousedown on block edge → resize segment → emit("update-time")`。选区应该是次要功能。

**冲突点:**

```typescript
// 当前: 所有交互都围绕选区
function handleSelectionMouseDown(e: MouseEvent) {
  const zone = detectClickZone(e)  // 检测的是选区的句柄/主体/外部
  switch (zone) {
    case "left-handle": startHandleDrag("left", e)   // 拖拽选区左边界
    case "right-handle": startHandleDrag("right", e)  // 拖拽选区右边界
    case "body": startBodyDrag(e)                      // 移动整个选区
    case "outside": startNewSelection(e)               // 创建新选区
  }
}

// 期望: 所有交互都围绕 segment 块
function handleBlockMouseDown(segId: string, e: MouseEvent, edge: "left" | "right" | null) {
  if (edge) {
    startSegmentResize(segId, edge, e)   // 拖拽 segment 边缘 → 编辑时间戳
  } else {
    startSegmentDrag(segId, e)            // 移动整个 segment
  }
}
```

**需要专家意见:** 是否应该完全重构 TimelineRuler，将"块编辑"作为主交互，"选区"降级为辅助功能（如 shift+click 创建选区）？

### 问题 2: 波形显示与 Segment 块的层叠关系

**期望:** 音频波形作为背景，Segment 块作为前景，用户可以同时看到波形和字幕。

**现状:** 没有波形层。Segment 块和选区高亮在同一层，互相遮挡。

**技术约束:**
- pywebview 环境下，波形数据需要后端生成（已有 `waveform_path` 字段）
- 波形渲染可以用 Canvas 或 SVG，但需要与 Segment 块的 DOM 元素对齐
- 两者的时间→像素映射必须完全一致（共享 `viewStart` / `viewDuration`）

**需要专家意见:** 波形应该用 Canvas 渲染还是 SVG？Canvas 性能更好但与 DOM 块的 z-index 管理更复杂。

### 问题 3: 双向同步机制缺失

**期望:** 在 TimelineRuler 中拖拽 Segment 边缘 → Timeline 中的时间戳实时更新。在 Timeline 中编辑时间戳 → TimelineRuler 中的块位置实时更新。

**现状:**
- TimelineRuler 只接收 `segments` prop，不 emit `"update-time"`
- Timeline 的 TranscriptRow/SilenceRow 有时间编辑功能，但不通知 TimelineRuler
- 两者是独立的组件，没有共享状态

**数据流:**

```
当前:
  WorkspacePage → [segments prop] → Timeline → TranscriptRow (编辑时间)
  WorkspacePage → [segments prop] → TimelineRuler (只读显示)

期望:
  WorkspacePage → [segments ref] ↗ Timeline (显示 + 编辑)
                                ↘ TimelineRuler (显示 + 拖拽编辑)
  TimelineRuler → emit("update-time") → WorkspacePage → segments 更新 → 自动同步到 Timeline
  Timeline      → emit("update-time") → WorkspacePage → segments 更新 → 自动同步到 TimelineRuler
```

**需要专家意见:** 是否需要一个 `useSegmentEdit` composable 来统一管理时间戳编辑状态？

### 问题 4: 静音区域的视觉表达

**期望:** 静音区域在波形上自然可见（波形平坦），不需要额外的 UI 元素。

**现状:** 静音段是独立的 `Segment` 块，与字幕块同级显示，用颜色区分（灰色 vs 蓝色）。

**问题:** 如果实现了波形显示，静音段的块是否还需要？还是应该只在波形上标记静音区间（如用半透明覆盖层）？

**需要专家意见:** 静音检测结果应该如何在波形视图中表达？是保留独立块、还是用波形颜色/背景色区分？

### 问题 5: SuggestionPanel 与块编辑的交互

**现状:** SuggestionPanel 显示分析结果列表，点击"确认"修改 edit 的 status。

**问题:** 如果用户在 TimelineRuler 中拖拽了 Segment 边缘，这个操作应该：
- 自动创建一个 EditDecision？（用户手动调整 = 用户决策）
- 只修改 Segment 的 start/end？（直接编辑原始数据）
- 影响关联的 EditDecision？（如果该 segment 有 pending 的删除建议）

**需要专家意见:** Segment 时间戳编辑和 EditDecision 的关系是什么？是独立操作还是联动？

---

## 四、架构层面的疑问

### 4.1 TimelineRuler 需要完全重构

当前 TimelineRuler 的 ~600 行代码中，约 70% 是选区相关的逻辑（select range, handle drag, body drag, snap, scrollbar）。如果改为"波形+块编辑器"，这些代码大部分需要重写。

**疑问:** 是在现有代码上改造，还是从零开始写一个新的 `WaveformEditor.vue`？

### 4.2 状态管理需要统一

当前 `segments` 数据流:
```
WorkspacePage.segments (ref)
  ├── :segments prop → Timeline (只读 + 编辑时间)
  └── :segments prop → TimelineRuler (只读)
```

期望:
```
WorkspacePage.segments (ref)
  ├── :segments prop → Timeline (只读 + 编辑时间)
  └── :segments prop → TimelineRuler (只读 + 拖拽编辑)

TimelineRuler → emit("update-time", segId, field, value)
Timeline      → emit("update-time", segId, field, value)
                ↓
WorkspacePage → updateSegment(segId, field, value) → segments ref 更新
                ↓
              自动同步到 Timeline 和 TimelineRuler (Vue 响应式)
```

**疑问:** 是否需要一个 `useSegmentEdit` composable 封装 `updateSegment` 逻辑？

### 4.3 波形数据的获取与渲染

后端已有 `waveform_path` 字段，但前端从未使用。

**疑问:**
- 波形数据格式是什么？（JSON 数组？二进制？图片？）
- 渲染方案：Canvas（高性能，但与 DOM 块的 z-index 管理复杂）vs SVG（与 DOM 一致，但大文件性能差）
- 波形需要与 Segment 块完全对齐，共享 `viewStart` / `viewDuration` 的时间→像素映射

---

## 五、附录: 完整代码

### 5.1 数据类型 — `frontend/src/types/project.ts`

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

export interface AnalysisResult {
  id: string
  type: "filler" | "error"
  segment_ids: string[]
  confidence: number
  detail: string
}
```

### 5.2 后端模型 — `core/models.py` (EditDecision)

```python
class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None
```

### 5.3 后端服务 — `core/project_service.py` (关键片段)

**静音检测写入:**
```python
new_edits.append(EditDecision(
    id=edit_id,
    start=sil["start"],
    end=sil["end"],
    action="delete",
    source="silence_detection",
    status=EditStatus.PENDING,
    target_type="range",
    # target_id 为空 — 新建的静音段没有绑定目标
))
```

**用户标记写入:**
```python
new_edits.append(EditDecision(
    id=edit_id,
    start=seg.start,
    end=seg.end,
    action=action,
    source="user",
    status=edit_status,
    priority=200,
    target_type="segment",
    target_id=seg.id,  # 直接绑定 segment ID
))
```

**分析结果写入:**
```python
new_edits.append(EditDecision(
    id=edit_id,
    start=start,
    end=end,
    action="delete",
    source=source,
    analysis_id=ar.id,
    status=EditStatus.PENDING,
    priority=100,
    target_type="segment",
    target_id=ar.segment_ids[0],  # 绑定第一个 segment
))
```

### 5.4 Timeline.vue (完整)

```vue
<script setup lang="ts">
import type { Segment, EditDecision, AnalysisResult } from "@/types/project"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"

const props = defineProps<{
  segments: Segment[]
  edits: EditDecision[]
  analysisResults: AnalysisResult[]
  subtitleCount: number
  silenceCount: number
  selectedSegmentId?: string | null
  globalEditMode?: boolean
}>()

const emit = defineEmits<{
  seek: [time: number]
  "update-text": [segmentId: string, text: string]
  "update-time": [segmentId: string, field: "start" | "end", value: number]
  "toggle-status": [segment: Segment]
  "confirm-segment": [segment: Segment]
  "reject-segment": [segment: Segment]
  "confirm-suggestion": [editId: string]
  "reject-suggestion": [editId: string]
  "confirm-all": []
  "reject-all": []
  "seek-suggestion": [time: number]
  "toggle-edit-mode": []
}>()

function isOverlapping(edit: EditDecision, seg: Segment): boolean {
  return edit.start < seg.end && edit.end > seg.start
}

function getEditForSegment(seg: Segment): EditDecision | undefined {
  const byId = props.edits.find(e => e.target_id === seg.id)
  if (byId) return byId
  return props.edits.find(e =>
    Math.abs(e.start - seg.start) < 0.01 && Math.abs(e.end - seg.end) < 0.01,
  )
}

function getEffectiveStatus(seg: Segment): "normal" | "masked" | "kept" {
  const related = props.edits.filter(e =>
    e.target_id === seg.id || isOverlapping(e, seg),
  )
  if (related.length === 0) return "normal"
  const top = related.sort((a, b) => b.priority - a.priority)[0]
  if (top.action === "delete") return "masked"
  return "kept"
}

function getEditStatus(seg: Segment): EditDecision["status"] | null {
  return getEditForSegment(seg)?.status ?? null
}
</script>

<template>
  <div class="flex w-3/5 min-w-[500px] flex-col">
    <div class="flex items-center justify-between border-b border-gray-200 px-4 py-2">
      <span class="text-sm font-medium">Timeline</span>
      <div class="flex items-center gap-2">
        <button v-if="!globalEditMode" ... @click="emit('toggle-edit-mode')">编辑字幕</button>
        <button v-else ... @click="emit('toggle-edit-mode')">退出编辑</button>
        <span class="text-xs text-gray-500">{{ subtitleCount }} subtitles + {{ silenceCount }} silence</span>
      </div>
    </div>
    <div class="flex flex-1 overflow-hidden">
      <div class="flex-1 overflow-y-auto">
        <template v-for="seg in segments" :key="seg.id">
          <TranscriptRow
            v-if="seg.type === 'subtitle'"
            :segment="seg"
            :edit-status="getEditStatus(seg)"
            :effective-status="getEffectiveStatus(seg)"
            :is-selected="selectedSegmentId === seg.id"
            :global-edit-mode="globalEditMode"
            ...
          />
          <SilenceRow
            v-else
            :segment="seg"
            :edit-status="getEditStatus(seg)"
            :effective-status="getEffectiveStatus(seg)"
            ...
          />
        </template>
      </div>
      <div v-if="edits.some(e => e.status === 'pending')" class="w-72 ...">
        <SuggestionPanel ... />
      </div>
    </div>
  </div>
</template>
```

### 5.5 TranscriptRow.vue (完整)

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
  if (val && !isEditingText.value) startEdit()
  else if (!val && isEditingText.value) saveEdit()
})

function handleTextEditBlur() {
  if (props.globalEditMode) return  // 冻结
  saveEdit()
}

function handleTextEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") saveEdit()
  else if (e.key === "Escape") cancelEdit()
}

function handleRowClick() {
  if (editingTimeField.value) return
  if (isEditingText.value && !props.globalEditMode) saveEdit()
  emit("seek", props.segment.start)
}

const statusClass = computed(() => {
  if (props.effectiveStatus === "masked")
    return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
  if (props.effectiveStatus === "kept")
    return "border-l-3 border-green-400 bg-green-50"
  switch (props.editStatus) {
    case "pending": return "border-l-3 border-yellow-400 bg-yellow-50"
    case "confirmed": return "border-l-3 border-red-400 bg-red-50 line-through opacity-60"
    case "rejected": return "border-l-3 border-green-400 bg-green-50"
    default: return ""
  }
})
</script>

<template>
  <div :class="[statusClass, { 'ring-1 ring-blue-500': isSelected }]" @click="handleRowClick">
    <!-- 时间列 -->
    <div class="text-xs text-gray-400 w-[130px] ...">
      <span @mousedown.stop.prevent="startTimeEdit('start', $event)">{{ formatTime(segment.start) }}</span>
      <span>→</span>
      <span @mousedown.stop.prevent="startTimeEdit('end', $event)">{{ formatTime(segment.end) }}</span>
    </div>
    <!-- 文本列 -->
    <div class="flex-1 min-w-0 overflow-hidden">
      <input v-if="isEditingText" v-model="editText"
        @blur="handleTextEditBlur" @keydown="handleTextEditKeydown"
        @mousedown.stop @click.stop />
      <span v-else>{{ segment.text }}</span>
    </div>
    <!-- 编辑按钮 -->
    <div>
      <template v-if="isEditingText">
        <span @click.stop="saveEdit">保存</span>
        <span @click.stop="cancelEdit">取消</span>
      </template>
      <template v-else>
        <span @click.stop="startEdit">编辑</span>
      </template>
    </div>
    <!-- 状态列 -->
    <div>
      <template v-if="editStatus === 'pending'">
        <span @click.stop="emit('confirm-edit')">建议删除</span>
        <button @click.stop="emit('reject-edit')">保留</button>
      </template>
      <template v-else-if="editStatus === 'confirmed'">
        <span @click.stop="emit('toggle-status')">已删除</span>
      </template>
      <template v-else-if="editStatus === 'rejected'">
        <span @click.stop="emit('toggle-status')">已保留</span>
      </template>
      <template v-else>
        <span @click.stop="emit('toggle-status')">已保留</span>
      </template>
    </div>
  </div>
</template>
```

### 5.6 SilenceRow.vue (完整)

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

// 时间编辑逻辑 (与 TranscriptRow 相同)

const duration = computed(() => (props.segment.end - props.segment.start).toFixed(1))
</script>

<template>
  <div :class="{
    'bg-gray-50': !editStatus && (!effectiveStatus || effectiveStatus === 'normal'),
    'bg-yellow-50 border-l-3 border-yellow-400': editStatus === 'pending',
    'bg-red-50 border-l-3 border-red-400 opacity-60': editStatus === 'confirmed' || effectiveStatus === 'masked',
    'bg-green-50 border-l-3 border-green-400': editStatus === 'rejected' || effectiveStatus === 'kept',
  }">
    <!-- 时间列 -->
    <!-- 静音标识: --- 静音 X.Xs --- -->
    <!-- 状态按钮 -->
  </div>
</template>
```

### 5.7 TimelineRuler.vue — 选区拖动逻辑 (关键片段)

```typescript
// 句柄检测 (像素级)
const HANDLE_ZONE_PX = 8

function detectClickZone(e: MouseEvent): "left-handle" | "right-handle" | "body" | "outside" {
  const rect = rulerRef.value!.getBoundingClientRect()
  const clickX = e.clientX - rect.left
  const startPx = percentToPixels(timeToPercent(selectionStart.value!))
  const endPx = percentToPixels(timeToPercent(selectionEnd.value!))

  if (Math.abs(clickX - startPx) <= HANDLE_ZONE_PX) return "left-handle"
  if (Math.abs(clickX - endPx) <= HANDLE_ZONE_PX) return "right-handle"
  if (clickX > startPx && clickX < endPx) return "body"
  return "outside"
}

// Offset 算法
function startHandleDrag(side: "left" | "right", e: MouseEvent) {
  const handleTime = side === "left" ? selectionStart.value! : selectionEnd.value!
  const clickTime = getTimeFromX(e.clientX)
  dragInitialOffset.value = handleTime - clickTime  // 记录偏移
}

function handleHandleDrag(e: MouseEvent) {
  const rawTime = getTimeFromX(e.clientX) + dragInitialOffset.value  // 应用偏移
  // ...
}

// 释放吸附
function maybeSnapOnRelease(): boolean {
  const timePerPx = viewDuration.value / rect.width
  const snapTimeThreshold = SNAP_RELEASE_PX * timePerPx  // 5px → 时间阈值
  // 检查所有 segment 边界...
}
```

### 5.8 SuggestionPanel.vue (完整)

```vue
<script setup lang="ts">
import { computed, ref } from "vue"
import type { AnalysisResult, EditDecision, Segment } from "@/types/project"

const props = defineProps<{
  analysisResults: AnalysisResult[]
  edits: EditDecision[]
  segments: Segment[]
}>()

const pendingEdits = computed(() =>
  props.edits.filter(e => e.status === "pending" && e.action === "delete")
)

const groups = computed(() => {
  const fillerResults = props.analysisResults.filter(r => r.type === "filler")
  const errorResults = props.analysisResults.filter(r => r.type === "error")
  // 分组: "口头禅" / "口误触发"
})

function getEditForResult(result: AnalysisResult): EditDecision | undefined {
  return props.edits.find(e => e.analysis_id === result.id)
}
</script>

<template>
  <div>
    <div>发现 {{ analysisResults.length }} 处建议 | {{ pendingEdits.length }} 处待处理</div>
    <div v-for="group in groups">
      <div v-for="result in group.results" @click="handleSeek(result)">
        <span>{{ formatTime(...) }}</span>
        <span>{{ result.detail }}</span>
        <button @click.stop="emit('confirm-edit', ...)">确认</button>
        <button @click.stop="emit('reject-edit', ...)">忽略</button>
      </div>
    </div>
    <div v-if="pendingEdits.length > 0">
      <button @click="emit('confirm-all')">全部确认删除</button>
      <button @click="emit('reject-all')">忽略所有建议</button>
    </div>
  </div>
</template>
```

### 5.9 TranscriptRow.test.ts (完整)

```typescript
import { describe, it, expect } from "vitest"
import { mount } from "@vue/test-utils"
import { nextTick } from "vue"
import TranscriptRow from "./TranscriptRow.vue"
import type { Segment } from "@/types/project"

const baseSegment: Segment = {
  id: "seg-0001", version: 1, type: "subtitle",
  start: 1.0, end: 5.0, text: "Hello world", speaker: "",
}

describe("TranscriptRow", () => {
  it("renders segment text")
  it("renders timestamp")
  it("emits seek on click")
  it("shows pending status buttons")
  it("shows confirmed status with strikethrough class")
  it("applies selected ring style")
  it("enters edit mode on edit button click")
  it("emits update-text on save with changed text")
  it("cancels edit on Esc and restores original text")
  it("saves edit on blur")
  it("saves edit on row click and seeks")
  it("enters edit mode when globalEditMode becomes true")
  it("saves and exits when globalEditMode becomes false")
  it("shows save and cancel buttons when editing")
  it("does not emit update-text when save with unchanged text")
})
```

---

## 六、请求专家解答的具体问题

| # | 问题 | 优先级 |
|---|------|--------|
| Q1 | TimelineRuler 应该完全重写为"波形+块编辑器"，还是在现有选区逻辑上叠加块编辑？ | HIGH |
| Q2 | 波形渲染方案：Canvas（高性能）vs SVG（DOM 一致）？如何与 Segment 块的 DOM 层对齐？ | HIGH |
| Q3 | 块边缘拖拽的时间→像素精度如何保证？拖拽时是否需要实时吸附到帧边界？ | HIGH |
| Q4 | 静音检测结果在波形视图中的表达方式：独立块 vs 波形颜色 vs 背景覆盖层？ | MEDIUM |
| Q5 | Segment 时间戳编辑与 EditDecision 的关系：独立操作 vs 联动？ | MEDIUM |
| Q6 | 双向同步是否需要 `useSegmentEdit` composable，还是直接通过 prop/emit 链？ | MEDIUM |
| Q7 | 选区功能是否保留？如果保留，应该作为主交互还是辅助交互（如 shift+click）？ | LOW |

---

## 七、期望的架构重构方向

### 7.1 组件拆分

```
WaveformEditor.vue (替代 TimelineRuler.vue)
  ├── WaveformLayer.vue (Canvas/SVG 波形渲染)
  ├── SegmentBlocksLayer.vue (Segment 块 + 边缘拖拽)
  │     ├── SubtitleBlock.vue (字幕块, 可拖拽边缘)
  │     └── SilenceBlock.vue (静音块, 可拖拽边缘)
  ├── PlayheadLayer.vue (播放头)
  └── SelectionLayer.vue (选区, 辅助功能)
```

### 7.2 数据流

```
WorkspacePage
  ├── segments: Ref<Segment[]>  ← 唯一数据源
  ├── edits: Ref<EditDecision[]>
  │
  ├── <WaveformEditor
  │     :segments
  │     :edits
  │     :waveform-data
  │     :current-time
  │     @update-time="handleUpdateTime"
  │     @seek="handleSeek"
  │     @select-range="handleSelectRange"
  │   />
  │
  └── <Timeline
        :segments
        :edits
        @update-time="handleUpdateTime"
        @update-text="handleUpdateText"
        @seek="handleSeek"
      />

handleUpdateTime(segId, field, value) {
  // 更新 segments ref → Vue 响应式自动同步到两个子组件
  segments.value = segments.value.map(s =>
    s.id === segId ? { ...s, [field]: value } : s
  )
}
```

### 7.3 块边缘拖拽交互

```typescript
// SegmentBlocksLayer.vue
function handleBlockEdgeMouseDown(segId: string, edge: "left" | "right", e: MouseEvent) {
  e.stopPropagation()
  const seg = segments.find(s => s.id === segId)
  const initialValue = edge === "left" ? seg.start : seg.end
  const clickTime = getTimeFromX(e.clientX)
  const offset = initialValue - clickTime

  const onMove = (e: MouseEvent) => {
    const rawTime = getTimeFromX(e.clientX) + offset
    const snapped = snapEnabled ? snapTime(rawTime) : rawTime
    const clamped = clampTime(snapped, edge, seg)
    emit("update-time", segId, edge === "left" ? "start" : "end", clamped)
  }

  const onUp = () => {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }

  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}
```

---

## 八、测试状态

- Frontend: 30/30 passed (Vitest)
- Backend: 64/64 passed (pytest)
- Build: vue-tsc + vite build 通过

所有测试通过，但测试覆盖的是单元行为，未覆盖上述组件间的交互问题。重构后需要新增:
- 块边缘拖拽的交互测试
- 双向同步的集成测试
- 波形渲染的视觉回归测试

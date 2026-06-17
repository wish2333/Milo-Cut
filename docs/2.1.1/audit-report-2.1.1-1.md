# v2.1.1 审计报告 1 — 剩余交互问题规格

> **日期**: 2026-06-17
> **审计目标**: 针对 v2.1.1 实施后报告的三个交互问题进行深度访谈，输出修复规格
> **方法**: spec-interview 技能驱动的用户访谈

---

## 问题清单

| ID | 问题 | 严重程度 | 状态 |
|----|------|---------|------|
| A-01 | Timeline/Waveform 右键菜单互相独立，打开一个不关闭另一个 | 中 | **待修复** |
| A-02 | Timeline 右键点击时间戳误进入时间编辑模式 | 低 | **待修复** |
| A-03 | 编辑模式/选择模式下 Waveform 及 Timeline 操作行为混乱 | 高 | **待修复** |

---

## A-01: 右键菜单互关

### 现象

Timeline (TranscriptRow) 和 Waveform (SegmentBlocksLayer) 各自有独立的右键菜单，各自管理打开/关闭。右击一个区域唤出菜单后，直接右击另一个区域，旧菜单不关闭，新旧菜单重叠显示。

### 根因

- Timeline 使用 `contextMenuManager.ts` 的 `openContextMenu()` 管理菜单生命周期
- Waveform 使用内部 `contextMenu.value` + 本地 document 监听器
- 两者之间无通信机制，各自不知道对方菜单的存在

### 用户需求

> 点击任意区域（包括另一个右键区域）时关闭目前已打开的菜单，不要求全局单例。

### 修复方案

1. `contextMenuManager.ts` — `closeActive()` 新增 `CustomEvent('closeallcontextmenus')` 广播
2. `contextMenuManager.ts` — `openContextMenu()` 新增 `closeallcontextmenus` 监听器，使 Timeline 菜单能被 Waveform 关闭
3. `SegmentBlocksLayer.vue` — `handleBlockContextMenu` 打开菜单前 dispatch 事件；`onMounted` 监听该事件关闭本地菜单

---

## A-02: Timeline 右键时间戳不进编辑

### 现象

TranscriptRow 的时间列数字上右键点击时，先弹出时间编辑输入框，再弹出右键菜单。

### 根因

时间列的 `@mousedown.stop.prevent="startTimeEdit(...)"` 同时响应左键和右键。`mousedown` 事件在 `contextmenu` 事件之前触发，所以先进入编辑再弹出菜单。

### 用户需求

> 左键点击进入编辑，右键仅弹出菜单。

### 修复方案

在 `startTimeEdit` 调用前添加 `e.button !== 0` 判断，右键 (`button === 2`) 时直接 return。时间列模板改为：

```vue
@mousedown.stop.prevent="onTimeMouseDown('start', $event)"
```

其中 `onTimeMouseDown` 检查 `e.button === 0` 时才调用 `startTimeEdit`。

---

## A-03: 编辑模式拦截

### 三种模式的行为定义

| 状态 | 时间尺点击 | 方向键 | Waveform 右键分割/删除 | Timeline 右键分割 |
|------|-----------|--------|----------------------|-----------------|
| **普通** (默认) | seek + 播放 | 移动指针(不播放) | 正常可用 | 正常可用 |
| **选择模式** (`selectionMode`) | 移动指针(不播放) | 移动指针(不播放) | 正常可用 | 正常可用 |
| **编辑模式** (`globalEditMode`) | 无反应 | 移动指针(不播放) | 菜单照弹，操作→toast「请退出编辑模式后重试」 | 菜单照弹，操作→toast「请退出编辑模式后重试」 |

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| `editingActive` 范围 | 仅跟随 `globalEditMode` | 选择模式不影响编辑操作 |
| 选择模式时间尺点击 | 走 `set-time`（移动指针不播放） | 用户需要选择时不跳转播放 |
| 方向键播放行为 | 所有模式移动指针不播放 | 方向键是定位工具，不是播放控制 |
| Waveform 右键拦截条件 | `globalEditMode` 激活时 | 编辑模式禁止结构性修改 |
| Timeline 右键分割拦截条件 | `globalEditMode` 激活时 | 同上，统一行为 |
| Toast 文案 | 统一「请退出编辑模式后重试」 | 简洁明确 |

### 新增事件

| 事件 | 方向 | 说明 |
|------|------|------|
| `set-time` | SegmentBlocksLayer → WaveformEditor → WorkspacePage | 移动指针但不播放 |
| `toast` | SegmentBlocksLayer / TranscriptRow → 父组件 | 显示 toast 通知 |

### 修改的文件

| 文件 | 改动 |
|------|------|
| `contextMenuManager.ts` | `closeActive()` 新增 CustomEvent 广播；`openContextMenu` 新增事件监听 |
| `SegmentBlocksLayer.vue` | 监听广播事件 + 打开菜单前广播 + 分割/删除前检查 `globalEditMode` emit toast |
| `TranscriptRow.vue` | 时间列 `mousedown` 判断 `e.button` + 分割前检查 `globalEditMode` emit toast |
| `Timeline.vue` | 透传 `globalEditMode`、toast 事件到子组件 |
| `WaveformEditor.vue` | 调整 `editingActive` 逻辑为仅 `globalEditMode`；支持 `set-time` emit |
| `WorkspacePage.vue` | 新增 `handleSetTime`（不播放）；toast 事件处理 |

---

## 附录 A: 当前代码实现

### A-1: contextMenuManager.ts (当前)

```typescript
type CloseFn = () => void

let activeClose: CloseFn | null = null
let cleanupDocument: (() => void) | null = null

function closeActive() {
  if (cleanupDocument) {
    cleanupDocument()
    cleanupDocument = null
  }
  if (activeClose) {
    activeClose()
    activeClose = null
  }
}

function handleDocClick() { closeActive() }
function handleDocContextMenu() { closeActive() }
function handleScroll() { closeActive() }

export function openContextMenu(closeFn: CloseFn) {
  closeActive()
  activeClose = closeFn
  setTimeout(() => {
    document.addEventListener("click", handleDocClick, { once: true })
    document.addEventListener("contextmenu", handleDocContextMenu, { once: true })
    document.addEventListener("scroll", handleScroll, { capture: true, once: true })
    cleanupDocument = () => {
      document.removeEventListener("click", handleDocClick)
      document.removeEventListener("contextmenu", handleDocContextMenu)
      document.removeEventListener("scroll", handleScroll, { capture: true })
    }
  }, 0)
}

export function closeContextMenu() { closeActive() }
```

### A-2: SegmentBlocksLayer 右键菜单 (当前)

**关键函数**:

```typescript
function handleBlockContextMenu(block: Block, e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  selectedBlockId.value = block.seg.id
  contextMenu.value = { x: e.clientX, y: e.clientY, segmentId: block.seg.id }
  // 本地 document 监听器管理关闭
  const close = () => { contextMenu.value = null }
  const onDocClick = (ce: MouseEvent) => {
    const target = ce.target as HTMLElement
    if (!target.closest(".fixed.z-\\[9999\\]")) { close(); cleanup() }
  }
  const onDocContext = () => { close(); cleanup() }
  const cleanup = () => {
    document.removeEventListener("click", onDocClick)
    document.removeEventListener("contextmenu", onDocContext)
  }
  setTimeout(() => {
    document.addEventListener("click", onDocClick)
    document.addEventListener("contextmenu", onDocContext)
  }, 0)
}
```

**菜单模板** (Teleport to body):

```vue
<Teleport to="body">
  <div v-if="contextMenu" class="fixed z-[9999] bg-white rounded-md shadow-lg ..."
    :style="{ left: contextMenu.x + 'px', top: Math.min(contextMenu.y, menuMaxY) + 'px' }"
    @click="closeContextMenu">
    <button @click="splitSelectedAtCursor">按时间指针分割</button>
    <button @click="splitSelectedAtMidpoint">从中点分割</button>
    <div class="border-t ..." />
    <button @click="deleteSelected">删除</button>
  </div>
</Teleport>
```

**分割/删除函数**:

```typescript
function splitSelectedAtCursor() {
  const id = contextMenu.value?.segmentId
  if (!id) return
  const seg = props.segments.find(s => s.id === id)
  const pos = props.currentTime ?? 0
  if (!seg || pos <= seg.start || pos >= seg.end) return
  emit("split-segment", id, pos)
  closeContextMenu()
}

function splitSelectedAtMidpoint() {
  const id = contextMenu.value?.segmentId
  if (!id) return
  const seg = props.segments.find(s => s.id === id)
  if (!seg) return
  const mid = (seg.start + seg.end) / 2
  emit("split-segment", id, mid)
  closeContextMenu()
}

function deleteSelected() {
  if (selectedBlockId.value) {
    emit("delete-segment", selectedBlockId.value)
    selectedBlockId.value = null
  }
  closeContextMenu()
}
```

### A-3: WaveformEditor 编辑模式控制 (当前)

```typescript
const props = defineProps<{
  // ...
  editingActive?: boolean  // 当前 = globalEditMode || selectionMode
}>()

function handleSeek(time: number) {
  if (props.editingActive) return  // 编辑模式不 seek
  emit("seek", time)
}

function handleSeekSegment(segment: Segment) {
  if (props.editingActive) return  // 编辑模式不 seek
  emit("seek-segment", segment)
}

function handleWaveformSeek(time: number) {
  emit("seek", time)  // 方向键绕过 editingActive 检查
}
```

**WorkspacePage 绑定**:

```vue
<WaveformEditor
  :editing-active="globalEditMode || selectionMode"
  ...
/>
```

### A-4: TranscriptRow 时间编辑 (当前)

**时间列模板**:

```vue
<div class="text-xs text-gray-400 w-[150px] ...">
  <template v-if="editingTimeField === 'start'">
    <div class="flex items-center gap-0.5">
      <button @click.stop="adjustTime(-0.1)">&minus;</button>
      <input ref="timeInputRef" v-model="editingTimeValue" ... />
      <button @click.stop="adjustTime(0.1)">+</button>
    </div>
  </template>
  <template v-else>
    <span @mousedown.stop.prevent="startTimeEdit('start', $event)">
      {{ formatTime(segment.start) }}
    </span>
  </template>
  ... (同上 for 'end')
</div>
```

### A-5: TranscriptRow 右键菜单 (当前)

```vue
<Teleport to="body">
  <div v-if="contextMenu" class="fixed z-[9999] ...">
    <button @click="startEdit">编辑文本</button>
    <button @click="emit('toggle-status')">
      {{ displayStatus === 'confirmed' ? '取消删除' : '标记删除' }}
    </button>
    <div class="border-t ..." />
    <button @click="emit('split-at-pointer', props.currentTime ?? 0)">
      从时间指针分割
    </button>
    <button @click="emit('split')">从中点分割</button>
    <div class="border-t ..." />
    <button @click="emit('delete')">删除段落</button>
  </div>
</Teleport>
```

---

## 附录 B: 实施注意事项

1. **`editingActive` 重命名建议**: 当前 `editingActive` 语义模糊，建议改为 `editModeOn`（仅 `globalEditMode`）并新增 `selectModeOn`（仅 `selectionMode`）以便明确区分。
2. **`set-time` vs `seek`**: 前端需要区分"移动到时间点"和"移动到时间点并播放"。当前 `handleSeek` 在 WorkspacePage 中统一触发播放。新增 `set-time` 事件只更新 `currentTime` 不触发播放。
3. **右键菜单事件名**: CustomEvent 名使用 `closeallcontextmenus`（无连字符），避免 DOM 事件命名冲突。
4. **Toast 事件传递**: SegmentBlocksLayer 不直接引用 toast composable，应通过 emit 向父级传递，最终由 WorkspacePage 显示 toast。

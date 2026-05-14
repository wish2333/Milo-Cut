# Milo-Cut Frontend Implementation Guide

基于 Vue 3 + TypeScript + TailwindCSS v4 + DaisyUI v5 的前端落地指导，将 design-spec.md 和 component-spec.md 中的设计规范转化为可执行的代码结构。

本指南基于对 **PyWebVue 框架源码** 和 **ff-intelligent-neo 参考项目前端** 的深度分析编写，所有模式均有实际代码依据。

---

## 1. PyWebVue Bridge 通信层

### 1.1 通信架构

PyWebVue 采用 **轮询架构**，而非 WebSocket。核心是一个 50ms 间隔的 `tick()` 调用：

```
Frontend (Vue/TS)                          Backend (Python)
===================                        =================

call("greet", "Alice")  ------RPC------>  @expose greet(self, name)
  await response         <---JSON-------  returns {"success": True, "data": "Hello, Alice!"}

                              (background thread)
                              app.emit("progress", {pct: 50})
                                |
                                v
                              _event_queue.put(("progress", {pct: 50}))

tick() (every 50ms)  ------RPC------>  tick():
                                           _flush_events()
                                             -> evaluate_js: dispatchEvent("pywebvue:progress")
  onEvent("progress", ...)  <---DOM---
                                           _execute_next_task()
```

**关键约束：**
- 所有 Python -> JS 通信都通过 `tick()` 轮询分发，事件非即时到达（最大延迟 ~50ms）
- `_emit()` 可从任意线程调用（线程安全），事件进入 `queue.Queue` 等待 `tick()` 刷新
- 每次tick仅执行一个pending task，避免阻塞

### 1.2 bridge.ts 核心（直接复用）

```typescript
// bridge.ts -- 从 ff-intelligent-neo 验证的生产级实现

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
}

const BRIDGE_CALL_TIMEOUT_MS = 30_000

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`Bridge call timed out after ${ms}ms`)), ms)
    ),
  ])
}

function getRawApi(): PyWebViewApi {
  const pw = window.pywebview
  if (!pw || !pw.api) {
    throw new Error("pywebview API not available. Wait for pywebview to initialize.")
  }
  return pw.api
}

/** 等待 pywebview bridge 就绪 */
export function waitForPyWebView(timeout = 10_000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now()
    const check = () => {
      try {
        const api = window.pywebview?.api
        if (api && typeof (api as any).create_project === "function") {
          resolve()
          return
        }
      } catch { /* api might not be fully ready */ }
      if (Date.now() - start > timeout) {
        reject(new Error("pywebview bridge did not initialize within timeout"))
        return
      }
      setTimeout(check, 100)
    }
    check()
  })
}

/** 调用 @expose 装饰的 Python 方法 */
export async function call<T = unknown>(
  method: string,
  ...args: unknown[]
): Promise<ApiResponse<T>> {
  const api = getRawApi()
  const fn = api[method as keyof typeof api]
  if (typeof fn !== "function") {
    return { success: false, error: `Method '${method}' not found on bridge` }
  }
  return withTimeout(fn(...args) as Promise<ApiResponse<T>>, BRIDGE_CALL_TIMEOUT_MS)
}

/** 监听 Python 端 Bridge._emit() 推送的事件，返回清理函数 */
export function onEvent<T = unknown>(
  name: string,
  handler: (detail: T) => void,
): () => void {
  const event = `pywebvue:${name}`
  const listener = (e: Event) => {
    handler((e as CustomEvent).detail)
  }
  window.addEventListener(event, listener)
  return () => window.removeEventListener(event, listener)
}
```

### 1.3 useBridge -- 组件级事件生命周期管理

来自 ff-intelligent-neo 的验证模式，自动在组件卸载时清理事件监听：

```typescript
// composables/useBridge.ts
import { onUnmounted } from "vue"

type EventCallback = (detail: unknown) => void

export function useBridge() {
  const _listeners: Array<{ event: string; handler: EventListener }> = []

  function on(event: string, callback: EventCallback): void {
    const wrapped: EventListener = (e: Event) => {
      callback((e as CustomEvent).detail)
    }
    window.addEventListener(`pywebvue:${event}`, wrapped)
    _listeners.push({ event, handler: wrapped })
  }

  function off(event: string): void {
    const idx = _listeners.findIndex((l) => l.event === event)
    if (idx !== -1) {
      window.removeEventListener(`pywebvue:${_listeners[idx].event}`, _listeners[idx].handler)
      _listeners.splice(idx, 1)
    }
  }

  function cleanup(): void {
    for (const { event, handler } of _listeners) {
      window.removeEventListener(`pywebvue:${event}`, handler)
    }
    _listeners.length = 0
  }

  onUnmounted(cleanup)
  return { on, off, cleanup }
}
```

### 1.4 事件常量（前后端同步）

```typescript
// utils/events.ts -- 必须与后端 core/events.py 保持一致

// 任务生命周期
export const EVENT_TASK_PROGRESS = "task:progress"
export const EVENT_TASK_COMPLETED = "task:completed"
export const EVENT_TASK_FAILED = "task:failed"

// 项目级
export const EVENT_PROJECT_SAVED = "project:saved"
export const EVENT_PROJECT_DIRTY = "project:dirty"

// 分析结果
export const EVENT_ANALYSIS_UPDATED = "analysis:updated"

// 日志转发
export const EVENT_LOG_LINE = "log_line"
```

### 1.5 拖拽文件获取

PyWebVue 内置了文件拖拽支持，通过 `get_dropped_files()` 获取：

```typescript
async function getDroppedFiles(): Promise<string[]> {
  const res = await call<string[]>("get_dropped_files")
  return res.success && res.data ? res.data : []
}
```

---

## 2. 样式底层：TailwindCSS v4 变量配置

TailwindCSS v4 以 CSS 变量为核心。在主 CSS 文件中定义 Apple 风格令牌与 Milo-Cut 状态色。

```css
@theme {
  /* Apple 基础色 */
  --color-primary: #0066cc;        /* Action Blue */
  --color-canvas: #ffffff;
  --color-parchment: #f5f5f7;
  --color-ink: #1d1d1f;
  --color-ink-muted: #86868b;
  --color-ink-muted-48: #6e6e73;
  --color-hairline: #d2d2d7;
  --color-surface-tile-1: #272729;

  /* Milo-Cut 业务状态色 */
  --color-status-pending: #fff9e6;
  --color-status-confirmed: #fef2f2;
  --color-status-rejected: #f0fdf4;
  --color-status-warning: #dc2626;

  /* 字体规范 */
  --font-apple: "OPPO Sans 4.0", "Source Sans Pro", sans-serif;
  --tracking-tight: -0.022em;

  /* 圆角规范 */
  --radius-apple-lg: 18px;
  --radius-apple-pill: 9999px;
  --radius-apple-sm: 8px;
}
```

---

## 3. DaisyUI v5 主题定制

利用 DaisyUI 的 theme 插件封装 Apple Light/Dark Tile 逻辑。

```typescript
// tailwind.config.ts (DaisyUI v5 主题配置)
export default {
  daisyui: {
    themes: [
      {
        appleLight: {
          "primary": "#0066cc",
          "primary-content": "#ffffff",
          "base-100": "#ffffff",
          "base-200": "#f5f5f7",
          "base-300": "#e8e8ed",
          "neutral": "#1d1d1f",
          "rounded-btn": "9999px",
        },
      },
    ],
  },
}
```

---

## 4. TypeScript 类型定义

### 4.1 核心数据模型

类型定义必须与后端 `project.json` 的 schema 和 Bridge API 返回值严格对齐。

```typescript
// types/project.ts

/** 编辑状态：对应 PRD 状态机 */
export type EditStatus = 'pending' | 'confirmed' | 'rejected'

/** 片段类型：字幕段或静音段 */
export type SegmentType = 'subtitle' | 'silence'

/** 字幕段/静音段统一结构（对应 project.json 的 transcript.segments）
 *  注意：status 和 source 字段不属于后端 Segment，而是前端本地维护的编辑状态。
 *  后端 Segment 只有 type/start/end/text/words/speaker/dirtyFlags。
 */
export interface Segment {
  id: string
  version: number
  type: SegmentType
  start: number       // 秒
  end: number         // 秒
  text: string        // 字幕文本或 "静音 N.Ns"
  words?: Word[]      // 词级时间戳（ASR 产出）
  speaker: string | null
  dirtyFlags?: {
    textChanged: boolean
    timeChanged: boolean
    analysisStale: boolean
  }
}

/** 前端扩展的编辑状态（不在后端 Segment 中，前端本地管理） */
export interface SegmentEditState {
  status: EditStatus
  source?: string     // 来源：auto_silence / auto_filler / auto_error / user
  analysisId?: string
}

export interface Word {
  word: string
  start: number
  end: number
  confidence: number
}

/** 分析结果（对应 project.json 的 analysis） */
export interface AnalysisResult {
  id: string
  type: 'silence' | 'filler' | 'error' | 'repetition'
  segmentIds: string[]
  confidence: number
  detail: string
}

/** 编辑决策（对应 project.json 的 edits） */
export interface EditDecision {
  id: string
  start: number
  end: number
  action: 'delete' | 'keep'
  source: string
  analysisId?: string
  status: EditStatus
  priority: number  // 自动建议=100, 用户手动=200
}

/** 项目完整结构（对应 project.json） */
export interface Project {
  schemaVersion: string
  project: ProjectMeta
  media: MediaInfo
  transcript: TranscriptData
  analysis: AnalysisData
  edits: EditDecision[]
}

export interface ProjectMeta {
  name: string
  createdAt: string
  updatedAt: string
}

export interface MediaInfo {
  path: string
  mediaHash: string
  duration: number
  format: string
  width: number
  height: number
  fps: number
  audioChannels: number
  sampleRate: number
  bitRate: number
  proxyPath: string | null
  waveformPath: string | null
}

export interface TranscriptData {
  engine: string
  language: string
  segments: Segment[]
}

export interface AnalysisData {
  lastRun: string | null
  silenceSegments: SilenceSegment[]
  fillerHits: FillerHit[]
  errorPatterns: ErrorPattern[]
  repetitions: Repetition[]
}

export interface SilenceSegment {
  id: string
  start: number
  end: number
  duration: number
  confidence: number
}

export interface FillerHit {
  id: string
  segmentId: string
  text: string
  type: string
}

export interface ErrorPattern {
  id: string
  segmentIds: string[]
  type: string
  confidence: number
  trigger: string
}

export interface Repetition {
  id: string
  segmentIds: string[]
  similarity: number
}
```

### 4.2 统一任务模型

```typescript
// types/task.ts

export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

/** Milo-Cut 统一任务（PRD Appendix C） */
export interface TaskProgress {
  percent: number       // 0-100
  message: string
}

/** Milo-Cut 统一任务（PRD Appendix C） */
export interface MiloTask {
  id: string
  type: TaskType
  status: TaskStatus
  progress: TaskProgress
  payload: Record<string, unknown>
  result?: unknown
  error?: string
  createdAt: string
  startedAt?: string
  completedAt?: string
}

/** 任务类型枚举（MVP/P1 分离） */
export type TaskType =
  // MVP
  | 'silence_detection'
  | 'filler_detection'
  | 'error_detection'
  | 'full_analysis'
  | 'export_video'
  | 'export_subtitle'
  // P1
  | 'transcription'
  | 'repetition_detection'
  | 'vad_analysis'
  | 'waveform_generation'
  | 'proxy_generation'
  | 'export_timeline'
```

### 4.3 Bridge API 响应类型

```typescript
// types/api.ts

export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  code?: string
}

/** 所有 Bridge 方法名（供 call() 的 method 参数使用） */
export type BridgeMethod =
  // 项目管理
  | 'create_project'
  | 'open_project'
  | 'save_project'
  | 'close_project'
  | 'get_recent_projects'
  // 统一任务
  | 'create_task'
  | 'start_task'
  | 'cancel_task'
  | 'get_task'
  | 'list_tasks'
  // 字幕编辑
  | 'update_segment_text'
  | 'merge_segments'
  | 'split_segment'
  | 'search_replace'
  // 编辑决策
  | 'mark_segments'
  | 'confirm_all_suggestions'
  | 'reject_all_suggestions'
  | 'get_edit_summary'
  // 系统
  | 'select_files'
  | 'select_file'
  | 'open_folder'
  | 'get_app_info'
  | 'get_dropped_files'
```

---

## 5. Composables 设计

所有 composable 遵循 ff-intelligent-neo 验证的模式：
- 使用 `useBridge()` 管理事件监听生命周期
- 调用 `call()` 与后端通信
- 使用 Vue `ref`/`computed` 管理本地状态
- 事件驱动的状态更新（后端 emit -> 前端 onEvent -> 更新 ref）

### 5.1 useProject

```typescript
// composables/useProject.ts
import { ref, computed } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { EVENT_PROJECT_DIRTY, EVENT_PROJECT_SAVED } from "@/utils/events"
import type { Project } from "@/types/project"

export function useProject() {
  const { on } = useBridge()
  const project = ref<Project | null>(null)
  const isDirty = ref(false)
  const loading = ref(false)

  const segments = computed(() =>
    project.value?.transcript.segments ?? []
  )

  const edits = computed(() =>
    project.value?.edits ?? []
  )

  const mediaDuration = computed(() =>
    project.value?.media.duration ?? 0
  )

  async function createProject(name: string, mediaPath: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("create_project", name, mediaPath)
      if (res.success && res.data) {
        project.value = res.data
        isDirty.value = false
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function openProject(projectPath: string): Promise<boolean> {
    loading.value = true
    try {
      const res = await call<Project>("open_project", projectPath)
      if (res.success && res.data) {
        project.value = res.data
        isDirty.value = false
        return true
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function saveProject(): Promise<boolean> {
    if (!project.value) return false
    const res = await call("save_project")
    if (res.success) {
      isDirty.value = false
    }
    return res.success
  }

  async function closeProject(): Promise<boolean> {
    const res = await call("close_project")
    if (res.success) {
      project.value = null
      isDirty.value = false
    }
    return res.success
  }

  // 事件监听：后端保存后同步前端状态
  on(EVENT_PROJECT_SAVED, () => { isDirty.value = false })
  on(EVENT_PROJECT_DIRTY, () => { isDirty.value = true })

  return {
    project, isDirty, loading, segments, edits, mediaDuration,
    createProject, openProject, saveProject, closeProject,
  }
}
```

### 5.2 useTask -- 统一任务管理

这是 Milo-Cut 的核心 composable，管理所有长耗时任务（分析、导出等）：

```typescript
// composables/useTask.ts
import { ref, computed } from "vue"
import { call } from "@/bridge"
import { useBridge } from "./useBridge"
import { EVENT_TASK_PROGRESS, EVENT_TASK_COMPLETED, EVENT_TASK_FAILED } from "@/utils/events"
import type { MiloTask, TaskType, TaskStatus } from "@/types/task"

interface TaskProgressPayload {
  task_id: string
  progress: { percent: number; message: string }
}

interface TaskResultPayload {
  task_id: string
  result: unknown
}

interface TaskErrorPayload {
  task_id: string
  error: string
  code: string
}

export function useTask() {
  const { on } = useBridge()
  const tasks = ref<MiloTask[]>([])
  const activeTask = ref<MiloTask | null>(null)

  const isRunning = computed(() =>
    tasks.value.some(t => t.status === 'running')
  )

  async function createTask(type: TaskType, payload: Record<string, unknown>): Promise<MiloTask | null> {
    const res = await call<MiloTask>("create_task", type, payload)
    if (res.success && res.data) {
      tasks.value = [...tasks.value, res.data]
      return res.data
    }
    return null
  }

  async function startTask(taskId: string): Promise<boolean> {
    const res = await call("start_task", taskId)
    if (res.success) {
      const idx = tasks.value.findIndex(t => t.id === taskId)
      if (idx !== -1) {
        const updated = [...tasks.value]
        updated[idx] = { ...updated[idx], status: 'running' }
        tasks.value = updated
        activeTask.value = updated[idx]
      }
    }
    return res.success
  }

  async function cancelTask(taskId: string): Promise<boolean> {
    const res = await call("cancel_task", taskId)
    return res.success
  }

  async function getTask(taskId: string): Promise<MiloTask | null> {
    const res = await call<MiloTask>("get_task", taskId)
    return res.success && res.data ? res.data : null
  }

  async function listTasks(): Promise<MiloTask[]> {
    const res = await call<MiloTask[]>("list_tasks")
    if (res.success && res.data) {
      tasks.value = res.data
    }
    return res.success && res.data ? res.data : []
  }

  // 事件驱动更新
  on(EVENT_TASK_PROGRESS, (detail: unknown) => {
    const { task_id, progress } = detail as TaskProgressPayload
    const idx = tasks.value.findIndex(t => t.id === task_id)
    if (idx !== -1) {
      const updated = [...tasks.value]
      updated[idx] = { ...updated[idx], progress }
      tasks.value = updated
      if (activeTask.value?.id === task_id) {
        activeTask.value = updated[idx]
      }
    }
  })

  on(EVENT_TASK_COMPLETED, (detail: unknown) => {
    const { task_id, result } = detail as TaskResultPayload
    const idx = tasks.value.findIndex(t => t.id === task_id)
    if (idx !== -1) {
      const updated = [...tasks.value]
      updated[idx] = { ...updated[idx], status: 'completed', result }
      tasks.value = updated
      if (activeTask.value?.id === task_id) {
        activeTask.value = updated[idx]
      }
    }
  })

  on(EVENT_TASK_FAILED, (detail: unknown) => {
    const { task_id, error } = detail as TaskErrorPayload
    const idx = tasks.value.findIndex(t => t.id === task_id)
    if (idx !== -1) {
      const updated = [...tasks.value]
      updated[idx] = { ...updated[idx], status: 'failed', error }
      tasks.value = updated
      if (activeTask.value?.id === task_id) {
        activeTask.value = updated[idx]
      }
    }
  })

  return {
    tasks, activeTask, isRunning,
    createTask, startTask, cancelTask, getTask, listTasks,
  }
}
```

### 5.3 useTranscript -- 字幕数据操作

```typescript
// composables/useTranscript.ts
import { call } from "@/bridge"
import type { Segment } from "@/types/project"

export function useTranscript() {
  async function updateSegmentText(segmentId: string, text: string): Promise<boolean> {
    const res = await call("update_segment_text", segmentId, text)
    return res.success
  }

  async function mergeSegments(segmentIds: string[]): Promise<Segment | null> {
    const res = await call<Segment>("merge_segments", segmentIds)
    return res.success && res.data ? res.data : null
  }

  async function splitSegment(segmentId: string, position: number): Promise<Segment[] | null> {
    const res = await call<Segment[]>("split_segment", segmentId, position)
    return res.success && res.data ? res.data : null
  }

  async function searchReplace(
    query: string,
    replacement: string,
    scope: string = "all",
  ): Promise<{ count: number } | null> {
    const res = await call<{ count: number }>("search_replace", query, replacement, scope)
    return res.success && res.data ? res.data : null
  }

  return { updateSegmentText, mergeSegments, splitSegment, searchReplace }
}
```

### 5.4 useAnalysis -- 分析任务

```typescript
// composables/useAnalysis.ts
import { call } from "@/bridge"
import type { AnalysisResult } from "@/types/project"
import type { MiloTask, TaskType } from "@/types/task"
import { useTask } from "./useTask"

export function useAnalysis() {
  const { createTask, startTask, tasks } = useTask()

  async function runAnalysis(
    type: TaskType,
    payload: Record<string, unknown>,
  ): Promise<MiloTask | null> {
    const task = await createTask(type, payload)
    if (task) {
      await startTask(task.id)
    }
    return task
  }

  async function runFullAnalysis(): Promise<MiloTask | null> {
    return runAnalysis("full_analysis", {})
  }

  async function runSilenceDetection(): Promise<MiloTask | null> {
    return runAnalysis("silence_detection", {})
  }

  return { runAnalysis, runFullAnalysis, runSilenceDetection, tasks }
}
```

### 5.5 useExportCheck

```typescript
// composables/useExportCheck.ts
import { computed, type Ref } from "vue"
import type { EditDecision, Segment } from "@/types/project"

function checkSequentialDelete(segments: Segment[], threshold: number): boolean {
  let count = 0
  for (const s of segments) {
    if (s.status === 'confirmed') {
      count++
      if (count >= threshold) return true
    } else {
      count = 0
    }
  }
  return false
}

export function useExportCheck(segments: Ref<Segment[]>, totalDuration: Ref<number>) {
  const deletedSegments = computed(() =>
    segments.value.filter(s => s.status === 'confirmed')
  )

  const deletedDuration = computed(() =>
    deletedSegments.value.reduce((acc, s) => acc + (s.end - s.start), 0)
  )

  const resultDuration = computed(() => totalDuration.value - deletedDuration.value)

  const deleteRatio = computed(() =>
    totalDuration.value > 0
      ? (deletedDuration.value / totalDuration.value * 100)
      : 0
  )

  const safetyChecks = computed(() => ({
    isOverLimit: deleteRatio.value > 40,
    hasLongSegment: deletedSegments.value.some(s => (s.end - s.start) > 60),
    hasSequentialDelete: checkSequentialDelete(segments.value, 3),
  }))

  const canExport = computed(() =>
    deletedSegments.value.length > 0 && !safetyChecks.value.isOverLimit
  )

  return {
    deletedSegments, deletedDuration, resultDuration,
    deleteRatio, safetyChecks, canExport,
  }
}
```

### 5.6 usePlayer

```typescript
// composables/usePlayer.ts
import { ref } from "vue"
import { onMounted } from "vue"

export function usePlayer() {
  const currentTime = ref(0)
  const isPlaying = ref(false)
  const isCutPreview = ref(false) // Shift+Space 切换

  const seekTo = (time: number) => { currentTime.value = time }

  const togglePreviewMode = () => { isCutPreview.value = !isCutPreview.value }

  onMounted(() => {
    window.addEventListener('keydown', (e) => {
      if (e.shiftKey && e.code === 'Space') {
        e.preventDefault()
        togglePreviewMode()
      }
    })
  })

  return { currentTime, isPlaying, isCutPreview, seekTo, togglePreviewMode }
}
```

### 5.7 useKeyboard

```typescript
// composables/useKeyboard.ts
import { onMounted, onUnmounted } from "vue"

type KeyHandler = (e: KeyboardEvent) => void

export function useKeyboard() {
  const handlers: KeyHandler[] = []

  function register(handler: KeyHandler): void {
    handlers.push(handler)
  }

  function onKeyDown(e: KeyboardEvent): void {
    for (const handler of handlers) {
      handler(e)
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeyDown))
  onUnmounted(() => window.removeEventListener('keydown', onKeyDown))

  return { register }
}
```

---

## 6. 组件实现示例

### 6.1 TranscriptRow.vue

```vue
<script setup lang="ts">
import type { Segment, EditStatus } from '@/types/project'

const props = defineProps<{ segment: Segment }>()
const emit = defineEmits<{
  'update:status': [status: EditStatus]
  'seek': [time: number]
}>()

const statusClasses: Record<EditStatus, string> = {
  pending: 'bg-status-pending border-l-[3px] border-l-yellow-400',
  confirmed: 'bg-status-confirmed border-l-[3px] border-l-red-400 line-through opacity-60',
  rejected: 'bg-status-rejected border-l-[3px] border-l-green-400',
}

const cycleStatus = () => {
  const next: Record<EditStatus, EditStatus> = {
    pending: 'confirmed',
    confirmed: 'rejected',
    rejected: 'pending',
  }
  emit('update:status', next[props.segment.status])
}

const handleClick = () => emit('seek', props.segment.start)
</script>

<template>
  <div
    class="flex items-center px-4 py-3 transition-all duration-300 ease-in-out
           cursor-pointer active:scale-[0.99] select-none"
    :class="[statusClasses[segment.status]]"
    @click="handleClick"
    @keydown.delete="cycleStatus"
    tabindex="0"
  >
    <span class="font-mono text-xs text-ink-muted shrink-0 w-16">
      {{ formatTime(segment.start) }}
    </span>
    <p class="text-[17px] tracking-tight leading-[1.47] flex-1">
      {{ segment.text }}
    </p>
    <span v-if="segment.status !== 'pending'" class="text-xs font-semibold ml-2">
      {{ statusLabel }}
    </span>
  </div>
</template>
```

### 6.2 SilenceSegment.vue

```vue
<script setup lang="ts">
import type { Segment } from '@/types/project'

const props = defineProps<{ segment: Segment }>()
const emit = defineEmits<{
  'resize': [id: string, newStart: number, newEnd: number]
}>()

const isResizing = ref(false)
</script>

<template>
  <div
    class="flex items-center justify-center h-8 bg-parchment transition-all duration-300
           relative group select-none"
    :class="{
      'bg-status-pending': segment.status === 'pending',
      'bg-status-confirmed': segment.status === 'confirmed',
      'bg-status-rejected': segment.status === 'rejected',
    }"
  >
    <span class="text-xs text-ink-muted font-mono">
      {{ (segment.end - segment.start).toFixed(1) }}s
    </span>
    <div class="absolute left-0 top-0 w-1 h-full cursor-col-resize
                opacity-0 group-hover:opacity-100 bg-primary transition-opacity" />
    <div class="absolute right-0 top-0 w-1 h-full cursor-col-resize
                opacity-0 group-hover:opacity-100 bg-primary transition-opacity" />
  </div>
</template>
```

### 6.3 ExportSummaryModal.vue

```vue
<script setup lang="ts">
import type { Segment } from '@/types/project'
import { useExportCheck } from '@/composables/useExportCheck'

const props = defineProps<{ segments: Segment[]; totalDuration: number }>()
const emit = defineEmits<{ 'confirm': []; 'cancel': [] }>()

const { deletedDuration, resultDuration, deleteRatio, safetyChecks } =
  useExportCheck(toRef(props, 'segments'), toRef(props, 'totalDuration'))

const exportMode = ref<'precise' | 'fast'>('precise')
</script>
```

---

## 7. 项目文件结构

```
frontend/
  src/
    types/
      project.ts            -- 核心数据模型 (Segment, EditDecision, Project)
      task.ts               -- 统一任务模型 (MiloTask, TaskType, TaskStatus)
      api.ts                -- Bridge API 响应类型 + BridgeMethod 联合类型
    utils/
      events.ts             -- 事件常量 (与后端 core/events.py 同步)
      format.ts             -- 时间格式化、文件大小格式化
      logger.ts             -- 前端日志 (可选，对接后端 log_line 事件)
    composables/
      useBridge.ts          -- 事件监听生命周期管理 (onUnmounted 自动清理)
      useProject.ts         -- 项目状态管理 (CRUD, dirty tracking, 事件同步)
      useTask.ts            -- 统一任务管理 (create, start, cancel, 进度事件)
      useTranscript.ts      -- 字幕数据操作 (导入SRT, 合并, 拆分, 搜索替换)
      useAnalysis.ts        -- 分析结果管理 (运行检测, 状态同步)
      usePlayer.ts          -- 播放器控制 (播放, 跳转, 原片/剪后切换)
      useExport.ts          -- 导出逻辑 (安全校验, 双模式, 进度)
      useExportCheck.ts     -- 导出安全检查 (三道保险计算)
      useKeyboard.ts        -- 快捷键注册与管理
    components/
      workspace/
        TranscriptRow.vue       -- 字幕行组件 (状态切换, inline编辑)
        SilenceSegment.vue      -- 静音隔离条 (resize, 同步)
        VideoPlayer.vue         -- 视频预览 (字幕叠加, 对比模式)
        WaveformView.vue        -- 波形视图 (P1)
        SuggestionPanel.vue     -- 建议面板 (分组, 批量操作)
        StepController.vue      -- 步骤控制器
        ExportSummaryModal.vue  -- 导出摘要弹窗
      common/
        FileDropInput.vue       -- 拖拽导入
        ProgressBar.vue         -- 进度条
        PillToggle.vue          -- 模式切换 (精确/快速)
    pages/
      WelcomePage.vue           -- 欢迎页
      WorkspacePage.vue         -- 主工作台
      ExportPage.vue            -- 导出页
    bridge.ts                   -- PyWebVue Bridge 封装 (call, onEvent, waitForPyWebView)
    main.ts                     -- Vue 入口
    App.vue                     -- 根组件
  package.json
  tsconfig.json
  vite.config.ts
  index.html
```

---

## 8. 应用初始化

```typescript
// main.ts
import { createApp } from 'vue'
import { waitForPyWebView } from './bridge'
import App from './App.vue'

async function bootstrap() {
  // 等待 PyWebVue bridge 就绪
  await waitForPyWebView()
  const app = createApp(App)
  app.mount('#app')
}

bootstrap().catch((err) => {
  console.error('Failed to initialize:', err)
  document.body.innerHTML = `
    <div style="padding:40px;text-align:center;font-family:sans-serif">
      <h1>Milo-Cut</h1>
      <p>Failed to initialize. Please restart the application.</p>
      <pre>${err.message}</pre>
    </div>
  `
})
```

---

## 9. 开发要点

### 交互动效
- 所有按钮绑定 `active:scale-95`（对应 design-spec 的 `transform: scale(0.95)`）
- 状态切换使用 `transition-all duration-300 ease-in-out`
- 导出弹窗使用 `scale(0.95) -> scale(1) + opacity` 入场动画

### 本地优先架构
- 前端通过 PyWebVue Bridge 的 `call()` 调用 Python 后端
- 所有长任务通过 `create_task` / `start_task` 提交，通过 `onEvent` 接收进度
- 项目状态在前端 Vue reactive 系统中管理，每次操作后自动触发 Bridge `save_project`
- Bridge 调用有 30s 超时保护（`withTimeout`）

### 事件驱动状态更新
- 后端状态变更通过 `emit()` -> `tick()` -> `CustomEvent` 链路推送到前端
- 前端通过 `useBridge()` 的 `on()` 注册监听，`onUnmounted` 自动清理
- 避免轮询：不要用 `setInterval` 模拟实时更新，直接用事件系统

### 静音+字幕同步
- segments 数组中字幕段和静音段混合存储，按 start 时间排序
- 渲染时统一遍历，根据 type 字段决定使用 TranscriptRow 或 SilenceSegment 组件
- resize 静音段时，相邻字幕段的 start/end 实时联动更新

### 快捷键
- 全局快捷键通过 `useKeyboard` composable 统一注册
- 编辑器聚焦时拦截 Space/Delete 等按键，避免与全局冲突
- Shift+Space 的原片/剪后切换在 usePlayer 中实现

### 开发模式
- `bun install` 安装依赖，`bun run dev` 启动 Vite dev server（HMR）
- PyWebVue 自动检测 dev 模式，从 `http://localhost:5173` 加载前端
- 后端 `main.py` 需要同时运行：`uv run main.py`

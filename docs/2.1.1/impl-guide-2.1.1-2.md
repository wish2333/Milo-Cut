# v2.1.1 第 2 轮检查问题 — 落地实施指南

> 配套文档: `docs/2.1.1/fix-report-2.1.1-2.md`（根因分析）
> 分支: `dev-2.1.1`    日期: 2026-06-24
> 审查人签核: 已通过

本指南将修复报告的"修复方案"章节转化为可直接 copy-paste 的代码实现级指南。

---

## P0 级别修复（阻塞主流程）

### 1. C-1.1 智能删除无结果返回（前端状态同步）

**实施建议**: 短期方案采用**回调注入**触发 `refreshProject`，避免立刻重构 Pinia 带来的回归风险。

**修改 `frontend/src/composables/useLlmTasks.ts`**:

```typescript
// 新增入参，由外部注入 refreshProject 方法
export function useLlmTasks(refreshProject: () => Promise<void>) {
  // ...
  onEvent<{ results?: SmartDeleteResult[] }>(
    EVENT_LLM_SMART_DELETE_COMPLETED,
    async (detail) => {
      isRunning.value = false
      if (detail?.results) {
        smartDeleteResults.value = detail.results
      }
      // Fix C-1.1: 主动拉取最新 Project，触发 WorkspacePage 重新计算 analysisResults
      await refreshProject()
    },
  )

  // P1 字幕修正完成也需补充
  onEvent(EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED, async (detail) => {
    isRunning.value = false
    if (detail) {
      subtitleCorrectionResult.value = detail
    }
    await refreshProject()
  })

  // P2 精华提取完成也需补充
  onEvent(EVENT_LLM_HIGHLIGHT_COMPLETED, async (detail) => {
    isRunning.value = false
    if (detail?.results) {
      highlightResults.value = detail.results
    }
    if (detail?.total_duration !== undefined) {
      highlightTotalDuration.value = detail.total_duration
    }
    if (detail?.target_duration !== undefined) {
      highlightTargetDuration.value = detail.target_duration
    }
    await refreshProject()
    // 原有的 detect_highlight_jump_cuts 调用保留
    call<{ jump_cuts?: JumpCut[]; highlight_count?: number }>(
      "detect_highlight_jump_cuts",
    ).then((res) => {
      if (res.success && res.data?.jump_cuts) {
        jumpCuts.value = res.data.jump_cuts
      }
    })
  })
}
```

> **注意**: 当前 `useLlmTasks` 的导出签名是无参的 `export function useLlmTasks()`，改为接收回调会破坏所有调用点。实施时建议：
> - 方案 A（侵入小）: 改为 `useLlmTasks(options?: { refreshProject?: () => Promise<void> })`
> - 方案 B（架构优）: 在 composable 内部维护一个 `refreshProjectHandler` ref，通过单独的 `setRefreshProjectHandler(fn)` 注册
> - 方案 C（推荐）: 直接在 `WorkspacePage.vue` 的 `onEvent(EVENT_LLM_SMART_DELETE_COMPLETED)` 里调 refreshProject，不侵入 composable

---

### 2. A-2.1 字幕高亮联动 & 右键菜单收敛

**修改 `Timeline.vue`（计算属性 & 模板）**:

```vue
<script setup>
const highlightedSegmentId = ref<string | null>(null)

// 计算 playhead 所在的段 ID
const playheadSegmentId = computed(() => {
  const t = props.currentTime ?? 0
  return props.segments.find(
    s => s.type === 'subtitle' && t >= s.start && t <= s.end
  )?.id ?? null
})

// SuggestionPanel 联动处理
function handleSeekSuggestion(time: number, segmentId?: string) {
  emit('seek-suggestion', time)
  if (segmentId) {
    highlightedSegmentId.value = segmentId
    setTimeout(() => { highlightedSegmentId.value = null }, 2000)
  }
}

// 滚动到指定 segment
function scrollTranscriptRowIntoView(segmentId: string) {
  const el = listContainer.value?.querySelector(
    `[data-segment-id="${segmentId}"]`
  ) as HTMLElement | null
  el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}
</script>

<template>
  <TranscriptRow
    v-for="seg in segments"
    v-memo="[
      seg,
      getSegmentState(seg).displayStatus,
      selectedSegmentIds?.has(seg.id) ?? false,
      selectedSegmentId === seg.id,
      seg.id === playheadSegmentId,
      seg.id === highlightedSegmentId,
      globalEditMode,
      selectionMode
    ]"
    :is-playhead-inside="seg.id === playheadSegmentId"
    :is-highlighted="seg.id === highlightedSegmentId"
    @scroll-into-view="scrollTranscriptRowIntoView(seg.id)"
  />
</template>
```

**修改 `TranscriptRow.vue`（模板与脚本）**:

```vue
<script setup>
const props = defineProps<{
  segment: Segment
  // ... 原有 props ...
  isPlayheadInside?: boolean
  isHighlighted?: boolean
}>()
</script>

<template>
  <div
    :class="[
      statusClass,
      {
        'ring-2 ring-blue-500 bg-blue-50': isMultiSelected,
        'ring-1 ring-blue-500': isSelected && !isMultiSelected,
        'bg-blue-50 border-l-2 border-blue-400': isPlayheadInside && !isSelected && !isMultiSelected,
        'ring-2 ring-yellow-400 bg-yellow-50 transition-colors duration-1000': isHighlighted,
      }
    ]"
  >
    <!-- ... -->
  </div>

  <!-- 右键菜单: 仅 playhead 在范围内时才显示「从指针分割」 -->
  <button v-if="isPlayheadInside" @click="handleSplitAtPointer">
    从时间指针分割
  </button>
</template>
```

---

## P1 级别修复（核心交互与数据正确性）

### 3. A-2.4 分割字幕的 EditDecision 切割（Python 后端）

**修改 `core/project_service.py:split_segment`（第 917-919 行起）**:

```python
new_edits = []
for edit in self.active_timeline.edits:
    # 1. 针对拥有 _segment_ids 的 ED（如 LLM Smart Delete）
    if hasattr(edit, '_segment_ids') and segment_id in edit._segment_ids:
        # 为 A 和 B 各自 copy 一份
        for new_id in (f"{segment_id}-a", f"{segment_id}-b"):
            new_edits.append(edit.model_copy(update={
                "id": f"{edit.id}__{new_id}",
                "_segment_ids": [new_id],
            }))
        continue  # 原 ED 丢弃

    # 2. 针对 Rule-based / 时间范围型 ED（依赖 start_time / end_time）
    if hasattr(edit, 'start_time') and hasattr(edit, 'end_time'):
        # 判断 ED 的时间范围是否与当前被切的 Segment 发生重叠
        if edit.start_time < target.end and edit.end_time > target.start:
            # 只有 ED 跨越了 position 才需要切断
            if edit.start_time < position < edit.end_time:
                # 绑给 A 的左半截
                new_edits.append(edit.model_copy(update={
                    "id": f"{edit.id}_a",
                    "end_time": position,
                }))
                # 绑给 B 的右半截
                new_edits.append(edit.model_copy(update={
                    "id": f"{edit.id}_b",
                    "start_time": position,
                }))
                continue  # 原 ED 丢弃
            # ED 范围完全落在 position 一侧（不跨越），保留原样即可
            # 因为时间范围型 ED 不依赖 segment_id，范围本身已能正确匹配 a 或 b

    # 其他不相干的 ED 或未命中切割逻辑的 ED，直接保留
    new_edits.append(edit)
```

> **实施验证点**:
> - 实施时建议先打印 `[e.model_dump() for e in self.active_timeline.edits]` 确认 rule-based ED 实际字段名是 `start_time/end_time` 还是其他（如 `range_start/range_end`）
> - 若字段名不同，调整 hasattr 检查条件

---

### 4. A-2.2 拖选文字超出框外异常退出

**修改 `TranscriptRow.vue`**:

```typescript
// HACK: 拖选文字时光标可能滑出 input 边界触发 blur，
// 此时并非用户意图完成编辑，需延迟校验焦点是否真的离开所有 edit input。
// 若 150ms 内焦点回到任一 edit-text-input，视为拖选操作，忽略本次 blur。
function handleTextEditBlur() {
  if (props.globalEditMode) return

  setTimeout(() => {
    const active = document.activeElement
    // 如果焦点转移到了本页面的其他 edit-text-input（即用户仍在操作），视为拖选延伸，忽略
    if (active && active.tagName === 'INPUT' && active.classList.contains('edit-text-input')) {
      return
    }
    saveEdit()
  }, 150)
}
```

> **配套改动**: `<input>` 元素的 class 列表需追加 `edit-text-input` 标识类，以便上面的 `classList.contains('edit-text-input')` 能命中。
> ```vue
> <input class="edit-text-input w-full min-w-0 bg-white ..." />
> ```

---

### 5. A-4 TimelineSwitcher 消失问题（替换 window.confirm）

**修改 `WorkspacePage.vue`**:

在模板底部新增 DaisyUI Modal:

```vue
<dialog id="delete_timeline_modal" class="modal" ref="deleteModal">
  <div class="modal-box">
    <h3 class="font-bold text-lg">确认删除</h3>
    <p class="py-4">
      确定要删除时间线 "{{ timelineToDelete?.label }}" 吗？此操作无法撤销。
    </p>
    <div class="modal-action">
      <button class="btn" @click="closeDeleteModal">取消</button>
      <button class="btn btn-error" @click="executeDeleteTimeline">删除</button>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>关闭</button>
  </form>
</dialog>
```

在脚本中替换 `handleDeleteTimeline`:

```typescript
const deleteModal = ref<HTMLDialogElement | null>(null)
const timelineToDelete = ref<Timeline | null>(null)

function handleDeleteTimeline(timelineId: string) {
  // 不再使用 window.confirm，改为打开 modal
  timelineToDelete.value = props.project.timelines.find(t => t.id === timelineId) ?? null
  deleteModal.value?.showModal()
}

function closeDeleteModal() {
  deleteModal.value?.close()
  timelineToDelete.value = null
}

async function executeDeleteTimeline() {
  const id = timelineToDelete.value?.id
  closeDeleteModal()
  if (!id) return
  const res = await call<Project>("delete_timeline", id)
  if (res.success && res.data) {
    emit("project-updated", res.data)
    isDirty.value = true
    showToast("Timeline deleted", "success")
  } else {
    showToast(res.error ?? "Failed to delete timeline", "error")
  }
}
```

> **重命名路径**: 重命名的 inline input 失焦导致 dropdown 收起，需要在 TimelineSwitcher 内部维护 `dropdownOpen` 状态并在 rename 期间强制保持。DaisyUI dropdown 没有直接的 open-state API，建议改用 `<details>` 元素或自定义 dropdown 组件。

---

## P2 级别修复（布局与体验）

### 6. A-3 右侧栏 Overlay 改造

**修改 `Timeline.vue` 布局**:

```vue
<div class="relative flex flex-1 h-full overflow-hidden">
  <!-- 左侧: 永远占满宽度的 TranscriptRow 列表 -->
  <div ref="listContainer" class="flex-1 overflow-y-auto">...</div>

  <!-- 右上角: 悬浮折叠开关 -->
  <button
    class="absolute right-4 top-2 z-30 btn btn-sm btn-circle btn-ghost bg-white/80 shadow"
    @click="sidebarOpen = !sidebarOpen"
  >
    <PanelIcon v-if="!sidebarOpen" />
    <CloseIcon v-else />
  </button>

  <!-- 右侧: 滑动 Overlay 面板 -->
  <Transition
    enter-active-class="transition transform duration-200 ease-out"
    enter-from-class="translate-x-full"
    enter-to-class="translate-x-0"
    leave-active-class="transition transform duration-200 ease-in"
    leave-from-class="translate-x-0"
    leave-to-class="translate-x-full"
  >
    <div
      v-if="sidebarOpen"
      class="absolute right-0 top-0 bottom-0 w-80 bg-white shadow-2xl border-l border-gray-200 z-20 flex flex-col"
    >
      <!-- Tab header -->
      <div class="flex border-b border-gray-200 bg-gray-50">
        <button v-for="tab in tabs" :key="tab.key" ...>{{ tab.label }}</button>
      </div>
      <!-- Tab content -->
      <div class="flex-1 overflow-y-auto p-2">
        <SuggestionPanel v-show="activeTab === 'suggestion'" ... />
        <AIAssistantPanel v-show="activeTab === 'ai'" ... />
        <HighlightModeView v-show="activeTab === 'highlight'" ... />
      </div>
    </div>
  </Transition>
</div>
```

```typescript
const sidebarOpen = ref(false)  // 默认隐藏
```

---

## 未决问题最终裁决

| 编号 | 问题 | 裁决 |
|------|------|------|
| A-2.4 a | `_segment_ids` 覆盖度 | rule-based ED 确实没有 `_segment_ids`。按上面的 Python 修复代码引入 `start_time/end_time` 交叉判断即可兼容两类 |
| A-2.4 b | 时间范围型 ED 拆分 | **必须拆分**。强行丢弃会导致用户分析结果因一次无关拆分全部丢失，体验灾难 |
| A-3 | sidebar 持久化 | **v2.1.1 暂不实现**。默认 `false` 足够，留待 v2.1.2 引入 `vueuse` 的 `useLocalStorage` 时统筹处理 |
| A-4 | 删除 confirm 改造范围 | **局部替换**。本次仅替换 Timeline 删除。Segment 删除的 confirm 留待全局 `<GlobalConfirm />` 组件建立后统一迁移 |
| C-1.1 | refreshProject 触发链 | **方案 1（回调注入或 emit）**。中期（v2.1.2）必须将 Project 数据层提拔到 Pinia 统一管理 |

---

## 实施顺序建议

| 顺序 | 编号 | 优先级 | 理由 |
|------|------|--------|------|
| 1 | C-1.1 | P0 | 核心功能不可用，最先解决 |
| 2 | A-2.1 | P0 | 字幕编辑基础体验 |
| 3 | A-2.4 | P1 | 数据正确性，避免误删 |
| 4 | A-4 | P1 | 多 Timeline 管理体验 |
| 5 | A-2.2 | P1 | 编辑效率 |
| 6 | A-3 | P2 | 布局优化 |

---

## 实施注意事项

1. **useLlmTasks 签名变更**: 当前 `useLlmTasks()` 无参，改为接收回调会破坏所有调用点。推荐方案 C（在 WorkspacePage 内监听同一事件），不侵入 composable。
2. **rule-based ED 字段名**: Python 修复代码假设是 `start_time/end_time`，实施前需打印 `self.active_timeline.edits` 确认实际字段名，可能是 `range_start/range_end` 或其他。
3. **TranscriptRow edit-text-input class**: 为让 `handleTextEditBlur` 的 `classList.contains('edit-text-input')` 命中，需在 `<input>` class 列表追加该标识类。
4. **DaisyUI dropdown 强制保持打开**: DaisyUI 的 dropdown 没有直接的 `open` prop 控制，重命名场景需要自定义 dropdown 组件或用 `<details>` 元素替代。
5. **图标资源**: A-3 的 `PanelIcon` / `CloseIcon` 需要引入 SVG 资源，可从 `lucide-vue-next` 或 heroicons 取。

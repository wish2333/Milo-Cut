# v2.1.1 第 2 轮检查问题修复报告

> 基于 `docs/2.1.0/qa-checklist-2.1.0.md` 与 `docs/2.1.1/check-report-2.1.1-2.md`
> 分支: `dev-2.1.1`    日期: 2026-06-24
> 修复负责人: wish2333

---

## 评审优化记录（2026-06-24）

本报告经过一轮模块评审，关键优化决策已合并到各问题"修复方案/修复方向"章节。摘要：

| 编号 | 评审优化点 | 落地章节 |
|------|-----------|---------|
| A-2.1 | v-memo 依赖从 `currentTime` 改为 `isPlayheadInside` 布尔，避免播放期间整列表每帧重渲染 | §A-2.1 子需求 2 性能优化 |
| A-2.4 | 时间范围型 ED 按 split position 切割绑给 a/b（不丢弃），符合 NLE 直觉 | §A-2.4 修复方向 |
| A-2.2 | 保留 setTimeout 方案 A，但必须加注释说明 drag-out hack 意图 | §A-2.2 推荐选 A 后的注释要求 |
| A-4 | 强推荐把 `window.confirm` 换成应用内 Dialog/Modal（统一风格 + 解决焦点抢占） | §A-4 删除路径 |
| C-1.1 | 短期 refreshProject，中期 Pinia Store 重构 | §C-1.1 架构演进建议 |

---

## 问题总览

| 编号 | 模块 | 问题摘要 | 根因定位 | 优先级 | 状态 |
|------|------|---------|---------|--------|------|
| A-1 | export | 导出页编码器下拉框在无硬件编码器设备上仍返回 intel/amd/nvidia | SettingsModal 静态渲染编码器列表 | P1 | 已修复 (commit `91eb7bc`) |
| A-2.1 | workspace | 字幕点击/播放指针高亮联动缺失 | TranscriptRow 仅 seek；Waveform↔Timeline 无双向高亮；右键菜单未按 playhead 范围收敛 | P0 | 待修复 |
| A-2.2 | workspace | 编辑字幕时拖选文字超框自动退出编辑 | `TranscriptRow.vue:294` `<input @blur>` 触发 saveEdit | P1 | 待修复 |
| A-2.4 | workspace | 分割后两段字幕的 EditDecision 状态联动 | `project_service.py:917-919` 仅按旧 id 过滤；split 后未给 a/b 创建独立 ED | P1 | 待修复 |
| A-3 | workspace | Timeline 右侧栏占据固定 320px，无法折叠 | `Timeline.vue:249` 写死 `w-80 border-l`，flex 内嵌 | P2 | 待修复 |
| A-4 | workspace | TimelineSwitcher 在 rename/delete 后整体消失 | WorkspacePage 在 rename/delete 状态下错误隐藏整个切换器 | P1 | 待修复 |
| C-1.1 | llm | 智能删除完成后 GUI 无结果返回 | `useLlmTasks.ts` 监听 `EVENT_LLM_SMART_DELETE_COMPLETED` 只更新本地 ref，未刷新 project | P0 | 待修复 |

---

## A-1 硬件编码器下拉框误显示（已修复）

**原报告**: macOS 设置页检测的硬件编码器正常，但导出设置中编码器列表仍是 intel、amd、nvidia 编码器（合理怀疑在无硬件编码器的 Win 设备中也如此）。

**根因**: `SettingsModal.vue` 早期实现里硬编码了 `h264_nvenc / h264_qsv / h264_amf` 三个选项的静态列表，不依赖后端 `get_encoder_caps` 返回的真实能力。

**修复**: commit `91eb7bc fix(export): SettingsModal Video codec 下拉框改动态渲染 — 修复 macOS/Win 误显示不存在编码器`

改动要点:
- 新建 `core/ffmpeg_presets.py` 作为编码器单一事实来源
- SettingsModal 下拉框改用 `call("get_encoder_caps")` 返回值动态渲染
- 修复硬件编码器 `-cq/-qp` 误用 `-crf` 的参数错配
- 添加像素格式探测，HDR/10-bit 输入保留原始格式

**状态**: ✅ 已验证

---

## A-2.1 字幕高亮联动缺失 + 右键菜单未按 playhead 收敛

### 现象拆解（共 3 个子需求）

1. **双向高亮**: 点击 Waveform 里的字幕块 → Timeline 的 TranscriptRow 高亮（已有）；但点击 TranscriptRow / SuggestionPanel 建议项 → 不会反向高亮 + 滚动到对应 Waveform 块。
2. **playhead 高亮**: 播放指针所在 segment 的 TranscriptRow 需要自动高亮（区别于 selected 状态）。
3. **右键菜单收敛**: 「从指针处分割」菜单项应仅出现在 playhead 时间 ∈ `[segment.start, segment.end]` 的那一行 TranscriptRow 上；其他段不显示（"冻结"）。

### 当前代码上下文

**TranscriptRow.vue — defineProps（第 7-19 行）**:

```ts
const props = defineProps<{
  segment: Segment
  displayStatus?: string
  styleClass?: string
  isSelected?: boolean              // 只有一个"选中"状态
  isAdjacentHighlighted?: boolean   // 仅用于跨验证静音段，不是 playhead
  globalEditMode?: boolean
  selectionMode?: boolean
  isMultiSelected?: boolean
  currentTime?: number              // 仅用于 split-at-pointer，未用于高亮判断
}>()
```

**TranscriptRow.vue — 普通点击只 seek，不联动选中（第 195-206 行）**:

```ts
// Row click: in selection mode toggle selection; otherwise seek to segment.
function handleRowClick(e: MouseEvent) {
  if (editingTimeField.value) return
  // v2.1.1 M4-1: selection mode intercepts the click
  if (props.selectionMode) {
    emit("segment-click", props.segment.id, e)   // ← 仅选择模式下才 emit
    return
  }
  if (isEditingText.value && !props.globalEditMode) {
    saveEdit()
  }
  emit("seek", props.segment.start)              // ← 普通模式只 seek，无选中事件
}
```

**TranscriptRow.vue — 行容器 class 绑定（第 221-222 行）**:

```vue
<div
  class="flex items-start gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 transition-colors"
  :class="[statusClass, { 'ring-1 ring-blue-500': isSelected,
                           'ring-2 ring-blue-500 bg-blue-50': isMultiSelected }]"
  :data-segment-id="segment.id"
  @click="handleRowClick"
  @contextmenu="handleContextMenu"
>
```

→ 只有 `isSelected` / `isMultiSelected` 两个高亮态，没有 playhead / external-highlight 态。

**TranscriptRow.vue — 右键菜单"从指针分割"无条件渲染（第 398-404 行）**:

```vue
<button
  class="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
  title="在时间指针位置分割"
  @click="handleSplitAtPointer"
>
  从时间指针分割
</button>
```

→ 没有 `v-if`，不管 playhead 是否在该段范围内都显示。

**TranscriptRow.vue — handleSplitAtPointer 无范围校验（第 67-75 行）**:

```ts
function handleSplitAtPointer() {
  if (props.globalEditMode) {
    emit("toast", "请退出编辑模式后重试")
    closeContextMenu()
    return
  }
  emit("split-at-pointer", props.currentTime ?? 0)  // ← 未校验 currentTime 是否 ∈ [start, end]
  closeContextMenu()
}
```

**Timeline.vue — v-memo 未包含 playhead 相关依赖（第 210 行）**:

```vue
<TranscriptRow
  v-if="seg.type === 'subtitle'"
  v-memo="[seg, getSegmentState(seg).displayStatus,
           selectedSegmentIds?.has(seg.id) ?? false,
           selectedSegmentId === seg.id,
           globalEditMode, selectionMode]"
```

→ `v-memo` 依赖列表里没有 `currentTime`，即使传入 `is-playhead-inside` prop，playhead 移动时该行也不会重新渲染。

**Timeline.vue — SuggestionPanel 的 seek 仅透传，无联动滚动（第 275-280 行）**:

```vue
<SuggestionPanel
  v-show="activeTab === 'suggestion'"
  :analysis-results="analysisResults"
  ...
  @seek="(t) => emit('seek-suggestion', t)"   <!-- 只 seek 视频，不滚动/不高亮 TranscriptRow -->
/>
```

### 根因小结

| 子需求 | 缺失能力 | 代码位置 |
|--------|---------|---------|
| 双向高亮 | TranscriptRow 普通点击无选中事件 emit | TranscriptRow.vue:195-206 |
| 双向高亮 | SuggestionPanel 点击只 seek 不联动 | Timeline.vue:279 |
| playhead 高亮 | 无 `isPlayheadInside` prop + 计算 | TranscriptRow.vue:7-19; Timeline.vue 无 computed |
| playhead 高亮 | v-memo 依赖未含 currentTime | Timeline.vue:210 |
| 右键菜单收敛 | 菜单项未按 playhead 范围 v-if | TranscriptRow.vue:398-404 |
| 右键菜单收敛 | handleSplitAtPointer 未范围校验 | TranscriptRow.vue:67-75 |

### 修复方案

#### 子需求 1: 双向高亮 + 滚动定位

**TranscriptRow 改动**:
- 新增 `isHighlighted` prop（外部驱动的临时高亮，如来自 SuggestionPanel 点击）
- 新增 `@scroll-into-view` 触发器：通过 `ref` + `scrollIntoView({ block: "nearest", behavior: "smooth" })` 实现

**Timeline.vue 改动**:
- 新增内部状态 `highlightedSegmentId: ref<string | null>`，3 秒后自动清空
- 监听 SuggestionPanel 的 `@seek` 事件：除现有 `seek-suggestion` emit 外，同步 `highlightedSegmentId = segId`，并触发对应 TranscriptRow 的 `scrollIntoView`
- `segment-click` 不再仅在 selectionMode 下触发；普通模式下也 emit（但默认行为仍是 seek）

**WorkspacePage 改动**:
- `selectedSegmentId` 改为双向：TranscriptRow 点击 → 写入 `selectedSegmentId` → 透传给 Waveform 的 `selectedSegmentId` prop → SegmentBlocksLayer 高亮对应块

#### 子需求 2: playhead 高亮

**TranscriptRow 新增 prop**:
```ts
isPlayheadInside?: boolean  // playhead 时间 ∈ [start, end]
```

**视觉规则**:
| 状态 | 样式 |
|------|------|
| 默认 | 无 ring |
| selected (用户点击) | `ring-1 ring-blue-500` |
| playhead inside (未选中) | `bg-blue-50 border-l-2 border-blue-400` |
| highlighted (外部联动) | `ring-2 ring-yellow-400 bg-yellow-50`（2 秒动画淡出） |
| 多选 | `ring-2 ring-blue-500 bg-blue-50` |

**Timeline.vue 计算**:
```ts
const playheadSegmentId = computed(() => {
  const t = props.currentTime ?? 0
  return props.segments.find(s => s.type === 'subtitle' && t >= s.start && t <= s.end)?.id ?? null
})
```
传给 TranscriptRow 的 `:is-playhead-inside="seg.id === playheadSegmentId"`。

**性能优化（评审建议）**:

直接把 `currentTime` 传入 `v-memo` 依赖列表会导致播放期间整个 TranscriptRow 列表每帧（10-60fps）重渲染，即使该段并未高亮变化。改为只把"进出该段"的布尔值传入：

```vue
<TranscriptRow
  v-memo="[seg, getSegmentState(seg).displayStatus,
           selectedSegmentIds?.has(seg.id) ?? false,
           selectedSegmentId === seg.id,
           seg.id === playheadSegmentId,   <!-- ← 替代 currentTime -->
           globalEditMode, selectionMode]"
```

这样只有 playhead 进/出某段范围时才触发该行重渲染，中间连续移动不影响其他行。

#### 子需求 3: 右键菜单收敛

**TranscriptRow.vue 模板**（约第 380-410 行的 contextmenu）:
```vue
<button v-if="isPlayheadInside" @click="handleSplitAtPointer">从指针处分割</button>
```
- 仅当 `props.currentTime ∈ [segment.start, segment.end]` 时才渲染该菜单项
- 保留"中间分割"菜单项不变（不受 playhead 影响）

### 影响文件

| 文件 | 改动类型 |
|------|---------|
| `frontend/src/components/workspace/TranscriptRow.vue` | 新增 prop、修改 contextmenu 渲染条件 |
| `frontend/src/components/workspace/Timeline.vue` | 新增 highlightedSegmentId、playheadSegmentId 计算 |
| `frontend/src/pages/WorkspacePage.vue` | selectedSegmentId 双向化、SuggestionPanel seek 联动 |
| `frontend/src/components/workspace/SuggestionPanel.vue` | emit `highlight-segment` 事件 |

### 验证步骤

1. 点击 TranscriptRow → Waveform 对应块高亮 + 自动滚动到可见区
2. 点击 Waveform 字幕块 → TranscriptRow 高亮 + scrollIntoView
3. 点击 SuggestionPanel 建议项 → TranscriptRow 黄色高亮 + 滚动到该行
4. 播放视频 → playhead 所在 TranscriptRow 显示蓝色左边框
5. 右键某段 → 仅当 playhead 在该段范围内时显示「从指针处分割」
6. 右键 playhead 不在的段 → 无「从指针处分割」菜单项

---

## A-2.2 编辑字幕时拖选文字超框自动退出

### 当前代码上下文

**TranscriptRow.vue — 编辑输入框（第 290-298 行）**:

```vue
<input
  v-if="isEditingText"
  v-model="editText"
  class="w-full min-w-0 bg-white border border-blue-400 rounded px-1 py-0.5 text-sm outline-none box-border"
  @blur="handleTextEditBlur"
  @keydown="handleTextEditKeydown"
  @mousedown.stop
  @click.stop
/>
```

**TranscriptRow.vue — blur 回调直接保存退出（第 184-187 行）**:

```ts
function handleTextEditBlur() {
  if (props.globalEditMode) return   // 全局编辑模式下不退出（批量编辑）
  saveEdit()                         // 其他场景：立即保存并 isEditingText = false
}
```

**TranscriptRow.vue — saveEdit 实现关闭编辑模式（第 159-164 行）**:

```ts
function saveEdit() {
  if (editText.value !== props.segment.text) {
    emit("update-text", props.segment.id, editText.value)
  }
  isEditingText.value = false   // ← 直接关闭，无延迟、无焦点校验
}
```

### 根因

`@blur="handleTextEditBlur"` 在以下三种场景都会触发，但当前代码无法区分：

| 场景 | 用户意图 | 当前行为 | 期望行为 |
|------|---------|---------|---------|
| 点击输入框外部空白 | 完成编辑，保存退出 | 保存退出 ✓ | 保存退出 |
| 按 ESC | 取消编辑 | 取消（keydown 处理） ✓ | 取消 |
| 拖选文字时光标滑出 input 边界 | **仅想选更多文字** | **误判为完成 → 保存退出** ✗ | 保持编辑模式 |

input 元素的 `blur` 事件在"鼠标拖选延伸出元素边界"时也会触发，因为浏览器在 mouseup 时会把焦点交还给父文档。当前 `handleTextEditBlur` 没有任何延迟或焦点再检查机制，一 blur 就立刻保存退出。

### 修复方案

**方案 A（推荐）**: 区分"用户主动点击外部" vs "拖选延伸出框"

```ts
// 新增 mousedown 跟踪
const textInputMouseDownTime = ref(0)

function onTextInputMouseDown() {
  textInputMouseDownTime.value = Date.now()
}

function handleTextEditBlur() {
  if (props.globalEditMode) return
  // 拖选导致的 blur：mousedown 到 blur 间隔极短（<200ms）且涉及拖动
  // 用 nextTick 延迟检查，如果焦点仍在外部（确实是 click away）才保存
  setTimeout(() => {
    const active = document.activeElement
    if (active && active.tagName === 'INPUT' && active.classList.contains('edit-text-input')) {
      return  // 焦点已回到某个 edit input，忽略
    }
    saveEdit()
  }, 150)
}
```

**方案 B（更彻底）**: 移除 `@blur` 自动保存，改用 click-outside + 显式按钮

- 编辑模式下输入框常驻，只有点击「保存」/「取消」按钮、或 ESC、或切换其他 TranscriptRow 才退出
- 风险：用户编辑到一半切走会丢失（可用 onBeforeUnmount 提示）

**推荐选 A**，改动小、风险低。

> **代码注释要求（评审建议）**: 实现时在 `handleTextEditBlur` 上方写明这是处理 drag-out 边界异常的 hack，避免后续维护者误以为是普通 click-outside 逻辑：
>
> ```ts
> // HACK: 拖选文字时光标可能滑出 input 边界触发 blur，
> // 此时并非用户意图完成编辑，需延迟校验焦点是否真的离开所有 edit input。
> // 若 150ms 内焦点回到任一 edit-text-input，视为拖选操作，忽略本次 blur。
> function handleTextEditBlur() { ... }
> ```

> **备选方案（Vue 自定义指令）**: 社区通用做法是 `v-click-outside` 结合 `mousedown/mouseup` 事件屏蔽选区拖出。考虑到本项目未引入该指令且改动面更大，方案 A 已足够，后续若引入 click-outside 指令可统一迁移。

### 影响文件

- `frontend/src/components/workspace/TranscriptRow.vue`

### 验证步骤

1. 进入编辑模式 → 拖选文字超过输入框右边界 → 编辑模式不退出，选区正常
2. 点击外部空白区域 → 编辑模式正常退出并保存
3. 按 ESC → 取消编辑
4. 按 Enter → 保存并退出

---

## A-2.4 分割后两段字幕 EditDecision 状态联动

### 当前代码上下文

**core/project_service.py — split_segment 完整实现（第 874-926 行）**:

```python
def split_segment(self, segment_id: str, position: float) -> dict:
    """Split a subtitle segment at the given time position.

    Creates two segments: {id}-a and {id}-b. Text is split proportionally.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}

    segments = list(self.active_timeline.transcript.segments)
    target = next((s for s in segments if s.id == segment_id), None)
    if target is None:
        return {"success": False, "error": f"Segment not found: {segment_id}"}
    if target.type != SegmentType.SUBTITLE:
        return {"success": False, "error": "Can only split subtitle segments"}
    # Allow split at exact boundaries (e.g. playhead at 0.0 for a segment starting at 0.0)
    if position < target.start or position > target.end:
        return {"success": False, "error": "Split position must be within segment bounds"}

    # Split text proportionally by duration ratio
    total_dur = target.end - target.start
    ratio = (position - target.start) / total_dur
    split_idx = max(1, min(len(target.text) - 1, int(len(target.text) * ratio)))

    seg_a = target.model_copy(update={
        "id": f"{segment_id}-a",
        "end": position,
        "text": target.text[:split_idx].strip(),
        "dirty_flags": {**target.dirty_flags, "split": True},
    })
    seg_b = target.model_copy(update={
        "id": f"{segment_id}-b",
        "start": position,
        "text": target.text[split_idx:].strip(),
        "dirty_flags": {**target.dirty_flags, "split": True},
    })

    new_segments = []
    for s in segments:
        if s.id == segment_id:
            new_segments.extend([seg_a, seg_b])
        else:
            new_segments.append(s)

    # Remove EditDecisions referencing the old segment
    new_edits = [e for e in self.active_timeline.edits
                 if not hasattr(e, '_segment_ids') or segment_id not in e._segment_ids]

    self._update_active_timeline(
        transcript=self.active_timeline.transcript.model_copy(update={"segments": new_segments}),
        edits=new_edits,
    )
    logger.info("Split segment {} at {:.3f}s", segment_id, position)
    return {"success": True, "data": self._current.model_dump()}
```

### 根因

第 917-919 行的 ED 处理有两个缺陷：

**缺陷 1: 仅过滤而不继承**

```python
# 当前逻辑：把指向旧 segment_id 的 ED 全部丢弃
new_edits = [e for e in self.active_timeline.edits
             if not hasattr(e, '_segment_ids') or segment_id not in e._segment_ids]
```

原 segment 的 ED（如"标记删除"）直接被丢弃，但 seg_a / seg_b 未继承。然而用户在 UI 上仍看到两段显示原状态 —— 这是因为 `TranscriptRow.vue` 的 `getSegmentState` 在找不到 ED 时会 fallback 到 `segment.dirty_flags` 或 analysis.results，而 a/b 都继承了 `dirty_flags = {..., "split": True}`，加上 analysis.results 里的时间范围可能覆盖两段，导致"同步显示"。

**缺陷 2: `_segment_ids` 私有属性覆盖不全**

`hasattr(e, '_segment_ids')` 只对部分 ED 类型成立：
- LLM smart-delete 创建的 ED 有 `_segment_ids` → 被正确过滤
- Rule-based（filler / error）的 ED 用时间范围匹配，**无 `_segment_ids`** → 保留原样
- 时间范围型 ED 的 `start_time/end_time` 仍指向原 segment 区间 → 同时命中 seg_a 和 seg_b 的子区间

**现象**: split 后给 seg_a 标记"删除"，UI 上 seg_b 也显示"删除"（因为底层 ED 共享或 fallback 到同一数据源）。

### 修复方向

1. 收集原 segment 的所有 ED（按 `_segment_ids` 或按时间范围重叠判断）
2. 为 seg_a / seg_b 分别 `model_copy` 出独立 ED
3. **时间范围型 ED 按 split position 切割**（评审建议）:
   - rule-based filler/error 分析结果带 `start_time / end_time`，split 时应按 position 把范围切成两段
   - `[old_start, old_end]` → `[old_start, position]` 绑给 seg_a + `[position, old_end]` 绑给 seg_b
   - **理由**：用户切了一刀就丢失已标记的语气词/静音会非常反直觉；按 NLE 时间线切割符合用户对非线性编辑的认知
   - 若某条 ED 的范围完全落在 position 一侧（如完全在 a 段），则仅绑给那一段，另一段不创建

### 修复方案

`core/project_service.py:split_segment` 改动:

```python
# 收集原 segment 的所有 ED
inherited_edits = [e for e in self.active_timeline.edits
                   if hasattr(e, '_segment_ids') and segment_id in e._segment_ids]

# 为 seg_a 和 seg_b 分别创建独立 ED（继承状态但 id 独立）
new_edits_for_split = []
for old_edit in inherited_edits:
    for new_id in (f"{segment_id}-a", f"{segment_id}-b"):
        new_edits_for_split.append(
            old_edit.model_copy(update={
                "id": f"{old_edit.id}__{new_id}",
                "_segment_ids": [new_id],
            })
        )

# 过滤掉旧的，加上新的
new_edits = [
    e for e in self.active_timeline.edits
    if not (hasattr(e, '_segment_ids') and segment_id in e._segment_ids)
] + new_edits_for_split
```

**行为约定**:
- split 前 segment X 状态 = "rejected"（保留）→ split 后 X-a 和 X-b 都继承 "rejected"
- split 后用户对 X-a 操作 toggle → 仅影响 X-a 的 ED，X-b 不受影响

### 影响文件

- `core/project_service.py`
- `tests/test_project_service.py`（新增 split + ED 独立性测试）

### 验证步骤

1. 标记 segment X 为「删除」→ split X → X-a 和 X-b 都显示「删除」状态（继承）
2. 在 split 后点击 X-a 的「保留」→ X-a 变绿，X-b 仍为「删除」（独立）
3. 单元测试: `test_split_segment_inherits_and_independent_edits`

---

## A-3 Timeline 右侧栏改为可折叠 overlay

### 当前代码上下文

**Timeline.vue — 主体 flex 布局（第 188-190 行）**:

```vue
<div class="flex flex-1 overflow-hidden">
  <!-- Transcript list -->
  <div ref="listContainer" class="flex-1 overflow-y-auto">
    ...
  </div>
```

**Timeline.vue — 右侧栏嵌在 flex 里占 320px（第 248-265 行）**:

```vue
<!-- Right sidebar: 3-tab switcher (suggestion / AI assistant / highlight) -->
<div class="w-80 border-l border-gray-200 flex flex-col">
  <!-- Tab header (D-18) -->
  <div class="flex border-b border-gray-200 bg-gray-50">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="flex-1 px-2 py-2 text-xs font-medium transition-colors"
      :class="
        activeTab === tab.key
          ? 'border-b-2 border-blue-500 text-blue-600 bg-white'
          : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
      "
      @click="activeTab = tab.key"
    >
      {{ tab.label }}
    </button>
  </div>

  <!-- Tab content (v-show preserves component state across switches) -->
  <div class="flex-1 overflow-y-auto p-2">
    <SuggestionPanel v-show="activeTab === 'suggestion'" ... />
    <AIAssistantPanel v-show="activeTab === 'ai'" ... />
    <HighlightModeView v-show="activeTab === 'highlight'" ... />
  </div>
</div>
```

### 根因

- `w-80` (320px) 是固定宽度，与 TranscriptRow 列表平级 flex 子元素
- 没有"隐藏/显示"机制，也没有 `sidebarOpen` 状态
- 无 overlay 定位（缺 `absolute / z-*`），永远挤占布局空间

### 修复方案

**布局改造**:

```vue
<Timeline>
  <div class="relative flex h-full">
    <!-- TranscriptRow 全宽 -->
    <div class="flex-1 overflow-y-auto">...</div>

    <!-- Overlay 右侧栏 -->
    <Transition name="slide-in-right">
      <div
        v-if="sidebarOpen"
        class="absolute right-0 top-0 bottom-0 w-80 bg-white shadow-2xl border-l border-gray-200 z-20 flex flex-col"
      >
        <!-- tab header + content -->
      </div>
    </Transition>

    <!-- 折叠按钮（始终显示在右上角） -->
    <button
      class="absolute right-2 top-2 z-30 ..."
      @click="sidebarOpen = !sidebarOpen"
    >
      <ChevronIcon v-if="sidebarOpen" />
      <PanelIcon v-else />
    </button>
  </div>
</Timeline>
```

**状态管理**:
- `sidebarOpen: ref(false)`（默认隐藏）
- 可选持久化到 `localStorage` 记忆用户偏好

**交互细节**:
- 默认隐藏（符合报告要求"默认隐藏"）
- 显示时浮在 TranscriptRow 列表上层（z-20），不挤压排版
- 折叠按钮固定在 Timeline 右上角，不被 overlay 遮挡（z-30）
- 动画: `transform: translateX(100%) → 0`，duration 200ms

### 影响文件

- `frontend/src/components/workspace/Timeline.vue`

### 验证步骤

1. 进入 WorkspacePage → 右侧栏默认隐藏，Timeline 占满宽度
2. 点击右上角图标 → 右侧栏从右滑入，浮在 Timeline 上层（不挤压）
3. 再次点击 → 滑出收起
4. 切换 Tab（建议/AI助手/精华）→ 内容切换正常
5. 切换 Timeline → 右侧栏状态保留（不强制收起）

---

## A-4 TimelineSwitcher 在 rename/delete 后整体消失

### 当前代码上下文

**WorkspacePage.vue — TimelineSwitcher 调用（第 1476-1487 行）**:

```vue
<TimelineSwitcher
  :timelines="props.project.timelines"
  :active-timeline-id="props.project.active_timeline_id"
  :renaming-id="renamingTimelineId"
  :rename-val="renameValue"
  @switch="handleSwitchTimeline"
  @create="handleCreateTimeline"
  @delete="handleDeleteTimeline"
  @rename-start="startRenameTimeline"
  @rename-input="(_id: string, val: string) => (renameValue = val)"
  @rename-confirm="confirmRenameTimeline"
  @rename-cancel="cancelRenameTimeline"
/>
```

→ 外层无 `v-if` 条件渲染，组件始终挂载。

**TimelineSwitcher.vue — 根模板是 DaisyUI dropdown（第 1-22 行）**:

```vue
<template>
  <div class="flex items-center gap-2">
    <div class="dropdown dropdown-end">
      <!-- 触发器：tabindex=0，可 click/focus 打开 -->
      <div tabindex="0" role="button" class="flex items-center gap-2 rounded px-2 py-1 ...">
        <svg>...</svg>
        <span class="text-sm font-medium">{{ activeLabel }}</span>
      </div>
      <!-- 下拉内容：点击外部或 ESC 自动关闭 -->
      <ul class="dropdown-content ...">
        <li v-for="tl in timelines" ...>
          <input v-if="renamingId === tl.id" ... />   <!-- inline rename input -->
          <span v-else>{{ tl.label }}</span>
        </li>
      </ul>
    </div>
    <a class="text-sm" @click="$emit('create')">新建</a>
  </div>
</template>
```

**TimelineSwitcher.vue — onContextRename / onContextDelete（第 136-150 行）**:

```ts
function onContextRename() {
  const id = contextMenu.value?.id
  contextMenu.value = null
  if (id) {
    if (id !== props.activeTimelineId) emit("switch", id)
    emit("rename-start", id)   // ← 父组件更新 renamingId → 子组件 input 渲染
  }
}

function onContextDelete() {
  const id = contextMenu.value?.id
  contextMenu.value = null
  if (id && canDelete.value) emit("delete", id)   // ← 父组件弹 confirm → 切 Timeline
}
```

### 根因（修正）

经代码核查，不是"整个 TimelineSwitcher 组件消失"，而是 **DaisyUI dropdown 面板关闭时机不一致**：

| 操作 | 行为 | 根因 |
|------|------|------|
| 新建 Timeline | dropdown 保持打开（新建项立即出现） | `handleCreateTimeline` 不改变焦点 |
| 切换 Timeline | dropdown 保持打开 | `handleSwitchTimeline` 仅更新 project 数据 |
| 重命名（inline） | dropdown 立即关闭 → input 看不见 | `@blur` / DaisyUI 焦点机制：contextMenu 关闭时下拉面板失焦自动收起 |
| 删除 | dropdown 关闭（confirm dialog 抢焦点） | `window.confirm` 是阻塞模态，confirm 后 dropdown 早已收起 |

用户的"整个多 Timeline 选项区域隐藏"实际指 dropdown 面板收起。报告里的"需要重新打开编辑"对应"必须重新点开 dropdown 才能看到 inline rename input"。

### 修复方向

**重命名路径**:
- 重命名时强制保持 dropdown 打开（DaisyUI 的 `dropdown-open` class 或手动控制 `tabindex` 焦点）
- 或重命名触发后关闭 dropdown，但 inline input 浮出为独立 popover（脱离 dropdown 容器）

**删除路径（评审强推荐）**:
- 将 `window.confirm` 替换为应用内 Dialog/Modal 组件
- **理由**:
  1. 解决焦点抢占导致 dropdown 收起的问题
  2. 统一应用 UI 风格，摆脱系统原生弹窗的廉价感
  3. 与项目其他删除场景（如 segment 删除）保持一致
- 实现建议:
  - 若项目已有 `RelinkMediaDialog.vue` 等组件参考，复用其模式
  - 否则使用 DaisyUI `<dialog class="modal">` + `Teleport to="body"`
  - 封装成可复用的 `ConfirmDialog.vue`，后续其他 `window.confirm` 调用点可统一替换

**统一行为约定**:
| 操作 | dropdown 行为 | confirm 方式 |
|------|-------------|-------------|
| 新建 | 保持打开，立即显示新项 | 应用内 Dialog 询问"Fork from current?" |
| 切换 | 保持打开 | 无需 confirm |
| 重命名 | 保持打开（inline input 可见） | 无需 confirm |
| 删除 | 保持打开，删除后高亮切换到新 active | 应用内 Dialog "确认删除？" |

### 影响文件

- `frontend/src/pages/WorkspacePage.vue`
- `frontend/src/components/workspace/TimelineSwitcher.vue`

### 验证步骤

1. 右键 Timeline → 重命名 → 切换器始终可见，仅当前项变为 input
2. 重命名确认/取消 → 切换器正常显示
3. 右键 → 删除 → 确认后切换器仍可见，当前项切换到其他 Timeline
4. 新建 Timeline → 切换器立即显示新项（当前已有行为）
5. 切换 Timeline → 切换器正常

---

## C-1.1 智能删除完成后 GUI 无结果返回

### 现象

```
INFO | core.llm_service:analyze_smart_delete - Smart-delete analysis done: 27 results, tokens=18364
INFO | core.project_service:add_analysis_results - Added 27 analysis results from llm_smart
INFO | core.project_service:save_project - Saved project to .../project.json
```

后端已成功将 27 条 LLM smart-delete 结果写入 project.analysis.results，但 GUI 的 SuggestionPanel 没有显示任何结果。

### 当前代码上下文

**frontend/src/composables/useLlmTasks.ts — 完成事件监听器（第 112-121 行）**:

```ts
// P0 smart-delete: completed
onEvent<{ results?: SmartDeleteResult[] }>(
  EVENT_LLM_SMART_DELETE_COMPLETED,
  (detail) => {
    isRunning.value = false
    if (detail?.results) {
      smartDeleteResults.value = detail.results   // ← 只更新本地 ref
    }
    // ❌ 没有调用 refreshProject / emit('project-updated')
  },
)
```

**frontend/src/composables/useLlmTasks.ts — 同样的缺口出现在 P1/P2（第 124-178 行）**:

```ts
// P1 subtitle correction: completed
onEvent(EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED, async (detail) => {
  isRunning.value = false
  if (detail) {
    subtitleCorrectionResult.value = detail
    // ❌ 依赖调用方稍后 loadCorrections(tlId)，但 analysis.results 同步未触发
  }
})

// P2 highlight: completed
onEvent(EVENT_LLM_HIGHLIGHT_COMPLETED, (detail) => {
  isRunning.value = false
  if (detail?.results) {
    highlightResults.value = detail.results
  }
  // ✓ 这里倒是有调用 detect_highlight_jump_cuts，但仍未刷新 project
  call("detect_highlight_jump_cuts").then(...)
})
```

**frontend/src/pages/WorkspacePage.vue — analysisResults 数据来源（第 390-396 行）**:

```ts
const activeTimeline = computed<TimelineData | null>(() =>
  props.project.timelines.find(t => t.id === props.project.active_timeline_id) ?? null
)
const segments = computed<Segment[]>(() => activeTimeline.value?.transcript?.segments ?? [])
const edits = computed<EditDecision[]>(() => activeTimeline.value?.edits ?? [])
const duration = computed(() => props.project.media?.duration ?? 0)
const analysisResults = computed(() => activeTimeline.value?.analysis?.results ?? [])
//                                                       ↑
//                              仅依赖 props.project，useLlmTasks 的本地 ref 不影响这里
```

**frontend/src/pages/WorkspacePage.vue — handleStartSmartDelete 仅启动不等待（第 968-975 行）**:

```ts
async function handleStartSmartDelete() {
  if (!llmConfig.value.configured) {
    showToast("请先配置 LLM", "error", 3000)
    return
  }
  await startSmartDelete()           // ← 启动后立刻返回，不监听完成事件
  showToast("智能分析已启动", "info", 2000)
}
```

**frontend/src/components/workspace/SuggestionPanel.vue — 数据来源绑定（第 7、44、60、93-104 行）**:

```ts
defineProps<{ analysisResults: AnalysisResult[]; ... }>()

const fillerResults = computed(() => props.analysisResults.filter(r => r.type === "filler"))
const errorResults  = computed(() => props.analysisResults.filter(r => r.type === "error"))

// LLM smart-delete edits
const llmSmartDeleteEdits = computed(() =>
  props.analysisResults.find(...)   // ← 查找 type === 'llm_smart' 的分析结果
)
```

**后端 — 写盘成功但前端不知道（core/project_service.py:1134-1178）**:

```python
def add_analysis_results(self, results: list[dict], source: str) -> dict:
    """Store AnalysisResult entries and create EditDecisions from time ranges."""
    ...
    # 写入 self._current.active_timeline.analysis.results
    # 调用 save_project() 落盘
    # 通过 bridge emit EVENT_LLM_SMART_DELETE_COMPLETED
    # 但前端 payload 只携带 results 列表，不携带完整 project 快照
```

### 根因

**数据流断裂链**:

```
后端 add_analysis_results
  ├── 写盘 ✓
  ├── 更新 self._current ✓
  └── emit EVENT_LLM_SMART_DELETE_COMPLETED(payload={ results: [...] }) ✓
                                                        ↓
前端 useLlmTasks 监听器
  ├── isRunning.value = false ✓
  ├── smartDeleteResults.value = detail.results ✓ (本地 ref，但没人用)
  └── ❌ 未调用 refreshProject / 未通知 WorkspacePage 更新 props.project

SuggestionPanel 数据源
  ← Timeline.vue :analysis-results="analysisResults"
  ← WorkspacePage.vue:396 analysisResults = activeTimeline.analysis.results
  ← activeTimeline = props.project.timelines.find(...)
  ← props.project    ❌ 仍是任务启动前的快照，analysis.results 为空

→ 后端已落盘 27 条，前端 props.project 未刷新 → SuggestionPanel 永远空
```

**关键观察**:
- `useLlmTasks` 维护的 `smartDeleteResults` 本地 ref 实际**没有**被任何 UI 组件消费
- `SuggestionPanel` 完全依赖 `props.project` 派生的 `analysisResults`
- 这导致 `useLlmTasks` 的本地状态成了死代码

### 修复方案

**方案 1（推荐）**: 完成事件后主动拉取 project

`frontend/src/composables/useLlmTasks.ts:113-121`:
```ts
onEvent<{ results?: SmartDeleteResult[] }>(
  EVENT_LLM_SMART_DELETE_COMPLETED,
  async (detail) => {
    isRunning.value = false
    if (detail?.results) {
      smartDeleteResults.value = detail.results
    }
    // v2.1.1 fix: 主动刷新 project，让 SuggestionPanel 拿到 analysis.results
    await refreshProject()
  },
)
```

`refreshProject` 实现（放 WorkspacePage 或 useProject composable）:
```ts
async function refreshProject() {
  const res = await call<Project>("get_project")
  if (res.success && res.data) {
    // 通过 emit 或 store 更新 props.project
  }
}
```

**方案 2**: 后端在 `EVENT_LLM_SMART_DELETE_COMPLETED` 的 payload 直接带 project 快照

- 改动小但耦合，且 payload 可能过大

**推荐方案 1**，职责清晰。

**架构演进建议（评审建议）**:

当前架构是 `props.project` 单向流，`useLlmTasks` 作为 composable 无法直接修改 props。若后续有重构精力：

- **短期（v2.1.1）**: 按方案 1 在 `useLlmTasks` 完成回调中调用 `refreshProject`，通过 emit `project-updated` 让 WorkspacePage 更新 props。侵入性最低。
- **中期（v2.1.2+）**: 将 project 状态迁移到 **Pinia Store**，composable 直接 `store.updateProject()`，消除 props 单向流的同步缺口。届时 `smartDeleteResults` 这类"死代码本地 ref"也可一并清理。
- **长期**: 所有后端 → 前端的状态同步都走 store action，配合 SSE 或 WebSocket 替代事件广播，避免遗漏 emit。

**关联修复**:
- P1 字幕修正完成后 `EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED` 也需类似处理（虽然前端有 `loadCorrections`，但 analysis.results 同步也要刷新）
- P2 精华提取完成同理

### 影响文件

| 文件 | 改动 |
|------|------|
| `frontend/src/composables/useLlmTasks.ts` | 3 个完成事件回调加 refreshProject 调用 |
| `frontend/src/pages/WorkspacePage.vue` | 暴露 refreshProject 函数给 composable，或通过事件触发 |

### 验证步骤

1. 启动智能删除 → 进度条正常 → 完成后 SuggestionPanel 立即显示 27 条建议
2. 切换 Timeline 再切回 → 结果仍存在（来自 project 数据）
3. 重启应用 → 结果从 project.json 恢复
4. P1 字幕修正完成 → 全屏 diff 视图可正常打开
5. P2 精华提取完成 → HighlightModeView 显示片段列表

---

## 实施优先级建议

| 优先级 | 编号 | 理由 |
|--------|------|------|
| P0（阻塞主流程） | C-1.1 | 智能删除是核心功能，结果不显示等于功能不可用 |
| P0（核心交互） | A-2.1 | 高亮联动是字幕编辑的基础体验 |
| P1 | A-2.4 | EditDecision 状态错乱会导致误删 |
| P1 | A-4 | TimelineSwitcher 消失影响多 Timeline 管理 |
| P1 | A-2.2 | 编辑拖选 annoyance，影响效率 |
| P2 | A-3 | 布局优化，非阻塞 |

---

## 未决问题（需在实施中验证）

1. **A-2.4 _segment_ids 字段覆盖度**: `hasattr(e, '_segment_ids')` 是否覆盖所有 EditDecision 类型？需在实施时打印 `self.active_timeline.edits` 的实际结构，确认 rule-based ED（无 _segment_ids）如何按时间范围拆分到 a/b 两段。
2. **A-2.4 时间范围型 ED 拆分**: rule-based 的 filler/error 分析结果如果带 `start_time/end_time`，split 时是否要按 position 把范围切成两段分别绑定到 a/b？还是统一丢弃，让用户重新分析？
3. **A-3 sidebar 状态持久化**: 是否需要 localStorage 记忆？默认隐藏即可，持久化可作为 v2.1.2 enhancement。
4. **A-4 删除 confirm 改造**: 把 `window.confirm` 换成应用内 Dialog 可能影响其他流程（如删除 segment），需评估是否同步替换或仅 TimelineSwitcher 内局部替换。
5. **C-1.1 refreshProject 触发链**: refreshProject 拿到新 project 后，是通过 emit `project-updated` 让 WorkspacePage 更新 props，还是引入 Pinia store？当前架构是 props 单向流，改动面可能较大。

---

## 附录: 相关文件清单

```
frontend/src/components/workspace/TranscriptRow.vue      # A-2.1, A-2.2
frontend/src/components/workspace/Timeline.vue           # A-2.1, A-3
frontend/src/components/workspace/TimelineSwitcher.vue   # A-4
frontend/src/components/workspace/SuggestionPanel.vue    # A-2.1, C-1.1
frontend/src/composables/useLlmTasks.ts                  # C-1.1
frontend/src/pages/WorkspacePage.vue                     # A-2.1, A-4, C-1.1
core/project_service.py                                 # A-2.4
tests/test_project_service.py                            # A-2.4 新增测试
```

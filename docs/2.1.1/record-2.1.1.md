# v2.1.1 实施记录

> **版本**: 2.1.1
> **基准**: v2.1.0 (`dev-2.1.0` 分支)
> **分支**: `dev-2.1.1`

## 背景

v2.1.0 发布后手动检查发现多项问题，涵盖崩溃 bug、性能瓶颈、交互缺失三大类。本版本一次性修复全部问题。

## 修复概要

| 模块 | 内容 | 状态 |
|------|------|------|
| M1 | P0 bug 修复 (Analysis 崩溃 + 取消状态错误) | **完成** |
| M2 | LLM 参数可配置 (窗口/批次/上下文/并发数 + Settings UI) | **完成** |
| M3 | LLM chunk 级并发 (smart_delete/correction 并发调用) | **完成** |
| M4 | 字幕交互增强 (多选/时间微调/合并分割/搜索入口/Timeline 重命名) | **完成** |
| M5 | 文档修正 (检查清单 + record) | **完成** |

## M1: P0 Bug 修复

### M1-1: Analysis 功能崩溃

**根因**: v2.0.0 多 Timeline 重构后 `Project` 不再持有 `transcript`，但三个 handler (filler/error/full_analysis) 仍读取 `project.transcript.segments`。

**修复**: 新建 `_get_target_timeline(task)` helper，全部 6 个 handler（3 规则 + 3 LLM）统一调用。

**AR-1**: 消除全部 handler 的 timeline 获取重复。

### M1-2: 取消任务报错 + 状态错误

**根因**: `_execute_task` 不区分取消和失败，统一走 FAILED。

**修复**:
- `_execute_task` except 分支检查 `is_cancelled`（`RuntimeError("Cancelled")` 或 `cancel_event.is_set()`），取消时标记 CANCELLED + emit TASK_CANCELLED
- 新增 `TASK_CANCELLED` 事件常量 (`core/events.py` + `frontend/src/utils/events.ts`)
- 前端 toast 改为「取消中...」，TASK_CANCELLED 到达后弹「已取消」
- `useTask`/`useLlmTasks` 监听 TASK_CANCELLED 重置运行状态

**已知局限**: 已发出的 HTTP 请求在 daemon 线程中继续，仍会消耗 Token。

## M2: LLM 参数可配置

### 新增 settings 字段

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `llm_smart_window_duration` | 60.0 | 智能删除窗口 (秒) |
| `llm_smart_overlap_duration` | 10.0 | 智能删除重叠 (秒) |
| `llm_correction_batch_size` | 30 | 字幕修正批次大小 |
| `llm_correction_context_window` | 5 | 字幕修正上下文窗口 |
| `llm_highlight_chunk_duration` | 1800.0 | 精华提取窗口 (秒) |
| `llm_highlight_overlap_duration` | 60.0 | 精华提取重叠 (秒) |
| `llm_concurrency` | 5 | LLM 并发数 |

### 传递链路

```
settings.json → core/config.py _DEFAULT_SETTINGS → load_settings()
→ core/llm_service.py get_llm_config() + 3 个 analyze 函数读取参数
```

### UI

SettingsModal LLM Tab 新增「高级参数」折叠区（`<details>`），含 7 个 number input。

## M3: LLM Chunk 级并发

### 适用范围

| 功能 | 并发 | 原因 |
|------|------|------|
| smart_delete | **是** | 20+ 独立窗口 → ThreadPoolExecutor + 顺序合并 |
| subtitle_correction | **是** | 4-6 独立批次 → ThreadPoolExecutor + 顺序合并 |
| highlight | **否** | 通常仅 1 块 |
| semantic_search | **否** | 单次调用 |

### 实现

- `ThreadPoolExecutor(max_workers=concurrency)` 提交全部 chunk/batch
- `as_completed` 收集 → `results_by_index[idx]` → 按原始顺序合并
- 取消 → `executor.shutdown(wait=False, cancel_futures=True)` 立即返回

### AR-2: 429 自适应降级

- `call_llm` 429 专用退避: 5s/10s/20s
- 连续 3 次 429 → 剩余 chunk 改串行

## M4: 字幕交互增强

### M4-1: 多选模式

| 交互 | 行为 |
|------|------|
| 工具栏按钮 | 切换选择/播放模式 |
| 普通点击 | 切换选中/取消 (蓝色 ring-2 + 左侧指示条) |
| Ctrl/Cmd + 点击 | 切换单个段选中 |
| Shift + 点击 | 范围选 (从上次选中段到当前段) |
| ESC | 清空选区 / 退出选择模式 |
| Enter | 合并选中段 (≥2 段) |
| Delete | 批量标记选中段删除 |

### M4-2: 时间微调

| 操作 | 步长 |
|------|------|
| −/+ 按钮 | ±0.1s |
| ↑/↓ 方向键 | ±0.1s |
| Shift + ↑/↓ | ±1.0s |

### M4-3: 合并/分割

- 合并: 选择模式选中 ≥2 段 → 合并按钮 → `merge_segments(ids)`（后端 API 已存在）
- 分割: 右键菜单「分割」→ `(start + end) / 2` → `split_segment(id, midpoint)`

### M4-4: 搜索替换入口

- Timeline 工具栏新增搜索图标按钮
- 与 Ctrl+F 快捷键双入口共存
- 点击展开/收起 SearchReplaceBar

### M4-5: Timeline 重命名

- TimelineSwitcher 新增右键菜单：切换/重命名/删除
- 重命名为内联 input 编辑 (Enter/blur 确认 → `rename_timeline` API)

### AR-3: v-memo 优化

`TranscriptRow` 添加 `v-memo`，依赖 6 项：`seg/displayStatus/selectedSegmentIds.has(seg.id)/selectedSegmentId===seg.id/globalEditMode/selectionMode`。选择模式下选中单段不再触发其他段重绘。

## M5: 文档

- `docs/2.1.1/record-2.1.1.md` — 本文档
- `docs/2.1.1/spec-v2.1.1.md` — 规格文档（实施前编写）

## 变更文件清单

### 后端 (6 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `main.py` | M1 | 新增 `_get_target_timeline` helper；6 个 handler 统一调用 |
| `core/task_manager.py` | M1 | _execute_task 区分 Cancelled/FAILED |
| `core/events.py` | M1 | 新增 TASK_CANCELLED 事件常量 |
| `core/config.py` | M2 | _DEFAULT_SETTINGS 新增 7 个 LLM 参数字段 |
| `core/llm_service.py` | M2+M3+AR | 3 个 analyze 函数读取参数 + smart_delete/correction ThreadPoolExecutor + call_llm 429 专用退避 + 自适应降级 |
| `frontend/src/utils/events.ts` | M1 | 同步 TASK_CANCELLED |

### 前端 (8 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | M2 | LLM Tab 新增「高级参数」折叠区 |
| `frontend/src/composables/useSegmentEdit.ts` | M4 | 新增 selectionMode/selectedSegmentIds/handleSegmentClick |
| `frontend/src/components/workspace/TranscriptRow.vue` | M4 | 选择模式样式 + ±0.1s 按钮 + 右键菜单分割 + 键盘微调 |
| `frontend/src/components/workspace/Timeline.vue` | M4+AR | 选择模式按钮 + 搜索图标 + 合并按钮 + v-memo |
| `frontend/src/pages/WorkspacePage.vue` | M4 | handleMergeSelected/handleSplitSegment/搜索入口/Timeline 重命名/键盘快捷键 |
| `frontend/src/composables/useEdit.ts` | M4 | (不改, API 已存在) |
| `frontend/src/composables/useTask.ts` | M1 | 监听 TASK_CANCELLED |
| `frontend/src/composables/useLlmTasks.ts` | M1 | 监听 TASK_CANCELLED 重置 isRunning |
| `frontend/src/types/edit.ts` | M2 | AppSettings 新增 7 个 LLM 字段 |

### 测试 (3 文件)

| 文件 | 模块 | 内容 |
|------|------|------|
| `tests/test_analysis_handlers.py` | M1 | 4 测试: _get_target_timeline 解析 + 3 handler 读取 active timeline |
| `tests/test_task_cancel.py` | M1 | 5 测试: Cancelled/FAILED/Completed 区分 + 事件类型 |
| `tests/test_llm_concurrency.py` | M3 | 4 测试: 并发结果顺序合并 + 取消 + 单块失败隔离 + 批次顺序 |

---

## 后续审计 (AUD-1)

**日期**: 2026-06-17
**来源**: spec-interview 用户访谈
**文档**: `docs/2.1.1/audit-report-2.1.1-1.md`

### 发现的问题

| ID | 问题 | 状态 |
|----|------|------|
| A-01 | Timeline/Waveform 右键菜单互不关闭 | **完成** |
| A-02 | Timeline 右键时间戳误进编辑模式 | **完成** |
| A-03 | 编辑模式/选择模式下 Waveform/Timeline 操作行为混乱 | **完成** |

### 修复实施

**日期**: 2026-06-17
**依据**: `docs/2.1.1/audit-report-2.1.1-1.md` + 深度审计报告

#### A-01: 右键菜单互关

- `contextMenuManager.ts`: `openContextMenu()` 打开前 `dispatchEvent('closeallcontextmenus')` 广播 → 关闭 Waveform 菜单；`setTimeout` 内注册 `window` 级监听器响应外部关闭；`cleanupDocument` 中一起清理
- `SegmentBlocksLayer.vue`: `handleBlockContextMenu` 打开前广播关闭 Timeline 菜单；`onMounted` 注册 `handleGlobalClose` 监听 → `onUnmounted` 注销

#### A-02: 时间戳右键不进编辑

- `TranscriptRow.vue`: 模板 `<span @mousedown="onTimeMouseDown(...)">` 移除 `.stop.prevent`；`onTimeMouseDown` 检查 `e.button !== 0`（右键）直接 return 不阻止冒泡，`contextmenu` 事件正常触发

#### A-03: 编辑模式行为统一

- `WaveformEditor.vue`: `editingActive` prop 拆分为 `globalEditMode` + `selectionMode`；时间尺点击三态：`globalEditMode` → 无反应、`selectionMode` → `emit set-time`（不播放）、普通 → `emit seek`（播放）；方向键统一 `emit set-time`；新增 `set-time` / `toast` emits
- `SegmentBlocksLayer.vue`: 新增 `globalEditMode` prop；方向键 `emit set-time` 替代 `seek`；`splitSelectedAtCursor` / `splitSelectedAtMidpoint` / `deleteSelected` 检查 `globalEditMode` → 拦截时 `emit toast` + `closeContextMenu()`
- `TranscriptRow.vue`: `handleSplitAtPointer` / `handleSplitAtMidpoint` / `handleDeleteSegment` 检查 `globalEditMode` → 拦截时 `emit toast` + `closeContextMenu()`
- `Timeline.vue`: emits 新增 `toast` 透传
- `WorkspacePage.vue`: 新增 `handleSetTime(time)`（seek 不 play）；WaveformEditor 绑定改为 `:global-edit-mode` + `:selection-mode` + `@set-time` + `@toast`；Timeline 新增 `@toast`

#### split-segment 边界修复

- `core/project_service.py`: `split_segment` 边界检查 `<=` / `>=` → `<` / `>`（修复播放指针在 0.0 时 `position <= target.start` 被误拒）

### 变更文件 (本审计)

| 文件 | 模块 |
|------|------|
| `frontend/src/utils/contextMenuManager.ts` | A-01 |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | A-01, A-03 |
| `frontend/src/components/workspace/TranscriptRow.vue` | A-02, A-03 |
| `frontend/src/components/waveform/WaveformEditor.vue` | A-03 |
| `frontend/src/components/workspace/Timeline.vue` | A-03 |
| `frontend/src/pages/WorkspacePage.vue` | A-03 |
| `core/project_service.py` | split 边界修复 |

### AUD-2: 导出编码器列表硬编码 (check-report-2.1.1-2 #1)

**根因**: `SettingsModal.vue` Export section 的 Video codec 下拉框硬编码了 10 个编码器选项 (nvenc/qsv/amf)，未使用 `detect_gpu_encoders` API 返回的 `gpuEncoders` 动态渲染。macOS 上错误显示 Intel/AMD/NVIDIA 编码器且缺失 videotoolbox；无硬件编码器的 Win 设备同样受影响。
- 后端 `detect_gpu_encoders` 本身工作正常（设置页 Hardware Encoders 徽章正确只显示 videotoolbox 即为证）。

**修复**: `SettingsModal.vue` Export section 改为动态渲染：
- 新增 `encoderMeta` ref + `availableVideoCodecs` computed：libx264/libx265 永远显示；libsvtav1 按 `gpuEncoders` 判断；硬件编码器按 `gpuEncoders` 过滤
- `onMounted` 并发调用 `get_encoder_metadata` 获取友好 label（单一事实来源）
- 当前已保存 codec 即使检测漏了也保留显示（防御性 fallback）

## 后续审计 (AUD-3): check-report-2.1.1-3 + spec-sidebar-ai-fixes-2.1.1-4

**日期**: 2026-06-24
**来源**: check-report-2.1.1-3 (用户实测反馈) + spec-sidebar-ai-fixes-2.1.1-4 (审计后修订规格)

### 发现的问题

| ID | 问题 | 状态 |
|----|------|------|
| A-2.1 | 侧边栏建议面板缺少播放头定位高亮 + 建议点击后文本行不跳转 | **完成** |
| A-2.2 | 文本拖选编辑 blur 时误保存 | **完成** |
| A-2.3 | SuggestionPanel 缺少状态可视化（已确认/已忽略无标识） | **完成** |
| A-2.4 | split_segment 后 EditDecision 未正确继承/分割 | **完成** |
| A-2.5 | TimelineSwitcher dropdown 重命名时被 focus 窃取关闭 | **完成** |
| A-2.6 | window.confirm 删除 Timeline 窃取焦点 | **完成** |
| A-2.7 | AI 智能删除结果 id 重复导致全组串扰 | **完成** |
| A-2.8 | 智能删除提示词未区分"半句口误+修正" | **完成** |
| A-2.9 | 侧边栏右键缺少全部确认/全部忽略/删除整组操作 | **完成** |
| A-2.10 | 侧边栏宽度固定不可调 | **完成** |
| A-2.11 | 侧边栏关闭按钮被遮挡 | **完成** |
| A-2.12 | 分割后时间戳右键分割按钮始终显示 | **完成** |

### 修复实施

#### A-2.7: AI 智能删除 id 重复 bug（spec 问题 2）

**根因**: `main.py` 构建分析结果时，27 个 `analysis_results` 共享同一时间戳作为 id（缺少序号 `_{i}`），导致 `project_service.py` 的 `add_analysis_results` 生成 27 个完全相同的 `edit-{ar.id}`。

**修复**（三层防御）:
- `main.py`: `_handle_smart_delete` 提取 `_ts` 一次，`analysis_results` 列表推导加 `enumerate` 拿序号 `_{i}`；`edits` 列表也统一使用 `_ts`
- `project_service.py`: `add_analysis_results` 新增 `existing_edit_ids` 集合 + `_dup{N}` 后缀防御
- `project_service.py`: 新增 `_dedupe_edit_ids()` 迁移方法，在 `open_project` 中调用，修复已有重复 id 的旧项目（O(n) 快速跳过无重复项目）
- `workflow_engine.py`: `_extract_edits_from_result` 补 `seen_ids` + `_dup{N}` 兜底防御

#### A-2.8: 智能删除提示词优化 + partial_delete 分组（spec 问题 3）

**修复**:
- `core/llm_prompts.py`: `_SMART_DELETE_SYSTEM` 新增第 4 条规则 `partial_delete`（单句内口误+修正不可整句删除），修订 `self_correct` 定义为跨片段口误，加 3 条 few-shot 示例
- `core/models.py`: `AnalysisResult` 新增可选 `category: str = ""` 字段
- `main.py`: `analysis_results` 透传 `category`；`edits` 对 `partial_delete` 用 `action="keep"` + 低 priority（10 vs 50）
- `frontend/src/types/project.ts`: `AnalysisResult` 接口加 `category?: string`
- `frontend/src/components/workspace/SuggestionPanel.vue`: 新增 `partial_delete` 分组，按 `analysis_id` 反查 `category`（`computed` 响应式），拆分到独立的"部分删除（需手动处理）"组

#### A-2.9: SuggestionPanel 批量操作 + 右键菜单（spec 问题 4）

**修复**:
- `core/project_service.py`: 新增 `update_edit_decisions_batch`（批量改状态）和 `delete_edit_decisions_batch`（永久删除 edits）
- `main.py`: 暴露 `update_edit_decisions_batch` + `delete_edit_decisions_batch` 接口
- `frontend/src/composables/useAnalysis.ts`: 新增 `resetEdit`、`batchUpdateEdits`、`deleteEdits` 函数
- `frontend/src/components/workspace/SuggestionPanel.vue`: 重构为完整右键菜单系统——单项右键（确认/忽略/撤销）、组右键（全部确认/全部忽略/全部撤销/删除本组 + 二次确认）

#### A-2.1: 播放头高亮 + 建议点击跳转

**修复**:
- `frontend/src/components/workspace/Timeline.vue`: 新增 `playheadSegmentId` computed（基于 `currentTime` 匹配 subtitle 段），`highlightedSegmentId` ref（外部点击临时高亮 2s），`listContainer` ref（scrollIntoView 滚动容器）
- `frontend/src/components/workspace/TranscriptRow.vue`: 新增 `isPlayheadInside` prop（蓝色左边框 + 浅蓝背景），`isHighlighted` prop（黄色 ring 高亮）；模板 `v-memo` 依赖新增这两项

#### A-2.2: 文本拖选 blur 误保存

**修复**: `TranscriptRow.vue` 的 `handleTextEditBlur` 改为延迟 150ms + 检查 `document.activeElement`——若 focus 回到另一个 `.edit-text-input`（拖拽到另一行），则忽略该 blur 事件。输入元素加 `edit-text-input` class 便于选择器识别。

#### A-2.3: SuggestionPanel 状态可视化

**修复**: `SuggestionPanel.vue` 重写分组逻辑——每组统计 `pendingCount`/`confirmedCount`/`rejectedCount` 并在组标题旁显示；单项根据 status 显示 `[Y]` 绿色（已确认）、`[N]` 灰色（已忽略）+ 删除线；确认/忽略按钮根据当前 status 条件显示；新增"撤销"按钮恢复 pending

#### A-2.4: split_segment EditDecision 继承/分割

**修复**: `core/project_service.py` 的 `split_segment` 方法完全重写 EditDecision 处理逻辑：
- `segment` 类型 ED → 克隆到 a/b 子段（更新 `target_id` + 裁剪 `start`/`end`），两段独立
- `range` 类型 ED 跨越分割点 → 切成两个（`_a` + `_b` 后缀）
- 非 target 分段或完全在一侧的 ED → 保持不变
- 旧代码 `hasattr(e, '_segment_ids')` 检测永假（EditDecision 无此字段），导致 ED 不会被分割

#### A-2.5: TimelineSwitcher dropdown 重命名关闭

**修复**: `TimelineSwitcher.vue` 将 `<div>` dropdown 改为 `<details>` 元素 + `dropdownOpen` ref 显式控制打开状态；重命名时 `dropdownOpen.value = true` 强制保持展开；`onToggle` 事件处理更新状态

#### A-2.6: in-app confirm modal 替代 window.confirm

**修复**: `WorkspacePage.vue` 新增 `confirmAction` 函数（基于 `<dialog>` + Promise），替换 `handleDeleteTimeline` 中的 `window.confirm`；新增 `confirmModalRef` + `confirmState` + `resolveConfirm` 逻辑；模板新增 `<dialog>` 模态框组件

#### A-2.10: 侧边栏可变宽度

**修复**: `Timeline.vue` 新增 `sidebarWidth` ref（从 `localStorage` 恢复）+ `SIDEBAR_MIN=320` + `SIDEBAR_MAX_RATIO=0.85`；左侧拖拽 handle（`onSidebarResizeStart` mousedown/mousemove/mouseup）；`window.resize` 动态更新最大值

#### A-2.11: 侧边栏按钮融入 UI

**修复**: 关闭按钮从独立 `absolute` 改为 Tab 栏行内元素（`flex-shrink-0` + `z-10`）；展开按钮去掉悬浮样式改为半透明扁平（`bg-white/40 backdrop-blur-sm`）；Tab 按钮 `min-w-0` + `truncate` 防溢出

#### A-2.12: 分割后时间戳右键分割按钮仅播放头内显示

**修复**: `TranscriptRow.vue` 右键菜单"在时间指针位置分割"加 `v-if="isPlayheadInside"` 条件

### 变更文件清单 (本审计)

#### 后端 (4 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `main.py` | A-2.7, A-2.8, A-2.9 | `_handle_smart_delete` id 加序号 + category 透传 + partial_delete 用 keep; 新增 `update_edit_decisions_batch` + `delete_edit_decisions_batch` expose; LLM handlers 返回 project 数据 |
| `core/project_service.py` | A-2.4, A-2.7, A-2.9 | `_dedupe_edit_ids` 迁移 + `add_analysis_results` 防御去重 + `update_edit_decisions_batch` + `delete_edit_decisions_batch` + `split_segment` ED 继承/分割重写 |
| `core/workflow_engine.py` | A-2.7 | `_extract_edits_from_result` id 唯一性兜底防御 |
| `core/llm_prompts.py` | A-2.8 | `_SMART_DELETE_SYSTEM` 新增 partial_delete + 修订 self_correct + few-shot 示例 |

#### 前端 (8 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `frontend/src/types/project.ts` | A-2.8 | `AnalysisResult` 接口加 `category?: string` |
| `frontend/src/composables/useAnalysis.ts` | A-2.9 | 新增 `resetEdit` + `batchUpdateEdits` + `deleteEdits` |
| `frontend/src/components/workspace/SuggestionPanel.vue` | A-2.3, A-2.8, A-2.9 | 状态可视化 + partial_delete 分组 + 右键菜单系统（单项/组级操作） |
| `frontend/src/components/workspace/Timeline.vue` | A-2.1, A-2.9, A-2.10, A-2.11 | 播放头高亮 + 侧边栏可变宽度 + 按钮融入 UI + resize handle + 事件转发 |
| `frontend/src/components/workspace/TranscriptRow.vue` | A-2.1, A-2.2, A-2.12 | playheadInside/highlighted props + blur 延迟保存 + edit-text-input class |
| `frontend/src/components/workspace/TimelineSwitcher.vue` | A-2.5 | `<details>` 显式状态控制 + rename focus |
| `frontend/src/pages/WorkspacePage.vue` | A-2.6, A-2.9 | in-app confirm modal + 批量操作接线 |

#### 测试 (1 文件)

| 文件 | 模块 | 变更 |
|------|------|------|
| `tests/test_project_service.py` | A-2.4 | `test_split_segment_inherits_and_independent_segment_edits` + `test_split_segment_cuts_range_edits_crossing_position` |

### 统计

- 修改文件: 14
- 新增文件: 0（均为修改已有文件）
- 后端净增: ~262 行
- 前端净增: ~744 行
- 测试净增: ~67 行

## 后续审计 (AUD-4)

> 待定


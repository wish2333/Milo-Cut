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
| A-01 | Timeline/Waveform 右键菜单互不关闭 | **待修复** |
| A-02 | Timeline 右键时间戳误进编辑模式 | **待修复** |
| A-03 | 编辑模式/选择模式下 Waveform/Timeline 操作行为混乱 | **待修复** |

### 修复规格概要

参见 `docs/2.1.1/audit-report-2.1.1-1.md`。

## 后续审计 (AUD-2)

> 待定


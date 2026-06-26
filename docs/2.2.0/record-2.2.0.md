# v2.2.0 规格与实施记录

## 概述

v2.2.0 聚焦于两个功能改进：
1. **字幕纠错集成 partial_delete 意见** -- 将快速清理的"部分删除"意见跟随 segment 发送给字幕纠错 LLM
2. **精华提取功能修复** -- 新增精华导出功能，修复 LLM 未配置时的手动管理体验

## 功能 A：字幕纠错集成 partial_delete 意见

### 背景

v2.1.1 中，字幕纠错 LLM 只接收 segment 的文本和时间戳信息，不感知前序"快速清理"（smart delete）的分析结果。其中 `partial_delete` 类别（句内含口误/重复，如"他是那段历史中的他是那段历史的亲历者"）对字幕纠错非常有价值。

### 实施

1. **`core/timeline_utils.py`**: 新增 `collect_partial_delete_hints()` 从 `AnalysisResult` 收集 `category="partial_delete"` 的提示文本
2. **`main.py:_handle_subtitle_correction`**: 收集 partial_delete hints 并附加到对应 segment dict 的 `edit_hint` 字段
3. **`core/llm_service.py:_build_structured_user_message`**: 支持 segment dict 中的 `edit_hint` 字段透传到 LLM 输入
4. **`core/llm_prompts.py`**: Mode A / Mode B 提示词新增 `edit_hint` 字段使用说明

### 数据流

```
AnalysisResult(category=partial_delete, detail="前半口误后半修正")
  -> collect_partial_delete_hints() -> {"s2": "前半口误后半修正"}
  -> segment dict["edit_hint"] = "前半口误后半修正"
  -> _build_structured_user_message() -> JSON payload 含 edit_hint
  -> LLM 提示词指导: "对于这类片段，请特别关注其句内的重复/口误部分"
```

## 功能 B：精华提取功能修复

### 问题

1. 导出界面没有精华导出按钮
2. 后端有 `get_highlight_ranges()` 但从未被实际调用
3. LLM 未配置时 UI 误导用户以为整个精华功能不可用

### 实施

#### B1: 精华导出（后端）

**设计决策**: 复用现有 FFmpeg 导出管道，通过"虚拟 edits"实现精华导出。精华范围 = 全片 - 非精华范围，将非精华范围标记为 confirmed delete，现有 `export_video`/`export_audio`/`export_srt` 自然只保留精华范围。

- **`core/export_service.py:build_highlight_export_edits()`**: 构建精华导出虚拟 edits
- **`core/export_service.py:get_highlight_ranges()`**: 修复支持 dict 格式 segments（之前只支持 Segment 对象）
- **`main.py:_get_export_segments_and_edits()`**: 新增辅助方法，当 `highlight_mode=true` 时使用虚拟 edits
- **4 个 export handler** 均已适配 highlight_mode

#### B2: 精华导出（前端）

- **`ExportPage.vue`**: 新增"精华视频""精华音频""精华字幕"导出按钮
- highlight_mode 通过 payload 传递，复用现有任务类型和进度跟踪

#### B3: 手动管理体验改进

- **`HighlightModeView.vue`**: LLM 未配置时改为引导文案"自动提取需要配置 LLM 连接。你也可以右键字幕片段手动加入精华"
- 空状态文案区分 LLM 已配置/未配置两种情况
- 后端 `add_highlight_segment` 从未门控 LLM 配置，手动添加始终可用

### 精华范围来源

精华范围来自 `AnalysisResult(type="llm_highlight")` 的 `segment_ids`，同时覆盖：
- LLM 自动提取的精华（source="llm_highlight"）
- 手动添加的精华（source="manual_highlight"，同样存储为 type="llm_highlight"）

## 测试

### 新增测试 (`tests/test_v2_2_0_features.py`, 15 个)

- `TestCollectPartialDeleteHints`: 3 个（空、有 reason、默认 reason）
- `TestBuildStructuredUserMessageEditHint`: 2 个（无 hint、有 hint）
- `TestGetHighlightRanges`: 3 个（dict segments、空、manual+llm）
- `TestBuildHighlightExportEdits`: 7 个（基础、空、开头、全覆盖、手动、trailing gap、重叠合并）

### 测试基线

- 后端单元测试: 384 通过 (+15 新增)
- 后端集成测试: 35 通过
- 前端测试: 169 通过 (预存 2 个失败除外)
- ruff + ESLint: 零错误（我修改的文件）
- frontend build: 成功

## 涉及文件

| 文件 | 改动 |
|------|------|
| `core/timeline_utils.py` | 新增 `collect_partial_delete_hints()` |
| `core/llm_service.py` | `_build_structured_user_message` 支持 edit_hint |
| `core/llm_prompts.py` | Mode A/B 提示词新增 edit_hint 说明 |
| `core/export_service.py` | 新增 `build_highlight_export_edits()`，修复 `get_highlight_ranges()` |
| `main.py` | `_handle_subtitle_correction` 集成 hints，4 个 export handler 支持 highlight_mode |
| `frontend/src/pages/ExportPage.vue` | 新增精华导出按钮和逻辑 |
| `frontend/src/components/workspace/HighlightModeView.vue` | UI 改进 |
| `tests/test_v2_2_0_features.py` | 新增 15 个测试 |

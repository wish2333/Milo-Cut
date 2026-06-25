# Milo-Cut v2.1.1 Release Notes

> **发布日期**: 2026-06-26
> **基准**: v1.3.0
> **分支**: `dev-2.1.1` → `main`
> **涵盖版本**: v2.0.0, v2.0.1, v2.1.0, v2.1.1

---

## 一、版本概述

v2.1.1 是 Milo-Cut 自 v1.3.0 以来最大的一次版本跃迁，跨越 4 个大版本，净增 **91 个 commits**，历时约 4 周开发。核心变化可归纳为三条主线：

1. **AI 能力全面引入** — 从零搭建 LLM 服务体系，实现智能删除、字幕修正、精华提取、语义搜索四大 AI 功能
2. **架构现代化** — 多 Timeline 架构重构、工作流引擎编排、HTTP 桥接 API 独立进程
3. **交互与质量升级** — 侧边栏内联化、字幕交互增强、7 轮审计 40+ 项 Bug 修复

---

## 二、v2.0.0 -- AI 基础设施与多 Timeline 重构

### Phase 1: 基础设施 (93f1917)

- 版本号单一事实来源：`core.__version__` 从 `pyproject.toml` 读取
- LLM 服务体系：`core/llm_service.py` 支持 OpenAI/Ollama/自定义 API
- HTTP 桥接 API：`core/bridge_service.py` 独立进程运行，`/api/v1/health` 端点
- LLM 设置面板：供应商选择、API Key、模型名、深度思考开关

### Phase 2: 核心功能 (b874ac5)

- Topic Drift 分析：检测演讲话题漂移并标记
- Bridge 文件协议：支持通过文件路径传递大型数据

### Phase 3: UI/UX 精炼 (f34d103)

- SplitPanel 分栏拖拽：波形图/字幕列表可调整比例
- 方向感知页面过渡动画
- `onMounted` 延迟加载优化首屏体验

### Phase 4a: 多 Timeline 基础设施 (e280368)

- `Timeline` 模型：每条 timeline 拥有独立的 transcript、edits、analysis
- `Project` v2 schema (`schema_version=2`)：多 timeline 列表 + 活动 timeline 切换
- v1 → v2 自动迁移逻辑

### Phase 4b: LLM 三大核心功能 (da1199d)

- **P0 智能删除 (Smart Delete)**：LLM 分析字幕片段，建议删除口误、重复、无关内容
- **P1 字幕修正 (Subtitle Correction)**：LLM 批量校正 ASR 识别错误
- Topic Drift 清除逻辑

### Phase 4c: LLM 补充功能 (705d41d)

- **P2 智能精华提取 (Highlight Extraction)**：LLM 从长视频中识别高光片段
- **P3 语义搜索 (Semantic Search)**：自然语言查询定位视频片段

### Phase 4d: 集成测试 (86b31c6)

- `main.py` 代码按功能 region 分区
- 端到端集成测试补充

---

## 三、v2.0.1 -- UI 修补

- Dropdown 透明背景修复
- 深色导航栏按钮可见性
- v2.0.0 发布后 spec 审计修正

---

## 四、v2.1.0 -- AI 工作流与提示词系统

### Phase 1: 提示词风格预设 (68f28f6)

- 预设 CRUD（创建/读取/更新/删除）
- 内置默认保护（系统预设不可编辑/删除）
- 设置页预设管理 UI
- config 浅拷贝修复

### Phase 2: AI 助手面板 (3bdedda)

- 三 Tab 切换（智能删除 / 字幕修正 / 精华提取）
- 功能卡片式布局
- P0 结果合并（多批次结果自动去重合并）
- P1 字幕修正全屏 diff 审阅视图

### Phase 3: 提示词编辑系统 (1781e2c)

- 标记位注入（`{transcript}`, `{context}` 等）
- 分层持久化（系统默认 → 用户覆盖）
- 双模式编辑 UI（基础/高级）

### Phase 4: 工作流引擎与设置全屏化

- **工作流引擎** (`core/workflow_engine.py`)：步骤编排、依赖管理、累积模式 handler
- **工作流 UI**：模式切换、配置面板、执行面板、冲突解决视图
- **设置页全屏化**：Teleport 覆盖层、ESC 关闭、Tab 中文化
- 预设选择器、失败对话框、悲观锁
- 补充 35 个工作流引擎单测 + 20 个集成测试 + 22 个前端测试

---

## 五、v2.1.1 -- 质量收敛与交互增强

### M1: P0 Bug 修复

- **Analysis 功能崩溃修复**：多 Timeline 重构后 handler 读取旧 `project.transcript.segments` 导致崩溃，新建 `_get_target_timeline(task)` helper 统一获取活动 timeline
- **取消任务状态错误修复**：`_execute_task` 区分 `CANCELLED` 与 `FAILED` 状态，新增 `TASK_CANCELLED` 事件；前端 toast 正确显示"已取消"

### M2: LLM 参数可配置

新增 7 个可配置参数并接入 SettingsModal LLM Tab「高级参数」折叠区：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `llm_smart_batch_size` | 20 | 智能删除批次大小（条数） |
| `llm_smart_overlap_size` | 4 | 智能删除重叠条数 |
| `llm_correction_batch_size` | 30 | 字幕修正批次大小 |
| `llm_correction_context_window` | 5 | 字幕修正上下文窗口 |
| `llm_highlight_chunk_duration` | 1800.0 | 精华提取窗口（秒） |
| `llm_highlight_overlap_duration` | 60.0 | 精华提取重叠（秒） |
| `llm_concurrency` | 5 | LLM 并发数 |

### M3: LLM Chunk 级并发

- `smart_delete` 与 `subtitle_correction` 改为 `ThreadPoolExecutor` 并发提交 chunk/batch
- 结果按原始顺序合并，单块失败不影响其他块
- 429 自适应降级：连续 3 次限流 → 剩余 chunk 串行执行

### M4: 字幕交互增强

- **多选模式**：工具栏切换、Ctrl/Shift 范围选、ESC 清空、Enter 合并、Delete 批量删除
- **时间微调**：±0.1s 方向键、Shift ±1.0s
- **合并/分割**：多选合并、右键分割（中点切分）
- **搜索入口**：Timeline 工具栏搜索图标按钮（与 Ctrl+F 双入口共存）

### M5: 文档完善

- `docs/2.1.1/record-2.1.1.md` 实施记录
- `docs/2.1.1/spec-v2.1.1.md` 规格文档

### M6: isDirty watch 竞态修复

- Vue `watch(isDirty, ...)` 改用 `onCleanup` 回调模式
- 修复连续操作时 auto-save timer 不重置导致数据丢失的问题

### M7: 移除 Analysis 规则引擎

- 全链路清理 `core/analysis_service.py`（332 行删除）
- `TaskType` 移除 `FILLER_DETECTION` / `ERROR_DETECTION` / `FULL_ANALYSIS`
- `AnalysisResult.type` 缩减为 `llm_smart_delete | llm_subtitle_correction | llm_highlight`
- 前后端共 25 个文件修改，353/353 测试通过

### AUD-1: 交互修复

- Timeline/Waveform 右键菜单互不关闭 → 全局关闭事件广播
- 时间戳右键误进编辑模式 → `mousedown` button check
- 编辑模式/选择模式下操作行为统一 → 三态逻辑拆分

### AUD-2: 编码器列表动态渲染

- SettingsModal Export section 的 Video codec 下拉框从硬编码 10 个编码器改为按 `detect_gpu_encoders` API 返回值动态渲染
- macOS 上正确只显示 videotoolbox（而非错误显示 nvenc/qsv/amf）

### AUD-3: 侧边栏与建议面板修复 (12 项)

| ID | 修复内容 |
|----|----------|
| A-2.1 | 播放头定位高亮 + 建议点击后文本行跳转 + scrollIntoView |
| A-2.2 | 文本拖选编辑 blur 时误保存 → 延迟 150ms + `activeElement` 检查 |
| A-2.3 | SuggestionPanel 状态可视化（已确认/已忽略标识 + 组统计） |
| A-2.4 | `split_segment` 后 EditDecision 正确继承/分割 |
| A-2.5 | TimelineSwitcher dropdown 重命名时保持展开 |
| A-2.6 | `window.confirm` 替换为 in-app `<dialog>` 模态框 |
| A-2.7 | AI 智能删除 id 重复 → 三层防御（序号 + 去重 + 迁移） |
| A-2.8 | 智能删除提示词新增 `partial_delete` 分类（半句口误+修正） |
| A-2.9 | SuggestionPanel 批量操作 + 右键菜单（全部确认/忽略/删除整组） |
| A-2.10 | 侧边栏可变宽度（320px-85vw，拖拽 handle + localStorage 记忆） |
| A-2.11 | 侧边栏关闭按钮融入 Tab 栏 UI |
| A-2.12 | 分割后时间戳右键"在时间指针位置分割"仅播放头内显示 |

### AUD-4: AI 智能删除输入过滤 + 条数分块模式

- **输入过滤**：`collect_confirmed_deleted_seg_ids()` 公共 helper，smart_delete/subtitle_correction/highlight 输入自动忽略用户已确认删除的段落
- **条数分块**：智能删除从时间窗口模式（60s 窗口 + 10s 重叠）改为条数批次模式（默认 20 条 + 4 条重叠），`chunk_transcript_by_count()` P1 式 batch+target 分块
- 旧设置键自动迁移（`llm_smart_window_duration` → `llm_smart_batch_size`）
- 17 项审计修正（P0×2 + P1×2 + P2×13）

### Spec-6: UI/UX 优化 (5 批次, 13 commits)

| 批次 | 内容 |
|------|------|
| 第零批 | 字幕修正 `timeline_id` NameError 崩溃修复 |
| 第一批 | 拖拽 guard + 时间编辑步进修复 + 移除 ± 按钮 |
| 第二批 | 精华提取数据修复：过滤已删除段落 + 移除 EditDecision 污染 + adapt jump_cuts |
| 第三批 | 侧边栏内联化：从 `<Teleport to="body">` 浮动层改为 Timeline flex 子元素，默认展开 |
| 第四批 | P1/P2 视觉精炼：快捷键 Tab、HighlightModeView 密度圆点、字幕修正 toast、精华右键增删 API、Ctrl+F/I/O/Ctrl+Shift+A/D 快捷键、按钮 `active:scale-95` + `rounded-md` 统一 |

### Spec-9: 代码审查修复批次

- **P0 (Critical)**：`remove_highlight_segment` 在 Pydantic 模型上误用 `.get()` + 直接赋值 frozen 模型导致崩溃 → 改用属性访问 + `model_copy(update=...)`
- **M1 (Medium)**：`add_analysis_results` 运算符优先级陷阱 → 显式 `if target_type is not None` 重构
- **M2 (Medium)**：Timeline 死代码 emit 桥接移除
- **L1 (Low)**：`_migrate_highlights` orphan 清理泛化为任意 source
- **L2 (Low)**：测试 `_ServiceStub` 消除 70+ 行重复逻辑，改用真实 `ProjectService`
- **L3 (Low)**：`reasonix.toml` 确认在 `.gitignore` 中

### UI 修复补丁

- SuggestionPanel 移除"撤销"按钮 + "全部撤销本组"菜单项
- `partial_delete` 分类 EditDecision 默认 status 改为 `REJECTED`（保留而非删除）
- 字幕纠错完成回调补调用 `loadCorrections` 修复"查看修正结果"不出现
- `add_highlight_segment` / `remove_highlight_segment` 返回完整 `project` → 前端实时刷新

---

## 六、已知问题

> 以下功能已在 v2.1.1 中内置但在标记场景中不可用，将在 v2.2.0 中修复。

| 功能 | 问题 | 影响 |
|------|------|------|
| **精华提取导出** | 导出界面缺少精华内容的导出按钮，后端导出管线未对接用户手动增删操作 | 精华提取功能实际不可用于最终输出 |
| **精华提取手动管理** | 未验证在 LLM 配置缺失时用户能否完全手动添加/管理精华 | 无 LLM 配置时功能可能冻结 |
| **工作流模式** | 开发至今未进行充分的端到端功能验证 | 可能存在未发现的流程阻断 Bug |

---

## 七、技术统计

| 指标 | 数值 |
|------|------|
| 覆盖版本 | v2.0.0 + v2.0.1 + v2.1.0 + v2.1.1 |
| 总 commits | 91 |
| 新增/删除文件 | `core/llm_service.py`, `core/llm_prompts.py`, `core/workflow_engine.py`, `core/bridge_service.py`, `core/timeline_utils.py` 等 20+ |
| 删除文件 | `core/analysis_service.py`, `tests/test_analysis_service.py` |
| 修改文件 | 50+ |
| 后端测试 | 367/367 通过 |
| 前端测试 | 169 passed, 2 failed (既有问题，非本次引入) |
| 审计轮次 | 7 轮 (AUD-1 至 AUD-4, Spec-6, Spec-9, review patch) |

---

## 八、致谢

本版本由 AI 辅助开发完成，采用 Subagent-Driven Development 方法论，多轮审计保障代码质量。

---

*Release prepared by Reasonix on 2026-06-26*

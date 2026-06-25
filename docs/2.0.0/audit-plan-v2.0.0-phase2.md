# Milo-Cut v2.0.0 Phase 2 执行计划

> Version: 1.0
> Date: 2026-06-12
> Baseline: audit-plan-v2.0.0.md Phase 2 + record-2.0.0.md (Phase 1 已完成)
> Scope: Topic Drift 完整实现 + Bridge Service 文件协议
> Status: **已完成** (2026-06-13)

---

## 0. 当前进度确认

### Phase 1 (Foundation) -- 已完成 (commit 93f1917)

| 任务 | 状态 | 关键交付 |
|------|------|----------|
| Task 1.4: 单一版本源 | 已完成 | `core/__init__.py` importlib.metadata + tomllib |
| Task 1.1: LLM 服务架构 | 已完成 | `core/llm_service.py` -- call_llm, test_connection, estimate_tokens, chunk_transcript |
| Task 1.3: HTTP API 桥接 | 已完成 | `core/bridge_service.py` -- health/projects/timeline/analyze 端点 |
| Task 1.2: LLM 设置面板 | 已完成 | `SettingsModal.vue` LLM 选项卡 + `useLlmSettings.ts` |

Phase 1 测试覆盖: 17 LLM + 8 Bridge = 25 个新测试, 全部通过。

### Phase 1 遗留技术决策

1. **LLM SDK**: 实际使用了 `openai` Python SDK (而非 audit-plan 原定的裸 `httpx`), 因其内置流式、重试、类型提示 -- Phase 2 维持此决策。
2. **LLM 设置面板**: 嵌入 `SettingsModal.vue` 作为选项卡 (而非独立 `LlmSettingsPanel.vue`), Phase 2 维持。
3. **AnalysisResult.type**: 当前 Literal 为 `"filler" | "error" | "duplicate" | "punctuation"` -- Phase 2 需扩展以支持 topic drift 结果。

---

## 1. Phase 2 范围

### 本阶段任务 (来自 audit-plan-v2.0.0.md Phase 2)

| 任务 | 工时 | 依赖 | 状态 |
|------|------|------|------|
| Task 2.1: Topic Drift 后端 | 3 pd | Task 1.1 (已完成) | **已完成** |
| Task 2.2: Topic Drift 前端 | 3 pd | Task 2.1 + Task 1.2 | **已完成** |
| Task 2.3: Bridge Service 文件协议 | 1 pd | Task 1.3 (已完成) | **已完成** |
| **Phase 2 合计** | **7 pd** | | **已完成** |

### 审计修复项 (并入本阶段)

| 修复项 | 工时 | 来源 | 并入任务 |
|--------|------|------|----------|
| LLM Chunking Strategy (backend) | 1 pd | B-03 | Task 2.1 |
| LLM Chunking Merge (frontend) | 0.5 pd | B-03 | Task 2.2 |
| Token Estimation Utility | 0.5 pd | M-02 | 已在 Phase 1 完成 |
| Emotion Confidence Schema | 0.5 pd | M-01 | 延后 (Emotion Analysis 推迟至 v2.1) |

### Phase 2 总计: 9 pd (含审计修复)

---

## 2. Task 2.1: Topic Drift 后端 [3.5 pd]

> 目标: 在 LLM 服务中实现 Topic Drift 分析, 支持分块、流式进度、缓存、降级

### 2.1.1 数据模型扩展

**文件**: `core/models.py`

- 扩展 `AnalysisResult.type` Literal, 新增 `"topic_drift"` 类型
  - 当前: `Literal["filler", "error", "duplicate", "punctuation"]`
  - 目标: `Literal["filler", "error", "duplicate", "punctuation", "topic_drift"]`
- 新增 `TopicDriftResult` 模型 (独立于 AnalysisResult, 用于 LLM 返回结构化结果):
  ```
  class TopicDriftResult(BaseModel, frozen=True):
      segment_id: str
      topic: str = ""
      relevance: float = 1.0   # 0.0-1.0
      confidence: float = 1.0  # 0.0-1.0
      reason: str = ""
  ```
- 新增 `TopicDriftData` 模型 (存储在 Project 中, 支持缓存):
  ```
  class TopicDriftData(BaseModel, frozen=True):
      topic_description: str = ""
      results: list[TopicDriftResult] = Field(default_factory=list)
      transcript_hash: str = ""
      last_run: str | None = None
      token_usage: dict = Field(default_factory=dict)
  ```
- 在 `Project` 模型新增字段: `topic_drift: TopicDriftData = Field(default_factory=TopicDriftData)`

**验证**:
- [ ] `TopicDriftResult` 序列化/反序列化测试
- [ ] `TopicDriftData` frozen 不可变性测试
- [ ] `Project` 含 topic_drift 字段的 round-trip 测试

### 2.1.2 Topic Drift 核心逻辑

**文件**: `core/llm_service.py` (MODIFY)

- 新增 `analyze_topic_drift()` 函数:
  ```
  def analyze_topic_drift(
      segments: list[dict],
      topic_description: str = "",
      *,
      config: LlmConfig | None = None,
      cancel_event: threading.Event | None = None,
      progress_cb: Callable[[float, str], None] | None = None,
      chunk_callback: Callable[[list[dict]], None] | None = None,
  ) -> dict[str, Any]:
  ```
  - 使用已有的 `chunk_transcript()` 分块 (5 min, 30s overlap)
  - 对每个 chunk 构建 prompt, 调用 `call_llm()`
  - 解析 LLM 返回的 JSON 为 `list[TopicDriftResult]`
  - 通过 `chunk_callback` 逐块返回结果 (流式, 不等全部完成)
  - 通过 `progress_cb` 上报进度 (chunk_index / total_chunks)
  - 累计 token_usage, 通过返回值传出
  - 返回: `{"success": True, "data": {"results": [...], "token_usage": {...}}}`

- Topic Drift prompt 模板:
  - System: `"你是一位视频内容分析专家。分析以下视频转录片段与给定主题的相关性。"`
  - User: 包含 topic_description + segments 文本 + JSON 输出格式要求
  - 输出 schema: `[{"segment_id": str, "topic": str, "relevance": float, "reason": str}]`

- LLM 响应解析 (`_parse_topic_drift_response()`):
  - 从 markdown code block 或纯 JSON 中提取
  - 容错: 字段缺失时使用默认值
  - 容错: relevance 超出 [0,1] 时 clamp

- 降级处理: 若 `config.is_configured() == False`, 直接返回 `{"success": False, "error": "LLM not configured"}`, 前端据此隐藏 Topic Drift 入口

**验证**:
- [ ] `analyze_topic_drift()` 使用 mock LLM 返回的完整流程测试
- [ ] JSON 解析容错 (markdown 包裹、字段缺失、relevance 越界)
- [ ] chunk_callback 被正确调用 (逐块)
- [ ] cancel_event 中断时返回 Cancelled

### 2.1.3 任务系统集成

**文件**: `main.py` (MODIFY)

- 在 `_register_task_handlers()` 注册 `TaskType.LLM_TOPIC_DRIFT` -> `self._handle_topic_drift`
- 新增 `_handle_topic_drift(self, task, cancel_event, progress_cb)`:
  - 从 task.payload 取 `topic_description`
  - 取当前项目的 transcript segments
  - 调用 `analyze_topic_drift()`, 传入 cancel_event 和 progress_cb
  - chunk_callback 内通过 `self._emit()` 发送 `llm:analysis_progress` 事件 (含 chunk 结果)
  - 完成后: 存储结果到 project.topic_drift, 发送 `llm:analysis_completed`
  - token_usage 通过 `llm:token_usage` 事件发出
  - 失败时发送 `llm:analysis_failed`

- 新增 `@expose` 方法:
  - `start_topic_drift(self, topic_description: str = "") -> dict`
    - 创建 LLM_TOPIC_DRIFT 任务, payload 含 topic_description
    - 返回 task_id
  - `get_topic_drift_results(self) -> dict`
    - 读取当前 project.topic_drift, 返回结果列表
    - 若无结果返回空列表 (非错误)

**验证**:
- [ ] 任务创建 -> 启动 -> 进度事件 -> 完成事件 全链路测试 (mock)
- [ ] 缓存: 二次调用 get_topic_drift_results 返回已存结果
- [ ] 降级: LLM 未配置时 start_topic_drift 返回明确错误

### 2.1.4 Bridge HTTP 端点扩展

**文件**: `core/bridge_service.py` (MODIFY)

- 新增 `GET /api/v1/projects/{name}/topic-drift` 端点:
  - 返回项目的 topic_drift 缓存结果
  - 注入新回调: `get_topic_drift_fn: Callable[[str], dict | None]`

**验证**:
- [ ] 端点返回缓存结果
- [ ] 无结果时返回空列表

---

## 3. Task 2.2: Topic Drift 前端 [3.5 pd]

> 目标: Topic Drift 面板 UI + composables + SuggestionPanel 集成

### 3.2.1 TopicDriftPanel 组件

**文件**: `frontend/src/components/workspace/TopicDriftPanel.vue` (NEW)

- Props: `results: TopicDriftResult[]`, `loading: boolean`, `llmConfigured: boolean`
- Emits: `start-analysis: [topicDescription: string]`, `cancel: []`, `accept-all: []`, `reject-all: []`, `seek: [time: number]`
- 布局:
  - 顶部: topic_description 输入框 (可选) + "开始分析" 按钮 (LLM 未配置时 disabled + tooltip)
  - 进度区: streaming 进度条 (0-100%), 显示当前 chunk / total chunks
  - 结果列表: 基于 segment_id 的 upsert 渲染
    - 每条: 时间戳 + 文本预览 + topic 标签 + relevance 徽章
    - 颜色: relevance >= 0.7 绿色 (保留), < 0.4 红色 (删除), 否则黄色 (待定)
  - 批量操作: "接受所有建议" / "拒绝所有"
  - 离线状态: LLM 未配置时显示提示 "需要配置 LLM 才能使用主题漂移分析"

- Upsert 逻辑: 同一 segment_id 的结果, 后到的覆盖先到的 (处理 overlap 区域去重, 无闪烁)

**验证**:
- [ ] 组件渲染测试 (空结果、有结果、loading 状态)
- [ ] upsert: 重复 segment_id 不产生重复条目
- [ ] 颜色编码: 三档 relevance 正确着色
- [ ] LLM 未配置时按钮 disabled

### 3.2.2 Composables

**文件**: `frontend/src/composables/useTopicDrift.ts` (NEW)

```typescript
export function useTopicDrift() {
  const results = ref<TopicDriftResult[]>([])
  const loading = ref(false)
  const progress = ref(0)
  const error = ref<string | null>(null)

  async function startAnalysis(topicDescription?: string): Promise<string | null>
  // 创建任务, 注册事件监听, 返回 task_id

  async function loadResults(): Promise<void>
  // 调用 get_topic_drift_results 加载缓存

  function cancelAnalysis(): void
  // 调用 cancel_task

  // 事件处理: llm:analysis_progress -> upsert results + update progress
  //           llm:analysis_completed -> loading=false
  //           llm:analysis_failed -> error + loading=false

  return { results, loading, progress, error, startAnalysis, loadResults, cancelAnalysis }
}
```

- upsert 实现: 收到 chunk 结果时, 按 segment_id 合并到 results (Map 去重)
- 生命周期: useBridge() 自动管理事件监听注册/卸载

**文件**: `frontend/src/composables/useLlmAnalysis.ts` (NEW)

- 共享 LLM 分析生命周期状态机
- Token usage 展示: 暴露 `tokenUsage` reactive ref
- 监听 `llm:token_usage` 事件累加

**验证**:
- [ ] useTopicDrift: startAnalysis 触发任务创建
- [ ] useTopicDrift: progress 事件正确更新 results 和 progress
- [ ] useTopicDrift: cancel 后 loading 归 false
- [ ] useLlmAnalysis: token usage 累加正确

### 3.2.3 WorkspacePage 集成

**文件**: `frontend/src/components/WorkspacePage.vue` (MODIFY)
**文件**: `frontend/src/components/workspace/SuggestionPanel.vue` (MODIFY)

- SuggestionPanel 新增 "主题漂移" tab (与现有 口头禅/口误/静音 并列)
- SuggestionPanel 改为 tab 式布局:
  - Tab 1: 规则分析 (filler/error/silence -- 现有逻辑)
  - Tab 2: 主题漂移 (TopicDriftPanel)
- WorkspacePage 传递 `segments`、`llmConfigured` 给 SuggestionPanel
- TopicDriftPanel 的 accept-all/reject-all 转换为 EditDecision 并写入 project

**验证**:
- [ ] Tab 切换正常
- [ ] 规则分析 tab 不受影响 (无回归)
- [ ] TopicDriftPanel 正确接收 props

### 3.2.4 类型定义

**文件**: `frontend/src/types/project.ts` (MODIFY) 或 `frontend/src/types/edit.ts`

- 新增 `TopicDriftResult` 接口:
  ```typescript
  interface TopicDriftResult {
    segment_id: string
    topic: string
    relevance: number
    confidence: number
    reason: string
  }
  ```

---

## 4. Task 2.3: Bridge Service 文件协议 [1 pd]

> 目标: 基于 JSONL 文件的桥接协议, 作为 HTTP API 的补充

### 2.3.1 文件协议核心

**文件**: `core/bridge_service.py` (MODIFY)

- 新增 `FileProtocolManager` 类:
  ```
  class FileProtocolManager:
      def __init__(self, base_dir: Path | None = None):
          # base_dir 默认: APPDATA/milo-cut/bridge/
          # self.outgoing = base_dir / "outgoing"
          # self.incoming = base_dir / "incoming"
          # self.archive = base_dir / "archive"

      def publish(self, data_type: str, payload: dict) -> dict:
          # 写 .milo.jsonl 到 outgoing/
          # 原子写入: temp file -> os.replace()
          # 文件名: {timestamp}_{data_type}.milo.jsonl

      def poll_incoming(self) -> list[dict]:
          # 扫描 incoming/*.milo.jsonl
          # 解析每行 JSON
          # 处理后移到 archive/

      def start_polling(self, interval: float = 2.0):
          # 启动后台轮询线程

      def stop_polling(self):
          # 停止轮询
  ```

- 数据类型 (`data_type`):
  - `edit_timeline`: 转录片段时间 + 编辑动作
  - `analysis_results`: 分析结果摘要
  - `topic_drift`: 主题漂移分析结果

- 文件格式: JSONL (每行一个 JSON 对象, 支持流式追加)
  ```jsonl
  {"type": "segment", "id": "seg-1", "start": 0.0, "end": 2.5, "action": "delete"}
  {"type": "segment", "id": "seg-2", "start": 2.5, "end": 5.0, "action": "keep"}
  ```

- 关键实现细节:
  - **原子写入**: `tempfile.NamedTemporaryFile` -> `os.replace()` (非 `os.rename()`, Windows 兼容)
  - **轮询间隔**: 2s (非 500ms, 减少 IO 开销)
  - **文件归档**: 处理后 `os.replace(incoming/file, archive/file)`
  - **线程安全**: `_lock = threading.Lock()` 保护文件操作

**验证**:
- [ ] publish 写入文件, 内容正确
- [ ] publish 原子性: 中断不产生半写文件
- [ ] poll_incoming 正确解析 + 归档
- [ ] 轮询线程 start/stop 生命周期
- [ ] Windows os.replace 覆盖测试

### 2.3.2 BridgeService 集成

**文件**: `main.py` (MODIFY)

- 在 `MiloCutApi.__init__` 中创建 `FileProtocolManager` 实例
- 项目保存时自动 publish `edit_timeline` (hook 到 project_service 保存流程)
- 分析完成时自动 publish `analysis_results` 和 `topic_drift`
- 启动轮询消费 incoming 消息 (可选: 目前 MVP 仅 publish, incoming 消费为预留)

**验证**:
- [ ] 项目保存后 outgoing 目录有文件
- [ ] 文件内容包含 segments + edits

---

## 5. 测试计划

### 5.1 后端单元测试

**文件**: `tests/test_topic_drift.py` (NEW)

| 测试 | 覆盖 |
|------|------|
| test_topic_drift_result_model | TopicDriftResult 序列化 |
| test_topic_drift_data_frozen | TopicDriftData 不可变 |
| test_project_with_topic_drift | Project round-trip 含 topic_drift |
| test_analyze_topic_drift_mock | mock LLM 完整流程 |
| test_parse_response_markdown | markdown code block 解析 |
| test_parse_response_field_missing | 字段缺失容错 |
| test_relevance_clamp | relevance 越界 clamp |
| test_chunk_callback_per_chunk | chunk_callback 逐块调用 |
| test_cancel_event | 取消中断 |

**文件**: `tests/test_file_protocol.py` (NEW)

| 测试 | 覆盖 |
|------|------|
| test_publish_writes_file | publish 写入 |
| test_publish_atomic | 原子写入 |
| test_poll_incoming_parse | 解析 incoming |
| test_poll_incoming_archive | 归档 |
| test_polling_lifecycle | 轮询线程 start/stop |

### 5.2 前端测试

**文件**: `frontend/src/components/workspace/TopicDriftPanel.test.ts` (NEW)

| 测试 | 覆盖 |
|------|------|
| renders empty state | 空结果渲染 |
| renders results | 有结果渲染 |
| upsert no duplicates | segment_id 去重 |
| relevance color coding | 三档颜色 |
| disabled when unconfigured | LLM 未配置 |

### 5.3 回归验证

- [ ] `uv run pytest` 全部通过 (含新测试)
- [ ] `cd frontend && bun run build` 零错误
- [ ] `cd frontend && bun run test` 全部通过
- [ ] 现有规则分析 (filler/error) 不受影响

---

## 6. 依赖与执行顺序

```
Task 2.1 Topic Drift 后端
  2.1.1 数据模型 ──────┐
  2.1.2 核心逻辑 ──────┤ (依赖 2.1.1)
  2.1.3 任务集成 ──────┤ (依赖 2.1.2)
  2.1.4 HTTP 端点 ─────┘ (依赖 2.1.1)
         │
         v
Task 2.2 Topic Drift 前端
  3.2.4 类型定义 ──────┐
  3.2.2 composables ──┤ (依赖 2.1.3 的 @expose)
  3.2.1 TopicDriftPanel ┤ (依赖 3.2.2 + 3.2.4)
  3.2.3 集成 ──────────┘ (依赖 3.2.1)

Task 2.3 文件协议 (与 2.1/2.2 并行)
  2.3.1 FileProtocolManager ─┐
  2.3.2 集成 ────────────────┘
```

**推荐顺序**: 2.1 (全部) -> 2.2 (全部) -> 2.3 (并行可提前启动)

---

## 7. 验收标准 (Phase 2 Gate)

- [ ] Topic Drift: 对测试视频发起分析, 流式显示逐块结果
- [ ] Topic Drift: 结果含 relevance 评分, 批量接受/拒绝工作正常
- [ ] Topic Drift: LLM 未配置时入口隐藏/禁用, 规则分析不受影响
- [ ] Topic Drift: 30 分钟视频通过分块完成分析, 无截断
- [ ] 文件协议: 项目保存后 outgoing/ 生成 .milo.jsonl 文件
- [ ] 文件协议: incoming/ 文件被正确解析并归档到 archive/
- [ ] HTTP API: 新增 topic-drift 端点响应正确
- [ ] 后端测试: `uv run pytest` 通过, 新代码覆盖率 >= 80%
- [ ] 前端构建: `bun run build` 零错误
- [ ] 前端测试: `bun run test` 通过
- [ ] 无回归: 现有功能 (silence detection, export, waveform, 规则分析) 不受影响

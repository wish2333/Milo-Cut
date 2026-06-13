# v2.0.0 AI 驱动 -- 实施记录

> **版本**: 2.0.0
> **主题**: AI 驱动 -- LLM 分析服务、HTTP API 桥接、全局步骤导航
> **基准**: v1.3.0 (已发布)
> **分支**: `dev-1.3.0`
> **计划文档**: `docs/2.0.0/audit-plan-v2.0.0.md`
> **审计报告**: `docs/2.0.0/audit-report-v2.0.0.md`
> **PRD**: `docs/2.0.0/PRD-v2.0.0.md`

---

## 概要

v2.0.0 Phase 1 (Foundation) 为 Milo-Cut 建立三大基础能力:

1. **单一版本源** -- `pyproject.toml` 作为唯一版本号来源, 所有构建脚本和前端自动同步
2. **LLM 服务层** -- 基于 OpenAI SDK 的统一 LLM 调用服务, 支持 OpenAI/DeepSeek/Qwen/Ollama 等兼容 API, 内置重试、流式、分块和 Token 估算
3. **HTTP API 桥接** -- stdlib http.server 实现的本地 REST API, 供外部工具 (如 Milo-Cut Neo) 查询项目状态和触发分析
4. **LLM 设置面板** -- 在 SettingsModal 中新增 LLM 配置选项卡, 含 Provider 选择、API Key 管理、连接测试

---

## 变更文件 (共 22 个)

### 后端 (12 个文件)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/__init__.py` | 重写 | `_read_version()` 从 pyproject.toml 读取版本, importlib.metadata + tomllib 双重回退 |
| `core/llm_service.py` | 新增 | LLM 服务核心: `call_llm()`, `test_connection()`, `estimate_tokens()`, `chunk_transcript()` |
| `core/bridge_service.py` | 新增 | HTTP API 桥接: `/api/v1/health`, `/projects`, `/projects/{name}/timeline`, `/analyze` |
| `core/models.py` | 修改 | 新增 `LlmProvider` 枚举、`LlmConfig` 模型、`LLM_TOPIC_DRIFT` 任务类型 |
| `core/events.py` | 修改 | 新增 4 个 LLM 事件: `llm:analysis_progress/completed/failed`, `llm:token_usage` |
| `core/config.py` | 修改 | 新增 6 个 LLM 默认设置项 (provider, base_url, api_key, model, temperature, timeout) |
| `main.py` | 修改 | 移除 `_get_version()`, 改用 `core.__version__`; 新增桥接回调和 LLM bridge 方法 (test_llm_connection, get_llm_config, update_llm_config, get_bridge_status); 启动时初始化 BridgeService 并注册 atexit 清理 |
| `app.spec` | 修改 | 新增 `_read_version()`, 动态 CFBundleVersion; 打包 pyproject.toml 到 datas |
| `build.py` | 修改 | 新增 `_read_version()`, Android buildozer 版本从 pyproject.toml 读取; onefile 模板添加 "core" hiddenimport 和 pyproject.toml datas |
| `pyproject.toml` | 修改 | 新增 `openai>=1.0` 依赖 |
| `tests/test_llm_service.py` | 新增 | 17 个测试: Token 估算 (5), LlmConfig (6), chunk_transcript (5), 配置读取 (1) |
| `tests/test_bridge_service.py` | 新增 | 8 个测试: health 端点, CORS, 404, projects 回调, 无回调降级, 生命周期管理 |

### 前端 (5 个文件)

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 | 新增 LLM 选项卡: Provider 下拉 (OpenAI/DeepSeek/Qwen/Custom)、Base URL、API Key (含显示/隐藏)、Model、Temperature 滑块、Test Connection 按钮、Ollama 自动检测 |
| `frontend/src/composables/useLlmSettings.ts` | 新增 | LLM 设置 composable: `testConnection()` 返回连接状态 |
| `frontend/src/types/edit.ts` | 修改 | `AppSettings` 接口新增 6 个 llm_* 字段 |
| `frontend/src/utils/events.ts` | 修改 | 新增 4 个 LLM 事件常量 (与 `core/events.py` 同步) |
| `frontend/package.json` | 修改 | 新增 `sync-version` 脚本 + `prebuild` 钩子, 自动从 pyproject.toml 同步版本号 |

### 文档 (3 个文件)

| 文件 | 说明 |
|------|------|
| `docs/2.0.0/PRD-v2.0.0.md` | v2.0.0 产品需求文档 |
| `docs/2.0.0/audit-report-v2.0.0.md` | PRD 审计报告 |
| `docs/2.0.0/audit-plan-v2.0.0.md` | 执行计划 (4 阶段, 25 人天) |

---

## 架构决策

### LLM 服务 -- 选择 OpenAI SDK

- 使用官方 `openai` Python 库而非裸 `httpx`, 因其内置流式、重试、类型提示
- 不设置 `max_tokens`, 让模型自由输出完整分析结果 (适合长视频 Topic Drift 场景)
- 超时默认 120s (长文本分析需要足够时间)

### HTTP 桥接 -- 选择 stdlib http.server

- 与现有 `media_server.py` 保持一致, 零新依赖
- 回调注入模式: BridgeService 通过构造函数接收 `get_projects_fn` 等回调, 避免耦合具体服务
- 使用 `staticmethod()` 包装防止 Python 将回调类属性误绑为实例方法

### 版本管理 -- pyproject.toml 单一事实来源

- `core/__init__.py` 提供运行时版本读取 (importlib.metadata + tomllib 回退)
- `app.spec` / `build.py` 各自读取 pyproject.toml (打包时 pyproject.toml 必须 accessible)
- `frontend/package.json` 在 build 前自动同步 (prebuild 钩子)

### LLM 设置 -- 嵌入现有 SettingsModal

- 新增 LLM 选项卡而非独立面板, 保持设置入口统一
- Provider 切换时自动填充 Base URL 和 Model 默认值
- API Key 前端不持久化明文, 仅通过 `update_llm_config` 写入后端 settings.json

---

## 测试覆盖

| 模块 | 测试数 | 覆盖要点 |
|------|--------|----------|
| `test_llm_service.py` | 17 | Token 估算 (中/英/混合), LlmConfig 序列化与 Provider 默认值, chunk_transcript 分块与重叠, frozen 不可变性 |
| `test_bridge_service.py` | 8 | health 端点, CORS 头, 404 路由, projects 回调 (有/无), start/stop 生命周期 |
| 已有测试 | 126 | 全部通过, 无回归 |
| 前端测试 | 105 | 全部通过 |

---

## Phase 1 完成状态

| 任务 | 状态 | 耗时 |
|------|------|------|
| Task 1.4: 单一版本源 | 已完成 | -- |
| Task 1.1: LLM 服务架构 | 已完成 | -- |
| Task 1.3: HTTP API 桥接服务 | 已完成 | -- |
| Task 1.2: LLM 设置面板 | 已完成 | -- |

---

## Phase 2: Core Features (已完成)

> 目标: Topic Drift 完整实现 + Bridge Service 文件协议

### 概要

Phase 2 为 Milo-Cut 实现了 AI 驱动的主题漂移分析和文件协议桥接两大核心能力:

1. **Topic Drift 后端** -- 基于 LLM 的转录片段主题相关性分析, 支持 5 分钟分块 + 30 秒重叠、流式逐块返回、overlap 去重、JSON 容错解析、取消与降级
2. **Topic Drift 前端** -- TopicDriftPanel 组件 + useTopicDrift/useLlmAnalysis composables, 按相关度三档颜色编码, 批量接受/拒绝低相关度片段
3. **Bridge 文件协议** -- JSONL 文件发布/消费, 原子写入 (os.replace), 2s 轮询, 自动归档; 项目保存和分析完成时自动发布数据

### 变更文件 (共 15 个)

#### 后端 (9 个文件)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/models.py` | 修改 | 新增 `TopicDriftResult`、`TopicDriftData` 模型; `AnalysisResult.type` 扩展 `"topic_drift"`; `Project` 新增 `topic_drift` 字段 |
| `core/llm_service.py` | 修改 | 新增 `analyze_topic_drift()` 分块流式分析、`_build_topic_drift_prompt()` prompt 构建、`_parse_topic_drift_response()` JSON 容错解析 (markdown/bare JSON/字段缺失/relevance clamp) |
| `core/bridge_service.py` | 修改 | 新增 `GET /api/v1/projects/{name}/topic-drift` 端点 + `get_topic_drift_fn` 回调注入 |
| `core/project_service.py` | 修改 | 新增 `update_topic_drift()` / `get_topic_drift()` 方法, 支持缓存存储和读取; 导入 `TopicDriftData`/`TopicDriftResult` |
| `core/file_protocol.py` | 新增 | `FileProtocolManager`: JSONL publish/poll, `publish_edit_timeline()` / `publish_topic_drift()`, 原子写入 (tempfile + os.replace), 2s 轮询, 自动归档 |
| `core/paths.py` | 修改 | 新增 `get_bridge_dir()` -- bridge 协议目录 (outgoing/incoming/archive) |
| `main.py` | 修改 | 注册 `LLM_TOPIC_DRIFT` handler + `_handle_topic_drift` (流式事件 + 缓存); `@expose` start_topic_drift/get_topic_drift_results/add_analysis_results/get_file_protocol_status; save_project 钩子发布 edit_timeline; topic drift 完成发布结果; 文件协议轮询启动 + atexit 清理 |
| `tests/test_topic_drift.py` | 新增 | 26 个测试: 模型序列化 (6)、解析容错 (9)、prompt 构建 (3)、analyze_topic_drift 完整流程 (8) |
| `tests/test_file_protocol.py` | 新增 | 14 个测试: publish 写入/原子性/中文内容 (7)、poll 解析/归档/多文件 (5)、轮询生命周期 (2) |

#### 前端 (6 个文件)

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/types/project.ts` | 修改 | 新增 `TopicDriftResult`、`TopicDriftData` 接口; `Project` 新增 `topic_drift` 字段; `AnalysisResult.type` 扩展 `"topic_drift"` |
| `frontend/src/composables/useTopicDrift.ts` | 新增 | 单例状态管理: 事件监听 (4 个 llm:* 事件), segment_id upsert 去重, 任务创建/取消, 缓存加载 |
| `frontend/src/composables/useLlmAnalysis.ts` | 新增 | LLM token 用量累计 + 格式化展示 |
| `frontend/src/components/workspace/TopicDriftPanel.vue` | 新增 | 完整面板: 主题输入 + 分析按钮 (LLM 未配置时 disabled)、流式进度条、按 relevance 排序结果列表、三档颜色编码 (绿>=0.7/黄/红<0.4)、批量接受/拒绝、点击跳转 |
| `frontend/src/components/workspace/TopicDriftPanel.test.ts` | 新增 | 10 个测试: 空状态/渲染/排序/颜色编码/disabled/emit seek/批量操作/进度条 |
| `frontend/src/components/workspace/Timeline.vue` | 修改 | 右侧栏新增 tab 切换器 (建议/主题漂移), 集成 TopicDriftPanel |
| `frontend/src/pages/WorkspacePage.vue` | 修改 | 接入 useTopicDrift composable + llmConfigured 检查 + onMounted 加载缓存; 新增 handleAcceptTopicDriftAll/handleRejectTopicDriftAll; Timeline 传递 topic drift props/events |
| `frontend/src/composables/useSegmentEdit.test.ts` | 修改 | 修复 Project mock 新增 topic_drift 字段 |

#### 文档 (1 个文件)

| 文件 | 说明 |
|------|------|
| `docs/2.0.0/audit-plan-v2.0.0-phase2.md` | Phase 2 执行计划文档 |

### 架构决策

#### Topic Drift 分块策略 (B-03 审计修复)

- 沿用 Phase 1 的 `chunk_transcript()`: 5 分钟分块 + 30 秒重叠
- 逐块调用 LLM, 通过 `chunk_callback` 流式返回结果, 前端即时 upsert
- overlap 区域去重: 同一 segment_id 的结果保留最后一次值 (后到的覆盖先到的)
- LLM 返回解析容错: 支持 markdown code block / bare JSON / 字段缺失 / relevance 越界 clamp

#### 文件协议 -- 原子写入与轮询

- 使用 `tempfile.mkstemp()` + `os.replace()` 实现 Windows 兼容的原子写入 (非 `os.rename()`)
- 轮询间隔 2s (非 500ms), 减少 IO 开销
- 处理后文件 `os.replace()` 到 `archive/` 目录
- 与 HTTP API 互补: HTTP 为主动查询, 文件为被动推送

#### 前端 tab 集成

- 在 Timeline 右侧栏新增 tab 切换器, 而非创建独立面板
- "建议" tab 保留现有规则分析 (filler/error/silence) 逻辑不变
- "主题漂移" tab 接入 TopicDriftPanel, LLM 未配置时显示提示
- accept-all 将低相关度结果 (relevance < 0.4) 转为 EditDecision 写入项目

### 测试覆盖

| 模块 | 测试数 | 覆盖要点 |
|------|--------|----------|
| `test_topic_drift.py` | 26 | 模型序列化/frozen, JSON 解析 (markdown/bare/缺失/clamp), prompt 构建, 完整流程 (mock LLM), chunk_callback, 取消, overlap 去重, LLM 失败续行, 进度回调 |
| `test_file_protocol.py` | 14 | publish 写入/原子性/文件名/中文, publish_edit_timeline/publish_topic_drift, poll 解析/归档/多文件/无效行, 轮询 start/stop |
| `TopicDriftPanel.test.ts` | 10 | 空状态/结果渲染/排序/颜色编码/disabled/emit/批量操作/进度条 |
| 后端总测试 | 174 | 全部通过 (排除预存 ASR VadOptions 失败, 与本次无关) |
| 前端总测试 | 115 | 全部通过 |

### Phase 2 完成状态

| 任务 | 状态 | 耗时 |
|------|------|------|
| Task 2.1: Topic Drift 后端 | 已完成 | -- |
| Task 2.2: Topic Drift 前端 | 已完成 | -- |
| Task 2.3: Bridge Service 文件协议 | 已完成 | -- |

Phase 3 (UIUX Polish) 待实施:
- Task 3.1: 全局步骤导航
- Task 3.2: 工作区分栏拖拽
- Task 3.3: 页面过渡动画

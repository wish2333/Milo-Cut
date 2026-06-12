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

Phase 2 (Core Features) 待实施:
- Task 2.1: Topic Drift 后端
- Task 2.2: Topic Drift 前端
- Task 2.3: Bridge Service -- 文件协议

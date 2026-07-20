# Milo-Cut -- 项目经历文档（v2.0.0 - v2.2.1：AI 驱动进化阶段）

## 1. 项目概览

| 项目           | 详情                                                         |
| -------------- | ------------------------------------------------------------ |
| 项目名称       | Milo-Cut                                                     |
| 项目类型       | 桌面应用（AI 视频粗剪预处理器）                              |
| 角色           | 独立开发者（全栈，AI 辅助 VibeCoding）                       |
| 本阶段开发周期 | 2026年6月 至 2026年6月（v2.0.0 - v2.2.1，6个版本密集迭代）   |
| 技术栈         | Python 3.11 / Vue 3 + TypeScript / PyWebView / FFmpeg / Tailwind CSS 4 / DaisyUI 5 / OpenAI SDK |
| 目标用户       | 口播博主、课程录制者、播客剪辑师等视频内容创作者             |
| 仓库           | 本地 Git 仓库（main 分支，当前版本 v2.2.1）                  |

### 1.1 阶段背景

v1.3.0 之前，Milo-Cut 已完成从零到可用的跨越：PyWebView + Vue 3 混合架构验证成功，静音检测、SRT 字幕编辑、多格式导出等"素材清洗"核心功能落地。但产品的分析能力始终停留在规则层——正则匹配中文口头禅、固定触发词检测口误、n-gram 相似度识别重复——无法理解语义。一个典型的困境：用户说"不对重来"后紧跟的整段废片，规则引擎只能靠触发词列表命中，一旦措辞变化就漏检。

v2.0.0 是 Milo-Cut 的智能化分水岭。核心目标是将分析引擎从"规则驱动"升级为"LLM 驱动"，让工具真正理解口播内容的语义，而不仅仅是匹配字符串。与此同时，v2.0.0 还承担了另一个战略任务：将 Milo-Cut 从独立工具升级为可互操作的"生态系统组件"——通过 HTTP API 和文件协议与姊妹项目（FFmpeg 批处理工具）协同，形成" Milo-Cut 负责'剪什么'、Neo 负责'怎么剪'"的分工。

v2.0.1 - v2.2.1 则是在 v2.0.0 的 AI 基础设施上持续深化：提示词预设管理、字幕逐条 diff 审阅、一键清理工作流、规则引擎整体移除（被 LLM Smart Delete 完全覆盖）、LLM chunk 级并发、macOS 桥竞态修复。整个阶段从"接通 LLM"到"让 LLM 真正好用"，经历了 6 个版本的密集迭代。

### 1.2 用户画像

- **口播博主 / 知识博主**：录制 30-90 分钟口播视频，口误多、停顿多、重复表达频繁，希望 AI 自动识别"有声废话"而非只检测静音
- **课程录制者 / 教培团队**：45-120 分钟录屏加讲解，经常讲错重讲、存在长时间停顿，需要从全片中提取"精华片段"用于短视频二次分发
- **播客 / 访谈剪辑师**：60-180 分钟多人对话，需要用自然语言搜索快速定位"上次提到 XX 是在什么时候"，而非逐句聆听
- **实习同事 / 同学**：在教育实习场景中需要快速处理录课视频，但不具备专业剪辑技能，期望"一键清理"工作流而非逐功能操作

---

## 2. 痛点与动机

### 上一阶段遗留的瓶颈（v1.3.0 现状）

v1.3.0 的分析能力完全由规则引擎承担，在实际使用中暴露出四类核心局限：

- **规则引擎无法理解语义**：口头禅检测依赖字符串包含匹配，无法识别上下文相关的填充词；口误检测依赖人工维护的触发词列表 + 固定 lookahead，用户说"啊不对刚才那个"就漏检；重复检测用 n-gram 余弦相似度，语义相同但措辞不同的重复表达（"我觉得这个很重要" / "这一点非常关键"）完全无法命中
- **分析结果缺乏深度**：规则只能产出"删 / 不删"的二元判断，无法告诉用户"这段话偏离了主题"或"这句是核心论点值得保留"，更无法根据用户指定的目标时长自动生成精华剪辑方案
- **工具间协同断裂**：Milo-Cut 与姊妹项目（FFmpeg 批处理工具 Neo）技术栈完全一致（同为 pywebvue + Vue 3），但两个项目各自独立运行，用户需在两个应用之间手动切换，"先在 Milo-Cut 里决定剪什么，再到 Neo 里执行编码导出"的分工无法自动化
- **交互体验粗糙**：页面切换无过渡动画、工作区栏宽固定不可调、设置弹窗空间不足（640px Modal 无法容纳 LLM 配置的提示词编辑器）、缺乏全局步骤引导（用户不知道"导入 -> 分析 -> 编辑 -> 导出"走到了哪一步）

### 本阶段实现的改善

- **分析引擎从规则升级为 LLM 语义理解**：新增四类 AI 分析能力——智能删除（P0，识别口误/重复/口头禅并给出置信度）、字幕纠错（P1，修正 ASR 识别错误并逐条 diff 审阅）、精华提取（P2，按目标时长从全片中筛选高信息密度片段）、语义搜索（P3，自然语言查询定位片段）
- **生态系统互操作落地**：实现 HTTP REST API（`/api/v1/health`、`/projects`、`/timeline`、`/analyze`）和 JSONL 文件协议双通道，外部工具可查询项目状态、触发分析、消费编辑时间线
- **工作流从手动逐功能操作升级为一键编排**：用户可保存"快速清理"工作流（smart delete -> subtitle correction -> highlight 三步串行），一键启动后自动顺序执行、冲突检测、结果直接写入项目
- **交互体验全面打磨**：全局 5 步骤导航控制器、可拖拽分栏（25%-75% + localStorage 持久化）、页面过渡动画（300ms fade+slide，尊重 prefers-reduced-motion）、设置页全屏化（640px Modal -> 100vw 全屏覆盖层）
- **最终移除规则引擎**：v2.1.1 中认定规则引擎的 4 个专属 bug 共享同一架构缺陷（append-only AnalysisResult、EditDecision 单向关联无级联删除、字符串匹配代替语义理解），且其能力已被 LLM Smart Delete 完全覆盖，决定整体移除而非修补

---

## 3. 核心职责

作为独立开发者，在本阶段（v2.0.0 - v2.2.1）负责全部技术决策与实现：

- **产品规划**：编写 v2.0.0 PRD，定义三大支柱（智能进化 / 生态互操作 / 产品交付），按 P0/P1/P2 排列 20 项功能优先级，制定 4 阶段实施计划（Foundation -> Core Features -> UIUX Polish -> Delivery）
- **LLM 服务架构设计**：从零设计统一 LLM 调用层（`core/llm_service.py`），基于 OpenAI SDK 实现，支持 OpenAI/DeepSeek/Qwen/GLM/Ollama 等兼容 API，内置流式输出、Token 估算、分块策略（长窗口 5min+30s overlap / 短窗口 25s+5s overlap）、JSON 四层降级解析、429 自适应退避、chunk 级并发
- **提示词工程体系**：设计参数化提示词系统（`{{param}}` 标记位注入）、分层持久化（全局默认 + 项目覆盖）、风格预设 CRUD、双模式编辑（简单参数 / 高级全量 textarea），并根据真实探针报告反复调优（职责边界划分、标点规则、上下文连贯性）
- **前端架构演进**：实现全局步骤导航状态机、可拖拽 SplitPanel、AI 助手面板（四功能统一入口）、字幕逐条 diff 审阅全屏视图、精华模式视图、语义搜索栏、工作流配置 UI，迁移 DaisyUI 语义类为纯 Tailwind
- **质量保障**：每阶段产出 audit-report / audit-plan 闭环，编写后端单元测试 + 集成测试（`@pytest.mark.integration` 标记分离）+ 前端组件测试，执行真实 LLM 探针验证提示词质量，全量测试达 390+ 后端 / 171 前端
- **工程化治理**：单一版本源（pyproject.toml -> 前端 package.json 自动同步）、main.py region 分区（12 个 `# region` 折叠 90 个 @expose 方法）、桥竞态修复（`__BRIDGE_READY__` 双信号轮询）、SettingsModal 延迟挂载

---

## 4. 产品方案

### 4.1 方案概述

v2.0.0+ 的核心产品决策是：**将 LLM 作为分析引擎的"第二层大脑"，而非替代规则层**。规则层继续承担高置信度、低延迟的确定性检测（静音段、字面重复），LLM 层负责需要语义理解的分析任务（主题判断、口误识别、内容筛选、自然语言导航）。两层结果统一为 EditDecision / AnalysisResult 模型，在同一个建议面板中展示，用户无需感知"这条建议来自规则还是 AI"。

同时，产品从"单工具"向"生态组件"演进：通过 HTTP API 和文件协议暴露项目状态和分析能力，使外部工具能查询"用户剪了什么"、触发"重新分析"、消费"编辑时间线"。这为后续与 FFmpeg 批处理工具的协同奠定了协议基础。

### 4.2 核心功能设计

#### 功能一：四层 AI 分析引擎（P0/P1/P2/P3）

**做什么**：为口播视频提供四种互补的 AI 分析能力，覆盖"减法"（删差的）和"加法"（挑好的）两个方向。

**设计原因**：规则引擎无法理解语义，而口播视频的核心问题——口误后的废段、语义重复、偏离主题、信息密度低——都需要语义判断。四种能力按"删除置信度"和"内容方向"分层，用户可按需选择分析深度。

**关键设计决策**：

- **P0 智能删除（Smart Delete）**：使用 25s 窗口 + 5s overlap 的短窗口分块策略（口误/重复是局部现象，短窗口更精准），LLM 返回 `{segment_id, action, confidence, category}` 结构化结果，4 层降级解析（json.loads -> markdown code block -> regex 提取 -> 逐行 regex）。结果转为 `EditDecision(source="llm_smart")`，与规则结果同列展示。增量分析跳过规则引擎已标记的 segment，避免重复 LLM 调用
- **P1 字幕纠错（Subtitle Correction）**：分两种模式——Mode A 无参考稿（LLM 自行判断 ASR 错误）、Mode B 有参考稿（用户提供正确文本，LLM 据此修正）。关键安全机制：时间戳双层断言（dev 环境 raise ValueError 强保证，prod 环境 raise TimestampCorruptionError 后回滚单个 segment 不影响其他）；分层容错策略（全量匹配正常应用、部分匹配标记 `dirty_flags.llm_uncovered`、全量失配才报错）。v2.1.0 Phase 2 进一步改为"生成 AnalysisResult -> 用户逐条 diff 审阅 -> 接受的才 apply"，不再自动覆盖 segment 文本
- **P2 精华提取（Highlight）**：全文 30 分钟分块（从最初 5 分钟调整为 30 分钟，解决上下文碎片化问题），LLM 识别高信息密度片段（核心论点/关键数据/精彩类比/重要结论），按 density 分级排序，target_duration 裁剪（±20% 容差）。跳变点检测（相邻 highlight 间隔 >2s 视为跳变点）+ crossfade 选项消除音频爆音。v2.2.0 实现精华导出：复用现有 FFmpeg 管道，精华范围 = 全片 - 非精华范围，将非精华标记为 confirmed delete
- **P3 语义搜索（Semantic Search）**：单次 LLM 调用（不分块），自然语言查询返回 top_k 最相关 segment + relevance + match_reason。选择 LLM 而非 embedding 向量检索，避免引入向量数据库依赖；超长 transcript 截断到最近 200 segments

#### 功能二：提示词工程体系

**做什么**：让用户能自定义 5 个 LLM 功能的系统提示词，支持参数化、预设管理、分层持久化。

**设计原因**：不同场景（学术报告 vs 日常 vlog）对"什么算口误""什么算精华"的判断标准不同，硬编码提示词无法适应。同时，用户调试提示词时需要能保存多套参数组合快速切换。

**关键设计决策**：

- **标记位注入**：提示词中使用 `{{custom_fillers}}` 双花括号格式（避免与 JSON 模板冲突），`_inject_placeholders` 运行时替换，空值替换为空字符串（保留行结构而非删除行），`_format_param` 对每个值 strip 处理
- **分层持久化**：全局默认存 `settings.json["llm_prompts"]`，项目级覆盖存 `Timeline.llm_prompts`，`get_effective_prompt` 按优先级读取
- **风格预设 CRUD**：每个功能（P0/P1/P2）独立预设列表，内置一个 id="default" 的稳定默认预设（受保护不可删除），用户可保存/应用/删除自定义预设。预设是"候选配置集合"，必须"应用"后才写入 override 生效
- **双模式编辑**：简单模式（参数化字段 textarea）+ 高级模式（全量 system_override textarea），`system_override` 非空时优先于简单模式参数
- **真实探针驱动调优**：编写 `scripts/llm_full_probe.py` 全功能探针脚本，使用真实项目数据调用 5 个 LLM 功能，生成 markdown 分析报告。据此反复调整提示词：划分 smart_delete 与 subtitle_correction 的职责边界（口误/卡壳/重复归前者，ASR 识别错误归后者）、补充 confidence 字段说明、强调上下文连贯性

#### 功能三：一键清理工作流

**做什么**：将原本需要手动逐个运行的 P0 -> P1 -> P2 三步 AI 分析编排为可保存、可复用、一键启动的自动化工作流。

**设计原因**：用户每次处理新视频都要重复"运行 smart delete -> 等待完成 -> 运行 subtitle correction -> 等待完成 -> 运行 highlight"的操作序列。工作流引擎将这个序列自动化，并处理步骤间的数据依赖和冲突。

**关键设计决策**：

- **v2.1.0 沙箱-确认模式 -> v2.2.0 非沙箱化改造**：v2.1.0 的工作流采用沙箱模式（步骤结果累积，用户点击 Apply 才写入项目），审计发现 `apply_workflow()` 直接赋值 `ProjectService.current`（只读 @property 无 setter）导致 Apply 永远抛 AttributeError。v2.2.0 决定删除沙箱模式，步骤直接走正常写 project 路径（与单功能模式一致），P0 bug 通过删除写入逻辑自然消除
- **payload 冻结 timeline_id**：排队期间用户可能切换 timeline，handler 从 `task.payload` 读取 `timeline_id` 而非实时 `active_timeline_id`，实现并发隔离
- **临时定义自动清理**：用户无已选工作流直接启动时自动创建临时定义，执行结束后通过 `watch(wf.isActive)` 自动删除，避免无效残留
- **步骤建议数恢复**：非沙箱化改造误删 `WORKFLOW_STEP_COMPLETED` 的 `edits_count` 字段，前端显示"条"字无数字，后续从步骤执行结果中提取 `edits` / `corrections` 列表长度恢复

#### 功能四：生态系统互操作

**做什么**：通过 HTTP REST API 和 JSONL 文件协议双通道，使外部工具能查询 Milo-Cut 的项目状态、触发分析、消费编辑时间线。

**设计原因**：Milo-Cut 与姊妹项目（FFmpeg 批处理工具 Neo）技术栈完全一致（同为 pywebvue + Vue 3），但两项目独立运行，用户需手动切换。互操作协议使"Milo-Cut 决定剪什么 -> Neo 执行编码导出"的分工自动化。

**关键设计决策**：

- **HTTP API（主动查询）**：基于 stdlib `http.server` 实现（零新依赖，与现有 media_server.py 一致），端点包括 `/api/v1/health`、`/projects`、`/projects/{name}/timeline`、`/analyze`。回调注入模式避免耦合具体服务（`BridgeService` 通过构造函数接收 `get_projects_fn` 等回调）
- **文件协议（被动推送）**：JSONL 格式发布/消费，`tempfile.mkstemp()` + `os.replace()` 实现 Windows 兼容的原子写入（非 `os.rename()`），2s 轮询间隔（非 500ms 减少 IO），处理后归档到 `archive/` 目录。项目保存和分析完成时自动发布数据

### 4.3 系统架构

v2.0.0+ 在原有架构上新增了 LLM 服务层和互操作桥接层：

### Python Backend (PyWebVue Bridge)

- **main.py (MiloCutApi)**：包含90个@expose方法，划分为12个region分区。
- **TaskManager**：统一异步任务管理，新增CANCELLED状态。
- Core Services：
  - **llm_service**：LLM调用核心，提供call_llm、analyze_smart_delete、analyze_subtitle_correction、analyze_highlights、semantic_search，支持chunk级并发与429退避。
  - **llm_prompts**：5个参数化提示词常量，支持标记位注入和分层读取。
  - **llm_presets**：风格预设CRUD，内置默认保护。
  - **diff_service**：基于difflib的字符级diff，供P1行内渲染使用。
  - **workflow_engine**：一键清理工作流编排引擎。
  - **bridge_service**：HTTP REST API（localhost:18230）。
  - **file_protocol**：JSONL文件协议，支持原子写入和2秒轮询。
  - **timeline_utils**：多Timeline辅助工具，收集partial_delete hints。
  - **export_service**：新增精华导出功能，使用虚拟edits和range减法。
  - **ffmpeg_service**：FFmpeg/ffprobe封装。
  - **export_timeline**：时间线导出，支持EDL/XML/OTIO格式。
  - **subtitle_service**：SRT解析与生成。
  - **media_server**：本地HTTP媒体流服务。
  - **project_service**：项目管理，包括correction持久化和highlight增删。
  - **已移除 analysis_service**：v2.1.1整体删除，被LLM Smart Delete覆盖。
- **Models (Pydantic v2)**：LlmConfig / TopicDriftResult / Timeline（含llm_prompts）。

### Vue 3 Frontend

- **pages/**：WelcomePage / WorkspacePage / ExportPage。
- components/：
  - **common/**：StepController / SplitPanel（v2.0.0新增）。
  - **workspace/**：AIAssistantPanel / HighlightModeView / SemanticSearchBar / SubtitleCorrectionReview / SuggestionPanel / TimelineSwitcher / SearchReplaceBar。
  - **export/**：EncodingSettings / PreviewPlayer。
  - **waveform/**：WaveformCanvas / WaveformEditor / SegmentBlocksLayer。

**LLM 调用链路**：前端 AIAssistantPanel -> `useLlmTasks` composable -> `call("start_smart_delete", ...)` -> TaskManager 创建任务 -> 后台线程执行 `analyze_smart_delete()` -> `chunk_transcript_short` 分块 -> `ThreadPoolExecutor` 并发提交 -> 每块 `call_llm()` -> `_parse_json_response_layers` 四层降级解析 -> 结果合并 -> `add_analysis_results` 写入项目 -> `task:completed` 事件触发前端刷新。

**互操作双通道**：HTTP API 为主动查询（外部工具按需调用 REST 端点），文件协议为被动推送（项目保存 / 分析完成时自动发布 JSONL，外部工具轮询消费）。两者互补：HTTP 低延迟但需在线，文件协议离线可用但延迟较高。

**多 Timeline 架构**（v2.0.0 Phase 4a 引入）：`Project` 不再持有单一 `transcript`，而是 `Project.current.timelines` 字典 + `active_timeline_id`。用户可创建 / 切换 / fork / 重命名 Timeline，每个 Timeline 独立维护 transcript + analysis + edits + llm_prompts。并发任务通过 payload 冻结 timeline_id 实现隔离。

---

## 5. 开发过程

### 5.1 规划与调研阶段

v2.0.0 启动前，系统梳理了 v1.3.0 的能力边界和技术债务：

- **能力差距分析**：逐项评估规则引擎的四类检测（口头禅/口误/重复/标点）在真实口播素材上的漏检率，确认"无法理解语义"是核心瓶颈
- **LLM 选型评估**：评估 OpenAI SDK（内置流式/重试/类型提示，但绑定 OpenAI API）vs 裸 httpx（灵活但需手写重试/流式），最终选择 OpenAI SDK + base_url 可配置（兼容 DeepSeek/Qwen/GLM/Ollama 等所有 OpenAI 兼容 API）
- **互操作协议选型**：对比 HTTP API（低延迟、中复杂度）、文件协议（中延迟、低复杂度）、WebSocket（最低延迟、高复杂度），选择文件协议（主）+ HTTP API（辅）的双通道方案
- **PRD 编写**：产出完整 PRD，定义三大支柱（智能进化 / 生态互操作 / 产品交付）、20 项功能优先级矩阵、4 阶段实施计划、技术风险矩阵

### 5.2 v2.0.0：AI 驱动基础建设（Phase 1 - Phase 4d）

v2.0.0 是本阶段工作量最大的版本，分 7 个子 Phase 实施：

**Phase 1（Foundation）**：建立三大基础能力——单一版本源（pyproject.toml 作为唯一版本号来源，`core/__init__.py` 运行时读取，build.py / app.spec / package.json 自动同步）、LLM 服务层（`core/llm_service.py`，`call_llm()` / `test_connection()` / `estimate_tokens()` / `chunk_transcript()`）、HTTP API 桥接（`core/bridge_service.py`，4 个 REST 端点）、LLM 设置面板（SettingsModal 新增 LLM 选项卡）。

**Phase 2（Core Features）**：实现 Topic Drift 后端（5 分钟分块 + 30 秒重叠 + 流式逐块返回 + overlap 去重 + JSON 容错解析）和前端（TopicDriftPanel + 三档颜色编码）、Bridge 文件协议（JSONL 原子写入 + 2s 轮询 + 自动归档）。

**Phase 3（UIUX Polish）**：全局步骤导航（useStepNav 状态机，5 步骤，仅可跳到已达到的步骤）、工作区分栏拖拽（SplitPanel，pointer 事件，25%-75%，localStorage 持久化）、页面过渡动画（300ms fade+slide，prefers-reduced-motion 降级）。

**Phase 4a（工程化 + 多 Timeline）**：代码质量治理（region 分区、lint 零错误、API 同步检查）+ 多 Timeline 基础设施（Project 重构、TimelineSwitcher 组件、fork/switch API）。

**Phase 4b（C-02 + P0 + P1）**：LLM 输入格式重构（segment dict -> JSON payload，消除解析歧义）、P0 智能删除（短窗口分块 + 增量分析 + TaskType）、P1 字幕修正（模式 A/B + context_window + 置信度 + 时间戳断言 + 分层容错）、Topic Drift 清理（后端 6 文件 + 前端 6 文件，Topic Drift 被 P0/P1 更精准的能力替代）。

**Phase 4c（P2 + P3）**：精华提取（全文分块 + density 排序 + target_duration 裁剪 + 跳变点检测 + crossfade）、语义搜索（LLM 语义匹配 + top_k + relevance 降序）。

**Phase 4d（集成测试 + 发布）**：后端 15 个集成测试（P0-P3 全链路 mock-LLM + 多 Timeline 隔离 + 时间戳断言）、前端 32 个组件测试、main.py region 分区（12 个 region 折叠 90 个 @expose 方法）、构建验证（378 测试通过 + Lint 零错误 + API 同步 + 前端构建成功）。

### 5.3 v2.0.1：UI 打磨

基于 v2.0.0 的 AI 基础设施，聚焦四个 UI/UX 补全问题：

- **Dropdown 透明背景修复**：DaisyUI 5 自定义主题 `appleLight` 声明但未定义颜色变量，导致 `bg-base-100` 渲染为透明。通过 `@plugin "daisyui/theme"` 块为 appleLight 定义 4 个语义颜色（oklch 色彩空间，与现有 @theme 视觉等效）
- **AI 助手面板**：将 P0/P1/P2/P3 四个孤立组件统一接入工作区 UI，右侧面板三 tab 切换器（建议 / AI 助手 / 精华），使用 `v-show` 而非 `v-if` 保持组件状态（expandedGroups / 搜索 query / 参考稿 textarea 不丢失）
- **提示词编辑系统**：5 个 prompt 标记位化（`{{param}}`），分层持久化（全局 + 项目），双模式编辑（简单参数 + 高级全量），重置为默认
- **设置页全屏化**：640px Modal -> 100vw 全屏覆盖层 + Teleport to body + 150ms 过渡动画 + ESC 快捷键

### 5.4 v2.1.0：AI 能力深化

三个核心缺口的填补：

- **提示词风格预设**：每个 LLM 功能支持多套参数组合预设（"学术报告" vs "日常 vlog"），内置 id="default" 稳定默认预设（受保护不可删除）。实施中发现并修复 `config.load_settings` 浅拷贝污染全局默认的潜伏 bug（`{**dict}` 只复制顶层，嵌套可变对象仍引用同一全局单例，改用 `copy.deepcopy`）
- **P1 完整 diff 审阅**：从"自动 apply 全部修正"改为"生成 AnalysisResult -> 用户逐条 diff 审阅 -> 接受的才 apply"。新增 `diff_service.py`（difflib 字符级 diff），前端全屏 diff 视图（置信度分组 0.8 阈值、行内 diff 红删绿增、批量"信任高置信度"）
- **一键清理工作流**：WorkflowEngine 编排多步骤串行执行，冲突检测，预设复用。v2.1.0 采用沙箱-确认模式（步骤结果累积，Apply 后写入）

### 5.5 v2.1.1：质量收敛与规则引擎移除

v2.1.0 发布后手动检查发现多项问题，一次性修复并做出重大架构决策：

- **P0 bug 修复**：Analysis 功能崩溃（多 Timeline 重构后 handler 仍读取 `project.transcript`，新建 `_get_target_timeline` helper 统一）、取消任务状态错误（`_execute_task` 不区分 Cancelled/FAILED，新增 TASK_CANCELLED 事件）
- **LLM 参数可配置 + chunk 级并发**：7 个参数暴露到设置页（窗口/批次/上下文/并发数），smart_delete/correction 使用 `ThreadPoolExecutor` 并发提交，429 自适应退避（5s/10s/20s，连续 3 次降级为串行）
- **字幕交互增强**：多选模式（Ctrl/Shift + 点击范围选）、时间微调（±0.1s / Shift ±1.0s）、合并/分割、搜索替换入口、Timeline 重命名、v-memo 优化
- **移除 Analysis 规则引擎**：审计认定 4 个专属 bug 共享同一架构缺陷（append-only AnalysisResult、EditDecision 单向关联无级联删除、字符串匹配代替语义理解），且规则引擎能力已被 LLM Smart Delete 完全覆盖。删除 `core/analysis_service.py`（332 行）+ handler/注册/import，全链路清理后端 5 文件 + 前端 11 文件 + 测试 9 文件，净删约 500 行
- **isDirty watch 竞态修复**：Vue `watch(isDirty)` 只在值变化时触发，连续操作（A -> B 在 2s 内）第二次 `isDirty = true` 不触发 watch，导致操作 B 的修改在 auto-save 前丢失。改用 Vue 3.5+ `onCleanup` 回调模式重置 timer

### 5.6 v2.2.0：功能完善与工作流重构

- **字幕纠错集成 partial_delete**：将快速清理中 `partial_delete` 类别（句内口误/重复）的分析结果跟随 segment 传递给字幕纠错 LLM，辅助更精准的修正
- **精华提取导出**：复用现有 FFmpeg 管道，通过"虚拟 edits"实现精华导出（精华范围 = 全片 - 非精华范围）。修复三个 bug：文件名覆盖冲突（`_highlight` 后缀）、已删除片段重新混入（range 减法）、`get_highlight_ranges` 未过滤类型（一行 `type == "llm_highlight"` 过滤）
- **工作流非沙箱化改造**：移除 v2.1.0 的沙箱-确认模式（步骤直接写 project），`apply_workflow` / `discard_workflow` 保留为 stub。净减约 99 行 workflow_engine 代码

### 5.7 v2.2.1：macOS 桥竞态修复

修复打包成 `.app` 在 macOS 上首次启动时多个页面空白的竞态问题：

- **根因**：pywebview 已知问题——`js_api` 在 JS 上下文创建时即注入（远早于 `loaded` 事件），前端 `waitForPyWebView()` 仅轮询 `window.pywebview.api` 是否存在即误判就绪，此时发起的 10+ 桥调用被 WebKit 静默丢弃
- **修复**：后端 `on_loaded` 显式设置 `window.__BRIDGE_READY__ = true`，前端 `waitForPyWebView` 改为双信号轮询（api 存在 + READY 标志），SettingsModal 改为 `v-if` 延迟挂载（冷启动不再并发发起调用风暴），`call()` 入口增加桥未就绪等待兜底

---

## 6. 项目成果

### 6.1 量化成果

- **代码规模**：本阶段新增后端模块 12 个（llm_service / llm_prompts / llm_presets / diff_service / workflow_engine / bridge_service / file_protocol / timeline_utils 等），前端组件 / composable 15+ 个。移除规则引擎净删约 500 行。main.py 的 @expose 方法从约 60 个增长到 90 个，用 12 个 region 分区管理
- **测试规模**：后端测试从 v1.3.0 的约 126 个增长到 390+ 单元测试 + 35 集成测试，前端从 105 个增长到 171 个。全量测试达 560+，连续多个版本零回归
- **AI 分析能力**：从 v1.3.0 的 4 类规则检测，增长到 4 类 LLM 语义分析（P0 智能删除 / P1 字幕纠错 / P2 精华提取 / P3 语义搜索），覆盖"减法"和"加法"两个方向
- **LLM 供应商支持**：5 种（DeepSeek / OpenAI / Qwen / GLM / Custom / Ollama），DeepSeek 为默认（性价比高），支持深度思考模式（thinking mode，extra_body 传递）
- **版本迭代密度**：v2.0.0 - v2.2.1 共 6 个版本，v2.0.0 分 7 个子 Phase 实施，总开发周期约 3 周密集迭代
- **提示词体系**：5 个参数化提示词 + 标记位注入 + 分层持久化 + 风格预设 CRUD + 双模式编辑，经多轮真实探针调优
- **互操作通道**：HTTP REST API（4 端点）+ JSONL 文件协议（原子写入 + 轮询 + 归档），双通道互补

### 6.2 定性成果

- **分析引擎成功从规则升级为 LLM 语义理解**：核心瓶颈（规则引擎无法理解语义）被彻底解决，Smart Delete 的 category 分级（semantic_dup / partial_delete / filler）和 confidence 区分度证明了 LLM 对口播内容的语义理解能力
- **规则引擎整体移除验证了 LLM 能力的成熟度**：v2.1.1 敢于删除 analysis_service.py（332 行），是因为审计确认 LLM Smart Delete 在真实素材上的覆盖率已完全超越规则引擎，这是对 AI 能力可靠性的重要验证
- **工作流引擎经历"沙箱 -> 非沙箱"的架构纠偏**：v2.1.0 的沙箱-确认模式因 `ProjectService.current` 只读 property 导致 Apply 永远失败，v2.2.0 通过删除沙箱模式而非给 property 加 setter 来解决，体现了"删除复杂性比增加复杂性更正确"的工程判断
- **macOS 桥竞态修复体现了跨平台桌面开发的深层挑战**：pywebview 的 `js_api` 注入早于 `loaded` 事件是已知上游问题，通过 `__BRIDGE_READY__` 双信号轮询在应用层绕过，而非等待上游修复

### 6.3 个人能力体现

- **LLM 工程化能力**：从零构建 LLM 服务层，处理了流式输出、Token 估算、分块策略、JSON 容错解析、429 退避、chunk 级并发、取消支持、错误隔离等工程化问题，形成了可复用的 LLM 集成模式
- **提示词工程能力**：不仅实现参数化 / 预设 / 分层持久化的技术体系，更通过真实探针报告反复调优提示词（职责边界划分、标点规则、上下文连贯性），将 LLM 输出质量从"可用"提升到"好用"
- **架构决策能力**：在多个关键节点做出正确的"删除 vs 保留"判断——移除 Topic Drift（被 P0/P1 替代）、移除规则引擎（被 Smart Delete 覆盖）、移除沙箱模式（Apply 不可行），每次删除都基于充分的审计分析
- **质量保障能力**：建立了 audit-report / audit-plan / 实施修复 / record 文档的闭环流程，单元测试 + 集成测试分层，真实 LLM 探针验证，连续 6 个版本保持高测试覆盖和零回归
- **跨平台问题诊断能力**：macOS 桥竞态的根因分析涉及 pywebview 上游 issue、WebKit 桥静默丢弃、前端误判就绪等多个环节，体现了在混合架构中追踪跨层问题的能力

---

## 7. 亮点与挑战

### 7.1 技术挑战

- **挑战一：LLM 输出的结构化解析与容错**
  - **问题**：LLM 返回的 JSON 格式不可控——有的模型严格遵循格式，有的包裹在 markdown code block 中，有的返回 bare JSON，有的字段缺失或 relevance 越界。如果解析失败，整段分析结果丢失
  - **解决方案**：设计四层降级解析流水线——Layer 1 `json.loads` 直接解析（最快，遵循格式的模型）；Layer 2 提取 markdown code block 后解析；Layer 3 regex 提取 `[...]` 或 `{...}` 子串后解析；Layer 4 逐行 regex 提取 segment_id + relevance/action（极端降级）。所有 4 层独立可测试，全部返回 None 时调用者 graceful 降级
  - **收获**：与 LLM 交互时，永远不能假设输出格式严格可控。多层降级解析是工程上最务实的容错策略，比"要求模型一定按格式输出"更可靠

- **挑战二：LLM 调用的延迟与并发优化**
  - **问题**：30 分钟视频的 smart_delete 可能产生 20+ 个独立窗口，逐块串行调用 LLM 耗时可达 5-10 分钟，用户体验极差
  - **解决方案**：chunk 级并发——`ThreadPoolExecutor(max_workers=concurrency)` 提交全部 chunk，`as_completed` 收集后按原始顺序合并（`results_by_index[idx]`）。取消时 `executor.shutdown(wait=False, cancel_futures=True)` 立即返回。429 自适应退避：连续 3 次 429 后剩余 chunk 自动降级为串行，避免触发供应商限流
  - **收获**：并发 + 自适应降级是处理外部 API 限流的标准模式。关键细节是"按原始顺序合并"——用户看到的结果列表必须与视频时间轴顺序一致

- **挑战三：字幕修正的时间戳安全保证**
  - **问题**：P1 字幕纠错让 LLM 修改 segment 文本，但如果 LLM 意外篡改了时间戳（start/end），会破坏整个时间轴的完整性，导致波形错位、导出错误
  - **解决方案**：时间戳双层断言——dev 环境（`MILO_ENV=development`）时间戳损坏直接 raise ValueError，开发期强保证；prod 环境 raise TimestampCorruptionError，调用者 catch 后回滚该 segment 文本，不影响其他已修正 segment。分层容错策略：全量匹配正常应用、部分匹配标记 `dirty_flags.llm_uncovered` 保留原样、全量失配才报错、分段回滚（时间戳断言失败的 segment 单独回滚）
  - **收获**：与 LLM 交互涉及修改用户数据时，必须有"不可变契约"保护。时间戳是时间轴的基石，任何修改路径都必须经过断言验证。"创建时充分防御、失败时局部回滚、不影响其他数据"是正确的容错粒度

- **挑战四：浅拷贝污染全局默认的潜伏 bug**
  - **问题**：v2.1.0 编写预设单元测试时，发现测试间状态泄漏——TestApplyPreset 创建的 preset 数据出现在 TestDeletePreset 的结果中，尽管每个测试有独立的 tmp_path。根因是 `config.load_settings` 使用 `{**_DEFAULT_SETTINGS, **data}` 浅拷贝，嵌套的可变对象（`llm_prompt_presets: {}`）仍引用全局 `_DEFAULT_SETTINGS` 中的同一对象
  - **解决方案**：改用 `copy.deepcopy(_DEFAULT_SETTINGS)`。此 bug 潜伏于整个 settings 系统，任何通过 `load_settings()` 获取 settings 并修改嵌套 dict/list 的代码都会污染全局默认。v2.0.0/v2.0.1 未暴露，是因为此前无功能像 `llm_prompt_presets` 这样高频原地修改嵌套结构
  - **收获**：Python 的 `{**dict}` 浅拷贝是隐蔽的陷阱。在涉及全局默认值 + 运行时修改的场景中，必须使用 deepcopy。单元测试的隔离性不仅是 tmp_path 的事，还要警惕被测代码内部的全局状态引用

- **挑战五：pywebview 桥竞态导致 macOS 冷启动空白页**
  - **问题**：打包成 `.app` 在 macOS 上首次启动时，首页 / 设置页 / LLM 页全部空白，无任何错误日志。用户打开任意媒体文件后，所有内容恢复正常。根因是 pywebview 的 `js_api` 在 JS 上下文创建时即注入（远早于 `loaded` 事件），前端 `waitForPyWebView()` 仅轮询 `window.pywebview.api` 是否存在即误判就绪，此时发起的 10+ 桥调用被 WebKit 静默丢弃
  - **解决方案**：后端 `on_loaded` 显式设置 `window.__BRIDGE_READY__ = true`（在启动 tick 循环之前），前端 `waitForPyWebView` 改为双信号轮询（api 存在 + READY 标志，缺一不可）。SettingsModal 改为 `v-if` 延迟挂载，冷启动不再并发发起调用风暴。`call()` 入口增加桥未就绪等待兜底
  - **收获**：桌面混合架构中，前端与后端的"就绪"时机可能不对齐。仅检查 API 对象是否存在不够，必须等待后端显式的"我准备好了"信号。这个 bug 在 Windows 上从未出现（WebKit 实现差异），说明跨平台测试不可省略

### 7.2 设计亮点

- **"减法 + 加法"双向 AI 分析**：P0 智能删除（删差的）和 P2 精华提取（挑好的）构成完整的 AI 辅助剪辑闭环。用户可以先"减法"清理废段，再"加法"提取精华用于二次分发。P1 字幕纠错提升字幕质量，P3 语义搜索提供自然语言导航。四种能力互补而非重叠
- **提示词工程的完整体系**：从"硬编码常量"进化到"参数化标记位 + 分层持久化 + 风格预设 CRUD + 双模式编辑"，并通过真实探针报告驱动调优。这不是简单的"写好 prompt"，而是构建了一套让用户能自行调整和复用 prompt 的产品化系统
- **规则引擎整体移除的架构勇气**：v2.1.1 基于审计分析，认定规则引擎的 4 个专属 bug 共享同一架构缺陷且能力已被 LLM 覆盖，决定整体删除而非修补。这避免了"规则层 + LLM 层双重维护"的复杂性，让代码库更清晰
- **工作流非沙箱化的"删除复杂性"决策**：v2.1.0 的沙箱模式因 `ProjectService.current` 只读 property 导致 Apply 失败，v2.2.0 通过删除沙箱模式（步骤直接写 project）而非给 property 加 setter 来解决。"删除导致 bug 的复杂性"比"增加新机制绕过 bug"更正确

### 7.3 开发流程亮点

- **审计驱动的闭环迭代**：每个版本 / Phase 都遵循"spec / audit-plan -> 实施 -> audit-report -> record 文档"的闭环。审计报告不仅发现问题，还分析根因和架构缺陷（如规则引擎的 append-only 设计），为"删除 vs 保留"的决策提供依据
- **真实 LLM 探针验证提示词质量**：编写探针脚本，使用真实项目数据调用全部 LLM 功能，生成 markdown 分析报告。据此反复调优提示词（职责边界、标点规则、上下文连贯性、chunk 时长），将 LLM 输出从"格式正确"提升到"语义精准"
- **测试分层与持续零回归**：单元测试（关注单个函数 / 类）+ 集成测试（`@pytest.mark.integration` 标记，关注跨模块数据流）+ 前端组件测试 + 真实 LLM 探针，四层验证。连续 6 个版本保持全量测试通过和零回归

---

## 8. 项目复盘

### 做得好的地方

- **LLM 工程化体系成熟**：从 `call_llm()` 基础调用，到分块策略、并发提交、429 退避、四层降级解析、时间戳安全断言，形成了一套可复用的 LLM 集成模式。这套模式不仅适用于视频分析，也可迁移到任何"长文本 + LLM 逐段处理"的场景
- **审计驱动敢于做减法**：在本阶段做了三次重要的"删除"决策——移除 Topic Drift（被 P0/P1 替代）、移除规则引擎（被 Smart Delete 覆盖）、移除沙箱模式（Apply 不可行）。每次删除都基于充分的审计分析，而非主观偏好。结果是代码库更清晰、维护成本更低
- **提示词工程从"能跑"到"好用"**：通过真实探针报告反复调优，解决了职责边界重叠（smart_delete 与 subtitle_correction 都想处理口误）、上下文碎片化（highlight 孤立金句无上下文）、标点残留等质量问题。这证明了"提示词不是写一次就完事，而是需要像代码一样持续调优"
- **跨平台问题诊断到位**：macOS 桥竞态的根因分析跨越了 pywebview 上游、WebKit 桥、前端轮询逻辑三个层面，最终在应用层通过双信号机制绕过。体现了在混合架构中追踪跨层问题的系统化能力

### 可改进的地方

- **沙箱模式的设计缺陷本应在 v2.1.0 测试阶段发现**：`apply_workflow()` 直接赋值 `ProjectService.current`（只读 property 无 setter）的问题，如果有集成测试覆盖 Apply 路径，应该在发布前暴露。v2.1.0 缺少了工作流的端到端集成测试
- **BUG3（get_highlight_ranges 未过滤类型）暴露了测试数据的盲区**：单元测试只构造了 `type="llm_highlight"` 的结果，从未混入 `llm_smart_delete` / `llm_subtitle_correction`。集成层的 bug 必须用混合数据测试才能暴露。后续应在测试策略中明确"混合类型数据"的覆盖要求
- **v2.0.0 的 Topic Drift 最终被移除，存在一定的设计浪费**：Phase 2 花费精力实现的 Topic Drift（后端 + 前端 + 文件协议），在 Phase 4b 中被 P0/P1 更精准的能力替代并清理。虽然这个过程本身是"探索 -> 发现更优方案 -> 清理"的正常迭代，但在 PRD 阶段如果能更清晰地定义 P0/P1 的能力边界，可以减少中间版本的实现浪费
- **macOS 跨平台测试滞后**：桥竞态问题直到 v2.2.1 打包后在 macOS 上才被发现，而此前所有开发都在 Windows 11 上进行。对于使用 pywebview 的桌面应用，macOS / Linux 的早期验证应纳入常规流程

### 关键收获

- **LLM 集成的核心挑战不在"调用"，而在"容错"**：LLM 的输出格式不可控、延迟高、可能限流、可能篡改用户数据。工程上的重点是四层降级解析、并发 + 自适应退避、时间戳安全断言、分层容错——这些都是"当 LLM 不完美时如何保证系统仍然可靠"的防御性设计
- **"删除复杂性"比"增加复杂性"更需要勇气和判断力**：本阶段三次重要的架构改进（移除 Topic Drift / 规则引擎 / 沙箱模式）都是通过"删除"而非"增加"来实现的。每次删除都基于审计分析确认"被替代"或"有设计缺陷"，这比堆叠新功能更能提升代码库的健康度
- **提示词是"活"的工程产物**：需要像代码一样版本管理、参数化、预设化、持续调优。真实探针报告是验证提示词质量的唯一可靠手段——单元测试只能验证格式正确性，无法验证语义质量
- **跨平台桌面应用的"就绪时机"问题**：前端框架的 mount 时机与后端原生桥的就绪时机可能不对齐，仅检查 API 对象是否存在不够，必须等待后端显式信号。这类时序竞态在单一平台上可能永远不暴露，跨平台测试不可省略

---

*文档生成时间：2026年6月*
*覆盖版本：v2.0.0 - v2.2.1*
*基于各版本 record / spec / audit-report / PRD 文档整理*
*视角：独立开发者（全栈，AI 辅助 VibeCoding）*
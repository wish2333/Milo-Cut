# Milo-Cut

> 把 1 小时杂乱粗录，变成 40 分钟干净可剪素材。像改文档一样剪视频。

Milo-Cut 是一款面向口述演示类视频的本地 AI 粗剪预处理器。自动检测静音、识别语气词与口误、用 LLM 智能标记删除建议、批量纠错字幕、提取精华片段，最终让你确认后导出干净素材。全程本地处理，无需上传。

## 功能特性

### AI 辅助（LLM）

- **AI 智能删除** -- LLM 分析字幕稿，标记语气词、重复片段、口误与跑题内容，支持批量删除。结果分为"整段删除"与"句内部分删除"两类，部分删除意见会作为上下文提示透传给字幕纠错 LLM（v2.2.0）。
- **AI 字幕纠错** -- LLM 批量纠错 ASR 识别错误，左右对比 diff 审阅；可一键接受高置信度建议，或逐条复核。
- **AI 精华提取** -- LLM 从长录像中识别关键片段；右键字幕可手动加入或移除精华。精华范围通过"反转 + 删除"管线导出为 MP4 / 音频 / SRT（v2.2.0）。
- **AI 语义搜索** -- 自然语言查询定位特定片段（"找到讲 Q3 营收那段"）。
- **提示词预设与编辑** -- 自定义 LLM 系统提示词，支持风格预设与模板变量注入。

### 检测与编辑

- **静音检测** -- 基于 FFmpeg，可配置阈值与时长；尊重既有用户 / LLM 决定，绝不覆盖已有分析结果（v2.3.0 修复了清空 AnalysisData 的严重回归）。
- **语气词检测** -- 自定义词表，正则匹配高频中文语气词。
- **口误触发词检测** -- 识别"不对重来""说错了""重新说"等口误触发词。
- **多时间轴编辑** -- 从当前状态 fork 出独立 timeline，每个 timeline 拥有自己的字幕、决定与分析。在多种剪辑方案间切换不丢失先前工作。
- **工作流引擎** -- 可配置管线编排静音检测、智能删除、字幕纠错三步。
- **字幕交互** -- 多选模式、时间微调（±0.1s）、合并 / 拆分段、全局搜索替换。
- **列表副轨编辑** -- 字幕列表轨感知（v3.0.3）：列表头部分段切换主轨/副轨（会话视图态，不入数据层）；副轨行支持文本/时间编辑、定位、右键删除此条字幕（无确认框，撤销兜底）；编辑与波形修剪共用同一防抖乐观内核，失败回滚并 toast 错误原文。
- **波形可视化** -- Canvas 波形显示，叠加片段标记与播放头跟踪。
- **视频预览** -- 内置播放器，支持字幕叠加、edited 跳剪播放、为大文件生成代理。

### 导出

- **MP4** -- 流复制（`-c copy`）或精确重编码，支持硬件编码器（NVENC / VideoToolbox / QSV / AMF）与编码器预设注册表（v2.3.0）。
- **音频 / SRT / VTT** -- 独立音频 m4a、字幕 SRT、WebVTT。
- **时间轴格式** -- OTIO / EDL / FCPXML / Premiere XML。audio-only 项目（fps=0）现在能正确导出时间轴文件（v2.3.1 P0 修复）。
- **精华导出** -- 仅导出精华范围为 MP4 / 音频 / SRT / VTT（v2.2.0）。

### 平台与本地优先

- **本地优先** -- 所有处理在本地完成，数据不离开设备。LLM 调用由桌面应用直连你配置的 provider。
- **macOS 冷启动修复** -- `__BRIDGE_READY__` 信号消除 pywebview 已知竞态，避免首次启动空白页面（v2.2.1）。
- **ProjectPatch 协议** -- 按层局部更新（segments / edits / analysis）替代旧版全量 Project 转储，wire payload 减少约 70%，长项目写操作 p95 延迟最高降低 81%（v2.3.2）。

> **已知限制**: 工作流模式有待充分验证。详见 [docs/2.1.1/release-2.1.1.md](docs/2.1.1/release-2.1.1.md)。

## 快速开始

### 环境要求

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) 包管理器
- [Bun](https://bun.sh/)（前端构建）
- FFmpeg 和 FFprobe（需在 PATH 中或在设置中配置路径）

### 开发模式

```bash
# 一键启动（自动安装依赖，启动 Vite 开发服务器 + PyWebView 桌面窗口）
uv run dev.py

# 使用预构建的 frontend_dist/
uv run dev.py --no-vite

# 仅安装依赖
uv run dev.py --setup
```

### 构建打包

```bash
uv run build.py              # 构建桌面应用（onedir 模式）
uv run build.py --onefile    # 构建单文件可执行程序
uv run build.py --clean      # 先清理构建产物再打包
```

### 运行测试

```bash
# 后端测试（pytest，478 条）
uv run pytest tests/ -v

# 前端测试（vitest，241 条）
cd frontend && bun run test

# 类型检查 + 生产构建（vue-tsc + vite build）
cd frontend && bun run build
```

### 性能基线（v2.3.2）

```bash
# 生成确定性合成项目（1167 segments / 989 edits / 490 KB）
uv run python -m tests.fixtures.generate_synthetic_project \
    --output /tmp/synthetic.json --segments 1167 --edits 989

# 跑后端 benchmark（model_dump、写操作、payload 体积）
uv run python -m tests.perf.backend_benchmark \
    --runs 30 --output tests/perf/results/baseline.json
```

基线数据与解读见 [`tests/perf/README.md`](tests/perf/README.md)。

## 架构概览

```
milo-cut/
  main.py              # 入口 + @expose API 桥接（约 80 个方法）
  core/                # Python 后端服务
    project_service.py # 项目 CRUD、segment/edit/analysis 操作、_revision 计数器
    project_patch.py   # v2.3.2 ProjectPatch schema + apply_project_patch
    export_service.py  # FFmpeg 分段拼接导出 + 精华虚拟 edits
    export_timeline.py # OTIO/EDL/FCPXML/Premiere XML 时间轴导出
    ffmpeg_service.py  # ffprobe/ffmpeg 封装：探测、静音检测、波形、代理
    ffmpeg_presets.py  # 编码器注册表（CRF/CQ/QP、像素格式、硬件加速）
    llm_service.py     # LLM provider 抽象（OpenAI/Ollama/custom）
    llm_prompts.py     # 系统提示词，支持模板变量注入
    llm_presets.py     # 提示词风格预设
    workflow_engine.py # 多步工作流编排（静音 + 智能删除 + 纠错）
    analysis_service.py# 规则式语气词 + 口误触发词检测
    subtitle_service.py# SRT 解析（UTF-8、GB18030、BOM）
    timeline_utils.py  # 时间轴工具，partial_delete 提示收集
    diff_service.py    # 字幕纠错 diff 生成
    task_manager.py    # 后台任务执行，支持进度与取消
    bridge_service.py  # HTTP bridge API（health、analyze）
    media_server.py    # 本地 HTTP 服务器，为 <video> 提供媒体流
    asr_service.py     # ASR 插件抽象（faster-whisper、qwen3-asr）
    plugin_manager.py  # ASR 插件安装 / 模型下载生命周期
    proxy_manager.py   # 大源文件的代理视频生成
    config.py          # 设置存储（data/settings.json）
    paths.py           # 跨平台路径解析
    events.py          # 事件名常量（与 frontend/src/utils/events.ts 镜像）
    models.py          # Pydantic v2 frozen 模型（Project、Segment、EditDecision 等）
    logging.py         # Loguru 配置
  pywebvue/            # 自定义 pywebview 桥接框架
    bridge.py          # Bridge 基类 + @expose 装饰器
    app.py             # PyWebView 窗口 + __BRIDGE_READY__ 信号
  frontend/            # Vue 3 + TypeScript 单页应用
    src/
      bridge.ts        # Python <-> JS 通信（waitForPyWebView、call、onEvent）
      types/project.ts # Project / ProjectPatch / ProjectResponse 类型
      utils/projectPatch.ts     # applyProjectPatch 合并 helper
      utils/segmentHelpers.ts   # buildSegmentStateMap、resolveSegmentState
      utils/editedPlayback.ts   # 跳剪播放、删除区间解析
      pages/           # WelcomePage、WorkspacePage、ExportPage
      components/      # waveform/、workspace/、export/、common/
      composables/     # useProject、useEdit、useSegmentEdit、useUndoRedo、
                       # useExport、useAnalysis、useEditedPlayback、useLlmTasks 等
  tests/
    fixtures/          # 合成项目生成器（确定性）
    perf/              # 后端 benchmark 工具 + results/
    test_*.py          # 478 条 pytest 测试
```

**通信机制**：Python 通过 `@expose` 装饰器暴露方法，前端通过 `bridge.call()` 调用。Python 通过 `_emit()` 向前端推送事件，前端通过 `onEvent()` 监听。由于 PyWebView 仅允许主线程 `evaluate_js`，桥接层使用 50ms tick 循环串行化跨线程任务。

**ProjectPatch 协议（v2.3.2）**：已迁移的写方法返回 `ProjectPatch` 信封（`{revision, segments?, edits?, analysis?, media?, full_project?}`）替代全量 Project 转储。前端通过 `applyProjectPatch` 应用 patch、用 `lastSeenRevision` 拒绝乱序响应，对未迁移方法自动回退到 legacy 全量路径。未修改层的对象引用保持稳定，消除了 v2.3.1 报告的 GUI 卡顿 Vue 级联。

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面壳 | pywebview |
| 后端 | Python 3.11、Pydantic v2、Loguru |
| 前端 | Vue 3、TypeScript、Vite 6 |
| UI 框架 | TailwindCSS v4、DaisyUI v5 |
| AI / LLM | OpenAI 兼容 API（DeepSeek、OpenAI、Qwen、GLM、Ollama、自定义） |
| ASR | faster-whisper、qwen3-asr（可选插件） |
| 媒体处理 | FFmpeg / FFprobe |
| 打包工具 | PyInstaller |

## 目标用户

| 用户类型 | 典型素材 | 核心痛点 |
|---------|---------|---------|
| 口播博主 / 知识博主 | 30-90 分钟口播视频 | 口误多、停顿多、重复表达 |
| 课程录制者 / 教培团队 | 45-120 分钟录屏 + 讲解 | 讲错重讲、长时间停顿 |
| 播客 / 访谈剪辑师 | 60-180 分钟多人对话 | 找重点片段耗时、去废话 |
| 企业培训视频编辑 | 30-60 分钟内训录像 | 隐私敏感需本地处理 |
| 直播切片运营 | 2-6 小时直播录像 | 找高能片段、批量去冗余 |

## 版本历史（自 v2.1.1 起）

| 版本 | 类型 | 要点 |
|------|------|------|
| **v2.3.2** | 性能优化 | ProjectPatch 按层更新协议（迁移 5 个写方法）；后端 start 升序 invariant；`mergedSegments` 简化；SubtitleOverlay seeked 修复。写操作 p50 -38..-45%，p95 最高 -81%。 |
| **v2.3.1** | 紧急修复 + 审计 | audio-only 项目 OTIO/EDL/XML 导出空文件（P0）；`get_edit_summary` 把 PENDING 当 CONFIRMED 算；`subtitle_trim` edits 创建为 PENDING；edited 跳剪播放性能审计。 |
| **v2.3.0** | 紧急修复 | 静音检测不再清空 `AnalysisData`（P0）；尊重既有 user / LLM 决定；LLM 重跑尊重用户 edits；overlapping silence edits 迁移。 |
| **v2.2.1** | Bug 修复 | macOS 首次启动空白页 -- `__BRIDGE_READY__` 信号修复 pywebview 竞态（#431）；SettingsModal 延迟挂载；`call()` 兜底就绪检查。 |
| **v2.2.0** | 新功能 | 字幕纠错集成 `partial_delete` 提示；精华导出管线（MP4 / 音频 / SRT / VTT）通过虚拟 edits 实现；LLM 未配置时 UX 引导。 |
| **v2.1.1** | 新功能 + 修复 | 多选模式、时间微调、提示词预设、编码器注册表。（本次 README 更新的基线。） |

完整 release notes 在 `docs/<version>/`（如 [`docs/2.3.0/2.3.2-record.md`](docs/2.3.0/2.3.2-record.md)）。

## 文档

- [`docs/design-spec.md`](docs/design-spec.md) -- Apple Edition 设计语言
- [`docs/backend-guide.md`](docs/backend-guide.md) / [`docs/frontend-guide.md`](docs/frontend-guide.md) -- 开发者指南
- [`docs/<version>/`](docs/) -- 每版本实施记录（v0.1.0 到 v2.3.2）
- [`tests/TEST_GUIDE.md`](tests/TEST_GUIDE.md) -- 自动化 + 手动测试流程
- [`tests/perf/README.md`](tests/perf/README.md) -- 性能基线工具说明
- [`AGENTS.md`](AGENTS.md) -- Agent 指南（Codex / Claude Code / OpenCode）

## 开源协议

[GPL-3.0](LICENSE)

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
- **波形可视化** -- Canvas 波形显示，叠加片段标记与播放头跟踪。
- **视频预览** -- 内置播放器，支持字幕叠加、edited 跳剪播放、为大文件生成代理。

### 导出

- **MP4** -- 流复制（`-c copy`）或精确重编码，支持硬件编码器（NVENC / VideoToolbox / QSV / AMF）与编码器预设注册表（v2.3.0）。
- **音频 / SRT / VTT** -- 独立音频 m4a、字幕 SRT、WebVTT。
- **时间轴格式** -- OTIO / EDL / FCPXML / Premiere XML。audio-only 项目（fps=0）现在能正确导出时间轴文件（v2.3.1 P0 修复）。
- **精华导出** -- 仅导出精华范围为 MP4 / 音频 / SRT / VTT（v2.2.0）。

### 数据保真与可靠性（v3.0.0）

- **词级时间戳全程保留** -- 转录结果不再经 SRT 中转；拆分/合并保留词级数据，LLM 纠错后重新对齐词级时间戳（局部编辑保留原时间戳，不可靠的对齐会被清除而不是错位放置）。
- **崩溃安全的项目文件** -- 原子保存（fsync）+ `.bak.1/.bak.2` 轮换备份；损坏的工程自动恢复并 toast 提示，随后在磁盘上自愈。
- **LLM 可靠性协议** -- 批级 ledger 带重试与覆盖缺口上报（绝不静默丢批）、响应清洗、base URL SSRF 防护、不透明段 id、按通路独立控温。
- **波形峰值缓存** -- `<media>.peaks.json` 边车文件带 `{size, mtime_ms}` 签名；重新打开同一媒体约 1 ms 就绪，不再重跑 ffmpeg。

### 性能与规模（v3.0.0）

- **分层撤销** -- 经后端 `apply_undo` 通道按层快照；1167 段工程上的撤销主线程耗时约 1.2 ms，revision 严格单调递增。
- **虚拟化字幕列表 + 就地 patch 合并** -- 1200 段工程滚动保持 60 fps；未变更行保持对象恒等，Vue 跳过对它们的重渲染。
- **桥接事件批量 + 自适应 tick** -- 每批一次 `evaluate_js`（512 KB 预算），空闲 tick 降至 250 ms；波形生成不再阻塞 UI 线程。
- **波形渲染管线** -- rAF 合帧绘制、DPR 感知画布尺寸、指令式播放头（播放期间零 Vue patch）、悬停 seek 预览。

### 多行时间线（v3.0.2）

- **多行时间线** -- 把波形翻转为虚拟化行列表（"一行 = 一窗"，每行时长预设 5/10/20/30 秒）一次纵览几分钟素材；末行收缩为剩余时长，迷你总览条显示覆盖范围与播放头刻度（点击/拖拽跳转，行对齐）。
- **行手势** -- 普通滚轮原生滚动；Ctrl/Cmd+滚轮切换每行秒数，Ctrl/Cmd+Shift+滚轮切换行高（160 ms 突发合并后，播放中的行重新锚定到新几何）。
- **行内编辑** -- 点击空白 seek、拖动 scrub（32 ms 节流）、双击切换播放；Ctrl+拖动建段（预览停在块边缘，窄缝隙拒绝）；Shift+拖动跨行框选并入全局选择；修剪自由跨行边界（行边缘不钳制——以邻居边界 + 吸附 + 吸附后回钳为准；Alt 仅反转吸附）。
- **跟随与持久化** -- 播放跟随只在换行时判定（舒适区 = 仅播放头），手动滚动暂停跟随 3 秒，列表导航走同一 reveal 通路；模式、预设、滚动位置与面板高度持久化到 localStorage，重开恢复。
- **行内轨道** -- 副轨 lane 组合进每一行（折叠/预设状态跨行同步）；有轨道在场时默认行高提升到 168 px（除非你已自选过）。

### 列表轨感知字幕列表（v3.0.3）

- **列表轨选择器** -- 字幕列表头部分段切换主轨/各副轨；选择是会话视图态（不进 patch、不持久化，重载恒回主轨）。
- **列表内副轨编辑** -- 副轨行显示文本/时间戳/时长与绑定标记；双击或行菜单编辑文本，时间戳可点击编辑并 ±0.1s 微调；编辑与波形修剪共用同一防抖乐观内核，失败回滚并 toast 后端错误原文。
- **行操作与撤销谓词表** -- 点击 seek，播放头高亮当前行，右键菜单提供 定位 / 编辑 / 删除此条字幕（无确认框——undo 兜底）；捕获层走谓词表（文本 → 仅 tracks；时间 → 有绑定时 tracks + bindings；删除 → 恒两者），undo 时偏移量原子恢复。
- **跟随平滑（可选开启）** -- 导航跳转可带 140 ms ease-out 动画（`milocut:timeline-follow-smooth:v1`，默认关）；播放时钟路径恒瞬时写入，连续播放行为不变。
- **菜单快捷键角标** -- 行右键菜单标注已注册快捷键（等宽角标，R9.4 风格）；未注册快捷键的项仅显示文本。

### AI 翻译、轨道纠错与手动范围（v3.0.4）

- **AI 翻译生成翻译副轨** -- AI 面板一键把主轨字幕翻译成绑定副轨：选择目标语言（内置 9 种，记忆上次选择）后 LLM 分批翻译，译文段按主轨段 1:1 绑定（时间戳复制对齐）；完成后自动切到译文轨，双语播放（主字幕下方显示绑定译文行）与双语两行 SRT/VTT 导出开箱即用；undo 一次回退整轨（含全部绑定关系）。任一批次失败则整任务零落盘；翻译期间被删除的主轨段经对账进入 uncovered 清单，面板明示不静默。
- **翻译轨级联删除语义** -- 主轨删除段时，其绑定的译文段随之删除（1:1 绑定语义）；用户误删可 undo 恢复。
- **AI 纠错感知当前轨** -- 字幕纠错不再限于主轨：副轨视图下纠错卡可用并锁定当前轨（显式轨徽），待审建议按轨隔离互不清除，审阅条目标注来源轨；接受/拒绝返回 ProjectPatch 局部更新（不再触发整工程全量刷新），undo 一次同时回退文本与审阅条目；主轨已删除段的绑定译文段自动跳过，无绑定译文段照常纠错。
- **手动剪辑范围** -- 波形工具栏"范围标记"toggle（默认关闭）开启后在主轨空白区框选区间，松手确认气泡二选一（删除/保留）；建议面板新增"手动范围"分组与"+ 时间码"精确输入入口（确认即参与裁剪计算）；"保留"（keep）区间被自动裁剪计算排除——被 keep 的内容不会被自动裁剪吃掉（2.x"撑住间隙"语义回归），与手动删除区间并存时导出服从手动删除；待定（pending）范围不影响跳播、进度条红罩与导出预览。
- **顺带批** -- 列表"编辑"扫掠覆盖副轨行（一键进出整列文本编辑，切轨前未决编辑先落盘）；建段模式下点击副轨 lane 空白恢复建段（历史断链接通，multi/basic 两路径均可用）；语义搜索在副轨视图下结果文本与时间正确显示、点击定位主轨命中段。

### 多轨字幕与堆叠时间线（v3.0.0 数据层 / v3.0.1 完整交互）

- **堆叠时间线** -- 主轨与全部副轨 lane 堆叠在同一缩放/滚动面上，单一播放头横跨所有 lane；lane 可折叠/调高/隐藏（高度全局持久化）。
- **副轨** -- 导入 SRT 作为第二轨并自动以 300 ms 容差绑定；副轨段可修剪/拖动并受邻居间隙约束；联动拆分/配对删除保持绑定诚实（破坏性解绑始终计数进 toast，且原子可撤销）。
- **永不漂移的绑定** -- 每次编辑后绑定偏移按最终几何整体重建；主轨永不被对账逻辑回写。
- **轨道导出** -- 每轨 SRT/VTT 走与主轨相同的确认删除映射，另有双语合并（两行）导出；播放时主字幕下方显示绑定的副轨行（设置中可开关）。
- **工作流失败回滚**（v3.0.0）-- 分步层快照跨会话持久化；可只回滚失败步骤，或回滚整个工作流。

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

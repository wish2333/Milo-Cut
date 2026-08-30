# Milo-Cut 竞品分析与优化报告：对标 moys-asr-workflow（MAW/MAWE）

> 分析方式：完整克隆 MAW 仓库（v1.5.0，约 2MB 核心源码），逐文件阅读其后端管线（ASR providers、托管 runtime、脚本对齐、LLM 后处理、工程格式、波形）、前端编辑器（editor.js / waveform.js / gap-remove-core.js 等约 1.5 万行核心逻辑）以及全部产品文档（README / DESIGN / DEVELOPMENT / WORKFLOW / CHANGELOG / JSON_SCHEMA）。
> 对照基准：Milo-Cut v2.3.2。

---

## 一、竞品定位与产品形态

MAW（Moy's ASR Workflow）是一条**刻意收窄的 ASR → 字幕 → 编辑 → 交接导出**工作流：

```
本地媒体 → 云端 ASR（Qwen/Fun-ASR/Soniox/腾讯云/必剪）或本地引擎
        → SRT + .mosp 工程（JSON，整数毫秒）
        → MAWE 编辑器（浏览器 Server 版 / 单文件 HTML / Tauri 桌面版）
        → 导出（SRT/OTIO/OTIOZ/FCP7 XML/FFconcat/Resolve JSON/Lottie...）
```

与 Milo-Cut 的定位对比：

| 维度 | Milo-Cut | MAW/MAWE |
|---|---|---|
| 核心命题 | 口播视频**粗剪预处理**，直接产出可用的干净视频素材 | **字幕工程**全流程，产出字幕文件与"交给专业 NLE 的交接工程" |
| 删除决策 | 静音 + 语气词/口误规则 + LLM 智能删除建议 | 静音空隙（可逆压缩时间线）+ 口播对齐（文稿驱动选段）+ OCR 去重 |
| 成片能力 | **强**：FFmpeg 剪切导出 MP4/音频、硬件编码、代理、精华反转导出 | **无**：不直接渲染视频，FFconcat 重组仅做流复制拼回媒体 |
| ASR 供给 | 插件化（faster-whisper / qwen3-asr），需用户自装 | **9 个引擎**（4 云 5 本地）+ 托管 runtime 一键安装 + 国内镜像测速 |
| LLM 能力 | 删除建议、字幕纠错、精华提取、语义搜索 | 校对、重分段、翻译、自定义任务（时间轴安全回写协议） |
| 技术栈 | Python + PyWebView + Vue3 | Python CLI + vanilla JS 编辑器 + Tauri 桌面壳 |
| 分发 | PyInstaller onedir/onefile | Release zip（含/不含 FFmpeg 两档）+ AppImage + 官网在线编辑器 |

**重叠区（正面竞争）**：静音删除、波形编辑、LLM 字幕纠错、OTIO/FCPXML 导出、本地优先桌面应用。
**Milo-Cut 独有优势**：端到端出片（用户拿到的是能直接发布的视频）、多时间轴 fork、ProjectPatch 增量协议、LLM 删除建议闭环。
**MAW 独有优势**：ASR 供给侧广度、字词级时间码深度、专业 NLE 交接生态、工程契约严谨度、键盘效率体系。

---

## 二、MAW 值得警惕/学习的核心设计（源码级）

1. **Provider 中立中间表示**：9 个 ASR 引擎全部先归一到同一 `items/segments`（词/字级整数毫秒）结构，断句、纠错、导出、编辑全链路只依赖这一个契约。Milo-Cut 的 `asr_service.py` 插件抽象方向一致，但**未规定词级 items 必须落库**——这是下游一切精细能力的分水岭。
2. **托管运行时（runtimes/）**：`RuntimeSpec` 声明式规格 + `ManagedRuntime` 生命周期基类，Torch 级重依赖装进独立环境（embedded Python / venv / uv 三形态统一），GPU/CPU 双 frozen 清单自动兜底 + PyPI 镜像测速。对比：Milo-Cut 的 `plugin_manager.py` 只覆盖模型下载，依赖安装是用户手工环节。
3. **gap provenance 溯源 schema**：静音空隙删除的每一段都记录来源（`audio_gate` / `script_alignment` / `manual`），重扫时保留手工结果、可整体应用/清除/收缩。Milo-Cut 的 EditDecision 有 status 但**没有来源分层**，重新检测会与用户手工决策打架（v2.3.0 刚修过一次清空 AnalysisData 的回归，根因即在此）。
4. **LLM 时间轴安全回写协议**：LLM 只拿到 source_id + 文本，只能返回 ID 分组与新文字；本地校验 ID 完整/连续/有序后，在原时间槽内重对账词级 items，翻译漏条自动单条修复重试。Milo-Cut 的 llm_service 目前由 LLM 直接影响编辑决策，缺少这层"LLM 永远碰不到时间轴"的协议化隔离。
5. **脚本对齐（script_alignment.py，126KB）**：行级候选滑窗 → 全局 top-K 路径 DP → 词级 item 切片修剪，三级由粗到细，能识别"照稿重讲/中途重录/漏录/多余 take"，与 gap 子系统联动输出"应删/应留"结论。这是 MAW 区别于所有字幕工具的杀手锏，且与 Milo-Cut "口播视频"的场景高度重叠。
6. **波形双轨缓存**：自研 minmax i8 base64 缓存（带 `media_signature` 失效判定）+ 逆向解析 REAPER `.ReaPeaks`（可复用专业软件已生成的波形/频谱，Rust 内核生成）。Milo-Cut 每次由 ffmpeg_service 现算波形，无缓存层。
7. **编辑器键盘体系**：JKL 五档倍速播放（含倒放）、WASD 字幕导航/微调、`←/→` 整体移动 + `Ctrl` 起点 + `Ctrl+Shift` 终点 + `Shift` 贴齐相邻边界（幅度可配，默认 50ms，`Alt` 临时反转联动）、`Z/X` 把边界吸附到指针/播放头、`G/Shift+G/H/B` 多轨字幕操作、hover seek 画面预览（rAF 节流不真正 seek）。Milo-Cut 只有 ±0.1s 微调与多选，键盘密度差一个量级。
8. **工程契约版本化**：`.mosp` 有完整 JSON_SCHEMA.md、schema 版本字符串（`moy.asr.*.v1`）、`validate/normalize/repair` 三层、覆盖保存自动 `.bak` 备份、legacy 迁移路径。Milo-Cut 的 project.json 无 schema 文档、无备份策略。
9. **多 kind 统一撤销栈 + 稳定 ID**：segments / 布局树 / gap / 预览四类记录共享 100 步单栈（双端镜像），恢复时用 segment 稳定 id 还原选区，避免下标漂移。Milo-Cut 的全 Project 快照撤销更重，且大项目内存开销高。
10. **前端本地静音检测**：MAW 直接在前端消费波形 min/max 峰值跑"门限 + 迟滞 + 前后余量"五参数算法，即时扫描即时预览、无需后端往返。Milo-Cut 的静音检测走 FFmpeg 子进程 + TaskManager，交互回路慢一拍。
11. **三宿主同码前端**：同一份 web/ 前端跑在单文件 HTML / 127.0.0.1 本地服务器 / Tauri 三种宿主，文件访问全部隔离在 payload 回调注入点之后——与 PyWebView 场景高度同构，值得 pywebvue 层参考。

---

## 三、优化建议（按优先级）

### P0 —— 补齐护城河（直接决定竞争胜负）

1. **词级时间戳（items）作为一等公民落库**
   `Segment` 增加 `items: list[WordItem]`（词/字 + 毫秒区间），ASR 插件输出与 SRT 导入都尽量填充。它是精确拆分（在词边界切开而非时间中点）、字幕-音频对齐、LLM 改字后重对账、口播对齐的共同前置。没有它，后面 3 条都做不了。

2. **EditDecision 增加 provenance（来源分层）**
   决策来源枚举：`silence_detection` / `filler_rule` / `llm_suggestion` / `manual`。重扫只更新非 manual 项，manual 永久保留；配合批量"按来源清除"。可进一步借鉴 MAW 的 append-only override + 可重算投影模型（真实状态存操作记录，`gaps[]` 只是投影），这能根治"重新检测覆盖人工决策"这一类回归，也是用户信任的基础。

3. **波形缓存层 + 前端本地静音扫描**
   按 `media_signature`（大小+mtime）缓存 min/max peaks（100 peaks/s，3 小时约 2MB），存 sidecar 或项目内；命中即秒开长视频。在此之上可把静音检测迁移为前端算法（直接消费波形峰值 + 迟滞门限），实现"调参数 → 即时预览"的交互闭环，FFmpeg 方案保留为兜底。实现成本低、体感提升最大。

### P1 —— 正面吸收竞品强项

4. **一键 ASR 体验**：借鉴托管 runtime 思路，把 faster-whisper 依赖装进独立 venv（`pip install --target` + frozen 清单 + CPU/GPU 探测 + 国内镜像测速），主包保持零 Torch；模型下载加心跳式诚实进度（"约 40%–70%"）。这是 MAW 对小白用户最大的友好点，Milo-Cut 目前是明显短板。
5. **文稿对齐/口播对齐（可后置但必须列入路线图）**：先做简化版——用户粘贴讲稿，用 difflib 对齐字幕文本定位"念错的/漏念的/多念的"段落并给出删除建议。不需要 MAW 的三级 DP 也能覆盖 80% 场景，且与 LLM 智能删除天然互补（规则对齐给证据，LLM 给语义判断）。
6. **LLM 回写协议化**：把字幕纠错升级为"source_id + 纯文本响应 + 本地重对账"协议；词级 items 存在时，改字后按字符 span 把时间戳精确回贴；同时加响应消毒（剥离思考文本）与 base_url SSRF 校验。
7. **导出为"干净素材"加一条 NLE 交接轨**：Milo-Cut 已有 OTIO/FCPXML 导出，补上"带删除决定的 marker 颜色映射（Resolve 五色）"与 FFconcat 快速重组（流复制拼回去空隙媒体，零转码），并让所有导出提供"原始时间线 / 去空隙时间线"双轨选项——让"不要成片、只要素材交接"的用户也能被覆盖。

8. **撤销栈升级（中期）**：从全 Project 快照迁移到按 kind 的分层快照（segments / edits / analysis），配合稳定 segment id 还原选区；跨轨/成对操作可原子撤销，长项目内存占用显著下降。

### P2 —— 体验与工程债

8. **键盘效率体系**：JKL 播放、WASD 段导航、方向键分级步长（默认 ±100ms，Shift ×10，Alt ±10ms）、`Enter` 确认/`X` 切换删除决定。参照 MAW 帮助面板按"基础/快捷/波形区"分组的做法做快捷键速查。
9. **工程保存加固**：覆盖保存前自动 `project.json.bak`；为数据模型写一份 `PROJECT_SCHEMA.md` 并在 `validate/normalize` 中加稳定 ID 与时间合法性修复（MAW 的 `repair_*_timing_ranges` 值得抄）。
10. **布局工作区（可选）**：MAW 的 workspace 二叉树（四模块可拖拽重组 + 预设 + 跨工程复用）成本较高；Milo-Cut 可先做"波形高度/列表宽度比例持久化"这一最小子集。
11. **子进程全链路可取消**：模型下载、转写、导出统一 Event + 进程树终止 + JSON 错误行协议（Milo-Cut TaskManager 已有取消，需覆盖到 ASR 插件子进程）。

### 不建议跟进的方向

- **多 ASR 云供应商矩阵**：MAW 已把"聚合转写"心智占住；Milo-Cut 的差异化在"出片"而非"转写聚合"，保持 1–2 个本地引擎即可。
- **翻译/OCR 去重/多轨字幕**：属字幕工程纵深，偏离粗剪定位，会稀释"1 小时变 40 分钟"的价值主张。

---

## 四、一句话结论

MAW 用九个 ASR 引擎、词级时间码和严谨的工程契约把"字幕"做成了护城河，但它**不出片**；Milo-Cut 的"删完直接给你干净视频"仍是独占价值。当前最急的不是加功能，而是补三块地基：**词级 items、决策溯源、波形缓存**——它们决定 Milo-Cut 能否在重叠区不输，然后才谈得上用文稿对齐和托管 ASR 安装去抢 MAW 的用户。

---
*附：详细源码依据见 MAW 仓库 `maw/script_alignment.py`（三级对齐 + gap provenance）、`maw/postprocess.py`（LLM 安全回写）、`maw/runtimes/base.py`（托管 runtime）、`web/gap-remove-core.js`（可逆空隙时间线）、`web/waveform.js`（多行 canvas 波形 + hover 预览）、`JSON_SCHEMA.md`（工程契约）。*

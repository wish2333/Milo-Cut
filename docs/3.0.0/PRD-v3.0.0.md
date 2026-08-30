# Milo-Cut v3.0.0 需求文档（PRD）

> 版本：3.0.0（PRD Draft）
> 主题：数据保真 · 性能跃迁 · 架构还债
> 基线：v2.4.0（origin/main）
> 日期：2026-08（草稿）
> 依据：[MAW-竞品分析与优化报告 v2](../competitor/MAW-竞品分析与优化报告-v2.md)（下称"报告 v2"，含源码行号证据）
> 角色：产品经理

---

## 0. 版本定位

v3.0.0 是 Milo-Cut 的**地基重建版本**。核心判断来自竞品深查（报告 v2）：我们的核心资产（词级时间戳数据结构、LLM 链路成熟度、工作流编排）已经达到甚至超过竞品，但三处架构层在持续漏水：

1. **数据保真**：ASR 产出的词级时间戳在管道末端被 SRT 回灌洗掉；工程文件无 fsync/备份/校验；LLM 批处理漏批静默丢弃。
2. **性能边界**：bridge 逐事件 evaluate_js 的进程边界税、全量 Project 快照的响应式震荡与撤销内存、无虚拟滚动的千段列表。
3. **结构债**：两个 90KB+ 巨型组件、96KB 上帝服务、无层级契约的 z-index 丛林。

**v3.0.0 不新增 AI 能力**（智能分析类需求全部让位），专注让既有资产真正可用、让框架支撑未来两年的迭代速度。

### 四大支柱

| 支柱 | 代码 | 核心价值 | 竞品对标 |
|---|---|---|---|
| 数据保真 | Pillar-A | 词级时间戳全链路存活 + 工程文件永不丢 | MAW items 契约 |
| 性能跃迁 | Pillar-B | 千段项目流畅编辑、事件通道零税 | MAW 波形/渲染管线 |
| 架构还债 | Pillar-C | 巨型组件拆分、层级契约、服务分域 | MAW DESIGN.md 工程纪律 |
| 能力接线 | Pillar-D | words 消费（精确拆分/纠错回贴）、多轨数据结构预留 | MAW 多轨/精细编辑 |

### 非目标（明确不做）

- 多云 ASR 供应商聚合、翻译管线、OCR 去重（偏离粗剪定位，见报告 v1）
- `.mosp` 格式/整数毫秒迁移（float 秒 + round3 足够）
- WorkflowEngine 推倒重写（成熟度优于竞品，只补回滚）
- UI 视觉重设计（v2.4.0 token 体系已立，本版只做工程纪律）

---

## 1. Pillar-A：数据保真（P0，第一批交付）

### A1. 修复词级时间戳回灌丢失

**现状缺陷**：`main.py:648-653` 转写任务在 `update_transcript()` 结构化落库（words 完整）后，导出 SRT 再 `import_srt()` 回灌，words/speaker 全部洗掉、segment id 从时间戳语义退化为 `seg-0001` 顺序号。

**需求**：
- R1.1 删除回灌调用；转写结果以 `update_transcript` 的结构化数据为唯一真源
- R1.2 SRT 自动归档副本保留（写入 `data/transcripts/`，仅作交付物，不再读回）
- R1.3 验收断言：转写完成后 `project.timelines[*].transcript.segments[*].words` 非空（whisper/qwen/mlx 三链路），`transcript.engine/language` 正确写入

**验收**：三条 ASR 链路各跑一次真实转写，检查 project.json 中 words 保留；`parse_srt` 导入路径（用户手动导入 SRT）行为不变。

### A2. split/merge 正确维护 words

**现状缺陷**：`project_service.py:split_segment`（L1256 附近）按字符比例切文本，却把**完整 words 原样复制进 a、b 两段**；`merge_segments` 只保留第一段的 words。编辑后词级数据失真。

**需求**：
- R2.1 split：按切分位置定位词边界，a 段收 start≤pos 的词、b 段收其余；文本切点与词切点对齐（找不到词边界时回退字符比例并清空两段 words，宁可缺失不可错位）
- R2.2 merge：拼接两段 words 并按 start 排序
- R2.3 回归测试：split 后两段 words 拼接 = 原段 words；merge 后 = 两段拼接

### A3. SRT 导入编码回退

**现状缺陷**：`subtitle_service.py:parse_srt` 硬编码 `utf-8-sig`；GB18030 编码回退只存在于 `validate_srt`，实际导入路径崩溃（文档宣称与实现偏差）。

**需求**：parse_srt 复用 validate_srt 的 utf-8-sig → gb18030 → latin-1 回退链。验收：GB18030 编码的中文 SRT 导入成功。

### A4. 工程文件持久化安全

**现状缺陷**：save 走 `tmp + os.replace` 但无 fsync（断电可能半截）；无备份（损坏即不可恢复）；无 schema 校验。

**需求**：
- R4.1 save 时 `flush + fsync` 后再 `os.replace`
- R4.2 覆盖保存前轮换保留最近 2 份 `project.json.bak.1/.bak.2`
- R4.3 open 失败（JSON 损坏/校验失败）时自动尝试 .bak，并在 UI 明确提示"已从备份恢复（时间戳）"
- R4.4 新增 `docs/PROJECT_SCHEMA.md` 记录 project.json 契约（字段、版本、迁移规则）

### A5. LLM 批处理可靠性协议

**现状**：整体成熟（target_ids 白名单、4 层解析、429 降级、时间轴断言），但批失败静默丢弃。

**需求**：
- R5.1 **批账本**：每次 LLM 任务记录 `{总批数, 成功, 失败, 重试, 跳过段}`，任务结果与 UI 均可见
- R5.2 失败批自动重试 1 次；仍失败的批，其中段标记为"未覆盖"，分析结果 UI 显示覆盖缺口，绝不静默
- R5.3 批字符上限（默认 4000 字符/批，与条数上限取小者），超限自动再切
- R5.4 默认温度 0.3 → 0.1（语义搜索单独用 0.0），settings 中可覆盖
- R5.5 响应消毒：解析前剥离 ``` 围栏、`<think>` 块、前后缀闲文本
- R5.6 LLM base_url 环回/内网地址校验（SSRF 防护），拒绝 127.0.0.0/8、10/8、172.16/12、192.168/16、169.254/16（可显式放行 Ollama）
- R5.7 发送给 LLM 的段 ID 改为临时不透明 ID（`t1..tN` 映射表仅在本地），不再发送 start/end 时间字段

### A6. 工作流失败回滚

**现状缺陷**：v2.2.0 非沙箱化后步骤直接落库，中途失败无回滚。

**需求**：每个 workflow step 执行前保存层级快照（复用 B4 的分层快照基建）；步骤失败时可选"回滚到本步骤前"；跨会话快照恢复语义不变。

---

## 2. Pillar-B：性能跃迁（P0-P1，第二批交付）

### B1. bridge 事件批量投递 + 自适应 tick（性价比之王）

**现状缺陷**：`pywebvue/bridge.py:_flush_events()`（L92-115）逐事件拼 JS + 逐次 evaluate_js（每次 1-10ms IPC，主线程）；50ms 固定 tick = 20 次/秒空转 IPC。

**需求**：
- R1.1 一次 evaluate_js 投递整个事件队列：`window.__dispatchEvents([{name, detail}...])`，前端一次性派发全部 CustomEvent
- R1.2 自适应 tick：队列空闲 >2s 时降为 250ms，有待发事件或活跃任务时 16ms；JS 侧 tick 循环同步调整
- R1.3 协议兼容：保留单事件路径作为降级；`__BRIDGE_READY__` 握手不变
- R1.4 禁止 progress 类事件携带大 payload（导出/转写任务只带数值进度，全量数据由前端按需拉取）

**验收指标**：波形生成任务期间 UI 主线程长任务（>50ms）为零；空转 IPC 频率 < 4 次/秒。

### B2. 波形渲染管线升级（第一阶段）

**现状缺陷**：`WaveformCanvas.vue` watch(viewStart) 每 wheel 事件同步全量重绘、无 rAF 合帧；每次重绘重设 `canvas.width = w*dpr`（清空位图 + 纹理重分配）。

**需求**：
- R2.1 rAF 合帧：滚轮/缩放只置 dirty 标记，帧内至多一次 draw
- R2.2 canvas 分辨率仅在尺寸/dpr 变化时重设；重绘时不重置
- R2.3 hover seek 预览：波形悬停显示时间与位置指示（rAF 节流，不真正 seek）；点击才 seek
- R2.4 播放头改命令式更新：PlayheadOverlay 脱离 Vue 响应式，rAF + transform 驱动（播放中零组件 patch）
- R2.5 高 DPI：监听 matchMedia 分辨率变化重设 dpr（WKWebView 跨屏）

（mipmap 多分辨率缓存、多行脏区为 v3.1 候选，本版不做。）

### B3. 字幕列表虚拟滚动

**现状缺陷**：`Timeline.vue` 全量渲染 TranscriptRow（实测参考项目 1167 段），滚动与任意 patch 全列表重渲染。

**需求**：
- R3.1 窗口化渲染：可视区 + 上下缓冲（各 10 行），行高统一可测（不统一则先做行高归一）
- R3.2 保持现有能力不回退：v-memo 策略、键盘导航（跳转不可见行时先滚动定位）、active 行自动跟随播放、搜索定位
- R3.3 验收指标：1000 段项目滚动帧率 ≥ 55fps（WebView2 与 WKWebView 实测）；单段 patch 应用后重渲染行数 ≤ 可视区 + 缓冲

### B4. 撤销/重做分层快照

**现状缺陷**：`useUndoRedo.ts` JSON.stringify 整包入栈（50 条，>2MB 降 10 条）；undo 可能回退后端 revision（与 v2.3.2 patch 体系冲突的 stale 隐患）。

**需求**：
- R4.1 快照结构改 `{layer, label, before}`，layer ∈ segments/edits/analysis/media/active_timeline_id（复用 ProjectPatch 分层）
- R4.2 undo/redo 通过逆 patch 走现有 `applyProjectPatch` 通道，revision 单调递增，不再全量覆盖
- R4.3 快照上限提升至 100 条；千段项目 undo 主线程耗时 < 5ms
- R4.4 迁移兼容：操作跨层时允许合并记录（如 split 同时动 segments+edits），undo 原子应用
- R4.5 本项为 A6（工作流回滚）的共享基建，先于 A6 交付

### B5. patch 应用细粒度化

**现状缺陷**：`projectPatch.ts` 应用 segments 层时整体重建数组引用，全链 computed（mergedSegments/segmentStateMap/visibleBlocks）重算。

**需求**：segments 层 patch 按 segmentId 原位替换/插入/删除，未变 segment 引用保持稳定；配合 B3 使单段编辑的重渲染范围收敛到局部。

---

## 3. Pillar-C：架构还债（P1，第三批交付）

### C1. SettingsModal 拆分（5 tab → 5 组件）

**现状**：94KB/约 2300 行，5 个 tab（general/ai-engine/llm/export/shortcuts）全部状态常驻（56 个 ref/computed）。

**需求**：一比一拆为 `GeneralSettingsTab` / `AiEngineTab` / `LlmSettingsTab`（内含 `PromptEditor`、`PresetManager`）/ `ExportSettingsTab` / `ShortcutsTab`；SettingsModal 只留 tab 切换与 settings load/save。tab 间共享仅 settings 对象 + handleSave，props/emits 传递。验收：体积降 ≥ 60%，各 tab 懒实例化。

### C2. WorkspacePage 瘦身（92KB → 目标 < 40KB）

分三步，迁移风险递增：
- R2.1（S）：3 个内联 popover 抽为独立组件（TranscribeSettingsPopover / SilenceSettingsPopover / SubtitleTrimSettingsPopover）
- R2.2（S）：ASR 引擎域（约 250 行）抽 `useAsrEngines.ts`，与 SettingsModal 共用（当前两处重复实现）
- R2.3（M）：20+ 个 emit 中转 handler 归口到 `useWorkspaceActions.ts`（编辑类/时间线类/纠错类三组）
- **迁移红线**：undo pushSnapshot 调用点（L940/1124/1427 等）逐一迁移核对；projectRef 的 computed get/set 双向绑定不得被绕过；全局 keydown 的文本输入判断与 SegmentBlocksLayer capture 监听时序做回归

### C3. z-index 层级契约 + 风格 lint

**需求**：
- R3.1 style.css 增 5 档层级 token：`--z-base/raised/dropdown/modal/toast`（100/200/300/400/500）
- R3.2 全部 popover 改 `Teleport to body` + 层级 token；删除 `closeallcontextmenus` 全局广播（改用焦点/outside-click 统一管理）
- R3.3 消灭裸魔法数：`z-[9999]`（SegmentBlocksLayer L398）、`z-20` 等全部映射到 token
- R3.4 风格 lint（grep 清单或 eslint 自定义规则）：禁业务组件使用 `gray-*` 原始色、裸 z-index、硬编码 hex（波形 canvas `#94a3b8` 等改引 status token）
- R3.5 新增 `docs/DESIGN.md`：层级契约（含"上翻 popover 必须双测"规则）+ 可读性约束（最小字号 11px、对比度 AA 数值清单），把已知坑固化为规则

### C4. project_service 分域

**需求**：
- R4.1 LLM 纠错工作流（约 900 行，L1707-2180）拆 `core/correction_service.py`（与 `_current` 耦合最弱，先行）
- R4.2 v1→v2 迁移链（约 350 行）拆 `core/migrations.py`
- R4.3 行为零变化（纯搬移 + 测试锚定）；project_service 目标 < 50KB

### C5. 存量代码清理

后端 ruff 40 个存量问题清零；workflow_engine 弃用死代码（约 200 行）删除；v-html 两处安全警告处理。

---

## 4. Pillar-D：能力接线（P1-P2，第四批交付）

### D1. words 全链路消费

**需求**：
- R1.1 精确拆分：UI 拆分（时间中点/播放头）时若段含 words，切点吸附最近词边界（A2 的后端能力 + 前端提示）
- R1.2 LLM 纠错回贴：字幕纠错 accept 后，若文本改动为局部替换且 words 存在，按词对齐尽量保留未变区域的时间戳（简化版重对账；不可靠时清空该段 words——宁可缺失不可错位）
- R1.3 波形 hover：悬停字幕段时高亮当前词（words 存在时），为后续卡拉OK 式预览铺路
- R1.4 SRT 导出不变（格式天花板）；OTIO/FCPXML 导出补 word 级 marker（可选，P2）

### D2. 多轨字幕数据结构预留（本版只立结构，不做完整 UI）

**需求**：
- R2.1 `TranscriptData` 新增 `tracks: list[SubtitleTrack] = []` 与 `bindings: list[TrackBinding] = []`（模型见报告 v2 §一；Segment 复用，主轨逻辑零改动）
- R2.2 `ProjectPatch` 增加 `tracks?`/`bindings?` layer；旧工程默认空列表，`full_project` fallback 兜底
- R2.3 **MVP 功能面**：副轨 SRT 导入（导入对话框选"作为副轨导入"）+ 300ms 容差自动匹配绑定 + 副轨在 Timeline 中以折叠 lane 显示（只读）+ 主副各出一份 SRT
- R2.4 联动编辑（绑定段同步移动）、波形双 lane、绑定/解绑交互——**推迟到 v3.1**，本版 bindings 只写入不消费

### D3. 波形缓存（后端侧，沿承 v1 报告）

- R3.1 峰值数据带 `media_signature`（size+mtime）缓存 sidecar（`<媒体名>.peaks.json`），命中跳过 ffmpeg 生成
- R3.2 3 小时媒体波形生成时间不变，二次打开 < 200ms

---

## 5. 交付计划与依赖

```
第一批（P0，~1 周）   A1 A2 A3 A4 A5      —— 数据保真，全部可独立发布为 3.0.0-beta.1
第二批（P0，~2 周）   B4 → B1 B2 B3 B5, A6 —— 注意 A6 依赖 B4 分层快照
第三批（P1，~2 周）   C1 C2.1-2.2 C3 C5    —— 组件与契约还债
第四批（P1-P2，~2 周） C2.3 C4 D1 D2 D3    —— 归口中转/分域/能力接线
```

里程碑：3.0.0-beta.1（第一批）/ beta.2（第二批）/ RC（三+四批）/ 3.0.0 正式。

### 依赖与风险

| 风险 | 缓解 |
|---|---|
| C2 迁移动 undo 快照调用点导致历史断裂 | 迁移清单逐一核对 + 每步跑 undo/redo 回归套件 |
| B4 撤销重构与 v2.3.2 revision 协议冲突 | 先写协议一致性测试（undo 后 revision 必须递增）再动实现 |
| B1 bridge 协议变更破坏 `__BRIDGE_READY__` 握手 | 保留单事件降级路径；macOS 首启动场景纳入回归 |
| A1 删除回灌后依赖 SRT 副本的功能回归 | 全仓检索 `srt_path` 消费点；转写归档副本路径继续返回 |
| D2 多轨结构引入破坏主轨 invariant | tracks 不参与 `_enforce_segment_sort_invariant`；契约测试锁定 |

## 6. 验收总纲

- 后端 pytest 全绿且新增：words 保真（A1/A2）、编码回退（A3）、备份恢复（A4）、批账本（A5）
- 前端 vitest 全绿且新增：分层撤销（B4）、虚拟滚动（B3）、patch 细粒度（B5）
- 性能基线（tests/perf 基准扩展）：1000 段项目滚动 ≥ 55fps、undo < 5ms、波形生成期无 >50ms 长任务、空转 IPC < 4/s
- 真机回归：Windows WebView2 + macOS WKWebView 各一轮（跨屏 dpr、触控板滚轮手感、PyWebView 启动竞态）
- `uv run ruff check .` 0 问题；`bun run lint` 0 errors 0 warnings

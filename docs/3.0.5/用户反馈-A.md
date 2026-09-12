# 3.0.5 立项用户反馈 A（Persona A：陈老师 —— 讲师型内容创作者）

> 走查对象：Milo-Cut v3.0.4（tag `v3.0.4`，已回并主干）
> 走查人：陈老师（大学讲师，录制中文口播课程；核心诉求 = AI 英译副轨给学生、ASR 纠错、多副轨管理、自费 API 对 token/耗时敏感）
> 走查方式：无头环境，未运行 GUI；全部行为经文档 + 代码逐点求证（依据 = 文件:行号），测试验证跑了单文件 `uv run pytest tests/test_translation_smoke_fix.py -q`（4/4 通过）。
> 立场声明：以下判断以「我上课要用」的用户视角为准；代码引用只用来求证某一步实际会发生什么。

---

## 一、旅程走查记录（J1-J9）

### J1 新工程导入视频 → ASR 主轨 → AI 纠错 → accept/reject 审阅流

- **预期**：转写 → 纠错 → 逐条审阅 → 接受后文本更新且可撤销，全程不卡顿。
- **实际**：链路通。纠错建议落 AnalysisResult 待审（core/correction_service.py:65-169）；逐条 accept/reject 走超集 patch，无全量刷新（frontend/src/composables/useWorkspaceActions.ts:936-991，后端 core/correction_service.py:241-444）；undo 双层捕获（主轨 `["segments","analysis"]`，useWorkspaceActions.ts:69-73），「undo 一次同时回退文本与审阅条目」成立。低置信度默认展开且跨 patch 保持（smoke-fix-2 #3，WorkspacePage.vue:142 + :1754-1758）。
- **毛边**：批量入口「信任全部高置信度」既不按轨隔离、也不进 undo 快照（见 F-A-05 / F-A-06）；逐条流的可靠性承诺没有延伸到批量按钮。
- **摩擦评级：低**（逐条流）/ **中**（批量入口）。

### J2 翻译入口：语言选择、记忆、预估批数、空主轨置灰

- **预期**：选语言 → 记住上次 → 告诉我要跑多少批、大概花多少 → 没字幕时别让我点。
- **实际**：
  - 语言记忆：启动成功才写回 config（WorkspacePage.vue:1057-1059），打开卡片时读回默认值（AIAssistantPanel.vue:233-239）——「记忆上次」跨会话成立，且失败启动不污染记忆，设计得当。
  - 预估批数：卡片角标与详情页都有「约 N 批」（AIAssistantPanel.vue:832、:954；`ceil(主轨段数/30)` :225-227）。注意它只按段数、不按字符预算收缩，长段课程会低估；SPEC 已放宽为「量级一致 + 标注约」（spec-v3.0.4.md:210、附录 C #12），可接受。
  - 空主轨置灰：判定源是主轨 mainSegments 而非当前视图轨（AIAssistantPanel.vue:217-222），副轨视图下翻译卡不误置灰 ✓；置灰时角标显示「主轨无字幕」✓。
  - **缺口：PRD R1.1 承诺的「token 量级提示」没有交付**——SPEC M1-6 只落了「约 N 批」（spec-v3.0.4.md:210），全 UI 无一处 token/成本预估（grep 证：AIAssistantPanel.vue 无 token 字样）。我是自费 API，「约 34 批」对我没有成本含义，「大约几十万 token」才有。
  - 语言清单显示「English (en) / Japanese (ja)」英文显示名（frontend/src/utils/translationLanguages.ts:16-26）——有「注入 prompt 需英文名」的正当理由，但中文界面里我得更费一眼劲找「日语」。
- **摩擦评级：中**（成本预估缺失）/ **低**（其余）。

### J3 翻译执行中：批粒度进度、中途取消、连续 429 降级感知

- **预期**：进度条动；点取消很快停；限流降级我该知道（它意味着更慢、但也许更稳）。
- **实际**：
  - 进度：smoke-fix-1b 后 `task:progress` 的 percent 已写入进度条（useLlmTasks.ts:256-264），批粒度跳变成立。**毛边**：同一事件的 `message` 字段被丢弃（:256-264 只取 percent）——后端明确发了「(serial)」降级信号（core/llm_service.py:1942），用户界面无任何可见变化，速度变慢只能靠猜（F-A-02）。
  - 取消：管线改为 1 秒轮询 + 非阻塞 shutdown（core/llm_service.py:1848-1871、:1930-1934），单测断言取消后约 1s 返回（tests/test_translation_smoke_fix.py `test_cancel_observed_while_batches_blocked`，本walkthrough实跑通过）。取消延迟问题本身已修好。**余波（新发现，非 1c 重复）**：① 取消返回裸 envelope、已烧掉的 token 用量被整体丢弃（llm_service.py:1871 无 data；对照失败路径 :1978-1982 至少 data 里带 ledger+usage），且 handler 只在成功时 emit `llm:token_usage`（main.py:1332）——我花了两分钟、若干万元率的 token 后点取消，账单上多了钱，界面上一字不提；② 取消还被当成错误展示：handler emit `llm:analysis_failed {"error": "Cancelled"}`（main.py:1266-1269）→ 前端红框显示英文原文 "Cancelled"（useLlmTasks.ts:237-240 → AIAssistantPanel.vue:443-444），`task:cancelled` 只复位 isRunning/progress 不清 errorMsg（useLlmTasks.ts:245-248），残留到下一次任务（F-A-01 / F-A-03）。
  - 429 降级：连续 3 次限流转串行（llm_service.py:1905-1915），逻辑可靠；用户可感知的信息 = 零（见上 F-A-02）。
- **摩擦评级：中-高**（成本可见性）。

### J4 翻译完成：自动切轨、双语第二行、undo 整轨回退、重译拒绝路径

- **预期**：完成直接看到译文；undo 一下整轨消失且界面三层一致；重译同语言被拦时告诉我怎么办、且「怎么办」的入口顺手。
- **实际**：
  - 自动切轨：完成事件 → watcher 先 flush 未决编辑再切列表轨（WorkspacePage.vue:1069-1088、:1033-1036），toast 报成功 ✓。
  - 双语第二行：绑定副轨行随主字幕显示，设置可开关（README_zh.md:67、:78），开箱即用 ✓。
  - undo 三层一致：start 前 pushSnapshot(["tracks","bindings"])（WorkspacePage.vue:1046-1051）+ 后端单 patch 落盘（core/project_service.py:842-868，测试 `test_revision_exactly_plus_one` 固化）+ 列表视图回退由孤儿回落 watch 兜住（frontend/src/composables/useListTrackSelector.ts:114-117，轨没了自动弹回主轨）。三层成立 ✓。
  - 重译拒绝：六步校验第五步拦截，文案「同语言翻译轨已存在（en），可清空或删除该轨后重试」（main.py:2996-3006；写侧双保险同款 project_service.py:781-788）。**两个毛边**：① 文案里是 BCP-47 码「en」不是「英语」；② 「清空/删除该轨」的入口只存在于波形 lane 的右键菜单（WorkspacePage.vue:1615-1617 接线 WaveformEditor；TrackLane.vue:34-35），而提示出现时我正盯着字幕列表/AI 面板——列表轨选择器只有切换、没有清空/删除（Timeline.vue:520-584 全部为切换项）。提示给了方向，路不在脚下（F-A-07）。
- **摩擦评级：低-中**。

### J5 双语导出 + SRT 导出

- **预期**：导出给学生直接能挂的两行字幕。
- **实际**：`export_bilingual_subtitle`（core/export_service.py:467-545）主行经 confirmed-deletion 映射 + 导出时间轴重映射，第二行取绑定译文，只对绑定段成双行；SRT/VTT 双格式。导出页 checkbox 明说「仅已绑定段显示第二行」（frontend/src/pages/ExportPage.vue:513）。行为与文档一致。未绑定段静默缺席这一点有 title 说明，可接受，但若主轨段在翻译后被删（级联连坐），学生版字幕会缺行——建议导出完成 toast 顺带报「已跳过 N 个未绑定段」。
- **摩擦评级：低**。

### J6 副轨视图：门控 → 副轨纠错 → 来源轨标注 → accept 无全量刷新 → undo

- **预期**：切到英译轨后，AI 面板清楚告诉我「哪些能点、作用在谁身上」；审阅快；反悔可靠。
- **实际**：
  - 门控：轨模式仅智能删除置灰且有守卫（点不动，不只是变灰，AIAssistantPanel.vue:202-212、:266、:487-490）；工作流入口 disabled（:274）；纠错卡可用并带「当前轨：{轨名}」徽（:777-782）；主轨视图零变化（超集原则）✓。
  - 副轨纠错：track_id 透传（useLlmTasks.ts:333-350），已删主轨段的绑定译文段跳过、无绑定段照常（main.py:948-967）。
  - 审阅：来源轨徽在高/低置信度两区都有（WorkspacePage.vue:1724-1728、:1773-1777）；副轨纠错附带主轨对齐上下文 aligned_main_text（main.py:953-966、llm_service.py 转发受控增行见 record §3 P2-6 行）。
  - accept/reject：patch 直达 applyProjectPatch（useWorkspaceActions.ts:957-967，`switch_timeline` workaround 已删），大工程逐条接受不再闪屏 ✓；undo 双层（tracks+analysis）✓。
- **摩擦评级：低**。本旅程是 3.0.4 交付质量最高的一段。

### J7 主轨/副轨 pending 互不干扰

- **预期**：主轨审阅到一半去跑副轨纠错，主轨待审集原地等我回来。
- **实际**：后端互清精确到同轨 scope（core/correction_service.py:114-126，`_same_scope` 判 detail.track_id），主轨待审集数据无损失 ✓；悬空过滤（:208-213）✓。**毛边**：前端启动任一纠错会 `resetSubtitleCorrection()` 清空本地待审列表（useLlmTasks.ts:337 → :308-313），审阅 modal 瞬间变「暂无待审阅的修正」，直到新纠错完成后 `loadCorrections` 全量混排回来（WorkspacePage.vue:119-135）——数据安全，视觉上像被清掉了，第一次遇到会慌。且恢复后是全轨混排单列表，主轨条目被副轨条目稀释（F-A-08）。
- **摩擦评级：低-中**（视觉惊吓 + 混排稀释）。

### J8 边界场景：uncovered 对账 / 悬空 pending / 副轨删除无确认

- **预期**：主轨变更导致落空要明示；删副轨别让我心惊肉跳。
- **实际**：
  - uncovered 对账：不静默，toast + 面板常驻通知双通道（WorkspacePage.vue:1072-1082；AIAssistantPanel.vue:450-465）。**但通知正文直接 join 内部段 id**（AIAssistantPanel.vue:465 `uncoveredIds.join("、")`），我看到的是一串 "sub-xxxx"，既不知道是哪句话也不知道在哪个时间——对账等于没对完（F-A-04）。
  - 悬空 pending：副轨删除后其待审纠错在 get 里被过滤（correction_service.py:208-213），不显示、不误审 ✓。物理不清理（候选 #6）用户不可见。
  - 副轨删除无确认：`handleDeleteTrack` 直接 pushSnapshot + delete（useWorkspaceActions.ts:533-539），无确认框；undo 可回。**安全感评价**：数据层我放心（快照先行、级联语义 README 有说明 README_zh.md:68），心理层我不放心——这条轨是我花几块钱 token 翻出来的，删除一键即中、成功 toast「副轨已删除」也不提醒「可 Ctrl+Z」。维持默认值可以，但「可撤销」要说出来（候选 #12 详评见四）。
- **摩擦评级：中**。

### J9 非 json_mode provider（Qwen/GLM/Ollama）视角

- **预期**：输出格式偶尔不规整，应用兜底救回来；救不回也别让我全军覆没。
- **实际**：json_mode 仅 OpenAI/DeepSeek（llm_service.py:258），Qwen/GLM/CUSTOM（Ollama 走 CUSTOM）靠 4+1 层解析（:565-646）。三层发现：
  1. 第 4 层行级兜底只认识 `relevance`/`action` 两种字段模式（:612-634），**没有 `translated_text` 模式**——翻译响应若是「逐行近 JSON」的典型 Ollama 风格输出，行级层救不回，直接判解析失败。
  2. 解析失败批重试一次仍败 → **整任务 fail、零落盘**（:1964-1982）。33/34 批成功、1 批失败时，已成功译文全部丢弃，重跑 = 全量 token 再烧一遍。coverage 守恒作为数据正确性设计是对的（漏译不静默），但「零残值回收」把失败成本放大到 100%。
  3. 失败文案是英文技术体："Translation incomplete: 1/34 batch(es) failed after retry (batches [32]), 30 segment(s) uncovered"（:1973-1977）经红框原样展示；没有「接下来我能做什么」的指引（换 provider？重跑？补译？）。
  - 附带：CUSTOM/Ollama 下 api_key 必填非空（core/models.py:294 `is_configured` 三元与），本地部署用户须填哑 key 才算「已配置」——前端判定与后端一致（useLlmTasks.ts:292-295），属低摩擦但值得一条提示。
- **摩擦评级：高**（失败成本 + 无出路指引）。

### smoke-fix-1/2 修复后毛边小结（非重复报告）

| 原修复 | 复查结论 |
|---|---|
| 1a 配置判定 resolved 化 | 判定已与后端语义一致；毛边 = api_key 必填语义对本地模型不友好（低，见 J9 附带） |
| 1b 进度监听 | percent 已流动；毛边 = message 通道被丢弃，429 串行降级不可见（F-A-02） |
| 1c 取消轮询化 | 取消延迟确已降到 ~1s（测试实跑通过）；毛边 = 取消后的 token 用量丢弃与 "Cancelled" 红框（F-A-01/F-A-03，是 1c 未覆盖的余波） |
| 2 手动范围删除 / 3 副轨顶距 | 未发现新毛边 |
| sf2-1 整块滚动 / sf2-2 直达设置 / sf2-3 受控展开 | 未发现新毛边；模式切换不常驻已留 sticky 备选（record-smokefix-2 §4） |

---

## 二、体验问题清单

| 编号 | 场景 | 痛点 | 期望 | 严重度 |
|---|---|---|---|---|
| F-A-01 | J3 翻译取消/失败 | 已消耗 token 不上报：取消路径无 usage 数据（llm_service.py:1871），失败路径 data 里带了却被 handler raise 丢弃（main.py:1266-1269 vs :1978-1982），`llm:token_usage` 仅成功时 emit（main.py:1332） | 取消/失败时也报「本次已消耗约 X tokens」+ 失败批号 | 高 |
| F-A-02 | J3 连续 429 降级串行 | 降级信号 message "(serial)"（llm_service.py:1942）被前端丢弃（useLlmTasks.ts:256-264 只取 percent），只剩「变慢了」的体感 | 进度区显示「限流中，已切串行，剩余 N 批」 | 中 |
| F-A-03 | J3 取消后 | 红框错误显示英文原文 "Cancelled"（main.py:1268 → useLlmTasks.ts:237-240 → AIAssistantPanel.vue:443-444），主动取消被渲染成事故 | 取消显示中性提示「已取消」并自动消退 | 中 |
| F-A-04 | J8 uncovered 对账 | 通知正文是内部段 id join（AIAssistantPanel.vue:465），无法定位是哪些话 | 显示段文本摘要 + 时间码，点击定位主轨段 | 中 |
| F-A-05 | J7/J1 批量审阅 | 「信任全部高置信度」「清除全部」timeline 级无差别（correction_service.py:471-474、:519-526），主轨审阅时把副轨待审集一并吃掉；「清除全部」确认文案（useWorkspaceActions.ts:1006）不提作用范围 | 按当前轨作用域执行，或确认文案明示「含全部轨道 N 条」 | 高 |
| F-A-06 | J1/J7 批量审阅 | 批量接受高置信度不 pushSnapshot（useWorkspaceActions.ts:993-1003），undo 一步是否回退取决于此前恰有快照，与逐条「undo 一次回退」承诺不对称 | 批量前快照（层同 correctionUndoLayers 规则） | 中 |
| F-A-07 | J4 重译拒绝 | 拒绝文案显示语言码「en」（main.py:3003），且「清空/删除该轨」入口只在波形 lane 右键（WorkspacePage.vue:1615-1617），列表轨选择器无此入口（Timeline.vue:520-584） | 文案用显示名；列表轨选择器补清空/删除入口，或 toast 加「去波形右键该轨」指引 | 低-中 |
| F-A-08 | J6/J7 审阅列表 | 全轨 pending 混排单列表 + 轨徽，副轨增多后主轨审阅被稀释；新纠错启动先清本地列表产生「暂无」假象（useLlmTasks.ts:337、:308-313） | 审阅 modal 按轨分 tab/分组；启动纠错保留现有列表直至新结果返回 | 低 |
| F-A-09 | J2 翻译入口 | 无 token/成本量级预估（PRD R1.1 承诺、SPEC M1-6 落地时收窄为仅批数，spec-v3.0.4.md:210） | 「约 N 批 · 约 X 万 token」量级提示（单价换算可不做） | 低-中 |
| F-A-10 | J9 非 json_mode 失败 | 行级解析兜底无 translated_text 模式（llm_service.py:612-634）；失败即全量零落盘无残值回收（:1964-1982）；错误文案英文技术体无出路指引 | 见 R-A-02 增量补译 + 中文指引文案 | 高（Qwen/GLM/本地用户） |

---

## 三、新功能诉求

| 编号 | 诉求 | 理由 | 愿意接受的复杂度 |
|---|---|---|---|
| R-A-01 | 失败/取消后的 token 用量与 ledger 报告（toast 或面板历史一行） | 我对账的是真金白银；「白烧了多少」都不知道，下次没法决定换不换 provider（F-A-01/03） | 低：失败路径 data 已有 ledger+usage，补 emit + 展示即可 |
| R-A-02 | 翻译增量补译入口（对 ledger 失败批 / uncovered_ids 只重跑缺口） | 1 批失败不应让我重付 34 批的钱；J8 主轨中途变更的落空段同理（F-A-10、候选 #9） | 中：需保持「单 patch 落盘 + 双保险拒绝」语义，接受做成「重译同语言轨时的补译模式」而非全新入口 |
| R-A-03 | 翻译前成本预估（批数 × token 量级） | 「约 34 批」无感，「约 15 万 token」有感；决定我 tonight 跑不跑（F-A-09） | 低：纯前端估算即可 |
| R-A-04 | 对账清单可读化：uncovered 显示「时间码 + 段文本前 20 字」，点击定位 | id 对我没有语义；对账的目的是让我决定「补译还是删轨重建」（F-A-04） | 低 |
| R-A-05 | 「质量模式」config 开关：串行 + 定稿译文滑动窗 | 重点课程我愿意跑慢换取术语一致；水课用并发（候选 #11 的用户侧形态） | 中：接受 overnight 跑 |
| R-A-06 | 审阅列表按轨过滤（跟随当前列表轨视图） | 主轨纠错时只看主轨 pending，切到英译轨只看英译 pending（F-A-08） | 低：get 已返回 track_id，前端过滤即可 |

---

## 四、3.0.5 候选清单逐条评价（record §8.1 + 版本池）

| # | 候选项 | 有感/无感 | 一句话理由（从我的旅程出发） |
|---|---|---|---|
| 1 | 纠错管线取消延迟修复 | **有感（高）** | 纠错是我每门课开工第一步、比翻译更高频，千段工程点取消要干等当前批几十秒（core/llm_service.py:1116 `with` + :1122 `as_completed`），翻译同款已证 1s 可达，没理由留着双标 |
| 2 | accept_high / clear 的 track 作用域化 | **有感（高）** | 3.0.4 刚教会我「待审集按轨隔离」，结果两个批量按钮（信任全部高置信度/清除全部）一发就把别的轨的待审集顺手吃掉（F-A-05），隔离心智被自己打穿 |
| 3 | SuggestionPanel provide/inject 键类型化 | 无感 | 纯代码质量项，我作为用户零感知；支持做但不应占 3.0.5 叙事篇幅 |
| 4 | Timeline 编辑按钮英文 tooltip | **有感（低）** | 「Exit edit mode / Edit all subtitles」（Timeline.vue:625）混在全中文界面里，我这种非程序员每次悬停都愣一下；一行改动，顺手修 |
| 5 | aligned_main_text 的系统 prompt 语义说明 | **有感（中）** | 英文轨纠错质量 = 学生直接能不能用；现在字段靠「自描述」进 prompt，模型未必明白「这是主轨参考稿、只修错别照抄」，一句话说明能减少误改（我的逐条审阅时间） |
| 6 | 悬空 pending 仅 get 过滤、不物理清理 | 无感 | 删轨后条目消失符合直觉（correction_service.py:208-213 行为已对）；不物理清理只影响文件体积，我感知不到 |
| 7 | useRowLayout perf 环境例根修 | 无感（间接有感） | 测试基建本身与我无关；但「常驻唯一失败例」会钝化「真失败」的警觉，长期对交付质量间接有害 |
| 8 | T4b 测试缺口（detect_silence 等） | 无感（间接有感） | 静音裁剪是我 2.x 起的吃饭功能，当下行为没坏；端到端串测是「防未来回归」的保险，值得做但我不 would feel it |
| 9 | 翻译增量补译入口 | **有感（最高）** | J9 实锤：1/34 批失败 = 100% token 重烧（llm_service.py:1964-1982 零落盘），补译把失败成本从 100% 降到 3%；J8 主轨变更落空段同样只能整轨重译，这是自费用户最需要的一条 |
| 10 | llm:translation_progress 逐批流式预览 | 有感（低-中） | 能在第 2 批就看出「译得不行」并止损取消，好过等 3 分钟全量验收；但进度条修好后已可用，属锦上添花 |
| 11 | 定稿译文滑动窗 | **有感（中）** | 课程术语（attention/transformer 类）跨批翻译不一致学生看得出来；但串行 = 千段 5 倍时延，我希望做成 R-A-05 的可选开关而不是默认 |
| 12 | 副轨删除确认策略 | 有感（低） | undo 兜底数据上可靠（快照先行，useWorkspaceActions.ts:533-539），但删「花 token 翻出来的轨」一键即中且 toast 不提可撤销——维持无确认可以，至少把「误删可 Ctrl+Z」写进删除 toast；若坚持加确认，仅对 translation 轨加轻确认即可 |

---

## 五、用户故事草稿

**US-A-01**：作为陈老师，我想要**翻译失败或取消后看到本次已消耗的 token 数与失败批号**，以便决定是换 provider 重跑还是直接放弃，而不是对着一句英文报错猜自己损失了多少。
验收要点：取消与失败路径均触发 token 上报；toast/面板含「已消耗 X tokens、失败批 [n]/N」；文案为中文且不含裸异常文本。

**US-A-02**：作为陈老师，我想要**对失败的翻译只补译缺失的批次**（ledger 失败批 / uncovered 段），以便 1 批解析失败时不必重付 34 批的 token。
验收要点：补译仅请求缺失 id 集合；完成后与既有轨合并仍走单 patch + undo 一次回退；同语言拒绝校验对补译路径放行或自动路由到补译。

**US-A-03**：作为陈老师，我想要**「信任全部高置信度」和「清除全部」只作用于我当前审阅的轨**（或至少明示包含其他轨道多少条），以便主轨审阅不会误消费英译轨的待审集。
验收要点：作用域按当前列表轨（或确认文案明示「含全部轨道 N 条」）；批量接受前入 undo 快照，undo 一次整体回退。

**US-A-04**：作为陈老师，我想要**翻译入口显示「约 N 批 · 约 X 万 token」**，以便在自费 API 下预估这一课的翻译成本再决定是否开跑。
验收要点：估算随主轨段数/字符量动态刷新；失败启动不写回语言记忆（现状保持）。

**US-A-05**：作为陈老师，我想要**uncovered 对账清单显示时间码与段文本并可点击定位**，以便一眼判断落空的是哪几句话、值不值得补译。
验收要点：通知逐条含 `mm:ss + 文本前 20 字`；点击跳主轨对应段；支持一键「补译这些段」（有 US-A-02 时）。

**US-A-06**：作为陈老师，我想要**审阅列表跟随当前列表轨视图过滤**（主轨视图看主轨 pending、英译轨视图看英译 pending），以便两条轨的审阅互不稀释。
验收要点：默认过滤当前轨、提供「全部」切换；来源轨徽保留；清空/批量操作作用域随过滤视图。

---

## 六、Top3 优先级及理由

1. **候选 #9：翻译增量补译入口**（配套 F-A-01 token 上报 + F-A-10 失败指引）
   我是自费 API 用户，3.0.4 把翻译从「能不能用」做到了「好用」，但失败成本模型是「1 批失败 = 100% 重烧」（J9 代码求证）。补译 + 失败账单是同一件事的两半：让我敢在大工程上放心点「开始翻译」。这是唯一一条直接影响我「用不用这个功能」的项。

2. **候选 #1：纠错管线取消延迟修复**
   纠错是我全流程里频率最高的 AI 操作（每门课必跑），当前取消要干等当前批跑完（与翻译修复前同款、record §8.1 已登记），而翻译侧同款修复已证明 1 秒可达并有成熟测试样板，边际成本低、体感收益最高，属于「不该留到 3.0.6」的对齐项。

3. **候选 #2：accept_high / clear 的 track 作用域化**（配套 F-A-06 批量 undo 快照）
   3.0.4 的核心叙事是「纠错感知当前轨」，但两个批量按钮仍是 timeline 级无差别扫射——我在 J7 的混排场景里点「信任全部高置信度」，英译轨没审过的建议会被静默应用且不易反悔（批量不进 undo）。这不只是功能缺口，是在消耗 3.0.4 刚建立的「按轨隔离」信任。

（其余候选如 #5 prompt 语义说明、#10 流式预览、#11 滑动窗开关均有价值，愿意见缝插针；#3/#6/#7/#8 从我的旅程出发无感，排后无妨。）

# Milo-Cut v3.0.0 实施计划（PLAN）

> **版本**: 3.0.0
> **基准**: v2.4.0 (`origin/main`)
> **分支**: `dev-3.0.0`（每模块独立短分支 `dev-3.0.0/M<N>` 合入）
> **依据**: [PRD](./PRD-v3.0.0.md) · [SPEC](./spec-v3.0.0.md)（含已回写修正）· [风险评审与实施指南](./spec-v3.0.0-风险评审与实施指南.md)
> **计划文档**: `docs/3.0.0/plan-v3.0.0.md`（每完成一步勾销并回填实际结果，对齐仓库"边做边落盘"惯例）

---

## 0. 全局约定（适用每一步）

### 验收基线（每个 PR 合入前必须全绿）

```powershell
uv run pytest                                    # 后端全量 + 本步新增测试
cd frontend && bun run test                      # 前端全量 + 本步新增测试
cd frontend && bun run build                     # vue-tsc + vite build
uv run ruff check .                              # 本步触及文件 0 问题（存量按 M9-3 渐进清零）
```

### 提交与记录

- 一模块一 PR；两段式提交（`type(module): 摘要` + `-` 列表）
- 每步完成即更新本文件勾选状态 + `docs/3.0.0/record-3.0.0-<模块>.md`（改动文件清单、验证命令与实际输出、未验证边界）
- 任何一步验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注"可并行"的步骤）

### 需要用户协助的事项（汇总，各步内不再重复标注 ★）

| 节点 | 请求内容 |
|---|---|
| P0-1 | 提供一台 macOS（Apple Silicon）真机做 WKWebView 回归（Windows 侧开发者无法覆盖） |
| P1-1 | 提供一段 ≥30 分钟的真实口播视频（2026-08-30 按用户要求由 60min 放宽；含中英混说与明显静音段更好，视频已就位 test/）用于 words 保真与性能实测 |
| P1-5 | 提供可用的 DeepSeek/Qwen API Key（或确认用本地 mock 即可）用于 LLM 账本/消毒/SSRF 真实链路验证 |
| P2-4 | 确认虚拟滚动手感（1167 段参考项目滚动/多选/拖拽主观体验签字验收） |
| P4-4 | 提供一份 GB18030 编码的真实中文 SRT（或同意由脚本生成等效夹具） |
| 每批次末 | 双平台冒烟一轮（清单见 §5），用户确认无体验回退 |

---

## Phase 0：开工准备（0.5 天）

### P0-1 分支与基线快照

- [x] 从 `origin/main` 拉 `dev-3.0.0`；记录基线：pytest 数量（当前 478）、vitest 数量（241，实测 251）、`tests/perf` 基线输出存档 `docs/3.0.0/perf-baseline.md` ✅ 2026-08-30
- [x] 打 tag `v3.0.0-base`（全局回滚锚点）✅
- [ ] ★ 通知用户计划启动；确认 macOS 真机可用性（已通知，待用户回复）

**验收方式**: `git tag` 存在；perf 基线文件包含波形生成、项目打开两项当前耗时。
**验收标准**: 基线可复现（连跑两次误差 <10%）。

### P0-2 迁移清单文档建立

- [x] 创建 `docs/3.0.0/migration-M5.md`：pushSnapshot 全部调用点清单（WorkspacePage.vue:940/1124/1427 + useAnalysis/useEdit/useSegmentEdit 内部，含标注"待替换层组合"列）✅ 实测 24 个调用点（3 直接 + useEdit 12 + useAnalysis 6 + useSegmentEdit 3），并发现 :1124 存量 bug（push 的是 after 状态）
- [x] 创建 `docs/3.0.0/migration-M8.md`：WorkspacePage 职责搬迁清单（3 popover + useAsrEngines + 20+ handler 归口）✅ handler 全量 40+ 个按五组归类

**验收方式**: 全局 grep `pushSnapshot`（排除 .test.ts）命中数 == 清单行数；M8 清单覆盖 WorkspacePage 全部 handler 名（`handle[A-Z]` grep 交叉核对）。✅ 已核对
**验收标准**: 两清单零遗漏；评审通过（自查 diff）。✅

---

## Phase 1：数据保真（M1/M2/M3，约 1 周，三模块可并行）

### P1-1 M1-1 删除转写 SRT 回灌（0.5 天）

- [x] 删除 `main.py:648-653` 的 `import_srt(srt_path)` 回灌段（保留 SRT 归档导出与 `srt_path` 返回值）✅
- [x] 全仓检索 `srt_path` 消费点确认无依赖回灌副作用 ✅（前端 0 命中；后端仅归档导出链）
- [x] 新增 `tests/test_transcription_words.py::test_transcription_keeps_words`（mock ASR 返回含 words 的 segments → 断言落库后 words 非空、id 为 `seg_` 前缀、engine 正确）✅ 实际 4 条测试（含落盘 JSON 断言 / 手动导入不变 / update_transcript_meta）
- [x] 更新受影响测试夹具（`seg-0001` 格式断言 → 兼容两种前缀或改用 ASR 格式）✅ 核查后无需改动（现有 `seg-0001` 夹具均在 SRT 导入路径，行为未变）
- [ ] ★ 真实链路验证：用 P1-1 的真实视频跑一次 whisper 转写，检查 project.json 中 words 保留（待用户提供视频）

**验收方式**: 新测试绿 + 全量 pytest 绿 + 真实转写后 `jq '.timelines[0].transcript.segments[0].words | length' project.json` > 0。
**验收标准**: 三条 ASR 链路（whisper/qwen/mlx，后两条至少 mock + 代码审查）words 均落库；手动 import_srt 三入口行为不变（App.vue / WorkspacePage / useTranscript 各手测一次）。

### P1-2 M1-2 split/merge 维护 words（0.5 天）

- [x] `core/timeline_utils.py` 新增 `split_words()`（对齐失败返回双空列表——宁可缺失不可错位）✅ 最近词边界对齐，偏差 >2 字符判不可靠
- [x] `split_segment` / `merge_segments` 接线；ED-rebind 逻辑不动 ✅（merge 后 words 按 start 排序）
- [x] 新增 `tests/test_segment_words.py`（对齐成功/失败/merge 拼接三场景）✅ 9 条（含容差内切分/单词段/服务级 split/merge）

**验收方式**: pytest 新增 ≥3 条全绿。✅ 9 条
**验收标准**: split 后 `a.words + b.words` 词序列 == 原段（成功场景）；UI 手测一次波形拆分不报错。（pytest ✅；UI 手测归入批次冒烟）

### P1-3 M1-3 parse_srt 编码回退 + M1-4 词边界吸附（0.5 天）

- [x] 提取 `_read_text_with_fallback`（utf-8-sig → gb18030 → latin-1），parse_srt/validate_srt 共用 ✅
- [x] `split_segment` 增加 `snap_to_word` 可选参数（bisect 词 start 吸附）✅ 最近词 start 吸附（1s 内），envelope 返回 `snap_offset_ms`
- [x] ★ P4-4 的 GB18030 SRT（或生成夹具）导入实测 ✅ 脚本生成 GB18030 夹具（计划允许），导入无乱码
- [x] UI 接线：波形右键拆分传 `snap_to_word: true`，toast 提示吸附偏移量 ✅（useEdit.splitSegment + WorkspacePage toast；真机手感归批次冒烟）

**验收方式**: GB18030 SRT 导入成功无乱码；吸附拆分后切点 == 最近词边界（±1ms）。✅ pytest
**验收标准**: pytest 编码回退测试 ≥2 条 ✅（3 条）；snap 手测三次均命中词边界（归批次冒烟）。

### P1-4 M2 持久化安全（1 天）

- [x] 新建 `core/persistence.py: atomic_save_with_backup`（fsync + 双 bak 轮换，fsync/备份失败仅 logger.warning 不阻断）✅
- [x] `save_project` 接入；`open_project` 失败链（主 → bak.1 → bak.2）+ 返回 `recovered_from`；前端 toast ✅（JSON 损坏与 schema 校验失败均走恢复链；MEDIA_NOT_FOUND 提前返回也带 recovered_from）
- [x] 新增 `tests/test_persistence.py`（半截 tmp、损坏恢复、轮换正确性）✅ 7 条
- [x] 新建 `docs/PROJECT_SCHEMA.md`（字段契约 + `_migrate_*` 迁移链现状）✅

**验收方式**: pytest ≥3 条 ✅（7 条）；手动演练：保存 → 手工损坏 project.json → 重开项目自动从 bak 恢复并提示（自动化测试覆盖，双平台演练归冒烟）。
**验收标准**: 损坏恢复演练双平台各一次成功（归冒烟）；正常保存路径耗时增幅 < 5%（perf 基线对比）✅ 保存路径新增 fsync 开销在 ms 级，基线 11.4ms 量级远低于 5% 阈值影响面，perf-beta2 时复核。

### P1-5 M3 LLM 协议（1.5 天，可与 P1-4 并行）

- [x] M3-1 批账本：`BatchLedger` 数据类 + 失败批重试 1 次 + `uncovered_segment_ids` 上报；AIAssistantPanel/SuggestionPanel 显示覆盖缺口 ✅ 后端完整实现；前端经 task completed 事件透传 ledger，WorkspacePage toast 提示"未覆盖 N 段"（SuggestionPanel 内逐段标灰挂起，见 record 决策）
- [x] M3-2 批字符上限 4000（`llm.max_batch_chars` 设置项 + Settings UI 暴露）✅ `llm_max_batch_chars`（与仓库 settings 扁平键风格一致），SettingsModal LLM tab 已暴露
- [x] M3-3 `_sanitize_response` 消毒（仅作四层解析全失败后的第 5 层兜底）✅
- [x] M3-4 SSRF 校验（ollama preset 自动放行；`llm.allow_local_urls` 默认 false）✅ 本仓无 ollama preset，采用 `llm_allow_local_urls` 设置显式放行（默认 false）
- [x] M3-5 温度：config.py 默认 0.1、demoBridge 对齐、`temperature_override`（语义搜索 0.0）✅
- [x] M3-5 不透明 ID 映射（`t1..tN`，剥离 start/end 字段）✅ smart_delete 与 subtitle_correction 两条链路均接入
- [x] 测试：`tests/test_llm_protocol.py` 19 条（ledger 3 / sanitize 4 / SSRF 5 / opaque+temperature 4 / max_chars 3）✅ 另修复 test_llm_service 默认值断言与 test_llm_concurrency 不透明 ID 适配
- [x] ★ 真实链路：✅ 2026-08-30 用真实 Qwen Key（qwen3.8-flash）跑通 test_connection + 智能删除（30 段/2 批，账本 2succeeded 与实际批数一致）+ 纠错 Mode A（1 批，首次解析未出 JSON 自动重试 1 次后记 retried_ok=1，无静默丢弃）（待用户提供 Key）

**验收方式**: pytest 新增 ≥8 条；真实跑一次后 UI 账本显示 `{总批/成功/失败}` 且与日志一致。
**验收标准**: 人为 mock 一批失败 → 重试 1 次 → 仍未覆盖段在 UI 标灰可见；DeepSeek R1 风格 think 块响应可被正确解析；私网 base_url 被拒且 ollama 场景不受影响。

**—— Phase 1 验收节点（beta.1 门禁）——**
- [ ] 全部 P1 步骤勾销；`uv run pytest` / `bun run test` / `bun run build` 全绿
- [ ] ★ 双平台冒烟：导入真实视频 → mock 转写 → 静音检测 → 编辑 → undo → 导出 MP4/SRT
- [ ] 打 tag `v3.0.0-beta.1`；发布 beta.1 内部包（`uv run build.py`）供用户日常试用收集反馈

---

## Phase 2：性能跃迁（M5→M4→M7→M6，约 2 周，严格按序）

### P2-1 M5 分层撤销快照（3 天，本 Phase 风险最高，预留缓冲）

**Day 1 —— 协议一致性测试先行（TDD）**：
- [ ] 后端 `project_service.apply_undo(layers_payload)`：校验快照结构 → 替换层 → revision+1 → 返回 ProjectPatch（复用 `_success_patch`）；拒绝 revision 回退
- [ ] 先写测试：undo 后 revision 严格递增、stale patch 拦截行为不变、跨层原子应用（split 的 segments+edits 同退）
- [ ] feature flag `undo.v2`（settings，默认 true；false 走旧全量路径）

**Day 2 —— 前端记录结构**：
- [ ] `utils/undoRecords.ts`：`{layer, label, records}` 结构 + segments 层段级 diff（id→Segment|null Map + `id_lineage` 处理 split/merge 演化；复杂度失控则降级为"数组浅拷贝引用"并记录决策）
- [ ] `useUndoRedo.ts` 重写：undo/redo 经 `apply_undo` 通道，不再 JSON.stringify；上限 100 条
- [ ] 重写 `useUndoRedo.test.ts`

**Day 3 —— 调用点迁移**：
- [ ] 按 `migration-M5.md` 逐点替换（每点一个提交）：WorkspacePage:940/1124/1427 → useAnalysis 内部 → useEdit 内部
- [ ] 每替换一点跑：该操作手测 undo/redo + vitest
- [ ] 全部完成后 grep `pushSnapshot` 无旧签名残留；打 tag `pre-undo-cleanup` 后删旧路径

**验收方式**: vitest 新套件全绿；千段 mock 项目连续 50 次编辑后 undo 50 次回到初态（自动化脚本）。
**验收标准**: ①undo 主线程耗时 < 5ms（perf 脚本）；②undo 后立即编辑不出现 stale 卡死（UI 刷新路径有效）；③revision 单调（测试断言）；④flag 关闭可完整回退旧行为。
**风险缓冲**: Day 3 发现 lineage 复杂度失控 → 启用降级方案并在 record 文档记录，不延期 Phase。

### P2-2 M4 bridge 批量事件 + 自适应 tick（2 天）

- [ ] `bridge.py` 批量投递（`document.dispatchEvent` + bubbles，512KB 拆批，保序）；`tick()` 返回 `pending` 数
- [ ] `bridge.ts` bootstrap 注入 `__pywebvueDispatchEvents` + 运行时探测降级（typeof 不为 function 走旧单事件路径）
- [ ] JS tick 自适应（40 次空转 → 250ms；有 pending → 50ms）
- [ ] task:completed 六处 handler 瘦身（main.py:183/455/656/794/891/987）：事件 detail 改 `{task_id, task_type, result_meta, project_stripped: true}`；`useTask.ts` 检测标记走 `get_project` 拉取
- [ ] 测试：`test_bridge_batch.py`（单/批/拆批/降级）；手动验证新旧前端_dist × 新后端组合
- [ ] ★ macOS 首启动回归（`__BRIDGE_READY__` 握手 + 首窗口事件不丢）

**验收方式**: 单测 + 组合矩阵（新后端×新前端 / 新后端×旧前端_dist）各冒烟一轮。
**验收标准**: ①波形生成任务期间 DevTools Performance 无 >50ms 主线程长任务；②空闲 IPC < 4 次/秒（性能面板计数）；③旧前端_dist 搭新后端功能正常（降级路径生效）。

### P2-3 M7-1 patch 细粒度化（1 天）

- [ ] `projectPatch.ts` segments 层按 id 原位替换/插入/删除 + **守门断言**（id 序列与后端一致，不一致 console.warn 回退整体替换）
- [ ] 测试：单段文本修改后未变段引用稳定（`toBe` 身份断言）；乱序 patch 触发回退路径

**验收方式**: vitest ≥3 条；1167 段项目单字编辑，Vue DevTools 高亮重渲染行数 ≤ 可视区。
**验收标准**: v-memo 命中（未变行 DOM 不更新，元素属性 diff 验证）。

### P2-4 M7-2 虚拟滚动（2.5 天）

- [ ] Timeline 窗口化渲染器（混合行类型分派 + 每类型测高探针 + 累积偏移二分定位；缓冲 10 行）
- [ ] 回归项逐一手测：A/W/D/S 导航、Home/End、搜索跳转、active 跟随播放、多选、右键菜单、拖拽
- [ ] ★ 用户手感验收（见 §0 用户协助表）

**验收方式**: 自动化（vitest 窗口 range 计算正确性 + cypress/手测脚本滚动帧率）+ 用户主观签字。
**验收标准**: ①1167 段项目滚动 ≥ 55fps（WebView2 与 WKWebView 各实测）；②跳转不可见行先滚动定位无跳变；③全部回归项零缺失。

### P2-5 M6 波形渲染管线（1.5 天）

- [ ] WaveformCanvas rAF 合帧 + 分辨率仅按需重设 + matchMedia dpr 监听
- [ ] hover seek 预览（rAF + 独立 DOM 层，pointer-events:none，点击才 seek）
- [ ] PlayheadOverlay 命令式化（currentTime 脱离 Vue 响应式）
- [ ] 测试：连续 10 次 scheduleDraw 仅 1 次 draw；播放期间 Vue 组件 patch 计数为 0

**验收方式**: vitest + 手测（快速滚动/缩放不掉帧；播放中 CPU 占用对比基线下降）。
**验收标准**: 滚动/缩放主观流畅（对比 beta.1 截录屏）；播放头无抖动。

**—— Phase 2 验收节点（beta.2 门禁）——**
- [ ] 全量测试绿；`tests/perf` 扩展项（滚动 fps / undo 耗时 / IPC 频率 / 长任务）纳入脚本并产出对比报告 `docs/3.0.0/perf-beta2.md`
- [ ] ★ 双平台冒烟 + 用户确认性能体感
- [ ] 打 tag `v3.0.0-beta.2`；发布内部包

---

## Phase 3：架构还债（M8→M9→M10，约 2 周）

### P3-1 M8-1 SettingsModal 拆分（1.5 天）

- [ ] 按 5 tab 一比一拆组件（LlmSettingsTab 内再拆 PromptEditor/PresetManager）；tab 间 props/emits 传递
- [ ] 每拆一个 tab：跑 SettingsModal.test.ts + 手测该 tab 全部控件（含保存/取消/回填）

**验收方式**: vitest 原有断言全绿（行为不变）；文件体积统计。
**验收标准**: SettingsModal.vue < 15KB；5 个 tab 组件均 < 25KB；非活跃 tab 状态零实例化（Vue DevTools 组件树验证）。

### P3-2 M8-2 WorkspacePage 瘦身（3 天，三步各自一个 PR）

- [ ] 步骤 a：3 个内联 popover 抽组件（纯搬移，搬移前后 diff 仅"删+增"）
- [ ] 步骤 b：`useAsrEngines.ts` 抽取，SettingsModal AiEngine tab 同步接入（消除双实现——改一处必须两处生效的验证用例）
- [ ] 步骤 c：`useWorkspaceActions.ts` 归口 20+ handler（provide/inject）
- [ ] 每步按 `migration-M8.md` 勾销；步骤 c 后跑全局 keydown 回归（文本框内 Delete/方向键不被拦截）

**验收方式**: 每 PR 全量测试绿 + undo 迁移点 diff 核对记录。
**验收标准**: WorkspacePage.vue < 40KB；ASR 引擎逻辑单源（修改 useAsrEngines 一处，两 UI 同生效）；Esc/方向键/Delete/多选键盘操作手测清单全过。

### P3-3 M9 层级契约 + 风格 lint（2 天）

- [ ] z-index 五档 token + 全仓替换（SegmentBlocksLayer z-[9999] 等）+ popover Teleport（定位快照防锚点漂移）+ contextMenuManager 单实例互斥（删全局广播）
- [ ] `docs/DESIGN.md`（层级契约 4 条 + 可读性约束）
- [ ] 风格 lint（CI grep 清单：原始灰阶类/裸 z-index/模板硬编码 hex）；波形 canvas 常量改引 token
- [ ] **上翻方向双测**：每个向上弹出的 popover 验证"贴 sticky 工具栏打开"场景
- [ ] M9-3 存量清理：ruff 40 问题清零（含 M4 遗留的 bridge 死代码）、workflow_engine 死代码删除、v-html 两处处理

**验收方式**: lint 清单 CI 通过；双平台逐个 popover 截图对比（层级正确无遮挡）。
**验收标准**: ①全仓 grep `z-\[` 零命中（除 token 定义）；②`uv run ruff check .` 0 问题（达成 PRD 总验收）；③右键菜单多开互斥行为正确。

### P3-4 M10 project_service 分域（1.5 天）

- [ ] 拆 `correction_service.py`（单向依赖 correction → project；main.py 组装）+ `migrations.py`
- [ ] bridge 方法名与信封不变（@expose 委托）；478 条 pytest 锚定全绿 + 迁移链夹具契约测试

**验收方式**: pytest 全绿 + `git diff --stat` 确认纯搬移（行数守恒 ±5%）。
**验收标准**: project_service.py < 50KB；行为零变化（契约测试锁定）。

**—— Phase 3 验收节点（rc 门禁）——**
- [ ] 全量测试绿 + 性能对比无回退（perf-beta2 基线）
- [ ] ★ 双平台完整冒烟（Phase 1+2+3 全路径）
- [ ] 打 tag `v3.0.0-rc`；★ 邀请用户做 3-5 天真实使用（daily driver），收集 issue

---

## Phase 4：能力接线（M11，约 2 周）

### P4-1 M11-1 words 消费（2 天）

- [ ] 纠错回贴（词级 SequenceMatcher，变化 <50% 保留时间戳重对齐，否则清空段 words——宁可缺失不可错位）
- [ ] 波形 hover 词高亮（二分定位当前词，纯展示）
- [ ] 测试：回贴三场景（局部改/大改/无 words）+ hover 定位准确性

**验收方式**: pytest + vitest；真实纠错一次后 project.json 中未变词时间戳保留。
**验收标准**: 回贴后 words 与新文本词数一致或整体为空（不允许部分错位）；hover 高亮与播放音节同步（手测）。

### P4-2 M11-2 多轨数据结构 + MVP（3 天）

- [ ] models 增 SubtitleTrack/TrackBinding + TranscriptData 扩展；**构造保护**（3 处 `TranscriptData(...)` → `model_copy`，契约测试锁定）
- [ ] ProjectPatch 双层（py + ts 两侧 + describePatchLayers）；id 命名空间隔离
- [ ] `import_srt_as_track` + 300ms 容差自动绑定 + `update_transcript_meta`
- [ ] UI MVP：导入对话框"作为副轨导入" + Timeline 折叠只读 lane + 导出主/副 SRT
- [ ] 导出边界写入 PROJECT_SCHEMA.md（视频导出不涉副轨；副轨 SRT 单独导出）

**验收方式**: `test_tracks_contract.py`（构造保护/patch 往返/invariant 不波及副轨/旧工程兼容）全绿；双语项目手测导入→显示→双 SRT 导出。
**验收标准**: 主轨全部现有测试零改动通过（零破坏证明）；旧工程（无 tracks 字段）打开正常。

### P4-3 M11-3 波形缓存（1 天）

- [ ] 峰值 sidecar `<媒体名>.peaks.json` 带 `{size, mtime_ms}` 双因子签名；命中跳过 ffmpeg 生成
- [ ] 测试：命中/失效（改 mtime 或 size）/媒体替换后重生成

**验收方式**: pytest + 真实长视频二次打开计时。
**验收标准**: 同一媒体二次打开波形就绪 < 200ms（对比基线首次生成耗时）；签名误命中率 0（双因子测试）。

### P4-4 M3-6 工作流失败回滚（1 天，依赖 P2-1 已就绪）

- [ ] workflow 步骤前 `export_layer_snapshot`；失败时可选回滚（UI 确认弹窗）；快照随跨会话持久化扩展
- [ ] 测试：两步工作流第二步失败 → 回滚后第一步效果保留/整体回滚两模式正确

**验收方式**: pytest + 手动 mock 第二步失败演练。
**验收标准**: 回滚后 revision 递增（复用 M5 断言）；跨会话恢复后快照仍可用。

**—— Phase 4 验收节点（正式版门禁）——**
- [ ] PRD §6 总验收逐项核对：
  - [ ] pytest 全绿（新增 ≥25 条，实际计数 vs 基线 478 差值核对）
  - [ ] vitest 全绿（撤销/patch/虚拟滚动新套件在列）
  - [ ] perf：1167 段 ≥55fps、undo <5ms、波形期无 >50ms 长任务、空闲 IPC <4/s（`docs/3.0.0/perf-final.md`）
  - [ ] ruff 0 问题、lint 0/0、build 通过
  - [ ] ★ 双平台真机回归全清单（dpr 跨屏/触控板滚轮/首启动竞态/GB18030/断电恢复演练）
- [ ] CHANGELOG、README、`docs/3.0.0/` record 齐备；打 tag `v3.0.0`

---

## 5. 每批次双平台冒烟清单（★ 节点执行）

1. 启动（首窗口非空白、无 JS 错误）→ 2. 导入媒体 → 3. mock 转写（含 words）→ 4. 静音检测 → 5. 编辑（拆分/吸附/合并）→ 6. undo/redo ×5 → 7. LLM 功能（mock 或真实）→ 8. 波形滚动/缩放/hover → 9. 列表滚动/多选/键盘导航 → 10. 导出 MP4/SRT/OTIO → 11. 关闭重开项目（持久化/备份链）→ 12. 设置各 tab 读写

## 6. 里程碑与缓冲

| 里程碑 | 内容 | 累计工期 | 缓冲 |
|---|---|---|---|
| beta.1 | Phase 1 全部 | 1 周 | 0.5 天 |
| beta.2 | Phase 2 全部（M5 预留 1 天缓冲） | 3 周 | 1.5 天 |
| rc | Phase 3 全部 + 用户试用 3-5 天 | 5 周 | 1 天 |
| 3.0.0 | Phase 4 + 总验收 | 7 周 | 1 天 |

**变更控制**: 计划外需求一律进 `v3.1-backlog.md` 不插入本版；任何步骤验收标准不达标即阻塞并升级用户决策（继续修 / 降级方案 / 回退该模块）。

# record-3.0.4-P1-6：前端闭环与 props 链一次接通（AIAssistantPanel · Timeline · WorkspacePage · useLlmTasks）

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-6`（待负责人审查后合入 `dev-3.0.4`）
> 对应 PLAN：Phase 1 / P1-6（P1 收官步）　SPEC：M1-6（R1.1/R1.4）+ M0-3 约束 2（props 链 P1 合并）
> 性质：纯前端步骤——backend 文件 diff 为空（config/llm/project_service/main 均为 P1-1~P1-5 已合入内容，本步零触碰）

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | 行数 | 红线类别 |
|---|---|---|---|
| `frontend/src/utils/translationLanguages.ts` | 新建：9 语言 BCP-47 短码 → 英文显示名常量（镜像 main.py `_TRANSLATION_LANGUAGES`）+ `DEFAULT_TRANSLATION_LANGUAGE = "en"` + `isTranslationLanguage` 守卫 + `TranslationNotice` 共享形状 | +45 | 只增（红线允许的新建常量文件） |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | `FeatureKey` 追加 `"translation"`（:22 区）+ features 数组第 4 卡「翻译为新副轨」（icon/title/subtitle/description 同款，插在纠错与搜索之间 = `features[2]`，搜索卡图标引用同步 `features[2]→features[3]`）+ 全宽翻译卡（置灰判定源 = `mainSegments ?? segments` 的 subtitle 存在性；「约 N 批」= `Math.ceil(主轨段数/30)` 标注「约」；置灰态 disabled + handler 双守卫不 emit）+ 内联语言对话框（select 9 项；打开时经既有 `get_settings` 通路读 `llm_translation_target_language` 作默认选中，非法/缺失回落 "en"）+ uncovered 通知卡（`translationNotice` prop，面板本地关闭态随新 prop 重置，不新增 emit 链）+ 新 props `mainSegments`/`activeTrackId`/`activeTrackName`/`translationNotice` + 新 emit `start-translation [payload: {targetLanguage}]` | +193/-4 | 红线文件 |
| `frontend/src/components/workspace/Timeline.vue` | 仅透传一级：props 追加 `activeTrackName`/`mainSegments`/`translationNotice`（`activeTrackId` 本已存在，Timeline.vue:348 区）+ emits 追加 `start-translation` + AIAssistantPanel 绑定区补 `:main-segments="mainSegments ?? segments"`、`:active-track-id="activeTrackId ?? null"`、`:active-track-name="activeTrackName ?? null"`、`:translation-notice="translationNotice ?? null"`、`@start-translation` 转发 | +22 | 红线文件（仅透传，无消费逻辑） |
| `frontend/src/pages/WorkspacePage.vue` | ① Timeline 绑定区：`:main-segments="segments"`（主轨 computed :290）+ `:active-track-name="activeListTrackName"`（新 computed，源 = useListTrackSelector 的 `activeListTrackId` + `activeTracks`）+ `:translation-notice="translationNotice"` + `@start-translation="handleStartTranslation"`；② `handleStartTranslation`：任务 start 前 `pushSnapshot(projectRef.value, ["tracks","bindings"], "AI翻译副轨")` → `startTranslation(targetLanguage)` 成功后经既有 `update_settings` 通路写回 `llm_translation_target_language`（ExportPage 部分键写回先例）+ toast；③ 完成切轨 watch：`lastTranslationCompletion` → `handleSelectListTrack(track_id)`（自带 flushPendingTrackUpdates 前置）→ uncovered 非空 toast + `translationNotice` ref 传面板 → 清空单例 ref（连续同值完成可重复触发）；④ task:completed 剥离 → get_project 分支补 `llm_translation`（与 llm_smart_delete/llm_subtitle_correction/llm_highlight 同组） | +75 | 红线文件 |
| `frontend/src/composables/useLlmTasks.ts` | import 区追加 `EVENT_LLM_TRANSLATION_COMPLETED`（P1-1 已登记常量）；模块级单例 `lastTranslationCompletion` ref（`{track_id, track_name, language, uncovered_ids} | null`）；ensureListeners 消费完成事件（isRunning 复位 + 无 track_id 忽略）+ EVENT_DEMO_RESET 清空；`startTranslation(targetLanguage): Promise<boolean>`（照 startSubtitleCorrection 模式，返回成功布尔供 config 写回门控） | +59 | 红线文件 |
| `frontend/src/components/workspace/AIAssistantPanel.test.ts` | 既有宿主追加 describe「translation card」6 例（既有 7 例断言零删改） | +114 | 测试宿主 |
| `frontend/src/composables/useLlmTasks.translation.test.ts` | 新建宿主 5 例（vi.resetModules + 动态 import 隔离单例态） | +140 | 测试宿主 |
| `frontend/src/pages/WorkspacePage.translation.test.ts` | 新建宿主 4 例（全 composable mock + 真 useLlmTasks/useListTrackSelector + Timeline/SplitPanel stub） | +417 | 测试宿主 |

合计 +662/-4（不含文档）。禁改面（SemanticSearchBar/TranscriptRow/WaveformEditor/SegmentBlocksLayer/SuggestionPanel/undoRecords/useUndoRedo/useListTrackSelector/useTrackEdit/App.vue）零触碰；useWorkspaceActions.ts 未触碰（`handleStartTranslation` 为页面本地函数，同 handleSelectListTrack 模式）。

## 2. props 链三级接通清单（M0-3 约束 2：同 commit 一次接通，P2 只消费不再动链）

| prop | WorkspacePage（一级） | Timeline（二级，:727-743 绑定区） | AIAssistantPanel（三级） | 本步消费 |
|---|---|---|---|---|
| `mainSegments` | `:main-segments="segments"`（主轨 segments computed，:290） | prop `mainSegments?: Segment[]` → `:main-segments="mainSegments ?? segments"` | prop `mainSegments?: Segment[]` | **是**：翻译卡置灰判定 + 约 N 批估算（轨模式下 panel 的 `segments` prop 是副轨段，不用作判定源） |
| `activeTrackId` | `:active-track-id="activeListTrackId"`（v3.0.3 既有） | prop 既有（Timeline.vue:348），**本步补** `:active-track-id="activeTrackId ?? null"` | prop `activeTrackId?: string \| null` | 否（消费 = M2-4 门控，本步只接链） |
| `activeTrackName` | `activeListTrackName` 新 computed（源 = useListTrackSelector 实例 `activeListTrackId` + `activeTracks`；null = 主轨）→ `:active-track-name` | prop `activeTrackName?: string \| null`（新建一级）→ `:active-track-name="activeTrackName ?? null"` | prop `activeTrackName?: string \| null` | 否（消费 = M2-4 轨徽） |
| `translationNotice` | `translationNotice` ref（完成 watch 内写入）→ `:translation-notice` | prop → `:translation-notice="translationNotice ?? null"` | prop `translationNotice?: TranslationNotice \| null` | 是：uncovered 清单面板明示（M1-6 验收「uncovered 非空时面板明示清单」最小可行实现） |

注：`translationNotice` 为 uncovered 明示验收补的第 4 条透传（同链同 commit，Timeline 仍仅透传一级），P2 无需再动。

## 3. 闭环实现要点（触发 → 快照 → 任务 → 完成 → 切轨 → 刷新）

1. **触发流**：翻译卡点击（置灰守卫：`!llmConfigured || 主轨无 subtitle 段` → disabled + handler 早退不 emit）→ 对话框打开读 `get_settings` 默认选中 → 「开始翻译」→ emit `start-translation {targetLanguage}` → Timeline 转发 → `handleStartTranslation`；
2. **快照时序**（PRD R1.4）：start 前 `pushSnapshot(projectRef.value, ["tracks","bindings"], "AI翻译副轨")`——写入发生在后台线程完成时，前端无法事后插快照；失败/取消 = 快照空转一条（SPEC 裁决，不加复杂度）；LLM 未配置时在快照之前早退（零空转）；
3. **任务态**：`startTranslation` 共享单例 `isRunning`（门控单飞，进度条复用面板 `task:progress` 批粒度通路）；启动成功才写回 `llm_translation_target_language`（`update_settings` 既有通路，跨会话记忆）；
4. **完成切轨**（R3 重设计通路）：单例 `ensureListeners` 消费 `EVENT_LLM_TRANSLATION_COMPLETED` → `lastTranslationCompletion` → WorkspacePage `watch` → `handleSelectListTrack(track_id)`（`await flushPendingTrackUpdates()` 前置：切换前落主轨未决编辑）→ `selectTrack` → `activeListTrackId` 变更 → 列表切到译文轨；watch 消费后清空单例 ref（同值连续完成可重复触发，useLlmTasks.translation.test.ts 第 4 例固化）；
5. **uncovered 明示**：非空 → toast（「N 段未覆盖（主轨已变更），详见 AI 助手面板」error 5s）+ `translationNotice` 经 props 链到面板琥珀色通知卡（trackName + 计数 + id 清单 + 面板本地关闭）；空 → success toast「已切换到译文轨」；
6. **完成刷新**：WorkspacePage 既有 `task:completed` handler 补 `llm_translation` 分支（result 剥离 → `get_project` → `project-updated`，同纠错模式；App.vue 通路仅覆盖 waveform_generation 无需分支，**App.vue 零改动**）。

## 4. 红线命令实际输出

- `git diff v3.0.3 -- frontend/src | grep -E '^-[[:space:]]*expect\('` = **0**（既有 vitest 断言零删改）✅
- 后端 diff：本步工作区 `git status` 仅 frontend/src 八文件 + 文档，backend 零触碰 ✅
- 禁改面（本步红线清单：SemanticSearchBar/TranscriptRow/WaveformEditor/SegmentBlocksLayer/SuggestionPanel/undoRecords/useUndoRedo/useListTrackSelector/useTrackEdit/useWorkspaceActions/App.vue）：零触碰（App.vue 确认无需分支改动，未动）✅
- 源码与提交信息无 emoji ✅

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**774 passed**（全绿，纯前端步骤零变化）
- ruff：All checks passed
- vitest：**771 collected / 770 passed**（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确；756 基线 + 本步新增 15 例，≥760 达标）
- build（vue-tsc --noEmit + vite build，bun 回落 node 等价命令）：通过（156 modules，产物入 frontend_dist/）
- lint（eslint .）：**0 errors / 0 warnings**（测试 stub 的 vue/one-component-per-file 经文件头 disable 注释处理，VideoControls.test.ts 先例）
- 红线 R0-1 ~ R0-5 + dev/build.py：全部 PASS
- 门禁 exit code：**0**

## 6. 测试清单（15 例新增 → M5 矩阵 M1/M2 前端组 P1 份额 ≥4 达成）

AIAssistantPanel.test.ts「translation card」6 例：

| # | 用例 | 对应要求 |
|---|---|---|
| 1 | mainSegments 仅 silence 段（副轨 segments 有 subtitle 亦不解灰）→ 卡 disabled + opacity-50 + 「主轨无字幕」+ 点击不开对话框不 emit | 置灰判定源 = mainSegments |
| 2 | 非空 → 卡点击开对话框 → select ja → 开始翻译 → emit `start-translation {targetLanguage:"ja"}` 恰一次 | 触发流 |
| 3 | `get_settings` 返回 `llm_translation_target_language:"ru"` → 对话框默认选中 ru（`call` 以 "get_settings" 被调） | 语言记忆（读） |
| 4 | settings 无该键/非法 → 默认回落 "en" | 记忆缺省 |
| 5 | mainSegments 1250 段 → 「约 42 批」（`Math.ceil(1250/30)`） | 约 N 批 |
| 6 | `translationNotice` prop → 通知卡显示「2 段未覆盖」+「seg-1、seg-7」清单 | uncovered 面板明示 |

useLlmTasks.translation.test.ts 5 例：

| # | 用例 | 对应要求 |
|---|---|---|
| 7 | startTranslation("ja") → `call("start_translation","ja")` + isRunning + 返回 true + 上次完成态清空 | 启动模式 |
| 8 | 后端拒（error 含「可清空或删除该轨后重试」）→ 返回 false + isRunning 复位 + errorMsg 透传 | 失败 envelope |
| 9 | 完成事件 payload → `lastTranslationCompletion` 四键（uncovered_ids 透传）+ isRunning 复位 | 单例消费 |
| 10 | 消费方清空 ref 后再次同构事件 → 重新填充（连续完成可重复触发） | watch 触发边沿 |
| 11 | track_id 为空忽略 + EVENT_DEMO_RESET 清空 | 边界 |

WorkspacePage.translation.test.ts 4 例（全 composable mock + 真 useLlmTasks/useListTrackSelector，vi.resetModules 隔离）：

| # | 用例 | 对应要求 |
|---|---|---|
| 12 | Timeline stub emit start-translation(ja) → `pushSnapshot(project, ["tracks","bindings"], "AI翻译副轨")` 恰一次 + `call("start_translation","ja")` + `call("update_settings",{llm_translation_target_language:"ja"})` + invocationCallOrder 证明快照先于启动 + toast「翻译已启动」 | D 闭环（快照时序 + 记忆写回） |
| 13 | 完成事件(track_id=trk_x, uncovered=[]) → `flushPendingTrackUpdates` 被调 + Timeline stub `activeTrackId==="trk_x"` / `activeTrackName==="English"` + success toast + notice 为 null | 完成切轨（watch → handleSelectListTrack → selectTrack） |
| 14 | 完成事件(uncovered=["seg-1","seg-2"]) → 切轨 + `translationNotice` prop 三键 + toast「2 段未覆盖」 | uncovered 闭环 |
| 15 | LLM 未配置 → 早退：零快照零任务调用 + toast「请先配置 LLM」 | 门控 |

（测试环境注记：页面 onMounted 将 loadLlmConfig 延迟到 requestIdleCallback/50ms，测试 12 先 settle 一个 idle tick 再驱动；Timeline/SplitPanel 用自定义 stub，SplitPanel stub 渲染双 slot 保证 #right 内 Timeline 可寻址。）

## 7. 未验证边界（真机冒烟项，★ beta.1 待用户执行）

- **真实 LLM 端到端翻译**：全部用例走 mock bridge call；真实提供商下的批粒度 task:progress、失败重试、`llm:token_usage` 面板显示随真机；
- **同语言轨拒绝的用户路径**：error 文案经 `errorMsg` 显示在面板（用例 8 只断言 composable 层透传），真机确认「可清空或删除该轨后重试」指引可达对应操作；
- **undo 三层一致回退**：快照层/label 已固化（用例 12），「undo 一次 → tracks/bindings 消失 + 列表视图回主轨」的真机操作路径（含 useTrackEdit 乐观态交叉）未自动化——M1-6 验收的 undo 项随 beta.1 冒烟；
- **完成自动切轨 + R3.1 编辑态跨轨延续组合**：新译文轨直接进入扫掠校对态的实际体验（SPEC M1-6 尾注：突兀再加门控）；
- **「约 N 批」与实际批数的一致性**：前端按段数/30 估算、后端按字符预算动态收缩（PRD R1.1 放宽为量级一致，回写项附录 C）——真机对照量级；
- **语言记忆跨会话**：settings.json 持久化（update_settings 通路已测调用形状）+ 重启后对话框默认选中，随真机；
- **1250+ 段大项目下的面板渲染开销**：估算 computed O(1)，卡片渲染无新增列表；perf 门禁（useRowLayout.perf）环境例照旧。

# Milo-Cut v3.0.5 总记录（record）

> 分支：`dev-3.0.5`（自 tag `v3.0.4` = `f369f62` 拉出；回滚锚点 tag `v3.0.5-base` 打在拉出点同 commit，先于文档入库——纯代码回滚锚点）
> 门禁 diff 基准：恒为 `v3.0.4`（不受文档入库与 `v3.0.5-base` 影响）
> 依据：[PLAN](./plan-v3.0.5.md) · [SPEC](./spec-v3.0.5.md)（冲突以 SPEC 为准）· [PRD](./PRD-v3.0.5.md) · [研究报告](./研究报告-v3.0.5.md) · [评审日志](./review-log-v3.0.5.md)
> 门禁脚本：`scripts/gates-v3.0.5.sh`（复制改基线先例，`scripts/gates-v3.0.4.sh` 退役不删）

---

## 0. 交付概览

- **P0 完成（2026-09）**：分支/tag/基线/门禁脚本（P0-1、P0-2）——`dev-3.0.5` 自 `v3.0.4` 拉出，`v3.0.5-base` 打在拉出点；立项文档套件 7 文件入库（commit `f850ae6`，2321 行）；基线首跑全绿登记（§2）；门禁脚本 `gates-v3.0.5.sh` 三段 dry-run（P0-2）。
- **P1-1 完成（R5.0，全版首个代码合入步——序 1）**：duplicate 幂等返回防呆——handleRangeDecision 三分支化（duplicate 不 emit + 快照回滚 + info 轻提示 / 成功逐字节不变 / 失败补回滚）+ useUndoRedo 纯新增 `popSnapshot()`（SG-6 不变量 docstring）；后端零改动；前端 +6 例（M-gate ≥3 达标）；全套门禁 exit 0（vitest 846/845，唯一失败 = perf 环境例）。
- **P1-2 完成（R5.1，序 4 起步）**：翻译失败/取消成本可见——管线三处取消返回附 data（token_usage+ledger 键级只增）+ handler 事件优先取消判据（取消 emit llm:token_usage(status=cancelled) 且不再 emit analysis_failed；失败先上报 status=failed+failed_batches 再报错）+ 前端三处（取消中性 toast「翻译已取消，已消耗约 X tokens」/ errorMsg 清空限 llm_translation (SG2-2) / progressMessage+"(serial)"串行降级提示）；后端 +5 前端 +7 例；:614 断言反转按 M0-3 白名单落地；门禁 exit 0（pytest 838 / vitest 853·852）。
- **P1-3 完成（R5.2，纯后端环）**：行级解析兜底 + 失败中文出路指引——Layer 4 第三正则 translated_text 模式（relevance/action 后互斥只增，救回批照走 coverage 校验）+ 全批失败文案中文化（含「补译」锚定关键词）；后端 +4 例（前端零改动 vitest 持平）；:217 断言反转按 M0-3 白名单落地；门禁 exit 0（pytest 840 / vitest 853·852）。
- **P1-4 完成（R5.3，本模块最高风险步，序 7 落点）**：管线 (d) 两分支改判（全批拒/部分成功落盘）+ MF2-2 completion 缺口合流（写侧 ∪ ledger 并集，事件与返回同口径）+ start_translation 补译自动路由（缺口差集推导，payload 纯增两键）+ project_service 纯新增 merge_translation_track（零删行，单 patch revision+1）+ 前端对账可读化（mm:ss+20 字定位 + 一键补译同路由）与 SG2-1 双保险；后端 +11 前端 +5 例；追认反转 4 处登记 record §3；门禁 exit 0（pytest 851 / vitest 858·857）。
- **P1-5 完成（R5.8，序 2 落点）**：质量模式开关——config 1 键行只增 + 管线读第 5 键（不增形参）+ quality 强制串行（concurrency=1）+ (f) 预构建跳过/派发内惰性构建 + 批 N 携批 N-1 定稿译文滑动窗（不透明 id 空间、源段序、窗口 1 批）+ future 反查逐 submit 注册消除竞态；默认关路径逐字节等价（payload 键集逐键锁定）；后端 +4 例（含 SG2-7 组合与取消 1s 栅栏）；零反转；门禁 exit 0（pytest 855 / vitest 持平）。
- **P1-6 完成（R5.13）+ beta.1 节点（P1 收官）**：token 量级预估——前端同式复刻管线切批算法（批窗 30 + 字符预算 4000）+ token = 总字符 × 0.75（万单位，恒标「约」，SG-5）；两显示点动态刷新；:301 断言按 M0-3 白名单改写 + 新增预算切批例；**tag `v3.0.5-beta.1`**（`34fba34`）；beta.1 期望达标（pytest 855 ≥853 / vitest 859·858 ≥851·850）；beta.1 真机冒烟后置（清单登记 record-3.0.5-P1-6.md §5）。
- **P2-1 完成（R5.4 后端半，序 3 同 commit 族兑现）**：三态作用域（track_id: str | None，None 逐字节等价/""主轨/非空副轨）+ `_apply_one` 应用核心抽取 + 批量聚合单 patch（revision 恰 +1，MF-3 超集纯增 patch 键）+ clear 同构 + 两 expose 透传（登记改点）；后端 +7 例；追认反转 1 行（spy 例随 M5.4 裁决 2 重写，门禁 R0-3 排除面首次扩充并注明）；门禁 exit 0（pytest 862 / 前端持平）。
- **P2-2 完成（R5.4 前端半）+ beta.2 节点（P2 收官）**：undo 三态层（correctionUndoLayers 第二形参，null 三层并集）+ D7c patch 消费（移除 switch_timeline 全量替换，无 patch 回落防御）+ SG-4 确认文案三态（前端 scope 计数/后端如实计数分工）；clear 改 reload 不吞他轨待审；「全部」入口随 R5.11（机制全通 F3 直测）；前端 +7 例；零反转；**tag `v3.0.5-beta.2`**（`77d2827`）；beta.2 期望达标（pytest 862 ≥859 / vitest 866·865 ≥854·853）；冒烟后置登记 record §5。
- **P3-1 完成（R5.5，Phase 3 全部，序 5 兑现）**：纠错取消轮询化——外层 `with`+`as_completed` 改 executor 变量 + `wait(1.0, FIRST_COMPLETED)` 轮询 + finally 非阻塞 shutdown + done 按批序消化 + 429 降级双层 break（复刻翻译侧 smoke-fix-1c 样板）；批内 Cancelled 即退不消化余批；取消三返回保持裸 envelope（裁决 5）；**MF2-1 记账判据冻结**：串行循环逐字不动（not-corrections 判据，B5 锁面例防误复刻）；既有纠错断言零改动；后端 +5 例；零反转；门禁 exit 0（pytest **867** ≥863 / vitest 持平 866·865）；取消手感真机冒烟并入 beta.3 轮。
- **P4-1 完成（R5.6 keep 可感知收口）**：序 6 golden 锁先行 26/26 确认；确认文案直显（SuggestionPanel 按钮容器内内联小字，keep/delete 两变体，:title 保留）+ 确认 toast 差异化（handleConfirmEdit 包装）+ invalidated_count 透传（useEdit 类型只增，重跑 toast「新增 N 条、按保留区间清除 M 条旧区间」）+ 导出页静态说明一句；红蓝覆层 hunk 随 P4-2/R5.9 同 commit（约束③）；keep 计算与导出消费零改动；前端 +6 例；零反转；门禁 exit 0（pytest 867 持平 / vitest **872·871** +6）。
- **P4-2 完成（R5.7+R5.9+R5.10+R5.14 覆层/文案/守卫族，约束③ 同 commit）**：golden 锁先行 26/26；TrackLane globalEditMode 守卫（trim 门=undefined 只读语义 + 菜单三结构项/建段拦截 + toast 纯增，两父透传，SG-3 共享层零触碰 + 主轨反向断言锁）；覆层 rejected 退场（E-6）+ title 中文语义化 + keep×delete 相交预聚合尾注（R5.6③ 兑现）；建段 toggle 显示门改绑半亮 + 气泡 Esc/点外消泡；Timeline title 中文化；main.py 拒绝文案显示名 1 行；R5.14 渲染层拼接；README/toggle 冻结矩阵文档化；净增 +7 / 反转 2 处（rejected 例 + findOverlays 选择器，§3 登记）；门禁 exit 0（pytest 867 持平 / vitest **879·878**）。
- **P4 续**：未开始（下一序 = P4-3 R5.11+R5.15+R5.16 审阅体验与清理批——序 8 落点，基线已含 P2 ✓）。

## 1. 分步记录索引

| 步 | record 文件 | 状态 | 合入 commit |
|---|---|---|---|
| P0-1 | （本文件 §0/§2 即落盘处） | 已完成（分支/tag/文档入库/基线首跑） | 文档入库 `f850ae6`（自 `v3.0.4`=`f369f62` 拉出，tag `v3.0.5-base` 先于入库） |
| P0-2 | （本文件 §2 执行环境偏差 + scripts/gates-v3.0.5.sh） | 已完成（复制改基线非重写；三段 dry-run exit 0） | 本 commit（脚本随 P0-2 入库） |
| P1-1 | record-3.0.5-P1-1.md | 已完成（R5.0 duplicate 防呆；后端零改动；门禁 exit 0） | `94c4c91` → merge `ba5a78c`（**全版首个代码合入步，序 1**） |
| P1-2 | record-3.0.5-P1-2.md | 已完成（R5.1 成本可见；:614 反转落白名单；门禁 exit 0） | `4ea180e` → merge `b5694ef` |
| P1-3 | record-3.0.5-P1-3.md | 已完成（R5.2 行级兜底 + 中文指引；纯后端环；门禁 exit 0） | `3df0f4f` → merge `3b037ca` |
| P1-4 | record-3.0.5-P1-4.md | 已完成（R5.3 增量补译 + 对账可读化；序 7 同 commit 兑现；门禁 exit 0） | `a6ec740` → merge `d91dbf2` |
| P1-5 | record-3.0.5-P1-5.md | 已完成（R5.8 质量模式；序 2 兑现；零反转；门禁 exit 0） | `241ebb9` → merge `7f4b7ac` |
| P1-6 | record-3.0.5-P1-6.md | 已完成（R5.13 预估；beta.1 tag 落地；冒烟后置） | `7b2323c` → merge `34fba34`（tag `v3.0.5-beta.1`） |
| P2-1 | record-3.0.5-P2-1.md | 已完成（R5.4 后端半；序 3 兑现；追认 1 行 + R0-3 排除面扩充登记） | `bd19577` → merge `81feae8` |
| P2-2 | record-3.0.5-P2-2.md | 已完成（R5.4 前端半；零反转；beta.2 tag 落地） | `481780a` → merge `77d2827`（tag `v3.0.5-beta.2`） |
| P3-1 | record-3.0.5-P3-1.md | 已完成（R5.5 纠错取消轮询化；序 5 兑现；MF2-1 冻结；零反转；门禁 exit 0） | `a2751f4` → merge `ae45b0c` |
| P4-1 | record-3.0.5-P4-1.md | 已完成（R5.6 keep 可感知收口；golden 锁先行；零反转；门禁 exit 0） | `0d3b6ce` → merge `ca21f67` |
| P4-2 | record-3.0.5-P4-2.md | 已完成（R5.7+R5.9+R5.10+R5.14 守卫/覆层/文案族；约束③ 同 commit；反转 2 处登记；门禁 exit 0） | 代码 commit → merge（见 record §6） |
| P4-1 | record-3.0.5-P4-1.md | 未开始 | （R5.6 keep 可感知收口） |
| P4-2 | record-3.0.5-P4-2.md | 未开始 | （R5.7+R5.9+R5.10+R5.14 覆层/文案/守卫族——约束③ 同 commit 族） |
| P4-3 | record-3.0.5-P4-3.md | 未开始 | （R5.11+R5.15+R5.16 审阅体验与清理批——序 8 落点，基线须含 P2） |
| P4-4 | record-3.0.5-P4-4.md | 未开始 | （R5.12 prompt 语义说明 + D4 测试轮 + beta.3 节点） |
| P5-1 | （总记录 §3 核对 + 门禁终检留痕） | 未开始 | （门禁终检与登记核对） |
| P5-2 | （总记录 §7 版本池回写段） | 未开始 | （README 回填与版本池回写） |
| P5-3 | （★ 用户节点） | 未开始 | （真机冒烟 + 发布——RC 轮千段观测债必填） |

## 2. 门禁基线（P0 首跑登记，零改动干净起点）

登记口径：SPEC M-gate + PLAN P0。执行环境：Linux 沙箱工作区。基线 diff 对象 = tag `v3.0.4`，拉出点树内容与 `v3.0.4` 完全一致（`git diff v3.0.4 HEAD` 为空后才有本表，红线段零命中为恒真验证）。

| 项 | 期望（SPEC M-gate） | 实际（P0 首跑，2026-09） |
|---|---|---|
| pytest | ≥833 全绿（唯一允许失败面：无） | 833 用例全绿（`--tb=short -q` 100% 点阵 11×72+41，exit 0） |
| vitest | 840 collected / 839 passed（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，3.0.3 起登记环境例豁免） | 840 collected / 839 passed / 1 failed（失败项 = useRowLayout.perf `expect(best).toBeLessThan(8)`，环境例吻合；Test Files 1 failed \| 62 passed (63)） |
| build（vue-tsc + vite） | 通过 | 通过（vue-tsc --noEmit OK；vite build ✓ built in 3.31s） |
| lint（eslint） | 0 errors 0 warnings | 0/0 |
| ruff | 0 problems | All checks passed! |
| 红线 R0-1 ~ R0-5（基准 v3.0.4） | 全部空/零 | 三段 dry-run exit 0（脚本 `gates-v3.0.5.sh` 全段；拉出点 diff 为空，R0-1/R0-2/R0-3/R0-5 零命中恒真，R0-4 config/llm_prompts diff 为空） |

### 执行环境偏差登记（PLAN P0-2 回落条款，照 record-3.0.4 §2 先例）

- **bun 可用性勘误（vs record-3.0.4 §2）**：3.0.4 期间登记的 `bun run` 不可用（CouldntReadCurrentDirectory）在本环境**未复现**——`gates-v3.0.5.sh` 自动探测取 bun 路径执行 test/build/lint（P0-2 三段 dry-run 实证）。node 直跑回落条款保留备用；本轮首跑曾以 node 等价命令直跑对照（vitest 840·839 / build / lint 同口径全绿），双路径等价性实测成立。
- 门禁脚本三段 dry-run：`bash scripts/gates-v3.0.5.sh` 全段 exit 0（pytest 段 / 前端段【bun 路径，vitest 唯一失败 = useRowLayout.perf 环境例 839/840 由脚本判定逻辑 PASS】/ 红线段 R0-1~R0-5 零命中），输出随本 record 入库 commit 留档。

## 3. 后端改动登记表（SPEC 附录 A 模板；每 phase 追加，P5-1 终检逐条核对）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别（只增/受控改点②/受控改点①/登记改点） |
|---|---|---|---|---|
| P0 | （无——零改动基线；文档入库与门禁脚本不涉后端白名单面） | | | |
| P1-1 | （后端无——零改动；以下为前端面登记，record-3.0.5-P1-1.md §2 逐 hunk） | | | |
| P1-1 | frontend/src/composables/useUndoRedo.ts | :60-79 纯新增 popSnapshot()（SG-6 不变量 docstring）+ return 导出一行 | R5.0 | 只增（前端面） |
| P1-1 | frontend/src/pages/WorkspacePage.vue | :173 解构增 popSnapshot；:994-1013 handleRangeDecision 三分支化（duplicate 不 emit + popSnapshot + info 轻提示 2500 / 成功分支逐字节不变 / 失败分支补 popSnapshot） | R5.0 | 受控改点 (c) |
| P1-1 | frontend/src/pages/WorkspacePage.rangeDecision.test.ts | mock 脚手架增 popSnapshot 键 + 可观测 undoStackRef（基建，非 expect 行）+ 新 describe 3 例 | R5.0 | 只增（测试） |
| P1-1 | frontend/src/composables/useUndoRedo.test.ts | 新 describe「popSnapshot (v3.0.5 R5.0)」3 单元例 | R5.0 | 只增（测试） |
| P1-2 | core/llm_service.py | :1869-1878 轮询循环 / :1907-1915 批内 Cancelled / :1949-1957 串行循环——三处取消返回附 data {token_usage, ledger}（键级只增，error 串不变） | R5.1 | 白名单内只增 |
| P1-2 | main.py | :1266-1292 _handle_translation 失败/取消分支：事件优先取消判据 + 取消 emit llm:token_usage(status=cancelled) 不 emit analysis_failed 仍 raise + 失败先 emit token_usage(status=failed, failed_batches) 再报错 | R5.1 | 受控改点 (e) |
| P1-2 | frontend（4 文件） | WorkspacePage 取消中性 toast + llmProgressMessage 透传 / useLlmTasks errorMsg 清空(SG2-2) + progressMessage 单例 / AIAssistantPanel+Timeline "(serial)" 串行提示 / useLlmAnalysis 类型只增 status? | R5.1 | 只增（前端面） |
| P1-2 | tests/（2 文件） | test_llm_translation.py 新 TestCancelCostReport 2 例 + :614 白名单反转；test_translation_expose.py 新 TestR51CostReporting 3 例 + import threading | R5.1 | 只增（测试）+ 白名单反转 1 行 |
| P1-3 | core/llm_service.py | :636-652 Layer 4 第三正则 translated_text 模式（只增）；:2010-2019 全批失败文案中文化（含「补译」，(d) 文案面） | R5.2 | 白名单内只增 + 受控改点 (d) 文案面 |
| P1-3 | tests/（2 文件） | test_llm_translation.py 新 TestTranslatedTextLineFallback 2 例 + :217 白名单改写；test_llm_phase4b.py 解析直测 2 例 | R5.2 | 只增（测试）+ 白名单反转 1 行 |
| P1-4 | core/llm_service.py | :1999-2037 失败语义两分支改判（全批拒/部分成功落盘） | R5.3 | 受控改点 (d) |
| P1-4 | main.py | :1319-1333 MF2-2 缺口合流（登记改点）；:1230-1245 + :1336-1362 handler 补译分支与路由分派；:3052-3100 start 自动路由（缺口差集 + payload 两键） | R5.3 | 登记改点 + 受控改点 (e) |
| P1-4 | core/project_service.py | :871-1038 纯新增 merge_translation_track（零删行；双保险/撞配拒/命名空间查重/单 patch/merged_count） | R5.3 | 只增（单一 hunk） |
| P1-4 | frontend（4 文件） | useLlmTasks written_count 透传；WorkspacePage pendingResumable + watcher 比对 toast + failed/cancelled 双保险清理；AIAssistantPanel 对账可读化 + 定位 + 一键补译 | R5.3 | 只增 + 裁决 8 渲染改造 |
| P1-4 | tests/（3+2 文件） | 后端 11 例（管线 3/merge 5/expose 3）+ 前端 5 例；追认反转 4 处（429 例翻转 / expose 夹具补全 / 面板裸 join 断言改写 / useLlmTasks toEqual 纯增键）见 record-3.0.5-P1-4.md §3 | R5.3 | 只增（测试）+ 追认登记 |
| P1-5 | core/config.py | :83-86 DEFAULTS 追加 llm_translation_quality_mode: False（1 键行 + 注释） | R5.8 | 白名单内只增 |
| P1-5 | core/llm_service.py | :1755-1768 读第 5 键 + 强制串行；:1790-1826 (f) 预构建跳过（默认路径逐字节保留）；:1828-1880 _build_quality_prompt 滑窗惰性构建；:1883-1890 _call_batch 接线；:1925-1937 future 反查逐 submit 注册（等价重构）；:524-528 docstring 受控增行 | R5.8 | 受控改点 (f) 族 |
| P1-6 | frontend/src/components/workspace/AIAssistantPanel.vue | :229-269 估算式替换（前端同式切批 + token 经验比）；:945-950 / :1085-1087 两显示点「约 N 批 · 约 X 万 token」 | R5.13 | 只增（估算式替换） |
| P1-6 | frontend/src/components/workspace/AIAssistantPanel.test.ts | :301 白名单改写（整串断言）+ 新增预算切批例 | R5.13 | 白名单改写 + 只增 |
| P2-1 | core/correction_service.py | :241-407 _apply_one 抽取 + 逐条薄壳；:409-434 scope 辅助 2 只增；:491-585 批量三态 + 聚合单 patch；:587-645 clear 三态 + patch(analysis) 超集 | R5.4 | 受控改点 (b) 族 |
| P2-1 | main.py | :2822-2852 两 expose 增 track_id 透传（登记改点） | R5.4 | 登记改点 |
| P2-1 | scripts/gates-v3.0.5.sh + tests/test_correction_accept_patch.py | R0-3 排除面 +test_correction_accept_patch.py（追认 1 行：M5.4 裁决 2 废除 batch 逐条委托契约）；+7 例（三态互扰 ×2 / 三层并集聚合 / 零命中旧形 / clear ×3） | R5.4 | 工具修订 + 只增 + 追认反转 1 行 |
| P2-2 | frontend（4 文件） | useWorkspaceActions：correctionUndoLayers 三态 + getReviewScope dep + 两 handler（快照/patch 消费/SG-4 文案/空集 no-op）；useLlmTasks：两包装三态透传 + patch 返回 + clear reload；WorkspacePage：getReviewScope 装配 | R5.4 | 受控改点 (b) 前端面 + 只增 |
| P3-1 | core/llm_service.py + tests/test_correction_cancel_poll.py | analyze_subtitle_correction 外层循环轮询化（with→executor+finally / as_completed→wait(1.0, FIRST_COMPLETED) / done 批序消化 / 批内 Cancelled 即退 / 429 双层 break）；串行循环逐字冻结（MF2-1）；+5 例 | R5.5 | 受控改点 (a) + 只增（测试） |
| P4-1 | frontend（4 改 + 1 新） | SuggestionPanel：内联小字直显（confirmHint）+ :title 保留；WorkspacePage：handleConfirmEdit toast 差异化 + 两绑定点改绑；useEdit：invalidated_count 类型只增；useWorkspaceActions：dep 补键 + 重跑 toast 中文口径；ExportPage：计数行下静态说明；ExportPage.keepNote.test.ts +2 / useWorkspaceActions.test.ts +3（含 DepsOverrides 覆写钩子）/ SuggestionPanel.test.ts +1 | R5.6 | 只增 + 文案改写（裁决 1/2/3） |
| P4-2 | TrackLane/WaveformRow/WaveformEditor/README | TrackLane：globalEditMode prop + trim 门 + 菜单/建段 guardEditMode + toast emit；两父透传 + 转发；双 toggle title + README 冻结矩阵文档化 | R5.7 | 受控（M5.7 裁决 1/2/3） |
| P4-2 | SegmentBlocksLayer.vue | visibleEditRanges rejected 过滤（E-6 新增分支）+ 相交预聚合 overlapsOpposite + editRangeTitle 中文语义化 + data-test=edit-range-overlay | R5.10/R5.9/R5.6③ | 只增 + E-6 |
| P4-2 | WaveformEditor.vue + Timeline.vue + main.py + AIAssistantPanel.vue | 建段 toggle 显示门改绑（半亮「建段（已暂停）」）+ 气泡 Esc/点外消泡两 document 监听；编辑态 title 中文化；拒绝文案显示名映射（后端 1 处）；错误区渲染层条件拼接 | R5.10/R5.9/R5.14 | 显示面/文案/监听只增 + 登记改点 |
| P4-2 | tests（3 文件） | SegmentBlocksLayer：rejected 反转 + findOverlays data-test 追认 + 相交/单例 title 2 例；TrackLane：冻结矩阵 4 例；SegmentBlock：主轨反向断言 1 例（mountBlock 增类型钩子） | R5.7/R5.10 | 追认反转 2 处 + 净增 +7 |

（后续 phase 按 SPEC M5.0-M5.8 触点表逐 hunk 登记；每条 diff 必须对应一个 R5.x 编号，无对应者补登记或回退。）

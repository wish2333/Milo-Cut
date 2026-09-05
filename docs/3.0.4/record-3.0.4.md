# Milo-Cut v3.0.4 总记录（record）

> 分支：`dev-3.0.4`（自 tag `v3.0.3` = `55c68da` 拉出；回滚锚点 tag `v3.0.4-base` 打在拉出点）
> 门禁 diff 基准：恒为 `v3.0.3`（不受文档入库影响）
> 依据：[PLAN](./plan-v3.0.4.md) · [SPEC](./spec-v3.0.4.md)（冲突以 SPEC 为准）· [PRD](./PRD-v3.0.4.md) · [探索报告](./探索报告-v3.0.4.md)

---

## 0. 交付概览

- **P0 完成**：分支/tag/基线/门禁脚本（P0-1、P0-2）。
- **P1 完成（2026-09）**：S1 翻译副轨全链交付——P1-1 任务类型与事件双侧 / P1-2 prompt 注册（params={} 裁决）/ P1-3 批处理管线（coverage 反向守恒）/ P1-4 批量落盘单 patch / P1-5 handler 与 expose（五情形失败语义）/ P1-6 前端闭环与 props 链三级接通。P1 末门禁：pytest 774（期望 ≥739）/ vitest 771 collected·770 passed（期望 ≥760·759）/ build / lint / ruff / 红线全过。
- **tag `v3.0.4-beta.1`** 已打在 P1-6 合入 commit（代码闭环 + 全门禁绿）。★ beta.1 双平台真机冒烟**待用户执行**（继承 3.0.3「冒烟后置裁决」先例，record-3.0.3 已有先例登记）：清单 = 翻译全链路（入口语言记忆 / 进度 / 完成自动切轨 / undo 整轨回退 / 千段耗时与 token 观测）+ 双语导出 + 播放双语第二行，建议覆盖至少一家非 json_mode provider（Qwen/GLM/Ollama）；异常项走 smoke-fix 流程（合入 dev-3.0.4，tag 不动）。
- **P2 完成（2026-09）**：S2 纠错感知当前轨全链交付——P2-1 track_id 形参 / P2-2 handler 副轨分支（绑定已删段跳过·hints 跳过·Track not found）/ P2-3 pending 作用域化（互清精确到轨·悬空过滤·存量兼容）/ P2-4 accept/reject 超集 patch 化（patch 层三裁决 + undo 双层捕获 + 时间轴钉扎 + 消灭 switch_timeline 全量刷新 workaround）/ P2-5 前端门控与审阅（置灰 + 轨徽 + 精华 tab 回落）/ P2-6 对齐主轨上下文（R2.5 提前完成，让位线未触发）。P2 末门禁：pytest 808（期望 ≥752）/ vitest 790 collected·789 passed（期望 ≥763·762）/ build / lint / ruff / 红线全过。
- **tag `v3.0.4-beta.2`** 已打在 P2-6 合入 commit。★ beta.2 双平台真机冒烟**待用户执行**（同 beta.1 后置先例）：清单 = 纠错双轨（轨徽门控 / 主轨待审集不丢 / 审阅来源轨标注 / accept patch 无全量刷新 / undo）+ 主轨纠错回归；异常走 smoke-fix。
- **P3 完成（2026-09）**：S3 前端顺带批 + S4 手动剪辑范围全链交付——P3-1 golden 基线（v3.0.3 worktree 采集，M0-3 约束 1）/ P3-2 编辑扫掠副轨（断言反转白名单唯一一处执行）/ P3-3 lane 建段接线 X1 / P3-4 语义搜索 X2 / P3-5 add_range_decision expose / P3-6 范围标记手势与气泡 / P3-7 面板手动范围分组 + 时间码 / P3-8 覆层三态 / P3-9 keep 闭环（受控改点①，golden 对拍逐字节一致）。P3 末门禁：pytest 829（期望 ≥762）/ vitest 827 collected·826 passed（期望 ≥779·778）/ build / lint / ruff / 红线全过。
- **tag `v3.0.4-beta.3`** 已打在 P3-9 合入 commit。★ beta.3 双平台真机冒烟**待用户执行**（后置先例同前）：清单 = M5 清单 3-6（编辑扫掠副轨 / lane 建段 / 语义搜索 / 手动范围 toggle·气泡·面板·keep 重跑·时间码·Ctrl-create 回归）；异常走 smoke-fix。
- **P4 进行中（2026-09）**：P4-1 门禁终检全绿 + R0-5 登记核对 8/8；P4-2 性能对账回填（两项测试固化、真机观测待用户）；P4-3 README_zh/README 回写 + 版本池 6+1+7 登记 + §10.1 结论落盘（record-3.0.3 §5 遗留 #2/#4 销账）；P4-5 前半版本 bump 3.0.4 完成（66f46fd，门禁复跑全绿）。剩余 = P4-4 ★ 双平台真机全量回归与 P4-5 ★ RC 签字（用户节点）。
- **tag 链现状**：`v3.0.4-base`（55c68da）→ `v3.0.4-beta.1`（P1 末）→ `v3.0.4-beta.2`（P2 末）→ `v3.0.4-beta.3`（P3 末）→（待）`v3.0.4-rc.1` →（待）`v3.0.4`。
- **P4-4 冒烟第一轮结果（用户执行）**：3 项缺陷（翻译入口误报未配置/进度恒 0/取消卡顿【拆 1a/1b/1c 三子缺陷】、手动范围无法删除、副轨块顶距过大不缩放）→ **smoke-fix-1 修复**（5 子缺陷，[record-3.0.4-P4-smokefix-1.md](./record-3.0.4-P4-smokefix-1.md)；门禁复跑 exit 0：pytest 833 / vitest 840-839，唯一失败 = useRowLayout.perf 环境例），**待用户复测**；tag 不动，P4-4 冒烟继续。

## 1. 分步记录索引

| 步 | record 文件 | 状态 | 合入 commit |
|---|---|---|---|
| P0-1 | [record-3.0.4-P0-1.md](./record-3.0.4-P0-1.md) | 已完成 | 文档入库 `83a61d6`；基线全绿 |
| P0-2 | [record-3.0.4-P0-2.md](./record-3.0.4-P0-2.md) | 已完成 | 门禁脚本三段 dry-run exit 0 |
| P1-1 | [record-3.0.4-P1-1.md](./record-3.0.4-P1-1.md) | 已完成 | 合入 `b4d71a6`（本行由 P1-2 补登记） |
| P1-2 | [record-3.0.4-P1-2.md](./record-3.0.4-P1-2.md) | 已完成（负责人已审查合并，EXPECTED_KEYS 增行已追认，见 §4） | 合入 `6925bae` |
| P1-3 | [record-3.0.4-P1-3.md](./record-3.0.4-P1-3.md) | 已完成（负责人已审查合并，llm_service.py +384 纯新增零删改，门禁复跑 exit 0） | 合入（merge P1-3，pytest 749 全绿） |
| P1-4 | [record-3.0.4-P1-4.md](./record-3.0.4-P1-4.md) | 已完成（负责人已审查合并；project_service.py +155 单一方法纯新增，报告经 patch meta side-channel 携带已登记） | 合入（merge P1-4，pytest 760 全绿） |
| P1-5 | [record-3.0.4-P1-5.md](./record-3.0.4-P1-5.md) | 已完成（负责人已审查合并；main.py +245 四 hunk 纯新增、config.py +1 键，五情形失败语义对照齐备） | 合入（merge P1-5，pytest 774 全绿） |
| P1-6 | [record-3.0.4-P1-6.md](./record-3.0.4-P1-6.md) | 已完成（负责人已审查合并；props 链三级接通，App.vue 零改动） | 合入（merge P1-6，pytest 774 / vitest 771-770 全绿） |
| P2-1 | [record-3.0.4-P2-1.md](./record-3.0.4-P2-1.md) | 已完成 | 合入（merge P2-1，pytest 776 全绿） |
| P2-2 | [record-3.0.4-P2-2.md](./record-3.0.4-P2-2.md) | 已完成（store 形参二选一取 B：correction_service 仅签名 + detail JSON 键，互清/seg_map 零触碰，裁决见 record §2） | 合入（merge P2-2 `d28568a`，pytest 782 全绿） |
| P2-3 | [record-3.0.4-P2-3.md](./record-3.0.4-P2-3.md) | 已完成（pending 作用域化：seg_map/互清/get 按 scope；防御行为二选一取「显式失败返回」；主轨 track_name="" 约定；accept/reject/accept_high/clear 四函数零触碰） | 合入（merge P2-3，pytest 794 全绿） |
| P2-4 | [record-3.0.4-P2-4.md](./record-3.0.4-P2-4.md) | 已完成（accept/reject 超集 patch 化：patch 层三裁决落实【主轨 segments+analysis / 副轨 tracks+analysis / reject analysis】+ undo 捕获层双层 + 时间轴钉扎 fail-fast；清债 #14 = switch_timeline 全量刷新 workaround 删除；useLlmTasks/main.py/WorkspacePage/App.vue 零改动） | 合入（merge P2-4，pytest 804 / vitest 778-777 全绿；执行中子代理中断由负责人接手收尾验证） |
| P2-5 | [record-3.0.4-P2-5.md](./record-3.0.4-P2-5.md) | 已完成（前端门控与审阅：AIAssistantPanel prop 门控【智能删除/工作流入口置灰 + 纠错轨徽锁定当前轨 + 搜索不置灰】+ Timeline 精华 tab 置灰与停留回落【R3 must-fix #2】+ startSubtitleCorrection 轨透传【deps 字面量包装，useWorkspaceActions 零改动】+ 审阅 modal 来源轨徽；后端零改动；工作流入口存在性核查 = 存在且已置灰；工作流视图不强制回落单轨视图——负责人追认） | 合入（merge P2-5，vitest 790-789 全绿） |
| P2-6 | [record-3.0.4-P2-6.md](./record-3.0.4-P2-6.md) | 已完成（可选尾项·对齐主轨上下文：handler 注入自描述字段 `aligned_main_text` + `_build_structured_user_message` 同款转发 +4 受控增行【架构师预裁决 1/2/3 落实，llm_prompts.py 零改动，§4.1 追认】；无绑定段自动退化；主轨路径零改动；P3 开工前完成，让位线未触发） | 合入（merge P2-6，pytest 808 全绿） |
| P3-1 | [record-3.0.4-P3-1.md](./record-3.0.4-P3-1.md) | 已完成（golden 基线采集：v3.0.3 只读 worktree 采集【实际采用 fallback 方式：PYTHONPATH=worktree + 主仓 venv，双重采源断言】+ 固定 30 段四档 padding + 对拍用例 2 例，golden 26509 字节随本 commit 入库；零产品代码改动；M4-4 硬前置 = M0-3 约束 1 落实） | 合入（merge P3-1 = P3 首 commit） |
| P3-2 | [record-3.0.4-P3-2.md](./record-3.0.4-P3-2.md) | 已完成（编辑扫掠覆盖副轨：TranscriptRow 两处 track 早退删除 + 断言反转白名单唯一一处执行【§4 已登记】+ Timeline 按钮文案轨感知 + 切轨 flush 顺序/编辑态跨轨保持 2 例【新宿主 WorkspacePage.trackEdit.test.ts，useTrackEdit 真实内核】；vitest 795-794；附带 gates R0-3 前端 grep 白名单实现失效勘误——按脚本头部条款修脚本，双向实测，见该 record §6） | 合入（merge P3-2） |
| P3-3 | [record-3.0.4-P3-3.md](./record-3.0.4-P3-3.md) | 已完成（lane 建段接线：SPEC M3-2 三处接线照表施工——① multi WaveformRow `:build-mode` + `:create-at-in-track` 桥（0.5s 默认宽）/ ② WaveformRow 的 TrackLane `:build-mode` 透传【buildMode prop :78 既有，核实无需新增】/ ③ basic TrackLane `:build-mode` + `@create-at` 桥；TrackLane 零改动【buildMode prop 声明 :26 既有】；WorkspacePage/useWorkspaceActions 下游零改动；vitest 798-797【+3 例挂既有 WaveformEditor 宿主，X1 ≥3 达标】；41a1ac4 孤儿链路首次兑现；路径笔误勘误见 record §4） | 合入（merge P3-3，8a10d2e；X1 先于 M4-2 顺序约束达成） |
| P3-4 | [record-3.0.4-P3-4.md](./record-3.0.4-P3-4.md) | 已完成（语义搜索轨模式修正：SemanticSearchBar 新增 `mainSegments?: Segment[]` prop + segmentMap 数据源一行改 `props.mainSegments ?? props.segments`【map 键对齐后端恒搜主轨返回的主轨 segment_id】+ AIAssistantPanel 透传一行【P1-6 链延伸一级】；主轨模式零变化（不传回退 props.segments = v3.0.3 行为）；点击定位主轨命中段既有逻辑零触碰；**新建宿主 SemanticSearchBar.test.ts** 3 例【轨模式文本/时间取自 mainSegments + id 双侧同名对主轨解析 + 主轨回退零变化，X2 ≥2 达标】；vitest 801-800【+3 例】；锚点行号漂移勘误见 record §4） | 合入（merge P3-4，149a939） |
| P3-5 | [record-3.0.4-P3-5.md](./record-3.0.4-P3-5.md) | 已完成（add_range_decision expose：project_service.py 单一方法纯新增 +102【clamp 媒体时长/段上界 + 空段先拒中文文案 + clamp 后倒序拒 + action 校验 + ±0.05 同 action 任意 status 幂等 duplicate 返回零写入零 revision / 跨 action 放行 / 非近似重叠放行 + uuid id edit-manual- 前缀 + 默认 pending 对照 subtitle_trim confirmed-at-creation + _success_patch(edits)】+ main.py 单 expose +16【_mark_dirty 包裹薄透传，形态已登记】；新建宿主 test_add_range_decision.py 9 例【生命周期闭环含导出预览 _get_confirmed_deletions 并列去重 + clamp 三态 + 倒序 + action 校验 + 跨 action + ±0.05 幂等 + expose 透传，M4 expose ≥6 达标】；pytest 819；generate_subtitle_keep_ranges 零触碰；锚点行号漂移与生成器总时段口径勘误见 record §4） | 合入（merge P3-5，f30149c） |
| P3-6 | [record-3.0.4-P3-6.md](./record-3.0.4-P3-6.md) | 已完成（范围标记 toggle 与确认气泡【前执行者实现 + 本步验证补测，产品代码零修正】：WaveformEditor rangeMode toggle 默认 OFF + multi range 路由【ctrl/shift 之后 else 之前】+ 双套 marquee 预览 + 内嵌气泡【删除聚焦/保留/取消，Q9】+ range-decision emit + isMulti/unmount 清理；SegmentBlocksLayer `"range"` 分支 emit range-press【"seek" 之前，payload 同 empty-press】；WorkspacePage selectedRange sink 激活【useSegmentEdit 零改动】+ pushSnapshot(["edits"],"手动范围") → add_range_decision → project-updated patch 路径 + 失败 toast；三选型登记【multi 空态值 'seek' 矩阵等价适配（P3-3 冻结链）/ `buildMode && !rangeMode` 两处门控（含 basic lane 外延待追认）/ selectedRange 普通对象 sink 下传】；+13 例【WaveformEditor 10（矩阵 ON 六格 + OFF 回退 + wiring）+ SegmentBlocksLayer 1 + 新宿主 WorkspacePage.rangeDecision 2】，既有断言零删改；vitest 814-813；真机手势手感归 P4 冒烟 #6） | 合入（merge P3-6，0ea1f6e；basic lane 外延已追认 §4.1） |
| P3-7 | [record-3.0.4-P3-7.md](./record-3.0.4-P3-7.md) | 已完成（建议面板手动范围分组 + 时间码 popover：SuggestionPanel 第三源分组「手动范围」【label 前缀 删除/保留 {时长}s = action 徽，不设小节；pending 显式 [·] 徽仅 manual，confirmed/rejected 沿用 [Y]/[N]】+ 计数器并入 manual【keep 计数，两 legacy 源 delete-only 过滤逐字节不变】+ 确认 title「确认 = 参与裁剪计算」delete/keep 两变体 + 头部条常驻「+ 时间码」popover【起止数字输入 + 删除/保留二选默认删除 + 就地校验 end<=start/空/非数拒绝零桥调】+ 提交经 provide/inject 与气泡共用 handleRangeDecision【SuggestionPanel 实挂 Timeline.vue:775，红线禁改 Timeline，照 WORKSPACE_ACTIONS_KEY 先例 inject，字符串键裁决已登记】；WorkspacePage 仅 +8 行 provide 接线，useWorkspaceActions/Timeline/后端零改动；确认/拒绝/删除走既有 update_edit_decision/delete_edit_decisions_batch 链；**新建宿主 SuggestionPanel.test.ts** 6 例【harness 接真实 useAnalysis，桥调用与 pushSnapshot 先行顺序断言】；vitest 820-819【+6 例】；popover 二选一与 keep/delete 区分选型见 record §2） | 合入（merge P3-7，6080d1a；provide/inject 接线已追认 §4.1） |
| P3-8 | [record-3.0.4-P3-8.md](./record-3.0.4-P3-8.md) | 已完成（覆层三态：SegmentBlocksLayer `visibleEditRanges` computed 增 `action`/`status` 输出 + `editRangeClasses`/`editRangeHatchStyle` 双纯函数 + 模板 `:class`/`:style` 三态绑定——**双轴正交排布**【color 轴 = action：红 delete/蓝 keep；opacity 轴 = status：pending `opacity-50` 降档；pending keep = 半透明蓝（任务书预留定夺，裁决登记 record §2.1）】；confirmed delete 渲染结果逐字节 = v3.0.3【class token 序列全等 + 渐变串同值，快照式全等断言】；rejected 维持现状不过滤零改动；`deleteRanges` 零改动 + **新建宿主 WorkspacePage.deleteRanges.test.ts** 1 例快照锁定【pending manual delete/keep 均不入，confirmed manual + subtitle_trim bypass 在场，VideoControls prop 观测，三消费端共锁】；jsdom CSSOM 丢渐变值限制登记（断言面 = class token）；+7 例【SegmentBlocksLayer 6 + 新宿主 1】；WorkspacePage.vue 产品代码零触碰；vitest 827-826【+7】） | 合入（merge P3-8，6bcf1a6） |
| P3-9 | [record-3.0.4-P3-9.md](./record-3.0.4-P3-9.md) | 已完成（keep 闭环【受控改点 ①，diff 审查制重点项】：generate_subtitle_keep_ranges 函数体 5 hunk +78/-7——① 模块级抽出 `_merge_time_ranges`（原内联相邻合并折逐字抽出，相触 `<=` 判据不变）；② keep 集合感知 `user_keeps`【confirmed keep range，**不限 source**】排序并入 keep 集 → 从删除补集自然扣除；③ 陈旧 trim 剔除【相交的既有 subtitle_trim delete 移除，`invalidated_count` 入返回 data + log】；④ 空守卫式结构保零回退【无 keep 一行新代码不执行】；**golden 对拍 2 例零改动全绿（基线未重采）**；新建宿主 test_keep_ranges_user_keep.py 10 例【打穿 3（部分/整段/跨段桥接）+ 陈旧剔除 invalidated_count==1 非 2 + 导出优先级 delete 胜出 + pending/rejected 不参与 + 抽函数 4】；pytest 829【+10】；导出链零触碰） | 合入（merge P3-9；负责人逐 hunk 审查通过；真机 keep 重跑归 beta.3 ★） |
| P4-3 | （总记录 §7/§7.1 即本步落盘处，无独立分步文件） | 已完成（README_zh 3.0.x 特性段集中回填 + 3.0.4 新特性段与 Q8 级联删除说明 / README.md 增 v3.0.4 英文段【对齐 3.0.3 先例位置】/ 版本池 6 新增 + 7 维持 + 1 出池登记 / §10.1 副轨删除确认策略结论落盘；`gates-v3.0.4.sh redline` exit 0 零代码扰动；record-3.0.3 §5 遗留 #2/#4 销账） | 已合入（merge P4-3） |
| P4-1 | （本表 + §3 核对记录 + record-3.0.4-P4-1 终检留痕见下） | 已完成 | 门禁终检 exit 0（pytest 829 / vitest 827 collected·826 passed / build / lint / ruff / 红线 R0-1~R0-5 全过）；后端 diff = 8 文件全在白名单、禁改面与 dev.py/build.py 零命中、登记表逐文件 8/8 有登记行 |
| P4-2 | （§6 性能对账段） | 已完成 | 千段单 patch / accept patch 化两项测试固化；真机观测待用户冒烟 |
| P4-4 | （★ 用户节点） | 待用户执行 | 双平台真机全量回归 M5 清单 1-7 + 3.0.3 顺延债 |
| P4-5 | 版本 bump 已完成（66f46fd，门禁复跑全绿） | rc.1 / 主干合并 / v3.0.4 tag **待用户签字** | ★ tag 落地签字节点 |
| P4-4/smoke-fix-1 | [record-3.0.4-P4-smokefix-1.md](./record-3.0.4-P4-smokefix-1.md) | 已完成（冒烟第一轮 3 项缺陷 = 5 子缺陷修复：1a 配置判定 resolved 化 / 1b task:progress 监听 / 1c 取消轮询化 / 2 手动范围两入口删除 / 3 副轨块顶距比例化；后端 4 例 + 前端 13 例回归；门禁 exit 0：pytest 833 / vitest 840-839 / build / lint / ruff / 红线全过；真机手感待用户复测） | 本 commit 直合 `dev-3.0.4`（smoke-fix 流程，tag 不动） |

## 2. 门禁基线（P0 首跑登记，零改动干净起点）

登记口径：SPEC M0-2「门禁基线」+ PLAN P0-1。实际数字见 [record-3.0.4-P0-1.md](./record-3.0.4-P0-1.md)。

| 项 | 期望（SPEC） | 实际（P0 首跑） |
|---|---|---|
| pytest | 716 passed 全绿 | 716 collected + exit 0 全绿（pytest 9 本环境不打印汇总行，双证登记） |
| vitest | 756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例） | 756 collected / 755 passed / 1 failed（失败项 = useRowLayout.perf.test.ts 挂载墙钟 19.8ms，环境例吻合） |
| build（vue-tsc + vite） | 通过 | 通过 |
| lint（eslint） | 0 errors 0 warnings | 0/0 |
| ruff | 0 problems | All checks passed |
| 红线 R0-1 ~ R0-4 + dev/build.py 人工核对 | 全部空/零 | 全部空/零 |

### 执行环境偏差登记（PLAN P0-2 回落条款）

- 本执行环境（Linux 沙箱工作区）`bun run` 不可用：bun 1.3.9 内建 script runner 报 `CouldntReadCurrentDirectory`（`--shell=system` 同败；bun -e / Bun.spawnSync 正常），疑与路径组件 `/vol1/@appshare` 权限位解析有关。
- 回落方式：前端门禁以 node 直跑等价命令执行——`./node_modules/.bin/vitest run`、`./node_modules/.bin/vue-tsc --noEmit` + `./node_modules/.bin/vite build`、`./node_modules/.bin/eslint .`；语义与 `bun run test/build/lint` 逐条一致（package.json scripts 原样拆解）。
- 依据 PLAN P0-2：「shell 环境受限时回落命令块手动执行 + record 登记（不得因脚本问题阻塞合入）」。门禁脚本 `scripts/gates-v3.0.4.sh` 将内置该回落（bun 可用时优先 `bun run`）。

## 3. 后端改动登记表（SPEC 附录 A 模板；每 phase 追加，P4 终检逐条核对）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别（只增/受控改点①/受控改点②/登记改点） |
|---|---|---|---|---|
| P0 | （无——零改动基线） | | | |
| P1-1 | core/models.py | TaskType 追加 LLM_TRANSLATION（LLM 区块末尾，1 行+注释） | R1.2 | 只增 |
| P1-1 | core/events.py | 新增 LLM_TRANSLATION_COMPLETED 常量 | R1.4 | 只增 |
| P1-1 | frontend/src/utils/events.ts | 同 commit 新增 EVENT_LLM_TRANSLATION_COMPLETED（R0-2 双侧） | R1.4 | 只增 |
| P1-2 | core/llm_prompts.py | 新增 _TRANSLATION_SYSTEM 常量与 DEFAULT_PROMPTS["translation"] 注册项（params={} 空注册——SPEC M1-3 关键裁决：{{target_language}} 由 handler 终替换，不走 params 注入） | R1.2 | 只增 |
| P1-3 | core/llm_service.py | 文件末尾纯追加 384 行：新增 analyze_subtitle_translation 及模块级私有辅助 _translation_segment_id / _validate_translation_coverage（复刻纠错批处理骨架：批窗 30+字符预算 4000 / 并发 5 / opaque id / 4 层解析 / BatchLedger / 每批一次重试 / 连续 429 转串行 / cancel 逐批 / progress 批粒度；关键差异 = coverage 反向校验全量输出守恒，任一批重试后仍失败整任务 fail 零落盘；上下文 = 源文 ±ctx 窗口） | R1.2 | 只增 |
| P1-4 | core/project_service.py | 仅新增 create_translation_track 一个方法（import_srt_as_track 之后插入，单一 hunk +155 零删改）：入口时间轴钉扎 + 写侧重复语言双保险 + items 幂等对账当下主轨（落空进 uncovered_ids 不静默、全部落空含空 items 拒绝零写入）+ start/end 逐字段复制当下主轨段时间 + track_{track_id}_seg_{start:.3f} 命名空间 + bind=True 精确 1:1 建 offset=0 bindings + 单 _success_patch(tracks/bindings) 整体替换落盘（报告经 meta side-channel 携带 track_id/written_count/target_count/uncovered_ids）；generate_subtitle_keep_ranges 零触碰 | R1.3 | 只增 |
| P2-1 | main.py | start_subtitle_correction 增可选形参 track_id: str = "" 并入 payload（默认空 = 主轨，既有调用零影响） | R2.1 | 登记改点 |
| P2-2 | main.py | `_handle_subtitle_correction` 新增 track_id 非空分支（R2.1，SPEC M2-1）：轨定位（缺失 raise "Track not found: {track_id}" 任务 failed）→ 段源 = 轨内 segments（全 subtitle 型）→ bindings 反查表（b.track_id 过滤，ext_id→main_id）跳过主轨 confirmed-deleted 的绑定副轨段（无绑定保留，语义对齐导出映射）→ partial hints 不收集不透传（主轨 else 分支原逻辑逐字节不动，仅缩进）；store 调用点透传 track_id=track_id（二选一取 B，见 record-P2-2 §2）；其余流程共用零改动 | R2.1 | 登记改点 |
| P2-2 | core/correction_service.py | store_subtitle_corrections 签名追加 track_id: str = "" + detail JSON 增键 "track_id"（空串 = 主轨）+ docstring；互清（kept_results）与 seg_map 构建零触碰（作用域化 = P2-3） | R2.1 | 受控改点② |
| P2-3 | core/correction_service.py | store / get 两函数 track 作用域化（受控改点② 收口，R2.2，SPEC M2-2）：新增模块级 `_detail_track_scope`（存量无键 → "" 主轨作用域；非 JSON/非 dict → None 保守不清）；store seg_map 按 scope（空 = 主轨原路径；非空 = 轨内 segments，轨缺失防御性显式失败）+ 互清精确到「detail.track_id == 本次 track_id」同类型结果 + detail JSON 增键 "timeline_id"（供 P2-4 钉扎）；get 输出逐条附 track_id/track_name（主轨 ""/""，前端据空串判主轨）+ 悬空过滤（轨已删 → 跳过）+ 段解析按 scope（回退 0.0 保留）；accept/reject/accept_high_confidence/clear 四函数零触碰 | R2.2 | 受控改点② |
| P2-4 | core/correction_service.py | accept/reject 超集 patch 化（R2.3，SPEC M2-3）：新增模块级 `_detail_timeline_scope`（存量无 timeline_id 键 → "" 缺省放行；非 JSON/非 dict → None 跳过钉扎不猜归属）；accept 解析后时间轴钉扎（timeline_id 非空且 ≠ active → 「该结果属于其他时间轴，请切换后审阅」零写入）+ 按 detail.track_id 分流——主轨逻辑不变、返回超集 {segment_id, patch: _success_patch(segments+analysis)}（:157 兼容），副轨新路径（轨/段缺失显式失败 → 复用 _assert_timestamps_unchanged + _check_correction_confidence + reattach_words【words=[] 原样空表】→ track.model_copy 整体替换写回 transcript.tracks + 移除结果 → {segment_id, track_id, patch: _success_patch(tracks+analysis)}，bindings 零触碰）；reject 同款钉扎（malformed detail 跳过检查保 v3.0.3 行为）+ 超集 {segment_id, patch: _success_patch(analysis)}；accept_high_confidence/clear/store/get 零触碰 | R2.3 | 受控改点② |
| P2-4 | frontend/src/composables/useWorkspaceActions.ts | handleAccept/handleRejectCorrection 直调桥取回超集 patch：调用前按 scope pushSnapshot（correctionUndoLayers：主轨 [segments,analysis] / 副轨 [tracks,analysis]，条目 track_id 判 scope）→ emit("project-updated", patch) 走 applyProjectPatch，删除 switch_timeline 全量刷新 workaround（清债 #14；无 patch 防御回落）；handleSwitchTimeline 成功分支挂 void loadCorrections 重取钩子；新增 CorrectionReviewEntry/CorrectionReviewResult 类型 + correctionUndoLayers 辅助；deps 接口零字段增删（accept/rejectCorrection 保留接口移出解构） | R2.3 | 登记改点 |
| P2-5 | frontend/src/components/workspace/AIAssistantPanel.vue | M2-4 门控（R2.4）：isTrackMode computed（activeTrackId 非空）+ isFeatureTrackGated（轨模式仅 smart_delete）；selectFeature/switchPanelMode/handleStartSmartDelete 三守卫（置灰态点击不 emit start，非仅样式）；watch isTrackMode 关闭门控功能已开详情；模板智能删除卡 disabled+置灰类+title「仅主轨可用」+小字标签、纠错卡可用+卡底轨徽「当前轨：{track_name}」（主轨不渲染）、工作流 mode-switch 按钮 disabled+title+置灰类；搜索/翻译卡零触碰；props 链零改动（P1-6 交付仅消费） | R2.4 | 登记改点 |
| P2-5 | frontend/src/components/workspace/Timeline.vue | M2-4 精华 tab 门控（R2.4，R3 must-fix #2）：isTabTrackGated（轨模式仅 highlight）+ selectTab 守卫 + watch isTrackMode 变 true 且停留 highlight → 自动回落 suggestion；tab 按钮 disabled + title「仅主轨可用」+ 置灰类（置灰非隐藏，三 tab 布局稳定）+ data-test 锚；建议 tab 不门控；props 链零改动 | R2.4 | 登记改点 |
| P2-5 | frontend/src/composables/useLlmTasks.ts | 仅 startSubtitleCorrection 增第二可选形参 trackId=""，桥调用改四位置参 (referenceText, "", 3, trackId)（P2-2 后端签名；中段保持后端默认；"" = 主轨 v3.0.3 语义不变）；其余零触碰 | R2.4 | 登记改点 |
| P2-5 | frontend/src/pages/WorkspacePage.vue | ① deps 字面量（纠错调用点）startSubtitleCorrection 包装追加 activeListTrackId.value ?? ""（useWorkspaceActions 冻结零改动，轨 id 在本页注入）；② 审阅 modal：correctionTrackName 窄类型 helper（track_name 运行时在场、经本地交叉类型读取）+ 高/低置信度区块来源轨徽「来源轨：{track_name}」（非空显示空不显示）；renderDiff 与时间/文本渲染零改动 | R2.4 | 登记改点 |
| P1-5 | core/config.py | DEFAULTS LLM 区块追加 1 行 `"llm_translation_target_language": "en",`（+注释共 +4）：前端「记忆上次语言」持久化键（R1.1，P1-6 消费） | R1.1 | 只增 |
| P1-5 | main.py | 四 hunk 纯新增 +245 零删改：① 模块级 `_TRANSLATION_LANGUAGES` 常量（9 语言 BCP-47 → 英文显示名，expose 校验与 handler 终替换共用单一事实来源）；② 注册块追加 `register_handler(TaskType.LLM_TRANSLATION, self._handle_translation)`（R1.2）；③ `_handle_translation` 五步流程（R1.2/R1.3）：主轨段源排除 confirmed-deleted → get_effective_prompt("translation") + `{{target_language}}` 英文显示名终替换（残留 `{{` fail-fast）→ analyze_subtitle_translation（失败 raise 零落盘；target_language 传 code，已核实不进 prompt）→ 完成时时间轴钉扎校验（不一致 failed 零落盘带回到原时间轴指引）→ create_translation_track 单 patch 写入 + emit LLM_TRANSLATION_COMPLETED（payload 含 track_id/track_name/language/written_count/target_count/uncovered_ids/ledger，取自 meta.translation 与管线 ledger）+ emit llm:token_usage + 返回含 project dump；④ `@expose start_translation` 六步校验序（R1.5）：LLM configured → project open → 语言合法 → 主轨有 subtitle 段 → 同语言 translation 轨拒绝（文案含「可清空或删除该轨后重试」）→ create_task("llm_translation", {...})；既有函数零触碰 | R1.2/R1.5 | 只增 |
| P2-6 | core/llm_service.py | `_build_structured_user_message` edit_hint 转发块后新增 `aligned_main_text` 段级转发受控增行 +4（注释 1 + 代码 3，s.get 存在则 item["aligned_main_text"]=str(...)，与 edit_hint 同款模式）；analyze_subtitle_correction 签名/批处理管线/其余 builder 逻辑零改动；llm_prompts.py 零改动（字段名自描述，prompt 增强登记 3.0.5 候选） | R2.5 | 只增（受控增行，§4.1 追认——SPEC M0-1 llm_service.py 行「仅新增 analyze_subtitle_translation」为行级滞后，M2-5 明文点名本通路） |
| P2-6 | main.py | `_handle_subtitle_correction` track 分支注入对齐主轨上下文 +10/-1：`main_text_by_id` 主轨文本反查表 + 循环内对有绑定主伙伴（未 confirmed-deleted，被删者上游已 continue）且查得非空文本的副轨段 seg_dict 注入 `aligned_main_text = <主轨段 text>`；无绑定段不注入（自动退化）；主轨 else 分支逐字节不动 | R2.5 | 登记改点（M2-1 track 分支内顺带增强） |
| P3-5 | core/project_service.py | 仅新增 add_range_decision 一个方法（delete_edit_decisions_batch 之后插入，单一 hunk +102/-0）+ 1 行 uuid import：clamp 上界 = media.duration，media 缺失取主轨 subtitle 段 max end（同 generate_subtitle_keep_ranges 口径）且空段先拒（error 逐字「无媒体时长且无字幕段，无法确定范围上界」）；clamp 后 end≤start 拒；action ∈ {delete, keep} 校验；±0.05s 同 action 任意 status 幂等返回既有 edit_id + duplicate=True（无 patch 零写入零 revision bump；跨 action 放行 / 非近似重叠放行，判据同 subtitle_trim 生成侧）；新 edit id=edit-manual-{uuid4().hex[:8]}、status=PENDING（对照 subtitle_trim confirmed-at-creation）、target_type=range、target_id=None、priority=100 → _update_active_timeline → _success_patch(edits)；generate_subtitle_keep_ranges 零触碰（P3-9 受控改点 ①） | R4.1 | 只增 |
| P3-5 | main.py | 仅新 expose add_range_decision(start, end, action="delete", source="manual")（delete_edit_decisions_batch 之后插入，单一 hunk +16/-0）：_mark_dirty 包裹薄透传（形态登记见 record-P3-5 §2.6，同簇 delete_edit_decisions_batch/add_analysis_results 惯例；幂等 duplicate 返回亦 emit PROJECT_DIRTY，service 层仍零写入） | R4.1 | 只增 |
| P3-9 | core/project_service.py | **受控改点 ①**：`generate_subtitle_keep_ranges` 函数体受控改造（R4.4，SPEC M4-4 改动 3 条）+ 模块级抽出合并小函数，共 5 hunk +78/-7（vs dev-3.0.4；逐 hunk 说明见 record-3.0.4-P3-9.md §2）：① 新增模块级私有 `_merge_time_ranges`（+21，原函数内联相邻合并折逐字抽出，相触 `<=` 判据与比较序不变，乱序输入先 sorted 再折）；② 函数 docstring 增 M4-4 段（+8 纯注释）；③ keep_ranges 构建段抽函数复用（-7 内联折 + 调用）+ **keep 集合感知**：构建段后补集前收集 `user_keeps`（action=keep ∧ status=CONFIRMED ∧ target_type=range，**不限 source**），`if user_keeps:` 时 `keep_ranges = _merge_time_ranges([*keep_ranges, *user_keeps])` → keep 区间从删除补集自然扣除（补集段零改动）；④ **陈旧 trim 剔除**：`if user_keeps:` 时移除与任一 user_keep 严格相交（半开区间，相触不算）的既有 `source="subtitle_trim"` delete edit，计数 `invalidated_count` + logger.info 一条含计数（仅 count>0 时输出）；剔除先于 already_covered 扫描（幸存集替换 existing_edits，防陈旧整段被 ±0.05 判据误吸收残余）；手动决策永不触碰；⑤ 返回 data 增键 `invalidated_count`（纯增键，golden 对拍只取三计数键 + edits dump 不受影响）；无用户 keep 工程 `if user_keeps:` 守卫使新逻辑零执行——输出与 v3.0.3 逐字节一致（golden 2 例零改动全绿即判据，基线未重采） | R4.4 | 受控改点① |

## 4. 断言反转白名单登记（R0-3 唯一例外）

| 文件:行 | 反转内容 | 理由 | 登记步 |
|---|---|---|---|
| frontend/src/components/workspace/TranscriptRow.test.ts:270-275（改写后 :271-286） | 原意图「never enters text edit under globalEditMode」断言 `input.edit-text-input` **不存在**（固化 3.0.3 M1-3 副轨豁免）→ 新意图「enters text edit under globalEditMode (track variant)」断言 `input.edit-text-input` **存在**，并补退出扫掠经 `track-text` 批量保存、`update-text` 不触发 ×2 断言（意图与断言同步反转，非削弱；完整 diff 原文见 [record-3.0.4-P3-2.md](./record-3.0.4-P3-2.md) §3） | R3.1 裁决反转（T1 方案 A）：3.0.3 M1-3 豁免经一版使用被用户证伪为「按钮坏了」（US-T1-1）；Q1 裁决编辑态为跨轨全局态 | P3-2 |

后端 `tests/` 断言零删改（反转白名单为空）。

### 4.1 既有测试文件受控增行登记（R0-3 门禁 grep 之外，负责人追认制）

| 文件:位置 | 增行内容 | 性质与理由 | 追认 | 登记步 |
|---|---|---|---|---|
| tests/test_llm_prompts.py EXPECTED_KEYS 集合 | `+ "translation",`（1 行，集合字面量） | 非断言删改（`^-` grep 恒 0）；既有 `test_all_expected_keys_present` 为注册表键集**精确等值**断言，translation 注册后不增该键必红；增行后断言严格性保持且覆盖扩为 6 键，符合「只增不改」精神 | 架构师已追认（P1-2 合并审查） | P1-2 |
| core/llm_service.py:554-557 `_build_structured_user_message` | `+4`：`aligned_main_text` 段级转发（注释 1 + `s.get` 存在则 `item[...] = str(...)`，与 edit_hint 转发同款模式） | 既有函数受控增行（非测试文件，同属门禁 grep 之外的受控改面）：SPEC M0-1 llm_service.py 行写「仅新增 analyze_subtitle_translation 及其私有辅助」，而 SPEC M2-5（R2.5）明文点名 `_build_structured_user_message` 的上下文通路——M0-1 表先于 M2-5 定稿的行级滞后；文件级红线（白名单文件集）不受影响；不复用 edit_hint 通道（系统 prompt 已锚定其语义为「句内口误/重复」，复用会误导模型） | 架构师预裁决（P2-6 委派时） | P2-6 |
| frontend/src/components/waveform/WaveformEditor.vue basic 路径 extension TrackLane `:build-mode` 门控 | `buildMode && !rangeMode` 外延至副轨 lane（产品代码，非测试） | 范围模式 ON 时建段全局暂停（含副轨 lane），消除双 toggle 同 ON 的手势歧义；「副轨 lane 不参与范围标记」语义不变（lane 仍不产生 range，仅建段暂停） | 架构师已追认（P3-6 合并审查） | P3-6 |
| SuggestionPanel→WorkspacePage 时间码接线（P3-7，产品代码选型） | provide/inject 字符串键 `"suggestion:add-range-decision"` 替代 emit 经 Timeline 中转 | SuggestionPanel 实际挂载于 Timeline.vue:775，P3-7 红线禁改 Timeline；provide/inject 使两入口（气泡/时间码）共用同一 handleRangeDecision，SPEC「共用 add_range_decision」字面达成 | 架构师已追认（P3-7 合并审查；类型化 InjectionKey 登记 3.0.5 候选） | P3-7 |

## 5. 超期决策树触发留痕（立项会授权，四要素：日期/触发信号/裁决与影响面/回写文档处）

（无触发则本节记「未触发」）

## 6. 性能对账（P4-2，本版不新建后端 perf 基线——PRD/SPEC 均未立项）

对账口径 = PLAN P4-2 三项：

| # | 对账项 | 判据 | 状态 |
|---|---|---|---|
| ① | M1-4 千段单 patch | `tests/test_translation_track.py::test_revision_exactly_plus_one[1000]`：1000 段一次 create_translation_track，revision 恰好 +1（内存计数与 patch envelope 双证），undo 一次回退整轨 | ✅ 测试固化 |
| ② | M2-3 accept 无 O(project) 全量刷新 | 后端：accept 返回 patch envelope（revision 单调 +1，`tests/test_correction_accept_patch.py`）；前端：`useWorkspaceActions.test.ts` 断言 switch_timeline 零调用、走 applyProjectPatch（switch_timeline workaround 已删除） | ✅ 测试固化 |
| ③ | beta.1 真机千段翻译耗时与 token 观测 | 真机项：入口预估批数（约 N 批）+ `llm:token_usage` 事件复用；**待用户双平台冒烟执行后回填观测值**（清单见 §0 beta.1 节） | ⏳ 待用户冒烟 |

`useRowLayout.perf.test.ts` 环境例维持豁免口径（record-3.0.3 §5 #5），不新设基线；根修登记清债池（3.0.5 候选，维持既有登记）。

## 7. 版本池回写（P4-3：新增 6 项 + 出池 1 项，见 PRD §10.2）

2026-09 P4-3 回填，条目按 PRD §10.2 原文登记：

**新增登记 6 项**：

| # | 项 | 说明（PRD §10.2 原文） |
|---|---|---|
| 1 | T1 方案 B 波形侧编辑模式一致性收口 | 含 trim 冻结语义裁决，3.0.5 候选，与 X1 接线同文件族（Q2 改判不入版） |
| 2 | 2.x 重叠段解交叠载入迁移 | 观察项，触发 = 真实旧工程受阻塞反馈 |
| 3 | 翻译增量补译入口 | ledger.uncovered（M1-2 边界不做增量补译） |
| 4 | `llm:translation_progress` 逐批流式预览 | M1-6 边界不入版（进度走通用 `task:progress` 批粒度） |
| 5 | 定稿译文滑动窗 | 与并发 5 互斥，需串行模式/config 开关——R1.2 Round 2 改判随项；本版裁「并发 + 源文 ±ctx 窗口」，3.0.5 候选 |
| 6 | `accept_high_confidence_corrections` / `clear_subtitle_corrections` 的 track 作用域化 | 本版维持 timeline 级语义——R2.3 边界，Round 2 suggest #13（副轨审阅用逐条 accept/reject） |

**维持原样 7 项（照抄 PRD §10.2）**：桥断连警示 / 点击字幕三模式 / 撤销恢复选区+视图 / 工作区预设（布局随工程走）/ 行设置随工程走 / 二分切片 / 手工 DOM 行保留——其中「需 schema 演进」两项（工作区预设、行设置随工程）**不因红线重启入版**：「只增不改」仍冻结既有模型字段，schema 演进留 3.1.x 专门重启（PRD §6-Q14）。

**出池 1 项**：翻译管线（3.0.1 PRD:54 暂缓项 → 本版 S1 交付，P1 全链）。

### 7.1 §10.1 观察项结论落盘：副轨删除确认策略再评估

结论 = **维持「无确认框 + undo 兜底」默认值**（立项会裁决 ③，2026-09；PLAN「立项会裁决登记」表 #3 / PRD §11 修订-2 ③ / §10.1 观察项同源）。beta.1 起观察误删证据，证据出现再议——本版真机冒烟尚未执行（beta.1/beta.2/beta.3 均登记后置待用户），观察期顺延至用户冒烟（P4-4 双平台真机清单）后起算。

## 8. 遗留清单（P4 归档：本版未尽事项 + 3.0.5 候选登记）

（待回填）

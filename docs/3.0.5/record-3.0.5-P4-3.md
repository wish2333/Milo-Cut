# record-3.0.5-P4-3：R5.11 + R5.15 + R5.16 审阅体验与清理批（序 8 落点）

> 步骤：PLAN P4-3 · 依据：[SPEC M9 顺带表](./spec-v3.0.5.md)（R5.11/R5.15/R5.16 行）· [PLAN](./plan-v3.0.5.md) P4-3 · [PRD](./PRD-v3.0.5.md) R5.11/R5.15/R5.16
> 分支：`dev-3.0.5-P4-3`（已合入已删）· 提交：见 §6

## 0. 序 8 前置确认

P4-3 开发基线 = P4-2 后 `dev-3.0.5`（**已含 P2 的 useWorkspaceActions.ts 改造**——同文件族 + pendingCorrections 消费面前置满足，硬约束核对 ✓）。

## 1. 改动清单

### R5.11（审阅体验三件）

| 文件 | hunk | 内容 |
|---|---|---|
| `WorkspacePage.vue` | :146-161 / :978-985 / modal 模板区 | **审阅 modal 按轨过滤**：`reviewScopeAll` ref（默认 false）+ `scopedCorrections` computed（按 `activeListTrackId ?? ""` 过滤 track_id）；高/低置信度两列表与计数、空态文案全部改绑 scoped；批量条新增「按当前轨 / 全部」分段切换（data-test=review-scope-track/all）；**「全部」= 现状不过滤** 且打通 R5.4 后置的 null 入口——`getReviewScope` 在「全部」态返回 `trackId: null`（三态批量面：快照三层并集/确认文案〈全部轨道〉/后端全轨过滤，P2-2 机制全通后本步接电） |
| `useLlmTasks.ts` | startSubtitleCorrection :360-366 / completed handler :170-184 | **reset 延后**：启动时仅清进度/错误（progress/errorMsg/progressMessage），不再 `resetSubtitleCorrection()` 清列表（「暂无」假象消除）；completed 事件内 `pendingCorrections = []` 权威清场（stored_count>0 由 loadCorrections 整体替换；0 结果运行保留清场防旧结果滞留） |
| `SuggestionPanel.vue` | 时间码 submitTimecode/parseTimecode/takePlayhead + 模板 | **时间码升级**：输入改 text + `parseTimecode` 兼容纯秒（12.5）与 mm:ss.s（1:12.5，正则 `^(?:(\d+):)?(\d+(?:\.\d+)?)$`）；「取播放头」按钮（currentTime prop 预填起值）；提交前 clamp 至时间轴范围（segments 末端）并回显（字段写回落位值）；成功 `toast` emit（新增 emit，经 Timeline 既有 toast 链转发）；错误文案更新两格式提示 |
| `Timeline.vue` | SuggestionPanel 装配 :785-794 | 透传 `:current-time` + `@toast` 转发（Timeline 已有 toast emit 与页面接线，零新链） |

### R5.15（删除/级联 toast）

| 文件 | hunk | 内容 |
|---|---|---|
| `useWorkspaceActions.ts` | handleDeleteTrackSegment :531 / handleDeleteTrack :560-573 | 单段删除 toast →「已删除 1 段，可 Ctrl+Z 撤销」；整轨删除 → 删除前 `getProject()` 读该轨 segments 数 N →「已删除 N 段及其关联数据，可 Ctrl+Z 撤销」（级联附注）；**不加确认框**（record-3.0.4 §7.1 裁决维持） |

### R5.16（perf 例根修）

| 文件 | hunk | 内容 |
|---|---|---|
| `useRowLayout.perf.test.ts` | 全文重写 | **墙钟阈值断言全部移除**（p50×2 + best 3 行），改为确定性断言：窗口数学全滚动扫掠的 clamp/连续/视窗形状不变量（最深 first 覆盖全行空间）+ composable 链单调推进 + WaveformRow 挂载渲染定位面（data-row-index 逐挂校验）；墙钟数字降级为 console 遥测（无断言） |
| `scripts/gates-v3.0.5.sh` | R0-3 前端白名单 | 追认 `useRowLayout.perf.test.ts` 入反转白名单（R5.16 根修移除 3 行墙钟断言，M0-3 追认制，见 §3）；**豁免口径退役**：vitest 判定按全绿（脚本原有双口径分支，全绿路径首次生效） |

## 2. 用例登记（M-gate 前端 R5.11 半边 + R5.15 1 例；净增 +4 + 改写 3）

| # | 用例 | 覆盖 |
|---|---|---|
| F1 | mm:ss.s 解析 | 「1:12.5」→ 72.5 入桥（add_range_decision 第三参直测）+ toast 文案「已添加删除范围 72.5s - 75s」 |
| F2 | 取播放头 | currentTime=72.5 → 起值字段预填 "72.5" |
| F3 | clamp 提交 | extent=100s，end=150 → 桥收到 100（回显等价面：落位值即提交值） |
| F4 | 级联计数（SG2-5） | 轨 3 段 → toast「已删除 3 段及其关联数据，可 Ctrl+Z 撤销」全文断言 + delete_track 桥调用 |
| 改写 | 审阅过滤接线（WorkspacePage.correctionTrack.test.ts badge 例） | 默认主轨态 track 条目被滤出（badge=0）→「全部」切换后原断言面全数恢复（badge=1 + 双侧时间） |

reset 延后无独立断言面（事件时序单测成本 > 收益：completed 清场 + loadCorrections 替换已由改写例间接覆盖主径），登记 §5。

## 3. 断言反转清单（M0-3 追认制）

| 位置 | 原断言 | 新断言 | 依据 |
|---|---|---|---|
| `useRowLayout.perf.test.ts`（3 行） | `expect(p50(samples)).toBeLessThan(1)` ×2 + `expect(best).toBeLessThan(8)` | 移除（确定性不变量断言替代，墙钟降级 console 遥测） | R5.16 裁决「确定性计时/采样次数化断言，移除墙钟阈值」；gates 白名单追认 |
| `WorkspacePage.correctionTrack.test.ts`（badge 例，改写非删除） | modal 打开即见全部条目 | 默认主轨态 track 条目滤出 +「全部」切换后恢复 | R5.11 行为面（默认作用域过滤）；expect 行零删（纯增前置断言 + 交互步骤） |

## 4. 验证（全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  867 passed in 9.14s                        # 本步后端零改动
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  64 passed (64)
  Tests       883 passed (883)               # P4-2 879 → 883（+4）；★★ 全绿——useRowLayout.perf 豁免口径退役，R5.16 根修销账
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（R0-3 前端白名单追认 useRowLayout.perf.test.ts 后形态）
===== 门禁汇总: 全部通过 (exit 0) =====
```

注：门禁首轮曾现 `test_all_batches_failed_still_refuses_zero_write` 单例失败（并行负载下计时抖动），单跑与全量复跑均绿，复跑门禁 exit 0——非本步改动面（本步后端零改动），登记备查。

## 5. 解释登记与未验证边界

- **reset 延后无独立断言**：completed 清场 + loadCorrections 整体替换的时序由 useLlmTasks 事件驱动，单测需模拟 task 事件链；「启动不清列表」的面由改写 badge 例运行路径间接经过。真机手感（运行中旧列表保持可见）随 beta.3 冒烟。
- **clamp 的 extent 口径**：取 segments 末端（主轨字幕范围）而非 media duration——面板 props 无媒体时长且 segments 覆盖实际可用范围；空 segments 时跳过 clamp（无锚点不误伤）。
- **「全部」态与批量按钮**：批量接受/清除在「全部」态走 null 三态（P2-1/P2-2 机制），确认文案〈全部轨道〉、快照三层并集——该面已有 P2 直测（F3 三层并集例），本步只接入口不重复断言。
- **perf 遥测保留**：console.log 三条墙钟数字供人工观测，断言面零环境依赖（M8-3 的性能意图由确定性不变量 + 遥测双轨承接）。
- **审阅过滤的 track_id 口径**：后端 get_subtitle_corrections payload 运行时已带 track_id（P2-2 类型补全），过滤判据 `(track_id ?? "") === activeListTrackId ?? ""`——无 track_id 的旧数据视为主轨，兼容。

## 6. 改动登记表追加

| 步 | 文件 | 改动 | 关联 | 类别 |
|---|---|---|---|---|
| P4-3 | WorkspacePage.vue | reviewScopeAll + scopedCorrections + modal 过滤切换 + getReviewScope null 入口 | R5.11 | 受控 + 只增 |
| P4-3 | useLlmTasks.ts | startSubtitleCorrection reset 延后 + completed 权威清场 | R5.11 | 受控（时序改点） |
| P4-3 | SuggestionPanel.vue + Timeline.vue | parseTimecode/takePlayhead/clamp 回显/toast emit + currentTime 透传 + toast 转发 | R5.11 | 只增 + 输入面改写 |
| P4-3 | useWorkspaceActions.ts | 单段/整轨删除 toast 撤销提示 + 级联计数 | R5.15 | 文案改写 |
| P4-3 | useRowLayout.perf.test.ts + scripts/gates-v3.0.5.sh | 确定性重写（墙钟断言移除）+ R0-3 白名单追认 + 豁免退役 | R5.16 | 根修 + 工具修订 |
| P4-3 | tests（3 文件） | SuggestionPanel +3（时间码族）/ useWorkspaceActions +1（级联计数）/ correctionTrack badge 例改写 | R5.11/R5.15 | 只增 + 追认改写 |

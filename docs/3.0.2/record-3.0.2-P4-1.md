# record-3.0.2-P4-1: 跟随三分（M6-1）

日期：2026-09-02　分支：`dev-3.0.2-p4-1`　合入：`dev-3.0.2`

## 交付范围（PLAN P4-1，SPEC M6-1）

| 三分 | 行为 | 实现落点 |
|---|---|---|
| 播放跟随 | 换行才判定；舒适区内只动播放头；否则跟随到 FOLLOW_BIAS | 编辑器 `watch(currentTime)`（multi only）：`lastFollowedRow` 变化判定 → `isRowVisibleInComfortZone` 免滚 → `followScrollTop(row, vh, rowHeight, max, FOLLOW_BIAS)`，写入前 `noteAutoScroll(target)` 记账 |
| 手动滚动冷却 | 用户滚动后 3s 内跟随静默 | scroll 事件分类：`isTrusted && !consumeAutoScroll(source.scrollTop)` → `markManualScroll()`（`manualFollowUntil = now + 3000`）；跟随判定**先查冷却、且冷却期不推进 lastFollowedRow**（冷却结束后下一个换行即恢复跟随） |
| revealTime 跳转 | REVEAL_BIAS + 舒适区免滚 + 视口内只动播放头 + **跳转后设 3s 冷却** | `useRowLayout.revealTime` 增设 `manualFollowUntil`（实际滚动时才设；舒适区免滚不设） |
| 列表导航统一入口 | 字幕列表 seek → 波形 revealTime | 编辑器 `defineExpose({ revealTime: revealFromNavigation })`（basic 下 no-op）；WorkspacePage `waveformEditorRef` + `handleListSeek` 包住 Timeline 的 `@seek`/`@seek-suggestion` |

## 关键裁决与登记

| # | 事项 | 裁决 |
|---|---|---|
| 1 | 回环判别 `!wasAutoScroll` | 落地为 `autoScrollTarget` 数值匹配（±1px，`consumeAutoScroll`）：跟随写入后第一条 isTrusted 滚动事件若命中目标 = 程序回声（不设冷却），否则 = 真手动。布尔版在 smooth/多事件流下不可靠 |
| 2 | 跟随 smooth | **未启用**（瞬时赋值）：瞬时写 = 单条回声事件，回环分类精确；smooth 的中间事件流需要时间窗抑制配合，移交真机手感评估（M6-1 smooth 括号从宽解释，登记待观察） |
| 3 | 冷却期行号追踪 | 冷却先于换行判定，且冷却期**不推进** lastFollowedRow——冷却一过，下一个时间 tick 即恢复跟随（播放中 ≤ 一个 timeupdate 周期），用户不会停在远离播放行的位置 |
| 4 | basic 分支 | `maybeFollowPlayhead`（200ms 节流出窗居中）原样保留；revealTime/跟随 watch 均 multi-only；revealFromNavigation basic 下 no-op |

## 测试（新增 9 例）

- 内核簿记 4 例（useRowLayout.test，Date-only fake timers）：revealTime 深行设 3s 冷却（2999ms 真 / 3000ms 假）；舒适区 reveal 不滚动不设冷却；markManualScroll 窗口边界（2999/3000）；consumeAutoScroll 命中一次即耗、未命中清目标。
- 编辑器 5 例（WaveformEditor.test，clientHeight 320 桩；视口 320 / stride 130 / 舒适带 rowTop ∈ [64,136] / 跟随目标 r×130−112）：
  - 换行才判定：同行 5→8s 不滚动；换行 25s → scrollTop 148；
  - 回环抑制：跟随写 148 后第一条 trusted 滚动 = 回声 → 不设冷却 → 45s 继续跟随到 408；
  - 冷却窗口：回声后第二条 trusted = 真手动 → 冷却期内 45s 被拦（仍 148）→ advance 3000ms → 65s 跟随到 668；
  - 免滚路径：M5-2 锚点（ctrl+滚轮 spr 5）落位后 row 1 舒适 → 8s 免滚、13s 跟随 148（兼验 M5-2×M6-1 组合）；
  - expose 的 revealTime：REVEAL_BIAS 376 跳转 + 冷却拦截 + 到期恢复 928。

## 测试基建备注

- happy-dom 的 `el.scrollTop` 跨宏任务会被规范化回 0（scrollHeight 恒 0）——跟随测试全部采用**同 tick 断言**（组件写入路径），不直接赋值 DOM scrollTop；「手动滚动」用第二条 trusted 事件构造（autoScrollTarget 已消费 → 必分类为手动），语义等价且不依赖布局引擎。
- fake timers 分档：跟随 describe 全量 fake（Date 驱动冷却 + setTimeout 驱动 M5-1 burst）；簿记 describe 仅 fake Date。

## 门禁（全绿）

pytest 708 ✓ / vitest 632 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

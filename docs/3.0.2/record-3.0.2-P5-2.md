# record-3.0.2-P5-2: 行内副轨 lanes 组合与行高联动（M7-2）

日期：2026-09-02　分支：`dev-3.0.2-p5-2`　合入：`dev-3.0.2`

## 交付范围（PLAN P5-2，SPEC M7-2）

| 需求 | 实现 |
|---|---|
| 每行主 lane + 副轨 lanes | WaveformRow 主区包裹 div（`mainAreaHeight = max(40, rowHeight − Σ副轨高)`，无 tracks 时 = rowHeight−24 与旧几何逐像素等价）；TrackLane v-for 行相对定位（top 从主区底部累计），沿用 LANE_PRESET_HEIGHTS（sm32/md48/lg72）+ LANE_COLLAPSED 24，**无新档位**（评审修正落地） |
| lanes 数约束 | 每行 lanes 数 = 全局非隐藏 tracks 数（同一时间窗全部副轨出现在每个行组） |
| 行高联动 | tracks 出现且 stored rowHeight 仍为默认 120 → 自动切 168（一次性 bump，写透持久化）；**任何非默认持久化值视为用户已改，尊重不覆盖**——派生判定，schema 零增字段；tracks 移除不下调 |
| 副轨行内 trim | updateTime 闭包（trackId 绑定）传入每行 TrackLane，走 M1-1/P05 已激活的乐观链路；组合态由编辑器测试锚定 |
| 折叠/预设共享 | laneState（useLaneLayout state）编辑器级单例传入每行——任一行折叠，全部行 lockstep（测试锚定） |

## 实现说明

- TrackLane 组件**零改动**复用：其注入的 TIMELINE_METRICS_KEY 在行内即行级适配器（viewStart=rowStart），子 lane 块自动按行窗裁剪；行相对 top 由行内 laneItems 计算。
- 编辑器 tracksRef（既有）+ laneCtl（basic 既有单例）复用：折叠/预设/隐藏状态与 basic 栈共享同一持久化（milocut:timeline-layout:v1）。
- 事故记录：联动 watch 初版置于 rowLayout 声明前（immediate 同步执行触发 TDZ）+ 清理误删 trackOverflow——均已修复并由全量测试锚定。

## 测试（新增 3 例，clientHeight 320 桩 / 1 条 md 副轨 / rowHeight 168）

- 每行 1:1 子 lane（visibleRows × tracks），首行 lane height 48px / top 120px（主区 168−48）。
- 行高联动：stored 120 + tracks → select **168**；stored 96（已改）→ 保持 96。
- 折叠 lockstep：任一行 lane-collapse 点击 → 全部行 lane 24px。

## 门禁（全绿）

pytest 708 ✓ / vitest 653 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

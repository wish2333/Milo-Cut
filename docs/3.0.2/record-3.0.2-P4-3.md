# record-3.0.2-P4-3: 迷你总览条（M6-4）

日期：2026-09-02　分支：`dev-3.0.2-p4-3`　合入：`dev-3.0.2`

## 交付范围（PLAN P4-3，SPEC M6-4）

`ScrollbarStrip` 双分支转型：

| 分支 | 模式 | 行为 |
|---|---|---|
| legacy（无 overview prop） | basic | 单窗拇指 + 注入 metrics 拖拽 viewStart——**逐字节零改动** |
| overview（overview prop） | multi | 全片缩略条：覆盖矩形 + 播放头刻线 + 点击/拖拽 seek |

- **覆盖区间新计算**（评审修正落地，不复用单窗 thumbLeft/thumbWidth）：
  - `leftPercent = visibleRows.first × spr / duration × 100`
  - `widthPercent = (last + 1 − first) × spr / duration × 100`（右端 clamp 100）
- **播放头刻线**：`currentTime / duration` 细红线（`overview-playhead`）。
- **点击/拖拽 seek**：strip 内 x 比例 × duration → `overview-seek` 事件 → 编辑器 `handleOverviewSeek` → `rowLayout.revealTime(time)`——**行对齐**（量化到行边界 + REVEAL_BIAS 落位）；拖拽 rAF 节流复用既有模式。
- 编辑器 `overviewGeometry` computed：duration ≤ 0 守卫（全宽占位）。

## 测试（新增 3 例，600px strip 几何桩 + clientHeight 320）

- 覆盖区间与 visibleRows 一致：scrollTop 0 → rows 0..5 → left 0% / width **60%**；播放头 currentTime 25 → `calc(25% - 1px)`。
- 滚动跟随 + 末端钳制：reveal 45s → rows 0..8 → width **90%**；reveal 85s → first 4 / last 9（rowCount 9 钳制）→ left **40%** / width **60%**。
- 跳转行对齐：strip 中点点击（50s）→ revealTime → scrollTop **506**（= 5×130 − 320×0.45，行 5 REVEAL_BIAS 落位）；拖拽 rAF 节流后 80s → **896**（行 8）。

## 已知边界

- 拖拽经 revealTime（REVEAL_BIAS + 舒适区免滚）：指针在小范围内移动时目标行未变则不滚动——SPEC 指定 revealTime 语义的必然行为；真机清单（跟随手感）一并验证。
- 播放头刻线为跟随 `currentTime` 的被动显示（不主动滚动总览窗）。

## 门禁（全绿）

pytest 708 ✓ / vitest 643 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

**Phase 4 三步（P4-1/P4-2/P4-3）至此全部合入**；退出检查剩：手工冒烟（跟随手感 + 总览跳转 + 重开恢复位置）。

# record-3.0.2-P3-3: 多行 trim 接线（M5-4）

日期：2026-09-02　分支：`dev-3.0.2-p3-3`　合入：`dev-3.0.2`

## 交付范围（PLAN P3-3，SPEC M5-4，M8-1 五项验收全覆盖）

| M8-1 验收项 | 测试（WaveformRow.test 新 describe，行 1 = [10s,20s] 映射 600px） |
|---|---|
| trim 越行界不被钳 | 左缘拖到冻结时间 7.67s → raw 9.5s **越过行起点 10s**，乐观更新携带 9.5（不钳 10） |
| 被邻居钳 | 前邻 [9,11]：raw 9.5 落在其跨度内 → 钳到 prevEnd = 11 |
| snap 后二次 clamp | 后邻 start 14.006：raw 14.007 → 钳 14.006 → snap 上取整 14.01 → 二次钳回 **14.006** |
| Alt 反转 | 同位释放 altKey：值保持 12.346 自由网格（对照：无 Alt → 12.35） |
| 拖拽中行回收连续 | mousedown 冻结后 `wrapper.unmount()`，document mousemove 仍按冻结快照换算（9.5 连续输出）——M3-3 骨架的接线验证点闭合 |

## 实现要点

- **冻结源接线**（`WaveformRow`）：
  - 行根 `@mousedown.capture="captureFrozenGeometry"` —— **捕获阶段**先于块的 trim handler 冻结本行 rect+span 进编辑器 `rowDrag` 单例（P2-5 骨架的第二个真实消费者）；行内任意 mousedown（trim/空点）都先冻结。
  - `trimTimeSource = props.getTimeFromPointer ?? frozenTimeFromPointer`：frozen 转换器 = `rowDrag.timeAt(clientX, {bounded:false})` + **clamp[0,duration]**（P4 双映射：行界永不进约束链，S7.8；仅全局 [0,duration]），无捕获回退行适配器 `metrics.getTimeFromX`（拖拽外的散读）。
  - 显式 prop 注入仍优先（块级 M3-2③ 测试与既有消费不受影响）。
- **约束链**（SegmentBlock 既有 `:142-144` 三段式，本步经冻结源验证）：unbounded → `clampTimeToNeighbors`（blocked 拒动）→ `snapToStep`（Alt 反转）→ snap 后二次 clamp → 乐观更新（useSegmentEdit / useTrackEdit 主/副轨既有路径，零改动）。
- **Alt 语义矩阵落地**（M5-4 表）：任意轨道 trim/move = 仅反转 snap；主轨 Alt + 绑定 → 联动照常（联动在 updateTime 链路自动发生，无跳过通道，schema 冻结红线）；副轨 Alt 无特殊语义。**trim-end 占位消费移除**：WaveformEditor basic 分支不再 `emit('toast','裁剪已应用')`——真实链路即 updateTime 乐观路径；trim-end 事件保留在层/行发射面（后续消费者可用）。
- **basic 零改动**：basic 的 SegmentBlocksLayer 从未接收注入（回退 metrics.getTimeFromX 现状语义）；行捕获监听只存在于 multi 行根。

## 测试基建备注

- 行级测试桩：原型 gBCR 补丁（`.waveform-row` = 600px 全宽 / `.rounded.border` 块 = 600px 全宽）→ 左缘条 clientX<16、右缘条 >584；mousedown 走 VTU trigger（捕获阶段真实冒泡），move/up 走 document 原生派发。
- `mountRow` 增 `rowDrag` / `updateTime` 透传；旧断言「无注入时向块传 undefined」按 M5-4 新契约更新为「传行自产冻结转换器」（显式注入优先的断言保留且仍绿）。

## 门禁（全绿）

pytest 708 ✓ / vitest 623 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓（零后端改动）

## 已知边界

- trim 期间 spr 变更（Ctrl+滚轮）会全量重挂行——拖拽闭包经 document 监听 + 冻结快照存活，updateTime 依旧连续（冻结几何跨 spr 语义成立）；真机清单 B 可顺带验证该组合。
- trim-end 的 altKey payload 现无编辑器侧消费者（联动不可跳过是裁决）——字段保留以对齐 v3.0.1 M4-5 事件契约。

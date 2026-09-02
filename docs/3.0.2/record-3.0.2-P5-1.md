# record-3.0.2-P5-1: 底部区高度与控件栏（M7-1）— 进行中（divider/coverage 已合入，R9.4/R9.5 待 P5-1b）

日期：2026-09-02　分支：`dev-3.0.2-p5-1`　合入：`dev-3.0.2`

## 本批合入范围

### 高度 divider（M7-1）

- `editorHeightPx` 走 M6-3 schema（P4-2 已定全字段），**变更即写**（divider 拖拽的每次 mousemove 经 clamp 后直接更新 state → 既有持久化路径落盘）。
- clamp：[20%, 70%] × `window.innerHeight`（`clampEditorHeight`，round 取整）；未设置时默认 **45%**；headless（innerHeight 不可用）回退 320px 下限 120px。
- divider 挂 multi 容器上缘（`viewport-divider`，拖拽向上 = 增高），document 级 move/up 监听（与 P3 手势同款生命周期）。
- **行模型下无 stretch/redraw 需求**（对位 MAW stretchWaveformCanvases 的差异说明）：行高由用户预设决定、与面板高度解耦，divider 只改变可视行数（visibleRows 重算 → 行挂载/卸载）；canvas 位图尺寸不随面板高度变化，无需拖拽期 CSS 拉伸 + 松手重绘。登记为行模型对 M7-1 该子句的替代满足。

### 控件栏完整形态

- 中部覆盖范围标签（`viewport-coverage`）：`formatTimeShort(scrollTopTime)–formatTimeShort(scrollTopTime + 可视行数×spr) / 全片 formatTimeShort(duration)`，末端 clamp 到 duration；替换 beta.1 的行号计数（rowCountLabel 移除）。
- 左「Regen + 模式切换」右「spr + 行高 select」布局维持 beta.1 形态（符合 M7-1 左中右分栏）。

## 测试（新增 2 例）

- 高度 round-trip + clamp 表：480→"480px"（区间内原样）/ 50→"160px"（20% 钳）/ 5000→"560px"（70% 钳）/ 未设置→"360px"（45% 默认，innerHeight 800 桩）。
- divider 拖拽：上拖 80px → 面板 360→440 + `loadRowLayoutState().editorHeightPx = 440`（变更即写验证）。

## 待办（P5-1b，下一轮）

- R9.4 行/块右键菜单 kbd 角标（SegmentBlocksLayer 上下文菜单 + 快捷键注记渲染测试）。
- R9.5 toast 上限 3 条 + 高频冷却参数上调（useToast 既有机制）。

## 门禁（全绿）

pytest 708 ✓ / vitest 645 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

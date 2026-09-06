# record-3.0.2-P5-1: 底部区高度与控件栏（M7-1）

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

## 追加合入（P5-1b，同 record）

### R9.4 右键菜单 kbd 角标

- 块上下文菜单项改 flex 布局 + 右对齐 kbd 角标；**只标注真实存在的快捷键**：「删除」= Del（层 keydown 既有 Delete/Backspace 处理），两个分割项无既有快捷键、不虚造（「菜单即速查表」的诚实实现）。列表行菜单属 v3.0.1 面（零改动红线），本轮不动。

### R9.5 toast 栈策略（useToast 上调参数）

- `MAX_VISIBLE_TOASTS = 3`：超出丢最旧（`slice(-3)`）。
- `TOAST_HIGH_FREQ_COOLDOWN_MS = 500`：同消息在冷却窗内重复 showToast 直接吞掉（高频事件不刷屏）；不同消息不受影响；过期移除逻辑不变。

## 测试（累计 +8）

- 高度 2 例：clamp round-trip 表（480/50→160/5000→560/未设置→360，innerHeight 800 桩）；divider 上拖 80px → 440 且 `editorHeightPx=440` 落盘。
- 菜单角标 1 例：块右键 → Teleport 至 body 的菜单含唯一 kbd「Del」（data-test=menu-kbd-delete），分割项无虚造角标，卸载后菜单清空。
- toast 策略 4 例：上限 3 丢最旧（a..e → c/d/e）；同消息冷却窗内吞掉、过期后放行；不同消息不去重；到期移除。

## 门禁（全绿）

pytest 708 ✓ / vitest 650 ✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓

**P5-1 全部子项完成。**

# Milo-Cut 设计契约（DESIGN.md）

> 版本: v3.0.0 (M9-2 建立) · 依据: PRD C3 / SPEC M9 / 竞品报告 v2（层级丛林教训）
> 适用: 全部业务 `.vue` 组件与全局样式。执行机制见 `frontend/src/utils/styleLint.test.ts`（随 vitest 门禁运行）。

---

## 一、z-index 层级契约

Token 定义：`frontend/src/style.css` `@theme`（`--z-base/raised/dropdown/modal/toast` = 100/200/300/400/500），经 `@utility z-base … z-toast` 暴露为工具类。

### 规则

1. **五档之外无层级**。全局浮层只允许五档 token：
   | token | 数值 | 用途 | 现状示例 |
   |---|---|---|---|
   | `z-base` | 100 | 常驻悬浮徽标 | App demo 徽标 |
   | `z-raised` | 200 | sticky 工具栏 / 组件内交互覆盖层 | Timeline 选择模式横幅、SplitPanel 拖拽热区、波形代理遮罩 |
   | `z-dropdown` | 300 | popover / dropdown / 右键菜单 | 转写/静音/裁剪设置弹层、行右键菜单、波形块右键菜单、TimelineSwitcher 面板 |
   | `z-modal` | 400 | 全屏模态 / 全屏覆盖页 | SettingsModal、确认弹窗、字幕全屏、RelinkMediaDialog、ConflictResolutionView |
   | `z-toast` | 500 | toast / 通知 | ToastContainer |
2. **禁裸魔法数**。业务组件禁用 `z-[N]` 与 Tailwind 数字档（`z-10/20/50` 等）；唯一合法定义点是 style.css 的 token 区。styleLint 测试锁定。
3. **右键菜单单实例互斥**。所有右键菜单经 `utils/contextMenuManager.ts` 的 `openContextMenu(close)` 打开——打开新菜单自动关闭旧菜单（模块级单状态），outside-click / 滚动 / 再右键由管理器统一关闭。禁止组件间全局广播（v2.1.1 的 `closeallcontextmenus` 已于 M9-1 移除）。
4. **上翻方向双测**：任何向上弹出（`bottom-full` / `bottom-0` 定位）的 popover，必须验证"贴着 sticky 工具栏 / 布局分隔条打开"不被遮挡（竞品同坑三次的教训）。当前仓库内 popover 均为向下弹（`top-full`），本规则约束未来新增。

### 豁免：局部堆叠上下文

组件内部自成体系的层叠（如 WaveformEditor 内 `style="z-index: 0/1/2/5/10"` 的波形层叠，容器自身 `relative`）不受五档约束——它们不与全局浮层竞争。判定标准：层叠值是否只在该组件的 `position: relative/absolute` 容器内比较。

## 二、可读性约束

1. **最小字号 11px**（`text-[11px]` 及以上；Tailwind `text-xs` = 12px 可用，`text-[10px]` 禁止）。例外清单：无（如需新增须在本文件登记）。
2. **正文对比度 ≥ AA（4.5:1）**。语义色板已满足：`--color-ink`（#1d1d1f）/`--color-ink-muted`（#86868b，白底 4.54:1）上正文与标签达标；`--color-ink-muted-48`（#6e6e73）仅限辅助说明文字。
3. **例外清单**（显式登记，允许偏离）：
   - 波形块内时间标签（Canvas 绘制）使用 slate 色阶（`utils/waveformTheme.ts`），对比度按图形元素（3:1 图形对比）评估。

## 三、颜色与样式纪律

1. **业务组件禁硬编码 hex**。模板/样式用语义 token（`--color-*` / Tailwind 主题类）；Canvas 绘制色集中到 `utils/waveformTheme.ts`（Canvas 无法读 CSS 类）。styleLint 测试锁定。
2. **原始灰阶/彩阶类（`text-gray-*`、`bg-amber-*` 等）新代码禁用**，统一用语义 token（`text-ink-muted`、`bg-status-*` 等）。存量迁移为机械式大扫除，挂 v3.1 backlog（record-3.0.0-P3-3 登记），本版不强制。
3. **深色磁贴上的浮层用 surface token**（`bg-surface-tile-1` 族），禁止白底硬编码（转写设置弹层历史坑）。

## 四、执行机制

- `frontend/src/utils/styleLint.test.ts`：z-index 与 hex 规则随 `bun run test` 门禁运行，违例即红。
- 新 token/工具类唯一入口：`style.css`；新增档位须同步更新本文件表格与 styleLint 断言。

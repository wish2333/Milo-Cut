# v2.0.1 UI 打磨 -- 实施记录

> **版本**: 2.0.1
> **主题**: UI 打磨 -- Dropdown 修复、AI 助手面板、提示词编辑系统、设置页全屏化
> **基准**: v2.0.0 (待发布)
> **分支**: `dev-2.0.1` (基于 `dev-2.0.0`)
> **规格文档**: `docs/2.0.1/spec-v2.0.1.md`

---

## 概要

v2.0.1 是基于 v2.0.0 的补丁/打磨版本,聚焦 4 个 UI/UX 问题:

1. **Timeline 下拉菜单透明背景** -- TimelineSwitcher 的 dropdown 弹出后背景透明
2. **AI 分析入口不明晰** -- P0/P1/P2/P3 四个 AI 功能组件已开发但未接入工作区 UI
3. **AI 提示词不支持调整** -- 5 个 system prompt 硬编码在 Python 常量中
4. **设置页是弹窗,空间不足** -- SettingsModal 作为 640px Modal 弹窗

---

## Phase 1: Dropdown 修复 + 深色导航栏按钮可见性 (已完成)

### 概要

Phase 1 修复了两个 UI 可见性问题:

1. **DaisyUI 主题变量缺失** -- `appleLight` 自定义主题声明但未定义颜色,导致 `bg-base-100` 等 DaisyUI 语义类渲染为透明,影响 4 个组件
2. **TimelineSwitcher 按钮在深色导航栏不可见** -- 按钮使用 DaisyUI `btn-outline` 类,在 `bg-gray-900` 深色导航栏中几乎不可见

### 根因分析

#### 问题 1: DaisyUI 主题变量缺失

`frontend/src/style.css` 中声明了 `appleLight` 自定义主题:

```css
@plugin "daisyui" {
  themes: appleLight --default;
  prefix: false;
}
```

但**没有为该主题定义任何颜色变量**。DaisyUI 5 要求自定义主题必须通过 `@plugin "daisyui/theme"` 块定义颜色,否则不生成 `--color-base-100` / `--color-base-content` 等语义 CSS 变量,导致 `bg-base-100` / `border-base-300` 等工具类无对应变量,渲染为透明。

受影响组件 (4 个):

| 组件 | 文件:行 | 使用的类 |
|------|---------|---------|
| TimelineSwitcher | `TimelineSwitcher.vue:13` | `bg-base-100 rounded-box border border-base-300` |
| HighlightModeView | `HighlightModeView.vue:200` | `border-base-300 bg-base-100` |
| SemanticSearchBar | `SemanticSearchBar.vue:139` | `border-base-300 bg-base-100 hover:bg-base-200` |
| SubtitleCorrectionReview | `SubtitleCorrectionReview.vue:255` | `border-base-300 bg-base-100` |

> 注: 项目主体 UI 使用 `@theme` 中自定义的颜色 (`--color-canvas`、`--color-ink` 等),不依赖 DaisyUI 语义变量,所以只有 v2.0.0 新增的 AI 功能组件受影响。

#### 问题 2: 深色导航栏按钮不可见

WorkspacePage 顶部导航栏使用 `bg-gray-900` 深色背景 (`WorkspacePage.vue:1042`),周围元素均用 `text-gray-400 hover:text-white` 适配深色背景。但 TimelineSwitcher 的按钮触发器使用 DaisyUI `btn btn-sm btn-outline` 类,该类在深色背景上渲染为灰色描边 + 灰色文字,几乎不可见。

### 变更文件 (共 3 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/style.css` | 修改 (+19 行) | 新增 `@plugin "daisyui/theme"` 块,为 appleLight 主题定义 4 个语义颜色变量 (base-100/200/300/content) + border radius 变量 |
| `frontend/src/components/workspace/TimelineSwitcher.vue` | 修改 (1 行) | 按钮触发器从 `btn btn-sm btn-outline` 改为显式深色适配类 (`text-gray-300 hover:text-white hover:bg-white/10`) |
| `docs/2.0.1/spec-v2.0.1.md` | 修改 (+472/-60 行) | 审计修正 + 附录 A/B + 4 点审计反馈固化 |

### 架构决策

#### 颜色映射 -- 与现有 @theme 保持视觉一致

DaisyUI 语义变量映射到现有 `@theme` 自定义颜色,确保 `bg-base-100` 等同于 `bg-canvas`:

| DaisyUI 变量 | oklch 值 | 等效 Hex | 对应 @theme |
|---|---|---|---|
| `--color-base-100` | `oklch(100% 0 0)` | #ffffff | `--color-canvas` |
| `--color-base-200` | `oklch(97.1% 0.0027 286.4)` | #f5f5f7 | `--color-parchment` |
| `--color-base-300` | `oklch(86.5% 0.0068 286.3)` | #d2d2d7 | `--color-hairline` |
| `--color-base-content` | `oklch(23.2% 0.0038 286.1)` | #1d1d1f | `--color-ink` |

oklch 值通过 sRGB → linear → OKLab → OKLCH 精确转换,与原 Hex 视觉等效。

#### 色彩空间 -- 选择 oklch 而非 Hex

DaisyUI 5 + Tailwind v4 强烈推荐 `oklch()` 色彩空间。虽然 Hex 也兼容,但 `oklch` 在 Tailwind v4 中的透明度修饰符 (如 `bg-base-100/50`) 解析行为最稳定。

#### TimelineSwitcher 按钮样式 -- 显式类替代 DaisyUI btn-outline

放弃 `btn-outline` (依赖 DaisyUI 默认配色),改用与导航栏周围元素一致的显式类: `text-gray-300 hover:text-white hover:bg-white/10 transition-colors`。这保证了在 `bg-gray-900` 深色导航栏中的可见性,与相邻的返回按钮、项目名等信息保持风格统一。

### 测试覆盖

| 验证项 | 结果 |
|--------|------|
| `bun run build` (前端构建) | 通过 -- DaisyUI 5.5.19 正确解析主题,CSS 106.14 kB |
| 生成 CSS 包含 `--color-base-100` | 确认 -- `oklch(100% 0 0)` 变量已生成 |
| `bun run test` (147 测试) | 全部通过 -- 含 TimelineSwitcher.test.ts、HighlightModeView.test.ts |

### spec 文档审计修正

同步修正了 spec 文档中与代码现状的偏差:

- **背景陈述 #2/#3**: 精确化孤立组件详情 (3 个组件 + 1 个 composable)、prompt 数量 (4 → 5)
- **Phase 1**: 根因已确认 + Tailwind 4 无 JS 配置文件说明 + 受影响组件 5 → 4
- **Phase 2**: 每个文件增加现状说明 (孤立状态/未导入/无引用)、source 值交叉验证、progress ref 名修正、v-show 状态保持建议
- **Phase 3**: analyze_* 函数实际签名 + prompt 常量精确行号 + 调用链 + _format_param strip + 浅拷贝合并注释
- **Phase 4**: SettingsModal 当前结构快照 + ESC 快捷键 + Transition 过渡动画
- **附录 A**: Phase 1 根因分析 (现状/根因/受影响组件/为何主体 UI 未暴露/Tailwind 4 说明)
- **附录 B**: 当前代码架构快照 (后端 LLM 架构/前端架构/Event 同步/SettingsModal 结构)

# Milo-Cut v2.4.0 UI 设计标准

> **适用范围**：Vue 3 + Tailwind CSS 4 + DaisyUI 5 前端  
> **设计目标**：专业、安静、可扫描、以视频和字幕为中心  
> **继承规范**：`docs/design-spec.md` 的 Apple Edition

## 1. 核心原则

1. **内容优先**：视频画面、字幕文本、波形是内容，UI 只负责组织和解释。
2. **单一强调色**：Action Blue 用于主操作、链接、当前项和键盘焦点。
3. **背景分层而非边框堆叠**：优先通过 Canvas、Parchment、Video Surface 区分区域。
4. **状态色只表达语义**：Pending、Delete、Keep 不得用于普通按钮层级。
5. **稳定的视觉节奏**：统一间距、字体、圆角和控件高度，避免逐组件临时设计。
6. **每个操作都可解释**：危险操作需要明确文案；后台任务需要进度或状态反馈。

## 2. 颜色 Token

| Token | 值 | 用途 |
|---|---|---|
| `--color-canvas` | `#FFFFFF` | 主内容、字幕画布 |
| `--color-parchment` | `#F5F5F7` | 面板、辅助区域、空状态 |
| `--color-ink` | `#1D1D1F` | 主文字 |
| `--color-ink-muted` | `#6E6E73` | 次要文字、时间戳 |
| `--color-hairline` | `#D2D2D7` | 极细分隔线 |
| `--color-surface-tile-1` | `#272729` | 视频区域、深色控制区 |
| `--color-primary` | `#0066CC` | 主操作、链接、选中、focus |
| `--color-status-pending` | `#FFF9E6` | 待确认 |
| `--color-status-confirmed` | `#FEF2F2` | 确认删除 |
| `--color-status-rejected` | `#F0FDF4` | 保留/忽略删除 |
| `--color-status-warning` | `#DC2626` | 高风险警告和危险操作 |

禁止在业务组件中新增 `green-*`、`purple-*`、`indigo-*` 作为主按钮色；如确有新语义，先增加 token，再使用语义类名。

## 3. 字体与类型

优先字体栈：

```css
"-apple-system", BlinkMacSystemFont, "SF Pro Text", "PingFang SC", system-ui, sans-serif
```

| 层级 | 规格 | 用途 |
|---|---|---|
| Display | 32–40px / 600 / 1.1 | Welcome 标题、页面主标题 |
| Heading | 20–24px / 600 / 1.25 | 区域标题、导出摘要 |
| Body | 16–17px / 400 / 1.47 | 字幕正文、主要说明 |
| Control | 13–14px / 400 或 600 | 按钮、菜单、输入框 |
| Caption | 12–13px / 400 | 时间戳、状态辅助信息 |
| Mono | 12–13px / 400 | 时间码、技术参数 |

业务组件不使用 500 字重。中文和英文文案统一由产品语言决定，不能在 loading 或按钮中混用。

## 4. 间距、尺寸与圆角

### 4.1 间距

基础间距只使用：`4 / 8 / 12 / 16 / 24 / 32 / 48` px。

### 4.2 控件高度

- 紧凑工具栏：28–32px
- 普通按钮和输入框：36px
- 主操作按钮：40–44px
- 顶部导航：44–48px

### 4.3 圆角

| Token | 值 | 用途 |
|---|---:|---|
| `--radius-control` | 6px | 输入框、普通按钮、菜单 |
| `--radius-panel` | 10–12px | 独立面板或弹窗 |
| `--radius-pill` | 9999px | 主按钮、状态胶囊 |
| `--radius-none` | 0 | Workspace 大区、字幕行、波形区 |

默认不使用装饰性阴影。只有视频画面、弹窗和悬浮菜单可以使用阴影。

## 5. 页面标准

### 5.1 WelcomePage

- 页面背景使用 Canvas。
- 标题和副标题左对齐或保持稳定的居中块，不使用额外装饰图形。
- 拖拽导入区域是唯一主视觉焦点，支持 hover、dragover、disabled、loading、error 五种状态。
- 最近项目使用无阴影列表，项目名为主信息，路径和更新时间为辅助信息。
- 设置按钮必须有中文 `aria-label` 和 `focus-visible`。

### 5.2 WorkspacePage

```text
Top chrome: project / stage / undo-redo / export
Main:      video surface | transcript canvas
Bottom:    waveform timeline
Optional:  suggestion panel / drawer
```

- 视频区使用 `surface-tile-1`，字幕区使用 Canvas，分析面板使用 Parchment。
- 不给整个字幕区叠加多层 `border + rounded`。
- 字幕行最小高度建议 52px，时间码与正文垂直居中。
- 当前播放行使用左侧 Action Blue 标记；选中行使用浅蓝背景；编辑中使用细蓝色 outline。
- 删除/保留状态使用浅色背景，不改变正文可读性。
- 波形中的静音区域使用半透明状态色，不能遮挡播放头和可拖拽边界。

### 5.3 ExportPage

- 预览区占据主要面积。
- 左侧使用可折叠设置组，右侧显示导出摘要和操作。
- 只允许一个 primary action；其他格式使用 secondary 或 text action。
- 导出摘要必须展示最终时长、删除时长、删除比例和输出格式。
- 删除比例超过 40% 时才升级为危险警告，不应让普通导出操作一直显示红色。

## 6. 组件状态标准

所有按钮、输入框、可选行和拖拽区域至少覆盖：

```text
default -> hover -> active -> focus-visible -> disabled
```

异步组件额外覆盖：

```text
idle -> loading -> success / error
```

空内容组件额外覆盖：

```text
empty -> first action -> populated
```

焦点标准：

```css
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
```

不以颜色作为唯一状态通道；删除、待确认、保留等状态应同时具备文字或结构提示。

## 7. 文案标准

优先使用短中文动作：`导出视频`、`返回编辑`、`正在生成代理视频…`、`暂无分析建议`、`重新尝试`。

错误提示应包含“发生了什么 + 用户可以做什么”，例如：

```text
无法读取视频信息。请检查文件路径，或重新选择视频。
```

Tooltip、`title`、`aria-label` 和可见按钮文案必须保持同一语言。

## 8. 可访问性与验证

- 正文与背景达到 WCAG AA 对比度；浅灰文字不用于关键操作。
- 所有图标按钮必须有 `aria-label` 或可读文本。
- 键盘可完成导入、搜索、播放/暂停、删除标记、撤销/重做和导出。
- 遵守 `prefers-reduced-motion`；页面过渡不影响核心操作。
- 前端构建、单元测试和手动工作流验证必须全部通过。


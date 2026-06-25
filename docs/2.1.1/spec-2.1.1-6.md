# Milo-Cut Component Specification

基于 design-spec.md 的设计系统，本文档定义核心页面的布局结构和关键组件的交互细节。

**v2.1.1 UI/UX 优化修订** — 侧边栏从浮动覆盖改为内联同平面布局；字幕行时间编辑重构；全局视觉精炼。

---

## 1. 工作区页面布局 (Workspace Layout)

"博物馆展厅"模式：上方沉浸式视频区，右侧文档式编辑器。

```text
+-----------------------------------------------------------------------+
|  MILO-CUT    [1 导入] -- (2 转写) -- (3 分析) -- (4 编辑) -- [5 导出]  | <- Global Nav (44px)
+---------------------------+-------------------------------------------+
|                           |  TIMELINE TOOLBAR          | SIDEBAR HEAD | <- 分区标题栏
|      VIDEO PLAYER         |  [编辑][搜索][选择] count  | [建议][AI][精华] [<]
|    (Surface Tile 1)       |----------------------------+--------------|
|                           |  TRANSCRIPT EDITOR         |              |
|      [  Video Area  ]     |  00:12 [大家好...] Pending |  Suggestion  |
|      (Product Shadow)     |  00:16 [--- 静音 1.5s ---]|  Panel /     |
|                           |  00:18 [这个功能...] Error |  AI Assistant|
|      [ > ] 00:15 / 05:00  |  00:22 [重点是...]  Saved  |  / Highlight |
|                           |  (flex-1, independent      |  (384px,     |
|                           |   vertical scroll)         |   independent|
|                           |                            |   scroll)    |
+---------------------------+----------------------------+--------------+
|  WAVEFORM VIEW (16kHz)    [ Regen ] [00.0s ━ 120.0s window ━ 130.0s]  | <- 波形工具栏(增强)
|  +---------------------+                                              |
|  | /\_/\__/\_/\_/\_/\ |                                              |
|  +---------------------+                                              |
+----------------------------------------------------------------------+
```

### 核心变更：侧边栏内联化

侧边栏不再是 `<Teleport to="body">` + `fixed` 定位的浮动覆盖层。改为 Timeline 内部的 flex 兄弟元素，与字幕列表在同一平面上，共享同一高度范围。

**空间来源**：侧边栏展开时挤压字幕列表宽度（字幕列表用 `flex-1 min-w-0` 自适应收缩），视频区域宽度完全不受影响。

### 尺寸比例

| 区域 | 宽度 | 说明 |
|------|------|------|
| 左栏（视频+波形） | SplitPanel ratio * 100% | 默认 40%，拖拽可调，持久化 |
| 右栏外框（Timeline 容器） | (1-ratio) * 100% | 默认 60% |
| ├─ 字幕列表 | `flex-1 min-w-0` | 侧边栏展开时自动收缩 |
| ├─ 分隔条 | 1px + 透明 hit area | 与 SplitPanel 视觉一致 |
| └─ 侧边栏 | `sidebarWidth` px | 默认 384px，左边缘拖拽调整，持久化 |
| 波形编辑器 | 固定 ~124px | h-6 控制栏 + h-28 画布 |

---

## 2. 侧边栏详细规范 (Inline Sidebar)

### 2.1 布局结构

侧边栏作为 Timeline 内部 `relative flex flex-1 overflow-hidden` 容器的第三个 flex 子元素（字幕列表 + 收起箭头 + 侧边栏）。

```
Timeline 根容器 (flex flex-col h-full)
├─ 标题栏 (flex items-center justify-between border-b) — 分区模式
│   ├─ 左侧: Timeline 标题 + 工具按钮组（选择模式、搜索、编辑字幕、统计）
│   └─ 右侧: 侧边栏 Tab 按钮（建议/AI助手/精华）+ 收起箭头 [<]
├─ 内容区 (relative flex flex-1 overflow-hidden)
│   ├─ 字幕列表 (flex-1 min-w-0 overflow-y-auto)
│   ├─ 分隔条 (w-px, 与 SplitPanel 一致的 1px 灰线 + 透明 hit area)
│   └─ 侧边栏 (flex flex-col, width: sidebarWidth px)
│       ├─ Tab 内容区 (flex-1 overflow-y-auto p-2)
│       └─ 无独立标题栏（标题栏在上层分区中）
```

### 2.2 状态管理

| 属性 | 默认值 | 持久化 | 说明 |
|------|--------|--------|------|
| `sidebarOpen` | `true` | 否（每次打开项目默认展开） | 不记忆收起状态 |
| `sidebarWidth` | `384` | 是（localStorage `milo-sidebar-width`） | 左边缘拖拽调整 |
| `activeTab` | `"suggestion"` | 否 | Tab 切换状态 |

**宽度约束**：最小 `320px`，最大 `window.innerWidth * 0.85`。窗口 resize 时自动 clamp。

### 2.3 收起/展开交互

**收起后空间分配**：侧边栏完全移除（`v-if="false"`），字幕列表 `flex-1` 自动填满全部宽度。标题栏右侧只保留一个小箭头按钮 `[>]`。

**动画**：宽度过渡（CSS `transition: width 200ms ease-out`）。展开时从 `0` 过渡到 `sidebarWidth`；收起时反向。字幕列表同步平滑收缩/扩展。注意：因为使用 `v-if`，需要在 leave 过渡完成后再移除 DOM（使用 Vue `<Transition>` 的 JavaScript hooks 或 `transition: width` + 延迟 `v-if`）。

**收起按钮位置**：标题栏最右侧，与 Tab 按钮在同一行。图标为 `<` （展开时）或 `>` （收起时）。

### 2.4 标题栏分区

标题栏从单行横贯改为左右分区：

| 区域 | 内容 | 宽度策略 |
|------|------|---------|
| 左侧 | Timeline 标题 + "选择模式" / "搜索" / "编辑字幕" 按钮 + 段落统计 | `flex-1 min-w-0`（可收缩） |
| 右侧 | 侧边栏 Tab 按钮（建议/AI助手/精华）+ 收起箭头 | `flex-shrink-0` |

侧边栏收起时，右侧区域只显示 `[>]` 箭头按钮。

### 2.5 分隔条

侧边栏与字幕列表之间的分隔条采用与 SplitPanel 一致的视觉规范：
- 宽度：`w-px`（1px 可见线）
- 颜色：`bg-gray-200`（默认），`hover:bg-blue-400`（悬停）
- 透明 hit area：左右各延伸 `6px`（`-left-1.5 -right-1.5 z-10`）
- 光标：`cursor-ew-resize`
- 交互：保持现有 `onSidebarResizeStart` 的 mousedown 拖拽逻辑

### 2.6 竖向滚动

侧边栏 Tab 内容区与字幕列表**各自独立竖向滚动**（`overflow-y-auto`）。点击建议项时通过 `handleSuggestionSeek` 触发字幕列表 `scrollIntoView`（已有逻辑保留）。

### 2.7 移除的元素

以下浮动版特有的元素在内联版中移除：
- `<Teleport to="body">` 包裹
- `fixed top-0 bottom-0 right-0` 定位
- `shadow-2xl` 阴影（内联面板用分隔线而非阴影区分）
- `z-40` 层叠上下文（不需要覆盖）
- 右上角独立 hamburger 汉堡按钮（改由标题栏箭头替代）

---

## 3. 核心组件细节规范

### 3.1 字幕行组件 (TranscriptRow)

字体：`{typography.body}` (17px / 400 / -0.374px)

**状态与视觉映射：**

| 状态 | 背景 | 文字样式 | 左边条 |
|------|------|---------|--------|
| 常规 | `{colors.canvas}` (#ffffff) | 正常 | 无 |
| Pending | `{colors.status-pending}` (#fff9e6) | 正常 | 3px 黄色竖线 |
| Confirmed | `{colors.status-confirmed}` (#fef2f2) | 中划线 + 降低透明度 | 3px 红色竖线 |
| Rejected | `{colors.status-rejected}` (#f0fdf4) | 正常 | 3px 绿色竖线 |
| 交叉验证高亮 | `{colors.canvas}` | 正常 | 3px Action Blue 竖线 |
| 选中/聚焦 | `{colors.canvas}` + 1px Action Blue 描边 | 正常 | 无 |

#### 3.1.1 时间列重构（v2.1.1 修复）

**问题**：原 `w-[150px] shrink-0` 时间列在编辑模式下渲染 `[−][input 55px][+]` 控件组（~95px），加上箭头分隔符和另一个非编辑时间戳（~60px），总宽度超过 150px，导致内容溢出换行，破坏行排版。

**修复方案**：原地替换编辑，去掉 ± 按钮。

```
显示模式:  [00:12.3 → 00:18.5]         <- span, 150px 固定
编辑模式:  [00:12.3 → 00:18.5]         <- input 替换对应 span，宽度与 span 一致
                ^ 点击 start 变成 input
```

- 点击时间戳 → 该时间戳变为 `<input>`，**input 宽度与原 `<span>` 显示宽度一致**（约 60px，用 `w-[60px]` 或与 span 相同的固定宽度）
- **去掉 `−` 和 `+` 按钮**，不再渲染额外的按钮元素
- 时间列始终保持 `w-[150px] shrink-0`，编辑和不编辑时占用的宽度完全相同
- **零布局偏移**：input 和 span 使用相同的 font-mono、font-size、padding，确保切换时无视觉跳动

**键盘微调（保留并明确）**：
input 聚焦时的键盘交互（`handleTimeEditKeydown` 已实现，保留不变）：
- `Enter` → 确认编辑
- `Escape` → 取消编辑
- `ArrowUp` → +0.1s（Shift = +1.0s）
- `ArrowDown` → -0.1s（Shift = -1.0s）
- 直接输入数字 → 手动输入时间值

> **注意**：ArrowUp/Down 在此上下文（时间编辑 input 聚焦）中是微调时间；在字幕列表浏览上下文中是上下移动选中行。两个上下文不冲突，因为 input 聚焦时键盘事件被 input 捕获。

**交互（保留不变）：**
- 点击行 -> 视频跳转到对应时间点
- `Delete` -> 标记为 Pending（若已是 Pending 则升级为 Confirmed）
- `Space` -> 从该行时间点开始预览播放
- `Ctrl+Z` -> 撤销状态变更

### 3.2 静音隔离条 (SilenceSegment)

- 背景：`{colors.canvas-parchment}` (#f5f5f7)，高度 32px
- 标注：居中显示 `{typography.caption}` 字体的"静音 N.Ns"
- 左右边缘：可拖拽 resize 手柄（4px 宽，hover 时显示 Action Blue）
- 拖拽调整时，相邻字幕行的起止时间实时同步更新
- 调整结果即时写入 `project.json` 的 `edits` 数组

**静音段状态映射（保留不变）：**

| 状态 | 背景 | 标注文字 |
|------|------|---------|
| 默认 | `{colors.silence-bg}` (#f5f5f7) | "静音 N.Ns" 灰色 |
| 建议删除 | `{colors.status-pending}` (#fff9e6) | "静音 N.Ns [建议删除]" 黄色 |
| 已确认删除 | `{colors.status-confirmed}` (#fef2f2) | "静音 N.Ns [已确认]" 红色 |
| 已保留 | `{colors.status-rejected}` (#f0fdf4) | "静音 N.Ns [已保留]" 绿色 |

### 3.3 建议面板卡片 (SuggestionPanel)

- 容器：圆角 `{rounded.lg}` (18px)，边框 `{colors.hairline}` (#d2d2d7)
- 统计区：`{typography.body-strong}` 显示各类发现数量
- 按类型分组显示，每组可展开/折叠

**分组结构（保留不变）：**

```
SUGGESTION PANEL
+-------------------------------------------+
|  发现 3 处静音 | 5 处口头禅 | 1 处口误      |
+-------------------------------------------+
|  v 静音段 (3)                              |
|    [静音 2.3s] 00:16 - 00:18   [确认][忽略] |
|    [静音 1.5s] 00:45 - 00:47   [确认][忽略] |
|    [静音 4.1s] 01:23 - 01:27   [确认][忽略] |
+-------------------------------------------+
|  > 口头禅 (5)                              |
|  > 口误触发 (1)                            |
+-------------------------------------------+
|  [全部确认删除]            [忽略所有建议]     |
+-------------------------------------------+
```

### 3.4 视频预览区 (VideoPlayer)

- 背景：`{colors.surface-tile-1}` (#272729)，视频黑边与 UI 融合
- 视频窗口投影：`3px 5px 30px`，浮动在展厅表面
- 底部控制栏：播放/暂停、时间进度、`Shift+Space` 切换原片/剪后
- 字幕叠加：底部白色 SF Pro Display，跟随当前时间

**对比预览模式 (Shift+Space)（保留不变）：**

| 模式 | 显示内容 | 时间轴行为 |
|------|---------|-----------|
| 原片模式 | 完整原始视频 | 正常播放，显示所有段 |
| 剪后模式 | 跳过 Confirmed 删除段 | 播放时自动跳过已确认删除的时间段，进度条显示缺口 |

### 3.5 波形视图 (WaveformView)

- 紧凑型，位于视频播放器正下方
- 高度：64px（固定）
- 静音段区域：半透明色块覆盖
- 字幕段边界：竖线标记 + 时间戳
- Confirmed 删除段：红色半透明覆盖
- 交互：点击跳转、拖拽选区、鼠标滚轮缩放时间范围

#### 3.5.1 波形工具栏增强（v2.1.1 待定）

当前工具栏仅包含：`Regen` 按钮 + 视窗开始时间 + 窗口时长 + 视窗结束时间。有效信息密度过低。

**待定增强项**（完整审阅后最终决定）：
- 缩放控件按钮（放大/缩小/适应窗口）— 作为滚轮缩放的显式替代
- 播放头精确时间显示
- 视窗内段落统计
- 波形显示选项切换

> 此区域在完成侧边栏重构和全局视觉精炼后，结合实际使用体验再做最终决定。

### 3.6 步骤控制器 (StepController)

嵌入 Global Nav 居中位置（保留不变）：

```
[1 导入] -- (2 转写) -- (3 分析) -- (4 编辑) -- [5 导出]
  ^完成      ^当前       ^未达       ^未达       ^未达
  蓝色勾     Action      灰色        灰色        灰色
             Blue高亮
```

- 已完成步骤：Action Blue 勾选图标 + 可点击回退
- 当前步骤：Action Blue 高亮，文字加粗 600
- 未达步骤：灰色文字，不可点击
- MVP 中"转写"步骤更名为"导入字幕"

---

## 4. 导出摘要弹窗 (Export Summary Modal)

导出前强制弹出的安全检查，Apple 风格居中模态框。
"大数字"视觉冲击力 + 三道保险逻辑，确保用户对修改一目了然。

```text
+-------------------------------------------------------------+
|                                                             |
|                   导出汇总摘要 (Export Summary)              | <- display-md
|                                                             |
|       +---------------------------------------------+       |
|       |                                             |       |
|       |      40:12            -19:48        33%     |       | <- hero-display (56px/600)
|       |    预计时长          裁剪掉时长      占比     |       | <- caption (14px/400)
|       |                                             |       |
|       +---------------------------------------------+       |
|                                                             |
|    检测到以下异常情况 (Safety Checks):                        | <- body-strong
|    +---------------------------------------------------+    |
|    | [!] 存在 1 段超过 60s 的删除段 (建议检查)           |    | <- status-pending bg
|    | [!] 连续删除超过 3 段内容                          |    |
|    +---------------------------------------------------+    |
|                                                             |
|    导出模式:                                                |
|    [精确模式 (推荐)]  [快速模式]                              | <- pill toggle
|                                                             |
|      [      确认导出 (Proceed)      ]                       | <- button-primary (Action Blue pill, 80% width)
|                                                             |
|      [      返回检查 (Review)       ]                       | <- button-secondary (Action Blue text + border)
|                                                             |
+-------------------------------------------------------------+
```

**触发规则（保留不变）：**
- 删除段总时长超过原视频 40% -> 占比数字变警告红 + 额外显示总量警告
- 单段删除超过 60 秒 -> Safety Checks 区显示长片段警告
- 连续删除超过 3 段 -> Safety Checks 区显示连续性警告

**Hero Statistics 颜色逻辑（保留不变）：**

| 数据 | 正常态 | 警告态 |
|------|--------|--------|
| 预计时长 | Action Blue (#0066cc) | Action Blue |
| 裁剪时长 | `{colors.ink-muted-48}` 灰色 | 灰色 |
| 占比 | Action Blue | 警告红 (#dc2626)，超过 40% 触发 |

**导出模式切换（保留不变）：**

| 模式 | 样式 | 说明 |
|------|------|------|
| 精确模式（推荐） | Action Blue pill + "推荐"标签 | 帧级精度，重新编码 |
| 快速模式 | 黑色边框 pill | 关键帧精度，-c copy，UI 提示切点可能偏移 |

---

## 5. 响应式布局

| 视口宽度 | 布局调整 |
|---------|---------|
| Desktop (>1440px) | 左右双栏，编辑器占 60%，两侧留白 |
| Laptop (1024-1440px) | 左右双栏，分隔条可拖拽，无留白 |
| Tablet (<1024px) | 上下结构，视频固定顶部，编辑器下方滚动 |
| Narrow (<834px) | 步骤条简化为图标，侧边栏默认收起 |

---

## 6. 全局视觉精炼规范 (v2.1.1 Deep Refinement)

在不改变现有功能的前提下，对以下四个维度进行深度优化，使整体视觉语言更统一、更贴近 Apple Edition 设计目标。

### 6.1 间距 / 边框 / 圆角节奏统一

**目标**：消除各区域间不一致的 padding、margin、border、border-radius 值，建立可预测的间距节奏。

| 层级 | 统一规范 | 适用区域 |
|------|---------|---------|
| 区域间距 | 区域之间用 1px `border-gray-200` 分隔，不用 gap 留白 | Nav ↔ Toolbar ↔ Content ↔ Waveform |
| 内边距 | 水平 `px-4`，垂直 `py-2` 为基准节奏 | Nav, Toolbar, 标题栏 |
| 紧凑内边距 | 水平 `px-3`，垂直 `py-2` | TranscriptRow, SilenceRow |
| 圆角 | 按钮统一 `rounded-md`（6px），卡片 `rounded-lg`（8px），行内标签 `rounded`（4px） | 全局 |
| 边框颜色 | 统一使用 `border-gray-200` 作为分隔线，`border-gray-300` 作为输入框边框 | 全局 |

**审查清单**：
- Nav、Toolbar、Timeline 标题栏、波形工具栏的 border-b 是否一致
- 各按钮的 rounded 值是否统一（当前混用 rounded / rounded-md）
- px-3 / px-4 是否在同类区域一致

### 6.2 按钮层级和交互反馈

**目标**：建立清晰的按钮视觉层级，统一 hover/active/disabled 反馈。

| 层级 | 样式 | 用途 | 示例 |
|------|------|------|------|
| Primary | `bg-blue-500 text-white hover:bg-blue-600 active:scale-95` | 主要操作 | Import SRT, 确认导出 |
| Secondary | `bg-gray-100 text-gray-700 hover:bg-gray-200` | 次要操作 | 编辑, 取消, 保留 |
| Toggle Active | `bg-blue-100 text-blue-700` | 激活状态 | 选择模式开, 搜索开 |
| Toggle Inactive | `text-gray-500 hover:bg-gray-100` | 未激活状态 | 选择模式关 |
| Danger | `bg-red-100 text-red-700 hover:bg-red-200` | 危险/删除 | 已删除标签 |
| Ghost | `text-gray-400 hover:text-white`（深色背景） | 导航栏次要 | Save, Back |

**交互反馈统一**：
- 所有可点击元素 `transition-colors duration-150`
- 按下反馈：Primary/Secondary 用 `active:scale-95`（100ms）
- 禁用状态：`disabled:opacity-50 disabled:cursor-not-allowed`

### 6.3 配色和明暗过渡

**目标**：优化暗色区域（Nav `bg-gray-900`、视频区 `bg-gray-900`）与亮色区域（Toolbar `bg-gray-50`、Timeline `bg-white`）之间的视觉过渡。

| 区域 | 背景 | 文字 | 过渡策略 |
|------|------|------|---------|
| Global Nav | `bg-gray-900` | `text-white` / `text-gray-400` | 硬边界（border-b） |
| Toolbar | `bg-gray-50` | `text-gray-700` / `text-gray-500` | 硬边界（border-b） |
| Timeline 容器 | `bg-white` | `text-gray-900` / `text-gray-500` | 圆角边框包裹 |
| TranscriptRow | `bg-white`（常规）| `text-gray-900` | 状态色背景覆盖 |
| 侧边栏 Tab 内容 | `bg-white` | `text-gray-900` | 与字幕列表同平面，无背景色差 |
| 波形区 | `bg-white` | `text-gray-500` | border-t 分隔 |

**状态色层次审查**：
- Pending 黄：`bg-yellow-50/text-yellow-700`（标签）vs `bg-yellow-100/text-yellow-700`（按钮）— 确保层次一致
- Confirmed 红：`bg-red-50/text-red-700` vs `bg-red-100/text-red-700`
- Rejected 绿：`bg-green-50/text-green-700` vs `bg-green-100/text-green-700`
- Action Blue 强调：仅用于 Primary 按钮、选中描边、播放头高亮

### 6.4 字体层级和行高

**目标**：建立清晰的字体大小层级，确保标题、正文、标注、时间戳有明确的视觉层次。

| 用途 | Tailwind 类 | px 值 | 字重 | 用在哪里 |
|------|------------|-------|------|---------|
| 区域标题 | `text-sm font-medium` | 14px | 500→**改 600** | Timeline 标题, 侧边栏 Tab |
| 正文（字幕文本） | `text-sm` | 14px | 400 | TranscriptRow 文本 |
| 标注/辅助 | `text-xs` | 12px | 400 | 统计信息, 按钮文字, 时间显示 |
| 微标注 | `text-[11px]` | 11px | 400 | 波形时间, ±按钮（移除后不适用） |
| 输入框 | `text-[11px] font-mono` | 11px | 400 | 时间编辑 input |

> **注意**：design-spec.md 原定字幕正文 17px，但当前实现统一使用 14px（`text-sm`）。本次优化**不改变**正文字号（14px 已适用于密集编辑场景），但确保层级关系一致。

**行高与间距**：
- TranscriptRow：`py-2`（8px 上下），行间无额外 gap，靠 padding 形成节奏
- SilenceRow：`h-8`（32px 固定高度），与 TranscriptRow 视觉等高
- 标题栏：`py-2`，与 TranscriptRow 保持一致的垂直节奏

---

## 7. 交互微动效 (Micro-interactions)

| 元素 | 效果 | 时长 |
|------|------|------|
| 所有按钮 | `transform: scale(0.95)` 按下 | 100ms |
| 状态切换 | 字幕行背景色渐变 | ease-in-out 300ms |
| 静音段 resize | 实时更新时间标注 | 即时 |
| 步骤切换 | 进度条平滑过渡 | ease-in-out 400ms |
| 导出弹窗 | 从中心 scale(0.95) + opacity 放大到 scale(1) | ease-out 200ms |
| 建议面板展开/折叠 | max-height 过渡 | ease-in-out 250ms |
| **侧边栏展开/收起** | **width 过渡**（flex-basis 或 width transition） | **ease-out 200ms** |
| **按钮 hover** | **background-color 过渡** | **150ms** |

---

## 8. 快捷键汇总

| 快捷键 | 上下文 | 功能 |
|--------|-------|------|
| `Space` | TranscriptRow 聚焦 | 从该行时间点播放视频 |
| `Shift+Space` | 全局 | 原片/剪后切换预览 |
| `Delete` | TranscriptRow 聚焦 | 标记删除（Pending -> Confirmed） |
| `Ctrl+Z` | 全局 | 撤销上一步编辑 |
| `Ctrl+S` | 全局 | 保存项目 |
| `Ctrl+F` | 编辑器区域 | 打开搜索替换 |
| `I` | 播放中 | 跳到当前片段开头 |
| `O` | 播放中 | 跳到当前片段结尾 |
| `Up/Down` | 编辑器区域（非 input 聚焦） | 上下移动选中行 |
| `Up/Down` | 时间编辑 input 聚焦 | ±0.1s 微调（Shift = ±1.0s） |
| `Shift+Click` | 编辑器区域 | 多选字幕行 |
| `Ctrl+Shift+A` | 建议面板 | 全部确认建议 |
| `Ctrl+Shift+D` | 建议面板 | 忽略所有建议 |

---

## 9. 设置页面快捷键展示 (Settings Shortcuts Tab)

在设置模态框（`SettingsModal.vue`）中新增第五个 Tab "快捷键"，将第 8 节的所有快捷键以可视化的方式展示给用户。

### 9.1 Tab 注册

在 Tab 导航数组（`SettingsModal.vue` Tab nav `v-for`）中新增：

```js
{ id: 'shortcuts' as const, label: '快捷键' }
```

对应扩展 `activeTab` 类型联合（`SettingsModal.vue` 第 67 行附近）：

```ts
const activeTab = ref<'general' | 'ai-engine' | 'llm' | 'export' | 'shortcuts'>('general')
```

### 9.2 布局结构

遵循设置页面的 section 卡片模式。按功能分组展示，每组一个 `<section>`：

```text
+-----------------------------------------------------------+
|  通用  |  AI 引擎  |  LLM  |  导出  |  快捷键              <- Tab 导航
+-----------------------------------------------------------+
|                                                           |
|  播放控制                                                  |
|  ----------------------------------------------------     |
|  从当前行播放视频            [ Space ]                      |
|  原片 / 剪后切换预览         [ Shift ] + [ Space ]          |
|  跳到片段开头                [ I ]                          |
|  跳到片段结尾                [ O ]                          |
|                                                           |
|  编辑操作                                                  |
|  ----------------------------------------------------     |
|  标记删除                    [ Delete ]                     |
|  撤销上一步                  [ Ctrl ] + [ Z ]               |
|  保存项目                    [ Ctrl ] + [ S ]               |
|  打开搜索替换                [ Ctrl ] + [ F ]               |
|                                                           |
|  上下移动选中行              [ ↑ ] / [ ↓ ]                   |
|  多选字幕行                  [ Shift ] + Click              |
|                                                           |
|  时间微调（时间编辑 input 聚焦时）                          |
|  ----------------------------------------------------     |
|  +0.1s / +1.0s(Shift)        [ ↑ ] ( [ Shift ] + [ ↑ ] )    |
|  -0.1s / -1.0s(Shift)        [ ↓ ] ( [ Shift ] + [ ↓ ] )    |
|                                                           |
|  建议面板                                                  |
|  ----------------------------------------------------     |
|  全部确认建议                [ Ctrl ] + [ Shift ] + [ A ]   |
|  忽略所有建议                [ Ctrl ] + [ Shift ] + [ D ]   |
|                                                           |
+-----------------------------------------------------------+
```

### 9.3 按键样式 (`<kbd>` 组件)

每个按键用 `<kbd>` 标签渲染，统一样式：

```html
<kbd class="inline-flex items-center min-w-[28px] justify-center rounded border border-gray-300
  bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-600 shadow-sm">
  Space
</kbd>
```

组合键用 `+` 分隔符连接：

```html
<kbd>Ctrl</kbd>
<span class="text-gray-400 mx-1">+</span>
<kbd>S</kbd>
```

### 9.4 分组规范

| 分组 | 包含快捷键 |
|------|-----------|
| 播放控制 | Space, Shift+Space, I, O |
| 编辑操作 | Delete, Ctrl+Z, Ctrl+S, Ctrl+F, Up/Down, Shift+Click |
| 时间微调 | Up/Down（input 聚焦时）, Shift+Up/Down |
| 建议面板 | Ctrl+Shift+A, Ctrl+Shift+D |

### 9.5 行布局模式

每行沿用设置页面的 `flex items-center justify-between` 模式：

```html
<div class="flex items-center justify-between py-1.5">
  <span class="text-gray-600">从当前行播放视频</span>
  <div class="flex items-center gap-1">
    <kbd>...</kbd>
  </div>
</div>
```

### 9.6 实现说明

- 快捷键列表**硬编码在模板中**（无集中式注册表），因为当前代码库的快捷键分散在各组件的 keydown handler 中
- 此 Tab 为纯展示，无交互逻辑、无 save 按钮（footer 的保存/关闭按钮不影响此 Tab）
- 如果后续新增快捷键，需同步更新此 Tab 内容和第 8 节汇总表

---

## 10. Bug 修正：文字拖拽误触 SRT 导入提示 (v2.1.1)

### 问题描述

用户在字幕列表中选中文字后拖动，会误触发全屏的"松开以导入 SRT 文件"拖放提示覆盖层。

### 根因分析

`App.vue` 根 `<div>`（第 180-186 行）绑定了 `@dragenter` / `@dragover` / `@dragleave` / `@drop` 四个事件处理器，用于检测外部文件拖入。但这些处理器**不检查 `e.dataTransfer` 的内容类型**，对任何拖拽事件（包括浏览器原生的文字拖拽）都会触发。

关键链路：
1. TranscriptRow 的字幕文本是普通 `<span>`（第 322 行），无 `select-none`，用户可正常选中
2. 选中文字后拖动 -> 浏览器发起标准 HTML5 文字拖拽（`dataTransfer.types` 含 `"text/plain"`，无 Files）
3. 拖拽事件冒泡到 `App.vue` 根 `<div>`
4. `handleWindowDragOver`（第 103-105 行）无条件调用 `preventDefault()`，允许 drop 发生
5. `handleWindowDragEnter`（第 95-101 行）设置 `isDragging = true`，显示蓝色覆盖层
6. `handleWindowDrop`（第 116-161 行）执行 100ms 后调用 `get_dropped_files()`，返回空（非文件拖拽），不导入任何内容
7. 但蓝色覆盖层已经闪现，造成视觉干扰

### 修复方案

在 `App.vue` 的四个拖拽处理器中，**对非文件拖拽提前返回**，不设置 `isDragging`，不调用 `preventDefault()`：

```js
// 判断是否为文件拖拽
function isFileDrag(e: DragEvent): boolean {
  return e.dataTransfer?.types?.includes("Files") ?? false
}

function handleWindowDragEnter(e: DragEvent) {
  if (!isFileDrag(e)) return          // 文字拖拽直接忽略
  dragCounter++
  if (!isDragging.value) isDragging.value = true
}

function handleWindowDragOver(e: DragEvent) {
  if (!isFileDrag(e)) return          // 不调用 preventDefault()，浏览器自然禁止 drop
  e.preventDefault()
}

function handleWindowDragLeave(e: DragEvent) {
  if (!isFileDrag(e)) return
  dragCounter--
  if (dragCounter <= 0) {
    dragCounter = 0
    isDragging.value = false
  }
}

function handleWindowDrop(e: DragEvent) {
  if (!isFileDrag(e)) return          // 文字 drop 不处理
  e.preventDefault()
  dragCounter = 0
  isDragging.value = false
  // ...原有导入逻辑...
}
```

### 安全性说明

- PyWebView 后端的文件拖放检测（`pywebvue/app.py:125-126`）只响应真实的 OS 文件拖放，与前端 UI 层的 `dataTransfer` 检查互不影响
- `dataTransfer.types.includes("Files")` 是标准 API，在所有现代浏览器中可靠工作
- 修复不影响真正的文件拖入导入功能

### 10.2 Bug 修正：ArrowUp/Down 时间微调步进错误 + 格式不一致

**问题描述**

字幕行时间列进入编辑模式后，用键盘 ArrowUp/Down 微调时间时：
1. 步进值完全不对（如按一次 ArrowUp 跳跃几十秒甚至几分钟）
2. 微调后 input 中显示的是无格式数字（如 `"1.3"`），与显示模式的 `MM:SS.mmm` 格式不一致
3. 确认后时间值错乱

**根因分析**

`TranscriptRow.vue` 时间编辑涉及两个核心函数，但微调逻辑对它们产生了误用：

| 函数 | 位置 | 行为 |
|------|------|------|
| `formatTime(seconds)` | `utils/format.ts:1` | 输出 `"MM:SS.mmm"` 格式（如 `01:23.456`）|
| `parseTime(input)` | `utils/format.ts:37` | 接受 `MM:SS.mmm` / `SS.mmm` / 纯秒数，返回秒数 |

**Bug 1 — 步进错误**：

`startTimeEdit`（第 113 行）用 `formatTime()` 初始化 input 值：
```js
editingTimeValue.value = formatTime(...)  // e.g. "01:23.456"
```

ArrowUp/Down 微调（第 145-146 行）和 `adjustTime`（第 131 行）用 `parseFloat()` 解析这个字符串：
```js
const current = parseFloat(editingTimeValue.value)  // parseFloat("01:23.456") = 1
```

`parseFloat("01:23.456")` 遇到第一个 `:` 就停止解析，返回 `1`。所以微调的基准值被误读为 `1` 秒，而非实际的 `83.456` 秒。按一次 ArrowUp 后值变成 `1.1`，按一次 Shift+ArrowUp 变成 `2.0`，与预期完全不符。

**Bug 2 — 格式不一致**：

微调后写入的值是纯数字：
```js
editingTimeValue.value = (current + step).toFixed(1)  // e.g. "1.1"
```

这覆盖了原来的 `"01:23.456"` 格式字符串。用户在 input 中看到的是 `"1.1"` 而非 `"01:23.456"`，视觉上与显示模式不一致。虽然 `applyTimeEdit` 调用 `parseTime("1.1")` 会正确返回 `1.1` 秒，但此时原始时间已被完全丢失。

**修复方案**

统一用秒数作为内部编辑状态，显示时格式化：

```js
// 用秒数（number）作为内部状态，而非格式化字符串
const editingTimeSeconds = ref<number>(0)

function startTimeEdit(field: "start" | "end", e: MouseEvent) {
  e.stopPropagation()
  const seconds = field === "start" ? props.segment.start : props.segment.end
  editingTimeSeconds.value = seconds
  editingTimeField.value = field
  // input 中显示格式化后的时间
  editingTimeValue.value = formatTime(seconds)
  nextTick(() => timeInputRef.value?.select())
}

function handleTimeEditKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    applyTimeEdit()
  } else if (e.key === "Escape") {
    cancelTimeEdit()
  } else if (e.key === "ArrowUp") {
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    editingTimeSeconds.value += step
    editingTimeValue.value = formatTime(editingTimeSeconds.value)
  } else if (e.key === "ArrowDown") {
    e.preventDefault()
    const step = e.shiftKey ? 1.0 : 0.1
    editingTimeSeconds.value = Math.max(0, editingTimeSeconds.value - step)
    editingTimeValue.value = formatTime(editingTimeSeconds.value)
  }
}

function applyTimeEdit() {
  // 优先从 input 文本解析（用户可能手动输入了新值）
  const parsed = parseTime(editingTimeValue.value)
  if (parsed !== null && editingTimeField.value) {
    emit("update-time", props.segment.id, editingTimeField.value, parsed)
  }
  editingTimeField.value = null
}
```

**关键变更点**：

| 变更 | 原逻辑 | 新逻辑 |
|------|--------|--------|
| 内部基准值 | `parseFloat(editingTimeValue)` 解析 `"MM:SS.mmm"` 字符串 | 独立 `editingTimeSeconds: number` 变量，直接存储秒数 |
| ArrowUp/Down 运算 | `parseFloat("01:23.456") + 0.1` = `1.1`（错误） | `83.456 + 0.1` = `83.556`（正确） |
| input 显示值 | `(current + step).toFixed(1)` = `"1.1"`（无格式） | `formatTime(83.556)` = `"01:23.556"`（一致格式） |
| 手动输入兼容 | 用户手动输入会被 `parseFloat` 误解析 | `applyTimeEdit` 仍走 `parseTime(input)`，正常解析用户手动输入的 `MM:SS.mmm` 或纯秒数 |
| 负值保护 | 无 | ArrowDown 时 `Math.max(0, ...)` 防止负时间 |

**`adjustTime` 函数同步修复**（当前被 ± 按钮调用，重构后 ± 按钮移除，但函数逻辑应一致以防残留调用）：

```js
function adjustTime(delta: number) {
  editingTimeSeconds.value = Math.max(0, editingTimeSeconds.value + delta)
  editingTimeValue.value = formatTime(editingTimeSeconds.value)
  applyTimeEdit()
}
```

### 10.3 Bug 修正：字幕修正 NameError 导致功能完全崩溃

**问题描述**

字幕修正功能执行完成后，后端抛出 `NameError: name 'timeline_id' is not defined`，导致修正结果无法存储，前端收不到 `llm:subtitle_correction_completed` 事件，功能完全不可用。

**根因**

`main.py` 第 819 行（`_handle_subtitle_correction` 方法）：

```python
store_result = self._mark_dirty(
    self._project.store_subtitle_corrections(corrections, timeline_id)  # ← timeline_id 未定义
)
```

该函数在第 760 行通过 `timeline = self._get_target_timeline(task)` 获取了 timeline 对象，但从未定义 `timeline_id` 变量。`_get_target_timeline` 内部（第 364 行）计算了 `timeline_id` 但只返回 `timeline` 对象，不返回 ID。

对比 `_handle_smart_delete`（第 738 行）调用 `add_analysis_results` 时不传 timeline_id（使用 active timeline），而 `store_subtitle_corrections` 的签名要求传入 `timeline_id: str`。

**修复方案**

在第 760 行之后补充 `timeline_id` 变量定义：

```python
timeline = self._get_target_timeline(task)
timeline_id = task.payload.get("timeline_id", "") or self._project.current.active_timeline_id
```

或直接使用 `timeline.id`（如果 Timeline 模型有 id 字段），与 `_get_target_timeline` 内部逻辑一致。

**修复后**：字幕修正完成后的反馈链路恢复：
- 后端发射 `llm:subtitle_correction_completed` 事件
- 前端 `useLlmTasks` 监听 → `subtitleCorrectionCount > 0`
- AIAssistantPanel 显示绿色"查看修正结果 (N 条)"按钮
- SuggestionPanel 显示"P1 字幕修正待审 (N 条)"蓝色横条

**额外改进**：修正完成时增加完成 toast 提示（当前无完成 toast）：

在 `useLlmTasks.ts` 的 `EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED` 监听回调中（第 124-134 行），增加 toast 通知（需通过 composable 暴露 toast 能力或在 WorkspacePage 的事件回调中处理）：

```ts
// WorkspacePage.vue 中监听 llm:subtitle_correction_completed
// 或在 useLlmTasks 回调中触发外部回调
showToast(`字幕修正完成，发现 ${stored_count} 条修改`, "success", 3000)
```

用户手动点击"查看修正结果"按钮打开全屏审阅界面（不自动打开）。

---

## 11. 精华提取功能重构 (v2.1.1)

### 11.1 问题总览

当前精华提取功能存在多层问题导致基本不可用：

| 问题 | 严重程度 | 位置 |
|------|---------|------|
| highlight EditDecision 污染字幕行状态 | 高 — 字幕行误显 pending 黄色 | `main.py:897-908` 创建, `segmentHelpers.ts:25-52` 未过滤 |
| 后端未过滤已确认删除段落 | 高 — LLM 收到垃圾数据 | `main.py:848-852` |
| 前端不显示字幕原文 | 中 — 用户无法判断片段内容 | `HighlightModeView.vue:220-222` |
| 无编辑/删除/添加能力 | 高 — 结果不可调整 | `HighlightModeView.vue` 全局 |
| 无导出入口 | 低 — 可手动到导出页操作 | - |

### 11.2 后端修复：移除 highlight EditDecision 创建

**根因分析**

`_handle_highlight`（`main.py` 第 888-908 行）为每个精华片段创建了 `EditDecision(action="keep", source="llm_highlight", status=PENDING(默认), priority=30)`。这些 edits 进入 timeline.edits 列表后，被 `resolveSegmentState`（`segmentHelpers.ts:25-52`）处理：

```js
// resolveSegmentState 不区分 source/action，把所有非 rejected 的 edits 纳入状态计算
const active = all.filter(e => e.status !== "rejected")  // highlight 的 pending 被纳入
// ...
return {
  displayStatus: topActive.status,  // "pending" — 来自 highlight edit
  styleClass: topActive.action === "delete" ? "masked" : "kept",  // "kept"
}
```

只有 highlight edit 的 segment 被设为 `displayStatus="pending"`，导致 TranscriptRow 显示黄色背景和左边条（像是删除建议），但实际上 SuggestionPanel 不计入它（因为只算 `action="delete"`）。

**表现**：字幕列表中显示为黄色"待处理"的段落数 ≠ SuggestionPanel 中"N 处待处理"的数量。

**修复方案**：`_handle_highlight` 不再创建 EditDecision，仅保留 AnalysisResult。

移除 `main.py` 第 888-908 行的整个 `edits = []` 代码块，以及第 933 行 `"edits": edits` 的返回值。精华片段仅通过 `AnalysisResult(type="llm_highlight", segment_ids=[segId])` 和前端 `highlightResults` 管理。

同时需要修改 `llm:highlight_completed` 事件（第 929-937 行）中不再传 `edits` 字段，前端 `useLlmTasks.ts` 对应事件监听去掉对 `edits` 的处理。

**受影响的后端功能适配**：

`detect_highlight_jump_cuts`（`main.py:2427`）和 `get_highlight_ranges`（`export_service.py:480-491`）当前从 `timeline.edits` 中提取 `action="keep" + source="llm_highlight"` 的范围。移除 EditDecision 后，需改为从 `AnalysisResult(type="llm_highlight")` 的 `segment_ids` + `timeline.transcript.segments` 推导范围：

```python
# detect_highlight_jump_cuts 重写
analysis_results = [r for r in timeline.analysis.results if r.type == "llm_highlight"]
seg_ids = set()
for r in analysis_results:
    seg_ids.update(r.segment_ids)
seg_map = {s.id: s for s in timeline.transcript.segments if s.type == SegmentType.SUBTITLE}
ranges = [(seg_map[sid].start, seg_map[sid].end) for sid in seg_ids if sid in seg_map]
ranges.sort()
# 然后 detect_jump_cuts(ranges) 不变
```

`get_highlight_ranges`（export_service.py）同样重写，或标记为 deprecated 由新逻辑替代。

### 11.3 后端修复：过滤已删除段落

### 11.3 后端修复：过滤已删除段落

在 `_handle_highlight`（`main.py` 第 848-852 行）中，增加 confirmed 删除段落的过滤：

```python
from core.timeline_utils import collect_confirmed_deleted_seg_ids

# 仅过滤 confirmed（已确认删除），保留 pending（待确认可能被保留）
deleted_seg_ids = collect_confirmed_deleted_seg_ids(timeline)
segments = [
    s.model_dump()
    for s in timeline.transcript.segments
    if s.type == SegmentType.SUBTITLE and s.id not in deleted_seg_ids
]
```

与 `_handle_smart_delete`（第 650-655 行）和 `_handle_subtitle_correction`（第 767-772 行）保持一致的过滤策略。

### 11.4 前端重构：HighlightModeView 结果展示

保持当前的两行卡片结构，做以下调整：

**当前结构（每个片段卡片）：**
```
┌─────────────────────────────────────────┐
│ [12:34]  [高密度]                        │  <- 第一行：时间戳 + 密度标签
│ 核心论点：介绍了产品三大核心优势          │  <- 第二行：理由文字
└─────────────────────────────────────────┘
```

**重构后结构：**
```
┌─────────────────────────────────────────┐
│ ● [12:34]  我们的产品有三大核心优势...    │  <- 第一行：密度圆点 + 时间戳 + 字幕原文(截断)
│ 核心论点：介绍了产品三大核心优势          │  <- 第二行：理由文字
└─────────────────────────────────────────┘
```

具体变更：

| 元素 | 当前 | 重构后 |
|------|------|--------|
| 密度标签 | `bg-green-100 text-green-800` 文字徽章"高密度" | 8px 颜色圆点（green/yellow/gray）|
| 字幕原文 | 不显示 | 第一行时间戳后显示 `segment.text`，`truncate` 截断 |
| 理由文字 | 第二行显示 | 保留不变 |
| 删除操作 | 无 | 右键菜单"从精华中移除" |

**密度圆点样式：**

```html
<!-- 替换 densityBadge + densityLabel -->
<span
  class="inline-block h-2 w-2 shrink-0 rounded-full"
  :class="{
    'bg-green-500': item.highlight.density === 'high',
    'bg-yellow-500': item.highlight.density === 'medium',
    'bg-gray-400': item.highlight.density === 'low',
  }"
  :title="densityLabel(item.highlight.density)"
></span>
```

**字幕原文显示：**

```html
<!-- 第一行：圆点 + 时间戳 + 字幕原文 -->
<div class="mb-1 flex items-center gap-2 min-w-0">
  <span class="density-dot ..." />
  <button class="shrink-0 ..." @click="handleSeek(item.startTime)">
    {{ formatTimeShort(item.startTime) }}
  </button>
  <span class="truncate text-gray-500">{{ item.segment?.text }}</span>
</div>
<!-- 第二行：理由（保留不变） -->
<div class="text-gray-600">{{ item.highlight.highlight_reason }}</div>
```

### 11.5 前端重构：编辑能力

#### 11.5.1 删除片段

在精华列表项上增加右键菜单：

```html
<div
  v-for="item in sortedHighlights"
  @contextmenu="onHighlightContextMenu($event, item.highlight.segment_id)"
>
```

右键菜单项："从精华中移除" → emit 事件到 WorkspacePage → 调用后端删除对应的 `AnalysisResult(type="llm_highlight")`。

需要新增后端 API（或复用现有 `delete_analysis_results`）：
- 删除指定 segment_id 的 highlight AnalysisResult
- 前端 `highlightResults` 同步过滤移除该项

**新增 emit 事件链：**
`HighlightModeView @remove-highlight(segmentId)` → `Timeline @remove-highlight` → `WorkspacePage handleRemoveHighlight(segmentId)`

#### 11.5.2 手动添加片段

在 TranscriptRow 的右键菜单中增加"加入精华"选项。点击后：
1. 为该字幕段落创建 `AnalysisResult(type="llm_highlight", segment_ids=[segId], confidence=1.0, detail="手动添加")`
2. 前端 highlightResults 增加该项

**数据流：** TranscriptRow 右键菜单 → emit 到 WorkspacePage → 调用后端 API → 刷新前端状态

需要新增后端 API：`add_highlight_segment(segment_id, timeline_id)`

#### 11.5.3 微调片段起止时间

精华片段在波形编辑器（WaveformEditor）中显示为色块，用户可直接在波形上拖拽边界微调（类似静音段的 resize 手柄）。

- 精华片段在波形上显示为半透明蓝色色块（区别于静音段的灰色、删除段的红色）
- 左右边界可拖拽 resize
- 拖拽后更新对应 segment 的 start/end

> **注意**：此功能依赖波形编辑器对 highlight 类型的渲染支持，需要在 `SegmentBlocksLayer` 或 `WaveformEditor` 中增加 highlight 色块的渲染逻辑（从 AnalysisResult 而非 EditDecision 获取 highlight 范围）。如果波形实现复杂度较高，可作为 P2 延后。

### 11.6 数据模型补充

当前精华结果在前端是 `HighlightResult` 接口（`useLlmTasks.ts`），后端以普通 dict 流转，没有专用 Pydantic 模型。建议保持现状（dict + 前端 interface），不新增模型类。

精华片段在项目中**仅通过 AnalysisResult 存在**：
- `AnalysisResult(type="llm_highlight", segment_ids=[segId])` — 分析记录

不再创建 EditDecision。删除/添加操作只需维护 AnalysisResult，前端 `highlightResults` 同步更新。

---

## 12. 实施优先级 (v2.1.1 UI/UX 优化)

| 优先级 | 任务 | 影响范围 | 风险 |
|--------|------|---------|------|
| P0 | 侧边栏内联化重构 | Timeline.vue, WorkspacePage.vue | 中 — 布局重构 |
| P0 | TranscriptRow 时间列编辑重构 | TranscriptRow.vue | 低 — 局部组件 |
| P0 | 文字拖拽误触 SRT 导入提示 Bug | App.vue | 低 — 事件处理器增加类型检查 |
| P0 | ArrowUp/Down 时间微调步进错误 + 格式不一致 | TranscriptRow.vue | 低 — 用秒数变量替代 parseFloat |
| P0 | 字幕修正 NameError 导致功能崩溃 | main.py:819 | 低 — 补充 timeline_id 变量定义 |
| P0 | 精华提取后端未过滤已删除段落 | main.py:848-852 | 低 — 增加 collect_confirmed_deleted_seg_ids |
| P0 | highlight EditDecision 污染字幕行状态（数量不一致）| main.py:888-908, segmentHelpers.ts | 中 — 移除 EditDecision 创建 + 适配 jump_cuts |
| P1 | 精华提取前端结果显示重构 | HighlightModeView.vue | 中 — 圆点+原文+右键菜单 |
| P1 | 精华片段删除/添加能力 | HighlightModeView, TranscriptRow, main.py | 中 — 新增 API + 事件链 |
| P1 | 字幕修正完成 toast 提示 | useLlmTasks.ts / WorkspacePage.vue | 低 — 增加 success toast |
| P1 | 标题栏分区重构 | Timeline.vue | 低 — 模板调整 |
| P1 | 间距/边框/圆角节奏统一 | 全局 CSS + 组件 | 低 — 样式微调 |
| P1 | 按钮层级和交互反馈统一 | 全局组件 | 低 — class 替换 |
| P2 | 配色和明暗过渡精炼 | 全局组件 | 低 — 颜色微调 |
| P2 | 字体层级和行高审查 | 全局组件 | 低 — class 替换 |
| P2 | 设置页面快捷键 Tab | SettingsModal.vue | 低 — 纯展示 section |
| P3 | 波形工具栏增强 | WaveformEditor.vue | 待定 — 审阅后决定 |

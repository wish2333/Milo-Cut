# v2.1.1 Spec-6 实施符合度审计报告

> **日期**: 2026-06-25
> **审计目标**: 对照 `docs/2.1.1/spec-2.1.1-6.md`，逐项核查当前代码库的实施符合度
> **审计范围**: spec-2.1.1-6.md 全部 12 节（工作区布局、侧边栏内联化、核心组件、导出弹窗、响应式、全局视觉精炼、微动效、快捷键、设置页快捷键 Tab、三处 Bug 修正、精华提取重构、实施优先级）
> **方法**: 直接读源码（grep + read_file）逐条比对，所有结论附 file:line 证据
> **基线**: 当前工作树（dev 分支，未开始 spec-6 实施）

---

## 0. Executive Summary

**核心结论：spec-2.1.1-6.md 描述的 v2.1.1 UI/UX 优化几乎完全未实施。** 当前代码库仍处于 spec-6 之前的状态——侧边栏仍是浮动覆盖层、时间列 ± 按钮仍在、三个 P0 Bug 全部存在、精华提取重构零进展。

> **阻断性缺陷预警（Hotfix 级）**：当前主干代码存在一个严重的阻断性 Bug——字幕修正功能因 `NameError: name 'timeline_id' is not defined`（main.py:819）完全崩溃，用户执行修正后结果无法存储、前端收不到完成事件。**无论 spec-6 规划如何，此项需立即打 Hotfix 优先修复**，不应等到 spec-6 整体实施时才处理。详见 §6.3。

### 总体符合度

| 维度 | 符合 | 部分符合 | 不符合 | 符合率 |
|------|------|---------|--------|--------|
| 侧边栏内联化（§1-2，7 项） | 2 | 1 | **4** | 29% |
| 核心组件（§3-5，多项） | 9 | 8 | **11** | 32% |
| 导出摘要弹窗（§4，5 项） | 3 | 0 | **2** | 60% |
| 全局视觉精炼（§6-7） | 4 | 3 | **5** | 33% |
| 快捷键 + 设置页（§8-9） | 7 | 1 | **6** | 50% |
| Bug 修正（§10，3 个 P0） | 0 | 0 | **3** | 0% |
| 精华提取重构（§11，6 项） | 0 | 0 | **6** | 0% |
| **合计** | **25** | **13** | **37** | **34%** |

### 缺陷分类（Bug vs 重构）

为便于排期与验收，将 spec §12 的 P0 任务按性质分为两类——**代码缺陷（Bug）**看重回归测试，**核心功能重构**看重视觉与交互验收：

**A. 现有系统代码缺陷（P0 Bug，5 项）** — 针对已上线功能的回归性修复

| Bug ID | 描述 | 性质 | 状态 |
|--------|------|------|------|
| §10 拖拽误触 SRT | 文字拖拽触发导入覆盖层 | 交互缺陷 | **未修复** |
| §10.2 ArrowUp/Down 步进 | `parseFloat("MM:SS.mmm")` 导致时间错乱 | 逻辑缺陷 | **未修复** |
| §10.3 字幕修正 NameError | `timeline_id` 未定义，**功能完全崩溃（阻断性）** | 崩溃缺陷 | **未修复** |
| §11.2 highlight EditDecision 污染 | 精华 edit 导致字幕行误显黄色 | 数据污染 | **未修复** |
| §11.3 后端未过滤已删除段落 | LLM 收到已确认删除的垃圾数据 | 数据缺陷 | **未修复** |

**B. Spec 规定的核心功能重构（P0 重构，2 项）** — spec-6 新增的布局/交互变更

| 重构 ID | 描述 | 性质 | 状态 |
|---------|------|------|------|
| §1-2 侧边栏内联化 | 浮动覆盖层 → Timeline flex 子元素 | 布局重构 | **未实施** |
| §3.1.1 时间列重构 | 移除 ± 按钮，改原地 input 替换 | 交互重构 | **未实施** |

### 实施进度推断

spec-2.1.1-6.md 第 12 节列出的 17 项任务（P0×7、P1×6、P2×3、P3×1）中，**无任何一项可判定为已完成**。代码库中存在一些 spec 之前已实现的关联逻辑（如 `collect_confirmed_deleted_seg_ids` helper 已被 smart_delete 和 subtitle_correction 使用，但 highlight 未用），说明开发者拥有实施所需的全部基础设施，只是尚未启动 spec-6 的工作。

---

## 1. 侧边栏内联化（§1-2）— 严重不符合

**这是 spec-6 的核心变更（P0），当前完全未实施。** 侧边栏仍为 `<Teleport to="body">` + `fixed` 定位的浮动覆盖层，与 spec 描述的"Timeline 内部 flex 兄弟元素"模型相反。

### 1.1 布局结构（§2.1）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 侧边栏为 flex 子元素 | Timeline.vue `relative flex flex-1 overflow-hidden` 容器（:272）的第三个 flex 子 | **Timeline.vue:354** `<Teleport to="body">` 脱离 DOM 流；:272 容器内只有 transcript list（:274）和 toggle button（:338）两个子元素 | **不符合** |

```html
<!-- Timeline.vue:272 — flex 容器，spec 要求侧边栏在此内部 -->
<div class="relative flex flex-1 overflow-hidden">
  <div ref="listContainer" class="flex-1 overflow-y-auto"> ... </div>  <!-- :274 字幕列表 -->
  <button v-show="!sidebarOpen" class="absolute right-2 top-2 ...">   <!-- :338 toggle -->
</div>

<!-- Timeline.vue:354 — 侧边栏被 Teleport 到 body，不在 flex 容器内 -->
<Teleport to="body">
  <Transition ...>
    <div v-if="sidebarOpen" class="fixed top-0 bottom-0 right-0 ... z-40">  <!-- :363-365 -->
```

### 1.2 状态管理（§2.2）

| 属性 | Spec 默认值 | 持久化 | 实际 | 状态 |
|------|------------|--------|------|------|
| `sidebarOpen` | `true`（默认展开） | 否 | **Timeline.vue:105** `ref(false)` — 默认收起 | **不符合** |
| `sidebarWidth` | `384` | 是 `milo-sidebar-width` | **Timeline.vue:111-112** `Number(localStorage.getItem(SIDEBAR_STORAGE_KEY)) \|\| 384` | 符合 |
| min/max 约束 | 320 / `innerWidth*0.85` | — | **Timeline.vue:108-109,114** `SIDEBAR_MIN=320`、`SIDEBAR_MAX_RATIO=0.85` | 符合 |
| `activeTab` | `"suggestion"` | 否 | **Timeline.vue:97** `ref<RightPanelTab>("suggestion")` | 符合 |

### 1.3 收起/展开交互（§2.3）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 收起后 `v-if="false"` 完全移除 | DOM 销毁 | **Timeline.vue:364** `v-if="sidebarOpen"` — 是 v-if | 符合 |
| 动画：`transition: width 200ms ease-out` | width 过渡，字幕列表同步收缩 | **Timeline.vue:356-361** 用 `translate-x-full`/`translate-x-0` **transform 滑动**，非 width 过渡；字幕列表不收缩（因侧边栏是覆盖层） | **不符合** |

```html
<!-- Timeline.vue:355-361 — transform 滑动，非 spec 要求的 width 过渡 -->
<Transition
  enter-active-class="transition transform duration-200 ease-out"
  enter-from-class="translate-x-full"
  enter-to-class="translate-x-0"
  leave-active-class="transition transform duration-200 ease-in"
  leave-from-class="translate-x-0"
  leave-to-class="translate-x-full"
>
```

### 1.4 标题栏分区（§2.4）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 主标题栏左右分区 | 左：Timeline 标题+工具；右：侧边栏 Tab + 收起箭头，同一行 | Timeline 主标题栏（:224-270）只有 Timeline 标题和工具按钮；侧边栏 Tab（:376-402）在**浮动面板内部独立 header** | **不符合** |

### 1.5 分隔条（§2.5）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| `w-px`（1px 可见线）| 1px 灰线 | **Timeline.vue:370** `w-1.5`（6px）| 部分符合 |
| 透明 hit area `-left-1.5 -right-1.5 z-10` | 两侧扩展命中区 | :370 无 `-left-1.5 -right-1.5`，整个 6px 手柄即命中区 | 部分符合 |
| `bg-gray-200` 默认色 | 灰色 | :370 `bg-gray-200/0`（完全透明）| **不符合** |
| `hover:bg-blue-400` | 悬停蓝 | :370 `hover:bg-blue-400/40`（40% 透明度）| 部分符合 |

### 1.6 竖向滚动（§2.6）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| tab 内容区 `overflow-y-auto` | 独立滚动 | **Timeline.vue:405** `class="flex-1 overflow-y-auto p-2"` | 符合 |

### 1.7 移除的元素（§2.7）

spec 要求内联版移除以下浮动版特有元素——**全部仍存在**：

| 元素 | Spec 要求 | 实际 | 状态 |
|------|----------|------|------|
| `<Teleport to="body">` | 移除 | **Timeline.vue:354** 仍存在 | **不符合** |
| `fixed top-0 bottom-0 right-0` | 移除 | **Timeline.vue:365** 仍存在 | **不符合** |
| `shadow-2xl` | 移除 | **Timeline.vue:365** 仍存在 | **不符合** |
| `z-40` | 移除 | **Timeline.vue:365** 仍存在 | **不符合** |
| 独立 hamburger 按钮 | 改由标题栏箭头替代 | :338-347 有一个 `absolute right-2 top-2` 的菜单图标按钮（三条横线 SVG），`v-show="!sidebarOpen"` | **不符合** |

### 1.8 小结

侧边栏内联化 7 项核查中 **2 符合 / 1 部分符合 / 4 不符合**。核心问题：侧边栏仍是全屏覆盖层，未进入 Timeline flex 布局，spec 描述的"挤压字幕列表宽度、视频区不受影响"的空间分配模型无法实现。

---

## 2. 核心组件（§3-5）— 部分符合

### 2.1 TranscriptRow 时间列（§3.1 + §3.1.1）— 重构未完成

§3.1.1 是 spec-6 的 P0 修复项，要求"原地替换编辑，去掉 ± 按钮"。**当前 ± 按钮仍完整存在**。

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 时间列 `w-[150px] shrink-0` | 150px 固定 | **TranscriptRow.vue:257** `w-[150px] shrink-0` | 符合 |
| input 宽度与 span 一致（~60px）| 零布局偏移 | **TranscriptRow.vue:268** `w-[55px]`（55px，接近 60px）| 基本符合 |
| **去掉 ± 按钮** | 不渲染额外按钮元素 | **TranscriptRow.vue:260-264**（−按钮）、**273-277**（+按钮）start 编辑模式；**286-290**、**299-303** end 编辑模式 — ± 按钮各一对，共 4 个 | **不符合** |
| 零布局偏移 | input 和 span 同 font-mono/size/padding | input `w-[55px]`（:268），span 无固定宽度，宽度不完全一致 | 部分符合 |

```html
<!-- TranscriptRow.vue:259-278 — start 时间编辑模式，± 按钮仍存在 -->
<div class="flex items-center gap-0.5">
  <button ... @click.stop="adjustTime(-0.1)">&minus;</button>   <!-- :260 应移除 -->
  <input ref="timeInputRef" v-model="editingTimeValue" class="w-[55px] ..." />
  <button ... @click.stop="adjustTime(0.1)">+</button>          <!-- :273 应移除 -->
</div>
```

### 2.2 TranscriptRow 状态视觉映射（§3.1）

| 状态 | Spec 期望（背景/左边条）| 实际实现 | 状态 |
|------|----------------------|---------|------|
| Pending | `#fff9e6` + 3px 黄竖线 | **TranscriptRow.vue:228-233** 仅 `masked`(红)/`kept`(绿) 两档 styleClass；Pending 通过 `displayStatus` 在按钮区分（:356-371），**无独立黄色行背景** | **不符合** |
| Confirmed | `#fef2f2` + 中划线 + 3px 红 | `styleClass="masked"` → `border-l-3 border-red-400 bg-red-50 line-through opacity-60`（:228）；`bg-red-50` ≈ #fef2f2 | 符合 |
| Rejected | `#f0fdf4` + 3px 绿 | `styleClass="kept"` → `border-l-3 border-green-400 bg-green-50`（:229）；`bg-green-50` ≈ #f0fdf4 | 符合 |

### 2.3 SilenceRow（§3.2）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 背景 `#f5f5f7` | 灰色 | **SilenceRow.vue:81** `bg-gray-50`（=#f9fafb，非 #f5f5f7）| 部分符合 |
| 高度 32px（h-8）| h-8 | **SilenceRow.vue:78** `h-8` | 符合 |
| 居中"静音 N.Ns" | 居中标注 | **SilenceRow.vue:118-120** `flex-1 text-center` "--- 静音 {{ duration }}s ---"（用 `---` 包裹，非 spec 的"静音 N.Ns"）| 部分符合 |
| **resize 手柄（4px，hover Action Blue）** | 可拖拽调整 | **SilenceRow.vue 无 resize 手柄**，不支持拖拽调整时长 | **不符合** |
| 拖拽同步相邻字幕起止 | 实时同步 | 无此能力（依赖上一条）| **不符合** |
| 状态映射（4 档）| 默认/建议删除/已确认/已保留 | **SilenceRow.vue:80-85** pending→黄、confirmed/masked→红、kept→绿 | 符合 |

### 2.4 SuggestionPanel（§3.3）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| `rounded-lg`（18px）| 圆角 | **SuggestionPanel.vue:190** `rounded-lg`（Tailwind 8px，非 spec 18px；但 §6.1 统一为 8px，以此为准）| 符合 |
| 边框 `#d2d2d7` | 灰色 | :190 `border-gray-200`（=#e5e7eb，非 #d2d2d7）| 部分符合 |
| 按类型分组可展开/折叠 | 折叠组 | **SuggestionPanel.vue:27** `expandedGroups`、**106** `toggleGroup`、**217-231** 分组 UI | 符合 |
| "全部确认删除" | 批量确认 | **SuggestionPanel.vue:298-302** `@click="emit('confirm-all')"` | 符合 |
| "忽略所有建议" | 批量忽略 | **SuggestionPanel.vue:303-308** `@click="emit('reject-all')"` | 符合 |

### 2.5 VideoPlayer（§3.4）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 背景 `#272729` | 深灰 | **WorkspacePage.vue:1917** `bg-gray-900`（=#111827，非 #272729；`#272729` 定义在 style.css:35 但视频区未用）| **不符合** |
| 视频窗口投影 `3px 5px 30px` | 浮动阴影 | WorkspacePage.vue 视频容器（:1919-1924）无 shadow 类 | **不符合** |
| Shift+Space 切换原片/剪后 | 键盘切换 | **WorkspacePage.vue:1390-1393** `if (e.shiftKey && e.code === "Space") previewMode toggle` | 符合 |
| 独立 VideoPlayer 组件 | — | 无独立组件，逻辑分布在 WorkspacePage.vue + VideoControls.vue | 部分符合 |

### 2.6 WaveformEditor（§3.5）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 高度 64px（§3.5）/ ~124px（§1 表格）| 固定 | **WaveformEditor.vue:122** `h-28`（112px 画布）+ :106 `h-6`（24px 控制栏）= **136px 总高**；与 spec 两处均不符 | 部分符合 |
| 静音段半透明色块 | 灰色覆盖 | **WaveformCanvas.vue:138-155** `drawSilenceOverlay()` 用 `rgba(148,163,184,0.25)` | 符合 |
| 段落边界竖线 + 时间戳 | 竖线标记 | **SegmentBlocksLayer.vue:336-371** 用绝对定位 div 绘制**完整块状**（border + 背景），非竖线 | 部分符合 |
| Confirmed 删除段红色半透明 | 红色覆盖 | **SegmentBlocksLayer.vue:103** `masked`→`bg-red-200/60`；:374-385 edit range overlays `bg-red-300/30` + 斜线图案 | 符合 |
| 工具栏 Regen + 窗口时间 | 基本工具栏 | **WaveformEditor.vue:107-116** Regen 按钮 + viewStart/viewDuration/viewEnd | 符合 |

### 2.7 StepController（§3.6）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| Global Nav 居中步骤进度 | `[1 导入]--(2 转写)--...--[5 导出]` | **无 StepController 组件**（grep 零匹配）；WorkspacePage.vue:1487-1541 顶部 nav 只有项目名和 save 按钮，**无步骤进度 UI** | **不符合** |

### 2.8 小结

核心组件核查中 **9 符合 / 8 部分符合 / 11 不符合**。主要缺口：TranscriptRow ±按钮未移除（P0）、SilenceRow 无 resize 手柄、无 StepController、视频区背景色/阴影不符。已符合项多为 v2.1.0 之前已实现的基础能力。

---

## 3. 导出摘要弹窗（§4）— 基本符合

### 3.1 Hero 统计 + Safety Checks

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| Hero 大数字（预计/裁剪/占比）| 56px/600 hero-display | **EditSummaryModal.vue:37-55** `text-3xl font-bold`（≈30px，非 spec 56px）三列 | 部分符合 |
| Safety Checks 区（>60s、连续>3段）| 黄色警告列表 | **EditSummaryModal.vue:57-68** 遍历 `summary.warnings`，`bg-yellow-50`；测试 `EditSummaryModal.test.ts:20-23` 验证 >60s 和 3+ 连续阈值 | 符合 |
| 占比>40% 变红 | 警告红 | **EditSummaryModal.vue:17** `isWarning = delete_percent > 40`；:49 `:class="isWarning ? 'text-red-600' : 'text-blue-600'"`；:71-73 额外红色提示框 | 符合 |
| Apple 风格居中模态 | 居中 + 遮罩 | :27-32 `fixed inset-0 z-50 ... bg-black/40` + `rounded-2xl shadow-2xl` | 符合 |

### 3.2 导出模式切换（§4）— 缺失

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 精确/快速 pill toggle | `[精确模式(推荐)] [快速模式]` | **EditSummaryModal.vue 无导出模式切换 UI**；全前端 grep `export_mode\|精确模式\|快速模式\|exportMode\|precision` 零匹配 | **不符合** |

### 3.3 小结

导出摘要弹窗 5 项中 **3 符合 / 0 部分符合 / 2 不符合**。Hero 统计和 Safety Checks 已实现（v2.1.0 基础），但导出模式 pill toggle 完全缺失。

---

## 4. 全局视觉精炼（§6-7）— 部分符合

### 4.1 间距/边框/圆角（§6.1）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 区域间 1px `border-gray-200` 分隔 | 统一边框 | WorkspacePage toolbar `border-b border-gray-200`（:1544）、Timeline header（:376）、BatchExportPanel（:109）一致 | 符合 |
| 基准内边距 `px-4 py-2` | Nav/Toolbar/标题栏 | 工具栏按钮 `px-3 py-1.5`（:1546）— 用 px-3 非 px-4 | 部分符合 |
| 紧凑内边距 `px-3 py-2` | TranscriptRow/SilenceRow | TranscriptRow 行 `px-3`、SilenceRow :78 `px-3` | 符合 |
| 按钮 `rounded-md`（6px）| 统一圆角 | 工具栏按钮 `rounded-md`（:1546），弹窗按钮 `rounded-lg`（:1855）— 两级但各自一致 | 符合 |
| 边框色 `border-gray-200`/`border-gray-300` | 分隔/输入区分 | 输入框 `border-gray-300`、分隔 `border-gray-200` 一致 | 符合 |

### 4.2 按钮层级（§6.2）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| Primary `bg-blue-500` | 主操作 | `bg-blue-500`（:1546, :1861）| 符合 |
| Secondary `bg-gray-100` | 次要操作 | `bg-gray-100 hover:bg-gray-200`（:345 等）| 符合 |
| Toggle Active/Inactive | 激活/未激活 | pill 样式（:1567-1576）| 符合 |
| Danger `bg-red-100` | 危险 | `bg-red-500`（:1709, :438）— 用 500 非 100 | 部分符合 |
| Ghost（深色背景）`text-gray-400` | Nav 次要 | WorkspacePage nav 按钮 `text-gray-400`（:1500 等）| 符合 |
| **`active:scale-95`** | 按下反馈 | **全前端仅 FileDropInput.vue:39 一处**；工具栏/弹窗/面板按钮均无 | **不符合** |
| **`transition-colors duration-150`** | 统一过渡 | 用了 `transition-colors` 但**无 `duration-150`**（grep 零匹配）| **不符合** |
| `disabled:opacity-50` | 禁用态 | 部分按钮有 `disabled:opacity-50` | 部分符合 |

### 4.3 配色（§6.3）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| Nav `bg-gray-900` | 深色 | **WorkspacePage.vue:1487** `bg-gray-900` | 符合 |
| Toolbar `bg-gray-50` | 浅灰 | **WorkspacePage.vue:1544** `bg-gray-50` | 符合 |
| Timeline `bg-white` | 白色 | **WorkspacePage.vue:1485, :1974** `bg-white` | 符合 |

### 4.4 字体层级（§6.4）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 区域标题 `text-sm font-medium`（**改 600**）| 600 字重 | SettingsModal h3 `text-sm font-semibold`（:720, :781）、HighlightModeView:123 `font-semibold`、EditSummaryModal:34 `text-lg font-semibold` — 实际多用 semibold(600)，与 spec 目标一致 | 符合 |
| 正文 `text-sm`（14px，不回 17px）| 14px | 全局正文 `text-sm` | 符合 |
| 标注 `text-xs` | 12px | 统计/按钮/时间 `text-xs` | 符合 |
| 输入框 `text-[11px] font-mono` | 11px mono | TranscriptRow:268 `text-[11px] font-mono` | 符合 |

> spec §6.4 明确"不改变正文字号（14px 已适用）"，当前实现符合此决策。

### 4.5 微动效（§7）

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 按钮 `scale(0.95)` 100ms | 按压缩放 | **仅 FileDropInput.vue:39 一处**；无全局 scale 动效 | **不符合** |
| 状态切换 bg 渐变 300ms | 过渡 | 部分 `transition-colors`，无统一 300ms | 部分符合 |
| 侧边栏 width 200ms | 展开/收起 | 用 transform `translate-x` 200ms（Timeline.vue:356），非 width | **不符合**（同 §1.3）|
| 按钮 hover bg 150ms | hover 过渡 | 用 `transition-colors` 但无 `duration-150` | **不符合** |

### 4.6 小结

全局视觉精炼核查中 **4 符合 / 3 部分符合 / 5 不符合**。配色和字体层级基本到位（v2.1.0 基础），但 §6.2/§7 要求的 `active:scale-95`、`duration-150` 等交互反馈统一几乎完全缺失。

---

## 5. 快捷键 + 设置页（§8-9）— 部分符合

### 5.1 快捷键实现现状（§8）

| 快捷键 | Spec 期望 | 实际实现（file:line）| 状态 |
|--------|----------|-------------------|------|
| `Space` | TranscriptRow 聚焦：从该行播放 | **WorkspacePage.vue:1395-1398** `handleTogglePlay()` | 符合 |
| `Shift+Space` | 全局：原片/剪后切换 | **WorkspacePage.vue:1390-1393** `previewMode toggle` | 符合 |
| `Delete` | TranscriptRow：标记删除 | **WorkspacePage.vue:1431-1435**（selectionMode 批量删除）；TranscriptRow 单行删除通过右键菜单 | 部分符合 |
| `Ctrl+Z` | 全局：撤销 | **WorkspacePage.vue:1405-1408** `handleUndo()` | 符合 |
| `Ctrl+S` | 全局：保存 | **WorkspacePage.vue:1400-1403** | 符合 |
| `Ctrl+F` | 编辑器：搜索替换 | **Timeline.vue:242** 仅 title 提示，**无 keydown handler** | **不符合** |
| `I` / `O` | 播放中：跳片段首/尾 | **未实现**（grep 零匹配）| **不符合** |
| `Up/Down`（非 input）| 编辑器：移动选中行 | 未实现全局上下移动（仅时间编辑 input 内步进）| **不符合** |
| `Up/Down`（input 聚焦）| ±0.1s（Shift ±1.0s）| **TranscriptRow.vue:141-153** 实现（但有 §6 Bug）| 部分符合 |
| `Shift+Click` | 编辑器：多选 | **TranscriptRow.vue:216-218** selectionMode 下处理 | 符合 |
| `Ctrl+Shift+A/D` | 建议面板：全确认/全忽略 | **未实现**（grep 零匹配）| **不符合** |

### 5.2 设置页快捷键 Tab（§9）— 完全缺失

§9 是 spec-6 的 P2 任务，要求在 SettingsModal 新增第 5 个 Tab。**完全未实施**。

| 要求 | Spec 期望 | 实际实现 | 状态 |
|------|----------|---------|------|
| 第 5 个 tab（id: `'shortcuts'`，label `'快捷键'`）| 新增 tab | **SettingsModal.vue 无 shortcuts tab**（只有 general/ai-engine/llm/export 四个）| **不符合** |
| `activeTab` 类型含 `'shortcuts'`| 类型扩展 | **SettingsModal.vue:67** `ref<"general" \| "ai-engine" \| "llm" \| "export">("general")` — 无 shortcuts | **不符合** |
| `<kbd>` 元素 + 指定样式 | `border-gray-300 bg-gray-50 ... font-mono` | **全前端 grep `<kbd` 零匹配** | **不符合** |
| 分组（播放/编辑/时间微调/建议面板）| 4 组分类 | 不存在 | **不符合** |

### 5.3 小结

快捷键 + 设置页核查中 **7 符合 / 1 部分符合 / 6 不符合**。已有快捷键多为 v2.1.0 基础能力；spec-6 新增的 Ctrl+F、I/O、Ctrl+Shift+A/D 全部缺失，设置页快捷键 Tab 完全未实施。

---

## 6. Bug 修正（§10）— 三个 P0 全部未修复

### 6.1 §10 拖拽误触 SRT — 未修复

**Spec 要求**：4 个拖拽处理器对非文件拖拽提前返回。

**实际实现**（`frontend/src/App.vue`）：

| 要求 | Spec 期望 | 实际 | 状态 |
|------|----------|------|------|
| `isFileDrag(e)` 辅助函数 | 检查 `dataTransfer.types.includes("Files")` | **不存在**（全前端 grep `isFileDrag` 零匹配）| **不符合** |
| dragenter 非文件提前返回 | `if (!isFileDrag(e)) return` | **App.vue:95** `handleWindowDragEnter` 无条件 `preventDefault + dragCounter++` | **不符合** |
| dragover 非文件提前返回 | 同上 | **App.vue:103** `handleWindowDragOver` 无条件 preventDefault | **不符合** |
| dragleave 非文件提前返回 | 同上 | **App.vue:107** 无条件 | **不符合** |
| drop 非文件提前返回 | 同上 | **App.vue:116** 无条件 | **不符合** |

**影响**：用户在字幕列表选中文字后拖动，仍会闪现蓝色"松开以导入 SRT"覆盖层。

### 6.2 §10.2 ArrowUp/Down 时间步进 — 未修复

**Spec 要求**：用 `editingTimeSeconds: ref<number>` 替代 `parseFloat(editingTimeValue)`。

**实际实现**（`TranscriptRow.vue`）：

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| `editingTimeSeconds: ref<number>` | 秒数 number 变量 | **TranscriptRow.vue:108** 仅 `editingTimeValue = ref("")`（字符串），**无 editingTimeSeconds** | **不符合** |
| 不用 `parseFloat(editingTimeValue)` | 避免解析 "MM:SS.mmm" | **:131, :145, :151** 三处仍用 `parseFloat(editingTimeValue.value)` | **不符合** |
| ArrowUp `+= step` 后 `formatTime()` | 格式化回写 | **:146** `(current + step).toFixed(1)` — 纯数字如 "1.1"，**无 formatTime** | **不符合** |
| ArrowDown `Math.max(0, ...)` | 防负值 | **:152** `(current - step).toFixed(1)` — **无 Math.max 保护** | **不符合** |

```typescript
// TranscriptRow.vue:130-134 — adjustTime 仍用 parseFloat
function adjustTime(delta: number) {
  const current = parseFloat(editingTimeValue.value) || 0  // ❌ "01:23.456" → 1
  editingTimeValue.value = (current + delta).toFixed(1)     // ❌ 无 formatTime
  applyTimeEdit()
}

// TranscriptRow.vue:141-153 — ArrowUp/Down 同样 parseFloat，无 Math.max
} else if (e.key === "ArrowUp") {
    const current = parseFloat(editingTimeValue.value) || 0
    editingTimeValue.value = (current + step).toFixed(1)    // ❌
} else if (e.key === "ArrowDown") {
    const current = parseFloat(editingTimeValue.value) || 0
    editingTimeValue.value = (current - step).toFixed(1)    // ❌ 无 Math.max(0, ...)
}
```

**Bug 复现路径**：`startTimeEdit`（:113）用 `formatTime()` 初始化 input 为 "01:23.456" → 用户按 ArrowUp → `parseFloat("01:23.456")` = 1（遇冒号停止）→ 显示 "1.1" → 原始 83.456s 被错改为 1.1s。

### 6.3 §10.3 字幕修正 NameError — 未修复

**Spec 要求**：调用 `store_subtitle_corrections(corrections, timeline_id)` 前定义 `timeline_id`。

**实际实现**（`main.py`）：

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| `_handle_subtitle_correction` 作用域定义 `timeline_id` | 补充变量定义 | **main.py:760** `timeline = self._get_target_timeline(task)` 只接收 timeline 对象；**main.py:819** 引用 `timeline_id` 但该变量从未在 `_handle_subtitle_correction` 作用域定义 | **不符合** |

**根因确认**：`_get_target_timeline`（main.py:361-368）内部 `timeline_id`（:364）是**局部变量**，`return timeline`（:368）只返回 timeline 对象，不返回 ID。因此 `_handle_subtitle_correction` 中（:760-819）`timeline_id` 未定义。

```python
# main.py:361-368 — timeline_id 是局部变量，不返回
def _get_target_timeline(self, task):
    ...
    timeline_id = task.payload.get("timeline_id", "") or project.active_timeline_id  # :364 局部
    timeline = project.get_timeline(timeline_id)
    if timeline is None:
        raise ValueError(...)
    return timeline  # :368 只返回对象，不返回 ID

# main.py:760, 819 — 调用方
def _handle_subtitle_correction(self, task, cancel_event, progress_cb):
    ...
    timeline = self._get_target_timeline(task)  # :760 无 timeline_id
    ...
    store_result = self._mark_dirty(
        self._project.store_subtitle_corrections(corrections, timeline_id)  # :819 NameError!
    )
```

**影响**：字幕修正执行完成后抛 `NameError: name 'timeline_id' is not defined`，修正结果无法存储，前端收不到 `llm:subtitle_correction_completed` 事件，**功能完全不可用**。

**完成 toast**：spec §10.3 额外要求修正完成 toast — **未实现**（:827 仅 emit 事件，无 toast）。

### 6.4 小结

三个 P0 Bug **全部未修复**。这是 spec-6 中最高优先级、最低风险的修复项（均为局部改动），却完全未动工。

---

## 7. 精华提取重构（§11）— 完全未实施

§11 是 spec-6 中规模最大的重构（P0×2 + P1×2），**6 项核查全部不符合，零进展**。

### 7.1 后端：移除 highlight EditDecision（§11.2）— 未实施

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| 不再创建 `EditDecision(action="keep", source="llm_highlight")`| 移除 edits 创建 | **main.py:888-908** 仍构建 `edits.append({... "action": "keep", "source": "llm_highlight" ...})` | **不符合** |
| `llm:highlight_completed` 不传 `edits` 字段 | 只传 results | **main.py:929-936** 事件仍含 `"edits": edits` | **不符合** |

### 7.2 后端：过滤已删除段落（§11.3）— 未实施

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| `_handle_highlight` 用 `collect_confirmed_deleted_seg_ids` 过滤 | 过滤 confirmed 删除段 | **main.py:848-852** 仅 `if s.type == SegmentType.SUBTITLE`，**无 collect_confirmed_deleted_seg_ids 调用** | **不符合** |

> 对比：`_handle_smart_delete`（:650）和 `_handle_subtitle_correction`（:767）**已正确使用**该 helper。highlight 是唯一漏网者。

### 7.3 后端：jump_cuts / get_highlight_ranges 适配（§11.2）— 未实施

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| `detect_highlight_jump_cuts` 从 AnalysisResult 读 | 新数据源 | **main.py:2427** 仍从 `timeline.edits` 读：`get_highlight_ranges([e.model_dump() for e in timeline.edits])` | **不符合** |
| `get_highlight_ranges` 从 AnalysisResult 读 | 新数据源 | **core/export_service.py:486-489** 仍检查 `edit.get("source","").startswith("llm_highlight")`（从 edits）| **不符合** |

### 7.4 前端：segmentHelpers 过滤（§11.2）— 未实施

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| `resolveSegmentState` 过滤 highlight edits | 排除 `source="llm_highlight"` | **segmentHelpers.ts:21-53** 无任何 source 过滤，处理所有 edits（导致 highlight 的 pending edit 污染字幕行状态）| **不符合** |

### 7.5 前端：HighlightModeView 重构（§11.4）— 未实施

| 要求 | Spec 期望 | 实际（file:line）| 状态 |
|------|----------|----------------|------|
| 密度圆点（8px green/yellow/gray）| 替代文字徽章 | **HighlightModeView.vue:211-216** 仍用 `rounded-full px-2 py-0.5 text-[10px]` 文字徽章"高/中/低密度" | **不符合** |
| 字幕原文 `segment.text`（truncate）| 显示原文 | **HighlightModeView.vue:220-222** 只显示 `highlight_reason`，**无 segment.text** | **不符合** |
| 右键"从精华中移除"菜单 | 可移除 | 全前端 grep "从精华中移除" 零匹配，**无右键菜单** | **不符合** |

### 7.6 前端：编辑能力（§11.5）— 未实施

| 要求 | Spec 期望 | 实际 | 状态 |
|------|----------|------|------|
| TranscriptRow 右键"加入精华" | 可添加 | **TranscriptRow.vue:400-443** 右键菜单只有编辑文本/标记删除/分割/删除段落，**无"加入精华"** | **不符合** |
| 后端 API `add_highlight_segment` | 新增 API | 全项目 grep 零匹配（仅 spec 文档出现）| **不符合** |
| 波形 highlight 色块拖拽 | 可微调时间 | 未实现 | **不符合** |

### 7.7 小结

精华提取重构 6 项**全部不符合**。这是 spec-6 中最严重的功能性问题——highlight EditDecision 污染导致"字幕列表黄色段落数 ≠ SuggestionPanel 待处理数"，且 LLM 收到已确认删除的垃圾数据。基础设施（`collect_confirmed_deleted_seg_ids`）已就绪，但 highlight 链路完全未接入。

---

## 8. 问题汇总与实施建议

### 8.1 问题分布

| 类别 | 符合 | 部分 | 不符合 | 符合率 |
|------|------|------|--------|--------|
| 侧边栏内联化（§1-2）| 2 | 1 | 4 | 29% |
| 核心组件（§3-5）| 9 | 8 | 11 | 32% |
| 导出摘要弹窗（§4）| 3 | 0 | 2 | 60% |
| 全局视觉精炼（§6-7）| 4 | 3 | 5 | 33% |
| 快捷键 + 设置页（§8-9）| 7 | 1 | 6 | 50% |
| Bug 修正（§10，P0）| 0 | 0 | **3** | **0%** |
| 精华提取重构（§11）| 0 | 0 | **6** | **0%** |
| **合计** | **25** | **13** | **37** | **34%** |

### 8.2 P0 问题清单（最高优先级，共 8 项）

按性质分为两类（详见 §0 缺陷分类说明）：**A 类 = 现有系统代码缺陷**，验收以回归测试为主；**B 类 = Spec 规定的核心功能重构**，验收以视觉与交互为准。

| ID | 类别 | 性质 | 问题 | 位置 | 修复难度 |
|----|------|------|------|------|---------|
| P0-1 | §10 拖拽 Bug | A 缺陷 | 文字拖拽误触 SRT 导入覆盖层 | App.vue:95-161 | 低（加 isFileDrag guard）|
| P0-2 | §10.2 步进 Bug | A 缺陷 | ArrowUp/Down `parseFloat` 导致时间错乱 | TranscriptRow.vue:108,131,141-153 | 低（换 editingTimeSeconds ref）|
| P0-3 | §10.3 NameError | A 缺陷⚠️**阻断** | 字幕修正 `timeline_id` 未定义，功能崩溃 | main.py:819 | 低（补一行变量定义）|
| P0-4 | §11.2 污染 | A 缺陷 | highlight EditDecision 污染字幕行状态 | main.py:888-908, segmentHelpers.ts:21-53 | 中（移除 edits + 适配 jump_cuts）|
| P0-5 | §11.3 过滤 | A 缺陷 | highlight 后端未过滤已删除段落 | main.py:848-852 | 低（加一行 helper 调用）|
| P0-6 | §1-2 侧边栏 | B 重构 | 侧边栏未内联化，仍为浮动覆盖层 | Timeline.vue:354-460 | 中（布局重构）|
| P0-7 | §3.1.1 时间列 | B 重构 | TranscriptRow ±按钮未移除 | TranscriptRow.vue:260-303 | 低（删模板 + 改编辑逻辑）|
| P0-8 | §10.2 关联 | A 缺陷 | 时间编辑无 formatTime 回写 + 无 Math.max 防负 | TranscriptRow.vue:146,152 | 低（随 P0-2 一并修）|

> P0-3 为阻断性缺陷，建议作为独立 Hotfix 提前处理，不必与 spec-6 其他任务绑定同一发布。

### 8.3 实施顺序建议

依据 spec §12 优先级 + 依赖关系，建议按以下顺序实施。**每批均应附带对应测试**（见各批末尾的测试要求），防止缺陷复发——Bug 修复看重回归测试，重构看重视觉与交互验收。

**第零批：Hotfix 阻断缺陷（0.5 天，独立提审）**
- P0-3 NameError（main.py:819 补 `timeline_id = task.payload.get("timeline_id", "") or self._project.current.active_timeline_id`）
- 测试要求：后端单测 mock `_handle_subtitle_correction` 全流程，断言不抛 NameError 且正确调用 `store_subtitle_corrections(corrections, <正确 timeline_id>)`；补充事件发射断言。

**第一批：低风险 P0 Bug（1-2 天）**
1. P0-1 拖拽 guard（App.vue 加 isFileDrag + 4 处 early return）
2. P0-2/P0-8 步进修复（TranscriptRow.vue 引入 editingTimeSeconds ref）
3. P0-7 时间列 ±按钮移除（与 P0-2 同文件，一并改）
- 测试要求：
  - P0-1：为 `isFileDrag` 编写单测，模拟 `dataTransfer.types` 含/不含 `"Files"`、空 types、null dataTransfer 等边界值；集成测试验证文字拖拽不再触发 `isDragging=true`。
  - P0-2/P0-8：为时间步进编写边界值测试——初始值 `"01:23.456"` 按 ArrowUp 应得到 `83.556s`（非 `1.1`），ArrowDown 到 0 后不应变负（验证 `Math.max(0, ...)`），Shift+Arrow 步长 1.0s，手动输入 `"MM:SS.mmm"` 与纯秒数均能被 `parseTime` 正确解析。

**第二批：精华功能后端修复（1-2 天）**
5. P0-5 过滤已删除段落（main.py:848 加 helper，复用现有 collect_confirmed_deleted_seg_ids）
6. P0-4 移除 EditDecision 创建 + 适配 detect_highlight_jump_cuts / get_highlight_ranges + segmentHelpers 过滤
- 测试要求：
  - P0-5：单测构造含 confirmed/pending/rejected 删除段的 timeline，断言传给 LLM 的 segments 不含 confirmed 删除段、仍含 pending 段。
  - P0-4：单测验证 `_handle_highlight` 不再生成 `source="llm_highlight"` 的 EditDecision；`resolveSegmentState` 对仅含 highlight edit 的 segment 返回 neutral 状态（不显黄）；`detect_highlight_jump_cuts` 从 AnalysisResult 正确推导范围（含跨多 segment、空 segment_ids 兜底）。

**第三批：侧边栏内联化（2-3 天）**
7. P0-6 侧边栏内联化重构（Timeline.vue 布局重构，移除 Teleport/fixed，改 flex 子元素 + width 过渡）
- 验收要求（视觉与交互）：侧边栏展开时挤压字幕列表宽度且视频区宽度不变；`transition: width 200ms ease-out` 平滑过渡；收起后 `v-if` 完全移除、字幕列表填满；分隔条 `w-px` + 透明 hit area；主标题栏左右分区（Timeline 工具 + 侧边栏 Tab 同行）。回归测试验证 `sidebarWidth` 持久化、resize 拖拽、window resize clamp。

**第四批：P1/P2 视觉精炼 + 功能补全（3-5 天）**
8. 标题栏分区、间距统一、active:scale-95、duration-150
9. HighlightModeView 圆点+原文+右键菜单、编辑能力
10. 设置页快捷键 Tab、缺失快捷键（Ctrl+F、I/O、Ctrl+Shift+A/D）
- 测试要求：P1 精华编辑能力需补全右键菜单交互测试（删除/添加 AnalysisResult 后前端 `highlightResults` 同步）；快捷键新增项需 keydown handler 单测。视觉精炼项以人工验收 + 截图对比为主。

### 8.4 关键观察

1. **基础设施已就绪**：`collect_confirmed_deleted_seg_ids`（core/timeline_utils.py）已被 smart_delete 和 subtitle_correction 正确使用，highlight 只需接入即可，无需新建工具函数。
2. **Bug 修复零成本**：三个 P0 Bug 均为局部改动（补变量、加 guard、换 ref 类型），不涉及架构变更，可在半天内全部修复。
3. **侧边栏是最大工作量**：从浮动覆盖层改为 flex 子元素需要重构 Timeline.vue 的布局结构，并同步处理 width 过渡动画、标题栏分区、分隔条样式，是 spec-6 中风险最高的任务。
4. **符合项多为存量**：25 项"符合"中，绝大多数（配色、字体、SuggestionPanel、WaveformEditor 基础、已有快捷键）是 v2.1.0 及之前已实现的能力，非 spec-6 新增工作。

---

## 附录：审计方法说明

- **审计基线**：当前工作树（dev 分支），未开始 spec-6 实施
- **证据来源**：直接 grep + read_file 源码，所有结论附 file:line
- **验证方式**：关键发现（NameError、parseFloat bug、Teleport 仍存在）经人工二次 read_file 确认
- **子代理**：两个探索子代理（sa_20260625_025113、sa_20260625_025327）分别覆盖 §1-5 和 §4,6-12

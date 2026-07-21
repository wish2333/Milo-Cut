# Milo-Cut v2.4.0 UI 审计报告

> **版本**：v2.4.0（设计与 UI 优化）  
> **日期**：2026-07-21  
> **基线**：v2.3.2  
> **范围**：Welcome、Workspace、Export 三个前端页面及其共享视觉基础  
> **结论类型**：代码审计 + 设计规范对照；未进行浏览器截图或真实性能测量

## 1. Executive Summary

Milo-Cut 当前并不是缺少功能，而是视觉语言没有完全收敛。仓库已有 Apple Edition 设计规范和基础 token，但页面实现仍混用 Tailwind 原始灰阶、DaisyUI 语义色和多种业务色，导致产品更像多个工具面板的组合，而不是一个完整的专业视频工作台。

本版建议采用“深色视频舞台 + 白色字幕画布 + 纸张色分析面板”的三层视觉结构，保留 Action Blue 作为唯一主要交互色；状态色只承担“待确认 / 删除 / 保留”的语义，不承担按钮层级。

本轮 P0 优化不改变后端、数据模型或交互协议，重点是：

1. 将原始颜色、圆角、字体和边框规则收敛到共享 token。
2. 统一 Workspace 的视频区、字幕区、波形区层级，减少卡片化边框。
3. 让字幕行成为视觉主角，明确播放中、选中、编辑中和分析状态。
4. 简化 Export 的操作层级，消除绿色、蓝色、紫色、靛蓝并存造成的视觉竞争。
5. 补齐焦点、加载、空状态、错误状态和中文操作文案。

## 2. 审计依据

### 2.1 规范与实现

| 来源 | 观察 |
|---|---|
| `docs/design-spec.md` | 已定义 Canvas、Parchment、Near-Black、Action Blue、状态色和边缘对齐原则 |
| `frontend/src/style.css` | 已有 `--color-*` 和 Apple 字体/圆角 token，但组件未完全使用 |
| `WelcomePage.vue` | 主体视觉较克制，但最近项目仍使用 `gray-*` 原始色 |
| `WorkspacePage.vue` | 视频区、时间线和底部波形结构合理，但时间线仍是 `rounded-lg + border` 卡片 |
| `ExportPage.vue` | 三栏结构清晰，但主操作颜色和按钮样式不一致 |
| `TranscriptRow.vue` / `SuggestionPanel.vue` | 已具备文本编辑和分析建议基础，需强化状态层级与选中反馈 |

### 2.2 当前不一致清单

| 问题 | 证据 | 影响 | 优先级 |
|---|---|---|---:|
| 颜色系统分裂 | Export 使用 green / blue / purple / indigo；Workspace 使用 gray / red / orange / green | 用户无法快速判断主要操作 | P0 |
| token 未成为唯一入口 | `style.css` 已定义 `primary/canvas/parchment/ink`，页面仍大量使用 `gray-*` | 主题和后续维护成本上升 | P0 |
| 容器过度卡片化 | Workspace 时间线使用 `rounded-lg border bg-white` | 破坏“边缘对齐”工作台感 | P0 |
| 圆角规则混用 | `rounded`、`rounded-md`、`rounded-lg`、`rounded-2xl`、pill 并存 | 视觉节奏不稳定 | P0 |
| 文字规范不一致 | 规范要求 400 / 600，代码大量使用 `font-medium`；存在中英文混杂 loading 文案 | 产品完成度下降 | P1 |
| 状态反馈不够集中 | 状态色分散在行、按钮、提示和波形中 | 分析建议与操作行为容易混淆 | P1 |
| 专业交互状态不完整 | 未形成统一 `focus-visible`、empty、loading、error 规则 | 键盘和异常场景体验不足 | P1 |

## 3. 用户与工作流影响

### 3.1 导入阶段

当前导入页能完成拖拽和最近项目打开，但视觉重点只停留在“选择文件”，没有明确告诉用户 Milo-Cut 的核心价值。建议增加轻量能力说明，不增加营销装饰。

### 3.2 编辑阶段

编辑阶段是产品核心。视频预览、字幕文本、静音片段、分析建议和波形应被理解为同一条时间轴上的不同观察层。当前右侧时间线被包在独立圆角卡片中，用户会感知到“视频”和“编辑器”是两个模块，而不是同一个工作台。

### 3.3 导出阶段

导出页功能完整，但多个高饱和按钮同时出现，导致“导出视频”和“导出字幕”等操作没有明确层级。建议把“最终交付”作为唯一主任务，其他格式作为次级选项。

## 4. v2.4.0 设计方向

```text
深色视频舞台  ->  用户观看和定位
白色字幕画布  ->  用户阅读和编辑
浅纸色分析面板 -> 用户判断和确认
底部波形时间轴 -> 用户调整时间范围
Action Blue    -> 用户当前可以执行的主要动作
```

这是一套“编辑优先”的工作台，不追求装饰性的玻璃、渐变或阴影。视觉高级感来自留白、对齐、稳定的类型比例和明确的状态色。

## 5. 优化范围与非目标

### 本版范围

- 共享 CSS token 和基础控件状态
- WelcomePage 的导入与最近项目视觉层级
- WorkspacePage 的工作台容器、视频/字幕/波形层级
- TranscriptRow 和 SuggestionPanel 的状态表现
- ExportPage 的按钮层级和导出摘要视觉
- 统一中文文案、focus-visible、empty/loading/error 状态

### 本版非目标

- 不修改 Python backend、Project、ProjectPatch 或 TaskManager
- 不改变现有 bridge API 和事件协议
- 不重做视频播放逻辑、波形算法或导出逻辑
- 不引入新的 UI 组件库
- 不在没有截图或性能基线的情况下进行大范围布局重构

## 6. 验收标准

1. 页面业务操作不再直接使用未纳入设计 token 的主要颜色。
2. Export 页面最多有一个主色按钮体系，危险操作才使用红色。
3. Workspace 的视频、字幕、波形三个区域能够通过背景和对齐关系区分，不依赖外层圆角卡片。
4. 字幕行具备默认、hover、selected、playhead、editing、pending、confirmed、rejected 状态。
5. 所有可操作元素存在可见的 `focus-visible` 状态。
6. loading、empty、error 状态不出现中英文混杂的默认文案。
7. `cd frontend && bun run build` 通过，现有前端测试不回归。
8. 不修改 `docs/demo/` 等已有用户未跟踪文件。


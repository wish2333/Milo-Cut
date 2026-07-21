# Netlify 浏览器 Demo Implementation Plan（v2.4.0 UI 基线）

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 以 Milo-Cut v2.4.0 已收敛的 UI 设计系统为视觉基线，增加一个不依赖 Python、FFmpeg、真实媒体文件或外部 API 的浏览器演示模式，并将其部署到 Netlify，展示核心编辑、AI 建议、冲突解决和导出流程。

**Architecture:** 保留当前桌面版 pywebview bridge 作为默认运行时，新增一个由 `VITE_DEMO_MODE` 控制的浏览器 Demo runtime。Demo runtime 使用单一内存状态仓库和确定性的任务模拟器，复用现有 Workspace、Timeline、Suggestion、AI、Conflict Resolution 和 Export 页面；媒体预览与波形改为纯 DOM/Canvas 的轻量模拟，不提交 `demo.mp4`、音频、图片或波形 JSON 等大资源。所有 Demo UI 必须复用 v2.4.0 的 Canvas、Parchment、Video Surface、Action Blue、状态色和 `mc-button-*` 语义，不另起一套视觉系统。

**Tech Stack:** Vue 3, TypeScript, Vite, Tailwind CSS 4, Vitest, Bun, Netlify Static Hosting

---

## 1. 审议结论摘要

### 1.0 版本基线变化

本计划原先以 v2.3.2 前端结构为背景；现在应以 v2.4.0 的以下成果为前置条件：

- `docs/2.4.0/ui-design-standard-2.4.0.md` 已定义颜色、字体、间距、圆角、按钮、状态和可访问性标准。
- `frontend/src/style.css` 已提供 `primary-hover`、`primary-soft`、`surface-tile-1`、状态 token、`mc-button-primary/secondary/quiet/danger` 和全局 `:focus-visible`。
- Workspace 已形成“深色视频舞台 + 白色字幕画布 + Parchment 分析面板 + 底部波形”的视觉结构。
- v2.4.0 已验证前端测试和生产构建通过（241 tests、19 test files）。

因此 Demo 不应新增普通 Tailwind 原始主色、装饰性大圆角、独立阴影体系或绿色/紫色/靛蓝主按钮。Demo 需要做的是把模拟状态接入这套视觉系统。

### 1.1 推荐方案

采用“同一套页面 + 双 bridge runtime”方案：

```text
                         ┌──────────────────────┐
                         │  Existing Desktop UI │
                         │  App / Workspace     │
                         └──────────┬───────────┘
                                    │ call(method, args)
                       ┌────────────┴────────────┐
                       │                         │
              pywebview runtime          browser demo runtime
              window.pywebview.api       demoStore + demoBridge
                       │                         │
                Python / FFmpeg              in-memory fixture
```

桌面版不进入 Demo 分支；Netlify 构建时设置 `VITE_DEMO_MODE=true`，只在浏览器构建中启用 mock bridge 和演示数据。

### 1.2 可以完全不提交大媒体资源

可以，而且建议初版明确不提交以下文件：

- `demo.mp4`
- `demo.webm`
- `demo.wav` / `demo.mp3`
- `waveform.json`
- 任何外部视频 CDN 链接

替代方案：

1. 左侧视频区域使用纯 CSS/DOM 的“模拟媒体画面”，显示演示标题、时间码、当前字幕和删除区域。
2. 播放、暂停、快进、拖动时间轴只改变内存中的 `currentTime`，通过 `requestAnimationFrame` 模拟播放。
3. 波形由 Canvas 根据固定 seed 在浏览器内即时绘制，数据不经过网络请求。
4. 视觉上明确标注“浏览器演示模式｜媒体画面为模拟预览”，避免用户误以为正在播放真实视频。

这样 Netlify 只需加载 JS/CSS/HTML，首屏不会等待媒体文件，也不会因为视频流量消耗免费额度。

### 1.3 Demo 的边界

Demo 目标是展示产品交互和决策流程，不承诺真实媒体处理能力。

#### 初版演示功能

- 预加载一个完整示例项目
- 浏览时间轴和字幕片段
- 移动模拟播放头
- 编辑字幕文本
- 查看、确认、驳回智能删除建议
- 查看、接受、驳回字幕纠错
- 启动模拟 AI 工作流
- 展示一个确定性的工作流冲突
- 通过三种按钮解决冲突
- 打开导出页并模拟导出成功
- 重置整个演示状态

#### 初版不做真实功能

- 上传本地视频
- 读取本地文件
- ASR 转录
- 真实 LLM 请求
- FFmpeg 编码
- 真实视频/音频导出
- 代理视频生成
- 真实波形生成
- 项目持久化
- 最近项目列表的真实读写

这些入口应在 Demo 中禁用、隐藏，或显示“桌面版可用”，不应返回容易让用户误判的成功状态。

---

## 2. 现有代码调查与改造边界

### 2.1 已验证可复用部分

- `frontend/src/pages/WorkspacePage.vue` 已经包含视频区、时间轴、波形区、AI 面板和任务反馈。
- `frontend/src/components/workspace/Timeline.vue` 已经处理字幕、建议、时间轴交互。
- `frontend/src/components/workspace/SuggestionPanel.vue` 已经处理建议分组、确认、驳回和批量操作。
- `frontend/src/components/workspace/ConflictResolutionView.vue` 已经有冲突展示和三种解决动作。
- `frontend/src/pages/ExportPage.vue` 已经有导出摘要和格式设置页面。
- `frontend/src/types/project.ts` 已经定义 `Project`、`Segment`、`EditDecision`、`AnalysisResult` 等 Demo 所需模型。
- `frontend/src/test/helpers/mockProject.ts` 可以作为测试 fixture 的字段参考。

### 2.2 v2.4.0 视觉复用边界

Demo 接入后，页面仍必须遵守 `docs/2.4.0/ui-design-standard-2.4.0.md`：

- 模拟媒体画面使用 `surface-tile-1`，不创建新的深色或渐变主题。
- 字幕与时间轴内容使用 Canvas/白色内容层，避免额外的 `border + rounded-lg` 外层卡片。
- AI、建议和空状态区域使用 Parchment 或既有语义 token。
- 主操作只使用 Action Blue 或 `mc-button-primary`；次要操作使用 `mc-button-secondary` / `mc-button-quiet`。
- 删除、待确认、保留只使用既有 `status-*` 语义，不把状态色用作普通按钮层级。
- Demo 标签、模拟导出提示、任务进度和冲突反馈需要有 `focus-visible`、loading、success、error 状态。
- 新增文案统一使用中文，并明确“模拟”“演示模式”“不生成文件”等边界。
- 模拟播放应遵守 `prefers-reduced-motion`，减少动画时应仍能看见当前时间和播放状态。

本计划不顺带完成 2.4.0 记录中列出的设置弹层、字幕修正全屏页和右键菜单的全部历史 Tailwind 清理；如 Demo 直接触达这些区域，只能复用已有 token，不扩张成新的 UI 重构任务。

### 2.3 当前阻塞点

1. `frontend/src/main.ts` 会等待 pywebview bridge。
2. `frontend/src/App.vue` 会再次等待 `window.__BRIDGE_READY__`。
3. `frontend/src/bridge.ts` 当前只能调用 `window.pywebview.api`。
4. `WorkspacePage.vue` 初始化时会请求视频 URL、波形 URL、设置、插件、模型和 LLM 配置。
5. AI、工作流、导出 composable 都假设 bridge 返回任务和事件。
6. `SubtitleOverlay.vue` 依赖真实 `<video>` 元素，不适合直接挂到无视频资源的 Demo。

改造原则是只在这些边界增加 Demo 分支，不修改 Python 后端协议，不把 Demo 逻辑散落到每个按钮处理函数中。

---

## 3. 目标数据模型

### 3.1 示例项目

新增 `frontend/src/demo/demoProject.ts`，提供确定性的 `Project`：

- 项目名称：`Milo-Cut 产品演示`
- 媒体时长：约 90 秒
- `media.path` 使用占位字符串，例如 `demo://sample-media`
- `media.width` / `height` / `fps` 填充正常视频元数据
- 8～12 个字幕片段
- 3～5 个静音片段
- 3 个待确认的智能删除建议
- 2 个待审字幕纠错
- 2～3 个精华候选片段
- 至少一个片段同时被两个工作流步骤引用，用于制造可解释冲突

示例数据必须满足：

- 所有 `EditDecision.target_id` 都引用真实 segment。
- 所有时间范围都在 `[0, media.duration]` 内。
- `segments` 按 `start` 升序排列。
- 删除建议、字幕纠错和精华结果之间的关联是稳定的。
- 每次刷新页面得到完全相同的数据，便于产品评审和截图。

### 3.2 单一状态仓库

新增 `frontend/src/demo/demoStore.ts`，集中维护：

```ts
interface DemoState {
  project: Project
  currentTime: number
  isPlaying: boolean
  playbackRate: number
  activeTask: DemoTask | null
  corrections: DemoCorrection[]
  workflows: DemoWorkflow[]
  workflowSession: DemoWorkflowSession | null
  exportHistory: DemoExportRecord[]
  revision: number
}
```

要求：

- 对外提供只读 computed 状态和明确的 mutation 方法。
- mutation 使用深拷贝或结构化 clone，避免直接修改 fixture 常量。
- 每次项目状态写入都递增 `revision`。
- `get_edit_summary`、待审数量、删除时长等均从当前 Project 派生，不重复存储。
- `reset()` 返回初始 fixture 的全新副本。

---

## 4. 媒体与波形的无文件方案

### 4.1 模拟媒体画面

新增 `frontend/src/components/demo/DemoPreviewSurface.vue`。

组件职责：

- 接收 `segments`、`currentTime`、`duration`、`previewMode`、`deleteRanges`。
- 使用 v2.4.0 的 `surface-tile-1`、既有字体和 Action Blue 语义绘制静态视觉画面；允许使用低对比度内部纹理，但不引入新的品牌色。
- 根据 `currentTime` 找到当前字幕并显示在画面底部。
- 根据 `previewMode` 显示“原始预览”或“已编辑预览”。
- 在删除区间显示半透明标识。
- 不创建 `<video>`，不请求网络，不读取本地文件。
- 通过 `requestAnimationFrame` 或统一 playback composable 实现模拟播放。
- 提供 `aria-label`、键盘 focus 和 reduced-motion 兼容状态。

`WorkspacePage.vue` 在 Demo 模式中渲染该组件，桌面模式继续渲染现有 `<video>` 和 `SubtitleOverlay`。

### 4.2 模拟播放控制

新增 `frontend/src/composables/useDemoPlayback.ts`。

行为：

- `play()`：以当前 playback rate 推进 `currentTime`。
- `pause()`：停止动画帧。
- `seek(time)`：限制到 `[0, duration]`。
- 到达结尾自动暂停并回到稳定的结束状态。
- `togglePreviewMode()` 只影响视觉和删除区间，不修改 Project。
- 页面卸载时取消 `requestAnimationFrame`。

现有 `VideoControls.vue` 已经以 props + emits 为主，因此继续复用，不需要绑定真实 `<video>`。

### 4.3 Canvas 波形

修改 `frontend/src/components/waveform/WaveformCanvas.vue`，增加 Demo 输入，例如：

```ts
defineProps<{
  segments: Segment[]
  waveformPath?: string
  duration?: number
  demoMode?: boolean
}>()
```

在 `demoMode` 下：

- 不执行 `fetch()`。
- 根据固定 seed 生成有限数量的峰值数据。
- 使用现有 Canvas 绘制逻辑绘制波形。
- 波形静音区使用已有状态语义和半透明处理，不新增高饱和色或外层装饰卡片。
- 即使 Canvas 不可用，也保留现有 flat-line fallback。

在桌面模式下保持现有 `waveformPath` JSON 加载流程不变。

---

## 5. Demo Bridge 设计

### 5.1 Bridge 选择

修改 `frontend/src/bridge.ts`，将当前 bridge 拆成两个实现：

```ts
export function isDemoMode(): boolean
export async function call<T>(method: string, ...args: unknown[]): Promise<ApiResponse<T>>
export function onEvent<T>(name: string, handler: (detail: T) => void): () => void
```

实现策略：

- Demo 模式：调用 `demoBridge.call()`。
- 桌面模式：继续调用 `window.pywebview.api`。
- `onEvent()` 在 Demo 模式使用同一套 `CustomEvent("pywebvue:...")` 机制，确保现有 composable 无需知道运行时差异。
- 不在组件中直接判断 `window.pywebview`，避免 Demo 分支扩散。

### 5.2 必须支持的 Demo 方法

| 方法 | Demo 行为 |
|---|---|
| `get_app_info` | 返回 Demo 版本标识 |
| `get_recent_projects` | 返回空数组或单个演示项目入口 |
| `get_settings` | 返回只读演示设置 |
| `list_plugins` | 返回一个“模拟已安装引擎” |
| `list_models` | 返回一个“模拟模型” |
| `get_llm_config` | 返回已配置的 Demo LLM 状态 |
| `get_video_url` | 不调用；Demo 页面使用 `DemoPreviewSurface` |
| `get_waveform_url` | 不调用；Demo Canvas 本地生成 |
| `get_project` | 返回当前 Project |
| `update_segment` | 更新 segment 的时间字段 |
| `update_segment_text` | 更新字幕文本 |
| `update_edit_decision` | 更新指定 edit 的 status |
| `update_edit_decisions_batch` | 批量更新 edit status |
| `mark_segments` | 创建或更新删除建议 |
| `get_edit_summary` | 从当前 Project 计算摘要 |
| `get_subtitle_corrections` | 返回当前待审纠错 |
| `accept_correction` | 更新文本并移除该纠错 |
| `reject_correction` | 只移除该纠错 |
| `accept_high_confidence_corrections` | 批量接受高置信度纠错 |
| `clear_subtitle_corrections` | 清空待审纠错 |
| `create_task` | 创建内存任务 |
| `start_task` | 启动确定性的模拟任务和事件序列 |
| `cancel_task` | 取消当前任务并发出取消事件 |
| `get_task` / `list_tasks` | 返回内存任务状态 |
| `start_smart_delete` | 模拟智能删除结果 |
| `start_subtitle_correction` | 模拟字幕纠错结果 |
| `start_highlight` | 模拟精华结果 |
| `detect_highlight_jump_cuts` | 返回固定跳剪数据 |
| `get_workflows` | 返回一个预置工作流 |
| `save_workflow` | 保存到内存，不持久化 |
| `delete_workflow` | 从内存删除 |
| `start_workflow` | 启动工作流模拟 |
| `cancel_workflow` | 结束当前工作流模拟 |
| `detect_workflow_conflicts` | 返回固定冲突 |
| `resolve_workflow_conflict` | 将冲突标记为已解决 |
| `apply_workflow` / `discard_workflow` | 收敛或重置工作流结果 |
| 导出相关方法 | 显示模拟成功，不创建真实媒体文件 |

对未纳入 Demo 范围的方法，不应静默执行危险动作。统一返回：

```ts
{ success: false, error: "该功能仅在桌面版可用" }
```

### 5.3 任务模拟器

新增 `frontend/src/demo/demoTaskRunner.ts`，统一处理所有异步演示任务：

- 每次任务分配唯一 `taskId` 和 `runId`。
- 同一时间只允许一个后台演示任务。
- 新任务启动时取消旧任务，或者由 UI 明确拒绝启动。
- 按固定步骤发出 `task:progress`、LLM progress 和 workflow progress 事件。
- 任务完成时一次性写入项目结果，再发出 `task:completed`。
- 旧任务回调检查 `runId`，不匹配则丢弃。
- 取消时清理所有 timer 和 animation frame。

推荐模拟时间：

- 普通按钮反馈：300～600ms
- AI 分析：1.2～2.0s
- 工作流：每一步 700～1000ms
- 导出成功提示：500ms

Demo 不应使用真实网络请求，因此这些延迟只用于展示进度，不代表真实性能。

---

## 6. 功能演示流程

### 场景 A：预加载与时间轴浏览

1. 浏览器打开即显示 Demo 项目，不经过 WelcomePage 的文件选择流程。
2. 顶部展示“浏览器演示模式”标签。
3. 左侧显示模拟媒体画面，底部显示生成式 Canvas 波形。
4. 点击时间轴片段，模拟播放头跳转。
5. 修改字幕文本后，Project revision 增加，时间轴和字幕叠加层同步更新。

### 场景 B：智能删除建议

1. 初始项目已经有少量静音建议，便于用户立即看到建议面板。
2. 点击“智能删除”后显示进度。
3. 任务完成后加入固定的 `llm_smart` edits。
4. 点击确认/驳回只改变对应 edit 状态。
5. 导出摘要随确认状态实时变化。

### 场景 C：字幕纠错

1. 点击字幕纠错后显示模拟进度。
2. 任务完成后显示待审纠错入口。
3. 接受纠错：更新 segment.text、删除待审纠错。
4. 驳回纠错：保留原文、删除待审纠错。
5. 批量接受高置信度纠错只处理 `confidence >= 0.8` 的项目。

### 场景 D：工作流与冲突解决

预置工作流：

```text
P0 智能删除 -> P1 字幕修正 -> P2 精华提取
```

固定冲突：

- P0 对同一 segment 给出 `delete`。
- P2 将同一 segment 纳入精华，等价于 `keep`。

冲突解决行为：

- “保留删除”：最终删除 edit 为 confirmed，精华结果移除。
- “保留精华”：最终删除 edit 为 rejected，精华结果保留。
- “两者都保留”：保留两个结果，但导出摘要必须明确说明该片段不会被自动删除，避免状态含义不清。

解决完毕后，ConflictResolutionView 关闭，Workspace 的建议、精华标记和导出摘要都来自同一 Project 状态。

### 场景 E：模拟导出

1. 进入 ExportPage。
2. 展示当前确认删除时长和导出摘要。
3. 点击任意导出按钮。
4. 运行一个短暂的模拟任务。
5. 显示“演示导出完成”，不生成文件、不触发浏览器大文件下载。

可以额外提供一个很小的 `.txt` 结果下载，内容仅包含导出摘要；该文件不是必要功能，默认建议先不做。

---

## 7. 页面启动与运行时隔离

### 7.1 启动逻辑

修改 `frontend/src/main.ts` 和 `frontend/src/App.vue`：

- `VITE_DEMO_MODE=true` 时直接挂载 App，不等待 pywebview。
- App 初始化时加载 `demoStore.reset()` 的 Project。
- 桌面模式继续等待 `window.pywebview.api` 和 `window.__BRIDGE_READY__`。
- Demo 模式不显示“正在连接后端”或 Bridge Error。
- Demo 模式的初始化、重置和任务反馈使用 v2.4.0 的状态 token 和中文文案，不使用技术性英文 loading 文案。

### 7.2 WelcomePage 行为

Demo 模式建议不显示真实文件输入，改为：

- 直接进入示例项目，或
- 显示一个“打开演示项目”按钮。

不要在 Demo 模式里调用 `probe_media`、`create_project`、`select_files`。

### 7.3 重置入口

新增 Demo 控制条或设置入口：

- “重置演示”恢复初始 Project。
- 清理所有任务、冲突、纠错审阅状态和导出状态。
- 重新定位播放头到 0 秒。
- 不刷新页面即可恢复完整演示路径。

---

## 8. Netlify 构建配置

新增根目录 `netlify.toml`：

```toml
[build]
command = "cd frontend && bun install --frozen-lockfile && bun run build"
publish = "frontend_dist"

[build.environment]
VITE_DEMO_MODE = "true"
BUN_VERSION = "1.3.10"

[[redirects]]
from = "/*"
to = "/index.html"
status = 200
```

说明：

- 当前 `frontend/vite.config.ts` 的构建输出是仓库根目录 `frontend_dist/`，因此 publish 目录应保持为 `frontend_dist`。
- 如果后续改成 Netlify 独立前端构建目录，可以再将输出改为 `frontend/dist`，但不属于本次 Demo 必需变更。
- 当前应用没有 Vue Router，SPA fallback 不是首要依赖，但保留配置可以避免未来增加 URL 路由后出现刷新 404。
- 不应把 `data/`、`frontend_dist/` 或 `node_modules/` 提交到 Git。

---

## 9. 文件变更清单

### 9.1 新增文件

- `docs/demo/plan.md`：本待审议计划。
- `frontend/src/demo/demoProject.ts`：固定演示 Project 和辅助 fixture。
- `frontend/src/demo/demoStore.ts`：单一 Demo 状态仓库。
- `frontend/src/demo/demoBridge.ts`：浏览器版 bridge API。
- `frontend/src/demo/demoTaskRunner.ts`：任务、进度、取消和 runId 管理。
- `frontend/src/demo/demoPlayback.ts`：模拟播放状态与时间推进。
- `frontend/src/components/demo/DemoPreviewSurface.vue`：无媒体文件的模拟预览。
- `frontend/src/demo/demoStore.test.ts`：Project mutation、revision、reset、冲突收敛测试。
- `frontend/src/demo/demoBridge.test.ts`：API envelope、任务事件和旧 run 丢弃测试。
- `frontend/src/components/demo/DemoPreviewSurface.test.ts`：字幕、播放头、删除区间显示测试。
- `netlify.toml`：Netlify 构建与 SPA fallback 配置。

### 9.2 修改文件

- `frontend/src/bridge.ts`：增加 Demo runtime 路由。
- `frontend/src/main.ts`：Demo 模式跳过 pywebview 初始化等待。
- `frontend/src/App.vue`：Demo 模式加载初始 Project、显示重置入口。
- `frontend/src/pages/WelcomePage.vue`：Demo 模式绕过文件选择。
- `frontend/src/pages/WorkspacePage.vue`：接入模拟预览、模拟播放和 Demo 波形开关。
- `frontend/src/components/waveform/WaveformCanvas.vue`：支持本地确定性 Canvas 波形。
- `frontend/src/components/workspace/ConflictResolutionView.vue`：必要时补充 Demo 冲突完成态和按钮反馈。
- `frontend/src/style.css`：默认不修改；仅当验收发现缺少通用语义 token 时，才以 v2.4.0 设计标准为依据补充 token，不添加 Demo 专属颜色体系。
- `frontend/package.json`：增加 `build:netlify`（如果最终需要与桌面构建分离）。

---

## 10. 测试与验收计划

### 10.1 单元测试

```bash
cd frontend
bun run test -- demoStore demoBridge DemoPreviewSurface
```

必须覆盖：

- 初始 fixture 字段完整且 segment 引用有效。
- 文本编辑只修改目标 segment。
- 确认/驳回 edit 会更新摘要。
- 接受纠错会同步更新文本和 pending correction。
- 三种冲突解决结果都能收敛到明确状态。
- reset 后完全恢复初始 fixture。
- 新任务启动后，旧任务的延迟回调不会覆盖新状态。
- cancel 会清理任务并发出取消事件。
- Demo bridge 所有返回值符合 `{ success, data, error }` envelope。
- Demo 新增模板不出现绿色、紫色、靛蓝主按钮或未登记的业务颜色。
- Demo 新增交互控件具备 `focus-visible` 和 disabled 状态。

### 10.2 现有回归测试

```bash
cd frontend
bun run test
bun run build
```

预期：现有组件测试继续通过，桌面版默认 bridge 行为不变。

### 10.3 浏览器手工验收

使用浏览器打开 Demo 构建后检查：

1. 首屏不等待 10 秒，不显示 Bridge Error。
2. Network 面板没有 `.mp4`、`.webm`、`.wav`、`.mp3` 或 waveform JSON 请求。
3. 模拟媒体区使用 Video Surface，字幕区使用内容画布，分析区使用 Parchment，三层关系与 v2.4.0 Workspace 标准一致。
4. 播放按钮、时间轴 seek、字幕编辑可用，键盘 focus 清晰。
5. AI 操作之间不会同时运行并互相覆盖。
6. 工作流冲突可解决，解决后建议面板和导出摘要一致。
7. 导出按钮不会发起大文件下载或真实文件系统操作。
8. 重置演示后可以重新完整演示。
9. reduced-motion 环境下仍可识别播放、进度和完成状态。
10. 桌面模式运行 `uv run dev.py --no-vite` 时仍走原有 Python bridge。

### 10.4 Netlify 验收

- 构建命令成功。
- `frontend_dist/index.html` 存在且可访问。
- 直接访问站点根路径成功。
- 刷新任意未来新增的 SPA 路径不会 404。
- 发布包中不包含视频、音频和大型波形资源。

### 10.5 v2.4.0 视觉验收

- Demo 不新增第二套按钮 class；主、次、quiet、danger 操作分别落到既有 `mc-button-*` 语义。
- Demo 媒体预览使用 Video Surface，字幕/时间轴使用 Canvas 或白色内容层，分析区域使用 Parchment。
- 不新增绿色、紫色、靛蓝主按钮；确认删除、驳回/保留和待处理状态仍使用既有状态 token。
- 不为模拟媒体区、字幕区或波形区添加装饰性多层 `border + rounded` 卡片。
- Demo 标签、任务进度、冲突反馈和模拟导出结果具备键盘 focus、中文文案和清晰的 loading/success/error 状态。
- 在 `prefers-reduced-motion: reduce` 下，演示仍可通过静态时间码、状态文本和进度条理解当前状态。

---

## 11. 风险与取舍

| 风险 | 影响 | 缓解方案 |
|---|---|---|
| 无真实视频导致产品观感下降 | 中 | 使用高质量 CSS 模拟画面、字幕和时间码，并明确 Demo 标签 |
| 复用 Workspace 触发未覆盖的 bridge 方法 | 中 | 首轮记录所有未覆盖方法；非 Demo 功能统一返回“桌面版可用” |
| 多个 timer 竞争写 Project | 高 | 单一 task runner、runId、统一 cancel/cleanup |
| mock 状态与真实 Project 协议漂移 | 中 | 复用 `Project` TypeScript 类型，并加入 fixture schema 测试 |
| 用户误以为导出成功生成了视频 | 中 | 导出按钮文案使用“模拟导出”，完成提示明确“不生成文件” |
| Netlify 构建环境 Bun 版本变化 | 低 | 在 `netlify.toml` 或 Netlify 环境变量固定 `BUN_VERSION`，并保留 lockfile |
| 后续改真实 Web 后端时 Demo 逻辑过度侵入 | 中 | 所有 Demo 逻辑放在 `frontend/src/demo/`，bridge 只保留一层路由 |

---

## 12. 分阶段实施顺序

### Phase 0：计划确认

- 审议 Demo 是否接受“无真实视频、无真实波形”的模拟媒体方案。
- 确认 Demo 直接继承 v2.4.0 视觉系统，不为 Demo 单独设计新的颜色、按钮和圆角。
- 确认初版只展示核心编辑和 AI 冲突解决，不做真实上传/导出。
- 确认是否需要保留 WelcomePage，还是直接打开演示项目。

### Phase 1：最小浏览器运行时

- 新增 Demo fixture、store、bridge。
- 绕过 pywebview 初始化等待。
- 预加载 Workspace。
- 让现有页面在浏览器中无报错显示。

### Phase 2：无资源媒体体验

- 新增模拟媒体画面。
- 接入模拟播放。
- 接入 Canvas 生成式波形。
- 验证无媒体资源网络请求。

### Phase 3：核心功能演示

- 智能删除建议。
- 字幕纠错审阅。
- 工作流进度。
- 冲突解决。
- 导出摘要与模拟导出。

### Phase 4：防冲突与测试

- 增加 runId、取消和 reset。
- 完成 Demo 单元测试。
- 完成现有回归测试。
- 手工验证所有演示路径。

### Phase 5：Netlify 发布准备

- 添加 `netlify.toml`。
- 固定 Bun 构建版本。
- 检查产物大小和资源请求。
- 构建 Deploy Preview 并进行最终审议。

---

## 13. 待审议问题

1. 是否接受左侧使用“模拟媒体画面”，而不是播放真实视频？本计划推荐接受。
2. 是否需要在 Demo 中保留 WelcomePage？推荐保留一个简化入口，但默认直接进入示例项目。
3. 是否要演示“真实导出文件下载”？推荐初版不做，只展示导出摘要和成功状态。
4. 是否需要让 Demo 模式支持用户刷新后保留修改？推荐初版不做，使用“重置演示”保证可重复。
5. 是否需要把“工作流冲突解决”作为首页引导路径？推荐保留一个明显入口，以体现产品差异化。

---

## 14. 预计规模

- 不增加媒体大文件。
- 预计新增约 8～10 个前端文件和 8～10 个现有文件的小范围修改。
- 不修改 Python 后端。
- 不引入新的运行时依赖。
- POC 约半天到一天。
- 带完整测试、冲突状态和 Netlify 验收约 1～2 天。

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

---

## Phase 2: AI 助手面板 (已完成)

### 概要

Phase 2 将 P0/P1/P2/P3 四个 AI 分析功能接入工作区 UI,实现:

1. **右侧面板三 tab 切换器** (D-18) -- 建议 / AI 助手 / 精华
2. **AIAssistantPanel 组件** (D-02, D-04, D-12, D-14) -- LLM 状态指示器 + 功能卡片 + 操作区
3. **P0 智能删除结果合并** (D-15) -- 新增 llm_smart 分组到 SuggestionPanel
4. **P1 字幕修正全屏 diff 视图** (D-16) -- Teleport + Transition + ESC 关闭
5. **P2 精华提取接入** -- HighlightModeView 作为第三 tab
6. **P3 语义搜索接入** -- SemanticSearchBar 内联到 AI 助手面板

### 变更文件 (共 5 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/composables/useLlmTasks.ts` | 修改 (+30 行) | 新增 LlmConfigStatus 接口、llmConfig 单例 ref、loadLlmConfig() 方法,暴露 LLM 配置状态 (D-04/D-12) |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 修改 (+22 行) | 新增 llm_smart 分组 (D-15);扩展 SuggestionItem.type 联合类型;expandedGroups 默认展开加入 llm_smart;getEditForItem 按 id 查找 |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | **新增** (260 行) | LLM 状态指示器 + 3 功能卡片 (场景名+副标题、未配置置灰+badge) + P0 启动 + P1 参考稿+查看结果 + P3 语义搜索内联 |
| `frontend/src/components/workspace/Timeline.vue` | 修改 (+80/-10 行) | 右侧面板从单 SuggestionPanel 改为三 tab 切换器 (v-show 保持状态);面板宽度 w-72→w-80;新增 LLM props/events 代理 |
| `frontend/src/pages/WorkspacePage.vue` | 修改 (+110 行) | 集成 useLlmTasks;onMounted 调用 loadLlmConfig;EVENT_TASK_COMPLETED 扩展处理 LLM 任务;LLM handler 函数;Timeline 传入 LLM props;SettingsModal + P1 全屏 diff 视图 |

### 架构决策

#### Tab 切换使用 v-show 而非 v-if -- 保持组件状态

三 tab 内容组件 (SuggestionPanel/AIAssistantPanel/HighlightModeView) 使用 `v-show` 条件渲染。原因:
- `SuggestionPanel` 内部维护 `expandedGroups` (分组折叠状态)
- `SemanticSearchBar` 内部维护用户输入的搜索 query + results
- `AIAssistantPanel` 维护选中的功能卡片 + P1 参考稿 textarea

使用 `v-if` 会导致每次切换 tab 时组件销毁重建,用户交互状态全部丢失。

#### LLM 配置状态获取 -- 通过 get_llm_config 桥接方法

useLlmTasks 新增 `loadLlmConfig()` 方法,调用后端 `get_llm_config` @expose 方法。后端返回 masked api_key (非空表示已配置),前端通过 `api_key_masked` 是否非空判断 configured 状态。状态存储在单例 ref 中,所有 useLlmTasks() 调用者共享。

#### P0 结果合并路径 -- 通过 project refresh 自动反映

P0 smart-delete 完成后,后端将结果写入 EditDecision (source="llm_smart"),通过 EVENT_TASK_COMPLETED 事件触发 WorkspacePage 的 project refresh。刷新后的 edits 传给 SuggestionPanel,自动渲染为新的 llm_smart 分组。无需 AIAssistantPanel 直接管理结果。

#### P1 全屏 diff 视图 -- 基础实现

v2.0.1 的 P1 全屏 diff 视图为基础实现 (显示修正统计 + 返回按钮)。完整的逐条 diff 审阅 (accept/reject/diff 展示) 留待后续完善 -- 当前 SubtitleCorrectionReview 组件已具备完整的 diff 能力,但需要后端暴露 corrections 列表获取接口 (当前 corrections 仅在任务返回值中,未通过事件或 @expose 方法持久化)。

### 决策映射

| 决策 | 实现 |
|------|------|
| D-02 (统一 AI 面板) | AIAssistantPanel.vue 作为所有 AI 功能入口 |
| D-04 (LLM 状态指示器) | 绿/黄色圆点 + 模型名 + 未配置时"去设置"链接 |
| D-12 (未配置置灰) | 卡片 opacity-50 + cursor-not-allowed + "未配置" badge |
| D-14 (场景名+副标题) | "快速清理 (智能删除)" / "字幕纠错 (字幕修正)" / "内容搜索 (语义搜索)" |
| D-15 (P0 结果合并) | SuggestionPanel 新增 llm_smart 分组,默认展开 |
| D-16 (P1 全屏 diff) | Teleport + Transition fade + ESC 关闭 |
| D-18 (三 tab 切换) | 建议 / AI 助手 / 精华,使用 v-show |

### 测试覆盖

| 验证项 | 结果 |
|--------|------|
| `bun run build` (前端构建) | 通过 -- 90 modules,JS 210.37 kB,CSS 107.83 kB |
| `bun run test` (147 测试) | 全部通过 -- 含 HighlightModeView/SubtitleCorrectionReview/TimelineSwitcher 测试 |
| TypeScript 类型检查 | 通过 -- vue-tsc --noEmit 无错误 |

---

## Phase 3: 提示词编辑系统 (已完成)

### 概要

Phase 3 实现了 AI 提示词的自定义能力,支持:

1. **5 个 prompt 标记位化** -- smart_delete/subtitle_correction_a/b/highlight 加入 `{{param}}` 标记位 (search 无参数化)
2. **分层持久化** (D-08) -- 全局默认 (settings.json) + 项目覆盖 (Timeline.llm_prompts)
3. **双模式编辑** (D-05) -- 简单模式 (参数化字段) + 高级模式 (全量 textarea)
4. **标记位注入** (D-19) -- `{{param}}` 替换,空值→空字符串,`_format_param` 按 key 类型格式化 + strip 处理
5. **重置为默认** (D-07) -- 每个 prompt 可独立重置

### 变更文件 (共 8 个)

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/llm_prompts.py` | **新增** (250 行) | 5 个 prompt 常量 (含 {{param}} 标记位) + DEFAULT_PROMPTS 注册表 + get_effective_prompt + _inject_placeholders + _format_param + get_default_prompt_text/params |
| `core/llm_service.py` | 修改 (-60/+30 行) | 删除 5 个内联常量定义,改为从 llm_prompts 导入;4 个 analyze_* 函数新增 system_prompt 参数 (None 时使用 get_effective_prompt) |
| `core/config.py` | 修改 (+2 行) | _DEFAULT_SETTINGS 新增 `llm_prompts: {}` 字段 |
| `core/models.py` | 修改 (+5 行) | Timeline 新增 `llm_prompts: dict = Field(default_factory=dict)` 字段 |
| `main.py` | 修改 (+90 行) | 新增 3 个 @expose: get_llm_prompts/update_llm_prompt/reset_llm_prompt + _load_settings_raw helper;4 个 LLM handler 全部传入 effective prompt |
| `frontend/src/composables/useLlmSettings.ts` | 修改 (+60 行) | 新增 PromptDefaults/PromptOverride/LlmPromptsData 接口 + loadPrompts/updatePrompt/resetPrompt 方法 |
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 (+100 行) | LLM tab 新增提示词编辑子面板:功能选择器 + 简单/高级模式切换 + 参数 textarea + 全量 prompt textarea + 查看默认 + 保存/重置 |
| `tests/test_llm_prompts.py` | **新增** (200 行) | 28 个测试:DEFAULT_PROMPTS 结构 + _format_param + _inject_placeholders + get_effective_prompt (分层优先级) + helper 函数 |

### 架构决策

#### 标记位格式 -- `{{param}}` 双花括号

选择 `{{custom_fillers}}` 格式而非单花括号 `{custom_fillers}`,避免与 JSON 模板字符串冲突。Python 中 `{{{{{key}}}}}` (5 层花括号) 在 f-string 中正确求值为 `{{key}}` 字符串。

#### 空值处理 -- 替换为空字符串而非移除行

当参数为空时,标记位替换为 `""`,保留所在行结构 (变为空行)。这确保了不加参数时 prompt 结构与原始基本一致,只是多一个空行 -- 对 LLM 分析质量无影响。

#### _format_param 的 strip 处理

`_format_param` 对每个值调用 `strip()`,避免用户输入的纯空格项被判定为有内容。这是审计反馈的具体落实。

#### 浅拷贝合并的安全性

```python
params = {**default["params"], **override.get("params", {})}
```

这是浅拷贝合并 (Shallow Merge)。当前参数结构仅一层 `list[str]`,浅拷贝是安全的。如果未来参数结构嵌套更深层,需改用 Deep Merge。

#### system_override 优先级

高级模式的 `system_override` 优先于简单模式参数。如果 `system_override` 非空且非纯空白,直接返回该文本,跳过标记位注入。空/纯空白的 `system_override` 被忽略,回退到简单模式。

### 决策映射

| 决策 | 实现 |
|------|------|
| D-05 (双模式编辑) | SettingsModal LLM tab 内功能选择 + 简单/高级模式 radio |
| D-06 (参数化方案) | custom_fillers (smart_delete) / glossary (subtitle_correction) / focus_keywords (highlight) |
| D-07 (重置为默认) | reset_llm_prompt @expose + 前端"重置为默认"按钮 |
| D-08 (分层持久化) | settings.json 全局 + Timeline.llm_prompts 项目级 |
| D-19 (标记位注入) | `{{param}}` 替换 + _format_param 格式化 + 空值→空串 |

### 测试覆盖

| 验证项 | 结果 |
|--------|------|
| `uv run pytest tests/test_llm_prompts.py` | 28 测试全部通过 |
| `uv run pytest tests/` (全量,排除 whisper) | 231 测试全部通过 |
| `bun run build` (前端构建) | 通过 -- 90 modules,JS 215.13 kB |
| `bun run test` (147 前端测试) | 全部通过 |
| TypeScript 类型检查 | 通过 -- vue-tsc --noEmit 无错误 |

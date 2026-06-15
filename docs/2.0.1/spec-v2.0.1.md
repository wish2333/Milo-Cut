# v2.0.1 UI 打磨 -- 实施规格说明

> **版本**: 2.0.1
> **主题**: UI 打磨 -- Dropdown 修复、AI 助手面板、提示词编辑系统、设置页全屏化
> **基准**: v2.0.0 (待发布)
> **分支**: `dev-2.0.1` (基于 `dev-2.0.0`)
> **类型**: 补丁/打磨版本 (含少量新功能)

---

## 背景与问题陈述

v2.0.0 完成了 AI 驱动的核心功能 (P0-P3)，但在实际使用中发现 4 个 UI/UX 问题:

1. **Timeline 下拉菜单透明背景** -- TimelineSwitcher 的 dropdown 弹出后背景透明，看不清内容
2. **AI 分析入口不明晰** -- P0/P1/P2/P3 四个 AI 功能组件已开发 (SubtitleCorrectionReview / HighlightModeView / SemanticSearchBar + useLlmTasks composable) 但未接入工作区 UI (WorkspacePage 未导入任何 LLM composable,三个组件均为孤立状态)
3. **AI 提示词不支持调整** -- 5 个 system prompt 硬编码在 `core/llm_service.py` 常量中 (smart_delete 1 个 + subtitle_correction A/B 2 个 + highlight 1 个 + search 1 个)，用户无法定制
4. **设置页是弹窗，空间不足** -- SettingsModal 作为 640px Modal 弹窗 (`w-[640px] max-w-[90vw] max-h-[85vh]`)，内容拥挤

---

## 决策摘要

| 编号 | 决策 | 选择 |
|------|------|------|
| D-01 | Dropdown 修复策略 | 根因已确认 (appleLight 主题无颜色定义); 首选补充 `@plugin "daisyui/theme"` 颜色定义, fallback 用显式颜色类 |
| D-02 | AI 功能入口布局 | 统一 AI 助手面板，在右侧面板内与 SuggestionPanel 切换 |
| D-03 | 精华提取 (P2) 集成 | 独立工作模式切换 (编辑模式 / 精华模式) |
| D-04 | AI 助手面板内容 | 顶部功能卡片选择器 (场景名+功能名副标题) + LLM 状态指示器 |
| D-05 | 提示词编辑深度 | 双模式: 简单 (参数化微调) + 高级 (全量文本编辑) |
| D-06 | 提示词参数化方案 | 按功能定制参数 (口头禅列表 / 术语表 / 关注关键词) |
| D-07 | 提示词回退机制 | 每项独立"重置为默认"按钮 |
| D-08 | 提示词持久化 | 分层: 全局默认 (settings.json) + 项目覆盖 (project.json) |
| D-09 | 设置页架构 | 升级现有 Modal 为全屏覆盖层 (100vw x 100vh) |
| D-10 | 设置页 tab 布局 | 保留现有 4 个顶部 tab，增大内容区 |
| D-11 | 设置入口位置 | 保留 WelcomePage 现有入口，不新增入口 |
| D-12 | AI 未配置表现 | 功能卡片置灰 + "未配置" badge + 一键跳转设置 |
| D-13 | 精华模式布局 | v2.0.1 先做基础切换 (右侧第三 tab)，独立布局留 v2.1.0 |
| D-14 | 功能卡片命名 | 场景名为主标题 + 功能名为副标题 (如"快速清理 (智能删除)") |
| D-15 | P0 结果展示 | 合并到 SuggestionPanel 作为新分组 (source=llm_smart) |
| D-16 | P1 结果展示 | AI 助手内"查看修正结果"按钮触发专属全屏 diff 视图 |
| D-17 | P1 跳转行为 | 仅视频跳转播放位置，不切换 tab |
| D-18 | 精华模式触发 | 右侧面板第三个 tab: [建议 / AI 助手 / 精华] |
| D-19 | 提示词参数注入 | 标记位替换 ({{param}})，修改现有 prompt 加标记位，空参数替换为空串 |
| D-20 | 一键清理工作流 | 留给 v2.1.0 (需任务编排能力) |
| D-21 | 提示词风格预设 | 留给 v2.1.0 |
| D-22 | 长视频提示 | 不做 (ASR 已做预处理，LLM 分析的是已分段文本，与视频时长无关) |

---

## 实施计划

### Phase 1: Dropdown 修复 (D-01)

**目标**: 修复 TimelineSwitcher 下拉菜单透明背景问题

#### 排查步骤

1. 检查 DaisyUI 5 theme 配置是否正确加载到组件层级
2. 检查 `--b1` (base-100) CSS 变量是否在 `:root` 或组件作用域中定义
3. 检查 Tailwind CSS 4 + DaisyUI 5 的集成方式 (`@plugin "daisyui"` vs `daisyui: { themes: [...] }`)
4. 检查 `z-50` 层级是否被其他元素遮挡

> **排查结论 (代码审计)**: 根因已确认,见 [附录 A: Phase 1 根因分析](#附录-a-phase-1-根因分析)。

#### 修复方案

- **首选**: 为 `appleLight` 主题补充颜色定义,使 DaisyUI 5 生成 `--b1`/`base-100` 等 CSS 变量:
  ```css
  /* frontend/src/style.css */
  @plugin "daisyui" {
    themes: appleLight --default;
    prefix: false;
  }
  /* 新增: 显式定义 appleLight 主题颜色 (DaisyUI 5 要求自定义主题必须定义颜色,
     否则不生成 base-100/secondary/content 等语义变量) */
  @plugin "daisyui/theme" {
    name: "appleLight";  /* 建议加引号 -- DaisyUI 5 官方推荐 name 属性使用字符串包裹 */
    default: true;
    color-scheme: light;
    --color-base-100: oklch(100% 0 0);       /* #ffffff -- 推荐使用 oklch() 获得最佳生态兼容性 */
    --color-base-200: oklch(97% 0.001 286);  /* #f5f5f7 */
    --color-base-300: oklch(87% 0.005 286);  /* #d2d2d7 */
    --color-base-content: oklch(21% 0.006 286); /* #1d1d1f */
    /* 可选: 补充 primary/secondary/neutral 语义色 */
  }
  ```
  > **色彩格式说明**: DaisyUI 5 + Tailwind v4 强烈推荐使用 `oklch()` 色彩空间。虽然 Hex 也兼容,但如果后续需要使用透明度修饰符 (如 `bg-base-100/50`),`oklch` 在 Tailwind v4 中的解析行为最稳定。上表中的 oklch 值与现有 `@theme` 中的 Hex 值视觉等效。
- **Fallback (仅改组件类)**: 将 `bg-base-100` / `border-base-300` 替换为显式颜色类:
  ```html
  <!-- 修复前 -->
  <ul class="dropdown-content z-50 menu p-2 shadow-lg bg-base-100 rounded-box w-64 border border-base-300">
  <!-- 修复后 (fallback) -->
  <ul class="dropdown-content z-50 menu p-2 shadow-xl bg-white text-gray-800 rounded-box w-64 border border-gray-200">
  ```

> **注意**: 当前代码库中 **4 个组件** 使用了 `bg-base-100`/`border-base-300` 类 (TimelineSwitcher、HighlightModeView、SemanticSearchBar、SubtitleCorrectionReview),首选方案可一次性修复全部;Fallback 方案需逐组件修改。

#### 影响范围

| 文件 | 变更 |
|------|------|
| `frontend/src/style.css` | **首选**: 补充 `@plugin "daisyui/theme"` 颜色定义 (appleLight 主题) |
| `frontend/src/components/workspace/TimelineSwitcher.vue` | **Fallback only**: 修改 dropdown-content CSS 类 |
| ~~`frontend/tailwind.config.*`~~ | **不适用** -- 本项目使用 Tailwind CSS 4,无 JS 配置文件,配置在 `style.css` 中通过 `@plugin`/`@theme` 指令完成 |

---

### Phase 2: AI 助手面板 (D-02, D-03, D-04, D-12, D-14~D-18)

**目标**: 将 P0/P1/P3 三个 AI 分析功能接入工作区 UI; P2 精华提取作为右侧第三 tab

#### 架构设计

##### 2.1 右侧面板三 tab 切换器

在 Timeline 右侧面板顶部增加三 tab 切换器 (D-18):

```
┌──────────────────────────────────┐
│  [建议]  [AI 助手]  [精华]        │  <- 三 tab 切换
├──────────────────────────────────┤
│                                  │
│  SuggestionPanel /               │  <- 根据 tab 切换内容
│  AIAssistantPanel /              │
│  HighlightModeView               │
│                                  │
└──────────────────────────────────┘
```

- `[建议]` tab: 现有 SuggestionPanel (规则分析: filler/error/silence + P0 智能删除结果合并)
- `[AI 助手]` tab: 新增 AIAssistantPanel (P0 启动 + P1 启动 + P3 搜索)
- `[精华]` tab: HighlightModeView (P2 精华提取 + 跳切点 + 时长控制)

> **关键 UX: Tab 切换使用 `v-show` 保持组件状态**
>
> 三 tab 的内容组件**必须使用 `v-show` 而非 `v-if`** 进行条件渲染。原因:
> - `SuggestionPanel` 内部维护 `expandedGroups` (分组折叠/展开状态)
> - `SemanticSearchBar` 内部维护用户输入的搜索查询 + 搜索结果
> - `SubtitleCorrectionReview` 内部维护 `acceptedIds`/`rejectedIds` + `referenceText` 输入
>
> 使用 `v-if` 会导致每次切换 tab 时组件被销毁重建,用户的交互状态 (展开的分组、已输入的参考稿、滚动位置) 全部丢失。
>
> ```vue
> <div class="flex-1 overflow-y-auto">
>   <SuggestionPanel  v-show="activeTab === 'suggestion'" ... />
>   <AIAssistantPanel v-show="activeTab === 'ai'"        ... />
>   <HighlightModeView v-show="activeTab === 'highlight'" ... />
> </div>
> ```

##### 2.2 AIAssistantPanel 组件

```
┌──────────────────────────────────┐
│  ● LLM 已配置 (test-model)        │  <- LLM 状态指示器 (D-04)
├──────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐       │
│  │ 快速清理  │ │ 字幕纠错  │       │  <- 功能卡片 (D-14)
│  │(智能删除) │ │(字幕修正) │       │     场景名 + 功能名副标题
│  └──────────┘ └──────────┘       │
│  ┌──────────┐                     │
│  │ 内容搜索  │                     │
│  │(语义搜索) │                     │
│  └──────────┘                     │
├──────────────────────────────────┤
│                                  │
│  (选中功能的操作区)                │  <- 根据选中的卡片展示
│                                  │
└──────────────────────────────────┘
```

**功能卡片命名 (D-14)**:
- 主标题 (场景名): 快速清理 / 字幕纠错 / 内容搜索
- 副标题 (功能名): (智能删除) / (字幕修正) / (语义搜索)

**LLM 状态指示器**:
- 已配置: 绿色圆点 + "LLM 已配置" + 模型名
- 未配置: 黄色圆点 + "未配置" + "去设置" 链接

**功能卡片 (未配置时) (D-12)**:
- 卡片置灰 (opacity-50 + cursor-not-allowed)
- 右上角 "未配置" badge
- 点击卡片: 跳转到设置页 LLM tab

**功能卡片 (已配置时)**:
- 正常颜色，可点击
- 点击后下方展示对应功能区

##### 2.3 功能区详情

**快速清理 / 智能删除 (P0) (D-15)**:

- 启动按钮 "开始智能分析"
- 进度条 (复用 useLlmTasks 的共享 `progress` ref)
- **结果不在此面板展示** -- 分析完成后自动切换到 `[建议]` tab
- 结果合并到 SuggestionPanel 作为新分组 "智能删除" (source=`"llm_smart"`，与后端 `_handle_smart_delete` 写入的 EditDecision.source 值一致)
- SuggestionPanel 需扩展: 新增 llm_smart 分组类型

**字幕纠错 / 字幕修正 (P1) (D-16, D-17)**:
- 参考稿 textarea (模式 B，可选，留空为模式 A)
- 启动按钮 "开始字幕修正"
- 分析完成后: AI 助手面板内显示 "查看修正结果 (N 条)" 按钮
- **点击按钮触发专属全屏 diff 视图** (SubtitleCorrectionReview 全屏化):
  ```
  ┌─ 字幕修正审阅 (全屏覆盖层) ──────────────┐
  │                                          │
  │  高置信度修正 (N)                         │
  │  ┌──────────────────────────────────────┐│
  │  │ 00:05  [同音错字]  高置信度           ││
  │  │ 原文: 这是错字  →  修正: 这是正字    ││
  │  │ [接受] [拒绝]                         ││
  │  └──────────────────────────────────────┘│
  │                                          │
  │  低置信度修正 (N)  (默认折叠)             │
  │  ...                                     │
  │                                          │
  │  [信任高置信度]  [返回]                   │
  └──────────────────────────────────────────┘
  ```
- 全屏 diff 视图内点击时间链接: **仅视频跳转播放位置，不切换 tab** (D-17)
- 关闭全屏 diff 视图后返回 AI 助手面板

**内容搜索 / 语义搜索 (P3)**:
- 搜索输入框 (常驻，不需要启动任务)
- 搜索结果列表 (segment 文本预览 + relevance badge + 跳转)
- 复用 SemanticSearchBar 组件
- 点击结果: 仅视频跳转，不切换 tab

##### 2.4 精华 tab (P2) (D-13, D-18)

`[精华]` tab 直接展示 HighlightModeView 组件:

```
┌──────────────────────────────────┐
│  高光提取           3 个高光片段  │
├──────────────────────────────────┤
│  目标时长: [10] 分钟  [开始提取]  │
├──────────────────────────────────┤
│  已选 20s / 目标 60s              │
│  ⚠ 检测到 2 处跳切               │
├──────────────────────────────────┤
│  00:10 [高密度] 核心论点          │
│  00:30 [中密度] 精彩类比          │
│  01:00 [高密度] 重要结论          │
└──────────────────────────────────┘
```

- v2.0.1: 基础切换 + HighlightModeView 原样展示
- v2.1.0: 独立布局打磨 (跳切 crossfade 预览、精华版直通导出等)

#### SuggestionPanel 扩展 (D-15)

现有 SuggestionPanel 的 groups computed 需新增 llm_smart 分组:

```typescript
// 新增分组类型
const llmSmartEdits = props.edits.filter(
  e => e.source === "llm_smart" && e.status === "pending"
)
if (llmSmartEdits.length > 0) {
  result.push({
    type: "llm_smart",
    label: "智能删除",
    items: llmSmartEdits.map(e => ({ ... })),
  })
}
```

> **现状说明 (代码审计)**: 当前 `SuggestionPanel.vue` 的 `SuggestionItem.type` 联合类型为 `"filler" | "error" | "silence"`，`expandedGroups` 初始值为 `new Set(["filler", "error"])`。新增 llm_smart 分组需同步扩展该联合类型,并考虑是否默认展开 (当前 silence 分组默认折叠)。`props.edits` 的 `source` 字段为 `string` 类型 (见 `frontend/src/types/project.ts:29`),后端写入值确认为 `"llm_smart"` (`main.py:719`)。

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/AIAssistantPanel.vue` | **新增** | AI 助手面板: LLM 状态 + 功能卡片 (场景名+副标题) + 操作区 |
| `frontend/src/components/workspace/SubtitleCorrectionFullscreen.vue` | **新增** | P1 专属全屏 diff 视图 (基于现有 SubtitleCorrectionReview 组件扩展) |
| `frontend/src/components/workspace/Timeline.vue` | 修改 | 右侧面板从单面板 (SuggestionPanel) 改为三 tab 切换 (建议/AI 助手/精华) |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 修改 | 新增 llm_smart 分组类型 (D-15); 扩展 SuggestionItem.type 联合类型 |
| `frontend/src/pages/WorkspacePage.vue` | 修改 | 集成 useLlmTasks (当前未导入); 处理 P0 完成后自动切换建议 tab; P1 全屏 diff 触发 |
| `frontend/src/composables/useLlmTasks.ts` | 修改 | 暴露 LLM 配置状态 (当前无此能力); P0 完成后 emit 切换 tab 信号 |

> **现状说明 (代码审计)**:
> - **AIAssistantPanel.vue**: 不存在,需新建。
> - **SubtitleCorrectionFullscreen.vue**: 不存在,需新建。现有 `SubtitleCorrectionReview.vue` 可作为基础 (已含 diff 展示、accept/reject、批量信任逻辑)。
> - **Timeline.vue**: 当前右侧面板仅渲染 `<SuggestionPanel>` (`Timeline.vue:144`),无 tab 切换器。需新增 tab 状态 + 条件渲染。
> - **WorkspacePage.vue**: 当前**完全没有**集成任何 LLM composable (未 import `useLlmTasks`/`useLlmAnalysis`)。需新增 import + 调用。
> - **useLlmTasks.ts**: 已实现 P0/P1/P2 启动 + 结果接收,但 (a) 无任何组件引用它 (b) 不暴露 LLM 配置状态 (c) 无 tab 切换信号。
> - **HighlightModeView.vue / SemanticSearchBar.vue / SubtitleCorrectionReview.vue**: 三个 AI 功能组件已存在且功能完整,但均未被任何页面组件引用 (均为孤立组件)。Phase 2 需在 AIAssistantPanel / Timeline 中接入它们。

### Phase 3: 提示词编辑系统 (D-05, D-06, D-07, D-08, D-19)

**目标**: 用户可自定义 4 个 AI 功能的 system prompt

#### 架构设计

##### 3.1 双模式编辑

每个 AI 功能的提示词编辑区提供两个模式:

- **简单模式** (默认): 暴露关键参数化字段 (非全量 prompt)
  - 智能删除: 自定义口头禅列表 (注入到 prompt 的 `{{custom_fillers}}` 标记位)
  - 字幕修正: 参考术语/专有名词表 (注入到 `{{glossary}}` 标记位)
  - 精华提取: 关注重点关键词 (注入到 `{{focus_keywords}}` 标记位)
  - 语义搜索: 无参数化 (纯查询，不提供简单模式)

- **高级模式**: 全量 prompt 文本编辑 (textarea)
  - 展示完整的 system prompt 原文 (含标记位)
  - 支持直接编辑 (包括标记位)
  - "查看默认值" 参考 + "重置为默认" 按钮

##### 3.2 提示词参数定义

```python
# core/llm_prompts.py (新增)
DEFAULT_PROMPTS = {
    "smart_delete": {
        "system": _SMART_DELETE_SYSTEM,  # 从 llm_service.py 移出
        "params": {
            "custom_fillers": [],  # 自定义口头禅列表
        },
    },
    "subtitle_correction_a": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_A,
        "params": {
            "glossary": [],  # 术语表
        },
    },
    "subtitle_correction_b": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_B,
        "params": {
            "glossary": [],
        },
    },
    "highlight": {
        "system": _HIGHLIGHT_SYSTEM,
        "params": {
            "focus_keywords": [],  # 关注关键词
        },
    },
    "search": {
        "system": _SEARCH_SYSTEM,
        "params": {},  # 无参数化
    },
}
```

##### 3.3 分层持久化 (D-08)

- **全局默认**: `data/settings.json` 的 `llm_prompts` 字段
  ```json
  {
    "llm_prompts": {
      "smart_delete": {
        "system_override": null,
        "params": { "custom_fillers": ["那个", "就是说"] }
      }
    }
  }
  ```

- **项目覆盖**: `data/projects/<name>/project.json` 的 `timeline.llm_prompts` 字段
  ```json
  {
    "llm_prompts": {
      "smart_delete": {
        "system_override": "自定义 prompt 全文...",
        "params": { "custom_fillers": ["本项目特有口头禅"] }
      }
    }
  }
  ```

- **读取优先级**: 项目覆盖 > 全局默认 > 硬编码常量

##### 3.4 Prompt 标记位注入 (D-19)

**方案**: 修改现有 prompt 常量，在合适位置插入 `{{param}}` 标记位。运行时替换为用户输入的值。空参数替换为空字符串，确保不加参数时 prompt 行为不变。

**示例 -- 智能删除 prompt 标记位**:

```python
# 修改前 (llm_service.py 硬编码)
_SMART_DELETE_SYSTEM = """你是视频剪辑助手。用户以 JSON 格式提供一组转录片段。
请识别需要删除的片段: 口头禅、重复语句、自我纠正。
...
"""

# 修改后 (llm_prompts.py，加入标记位)
_SMART_DELETE_SYSTEM = """你是视频剪辑助手。用户以 JSON 格式提供一组转录片段。
请识别需要删除的片段: 口头禅、重复语句、自我纠正。
{{custom_fillers}}
...
"""
# 当 custom_fillers 为空时，标记位替换为 ""，prompt 行为不变
# 当有值时替换为: "\n额外需要检测的口头禅: 那个、就是说"
```

**注入逻辑**:

```python
def get_effective_prompt(func_key: str, project=None) -> str:
    """获取生效的 system prompt，合并标记位参数注入。"""
    default = DEFAULT_PROMPTS[func_key]
    settings = load_settings()
    global_override = settings.get("llm_prompts", {}).get(func_key, {})

    # 项目级覆盖优先
    if project and func_key in project_prompts:
        override = project_prompts[func_key]
    else:
        override = global_override

    # 高级模式: 使用 system_override (如果存在)
    if override.get("system_override"):
        return override["system_override"]

    # 简单模式: 标记位替换
    system = default["system"]
    # 浅拷贝合并 (Shallow Merge) -- 安全: 参数结构仅一层 list[str]
    # 如未来参数结构嵌套更深层,需改用 Deep Merge
    params = {**default["params"], **override.get("params", {})}
    return _inject_placeholders(system, params, func_key)


def _inject_placeholders(prompt: str, params: dict, func_key: str) -> str:
    """将参数值替换到 prompt 中的 {{param}} 标记位。

    空值替换为空字符串，不影响 prompt 结构。
    非空值格式化为可读的补充指令段。
    """
    result = prompt
    for key, value in params.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder not in result:
            continue  # 该 prompt 无此标记位，跳过
        formatted = _format_param(key, value, func_key)
        result = result.replace(placeholder, formatted)
    return result


def _format_param(key: str, value: list[str], func_key: str) -> str:
    """将参数值格式化为 prompt 中的可读文本。

    空值或仅含空白字符的值都替换为空字符串,保证 prompt 纯净。
    """
    # 过滤空白项,避免只有空格的参数被判定为有内容
    cleaned = [v.strip() for v in value if v and v.strip()]
    if not cleaned:
        return ""  # 空值 -> 空字符串
    # 按参数类型格式化
    if key == "custom_fillers":
        return f"\n额外需要检测的口头禅: {'、'.join(cleaned)}"
    elif key == "glossary":
        return f"\n参考术语表 (优先使用这些正确写法): {'、'.join(cleaned)}"
    elif key == "focus_keywords":
        return f"\n特别关注这些关键词的相关内容: {'、'.join(cleaned)}"
    return ""
```

##### 3.5 UI 集成

提示词编辑放在设置覆盖层的 LLM tab 中 (Phase 4 完成后):

```
┌─ LLM 设置 tab ─────────────────────────┐
│                                        │
│  [连接配置]  [提示词]                    │  <- LLM tab 内子切换
│                                        │
│  ┌─ 提示词 ──────────────────────────┐  │
│  │                                   │  │
│  │  功能: [智能删除 ▾]                │  │
│  │                                   │  │
│  │  ○ 简单模式  ○ 高级模式            │  │
│  │                                   │  │
│  │  简单模式:                         │  │
│  │  自定义口头禅: [那个, 就是说, ...]  │  │
│  │                                   │  │
│  │  高级模式:                         │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │ (textarea: 完整 prompt)      │  │  │
│  │  └─────────────────────────────┘  │  │
│  │  [重置为默认]                      │  │
│  │                                   │  │
│  └───────────────────────────────────┘  │
│                                        │
└────────────────────────────────────────┘
```

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/llm_prompts.py` | **新增** | prompt 常量 + 默认参数定义 + get_effective_prompt |
| `core/llm_service.py` | 修改 | 从 llm_prompts 读取 prompt 替代硬编码常量; analyze_* 函数新增 prompt_override 参数 |
| `core/config.py` | 修改 | `_DEFAULT_SETTINGS` 新增 `llm_prompts` 字段 |
| `core/models.py` | 修改 | `Timeline` 新增 `llm_prompts` 字段 (项目级覆盖) |
| `main.py` | 修改 | 新增 @expose: get_llm_prompts / update_llm_prompts / reset_llm_prompt |
| `frontend/src/components/workspace/SettingsOverlay.vue` | 修改 | LLM tab 新增提示词编辑子面板 (Phase 4 重命名后) |
| `frontend/src/composables/useLlmSettings.ts` | 修改 | 新增 getPrompts / updatePrompt / resetPrompt |

> **现状说明 (代码审计)**:
> - **5 个 prompt 常量当前硬编码位置** (均在 `core/llm_service.py` 中):
>   - `_SMART_DELETE_SYSTEM` (行 437)
>   - `_SUBTITLE_CORRECTION_SYSTEM_A` (行 581) / `_SUBTITLE_CORRECTION_SYSTEM_B` (行 594)
>   - `_HIGHLIGHT_SYSTEM` (行 824)
>   - `_SEARCH_SYSTEM` (行 998)
> - **analyze_* 函数当前签名** (均**无** prompt_override 参数,需新增):
>   - `analyze_smart_delete(segments, existing_flagged_ids, *, config, cancel_event, progress_cb, chunk_callback)` (行 449)
>   - `analyze_subtitle_correction(segments, reference_text, context_window, *, config, cancel_event, progress_cb)` (行 605)
>   - `analyze_highlights(segments, *, config, cancel_event, progress_cb, ...)` (行 841)
>   - `semantic_search(segments, query, *, config, ...)` (行 1008) -- 纯查询无标记位,但仍需接受 override 保持一致性
> - **config.py**: `_DEFAULT_SETTINGS` (行 14-82) 当前无 `llm_prompts` key,需新增。
> - **models.py Timeline**: 当前字段 (行 260-275) 无 `llm_prompts`,需新增。
> - **main.py**: 当前无 `get_llm_prompts` / `update_llm_prompts` / `reset_llm_prompt` 方法。
> - **useLlmSettings.ts**: 当前仅有 `testConnection` (行 13-33),需扩展。
> - **后端调用链**: main.py 中 `_handle_smart_delete` (行 657)、`_handle_subtitle_correction` (行 748)、`_handle_highlight` (行 807) 直接调用 analyze_* 函数 -- 新增 prompt_override 后需在这些 handler 中传入 get_effective_prompt 结果。

---

### Phase 4: 设置页全屏化 (D-09, D-10, D-11)

**目标**: SettingsModal 升级为全屏覆盖层，增大内容空间

#### 架构设计

##### 4.1 全屏覆盖层

将 `SettingsModal.vue` 重命名为 `SettingsOverlay.vue`，修改根元素:

```vue
<template>
  <Teleport to="body">
    <Transition name="overlay-fade">
      <div v-if="visible" class="fixed inset-0 z-[9998] bg-white">
        <!-- 100vw × 100vh 全屏，无遮罩 -->
        <div class="flex h-full flex-col">
          <!-- Header -->
          <div class="flex items-center justify-between border-b px-8 py-4">
            <h2 class="text-lg font-semibold">设置</h2>
            <button @click="$emit('close')" class="btn btn-sm btn-ghost">✕</button>
          </div>
          
          <!-- Tab 导航 -->
          <div class="border-b px-8">
            <div class="flex gap-6">
              <button v-for="tab in tabs" ...>{{ tab.label }}</button>
            </div>
          </div>
          
          <!-- Tab 内容 (flex-1 占满剩余空间) -->
          <div class="flex-1 overflow-y-auto px-8 py-6">
            <!-- 各 tab 内容 -->
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { onMounted, onUnmounted } from "vue"

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

// ESC 快捷键关闭全屏覆盖层
function handleEsc(e: KeyboardEvent) {
  if (e.key === "Escape" && props.visible) emit("close")
}
onMounted(() => window.addEventListener("keydown", handleEsc))
onUnmounted(() => window.removeEventListener("keydown", handleEsc))
</script>

<style>
/* 全屏覆盖层淡入淡出 -- 150ms 平滑过渡,避免突兀的白板闪现 */
.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 150ms ease;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
```

> **UX 补充**:
> - **ESC 快捷键**: 全屏覆盖层让用户下意识按 ESC 退出,需在 `onMounted` 监听 `keydown.esc` 触发 `@close`。
> - **过渡动画**: 100vw 全屏白板突然出现视觉冲击大,套 `<Transition name="overlay-fade">` 实现 150ms 淡入淡出。

##### 4.2 保留现有 4 个 tab

- **通用**: FFmpeg/FFprobe 路径、GPU 检测、uv 可用性
- **AI 引擎**: ASR 引擎选择、模型管理、插件安装
- **LLM**: 连接配置 (Provider/Base URL/API Key/Model/Temperature) + 提示词编辑 (Phase 3 成果)
- **导出**: 编码器、质量参数、像素格式

内容区从 Modal 的 ~400px 高度扩展到 ~calc(100vh - 120px)，大幅减少拥挤。

##### 4.3 入口不变

保留 WelcomePage 现有设置按钮入口，仅替换组件引用:

```vue
<!-- WelcomePage.vue (当前行 154) -->
<!-- 修改前 -->
<SettingsModal :visible="showSettings" @close="showSettings = false" />
<!-- 修改后 -->
<SettingsOverlay :visible="showSettings" @close="showSettings = false" />
```

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | **重命名** → `SettingsOverlay.vue` + 重写根元素为全屏 |
| `frontend/src/pages/WelcomePage.vue` | 修改 | import 路径更新 (当前行 4: `import SettingsModal from "@/components/workspace/SettingsModal.vue"`) |

> **现状说明 (代码审计)**:
> - **SettingsModal.vue 当前结构** (行 394-399): 根元素为 `<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">`,内层为 `<div class="bg-white rounded-2xl shadow-2xl w-[640px] max-w-[90vw] max-h-[85vh] overflow-hidden flex flex-col">`。
> - **无 Teleport**: 当前组件直接渲染在父组件 DOM 位置,未使用 `<Teleport to="body">`。全屏化需新增 Teleport 以避免被父容器 (如 overflow-hidden) 裁剪。
> - **4 个 tab 现状**: `activeTab` ref 类型为 `"general" | "ai-engine" | "llm" | "export"` (行 23),tab 导航内联在模板中 (行 406-425)。
> - **LLM tab 现状** (行 944+): 当前包含 Provider/Base URL/API Key/Model/Temperature 表单 + testConnection 按钮。Phase 3 的提示词编辑子面板需追加到此 tab 内。
> - **tab label 语言**: 当前 tab label 为英文 (General/AI Engine/LLM/Export),全屏化时是否需中文化由实施者决定 (与 spec 示例中的 "设置" 不一致)。

---

## 实施顺序

| 顺序 | Phase | 预估 | 说明 |
|------|-------|------|------|
| 1 | Phase 1: Dropdown 修复 | 0.5 pd | 最快见效，不依赖其他 Phase |
| 2 | Phase 2: AI 助手面板 | 3-4 pd | 三 tab 切换 + AI 助手面板 + P0 合并 + P1 全屏 diff + 精华 tab |
| 3 | Phase 3: 提示词编辑系统 | 2-3 pd | 后端 prompt 标记位重构 + 前端编辑 UI |
| 4 | Phase 4: 设置页全屏化 | 1 pd | 最后做，因为 Phase 3 的提示词编辑要放入设置页 |
| **合计** | | **6.5-8.5 pd** | |

---

## 测试策略

| 模块 | 测试要点 | 测试文件现状 |
|------|----------|------------|
| Dropdown 修复 | `TimelineSwitcher.test.ts`: 验证 dropdown-content 背景可见性 | **已存在** (`TimelineSwitcher.test.ts` 3.3KB) |
| AI 助手面板 | `AIAssistantPanel.test.ts`: LLM 状态指示器 / 卡片置灰 / 场景名+副标题展示 / 卡片切换 | **需新建** |
| P0 结果合并 | `SuggestionPanel.test.ts`: 验证 llm_smart 分组渲染 + accept/reject | **需新建** (当前 SuggestionPanel 无测试) |
| P1 全屏 diff | `SubtitleCorrectionFullscreen.test.ts`: 全屏触发 / diff 展示 / accept-reject / 视频跳转不切 tab | **需新建** (现有 `SubtitleCorrectionReview.test.ts` 可作参考) |
| 精华 tab | Timeline 集成测试: 三 tab 切换 / HighlightModeView 渲染 | **需新建** |
| 提示词编辑 | 后端: `tests/test_llm_prompts.py` (标记位注入/空值兼容/分层覆盖/重置); 前端: 简单模式/高级模式切换 | **需新建** |
| 设置全屏化 | `SettingsOverlay.test.ts`: 全屏布局 / tab 切换 | **需新建** (重命名后 SettingsModal 无测试) |

---

## 风险与约束

| 风险 | 缓解措施 |
|------|----------|
| DaisyUI 主题问题已确认为全局性 (appleLight 主题无颜色定义) | Phase 1 首选方案统一修复: 补充 `@plugin "daisyui/theme"` 颜色定义,一次性修复全部 4 个使用 base-100 的组件 |
| 提示词标记位修改可能影响现有 LLM 分析质量 | 空参数替换为空字符串，保证不加参数时 prompt 与原始完全一致；标记位放在不影响核心指令的位置 |
| P1 全屏 diff 视图在 PyWebView 中可能有渲染差异 | Teleport to body + 测试 PyWebView 实际渲染 |
| P0 结果合并到 SuggestionPanel 需要扩展分组逻辑 | SuggestionPanel 已有按 source 过滤的机制，新增 llm_smart 分组风险低 |
| 三 tab 切换器增加了 Timeline.vue 复杂度 | tab 状态用简单的 ref 管理，不引入新依赖 |

---

## v2.1.0 候选功能 (留待后续版本)

以下功能受剪映 Skill 项目（https://github.com/luoluoluo22/jianying-editor-skill）启发，有价值但不适合放入 v2.0.1 补丁版本:

| 功能 | 来源启发 | 留到 v2.1.0 的原因 |
|------|----------|-------------------|
| **一键清理工作流** (D-20) | 剪映 Skill 一键式任务编排 | 需要任务编排能力 (串联多个 LLM 任务)，当前 `TaskManager` 仅支持单任务独立执行,不支持任务链 (见 `core/task_manager.py`) |
| **提示词风格预设** (D-21) | 剪映 Skill Chain of Thought 风格解构 | 需为每个场景维护一套参数组合，增加维护成本 |
| **精华模式独立布局** (D-13 后续) | -- | v2.0.1 先做基础 tab 切换，跳切 crossfade 预览/精华版直通导出留后续打磨 |
| **AI 解说词/文案生成** | 剪映 Skill 影视解说 | 需要新的 LLM 分析函数 + 全新的文案编辑 UI |
| **语义素材匹配** | 剪映 Skill Smart Rough Cut | 需要 B-Roll 素材管理 + 视频内容理解，超出预处理定位 |
| **自然语言全局指令** | 剪映 Skill Agent 式交互 | 需要 Agent 式任务编排层 |
| **时间轴精度规范** (float seconds) | 剪映 Skill 时间精度规则 | 涉及 EditDecision 时间格式重构，影响面大 |

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| ~~O-01~~ | ~~精华模式独立布局的具体设计~~ | **已解决** (D-13/D-18): v2.0.1 做右侧第三 tab 基础切换，独立布局留 v2.1.0 |
| ~~O-02~~ | ~~提示词参数注入到 prompt 的具体格式~~ | **已解决** (D-19): 标记位替换 ({{param}})，空值替换为空字符串 |
| O-03 | P1 全屏 diff 视图中"信任高置信度"批量操作后的确认流程 | 待定 -- Phase 2 实施时确定: 是立即 apply 还是需要二次确认 |

---

## 附录 A: Phase 1 根因分析

> 基于 `dev-2.0.1` 分支代码审计 (commit 038f669)。

### A.1 现状

`frontend/src/style.css` 的 DaisyUI 5 配置:

```css
@import "tailwindcss";

@plugin "daisyui" {
  themes: appleLight --default;
  prefix: false;
}
```

声明了自定义主题 `appleLight` 并标记为 `--default`,但**没有为该主题定义任何颜色变量**。

### A.2 根因

DaisyUI 5 要求自定义主题必须通过 `@plugin "daisyui/theme"` 块定义颜色。仅声明主题名而不定义颜色时,DaisyUI 不会生成 `--color-base-100` / `--color-base-200` / `--color-base-content` 等语义 CSS 变量,导致 `bg-base-100` / `text-base-content` / `border-base-300` 等工具类无对应变量,渲染为透明 (fallback 到 inherit/transparent)。

### A.3 受影响组件清单

以下 4 个组件使用了 `bg-base-100` 和/或 `border-base-300` 类,全部受影响:

| 组件 | 文件:行 | 使用的类 |
|------|---------|---------|
| TimelineSwitcher | `TimelineSwitcher.vue:13` | `bg-base-100 rounded-box border border-base-300` |
| HighlightModeView | `HighlightModeView.vue:200` | `border-base-300 bg-base-100` |
| SemanticSearchBar | `SemanticSearchBar.vue:139` | `border-base-300 bg-base-100 hover:bg-base-200` |
| SubtitleCorrectionReview | `SubtitleCorrectionReview.vue:255` | `border-base-300 bg-base-100` |

> **注**: `rounded-box` 也是 DaisyUI 语义类 (对应 `border-radius`),但由于 border-radius 的 fallback 是 0 而非 transparent,视觉影响不如背景色明显。

### A.4 为什么其他地方没暴露问题

项目主体 UI 使用自定义 `@theme` 中定义的颜色 (`--color-canvas`、`--color-ink`、`--color-parchment` 等),通过 `bg-canvas` / `text-ink` / `bg-parchment` 类引用,不依赖 DaisyUI 语义变量。只有上述 AI 功能相关组件 (v2.0.0 新增) 使用了 DaisyUI 语义类。

### A.5 Tailwind CSS 4 配置方式说明

本项目使用 Tailwind CSS 4,**没有 `tailwind.config.*` JS 配置文件**。所有配置通过 CSS 内的 `@import "tailwindcss"` / `@plugin "daisyui"` / `@theme` 指令完成。因此 Phase 1 修复仅在 `style.css` 中操作,不涉及 JS 配置文件。

---

## 附录 B: 当前代码架构快照

> 基于 `dev-2.0.1` 分支代码审计 (commit 038f669)。供 v2.0.1 实施时参考。

### B.1 后端 LLM 架构现状

#### B.1.1 Prompt 常量 (硬编码在 `core/llm_service.py`)

| 常量名 | 行号 | 用途 | 对应 func_key (Phase 3) |
|--------|------|------|-------------------------|
| `_SMART_DELETE_SYSTEM` | 437 | P0 智能删除 system prompt | `smart_delete` |
| `_SUBTITLE_CORRECTION_SYSTEM_A` | 581 | P1 字幕修正 模式 A (LLM 自纠正) | `subtitle_correction_a` |
| `_SUBTITLE_CORRECTION_SYSTEM_B` | 594 | P1 字幕修正 模式 B (参考稿对齐) | `subtitle_correction_b` |
| `_HIGHLIGHT_SYSTEM` | 824 | P2 精华提取 system prompt | `highlight` |
| `_SEARCH_SYSTEM` | 998 | P3 语义搜索 system prompt | `search` |

#### B.1.2 分析函数签名 (均无 prompt_override 参数)

```python
# core/llm_service.py

def analyze_smart_delete(
    segments: list[dict],
    existing_flagged_ids: set[str] | None = None,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:  # 行 449

def analyze_subtitle_correction(
    segments: list[dict],
    reference_text: str | None = None,  # None=模式A, 非空=模式B
    context_window: int = 3,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:  # 行 605

def analyze_highlights(
    segments: list[dict],
    target_duration_minutes: int = 10,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    chunk_callback: Callable[[list[dict]], None] | None = None,
) -> dict[str, Any]:  # 行 841

def semantic_search(
    query: str,
    segments: list[dict],
    top_k: int = 5,
    *,
    config: LlmConfig | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:  # 行 1008
```

#### B.1.3 LLM 配置模型 (`core/models.py:223`)

```python
class LlmConfig(BaseModel, frozen=True):
    provider: LlmProvider = LlmProvider.CUSTOM
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    timeout: int = 120

    def is_configured(self) -> bool:
        """检查 base_url + api_key + model 均非空。"""
        return bool(self.resolved_base_url() and self.api_key and self.resolved_model())
```

`is_configured()` 用于前端 D-12 (LLM 未配置时卡片置灰)。Phase 2 需在 `useLlmTasks` 中暴露此状态。

#### B.1.4 main.py LLM 任务处理链

| @expose 方法 | 行号 | 内部 handler | 调用的分析函数 |
|-------------|------|-------------|--------------|
| `start_smart_delete(timeline_id)` | 1916 | `_handle_smart_delete` (行 657) | `analyze_smart_delete` |
| `start_subtitle_correction(reference_text, timeline_id, context_window)` | 1942 | `_handle_subtitle_correction` (行 748) | `analyze_subtitle_correction` |
| `start_highlight(target_duration_minutes, timeline_id)` | 1999 | `_handle_highlight` (行 807) | `analyze_highlights` |
| `semantic_search(query, top_k, timeline_id)` | 2026 | (同步直接调用) | `semantic_search` |
| `confirm_all_from_source(source, min_confidence)` | 1980 | (委托 ProjectService) | -- |

> P0 结果写入 EditDecision 的 `source` 值为 `"llm_smart"` (`main.py:719`),AnalysisResult 的 `type` 值为 `"llm_smart_delete"` (`main.py:731`)。
> P2 结果写入 EditDecision 的 `source` 值为 `"llm_highlight"` (`main.py:870`)。

### B.2 前端架构现状

#### B.2.1 已存在的 AI 功能组件 (均为孤立状态)

| 组件 | 文件 | 功能 | 引用状态 |
|------|------|------|---------|
| SubtitleCorrectionReview | `SubtitleCorrectionReview.vue` (11.3KB) | P1 diff 审阅面板 | **无引用** |
| HighlightModeView | `HighlightModeView.vue` (6.0KB) | P2 精华提取视图 | **无引用** |
| SemanticSearchBar | `SemanticSearchBar.vue` (4.4KB) | P3 语义搜索栏 | **无引用** |

三个组件均接收 `llmConfigured: boolean` prop,内部处理未配置状态的 UI。

#### B.2.2 已存在的 LLM composable

| Composable | 文件 | 功能 | 引用状态 |
|-----------|------|------|---------|
| `useLlmTasks` | `useLlmTasks.ts` (6.9KB) | P0/P1/P2 启动 + 结果流式接收 (单例 state) | **无引用** |
| `useLlmSettings` | `useLlmSettings.ts` (0.9KB) | 仅 testConnection | 被 SettingsModal 引用 |
| `useLlmAnalysis` | `useLlmAnalysis.ts` (1.7KB) | 旧版 LLM 分析 composable | **无引用** |

`useLlmTasks` 暴露的 API: `startSmartDelete()`、`startSubtitleCorrection(referenceText)`、`startHighlight(targetMinutes)`、`confirmAllFromSource(source, minConfidence)` + 结果 ref (`smartDeleteResults`、`subtitleCorrectionResult`、`highlightResults`、`jumpCuts` 等) + 共享 state (`isRunning`、`progress`、`errorMsg`)。

> **注意**: `useLlmTasks` 不暴露 LLM 配置状态 (`is_configured`)。Phase 2 的 AIAssistantPanel 需要新增此能力。

#### B.2.3 WorkspacePage.vue 当前集成

WorkspacePage (**行 1-22**) 当前导入:
- `useAnalysis` (规则分析: filler/error/silence)
- `useExport` / `useEdit` / `useSegmentEdit` / `useUndoRedo`
- `usePluginManager` / `useUvAvailability`
- 组件: `Timeline` / `TimelineSwitcher` / `WaveformEditor` / `SearchReplaceBar` / `VideoControls` / `SubtitleOverlay` / `ProgressBar` / `SplitPanel`

**未导入**: `useLlmTasks` / `useLlmAnalysis` / 任何 AI 功能组件。

#### B.2.4 Timeline.vue 右侧面板现状

```vue
<!-- Timeline.vue:142-154 -->
<div class="w-72 border-l border-gray-200 flex flex-col">
  <SuggestionPanel
    :analysis-results="analysisResults"
    :edits="edits"
    :segments="segments"
    @confirm-edit="(editId) => emit('confirm-suggestion', editId)"
    @reject-edit="(editId) => emit('reject-suggestion', editId)"
    @confirm-all="emit('confirm-all')"
    @reject-all="emit('reject-all')"
    @seek="(t) => emit('seek-suggestion', t)"
  />
</div>
```

右侧面板宽度固定 `w-72` (288px),仅渲染 SuggestionPanel。Phase 2 需在此处新增 tab 切换器。

#### B.2.5 SuggestionPanel 分组现状

`SuggestionPanel.vue` 当前 groups computed 支持 3 种分组:
- `filler` (口头禅) -- 默认展开
- `error` (口误触发) -- 默认展开
- `silence` (静音检测) -- 默认折叠

`SuggestionItem.type` 联合类型: `"filler" | "error" | "silence"`。
Phase 2 需新增 `"llm_smart"` 分组 (source 过滤值 `"llm_smart"`)。

### B.3 Event 同步状态

`core/events.py` 与 `frontend/src/utils/events.ts` **已同步**,均定义了:

| 事件名 | 用途 |
|--------|------|
| `llm:smart_delete_progress` | P0 进度 (含增量结果) |
| `llm:smart_delete_completed` | P0 完成 |
| `llm:subtitle_correction_completed` | P1 完成 |
| `llm:highlight_progress` | P2 进度 (含增量结果) |
| `llm:highlight_completed` | P2 完成 |
| `llm:semantic_search_completed` | P3 完成 |
| `llm:analysis_failed` | 通用失败 |
| `llm:analysis_progress` / `llm:analysis_completed` | 通用进度/完成 (旧版) |
| `llm:token_usage` | token 用量 |

> Phase 2-3 不需新增事件,现有事件已覆盖全部需求。

### B.4 SettingsModal.vue 结构快照

| 元素 | 行号 | 现状 |
|------|------|------|
| 根 div | 394-398 | `fixed inset-0 z-50 flex items-center justify-center bg-black/40` (有遮罩) |
| 内层容器 | 399 | `bg-white rounded-2xl shadow-2xl w-[640px] max-w-[90vw] max-h-[85vh]` |
| Header | 400-402 | "Settings" (英文标题) |
| Tab 导航 | 406-425 | 4 tab: General / AI Engine / LLM / Export (英文 label) |
| General tab | 428+ | FFmpeg/GPU/uv |
| AI Engine tab | 628+ | ASR 引擎/模型/插件 |
| LLM tab | 944+ | Provider/Base URL/API Key/Model/Temperature + testConnection |
| Export tab | 1034+ | 编码器/质量/像素格式 |
| Teleport | -- | **未使用** |

Phase 4 需: (1) 新增 `<Teleport to="body">` (2) 根元素改为 `fixed inset-0 z-[9998] bg-white` 全屏无遮罩 (3) 内层改为 `flex h-full flex-col` (4) 可选中文化 tab label。

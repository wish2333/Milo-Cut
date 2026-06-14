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
2. **AI 分析入口不明晰** -- P0/P1/P2/P3 四个 AI 功能组件已开发但未接入工作区 UI
3. **AI 提示词不支持调整** -- 4 个 system prompt 硬编码在 Python 常量中，用户无法定制
4. **设置页是弹窗，空间不足** -- SettingsModal 作为 Modal 弹窗，内容拥挤

---

## 决策摘要

| 编号 | 决策 | 选择 |
|------|------|------|
| D-01 | Dropdown 修复策略 | 排查 DaisyUI 主题根因，必要时用显式颜色类 fallback |
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

#### 修复方案

- **首选**: 找到主题配置根因并修复 (可能只需在 CSS 中补充变量定义)
- **Fallback**: 将 `bg-base-100` 替换为显式颜色类:
  ```html
  <!-- 修复前 -->
  <ul class="dropdown-content z-50 menu p-2 shadow-lg bg-base-100 rounded-box w-64 border border-base-300">
  <!-- 修复后 (fallback) -->
  <ul class="dropdown-content z-50 menu p-2 shadow-xl bg-white text-gray-800 rounded-box w-64 border border-gray-200">
  ```

#### 影响范围

| 文件 | 变更 |
|------|------|
| `frontend/src/components/workspace/TimelineSwitcher.vue` | 修改 dropdown-content CSS 类 |
| `frontend/src/style.css` (可能) | 补充 DaisyUI 主题 CSS 变量 |
| `frontend/tailwind.config.*` (可能) | 补充 theme 配置 |

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
- 进度条 (复用 useLlmTasks 的 smartDeleteProgress)
- **结果不在此面板展示** -- 分析完成后自动切换到 `[建议]` tab
- 结果合并到 SuggestionPanel 作为新分组 "智能删除" (source=llm_smart)
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

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/AIAssistantPanel.vue` | **新增** | AI 助手面板: LLM 状态 + 功能卡片 (场景名+副标题) + 操作区 |
| `frontend/src/components/workspace/SubtitleCorrectionFullscreen.vue` | **新增** | P1 专属全屏 diff 视图 (基于 SubtitleCorrectionReview 扩展) |
| `frontend/src/components/workspace/Timeline.vue` | 修改 | 右侧面板从单面板改为三 tab 切换 (建议/AI 助手/精华) |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 修改 | 新增 llm_smart 分组类型 (D-15) |
| `frontend/src/pages/WorkspacePage.vue` | 修改 | 集成 useLlmTasks; 处理 P0 完成后自动切换建议 tab; P1 全屏 diff 触发 |
| `frontend/src/composables/useLlmTasks.ts` | 修改 | 暴露 LLM 配置状态; P0 完成后 emit 切换 tab 信号 |
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
    """将参数值格式化为 prompt 中的可读文本。"""
    if not value:
        return ""  # 空值 -> 空字符串
    # 按参数类型格式化
    if key == "custom_fillers":
        return f"\n额外需要检测的口头禅: {'、'.join(value)}"
    elif key == "glossary":
        return f"\n参考术语表 (优先使用这些正确写法): {'、'.join(value)}"
    elif key == "focus_keywords":
        return f"\n特别关注这些关键词的相关内容: {'、'.join(value)}"
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
| `core/llm_service.py` | 修改 | 从 llm_prompts 读取 prompt 替代硬编码常量; analyze_* 函数接受 prompt_override 参数 |
| `core/config.py` | 修改 | settings 默认值新增 llm_prompts 字段 |
| `core/models.py` | 修改 | Timeline 新增 llm_prompts 字段 (项目级覆盖) |
| `main.py` | 修改 | @expose: get_llm_prompts / update_llm_prompts / reset_llm_prompt |
| `frontend/src/components/workspace/SettingsOverlay.vue` | 修改 | LLM tab 新增提示词编辑子面板 |
| `frontend/src/composables/useLlmSettings.ts` | 修改 | 新增 getPrompts / updatePrompt / resetPrompt |

---

### Phase 4: 设置页全屏化 (D-09, D-10, D-11)

**目标**: SettingsModal 升级为全屏覆盖层，增大内容空间

#### 架构设计

##### 4.1 全屏覆盖层

将 `SettingsModal.vue` 重命名为 `SettingsOverlay.vue`，修改根元素:

```vue
<template>
  <Teleport to="body">
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
  </Teleport>
</template>
```

##### 4.2 保留现有 4 个 tab

- **通用**: FFmpeg/FFprobe 路径、GPU 检测、uv 可用性
- **AI 引擎**: ASR 引擎选择、模型管理、插件安装
- **LLM**: 连接配置 (Provider/Base URL/API Key/Model/Temperature) + 提示词编辑 (Phase 3 成果)
- **导出**: 编码器、质量参数、像素格式

内容区从 Modal 的 ~400px 高度扩展到 ~calc(100vh - 120px)，大幅减少拥挤。

##### 4.3 入口不变

保留 WelcomePage 现有设置按钮入口，仅替换组件引用:

```vue
<!-- WelcomePage.vue -->
<!-- 修改前 -->
<SettingsModal :visible="showSettings" @close="showSettings = false" />
<!-- 修改后 -->
<SettingsOverlay :visible="showSettings" @close="showSettings = false" />
```

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `frontend/src/components/workspace/SettingsModal.vue` | **重命名** → `SettingsOverlay.vue` + 重写根元素为全屏 |
| `frontend/src/pages/WelcomePage.vue` | 修改 | import 路径更新 |

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

| 模块 | 测试要点 |
|------|----------|
| Dropdown 修复 | TimelineSwitcher.test.ts: 验证 dropdown-content 背景可见性 |
| AI 助手面板 | AIAssistantPanel.test.ts: LLM 状态指示器 / 卡片置灰 / 场景名+副标题展示 / 卡片切换 |
| P0 结果合并 | SuggestionPanel.test.ts: 验证 llm_smart 分组渲染 + accept/reject |
| P1 全屏 diff | SubtitleCorrectionFullscreen.test.ts: 全屏触发 / diff 展示 / accept-reject / 视频跳转不切 tab |
| 精华 tab | Timeline 集成测试: 三 tab 切换 / HighlightModeView 渲染 |
| 提示词编辑 | 后端: llm_prompts.py 单元测试 (标记位注入/空值兼容/分层覆盖/重置); 前端: 简单模式/高级模式切换 |
| 设置全屏化 | SettingsOverlay.test.ts: 全屏布局 / tab 切换 |

---

## 风险与约束

| 风险 | 缓解措施 |
|------|----------|
| DaisyUI 主题问题可能是全局性的，影响其他组件 | Phase 1 先排查，如果是全局问题则统一修复 |
| 提示词标记位修改可能影响现有 LLM 分析质量 | 空参数替换为空字符串，保证不加参数时 prompt 与原始完全一致；标记位放在不影响核心指令的位置 |
| P1 全屏 diff 视图在 PyWebView 中可能有渲染差异 | Teleport to body + 测试 PyWebView 实际渲染 |
| P0 结果合并到 SuggestionPanel 需要扩展分组逻辑 | SuggestionPanel 已有按 source 过滤的机制，新增 llm_smart 分组风险低 |
| 三 tab 切换器增加了 Timeline.vue 复杂度 | tab 状态用简单的 ref 管理，不引入新依赖 |

---

## v2.1.0 候选功能 (留待后续版本)

以下功能受剪映 Skill 项目启发，有价值但不适合放入 v2.0.1 补丁版本:

| 功能 | 来源启发 | 留到 v2.1.0 的原因 |
|------|----------|-------------------|
| **一键清理工作流** (D-20) | 剪映 Skill 一键式任务编排 | 需要任务编排能力 (串联多个 LLM 任务)，当前 TaskManager 不支持任务链 |
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

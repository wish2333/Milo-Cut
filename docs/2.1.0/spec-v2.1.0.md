# v2.1.0 AI 能力深化 -- 实施规格说明

> **版本**: 2.1.0
> **主题**: AI 能力深化 -- 提示词风格预设、P1 完整 diff 审阅、一键清理工作流
> **基准**: v2.0.1 (基于 `dev-2.0.1` 分支)
> **分支**: `dev-2.1.0` (基于 `dev-2.0.1`)
> **类型**: 功能版本 (Feature Release)
> **预估工作量**: 6-8 周 (重量级版本)

---

## 背景与问题陈述

v2.0.0 完成了 AI 驱动的核心功能 (P0-P3)，v2.0.1 补齐了 AI 功能的 UI 入口、提示词参数化和设置页全屏化。但在实际使用中，AI 能力仍有三个核心缺口：

### 缺口 1: 提示词缺乏预设管理

v2.0.1 实现了参数化提示词系统 (`core/llm_prompts.py`)，每个 LLM 功能支持 `{{param}}` 标记位注入 + 高级模式 `system_override`。但用户只能维护"当前一套参数"，无法保存不同场景的参数组合。

**痛点**: 用户处理"学术报告"和"日常 vlog"需要完全不同的 `custom_fillers` / `glossary` 配置，每次切换场景都要手动重新填入参数。

### 缺口 2: P1 字幕修正审阅不完整

v2.0.1 的 P1 字幕修正只做了基础全屏视图 (统计 + 返回按钮)，缺少：
- 逐条 accept/reject 操作
- 行内 diff 展示 (原文 vs 修正)
- 批量操作 ("信任高置信度")
- corrections 列表未持久化 (仅任务返回值)

**痛点**: 用户运行 P1 后，无法在应用内逐条审阅修正建议，也无法关闭重开项目后继续审阅。

### 缺口 3: 缺乏多任务编排能力

当前 `TaskManager` 仅支持单任务独立执行，用户需要手动逐个运行规则分析 → P0 → P1 → P2，且各任务产出的 EditDecision 可能存在时间范围冲突，需人工排查。

**痛点**: 用户处理一个 30 分钟视频，需要手动运行 4 次分析，手动检查冲突，效率低下。

---

## 决策摘要

| 编号 | 决策 | 选择 |
|------|------|------|
| D-01 | v2.1.0 总体定位 | AI 能力深化 (延续 v2.0.x AI 主线) |
| D-02 | 功能模块范围 | 3 个模块: 提示词预设 + P1 完整 diff + 一键清理工作流 |
| D-03 | 版本发布策略 | 基于 `dev-2.0.1` 继续开发，v2.1.0 完成后合并 main |
| D-04 | Phase 实施顺序 | Phase 1 预设 → Phase 2 P1 diff → Phase 3 工作流 |
| D-05 | 工作量预期 | 重量级 (6-8 周)，含深度打磨 |

### 工作流相关决策

| 编号 | 决策 | 选择 |
|------|------|------|
| D-10 | 工作流编排方式 | 可配置任务链 (用户定义步骤序列) |
| D-11 | 步骤间依赖处理 | 交互式询问 (失败时弹出: 重试/跳过/终止) |
| D-12 | 数据依赖模型 | 串联式 (前步输出作为后步输入) |
| D-13 | 步骤结果冲突处理 | 冲突标记 + 强制解决 |
| D-14 | 数据传递机制 | 内存工作副本 (各步产出 EditDecision，不立即 apply) |
| D-15 | 冲突检测维度 | segment id 维度 (同 segment 多决策标记冲突) |
| D-16 | 冲突解决 UI | 专用冲突解决视图 (全屏) |
| D-17 | 冲突解决 UX | 可选流程 (可跳过冲突直接导出，默认保留所有决策) |
| D-18 | 工作流架构 | 新建独立 WorkflowEngine (与 TaskManager 并行) |
| D-19 | 工作流配置 UI | AI 助手面板内嵌 (工作流模式) |
| D-20 | 进度展示 | 多级进度 (总进度 + 每步骤子进度) |
| D-21 | 工作流可保存 | 可保存可复用 (命名工作流) |
| D-22 | 工作流取消行为 | 用户选择 (立即取消 / 当前步骤完成后停) |
| D-23 | 工作流存储 | 仅全局 (settings.json)，所有项目共享 |
| D-24 | 冲突数据结构 | 一次性快照 (执行完成时计算) |
| D-25 | 多 Timeline 处理 | 仅活动 timeline |
| D-26 | LLM 未配置表现 | 可配置不可启动 |
| D-27 | 并发工作流 | 单工作流串行 |
| D-28 | 工作副本生命周期 | 跨会话持久化 (完整快照文件) |
| D-29 | 规则分析集成 | 含规则分析步骤 (工作流可串联规则分析) |
| D-30 | 工作副本持久化粒度 | 完整快照文件 (segments + edits 独立 JSON) |
| D-31 | P3 与工作流关系 | P3 不进工作流 (即时查询型，保持独立) |
| D-32 | 预定义工作流模板 | 不内置 (用户从空白配置开始) |
| D-33 | 模型扩展方式 | 弱类型存储 (dict/json，不新建强类型模型) |

### 预设相关决策

| 编号 | 决策 | 选择 |
|------|------|------|
| D-40 | 预设来源 | 内置 + 用户自定义 |
| D-41 | 预设粒度 | 单功能预设 (每个 LLM 功能独立预设列表) |
| D-42 | 预设与参数关系 | 预设 = 参数快照 (custom_fillers + glossary + focus_keywords 等) |
| D-43 | 工作流步骤与预设 | 工作流步骤可选预设 (选预设则用预设参数，不选用当前参数) |
| D-44 | 内置预设数量 | 仅默认预设 (等同当前行为)，其他用户自建 |
| D-45 | 预设与工作流交互 | 预设可选 (工作流中选预设不强制覆盖) |

### P1 diff 相关决策

| 编号 | 决策 | 选择 |
|------|------|------|
| D-50 | P1 corrections 持久化 | 审阅后清除 (持久化期间可跨会话，审阅完成清除) |
| D-51 | diff 展示方式 | 行内 diff (删除线+红背景 / 绿背景标记新文本) |
| D-52 | 批量操作 | 信任高置信度 |
| D-53 | P1 与导出关系 | 直接更新 segment.text |
| D-54 | P1 数据结构 | 扩展 AnalysisResult (type=llm_subtitle_correction) |
| D-55 | diff 计算 | 后端 difflib + 前端解析 |
| D-56 | 中文 diff 处理 | 字符级 diff + 前端聚合连续差异 |
| D-57 | P1 全屏视图入口 | 双入口 (SuggestionPanel 摘要 + AI 助手全屏详细审阅) |

### 风险与测试决策

| 编号 | 决策 | 选择 |
|------|------|------|
| D-60 | 最大技术风险 | 冲突解决 UX |
| D-61 | 冲突 UX 缓解 | 冲突解决可选 (可跳过) |
| D-62 | 测试策略 | 后端单元 + 关键路径集成测试，前端保持现有密度 |

### 反馈整合决策 (外部 Review)

| 编号 | 决策 | 选择 |
|------|------|------|
| D-65 | 工作流 source 命名 (原 O-01) | `workflow:<wf_id>:<name>` 格式，ID 供程序识别 + name 供 UI 展示 |
| D-66 | "两者都保留"语义 (原 O-02) | 保留两条独立 EditDecision，冲突解决=决策去重非合并 |
| D-67 | 快照过期处理 (原 O-03) | 悲观锁 (工作流期间禁用 Timeline 编辑) + apply 时 content hash 校验 |
| D-68 | P1 置信度阈值默认值 (原 O-04) | 0.8 (ASR 经验: <0.8 多含 LLM 幻觉改写) |
| D-69 | 中文 diff 碎片优化 | 前端聚合: 相邻 delete/insert 块间距 <2 字符时视觉合并为"替换块" |
| D-70 | 工作流资源排队可见性 | UI 显示"等待系统资源..."状态 (区别于"分析中") |
| D-71 | 工作流取消过渡态 | "当前步骤完成后停"模式下 UI 进入 Cancelling... 状态，禁用后续勾选 |
| D-72 | 工作流心跳检测 | 新增 `workflow:heartbeat` 事件，前端超时检测任务中断 |
| D-73 | 预设模型联动 (未来) | 预留 save_preset 记录 model 字段，留待后续版本启用 |
| D-74 | 预设导入导出 (未来) | 预留 JSON 导入导出能力，留待社区分享场景启用 |

> D-73/D-74 标记为"未来"：Phase 1 数据结构预留字段，但不实现 UI，避免范围蔓延。

---

## 实施计划

### Phase 1: 提示词风格预设 (D-40 ~ D-45)

**目标**: 为每个 LLM 功能 (P0/P1/P2，不含 P3) 支持保存多套参数组合预设，用户可快速切换不同场景的提示词配置。

#### 架构设计

##### 1.1 预设数据模型

预设 = 参数快照。每个预设是某个 LLM 功能当前参数 (简单模式) + 可选 `system_override` (高级模式) 的完整拷贝。

```python
# settings.json 新增字段 (弱类型存储，D-33)
{
  "llm_prompt_presets": {
    "smart_delete": [
      {
        "id": "preset-uuid",
        "name": "学术报告",
        "params": {"custom_fillers": ["那么", "那个"]},
        "system_override": "",
        "model": "",               # D-73: 预留模型联动字段 (Phase 1 不启用 UI)
        "created_at": "2025-01-01T00:00:00"
      },
      {
        "id": "preset-uuid-2",
        "name": "日常 vlog",
        "params": {"custom_fillers": ["嗯", "就是"]},
        "system_override": "",
        "model": "",               # D-73: 预留
        "created_at": "2025-01-02T00:00:00"
      }
    ],
    "subtitle_correction_a": [
      {
        "id": "preset-uuid-3",
        "name": "技术术语",
        "params": {"glossary": ["Kubernetes", "微服务"]},
        "system_override": "",
        "model": "",               # D-73: 预留
        "created_at": "2025-01-01T00:00:00"
      }
    ]
    // highlight / subtitle_correction_b 同理
    // search 无参数化 (D-41 排除 P3)，不参与预设
  }
}
```

**预留字段说明 (D-73, D-74)**:
- `model`: 预留模型联动字段。同一套提示词在不同模型下表现差异巨大，后续版本可在 apply 预设时同时切换模型。Phase 1 仅存储不启用 UI。
- 预设 JSON 导入导出能力 (D-74) 同样预留，方便未来社区分享针对垂直领域 (医学讲座/游戏直播) 的优化参数。Phase 1 不实现。

**预设与现有 override 的关系**:
- 现有 `llm_prompts` (settings.json) 存储"当前生效"的 override，是全局唯一当前配置
- 预设是"候选配置集合"，应用预设 = 将预设内容写入 `llm_prompts[func_key]`
- 预设不直接生效，必须"应用"后才写入 `llm_prompts`

##### 1.2 后端 API 设计

新增 4 个 `@expose` 方法到 `main.py:MiloCutApi`:

| 方法 | 签名 | 功能 |
|------|------|------|
| `get_prompt_presets(func_key)` | `-> dict` | 获取指定功能的预设列表 |
| `save_prompt_preset(func_key, name, params, system_override)` | `-> dict` | 保存当前参数为新预设 (生成 UUID) |
| `apply_prompt_preset(func_key, preset_id)` | `-> dict` | 应用预设到 `llm_prompts` (等同于 update_llm_prompt) |
| `delete_prompt_preset(func_key, preset_id)` | `-> dict` | 删除指定预设 |

**后端实现位置**: 新建 `core/llm_presets.py` (与 `llm_prompts.py` 并列)，封装预设 CRUD 逻辑，`main.py` 方法委托调用。

```python
# core/llm_presets.py (新增)
def get_presets(func_key: str) -> list[dict]:
    """从 settings.json 读取指定功能的预设列表。"""

def save_preset(func_key: str, name: str, params: dict, system_override: str) -> dict:
    """保存新预设，返回含 UUID 的完整预设对象。"""

def apply_preset(func_key: str, preset_id: str) -> dict:
    """应用预设: 将预设 params + system_override 写入 llm_prompts。"""

def delete_preset(func_key: str, preset_id: str) -> dict:
    """删除预设。"""
```

##### 1.3 前端 UI 设计

在 SettingsModal 的 LLM tab 提示词编辑子面板中，功能选择器下方新增预设管理区:

```
┌─ LLM tab > 提示词编辑 ─────────────────────────────────┐
│                                                        │
│  功能: [智能删除 ▼]                                     │
│                                                        │
│  ┌─ 预设管理 ────────────────────────────────────────┐ │
│  │  预设: [学术报告 ▼]  [应用] [另存为预设] [删除]   │ │  <- 新增
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  ○ 简单模式  ○ 高级模式                                │
│                                                        │
│  (简单模式参数 textarea 或高级模式全量 textarea)        │
│                                                        │
│  [保存]  [重置为默认]                                  │
└────────────────────────────────────────────────────────┘
```

**交互流程**:
1. **另存为预设**: 点击后弹出输入框填预设名，将当前 textarea 中的参数保存为新预设
2. **应用预设**: 从下拉选择预设后点"应用"，textarea 内容被预设值覆盖 (等同于手动填入 + 保存)
3. **删除预设**: 从下拉选择预设后点"删除"，二次确认后删除

**内置预设 (D-44)**: 仅提供一个"默认"预设 (params 全空 + system_override 空)，等同当前行为。其他预设由用户自建。

##### 1.4 预设与工作流的交互 (D-43, D-45)

Phase 3 工作流配置时，每个步骤可选择一个预设。此交互在 Phase 3 实现时落地，Phase 1 仅完成预设 CRUD 基础设施。Phase 1 需确保 `get_prompt_presets` API 可被工作流配置 UI 复用。

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/llm_presets.py` | **新增** (~120 行) | 预设 CRUD 逻辑: get/save/apply/delete |
| `core/config.py` | 修改 (+1 行) | `_DEFAULT_SETTINGS` 新增 `llm_prompt_presets: {}` 字段 |
| `main.py` | 修改 (+60 行) | 新增 4 个 @expose 方法: get/save/apply/delete_prompt_preset |
| `frontend/src/composables/useLlmSettings.ts` | 修改 (+50 行) | 新增 PromptPreset 接口 + loadPresets/savePreset/applyPreset/deletePreset 方法 |
| `frontend/src/components/workspace/SettingsModal.vue` | 修改 (+80 行) | 提示词编辑区新增预设管理 UI (下拉 + 应用/另存/删除按钮) |
| `tests/test_llm_presets.py` | **新增** (~100 行) | 预设 CRUD 单元测试 |

#### 测试要点

| 模块 | 测试内容 |
|------|----------|
| `core/llm_presets.py` | save 生成 UUID + apply 正确写入 llm_prompts + delete 移除 + get 返回列表 |
| `main.py` @expose | 4 个方法的 envelope 返回格式 + 错误处理 (无效 func_key / preset_id) |
| 前端 SettingsModal | 预设下拉渲染 + 应用后 textarea 更新 + 另存为弹窗 + 删除确认 |

---

### Phase 2: P1 完整 diff 审阅 (D-50 ~ D-57)

**目标**: 将 P1 字幕修正从"自动 apply 全部修正"改为"生成 AnalysisResult → 用户逐条审阅 diff → 接受的修正才 apply"，并支持批量操作和跨会话审阅。

#### 现状与问题

当前 P1 流程 (v2.0.1):
1. `_handle_subtitle_correction` 调用 `analyze_subtitle_correction` 获取 corrections 列表
2. **立即调用** `project_service.apply_subtitle_corrections(corrections)` 直接修改所有 segment.text
3. corrections 列表仅在任务返回值和事件中，**未持久化**
4. 前端 AI 助手面板的 P1 全屏视图只显示统计 + 返回按钮，无逐条审阅

**核心矛盾**: 用户无法在修正 apply 前审阅，也无法拒绝特定修正。

#### 架构设计

##### 2.1 P1 流程重构 -- 从"自动 apply"到"审阅后 apply"

**新流程**:
```
LLM 分析 → corrections 存为 AnalysisResult(type=llm_subtitle_correction)
         → 前端展示 diff 审阅视图
         → 用户逐条 accept/reject
         → accept 的修正 apply 到 segment.text
         → 审阅完成后清除 AnalysisResult (D-50)
```

**关键变更**: `_handle_subtitle_correction` 不再调用 `apply_subtitle_corrections`，而是将 corrections 写入 `AnalysisResult`。

##### 2.2 corrections 持久化 -- 扩展 AnalysisResult (D-54)

AnalysisResult 现有结构 (`core/models.py:151`):
```python
class AnalysisResult(BaseModel, frozen=True):
    id: str
    type: Literal["filler", "error", "duplicate", "punctuation",
                  "llm_smart_delete", "llm_subtitle_correction", "llm_highlight"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""
```

**注意**: `llm_subtitle_correction` 已在 type Literal 中 (v2.0.0 已预留)。但当前 `detail: str` 字段无法存储结构化 corrections。

**方案**: 利用 `detail` 字段存储 JSON 序列化的 corrections 列表 (弱类型扩展，不改模型结构):

```python
import json

# 每个 segment 的修正存为一条 AnalysisResult
for corr in corrections:
    result = AnalysisResult(
        id=f"corr-{corr['segment_id']}-{uuid4().hex[:8]}",
        type="llm_subtitle_correction",
        segment_ids=[corr["segment_id"]],
        confidence=corr.get("confidence", 0.8),
        detail=json.dumps({
            "original_text": original_seg_text,  # 从 segment 查找
            "corrected_text": corr["corrected_text"],
            "changes": corr.get("changes", []),
            "category": corr.get("category", "none"),
        }, ensure_ascii=False),
    )
```

> **为何不改模型**: AnalysisResult.detail 是 `str`，存 JSON 字符串是已有的弱类型模式。新建模型会增加迁移成本。与 D-33 (弱类型存储) 一致。

**存储位置**: AnalysisResult 列表已存在于 `Timeline.analysis` 结构中，无需新增字段。审阅完成后从 analysis 列表中移除该 type 的记录 (D-50)。

##### 2.3 diff 计算 -- 后端 difflib + 前端解析 (D-55, D-56)

**后端**: 新增 `core/diff_service.py`，使用 `difflib.SequenceMatcher` 计算字符级 diff:

```python
# core/diff_service.py (新增)
import difflib

def compute_inline_diff(original: str, corrected: str) -> dict:
    """计算行内 diff，返回 token 序列供前端渲染。

    中文采用字符级 diff (D-56)，前端聚合连续差异片段。

    Returns:
        {
            "tokens": [
                {"text": "这是", "type": "equal"},
                {"text": "错字", "type": "delete"},
                {"text": "正字", "type": "insert"},
                {"text": "示例", "type": "equal"},
            ]
        }
    """
    matcher = difflib.SequenceMatcher(None, original, corrected)
    tokens = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            tokens.append({"text": original[i1:i2], "type": "equal"})
        elif tag == "replace":
            tokens.append({"text": original[i1:i2], "type": "delete"})
            tokens.append({"text": corrected[j1:j2], "type": "insert"})
        elif tag == "delete":
            tokens.append({"text": original[i1:i2], "type": "delete"})
        elif tag == "insert":
            tokens.append({"text": corrected[j1:j2], "type": "insert"})
    return {"tokens": tokens}
```

**中文 diff 策略 (D-56, D-69)**: 字符级 diff + 前端聚合。difflib 对中文字符串按 Unicode 字符比较，连续的 delete+insert 块在前端渲染为一个"替换"片段 (红删除 + 绿插入相邻显示)。

**碎片优化 (D-69)**: difflib 字符级比较在处理"句子重组"时会产生细碎的 delete/insert 交替。前端渲染时执行聚合规则: **相邻 delete 块和 insert 块间距 <2 字符时，视觉合并为一个"替换块"**，减少认知负担。

```typescript
// 前端聚合伪代码 (D-69)
function aggregateDiffTokens(tokens: DiffToken[]): DiffToken[] {
  const result: DiffToken[] = []
  for (let i = 0; i < tokens.length; i++) {
    const tok = tokens[i]
    const prev = result[result.length - 1]
    // 相邻 delete + insert (间距 0) 或中间仅隔 <2 个 equal 字符 → 合并为 replace 块
    if ((prev?.type === 'delete' && tok.type === 'insert') ||
        (prev?.type === 'insert' && tok.type === 'delete')) {
      // 合并为一对 (visual replace block)
      result[result.length - 1] = {
        type: 'replace',
        deleteText: prev.type === 'delete' ? prev.text : tok.text,
        insertText: prev.type === 'insert' ? prev.text : tok.text,
      }
    } else {
      result.push(tok)
    }
  }
  return result
}
```

**置信度阈值 (D-52, D-68)**: "信任高置信度"批量操作的默认阈值 **0.8**。ASR 经验表明 0.8 以下的修正往往包含 LLM 幻觉改写。阈值在前端 UI 可调 (滑块或输入框)，默认值 0.8 作为保守起点。

**新增 @expose 方法**:

| 方法 | 签名 | 功能 |
|------|------|------|
| `get_subtitle_corrections(timeline_id)` | `-> dict` | 获取当前持久化的 P1 corrections (AnalysisResult 列表，解析 detail JSON) |
| `compute_diff(original, corrected)` | `-> dict` | 计算单条 diff (或批量) |
| `accept_correction(result_id)` | `-> dict` | 接受单条修正: apply 到 segment.text + 移除 AnalysisResult |
| `reject_correction(result_id)` | `-> dict` | 拒绝单条修正: 仅移除 AnalysisResult |
| `accept_high_confidence_corrections(timeline_id, threshold)` | `-> dict` | 批量接受高置信度修正 (D-52) |
| `clear_subtitle_corrections(timeline_id)` | `-> dict` | 清除所有未审阅的 P1 corrections |

##### 2.4 前端 diff 审阅 UI (D-51, D-57)

**双入口设计 (D-57)**:

1. **SuggestionPanel 摘要入口**: P1 corrections 作为新分组 `llm_correction` 显示在建议面板，每条显示原文→修正预览 (截断)，点击展开行内 diff
2. **AI 助手全屏审阅入口**: 点击"查看修正结果 (N 条)"触发全屏 diff 审阅视图 (复用 v2.0.1 的全屏 Teleport 框架)

**全屏 diff 审阅视图布局**:

```
┌─ 字幕修正审阅 (全屏覆盖层) ──────────────────────────────┐
│                                                          │
│  高置信度修正 (N)                 [信任全部高置信度]       │  <- D-52 批量操作
│  ┌──────────────────────────────────────────────────────┐│
│  │ 00:05  [同音错字]  置信度 0.92                        ││
│  │  这是由于优化原因 → 这是由于优化原因                   ││  <- 行内 diff (D-51)
│  │       ^^^^^^^      ^^^^^^^                           ││     红删除线 + 绿背景
│  │  [接受] [拒绝]                                        ││
│  └──────────────────────────────────────────────────────┘│
│  ┌──────────────────────────────────────────────────────┐│
│  │ 00:12  [专有名词]  置信度 0.88                        ││
│  │  ...                                                  ││
│  └──────────────────────────────────────────────────────┘│
│                                                          │
│  低置信度修正 (N)  (默认折叠)                              │
│  ...                                                     │
│                                                          │
│  [返回]                                          N/M 已审 │
└──────────────────────────────────────────────────────────┘
```

**行内 diff 渲染 (D-51)**:
- `delete` token: `<span class="line-through bg-red-100 text-red-700">{{text}}</span>`
- `insert` token: `<span class="bg-green-100 text-green-700">{{text}}</span>`
- `equal` token: `<span>{{text}}</span>`

**交互**:
- 点击时间链接: 仅视频跳转播放位置 (D-17 沿用)
- accept/reject 后该条从列表移除 (动画过渡)
- "信任全部高置信度" (D-52): 批量 accept 所有 confidence ≥ threshold 的修正

##### 2.5 apply 逻辑重构

现有 `apply_subtitle_corrections` 拆分为:
- `store_subtitle_corrections(corrections)`: 将 corrections 存为 AnalysisResult (新)
- `accept_subtitle_correction(result_id, segment_id, corrected_text)`: 单条 apply (新)
- 原 `apply_subtitle_corrections` 保留用于批量接受高置信度

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/diff_service.py` | **新增** (~60 行) | difflib 行内 diff 计算 |
| `core/project_service.py` | 修改 (+80/-20 行) | 新增 store/accept/reject_subtitle_correction + 批量接受方法; apply_subtitle_corrections 重构 |
| `main.py` | 修改 (+70 行) | `_handle_subtitle_correction` 不再自动 apply; 新增 6 个 @expose 方法 |
| `frontend/src/composables/useLlmTasks.ts` | 修改 (+40 行) | 新增 corrections 列表 state + load/accept/reject/acceptHighConfidence 方法 |
| `frontend/src/components/workspace/SubtitleCorrectionReview.vue` | 修改 (+150 行) | 完善全屏 diff 审阅: 行内 diff 渲染 + accept/reject + 批量操作 + 置信度分组 |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 修改 (+30 行) | 新增 llm_correction 分组 (摘要入口) |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 修改 (+20 行) | P1 "查看修正结果" 按钮触发全屏审阅 (完善 v2.0.1 基础实现) |
| `tests/test_diff_service.py` | **新增** (~80 行) | diff 计算单元测试 (中文/英文/无变化) |
| `tests/test_subtitle_correction_review.py` | **新增** (~120 行) | store/accept/reject/批量逻辑测试 |

#### 测试要点

| 模块 | 测试内容 |
|------|----------|
| `core/diff_service.py` | 中文 diff token 序列 + 相同文本无 diff + 纯插入/删除/替换 |
| corrections 持久化 | store 写入 AnalysisResult + detail JSON 解析 + 审阅后清除 |
| accept/reject | accept 正确修改 segment.text + reject 不修改 + AnalysisResult 移除 |
| 批量接受 | threshold 过滤 + 批量 apply + 未达 threshold 的保留 |
| 前端 diff 渲染 | 行内 diff token 颜色标注 + 置信度分组折叠 |

---

### Phase 3: 一键清理工作流 (D-10 ~ D-33)

**目标**: 新建独立 WorkflowEngine，支持用户配置任务链 (规则分析 + P0 + P1 + P2 的任意串联)，串联执行并管理步骤间数据传递、冲突检测、跨会话恢复。

#### 架构设计

##### 3.1 WorkflowEngine -- 独立于 TaskManager (D-18)

**设计原则**: WorkflowEngine 是编排层，TaskManager 是执行层。WorkflowEngine 不直接执行任务，而是通过 TaskManager 调度单个任务，自己管理链式逻辑、状态、冲突。

```python
# core/workflow_engine.py (新增)
class WorkflowEngine:
    """任务链编排引擎。

    管理工作流的创建、执行、取消、状态查询。
    内部通过 TaskManager 执行单个步骤，自己管理:
    - 步骤间数据传递 (内存工作副本)
    - 失败处理 (交互式询问)
    - 冲突检测 (segment id 维度)
    - 跨会话恢复 (快照文件)
    """

    def __init__(self, task_manager: TaskManager, project_service, emit_fn):
        self._task_manager = task_manager
        self._project_service = project_service
        self._emit = emit_fn
        self._active_workflow: dict | None = None  # 仅支持单工作流串行 (D-27)
        self._cancel_event = threading.Event()

    # --- 工作流定义 CRUD (存储在 settings.json, D-23) ---

    def get_workflows(self) -> dict:
        """获取所有已保存的工作流定义。"""

    def save_workflow(self, name: str, steps: list[dict]) -> dict:
        """保存工作流定义。steps = [{"type": "full_analysis"|"llm_smart_delete"|..., "preset_id": "..."}]"""

    def delete_workflow(self, workflow_id: str) -> dict:
        """删除工作流定义。"""

    # --- 工作流执行 ---

    def start_workflow(self, workflow_id: str, timeline_id: str) -> dict:
        """启动工作流: 创建工作副本 + 逐步执行。"""

    def cancel_workflow(self, mode: str = "immediate") -> dict:
        """取消工作流。mode = "immediate" | "after_current" (D-22)"""

    def handle_step_failure(self, action: str) -> dict:
        """处理步骤失败。action = "retry" | "skip" | "abort" (D-11)"""

    def get_workflow_status(self) -> dict:
        """获取当前工作流执行状态 + 进度。"""

    # --- 冲突检测 ---

    def detect_conflicts(self) -> dict:
        """检测工作副本中的 EditDecision 冲突 (segment id 维度)。"""
```

##### 3.2 工作流定义模型 (弱类型存储, D-33)

工作流定义存储在 `settings.json` (D-23 仅全局):

```python
# settings.json 新增字段
{
  "workflows": [
    {
      "id": "wf-uuid",
      "name": "我的深度清理",
      "steps": [
        {"type": "full_analysis", "preset_id": null},
        {"type": "llm_smart_delete", "preset_id": "preset-uuid-1"},
        {"type": "llm_subtitle_correction", "preset_id": "preset-uuid-3"}
      ],
      "created_at": "2025-01-01T00:00:00"
    }
  ]
}
```

**步骤类型** (D-29 含规则分析):

| step type | 对应 TaskType | 说明 |
|-----------|--------------|------|
| `full_analysis` | `TaskType.FULL_ANALYSIS` | 规则分析 (filler + error + silence) |
| `llm_smart_delete` | `TaskType.LLM_SMART_DELETE` | P0 智能删除 |
| `llm_subtitle_correction` | `TaskType.LLM_SUBTITLE_CORRECTION` | P1 字幕修正 |
| `llm_highlight` | `TaskType.LLM_HIGHLIGHT` | P2 精华提取 |

> P3 语义搜索不进入工作流 (D-31)，保持独立即时查询。

##### 3.3 内存工作副本与跨会话持久化 (D-14, D-28, D-30)

**工作副本 = 完整快照文件** (D-30):

工作流启动时创建快照，包含当前 timeline 的 segments + 所有步骤产出的 EditDecision。

```python
# 快照文件路径: data/projects/<project_name>/<timeline_id>_workflow_<wf_instance_id>.json
{
  "workflow_id": "wf-uuid",
  "workflow_instance_id": "wfi-uuid",
  "workflow_name": "我的深度清理",
  "timeline_id": "tl-xxx",
  "created_at": "...",
  "status": "running"|"paused"|"completed"|"cancelled",
  "current_step_index": 1,
  "total_steps": 3,
  "segments_snapshot": [...],  # 工作流启动时的 segments 完整拷贝
  "accumulated_edits": [...],  # 各步骤产出的 EditDecision (不 apply 到真实 project)
  "step_results": [
    {"index": 0, "type": "full_analysis", "status": "completed", "edits_count": 15},
    {"index": 1, "type": "llm_smart_delete", "status": "running", "edits_count": 0}
  ]
}
```

**生命周期 (D-28)**:
- 工作流启动: 创建快照文件
- 执行中: 每步完成后更新快照 (append edits + 更新 current_step_index)
- 跨会话恢复: 应用启动时扫描 `data/projects/*/` 下的 `*_workflow_*.json`，检测 `status=running/paused` 的快照，提示用户恢复
- 审阅完成: 用户 apply 或放弃后删除快照文件

##### 3.4 串联式数据传递 (D-12, D-14)

**核心机制**: 每步产出 EditDecision 写入 `accumulated_edits`，下一步骤的输入 segments 来自 `segments_snapshot` (工作流启动时的原始拷贝)。

**为何不用前步修改后的 segments**: EditDecision 是"建议"不是"已执行"，工作流期间不修改真实 segments。各步骤基于同一原始 segments 分析，避免前步错误传播。

> **与冲突检测的关系**: 各步骤基于相同 segments 独立分析，必然可能对同一 segment 产出不同建议 (如 P0 建议删除 + P1 建议修正字幕)。这正是冲突检测的输入 (见 3.5)。

##### 3.5 冲突检测 -- segment id 维度 (D-13, D-15, D-24)

**一次性快照** (D-24): 工作流全部步骤完成后，对 `accumulated_edits` 执行一次冲突检测:

```python
def detect_conflicts(self) -> dict:
    """检测 accumulated_edits 中的冲突。

    冲突定义: 同一 segment_id 有多个不同 action 或不同 source 的 EditDecision。
    (D-15: segment id 维度)

    Returns:
        {
            "conflicts": [
                {
                    "segment_id": "seg-xxx",
                    "segment_text": "...",
                    "decisions": [
                        {"edit_id": "...", "action": "delete", "source": "llm_smart", "step": 1},
                        {"edit_id": "...", "action": "keep", "source": "llm_highlight", "step": 2},
                    ]
                }
            ],
            "total_conflicts": N
        }
    """
    # 按 segment_id 分组 accumulated_edits
    seg_groups = defaultdict(list)
    for edit in self._snapshot["accumulated_edits"]:
        if edit.get("target_type") == "segment" and edit.get("target_id"):
            seg_groups[edit["target_id"]].append(edit)

    conflicts = []
    for seg_id, edits in seg_groups.items():
        if len(edits) > 1:
            # 同一 segment 有多个 decision = 冲突
            conflicts.append({
                "segment_id": seg_id,
                "segment_text": self._get_segment_text(seg_id),
                "decisions": [...],
            })
    return {"conflicts": conflicts, "total_conflicts": len(conflicts)}
```

##### 3.6 冲突解决 UI -- 专用视图 + 可选流程 (D-16, D-17)

工作流完成后，若有冲突，前端弹出冲突解决视图 (全屏覆盖层):

```
┌─ 冲突解决 (3 个冲突) ────────────────────────────────────┐
│                                                          │
│  [跳过冲突解决]                              ← D-17 可选 │
│                                                          │
│  冲突 1/3                                                │
│  ┌──────────────────────────────────────────────────────┐│
│  │ 00:05  "这是由于优化原因导致的..."                    ││
│  │                                                      ││
│  │  P0 智能删除 建议: 删除 (语义重复)                    ││
│  │  P2 精华提取 建议: 保留 (高密度片段)                  ││
│  │                                                      ││
│  │  [保留删除] [保留精华] [两者都保留]                   ││
│  └──────────────────────────────────────────────────────┘│
│  ...                                                     │
│                                                          │
│  [跳过冲突解决]  [全部解决后继续]                         │
└──────────────────────────────────────────────────────────┘
```

**可选流程 (D-17, D-61)**: 用户可点"跳过冲突解决"，默认保留所有 EditDecision (各自独立呈现到 SuggestionPanel)，不强制解决。解决冲突是优化体验而非强制阻塞。

**冲突解决操作语义 (D-66)**:
- **保留删除**: 移除 P2 的 keep decision，仅保留 P0 的 delete decision
- **保留精华**: 移除 P0 的 delete decision，仅保留 P2 的 keep decision
- **两者都保留**: 保留两条独立 EditDecision。冲突解决的本质是"决策去重"而非"决策合并"，用户认为 P0 删除和 P2 精华都对，则两者都存在于建议列表，交由用户在主界面最终决定

##### 3.7 工作流配置 UI -- AI 助手面板内嵌 (D-19)

在 AIAssistantPanel 新增"工作流"模式 (与现有"功能卡片"模式并列):

```
┌─ AI 助手 ───────────────────────────────────────────────┐
│                                                          │
│  ● LLM 已配置 (test-model)                               │
│                                                          │
│  [单功能]  [工作流]                  ← 模式切换           │
│                                                          │
│  (工作流模式:)                                           │
│  已保存工作流: [我的深度清理 ▼]  [启动]  [新建]  [删除]   │
│                                                          │
│  ── 或新建工作流 ──                                       │
│  名称: [____________________]                            │
│  步骤:                                                    │
│   ☑ [规则分析]                                            │
│   ☑ [P0 智能删除]  预设: [学术报告 ▼]                    │
│   ☐ [P1 字幕修正]  预设: [技术术语 ▼]                    │
│   ☐ [P2 精华提取]  预设: [默认 ▼]                        │
│  [保存工作流]                                             │
│                                                          │
│  (执行中:)                                               │
│  总进度: ████████░░░░ 2/3                                │  <- D-20 多级进度
│  ✓ 规则分析 (15 条建议)                                   │
│  ⟳ P0 智能删除 (30/50)                                   │
│  ○ P2 精华提取                                            │
│  [取消 ▼]  ← D-22: 立即取消 / 当前步骤完成后停            │
└──────────────────────────────────────────────────────────┘
```

**LLM 未配置 (D-26)**: 工作流模式可配置可保存，但含 LLM 步骤的工作流启动时检查 LLM 配置，未配置则提示"请先配置 LLM"并阻止启动。

##### 3.8 步骤失败处理 -- 交互式询问 (D-11)

某步骤失败时，通过事件通知前端弹出选择:

```typescript
// 前端监听 workflow:step_failed 事件
onEvent("workflow:step_failed", (data) => {
  showFailureDialog({
    stepName: data.step_name,
    error: data.error,
    options: ["重试", "跳过", "终止"],
    onSelect: (action) => {
      call("handle_step_failure", { action })
    }
  })
})
```

##### 3.9 工作流取消 -- 用户选择 (D-22)

取消按钮为下拉菜单:
- **立即取消**: 设置 cancel_event，当前步骤通过 TaskManager 取消，已完成步骤保留
- **当前步骤完成后停 (D-71)**: 等待当前步骤完成，不启动后续步骤。选择此模式后 UI 进入 **Cancelling...** 状态: 禁用后续步骤的勾选，进度条标注"等待当前步骤完成"，取消按钮变为"立即取消 (不等待)"供二次确认

##### 3.10 工作流完成后 -- apply 到真实 project

工作流全部完成 + 冲突解决 (或跳过) 后，用户决定是否 apply:

- **Apply**: 将 `accumulated_edits` 写入真实 project 的 EditDecision 列表 (source 标记 `workflow:<wf_id>:<name>` 格式，D-65)，删除快照文件
- **放弃**: 删除快照文件，不影响真实 project

**快照过期校验 (D-67)**: apply 前计算当前 timeline segments 的 content hash，与快照中记录的 `segments_hash` 比对:
- Hash 一致: 正常 apply
- Hash 不一致: 弹窗"检测到 Timeline 已发生显著变化，工作流已失效，请重新创建"，阻止 apply

##### 3.11 悲观锁 -- Timeline 编辑锁定 (D-67)

工作流启动后，对应 timeline 进入**锁定状态**:
- 前端禁用该 timeline 的手动编辑 (WaveformEditor / SuggestionPanel 的 accept/reject 按钮置灰)
- 后端 @expose 方法检查 timeline 锁定状态，编辑类方法返回"此 timeline 正在运行工作流，请等待完成或取消工作流"
- 工作流完成/取消/放弃后自动解锁

> **为何选择悲观锁**: 工作流基于某一时刻的 segments 快照进行深度分析，若运行期间手动编辑，apply 时必然语义错乱。悲观锁从源头杜绝冲突，比 apply 时再检测更安全。

##### 3.12 资源排队可见性 (D-70)

工作流步骤通过 TaskManager 调度时，可能因信号量 (Semaphore) 占用而进入 QUEUED 状态。尤其是 `TaskType.FULL_ANALYSIS` 是重负载任务，若用户同时运行导出，工作流步骤可能排队等待。

**UI 处理**: 步骤状态区分三种:
- `running`: 步骤正在执行 (显示进度条)
- `queued`: 步骤已提交但等待系统资源 (显示"等待系统资源..."，进度条暂停)
- `pending`: 未轮到 (灰色)

前端通过 `workflow:step_started` 事件的 `status` 字段区分 running/queued。

##### 3.13 心跳检测 (D-72)

对于耗时极长的 4 步骤工作流，若后端因异常崩溃，前端需检测任务中断:

**机制**: WorkflowEngine 每 15 秒 emit `workflow:heartbeat`。前端 useWorkflow 设置 45 秒超时计时器，每次收到心跳重置。超时未收到心跳则提示"工作流可能已中断，请检查应用状态"。

#### 新增事件

| 事件名 | 方向 | 用途 |
|--------|------|------|
| `workflow:started` | Py→JS | 工作流启动 |
| `workflow:step_started` | Py→JS | 步骤开始 (含 step_index, step_name, status: running/queued) |
| `workflow:step_progress` | Py→JS | 步骤进度 (复用现有 task:progress) |
| `workflow:step_completed` | Py→JS | 步骤完成 (含 edits_count) |
| `workflow:step_failed` | Py→JS | 步骤失败 (触发交互式询问) |
| `workflow:completed` | Py→JS | 工作流全部完成 (触发冲突检测) |
| `workflow:cancelled` | Py→JS | 工作流取消 |
| `workflow:conflicts_detected` | Py→JS | 冲突检测结果 |
| `workflow:heartbeat` | Py→JS | 心跳 (每 15s，D-72)，前端超时检测任务中断 |

> 需同步更新 `core/events.py` 和 `frontend/src/utils/events.ts`。共 9 个 workflow:* 事件。

#### 影响范围

| 文件 | 变更 | 说明 |
|------|------|------|
| `core/workflow_engine.py` | **新增** (~400 行) | WorkflowEngine: 定义 CRUD + 执行 + 取消 + 冲突检测 + 快照管理 |
| `core/events.py` | 修改 (+9 行) | 新增 9 个 workflow:* 事件常量 (含 heartbeat) |
| `core/config.py` | 修改 (+1 行) | `_DEFAULT_SETTINGS` 新增 `workflows: []` 字段 |
| `main.py` | 修改 (+120 行) | 新增 ~10 个 @expose 方法委托 WorkflowEngine |
| `frontend/src/utils/events.ts` | 修改 (+9 行) | 新增 9 个 workflow:* 事件常量 (含 heartbeat) |
| `frontend/src/composables/useWorkflow.ts` | **新增** (~200 行) | 工作流 state + 配置 + 执行 + 取消 + 冲突解决 |
| `frontend/src/components/workspace/AIAssistantPanel.vue` | 修改 (+200 行) | 新增工作流模式 (模式切换 + 配置 UI + 进度 + 取消) |
| `frontend/src/components/workspace/ConflictResolutionView.vue` | **新增** (~150 行) | 冲突解决全屏视图 |
| `tests/test_workflow_engine.py` | **新增** (~200 行) | 引擎单元测试: 定义 CRUD + 执行流程 + 冲突检测 |
| `tests/test_workflow_integration.py` | **新增** (~150 行) | 集成测试: 多步骤串联 + 失败处理 + 快照恢复 |

#### 测试要点

| 模块 | 测试内容 |
|------|----------|
| 工作流定义 CRUD | save/get/delete + 无效步骤类型校验 |
| 执行流程 | 步骤顺序执行 + 内存副本隔离真实 project |
| 失败处理 | retry 重试 + skip 跳过继续 + abort 终止 |
| 冲突检测 | 同 segment 多决策检测 + 无冲突场景 + target_type=range 不检测 |
| 快照持久化 | 快照创建 + 跨会话恢复检测 + apply 后删除 |
| 取消 | 立即取消 (cancel_event) + 当前步骤完成后停 |
| 集成 | 规则分析 + P0 + P1 全流程串联 + 冲突解决 |

---

## Phase 实施汇总

| Phase | 主题 | 预估工作量 | 内容 |
|-------|------|-----------|------|
| 1 | 提示词风格预设 | 1-1.5 周 | 预设 CRUD + 设置页 UI + 工作流预留接口 |
| 2 | P1 完整 diff 审阅 | 2-2.5 周 | diff 计算 + corrections 持久化 + 审阅 UI 重构 |
| 3 | 一键清理工作流 | 3-4 周 | WorkflowEngine + 内存副本 + 冲突检测 + UI |
| **合计** | | **6-8 周** | |

**Phase 顺序考量 (D-04)**:
- Phase 1 先做: 最简单，为 Phase 3 工作流步骤选预设提供基础设施
- Phase 2 其次: P1 完整 diff 是工作流中 P1 步骤的前置条件 (审阅后的 corrections 才能进入工作流串联)
- Phase 3 最后: 最复杂，依赖 Phase 1 的预设 + Phase 2 的 P1 审阅流程

---

## 风险与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| **冲突解决 UX 复杂** (D-60 最大风险) | 高 | 冲突解决可选 (D-17/D-61): 用户可跳过，默认保留所有决策。不强制阻塞导出。"两者都保留"(D-66)语义为保留两条独立决策 |
| 中文 diff 可读性 (difflib 字符级) | 中 | 字符级 diff + 前端聚合连续差异 (D-56) + 碎片优化 (D-69): 相邻 delete/insert 间距 <2 字符视觉合并为替换块。Phase 2 测试验证，若仍差再评估 jieba |
| 工作流状态一致性 (跨会话恢复) | 中 | 完整快照文件 (D-30) + 每步更新快照。恢复时校验快照完整性 |
| 快照与 Timeline 不同步 (用户手动编辑) | 中 | 悲观锁 (D-67): 工作流期间禁用 Timeline 编辑 + apply 时 content hash 校验，不一致则提示重新创建 |
| WorkflowEngine 与 TaskManager 并发交互 | 中 | WorkflowEngine 不持有 TaskManager 的锁，仅通过 create_task/cancel_task API 交互。单工作流串行 (D-27) 避免竞态 |
| 工作流步骤排队误认为挂死 | 低 | 资源排队可见性 (D-70): 步骤状态区分 running/queued/pending，queued 时显示"等待系统资源..." |
| 后端崩溃导致工作流静默中断 | 低 | 心跳检测 (D-72): 每 15s emit workflow:heartbeat，前端 45s 超时检测并提示 |
| P1 流程重构影响现有行为 | 中 | 原 `apply_subtitle_corrections` 保留为批量接受方法。新增 store/accept/reject 方法，渐进迁移 |
| 快照文件膨胀 (长视频 segments 拷贝) | 低 | 快照是临时文件，apply/放弃后删除。长视频 segments ~1MB，可接受 |

---

## 测试策略

### 后端测试 (D-62: 单元 + 集成)

| 模块 | 测试文件 | 覆盖 |
|------|----------|------|
| 预设 CRUD | `tests/test_llm_presets.py` | save/apply/delete + UUID 生成 + settings.json 持久化 |
| diff 计算 | `tests/test_diff_service.py` | 中文/英文/混合 + 无变化 + 纯插入/删除 |
| P1 审阅逻辑 | `tests/test_subtitle_correction_review.py` | store/accept/reject + 批量接受 + 审阅后清除 |
| 工作流引擎 | `tests/test_workflow_engine.py` | 定义 CRUD + 执行流程 + 失败处理 + 冲突检测 |
| 工作流集成 | `tests/test_workflow_integration.py` (标记 @pytest.mark.integration) | 多步骤串联 + 快照恢复 + 端到端 |

### 前端测试 (保持现有密度)

| 模块 | 测试文件 | 覆盖 |
|------|----------|------|
| 预设 UI | SettingsModal 测试扩展 | 预设下拉 + 应用 + 另存为 + 删除 |
| P1 diff 审阅 | SubtitleCorrectionReview 测试扩展 | 行内 diff 渲染 + accept/reject + 批量 |
| 工作流 UI | AIAssistantPanel 测试扩展 | 模式切换 + 配置 + 进度展示 |
| 冲突解决 | ConflictResolutionView 测试新建 | 冲突渲染 + 解决操作 + 跳过 |

### 测试基线

| 维度 | v2.0.1 基线 | v2.1.0 目标 |
|------|------------|------------|
| 后端单元测试 | 231 | ~260 (+29 预估) |
| 后端集成测试 | 15 | ~18 (+3 工作流集成) |
| 前端测试 | 147 | ~165 (+18 预估) |
| ruff + ESLint | 零错误 | 零错误 |

---

## 开放问题

| 编号 | 问题 | 状态 |
|------|------|------|
| ~~O-01~~ | ~~工作流 apply 到真实 project 时，accumulated_edits 的 source 字段命名规范~~ | **已解决** (D-65): `workflow:<wf_id>:<name>` 格式。保留 ID 供程序唯一识别，保留 name 供 UI 展示 (如 SuggestionPanel 标注"来自：深度清理工作流") |
| ~~O-02~~ | ~~冲突解决视图中"两者都保留"操作的具体语义~~ | **已解决** (D-66): 保留两条独立 EditDecision。冲突解决的本质是"决策去重"而非"决策合并"，用户认为 P0 删除和 P2 精华都对，则两者都存在于建议列表，交由用户在主界面最终决定 |
| ~~O-03~~ | ~~跨会话恢复时，如果原始 project 的 segments 已变化 (用户手动编辑)，快照如何处理~~ | **已解决** (D-67): 采用悲观锁 + Hash 校验。工作流启动后禁用 Timeline 手动编辑；apply 时计算 segments content hash，若与快照不一致则弹窗"检测到 Timeline 已发生显著变化，工作流已失效，请重新创建" |
| ~~O-04~~ | ~~P1 diff 审阅中，置信度 threshold 的默认值~~ | **已解决** (D-68): 默认 0.8。ASR 经验表明 0.8 以下的修正往往包含 LLM 幻觉改写，0.8 作为保守起点，后续根据用户反馈调整 |

---

## 附录 A: 现状代码架构快照 (v2.0.1 基线)

> 基于 `dev-2.0.1` 分支 (commit db26fcd)。供 v2.1.0 实施时参考。收录相关模块的当前代码实现，标注后续 Phase 的改造点。

---

### A.1 提示词系统现状 (Phase 1 基线)

#### A.1.1 `core/llm_prompts.py` (250 行，完整)

```python
"""LLM prompt management with parameterized placeholders.

Centralizes the 5 system prompts used across P0-P3 features and supports:
- Parameterized placeholders ({{param}}) for simple-mode customization
- Full-text override for advanced-mode editing
- Layered persistence (global settings < project override < hardcoded default)

Prompt keys:
    smart_delete          -- P0 智能删除
    subtitle_correction_a -- P1 字幕修正 模式 A (LLM 自纠正)
    subtitle_correction_b -- P1 字幕修正 模式 B (参考稿对齐)
    highlight             -- P2 精华提取
    search                -- P3 语义搜索 (无参数化)
"""

from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Prompt constants (with {{param}} placeholders for customization)
# ------------------------------------------------------------------

_SMART_DELETE_SYSTEM = """你是视频剪辑助手。用户以 JSON 格式提供一组转录片段。
请识别其中可安全删除的片段:
1. semantic_dup: 语义重复 -- 同一观点换措辞重述 (规则引擎只能识别字面重复)
2. self_correct: 无触发词口误 -- 说错后自然纠正的完整区域
3. filler_phrase: 上下文口头禅 -- 无实义过渡句如"然后接下来就是我们要讲的那个"
{{custom_fillers}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase"}]
只输出建议删除的片段，无需删除的不要输出。
"""

_SUBTITLE_CORRECTION_SYSTEM_A = """你是视频字幕纠错专家。用户以 JSON 格式提供转录片段列表。
请修正每个片段中的 ASR 识别错误:
- 同音错字 (如"由于"误识为"优化")
- 专有名词错误 (如人名、地名、术语)
- 断句/标点问题
{{glossary}}
注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容。

输出格式: JSON 数组，每个元素对应输入中的一个片段:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明1", "变更说明2"], "category": "homophone|proper_noun|punctuation|none"}]
如果某片段无需修正，corrected_text 设为与原文相同，category 设为 "none"。
"""

_SUBTITLE_CORRECTION_SYSTEM_B = """你是视频字幕对齐专家。用户以 JSON 格式提供 ASR 转录片段和参考稿全文。
请将每个 ASR 片段与参考稿内容对齐，用参考稿内容修正 ASR 文本错误。
{{glossary}}
注意: 不要改变片段的原始时间戳 (start/end)。只修正文本内容使其与参考稿一致。

输出格式: JSON 数组:
[{"segment_id": "片段ID", "corrected_text": "修正后的文本", "changes": ["变更说明"], "category": "reference_aligned|none", "confidence": 0.0到1.0}]
如果某片段无需修正，corrected_text 设为与原文相同，category 设为 "none"。
"""

_HIGHLIGHT_SYSTEM = """你是演讲视频内容分析师。用户以 JSON 格式提供转录片段列表。
请识别其中的高信息密度片段，用于生成精华版剪辑。

高信息密度片段包括:
- 核心论点和主要观点
- 关键数据、统计数字、实验结果
- 精彩类比、比喻、案例
- 重要结论和总结
{{focus_keywords}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "highlight_reason": "亮点理由", "density": "high|medium"}]

只输出识别到的亮点片段，普通内容不要输出。
用户会指定目标精华时长，请按信息密度优先级 (high > medium) 选取。
"""

_SEARCH_SYSTEM = """你是内容检索助手。用户以 JSON 格式提供转录片段列表和搜索查询。
请找出与查询语义最相关的片段 (不仅是字面匹配，包括语义关联)。

输出格式: JSON 数组，按相关度降序排列
[{"segment_id": "片段ID", "relevance": 0.0到1.0, "match_reason": "匹配原因"}]

只输出最相关的前 K 个片段，K 由用户指定。relevance 为 1.0 表示完全匹配，0.0 表示不相关。
"""

# ------------------------------------------------------------------
# Default prompt registry  ← Phase 1 预设的 "默认预设" 数据源
# ------------------------------------------------------------------

DEFAULT_PROMPTS: dict[str, dict[str, Any]] = {
    "smart_delete": {
        "system": _SMART_DELETE_SYSTEM,
        "params": {"custom_fillers": []},
    },
    "subtitle_correction_a": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_A,
        "params": {"glossary": []},
    },
    "subtitle_correction_b": {
        "system": _SUBTITLE_CORRECTION_SYSTEM_B,
        "params": {"glossary": []},
    },
    "highlight": {
        "system": _HIGHLIGHT_SYSTEM,
        "params": {"focus_keywords": []},
    },
    "search": {
        "system": _SEARCH_SYSTEM,
        "params": {},
    },
}


# ------------------------------------------------------------------
# Placeholder injection
# ------------------------------------------------------------------

def _format_param(key: str, value: list[str], func_key: str) -> str:
    """将参数值格式化为 prompt 中的可读文本。空值或仅含空白都替换为空串。"""
    cleaned = [v.strip() for v in value if v and v.strip()]
    if not cleaned:
        return ""
    if key == "custom_fillers":
        return f"\n额外需要检测的口头禅: {'、'.join(cleaned)}"
    elif key == "glossary":
        return f"\n参考术语表 (优先使用这些正确写法): {'、'.join(cleaned)}"
    elif key == "focus_keywords":
        return f"\n特别关注这些关键词的相关内容: {'、'.join(cleaned)}"
    return ""


def _inject_placeholders(prompt: str, params: dict, func_key: str) -> str:
    """将参数值替换到 prompt 中的 {{param}} 标记位。空值→空串。"""
    result = prompt
    for key, value in params.items():
        placeholder = f"{{{{{key}}}}}"
        if placeholder not in result:
            continue
        formatted = _format_param(key, value, func_key)
        result = result.replace(placeholder, formatted)
    return result


# ------------------------------------------------------------------
# Effective prompt resolution  ← Phase 1 预设 apply 后由此函数读取
# ------------------------------------------------------------------

def get_effective_prompt(
    func_key: str,
    project_prompts: dict | None = None,
) -> str:
    """获取生效的 system prompt，合并标记位参数注入。

    读取优先级: 项目覆盖 > 全局默认 > 硬编码常量
    """
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        logger.warning(f"Unknown prompt key: {func_key}")
        return ""

    from core.config import load_settings
    settings = load_settings()
    global_prompts = settings.get("llm_prompts", {})
    global_override = global_prompts.get(func_key, {})

    # 项目级覆盖优先
    if project_prompts and func_key in project_prompts:
        override = project_prompts[func_key]
    else:
        override = global_override

    # 高级模式: 使用 system_override (如果存在且非空)
    system_override = override.get("system_override")
    if system_override and system_override.strip():
        return system_override

    # 简单模式: 标记位替换
    system = default["system"]
    params = {**default["params"], **override.get("params", {})}
    return _inject_placeholders(system, params, func_key)


def get_default_prompt_text(func_key: str) -> str:
    """获取指定功能的默认 prompt 原文 (含标记位)。用于前端"查看默认值"。"""
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        return ""
    return default["system"]


def get_default_params(func_key: str) -> dict[str, list[str]]:
    """获取指定功能的默认参数定义。用于前端简单模式表单渲染。"""
    default = DEFAULT_PROMPTS.get(func_key)
    if default is None:
        return {}
    return default["params"]
```

> **Phase 1 改造点**: `DEFAULT_PROMPTS` 是预设"默认预设"的数据源。预设 = params 快照 + 可选 system_override。预设 apply 时写入 `settings.json` 的 `llm_prompts[func_key]`，`get_effective_prompt` 无需修改即可读取生效。

#### A.1.2 `main.py` 提示词 @expose 方法 (3 个，完整)

```python
    @expose
    def get_llm_prompts(self) -> dict:
        """Read all LLM prompt configurations (defaults + user overrides).

        Returns:
            {"success": True, "data": {"defaults": {...}, "overrides": {...}}}
        """
        from core.llm_prompts import DEFAULT_PROMPTS, get_default_params

        defaults = {}
        for key in DEFAULT_PROMPTS:
            defaults[key] = {
                "system": DEFAULT_PROMPTS[key]["system"],
                "params": get_default_params(key),
            }

        settings = self._load_settings_raw()
        overrides = settings.get("llm_prompts", {})

        return {"success": True, "data": {"defaults": defaults, "overrides": overrides}}

    @expose
    def update_llm_prompt(self, func_key: str, updates: dict) -> dict:
        """Update a single LLM prompt configuration.

        Args:
            func_key: One of DEFAULT_PROMPTS keys.
            updates: {"system_override": str|None, "params": {...}}
        """
        from core.llm_prompts import DEFAULT_PROMPTS

        if func_key not in DEFAULT_PROMPTS:
            return {"success": False, "error": f"Unknown prompt key: {func_key}"}

        settings = self._load_settings_raw()
        prompts = settings.get("llm_prompts", {})

        existing = prompts.get(func_key, {})
        if "system_override" in updates:
            val = updates["system_override"]
            existing["system_override"] = val if val and val.strip() else None
        if "params" in updates:
            existing["params"] = updates["params"]

        prompts[func_key] = existing
        settings["llm_prompts"] = prompts

        return self.update_settings({"llm_prompts": prompts})

    @expose
    def reset_llm_prompt(self, func_key: str) -> dict:
        """Reset a single LLM prompt to its hardcoded default."""
        from core.llm_prompts import DEFAULT_PROMPTS

        if func_key not in DEFAULT_PROMPTS:
            return {"success": False, "error": f"Unknown prompt key: {func_key}"}

        settings = self._load_settings_raw()
        prompts = settings.get("llm_prompts", {})
        prompts.pop(func_key, None)
        settings["llm_prompts"] = prompts

        return self.update_settings({"llm_prompts": prompts})

    def _load_settings_raw(self) -> dict:
        """Load raw settings dict (internal helper for prompt management)."""
        from core.config import load_settings
        return load_settings()
```

> **Phase 1 改造点**: 新增 4 个 @expose: `get_prompt_presets` / `save_prompt_preset` / `apply_prompt_preset` / `delete_prompt_preset`。`apply_prompt_preset` 内部委托 `update_llm_prompt` 写入 override。

#### A.1.3 `frontend/src/composables/useLlmSettings.ts` (106 行，完整)

```typescript
import { ref } from "vue"
import { call } from "@/bridge"

export interface LlmConnectionResult {
  model: string
  response_time_ms: number
}

const testing = ref(false)
const testResult = ref<{ success: boolean; message: string } | null>(null)

// Phase 3: Prompt management state
export interface PromptDefaults {
  system: string
  params: Record<string, string[]>
}

export interface PromptOverride {
  system_override?: string | null
  params?: Record<string, string[]>
}

export interface LlmPromptsData {
  defaults: Record<string, PromptDefaults>
  overrides: Record<string, PromptOverride>
}

const promptsData = ref<LlmPromptsData | null>(null)
const loadingPrompts = ref(false)

export function useLlmSettings() {
  async function testConnection(): Promise<boolean> {
    testing.value = true
    testResult.value = null
    const res = await call<LlmConnectionResult>("test_llm_connection")
    testing.value = false
    if (res.success && res.data) {
      testResult.value = {
        success: true,
        message: `Connected to ${res.data.model} (${res.data.response_time_ms}ms)`,
      }
      return true
    }
    testResult.value = {
      success: false,
      message: res.error ?? "Connection failed",
    }
    return false
  }

  // Phase 3: Load all prompt configurations (defaults + overrides)
  async function loadPrompts(): Promise<void> {
    loadingPrompts.value = true
    const res = await call<LlmPromptsData>("get_llm_prompts")
    loadingPrompts.value = false
    if (res.success && res.data) {
      promptsData.value = res.data
    }
  }

  // Phase 3: Update a single prompt's override
  async function updatePrompt(
    funcKey: string,
    updates: PromptOverride,
  ): Promise<boolean> {
    const res = await call<{ func_key: string }>(
      "update_llm_prompt", funcKey, updates,
    )
    if (res.success) {
      await loadPrompts()
      return true
    }
    return false
  }

  // Phase 3: Reset a single prompt to default
  async function resetPrompt(funcKey: string): Promise<boolean> {
    const res = await call<{ func_key: string }>(
      "reset_llm_prompt", funcKey,
    )
    if (res.success) {
      await loadPrompts()
      return true
    }
    return false
  }

  return {
    testing, testResult, testConnection,
    // Phase 3: Prompt management
    promptsData, loadingPrompts, loadPrompts, updatePrompt, resetPrompt,
  }
}
```

> **Phase 1 改造点**: 新增 `PromptPreset` 接口 + `loadPresets` / `savePreset` / `applyPreset` / `deletePreset` 方法，调用对应 4 个新 @expose。

#### A.1.4 `SettingsModal.vue` 提示词编辑 UI 片段 (LLM tab 内)

```vue
<!-- Function selector -->
<div class="flex items-center gap-2 mb-3">
  <label class="text-xs text-gray-500">功能:</label>
  <select :value="selectedPromptKey"
          class="px-2 py-1 text-xs border border-gray-300 rounded"
          @change="handlePromptKeyChange(($event.target as HTMLSelectElement).value)">
    <option v-for="f in promptFuncKeys" :key="f.key" :value="f.key">
      {{ f.label }}
    </option>
  </select>
</div>

<!-- ← Phase 1 新增: 预设管理区 (下拉 + 应用/另存为/删除) -->

<!-- Mode toggle -->
<div class="flex items-center gap-3 mb-3">
  <label class="flex items-center gap-1 text-xs">
    <input type="radio" value="simple" v-model="promptEditMode" />
    简单模式
  </label>
  <label class="flex items-center gap-1 text-xs">
    <input type="radio" value="advanced" v-model="promptEditMode" />
    高级模式
  </label>
</div>

<!-- Simple mode: parameter fields -->
<div v-if="promptEditMode === 'simple'" class="space-y-3">
  <div v-for="(_text, paramKey) in promptParamText" :key="paramKey">
    <label class="block text-xs font-medium text-gray-600 mb-1">
      {{ promptParamLabels[paramKey] ?? paramKey }}
    </label>
    <textarea v-model="promptParamText[paramKey]"
              class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
              rows="3" :placeholder="'每行一个'"></textarea>
  </div>
  <p v-if="Object.keys(promptParamText).length === 0" class="text-xs text-gray-400">
    此功能无可配置参数
  </p>
</div>

<!-- Advanced mode: full prompt textarea -->
<div v-else class="space-y-2">
  <label class="block text-xs font-medium text-gray-600">
    完整提示词 (含标记位)
  </label>
  <textarea v-model="promptSystemOverride"
            class="w-full p-2 text-xs border border-gray-300 rounded font-mono"
            rows="10" :placeholder="placeholderHint"></textarea>
  <details class="text-xs text-gray-500">
    <summary class="cursor-pointer">查看默认提示词</summary>
    <pre class="mt-2 p-2 bg-gray-50 rounded text-xs overflow-x-auto whitespace-pre-wrap">
      {{ promptsData?.defaults?.[selectedPromptKey]?.system ?? '(无)' }}
    </pre>
  </details>
</div>

<!-- Action buttons -->
<div class="flex items-center gap-2 mt-3">
  <button class="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700
                 disabled:opacity-50" :disabled="promptSaving"
          @click="handleSavePrompt">
    {{ promptSaving ? '保存中...' : '保存' }}
  </button>
  <button class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
          @click="handleResetPrompt">
    重置为默认
  </button>
  <span v-if="promptStatusMsg" class="text-xs text-green-600">
    {{ promptStatusMsg }}
  </span>
</div>
```

> **Phase 1 改造点**: 在功能选择器与模式切换之间插入"预设管理区" (预设下拉 + 应用/另存为/删除按钮)。

---

### A.2 P1 字幕修正现状 (Phase 2 基线)

#### A.2.1 `core/models.py` AnalysisResult + EditDecision + Timeline 模型

```python
# core/models.py:102
class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""                                    # "llm_smart" / "llm_highlight" / "llm_subtitle_correction" ...
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING             # pending / confirmed / rejected
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None                        # segment id (当 target_type="segment")


# core/models.py:151
class AnalysisResult(BaseModel, frozen=True):
    id: str
    type: Literal["filler", "error", "duplicate", "punctuation",
                  "llm_smart_delete", "llm_subtitle_correction",   # ← P1 type 已预留
                  "llm_highlight"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""                                     # ← Phase 2 存 JSON 序列化的 corrections


# core/models.py:260
class Timeline(BaseModel, frozen=True):
    """Independent timeline -- owns a complete transcript + edits + analysis."""
    id: str
    label: str
    source: str = "manual"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    parent_id: str = ""
    transcript: TranscriptData = Field(default_factory=TranscriptData)
    edits: list[EditDecision] = Field(default_factory=list)
    analysis: AnalysisData = Field(default_factory=AnalysisData)
    # Phase 3: Project-level LLM prompt overrides (per-timeline).
    llm_prompts: dict = Field(default_factory=dict)
```

> **Phase 2 改造点**: `AnalysisResult.type` 的 `"llm_subtitle_correction"` 已预留。Phase 2 将 corrections 存入 `detail` 字段 (JSON 字符串)，无需新增模型字段。`EditDecision.source` 将新增 `"llm_subtitle_correction"` 值。

#### A.2.2 `core/project_service.py:1180` apply_subtitle_corrections (当前实现，完整)

```python
    def apply_subtitle_corrections(self, corrections: list[dict]) -> dict:
        """Apply LLM subtitle corrections to the active timeline.

        Uses layered fault tolerance: does not fail entirely on partial
        mismatches. Matches by segment_id, applies what matches, and marks
        uncovered segments with dirty_flags.llm_uncovered.

        Args:
            corrections: List of dicts with segment_id, corrected_text,
                changes, category, confidence.

        Returns:
            {"success": True, "data": {corrected_count, uncovered_count,
             uncovered_ids, orphaned_count, partial}}
            {"success": False, "error": str} on complete mismatch.
        """
        if self._current is None:
            return {"success": False, "error": "No project is open"}

        from core.llm_service import (
            TimestampCorruptionError,
            _assert_timestamps_unchanged,
            _check_correction_confidence,
        )

        timeline = self.active_timeline
        seg_map = {s.id: s for s in timeline.transcript.segments}
        total = len(timeline.transcript.segments)

        # Match corrections to segments
        matched: list[tuple[Segment, dict]] = []
        uncovered_ids: list[str] = []

        for seg in timeline.transcript.segments:
            corr = next((c for c in corrections if c["segment_id"] == seg.id), None)
            if corr:
                matched.append((seg, corr))
            else:
                uncovered_ids.append(seg.id)

        extra_corrections = [c for c in corrections if c["segment_id"] not in seg_map]

        # Complete mismatch
        if len(matched) == 0 and total > 0:
            return {
                "success": False,
                "error": "No segment_id matched (LLM output completely mismatched)",
            }

        if len(matched) < total:
            logger.warning(
                f"Partial correction coverage: {len(matched)}/{total} segments matched, "
                f"{len(uncovered_ids)} uncovered, {len(extra_corrections)} orphaned"
            )

        # Apply corrections  ← Phase 2 核心改造: 拆分为 store + accept/reject
        corr_map = {seg_id: corr for seg, corr in matched for seg_id in [seg.id]}
        new_segments: list[Segment] = []
        rolled_back_count = 0

        for seg in timeline.transcript.segments:
            corr = corr_map.get(seg.id)
            if corr:
                corrected_text = str(corr.get("corrected_text", seg.text))
                conf = _check_correction_confidence(seg.text, corrected_text)
                new_flags = {**seg.dirty_flags, "llm_corrected": True}
                if conf["low_confidence"]:
                    new_flags["llm_low_confidence"] = True

                corrected = seg.model_copy(
                    update={"text": corrected_text, "dirty_flags": new_flags}
                )

                # Timestamp assertion
                try:
                    _assert_timestamps_unchanged(
                        seg.start, seg.end, corrected.start, corrected.end,
                        segment_id=seg.id,
                    )
                    new_segments.append(corrected)
                except TimestampCorruptionError:
                    rolled_back_count += 1
                    new_segments.append(seg)
            else:
                uncovered = seg.model_copy(
                    update={
                        "dirty_flags": {**seg.dirty_flags, "llm_uncovered": True}
                    }
                )
                new_segments.append(uncovered)

        # Update timeline: new segments + invalidate analysis
        self._update_active_timeline(
            transcript=timeline.transcript.model_copy(update={"segments": new_segments}),
            analysis=timeline.analysis.model_copy(update={"last_run": None}),
        )

        logger.info(
            f"Applied subtitle corrections: {len(matched)} matched, "
            f"{len(uncovered_ids)} uncovered, {rolled_back_count} rolled back"
        )

        return {
            "success": True,
            "data": {
                "corrected_count": len(matched) - rolled_back_count,
                "uncovered_count": len(uncovered_ids),
                "uncovered_ids": uncovered_ids,
                "orphaned_count": len(extra_corrections),
                "rolled_back_count": rolled_back_count,
                "partial": len(matched) < total,
            },
        }
```

> **Phase 2 改造点**: 此方法当前**直接修改 segment.text**，无审阅环节。Phase 2 将其拆分:
> - `store_subtitle_corrections(corrections)` -- 写入 AnalysisResult (detail 存 JSON)，不修改 segment
> - `accept_subtitle_correction(result_id)` -- 单条 apply 到 segment.text + 移除 AnalysisResult
> - `reject_subtitle_correction(result_id)` -- 仅移除 AnalysisResult
> - 原 `apply_subtitle_corrections` 保留，供"信任高置信度"批量接受复用

#### A.2.3 `main.py:757` _handle_subtitle_correction (当前实现，完整)

```python
    def _handle_subtitle_correction(self, task, cancel_event, progress_cb):
        """Run LLM subtitle correction on the active timeline."""
        if self._project.current is None:
            raise ValueError("No project open")

        from core.llm_service import analyze_subtitle_correction

        project = self._project.current
        timeline_id = task.payload.get(
            "timeline_id", project.active_timeline_id
        )
        timeline = project.get_timeline(timeline_id)
        if timeline is None:
            raise ValueError(f"Timeline {timeline_id} not found")

        reference_text = task.payload.get("reference_text", "")
        context_window = task.payload.get("context_window", 3)

        segments = [
            s.model_dump()
            for s in timeline.transcript.segments
            if s.type == SegmentType.SUBTITLE
        ]
        if not segments:
            raise ValueError("No subtitle segments to correct")

        # Phase 3: resolve effective prompts for both modes
        from core.llm_prompts import get_effective_prompt

        project_prompts = (
            timeline.llm_prompts if hasattr(timeline, "llm_prompts") else None
        )
        effective_prompt_a = get_effective_prompt(
            "subtitle_correction_a", project_prompts
        )
        effective_prompt_b = get_effective_prompt(
            "subtitle_correction_b", project_prompts
        )

        result = analyze_subtitle_correction(
            segments,
            reference_text=reference_text if reference_text else None,
            context_window=context_window,
            cancel_event=cancel_event,
            progress_cb=progress_cb,
            system_prompt_a=effective_prompt_a,
            system_prompt_b=effective_prompt_b,
        )

        if not result.get("success"):
            error = result.get("error", "Subtitle correction failed")
            self._emit("llm:analysis_failed", {"error": error})
            raise RuntimeError(error)

        corrections = result["data"]["corrections"]
        token_usage = result["data"]["token_usage"]

        # Apply corrections to project  ← Phase 2 核心改造点
        apply_result = self._project.apply_subtitle_corrections(corrections)

        if not apply_result["success"]:
            raise RuntimeError(
                apply_result.get("error", "Failed to apply subtitle corrections")
            )

        self._emit("llm:subtitle_correction_completed", apply_result["data"])
        self._emit("llm:token_usage", token_usage)

        return {
            "corrections": corrections,
            "apply_result": apply_result["data"],
            "token_usage": token_usage,
        }
```

> **Phase 2 改造点**: 第 `apply_result = self._project.apply_subtitle_corrections(corrections)` 行替换为 `self._project.store_subtitle_corrections(corrections, timeline_id)`。不再自动 apply，corrections 存为 AnalysisResult 供前端审阅。新增 6 个 @expose 方法 (get_subtitle_corrections / compute_diff / accept_correction / reject_correction / accept_high_confidence_corrections / clear_subtitle_corrections)。

---

### A.3 TaskManager 现状 (Phase 3 基线)

#### A.3.1 `core/task_manager.py` 核心调度逻辑 (完整)

```python
class TaskManager:
    """High-concurrency task manager with HoL-blocking fix and FIFO ordering."""

    HEAVY_TASKS: set[TaskType] = {
        TaskType.EXPORT_VIDEO,
        TaskType.EXPORT_AUDIO,
        TaskType.TRANSCRIPTION,
        TaskType.SILENCE_DETECTION,
    }
    LIGHT_TASKS: set[TaskType] = {
        TaskType.WAVEFORM_GENERATION,
        TaskType.PROXY_GENERATION,
    }

    def __init__(self, emit_fn: Callable[[str, Any], None]) -> None:
        self._emit = emit_fn
        self._tasks: dict[str, MiloTask] = {}
        self._queue: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._handlers: dict[
            TaskType, Callable[[MiloTask, threading.Event, Callable[[float, str], None]], dict]
        ] = {}
        self._sequence = itertools.count()
        # Concurrency control
        self._heavy_semaphore = threading.Semaphore(1)  # GPU/CPU-intensive
        self._light_semaphore = threading.Semaphore(3)  # I/O-bound
        self._worker_thread: threading.Thread | None = None
        self._worker_running = False

    def register_handler(self, task_type, handler):
        """Register a handler function for a task type."""
        self._handlers[task_type] = handler

    def create_task(self, task_type: str, payload: dict | None = None,
                    priority: str = "normal") -> dict:
        """Create task with priority level and auto-dispatch to queue."""
        try:
            tt = TaskType(task_type)
        except ValueError:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

        task_id = str(uuid.uuid4())[:8]
        task = MiloTask(id=task_id, type=tt, status=TaskStatus.QUEUED, payload=payload or {})

        with self._lock:
            self._tasks[task_id] = task
            priority_map = {"high": 0, "normal": 1, "low": 2}
            priority_num = priority_map.get(priority, 1)
            self._queue.put((priority_num, next(self._sequence), task_id))

        self._ensure_worker()
        return {"success": True, "data": task.model_dump()}

    def cancel_task(self, task_id: str) -> dict:
        """Cancel task -- works for both queued and running tasks."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return {"success": False, "error": f"Task not found: {task_id}"}
            # Case A: Task still queued
            if task.status == TaskStatus.QUEUED:
                self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
                return {"success": True, "data": self._tasks[task_id].model_dump()}
            # Case B: Task running -- trigger cancel event
            if task.status == TaskStatus.RUNNING:
                event = self._cancel_events.get(task_id)
                if event:
                    event.set()
                self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})
                return {"success": True, "data": self._tasks[task_id].model_dump()}
        return {"success": False, "error": f"Task {task_id} is {task.status}, cannot cancel"}

    # ------------------------------------------------------------------
    # Internal: worker dispatch and execution
    # ------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        """Start worker thread if not already running."""
        with self._lock:
            if not self._worker_running:
                self._worker_running = True
                self._worker_thread = threading.Thread(
                    target=self._process_queue, daemon=True,
                )
                self._worker_thread.start()

    def _process_queue(self) -> None:
        """Dispatch loop: only pulls tasks and spawns execution threads.
        This thread NEVER blocks on semaphore acquisition."""
        while True:
            try:
                _priority_num, _seq, task_id = self._queue.get(timeout=5.0)
            except queue.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker_running = False
                        return
                continue

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                if task.status == TaskStatus.CANCELLED:
                    continue

            # Spawn separate thread for semaphore + execution (HoL blocking fix)
            t = threading.Thread(
                target=self._threaded_execution_wrapper,
                args=(task_id, task), daemon=True,
            )
            t.start()

    def _threaded_execution_wrapper(self, task_id: str, task: MiloTask) -> None:
        """Acquire appropriate semaphore and execute in separate thread."""
        semaphore = (
            self._heavy_semaphore if task.type in self.HEAVY_TASKS else self._light_semaphore
        )
        semaphore.acquire()
        try:
            # Double-check: re-check status (user may have cancelled while waiting)
            with self._lock:
                current = self._tasks.get(task_id)
                if current is None or current.status != TaskStatus.QUEUED:
                    return
            self._execute_task(task_id, task)
        finally:
            semaphore.release()

    def _execute_task(self, task_id: str, task: MiloTask) -> None:
        """Execute a single task handler."""
        handler = self._handlers.get(task.type)
        if not handler:
            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(
                        update={"status": TaskStatus.FAILED,
                                "error": f"No handler for task type: {task.type}"}
                    )
            return

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[task_id] = cancel_event
            current = self._tasks.get(task_id)
            if current:
                self._tasks[task_id] = current.model_copy(
                    update={"status": TaskStatus.RUNNING,
                            "started_at": datetime.now().isoformat()}
                )

        try:
            def progress_cb(percent: float, message: str = "") -> None:
                self._update_progress(task_id, percent, message)

            result = handler(task, cancel_event, progress_cb)

            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(
                        update={"status": TaskStatus.COMPLETED,
                                "progress": TaskProgress(percent=100),
                                "result": result,
                                "completed_at": datetime.now().isoformat()}
                    )

            self._emit(TASK_COMPLETED, {
                "task_id": task_id, "task_type": task.type.value, "result": result,
            })

        except Exception as e:
            logger.exception("Task {} failed", task_id)
            with self._lock:
                current = self._tasks.get(task_id)
                if current:
                    self._tasks[task_id] = current.model_copy(
                        update={"status": TaskStatus.FAILED, "error": str(e),
                                "completed_at": datetime.now().isoformat()}
                    )
            self._emit(TASK_FAILED, {"task_id": task_id, "error": str(e)})
        finally:
            with self._lock:
                self._cancel_events.pop(task_id, None)
```

> **Phase 3 改造点**: WorkflowEngine 不修改 TaskManager，而是作为编排层通过 `create_task` / `cancel_task` / `get_task` API 调度单个步骤。WorkflowEngine 监听 `TASK_COMPLETED` / `TASK_FAILED` 事件判断步骤完成/失败，再决定下一步。

#### A.3.2 TaskType 枚举 (完整，`core/models.py:27`)

```python
class TaskType(StrEnum):
    # MVP
    SILENCE_DETECTION = "silence_detection"
    EXPORT_VIDEO = "export_video"
    EXPORT_SUBTITLE = "export_subtitle"
    EXPORT_AUDIO = "export_audio"
    EXPORT_VTT = "export_vtt"
    # P1
    FILLER_DETECTION = "filler_detection"
    ERROR_DETECTION = "error_detection"
    FULL_ANALYSIS = "full_analysis"                    # ← 工作流步骤: 规则分析
    TRANSCRIPTION = "transcription"
    VAD_ANALYSIS = "vad_analysis"
    WAVEFORM_GENERATION = "waveform_generation"
    PLUGIN_INSTALL = "plugin_install"
    MODEL_DOWNLOAD = "model_download"
    PROXY_GENERATION = "proxy_generation"
    # LLM
    LLM_SMART_DELETE = "llm_smart_delete"              # ← 工作流步骤: P0
    LLM_SUBTITLE_CORRECTION = "llm_subtitle_correction" # ← 工作流步骤: P1
    LLM_HIGHLIGHT = "llm_highlight"                    # ← 工作流步骤: P2
    LLM_SEMANTIC_SEARCH = "llm_semantic_search"        # ← 不进工作流 (P3, D-31)
```

> **Phase 3 改造点**: 无需新增 TaskType。工作流的 4 种步骤类型 (full_analysis / llm_smart_delete / llm_subtitle_correction / llm_highlight) 均已存在。

#### A.3.3 `main.py` LLM 任务启动 @expose 方法 (P0/P1/P2，完整)

```python
    @expose
    def start_smart_delete(self, timeline_id: str = "") -> dict:
        """Start LLM smart-delete analysis as a background task."""
        from core.llm_service import get_llm_config as _get_cfg
        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task("llm_smart_delete", {"timeline_id": tl_id})
        return task

    @expose
    def start_subtitle_correction(self, reference_text: str = "",
                                   timeline_id: str = "", context_window: int = 3) -> dict:
        """Start LLM subtitle correction as a background task."""
        from core.llm_service import get_llm_config as _get_cfg
        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task(
            "llm_subtitle_correction",
            {"timeline_id": tl_id, "reference_text": reference_text,
             "context_window": context_window},
        )
        return task

    @expose
    def confirm_all_from_source(self, source: str, min_confidence: float = 0.0) -> dict:
        """Batch-confirm all pending edit decisions from a given source."""
        result = self._project.confirm_all_from_source(source, min_confidence)
        if result["success"] and self._project.current:
            result["data"]["project"] = self._project.current.model_dump()
        return result

    @expose
    def start_highlight(self, target_duration_minutes: int = 10, timeline_id: str = "") -> dict:
        """Start LLM highlight extraction as a background task."""
        from core.llm_service import get_llm_config as _get_cfg
        config = _get_cfg()
        if not config.is_configured():
            return {"success": False, "error": "LLM not configured"}
        if self._project.current is None:
            return {"success": False, "error": "No project open"}
        tl_id = timeline_id or self._project.current.active_timeline_id
        task = self._task_manager.create_task(
            "llm_highlight",
            {"timeline_id": tl_id, "target_duration_minutes": target_duration_minutes},
        )
        return task
```

> **Phase 3 改造点**: WorkflowEngine 内部调用这些方法的底层 (`self._task_manager.create_task(...)`) 来调度步骤，但会额外传入 `workflow_instance_id` 到 payload 以关联工作流实例。工作流启动前检查 LLM 配置 (D-26: 可配置不可启动)。

---

### A.4 事件同步现状

#### A.4.1 `core/events.py` (完整，45 行)

```python
"""Event name constants for bridge communication.

Must stay in sync with frontend src/utils/events.ts.
"""

# Task lifecycle
TASK_PROGRESS = "task:progress"
TASK_COMPLETED = "task:completed"
TASK_FAILED = "task:failed"

# Project-level
PROJECT_SAVED = "project:saved"
PROJECT_DIRTY = "project:dirty"

# Analysis results
ANALYSIS_UPDATED = "analysis:updated"

# Edit summary
EDIT_SUMMARY_UPDATED = "edit:summary_updated"

# Log forwarding
LOG_LINE = "log_line"

# Encoder fallback
ENCODER_FALLBACK = "encoder:fallback"

# LLM analysis
LLM_ANALYSIS_PROGRESS = "llm:analysis_progress"
LLM_ANALYSIS_COMPLETED = "llm:analysis_completed"
LLM_ANALYSIS_FAILED = "llm:analysis_failed"
LLM_TOKEN_USAGE = "llm:token_usage"

# P0: Smart delete
LLM_SMART_DELETE_PROGRESS = "llm:smart_delete_progress"
LLM_SMART_DELETE_COMPLETED = "llm:smart_delete_completed"

# P1: Subtitle correction
LLM_SUBTITLE_CORRECTION_COMPLETED = "llm:subtitle_correction_completed"

# P2: Highlight extraction
LLM_HIGHLIGHT_PROGRESS = "llm:highlight_progress"
LLM_HIGHLIGHT_COMPLETED = "llm:highlight_completed"

# P3: Semantic search
LLM_SEMANTIC_SEARCH_COMPLETED = "llm:semantic_search_completed"

# ← Phase 3 新增 9 个 workflow:* 事件 (见下方 A.4.3)
```

#### A.4.2 `frontend/src/utils/events.ts` (完整，34 行)

```typescript
export const EVENT_TASK_PROGRESS = "task:progress"
export const EVENT_TASK_COMPLETED = "task:completed"
export const EVENT_TASK_FAILED = "task:failed"

export const EVENT_PROJECT_SAVED = "project:saved"
export const EVENT_PROJECT_DIRTY = "project:dirty"

export const EVENT_ANALYSIS_UPDATED = "analysis:updated"

export const EVENT_EDIT_SUMMARY_UPDATED = "edit:summary_updated"

export const EVENT_LOG_LINE = "log_line"

export const EVENT_ENCODER_FALLBACK = "encoder:fallback"

// LLM analysis
export const EVENT_LLM_ANALYSIS_PROGRESS = "llm:analysis_progress"
export const EVENT_LLM_ANALYSIS_COMPLETED = "llm:analysis_completed"
export const EVENT_LLM_ANALYSIS_FAILED = "llm:analysis_failed"
export const EVENT_LLM_TOKEN_USAGE = "llm:token_usage"

// P0: Smart delete
export const EVENT_LLM_SMART_DELETE_PROGRESS = "llm:smart_delete_progress"
export const EVENT_LLM_SMART_DELETE_COMPLETED = "llm:smart_delete_completed"

// P1: Subtitle correction
export const EVENT_LLM_SUBTITLE_CORRECTION_COMPLETED = "llm:subtitle_correction_completed"

// P2: Highlight extraction
export const EVENT_LLM_HIGHLIGHT_PROGRESS = "llm:highlight_progress"
export const EVENT_LLM_HIGHLIGHT_COMPLETED = "llm:highlight_completed"

// P3: Semantic search
export const EVENT_LLM_SEMANTIC_SEARCH_COMPLETED = "llm:semantic_search_completed"

// ← Phase 3 新增 9 个 workflow:* 事件 (见下方 A.4.3)
```

#### A.4.3 Phase 3 需新增的事件 (两文件同步)

```python
# core/events.py 追加:

# Workflow (Phase 3)
WORKFLOW_STARTED = "workflow:started"
WORKFLOW_STEP_STARTED = "workflow:step_started"
WORKFLOW_STEP_PROGRESS = "workflow:step_progress"
WORKFLOW_STEP_COMPLETED = "workflow:step_completed"
WORKFLOW_STEP_FAILED = "workflow:step_failed"
WORKFLOW_COMPLETED = "workflow:completed"
WORKFLOW_CANCELLED = "workflow:cancelled"
WORKFLOW_CONFLICTS_DETECTED = "workflow:conflicts_detected"
WORKFLOW_HEARTBEAT = "workflow:heartbeat"  # D-72: 每 15s 心跳
```

```typescript
// frontend/src/utils/events.ts 追加:

// Workflow (Phase 3)
export const EVENT_WORKFLOW_STARTED = "workflow:started"
export const EVENT_WORKFLOW_STEP_STARTED = "workflow:step_started"
export const EVENT_WORKFLOW_STEP_PROGRESS = "workflow:step_progress"
export const EVENT_WORKFLOW_STEP_COMPLETED = "workflow:step_completed"
export const EVENT_WORKFLOW_STEP_FAILED = "workflow:step_failed"
export const EVENT_WORKFLOW_COMPLETED = "workflow:completed"
export const EVENT_WORKFLOW_CANCELLED = "workflow:cancelled"
export const EVENT_WORKFLOW_CONFLICTS_DETECTED = "workflow:conflicts_detected"
export const EVENT_WORKFLOW_HEARTBEAT = "workflow:heartbeat"  // D-72: 每 15s 心跳
```

---

## 附录 B: v2.1.0 候选功能 (未纳入，留待后续)

以下功能有价值但未纳入 v2.1.0 范围 (D-02 仅 3 模块):

| 功能 | 来源 | 留待版本 | 原因 |
|------|------|----------|------|
| 精华模式独立布局 | v2.0.1 spec D-13 后续 | v2.2.0 | 跳切 crossfade 预览 / 精华版直通导出，需独立布局打磨 |
| AI 解说词/文案生成 | v2.0.1 spec 候选 | v2.2.0 | 需新 LLM 分析函数 + 全新文案编辑 UI |
| 语义素材匹配 | 剪映 Skill 启发 | v2.3.0+ | 需 B-Roll 素材管理 + 视频内容理解，超出预处理定位 |
| 自然语言全局指令 | 剪映 Skill 启发 | v2.3.0+ | 需 Agent 式任务编排层 |
| 预定义工作流模板 | 本 spec D-32 | 视用户反馈 | Phase 3 完成后根据用户使用数据决定是否内置模板 |
| macOS 打包 | v2.0.0 PRD Pillar-C | v2.2.0 | 非主线 AI 功能，单独排期 |
| 键盘快捷键系统 | v2.0.0 PRD Pillar-C | v2.2.0 | 非主线 AI 功能，单独排期 |


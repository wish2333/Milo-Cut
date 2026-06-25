# Milo-Cut v2.0.0 Phase 1-2 实施问题审计报告

> Version: 2.0 (修订版)
> Date: 2026-06-14
> Scope: Phase 1 (Foundation) + Phase 2 (Core Features) 实施过程中发现的问题
> Related: `audit-report-v2.0.0.md` (PRD 级审计), `record-2.0.0.md` (实施记录)

---

## 0. Executive Summary

Phase 1-2 的后端工程质量良好 (40 个新测试覆盖核心逻辑，类型检查通过)，但暴露了一个**根本性的产品定位问题**: Topic Drift 功能与 Milo-Cut 的核心提效价值脱节。此外有 3 个实施层面的技术问题和 3 个工程改进建议。

**核心结论: Topic Drift 功能定位不清、实际价值存疑，需重新评估其存在意义或重构为真正服务提效的能力。**

---

## 1. Critical: 产品定位问题

### C-01: Topic Drift 功能定位不清，需重构为 LLM 增强提效能力

| Item | Detail |
|------|--------|
| Phase | Phase 2 (Task 2.1 + 2.2) |
| File | `core/llm_service.py:286-490`, `frontend/src/components/workspace/TopicDriftPanel.vue` |
| Severity | **Critical (产品级)** |
| Status | **初步决策: 方向 E (按优先级重构为 4 级 LLM 增强能力)，详见下文** |

---

#### A. 问题详述

Milo-Cut 的核心价值 (README): *"Turn 1 hour of raw footage into 40 minutes of clean, editable material."* 核心是 **提效**，受众是演讲视频剪辑者。

Topic Drift (逐句标注与主题相关性 0-1 分) 的四个核心问题:

1. **提效价值不清**: 演讲视频天然单主题，"跑题"极少出现且用户秒级可判，花 LLM 成本是负提效
2. **粒度错误**: 逐句打分制造 200+ 条决策噪音，"跑题"是段落级概念
3. **与现有能力割裂**: 没有填补规则引擎的真实盲区 (语义重复、上下文口头禅、无触发词口误)
4. **交互过重**: 独立 Tab/流式进度/三档颜色/批量操作，投入产出比低

**用户原话反馈:**
> "这功能真的有什么用吗？一句句话标注跑题？你到底懂不懂这个项目和他已经完成的提效内容以及受众啊"

---

#### B. 现有规则引擎的能力边界 (LLM 应填补的盲区)

| 检测项 | 现有实现 | 已覆盖 | **盲区 (LLM 应补充)** |
|--------|----------|--------|----------------------|
| 口头禅 | `detect_fillers`: 字符串包含匹配词表 | "嗯/啊/那个" 等字面口头禅 | 上下文口头禅: "然后那个接下来就是说" 这种无信息过渡句 |
| 重复段 | `detect_duplicates`: n-gram 余弦相似度 >= 0.85 | 字面高度相似的重复 | **语义重复**: 同一观点换措辞重述 ("刚才说的那个原理简单来说就是...") |
| 口误 | `detect_errors`: 触发词 + lookahead=3 | "不对/重来/说错了" 后的重说段 | **无触发词口误**: 说了半句自然纠正 ("我觉得是三...不对应该是五个，五个人") |
| 标点 | `detect_punctuation`: 字符集匹配 | 异常标点 ASR 噪声 | -- |
| 静音 | FFmpeg silencedetect | 无说话片段 | -- |

**结论: LLM 的价值不是做规则引擎已做好的事，而是补盲区 + 做规则引擎做不到的语义级操作。**

---

#### C. 初步决策: 方向 E -- 按优先级重构为 4 级 LLM 增强能力

放弃"主题漂移"这个伪需求，将 LLM 能力重新定位为 **Milo-Cut 提效链路的增强层**，按用户价值排序分 4 个优先级实施:

---

##### P0: 智能删除增强 (LLM 补盲区)

> **目标: 用 LLM 补全规则引擎漏掉的"可安全删除"片段，直接生成 EditDecision，与规则结果合并展示。**

这是 LLM 最自然的切入点 -- 不改变现有交互流程，只是让 SuggestionPanel 里多出更准的建议。

| 能力 | 规则引擎版本 | LLM 增强版本 |
|------|-------------|-------------|
| 重复句删除 | n-gram 相似度，仅识别字面重复 | **语义重复**: 识别"同一观点换措辞重述"，建议删除冗余的那一遍 |
| 口误重说删除 | 触发词 + lookahead，仅识别"不对/重来" | **无触发词口误**: 识别"说错后自然纠正"的完整区域 (包括被纠正的错句 + 纠正句) |
| 口癖句删除 | 字符串包含，仅识别词表中的字面口头禅 | **上下文口头禅**: 识别无实义过渡句 ("然后接下来就是我们要讲的那个") |

**关键设计:**
- **短窗口分析** (15-30s 窗口)，因为口误/重复/口癖都是局部现象 -- 说错一句话后通常几秒内就会纠正重说，不需要长上下文。窗口过大会引入无关片段干扰 LLM 判断
- **直接生成 EditDecision(delete, source="llm_smart")**，复用现有 SuggestionPanel 交互
- **增量分析**: 跳过规则引擎已标记的 segment，只分析未覆盖区域
- **与规则结果同列展示**，source 字段区分，用户统一 confirm/reject
- **不改变时间戳**: 只生成删除建议 (start/end 来自已有 segment)，不触碰 segment 内容

---

##### P1: 字幕修正 (LLM 语义级文本纠错)

> **目标: 用 LLM 修正 ASR 识别错误，支持逐字稿校对和参考稿对齐，确保修正后无时间戳错位。**

这是用户明确要求的能力，也是 Milo-Cut 目前最大的痛点 -- ASR 输出的字幕有大量同音错字、专有名词错误、断句不当。

**两种修正模式:**

**模式 A: 无参考稿 (LLM 自主纠错)**
- 输入: ASR 原始字幕文本 (带 word-level timestamps)
- LLM 任务: 修正同音错字、专有名词、断句、标点
- 输出: 修正后的文本 + diff 标记哪些词改了

**模式 B: 有参考稿 (逐字稿/演讲稿对齐)**
- 输入: ASR 字幕文本 + 用户提供的参考稿 (全文)
- LLM 任务: 将 ASR 字幕与参考稿对齐，用参考稿内容修正 ASR 文本
- 输出: 修正后的文本 + 对齐置信度

**字幕修正的时间戳安全保证 (核心约束):**

这是整个功能最关键的部分 -- LLM 修正文本后 **绝不能** 导致时间戳错位、缺漏或偏移:

| 风险 | 原因 | 保证措施 |
|------|------|----------|
| 时间戳偏移 | LLM 改了文本长度，原有 start/end 不再对应 | **不改 segment 的 start/end**，只改 text 字段 |
| 词级时间戳丢失 | LLM 重写了整句，原有 word-level timestamps 失效 | **保留原 words 数组不动**；若文本变更则尝试 word-level diff 重新对齐，对齐失败则清空 words 并标记 `dirty_flags.llm_corrected` |
| 字幕缺漏 | LLM 漏掉了某些 segment 或合并了多句 | **强制 1:1 输入输出约束**: 输入 N 个 segment，必须输出 N 个修正结果，LLM 不允许增删 segment |
| 文本膨胀/缩减 | LLM 添加了原文没有的内容 | **字符级 diff 校验**: 修正后文本与原文的编辑距离超过阈值时标记 `low_confidence`，用户需手动确认 |
| 时间戳-文本不一致 | 修正后文本与时间窗口内的语音不再对应 | 不涉及 -- 修正的是文本内容，音频未变，时间戳仍标记原始语音边界 |

**实现要点:**
- **输入端结构化 JSON** (解决 C-02): 每个 segment 作为 `{id, text, words: [{word, start, end}]}` 传入
- **输出端要求 1:1 对应**: `{segment_id, corrected_text, changes: [{original, corrected, reason}]}`
- **Word-level diff 对齐**: 用 difflib 对原 words 和修正后文本做序列对齐，尽量保留 word timestamps
- **dirty_flags 标记**: 修正过的 segment 设置 `dirty_flags.llm_corrected = true`，UI 可高亮显示
- **用户逐条确认**: 不自动应用，所有修正进入 review 队列，用户逐条 accept/reject (类似 git diff)

---

##### P2: 智能亮点提取与剪辑

> **目标: LLM 分析全文，自动提取高信息密度片段，生成"精华版"时间线。**

这是比删除更进一步的能力 -- 不是减法 (删差的)，而是加法 (挑好的)。

**场景:** 用户有一个 40 分钟演讲，想快速生成一个 10 分钟精华版用于社交媒体分发。

**实现:**
- LLM 分析全文转录，识别高信息密度段落 (核心论点、关键数据、精彩类比)
- 输出: 建议保留的 segment 区间列表 + 每段的"亮点理由"
- 生成新的 EditDecision(action="keep", source="llm_highlight")，反转现有 delete 逻辑
- UI: 新增"精华模式"视图，高亮 LLM 推荐保留的片段，用户可调整目标时长 (LLM 重新裁剪)

**与 P0/P1 的区别:** P0/P1 是在现有时间线上做增强，P2 是生成新的时间线视角。

---

##### P3: 语义搜索与导航

> **目标: 用自然语言搜索转录内容，快速定位到特定段落。**

**场景:** 用户想找到"刚才讲性能优化的那段"，而非手动滚动 400 条字幕。

**实现:**
- 搜索框输入自然语言查询
- LLM 将查询与所有 segment 做语义匹配 (或用 embedding 向量检索)
- 返回最相关的 segment 列表，点击跳转

---

##### 基础设施: 多 Timeline 支持 (P0-P3 共同依赖)

> **目标: 一个 Project 中可存在多条独立 timeline，每条 timeline 拥有独立的 transcript + edits + analysis，用户可创建、切换、比对不同处理方案，互不影响。**

LLM 功能 (P0-P3) 的处理结果不可能每次都让用户满意。用户可能想:
- 用不同参数跑两次 P0 智能删除，比对哪次结果更好
- P1 字幕修正试两个不同模型，对比修正质量
- P0 删除建议 + P2 亮点提取组合成不同方案
- 保留原始 timeline 不动，在新 timeline 上试验

当前 `Project` 数据模型只有一个 `transcript` + `edits` + `analysis`，无法满足多方案并存需求。

**现有冲突解决机制评估:**

现有代码已有一套 transcript 变更时的冲突处理:
- `update_transcript()`: 替换字幕时保留 silence segment，清理 orphaned edits (target_id 不再存在)
- `delete_segment()` / `merge_segments()` / `clear_subtitles()`: 删除 segment 时同步清理引用该 segment_id 的 edits
- `_resolve_subtitle_overlap()`: 字幕与静音区间重叠时裁剪/分裂字幕
- `_trim_silences_around_subtitles()`: 静音区间避让已确认删除的字幕

**现有机制的本质: segment ID 是 transcript 与 edits/analysis 的唯一关联键，冲突解决是单向减法 (清理孤儿，不做迁移)。**

这套机制能覆盖: segment 删除/合并/重新导入等 ID 消失场景。**但覆盖不了 P1 字幕修正引入的新场景:**

| 场景 | 现有机制 | 问题 |
|------|----------|------|
| 字幕修正改了文本，ID 不变 | 无感知 (不触发 orphan 清理) | analysis 中的 filler/error 检测可能已失效 (口头禅被修正掉了) |
| 字幕修正改了断句 (合并/拆分句) | ID 体系断裂 | 所有引用旧 ID 的 edits/analysis 全部失效 |
| 多 timeline 中不同 transcript 版本 | 不存在此场景 | 当前只有一个 transcript |

**结论: 现有机制不够。需要让每条 timeline 拥有独立的 transcript，而非共享单一 transcript + text_overrides 叠加。**

**数据模型扩展 (core/models.py):**

```python
class Timeline(BaseModel, frozen=True):
    """独立的时间线 -- 拥有完整的 transcript + edits + analysis。"""
    id: str                          # 唯一标识
    label: str                       # 用户可见名称 ("原始" / "字幕修正-DeepSeek" / "智能删除v1")
    source: str = "manual"           # 创建来源
    created_at: str
    parent_id: str = ""              # 从哪条 timeline 分叉而来 (用于追溯)
    transcript: TranscriptData       # 此 timeline 的完整转录 (含字幕修正后的文本/断句)
    edits: list[EditDecision] = Field(default_factory=list)
    analysis: AnalysisData = Field(default_factory=AnalysisData)

class Project(BaseModel, frozen=True):
    # ... 现有 media/project 字段不变 ...
    timelines: list[Timeline] = Field(default_factory=list)
    active_timeline_id: str = ""     # 当前激活的 timeline
```

**设计要点:**

1. **每条 timeline 拥有独立 transcript**: P1 字幕修正在目标 timeline 的 transcript 上直接操作 (改 text / 合并句 / 拆分句)，不通过 overlay 叠加。这样 segment ID 体系在每个 timeline 内部自洽，edits/analysis 引用的 ID 始终有效。

2. **Timeline 间完全独立**: 每条 timeline 是封闭的 transcript + edits + analysis 三元组，切换时互不影响。切换 = 更换 `active_timeline_id`。

3. **分叉创建 (fork)**: 新 timeline 从父 timeline 复制完整 transcript + (可选) edits。字幕修正/智能删除等操作在 fork 上进行，原始 timeline 不受影响。`parent_id` 记录分叉来源。

4. **冲突解决沿用现有机制**: 在单条 timeline 内部，transcript 变更 (delete/merge/修正断句) 时的 orphan edit 清理逻辑不变 -- 只是需要作用于 `active_timeline.transcript` 和 `active_timeline.edits`，而非 `project.transcript` 和 `project.edits`。

5. **字幕修正后的 analysis 失效处理**: 当 P1 修正了文本内容 (ID 不变但 text 变了)，标记该 timeline 的 `analysis.last_run = null` 表示 analysis 已过期，UI 提示用户"字幕已修正，建议重新运行分析"。这是现有机制的自然延伸。

6. **向后兼容**: 现有单 timeline 项目加载时自动迁移 -- 将现有 `transcript` + `edits` + `analysis` 包装为一条默认 timeline (`id="default"`, `label="原始"`)，`active_timeline_id="default"`。原 `Project.transcript` / `Project.edits` / `Project.analysis` 字段移除，统一通过 `active_timeline` 访问。

7. **导出隔离**: 导出时只使用 `active_timeline` 的 transcript + edits，不影响其他 timeline。

8. **Timeline 操作 API**:
   - `create_timeline(label, source, fork_from=None)`: 新建空白或从指定 timeline 分叉
   - `duplicate_timeline(id, new_label)`: 完整复制一条 timeline
   - `switch_timeline(id)`: 切换 active
   - `delete_timeline(id)`: 删除 (至少保留一条)
   - `rename_timeline(id, new_label)`: 重命名

**UI 设计:**
- WorkspacePage 顶部新增 Timeline 切换器 (下拉或标签页)
- 每个 LLM 分析任务完成后默认在当前 timeline 上操作，用户可手动 fork 后再操作
- Timeline 之间可快速切换比对 (类似 Photoshop 图层 / Git 分支)
- 切换时波形/Timeline/SuggestionPanel 全部刷新为对应 timeline 的数据

**ProjectService 改造范围:**

现有 `ProjectService` 的所有方法直接操作 `self._current.transcript` / `self._current.edits`。改造后统一改为操作 `self._active_timeline.transcript` / `self._active_timeline.edits`。这是一个大范围但机械性的重构 -- 新增一个 `@property active_timeline` 属性，所有 `self._current.transcript` 替换为 `self.active_timeline.transcript`。

---

#### D. 实施优先级与依赖关系

```
基础设施: 多 Timeline  ←── P0-P3 共同依赖, 数据模型 + API + UI 切换器
     │
     ├── P0 智能删除增强  ←── 复用现有 EditDecision + SuggestionPanel
     │        │
     │        └── P1 字幕修正  ←── 需 review UI + word-level diff + text_overrides
     │                 │
     │                 └── (P1 完成后字幕质量提升，P2 亮点提取更准确)
     │
     ├── P2 亮点提取  ←── 需新的"精华模式"视图
     │
     └── P3 语义搜索  ←── 可独立，但依赖 P1 的字幕质量
```

| 优先级 | 功能 | 依赖 | 预估工作量 | 提效价值 |
|--------|------|------|-----------|----------|
| **基础** | 多 Timeline 支持 | 无 (数据模型+ProjectService 重构) | 4-5 pd | 高 (P0-P3 共同依赖，用户比对方案的基础) |
| **P0** | 智能删除增强 | 基础设施 + Phase 1 LLM | 2-3 pd | 高 (补规则引擎盲区) |
| **P1** | 字幕修正 | 基础设施 + P0 (LLM 调用框架) | 3-4 pd | 极高 (解决 ASR 痛点) |
| P2 | 亮点提取 | 基础设施 + P1 (字幕质量) | 3-4 pd | 中 (进阶功能) |
| P3 | 语义搜索 | P1 (字幕质量) | 2 pd | 中 (效率工具) |

**Topic Drift 现有代码处理:**
- `core/llm_service.py` 的 `analyze_topic_drift` / `_build_topic_drift_prompt` / `_parse_topic_drift_response`: **保留但重构**，P0 复用其分块、流式、解析框架，改 prompt 和输出 schema
- `TopicDriftPanel.vue`: P0 阶段**删除**，智能删除建议直接进 SuggestionPanel，不需要独立 Tab
- `useTopicDrift.ts` / `useLlmAnalysis.ts`: **保留并泛化**，重命名为通用的 LLM 分析 composable

---

#### E. 对 v2.0.0 版本规划的影响

这是对 v2.0.0 的修正，**所有功能都在 v2.0.0 内完成**，不推迟到后续版本:

| 阶段 | 内容 | 预估 |
|------|------|------|
| Phase 4a | 多 Timeline 基础设施 (Timeline 模型 + ProjectService 重构 + 迁移 + UI 切换器) | 4-5 pd |
| Phase 4b | P0 智能删除增强 + P1 字幕修正 | 5-7 pd |
| Phase 4c | P2 亮点提取 + P3 语义搜索 | 5-6 pd |
| Phase 4d | 集成测试 + 发布 | 2-3 pd |

**v2.0.0 发布时 LLM 功能完整交付:**
- Topic Drift 代码重构为 P0-P3 (不保留旧的逐句打分逻辑)
- C-02 (输入结构化) 在 P0 实施时解决
- 多 Timeline 支持作为 v2.0.0 核心特性

**原 Phase 4 (集成与发布)** 扩展为 Phase 4a-4d，LLM 功能重构与集成合并进行。

---

### C-02: LLM 输入用自然语言 prompt，输出却要求结构化 JSON -- 数据格式不对称

| Item | Detail |
|------|--------|
| Phase | Phase 2 (Task 2.1) |
| File | `core/llm_service.py:295-314` (`_TOPIC_DRIFT_USER_TEMPLATE`), `core/llm_service.py:340-393` (`_parse_topic_drift_response`) |
| Severity | **High (设计缺陷)** |
| Status | **OPEN** |

**问题:**

当前 Topic Drift 的 LLM 调用存在输入输出格式不对称:

**输入 (自然语言 prompt):**
```
请分析以下视频转录片段与主题的相关性。
分析主题：未指定（请根据视频整体内容判断...）
转录片段：
[s1] 今天我们来聊聊分布式系统
[s2] 先说一下背景
...
```

**输出 (要求结构化 JSON):**
```json
[{"segment_id": "s1", "topic": "...", "relevance": 0.8, "reason": "..."}]
```

矛盾在于: 既然最终需要结构化数据，为何输入不用结构化格式？当前用自然语言拼接片段列表，导致:
1. LLM 解析片段 ID 不可靠 (prompt 里的 `[s1]` 标记是非标准格式，文本中的方括号会干扰)
2. 片段文本中的特殊字符 (方括号、换行、JSON 保留字符) 容易破坏 prompt 结构
3. 为了容忍 LLM 输出不规范，被迫写了复杂的容错解析逻辑 (`_parse_topic_drift_response` 处理 markdown code block / bare JSON / 字段缺失 / relevance 越界 clamp，共 50+ 行)

**用户原话反馈:**
> "既然 LLM 要导出 json 为何传入时不用结构化的 json？"

**修复方向 (不依赖 Structured Output):**

Milo-Cut 支持 OpenAI / DeepSeek / Qwen / Custom (含 Ollama 本地模型) 四类 provider，它们对 OpenAI Structured Output (`response_format: json_schema`) 的支持差异很大:

| Provider | `json_schema` | `json_object` | 备注 |
|----------|---------------|---------------|------|
| OpenAI | 完整支持 | 完整支持 | 原生 |
| DeepSeek | 不支持 | 支持 | 仅保证返回合法 JSON，不保证 schema |
| Qwen | 部分支持 | 部分支持 | 依赖 dashscope 版本 |
| Ollama | 取决于模型 | 多数不支持 | 本地模型能力参差 |

因此 **不能强制依赖 Structured Output**。正确方向是输入端结构化 + 输出端分层降级:

**1. 输入端: 改用结构化 JSON messages**

将片段数据以 JSON 形式传入 `user` message，而非拼成 `[s1] text` 的自然语言:

```python
user_content = json.dumps({
    "topic": topic_description or None,
    "segments": [
        {"id": s["id"], "text": s["text"]}
        for s in segments
    ]
}, ensure_ascii=False)

messages = [
    {"role": "system", "content": _TOPIC_DRIFT_SYSTEM},
    {"role": "user", "content": user_content},
]
```

好处:
- segment_id 解析可靠 (JSON 键值对，无歧义)
- 片段文本中的特殊字符不再破坏结构 (JSON 自动转义)
- LLM 更容易将输入 id 与输出 id 对应

system prompt 简化为纯输出格式说明 (不再需要 `[id] text` 拼接模板):
```
你是视频内容分析专家。用户会以 JSON 格式提供主题和转录片段列表。
请为每个片段输出与主题的相关性评分。
输出格式: JSON 数组，每个元素: {"segment_id", "topic", "relevance"(0.0-1.0), "reason"}
```

**2. 输出端: 分层降级解析 (保留容错，但分层)**

```python
def _parse_topic_drift_response(content: str) -> list[dict]:
    # Layer 1: 尝试直接 json.loads (模型遵守格式时最快)
    # Layer 2: 提取 markdown code block 后 json.loads
    # Layer 3: 正则提取 [...] 子串后 json.loads
    # Layer 4: 逐行 regex 提取 segment_id + relevance (极端降级)
    # 每层失败则进入下一层，全部失败返回 []
```

当前实现只有 Layer 2+3 合并的版本，缺少 Layer 1 (直接解析) 和 Layer 4 (逐行降级)。分层后可针对不同模型的输出习惯优化。

**3. 可选: 对已知支持的 provider 启用 `response_format`**

在 `call_llm` 中根据 provider 能力选择性传入 `response_format`:
```python
# 仅对支持 json_object 的 provider 传入 (OpenAI/DeepSeek)
if config.provider in (LlmProvider.OPENAI, LlmProvider.DEEPSEEK):
    kwargs["response_format"] = {"type": "json_object"}
```

但这是锦上添花，**核心修复是输入端结构化 (第 1 点)**，这已经能大幅提升 segment_id 匹配的可靠性，且对所有 provider 通用。

---

## 2. Medium: 实施层面技术问题

### M-01: BridgeService 回调方法绑定陷阱

| Item | Detail |
|------|--------|
| Phase | Phase 1 (Task 1.3) |
| File | `core/bridge_service.py`, `main.py` |
| Severity | Medium |
| Status | RESOLVED |

**问题:**
`BridgeService` 通过 `setattr(handler, attr, value)` 注入回调到 HTTP handler，但 Python 描述符协议将实例属性赋值绑定了 `self`，导致回调多接收一个参数。

**修复:**
用 `staticmethod()` 包装回调阻止绑定。

**教训:**
Python 回调注入到类属性时必须注意描述符协议。

---

### M-02: Timeline.vue import 路径缺少 @/ 别名

| Item | Detail |
|------|--------|
| Phase | Phase 2 (Task 2.2) |
| File | `frontend/src/components/workspace/Timeline.vue` |
| Severity | Medium (编译失败) |
| Status | RESOLVED |

**问题:**
新增 `import type { TopicDriftResult } from "types/project"` 缺少 `@/` 别名前缀，导致 TypeScript 编译失败。

**修复:**
改为 `from "@/types/project"`。

**教训:**
AGENTS.md/CLAUDE.md 明确约定所有前端 import 用 `@/` 别名，但新增时易遗漏。建议 ESLint `no-restricted-imports` 规则强制。

---

### M-03: Project mock 缺少 topic_drift 字段 + add_analysis_results 未 expose

| Item | Detail |
|------|--------|
| Phase | Phase 2 (Task 2.2 -> 2.3) |
| File | `useSegmentEdit.test.ts`, `main.py` |
| Severity | Medium |
| Status | RESOLVED |

**问题 (合并两项):**
1. Phase 2 在 `Project` 模型新增 `topic_drift` 字段后，`useSegmentEdit.test.ts` 的 mock 未同步更新，Pydantic frozen model 构造失败。
2. `ProjectService.add_analysis_results` 方法存在但未在 `main.py` 中通过 `@expose` 装饰器暴露给前端。

**修复:**
- 测试 mock 添加 `topic_drift: undefined`
- `main.py` 添加 `@expose def add_analysis_results(...)`

**教训:**
- 模型字段变更必须同步更新所有测试 mock (建议集中管理 mock)
- 新增 ProjectService 方法必须同步在 main.py 暴露 (建议自动化检查)

---

## 3. Low: 工程改进建议

### L-01: 前端 import 路径缺少自动检查

| Phase | Phase 2 |
| Severity | Low |

建议添加 ESLint `no-restricted-imports` 规则强制 `@/` 别名，避免 M-02 类问题复发。

### L-02: 测试 mock 集中管理

| Phase | Phase 1-2 |
| Severity | Low |

多个测试文件存在重复的 Project mock。建议提取到 `frontend/src/test/helpers/mockProject.ts`。

### L-03: 前后端 API 同步检查缺失

| Phase | Phase 1-2 |
| Severity | Low |

建议添加脚本比对 `main.py` 中 `@expose` 方法列表与前端 `call()` 调用，检测不一致 (避免 M-03 第 2 项复发)。

---

## 4. 问题分布

### 按严重程度

| 级别 | 数量 | 问题 ID |
|------|------|---------|
| Critical (产品级) | 1 | C-01 |
| High (设计缺陷) | 1 | C-02 |
| Medium (实施) | 3 | M-01, M-02, M-03 |
| Low (工程改进) | 3 | L-01, L-02, L-03 |
| **总计** | **8** | |

### 按性质

| 类型 | 数量 | 问题 ID |
|------|------|---------|
| 产品定位/功能价值 | 1 | C-01 |
| API 设计/数据格式 | 1 | C-02 |
| Python 语言陷阱 | 1 | M-01 |
| 编译/类型错误 | 1 | M-02 |
| 测试维护/API 同步 | 1 | M-03 |
| 工程规范 | 3 | L-01, L-02, L-03 |

---

## 5. 与 PRD 审计报告的关系

`audit-report-v2.0.0.md` (PRD 级) 识别了 PRD 文档层面的问题。本报告识别 **实施过程** 中暴露的问题。

值得注意: PRD 审计报告 (B-03: LLM 输出长度限制) 已正确预见了长视频 LLM 调用的技术风险，但 **没有质疑 Topic Drift 功能本身的产品价值**。这是一个审计维度的盲区 -- PRD 审计关注"能否实现"，本报告补充"是否值得实现"。

---

## 6. Phase 4 前置决策

**C-01 初步决策: 方向 E -- LLM 功能按优先级重构，全部在 v2.0.0 内完成**

- 原 Phase 4 扩展为 Phase 4a-4d，LLM 功能重构与集成合并进行
- 先做多 Timeline 基础设施 (P0-P3 共同依赖)，再按 P0→P1→P2→P3 顺序实施
- Topic Drift 代码重构，不保留旧逻辑
- C-02 (LLM 格式对称化) 在 P0 实施时解决

---

## Appendix: 问题汇总表

| ID | Phase | Severity | 文件 | 问题 | 状态 |
|----|-------|----------|------|------|------|
| C-01 | 2 | **Critical** | llm_service.py:286-490, TopicDriftPanel.vue, models.py | Topic Drift 偏离核心价值，需重构为 LLM 增强提效能力 | **初步决策: 方向 E (多Timeline + P0智能删除 + P1字幕修正 + P2亮点提取 + P3语义搜索)，全部 v2.0.0 内完成** |
| C-02 | 2 | **High** | llm_service.py:295-314 | LLM 输入自然语言/输出要求 JSON，格式不对称 | **OPEN** |
| M-01 | 1 | Medium | bridge_service.py | Python 描述符协议回调绑定 | RESOLVED |
| M-02 | 2 | Medium | Timeline.vue | import 缺少 @/ 别名 | RESOLVED |
| M-03 | 2 | Medium | useSegmentEdit.test.ts, main.py | mock 字段遗漏 + expose 遗漏 | RESOLVED |
| L-01 | 2 | Low | ESLint config | import 路径自动检查 | 建议 |
| L-02 | 1-2 | Low | test files | 测试 mock 集中管理 | 建议 |
| L-03 | 1-2 | Low | main.py | 前后端 API 同步检查 | 建议 |

---

## Appendix B: 当前实现状态对照 (2026-06-14 快照)

> 本附录逐项列出审计报告中所有问题的**当前代码库实际状态**，含文件路径与行号，供 Phase 4 实施前作为基线参考。所有行号基于当前工作树 (未开始 Phase 4 重构)。

### B-1. C-01 Topic Drift 当前实现 (待重构)

**状态: 完整存在，尚未按方向 E 重构为 P0-P3。**

| 组件 | 当前状态 | 文件:行号 |
|------|----------|-----------|
| Topic Drift 系统 prompt | 存在，中文 prompt 要求 JSON 数组输出 | `core/llm_service.py:289-293` (`_TOPIC_DRIFT_SYSTEM`) |
| Topic Drift 用户 prompt 模板 | 存在，`str.format()` 拼接 `[id] text` 片段列表 | `core/llm_service.py:295-314` (`_TOPIC_DRIFT_USER_TEMPLATE`) |
| Prompt 构建函数 | 存在，逐句拼成 `[{seg_id}] {text}` 格式 | `core/llm_service.py:317-336` (`_build_topic_drift_prompt`) |
| 响应解析函数 | 存在，regex 提取 markdown code block / bare JSON，clamp relevance/confidence 到 [0,1] | `core/llm_service.py:339-393` (`_parse_topic_drift_response`) |
| 主分析函数 | 存在，`chunk_transcript` 分块 (5min + 30s overlap)，逐块调用 LLM，`chunk_callback` 流式回传，按 segment_id 去重 | `core/llm_service.py:396-493` (`analyze_topic_drift`) |
| 分块函数 | 存在 | `core/llm_service.py:239-282` (`chunk_transcript`) |
| 数据模型 | `TopicDriftResult` (`core/models.py:251-257`) + `TopicDriftData` (`core/models.py:260-267`) | `Project.topic_drift: TopicDriftData` (`core/models.py:287`) |
| 后端 API | `start_topic_drift` (`main.py:1562`), `get_topic_drift_results` (`main.py:1587`), `_handle_topic_drift` 任务处理器 (`main.py:633-691`) | -- |
| 前端 Panel 组件 | 存在 (187 行)，按 relevance 升序排列，<0.4 红 / 0.4-0.7 黄 / ≥0.7 绿 | `frontend/src/components/workspace/TopicDriftPanel.vue:1-187` |
| 前端 Composable | 存在，含流式进度 / accept-all / reject-all | `frontend/src/composables/useTopicDrift.ts`, `frontend/src/composables/useLlmAnalysis.ts` |
| 前端类型定义 | `TopicDriftResult` (`types/project.ts:87`), `TopicDriftData` (`types/project.ts:95`) | `Project.topic_drift` (`types/project.ts:76`) |

**重构影响范围:** P0 阶段 `_TOPIC_DRIFT_*` prompt + 解析函数将被替换，`TopicDriftPanel.vue` 将删除，`useTopicDrift.ts` / `useLlmAnalysis.ts` 将泛化为通用 LLM 分析 composable。`TopicDriftResult`/`TopicDriftData` 模型按 P0-P3 新 schema 调整。

---

### B-2. C-02 LLM 输入输出格式不对称 (当前状态)

**状态: 仍是自然语言 prompt 输入 + regex 解析输出，未结构化。** 审计标记 OPEN，计划在 P0 实施时解决。

当前 `_build_topic_drift_prompt` (`core/llm_service.py:317-336`) 实现:

```python
lines: list[str] = []
for seg in segments:
    seg_id = seg.get("id", seg.get("segment_id", "?"))
    text = seg.get("text", "").strip()
    lines.append(f"[{seg_id}] {text}")
segments_text = "\n".join(lines)
return _TOPIC_DRIFT_USER_TEMPLATE.format(
    topic_line=topic_line, segments_text=segments_text
)
```

当前 `_parse_topic_drift_response` (`core/llm_service.py:339-393`) 解析层级:

| 层级 | 审计建议 | 当前实现 |
|------|----------|----------|
| Layer 1: 直接 `json.loads` | 建议新增 | **缺失** |
| Layer 2: markdown code block 提取 | 合并 Layer 2+3 | 与 Layer 3 合并在 `:348-360` |
| Layer 3: `[...]` 子串提取 | 合并 Layer 2+3 | 同上 |
| Layer 4: 逐行 regex 降级 | 建议新增 | **缺失** |

`call_llm` 中**未**根据 provider 能力传入 `response_format` -- 所有 provider 统一走 prompt 约束。

---

### B-3. M-01 BridgeService 回调绑定陷阱 (已解决)

**状态: RESOLVED。** 当前实现使用 `staticmethod()` 包装回调阻止描述符绑定。

`core/bridge_service.py:200-247`:
- `BridgeService.__init__` (`:203-218`) 接收回调函数为 kwargs，存为实例属性
- `start()` (`:232-247`) 动态创建 handler 子类，每个回调用 `staticmethod(...)` 包装:

```python
handler_attrs = {
    "get_projects_fn": staticmethod(self._get_projects_fn) if self._get_projects_fn else None,
    "get_project_fn": staticmethod(self._get_project_fn) if self._get_project_fn else None,
    "start_analysis_fn": staticmethod(self._start_analysis_fn) if self._start_analysis_fn else None,
    "get_topic_drift_fn": staticmethod(self._get_topic_drift_fn) if self._get_topic_drift_fn else None,
}
handler_cls = type("BoundBridgeHandler", (_BridgeHandler,), handler_attrs)
```

`_BridgeHandler` 基类 (`core/bridge_service.py:72-79`) 声明这些为 `Callable` 类属性。绑定问题已彻底解决。

---

### B-4. M-02 Timeline.vue import 路径 (已解决)

**状态: RESOLVED。** 当前所有 import 均使用 `@/` 别名。

`frontend/src/components/workspace/Timeline.vue:1-8`:
```ts
import type { Segment, EditDecision, AnalysisResult, TopicDriftResult } from "@/types/project"
import { resolveSegmentState } from "@/utils/segmentHelpers"
import TranscriptRow from "@/components/workspace/TranscriptRow.vue"
import SilenceRow from "@/components/workspace/SilenceRow.vue"
import SuggestionPanel from "@/components/workspace/SuggestionPanel.vue"
import TopicDriftPanel from "@/components/workspace/TopicDriftPanel.vue"
```

无相对路径 `../` 违规。

---

### B-5. M-03 mock 字段遗漏 + expose 遗漏 (已解决)

**状态: RESOLVED。** 两项均已修复:

1. **`add_analysis_results` 已 expose**: `main.py:1042-1050` 装饰 `@expose`，委托 `self._project.add_analysis_results(results, source=source)`。当前 `main.py` 共有 **79 个 `@expose` 方法** (审计写作时为 82，后经清理)。
2. **测试 mock 已补 `topic_drift`**: `frontend/src/composables/useSegmentEdit.test.ts:34` 含 `topic_drift: { ... }` 字段。`TopicDriftResult`/`TopicDriftData` 类型定义见 `frontend/src/types/project.ts:87, 95`。

---

### B-6. L-01 ESLint `no-restricted-imports` 规则 (未实施)

**状态: 未实施。项目完全未配置 ESLint。**

- `frontend/eslint.config.*` / `frontend/.eslintrc*`: **均不存在**
- `frontend/package.json` devDependencies: **无任何 ESLint 包** (仅 vite / vitest / vue-tsc / tailwindcss / daisyui / typescript / happy-dom / test-utils)
- 当前唯一静态检查: `vue-tsc --noEmit` (在 `build` script 内, `package.json:10`)

**影响:** M-02 类 import 别名违规无自动化防护，依赖人工 review。

---

### B-7. L-02 测试 mock 集中管理 (未实施)

**状态: 未实施。无集中 mock 层。**

- `tests/conftest.py:1-112`: 仅提供数据 fixtures (sample segments / projects / SRT content)，**无 mock 对象**
- 后端 mock: 各测试文件**内联**使用 `monkeypatch.setattr` / `patch()` (如 `tests/test_topic_drift.py` 内联构造 mock response dict)
- 前端 mock: 各 `.test.ts` 文件**内联**构造 Project 对象 (如 `useSegmentEdit.test.ts:34` 内联 `topic_drift` 字段)
- **无共享 mock 工厂**: `tests/mocks.py` / `tests/factories.py` / `frontend/src/test/helpers/mockProject.ts` 均不存在

**影响:** 模型字段变更时需手动同步多个测试文件 (M-03 第 1 项即因此复发)。

---

### B-8. L-03 前后端 API 同步检查脚本 (未实施)

**状态: 未实施。无 API 同步检查脚本。**

- `package.json` 仅有 `sync-version` 脚本 (`:8`)，**仅同步版本号字符串** (pyproject.toml ↔ package.json)，不检查 API 方法名
- 79 个 `@expose` 方法 (`main.py`) 与前端 `call()` 调用完全依赖人工保持同步

**影响:** 新增 `ProjectService` 方法忘记 `@expose` (M-03 第 2 项) 无自动化检测。

---

### B-9. 多 Timeline 基础设施 (未实施 -- P0-P3 共同前置依赖)

**状态: 未实施。`Project` 仍是单 timeline 扁平结构。**

当前 `Project` 模型 (`core/models.py:280-287`):

```python
class Project(BaseModel, frozen=True):
    schema_version: int = 1
    project: ProjectMeta = Field(default_factory=ProjectMeta)
    media: MediaInfo | None = None
    transcript: TranscriptData = Field(default_factory=TranscriptData)
    analysis: AnalysisData = Field(default_factory=AnalysisData)
    edits: list[EditDecision] = Field(default_factory=list)
    topic_drift: TopicDriftData = Field(default_factory=TopicDriftData)
```

- **`Timeline` 模型: 不存在** (grep `class Timeline` / `timelines` / `active_timeline` 在 `core/` 无源码匹配)
- `Project` 直接持有**单一** `transcript` / `edits` / `analysis` / `topic_drift`
- 无 `timelines: list[Timeline]`，无 `active_timeline_id`，无 fork/switch/delete timeline API
- 前端无 Timeline 切换器 UI

**影响:** 这是审计规划中 P0-P3 的**共同前置依赖** (预估 4-5 pd)，未实施则所有 LLM 增强功能无法启动。

---

### B-10. P0-P3 LLM 增强功能 (全部未实施)

**状态: 4 项功能全部未实施，代码库中无任何相关符号。**

| 优先级 | 功能 | 搜索关键词 | 匹配结果 |
|--------|------|-----------|----------|
| P0 | 智能删除增强 (LLM 补盲区) | `smart_delete` / `smart.delete` / `llm_smart` | **0 匹配** |
| P1 | 字幕修正 (语义级文本纠错) | `subtitle_correction` / `subtitle.correction` / `llm_corrected` | **0 匹配** |
| P2 | 亮点提取 (精华版时间线) | `highlight_extract` / `highlight.extract` / `llm_highlight` | **0 匹配** |
| P3 | 语义搜索 (自然语言定位) | `semantic_search` / `semantic.search` | **0 匹配** |

当前 LLM 能力**仅** Topic Drift (`core/llm_service.py:396-493`)。P0-P3 均待实施。

---

### B-11. 当前实现状态总览表

| 问题 ID | 当前状态 | 关键文件:行号 | Phase 4 是否需处理 |
|---------|----------|---------------|-------------------|
| **C-01** Topic Drift | 完整存在，待重构 | `core/llm_service.py:289-493`, `TopicDriftPanel.vue:1-187` | 是 (Phase 4a-4b) |
| **C-02** LLM 格式不对称 | OPEN，未结构化 | `core/llm_service.py:317-393` | 是 (Phase 4b P0 时解决) |
| **M-01** Bridge 回调绑定 | RESOLVED | `core/bridge_service.py:232-247` | 否 |
| **M-02** Timeline.vue import | RESOLVED | `frontend/src/components/workspace/Timeline.vue:1-8` | 否 |
| **M-03** mock + expose | RESOLVED | `main.py:1042-1050`, `useSegmentEdit.test.ts:34` | 否 |
| **L-01** ESLint no-restricted-imports | 未实施 (无 ESLint) | -- | 建议 |
| **L-02** 测试 mock 集中管理 | 未实施 (内联 mock) | `tests/conftest.py` (仅 fixtures) | 建议 |
| **L-03** API 同步检查脚本 | 未实施 (仅 sync-version) | `package.json:8` | 建议 |
| **基础** 多 Timeline | 未实施 (单 timeline) | `core/models.py:280-287` | 是 (Phase 4a) |
| **P0** 智能删除增强 | 未实施 | -- | 是 (Phase 4b) |
| **P1** 字幕修正 | 未实施 | -- | 是 (Phase 4b) |
| **P2** 亮点提取 | 未实施 | -- | 是 (Phase 4c) |
| **P3** 语义搜索 | 未实施 | -- | 是 (Phase 4c) |

**结论:** M-01/M-02/M-03 已解决; C-01/C-02 及基础设施 + P0-P3 全部待 Phase 4 实施; L-01/L-02/L-03 三项工程改进建议均未落地。当前代码库可作为 Phase 4 重构的干净基线。

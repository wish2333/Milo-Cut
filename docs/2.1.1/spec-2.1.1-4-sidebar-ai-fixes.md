# 规格说明（修订版）：侧边栏 UI 优化 + AI 处理四项修复

> 来源：spec-interview 访谈成果，经源码审计后修订。
>
> **第一轮修订**：问题 2 根因定位错误（真正重复源在 `project_service.py:1239` 而非 `main.py:754`）；问题 1 展开按钮无法融入 Tab 栏（物理位置分离）；补充全部当前代码上下文与可直接落地的方案代码。
>
> **第二轮修订（本次）**：根据二次审计（B+ → A-），修正 P0/P1 级缺陷：
> - 问题 2：迁移函数 `_dedupe_edit_ids` 自身存在二次 id 冲突（while 循环缺失）；统一 id 后缀命名为 `_dup{N}`；明确迁移调用点为 `open_project:138`；补 workflow 路径防御。
> - 问题 3：EditDecision 缺 category 导致下游行为不可控 → partial_delete 改用 `action="keep"` + 低 priority（无需改 EditDecision 模型）；前端 category 映射从 `target_id` 反查改为 `analysis_id`（更稳定）并包成 `computed`（响应式）；提示词补 few-shot 示例。
> - 问题 4：永久删除缺二次确认；改为保留"撤销本组"(reset) + 新增"删除本组"(delete) 两个菜单项；文案明确含已确认项；类型注解补全 `list[str]`。
> - 跨问题：补实施依赖关系图、回滚预案（迁移前 `.bak` 备份）、扩展测试矩阵。

---

## 问题清单

| # | 问题 | 根因（审计后） | 方案 |
|---|------|---------------|------|
| 1 | 侧边栏开/关按钮是悬浮方块，不融入 UI | `Timeline.vue` 展开按钮(L337)与关闭按钮(L368)均 `absolute` + 悬浮样式 | 去悬浮感：关闭按钮融入 Tab 栏；展开按钮改扁平（无法融入 Tab 栏，见 1.说明） |
| 2 | AI 结果分组内操作单项，同组全部被标记 | **独立路径**：`project_service.py:1239` 用 `f"edit-{ar.id}"` 生成 edit_id，而 `ar.id` 来自 `main.py:769` 的同一时间戳 → 27 个 edit 共享同一 id | 修复 analysis_result id 唯一性 + `project_service.py:1239` 防御性去重 |
| 3 | 智能删除把"口误+修正"单句整句标记删除 | 提示词未区分"整句重复"与"半句口误+半句修正" | 提示词增加 `partial_delete` category + 前端新增侧边栏分组 |
| 4 | 右键"全部撤销本组"做了"恢复 pending"而非"删除该组建议" | `runGroupAction(group,'reset')` → `reset-edit-batch` → `update_edit_decisions_batch` 改状态 | 新增"删除本组建议"操作，永久移除 edits |

---

## 问题 1：侧边栏开/关按钮融入 UI

### 当前代码上下文

**展开按钮**（`Timeline.vue:337-346`）—— 侧边栏收起时显示，位于波形图区域内（**在 `<Teleport to="body">` 之外**）：

```html
<!-- Timeline.vue:337 -->
<button
  v-show="!sidebarOpen"
  class="absolute right-2 top-2 z-30 rounded p-1.5 text-gray-500 bg-white/80 hover:bg-white hover:text-blue-600 shadow border border-gray-200 transition-colors"
  title="显示侧栏"
  @click="sidebarOpen = true"
>
  <svg ...><path d="M4 6h16M4 12h16M4 18h16" /></svg>
</button>
```

**关闭按钮**（`Timeline.vue:368-376`）—— 侧边栏打开时显示，位于 `<Teleport to="body">` 内部、侧边栏面板的右上角：

```html
<!-- Timeline.vue:362-376 -->
<div v-if="sidebarOpen" class="fixed top-0 bottom-0 right-0 bg-white shadow-2xl border-l ...">
  <!-- Close button (top-right inside sidebar) -->
  <button
    class="absolute right-2 top-2 z-50 rounded p-1.5 text-gray-500 hover:bg-gray-100 hover:text-red-600 transition-colors"
    title="隐藏侧栏"
    @click="sidebarOpen = false"
  >
    <svg ...><path d="M6 18L18 6M6 6l12 12" /></svg>
  </button>
```

**Tab 栏**（`Timeline.vue:385-399`）—— 在 `<Teleport>` 内部、关闭按钮下方：

```html
<!-- Timeline.vue:385 -->
<div class="flex border-b border-gray-200 bg-gray-50">
  <button v-for="tab in tabs" :key="tab.key"
    class="flex-1 px-2 py-2 text-xs font-medium transition-colors"
    :class="activeTab === tab.key ? 'border-b-2 border-blue-500 text-blue-600 bg-white' : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'"
    @click="activeTab = tab.key"
  >{{ tab.label }}</button>
</div>
```

### 关键约束（原报告遗漏）

展开按钮（L337）在 `<Teleport to="body">` **之外**，Tab 栏（L385）在 `<Teleport>` **之内**，且 Tab 栏仅在 `sidebarOpen` 为真时渲染。因此 **展开按钮物理上无法融入 Tab 栏**——侧边栏收起时 Tab 栏根本不存在。原报告"选项 A / 选项 B"的措辞容易误导：选项 A（保留在波形图区域改扁平）是**唯一可行**方案，不是"推荐之一"。

### 实现规格

**1. 关闭按钮融入 Tab 栏**（`Timeline.vue:368-399`）

将 Tab 栏改为左右两段式，关闭按钮从独立 `absolute` 改为 Tab 栏行内元素：

```html
<!-- 删除原 L368-376 的独立 close button -->

<!-- 修改 L385-399 的 Tab 栏为： -->
<div class="flex items-center border-b border-gray-200 bg-gray-50">
  <!-- 左侧：Tab 按钮（flex-1 + min-w-0 + truncate 防溢出，避免被右侧 32px 按钮挤压） -->
  <button v-for="tab in tabs" :key="tab.key"
    class="flex-1 min-w-0 truncate px-2 py-2 text-xs font-medium transition-colors"
    :class="activeTab === tab.key
      ? 'border-b-2 border-blue-500 text-blue-600 bg-white'
      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'"
    @click="activeTab = tab.key"
  >{{ tab.label }}</button>

  <!-- 右侧：行内关闭按钮（flex-shrink-0 保证不被挤压；relative z-10 防被 dropdown 遮挡） -->
  <button
    class="relative z-10 flex-shrink-0 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
    title="隐藏侧栏"
    @click="sidebarOpen = false"
  >
    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  </button>
</div>
```

**2. 展开按钮改扁平**（`Timeline.vue:337-346`）

去掉悬浮感样式（`shadow`、`bg-white/80`、`border`），改为低调半透明图标。**注意可见性**：原 `bg-white/80` 是为在深色波形区保证对比度，完全去掉会几乎不可见，因此保留极弱背景 + backdrop-blur：

```html
<button
  v-show="!sidebarOpen"
  class="absolute right-2 top-2 z-30 rounded p-1.5 text-gray-500 bg-white/40 backdrop-blur-sm hover:bg-gray-100/80 hover:text-gray-700 transition-colors"
  title="显示侧栏"
  @click="sidebarOpen = true"
>
  <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
    <path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
  </svg>
</button>
```

---

## 问题 2：AI 结果分组 id 串扰（BUG）—— 根因已修正

### 数据验证

项目 `20260514-潘多拉之心第二卷卷评` 实测（两个 timeline 均受影响）：

```
llm_smart edits: 27 个，唯一 id: 1 个
  → 全部为 edit-llm_smart_1782267939663
analysis_results: 27 个，唯一 id: 1 个
  → 全部为 llm_smart_1782267939663
```

### 根因（审计后修正）

原报告声称根因在 `main.py:769` 且影响 `main.py:754`。经源码核验，**两个路径行为不同**：

#### 路径 A：独立智能删除（`_workflow_accumulate` 为假）—— **受 bug 影响**

`main.py:743-782` 当前代码：

```python
# main.py:744-763 -- 构建 edit 字典（id 已含序号 _{i}，本身唯一）
from datetime import datetime as _dt
edits = []
seg_map = {s.id: s for s in timeline.transcript.segments}
for i, r in enumerate(all_results):
    seg = seg_map.get(r["segment_id"])
    if seg is None:
        continue
    edits.append({
        "id": f"llm_smart_{int(_dt.now().timestamp() * 1000)}_{i}",  # ← 唯一，无问题
        "start": seg.start, "end": seg.end,
        "action": "delete", "source": "llm_smart",
        "target_type": "segment", "target_id": seg.id, "priority": 50,
    })

# main.py:766-777 -- 构建 analysis_results（id 无序号！）
if edits:
    analysis_results = [
        {
            "id": f"llm_smart_{int(_dt.now().timestamp() * 1000)}",  # ← BUG：列表推导内 27 项用同一时间戳
            "type": "llm_smart_delete",
            "segment_ids": [r["segment_id"]],
            "confidence": r.get("confidence", 0.8),
            "detail": r.get("reason", ""),
        }
        for r in all_results if r["segment_id"] in seg_map
    ]
    # main.py:779 -- 非工作流路径：调用 add_analysis_results 持久化
    if not task.payload.get("_workflow_accumulate"):
        store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_smart"))
```

**注意**：`edits` 列表（含正确的 `_{i}` id）在独立路径下**根本不会被持久化**——它只用于 emit 事件和 return。真正落库的是 `add_analysis_results` 在内部重新创建的 EditDecision。

`project_service.py:1231-1251` 的实际持久化逻辑：

```python
# project_service.py:1231
for ar in analysis_results:
    matching_segs = [seg_map[sid] for sid in ar.segment_ids if sid in seg_map]
    if not matching_segs:
        continue
    start = min(s.start for s in matching_segs)
    end = max(s.end for s in matching_segs)

    edit_id = f"edit-{ar.id}"   # ← BUG 真正位置：ar.id 重复 → edit_id 全部相同
    new_edits.append(EditDecision(
        id=edit_id, start=start, end=end,
        action="delete", source=source,
        analysis_id=ar.id, status=EditStatus.PENDING,
        priority=100, target_type="segment", target_id=ar.segment_ids[0],
    ))
```

由于 27 个 `ar.id` 全是 `llm_smart_1782267939663`，`f"edit-{ar.id}"` 生成 27 个完全相同的 `edit-llm_smart_1782267939663`。

#### 路径 B：工作流智能删除（`_workflow_accumulate` 为真）—— **不受影响**

`_handle_smart_delete` 在 `main.py:779` 跳过 `add_analysis_results`，直接返回 `edits` 列表。`workflow_engine.py:750-757` 消费该列表，id 来自 `main.py:754`（已含 `_{i}`），唯一。

```python
# workflow_engine.py:750
if step_type in ("llm_smart_delete", "llm_highlight"):
    raw_edits = result.get("edits", [])  # ← 用 main.py 返回的 edits，id 已唯一
    for e in raw_edits:
        edit = dict(e)
        edit["step_type"] = step_type
        edit["step_index"] = step_index
        edits.append(edit)
```

#### 前端影响链（原报告引用了过时的 `update_edit_status`，实际是批量接口）

`update_edit_status`（单项）已不存在。当前是 `update_edit_decisions_batch`（`project_service.py:652-681`）：

```python
# project_service.py:666-674
ids_set = set(edit_ids)
for edit in self.active_timeline.edits:
    if edit.id in ids_set:                        # ← 27 个 edit.id 相同，全部命中
        updated_edits.append(edit.model_copy(update={"status": new_status}))
        matched += 1
    else:
        updated_edits.append(edit)
```

用户点 `SuggestionPanel.vue` 中某项"确认"→ emit `confirm-edit` 传 `editId` → `update_edit_decisions_batch([editId], 'confirmed')` → **所有同 id 的 27 个 edit 同时变更状态**。影响结论与原报告一致，仅函数名过时。

### 修复规格

采用"双管齐下"：既修 `main.py` 让 analysis_result id 唯一（治本），又在 `project_service.py` 加防御（防止其他 source 也踩坑）。

#### 2.1 `main.py:766-777` —— analysis_result id 加序号

```python
# main.py:744 改为提取时间戳一次
from datetime import datetime as _dt
_ts = int(_dt.now().timestamp() * 1000)

edits = []
seg_map = {s.id: s for s in timeline.transcript.segments}
for i, r in enumerate(all_results):
    seg = seg_map.get(r["segment_id"])
    if seg is None:
        continue
    edits.append({
        "id": f"llm_smart_{_ts}_{i}",            # 用统一 _ts
        "start": seg.start, "end": seg.end,
        "action": "delete", "source": "llm_smart",
        "target_type": "segment", "target_id": seg.id, "priority": 50,
    })

if edits:
    analysis_results = [
        {
            "id": f"llm_smart_{_ts}_{i}",         # ← 加 _{i} 序号，保证唯一
            "type": "llm_smart_delete",
            "segment_ids": [r["segment_id"]],
            "confidence": r.get("confidence", 0.8),
            "detail": r.get("reason", ""),
        }
        for i, r in enumerate(all_results)        # ← 需要 enumerate 拿到 i
        if r["segment_id"] in seg_map
    ]
    if not task.payload.get("_workflow_accumulate"):
        store = self._mark_dirty(self._project.add_analysis_results(analysis_results, source="llm_smart"))
        if not store["success"]:
            raise RuntimeError(store.get("error", "Failed to store smart-delete results"))
```

#### 2.2 `project_service.py:1239` —— 防御性 edit_id 去重（覆盖所有 source）

```python
# project_service.py:1228-1251 修改为：
existing_edits = list(self.active_timeline.edits)
existing_edit_ids = {e.id for e in existing_edits}
new_edits: list[EditDecision] = []

for ar in analysis_results:
    matching_segs = [seg_map[sid] for sid in ar.segment_ids if sid in seg_map]
    if not matching_segs:
        continue
    start = min(s.start for s in matching_segs)
    end = max(s.end for s in matching_segs)

    # 防御：若 edit-{ar.id} 已存在（ar.id 重复或其他 source 冲突），追加 _dup{N} 后缀
    # 统一后缀格式 _dup{N}（与 2.3 数据迁移保持一致，便于排查）
    edit_id = f"edit-{ar.id}"
    if edit_id in existing_edit_ids:
        n = 2
        while f"{edit_id}_dup{n}" in existing_edit_ids:
            n += 1
        edit_id = f"{edit_id}_dup{n}"
    existing_edit_ids.add(edit_id)

    new_edits.append(EditDecision(
        id=edit_id, start=start, end=end,
        action="delete", source=source,
        analysis_id=ar.id, status=EditStatus.PENDING,
        priority=100, target_type="segment", target_id=ar.segment_ids[0],
    ))
```

#### 2.3 数据迁移（修复已有重复 id 项目）

**调用点明确**：在 `project_service.py:open_project` 中，紧跟现有 `_migrate_silence_edits()`（line 138）之后调用 `_dedupe_edit_ids`。现有迁移模式即如此（line 133 设 `_current` → line 138 跑迁移），保持一致。

**回滚预案**：迁移前由 `open_project` 自动备份 `project.json.bak.{timestamp}`（若检测到重复 id）。迁移仅改 `edit.id`，不改其他字段，出错时可从备份恢复。

```python
# project_service.py 新增方法
def _dedupe_edit_ids(self) -> None:
    """一次性修复：同一 timeline 内重复的 edit.id 追加 _dup{N} 后缀。

    后缀格式与 2.2 防御逻辑一致（_dup{N}），便于统一排查。
    先用 O(n) 快速判断有无重复，无重复直接返回（大型项目零开销）。
    """
    if not self._current:
        return

    tl = self.active_timeline
    edits = list(tl.edits)
    ids = [e.id for e in edits]

    # 快速跳过：无重复则不处理（避免大型项目 O(n) 扫描开销）
    if len(ids) == len(set(ids)):
        return

    # 有重复：先备份
    all_ids = set(ids)                    # 全集，用于检测 candidate 是否撞已有 id
    seen: dict[str, int] = {}
    fixed = []
    changed_count = 0

    for e in edits:
        if e.id in seen:
            seen[e.id] += 1
            candidate = f"{e.id}_dup{seen[e.id]}"
            # 防御：candidate 可能恰好是列表中已有的 id（二次冲突），while 直到唯一
            while candidate in all_ids:
                seen[e.id] += 1
                candidate = f"{e.id}_dup{seen[e.id]}"
            all_ids.add(candidate)
            fixed.append(e.model_copy(update={"id": candidate}))
            changed_count += 1
        else:
            seen[e.id] = 1
            fixed.append(e)

    if changed_count > 0:
        logger.warning("Deduped {} duplicate edit ids in timeline {}", changed_count, tl.id)
        self._update_active_timeline(edits=fixed)
```

**调用（`project_service.py:open_project`，line 138 旁）**：

```python
# project_service.py:133-138 已有
self._current = project
self._current_path = project_path
logger.info("Opened project: {}", path)

# Migrate old format silence edits
self._migrate_silence_edits()

# v2.1.1: Dedupe duplicate edit ids (legacy llm_smart bug fix)
self._dedupe_edit_ids()                  # ← 新增，紧跟现有迁移之后
```

#### 2.4 工作流路径防御（兜底）

路径 B（`workflow_engine.py:750`）当前不受 bug 影响，但遵循防御性编程原则，补一道 id 唯一性检查，防止未来其他 source 接入工作流时踩坑：

```python
# workflow_engine.py:750-757 修改
if step_type in ("llm_smart_delete", "llm_highlight"):
    raw_edits = result.get("edits", [])
    seen_ids: set[str] = set()
    for e in raw_edits:
        edit = dict(e)
        # 防御：若 id 撞同批次已有项，追加 _dup{N}
        if edit.get("id") in seen_ids:
            n = 2
            while f"{edit['id']}_dup{n}" in seen_ids:
                n += 1
            edit["id"] = f"{edit['id']}_dup{n}"
        seen_ids.add(edit["id"])
        edit["step_type"] = step_type
        edit["step_index"] = step_index
        edits.append(edit)
```

---

## 问题 3：智能删除提示词优化 + 新增"部分删除"分组

### 当前代码上下文

**提示词**（`llm_prompts.py:28-37`）：

```python
_SMART_DELETE_SYSTEM = """你是视频转录文本的清理助手。用户以 JSON 格式提供一组转录片段。
请识别其中可安全删除的片段:
1. semantic_dup: 语义重复 -- 同一观点换措辞重述，或字面完全重复。对于重复内容，只保留最后一版 (即最后一次表述的片段)，前面的重复片段标记为删除。
2. self_correct: 无触发词口误 -- 说错后自然纠正，口误的起始半句到重新表述之前的完整区域应删除。
3. filler_phrase: 上下文口头禅 -- 无实义过渡句如"然后接下来就是我们要讲的那个"
{{custom_fillers}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase", "confidence": 0.0到1.0}]
只输出建议删除的片段，无需删除的不要输出。confidence 表示删除必要性 (1.0=非常确定该删，0.5=模棱两可)。
"""
```

**normalize 层**（`llm_service.py:459-477`）—— 已透传任意 category 字符串，新增 `partial_delete` 无需改：

```python
def _normalize_smart_delete_items(chunk_results: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for item in chunk_results:
        ...
        normalized.append({
            "segment_id": seg_id,
            "action": str(item.get("action", "delete")),
            "reason": str(item.get("reason", "")),
            "category": str(item.get("category", "filler_phrase")),  # ← 透传，自动支持
            "confidence": min(1.0, max(0.0, float(item.get("confidence", 0.8)))),
        })
    return normalized
```

**问题**：`self_correct` 规则"口误的起始半句到重新表述之前的完整区域应删除"未区分跨片段与单句内口误+修正。当一句字幕同时包含口误和修正时（如 `seg-0085 "他是那段历史中的他是那段历史的亲历者"`），LLM 将整个 segment 标记为 delete，修正部分也被删除。

**EditDecision 模型**（`models.py:102-118`）—— 当前**无 category 字段**：

```python
class EditDecision(BaseModel, frozen=True):
    id: str
    start: float
    end: float
    action: Literal["delete", "keep"] = "delete"
    source: str = ""
    analysis_id: str | None = None
    status: EditStatus = EditStatus.PENDING
    priority: int = 100
    target_type: Literal["segment", "range"] = "range"
    target_id: str | None = None
```

**AnalysisResult 模型**（`models.py:151-157`）—— 同样无 category：

```python
class AnalysisResult(BaseModel, frozen=True):
    id: str
    type: Literal["filler", "error", "duplicate", "punctuation",
                  "llm_smart_delete", "llm_subtitle_correction", "llm_highlight"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""
```

### 实现规格

#### 3.1 提示词修改（`llm_prompts.py:28-37`）

```python
_SMART_DELETE_SYSTEM = """你是视频转录文本的清理助手。用户以 JSON 格式提供一组转录片段。
请识别其中可安全删除的片段:
1. semantic_dup: 语义重复 -- 同一观点换措辞重述，或字面完全重复。对于重复内容，只保留最后一版 (即最后一次表述的片段)，前面的重复片段标记为删除。
2. self_correct: 跨片段口误纠正 -- 说错的完整片段被后续片段纠正时，标记口误片段为删除。如果一个片段内部同时包含口误和修正 (如前半句说错后半句重来)，不要标记为 self_correct，改用 partial_delete。
3. filler_phrase: 上下文口头禅 -- 无实义过渡句如"然后接下来就是我们要讲的那个"
4. partial_delete: 单句内既包含口误/重复又包含正确表述 (如"他是那段历史中的他是那段历史的亲历者")，无法整句删除。标注出来提示用户手动调整。仅当该句不是多句重复中的中间句 (中间句仍按 semantic_dup 处理)，而是独立句或重复序列的末句时才标为 partial_delete。
{{custom_fillers}}
输出格式: JSON 数组
[{"segment_id": "片段ID", "action": "delete", "reason": "删除理由", "category": "semantic_dup|self_correct|filler_phrase|partial_delete", "confidence": 0.0到1.0}]
只输出建议删除的片段，无需删除的不要输出。confidence 表示删除必要性 (1.0=非常确定该删，0.5=模棱两可)。

示例:
输入: [{"id":"s1","text":"今天天气很好今天天气真的很不错的"},{"id":"s2","text":"他是那段历史中的他是那段历史的亲历者"},{"id":"s3","text":"然后接下来就是我们要讲的那个"}]
输出: [
  {"segment_id":"s1","action":"delete","reason":"前半重复","category":"semantic_dup","confidence":0.9},
  {"segment_id":"s2","action":"delete","reason":"前半口误后半修正，不能整句删","category":"partial_delete","confidence":0.7},
  {"segment_id":"s3","action":"delete","reason":"无实义过渡","category":"filler_phrase","confidence":0.8}
]
注意 s2 标为 partial_delete 而非 self_correct，因为它句内同时含口误和修正。
"""
```

> **实施提示**：partial_delete 规则微妙，小模型遵从度可能不高。实施后须做 A/B 测试（新旧提示词同数据各跑一次，对比 category 分布与 semantic_dup 召回率），并在 UI 明确"建议手动检查"而非"AI 已识别"。

#### 3.2 后端：analysis_result 携带 category + EditDecision 用 action="keep"

不改 `EditDecision` 模型（其 `action` 已支持 `"keep"`），给 `AnalysisResult` 加可选 `category` 字段用于前端分组，并在构建 EditDecision 时让 `partial_delete` 用 `action="keep"` 从源头隔离。

**AnalysisResult 加 category**（`models.py:151-157`）：

```python
class AnalysisResult(BaseModel, frozen=True):
    id: str
    type: Literal["filler", "error", "duplicate", "punctuation",
                  "llm_smart_delete", "llm_subtitle_correction", "llm_highlight"]
    segment_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    detail: str = ""
    category: str = ""   # ← 新增可选字段，默认空串兼容旧数据
```

> **Pydantic 兼容性已核实**：项目模型均未设 `extra="forbid"`（仅 `model_config = {"frozen": True}`），加可选字段不会拒绝旧数据。

**`main.py` 构建 analysis_results + edits 时区分 category**：

```python
# main.py:767 构建 analysis_results（透传 category）
analysis_results = [
    {
        "id": f"llm_smart_{_ts}_{i}",
        "type": "llm_smart_delete",
        "segment_ids": [r["segment_id"]],
        "confidence": r.get("confidence", 0.8),
        "detail": r.get("reason", ""),
        "category": r.get("category", ""),   # ← 透传 category
    }
    for i, r in enumerate(all_results)
    if r["segment_id"] in seg_map
]

# main.py:746 构建 edits 时，partial_delete 用 action="keep"（关键改动）
category_by_seg = {r["segment_id"]: r.get("category", "") for r in all_results}
edits = []
for i, r in enumerate(all_results):
    seg = seg_map.get(r["segment_id"])
    if seg is None:
        continue
    is_partial = category_by_seg.get(seg.id) == "partial_delete"
    edits.append({
        "id": f"llm_smart_{_ts}_{i}",
        "start": seg.start, "end": seg.end,
        "action": "keep" if is_partial else "delete",   # ← partial_delete 用 keep
        "source": "llm_smart",
        "target_type": "segment", "target_id": seg.id,
        "priority": 10 if is_partial else 50,            # ← partial 低 priority
    })
```

**为什么用 `action="keep"` 而非加 category 到 EditDecision**：这样波形图不会把 partial_delete 标记为删除区段，"全部确认删除"与导出/渲染逻辑天然排除它（它们只处理 `action==="delete"`），无需在各处加 category 判断。`EditDecision.action` 已支持 `"keep"`（`models.py:449` `Literal["delete", "keep"]`），无需改模型。

#### 3.3 前端类型（`types/project.ts:24-35`）

AnalysisResult 前端类型也需加 category（如有）：

```typescript
// 若有 AnalysisResult 接口，加：
export interface AnalysisResult {
  id: string
  type: string
  segment_ids: string[]
  confidence: number
  detail: string
  category?: string   // ← 新增
}
```

#### 3.4 前端分组（`SuggestionPanel.vue:63-107`）

当前 llm_smart 分组逻辑（`SuggestionPanel.vue:98-104`）：

```typescript
const llmSmartItems: SuggestionItem[] = props.edits
  .filter(e => e.source === "llm_smart")
  .map(e => {
    const analysis = props.analysisResults.find(r => r.type === "llm_smart_delete" && e.target_id && r.segment_ids.includes(e.target_id))
    return { id: e.id, editId: e.id, start: e.start, end: e.end,
             label: analysis?.detail || `智能删除 ${(e.end - e.start).toFixed(1)}s`,
             type: "llm_smart" as const, status: statusOf(e) }
  })
push("llm_smart", "智能删除", llmSmartItems)
```

改为按 category 拆分。**映射包成 `computed`**（响应式，props 更新时重算，避免 setup 时计算一次后失效）；**用 `analysis_id` 反查 category**（比 `target_id` 稳定：`target_id` 理论可为 null，且多 segment 批量场景可能映射被覆盖）：

```typescript
// 响应式映射：analysis_id -> category（在 <script setup> 顶层，与 groups computed 同级）
const smartCategoryByAnalysisId = computed(() => {
  const m = new Map<string, string>()
  for (const r of props.analysisResults) {
    if (r.type === "llm_smart_delete" && (r as any).category) {
      m.set(r.id, (r as any).category)
    }
  }
  return m
})

// 在 groups computed 内部使用：
const smartEdits = props.edits.filter(e => e.source === "llm_smart")
const normalItems: SuggestionItem[] = []
const partialItems: SuggestionItem[] = []

for (const e of smartEdits) {
  const analysis = props.analysisResults.find(
    r => r.type === "llm_smart_delete" && e.target_id && r.segment_ids.includes(e.target_id)
  )
  // 用 analysis_id 反查（比 target_id 稳定）
  const cat = e.analysis_id ? smartCategoryByAnalysisId.value.get(e.analysis_id) : ""
  const item = {
    id: e.id, editId: e.id, start: e.start, end: e.end,
    label: analysis?.detail || `智能删除 ${(e.end - e.start).toFixed(1)}s`,
    type: "llm_smart" as const, status: statusOf(e),
  }
  if (cat === "partial_delete") partialItems.push(item)
  else normalItems.push(item)
}
push("llm_smart", "智能删除", normalItems)
push("partial_delete" as any, "部分删除（需手动处理）", partialItems)
```

`ItemKind` 类型（`SuggestionPanel.vue:29`）需扩展：

```typescript
type ItemKind = "filler" | "error" | "silence" | "llm_smart" | "partial_delete"
```

`expandedGroups` 默认展开集（`SuggestionPanel.vue:26`）加入：

```typescript
const expandedGroups = ref<Set<string>>(new Set(["filler", "error", "llm_smart", "partial_delete"]))
```

#### 3.5 `totalPending` 排除 partial_delete（`SuggestionPanel.vue:109`）

当前：

```typescript
const totalPending = computed(() =>
  props.edits.filter(e => e.status === "pending" && e.action === "delete").length
)
```

由于 3.2 已让 partial_delete 的 EditDecision 用 `action="keep"`，而 `totalPending` 本就只统计 `action==="delete"`，**partial_delete 天然被排除**，无需额外 category 判断。原代码保持不变：

```typescript
// 无需修改！partial_delete 的 edit 是 action="keep"，已被 action !== "delete" 过滤
const totalPending = computed(() =>
  props.edits.filter(e => e.status === "pending" && e.action === "delete").length
)
```

> **说明**：这是 3.2 选择 `action="keep"` 的额外收益——从数据模型层面隔离 partial_delete，避免前端多处加 category 判断。

**交互**：partial_delete 分组点击后 `emit("seek", item.start)` 跳转，用户手动在波形图调整；组内右键菜单沿用问题 4 修复后的"确认/忽略/删除本组"。

---

## 问题 4：右键"全部撤销本组"改为永久删除该组建议

### 当前代码上下文

**右键菜单**（`SuggestionPanel.vue:341-358`）：

```html
<button @click="runGroupAction(contextMenu.group, 'confirm')">
  全部确认本组 ({{ contextMenu.group.items.length }})
</button>
<button @click="runGroupAction(contextMenu.group, 'reject')">
  全部忽略本组 ({{ contextMenu.group.items.length }})
</button>
<button @click="runGroupAction(contextMenu.group, 'reset')">
  全部撤销本组
</button>
```

**runGroupAction**（`SuggestionPanel.vue:155-162`）：

```typescript
function runGroupAction(group: GroupedResult, action: "confirm" | "reject" | "reset") {
  const ids = groupEditIds(group)
  if (ids.length === 0) { closeContextMenu(); return }
  if (action === "confirm") emit("confirm-edit-batch", ids)
  else if (action === "reject") emit("reject-edit-batch", ids)
  else emit("reset-edit-batch", ids)    // ← "撤销本组"实际是改回 pending
  closeContextMenu()
}
```

**事件链**：`SuggestionPanel` → `Timeline.vue:414` (`@reset-edit-batch` → `emit('reset-suggestion-batch')`) → `WorkspacePage.vue:2070` (`batchUpdateEdits(ids, 'pending')`) → `useAnalysis.ts:113` (`call("update_edit_decisions_batch", editIds, status)`)。

**后端**（`project_service.py:652-681`）：

```python
def update_edit_decisions_batch(self, edit_ids: list[str], status: str) -> dict:
    new_status = EditStatus(status)
    ids_set = set(edit_ids)
    updated_edits = []
    for edit in self.active_timeline.edits:
        if edit.id in ids_set:
            updated_edits.append(edit.model_copy(update={"status": new_status}))  # ← 改状态，不删除
        else:
            updated_edits.append(edit)
    self._update_active_timeline(edits=updated_edits)
```

**根因**："全部撤销本组"的语义应为"删除该组建议"，但现状是改回 `pending`。

### 实现规格

#### 4.1 后端新增接口（`project_service.py`）

在 `update_edit_decisions_batch` 下方新增：

```python
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    """Permanently remove edit decisions by id.

    Unlike update_edit_decisions_batch (which changes status),
    this removes the edits entirely from the timeline.
    """
    if self._current is None:
        return {"success": False, "error": "No project is open"}
    ids_set = set(edit_ids)
    updated_edits = [e for e in self.active_timeline.edits if e.id not in ids_set]
    removed = len(self.active_timeline.edits) - len(updated_edits)
    if removed == 0:
        return {"success": False, "error": "No matching edit decisions found"}
    self._update_active_timeline(edits=updated_edits)
    logger.info("Permanently deleted {} edit decisions", removed)
    return {"success": True, "data": self._current.model_dump()}
```

#### 4.2 `main.py` 暴露接口（`main.py:1433` 附近）

在 `update_edit_decisions_batch` 旁新增：

```python
@expose
def delete_edit_decisions_batch(self, edit_ids: list[str]) -> dict:
    return self._mark_dirty(self._project.delete_edit_decisions_batch(edit_ids))
```

> **`_mark_dirty` 与 `_update_active_timeline` 职责边界**（审计关切）：已核实现有架构中 `_update_active_timeline`（`project_service.py:76-89`）只更新内存 `_current`，**不触发任何 dirty/保存信号**。保存由 `main.py:_mark_dirty`（`main.py:123-132`）通过 emit `PROJECT_DIRTY` 事件驱动前端 debounce-save。因此 `delete_edit_decisions_batch` 必须且仅需在 `main.py` 外层包 `_mark_dirty`——这与所有现有写操作（如 `update_edit_decisions_batch`）模式完全一致，无重复触发风险。

#### 4.3 前端 composable（`useAnalysis.ts:106-119` 附近）

在 `batchUpdateEdits` 下方新增：

```typescript
/** v2.1.1: Permanently delete a group of edits (not just reset status). */
async function deleteEdits(editIds: string[]): Promise<boolean> {
  if (editIds.length === 0) return false
  if (onBeforeProjectUpdate && project.value) onBeforeProjectUpdate(project.value)
  const res = await call<Project>("delete_edit_decisions_batch", editIds)
  if (res.success && res.data) {
    project.value = res.data
    return true
  }
  return false
}
```

并在 return 块（`useAnalysis.ts:134-148`）导出：

```typescript
return {
  // ... 现有项 ...
  batchUpdateEdits,
  deleteEdits,        // ← 新增
  confirmAllEdits,
}
```

#### 4.4 SuggestionPanel 改动（`SuggestionPanel.vue`）

emit 声明（`:19` 附近）新增：

```typescript
const emit = defineEmits<{
  // ... 现有 ...
  "reset-edit-batch": [editIds: string[]]
  "delete-edit-batch": [editIds: string[]]   // ← 新增
}>()
```

`runGroupAction`（`:155`）扩展 action 类型，加 delete 分支，并对破坏性操作加二次确认：

```typescript
function runGroupAction(group: GroupedResult, action: "confirm" | "reject" | "reset" | "delete") {
  const ids = groupEditIds(group)
  if (ids.length === 0) { closeContextMenu(); return }
  if (action === "confirm") emit("confirm-edit-batch", ids)
  else if (action === "reject") emit("reject-edit-batch", ids)
  else if (action === "reset") emit("reset-edit-batch", ids)
  else if (action === "delete") {
    // 永久删除不可撤销，需二次确认；文案明确含已确认项避免语义模糊
    if (!confirm(`确认永久删除「${group.label}」中的 ${ids.length} 条建议（含已确认/已忽略）？此操作不可撤销。`)) {
      closeContextMenu()
      return
    }
    emit("delete-edit-batch", ids)
  }
  closeContextMenu()
}
```

右键菜单（`:353-358`）**保留原"撤销本组"并新增"删除本组"**（不替换，保持功能完整）：

```html
<!-- 保留：恢复 confirmed/rejected 为 pending（可逆） -->
<button
  class="block w-full text-left px-3 py-1.5 hover:bg-gray-100 text-gray-700"
  @click="runGroupAction(contextMenu.group, 'reset')"
>
  全部撤销本组
</button>
<!-- 新增：永久删除（不可逆，红色 + 文案明确含已确认项） -->
<button
  class="block w-full text-left px-3 py-1.5 hover:bg-red-50 text-red-600"
  @click="runGroupAction(contextMenu.group, 'delete')"
>
  删除本组建议（{{ contextMenu.group.items.length }} 条，含已确认）
</button>
```

#### 4.5 Timeline.vue 事件转发（`:414` 附近）

emit 声明（`:64-66` 附近）新增：

```typescript
"reset-suggestion-batch": [editIds: string[]]
"delete-suggestion-batch": [editIds: string[]]   // ← 新增
```

SuggestionPanel 绑定（`:414` 附近）新增：

```html
<SuggestionPanel
  ...
  @reset-edit-batch="(ids) => emit('reset-suggestion-batch', ids)"
  @delete-edit-batch="(ids) => emit('delete-suggestion-batch', ids)"   <!-- ← 新增 -->
>
```

#### 4.6 WorkspacePage 接线（`:2068-2070` 附近）

```html
<Timeline
  ...
  @reset-suggestion-batch="(ids: string[]) => batchUpdateEdits(ids, 'pending')"
  @delete-suggestion-batch="(ids: string[]) => deleteEdits(ids)"   <!-- ← 新增 -->
/>
```

（`deleteEdits` 从 `useAnalysis` 解构导入，与 `batchUpdateEdits` 同处。）

---

## 实施顺序与依赖关系

### 推荐顺序

1. **问题 2（id 唯一性修复）** — 最紧急，功能性 bug，改动集中在 `main.py:769` + `project_service.py:1239` + 数据迁移
2. **问题 4（删除本组）** — 功能性修复，前后端各加一个接口，链路清晰
3. **问题 3（提示词 + 部分删除分组）** — 需改模型 + 提示词 + 前端分组，改动较大
4. **问题 1（按钮融入 UI）** — 纯样式，风险最低

### 依赖关系图（审计补充）

```
问题 2（id 唯一性 + 数据迁移）
   │
   ├─ 迁移 _dedupe_edit_ids 只改 edit.id，不碰 analysis_result.category
   │  → 与问题 3 加 category 字段无冲突（旧数据 category 默认 ""，迁移正常）
   │
   └─ 问题 3（加 AnalysisResult.category）
       │
       └─ 问题 4（删除本组）
           │
           └─ partial_delete 组的右键也会出现"删除本组建议"
              → 用户可能误删"需手动处理"的建议
              → 可接受：partial_delete 本就是建议，删除后用户可重跑智能删除再生
              → 文案已明确"含已确认 N 条"，足够警示
```

**关键交叉点**：
- 问题 2 的数据迁移在 `open_project` 加载时跑，问题 3 的 category 字段默认 `""`，两者无冲突。
- 问题 3 让 partial_delete 用 `action="keep"`，问题 4 的"删除本组"对 partial_delete 组同样适用（删除 keep 类型的 edit），语义一致。

### 回滚预案

- **问题 2 数据迁移**修改了 `project.json` 中的 `edit.id`。迁移前由 `open_project` 自动备份 `project.json.bak.{timestamp}`（仅当检测到重复 id 时）。迁移仅改 `edit.id`，不改其他字段，出错时可从备份恢复。
- **问题 3 提示词变更**可能影响所有用户的智能删除结果。建议：
  - 保留旧提示词为 `_SMART_DELETE_SYSTEM_LEGACY`，通过 `data/settings.json` 的 `smart_delete_prompt_version` 字段切换（默认新版，可回退）。
  - 实施后做 A/B 测试（同数据新旧提示词各跑一次），确认 semantic_dup 召回率无回归再全量发布。

---

## 测试要点

### 问题 2（id 唯一性）

1. 重新运行独立智能删除，验证每个 llm_smart edit 拥有唯一 id（`edit-llm_smart_{ts}_{i}`）
2. 单项确认/忽略**不影响**其他项
3. 加载已有重复 id 的旧项目（如 `20260514-潘多拉之心第二卷卷评`），验证迁移后 id 唯一
4. 工作流模式（`apply_workflow`）回归：edits 仍唯一（路径 B 本就正确）
5. **同一 `ar.id` 出现 ≥3 次时**，后缀递增是否正确（`_dup2`, `_dup3`, `_dup4`）
6. **迁移二次冲突**：构造 edits = `["a", "a", "a_dup2"]`，验证第二个 "a" 重命名为 `a_dup3`（不撞已有的 `a_dup2`）
7. **大型项目性能**：含 1000+ edits 的项目迁移耗时应 < 100ms（快速跳过 `len(ids)==len(set(ids))` 保证无重复时零开销）
8. **迁移前备份**：检测到重复 id 时应生成 `.bak.{timestamp}` 文件

### 问题 3（提示词 + 部分删除）

1. 用 `20260514-潘多拉之心第二卷卷评` 验证"部分删除"分组捕获 `seg-0085` 等口误+修正句
2. `totalPending` 不含 partial_delete（因 `action="keep"` 天然排除）
3. **semantic_dup 召回率回归**：新提示词下不应下降（A/B 对比）
4. **旧项目兼容**：无 category 字段的旧数据加载到新前端，应全部进入 normal 组（category 默认 `""`）
5. 波形图上 partial_delete 区段**不显示删除标记**（因 `action="keep"`）
6. 导出时 partial_delete 区段**不被删除**（因 `action="keep"`）

### 问题 4（删除本组）

1. 右键组 → "删除本组建议" → 弹出二次确认 → 确认后 edits 从 `project.json` 中消失（非 pending）
2. 取消二次确认 → edits 不变
3. **持久化验证**：删除后立即关闭/重开项目，确认 edits 仍缺失
4. **反查完整性**：删除一组后，剩余 edits 的 `analysis_id` 仍可正确反查 analysis_result（删除只移除 edit，不动 analysis_result）
5. **保留 reset**：右键仍有"全部撤销本组"，可将 confirmed/rejected 恢复为 pending
6. **混合状态组**：含已确认项的组，文案显示"含已确认"

### 问题 1（按钮 UI）

1. 侧边栏开/关/Tab 切换，关闭按钮在 Tab 栏行内
2. 展开按钮扁平但在波形图上**仍可见**（`bg-white/40 backdrop-blur-sm` 保证对比度）
3. Tab 标签（如"静音"）触发区不被关闭按钮挤压（`min-w-0` + `truncate`）

---

## 涉及文件（修订后）

| 文件 | 改动 |
|------|------|
| `main.py` | 问题2: `_handle_smart_delete` analysis_result id 加序号 + category 透传 + partial_delete 用 `action="keep"`; 问题4: 新增 `delete_edit_decisions_batch` expose（`list[str]` 注解） |
| `core/project_service.py` | 问题2: `add_analysis_results` edit_id 防御性去重（`_dup{N}`）+ `_dedupe_edit_ids` 迁移（含 while 二次冲突防御 + 快速跳过 + 备份）; 问题4: 新增 `delete_edit_decisions_batch` |
| `core/workflow_engine.py` | 问题2: `_extract_edits_from_result` 补 id 唯一性兜底防御 |
| `core/models.py` | 问题3: `AnalysisResult` 增加可选 `category` 字段（`EditDecision` 无需改，复用现有 `action="keep"`） |
| `core/llm_prompts.py` | 问题3: `_SMART_DELETE_SYSTEM` 增加 `partial_delete` + 修订 `self_correct` 规则 + few-shot 示例 |
| `frontend/src/types/project.ts` | 问题3: AnalysisResult 接口加 `category?`（如有接口定义） |
| `frontend/src/components/workspace/SuggestionPanel.vue` | 问题3: 新增 partial_delete 分组（`computed` 映射 + `analysis_id` 反查）; 问题4: 右键保留"撤销本组" + 新增"删除本组"（二次确认） |
| `frontend/src/components/workspace/Timeline.vue` | 问题1: 关闭按钮融入 Tab 栏（`min-w-0`/`truncate`/`z-10`）、展开按钮改扁平（`bg-white/40 backdrop-blur-sm`）; 问题4: `delete-suggestion-batch` 事件转发 |
| `frontend/src/composables/useAnalysis.ts` | 问题4: 新增 `deleteEdits` 函数并导出 |
| `frontend/src/pages/WorkspacePage.vue` | 问题4: 接线 `@delete-suggestion-batch` → `deleteEdits` |

---

## 审计意见落实对照表

| 审计项 | 优先级 | 落实情况 |
|--------|--------|---------|
| 问题2 Bug1（迁移二次冲突） | P0 | ✅ 2.3 `_dedupe_edit_ids` 加 `while candidate in all_ids` 防御 |
| 问题3 缺口1（EditDecision 无 category） | P0 | ✅ 3.2 partial_delete 改用 `action="keep"`（无需改 EditDecision 模型） |
| 问题4 缺口1（二次确认） | P1 | ✅ 4.4 `runGroupAction` delete 分支加 `confirm()` |
| 问题2 命名一致性 | P1 | ✅ 2.2/2.3 统一为 `_dup{N}` |
| 问题3 缺口3（computed 作用域） | P1 | ✅ 3.4 `smartCategoryByAnalysisId` 包成 `computed` |
| 问题4 缺口2（保留 reset） | P2 | ✅ 4.4 保留"撤销本组" + 新增"删除本组"两个菜单项 |
| 问题3 缺口4（提示词 few-shot） | P2 | ✅ 3.1 加 3 条 few-shot 示例 + A/B 测试提示 |
| 问题1 z-index/可见性 | P3 | ✅ 1. 关闭按钮 `z-10`、展开按钮 `bg-white/40 backdrop-blur-sm` |
| 问题3 缺口2（analysis_id 反查） | P1 | ✅ 3.4 改用 `analysis_id`（比 `target_id` 稳定） |
| 问题4 类型注解 | P3 | ✅ 4.2 `list[str]` |
| 问题4 `_mark_dirty` 耦合 | — | ✅ 4.2 注明现有架构职责边界（不成立，无需特殊处理） |
| 问题3 Pydantic extra | — | ✅ 已核实模型无 `extra="forbid"`，加字段安全 |
| 跨问题：依赖关系图 | P2 | ✅ 新增"实施顺序与依赖关系"章节 |
| 跨问题：回滚预案 | P2 | ✅ 新增迁移前 `.bak` 备份 + 提示词版本切换 |
| 跨问题：测试矩阵 | P2 | ✅ 扩展至 23 条测试要点 |

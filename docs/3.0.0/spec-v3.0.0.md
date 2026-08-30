# v3.0.0 实施规格说明（SPEC）

> **版本**: 3.0.0
> **基准**: v2.4.0 (`origin/main`)
> **分支**: `dev-3.0.0`
> **规格文档**: `docs/3.0.0/spec-v3.0.0.md`
> **需求文档**: `docs/3.0.0/PRD-v3.0.0.md`
> **来源**: 竞品深查报告 v2（`docs/competitor/MAW-竞品分析与优化报告-v2.md`，含源码证据）
> **工程约束**: 全程遵守 AGENTS.md（`uv run` / `bun` / API 信封 / 事件名双端同步 / 无 emoji / Pydantic v2 frozen）

---

## 概要

v3.0.0 按 PRD 四支柱分四批实施。本 SPEC 按**模块（M）**组织，每个模块给出：现状与根因（文件+行号）、实施方案（含关键代码）、测试规格、迁移/兼容注意。模块与 PRD 需求编号映射见文末总表。

### 模块划分

| 模块 | 内容 | 批次 | 预估改动 |
|------|------|------|---------|
| M1 | 词级数据保真（A1/A2/A3/D1.1） | 1 | 后端 3 文件 + 测试 |
| M2 | 持久化安全（A4） | 1 | 后端 1 文件 + 文档 |
| M3 | LLM 可靠性协议（A5） | 1 | 后端 2 文件 + 前端 1 文件 |
| M4 | bridge 批量事件 + 自适应 tick（B1） | 2 | pywebvue 2 文件 + 前端 1 文件 |
| M5 | 分层撤销快照（B4 + A6） | 2 | 前端 2 文件 + 后端 1 文件 |
| M6 | 波形渲染管线第一阶段（B2） | 2 | 前端 3 文件 |
| M7 | 字幕列表虚拟滚动（B3 + B5） | 2 | 前端 3 文件 |
| M8 | SettingsModal / WorkspacePage 拆分（C1/C2） | 3 | 前端 ~12 文件 |
| M9 | 层级契约 + 风格 lint（C3/C5） | 3 | 前端全局 + 文档 |
| M10 | project_service 分域（C4） | 4 | 后端 3 文件 |
| M11 | words 消费 + 多轨结构 + 波形缓存（D1/D2/D3） | 4 | 后端 3 文件 + 前端 2 文件 |

---

## M1: 词级数据保真

### M1-1: 删除转写 SRT 回灌（PRD A1）

**现状**: `main.py:_handle_transcription` L590-653。L596 `update_transcript()` 已把含 words 的结构化 segments 落库；L600-646 导出剥掉 words/speaker 的 SRT 到 `data/transcripts/`；**L648-653 `self.import_srt(srt_path)` 把贫化数据整体替换回项目**，words/speaker 全丢、id 退化为 `seg-0001`。

**方案**:

```python
# main.py L648-653 -- Before:
# Import the auto-saved SRT back into the project
if srt_path:
    try:
        self.import_srt(srt_path)
    except Exception as e:
        logger.warning("Failed to import auto-saved SRT: {}", e)

# After: 整段删除。SRT 保留为归档交付物，不再读回。
```

同时确认 L655-660 返回值不变（`srt_path` 继续返回，供 UI 展示归档路径）。

**注意**: 全仓检索 `srt_path` 消费点（`useTask.ts`/`useWorkflow.ts`），确认没有逻辑依赖"回灌后 id 重排"。

**测试**: `tests/test_transcription_words.py` 新增：
- `test_transcription_keeps_words`: mock ASR 返回含 words 的 segments，跑 `_handle_transcription`，断言 `project.active_timeline.transcript.segments[0].words` 非空、`transcript.engine` 正确。
- `test_manual_srt_import_unchanged`: 手动 `import_srt` 路径行为不变（id 顺序号语义保留）。

### M1-2: split/merge 维护 words（PRD A2）

**现状**: `core/project_service.py:split_segment`（L1256 附近）按 `position` 字符比例切文本，但把完整 `words` 复制进 a、b 两段；`merge_segments` 只保留第一段 words。

**方案**: 新增 `core/timeline_utils.py` 纯函数（与 `_current` 解耦，便于单测）：

```python
def split_words(words: list[Word], text: str, position: int,
                 a_text: str, b_text: str) -> tuple[list[Word], list[Word]]:
    """按文本切分点把 words 分成两半。

    策略：累计词文本长度逼近 position 找词边界；偏差 > 2 字符（标点/空格噪声）
    视为不可靠，返回 ([], []) —— 宁可缺失，不可错位。
    """
```

- `split_segment` 调用后：a/b 段 `words` 分别赋值，二者同时为空或同时有效
- `merge_segments`: `merged.words = [*first.words, *second.words]`（天然按 start 有序，前置条件是两段自身有序）
- EditDecision 的 ED-rebind 逻辑（L1300-1350）不动

**测试**: `tests/test_segment_words.py`:
- split 后 `a.words + b.words` 的 word 序列 == 原段 words（对齐成功场景）
- 不可靠切点场景：两段 words 均为空，不抛错
- merge 后 words 为拼接且有序

### M1-3: parse_srt 编码回退（PRD A3）

**现状**: `core/subtitle_service.py:16 parse_srt` 硬编码 `utf-8-sig`；`validate_srt`（L73）有 gb18030/latin-1 回退但导入路径未复用。

**方案**: 提取共享 `_read_text_with_fallback(path) -> str`（编码顺序 utf-8-sig → gb18030 → latin-1，逐个 try），`parse_srt` 与 `validate_srt` 均调用。

**测试**: 用 GB18030 编码生成中文 SRT 夹具，`parse_srt` 成功且文本无乱码。

### M1-4: 拆分吸附词边界（PRD D1.1，随本模块一并落地后端部分）

`split_segment` payload 新增可选 `snap_to_word: bool = false`：为 true 且段含 words 时，把传入 `start`（切点时间）吸附到最近词边界（`bisect` 词 start），再走 M1-2 切分。前端在 M7 之后接 UI（波形右键拆分默认开启吸附，提示"已吸附词边界 ±Nms"）。

---

## M2: 持久化安全

**现状**: `core/project_service.py` save 路径 `model_dump_json(indent=2)` → 写 tmp → `os.replace`。无 fsync、无备份、无损坏恢复。

**方案**: 新增 `core/persistence.py`：

```python
def atomic_save_with_backup(path: Path, content: str, keep: int = 2) -> None:
    """tmp 写入 -> flush+fsync -> 轮换 .bak.N -> os.replace -> fsync 目录(fd 不可用时跳过)."""
```

- 备份轮换：`project.json.bak.1` ← 当前文件，`bak.2` ← 旧 bak.1（copy，不 rename，避免覆盖窗口）
- `open_project` 失败处理链：主文件 JSON 损坏/`Project.model_validate` 失败 → 尝试 bak.1 → bak.2 → 全部失败返回 `{"success": False, "error": "项目文件损坏且无可用备份", "data": {"tried": [...]}}`
- 从备份恢复成功时在返回 data 中带 `recovered_from` 字段，前端 toast 提示"已从备份恢复（保存时间约 X）"
- 新增 `docs/PROJECT_SCHEMA.md`：字段契约、版本迁移规则（`_migrate_*` 链的现状梳理）

**测试**: `tests/test_persistence.py`:
- 断电模拟：写一半的 tmp 不影响主文件
- 主文件损坏 → bak.1 可恢复且 `recovered_from` 正确
- 连续 save 三次后 bak 轮换正确

---

## M3: LLM 可靠性协议

**现状**: `core/llm_service.py`（1303 行）。已有：`call_llm` 3 次指数退避重试（L198-207 区分不可重试错误）、`chunk_transcript_by_count`（L314-363 overlap+target_ids）、4 层 JSON 解析、温度默认 0.3（L71）。缺陷：批失败静默丢弃、无字符上限、无消毒、无 SSRF 校验、真实主键+时间发给模型。

### M3-1: 批账本与漏批重试

在批处理执行处（smart_delete 与 subtitle_correction 的共享循环，M10 会抽 `BatchExecutor`，本模块先在两处分别实现同规格）：

```python
@dataclass
class BatchLedger:
    total: int = 0
    succeeded: int = 0
    retried_ok: int = 0
    failed: list[str] = field(default_factory=list)   # batch indexes
    uncovered_segment_ids: list[str] = field(default_factory=list)
```

- 失败批自动重试 1 次（复用原 payload）
- 任务返回值增加 `ledger` 字段；`task:completed` 事件携带
- `uncovered_segment_ids` 非空时结果 UI（AIAssistantPanel）显示覆盖缺口条（"本次分析未覆盖 N 段，已标灰"），对应段在 SuggestionPanel 标记"未覆盖"

### M3-2: 批字符上限

`chunk_transcript_by_count` 增加参数 `max_chars: int = 4000`：累计字符超限时提前截断当前批（保证单 target 段不被拆散），与 `batch_size` 取先到者。设置项 `llm.max_batch_chars` 暴露到 SettingsModal LLM tab。

### M3-3: 响应消毒

解析前新增 `_sanitize_response(text)`：
1. 剥 ```json / ``` 围栏（现有部分解析层已处理，统一上提）
2. 剥 `<think>...</think>` 块（DeepSeek R1 系列）
3. 取首个 `{` 到最后一个 `}` 之间的内容（兜底）

### M3-4: SSRF 校验

`_resolve_base_url` 处：解析 host → `ipaddress` 解析（域名先 `socket.getaddrinfo` 全部结果）→ 任一命中环回/私网/链路本地段即拒绝，错误信息引导配置 `llm.allow_local_urls: true` 放行（默认 true 当 provider 为 ollama，其余默认 false）。**注意**: Ollama 默认 `http://localhost:11434`，preset 选择 ollama 时自动放行，避免打断现有用户。

### M3-5: 温度与不透明 ID

- `settings.get("llm_temperature", 0.3)` 默认改 0.1（core/config.py:62 与 demo mock demoBridge.ts:55 的 0.2 一并对齐，消除三处默认值分叉）；LlmConfig 增加 `temperature_override`，`run_semantic_search` 路径传 0.0（核验确认四路径现共用单一温度，llm_service.py:71→135）
- 批组装时建映射 `real_id -> f"t{i}"`，发给模型的 segments 只含 `{id, text}`（去掉 start/end/type 等字段）；解析结果经映射还原。`_assert_timestamps_unchanged` 断言保留

### M3-6: 工作流回滚（PRD A6，依赖 M5）

`workflow_engine` 步骤执行前调 `project_service.export_layer_snapshot()`（M5 提供）；步骤失败且用户选择回滚时经 patch 通道逆应用。快照随 workflow 跨会话持久化格式（v2.0.0 快照机制）扩展 `layer_snapshot` 字段。

**测试**: `tests/test_llm_ledger.py`（mock 批失败/重试/未覆盖）、`tests/test_llm_sanitize.py`（think 块/围栏/前后缀闲文本）、`tests/test_llm_ssrf.py`（私网拒绝/ollama 放行）、`tests/test_llm_opaque_ids.py`（映射往返一致、断言不触发）。

---

## M4: bridge 批量事件 + 自适应 tick

**现状**: `pywebvue/bridge.py:_flush_events()`（L92-115）逐事件 `evaluate_js(f"window.dispatchEvent(new CustomEvent('{name}', {{detail:{json}}}))")`；`pywebvue/app.py` 注入的 JS tick 循环固定 50ms。

### M4-1: 批量投递协议

```python
# bridge.py -- Before: 每事件一次 evaluate_js (bridge.py:92-115)
# After: 队列非空时一次调用; 注意派发目标必须是 document (与 bridge.ts onEvent 监听一致)
payload = json.dumps(
    [{"name": f"pywebvue:{e[0]}", "detail": e[1]} for e in batch],
    ensure_ascii=False,
)
self._window.evaluate_js(f"window.__pywebvueDispatchEvents({payload});")
```

前端 `bridge.ts` 注入（经 `pywebvue/app.py` 的 bootstrap JS）：

```js
window.__pywebvueDispatchEvents = (events) => {
  for (const ev of events) {
    // 与旧路径一致: document + bubbles (bridge.py:100-104 原语义)
    document.dispatchEvent(
      new CustomEvent(ev.name, { detail: ev.detail, bubbles: true }),
    );
  }
};
```

- 兼容：保留单事件 `__pywebvueDispatch`（改名前先探测 `typeof window.__pywebvueDispatchEvents === 'function'`，不存在走旧路径）——防旧前端_dist 搭新后端
- **payload 上限**：单批 JSON > 512KB 时拆多次投递（避免 evaluate_js 长字符串卡主线程）

### M4-2: 自适应 tick

> 核验修正：`run_on_bridge`/`_task_queue` 全仓零调用方（见风险评审指南 §1-#5），自适应 tick 只需考虑事件延迟，任务超时约束不存在。

JS 侧 tick 循环：连续 40 次空转 → 间隔升 250ms；`tick()` 返回值从 `{"success": True}` 扩展为 `{"success": True, "data": {"pending": <事件队列长度>}}`，JS 据 pending 决定快档（50ms）/降档（250ms）。**最坏延迟承诺**：空闲态首个事件 ≤ 250ms（交互调用走 `call()` 通道不经事件队列，不受影响）。`_execute_next_task`/`run_on_bridge` 死代码移入 M9-3 清理。

### M4-3: 事件 payload 瘦身（核验修正：6 个具体修改点）

核验确认 `task:completed` 事件 result 在 6 个 handler 携带全量 project dump（main.py:183 静音检测 / 455 波形 / 656 转写 / 794 智能删除 / 891 纠错 / 987 精华）。改造：

- handler **同步返回值不动**（`call()` 通道不走 evaluate_js，无 IPC 问题）
- `task:completed` 事件 detail 改为 `{task_id, task_type, result_meta, project_stripped: true}`（result_meta 含 revision/layer_names 摘要）；前端 `useTask.ts` 检测 `project_stripped` 后经 `get_project` 拉取，无标记走旧路径（兼容旧前端_dist）
- `task:progress` 已是轻量（task_manager.py:343-349 仅 task_id/percent/message），不动
- `core/events.py` 与 `frontend/src/utils/events.ts` 注释登记 payload 约定

**测试**: `tests/test_bridge_batch.py`（单事件/批量/超限拆分/降级路径）；手动回归 macOS 首启动（`__BRIDGE_READY__` 握手时序不变）。

---

## M5: 分层撤销快照

**现状**: `frontend/src/composables/useUndoRedo.ts` L22-30 `JSON.stringify(project)` 整包入栈，50 条上限、>2MB 降 10 条；undo 后 emit 全量覆盖，可能回退后端 revision。

### M5-1: 快照结构

```ts
// utils/undoRecords.ts (新)
export type UndoLayer = 'segments' | 'edits' | 'analysis' | 'media' | 'active_timeline_id';
export interface UndoRecord {
  id: string;
  label: string;                    // 操作名，用于 UI 历史菜单
  createdAt: number;
  records: Partial<Record<UndoLayer, unknown>>;  // before 快照，仅受影响层
}
```

- `pushSnapshot(layers: UndoLayer[], label)`：调用点从"操作前全量 push"改为"操作前按层 push"（edits 层直接存引用副本；segments 层 M5-3 段级化）
- 跨层操作（split 动 segments+edits）单条记录多 layer，undo 原子应用

### M5-2: undo 走 patch 通道

undo 时构造逆 patch：`{revision: current+1, <layer>: before}` 经 `applyProjectPatch` 应用，再调用对应后端写接口同步真源（或新增 `undo_apply` @expose 方法——**采用后者**：后端 `project_service.apply_undo(layers_payload)` 负责替换层内容并递增 revision，保证前端不可伪造 revision）。redo 同理用 after。

**红线**: undo/redo 后 `project._revision` 必须 > 操作前；`is_stale_patch` 行为不变。

### M5-3: segments 层段级 diff（第二步，可降级）

- 快照存 `Map<segmentId, Segment | null>`（null=删除，缺席=不变）
- split/merge 的 id 演化：记录 `id_lineage`（新 id → 旧 id），undo 时按 lineage 整组回滚
- 若复杂度失控，降级方案：segments 层保留"数组引用副本"（浅拷贝 segment 列表，不 stringify），内存仍远低于全量 JSON 字符串

**上限**: 100 条；分层后单条通常 < 100KB，取消 2MB 降级规则。

**测试**: `useUndoRedo.test.ts` 重写：分层快照正确性、跨层原子 undo、revision 单调、split→undo→redo 的 id 稳定性、100 条上限。

---

## M6: 波形渲染管线第一阶段

**现状**: `WaveformCanvas.vue` L104 每次重绘 `canvas.width = rect.width * dpr`；L239-241 `watch(metrics.viewStart, draw)` 同步触发；`PlayheadOverlay.vue` Vue 响应式驱动。

### M6-1: rAF 合帧 + 分辨率按需重设

```ts
// WaveformCanvas.vue
let drawPending = false;
function scheduleDraw() {
  if (drawPending) return;
  drawPending = true;
  requestAnimationFrame(() => { drawPending = false; draw(); });
}
// watch(viewStart/viewDuration) -> scheduleDraw()
// draw() 内: 仅当 rect/dpr 变化时执行 canvas.width 赋值, 否则 clearRect + 重画
```

- 删除 L97 的 0.02s 时间去重（rAF 合帧后冗余）
- `matchMedia(`(resolution: ${dpr}dppx)`)` 监听 dpr 变化（WKWebView 跨屏），变化时置尺寸 dirty

### M6-2: hover seek 预览

波形 pointermove 只记录 `pendingHover = {x, t}`，rAF 帧内更新一个轻量 DOM 指示条（时间 tooltip + 垂直线，`pointer-events: none`）；点击才调 `video.currentTime = t`。不触发 Vue 状态更新（用 ref 直接操作 style）。

### M6-3: 播放头命令式

`PlayheadOverlay.vue`: 模板保留空壳 div；`video.timeupdate` + rAF 插值驱动 `el.style.transform = translateX(...)`。Vue 状态只存 `paused`（暂停态显示光标样式）。`currentTime` 从 WorkspacePage 的响应式依赖中移除（视频域内部持有非响应式 ref）。

**测试**: 组件测试验证 scheduleDraw 合帧（连续 10 次 scheduleDraw 只 1 次 draw）；手动回归 WebView2/WKWebView 滚动流畅度。

---

## M7: 字幕列表虚拟滚动 + patch 细粒度化

### M7-1: patch 细粒度化（先做，B5）

`utils/projectPatch.ts` 应用 segments 层时：

```ts
// Before: segments: [...patch.segments]  (整体引用替换)
// After: 若 patch 带 segment 级标识 -> 按 id 原位替换/插入/删除, 其余元素引用不变
```

- 后端 `_success_patch` 的 segments 层序列化保持不变（全量数组）；**前端应用时**先 diff：构造 `Map<id, newSeg>`，遍历现有数组按 id 替换，新增段按 start 插入（后端已保证有序，直接 concat + 局部排序）；被删 id 过滤。O(n) 单次遍历，未变元素引用稳定 → `v-memo` 生效
- `mergedSegments`/`segmentStateMap` 等 computed 因引用稳定自动跳过重算

### M7-2: 虚拟滚动

`Timeline.vue` 改造：
- 行高归一：TranscriptRow 单行/双行模式统一行高（测量最复杂的一步，含静音行）
- 窗口化：可视区 + 上下缓冲 10 行；容器监听 scroll（rAF 节流）维护 `visibleRange`。**混合行类型**（TranscriptRow 与 SilenceRow 两分支，Timeline.vue:327/357）：窗口渲染器内部按 `seg.type` 分派组件；行高当前统一（TranscriptRow min-h-52px 单行 truncate，核验确认无展开模式），测高器按组件类型注册并预计算累积偏移数组（二分定位），为未来变高行零成本预留
- 原位替换守门断言（M7-1）：应用后数组 id 序列必须与后端 patch.segments 完全一致，不一致即回退整体替换并 `console.warn`（宁可慢，不可错序）
- 快捷键/搜索/active 跟随跳转不可见行时先 `scrollIntoView` 再更新 range
- 上下文菜单、多选、拖拽在虚拟行上保持（右键菜单已是全局管理，风险低）
- 空间占用：`v-for` 渲染 `segments.slice(start, end)`，外层撑高 div 用总行数 × 行高

**验收**: 1167 段参考项目实测滚动 ≥ 55fps；`uv run pytest` + vitest 全绿；键盘导航回归（A/W/D/S、Home/End、搜索跳转、播放跟随）。

---

## M8: 组件拆分

### M8-1: SettingsModal → 5 tab 组件

一比一拆：`GeneralSettingsTab.vue` / `AiEngineSettingsTab.vue` / `LlmSettingsTab.vue`（内部再拆 `PromptEditor.vue`、`PresetManager.vue`）/ `ExportSettingsTab.vue` / `ShortcutsSettingsTab.vue`。SettingsModal 保留 `activeTab` 状态 + `loadSettings/handleSave`。props: `settings`、emits: `update:settings`/`save`。tab 组件按 `v-if` 惰性挂载。

### M8-2: WorkspacePage 三步瘦身

1. **S**: 3 个内联 popover → `TranscribeSettingsPopover.vue` / `SilenceSettingsPopover.vue` / `SubtitleTrimSettingsPopover.vue`（纯模板+局部状态搬移）
2. **S**: ASR 引擎域（L248-758 约 250 行）→ `composables/useAsrEngines.ts`，SettingsModal 的 AiEngine tab 同步接入（消除双实现）
3. **M**: 20+ 个 `handleXxx` 中转 → `composables/useWorkspaceActions.ts`，按编辑/时间线/纠错三组归口；子组件事件经 provide/inject 的 action 对象调用，减少逐层 emit

**迁移红线**（写入 PRD 风险表的执行清单；配套迁移清单文档 `docs/3.0.0/migration-M5.md` 逐点勾销）：
- undo pushSnapshot 调用点迁移前后逐一 diff 核对：直接调用 3 处（WorkspacePage.vue:940/1124/1427）**及 useAnalysis/useEdit 内部注入调用**（核验确认 composables 内部亦调用，原清单遗漏）
- `projectRef` computed get/set 双向绑定：子组件只能经 action 层写，不得直接改引用
- 全局 keydown（L1464-1554）与 SegmentBlocksLayer capture 监听时序：迁移后跑 Esc/方向键/Delete/文本输入冲突回归

---

## M9: 层级契约 + 风格 lint

### M9-1: z-index token

`style.css` `@theme` 增加：

```css
--z-base: 100;      /* 普通文档流 */
--z-raised: 200;    /* 悬浮卡片、sticky 工具栏 */
--z-dropdown: 300;  /* popover / dropdown / 右键菜单 */
--z-modal: 400;     /* 模态框 */
--z-toast: 500;     /* toast / 通知 */
```

- 全仓替换：`z-[9999]`（SegmentBlocksLayer L398）→ `z-dropdown`；`z-20` 系列 → 对应档；`ToastContainer` → `z-toast`
- popover 统一 `<Teleport to="body">` + 层级 token + outside-click 关闭；删除 `closeallcontextmenus` 全局广播（`contextMenuManager.ts` 改为单实例互斥：打开新菜单自动关闭旧菜单）
- **上翻方向双测**：任何向上弹出的 popover 必须验证"贴着 sticky 工具栏/布局分隔条打开"场景（竞品同坑三次的教训，规则写入 DESIGN.md）

### M9-2: DESIGN.md 与风格 lint

- 新增 `docs/DESIGN.md`：层级契约（4 条规则）+ 可读性约束（正文/标签/控件最小 11px，对比度 AA ≥ 4.5:1，例外清单显式列出）
- eslint 自定义规则或 CI grep 清单：业务 `.vue` 禁 `text-gray-*`/`bg-amber-*` 等原始灰阶彩阶类、裸 `z-[N]`、模板内硬编码 hex（波形 canvas 常量改引 CSS 变量 `getComputedStyle` 或共享常量模块）
- 深色磁贴下的白底 popover（转写设置）改用 surface token

### M9-3: 存量清理

后端 ruff 40 问题清零（`bridge_service/config/project_service/workflow_engine/scripts/tests`）；workflow_engine 弃用死代码删除；`v-html` 两处警告处理（转义或移除）。

---

## M10: project_service 分域

- `core/correction_service.py`：承接字幕纠错 CRUD/apply（`project_service.py` L1707-2180 约 900 行）。接口 `CorrectionService(project_service)` 持有只读 project 访问 + 经 `project_service` 的写方法回写；`main.py` 的 @expose 方法委托调用，**bridge 方法名与信封不变**
- `core/migrations.py`：`_migrate_to_v2` 及四个后续 `_migrate_*`（约 350 行），`ProjectService._open_internal` 调 `migrations.migrate(raw: dict) -> dict`
- 零行为变化：纯搬移 + 现有 478 条 pytest 锚定 + 新增契约测试（迁移链各版本夹具跑通）

---

## M11: 能力接线（D 支柱）

### M11-1: words 消费（D1.2/D1.3）

- **纠错回贴**: `correction_service.apply` 时，若旧文本与新文本可按词对齐（`difflib.SequenceMatcher` on word 序列），未变区域 words 保留、变更区域清空该词；比例 < 50% 变化时整体保留时间戳重对齐，否则清空段 words。规则：**宁可缺失，不可错位**
- **波形 hover 词高亮**: SegmentBlocksLayer hover 时若当前段含 words，二分定位当前时间的词并在块内高亮（纯展示，不影响数据）

### M11-2: 多轨数据结构（D2）

```python
# core/models.py 新增（frozen, 契约对齐现有风格; 时间保持 float 秒 + round3）
class SubtitleTrack(BaseModel, frozen=True):
    id: str
    role: str = "extension"          # 预留 translation/caption
    name: str = ""
    language: str = ""
    segments: list[Segment] = Field(default_factory=list)

class TrackBinding(BaseModel, frozen=True):
    id: str
    track_id: str
    main_segment_id: str
    extension_segment_id: str
    start_offset: float = 0.0        # 副轨相对主轨偏移(秒)
    end_offset: float = 0.0

# TranscriptData 增加:
    tracks: list[SubtitleTrack] = Field(default_factory=list)
    bindings: list[TrackBinding] = Field(default_factory=list)
```

- `ProjectPatch`（core/project_patch.py）增加 `tracks: list[dict] | None`、`bindings: list[dict] | None` 层，插在 timeline 内层组（analysis 与 media 之间，对齐 models.py:401-411 字段分组）；`frontend/src/utils/projectPatch.ts` 同步（含 `describePatchLayers`）
- **构造保护（核验修正，必做）**：`update_transcript`（project_service.py:605）、`add_silence_results`（:886）、`add_segment`（:1132）三处现有 `TranscriptData(segments=...)` 重建会静默丢 tracks/engine/language——一律改 `transcript.model_copy(update={"segments": ...})`；新增契约测试锁定三方法保留 tracks；transcript 级元数据更新走新增 `update_transcript_meta`
- `_enforce_segment_sort_invariant` **只管主轨**（显式注释锁定）；副轨各 track 自维护有序；副轨段 id 命名空间隔离（`track_{trackId}_seg_{start:.3f}`）防与主轨 merge/决策系统误匹配
- MVP UI：导入对话框"作为副轨导入"→ `import_srt_as_track(path, language)`（parse 后 300ms 容差与主轨匹配生成 bindings）；Timeline 底部折叠 lane 只读显示；导出对话框增加"主轨 SRT / 副轨 SRT"
- 绑定联动、波形双 lane、绑定/解绑交互 → v3.1，本版 bindings 只写不消费
- 时间轴裁剪（`_map_to_exported_timeline` 同族逻辑）：副轨段在视频导出时不参与，仅 SRT 导出按用户选择；此边界写入 PROJECT_SCHEMA.md

### M11-3: 波形缓存（D3）

- `ffmpeg_service.generate_waveform` 输出 sidecar `<媒体名>.peaks.json`，头带 `{"media_signature": {"size": int, "mtime_ms": int}, "version": 1}`
- 生成前检查 sidecar 签名命中即直接返回缓存数据
- 前端 `resolveWaveformUrl` 优先取 sidecar；后端命中时不建 waveform 任务（`triggerWaveformGeneration` 探测逻辑在 Python 侧）

**测试**: `tests/test_waveform_cache.py`（签名命中/失效/媒体变更后重新生成）；多轨契约测试 `tests/test_tracks_contract.py`（patch 层往返、invariant 不波及副轨、旧工程缺省字段兼容）。

---

## 依赖顺序与发布批次

```
M1 → M2 → M3 (M3-6 等 M5)          3.0.0-beta.1
M5 → M4 → M6 → M7                  3.0.0-beta.2
M8 → M9 → M10                      3.0.0-rc
M11 (依赖 M1/M7)                    3.0.0 正式
```

## 需求追溯矩阵

| PRD | 模块 | PRD | 模块 | PRD | 模块 |
|---|---|---|---|---|---|
| A1 | M1-1 | B1 | M4 | C2 | M8-2 |
| A2 | M1-2 | B2 | M6 | C3 | M9-1/9-2 |
| A3 | M1-3 | B3 | M7-2 | C4 | M10 |
| A4 | M2 | B4 | M5 | C5 | M9-3 |
| A5 | M3 | B5 | M7-1 | D1.1 | M1-4 |
| A6 | M3-6 | C1 | M8-1 | D1.2/1.3 | M11-1 |
| D2 | M11-2 | D3 | M11-3 | | |

## 总验收（与 PRD §6 对齐）

1. `uv run pytest` 全绿（新增 ≥ 25 条：words 保真/持久化/账本/消毒/SSRF/bridge 批量/多轨契约/波形缓存）
2. `cd frontend && bun run test` 全绿（撤销重写/patch 细粒度/虚拟滚动/组件拆分回归）
3. 性能基线（tests/perf 扩展）：1167 段滚动 ≥ 55fps、undo < 5ms、波形生成期无 >50ms 长任务、空闲 IPC < 4/s
4. `uv run ruff check .` 0 问题；`bun run lint` 0/0；`bun run build` 通过
5. 双平台真机回归（WebView2 + WKWebView）：dpr 跨屏、触控板滚轮、首启动竞态、GB18030 SRT、断电恢复演练

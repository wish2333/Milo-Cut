# v3.0.0 SPEC 风险评审与实施指南

> **用途**: 对 `spec-v3.0.0.md` / `PRD-v3.0.0.md` 的破坏性变更风险评估、源码核验修正、实操指导。
> **方法**: 逐项对照 v2.4.0 源码核验 SPEC 的全部高风险假设（核验证据见 §1），修正 SPEC 中与源码不符的 4 处设计，补充实施顺序、bug 规避、风格与鲁棒性要求。
> **结论先行**: **无协议级破坏性变更**（bridge API 信封、事件名、工程文件向后兼容均保持）；最高风险点为 M5（撤销重构）与 M7（虚拟滚动），各有专属规避方案；核验发现 2 个 SPEC 未预见的真实缺陷被顺带修复（task:completed 全量 project 载荷、TranscriptData 构造丢元数据）。

---

## 1. 源码核验结论（修正 SPEC 的事实基础）

| # | 核验项 | 事实（文件:行号） | 对 SPEC 的影响 |
|---|---|---|---|
| 1 | Segment.id 生成 | ASR 脚本自带 `seg_{start:.3f}`（whisper:159 / qwen:365 / mlx:237），**必填无默认**（models.py:71）；parse_srt 生成 `seg-0001` 递增号（subtitle_service.py:52）；前端运行时**零依赖** `seg-` 前缀格式（仅测试 mock 使用） | M1-1 删除回灌后 id 变为 ASR 格式，**无破坏**；但测试夹具需更新 |
| 2 | TranscriptData 构造点 | 全仓仅 3 处构造（project_service.py:605 update_transcript / 886 add_silence_results / 1132 add_segment），**全部只传 segments、丢弃 engine/language**；models.py:303 有 default_factory 路径 | M11 若加 tracks 字段，这 3 处会**静默丢 tracks**——SPEC 已补修正案（§2.4） |
| 3 | pushSnapshot 调用点 | 直接调用 3 处（WorkspacePage.vue:940/1124/1427）；**另注入 useAnalysis/useEdit（L140/159）内部各自调用** | M5/M8 迁移清单必须包含 composables 内部调用，原 SPEC 遗漏 |
| 4 | 事件 payload | task:progress 轻量（task_manager.py:343-349 仅 task_id/percent/message）；**task:completed 的 result 多路径携带全量 project dump**（main.py:183/455/656/794/891/987 共 6 个 handler） | 原 SPEC M4-3 只写了"纪律"，实际是 6 处具体修改点（§2.3） |
| 5 | run_on_bridge 调用方 | **全仓零调用**（bridge.py:166 定义后无人使用；register_handler 亦无 Bridge 侧调用者） | M4 自适应 tick **不受任务超时约束**，设计大幅简化（§2.2）；`_execute_next_task` 为事实死代码，M9-3 顺带清理 |
| 6 | 温度消费 | 四条 LLM 路径共用 `call_llm` 单一 settings 温度（llm_service.py:71→135）；唯一硬编码例外 test_connection=0（:243）；前端滑杆无独立默认；**demo mock 默认 0.2 与后端 0.3 不一致**（demoBridge.ts:55） | M3-5 按路径温度需扩展 LlmConfig 而非仅改默认值（§2.5）；demo 默认值对齐 |
| 7 | Timeline 行高 | TranscriptRow 统一 `min-h-[52px]` 单行 truncate（:251/:312），**无展开/双行模式**；但列表混排两种行组件（TranscriptRow + SilenceRow，Timeline.vue:327/357） | M7-2 虚拟滚动比预估容易（行高统一），但需处理**混合行类型**窗口化 |
| 8 | v-memo 依赖 | v-memo 数组含 `seg` 对象本身（Timeline.vue:328） | 证实 M7-1 的价值：数组整体替换 → 全部行 v-memo 失效；按 id 原位替换 → 未变行引用稳定、v-memo 生效 |
| 9 | import_srt 前端调用方 | 3 个独立入口（useTranscript.ts:6 / WorkspacePage.vue:941 手动导入 / App.vue:207 项目创建） | M1-1 只动 main.py 回灌调用，3 个手动入口行为不变，破坏面收敛 |
| 10 | ProjectPatch 字段 | models.py:401-411 全 8 字段已核；tracks/bindings 层应插在 timeline 内层组（analysis 与 media 之间） | M11 落点确认 |
| 11 | 保存链 | 后端 save_project（project_service.py:440）+ PROJECT_DIRTY 事件 → 前端 watch(isDirty) 2s 防抖（useProject.ts:41-53）+ 手动保存 2 处 | M2 备份逻辑挂 save_project 内部，前端零改动 |
| 12 | bridge 派发目标 | `_flush_events` 用 **`document.dispatchEvent` + `bubbles: true`**（bridge.py:100-104） | 原 SPEC M4-1 草案写的 `window.dispatchEvent` 会脱离现有监听目标，**已修正为 document**（§2.1） |

---

## 2. SPEC 修正案（Errata，已同步回写 spec-v3.0.0.md）

### 2.1 M4-1 派发目标修正

批量投递 helper 必须沿用 `document.dispatchEvent` + `bubbles: true`（与 bridge.ts 现有 `onEvent` 监听目标一致）。修正后 Python 侧：

```python
payload = json.dumps(
    [{"name": f"pywebvue:{e[0]}", "detail": e[1]} for e in batch],
    ensure_ascii=False,
)
self._window.evaluate_js(f"window.__pywebvueDispatchEvents({payload});")
```

```js
// bridge.ts bootstrap 注入
window.__pywebvueDispatchEvents = (events) => {
  for (const ev of events) {
    document.dispatchEvent(
      new CustomEvent(ev.name, { detail: ev.detail, bubbles: true }),
    );
  }
};
```

### 2.2 M4-2 自适应 tick 简化

核验 #5：`run_on_bridge`/`_task_queue` 零调用方，自适应 tick **只需考虑事件延迟**。设计简化为：

- JS 侧 tick 循环：连续 40 次空转 → 间隔 250ms；每次 tick 返回值由 `{"success": True}` 扩展为 `{"success": True, "data": {"pending": <事件队列长度>}}`，JS 据此决定保持快档或降档
- **最坏延迟承诺**：空闲态下首个事件延迟 ≤ 250ms（用户不可感知的事件均为后台完成通知；交互调用走 `call()` 通道不经事件队列，不受影响）
- `_execute_next_task` 与 `_task_queue`/`_pending_results`/`run_on_bridge`/`run_on_main_thread` 移入 M9-3 死代码清理（保留 `register_handler` 名称空间的兼容注释）

### 2.3 M4-3 改为具体修改点（6 个 handler）

task:completed 携带全量 project 的 6 处（main.py:183/455/656/794/891/987）统一改造：

- handler 返回值保留 `"project"` 键（**调用方同步返回值不动**——`call()` 返回不走 evaluate_js，无 IPC 体积问题）
- `task:completed` **事件**的 detail 改为 `{task_id, task_type, result_meta}`（含 `revision`、`layer_names` 等摘要），前端收到事件后经 `get_project`（或新增 `get_project_since(revision)`）拉取
- 兼容期：事件 detail 同时带 `"project_stripped": true` 标记，前端 `useTask.ts` 旧逻辑检测到该标记走拉取路径，否则用旧路径——保证 dev（新前端）与打包 frontend_dist（旧前端）任意组合可跑

### 2.4 M11-2 TranscriptData 构造保护（新增）

核验 #2：`update_transcript`/`add_silence_results`/`add_segment` 三处以 `TranscriptData(segments=...)` 重建，新增 tracks 后会静默丢失。修正：

- 三处一律改为 `transcript.model_copy(update={"segments": ...})`（保留 engine/language/tracks/bindings）
- 新增契约测试：构造带 tracks 的工程 → 跑 update_transcript/add_silence_results/add_segment → tracks 原样保留
- `update_transcript` 签名不动（仍只接收 segments），transcript 级元数据的更新走新增的 `update_transcript_meta`（M11 一并交付，供副轨导入使用）

### 2.5 M3-5 按路径温度（细化）

LlmConfig 增加可选 `temperature_override: float | None`；`run_semantic_search`（及后续纯检索类调用）传 `0.0`；其余路径读 `settings.llm_temperature`（默认 0.3 → 0.1，`core/config.py:62` 同步）。demo mock 默认（demoBridge.ts:55 的 0.2）对齐 0.1，消除三处默认值分叉。

### 2.6 M7-2 混合行类型（补充）

窗口化按 `mergedSegments` 统一序列处理，行组件按 `seg.type` 分派（现有 v-if 逻辑搬到窗口渲染器内部）；SilenceRow 与 TranscriptRow 行高不同时，虚拟滚动采用**分段测高**（每类型注册一个测高探针，序列预计算累积偏移数组，`Array.prototype.findIndex` 之外用二分定位）。行高当前统一（核验 #7），二分为零成本预留。

---

## 3. 破坏性变更与风险矩阵

### 3.1 兼容性承诺（全版本有效）

| 面 | 承诺 | 核验依据 |
|---|---|---|
| bridge API 信封 | 所有 @expose 返回 `{"success", "data", "error"}`，方法名不变（M10 分域仅内部重组） | expose 装饰器契约（bridge.py:21-43） |
| 事件名 | `core/events.py` 与 `frontend/src/utils/events.ts` 同步，本版不删不改既有事件名，只增 `task:completed` detail 字段（追加式） | AGENTS.md 事件契约 |
| 工程文件 | project.json 只增字段（words 本就存在、tracks/bindings 带默认值），旧工程零迁移打开；Pydantic frozen 模型兼容缺省字段 | models.py 默认值策略 |
| settings | 只改默认值（llm_temperature），已保存的 settings.json 用户值优先，不覆盖 | config.py 读取合并逻辑 |
| frontend_dist | bridge 批量投递带运行时探测降级；task:completed 带 `project_stripped` 兼容标记 | §2.1/2.3 |

### 3.2 模块风险评级

| 模块 | 破坏面 | 风险 | 主要 bug 向量 | 规避（详见 §4） |
|---|---|---|---|---|
| M1 词级保真 | 低（id 格式变化无消费方） | 低 | 测试夹具依赖 `seg-` 格式；split 词对齐错位 | 更新夹具；宁可缺失不可错位 |
| M2 持久化 | 低（save 内部） | 低 | fsync 在网络盘/Windows 句柄语义差异；bak 占用磁盘 | try/except 包裹 fsync 与备份，失败仅告警不阻断保存 |
| M3 LLM 协议 | 中（温度默认变化影响输出风格） | 中 | SSRF 校验误伤 Ollama 用户；消毒误剥合法内容 | preset 自动放行 + 消毒仅在四层解析全失败后作为第 5 层兜底 |
| M4 bridge | 中（协议双端） | 中高 | 新后端+旧前端、事件顺序保证、大 payload 拆批 | 运行时探测降级 + 单批保序 + 512KB 拆批；macOS 首启动回归 |
| M5 撤销 | 高（交互核心路径） | **最高** | undo 后 revision 回退/前进语义错、跨层原子性、composables 内部 pushSnapshot 遗漏 | 后端 apply_undo 单一入口 + 迁移清单（§4.2）+ 协议一致性测试先行 |
| M6 波形 | 低（组件内部） | 低 | dpr 探测在 WKWebView 跨屏；hover 预览与拖拽手势冲突 | pointer-capture 判定 + 预览层 pointer-events:none |
| M7 列表 | 高（渲染核心路径） | 高 | 虚拟行上的多选拖拽/右键/键盘导航；patch 原位替换破坏排序假设 | 后端已保证有序（sort invariant），前端替换算法断言"结果与后端数组 id 序列一致"否则回退全量替换 |
| M8 拆分 | 中（大面积搬移） | 中 | undo 调用点遗漏、provide/inject 循环依赖、事件时序 | 搬移清单 diff 核对 + 每步全量测试 + 拆一个发一个内部提交 |
| M9 契约 | 低-中（样式类替换） | 低 | Teleport 后 popover 定位锚点（相对触发器定位需 getBoundingClientRect 快照） | 定位快照 + 上翻双测规则 |
| M10 分域 | 低（纯搬移） | 低 | 循环导入（correction_service ↔ project_service） | 单向依赖：correction → project；main.py 组装 |
| M11 多轨/缓存 | 中（模型扩展） | 中 | §2.4 构造丢 tracks；导出侧副轨残留；缓存签名误命中（mtime 精度） | 契约测试 + mtime_ms + size 双因子 + 导出边界写入 schema 文档 |

### 3.3 明确的非破坏项（易被误判）

- 删除 SRT 回灌：手动 import_srt 三入口（核验 #9）不受影响
- 温度默认值改动：已保存设置的用户无感（settings.json 优先）
- undo 上限 50→100：纯前端内存策略，无协议影响
- 删除 `run_on_bridge` 死代码：零调用方（核验 #5）

---

## 4. 实操指导

### 4.1 全局实施顺序（批次内亦按此依赖排序）

```
M1(词级) ─┐
M2(持久化) ├─ 无相互依赖，可并行，各自独立提交
M3(LLM)  ─┘   M3-6(回滚) 挂起等待 M5

M5(撤销) → M4(bridge) → M7(patch细粒度 → 虚拟滚动) → M6(波形)
     ↑ M5 先行因 A6 与 M8 迁移都依赖其基建

M8-1(SettingsModal) → M8-2(WorkspacePage 三步) → M9(契约/lint) → M10(分域)

M11 最后：依赖 M1(words)、M7(渲染)、M10(correction_service 已就位)
```

**每个模块一个 PR**，两段式提交信息（AGENTS.md 规范），禁止跨模块混合提交（回滚粒度）。

### 4.2 迁移清单模式（M5/M8 共用的防遗漏手段）

以 M5 为例，落地前先固化清单（存入 `docs/3.0.0/migration-M5.md`，随 PR 勾销）：

1. `pushSnapshot` 全部调用点：WorkspacePage.vue:940/1124/1427 + useAnalysis 内部 + useEdit 内部 + useSegmentEdit(如有)——**逐点标注替换后的层组合**（如 split → `[segments, edits]`）
2. 每替换一点，跑 `useUndoRedo.test.ts` + 对应操作的手动 undo/redo
3. 全部替换完成后，全局 grep `pushSnapshot` 确认无残留旧签名调用
4. 删除旧 JSON 快照路径前的最后一个提交打 tag `pre-undo-cleanup`，作为回归锚点

### 4.3 Bug 规避守则（按模块高风险点）

**通用**：
- 所有新后端方法经 `@expose` 返回信封；所有新事件双端同步登记（events.py + events.ts 同一提交）
- Pydantic frozen 模型改动只增字段带默认值；`model_copy(update=)` 替代重建构造（§2.4 教训）
- 每个破坏面改动配"运行时探测降级"（M4 的 `typeof` 探测、M7 的全量替换回退），降级路径必须有测试覆盖

**M1**: `split_words` 对齐失败必须返回双空列表（宁可缺失不可错位），禁止"部分词近似分配"
**M3**: SSRF 校验放行规则先于拦截规则执行（ollama preset → allow_local_urls 自动 true）；消毒函数只做剥离不做内容改写
**M5**: `apply_undo` 后端实现必须：校验请求层快照结构 → 替换层 → revision+1 → 返回 ProjectPatch（复用 `_success_patch`）；拒绝任何 revision 回退请求。前端 undo 后**不得**再对同一 revision 发起写操作（stale patch 会拦截，但要保证 UI 不卡死——stale 时刷新全量 project）
**M6**: rAF 回调内不得读取响应式状态（避免再触发调度循环）；dpr 监听用 `matchMedia` 而非 ResizeObserver
**M7**: 原位替换算法的守门断言——新数组 id 集合与顺序 == 后端 patch.segments 的 id 序列，不一致即回退整体替换并 `console.warn`（宁可慢，不可错序）
**M8**: 一次只搬一个职责；搬移前后 `git diff` 只应出现"删除+新增"无逻辑修改；全局 keydown 迁移后必须手测文本输入框内 Delete/方向键不被全局拦截
**M11**: 副轨段 id 必须与主轨 id 命名空间隔离（`track_{trackId}_seg_{start:.3f}`），防止 merge/决策系统误匹配

### 4.4 风格一致性要求

- **Python**: `uv run` 执行；类型注解 + docstring（现有风格）；新文件过 `ruff check`；无 emoji；日志走 loguru `logger`
- **前端**: `bun run`；组件文件 < 400 行（超出即拆，M8 的验收即体现此标准）；`@/` 别名导入；composable 用 `use*` 命名；CSS 优先语义 token（M9 之后禁原始灰阶类）
- **测试**: 后端 pytest 放 `tests/test_*.py`（本版新增 ≥25 条已列入 SPEC 总验收）；前端 vitest 与组件同目录 `.test.ts`；每个降级/回退路径至少 1 条测试
- **提交**: 两段式 `type(module): 摘要` + `-` 列表；一个 PR 一个模块；PR 描述附迁移清单勾销状态

### 4.5 鲁棒性基线（每个模块交付前自查）

1. 失败路径全部有出口：任何 try 块的 except 不吞错（至少 logger.warning + 用户可见降级）
2. 数据不变量测试先行：动 `_enforce_segment_sort_invariant` 相关代码前，先跑 `test_segment_sort_invariant.py` 全绿再开工
3. 双平台冒烟：每批次合并前 Windows（WebView2）+ macOS（WKWebView）各跑一轮核心路径（导入→转写(mock)→静音→编辑→undo→导出）
4. 性能护栏：tests/perf 基线脚本纳入 CI（beta.2 起），回归超 20% 阻断合并
5. 文档同步：`docs/3.0.0/record-*.md` 随模块记录实际改动（对齐仓库 record 惯例）；PROJECT_SCHEMA.md 与模型改动同一 PR 更新

### 4.6 回滚预案

- 每个 PR 独立可 revert（模块化提交的直接收益）
- M4 上线后若批量投递出问题：`evaluate_js` 探测降级路径仍在，可热修回单事件模式（保留双路径一个版本周期后再删）
- M5 上线后撤销异常：后端 `apply_undo` 与旧全量路径并存一个版本（feature flag `undo.v2`），异常时前端回退旧快照栈
- M2 备份机制不可能需要回滚（纯增益，失败仅告警）

---

## 5. 核验与修正后的文档状态

- 本文档：风险评审 + 实施指南（新增）
- `spec-v3.0.0.md`：已按 §2.1-2.6 回写修正（M4-1 派发目标、M4-2 tick 简化、M4-3 六处 handler 清单、M11-2 构造保护、M3-5 温度细化、M7-2 混合行类型）
- `PRD-v3.0.0.md`：无需修改（需求面未受核验影响；A6/M5 依赖关系原表述正确）

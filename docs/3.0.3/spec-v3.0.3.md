# v3.0.3 实施规格说明（SPEC）

> 版本：3.0.3（SPEC Draft —— 随 PRD 定稿节奏走）
> 上游：[PRD-v3.0.3](./PRD-v3.0.3.md) / [3.0.2 遗留登记](../3.0.2/record-3.0.2.md) / [3.0.2 smoke-fix-1](../3.0.2/record-3.0.2-smoke-fix-1.md)
> 基线：`dev-3.0.2` HEAD = d441bda（行号引用以撰写时为准）
> 本文职责：把 PRD 的 3 个特性（S1-S3）细化为**输入 / 输出 / 边界 / 验收**四段齐全的可实施契约。所有"裁决"栏为本 spec 在实施层做出的唯一性决定，与 PRD 冲突时以本文为准并需回写 PRD。

---

## 概要

### 模块划分

| 模块 | 内容 | 对应 PRD | 批次 |
|---|---|---|---|
| M0 | 全局契约：红线、数据契约现状、协议不变量 | 全部前置 | 全程 |
| M1 | 列表轨感知：选择器 / 副轨渲染 / 文本与时间编辑 / 行操作与撤销谓词 | S1 | P1 |
| M2 | 跟随平滑动画调度器 | S2 | P2 |
| M3 | 列表行右键菜单 kbd 角标 | S3 | P2 |
| M4 | 测试与门禁：用例矩阵、零后端改动断言、真机清单 | 全部 | 全程 |

### M0: 全局契约

#### M0-1: 红线（任何模块不得违反）

1. **后端零改动**——`core/models.py` / `core/project_service.py` / `main.py` / `core/events.py` 本版零 diff；`git diff` 四文件为空是每步硬门禁。S1 全部走既有 expose：`update_track_segment`（allowed_fields = start/end/text，project_service.py:1382）/ `delete_track_segment` / `add_track_segment` / `delete_track` / `clear_track_segments`。
2. **零新增 bridge 事件**——`core/events.py` 与 `frontend/src/utils/events.ts` 零改动。
3. **主轨列表零行为变化**——track 选择器缺省 = 主轨；主轨数据通路（`mergedSegments` → Timeline.vue 渲染、`handleListSeek`、主轨行编辑链）为 `activeListTrackId == null` 分支且断言与 v3.0.2 逐字节一致；既有 666 前端测试不改断言全绿是硬门禁。
4. **视图态不入数据层**——`activeListTrackId` 不产生 patch、不入 undo、不持久化（会话内 reactive）；与 3.0.2 `milocut:timeline-rows:v1` 平行的新 localStorage key 仅 S2 一个（`milocut:timeline-follow-smooth:v1`）。
5. **多行时间线零回退**——本版不触碰 `useRowLayout` 行映射内核与行虚拟化契约；S2 只替换 scrollTop **写入方式**（瞬时 → 可选动画），行几何/回环分类既有函数语义不变（仅扩展）。
6. **撤销捕获层谓词表唯一真源**（PRD R1.5 表）——text 恒 `["tracks"]`；start/end 按绑定谓词；删除恒 `["tracks","bindings"]`。实现查询用既有 `activeBindings`，不新增数据通道。
7. **常量单一真源**——smooth 时长/缓动常量从 S2 调度器模块导出；防抖 300ms 沿用 useTrackEdit 既有常量。

#### M0-2: 数据契约现状（实施前提，勿改）

- 副轨段模型：`track.segments[]`，字段 id / start / end / text；id 生成于创建时（`track_{track_id}_seg_{start:.3f}`）且**不可写**（update_track_segment 显式拒绝 id）。
- bindings：`main_segment_id` ↔ `extension_segment_id` + offsets；时间变更后 offsets 由后端整体重建（`rebuild_binding_offsets`），前端经 patch `bindings` 层接收。
- useTrackEdit 现状：乐观更新 + 300ms 防抖合并（key `trackId:segmentId:field`）+ 失败回滚 + 捕获层（波形 trim 路径）；**本版扩展点 = 列表文本/时间编辑复用同一 composable**（新增列表侧入口，防抖合并天然按 field 隔离）。
- 撤销：五层快照 pushSnapshot 在补丁应用前捕获（现状模式）；列表编辑走同一 `applyProjectPatch` 通路。
- 跟随回环现状：`markManualScroll` / `isFollowCoolingDown` / `noteAutoScroll` / `consumeAutoScroll`（useRowLayout，3.0.2 交付）——S2 的抑制判定扩展点。

#### M0-3: 交付顺序强制

```
P1: M1（R1.1 选择器 → R1.2 渲染 → R1.3/R1.4 编辑 → R1.5 行操作与撤销，顺序强制：先显示后编辑）
P2: M2 → M3（先调度器后角标；互不依赖，可并行开发但合入按此序）
P3: M4 终检 + 文档 + 真机清单
```

---

## M1: 列表轨感知（P1 / S1）

### M1-1: track 选择器（R1.1）

**改动**：`WorkspacePage.vue` 增 `activeListTrackId = ref<string | null>(null)`（null = 主轨）；`Timeline.vue` 增 props `tracks`（名称+段数）与 `activeTrackId`，头部渲染 segmented 切换（样式沿 3.0.2 控件栏 segmented 既有款）。

**边界**：
- 列表数据源单一 computed：`activeTrackId == null ? mergedSegments : activeTrack.segments`——**不新建第二套行渲染**，行组件按数据源多态；
- `delete_track` 成功后若 `activeListTrackId` 指向被删轨 → 置 null（watch 兜底）；
- 选择器切换不清空选中段集合（主轨选中集与副轨查看态正交；跨轨选中集本版不做——选中态仍仅主轨语义）。

**验收**：往返切换无残留；删当前轨自动回退主轨；主轨分支渲染 diff 为零（既有 Timeline 测试不改全绿）。

### M1-2: 副轨段渲染（R1.2）

**改动**：列表行组件副轨分支：text / `formatTime(start)` / 时长；`bindings` 中 `extension_segment_id` 命中时渲染联动标记（icon-only，title 提示主轨联动）；空轨渲染空态卡（说明 + 「新建字幕」按钮 → `add_track_segment(trackId, at=当前播放时间)`，沿波形建段同一 expose 与 toast）。

**边界**：副轨行不做多选/框选（本版范围外）；行高与主轨行同款（不引入第二套行样式）。

**验收**：双语工程副轨段全量正确显示；绑定标记与波形区一致；空轨建段后列表即时出现（patch tracks 层回填）。

### M1-3: 文本与时间编辑（R1.3/R1.4）

**改动**：useTrackEdit 增列表侧入口（`editTrackSegmentText(trackId, segId, text)` / `editTrackSegmentTime(trackId, segId, field, value)`）——乐观更新 + 300ms 防抖合并 + 失败回滚复用既有内核；时间编辑提交前本地预校验（min duration / 上界），后端拒绝（重叠）即回滚 + toast 错误原文。

**边界**：
- 防抖 key `trackId:segmentId:field` 与波形侧天然合并——同一字段列表与波形交替编辑不产生竞态（后到者覆盖，回滚以最后一次快照为准）；
- 文本编辑不走 clamp/重叠校验（后端 text 路径无几何语义）；
- 编辑中切换轨/切换主轨视图：未决防抖提交先 flush 再切换（沿 `flushScrollTopSave` 同模式）。

**验收**：防抖合并（同段同字段 3 次输入 1 次提交）；后端拒绝回滚 + toast；undo 后列表与波形一致；flush-on-switch 无丢字。

### M1-4: 行操作、定位与撤销谓词（R1.4/R1.5）

**改动**：副轨行单击 → `handleListSeek(start)`（既有通路复用）；右键菜单：定位 / 编辑 / 删除此条字幕（`delete_track_segment`，无确认框，撤销覆盖——沿 3.0.2 裁决）；播放跟随高亮当前副轨段（时间命中判定，与主轨列表同款）。

**捕获层实现表（M0-1.6 展开）**：

| 调用点 | 谓词实现 | 捕获层 |
|---|---|---|
| 列表 text 提交 | 恒真 | `["tracks"]` |
| 列表 start/end 提交 | `activeBindings.some(b => b.extension_segment_id === segId)` | 命中：`["tracks","bindings"]`；未命中：`["tracks"]` |
| 删除此条字幕 | 恒真 | `["tracks","bindings"]` |

**验收**：四行谓词表逐行 vitest（undo 后三层一致性断言，绑定段时间编辑回退含 offsets 还原）；undo/redo 对称。

---

## M2: 跟随平滑动画调度器（P2 / S2）

### M2-1: 调度器契约

**改动**：新纯逻辑模块 `frontend/src/composables/useScrollAnimator.ts`（单例 per WaveformEditor 实例；禁止 import 组件/bridge）：`animateTo(target, {durationMs})`（默认 140ms ease-out）、`redirect(target)`（动画中重定向 = 从当前值续跑新目标，不叠加）、`cancel()`；WaveformEditor 的 `writeScrollTop` 调用点改为经调度器（瞬时路径 = `durationMs: 0` 直通）。

**回环抑制（R2.2）**：
- 手动滚轮/滚动事件 → `cancel()` 后再走既有 `markManualScroll`（手动优先级最高）；
- 播放时钟回调（`PLAYBACK_CLOCK_KEY` 消费路径）期间**不启动**新动画（守卫旗标）——3.0.2 空白嫌疑的直接防御；
- 动画每帧经既有 `writeScrollTop` 通道写入（echo 分类/持久化通路不变，仅写入节奏变化）。

**设置开关（R2.3）**：localStorage `milocut:timeline-follow-smooth:v1`；读取容错（损坏 JSON / 非法值 → 默认）；**默认值 = `false`（瞬时）**，beta.1 真机 A/B 后由用户裁决改默认并回写本 spec。

**常量**：`FOLLOW_SMOOTH_DURATION_MS = 140`、`FOLLOW_SMOOTH_EASING = "easeOutCubic"`（模块导出）。

**验收**：vitest 四组——手动滚动打断、卸载清理（无泄漏 rAF）、重定向不叠加（同帧单写）、播放回调期禁启动；真机 A/B 记录进 beta.1 record。

---

## M3: 列表行右键菜单 kbd 角标（P2 / S3）

**改动**：列表行右键菜单项配置结构增可选 `kbd?: string` 字段；渲染层消费（mono 角标，款式样复用 3.0.2 R9.4 既有 CSS）；主轨行既有菜单项 + 副轨行三项（定位/编辑/删除）按快捷键登记表标注；无 `kbd` 项不渲染角标节点（不留空壳）。

**边界**：本项只改列表行菜单——波形行/块菜单（3.0.2 已带角标）零改动；菜单项动作语义零变化（纯展示层）。

**验收**：主/副轨行菜单角标正确；无快捷键项无空角标；菜单快照测试更新。

---

## M4: 测试与门禁

### 用例矩阵（新增下限）

| 组 | 用例 |
|---|---|
| 选择器 | 往返切换、删轨回退、主轨分支零 diff、空态建段 |
| 副轨渲染 | 字段显示、绑定标记、空轨 |
| 编辑 | 文本防抖合并/回滚、时间预校验、后端拒绝回滚+toast、flush-on-switch |
| 撤销谓词 | 四行表逐行（含 offsets 还原）、redo 对称 |
| 调度器 | 打断/清理/重定向/播放期禁启动/开关容错 |
| 角标 | 标注正确、空角标缺失、快照更新 |

### 门禁命令（每步合入前全绿）

```bash
uv run pytest                              # ≥716 全绿（后端零改动，数字只增不减）
cd frontend && bun run test                # ≥666 全绿且新增全绿
cd frontend && bun run build               # vue-tsc + vite build
cd frontend && bun run lint                # eslint 0 errors 0 warnings
uv run ruff check .                        # 0 问题（本步触及文件）
git diff core/events.py frontend/src/utils/events.ts core/models.py main.py core/project_service.py   # 必须为空
```

### 真机清单（P3，双平台）

- 列表副轨编辑全链路：切换 → 文本改 → 时间改（含越界/重叠拒绝）→ 删除 → undo/redo 全程对照波形区
- smooth A/B：回放跟随 + 手动滚动混合操作各 3 分钟，空白/跳变观察（beta.1 前置项）
- kbd 角标显示；多行模式下列表联动（seek → 行锚定）回归

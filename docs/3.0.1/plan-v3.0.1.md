# Milo-Cut v3.0.1 实施计划（PLAN）

> **版本**: 3.0.1
> **基准**: v3.0.0 工作树（内部里程碑版，不独立发布）
> **分支**: `dev-3.0.1`（每模块独立短分支 `dev-3.0.1/<step-id>` 合入）
> **依据**: [PRD](./PRD-v3.0.1.md) · [SPEC](./spec-v3.0.1.md)（含实施层裁决，已定稿）· [堆叠时间线分析](./spec-v3.0.1-堆叠时间线分析.md)
> **计划文档**: `docs/3.0.1/plan-v3.0.1.md`（每完成一步勾销并回填实际结果，对齐仓库"边做边落盘"惯例）

---

## 0. 全局约定（适用每一步）

### 验收基线（每步合入前必须全绿）

```bash
uv run pytest                              # 后端全量 + 本步新增测试
cd frontend && bun run test                # 前端全量 + 本步新增测试
cd frontend && bun run build               # vue-tsc + vite build
uv run ruff check .                        # 本步触及文件 0 问题
```

追加门禁（按步骤触发）：

- Phase 3 起追加：`projectPatch.perf` 断言（M3 门禁，失败即冻结后续步骤）
- Phase 4 追加：`git diff core/events.py frontend/src/utils/events.ts` 为空（SPEC 红线 M0-3.3）

### 提交与记录

- 一步一短分支一合入；两段式提交（`type(module): 摘要` + `-` 列表，不带版本号）
- 每步完成即勾销本文件 + 写 `docs/3.0.1/record-3.0.1-<step-id>.md`（改动文件清单、验证命令与实际输出、未验证边界）
- 验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注"可并行"的步骤）

### 批次顺序强制（SPEC 交付顺序，不得调换）

```
P0 批次: 约束内核先行（纯函数 + 重叠拒绝同批，防拖拽回跳）
P1 批次: 只读几何化（lane 拖拽只 emit 不提交）
P2 批次: M5-1 -> M3 接线 -> M2-1 联动 -> M2-2 -> M2-3 -> M5-2/3（顺序强制）
P3 批次: 导出 -> overlay -> 文档
```

### 需要用户协助的事项（汇总，各步内不再重复标注 ★）

| 节点 | 请求内容 |
|---|---|
| P0-1 | 确认计划启动、基线数字无异议 |
| P1-1 | 提供副轨测试素材：一份中文主轨视频 + 一份时间轴大致对齐（300ms 容差内）的外语 SRT；另备一份故意错位的 SRT（用于 unbound/消解路径） |
| Phase 2 / 3 末 | beta 冒烟：macOS 侧由本机完成，Windows WebView2 侧需你跑一轮冒烟清单（§5） |
| P4-5 | 双平台全量真机回归签字（手感验收：拖拽/trim/联动跟随主观体验） |

---

## Phase 0: 开工准备（0.5 天）

### P0-1 分支与基线快照

- [x] 从当前基线拉 `dev-3.0.1`；记录基线：pytest 用例数、vitest 用例数、`tests/perf` 输出存档 `docs/3.0.1/perf-baseline.md` ✅ 2026-08-31（pytest 598 / vitest 343，见 record-3.0.1-P0-1）
- [x] 打 tag `v3.0.1-base`（全局回滚锚点）✅ 2026-08-31
- [ ] ★ 通知用户计划启动；确认副轨测试素材就位时间（已通知；素材不阻塞 Phase 1，合成 SRT 降级方案见 §6）

**验收方式**: `git tag` 存在；perf 基线文件含项目打开、波形生成、undo 三项当前耗时。
**验收标准**: 基线可复现（连跑两次误差 <10%）。

---

## Phase 1: 约束内核（P0 批次，~1 天，无 UI）

### P1-1 前端约束函数族 `trackConstraints.ts`（SPEC M1 全部）

- [x] 新建 `frontend/src/utils/trackConstraints.ts`：`MIN_SEGMENT_DURATION`/`SNAP_STEP` 常量 + M1-1 邻居与主轨约束（`getTrackNeighborBounds`/`constrainCueRangeToTrack`）+ M1-2 副轨约束（`clampExtensionRange`/`extensionRangeOverlapsNeighbors`）+ M1-3 联动四件（`reconcileExtensionTrack`/`syncBoundExtensionForMain`/`rebuildBindingOffsets`）+ M1-4 `constrainBoundExtensionPanelEdit` ✅ 2026-08-31
- [x] `SegmentBlocksLayer.vue` 改 import 共享常量，删除本地 `MIN_SEGMENT_DURATION` 与 `snapToFrame` 硬编码（行为零变化）✅ 2026-08-31
- [x] 新建 `trackConstraints.test.ts`：逐函数边界用例表（空轨/首尾段/缝隙恰等于 min/缝隙不足/多选豁免/reconcile 四规则+counters/offset round3/NaN 抛错）+ 模块纯性测试（import 列表无 vue/bridge）✅ 2026-08-31（54 用例；SPEC 勘误两条，见 record-3.0.1-P1-1）

**验收方式**: `bun run test`（新用例全绿）；grep 确认 SegmentBlocksLayer 无本地常量残留。
**验收标准**: 用例表全项覆盖；SegmentBlocksLayer 现有测试零改动全绿。

### P1-2 后端镜像 `core/track_constraints.py`（可并行）

- [x] Python 镜像实现：`reconcile_extension_track` / `sync_bound_extension_for_main` / `rebuild_binding_offsets` / `clamp_extension_range` / `overlaps_neighbors`（语义与 M1 逐条对齐）✅ 2026-09-01
- [x] 新建 `tests/test_track_constraints.py`：**复用 P1-1 同一组边界用例表**双侧锚定（含常量数值一致断言）✅ 2026-09-01（53 用例；发现并消解 Python banker's rounding 与 JS Math.round 的 tie 差异，见 record-3.0.1-P1-2）

**验收方式**: `uv run pytest tests/test_track_constraints.py`。
**验收标准**: 与前端用例表一一对应，双侧全绿；`ruff check` 0 问题。

### P1-3 `update_segment` 重叠拒绝 + 前端最小接线（SPEC M2-1 第 1-3 步，联动第 4 步不激活）

- [ ] `update_segment`：副轨命名空间 id 拒绝引导；同轨重叠校验（排除自身、epsilon 贴合放行），拒绝信息含冲突段 id
- [ ] **同 PR 内**最小接线 `SegmentBlocksLayer` trim 提交路径：clampTime 前置 `constrainCueRangeToTrack`，blocked 时本次拖动拒动（红线：两半分批合入会出现拖拽回跳）
- [ ] 新建 `tests/test_track_linkage.py`（本步只写拒绝路径用例：前邻/后邻/双侧夹击/贴合放行/副轨 id 引导）

**验收方式**: `uv run pytest tests/test_track_linkage.py` + `bun run test`（SegmentBlocksLayer 全绿）。
**验收标准**: 手工冒烟——主轨拖拽挤压邻居时被缝内平移或拒动，永不产生视觉重叠；防抖提交无回跳。

### P1-4 patch merge 函数先行入库（SPEC M3 前半，无消费者）

- [ ] `projectPatch.ts` 新增 `mergeTracksInPlace` / `mergeBindingsInPlace`（含 id 序列 gate assertion）；`ProjectPatch.ts` 类型补 `meta?: Record<string, unknown> | null`
- [ ] `projectPatch.test.ts` 扩展：引用恒等 `toBe` 断言 + gate 回退用例
- [ ] 新建 `projectPatch.perf.test.ts`：1000 主段 + 4x200 副段规模 apply 耗时断言（p50 < 5ms）+ 单遍扫描结构断言

**验收方式**: `bun run test`。
**验收标准**: perf 断言通过（此测试自 Phase 3 起为合入门禁）；`applyProjectPatch` 本步不接线（tracks/bindings 仍整体替换，Phase 3 激活）。

**Phase 1 退出检查**: 四步全合入；`uv run pytest` 与 `bun run test` 全量绿；本批不发布（无 UI），合入 `dev-3.0.1` 即可。

---

## Phase 2: 堆叠渲染（P1 批次，~1 周）→ `v3.0.1-beta.1`

### P2-1 `useLaneLayout` + 布局持久化（SPEC M4-1）

- [ ] 新建 `useLaneLayout.ts`：`computeLaneLayout` 纯函数（主轨下限 96px 挤压规则、lane 最小 24px）+ `LaneHeightPreset`（32/48/72）+ localStorage `milocut:timeline-layout:v1` 读写（损坏 JSON 回退默认）
- [ ] 新建 `useLaneLayout.test.ts`：0/1/4 轨、全折叠、下限挤压、损坏回退

**验收方式**: `bun run test`。
**验收标准**: 全绿；布局状态不入 undo 栈、不产生 patch（代码评审项）。

### P2-2 `SegmentBlock` 泛化抽取（SPEC M4-3，纯重构锚定）

- [ ] 新建 `components/waveform/SegmentBlock.vue`（渲染 + trim 交互参数化，`trackKind: "main" | "extension"`）
- [ ] `SegmentBlocksLayer.vue` 改为组合 SegmentBlock 的主轨容器（**现有测试断言零改动全绿**）
- [ ] 新建 `SegmentBlock.test.ts`（含 Alt 键 stub：M4-5 只留接口，本步不实现语义）

**验收方式**: `bun run test`（SegmentBlocksLayer.test.ts 不改断言全绿）。
**验收标准**: 纯重构——主轨渲染与交互行为逐像素等价（测试锚定）。

### P2-3 TrackLane 几何化重写（SPEC M4-2）

- [ ] `Timeline.vue:611` 摘除 TrackLane（虚拟列表恢复原状）；重写 `TrackLane.vue`：inject metrics、percent 定位渲染 SegmentBlock（`trackKind="extension"`）、视口裁剪、折叠/显隐/高度档位控件、轨道徽标、>4 轨提示
- [ ] 拖拽/trim/split **只 emit 不提交**（本批无编辑面，Phase 3 激活）
- [ ] `TrackLane.test.ts` 重写：percent 定位、折叠/显隐 emits、>4 提示；删除旧文本列表用例

**验收方式**: `bun run test` + `bun run build`。
**验收标准**: 副轨段块与主轨同缩放目视对齐；Timeline.vue 列表行为无回退（虚拟滚动测试全绿）。

### P2-4 WaveformEditor 堆叠编排（SPEC M4-4）

- [ ] 外层 flex-col：主轨区（既有 z0-z10 层）+ lane 区；`containerRef` 指向整个堆叠容器（getTimeFromX 全区生效）
- [ ] `PlayheadOverlay` 提升为堆叠容器直属子节点，`inset-y-0` 贯穿全部 lane，z=10 不变
- [ ] lane 区 wheel 缩放/平移生效；`createRafScheduler` 接入 lane 指针采样节流；**不引入 lane canvas**（核验修正裁决）
- [ ] `WaveformEditor.test.ts` 扩展：lane 数渲染、播放头单节点贯穿、lane 区 wheel

**验收方式**: `bun run test`；本机跑 `docs/3.0.1/perf-baseline.md` 各项对照。
**验收标准**: 4 副轨 + 千段主轨下缩放/平移/播放帧率不回退；播放头在全部 lane 同步贯穿。

### P2-5 Alt 语义接线（SPEC M4-5）

- [ ] SegmentBlock 指针处理层读 `e.altKey`：吸附临时反转 + 副轨拖动跳过联动跟随回调（提交侧 Phase 3 才存在，本步只断言回调参数）
- [ ] `SegmentBlock.test.ts` 补 altKey 用例

**验收方式**: `bun run test`。
**验收标准**: Alt 按下拖动自由定位，松开恢复吸附。

### P2-6 beta.1 冒烟与发布

- [ ] macOS 本机冒烟：SRT 副轨导入 -> 堆叠显示 -> 折叠/高度/显隐 -> 缩放平移 -> 播放头贯穿
- [ ] ★ Windows WebView2 冒烟同一清单；wheel deltaMode 重点观察
- [ ] 打 tag `v3.0.1-beta.1`；`record-3.0.1-beta.1.md` 汇总

**验收标准**: 冒烟清单全过、无体验回退；两份 record 落盘。

---

## Phase 3: 副轨编辑与绑定联动（P2 批次，~1.5 周）→ `v3.0.1-beta.2`

> 本 Phase 步骤顺序强制（SPEC 交付顺序）：撤销层 -> merge 接线 -> 联动 -> 独立编辑 -> 成对删除/拆分 -> composable/集成。前置依赖倒置会同时踩性能与原子性两个最高风险。

### P3-1 撤销层扩展（SPEC M5-1，前后端同 PR）

- [ ] `undoRecords.ts`：`UndoLayer` + `"tracks" | "bindings"`；`captureLayers` 补两层浅拷贝
- [ ] `project_service.py`：`_UNDO_LAYERS` 扩展；`apply_undo` 对新层 `model_validate`、全量 validate 通过后整体替换（原子语义不变）、`base_revision` 校验不变
- [ ] `useUndoRedo.test.ts` 扩展：新层捕获与回放

**验收方式**: `uv run pytest` + `bun run test`。
**验收标准**: 六层 undo 通道全通；apply_undo 对非法 tracks payload 原子拒绝（部分层不落库）。

### P3-2 merge 接线激活（SPEC M3 后半）

- [ ] `applyProjectPatch` 的 tracks/bindings 层切换为 `mergeTracksInPlace`/`mergeBindingsInPlace`
- [ ] 跑 `projectPatch.perf.test.ts` —— **自此为合入门禁**

**验收方式**: `bun run test`（perf 断言）。
**验收标准**: 单副段 patch 后未变引用恒等；断言不过则冻结本 Phase 后续步骤。

### P3-3 `update_segment` 联动激活（SPEC M2-1 第 4 步）

- [ ] `core/track_constraints.py` 的 sync/reconcile/rebuild 接入 update_segment（按 SPEC 算法 5 步）；`meta.linkage = {squeezed, removed, unbound}`
- [ ] `tests/test_track_linkage.py` 补联动用例：move 整体平移/trim 单边跟随/reconcile 三计数/offset 重建/无绑定路径 patch 不带 tracks/bindings 层
- [ ] 前端 toast 消费 `meta.linkage`（R7.5 计数提示，破坏性消解绝不静默）

**验收方式**: `uv run pytest tests/test_track_linkage.py` + 手工冒烟（拖主轨看副段跟随）。
**验收标准**: 红线 M0-3.1 机器锚定——联动路径断言主轨 segments 引用与值均不变。

### P3-4 `update_track_segment` expose（SPEC M2-2）

- [ ] main.py + project_service：六步校验链、offsets 派生重建、绝不反向改主轨、`meta.linkage = {rebuilt}`
- [ ] `tests/test_track_linkage.py` 补：校验链六条各一例 + 主轨零变更断言

**验收方式**: `uv run pytest`。
**验收标准**: 全绿；错误信息含 track_id / 冲突段 id。

### P3-5 成对删除 + 联动拆分（SPEC M2-3）

- [ ] `delete_segment`：命中 bindings 成对删副段 + 解绑，返回三层 patch
- [ ] `split_segment`：共用绝对切点（cut_ext = position + start_offset）；可拆 -> 副段同步拆 + 双 binding 重挂（offsets 全部 rebuild）；越界 -> 按重叠更大侧重挂 / 双侧皆不可 -> 解绑 + unbound 计数
- [ ] `tests/test_track_linkage.py` 补：可拆/重挂前侧/重挂后侧/解绑四路径

**验收方式**: `uv run pytest`。
**验收标准**: 四路径全绿；新段 id 规则符合命名空间契约（M0-2）。

### P3-6 `useTrackEdit.ts` + 编辑面激活（SPEC M5-2）

- [ ] 新建 `useTrackEdit.ts`：选区、`updateTrackSegmentTime`（乐观更新 + 300ms 防抖键 `${trackId}:${segmentId}:${field}` + 失败回滚）、`flushPendingUpdates`
- [ ] TrackLane/SegmentBlock（extension）编辑回调接线到 useTrackEdit；按 M5-1 映射表执行捕获层（含"提交时是否有绑定"判定）
- [ ] `useTrackEdit.test.ts`：乐观/防抖合并/回滚/捕获层

**验收方式**: `bun run test` + 手工冒烟（副轨拖拽、trim、undo 跟手）。
**验收标准**: 副轨拖拽 patch 流量为被改段（非全轨）；失败回滚与主轨行为一致。

### P3-7 原子性集成测试（SPEC M5-3）

- [ ] `useUndoRedo.test.ts` 扩展：联动拆分 -> 单条 undo 三层同回退 -> redo 对称 -> revision 全程单调；布局变更不入栈断言

**验收方式**: `bun run test`。
**验收标准**: 全绿；apply_undo 路径不触发 reconcile（mock 断言）。

### P3-8 beta.2 冒烟与发布

- [ ] macOS + ★ Windows 冒烟：联动跟随 / 成对删除 / 联动拆分 / Alt 独立拖动 / undo 三层回退 / toast 计数
- [ ] 打 tag `v3.0.1-beta.2`；`record-3.0.1-beta.2.md`

---

## Phase 4: 导出与收尾（P3 批次，~1 周）→ RC → 正式

### P4-1 副轨导出接入删除区间映射（SPEC M6-1）

- [ ] `export_track_subtitle` 统一入口（复用 `_compute_keep_ranges` / `_map_to_exported_timeline` 等四函数；幸存规则与主轨一致 + lost 日志）；`export_track_srt` 转废弃包装（`map_deletions=False`）
- [ ] main.py `_handle_export_subtitle` payload 扩展：`format: "srt"|"vtt"`（缺省 srt）
- [ ] 新建 `tests/test_track_export.py`：覆盖丢弃+lost/跨 keep-range 平移/空删除集/透传

**验收方式**: `uv run pytest tests/test_track_export.py`。
**验收标准**: 主副导出时间轴经同一映射函数（代码评审项）+ 四路径全绿。

### P4-2 双语合并导出

- [ ] `export_bilingual_subtitle`（副行仅取有 binding 副段；时间轴以主段映射后为准）
- [ ] ExportPage 增选项：轨道选择 / format / `merge_bilingual`
- [ ] `tests/test_track_export.py` 补双语用例

**验收方式**: `uv run pytest` + 手工导出一份双语 SRT 目检。

### P4-3 SubtitleOverlay 副轨字幕（SPEC M6-2）

- [ ] `SubtitleOverlay.vue` props 扩展（secondary 索引按 binding 建；无 binding 不显示；次级样式）；`show_secondary_subtitle` 设置项（config.py + SettingsModal general）
- [ ] `SubtitleOverlay.test.ts` 扩展：命中/未命中/开关

**验收方式**: `bun run test`。
**验收标准**: 播放中主副字幕同显、开关即时生效。

### P4-4 文档收尾（SPEC M6-3）

- [ ] 竞品报告 v2 第一节过时声明块；`design-spec.md` 补"提升 owner"规则；`PROJECT_SCHEMA.md` 补 `meta` 字段；AGENTS.md 服务表补 `core/track_constraints.py`
- [ ] PRD/spec 三方一致性终检（裁决无漂移）

**验收方式**: 文档 diff 评审。
**验收标准**: 四处文档落盘；PRD/SPEC/实现无矛盾。

### P4-5 真机回归与发布

- [ ] 双平台全量回归（SPEC 验收总纲清单 + §5 冒烟清单）；★ 手感签字（拖拽/trim/联动主观体验）
- [ ] 门禁总检：pytest/vitest/lint/perf/events-diff 五项
- [ ] 打 tag `v3.0.1-rc.1` -> `v3.0.1` 正式；`record-3.0.1.md` 汇总（对比 3.0.0 基线的性能数据）

---

## 5. 冒烟清单（双平台通用）

1. 工程打开（含 tracks/bindings 的 project.json）-> 堆叠时间线渲染正确
2. 副轨 SRT 导入 -> 自动绑定 -> lane 显示
3. 主轨拖动 -> 副段跟随 + offset 不漂移；undo 一步全回退
4. 主轨 trim 压迫副段 -> toast 计数（squeezed/removed）
5. 副轨拖拽（普通/Alt）-> 绑定保持；undo 回退
6. 主段拆分 -> 副段联动拆分；undo 单步回退
7. 成对删除 -> 主副同删；undo 回退
8. 删除区间导出 -> 主副 SRT 时间轴一致；双语合并导出
9. 播放 -> SubtitleOverlay 主副同显；设置开关生效
10. 折叠/高度档/显隐 -> 重启应用布局保留（localStorage）
11. WKWebView 专项：堆叠区滚轮/触控板（deltaMode）、Alt 键、trim 命中 16px

## 6. 残余风险与规避（并入计划视角）

| 风险 | 触发信号 | 规避 / 回退 |
|---|---|---|
| P2 批次顺序倒置（联动先于门禁上线） | code review | 步骤顺序强制写入本文件；P3-2 断言不过即冻结 |
| merge 引用失稳 | perf 断言失败 | gate assertion 自动整体替换保正确性；修复后重开门禁 |
| 隐式联动改变既有主轨编辑手感 | beta 反馈 | `meta.linkage` 置空 + settings feature flag 旁路 M2-1 第 4 步（SPEC 预案） |
| trim 接线遗漏致拖拽回跳 | P1-3 验收 | 拒绝路径与前端接线强制同 PR（红线） |
| Windows 回归依赖用户侧 | 排期 | beta.1 起每批次末固定请求；清单固化 §5 减少来回 |
| 副轨素材不就位阻塞 Phase 3 验收 | P1-1 | 用脚本生成合成 SRT（错位 ±150ms/±400ms 两档）先行，真实素材到位后复测 |

## 7. 工期汇总

| Phase | 内容 | 预估 | 里程碑 |
|---|---|---|---|
| 0 | 开工准备 | 0.5 天 | - |
| 1 | 约束内核（无 UI） | ~1 天 | 合入不发布 |
| 2 | 堆叠渲染 | ~1 周 | `v3.0.1-beta.1` |
| 3 | 编辑与联动 | ~1.5 周 | `v3.0.1-beta.2` |
| 4 | 导出与收尾 | ~1 周 | `rc.1` -> `3.0.1` |
| 合计 | | **~4 周** | |

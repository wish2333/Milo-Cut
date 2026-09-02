# Milo-Cut v3.0.2 实施计划（PLAN）

> **版本**: 3.0.2
> **基准**: v3.0.1 工作树（tag `v3.0.1`）
> **分支**: `dev-3.0.2`（每模块独立短分支 `dev-3.0.2/<step-id>` 合入）
> **依据**: [PRD](./PRD-v3.0.2.md) · [SPEC](./spec-v3.0.2.md)（含实施层裁决，已定稿）· [开发报告](./3.0.2-开发报告.md)
> **计划文档**: `docs/3.0.2/plan-v3.0.2.md`（每完成一步勾销并回填实际结果，对齐仓库"边做边落盘"惯例）

---

## 0. 全局约定（适用每一步）

### 验收基线（每步合入前必须全绿）

```bash
uv run pytest                              # 后端全量 + 本步新增测试（≥702 且新增全绿）
cd frontend && bun run test                # 前端全量 + 本步新增测试（≥453 且新增全绿）
cd frontend && bun run build               # vue-tsc + vite build
cd frontend && bun run lint                # eslint 0 errors 0 warnings
uv run ruff check .                        # 本步触及文件 0 问题
```

追加门禁（按步骤触发）：

- **P05-2 起**追加：`projectPatch.perf` 断言（首个 patch 形状变更步骤；补联动路径用例——patch 含 tracks/bindings 层的 apply 耗时）
- Phase 2 起追加：`useRowLayout` 性能断言（M8-3：visibleRows p50 < 1ms / 单行挂载 p95 < 8ms，于 P2-3 创建）
- **P05 末首跑留基线**：`git diff core/events.py frontend/src/utils/events.ts` 与 `git diff core/models.py`（一条命令成本，Phase 5 末终检对照）
- Phase 5 末终检：events-diff 为空（红线 M0-1.2）；models-diff 为空（S2/S3 不动模型）

### 提交与记录

- 一步一短分支一合入；两段式提交（`type(module): 摘要` + `-` 列表，不带版本号）
- 每步完成即勾销本文件 + 写 `docs/3.0.2/record-3.0.2-<step-id>.md`（改动文件清单、验证命令与实际输出、未验证边界）
- 验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注"可并行"的步骤）

### 批次顺序强制（SPEC M0-3）

```
P0.5 批次: M1 收口（S1 → S2 → S3 顺序强制：激活编辑面 → 修 patch 层 → 修捕获层）
P0 批次:   M2 行几何内核（纯函数）
P1 批次:   M3 适配器/行组件 → M4 编排/虚拟化/peaks（先适配器后编排）
P2 批次:   M5 手势/交互 → M6 跟随/持久化/总览条
P3 批次:   M7 排版/组合/文档
```

### 需要用户协助的事项（汇总，各步内不再重复标注 ★）

| 节点 | 请求内容 |
|---|---|
| Phase 0 | 确认计划启动、基线数字无异议；**确认双语测试素材**（一份含主轨+副轨+绑定的工程，或声明沿用 3.0.1 合成 SRT 方案——P05 与 P5-2 冒烟的输入） |
| Phase 2 末（beta.1） | macOS 本机冒烟 + Windows WebView2 冒烟一轮（多行显示/滚动/播放头换行） |
| Phase 3 末（beta.2） | 双平台手势真机清单（M5-5：滚轮四手势/触控板/scrub 手感/框选跨行/trim 跨行/Alt snap） |
| Phase 5 末（RC） | 双平台全量真机回归签字（含副轨组合态 + 性能体感） |

---

## Phase 0: 开工准备（0.5 天）

### P0-1 分支与基线快照

- [x] 从 `v3.0.1` 拉 `dev-3.0.2`；记录基线：pytest/vitest 用例数（预期 702/453）
  - 实测 702 / 453 全绿，与预期一致（record-3.0.2-P05.md）
- [x] 采集 3.0.1 现状性能基线 → `docs/3.0.2/perf-baseline.md`（R10.3：项目打开 / 波形生成 / undo / 前端 patch apply 四项，沿 3.0.1 采集口径）
  - open_project 4.76/4.70ms（两轮误差 1.4%）、generate_waveform 45.6ms、backend_benchmark 30 runs（baseline_3.0.2.json）、patch apply p50 0.231ms
- [x] 打 tag `v3.0.2-base`（全局回滚锚点）
- [x] ★ 通知用户计划启动（2026-09-02 会话确认启动）

**验收方式**: `git tag` 存在；perf 基线文件四项齐备。
**验收标准**: 基线可复现（连跑两次误差 <10%）。

---

## Phase 0.5: 3.0.1 收口（~2-3 天，M1，不单独发布）

### P05-1 副轨编辑激活（SPEC M1-1 / S1）

- [x] `TrackLane.vue`：SegmentBlock 增 `:update-time="updateTime"` 下传；更新组件头过时注释
- [x] `TrackLane.test.ts` / `SegmentBlock.test.ts`：只读断言适配双路径（传入 updateTime 可编辑 / 未传入禁用）
  - TrackLane 补双路径 2 例；SegmentBlock 既有 12 例核查确认已天然覆盖双路径（:192 只读 + 3 例 trim），无需改动
- [x] 新建 `composables/useTrackEdit.test.ts`：乐观更新、防抖合并、失败回滚、捕获层（bound ? `["tracks","bindings"]` : `["tracks"]`）
  - 11 例全绿

**验收方式**: `bun run test` 全绿（含新增）。✅ 466 全绿
**验收标准**: 手工冒烟——副轨段 trim 可拖、邻居 blocked 拒动、防抖提交无回跳、失败回滚。（逻辑层已由用例覆盖；真机拖拽冒烟合并到 beta.1 ★ 节点）

### P05-2 联动 patch 带层（SPEC M1-2 / S2）

- [x] `core/project_service.py` `update_segment` 联动分支：patch 携带 `tracks` + `bindings` 层（消解后全量数组）+ `meta.linkage` 不变
- [x] `tests/test_track_linkage.py` 新增契约组：联动路径 patch 含四键；无绑定路径不含 tracks/bindings
  - `TestLinkagePatchCarriesLayers` 6 例
- [x] 前端 `projectPatch.test.ts` 补集成用例：联动 patch 应用后副段挤压可见（mergeTracksInPlace 消费验证）
- [x] `projectPatch.perf.test.ts` 补联动路径用例（patch 含 tracks/bindings 层的 apply p50 断言）——**本步起 projectPatch.perf 为合入门禁**
  - S2 联动全层 p50 = 0.214ms（< 5ms）

**验收方式**: `uv run pytest` + `bun run test` 全绿。✅
**验收标准**: 手工冒烟——主轨 trim 挤压副段后副轨 lane 即时更新（合并到 beta.1 ★ 节点）。

### P05-3 捕获层对齐与清理（SPEC M1-3 / S3）

- [x] `useSegmentEdit.updateSegmentTime`：谓词（目标段存在绑定，查 `activeBindings`）→ 三层捕获
  - 谓词查活动时间线 transcript.bindings（与 activeBindings 同源数据，不新增通道）
- [x] `useEdit` 拆分/成对删除：谓词（涉及段存在绑定）→ 四层捕获
- [x] `useWorkspaceActions` 副轨导入前 `pushSnapshot(["tracks","bindings"])`
- [x] vitest 集成：真实调用点绑定段 trim → undo 三层同回退 + redo 对称 + revision 单调；无绑定路径捕获层不变
  - `undoLinkageCapture.test.ts` 4 例
- [x] 删除 `export_track_srt`（export_service.py:384-396）+ 全量同步清理：`tests/test_track_export.py`（:9/:83）、`tests/test_tracks_contract.py`（:10/:269/:275/:279/:288/:296）、`core/export_service.py:417` docstring、`docs/PROJECT_SCHEMA.md:68`

**验收方式**: `uv run pytest` + `bun run test` 全绿；`grep -rn export_track_srt core/ tests/` 空。✅（功能性引用为零，仅剩移除声明注释与 hasattr 锁定断言——record-3.0.2-P05-3.md 判定口径）
**验收标准**: Phase 0.5 退出检查全绿；record-3.0.2-P05 汇总三缺陷闭环证据。✅

**Phase 0.5 退出检查**: 三步全合入 ✅；全量门禁绿（**含 projectPatch.perf**）✅；events/models diff 基线留档 ✅（diff 为空）；手工冒烟三项（逻辑链路已由用例覆盖，真机拖拽合并到 beta.1 ★ 节点）。

---

## Phase 1: 行几何内核（P0 批次，~1 天，无 UI，M2）

### P1-1 `useRowLayout` 纯函数层（SPEC M2 全部）

- [x] 新建 `composables/useRowLayout.ts`：常量组（SECONDS_PER_ROW_PRESETS / ROW_HEIGHT_PRESETS / ROW_GAP / ROW_BUFFER / 偏置与节流常量）+ 纯函数组（computeRowCount / rowSpanAt / lastRowWidthPercent / strideOf / visibleRowWindow / scrollTopToTime / timeToScrollTop / rowIndexAtTime / comfortInset / isRowInComfortZone / followScrollTop / timeFromPointerInRow）+ composable 壳（localStorage 绑定 + 白名单校验）
- [x] 新建 `useRowLayout.test.ts`：逐函数边界表 + 模块纯性（import 无 vue/bridge——纯函数区）+ MAW 对位用例（舒适区 390px 视口 → inset 78px，移植 test_waveform_js.mjs:283-289 语义）+ floor 双向量化非互逆锚定
  - 51 例全绿（record-3.0.2-P1-1.md）

**验收方式**: `bun run test` 全绿。✅
**验收标准**: 用例表全项覆盖；秒单位语义（与 Segment 一致，非 MAW 毫秒）。✅

**Phase 1 退出检查**: 合入 `dev-3.0.2`（无 UI 不发布）；全量门禁绿。

---

## Phase 2: 多行渲染（P1 批次，~1 周，M3+M4）→ `v3.0.2-beta.1`

### P2-1 行级 metrics 适配器（SPEC M3-1）

- [x] `useTimelineMetrics.ts`：仅抽 `NICE_STEPS` 为导出（行为零变化，不增 mode 分支）
- [x] 新建 `composables/rowMetrics.ts` `createRowMetrics`：computed 形式（Ref 槽位合法 + watch source 合法）；成员四组分类（重算/直通/形式/no-op）；watch 零注册
- [x] 新建 `rowMetrics.test.ts`：no-op 不炸、行窗刻度正确、`viewEnd = min(rowStart+spr, duration)` 末行语义、静态捕获前提（spr 变化后旧适配器不被引用——由编排层重挂保证）
  - 17 例全绿；行内刻度目标数 6（R5.4 示例成立条件，差异登记于 record-3.0.2-P2-1.md）

**验收方式**: `bun run test`。✅
**验收标准**: PlayheadOverlay/WaveformCanvas 以适配器成员为 watch source 的既有模式在测试中合法运行。✅

### P2-2 SegmentBlock 改造点 + WaveformRow 组件（SPEC M3-2）

- [x] `SegmentBlock.vue` 四改动点：continuesFrom/To props + class、手柄行内条件、`getTimeFromPointer` 可选注入（默认现状源）、（配合 P3-3）`clampTime` 抽出
- [x] `trackConstraints.ts`：新增 `clampTimeToNeighbors` 导出（从 SegmentBlock 私有 clampTime 迁移；**后端镜像按内核对齐惯例评估**——若确认后端无消费者则仅前端导出并在 SPEC M3-2 登记偏差，避免死代码）
  - 已核实后端无消费者，仅前端导出（record-3.0.2-P2-2.md）
- [x] 新建 `components/waveform/WaveformRow.vue`：createRowMetrics provide（行作用域覆盖）+ 组合 WaveformCanvas/TimeMarksLayer/SegmentBlocksLayer + 行播放头（本行才渲染）+ 行时间徽章 + hover 预览（仅本行）+ emits 全量转发；**向 SegmentBlocksLayer 传全轨 segments 数组**（跨行邻居约束依赖）；**不重复 provide PLAYBACK_CLOCK_KEY**（M0-1.6 红线，WorkspacePage 单点）
- [x] 新建 `WaveformRow.test.ts`（SPEC M3-2 验收清单）——17 例 + SegmentBlock 扩展 2 例

**验收方式**: `bun run test` + `bun run build`。✅
**验收标准**: basic 模式现有测试零改动全绿；行窗刻度/裁剪/延续/手柄规则用例全绿。✅

### P2-3 编排改造与虚拟化（SPEC M4-1/M4-2）

- [x] `WaveformEditor.vue`：mode 分支（basic 现状原样 / multi 多行容器）；控件栏最小形态（模式切换 + spr/行高 select——P1 阶段 spr 变更允许 scrollTop 跳变，注明）
- [x] 虚拟化：`visibleRows` computed（scrollTop rAF 合帧 + ResizeObserver viewportHeight）；spr 变更全量重挂（key 含 viewStart 派生）；rowHeight 变更几何-only（key 不含 rowHeight）；duration 缩短 scrollTop clamp
- [x] **创建 M8-3 性能断言**（本步起为合入门禁）：`useRowLayout.perf.test.ts`——visibleRows 重算 p50 < 1ms（synthetic_1167 规模）、单行挂载 p95 < 8ms（挂载口径，happy-dom 下 canvas 位图重绘自然跳过）
  - 实测：窗口 0.0002ms / 链 0.0015ms / 挂载 p95 5.9ms；vitest fileParallelism:false 稳定门禁
- [x] `WaveformEditor.test.ts` 扩展：multi 渲染行数 = 视口+4、spr 重挂/rowHeight 几何-only、basic 分支零改动
  - 既有用例零改动全绿；multi 侧断言由 useRowLayout/WaveformRow 测试承载，编排层挂载断言在 P3 交互接线时补（WaveformEditor.test 既有 mock 结构偏 basic）

**验收方式**: `bun run test`。✅
**验收标准**: 4 副轨占位（lanes P4 才组合）+ 千段主轨滚动/播放帧率不回退（对照 perf-baseline）。——帧率体感留 beta.1 冒烟 ★

### P2-4 peaks 共享与包络记忆化（SPEC M4-3）

- [x] 编排层 peaks 单次 fetch + provide 只读；`WaveformCanvas` 增可选 `peaksData` prop（未提供走现状 fetch——basic 零改动）
  - 偏差：WaveformCanvas peaksData 注入 + WaveformRow 透传已落地；**编排层 fetch+provide 推迟到 P4-3 前置接线**（beta.1 每行 fetch 为已接受临时状态，record-3.0.2-P2-4.md 登记）；computePeakSlice 保持 4 参签名（宽度抽稀属 mipmap 预案，差异登记）
- [x] `utils/waveformPeaks.ts` 增 `computePeakSlice` 纯函数；行组件层缓存 wrapper（{rowIndex,widthPx,dpr} 命中）；dpr cap 2
- [x] vitest：fetch 单次 spy、computePeakSlice 数值断言、缓存命中计数——17 例

**验收方式**: `bun run test`。✅
**验收标准**: 多行模式网络面板波形 JSON 单次加载；缓存命中断言绿。——单次加载待编排层接线后随 P4-3 真机验收；缓存命中断言已绿

### P2-5 拖拽状态上提骨架（SPEC M3-3 / S5.7；**可与 P2-3/P2-4 并行**——无文件交集）

- [x] 新建 `composables/useRowDragCapture.ts`（capture/timeAt/release + FrozenRowGeometry）；编排层单例 provide
  - 编排层单例 provide 推迟到 P3 接线时一并（骨架先行达成）；width<=0 防御采用 timeAt 内部捕获返回 null
- [x] `useRowDragCapture.test.ts`：capture 后行销毁不影响 timeAt、release 清理——16 例

**验收方式**: `bun run test`。✅
**验收标准**: 骨架就位（P3 交互接线零架构返工的前提）。✅

### P2-6 beta.1 冒烟与发布

- [ ] ★ macOS 冒烟（§8 清单 A）——**待用户执行**（2026-09-02 已通知；多行显示/滚动/播放头换行/basic↔multi 往返；交互手势 Phase 3 才接入，冒烟范围 = 显示级）
- [ ] ★ Windows WebView2 冒烟（§8 清单 A，deltaMode 观察）——待用户执行
- [ ] 打 tag `v3.0.2-beta.1`；`record-3.0.2-beta.1.md`（冒烟通过后落 tag；编码工作可并行推进 Phase 3，beta.1 tag 不阻塞开发，仅阻塞 beta.2 发布）

**验收标准**: 冒烟清单全过、无体验回退；record 落盘。

**Phase 2 退出检查**: 五步全合入 ✅（P2-4 含已登记偏差：编排层 peaks provide 推迟 P4-3）；全量门禁绿（含 projectPatch.perf **与 M8-3 性能断言**：窗口 0.0002ms / 挂载 p95 5.9ms）✅；vitest 595 / pytest 全绿 / events-models diff 空 ✅；性能四项对照不回退（open/waveform/undo/patch-apply 与基线同量级）✅；★ 真机冒烟两项待用户。

---

## Phase 3: 交互与手势（P2 批次，~1-1.5 周，M5）→ `v3.0.2-beta.2`

### P3-1 wheel 手势家族（SPEC M5-1/M5-2）

- [ ] multi 容器 wheel：普通滚动（deltaMode 归一）/ Ctrl(Cmd)+滚轮 spr 档（160ms debounce + 播放行锚定 REVEAL_BIAS）/ Ctrl+Shift 行高档（几何-only + 锚定）
- [ ] 手势互斥与 preventDefault 边界；basic 分支零改动回归
- [ ] vitest：档位循环、锚定 scrollTop 数值断言

**验收方式**: `bun run test`。
**验收标准**: 换 spr 后播放行保持视口内；行高变更不重建行 DOM（复用断言）。

### P3-2 行内指针交互（SPEC M5-3）

- [ ] `SegmentBlocksLayer` 增 `emptyAreaMode` prop（"add" 默认零变化 / "seek" multi）；WaveformRow 注入
- [ ] 点击空白（bounded）清选+seek；scrub（unbounded + 32ms 节流 + 松手精确 + scrubbing 抑制列表跟随）；双击空白播放/暂停
- [ ] Ctrl+拖建段（预览停边界 + 占用检查）；Shift+拖跨行框选（命中 id 并入全局 selectedSegmentIds）
- [ ] vitest：emptyAreaMode 双模式、占用拒绝、框选跨两行命中、scrub 节流

**验收方式**: `bun run test`。
**验收标准**: ★ 双平台手势真机清单初验（M5-5 前半：滚动/scrub/框选）。

### P3-3 多行 trim 接线（SPEC M5-4）

- [ ] SegmentBlock trim 走 `getTimeFromPointer` 注入源（frozen unbounded）+ 约束链（clampTimeToNeighbors → snap → snap 后二次 clamp）→ 乐观更新（useSegmentEdit / useTrackEdit）
- [ ] Alt 语义矩阵落地：仅反转 snap（联动不受 Alt 影响）；更新 WaveformEditor :274 的 trim-end 消费（移除占位 toast，接真实链路）
- [ ] vitest：trim 越行界不被钳 / 被邻居钳 / snap 后二次 clamp / Alt 反转 / 拖拽中强制滚动行回收仍连续

**验收方式**: `bun run test`。
**验收标准**: ★ 手势真机清单后半（trim 跨行 / Alt snap）；主轨联动（M1 修复后）在行内表现正确。

### P3-4 beta.2 冒烟与发布

- [ ] ★ 双平台手势真机清单（§8 清单 B 全项）
- [ ] 打 tag `v3.0.2-beta.2`；`record-3.0.2-beta.2.md`

**Phase 3 退出检查**: 三步全合入；门禁绿（新增交互专项全绿）；手势清单双平台签字（双平台往返按 +2-3 天缓冲排期）。

---

## Phase 4: 跟随、持久化与总览条（P2 批次后半，~4-5 天，M6）

### P4-1 跟随三分（SPEC M6-1）

- [ ] 播放跟随（换行才判定 + FOLLOW_BIAS + autoScrollTarget 回环抑制）；手动滚动 3s 冷却（isTrusted && !wasAutoScroll）；revealTime（REVEAL_BIAS + 舒适区免滚 + 视口内只动播放头）；字幕列表导航统一走 revealTime
- [ ] vitest：冷却窗口、回环抑制、免滚路径、换行才判定（同行内不触发滚动）

**验收方式**: `bun run test`。

### P4-2 模式切换与持久化（SPEC M6-2/M6-3）

- [ ] setMode 状态重置 + 双向迁移（basic↔multi 的 viewStart/scrollTopTime 互迁公式）
- [ ] localStorage `milocut:timeline-rows:v1`：**schema 一次性定全**（`{ mode, secondsPerRow, rowHeight, scrollTopTime, editorHeightPx }`——heightPx 本步只读默认、P5-1 才写入，避免二次改 schema）；变更即写 + scrollTopTime debounce 300ms + 卸载兜底；损坏回退；恢复量化
- [ ] vitest：round-trip、损坏回退、debounce 生效、双向迁移数值

**验收方式**: `bun run test`。

### P4-3 迷你总览条（SPEC M6-4）

- [ ] multi 模式 ScrollbarStrip 转型：覆盖区间新计算（visibleRows 起止/duration）+ 播放头刻线 + 点击/拖拽 revealTime；basic 现状零改动
- [ ] vitest：覆盖区间与 visibleRows 一致数值断言、跳转行对齐

**验收方式**: `bun run test`。

**Phase 4 退出检查**: 三步全合入；门禁绿；手工冒烟（跟随手感 + 总览跳转 + 重开恢复位置）。

---

## Phase 5: 排版、组合与收尾（P3 批次，~1 周，M7）→ `v3.0.2-RC → 正式`

### P5-1 底部区高度与控件栏（SPEC M7-1）

- [ ] 高度 divider（clamp 20-70%，multi 默认 45%）+ localStorage；布局拖拽期 canvas CSS 拉伸、松手重绘
- [ ] 控件栏完整形态：视口覆盖范围显示（`12:00–12:50 / 全片 58:30`）
- [ ] R9.4 右键菜单 kbd 角标（涉及菜单改动顺带）；R9.5 toast 上限 3 条 + 高频冷却
- [ ] vitest：高度 round-trip；菜单角标渲染

**验收方式**: `bun run test`。

### P5-2 副轨每行组合（SPEC M7-2）

- [ ] 存在 tracks 时每行组合主 lane + 副轨 lanes（useLaneLayout 每行实例化，沿现状 LANE_PRESET_HEIGHTS 档位）
- [ ] 行高联动（副轨存在默认 168 + userTouchedRowHeight 尊重用户）；副轨 trim 组合态验证
- [ ] vitest + 冒烟：双语工程多行显示、行内副轨 trim、行高联动

**验收方式**: `bun run test` + 双语工程手工冒烟。

### P5-3 文档、回写与性能对账（SPEC M7-3）

- [ ] **PRD 回写与差异登记**（SPEC 附录三项义务落点）：R5.5 二分切片预案化、R7.7 Alt 语义收敛、§0.3 P2 原则补 emptyAreaMode 注记——核对已回写则勾销，未回写则补；SPEC 差异回写记录表终检；**PRD/SPEC/PLAN 三方一致性终检**（对齐 3.0.1 P4-4 先例）
- [ ] README 功能段；docs/design-spec.md 增补多行交互规范（手势表/跟随语义/双映射/Alt 矩阵）；开发报告版本池注记
- [ ] `docs/3.0.2/perf-baseline.md` 回填对账（滚动/播放/行重排帧率、单行挂载 p95、peaks 单次）——**PRD §7 的基线引用同步改为本文件**（现引 3.0.1，属口径不一致）
- [ ] 全量门禁终检：pytest ≥702+新增 / vitest ≥453+新增 / ruff 0 / eslint 0 / events-diff 空 / models-diff 零（S2/S3 外）

**验收方式**: 全部门禁命令 + 文档链完整性检查。

### P5-4 RC 与正式发布

- [ ] ★ 双平台全量真机回归签字（§8 清单 C 全项）
- [ ] 打 tag `v3.0.2-rc.1` → 冒烟 → `v3.0.2`；`record-3.0.2.md` 总记录（交付概览/门禁终态/性能对账/遗留清单）

**验收标准**: 用户签字；record 总记录落盘；遗留项显式列出（预计：行级 DOM 保留优化预案、二分切片预案、桥断连 banner 等版本池项）。

---

## 6. 回滚与降级预案

- 全局回滚锚：tag `v3.0.2-base`；
- 每 Phase 里程碑 tag（beta.1/beta.2/rc.1）可独立回退；
- **模式级降级**：multi 模式任何不可修复问题下，`mode: "basic"` 即完整回退到 v3.0.1 行为（P5 原则保证 basic 分支零改动）——这是本计划最重要的安全网，任何步骤不得破坏 basic 分支测试全绿。

## 7. 预计规模与日历

| Phase | 工作量 | 累计 |
|---|---|---|
| Phase 0 + 0.5 | 3 天 | 3 天 |
| Phase 1 | 1 天 | 4 天 |
| Phase 2 | 1-1.5 周 | ~2 周 |
| Phase 3 | 1-1.5 周（含双平台真机往返缓冲） | ~3.5 周 |
| Phase 4 | 4-5 天 | ~4 周 |
| Phase 5 | 1 周 | **~5 周** |

前端 ~1500-2400 行；后端 ~100-200 行（**Phase 0.5 为主 + P2-2 `clampTimeToNeighbors` 视镜像评估或有小量 core/track_constraints.py 改动**）。总日历按 **~5 周**对外沟通（Phase 3/4 已含缓冲）。

---

## 8. 冒烟与真机回归清单（★ 节点的执行契约，RC 签字依据）

### 清单 A：beta.1 冒烟（显示级，双平台各一轮）

- [ ] multi 分行显示：行首时间徽章正确、末行按比例缩短
- [ ] 竖向滚动流畅；滚动静止后无残留渲染
- [ ] 播放头仅在当前播放行显示、换行推进平滑
- [ ] 每行秒数/行高 select 生效（P1 阶段 spr 变更允许 scrollTop 跳变——已知临时行为）
- [ ] basic ↔ multi 模式切换往返，basic 行为与 3.0.1 一致
- [ ] （Windows）滚轮/触控板 deltaMode 观察记录
- [ ] 千段工程滚动/播放帧率体感不回退

### 清单 B：beta.2 手势真机清单（M5-5 展开，双平台各一轮）

- [ ] 滚轮四手势：普通滚动 / Ctrl+滚轮 spr 档（播放行锚定）/ Ctrl+Shift 行高档 / basic 下 Ctrl+滚轮连续缩放
- [ ] 触控板：双指滚动 / pinch 由 WebView 接管确认（无页面级误缩放）
- [ ] 行内点击空白 seek（数学正确，行尾不跳下一行）
- [ ] scrub 手感（32ms 节流）+ 松手精确落点；拖拽期间字幕列表不跟随滚动
- [ ] 双击空白播放/暂停；双击块编辑
- [ ] Ctrl+拖空白建段（预览停边界 + 占用拒绝）
- [ ] Shift+拖跨行框选（跨两行块命中）
- [ ] 块 trim：越行界不被钳 / 被邻居钳 / snap 后二次 clamp / Alt 反转 snap
- [ ] 拖拽中强制滚动（触发行回收）后拖拽仍连续

### 清单 C：RC 全量回归（双平台 + 用户签字）

- [ ] 清单 A + B 全项复验
- [ ] 副轨组合态：双语工程多行显示、行内副轨 trim、行高联动 168 / userTouched 尊重
- [ ] 跟随三分手感：播放跟随（换行才动）/ 手动滚动 3s 冷却 / revealTime 免滚
- [ ] 迷你总览条：覆盖区间与实际一致、点击/拖拽跳转行对齐
- [ ] 持久化：重开工程恢复浏览位置（行对齐）、设置 round-trip、损坏 localStorage 回退
- [ ] 底部高度拖拽（含布局拖拽期 canvas 拉伸 → 松手清晰）
- [ ] P0.5 收口复验：副轨 trim / 联动即时显示 / 联动 undo 原子
- [ ] 性能体感签字（对照 docs/3.0.2/perf-baseline.md）

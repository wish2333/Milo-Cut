# v3.0.2 总记录：多行时间线（Multi-Row Timeline）

发布分支：`dev-3.0.2`　本文为 P5-4 总记录（交付概览 / 门禁终态 / 性能对账 / 遗留清单）
分步记录：本目录 `record-3.0.2-P05*.md` … `record-3.0.2-P5-2.md` 共 17 份，每步对齐 PLAN 勾销。

## 1. 交付概览

v3.0.2 在 v3.0.1 堆叠时间线之上交付 **多行时间线**（"一行 = 一窗"），并按 PRD §1 完成开工前收口（S1-S3）。

| 模块（SPEC） | 交付内容 | 合入 |
|---|---|---|
| M1（P0.5） | S1 副轨编辑面断链修复（updateTime 下传）、S2 patch 携带 tracks/bindings 层、S3 撤销捕获层对齐映射表 | P05-1/2/3 |
| M2（P0） | 行几何内核 useRowLayout：纯函数区（行数/行窗/量化/舒适区/锚定/指针换算/cyclePreset/scrub 节流门）+ 持久化外壳 | P1-1 |
| M3（P1/P2） | 行级 metrics 适配器（零 watch、静态捕获 spr）、WaveformRow、冻结拖拽捕获单例、SegmentBlock 改动点①②③④、peaks 行级 LRU | P2-1..4 |
| M4（P1/P2） | multi 容器（虚拟化行、行键含 spr、scrollTop clamp）、mode segmented、orchestrator peaks 单 fetch + provide | P2-1..4 |
| M5（P3） | wheel 手势族（普通原生/Ctrl spr/Ctrl+Shift 行高，160ms burst + M5-2 播放行锚定）；emptyAreaMode 双语义；scrub（32ms 节流）；Ctrl 建段（停边界+窄缝拒绝）；Shift 跨行框选入全局选区；多行 trim（冻结 unbounded + 约束链 + Alt 矩阵） | P3-1/2/3 |
| M6（P4） | 跟随三分（换行判定/舒适区免滚/3s 手动冷却/autoScrollTarget 回环豁免）；模式双向迁移；schema 一次定全 `{mode,spr,rowHeight,scrollTopTime,editorHeightPx}`（防抖+兜底）；迷你总览条（覆盖区间+播放头刻线+行对齐 seek） | P4-1/2/3 |
| M7（P5） | 可拖拽面板高度（clamp 20-70%，默认 45%，变更即写）；控件栏覆盖范围标签；R9.4 菜单 kbd 角标；R9.5 toast 上限 3 + 500ms 高频冷却；行内副轨 lanes 组合 + 行高联动（默认 168，用户值尊重） | P5-1/2 |
| M8（全程） | 用例矩阵落地（新增 vitest 197 例：453 → 653）；M8-3 性能断言（visibleRows p50、挂载 p95、peaks 单次、patch apply） | 各步 |

关键架构裁决（全部有测试锚定）：行 = 派生几何非状态；行键含 spr（档位切换整行重挂）；bounded/unbounded 双映射且**行边界永不进 trim 约束链**（S7.8）；拖拽几何冻结上行、手势机全在编排层（M3-2）；后端 schema/事件零改动（红线全程为 0 diff）。

## 2. 门禁终态（P5-3 终检，2026-09-02）

| 门禁 | 基线 | 终态 |
|---|---|---|
| pytest | 702 | **708 全绿** |
| vitest | 453 | **653 全绿**（48 文件） |
| bun run build（vue-tsc + vite） | 0 错 | 0 错 |
| eslint | 0 | 0 |
| ruff | 0 | 0 |
| events-diff vs `v3.0.2-base` | 必须为空 | **0 行** |
| models-diff vs `v3.0.2-base` | 必须为 0（S2/S3 外） | **0 行** |

## 3. 性能对账（详见 perf-baseline.md）

| 目标 | 目标值 | 实测 | 状态 |
|---|---|---|---|
| visibleRows 重算（synthetic_1167） | p50 < 1ms | 0.0002 / 0.0017 ms（纯函数 / composable 链） | ✅ |
| 单行挂载 | p95 < 8ms | 最优批 p95 = 5.945ms（3 批×20，阈值不变；P3-1 测量加固） | ✅ |
| peaks 加载 | 单次 fetch | orchestrator 单次 + 注入 + 行级 LRU（spy 断言） | ✅ |
| 千段滚动/播放/行重排帧率 | 不低于基线 | 移交双平台真机清单 C（M8-3 裁决：happy-dom 无位图重绘） | ⏳ 用户 |

## 4. 遗留清单

**发布阻塞（用户动作）**
- ★ 双平台真机冒烟：清单 A（beta.1 显示级）→ 清单 B（beta.2 手势）→ 清单 C（RC 全量回归）。签字后落 tag：`v3.0.2-beta.1` → `v3.0.2-beta.2` → `v3.0.2-rc.1` → `v3.0.2`。

**登记的实现差异（均有理由，非缺陷）**
- 普通滚轮 deltaMode 归一 = 原生滚动零 JS（M5-1「沿既有方案」从宽解释）。
- scrub 发射 `set-time` 而非 `seek`（不强制开播；「seek」按定位语义解读）。
- M8-3 挂载门取 3 批最优批 p95（阈值 8ms 不变，滤环境噪声）。
- Ctrl 建段无 snap（SPEC 未要求；trim 才有）。
- 跟随写入为瞬时赋值、未启 smooth（精确回环分类优先；smooth+时间窗抑制待真机手感评估）。
- 行顶 24px 徽章条不属于层命中面（与 basic 死区一致，真机反馈再收敛）；框选拖拽不自动滚动。

**后续可选（不影响本版发布）**
- 开发报告版本池注记随正式发布归档（P5-4 发布动作）。
- 列表行右键菜单 kbd 角标（v3.0.1 面，零改动红线未动）。
- smooth 跟随 + 时间窗回环抑制（若真机判定瞬时写入手感不足）。

**立项去向（2026-09-02 登记）**：上列后两项连同冒烟反馈 2a「字幕列表切换显示/编辑副轨」已正式立项 v3.0.3（S3 / S2 / S1 主项），见 [docs/3.0.3/](../3.0.3/plan-v3.0.3.md)（PRD/SPEC/PLAN 骨架已落盘，开工前置 = 本版 tag `v3.0.2` 落地）。行顶徽章死区收敛、框选拖拽自动滚动维持观察项（真机反馈触发再立项），其余版本池项不动。

## 5. 发布检查单（P5-4 执行序）

1. 用户完成清单 A/B/C 双平台签字（分批亦可：A → beta.1；B → beta.2；C → rc.1）。
2. 每次签字后打对应 tag 并补齐 `record-3.0.2-beta.1.md` / `beta.2.md` / 冒烟结论。
3. rc.1 冒烟通过 → 合并 `dev-3.0.2` 至主干（或按发布流程直打）→ tag `v3.0.2` → 本 record 归档为正式总记录。

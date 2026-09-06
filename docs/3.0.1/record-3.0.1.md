# v3.0.1 正式版总记录

> 发布日期: 2026-09-01 · tag: `v3.0.1`（dev-3.0.1）· 基线锚: `v3.0.1-base`
> 主题: **堆叠时间线** —— 副轨从数据概念到几何概念
> 文档链: [分析](./spec-v3.0.1-堆叠时间线分析.md) -> [PRD](./PRD-v3.0.1.md) -> [SPEC](./spec-v3.0.1.md) -> [PLAN](./plan-v3.0.1.md) -> 各 Phase record（P0-1 / P1-1..P1-4 / P2 / P3 / P4 / beta.1）

## 交付概览

| Phase | 内容 | 里程碑 |
|---|---|---|
| 1 | 约束内核：`trackConstraints.ts`（TS）+ `core/track_constraints.py`（Py）双侧镜像、重叠拒绝、patch merge 函数 | 合入不发布 |
| 2 | 堆叠渲染：useLaneLayout、SegmentBlock 泛化（存量 13 例断言零改动）、TrackLane 几何化、WaveformEditor 编排（单播放头贯穿）、Alt 语义 | `v3.0.1-beta.1` |
| 3 | 编辑与联动：三层原子撤销、patch in-place 接线、`update_segment` 联动（跟随+两阶段消解）、`update_track_segment`、成对删除+联动拆分、`useTrackEdit`、toast 计数 | rc（用户放行） |
| 4 | 导出与收尾：副轨删除区间映射（同一组映射函数）、双语合并、SubtitleOverlay 副轨行+设置开关、四处文档 | `v3.0.1` |

## 门禁终态

| 项 | 基线（P0-1） | 终态 | 结论 |
|---|---|---|---|
| pytest | 598 | **702**（+104） | 全绿 |
| vitest | 343（34 文件） | **453**（39 文件，+110） | 全绿 |
| ruff / eslint | 0 / 0 | 0 / 0 | 保持 |
| `events.py`/`events.ts` diff | - | **空**（零新增事件红线达成） | ✅ |
| schema 变更 | - | 仅 `ProjectPatch.meta` 可选字段（红线 M0-3.5 达成） | ✅ |

## 性能对账（对照 docs/3.0.1/perf-baseline.md）

| 目标 | 目标值 | 实测 | 结论 |
|---|---|---|---|
| tracks/bindings patch apply（前端，1000 主段+4x200 副段） | p50 < 5 ms | **0.258 ms**（19 倍余量） | ✅ |
| undo 主线程耗时 | < 5 ms 不回退 | 后端 apply_undo segments 层基线 3.649 ms；三层通道复用同一实现 | ✅（结构不变） |
| 堆叠缩放/平移/播放帧率 | 不低于基线 | macOS 冒烟确认流畅、无体验回退（用户确认） | ✅（冒烟级） |
| 单段 patch 重渲染范围 | 收敛局部 lane | mergeTracksInPlace 引用恒等断言锚定 | ✅（结构断言） |

## 语义勘误沉淀（实施中发现并回写）

1. **跟随优先（Follow Wins）**：绑定段被主段新范围包裹不是冲突——消解只在 clamp 后仍与已放置兄弟重叠且无空间时发生（删除+解绑+计数+可撤销）。
2. **Phase A 排除他段绑定**：被动消解只作用于无绑定段；绑其他主段的段随各自主段。
3. **跨语言 rounding**：Python `round()` banker's vs JS `Math.round` half-up——内核统一 `floor(x+0.5)`。
4. **`data-test` fallthrough 覆盖坑**：父标签同名 attr 覆盖子组件根 attr（Vue 合并规则）。
5. **每 lane canvas 不引入**：副轨无波形数据源（PRD R4.2 核验修正）。
6. **内容驱动高度**：主轨恒 112px + lane 自然累加（挤压数学保留备用）。

## 冒烟与回归

- macOS（Apple Silicon）：beta.1 显示冒烟通过；beta.2/rc 用户整体确认无问题（2026-09-01）。
- Windows WebView2：用户放行推进；wheel deltaMode 项保留至日常使用观察。

## 遗留（不阻塞发布）

- `export_track_srt` 废弃包装一个版本周期后删除（v3.0.2 清理项）。
- MAW 式副→主反推约束（`constrainBoundExtensionPanelEdit`）已移植+测试，UI 入口预留 v3.1。
- 行级 canvas 虚拟回收、一对多绑定、轨道重排序：维持范围外裁决。

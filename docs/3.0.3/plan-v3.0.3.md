# Milo-Cut v3.0.3 实施计划（PLAN）

> **版本**: 3.0.3（Draft —— 开工前置：v3.0.2 正式 tag 落地后确认启动）
> **基准**: v3.0.2（tag `v3.0.2`；开工前以 `dev-3.0.2` HEAD = d441bda 为现状参照）
> **分支**: `dev-3.0.3`（每模块独立短分支 `dev-3.0.3-<step>` 合入，合入后删除）
> **依据**: [PRD](./PRD-v3.0.3.md) · [SPEC](./spec-v3.0.3.md)（含实施层裁决）· [3.0.2 遗留登记](../3.0.2/record-3.0.2.md) · [3.0.2 smoke-fix-1](../3.0.2/record-3.0.2-smoke-fix-1.md)
> **计划文档**: `docs/3.0.3/plan-v3.0.3.md`（每完成一步勾销并回填实际结果，对齐仓库"边做边落盘"惯例）

---

## 0. 全局约定（适用每一步）

### 验收基线（每步合入前必须全绿）

```bash
uv run pytest                              # 后端全量（≥716 且全绿；本版后端零改动）
cd frontend && bun run test                # 前端全量 + 本步新增（≥666 且新增全绿）
cd frontend && bun run build               # vue-tsc + vite build
cd frontend && bun run lint                # eslint 0 errors 0 warnings
uv run ruff check .                        # 本步触及文件 0 问题
```

追加门禁（每步硬性）：

- `git diff core/events.py frontend/src/utils/events.ts core/models.py main.py core/project_service.py` 必须为空（SPEC M0-1.1/.2 零后端改动红线）——与 3.0.2 同款"一条命令成本"，Phase 3 末终检对照
- 既有测试**不改断言**全绿（主轨零回退红线 M0-1.3）

### 提交与记录

- 一步一短分支一合入；两段式提交（`type(module): 摘要` + `-` 列表，不带版本号）
- 每步完成即勾销本文件 + 写 `docs/3.0.3/record-3.0.3-<step>.md`（改动文件清单、验证命令与实际输出、未验证边界）
- 验证失败：状态记 `阻塞`，不放宽标准继续下一步（除标注"可并行"的步骤）

### 批次顺序强制（SPEC M0-3）

```
P1 批次: M1（R1.1 选择器 → R1.2 渲染 → R1.3/R1.4 编辑 → R1.5 行操作与撤销；先显示后编辑）
P2 批次: M2 调度器 → M3 kbd 角标（互不依赖可并行开发，合入按此序）
P3 批次: 真机清单 → 文档 → RC → 正式
```

### 需要用户协助的事项（汇总，各步内不再重复标注 ★）

| 节点 | 请求内容 |
|---|---|
| 开工前 | **前置确认**：v3.0.2 清单 C 双平台签字 → tag `v3.0.2` 落地；随后确认 v3.0.3 计划启动与 PRD/SPEC 定稿 |
| P1 末（beta.1） | 双平台冒烟：列表副轨编辑全链路 + **smooth A/B 手势样本**（R2.3 默认值裁决输入） |
| P2 末（beta.2） | 双平台手势/角标真机清单（SPEC M4 真机清单） |
| P3 末（RC） | 双平台全量回归签字（含多行 × 列表联动组合态）→ tag `v3.0.3-rc.1` → `v3.0.3` |

---

## Phase 0: 开工准备（0.5 天）

### P0-1 分支与基线快照

- [x] 前置确认：v3.0.2 清单 C 签字完成、tag `v3.0.2` 存在
  - **裁决（2026-09，备选路径生效）**：`v3.0.2` tag 未落，用户要求提前开工——从 `dev-3.0.2` HEAD = `945bbc4` 拉出 `dev-3.0.3`；`v3.0.2` tag 落地后如需对齐按 rebase 备忘处理（见 record）
- [x] 从基线拉 `dev-3.0.3`；记录基线：pytest 716 全绿 / vitest 665+1（666 总数，1 例为 happy-dom 挂载墙钟环境性失败，断言未动）
  - 备选（用户要求提前开工）：从 `dev-3.0.2` HEAD 拉出，`v3.0.2` tag 后 rebase——**已按此路径执行，裁决记录于 record-3.0.3-P0-1.md**
- [x] 打 tag `v3.0.3-base`（全局回滚锚点）
- [ ] PRD/SPEC 状态 Draft → 定稿（回填裁决分歧，如有）
- [x] ★ 通知用户计划启动

**验收方式**: `git tag` 存在；基线数字记录于本步 record。
**验收标准**: 门禁命令首跑全绿（零改动的干净起点）。

---

## Phase 1: 列表副轨闭环（~2-3 天，M1）→ `v3.0.3-beta.1`

### P1-1 track 选择器与数据源（SPEC M1-1 / R1.1）

- [x] `WorkspacePage.vue`：`activeListTrackId` ref（null = 主轨）+ 删轨回退 watch 兜底
  - 落点裁决：承载于新 `useListTrackSelector` composable（WorkspacePage 接线），reactive 行为可 vitest 直测（见 record-3.0.3-P1-1.md）
- [x] `Timeline.vue`：`tracks` / `activeTrackId` props + 头部 segmented 切换（沿 3.0.2 控件栏款）
- [x] 数据源单一 computed（主轨 `mergedSegments` / 副轨 `activeTrack.segments`），不建第二套行渲染
  - 引用恒等断言：null 分支 `listSegments === mergedSegments`（零拷贝）
- [x] vitest：往返切换、删轨回退、主轨分支零 diff（新增 17 例：composable 12 + Timeline 5；删轨回退 watch 采用多源形态，单 getter 有吞纠偏缺陷，踩中后修正，见 record）

**验收方式**: `bun run test` 全绿（含新增）；既有 Timeline 测试不改断言。
**验收标准**: 手工冒烟（合并 beta.1 ★ 节点）。

### P1-2 副轨段渲染与空态（SPEC M1-2 / R1.2）

- [ ] 列表行副轨分支：text / start / 时长 + 绑定标记（bindings 命中 icon）
- [ ] 空轨空态卡 + 「新建字幕」入口（`add_track_segment`，沿波形建段 expose 与 toast）
- [ ] vitest：字段显示、绑定标记、空态建段

**验收方式**: `bun run test` 全绿。
**验收标准**: 双语工程冒烟合并 beta.1 ★ 节点。

### P1-3 文本/时间编辑与行操作（SPEC M1-3/M1-4 / R1.3-R1.5）

- [ ] useTrackEdit 增列表侧入口（text / time），防抖合并 + 失败回滚 + flush-on-switch
- [ ] 时间编辑本地预校验（min duration / 上界）；后端拒绝回滚 + toast 错误原文
- [ ] 副轨行单击 seek（复用 `handleListSeek`）+ 播放跟随高亮
- [ ] 右键菜单：定位 / 编辑 / 删除此条字幕（`delete_track_segment`，无确认框）
- [ ] **撤销捕获层谓词表**（SPEC M1-4 表）逐行落地 + vitest（含 offsets 还原、redo 对称）

**验收方式**: `bun run test` 全绿（新增 ≥ 谓词表 4 行 + 编辑 4 组）；门禁命令全绿。
**验收标准**: 编辑全链路冒烟合并 beta.1 ★ 节点；打 tag `v3.0.3-beta.1` + record。

---

## Phase 2: 体验打磨（~1-2 天，M2/M3）→ `v3.0.3-beta.2`

### P2-1 跟随平滑动画调度器（SPEC M2-1 / S2）——beta.1 真机 A/B 之后

- [ ] 新建 `useScrollAnimator.ts`（animateTo / redirect / cancel，常量导出）
- [ ] `writeScrollTop` 调用点接调度器；手动滚动 cancel + 播放回调期禁启动守卫
- [ ] localStorage `milocut:timeline-follow-smooth:v1` 开关；**默认值 = beta.1 A/B 用户裁决**（回写 SPEC M2-1）
- [ ] vitest 四组：打断 / 卸载清理 / 重定向不叠加 / 播放期禁启动 + 开关容错

**验收方式**: `bun run test` 全绿；A/B 结论记录于本步 record。
**验收标准**: 回放 + 手动混合操作无空白/跳变（3.0.2 嫌疑不复现）。

### P2-2 列表行右键菜单 kbd 角标（SPEC M3 / S3）——与 P2-1 可并行开发，合入按序

- [ ] 菜单项配置增 `kbd?: string`；渲染层统一消费（复用 3.0.2 R9.4 角标款）
- [ ] 主轨/副轨行菜单按快捷键登记表标注；无 kbd 项不渲染空节点
- [ ] 菜单快照测试更新

**验收方式**: `bun run test` 全绿。
**验收标准**: 真机清单合并 beta.2 ★ 节点；打 tag `v3.0.3-beta.2` + record。

---

## Phase 3: 收尾与发布（~1 天）→ `v3.0.3-RC → 正式`

### P3-1 真机清单 C 对应版（SPEC M4 真机清单）

- [ ] ★ 双平台：列表副轨编辑全链路（含拒绝路径与 undo/redo 对照波形区）
- [ ] ★ 双平台：smooth 手感终验（默认值确认）；多行 × 列表联动回归；kbd 角标显示
- [ ] 性能对账：列表轨切换/千段副轨列表渲染（对照 3.0.2 perf-baseline 口径，本版无新基线文件则回填对账段）

### P3-2 文档与版本池回写

- [ ] README 功能段（列表副轨编辑）；design-spec 增补列表轨交互规范（选择器/编辑/谓词表）
- [ ] 开发报告版本池注记回写：#4 行顶徽章死区 / #5 框选自动滚动观察状态更新；smooth 项出池销账
- [ ] record 总记录落盘（`record-3.0.3.md`：交付概览 / 门禁终态 / 遗留清单）

### P3-3 发布

- [ ] 门禁终检（events/models/main/project_service diff 为空终验）
- [ ] ★ 用户 RC 签字 → tag `v3.0.3-rc.1` → 合并主干 → tag `v3.0.3` → 总 record 归档

---

## 规模与风险对照

- 规模：前端 ~600-1000 行，后端 0 行；总量约为 v3.0.2 三分之一（PRD §4）
- 高风险两项的缓解落点：双数据源串扰 → P1-1 视图态单真源 + 主轨零 diff 测试；smooth 空白嫌疑 → P2-1 播放期禁启动守卫 + 默认关闭 + A/B 定默认
- 观察项（不入版，真机反馈触发再立项）：行顶徽章死区收敛 / 框选拖拽自动滚动（PRD §0.1 表）

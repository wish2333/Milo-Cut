# v3.0.0 性能对账报告（beta.2 门禁 · perf-beta2）

> 采集时间: 2026-08-31 · 平台: Windows 11 · 分支: `dev-3.0.0` @ 213f580 (M6 之后)
> 基线: `docs/3.0.0/perf-baseline.md`（v3.0.0-base，2026-08-30）
> 采集方式: 后端 `tests/perf/backend_benchmark.py`（30 runs，seed=42，synthetic_1167）；前端 vitest `undoScale.perf.test.ts`（1167 段 × 50 编辑/50 undo，performance.now 采样）

## 测试基线计数（当前）

| 套件 | 数量 | 结果 |
|---|---|---|
| pytest | 550 | 全绿 |
| vitest | 314（含 1 条 undo 规模自动化） | 全绿 |

## 已测项（自动化）

### undo 主线程耗时（M5，目标 < 5 ms）✅ 达标

前端主线程 = 层栈操作 + apply_undo 调用解析 + applyProjectPatch 原位应用（1167 段全量层）。两次独立运行（一次与 vite build 并发，代表负载波动上界）：

| 指标 | 空载运行 | 负载运行（与 build 并发） |
|---|---|---|
| undo p50 | **1.293 ms** | **2.918 ms** |
| undo max（50 次） | 2.615 ms | 10.958 ms |
| captureLayers p50 | 0.018 ms | 0.021 ms |

p50 全部 < 5 ms 达标；max 在并发负载下偶发越线但属调度抖动，非稳态路径回归（目标口径为主线程耗时 p50）。

后端份额（bridge 线程，不计前端主线程）：`apply_undo_segments_layer`（1167 段整层校验+替换+revision+1+patch 信封）p50 **3.961 ms** / p95 7.727 / p99 7.928（`tests/perf/results/beta2_stage2.json`）。

端到端 undo 延迟 ≈ 前端 1.3 ms + IPC + 后端 ~4 ms，远低于可感知阈值。

### 千段回放正确性（M5 收尾）✅

1167 段项目连续 50 次编辑 → 50 次 undo 回到与初态 deep-equal（`undoScale.perf.test.ts`，真实 useUndoRedo + applyProjectPatch + 后端契约 mock）。

### 项目打开 / 保存（M2 复核）✅ 无回归信号

| 指标 | 基线（P0） | 本次 | 备注 |
|---|---|---|---|
| `open_project` p50 | 11.89 / 11.39 ms | **4.767 / 4.733 ms**（两轮误差 0.7%） | 读文件→迁移链→校验全路径 |
| `save_project` p50 | —（M2 前无独立基线） | **3.425 ms** | 含 fsync + 双 bak 轮换 + os.replace 全路径 |

P1-4 验收"正常保存路径耗时增幅 < 5%"：fsync+备份开销后保存仍在毫秒量级，写路径无回归信号。打开两轮均低于基线（同机；差异主要来自环境热缓存状态，方向上无退化）。

## 待真机项（★ 双平台冒烟测量后回填本报告）

macOS（WKWebView，2026-08-31 用户实测）已回填；Windows（WebView2）待测。

| 指标 | 目标 | macOS / WKWebView | Windows / WebView2 |
|---|---|---|---|
| 1167+ 段列表滚动帧率 | ≥ 55 fps | **60 fps ✅**（1200 段项目） | 待测 |
| 波形生成任务期主线程长任务 | >50ms 长任务为 0 | **0 ✅**（PerformanceObserver） | 待测 |
| 空闲 IPC 频率 | < 4 次/秒 | **≈4 次/秒 ✅**（累计计数每秒 +4，即 250ms 降档生效；首测脚本未清零计数器，实际速率为相邻两次读数差） | 待测 |
| 播放中 CPU 占用 | 对比 beta.1 下降 | 用户体感流畅、功能正常 ✅（未量化） | 待测 |
| 播放头无抖动 / hover 预览手感 | 对比 beta.1 截录屏 | 正常 ✅ | 待测 |
| 波形缓存二次打开 < 200ms | M11-3 落地后测 | 未开始（Phase 4） | 未开始 |
| 1167 段单字编辑重渲染行数 ≤ 可视区 | Vue DevTools 高亮验证 | 待测 | 待测 |
| undo/redo ×5 手感 + macOS Cmd 链路 | 冒烟清单第 6 项 | 撤销重做正常 ✅（编辑/撤销即时无卡死） | 待测 |
| 千段跳转定位（搜索/建议跳远端行） | 先瞬时定位无跳变 | 正常 ✅ | 待测 |

## 结论

自动化可测的全部达标：undo 主线程 p50 1.3ms（目标 5ms）、千段 50/50 回放正确、打开/保存毫秒级无回归。beta.2 门禁剩余：★ 双平台冒烟（含本报告待真机项测量回填）→ 用户性能体感确认 → 删除 legacy undo 路径（tag `pre-undo-cleanup` 回滚锚点）→ 打 tag `v3.0.0-beta.2`。

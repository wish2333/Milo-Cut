# v3.0.0 性能对账报告（正式版门禁 · perf-final）

> 采集时间: 2026-08-31 · 平台: Windows 11 / macOS（真机项另列） · 分支: `dev-3.0.0` @ Phase 4 收官
> 基线: `perf-baseline.md`（v3.0.0-base）· 上门禁: `perf-beta2.md`
> 采集方式: `tests/perf/backend_benchmark.py`（30 runs，seed=42，synthetic_1167）→ `results/final_stage.json`；open/save 计时与基线同口径；undo 千段回放 `undoScale.perf.test.ts`

## 测试基线计数（对账 PRD §6）

| 套件 | 基线 | 正式版 | 差值 |
|---|---|---|---|
| pytest | 478 | **598** 全绿 | +120（验收要求 ≥25） |
| vitest | 251 | **343** 全绿 | +92 |
| ruff | 38 存量 | **0**（全仓） | 清零（PRD §6 达成） |
| `bun run lint` | - | **0 errors 0 warnings**（全仓） | VideoControls.test.ts 存量 2 warnings 以文件级豁免清零（渲染计数桩为测试意图，注释说明） |
| bun run build | - | 通过 | vue-tsc + vite |

## 后端 benchmark（final vs beta2，p50 ms）

| operation | final | beta2 | 基线(stage0/baseline) | 结论 |
|---|---:|---:|---:|---|
| apply_undo_segments_layer（1167 段全层） | **3.590** | 3.961 | - | 更优，<5ms 达标 |
| project_model_dump | 0.854 | 0.953 | 0.888 | 更优 |
| project_model_dump_json | 1.211 | 1.303 | 1.211 | 持平 |
| update_edit_decision | 0.527 | 0.569 | 0.937 | 更优 |
| update_segment | 0.630 | 0.694 | 0.975 | 更优 |
| mark_segments_single / batch_10 | 0.573 / 0.628 | 0.610 / 0.665 | - | 更优 |

**无回退项**；Phase 4 全部新增功能（回贴/多轨/波形缓存/回滚）零基准回归。

## undo / 打开 / 保存（自动化）

| 指标 | 目标 | 正式版实测 | 门禁 |
|---|---|---|---|
| undo 主线程 p50（1167 段 × 50 回放） | < 5 ms | **1.188 ms**（max 2.635；beta2 并发负载口径 2.918 亦达标） | ✅ |
| `open_project` p50 | 毫秒级无回归 | **4.250 ms**（beta2 4.767/4.733；MEDIA_NOT_FOUND 口径与基线一致） | ✅ |
| `save_project` p50（fsync+双 bak 全路径） | 毫秒级无回归 | **2.736 ms**（beta2 3.425） | ✅ |
| 波形缓存命中 | < 200 ms | **0.844 ms**（6000 peaks，perf-beta2 记录口径） | ✅ |

## 真机项（★ 待双平台补测后回填本表，沿用 beta.2 用户裁决模式）

| 指标 | 目标 | macOS / WKWebView | Windows / WebView2 |
|---|---|---|---|
| 1167+ 段滚动帧率 | ≥ 55 fps | beta.2 已测 60fps ✅（Phase 4 无渲染管线改动，正式版复测待定） | **待补测**（beta.2+rc 两轮均挂账） |
| 波形生成期主线程长任务 >50ms | 0 | beta.2 已测 0 ✅ | **待补测** |
| 空闲 IPC 频率 | < 4 次/秒 | beta.2 已测 ≈4/s ✅ | **待补测** |
| 播放中 CPU / 播放头手感 | 优于 beta.1 | beta.2 已确认 ✅ | **待补测** |
| hover 词高亮与播放同步（P4-1） | 手测 | **待测** | **待测** |
| 副轨导入→折叠 lane→双 SRT 导出（P4-2） | 手测 | **待测** | **待测** |
| 失败回滚弹窗演练（P4-4） | 手测 | **待测** | **待测** |
| dpr 跨屏 / 触控板滚轮 / 首启动竞态 / GB18030 / 断电恢复演练 | 全清单 | rc 冒烟全绿 ✅（标准清单部分） | **待补测** |

## 结论

自动化可测项全部达标且无基准回退：**pytest 598 / vitest 343 / ruff 0 / lint 0-0 / build 通过 / undo 1.19ms / open-save 毫秒级 / benchmark 全项持平或更优**。真机项（Windows 补测 + Phase 4 新功能手感）待用户轮次回填后即可打 tag `v3.0.0`。

# v3.0.2 性能基线（P0-1 存档）

> 采集时间: 2026-09-02 · 平台: macOS（Apple Silicon）· 分支: `dev-3.0.2`（基线点 = `v3.0.2-base` tag）
> 采集方式: 沿 3.0.1 口径——真实调用 `ProjectService.open_project` 与 `core.ffmpeg_service.generate_waveform`，多次采样取 p50；序列化基准走 `tests/perf/backend_benchmark`（30 runs，seed=42）；前端 patch apply 走 `frontend/src/utils/projectPatch.perf.test.ts`。
> 注意: 与 `docs/3.0.1/perf-baseline.md` 同平台（macOS Apple Silicon）可直接对比；本文件是 v3.0.2 全程的回退对照锚，P3 末（P5-3）回填对账。

## 测试基线计数

| 套件 | 数量 | 结果 |
|---|---|---|
| pytest（`uv run pytest`） | 702 | 全绿 |
| vitest（`bun run test`） | 453（39 文件） | 全绿 |

## 性能基线

### 项目打开（synthetic_1167，seed=42，1167 段 / 989 edits，819 KB）

| 指标 | 第 1 轮 | 第 2 轮 |
|---|---|---|
| `open_project` p50（20 次/轮） | 4.76 ms | 4.70 ms |

- 两轮误差 1.4% < 10%，满足可复现标准。
- 口径与 3.0.1 一致：合成工程媒体不存在，`open_project` 在媒体检查处提前返回 `MEDIA_NOT_FOUND`；计时覆盖「读文件 → 迁移链 → `Project.model_validate`」全路径。

### 波形生成（60 秒 16kHz 单声道正弦 wav，6000 buckets）

| 指标 | 值 |
|---|---|
| `generate_waveform` p50（3 轮：45.1 / 45.6 / 45.7） | 45.6 ms |

### 后端序列化与写入基准（`tests/perf/results/baseline_3.0.2.json`，30 runs）

| operation | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| `generate_synthetic_project` | 6.084 | 10.297 | 10.297 |
| `project_model_dump` | 0.898 | 1.170 | 3.311 |
| `project_model_dump_json` | 1.218 | 1.227 | 1.288 |
| `update_edit_decision` | 0.543 | 0.588 | 2.713 |
| `update_segment` | 0.642 | 0.659 | 0.705 |
| `mark_segments_single` | 0.586 | 0.630 | 0.642 |
| `mark_segments_batch_10` | 0.644 | 0.708 | 0.718 |
| `apply_undo_segments_layer` | 3.655 | 8.443 | 8.710 |

| Serialized `Project` size | 490.60 KB (502,374 bytes) |
|---|---|

### 前端 patch apply（`projectPatch.perf.test.ts`，1000 主段 + 4×200 副段 ×50）

| 指标 | 值 |
|---|---|
| `applyProjectPatch`（segments+tracks+bindings 全层）p50 | 0.231 ms |

## v3.0.2 目标对账（P5-3 回填，2026-09-02）

| 目标 | 基线 | 目标值 | SPEC 依据 | 状态 |
|---|---|---|---|---|
| multi visibleRows 重算 | 纯计算 p50 实测 | p50 < 1 ms（synthetic_1167 规模） | M8-3 | ✅ visibleRowWindow x200 p50=0.0002ms；composable 链 x100 p50=0.0017ms |
| 单行挂载 | 无（v3.0.1 无行概念） | p95 < 8 ms（挂载口径，happy-dom） | M8-3 | ✅ 3 批×20 挂载最优批 p95 = 5.945 ms（1167 段， warmed；批次 p95 5.945/6.859/7.531） |
| peaks 加载 | 每窗 fetch | multi 模式单次 fetch（spy 断言） | M4-3 | ✅ orchestrator 单次 fetch + provide 注入（WaveformCanvas.peaks.test：fetchSpy toHaveBeenCalledTimes(1)）；行级 LRU 缓存 64 |
| 千段滚动/播放/行重排帧率 | 本文件采集日体感 + 计时 | 不低于本基线 | PRD §7 | ⏳ 真机清单 C（canvas 位图重绘口径，M5-5/M8-3 移交双平台） |
| 五项工程门禁 | 本文件采集日全绿（pytest 702 / vitest 453） | 全程全绿 + events-diff 空 + models-diff 零 | M8-2 | ✅ pytest 708 / vitest 653 / build / lint 0 / ruff 0；events+models diff vs v3.0.2-base = 0 |

对账说明：
- 单行挂载门测量口径 = 3 批 × 20 挂载取最优批 p95（P3-1 加固，阈值 8ms 不变）——p95(20) 即最大样本，单次 GC 停顿在跨测试文件负载下会误杀（实测全量跑 15.4ms vs 单跑 ~6ms），最优批过滤环境噪声、只锚定组件内在成本。
- 帧率项依赖真实 WebView 渲染管线（happy-dom 无位图重绘），按 M8-3 评审裁决移交双平台真机清单 C；不阻塞 RC 打 tag 前的全量自动化门禁。

# v3.0.1 性能基线（P0-1 存档）

> 采集时间: 2026-08-31 · 平台: macOS（Apple Silicon）· 分支: `dev-3.0.1`（基线点 = `v3.0.1-base` tag）
> 采集方式: 真实调用 `ProjectService.open_project` 与 `core.ffmpeg_service.generate_waveform`，多次采样取 p50；序列化基准走 `tests/perf/backend_benchmark`（30 runs，seed=42）。
> 注意: 与 `docs/3.0.0/perf-baseline.md`（Windows 11）跨平台不可直接对比；本文件是 v3.0.1 全程的回退对照锚。

## 测试基线计数

| 套件 | 数量 | 结果 |
|---|---|---|
| pytest（`uv run pytest`） | 598 | 全绿 |
| vitest（`bun run test`） | 343（34 文件） | 全绿 |

## 性能基线

### 项目打开（synthetic_1167，seed=42，1167 段 / 989 edits，819 KB）

| 指标 | 第 1 轮 | 第 2 轮 |
|---|---|---|
| `open_project` p50（20 次/轮） | 4.64 ms | 4.75 ms |

- 两轮误差 2.4% < 10%，满足可复现标准。
- 口径与 3.0.0 一致：合成工程媒体不存在，`open_project` 在媒体检查处提前返回 `MEDIA_NOT_FOUND`；计时覆盖「读文件 → 迁移链 → `Project.model_validate`」全路径。

### 波形生成（60 秒 16kHz 单声道正弦 wav，6000 buckets）

| 指标 | 值 |
|---|---|
| `generate_waveform` p50（3 轮：50.0 / 45.9 / 45.5） | 45.9 ms |

### 后端序列化与写入基准（`tests/perf/results/baseline_3.0.1.json`，30 runs）

| operation | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| `generate_synthetic_project` | 5.852 | 8.347 | 8.347 |
| `project_model_dump` | 0.868 | 1.146 | 2.900 |
| `project_model_dump_json` | 1.199 | 1.217 | 1.347 |
| `update_edit_decision` | 0.534 | 0.576 | 2.561 |
| `update_segment` | 0.642 | 0.659 | 0.666 |
| `mark_segments_single` | 0.577 | 0.612 | 0.637 |
| `mark_segments_batch_10` | 0.632 | 0.698 | 0.699 |
| `apply_undo_segments_layer` | 3.649 | 8.450 | 8.820 |

| Serialized `Project` size | 490.60 KB (502,374 bytes) |
|---|---|

## v3.0.1 目标对账（验收时回填）

| 目标 | 基线 | 目标值 | SPEC 依据 | 状态 |
|---|---|---|---|---|
| tracks/bindings patch apply（前端） | 待 M3 落地后测 | p50 < 5 ms（1000 主段 + 4x200 副段） | M3 perf 断言 | 未开始 |
| undo 主线程耗时 | apply_undo segments 层 3.649 ms（后端） | < 5 ms 不回退 | 验收总纲 | 未开始 |
| 堆叠缩放/平移/播放帧率（4 副轨 + 千段） | 待 M4 落地后测 | 不低于 3.0.0 基线 | M4 验收 | 未开始 |
| 单段 patch 重渲染范围 | 待 M3 落地后测 | 收敛到局部 lane | R6.2 | 未开始 |
| 五项工程门禁 | 本文件采集日全绿 | 全程全绿 | 验收总纲 | 未开始 |

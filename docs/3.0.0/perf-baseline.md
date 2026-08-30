# v3.0.0 性能基线（P0-1 存档）

> 采集时间: 2026-08-30 · 平台: Windows 11 · 分支: `dev-3.0.0`（基线点 = `v3.0.0-base` tag）
> 采集方式: 真实调用 `ProjectService.open_project` 与 `core.ffmpeg_service.generate_waveform`，多次采样取 p50。

## 测试基线计数

| 套件 | 数量 | 结果 |
|---|---|---|
| pytest（`uv run pytest`） | 478 | 全绿 |
| vitest（`bun run test`） | 251（22 文件） | 全绿 |

> 注：计划文档中记录的 vitest 基线为 241，实测为 251（以本文件为准）。

## 性能基线

### 项目打开（synthetic_1167，seed=42，1167 段 / 989 edits，824 KB）

| 指标 | 第 1 轮 | 第 2 轮 |
|---|---|---|
| `open_project` p50 | 11.89 ms | 11.39 ms |

- 两轮误差 ≈ 4.2% < 10%，满足可复现标准。
- 说明: 合成工程媒体文件不存在，`open_project` 在媒体检查处提前返回 `MEDIA_NOT_FOUND`；计时覆盖「读文件 → 迁移链 → `Project.model_validate`」全路径，与后续对比口径一致。

### 波形生成（60 秒 16kHz 单声道正弦 wav，6000 buckets）

| 指标 | 值 |
|---|---|
| `generate_waveform` p50（3 轮） | 120.2 ms |

### 既有后端序列化基线（沿用 v2.3.2，`tests/perf/results/baseline_stage0.json`）

| operation | p50 (ms) |
|---|---:|
| `Project.model_dump()` | 0.888 |
| `Project.model_dump_json()` | 1.211 |
| `update_edit_decision` | 0.937 |
| `update_segment` | 0.975 |

## v3.0.0 目标对账（验收时回填）

| 目标 | 基线 | 目标值 | 状态 |
|---|---|---|---|
| undo 主线程耗时 | 待 M5 落地后测 | < 5 ms | 未开始 |
| 1167 段滚动帧率 | 待 M7 落地后测 | ≥ 55 fps | 未开始 |
| 波形生成期主线程长任务 | 待 M4 落地后测 | 无 >50ms | 未开始 |
| 空闲 IPC 频率 | 待 M4 落地后测 | < 4 次/秒 | 未开始 |
| 波形缓存二次打开 | 待 M11-3 落地后测 | < 200 ms | 未开始 |

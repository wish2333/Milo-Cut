# Record: P0-1 分支与基线快照（Phase 0）

> 日期: 2026-08-31 · 分支: `dev-3.0.1`（自 `spec/v3.0.1-stacked-timeline` @ 847b42c 拉出）· tag: `v3.0.1-base`

## 完成内容

- 规划文档入库: `docs/3.0.1/` 三件套（PRD / SPEC / PLAN，commit 847b42c）+ `.gitignore` 忽略 `_competitor/`、解除 `/test/`
- 基线计数: pytest **598** 全绿；vitest **343**（34 文件）全绿
- perf 基线存档 `docs/3.0.1/perf-baseline.md`:
  - `open_project`(synthetic_1167) p50 ≈ 4.64 / 4.75 ms（两轮误差 2.4% < 10%，可复现）
  - `generate_waveform`(60s tone, 6000 buckets) p50 ≈ 45.9 ms
  - 序列化基准 30 runs 存 `tests/perf/results/baseline_3.0.1.json`（`update_segment` 0.642 ms / `apply_undo_segments_layer` 3.649 ms / Project 490.6 KB）
- tag `v3.0.1-base` 已打（全局回滚锚点）
- 采集产物: `data/perf/synthetic_1167.json`（seed=42）、`data/perf/perf_60s.wav`（不入库，data/ 已忽略）

## 验证命令与实际输出

```
uv run pytest                      -> 598 passed in 5.02s（exit 0）
cd frontend && bun run test        -> Test Files 34 passed, Tests 343 passed
backend_benchmark --runs 30        -> 表见 perf-baseline.md（exit 0）
git tag v3.0.1-base                -> 存在
```

## 与 3.0.0 基线的差异说明

- 平台不同（macOS Apple Silicon vs Windows 11）：`open_project` 11.9 -> 4.6 ms、`generate_waveform` 120.2 -> 45.9 ms 的变化主要是跨平台差异，**不作为改进证据**；v3.0.1 内部对比一律以本文件为锚。

## 未验证边界 / 待用户协助

- ★ 副轨测试素材（对齐的外语 SRT + 故意错位 SRT）待提供（P1-1 前不阻塞，Phase 3 验收前需到位；不就位则先用合成 SRT）
- ★ Windows WebView2 侧冒烟（beta.1 起，每批次末）

# Record: P0 开工准备（Phase 0）

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · tag: `v3.0.0-base`

## 完成内容

### P0-1 分支与基线快照

- 从 `origin/main`（3faacfa，v2.4.0）创建并切换到 `dev-3.0.0`
- 规划文档入库: `docs/3.0.0/`（PRD/SPEC/风险评审/PLAN）+ `docs/competitor/` 报告 v1/v2（commit e1cc4d6）
- 基线计数: pytest **478** 全绿；vitest **251**（22 文件）全绿（计划文档原记 241，以实测为准）
- perf 基线存档 `docs/3.0.0/perf-baseline.md`:
  - `open_project`(synthetic_1167) p50 ≈ 11.9 / 11.4 ms（两轮误差 4.2% < 10%，可复现）
  - `generate_waveform`(60s tone, 6000 buckets) p50 ≈ 120.2 ms
- tag `v3.0.0-base` 已打（全局回滚锚点）

### P0-2 迁移清单

- `docs/3.0.0/migration-M5.md`: pushSnapshot 调用点共 **24 处**
  - WorkspacePage 直接 3 处（:940 / :1124 / :1427）
  - useEdit 内部 12 处、useAnalysis 内部 6 处、useSegmentEdit 内部 3 处（经 `onBeforeProjectUpdate` 注入参数间接调用）
  - 每点标注"待替换层组合"；发现 :1124 存量 bug（push 的是操作后状态）
- `docs/3.0.0/migration-M8.md`: 3 popover（:1732 / :1883 / :1994 模板块）+ useAsrEngines 域（约 L247-700）+ 40+ handler 按五组归口清单
- 交叉核对: `handle[A-Z]` grep 与清单一致，零遗漏

## 验证命令与实际输出

```
uv run pytest            -> 478 passed（72*6+46 dots，exit 0）
bun run test             -> Test Files 22 passed, Tests 251 passed
git tag v3.0.0-base      -> 存在
```

## 未验证边界 / 待用户协助

- ★ macOS（Apple Silicon）真机可用性待确认（影响 P2-2 WKWebView 回归、P2-4 双平台 fps 实测）
- ★ ≥60 分钟真实口播视频待提供（P1-1 words 保真实测）
- ★ DeepSeek/Qwen API Key 待确认（P1-5 LLM 真实链路验证；无则用 mock）

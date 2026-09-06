# v3.0.3 P0-1 记录：分支与基线快照

> 日期：2026-09　分支：`dev-3.0.3`　基准：`v3.0.3-base` tag

## 裁决记录（开工前置备选路径）

- `v3.0.2` 正式 tag **未落地**（清单 C 双平台签字未完成）。按 PLAN P0-1 备选路径开工：
  - 从 `dev-3.0.2` HEAD = `945bbc4`（含 v3.0.3 PRD/SPEC/PLAN 骨架提交）拉出 `dev-3.0.3`；
  - 打 tag `v3.0.3-base`（全局回滚锚点）；
  - **备忘**：`v3.0.2` tag 落地后，本分支首三个文档提交（`945bbc4` 之前部分）无需 rebase——`dev-3.0.3` 基于 `dev-3.0.2` HEAD 线性生长，`v3.0.2` tag 应落在这条线的 `d441bda`（或含后续文档提交），届时确认无分叉即可。

## 门禁基线（v3.0.3-base 首跑，零改动干净起点）

| 命令 | 预期 | 实际 | 结果 |
|---|---|---|---|
| `uv run pytest` | ≥716 全绿 | **716 passed** in 6.27s | PASS |
| frontend vitest | ≥666 全绿 | **665 passed / 1 failed**（666 总数） | 见下方环境差异 |
| `vue-tsc --noEmit` + `vite build` | 0 错误 | built in 3.28s，0 错误 | PASS |
| eslint | 0 errors 0 warnings | 0 | PASS |
| `uv run ruff check .` | 0 问题 | All checks passed! | PASS |

## 环境差异登记（不改断言）

`src/composables/useRowLayout.perf.test.ts`「single WaveformRow mount stays under 8ms p95」在本机失败：三批 20 次挂载最优批 p95 ≈ **18.08ms**（阈值 8ms，happy-dom 挂载墙钟成本）。该用例为墙钟性能门，3.0.2 record 记录当时开发机 ~5.9ms；本机（虚拟化 Linux 环境）happy-dom 挂载成本系统性偏高，**断言未改动、门不放宽**，以"基线即含此 1 例环境性失败"为准入口径：后续每步门禁要求失败集合**不扩大**（其余 665 例 + 新增用例全绿）。真机性能对账由 P3-1 真机清单覆盖（3.0.2 同款裁决：happy-dom 无位图重绘，挂载墙钟不代表真机）。

## 环境工具链差异登记（命令等价替换）

- `uv` 不在 PATH：经 `pip3 install --user --break-system-packages uv` 装至 `~/.local/bin/uv`（0.12.9），`uv run` 自动建 `.venv` 并装齐依赖。
- `bun` 位于 `/var/apps/bunjs/target/bin/bun`（1.3.9）；**bun 在含 `@` 的路径下 `bun run` 触发 `CouldntReadCurrentDirectory`**（已隔离验证：/tmp 正常、@ 路径必现，symlink 规避无效）。等价替换：`bun run test` → `./node_modules/.bin/vitest run`；`bun run build` → `./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vite build`；`bun run lint` → `./node_modules/.bin/eslint .`（bun run 仅作脚本转发，二进制与参数一一对应）。

## 改动文件清单

- 新建 `dev-3.0.3` 分支（自 `945bbc4`）、tag `v3.0.3-base`
- 新建 `docs/3.0.3/record-3.0.3-P0-1.md`（本文件）
- PLAN `P0-1` 勾销

## 未验证边界

- 双平台真机验证不在本步范围（P3-1 清单）。
- `v3.0.2` tag 落地时机由用户掌控（清单 C 签字）。

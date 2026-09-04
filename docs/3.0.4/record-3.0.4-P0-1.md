# record-3.0.4-P0-1：分支、tag 与基线快照（含文档入库）

> 日期：2026-09（D0）　执行：v3.0.4 团队（编排者代行 PM/执行）
> 对应 PLAN：Phase 0 / P0-1

## 1. 分支与 tag

| 项 | 值 |
|---|---|
| 拉出点 | tag `v3.0.3` = `55c68da5e273ea9df6b7994f49ff86cf4e3934a1`（= dev-3.0.3 HEAD，含修订-1 追补） |
| 新分支 | `dev-3.0.4`（自 `v3.0.3` 拉出） |
| 回滚锚点 | tag `v3.0.4-base` 打在拉出点（`55c68da`），**先于**文档入库——纯代码回滚点 |
| 门禁 diff 基准 | 恒为 `v3.0.3`（不受文档入库影响） |

```
git checkout -b dev-3.0.4 v3.0.3 && git tag v3.0.4-base
```

## 2. 文档入库

- commit `83a61d6` `docs(3.0.4): v3.0.4 立项文档入库 -- 探索报告/PRD/SPEC/PLAN/评审日志`
- `docs/3.0.4/` 五文件：探索报告(488 行) / PRD(374 行) / SPEC(530 行) / PLAN(444 行) / review-log(60 行，PLAN 四文档之外的评审留痕，随同入库)
- 总记录骨架 `docs/3.0.4/record-3.0.4.md` 建立（含后端改动登记表总表，SPEC 附录 A 模板；本文件为 P0-1 分步记录）

## 3. 门禁基线首跑登记（零改动干净起点）

| 项 | 期望（SPEC M5） | 实际 | 判定 |
|---|---|---|---|
| `uv run pytest` | 716 passed 全绿 | **exit 0 + `--collect-only` 计 716**（42 个测试文件求和=716；pytest 9 于本环境不打印汇总行，以 exit code + collected 双证全绿） | ✅ |
| `bun run test`（vitest） | 756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts） | **756 collected / 755 passed / 1 failed**；失败项 = `useRowLayout.perf.test.ts > single WaveformRow mount stays under 8ms p95`（实测 19.8ms，挂载墙钟，record-3.0.3 已登记环境例） | ✅ |
| `bun run build`（vue-tsc --noEmit + vite build） | 通过 | vue-tsc 0 错误；vite build 成功（3.08s，产物 frontend_dist/） | ✅ |
| `bun run lint`（eslint .） | 0 errors 0 warnings | exit 0，无任何输出 | ✅ |
| `uv run ruff check .` | 0 problems | `All checks passed!` | ✅ |

### 红线命令首跑（期望全部空/零——常量未加，P1-1 起按期望输出核对）

| 红线 | 命令 | 实际输出 | 判定 |
|---|---|---|---|
| R0-1 白名单 | `git diff v3.0.3 --name-only -- core/ main.py` | 空 | ✅ |
| R0-1 禁改面 | `git diff v3.0.3 --name-only -- pywebvue/ core/task_manager.py … core/migrations.py` | 空 | ✅ |
| R0-2 events py | `git diff v3.0.3 -- core/events.py \| grep -E '^\+.*(LLM_TRANSLATION_COMPLETED\|llm:translation_completed)'` | 空 | ✅ |
| R0-2 events ts | 同款 events.ts 侧 | 空 | ✅ |
| R0-3 后端断言 | `git diff v3.0.3 -- tests/ \| grep -cE '^-[[:space:]]*(assert \|self\.assert)'` | 0 | ✅ |
| R0-3 前端断言 | `git diff v3.0.3 -- frontend/src \| grep -E '^-[[:space:]]*expect\(' \| grep -v 'TranscriptRow.test.ts' \| wc -l` | 0 | ✅ |
| R0-4 models 专项 | `git diff v3.0.3 -- core/models.py` | 空 | ✅ |
| R0-5 人工核对 | `git diff v3.0.3 --name-only \| grep -E '^(dev\|build)\.py$'` | 空 | ✅ |

## 4. 执行环境偏差登记

- `bun run` 在本执行环境不可用（bun 1.3.9 内建 script runner 报 `CouldntReadCurrentDirectory`；`--shell=system` 同败；`bun -e` / `Bun.spawnSync` 正常）。前端门禁按 PLAN P0-2 回落条款以 node 直跑等价命令执行：`./node_modules/.bin/vitest run` / `./node_modules/.bin/vue-tsc --noEmit` + `./node_modules/.bin/vite build` / `./node_modules/.bin/eslint .`（package.json scripts 原样拆解，语义一致）。门禁脚本（P0-2）内置「bun 可用优先、否则回落」。
- 环境事实：uv 0.12.9（~/.local/bin）、bun 1.3.9（/var/apps/bunjs/target/bin）、node v24、Python 3.11（.venv 现成）。

## 5. 未验证边界

- 双平台真机（Windows/macOS）验证不在本环境能力内，全部顺延至 beta.1 ★ 起的真机冒烟节点。
- `uv run dev.py` 应用启动冒烟未执行（P0 无前端改动，不阻塞；beta.1 冒烟覆盖）。

## 6. 结论

P0-1 完成：分支/tag/文档入库/record 骨架/基线首跑全绿，红线全部空零。**通知用户：v3.0.4 开发正式启动。**

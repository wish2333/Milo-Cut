# record-3.0.4-P0-2：红线门禁脚本化

> 日期：2026-09（D0）
> 对应 PLAN：Phase 0 / P0-2　commit 类型：`chore(gates)`

## 1. 交付物

- `scripts/gates-v3.0.4.sh`（新增，不在 `core/ main.py` 白名单审查范围，R0-5 不受影响）
- 三段结构：后端门禁 / 前端门禁 / 红线检查（R0-1 ~ R0-5），命令原样封装 SPEC M5 命令块，仅加段落标题与汇总 exit code
- 支持 `all|backend|frontend|redline` 分段执行；汇总 exit 0/1

## 2. SPEC M5 命令封装对照（零改写核验）

| SPEC M5 命令 | 脚本落点 |
|---|---|
| `uv run pytest` | 后端段原样（期望 ≥716 全绿；当期期望总数由 record 登记表承载） |
| `uv run ruff check .` | 后端段原样 |
| `cd frontend && bun run test` | 前端段原样；bun 不可用环境自动回落 `./node_modules/.bin/vitest run`（等价性登记见 P0-1 record §4）；附唯一失败判定 = useRowLayout.perf.test.ts 且 passed = collected - 1 |
| `cd frontend && bun run build` | 前端段原样 / 回落 vue-tsc + vite |
| `cd frontend && bun run lint` | 前端段原样 / 回落 eslint . |
| R0-1 白名单 | 原样命令 + 文件集 ⊆ SPEC M0-1 白名单的自动比对（models/events/config/llm_prompts/llm_service/project_service/correction_service/main.py） |
| R0-1 禁改面 | 原样命令，期望空 |
| R0-2 events 双侧 | 原样两条 grep；口径 = 双侧各恰好 1 行（P1-1 前 0 行亦通过） |
| R0-3 断言零删改 | 原样两条命令；后端期望 0、前端白名单外期望 0 |
| R0-4 models 专项 | 原样 `git diff v3.0.3 -- core/models.py` 输出全文供人工核对 |
| R0-5 diff 审查制 | `git diff v3.0.3 --stat -- core/ main.py` + dev.py/build.py 全量 name-only 人工核对（SPEC 遗漏注记固化进脚本） |

## 3. Dry-run 结果（本执行环境）

- `bash scripts/gates-v3.0.4.sh redline`：红线段全部空/零，exit 0（P0 时点口径）。
- `bash scripts/gates-v3.0.4.sh all`：**三段全过，exit 0**——pytest 716 passed in 5.68s / ruff All checks passed / vitest 756 collected·755 passed（唯一失败判定正确命中 useRowLayout.perf.test.ts）/ build 通过 / lint 0/0 / 红线全空零。stdout 全文见本 record 同目录执行留痕（/tmp/gates-full-dryrun.log 摘录于 git commit 时省略，关键统计行已录）。

## 4. 偏差登记

- **双环境 dry-run 不可行**：本执行环境仅 Linux bash 可用（无 macOS / Windows Git Bash）。按 PLAN「shell 环境受限时回落命令块手动执行 + record 登记」精神，双环境验证顺延至 beta.1 ★ 双平台真机冒烟节点补验；单环境（Linux bash）已验证与手动逐条执行一致。
- bun 回落探测内置（`bun run --version` 探测成功即用 bun run，否则 node 等价命令）；两路径输出形态一致。

## 5. 执行约定（固化）

1. 每 phase 合入前执行 `bash scripts/gates-v3.0.4.sh all` 一次，stdout 全文贴当步 record；
2. SPEC 与脚本冲突以 SPEC 为准，当场修脚本并登记；
3. 脚本失败不得私改脚本放宽判定——先回命令块手动复核，确属脚本 bug 才修脚本 + record 登记。

## 6. 未验证边界

- Windows Git Bash / macOS bash 双环境 dry-run（顺延 beta.1 真机）。
- 脚本对 vitest 统计行的解析依赖 vitest 3 输出格式（`Tests  X failed | Y passed (Z)`）；格式变化时需修脚本（不阻塞：解析失败会显式 FAIL 并提示人工核对，不会假绿）。

## 7. 结论

P0-2 完成：`bash scripts/gates-v3.0.4.sh` = 一条命令执行全部门禁，基线 exit 0。Phase 0 收口，进入 P1。

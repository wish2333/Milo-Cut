# record-3.0.4-P1-1：任务类型与事件常量双侧

> 日期：2026-09（P1）　分支：`dev-3.0.4-p1-1` → 合入 `dev-3.0.4`
> 对应 PLAN：Phase 1 / P1-1　SPEC：M1-1（R1.2/R1.4）

## 1. 改动文件清单（白名单核对）

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `core/models.py` | TaskType 枚举 LLM 区块末尾追加注释 + `LLM_TRANSLATION = "llm_translation"`（仅 2 行，models.py:45 后） | R1.2 | 只增 |
| `core/events.py` | LLM 区块末尾新增 `LLM_TRANSLATION_COMPLETED = "llm:translation_completed"`（1 行 + 注释） | R1.4 | 只增 |
| `frontend/src/utils/events.ts` | 同位置新增 `EVENT_LLM_TRANSLATION_COMPLETED = "llm:translation_completed"`（1 行 + 注释，与 events.py 同一 commit） | R1.4 | 只增 |

`tests/`：本步无新增用例（M5 矩阵「事件双侧登记」以 R0-2 门禁 grep 为判据；expose/事件组用例随 P1-5）。

## 2. 红线命令实际输出

- **R0-4 专项** `git diff v3.0.3 -- core/models.py`：仅含 `+    # v3.0.4 M1: AI translation...` 与 `+    LLM_TRANSLATION = "llm_translation"` 两行（1 枚举成员 + 1 注释），既有字段/签名/默认值/校验器零改动 ✅
- **R0-2 events.py 侧**：恰好命中 1 行 `+LLM_TRANSLATION_COMPLETED = "llm:translation_completed"` ✅（常量名与值均不含连续下划线串 `llm_translation_completed`，must-fix #1 口径）
- **R0-2 events.ts 侧**：恰好命中 1 行 `+export const EVENT_LLM_TRANSLATION_COMPLETED = "llm:translation_completed"` ✅

## 3. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：716 passed in 5.80s（全绿，与基线一致——本步无行为变化）
- ruff：All checks passed
- vitest：756 collected / 755 passed（唯一失败 = useRowLayout.perf.test.ts 环境例，判定正确）
- build（vue-tsc + vite）：通过
- lint：0/0
- R0-1：diff 文件集 = models.py / events.py，均在白名单；禁改面空
- R0-3：后端断言删除 0；前端白名单外 expect 删除 0
- R0-5：dev.py / build.py 零改动

## 4. 后端改动登记表追加（总表同步）

| phase | 文件 | hunk 摘要 | R 编号 | 红线类别 |
|---|---|---|---|---|
| P1-1 | core/models.py | TaskType 追加 LLM_TRANSLATION（LLM 区块末尾，1 行+注释） | R1.2 | 只增 |
| P1-1 | core/events.py | 新增 LLM_TRANSLATION_COMPLETED 常量 | R1.4 | 只增 |

## 5. 未验证边界

- 常量的消费方（handler emit / 前端监听）随 P1-5/P1-6 交付；本步仅登记常量，无运行时行为可验证。
- 真机事件冒烟随 beta.1。

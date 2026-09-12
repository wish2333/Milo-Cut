# record-3.0.5-P1-6：R5.13 token 量级预估（SPEC M9）+ beta.1 节点（P1 收官）

> 步骤：PLAN P1-6 · 依据：[SPEC M9 R5.13](./spec-v3.0.5.md) · [PLAN](./plan-v3.0.5.md) P1-6 · [PRD](./PRD-v3.0.5.md) R5.13（P5 / F-A-09 / SG-5）
> 分支：`dev-3.0.5-P1-6`（已合入已删）· 提交：`7b2323c`（代码）→ `34fba34`（--no-ff 合入 `dev-3.0.5`）
> **beta.1 节点**：tag `v3.0.5-beta.1` 打于 `34fba34`；P1 全六步（R5.0/R5.1/R5.2/R5.3/R5.8/R5.13）收口

## 1. 改动清单

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `frontend/src/components/workspace/AIAssistantPanel.vue` | :229-269（估算 computed 区） | 旧 `ceil(N/30)` 单值估算替换为 `translationEstimate`：**前端同式复刻管线 target_windows 切批算法**（批窗 30 + 字符预算 4000，逐窗累计判界同形——任意文本长度组合下批数贴真实派发）；`tokens = 主轨字幕总字符 × 0.75` 经验比（万单位一位小数）；派生 `estimatedTranslationBatches` / `estimatedTranslationTokensWan` 两 computed | 只增（替换估算式） |
| 同上 | :945-950（翻译卡徽标） | `约 N 批 · 约 X 万 token`（主轨无字幕态保持「主轨无字幕」） | 渲染改写 |
| 同上 | :1085-1087（翻译对话框行） | `主轨字幕约 N 批 · 约 X 万 token，完成后自动切换到新译文轨` | 渲染改写 |

随主轨段数动态刷新：computed 依赖 `mainSegments` prop（track 模式判源不变——`translationSourceSegments` 先例），两显示点天然响应式；「约」标注恒在（SG-5 防系统性漂移）。

## 2. 用例登记（M-gate 前端 R5.13 = 1，实际改写 1 + 新增 1）

| # | 用例 | 要点 |
|---|---|---|
| F1（:301 改写） | estimates batches via the backend-shaped split and tokens from total chars | 短文本 1250 段（"main N"）：字符预算不缩窗 → 42 批（与旧口径同值，预算面验证靠 F2）；总字符 10143 → 7607 token → 「约 42 批 · 约 0.8 万 token」整串断言 |
| F2（新增） | splits long-text batches by the char budget | 60 段 × 200 字：4000 预算缩窗至 20 段/批 → **3 批**（朴素 ceil(60/30)=2 被证伪——预算切批面生效）；9000 token → 0.9 万 |

## 3. 断言反转清单登记（M0-3 白名单）

| 文件:行 | 处置 | 意图与理由 |
|---|---|---|
| AIAssistantPanel.test.ts:301（estimates the batch count as ceil(mainSegments / 30) 例） | **已按 M0-3 白名单改写**：断言 `"约 42 批"` → `"约 42 批 · 约 0.8 万 token"`（例名与意图同步改为 backend-shaped split） | R5.13 + SG-5 新估算式（M0-3 预登记：文字必然变化，★B-2）；该文件为 R0-3 前端白名单文件，expect 行改写在册 |

白名单外命中：零（门禁 R0-3 前端 PASS 实证）。

## 4. 验证（beta.1 节点全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  855 passed in 7.73s                        # pytest 全绿（beta.1 期望 ≥853 ✓；P1 五后端步累计 +22）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 858 passed (859)    # beta.1 期望 ≥851/≥850 ✓（P1 累计 +19）；唯一失败 = useRowLayout.perf 环境例（豁免口径，R5.16 根修后退役）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（后端 diff 白名单内 / 禁改面空 / events 双侧零 / 断言白名单外零删改（双侧）/ dev.py build.py 零改动）
===== 门禁汇总: 全部通过 (exit 0) =====
```

**beta.1 期望总数核对**（PLAN §0.1 表）：pytest ≥853 → 实际 **855** ✓；vitest ≥851/≥850 → 实际 **859 collected / 858 passed** ✓。tag `v3.0.5-beta.1` 落地。

## 5. 真机冒烟（beta.1 轮）——后置执行登记

按 3.0.4 冒烟后置先例（PLAN P1-6 明示「可后置执行」），beta.1 轮双平台真机冒烟**后置**，清单如下（异常走 smoke-fix：合入分支、tag 不动）：

- duplicate 防呆手感（重复框选/双击/时间码重复提交：轻提示、undo 栈不涨）
- 翻译失败→补译全链（至少一家非 json_mode 提供商：中文指引 / token 上报 / 缺口对账可读可定位 / 一键补译 / undo 一次回退）
- 取消中性提示与连续 429 降级可见
- token 量级预估显示

## 6. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步后端零改动；前端 2 文件登记入总表（估算式替换 + 渲染两点 + 测试改写/新增）。

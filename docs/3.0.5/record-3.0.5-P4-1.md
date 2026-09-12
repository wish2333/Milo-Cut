# record-3.0.5-P4-1：R5.6 keep 可感知收口（文案直显 + invalidated_count + 导出页说明）

> 步骤：PLAN P4-1 · 依据：[SPEC M5.6](./spec-v3.0.5.md)（实施裁决 1/2/3）· [PLAN](./plan-v3.0.5.md) P4-1 · [PRD](./PRD-v3.0.5.md) R5.6（S3 / US-05）
> 分支：`dev-3.0.5-P4-1`（已合入已删）· 提交：见 §6

## 0. 序 6 golden 锁先行确认

动手前复跑 `SegmentBlocksLayer.test.ts`：**26/26 全绿**（:287-381 三态 describe + keep golden 面含 6 例通过），基线绿确认后开工。**收口后未复跑破坏面**——本步零触碰 SegmentBlocksLayer.vue / editRangeClasses（红蓝并存 hunk 按 M5.6 裁决 3 随 P4-2 与 R5.9 同 commit 合入，约束③）。

## 1. 改动清单

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `SuggestionPanel.vue` | 按钮容器 :492-516 内 | **裁决 1 直显**：确认/忽略按钮后追加内联小字 `<span class="max-w-[9rem] text-[10px] text-ink-muted">`（manual 条件渲染；keep 全句「确认 = 参与裁剪计算，保留区间将从自动裁剪中扣除，非导出动作」/ delete「确认 = 参与裁剪计算，非导出动作」）；DOM 变更不出容器；`:title` :496 保留渐进增强；新增 `confirmHint()` 与 confirmTitle 同族 | 只增（模板 + 1 函数） |
| `WorkspacePage.vue` | :1032-1048 新函数 + :1253/:1658 改绑 | **裁决 1 toast 差异化**：`handleConfirmEdit(editId)` 包装 confirmEdit——按 edits 查 action，成功后 keep/删除两文案（与内联小字同措辞族）；两监听点 `@confirm-edit`/`@confirm-suggestion` 由裸 confirmEdit 改绑包装 | 只增 + 绑定点改写 |
| `useEdit.ts` | :181-207 | **裁决 2 透传**：generateSubtitleKeepRanges 泛型/返回类型/返回对象补 `invalidated_count: number`（后端 :3154 已上报、零改动） | 类型只增 |
| `useWorkspaceActions.ts` | :129 dep 类型 / :790-805 toast | dep 类型补键；重跑 toast 改「新增 {new_edits} 条、按保留区间清除 {invalidated_count} 条旧区间」（invalidated=0 只报新增；失败文案不变） | 类型只增 + 文案改写 |
| `ExportPage.vue` | 计数行 :415-417 下 | **裁决 3 导出页静态说明**：`<p>` 一句「保留区间与删除区间重叠时，导出按删除处理」（confirmedEdits>0 条件渲染） | 只增 |
| 随 P4-2 后置 | SegmentBlocksLayer.vue :390 覆层 title / visibleEditRanges :141 相交预聚合 | 红蓝并存 hover 尾注与 title 语义化——M5.6 裁决 3 合并施工（防同文件 hunk 撕裂，约束③），覆层面断言随 P4-2 收口补齐 | 后置登记 |

keep 计算（project_service :2915-2989）与导出消费语义**零改动**（裁决 4：三点均文案/toast/类型面）。

## 2. 用例登记（M-gate 前端 R5.6 ≥3，实际 +6）

| # | 用例 | 覆盖 |
|---|---|---|
| F1 | SuggestionPanel 内联小字直显 | keep/delete 两变体以**行文本**断言（非 title 属性）——hover 依赖消除（裁决 1） |
| F2 | 重跑 toast invalidated>0 | 「新增 5 条、按保留区间清除 2 条旧区间」全文断言 |
| F3 | 重跑 toast invalidated=0 | 只报「新增 4 条」，无清除半句 |
| F4 | 重跑失败 toast | null 结果 → 错误文案不变（防御面回归） |
| F5 | 导出页说明渲染 | confirmed delete 存在 → 静态说明句以可见文本出现 |
| F6 | 导出页说明缺席 | 零确认修改 → 说明句不渲染（空工程头清洁） |

（确认 toast 差异化 handleConfirmEdit 无独立断言面——依赖 WorkspacePage 深装配（bridge/project 注入链），P4-2 R5.9 同文件覆层 hunk 合入时该面板面一并冒烟；措辞与 F1 直测的内联小字同族。登记 §5。）

测试基建：useWorkspaceActions.test.ts DepsOverrides 开放 `showToast`/`generateSubtitleKeepRanges` 覆写（测试钩子只增）。

## 3. 断言反转清单

本步**零反转**（纯新增用例；原 English 重跑 toast 文案被 F2-F4 同步改写为新中文口径——属实现面文案改写非既有断言，无既有测试断言旧串，门禁 R0-3 前端 PASS 实证）。

## 4. 验证（全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  867 passed in 8.68s                        # 后端零改动，与 P3 持平
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 63 passed (64)
  Tests       1 failed | 871 passed (872)    # beta.2 866 → 872（+6）；唯一失败 = useRowLayout.perf 环境例（已登记）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（禁改面为空；events 双侧零改动；断言白名单外零删改；dev.py/build.py 零改动）
===== 门禁汇总: 全部通过 (exit 0) =====
```

## 5. 解释登记与未验证边界

- **确认 toast 差异化无独立断言**：handleConfirmEdit 依赖 WorkspacePage 全装配（useAnalysis 桥接 + project refs），单测面成本高于收益；文案与 F1 直测内联小字同族同源（confirmHint/两文案措辞一体设计），P4-2 冒烟覆盖。登记。
- **内联小字宽度**：`max-w-[9rem]` 折行容忍长句（面板窄列不溢出）；真机字号/折行观感随 beta.3 冒烟。
- **覆层红蓝并存提示后置**：SegmentBlocksLayer :390 title 中文化 + visibleEditRanges 相交预聚合 + 尾注——与 R5.9 同 hunk 随 P4-2 合入（M5.6 裁决 3 / 约束③），本步 golden 锁面零触碰。
- **invalidated_count 语义**：仅字幕裁剪重跑（subtitle_trim source 旧删除区间被 keep 重叠清除，manual 决策永不触碰——后端 :3082 注释口径）；toast 只在该路径出现。

## 6. 后端改动登记表追加

本步后端零改动；前端 5 文件（4 改 + 1 新测试文件）登记入总表。

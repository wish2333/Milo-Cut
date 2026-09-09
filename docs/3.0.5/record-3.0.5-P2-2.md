# record-3.0.5-P2-2：R5.4 前端：批量 undo 三态层 + patch 消费 + 确认文案 + beta.2 节点（P2 收官）

> 步骤：PLAN P2-2 · 依据：[SPEC M5.4](./spec-v3.0.5.md)（实施裁决 3-6 / 触点表前端面）· [PLAN](./plan-v3.0.5.md) P2-2 · [PRD](./PRD-v3.0.5.md) R5.4（S2 / MF-1 / D7c / SG-4）
> 分支：`dev-3.0.5-P2-2`（已合入已删）· 提交：`481780a`（代码）→ `77d2827`（--no-ff 合入 `dev-3.0.5`）
> **beta.2 节点**：tag `v3.0.5-beta.2` 打于 `77d2827`；P2 两步（R5.4 后端 + 前端）收口

## 1. 改动清单

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `useWorkspaceActions.ts` | :69-88（correctionUndoLayers） | **MF-1 三态第二形参** `scopeTrackId: string \| null = null`：null = 全部视图 → `["segments","tracks","analysis"]` 三层并集（全部视图天然混含主/副轨结果，两层快照必挂 undo 故三层）；"" = 主轨两层；非空 = 副轨两层；逐条调用单参形态不变（entry 恒带具体 scope） | 受控改点 (b) 前端面 |
| 同上 | :144-148 / :172-182（deps） | 新 dep `getReviewScope: () => {trackId, trackName}`；两包装签名升级（三态透传 + patch 返回） | 只增 |
| 同上 | :1013-1105（两 handler） | **D7c 消费链**：三态 pushSnapshot 先于批量写（「批量接受」/「批量清除」标签，一次 undo 回退整批——对接 P2-1 聚合单 patch）；`res.patch` 存在 → 单次 `emit("project-updated", patch)`（applyProjectPatch 通道），**移除** switch_timeline 全量替换（accept 无 patch 回落旧径防御；clear 原本无刷新，新增 patch 消费）；**SG-4 口径分工**：确认框 N = 前端 scope 过滤计数（accept 区含 ≥0.8 过滤、clear 区全部待审），完成 toast N = 后端 accepted_count/cleared_count 如实；裁决 6 文案三态（〈主轨〉/〈轨名〉/〈全部轨道〉）；空集 no-op 轻提示不弹框不清桥 | 受控消费面 (D7c) |
| `useLlmTasks.ts` | :519-555（两包装） | `acceptHighConfidenceCorrections(tlId, threshold, trackId)` 第三参透传 + `patch` 返回键；`clearCorrections(tlId, trackId)` 同构 + 返回 `{cleared, patch}`；**clear 由本地 `pendingCorrections = []` 改 `loadCorrections` reload**（作用域清除不吞他轨待审的 UI 面；None 全清语义等价——后端已清空，get 返回空） | 只增 + 行为修正（登记） |
| 同上 | :43-56（SubtitleCorrection） | 补 `track_id?`/`track_name?`（后端 get_subtitle_corrections payload 已携带，运行时无变化）+ CorrectionReviewEntry 补 `confidence?` | 类型只增 |
| `WorkspacePage.vue` | 装配点 | deps 增 `getReviewScope: () => ({trackId: activeListTrackId ?? "", trackName: activeListTrackName})`——列表轨即审阅作用域（null id = 主轨视图 → ""）；**「全部」(null) 入口随 R5.11 审阅过滤 toggle 到位**（本步机制全通、入口后置，登记 §5） | 只增 |

## 2. 用例登记（M-gate 前端 R5.4 ≥3，实际 +7）

| # | 用例 | 覆盖 |
|---|---|---|
| F1 | main scope confirm + snapshot | 裁决 6 文案〈主轨〉+ scope 过滤计数（3 条中 1 条高置信度）；快照主轨两层；桥调用第三参 "" |
| F2 | track scope confirm + snapshot | 〈English〉文案 + 副轨两层 + 第三参轨 id |
| F3 | 全部 scope 三层并集 | 〈全部轨道〉文案计两轨高置信度；快照 **[segments, tracks, analysis] 并集**；第三参 null |
| F4 | patch 消费无全量刷新 | 聚合 patch 经 project-updated 单次发射；switch_timeline 零调用 |
| F5 | 无 patch 回落 | accepted=0 无 patch → switch_timeline 旧径（防御路径） |
| F6 | clear 作用域 | 确认计全部待审（不筛置信度）+ 轨 id 透传 + 快照轨两层 + patch 消费 |
| F7 | 空集 no-op | 作用域零待审 → 不弹框零桥调用 |

「undo 三态各一次回退」验收面：快照层正确性（F1-F3）+ 后端聚合单 patch revision+1（P2-1 B3）+ 既有 undo 模拟机制（本宿主 M2-3 先例）三面合成；真机手感留 beta.2 冒烟。

## 3. 断言反转清单

本步**零反转**（纯新增用例；门禁 R0-3 前端 PASS 实证）。

## 4. 验证（beta.2 节点全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  862 passed in 8.11s                        # beta.2 期望 ≥859 ✓（P2 后端 +7 于 beta.1）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 62 passed (63)
  Tests       1 failed | 865 passed (866)    # beta.2 期望 ≥854/≥853 ✓（P2 前端 +7）；唯一失败 = perf 环境例（豁免）
  [PASS] build 通过（一轮 mock 类型/未用变量修复后绿） / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（含 R0-3 双侧白名单口径 [P2-1 排除面扩充后形态]）
===== 门禁汇总: 全部通过 (exit 0) =====
```

**beta.2 期望总数核对**：pytest ≥859 → **862** ✓；vitest ≥854/≥853 → **866 collected / 865 passed** ✓。tag `v3.0.5-beta.2` 落地。

## 5. 解释登记与未验证边界

- **「全部」入口后置**：getReviewScope 当前映射 `activeListTrackId ?? ""`（主轨/副轨两态可达）；null（全部）入口随 R5.11（P4-3）审阅过滤 toggle 到位——三态机制（快照层/确认文案/桥透传/后端过滤）本步全通并有 F3 直测（测试以 getReviewScope 覆盖注入 null）。
- **按钮标签未作用域化**：批量条 N（WorkspacePage :1774 信任全部高置信度 (N)）仍为全量计数——列表按轨过滤归 R5.11（同文件同面），确认框文案为权威作用域口径；登记不顺手改。
- **clear 的 reload 语义**：作用域清除后 reload 全量待审（get_subtitle_corrections 现无 scope 形参；他轨条目保留显示正确）；R5.11 过滤到位后显示面随作用域收窄。
- **beta.2 真机冒烟（后置，3.0.4 先例）**：批量按钮作用域（主轨视图操作不吞副轨待审集；确认文案轨名/条数；「全部」明示待 R5.11 后真机验）+ 批量 undo 一次回退手感。

## 6. 后端改动登记表追加

本步后端零改动；前端 4 文件登记入总表。

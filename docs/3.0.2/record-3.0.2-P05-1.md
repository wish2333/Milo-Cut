# Record: P05-1 副轨编辑激活（Phase 0.5 / SPEC M1-1 / S1）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p05-1`（合入 `dev-3.0.2`）· 基点: `v3.0.2-base`

## 完成内容

- `TrackLane.vue`：SegmentBlock 增 `:update-time="updateTime"` 下传（v3.0.1 M5-2 预留语义激活）；组件头注释从 "P2 batch: read-only" 改写为 v3.0.2 激活记录
- `TrackLane.test.ts`：新增双路径用例（传入 updateTime → SegmentBlock props 为该函数 / 未传入 → undefined 保持禁用）
- 新建 `composables/useTrackEdit.test.ts`（11 例）：乐观更新（含 unknown segment 忽略、兄弟段/主轨引用不受扰）、防抖合并（同段同字段 3 合 1、异字段异段独立）、失败回滚（失败取回前快照 / 成功采用后端态）、捕获层（有绑定 `["tracks","bindings"]` / 无绑定 `["tracks"]` / 仅 extension 侧命中才算绑定）、flushPending 立即提交且定时器不重复
- `SegmentBlock.test.ts` 既有 12 例无需改动：核查确认其已天然覆盖双路径（:192 "read-only mode (no updateTime) disables trim drags" 禁用路径 + 3 例传入 updateTime 的 trim 拖拽路径），符合 SPEC M1-1「只读断言适配双路径」的意图（双路径均有断言），无只读单断言需要改写

## 验证命令与实际输出

```
cd frontend && bun run test  ->  Test Files 40 passed (40) / Tests 466 passed (466)（新增 13 例全绿；连续 6 轮复跑全绿）
cd frontend && bun run build ->  vue-tsc + vite build ✓（887ms）
cd frontend && bun run lint  ->  eslint 0 errors 0 warnings
```

## 已知偏差（对 PLAN 的记录）

- PLAN 的短分支命名 `dev-3.0.2/<step-id>` 与常驻分支 `dev-3.0.2` 在 git ref 层互斥（`cannot lock ref`），改用 `dev-3.0.2-<step-id>` 命名，后续步骤沿用
- vitest 文件级假定时器在用例间不自动清理（首版用例暴露：前用例遗留 debounce 定时器在后续用例 advance 时触发）——已在测试 beforeEach 加 `vi.clearAllTimers()` 防护；属测试卫生问题，非 useTrackEdit 缺陷
- `pendingTrackCount` 基于非响应式 Map 的 computed，生产无消费者、无行为影响；未在本步改动（不扩 scope），登记为潜在清理项

## 未验证边界 / 待冒烟

- 手工冒烟（副轨段可拖 trim、邻居 blocked 拒动、防抖提交无回跳、失败回滚）待 Phase 0.5 退出检查时与 P05-2/P05-3 一并真机执行（涉及 UI 拖拽，自动化用例已覆盖链路逻辑）

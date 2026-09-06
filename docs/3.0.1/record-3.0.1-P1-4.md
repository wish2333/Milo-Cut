# Record: P1-4 patch merge 函数先行入库（Phase 1）

> 日期: 2026-09-01 · 分支: `p1/p1-4-...`（随 P1-3 分支顺延提交）-> `dev-3.0.1`

## 完成内容

- `frontend/src/utils/projectPatch.ts` 新增：
  - `mergeTracksInPlace`：按 trackId 复用未变 track 引用；track 内段经 `mergeSegmentsInPlace` 保持段级引用稳定；后端顺序为真源，id 序列不一致 gate 回退整体替换
  - `mergeBindingsInPlace`：按 binding id 合并，同款 gate
  - helpers：`trackEqual`（id/role/name/language + 逐段 `segmentEqual`）、`bindingEqual`、`segmentsArrayEqual`
- `frontend/src/types/project.ts`：`ProjectPatch` 补 `meta?: Record<string, unknown> | null`（SPEC M2-1 唯一 schema 触碰点，前端侧）
- **本步不接线**：`applyProjectPatch` 的 tracks/bindings 层仍整体替换（M11-2 现状），merge 函数无生产消费者；Phase 3 P3-2 激活

## 测试

- `projectPatch.test.ts` 追加 10 用例：track 引用恒等 / 变更 track 内未变段引用恒等 / 删除与新增 / gate 回退（warn 断言）/ bindings 三态 + gate
- 新建 `projectPatch.perf.test.ts`（R6.2 门禁，Phase 3 起强制）：
  - 合成规模 1000 主段 + 4x200 副段 + 200 bindings：`applyProjectPatch` 组合三层 patch p50 = **0.196ms**（门禁 < 5ms，25 倍余量）
  - 单副段变更后兄弟 track / 兄弟段引用 `toBe` 稳定断言（当前直接断言 merge 函数，P3-2 后自动覆盖接线路径）
  - 单遍扫描结构断言（4x 输入耗时线性放缩）

## 验证命令与实际输出

```
cd frontend && bun run test               -> Test Files 36, Tests 407 passed
[perf] applyProjectPatch(...,1000+4x200) x50: p50=0.196ms
cd frontend && bun run build              -> 通过
uv run pytest                             -> 663 passed
uv run ruff check .                       -> All checks passed
```

## Phase 1 退出检查（plan §Phase 1）

- P1-1/P1-2/P1-3/P1-4 全部合入 `dev-3.0.1`；pytest 663 / vitest 407 全量绿；本批不发布（无 UI）✅

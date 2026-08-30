# Record: P2-3 M7-1 patch 细粒度化

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M7-1 / 风险评审 §4.3 M7 守门断言 / PRD B5

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/utils/projectPatch.ts` | 新增 `mergeSegmentsInPlace(oldSegs, newSegs)`：①Map<id, seg> 合并 O(n)；②`segmentEqual` 段级相等性（id/version/type/start/end/text/speaker + words 逐词 word/start/end）——**相等的段保留旧对象引用**（toBe 稳定，v-memo 与 mergedSegments/segmentStateMap 等 computed 依赖自动跳过）；删除=缺席过滤；新增段并入后按 start 稳定排序；③**守门断言**：合并结果 id 序列必须与后端 patch.segments 完全一致，否则 `console.warn` + 整体替换（宁可慢，不可错序）。`applyProjectPatch` segments 层接入 |
| `frontend/src/utils/projectPatch.test.ts` | M7-1 测试组 4 条 |

## 关键说明

- 后端 segments 层序列化保持全量数组不变（计划原文要求），细粒度化完全在前端应用侧，后端零改动。
- 相等性检查是引用稳定的关键：patch 每次解析出的都是全新对象，仅按 id 替换不解决 v-memo 失效（所有引用都会换新）；必须做字段级相等比较才能保住未变行引用。words 数组为唯一的嵌套结构，逐词比较（word/start/end）。
- 守门断言用例采用"等 start 双段乱序"构造（稳定排序无法从 start 派生的唯一场景），验证回退路径与 console.warn 均触发。

## 验证

```
cd frontend && bun run test   -> 261 passed（257 + 4）
cd frontend && bun run build  -> vue-tsc + vite 通过
```

## 未验证边界

- 1167 段项目单字编辑 Vue DevTools 重渲染行数 ≤ 可视区、v-memo 命中验证 → 与 P2-4 虚拟滚动同批真机实测（Vue DevTools 高亮）

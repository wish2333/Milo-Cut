# Record: P2-2 M4 bridge 批量事件 + 自适应 tick + task:completed 瘦身

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M4 / 风险评审 §2.1-2.3 修正案 / PRD B1

## 改动文件

| 文件 | 改动 |
|---|---|
| `pywebvue/bridge.py` | `_flush_events` 重写：整体出队（严格 FIFO）→ 按 512KB 序列化预算分块 → 每批一次 `evaluate_js`；`_dispatch_batch` 内嵌 `typeof __pywebvueDispatchEvents` 回退（旧前端兼容）；`tick()` 返回 `{success, data: {pending}}` |
| `pywebvue/app.py` | on_loaded bootstrap：先注入 `__pywebvueDispatchEvents`（document.dispatchEvent + bubbles），再置 `__BRIDGE_READY__`；tick 循环改自适应（连续 40 次空转 → 250ms，pending > 0 → 50ms） |
| `core/task_manager.py` | `TASK_COMPLETED` 事件瘦身：result 含 `project` 时事件载荷剥离之并附 `result_meta: {project_stripped: true, keys}`；task 记录保留全量 result（`get_task` 走 call 通道不受影响） |
| `frontend/src/composables/useAnalysis.ts` | C1 监听器：`result_meta.project_stripped` → `get_project` 拉取后经 `onBeforeProjectUpdate`(segments,edits) 回填；非 stripped（demo）走旧路径 |
| `frontend/src/composables/useProject.ts` / `frontend/src/App.vue` | waveform_generation 完成事件同样检测 stripped → 拉取 |
| `frontend/src/pages/WorkspacePage.vue` | proxy_generation / llm_* 完成事件检测 stripped → 拉取并 emit |
| `tests/test_bridge_batch.py`（新） | 11 条 |

## 实现决策（对 plan/SPEC 的偏差）

1. **派发 helper 由后端注入而非 bridge.ts bootstrap**：tick 循环本就由 app.py 注入（历史设计），helper 放同处使旧 frontend_dist 搭新后端自动获得批量路径（组合矩阵的"旧前端"侧不再需要运行时探测降级到最坏路径）；派发 JS 内的 typeof 回退仍保留并有测试。
2. **事件瘦身收敛到 task_manager 单点**：SPEC §2.3 列的 main.py 六处 handler（返回值含 project）零改动，唯一 emit 点（task_manager:TASK_COMPLETED）统一剥离——覆盖面比六处清单更全（未来新 handler 自动合规），调用方同步返回值不受影响（call 通道无 IPC 税）。
3. **前端消费点为 4 文件 5 处监听**（风险评审清单未含 WorkspacePage 的 proxy/llm 分支与 App.vue waveform 分支，实际全量排查补齐）；demo 桥不发 stripped 标记自动走旧逻辑。

## 测试覆盖（test_bridge_batch.py，11 条）

- 批量派发: 单事件单次调用；20 事件合并一次 evaluate_js 且顺序保持；300KB×3 独占拆批保序；60KB×10 按 512KB 预算分 2 组合计保序
- 兼容: 派发 JS 含 typeof 回退 + document.dispatchEvent + bubbles
- 关窗: evaluate_js 失败清空队列并置 window=None
- tick: pending 计数（空/排空/无窗口）
- 事件瘦身: 含 project 的 result 被剥离 + project_stripped 标记；不含 project 的 result 原样

## 验证命令与实际输出

```
uv run pytest -q                        -> 全绿 549 passed（538 + 11）
uv run ruff check <触及文件>             -> 0 问题
cd frontend && bun run test             -> 257 passed
cd frontend && bun run build            -> 通过
```

## 未验证边界（归批次冒烟 / perf-beta2）

- 波形生成期 DevTools 无 >50ms 长任务、空闲 IPC <4/s 实测（perf-beta2）
- 新旧 frontend_dist × 新后端组合矩阵手测（架构上已满足，冒烟确认）
- macOS 首启动握手真机回归（代码审查通过，真机归冒烟）

# Record: P3-3 M9 层级契约 + 风格 lint + 存量清理

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M9-1/9-2/9-3 / PRD C3+C5 / plan P3-3

## M9-1 z-index 五档 token + 菜单互斥

| 文件 | 改动 |
|---|---|
| `frontend/src/style.css` | `@theme` 新增 `--z-base/raised/dropdown/modal/toast`（100/200/300/400/500）+ `@utility z-*` 五个工具类；**构建产物已验证生效**（`z-index:var(--z-*)` 五条全部出现在 dist CSS） |
| 19 个组件/页面 | 26 处裸层级全部替换为 token 工具类：10 处 `z-[N]`（右键菜单→`z-dropdown`、SettingsModal/确认弹窗/字幕全屏/demo 加载→`z-modal`、Toast→`z-toast`、demo 徽标→`z-base`）+ 16 处 Tailwind 数字档（弹层/菜单→`z-dropdown`、sticky 横幅/拖拽热区/容器内遮罩→`z-raised`、模态覆盖→`z-modal`） |
| `frontend/src/utils/contextMenuManager.ts` | 移除 `closeallcontextmenus` 全局广播（派发 + 外部监听），单实例互斥由模块级 `activeClose` 状态天然保证（打开新菜单先 `closeActive()`） |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 右键菜单迁移至管理器：删除本地 document click/contextmenu 监听（含对 `z-[9999]` class 的 closest 选择器——改名后本会失效，迁移顺带消除隐患）、广播派发与 `handleGlobalClose` 监听；Escape/箭头键 capture 监听保留 |
| `frontend/src/utils/styleLint.test.ts`（新） | 3 条源码级 lint：业务 .vue 禁裸 z-index（`z-[N]` 与 `z-10..50`）、禁硬编码 hex（6/3 位）、style.css 含全部 token 与 @utility |

### 决策与偏差

1. **三个设置弹层不迁移 Teleport**（SPEC M9-1 原文"popover 统一 Teleport to body"）：转写/静音/裁剪弹层是工具栏锚定的 `absolute top-full` 面板，随锚点滚动、无锚点漂移面；Teleport 化需引入 getBoundingClientRect 定位快照（新增复杂度）却无行为收益。Teleport 保留给未来浮动面板场景。**上翻双测规则**：当前全部弹层向下弹（`top-full`），规则以文档形式约束未来新增（DESIGN.md 规则 4）。
2. **SuggestionPanel 右键菜单未接管理器**：其菜单一向独立管理（无广播监听），移除广播对其零影响；接入管理器挂 v3.1（record 登记为已知边界）。
3. **WaveformEditor 内联 `z-index: 0/1/2/5/10` 保留**：容器内局部堆叠上下文，不与全局浮层竞争；豁免条款写入 DESIGN.md。

## M9-2 DESIGN.md + 波形色板

| 文件 | 改动 |
|---|---|
| `docs/DESIGN.md`（新） | 层级契约 4 条（五档之外无层级 / 禁裸魔法数 / 菜单单实例互斥 / 上翻双测）+ 局部堆叠上下文豁免判定 + 可读性约束（最小 11px、AA 4.5:1、例外清单显式登记）+ 颜色纪律（禁 hex、灰阶类新代码禁用、浮层 surface token）+ 执行机制 |
| `frontend/src/utils/waveformTheme.ts`（新） | 波形 Canvas 色板单一来源（peak/peakStroke，slate 阶）；WaveformCanvas 3 处硬编码 hex 改引常量 |

灰阶类（`text-gray-*` 等）存量迁移：规则已写入 DESIGN.md 约束新代码；存量是全组件机械大扫除（数百处、零功能收益），挂 v3.1 backlog，本版不在 lint 中强制（避免门禁全红）。

## M9-3 存量清理

| 项 | 结果 |
|---|---|
| ruff 存量清零 | **38 → 0**（PRD §6 总验收项达成）：29 项自动修（F401/F541/I001/UP035）+ 手动 9 项：bridge_service 死变量、2 个 probe 脚本 E402（`# ruff: noqa: E402` 文件级豁免，sys.path 前置脚本模式）、3 处未用变量、B007 改 `_batch_segs`、B017 `pytest.raises(Exception)` 收窄为 `ValidationError` |
| pywebvue/bridge.py 死代码 | 任务队列机制整体移除（`_handlers/_task_queue/_pending_results/_cancelled_tasks/_task_lock/_task_counter` + `_execute_next_task/_deliver_result/register_handler/run_on_bridge/run_on_main_thread` + tick 内调用 + docstring 段，约 90 行）——风险评审核验 #5 确认零调用方；`tick()` 返回 pending 的自适应 tick 协议不变，`test_bridge_batch.py` 11 条全绿 |
| core/workflow_engine.py 死代码 | `_extract_edits_from_result` 删除（约 40 行，自 v2.2.0 起零调用）。**估算偏差**：风险评审"约 200 行"中的另两处不可删——`_compute_segments_hash` 实际被 `_create_snapshot` 调用（v2.2.0 注解过时）、`detect_conflicts` 经 main.py @expose 且前端 useWorkflow 存在调用方（bridge API 面稳定承诺）；如实保留 |
| v-html 两处警告 | WorkspacePage 字幕修正 diff 渲染两处 `v-html="renderDiff(corr)"` 加 eslint-disable + 安全注释（内容经 escapeHtml 全量转义 + 代码控控的固定 span 包裹，XSS 面为零）；`bun run lint` 对触及文件 0 errors **0 warnings** |

## 验证命令与实际输出

```
cd frontend && bunx vue-tsc --noEmit   -> 0 错误
cd frontend && bun run test            -> 321 passed (31 files)（318 + 3 styleLint）
cd frontend && bun run build           -> 通过；dist CSS 含五条 z-index:var(--z-*)
bunx eslint <触及文件>                 -> 0 errors 0 warnings（v-html 已消除）
uv run pytest                          -> 550 passed（bridge/workflow_engine 删码后全绿）
uv run ruff check .                    -> All checks passed!（全仓 0 问题，PRD 总验收达成）
grep -rn "z-\[" frontend/src           -> 仅 style.css 注释措辞一处（非代码），验收"除 token 定义"达成
grep closeallcontextmenus frontend/src -> 仅 2 处历史说明注释，零代码
```

## 未验证边界（归批次双平台冒烟）

- ★ 各 popover/右键菜单层级截图对比（M9-1 验收：层级正确无遮挡）；右键菜单多开互斥手测（行菜单 vs 波形块菜单互相关闭）
- 上翻方向双测：当前无上翻 popover，规则就绪
- WKWebView/WebView2 下 toast > modal > dropdown 实际叠放视觉核对

# record-3.0.4-P4-smokefix-1：真机冒烟第一轮异常 smoke-fix（P4-4 冒烟流程，tag 不动）

> 日期：2026-09　分支：`dev-3.0.4`（smoke-fix 直合，不另拉分支；PLAN P4-4「异常项走 smoke-fix 流程（合入 dev-3.0.4，tag 不动）」）
> 触发：P4-4 双平台真机全量回归**第一轮**（用户执行）反馈 3 项缺陷，拆解为 5 个子缺陷（1a/1b/1c/2/3）
> 修复来源：产品代码 5 文件修复由负责人完成并交付本步（后端回归测试 4 例已随附跑绿）；本步补前端回归测试 13 例 + 全套门禁 + 登记入库
> tag 链：不动（`v3.0.4-beta.3` 之后无新 tag；rc.1 仍待 P4-5 用户签字）

## 1. 缺陷清单（用户冒烟反馈摘要）/ 根因 / 修复

| # | 用户反馈摘要 | 根因 | 修复 |
|---|---|---|---|
| 1a | 翻译入口提示「LLM 未配置」，但设置页测试按钮一直可用（默认 provider 配置下 base_url/model 留空走默认值） | 前端 `loadLlmConfig` 用**原始** `base_url`/`model` 字段判 configured——空串 = 走 provider 默认的合法形态被误判未配置；后端 `is_configured()` 语义本就按解析后值判定 | `main.py` `get_llm_config` expose 增 `resolved_base_url`/`resolved_model` 两字段（`config.resolved_base_url()`/`resolved_model()`）；`useLlmTasks.loadLlmConfig` 改用 resolved 字段判定（缺失回落原始字段，兼容旧后端） |
| 1b | 翻译任务进度条全程 0%，直到完成才跳变 | 面板进度条只接了各功能**结果**流（smart_delete/highlight 等），从未监听通用 `task:progress` 流 | `useLlmTasks.ensureListeners` 新增 `EVENT_TASK_PROGRESS` 监听：`isRunning` 为 true 时把 `detail.percent` 写入 `progress` ref（UI 单飞约定 SPEC M1-5 下无歧义，无需 task-id 簿记）；非数值 percent 忽略；其余功能态不受影响 |
| 1c | 翻译中途点取消，界面要等很久（在途批次完成）才停 | `analyze_subtitle_translation` 并发循环用 `as_completed`（阻塞到下一批完成才能观察 cancel）+ `with` 块退出 `shutdown(wait=True)` 等在途 HTTP 批 | 改 `concurrent.futures.wait(timeout=1.0, FIRST_COMPLETED)` 轮询 + finally 非阻塞 `shutdown(wait=False, cancel_futures=True)`；取消延迟从「下一批完成」降到轮询间隔；429 降串行路径双循环退出修正（stop_polling）；完成集按批序排序处理保持 ledger/progress 顺序稳定 |
| 2 | 手动标记的范围无法删除（只能撤销整工程） | 条目右键菜单只有「确认/忽略」；组级删除藏在组头右键菜单里不可发现 | `SuggestionPanel.vue` ① manual 条目右键菜单新增「删除此项（永久，含已确认）」（仅 manual，`runItemDeleteFromMenu`，confirm 确认后 emit `delete-edit-batch` [单 id]）；② manual 组头新增可见「清除」按钮（`data-test="manual-group-clear"`，`@click.stop` 调 `runGroupAction(group, 'delete')`，与组右键删除同链同 confirm 文案）；下游 Timeline → WorkspacePage → `delete_edit_decisions_batch` 通路既有零改动 |
| 3 | 副轨（译文轨）行高缩小时字幕块几乎看不到（顶距不变） | 块区 top 固定 `top-4`（16px）——占 24-48px 行高的 33-67%；副轨上无时间标尺，16px 留空无功能意义 | `TrackLane.vue` 块区 top 改 `blocksTop` computed = `clamp(round(lane.height*0.15), 3, 10)`px，随行高缩放（lg 72 → 10 / md 48 → 7 / sm 32 → 5 / collapsed 24 → 4 且块区 v-if 不渲染） |

## 2. 修复文件与行数（vs 合入前 HEAD = `bfc97c6`）

| 文件 | numstat | 缺陷 | 性质 |
|---|---|---|---|
| `main.py` | +6/-0 | 1a | 只增（expose 两字段 + 注释） |
| `core/llm_service.py` | +73/-40 | 1c | 受控改点（并发循环重构，行为等价 + 取消/429 路径修正） |
| `frontend/src/composables/useLlmTasks.ts` | +28/-6 | 1a + 1b | 登记改点（loadLlmConfig 判定 + 新监听器） |
| `frontend/src/components/workspace/SuggestionPanel.vue` | +37/-0 | 2 | 只增（两入口删除 affordance） |
| `frontend/src/components/workspace/TrackLane.vue` | +16/-2 | 3 | 登记改点（固定 top-4 → 比例 computed） |
| `uv.lock` | +1/-1 | —（随行） | 版本 bump 3.0.3 → 3.0.4 锁文件同步（66f46fd bump pyproject 后 `uv run` 重锁产物，非手改） |

红线核对：后端 diff 文件集 ⊆ SPEC M0-1 白名单（`main.py`/`core/llm_service.py` 均在表内）；禁改面 / dev.py / build.py 零命中；`core/events.py` 零改动（1b 复用既有 `task:progress` 事件，R0-2 无涉）；前端断言零删改（本步全部纯新增，见 §4）。

## 3. 回归测试清单（+17 例：后端 4 + 前端 13）

### 后端 4 例（负责人随修复交付，本步零改动，`tests/test_translation_smoke_fix.py` 新建 188 行）

| 例 | 缺陷 | 断言要点 |
|---|---|---|
| `test_resolved_fields_present_with_defaults` | 1a | 空 base_url/model + 有效 key → `is_configured()` True + expose 携带 resolved 字段 + api_key_masked 非空 |
| `test_raw_fields_stay_raw_for_settings_editor` | 1a | 原始 `base_url`/`model` 键保持用户原值（空串）——设置编辑器不会把默认值回写成显式覆盖 |
| `test_cancel_observed_while_batches_blocked` | 1c | 全部在途批阻塞 60s barrier + t=0.3s 取消 → 管线 5s 内（断言 worker 不存活，实际约 1s 轮询间隔）返回 `{success: False, error: "Cancelled"}`；barrier 释放后线程干净退出（非阻塞 shutdown） |
| `test_no_cancel_completes_normally` | 1c | 无取消快乐路径不回退：全量守恒 + 译文按段序返回 |

### 前端 13 例（本步新增）

**新建宿主 `frontend/src/composables/useLlmTasks.progress.test.ts`（7 例，183 行；照 `useLlmTasks.translation.test.ts` 的 vi.resetModules + 动态 import 单例隔离手法）**

| 例 | 缺陷 | 断言要点 |
|---|---|---|
| writes detail.percent into progress while a translation task is running | 1b | 经 `startTranslation` mock 成功进入 running 态 → emit `task:progress` {percent: 42} → `progress.value === 42`；后续批次 83.5 持续覆写 |
| ignores task:progress once the task is no longer running (completion path) | 1b | 完成事件翻转 isRunning 后，迟到 progress(99) 不覆写（保持 42） |
| ignores task:progress entirely while no task was ever started | 1b | isRunning=false 时 emit → progress 不被写（保持 0） |
| ignores progress payloads without a numeric percent | 1b | 字符串 percent / 缺字段 / undefined detail 三种畸形载荷均忽略 |
| treats empty raw fields with provider defaults as configured | 1a | `get_llm_config` 返回空 raw + resolved 值 + masked key → `configured === true`，model/baseUrl 取 resolved 值 |
| stays unconfigured when the resolved fields are empty too (no api key) | 1a | resolved 值在场但 api_key_masked 空 → `configured === false`（key 真值性不放松） |
| falls back to the raw fields when resolved ones are absent | 1a | 旧后端无 resolved 字段 → 回落 raw 字段判定（兼容性零回退） |

**挂既有宿主 `frontend/src/components/workspace/SuggestionPanel.test.ts`（+4 例，+125 行；harness 接真实 useAnalysis 同款）**

| 例 | 缺陷 | 断言要点 |
|---|---|---|
| item context menu offers 删除此项 … confirm=true | 2 | manual 条目右键 → 菜单出现「删除此项（永久…）」；confirm=true → emit `delete-edit-batch` [[单 editId]] + 桥调 `delete_edit_decisions_batch` [单 id] + confirm 文案含条目 label + pushSnapshot 先于桥调用（不可逆先快照） |
| confirm=false keeps the edit | 2 | confirm=false → 零 emit / 零桥调 / 零快照 + 菜单关闭 |
| manual group header renders a 清除 button …without folding it | 2 | `data-test="manual-group-clear"` 在场（含永久删除 title）→ confirm=true → emit `delete-edit-batch` [该组全部 editId（含已确认）] + 桥调同参；`@click.stop` 不触发挥叠 toggle（点击后组仍展开、条目行仍在场） |
| zero regression: legacy silence group | 2 | 静音组无清除按钮；条目菜单仅「确认此项/忽略此项」，**无**「删除此项」 |

**挂既有宿主 `frontend/src/components/workspace/TrackLane.test.ts`（+2 例，+31 行）**

| 例 | 缺陷 | 断言要点 |
|---|---|---|
| scales lane-blocks top with the lane height | 3 | height=48 → `lane-blocks` style top === "7px"；32 → "5px"；72 → "10px"（0.15*72=10.8 round 11 被 10px 上限压回） |
| keeps the block area unrendered while collapsed (height 24) | 3 | collapsed → `lane-blocks` v-if 不渲染 + 「已折叠」提示在场 |

既有断言零删改：三处全部纯新增（门禁 R0-3 前端白名单外 expect 删除数 = 0 自证）。

## 4. 门禁（`bash scripts/gates-v3.0.4.sh all`，exit 0）

| 项 | 期望 | 实际 |
|---|---|---|
| pytest | 833 = 829 + 新增 4，全绿 | **833 passed**（7.19s） |
| vitest | collected ≥834，唯一失败 = useRowLayout.perf 环境例 | **840 collected / 839 passed / 1 failed**（失败项 = `useRowLayout.perf.test.ts` 挂载墙钟环境例，827 → 840 = +13；豁免口径见 record-3.0.4.md §6） |
| build（vue-tsc --noEmit + vite build） | 通过 | 通过（3.19s，4 chunks） |
| lint（eslint .） | 0 errors 0 warnings | 0/0 |
| ruff check . | 0 problems | All checks passed |
| 红线 R0-1 ~ R0-5 + dev/build.py | 全部空/零/白名单内 | 全过（后端 diff 8 文件全在白名单；禁改面为空；R0-2 双侧 1/1；断言零删改 ×2；models.py 仅 LLM_TRANSLATION 追加） |

执行环境注记：本轮 `bun run` 可用（PATH 含 bunjs target），门禁脚本走 bun run test/build/lint 主路径（非回落）；pytest 833 与 vitest 840-839 与上方分项一致。

## 5. 未验证边界（待用户真机复测）

- **取消响应手感（1c）**：自动化断言「取消后 worker 5s 内返回（实测约 1s 轮询间隔）」；真机从点击取消到 UI 停止转圈的实际手感（含桥 tick 50ms 节流）待复测。
- **进度条真机流动（1b）**：单测验证 ref 写入链路；真机批粒度刷新的视觉连续性（30 段/批的跳变步进感）待复测。
- **配置误报（1a）**：mock 覆盖 resolved 判定；真机 DeepSeek/Qwen/GLM/Ollama 各 provider 默认配置下入口不再误报待复测（beta.1 清单本就要求覆盖至少一家非 json_mode provider）。
- **副轨视觉（3）**：断言像素值；真机四档行高（72/48/32/折叠）下字幕块可见性与美观度待复测。
- **删除 affordance（2）**：单测覆盖 emit/桥调/confirm 双态/折叠隔离；真机右键菜单与「清除」按钮交互手感、confirm 弹窗原生样式待复测。
- 多行时间线视觉回归债（3.0.3 顺延第 7 项）与 P4-4 清单其余项：仍待用户继续冒烟。

## 6. 登记口径与提交

- 本轮为 **P4-4 真机冒烟第一轮异常的 smoke-fix**（PLAN 冒烟流程）：直合 `dev-3.0.4`，**tag 不动**，不自行合并任何分支、不打 tag。
- 单 commit 含：5 文件产品修复 + 后端 4 例（负责人交付，勿改）+ 前端 13 例（本步）+ 2 文档（本 record + 总记录 §0/§1 回写）+ uv.lock 随行同步。
- P4-4 状态不变（冒烟继续，后续轮次异常另行 smoke-fix）；P4-5 rc.1/v3.0.4 tag 仍为用户签字节点。

# record-3.0.5-P1-5：R5.8 质量模式开关（SPEC M5.8；序 2 落点；MF-4 受控改点 (f)）

> 步骤：PLAN P1-5 · 依据：[SPEC M5.8](./spec-v3.0.5.md)（实施裁决 1-5 / 触点表）· [PLAN](./plan-v3.0.5.md) P1-5 · [PRD](./PRD-v3.0.5.md) R5.8（S5 / Q7 / N4）
> 分支：`dev-3.0.5-P1-5`（已合入已删）· 提交：`241ebb9`（代码）→ `7f4b7ac`（--no-ff 合入 `dev-3.0.5`）
> 顺序：序 2 已执行——P1-4（R5.3/(d)）先合入（`d91dbf2`）后本步开工；(f) :1774-1790 与 (d) 改判区同函数不同段，本步 diff 与 (d) 无 hunk 交叠（登记表分行登记）

## 1. 改动清单（逐 hunk）

| 文件 | hunk | 内容 | 红线类别 |
|---|---|---|---|
| `core/config.py` | :83-86（`llm_translation_target_language` 后） | DEFAULTS 追加 `"llm_translation_quality_mode": False` **1 键行**（+3 行注释；R0-4 人工核对：只增，位置即 SPEC 锚点） | 白名单内只增 |
| `core/llm_service.py` | :1755-1768（设置读取段） | 增读第 5 键 `settings.get("llm_translation_quality_mode", False)`（**不增函数形参**，handler 零改动——裁决 1）；quality_mode → `concurrency = 1`（值覆盖，一行裁决——裁决 2；取消 ~1s 不受影响：轮询 `wait(1.0)` :1866-1868 与串行降级循环 cancel 检查 :1938 在位，本步未触碰） | 受控（读取段增键 + 值覆盖） |
| `core/llm_service.py` | :1790-1826（预构建段） | **受控改点 (f)**：注释更新 + `batch_payloads` 类型放宽 `str \| None` + 新增 `quality_batch_contexts`（批上下文切片）；quality 开启 → 预构建循环跳过 prompt 组装（append `(target_ids, None, id_map)` 后 continue）；**默认关路径预构建逐字节保留**（关闭路径 payload 键集逐键等价用例 B1 锁定） | 受控改点 (f) |
| `core/llm_service.py` | :1828-1880（`_build_quality_prompt` 新嵌套函数） | 串行派发内惰性构建：extra 基础键 `target_segment_ids` + 批 N-1 定稿译文 `finalized_translations`（**批 N-1 的不透明 id 空间**（模型所见同空间）、源段序（source_order 排序）、窗口 = 1 批定稿）；prev future 读取带 `done() ∧ not cancelled()` + `except Exception` 三重防御（429 降级废弃 future / 异常 future 不破窗不阻塞） | 受控改点 (f)（新增函数） |
| `core/llm_service.py` | :1883-1890（`_call_batch` 头部） | `prompt is None` 分支接 `_build_quality_prompt`（默认路径 prompt 恒非 None，行为零变化） | 受控改点 (f) |
| `core/llm_service.py` | :1925-1937（futures 构造） | comprehension 改逐批 submit 循环 + `future_by_idx` **逐 submit 注册**：batch N 只能在 submit(N) 返回后启动，而 future_by_idx[N-1] 在 submit(N) 之前已注册——**归纳消除注册竞态**（即时 mock 下 comprehension 版存在理论 NameError/缺窗竞态，实测口径亦稳定）；futures dict 形状不变（`outstanding = set(futures)` / `futures[f]` 排序键照旧） | 受控改点 (f)（等价重构） |
| `core/llm_service.py` | :524-528（`_build_structured_user_message` docstring） | 受控增行：extra_context 文档登记 `finalized_translations` 转发键（extra_context 经 `payload.update` 顶层转发，行为零改动——增行为文档锚点） | 受控增行 |

**补译组合（Q7）**：补译请求走同管线（P1-4 路由），开关为全局设置不分新建/补译——同受串行约束；补译批「上一批」= 本轮补译序列内上一批（batch 索引即本轮序列，天然成立，零额外改动）。

## 2. 用例登记（M-gate 后端 R5.8 ≥2，实际 +4）

| # | 用例 | 覆盖裁决 |
|---|---|---|
| B1 | test_off_by_default_payload_key_set_unchanged | 裁决 3 前半（默认关：3 批 prompt 顶层键集恰 {segments, target_segment_ids}，逐键等价判据面） |
| B2 | test_quality_mode_sliding_window | 裁决 3 后半 + 裁决 2（开启（含 concurrency=5 配置被强制 1）：批 1 无该键（窗口边界）+ 批 2/3 各携前批定稿译文（前批不透明 id 空间 + 目标表同序 + EN[t] 逐条）） |
| B3 | test_quality_mode_cancel_still_prompt | 裁决 2（串行 + 全批阻塞栅栏 + 0.3s 取消 → ~2s 内返回取消 envelope；复用 smoke-fix 1c 栅栏法） |
| B4 | test_quality_mode_with_429_no_double_shutdown_hang | 裁决 5 SG2-7（quality × 持续 429：降级分支仍触发（"switching remaining" 警告）且无害——shutdown 幂等、串行循环接管、全批失败拒绝 envelope 完整（含补译文案 + data 双键），无挂起无崩溃） |

既有例零改动全绿（关闭路径行为等价的另一佐证：既有 27 例含 happy path/取消/429/守恒全部原样通过）。前端零改动（vitest 持平 858·857）。

## 3. 断言反转清单登记（M0-3 白名单）

本步**零反转**：纯新增用例，既有断言零触碰（门禁 R0-3 后端 PASS 实证）。

## 4. 验证（全套门禁，合入前执行；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  855 passed in 8.27s                        # pytest 全绿（P1-4 后 851 + 本步 4）
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Tests  1 failed | 857 passed (858)         # 与 P1-4 持平（前端零改动）；唯一失败 = perf 环境例（豁免口径）
  [PASS] build 通过 / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  [PASS] 后端 diff 白名单内（+ core/config.py 入列）
  [PASS] 禁改面为空 / R0-2 events 双侧零改动 / 断言白名单外零删改（双侧）/ dev.py build.py 零改动
  --- R0-4 config diff（人工核对：DEFAULTS 追加 1 键行 + 3 注释行，位置 = llm_translation_target_language 后，只增 ✓）---
===== 门禁汇总: 全部通过 (exit 0) =====
```

定向先行：test_llm_translation.py 31 例全绿（27 既有 + 4 新）。

## 5. 解释登记与未验证边界

- **futures 构造等价重构说明**：comprehension → 逐 submit 循环为 (f) 的竞态消除配套（同 hunk 族）；默认路径行为等价（提交序、futures 形状、轮询消费不变），B1 + 既有 27 例全绿为证。若 P5-1 终检对此 hunk 有「(f) 外多改」质疑，以本条登记为准（裁决 3「串行派发循环内逐批构建」的实现依赖）。
- **窗口数据源口径**：读 prev future result（工作者序列保证已 done）而非主线程 translations_by_index（后者消费与工作者启动存在竞态）——record 留痕的实现裁决，SPEC 未指定数据源，两者语义一致（同一定稿集）。
- **时延标注**：约 5× 时延（并发 5 → 串行）随 README 回填在 P5-2 落（PRD §9 写入设置文案要求）。
- **真机边界**：质量模式真机翻译质量收益观察留后续版本池（PRD §10.2 观察项）；本步交付开关与滑窗机制本身。

## 6. 后端改动登记表追加（总表见 record-3.0.5.md §3）

本步追加：config 只增 1 行 / llm_service (f) 族 6 hunk（含读取段增键与值覆盖），已汇总入总表；(d)/(f) 分行登记兑现。

# record-3.0.4-P3-1：golden 基线采集（M4-4 硬前置 = M0-3 约束 1）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-1`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-1　SPEC：M4-4 步骤 3（零回退判据与基线采集时机）+ M0-3 约束 1（golden 先行）+ R0-4
> 采集基线：tag `v3.0.3` = `55c68da5e273ea9df6b7994f49ff86cf4e3934a1`（只读 worktree `/tmp/milo-golden-v303`，采集后已移除）

## 1. 交付物清单（本步零产品代码改动）

| 文件 | 性质 | 说明 |
|---|---|---|
| `scripts/capture_keep_ranges_golden.py` | 新增（入库保可复跑，PLAN P3-1 裁决） | 采集脚本兼单一事实来源：固定 30 段段集 + padding 四档扫描 + 运行手法（真实 ProjectService + 临时工程 + update_transcript 造 subtitle 段，复刻 tests/test_project_service.py::_create_service 手法）+ 稳定序列化 `json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`；`main()` 内置双重采源断言（见 §2）；对拍用例 import 同一模块，采集与对拍共用一条代码路径 |
| `tests/fixtures/golden_keep_ranges_v3.0.3.json` | 新增（golden 数据文件） | 26509 字节；`meta`（基线 tag/commit、段集定义全量内嵌可重建、padding 档位、采集日期/方式、序列化口径）+ `results`（四档逐档 `summary` 计数 + 活动 timeline edits dump，后者即逐字节对拍对象） |
| `tests/test_keep_ranges_golden.py` | 新增（对拍用例骨架，2 例） | 见 §5 |

`core/`、`main.py`、`frontend/`、`pywebvue/`、`tests/` 既有文件：**零改动**（§6 红线自证）。

## 2. 采集执行方式（A.3 二选一登记：实际采用 fallback）

- **primary 尝试（失败，未采用）**：`cd /tmp/milo-golden-v303 && uv run --no-sync python scripts/capture_keep_ranges_golden.py`——uv 0.12.9 在 worktree 内新建裸 `.venv`（无依赖，`--no-sync` 不安装），`import loguru` 即 `ModuleNotFoundError`；失败时模块源断言已先行证实导入的是 worktree 代码（`/tmp/milo-golden-v303/core/project_service.py`），仅缺第三方依赖。已删除该误建 `.venv`。
- **实际采用（fallback）**：主仓工作目录执行 `PYTHONPATH=/tmp/milo-golden-v303 uv run --no-sync python scripts/capture_keep_ranges_golden.py --output <主仓>/tests/fixtures/golden_keep_ranges_v3.0.3.json`——主仓 `.venv`（Python 3.11.2）+ PYTHONPATH 使 worktree 代码路径优先；脚本 `_bootstrap_syspath()` 以 `find_spec("core")` 尊重 PYTHONPATH 优先级，不会让主仓 `core/` 抢先。
- **采源验证（脚本内置，输出留痕）**：`core.project_service.__file__ = /tmp/milo-golden-v303/core/project_service.py`（断言路径含 `milo-golden-v303`）；core 来源仓 `git rev-parse HEAD = 55c68da5e273ea9df6b7994f49ff86cf4e3934a1`（断言 == v3.0.3 全哈希）。两项任一不符即拒采退出。
- 环境：uv 0.12.9 / Python 3.11.2（主仓 `.venv`）；worktree 检出自 tag `v3.0.3`（detached HEAD），采集完成后 `git worktree remove` 清理。

## 3. 固定段集与 padding 档位

- **段集**：30 段 `gseg-0001..gseg-0030`，确定性手工表（无随机），总时长 86.5s（末段 end 即 total_duration），全量内嵌于 golden `meta.segment_set`。形态覆盖（合并阈值 = 2×padding，四档分别 0.0/0.4/1.0/2.0）：
  - 连续段（gap 0）：gseg-0002/0003、0019→0020、0025/0026；
  - 小间隙（< 最小非零档）：0.1s ×3（0004/0017/0018）；
  - 跨每档合并阈值的间隙：0.4 / 0.5 ×6 / 0.6 / 0.8 ×2 / 1.0 / 1.1 / 1.2 / 1.5 ×2 / 2.0 ×4 / 2.5 / 4.0；
  - 等长段：gseg-0011..0016 六段 2.0s 恒 0.5s 间隙（+ 0001/0002 等长对）；变长段：0.2s–4.5s 共 15 种时长；
  - 首段 start=1.0（padding<1.0 各档触发前导删除区间，padding=1.0 档不触发——首段形态分支双向覆盖）；末段 end=86.5=总时长（subtitle-only 段集下无尾随删除区间，为 v3.0.3 文档化行为）。
- **padding 档位**：`[0.0, 0.2, 0.5, 1.0]`（函数唯一参数名 `padding`，缺省 0.3 不入档——四档已含两侧与中间分辨率）。
- **逐档结果**（keep_ranges/delete_ranges/new_edits/edits dump 数）：0.0 → 25/25/25/25；0.2 → 21/21/21/21；0.5 → 11/11/11/11；1.0 → 3/3 组 keep/2 delete/2 new（首段 padding 吸收前导区间，delete 少于 keep 一档）。每档独立临时工程（函数对既有 edits 有 ±0.05 去重，共享工程会使计数依赖执行顺序）。

## 4. golden 文件

- 路径/大小：`tests/fixtures/golden_keep_ranges_v3.0.3.json`，**26509 字节**（UTF-8，`ensure_ascii=False`）。
- 结构：`meta`（基线 tag `v3.0.3`、commit 全哈希、函数名、padding 参数名与档位、采集日期 2026-09-05、采集方式、媒体时长 90.0、段集定义全量、shape 注记、序列化口径、可比对区段名 `results`）+ `results`（键 = 档位字符串 `str(padding)`，值 = `{"summary": {keep_ranges, delete_ranges, new_edits}, "edits": [活动 timeline edits dump]}`）。
- edits dump 取自函数返回 `data.project` 中活动 timeline 的 `edits`（即「输出 edits dump」），保持生成序（id 为零填充序号 `edit-subtitle-trim-NNNN`，随时间升序——序变动亦会被对拍捕获）。

## 5. 对拍用例（tests/test_keep_ranges_golden.py，2 例）

| # | 用例 | 锁定 |
|---|---|---|
| 1 | test_generate_subtitle_keep_ranges_matches_v3_0_3_golden_byte_for_byte | 无用户 keep/任何既有 edit 的工程 + 同一固定段集 + 同 padding 扫描，当前代码输出经共享 `canonical_dumps` 序列化后与 golden `results` **逐字节一致**；失败时报告**首处分歧路径**（如 `results.0.5.edits[2].end: golden=… != current=…`）+ unified diff 摘要（截 4000 字符），供 P3-9 排查 |
| 2 | test_golden_meta_matches_shared_definition | golden `meta` 与共享模块防漂移：baseline_tag=v3.0.3、padding 档位一致、30 段定义逐字段精确相等（含 JSON 浮点往返稳定性） |

共享通路：用例经 `sys.path` 注入仓库根 `scripts/` 后 `from capture_keep_ranges_golden import build_capture_results, canonical_dumps, ...`——段集构建、运行、序列化与采集脚本同一模块同一代码路径（二选一取舍：import scripts/ 单一事实来源优于 fixtures/ 下第二份 helper，且 worktree 采集时仅需复制一个文件）。诊断器在结构比对前将两侧规范回纯 JSON 类型（StrEnum 序列化即值），确保报出的是真实数值/结构分歧而非枚举类型伪差异。

## 6. 红线自证（本步零产品代码改动）

- `git diff v3.0.3 -- core/ | grep -c generate_subtitle_keep_ranges` = **0**（P1/P2 累积 diff 中该函数亦零触碰；本步未新增任何 core/ hunk）。
- `git diff dev-3.0.4 -- core/ main.py frontend/ pywebvue/` = 空；`git diff dev-3.0.4 --stat` = 0 行（本步对全部已跟踪文件零改动，改动面 = 3 个新增未跟踪文件）。
- `git diff dev-3.0.4 -- tests/` = 空（tests/ 既有文件零改动，含零断言删改）。
- worktree 只读使用：采集不产生任何 v3.0.3 跟踪文件改动（复制的脚本与 `__pycache__` 均为临时物，清理后移除 worktree）。

## 7. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**810 passed**（808 + 2，全绿）
- ruff：0 problems；vitest：790 collected / 789 passed（唯一失败 = useRowLayout.perf.test.ts，已登记环境例）；build（vue-tsc + vite）/ lint（eslint 0/0）通过
- 红线 R0-1~R0-5 全部 PASS（后端 diff 文件集 ⊆ 白名单且均为 P1/P2 已登记 hunk；禁改面为空；events 双侧 1/1；后端断言删除 0；前端白名单外 expect 删除 0；dev.py/build.py 零改动）

## 8. 注意事项（P3-9 使用说明）

- P3-9 keep 感知改造合入后，用例 #1 即 M4-4 零回退判据的执行体：`user_keeps` 为空 → 输出必须仍与本文 golden 逐字节一致。
- golden 一经入库**不得重采覆盖**（重采即自带改动、对拍失义——M0-3 约束 1 的时序刚性）；若段集/档位确需调整，须在 v3.0.3 只读环境重采并单独登记理由。
- 主线 pytest 从本步起期望总数 810（后续 phase 登记「当期期望总数」以此为基）。

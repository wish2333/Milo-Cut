# record-3.0.4-P2-1：expose 轨道形参（start_subtitle_correction 增 track_id）

> 日期：2026-09（P2）　分支：`dev-3.0.4-p2-1` → 合入 `dev-3.0.4`
> 对应 PLAN：Phase 2 / P2-1　SPEC：M2-1（R2.1）

## 1. 改动文件清单

| 文件 | 改动 | R 编号 | 红线类别 |
|---|---|---|---|
| `main.py` | `start_subtitle_correction` 签名追加 `track_id: str = ""`（docstring 注明默认空 = 主轨、v3.0.3 行为不变）+ payload 追加 `"track_id": track_id` 一键 | R2.1 | 登记改点（SPEC M0-1 main.py 行明列） |
| `tests/test_correction_track_payload.py` | 新建 2 例：显式 track_id 入 payload（v3.0.3 既有键不变）；缺省调用 payload.track_id == "" 主轨等价 | R2.1 | 只增 |

## 2. 契约落实

- 形参默认值 `""`：既有调用（前端 useLlmTasks 既有调用点、workflow 等）零影响——缺省路径 payload 仅多一个值为空串的键，handler 侧（P2-2）对空串按主轨分支处理。
- M5 矩阵「track_id 缺省主轨一致」由既有断言零改动全绿 + 本步缺省等价用例双证。

## 3. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：776 passed（774 + 2，全绿）
- ruff：0 problems；vitest：771 collected / 770 passed（唯一失败 = useRowLayout.perf 环境例）；build / lint 通过
- 红线 R0-1~R0-5：全部 PASS（main.py diff 属登记改点；断言删除 0）

## 4. 未验证边界

- track_id 非空时 handler 段源行为随 P2-2 交付（本步仅 payload 透传）。
- 真机副轨纠错冒烟随 beta.2 ★。

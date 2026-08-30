# Record: P1-4 M2 持久化安全

> 日期: 2026-08-30 · 分支: `dev-3.0.0`

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/persistence.py`（新） | `atomic_save_with_backup(path, content, keep=2)`：tmp → flush+fsync → 双 bak 轮换（copy 语义）→ os.replace → 目录 fsync（尽力而为）；`load_json_with_recovery(path, keep, validate)`：主 → bak.1 → bak.2 恢复链，validate 失败同视为损坏，返回 `(payload, recovered_from, tried)` |
| `core/project_service.py` | `save_project` 改走 atomic_save_with_backup；`open_project` 接入恢复链（JSON 损坏与 model_validate 失败均触发），成功/`MEDIA_NOT_FOUND` 返回均附 `recovered_from`，全败返回 `{"error": "项目文件损坏且无可用备份", "data": {"tried": [...]}}` |
| `frontend/src/composables/useProject.ts` | `openProject` 检测 `recovered_from` → toast「项目文件损坏，已从备份恢复」 |
| `tests/test_persistence.py`（新） | 7 条测试 |
| `docs/PROJECT_SCHEMA.md`（新） | 字段契约 + 迁移链 + 持久化安全契约 + 导出边界 |

## 测试覆盖

- 半截 tmp 写入不影响主文件（断电模拟）
- 连续 save 三次后 bak.1/bak.2 轮换正确；超出 keep 的备份被丢弃
- 主文件 JSON 损坏 → 从 bak.1 恢复且 `recovered_from` 正确（含 MEDIA_NOT_FOUND 提前返回路径）
- 主文件 JSON 合法但 schema 校验失败 → 同样走 bak 恢复
- 全部候选损坏 → 失败返回 + tried 列表（3 个候选）

## 验证命令与实际输出

```
uv run pytest -q                     -> 全绿（502 passed）
uv run ruff check <触及文件>          -> 0 问题
cd frontend && bun run build / test  -> 通过 / 251 passed
```

## 未验证边界

- 双平台手动断电恢复演练 → 批次冒烟
- 保存路径耗时增幅 <5% 的正式复核 → perf-beta2 报告（fsync 开销 ms 级，风险低）

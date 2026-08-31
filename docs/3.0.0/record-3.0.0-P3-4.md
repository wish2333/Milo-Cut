# Record: P3-4 M10 project_service 分域

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M10 / PRD C4 / plan P3-4

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/correction_service.py`（新，454 行） | `CorrectionService(project_service)` 承接字幕纠错域 8 方法（store/get/_parse/accept/reject/accept_high_confidence/clear/apply_subtitle_corrections），bodies 逐字搬移、`self.` → `self._project.`（域内互调保持 `self.`）；运行时零 project_service 导入（仅 TYPE_CHECKING 类型引用）——单向依赖 correction → project |
| `core/migrations.py`（新，238 行） | 迁移链独立模块：`migrate_v1_to_v2(raw)`（纯 dict 函数）+ 4 个 post-load 实例迁移改模块函数（`service` 参数，bodies 逐字）+ `run_post_load_migrations(service)` 门面按原 open_project 顺序执行 |
| `core/project_service.py` | 2538 行 → **1909 行**（-629）：删除上述 13 个方法；`__init__` 接线 `self.correction = CorrectionService(self)`；open_project 改调 `migrations.migrate_v1_to_v2` / `migrations.run_post_load_migrations(self)`；其余零改动 |
| `main.py` | 7 处 `self._project.X` → `self._project.correction.X` 委托；**bridge 方法名与信封零变化** |
| 测试随迁 | `test_project_service.py`（_migrate_highlights/_migrate_overlapping → migrations 模块函数）、`test_migration.py`（_migrate_to_v2 → migrate_v1_to_v2，纯函数化后删除多余 ProjectService 构造）、`tests/integration/test_llm_pipeline.py`（svc.apply → svc.correction.apply）、`test_subtitle_correction_review.py`（34 处调用点 → svc.correction.X） |

## 实现决策

1. **组装点偏差**：SPEC 原文"main.py 组装"，实际在 `ProjectService.__init__` 自动接线 `self.correction`——保证集成测试直接构造 ProjectService 的既有路径零改动，main.py 仍只做 @expose 委托。单向依赖不受影响（correction_service 运行时不 import project_service）。
2. **域内互调保真**：搬移转换初版把 `accept_high_confidence_corrections` 内部对 `accept_subtitle_correction` 的调用误改为跨域调用，已在转换后按方法名单还原为 `self.`（2 处）；`self._project._current = ...` 的一处私有写入属搬移原语义（apply 流程直写当前工程），保留并记录。
3. **confirm_all_from_source 留守 project_service**：其为按 source 过滤的 ED 批量确认（分析/建议域），不属字幕纠错 CRUD/apply，未搬移。
4. **detect_conflicts / _compute_segments_hash 保留**：workflow_engine 侧初判"死代码"经核验实际可达（前者经 main.py @expose + 前端 useWorkflow 调用方，后者被 _create_snapshot 引用），遵从 bridge API 面稳定承诺不删。

## 验证命令与实际输出

```
uv run pytest                 -> 550 passed（全部锚定测试零改动断言语义，仅调用点随迁）
uv run ruff check .           -> All checks passed!
uv run python -c "import main" -> OK
```

行数守恒核对（验收：±5%）：2538 行 → 1909 + 454 + 238 = **2601 行（+2.5%）✅**；新增行为纯文件头/`__init__` 接线/门面函数。

## 验收偏差

**project_service.py < 50KB 未达标：实际 81.7KB**（106.4KB → 81.7KB，-23%）。计划行号基线（L1707-2180 约 900 行纠错域）对应 v2.4.0 时代；当前实际纠错域仅 454 行（多次迭代后收缩），M10 既定范围（纠错 + 迁移链）已全部搬出。剩余主体为编辑/ED/静音/时间线域，超出 M10 范围。与 M8-2 同性质，随批次检查点由用户裁决（接受现状 / v3.1 追加分析域拆分）。

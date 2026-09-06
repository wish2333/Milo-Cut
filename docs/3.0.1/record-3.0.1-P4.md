# Record: Phase 4 导出与收尾（P4-1 ~ P4-4，rc 代码完成）

> 日期: 2026-09-01 · 分支: `p4/export-and-polish` -> `dev-3.0.1`

## 完成内容

### P4-1 副轨导出接入删除区间映射（SPEC M6-1，PRD R9.1）
- 新统一入口 `export_track_subtitle(track, edits, output_path, *, media_duration, fmt, map_deletions)`：**复用主轨同一组映射函数**（`_get_confirmed_deletions` / `_compute_keep_ranges` / `_subtitle_survives_in_keep_ranges` / `_map_to_exported_timeline`），幸存规则与主轨一致 + lost 日志
- `export_track_srt` 降级为废弃包装（`map_deletions=False`，一版本周期后删除）
- main.py `_handle_export_subtitle` payload 扩展：`format: "srt"|"vtt"`（缺省 srt，非法值回退 srt）
- SRT/VTT 两种格式化输出

### P4-2 双语合并导出（PRD R9.2）
- `export_bilingual_subtitle`：主行 + 绑定副行双行同条；**仅已绑定副段显示第二行**；未绑定主段单行；时间轴以映射后主段为准
- ExportPage 每轨按钮组：SRT / VTT / 双语 SRT（含轨道名与 language 标识）

### P4-3 SubtitleOverlay 副轨字幕（SPEC M6-2，PRD R10.1/R10.2）
- props 扩展 `secondary: {tracks, bindings}` + `showSecondary`；binding 索引 `main_segment_id -> ext text`；仅绑定段显示次级行（小一号 + 降透明度），无绑定副段永不显示
- 设置项 `show_secondary_subtitle`（默认 true）：`core/config.py` 默认表 + `AppSettings` 类型 + GeneralSettingsTab 复选框；WorkspacePage 接线（设置弹窗关闭即 reload 生效）
- demo 桥 settings fixture 补字段

### P4-4 文档收尾（SPEC M6-3）
- 竞品报告 v2 第一节补时效声明（指向 PRD §0.3 现状表）
- `docs/design-spec.md` 补 §9"提升 owner 而非提升弹层"层级规则（含播放头实例）+ §10 堆叠时间线视觉约定
- `docs/PROJECT_SCHEMA.md` 补 `meta` 字段说明（唯一 schema 触碰点）
- `AGENTS.md` / `CLAUDE.md` 服务表补 `core/track_constraints.py`

## 验证命令与实际输出

```
uv run pytest                     -> 702 passed（基线 695 + 7 导出用例）
uv run ruff check .               -> All checks passed
cd frontend && bun run test       -> Test Files 39, Tests 453 passed
cd frontend && bun run build      -> 通过
cd frontend && bun run lint       -> 0 problems
git diff core/events.py frontend/src/utils/events.ts -> 空
```

## 实施说明

- straddler 段（骑跨删除区间）语义：两段 keep-overlap 在导出时间轴上拼接（与主轨 export_srt 完全一致）；测试含主副同一映射的一致性断言（同一几何经两条通道输出相同时间戳）。
- min 时长不足在 `update_track_segment` 中为**显式拒绝**（非静默拉宽）——前端 blocked 语义与后端终审一致。

## 未验证边界（P4-5 待办）

- ★ 双平台全量真机回归（§5 冒烟清单）+ 手感签字
- `v3.0.1-rc.1` -> `v3.0.1` 正式 tag 与 record 汇总

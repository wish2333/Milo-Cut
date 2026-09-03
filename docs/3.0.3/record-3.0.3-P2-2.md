# v3.0.3 P2-2 记录：列表行右键菜单 kbd 角标（SPEC M3 / PRD S3）

> 日期：2026-09　分支：`dev-3.0.3`（P2-2 短分支合入）

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/components/workspace/TranscriptRow.vue` | 右键菜单重构为配置驱动：`RowMenuItem`（label / `kbd?` / tone / dividerBefore / title / show / action），主/副轨两份配置 + 渲染层统一消费（v-for）；`kbd` 节点仅在有值时渲染 |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | 新增 M3 describe（5 例） |

## 快捷键登记表映射（裁决核心）

以 `ShortcutsSettingsTab.vue`（v3.0.0 M8-1 快捷键登记 UI）为唯一真源逐项比对：

| 菜单项 | 登记表匹配 | 角标 |
|---|---|---|
| 主轨·标记删除/取消删除 | 标记删除 → `Delete`（选择模式批量标记） | **Del** |
| 主轨·编辑文本 / 从时间指针分割 / 从中点分割 / 加入精华 / 删除段落 | 无登记快捷键 | 无 |
| 副轨·定位 / 编辑 / 删除此条字幕 | 无登记快捷键（`Delete` 仅作用于主轨选择模式，副轨无选择机制） | 无 |

- **R9.4 原则延续（不发明快捷键）**：无快捷键的项不渲染空 `<kbd>` 壳；角标款式复用 R9.4 既有 CSS（`font-mono text-[10px]` 灰角标，右缘对齐）。
- 边界遵守：仅动列表行菜单——波形行/块菜单（3.0.2 已带角标）零改动；菜单项动作语义零变化（纯展示层重构，既有 50 例主/副轨菜单测试零改动全绿）。

## 菜单行为等价性

- 按钮色调三档映射（default 灰 / primary 蓝·加入精华 / danger 红·删除族）与原逐项 class 一致；`title` 提示、分割项 `isPlayheadInside` 条件、`add-to-highlight` 显式关菜单、globalEditMode 守卫路径全部保持原 wiring。
- `track-menu-delete` data-test 保留（P1-3 测试与 Timeline 转发不受影响）。

## 测试（新增 5）

1. 主菜单 Del 角标唯一且款式正确（`data-test="menu-kbd"` + font-mono + 位于标记删除项内）。
2. 全主菜单快照（playhead 在场时 6 项全渲染）且 kbd 全局唯一。
3. confirmed 状态下取消删除项保留角标。
4. 副轨菜单零角标（不发明快捷键）且三项文字齐全。
5. 配置层动作仍触发（编辑文本进输入态；`show: false` 项整体隐藏不渲染）。

## 门禁（本步实际输出）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **716 passed** ✅ |
| vitest 全量 | **748 passed / 1 failed**（749 总数；唯一失败仍为 P0-1 已登记挂载墙钟环境例，失败集合未扩大）✅ |
| `vue-tsc --noEmit` + `vite build` | 0 错误 ✅ |
| eslint / `uv run ruff check .` | 全绿 ✅ |
| 红线五文件 diff | **空** ✅ |

## 未验证边界

- kbd 角标真机显示合并 beta.2 ★ 清单（P3-1）。

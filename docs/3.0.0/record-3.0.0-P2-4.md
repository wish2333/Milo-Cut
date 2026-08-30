# Record: P2-4 M7-2 字幕列表虚拟滚动

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M7-2 / 风险评审 §2.6 混合行类型 + §4.3 M7 守门断言 / PRD B3

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/utils/virtualList.ts`（新） | 纯函数窗口数学：`buildCumulativeOffsets`（类型注册表 + 前缀和偏移，n+1 条目）/ `findRowIndexForOffset`（二分定位）/ `computeVisibleWindow`（可视区 + overscan，空表与越界防御）/ `scrollTargetForIndex`（上方行顶对齐、下方行底对齐、已可见返回 null） |
| `frontend/src/utils/virtualList.test.ts`（新） | 21 条（含 1167 行单调性、混合行高、边界 clamp、大视口、简并输入） |
| `frontend/src/components/workspace/Timeline.vue` | 窗口化渲染器接入：全高 spacer（`height: totalHeight`）+ 绝对定位窗口切片（`top: offsets[start]`）；混合行按 `seg.type` 分派（原 v-if 逻辑原样保留，v-memo 数组不变）；rAF 节流 scroll 监听；ResizeObserver 视口高（不可用时降级 window resize）；`probeRowHeights` 每类型实测 offsetHeight 校正注册表；`scrollToSegment` 数学定位接入 selectedSegmentId watch 与 SuggestionPanel 外部高亮两个既有滚动点；草稿缓存 Map + 段删除清理 |
| `frontend/src/components/workspace/Timeline.test.ts`（新） | 7 条组件测试（短列表全渲染/长列表窗口收敛/滚动窗口平移/选段跳转定位/可见选段不滚动/草稿跨卸载保留/混合行渲染与 spacer 高度） |
| `frontend/src/components/workspace/TranscriptRow.vue` | 新增可选 `draft` prop 与 `draft-change` 事件：击键镜像未保存编辑文本（M7-2 草稿缓存），`startEdit` 优先恢复 draft，save/cancel 清除 |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | +4 条（击键镜像/draft 恢复/保存清除/取消清除） |

## 实现要点

- **混合行高**：TranscriptRow `min-h-[52px]`、SilenceRow `h-9`(36px)，注册表默认值即 CSS 值；探针在挂载与 segments 变化后实测渲染行高，偏差时更新注册表并重算偏移（`h <= 0` 忽略，兼容 happy-dom）。未来变高行零架构成本（风险评审 §2.6 预留）。
- **跳转定位**：`scrollTargetForIndex` 返回精确 scrollTop，行在视口上方顶对齐、下方底对齐、已可见不动；`el.scrollTop` 直接赋值（语义等同 `behavior:"auto"`，WebView2/WKWebView/happy-dom 三方一致）。
- **草稿缓存（虚拟化的行为保持关键）**：全量渲染时代码隐式依赖"行永不卸载"来保住全局编辑模式的未保存输入；虚拟化后滚出窗口即卸载。TranscriptRow 击键 → `draft-change` → Timeline `drafts` Map → 重挂载时 `startEdit` 恢复。保存/取消清空，段删除时清理残留。undo 栈不受影响（草稿不产生后端写入）。
- **性能路径**：滚动仅 rAF 内一次 scrollTop 读 + O(log n) 二分 + O(窗口) slice；offsets 仅在 segments/行高变化时 O(n) 重算；未变行靠既有 v-memo 跳过 patch。

## 实现决策（对 plan/SPEC 的偏差记录）

1. **移除 scrollIntoView 精调**：跳转改为纯数学定位一次到位。探针保证 offsets 与真实行高同步，精调无增益；且 happy-dom 的 `scrollTo`/`scrollIntoView` 存在错误 clamp（7748→7200），`scrollTop` 直赋是唯一跨环境一致图元。
2. **plan 回归清单核实偏差**：A/W/D/S 导航、Home/End、搜索跳转定位、列表拖拽在当前构建中不存在（grep 核实，疑为 spec 草稿残留表述）；本步未新增快捷键。实际存在且已被测试覆盖的交互面：Tab/Enter/Space 行焦点 seek、I/O 跳转、多选 Ctrl/Shift/Enter/Delete、右键菜单（Teleport 不受虚拟化影响）、外部高亮滚动定位、播放头所在行高亮。
3. **选择模式 sticky 横幅的偏移误差**：横幅 sticky 占位于流内，窗口数学未扣除其高度（≈33px ≈ 0.6 行），由 overscan 10 行缓冲吸收；与旧行为（scrollIntoView nearest 同样未计横幅）一致。

## 验证命令与实际输出

```
cd frontend && bun run test   -> 293 passed (24 files)（261 存量 + 21 virtualList + 7 Timeline + 4 TranscriptRow）
cd frontend && bun run build  -> vue-tsc + vite 通过
bunx eslint <触及文件>         -> 0 问题
uv run pytest                 -> 550 passed（后端零改动，锚定确认）
```

## 未验证边界

- ★ 1167 段滚动 ≥55fps 双平台实测（WebView2/WKWebView）+ 用户手感签字 → 批次冒烟；perf 脚本扩展与 `perf-beta2.md` 产出在 Phase 2 门禁
- M7-1 v-memo 命中/重渲染行数 ≤ 可视区的 Vue DevTools 验证 → 与本步同批真机实测
- 已知边界：时间戳编辑（点击时间值）滚出窗口时未提交值丢弃（文本编辑有草稿缓存，时间编辑无）；影响面极小（±0.1s 微调），如冒烟反馈明显再补草稿机制

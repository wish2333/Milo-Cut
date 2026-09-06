# Record: Phase 2 堆叠渲染（P2-1 ~ P2-5，beta.1 代码完成）

> 日期: 2026-09-01 · 分支: `p2/stacked-rendering` -> `dev-3.0.1`

## 完成内容

### P2-1 useLaneLayout（SPEC M4-1）
- `computeLaneLayout` 纯函数：预设 32/48/72、折叠 24、主轨下限 96 挤压（lg->md->sm->24 两轮压缩）、`overflowing` 标记
- localStorage `milocut:timeline-layout:v1` 全局偏好；损坏 JSON / 缺键容错
- `useLaneLayout` composable：ResizeObserver 容器高 + collapse/hidden/preset 操作 + 深度 watch 持久化
- 14 用例

### P2-2 SegmentBlock 泛化（SPEC M4-3）
- 从 SegmentBlocksLayer 抽出块渲染 + trim 交互 + hover 词高亮为 `SegmentBlock.vue`；`trackKind: "main" | "extension"` 参数化（extension 用 violet 次级样式）
- **SegmentBlocksLayer.test.ts 13 例断言零改动全绿**（纯重构锚定达成）
- `trim-end` 事件携带 altKey（Phase 3 联动跳过预留）；Layer emits 表扩展转发
- 12 块级用例（扩展样式/裁剪拖拽数学/Alt 反转吸附/只读禁用/邻居约束）

### P2-3 TrackLane 几何化（SPEC M4-2）
- 重写为几何 lane：inject 共享 metrics、percent 定位 SegmentBlock、视口裁剪、悬浮标题条（折叠按钮 + 轨道徽标 + 段数）
- 从 `Timeline.vue` 摘除（import + 挂载 + `tracks` prop），虚拟列表恢复原状；数据通路改接 WorkspacePage -> WaveformEditor
- TrackLane.test.ts 重写 8 用例（定位/裁剪/折叠/空轨/徽标）

### P2-4 WaveformEditor 堆叠编排（SPEC M4-4）
- 堆叠表面 `data-test="timeline-stack"`：主轨区（z0-z10 层与 hover 预览不变）+ N lane 绝对定位 + **单条 PlayheadOverlay 提升为 stack 直接子节点**（inset-y-0 贯穿全部 lane，"提升 owner"规则落地）
- wheel 缩放/平移从主轨区移到整个 stack（单 listener，lane 区共享导航）
- `tracks` prop 新增；>4 软提示（不硬限）；内容驱动高度（见偏差）
- WaveformEditor.test.ts 扩展 6 用例

### P2-5 Alt 语义（SPEC M4-5）
- SegmentBlock onUp：`ev.altKey` 跳过 snap（自由定位），邻居 clamp 保留；`trim-end.altKey` 供 Phase 3 副轨联动跳过
- SegmentBlock.test.ts 断言 Alt/非 Alt 值差异

## 实施偏差（已回写 SPEC 或待回写）

1. **内容驱动高度模式**：SPEC M4-4 挤压规则针对固定高容器；实际集成采用"主轨恒 112px（h-28）+ lane 自然高度累加"的内容驱动模式（computeLaneLayout 输入 = 期望高度，压缩永不触发）。理由：避免破坏 3.0.0 刚调定的 WorkspacePage 布局；折叠/显隐/高度档位全部有效。挤压数学保留在 computeLaneLayout（固定高容器可用，测试覆盖）。
2. **`data-test` fallthrough 覆盖坑**：父组件标签上的 `data-test` 会覆盖子组件根元素同名 attr（Vue attr 合并规则）——测试选择器一度全部落空。已移除父侧 attr；此坑记入开发笔记。
3. 裸 z-index 合规：lane 标题条/overflow hint 的局部层级用 inline style（跟随主轨区 z1-z10 既有惯例），通过 M9-2 styleLint。

## 验证命令与实际输出

```
cd frontend && bun run test   -> Test Files 38, Tests 442 passed
cd frontend && bun run build  -> vue-tsc + vite build 通过
cd frontend && bun run lint   -> 0 problems
uv run pytest                 -> 663 passed（后端本批零改动）
uv run ruff check .           -> All checks passed
```

## 未验证边界（P2-6 待办）

- ★ macOS 本机 GUI 冒烟（SRT 导入 -> 堆叠显示 -> 折叠/高度/显隐 -> 缩放 -> 播放头贯穿）——构建级验证已过，GUI 冒烟待用户执行
- ★ Windows WebView2 冒烟（wheel deltaMode 重点）
- `v3.0.1-beta.1` tag 待双平台冒烟通过后打

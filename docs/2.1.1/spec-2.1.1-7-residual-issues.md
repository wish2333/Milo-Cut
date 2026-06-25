# v2.1.1 Spec-6 执行阶段残余问题

> **日期**: 2026-06-25
> **来源**: spec-interview + Spec-6 执行后验证
> **关联**: `docs/2.1.1/spec-2.1.1-6.md`, `docs/2.1.1/record-2.1.1.md`

---

## 问题总览

| ID | 严重 | 类别 | 问题 | 状态 |
|----|------|------|------|------|
| R-01 | P0 | Bug | 编辑预览模式未跳过 `subtitle_trim` 间隙 | 未修复 |
| R-02 | P0 | 数据 | 字幕修正处理后计数不归零 + AnalysisResult 残留 | 未修复 |
| R-03 | P1 | UI | 高光提取跳切无折叠 + "已选 xx s" 小数过多 | 未修复 |
| R-04 | P1 | UI | 建议面板右键"全部撤销本组" + 底部大按钮精简 | 未修复 |
| R-05 | P2 | 验证 | 字幕纠错重复执行安全性 | 已验证安全 |
| R-06 | P2 | 已知项 | Spec-6 已知剩余 Minor 问题（M1-M5） | 延后 |

---

## R-01: 编辑预览模式未跳过 `subtitle_trim` 间隙 (P0 Bug)

### 问题

`subtitle_trim` 是系统自动检测的字幕间空白间隙（`core/project_service.py:1886-1905`），创建为 `action="delete"`, `source="subtitle_trim"`, `status=PENDING` 的 EditDecision。

在"剪后预览"模式中，`WorkspacePage.vue:185-190` 的 `deleteRanges` 过滤条件只包含 `status==="confirmed" && action==="delete"`，不包含 `source==="subtitle_trim"`，导致字幕间空白间隙在预览中**不会被跳过**——播放器仍然播放这些已检测出的间隙区域。

### 根因代码

```js
// WorkspacePage.vue:185-190 — 当前
const deleteRanges = computed(() => {
  return edits.value
    .filter(e => e.status === "confirmed" && e.action === "delete")
    //                          ^^^^^^^^^^^^^^^^^
    // subtitle_trim 的 status 是 PENDING，被此条件排除
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})
```

### 修复

```js
const deleteRanges = computed(() => {
  return edits.value
    .filter(e =>
      e.action === "delete" && (
        e.status === "confirmed" || e.source === "subtitle_trim"
      )
    )
    .map(e => ({ start: e.start, end: e.end }))
    .sort((a, b) => a.start - b.start)
})
```

| 变更 | 旧 | 新 |
|------|-----|-----|
| 过滤条件 | `status==="confirmed" && action==="delete"` | `action==="delete" && (status==="confirmed" \|\| source==="subtitle_trim")` |
| subtitle_trim 行为 | 不跳过 | 跳过（不论 status）|
| 文件 | `WorkspacePage.vue:185-190` | 局部 computed，一行改动 |

**安全性分析**: `subtitle_trim` 的 REJECTED edits（用户选择保留的间隙）也会被跳过——这是正确的行为：剪后预览应该跳过所有检测出的字幕间空白间隙，因为间隙本身不是内容。

---

## R-02: 字幕修正处理后计数不归零 + 数据残留 (P0)

### 问题 A — 按钮计数显示错误

AI 字幕修正完成后，AIAssistantPanel 显示绿色"查看修正结果 (N 条)"按钮。用户逐条处理完所有修正后，按钮文本仍然显示旧计数。

**根因** (`WorkspacePage.vue:81-83`)：

```js
const subtitleCorrectionCount = computed(
  () => subtitleCorrectionResult.value?.stored_count ?? pendingCorrections.value.length,
)
```

`stored_count` 在 `llm:subtitle_correction_completed` 事件中赋值一次（`useLlmTasks.ts:155`），之后**永不递减**。处理完后 `pendingCorrections.length === 0`，但 `??` 优先取左侧非 null 的 `stored_count`（仍为正整数），导致按钮永远显示初始计数。

### 问题 B — AnalysisResult 数据堆积

`AnalysisResult(type="llm_subtitle_correction")` 记录持久化在 `project.json` 的 `timeline.analysis.results` 中。虽然 `store_subtitle_corrections()` 在**重新执行 P1** 时会清除旧同类型记录，但**审阅完毕后**没有触发清理。

影响：
- 已处理完的修正记录残留在 project.json，随多次操作持续膨胀
- 下次打开项目时从残留数据重新 load
- 多次执行 P1 + 多次处理后累积形成"屎山数据"

### 修复

| 子项 | 方案 |
|------|------|
| 计数显示 | `subtitleCorrectionCount` 优先取 `pendingCorrections.length`，`stored_count` 仅 fallback。或处理完毕后调用 `resetSubtitleCorrection()` 置 `stored_count = 0` |
| 数据清理 | 全部修正项处理完毕时（`pendingCorrections.length === 0`），前端调用后端 API 删除对应 `AnalysisResult(type="llm_subtitle_correction")` |
| Toast 去重 | 修正 toast 加 guard（已知 M4），防止重复弹窗 |

---

## R-03: 高光提取 UI 问题 (P1)

### 问题 A — 跳切检测列表无折叠

`HighlightModeView.vue:175-185`，跳切警告 `<ul>` 逐条列出所有跳切，无折叠/无高度限制。当跳切较多时（10+ 处），黄色横幅撑爆可见区域，精华提取列表被挤出屏幕，用户无法查看和校验提取质量。

**修复**：改为 `<details>` 默认折叠：

```html
<details class="rounded-lg border border-yellow-200 bg-yellow-50 p-2 text-xs text-yellow-800">
  <summary class="cursor-pointer font-semibold">
    检测到 {{ jumpCuts.length }} 处跳切（点击展开）
  </summary>
  <ul class="mt-1 ml-4 list-disc">
    <li v-for="(jc, i) in jumpCuts" :key="i">
      片段 {{ jc.index }} -> {{ jc.index + 1 }} 间隔
      {{ Math.round(jc.gap_duration) }}s 可能产生音频跳变
    </li>
  </ul>
</details>
```

### 问题 B — "已选 xx s" 小数位数过多

`HighlightModeView.vue:171`：

```html
已选 {{ totalDuration }}s / 目标 {{ targetDuration }}s
```

`totalDuration` 来自后端 float 直接累加（`detail.total_duration`），无格式化，如 `615.378194`。

**修复**：`toFixed(1)` 保留 1 位小数：

```html
已选 {{ totalDuration.toFixed(1) }}s / 目标 {{ targetDuration.toFixed(1) }}s
```

---

## R-04: 建议面板 UI 精简 (P1)

### 背景

审计 `SuggestionPanel.vue` 发现右键菜单和底部操作栏存在冗余功能。

### 移除项

| 位置 | 移除 | 保留 | 理由 |
|------|------|------|------|
| 右键 group scope | "全部撤销本组" (`reset`) | "全部确认本组"、"全部忽略本组"、"删除本组建议" | reset 已覆盖单项撤销，组级 reset 无使用场景 |
| 底部操作栏 | "全部确认删除" 大按钮 | — | 组级右键已覆盖 |
| 底部操作栏 | "忽略所有建议" 大按钮 | — | 组级右键已覆盖，跨组批量忽略无意义 |

> "删除本组建议" 保留：用户可能想要永久移除某组无意义的 LLM 分析结果（如 LLM 幻觉产生的虚假建议）。

### 涉及代码

| 移除 | 行范围 | 内容 |
|------|--------|------|
| "全部撤销本组" | 355-359 | `<button @click="runGroupAction(contextMenu.group, 'reset')">全部撤销本组</button>` |
| 底部两个按钮 | 296-309 | 整块 `<div v-if="totalPending > 0">` + 两个 `<button>` |

---

## R-05: 字幕纠错重复执行安全性 (P2 — 已验证安全)

### 调查结论

P1 字幕纠错**重复执行是安全的**，不会造成数据冲突或逻辑错误。两层防护：

**后端** (`core/project_service.py:1391-1395`)：`store_subtitle_corrections()` 在写入前显式清除旧同类型记录：

```python
kept_results = [
    r for r in tl.analysis.results
    if r.type != "llm_subtitle_correction"
]
```

**前端** (`useLlmTasks.ts:231-236`)：`resetSubtitleCorrection()` 在每次执行前重置状态：

```js
subtitleCorrectionResult = null
pendingCorrections = []
```

**Workflow 层** (`core/workflow_engine.py:763`)：注释明确 *"subtitle_correction produces no segment-level EditDecisions"* —— 仅存储 AnalysisResult，不创建冲突的 EditDecision。

> **注意**：虽然执行本身安全，但已处理的旧 AnalysisResult 如果不清理仍会堆积（见 R-02）。

---

## R-06: Spec-6 已知剩余 Minor 问题

来自 `record-2.1.1.md` 最终审查（commit `fccb2fe`），当时标记为可延后：

| # | 描述 | 文件 |
|---|------|------|
| M1 | `duration-150` 未添加到 `active:scale-95` 按钮（scale 动画缺少 transition 不可见） | 全局按钮组件 |
| M2 | SettingsModal save/cancel 按钮使用 `rounded-lg`（应为 `rounded-md`） | `SettingsModal.vue` |
| M3 | Timeline merge 按钮使用 `rounded`（应为 `rounded-md`） | `Timeline.vue` |
| M4 | 字幕修正完成 toast 无去重 guard | `WorkspacePage.vue` |
| M5 | `add_highlight_segment` / `remove_highlight_segment` 缺少后端单测 | `tests/` |

---

## Spec-6 中被忽略的规格项

对照 `spec-2.1.1-6.md` 逐节复查执行完成度：

| 节 | 内容 | 状态 | 备注 |
|----|------|------|------|
| 1 | 工作区页面布局（侧边栏内联化） | 完成 | |
| 2 | 侧边栏详细规范 | 完成 | |
| 3.1 | 字幕行组件（含时间列重构） | 完成 | |
| 3.1.1 | 时间列编辑重构 | 完成 | |
| 3.2 | 静音隔离条 | 完成 | |
| 3.3 | 建议面板卡片 | 完成 | 右链 + 按钮需精简(R-04) |
| 3.4 | 视频预览区 | 部分 | 剪后预览未跳过 subtitleTrim (R-01) |
| 3.5 | 波形视图 | 完成 | |
| 3.5.1 | 波形工具栏增强 | **未执行** | spec 标注"待定"，本次也未决定 |
| 4 | 导出摘要弹窗 | 完成 | |
| 5 | 响应式布局 | 完成 | |
| 6 | 全局视觉精炼 | 部分 | M1/M2/M3 按钮圆角未统一 |
| 7 | 交互微动效 | 部分 | M1 transition 缺失 |
| 8 | 快捷键汇总 | 完成 | |
| 9 | 设置页快捷键 Tab | 完成 | |
| 10 | Bug: 文字拖拽 SRT | 完成 | |
| 10.2 | Bug: ArrowUp/Down 微调 | 完成 | |
| 10.3 | Bug: NameError 崩溃 | 完成 | |
| 11 | 精华提取重构 | 部分 | 跳切折叠(R-03A) + 小数(R-03B) + M5 测试缺失 |
| 11.2 | 移除 highlight EditDecision | 完成 | remain text fixed; back to original |

### 未执行项清单

| 项目 | 来源 | 原因 |
|------|------|------|
| 波形工具栏增强 | spec 3.5.1 | spec 自身标注"待定"，审阅后未决定 |
| 编辑预览 subtitleTrim 跳过 | spec 6.6 隐式 | `deleteRanges` 未考虑 `source` 维度 |
| 按钮圆角/transition 统一 | spec 6.1/6.2 | 执行遗漏 (M1/M2/M3) |
| 高光跳切折叠 + 时长格式 | spec 11.4 隐式 | UI 实现细节遗漏 (R-03) |
| 建议面板 UI 精简 | 无 spec | 用户实测反馈 (R-04) |
| 字幕修正数据清理 | 无 spec | 用户实测反馈 (R-02) |

---

## 变更文件预估

以下为修复上述问题预计需要修改的文件：

| 文件 | 问题 | 变更 |
|------|------|------|
| `WorkspacePage.vue` | R-01, R-02 | `deleteRanges` 纳入 subtitle_trim；`subtitleCorrectionCount` 修复；修正完毕后清理后端数据 |
| `SuggestionPanel.vue` | R-04 | 移除"全部撤销本组"右键项 + 底部两个大按钮 |
| `HighlightModeView.vue` | R-03 | 跳切 `<details>` 折叠；`toFixed(1)` 格式化 |
| `useLlmTasks.ts` | R-02 | 审阅完毕时调用清理 API；reset 逻辑 |
| `main.py` | R-02 | 新增 `cleanup_processed_corrections` 或复用删除接口 |
| `SettingsModal.vue` | M2 | `rounded-lg` → `rounded-md` |
| `Timeline.vue` | M3 | `rounded` → `rounded-md` |
| 全局按钮 | M1 | 补 `duration-150` |
| `tests/` | M5 | 补充后端单测 |

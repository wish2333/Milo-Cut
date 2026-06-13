# Milo-Cut v2.0.0 Phase 3 执行计划

> Version: 1.0
> Date: 2026-06-13
> Baseline: audit-plan-v2.0.0.md Phase 3 + record-2.0.0.md (Phase 1/2 已完成)
> Scope: 全局步骤导航 + 工作区分栏拖拽 + 页面过渡动画
> Status: **进行中**

---

## 0. 当前进度确认

### Phase 1 (Foundation) -- 已完成 (commit 93f1917)

| 任务 | 状态 |
|------|------|
| Task 1.4: 单一版本源 | 已完成 |
| Task 1.1: LLM 服务架构 | 已完成 |
| Task 1.3: HTTP API 桥接 | 已完成 |
| Task 1.2: LLM 设置面板 | 已完成 |

### Phase 2 (Core Features) -- 已完成 (commit b874ac5)

| 任务 | 状态 |
|------|------|
| Task 2.1: Topic Drift 后端 | 已完成 |
| Task 2.2: Topic Drift 前端 | 已完成 |
| Task 2.3: Bridge Service 文件协议 | 已完成 |

---

## 1. Phase 3 范围

| 任务 | 工时 | 依赖 | 状态 |
|------|------|------|------|
| Task 3.1: 全局步骤导航 | 3 pd | 无 (独立) | **进行中** |
| Task 3.2: 工作区分栏拖拽 | 1 pd | 无 (独立) | **进行中** |
| Task 3.3: 页面过渡动画 | 0.5 pd | Task 3.1 | **进行中** |
| **Phase 3 合计** | **4.5 pd** | | |

---

## 2. Task 3.1: 全局步骤导航 [3 pd]

> 目标: 按 design-spec.md 实现 5 步骤导航, 替代当前 v-if 硬切换

### 2.1.1 步骤映射

根据 design-spec.md, 5 个步骤映射到现有页面:

| 步骤 | 名称 | 对应组件 | 触发条件 |
|------|------|----------|----------|
| 1 | 导入 (Import) | WelcomePage | 无项目 (`!project`) |
| 2 | 分析 (Analyze) | WorkspacePage | 项目已创建, 执行检测 |
| 3 | 编辑 (Edit) | WorkspacePage | 编辑片段 |
| 4 | 审阅 (Review) | WorkspacePage | 审阅编辑决策 |
| 5 | 导出 (Export) | ExportPage | `showExportPage` |

步骤 2/3/4 共享 WorkspacePage, 通过 WorkspacePage 内部状态区分。

### 2.1.2 useStepNav composable

**文件**: `frontend/src/composables/useStepNav.ts` (NEW)

```typescript
export type StepId = "import" | "analyze" | "edit" | "review" | "export"

export interface StepDef {
  id: StepId
  label: string
  index: number
}

export const STEPS: StepDef[] = [
  { id: "import", label: "导入", index: 0 },
  { id: "analyze", label: "分析", index: 1 },
  { id: "edit", label: "编辑", index: 2 },
  { id: "review", label: "审阅", index: 3 },
  { id: "export", label: "导出", index: 4 },
]

export function useStepNav() {
  const currentStep = ref<number>(0)          // 当前步骤索引
  const maxReachedStep = ref<number>(0)       // 已达到的最大步骤 (用于限制跳转)
  const completedSteps = ref<Set<number>>(new Set())  // 已完成步骤

  function goToStep(index: number): boolean   // 仅允许跳到 <= maxReachedStep
  function nextStep(): void
  function prevStep(): void
  function markComplete(index: number): void  // 标记步骤完成, 推进 maxReachedStep
  function reset(): void                       // 项目关闭时重置

  return { currentStep, maxReachedStep, completedSteps, steps: STEPS,
           goToStep, nextStep, prevStep, markComplete, reset }
}
```

### 2.1.3 StepController 组件

**文件**: `frontend/src/components/common/StepController.vue` (NEW)

- Props: `steps: StepDef[]`, `current: number`, `maxReached: number`, `completed: number[]`
- Emits: `navigate: [index: number]`
- 设计: surface-black 背景, 44px 高, 居中显示步骤, 已完成显示 Action Blue 勾选, 当前高亮
- 点击导航: 仅 `index <= maxReached` 可点击
- 响应式: 桌面水平排列, 窄窗口紧凑

### 2.1.4 App.vue 集成

**文件**: `frontend/src/App.vue` (MODIFY)

- 引入 useStepNav, 在顶部渲染 StepController
- 步骤与页面映射:
  - step 0 (import): WelcomePage
  - step 1-3 (analyze/edit/review): WorkspacePage
  - step 4 (export): ExportPage
- 项目创建 -> goToStep(1)
- 点击导出按钮 -> goToStep(4)
- 项目关闭 -> reset()

---

## 3. Task 3.2: 工作区分栏拖拽 [1 pd]

> 目标: WorkspacePage 两栏布局支持拖拽调整比例

### 3.2.1 SplitPanel 组件

**文件**: `frontend/src/components/common/SplitPanel.vue` (NEW)

- Props: `minRatio?: number` (默认 0.3), `maxRatio?: number` (默认 0.7), `storageKey?: string`
- 左右两栏 + 可拖拽分隔条
- 拖拽时 `cursor: col-resize`, 实时更新比例
- 比例约束: 30%-70%
- localStorage 持久化: key 由 storageKey 决定
- slot: `#left`, `#right`

### 3.2.2 WorkspacePage 集成

**文件**: `frontend/src/pages/WorkspacePage.vue` (MODIFY)

- 主内容区 (`flex flex-1 overflow-hidden`) 用 SplitPanel 包裹
- 左栏: 视频播放器 (原 `w-2/5`)
- 右栏: Timeline (原 `w-3/5`)
- storageKey: `milo-split-workspace`

---

## 4. Task 3.3: 页面过渡动画 [0.5 pd]

> 目标: 页面切换平滑过渡

**文件**: `frontend/src/App.vue` (MODIFY)

- 用 `<Transition :name="transitionName">` 包裹页面组件
- transitionName 根据导航方向决定: 前进 `slide-left`, 后退 `slide-right`
- CSS: 300ms fade + slide
- 响应 `prefers-reduced-motion`: 禁用动画

---

## 5. 测试计划

### 后端

Phase 3 纯前端, 无后端改动。

### 前端单元测试

**文件**: `frontend/src/composables/useStepNav.test.ts` (NEW)

| 测试 | 覆盖 |
|------|------|
| 初始化 currentStep=0 | 默认状态 |
| nextStep 推进 | 前进 |
| goToStep 超过 maxReached 拒绝 | 限制 |
| markComplete 推进 maxReached | 完成标记 |
| reset 重置 | 项目关闭 |

**文件**: `frontend/src/components/common/SplitPanel.test.ts` (NEW)

| 测试 | 覆盖 |
|------|------|
| 渲染左右 slot | 基础渲染 |
| 比例 clamp 到 min/max | 约束 |
| localStorage 持久化 | 恢复 |

**文件**: `frontend/src/components/common/StepController.test.ts` (NEW)

| 测试 | 覆盖 |
|------|------|
| 渲染 5 步骤 | 基础渲染 |
| 当前步骤高亮 | 状态样式 |
| 超过 maxReached 不可点击 | disabled |

---

## 6. 验收标准 (Phase 3 Gate)

- [ ] StepController: 5 步骤可导航, 状态保持
- [ ] SplitPanel: 拖拽 30-70%, 跨会话持久化
- [ ] 过渡动画: 300ms fade-slide, 尊重 prefers-reduced-motion
- [ ] 前端构建: `bun run build` 零错误
- [ ] 前端测试: `bun run test` 通过
- [ ] 无回归: 现有功能不受影响

# record-3.0.4-P4-smokefix-2：真机冒烟第二轮修复（侧栏滚动 / 设置跳转 / 低置信度审阅）

> 日期：2026-09　分支：`dev-3.0.4`（直接提交，冒烟修复流程，tag 不动）
> 对应：P4-4 真机冒烟第二轮用户反馈（3 项）

## 1. 用户反馈 → 根因 → 修复

| # | 用户反馈 | 根因 | 修复 |
|---|---|---|---|
| 1 | 侧边栏 AI 助手滚动条错误，冻结太多，多行模式可能看不到开始处理按钮 | 面板根为 `overflow-hidden` 多段布局：工作流配置视图与功能详情视图各自 `overflow-y-auto`，头部（状态行/错误/模式切换/卡片/进度）全部冻结——短视口下启动按钮可能被挤出可视区 | **整块滚动重构**：仅保留 LLM 状态行固定（:409 区），其余全部（错误/翻译通知/模式切换/工作流视图/功能卡/进度/详情表单）包进单一 `overflow-y-auto` 容器；移除两处内部 `flex-1 overflow-y-auto`（空态块 flex-1 同步归一）——面板随内容整体滚动，启动按钮永在滚动流内 |
| 2 | 希望加按钮跳转设置页-LLM 方便改模型 | 「去设置」按钮仅在未配置时显示，且跳转落在 general 标签 | ① SettingsModal 新增可选 `initialTab` prop（activeTab 初始化默认 general 不变）；② WorkspacePage 绑定 `initial-tab="llm"`；③ 面板状态行的设置按钮改为**常驻**「模型设置」按钮（data-test="open-model-settings"），点击直达 LLM 标签 |
| 3 | 字幕修正审阅：低置信度每确认一个就折叠，需重开再确认下一个 | `<details>` 无受控 open——accept 的 patch 刷新使该节重挂载，DOM 展开态丢失 | 改受控 ref `lowConfidenceOpen`（`:open` + `@toggle` 双向）：展开态跨 patch 刷新保持；**默认改为展开**（顺序确认是该节的核心工作流，原「默认折叠」裁决随本反馈反转，用户可手动收起且状态保持） |

## 2. 改动文件

| 文件 | 改动 |
|---|---|
| frontend/src/components/workspace/AIAssistantPanel.vue | 整块滚动重构（新增滚动容器 + 移除两处内部滚动 + 空态归一）+「模型设置」常驻按钮 |
| frontend/src/components/workspace/SettingsModal.vue | `initialTab` prop（+6 行，默认 general 向后兼容） |
| frontend/src/pages/WorkspacePage.vue | `:initial-tab="llm"` 绑定 + `lowConfidenceOpen` 受控 details |

纯前端，后端零改动。

## 3. 验证

- vitest：**840 collected / 839 passed**（唯一失败 = useRowLayout.perf 环境例）；面板/工作区相关宿主 26/26 绿（含零回退断言）
- vue-tsc --noEmit + vite build 通过；eslint 0/0；pytest 833 保持
- `bash scripts/gates-v3.0.4.sh all` **exit 0**（红线 R0-1~R0-5 全过；既有断言零删改自证）

## 4. 裁决登记

- 低置信度节「默认折叠 → 默认展开」为对 3.0.3 既有默认值的用户反馈反转（受控 details 使折叠选择仍可用且持久），登记于本 record。
- 面板固定区收敛为「仅 LLM 状态行」：模式切换随内容滚动（不再常驻）——若真机反馈需要模式切换常驻，可加 `sticky top-0` 一行实现，登记备选。

## 5. 未验证边界

真机滚动手感/跳转落点/低置信度连续确认流——待用户第三轮复测。

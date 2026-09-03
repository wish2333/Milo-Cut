# v3.0.3 P2-1 记录：跟随平滑动画调度器（SPEC M2-1 / PRD R2.1-R2.3）

> 日期：2026-09　分支：`dev-3.0.3`（P2-1 短分支合入）

## 新增/改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/composables/useScrollAnimator.ts` | 新增纯模块：`createScrollAnimator`（animateTo/redirect/cancel/isActive/inEchoWindow/dispose），常量 `FOLLOW_SMOOTH_DURATION_MS=140` / `FOLLOW_SMOOTH_EASING="easeOutCubic"` / `FOLLOW_SMOOTH_STORAGE_KEY` / `SCROLL_ECHO_WINDOW_MS=100`；`readSmoothEnabled`/`writeSmoothEnabled` 容错读写（损坏 JSON/非布尔/异常 → 默认 false）；**零组件/bridge 依赖（SPEC M0-1）**，rAF/now 可注入供 vitest |
| `frontend/src/components/waveform/WaveformEditor.vue` | 接线：`writeScrollTop` 平滑分流（durationMs 0 直通保持 v3.0.2 语义）；导航跳转（exposed revealTime / 概览条 seek）经 `revealWithSmooth`（内核 revealTime 零改动，包裹 from→target 动画，DOM 钉在起点防目标闪帧）；reflector 监视器动画期间让权；滚轮 passive 哨兵取消动画；handleScroll 时间窗回环抑制；卸载 dispose |
| 测试 | `useScrollAnimator.test.ts` 新文件 12 例；`WaveformEditor.smoothFollow.test.ts` 新文件 6 例 |

## 实现要点 / 裁决

- **守卫（R2.2，3.0.2 空白嫌疑直接防御）**：播放时钟消费路径（currentTime prop → follow watch）写入**恒瞬时**，永不启动动画——开关开启也不变。smooth 仅作用于导航跳转。
- **时间窗回环抑制（R2.2）**：动画驱动中（及最后一帧后 100ms 宽限）的 trusted scroll 事件按动画回声处理——既不 cancel 也不 markManualScroll；窗口外的信任事件走既有 `consumeAutoScroll` 精确分类（3.0.2 语义不变）。滚轮哨兵（passive，不 preventDefault）在动画期检测手动意图并 cancel（手动优先级最高）。
- **重定向不叠加**：动画期任何 animateTo/redirect = 从当前已写值续跑新目标（单 rAF 链，同帧单写）；NaN/Inf 目标拒收（与 writeScrollTop 空白防护对齐）。
- **单写者原则**：瞬时路径先 cancel 再写；锚定（spr/行高切换）与 maxScrollTop 钳制也先 cancel——几何变化下瞬时写入胜出。
- **开关（R2.3）**：localStorage `milocut:timeline-follow-smooth:v1`（M0-1.4 同族视图态键，不持久化到工程），**默认 false（瞬时）**；严格 `=== true` 解析，"1"/"yes" 等不误开。A/B 用户裁决后如改默认值回写 SPEC M2-1。
- **模式开关 reveal 维持瞬时**（裁决：布局重构非导航跳转）；basic 模式不受影响（smoothJumpEnabled 门控 isMulti）。

## 测试（新增 18）

- 纯模块（12）：常量与缓动；durationMs 0 直通单写；NaN/Inf 拒收；from→target 逐帧递增且精确落点；redirect 无叠加（单链收敛新目标）；cancel 停写；dispose 后全 API 忽略（无 rAF 泄漏）；inEchoWindow 激活/宽限/过期三态；新鲜实例无 from 直写；开关容错 6 变体（缺失/true/false/损坏 JSON/类型错/broken storage）。
- 编辑器集成（6）：smooth ON 跳转动画（起点钉住→首帧→精确落 376）；smooth OFF 瞬时（默认语义回归）；**播放时钟路径恒瞬时**；滚轮动画期取消；卸载无 rAF 泄漏；动画期 trusted scroll 不触发冷却（动画落点后续跳转正常跟随）。
- 既有 follow/回环冷却测试（smooth OFF 世界）零改动全绿。

## 门禁（本步实际输出）

| 命令 | 结果 |
|---|---|
| `uv run pytest` | **716 passed** ✅ |
| vitest 全量 | **743 passed / 1 failed**（744 总数；唯一失败仍为 P0-1 已登记挂载墙钟环境例，失败集合未扩大）✅ |
| `vue-tsc --noEmit` + `vite build` | 0 错误 ✅ |
| eslint | 0 errors 0 warnings ✅ |
| `uv run ruff check .` | All checks passed! ✅ |
| 红线五文件 diff | **空** ✅ |

## 未验证边界

- 真机 WebView 上 rAF 节流/掉帧下的手感（140ms 是否合适）与空白复现——beta.2 ★ 冒烟合并验证；A/B 默认值裁决输入回写 SPEC。
- 时间窗 100ms 宽限在低端机的 scroll 事件延迟覆盖为经验值，冒烟异常时优先复查此参数。

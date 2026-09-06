# Record: P2-5 M6 波形渲染管线第一阶段

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: SPEC M6-1/M6-2/M6-3 / 风险评审 §4.3 M6（rAF 回调禁读响应式触发调度、dpr 用 matchMedia）/ PRD B2

## 改动文件

| 文件 | 改动 |
|---|---|
| `frontend/src/utils/rafScheduler.ts`（新） | rAF 合帧调度器：窗口内多次 `schedule()` 合并为一次任务执行；`cancel()` 丢弃未执行任务；帧函数可注入（测试确定性） |
| `frontend/src/utils/rafScheduler.test.ts`（新） | 4 条（10 次 schedule → 1 次执行、执行后再调度、cancel 丢弃、无任务 cancel 幂等） |
| `frontend/src/composables/usePlaybackClock.ts`（新） | 播放时钟：原始时间域（非响应式，`getTime/subscribe/ingest`）+ `coarseTime` 粗粒度响应式镜像（播放中 ≥100ms 才写、暂停/seek 即时写、值相同跳过写）；`start/stop` 自建 rAF 循环供原模式播放；`now` 可注入 |
| `frontend/src/composables/usePlaybackClock.test.ts`（新） | 7 条（节流窗口、暂停即时、窗口过后恢复、值相同不写防循环、订阅/退订、循环随播放状态自停、stop 取消） |
| `frontend/src/components/waveform/WaveformCanvas.vue` | M6-1：全部重绘走 rafScheduler；ResizeObserver 回调缓存 CSS 尺寸，`draw()` 帧内零布局读；canvas.width/height 仅在 CSS 尺寸/dpr 变化时重设（`setTransform` 保 dpr 映射），消除每帧位图重分配；matchMedia `(resolution: N dppx)` 监听 dpr 变化（变化后重臂新分辨率查询 + 置位脏；addEventListener/addListener 双兼容）；删除 0.02s viewStart 去重 |
| `frontend/src/components/waveform/PlayheadOverlay.vue` | M6-3 重写：模板零响应式依赖（空壳 div），位置由播放时钟原始样本直写 `translate3d`；视图变化（缩放/滚动，暂停态）经显式 watch 重定位；containerWidth 经 ResizeObserver 缓存；clamp 语义与旧 playheadPercent 一致（出视区停靠边缘）；卸载退订 |
| `frontend/src/components/waveform/WaveformEditor.vue` | M6-2：层容器 pointermove/pointerleave → pending 样本（非响应式）→ rAF 刷 `pointer-events:none` 指示层（竖线 + 时间标签 textContent 直写）；容器 rect 缓存 + RO 失效，move 路径零布局读；hoverScheduler 卸载取消 |
| `frontend/src/components/waveform/PlayheadOverlay.test.ts`（新） | 6 条（挂载定位、时钟跟随、边缘 clamp、**零响应式依赖证明**、暂停态视图重定位、卸载退订） |
| `frontend/src/components/waveform/WaveformEditor.test.ts`（新） | 3 条（hover 显示指示线与时间、leave 隐藏、hover 不产生 seek/set-time） |
| `frontend/src/components/waveform/injectionKeys.ts` | 新增 `PLAYBACK_CLOCK_KEY` |
| `frontend/src/pages/WorkspacePage.vue` | M6-3 接线：`currentTime` 由 60Hz 响应式 ref 改为播放时钟 coarseTime；编辑模式控制器 publish 进时钟（`onTimeUpdate: (t) => clock.ingest(t)`）；原模式经 `watch([previewMode, videoPaused])` 启停时钟循环；demo 模式 watch 桥接 ref → ingest；`provide(PLAYBACK_CLOCK_KEY)` |

## 实现要点

- **60Hz 响应式断链（性能主收益）**：旧链路 编辑模式 rAF → `currentTime.value` 写 → WorkspacePage 整树重渲染（5 个模板消费点）+ Timeline/VideoControls/PlayheadOverlay 子树 patch，每秒 ~60 次。新链路：原始样本走时钟订阅（仅 overlay 的 transform 直写），`currentTime` 为 ≤10Hz coarse 镜像——7 个消费点代码零改动，重渲染频率降 ~6 倍；播放头渲染完全脱离 Vue。
- **原模式播放头顺带修复**：旧实现原模式仅靠原生 `timeupdate`（~4Hz）驱动，播放头阶梯抖动；时钟自建循环后原模式同样 60fps 平滑。
- **粗粒度精度权衡**：SegmentBlocksLayer 按指针分割 / ←→ 微调读取 currentTime，播放中最多滞后 100ms（暂停/seek 事件即时写，静止操作无滞后）；1x 速度下 0.1s 偏移可接受，批次冒烟确认。
- **demo 循环防护**：useDemoPlayback 直写 coarseTime ref；watch 桥接为 `ingest(t)`，ingest 内值相同跳过 coarse 写 → watch 不重触发（单测覆盖）。
- **WaveformCanvas 帧纪律**：draw() 内只读缓存的 CSS 尺寸（RO 回调更新），不调 getBoundingClientRect；rAF 回调不写任何响应式状态（风险评审 §4.3 红线）。

## 实现决策（对 plan/SPEC 的偏差记录）

1. **"10 次 scheduleDraw 仅 1 次 draw"以 rafScheduler 纯函数单测承载**：happy-dom 无 canvas 2d context（`getContext` 返回 null），组件级无法 spy draw 计数；合帧逻辑本身已抽取为可注入帧函数的独立模块，测试即等价覆盖。dpr 监听的真实跨屏行为归双平台冒烟。
2. **"播放期间 patch 计数为 0"以零响应式依赖测试承载**：PlayheadOverlay 新模板不含任何响应式绑定；测试将旧模板依赖的 playheadPercent 源（currentTime ref）突变后断言 DOM 不变——无依赖即无 patch，与逐帧计数等价且更稳。
3. **hover 预览宿主选 WaveformEditor 层容器**（非 SPEC 草案的"波形 pointermove"）：blocks 的 pointermove 会冒泡到容器，预览在全波形区可用；拖拽手势不受影响（预览层 pointer-events:none、只读不拦截，符合风险评审 §3.2 M6 缓解）。
4. **指示线时间标签格式用 formatTimeShort**（`M:SS`），非 formatTime 的毫秒精度——预览仅需秒级提示。
5. **useTimelineMetrics.playheadPercent/playheadVisible 保留导出**但生产侧已无消费方（仅测试与接口稳定）；M8/M9 清理时再评估去留。

## 验证命令与实际输出

```
cd frontend && bun run test   -> 313 passed（293 存量 + 4 rafScheduler + 7 clock + 6 PlayheadOverlay + 3 WaveformEditor）
cd frontend && bun run build  -> vue-tsc + vite 通过
bunx eslint <触及文件>         -> 0 errors（2 个 v-html warning 为 M9-3 已登记存量，非本次引入）
uv run pytest                 -> 550 passed（后端零改动，锚定确认）
```

## 未验证边界

- 快速滚动/缩放流畅度对比 beta.1 截录屏、播放中 CPU 占用对比 → 批次双平台冒烟 + `perf-beta2.md`（空闲 IPC/长任务指标同批回填）
- WKWebView 跨屏 dpr 切换（matchMedia 监听）真机实测；`will-change-transform` 播放头在 WKWebView 的合成器表现手测
- 编辑模式 2x 速播放时粗粒度高亮/分割读值滞后 100ms 的手感 → 冒烟确认

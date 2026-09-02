# Record: P2-4 peaks 共享与包络记忆化（Phase 2 / SPEC M4-3）

> 日期: 2026-09-02 · 分支: `dev-3.0.2-p2-4`（合入 `dev-3.0.2`）· 基点: P2-3/P2-5 合入后

## 完成内容

- `frontend/src/utils/waveformPeaks.ts`：
  - 新增纯函数 `computePeakSlice(peaks, viewStart, viewEnd, duration): PeakSlice | null`——把 WaveformCanvas.drawWaveform 的桶区间计算（floor/ceil + duration 缺失时 bps 回退）**原样抽取**，行为零变化；返回 `{startBucket, endBucket, bucketsPerSecond}` 供绘制与行级缓存共用。`widthPx` 参数裁决：SPEC 签名含 widthPx，但现行管线按可见桶全画（无按宽抽取），宽度抽稀属 MAW mipmap 预案——签名保持 4 参，差异登记（M8/M4-4 同类后置）
  - 新增 `clampDpr(dpr)`：dpr 钳 [1,2]（M4-3 裁决）
- 新建 `frontend/src/composables/usePeakSliceCache.ts`：行级缓存 `{rowIndex, widthPx, dpr}` 命中（key 内含 clampDpr，hidpi 变体共享条目）；LRU 语义（命中刷新 + 超限逐出最老），上限 64（可视行数 ≤ 视口+4，稳态不会触顶，仅防 resize 循环病理）；null 结果（空窗）同样缓存
- `WaveformCanvas.vue`：
  - 增可选 `peaksData` prop——提供时跳过自身 fetch（loadWaveform 与 waveformPath watcher 双守卫）；watch peaksData 变化：注入接管 / 清除回退 fetch 路径（媒体切换）
  - drawWaveform 改用 computePeakSlice（数值等价抽取）
- `WaveformRow.vue`：可选 `peaksData` prop 透传 WaveformCanvas（编排层单次 fetch + provide 属 P4-3 前置接线，beta.1 每行 fetch 为已接受临时状态）

## 测试

- `waveformPeaks.test.ts` 扩展 10 例（原 3 + 新 7）：窗口映射、分数窗 floor/ceil、bps 回退、末桶钳制、退化输入 null、6000 桶/60s 侧车的 10s 行切片、clampDpr 边界
- `usePeakSliceCache.test.ts` 新建 7 例：命中一次计算、键隔离、dpr cap 共享、null 缓存、clear、上限逐出、LRU 刷新存活
- `WaveformCanvas.peaks.test.ts` 新建 3 例：注入时 fetch spy 零调用（含 props 变更）、无注入走现状 fetch（一次、带 path）、注入清除回退 fetch

## 验证命令与实际输出

```
cd frontend && bun run test          -> Test Files 48 passed / Tests 595 passed（578 + 17 新增）
cd frontend && bun run build         -> ✓ vue-tsc + vite build
cd frontend && bun run lint          -> 0 errors 0 warnings
```

## 未验证边界

- 多行模式网络面板单次加载验收：待编排层 peaks provide 接线（P4-3 前置）后与总览条一起真机验证；届时回填 perf-baseline.md 的「peaks 单次 fetch」对账项

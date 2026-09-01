# Record: v3.0.1-beta.1（Phase 2 汇总）

> 日期: 2026-09-01 · tag: `v3.0.1-beta.1`（dev-3.0.1 @ 530ae91）

## 交付范围

Phase 2 堆叠渲染全量：useLaneLayout 布局与持久化、SegmentBlock 泛化（主副共用）、TrackLane 几何化重写（自 Timeline 摘除）、WaveformEditor 堆叠编排（单播放头贯穿 + wheel 全区 + >4 软提示）、Alt 语义（snap 反转 + trim-end.altKey 载荷）。

## 冒烟结果（用户确认）

- macOS：显示正常，副轨块与主轨同缩放对齐 ✅（2026-09-01，用户确认"显示没问题"）
- Windows WebView2：随下批次补验（用户放行推进）

## 门禁快照

- vitest 442（38 文件）/ pytest 663 / build / eslint 0 / ruff 0 —— 全绿

## 遗留

- Windows 冒烟清单项并入 beta.2 冒烟（wheel deltaMode 重点）

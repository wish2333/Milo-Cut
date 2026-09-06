# Record: P4-3 M11-3 波形缓存（peaks sidecar 双因子签名）

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M11-3 / PRD D3 / plan P4-3

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/ffmpeg_service.py` | 新增缓存层：`media_signature(path)`（`{size, mtime_ms}`，mtime 由 `st_mtime_ns` 整数换算避免浮点抖动）、`peaks_sidecar_path`（`media.mp4` → `media.peaks.json` 同目录 sidecar）、`write_waveform_cache`（写 `{version:1, media_signature, peaks}` 信封；媒体目录不可写返回 None 仅告警）、`load_waveform_cache`（存在性+版本+签名+非空 peaks 全核对才命中；任何异常一律 miss）、`read_peaks_file`（legacy 裸数组读取）。`generate_waveform` 本体未动（契约不变） |
| `main.py` | `_handle_waveform_generation` 接线：任务入口先探测 sidecar——**命中即跳过 ffmpeg 提取**，直接 `update_media_waveform(sidecar)` + media server 挂载 + 落盘保存，返回值附 `cached: true`；未命中走原生成路径，生成后从 waveform.json 读回 peaks 写 sidecar（best effort），`waveform_path` 指向 sidecar（写失败回退 legacy 路径）；`_finalize_and_save` 提取收尾公共段 |
| `tests/test_waveform_cache.py`（新） | 15 条：签名形状/内容变更 2、写读命中 1、无 sidecar miss 1、size 变 miss 1、**mtime 变同 size miss 1（双因子各自独立验证）**、媒体替换→miss→重生成→再命中 1、损坏 JSON/未知版本/空 peaks/签名形状缺失 miss 4、不可写目录回退 None 1、read_peaks_file 形状 1、**handler 级**（MiloCutApi `__new__` 模式 + monkeypatch `main.generate_waveform` 计数）：二次运行零 ffmpeg 调用且 `cached: true` 1、媒体替换后重生成 1 |
| `frontend/src/utils/waveformPeaks.ts`（新） | `parseWaveformPeaks(data)`：同时接受 legacy 裸数组与 sidecar 信封（`{peaks}`），形状不可识别返回 null（组件走 loadError 态） |
| `frontend/src/utils/waveformPeaks.test.ts`（新） | 3 条（裸数组/sidecar 信封/空与畸形拒绝） |
| `frontend/src/components/waveform/WaveformCanvas.vue` | `loadWaveform` 改用 `parseWaveformPeaks`（sidecar 命中后 media server 服务的是信封形状，前端必须识别） |

## 实现决策（对 plan/SPEC 的偏差记录）

1. **命中路径为「任务瞬时完成」而非「不建任务」**：SPEC 写"后端命中时不建 waveform 任务（探测逻辑在 Python 侧）"；`create_task` 由前端发起、协议面无 Python 侧拦截点，故探测落在任务 handler 入口——命中时任务在毫秒级完成（实测 0.84ms），不产生 ffmpeg 子进程与长任务事件。收益同原设计（新旧 frontend_dist 行为一致、旧前端也享受缓存），协议面更简单；偏差如实记录。
2. **waveform_path 直接指向 sidecar**（而非 sidecar↔waveform.json 双写）：峰值数据单一事实源，3 小时媒体避免 ~20MB×2 重复落盘；media server 服务任意路径 JSON，前端 `parseWaveformPeaks` 兼容新旧形状，存量工程（waveform.json 裸数组）零迁移继续可读。
3. **缓存纯增益、永不阻断**：sidecar 写失败（只读媒体目录/网络盘）仅告警，回退 legacy waveform.json；load 任何异常一律按 miss 重新生成——对齐 M2 持久化「失败仅告警」模式。

## 验证命令与实际输出

```
uv run pytest                              -> 593 passed（578 + 15）
uv run ruff check .                        -> All checks passed!
cd frontend && bun run test                -> 343 passed (34 files)（340 + 3）
cd frontend && bun run build               -> vue-tsc + vite 通过
```

缓存命中开销实测（6000 peaks ≈ 60s@100bps 量级，本机）：

```
load_waveform_cache 平均 0.844 ms/call —— 验收"二次打开波形就绪 < 200ms"余量 ~237 倍
```

## 未验证边界（归批次冒烟 / perf-final）

- ★ 真实长视频二次打开计时回填（验收方式原文；自动化等价已覆盖"命中零 ffmpeg"与 ms 级读回）
- 签名误命中率 0 的真机长尾：mtime 粒度量化文件系统上同秒同尺寸替换媒体的极端场景（双因子设计固有残余风险，SPEC 选型既定）
- 3 小时媒体 sidecar 体积与读回耗感的真机观测（6000 peaks 信封 ~0.5MB 量级，理论无虞）

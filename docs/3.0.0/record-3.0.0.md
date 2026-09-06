# Milo-Cut v3.0.0 实施总记录（正式版）

> **版本**: 3.0.0
> **分支**: `dev-3.0.0`（基线 `v3.0.0-base` = v2.4.0 @ origin/main）
> **计划**: [plan-v3.0.0.md](./plan-v3.0.0.md) · **需求**: [PRD](./PRD-v3.0.0.md) · **规格**: [SPEC](./spec-v3.0.0.md) · **风险评审**: [指南](./spec-v3.0.0-风险评审与实施指南.md)
> **日期**: 2026-08-30 ~ 2026-08-31
> **主题**: 数据保真 · 性能跃迁 · 架构还债 · 能力接线（地基重建版，不新增 AI 能力）

## 1. 四阶段完成总览

| 阶段 | 内容 | 门禁 | record |
|---|---|---|---|
| Phase 0 开工准备 | 分支/基线快照/迁移清单 | tag `v3.0.0-base` | [P0](./record-3.0.0-P0.md) |
| Phase 1 数据保真 | M1 词级保真 / M2 持久化安全 / M3 LLM 协议 | tag `v3.0.0-beta.1` | [P1-1](./record-3.0.0-P1-1.md) ~ [P1-5](./record-3.0.0-P1-5.md)、[beta.1](./record-3.0.0-beta.1.md)、[macOS 冒烟](./record-3.0.0-smoke-macos-1.md) |
| Phase 2 性能跃迁 | M5 分层撤销 / M4 bridge 批量事件 / M7 虚拟滚动+patch 细粒度 / M6 波形管线 | tag `v3.0.0-beta.2`（legacy undo 删除） | [P2-1](./record-3.0.0-P2-1-day1.md)~[day3](./record-3.0.0-P2-1-day3.md)、[P2-2](./record-3.0.0-P2-2.md)~[P2-5](./record-3.0.0-P2-5.md)、[beta.2](./record-3.0.0-beta.2.md) |
| Phase 3 架构还债 | M8 组件拆分 / M9 层级契约+lint / M10 project_service 分域 | tag `v3.0.0-rc` | [P3-1](./record-3.0.0-P3-1.md) ~ [P3-4](./record-3.0.0-P3-4.md)、[rc 冒烟](./record-3.0.0-smoke-macos-rc.md) |
| Phase 4 能力接线 | M11-1 words 消费 / M11-2 多轨 MVP / M11-3 波形缓存 / M3-6 工作流回滚 | 正式版（本文档） | [P4-1](./record-3.0.0-P4-1.md) ~ [P4-4](./record-3.0.0-P4-4.md) |

## 2. PRD §6 总验收核对表

| 项 | 要求 | 实际 | 结果 |
|---|---|---|---|
| pytest 全绿 | 新增 ≥25（基线 478） | **598 passed**（+120） | ✅ |
| vitest 全绿 | 撤销/patch/虚拟滚动新套件在列 | **343 passed**（undoRecords/projectPatch/virtualList/rafScheduler/clock/TrackLane 等新套件在列） | ✅ |
| perf 自动化项 | undo <5ms；打开/保存无回归 | undo p50 **1.188ms**；open **4.25ms** / save **2.74ms**；benchmark 全项持平或更优（[perf-final](./perf-final.md)） | ✅ |
| perf 真机项 | 1167 段 ≥55fps；波形期无 >50ms 长任务；空闲 IPC <4/s | macOS beta.2 已测（60fps / 0 / ≈4/s）✅；**Windows 补测挂账**（beta.2+rc 用户裁决先行模式） | ⏳ 待补测回填 |
| ruff | 0 问题 | 全仓 0（38 存量清零） | ✅ |
| bun run lint | 0 errors 0 warnings | 全仓 0/0 | ✅ |
| bun run build | 通过 | vue-tsc + vite 通过 | ✅ |
| ★ 双平台真机回归全清单 | dpr 跨屏/触控板/首启动/GB18030/断电恢复 | macOS rc 冒烟全绿（标准清单）；Windows 全清单待补测 | ⏳ 待用户轮次 |
| CHANGELOG / README / record 齐备 | - | 本文档 §3 承载 changelog 汇总（仓库无独立 CHANGELOG.md 惯例，对齐 2.2.1/2.4.0 发布模式）；README 增 v3.0.0 特性四节；`docs/3.0.0/` record 19 份齐备 | ✅ |
| 版本号 bump | - | pyproject.toml / frontend/package.json / uv.lock → 3.0.0（复刻 2.4.0 bump 模式） | ✅ |
| tag `v3.0.0` | 门禁全过 + 双平台闭环后打 | **待 Windows 补测闭环** | ⏳ |

## 3. Changelog（v3.0.0 汇总）

### 数据保真

- 删除转写 SRT 回灌，words/speaker 全链路存活；`update_transcript_meta` 落 engine/language
- split/merge 维护 words（对齐失败宁可缺失不可错位）；拆分吸附词边界（`snap_to_word` + toast 提示）
- parse_srt 编码回退链（utf-8-sig → gb18030 → latin-1），GB18030 导入不再崩溃
- 持久化安全：fsync + 双 bak 轮换 + 损坏自愈（`recovered_from` toast + 磁盘写回）+ [PROJECT_SCHEMA](../PROJECT_SCHEMA.md)
- LLM 可靠性协议：批账本（失败重试 1 次 + 覆盖缺口 toast，绝不静默）、批字符上限 4000、响应消毒、SSRF 校验、不透明 ID、温度 0.1 + 按路径覆盖
- LLM 纠错回贴：词级 SequenceMatcher 重对齐，局部改动保留原时间戳，<50% 相似整体清空
- 工作流失败回滚：步骤边界层快照跨会话持久化，「回滚本步 / 全部回滚」经 apply_undo 通道，revision 单调

### 性能

- 分层撤销（apply_undo 协议 + 前端 100 条层栈）：undo 主线程 p50 ~1.2ms（1167 段）
- bridge 批量事件（512KB 拆批保序）+ 自适应 tick（空闲 250ms）+ task:completed 载荷瘦身
- patch 细粒度化（段级原位合并 + 守门断言）+ 字幕列表虚拟滚动（1200 段 60fps）
- 波形渲染管线：rAF 合帧、canvas 按需重设、dpr matchMedia、命令式播放头、hover seek 预览
- 波形峰值 sidecar 缓存（`{size, mtime_ms}` 双因子）：二次打开 ~0.84ms 跳过 ffmpeg

### 架构还债

- SettingsModal 94.5KB → 6.4KB（5 tab + 2 子组件，懒挂载）；WorkspacePage 96.5KB → 61.3KB（popover/ASR 单源/handler 五组归口，目标降级 ~60KB 用户裁决关闭）
- z-index 五档 token + 26 处替换 + 菜单单实例互斥 + [DESIGN.md](../DESIGN.md) 层级契约 + styleLint 门禁
- project_service 分域（correction_service + migrations 独立模块，106.4KB → 81.7KB，<50KB 未达标挂 v3.1 裁决）
- ruff 38 → 0、bridge 死代码 ~90 行移除、workflow_engine 死代码删除、v-html 警告消除

### 能力接线

- 多轨字幕 MVP：SubtitleTrack/TrackBinding 模型 + 副轨 SRT 导入（300ms 容差自动绑定、id 命名空间隔离）+ Timeline 折叠只读 lane + 副轨 SRT 独立导出；构造保护契约测试锁定（tracks 不再被静默丢弃）
- 波形 hover 词高亮（二分定位、纯展示，卡拉OK 预览铺路）

### 兼容性承诺（全版本有效，风险评审 §3.1）

bridge API 信封与方法名不变；事件名只增不改；project.json 只增字段带默认值（旧工程零迁移）；settings 已保存值优先；旧 frontend_dist 搭新后端走运行时降级。

## 4. 已裁决偏差与挂账

| 项 | 裁决/状态 |
|---|---|
| M8-2 WorkspacePage <40KB 未达标（61.3KB） | 用户裁决 2026-08-31 降级 ~60KB 关闭；追加拆分挂 v3.1 |
| M10 project_service <50KB 未达标（81.7KB） | 随批次检查点由用户裁决（分析域拆分挂 v3.1 候选） |
| Windows（WebView2）补测 | beta.2/rc 两轮用户裁决「macOS 先行」，正式版 tag 前需闭环并回填 perf-final |
| 灰阶类存量迁移 / SuggestionPanel 菜单接入管理器 / 绑定联动编辑 | v3.1 backlog（DESIGN.md 约束新代码） |
| qwen3.8-flash 纠错 JSON 遵循弱 | beta.1 遗留观察；如持续可强化 prompt 约束（v3.1） |

## 5. 未验证边界汇总（真机轮次清单）

1. Windows（WebView2）：标准冒烟清单 + perf-final 真机表（fps/IPC/长任务/CPU）+ Phase 4 新功能（hover 词高亮/副轨/回滚弹窗/波形缓存二次打开）
2. macOS：Phase 4 新功能手测（同上四项；标准清单 rc 已全绿）
3. 30min 真实视频 whisper 转写 words 保真抽查（beta.1 遗留，夹具 words 已注入可对照）
4. v-memo 命中 / 单字编辑重渲染行数的 Vue DevTools 验证（两平台）
5. DeepSeek R1 think 块真实样本（消毒层单测已覆盖）

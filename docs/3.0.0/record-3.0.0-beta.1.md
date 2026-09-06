# Record: v3.0.0-beta.1 门禁通过

> 日期: 2026-08-30 · tag: `v3.0.0-beta.1`（基于 `dev-3.0.0` @ 1b769a0 + 本文档提交）

## 门禁核对

| 项 | 结果 |
|---|---|
| pytest | 524 passed（基线 478 + 46 新增） |
| vitest | 251 passed |
| bun run build | 通过（vue-tsc + vite） |
| ruff（触及文件） | 0 问题 |
| macOS 冒烟 | 通过（第二轮：转写自动保存 / Cmd 快捷键 + 撤销重做按钮 / 损坏项目自愈+恢复提示均确认修复） |
| Windows 持续验证 | 本机全程 pytest/vitest/build 门禁 |
| LLM 真实链路 | Qwen qwen3.8-flash 智能删除/纠错跑通，账本对账一致（record-P1-5） |
| 内部包 | PyInstaller onedir 构建成功 `dist/milo-cut/milo-cut.exe` |

## 未闭环项（转入后续批次，不阻塞 beta.1）

- 30min 真实视频 whisper 转写 words 保真抽查（视频已就位 `test/`，Phase 2 期间并行验证）
- DeepSeek R1 风格 think 块真实样本（消毒层已有单测覆盖）
- 性能基线对账表各项（待 Phase 2/4 对应模块落地后回填 perf-beta2 / perf-final）

## 遗留观察

- qwen3.8-flash 纠错 Mode A JSON 指令遵循弱（协议按设计重试+账本可见），如持续可强化 prompt 约束

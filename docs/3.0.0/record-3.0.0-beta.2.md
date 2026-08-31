# Record: v3.0.0-beta.2 门禁通过

> 日期: 2026-08-31 · tag: `v3.0.0-beta.2`（基于 `dev-3.0.0`）
> 范围: Phase 2 全部（M5 分层撤销 / M4 bridge 批量事件 / M7-1 patch 细粒度 / M7-2 虚拟滚动 / M6 波形渲染管线）

## 门禁核对

| 项 | 结果 |
|---|---|
| pytest | 550 passed |
| vitest | 311 passed（29 文件；含 undo 千段规模自动化） |
| bun run build | 通过（vue-tsc + vite） |
| ruff（触及文件） | 0 问题 |
| eslint（触及文件） | 0 errors（2 个 v-html warning 为 M9-3 已登记存量） |
| macOS 冒烟（WKWebView） | **全绿**：滚动 60fps（1200 段）、波形期长任务 0、空闲 IPC ≈4/s（250ms 降档生效）、undo/Cmd 链路/千段跳转/hover 预览/播放头手感正常 |
| Windows 冒烟（WebView2） | **待后续补测**（用户裁决 2026-08-31 先行放行 beta.2；补测后回填 perf-beta2.md） |
| 自动化性能 | undo 主线程 p50 1.3–2.9ms（目标 <5ms）；apply_undo 后端 p50 3.96ms；千段 50 编辑/50 undo 回放回到初态；open 4.8ms / save 3.4ms（P1-4 复核通过）——详见 `perf-beta2.md` |

## 本批收尾改动（legacy undo 路径删除）

按 P2-1 Day 3 既定计划（tag `pre-undo-cleanup` 回滚锚点已打，且 beta.2 冒烟通过）：

- `useUndoRedo.ts`：删除 legacy 全量 JSON 快照栈（legacyUndoStack/legacyRedoStack）、`isUndoV2` 分支、`UndoOutcome.project` 字段；undo/redo 仅走 apply_undo 通道（上限 100 条不变）
- `WorkspacePage.vue`：删除 `undoV2Enabled` ref、settings 读取、undo/redo 的 res.project 分支
- `main.py`：apply_undo 移除 `undo_v2` 门禁；`core/config.py`：移除 `undo_v2` 键（已存 settings.json 中的残留键无消费方，无害）
- 测试：删除 legacy 路径 2 条 + flag 切换 1 条（vitest 314 → 311）；后端无 flag 测试需动

## 冒烟辅助产物

- `test/test_video_long_1200segs.srt`：1200 段 / 覆盖 31.8min 长视频的千段列表夹具（SRT 导入即得，无需转写）
- `scripts/fabricate_words.py`：向既有 project.json 注入合成 words（CJK 单字/拉丁整词、按字长比例分配时间、真实 schema 校验自测通过）；已对 long 项目注入 1204 段 / 18162 词，供 M1-4 吸附拆分与未来 M11-1 词高亮冒烟；注入前备份 `project.json.pre-words.bak`

## 遗留项（不阻塞 beta.2）

- Windows（WebView2）冒烟补测 → 结果回填 `perf-beta2.md`
- 1167 段单字编辑 v-memo 命中的 Vue DevTools 验证（两平台均待测）
- 30min 真实视频 whisper 转写 words 保真抽查（beta.1 遗留；夹具 words 注入为替代路径，真实 ASR 抽查仍建议在 rc 前做一次）
- DeepSeek R1 风格 think 块真实样本（消毒层已有单测覆盖）

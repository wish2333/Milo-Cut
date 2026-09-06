# Record: Phase 1 macOS 冒烟问题修复

> 日期: 2026-08-30 · 分支: `dev-3.0.0` · 依据: 用户 macOS 首轮冒烟反馈

## 冒烟结论

- 通过: 其他回归项（转写/波形/编辑/导出/设置等）全部通过
- TSM `AdjustCapsLockLEDForKeyTransitionHandling` 日志: macOS 系统级键盘 LED 日志噪音，与 App 无关，**不处理**
- 3 个问题修复见下

## 问题与修复

### 1. 转写完成后没有自动保存（M1-1 回归）

- **根因**: 旧链路中 SRT 回灌的 `import_srt → _mark_dirty → PROJECT_DIRTY` 恰好触发了前端 2s 防抖自动保存；M1-1 删除回灌后该信号丢失
- **修复**: `_handle_transcription` 在 `update_transcript_meta` 成功后显式 `self._emit(PROJECT_DIRTY)`
- **测试**: `test_transcription_emits_project_dirty`（断言事件队列收到 `project:dirty`）

### 2. macOS 下 undo/redo 快捷键无反应 + 需要实体按钮

- **根因**: `handleGlobalKeydown` 只判 `e.ctrlKey`，macOS 的 Cmd 修饰键未覆盖（⌘S/⌘F 同样受影响）
- **修复**: 统一 `const mod = e.ctrlKey || e.metaKey`（s/z/y/shift+z/f 五处）
- **新增**: 顶栏 Save 按钮左侧增加「↩ 撤销」「↪ 重做」实体按钮，接 `canUndo/canRedo` 禁用态

### 3. 破坏 project.json 后首页项目消失 + 拖拽打开无恢复提示

- **根因 A**: `get_recent_projects` 遇到损坏 JSON 直接 `continue`，项目从列表消失，用户失去入口
- **修复 A**: 损坏时回退读 `.bak.1/.bak.2` 的元数据，条目标记 `corrupted: true`；WelcomePage 显示「主文件损坏，将从备份恢复」徽标
- **根因 B**: App.vue 拖拽打开分支对失败（非 MEDIA_NOT_FOUND-with-path）静默、对 `recovered_from` 也不提示
- **修复 B**: 失败 → toast 错误信息；`recovered_from` 存在 → toast「项目文件损坏，已从备份恢复」
- **测试**: `test_corrupt_project_still_listed_with_bak_meta`

## 其他

- 长视频标准由 60min 放宽至 **30min**（用户要求），视频已就位 `test/`
- 验证: pytest 523 全绿 / vitest 251 / build / ruff 触及文件 0 问题

## 待 macOS 复测清单

1. 转写完成 ~2s 后状态栏出现保存指示（或关开项目后数据仍在）
2. Cmd+Z / Cmd+Shift+Z / 顶栏撤销重做按钮（含禁用态）
3. 手工破坏 project.json → 重启 App → 最近列表仍有条目并带损坏徽标 → 点击打开 → toast 恢复提示
4. 拖拽 project.json 打开损坏项目 → toast 恢复提示

## 补充修复（round 2，2026-08-30）

- **用户观察**: 不重启 App 时最近列表打开不恢复；重启后"信息恢复"但 project.json 文件本身仍是坏的——判断正确，恢复只读了 bak 到内存，磁盘主文件从未被修复写回
- **修复**: `open_project` 恢复成功后立即 `save_project()` 自愈写回主文件（自愈失败仅告警不阻断打开）；WelcomePage 最近列表打开路径同样补「已从备份恢复」toast
- **测试**: `test_open_repairs_corrupt_main_file_on_disk`（恢复后再次打开不再报 recovered_from，证明磁盘已修复）
- 验证: pytest 524 全绿 / vitest 251 / build / ruff 0 问题

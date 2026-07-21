# Milo-Cut v2.4.0 UI 优化实施记录

> **版本**：v2.4.0  
> **分支**：`codex/2.4.0`  
> **基线**：v2.3.2  
> **日期**：2026-07-21  
> **类型**：UI Design System + P0 Visual Consistency

## 1. 完成范围

本阶段依照以下文档实施：

- `docs/2.4.0/ui-audit-report-2.4.0.md`
- `docs/2.4.0/ui-design-standard-2.4.0.md`
- `docs/plans/2026-07-21-milo-cut-2.4.0-ui-optimization.md`

未修改 Python backend、bridge API、Project/ProjectPatch、TaskManager 或导出业务逻辑。

## 2. 代码修改摘要

### 2.1 共享视觉基础

修改 `frontend/src/style.css`：

- 增加 `primary-hover`、`primary-soft`、控件高度和控制级/面板级圆角 token。
- 将字体栈调整为 macOS 系统字体 + `PingFang SC` 回退。
- 新增 `mc-button-primary`、`mc-button-secondary`、`mc-button-quiet`、`mc-button-danger`。
- 增加全局 `:focus-visible` 和文本选择样式。
- 保留现有 reduced-motion 页面过渡逻辑。

### 2.2 页面与组件

| 模块 | 实施内容 |
|---|---|
| Welcome | 最近项目改用语义 token；设置按钮增加中文 tooltip/aria-label；导入按钮和 focus 状态统一 |
| Workspace | 视频/字幕/波形层级改用 Canvas、Parchment、Surface token；去除字幕区外层卡片化圆角；导入、转写、静音检测、导出等操作统一按钮语义；关键 loading 文案中文化 |
| Timeline | 标题、空状态、选择模式、侧栏和编辑工具使用统一 token；空状态改为中文并给出下一步操作 |
| TranscriptRow | 行高提升到 52px；正文使用 16px；时间码使用 muted mono；增加键盘 focus 和 Enter/Space 操作；状态背景改用 pending/confirmed/rejected token |
| SilenceRow | 时间轴行高提升；静音状态背景改用语义 token；保留原有状态行为和测试覆盖 |
| SuggestionPanel | 面板改用 Parchment；分析修正提示使用 primary-soft；确认/忽略按钮改用 primary/secondary 语义；确认状态仍保留绿色语义文本 |
| VideoControls | 深色控制条、进度条、播放头和弹出菜单统一使用视频 surface 与 Action Blue |
| Export | 视频导出作为唯一主按钮；音频、字幕、精华和时间线格式改为 secondary；边框、进度、状态和项目信息使用语义 token |

## 3. 验证结果

### 前端单元测试

```text
Test Files  19 passed (19)
Tests       241 passed (241)
```

执行命令：

```bash
cd frontend && bun run test
```

### 前端生产构建

```text
vite build: passed
101 modules transformed
```

执行命令：

```bash
cd frontend && bun run build
```

### 静态检查

- `git diff --check`：通过
- 未修改 `docs/demo/`
- 未修改 backend、bridge 和数据模型
- 绿色文本仅保留给“已确认/已保留/差异插入”等语义状态，不用于普通主按钮

## 4. 未完成项与后续建议

以下内容不纳入本次 P0 检查点：

1. 设置弹层、字幕修正全屏页和少量右键菜单仍有历史 Tailwind 原始类，建议作为 P1 做完整 token 收敛。
2. Export 页面仍保留英文技术选项名称（OTIO、Crossfade、Clean Export 等），建议后续补齐产品级中文文案。
3. 尚未进行真实 PyWebView 窗口下的截图回归；建议在 macOS 和 Windows 各执行一次导入、播放、编辑、导出手动流程。
4. 尚未改变布局比例和建议面板抽屉逻辑，避免在没有真实窗口截图和用户反馈时进行高风险重构。


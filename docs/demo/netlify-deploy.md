# Milo-Cut 浏览器 Demo：Netlify 部署

Demo 使用 `VITE_DEMO_MODE=true` 启用浏览器内存 runtime，不需要 Python、FFmpeg、真实媒体文件或外部 API。

## 连接 Git 仓库

1. 在 Netlify 选择 **Add new site → Import an existing project**。
2. 选择 Milo-Cut 仓库和 demo 分支 `codex/demo-netlify`（合并后也可以选择目标发布分支）。
3. Build settings 保持由仓库根目录的 `netlify.toml` 提供：
   - Build command：`cd frontend && bun install --frozen-lockfile && bun run build`
   - Publish directory：`frontend_dist`
   - `VITE_DEMO_MODE=true`
   - `BUN_VERSION=1.3.10`
4. 点击 **Deploy site**。

## 本地复现 Netlify 构建

```bash
cd frontend
bun install --frozen-lockfile
bun run build
```

确认仓库根目录生成 `frontend_dist/index.html`。也可以用 `bun run preview` 查看静态构建。

## 验收清单

- 首屏直接进入“浏览器演示模式”，不等待 pywebview bridge。
- Network 中没有 `.mp4`、`.webm`、`.wav`、`.mp3` 或 waveform JSON 请求。
- 播放、时间轴 seek、字幕编辑、建议确认/驳回、纠错审阅、工作流冲突和模拟导出可操作。
- “重置演示”可以在不刷新页面的情况下恢复 fixture。
- 模拟导出只显示成功提示，不创建媒体文件或发起大文件下载。
- `netlify.toml` 的 SPA fallback 可避免未来增加路由后刷新 404。

## 注意事项

Demo 不承诺真实上传、ASR、LLM、FFmpeg 编码和项目持久化能力；这些入口会显示“该功能仅在桌面版可用”或使用确定性的内存模拟。Netlify 环境不要配置真实 LLM key，避免误以为 Demo 会发起外部请求。


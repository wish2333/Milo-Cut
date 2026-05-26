# Milo-Cut

> 把 1 小时杂乱粗录，变成 40 分钟干净可剪素材。像改文档一样剪视频。

Milo-Cut 是一款面向粗录视频的本地 AI 粗剪预处理器。自动检测静音、口误、口头禅、重复片段，用户确认后导出干净素材。全程本地处理，无需上传。

## 功能特性

- **静音检测** -- 基于 FFmpeg 的静音检测，可配置阈值和时长
- **口头禅检测** -- 可自定义词表，正则匹配标记高频口头禅
- **口误触发词检测** -- 识别"不对重来""说错了""重新说"等口误触发词
- **SRT 字幕导入与编辑** -- 导入已有字幕，内联编辑文本，删除文本即删除视频片段
- **波形可视化** -- 基于 Canvas 的波形显示，叠加片段标记
- **视频预览** -- 内置播放器，支持字幕叠加和播放控制
- **多格式导出** -- MP4（快速复制或精确重编码）、SRT、OTIO、EDL、FCPXML/Premiere XML
- **全局搜索替换** -- 批量查找替换字幕文本
- **本地优先** -- 所有处理在本地完成，数据不离开设备

## 快速开始

### 环境要求

- Python 3.11+
- [UV](https://docs.astral.sh/uv/) 包管理器
- [Bun](https://bun.sh/)（前端构建）
- FFmpeg 和 FFprobe（需在 PATH 中或在设置中配置路径）

### 开发模式

```bash
# 一键启动（自动安装依赖，启动开发服务器 + 桌面窗口）
dev.bat          # Windows
./dev.sh         # macOS/Linux

# 或手动启动：
uv run python main.py
```

### 构建打包

```bash
uv run build.py              # 构建桌面应用（onedir 模式）
uv run build.py --onefile    # 构建单文件可执行程序
uv run build.py --clean      # 先清理构建产物再打包
```

### 运行测试

```bash
# 后端测试（pytest）
uv run pytest tests/ -v

# 前端测试（vitest）
cd frontend && bun run test
```

## 架构概览

```
milo-cut/
  main.py              # 入口 + API 桥接层（约 30 个暴露方法）
  core/                # Python 后端服务
    project_service.py # 项目 CRUD、片段编辑、持久化
    export_service.py  # 基于 FFmpeg 的视频/音频/字幕导出
    ffmpeg_service.py  # ffprobe/ffmpeg 封装、静音检测、波形生成
    analysis_service.py# 口头禅和口误触发词检测
    subtitle_service.py# SRT 解析（支持 UTF-8、GB18030、BOM）
    task_manager.py    # 后台任务执行，支持进度报告和取消
    media_server.py    # 本地 HTTP 服务器，用于视频流传输
    models.py          # Pydantic v2 数据模型
  pywebvue/            # 自定义 pywebview 桥接框架
  frontend/            # Vue 3 + TypeScript 单页应用
    src/
      bridge.ts        # Python <-> JS 通信层
      pages/           # WelcomePage（导入）、WorkspacePage（编辑）
      components/      # 波形编辑器、字幕行、时间轴
      composables/     # useProject、useEdit、useExport、useAnalysis 等
```

**通信机制**：Python 通过 `@expose` 装饰器暴露方法，前端通过 `bridge.call()` 调用。Python 通过 `_emit()` 向前端推送事件，前端通过 `onEvent()` 监听。

## 技术栈

| 层级 | 技术 |
|------|------|
| 桌面壳 | pywebview |
| 后端 | Python 3.11、Pydantic v2、Loguru |
| 前端 | Vue 3、TypeScript、Vite 6 |
| UI 框架 | TailwindCSS v4、DaisyUI v5 |
| 媒体处理 | FFmpeg / FFprobe |
| 打包工具 | PyInstaller |

## 目标用户

| 用户类型 | 典型素材 | 核心痛点 |
|---------|---------|---------|
| 口播博主 / 知识博主 | 30-90 分钟口播视频 | 口误多、停顿多、重复表达 |
| 课程录制者 / 教培团队 | 45-120 分钟录屏+讲解 | 讲错重讲、长时间停顿 |
| 播客 / 访谈剪辑师 | 60-180 分钟多人对话 | 找重点片段耗时、去废话 |
| 企业培训视频编辑 | 30-60 分钟内训录像 | 隐私敏感需本地处理 |
| 直播切片运营 | 2-6 小时直播录像 | 找高能片段、批量去冗余 |

## 开源协议

[GPL-3.0](LICENSE)

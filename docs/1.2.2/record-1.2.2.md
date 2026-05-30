# Milo-Cut 1.2.2 Development Record

---

## Overview

1.2.2 版本聚焦于 macOS 平台适配，核心目标：

1. macOS 打包为 .app bundle，双击即可运行
2. macOS 子进程控制台不弹窗、系统 ffmpeg/uv 可检测、打开数据目录不报错
3. macOS 适配 ASR 引擎设备选项：Whisper 使用 MPS、Qwen3 新增 Apple Silicon MLX 插件
4. 修复 MLX 转录结果对齐重叠问题

---

## Commit Message

```
feat(macos): macOS .app 打包 + MLX ASR 引擎 + MPS 设备支持

- app.spec 添加 BUNDLE 目标，build.py 默认构建 .app bundle
- 修复 macOS 子进程 start_new_session 控制台弹窗
- 修复 _fix_macos_path() 注入 shell PATH 使 ffmpeg/uv 可检测
- 修复 open_data_directory 跨平台兼容（macOS open / Linux xdg-open）
- 修复 asr_service._asr_script() 使用 sys._MEIPASS 定位打包后脚本
- 打包时 DevTools 默认关闭（debug=False when frozen）
- 新增 plugin-qwen-mlx 插件（mlx-qwen3-asr[aligner]，无 PyTorch 依赖）
- 新增 mlx_transcribe.py 使用 MLX Session API 转录
- 新增 transcribe_with_mlx() 分发逻辑
- macOS Whisper 设备默认 Auto (MPS)，隐藏 CPU 选项
- macOS Qwen3 CPU 设备默认 MPS，支持 float16，隐藏 CPU 选项
- macOS 隐藏 CUDA/GPU 选项和不适用的 compute type
- 修复 MLX _split_into_subtitle_segments current_time 未推进导致重叠
- 所有平台相关改动通过 isDarwin/sys.platform 条件隔离，不影响 Windows
```

---

## Files Modified Summary

| 文件 | 改动说明 |
|------|---------|
| `app.spec` | 添加 BUNDLE 目标生成 Milo Cut.app；macOS 打包 asr_scripts datas |
| `build.py` | 移除 --app 标志，默认 onedir 构建 .app；macOS asr_scripts datas |
| `main.py` | debug=False when frozen；_fix_macos_path()；open_data_directory 跨平台；MLX 转录分发 |
| `core/plugin_manager.py` | 新增 plugin-qwen-mlx 注册；list_plugins() 平台过滤；_subprocess_kwargs macOS start_new_session |
| `core/asr_service.py` | 新增 transcribe_with_mlx()；_asr_script() sys._MEIPASS 定位 |
| `core/asr_scripts/mlx_transcribe.py` | **新建** MLX 转录脚本（Session API、smart slicing、word 对齐） |
| `core/asr_scripts/qwen_transcribe.py` | MPS 设备支持 + float16 dtype |
| `core/ffmpeg_service.py` | _SUBPROCESS_KWARGS macOS start_new_session |
| `core/ffmpeg_presets.py` | 同上 |
| `core/export_service.py` | 同上 |
| `frontend/src/pages/WorkspacePage.vue` | isDarwin/isMlx 条件控制 device/compute 选项；MPS 设备；plugin_id 传递 |
| `frontend/src/components/workspace/SettingsModal.vue` | macOS 隐藏 CUDA/MLX 安装选项；设备/compute 过滤；MPS 支持 |
| `frontend/src/types/edit.ts` | asr_device 类型新增 "mps" |

---

## Merge Message

```
feat: v1.2.2 -- macOS .app 打包 + MLX ASR 引擎 + MPS 设备支持

核心特性:
- macOS 打包为 .app bundle，双击即可运行 (app.spec BUNDLE 目标)
- 新增 plugin-qwen-mlx 插件，基于 Apple MLX 框架的 Qwen3 ASR 引擎，无 PyTorch 依赖
- macOS Whisper 默认使用 MPS 设备加速，隐藏不适用的 CPU 选项
- macOS Qwen3 支持 MPS + float16，隐藏 CUDA/GPU 和不适用 compute type
- MLX 转录脚本: Session API、smart slicing、word-level 对齐

关键修复:
- macOS 子进程 start_new_session 控制台弹窗修复
- _fix_macos_path() 注入 shell PATH 使系统 ffmpeg/uv 可检测
- open_data_directory 跨平台兼容 (macOS open / Linux xdg-open)
- asr_service._asr_script() 使用 sys._MEIPASS 定位打包后脚本
- MLX _split_into_subtitle_segments current_time 未推进导致字幕重叠
- 打包时 DevTools 默认关闭 (debug=False when frozen)

新增文件:
- core/asr_scripts/mlx_transcribe.py -- MLX 转录脚本 (Session API)

修改 14 文件 | 所有平台改动通过 isDarwin/sys.platform 条件隔离，不影响 Windows
```

---

## Release Note (v1.2.2)

### macOS 原生应用

Milo-Cut 现已支持 macOS 平台，打包为标准 .app bundle，双击即可运行:

- macOS 应用包 (.app) 通过 PyInstaller BUNDLE 目标生成
- 修复打包后子进程控制台弹窗、系统 ffmpeg/uv 路径检测、数据目录打开等平台兼容问题
- 打包环境下 DevTools 默认关闭，提供更简洁的用户体验

### MLX ASR 引擎 (Apple Silicon)

新增专为 Apple Silicon 设计的 MLX 转写引擎:

- 基于 Apple MLX 框架的 Qwen3 ASR，无需安装庞大的 PyTorch 依赖
- 利用 MLX Session API 进行高效推理，支持 smart audio slicing 和 word-level 时间戳对齐
- macOS 上 Whisper 引擎默认使用 MPS 设备加速
- macOS 上自动隐藏不适用的 CUDA/GPU 选项和 compute type

### 修复

- 修复 MLX 转录结果中字幕时间戳重叠问题（current_time 未推进）
- 修复 macOS 上打开数据目录报错（改用 `open` 命令）
- 修复打包后 ASR 脚本路径定位失败（使用 sys._MEIPASS）
- 所有平台相关改动通过 `isDarwin`/`sys.platform` 条件隔离，不影响 Windows 现有功能

 Context

 Milo-Cut 导出模块存在结构性缺陷: 所有编码器统一使用 -crf 参数（硬件编码器应使用
 -cq/-qp），缺少像素格式探测和容器优化（movflags +faststart），前后端默认值不一致。参照 ff-intelligent-neo 2.1.0+
 的编码器注册表机制进行改造。

 实施步骤

 Step 1: 新建 core/ffmpeg_presets.py -- 编码器配置单一事实来源

 创建新文件，包含:
 - ENCODER_QUALITY_MODE: 编码器 -> 质量模式映射 (crf/cq/qp/q)
 - ENCODER_RECOMMENDED_QUALITY: 编码器 -> 推荐质量值
 - ENCODER_QUALITY_RANGE: 编码器 -> 质量值范围
 - QUALITY_FLAG_MAP: 质量模式 -> FFmpeg 标志 (-crf/-cq/-qp/-q:v)
 - ENCODER_FALLBACK_CHAIN: 编码器回退链
 - get_quality_args(codec, crf) -> list[str]: 根据编码器生成正确的质量参数
 - select_pixel_format(media_info, user_override) -> str: 像素格式探测
 - check_encoder_availability(ffmpeg, codec) -> bool: 编码器可用性检查
 - get_fallback_codec(ffmpeg, requested) -> str: 获取可用的回退编码器

 Step 2: 修改 core/ffmpeg_service.py -- probe_media 增加 pix_fmt

 在 probe_media 函数中，从视频流提取 pix_fmt 字段，添加到返回的 data dict 中。

 Step 3: 修改 core/export_service.py -- FFmpeg 命令构建

 - export_video(): 导入 ffmpeg_presets 模块，使用 get_quality_args() 替代硬编码 -crf，添加 -pix_fmt 和 -movflags
 +faststart
 - export_video() 签名: preset 默认值从 "fast" 改为 "medium"
 - _extract_segment(): 新增 video_codec/preset/crf 参数，使用 get_quality_args() 生成质量参数

 Step 4: 修改 main.py -- 导出任务处理

 - _handle_export_video(): 导入 get_fallback_codec，导出前检查编码器可用性并自动回退
 - _handle_export_video(): preset 默认值从 "fast" 改为 "medium"
 - 新增 get_encoder_metadata() @expose 方法，返回编码器元数据供前端使用

 Step 5: 修改 frontend/src/components/export/EncodingSettings.vue

 - 从后端 get_encoder_metadata API 获取编码器元数据
 - 编码器切换时自动应用推荐质量值 (E-5)
 - CRF 滑块范围根据编码器动态调整 (E-6)
 - 质量标签显示正确的质量模式名称 (CRF/CQ/QP)

 Step 6: 修改 frontend/src/pages/ExportPage.vue

 - handleExportVideo(): 监听 encoder:fallback 事件，提示用户编码器回退

 关键文件

 ┌─────────────────────────────────────────────────────┬──────────────────────────────────┐
 │                        文件                         │               操作               │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────┤
 │ core/ffmpeg_presets.py                              │ 新建 -- 编码器配置中心           │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────┤
 │ core/ffmpeg_service.py                              │ 修改 -- probe_media 增加 pix_fmt │
 ├─────────────────────────────────────────────────────┼──────────────────────────────────┤
  优先级调整为 P0(E-1/E-2) > P1(E-3/E-4) > P2(E-5/E-6) > P3(E-7)。
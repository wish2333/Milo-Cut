# Milo-Cut PRD v0.2

## 1. 产品背景

### 1.1 问题定义

口播/课程/访谈/直播等粗录视频的后期处理中，**素材清洗**（去停顿、去口误、去重复、去废话）占总创作时间 40% 以上，且高度重复。现有工具要么仅依赖静音检测（无法识别有声废话），要么功能过重/云端依赖（如 Premiere、Descript），要么缺乏中文口播优化。

### 1.2 产品定位

> **一款面向粗录音视频的本地 AI 粗剪预处理器。**
> 导入粗录视频 -> 自动转写 -> 标记停顿/口误/重复/废话 -> 用户确认 -> 导出干净素材。
> 不是完整剪辑软件，而是"录完第一步打开的 AI 清洗工具"。

一句话宣传语：
> **把 1 小时杂乱粗录，变成 40 分钟干净可剪素材。像改文档一样剪视频。**

### 1.3 核心差异化

1. **中文口播深度优化**：识别口误、重说、废话、口头禅
2. **本地优先**：隐私友好、导入即用、核心功能不上传音视频
3. **字幕 + 静音 + 语义三层融合**：不仅知道哪里安静，还知道哪里没价值

---

## 2. 目标用户

| 用户类型 | 典型素材 | 核心痛点 |
|---------|---------|---------|
| 口播博主 / 知识博主 | 30-90分钟口播视频 | 口误多、停顿多、重复表达 |
| 课程录制者 / 教培团队 | 45-120分钟录屏+讲解 | 讲错重讲、长时间停顿 |
| 播客 / 访谈剪辑师 | 60-180分钟多人对话 | 找重点片段耗时、去废话 |
| 企业培训视频编辑 | 30-60分钟内训录像 | 隐私敏感需本地处理 |
| 直播切片运营 | 2-6小时直播录像 | 找高能片段、批量去冗余 |

**首批聚焦**：口播博主 + 课程录制者（痛点最明确、需求最强）

**暂不服务**：影视混剪、多机位综艺、特效包装、高级广告片

---

## 3. 核心场景

| # | 场景 | 用户操作 | 预期效果 |
|---|------|---------|---------|
| 1 | 删除长停顿 | 导入视频 -> 自动标记 -> 确认导出 | 1小时素材减少5-15分钟无效停顿 |
| 2 | 删除口头禅 | 自动识别"嗯啊然后就是" -> 一键全删 | 清除高频口头禅，无残留 |
| 3 | 标记口误废片段 | 检测"不对重来""说错了"后内容 -> 建议删除 | 自动找到口误后的废弃段落 |
| 4 | 标记重复讲述 | 检测相似段落 -> 建议保留最优版本 | 消除重复表达 |
| 5 | 导出给精剪软件 | 确认后导出 MP4+SRT+FCPXML | 在 Pr/达芬奇/FCP 中继续精剪 |

### 成功指标

- 1小时素材首次粗剪时间减少 **50%+**（对比纯手工听+剪）
- 自动建议的误删率低于 **10%**
- 用户可在 **3步内** 导出 MP4+SRT（导入->确认->导出）
- 用户可在 **5分钟内** 完成首次导入到转写的全流程

---

## 4. 产品目标与非目标

### 做

- 本地 ASR 转写 + 字幕编辑
- 静音/口头禅/口误/重复 自动检测与建议
- 文本标记式交互（删文本 = 删视频片段）
- MP4 + SRT + 剪辑工程文件导出
- 模块化步骤流程（可逐步执行、可跳过）
- 原片/剪后对比预览

### 不做（MVP 阶段）

- 多轨复杂时间线
- 特效、转场、滤镜、美颜
- 自动一键成片（AI 只建议，用户确认）
- 云端协作 / 云端存储
- 素材库管理 / 项目管理
- 短视频模板 / 花字 / 音乐卡点
- LLM 跑题检测 / 章节生成 / 短视频切片推荐

---

## 5. 功能优先级

### P0 - MVP 必须

| 功能 | 说明 |
|------|------|
| 视频导入 | 拖拽导入 MP4/MOV/MKV，自动提取音频、生成媒体信息 |
| 导入已有 SRT | 用户手动上传 SRT 字幕文件，解析为带时间戳的字幕段 |
| 静音检测 | FFmpeg silencedetect，标记超过阈值的停顿段 |
| 静音+字幕同步显示 | 静音段与字幕段在时间轴上对齐显示，用户可交叉验证并调整时长 |
| 口头禅检测 | 可配置词表，正则匹配标记 |
| 口误触发词检测 | "不对重来""说错了""重新说"等规则匹配 |
| 字幕列表 + 确认/拒绝 | 显示所有建议，默认标记删除，用户取消误判 |
| 导出 MP4（精确模式） | 重新编码，保证帧级切点准确 |
| 导出 SRT | 标准字幕文件 |

### P1 - MVP 增强

| 功能 | 说明 |
|------|------|
| 本地 ASR 转写 | FunASR 默认 / faster-whisper 可选，生成带时间戳字幕（句级+词级） |
| 重复句检测 | sentence-transformers 文本相似度 |
| VAD 增强静音检测 | Voice Activity Detection 与 silencedetect 交叉验证，降低误删率 |
| 视频预览 + 字幕叠加 | HTML5 video 播放 + 实时字幕 |
| 波形可视化（简化版） | 静态波形图 + 颜色标记段 |
| 原片/剪后切换预览 | Shift+Space 快速对比 |
| 导出 MP4（快速模式） | -c copy，关键帧级粗剪，速度优先 |
| 全局搜索替换 | 字幕文本批量替换 |

### P2 - MVP 后

| 功能 | 说明 |
|------|------|
| FCPXML / Premiere XML / EDL 导出 | 专业剪辑软件衔接 |
| 文稿对齐 | 有讲稿时自动匹配、找脱稿/漏读 |
| 章节自动生成 | LLM 辅助 |
| 短视频切片建议 | 找高价值片段 |
| 批量处理 | 多视频队列 |
| LLM 跑题检测 / 粗剪评分 | 可选云端增强 |
| 本地模型管理 UI | 下载/切换 ASR 模型 |
| 插件化规则系统 | 自定义分析规则 |

---

## 6. 用户流程

```
[导入视频] --> [导入SRT] --> [智能分析] --> [确认编辑] --> [导出]
     |             |              |              |             |
  拖拽/选择     手动上传       可分步执行      核心交互      多格式
  自动提取     解析时间戳     静音/口头禅     取消误判      MP4/SRT
  媒体信息     校验格式       /口误 + 同步    批量确认      /FCPXML等
```

**模块化原则**：每个步骤可独立执行、可跳过、可在步骤内手动介入。不是一键全流程。MVP 阶段用户手动提供 SRT 字幕，ASR 转写在 P1 阶段作为增强功能加入。

---

## 7. 关键交互

### 7.1 默认标记 + 取消选择

分析完成后，所有建议删除项默认标记为 `pending`（黄色），用户逐条或批量确认。确认后变为 `confirmed`（红色），拒绝后变为 `rejected`（绿色）。

用户也可以反转模式：默认全部拒绝，手动勾选需要删除的。

### 7.2 误删防护（三道保险）

1. **导出前摘要**：第一次导出前强制显示"将删除 X 段，共 Y 分钟（占总量 Z%）"
2. **状态分级**：自动建议 -> pending，用户确认 -> confirmed，只有 confirmed 才进入导出
3. **异常检测提示**：
   - 删除段超过总时长 40% 时弹窗警告
   - 单段删除超过 60 秒时弹窗确认
   - 连续删除超过 3 段时弹窗确认

### 7.3 文本即剪辑

字幕编辑器中，选中一行文字即定位视频到对应时间点。删除一行文字 = 将该时间段标记为删除。合并两行 = 合并时间段。回车拆分 = 在光标位置拆分时间段。

### 7.4 步骤控制器

顶部步骤条显示当前进度：`导入 -> 转写 -> 分析 -> 编辑 -> 导出`。已完成步骤显示绿色勾，当前步骤高亮，未到达步骤灰色。用户可以点击已完成的步骤回退查看。

---

## 8. 功能需求

### 8.1 素材导入

- 支持格式：MP4 / MOV / MKV / MP3 / WAV
- 导入方式：拖拽、文件选择对话框
- 自动操作：提取音频（WAV 16kHz mono）、获取媒体信息（时长/分辨率/帧率/编码）
- 可选：生成代理文件（720p 低码率用于预览加速）

### 8.2 字幕导入（MVP 核心）

- 支持格式：SRT（MVP 必须），VTT/SUB（P1）
- 导入方式：拖拽或文件选择
- 自动解析：提取时间戳 + 文本内容，生成标准 segment 列表
- 格式校验：检测时间戳格式、编码、序号连续性，异常时提示具体问题
- 时间轴校验：检测字幕总时长是否与视频时长匹配，偏差超 10% 时警告
- 导入后即可进入分析和编辑流程，无需 ASR

### 8.3 语音识别（P1 增强）

- 默认引擎：FunASR（中文优先）
- 可选引擎：faster-whisper（多语言/中英混合）
- 输出：句级时间戳 + 可选词级时间戳 + 置信度
- 进度：通过事件系统推送进度百分比
- 支持参数：语言选择、模型大小、VAD 开关
- ASR 完成后自动进入字幕编辑流程

### 8.4 智能分析

**规则层（确定性，高置信度）：**

| 类型 | 示例 | 置信度 |
|------|------|--------|
| 静音 | 超过 N ms 的低音量段 | 0.95 |
| 口头禅 | 嗯、啊、然后、就是、那个、怎么说呢 | 0.90 |
| 口误触发词 | 不对、重来、重新说、刚才说错了、这段不要 | 0.85 |
| 废弃指令 | "这段剪掉""不要了""重来一遍" | 0.90 |

**静音+字幕同步显示（MVP 核心交互）：**

静音检测和字幕段共享同一时间轴，在编辑器中同步渲染：

- 静音段在字幕列表中以独立行显示（灰色背景，标注"静音 N.Ns"），穿插在对应位置的字幕段之间
- 字幕编辑器和波形视图中，静音段和字幕段使用不同颜色区分
- 用户可以拖拽调整静音段与相邻字幕段的边界，精确控制删除范围
- 交叉验证场景：静音段前后若恰好是口误触发词/重复句，系统用连线或高亮提示关联关系
- 用户调整字幕段时间戳后，静音段的对应位置自动同步更新

**相似度层（P1，需确认）：**

| 类型 | 技术 | 置信度 |
|------|------|--------|
| 重复句 | bge-small-zh 文本向量相似度 + 时间邻近窗口 | 0.70-0.90 |
| 口误重说 | 触发词检测 + 后续 N 句与前文对比 | 0.75-0.85 |

**VAD 增强层（P1，静音检测交叉验证）：**

MVP 的 silencedetect 仅基于音量阈值，在背景噪声不均匀、低声说话、快速停顿等场景下可能误判。P1 引入 VAD 作为交叉验证：

| 判定逻辑 | silencedetect | VAD | 结果 |
|---------|--------------|-----|------|
| 确认静音 | 静音 | 无语音 | 建议删除（高置信度） |
| 低音量但有语音 | 静音 | 有语音 | 保留（避免误删轻声说话） |
| 有声但无语音 | 有声 | 无语音 | 标记可疑（可能是噪声/呼吸声） |
| 正常语音 | 有声 | 有语音 | 保留 |

- VAD 引擎：WebRTC VAD（轻量本地）或 Silero VAD（高精度本地模型）
- 性能：分段批处理，不阻塞 UI
- UI 表现：WaveformView 上用第二行颜色条叠加显示 VAD 结果，与静音段颜色形成双轨对比

**LLM 层（P2，仅建议）：**

跑题检测、章节划分、粗剪评分、短视频切片。用户必须显式开启。

### 8.5 字幕编辑器

- 显示所有字幕行 + 静音段行，每行显示：时间戳 + 文本/标签 + 状态标签
- 静音段行以灰色背景穿插在字幕段之间，显示"静音 N.Ns"和音量信息
- Inline 编辑：点击文本直接修改
- 时长调整：拖拽字幕行边界调整起止时间，静音段自动同步
- 合并：选中多行 -> 合并为一行 + 合并时间段
- 拆分：光标定位 -> 回车拆分
- 搜索替换：支持全局批量替换
- 点击行：视频跳转到对应时间点
- 标记操作：右键或快捷键标记 删除/保留/待确认
- 交叉验证：选中一段静音时，高亮其前后最近的字幕段，帮助判断是否为有效停顿

### 8.6 预览

- HTML5 video 播放器
- 字幕叠加显示（底部，跟随当前时间）
- 原片/剪后切换预览（Shift+Space）
- 点击字幕行跳转（双向同步）

### 8.7 导出

**双模式导出：**

| 模式 | 方式 | 精度 | 速度 | 说明 |
|------|------|------|------|------|
| 精确导出（默认） | 重新编码 | 帧级 | 较慢 | 保证切点准确，MVP 默认 |
| 快速导出 | -c copy | 关键帧级 | 快 | 可能在切点处有偏移，UI 明确提示 |

**导出格式：**

| 格式 | 阶段 | 说明 |
|------|------|------|
| MP4 | P0 | 视频+音频，已删除指定段 |
| SRT | P0 | 标准字幕 |
| VTT | P1 | Web 字幕 |
| FCPXML | P2 | Final Cut Pro 工程文件 |
| Premiere XML | P2 | Premiere Pro 工程文件 |
| EDL | P2 | 通用剪辑决策列表 |
| JSON | P0 | 剪辑决策数据（项目文件本身） |

---

## 9. 非功能需求

### 9.1 性能

**MVP 性能要求：**

| 操作 | 指标 |
|------|------|
| SRT 导入解析 | <= 1 秒（1000 条字幕以内） |
| 静音检测 1 小时视频 | <= 30 秒 |
| 静音+字幕同步渲染 | <= 500ms（500 段字幕 + 200 段静音） |
| 精确导出 1 小时视频 | 取决于编码器，使用 x264 medium 应在 1x 实时以内 |
| 快速导出 1 小时视频 | <= 60 秒（-c copy，P1） |

**P1 ASR 性能验收（指定硬件前提）：**

| 配置 | 素材 | 指标 |
|------|------|------|
| i5/i7 CPU，无独显，16GB RAM | 1080p 口播，60min，16kHz mono wav，中文普通话 | FunASR RTF <= 0.5（30分钟内完成） |
| NVIDIA RTX 3060，16GB RAM | 同上 | faster-whisper RTF <= 0.2（12分钟内完成） |
| 同上 | 同上 | 字幕时间戳平均误差 <= 500ms |

**P1 其他性能要求：**

| 操作 | 指标 |
|------|------|
| 波形渲染 2 小时音频 | 保持 30fps 流畅滚动 |

### 9.2 隐私策略

| 级别 | 说明 |
|------|------|
| P0 | 所有核心功能本地完成，不上传音视频、不上传转写文本 |
| P2 | LLM 建议为可选增强，仅上传转写文本，不上传原始音视频 |
| 强制 | 用户必须显式开启云端分析，设置页显示 API Provider 和关闭入口 |

### 9.3 稳定性

- 项目文件自动保存（每次编辑操作后）
- 崩溃恢复：重新打开项目时检测未保存的自动保存文件
- FFmpeg 进程异常退出时，清理临时文件并报告错误

### 9.4 兼容性

- 操作系统：Windows 11（MVP），后续支持 macOS / Linux
- 视频编码：H.264 / H.265 / AV1
- 音频编码：AAC / MP3 / PCM
- 桌面框架：PyWebView（Edge WebView2 on Windows）

---

## 10. 数据与状态模型

### 10.1 项目文件结构（project.json）

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "我的口播视频",
    "created_at": "2026-05-14T10:00:00Z",
    "updated_at": "2026-05-14T12:00:00Z"
  },
  "media": {
    "path": "D:/Videos/raw.mp4",
    "media_hash": "sha256:abc...",
    "duration": 3600.0,
    "format": "mp4",
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "audio_channels": 2,
    "sample_rate": 44100,
    "bit_rate": 5000000,
    "proxy_path": null,
    "waveform_path": null
  },
  "transcript": {
    "engine": "funasr",
    "language": "zh",
    "segments": [
      {
        "id": "seg_001",
        "version": 1,
        "start": 12.3,
        "end": 16.8,
        "text": "大家好今天我们来讲一下如何使用这个工具",
        "words": [
          {"word": "大家", "start": 12.3, "end": 12.6, "confidence": 0.98}
        ],
        "speaker": null,
        "dirty_flags": {
          "text_changed": false,
          "time_changed": false,
          "analysis_stale": false
        }
      }
    ]
  },
  "analysis": {
    "last_run": "2026-05-14T11:00:00Z",
    "silence_segments": [
      {"id": "sil_001", "start": 20.1, "end": 22.4, "duration": 2.3, "confidence": 0.95}
    ],
    "filler_hits": [
      {"id": "fil_001", "segment_id": "seg_003", "text": "嗯", "type": "filler"}
    ],
    "error_patterns": [
      {"id": "err_001", "segment_ids": ["seg_005", "seg_006"], "type": "re_read", "confidence": 0.9, "trigger": "不对重来"}
    ],
    "repetitions": [
      {"id": "rep_001", "segment_ids": ["seg_008", "seg_012"], "similarity": 0.87}
    ]
  },
  "edits": [
    {
      "id": "edit_001",
      "start": 20.1,
      "end": 22.4,
      "action": "delete",
      "source": "auto_silence",
      "analysis_id": "sil_001",
      "status": "pending",
      "priority": 100
    }
  ],
  "export_history": []
}
```

### 10.2 编辑状态一致性规则

| 事件 | 影响 |
|------|------|
| 字幕文本变更 | 该 segment 的 `text_changed = true`，文本类分析标记 `analysis_stale = true` |
| 字幕时间变更 | 该 segment 的 `time_changed = true`，所有关联分析标记 `analysis_stale = true` |
| 合并/拆分段 | 生成新 segment，原 segment 的分析关联失效 |
| 用户手动编辑 | `priority = 200`，高于自动建议（priority=100） |
| 重叠删除段 | 取并集，按 priority 高的为准 |
| 分析过期 | UI 显示"分析结果已过期，建议重新分析" |

### 10.3 Edit 状态机

```
pending (黄色) --> confirmed (红色) --> [导出]
     |                |
     v                v
rejected (绿色)    reverted (灰色)
```

---

## 11. 导出策略

| 模式 | FFmpeg 参数 | 切点精度 | 适用场景 |
|------|------------|---------|---------|
| 精确导出 | `-ss <start> -to <end>` 重新编码 | 帧级（<= 1帧误差） | **MVP 默认**，保证质量 |
| 快速导出 | `-c copy -ss <start> -to <end>` | 关键帧级（可能偏移数秒） | 快速预览、粗筛 |

**精确导出实现策略**：将保留的片段逐个导出，再用 concat 协议拼接，避免全量重编码。

**导出前校验清单**：
- 有 confirmed 的删除段吗？
- 删除段总时长是否超过原视频 40%？
- 有单段超过 60 秒的删除吗？
- 有连续 3 段以上的删除吗？
- 项目文件是否已保存？

---

## 12. 异常流程

| 异常场景 | 处理策略 |
|---------|---------|
| ASR 失败 | 显示错误信息，建议切换引擎或导入 SRT，不阻塞后续操作 |
| FFmpeg 未安装 | 首次启动检测，提供内置下载器（Windows），或引导手动安装 |
| 源视频文件丢失 | 打开项目时检测 media.path，提示文件不存在，提供重新定位 |
| 源视频文件被修改 | 通过 media_hash 检测，提示文件已变更，建议重新分析 |
| 项目路径变化 | 使用相对路径 + 打开时重定位 |
| 模型下载失败 | 离线提示，支持手动放置模型文件 |
| 导出中断 | 保留已导出的临时片段，提供"继续导出"选项 |
| 字幕时间戳错位 | 允许用户手动调整，提供"按比例缩放"工具 |
| 内存不足 | 检测可用内存，大文件自动切换为分段处理 |
| ASR 输出空结果 | 提示可能是音频问题（静音文件/格式不支持），建议检查音频轨道 |

---

## 13. 验收标准

### Phase 0 验收（技术验证闭环）

- [ ] 导入 5 分钟口播视频，自动提取音频并获取媒体信息
- [ ] 导入对应 SRT 字幕文件，解析为带时间戳的 segment 列表
- [ ] 静音检测标记停顿段，静音段与字幕段同步显示在编辑器中
- [ ] 可拖拽调整静音段边界，调整后时间轴同步更新
- [ ] 删除标记段后导出 MP4，在 VLC 中播放无黑屏/音频断裂
- [ ] 导出 SRT 字幕与视频同步

### Phase 1 验收（MVP 验收）

- [ ] 使用 1 小时口播素材 + 对应 SRT 完成全流程（导入 -> 导入SRT -> 分析 -> 确认 -> 导出）
- [ ] SRT 导入支持中文/英文，格式错误时给出具体提示
- [ ] 静音段穿插在字幕段之间同步显示，颜色区分清晰
- [ ] 静音段可拖拽调整边界，相邻字幕段时间自动同步
- [ ] 选中静音段时前后字幕段高亮，支持交叉验证
- [ ] 口头禅检测覆盖配置词表中 90%+ 的匹配
- [ ] 口误触发词检测无遗漏（针对测试用例集）
- [ ] 字幕编辑器 inline 编辑、合并、拆分功能正常
- [ ] 导出前摘要弹窗显示正确统计
- [ ] 误删防护三项触发正常（40%/60s/连续3段）
- [ ] 项目文件保存/加载正常，崩溃恢复可用

---

## 14. 开源合规

| 组件 | 许可证 | 备注 |
|------|--------|------|
| PyWebVue | MIT | 可作为依赖使用，风险低 |
| ff-intelligent-neo | 需确认 | README 写 AGPL-3.0，LICENSE 文件需核实，迁移前必须确认实际授权 |
| FFmpeg | GPL/LGPL | 取决于编译参数和链接方式，需确认分发合规 |
| auto-editor | Unlicense | 公有领域，可自由使用 |
| FunASR | MIT | 模型权重需确认 |
| faster-whisper | MIT | 基于 CTranslate2，MIT |
| sentence-transformers | Apache-2.0 | 可用 |
| bge-small-zh | MIT (模型) | 需确认模型权重许可 |

**打包产物必须包含 Third-party Notices 文件。**

**迁移前必须完成**：确认 ff-intelligent-neo 的实际许可证，以及 FFmpeg 在打包分发场景下的 GPL/LGPL 合规性。

---

## 15. 风险与里程碑

### 风险矩阵

| 风险 | 影响 | 概率 | 缓解策略 |
|------|------|------|---------|
| ASR 中文准确率不达标 | 高 | 中 | MVP 不依赖 ASR，用户手动提供 SRT；P1 双引擎（FunASR + Whisper） |
| FFmpeg stream copy 切点不精确 | 中 | 高 | 默认精确导出，快速导出明确提示风险 |
| 静音检测误判（噪声/低声说话） | 中 | 中 | P1 引入 VAD 交叉验证，双轨判定降低误删率 |
| 超长视频（2h+）波形渲染卡顿 | 中 | 中 | 分段渲染、虚拟滚动、WebWorker |
| ff-intelligent-neo 许可证不兼容 | 高 | 低 | 迁移前确认，必要时重写而非复制 |
| PyWebView 在不同 WebView2 版本的表现差异 | 中 | 中 | 锁定最低 WebView2 版本，CI 测试 |
| 模型文件体积过大影响分发 | 中 | 中 | 模型按需下载，不内置 |

### 里程碑

| 里程碑 | 内容 | 预计时间 |
|--------|------|---------|
| M0: 技术验证 | 最小闭环：导入->SRT导入->静音标记同步显示->导出 | 1-2 周 |
| M1: MVP | P0 全部功能（基于手动SRT） | 4-6 周（从 M0 完成后算起） |
| M2: 增强版 | P1 功能 + 部分P2 | 4-6 周（从 M1 完成后算起） |
| M3: 产品化 | 打包分发 + 模型管理 + 国际化 | 持续 |

---

# 技术设计文档（附录）

以下为技术实现层面的详细设计，支撑上述 PRD。

---

## A. 系统架构

```
Milo-Cut Desktop App
|
|-- Python Backend (PyWebVue Bridge)
|   |-- Bridge API (milo_cut_api.py)
|   |-- TaskManager           -- 统一任务管理（ASR/分析/导出）
|   |-- Core Engine
|   |   |-- ffmpeg_service     -- FFmpeg/ffprobe 封装
|   |   |-- audio_service      -- 音频提取、波形生成
|   |   |-- silence_detector   -- 静音检测
|   |   |-- asr_service        -- ASR 抽象层
|   |   |-- analysis_engine    -- 三层分析引擎
|   |   |-- edit_engine        -- 编辑决策管理
|   |   |-- subtitle_service   -- 字幕 CRUD
|   |   |-- preview_service    -- 代理文件/预览
|   |   |-- export_service     -- 多格式导出
|   |   |-- project_service    -- 项目文件管理
|   |-- Storage
|       |-- project.json
|       |-- autosave/
|       |-- cache/
|
|-- Vue 3 Frontend
    |-- pages/
    |   |-- WelcomePage
    |   |-- WorkspacePage
    |   |-- ExportPage
    |-- components/
    |   |-- workspace/
    |   |   |-- VideoPlayer
    |   |   |-- WaveformView
    |   |   |-- TranscriptEditor
    |   |   |-- SuggestionPanel
    |   |   |-- StepController
    |   |-- common/
    |       |-- FileDropInput
    |       |-- ProgressBar
    |       |-- LogPanel
    |-- composables/
        |-- useProject
        |-- useTranscript
        |-- useAnalysis
        |-- usePlayer
        |-- useExport
```

---

## B. 技术栈

| 层级 | 技术选择 |
|------|---------|
| 桌面壳 | PyWebView / PyWebVue |
| 前端 | Vue 3 + TypeScript + TailwindCSS v4 + DaisyUI v5 |
| 构建工具 | Vite 6 |
| 后端 | Python 3.11+ |
| 包管理 | uv (后端) + bun (前端) |
| 视频处理 | FFmpeg / ffprobe |
| 静音检测 | FFmpeg silencedetect + auto-editor |
| ASR | FunASR (默认) + faster-whisper (可选) |
| 语义分析-规则 | 正则 + 配置词表 |
| 语义分析-相似度 | sentence-transformers / bge-small-zh |
| 语义分析-LLM | P2，可选 API 调用 |
| 数据存储 | JSON 文件 |
| 打包 | PyInstaller onedir |

---

## C. 统一任务 API

所有长任务（ASR、分析、波形生成、导出）使用统一任务模型：

```python
class MiloCutApi(Bridge):
    # ---- 统一任务管理 ----
    @expose def create_task(self, task_type: str, payload: dict) -> dict
    @expose def start_task(self, task_id: str) -> dict
    @expose def cancel_task(self, task_id: str) -> dict
    @expose def get_task(self, task_id: str) -> dict
    @expose def list_tasks(self) -> dict

    # task_type 枚举（MVP 仅含无 transcription 前缀的项）：
    # "silence_detection", "filler_detection", "error_detection",
    # "full_analysis", "export_video", "export_subtitle"
    # P1 新增：
    # "transcription", "repetition_detection", "vad_analysis",
    # "waveform_generation", "proxy_generation", "export_timeline"

    # 事件名约定：
    # "task:{task_id}:progress"  -- {progress: 0-100, message: str}
    # "task:{task_id}:completed" -- {result: dict}
    # "task:{task_id}:failed"    -- {error: str, code: str}
```

### 项目管理 API

```python
    @expose def create_project(self, name: str, media_path: str) -> dict
    @expose def open_project(self, project_path: str) -> dict
    @expose def save_project(self) -> dict
    @expose def close_project(self) -> dict
    @expose def get_recent_projects(self) -> dict
```

### 字幕编辑 API

```python
    @expose def update_segment_text(self, segment_id: str, text: str) -> dict
    @expose def merge_segments(self, segment_ids: list[str]) -> dict
    @expose def split_segment(self, segment_id: str, position: float) -> dict
    @expose def search_replace(self, query: str, replacement: str, scope: str) -> dict
```

### 编辑决策 API

```python
    @expose def mark_segments(self, segment_ids: list[str], action: str) -> dict
    @expose def confirm_all_suggestions(self) -> dict
    @expose def reject_all_suggestions(self) -> dict
    @expose def undo_edit(self, edit_id: str) -> dict
    @expose def get_edit_summary(self) -> dict
```

### 设置 API

```python
    @expose def get_settings(self) -> dict
    @expose def update_settings(self, settings: dict) -> dict
    @expose def get_asr_engines(self) -> dict
```

---

## D. 后端模块与复用来源

| 模块 | 文件 | 复用来源 |
|------|------|---------|
| 应用入口 | `main.py` | PyWebVue 模板 |
| FFmpeg 服务 | `core/ffmpeg_service.py` | 迁移自 ff-intelligent-neo command_builder + task_runner + process_control + file_info |
| 音频服务 | `core/audio_service.py` | 新建 |
| 静音检测 | `core/silence_detector.py` | 迁移自 ff-intelligent-neo auto_editor_runner + auto_editor_api |
| VAD 服务 | `core/vad_service.py` | P1 新建（WebRTC VAD / Silero VAD 封装） |
| ASR 服务 | `core/asr_service.py` | 新建 |
| 分析引擎 | `core/analysis_engine.py` | 新建 |
| 规则分析器 | `core/analyzers/rule_analyzer.py` | 新建 |
| 相似度分析器 | `core/analyzers/similarity_analyzer.py` | 新建 |
| LLM 分析器 | `core/analyzers/llm_analyzer.py` | P2 新建 |
| 编辑引擎 | `core/edit_engine.py` | 新建 |
| 字幕服务 | `core/subtitle_service.py` | 新建 |
| 预览服务 | `core/preview_service.py` | 新建 |
| 导出服务 | `core/export_service.py` | 新建 |
| 项目管理 | `core/project_service.py` | 新建 |
| 数据模型 | `core/models.py` | 新建 (Pydantic) |
| 任务管理 | `core/task_manager.py` | 新建（统一任务抽象） |
| 路径管理 | `core/paths.py` | 迁移自 ff-intelligent-neo |
| 配置管理 | `core/config.py` | 迁移自 ff-intelligent-neo |
| 日志 | `core/logging.py` | 迁移自 ff-intelligent-neo |

---

## E. UI 布局

### WorkspacePage（核心页面）

```
+-------------------------------------------------------+
| StepController [导入] [转写] [分析] [编辑] [导出]       |
+---------------------------+---------------------------+
|                           |  TranscriptEditor         |
|    VideoPlayer            |  [pending] 大家好...      |
|    (带字幕叠加)            |  [confirmed] 今天讲...    |
|                           |  [rejected] 不对重来...   |
+---------------------------+---------------------------+
|    WaveformView           |  SuggestionPanel          |
|    (波形+彩色片段标记)     |  静音: 3段 | 口头禅: 5处   |
|                           |  口误: 2处 | 重复: 1处     |
|                           |  [全部确认] [全部忽略]     |
+---------------------------+---------------------------+
```

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| Space | 播放/暂停 |
| Shift+Space | 原片/剪后切换 |
| Ctrl+S | 保存项目 |
| Delete | 删除选中片段 |
| Ctrl+Z | 撤销 |
| Ctrl+F | 搜索替换 |
| I / O | 跳到片段开头/结尾 |

---

## F. 从现有项目迁移清单

| 迁移内容 | 来源 | 目标文件 |
|----------|------|---------|
| FFmpeg 命令构建器 | ff-intelligent-neo `core/command_builder.py` | `core/ffmpeg_service.py` |
| 任务执行与进程控制 | ff-intelligent-neo `core/task_runner.py` + `core/process_control.py` | `core/ffmpeg_service.py` |
| 路径管理 | ff-intelligent-neo `core/paths.py` | `core/paths.py` |
| 配置持久化 | ff-intelligent-neo `core/config.py` | `core/config.py` |
| ffprobe 文件探测 | ff-intelligent-neo `core/file_info.py` | `core/ffmpeg_service.py` |
| auto-editor 封装 | ff-intelligent-neo `core/auto_editor_runner.py` + `auto_editor_api.py` | `core/silence_detector.py` |
| 日志系统 | ff-intelligent-neo `core/logging.py` | `core/logging.py` |
| 打包配置 | ff-intelligent-neo `app.spec` + `build.py` | `build.py` + `app.spec` |
| 拖拽导入组件 | ff-intelligent-neo `FileDropInput.vue` | `components/common/FileDropInput.vue` |
| PyWebVue 框架 | PyWebVue `pywebvue/` | 直接作为依赖引入 |

---

## G. 开发路线

### Phase 0: 技术验证 (1-2周)

1. 基于 PyWebVue 创建项目骨架
2. 迁移 FFmpeg 封装
3. 实现 SRT 解析与导入
4. 验证静音检测 + 字幕同步显示
5. 验证导出剪辑后 MP4
6. **验收**：导入视频 -> 导入SRT -> 静音标记同步显示 -> 导出MP4

### Phase 1: MVP (4-6周)

1. 项目管理（新建/保存/打开/最近项目）
2. SRT 导入 + 格式校验 + 时间轴校验
3. 静音检测 + 与字幕同步显示（核心交互）
4. 规则层分析（口头禅/口误触发词）
5. 字幕编辑器 + 确认/拒绝交互 + 误删防护
6. 静音段边界拖拽调整 + 时间轴同步
7. 精确导出 MP4 + SRT
8. 设置页（静音检测参数、口头禅词表、导出模式）
9. **验收**：按第13章 MVP 验收标准执行

### Phase 2: 增强版 (4-6周)

1. 本地 ASR 转写（FunASR / faster-whisper）
2. VAD 增强静音检测（与 silencedetect 交叉验证）
3. 重复句检测（相似度层）
4. 视频预览 + 字幕叠加
4. 波形可视化
5. 原片/剪后切换预览
6. 快速导出模式
7. 全局搜索替换
8. FCPXML / Premiere XML / EDL 导出

### Phase 3: 产品化 (持续)

1. LLM 跑题检测 / 章节生成
2. 短视频切片建议
3. 批量处理
4. 本地模型管理 UI
5. 自动更新
6. 国际化 (i18n)
7. 打包分发优化


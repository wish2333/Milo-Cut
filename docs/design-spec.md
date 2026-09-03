# Milo-Cut Design Specification (Apple Edition)

## 1. 设计概述 (Overview)

Milo-Cut 的界面设计遵循"摄影第一"原则，将**视频预览窗口**和**转写文本内容**视为核心资产。UI 框架采用边缘对齐的磁贴（Tiles）设计，去除所有装饰性的渐变和阴影，仅保留一个标志性的 Action Blue (#0066cc) 作为交互引导色。

* **视觉节奏**：采用全屏磁贴在浅色（Canvas）和深色（Near-Black）间切换，模拟 Apple 官网的展厅感。
* **交互逻辑**：采用"文本即剪辑"的直觉操作，状态切换（待处理/已确认/已拒绝）通过柔和的语义色块区分，而非繁琐的图标。

---

## 2. 色彩系统 (Colors)

| 类型 | Token | Hex | 用途 |
|------|-------|-----|------|
| **品牌主色** | `{colors.primary}` | `#0066cc` | 所有按钮、链接、关键交互 |
| **背景(浅)** | `{colors.canvas}` | `#ffffff` | 工作区主背景、字幕行背景 |
| **背景(纸感)** | `{colors.canvas-parchment}` | `#f5f5f7` | 侧边栏建议面板、底部状态栏 |
| **背景(深)** | `{colors.surface-tile-1}` | `#272729` | 视频播放器区域、深色模式磁贴 |
| **状态：待确认** | `{colors.status-pending}` | `#fff9e6` | Pending：极淡黄色背景 |
| **状态：确认删** | `{colors.status-confirmed}` | `#fef2f2` | Confirmed：极淡红色，高危操作区域 |
| **状态：已保留** | `{colors.status-rejected}` | `#f0fdf4` | Rejected：极淡绿色，内容安全 |
| **静音段背景** | `{colors.silence-bg}` | `#f5f5f7` | 静音段穿插行背景（与纸感背景一致） |
| **交叉验证高亮** | `{colors.crossref}` | `#0066cc` | 选中静音段时前后字幕行边缘高亮 |

---

## 3. 文字系统 (Typography)

严格执行 Apple 的负字距方案，营造紧致感。

| 用途 | Token | 规格 |
|------|-------|------|
| 阶段标题 | Display-lg | `40px / 600 / 1.10` |
| 转写字幕正文 | Body | `17px / 400 / 1.47 / -0.374px` |
| 时间戳/静音标注 | Caption | `14px / 400` 灰色 |
| 导出摘要 | Lead | `24px / 600 / 1.25` |

字重严格在 400（常规）和 600（半粗）之间，禁止 500。

---

## 4. 核心组件 (Components)

### 4.1 全局导航与步骤控制 (`global-nav` & `step-controller`)

- 背景：`{colors.surface-black}`，高度 44px
- 左侧：Milo-Cut Logo
- 居中：步骤控制器 `导入 -> 转写 -> 分析 -> 编辑 -> 导出`
- 已完成步骤显示 Action Blue 勾选，当前步骤高亮

### 4.2 转写编辑器 (`transcript-editor`)

"文本即剪辑"的核心区域。

- **字幕行**：`[时间戳] + [文本内容] + [状态标签]`
- **静音段**：穿插在字幕行间，背景 `{colors.canvas-parchment}`，标注"静音 N.Ns"和音量信息
- **交互**：
  - 点击行 -> 视频同步跳转
  - 选中文字按 Delete -> 背景变为 `{colors.status-pending}`
  - 选中静音段 -> 前后字幕行产生 Action Blue 边缘高亮（交叉验证）
  - 拖拽静音段边界 -> 调整起止时间，相邻字幕段自动同步

### 4.3 视频播放器 (`video-player`)

- 放置在 `{colors.surface-tile-1}` 深色磁贴中，视频居中
- 底部叠加实时字幕，白色 SF Pro Display
- 视频画面投射 `3px 5px 30px` 阴影，具浮动感

### 4.4 操作按钮 (`button-primary`)

- 全胶囊型（Pill-shaped），Action Blue 背景，白色文字
- 按下时 `transform: scale(0.95)`
- 状态按钮使用对应语义色背景 + 深色文字

### 4.5 波形视图 (`waveform-view`)

- 紧凑型，位于视频播放器下方
- 静音段区域以半透明色块覆盖
- 字幕段边界以竖线标记
- 支持点击跳转和拖拽选区

---

## 5. 用户流程交互设计 (UX Flow)

### 阶段一：导入

1. 拖拽视频进入，界面从 `{colors.canvas}` 平滑切换为加载态
2. 导入 SRT 字幕文件，解析后生成字幕行列表
3. 后台执行静音检测，字幕行间自动插入灰色静音条

### 阶段二：分析与交叉验证

1. 口头禅/口误自动标记为 Pending（淡黄色背景）
2. 选中静音段 -> 前后字幕行 Action Blue 边缘高亮，辅助判断是否误删
3. 拖拽静音段边界微调起止时间

### 阶段三：确认与导出

1. 批量确认/拒绝操作
2. 导出前弹出 Apple 风格居中模态框
3. 摘要以 Lead 字体显示"将删除 X 分钟，占总量 Y%"
4. 删除超过 40% 时文字变红警告

---

## 6. WorkspacePage 布局

```
+--[global-nav: surface-black 44px]-----------------------+
| Logo    [导入] -> [转写] -> [分析] -> [编辑] -> [导出]   |
+---------------------------+-----------------------------+
|                           |                             |
|    video-player           |    transcript-editor        |
|    (surface-tile-1)       |    (canvas white)           |
|    深色磁贴               |    [00:12] 大家好...        |
|    视频居中+阴影           |    [静音 2.4s]  ----灰色行  |
|    底部字幕叠加            |    [00:16] 今天讲...        |
|                           |                             |
+---------------------------+-----------------------------+
|    waveform-view          |    suggestion-panel         |
|    紧凑波形+标记           |    (canvas-parchment)       |
|                           |    静音: 3段 | 口头禅: 5处   |
|                           |    [全部确认] [全部忽略]     |
+---------------------------+-----------------------------+
```

---

## 7. 设计准则 (Do's and Don'ts)

### 务必执行

- 单一强调色：除状态背景色外，所有交互元素只用 Action Blue
- 17px 基准：所有字幕文本 17px
- 边缘对齐：视频播放器与字幕编辑区无缝衔接，用颜色区分而非边框线
- 静音段与字幕段使用同一时间轴，颜色区分而非空间分离

### 严禁使用

- 禁止圆角混用：字幕行和静态组件不大圆角，仅按钮和卡片用 pill/lg
- 禁止装饰性阴影：除视频画面外，UI 组件不得有阴影
- 禁止 500 字重：严格 400 和 600
- 禁止 emoji 和装饰性图标用于功能按钮

## 9. 层级契约补充：提升 owner，而非提升弹层（v3.0.1）

Stacking context 陷阱：`position: fixed` 弹层若被封印在带 `transform`/`filter`/`will-change` 的 sticky 祖先内，其 z-index 只在该祖先的 stacking context 内生效（同一坑连踩三次后固化的规则，源自 MAW DESIGN.md 166-197）。

**规则**：修复层级冲突时**提升 owner**（把弹层移到无 transform 祖先的直接管辖范围，如堆叠表面根节点），**不要**给弹层本身堆更高的 z-index。

实例：v3.0.1 堆叠时间线中，`PlayheadOverlay` 从主轨层提升为堆叠表面（`timeline-stack`）的直接子节点，`inset-y-0` 贯穿主轨与全部副轨 lane（单节点、z-10）。配套约束：弹层必须双测（层内 + 跨层）。

## 10. 堆叠时间线视觉约定（v3.0.1）

- 主轨：波形 + 蓝色系段块（既有 EditDecision 状态色）。
- 副轨 lane：violet 次级色块（`bg-violet-200/50`），悬浮标题条（轨道名 · language · 段数 + 折叠钮）。
- 播放头：单条红线上下贯穿（提升 owner 后的唯一实例）。
- lane 高度档位 32/48/72px，折叠 24px，主轨下限 96px（挤压链 lg→md→sm→24）。

## 11. 多行时间线交互规范（v3.0.2）

- **双模式**：聚焦（basic，单窗 + 副轨堆叠，v3.0.1 语义）与多行（multi，虚拟化行列表，"一行 = 一窗"）随存随切；互迁公式：multi→basic 居中 `scrollTopTime + spr/2`，basic→multi reveal 视窗中心。
- **行几何**：行 = 派生几何（duration / secondsPerRow），末行按剩余时长缩短；行高预设 64–168px 与面板高度解耦（divider 只改可视行数）；行键含 spr，档位切换整行重挂（行级适配器静态捕获 spr）。
- **wheel 手势表**：

| 手势 | 行为 |
|---|---|
| 普通滚轮 / 触控板 | 原生竖向滚行（不拦截） |
| Ctrl/Cmd + 滚轮 | 每行秒数档 5/10/20/30 循环（160ms burst 合并净步数） |
| Ctrl/Cmd + Shift + 滚轮 | 行高档 64–168 循环（wheel 下 = 缩小内容） |
| 档位结算后 | 播放行锚定 REVEAL_BIAS（0.45） |

- **空点双语义**（`emptyAreaMode`）：basic 空点建段（现状）；multi 空点 = 清选 + 定位。修饰路由：plain 拖 = scrub（32ms 节流，松手精确定位，不改播放态）；Ctrl 拖 = 建段（预览停块缘、窄缝拒绝）；Shift 拖 = 跨行框选（并入全局多选）；双击空点 = 播放/暂停。
- **bounded / unbounded 双映射**：点击/建段钳行内；scrub 与 trim 用冻结换算（unbounded，仅钳 [0, duration]）——行边界永不进 trim 约束链（S7.8），拖拽中行回收不失连续。
- **trim 约束链**：unbounded → 邻居钳（blocked 拒动）→ snap 0.01s（Alt 反转）→ snap 后二次钳。Alt 无跳过联动语义（联动自动且不可跳过）。
- **跟随三分**：播放跟随换行才判定（舒适区只动播放头，否则 FOLLOW_BIAS 0.35）；手动滚动 3s 冷却（程序回声经 autoScrollTarget 匹配豁免）；revealTime 跳转 = REVEAL_BIAS + 免滚 + 冷却置位，字幕列表导航统一走此入口。
- **持久化**：`milocut:timeline-rows:v1` = `{ mode, secondsPerRow, rowHeight, scrollTopTime, editorHeightPx }`；档位/高度变更即写，滚动位置 300ms 防抖 + 卸载兜底；白名单校验损坏回退；重开恢复按行边界量化。
- **副轨行内组合**：每行 = 主 lane（blocks）+ 副轨 lanes（32/48/72/折叠 24，与聚焦模式共享折叠态）；有副轨时默认行高自动 168（用户自选值尊重）；副轨 trim 组合态可用。

## 12. 列表轨交互规范（v3.0.3）

- **轨选择器**：字幕列表头部 segmented 切换（主轨 / 各副轨，含段数徽标）；选择态 = `activeListTrackId`（null = 主轨）会话视图态——不产生 patch、不入 undo、不持久化，刷新/删轨/切时间线回退主轨（回退兜底单一真源在 `useListTrackSelector`）。
- **副轨行多态**：与主轨同一行组件 variant 分支——文本 / 时间戳 / 时长 chip / 绑定标记；空轨渲染空态卡 +「新建字幕」（播放时间锚点 2s cue，媒体上界钳制）；副轨行不参与选中模式与 globalEditMode 全局扫描。
- **编辑通路**：双击行 / 菜单「编辑」进文本编辑（draft 虚拟滚动恢复沿用主轨机制）；时间戳点击进数值编辑（±0.1s 箭头微调）；与波形 trim 共用 `useTrackEdit` 防抖乐观内核（300ms 合并、失败回滚 + toast 错误原文）；切轨前 flush 未决防抖（flush-on-switch）。
- **撤销捕获层谓词表**（唯一真源，PRD R1.5）：

| 列表操作 | 谓词 | 捕获层 |
|---|---|---|
| 文本编辑（text） | 恒真 | `["tracks"]` |
| 时间编辑（start/end，有绑定） | 绑定谓词命中 | `["tracks","bindings"]` |
| 时间编辑（无绑定） | 绑定谓词未中 | `["tracks"]` |
| 删除此条字幕 | 恒真 | `["tracks","bindings"]` |

  undo 时 tracks/bindings（含偏移）原子还原，redo 对称；删除无确认框（undo 兜底）。
- **kbd 角标**：行右键菜单配置驱动（`kbd?` 字段），角标只标注快捷键登记表（ShortcutsSettingsTab）中的真实快捷键（现仅主轨「标记删除」= Del）；无登记项不渲染空节点（延续 R9.4「不发明快捷键」）。
- **跟随平滑（opt-in）**：导航跳转可 140ms ease-out 动画（`milocut:timeline-follow-smooth:v1`，默认关）；播放时钟消费路径恒瞬时（永不启动动画）；时间窗回环抑制（动画驱动期 trusted scroll 按回声处理）；滚轮哨兵动画期取消（手动优先）。波形行几何/回环分类内核零改动（仅写入方式扩展）。

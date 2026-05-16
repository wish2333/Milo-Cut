## 过期问题

1. 字幕部分尽管不检测也应该能够选择删除，此外还要妥善处理好与空白检测的冲突
  2. TimelineRuler需要有滑块来滚动而非拖动滚动，避免与时间跳转的点击（改为点击时间码区域才跳转时间，点击时间范围改为选

    择某段时间）冲突；同时允许滚轮实现滚动，要处理好滚轮缩放（改为Ctrl+滚轮-->缩放）；区域高度可以放大一些；选择某段时间
    后可以拖动范围左右来更改选区范围，增加按钮开关吸附；优化性能表现
  3. Timeline中应当允许修改范围时间戳的数值
  4. 应当支持添加新的剪辑区域
  5. 用自定义组件替换播放区域的浏览器原生播放选项栏
  6. 导出视频时报错

仍然有几个功能没有实现：
    1. 字幕部分尽管不检测也应该能够选择删除（现在用删除键作为快捷键与字幕编辑冲突，不要用快捷键，直接显示已保留，可以点击切换成删除，Analysis之后对检测到的字幕标注建议删除），此外还要妥善处理好与空白检测的冲突
  2. TimelineRuler允许滚轮实现滚动；选择某段时间后可以拖动范围左右来更改选区范围

## 新问题

已知问题：

- Analysis检测后弹出的建议栏无法收起，应用或忽略建议后没有自动收起

仍然有几个功能没有实现：

- Timeline中应当允许修改范围时间戳的数值

- 选区拖动仍然没有任何功能得到了真正的实现，实现的空白区域选区实现的及其粗糙，你必须完全自查这个功能并优化，甚至可能因为现在写得太烂而需要重写。这项功能，你先别继续优化了，先清晰而简练地告诉我你想怎么实现，由我来审计。
- 同步显示空白检测和字幕，但是你没有处理好冲突问题。这项功能，你先别继续优化了，先清晰而简练地告诉我你想怎么实现，由我来审计。

  Audit 1: Timeline 选区拖动

  当前问题:

  1. getTimeFromX() 无条件调用 snapTime()，导致 snap 开启时拖动句柄/整体移动会吸附到段边界，行为不可预测
  2. 句柄检测用像素阈值 1.5%，缩放后不一致：放大时句柄区域过窄，缩小时过宽
  3. 选区创建、句柄拖动、整体移动共用同一个 mousedown handler，互相干扰
  4. 整体移动时 getTimeFromX 每帧重新计算吸附位置，导致移动不平滑
  5. 整个选区区域都是 cursor-crosshair，没有区分句柄/整体/空白区域的光标

  重写方案:

  交互分层 — 把事件处理拆成三个独立层：
  - 选区创建层: 空白区域 mousedown → 拖拽创建新选区（覆盖旧选区）
  - 句柄层: 左/右句柄 mousedown → 拖拽调整边界。用独立的绝对定位 <div> 做句柄（宽 8px），而非靠百分比计算命中
  - 整体移动层: 选区 body mousedown → 平移整个选区。记录初始 offset = clickTime - selectionStart，移动时 newStart =
    currentTime - offset，避免原点漂移

  Snap 仅用于创建: 创建选区时启用 snap；拖动句柄和整体移动时不 snap，保证拖动手感平滑

  光标: 句柄 → ew-resize，选区 body → grab/grabbing，空白区域 → crosshair

  选区 body 移动算法:
  mousedown:  offset = clickTime - selectionStart
  mousemove:  newStart = clickTime - offset
              clamp(newStart, 0, duration - selectionDuration)
              selectionEnd = newStart + selectionDuration
  不再每帧重算吸附，只在 mouseup 时 emit 最终值

  句柄拖动算法:
  mousedown on left handle:  dragOrigin = selectionStart
  mousemove:  selectionStart = clamp(clickTime, selectionEnd - 0.1, selectionEnd)
  mousedown on right handle: dragOrigin = selectionEnd
  mousemove:  selectionEnd = clamp(clickTime, selectionStart + 0.1, selectionStart)

---
  Audit 2: 空白检测与字幕同步显示冲突

  当前问题:

  1. add_silence_results() 用 abs(e.start - sil["start"]) < 0.05

    做重复检测，只能匹配完全相同的时间范围。部分重叠（如字幕 1.0-3.0s，空白 2.5-4.0s）不处理
  2. 前端 mergedSegments 直接拼接所有 segments 排序，空白段和字幕段在时间线上可以重叠显示
  3. getEditForSegment() 用时间匹配找 EditDecision，但同一个时间点可能有多个

    EditDecision（一个来自空白检测，一个来自字幕删除），匹配不确定
  4. 没有优先级机制：用户手动标记字幕删除 vs 空白检测建议删除，冲突时不知道听谁的

  解决方案:

  后端: 空白检测时裁剪重叠字幕（核心改动）

  add_silence_results() 增加逻辑：对每个检测到的空白区间，检查与现有字幕段的重叠关系：

  - 完全包含: 字幕完全在空白内 → 跳过该字幕（空白覆盖）
  - 部分重叠（左）: 字幕跨越空白左边界 → 裁剪字幕的 end 到空白的 start
  - 部分重叠（右）: 字幕跨越空白右边界 → 裁剪字幕的 start 到空白的 end
  - 空白被字幕包含: 空白完全在字幕内 → 不裁剪字幕，但仍然创建空白段（用户可选择是否删除该段空白）
  - 无重叠: 正常处理

  同时，如果已有用户手动创建的 EditDecision（source="user"）与新空白重叠，保留用户决策，不覆盖。

  后端: EditDecision 增加 priority 字段使用

  当前模型已有 priority 字段但未使用。方案：
  - silence_detection → priority 100
  - analysis → priority 100
  - user → priority 200（用户操作优先级更高）

  get_edit_summary() 和导出时，同一时间段有多个 EditDecision 时取 priority 最高的。

  前端: 改进时间匹配

  getEditForSegment() 改为用 segment ID 匹配而非时间匹配：
  - 后端创建 EditDecision 时记录 segment_ids（当前已有 analysis_id，但 EditDecision 没有 segment_ids 字段）
  - 或者改为：EditDecision 的 id 直接包含 segment id（如 edit-user-sub-0001），前端用 e.id.includes(seg.id) 匹配

  前端: 重叠段视觉处理

  mergedSegments 的渲染：如果字幕段被裁剪后 start >= end，从列表中移除。重叠区域的空白段用不同的背景色标识。

---
  以上是两个功能的完整分析。请审计后告诉我是否可以按此方案实现，或需要调整。

```
你的审计逻辑非常清晰，显然你已经厌倦了现有代码中那种“靠运气对齐”的逻辑。这两项重构方案在工程化思路上都是正确的，特别是从**基于像素/时间的模糊匹配**转向**基于 DOM/ID 的精确控制**。

以下是我的审计结论和建议：

------

## Audit 1: Timeline 选区拖动

**状态：批准 (Approved)**

你的重构方案解决了 Timeline 交互中最核心的“漂移”和“冲突”问题。

### 关键点审计：

- **交互分层：** 这是最明智的改动。把 `mousedown` 逻辑拆分，能彻底解决“我想拖动句柄却不小心创建了新选区”的噩梦。
- **8px 句柄：** 这是一个非常实用的经验数值。建议在 CSS 中使用 `pointer-events: all` 并给句柄加一个略大于视觉宽度的透明感知区，以提升易用性。
- **Offset 算法：** 记录 `initial offset` 是解决“原点漂移”的标准解法。这能保证在 `mousemove` 时，选区完美同步鼠标位移。

### 补充建议：

- **吸附边界抖动：** 虽然你决定在拖动时不使用 `snap`，但建议在 `mouseup` 释放时，如果距离最近的 `snap` 点在极小阈值内（如 5px），自动吸附最终值。这既保证了过程平滑，又保证了结果精确。
- **Edge Case：** 在 `handle drag` 算法中，记得处理 `selectionStart` 超过 `selectionEnd` 的情况（即左右互换），或者直接 `clamp` 限制它们不能重叠。

------

## Audit 2: 空白检测与字幕同步冲突

**状态：需微调 (Needs Adjustment)**

你的优先级系统和 ID 匹配方案非常出色，但在“裁剪逻辑”上，我建议采取更稳妥的策略。

### 关键点审计：

- **优先级 (Priority)：** 引入 `user` (200) > `auto` (100) 是解决冲突的根本。
- **ID 匹配：** 坚决支持弃用时间匹配。在 Electron 环境下，浮点数精度抖动会让你在 `0.0000001s` 的差距上浪费无数时间。

### 调整建议：

- **逻辑裁剪 vs. 物理裁剪：** 你方案中提到的“裁剪字幕（后端改动）”是**破坏性**的。如果用户误删了空白段，原本被裁剪的字幕可能无法完美还原。
  - **建议：** 保持字幕原始时间戳不变。在渲染层（Getter）进行逻辑合并。如果 `EditDecision(Priority 200)` 标记了某段删除，则直接隐藏该范围内的所有显示。
- **“碎裂”风险：** 裁剪逻辑容易产生“碎片化字幕”（例如一个 0.5s 的单词被切成了两半）。建议增加一个阈值：如果裁剪后剩余的字幕长度小于 0.2s，直接将其设为 `hidden` 而不是保留一个肉眼看不见的极短段。
- **视觉冲突：** 当空白段和字幕重叠时，UI 上建议使用**堆叠（Stacking）\**而非\**合并（Merging）**。字幕段在下，空白检测阴影在上，这样用户能一眼看出“这里有字幕，但系统建议因为静音而删除”。

### 总结

**你的重写方案逻辑严密，可以立即进入实现阶段。**

对于 `Audit 2`，建议优先考虑“逻辑屏蔽”而非“物理裁剪”，以保留数据的可溯源性。

你打算先从哪一个 Audit 开始落地？我也建议你检查一下建议栏的 `z-index` 或 `v-if` 逻辑，那个问题可能只是缺了一行代码。
```

> 1. 进入编辑用快捷方式（双击）有点不够直观，应该添加一个进入编辑的按钮，进入编辑模式之后改为显示保存按钮，并支持Esc取消编辑（恢复原本内容，没有变动则不做变动）并退出编辑模式
> 2. 点击外部退出编辑模式的问题：现在点击其他行的字幕或静音区域、点击时间戳都不会退出，而且会丢失选择，导致它保持编辑模式不变直到再一次点击它
> 3. 应该添加一个全局按钮，让所有的字幕都进入可编辑的模式，并且关闭退出编辑模式的这些快捷方式，字幕进入编辑模式之后，原本进入编辑模式的按钮变成全部退出编辑模式的按钮

- 自定义播放器模块
  - 播放选项栏改为始终位于模块最下方
  - 音量修改部分鼠标离开图标就消失无法调整音量
- 提示模块
  - Clip region added 提示始终显示无法关闭，而且 这个提示也没啥用吧
- 时间线模块（包括Timeline和时间线）
  - 无法删除某个误添加的区块
  - 添加的区块仍会与字幕重叠，导致无法处理，冲突条件仍需优化，要不干脆改成两条时间轴吧，一条字幕时间轴，一条空白检测时间轴，然后就可以新加字幕/新加删除区域分开处理
  - 音频波形未显示
  - 空白检测覆盖到字幕区域的冲突仍未处理好，即便是覆盖了很小一块也会导致整条字幕被标记删除，应该是字幕部分仅产出被覆盖的区域
- 检测模块
  - Analysis检测后的建议无法拒绝，即便是点击忽略或是切换为已保留，仍然是显示删除线和红色提示
- 项目管理
  - 首页，即视频上传页并未提供打开已有项目的功能，而且同样的文件打开并非打开已有工程，而是完全新建工程
- 核心功能疑似没有实现
  - 有一种场景是，用户希望上传字幕之后根据字幕，仅保留字幕时间范围及每句字幕前后*最多*n（一般为0.x）秒的内容，并导出对应音频和与导出音频相匹配的字幕
  - 或者是用户还能叠加静音检测，得到一个更加精细的控制
  - 而且由于静音检测或字幕检测的误判，可能会导致两段声音直接硬切，所以希望能够可选地在每句话之间加入很短的淡入淡出和一小段静音

- 添加一键删除空白检测标记的按钮（在Detect按钮设置按钮的右边一个垃圾桶小按钮，点击弹窗确认是否删除）
- SubtitleTrim检测之后没有实际内容添加到Timeline中，且通知条无法关闭始终显示
- 时间线标尺需要细化（显示地更密一些），并且保持现在能够跟随缩放而变化的功能
- 项目保存没有提示（提示要在2s后自动关闭！）且不能影响进程
- 字幕块与空白检测块重叠问题仍然有问题：我必须强调最基本的原则：不能因为字幕块被空白覆盖而删除整个字幕块。希望实现的效果是，优先字幕块需要保留，并且可以设置被空白检测覆盖的字幕块会缩减到空白检测范围之外即可

- 导出存在问题
  - 仅测试字幕+padding去除功能时，会出现最后几个字幕块内容缺漏的问题，加上空白检测后会出现同样的问题
  - 导出的字幕与导出的音视频并不对应
  - 现在导出的完整逻辑是什么样的呢，导出是如何与Timeline联动的
- 字幕块padding删除逻辑补充：如果某条字幕标记已删除，那么SubtitleTrim检测的时候也需要无视它
- 新建导出界面（待实现）
  - 现有导出按钮删除，仅保留一个跳转导出界面的按钮
  - 导出界面中允许编码设置
  - 导出界面允许预览播放（跳过所有标注已删除区域的播放）
  - 导出界面允许导出通用时间线格式
- 时间线需要新增功能，双击某个块时能够定位到Timeline中的对应位置

## 0.2.0

- Analysis按钮一到SubtitleTrim及其删除按钮右侧
- DetectSilence检测出来的静音区域没法单独删除，只能全部清除（SubtitleTrim无需单独删除是因为他能够通过字幕块的调整之后重新检测重新划定，但是DetectSilence没法用这种方式，就需要有单独的DetectSilence块来编辑）
- 首页导入页支持通过拖入project.json或一级含project.json的文件夹读取项目

---

- 导出按钮右对齐
- 我的系统有nv显卡但是显示未检测到NVIDIAGPU，硬件编码不可用，没有显示av1_nvenc，而且libsvtav1应该除非系统为mac都要显示的啊
  - Unhandled bridge exception in detect_gpu
- 预览无法使用，仅显示xxx个删除区域
- 导出失败:Method 'export_audio' not found on bridge
  - Traceback (most recent call last):
      File "Q:\Git\GithubManager\Milo-Cut\pywebvue\bridge.py", line 32, in wrapper
        return func(*args, **kwargs)
               ^^^^^^^^^^^^^^^^^^^^^
      File "Q:\Git\GithubManager\Milo-Cut\main.py", line 500, in detect_gpu
        result = subprocess.run(
                 ^^^^^^^^^^
    NameError: name 'subprocess' is not defined
- 导出失败:Method 'export_video' not found on bridge
  - 控制台没有额外报错
- 导出失败:Method'export_subtitle' not found on bridge
  - 控制台没有额外报错
- 导出失败:[Ermo 22] Invalid argument: "('D:I1下载\Timeline 1.edl.mp4,)"
  - 控制台没有额外报错
- 导出失败:[Errno 22] Invalid argument:"('D:11下载ITimeline 1.fcpxml.mp4,)"
  - 控制台没有额外报错

> - 预览播放需要支持音量调整
> - 编码器设置并未成功，设置了AV1，导出的视频仍是H264编码
> - EDL导出失败:[Errno 22] Invalid argument:"('D:1\下载\Timeline 1.edl,)"
> FCPXML导出失败:[Errno 22] Invalid argument:"('D:\\下载\Timeline 1.fcpxml',)”

- /ecc:plan 在时间线上添加声音波形显示
- 时间线区域的缩放出了Ctrl+滚轮还应该有实体按钮+-
- DetectSilence允许在静音检测后、与字幕冲突检测前，先用margin值（0s-0.01s-0.5s，默认0s）自行缩一次范围（如果范围本身效果margin值则删除这个静音区域标识，如果margin值*2应当小于min duration）
- 目前如果DetectSilence与字幕冲突默认优先字幕，会缩减静音区域到字幕空隙，希望进一步允许DetectSilence在字幕空隙中还要和字幕保持距离（类似SubtitleTrim的padding）
- DetectSilence的min duration标尺缩到0.05-2s并允许0.05一格调整
- DetectSilence有一个检测兼容问题，我希望如果执行检测时某个字幕块已经标注为已删除，则字幕保护裁剪忽略这一字幕块

## 待提出的问题

- 一个前端bug，当Waveform滑块滑到最右边时会引发窗口横向滑块出现，遮挡Waveform滑块，并且无法消除，应当禁止窗口横向滑块出现
- 时间线导出支持OTTI
- OTTI（能否可选给每个音频块添加淡入淡出？OTTI还支持什么功能是适配我们这个项目的）

- 目前OTIO无法导入剪辑软件，怀疑构建失败，python不是有opentimelineio吗，用这个库构建OTIO文件

- OTTI建议如下：

````
OTIO 就是你要的那种：**一个 .otio 文件，PR 和达芬奇都能直接导入/导出**，而且比 XML/AAF 更现代、更稳、扩展性强很多。下面直接讲重点（2026 现状）。 --- ## ✅ OTIO 是什么 **OpenTimelineIO（.otio/.otioz）**：ASWF 开源的**时间线交换标准**，本质是 JSON，只存剪辑结构、时间码、轨道、元数据、素材路径，**不存视频画面**。 - **达芬奇**：**原生支持导入/导出 OTIO**（18+ 完全内置，不用插件） - **PR**：**2024 之后 Beta 原生支持 OTIO**；正式版 2025+ 已内置（文件 → 导入/导出 → OpenTimelineIO） - 结论：**2026 年，PR ↔ 达芬奇 用 OTIO 已经是官方原生工作流**，不需要 XML/AAF 绕路 --- ## ✅ PR ↔ 达芬奇 OTIO 互导（极简） ### 1）PR → 达芬奇（.otio） 1. PR：文件 → 导出 → **OpenTimelineIO（.otio）** 2. 达芬奇：文件 → 导入时间线 → **导入 OTIO** 3. 自动还原：**剪辑、多轨道、时间码、标记、帧率、素材路径** ### 2）达芬奇 → PR（.otio） 1. 达芬奇：交付 → 渲染预设选 **OpenTimelineIO（.otio）** 2. PR：文件 → 导入 → 选 .otio，直接生成序列 ### 3）OTIOZ（打包，更稳） - **.otioz = OTIO + 素材打包**（类似压缩包） - 适合：**换电脑/异地协作/路径乱了**的场景，直接打包带走，对方解压即用 --- ## ✅ OTIO vs XML/AAF（2026 实测） | 格式 | PR 原生 | 达芬奇原生 | 多轨道 | 元数据/标记 | 稳定性 | 扩展性 | |---|---|---|---|---|---|---| | **OTIO** | ✅ 2025+ | ✅ 18+ | ✅ 完美 | ✅ 完整 | ⭐⭐⭐⭐⭐ | 强（开源可扩展） | | FCP XML | ✅ | ✅ | ✅ 一般 | ❌ 丢失多 | ⭐⭐⭐⭐ | 弱 | | AAF | ✅ | ✅ | ✅ 好 | ⚠️ 部分丢 | ⭐⭐⭐⭐ | 中 | 一句话：**OTIO 是现在 PR ↔ 达芬奇 互导的最佳格式，没有之一**。 --- ## ✅ 注意（避坑） 1. **素材路径尽量不变**：OTIO 靠路径链接素材，路径变了要手动重链接 2. **复杂特效/插件会丢**：OTIO 只传**剪辑结构+元数据**，不传 PR 调色、Lumetri、第三方插件；达芬奇节点也不会回 PR 3. **分辨率/帧率统一**：工程设置一致（如 1080p 25fps），避免错位 --- ## ✅ 结论（你要的答案） - **能同时导入 PR 和达芬奇的工程文件：就是 OTIO（.otio/.otioz）** - **2026 年两者都原生支持**，比 XML/AAF 更稳、更全、更现代 - 工作流：**PR ↔ OTIO ↔ 达芬奇**，一步到位 要不要我给你一份可直接照着点的“PR ↔ 达芬奇 OTIO 互导极简操作清单”（含菜单路径和推荐参数）？
# OTIO 相对路径标准模板（直接复制即用）
保存为 `timeline.otio`，**仅改文件名即可**，全程相对路径，PR/达芬奇通用
```json
{
    "OTIO_SCHEMA": "timeline.1",
    "name": "项目时间线",
    "global_start_time": {
        "rate": 25.0,
        "value": 0
    },
    "tracks": [
        {
            "OTIO_SCHEMA": "track.1",
            "name": "视频轨道1",
            "kind": "Video",
            "children": [
                {
                    "OTIO_SCHEMA": "clip.1",
                    "name": "素材片段",
                    "media_reference": {
                        "OTIO_SCHEMA": "external_reference.1",
                        "target_url": "../media/video/素材.mp4",
                        "available_range": {
                            "start_time": {"rate":25.0,"value":0},
                            "duration": {"rate":25.0,"value":100}
                        }
                    },
                    "source_range": {
                        "start_time": {"rate":25.0,"value":0},
                        "duration": {"rate":25.0,"value":100}
                    }
                }
            ]
        },
        {
            "OTIO_SCHEMA": "track.1",
            "name": "音频轨道1",
            "kind": "Audio",
            "children": [
                {
                    "OTIO_SCHEMA": "clip.1",
                    "name": "音频素材",
                    "media_reference": {
                        "OTIO_SCHEMA": "external_reference.1",
                        "target_url": "../media/audio/音效.wav",
                        "available_range": {
                            "start_time": {"rate":25.0,"value":0},
                            "duration": {"rate":25.0,"value":100}
                        }
                    },
                    "source_range": {
                        "start_time": {"rate":25.0,"value":0},
                        "duration": {"rate":25.0,"value":100}
                    }
                }
            ]
        }
    ]
}
```

## 固定目录结构（必遵守，永不脱机）
```
项目总文件夹
├─ 剪辑工程文件夹
│  └─ timeline.otio    # OTIO放这里
└─ media               # 素材总文件夹
   ├─ video
   └─ audio
```
- `../media/` = **OTIO向上一级找到素材文件夹**
- 整个项目文件夹**随便移动、换盘符、换电脑**，路径永久生效

## 快速批量替换绝对路径 → 相对路径
1. 用记事本打开导出的原生OTIO
2. 查找所有：`file:///D:/你的长路径/`
3. 全部替换为：`../media/`
4. 保存直接导入PR/达芬奇，自动识别

## 帧率修改
把里面所有 `25.0` 改成你工程帧率：**24.0 / 30.0 / 60.0**

## 软件导出强制相对路径最终设置
1. PR：项目设置 → 勾选**首选使用相对路径**
2. 达芬奇：导出选 **OTIOZ** 自动内置相对路径，无需手动改
````

请根据以上内容撰写 @docs/audit-report-0.2.0-3.md

> - 导出界面播放预览再返回编辑界面之后，会有半分钟左右波形显示不见了，也无法回到导入页，半分钟后显示并可回到导入页
> - 所有使用旧通知的均改用Toast 通知系统
> - OTIO按钮提到最上方并写清楚是DaVinci/NewPR/Others
> - OTIO音频转场可选交叉过渡或是分别淡入淡出
> - 音视频转场导出能否通过filtercomplex实现（音频过渡是否也可选，共用一个勾选框）
> - Waveform滑块滑动时非常卡顿，请优化性能
> - 评估这几个问题，然后补充到 @..\docs\audit-report-0.2.0-3.md 的新附录中
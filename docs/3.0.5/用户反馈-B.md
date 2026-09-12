# Milo-Cut v3.0.4 用户走查反馈 —— Persona B：老周（精剪型视频作者）

> 走查人：老周（知识区 UP 主，每周 2-3 条口播视频；2.x「占位块撑间隙」习惯用户；重度依赖波形手势 + undo + 建议面板逐条审阅）
> 走查对象：v3.0.4（tag `v3.0.4`，已回并主干）
> 走查方式：文档 + 代码求证（无头环境，未跑 GUI）；所有行为结论均给出 文件:行号 或 record 章节依据
> 用途：3.0.5 立项预备的用户调研输入
> 日期：2026-09

---

## 一、旅程走查记录（J1-J10）

### J1 静音检测 → 智能删除 → 建议面板审阅流（基线，验证无回退）

- **预期**：老流程一条龙不回退——静音检测建议进面板「静音检测」组，智能删除进「智能删除/部分删除」组，逐条确认/忽略、批量操作、undo 正常。
- **实际**：三分组逻辑未动（`frontend/src/components/workspace/SuggestionPanel.vue:68-99`：静音 `silence_detection`、智能 `llm_smart`、部分删除 `partial_delete`）；v3.0.4 新增 manual 源后，头部计数对两个 legacy 源保持 delete-only 过滤逐字节不变（`SuggestionPanel.vue:123-136` 的 `isCounted`：manual 计 keep，legacy 只计 delete——它们本来不产 keep，计数零变化）；确认/忽略/批量全走既有 `update_edit_decision` / `confirmEdit` / `rejectEdit` 链（`frontend/src/composables/useAnalysis.ts:70-88`），每次操作前 `pushSnapshot(["edits"], "编辑决策")`（`useAnalysis.ts:73,83,94,119`）。门禁终态 pytest 833 / vitest 840-839（record-3.0.4.md §0 发布终态门禁）。
- **摩擦评级**：低。基线稳，无回退感。

### J2 范围标记 toggle ON → 空白框选 → 气泡三选 → 落盘 → 覆层 pending 即刻可见？toggle OFF 一切如旧？

- **预期**：toggle 开关有明确状态感；框选松手弹气泡（删除/保留/取消）；确认后 pending 覆层立刻出现；关掉 toggle 后波形行为与 3.0.3 完全一致。
- **实际**：
  - toggle 默认 OFF（`frontend/src/components/waveform/WaveformEditor.vue:307`），激活态琥珀色 + 文案「范围标记/标记中」（`WaveformEditor.vue:1253-1261`），与「建段」toggle 并排，工具栏心智一致。
  - multi 模式行内 press-drag 框选（`WaveformEditor.vue:875-901`），basic 模式走 `range-press` 桥（`:906-940`；`frontend/src/components/waveform/SegmentBlocksLayer.vue:194-205` 在 "seek" 分支之前转发）；拖拽中琥珀色预览条（`WaveformEditor.vue:1400-1405`），与蓝色建段预览、蓝色 Shift 多选框视觉可区分。
  - 松手弹内嵌气泡：时间区间 + 时长标签、删除（默认聚焦，Enter 直接触发）/保留/取消三按钮（`WaveformEditor.vue:853-855` Q9 注释、`:1408-1434`）。确认后 `emit("range-decision")` → WorkspacePage `handleRangeDecision`：先 `pushSnapshot(["edits"], "手动范围")` 再调 `add_range_decision`，patch 走 project-updated（`frontend/src/pages/WorkspacePage.vue:990-999`）。
  - pending 覆层即刻可见：patch 更新 edits → `visibleEditRanges`（`SegmentBlocksLayer.vue:141-160`）→ pending = 同款红纹 `opacity-50` 半透明（`SegmentBlocksLayer.vue:171-176`）；confirmed delete 红纹逐字节 = 3.0.3（`:166` 注释明确锁死）。覆盖响应是即时的，这点做得好。
  - toggle OFF：`closeRangeBubble()` 清掉未决气泡（`WaveformEditor.vue:308-311`），手势路由回落 scrub（`:779-782`），OFF 三格零回退有 vitest 锁（record P3-6）。
  - 毛边（不属 smoke-fix 已修 8 项）：①气泡无 Esc 关闭（WaveformEditor 文档级键盘捕获只有箭头键，`:319-328` 在 SegmentBlocksLayer；编辑器本体无 Esc→closeRangeBubble 绑定），取消只能鼠标点「取消」；②气泡出现后点击副轨 lane / 列表区等非主轨空白处，气泡不会自动消失，会一直挂在波形上直到下一次框选或切 toggle。
- **摩擦评级**：低-中（主链路顺；气泡关闭路径单一 + 挂留是小毛边）。

### J3 手势矩阵：范围 ON × 建段 ON、Ctrl/Shift 拖拽、multi 段多选——互斥提示可理解吗

- **预期**：Ctrl 建段、Shift 跨行多选不被范围模式抢走；两个 toggle 同开时有能被我理解的「谁赢」提示。
- **实际**：
  - 优先级实现正确：multi 路由 Ctrl → Shift → rangeMode → scrub 依次判定（`WaveformEditor.vue:771-783`，注释明确「byte-identical with the range mode on or off」）；basic 路径本就无 Ctrl/Shift 手势，无冲突面。
  - 互斥提示**只存在于按钮 hover title**：建段按钮 title「…与范围标记模式同开时以范围标记优先，建段暂停」（`WaveformEditor.vue:1247`），范围按钮 title 同义（`:1257`）。
  - **问题**：两 toggle 同 ON 时，建段按钮**仍然蓝色高亮、文案仍是「建段中」**（`:1243-1251` 绑定的是 `buildMode` 而非实际生效的 `buildMode && !rangeMode`；实际传给 lane 的是 `:build-mode="buildMode && !rangeMode"`，`:1367/:1555`）。也就是我看到的「建段中」在撒谎——此时点副轨 lane 不会建段，但没有任何视觉降档、置灰或 toast 提示「建段已暂停」。我不 hover tooltip 就不知道为什么点了没反应。这是「行为收窄但 UI 状态不收窄」的典型毛边。
- **摩擦评级**：中。

### J4 时间码 popover：口播精确输入

- **预期**：能按秒精确输起止、二选删除/保留、非法输入当场被拦；最好贴合口播精修习惯。
- **实际**：
  - 入口常驻建议面板头部「+ 时间码」按钮（`SuggestionPanel.vue:317-324`），空工程也能建第一条（头部条常驻裁决，`:302-305` 注释；分组本体受空组守卫隐藏 `:58-65`）——这个落点裁决我认可，入口不被空状态吞掉。
  - 起止 number 输入（step 0.1，`:336-358`）+ 删除/保留二选（默认删除，`:181-182,360-380`）；空/非数/end≤start 就地拒绝、零桥调（`:190-209`），错误文案明确（`:198,202`）。
  - 提交经 provide/inject 与气泡共用同一 `handleRangeDecision`（`:170-174` 注释 + `WorkspacePage.vue:958,990`），两入口语义一致，好评。
  - 毛边：①只收纯秒数（"如 12.5"），口播精修场景我脑子里是 `12:30.5` 这种 mm:ss，换算要停顿；②没有「填入当前播放头时间」按钮，想标「从现在起到下个停顿」还得去波形上读数；③起止超过媒体时长前端不拦，后端静默 clamp 到 duration（`core/project_service.py:1313-1329`），我输 9999 不会报错，区间被悄悄截短且**无任何提示**；④「添加」成功后 popover 直接关（`:208` closeTimecode），无成功 toast——反馈仅靠面板组里多出一条 + 覆层出现，在长列表里不够醒目。
- **摩擦评级**：中。

### J5 建议面板手动范围分组：[·]/[Y]/[N]、确认文案、逐条操作

- **预期**：pending/confirmed/rejected 三态一眼可辨；「确认 = 参与裁剪计算」能纠正我「确认 = 导出」的直觉误解；逐条确认/忽略/删除顺手。
- **实际**：
  - manual 组默认展开（`SuggestionPanel.vue:23-26`），建完立刻能看到条目；条目 label 前缀「删除/保留 X.Xs」即 action 徽（`:106-118`）；[·] 待处理 / [Y] 已确认 / [N] 已忽略三态徽章齐全（`:469-483`），manual 是唯一显式带 [·] 的组，我支持这个差异化——手动标的东西确实需要「还没生效」的心智。
  - 组头可见「清除」按钮 + 条目右键「删除此项（永久，含已确认）」+ 双重 confirm（`:437-445,267-276,538-544`）——smoke-fix-1 缺陷 2 的修复形态合理，永久删除的文案风险提示到位。
  - **核心毛边一：关键确认文案只在 hover title 里**。`confirmTitle` 返回「确认 = 参与裁剪计算（保留区间将从自动裁剪中扣除；非导出动作）」（`:154-159`），但它绑在确认按钮的 `:title` 上（`:496`）——不把鼠标悬停 1 秒就永远看不到。PRD R4.4 明确这句文案的存在理由是「防用户把确认 keep 误解为导出动作」（PRD-v3.0.4.md:230,232），藏在 tooltip 里，防误解效果大打折扣。老用户会凭 2.x/静音组的肌肉记忆直接点确认。
  - **核心毛边二：被「忽略」的手动范围，波形覆层还在**。覆层过滤只看 `target_type === "range"` 不看 status（`SegmentBlocksLayer.vue:147-148`），注释自认「Rejected is NOT filtered here (status quo kept)」（`:102`）。对静音/智能删除这是 3.0.3 既有现状（legacy 建议忽略后红纹留着情有可原）；但对手动范围，rejected 是 v3.0.4 新引入的用户路径——我明确说「这条不要了」，波形上那条蓝纹/红纹却原封不动（仅 50% 透明度的是 pending，rejected 连降档都没有），第一反应就是「忽略没生效」。
- **摩擦评级**：中-高（两条都直接打击「手动范围可信」这个核心体验）。

### J6 keep 闭环：标 keep → 确认 → 重跑自动裁剪 → 保住 + 陈旧红纹消失 → 导出预览

- **预期**：确认后的 keep 真的能把 2.x「占位块撑住」的那段从自动裁剪里抠出来；重跑后旧红纹消失；keep 和手动删除并存时我知道听谁的。
- **实际**：
  - 数据链完整：确认 keep（`update_edit_decision` → confirmed）后，`generate_subtitle_keep_ranges` 收集 `action=keep ∧ status=confirmed ∧ target_type=range`（不限 source）并入 keep 集（`core/project_service.py:2888-2895`），keep 区间从删除补集自然扣除——**求证结论：确认 keep 确实参与重跑计算**，2.x 占位块语义等价成立。
  - 陈旧剔除也在：相交的 `subtitle_trim` delete 被移除且 `invalidated_count` 计数（`:2915-2935`），手动决策永不触碰（`:2914` 注释）。
  - **但 `invalidated_count` 用户看不见**：前端 `generateSubtitleKeepRanges` 的返回类型只取 `keep_ranges/delete_ranges/new_edits` 三个数（`frontend/src/composables/useEdit.ts:181-202`），invalidated_count 被直接丢弃，无 toast、无面板提示。「3 条旧红纹被清掉了」这件事只能靠我自己盯着波形前后对比。我点「重新生成修剪区间」时最想要的信息恰恰是「这次改了什么」。
  - 导出端求证：`_get_confirmed_deletions` 只认 `action=delete ∧ status=confirmed`（`core/export_service.py:599-608`）——keep 不进导出，手动 confirmed delete 与 subtitle_trim 并列去重消费，红蓝重叠时**导出服从 delete**，与 PRD R4.4 消费边界一致（PRD:230）。
  - **理解成本**：红蓝并存谁赢，应用内零解释——面板条目、覆层 hover、确认文案都没提；只有 README_zh 写了（README_zh.md:70「与手动删除区间并存时导出服从手动删除」）。我这种会读 README 的算幸存者，普通用户碰到红蓝叠一起的第一反应是「这到底剪不剪？」。且导出预览里被 keep 顶掉的部分不会有任何标识。
- **摩擦评级**：中-高（闭环功能全通，但「可感知、可信任」层欠收口）。

### J7 undo 链：建范围 / 确认 / 删除 / 重跑裁剪的粒度

- **预期**：每步一个 undo，粒度不吞步不空步。
- **实际**：全部走 edits 层快照，一次操作一个快照——建范围「手动范围」（`WorkspacePage.vue:992`）；单条确认/忽略/批量删除「编辑决策」（`useAnalysis.ts:73,83,94,119`）；重跑裁剪「生成保留区间」（`useEdit.ts:193`）；删修剪编辑「删除修剪编辑」（`useEdit.ts:174`）。粒度一致，undo 一次回退一步，验证不吞步。
- 毛边：`handleRangeDecision` 是**先无条件 pushSnapshot 再调桥**（`WorkspacePage.vue:992-993`），而 ±0.05s 幂等 duplicate 时后端零写入零 revision（`project_service.py:1346-1356`）——前端却已经入栈了一个内容不变的快照，undo 栈被「空步」污染（连按几次 undo 都「没变化」，实际在消耗空快照）。`pushSnapshot` 本身无去重（`frontend/src/composables/useUndoRedo.ts:48-58`）。此毛边与 F-B-01 同源。
- **摩擦评级**：低-中。

### J8 编辑扫掠副轨：列表「编辑」按钮进副轨全列编辑、切轨 flush、编辑态跨轨保持

- **预期**：副轨视图点「编辑」一键进出全列文本编辑；切轨前草稿不丢；编辑态切轨不重置。
- **实际**：按钮文案感知轨道视图——副轨视图显示「编辑〈轨名〉」、编辑中统一「退出编辑」（`frontend/src/components/workspace/Timeline.vue:370-376`）；3.0.3 的副轨早退已按 T1 方案 A 移除（record P3-2；PRD R3.1 裁决反转理由 = 用户反馈「按钮坏了」，跟我对 3.0.3 的观感一致）；切轨 flush 走 `flushPendingTrackUpdates`（`frontend/src/composables/useTrackEdit.ts:227`），编辑态跨轨保持有 `WorkspacePage.trackEdit.test.ts` 两例锁。
- 毛边：按钮 tooltip 是英文「Edit all subtitles / Exit edit mode」（`Timeline.vue:625`）——按钮文案已经轨感知了，hover 提示却没跟上（即候选清单 #4，属实）。
- **摩擦评级**：低（功能通；tooltip 是一行文案的毛边）。

### J9 副轨 lane 建段 + 语义搜索定位主轨命中段

- **预期**：建段模式下点副轨 lane 空白能建段（2.x/3.0.1 承诺的历史断链接通）；副轨视图下语义搜索显示的结果是主轨的时间/文本，点击定位到主轨。
- **实际**：lane 建段三处接线落地（record P3-3；basic/multi 双路 `:build-mode` 透传 + `@create-at` 桥，默认 0.5s 宽）；语义搜索 `segmentMap` 改由 `mainSegments ?? segments` 构建（`frontend/src/components/workspace/SemanticSearchBar.vue:37-42`），轨模式下文本/时间取自主轨、点击 `emit("seek")` 定位主轨命中段（`:101`），主轨模式零变化。翻译轨场景（搜中文定位主轨原文）验证逻辑自洽。
- **摩擦评级**：低。

### J10 边界：±0.05s 幂等、clamp、空段先拒、重叠合法

- **预期**：重复框选别给我建两条；越界能兜住；空工程别崩；重叠范围别报错。
- **实际**：
  - **±0.05s 幂等（重要缺陷，见 F-B-01）**：后端同 action 近似等值返回既有 edit + `duplicate: True`，零写入零 revision（`project_service.py:1346-1356`；后端测试 `tests/test_add_range_decision.py:10-13`）。**但前端没有 duplicate 分支**：`handleRangeDecision` 只要 `res.success && res.data` 就 `emit("project-updated", res.data)`（`WorkspacePage.vue:994-995`），而 duplicate 的 `res.data = {edit_id, duplicate}` **没有 revision 字段** → App.vue 的 `isProjectPatch` 判 false（要求 revision 为 number，`frontend/src/types/project.ts:120-127`）→ 走 else 分支 `project.value = data`（`frontend/src/App.vue:126-135`）→ **整个内存工程对象被替换成 `{edit_id, duplicate}` 假对象**，后续渲染取 `project.timelines` 等字段全部落空。前端测试只覆盖成功 patch 与失败 toast 两态（`frontend/src/pages/WorkspacePage.rangeDecision.test.ts`：2 例均绿，无 duplicate 用例——本轮实跑验证）。触发场景很日常：同一区间重复框选确认、时间码重复提交同值、对已确认区间微调手抖落在 0.05s 内再确认。
  - clamp 到媒体时长：后端上界 `media.duration`（缺失取主轨段 max end，同 keep 口径），空段工程先拒且文案是中文「无媒体时长且无字幕段，无法确定范围上界」（`project_service.py:1313-1326`），前端 toast 会显示该文案——拒绝路径可用。但 clamp 成功路径静默截短（见 J4 ③）。
  - clamp 后 end≤start 拒（`:1330-1337`）；action 非法拒（`:1340-1344`）。
  - 范围重叠合法：非近似重叠一律放行（判据注释 `:1302-1304`），由 keep 感知计算消解——与我的「多刷几层范围再慢慢审」习惯兼容，好评。
- **摩擦评级**：高（F-B-01 属数据安全级）。

---

## 二、体验问题清单

### F-B-01 duplicate 幂等返回会把前端工程对象替换成假对象（数据安全级）

- **场景**：范围标记模式下对已存在的手动范围 ±0.05s 内重复框选确认（或时间码 popover 重复提交同值），后端按幂等设计返回 `{success, data: {edit_id, duplicate: true}}`（零写入，`core/project_service.py:1353-1356`）。
- **痛点**：前端无 duplicate 分支，`WorkspacePage.vue:994-995` 把该返回当 patch emit；`App.vue:126-135` 的 `isProjectPatch`（`frontend/src/types/project.ts:120-127`，要求 revision 为 number）判否，走 legacy 分支 `project.value = data` —— 内存工程被整体替换为两个键的假对象，工作区渲染随之崩坏。附带：emit 前已无条件 `pushSnapshot(["edits"])`（`WorkspacePage.vue:992`），undo 栈还多了一条空步。前端测试未覆盖 duplicate 态（`WorkspacePage.rangeDecision.test.ts` 仅成功/失败 2 例）。
- **期望**：前端识别 `duplicate: true`（后端可同时补 revision 或前端按 data 形状分流），静默跳过或轻提示「该范围已存在（已复用原条目）」，且不入 undo 快照。
- **严重度**：高（P0 级；触发频率不低——防抖双击恰恰是幂等设计的服务对象，却在前端变成炸点）。

### F-B-02 「确认 = 参与裁剪计算」防误解文案只在 hover title 里

- **场景**：建议面板逐条审阅手动范围，点「确认」。
- **痛点**：PRD R4.4 三点成本之一就是这句文案（PRD-v3.0.4.md:232），但它只绑定在确认按钮 `:title`（`SuggestionPanel.vue:154-159,496`）。hover tooltip 触达率极低，我的实际行为是凭静音组肌肉记忆直接点确认——确认 keep 后我以为是「导出保留片段」，实际只是让它参与下一次重跑计算，两者相差一次「重新生成修剪区间」操作。
- **期望**：keep 条目的确认动作内联可见文案（按钮旁小字 / 确认后 toast 一句「已确认保留：将在下次自动裁剪计算中扣除」），至少 keep 与 delete 确认后给差异化 toast。
- **严重度**：中-高（直接决定 keep 闭环能不能被正确使用）。

### F-B-03 keep 重跑的 invalidated_count 前端丢弃，「这次清理了什么」不可见

- **场景**：标了若干 keep 并确认后，点「重新生成修剪区间」。
- **痛点**：后端把被剔除的陈旧 subtitle_trim 计数放进返回 data 并打日志（`core/project_service.py:2915-2935,2986`），前端返回类型只取三个数（`frontend/src/composables/useEdit.ts:181-202`），invalidated_count 被丢弃，无任何用户可见反馈。重跑是覆盖性操作，我最需要知道「几条旧红纹被清掉、几条新增、几条保留原样」。
- **期望**：重跑完成 toast 汇报 `new_edits / invalidated_count`（如「新增 12 条、按保留区间清除 2 条旧区间」）。
- **严重度**：中。

### F-B-04 被忽略（rejected）的手动范围覆层仍显示

- **场景**：对某条手动范围点「忽略」。
- **痛点**：覆层过滤不看 status（`SegmentBlocksLayer.vue:147-148`，注释自认 status quo），红/蓝纹原样留在波形上。「忽略」的字面承诺（这条不作数）与波形显示矛盾；对手动范围这是 v3.0.4 新引入路径，比 legacy 建议组更刺眼。
- **期望**：rejected 的 range 覆层过滤掉或降为极淡描边；至少在覆层 hover 里显示「已忽略」状态。
- **严重度**：中。

### F-B-05 双 toggle 同开时「建段中」按钮视觉态与实际行为不符

- **场景**：范围标记与建段两个 toggle 同 ON，点副轨 lane 空白。
- **痛点**：实际传参是 `buildMode && !rangeMode`（`WaveformEditor.vue:1367,1555`），建段已被暂停，但建段按钮仍蓝色高亮显示「建段中」（`:1243-1251`）；互斥解释只在 hover title（`:1247`）。点击无反应时用户无从归因。
- **期望**：范围 ON 时建段按钮降档（置灰/描边虚化）或文案变「建段（已暂停）」；激活瞬间 toast 一次即可。
- **严重度**：中。

### F-B-06 时间码 popover 输入效率与反馈偏弱

- **场景**：口播精修时按时间码建范围。
- **痛点**：①只支持纯秒数，不支持 mm:ss（`SuggestionPanel.vue:335-357`）；②无「当前播放头」快捷填入；③超出媒体时长前端不预检，后端 clamp 静默截短（`project_service.py:1328-1329`），结果区间与输入不符且无提示；④添加成功无 toast。
- **期望**：支持 mm:ss:ss.s 解析；起/止旁加「取当前播放头」小按钮；clamp 发生时回显「已按媒体时长调整为止点 xx.xs」。
- **严重度**：中。

### F-B-07 红蓝并存时「导出服从 delete」应用内零解释

- **场景**：keep 区间与手动 delete（或自动裁剪区间）重叠，进导出。
- **痛点**：语义是刻意的（PRD R4.4：手动决策优先，`export_service.py:599-608` 只认 confirmed delete），但应用内无任何提示，红蓝叠块的波形观感是「既保又删」的矛盾态；导出预览不会标出被 keep 顶掉的部分。只有 README_zh（:70）写了。
- **期望**：红蓝重叠时覆层 hover 或导出确认页给一句「重叠区间按删除处理」。
- **严重度**：低-中。

### F-B-08 确认气泡关闭路径单一、点击外部不消泡

- **场景**：框选后气泡已弹，改主意去点别处。
- **痛点**：无 Esc 关闭（WaveformEditor 无对应键绑定），点段块/列表/副轨 lane 不消泡，气泡滞留至下一次框选或 toggle 切换（`WaveformEditor.vue:833-836` 的 closeRangeBubble 仅四路触发）。
- **期望**：Esc 关闭 + 点击波形区外任意处取消（等价「取消」）。
- **严重度**：低。

### F-B-09 keep 覆层 hover 提示是英文且语义错误「Delete range」

- **场景**：鼠标悬停蓝色 keep 覆层想确认这条是什么。
- **痛点**：覆层 title 硬编码 `` `Delete range: ${start}s - ${end}s` ``（`SegmentBlocksLayer.vue:390`），keep 蓝纹悬停也显示「Delete range」——三态改造只改了颜色轴（`:166-184`），没改语义文案。
- **期望**：title 随 action/status 输出中文（「保留范围 12.0s-15.0s（待确认）」），顺带把候选 #4 的多语言问题一并收口。
- **严重度**：低（但语义错误比纯语言问题更值得修）。

### F-B-10 重复提交在 undo 栈留空步

- **场景**：同 F-B-01 触发条件；因 F-B-01 修复后仍可能存在（若只修对象替换不修快照时序）。
- **痛点**：`pushSnapshot` 先于桥调用且无去重（`WorkspacePage.vue:992` + `useUndoRedo.ts:48-58`），duplicate 零写入时 undo 栈多一条无效果快照，Ctrl+Z 出现「按了没反应」的假死感。
- **期望**：确认结果为 duplicate/失败时回滚该次快照，或 pushSnapshot 延迟到确认写入成功后。
- **严重度**：低（与 F-B-01 同源，修复时应一并处理）。

---

## 三、新功能诉求

### R-B-01 时间码支持 mm:ss 输入与播放头快捷填入

- **诉求**：popover 起止输入框接受 `mm:ss.s` / `h:mm:ss.s`；各加一枚「取当前播放头」按钮。
- **理由**：口播精修的时间语汇是分:秒；「从播放头到下一个停顿」是最高频的建范围动作，现在要靠肉眼从波形读秒数。
- **愿意接受的复杂度**：低。纯前端解析 + 一次桥调用拿播放头，不动模型。

### R-B-02 手动范围自由备注

- **诉求**：给手动范围加一句备注（如「广告段，但后面 3 秒例子别删」），在建议面板条目与覆层 hover 显示。
- **理由**：我建 keep/delete 的当下永远知道为什么，三天后回来精修时只剩「保留 4.2s」这种没有语义的标签；2.x 我用占位块 + 备注习惯已验证这个需求真实存在。理解 3.0.4 受字段冻结红线限制（PRD §0.2 MVP 约束：EditDecision 无备注字段，加字段违红线；record §7 维持池同类裁决），若 3.1.x schema 演进重启，这是我第一顺位想要的字段；短期可评估 detail JSON 承载（纠错轨归属已有先例，PRD §1.1）。
- **愿意接受的复杂度**：中。接受走 schema 演进专门流程，或先做 detail JSON 过渡方案。

### R-B-03 手动范围操作的结果反馈规范化（成功/幂等/clamp 三态 toast）

- **诉求**：建范围成功、命中已存在（幂等）、区间被 clamp 三种结果都有明确轻提示。
- **理由**：现在成功靠观察、幂等是炸点（F-B-01）、clamp 静默；三个态都是我实际会踩的。
- **愿意接受的复杂度**：低。toast 文案层 + handleRangeDecision 分支处理。

### R-B-04 波形覆层状态可视化分级（pending/rejected 弱化、hover 中文状态行）

- **诉求**：覆层按 action × status 给出可扫描的分级视觉（pending 半透明已做，rejected 进一步弱化或隐藏），hover 显示中文「来源 + 状态」。
- **理由**：波形覆层是我判断「导出会剪什么」的第一依据，语义噪声（F-B-04/F-B-09）会直接动摇信任。
- **愿意接受的复杂度**：低。SegmentBlocksLayer 内聚改动。

---

## 四、3.0.5 候选清单逐条评价（老周视角：有感 / 无感 + 一句话理由）

| # | 候选项 | 评价 | 理由（从我的旅程出发） |
|---|---|---|---|
| 1 | 纠错管线取消延迟修复 | **有感** | smoke-fix-1 只修了翻译侧 1c，我纠错大工程点取消同样要等当前批跑完——同一份「点了取消却还在转」的焦躁，不应双标。（record §8.1；smokefix-1 表 1c） |
| 2 | accept_high_confidence / clear_subtitle_corrections 的 track 作用域化 | **有感** | 待审集已按轨隔离（R2.2），但「一键接受高置信度」还是 timeline 级——副轨视图下点一键会跨轨动主轨待审集，语义不一致迟早咬人；我逐条审阅为主，但这颗雷在批量场景。 |
| 3 | SuggestionPanel provide/inject 键类型化 | **无感** | 纯代码质量项，用户不可见；支持做，但不应占用 3.0.5 用户可感预算的优先级。（P3-7 选型登记） |
| 4 | Timeline 编辑按钮英文 tooltip 未随轨视图 | **有感（低成本高确定性）** | 我每天从列表「编辑」按钮进出全列编辑（J8），hover 出英文很出戏；按钮文案都轨感知了（Timeline.vue:370-376），就差这一行。 |
| 5 | aligned_main_text 字段的系统 prompt 语义说明 | **有感（副轨纠错质量向）** | 我用译文轨纠错就是指望模型对着主轨原文校译文（R2.5 的价值）；字段已注入但 prompt 不解释语义，模型用不用、怎么用全靠猜——这决定我敢不敢直接采信副轨纠错结果。 |
| 6 | 悬空 pending 纠错仅 get 过滤、不物理清理 | **无感（倾向不急）** | 我删了轨后 get 列表不出现幽灵条目就行（P2-3 已过滤）；物理清理是存储卫生，不是体验问题，观察即可。 |
| 7 | useRowLayout perf 环境例根修 | **无感** | 测试基建；但每版 record 都要写一句「唯一失败=环境例」，维护心智有成本，顺手修掉也行，别立项占主题。 |
| 8 | T4b 测试缺口（detect_silence 本体/端到端串测/padding=0 交叠/basic 空白点击建重叠段） | **无感但支持补** | 我不读测试；其中「basic 空白点击建重叠段」兜的是我的数据安全（J9 相关），若排期允许优先补这条。 |
| 9 | T1 方案 B 波形侧编辑模式一致性收口（含 trim 冻结语义裁决） | **有感（候选里我最想要的体验项）** | 列表能全列扫掠、波形侧 trim/菜单规则另一套（J3/J8 双轨心智），我两边来回切，规则割裂每天撞；但 trim 冻结语义必须先裁决清楚——我在编辑态下修剪被冻结/放行的预期要明确，别做成「有时能拖有时不能」。 |
| 10 | 2.x 重叠段解交叠载入迁移 | **无感** | 我的工程都是 3.x 建的；观察项定位合理（触发=真实旧工程受阻塞反馈），维持。 |
| 11 | 副轨删除确认策略（当前无确认框 + undo 兜底） | **有感（倾向维持无框 + 加删除 toast）** | 译文轨级联删除（主轨删段带删译文）+ 无确认，误删一串时 undo 兜底虽在，但栈里是多条「编辑决策」快照，找回心智成本高；维持无弹框，建议删除动作 toast 附「已删除 N 段，可撤销」，零打断而可感知。 |
| 12 | 手动范围自由备注 | **有感（3.0.5 最值得规划的长线项）** | 见 R-B-02；「保留 4.2s」没有语义的条目列表是我精修时最大的记忆负担，受字段冻结限制可先走 detail JSON 或列入 3.1.x schema 演进首发。 |

---

## 五、用户故事草稿

### US-B-01 手动范围幂等防呆
作为老周，我想要重复创建同一范围时得到「已存在」的明确反馈且工程状态不受影响，以便放心地反复框选微调而不怕弄坏工程。
**验收要点**：①duplicate 返回不再进入 project-updated（工程对象不变）；②轻提示「该范围已存在，已复用原条目」；③duplicate 路径不产生 undo 快照（无空步）；④新增 duplicate 态前端测试（`WorkspacePage.rangeDecision` 宿主补第三例）。

### US-B-02 keep 闭环可感知
作为老周，我想要确认 keep、重跑裁剪、红蓝并存这三个环节都有应用内的结果反馈，以便确信「确认 = 参与裁剪计算」而不是误当成导出动作。
**验收要点**：①确认 keep 时按钮旁或 toast 直显「参与裁剪计算、非导出」文案（不再仅 hover title）；②重跑完成 toast 汇报 invalidated_count 与 new_edits；③红蓝重叠区间在覆层 hover / 导出确认页标明「按删除处理」。

### US-B-03 手动范围三态语义诚实
作为老周，我想要被忽略的范围从波形上退场、待确认的范围有降档视觉、覆层悬停显示中文状态，以便波形所⻅即导出所得。
**验收要点**：①rejected range 覆层隐藏或极淡描边；②pending 保持 50% 透明（现状）；③覆层 title 按 action/status 中文化（删除/保留 × 待确认/已确认/已忽略）；④confirmed delete 红纹保持逐字节不变（golden 锁不破）。

### US-B-04 口播时间码输入
作为老周，我想要用 mm:ss 输入起止并一键取当前播放头，以便不换算、不读波形就能精确建范围。
**验收要点**：①支持 `mm:ss.s` 解析且兼容纯秒；②起/止旁「取播放头」按钮；③clamp 发生时回显调整后的值；④添加成功有 toast。

### US-B-05 波形/列表编辑模式一致性（对应候选 #9）
作为老周，我想要波形侧修剪与菜单行为和列表侧编辑模式同一套规则，以便不用记住「哪边要退编辑模式、哪边不用」。
**验收要点**：①trim 冻结语义先裁决并在 toggle title 与文档写明（编辑态下主/副轨块修剪的允许矩阵）；②lane 菜单结构操作纳入编辑模式守卫（与列表侧对齐）；③主轨既有手势零回退（对照 3.0.3 手势矩阵断言）。

---

## 六、Top3 优先级及理由

1. **F-B-01（含 F-B-10）：duplicate 幂等返回毁工程对象** —— 唯一的数据安全级问题，且触发场景（重复框选、双击、时间码重复提交）正是 ±0.05s 幂等设计想保护的日常操作；修复面小（前端 handleRangeDecision 分支 + 可选后端补 revision），性价比极高。3.0.5 无论如何应带上的修复。
2. **US-B-02 + F-B-02/F-B-03：keep 闭环的可感知收口**（确认文案直显 + invalidated_count toast + 红蓝并存语义提示）—— keep 是 2.x「占位块」习惯的正式接班人（我这类用户升级的最大动机），功能链已全通（已求证 project_service.py:2888-2935），差的只是「让用户敢信」的最后一层反馈；不改数据层，纯文案与 toast 面。
3. **候选 #9（T1 方案 B）波形侧编辑模式一致性收口** —— 列表扫掠 3.0.4 已通（J8 顺），波形侧规则不同造成的双轨心智是每日摩擦；前提是先把 trim 冻结语义裁决写死（我宁愿规则严但明确，也不要「有时能拖有时不能」）。顺带把候选 #4（英文 tooltip）与 F-B-09（覆层英文 title）两处一行级文案收口。

---

*依据文件清单：docs/3.0.4/record-3.0.4.md（§0/§3/§7/§8）、docs/3.0.4/PRD-v3.0.4.md（§4/§5/§6）、record-3.0.4-P4-smokefix-1.md、record-3.0.4-P4-smokefix-2.md、README_zh.md；代码：frontend/src/components/waveform/WaveformEditor.vue、frontend/src/components/waveform/SegmentBlocksLayer.vue、frontend/src/components/workspace/SuggestionPanel.vue、frontend/src/components/workspace/Timeline.vue、frontend/src/pages/WorkspacePage.vue、frontend/src/composables/useEdit.ts、useAnalysis.ts、useUndoRedo.ts、useSegmentEdit.ts、useTrackEdit.ts、frontend/src/utils/projectPatch.ts、frontend/src/utils/revision.ts、frontend/src/types/project.ts、frontend/src/App.vue、core/project_service.py、core/export_service.py、tests/test_add_range_decision.py。*

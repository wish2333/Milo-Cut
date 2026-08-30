# Milo-Cut 优化报告 v2：本质需求与实际缺陷深查（对照 MAW）

> 前置报告：[MAW-竞品分析与优化报告.md](./MAW-竞品分析与优化报告.md)（v1，竞品侧全景，保留不动）。
> v2 方法：三个并行深查分别逐行阅读我方 LLM 链路（llm_service.py 1303 行 / workflow_engine.py 936 行 / 前端 AI 面板）、前端性能与风格（WorkspacePage.vue 2386 行 / SettingsModal.vue / 波形五组件 / bridge 双端）、字幕管线与多轨（models / subtitle_service / asr_scripts / project_service.py 2320 行），并对照 MAW 对应实现；所有关键负面结论均经本人二次源码验证（含一次对子代理误判的反证与再纠正）。

---

## 〇、总裁决：我们的本质需求与真实差距

**本质需求**（Milo-Cut 立品之本，不可动摇）：把 1 小时口播粗录变成 40 分钟干净可剪素材——删除决策的质量与效率、出片能力、本地优先。

**v2 最重要的修正**（相对 v1 的认知）：

1. **词级时间戳我们不是"缺"，而是"有并被扔掉"**。`Segment.words`（models.py:64-78）早已存在，whisper/qwen/mlx 三条 ASR 链路全部产出词级数据并一度落库，但 `main.py:648-653` 在落库后**导出 SRT 再 `import_srt` 回灌**，把 words/speaker 全部洗掉、id 退化为顺序号。这不是能力缺口，是一行删除即可修复的链路 bug。**v1 报告中"P0 补词级 items"的判断需要修正为"P0 修复回灌 + 接线消费"**——我们离竞品的差距比 v1 估计的小得多。
2. **LLM 链路整体成熟度优于竞品**，不是短板。结构化契约、target_ids 白名单防幻觉、4 层降级 JSON 解析、批处理+并发+429 降级、3 次重试+可取消、`_assert_timestamps_unchanged` 断言保证时间轴结构上不可能被 LLM 破坏、可配置工作流+跨会话快照+心跳看门狗——这些 MAW 都没有或更弱。真正的差距收敛为两点：**漏批静默丢弃**与**工作流中途失败无回滚**。
3. **真正的深坑在前端与持久化架构**：tick 轮询逐事件 evaluate_js、全量 Project JSON 快照撤销、无虚拟滚动的字幕列表、两个 90KB+ 巨型组件、无 fsync/备份/schema 校验的工程文件。这些是长期累积的结构债，不是功能缺失。

---

## 一、多层字幕（用户重点关注 ①）

### 现状裁决

- **多轨字幕完全缺失**。`TranscriptData` 单轨扁平；`Timeline` 的"多份"是 fork 副本（LLM 试验用），不是同媒体并行轨道。`SubtitleOverlay`/波形均为单轨渲染。
- **需求判断**：双语/同传视频是我们的合理扩展场景，但**不是本质需求**，定位为 P2。v1 报告"不建议跟进多轨"的结论在产品层面维持，但在架构层面应**预留数据结构**，避免将来迁移。

### 关键发现：副轨设计不应动 Timeline，应动 TranscriptData

竞品 `moy.asr.multi_subtitle.v1` 的精华不在 UI，而在数据模型：**主轨 segments 唯一真源，副轨放 `tracks[*].segments`，`bindings` 记录主副段一对一关系并保存 start/end_offset_ms**；绑定操作驱动联动编辑/成对拆分删除/跨轨吸附；`enabled` 只隐藏不删。

照搬到我们的正确映射（子代理已给出草案，经我复核与现有结构自洽）：

```
TranscriptData:
    engine, language, segments            # 主轨，全部现有逻辑不动
    tracks: list[SubtitleTrack] = []      # 新增
SubtitleTrack: id, role, name, language, segments: list[Segment]   # 复用 Segment（words 天然携带）
TrackBinding: id, track_id, main_segment_id, extension_segment_id, start_offset_ms, end_offset_ms
```

- `ProjectPatch` 增加 `tracks?`/`bindings?` 两个 layer——v2.3.2 的 layer 机制就是为这种扩展准备的，**零协议破坏**；
- 联动编辑挂 `update_segment`：有 binding 则按 offset 同步；`split_segment` 的 ED-rebind 逻辑（project_service L1300-1350）有现成范式可抄；
- `_enforce_segment_sort_invariant` 只管主轨，副轨自维护有序；
- 导出按 track 参数化，主副各出一份 SRT；时间轴裁剪需对副轨做同样的 keep-ranges 映射（否则剪掉区域副字幕残留——竞品也是靠"从去空隙时间线导出"回避的，我们要做得更对）；
- MVP 边界：副轨 SRT 导入 + 300ms 容差自动匹配 + 联动移动 + 双 SRT 导出。竞品不支持的一对多/主副交换我们也不做。

**顺手修复的两个编码缺陷**（同属字幕管线）：`parse_srt` 硬编码 `utf-8-sig`，GB18030 的 SRT 导入直接 UnicodeDecodeError——回退逻辑只写在 `validate_srt` 里，实际导入路径没有用上，属于文档宣称与实现的偏差。

---

## 二、性能优化方案（用户重点关注 ②）

### 架构层结论：最大的性能税在"进程边界"，不在渲染

**1. bridge 事件通道（S 级改造，收益最大）**
`pywebvue/bridge.py:_flush_events()` 对队列里**每个事件单独拼 JS 字符串 + 单独 evaluate_js**——每次都是跨 CPython↔WebView2 的 IPC 且在主线程执行（约 1-10ms/次）。事件风暴时一次 tick drain N 个事件 = N 次 IPC，反而阻塞 UI；50ms 固定 tick 还意味着 20 次/秒的空转 IPC 往返（阻止 WebView 空闲、笔记本耗电）。叠加前端 useTask 的 3s 兜底轮询，形成双通道。
**改法**：一次 evaluate_js 派发整个事件队列（单次 `dispatchEvents([...])`），tick 改自适应（空闲 250ms / 活跃 16ms）。这两条属于 pywebvue 层，改完全 app 受益，是全清单性价比之王。

**2. 全量 Project 引用替换的响应式震荡（M 级）**
`projectPatch.ts` 应用 patch 时对目标 timeline 整体重建（`segments: [...patch.segments]`），改一个字 → `mergedSegments`/`segmentStateMap`/`visibleBlocks` 全链重算 → **无虚拟滚动的全量字幕列表重渲染**。拖拽 segment 边缘时每 300ms debounce 发一次 `update_segment`，就是每 300ms 一次全 app 级震荡。改法：patch 应用细粒度化（按 segmentId 原位替换，保持数组其他元素引用稳定），配合虚拟滚动（见下）。

**3. 字幕列表虚拟滚动（M 级，最大单项可感知收益）**
`Timeline.vue` 直接 `v-for` 全量 TranscriptRow（参考项目 1167 段），每行带右键菜单/时间编辑/拖拽。千段项目滚动与任何 patch 应用都卡。`v-memo` 是不够的补丁。

**4. 波形渲染管线落后竞品一代（S→L 分级）**
现状：单 canvas、后端峰值 JSON 一次载入、`watch(viewStart)` 每 wheel 事件同步全量重绘、无 rAF 合帧、每次重绘都重设 `canvas.width=dpr`（清空位图+重新分配纹理，WebView2 上可感知）。竞品是 mipmap 多分辨率 + 多行脏区重绘 + 全交互 rAF 合帧 + hover seek 预览。
**分性价比落地**：rAF 合帧 + 仅尺寸变化时重设分辨率（S，先做）→ hover 预览把 mousemove 改为每帧处理（S）→ 脏区/可视裁剪（M）→ mipmap（L，可后置；且 v1 的"波形缓存 media_signature"仍应做，那是后端侧）。

**5. 撤销系统是定时炸弹（M→L）**
`useUndoRedo` 用 `JSON.stringify(project)` 整包入栈（50 条，>2MB 降 10 条）：每次操作 O(项目大小) 序列化、undo 时主线程 parse 卡 10-50ms、内存 50×快照；更隐蔽的是**快照回退可能把后端 revision 一起回退**，与 v2.3.2 patch 体系打架产生 stale 风险。
**改法**：对齐竞品 typed record 模式，快照改 `{layer, before, after}`——layer 直接复用 ProjectPatch 已有分层；undo 走 `applyProjectPatch` 逆应用，revision 继续递增。两步走：先层级快照（M），后段级 diff（L）。

**6. PyWebView 内核专项**：progress 事件禁止携带大 payload；新组件的 bridge 调用必须过 `waitForPyWebView` 门（WebKit ready 前静默丢调用）；跨屏拖动时 WKWebView 的 devicePixelRatio 变化不触发 ResizeObserver；wheel deltaMode 需归一（mac 触控板过冲）。

### 播放头架构建议
`PlayheadOverlay` 用 Vue 响应式驱动 currentTime，播放中每帧触发组件 patch。应改为独立 rAF + transform 的命令式层（竞品同款），Vue 只管暂停态。

---

## 三、LLM 处理逻辑（用户重点关注 ③）

### 先说我们做得好的（v1 低估了）

| 能力 | Milo-Cut | MAW |
|---|---|---|
| 输出契约 | 结构化 JSON + target_ids 白名单防幻觉 + 字段归一化 | cue ID 分组协议 |
| 解析健壮性 | 4 层降级 JSON 解析 | JSON 清洗 |
| 批处理 | 20/30 条/批 + overlap 上下文 + 并发 5 + 429 串行降级 | 40 条/批并发 |
| 时间轴安全 | 解析器不读时间字段 + `_assert_timestamps_unchanged` 断言 | 本地重对账（更强，但我们量级下暂不需要） |
| 工作流 | 声明式编排 + 跨会话快照 + 心跳看门狗 + 失败交互 | 固定步骤序管线 |
| 可观测 | token 用量可观测 | 无 |

结论：**WorkflowEngine 比 MAW 固定管线更可维护，不要推倒**。v1 报告建议的"source_id + 消毒协议"要重新定性：其中**响应消毒（剥离推理文本）与 SSRF 校验仍值得抄**（S 级），但 span 重对账在我们"解析器根本不碰时间字段"的设计下**当前量级不必补**——那是 MAW 为"LLM 重分段/翻译"这类改结构任务付的成本，我们没有该任务。

### 真实缺陷（按严重度）

1. **漏批静默丢弃（最严重）**：批失败后无重试、无 skipped 报告，用户看到"分析完成"但实际丢了若干段，且无任何痕迹。改法：批账本（成功/失败/跳过计数）+ 失败批自动重试一次 + UI 展示 skipped 报告。S-M 级。
2. **无批字符上限**：有截断风险（竞品 4000 字符/批）。S 级。
3. **温度 0.3 偏高**（llm_service.py:71）：纠错/删除判定任务竞品用 0.1、语义搜索用 0。S 级配置改动。
4. **ID 用真实工程主键且发送 start/end 给模型**：信息泄露面大且无必要，换临时不透明 ID、不发时间。S 级。
5. **smart_delete 与 subtitle_correction 各有一套批处理，~200 行重复**：抽共享批处理执行器。M 级。
6. **v2.2.0 非沙箱化遗留**：工作流步骤直接落库、中途失败无回滚；~200 行弃用死代码。改法：每步 undo 快照实现失败回滚（与第二节撤销改造共享基建）；删死代码。M 级。
7. 提示词工程（占位符注入/三级覆盖/预设）真实生效，属健康资产；补 override 试运行校验与 Layer4 正则-prompt 一致性测试即可。

---

## 四、前端风格优化方案（用户重点关注 ④）

### 现状裁决：设计语言好，工程化纪律差

design-spec（摄影第一/磁贴/单一 Action Blue）与 2.4.0 标准（token 表/WCAG AA）底子不差，v2.4.0 刚完成 token 统一。**与竞品 DESIGN.md 的差距不在审美，在"把坑固化成规则"的工程纪律**：

1. **无 z-index 层级契约**。竞品把"popover 被 stacking context 吞掉"写成 4 条强制规则（同坑连发三次后固化）；我们正处于前夜：SegmentBlocksLayer 裸写 `z-[9999]`、WorkspacePage 三个 popover `z-20`、跨组件靠 `closeallcontextmenus` 全局广播互相关闭——典型"靠巧合维持层级"。
2. **token 双轨**：style.css 有 `@theme` token，但组件遍布 `text-gray-400`/`bg-amber-50` 原始类，波形 canvas 硬编码 `#94a3b8`，深色磁贴工具栏下挂白底 popover（违反自家磁贴语言）；spec 禁字重 500/规定胶囊按钮，模板未执行。
3. **无对比度/可读性验证清单**：AA 要求写了但没有落地检查，竞品直接给最小字号与对比度数值约束。

### 方案（工程化，不重画）

1. style.css 增 5 档层级 token（base/raised/dropdown/modal/toast）+ lint/grep 清单禁业务组件裸 z-index、`gray-*`、硬编码 hex（S）；
2. popover 统一 `Teleport to body` + 层级 token，删除 contextmenu 广播（M）；
3. SegmentBlocksLayer 红绿状态色、波形静音覆盖色改引 status token，保证波形区与字幕区语义色一致（S）;
4. 写我们自己的 DESIGN.md 第二节：层级契约（含"上翻 popover 必须双测"）+ 可读性约束，把已知坑规则化（S）；
5. 巨型组件拆分与风格治理同批做：SettingsModal 按 5 个 tab 一比一拆（S-M，体积 -70%，tab 间几乎无共享状态、风险低）；WorkspacePage 先抽 3 个内联 popover + `useAsrEngines`（与 SettingsModal 的 ASR 域重复 ~250 行），再抽 `useWorkspaceActions` 归口 20+ 个 emit 中转 handler，最后（全量回归前提下）store 化（L）。

---

## 五、持久化与数据安全（深查新发现的架构债）

`project_service.py` 96KB/2320 行/60+ 方法是**四个领域**塞出来的：LLM 纠错工作流（~900 行，可拆 `correction_service.py`，与 `_current` 耦合最弱、最先拆）、v1→v2 迁移链（~350 行，拆 `migrations.py`）、segment 几何编辑、持久化。

持久化热路径的真实问题：写操作只改内存 + 前端 2s 防抖全量 `model_dump_json`；`tmp + os.replace` 原子替换但**无 fsync**（断电可能半截数据）；**无 .bak 轮换**（竞品每次覆盖保存留一份）；**无 schema 校验**（损坏 JSON 直接打不开，无恢复路径）。
改法（S 级，一天内可完成）：save 时轮换 1-2 份 .bak + replace 前 fsync + `model_validate` 失败自动尝试 bak + 补 `PROJECT_SCHEMA.md`。另：**split_segment 按字符比例切文本却把完整 words 复制进两段、merge 只留第一段 words**——与回灌修复同批接线 words 时一并改掉（约 30 行）。

---

## 六、总路线图（合并 v1/v2 结论，按性价比排序）

### 第一批：修 bug 级缺陷（合计约一周量级，收益立竿见影）
1. 删除 main.py:648-653 的 SRT 回灌，words 落库保住（S）
2. split/merge 正确处理 words（S）
3. parse_srt 编码回退（S）
4. 持久化：fsync + .bak 轮换 + bak 恢复（S）
5. LLM：批字符上限 + 温度 0.1 + 响应消毒 + SSRF 校验（S）

### 第二批：性能体验跃迁（覆盖 80% 可感知问题）
6. bridge 事件批量投递 + 自适应 tick（S，全局受益）
7. 波形 rAF 合帧 + canvas 分辨率仅按需重设（S）
8. Timeline 虚拟滚动（M，最大单项）
9. undo/redo 层级快照（复用 ProjectPatch layer，修复 revision 回退隐患）（M）
10. LLM 漏批账本 + 重试 + skipped 报告（M）

### 第三批：结构还债
11. SettingsModal 拆 5 tab；WorkspacePage 抽 popover/useAsrEngines/useWorkspaceActions（S→M）
12. patch 应用细粒度化（M）
13. 层级 token + popover Teleport + 风格 lint + DESIGN 层级契约（M）
14. project_service 拆 correction_service / migrations（M）

### 第四批：能力扩展（先立数据结构，UI 按需上）
15. words 全链路消费：精确拆分边界、LLM 纠错回贴、hover 卡拉OK 高亮（M）
16. 多轨字幕：TranscriptData.tracks/bindings + ProjectPatch 双 layer，MVP=副轨导入+300ms 匹配+联动+双 SRT 导出（后端 300-500 行，前端另计）
17. 波形 mipmap/hover 预览/脏区（L）；undo 段级 diff（L）；store 化（L）
18. （沿承 v1）波形 media_signature 缓存、托管 ASR runtime、文稿对齐——维持 P1 排期

### 维持不做的（v1 结论复核后仍然成立）
多云 ASR 聚合、翻译管线、OCR 去重、mosp 格式、integer 毫秒迁移（float 秒+round3 足够）、一对多绑定。

---

## 七、一句话结论

v1 我们看到的是"竞品有什么我们没有"；v2 逐行深查后真相是：**词级数据、LLM 成熟度、工作流编排这些核心资产我们已经有甚至更好，真正在漏水的是三处架构层——进程边界的事件通道、全量快照的状态管理、无保护的持久化**。第一批"一周量级"的 bug 修复就能把 ASR 数据质量拉到与竞品同级；第二、三批的结构还债决定这个项目一年后还能不能快速迭代。

# record-3.0.4-P3-8：覆层三态（M4-3 后半，R4.3b）

> 日期：2026-09-06　分支：`dev-3.0.4-p3-8`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-8　SPEC：M4-3 表第 2 行（SegmentBlocksLayer.vue 覆层 action/status 感知）+ 第 3 行（deleteRanges 裁决：零改动 + 快照锁定用例）　PRD：R4.3b
> 前置：P3-5（`add_range_decision`，pending 手动范围可产出）、P3-6（建范围入口）、P3-7（建议面板手动分组 + keep 条目在场）。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 改动 | +38/-3 | ① `visibleEditRanges` computed 输出增 `action` / `status` 字段（`EditRangeBlock` 接口同步，:98-108/:151-160）；② 新增 `editRangeClasses` / `editRangeHatchStyle` 两纯函数（:163-186）实现三态（§2 排布）；③ 模板覆层 div 静态 class 改 `:class` 绑定、内层斜纹 div 静态 style 改 `:style` 绑定（:377-393）——confirmed delete 渲染结果逐字节不变（§3） |
| `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` | 改动（纯追加） | +104/-0 | 三态样式 6 例追加于新 describe 块「edit range overlay three-state (M4-3 / P3-8)」（§4），既有断言零删改 |
| `frontend/src/pages/WorkspacePage.deleteRanges.test.ts` | **本步新建宿主** | +314/-0（新文件） | `deleteRanges` 快照锁定 1 例（§4.2）：pending manual range（delete 与 keep 两种）不入、confirmed manual + subtitle_trim source bypass 在场——跳播/进度条红罩/导出预览三消费端共用的 computed 输出被锁定 |
| `docs/3.0.4/record-3.0.4-P3-8.md`（本文）、`record-3.0.4.md` §1、`plan-v3.0.4.md` P3-8 | 文档 | — | 登记与勾销 |

其余全部零改动：**WorkspacePage.vue 产品代码零触碰**（deleteRanges 过滤逻辑与 v3.0.3 逐字节一致，快照用例放新建测试宿主）、后端全部零改动、SuggestionPanel / WaveformEditor / WaveformRow / Timeline / useWorkspaceActions / 导出链零改动（git diff 文件集 = 上表，红线逐一核对）。

## 2. 三态排布终版（登记裁决）

**双轴正交：color 轴 = action，opacity 轴 = status。**

| action \ status | pending | confirmed | rejected |
|---|---|---|---|
| delete | 红斜纹 + `opacity-50` 降档 | **红斜纹全不透明（= v3.0.3 逐字节）** | 红斜纹全不透明（= 现状，见 §2.3） |
| keep | **蓝斜纹 + `opacity-50` 降档** | 蓝斜纹全不透明 | 蓝斜纹全不透明 |

1. **SPEC 字面冲突的解读（任务书预留的定夺点）**：SPEC M4-3 表第 2 行同时写「pending = 同款半透明（opacity 降档）」与「keep（任意 status）= 蓝色系斜纹/描边（不用红）」——pending keep 落在两条交集处无唯一解。任务书给定解读基线「pending 优先（半透明降档），非 pending keep = 蓝色系」，并允许「pending keep 用半透明蓝」的更贴切排布。**本步取后者（pending keep = 半透明蓝）**，理由：P3-7 面板里 pending keep 与 pending delete 并存（气泡/时间码二选一都产 pending），若 pending 抹平为一套无色差样式，波形上无法区分「待删」与「待留」——覆层存在的目的（PRD R4.3b 可视化裁决辅助）落空。双轴正交后：颜色答「删还是留」，透明度答「定了没」，两问独立可答。
2. **降档实现 = Tailwind `opacity-50` 类**（外层覆层 div 整体降档，斜纹/边框/底色同步半透明），SPEC「同款半透明（opacity 降档）」字面达成；不用单独调低 bg/border 透明度 token（两处改动的信息量低于一个 opacity 类，且 confirmed 档零沾染）。
3. **rejected 维持现状零改动**：现状 `visibleEditRanges` 过滤 = `target_type === "range"` + 视窗相交，**不含 status 过滤**——rejected range 一直渲染（红斜纹）。本步不扩大语义（不加 rejected 过滤）：rejected delete 沿用全不透明红斜纹（与 confirmed delete 同视觉，现状即如此）；rejected keep 按颜色轴落蓝系（本步新增态，历史上无 keep range 生产者，无既有视觉可破坏）。已补第 6 例锁定「rejected 仍渲染、不被过滤」。
4. **subtitle_trim 生成区间**：source 过滤天然隔离（面板分组按 `source === "manual"`），覆层侧 subtitle_trim delete（创建即 confirmed）落「confirmed delete」格 = 现状红斜纹逐字节——M4-3 边界「subtitle_trim 区间展示维持原样」达成。
5. **title tooltip 不动**：`:title` 沿用 `Delete range: …`（含 keep range 在内）——任务书改动面仅「computed 增字段 + 模板三态类」，title 不在三态类内；keep 条目的语义区分由颜色轴承担。真机观感归 P4 冒烟（可后续连同 rejected 是否过滤一起裁决）。

## 3. confirmed delete 逐字节一致性（实现机制）

- 改造前：静态 `class="absolute top-0 bottom-0 border border-red-400/60 bg-red-300/30 pointer-events-none"` + 静态 `style="background-image: repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(239,68,68,0.15) 3px, rgba(239,68,68,0.15) 6px)"`。
- 改造后：`:class="editRangeClasses(rangeBlock)"` 在 confirmed delete 分支返回**同一 token 序列** `absolute top-0 bottom-0 border border-red-400/60 bg-red-300/30 pointer-events-none`（无 opacity-50）；`:style="editRangeHatchStyle(rangeBlock)"` 生成**同一渐变串**（红 hatch `rgba(239,68,68,0.15)`，45deg/3px/6px 参数逐字面保留）。真实浏览器渲染结果逐字节一致；快照式断言见 §4 例 1（FULL class string 全等比对）。
- **jsdom 限制登记**：jsdom 的 CSSOM（cssstyle）对 `repeating-linear-gradient` 值直接丢弃（`el.style.backgroundImage = grad` / `style.cssText` 双路径实测均静默 no-op，仅裸 `setAttribute` 可存留而 Vue `:style` 不走该路径）——故斜纹渐变色**在 jsdom 内不可经 DOM 断言**（v3.0.3 静态 style 同样被丢，改造前后 jsdom 行为等价，真实浏览器不受影响）。测试侧以「外层 class token 完整编码双轴（action→色系、status→opacity）+ 斜纹载体 div 在场」为断言面，与本仓既有样式断言惯例（bg-red-200/bg-green-200 等 class 断言）一致。

## 4. 测试（+7 例：6 追加 + 1 新宿主）

vitest **827 collected（820 → 827，+7）/ 826 passed**（唯一失败 = `useRowLayout.perf.test.ts` 环境例，见 §5）。

### 4.1 三态样式（SegmentBlocksLayer.test.ts 追加 6 例，宿主既有 metrics injection harness 复用）

| # | 用例 | 断言要点 |
|---|---|---|
| 1 | confirmed delete = v3.0.3 红斜纹逐字节 | `classes().join(" ")` **全等** 快照串 `absolute top-0 bottom-0 border border-red-400/60 bg-red-300/30 pointer-events-none`；无 `opacity-50`；斜纹载体 `div.h-full` 在场 |
| 2 | pending delete = 红斜纹降档 | `border-red-400/60` + `bg-red-300/30` + `opacity-50` 在场，class 串无 blue |
| 3 | pending keep = 蓝斜纹降档（§2.1 裁决的锁定） | `border-blue-400/60` + `bg-blue-300/30` + `opacity-50`，class 串无 red；斜纹载体在场 |
| 4 | keep confirmed = 全不透明蓝系 | 蓝系两 token 在场、无 `opacity-50`、class 串无 red |
| 5 | rejected 仍渲染不过滤（§2.3 锁定） | rejected delete range 覆层在场且 class 全等 v3.0.3 快照串（= confirmed delete 同视觉，现状延续） |
| 6 | 无 range 数据零渲染（现状回归） | 空 edits 与仅 segment-target edit 两种输入 → `[title^="Delete range"]` 零命中（segment 决策只走 block 样式，永不产覆层） |

### 4.2 deleteRanges 快照锁定（新建宿主 WorkspacePage.deleteRanges.test.ts，1 例）

harness 镜像 WorkspacePage.rangeDecision.test.ts（P3-6 宿主：bridge/composable 全 mock + vi.resetModules 动态导入）；**观测点 = VideoControls stub 的 `deleteRanges` prop**（WorkspacePage.vue:1497——三消费端 useEditedPlayback 跳播 `rawDeleteRanges` / 进度条红罩 / 导出预览 DemoPreviewSurface 同吃 `deleteRanges` computed，锁 computed 输出即锁三端；VideoControls 为非 demo 模板中唯一常渲染的 `:delete-ranges` 绑定点）。

工程 fixture = 4 条 range edit 并存：pending manual delete（2-4s）/ pending manual keep（4.5-5.5s）/ confirmed manual delete（7-8.5s）/ **pending subtitle_trim**（1-1.5s，历史 source bypass）。断言输出**全等** `[{1,1.5}, {7,8.5}]`（按 start 排序）：pending manual 两种 action 均不入（跳播/红罩/导出预览不受 pending 影响），confirmed manual 与 subtitle_trim source bypass 在场——**过滤逻辑现状快照整锁定**（含 `confirmed OR subtitle_trim` 的 bypass 分支，比任务书下限多锁一格）。

## 5. 门禁（`bash scripts/gates-v3.0.4.sh` 三段全跑，exit 0）

- pytest：**819 passed，exit 0**（后端零改动，与 P3-5/P3-6/P3-7 持平）
- ruff：All checks passed（0 problems）
- vitest：**827 collected / 826 passed**（唯一失败 = `useRowLayout.perf.test.ts` 挂载墙钟 ~21ms vs 8ms 预算——record-3.0.3 §5 遗留 #5 已登记环境例；本机 base（dev-3.0.4 HEAD 3050134）单独复跑同败 ~20.8ms，与本步无关自证；820 → 827 = 本步 +7，≥822 达标）
- build：`vue-tsc --noEmit` exit 0 + `vite build` exit 0（回落命令块）
- lint：eslint 0 errors 0 warnings
- redline 段：全部通过（后端 diff 白名单 = 既有 8 文件零新增；R0-2 events 双侧零新事件；R0-3 前端断言零删改——本步全部纯追加；dev.py/build.py 零改动）

## 6. 偏离与边界登记

- **三态排布偏离 SPEC 字面（§2.1，任务书预留定夺）**：pending keep 取「半透明蓝」而非「pending 抹平为无色差降档」——颜色轴保 action 语义，pending 双例（#2 红 / #3 蓝）分别锁定。
- **rejected 不过滤**（§2.3）：现状本就不过滤 rejected，本步零改动不扩大语义，#6 例锁定渲染在场；rejected 与 confirmed 的视觉区分（要不要降档/过滤）留后续裁决。
- **title tooltip 沿用 `Delete range:` 前缀**（§2.5）：改动面红线仅限三态类，keep 条目 title 语义偏差登记在案，归 P4 冒烟观察项。
- **jsdom CSSOM 丢渐变值**（§3）：斜纹色不可 DOM 断言（改造前后等价、真实浏览器无影响），断言面落 class token + 载体在场，登记为测试侧裁量。
- **WorkspacePage.vue 零改动兑现**：快照用例在新测试宿主（测试文件不算产品代码），deleteRanges/导出链/静音与智能删除两既有分组断言零触碰。
- 覆层三态与 P3-9 keep 闭环的关系：本步只做**展示态**；keep 参与删除区间计算（`generate_subtitle_keep_ranges` 受控改点 ①）全部归 P3-9——若 Q10 砍项触发，P3-8 的 keep 蓝系样式随砍（SPEC M4-4 边界条款，砍法 = 移除 keep 色支 + #3/#4 两例，红/降档两轴不受影响）。

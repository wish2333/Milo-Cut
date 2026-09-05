# record-3.0.4-P3-6：范围标记 toggle 与确认气泡（M4-2，R4.2）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-6`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-6　SPEC：M4-2（toggle 裁决 + 手势矩阵 + 接线点 2 条 + 边界 + 验收）　PRD：R4.2（SPEC 附录 C #4/#5 改裁后口径）
> **执行接力注记**：前执行者完成产品代码后中断于实现后期；本步 = 验证其实现自洽性 + 补测试 + 登记 + 提交。**产品代码零修正**（vue-tsc / vitest 全量 / vite build / eslint 一次性全绿），三项实现选型核实自洽后照单登记（§2），未做任何推翻或改写。

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/waveform/WaveformEditor.vue` | 前执行者实现（本步仅验证） | +337/-8 | rangeMode toggle（默认 OFF，`data-test="range-mode-toggle"`）+ `handleRowEmptyGesture` range 路由（ctrl/shift 之后、else 之前）+ range marquee 双套预览 + 内嵌确认气泡（删除/保留/取消，删除聚焦）+ `confirmRange` emit `range-decision` + isMulti 双向清理 + unmount 清理 + `rangeSelection?: Ref` prop（§2.3） |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | 前执行者实现（本步仅验证） | +24/-1 | `emptyAreaMode` 联合类型增 `"range"` + `handleEmptyClick` 增 range 分支（"seek" 之前）emit `range-press`（payload 形态同 empty-press） |
| `frontend/src/pages/WorkspacePage.vue` | 前执行者实现（本步仅验证） | +27/-1 | 从 useSegmentEdit 解构 `selectedRange` + `rangeSelectionSink` 下传 `:range-selection`（§2.3）+ `handleRangeDecision`（pushSnapshot(["edits"],"手动范围") → `call("add_range_decision", …)` → 成功 emit project-updated patch / 失败 toast）+ `@range-decision` 接线 |
| `frontend/src/components/waveform/WaveformEditor.test.ts` | 本步补测（挂既有宿主） | +414/-0 | 10 例（multi 7 + basic 3，§4）；既有 48 例断言零删改 |
| `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` | 本步补测（挂既有宿主） | +37/-0 | 1 例（"range" 分支链，§4）；既有 19 例零删改 |
| `frontend/src/pages/WorkspacePage.rangeDecision.test.ts` | **本步新建宿主** | +302/-0（新文件） | 2 例（成功链 + 失败链，§4）；mock 脚手架照 WorkspacePage.trackEdit.test.ts（useSegmentEdit mock 增 `selectedRange` ref 一项） |
| `docs/3.0.4/record-3.0.4-P3-6.md`（本文）、`record-3.0.4.md` §1、`plan-v3.0.4.md` P3-6 | 文档 | — | 登记与勾销 |

其余全部零改动：TrackLane.vue / WaveformRow.vue / useSegmentEdit.ts / useWorkspaceActions.ts / 后端全部 / pywebvue / 其他前端文件（红线清单逐一核对，git diff 文件集 = 上表）。

## 2. 前执行者三项实现选型核验（照单登记，未推翻）

1. **multi 路径 empty-area-mode 用 `rangeMode ? 'seek' : buildMode ? 'add' : 'seek'`（非 SPEC 接线点 1 的字面 `'range'`）——「矩阵等价」适配**。核验自洽：multi 主轨链 = WaveformRow（P3-3 冻结）内部 SegmentBlocksLayer 仅在 `"seek"` 模式 emit `empty-press`（WaveformRow.vue:322 行内三元 `buildMode ? 'add' : (emptyAreaMode ?? 'seek')`），WaveformRow `handleEmptyPress` 冻结几何后仅转发 `empty-gesture`；若编辑器侧传 `"range"` 该链根本不触发。故 multi 的 range 路由按 SPEC 矩阵既定落点实现在 `handleRowEmptyGesture`（ctrl/shift 判断之后、else 之前），行层保持 seek 通道——与 SPEC 矩阵「multi plain ON → range marquee」格语义等价，仅接线值不同。**SPEC 字面嵌套三元 `'range'` 只用于 basic 直挂路径**（该处 SegmentBlocksLayer 为编辑器直接子级，无 WaveformRow 中转）。测试锚：wiring 用例断言行层 emptyAreaMode 双 toggle 同 ON = `"seek"` 且 WaveformRow `buildMode` 门控 false。
2. **`:build-mode="buildMode && !rangeMode"` 防「行内三元复活 add」**。核验自洽：WaveformRow 自身行内三元（`buildMode ? 'add' : …`）与 lane 建段都以 build-mode prop 为源，若不门控，双 toggle 同 ON 时行层将收到 `'add'`（范围手势被劫持为建段）。门控后双 ON = 行层 seek + buildMode false = 范围获胜。**落点两处**：multi WaveformRow（:1365 附近）与 basic extension TrackLane（:1555 附近）——后者为前执行者外延选型：双 toggle 同 ON 时 lane 建段同暂停（「范围标记仅主轨域」矩阵格的取值 = 建段全局暂停而非 lane 建段继续），与两处 toggle title 文案「与范围标记模式同开时以范围标记优先，建段暂停」全局一致。rangeMode OFF 时表达式退化为 `buildMode`，lane 建段（P3-3 X1）零回退（既有 lane 建段 3 例全绿自证）。
3. **selectedRange 激活方式 = WorkspacePage 解构 + sink 下传，useSegmentEdit.ts 零改动**。核验自洽：`<script setup>` 顶层 ref 在模板自动解包，直接 `:range-selection="editSelectedRange"` 会传值不传 ref；故以普通对象 `rangeSelectionSink = { ref: editSelectedRange }` 包一层（嵌套属性不自动解包），WaveformEditor 收到真 Ref 后 `stageRange` 原地写 `.value`（rowDrag 对象 prop 同款模式）——useSegmentEdit 的「只写不读死代码」ref（:85/:102-104）就此激活为气泡数据源，取消路径 `stageRange(null)` 同步清空。WaveformEditor 侧 prop 可选（`rangeSelection?`），standalone/demo 挂载回退 local ref 同语义（既有全部宿主 mock useSegmentEdit 不含 selectedRange → 传 undefined → 回退路径，既有测试零改动仍绿）。测试锚：WorkspacePage 用例断言 `props("rangeSelection")` 与 mock ref 同一（`toBe` 身份）；multi 取消用例断言注入 sink `sink.value` staged `{2,6}` → 取消后 `null`。

**实现细节注记（登记备查）**：① 退化守卫 `RANGE_MIN_SECONDS = 0.05`（无拖拽幅度 <0.05s 不开气泡，镜像 marquee w/h>2 no-op；阈值数字对齐后端 ±0.05 幂等 ε，纯取值巧合非耦合）；② `confirmRange` 对 start/end 各取两位小数四舍五入（`Math.round(t*100)/100`）；③ 气泡定位 = 框选终点 +6px 并按容器尺寸夹取（RANGE_BUBBLE_W=178/H=64 估算值）；④ isMulti watch 双向 `gestureCleanup?.() + closeRangeBubble()`（原仅 multi→basic 单向清理，现两方向都拆手势态 + 气泡）+ onUnmounted closeRangeBubble（staged selectedRange 不越界存活）；⑤ Q9 删除聚焦 = `openRangeBubble` 内 `await nextTick()` 后 `rangeDeleteBtnRef.value?.focus()`。

## 3. SPEC M4-2 手势矩阵逐格实现对照表

| 模式 | 手势 | 范围标记 OFF（= v3.0.3） | 范围标记 ON（实现） | 测试锚 |
|---|---|---|---|---|
| multi | plain press/drag | clear-selection + scrub（handleRowEmptyGesture else 分支） | `else if (rangeMode.value) startRangeGesture(g)`（ctrl/shift 之后、else 之前）→ rowDrag 冻结几何有界映射 → rangeDraft(multi) → 松手 openRangeBubble | 范围标记手势 #1（marquee left 20%/width 40% → bubble label 4.0s → 删除 → `{2,6,delete}`；无 set-time/clear-selection/add-segment 泄漏）；#2（保留 keep / 退化守卫）；#3（取消） |
| multi | Ctrl-drag | Ctrl-create 建段（钳邻居缝隙） | **不变**（ctrlKey 分支在前，优先级高于范围模式） | #4：add-segment `[[2,5]]` 与既有 M5-3 Ctrl 用例同参数逐字节一致；create-preview 在场、range-marquee/range-decision 不出现 |
| multi | Shift-drag | 段多选 marquee | **不变**（shiftKey 分支在前） | #5：select-segments `[["a","b"]]` 跨两行；无 range-decision |
| basic | plain click/drag | emptyAreaMode 由 buildMode 决定（OFF=seek 死 emit 无监听） | 嵌套三元 `rangeMode ? "range" : buildMode ? "add" : "seek"`（SPEC 字面）→ SegmentBlocksLayer `"range"` 分支 emit `range-press` → `handleBasicRangePress` 同层拖拽跟踪（单窗 metrics） | basic #2：真 SegmentBlocksLayer 链 → marquee 16.66%/33.33% → bubble 删除聚焦 → `{5,15,delete}`；无 add-segment/set-time/seek；SegmentBlocksLayer range mode 单测（payload 形态 + 双击静默） |
| basic | buildMode ON plain click | add 0.5s 段 | **范围获胜**（双 toggle 同 ON）：`"range"` 位于三元最前，add 分支不可达 | basic #3：层 props emptyAreaMode === "range"、无 add-segment、range-keep emit `{5,15,keep}` |
| 两模式 | lane/副轨区 | 不涉及 | 不涉及（multi 行内 lane 与 basic extension lane 均经 §2.2 buildMode 门控：双 ON 时 lane 建段暂停；rangeMode OFF 退化 `buildMode` 零回退） | 既有 lane 建段 3 例（M3-2 X1）全绿引用；wiring 用例（双 ON 门控断言） |

**OFF 零回退引用与补测**：multi plain（既有 M5-3「plain press scrubs」覆盖默认 OFF + 本步 #6 toggle 循环 ON→OFF 后 scrub 路径照旧）；multi Ctrl/Shift（既有 M5-3 两例 + 本步 #4/#5 对照）；basic seek（既有 SegmentBlocksLayer seek 模式 2 例 + 本步 basic #1 直挂层 OFF 无 range-marquee/bubble/range-decision/add-segment）；multi 建段 toggle（既有 smoke #4 两例）。

## 4. 测试（+13 例：WaveformEditor 10 + SegmentBlocksLayer 1 + WorkspacePage 新宿主 2）

vitest 814 collected（801 → 814，+13）／813 passed。手势合成 = mount + `dispatchEvent`/`trigger` mouse 事件序列（既有 WaveformEditor M5-3 手势惯例：makeMouse 强写 clientX/Y + 修饰键、document mousemove/mouseup、EmptyAreaLayerStub / 真 SegmentBlocksLayer 分路径）；锚 = `range-mode-toggle` / `range-marquee` / `range-bubble` / `range-delete` / `range-keep` / `range-cancel`（全 data-test）。

| # | 用例（宿主） | 断言要点 |
|---|---|---|
| 1 | multi ON plain press-drag（WaveformEditor） | 拖拽中 range-marquee（row 局部映射 left 20%/width 40%）+ 无 scrub/建段/清选泄漏；松手 marquee 消亡 + range-bubble 出现（label 含 4.0s）+ **activeElement = range-delete（Q9 删除聚焦）**；点 range-delete → `range-decision` `[[{start:2,end:6,action:"delete"}]]` + 气泡消亡 |
| 2 | multi ON keep + 退化守卫（WaveformEditor） | range-keep → `action:"keep"`；无拖拽幅度（0.033s < 0.05）不开气泡零 emit |
| 3 | multi ON 取消（WaveformEditor） | 注入 `rangeSelection` sink ref：松手后 `sink.value = {2,6}`（staged）；range-cancel → 无 range-decision + `sink.value = null` + 气泡消亡 |
| 4 | multi ON + Ctrl-drag（WaveformEditor） | add-segment `[[2,5]]`（与既有 Ctrl-create 用例同参逐字节一致）+ create-preview 在场；range-marquee/range-bubble/range-decision 全不出现 |
| 5 | multi ON + Shift-drag（WaveformEditor） | select-segments `[["a","b"]]`（跨行段多选照旧）；无 range-decision |
| 6 | multi OFF toggle 循环（WaveformEditor） | ON→OFF 后 plain press → set-time `[[6],[8]]` + clear-selection ×1（v3.0.3 scrub 路径）；toggle 文案「范围标记」↔「标记中」；全程无 range-marquee/range-bubble/range-decision |
| 7 | multi wiring（WaveformEditor） | 行层 emptyAreaMode：默认 seek → build ON=add → **双 ON=seek（§2.1 矩阵等价适配）**；WaveformRow buildMode：build ON=true → **双 ON=false（§2.2 门控）**；range OFF 后恢复 add/true |
| 8 | basic OFF（WaveformEditor，真 SegmentBlocksLayer） | 层 props emptyAreaMode="seek"；空白 press 无 range-marquee/bubble/range-decision/add-segment（OFF 零回退） |
| 9 | basic ON（WaveformEditor，真 SegmentBlocksLayer） | 层 props="range"；press-drag → marquee（view-% 坐标 16.66%/33.33%）→ bubble（activeElement = range-delete）→ 删除 → `range-decision` `[[{start:5,end:15,action:"delete"}]]`；无 add-segment/set-time/seek |
| 10 | basic ON + buildMode ON（WaveformEditor） | 双 toggle 同 ON：范围获胜——层 props="range"、无 add-segment、range-keep 正常 emit `{5,15,keep}` |
| 11 | "range" 分支链（SegmentBlocksLayer） | 空 press → `range-press` payload 逐字段（clientX/clientY/ctrlKey/shiftKey/time=bounded 5s，第二次 ctrl=true time=2s）；add-segment/empty-press 不出现；dblclick 静默（empty-double-click 仅 seek 模式） |
| 12 | 成功链（WorkspacePage.rangeDecision 新宿主） | `range-decision` → **orderLog = [pushSnapshot, call:add_range_decision]**（先快照后写）+ pushSnapshot 参数 `(project, ["edits"], "手动范围")` + `call("add_range_decision", 2, 6, "delete")` → project-updated 末次载荷 = patch envelope；**`props("rangeSelection")` ≡ mock 的 selectedRange ref（§2.3 接线身份断言）** |
| 13 | 失败链（WorkspacePage.rangeDecision） | `call` 返回 `{success:false, error:"Invalid range"}` → showToast `("手动范围创建失败: Invalid range","error",3000)` + project-updated 零新增 |

- **既有 vitest 断言零删改**（两既有宿主纯 append 新 describe，R0-3 门禁 grep 0 命中自证）；测试侧裁量登记：① 聚焦断言需 `attachTo: document.body`（happy-dom 的 focus() 对脱离文档的树为 no-op，VTU 默认 detach 挂载；本仓首例 focus 断言，无既有惯例可循）；② 既有 WorkspacePage 各宿主 useSegmentEdit mock 不含 selectedRange → 编辑器走 local ref 回退（设计内，§2.3），既有宿主零改动仍绿；③ 新宿主 mock 照 trackEdit 脚手架，仅 useSegmentEdit 增 `selectedRange` ref + useUndoRedo 的 pushSnapshot 提为模块级捕获 mock（顺序断言用）。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，**exit 0**）

- pytest：**819 passed**（后端零改动，与 P3-5 持平）
- ruff：All checks passed（0 problems）
- vitest：**814 collected / 813 passed**（唯一失败 = useRowLayout.perf.test.ts 挂载墙钟，record-3.0.3 §5 遗留 #5 已登记环境例，门禁判定口径内；801 → 814 = 本步 +13）
- build：vue-tsc --noEmit + vite build 通过；lint：eslint 0/0
- 红线：后端 diff 白名单/禁改面为空（后端零改动）；R0-2 events 双侧（本步零新事件）；R0-3 后端断言零删改 0；R0-3 前端白名单外零删改（本步两既有测试宿主纯新增，TranscriptRow 白名单外命中 0）；R0-5 dev.py/build.py 零改动
- 汇总：`===== 门禁汇总: 全部通过 (exit 0) =====`

## 6. 偏离与边界登记

- **无实质偏离**：矩阵 ON 六格 + OFF 零回退逐格覆盖（§3 表）；Ctrl/Shift 手势既有用例同参对照逐字节一致；默认 OFF 一切如旧。
- **接线值偏离（已登记 §2.1）**：multi 路径 empty-area-mode 用 `'seek'` 而非 SPEC 接线点 1 字面 `'range'`——矩阵等价适配（WaveformRow P3-3 冻结链只转发 empty-press），SPEC 矩阵落点（handleRowEmptyGesture）字面达成。
- **lane 建段门控外延（已登记 §2.2）**：`:build-mode="buildMode && !rangeMode"` 落两处（multi 行 + basic extension lane），双 toggle 同 ON 时建段全局暂停——「lane/副轨区不涉及」格的取值选型，非 SPEC 明文，登记待负责人追认。
- **未验证边界（归 P4 真机冒烟清单 #6，beta.3）**：真机拖拽跟手性、气泡定位观感（+6px 偏移与边缘夹取的手感）、amber 预览色与红/蓝既有覆层的对比度、触控板惯性滚动中的框选稳定性；气泡 Enter 直接确认（focus 已断言，native button 键盘行为未单测）；多显示器/DPI 缩放坐标。
- 波形覆层三态（keep 蓝 / pending 半透明）属 **P3-8**，本步覆层渲染零触碰；建议面板「手动范围」分组与时间码入口属 **P3-7**，本步面板零触碰。

## 7. 红线自证

- 改动文件集 = 3 个前执行者产品文件（WaveformEditor.vue +337/-8 · SegmentBlocksLayer.vue +24/-1 · WorkspacePage.vue +27/-1）+ 2 个既有测试宿主纯 append（+414/-0 · +37/-0）+ 1 个新建测试宿主 + 文档——`git diff dev-3.0.4 --name-only -- frontend/` 仅上述 6 个前端文件；
- 不动面逐一核对：TrackLane.vue / WaveformRow.vue / useSegmentEdit.ts / useWorkspaceActions.ts / core/ + main.py（后端全部）/ pywebvue/ —— diff 为空；
- 既有 vitest 断言零删改（两宿主既有用例逐字未动，R0-3 grep 0）；Ctrl/Shift 与 v3.0.3 逐字节一致（#4/#5 与既有 M5-3 用例同参数对照）；默认 OFF 一切如旧（#6/#7/#8 + 既有用例全绿）。

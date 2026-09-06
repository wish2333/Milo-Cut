# record-3.0.4-P3-2：编辑扫掠覆盖副轨（M3-1，R3.1，T1 方案 A，裁决反转）

> 日期：2026-09-05　分支：`dev-3.0.4-p3-2`（自 `dev-3.0.4` 拉出，待合入，不自行合并）
> 对应 PLAN：Phase 3 / P3-2　SPEC：M3-1（触点表 5 行 + 边界 + 验收）　PRD：§1.3（断言反转白名单唯一例外）+ R3.1 + §6-Q1
> 承接：3.0.3 M1-3 交付的 variant 分流（saveEdit 内 `track-text` / `update-text`）——本步零触碰、直接复用

## 1. 交付物清单

| 文件 | 性质 | numstat（vs `dev-3.0.4`） | 说明 |
|---|---|---|---|
| `frontend/src/components/workspace/TranscriptRow.vue` | 受控改点 | +4/-4 | A 项：删除两处 track 早退（§2.A）；注释同步改写（M1-3 豁免语义作废） |
| `frontend/src/components/workspace/TranscriptRow.test.ts` | 断言反转（本版唯一白名单） | +13/-2 | B 项：`:270-275` 用例整体反转改写（§3） |
| `frontend/src/components/workspace/Timeline.vue` | 受控改点（仅文案） | +13/-1 | D 项：`editSweepLabel` computed + 模板替换一行（§2.D）；`:title` 属性零改动（英文 tooltip，非文案面） |
| `frontend/src/components/workspace/Timeline.test.ts` | 新增用例 | +49/-0 | D 项 3 例：主轨两态零回退 / 轨视图「编辑〈轨名〉」/ 轨名缺失回落 |
| `frontend/src/pages/WorkspacePage.trackEdit.test.ts` | 新建测试宿主 | 新文件 342 行 | C2/C3 项 2 例（§4；命名照 WorkspacePage.translation / correctionTrack 先例） |
| `scripts/gates-v3.0.4.sh` | 门禁脚本勘误（偏离，§6） | +8/-1 | R0-3 前端 grep 白名单实现失效修复（脚本头部「SPEC 与脚本冲突以 SPEC 为准，当场修脚本」条款执行） |
| `docs/3.0.4/record-3.0.4-P3-2.md`（本文）、`record-3.0.4.md` §1/§4、`plan-v3.0.4.md` P3-2 | 文档 | — | 登记与勾销 |

后端 `core/`、`main.py`、`tests/`、`pywebvue/`：**零改动**（门禁 R0-1 后端 diff 文件集与本步无关，§5）。

## 2. SPEC M3-1 触点逐条对照

### A. TranscriptRow.vue 两处 track 早退删除

- onMounted：`if (props.globalEditMode && !isTrackVariant.value)` → `if (props.globalEditMode)`（原 :328，行号漂移后符号定位一致）；
- watch：删除 `if (isTrackVariant.value) return`（原 :331）。
- 副轨行随 `globalEditMode` 进入/退出行内编辑；**仅此两处** + 注释改写。保存路径零改动（saveEdit 的 `isTrackVariant ? emit("track-text") : emit("update-text")` 分流 3.0.3 已交付，核实原样）。
- 主轨路径 diff 语义为零：两处守卫仅对 track 行生效，删除后 main 行执行条件逐字节等价（`props.globalEditMode && !false` ≡ `props.globalEditMode`）。

### B. 断言反转白名单（本版唯一一处，PRD §1.3）

见 §3 登记表。白名单外任何 `expect(` 删除/改写 = 0（门禁 R0-3 实测，§5）。

### C. 新增断言

1. **反转用例本体**（B 项）：断言 `input.edit-text-input` 存在 + 退出扫掠经 `track-text` 批量保存（`update-text` 不触发）——一例覆盖进/出两态；
2. **切轨 flush**（C2）：挂 `WorkspacePage.handleSelectListTrack`，实现要点见 §4；
3. **编辑态跨轨保持**（C3）：`globalEditMode` 随主轨↔副轨切换不重置（1 例固化，Q1 裁决：现状即全局态，产品代码零改动）。

### D. Timeline 按钮文案

- `editSweepLabel` computed：`isTrackMode` 且 `activeTrackName` 非空 → 「编辑〈轨名〉」（轨名来源 = Timeline 既有 `activeTrackName` prop，P1-6 透传链）；`globalEditMode` → 「退出编辑」（两视图共用）；主轨视图 → 「编辑字幕」逐字节不变；
- 轨名缺失（activeTrackName null）防御性回落「编辑字幕」（WorkspacePage 现轨名恒伴随轨 id 出现，回落仅为兜底，测试固化）。

### E. 边界核对

- 仅列表侧；波形侧不入版（Q2 版本池）；撤销谓词表零新增（useTrackEdit.ts 只读核实，text 恒 `["tracks"]`，M1-4 谓词行 1 原样）；
- v-memo 依赖数组（Timeline.vue :695，SPEC 引 :644 行号漂移）已含 `globalEditMode` 与 `isTrackMode`：**零改动**（扫掠开启/切轨时行重渲染由既有依赖覆盖）；
- `useTrackEdit.ts` / `useListTrackSelector` / `handleSelectListTrack` 逻辑本体：**零改动**（C2 只把既有 flush 测出来）。

## 3. 断言反转登记表（R0-3 唯一例外，PRD §1.3；总记录 §4 已同步）

| 文件:行 | 原意图 | 新意图 | 反转理由 |
|---|---|---|---|
| TranscriptRow.test.ts:270-275（改写后 :271-286） | 「never enters text edit under globalEditMode」：globalEditMode 下副轨行**不得**进入行内编辑（断言 `input.edit-text-input` 不存在）——固化 3.0.3 M1-3 豁免 | 「enters text edit under globalEditMode (track variant)」：globalEditMode 下副轨行**随扫掠进入**行内编辑（断言 `input.edit-text-input` 存在），退出扫掠经 `track-text` 批量保存且 `update-text` 不触发 | R3.1 裁决反转（T1 方案 A）：3.0.3 M1-3 豁免经一版使用被用户证伪为「按钮坏了」（US-T1-1），Q1 裁决编辑态为跨轨全局态；意图与断言同步反转，非削弱断言（新增退出通道分流断言 ×2） |

反转 diff 原文（旧断言 vs 新断言，`git diff dev-3.0.4`）：

```diff
-  it("never enters text edit under globalEditMode", async () => {
+  it("enters text edit under globalEditMode (track variant)", async () => {
     const wrapper = mountTrack({ globalEditMode: true })
     await nextTick()
-    expect(wrapper.find("input.edit-text-input").exists()).toBe(false)
+    expect(wrapper.find("input.edit-text-input").exists()).toBe(true)
+    // exiting the sweep batch-saves through the track channel
+    await wrapper.find("input.edit-text-input").setValue("swept edit")
+    await wrapper.setProps({ globalEditMode: false })
+    expect(wrapper.emitted("track-text")).toBeTruthy()
+    expect(wrapper.emitted("track-text")![0]).toEqual(["swept edit"])
+    expect(wrapper.emitted("update-text")).toBeUndefined()
     wrapper.unmount()
   })
```

## 4. C2 flush 断言实现要点（WorkspacePage.trackEdit.test.ts）

- **被测对象 = 既有接线本身**：`handleSelectListTrack`（WorkspacePage.vue:997-1000，SPEC 引 :952-957 行号漂移）先 `await flushPendingTrackUpdates()` 再 `selectListTrack(trackId)`——产品代码零改动，本条只是把它测出来；
- **useTrackEdit 保持真实**（不 mock）：真实 `editTrackSegmentText` 经 Timeline stub 的 `update-track-text` 事件驱动 → 真实 pendingMap（300ms debounce key `trk_x:tseg-1:text`）；`vi.useFakeTimers()` 冻结防抖时钟，保证切轨时的未决态确定成立（提交只能来自 flush，不可能来自定时器）；
- **调用顺序观测**（spec 建议 mock 层验证）：桥 mock 在 `update_track_segment`（flush 内核的后端提交点）打点 `flush-commit`；对 Timeline stub 的 `activeTrackId` prop 挂 Vue `watch` 打点 `select-track:<id>`（真实 `useListTrackSelector` 的落点）；断言 `orderLog === ["flush-commit", "select-track:null"]` = flush 回调先于 selectListTrack 执行；
- **无丢失断言**：`call("update_track_segment", "trk_x", "tseg-1", { text: "flushed draft" })`——旧轨 pending 草稿携带全文提交（防抖从未自行触发，fake timers 下唯一提交通路 = flush 的 `clearTimeout + callback()`）；
- 其余脚手架照 WorkspacePage.correctionTrack.test.ts 先例（除 useTrackEdit 外 composable 全 mock、`vi.resetModules` 每例重建模块图）。

## 5. 门禁（bash scripts/gates-v3.0.4.sh all，exit 0）

- pytest：**810 passed**（P3-1 登记的当期期望总数，全绿；后端零改动）
- ruff：0 problems
- vitest：**795 collected / 794 passed**（唯一失败 = useRowLayout.perf.test.ts，已登记环境例；较 P3-1 基线 790 collected 净增 5 = Timeline +3 + 新宿主 +2，反转用例数不变）
- build：vue-tsc --noEmit + vite build 通过；lint：eslint 0/0
- 红线：R0-1 后端 diff 文件集 ⊆ 白名单（全部为 P1/P2 已登记 hunk，本步零新增）；禁改面空；R0-2 events 双侧 1/1；R0-3 后端断言零删改；**R0-3 前端断言白名单外零删改 = 0**（经 §6 脚本勘误后实测；本步全部前端 expect 删除 = 反转用例 1 行，恰在白名单内）；dev.py/build.py 零改动

## 6. 偏离登记

1. **scripts/gates-v3.0.4.sh R0-3 前端 grep 勘误（唯一实质偏离）**：原管线 `grep -E '^-\s*expect\(' | grep -v 'TranscriptRow.test.ts'` 按行过滤，而被删 expect 行本身不含文件名，白名单**恒失效**——本步为首次真实反转，实测原命令对「仅含白名单内 1 行删除」的 diff 报 1（必然 FAIL，门禁无法 exit 0）。执行脚本头部既定条款「SPEC 与本脚本冲突时以 SPEC 为准，当场修脚本」：改 awk 以 `+++ b/<path>` hunk 头归属文件后计数，判定口径不变（白名单【文件】外命中才 fail）。双向实测：当前 diff = 0（白名单内删除不计数）；人为在 Timeline.test.ts 删 1 行 expect（白名单外）= 1（守卫仍咬合）。SPEC M5 命令块的 PRD §9 同款缺陷不动（SPEC 为意图层，脚本为实现层，登记于此）。
2. Timeline.vue 按钮 `:title`（英文 tooltip "Edit all subtitles"）未随文案感知：SPEC M3-1 触点表明确范围 = 按钮文案，title 非文案面，保持最小 diff；如需同步登记 3.0.5 候选。
3. TranscriptRow.test.ts 反转用例在 SPEC 最低要求（断言 input 存在）之上补退出通道分流断言 ×2（track-text 触发 / update-text 不触发）：同一用例「整体改写」范围内的加强，非白名单外改动。

## 7. 红线自证

- 本步改动文件集 = TranscriptRow.vue / TranscriptRow.test.ts / Timeline.vue / Timeline.test.ts / WorkspacePage.trackEdit.test.ts（新建宿主）/ gates 脚本（§6 偏离 1）/ 文档——WorkspacePage.vue、useTrackEdit.ts 及其余前端文件零改动（`git diff dev-3.0.4 --stat` 见 §1，无越界文件）；
- 主轨既有断言全绿（TranscriptRow 37 例 / Timeline 30 例全过，主轨用例零改动）；
- 撤销谓词表零新增：useTrackEdit.ts 零触碰，text 恒 `["tracks"]`。

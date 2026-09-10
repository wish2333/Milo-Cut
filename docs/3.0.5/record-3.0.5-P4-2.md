# record-3.0.5-P4-2：R5.7+R5.9+R5.10+R5.14 覆层/文案/守卫族（约束③ 同 commit）

> 步骤：PLAN P4-2 · 依据：[SPEC M5.7](./spec-v3.0.5.md)（实施裁决 1-5）+ M9 顺带表（R5.9/R5.10/R5.14）· [PLAN](./plan-v3.0.5.md) P4-2 · [PRD](./PRD-v3.0.5.md) R5.7（S4/SG-3/焦点 4）
> 分支：`dev-3.0.5-P4-2`（已合入已删）· 提交：见 §6

## 0. 序 6 golden 锁先行确认

动手前复跑 `SegmentBlocksLayer.test.ts`：**26/26 全绿**（基线确认后开工）。收口后该文件 **28/28**（rejected 例按计划反转 + 相交/单例 title 2 例新增，golden class 快照面零触碰）。

## 1. 改动清单

### R5.7（M5.7，冻结矩阵落地）

| 文件 | hunk | 内容 | 类别 |
|---|---|---|---|
| `TrackLane.vue` | props/emits | 增 `globalEditMode?: boolean` prop + `toast: [msg]` emit（纯增）；trim 门 `:update-time="globalEditMode ? undefined : updateTime"`（undefined = M5-2 既有只读语义，零新机制） | 受控（裁决 1） |
| 同上 | 菜单三 handler | `onDeleteSegment/onClearTrack/onDeleteTrack` 经 `guardEditMode()`（置 toast「请退出编辑模式后重试」+ 关菜单不 emit）；`onLaneClick` 建段路径同拦；查询类（seek/折叠）不拦（裁决 5 边界天然清晰） | 受控（裁决 1） |
| `WaveformRow.vue` | TrackLane 实例 | 透传 `:global-edit-mode` + `@toast` 转发（SegmentBlocksLayer 同款链） | 只增 |
| `WaveformEditor.vue` | TrackLane 实例 :1546 | 同上两行 | 只增 |
| 同上 | 双 toggle title :1247/:1257 | 冻结矩阵 + 主/副轨不对称理由全文（裁决 3：点名主体不写「冻结矩阵」四字了事） | 文案 |
| `README.md` | v3.0.4 段尾 | 「Edit-mode freeze matrix (v3.0.5)」一条（裁决 3 README 面） | 只增 |

**SG-3 红线**：共享 SegmentBlock/SegmentBlocksLayer 零无差别拦截（反向断言锁，见 B-r1）。

### R5.9 + R5.6③（覆层/文案）

| 文件 | hunk | 内容 |
|---|---|---|
| `Timeline.vue` | :625 | 编辑态 toggle title 中文化两态（含冻结矩阵一句） |
| `SegmentBlocksLayer.vue` | :390 区 | 覆层 title 语义化 `editRangeTitle()`：`{保留\|删除}范围 {X}s - {Y}s（{待确认\|已确认}）` + keep×delete 相交对尾注「；与重叠区间导出按删除处理」 |
| 同上 | visibleEditRanges computed | **R5.6 裁决 3 相交预聚合**：成对比较置 `overlapsOpposite` 标志（一次遍历，渲染层零逻辑；editRangeClasses/golden class 面零触碰） |
| `main.py` | :3108-3118 | 重译拒绝文案语言码经 `_TRANSLATION_LANGUAGES` 转显示名（`（en）`→`（English（en））`，map 查找全增安全） |

### R5.10（覆层退场 + 显示门 + 消泡）

| 文件 | hunk | 内容 |
|---|---|---|
| `SegmentBlocksLayer.vue` | visibleEditRanges filter | **rejected 过滤新增分支**（E-6 只增：confirmed/pending 面 golden 锁零触碰；rejected 不再渲染） |
| `WaveformEditor.vue` | 建段 toggle :1243-1254 | 显示态改绑实际门 `buildMode && !rangeMode`：全亮「建段中」/ 半亮（bg-blue-600/50）「建段（已暂停）」/ 灰「建段」 |
| 同上 | onMounted/onUnmounted | 气泡两关闭路径：document 捕获级 `keydown`（Esc）+ `pointerdown`（容器外点，`contentEl/stackEl` contains 豁免内部点击） |

### R5.14（渲染层拼接）

| 文件 | hunk | 内容 |
|---|---|---|
| `AIAssistantPanel.vue` | 错误区 :529-531 | `errorMsg.includes("同语言翻译轨已存在")` 条件拼接「（波形区右键该轨 → 清空轨道/删除轨道）」——渲染层拼接（SG2-6），useLlmTasks 数据层零污染 |

## 2. 用例登记（M-gate 前端 R5.7 ≥4 + R5.10 半边；实际 +7 净增 + 1 反转）

| # | 用例 | 覆盖 |
|---|---|---|
| F1 | trim 门 | globalEditMode ON → SegmentBlock 收到 updateTime=undefined（只读） |
| F2 | 退出恢复 | setProps 关 → updateTime 恢复转发 |
| F3 | lane 三项拦截 + 退出恢复 | 三结构项全拦零 emit + toast ≥3 次文案精确 + 退出后清空轨恢复流转 |
| F4 | 建段冻结 | buildMode ON + 编辑态 → 点击 lane 零 create-at + 同款 toast |
| F-r1 | **主轨反向断言（裁决 4）** | 真实 SegmentBlock 挂 globalEditMode=ON + updateTime → trim 拖拽两次 updateTime 调用（防未来共享层补守卫误伤主轨） |
| F5 | rejected 退场（R5.10 半边） | rejected range 零覆层渲染（原 :364/:366「仍渲染」断言反转） |
| F6 | 相交尾注 | keep×delete 相交对双方 title 均含「；与重叠区间导出按删除处理」 |
| F7 | 单例语义 title | 孤立 keep pending → 「保留范围 1.0s - 4.0s（待确认）」无尾注 |

R5.14 文案拼接无断言面（M-gate 豁免明示，plan :291）；Esc/点外消泡与建段半亮无独立断言面（jsdom 手势成本 > 收益，随 beta.3 冒烟），登记 §5。

## 3. 断言反转清单（随本步落 record，M0-3 追认制）

| 位置 | 原断言 | 新断言 | 依据 |
|---|---|---|---|
| `SegmentBlocksLayer.test.ts` 原 rejected 例（:364/:366 区） | 「rejected ranges are still rendered, unfiltered（status quo kept）」长度 1 + class 全等 | 「rejected ranges are hidden」长度 **0** | R5.10 裁决隐藏（E-6 新增分支） |
| 同文件 `findOverlays`（非 expect 行） | `'[title^="Delete range"]'` | `'[data-test="edit-range-overlay"]'`（组件模板增 data-test） | R5.9 title 中文化后英文前缀失配；选择器追认制（非断言面） |

## 4. 验证（全套门禁；stdout 摘录）

`bash scripts/gates-v3.0.5.sh`（三段全跑）→ **exit 0**：

```text
===== 后端门禁 =====
  867 passed in 9.15s                        # main.py 1 行后端改动零破坏
  All checks passed!                         # ruff 0 problems
===== 前端门禁 =====
  Test Files  1 failed | 63 passed (64)
  Tests       1 failed | 878 passed (879)    # P4-1 872 → 879（+7）；唯一失败 = useRowLayout.perf 环境例（已登记，R5.16 根修）
  [PASS] build 通过（mountBlock 类型钩子 1 轮修复后绿） / lint 0/0
===== 红线检查 (基准 = v3.0.4) =====
  全部 PASS（禁改面为空；events 双侧零改动；断言白名单外零删改——本步反转 2 处均已在本 record §3 登记）
===== 门禁汇总: 全部通过 (exit 0) =====
```

## 5. 解释登记与未验证边界

- **Esc/点外消泡与建段半亮无独立断言**：两者均为监听器/纯显示面；jsdom 模拟 document 捕获事件 + 气泡聚焦链成本高于收益，真机手感随 beta.3 冒烟（plan :381 口径内）。
- **相交检测 O(n²)**：n = 视窗内 range 数（常态 <20），一次 computed 内成对比较可忽略；预聚合在 computed 层（响应式缓存），渲染层零逻辑（裁决 3）。
- **rejected 过滤与相交检测同 computed**：rejected 先过滤再相交判定——已拒绝的区间不参与相交语义（其裁决已撤回），口径自洽。
- **主轨反向断言的措辞**：SegmentBlock 的 globalEditMode prop 声明未消费 trim 门（现状基线），F-r1 锁的正是「未来有人在此补守卫」这一回归面。
- **R5.14 后端串**：main.py 显示名改动使错误串变化——既有 pytest 全绿（无断言旧串裸码形态的用例）；前端拼接判据子串「同语言翻译轨已存在」在显示名拼接后仍为前缀（f-string 首段），判据不受扰。

## 6. 改动登记表追加

| 步 | 文件 | 改动 | 关联 | 类别 |
|---|---|---|---|---|
| P4-2 | TrackLane.vue + WaveformRow.vue + WaveformEditor.vue + README.md | globalEditMode prop + trim 门 + 菜单/建段拦截 + toast emit + 两父透传 + 冻结矩阵文档化 | R5.7 | 受控（M5.7 裁决 1/2/3） |
| P4-2 | SegmentBlocksLayer.vue | visibleEditRanges rejected 过滤（E-6）+ 相交预聚合 overlapsOpposite + editRangeTitle 中文语义化 + data-test | R5.10 + R5.9 + R5.6③ | 只增 + E-6 新增分支 |
| P4-2 | WaveformEditor.vue | 建段 toggle 显示门改绑 + Esc/点外消泡两监听 | R5.10 | 显示面 + 监听只增 |
| P4-2 | Timeline.vue | 编辑态 title 中文化两态 | R5.9 | 文案 |
| P4-2 | main.py | 重译拒绝显示名映射（1 处 f-string） | R5.9 | 登记改点（后端 1 行族） |
| P4-2 | AIAssistantPanel.vue | 错误区渲染层条件拼接指引 | R5.14 | 渲染层只增（SG2-6） |
| P4-2 | tests（SegmentBlocksLayer/TrackLane/SegmentBlock） | 反转 2 处（§3 登记）+ 净增 7 例 | R5.7/R5.10 | 追认反转 + 只增 |

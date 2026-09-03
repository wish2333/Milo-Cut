# record-3.0.2-smoke-fix-1: 清单 A/B 首轮真机反馈修复（5 项）

日期：2026-09-02　分支：`dev-3.0.2-fix-smoke-1`　合入：`dev-3.0.2`

| # | 反馈 | 根因 | 修复 |
|---|---|---|---|
| 1 | 64px 不显示任何字幕块、80px 主块消失 | 主区包裹 div 与 SegmentBlocksLayer **双重 24px 徽章留白**：64px+1 副轨时块面积算成负数 | SegmentBlocksLayer 增 `fillContainer`（根节点 inset-0，父级独占留白）；WaveformRow 传入。留白自适应：`clamp(round(rowHeight×0.15), 8, 24)`——64px 行留白 10px（原 24px 占一半） |
| 2 | 副字幕轨无操作途径、无右键菜单、清空字幕不作用 | ①后端**无删除副轨段 API**（v3.0.1 仅 trim）；②lane 块无右键菜单；③「清空字幕」按语义仅清主轨（名称即含义） | 后端新增 `delete_track_segment(track_id, segment_id)`（移除段+连带删锚定 binding、tracks+bindings patch、主轨不动，镜像 update_track_segment 语义）+ main.py @expose；TrackLane 增块右键菜单（删除此条字幕/清空此轨，Teleport+openContextMenu 互斥）；链路 lane→row→editor→WorkspacePage→useWorkspaceActions.handleDeleteTrackSegment（失败 toast 可见，含「请重启应用后端」提示）；清空此轨 = 前端逐段循环删除（确认框）。后端测试 +3（删段/连带删 binding/未知 id 拒绝） |
| 3 | 右键关闭菜单后有时打不开新菜单 | contextMenuManager 异步注册（setTimeout 0）竞态：旧菜单的待注册监听在新菜单开启后才落地，once-contextmenu 立即关闭新菜单 | openContextMenu 取消同菜单族的 pendingRegister（clearTimeout），closeActive 一并清理 |
| 4 | 多行模式空白点击无法新增字幕 | M5-3 裁决空点 = seek，建段仅 Ctrl+拖 | 控件栏增「建段」toggle（`build-mode-toggle`，运行时态默认关）：开 → 空点恢复 basic 建段语义，关 → seek/scrub |
| 5 | 播放跟随没有滚动动画；字幕列表不随播放滚动 | ①跟随为瞬时赋值（回环分类精确性取舍）；②列表跟随 v3.0.1 起仅在选中时滚动，非本版删除 | 跟随写改 `scrollTo({behavior:"smooth"})` + **800ms 回声窗**（动画中间事件不误判手动/不同步状态；happy-dom 无 scrollTo 时回退瞬时，测试口径不变）；Timeline 增 playheadSegmentId 跟随 watcher（滚动到播放行）+ `scrubbing` prop 抑制（M5-3 契约接线：editor @scrubbing → WorkspacePage ref → Timeline） |

## 门禁

pytest 711（+3 后端删除用例）✓ / vitest 657（+4：fillContainer/主区几何/lane 菜单 ×2/scrubbing 透传）✓ / build ✓ / lint 0 ✓ / ruff 0 ✓ / events+models diff vs `v3.0.2-base` = 0 ✓（新桥方法不在两 diff 口径内，与 update_track_segment 先例一致）

## 备注

- 反馈 2 的「点了没用」如出现在最新代码上：`delete_track_segment` 是新增后端方法，**需重启 dev.py 的 Python 进程**才会进入 pywebview API 面（前端热更新不含后端）。
- 反馈 2a「字幕时间线切换到副字幕」（列表切换显示/编辑副轨）为独立功能，记入下一批次（列表当前仅主轨）。

## 追加（二轮反馈澄清：3/4/5 未解决的处理）

| # | 二轮反馈 | 处理 |
|---|---|---|
| 3 | 右键关闭后打不开新菜单 | **真根因**：互斥锁关闭回调与开启新菜单共享同一 `contextMenu` ref——开新菜单先 set 状态、后调旧 close（把 ref 置 null）→ 新菜单被自身注册流程抹除。修复：先 `openContextMenu`（旧 close 先跑）再 set 新状态；SegmentBlocksLayer 与 TrackLane 同步修复。回归测试：连开两块菜单持续可见（旧代码此测试必红） |
| 4 | 建段 toggle 无效 | 实证测试证明管线正常（toggle → 行层收到 'add'/'seek' 切换，+2 例）。请确认：①控件栏「建段」按钮是否变高亮「建段中」；②点击的是行内空白（块上不放段）。若仍无效请描述点击位置 |
| 5 | 跟随无动画 + 列表不滚动 | 波形 smooth 已合入（需 WebView 支持 scrollTo options；WKWebView/WebView2 均支持）；列表跟随已恢复（playheadSegmentId watcher + scrubbing 抑制接线）。请重验；若列表仍不滚，告知播放时右侧列表是否有蓝色播放指示条移动 |

另：反馈 2 需**重启 dev.py 的 Python 进程**（新增后端方法），若已重启仍失败请 F12 控制台截图报错。

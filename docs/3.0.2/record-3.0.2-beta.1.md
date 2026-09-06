# record-3.0.2-beta.1：多行显示冒烟通过（清单 A）

日期：2026-09-02　tag：`v3.0.2-beta.1`（落于含三轮真机反馈修复的 dev-3.0.2 HEAD）

## 冒烟结论（用户签字）

清单 A 全项通过：多行分行显示（行首徽章/末行缩短）、竖向滚动、播放头换行、每行秒数/行高 select、basic↔multi 往返、千段工程（1200 段 × 双语副轨）体感不回退。

## 冒烟中发现并已修复（详见 record-3.0.2-smoke-fix-1.md）

1. 64/80px 主块不可见（双重徽章留白）→ fillContainer + 留白自适应
2. 副轨无删除途径 → 后端 delete_track_segment/delete_track/clear_track_segments + lane 右键菜单全链
3. 右键菜单竞态 → contextMenuManager pending 注册取消
4. 多行空点建段 → 建段 toggle（双模式，默认关）
5. 跟随动画/列表跟随 → smooth 试验回退（瞬时跳位）+ Timeline playheadSegmentId 跟随恢复 + scrubbing 抑制
6. 撤销三类问题 → lane 操作快照 + trim 捕获合并（1.2s 窗）
7. 新建副轨按钮 + 连续播放 NaN 空白防御

## 遗留

- Windows 平台验证待补（清单 C 全量回归覆盖）
- 播放跟随为瞬时跳位（smooth 依赖引擎支持，本版不做，见总记录遗留清单）

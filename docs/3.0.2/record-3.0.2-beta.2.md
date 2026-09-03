# record-3.0.2-beta.2：交互手势冒烟通过（清单 B）

日期：2026-09-02　tag：`v3.0.2-beta.2`（与 beta.1 同 commit：清单 A/B 反馈修复交织交付，见 smoke-fix-1 record）

## 冒烟结论（用户签字）

清单 B 通过：滚轮四手势（原生滚动/Ctrl spr/Ctrl+Shift 行高/触控板）、scrub 手感（32ms 节流）、Shift 跨行框选、trim 跨行 + Alt snap、建段模式（双模式空点建段）、副轨 lane 菜单（删段/清空/删轨）及其撤销。

## 平台注记

macOS 签字通过；Windows（WebView2 deltaMode 观察）待清单 C 全量回归一并覆盖——不阻塞 beta.2 tag（用户 2026-09-02 授权）。

# Record: P1-3 M1-3 编码回退 + M1-4 词边界吸附

> 日期: 2026-08-30 · 分支: `dev-3.0.0`

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/subtitle_service.py` | 提取 `_read_text_with_fallback`（utf-8-sig → gb18030 → latin-1）；`parse_srt` / `validate_srt` 共用（修复导入路径 GB18030 崩溃的文档-实现偏差） |
| `core/project_service.py` | `split_segment` 新增 `snap_to_word: bool = False`：吸附最近词 start（限 1s 内，不跨段传送）；吸附时 words 按词 start 精确分配；envelope 追加 `snap_offset_ms` |
| `main.py` | `split_segment` @expose 透传 `snap_to_word`（信封不变） |
| `frontend/src/composables/useEdit.ts` | `splitSegment` 增加第三参，返回 `{ok, snapOffsetMs}` |
| `frontend/src/pages/WorkspacePage.vue` | 波形时间指针分割且段含 words 时启用吸附；toast「已吸附词边界 +Nms」 |
| `tests/test_srt_encoding.py`（新） | 3 条：GB18030 parse 无乱码 / validate 不回归 / utf-8 行为不变 |
| `tests/test_segment_words.py` | 追加 3 条 snap 测试（吸附/无 words 不吸附/flag 关闭保持比例切分） |

## 验证命令与实际输出

```
uv run pytest -q                       -> 全绿（495 passed）
uv run ruff check <触及文件>            -> 0 问题
cd frontend && bun run build           -> 通过（vue-tsc + vite）
cd frontend && bun run test            -> 251 passed
```

## 未验证边界

- ★ 真实 GB18030 SRT 文件（用户文件或继续用生成夹具）→ 批次冒烟
- 吸附 toast 手感（真机手测三次命中词边界）→ 批次冒烟

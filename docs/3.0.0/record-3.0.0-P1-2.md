# Record: P1-2 M1-2 split/merge 维护 words

> 日期: 2026-08-30 · 分支: `dev-3.0.0`

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/timeline_utils.py` | 新增 `split_words(words, text, position, a_text, b_text)`：累计词字符偏移，取距切点最近的词边界；偏差 >2 字符或退化输入（<2 词/空文本）返回 `([], [])`——宁可缺失不可错位 |
| `core/project_service.py` | `split_segment` 接线（a/b 段 words 分别赋值，对齐失败双空）；`merge_segments` 接线（words 拼接 + 按 start 排序）；ED-rebind 逻辑未动 |
| `tests/test_segment_words.py` | 新增 9 条测试 |

## 实现要点

- 对齐策略：`offsets[k]` = 词 k 起始的累计字符偏移；`best_k = argmin |offsets[k] - position|`（k ∈ [1, len-1]），`|dev| > 2` 判不可靠
- merge 天然有序前提是各段自身有序（ASR 输出保证），合并后仍按 start 显式排序兜底
- 与既有回归正交：`test_segment_sort_invariant.py` 13 条不受影响（split/merge 本就保序）

## 验证命令与实际输出

```
uv run pytest tests/test_segment_words.py tests/test_timeline_utils.py tests/test_segment_sort_invariant.py -q  -> 29 passed
uv run pytest -q                                                  -> 全绿（489 passed）
uv run ruff check core/timeline_utils.py core/project_service.py tests/test_segment_words.py -> 0 问题
```

## 未验证边界

- UI 波形拆分手测归入批次双平台冒烟（plan §5 清单第 5 项）

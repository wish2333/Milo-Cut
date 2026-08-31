# Record: P4-1 M11-1 words 消费（纠错回贴 + 波形 hover 词高亮）

> 日期: 2026-08-31 · 分支: `dev-3.0.0` · 依据: SPEC M11-1 / PRD D1.2 + D1.3 / plan P4-1

## 改动文件

| 文件 | 改动 |
|---|---|
| `core/timeline_utils.py` | 新增 `reattach_words(words, new_text, seg_start=None, seg_end=None)` 纯函数 + `_synthesize_words`/`_tokenize_fragment` 内部实现（分词约定与 `scripts/fabricate_words.py` 同款：CJK 单字/拉丁数字整词/其他标点单字，空白丢弃） |
| `core/correction_service.py` | `accept_subtitle_correction`（单条接受）与 `apply_subtitle_corrections`（批量应用）双链路接入回贴：`model_copy(update={..., "words": new_words})` |
| `tests/test_word_reattach.py`（新） | 14 条：纯函数 10（相同文本/局部改/删词/尾部追加/标点插入/大改清空/无 words/空 new_text/无锚词清空/段内替换插值）+ 服务接线 4（apply 回贴/apply 大改清空/apply 无 words 段/accept 回贴） |
| `frontend/src/utils/wordHighlight.ts`（新） | `findWordIndexAtTime(words, time)`：二分定位 `start <= t < end` 的词；间隙/首前/尾后/零宽词返回 -1 |
| `frontend/src/utils/wordHighlight.test.ts`（新） | 6 条（命中/边界开闭/间隙与首尾/空与单词/零宽合成词不命中/万词列表二分准确性） |
| `frontend/src/components/waveform/SegmentBlocksLayer.vue` | hover 门控 + 词高亮：`hoveredSegId` 状态（复用既有 block mousemove/mouseleave）+ `wordHighlight` computed（播放时间 clamp 到 hover 段后二分定位）；仅 hover 中且含 words 的块渲染逐词 span，命中词 `bg-blue-500/40` 高亮；其余块保持原单 span truncate 渲染零改动 |
| `frontend/src/components/waveform/SegmentBlocksLayer.test.ts` | +4 条（hover 命中高亮/越界 clamp 回退纯文本/leave 清除/无 words 段纯文本） |

## 回贴算法（`reattach_words`）

- **锚定**：对齐源取旧 `words` 拼接串（词表本身即旧文本分词真值；`seg.text` 可能含标点而 words 无，不作为对齐基准），与 `new_text` 做字符级 `SequenceMatcher(autojunk=False)`。
- **保留**：完整落在 `equal` 区间内的旧词原对象、原时间戳保留（frozen 模型直接引用，零拷贝）。
- **合成**：新文本未覆盖区（replace/insert/跨界词被弃后的子区）重新分词，在 `[prev_kept_end, next_kept_start]` 窗口内按字长比例插值时间戳，窗口外侧回退 `seg_start`/`seg_end`；合成词 `confidence=0.0` 标记为估算时轴。
- **宁可缺失不可错位**：相似度 `ratio() < 0.5`（大改）→ 整段 words 清空；无任一词完整落入 equal 区（无可靠锚）→ 清空；空 words / 空 new_text → 空。
- **全覆盖性质**：成功时 emitted tokens 拼接 == `new_text`（逐字符恰好覆盖一次），即验收"words 与新文本一致或整体为空（不允许部分错位）"的结构性保证；测试逐场景断言该性质。

## 实现决策（对 plan/SPEC 的偏差记录）

1. **接线双链路**：plan 点名 `correction_service.apply`，PRD D1.2 表述"accept 后"——`accept_subtitle_correction` 与 `apply_subtitle_corrections` 是同一能力的两条入口（逐条评审 vs 工作流批量），两处同语义接入，避免逐条接受路径漏词。
2. **hover 高亮时间源 = 播放时间**：plan"二分定位当前词"+ 验收"hover 高亮与播放音节同步"→ 高亮跟随 `currentTime`（P2-5 粗粒度时钟镜像 ≤10Hz）clamp 到 hover 段，hover 仅门控显示块——即卡拉OK 式预览的铺路语义（PRD D1.3 原文）。若真机手感反馈期望"指针位置高亮"，时间源替换为 `metrics.getTimeFromX(clientX)` 是单行改动，架构不变。
3. **渲染面收敛**：逐词 span 仅在"hover 中 + 含 words"的单块渲染，其余块（含全部静音块）保持原 truncate 单 span——重渲染与 DOM 面收敛到可视区单块，纯展示零数据写入（不产生 undo 记录、不触发 project patch）。
4. **验收方式"真实纠错后未变词时间戳保留"**：自动化等价由 `test_apply_reattaches_words` / `test_accept_reattaches_words` 承载（落库模型断言原始时间戳逐毫秒相等）；真实 LLM 链路抽查归批次冒烟（沿用 P1-5 既定口径）。

## 验证命令与实际输出

```
uv run pytest                              -> 564 passed（550 + 14）
uv run ruff check .                        -> All checks passed!（全仓 0 问题）
cd frontend && bun run test                -> 331 passed (32 files)（321 + 10）
cd frontend && bun run build               -> vue-tsc + vite 通过
bunx eslint <触及 4 文件>                   -> 0 问题
```

## 未验证边界（归批次双平台冒烟 / 真实链路）

- ★ hover 高亮与播放音节同步手感（验收标准手测项）；粗粒度 ≤10Hz 高亮刷新在播放中的观感
- ★ 真实 LLM 纠错一次后 project.json 未变词时间戳保留抽查（需 Key，沿用 P1-5 模式）
- 回贴后 undo/redo 链路（words 随 segments 层快照，M5 架构自动覆盖；真机过一遍确认）
- 合成词（confidence=0）在 SRT 导出等下游链路无消费方（words 不参与导出，代码审查确认）

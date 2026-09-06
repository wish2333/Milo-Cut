# Record: P1-1 M1-1 删除转写 SRT 回灌

> 日期: 2026-08-30 · 分支: `dev-3.0.0`

## 改动文件

| 文件 | 改动 |
|---|---|
| `main.py` | `_handle_transcription` 删除 L648-653 `import_srt(srt_path)` 回灌段；SRT 归档导出与 `srt_path` 返回值保留；新增 `update_transcript_meta(engine, language)` 调用使 transcript 元数据随转写落库（此前 update_transcript 只收 segments，engine/language 从未写入） |
| `core/project_service.py` | 新增 `update_transcript_meta` 方法（`model_copy(update=)` 保留 segments/edits；签名不动的 update_transcript 保持原样）；顺带清理存量未用导入 `AnalysisData`（ruff F401） |
| `tests/test_transcription_words.py` | 新增 4 条测试 |

## 测试

- `test_transcription_keeps_words`: mock ASR（whisper 链路）→ words 5 词保留、speaker 保留、id `seg_1.000`/`seg_3.500`（ASR 格式不回退）、engine/language 写入
- `test_transcribed_project_json_has_words`: 落盘 project.json 中 words 持久化
- `test_manual_srt_import_unchanged`: 手动 import_srt 三入口语义不变（`seg-0001` 顺序号保留、words 空）
- `test_update_transcript_meta_keeps_segments`: 元数据更新不动 segments

## 验证命令与实际输出

```
uv run pytest -q --tb=short          -> 482 passed（478 基线 + 4 新增，exit 0）
uv run ruff check main.py core/project_service.py tests/test_transcription_words.py -> 0 问题
```

## 消费点核查

- `git grep srt_path -- frontend` → 0 命中（前端不消费该字段，仅后端归档链使用）
- `git grep seg-0001 -- tests frontend` → 命中文件均为 SRT 导入路径夹具/文档，行为未变，无需更新

## 未验证边界

- ★ 真实视频 whisper 转写验证（待用户提供 ≥60min 视频；whisper/qwen mock 已覆盖，mlx 建议代码审查覆盖）
- 手动 import_srt 三入口（App.vue / WorkspacePage / useTranscript）建议下一轮双平台冒烟时各手测一次
